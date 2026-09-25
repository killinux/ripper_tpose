"""Fit VaM's Genesis 2 female head to another character's face: a head morph + a face texture.

Used by bring_to_vam.py.  Steps:

1. **Landmarks** on both heads, found the same way on each: eye corners, eye centres, nose tip,
   nose bridge, nostrils, mouth corners, upper / lower lip, chin, forehead, head top, back of the
   head, cheekbones, ears.  On G2F they come from its material islands (Lacrimals = inner eye
   corner, Tear = lower lid from inner to outer corner, Lips, Nostrils, Ears, Sclera); on the
   source from its eyeball / lacrimal parts and, where it has them, facial bones.
2. **Similarity** (scale, rotation, translation) carrying the source head onto G2F's -- VaM's
   head size is kept, the source only lends its shape.
3. **Thin-plate spline** from the G2F landmarks to the transformed source landmarks, applied to
   the whole head (faded out down the neck).
4. **Surface refinement**: skin vertices are pulled onto the source skin (closest point), the
   pull smoothed over the G2F mesh and applied in a few rounds -- after the spline the
   correspondence is already right, so this no longer shears the nose away the way plain
   nearest-point projection did (docs: README section 8).
5. The eyeballs move rigidly to the source's eye centres (VaM rotates them about their bones).

The result is the G2F head's new vertex positions; the morph is (fitted - base).
"""
import numpy as np

import vam_items as vi
import vam_lib as vl

HEAD_MATERIALS = ("Face", "Lips", "Nostrils", "Head", "Ears")
EYE_MATERIALS = ("Sclera", "Irises", "Pupils", "Cornea", "EyeReflection")
# parts that ride on the skin and must follow the surface pull, not just the spline: without it the
# lashes ended up to 4 mm off the lid margins and the mouth inside up to 8 mm off the lips
ATTACHED_MATERIALS = ("Eyelashes", "Tear", "Lacrimals", "Teeth", "Gums", "Tongue", "InnerMouth", "Ears")
# skin pulled onto the source surface.  Not the ears: an ear's folds have no counterpart in another
# character's ear, and projecting them crumpled G2F's ear (edges stretched 11x, 21 triangles
# turned over) -- the ears keep their shape and ride along with the skin around them
REFINE_MATERIALS = ("Face", "Lips", "Nostrils", "Head")
# a closest-point pair is only trusted where both surfaces face the same way (cos >= this):
# otherwise the inner lip is pulled onto the outer one and the lips fold over
FACING_MIN = 0.5


# ----------------------------------------------------------------------------- mesh helpers

def material_vertices(poly_len, poly_idx, poly_mat, mat_ids):
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    polys = np.nonzero(np.isin(poly_mat, list(mat_ids)))[0]
    if not len(polys):
        return np.zeros(0, dtype=np.int64)
    return np.unique(np.concatenate([poly_idx[starts[p]:starts[p] + poly_len[p]] for p in polys]))


def triangulate(poly_len, poly_idx, poly_mask=None):
    poly_len = np.asarray(poly_len)
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    out = []
    for n in (3, 4):
        sel = np.nonzero((poly_len == n) & (poly_mask if poly_mask is not None else True))[0]
        if not len(sel):
            continue
        q = np.asarray(poly_idx)[starts[sel][:, None] + np.arange(n)[None, :]]
        out.append(q[:, [0, 1, 2]])
        if n == 4:
            out.append(q[:, [0, 2, 3]])
    return np.concatenate(out) if out else np.zeros((0, 3), dtype=np.int64)


def closest_points(points, verts, tris):
    """Closest point on a triangle mesh + the triangle and its barycentric coordinates."""
    # only the triangles' own vertices go into the search grid: a vertex without triangles
    # (an eyelash next to the skin) would win the nearest-vertex step and leave the point unmatched
    used = np.unique(tris)
    remap = np.full(len(verts), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    cverts, ctris = verts[used], remap[tris]
    # a face mesh is dense: the body's 3 cm grid cell would hold ~160 of its vertices.  1.5 median
    # edges per cell matched a 64-candidate brute force on 100k texels of Fiona's face exactly
    # (1.0 did not: 341 misses); 4 edges was exact too but 4x slower
    edge = np.linalg.norm(cverts[ctris[:, 0]] - cverts[ctris[:, 1]], axis=1)
    cell = float(np.clip(1.5 * np.median(edge), 0.003, 0.03))
    idx = vi.closest_triangles(points, ctris, cverts, cell=cell, max_grid_distance=0.8 * cell)
    tv = tris[idx]
    a, b, c = verts[tv[:, 0]], verts[tv[:, 1]], verts[tv[:, 2]]
    q = _closest_on_triangle(points, a, b, c)
    bary = _barycentric(q, a, b, c)
    return q, idx, bary


def _closest_on_triangle(p, a, b, c):
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-30, 1e-30, den)
    out = a + ab * (vb / den)[:, None] + ac * (vc / den)[:, None]
    m = (d1 <= 0) & (d2 <= 0); out[m] = a[m]
    m = (d3 >= 0) & (d4 <= d3); out[m] = b[m]
    m = (d6 >= 0) & (d5 <= d6); out[m] = c[m]
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(np.abs(d1 - d3) < 1e-30, 1e-30, d1 - d3); out[m] = (a + ab * t[:, None])[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(np.abs(d2 - d6) < 1e-30, 1e-30, d2 - d6); out[m] = (a + ac * t[:, None])[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    den2 = (d4 - d3) + (d5 - d6)
    t = (d4 - d3) / np.where(np.abs(den2) < 1e-30, 1e-30, den2); out[m] = (b + (c - b) * t[:, None])[m]
    return out


def _barycentric(q, a, b, c):
    v0, v1, v2 = b - a, c - a, q - a
    d00 = np.einsum("ij,ij->i", v0, v0); d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1); d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-30, 1e-30, d00 * d11 - d01 * d01)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.stack([1 - v - w, v, w], axis=1)


# ----------------------------------------------------------------------------- landmarks

def _front_point(pts, x_tol, y_lo, y_hi):
    """Most forward (+Z) point of the midline strip |x| < x_tol, y_lo <= y <= y_hi."""
    sel = (np.abs(pts[:, 0]) < x_tol) & (pts[:, 1] >= y_lo) & (pts[:, 1] <= y_hi)
    s = pts[sel]
    return s[np.argmax(s[:, 2])]


def geometric_landmarks(skin, eye_l, eye_r, mouth_l, mouth_r):
    """Landmarks defined on skin geometry alone, given eye centres and mouth corners."""
    eye_y = 0.5 * (eye_l[1] + eye_r[1])
    mouth_y = 0.5 * (mouth_l[1] + mouth_r[1])
    span = eye_y - mouth_y                           # eye-to-mouth height sets every other band
    lm = {}
    lm["nasion"] = _front_point(skin, 0.004, eye_y - 0.05 * span, eye_y + 0.05 * span)
    lm["nose_tip"] = _front_point(skin, 0.004, mouth_y + 0.35 * span, eye_y - 0.2 * span)
    tip = lm["nose_tip"]
    wing = skin[(np.abs(skin[:, 1] - (tip[1] - 0.12 * span)) < 0.08 * span) & (skin[:, 2] > tip[2] - 0.35 * span)
                & (np.abs(skin[:, 0]) < 0.5 * span)]
    lm["ala_l"] = wing[np.argmin(wing[:, 0])]
    lm["ala_r"] = wing[np.argmax(wing[:, 0])]
    lm["upper_lip"] = _front_point(skin, 0.003, mouth_y + 0.02 * span, mouth_y + 0.25 * span)
    lm["lower_lip"] = _front_point(skin, 0.003, mouth_y - 0.3 * span, mouth_y - 0.02 * span)
    lm["chin"] = _front_point(skin, 0.004, mouth_y - 0.9 * span, mouth_y - 0.45 * span)
    lm["forehead"] = _front_point(skin, 0.004, eye_y + 0.6 * span, eye_y + 0.9 * span)
    lm["head_top"] = skin[np.argmax(skin[:, 1])]
    # the back of a head is sparsely meshed: take the deepest midline point over a tall band
    band = skin[(np.abs(skin[:, 0]) < 0.02) & (skin[:, 1] > eye_y - 0.1 * span) & (skin[:, 1] < eye_y + 0.8 * span)]
    lm["head_back"] = band[np.argmin(band[:, 2])]
    for side, sgn in (("l", -1.0), ("r", 1.0)):
        cheek = skin[(skin[:, 0] * sgn > 0) & (np.abs(skin[:, 1] - (eye_y - 0.3 * span)) < 0.06 * span)
                     & (skin[:, 2] > lm["nose_tip"][2] - 1.4 * span)]
        lm["cheek_" + side] = cheek[np.argmax(cheek[:, 0] * sgn)]
    return lm


def g2f_landmarks(verts, poly_len, poly_idx, poly_mat, names):
    mid = {n: i for i, n in enumerate(names)}
    vs = lambda mats: verts[material_vertices(poly_len, poly_idx, poly_mat, [mid[m] for m in mats])]  # noqa: E731
    skin = vs(HEAD_MATERIALS)
    lm = {}
    sclera, lac, tear, lips, nos, ears = vs(("Sclera",)), vs(("Lacrimals",)), vs(("Tear",)), vs(("Lips",)), vs(("Nostrils",)), vs(("Ears",))
    for side, sgn in (("l", -1.0), ("r", 1.0)):
        s = lambda a: a[a[:, 0] * sgn > 0]  # noqa: E731
        lm["eye_" + side] = s(sclera).mean(0)
        la = s(lac)
        lm["eye_in_" + side] = la[np.argmin(np.abs(la[:, 0]))]
        te = s(tear)
        lm["eye_out_" + side] = te[np.argmax(np.abs(te[:, 0]))]
        li = s(lips)
        lm["mouth_" + side] = li[np.argmax(np.abs(li[:, 0]))]
        lm["ear_" + side] = s(ears).mean(0)
        # lid margins at the middle of the eye: the lowest face vertex above / highest below the
        # eye centre, in front of the eyeball
        c = lm["eye_" + side]
        radius = np.linalg.norm(s(sclera) - c, axis=1).max()
        face = vs(("Face",))
        strip = face[(np.abs(face[:, 0] - c[0]) < 0.003) & (face[:, 2] > c[2] + 0.5 * radius)]
        up, lo = strip[strip[:, 1] > c[1]], strip[strip[:, 1] < c[1]]
        lm["lid_up_" + side] = up[np.argmin(up[:, 1])]
        lm["lid_lo_" + side] = lo[np.argmax(lo[:, 1])]
    lm.update(geometric_landmarks(skin, lm["eye_l"], lm["eye_r"], lm["mouth_l"], lm["mouth_r"]))
    return lm, skin


def source_landmarks(src, face_object, skin_material, eye_material, bone_head):
    """Landmarks on the source face (source coordinates, VaM axes)."""
    obj = src.obj(face_object)
    mats = obj["meta"]["materials"]
    ls, lt, lv = obj["loop_start"], obj["loop_total"], obj["loop_vert"]

    def verts_of(material):
        mi = mats.index(material)
        polys = np.nonzero(obj["mat"] == mi)[0]
        return np.unique(np.concatenate([lv[ls[p]:ls[p] + lt[p]] for p in polys]))

    skin_ids = verts_of(skin_material)
    skin = obj["verts"][skin_ids]
    eyes = obj["verts"][verts_of(eye_material)]
    lm = {}
    for side, sgn, s_ in (("l", -1.0, "L"), ("r", 1.0, "R")):
        e = eyes[eyes[:, 0] * sgn > 0]
        lm["eye_" + side] = e.mean(0)
        for key, bone in (("eye_in_", "FACIAL_%s_EyeCornerInner"), ("eye_out_", "FACIAL_%s_EyeCornerOuter"),
                          ("mouth_", "FACIAL_%s_LipCorner"), ("ear_", "FACIAL_%s_Ear"),
                          ("lid_up_", "FACIAL_%s_EyelidUpperA2"), ("lid_lo_", "FACIAL_%s_EyelidLowerA2")):
            p = bone_head(bone % s_)
            lm[key + side] = skin[np.argmin(np.linalg.norm(skin - p, axis=1))]
    lm.update(geometric_landmarks(skin, lm["eye_l"], lm["eye_r"], lm["mouth_l"], lm["mouth_r"]))
    return lm, obj, skin_ids


# ----------------------------------------------------------------------------- transforms

def similarity(src_pts, dst_pts, allow_rotation=True):
    """Umeyama: s, R, t with dst ~ s R src + t."""
    ms, md = src_pts.mean(0), dst_pts.mean(0)
    a, b = src_pts - ms, dst_pts - md
    if allow_rotation:
        U, S, Vt = np.linalg.svd(b.T @ a / len(a))
        D = np.eye(3)
        if np.linalg.det(U @ Vt) < 0:
            D[2, 2] = -1
        R = U @ D @ Vt
        s = np.trace(np.diag(S) @ D) / (np.sum(a ** 2) / len(a))
    else:
        R = np.eye(3)
        s = np.sum(a * b) / np.sum(a * a)
    t = md - s * R @ ms
    return s, R, t


class TPS:
    """3D thin-plate spline (phi(r) = r), exact at the control points."""

    def __init__(self, src, dst, reg=1e-8):
        n = len(src)
        K = np.linalg.norm(src[:, None, :] - src[None, :, :], axis=2)
        P = np.concatenate([np.ones((n, 1)), src], axis=1)
        A = np.zeros((n + 4, n + 4))
        A[:n, :n] = K + reg * np.eye(n)
        A[:n, n:] = P
        A[n:, :n] = P.T
        B = np.zeros((n + 4, 3))
        B[:n] = dst
        self.coef = np.linalg.solve(A, B)
        self.src = src

    def __call__(self, pts, chunk=4096):
        out = np.empty_like(pts)
        n = len(self.src)
        for s in range(0, len(pts), chunk):
            p = pts[s:s + chunk]
            K = np.linalg.norm(p[:, None, :] - self.src[None, :, :], axis=2)
            out[s:s + chunk] = K @ self.coef[:n] + self.coef[n] + p @ self.coef[n + 1:]
        return out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def fit_head(g2f, src, face_object, skin_material, eye_material, log=print, schedule=(30, 20, 12, 6, 3, 1)):
    """Returns (fitted G2F vertices, similarity (s, R, t) source -> G2F, report)."""
    names = g2f.meta["materialNames"]
    verts = g2f.verts.copy()
    glm, gskin = g2f_landmarks(verts, g2f.poly_len, g2f.poly_idx, g2f.poly_mat, names)
    slm, obj, skin_ids = source_landmarks(src, face_object, skin_material, eye_material, src.head)
    keys = [k for k in glm if k in slm]
    G = np.array([glm[k] for k in keys])
    S = np.array([slm[k] for k in keys])
    s, R, t = similarity(S, G)
    S2 = S @ R.T * s + t
    res = np.linalg.norm(S2 - G, axis=1)
    log("    head similarity: scale %.3f, rotation %.1f deg; landmark residual median %.1f mm, max %.1f mm (%s)"
        % (s, np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))), 1000 * np.median(res),
           1000 * res.max(), keys[int(np.argmax(res))]))
    src_skin = obj["verts"][skin_ids] @ R.T * s + t
    # source skin triangles (in G2F space) for the refinement
    ls, lt, lv = obj["loop_start"], obj["loop_total"], obj["loop_vert"]
    mi = obj["meta"]["materials"].index(skin_material)
    polys = np.nonzero(obj["mat"] == mi)[0]
    remap = -np.ones(len(obj["verts"]), dtype=np.int64)
    remap[skin_ids] = np.arange(len(skin_ids))
    plen = lt[polys]
    pidx = np.concatenate([lv[ls[p]:ls[p] + lt[p]] for p in polys])
    stris = triangulate(plen, remap[pidx])
    # which G2F vertices are "head": the head materials and everything inside the head, faded down the neck
    head_mat_ids = [names.index(m) for m in names if m not in ("Neck", "Torso", "Shoulders", "Hips", "Legs", "Feet",
                                                               "Toenails", "Hands", "Fingernails", "Forearms",
                                                               "Nipples", "defaultMat", "Hidden")]
    head_ids = material_vertices(g2f.poly_len, g2f.poly_idx, g2f.poly_mat, head_mat_ids)
    head_ids = head_ids[head_ids < 21556]
    neck_ids = material_vertices(g2f.poly_len, g2f.poly_idx, g2f.poly_mat, [names.index("Neck")])
    chin_y = glm["chin"][1]
    weight = np.zeros(len(verts))
    weight[head_ids] = 1.0
    weight[neck_ids] = np.maximum(weight[neck_ids], smoothstep(chin_y - 0.07, chin_y - 0.01, verts[neck_ids, 1]))
    moving = np.nonzero(weight > 0)[0]
    tps = TPS(G, S2)
    fitted = verts.copy()
    fitted[moving] = verts[moving] + weight[moving, None] * (tps(verts[moving]) - verts[moving])
    # surface refinement on the skin of the face and head
    surf = material_vertices(g2f.poly_len, g2f.poly_idx, g2f.poly_mat, [names.index(m) for m in REFINE_MATERIALS])
    surf = surf[surf < 21556]
    sa, sb, sc = src_skin[stris[:, 0]], src_skin[stris[:, 1]], src_skin[stris[:, 2]]
    stri_n = np.cross(sb - sa, sc - sa)
    stri_n /= np.maximum(np.linalg.norm(stri_n, axis=1, keepdims=True), 1e-20)
    orient = None
    ea, eb, deg = _edges(g2f.poly_len, g2f.poly_idx, len(verts))
    after_spline = fitted.copy()
    rounds = len(schedule)
    for rnd, smooth_iters in enumerate(schedule):
        q, idx, _bary = closest_points(fitted[surf], src_skin, stris)
        disp = np.zeros_like(verts)
        disp[surf] = q - fitted[surf]
        # do not chase the source where it has no skin (e.g. the neck seam, inside the mouth) ...
        far = np.linalg.norm(disp[surf], axis=1) > 0.02
        # ... nor where the closest source surface faces another way
        nrm = vl.outward_normals(fitted.astype(np.float32), g2f.poly_len, g2f.poly_idx)[surf]
        facing = np.einsum("ij,ij->i", nrm, stri_n[idx])
        if orient is None:                      # source winding: whichever way most pairs agree
            orient = -1.0 if np.median(facing) < 0 else 1.0
        away = orient * facing < FACING_MIN
        disp[surf[far | away]] = 0
        for _ in range(smooth_iters):
            acc = np.zeros_like(disp)
            np.add.at(acc, ea, disp[eb])
            avg = acc / np.maximum(deg, 1)[:, None]
            disp[surf] = 0.5 * disp[surf] + 0.5 * avg[surf]
        fitted[surf] += disp[surf] * (0.6 if rnd < rounds - 1 else 1.0)
        log("    head refine round %d: median pull %.2f mm, p95 %.2f mm (%d facing away, %d too far)"
            % (rnd + 1, 1000 * np.median(np.linalg.norm(q - fitted[surf], axis=1)),
               1000 * np.percentile(np.linalg.norm(q - fitted[surf], axis=1), 95), int(away.sum()), int(far.sum())))
    carry_pull(fitted, after_spline, surf,
               material_vertices(g2f.poly_len, g2f.poly_idx, g2f.poly_mat,
                                 [names.index(m) for m in ATTACHED_MATERIALS if m in names]))
    untangle(fitted, verts, g2f, [names.index(m) for m in REFINE_MATERIALS + ("Ears",)], log=log)
    # eyeballs: rigid move to the source eye centres (VaM turns them about their own bones, so
    # the morph also moves the lEye / rEye bone centres by the same amount)
    eye_shift = {}
    for side, sgn in (("l", -1.0), ("r", 1.0)):
        ids = material_vertices(g2f.poly_len, g2f.poly_idx, g2f.poly_mat, [names.index(m) for m in EYE_MATERIALS])
        ids = ids[verts[ids, 0] * sgn > 0]
        target = slm["eye_" + side] @ R.T * s + t
        eye_shift[side] = target - glm["eye_" + side]
        fitted[ids] = verts[ids] + eye_shift[side]
    log("    eyeballs moved: left %s mm, right %s mm"
        % (np.round(1000 * eye_shift["l"], 1), np.round(1000 * eye_shift["r"], 1)))
    report = {"similarity_scale": float(s), "landmarks": {k: [glm[k].tolist(), (slm[k] @ R.T * s + t).tolist()] for k in keys},
              "residual_mm": float(1000 * np.median(res)), "eye_shift": {k: v.tolist() for k, v in eye_shift.items()}}
    return fitted, (s, R, t), report


def untangle(fitted, base, g2f, mat_ids, rings=2, max_rounds=200, log=print):
    """Relax the displacement (fitted - base) where the fit turned skin triangles over.

    The spline is fold-free, but the surface pull meets other rules at a few seams -- the
    scalp pulled onto the source while the ear next to it only rides along, the mouth corners
    where the lip turns into the mouth -- and folds a handful of triangles there.  Averaging
    the displacement over the flipped triangles' vertices and ``rings`` of neighbours (a
    harmonic patch on the fold-free base mesh) unfolds them and leaves the rest alone."""
    tris = triangulate(g2f.poly_len, g2f.poly_idx, np.isin(g2f.poly_mat, mat_ids))
    ea, eb, deg = _edges(g2f.poly_len, g2f.poly_idx, len(base))
    nb = np.cross(base[tris[:, 1]] - base[tris[:, 0]], base[tris[:, 2]] - base[tris[:, 0]])
    first = None
    for rnd in range(max_rounds):
        nv = np.cross(fitted[tris[:, 1]] - fitted[tris[:, 0]], fitted[tris[:, 2]] - fitted[tris[:, 0]])
        bad = np.einsum("ij,ij->i", nb, nv) <= 0
        if first is None:
            first = int(bad.sum())
        if not bad.any():
            break
        region = np.zeros(len(base), dtype=bool)
        region[tris[bad].ravel()] = True
        for _ in range(rings):
            grown = region.copy()
            grown[eb[region[ea]]] = True
            region = grown
        disp = fitted - base
        for _ in range(10):
            acc = np.zeros_like(disp)
            np.add.at(acc, ea, disp[eb])
            avg = acc / np.maximum(deg, 1)[:, None]
            disp[region] = avg[region]
        fitted[region] = base[region] + disp[region]
    log("    untangle: %d skin triangles turned over by the pull, %d left after %d rounds"
        % (first, int(bad.sum()), rnd + 1))


def carry_pull(fitted, before, surf, ids, k=8, chunk=512):
    """Move ``ids`` by the inverse-distance average of the surface pull (fitted - before) of their
    k nearest ``surf`` vertices (positions before the pull), in place."""
    pull = fitted[surf] - before[surf]
    S = before[surf]
    for s in range(0, len(ids), chunk):
        p = before[ids[s:s + chunk]]
        d2 = ((p[:, None, :] - S[None, :, :]) ** 2).sum(-1)
        nn = np.argpartition(d2, k, axis=1)[:, :k]
        w = 1.0 / (np.take_along_axis(d2, nn, axis=1) + 1e-8)
        fitted[ids[s:s + chunk]] += (pull[nn] * w[..., None]).sum(1) / w.sum(1)[:, None]


# ----------------------------------------------------------------------------- texture

def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def material_uv_tris(obj, material):
    """Triangles of one source material as (vertex ids, loop ids) -- the loops carry the UVs."""
    ls, lt, lv = obj["loop_start"], obj["loop_total"], obj["loop_vert"]
    mi = obj["meta"]["materials"].index(material)
    polys = np.nonzero(obj["mat"] == mi)[0]
    vt, lt_ = [], []
    for p in polys.tolist():
        s, n = int(ls[p]), int(lt[p])
        for k in range(1, n - 1):
            lt_.append((s, s + k, s + k + 1))
            vt.append((lv[s], lv[s + k], lv[s + k + 1]))
    return np.array(vt, dtype=np.int64), np.array(lt_, dtype=np.int64)


def g2f_uv_triangles(g2f, mats):
    """(vertex triangles, uv triangles, uvs) of the G2F polygons with materials ``mats``."""
    names = g2f.meta["materialNames"]
    ids = [names.index(m) for m in mats]
    base = np.load(g2f.cache_npz)
    uvs = base["uvs"].astype(np.float64)
    uv_poly_idx = base["uv_poly_idx"]
    poly_len, poly_idx, poly_mat = g2f.poly_len, g2f.poly_idx, g2f.poly_mat
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    tri_v, tri_uv = [], []
    for p in np.nonzero(np.isin(poly_mat, ids))[0].tolist():
        s, n = int(starts[p]), int(poly_len[p])
        q, u = poly_idx[s:s + n], uv_poly_idx[s:s + n]
        for k in range(1, n - 1):
            tri_v.append((q[0], q[k], q[k + 1]))
            tri_uv.append((u[0], u[k], u[k + 1]))
    return np.array(tri_v, dtype=np.int64), np.array(tri_uv, dtype=np.int64), uvs


def rasterise(uv_tris, size):
    """Texel centres inside each UV triangle ((n, 3, 2), 0..1, V up).

    Returns (triangle index, texel column, image row, barycentric weights) per covered texel."""
    tri_ids, cols, rows, bary = [], [], [], []
    for i, uv in enumerate(np.asarray(uv_tris, dtype=np.float64) * size):
        lo = np.floor(uv.min(0)).astype(int)
        hi = np.ceil(uv.max(0)).astype(int)
        if (hi - lo).min() <= 0:
            continue
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
        pts = np.stack([xs.ravel(), ys.ravel()], axis=1)
        a, b, c = uv
        v0, v1, v2 = b - a, c - a, pts - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        w1 = (v2[:, 0] * v1[1] - v1[0] * v2[:, 1]) / den
        w2 = (v0[0] * v2[:, 1] - v2[:, 0] * v0[1]) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        px = pts[inside].astype(int)
        tri_ids.append(np.full(len(px), i))
        cols.append(np.clip(px[:, 0], 0, size - 1))
        rows.append(size - 1 - np.clip(px[:, 1], 0, size - 1))          # image row 0 = top = V 1
        bary.append(np.stack([w0[inside], w1[inside], w2[inside]], axis=1))
    if not tri_ids:
        return (np.zeros(0, dtype=np.int64),) * 3 + (np.zeros((0, 3)),)
    return np.concatenate(tri_ids), np.concatenate(cols), np.concatenate(rows), np.concatenate(bary)


def sample_bilinear(tex, uv):
    """Bilinear lookup of an (h, w[, c]) array at UVs (origin bottom-left, wrapping)."""
    th, tw = tex.shape[:2]
    x = np.clip(uv[:, 0] % 1.0 * tw - 0.5, 0, tw - 1.001)
    y = np.clip((1.0 - uv[:, 1] % 1.0) * th - 0.5, 0, th - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    if tex.ndim == 3:
        fx, fy = fx[:, None], fy[:, None]
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x0 + 1] * fx * (1 - fy)
            + tex[y0 + 1, x0] * (1 - fx) * fy + tex[y0 + 1, x0 + 1] * fx * fy)


def bake_face_texture(fitted, g2f, mats, src_verts_g2f, src_obj, skin_material, texture_path, size=2048,
                      log=print):
    """Rasterise G2F's face UV tile (materials ``mats``) at ``size``: every texel's point on the
    fitted head takes the colour of the closest point of the source skin (its own UVs, its
    diffuse texture).  Returns the RGB image (float 0..255), the coverage mask and the texel
    positions on the fitted head (size x size x 3, G2F space)."""
    from PIL import Image

    tri_v, tri_uv, uvs = g2f_uv_triangles(g2f, mats)
    tri_ids, cols, rows, w = rasterise(uvs[tri_uv], size)
    tv = tri_v[tri_ids]
    P = (fitted[tv[:, 0]] * w[:, 0:1] + fitted[tv[:, 1]] * w[:, 1:2] + fitted[tv[:, 2]] * w[:, 2:3])
    log("    face texture: %d texels to sample" % len(P))
    vt, ltri = material_uv_tris(src_obj, skin_material)
    q, tri_idx, bary = closest_points(P, src_verts_g2f, vt)
    suv = np.einsum("nk,nkj->nj", bary, src_obj["uv"][ltri[tri_idx]].astype(np.float64))
    tex = np.asarray(Image.open(texture_path).convert("RGB"), dtype=np.float64)
    col = sample_bilinear(tex, suv)
    out = np.zeros((size, size, 3), dtype=np.float64)
    mask = np.zeros((size, size), dtype=bool)
    pos = np.zeros((size, size, 3), dtype=np.float32)
    out[rows, cols] = col
    mask[rows, cols] = True
    pos[rows, cols] = P
    dist = np.linalg.norm(q - P, axis=1)
    log("    face texture: closest-point distance median %.2f mm, p95 %.2f mm"
        % (1000 * np.median(dist), 1000 * np.percentile(dist, 95)))
    return out, mask, pos


def bake_strands(img, fitted, g2f, mats, src_verts_g2f, src_obj, material, odi_path, color, size,
                 max_distance=0.01, opacity=1.0, log=print):
    """Paint hair cards lying on the skin (eyebrows) into the face texture.

    Every card vertex is projected onto the fitted head (closest point -> G2F UV), each card
    triangle is rasterised in that UV space with its own UVs, and its coverage (ODI red) is
    composited over the skin: transmittance multiplies over overlapping cards, so their order
    does not matter (they share one colour).  ``color`` is sRGB 0..255."""
    from PIL import Image

    tri_v, tri_uv, uvs = g2f_uv_triangles(g2f, mats)
    vt, ltri = material_uv_tris(src_obj, material)
    used = np.unique(vt)
    q, idx, bary = closest_points(src_verts_g2f[used], fitted, tri_v)
    dist = np.linalg.norm(q - src_verts_g2f[used], axis=1)
    guv = np.einsum("nk,nkj->nj", bary, uvs[tri_uv[idx]])
    remap = np.full(len(src_verts_g2f), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    ok = (dist[remap[vt]] < max_distance).all(axis=1)
    log("    %s: %d card triangles, %d on the skin (card-to-skin median %.1f mm)"
        % (material, len(vt), int(ok.sum()), 1000 * np.median(dist)))
    tri_ids, cols, rows, w = rasterise(guv[remap[vt[ok]]], size)
    suv = np.einsum("nk,nkj->nj", w, src_obj["uv"][ltri[ok][tri_ids]].astype(np.float64))
    odi = np.asarray(Image.open(odi_path).convert("RGB"), dtype=np.float64)[..., 0] / 255.0
    a = np.clip(sample_bilinear(odi, suv) * opacity, 0, 0.999)
    log_t = np.zeros((size, size))
    np.add.at(log_t, (rows, cols), np.log1p(-a))
    cover = 1.0 - np.exp(log_t)
    out = img * (1 - cover[..., None]) + np.asarray(color, dtype=np.float64) * cover[..., None]
    return out, cover


def box_blur(img, radius, passes=3):
    """Separable box blur (``passes`` times ~ a Gaussian), edges clamped."""
    out = img.astype(np.float64)
    for _ in range(passes):
        for axis in (0, 1):
            pad = [(0, 0)] * out.ndim
            pad[axis] = (radius + 1, radius)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
            n = out.shape[axis]
            hi = np.take(c, np.arange(2 * radius + 1, 2 * radius + 1 + n), axis=axis)
            lo = np.take(c, np.arange(0, n), axis=axis)
            out = (hi - lo) / (2 * radius + 1)
    return out


def masked_blur(img, mask, radius):
    """Blur of ``img`` over the texels in ``mask`` only (normalised convolution)."""
    m = mask.astype(np.float64)
    num = box_blur(img * m[..., None], radius)
    den = box_blur(m, radius)
    return num / np.maximum(den, 1e-6)[..., None]


def _grow(m):
    g = m.copy()
    g[1:] |= m[:-1]
    g[:-1] |= m[1:]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    return g


def outside_distance(mask, limit):
    """Distance in texels (4-neighbour steps, capped at ``limit``) from every covered texel to
    the uncovered region that reaches the image border -- the island's outer seam, not its
    holes (eyes, mouth)."""
    outside = np.zeros_like(mask)
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    outside &= ~mask
    while True:                                     # flood the uncovered region from the border
        grown = _grow(outside) & ~mask
        if (grown == outside).all():
            break
        outside = grown
    dist = np.full(mask.shape, float(limit))
    reached = outside.copy()
    front = outside
    for d in range(1, limit + 1):
        new = _grow(front) & ~reached
        if not new.any():
            break
        dist[new] = d
        reached |= new
        front = new
    dist[~mask] = 0
    return dist


def match_to_reference(img, mask, ref, band, blur, strength_inside=0.0):
    """Tone the baked texture into the reference skin around the island's outer seam.

    The low-frequency colour ratio ref / img (linear light) is applied fully at the seam and
    faded out over ``band`` texels, down to ``strength_inside`` in the middle of the face: the
    neck, scalp and ears keep the reference character's torso texture, so the face must meet
    them in its colour while its own detail (freckles, scar, mole, lips) stays."""
    lin = srgb_to_linear(img / 255.0)
    rlin = srgb_to_linear(ref / 255.0)
    lo = masked_blur(lin, mask, blur)
    rlo = masked_blur(rlin, mask, blur)
    ratio = rlo / np.maximum(lo, 1e-4)
    dist = outside_distance(mask, band)
    wgt = strength_inside + (1 - strength_inside) * smoothstep(band, 0, dist)
    out = lin * (1 + wgt[..., None] * (ratio - 1))
    return linear_to_srgb(out) * 255.0, wgt


def max_filter(a, radius):
    """Grey dilation with a (2 radius + 1)^2 square, edges clamped."""
    out = a.copy()
    for _ in range(radius):
        g = out.copy()
        g[1:] = np.maximum(g[1:], out[:-1])
        g[:-1] = np.maximum(g[:-1], out[1:])
        h = g.copy()
        h[:, 1:] = np.maximum(h[:, 1:], g[:, :-1])
        h[:, :-1] = np.maximum(h[:, :-1], g[:, 1:])
        out = h
    return out


def replace_dark_paint(img, mask, pos, ref, above_y, lateral_x, below_y, dark=(90, 140), grow=40, soften=16):
    """Swap the source's painted-on hair base (dark scalp paint at the hairline) for the
    reference skin: texels darker than the skin, above the brows or lateral to the eyes.  The
    paint fades into the skin over a few millimetres (a greyish fringe), so the swapped area is
    grown past that fringe by ``grow`` texels and feathered by ``soften``."""
    lum = img @ np.array([0.2126, 0.7152, 0.0722])
    y, ax = pos[..., 1], np.abs(pos[..., 0])
    region = np.maximum(smoothstep(above_y - 0.003, above_y + 0.003, y),
                        smoothstep(lateral_x - 0.003, lateral_x + 0.003, ax)
                        * smoothstep(below_y - 0.003, below_y + 0.003, y)) * mask
    h = smoothstep(dark[1], dark[0], lum) * region
    h = box_blur(max_filter(h, grow), soften, passes=2)
    h = np.minimum(h, region)
    return img * (1 - h[..., None]) + ref * h[..., None], h


def eye_formulas(eye_shift):
    """VaM morph formulas moving the eye bone centres with the eyeballs (VaM space, metres --
    checked against creator morphs, whose lEye BoneCenter values equal the mean shift of the
    x < 0 eyeball's vertices)."""
    out = []
    for side, bone in (("l", "lEye"), ("r", "rEye")):
        for axis, value in zip("XYZ", eye_shift[side]):
            out.append({"targetType": "BoneCenter" + axis, "target": bone, "multiplier": "%.7g" % value})
    return out


def iris_radii(img, centre, rmax, samples=240):
    """(pupil edge, iris rim) radii in UV of an iris disc, from its radial brightness profile:
    dark pupil, a darker-than-sclera iris ring, bright sclera (or rim) outside."""
    h, w = img.shape[:2]
    rs = np.linspace(0, rmax, samples)
    th = np.linspace(0, 2 * np.pi, 256, endpoint=False)
    u = centre[0] + rs[:, None] * np.cos(th)[None, :]
    v = centre[1] + rs[:, None] * np.sin(th)[None, :]
    x = np.clip((u * w).astype(int), 0, w - 1)
    y = np.clip(((1 - v) * h).astype(int), 0, h - 1)
    lum = (img[y, x, :3] @ np.array([0.2126, 0.7152, 0.0722])).mean(axis=1)
    pupil_level = lum[0]
    iris_band = (rs > 0.45 * rmax) & (rs < 0.65 * rmax)
    iris_level = np.median(lum[iris_band])
    pupil = rs[np.argmax(lum > pupil_level + 0.5 * (iris_level - pupil_level))]
    beyond = rs > 0.65 * rmax
    sclera_level = lum[beyond].max()
    first = np.nonzero(beyond & (lum > iris_level + 0.5 * (sclera_level - iris_level)))[0]
    rim = rs[first[0]] if len(first) else 0.85 * rmax
    return float(pupil), float(rim)


def transplant_iris(base_path, source_path, out_path, base_centres=((0.25, 0.25), (0.75, 0.25)),
                    base_rmax=0.235, source_centre=(0.5, 0.5), source_rmax=0.25, log=print):
    """Put the source's iris into a G2F eye texture (sclera in the top half, the two irises in
    the bottom half).  The ring between pupil edge and iris rim is mapped radially (both are
    measured on each texture), so the source's own limbus lands on G2F's rim and the base
    texture keeps its pupil and sclera."""
    from PIL import Image

    base_img = Image.open(base_path)
    mode = "RGBA" if base_img.mode == "RGBA" else "RGB"
    base = np.asarray(base_img.convert(mode), dtype=np.float64)
    src = np.asarray(Image.open(source_path).convert("RGB"), dtype=np.float64)
    p_f, r_f = iris_radii(src, source_centre, source_rmax)
    h, w = base.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    u, v = (xs + 0.5) / w, 1.0 - (ys + 0.5) / h
    out = base.copy()
    for c in base_centres:
        p_g, r_g = iris_radii(base, c, base_rmax)
        log("    iris: base disc %s pupil %.3f rim %.3f  <-  source pupil %.3f rim %.3f" % (c, p_g, r_g, p_f, r_f))
        dx, dy = u - c[0], v - c[1]
        r = np.hypot(dx, dy)
        sel = (r > p_g - 0.01) & (r < r_g + 0.01)
        t = (r[sel] - p_g) / (r_g - p_g)
        rf = p_f + np.clip(t, 0, 1) * (r_f - p_f)
        ang = np.arctan2(dy[sel], dx[sel])
        col = sample_bilinear(src, np.stack([source_centre[0] + rf * np.cos(ang),
                                             source_centre[1] + rf * np.sin(ang)], axis=1))
        wgt = smoothstep(p_g - 0.004, p_g + 0.004, r[sel]) * (1 - smoothstep(r_g - 0.003, r_g + 0.006, r[sel]))
        out[sel, :3] = out[sel, :3] * (1 - wgt[:, None]) + col * wgt[:, None]
    Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), mode).save(out_path)
    return out_path


def dilate(img, mask, rounds=16):
    """Grow the covered texels outward (UV seams must not bleed black)."""
    img = img.copy()
    mask = mask.copy()
    for _ in range(rounds):
        acc = np.zeros_like(img)
        cnt = np.zeros(mask.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            m = np.roll(np.roll(mask, dy, 0), dx, 1)
            acc += np.roll(np.roll(img, dy, 0), dx, 1) * m[..., None]
            cnt += m
        grow = (~mask) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        mask = mask | grow
    return img, mask


def _edges(poly_len, poly_idx, count):
    poly_len = np.asarray(poly_len)
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    a_list, b_list = [], []
    for n in (3, 4):
        sel = np.nonzero(poly_len == n)[0]
        q = np.asarray(poly_idx)[starts[sel][:, None] + np.arange(n)[None, :]]
        a_list.append(q.ravel())
        b_list.append(np.roll(q, -1, axis=1).ravel())
    a = np.concatenate(a_list).astype(np.int64)
    b = np.concatenate(b_list).astype(np.int64)
    ea, eb = np.concatenate([a, b]), np.concatenate([b, a])
    return ea, eb, np.bincount(ea, minlength=count).astype(np.float64)
