# -*- coding: utf-8 -*-
"""PMX Expression Transfer - the algorithm.  Copies the facial expressions (morphs) of one PMX model onto another PMX
model's face, whatever the two meshes are: different games, vertex counts, face shapes.  Runs inside Blender
(mathutils BVH for the nearest-point searches) or under a plain Python with numpy; only the ``pmx`` module of mmd_tools
is needed.  Shares its low-level helpers with pmx_outfit_transfer (same folder of add-ons).

How an expression finds its way onto the other face:
1. each face is read in its own frame: the eyeballs give the eye centres, left-right and up; the face looks along the
   third axis; lengths are measured in eye distances (IOD);
2. the features are found the same way on both faces, from the front (an orthographic z-buffer of the skin): the eye
   opening is where the eyeball shows in front of the skin (works for faces with eye holes and for closed sockets
   alike), the lid margins are its upper and lower edges; the lip line is the sharp valley between the lips (a slit or
   the mouth opening shows as a hole); plus the nose tip;
3. the donor's face is bent onto the target's face: a 2D warp of the features gives matching points all over the
   front of the face, and a 3D thin-plate spline through those pairs (features exact) carries every donor skin
   vertex over.  Each target skin vertex then takes the nearest point of the bent donor skin - upper-lid vertices only
   on the donor's upper lid, lower lip only on the lower lip, so nothing crosses an opening;
4. an expression's displacement at that donor point is carried over through the warp's local derivative (a wider
   mouth gets a wider smile, a taller eye opening a longer lid travel);
5. the lid margins are then corrected so the eye closes exactly as much as the donor's does (the upper-to-lower lid
   distance keeps the donor's ratio to the open eye, sample by sample along the lid), and lids never sink into the
   eyeball;
6. lashes, brows and other small meshes on the face ride on the nearest skin (offset turned with the skin), the teeth
   and tongue follow the jaw: one rigid motion fitted to the chin, the upper teeth stay.
The donor's vertex morphs, bone morphs (posed and baked) and group morphs (summed) can all be sources; every result is
written as a vertex morph with the donor's name and panel.
"""
import os
import re
import shutil
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _outfit_core():
    """pmx_outfit_transfer/core.py loaded by path (its package __init__ needs bpy, which a plain Python lacks)."""
    import importlib.util
    for folder in (os.path.dirname(HERE), r"E:\code\othercode\ripper_tpose\scripts\blender_addons"):
        p = os.path.join(folder, "pmx_outfit_transfer", "core.py")
        if os.path.isfile(p):
            spec = importlib.util.spec_from_file_location("pmx_outfit_transfer_core", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("pmx_outfit_transfer/core.py not found next to pmx_expression_transfer")


oc = _outfit_core()
UNIT_CM = oc.UNIT_CM

# -- the MMD expression names (panel: 1 brow, 2 eye, 3 mouth, 4 other) -----------------------------------------------
STANDARD = [
    ("まばたき", "blink", 2), ("笑い", "smile", 2), ("ウィンク", "wink", 2), ("ウィンク右", "wink_R", 2),
    ("ウィンク２", "wink2", 2), ("ｳｨﾝｸ２右", "wink2_R", 2), ("なごみ", "calm", 2), ("はぅ", "close><", 2),
    ("びっくり", "surprised", 2), ("じと目", "jito-eye", 2), ("キリッ", "kiri", 2), ("ｷﾘｯ", "kiri", 2),
    ("瞳小", "pupil_small", 2), ("下眼上", "lower_lid_up", 2), ("怒り目", "angry_eyes", 2), ("悲しむ", "sad_eyes", 2),
    ("真面目", "serious", 1), ("困る", "trouble", 1), ("にこり", "cheerful", 1), ("怒り", "anger", 1),
    ("上", "brow_up", 1), ("下", "brow_down", 1), ("前", "brow_front", 1),
    ("あ", "a", 3), ("い", "i", 3), ("う", "u", 3), ("え", "e", 3), ("お", "o", 3), ("あ２", "a2", 3), ("ん", "n", 3),
    ("ワ", "wa", 3), ("▲", "triangle", 3), ("∧", "mouth_∧", 3), ("□", "square", 3), ("ω", "omega", 3),
    ("ω□", "omega_open", 3), ("にっこり", "smile_mouth", 3), ("にやり", "grin", 3), ("にやり２", "grin2", 3),
    ("ぺろっ", "tongue_out", 3), ("てへぺろ", "tehepero", 3), ("てへぺろ２", "tehepero2", 3),
    ("口角上げ", "mouth_corner_up", 3), ("口角下げ", "mouth_corner_down", 3), ("口横広げ", "mouth_wide", 3),
    ("口横狭め", "mouth_narrow", 3), ("歯無し上", "no_upper_teeth", 3), ("歯無し下", "no_lower_teeth", 3),
]
STANDARD_NAMES = {n for n, _e, _c in STANDARD}
# names left unticked by default, and why (they move what this transfer does not carry: eyeballs, tongue, teeth)
NOT_BY_DEFAULT = {"瞳小": "动的是眼球", "ぺろっ": "要伸舌头（舌头只跟着下巴动）", "てへぺろ": "要伸舌头（舌头只跟着下巴动）",
                  "てへぺろ２": "要伸舌头（舌头只跟着下巴动）", "歯無し上": "动的是牙齿", "歯無し下": "动的是牙齿"}

EYE_BONES = ("左目", "右目", "両目")
EYEBALL_NAME = re.compile(r"eye(?!lash|brow|lid|[ _-]?overlay|shadow|line|liner|occ)|eyeball|ojos|iris|pupil|瞳|目玉|"
                          r"白目|黒目|ハイライト", re.IGNORECASE)
HAIR_NAME = re.compile(r"hair|髪|kami|bang|fringe|ponytail|braid|ahoge|头发|发", re.IGNORECASE)
MOUTH_NAME = re.compile(r"teeth|tooth|tongue|mouth|gum|口|歯|舌|牙", re.IGNORECASE)
NOT_FACE_NAME = re.compile(r"lash|brow|睫|眉|overlay|shadow|tear|涙|cheek_?blush|照れ", re.IGNORECASE)

EYE_K = 17          # samples along each lid margin (corner to corner)
LIP_K = 21          # samples along each lip margin


# -- small helpers ----------------------------------------------------------------------------------------------------
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def fit_sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    b = (P ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = x[:3]
    return c, float(np.sqrt(max(x[3] + c @ c, 1e-12)))


def quat_matrix(q):
    """PMX quaternion (x, y, z, w) -> 3x3 matrix acting on column vectors in PMX coordinates."""
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([[1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
                     [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
                     [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)]])


def kabsch(P, Q, w=None):
    """Rigid R, t (Q ~ R P + t), weighted."""
    w = np.ones(len(P)) if w is None else w
    w = w / (w.sum() + 1e-12)
    cp, cq = (P * w[:, None]).sum(0), (Q * w[:, None]).sum(0)
    H = ((P - cp) * w[:, None]).T @ (Q - cq)
    U, _S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, cq - R @ cp


def dilate(mask):
    out = mask.copy()
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def grow(region, allowed):
    """Grow ``region`` inside ``allowed`` until it stops (4-connected)."""
    region = region & allowed
    while True:
        nxt = dilate(region) & allowed
        if nxt.sum() == region.sum():
            return nxt
        region = nxt


def fill_holes(mask):
    border = np.zeros_like(mask)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    outside = grow(border & ~mask, ~mask)
    return ~outside


def rasterize(UV, Z, F, u0, v0, step, W, H):
    """Front-view z-buffer of triangles F (indices into UV / Z) on a W x H grid of pixel centres
    (u0 + (j + .5) step, v0 + (i + .5) step).  The larger Z wins (nearer to the viewer).
    Returns depth (H, W) (-inf where empty), triangle (H, W) (row of F, -1) and barycentrics (H, W, 3)."""
    depth = np.full((H, W), -np.inf)
    tri = np.full((H, W), -1, np.int64)
    bar = np.zeros((H, W, 3))
    if len(F) == 0:
        return depth, tri, bar
    P = UV[F]
    lo = np.floor((P.min(1) - [u0, v0]) / step - 0.5).astype(np.int64)
    hi = np.ceil((P.max(1) - [u0, v0]) / step - 0.5).astype(np.int64)
    keep = (hi[:, 0] >= 0) & (lo[:, 0] < W) & (hi[:, 1] >= 0) & (lo[:, 1] < H)
    Zf = Z[F]
    for t in np.flatnonzero(keep):
        j0, i0 = max(lo[t, 0], 0), max(lo[t, 1], 0)
        j1, i1 = min(hi[t, 0], W - 1), min(hi[t, 1], H - 1)
        if j1 < j0 or i1 < i0:
            continue
        a, b, c = P[t]
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-14:
            continue
        pu = u0 + (np.arange(j0, j1 + 1) + 0.5) * step
        pv = v0 + (np.arange(i0, i1 + 1) + 0.5) * step
        PU, PV = np.meshgrid(pu, pv)
        w0 = ((b[1] - c[1]) * (PU - c[0]) + (c[0] - b[0]) * (PV - c[1])) / den
        w1 = ((c[1] - a[1]) * (PU - c[0]) + (a[0] - c[0]) * (PV - c[1])) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        z = w0 * Zf[t, 0] + w1 * Zf[t, 1] + w2 * Zf[t, 2]
        cur = depth[i0:i1 + 1, j0:j1 + 1]
        upd = inside & (z > cur)
        if upd.any():
            cur[upd] = z[upd]
            tri[i0:i1 + 1, j0:j1 + 1][upd] = t
            bar[i0:i1 + 1, j0:j1 + 1][upd] = np.stack([w0, w1, w2], -1)[upd]
    return depth, tri, bar


class TPS:
    """Thin-plate spline X -> Y (rows), kernel r (3D) or r^2 log r (2D), per-point regularisation ``lam``."""

    def __init__(self, X, Y, lam):
        self.X = np.asarray(X, float)
        Y = np.asarray(Y, float)
        n, d = self.X.shape
        self.d = d
        K = self._k(np.linalg.norm(self.X[:, None] - self.X[None], axis=2))
        P = np.c_[np.ones(n), self.X]
        A = np.zeros((n + d + 1, n + d + 1))
        A[:n, :n] = K + np.diag(np.broadcast_to(lam, (n,)))
        A[:n, n:] = P
        A[n:, :n] = P.T
        b = np.zeros((n + d + 1, Y.shape[1]))
        b[:n] = Y
        try:
            sol = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            sol = np.linalg.lstsq(A, b, rcond=None)[0]
        self.W, self.a = sol[:n], sol[n:]

    def _k(self, r):
        if self.d == 3:
            return r
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(r > 1e-12, r * r * np.log(r), 0.0)

    def __call__(self, Q):
        Q = np.asarray(Q, float)
        out = np.empty((len(Q), self.W.shape[1]))
        for s in range(0, len(Q), 2000):
            q = Q[s:s + 2000]
            r = np.linalg.norm(q[:, None] - self.X[None], axis=2)
            out[s:s + 2000] = np.c_[np.ones(len(q)), q] @ self.a + self._k(r) @ self.W
        return out

    def jacobian(self, Q):
        """d f / d x at Q: (n, out, in).  3D kernel only."""
        Q = np.asarray(Q, float)
        out = np.empty((len(Q), self.W.shape[1], self.d))
        A = self.a[1:].T                                  # (out, in)
        for s in range(0, len(Q), 500):
            q = Q[s:s + 500]
            diff = q[:, None, :] - self.X[None]           # (n, N, in)
            r = np.linalg.norm(diff, axis=2)[..., None] + 1e-9
            out[s:s + 500] = A[None] + np.einsum("ik,nij->nkj", self.W, diff / r)
        return out


# -- one face ---------------------------------------------------------------------------------------------------------
class Face:
    """A model's face: which islands are skin, eyeballs, mouth interior, followers; the frame; the eye and lip
    margins; per-skin-vertex region labels (0 none, 1/2 left eye upper/lower lid, 3/4 right eye, 5/6 upper/lower
    lip)."""

    def __init__(self, pmx, model, log=print, skin=None, eyes=None, followers=None, mouth=None):
        self.pmx, self.m, self.log = pmx, model, log
        self.co = np.array([v.co for v in model.vertices], float)
        self.mf = oc.material_faces(model)
        self.mat_names = [mt.name for mt in model.materials]
        self.bone_names = [b.name for b in model.bones]
        self.override = {"skin": skin, "eyes": eyes, "followers": followers, "mouth": mouth}
        self._weights()
        self._islands()
        self._eyeballs()
        self._frame()
        self._roles()
        self._skin_arrays()
        self.eyes = [self._eye_margin(0), self._eye_margin(1)]
        self.lips = self._lip_margin()
        self._labels()
        self._mouth_pieces()

    # -- weights / bones ----------------------------------------------------------------------------------------------
    def _weights(self):
        m = self.m
        parent = [b.parent if b.parent is not None else -1 for b in m.bones]
        self.parent = parent
        idx = {n: i for i, n in enumerate(self.bone_names)}
        head = idx.get("頭")

        def subtree(root):
            if root is None:
                return set()
            kids = defaultdict(list)
            for i, p in enumerate(parent):
                if p is not None and p >= 0:
                    kids[p].append(i)
            out, st = set(), [root]
            while st:
                i = st.pop()
                out.add(i)
                st += kids[i]
            return out
        self.head_bones = subtree(head) if head is not None else set(range(len(m.bones)))
        eye_roots = [idx[n] for n in EYE_BONES if n in idx]
        self.eye_bones = set()
        for r in eye_roots:
            self.eye_bones |= subtree(r)
        for i, n in enumerate(self.bone_names):
            if re.search(r"eye(?!lash|brow|lid)", n, re.IGNORECASE) and not re.search(r"lid|lash|brow", n, re.I):
                self.eye_bones.add(i)
        # bones carried by physics (dynamic rigid bodies) and everything below them
        phys = {r.bone for r in m.rigids if r.mode in (1, 2) and r.bone is not None and r.bone >= 0}
        self.physics_bones = set()
        for b in phys:
            self.physics_bones |= subtree(b)
        self.bone_pos = {n: np.array(m.bones[i].location, float) for i, n in enumerate(self.bone_names)}
        # every vertex's (up to 4) bones and weights as arrays, for fast shares
        nb = len(m.bones)
        Wb = np.zeros((len(self.co), 4), np.int64)
        Ww = np.zeros((len(self.co), 4))
        for v, vert in enumerate(m.vertices):
            for k, (b, w) in enumerate(oc.weights_of(self.pmx, vert)[:4]):
                Wb[v, k] = b if 0 <= b < nb else 0
                Ww[v, k] = w
        self.Wb, self.Ww, self.nb = Wb, Ww, nb

    def _vertex_share(self, verts, bones):
        if not len(verts):
            return 0.0
        mask = np.zeros(self.nb + 1, bool)
        mask[[b for b in bones if 0 <= b < self.nb]] = True
        verts = np.asarray(verts, np.int64)
        w = self.Ww[verts]
        tot = w.sum()
        return float((w * mask[self.Wb[verts]]).sum() / tot) if tot > 0 else 0.0

    # -- islands (welded inside each material) --------------------------------------------------------------------------
    def _islands(self):
        self.islands = []                     # dicts: mat, faces (rows of model.faces), verts
        for mi, fl in enumerate(self.mf):
            if not fl:
                continue
            key, canon = {}, {}
            for f in fl:
                for v in self.m.faces[f]:
                    if v not in canon:
                        canon[v] = key.setdefault(tuple(np.round(self.co[v], 4)), v)
            parent = {}

            def find(x):
                while parent.setdefault(x, x) != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for f in fl:
                a, b, c = (canon[v] for v in self.m.faces[f])
                ra = find(a)
                parent[find(b)] = ra
                parent[find(c)] = ra
            groups = defaultdict(list)
            for f in fl:
                groups[find(canon[self.m.faces[f][0]])].append(f)
            for faces in groups.values():
                verts = np.unique(np.array([self.m.faces[f] for f in faces], np.int64))
                self.islands.append({"mat": mi, "faces": faces, "verts": verts})

    # -- eyes, frame ------------------------------------------------------------------------------------------------------
    def _eyeballs(self):
        names = self.override["eyes"]
        cand = []
        for k, isl in enumerate(self.islands):
            name = self.mat_names[isl["mat"]]
            if names is not None:
                if name in names:
                    cand.append(k)
                continue
            if NOT_FACE_NAME.search(name):
                continue
            share = self._vertex_share(isl["verts"][:: max(1, len(isl["verts"]) // 200)], self.eye_bones) \
                if self.eye_bones else 0.0
            if share > 0.5 or (EYEBALL_NAME.search(name) and not re.search(r"lash|brow|overlay", name, re.I)):
                cand.append(k)
        if not cand:
            raise RuntimeError("no eyeballs found (materials weighted to 左目 / 右目 or named eye / iris)")
        pts = np.concatenate([self.co[self.islands[k]["verts"]] for k in cand])
        head = self.bone_pos.get("頭", pts.mean(0))
        mid_x = head[0]
        sides = []
        for sgn in (1, -1):                   # model's left (+x) first
            ks = [k for k in cand if (self.co[self.islands[k]["verts"]][:, 0].mean() - mid_x) * sgn > 0]
            if not ks:
                raise RuntimeError("eyeballs found only on one side")
            P = np.concatenate([self.co[self.islands[k]["verts"]] for k in ks])
            c, r = fit_sphere(P)
            bone = self.bone_pos.get("左目" if sgn > 0 else "右目")
            if not (0.02 < r < 0.6) and bone is not None:
                c, r = bone, 0.18
            sides.append({"islands": ks, "centre": c, "radius": r})
        self.eyeball = sides
        self.eyeball_islands = set(cand)

    def _frame(self):
        cl, cr = self.eyeball[0]["centre"], self.eyeball[1]["centre"]
        x = cl - cr
        self.iod = float(np.linalg.norm(x))
        x /= self.iod
        y = np.array([0.0, 1.0, 0.0]) - x * x[1]
        y /= np.linalg.norm(y)
        f = np.cross(y, x)
        self.o = (cl + cr) / 2
        # forward must point out of the face: the eyes sit in front of the head bone (PMX faces -z when there is none)
        head = self.bone_pos.get("頭")
        ahead = (self.o - head) @ f if head is not None else -f[2]
        if ahead < 0:
            f = -f
        self.B = np.stack([x, y, f])           # rows: lateral (model's left), up, forward

    def norm(self, P):
        return (np.asarray(P) - self.o) @ self.B.T / self.iod

    # -- roles ----------------------------------------------------------------------------------------------------------
    def _roles(self):
        isl = self.islands
        Q = self.norm(self.co)
        info = []
        for k, it in enumerate(isl):
            q = Q[it["verts"]]
            name = self.mat_names[it["mat"]]
            in_box = ((np.abs(q[:, 0]) < 1.25) & (q[:, 1] > -2.3) & (q[:, 1] < 1.3) & (q[:, 2] > -1.2)).mean()
            sample = it["verts"][:: max(1, len(it["verts"]) // 150)]
            head = self._vertex_share(sample, self.head_bones - self.physics_bones)
            phys = self._vertex_share(sample, self.physics_bones)
            info.append({"name": name, "in_box": in_box, "head": head, "phys": phys, "q": q})
        self.info = info
        skin_names = self.override["skin"]
        cand = [k for k in range(len(isl)) if k not in self.eyeball_islands and info[k]["in_box"] > 0.2 and
                info[k]["head"] > 0.5 and not HAIR_NAME.search(info[k]["name"])]
        if skin_names is not None:
            skin = [k for k in range(len(isl)) if info[k]["name"] in skin_names and k not in self.eyeball_islands]
        else:
            # vote: the island seen first from the front at cheeks, nose, upper lip, chin
            probes = np.array([[0.0, -0.55], [0.45, -0.5], [-0.45, -0.5], [0.0, -0.85], [0.3, -1.15],
                               [-0.3, -1.15], [0.0, -1.5], [0.55, -0.85], [-0.55, -0.85], [0.0, 0.3]])
            F, owner = [], []
            for k in cand:
                if NOT_FACE_NAME.search(info[k]["name"]):
                    continue
                F += [self.m.faces[f] for f in isl[k]["faces"]]
                owner += [k] * len(isl[k]["faces"])
            F = np.array(F, np.int64)
            owner = np.array(owner)
            votes = Counter()
            if len(F):
                step = 0.01
                for pu, pv in probes:
                    d, t, _b = rasterize(Q[:, :2], Q[:, 2], F, pu - 0.02, pv - 0.02, step, 4, 4)
                    if (t >= 0).any():
                        votes[int(owner[t[t >= 0][0]])] += 1
            if not votes:
                raise RuntimeError("no face skin found in front of the eyes / mouth")
            top = votes.most_common(1)[0][0]
            skin = [k for k, n in votes.items() if n >= 2 and isl[k]["mat"] == isl[top]["mat"]] or [top]
        self.skin_islands = skin
        skin_set = set(skin)
        # skin surface for the distance tests below
        Fs = np.array([self.m.faces[f] for k in skin for f in isl[k]["faces"]], np.int64)
        self.mouth_islands, self.follower_islands = [], []
        todo = []
        for k in range(len(isl)):
            if k in skin_set or k in self.eyeball_islands:
                continue
            name = info[k]["name"]
            if self.override["mouth"] is not None or self.override["followers"] is not None:
                if self.override["mouth"] and name in self.override["mouth"]:
                    self.mouth_islands.append(k)
                elif self.override["followers"] and name in self.override["followers"]:
                    self.follower_islands.append(k)
                continue
            if info[k]["head"] < 0.5 or info[k]["in_box"] < 0.3 or HAIR_NAME.search(name):
                continue
            todo.append(k)
        if todo:
            # distance to the skin of a sample of every candidate island, in one search
            samples = [isl[k]["verts"][:: max(1, len(isl[k]["verts"]) // 12)] for k in todo]
            owner = np.concatenate([[i] * len(s) for i, s in enumerate(samples)])
            allv = np.concatenate(samples)
            _f, pts, _b = oc.NearestOnMesh(self.co, Fs).query(self.co[allv])
            close = np.linalg.norm(pts - self.co[allv], axis=1) / self.iod < 0.12
            frac = np.bincount(owner, close.astype(float), len(todo)) / np.bincount(owner, minlength=len(todo))
            for i, k in enumerate(todo):
                name = info[k]["name"]
                q = info[k]["q"]
                in_mouth = ((np.abs(q[:, 0]) < 0.75) & (q[:, 1] > -1.5) & (q[:, 1] < -0.55)).mean()
                if in_mouth > 0.8 and (MOUTH_NAME.search(name) or self._behind_skin(samples[i], Fs)):
                    self.mouth_islands.append(k)
                elif frac[i] > 0.5:
                    self.follower_islands.append(k)
        self.log("face: skin %s, eyeballs %s, mouth %s, followers %s" % (
            self._names(skin), self._names(self.eyeball_islands), self._names(self.mouth_islands),
            self._names(self.follower_islands)))

    def _names(self, ks):
        c = Counter(self.mat_names[self.islands[k]["mat"]] for k in ks)
        return ", ".join("%s%s" % (n, "" if c[n] == 1 else " x%d" % c[n]) for n in c) or "-"

    def _behind_skin(self, verts, Fs):
        """Most of these vertices are hidden behind the skin seen from the front."""
        Q = self.norm(self.co)
        q = Q[verts]
        u0, v0 = q[:, 0].min() - 0.01, q[:, 1].min() - 0.01
        step = 0.01
        W = int((q[:, 0].max() - u0) / step) + 2
        H = int((q[:, 1].max() - v0) / step) + 2
        d, _t, _b = rasterize(Q[:, :2], Q[:, 2], Fs, u0, v0, step, W, H)
        j = np.clip(((q[:, 0] - u0) / step).astype(int), 0, W - 1)
        i = np.clip(((q[:, 1] - v0) / step).astype(int), 0, H - 1)
        return float((d[i, j] > q[:, 2]).mean()) > 0.6

    # -- skin arrays ----------------------------------------------------------------------------------------------------
    def _skin_arrays(self):
        faces = [f for k in self.skin_islands for f in self.islands[k]["faces"]]
        self.skin_F = np.array([self.m.faces[f] for f in faces], np.int64)        # global vertex indices
        self.skin_V = np.unique(self.skin_F)
        self.Q = self.norm(self.co)
        # welded vertex of each skin vertex (UV-seam twins share one)
        key, canon = {}, np.arange(len(self.co))
        for v in self.skin_V:
            canon[v] = key.setdefault(tuple(np.round(self.co[v], 4)), v)
        self.canon = canon

    def raster(self, F, u0, v0, step, W, H, co=None):
        Q = self.Q if co is None else self.norm(co)
        return rasterize(Q[:, :2], Q[:, 2], F, u0, v0, step, W, H)

    def point(self, F, t, b, co=None):
        """3D point(s) of rows t of F at barycentrics b."""
        co = self.co if co is None else co
        return (co[F[t]] * b[..., None]).sum(-2)

    # -- eye margins ------------------------------------------------------------------------------------------------------
    def _eye_margin(self, side):
        eb = self.eyeball[side]
        cq = self.norm(eb["centre"][None])[0]
        step = 1.0 / 250
        u0, v0 = cq[0] - 0.55, cq[1] - 0.35
        W, H = int(1.1 / step), int(0.7 / step)
        Ds, Ts, Bs = self.raster(self.skin_F, u0, v0, step, W, H)
        Fe = np.array([self.m.faces[f] for k in eb["islands"] for f in self.islands[k]["faces"]], np.int64)
        De, _Te, _Be = self.raster(Fe, u0, v0, step, W, H)
        vis = np.isfinite(De) & (De > Ds + 1e-4)
        ci, cj = int((cq[1] - v0) / step), int((cq[0] - u0) / step)
        if not vis[ci, cj]:
            ii, jj = np.nonzero(vis)
            if not len(ii):
                raise RuntimeError("eye %s: the eyeball is nowhere visible from the front" % "LR"[side])
            k = np.argmin((ii - ci) ** 2 + (jj - cj) ** 2)
            ci, cj = ii[k], jj[k]
        seed = np.zeros_like(vis)
        seed[ci, cj] = True
        mask = fill_holes(grow(seed, vis))
        cols = np.flatnonzero(mask.any(0))
        us = u0 + (cols + 0.5) * step
        tops, bots = [], []
        up_pts, lo_pts = [], []
        for j in cols:
            rows = np.flatnonzero(mask[:, j])
            top, bot = rows.max(), rows.min()
            tops.append(v0 + (top + 0.5) * step)
            bots.append(v0 + (bot + 0.5) * step)
            up_pts.append(self._skin_hit(Ts, Bs, range(top + 1, min(top + 12, H)), j))
            lo_pts.append(self._skin_hit(Ts, Bs, range(bot - 1, max(bot - 12, -1), -1), j))
        inner_left = side == 1                   # right eye: the inner corner is on its +u side
        order = np.argsort(us)
        if inner_left:
            order = order[::-1]
        us, tops, bots = us[order], np.array(tops)[order], np.array(bots)[order]
        up_pts = [up_pts[i] for i in order]
        lo_pts = [lo_pts[i] for i in order]
        s = (us - us[0]) / (us[-1] - us[0])
        out = {"side": side, "mask": mask, "window": (u0, v0, step), "u": us, "top": tops, "bot": bots, "s_cols": s,
               "width": abs(us[-1] - us[0])}
        for name, pts in (("upper", up_pts), ("lower", lo_pts)):
            out[name] = self._resample(s, pts, EYE_K)
        h = np.linalg.norm(out["upper"]["pts"] - out["lower"]["pts"], axis=1)
        out["h"] = h
        out["height"] = float(h.max())
        return out

    def _skin_hit(self, Ts, Bs, rows, j):
        for i in rows:
            if 0 <= i < Ts.shape[0] and Ts[i, j] >= 0:
                return (int(Ts[i, j]), Bs[i, j].copy())
        return None

    def _resample(self, s, hits, K):
        """Samples at s = 0 .. 1 (K of them) from per-column skin hits (nearest column with a hit)."""
        ok = np.array([h is not None for h in hits])
        if ok.sum() < 3:
            raise RuntimeError("margin not found")
        s_ok = s[ok]
        hits = [h for h in hits if h is not None]
        sk = np.linspace(0, 1, K)
        tri, bar = [], []
        for x in sk:
            i = int(np.argmin(np.abs(s_ok - x)))
            tri.append(hits[i][0])
            bar.append(hits[i][1])
        tri, bar = np.array(tri), np.array(bar)
        return {"s": sk, "tri": tri, "bary": bar, "pts": self.point(self.skin_F, tri, bar)}

    # -- lip margins ------------------------------------------------------------------------------------------------------
    def _lip_margin(self):
        # nose tip: the nearest skin point to the viewer on the centre line below the eyes
        step = 1.0 / 200
        d, t, b = self.raster(self.skin_F, -0.1, -1.0, step, int(0.2 / step), int(0.8 / step))
        if not np.isfinite(d).any():
            raise RuntimeError("no skin below the eyes")
        i, j = np.unravel_index(np.argmax(np.where(np.isfinite(d), d, -np.inf)), d.shape)
        self.nose = {"tri": int(t[i, j]), "bary": b[i, j].copy(), "uv": (-0.1 + (j + .5) * step, -1.0 + (i + .5) * step)}
        self.nose["pts"] = self.point(self.skin_F, np.array([self.nose["tri"]]), self.nose["bary"][None])[0]
        nv = self.nose["uv"][1]
        step = 1.0 / 300
        u0, v0 = -0.7, nv - 1.0
        W, H = int(1.4 / step), int(0.88 / step)
        D, T, Bb = self.raster(self.skin_F, u0, v0, step, W, H)
        # a hole (slit, open mouth) counts as 0.05 IOD deeper than the deepest skin around it
        floor = np.nanmin(np.where(np.isfinite(D), D, np.nan)) if np.isfinite(D).any() else 0.0
        Dv = np.where(np.isfinite(D), D, floor - 0.05)
        jc = int((0.0 - u0) / step)
        w = int(0.05 / step)

        def contrast(col, i):
            up = col[i + 1:i + 1 + w]
            dn = col[max(i - w, 0):i]
            if not len(up) or not len(dn):
                return -1.0
            return min(up.max(), dn.max()) - col[i]
        col = Dv[:, jc]
        rows = range(w, H - int(0.12 / step))           # not right under the nose
        cs = np.array([contrast(col, i) for i in rows])
        ic = list(rows)[int(np.argmax(cs))]
        c_ref = max(cs.max(), 1e-6)
        stop = max(0.15 * min(c_ref, 0.05), 0.004)        # the valley has faded out: a mouth corner
        line = {jc: ic}
        for direction in (1, -1):
            i_prev, weak, j = ic, 0, jc + direction
            while 0 <= j < W:
                lo_, hi_ = max(i_prev - 3, w), min(i_prev + 4, H - w)
                cand = range(lo_, hi_)
                cc = np.array([contrast(Dv[:, j], i) for i in cand])
                k = int(np.argmax(cc))
                if cc[k] < stop:
                    weak += 1
                    if weak >= 3:
                        break
                else:
                    weak = 0
                i_prev = list(cand)[k]
                line[j] = i_prev
                j += direction
            for _ in range(min(weak, 2)):               # drop the weak tail
                line.pop(j - direction * (_ + 1), None)
        cols = np.array(sorted(line))
        us = u0 + (cols + 0.5) * step
        ups, los, vline = [], [], []
        for j in cols:
            i = line[j]
            vline.append(v0 + (i + 0.5) * step)
            ups.append(self._skin_hit(T, Bb, range(i + 1, min(i + 15, H)), j))
            los.append(self._skin_hit(T, Bb, range(i - 1, max(i - 15, -1), -1), j))
        s = (us - us[0]) / (us[-1] - us[0])            # right corner (-u) -> left corner (+u)
        out = {"u": us, "v": np.array(vline), "s_cols": s, "width": float(us[-1] - us[0]),
               "window": (u0, v0, step)}
        out["upper"] = self._resample(s, ups, LIP_K)
        out["lower"] = self._resample(s, los, LIP_K)
        out["centre_v"] = float(np.interp(0.0, us, out["v"]))
        return out

    # -- region labels ----------------------------------------------------------------------------------------------------
    def _labels(self):
        """Upper or lower lid / lip by the distance ALONG THE SKIN to the upper and to the lower margin (an inner lip
        that curls deep into the mouth reaches below the lip line seen from the front, but along the skin it is
        still nearer to its own margin)."""
        lab = np.zeros(len(self.co), np.int64)
        adj = self._adjacency()
        for side, e in enumerate(self.eyes):
            du = self._geodesic(adj, e["upper"], 0.3)
            dl = self._geodesic(adj, e["lower"], 0.3)
            self._assign(lab, du, dl, 1 + 2 * side, 2 + 2 * side)
        du = self._geodesic(adj, self.lips["upper"], 0.45)
        dl = self._geodesic(adj, self.lips["lower"], 0.45)
        self._assign(lab, du, dl, 5, 6)
        V = self.skin_V
        lab[V] = lab[self.canon[V]]
        self.labels = lab

    def _adjacency(self):
        Fc = self.canon[self.skin_F]
        adj = defaultdict(dict)
        for a, b, c in Fc:
            for x, y in ((a, b), (b, c), (c, a)):
                if x != y:
                    w = float(np.linalg.norm(self.co[x] - self.co[y]))
                    adj[x][y] = w
                    adj[y][x] = w
        return adj

    def _geodesic(self, adj, margin, limit):
        """Distance along the welded skin from a margin's inner samples (corners left out), up to limit IOD."""
        import heapq
        limit *= self.iod
        heap = []
        tri, pts = margin["tri"][1:-1], margin["pts"][1:-1]
        for t, p in zip(tri, pts):
            for v in self.canon[self.skin_F[t]]:
                heap.append((float(np.linalg.norm(self.co[v] - p)), int(v)))
        heapq.heapify(heap)
        dist = {}
        while heap:
            d, v = heapq.heappop(heap)
            if v in dist:
                continue
            if d > limit:
                break
            dist[v] = d
            for u, w in adj[v].items():
                if u not in dist:
                    heapq.heappush(heap, (d + w, u))
        return dist

    @staticmethod
    def _assign(lab, du, dl, up, low):
        for v in set(du) | set(dl):
            if lab[v]:
                continue
            a, b = du.get(v, np.inf), dl.get(v, np.inf)
            lab[v] = up if a <= b else low

    # -- mouth interior: which pieces ride the jaw -----------------------------------------------------------------------
    def _mouth_pieces(self):
        """Pieces as the exporter left them (shared vertex indices, not welded): teeth rows, tongue, gums, walls.
        Above the lip line: upper teeth / palate (still); below or around it: the jaw; spanning: blended by height."""
        mv = np.unique(np.concatenate([self.islands[k]["verts"] for k in self.mouth_islands])) \
            if self.mouth_islands else np.zeros(0, np.int64)
        self.mouth_v = mv
        self.mouth_w = np.zeros(len(mv))
        self.mouth_kind = Counter()
        jaw = []
        if not len(mv):
            self.jaw_ref_v = np.zeros(0, np.int64)
            return
        q = self.Q[mv]
        vl = np.interp(q[:, 0], self.lips["u"], self.lips["v"])
        pos = {v: i for i, v in enumerate(mv)}
        faces = [f for k in self.mouth_islands for f in self.islands[k]["faces"]]
        for piece in oc.islands(self.m.faces, faces):
            iv = np.array([pos[v] for v in np.unique(np.array([self.m.faces[f] for f in piece]))])
            rel = q[iv, 1] - vl[iv]
            if rel.min() > -0.05:
                self.mouth_w[iv] = 0.0
                self.mouth_kind["upper"] += 1
            elif rel.mean() < 0.05:
                self.mouth_w[iv] = 1.0
                self.mouth_kind["jaw"] += 1
                jaw.append(mv[iv])
            else:
                self.mouth_w[iv] = smoothstep((-rel + 0.05) / 0.1)
                self.mouth_kind["blend"] += 1
        self.jaw_ref_v = np.concatenate(jaw) if jaw else np.zeros(0, np.int64)


# -- the donor's expressions as per-vertex offsets ---------------------------------------------------------------------
def morph_kind(mo):
    offs = mo.offsets
    if not offs:
        return "empty"
    o = offs[0]
    if hasattr(o, "offset_type"):
        return "material"
    if hasattr(o, "morph"):
        return "group"
    if hasattr(o, "location_offset"):
        return "bone"
    if hasattr(o, "offset") and len(o.offset) == 3:
        return "vertex"
    return "uv"


def morph_offsets(pmx, model, co, mi, depth=0):
    """Per-vertex offsets (n, 3) of morph mi (vertex, bone posed with linear skinning, group summed)."""
    mo = model.morphs[mi]
    kind = morph_kind(mo)
    D = np.zeros_like(co)
    if kind == "vertex":
        for o in mo.offsets:
            D[o.index] += o.offset
    elif kind == "bone":
        D = bone_morph_offsets(pmx, model, co, {o.index: (np.array(o.location_offset, float),
                                                          quat_matrix(o.rotation_offset)) for o in mo.offsets})
    elif kind == "group" and depth < 4:
        for o in mo.offsets:
            if 0 <= o.morph < len(model.morphs) and o.morph != mi:
                D += o.factor * morph_offsets(pmx, model, co, o.morph, depth + 1)
    return D


def bone_morph_offsets(pmx, model, co, local):
    """Vertex offsets of a pose {bone: (translation, rotation)} - forward kinematics + linear blend skinning."""
    n = len(model.bones)
    head = np.array([b.location for b in model.bones], float)
    parent = [b.parent if b.parent is not None else -1 for b in model.bones]
    R = [None] * n
    t = [None] * n
    order = []
    seen = set()

    def visit(i):
        if i in seen:
            return
        p = parent[i]
        if 0 <= p < n and p != i:
            visit(p)
        seen.add(i)
        order.append(i)
    for i in range(n):
        visit(i)
    for i in order:
        tr, rot = local.get(i, (np.zeros(3), np.eye(3)))
        # local: x -> rot (x - h) + h + tr ; world = parent's world after it
        Rl, tl = rot, head[i] + tr - rot @ head[i]
        p = parent[i]
        if 0 <= p < n and R[p] is not None:
            R[i], t[i] = R[p] @ Rl, R[p] @ tl + t[p]
        else:
            R[i], t[i] = Rl, tl
    moved = {i for i in range(n) if not (np.allclose(R[i], np.eye(3)) and np.allclose(t[i], 0))}
    D = np.zeros_like(co)
    if not moved:
        return D
    for v, vert in enumerate(model.vertices):
        ws = oc.weights_of(pmx, vert)
        if not any(b in moved for b, _w in ws):
            continue
        p = co[v]
        acc = np.zeros(3)
        tot = 0.0
        for b, w in ws:
            acc += w * (R[b] @ p + t[b])
            tot += w
        if tot > 0:
            D[v] = acc / tot - p
    return D


# -- the transfer -------------------------------------------------------------------------------------------------------
class Correspondence:
    """Donor face bent onto the target face; per target skin vertex: donor triangle, barycentrics, warp derivative."""

    def __init__(self, donor, target, log=print):
        self.d, self.t, self.log = donor, target, log
        self._pairs()
        self._warp()
        self._match()

    def _features(self, face):
        """2D (u, v) and 3D points of the features, in a fixed order on every face."""
        uv, pts = [], []
        for e in face.eyes:
            for name in ("upper", "lower"):
                P = e[name]["pts"] if name == "upper" else e[name]["pts"][1:-1]     # corners once
                pts.append(P)
                uv.append(face.norm(P)[:, :2])
        for name in ("upper", "lower"):
            P = face.lips[name]["pts"] if name == "upper" else face.lips[name]["pts"][1:-1]
            pts.append(P)
            uv.append(face.norm(P)[:, :2])
        pts.append(face.nose["pts"][None])
        uv.append(face.norm(face.nose["pts"][None])[:, :2])
        return np.concatenate(uv), np.concatenate(pts)

    def _front(self, face, step=1.0 / 100):
        u0, v0 = -0.95, -1.85
        W, H = int(1.9 / step), int(2.75 / step)
        D, T, B = face.raster(face.skin_F, u0, v0, step, W, H)
        nrm = oc.face_frames(face.Q, face.skin_F)[:, 2]
        return {"D": D, "T": T, "B": B, "u0": u0, "v0": v0, "step": step, "W": W, "H": H, "n": nrm}

    def _pairs(self):
        d, t = self.d, self.t
        fuv_d, fp_d = self._features(d)
        fuv_t, fp_t = self._features(t)
        warp2 = TPS(fuv_d, fuv_t, 1e-6)
        fd, ft = self._front(d), self._front(t)
        X, Y, lam = [d.norm(fp_d)], [t.norm(fp_t)], [np.full(len(fp_d), 1e-6)]
        gs = 8
        ii, jj = np.meshgrid(np.arange(0, fd["H"], gs), np.arange(0, fd["W"], gs), indexing="ij")
        ii, jj = ii.ravel(), jj.ravel()
        ok = fd["T"][ii, jj] >= 0
        ii, jj = ii[ok], jj[ok]
        tri = fd["T"][ii, jj]
        ok = np.abs(fd["n"][tri] @ np.array([0, 0, 1.0])) > 0.35
        ii, jj, tri = ii[ok], jj[ok], tri[ok]
        uv = np.c_[fd["u0"] + (jj + .5) * fd["step"], fd["v0"] + (ii + .5) * fd["step"]]
        # keep away from the features (the lid / lip margins carry those) and out of the eye openings
        dist = np.min(np.linalg.norm(uv[:, None] - fuv_d[None], axis=2), axis=1)
        keep = dist > 0.05
        for e in d.eyes:
            u0, v0, st = e["window"]
            j = ((uv[:, 0] - u0) / st).astype(int)
            i = ((uv[:, 1] - v0) / st).astype(int)
            inn = (i >= 0) & (i < e["mask"].shape[0]) & (j >= 0) & (j < e["mask"].shape[1])
            keep[inn] &= ~e["mask"][i[inn], j[inn]]
        uv, ii, jj, tri = uv[keep], ii[keep], jj[keep], tri[keep]
        fd["n"], ft["n"] = np.abs(fd["n"]), np.abs(ft["n"])      # winding differs between exporters
        uv_t = warp2(uv)
        jt = ((uv_t[:, 0] - ft["u0"]) / ft["step"]).astype(int)
        it = ((uv_t[:, 1] - ft["v0"]) / ft["step"]).astype(int)
        ok = (jt >= 0) & (jt < ft["W"]) & (it >= 0) & (it < ft["H"])
        ok[ok] &= ft["T"][it[ok], jt[ok]] >= 0
        tri_t = np.where(ok, ft["T"][np.clip(it, 0, ft["H"] - 1), np.clip(jt, 0, ft["W"] - 1)], -1)
        ok &= tri_t >= 0
        ok[ok] &= ft["n"][tri_t[ok]] @ np.array([0, 0, 1.0]) > 0.35
        Pd = d.point(d.skin_F, tri[ok], fd["B"][ii[ok], jj[ok]])
        Pt = t.point(t.skin_F, tri_t[ok], ft["B"][it[ok], jt[ok]])
        X.append(d.norm(Pd))
        Y.append(t.norm(Pt))
        lam.append(np.full(ok.sum(), 2e-3))
        self.X, self.Y, self.lam = np.concatenate(X), np.concatenate(Y), np.concatenate(lam)
        self.n_features = len(fp_d)
        self.log("alignment: %d feature points, %d surface pairs" % (len(fp_d), int(ok.sum())))

    def _warp(self):
        d, t = self.d, self.t
        self.tps = TPS(self.X, self.Y, self.lam)
        Qd = d.Q[d.skin_V]
        self.warped = np.zeros_like(d.Q)
        self.warped[d.skin_V] = self.tps(Qd)
        res = np.linalg.norm(self.tps(self.X) - self.Y, axis=1)
        self.log("warp: feature residual max %.2f mm, surface pairs median %.2f mm" % (
            res[:self.n_features].max() * t.iod * UNIT_CM * 10, np.median(res[self.n_features:]) * t.iod * UNIT_CM * 10))

    def _match(self):
        d, t = self.d, self.t
        Fd = d.skin_F
        lab_d = d.labels[Fd]                              # (m, 3)
        Vt = t.skin_V
        lt = t.labels[Vt]
        self.tri = np.full(len(t.co), -1)
        self.bar = np.zeros((len(t.co), 3))
        self.dist = np.full(len(t.co), np.inf)
        for L in np.unique(lt):
            sel = Vt[lt == L]
            if L == 0:
                fsel = np.arange(len(Fd))
            else:
                fsel = np.flatnonzero((lab_d == L).any(1))
                if len(fsel) < 4:
                    fsel = np.arange(len(Fd))
            near = oc.NearestOnMesh(self.warped, Fd[fsel])
            f, p, b = near.query(t.Q[sel])
            self.tri[sel] = fsel[f]
            self.bar[sel] = b
            self.dist[sel] = np.linalg.norm(p - t.Q[sel], axis=1)
        pd = (d.Q[Fd[self.tri[Vt]]] * self.bar[Vt][..., None]).sum(1)
        J = self.tps.jacobian(pd)                         # normalised donor -> normalised target
        # world: D_t = (iod_t / iod_d) B_t^T J B_d D_d
        self.M = np.zeros((len(t.co), 3, 3))
        self.M[Vt] = (t.iod / d.iod) * np.einsum("ab,nbc,cd->nad", t.B.T, J, d.B)
        det = np.linalg.det(J)
        bad = det <= 0.05
        if bad.any():
            Rg = (t.iod / d.iod) * t.B.T @ d.B
            self.M[Vt[bad]] = Rg
        self.fade = np.ones(len(t.co))
        self.fade[Vt] = 1.0 - smoothstep((self.dist[Vt] - 0.04) / 0.08)
        self.log("match: %d target skin vertices, %.0f%% within 0.5 mm of the bent donor skin, %d far (faded)" % (
            len(Vt), 100 * (self.dist[Vt] * t.iod * UNIT_CM * 10 < 0.5).mean(), int((self.fade[Vt] < 0.5).sum())))

    def jaw_motion(self, Dd):
        """The donor's jaw (its lower teeth / tongue pieces) moved by offsets Dd, carried through the warp onto the
        target as one rigid motion (R, t) - or None when the donor has no such pieces or they do not move."""
        d, t = self.d, self.t
        jv = d.jaw_ref_v
        if len(jv) < 6 or np.linalg.norm(Dd[jv], axis=1).max() < 0.1 / UNIT_CM / 10:
            return None
        P = d.co[jv]
        Rd, td = kabsch(P, P + Dd[jv])
        # as a turn about the teeth's centre plus the centre's move: the turn keeps its angle and axis in the face
        # frame, the centre and its move are carried over by the face frames and the eye distance (the warp is only
        # good on the skin, not deep in the head)
        G = t.B.T @ d.B
        s = t.iod / d.iod
        g = P.mean(0)
        move = Rd @ g + td - g
        gt = t.o + s * G @ (g - d.o)
        Rt = G @ Rd @ G.T
        return Rt, gt + s * G @ move - Rt @ gt

    def carry(self, Dd):
        """Donor per-vertex offsets (world) -> target skin offsets (world)."""
        t = self.t
        Vt = t.skin_V
        Fd = self.d.skin_F
        dd = (Dd[Fd[self.tri[Vt]]] * self.bar[Vt][..., None]).sum(1)
        out = np.zeros_like(t.co)
        out[Vt] = np.einsum("nab,nb->na", self.M[Vt], dd) * self.fade[Vt, None]
        return out


class Filler:
    """Target skin vertices without a trustworthy donor point (farther than ~0.7 mm from the bent donor skin: the
    inner lips of a face whose lips curl deep into the mouth, the inside of a closed eye socket ...) do not take the
    carried offset; their offsets are filled in smoothly (harmonic, over the welded skin) from the trustworthy
    neighbours and, deep in the mouth, from the seam with the mouth interior (the upper side still, the lower side on
    the jaw)."""

    def __init__(self, corr, log=print):
        t = corr.t
        self.t = t
        C = np.unique(t.canon[t.skin_V])
        self.C = C
        pos = -np.ones(len(t.co), np.int64)
        pos[C] = np.arange(len(C))
        Fc = pos[t.canon[t.skin_F]]
        e = np.concatenate([Fc[:, [0, 1]], Fc[:, [1, 2]], Fc[:, [2, 0]]])
        e = np.unique(np.sort(e, axis=1), axis=0)
        e = e[e[:, 0] != e[:, 1]]
        self.ei = np.concatenate([e[:, 0], e[:, 1]])
        self.ej = np.concatenate([e[:, 1], e[:, 0]])
        q = t.Q[C]
        dist = corr.dist[C]
        region = (np.abs(q[:, 0]) < 1.0) & (q[:, 1] > -2.0) & (q[:, 1] < 0.9)
        self.reliable = dist < 0.012
        # the seam with the mouth interior (a mouth bag sewn to the inner lips)
        self.rim = np.zeros(len(C), bool)
        self.rim_w = np.zeros(len(C))
        if len(t.mouth_v):
            near = oc.NearestOnMesh(t.co, np.array([t.m.faces[f] for k in t.mouth_islands
                                                     for f in t.islands[k]["faces"]], np.int64))
            f, p, b = near.query(t.co[C])
            on = np.linalg.norm(p - t.co[C], axis=1) < 0.01 * t.iod
            if on.any():
                mw = np.zeros(len(t.co))
                mw[t.mouth_v] = t.mouth_w
                Fm = near.F
                self.rim = on & ~self.reliable
                self.rim_w = (mw[Fm[f]] * b).sum(1)
        self.free = ~self.reliable & region & ~self.rim
        log("filler: %d of %d welded skin vertices filled in (no close donor point), %d on the mouth-interior seam" % (
            int(self.free.sum()), len(C), int(self.rim.sum())))

    def apply(self, D, jaw_motion):
        if not self.free.any():
            return D
        t = self.t
        x = D[self.C].copy()
        if self.rim.any():
            R, tt = jaw_motion if jaw_motion is not None else (np.eye(3), np.zeros(3))
            P = t.co[self.C[self.rim]]
            x[self.rim] = ((P @ R.T + tt) - P) * self.rim_w[self.rim, None]
        free = self.free
        x[free] = 0.0
        cnt = np.bincount(self.ei, minlength=len(x)).astype(float)
        cnt[cnt == 0] = 1
        for _ in range(400):
            acc = np.zeros_like(x)
            np.add.at(acc, self.ei, x[self.ej])
            x[free] = acc[free] / cnt[free, None]
        out = D.copy()
        canon_val = np.zeros_like(D)
        canon_val[self.C] = x
        out[t.skin_V] = canon_val[t.canon[t.skin_V]]
        return out


def lid_fix(donor, target, Dd, Dt, strength=1.0):
    """Correct the target's lid margins so each eye closes / opens as much as the donor's, sample by sample; spread
    the correction over the lid.  Returns the corrected offsets and the closure ratio per eye (min over samples)."""
    out = Dt.copy()
    ratios = []
    for side in (0, 1):
        ed, et = donor.eyes[side], target.eyes[side]
        Ud, Ld = ed["upper"]["pts"], ed["lower"]["pts"]
        dU = (Dd[donor.skin_F[ed["upper"]["tri"]]] * ed["upper"]["bary"][..., None]).sum(1)
        dL = (Dd[donor.skin_F[ed["lower"]["tri"]]] * ed["lower"]["bary"][..., None]).sum(1)
        Ut, Lt = et["upper"]["pts"], et["lower"]["pts"]
        tU = (Dt[target.skin_F[et["upper"]["tri"]]] * et["upper"]["bary"][..., None]).sum(1)
        tL = (Dt[target.skin_F[et["lower"]["tri"]]] * et["lower"]["bary"][..., None]).sum(1)
        hd = np.linalg.norm(Ud - Ld, axis=1)
        ht = np.linalg.norm(Ut - Lt, axis=1)
        valid = (hd > 0.03 * donor.iod) & (ht > 0.03 * target.iod)
        ed_dir = (Ud - Ld) / np.maximum(hd, 1e-9)[:, None]
        et_dir = (Ut - Lt) / np.maximum(ht, 1e-9)[:, None]
        gd = ((Ud + dU - Ld - dL) * ed_dir).sum(1) / np.maximum(hd, 1e-9)          # donor gap / open gap
        gt = ((Ut + tU - Lt - tL) * et_dir).sum(1) / np.maximum(ht, 1e-9)
        want = 1.0 + (gd - 1.0) * strength
        delta = np.where(valid, (want - gt) * ht, 0.0)
        mu = np.abs((dU * ed_dir).sum(1))
        ml = np.abs((dL * ed_dir).sum(1))
        ru = np.where(mu + ml > 1e-9, mu / (mu + ml + 1e-12), 0.5)
        cu = (delta * ru)[:, None] * et_dir                   # upper lid moves along +dir by ru * delta
        cl = -(delta * (1 - ru))[:, None] * et_dir
        # spread over the lid: vertices of that lid's label, by distance to the margin samples
        for lab, pts, corr in ((1 + 2 * side, Ut, cu), (2 + 2 * side, Lt, cl)):
            vs = target.skin_V[target.labels[target.skin_V] == lab]
            if not len(vs):
                continue
            P = target.co[vs]
            dist = np.linalg.norm(P[:, None] - pts[None], axis=2)          # (n, K)
            k = np.argmin(dist, axis=1)
            r = dist[np.arange(len(vs)), k]
            reach = 0.6 * ht[k] + 0.04 * target.iod
            w = 1.0 - smoothstep(r / reach)
            out[vs] += w[:, None] * corr[k]
        gt2 = ((Ut + tU + cu - Lt - tL - cl) * et_dir).sum(1) / np.maximum(ht, 1e-9)
        ratios.append((float(gd[valid].min()) if valid.any() else 1.0, float(gt2[valid].min()) if valid.any() else 1.0))
    return out, ratios


class EyeGuard:
    """Skin and lashes around the eyes never go deeper into an eyeball than they were at rest (tested against the
    eyeball meshes themselves - a cornea bulges past any sphere): a vertex outside keeps its rest clearance or
    0.8 mm, whichever is less (a lid triangle a few mm wide sags ~0.3 mm into a cornea between its corners); the
    inner edge of a lid, a little inside the eyeball already, slides along it at its rest depth."""

    def __init__(self, target):
        self.t = target
        self.sides = []
        fv = np.unique(np.concatenate([target.islands[k]["verts"] for k in target.follower_islands]))             if target.follower_islands else np.zeros(0, np.int64)
        for side in (0, 1):
            eb = target.eyeball[side]
            Fe = np.array([target.m.faces[f] for k in eb["islands"] for f in target.islands[k]["faces"]], np.int64)
            near = oc.NearestOnMesh(target.co, Fe)
            c, r = eb["centre"], eb["radius"]
            sets = []
            for verts in (target.skin_V, fv):
                vs = verts[np.linalg.norm(target.co[verts] - c, axis=1) < r + 0.12 * target.iod] if len(verts) else verts
                d0 = self._signed(near, Fe, c, target.co[vs]) if len(vs) else np.zeros(0)
                keep = d0 > -0.08 * target.iod                    # not the back of a closed socket
                sets.append((vs[keep], d0[keep]))
            self.sides.append((near, Fe, c, sets))

    @staticmethod
    def _signed(near, Fe, c, P):
        f, q, _b = near.query(P)
        T = near.V[Fe[f]]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        n *= np.sign(((q - c) * n).sum(1) + 1e-12)[:, None]          # outward
        return ((P - q) * n).sum(1)

    def apply(self, D, part=0):
        """part 0: the skin, 1: the followers (lashes, brows)."""
        out = D.copy()
        t = self.t
        clear = 0.8 / UNIT_CM / 10
        for near, Fe, c, sets in self.sides:
            vs, d0 = sets[part]
            if not len(vs):
                continue
            moved = np.linalg.norm(out[vs], axis=1) > 1e-9
            vs, d0 = vs[moved], d0[moved]
            if not len(vs):
                continue
            P1 = t.co[vs] + out[vs]
            need = np.minimum(d0, clear)
            for _ in range(3):
                f, q, _b = near.query(P1)
                T = near.V[Fe[f]]
                n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
                n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
                n *= np.sign(((q - c) * n).sum(1) + 1e-12)[:, None]
                s1 = ((P1 - q) * n).sum(1)
                push = s1 < need - 1e-7
                if not push.any():
                    break
                P1[push] += (need[push] - s1[push])[:, None] * n[push]
            out[vs] = P1 - t.co[vs]
        return out


class Riders:
    """Followers (lashes, brows, ...) ride the skin under them: the attachment point moves with the skin and the
    offset from it turns with the skin around it (a rigid fit over a small patch, so a lash card turns as its lid
    does).  The mouth interior rides the jaw: the donor's jaw motion carried through the warp (else a rigid fit to
    the target's chin); the parts sewn to the lips take the lips' motion."""

    def __init__(self, target, log=print):
        self.t = target
        t = target
        Fs = t.skin_F
        self.near = oc.NearestOnMesh(t.co, Fs)
        verts = np.unique(np.concatenate([t.islands[k]["verts"] for k in t.follower_islands]))             if t.follower_islands else np.zeros(0, np.int64)
        self.fv = verts
        if len(verts):
            f, p, b = self.near.query(t.co[verts])
            # a small piece (one lash strand, one brow card) rides rigidly on the skin under its root
            dist = np.linalg.norm(p - t.co[verts], axis=1)
            row = {v: i for i, v in enumerate(verts)}
            self.n_rigid = 0
            for k in t.follower_islands:
                rows = np.array([row[v] for v in t.islands[k]["verts"]])
                P = t.co[verts[rows]]
                if np.linalg.norm(P.max(0) - P.min(0)) < 0.25 * t.iod:
                    r0 = rows[np.argmin(dist[rows])]
                    f[rows], b[rows], p[rows] = f[r0], b[r0], p[r0]
                    self.n_rigid += 1
            self.f_tri, self.f_bar, self.f_pt = f, b, p
            self.f_off = t.co[verts] - p
            self._patches(np.unique(t.canon[Fs[f]]))
            # lashes on a lid turn with that lid about the eyeball centre (like a lid bone): the lid's turn at the
            # nearest margin sample
            labs = t.labels[t.canon[Fs[f]]]                                      # (n, 3)
            lab = np.array([np.bincount(r, minlength=7).argmax() for r in labs])
            self.f_lid = []
            for side in (0, 1):
                for which, L in (("upper", 1 + 2 * side), ("lower", 2 + 2 * side)):
                    sel = np.flatnonzero(lab == L)
                    if not len(sel):
                        continue
                    pts = t.eyes[side][which]["pts"]
                    dd = np.linalg.norm(p[sel][:, None] - pts[None], axis=2)
                    k = np.argsort(dd, axis=1)[:, :2]
                    d0 = dd[np.arange(len(sel)), k[:, 0]]
                    d1 = dd[np.arange(len(sel)), k[:, 1]]
                    wk = d1 / np.maximum(d0 + d1, 1e-12)                      # weight of the nearer sample
                    self.f_lid.append((side, which, sel, k, wk))
        mv = t.mouth_v
        self.mv = mv
        if len(mv):
            # the still (upper) pieces may be sewn to the upper lip, the jaw's pieces to the lower lip - never across
            # (at the mouth corners the inner lips nearly touch)
            fl = t.labels[Fs]
            f = np.zeros(len(mv), np.int64)
            p = np.zeros((len(mv), 3))
            b = np.zeros((len(mv), 3))
            for low, banned in ((False, 6), (True, 5)):
                sel = (t.mouth_w >= 0.5) if low else (t.mouth_w < 0.5)
                if not sel.any():
                    continue
                fsel = np.flatnonzero(~(fl == banned).any(1))
                f_, p[sel], b[sel] = oc.NearestOnMesh(t.co, Fs[fsel]).query(t.co[mv[sel]])
                f[sel] = fsel[f_]
            self.m_on_skin = np.linalg.norm(p - t.co[mv], axis=1) < 0.01 * t.iod
            self.m_tri, self.m_bar = f, b
            loc = {v: i for i, v in enumerate(mv)}
            faces = [t.m.faces[f_] for k in t.mouth_islands for f_ in t.islands[k]["faces"]]
            self.m_faces = np.array([[loc[a], loc[b_], loc[c]] for a, b_, c in faces], np.int64)
        # fallback jaw reference: the chin below the lower lip
        q = t.Q[t.skin_V]
        vl = np.interp(q[:, 0], t.lips["u"], t.lips["v"])
        half = 0.5 * t.lips["width"]
        chin = (np.abs(q[:, 0]) < half) & (q[:, 1] < vl - 0.15) & (q[:, 1] > vl - 0.6) & (q[:, 2] > -0.6)
        self.chin_v = t.skin_V[chin]
        log("riders: %d follower vertices, %d mouth-interior vertices (%s)" % (
            len(verts), len(mv), ", ".join("%s %d" % kv for kv in sorted(t.mouth_kind.items())) or "-"))

    def _patches(self, centres):
        """For each centre (welded skin vertex), its neighbours within two rings of the welded skin mesh (same region
        label), Gaussian-weighted by rest distance: the patch whose rigid motion turns the followers."""
        t = self.t
        Fc = t.canon[t.skin_F]
        nbr = defaultdict(set)
        for a, b, c in Fc:
            nbr[a].update((b, c))
            nbr[b].update((a, c))
            nbr[c].update((a, b))
        I, J = [], []
        for v in centres:
            ring = {v} | nbr[v]
            two = set(ring)
            for u in ring:
                two |= nbr[u]
            lv = t.labels[v]
            for u in two:
                if lv == 0 or t.labels[u] == lv:
                    I.append(v)
                    J.append(u)
        I, J = np.array(I, np.int64), np.array(J, np.int64)
        d = np.linalg.norm(t.co[I] - t.co[J], axis=1)
        sig = 0.025 * t.iod
        self.pI, self.pJ, self.pW = I, J, np.exp(-(d / sig) ** 2) + 1e-6

    def _rotations(self, D):
        """Rigid rotation of each patch centre's neighbourhood under offsets D: {centre: 3x3} as an (n, 3, 3) array
        indexed like the model's vertices (identity where not computed)."""
        t = self.t
        I, J, W = self.pI, self.pJ, self.pW
        n = len(t.co)
        P, Q = t.co[J], t.co[J] + D[J]
        ws = np.bincount(I, W, n)
        ws[ws == 0] = 1
        pm = np.stack([np.bincount(I, W * P[:, k], n) for k in range(3)], 1) / ws[:, None]
        qm = np.stack([np.bincount(I, W * Q[:, k], n) for k in range(3)], 1) / ws[:, None]
        a = (P - pm[I]) * W[:, None]
        b = Q - qm[I]
        H = np.zeros((n, 3, 3))
        for r in range(3):
            for c in range(3):
                H[:, r, c] = np.bincount(I, a[:, r] * b[:, c], n)
        cent = np.unique(I)
        U, _S, Vt = np.linalg.svd(H[cent])
        d = np.sign(np.linalg.det(np.einsum("nji,nkj->nik", Vt, U)))
        Dg = np.zeros((len(cent), 3, 3))
        Dg[:, 0, 0] = Dg[:, 1, 1] = 1
        Dg[:, 2, 2] = np.where(d == 0, 1, d)
        R = np.tile(np.eye(3), (n, 1, 1))
        R[cent] = np.einsum("nji,njk,nlk->nil", Vt, Dg, U)
        return R

    def chin_motion(self, D):
        """Rigid motion of the chin under offsets D (the jaw when the donor has no teeth to read it from)."""
        t = self.t
        if len(self.chin_v) >= 6 and np.linalg.norm(D[self.chin_v], axis=1).max() > 0.1 / UNIT_CM / 10:
            P = t.co[self.chin_v]
            return kabsch(P, P + D[self.chin_v])
        return None

    def apply(self, D, jaw=True, jaw_motion=None):
        t = self.t
        out = D.copy()
        Fs = t.skin_F
        if len(self.fv):
            moved = (D[Fs[self.f_tri]] * self.f_bar[..., None]).sum(1)
            R = self._rotations(D)
            Rc = R[t.canon[Fs[self.f_tri]]]                                     # (n, 3, 3, 3)
            Rm = (Rc * self.f_bar[..., None, None]).sum(1)
            U, _S, Vt = np.linalg.svd(Rm)
            Rf = U @ Vt
            axis = t.B[0]
            for side, which, sel, k, wk in self.f_lid:
                e = t.eyes[side][which]
                c = t.eyeball[side]["centre"]
                Um = (D[Fs[e["tri"]]] * e["bary"][..., None]).sum(1)
                v0 = e["pts"] - c
                v1 = v0 + Um
                v0 = v0 - np.outer(v0 @ axis, axis)
                v1 = v1 - np.outer(v1 @ axis, axis)
                th = np.arctan2(np.cross(v0, v1) @ axis, (v0 * v1).sum(1))     # the lid's turn per sample
                ang = wk * th[k[:, 0]] + (1 - wk) * th[k[:, 1]]
                K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
                s_, c_ = np.sin(ang)[:, None, None], np.cos(ang)[:, None, None]
                Rf[sel] = np.eye(3)[None] + s_ * K[None] + (1 - c_) * (K @ K)[None]
            new = self.f_pt + moved + np.einsum("nab,nb->na", Rf, self.f_off)
            out[self.fv] = new - t.co[self.fv]
            still = np.abs(moved).sum(1) < 1e-9
            out[self.fv[still]] = 0.0
        self.jaw = (np.eye(3), np.zeros(3))
        if len(self.mv) and jaw:
            if jaw_motion is not None:
                Rj, tj = jaw_motion
            elif len(self.chin_v) >= 6 and np.linalg.norm(D[self.chin_v], axis=1).max() > 0.1 / UNIT_CM / 10:
                P = t.co[self.chin_v]
                Rj, tj = kabsch(P, P + D[self.chin_v])
            else:
                Rj, tj = np.eye(3), np.zeros(3)
            self.jaw = (Rj, tj)
            Pm = t.co[self.mv]
            Dm = ((Pm @ Rj.T + tj) - Pm) * t.mouth_w[:, None]
            if self.m_on_skin.any():
                # sewn vertices take the skin's motion, the correction fades over the interior mesh
                skin_moved = (D[Fs[self.m_tri]] * self.m_bar[..., None]).sum(1)
                corr = np.zeros_like(Dm)
                corr[self.m_on_skin] = skin_moved[self.m_on_skin] - Dm[self.m_on_skin]
                for _ in range(2):
                    corr = smooth_decay(corr, self.m_faces, self.m_on_skin, 25)
                Dm = Dm + corr
            out[self.mv] = Dm
        return out


def smooth_decay(values, F, pinned, iterations):
    """Spread pinned values over the mesh, decaying away from them (unpinned start at zero)."""
    i = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    j = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    cnt = np.bincount(i, minlength=len(values)).astype(float)
    cnt[cnt == 0] = 1
    out = values.copy()
    for _ in range(iterations):
        acc = np.zeros_like(out)
        np.add.at(acc, i, out[j])
        new = 0.9 * acc / cnt[:, None]
        out[~pinned] = new[~pinned]
    return out


# -- listing (for the panel) ------------------------------------------------------------------------------------------------
def list_morphs(donor_path, target_path=None):
    """[(name, name_e, category, kind, default_selected, note)] of the donor's morphs."""
    pmx = oc.pmx_module()
    D = pmx.load(donor_path)
    have = set()
    if target_path and os.path.isfile(target_path):
        T = pmx.load(target_path)
        have = {mo.name for mo in T.morphs}
    rows = []
    std = sum(1 for mo in D.morphs if mo.name in STANDARD_NAMES)
    for mo in D.morphs:
        kind = morph_kind(mo)
        note = ""
        sel = kind in ("vertex", "bone", "group")
        if kind in ("material", "uv", "empty"):
            note = {"material": "材质表情不搬", "uv": "UV 表情不搬", "empty": "空表情"}[kind]
        elif mo.name in have:
            sel, note = False, "目标已有"
        elif mo.name in NOT_BY_DEFAULT:
            sel, note = False, NOT_BY_DEFAULT[mo.name]
        elif std >= 10 and mo.name not in STANDARD_NAMES:
            sel, note = False, "不是 MMD 标准表情"
        rows.append((mo.name, mo.name_e, mo.category, kind, sel, note))
    return rows


# -- the whole run ------------------------------------------------------------------------------------------------------
def transfer_expressions(donor_path, target_path, out_path, morphs=None, replace=False, lid=True, jaw=True,
                         strength=None, roles_donor=None, roles_target=None, log=print):
    """Copy the donor's expressions onto the target's face; write the result to out_path.

    morphs: names to carry (None = the panel's default: the donor's MMD expressions the target lacks);
    replace: a same-named morph of the target is replaced (else skipped);
    lid / jaw: the lid closure correction / teeth and tongue on the jaw;
    strength: {category (1 brow, 2 eye, 3 mouth, 4 other): factor};
    roles_*: optional {"skin": [...], "eyes": [...], "followers": [...], "mouth": [...]} material names."""
    pmx = oc.pmx_module()
    log("donor  %s" % donor_path)
    log("target %s" % target_path)
    Dm = pmx.load(donor_path)
    Tm = pmx.load(target_path)
    donor = Face(pmx, Dm, log, **(roles_donor or {}))
    target = Face(pmx, Tm, log, **(roles_target or {}))
    for f, nm in ((donor, "donor"), (target, "target")):
        log("%s: IOD %.2f cm, eye openings %.2f / %.2f IOD high, mouth %.2f IOD wide" % (
            nm, f.iod * UNIT_CM, f.eyes[0]["height"], f.eyes[1]["height"], f.lips["width"]))
    corr = Correspondence(donor, target, log)
    filler = Filler(corr, log)
    guard = EyeGuard(target)
    riders = Riders(target, log)
    strength = strength or {}
    if morphs is None:
        morphs = [r[0] for r in list_morphs(donor_path, target_path) if r[4]]
    t_names = {mo.name: i for i, mo in enumerate(Tm.morphs)}
    report = {"donor": donor_path, "target": target_path, "added": [], "replaced": [], "skipped": [], "lids": {}}
    new_morphs = []
    for name in morphs:
        mi = next((i for i, mo in enumerate(Dm.morphs) if mo.name == name), None)
        if mi is None:
            report["skipped"].append((name, "来源没有"))
            continue
        mo = Dm.morphs[mi]
        kind = morph_kind(mo)
        if kind not in ("vertex", "bone", "group"):
            report["skipped"].append((name, "%s 表情不搬" % kind))
            continue
        if name in t_names and not replace:
            report["skipped"].append((name, "目标已有"))
            continue
        Dd = morph_offsets(pmx, Dm, donor.co, mi)
        if np.linalg.norm(Dd[donor.skin_V], axis=1).max() < 0.05 / UNIT_CM / 10:      # < 0.05 mm on the skin
            report["skipped"].append((name, "脸上没有变化（动的是眼球 / 牙齿 / 别处）"))
            continue
        k = strength.get(int(mo.category), 1.0)
        Dd = Dd * k
        Dt = corr.carry(Dd)
        if lid:
            Dt, ratios = lid_fix(donor, target, Dd, Dt, 1.0)
            if any(r[0] < 0.9 for r in ratios):
                report["lids"][name] = [[round(a, 3), round(b, 3)] for a, b in ratios]
        jm = corr.jaw_motion(Dd) if jaw else None
        if jaw and jm is None:
            jm = riders.chin_motion(Dt)
        Dt = filler.apply(Dt, jm)
        Dt = guard.apply(Dt)
        Dt = riders.apply(Dt, jaw=jaw, jaw_motion=jm)
        Dt = guard.apply(Dt, part=1)
        idx = np.flatnonzero(np.linalg.norm(Dt, axis=1) > 1e-6)
        vm = pmx.VertexMorph(name=name, name_e=mo.name_e or "", category=mo.category)
        for v in idx:
            o = pmx.VertexMorphOffset()
            o.index = int(v)
            o.offset = [float(x) for x in Dt[v]]
            vm.offsets.append(o)
        new_morphs.append(vm)
        if name in t_names:
            Tm.morphs[t_names[name]] = vm
            report["replaced"].append(name)
        else:
            t_names[name] = len(Tm.morphs)
            Tm.morphs.append(vm)
            report["added"].append(name)
        log("  %-8s %5d vertices, max %.2f mm" % (name, len(idx), float(np.linalg.norm(Dt, axis=1).max()) * UNIT_CM * 10))
    # 表情 frame
    facial = next((fr for fr in Tm.display if fr.name == "表情"), None)
    if facial is None:
        facial = pmx.Display()
        facial.name, facial.name_e, facial.isSpecial = "表情", "Exp", True
        Tm.display.append(facial)
    listed = {i for k, i in facial.data if k == 1}
    for name in report["added"]:
        i = t_names[name]
        if i not in listed:
            facial.data.append((1, i))
    # textures: real copies when written elsewhere
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if os.path.normcase(out_dir) != os.path.normcase(os.path.dirname(os.path.abspath(target_path))):
        tex_dir = os.path.join(out_dir, "textures")
        os.makedirs(tex_dir, exist_ok=True)
        for tx in Tm.textures:
            if os.path.isfile(tx.path):
                base, ext = os.path.splitext(os.path.basename(tx.path))
                dst, n = os.path.join(tex_dir, base + ext), 1
                while os.path.exists(dst) and os.path.getsize(dst) != os.path.getsize(tx.path):
                    dst, n = os.path.join(tex_dir, "%s_%d%s" % (base, n, ext)), n + 1
                if not os.path.exists(dst):
                    shutil.copyfile(tx.path, dst)
                tx.path = dst
    Tm.comment = (Tm.comment or "").rstrip() + "\r\nexpressions from %s by pmx_expression_transfer" % (
        os.path.basename(donor_path))
    n_uv = Tm.header.additional_uvs if Tm.header else 0
    pmx.save(out_path, Tm, add_uv_count=n_uv)
    report.update({"out": out_path, "morphs_total": len(Tm.morphs)})
    log("wrote %s: %d added, %d replaced, %d skipped" % (out_path, len(report["added"]), len(report["replaced"]),
                                                          len(report["skipped"])))
    return report
