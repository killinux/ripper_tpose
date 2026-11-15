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


COLLAR_MIN_CM = 0.5      # the body material rising this far above the ring around the neck = a collar
COLLAR_REACH_CM = 2.5    # ... counted within this distance outside the ring
COLLAR_MARGIN_CM = 0.3   # the old neck's shape is kept this far above the collar's rim
COLLAR_FADE_CM = 2.0     # ... and fades back to the new neck's own shape over this much


def _ray_triangles(o, d, A, E1, E2):
    """First crossing (t > 0) of the ray o + t d with the triangles (A, A + E1, A + E2): (t, triangle, u, v) or None."""
    p = np.cross(d, E2)
    det = (E1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = o - A
    u = (s * p).sum(1) * inv
    q = np.cross(s, E1)
    v = (q @ d) * inv
    t = (E2 * q).sum(1) * inv
    m = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 1e-6)
    if not m.any():
        return None
    k = np.where(m)[0][np.argmin(t[m])]
    return t[k], k, u[k], v[k]


def collar_fit(T, ring_mat, remove_mats, t_ring, co_t, frame, P2, is_face, log):
    """A neck ring inside a collar (Stellar Blade's turtleneck: the head meets the suit 3-4 cm under the visible rim)
    lets a thicker new neck poke out through the collar above the ring.  There the new neck takes the target's OLD
    neck shape (the removed material whose open edge is the ring - it fitted inside the collar): per vertex the radius
    of the old neck at its angle and height, up to the collar's rim + COLLAR_MARGIN_CM, fading back to its own over
    COLLAR_FADE_CM.  Returns (P2, w, normals of the old neck there, report); without a collar w is all 0."""
    tc, taxis, tfront, tside = frame
    w = np.zeros(len(P2))
    n_t = np.zeros_like(P2)
    r_ang = angle_of(co_t[t_ring], tc, taxis, tfront, tside)
    o = np.argsort(r_ang)
    ang_s = r_ang[o]
    rel = co_t[t_ring] - tc
    r_h = (rel @ taxis)[o]
    r_r = np.linalg.norm(rel - np.outer(rel @ taxis, taxis), axis=1)[o]
    mf = oc.material_faces(T)
    names = [mt.name for mt in T.materials]
    # the collar's rim: how far the ring material rises above the ring close round the neck, per 10-degree sector
    bv = sorted({v for f in mf[names.index(ring_mat)] for v in T.faces[f]})
    Q = co_t[bv]
    qa = angle_of(Q, tc, taxis, tfront, tside)
    qrel = Q - tc
    qh = qrel @ taxis - interp_ring(ang_s, r_h, qa)
    qr = np.linalg.norm(qrel - np.outer(qrel @ taxis, taxis), axis=1) - interp_ring(ang_s, r_r, qa)
    close = (qr < COLLAR_REACH_CM / UNIT_CM) & (qh > 0)
    bins = 36
    rim = np.zeros(bins)
    if close.any():
        kb = ((qa[close] + np.pi) / (2 * np.pi) * bins).astype(int) % bins
        np.maximum.at(rim, kb, qh[close])
    rim = np.maximum(rim, np.maximum(np.roll(rim, 1), np.roll(rim, -1)))     # a sector's rim also covers its edges
    if rim.max() * UNIT_CM < COLLAR_MIN_CM:
        return P2, w, n_t, None
    # the old neck: the removed material whose open edge runs along the ring (Eve's head edge lies 2 mm under the
    # suit's, not on it: within 8 mm all round)
    ring_pts = co_t[t_ring]
    old = None
    for n in remove_mats:
        if n not in names:
            continue
        loops, _canon = boundary_loops(T, [n], co_t)
        for l in loops:
            if len(l) >= 12 and np.mean([np.linalg.norm(ring_pts - co_t[v], axis=1).min() * UNIT_CM < 0.8
                                         for v in l]) > 0.9:
                old = n
        if old:
            break
    if old is None:
        log("  collar: rim %.1f cm above the ring, but no removed material ends at the ring - neck left as is" % (
            rim.max() * UNIT_CM))
        return P2, w, n_t, {"rim_cm": round(float(rim.max() * UNIT_CM), 2), "fitted": 0}
    tris = np.array([T.faces[f] for f in mf[names.index(old)]], np.int64)
    cen = co_t[tris].mean(1) - tc
    top = (rim.max() + (COLLAR_MARGIN_CM + COLLAR_FADE_CM + 1.0) / UNIT_CM) + r_h.max()
    keep = (cen @ taxis > r_h.min() - 1.0 / UNIT_CM) & (cen @ taxis < top)
    tris = tris[keep]
    A = co_t[tris[:, 0]]
    E1, E2 = co_t[tris[:, 1]] - A, co_t[tris[:, 2]] - A
    NT = np.array([T.vertices[v].normal for v in range(len(T.vertices))], float)
    # the new neck's vertices: height above the ring at their angle, against the rim there
    pa = angle_of(P2, tc, taxis, tfront, tside)
    prel = P2 - tc
    axial = prel @ taxis
    ph = axial - interp_ring(ang_s, r_h, pa)
    prim = rim[((pa + np.pi) / (2 * np.pi) * bins).astype(int) % bins]
    reach = prim + COLLAR_MARGIN_CM / UNIT_CM
    want = is_face & (ph > 0) & (ph < reach + COLLAR_FADE_CM / UNIT_CM)
    out = P2.copy()
    moved = []
    for k in np.where(want)[0]:
        base = tc + taxis * axial[k]
        d = P2[k] - base
        r = np.linalg.norm(d)
        if r < 1e-9:
            continue
        d /= r
        hit = _ray_triangles(base, d, A, E1, E2)
        if hit is None:
            continue
        t, j, u, v = hit
        wk = 1.0 if ph[k] <= reach[k] else float(smoothstep(1.0 - (ph[k] - reach[k]) / (COLLAR_FADE_CM / UNIT_CM)))
        out[k] = base + d * (r + (t - r) * wk)
        a_, b_, c_ = tris[j]
        nn = NT[a_] * (1 - u - v) + NT[b_] * u + NT[c_] * v
        n_t[k] = nn / (np.linalg.norm(nn) + 1e-12)
        w[k] = wk
        moved.append(abs(t - r))
    rep = {"rim_cm": [round(float(rim.min() * UNIT_CM), 2), round(float(rim.max() * UNIT_CM), 2)], "old_neck": old,
           "fitted": len(moved), "max_move_cm": round(float(max(moved) * UNIT_CM), 2) if moved else 0.0}
    log("  collar: the ring sits %.1f-%.1f cm under the collar's rim; %d neck vertices take the old neck's (%s) shape "
        "up to it (moved %.2f cm at most)" % (rep["rim_cm"][0], rep["rim_cm"][1], rep["fitted"], old,
                                             rep["max_move_cm"]))
    return out, w, n_t, rep


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


# -- a donor whose face is only a mask: cut its neck out of the body material ------------------------------------------
def _eye_centre(M):
    names = [b.name for b in M.bones]
    if "左目" in names and "右目" in names:
        return (np.array(M.bones[names.index("左目")].location, float) +
                np.array(M.bones[names.index("右目")].location, float)) / 2
    return np.array(M.bones[names.index("頭")].location, float)


def _neck_path(D, mi, c, n, axis=None, centre=None, band_cm=1.5, alpha=4.0, min_step_deg=0.5):
    """Faces of material mi above a closed EDGE PATH once round the neck near the plane (c, n): a shortest path in
    the graph of edges whose angle about ``axis`` (from ``centre``) grows by min_step_deg..30 degrees, edges near the
    plane cheaper - so the cut follows the mesh, has no zigzag folds, and its order by angle is its order along the
    edge (what the ring pairing needs).  UV-seam twins count as one vertex."""
    co = np.array([v.co for v in D.vertices], float)
    faces = oc.material_faces(D)[mi]
    keys, cid = {}, {}
    for f in faces:
        for v in D.faces[f]:
            if v not in cid:
                cid[v] = keys.setdefault(tuple(np.round(co[v], 4)), len(keys))
    pos = np.zeros((len(keys), 3))
    for v, k in cid.items():
        pos[k] = co[v]
    edges, face_edges = defaultdict(set), []
    for f in faces:
        a, b, cc = (cid[v] for v in D.faces[f])
        fe = []
        for x, y in ((a, b), (b, cc), (cc, a)):
            if x != y:
                edges[x].add(y)
                edges[y].add(x)
                fe.append((min(x, y), max(x, y)))
        face_edges.append(fe)
    d = (pos - c) @ n * UNIT_CM                          # cm above the plane
    ax = n if axis is None else axis / np.linalg.norm(axis)
    o = c if centre is None else centre
    e1 = np.array([0.0, 0.0, -1.0]) - (np.array([0.0, 0.0, -1.0]) @ ax) * ax
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax, e1)
    theta = np.arctan2((pos - o) @ e2, (pos - o) @ e1)
    radial = np.linalg.norm((pos - c) - np.outer((pos - c) @ n, n), axis=1) * UNIT_CM
    region = np.where((np.abs(d) < band_cm) & (radial < 9.0))[0]
    in_region = np.zeros(len(pos), bool)
    in_region[region] = True
    near_front = [k for k in region if abs(theta[k]) < np.radians(8)]
    if not near_front:
        raise RuntimeError("neck cut: no %s vertices near the cut plane in front" % D.materials[mi].name)
    s = min(near_front, key=lambda k: abs(d[k]))
    phi = np.mod(theta - theta[s], 2 * np.pi)
    dist, prev = {k: np.inf for k in region}, {}
    dist[s] = 0.0
    best, last = np.inf, None

    def cost(u, w):
        return np.linalg.norm(pos[u] - pos[w]) * UNIT_CM * (1.0 + alpha * (abs(d[u]) + abs(d[w])) / 2)
    for u in sorted(region, key=lambda k: phi[k]):
        if not np.isfinite(dist[u]):
            continue
        for w in edges[u]:
            if w == s:
                if phi[u] > 1.5 * np.pi and dist[u] + cost(u, w) < best:
                    best, last = dist[u] + cost(u, w), u
                continue
            if in_region[w] and np.radians(min_step_deg) < phi[w] - phi[u] < np.pi / 6 \
                    and dist[u] + cost(u, w) < dist[w]:
                dist[w], prev[w] = dist[u] + cost(u, w), u
    if last is None:
        raise RuntimeError("neck cut: no edge path once round the neck in %s" % D.materials[mi].name)
    path = [last]
    while path[-1] != s:
        path.append(prev[path[-1]])
    cut = {(min(x, y), max(x, y)) for x, y in zip(path, path[-1:] + path[:-1])}
    by_edge = defaultdict(list)
    for fi, fe in enumerate(face_edges):
        for e in fe:
            by_edge[e].append(fi)
    top = int(np.argmax([co[list(D.faces[f])].mean(0) @ n for f in faces]))
    seen, stack = {top}, [top]
    while stack:
        fi = stack.pop()
        for e in face_edges[fi]:
            if e not in cut:
                for g in by_edge[e]:
                    if g not in seen:
                        seen.add(g)
                        stack.append(g)
    return sorted(faces[fi] for fi in seen), {"path_vertices": len(path),
                                              "path_off_plane_cm": [round(float(d[path].min()), 2),
                                                                    round(float(d[path].max()), 2)]}


def _split_material(D, mi, part_faces, new_name):
    """The faces part_faces of material mi become a copy of it right after it (drawn where it was, before the hair);
    material morph indices after it shift by one."""
    mf = oc.material_faces(D)
    part = set(part_faces)
    faces = []
    for i, mt in enumerate(D.materials):
        if i == mi:
            rest = [D.faces[f] for f in mf[i] if f not in part]
            faces.extend(rest)
            faces.extend(D.faces[f] for f in part_faces)
            mt.vertex_count = 3 * len(rest)
        else:
            faces.extend(D.faces[f] for f in mf[i])
    nm = copy.deepcopy(D.materials[mi])
    nm.name = nm.name_e = new_name
    nm.vertex_count = 3 * len(part_faces)
    D.faces = faces
    D.materials.insert(mi + 1, nm)
    for mo in D.morphs:
        for o in mo.offsets:
            if hasattr(o, "offset_type") and o.index is not None and o.index > mi:
                o.index += 1
    return nm


def cut_donor_neck(D, ring_pts, eye_t, neck_from, log=print):
    """A donor whose face is only a mask (Genesis 8 / Daz: the neck and the back of the head are in the body
    material) has no neck ring of its own.  Cut ``neck_from`` once round the neck along mesh edges where the target's
    neck ring would sit on it - the target's ring moved by the eye-centre offset (both heads level at the eyes, so the
    head keeps the target's neck length) - and the part above becomes "<neck_from>_head": the face material of the
    swap (in place on D; returns its name and a report)."""
    names = [mt.name for mt in D.materials]
    if neck_from not in names:
        raise RuntimeError("neck cut: no material %s in the donor" % neck_from)
    mi = names.index(neck_from)
    P = ring_pts + (_eye_centre(D) - eye_t)
    c = P.mean(0)
    _u, _s, vt = np.linalg.svd(P - c)
    n = vt[2] if vt[2][1] > 0 else -vt[2]                 # the plane's normal points up the neck
    head_bone = np.array(D.bones[[b.name for b in D.bones].index("頭")].location, float)
    neck_bone = np.array(D.bones[[b.name for b in D.bones].index("首")].location, float)
    # pass 1 orders by angle about the plane's normal; pass 2 about ring centre -> 頭, as the ring pairing does
    faces, rep = _neck_path(D, mi, c, n)
    Dt = copy.deepcopy(D)
    nm = _split_material(Dt, mi, faces, neck_from + "_head")
    cot = np.array([v.co for v in Dt.vertices], float)
    loops, _canon = boundary_loops(Dt, [nm.name], cot)
    loops = [l for l in loops if len(l) >= 12 and np.linalg.norm(cot[l].mean(0) - neck_bone) < 1.2]
    if loops:
        rc = cot[max(loops, key=len)].mean(0)
        faces, rep = _neck_path(D, mi, c, n, axis=head_bone - rc, centre=rc)
    nm = _split_material(D, mi, faces, neck_from + "_head")
    rep.update({"material": nm.name, "faces": len(faces),
                "tilt_deg": round(float(np.degrees(np.arccos(np.clip(n[1], -1, 1)))), 1)})
    log("neck cut: %s cut once round the neck at the target's ring height (tilt %.1f deg, %d edges, %.2f..%.2f cm off "
        "the plane) - %d faces above it are %s" % (neck_from, rep["tilt_deg"], rep["path_vertices"],
                                                   rep["path_off_plane_cm"][0], rep["path_off_plane_cm"][1],
                                                   len(faces), nm.name))
    return nm.name, rep


# -- the swap ---------------------------------------------------------------------------------------------------------
def swap_head(donor_path, target_path, out_path, head_materials=None, remove_materials=None, blend_cm=4.0,
              tone="seam", scale=1.0, prefix=None, face=None, body=None, neck_from=None, log=print):
    """face: the donor's face material (the one whose open edge is the neck ring; default: by name, else the first
    head material); body: the target's body material(s), comma-separated (default ROE *_nk_body, else the outfit
    transfer's body guess - another game's model); neck_from: a donor whose face is only a mask - the material that
    holds its neck (Genesis 8: Body), cut at the target's ring height and used as the face (cut_donor_neck)."""
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
    if face_mat is None and not neck_from:
        raise RuntimeError("no face material among %s" % head_mats)
    t_body = [n.strip() for n in body.split(",") if n.strip()] if body else body_materials(T)
    if not t_body and oc.auto_body(T, nude=False):
        t_body = [oc.auto_body(T, nude=False)]           # another game: SkinEve, *-body05 ...
    if not t_body:
        raise RuntimeError("no body material in the target (ROE *_nk_body; else name it: body=...)")

    co_t = np.array([v.co for v in T.vertices], float)
    d_neck, d_head = np.array(D.bones[dn.index("首")].location), np.array(D.bones[dn.index("頭")].location)
    t_neck, t_head = np.array(T.bones[tidx["首"]].location), np.array(T.bones[tidx["頭"]].location)

    # -- rings ------------------------------------------------------------------------------------------------------
    t_face = [n for n in remove_mats if FACE_MAT.search(n) and not n.endswith("_nude")]
    near = None
    if t_face:
        try:
            near = co_t[neck_ring(T, t_face[:1], co_t, t_neck, log)]
        except RuntimeError:
            near = None
    t_ring = neck_ring(T, t_body[:1], co_t, t_neck, log, near=near)
    if neck_from:
        # a face that is only a mask: the neck is cut out of the material that holds it, at the target's ring height
        face_mat, report["neck_cut"] = cut_donor_neck(D, co_t[t_ring], _eye_centre(T), neck_from, log)
        head_mats = [face_mat] + [n for n in head_mats if n != face_mat]
    log("head: %s (face %s); removed from the target: %s; body ring on %s" % (
        ", ".join(head_mats), face_mat, ", ".join(remove_mats) or "-", t_body[0]))
    co_d = np.array([v.co for v in D.vertices], float)
    d_ring = neck_ring(D, [face_mat], co_d, d_neck, log)
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
    # a ring inside a collar: the new neck takes the old neck's shape up to the collar's rim (nothing without a collar)
    P2, w_collar, n_collar, rep_collar = collar_fit(T, t_body[0], remove_mats, t_ring, co_t,
                                                    (tc, taxis, tfront, tside), P2, is_face & ~on_ring, log)
    if rep_collar:
        report["collar"] = rep_collar

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
    fitted = w_collar > 0                              # in the collar: the old neck's normals, fading out with the shape
    N2[fitted] = N2[fitted] * (1 - w_collar[fitted, None]) + n_collar[fitted] * w_collar[fitted, None]
    N2 /= np.linalg.norm(N2, axis=1, keepdims=True) + 1e-12

    # -- bones: map the donor's to the target's (name / position / bring), head-subtree bones take the donor's places --
    head_bone_set = set()
    for v in head_verts:
        for b, x in oc.weights_of(pmx, D.vertices[v]):
            if x >= 0.3:
                head_bone_set.add(b)
    tr = oc.Transfer(pmx, D, T, log)
    # under the donor's 頭 also the bones with small head weights only (Tifa's eyelid helpers QQ6, < 0.3) and the bones
    # its bone morphs move: the expressions keep every bone they had
    d_head_sub, stack = set(), [dn.index("頭")]
    while stack:
        for c in tr.kids_d[stack.pop()]:
            d_head_sub.add(c)
            stack.append(c)
    for v in head_verts:
        for b, x in oc.weights_of(pmx, D.vertices[v]):
            if b in d_head_sub:
                head_bone_set.add(b)
    morph_bones = {o.index for mo in D.morphs for o in mo.offsets if hasattr(o, "location_offset")}
    head_bone_set |= morph_bones & d_head_sub
    stack = list(head_bone_set)
    while stack:
        k = stack.pop()
        for c in tr.kids_d[k]:
            if c in tr.d_dyn and c not in head_bone_set:
                head_bone_set.add(c)
                stack.append(c)
    bmap, bring = tr.map_bones(head_bone_set)
    # the outfit rule also matches bones BY POSITION under a matched parent (ROE a08's lip / brow bones onto g05's,
    # 0.4-1.5 cm); a bone the donor's BONE morphs move stays the donor's own, though - its expressions were made with
    # its name and axes (Tifa's Jaw Bone would have become Eve's Hair_Root, 3.2 cm off)
    pos_only = [i for i in bmap if i in d_head_sub and i in morph_bones and dn[i] != tn[bmap[i]]]
    if pos_only:
        for i in pos_only:
            del bmap[i]
        bring = set()
        for i in head_bone_set:
            j = i
            while j is not None and j >= 0 and j not in bmap and j not in bring:
                bring.add(j)
                j = D.bones[j].parent
        bring = sorted(bring)
        tr.bmap, tr.bring = bmap, bring
        log("  %d head bones the outfit rule paired by position come along as the donor's own (%s)" % (
            len(pos_only), ", ".join(dn[i] for i in pos_only[:5]) + (" ..." if len(pos_only) > 5 else "")))
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

    # split donor boundary edges where the target ring has vertices (different ring sampling only).  The ring keeps one
    # vertex per position; the face may use its UV-seam twin (Genesis 8 necks: 41 of 101), so match by position
    split_faces = {}
    if splits:
        def pkey(v):
            return tuple(np.round(co_d[v], 4))
        faces_at = defaultdict(list)
        for f in face_faces:
            for v in D.faces[f]:
                faces_at[pkey(v)].append(f)
        for a, b, t, v_t in splits:
            ka, kb = pkey(a), pkey(b)
            for f in faces_at[ka]:
                tri = D.faces[f]
                ta = [x for x in tri if pkey(x) == ka]
                tb = [x for x in tri if pkey(x) == kb]
                if ta and tb:
                    if any((e[0], e[1]) != (ta[0], tb[0]) for e in split_faces.get(f, [])):
                        warn("a head face has target ring vertices on two of its edges - only the first is cut")
                    split_faces.setdefault(f, []).append((ta[0], tb[0], t, v_t))
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
        elif hasattr(offs[0], "location_offset"):      # bone morph (mmd_tools: location_offset / rotation_offset)
            # bones of the head (matched or brought along); a bone without head weights (両目) by its name
            nm.offsets = [o for o in nm.offsets if o.index in bmap or o.index in new_index or
                          (0 <= o.index < len(dn) and dn[o.index] in tidx)]
            for o in nm.offsets:
                o.index = map_bone(o.index) if (o.index in bmap or o.index in new_index) else tidx[dn[o.index]]
                # the head was turned by R and scaled by S: the offsets (model axes) turn with it - a quaternion's
                # vector part turns with R, its scalar part stays
                o.location_offset = [float(x) for x in (R @ np.asarray(o.location_offset, float)) * S]
                q = np.asarray(o.rotation_offset, float)
                o.rotation_offset = [float(x) for x in R @ q[:3]] + [float(q[3])]
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

    # -- head colliders: the donor's static bodies on 頭 replace the target's - the head has the donor's shape now (Eve's
    # sphere, r 6.1 cm about her jaw, left Tifa's forehead and the second segments of her bangs 7-8 cm outside it) ------
    d_head_i, t_head_i = dn.index("頭"), tidx["頭"]
    d_head_col = [r for r in D.rigids if r.mode == 0 and r.bone == d_head_i]
    t_head_col = {i for i, r in enumerate(T.rigids) if r.mode == 0 and r.bone == t_head_i}
    if d_head_col and t_head_col:
        tmpl = T.rigids[min(t_head_col)]
        keep = [i for i in range(len(T.rigids)) if i not in t_head_col]
        rmap_h = {old: k for k, old in enumerate(keep)}
        T.rigids = [T.rigids[i] for i in keep]
        T.joints = [j for j in T.joints if j.src_rigid in rmap_h and j.dest_rigid in rmap_h]
        for j in T.joints:
            j.src_rigid, j.dest_rigid = rmap_h[j.src_rigid], rmap_h[j.dest_rigid]
        for r in d_head_col:
            nr = copy.deepcopy(r)
            nr.bone = t_head_i
            nr.location = [float(x) for x in place(np.array(r.location)[None])[0]]
            nr.rotation = oc.euler_of(R @ oc.rot_matrix(r.rotation))
            nr.size = [float(x) * S for x in r.size]
            nr.collision_group_number = tmpl.collision_group_number      # collide as the target's head did
            nr.collision_group_mask = tmpl.collision_group_mask
            if nr.name in {x.name for x in T.rigids}:
                nr.name = "%s:%s" % (prefix, nr.name)
            T.rigids.append(nr)
        report["head_colliders"] = {"removed": len(t_head_col), "added": len(d_head_col),
                                    "group": tmpl.collision_group_number}
        log("head colliders: the target's %d on 頭 replaced by the donor's %d (group %d, as the target's)" % (
            len(t_head_col), len(d_head_col), tmpl.collision_group_number))

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
