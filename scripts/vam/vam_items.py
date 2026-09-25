"""Write VaM clothing / hair items (.vam + .vaj + .vab) directly, no in-game creator.

VaM lists an item as soon as ``<name>.vam`` sits under ``Custom/Clothing/<Female|Male>/`` or
``Custom/Hair/<Female|Male>/`` (loose or inside a .var).  The three files are:

* ``.vam`` -- JSON metadata: itemType, uid ("<creator>:<name>"), displayName, creatorName, tags.
* ``.vaj`` -- JSON: the component list (tells the loader which stores follow in the .vab) and
  the storables (wrap control, sim, item control, one material block per material group).
* ``.vab`` -- the binary DynamicStore, laid out exactly as VaM's Clothing Creator stores it:

    "DynamicStore" "1.0" "DAZMesh" "1.0"
    name, nodeId, sceneNodeId, geometryId                     (strings)
    int numVerts, Vector3[numVerts]                           (VaM space: metres, +Y up, +Z front)
    int numMaterials, string[numMaterials]
    int numPolys, {int material, int n(3|4), int[n]}[numPolys]        base polygons
    {int material, int n, int[n]}[numPolys]                           the same polygons on UV vertices
    int numUVVerts, Vector2[numUVVerts]                        first numVerts are the base vertices
    int numMapped, {int baseVert, int uvVert, int firstPoly}[numMapped]   seam copies (uvVert >= numVerts)
    "DAZSkinWrap" "1.0" "Normal"
    "DAZSkinWrapStore" "1.0" int count(=numUVVerts)
       {int closestTriangle, int v1, int v2, int v3, float f0, f1, f2, float n0, n1, n2}[count]
    {"MaterialOptions" "1.0" "+Material<name>" int n, int[n]}   one per DAZSkinWrapMaterialOptions component
    byte 0                                                     (no cloth-sim geometry follows)

  Wrap record: the vertex is v1 + N*f0 + T1*f1 + T2*f2 (+ N*surfaceOffset at run time) with N the
  outward unit face normal of skin triangle (v1, v2, v3), T1 = centroid - v1, T2 = N x T1; the
  normal n0..n2 is the vertex normal in the same frame.  closestTriangle numbers the skin's
  triangles the way Unity's sub-meshes do: polygons grouped by material (stable), quads split
  (0,1,2)(0,2,3).  All of this was checked against the 385 mesh items installed here
  (``tests/test_vam_items.py`` rewrites 224 of them byte for byte).
"""
import json
import os
import struct

import numpy as np

import vam_lib as vl


# ----------------------------------------------------------------------------- binary writer

class _Writer:
    def __init__(self):
        self.buf = bytearray()

    def string(self, text):
        raw = text.encode("utf-8")
        n = len(raw)
        while True:
            byte = n & 0x7F
            n >>= 7
            if n:
                self.buf.append(byte | 0x80)
            else:
                self.buf.append(byte)
                break
        self.buf += raw

    def int32(self, value):
        self.buf += struct.pack("<i", int(value))

    def byte(self, value):
        self.buf.append(int(value) & 0xFF)

    def raw(self, data):
        self.buf += data


def write_vab(mesh, wrap_records, groups, tail=b"\x00"):
    """Serialise a clothing/hair DAZMesh store.

    ``mesh`` is a dict with: name, ids (3 strings), verts (nv,3), materials (list), poly_mat,
    poly_len, poly_idx (flat), uv_poly_idx (flat), uvs (nuv,2), mapped (m,3 int: base, uv, poly).
    ``wrap_records`` is an (nuv, 10) array whose first four columns are ints and last six floats
    (build it with ``pack_records``).  ``groups`` is [(group name incl. "+Material", [mat idx])].
    """
    w = _Writer()
    for s in ("DynamicStore", "1.0", "DAZMesh", "1.0"):
        w.string(s)
    w.string(mesh["name"])
    for s in mesh["ids"]:
        w.string(s)
    verts = np.ascontiguousarray(mesh["verts"], dtype="<f4").reshape(-1, 3)
    w.int32(len(verts))
    w.raw(verts.tobytes())
    w.int32(len(mesh["materials"]))
    for m in mesh["materials"]:
        w.string(m)
    poly_len = np.asarray(mesh["poly_len"], dtype=np.int64)
    poly_mat = np.asarray(mesh["poly_mat"], dtype=np.int64)
    w.int32(len(poly_len))
    for flat in (mesh["poly_idx"], mesh["uv_poly_idx"]):
        flat = np.asarray(flat, dtype="<i4")
        # {material, n, idx[n]} per polygon, assembled with numpy for speed
        out = bytearray()
        cursor = 0
        header = np.empty(2, dtype="<i4")
        for mat, n in zip(poly_mat.tolist(), poly_len.tolist()):
            header[0], header[1] = mat, n
            out += header.tobytes()
            out += flat[cursor:cursor + n].tobytes()
            cursor += n
        w.raw(bytes(out))
    uvs = np.ascontiguousarray(mesh["uvs"], dtype="<f4").reshape(-1, 2)
    w.int32(len(uvs))
    w.raw(uvs.tobytes())
    mapped = np.ascontiguousarray(mesh["mapped"], dtype="<i4").reshape(-1, 3)
    w.int32(len(mapped))
    w.raw(mapped.tobytes())
    for s in ("DAZSkinWrap", "1.0", "Normal", "DAZSkinWrapStore", "1.0"):
        w.string(s)
    rec = np.ascontiguousarray(wrap_records)
    if rec.dtype.itemsize != 40:
        raise ValueError("wrap records must be 40-byte structs (see pack_records)")
    w.int32(len(rec))
    w.raw(rec.tobytes())
    for name, members in groups:
        w.string("MaterialOptions")
        w.string("1.0")
        w.string(name)
        w.int32(len(members))
        for m in members:
            w.int32(m)
    w.raw(tail)
    return bytes(w.buf)


def pack_records(tri, verts3, coeffs, normals):
    """(n,) tri index, (n,3) skin vertex ids, (n,3) position coeffs, (n,3) normal coeffs ->
    (n, 40-byte) little-endian records as VaM stores them."""
    n = len(tri)
    out = np.zeros(n, dtype=[("i", "<i4", 4), ("f", "<f4", 6)])
    out["i"][:, 0] = tri
    out["i"][:, 1:4] = verts3
    out["f"][:, 0:3] = coeffs
    out["f"][:, 3:6] = normals
    return out


# ----------------------------------------------------------------------------- full parse (round trip)

def parse_vab_full(data):
    """Every field of a clothing .vab as plain arrays (the inverse of ``write_vab``)."""
    r = vl._Reader(data)
    head = [r.string() for _ in range(4)]
    if head != ["DynamicStore", "1.0", "DAZMesh", "1.0"]:
        raise ValueError("not a DAZMesh store: %r" % head)
    name = r.string()
    ids = [r.string() for _ in range(3)]
    nv = r.int32()
    verts = r.floats(nv * 3).reshape(-1, 3).copy()
    nm = r.int32()
    materials = [r.string() for _ in range(nm)]
    npoly = r.int32()
    mats, lens, idx = vl._read_poly_list(r, npoly, nv)
    _uvm, _uvl, uv_idx = vl._read_poly_list(r, npoly, 1 << 30)
    nuv = r.int32()
    uvs = r.floats(nuv * 2).reshape(-1, 2).copy()
    nmap = r.int32()
    mapped = r.ints(nmap * 3).reshape(-1, 3).copy()
    tokens = [r.string() for _ in range(5)]
    if tokens != ["DAZSkinWrap", "1.0", "Normal", "DAZSkinWrapStore", "1.0"]:
        raise ValueError("unexpected wrap header %r" % tokens)
    count = r.int32()
    rec = np.frombuffer(data, dtype=[("i", "<i4", 4), ("f", "<f4", 6)], count=count, offset=r.pos).copy()
    r.pos += 40 * count
    groups = []
    while r.pos < len(data):
        save = r.pos
        try:
            token = r.string()
        except (IndexError, UnicodeDecodeError):
            r.pos = save
            break
        if token != "MaterialOptions":
            r.pos = save
            break
        r.string()
        gname = r.string()
        n = r.int32()
        groups.append((gname, [r.int32() for _ in range(n)]))
    mesh = {"name": name, "ids": ids, "verts": verts, "materials": materials, "poly_mat": mats,
            "poly_len": lens, "poly_idx": idx, "uv_poly_idx": uv_idx, "uvs": uvs, "mapped": mapped}
    return mesh, rec, groups, data[r.pos:]


# ----------------------------------------------------------------------------- UV vertices

def split_uv_vertices(num_verts, poly_len, poly_idx, loop_uv):
    """Base polygons + per-corner UVs -> VaM's UV vertex set.

    UV vertex i < num_verts is base vertex i with the UV of its first corner; every other UV a
    base vertex takes (a seam) becomes an extra UV vertex, recorded as (base, uv, first polygon).
    Returns (uvs (nuv,2), uv_poly_idx (flat), mapped (m,3), uv_to_base (nuv,)).
    """
    poly_idx = np.asarray(poly_idx, dtype=np.int64)
    loop_uv = np.asarray(loop_uv, dtype=np.float32)
    poly_of_loop = np.repeat(np.arange(len(poly_len)), poly_len)
    uvs = np.zeros((num_verts, 2), dtype=np.float32)
    seen = np.zeros(num_verts, dtype=bool)
    extra = {}
    extra_list = []
    uv_poly_idx = np.empty(len(poly_idx), dtype=np.int64)
    key_uv = np.round(loop_uv * 1e6).astype(np.int64)
    for li in range(len(poly_idx)):
        v = int(poly_idx[li])
        if not seen[v]:
            seen[v] = True
            uvs[v] = loop_uv[li]
            uv_poly_idx[li] = v
            continue
        if key_uv[li, 0] == int(round(uvs[v, 0] * 1e6)) and key_uv[li, 1] == int(round(uvs[v, 1] * 1e6)):
            uv_poly_idx[li] = v
            continue
        k = (v, int(key_uv[li, 0]), int(key_uv[li, 1]))
        u = extra.get(k)
        if u is None:
            u = num_verts + len(extra_list)
            extra[k] = u
            extra_list.append((v, u, int(poly_of_loop[li]), loop_uv[li]))
        uv_poly_idx[li] = u
    if extra_list:
        uvs = np.concatenate([uvs, np.array([e[3] for e in extra_list], dtype=np.float32)])
        mapped = np.array([(e[0], e[1], e[2]) for e in extra_list], dtype=np.int32)
    else:
        mapped = np.zeros((0, 3), dtype=np.int32)
    uv_to_base = np.concatenate([np.arange(num_verts), mapped[:, 0] if len(mapped) else np.zeros(0, dtype=np.int64)])
    return uvs, uv_poly_idx, mapped, uv_to_base


# ----------------------------------------------------------------------------- skin wrap

def vam_triangles(poly_len, poly_idx, poly_mat):
    """The skin's triangles in VaM's numbering (material-grouped, quads (0,1,2)(0,2,3))."""
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    order = np.argsort(np.asarray(poly_mat), kind="stable")
    tris = []
    for p in order.tolist():
        s, n = int(starts[p]), int(poly_len[p])
        q = poly_idx[s:s + n]
        tris.append((q[0], q[1], q[2]))
        if n == 4:
            tris.append((q[0], q[2], q[3]))
    return np.array(tris, dtype=np.int64)


def _point_triangle_distance2(p, a, b, c):
    """Squared distance from points p (n,3) to triangles (n,3 each), vectorised (Ericson)."""
    ab, ac, ap = b - a, c - a, p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = np.where(np.abs(va + vb + vc) < 1e-30, 1e-30, va + vb + vc)
    v = vb / denom
    w = vc / denom
    closest = a + ab * v[:, None] + ac * w[:, None]
    # regions
    m = (d1 <= 0) & (d2 <= 0)
    closest[m] = a[m]
    m = (d3 >= 0) & (d4 <= d3)
    closest[m] = b[m]
    m = (d6 >= 0) & (d5 <= d6)
    closest[m] = c[m]
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(np.abs(d1 - d3) < 1e-30, 1e-30, d1 - d3)
    closest[m] = (a + ab * t[:, None])[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(np.abs(d2 - d6) < 1e-30, 1e-30, d2 - d6)
    closest[m] = (a + ac * t[:, None])[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-30, 1e-30, (d4 - d3) + (d5 - d6))
    closest[m] = (b + (c - b) * t[:, None])[m]
    diff = p - closest
    return np.einsum("ij,ij->i", diff, diff)


class _Grid:
    """Uniform grid over the skin vertices + vertex -> triangle adjacency, for nearest queries."""

    def __init__(self, verts, tris, cell=0.03):
        self.verts = np.asarray(verts, dtype=np.float64)
        self.cell = cell
        keys = self._key(np.floor(self.verts / cell).astype(np.int64))
        self.order = np.argsort(keys, kind="stable")
        self.skeys = keys[self.order]
        # vertex -> triangles (CSR)
        flat = np.asarray(tris).ravel()
        tri_of = np.repeat(np.arange(len(tris)), 3)
        o = np.argsort(flat, kind="stable")
        self.vt_tri = tri_of[o]
        self.vt_start = np.searchsorted(flat[o], np.arange(len(self.verts) + 1))

    @staticmethod
    def _key(c):
        return ((c[..., 0] + 2048) * 4096 + (c[..., 1] + 2048)) * 4096 + (c[..., 2] + 2048)

    def near_vertices(self, pts, k=6):
        """k nearest skin vertices among the 27 cells around each point (-1 where none)."""
        base = np.floor(pts / self.cell).astype(np.int64)
        qi, vi_ = [], []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    key = self._key(base + np.array([dx, dy, dz]))
                    lo = np.searchsorted(self.skeys, key, "left")
                    hi = np.searchsorted(self.skeys, key, "right")
                    cnt = hi - lo
                    tot = int(cnt.sum())
                    if not tot:
                        continue
                    q = np.repeat(np.arange(len(pts)), cnt)
                    off = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
                    qi.append(q)
                    vi_.append(self.order[np.repeat(lo, cnt) + off])
        out = -np.ones((len(pts), k), dtype=np.int64)
        if not qi:
            return out
        q = np.concatenate(qi)
        v = np.concatenate(vi_)
        d = np.einsum("ij,ij->i", pts[q] - self.verts[v], pts[q] - self.verts[v])
        o = np.lexsort((d, q))
        q, v = q[o], v[o]
        first = np.searchsorted(q, np.arange(len(pts)))
        rank = np.arange(len(q)) - first[q]
        keep = rank < k
        out[q[keep], rank[keep]] = v[keep]
        return out


def closest_triangles(points, tris, body_verts, candidates=24, chunk=256, grid=None, max_grid_distance=0.025,
                      cell=0.03, pairs_per_block=20_000_000):
    """Index of the skin triangle nearest to each point.

    Grid path: the triangles around the 6 nearest skin vertices (within one ``cell``), exact
    point-triangle distance.  Points with no skin vertex that close fall back to a brute-force
    centroid pre-filter.  Queries run in blocks sized so that no block builds more than about
    ``pairs_per_block`` point-vertex pairs (a 2048 texture bake is ~3M points).
    """
    body = np.asarray(body_verts, dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(tris)
    if grid is None:
        grid = _Grid(body, tris, cell)
    out = np.full(len(pts), -1, dtype=np.int64)
    per_cell = len(grid.skeys) / max(1, len(np.unique(grid.skeys)))
    block = max(512, int(pairs_per_block / (27 * per_cell)))
    for s in range(0, len(pts), block):
        out[s:s + block] = _closest_triangles_grid(pts[s:s + block], tris, body, grid, max_grid_distance)
    rest = np.nonzero(out < 0)[0]
    if len(rest):
        out[rest] = _closest_triangles_brute(pts[rest], tris, body, candidates, chunk)
    return out


def _closest_triangles_grid(pts, tris, body, grid, max_grid_distance):
    """Grid pass of closest_triangles for one block of points (-1 = not decided here)."""
    near = grid.near_vertices(pts)
    out = np.full(len(pts), -1, dtype=np.int64)
    have = near[:, 0] >= 0
    if not have.any():
        return out
    rows = np.nonzero(have)[0]
    vq = near[rows]
    # candidate triangles: all triangles incident to the near vertices
    cq, ct = [], []
    for j in range(vq.shape[1]):
        v = vq[:, j]
        ok = v >= 0
        s = grid.vt_start[v[ok]]
        e = grid.vt_start[v[ok] + 1]
        cnt = e - s
        tot = int(cnt.sum())
        off = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        cq.append(np.repeat(rows[ok], cnt))
        ct.append(grid.vt_tri[np.repeat(s, cnt) + off])
    cq = np.concatenate(cq)
    ct = np.concatenate(ct)
    tri = tris[ct]
    d = _point_triangle_distance2(pts[cq], body[tri[:, 0]], body[tri[:, 1]], body[tri[:, 2]])
    o = np.lexsort((d, cq))
    cq, ct = cq[o], ct[o]
    first = np.unique(cq, return_index=True)[1]
    out[cq[first]] = ct[first]
    # the grid is exact near the skin (checked against brute force on 67k garment points:
    # no miss up to 20 mm with the 3 cm cell); loose parts further out go the slow way
    far = np.zeros(len(pts), dtype=bool)
    far[cq[first]] = d[o][first] > max_grid_distance ** 2
    out[far] = -1
    return out


def _closest_triangles_brute(points, tris, body_verts, candidates=24, chunk=256):
    body = np.asarray(body_verts, dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64)
    cent = body[tris].mean(axis=1)
    cent2 = np.einsum("ij,ij->i", cent, cent)
    out = np.empty(len(pts), dtype=np.int64)
    k = min(candidates, len(tris))
    for s in range(0, len(pts), chunk):
        block = pts[s:s + chunk]
        d = cent2[None, :] - 2.0 * block @ cent.T + np.einsum("ij,ij->i", block, block)[:, None]
        cand = np.argpartition(d, k - 1, axis=1)[:, :k]
        rows = np.repeat(np.arange(len(block)), k)
        flat = cand.ravel()
        tri = tris[flat]
        dist = _point_triangle_distance2(block[rows], body[tri[:, 0]], body[tri[:, 1]], body[tri[:, 2]])
        best = np.argmin(dist.reshape(len(block), k), axis=1)
        out[s:s + chunk] = cand[np.arange(len(block)), best]
    return out


def wrap_frames(tri_verts, body_verts, body_outward_normals):
    """(origin, N, T1, T2) of skin triangles (v1, v2, v3), N oriented outward."""
    body = np.asarray(body_verts, dtype=np.float64)
    a, b, c = body[tri_verts[:, 0]], body[tri_verts[:, 1]], body[tri_verts[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
    hint = np.asarray(body_outward_normals, dtype=np.float64)
    hint = hint[tri_verts[:, 0]] + hint[tri_verts[:, 1]] + hint[tri_verts[:, 2]]
    sign = np.sign(np.einsum("ij,ij->i", n, hint))
    sign[sign == 0] = 1.0
    n *= sign[:, None]
    t1 = (a + b + c) / 3.0 - a
    t2 = np.cross(n, t1)
    return a, n, t1, t2


def stable_triangles(tris, shapes, poly_len, poly_idx, min_cos=0.5):
    """Skin triangles whose orientation is unambiguous in every given shape of the skin.

    A wrap record's frame normal is the triangle's normal turned to agree with the skin's
    outward vertex normals -- on the body as it is when the item is rebuilt.  Where the two
    are nearly perpendicular (creases), or where a morph turned the triangle over (the rest-body
    shrink did, for 716 triangles of Fiona's hands, feet, ears and torso), the frame flips and
    the vertex lands on the other side of the skin, twice its offset away (up to 20 cm).  Only
    triangles within ``min_cos`` of their hint, on the same side in all shapes, are usable."""
    ok = np.ones(len(tris), dtype=bool)
    ref = None
    for shape in shapes:
        v = np.asarray(shape, dtype=np.float64)
        hint = vl.outward_normals(v.astype(np.float32), poly_len, poly_idx).astype(np.float64)
        a, b, c = v[tris[:, 0]], v[tris[:, 1]], v[tris[:, 2]]
        n = np.cross(b - a, c - a)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
        h = hint[tris].sum(axis=1)
        h /= np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-20)
        cos = np.einsum("ij,ij->i", n, h)
        ok &= np.abs(cos) >= min_cos
        if ref is None:
            ref = np.sign(cos)
        else:
            ok &= np.sign(cos) == ref
    return ok


def compute_wrap(points, normals, body_verts, body_poly_len, body_poly_idx, body_poly_mat,
                 body_outward_normals=None, anchor_verts=None, tri=None, usable=None):
    """DAZSkinWrapStore records for cloth vertices (VaM space) on a skin mesh.

    Returns (tri (n,), verts3 (n,3), coeffs (n,3), ncoeffs (n,3)); ``wrap_to_body`` in vam_lib
    rebuilds ``points`` from them exactly (surfaceOffset 0) on ``body_verts`` with that body's
    own outward normals -- leave ``body_outward_normals`` None unless they are exactly those.
    ``anchor_verts`` picks the skin triangle on a different shape of the same mesh than the one
    the offsets are measured on (or pass ``tri`` directly); ``usable`` (bool per triangle, see
    ``stable_triangles``) limits that choice.
    """
    body = np.asarray(body_verts, dtype=np.float64)
    if body_outward_normals is None:
        body_outward_normals = vl.outward_normals(body.astype(np.float32), body_poly_len, body_poly_idx)
    tris = vam_triangles(body_poly_len, body_poly_idx, body_poly_mat)
    if tri is None:
        pick = body if anchor_verts is None else anchor_verts
        if usable is None:
            tri = closest_triangles(points, tris, pick)
        else:
            sub = np.nonzero(usable)[0]
            tri = sub[closest_triangles(points, tris[sub], pick)]
    tv = tris[tri]
    a, n, t1, t2 = wrap_frames(tv, body, body_outward_normals)
    d = np.asarray(points, dtype=np.float64) - a
    t1l = np.maximum(np.einsum("ij,ij->i", t1, t1), 1e-30)
    t2l = np.maximum(np.einsum("ij,ij->i", t2, t2), 1e-30)
    coeffs = np.stack([np.einsum("ij,ij->i", d, n),
                       np.einsum("ij,ij->i", d, t1) / t1l,
                       np.einsum("ij,ij->i", d, t2) / t2l], axis=1)
    nrm = np.asarray(normals, dtype=np.float64)
    ncoeffs = np.stack([np.einsum("ij,ij->i", nrm, n),
                        np.einsum("ij,ij->i", nrm, t1) / t1l,
                        np.einsum("ij,ij->i", nrm, t2) / t2l], axis=1)
    return tri, tv, coeffs, ncoeffs


# ----------------------------------------------------------------------------- morphs

def write_morph(folder, name, deltas, group="Morph", region="Morph", body_vertices=21556, eps=1e-6,
                min_value=0, max_value=1, formulas=()):
    """A VaM morph as VaM stores it: ``<name>.vmi`` (JSON) + ``<name>.vmb`` (int32 count, then
    {int32 vertex, float dx, dy, dz} per moved vertex, VaM space).  Female body morphs index the
    21556 body vertices; the genital graft needs a separate ``female_genitalia`` morph.
    ``formulas``: bone adjustments at full strength, e.g. ``{"targetType": "BoneCenterX",
    "target": "lEye", "multiplier": "0.001"}`` (metres, VaM axes)."""
    d = np.asarray(deltas, dtype=np.float64)[:body_vertices]
    idx = np.nonzero(np.linalg.norm(d, axis=1) > eps)[0]
    os.makedirs(folder, exist_ok=True)
    rec = np.zeros(len(idx), dtype=[("i", "<i4"), ("d", "<f4", 3)])
    rec["i"] = idx
    rec["d"] = d[idx]
    base = os.path.join(folder, name)
    with open(base + ".vmb", "wb") as f:
        f.write(struct.pack("<i", len(idx)))
        f.write(rec.tobytes())
    vmi = {"id": name, "displayName": name, "group": group, "region": region, "min": str(min_value),
           "max": str(max_value), "numDeltas": str(len(idx)), "isPoseControl": "false",
           "formulas": list(formulas)}
    with open(base + ".vmi", "w", encoding="utf-8", newline="\n") as f:
        json.dump(vmi, f, ensure_ascii=False, indent=3)
    return {"vmi": base + ".vmi", "vmb": base + ".vmb", "deltas": int(len(idx))}


# ----------------------------------------------------------------------------- .vam / .vaj

MATERIAL_DEFAULTS = {
    "hideMaterial": "false", "renderQueue": "2400", "Specular Texture Offset": "0",
    "Specular Intensity": "1", "Gloss": "5", "Specular Fresnel": "0.5", "Gloss Texture Offset": "0",
    "Global Illumination Filter": "0", "Alpha Adjust": "0", "Diffuse Texture Offset": "0",
    "Diffuse Bumpiness": "1", "Specular Bumpiness": "1",
}
TEXTURE_SLOTS = ("customTexture_MainTex", "customTexture_SpecTex", "customTexture_GlossTex",
                 "customTexture_AlphaTex", "customTexture_BumpMap", "customTexture_DecalTex")


def _fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return ("%.7g" % value)
    return str(value)


def material_storable(storable_id, textures=None, **params):
    s = {"id": storable_id}
    for k, v in MATERIAL_DEFAULTS.items():
        s[k] = v
    for i in range(1, 7):
        for axis, val in (("TileX", "1"), ("TileY", "1"), ("OffsetX", "0"), ("OffsetY", "0")):
            s["customTexture%d%s" % (i, axis)] = val
    for slot in TEXTURE_SLOTS:
        s[slot] = ""
    s["simTexture"] = ""
    for slot, name in (textures or {}).items():
        s["customTexture_" + slot if not slot.startswith("customTexture_") else slot] = name
    s["Diffuse Color"] = {"h": "0", "s": "0", "v": "1"}
    s["Specular Color"] = {"h": "0", "s": "0", "v": "1"}
    s["Subsurface Color"] = {"h": "0", "s": "0", "v": "1"}
    for k, v in params.items():
        s[k] = v if isinstance(v, dict) else _fmt(v)
    return s


def item_uid(creator, display):
    return "%s:%s" % (creator.replace(" ", ""), display)


def write_item(out_dir, creator, display, item_type, mesh, records, groups, material_params,
               tags="", disable_anatomy=False, surface_offset=0.0003, thumbnail=None):
    """Write <out_dir>/<display>.{vam,vaj,vab} (+ jpg).  ``groups`` are (material name, [idx]);
    ``material_params`` maps material name -> kwargs for ``material_storable``."""
    os.makedirs(out_dir, exist_ok=True)
    uid = item_uid(creator, display)
    hair = item_type.startswith("Hair")
    prefix = uid + ("CustomScalp" if hair else "")
    vab_groups = [("+Material" + name, members) for name, members in groups]
    data = write_vab(mesh, records, vab_groups)
    base = os.path.join(out_dir, display)
    with open(base + ".vab", "wb") as f:
        f.write(data)
    vam = {"itemType": item_type, "uid": uid, "displayName": display, "creatorName": creator,
           "tags": tags, "isRealItem": "true"}
    storables = []
    if not hair:
        storables.append({"id": uid + "Style"})
    storables.append({"id": prefix + "WrapControl", "wrapToSmoothedVerts": "false",
                      "surfaceOffset": _fmt(float(surface_offset)), "additionalThicknessMultiplier": "0",
                      "smoothIterations": "1"})
    if hair:
        storables.append({"id": uid + "Sim"})
    else:
        storables.append({"id": uid + "Sim", "simEnabled": "false", "integrateEnabled": "true",
                          "collisionEnabled": "true", "allowDetach": "false", "collisionRadius": "0.01",
                          "drag": "0.06", "weight": "1", "distanceScale": "1", "stiffness": "0.5",
                          "compressionResistance": "0.5", "friction": "0.5", "staticMultiplier": "2",
                          "collisionPower": "0.5", "gravityMultiplier": "1", "iterations": "3",
                          "detachThreshold": "0.005", "jointStrength": "1", "force": ["0", "0", "0"]})
    storables.append({"id": uid + "ItemControl", "disableAnatomy": _fmt(bool(disable_anatomy)),
                      "isRealClothingItem": "true"})
    for name, _members in groups:
        storables.append(material_storable(prefix + "Material" + name, **(material_params.get(name) or {})))
    vaj = {"components": [{"type": "DAZMesh"}, {"type": "DAZSkinWrap"}]
           + [{"type": "DAZSkinWrapMaterialOptions"} for _ in groups],
           "storables": storables}
    with open(base + ".vam", "w", encoding="utf-8", newline="\n") as f:
        json.dump(vam, f, ensure_ascii=False, indent=3)
    with open(base + ".vaj", "w", encoding="utf-8", newline="\n") as f:
        json.dump(vaj, f, ensure_ascii=False, indent=3)
    if thumbnail is not None:
        thumbnail.convert("RGB").save(base + ".jpg", quality=90)
    return {"uid": uid, "vam": base + ".vam", "vab": base + ".vab", "bytes": len(data)}
