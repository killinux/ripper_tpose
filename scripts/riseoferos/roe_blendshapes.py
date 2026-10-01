"""H-scene blend shapes of a Rise of Eros nude body -> PMX vertex morphs, and the weights a scene clip keys.

The game adds each H scene's shapes to the nude body at run time from bare_blend_shape_pc_<outfit>_nk.ab: one
TextAsset per scene (E07, E15 ...) in protobuf wire format,
    1 mesh { 1 name, 2 shape { 1 name, 2 frame { 1 weight (100), 2 vertex { 2 index, 3 dx, 4 dy, 5 dz } } },
             3 vertex count }
with the deltas in the mesh's own space (3ds Max style: Z up, metres).  The scene's pc_<base>_nk@erosNN_* clips key
the weights (0..100) on the body renderer; a curve's attribute is the CRC32 of the shape name.

Our nude PMX keeps the game mesh's vertex order (the body is the PMX's first mesh; checked by UV before anything is
written), so each delta lands on its own vertex.  The mesh->PMX map is fitted on the torso (scale 12.5 and an axis
swap); every delta is also turned with its neighbourhood (Kabsch over the nearest vertices), because the exporter's
A-pose turned the arms the scene's arm shapes (E07_arm_p1_p5) correct.  Morph names keep to the 15 Shift-JIS bytes
a VMD can name (pmx_bone_names.py rules: E07_Pussy_fixShape -> E07_Pussy_fixSh); the English name keeps the game's.

  python roe_blendshapes.py <bare_blend_shape bundle> --list
  python roe_blendshapes.py <bare_blend_shape bundle> <bundle with the body mesh> <pmx> [--out <pmx>]
"""
import argparse
import os
import struct
import sys
import zlib

import numpy as np
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmx_add_scale_morph as psm  # noqa: E402
import pmx_bone_names  # noqa: E402


def _varint(b, p):
    r = s = 0
    while True:
        x = b[p]
        p += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, p


def _fields(b):
    """(field number, wire type, value) of one protobuf message."""
    p = 0
    while p < len(b):
        key, p = _varint(b, p)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, p = _varint(b, p)
        elif wire == 5:
            v = struct.unpack_from("<f", b, p)[0]
            p += 4
        elif wire == 1:
            v = struct.unpack_from("<d", b, p)[0]
            p += 8
        elif wire == 2:
            n, p = _varint(b, p)
            v = b[p:p + n]
            p += n
        else:
            raise ValueError("protobuf wire type %d" % wire)
        yield field, wire, v


def parse_shapes(raw):
    """{mesh name: {"count": vertex count, "shapes": {shape: [(frame weight, [(vertex, (dx, dy, dz))])]}}}"""
    meshes = {}
    for f, w, mesh in _fields(raw):
        if (f, w) != (1, 2):
            continue
        name, count, shapes = None, None, {}
        for f2, w2, v2 in _fields(mesh):
            if (f2, w2) == (1, 2):
                name = v2.decode("utf-8")
            elif (f2, w2) == (3, 0):
                count = v2
            elif (f2, w2) == (2, 2):
                sname, frames = None, []
                for f3, w3, v3 in _fields(v2):
                    if (f3, w3) == (1, 2):
                        sname = v3.decode("utf-8")
                    elif (f3, w3) == (2, 2):
                        weight, deltas = 100.0, []
                        for f4, w4, v4 in _fields(v3):
                            if (f4, w4) == (1, 5):
                                weight = v4
                            elif (f4, w4) == (2, 2):
                                d = {ff: vv for ff, _ww, vv in _fields(v4)}
                                deltas.append((d.get(2, 0), (d.get(3, 0.0), d.get(4, 0.0), d.get(5, 0.0))))
                        frames.append((weight, deltas))
                shapes[sname] = frames
        meshes[name] = {"count": count, "shapes": shapes}
    return meshes


def bundle_shapes(path):
    """{scene (TextAsset name, e.g. E07): parse_shapes(...)} of a bare_blend_shape_*.ab bundle."""
    out = {}
    for o in UnityPy.load(path).objects:
        if o.type.name == "TextAsset":
            t = o.read()
            raw = t.m_Script if isinstance(t.m_Script, (bytes, bytearray)) else t.m_Script.encode("utf-8", "surrogateescape")
            out[t.m_Name] = parse_shapes(bytes(raw))
    return out


def game_mesh(env, name):
    """(vertices (n, 3), uv0 (n, 2)) of the Mesh called ``name``."""
    for o in env.objects:
        if o.type.name == "Mesh" and o.peek_name() == name:
            h = MeshHandler(o.read())
            h.process()
            return np.array(h.m_Vertices, dtype=float), np.array(h.m_UV0, dtype=float)
    raise KeyError("no mesh %s" % name)


def kabsch(P, Q):
    """Rotation R with R @ P[i] ~ Q[i] (rows are vectors)."""
    H = P.T @ Q
    U, _S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


def pmx_morphs(game_v, game_uv, pmx_info, shapes, neighbours=12, log=print):
    """{shape name: [(pmx vertex, (dx, dy, dz) in PMX units)]} for one mesh's shapes (first frame of each)."""
    pv = np.array([p for p, _w in pmx_info["verts"]], dtype=float)
    puv = np.array(pmx_info["uvs"], dtype=float)
    n = len(game_v)
    if len(pv) < n:
        raise ValueError("the PMX has fewer vertices (%d) than the game mesh (%d)" % (len(pv), n))
    # PMX v = 1 - Unity v; the eye/brow slots get new UVs from the exporter, so most (not all) must agree
    same = np.all(np.abs(puv[:n] - np.column_stack([game_uv[:, 0], 1.0 - game_uv[:, 1]])) < 1e-4, axis=1)
    if same.mean() < 0.8:
        raise ValueError("the PMX's first %d vertices are not the game mesh's (%.0f%% UVs agree)" % (n, 100 * same.mean()))
    torso = same & (np.abs(game_v[:, 0]) < 0.15) & (game_v[:, 2] > 0.6) & (game_v[:, 2] < 1.4)
    G = np.column_stack([game_v[torso], np.ones(torso.sum())])
    M, *_ = np.linalg.lstsq(G, pv[:n][torso], rcond=None)
    A, t = M[:3].T, M[3]
    resid = np.linalg.norm(game_v[torso] @ A.T + t - pv[:n][torso], axis=1)
    log("   mesh -> PMX: scale %.3f, offset %s, torso residual %.4f (p99 %.4f) PMX units on %d vertices"
        % (abs(np.linalg.det(A)) ** (1 / 3), np.round(t, 3), resid.mean(), np.percentile(resid, 99), torso.sum()))
    out = {}
    for name, frames in shapes.items():
        weight, deltas = frames[0]
        idx = np.array([i for i, _d in deltas])
        d = np.array([v for _i, v in deltas], dtype=float) * (100.0 / weight)
        offsets = []
        sq = (game_v ** 2).sum(1)
        for start in range(0, len(idx), 128):
            chunk = idx[start:start + 128]
            dist = sq[None, :] + sq[chunk][:, None] - 2.0 * game_v[chunk] @ game_v.T
            near = np.argpartition(dist, neighbours, axis=1)[:, :neighbours + 1]
            for row, vi in enumerate(chunk):
                nb = near[row]
                P = (game_v[nb] - game_v[vi]) @ A.T
                Q = pv[nb] - pv[vi]
                R = kabsch(P, Q) if np.linalg.norm(P) > 1e-9 else np.eye(3)
                offsets.append((int(vi), tuple(float(c) for c in R @ (A @ d[start + row]))))
        offsets = [o for o in offsets if max(abs(c) for c in o[1]) > 1e-6]
        out[name] = offsets
    return out


def add_morphs(pmx_path, morphs, out_path=None, log=print):
    """Append the morphs to the PMX (in place unless out_path).  A shape whose game name is already some morph's
    English name is skipped (a second run changes nothing).  Returns {shape name: PMX morph name}."""
    data = open(pmx_path, "rb").read()
    info = psm.parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    existing = [n.decode(enc) for n in info["morph_names"]]
    existing_e = [n.decode(enc) for n in info["morph_names_e"]]
    names = {}
    todo = []
    for shape in sorted(morphs):
        if shape in existing_e:
            names[shape] = existing[existing_e.index(shape)]
            log("   PMX already has %s as %s" % (shape, names[shape]))
        else:
            todo.append(shape)
    taken = list(existing) + [names[s] for s in names]
    short = pmx_bone_names.short_names(taken + todo)
    for k, shape in enumerate(todo):
        name = short.get(len(taken) + k, shape)
        names[shape] = name
        data, index, in_face = psm.append_vertex_morph(data, info, name, morphs[shape], comment=shape)
        info = psm.parse(data)
        log("   PMX: morph %s (%s, %d vertices) index %d%s" % (name, shape, len(morphs[shape]), index,
                                                                 "" if in_face else ", no 表情 frame"))
    if todo:
        tmp = (out_path or pmx_path) + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, out_path or pmx_path)
    return names


def clip_weights(clip_curves, names, n_frames=None):
    """MMD morph values (0..1) per frame from decode_roe_clip.blendshape_curves(): {PMX morph name: [w ...]}.
    ``names`` maps game shape names to PMX morph names; a curve's attribute is CRC32(shape name)."""
    by_crc = {zlib.crc32(shape.encode("utf-8")): morph for shape, morph in names.items()}
    out = {}
    for key, values in clip_curves.items():
        attr = int(key.split(":")[1])
        if attr in by_crc:
            out[by_crc[attr]] = [round(v / 100.0, 5) for v in values[:n_frames]]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shape_bundle")
    ap.add_argument("model_bundle", nargs="?")
    ap.add_argument("pmx", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    scenes = bundle_shapes(args.shape_bundle)
    if args.list or not args.pmx:
        for scene, meshes in scenes.items():
            for mesh, rec in meshes.items():
                for shape, frames in rec["shapes"].items():
                    print("%-4s %-16s %-24s %5d vertices" % (scene, mesh, shape, len(frames[0][1])))
        return
    env = UnityPy.load(args.model_bundle)
    info = psm.parse(open(args.pmx, "rb").read())
    for scene, meshes in scenes.items():
        for mesh, rec in meshes.items():
            gv, guv = game_mesh(env, mesh)
            morphs = pmx_morphs(gv, guv, info, rec["shapes"])
            add_morphs(args.pmx, morphs, args.out)


if __name__ == "__main__":
    main()
