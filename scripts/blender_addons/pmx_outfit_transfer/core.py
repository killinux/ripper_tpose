# -*- coding: utf-8 -*-
"""PMX Outfit Transfer - the algorithm.  Dresses one PMX model in another PMX model's clothes, fitted to the new
body, with the clothes' bones, rigid bodies and joints, materials and textures.  Runs inside Blender (mathutils
BVH) or under a plain Python with numpy (slower brute-force search); only the ``pmx`` module of mmd_tools is needed.

How the clothes find their place on the new body (3 steps):
1. skeleton: every garment vertex is skinned to the donor's bones; it is moved as if those bones had the target's
   rest positions (and directions, when ``align_rotation``) - linear blend skinning with per-bone transforms.
   Bones match by name; a donor bone the target lacks matches the target bone nearest to it under the same parent
   (the ROE families name the breast bones differently: chest_L02 / Breast_L02 / OPAI_L02), else it comes along;
2. body shape: the donor's body (the one the clothes were made over, retargeted the same way) is shrink-wrapped onto
   the target's nude body - a smooth displacement field over the donor body's vertices;
3. fit: each garment vertex keeps its offset from the nearest donor body face, expressed in that face's frame, and
   the face is moved by the displacement field - like Blender's Surface Deform.  Far from the body (the halo, a
   staff, a long train) the skeleton step alone decides: the fit fades out between ``near_cm`` and ``far_cm``.
4. weights (``follow_body``): the parts lying on the target's skin take the skin's weights at the point under them,
   so they move with it - the donor's weights on the target's bones split a breast or a thigh differently from the
   target's own skin (g05's cups on Inase a08's nude: the skin came out through them in every frame of a dance).
   Within ``follow_reach_cm`` of the skin fully, fading out over ``follow_fade_cm``; the share on the garment's own
   physics bones (a panel's top row) is kept.  The target's body is not touched.

Physics: the garment's rigid bodies and joints come along on the garment bones; a joint onto a donor body on a
matched bone is re-hung on the target's body there.  ``isolate`` moves the garment's dynamic bodies to collision
groups the target does not use and keeps the two outfits from colliding with each other; they still collide with
the target's body colliders (``collide_body``).
"""
import copy
import os
import re
import shutil
import sys
from collections import defaultdict

import numpy as np

# -- defaults ---------------------------------------------------------------------------------------------------------
# materials never taken as "clothes" when the caller does not choose (ROE naming + MMD habits)
NOT_OUTFIT = re.compile(r"_nk_body|_nk_face|_nude$|^eye_|^lash$|^brow$|^eye_overlay$|_nk_hair|^wp_|^hair$|^face$|^body$|"
                        r"^skin$|^eye|^tooth|^tongue|^teeth", re.IGNORECASE)
BODY_NUDE = re.compile(r"_nk_body_nude$")                    # ROE full: the nude copy; *_nk_body = the fitted one
BUST = re.compile(r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$",
                  re.IGNORECASE)
MATCH_CM = 5.0            # a nameless donor bone matches a target bone this close (same parent subtree)
UNIT_CM = 8.0             # PMX unit at mmd_tools' usual 0.08 import scale
FOLLOW_REACH_CM = 1.5     # follow_body: garment vertices this close to the target's skin take its weights fully
FOLLOW_FADE_CM = 2.0      # ... and fade back to their own weights over this much further out
HIDE_MORPH = "衣服非表示"  # the material morph made when the target has none to add the clothes to


# -- pmx module -------------------------------------------------------------------------------------------------------
def pmx_module():
    try:
        from mmd_tools.core import pmx            # inside Blender with mmd_tools installed
        return pmx
    except Exception:
        pass
    try:
        import addon_utils                        # Blender started with --factory-startup: enable it first
        addon_utils.enable("mmd_tools", default_set=False)
        from mmd_tools.core import pmx
        return pmx
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (os.path.normpath(os.path.join(here, "..", "..", "mmd_physics")),
                   r"E:\code\othercode\ripper_tpose\scripts\mmd_physics"):
        if os.path.isfile(os.path.join(folder, "cloth_collision_pmx.py")):
            if folder not in sys.path:
                sys.path.insert(0, folder)
            import cloth_collision_pmx as cc
            return cc.load_pmx_module(cc.find_pmx_module())
    raise RuntimeError("mmd_tools' pmx module not found")


def weights_of(pmx, v):
    """[(bone, weight)] of a vertex, every weight type."""
    w = v.weight
    bones, ws = list(w.bones), w.weights
    if w.type == pmx.BoneWeight.BDEF1:
        ws = [1.0]
    elif w.type == pmx.BoneWeight.BDEF2:
        ws = [ws[0], 1.0 - ws[0]]
    elif w.type == pmx.BoneWeight.SDEF:
        ws = [ws.weight, 1.0 - ws.weight]
    elif len(bones) == 2 and len(ws) == 1:
        ws = [ws[0], 1.0 - ws[0]]
    return [(b, float(x)) for b, x in zip(bones, ws) if b is not None and b >= 0 and x > 0]


def set_weights(pmx, w, weights):
    """{bone: weight} into a BDEF1 / BDEF2 / BDEF4 record (the four largest, renormalised)."""
    items = sorted(((b, x) for b, x in weights.items() if b is not None and b >= 0 and x > 1e-4),
                   key=lambda kv: -kv[1])[:4]
    total = sum(x for _b, x in items)
    items = [(b, x / total) for b, x in items]
    if len(items) == 1:
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF1, [items[0][0]], []
    elif len(items) == 2:
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF2, [items[0][0], items[1][0]], [items[0][1]]
    else:
        items += [(items[0][0], 0.0)] * (4 - len(items))
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF4, [b for b, _x in items], [x for _b, x in items]


def hide_offset(pmx):
    """A material morph offset that hides its material: diffuse and edge alpha x 0 (as ROE's 衣服非表示)."""
    o = pmx.MaterialMorphOffset()
    o.offset_type = pmx.MaterialMorphOffset.TYPE_MULT
    o.diffuse_offset, o.specular_offset, o.shininess_offset = [1.0, 1.0, 1.0, 0.0], [1.0, 1.0, 1.0], 1.0
    o.ambient_offset, o.edge_color_offset, o.edge_size_offset = [1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 0.0], 1.0
    o.texture_factor, o.sphere_texture_factor, o.toon_texture_factor = [1.0] * 4, [1.0] * 4, [1.0] * 4
    return o


def material_faces(model):
    out, start = [], 0
    for mt in model.materials:
        n = mt.vertex_count // 3
        out.append(list(range(start // 3, start // 3 + n)))
        start += mt.vertex_count
    return out


def material_vertices(model, name_pattern):
    mf = material_faces(model)
    vs = set()
    for mi, mt in enumerate(model.materials):
        if name_pattern.search(mt.name):
            for f in mf[mi]:
                vs.update(model.faces[f])
    return np.array(sorted(vs), dtype=np.int64)


def islands(faces, face_ids):
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in face_ids:
        a, b, c = faces[f]
        ra = find(a)
        parent[find(b)] = ra
        parent[find(c)] = ra
    groups = defaultdict(list)
    for f in face_ids:
        groups[find(faces[f][0])].append(f)
    return list(groups.values())


# -- geometry ---------------------------------------------------------------------------------------------------------
def rot_matrix(r):
    """PMX rigid / joint rotation (radians) -> matrix, as mmd_tools reads it: Ry @ Rx @ Rz."""
    rx, ry, rz = r
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def euler_of(R):
    rx = float(np.arcsin(np.clip(-R[1, 2], -1.0, 1.0)))
    if abs(np.cos(rx)) > 1e-6:
        return [rx, float(np.arctan2(R[0, 2], R[2, 2])), float(np.arctan2(R[1, 0], R[1, 1]))]
    return [rx, float(np.arctan2(-R[2, 0], R[0, 0])), 0.0]


def rotation_between(a, b):
    """The smallest rotation taking direction a to direction b."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))
    if s < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))


class NearestOnMesh:
    """Nearest point on a triangle mesh: (face index, point, barycentric).  mathutils BVH inside Blender, else
    a numpy search (triangle centroids' k nearest, exact point-triangle distance on those)."""

    def __init__(self, V, F):
        self.V, self.F = np.asarray(V, float), np.asarray(F, np.int64)
        self.bvh = None
        try:
            from mathutils import Vector
            from mathutils.bvhtree import BVHTree
            self.bvh = BVHTree.FromPolygons([Vector(p) for p in self.V], [tuple(int(i) for i in f) for f in self.F],
                                            all_triangles=True)
            self._Vector = Vector
        except Exception:
            self.cent = self.V[self.F].mean(1)

    def query(self, P):
        P = np.asarray(P, float)
        n = len(P)
        faces = np.zeros(n, np.int64)
        pts = np.zeros((n, 3))
        if self.bvh is not None:
            for i in range(n):
                loc, _nrm, idx, _d = self.bvh.find_nearest(self._Vector(P[i]))
                if idx is None:
                    faces[i] = -1
                    continue
                faces[i] = idx
                pts[i] = loc
            bad = faces < 0
            if bad.any():                    # out of the tree's range (should not happen without a distance limit)
                f2, p2, _ = self._numpy(P[bad], 1)
                faces[bad], pts[bad] = f2, p2
        else:
            faces, pts, _ = self._numpy(P, 12)
        bary = barycentric(P * 0 + pts, self.V[self.F[faces]])
        return faces, pts, bary

    def _numpy(self, P, k):
        faces = np.zeros(len(P), np.int64)
        pts = np.zeros((len(P), 3))
        c2 = (self.cent ** 2).sum(1)
        k = min(k, len(self.cent))
        for s in range(0, len(P), 512):
            Q = P[s:s + 512]
            d = (Q ** 2).sum(1)[:, None] + c2[None] - 2.0 * Q @ self.cent.T      # (q, faces), no (q, faces, 3)
            cand = np.argpartition(d, k - 1, axis=1)[:, :k] if k < len(self.cent) else \
                np.tile(np.arange(len(self.cent)), (len(Q), 1))
            tri = self.V[self.F[cand]]                      # (q, k, 3, 3)
            cp = closest_on_triangles(Q[:, None, :], tri)   # (q, k, 3)
            dd = ((cp - Q[:, None, :]) ** 2).sum(2)
            j = np.argmin(dd, axis=1)
            faces[s:s + 512] = cand[np.arange(len(Q)), j]
            pts[s:s + 512] = cp[np.arange(len(Q)), j]
        return faces, pts, None


def closest_on_triangles(P, tri):
    """Closest points on triangles tri (..., 3, 3) to points P (..., 3), broadcast on the leading dims."""
    A, B, C = tri[..., 0, :], tri[..., 1, :], tri[..., 2, :]
    n = np.cross(B - A, C - A)
    nn = (n * n).sum(-1, keepdims=True) + 1e-18
    q = P - ((P - A) * n).sum(-1, keepdims=True) / nn * n
    bary = barycentric(q, tri)
    inside = (bary >= -1e-6).all(-1)
    best = q.copy()
    bestd = np.where(inside, ((q - P) ** 2).sum(-1), np.inf)
    for s, e in ((A, B), (B, C), (C, A)):
        v = e - s
        t = np.clip(((P - s) * v).sum(-1) / ((v * v).sum(-1) + 1e-18), 0, 1)[..., None]
        x = s + t * v
        d = ((x - P) ** 2).sum(-1)
        take = d < bestd
        best = np.where(take[..., None], x, best)
        bestd = np.where(take, d, bestd)
    return best


def barycentric(q, tri):
    A, B, C = tri[..., 0, :], tri[..., 1, :], tri[..., 2, :]
    v0, v1, v2 = B - A, C - A, q - A
    d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
    d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
    den = d00 * d11 - d01 * d01 + 1e-18
    bv = (d11 * d20 - d01 * d21) / den
    bw = (d00 * d21 - d01 * d20) / den
    return np.stack([1 - bv - bw, bv, bw], axis=-1)


def face_frames(V, F):
    """Per face: orthonormal (e1, e2, n) rows, (nf, 3, 3)."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1 = B - A
    e1 /= np.linalg.norm(e1, axis=1, keepdims=True) + 1e-12
    n = np.cross(B - A, C - A)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    e2 = np.cross(n, e1)
    return np.stack([e1, e2, n], axis=1)


def smooth_field(values, F, iterations=5, lam=0.5):
    """Uniform Laplacian smoothing of a per-vertex field over the mesh's edges."""
    i = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    j = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    cnt = np.bincount(i, minlength=len(values)).astype(float)
    cnt[cnt == 0] = 1
    out = values.copy()
    for _ in range(iterations):
        acc = np.zeros_like(out)
        np.add.at(acc, i, out[j])
        out = (1 - lam) * out + lam * acc / cnt[:, None]
    return out


# -- the transfer -----------------------------------------------------------------------------------------------------
def auto_outfit_materials(model):
    return [mt.name for mt in model.materials if not NOT_OUTFIT.search(mt.name) and mt.vertex_count > 0]


def auto_body(model, nude):
    """The body material: nude copy (ROE *_nk_body_nude) or the fitted one (*_nk_body)."""
    names = [mt.name for mt in model.materials]
    if nude:
        for n in names:
            if BODY_NUDE.search(n):
                return n
    for n in names:
        if n.endswith("_nk_body"):
            return n
    for n in names:
        if re.search(r"body|skin|肌|体", n, re.IGNORECASE) and not NOT_OUTFIT.search(n.replace("_nk_body", "")):
            return n
    return None


def prefix_of(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"pc_([a-z]\d\d)", stem)
    return m.group(1) if m else re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", stem)[:12] or "graft"


def tail_direction(model, i):
    b = model.bones[i]
    head = np.array(b.location, float)
    dc = b.displayConnection
    if isinstance(dc, int):
        if dc >= 0 and dc < len(model.bones):
            return np.array(model.bones[dc].location, float) - head
        return None
    try:
        v = np.array(dc, float)
        return v if np.linalg.norm(v) > 1e-6 else None
    except Exception:
        return None


class Transfer:
    def __init__(self, pmx, donor, target, log=print):
        self.pmx, self.D, self.T, self.log = pmx, donor, target, log
        self.dn = [b.name for b in donor.bones]
        self.tn = {b.name: i for i, b in enumerate(target.bones)}
        self.d_head = np.array([b.location for b in donor.bones], float)
        self.t_head = np.array([b.location for b in target.bones], float)
        self.d_dyn = {r.bone for r in donor.rigids if r.mode in (1, 2) and r.bone is not None and r.bone >= 0}
        self.t_dyn = {r.bone for r in target.rigids if r.mode in (1, 2) and r.bone is not None and r.bone >= 0}
        self.kids_d = defaultdict(list)
        for i, b in enumerate(donor.bones):
            if b.parent is not None and b.parent >= 0:
                self.kids_d[b.parent].append(i)
        self.kids_t = defaultdict(list)
        for i, b in enumerate(target.bones):
            if b.parent is not None and b.parent >= 0:
                self.kids_t[b.parent].append(i)

    # -- bones ---------------------------------------------------------------------------------------------------------
    def map_bones(self, garment_bones):
        """bmap: donor bone -> target bone for matched bones; bring: donor bones that come along (parents first)."""
        D, T, dn, tn = self.D, self.T, self.dn, self.tn
        bmap, notes = {}, {}
        # 1. by name - unless both sides hang a dynamic body on it and it is not a breast (two different garments
        #    with the same chain names, e.g. two ROE skirts both called Skirt_L_01)
        for i, n in enumerate(dn):
            if n in tn:
                clash = i in self.d_dyn and tn[n] in self.t_dyn and not BUST.search(n)
                if clash and i in garment_bones:
                    notes[i] = "same name as the target's own garment bone - comes along renamed"
                    continue
                bmap[i] = tn[n]
        # 2. by position under the same parent (breast bones of other families, twist helpers)
        used = set(bmap.values())
        for i in range(len(dn)):
            if i in bmap:
                continue
            p = D.bones[i].parent
            if p is None or p < 0 or p not in bmap:
                continue
            tp = bmap[p]
            cands = [k for k in self.kids_t[tp] if k not in used]
            if not cands:
                continue
            # the donor head in the target: keep its offset from the matched parent
            pos = self.t_head[tp] + (self.d_head[i] - self.d_head[p])
            d = np.linalg.norm(self.t_head[cands] - pos, axis=1)
            k = int(np.argmin(d))
            if d[k] * UNIT_CM <= MATCH_CM:
                # a breast bone must match a breast bone; a garment bone with physics never matches a skeleton bone
                if (BUST.search(dn[i]) is not None) != (BUST.search(T.bones[cands[k]].name) is not None):
                    continue
                if i in self.d_dyn and not BUST.search(dn[i]):
                    continue
                bmap[i] = cands[k]
                used.add(cands[k])
                notes[i] = "matched by position to %s (%.1f cm)" % (T.bones[cands[k]].name, d[k] * UNIT_CM)
        # 3. everything else that the garment needs comes along, with the parents up to a matched bone
        bring = set()
        for i in garment_bones:
            j = i
            while j is not None and j >= 0 and j not in bmap and j not in bring:
                bring.add(j)
                j = D.bones[j].parent
        bring = sorted(bring)                 # donor order: parents first in the exports we handle
        self.bmap, self.bring, self.bone_notes = bmap, bring, notes
        return bmap, bring

    def anchor(self, i):
        """The matched bone whose transform moves donor bone i (itself, or the nearest matched ancestor)."""
        j = i
        while j is not None and j >= 0:
            if j in self.bmap:
                return j
            j = self.D.bones[j].parent
        return None

    def bone_transforms(self, align_rotation):
        """Per donor bone: (R, new head) so that p' = R (p - head_d) + head' for a point riding that bone alone."""
        n = len(self.dn)
        R = np.tile(np.eye(3), (n, 1, 1))
        new_head = self.d_head.copy()
        root_shift = np.zeros(3)
        for cand in ("センター", "下半身", "腰", "全ての親"):
            if cand in self.tn and cand in self.dn:
                root_shift = self.t_head[self.tn[cand]] - self.d_head[self.dn.index(cand)]
                break
        order = sorted(range(n), key=lambda i: self.depth(i))
        for i in order:
            if i in self.bmap:
                t = self.bmap[i]
                new_head[i] = self.t_head[t]
                if align_rotation:
                    a, b = tail_direction(self.D, i), tail_direction(self.T, t)
                    if a is not None and b is not None and np.linalg.norm(a) * UNIT_CM > 1.0 \
                            and np.linalg.norm(b) * UNIT_CM > 1.0:
                        Rab = rotation_between(a, b)
                        if np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)) > 0.0:   # < 90 deg: same bone
                            R[i] = Rab
                continue
            p = self.D.bones[i].parent
            if p is None or p < 0:
                new_head[i] = self.d_head[i] + root_shift
                continue
            R[i] = R[p]
            new_head[i] = R[p] @ (self.d_head[i] - self.d_head[p]) + new_head[p]
        self.R, self.new_head = R, new_head
        return R, new_head

    def depth(self, i):
        d, j = 0, i
        while j is not None and j >= 0:
            j = self.D.bones[j].parent
            d += 1
        return d

    def skin_points(self, P, weights):
        """Linear blend skinning of points P with [(bone, w)] lists through the bone transforms."""
        out = np.zeros_like(P)
        for k, (p, ws) in enumerate(zip(P, weights)):
            acc, tot = np.zeros(3), 0.0
            for b, w in ws:
                acc += w * (self.R[b] @ (p - self.d_head[b]) + self.new_head[b])
                tot += w
            out[k] = acc / tot if tot > 0 else p + (self.new_head[0] - self.d_head[0])
        return out

    def skin_vectors(self, N, weights):
        out = np.zeros_like(N)
        for k, (v, ws) in enumerate(zip(N, weights)):
            acc = np.zeros(3)
            for b, w in ws:
                acc += w * (self.R[b] @ v)
            out[k] = acc / (np.linalg.norm(acc) + 1e-12)
        return out


def transfer(donor_path, target_path, out_path, materials=None, donor_body=None, target_body=None, fit=True,
             near_cm=2.0, far_cm=12.0, align_rotation=True, split="bone", min_piece=100, prefix=None,
             isolate=True, collide_body=True, hide_morph="", follow_body=True, follow_reach_cm=FOLLOW_REACH_CM,
             follow_fade_cm=FOLLOW_FADE_CM, log=print):
    """Dress the target in the donor's materials.  Returns a report dict; writes out_path (+ textures\\).
    split: "bone" = one material per bone the pieces hang on, "island" = one per connected piece (small ones
    together by bone, < min_piece vertices), "none" = the donor's materials as they are.
    hide_morph: the target's material morph that hides its outfit (ROE full: 衣服非表示_材質) takes the new clothes too;
    a target with neither it nor a 衣服非表示 morph (a nude model) gets a 衣服非表示 material morph for them.
    follow_body: garment vertices on the target's skin take its weights (needs the fit's body materials)."""
    pmx = pmx_module()
    D, T = pmx.load(donor_path), pmx.load(target_path)
    if os.path.exists(out_path):
        raise RuntimeError("output exists: %s" % out_path)
    report = {"warnings": []}
    warn = report["warnings"].append
    prefix = prefix or prefix_of(donor_path)
    names = materials or auto_outfit_materials(D)
    d_mats = [i for i, mt in enumerate(D.materials) if mt.name in names]
    if not d_mats:
        raise RuntimeError("no donor material selected")
    log("clothes: %s" % ", ".join(D.materials[i].name for i in d_mats))

    tr = Transfer(pmx, D, T, log)
    mf = material_faces(D)
    take_faces = {mi: list(mf[mi]) for mi in d_mats}
    garment_verts = sorted({v for mi in d_mats for f in mf[mi] for v in D.faces[f]})
    gv_weights = {v: weights_of(pmx, D.vertices[v]) for v in garment_verts}

    # garment bones = bones carrying the clothes (>= 0.3 somewhere) + bones with dynamic bodies hanging under them
    garment_bones = set()
    for v in garment_verts:
        for b, w in gv_weights[v]:
            if w >= 0.3:
                garment_bones.add(b)
    # physics chains under garment bones (a chain's lower links may carry little weight but hold the bodies)
    stack = list(garment_bones)
    while stack:
        k = stack.pop()
        for c in tr.kids_d[k]:
            if c in tr.d_dyn and c not in garment_bones:
                garment_bones.add(c)
                stack.append(c)
    bmap, bring = tr.map_bones(garment_bones)
    log("bones: %d matched by name/position, %d come along (%s%s)" % (
        len(bmap), len(bring), ", ".join(tr.dn[i] for i in bring[:6]), " ..." if len(bring) > 6 else ""))
    for i, note in tr.bone_notes.items():
        if i in garment_bones or i in bring:
            log("  %s: %s" % (tr.dn[i], note))
    tr.bone_transforms(align_rotation)
    new_index = {i: len(T.bones) + k for k, i in enumerate(bring)}

    def map_bone(i):
        if i in bmap:
            return bmap[i]
        if i in new_index:
            return new_index[i]
        a = tr.anchor(i)
        return bmap[a] if a is not None else tr.tn.get("下半身", 0)

    # -- step 1: skeleton -------------------------------------------------------------------------------------------
    P = np.array([D.vertices[v].co for v in garment_verts], float)
    N = np.array([D.vertices[v].normal for v in garment_verts], float)
    W = [gv_weights[v] for v in garment_verts]
    P1 = tr.skin_points(P, W)
    N1 = tr.skin_vectors(N, W)

    # -- step 2 + 3: body shape ---------------------------------------------------------------------------------------
    disp = P1 - P                                  # per garment vertex, the whole move (for SDEF points)
    frame_rot = np.tile(np.eye(3), (len(P), 1, 1))
    fit_weight = np.zeros(len(P))
    extra_pts = []                                 # (array of points, weights) moved like garment points later
    body_d_name = donor_body or auto_body(D, nude=False)
    body_t_name = target_body or auto_body(T, nude=True)
    if fit and (body_d_name is None or body_t_name is None):
        warn("no body material found (donor %s, target %s): skeleton fit only" % (body_d_name, body_t_name))
        fit = False
    if fit:
        bd = material_vertices(D, re.compile("^%s$" % re.escape(body_d_name)))
        bt = material_vertices(T, re.compile("^%s$" % re.escape(body_t_name)))
        if len(bd) < 100 or len(bt) < 100:
            warn("body material too small (donor %d, target %d vertices): skeleton fit only" % (len(bd), len(bt)))
            fit = False
    if fit:
        log("fit: donor body %s (%d vertices) -> target body %s (%d vertices)" % (body_d_name, len(bd), body_t_name,
                                                                                len(bt)))
        # donor body faces (whole triangles inside the material), re-indexed 0..nb-1
        bd_set = {int(v): k for k, v in enumerate(bd)}
        FD = np.array([[bd_set[v] for v in D.faces[f]] for mi, mt in enumerate(D.materials)
                       if mt.name == body_d_name for f in mf[mi]], np.int64)
        bt_set = {int(v): k for k, v in enumerate(bt)}
        mft = material_faces(T)
        FT = np.array([[bt_set[v] for v in T.faces[f]] for mi, mt in enumerate(T.materials)
                       if mt.name == body_t_name for f in mft[mi]], np.int64)
        VD = np.array([D.vertices[int(v)].co for v in bd], float)
        VT = np.array([T.vertices[int(v)].co for v in bt], float)
        WD = [weights_of(pmx, D.vertices[int(v)]) for v in bd]
        VD1 = tr.skin_points(VD, WD)                               # the donor body in the target's skeleton
        near_t = NearestOnMesh(VT, FT)
        _f, pts, _b = near_t.query(VD1)
        delta = smooth_field(pts - VD1, FD, iterations=6, lam=0.5)
        # the smoothing decides WHERE on the target each donor vertex lands (no folds); a last snap puts it back ON
        # the target's surface, so the clothes keep their clearance from the skin (without it 1,200 of g05's
        # vertices ended up inside Inase a08)
        _f, pts, _b = near_t.query(VD1 + delta)
        delta = pts - VD1
        VD2 = VD1 + delta                                          # the donor body in the target's shape
        report["body_shift_cm"] = {"mean": round(float(np.linalg.norm(delta, axis=1).mean()) * UNIT_CM, 2),
                                   "max": round(float(np.linalg.norm(delta, axis=1).max()) * UNIT_CM, 2)}
        log("  body shape: donor -> target moves the body by %.1f cm on average, %.1f cm at most" % (
            report["body_shift_cm"]["mean"], report["body_shift_cm"]["max"]))
        # the clothes' place is read on the donor's OWN body, in the donor's own space: there the clothes and the
        # skin agree.  After the skeleton step they need not - a thigh band on 左足D and the skin on ThighTwist move
        # by different bone offsets (g05 -> a08: the band ended up 1 cm inside the thigh before the fit)
        near_d = NearestOnMesh(VD, FD)
        frames1, frames2 = face_frames(VD, FD), face_frames(VD2, FD)

        def fit_points(Q0, Q1):
            """Q0: positions in the donor; Q1: the same points after the skeleton step."""
            f, pts, bary = near_d.query(Q0)
            off = Q0 - pts
            dist = np.linalg.norm(off, axis=1)
            w = np.clip((far_cm / UNIT_CM - dist) / ((far_cm - near_cm) / UNIT_CM), 0.0, 1.0)
            local = np.einsum("nij,nj->ni", frames1[f], off)        # offset in the face frame (e1, e2, n)
            pts2 = np.einsum("nk,nkj->nj", bary, VD2[FD[f]])
            Q2 = pts2 + np.einsum("nji,nj->ni", frames2[f], local)
            Rf = np.einsum("nji,njk->nik", frames2[f], frames1[f])  # frame1 -> frame2 rotation
            return Q1 + w[:, None] * (Q2 - Q1), w, Rf
        P2, fit_weight, frame_rot = fit_points(P, P1)
        disp = P2 - P
        # normals: rotated with the face frame where the fit holds
        N2 = np.einsum("nij,nj->ni", frame_rot, N)
        N1 = N1 + fit_weight[:, None] * (N2 - N1)
        N1 /= np.linalg.norm(N1, axis=1, keepdims=True) + 1e-12
        report["fit"] = {"vertices": int(len(P)), "fully_fitted": int((fit_weight >= 0.999).sum()),
                         "skeleton_only": int((fit_weight <= 0.001).sum())}
        log("  %d garment vertices: %d follow the body fully, %d the skeleton only" % (
            len(P), report["fit"]["fully_fitted"], report["fit"]["skeleton_only"]))
    else:
        fit_points = None
    P_final, N_final = P + disp, N1
    vmap = {v: k for k, v in enumerate(garment_verts)}

    def move_extra(Q, ws):
        """Points that are not vertices (bone heads, bodies, joints): skeleton + fit like a vertex would be."""
        Q = np.asarray(Q, float)
        Q1 = tr.skin_points(Q, ws)
        if fit_points is None or len(Q) == 0:
            return Q1, np.tile(np.eye(3), (len(Q), 1, 1)), np.zeros(len(Q))
        Q2, w, Rf = fit_points(Q, Q1)
        return Q2, Rf, w

    # -- bones that come along -------------------------------------------------------------------------------------------
    heads = np.array([D.bones[i].location for i in bring], float) if bring else np.zeros((0, 3))
    heads2, _, _ = move_extra(heads, [[(i, 1.0)] for i in bring])
    for k, i in enumerate(bring):
        b = copy.deepcopy(D.bones[i])
        if i in tr.bone_notes and "renamed" in tr.bone_notes[i]:
            b.name = "%s:%s" % (prefix, b.name)
            b.name_e = "%s:%s" % (prefix, b.name_e or b.name)
        b.location = [float(x) for x in heads2[k]]
        p = b.parent
        b.parent = map_bone(p) if p is not None and p >= 0 else -1
        if isinstance(b.displayConnection, int):
            dc = b.displayConnection
            b.displayConnection = map_bone(dc) if dc >= 0 else -1
        if b.additionalTransform:
            t, val = b.additionalTransform
            b.additionalTransform = (map_bone(t), val)
        if b.isIK:
            b.isIK = False
            b.ik_links = []
            warn("IK bone %s comes along without its IK" % b.name)
        T.bones.append(b)
    report["bones_added"] = len(bring)

    # -- weights: the parts on the skin move with the target's skin ------------------------------------------------------
    follow = {}                                    # donor vertex -> {target bone: weight}
    if follow_body and fit:
        # the garment's physics: bones that came along carrying a dynamic body, or hanging under one
        dyn_bones = set()
        for i in bring:
            j = i
            while j is not None and j >= 0 and j not in bmap:
                if j in tr.d_dyn:
                    dyn_bones.add(i)
                    break
                j = D.bones[j].parent
        f_t, pts_t, bary_t = near_t.query(P_final)
        d_cm = np.linalg.norm(P_final - pts_t, axis=1) * UNIT_CM
        reach = np.clip((follow_reach_cm + follow_fade_cm - d_cm) / max(follow_fade_cm, 1e-6), 0.0, 1.0)
        body_w = {}
        full = 0
        for k, v in enumerate(garment_verts):
            ws = gv_weights[v]
            tot = sum(x for _b, x in ws)
            r = float(reach[k])
            if r <= 1e-3 or tot <= 0.0:
                continue
            # the share on the garment's physics bones stays as it is (a panel's top row half on its chain);
            # the rest moves from the garment's own bones to the skin's by r
            rest = 1.0 - sum(x for b, x in ws if b in dyn_bones) / tot
            if rest <= 1e-3:
                continue
            mixed = defaultdict(float)
            for b, x in ws:
                mixed[map_bone(b)] += (x if b in dyn_bones else (1.0 - r) * x) / tot
            bary = np.clip(bary_t[k], 0.0, None)
            bary = bary / (bary.sum() + 1e-12)
            for corner, bw in zip(FT[f_t[k]], bary):
                tv = int(bt[corner])
                if tv not in body_w:
                    body_w[tv] = weights_of(pmx, T.vertices[tv])
                for b, x in body_w[tv]:
                    mixed[b] += r * rest * bw * x
            follow[v] = mixed
            full += r >= 0.999
        report["follow_body"] = {"vertices": len(follow), "fully": int(full)}
        log("weights: %d garment vertices take the skin's weights (%d fully, the rest blended); the share on the "
            "garment's physics bones is kept" % (len(follow), full))

    # -- mesh ------------------------------------------------------------------------------------------------------------
    out_dir = os.path.dirname(os.path.abspath(out_path))
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)

    def place(src):
        base, ext = os.path.splitext(os.path.basename(src))
        dst, k = os.path.join(tex_dir, base + ext), 1
        while os.path.exists(dst) and os.path.getsize(dst) != os.path.getsize(src):
            dst, k = os.path.join(tex_dir, "%s_%d%s" % (base, k, ext)), k + 1
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        return dst
    if os.path.normcase(out_dir) != os.path.normcase(os.path.dirname(os.path.abspath(target_path))):
        for t in T.textures:
            if os.path.isfile(t.path):
                t.path = place(t.path)
    tex_index = {}

    def texture(src):
        if src not in tex_index:
            t = pmx.Texture()
            t.path = place(src)
            T.textures.append(t)
            tex_index[src] = len(T.textures) - 1
        return tex_index[src]

    n_uv = T.header.additional_uvs
    new_vertex = {}

    def new_vertex_of(v):
        if v in new_vertex:
            return new_vertex[v]
        src = D.vertices[v]
        nv = copy.deepcopy(src)
        k = vmap[v]
        nv.co = [float(x) for x in P_final[k]]
        nv.normal = [float(x) for x in N_final[k]]
        w = nv.weight
        if v in follow:
            set_weights(pmx, w, follow[v])
        elif isinstance(w.bones, (list, tuple)):
            w.bones = [map_bone(b) if b is not None and b >= 0 else b for b in w.bones]
        if w.type == pmx.BoneWeight.SDEF:
            d = disp[k]
            for attr in ("c", "r0", "r1"):
                val = getattr(w.weights, attr, None)
                if val is not None:
                    setattr(w.weights, attr, [float(x) for x in np.array(val, float) + d])
        nv.additional_uvs = (list(nv.additional_uvs) + [[0.0, 0.0, 0.0, 0.0]] * n_uv)[:n_uv]
        new_vertex[v] = len(T.vertices)
        T.vertices.append(nv)
        return new_vertex[v]

    def short_mat(name):
        s = re.sub(r"^pc_[a-z]\d\d_[a-z]+_", "", name)
        return re.sub(r"\s+", "", s) or name

    def bone_label(faces):
        acc = defaultdict(float)
        for f in faces:
            for v in D.faces[f]:
                for b, w in gv_weights[v]:
                    acc[b] += w
        if not acc:
            return "part"
        b = max(acc, key=acc.get)
        n = tr.dn[b]
        n = re.sub(r"_Dummy$", "", n)
        n = re.sub(r"[_\s]?\d+$", "", n)
        return n or tr.dn[b]

    new_mats = []
    pieces = []                                   # (donor material index, label, faces)
    for mi in d_mats:
        faces = take_faces[mi]
        if split == "bone":                       # one material per bone the pieces hang on (halo, leaves, panel)
            by_label = defaultdict(list)
            for g in islands(D.faces, faces):
                by_label[bone_label(g)].extend(g)
            for lab in sorted(by_label, key=lambda k: -len(by_label[k])):
                pieces.append((mi, lab, sorted(by_label[lab])))
        elif split == "island":                   # every connected piece; the small ones together, by bone
            groups = islands(D.faces, faces)
            big = [g for g in groups if len({v for f in g for v in D.faces[f]}) >= min_piece]
            small = defaultdict(list)
            for g in groups:
                if g not in big:
                    small[bone_label(g)].extend(g)
            labels = defaultdict(int)
            for g in sorted(big, key=lambda g: -len(g)):
                lab = bone_label(g)
                labels[lab] += 1
                pieces.append((mi, lab if labels[lab] == 1 else "%s_%d" % (lab, labels[lab]), sorted(g)))
            for lab in sorted(small, key=lambda k: -len(small[k])):
                pieces.append((mi, "%s_小件" % lab, sorted(small[lab])))
        else:
            pieces.append((mi, "", faces))
    for mi, label, faces in pieces:
        mt = copy.deepcopy(D.materials[mi])
        base = "%s_%s" % (prefix, short_mat(mt.name))
        mt.name = base if not label else "%s_%s" % (base, label)
        mt.name_e = mt.name
        mt.vertex_count = 3 * len(faces)
        for f in faces:
            T.faces.append(tuple(new_vertex_of(v) for v in D.faces[f]))
        for attr in ("texture", "sphere_texture") + (() if mt.is_shared_toon_texture else ("toon_texture",)):
            ti = getattr(mt, attr)
            if ti is None or ti < 0:
                continue
            src = D.textures[ti].path
            setattr(mt, attr, texture(src) if os.path.isfile(src) else -1)
        T.materials.append(mt)
        new_mats.append(len(T.materials) - 1)
    report["materials_added"] = [T.materials[i].name for i in new_mats]
    log("materials: %d new (%s%s)" % (len(new_mats), ", ".join(report["materials_added"][:5]),
                                      " ..." if len(new_mats) > 5 else ""))

    # -- the outfit switch ----------------------------------------------------------------------------------------------
    if hide_morph:
        def material_morph(name):
            return next((mo for mo in T.morphs if mo.name == name and isinstance(mo, pmx.MaterialMorph)), None)
        hide = material_morph(hide_morph) or material_morph(HIDE_MORPH)
        if hide is not None:
            for mi in new_mats:
                o = copy.deepcopy(hide.offsets[0]) if hide.offsets else hide_offset(pmx)
                o.index = mi
                hide.offsets.append(o)
            log("morph %s now hides the new clothes too" % hide.name)
        elif not any(mo.name in (hide_morph, HIDE_MORPH) for mo in T.morphs):
            # a nude model has no outfit switch: one for the new clothes, listed with the expressions
            hide = pmx.MaterialMorph(HIDE_MORPH, "hide outfit", pmx.Morph.CATEGORY_OHTER)
            for mi in new_mats:
                o = hide_offset(pmx)
                o.index = mi
                hide.offsets.append(o)
            T.morphs.append(hide)
            frame = next((d for d in T.display if d.isSpecial and d.name == "表情"), None)
            if frame is not None:
                frame.data.append((1, len(T.morphs) - 1))
            report["hide_morph_made"] = HIDE_MORPH
            log("new morph %s hides the new clothes" % HIDE_MORPH)
        else:
            other = next(mo for mo in T.morphs if mo.name in (hide_morph, HIDE_MORPH))
            warn("%s is a %s, not a material morph: the new clothes are not in it" % (other.name,
                                                                                      type(other).__name__))

    # -- display frame ---------------------------------------------------------------------------------------------------
    if bring:
        frame = pmx.Display()
        frame.name = frame.name_e = "%s衣服" % prefix
        frame.data = [(0, new_index[i]) for i in bring]
        T.display.append(frame)

    # -- physics ---------------------------------------------------------------------------------------------------------
    t_body_on_bone = {}
    for i, r in enumerate(T.rigids):
        if r.bone is not None and r.bone >= 0:
            t_body_on_bone.setdefault(r.bone, i)
    bring_set = set(bring)
    rmap = {}
    d_rigids = [(i, r) for i, r in enumerate(D.rigids) if r.bone is not None and r.bone in bring_set]
    locs = np.array([r.location for _i, r in d_rigids], float) if d_rigids else np.zeros((0, 3))
    locs2, Rf, _ = move_extra(locs, [[(r.bone, 1.0)] for _i, r in d_rigids])
    for k, (i, r) in enumerate(d_rigids):
        nr = copy.deepcopy(r)
        nr.bone = new_index[r.bone]
        nr.location = [float(x) for x in locs2[k]]
        Rtot = Rf[k] @ tr.R[r.bone] @ rot_matrix(r.rotation)
        nr.rotation = euler_of(Rtot)
        if nr.name in {x.name for x in T.rigids}:
            nr.name = "%s:%s" % (prefix, nr.name)
        rmap[i] = len(T.rigids)
        T.rigids.append(nr)
    joints_added, joints_dropped = 0, 0
    d_joints = [j for j in D.joints if j.src_rigid in rmap or j.dest_rigid in rmap]
    jl = np.array([j.location for j in d_joints], float) if d_joints else np.zeros((0, 3))
    jb = []
    for j in d_joints:
        r = D.rigids[j.dest_rigid if j.dest_rigid in rmap else j.src_rigid]
        jb.append([(r.bone, 1.0)])
    jl2, Rj, _ = move_extra(jl, jb)
    for k, j in enumerate(d_joints):
        def end(x):
            if x in rmap:
                return rmap[x]
            r = D.rigids[x]
            if r.bone is None or r.bone < 0:
                return None
            tb = map_bone(r.bone)                       # the target's body on the matched bone, or up the chain
            while tb is not None and tb >= 0:
                if tb in t_body_on_bone:
                    return t_body_on_bone[tb]
                tb = T.bones[tb].parent
            return None
        a, b = end(j.src_rigid), end(j.dest_rigid)
        if a is None or b is None:
            joints_dropped += 1
            continue
        nj = copy.deepcopy(j)
        nj.src_rigid, nj.dest_rigid = a, b
        nj.location = [float(x) for x in jl2[k]]
        bone = jb[k][0][0]
        nj.rotation = euler_of(Rj[k] @ tr.R[bone] @ rot_matrix(j.rotation))
        T.joints.append(nj)
        joints_added += 1
    report["rigids_added"], report["joints_added"], report["joints_dropped"] = len(rmap), joints_added, joints_dropped
    log("physics: %d rigid bodies, %d joints (%d dropped: no body to hang on)" % (len(rmap), joints_added,
                                                                                   joints_dropped))
    if isolate and rmap:
        report["groups"] = isolate_groups(T, set(rmap.values()), D, [i for i, _r in d_rigids], collide_body, log)

    # -- save ------------------------------------------------------------------------------------------------------------
    T.name = T.name_e = os.path.splitext(os.path.basename(out_path))[0]
    T.comment = (T.comment or "").rstrip() + "\r\n%s's clothes (%s) fitted on by pmx_outfit_transfer" % (
        prefix, os.path.basename(donor_path))
    pmx.save(out_path, T, add_uv_count=n_uv)
    back = pmx.load(out_path)
    missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
    report.update({"out": out_path, "vertices": len(back.vertices), "materials": len(back.materials),
                   "bones": len(back.bones), "rigids": len(back.rigids), "joints": len(back.joints),
                   "textures_missing": missing})
    log("wrote %s: %d vertices, %d materials, %d bones, %d rigids, %d joints%s" % (
        out_path, len(back.vertices), len(back.materials), len(back.bones), len(back.rigids), len(back.joints),
        "; textures missing: %s" % missing if missing else ""))
    return report


def isolate_groups(T, new_rigids, D, donor_rigid_ids, collide_body, log=print):
    """Move the new (donor) dynamic bodies to collision groups the target does not use; no collisions between the
    two outfits; the new bodies collide with the target's body colliders in place of the donor's.

    PMX: a body is in one group (0-15); the 16-bit mask says which groups it collides with (bit set = collides, as
    mmd_tools' pmx module reads the file); two bodies collide only when each one's mask allows the other's group."""
    old_rigids = [i for i in range(len(T.rigids)) if i not in new_rigids]
    t_groups_dyn = {T.rigids[i].collision_group_number for i in old_rigids if T.rigids[i].mode in (1, 2)}
    # body colliders = static bodies that collide with something (a static anchor with an empty mask stays out)
    t_groups_col = {T.rigids[i].collision_group_number for i in old_rigids
                    if T.rigids[i].mode == 0 and T.rigids[i].collision_group_mask}
    free = [g for g in range(15, -1, -1) if g not in t_groups_dyn and g not in t_groups_col]
    # donor groups: those of the bodies that came along, and which donor groups held colliders (mode 0)
    donor_groups_used = sorted({D.rigids[i].collision_group_number for i in donor_rigid_ids})
    donor_groups_col = {r.collision_group_number for r in D.rigids if r.mode == 0}
    remap = {}
    for g in donor_groups_used:
        if free:
            remap[g] = free.pop()
        else:
            remap[g] = max(t_groups_dyn | {15})            # out of groups: share one (still never the target's)
    for i, di in zip(sorted(new_rigids), donor_rigid_ids):
        r, dr = T.rigids[i], D.rigids[di]
        r.collision_group_number = remap[dr.collision_group_number]
        mask = 0
        for g in range(16):
            if not dr.collision_group_mask & (1 << g):
                continue
            if g in remap:                                    # the donor outfit's own groups
                mask |= 1 << remap[g]
            elif g in donor_groups_col and collide_body:      # the donor's body colliders -> the target's
                for tg in t_groups_col:
                    mask |= 1 << tg
        r.collision_group_mask = mask
    new_bits = 0
    for g in remap.values():
        new_bits |= 1 << g
    for i in old_rigids:
        r = T.rigids[i]
        if r.mode in (1, 2):
            r.collision_group_mask &= ~new_bits & 0xFFFF          # the target's clothes ignore the new ones
        elif collide_body and r.collision_group_mask:
            r.collision_group_mask |= new_bits                    # its body colliders accept them
    log("collision groups: donor %s -> %s; the two outfits never collide, the new clothes %s the body" % (
        donor_groups_used, [remap[g] for g in donor_groups_used], "collide with" if collide_body else "ignore"))
    return {"donor_groups": donor_groups_used, "new_groups": [remap[g] for g in donor_groups_used],
            "target_dynamic_groups": sorted(t_groups_dyn), "target_collider_groups": sorted(t_groups_col)}
