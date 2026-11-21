# 花木兰·水晶猎龙者 仿制 v11: the armour is modelled after the MS移植 #44 (HS2 port of the game model) previews.
# Base = Inase a08 nude + Eve's ponytail (build\b2_hair.pmx).  Everything else is made here:
#   - skin-grown shells (skinshell.py): the black suit, cuirass (cups + fangs + back plate), V belt, lames on the
#     shoulders / forearms / thighs, greaves, knee straps;
#   - built pieces (parts.py / geo.py): crown with flame horns, gems, shoulder crystals, hip fins, collar + brooch,
#     claws, elbow spikes, knee guards, sabatons, petal skirt, back ornaments + two crossed short swords, the
#     crystal greatsword.
#   python build_v11.py <base.pmx> <out.pmx> [--stages suit,cuirass,...] [--skip sword,...]
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
import parts as PT  # noqa: E402
import skinshell as S  # noqa: E402
import textures as TX  # noqa: E402
from geo import L, Part  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--stages", default="all")
ap.add_argument("--skip", default="")
ap.add_argument("--skin", default="pc_a01_nk_body")
args = ap.parse_args()
STAGES = None if args.stages == "all" else set(args.stages.split(","))
SKIP = set(x for x in args.skip.split(",") if x)


def on(stage):
    ok = (STAGES is None or stage in STAGES) and stage not in SKIP
    if ok:
        print(stage, flush=True)
    return ok


M = L.load(os.path.abspath(args.src))
FLIP = geo.winding_flip(M)
OUT_DIR = os.path.dirname(os.path.abspath(args.out))
TEX_DIR = os.path.join(OUT_DIR, "textures")
os.makedirs(TEX_DIR, exist_ok=True)
skin = S.Skin(M, args.skin)
NAMES = [b.name for b in M.bones]
CH = {}
print("skin:", len(skin.P), "vertices", len(skin.F), "faces")


def tex(name, maker, *a, **k):
    path = os.path.join(TEX_DIR, name)
    maker(path, *a, **k)
    return geo.texture(M, path)


T_PLATE = tex("v11_armor_plate.png", TX.armor_plate)
T_SUIT = tex("v11_suit.png", TX.suit)
T_SPH_GLOSS = tex("v11_sph_gloss.png", TX.sphere_gloss)
T_SPH_SUIT = tex("v11_sph_suit.png", TX.sphere_gloss, strength=0.6)
T_SPH_CRYSTAL = tex("v11_sph_crystal.png", TX.sphere_crystal)
T_SPH_SOFT = tex("v11_sph_soft.png", TX.sphere_soft)
T_DARK_BLADE = tex("v11_dark_blade.png", TX.dark_blade)
T_DARK = tex("v11_dark.png", TX.flat, TX.ARMOR_DARK * 1.25)
T_FLAME = tex("v11_flame.png", TX.flame_atlas)
T_CRYSTAL = tex("v11_crystal.png", TX.crystal)
T_FIN = tex("v11_fin.png", TX.fin)
T_KNEE = tex("v11_gold.png", TX.knee)
T_PETAL = tex("v11_petal.png", TX.petal)
T_PETAL_DARK = tex("v11_petal_dark.png", TX.petal, dark=True)
T_LOCK = tex("v11_hair_lock.png", TX.hair_lock)
T_SWORD = tex("v11_sword_blade.png", TX.sword_blade)
T_GRIP = tex("v11_grip.png", TX.grip)

ARMOR_MAT = dict(diffuse=(1, 1, 1, 1), specular=(0.30, 0.26, 0.25), shininess=95, ambient=(0.45, 0.42, 0.42), edge=True,
                 edge_color=(0.03, 0.01, 0.015, 1.0), edge_size=0.5, toon=0)
CRYSTAL_MAT = dict(diffuse=(1, 1, 1, 1), specular=(1.0, 0.95, 0.8), shininess=60, ambient=(0.62, 0.5, 0.4), edge=True,
                   edge_color=(0.30, 0.06, 0.0, 1.0), edge_size=0.5, toon=0)
SUIT_MAT = dict(diffuse=(1, 1, 1, 1), specular=(0.30, 0.27, 0.28), shininess=75, ambient=(0.5, 0.5, 0.5), edge=False, toon=0)
# Flat plates and blades take T_SPH_SOFT: a flat plate has one normal, so it samples ONE texel of the sphere map and
# the hot spot of the glossy map made whole plates flash white in the dance (found with the sphere map switched off).
FLAT_MAT = dict(ARMOR_MAT, specular=(0.20, 0.18, 0.17))
BLADE_MAT = dict(CRYSTAL_MAT, specular=(0.22, 0.18, 0.10))
GOLD_MAT = dict(diffuse=(1, 1, 1, 1), specular=(0.9, 0.7, 0.4), shininess=45, ambient=(0.7, 0.6, 0.5), edge=True,
                edge_color=(0.12, 0.03, 0.01, 1.0), edge_size=0.5, toon=0)
PETAL_MAT = dict(diffuse=(1, 1, 1, 1), specular=(0.05, 0.03, 0.02), shininess=80, ambient=(0.55, 0.45, 0.4), edge=True,
                 edge_color=(0.25, 0.05, 0.01, 1.0), edge_size=0.45, toon=0)


def commit(part, name, tex_i, sphere=None, double=False, **mat):
    if not len(part):
        print("  (empty part %s)" % name)
        return None
    bad = [i for i, w in enumerate(part.W) if not w]
    if bad:
        raise SystemExit("part %s: %d vertices without weights" % (name, len(bad)))
    mi = part.commit(M, name, tex_i, flip=FLIP, double=double, **mat)
    if sphere is not None:
        M.materials[mi].sphere_texture, M.materials[mi].sphere_texture_mode = sphere, 2      # additive
    print("  + %-18s %6d faces" % (name, len(part)), flush=True)
    return mi


def bone(name):
    return geo.bone_pos(M, name)


def bname(side, base):
    """the deforming leg bone: the D bone when the rig has one"""
    return side + base + "D" if side + base + "D" in NAMES else side + base


# ------------------------------------------------------------------ outlines (front view, cm; x = the model's left)
# lower edge of the cuirass, right half from the centre outwards: centre spike, two bat-wing jags, the long fang down
# to navel height, then up to the flank
E_FRONT = [(0.0, 127.0), (1.3, 129.8), (2.6, 125.8), (3.9, 128.6), (4.9, 121.2), (6.3, 125.0), (6.0, 111.2), (8.4, 117.2),
           (10.2, 118.6), (11.5, 118.2), (16.0, 117.5)]
# the same edge on the back: from the flank to a tail down the spine
E_BACK = [(0.0, 104.8), (1.8, 106.5), (2.6, 112.5), (5.0, 114.0), (8.0, 116.0), (10.5, 118.2), (16.0, 117.5)]
KEYHOLE = S.mirror_poly([(0.0, 133.0), (3.0, 136.6), (4.0, 139.6), (2.6, 141.6), (0.0, 142.2)])
# bare belly: under the cuirass edge at the top, 2 cm inside the silhouette at the sides, under the belt at the bottom
BARE = S.mirror_poly([(0.0, 131.0), (4.2, 130.2), (6.8, 126.6), (8.6, 121.0), (8.6, 118.5), (8.3, 116.0), (9.3, 112.0),
                      (10.8, 108.0), (11.8, 105.2), (11.8, 103.0), (9.0, 101.6), (6.0, 100.0), (3.0, 98.6), (0.0, 97.4)])


def upper_poly(edge_half):
    right = list(edge_half) + [(30.0, 117.5), (30.0, 175.0)]
    left = [(-x, y) for x, y in reversed(right)]
    if abs(edge_half[0][0]) < 1e-9:
        left = left[:-1]
    return right + left


POLY_UP_F, POLY_UP_B = upper_poly(E_FRONT), upper_poly(E_BACK)


def belt_top(x, front):
    ax = np.abs(x)
    yf = 98.0 + 6.8 * (ax / 13.5) ** 1.2
    y_seam = 98.0 + 6.8 * (14.5 / 13.5) ** 1.2
    yb = y_seam + 2.6 * np.clip(1 - ax / 14.5, 0, 1)
    return np.where(front, yf, yb)


# limbs: t = cm along the bone from its head, phi = 0 front / +90 outer / 180 back / -90 inner
SIDES = (("L", "左", 1), ("R", "右", -1))
UARM = {s: S.Limb(bone(n + "腕"), bone(n + "ひじ"), sg) for s, n, sg in SIDES}
FARM = {s: S.Limb(bone(n + "ひじ"), bone(n + "手首"), sg) for s, n, sg in SIDES}
THIGH = {s: S.Limb(bone(n + "足"), bone(n + "ひざ"), sg) for s, n, sg in SIDES}
SHIN = {s: S.Limb(bone(n + "ひざ"), bone(n + "足首"), sg) for s, n, sg in SIDES}


def f_armhole(P, t_cut=1.5, r_arm=6.5):
    """positive on the torso side of a clean cut across each shoulder: a plane t_cut cm down the upper arm, only
    inside the arm's cylinder"""
    f = np.full(len(P), 50.0)
    for s in ("L", "R"):
        t, _phi, r = UARM[s].coords(P)
        f = np.minimum(f, np.maximum(t_cut - t, r - r_arm))
    return f


def f_upper(P, C):
    front = P[:, 2] < 0
    f = np.where(front, S.sdf_polygon(P[:, :2], POLY_UP_F), S.sdf_polygon(P[:, :2], POLY_UP_B))
    f = np.where(front, np.minimum(f, -S.sdf_polygon(P[:, :2], KEYHOLE)), f)
    return np.minimum(f, f_armhole(P))


def f_belt(P, C):
    front = P[:, 2] < 0
    yt = belt_top(P[:, 0], front)
    width = 2.4 + 1.4 * np.clip(np.abs(P[:, 0]) / 14.5, 0, 1)
    f = np.minimum(yt - P[:, 1], P[:, 1] - (yt - width))
    return np.where(np.abs(P[:, 0]) < 22, f, -5.0)


def f_suit(P, C):
    front = P[:, 2] < 0
    bare = np.maximum(S.sdf_polygon(P[:, :2], BARE), S.sdf_polygon(P[:, :2], KEYHOLE) + 0.8)
    return np.where(front, -bare, 5.0)


def uv_edge(scale=4.0):
    def fn(P, f, C):
        return np.stack([np.clip(f / scale, 0.004, 0.985), P[:, 1] * 0.013], 1)
    return fn


# ------------------------------------------------------------------ probes of the body surface
TORSO = np.abs(skin.P[:, 0]) < 22


def probe_z(x, y, side, rad=1.3):
    """z of the body surface at (x, y): the front-most (side='front') or back-most skin point within rad cm"""
    d = np.hypot(skin.P[:, 0] - x, skin.P[:, 1] - y)
    sel = (d < rad) & TORSO
    if not sel.any():
        sel = d < rad * 2.5
    z = skin.P[sel][:, 2]
    return float(z.min() if side == "front" else z.max())


_band = skin.P[(np.abs(skin.P[:, 1] - 102.0) < 4) & TORSO]
HIP_C = (float(_band[:, 0].mean()), float(_band[:, 2].mean()))


def hip_radius(theta_deg, y, win_deg=13.0):
    """distance from the hip centre line to the skin at height y in the direction theta (0 = front, 90 = left)"""
    sel = (np.abs(skin.P[:, 1] - y) < 3.0) & TORSO
    Pb = skin.P[sel]
    ang = np.degrees(np.arctan2(Pb[:, 0] - HIP_C[0], -(Pb[:, 2] - HIP_C[1])))
    rad = np.hypot(Pb[:, 0] - HIP_C[0], Pb[:, 2] - HIP_C[1])
    near = np.abs(S.ang_diff(ang, theta_deg)) < win_deg
    return float(np.percentile(rad[near], 90)) if near.sum() > 4 else float(rad.max())


# ------------------------------------------------------------------ skin-grown parts
# the breastplate must not show the nipples: relax the skin there (a copy), and lift the plate over the real tip
NIP = []
for sx in (1, -1):
    d = np.hypot(skin.P[:, 0] - sx * 9.2, skin.P[:, 1] - 131.5)
    box = (d < 0.9) & (skin.P[:, 2] < -9)
    NIP.append(skin.P[np.nonzero(box)[0][skin.P[box][:, 2].argmin()]])
skin_cup = skin.relaxed(NIP, 2.6, iters=1500)
NIP_H = float(np.max(np.einsum("ij,ij->i", skin.P - skin_cup.P, skin_cup.N)))
print("nipples at", np.round(NIP, 1).tolist(), "standing %.2f cm over the relaxed breast" % NIP_H)

if on("suit"):
    part = S.shell(skin_cup, f_suit, 0.15, uv=lambda P, f, C: np.stack([P[:, 0] * 0.02, P[:, 1] * 0.02], 1),
                   h_coarse=1.5, h_fine=0.5, rim_to=0.0, channels=CH)
    commit(part, "v11_suit", T_SUIT, sphere=T_SPH_SUIT, **SUIT_MAT)

if on("cuirass"):
    def cup_offset(P, C):
        off = np.full(len(P), 0.65)
        for c in NIP:
            r = np.linalg.norm(P - c, axis=1)
            k = np.clip(1 - r / 4.0, 0, 1)
            off = np.maximum(off, 0.65 + max(NIP_H + 0.3 - 0.65, 0.0) * k * k * (3 - 2 * k))
        return off

    part = S.shell(skin_cup, f_upper, cup_offset, uv=uv_edge(), h_coarse=1.0, h_fine=0.3, rim_to=0.05, rim_uv=(0.02, 0.5), channels=CH)
    commit(part, "v11_cuirass", T_PLATE, sphere=T_SPH_GLOSS, **ARMOR_MAT)

if on("belt"):
    part = S.shell(skin, f_belt, 0.5, uv=uv_edge(1.6), h_coarse=1.0, h_fine=0.4, rim_to=0.05, rim_uv=(0.02, 0.5), sdf=False, channels=CH)
    commit(part, "v11_belt", T_PLATE, sphere=T_SPH_GLOSS, **ARMOR_MAT)


def lames(limbs, spans, phi_range, r_max, teeth, amp, off0, off1, rim_to=0.12, h_fine=0.5, full=False):
    """overlapping plates round a limb: each span (t0, t1) is one lame whose far edge stands off0 -> off1 cm from the
    skin (so it overlaps the next one) and is cut into `teeth` points."""
    part = Part()
    p0, p1 = phi_range
    for s in ("L", "R"):
        limb = limbs[s]
        for t0, t1 in spans:
            def field(P, C, limb=limb, t0=t0, t1=t1):
                t, phi, r = limb.coords(P)
                ph = (phi - p0) % 360.0 + p0
                frac = (ph - p0) / (p1 - p0)
                saw = np.abs((frac * teeth) % 1.0 - 0.5) * 2          # 0 at a tooth's centre
                f = np.minimum(t - t0, (t1 + amp * (1 - saw)) - t)
                if not full:
                    f = np.minimum(f, np.minimum(ph - p0, p1 - ph) * np.pi / 180 * np.maximum(r, 1.0))
                return np.minimum(f, r_max - r)

            def offset(P, C, limb=limb, t0=t0, t1=t1):
                t, _phi, _r = limb.coords(P)
                return off0 + (off1 - off0) * np.clip((t - t0) / (t1 - t0), 0, 1.25)

            part.add(S.shell(skin, field, offset, uv=uv_edge(2.5), h_coarse=0.9, h_fine=h_fine, rim_to=rim_to,
                             rim_uv=(0.02, 0.5), sdf=False, channels=CH))
    return part


if on("lames"):
    part = Part()
    part.add(lames(UARM, [(-5.5, 1.5), (0.5, 5.5), (4.5, 10.5)], (-35, 215), 8.5, 3, 1.2, 0.35, 1.05))        # pauldrons
    part.add(lames(FARM, [(2.0, 9.5), (8.5, 16.0), (15.0, 22.5)], (-20, 200), 6.0, 2, 1.5, 0.3, 0.8))          # vambraces
    part.add(lames(THIGH, [(9.0, 17.5), (16.5, 25.0), (24.0, 32.0), (31.0, 38.0)], (-55, 235), 12.0, 3, 2.2, 0.3, 0.9))
    commit(part, "v11_lames", T_PLATE, sphere=T_SPH_GLOSS, **ARMOR_MAT)

if on("greaves"):
    part = Part()
    for s in ("L", "R"):
        limb = SHIN[s]

        def field(P, C, limb=limb):
            t, phi, r = limb.coords(P)
            t_top = 4.5 - 3.4 * np.clip(1 - np.abs(phi) / 55.0, 0, 1)       # a point rising towards the knee in front
            return np.minimum.reduce([t - t_top, 37.5 - t, 9.0 - r])

        def offset(P, C, limb=limb):
            t, _phi, _r = limb.coords(P)
            return 0.45 + 0.6 * np.clip((8.0 - t) / 6.0, 0, 1)

        part.add(S.shell(skin, field, offset, uv=uv_edge(3.0), h_coarse=0.9, h_fine=0.3, rim_to=0.1, rim_uv=(0.02, 0.5),
                         sdf=False, channels=CH))
    commit(part, "v11_greaves", T_PLATE, sphere=T_SPH_GLOSS, **ARMOR_MAT)

if on("knee_straps"):
    part = Part()
    for s, n, sg in SIDES:
        kpos = bone(n + "ひざ")

        def field(P, C, kpos=kpos):
            r = np.hypot(P[:, 0] - kpos[0], P[:, 2] - kpos[2])
            return np.minimum(1.6 - np.abs(P[:, 1] - (kpos[1] + 0.6)), 9.0 - r)

        part.add(S.shell(skin, field, 0.5, uv=lambda P, f, C: np.stack([np.full(len(P), 0.5), np.full(len(P), 0.9)], 1),
                         h_coarse=0.9, h_fine=0.35, rim_to=0.1, sdf=False, channels=CH))
    commit(part, "v11_knee_straps", T_KNEE, sphere=T_SPH_GLOSS, **GOLD_MAT)


# ------------------------------------------------------------------ sabatons (convex boots lofted over the feet)
def hull2d(pts):
    pts = sorted(set(map(tuple, np.round(pts, 4))))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def ray_hull(c, d, hull):
    """distance from c along unit d to the hull's boundary"""
    best = 0.0
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        e = b - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        t = ((a[0] - c[0]) * e[1] - (a[1] - c[1]) * e[0]) / den
        u = ((a[0] - c[0]) * d[1] - (a[1] - c[1]) * d[0]) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            best = max(best, t)
    return best


def sabaton(sg, top=11.5, n_ring=16, margin=0.5):
    foot = (skin.P[:, 1] < top) & (skin.P[:, 0] * sg > 0)
    idx = np.nonzero(foot)[0]
    Pf = skin.P[idx]
    z0, z1 = Pf[:, 2].min(), Pf[:, 2].max()
    part = Part()
    rings = []
    zs = np.arange(z0 + 0.5, z1 - 0.2, 1.0)
    for zc in zs:
        sl = Pf[np.abs(Pf[:, 2] - zc) < 1.0]
        if len(sl) < 6:
            continue
        hull = hull2d(sl[:, :2])
        if len(hull) < 3:
            continue
        c = hull.mean(0)
        ring = []
        for k in range(n_ring):
            a = 2 * np.pi * k / n_ring
            d = np.array([np.cos(a), np.sin(a)])
            r = ray_hull(c, d, hull) + margin
            q = c + d * r
            p = np.array([q[0], max(q[1], -0.05), zc])
            near = idx[int(np.linalg.norm(Pf - p, axis=1).argmin())]
            ring.append(part.vert(p, (d[0], d[1], 0), (0.5, 0.5), list(skin.W[near])))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n_ring):
            k2 = (k + 1) % n_ring
            part.quad(r0[k], r0[k2], r1[k2], r1[k])
    part.smooth_normals()
    cen = np.mean(part.P, 0)
    if np.mean([float((part.P[v] - cen) @ part.N[v]) for v in range(len(part.P))]) < 0:
        part.F = [(a, c2, b) for a, b, c2 in part.F]
        part.N = [-q for q in part.N]
    for ring, sgn_z in ((rings[0], -1.0), (rings[-1], 1.0)):                     # toe and heel caps
        pts = [part.P[v] for v in ring]
        c = np.mean(pts, 0)
        wv = part.W[ring[0]]
        for k in range(n_ring):
            part.flat_tri(c, pts[k], pts[(k + 1) % n_ring], w=wv, out_hint=np.array([0, 0, sgn_z]))
    # toe claws and a heel spur
    toe = np.mean([part.P[v] for v in rings[0]], 0)
    w_toe = part.W[rings[0][0]]
    for dx in (-2.3, 0.0, 2.3):
        b0 = toe + np.array([dx, -0.4, 0.6])
        part.add(PT.leaf_blade([b0, b0 + np.array([dx * 0.25, 0.4, -2.2]), b0 + np.array([dx * 0.4, -0.9, -4.6])], 1.9, 1.3,
                               geo.unit((1, 0, 0)), w_toe, uv_rect=(0.4, 0.4, 0.6, 0.6),
                               knots=[(0, 0.9), (0.3, 1.0), (1.0, 0.0)]))
    heel = np.mean([part.P[v] for v in rings[-1]], 0)
    w_heel = part.W[rings[-1][0]]
    h0 = heel + np.array([0, 1.5, -0.6])
    part.add(PT.leaf_blade([h0, h0 + np.array([0, 1.2, 2.0]), h0 + np.array([0, 3.2, 4.2])], 2.0, 1.2, geo.unit((1, 0, 0)),
                           w_heel, uv_rect=(0.4, 0.4, 0.6, 0.6), knots=[(0, 0.9), (0.3, 1.0), (1.0, 0.0)]))
    return part


if on("sabatons"):
    part = Part()
    part.add(sabaton(1))
    part.add(sabaton(-1))
    commit(part, "v11_sabatons", T_DARK, sphere=T_SPH_SUIT, **dict(ARMOR_MAT, specular=(0.4, 0.36, 0.36)))

# ------------------------------------------------------------------ built parts
RNG = np.random.default_rng(44)

if on("crown"):
    c = PT.crown(M)
    commit(c["black"], "v11_crown", T_DARK_BLADE, sphere=T_SPH_SOFT, **FLAT_MAT)
    commit(c["flame"], "v11_crown_flame", T_FLAME, sphere=T_SPH_SOFT, **BLADE_MAT)
    commit(c["gem"], "v11_crown_gem", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)

if on("locks"):
    commit(PT.side_locks(M), "v11_side_locks", T_LOCK,
           **dict(SUIT_MAT, specular=(0.25, 0.25, 0.25), ambient=(0.6, 0.6, 0.6)))

if on("crystals"):
    commit(PT.shoulder_crystals(M, RNG), "v11_crystals", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)

if on("fins"):
    commit(PT.hip_fins(M), "v11_fins", T_FIN, sphere=T_SPH_SOFT, **dict(BLADE_MAT, ambient=(1.0, 0.92, 0.6)))

if on("collar"):
    c = PT.collar(M, probe_z(0.0, 142.6, "front"))
    commit(c["collar"], "v11_collar", T_DARK_BLADE, sphere=T_SPH_GLOSS, double=True, **FLAT_MAT)
    commit(c["brooch_rim"], "v11_brooch", T_KNEE, sphere=T_SPH_GLOSS, **GOLD_MAT)
    commit(c["brooch_gem"], "v11_brooch_gem", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)

if on("claws"):
    part = PT.claws(M, skin.P, skin.W)
    commit(part, "v11_claws", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)
    part = PT.elbow_spikes(M)
    part.add(PT.forearm_fins(M))
    commit(part, "v11_arm_fins", T_DARK_BLADE, sphere=T_SPH_SOFT, **FLAT_MAT)

if on("knees"):
    kp = bone("左ひざ")
    sel = (np.abs(skin.P[:, 1] - kp[1]) < 2.5) & (skin.P[:, 0] > 2) & (np.abs(skin.P[:, 0] - kp[0]) < 3.0)
    r_knee = float(kp[2] - skin.P[sel][:, 2].min())
    print("  knee front radius %.1f cm" % r_knee)
    k = PT.knee_guards(M, r_knee)
    commit(k["plate"], "v11_knee", T_KNEE, sphere=T_SPH_GLOSS, **GOLD_MAT)
    commit(k["gem"], "v11_knee_gem", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)

if on("skirt"):
    sk = PT.skirt(M, hip_radius, HIP_C)
    commit(sk["petal"], "v11_petals", T_PETAL, sphere=T_SPH_SOFT, **PETAL_MAT)
    commit(sk["petal_dark"], "v11_petals_dark", T_PETAL_DARK, sphere=T_SPH_SOFT, **PETAL_MAT)
    commit(sk["plate"], "v11_tassets", T_DARK_BLADE, sphere=T_SPH_SOFT, **FLAT_MAT)

if on("back"):
    b = PT.back_details(M, lambda x, y: probe_z(x, y, "back"))
    commit(b["black"], "v11_back", T_DARK_BLADE, sphere=T_SPH_SOFT, **FLAT_MAT)
    commit(b["flame"], "v11_back_flame", T_FLAME, sphere=T_SPH_SOFT, **BLADE_MAT)
    commit(b["gem"], "v11_back_gem", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)
    commit(b["hilt"], "v11_hilts", T_KNEE, sphere=T_SPH_GLOSS, **GOLD_MAT)

if on("sword"):
    sw = PT.greatsword(M)
    commit(sw["blade"], "v11_sword_blade", T_SWORD, sphere=T_SPH_SOFT, **BLADE_MAT)
    commit(sw["dark"], "v11_sword_dark", T_DARK_BLADE, sphere=T_SPH_SOFT, **FLAT_MAT)
    commit(sw["grip"], "v11_sword_grip", T_GRIP, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)
    commit(sw["gem"], "v11_sword_gem", T_CRYSTAL, sphere=T_SPH_CRYSTAL, **CRYSTAL_MAT)

# ------------------------------------------------------------------ switches (material morphs in the 表情 frame)
def hide_morph(name, name_e, prefixes):
    mats = [i for i, m in enumerate(M.materials) if any(m.name.startswith(p) for p in prefixes)]
    if not mats:
        return
    mo = L.pmx.MaterialMorph(name, name_e, L.pmx.Morph.CATEGORY_OHTER)
    for mi in mats:
        o = L.oc.hide_offset(L.pmx)
        o.index = mi
        mo.offsets.append(o)
    M.morphs.append(mo)
    frame = next((d for d in M.display if d.isSpecial and d.name == "表情"), None)
    if frame is not None:
        frame.data.append((1, len(M.morphs) - 1))
    print("  morph %s hides %d materials" % (name, len(mats)))


hide_morph("大剑非表示", "hide greatsword", ["v11_sword_"])
hide_morph("头冠非表示", "hide crown", ["v11_crown"])

L.save(M, os.path.abspath(args.out))
print("wrote", args.out, "| vertices", len(M.vertices), "faces", len(M.faces), "materials", len(M.materials))
