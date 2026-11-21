# Mesh parts for a PMX, built in centimetres with numpy and committed as one new material each.
# A Part holds vertices (position cm, normal, uv, weights = [(bone index, weight), ...]) and triangles whose
# cross(b - a, c - a) points OUT of the surface; commit() stores them in the winding the file already uses.
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2"))
import pmxlib as L  # noqa: E402
from add_crystals import winding_flip  # noqa: E402

CM = L.UNIT_CM


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n < 1e-12, 1.0, n)


def frame(d, up=(0.0, 1.0, 0.0)):
    """orthonormal (side, up2, d): d = the given direction, up2 as close to `up` as possible, side = up2 x d"""
    d = unit(d)
    up = np.asarray(up, float)
    side = np.cross(up, d)
    if np.linalg.norm(side) < 1e-6:
        side = np.cross(np.array([1.0, 0, 0]), d)
    side = unit(side)
    return side, np.cross(d, side), d


def rot_axis(axis, deg):
    axis = unit(axis)
    a = np.radians(deg)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * (K @ K)


class Part:
    def __init__(self):
        self.P, self.N, self.UV, self.W, self.F = [], [], [], [], []

    def __len__(self):
        return len(self.F)

    def vert(self, p, n=(0.0, 1.0, 0.0), uv=(0.0, 0.0), w=None):
        self.P.append(np.asarray(p, float))
        self.N.append(np.asarray(n, float))
        self.UV.append((float(uv[0]), float(uv[1])))
        self.W.append(list(w) if w is not None else [])
        return len(self.P) - 1

    def tri(self, a, b, c):
        if a != b and b != c and a != c:
            self.F.append((a, b, c))

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

    def flat_tri(self, p0, p1, p2, uv0=(0, 0), uv1=(0, 0), uv2=(0, 0), w=None, out_hint=None):
        """three new vertices with the face normal; out_hint (a vector) flips the triangle to face along it"""
        p0, p1, p2 = (np.asarray(p, float) for p in (p0, p1, p2))
        n = np.cross(p1 - p0, p2 - p0)
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            return
        if out_hint is not None and np.dot(n, out_hint) < 0:
            p1, p2, uv1, uv2, n = p2, p1, uv2, uv1, -n
        n = n / ln
        a = self.vert(p0, n, uv0, w)
        b = self.vert(p1, n, uv1, w)
        c = self.vert(p2, n, uv2, w)
        self.F.append((a, b, c))

    def flat_quad(self, p0, p1, p2, p3, uv0=(0, 0), uv1=(0, 0), uv2=(0, 0), uv3=(0, 0), w=None, out_hint=None):
        self.flat_tri(p0, p1, p2, uv0, uv1, uv2, w, out_hint)
        self.flat_tri(p0, p2, p3, uv0, uv2, uv3, w, out_hint)

    def add(self, other, R=None, t=None):
        """append another part, optionally transformed: p -> R p + t"""
        k = len(self.P)
        R = np.eye(3) if R is None else np.asarray(R, float)
        t = np.zeros(3) if t is None else np.asarray(t, float)
        for p, n, uv, w in zip(other.P, other.N, other.UV, other.W):
            self.P.append(R @ p + t)
            self.N.append(R @ n)
            self.UV.append(uv)
            self.W.append(list(w))
        det = np.linalg.det(R)
        for a, b, c in other.F:
            self.F.append((a + k, b + k, c + k) if det > 0 else (a + k, c + k, b + k))
        return self

    def set_weight(self, w):
        self.W = [list(w) for _ in self.P]
        return self

    def set_uv_rect(self, u0, v0, u1, v1):
        """squeeze the current uvs (assumed 0..1) into a rectangle of an atlas"""
        self.UV = [(u0 + (u1 - u0) * u, v0 + (v1 - v0) * v) for u, v in self.UV]
        return self

    def arrays(self):
        return np.array(self.P, float).reshape(-1, 3), np.array(self.F, int).reshape(-1, 3)

    def smooth_normals(self):
        """area-weighted vertex normals from the faces (vertices shared by faces get averaged)"""
        P, F = self.arrays()
        N = np.zeros_like(P)
        fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        self.N = list(unit(N))
        return self

    def faceted(self):
        """a copy with every face on its own three vertices and the face normal (hard edges)"""
        out = Part()
        for a, b, c in self.F:
            out.flat_tri(self.P[a], self.P[b], self.P[c], self.UV[a], self.UV[b], self.UV[c])
            for v, src in zip(range(len(out.P) - 3, len(out.P)), (a, b, c)):
                out.W[v] = list(self.W[src])
        return out

    def mirrored(self, M):
        """the x-mirrored copy: winding flipped, weights moved to the bones of the other side (by name)"""
        names = [b.name for b in M.bones]
        index = {n: i for i, n in enumerate(names)}
        out = Part()
        for p, n, uv, w in zip(self.P, self.N, self.UV, self.W):
            out.P.append(np.array([-p[0], p[1], p[2]]))
            out.N.append(np.array([-n[0], n[1], n[2]]))
            out.UV.append(uv)
            out.W.append([(index.get(L.swap_lr(names[b]), b), x) for b, x in w])
        out.F = [(a, c, b) for a, b, c in self.F]
        return out

    def bbox(self):
        P = np.array(self.P)
        return P.min(0), P.max(0)

    def commit(self, M, name, tex=-1, flip=None, double=False, **mat):
        """append to the PMX as a new material; returns the material index"""
        if flip is None:
            flip = winding_flip(M)
        base = len(M.vertices)
        n_uv = M.header.additional_uvs
        for p, n, uv, w in zip(self.P, self.N, self.UV, self.W):
            v = L.pmx.Vertex()
            v.co = [float(x) for x in np.asarray(p) / CM]
            nn = unit(n)
            if not np.isfinite(nn).all() or np.linalg.norm(nn) < 0.5:      # a degenerate point (blade tips)
                nn = np.array([0.0, 1.0, 0.0])
            v.normal = [float(x) for x in nn]
            v.uv = [float(uv[0]), float(uv[1])]
            v.additional_uvs = [[0.0, 0.0, 0.0, 0.0]] * n_uv
            bw = L.pmx.BoneWeight()
            if not w:
                raise ValueError("vertex without weights in part " + name)
            L.oc.set_weights(L.pmx, bw, dict_sum(w))
            v.weight = bw
            v.edge_scale = 1.0
            M.vertices.append(v)
        faces = [(a + base, c + base, b + base) if flip else (a + base, b + base, c + base) for a, b, c in self.F]
        kw = dict(diffuse=(1, 1, 1, 1), specular=(0.3, 0.3, 0.3), shininess=10, ambient=(0.5, 0.5, 0.5), edge=False,
                  edge_color=(0, 0, 0, 1), edge_size=1.0, toon=0, comment="")
        kw.update(mat)
        mi = L.new_material(M, name, name, tex, faces, **kw)
        M.materials[mi].is_double_sided = bool(double)
        return mi


def dict_sum(pairs):
    d = {}
    for b, x in pairs:
        d[int(b)] = d.get(int(b), 0.0) + float(x)
    return d


def W1(bone):
    return [(int(bone), 1.0)]


def bone_index(M, name):
    return L.bone_index(M, name)


def bone_pos(M, name):
    return np.array(M.bones[L.bone_index(M, name)].location, float) * CM


def texture(M, path):
    return L.add_texture(M, os.path.abspath(path))


# ---------------------------------------------------------------- primitives ----------------------------------------

def sweep(path, sections, closed_section=True, cap_start=True, cap_end=True, w=None, v_range=(0.0, 1.0)):
    """Loft: `path` = list of (centre, side, up) frames (side / up = the section's local x / y axes in world space),
    `sections` = list (same length) of (k, 2) arrays of local section points, counter-clockwise seen from the path's
    END looking back to its START... the caller keeps the same k everywhere.  uv: u around the section, v along."""
    part = Part()
    k = len(sections[0])
    rings = []
    for i, ((c, sx, sy), sec) in enumerate(zip(path, sections)):
        v = v_range[0] + (v_range[1] - v_range[0]) * i / max(len(path) - 1, 1)
        ring = []
        for j, (x, y) in enumerate(sec):
            ring.append(part.vert(np.asarray(c) + np.asarray(sx) * x + np.asarray(sy) * y, (0, 1, 0), (j / k, v), w))
        if closed_section:
            x, y = sec[0]
            ring.append(part.vert(np.asarray(c) + np.asarray(sx) * x + np.asarray(sy) * y, (0, 1, 0), (1.0, v), w))
        rings.append(ring)
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for j in range(len(r0) - 1):
            part.quad(r0[j], r0[j + 1], r1[j + 1], r1[j])
    part.smooth_normals()
    if closed_section:                 # the seam vertices share position: average their normals
        for ring in rings:
            n = unit(part.N[ring[0]] + part.N[ring[-1]])
            part.N[ring[0]] = part.N[ring[-1]] = n
    for cap, ring, (c, sx, sy), sign in ((cap_start, rings[0], path[0], -1.0), (cap_end, rings[-1], path[-1], 1.0)):
        if not cap:
            continue
        axis = np.cross(sx, sy) * sign
        pts = [part.P[v] for v in ring[:k]]
        cen = np.mean(pts, 0)
        for j in range(k):
            part.flat_tri(cen, pts[j], pts[(j + 1) % k], (0.5, 0.5), (0.5, 0.5), (0.5, 0.5), w, out_hint=axis)
    _orient_outward(part)
    return part


def _orient_outward(part):
    """flip all faces if the closed surface's signed volume is negative"""
    P, F = part.arrays()
    if not len(F):
        return
    vol = np.einsum("ij,ij->i", P[F[:, 0]], np.cross(P[F[:, 1]], P[F[:, 2]])).sum()
    c = P.mean(0)
    vol -= np.einsum("j,ij->i", c, np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])).sum()
    if vol < 0:
        part.F = [(a, c2, b) for a, b, c2 in part.F]
        part.N = [-n for n in part.N]


def polygon_plate(outline, origin, ax_u, ax_v, thick, uv_fn=None, w=None, bevel=0.0, back=True):
    """A flat plate from a 2D outline (list of (u, v) in cm, counter-clockwise seen from the FRONT = +normal side,
    normal = ax_u x ax_v): front face (optionally with a bevelled rim that drops `bevel` cm over `bevel` cm of inset),
    rim and back face.  uv_fn(u, v) -> texture uv (default: outline bbox -> 0..1)."""
    outline = np.asarray(outline, float)
    origin, ax_u, ax_v = np.asarray(origin, float), unit(ax_u), unit(ax_v)
    nrm = unit(np.cross(ax_u, ax_v))
    lo, hi = outline.min(0), outline.max(0)
    if uv_fn is None:
        def uv_fn(u, v):
            return ((u - lo[0]) / max(hi[0] - lo[0], 1e-9), 1.0 - (v - lo[1]) / max(hi[1] - lo[1], 1e-9))
    part = Part()

    def P3(uv, h):
        return origin + ax_u * uv[0] + ax_v * uv[1] + nrm * h

    tris = triangulate(outline)
    n = len(outline)
    if bevel > 0:
        inner = inset_polygon(outline, bevel)
        top = thick / 2
        for a, b, c in triangulate(inner):
            part.flat_tri(P3(inner[a], top), P3(inner[b], top), P3(inner[c], top), uv_fn(*inner[a]), uv_fn(*inner[b]),
                          uv_fn(*inner[c]), w, out_hint=nrm)
        for i in range(n):
            j = (i + 1) % n
            part.flat_quad(P3(outline[i], top - bevel), P3(outline[j], top - bevel), P3(inner[j], top), P3(inner[i], top),
                           uv_fn(*outline[i]), uv_fn(*outline[j]), uv_fn(*inner[j]), uv_fn(*inner[i]), w,
                           out_hint=nrm + unit(_edge_out(outline, i)) @ np.array([ax_u, ax_v]) * 0.7)
        rim_top = top - bevel
    else:
        for a, b, c in tris:
            part.flat_tri(P3(outline[a], thick / 2), P3(outline[b], thick / 2), P3(outline[c], thick / 2),
                          uv_fn(*outline[a]), uv_fn(*outline[b]), uv_fn(*outline[c]), w, out_hint=nrm)
        rim_top = thick / 2
    for i in range(n):
        j = (i + 1) % n
        out2 = unit(_edge_out(outline, i))
        part.flat_quad(P3(outline[i], rim_top), P3(outline[j], rim_top), P3(outline[j], -thick / 2), P3(outline[i], -thick / 2),
                       uv_fn(*outline[i]), uv_fn(*outline[j]), uv_fn(*outline[j]), uv_fn(*outline[i]), w,
                       out_hint=ax_u * out2[0] + ax_v * out2[1])
    if back:
        for a, b, c in tris:
            part.flat_tri(P3(outline[a], -thick / 2), P3(outline[b], -thick / 2), P3(outline[c], -thick / 2),
                          uv_fn(*outline[a]), uv_fn(*outline[b]), uv_fn(*outline[c]), w, out_hint=-nrm)
    return part


def _edge_out(outline, i):
    """outward 2D normal of edge i -> i+1 of a counter-clockwise polygon"""
    a, b = outline[i], outline[(i + 1) % len(outline)]
    d = b - a
    return np.array([d[1], -d[0]])


def polygon_area(poly):
    poly = np.asarray(poly, float)
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def inset_polygon(poly, d):
    """move every vertex inwards by d along the bisector of its two edge normals (fine for mild, mostly convex shapes)"""
    poly = np.asarray(poly, float)
    n = len(poly)
    out = []
    for i in range(n):
        n0 = unit(_edge_out(poly, (i - 1) % n))
        n1 = unit(_edge_out(poly, i))
        b = n0 + n1
        lb = np.linalg.norm(b)
        if lb < 1e-6:
            b, lb = n0, 1.0
        b = b / lb
        cos_half = max(float(b @ n0), 0.35)
        out.append(poly[i] - b * (d / cos_half))
    return np.array(out)


def triangulate(poly):
    """ear clipping of a simple polygon (counter-clockwise or clockwise); returns index triples"""
    poly = np.asarray(poly, float)
    n = len(poly)
    idx = list(range(n))
    if polygon_area(poly) < 0:
        idx.reverse()
    tris = []

    def is_convex(a, b, c):
        return (poly[b][0] - poly[a][0]) * (poly[c][1] - poly[a][1]) - (poly[b][1] - poly[a][1]) * (poly[c][0] - poly[a][0]) > 1e-12

    def inside(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        d1, d2, d3 = s(p, poly[a], poly[b]), s(p, poly[b], poly[c]), s(p, poly[c], poly[a])
        neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (neg and pos)

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        done = False
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if not is_convex(a, b, c):
                continue
            if any(inside(poly[q], a, b, c) for q in idx if q not in (a, b, c)):
                continue
            tris.append((a, b, c))
            idx.pop(k)
            done = True
            break
        if not done:                      # degenerate: clip anything
            a, b, c = idx[0], idx[1], idx[2]
            tris.append((a, b, c))
            idx.pop(1)
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def gem(center, axis_long, axis_wide, length, width, depth, w=None, uv_rect=(0, 0, 1, 1), tip=0.38):
    """An elongated faceted gem lying on a surface: hexagonal girdle outline (pointed at both ends of axis_long), a
    table raised by `depth` along the normal = axis_long x axis_wide... (normal points out of the surface)."""
    al, aw = unit(axis_long), unit(axis_wide)
    nrm = unit(np.cross(aw, al))
    h, wd = length / 2, width / 2
    girdle = [(0, h), (-wd, h * tip), (-wd, -h * tip), (0, -h), (wd, -h * tip), (wd, h * tip)]      # (wide, long)
    table = [(0, h * 0.45), (-wd * 0.45, h * tip * 0.4), (-wd * 0.45, -h * tip * 0.4), (0, -h * 0.45),
             (wd * 0.45, -h * tip * 0.4), (wd * 0.45, h * tip * 0.4)]
    u0, v0, u1, v1 = uv_rect

    def P3(q, hh):
        return np.asarray(center, float) + aw * q[0] + al * q[1] + nrm * hh

    def uv(q):
        return (u0 + (u1 - u0) * (q[0] / wd * 0.5 + 0.5), v0 + (v1 - v0) * (0.5 - q[1] / h * 0.5))

    part = Part()
    n = 6
    for i in range(n):
        j = (i + 1) % n
        part.flat_quad(P3(girdle[i], 0), P3(girdle[j], 0), P3(table[j], depth), P3(table[i], depth), uv(girdle[i]),
                       uv(girdle[j]), uv(table[j]), uv(table[i]), w, out_hint=nrm + aw * (girdle[i][0] + girdle[j][0])
                       + al * (girdle[i][1] + girdle[j][1]) * 0.5)
    for i in range(1, n - 1):
        part.flat_tri(P3(table[0], depth), P3(table[i], depth), P3(table[i + 1], depth), uv(table[0]), uv(table[i]),
                      uv(table[i + 1]), w, out_hint=nrm)
    return part


def crystal(base, direction, length, radius, rng, sides=6, w=None, jitter=0.12, taper=0.72, uv_rect=(0, 0, 1, 1),
            squash=1.0, lean=0.0, sink=0.25):
    """A faceted crystal: prism with `sides` faces from the base (sunk `sink` x length below it) to a shoulder ring at
    `taper` x length, then a point.  uv: u = facet (each facet its own column), v = 0 at the tip .. 1 at the bottom."""
    side, up2, d = frame(direction, up=(0.3, 1.0, 0.2))
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False) + rng.uniform(0, 2 * np.pi)
    ang = ang + rng.uniform(-jitter, jitter, sides) * 2
    r0 = radius * rng.uniform(1 - jitter, 1 + jitter, sides)
    r1 = radius * rng.uniform(1 - jitter, 1 + jitter, sides) * rng.uniform(0.95, 1.2)
    lean_v = (side * rng.uniform(-1, 1) + up2 * rng.uniform(-1, 1)) * lean * radius
    base = np.asarray(base, float)

    def ring(r, z, off):
        return [base + off + d * z + (side * np.cos(a) + up2 * np.sin(a) * squash) * rr for a, rr in zip(ang, r)]

    bottom = base - d * (sink * length)
    ring0 = ring(r0, 0.0, 0.0)
    ring1 = ring(r1, taper * length, lean_v)
    tip = base + lean_v * 1.3 + d * length
    u0, v0, u1, v1 = uv_rect
    part = Part()
    zmin, zmax = -sink * length, length

    def uv(k, z, half=0.5):
        return (u0 + (u1 - u0) * ((k + half) / sides), v0 + (v1 - v0) * (1.0 - (z - zmin) / (zmax - zmin)))

    axis_c = base + d * (length * 0.4)
    for k in range(sides):
        k2 = (k + 1) % sides
        hint = (ring0[k] + ring0[k2]) / 2 - axis_c
        hint = hint - d * float(hint @ d)
        part.flat_tri(bottom, ring0[k], ring0[k2], uv(k, zmin), uv(k, 0, 0.1), uv(k, 0, 0.9), w, out_hint=hint - d)
        part.flat_quad(ring0[k], ring0[k2], ring1[k2], ring1[k], uv(k, 0, 0.1), uv(k, 0, 0.9), uv(k, taper * length, 0.9),
                       uv(k, taper * length, 0.1), w, out_hint=hint)
        part.flat_tri(ring1[k], ring1[k2], tip, uv(k, taper * length, 0.1), uv(k, taper * length, 0.9), uv(k, length), w,
                      out_hint=hint + d * 0.5)
    return part


def blade(points, widths, thicks, up_hint, w=None, uv_rect=(0, 0, 1, 1), ridge=0.0):
    """A blade swept along `points` (k, 3): diamond cross-section, `widths` across (in the plane holding up_hint) and
    `thicks` through.  The last point may have width 0 (a tip).  uv: u across the WIDTH (0 = one edge, 0.5 = the
    central ridge, 1 = the other edge) on both faces, v along the length (0 at the first point).
    ridge > 0 flattens the diamond into a hexagon (a flat central band of that fraction of the width)."""
    pts = np.asarray(points, float)
    n = len(pts)
    u0, v0, u1, v1 = uv_rect
    part = Part()
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)]) / max(seg.sum(), 1e-9)
    frames = []
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        side, up2, dd = frame(d, up=up_hint)
        frames.append((up2, side))          # width axis ~ up_hint, thickness axis = side
    rows = []
    for i in range(n):
        wa, ta = frames[i]
        hw, ht = widths[i] / 2, thicks[i] / 2
        c = pts[i]
        row = {"e0": c - wa * hw, "e1": c + wa * hw, "f": c + ta * ht, "b": c - ta * ht}
        if ridge > 0:
            row["f0"], row["f1"] = c + ta * ht - wa * hw * ridge, c + ta * ht + wa * hw * ridge
            row["b0"], row["b1"] = c - ta * ht - wa * hw * ridge, c - ta * ht + wa * hw * ridge
        rows.append(row)

    def uv(u, i):
        return (u0 + (u1 - u0) * u, v0 + (v1 - v0) * acc[i])

    for i in range(n - 1):
        a, b = rows[i], rows[i + 1]
        ta = frames[i][1]
        wa = frames[i][0]
        if ridge > 0:
            ur = 0.5 * ridge
            strips = [("e0", "f0", 0.0, 0.5 - ur, ta - wa), ("f0", "f1", 0.5 - ur, 0.5 + ur, ta), ("f1", "e1", 0.5 + ur, 1.0, ta + wa),
                      ("e1", "b1", 1.0, 0.5 + ur, -ta + wa), ("b1", "b0", 0.5 + ur, 0.5 - ur, -ta), ("b0", "e0", 0.5 - ur, 0.0, -ta - wa)]
        else:
            strips = [("e0", "f", 0.0, 0.5, ta - wa), ("f", "e1", 0.5, 1.0, ta + wa), ("e1", "b", 1.0, 0.5, -ta + wa),
                      ("b", "e0", 0.5, 0.0, -ta - wa)]
        for k0, k1, ua, ub, hint in strips:
            part.flat_quad(a[k0], a[k1], b[k1], b[k0], uv(ua, i), uv(ub, i), uv(ub, i + 1), uv(ua, i + 1), w, out_hint=hint)
    return part


def tube(points, radii, sides=8, w=None, uv_rect=(0, 0, 1, 1), cap=True, up_hint=(0, 1, 0)):
    """round rod along points with per-point radii (smooth shaded)"""
    pts = np.asarray(points, float)
    n = len(pts)
    path, secs = [], []
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        side, up2, dd = frame(d, up=up_hint)
        path.append((pts[i], side, up2))
        secs.append(np.stack([np.cos(ang) * radii[i], np.sin(ang) * radii[i]], 1))
    part = sweep(path, secs, True, cap, cap, w)
    part.set_uv_rect(*uv_rect)
    return part


def leaf_sheet(spine, side, out, hw_knots, thick, w_fn, n_len=10, n_wid=6, cup=0.12, end_fn=None, uv_rect=(0, 0, 1, 1),
               lift=0.0):
    """A leaf-shaped sheet with thickness (front + back + rim), for skirt petals and plates.
    spine: (k, 3) polyline root -> tip; side: unit vector across the width; out: the sheet's outward normal;
    hw_knots: [(s, half width cm), ...] along the length fraction s; cup: how much the middle bulges outwards (x half
    width); end_fn(u) -> the length fraction where the column at u in -1..1 ends (a W-notched or V-shaped end);
    w_fn(s) -> weights of a point at length fraction s; lift: the far end is raised `lift` cm along out (lames)."""
    spine = np.asarray(spine, float)
    side, out = unit(side), unit(out)
    seg = np.linalg.norm(np.diff(spine, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)]) / max(seg.sum(), 1e-9)
    ks, kv = zip(*hw_knots)
    u0, v0, u1, v1 = uv_rect

    def pos(s):
        return np.array([np.interp(s, acc, spine[:, k]) for k in range(3)])

    grid = {}
    front = Part()
    for i in range(n_len + 1):
        for j in range(n_wid + 1):
            u = -1 + 2 * j / n_wid
            s = (i / n_len) * (end_fn(u) if end_fn else 1.0)
            hw = float(np.interp(s, ks, kv))
            p = pos(s) + side * (u * hw) + out * (cup * hw * (1 - u * u) + lift * s)
            grid[i, j] = front.vert(p, out, (u0 + (u1 - u0) * (u + 1) / 2, v0 + (v1 - v0) * s), w_fn(s))
    for i in range(n_len):
        for j in range(n_wid):
            front.quad(grid[i, j], grid[i, j + 1], grid[i + 1, j + 1], grid[i + 1, j])
    front.smooth_normals()
    nmean = np.mean(front.N, 0)
    if float(nmean @ out) < 0:
        front.F = [(a, c, b) for a, b, c in front.F]
        front.N = [-n for n in front.N]
    part = Part()
    part.add(front)
    k = len(front.P)
    for p, n, uv, w in zip(front.P, front.N, front.UV, front.W):       # back surface
        part.P.append(p - n * thick)
        part.N.append(-n)
        part.UV.append(uv)
        part.W.append(list(w))
    for a, b, c in front.F:
        part.F.append((a + k, c + k, b + k))
    # rim
    loop = [grid[i, 0] for i in range(n_len + 1)] + [grid[n_len, j] for j in range(1, n_wid + 1)] + \
           [grid[i, n_wid] for i in range(n_len - 1, -1, -1)] + [grid[0, j] for j in range(n_wid - 1, 0, -1)]
    cen = np.mean(front.P, 0)
    for a, b in zip(loop, loop[1:] + loop[:1]):
        pa, pb = front.P[a], front.P[b]
        if np.linalg.norm(pa - pb) < 1e-6:
            continue
        n0 = len(part.P)
        pa2, pb2 = pa - front.N[a] * thick, pb - front.N[b] * thick
        part.flat_quad(pa, pb, pb2, pa2, front.UV[a], front.UV[b], front.UV[b], front.UV[a], None,
                       out_hint=(pa + pb) / 2 - cen)
        for v in range(n0, len(part.P)):
            q = part.P[v]
            da = min(np.linalg.norm(q - pa), np.linalg.norm(q - pa2))
            db = min(np.linalg.norm(q - pb), np.linalg.norm(q - pb2))
            part.W[v] = list(front.W[a if da <= db else b])
    return part


def warp(part, fn, facet=True):
    """move every vertex through fn(p) -> p'; normals are recomputed (per face for faceted parts)"""
    part.P = [np.asarray(fn(p), float) for p in part.P]
    if facet:
        for a, b, c in part.F:
            n = np.cross(part.P[b] - part.P[a], part.P[c] - part.P[a])
            ln = np.linalg.norm(n)
            if ln > 1e-12:
                part.N[a] = part.N[b] = part.N[c] = n / ln
    else:
        part.smooth_normals()
    return part
