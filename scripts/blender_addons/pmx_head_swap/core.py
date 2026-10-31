# -*- coding: utf-8 -*-
"""PMX Head Swap - put one PMX model's head (face, eyes, lashes, brows, hair, ...) on another PMX model's body, with a
neck seam that cannot be seen.  Shares its helpers with pmx_outfit_transfer (same folder of add-ons).

What makes the seam invisible (all on the PMX data, no Blender needed):
1. the seam is the neck ring: the open edge of the donor's face mesh at the neck (ROE faces carry the neck down to the
   collar) and the open edge of the target's body at the top.  The head is placed so the two rings' centres and the
   neck axes (ring centre -> 頭) agree;
2. every ring vertex of the head is moved EXACTLY onto the body ring: rings with the same vertex count pair by angle
   around the neck (ROE: 60 and 60); otherwise each head vertex goes to the nearest point of the body ring's polyline
   and the body ring's own vertices are cut into the head's edge, so both edges are the same polyline - no gap, no
   T-junction;
3. the move fades out up the neck (``blend_cm``), the displacement smoothed over the mesh so no crease forms;
4. at the ring the head takes the body's vertex normals and bone weights (so shading and motion are continuous),
   blended out over the same band;
5. skin colour: the head's face texture is scaled so the skin just above the ring matches the body's skin just below
   it (one gain for the whole texture), and what is left of the difference per ring vertex is baked as a gradient into
   the texture over the band (``tone="seam"``).
The target's own head (face, eyes, lashes, brows, hair + hair physics, face morphs) is removed; the donor's head bones
come along (standard ones match by name and the target's copies move to the donor's positions, so the eyes turn
around the new eyes), its hair physics too, in collision groups the target does not use.
"""
import copy
import os
import re
import shutil
import sys
from collections import defaultdict, Counter

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
    raise ImportError("pmx_outfit_transfer/core.py not found next to pmx_head_swap")


oc = _outfit_core()

UNIT_CM = oc.UNIT_CM
HEAD_MAT = re.compile(r"_nk_face|^face|^eye|^lash|^brow|_nk_hair|^hair|^teeth|^tooth|^tongue|^mouth|^skin_face|^head",
                      re.IGNORECASE)
FACE_MAT = re.compile(r"_nk_face$|^face$|^face_|^skin_face|^head$", re.IGNORECASE)
BODY_MAT = re.compile(r"_nk_body$", re.IGNORECASE)
HEAD_BONES = ("頭",)


# -- helpers ------------------------------------------------------------------------------------------------------
def auto_head_materials(model, with_nude=False):
    out = []
    for mt in model.materials:
        if mt.vertex_count <= 0 or not HEAD_MAT.search(mt.name):
            continue
        if not with_nude and mt.name.endswith("_nude"):
            continue
        out.append(mt.name)
    return out


def face_material(model, candidates):
    for n in candidates:
        if FACE_MAT.search(n) and not n.endswith("_nude"):
            return n
    return candidates[0] if candidates else None


def body_materials(model):
    return [mt.name for mt in model.materials if BODY_MAT.search(mt.name) and not mt.name.endswith("_nude")] or \
           [mt.name for mt in model.materials if BODY_MAT.search(mt.name)]


def boundary_loops(model, mat_names, co):
    """Open edges of the given materials' faces, with coincident vertices merged: list of loops of vertex indices."""
    mf = oc.material_faces(model)
    mats = {n for n in mat_names}
    faces = [f for mi, mt in enumerate(model.materials) if mt.name in mats for f in mf[mi]]
    key, canon = {}, {}
    for f in faces:
        for v in model.faces[f]:
            canon[v] = key.setdefault(tuple(np.round(co[v], 4)), v)
    edges = Counter()
    for f in faces:
        a, b, c = (canon[v] for v in model.faces[f])
        for e in ((a, b), (b, c), (c, a)):
            if e[0] != e[1]:
                edges[tuple(sorted(e))] += 1
    adj = defaultdict(list)
    for (a, b), n in edges.items():
        if n == 1:
            adj[a].append(b)
            adj[b].append(a)
    seen, loops = set(), []
    for v in adj:
        if v in seen:
            continue
        loop, cur, prev = [], v, None
        while cur not in seen:
            seen.add(cur)
            loop.append(cur)
            nxt = [x for x in adj[cur] if x != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        loops.append(loop)
    return loops, canon


def neck_ring(model, mat_names, co, neck_pos, log, near=None):
    """The neck ring among the materials' boundary loops: the largest loop whose centre is within 1.2 units of the
    neck joint (or, with ``near`` = positions of the other side's ring, the loop coinciding best with them).
    Returns the loop as vertex indices (one per position)."""
    loops, canon = boundary_loops(model, mat_names, co)
    cands = [l for l in loops if len(l) >= 12]
    if near is not None:
        def score(l):
            d = np.array([np.linalg.norm(near - co[v], axis=1).min() for v in l])
            return float((d < 1e-3).mean())
        best = max(cands, key=score)
        if score(best) > 0.5:
            return best
    cands = [l for l in cands if np.linalg.norm(co[l].mean(0) - neck_pos) < 1.2]
    if not cands:
        raise RuntimeError("no neck ring found among %s (open edge within 1.2 units of 首)" % list(mat_names))
    return max(cands, key=len)


def ring_frame(ring_pts, axis):
    """Centre, axis (unit), and the angle of each ring point around the axis (0 = front -z, + = x)."""
    c = ring_pts.mean(0)
    axis = axis / (np.linalg.norm(axis) + 1e-12)
    front = np.array([0, 0, -1.0])
    front -= axis * (front @ axis)
    front /= np.linalg.norm(front) + 1e-12
    side = np.cross(axis, front)
    rel = ring_pts - c
    ang = np.arctan2(rel @ side, rel @ front)
    return c, axis, front, side, ang


def angle_of(P, c, axis, front, side):
    rel = P - c
    return np.arctan2(rel @ side, rel @ front)


def interp_ring(ang_sorted, vals_sorted, theta):
    """Periodic linear interpolation of per-ring-vertex values (sorted by angle) at angles theta."""
    a = np.concatenate([ang_sorted, ang_sorted[:1] + 2 * np.pi])
    v = np.concatenate([vals_sorted, vals_sorted[:1]], axis=0)
    t = np.mod(theta - a[0], 2 * np.pi) + a[0]
    k = np.searchsorted(a, t) - 1
    k = np.clip(k, 0, len(a) - 2)
    w = (t - a[k]) / (a[k + 1] - a[k] + 1e-12)
    if v.ndim == 1:
        return v[k] * (1 - w) + v[k + 1] * w
    return v[k] * (1 - w)[:, None] + v[k + 1] * w[:, None]


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def smooth_pinned(values, faces, pinned, iterations=12, lam=0.5):
    """Laplacian smoothing of a per-vertex field over the given faces; pinned vertices keep their value."""
    F = np.asarray(faces, np.int64)
    i = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    j = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    cnt = np.bincount(i, minlength=len(values)).astype(float)
    cnt[cnt == 0] = 1
    out = values.copy()
    free = ~pinned
    for _ in range(iterations):
        acc = np.zeros_like(out)
        np.add.at(acc, i, out[j])
        new = (1 - lam) * out + lam * acc / cnt[:, None]
        out[free] = new[free]
    return out


def blend_weights(wa, wb, t):
    """[(bone, w)] lists -> blended, <= 4 bones."""
    acc = defaultdict(float)
    for b, w in wa:
        acc[b] += (1 - t) * w
    for b, w in wb:
        acc[b] += t * w
    pairs = sorted(acc.items(), key=lambda p: -p[1])[:4]
    s = sum(w for _b, w in pairs) or 1.0
    return [(b, w / s) for b, w in pairs]


def set_weights(pmx, v, pairs):
    pairs = [(b, w) for b, w in pairs if w > 1e-6][:4]
    s = sum(w for _b, w in pairs) or 1.0
    pairs = [(b, w / s) for b, w in pairs]
    w = v.weight
    if not pairs:
        return
    if len(pairs) == 1:
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF1, [pairs[0][0]], []
    elif len(pairs) == 2:
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF2, [pairs[0][0], pairs[1][0]], [pairs[0][1]]
    else:
        while len(pairs) < 4:
            pairs.append((pairs[0][0], 0.0))
        w.type, w.bones, w.weights = pmx.BoneWeight.BDEF4, [p[0] for p in pairs], [p[1] for p in pairs]


# -- images (PIL outside Blender, bpy inside) ------------------------------------------------------------------------
def read_image(path):
    try:
        from PIL import Image
        return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0
    except ImportError:
        import bpy
        img = bpy.data.images.load(path, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        return px.reshape(h, w, 4)[::-1]          # Blender stores bottom-up


def write_image(path, arr):
    arr = np.clip(arr, 0, 1)
    try:
        from PIL import Image
        Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA").save(path)
    except ImportError:
        import bpy
        h, w = arr.shape[:2]
        img = bpy.data.images.new("head_swap_tone", w, h, alpha=True)
        img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).reshape(-1).astype(np.float32))
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        bpy.data.images.remove(img)


def sample(img, uv):
    """Bilinear-free nearest sample of RGB at uv (wrapping), uv (n, 2) PMX convention (v down)."""
    h, w = img.shape[:2]
    u = np.mod(uv[:, 0], 1.0)
    v = np.mod(uv[:, 1], 1.0)
    x = np.clip((u * w).astype(int), 0, w - 1)
    y = np.clip((v * h).astype(int), 0, h - 1)
    return img[y, x, :3]


def skin_mean(img, uvs, k=5):
    """Mean colour of a (blurred, k x k box) texture at the given uvs - the skin tone around them."""
    h, w = img.shape[:2]
    acc = np.zeros(3)
    n = 0
    for du in range(-k, k + 1, 2):
        for dv in range(-k, k + 1, 2):
            uv = uvs + np.array([du / w, dv / h])
            acc += sample(img, uv).sum(0)
            n += len(uvs)
    return acc / max(n, 1)


def rasterize_factor(img, tris_uv, tri_factors):
    """Multiply the texture inside each uv triangle by the per-corner factors (barycentric), wrapping uvs."""
    h, w = img.shape[:2]
    out = img
    for tri, fac in zip(tris_uv, tri_factors):
        uv = np.mod(tri, 1.0)
        if (np.abs(np.diff(np.concatenate([uv, uv[:1]]), axis=0)) > 0.5).any():
            continue                                  # crosses the wrap edge: leave it
        px = np.stack([uv[:, 0] * w, uv[:, 1] * h], axis=1)
        x0, y0 = np.floor(px.min(0)).astype(int) - 1
        x1, y1 = np.ceil(px.max(0)).astype(int) + 1
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, w - 1), min(y1, h - 1)
        if x1 <= x0 or y1 <= y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        P = np.stack([xs.ravel(), ys.ravel()], axis=1)
        A, B, C = px
        v0, v1, v2 = B - A, C - A, P - A
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-9:
            continue
        bv = (v2[:, 0] * v1[1] - v1[0] * v2[:, 1]) / den
        bw = (v0[0] * v2[:, 1] - v2[:, 0] * v0[1]) / den
        bu = 1 - bv - bw
        inside = (bu >= -0.002) & (bv >= -0.002) & (bw >= -0.002)
        if not inside.any():
            continue
        f = bu[:, None] * fac[0] + bv[:, None] * fac[1] + bw[:, None] * fac[2]
        yy, xx = ys.ravel()[inside].astype(int), xs.ravel()[inside].astype(int)
        out[yy, xx, :3] *= f[inside]
    return out


# -- the swap ---------------------------------------------------------------------------------------------------------
def swap_head(donor_path, target_path, out_path, head_materials=None, remove_materials=None, blend_cm=4.0,
              tone="seam", scale=1.0, prefix=None, face=None, body=None, log=print):
    """face: the donor's face material (the one whose open edge is the neck ring; default: by name, else the first
    head material); body: the target's body material(s), comma-separated (default ROE *_nk_body, else the outfit
    transfer's body guess - another game's model)."""
    pmx = oc.pmx_module()
    D, T = pmx.load(donor_path), pmx.load(target_path)
    if os.path.exists(out_path):
        raise RuntimeError("output exists: %s" % out_path)
    report = {"warnings": []}
    warn = report["warnings"].append
    prefix = prefix or oc.prefix_of(donor_path)
    dn, tn = [b.name for b in D.bones], [b.name for b in T.bones]
    tidx = {n: i for i, n in enumerate(tn)}
    for n in ("首", "頭"):
        if n not in dn or n not in tidx:
            raise RuntimeError("both models need the bones 首 and 頭")
    head_mats = head_materials or auto_head_materials(D)
    remove_mats = remove_materials if remove_materials is not None else auto_head_materials(T, with_nude=True)
    face_mat = face or face_material(D, head_mats)
    if face_mat is None:
        raise RuntimeError("no face material among %s" % head_mats)
    t_body = [n.strip() for n in body.split(",") if n.strip()] if body else body_materials(T)
    if not t_body and oc.auto_body(T, nude=False):
        t_body = [oc.auto_body(T, nude=False)]           # another game: SkinEve, *-body05 ...
    if not t_body:
        raise RuntimeError("no body material in the target (ROE *_nk_body; else name it: body=...)")
    log("head: %s (face %s); removed from the target: %s; body ring on %s" % (
        ", ".join(head_mats), face_mat, ", ".join(remove_mats) or "-", t_body[0]))

    co_d = np.array([v.co for v in D.vertices], float)
    co_t = np.array([v.co for v in T.vertices], float)
    d_neck, d_head = np.array(D.bones[dn.index("首")].location), np.array(D.bones[dn.index("頭")].location)
    t_neck, t_head = np.array(T.bones[tidx["首"]].location), np.array(T.bones[tidx["頭"]].location)

    # -- rings ------------------------------------------------------------------------------------------------------
    d_ring = neck_ring(D, [face_mat], co_d, d_neck, log)
    t_face = [n for n in remove_mats if FACE_MAT.search(n) and not n.endswith("_nude")]
    near = None
    if t_face:
        try:
            near = co_t[neck_ring(T, t_face[:1], co_t, t_neck, log)]
        except RuntimeError:
            near = None
    t_ring = neck_ring(T, t_body[:1], co_t, t_neck, log, near=near)
    log("neck ring: donor %d vertices, target %d vertices" % (len(d_ring), len(t_ring)))

    # -- rigid placement of the head: ring centre onto ring centre, neck axis onto neck axis, optional scale ----------
    dc, daxis, *_ = ring_frame(co_d[d_ring], d_head - co_d[d_ring].mean(0))
    tc, taxis, tfront, tside, _ = ring_frame(co_t[t_ring], t_head - co_t[t_ring].mean(0))
    R = oc.rotation_between(daxis, taxis)
    S = float(scale)

    def place(P):
        return (R @ ((np.asarray(P, float) - dc).T)).T * S + tc

    def place_dir(N):
        return (R @ np.asarray(N, float).T).T
    log("placed: centre shift %s cm, axis turn %.1f deg, scale %.3f" % (
        np.round((tc - dc) * UNIT_CM, 1).tolist(), np.degrees(np.arccos(np.clip(daxis @ taxis, -1, 1))), S))

    # -- head vertices (the donor's head materials) -----------------------------------------------------------------
    mfd = oc.material_faces(D)
    head_mi = [i for i, mt in enumerate(D.materials) if mt.name in head_mats]
    face_mi = [i for i, mt in enumerate(D.materials) if mt.name == face_mat]
    head_faces = [f for mi in head_mi for f in mfd[mi]]
    face_faces = [f for mi in face_mi for f in mfd[mi]]
    head_verts = sorted({v for f in head_faces for v in D.faces[f]})
    face_verts = sorted({v for f in face_faces for v in D.faces[f]})
    hv = {v: k for k, v in enumerate(head_verts)}
    P = place(co_d[head_verts])
    N = place_dir(np.array([D.vertices[v].normal for v in head_verts]))
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    # UV-seam twins (two vertices at one position, e.g. down the back of the neck) must move as one, or the seam
    # opens into a hairline crack after the blend: everything below is computed on one twin and copied
    key_h, canon_h = {}, np.arange(len(head_verts))
    for k, v in enumerate(head_verts):
        canon_h[k] = key_h.setdefault(tuple(np.round(co_d[v], 4)), k)

    # the ring pairs: donor ring vertex -> position / normal / weights of the target ring there
    d_ang = angle_of(P[[hv[v] for v in d_ring]], tc, taxis, tfront, tside)
    t_ang = angle_of(co_t[t_ring], tc, taxis, tfront, tside)
    d_order, t_order = np.argsort(d_ang), np.argsort(t_ang)
    t_ring_sorted = [t_ring[k] for k in t_order]
    t_pos_sorted = co_t[t_ring_sorted]
    t_nrm_sorted = np.array([T.vertices[v].normal for v in t_ring_sorted], float)
    t_w_sorted = [oc.weights_of(pmx, T.vertices[v]) for v in t_ring_sorted]
    splits = []                                      # (donor edge (a, b) in head-vertex index, t, target ring vertex)
    pair_pos, pair_nrm, pair_w = {}, {}, {}           # donor ring vertex -> target data
    if len(d_ring) == len(t_ring):
        # same sampling: pair by angle order.  ROE heads: 60 and 60, the same base ring
        for kd, kt in zip(d_order, t_order):
            v = d_ring[kd]
            pair_pos[v] = co_t[t_ring[kt]]
            pair_nrm[v] = np.array(T.vertices[t_ring[kt]].normal, float)
            pair_w[v] = oc.weights_of(pmx, T.vertices[t_ring[kt]])
        dist = np.array([np.linalg.norm(pair_pos[v] - P[hv[v]]) for v in d_ring])
        log("  paired 1:1 by angle: ring vertices move %.1f cm on average, %.1f cm at most" % (
            dist.mean() * UNIT_CM, dist.max() * UNIT_CM))
        report["ring"] = {"pairing": "1:1", "move_cm_mean": round(float(dist.mean()) * UNIT_CM, 2),
                          "move_cm_max": round(float(dist.max()) * UNIT_CM, 2)}
    else:
        # different sampling: each donor vertex goes onto the target polyline AT ITS OWN ANGLE (between the two target
        # vertices around it), and the target vertices are cut into the donor's boundary edges by angle too, so both
        # edges become the same polyline in the same order.  (Placing the donor vertices at the nearest point instead
        # let them overtake the cut-in target vertices: the edge folded back and left little triangular holes along
        # the seam - Stellar Blade Eve's 44-vertex neck on Inase a08's 60.)
        t_ang_sorted = t_ang[t_order]
        ext_ang = np.concatenate([t_ang_sorted, t_ang_sorted[:1] + 2 * np.pi])
        tw = t_w_sorted + t_w_sorted[:1]
        for i_r, v in enumerate(d_ring):
            th = d_ang[i_r]
            pair_pos[v] = interp_ring(t_ang_sorted, t_pos_sorted, np.array([th]))[0]
            n = interp_ring(t_ang_sorted, t_nrm_sorted, np.array([th]))[0]
            pair_nrm[v] = n / (np.linalg.norm(n) + 1e-12)
            t = np.mod(th - ext_ang[0], 2 * np.pi) + ext_ang[0]
            k = int(np.clip(np.searchsorted(ext_ang, t) - 1, 0, len(ext_ang) - 2))
            frac = float((t - ext_ang[k]) / (ext_ang[k + 1] - ext_ang[k] + 1e-12))
            pair_w[v] = blend_weights(tw[k], tw[k + 1], frac)
        # target vertices between two consecutive donor ring vertices (by angle): split that donor edge there
        d_sorted = [d_ring[k] for k in d_order]
        d_ang_sorted = d_ang[d_order]
        for kt, v_t in enumerate(t_ring_sorted):
            th = t_ang[t_order][kt]
            k = int(np.searchsorted(d_ang_sorted, th)) % len(d_sorted)
            a, b = d_sorted[k - 1], d_sorted[k]
            pa, pb = pair_pos[a], pair_pos[b]
            q = co_t[v_t]
            if min(np.linalg.norm(q - pa), np.linalg.norm(q - pb)) < 1e-4:
                continue
            seg = pb - pa
            t = float(np.clip(((q - pa) @ seg) / ((seg @ seg) + 1e-12), 0.0, 1.0))
            splits.append((a, b, t, v_t))
        report["ring"] = {"pairing": "projected", "splits": len(splits)}
        log("  rings differ (%d vs %d): donor vertices onto the target polyline, %d target vertices cut in" % (
            len(d_ring), len(t_ring), len(splits)))

    # -- the band: displacement that fades out up the neck, smoothed over the face mesh -----------------------------
    ring_by_key = {tuple(np.round(co_d[v], 4)): v for v in d_ring}
    ring_of = [ring_by_key.get(tuple(np.round(co_d[v], 4)), -1) for v in head_verts]   # head vertex -> ring vertex
    axial = (P - tc) @ taxis
    theta = angle_of(P, tc, taxis, tfront, tside)
    ring_axial = axial[[hv[v] for v in d_ring]][d_order]
    base = interp_ring(d_ang[d_order], ring_axial, theta)
    h = axial - base
    blend = blend_cm / UNIT_CM
    w = smoothstep(1.0 - h / blend)
    face_set = set(face_verts)
    is_face = np.array([v in face_set for v in head_verts])
    w[~is_face] = 0.0                                  # eyes, hair, teeth keep their place
    on_ring = np.array([rv >= 0 for rv in ring_of])
    w[on_ring] = 1.0
    ring_disp = np.array([pair_pos[v] - P[hv[v]] for v in d_ring])
    disp = interp_ring(d_ang[d_order], ring_disp[d_order], theta) * w[:, None]
    for k, rv in enumerate(ring_of):
        if rv >= 0:
            disp[k] = pair_pos[rv] - P[k]
    pinned = (w >= 1.0) | (w <= 0.0)
    local_faces = np.array([[canon_h[hv[v]] for v in D.faces[f]] for f in face_faces], np.int64)
    disp = smooth_pinned(disp, local_faces, pinned, iterations=15, lam=0.5)[canon_h]
    P2 = P + disp
    band = (w > 0) & (w < 1)
    report["band"] = {"vertices": int(band.sum()), "blend_cm": blend_cm}
    log("  band: %d face vertices blend over %.1f cm" % (band.sum(), blend_cm))

    # normals: the ring takes the body's; the band turns its normals by the ring's turn, fading out
    ring_rot = []
    for v in d_ring:
        n0 = N[hv[v]]
        ring_rot.append(oc.rotation_between(n0, pair_nrm[v]))
    ring_rot = np.array(ring_rot)[d_order]            # (n, 3, 3) sorted by angle
    N2 = N.copy()
    for k in np.where(w > 0)[0]:
        th = theta[k]
        # nearest ring pair (by angle) gives the turn; scale it by w through axis-angle
        j = int(np.argmin(np.abs(np.angle(np.exp(1j * (d_ang[d_order] - th))))))
        Rk = ring_rot[j]
        ang = np.arccos(np.clip((np.trace(Rk) - 1) / 2, -1, 1))
        if ang < 1e-6:
            continue
        axis = np.array([Rk[2, 1] - Rk[1, 2], Rk[0, 2] - Rk[2, 0], Rk[1, 0] - Rk[0, 1]])
        axis /= np.linalg.norm(axis) + 1e-12
        a = ang * w[k]
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        Rw = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
        N2[k] = Rw @ N[k]
    for k, rv in enumerate(ring_of):
        if rv >= 0:
            N2[k] = pair_nrm[rv]
    N2 /= np.linalg.norm(N2, axis=1, keepdims=True) + 1e-12

    # -- bones: map the donor's to the target's (name / position / bring), head-subtree bones take the donor's places --
    head_bone_set = set()
    for v in head_verts:
        for b, x in oc.weights_of(pmx, D.vertices[v]):
            if x >= 0.3:
                head_bone_set.add(b)
    tr = oc.Transfer(pmx, D, T, log)
    stack = list(head_bone_set)
    while stack:
        k = stack.pop()
        for c in tr.kids_d[k]:
            if c in tr.d_dyn and c not in head_bone_set:
                head_bone_set.add(c)
                stack.append(c)
    bmap, bring = tr.map_bones(head_bone_set)
    new_index = {i: len(T.bones) + k for k, i in enumerate(bring)}

    def map_bone(i):
        if i in bmap:
            return bmap[i]
        if i in new_index:
            return new_index[i]
        a = tr.anchor(i)
        return bmap[a] if a is not None else tidx["頭"]
    # the target's head-subtree bones (under 頭, not 頭) move to the donor's places so the eyes turn about the new eyes
    t_kids = defaultdict(list)
    for i, b in enumerate(T.bones):
        if b.parent is not None and b.parent >= 0:
            t_kids[b.parent].append(i)
    t_head_sub = set()
    stack = list(t_kids[tidx["頭"]])
    while stack:
        k = stack.pop()
        t_head_sub.add(k)
        stack.extend(t_kids[k])
    moved = 0
    for i_d, i_t in bmap.items():
        if i_t in t_head_sub:
            T.bones[i_t].location = [float(x) for x in place(np.array(D.bones[i_d].location)[None])[0]]
            moved += 1
    for k, i in enumerate(bring):
        b = copy.deepcopy(D.bones[i])
        b.location = [float(x) for x in place(np.array(b.location)[None])[0]]
        p = b.parent
        b.parent = map_bone(p) if p is not None and p >= 0 else -1
        if isinstance(b.displayConnection, int):
            dc_ = b.displayConnection
            b.displayConnection = map_bone(dc_) if dc_ >= 0 else -1
        if b.additionalTransform:
            t_, val = b.additionalTransform
            b.additionalTransform = (map_bone(t_), val)
        if b.isIK:
            b.isIK = False
            b.ik_links = []
            warn("IK bone %s comes along without its IK" % b.name)
        T.bones.append(b)
    log("bones: %d matched, %d moved to the donor's places, %d come along" % (len(bmap), moved, len(bring)))

    # -- remove the target's head ----------------------------------------------------------------------------------
    mft = oc.material_faces(T)
    rm_mi = {i for i, mt in enumerate(T.materials) if mt.name in remove_mats}
    keep_faces = [f for mi, mt in enumerate(T.materials) if mi not in rm_mi for f in mft[mi]]
    keep_verts = sorted({v for f in keep_faces for v in T.faces[f]})
    vmap = {v: k for k, v in enumerate(keep_verts)}
    removed_verts = len(T.vertices) - len(keep_verts)
    # bones whose weight only lived on removed vertices (the hair chains): their physics goes
    had = Counter()
    for v in T.vertices:
        for b, x in oc.weights_of(pmx, v):
            had[b] += x
    left = Counter()
    for v in keep_verts:
        for b, x in oc.weights_of(pmx, T.vertices[v]):
            left[b] += x
    orphan = {b for b in had if had[b] > 0.5 and left[b] < 1e-3}
    n_rigids_before, n_joints_before = len(T.rigids), len(T.joints)
    rigid_keep = [i for i, r in enumerate(T.rigids) if not (r.bone is not None and r.bone in orphan)]
    rmap = {old: k for k, old in enumerate(rigid_keep)}
    T.rigids = [T.rigids[i] for i in rigid_keep]
    T.joints = [j for j in T.joints if j.src_rigid in rmap and j.dest_rigid in rmap]
    for j in T.joints:
        j.src_rigid, j.dest_rigid = rmap[j.src_rigid], rmap[j.dest_rigid]
    log("removed: %d materials, %d vertices, %d rigid bodies + %d joints on bones left without weights (%s)" % (
        len(rm_mi), removed_verts, n_rigids_before - len(T.rigids), n_joints_before - len(T.joints),
        ", ".join(sorted(tn[b] for b in orphan)[:5]) + (" ..." if len(orphan) > 5 else "")))
    T.vertices = [T.vertices[v] for v in keep_verts]
    T.faces = [tuple(vmap[v] for v in T.faces[f]) for f in keep_faces]
    mat_map = {}
    new_mats = []
    for mi, mt in enumerate(T.materials):
        if mi in rm_mi:
            continue
        mat_map[mi] = len(new_mats)
        new_mats.append(mt)
    T.materials = new_mats
    # morphs: offsets on removed vertices / materials go; empty morphs go; same-named donor morphs replace
    kept_morphs, morph_map = [], {}
    n_morphs_before = len(T.morphs)
    for mi, mo in enumerate(T.morphs):
        offs = mo.offsets
        if offs and hasattr(offs[0], "index") and hasattr(offs[0], "offset"):          # vertex / uv morph
            mo.offsets = [o for o in offs if o.index in vmap]
            for o in mo.offsets:
                o.index = vmap[o.index]
        elif offs and hasattr(offs[0], "index") and hasattr(offs[0], "offset_type"):   # material morph
            mo.offsets = [o for o in offs if o.index == -1 or o.index in mat_map]
            for o in mo.offsets:
                if o.index != -1:
                    o.index = mat_map[o.index]
        if offs and not mo.offsets:
            continue
        morph_map[mi] = len(kept_morphs)
        kept_morphs.append(mo)
    T.morphs = kept_morphs
    removed_morphs = n_morphs_before - len(kept_morphs)
    for mo in T.morphs:
        if mo.offsets and hasattr(mo.offsets[0], "morph"):
            mo.offsets = [o for o in mo.offsets if o.morph in morph_map]
            for o in mo.offsets:
                o.morph = morph_map[o.morph]
    for fr in T.display:
        fr.data = [(k, (morph_map[i] if k == 1 else i)) for k, i in fr.data if not (k == 1 and i not in morph_map)]

    # -- add the donor's head: vertices, faces, materials, textures ---------------------------------------------------
    out_dir = os.path.dirname(os.path.abspath(out_path))
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)

    def place_tex(src):
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
                t.path = place_tex(t.path)
    tex_index = {}

    def texture(src):
        if src not in tex_index:
            t = pmx.Texture()
            t.path = place_tex(src)
            T.textures.append(t)
            tex_index[src] = len(T.textures) - 1
        return tex_index[src]

    # skin tone: the face texture gets one gain (body skin below the ring / face skin above it) and, for "seam", the
    # residual per ring vertex baked as a gradient over the band
    face_tex_src = D.textures[D.materials[face_mi[0]].texture].path if D.materials[face_mi[0]].texture >= 0 else None
    toned_path = None
    if tone != "none" and face_tex_src and os.path.isfile(face_tex_src):
        body_tex_src = None
        bmi = [i for i, mt in enumerate(T.materials) if mt.name == t_body[0]]
        if bmi and T.materials[bmi[0]].texture >= 0:
            body_tex_src = T.textures[T.materials[bmi[0]].texture].path
        if body_tex_src and os.path.isfile(body_tex_src):
            img_f = read_image(face_tex_src)
            img_b = read_image(body_tex_src)
            # the band on the head: face vertices 0.3-3 cm above the ring; on the body: vertices 0.3-3 cm below the top
            uv_d = np.array([D.vertices[v].uv for v in head_verts])
            band_f = is_face & (h > 0.3 / UNIT_CM) & (h < 3.0 / UNIT_CM)
            # T is already re-indexed here: these are current indices
            t_body_verts = oc.material_vertices(T, re.compile("^%s$" % re.escape(t_body[0])))
            tb_co = np.array([T.vertices[int(v)].co for v in t_body_verts])
            tb_h = (tb_co - tc) @ taxis - interp_ring(t_ang[t_order], ((t_pos_sorted - tc) @ taxis),
                                                      angle_of(tb_co, tc, taxis, tfront, tside))
            band_b = (tb_h < -0.3 / UNIT_CM) & (tb_h > -3.0 / UNIT_CM)
            uv_b = np.array([T.vertices[int(v)].uv for v in t_body_verts])
            if band_f.sum() >= 10 and band_b.sum() >= 10:
                mf_ = skin_mean(img_f, uv_d[band_f])
                mb_ = skin_mean(img_b, uv_b[band_b])
                gain = np.clip(mb_ / np.maximum(mf_, 1e-3), 0.5, 2.0)
                img_f[:, :, :3] *= gain
                report["tone_gain"] = [round(float(g), 3) for g in gain]
                log("  skin tone: face x %s (face band %s -> body band %s)" % (
                    np.round(gain, 3).tolist(), np.round(mf_, 3).tolist(), np.round(mb_, 3).tolist()))
                if tone == "seam":
                    # residual per ring vertex: body colour at the paired ring vertex / face colour at the donor vertex
                    res = {}
                    t_body_uv = {v: np.array(T.vertices[vmap[v]].uv) for v in t_ring if v in vmap}
                    for v in d_ring:
                        cf = skin_mean(img_f, uv_d[hv[v]][None], k=3)
                        # the paired target vertex: nearest ring vertex to pair_pos
                        kk = int(np.argmin(np.linalg.norm(co_t[t_ring] - pair_pos[v], axis=1)))
                        tv = t_ring[kk]
                        cb = skin_mean(img_b, t_body_uv[tv][None], k=3) if tv in t_body_uv else cf
                        res[v] = np.clip(cb / np.maximum(cf, 1e-3), 0.7, 1.4)
                    fac = np.ones((len(head_verts), 3))
                    ring_res = np.array([res[v] for v in d_ring])[d_order]
                    for k in np.where(w > 0)[0]:
                        fac[k] = 1 + (interp_ring(d_ang[d_order], ring_res, theta[k:k + 1])[0] - 1) * w[k]
                    tris_uv = [uv_d[[hv[v] for v in D.faces[f]]] for f in face_faces
                               if any(w[hv[v]] > 0 for v in D.faces[f])]
                    tri_fac = [fac[[hv[v] for v in D.faces[f]]] for f in face_faces
                               if any(w[hv[v]] > 0 for v in D.faces[f])]
                    img_f = rasterize_factor(img_f, tris_uv, tri_fac)
                    log("  seam gradient baked over %d triangles (residual %.2f..%.2f)" % (
                        len(tris_uv), ring_res.min(), ring_res.max()))
                base, ext = os.path.splitext(os.path.basename(face_tex_src))
                toned_path = os.path.join(tex_dir, "%s_toned.png" % base)
                write_image(toned_path, img_f)
            else:
                warn("skin tone: too few band vertices (face %d, body %d) - texture left alone" % (band_f.sum(), band_b.sum()))
        else:
            warn("skin tone: the body material has no texture file - texture left alone")

    n_uv = T.header.additional_uvs
    base_v = len(T.vertices)
    new_v = {}

    def add_vertex(v):
        if v in new_v:
            return new_v[v]
        k = hv[v]
        nv = copy.deepcopy(D.vertices[v])
        nv.co = [float(x) for x in P2[k]]
        nv.normal = [float(x) for x in N2[k]]
        wt = nv.weight
        if wt.type == pmx.BoneWeight.SDEF:
            for attr in ("c", "r0", "r1"):
                val = getattr(wt.weights, attr, None)
                if val is not None:
                    setattr(wt.weights, attr, [float(x) for x in place(np.array(val, float)[None])[0] + (P2[k] - P[k])])
        if isinstance(wt.bones, (list, tuple)):
            wt.bones = [map_bone(b) if b is not None and b >= 0 else b for b in wt.bones]
        if ring_of[k] >= 0:
            set_weights(pmx, nv, pair_w[ring_of[k]])
        elif w[k] > 0:
            j = int(np.argmin(np.abs(np.angle(np.exp(1j * (d_ang - theta[k]))))))
            set_weights(pmx, nv, blend_weights(oc.weights_of(pmx, nv), pair_w[d_ring[j]], float(w[k])))
        nv.additional_uvs = (list(nv.additional_uvs) + [[0.0, 0.0, 0.0, 0.0]] * n_uv)[:n_uv]
        new_v[v] = len(T.vertices)
        T.vertices.append(nv)
        return new_v[v]

    # split donor boundary edges where the target ring has vertices (different ring sampling only)
    split_faces = {}
    for a, b, t, v_t in splits:
        for f in face_faces:
            tri = D.faces[f]
            if a in tri and b in tri:
                split_faces.setdefault(f, []).append((a, b, t, v_t))
                break
    if splits:
        cut = sum(len(x) for x in split_faces.values())
        log("  %d of %d target ring vertices cut into the head's edge" % (cut, len(splits)))
        report["ring"]["cut_in"] = cut
    added_mats = []
    for mi in head_mi:
        mt = copy.deepcopy(D.materials[mi])
        faces_out = []
        for f in mfd[mi]:
            tri = D.faces[f]
            if f in split_faces:
                # cut the triangle along its boundary edge at every inserted point (fan from the opposite corner)
                pts = sorted(split_faces[f], key=lambda s: s[2])
                a, b = pts[0][0], pts[0][1]
                c = [x for x in tri if x not in (a, b)][0]
                chain = [add_vertex(a)]
                for (_a, _b, t, v_t) in pts:
                    ia, ib = add_vertex(a), add_vertex(b)
                    va, vb = T.vertices[ia], T.vertices[ib]
                    nv = copy.deepcopy(va)
                    nv.co = [float(x) for x in co_t[v_t]]
                    nv.normal = [float(x) for x in T.vertices[vmap[v_t]].normal] if v_t in vmap else va.normal
                    nv.uv = [va.uv[0] * (1 - t) + vb.uv[0] * t, va.uv[1] * (1 - t) + vb.uv[1] * t]
                    set_weights(pmx, nv, oc.weights_of(pmx, T.vertices[vmap[v_t]]) if v_t in vmap else
                                blend_weights(oc.weights_of(pmx, va), oc.weights_of(pmx, vb), t))
                    T.vertices.append(nv)
                    chain.append(len(T.vertices) - 1)
                chain.append(add_vertex(b))
                ic = add_vertex(c)
                # keep the winding of the original (a, b, c order as in tri)
                fwd = (tri.index(b) - tri.index(a)) % 3 == 1
                for u, v in zip(chain[:-1], chain[1:]):
                    faces_out.append((u, v, ic) if fwd else (v, u, ic))
            else:
                faces_out.append(tuple(add_vertex(v) for v in tri))
        T.faces.extend(faces_out)
        mt.vertex_count = 3 * len(faces_out)
        for attr in ("texture", "sphere_texture") + (() if mt.is_shared_toon_texture else ("toon_texture",)):
            ti = getattr(mt, attr)
            if ti is None or ti < 0:
                continue
            src = D.textures[ti].path
            if attr == "texture" and mi in face_mi and toned_path:
                src = toned_path
            setattr(mt, attr, texture(src) if os.path.isfile(src) else -1)
        if mt.name in {m.name for m in T.materials}:
            mt.name = "%s_%s" % (prefix, mt.name)
        T.materials.append(mt)
        added_mats.append(mt.name)
    report["materials_added"] = added_mats
    log("materials: %s" % ", ".join(added_mats))

    # -- the donor's morphs on the head (expressions): same names replace the target's -------------------------------
    t_names = {mo.name: i for i, mo in enumerate(T.morphs)}
    added, replaced = 0, 0
    donor_morph_index = {}
    for mi, mo in enumerate(D.morphs):
        offs = mo.offsets
        if not offs:
            continue
        nm = copy.deepcopy(mo)
        if hasattr(offs[0], "index") and hasattr(offs[0], "offset"):
            nm.offsets = [o for o in nm.offsets if o.index in new_v]
            for o in nm.offsets:
                o.index = new_v[o.index]
        elif hasattr(offs[0], "offset_type"):
            continue                                   # material morphs: the donor's material indices mean nothing here
        elif hasattr(offs[0], "morph"):
            nm.offsets = [o for o in nm.offsets if o.morph in donor_morph_index]
            for o in nm.offsets:
                o.morph = donor_morph_index[o.morph]
        elif hasattr(offs[0], "location"):             # bone morph
            nm.offsets = [o for o in nm.offsets if o.index in bmap or o.index in new_index]
            for o in nm.offsets:
                o.index = map_bone(o.index)
        if not nm.offsets:
            continue
        if nm.name in t_names:
            T.morphs[t_names[nm.name]] = nm
            donor_morph_index[mi] = t_names[nm.name]
            replaced += 1
        else:
            donor_morph_index[mi] = len(T.morphs)
            T.morphs.append(nm)
            t_names[nm.name] = donor_morph_index[mi]
            added += 1
    facial = next((fr for fr in T.display if fr.name == "表情"), None)
    if facial is not None:
        listed = {i for k, i in facial.data if k == 1}
        facial.data.extend((1, i) for i in sorted(donor_morph_index.values()) if i not in listed)
    log("morphs: %d of the target's went with the old head, %d of the donor's added, %d replaced same-named ones" % (
        removed_morphs, added, replaced))

    # -- display frame for the new bones ----------------------------------------------------------------------------
    if bring:
        fr = pmx.Display()
        fr.name = fr.name_e = "%s头" % prefix
        fr.data = [(0, new_index[i]) for i in bring]
        T.display.append(fr)

    # -- physics: the donor's hair chains -----------------------------------------------------------------------------
    t_body_on_bone = {}
    for i, r in enumerate(T.rigids):
        if r.bone is not None and r.bone >= 0:
            t_body_on_bone.setdefault(r.bone, i)
    bring_set = set(bring)
    d_rig = [(i, r) for i, r in enumerate(D.rigids) if r.bone is not None and r.bone in bring_set]
    rmap2 = {}
    for i, r in d_rig:
        nr = copy.deepcopy(r)
        nr.bone = new_index[r.bone]
        nr.location = [float(x) for x in place(np.array(r.location)[None])[0]]
        nr.rotation = oc.euler_of(R @ oc.rot_matrix(r.rotation))
        nr.size = [float(x) * S for x in r.size]
        if nr.name in {x.name for x in T.rigids}:
            nr.name = "%s:%s" % (prefix, nr.name)
        rmap2[i] = len(T.rigids)
        T.rigids.append(nr)
    j_added = j_dropped = 0
    for j in D.joints:
        if j.src_rigid not in rmap2 and j.dest_rigid not in rmap2:
            continue

        def end(x):
            if x in rmap2:
                return rmap2[x]
            r = D.rigids[x]
            if r.bone is None or r.bone < 0:
                return None
            tb = map_bone(r.bone)
            while tb is not None and tb >= 0:
                if tb in t_body_on_bone:
                    return t_body_on_bone[tb]
                tb = T.bones[tb].parent
            return None
        a, b = end(j.src_rigid), end(j.dest_rigid)
        if a is None or b is None:
            j_dropped += 1
            continue
        nj = copy.deepcopy(j)
        nj.src_rigid, nj.dest_rigid = a, b
        nj.location = [float(x) for x in place(np.array(j.location)[None])[0]]
        nj.rotation = oc.euler_of(R @ oc.rot_matrix(j.rotation))
        T.joints.append(nj)
        j_added += 1
    log("physics: %d rigid bodies, %d joints (%d dropped)" % (len(rmap2), j_added, j_dropped))
    if rmap2:
        report["groups"] = oc.isolate_groups(T, set(rmap2.values()), D, [i for i, _r in d_rig], True, log)

    # -- save -------------------------------------------------------------------------------------------------------
    T.name = T.name_e = os.path.splitext(os.path.basename(out_path))[0]
    T.comment = (T.comment or "").rstrip() + "\r\n%s's head (%s) by pmx_head_swap" % (prefix, os.path.basename(donor_path))
    pmx.save(out_path, T, add_uv_count=n_uv)
    back = pmx.load(out_path)
    missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
    report.update({"out": out_path, "vertices": len(back.vertices), "materials": len(back.materials),
                   "bones": len(back.bones), "rigids": len(back.rigids), "joints": len(back.joints),
                   "morphs": len(back.morphs), "textures_missing": missing, "bones_added": len(bring),
                   "rigids_added": len(rmap2), "joints_added": j_added, "vertices_removed": removed_verts})
    log("wrote %s: %d vertices, %d materials, %d bones, %d rigids, %d joints, %d morphs%s" % (
        out_path, len(back.vertices), len(back.materials), len(back.bones), len(back.rigids), len(back.joints),
        len(back.morphs), "; textures missing %s" % missing if missing else ""))
    return report
