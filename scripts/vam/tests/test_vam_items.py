"""Regression for vam_items.py (the direct .vam/.vaj/.vab writer) and face_fit.py helpers.

Pure Python + numpy.  Synthetic fixtures first; the last test rewrites real .vab files from
the VaM install (when present) and requires them byte-identical.

Covers:
  * compute_wrap -> vam_lib.wrap_to_body rebuilds the points exactly on the body they were
    measured on, and a triangle turned over between two shapes is refused by stable_triangles
    (that flip threw 952 of Fiona's vertices through the body in VaM)
  * closest_triangles: the grid, the block split and the brute-force fallback agree
  * write_morph: .vmb layout, the 21556-vertex guard, formulas in the .vmi
  * face_fit: TPS exact at its control points, similarity recovers a known transform,
    rasterise covers a UV triangle once, transplant_iris keeps pupil and sclera
  * write_vab(parse_vab_full(x)) == x on installed items without a cloth-sim store

Usage:
  python test_vam_items.py          -> prints VAM_ITEMS_TEST=PASS
"""

import json
import os
import shutil
import struct
import sys
import tempfile
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import face_fit as ff  # noqa: E402
import vam_items as vi  # noqa: E402
import vam_lib as vl  # noqa: E402

MARKER = "VAM_ITEMS_TEST"
VAM_INSTALL = r"E:\tools\vam\vam1.22\vam1.22\1.22"


def grid_mesh(n=12, size=0.3, bump=0.0):
    """A quad grid in the XY plane (VaM winding: clockwise seen from +Z), optional bump."""
    xs = np.linspace(-size / 2, size / 2, n)
    X, Y = np.meshgrid(xs, xs)
    Z = bump * np.exp(-(X ** 2 + Y ** 2) / (2 * (size / 8) ** 2))
    verts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    quads = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            quads.append([a, a + n, a + n + 1, a + 1])        # clockwise from +Z
    poly_len = np.full(len(quads), 4, dtype=np.int32)
    poly_idx = np.array(quads, dtype=np.int32).ravel()
    poly_mat = np.zeros(len(quads), dtype=np.int32)
    return verts, poly_len, poly_idx, poly_mat


def test_wrap_exact():
    verts, pl, pi, pm = grid_mesh(bump=0.05)
    rng = np.random.default_rng(1)
    pts = rng.uniform([-0.1, -0.1, 0.01], [0.1, 0.1, 0.06], size=(400, 3))
    nrm = np.tile([0.0, 0.0, 1.0], (len(pts), 1))
    tri, tv, coeffs, ncoeffs = vi.compute_wrap(pts, nrm, verts, pl, pi, pm)
    normals = vl.outward_normals(verts.astype(np.float32), pl, pi)
    back = vl.wrap_to_body(tv, coeffs, verts, normals)
    err = np.abs(back - pts).max()
    assert err < 1e-6, "wrap does not rebuild its own points: %g" % err
    # the records survive packing
    rec = vi.pack_records(tri, tv, coeffs, ncoeffs)
    assert rec.dtype.itemsize == 40 and np.array_equal(rec["i"][:, 0], tri)


def test_stable_triangles():
    verts, pl, pi, pm = grid_mesh(n=8)
    tris = vi.vam_triangles(pl, pi, pm)
    turned = verts.copy()
    # push one interior vertex through its neighbours: the triangles around it turn over
    k = 3 * 8 + 3
    turned[k, 0] += 0.12
    ok_same = vi.stable_triangles(tris, [verts, verts], pl, pi)
    ok_turned = vi.stable_triangles(tris, [verts, turned], pl, pi)
    assert ok_same.all(), "a flat grid must be all usable"
    around = np.isin(tris, [k]).any(axis=1)
    assert not ok_turned[around].all(), "triangles turned over must be refused"
    assert ok_turned[~np.isin(tris, [k, k - 1, k + 1, k - 8, k + 8, k - 9, k + 9, k - 7, k + 7]).any(axis=1)].all()


def test_closest_triangles():
    verts, pl, pi, pm = grid_mesh(n=30, bump=0.08)
    tris = vi.vam_triangles(pl, pi, pm)
    rng = np.random.default_rng(2)
    pts = np.concatenate([rng.uniform([-0.14, -0.14, -0.02], [0.14, 0.14, 0.1], size=(3000, 3)),
                          rng.uniform([-0.14, -0.14, 0.3], [0.14, 0.14, 0.4], size=(50, 3))])  # far: brute force
    ref = vi._closest_triangles_brute(pts, tris, verts, candidates=len(tris))
    got = vi.closest_triangles(pts, tris, verts, cell=0.02, max_grid_distance=0.016, pairs_per_block=20000)

    def d(idx):
        t = tris[idx]
        return vi._point_triangle_distance2(pts, verts[t[:, 0]], verts[t[:, 1]], verts[t[:, 2]])
    assert np.allclose(d(got), d(ref), atol=1e-12), "grid / block split / fallback disagree with brute force"


def test_morph(tmp):
    deltas = np.zeros((21600, 3))
    deltas[5] = (0.001, 0.002, -0.003)
    deltas[21556 + 3] = (1, 1, 1)                      # graft: must be dropped
    formulas = ff.eye_formulas({"l": np.array([0.001, 0, 0]), "r": np.array([0, -0.002, 0])})
    info = vi.write_morph(tmp, "T Head", deltas, group="G", region="R", formulas=formulas)
    assert info["deltas"] == 1
    data = open(info["vmb"], "rb").read()
    n = struct.unpack("<i", data[:4])[0]
    assert n == 1 and len(data) == 4 + 16
    idx, d = struct.unpack("<i", data[4:8])[0], np.frombuffer(data[8:20], "<f4")
    assert idx == 5 and np.allclose(d, deltas[5])
    vmi = json.load(open(info["vmi"], encoding="utf-8"))
    assert vmi["numDeltas"] == "1" and len(vmi["formulas"]) == 6
    assert vmi["formulas"][0] == {"targetType": "BoneCenterX", "target": "lEye", "multiplier": "0.001"}


def test_face_helpers(tmp):
    rng = np.random.default_rng(3)
    src = rng.normal(size=(20, 3))
    dst = src + rng.normal(scale=0.1, size=(20, 3))
    tps = ff.TPS(src, dst)
    assert np.abs(tps(src) - dst).max() < 1e-5, "TPS must hit its control points"
    ang = 0.3
    R = np.array([[np.cos(ang), -np.sin(ang), 0], [np.sin(ang), np.cos(ang), 0], [0, 0, 1]])
    s, R2, t = ff.similarity(src, 1.7 * src @ R.T + [1, 2, 3])
    assert abs(s - 1.7) < 1e-9 and np.allclose(R2, R) and np.allclose(t, [1, 2, 3])
    # one UV triangle covering the lower-left half of a 64 texture: every texel once
    ids, cols, rows, w = ff.rasterise(np.array([[[0, 0], [1, 0], [0, 1]]], dtype=float), 64)
    assert len(ids) == len(set(zip(cols.tolist(), rows.tolist()))), "a texel rasterised twice"
    assert abs(len(ids) - 64 * 64 / 2) <= 64 and np.allclose(w.sum(1), 1)
    # iris transplant: a synthetic G2F eye (dark pupil, grey iris, white sclera) and source eye
    from PIL import Image
    size = 256
    yy, xx = np.mgrid[0:size, 0:size]
    u, v = (xx + 0.5) / size, 1 - (yy + 0.5) / size
    base = np.full((size, size, 3), 30, np.uint8)
    for c in ((0.25, 0.25), (0.75, 0.25)):
        r = np.hypot(u - c[0], v - c[1])
        base[r < 0.23] = (230, 230, 230)
        base[r < 0.195] = (120, 120, 130)
        base[r < 0.08] = (20, 20, 20)
    srcimg = np.full((size, size, 3), 220, np.uint8)
    r = np.hypot(u - 0.5, v - 0.5)
    srcimg[r < 0.19] = (60, 160, 60)
    srcimg[r < 0.065] = (0, 0, 0)
    Image.fromarray(base).save(os.path.join(tmp, "base.png"))
    Image.fromarray(srcimg).save(os.path.join(tmp, "src.png"))
    out = ff.transplant_iris(os.path.join(tmp, "base.png"), os.path.join(tmp, "src.png"),
                             os.path.join(tmp, "out.png"), log=lambda *a: None)
    o = np.asarray(Image.open(out).convert("RGB"), dtype=int)
    px = lambda uu, vv: o[int((1 - vv) * size), int(uu * size)]  # noqa: E731
    assert px(0.25 + 0.14, 0.25)[1] > px(0.25 + 0.14, 0.25)[0] + 50, "iris ring not green"
    assert px(0.25, 0.25).max() < 40, "pupil changed"
    assert px(0.5, 0.75).min() > 25 and (px(0.25 + 0.215, 0.25) > 200).all(), "rim / sclera changed"


def test_real_vabs(limit=60):
    root = os.path.join(VAM_INSTALL, "AddonPackages")
    if not os.path.isdir(root):
        return "(no VaM install: real .vab round trip skipped)"
    same = checked = 0
    for dirpath, _d, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".var") or checked >= limit:
                continue
            try:
                z = zipfile.ZipFile(os.path.join(dirpath, name))
            except zipfile.BadZipFile:
                continue
            for member in z.namelist():
                if checked >= limit or not member.lower().endswith(".vab"):
                    continue
                data = z.read(member)
                if not vl.is_dazmesh_vab(data[:200]):
                    continue
                mesh, rec, groups, tail = vi.parse_vab_full(data)
                if tail != b"\x00":
                    continue                     # cloth-sim store follows: not written by vam_items
                checked += 1
                assert vi.write_vab(mesh, rec, groups, tail) == data, "%s:%s not byte-identical" % (name, member)
                same += 1
    return "(%d real .vab rewritten byte-identical)" % same


def main():
    tmp = tempfile.mkdtemp(prefix="vam_items_test_")
    try:
        test_wrap_exact()
        test_stable_triangles()
        test_closest_triangles()
        test_morph(tmp)
        test_face_helpers(tmp)
        note = test_real_vabs()
    except AssertionError as exc:
        print("%s=FAIL" % MARKER)
        print(repr(exc))
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("%s=PASS %s" % (MARKER, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
