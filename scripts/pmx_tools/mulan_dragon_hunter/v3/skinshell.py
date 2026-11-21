# Armour that grows out of the skin: take a body material's surface, keep the part where a scalar field is positive
# (the field's zero line is the plate's outline - drawn in body coordinates), refine the triangles near the outline so
# it stays crisp on a coarse body mesh, push it out along the normals and give it a rim.  The new vertices carry the
# skin's own weights, so the plate bends exactly like the body under it.
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
from geo import L, Part, unit  # noqa: E402


class Skin:
    """the vertices / faces of one material, in cm, with local indices"""

    def __init__(self, M, mat_names):
        if isinstance(mat_names, str):
            mat_names = [mat_names]
        mf = L.mat_faces(M)
        faces = []
        for name in mat_names:
            s, n = mf[L.mat_index(M, name)]
            faces += M.faces[s:s + n]
        flip = geo.winding_flip(M)
        vs = sorted({v for f in faces for v in f})
        loc = {v: i for i, v in enumerate(vs)}
        self.M = M
        self.global_index = vs
        self.P = np.array([M.vertices[v].co for v in vs], float) * geo.CM
        self.N = unit(np.array([M.vertices[v].normal for v in vs], float))
        self.UV = np.array([M.vertices[v].uv for v in vs], float)
        self.W = [L.oc.weights_of(L.pmx, M.vertices[v]) for v in vs]
        F = np.array([[loc[v] for v in f] for f in faces], int)
        self.F = F[:, [0, 2, 1]] if flip else F          # cross(b-a, c-a) points out
        self.bone_names = [b.name for b in M.bones]

    def bone_set(self, root_names):
        """indices of the named bones and all their descendants"""
        names = self.bone_names
        kids = {}
        for i, b in enumerate(self.M.bones):
            kids.setdefault(b.parent if b.parent is not None else -1, []).append(i)
        out, stack = set(), [names.index(n) for n in root_names if n in names]
        while stack:
            i = stack.pop()
            if i in out:
                continue
            out.add(i)
            stack += kids.get(i, [])
        return out

    def weight_sum(self, bones):
        return np.array([sum(x for b, x in w if b in bones) for w in self.W])

    def relaxed(self, centres, radius, iters=40):
        """a copy whose surface is relaxed (membrane smoothing) inside spheres around the given points - e.g. the
        nipples under a breastplate, so a plate grown from it has no bump.  Normals are recomputed there."""
        import copy
        out = copy.copy(self)
        P = self.P.copy()
        mask = np.zeros(len(P), bool)
        for c in centres:
            mask |= np.linalg.norm(P - np.asarray(c, float), axis=1) < radius
        nb = [[] for _ in range(len(P))]
        for a_, b_, c_ in self.F:
            nb[a_] += [b_, c_]
            nb[b_] += [a_, c_]
            nb[c_] += [a_, b_]
        idx = np.nonzero(mask)[0]
        nbs = [sorted(set(nb[i])) for i in idx]
        deg = max(len(n) for n in nbs)
        pad = np.full((len(idx), deg), -1, int)
        for k, n in enumerate(nbs):
            pad[k, :len(n)] = n
        wgt = (pad >= 0).astype(float)
        cnt = wgt.sum(1, keepdims=True)
        for _ in range(iters):
            P[idx] = (P[pad] * wgt[..., None]).sum(1) / cnt
        N = np.zeros_like(P)
        fn = np.cross(P[self.F[:, 1]] - P[self.F[:, 0]], P[self.F[:, 2]] - P[self.F[:, 0]])
        for k in range(3):
            np.add.at(N, self.F[:, k], fn)
        N = unit(N)
        out.P = P
        out.N = np.where(mask[:, None], N, self.N)
        return out


def sdf_polygon(pts, poly):
    """signed distance (cm) of 2D points to a closed polygon, POSITIVE INSIDE"""
    pts = np.asarray(pts, float)
    poly = np.asarray(poly, float)
    n = len(poly)
    d2 = np.full(len(pts), np.inf)
    inside = np.zeros(len(pts), bool)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ab = b - a
        t = np.clip(((pts - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
        proj = a + t[:, None] * ab
        d2 = np.minimum(d2, ((pts - proj) ** 2).sum(1))
        cond = (a[1] > pts[:, 1]) != (b[1] > pts[:, 1])
        xint = a[0] + (pts[:, 1] - a[1]) / np.where(abs(b[1] - a[1]) < 1e-12, 1e-12, (b[1] - a[1])) * (b[0] - a[0])
        inside ^= cond & (pts[:, 0] < xint)
    d = np.sqrt(d2)
    return np.where(inside, d, -d)


def mirror_poly(half, x0=0.0):
    """right half polyline (x >= x0, listed from the centre outwards and back to the centre) -> the closed symmetric
    polygon: the half followed by its mirror image in reverse"""
    half = [tuple(p) for p in half]
    left = [(2 * x0 - x, y) for x, y in reversed(half)]
    if abs(half[0][0] - x0) < 1e-9:
        left = left[:-1]
    if abs(half[-1][0] - x0) < 1e-9:
        left = left[1:]
    return half + left


class Work:
    """a refinable copy of (part of) the skin: positions, offset directions, parent edges for lazy weights"""

    def __init__(self, skin, face_mask=None, channels=None):
        self.skin = skin
        self.P = [p for p in skin.P]
        self.D = [n for n in skin.N]              # offset direction (interpolated linearly, not renormalised)
        self.C = {k: [float(x) for x in v] for k, v in (channels or {}).items()}     # per-vertex scalars
        self.parent = [None] * len(self.P)        # (a, b, t) for vertices made on an edge
        F = skin.F if face_mask is None else skin.F[face_mask]
        self.T = [tuple(int(x) for x in f) for f in F]
        self.mid = {}
        self._wcache = {}

    def arrays(self):
        return np.array(self.P), np.array(self.D), {k: np.array(v) for k, v in self.C.items()}

    def edge_point(self, a, b, t=0.5):
        key = (a, b) if a < b else (b, a)
        if t == 0.5 and key in self.mid:
            return self.mid[key]
        if a > b:
            a, b, t = b, a, 1 - t
        self.P.append(self.P[a] * (1 - t) + self.P[b] * t)
        self.D.append(self.D[a] * (1 - t) + self.D[b] * t)
        for vals in self.C.values():
            vals.append(vals[a] * (1 - t) + vals[b] * t)
        self.parent.append((a, b, t))
        v = len(self.P) - 1
        if t == 0.5:
            self.mid[key] = v
        return v

    def weights(self, v):
        if v in self._wcache:
            return self._wcache[v]
        par = self.parent[v]
        if par is None:
            w = {b: x for b, x in self.skin.W[v]}
        else:
            a, b, t = par
            w = {}
            for src, k in ((self.weights(a), 1 - t), (self.weights(b), t)):
                for bone, x in src.items():
                    w[bone] = w.get(bone, 0.0) + x * k
        self._wcache[v] = w
        return w

    def refine(self, select, h, levels=6):
        """split 1 -> 4 every triangle chosen by select(P, C, T) whose longest edge is over h"""
        for _ in range(levels):
            P, _D, C = self.arrays()
            T = np.array(self.T, int)
            if not len(T):
                return
            e = np.stack([np.linalg.norm(P[T[:, 0]] - P[T[:, 1]], axis=1), np.linalg.norm(P[T[:, 1]] - P[T[:, 2]], axis=1),
                          np.linalg.norm(P[T[:, 2]] - P[T[:, 0]], axis=1)], 1)
            pick = (e.max(1) > h) & select(P, C, T)
            if not pick.any():
                return
            out = [t for t, p in zip(self.T, pick) if not p]
            for (a, b, c), p in zip(self.T, pick):
                if not p:
                    continue
                ab, bc, ca = self.edge_point(a, b), self.edge_point(b, c), self.edge_point(c, a)
                out += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
            self.T = out


def shell(skin, field, offset, name="shell", uv=None, h_coarse=1.2, h_fine=0.35, face_mask=None, rim_to=None,
          rim_uv=None, sdf=True, channels=None, normal_from_geometry=False):
    """Build a Part from the skin where field > 0.
    field(P, C) -> (n,) values (cm-like, positive inside); offset(P, C) -> (n,) or a number, cm along the normal;
    uv(P, f, C) -> (n, 2) texture coordinates (default: (clip(f / 4), 0.5));
    channels: {name: per-skin-vertex array} carried (linearly) to the refined points and passed as C;
    rim_to: None (no rim) or the offset (cm) the rim strip goes down to (e.g. 0.0 = the skin);
    sdf: the field is a distance - triangles further than their own size from the outline are not refined."""
    wk = Work(skin, face_mask, channels)

    def near(P, C, T):
        f = field(P, C)
        ft = f[T]
        if sdf:
            size = np.stack([np.linalg.norm(P[T[:, 0]] - P[T[:, 1]], axis=1), np.linalg.norm(P[T[:, 1]] - P[T[:, 2]], axis=1),
                             np.linalg.norm(P[T[:, 2]] - P[T[:, 0]], axis=1)], 1).max(1)
            return (ft.max(1) > -size) & (ft.min(1) < size)
        return (ft.max(1) > 0) & (ft.min(1) < 0)

    def straddle(P, C, T):
        ft = field(P, C)[T]
        return (ft.max(1) > 0) & (ft.min(1) < 0)

    wk.refine(near, h_coarse, levels=5)
    wk.refine(straddle, h_fine, levels=5)
    P, D, C = wk.arrays()
    f = field(P, C)
    part = Part()
    vmap = {}
    cut_cache = {}
    fl = list(f)

    def cut(a, b):
        key = (a, b) if a < b else (b, a)
        if key in cut_cache:
            return cut_cache[key]
        fa, fb = fl[a], fl[b]
        t = float(np.clip(fa / (fa - fb), 1e-4, 1 - 1e-4))
        if abs(t - 0.5) < 1e-7:             # 0.5 would hand back a cached midpoint of the refinement
            t = 0.5 + 1e-6
        v = wk.edge_point(a, b, t)
        fl.append(0.0)
        cut_cache[key] = v
        return v

    tris, iso_edges = [], []
    for a, b, c in wk.T:
        ins = [fl[a] > 0, fl[b] > 0, fl[c] > 0]
        k = sum(ins)
        if k == 3:
            tris.append((a, b, c))
        elif k == 0:
            continue
        else:
            vs = [a, b, c]
            while not (ins[0] and not ins[2]) and not (k == 1 and ins[0] and not ins[1] and not ins[2]):
                vs = vs[1:] + vs[:1]
                ins = ins[1:] + ins[:1]
            if k == 1:                      # vs[0] inside
                p, q, r = vs
                pq, pr = cut(p, q), cut(p, r)
                tris.append((p, pq, pr))
                iso_edges.append((pq, pr, p))
            else:                           # vs[0], vs[1] inside, vs[2] outside
                p, q, r = vs
                qr, pr = cut(q, r), cut(p, r)
                tris.append((p, q, qr))
                tris.append((p, qr, pr))
                iso_edges.append((qr, pr, p))
    if not tris:
        return part
    P, D, C = wk.arrays()
    f = np.array(fl)
    used = sorted({v for t in tris for v in t})
    Pu, Du, fu = P[used], D[used], f[used]
    Cu = {k: v[used] for k, v in C.items()}
    off = offset(Pu, Cu) if callable(offset) else np.full(len(used), float(offset))
    pos = Pu + Du * off[:, None]
    uvs = uv(Pu, fu, Cu) if uv is not None else np.stack([np.clip(fu / 4.0, 0, 1), np.full(len(used), 0.5)], 1)
    nrm = unit(Du)
    for i, v in enumerate(used):
        vmap[v] = part.vert(pos[i], nrm[i], uvs[i], list(wk.weights(v).items()))
    for a, b, c in tris:
        part.tri(vmap[a], vmap[b], vmap[c])
    if normal_from_geometry:
        part.smooth_normals()
    if rim_to is not None and iso_edges:
        idx = {v: i for i, v in enumerate(used)}
        rim_n = {}
        for a, b, p in iso_edges:
            e = P[b] - P[a]
            mid = (P[a] + P[b]) / 2
            o = mid - P[p]
            nn = unit(D[a] + D[b])
            o = o - e * (float(o @ e) / max(float(e @ e), 1e-12))
            o = o - nn * float(o @ nn)
            o = unit(o)
            for v in (a, b):
                rim_n[v] = rim_n.get(v, 0) + o
        top, bot = {}, {}
        for v, o in rim_n.items():
            o = unit(o)
            i = idx[v]
            ruv = rim_uv if rim_uv is not None else (0.0, uvs[i][1])
            top[v] = part.vert(pos[i], o, ruv, list(wk.weights(v).items()))
            bot[v] = part.vert(Pu[i] + Du[i] * rim_to, o, ruv, list(wk.weights(v).items()))
        for a, b, p in iso_edges:
            # the shell triangle runs p -> a -> b (or its rotation) with the interior on p's side; the rim hangs
            # from edge a-b outwards: orient by the outward vector
            o = unit(rim_n[a] + rim_n[b])
            n_face = np.cross(part.P[top[b]] - part.P[top[a]], part.P[bot[a]] - part.P[top[a]])
            if float(n_face @ o) >= 0:
                part.quad(top[a], top[b], bot[b], bot[a])
            else:
                part.quad(top[b], top[a], bot[a], bot[b])
    return part


# ------------------------------------------------------------------ body coordinates --------------------------------

class Limb:
    """cylindrical coordinates around a bone segment A -> B: t (cm along, 0 at A), phi (degrees: 0 = front (-z),
    +90 = the limb's OUTER side, 180 = back, -90 = inner), r (cm from the axis)"""

    def __init__(self, A, B, outer_sign, front=(0.0, 0.0, -1.0)):
        self.A, self.B = np.asarray(A, float), np.asarray(B, float)
        self.axis = unit(self.B - self.A)
        self.length = float(np.linalg.norm(self.B - self.A))
        f = np.asarray(front, float)
        f = f - self.axis * float(f @ self.axis)
        self.front = unit(f)
        o = np.cross(self.axis, self.front)          # perpendicular to both
        if (o[0] * outer_sign) < 0:
            o = -o
        self.outer = unit(o)

    def coords(self, P):
        d = np.asarray(P, float) - self.A
        t = d @ self.axis
        rad = d - np.outer(t, self.axis)
        x, y = rad @ self.front, rad @ self.outer
        return t, np.degrees(np.arctan2(y, x)), np.hypot(x, y)


def ang_diff(a, b):
    """smallest signed difference a - b in degrees"""
    return (np.asarray(a) - b + 180.0) % 360.0 - 180.0
