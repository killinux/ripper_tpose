# The built (not skin-grown) pieces of 水晶猎龙者 v11, each a function returning geo.Part objects in cm.
# Coordinates: x = the model's left, y = up, front = -z (PMX / MMD).  Shapes follow the MS移植 #44 previews.
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
from geo import Part, unit  # noqa: E402

X = np.array([1.0, 0.0, 0.0])
Y = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])


def curve(ctrl, n=12):
    """Catmull-Rom through the control points, n samples per span -> (m, 3)"""
    c = np.asarray(ctrl, float)
    if len(c) == 2:
        return np.linspace(c[0], c[1], n + 1)
    pts = np.vstack([c[0] * 2 - c[1], c, c[-1] * 2 - c[-2]])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(c[-1])
    return np.array(out)


def profile(n, knots):
    """piecewise-linear profile sampled at n points of 0..1: knots = [(s, value), ...]"""
    s = np.linspace(0, 1, n)
    ks, kv = zip(*knots)
    return np.interp(s, ks, kv)


def leaf_blade(ctrl, width, thick, up_hint, w, uv_rect=(0, 0, 1, 1), knots=None, n=10, ridge=0.0, tknots=None):
    """a blade along a smooth curve with a leaf-like width profile ending in a point"""
    pts = curve(ctrl, n)
    k = len(pts)
    knots = knots or [(0, 0.55), (0.25, 1.0), (0.7, 0.62), (1.0, 0.0)]
    tknots = tknots or [(0, 1.0), (0.6, 0.8), (1.0, 0.05)]
    return geo.blade(pts, profile(k, knots) * width, profile(k, tknots) * thick, up_hint, w, uv_rect, ridge)


def both(M, part):
    out = Part()
    out.add(part)
    out.add(part.mirrored(M))
    return out


# ---------------------------------------------------------------------------------------------- crown ------------

def crown(M, head_bone="頭"):
    """{"black": Part, "flame": Part, "gem": Part}: the black tiara / frames, the flame blades (horns), the forehead
    gem.  Side pieces are built for the model's left and mirrored."""
    w = geo.W1(geo.bone_index(M, head_bone))
    black, flame, gems = Part(), Part(), Part()
    # central frame: a tall black diamond on the forehead over the fringe, leaning back with the forehead
    c0 = np.array([0.0, 166.6, -11.9])
    up = unit(np.array([0.0, 1.0, 0.22]))
    ax_u = np.array([-1.0, 0.0, 0.0])                # ax_u x up = the plate's front normal (towards -z)
    outline = [(0, -4.8), (1.2, -2.2), (2.7, 0.2), (1.6, 2.8), (0, 4.8), (-1.6, 2.8), (-2.7, 0.2), (-1.2, -2.2)]
    black.add(geo.polygon_plate(outline, c0, ax_u, up, 0.9, w=w, bevel=0.35,
                                uv_fn=lambda u, v: (0.5 + u / 6.0, 0.5 - v / 10.0)))
    front = unit(np.cross(ax_u, up))
    gems.add(geo.gem(c0 + front * 0.5 + up * 0.1, up, ax_u, 4.8, 2.7, 1.0, w=w, tip=0.42))

    side, f_side = Part(), Part()
    # main black wing: from beside the frame out and up past the temple
    side.add(leaf_blade([(1.6, 165.4, -11.6), (6.0, 167.2, -10.2), (10.6, 170.2, -6.4), (14.2, 174.0, -2.6)], 4.0, 1.0,
                        Y, w, knots=[(0, 0.7), (0.3, 1.0), (0.75, 0.7), (1.0, 0.0)]))
    # lower black blade: hugs the temple and points down in front of the ear
    side.add(leaf_blade([(2.0, 164.0, -11.5), (6.4, 163.6, -9.6), (9.0, 161.4, -6.2), (9.8, 157.6, -4.4)], 2.6, 0.8,
                        Y, w, knots=[(0, 0.6), (0.35, 1.0), (0.8, 0.6), (1.0, 0.0)]))
    # band to behind the ear
    side.add(leaf_blade([(8.6, 165.4, -7.0), (9.4, 166.0, -2.0), (8.8, 166.4, 3.0)], 2.0, 0.6, Y, w,
                        knots=[(0, 0.8), (0.5, 1.0), (1.0, 0.3)]))
    # small black spikes behind the gem
    side.add(leaf_blade([(1.3, 169.6, -9.6), (1.9, 173.4, -7.8), (2.9, 177.6, -6.2)], 2.0, 0.7, X, w))
    side.add(leaf_blade([(3.0, 168.8, -8.8), (4.0, 171.6, -7.0), (5.4, 174.4, -5.4)], 1.6, 0.6, X, w))
    # short flame blade
    f_side.add(leaf_blade([(3.2, 167.6, -10.6), (6.6, 171.6, -8.6), (9.8, 176.2, -6.0), (12.2, 180.8, -4.0)], 3.8, 0.9,
                          unit((0.6, -0.5, 0)), w, uv_rect=(0.02, 0.0, 0.48, 1.0)))
    # the tall horn: rises 29 cm, leaning out and back; widest a quarter of the way up
    horn = [(4.2, 168.2, -8.6), (5.2, 174.5, -6.8), (7.0, 183.0, -4.2), (8.8, 191.0, -1.2), (10.2, 198.0, 2.4)]
    f_side.add(leaf_blade(horn, 6.0, 1.5, X, w, uv_rect=(0.52, 0.0, 0.98, 1.0),
                          knots=[(0, 0.55), (0.2, 1.0), (0.55, 0.74), (0.85, 0.38), (1.0, 0.0)], n=8))
    # the barb on the horn's outer side
    f_side.add(leaf_blade([(6.8, 176.0, -5.8), (10.0, 180.6, -4.2), (13.6, 186.4, -2.4)], 3.2, 0.9, unit((0.55, -0.6, 0)), w,
                          uv_rect=(0.02, 0.0, 0.48, 1.0)))
    black.add(both(M, side))
    flame.add(both(M, f_side))
    return {"black": black, "flame": flame, "gem": gems}


# ---------------------------------------------------------------------------------------------- crystals ---------

def crystal_cluster(base, specs, rng, w, sides=6):
    """specs = [(offset (3,), direction (3,), length, radius), ...] relative to base"""
    out = Part()
    for off, d, length, radius in specs:
        out.add(geo.crystal(np.asarray(base, float) + np.asarray(off, float), d, length, radius, rng, sides=sides, w=w,
                            jitter=0.14, taper=float(rng.uniform(0.55, 0.72)), lean=0.25, sink=0.3))
    return out


def shoulder_crystals(M, rng):
    """big orange crystals on both shoulders (the left one taller and more pointed, the right a chunkier cluster)"""
    out = Part()
    for sgn, side in ((1, "左"), (-1, "右")):
        w = [(geo.bone_index(M, side + "肩"), 0.6), (geo.bone_index(M, side + "腕"), 0.4)]
        base = np.array([sgn * 15.2, 144.6, 3.2])
        if sgn > 0:
            specs = [((0, 0, 0), (0.30 * sgn, 1.0, -0.05), 16.0, 3.8), ((3.0 * sgn, -1.4, 0.6), (0.95 * sgn, 0.55, 0.1), 10.5, 3.1),
                     ((-2.4 * sgn, 0.0, 2.4), (-0.25 * sgn, 0.9, 0.55), 10.0, 2.8), ((0.8 * sgn, -1.0, -3.2), (0.4 * sgn, 0.75, -0.65), 8.0, 2.4)]
        else:
            specs = [((0, 0, 0), (0.45 * sgn, 1.0, 0.1), 12.5, 4.4), ((3.2 * sgn, -1.2, -0.6), (1.0 * sgn, 0.45, -0.2), 10.0, 3.6),
                     ((-2.2 * sgn, 0.2, 2.6), (-0.1 * sgn, 0.95, 0.6), 9.0, 3.2), ((1.0 * sgn, -1.2, -3.4), (0.5 * sgn, 0.6, -0.8), 8.5, 2.8),
                     ((3.6 * sgn, -2.6, 2.8), (0.9 * sgn, 0.2, 0.6), 7.5, 2.6)]
        out.add(crystal_cluster(base, specs, rng, w))
    return out


def hip_fins(M):
    """the two long yellow crystal blades at the hips: flat, straight, pointing out and down, the broad face up"""
    w = geo.W1(geo.bone_index(M, "下半身"))
    fin = leaf_blade([(10.0, 107.4, 2.4), (19.0, 105.6, 0.8), (29.5, 102.6, -1.0), (41.0, 98.6, -2.8)], 11.5, 1.6,
                     unit((0.2, 0.55, -0.8)), w, knots=[(0, 0.6), (0.16, 1.0), (0.6, 0.6), (1.0, 0.0)], ridge=0.3)
    return both(M, fin)


# ---------------------------------------------------------------------------------------------- collar -----------

def collar(M, front_z):
    """{"collar": Part (double sided ring around the neck), "brooch_rim": Part, "brooch_gem": Part}"""
    b_neck, b_up = geo.bone_index(M, "首"), geo.bone_index(M, "上半身3")
    rings = [(143.8, 145.0, 7.2, 6.6, 1.5, 0.0), (146.4, 147.8, 6.0, 5.95, 1.7, 0.45), (148.2, 151.2, 5.3, 5.5, 1.8, 0.85)]
    n = 24
    part = Part()
    idx = []
    for k, (yf, yb, rx, rz, cz, wn) in enumerate(rings):
        row = []
        for j in range(n + 1):
            a = 2 * np.pi * j / n
            p = np.array([rx * np.sin(a), yf + (yb - yf) * (1 - np.cos(a)) / 2, cz - rz * np.cos(a)])
            w = [(b_neck, wn), (b_up, 1 - wn)] if 0 < wn < 1 else [(b_neck if wn >= 1 else b_up, 1.0)]
            row.append(part.vert(p, (np.sin(a), 0.2, -np.cos(a)), (k / (len(rings) - 1), 4.0 * j / n), w))
        idx.append(row)
    for k in range(len(rings) - 1):
        for j in range(n):
            part.quad(idx[k][j], idx[k + 1][j], idx[k + 1][j + 1], idx[k][j + 1])
    part.smooth_normals()
    if np.mean([part.N[v][2] for v in idx[1][:3]]) > 0:        # front vertices must face -z
        part.F = [(a, c, b) for a, b, c in part.F]
        part.N = [-q for q in part.N]
    w = geo.W1(b_up)
    c0 = np.array([0.0, 142.6, front_z - 0.7])
    up = unit(np.array([0.0, 1.0, 0.25]))
    ax_u = np.array([-1.0, 0.0, 0.0])
    rim = geo.polygon_plate([(0, -3.4), (2.9, 1.2), (1.4, 2.4), (0, 1.8), (-1.4, 2.4), (-2.9, 1.2)], c0, ax_u, up, 0.7, w=w, bevel=0.25)
    front = unit(np.cross(ax_u, up))
    gem = geo.gem(c0 + front * 0.35 - up * 0.3, up, ax_u, 4.0, 3.0, 0.9, w=w, tip=0.15)
    return {"collar": part, "brooch_rim": rim, "brooch_gem": gem}


# ---------------------------------------------------------------------------------------------- hands ------------

def claws(M, skin_P, skin_W):
    """orange claws over the fingertips; skin_P (n, 3) cm and skin_W = per-vertex [(bone, w)] of the body skin"""
    out = Part()
    names = [b.name for b in M.bones]
    for side in ("左", "右"):
        for finger, length in (("親指２", 2.2), ("人指３", 2.6), ("中指３", 2.8), ("薬指３", 2.6), ("小指３", 2.2)):
            name = side + finger
            if name not in names:
                continue
            bi = names.index(name)
            head = np.array(M.bones[bi].location, float) * geo.CM
            sel = [i for i, w in enumerate(skin_W) if any(b == bi and x > 0.5 for b, x in w)]
            if len(sel) < 4:
                continue
            P = skin_P[sel]
            d = unit(P.mean(0) - head)
            t = (P - head) @ d
            tip = head + d * t.max()
            rad = np.linalg.norm((P - head) - np.outer(t, d), axis=1)
            r0 = float(np.percentile(rad, 90)) * 1.15 + 0.08
            seg = float(t.max())
            pts = [head + d * (seg * 0.35), tip - d * 0.25, tip + d * (length * 0.55), tip + d * length]
            out.add(geo.tube(pts, [r0, r0 * 0.95, r0 * 0.5, 0.02], sides=6, w=geo.W1(bi), up_hint=Y).faceted()
                    .set_uv_rect(0.3, 0.05, 0.45, 0.6))
    return out


def elbow_spikes(M):
    out = Part()
    for sgn, side in ((1, "左"), (-1, "右")):
        e = geo.bone_pos(M, side + "ひじ")
        a = unit(e - geo.bone_pos(M, side + "腕"))             # along the upper arm
        d = unit(a * 0.55 + Z * 0.8 + Y * 0.05)
        w = geo.W1(geo.bone_index(M, side + "ひじ"))
        base = e + Z * 2.4
        out.add(leaf_blade([base - d * 1.5, base + d * 3.5, base + d * 8.5], 3.4, 1.4, Y, w,
                           knots=[(0, 0.8), (0.3, 1.0), (1.0, 0.0)]))
    return out


# ---------------------------------------------------------------------------------------------- knees ------------

def knee_guards(M, r_knee):
    """{"plate": Part, "gem": Part}: a crescent shield bent round each knee with a diamond gem"""
    plates, gems = Part(), Part()
    for sgn, side in ((1, "左"), (-1, "右")):
        k = geo.bone_pos(M, side + "ひざ")
        names = [b.name for b in M.bones]
        thigh = names.index(side + "足D") if side + "足D" in names else names.index(side + "足")
        shin = names.index(side + "ひざD") if side + "ひざD" in names else names.index(side + "ひざ")
        w = [(thigh, 0.45), (shin, 0.55)]
        R = r_knee + 1.1
        outer = X * sgn
        front = -Z
        axis0 = np.array([k[0], k[1], k[2]])

        def bend(p, R=R, outer=outer, axis0=axis0):
            u, v, h = p                                   # arc cm, height cm, radial offset cm
            a = u / R
            return axis0 + Y * v + (front * np.cos(a) + outer * np.sin(a)) * (R + h)

        outline = [(0.0, -7.2), (3.6, -3.6), (5.6, 0.8), (6.2, 5.6), (3.8, 3.4), (0.0, 2.6), (-3.8, 3.4), (-6.2, 5.6),
                   (-5.6, 0.8), (-3.6, -3.6)]
        plate = geo.polygon_plate(outline, (0, 0, 0), (1, 0, 0), (0, 1, 0), 0.8, w=w, bevel=0.3,
                                  uv_fn=lambda u, v: (0.5 + u / 13.0, 0.52 - v / 14.0))
        geo.warp(plate, bend)            # the plate is small: its flat triangles follow the bend closely enough
        plates.add(plate)
        g = geo.gem((0, -1.2, 0.5), (0, 1, 0), (1, 0, 0), 5.0, 3.0, 1.0, w=w, tip=0.0)
        geo.warp(g, bend)
        gems.add(g)
    return {"plate": plates, "gem": gems}


# ---------------------------------------------------------------------------------------------- skirt ------------

def _panel(M, theta_deg, root_y, radius, length, hw_knots, flare_deg, thick, cup, leg_bone, lower_bone, w_max,
           n_len=10, n_wid=6, end_fn=None, bow=0.05, uv_rect=(0, 0, 1, 1), s0=0.0, s1=1.0, lift=0.0, centre=(0.0, 0.0),
           w_gain=1.3):
    """one hanging sheet at angle theta (0 = front, 90 = the model's left).  s0..s1 = the part of the full panel
    this sheet covers (lames of a stacked plate share one spine)."""
    th = np.radians(theta_deg)
    out = np.array([np.sin(th), 0.0, -np.cos(th)])
    tang = np.array([np.cos(th), 0.0, np.sin(th)])
    fl = np.radians(flare_deg)
    hang = unit(-Y * np.cos(fl) + out * np.sin(fl))
    out_n = unit(out * np.cos(fl) + Y * np.sin(fl))
    root = np.array([centre[0], root_y, centre[1]]) + out * radius
    ss = np.linspace(s0, s1, 12)
    spine = np.array([root + hang * (length * s) + out_n * (bow * length * s * s) for s in ss])
    ks, kv = zip(*hw_knots)

    def w_fn(s_local):
        s = s0 + (s1 - s0) * s_local
        wl = float(np.clip(0.10 + w_gain * s, 0, w_max))
        return [(lower_bone, 1 - wl), (leg_bone, wl)]

    knots_local = [(float(q), float(np.interp(s0 + (s1 - s0) * q, ks, kv))) for q in np.linspace(0, 1, 9)]
    return geo.leaf_sheet(spine, tang, out_n, knots_local, thick, w_fn, n_len=n_len, n_wid=n_wid, cup=cup,
                          end_fn=end_fn, uv_rect=uv_rect, lift=lift)


def skirt(M, hip_radius, centre):
    """{"petal": Part (bright orange), "petal_dark": Part (dark red-orange), "plate": Part (black lames)};
    hip_radius(theta_deg, y) -> cm from the hip centre line to the skin."""
    names = [b.name for b in M.bones]
    lower = names.index("下半身")
    petals, petals_dark, plates = Part(), Part(), Part()

    def notch_w(u):                 # W-shaped end: two points at |u| = 0.5
        return 1.0 - 0.10 * abs(abs(u) - 0.5) * 2

    def vee(u):                     # lame end: a shallow V, longest in the middle
        return 1.0 - 0.10 * abs(u)

    for sgn, side in ((1, "左"), (-1, "右")):
        leg = names.index(side + "足D") if side + "足D" in names else names.index(side + "足")

        def P(theta, root_y, gap, length, hw, flare, **k):
            th = theta * sgn
            return _panel(M, th, root_y, hip_radius(th, root_y) + gap, length, hw, flare, leg_bone=leg, lower_bone=lower,
                          centre=centre, **k)

        # ---- petals (under the plates): bright ones in front and along the back plate, dark ones behind
        pet = dict(thick=0.35, cup=0.18, w_max=0.92, n_wid=8)
        petals.add(P(27, 100.8, 1.3, 47, [(0, 4.6), (0.3, 6.6), (0.8, 6.0), (1, 4.4)], 7, end_fn=notch_w, **pet))
        petals.add(P(60, 103.0, 1.5, 58, [(0, 4.6), (0.3, 7.0), (0.75, 5.4), (1, 0.0)], 21, **pet))
        petals_dark.add(P(103, 104.0, 1.2, 64, [(0, 4.6), (0.3, 7.4), (0.75, 5.6), (1, 0.0)], 27, **pet))
        petals_dark.add(P(127, 104.5, 1.2, 62, [(0, 4.6), (0.3, 7.2), (0.75, 5.4), (1, 0.0)], 22, **pet))
        petals.add(P(164, 105.5, 1.6, 64, [(0, 2.8), (0.4, 3.8), (0.85, 2.6), (1, 0.0)], 9, **pet))
        # ---- black plates: stacks of lames sharing one spine
        pl = dict(thick=0.6, cup=0.22, w_max=0.92, uv_rect=(0, 0, 1, 1), n_wid=8)
        # front tasset: three lames, the last one pointed
        hw = [(0, 5.6), (0.5, 6.9), (0.72, 6.2), (1, 0.0)]
        for a, b, e in ((0.0, 0.36, vee), (0.30, 0.66, vee), (0.60, 1.0, None)):
            plates.add(P(27, 101.4, 2.6, 32, hw, 10, s0=a, s1=b, end_fn=e, lift=0.9, n_len=5, **pl))
        # side plate: two short lames, then the long blade
        hw = [(0, 5.6), (0.3, 6.8), (0.7, 4.6), (1, 0.0)]
        for a, b, e in ((0.0, 0.16, vee), (0.12, 0.30, vee), (0.26, 1.0, None)):
            plates.add(P(80, 103.5, 2.9, 62, hw, 26, s0=a, s1=b, end_fn=e, lift=0.9, n_len=6 if b < 1 else 10, **pl))
        # back plate: three lames, then a long smooth plate
        hw = [(0, 8.4), (0.25, 9.6), (0.6, 7.2), (1, 0.0)]
        for a, b, e in ((0.0, 0.13, vee), (0.10, 0.25, vee), (0.22, 0.38, vee), (0.34, 1.0, None)):
            plates.add(P(142, 105.0, 2.7, 58, hw, 16, s0=a, s1=b, end_fn=e, lift=0.9, n_len=5 if b < 1 else 10, **pl))
    return {"petal": petals, "petal_dark": petals_dark, "plate": plates}


def side_locks(M):
    """the long straight locks framing the face (Eve's hair has none): three thin strips each side, on the head bone"""
    w = geo.W1(geo.bone_index(M, "頭"))
    out = Part()
    for sgn in (1, -1):
        for dx, dz, top, bottom, hw in ((0.0, 0.0, 164.0, 146.8, 1.25), (0.9, 0.9, 163.4, 148.6, 1.0),
                                        (-0.7, -0.5, 163.0, 150.2, 0.9)):
            x0 = sgn * (7.5 + dx)
            spine = curve([(x0 * 0.94, top, -7.4 + dz), (x0 * 1.0, top - 5.5, -7.9 + dz), (x0 * 1.02, top - 11.0, -8.0 + dz),
                           (x0 * 1.04, bottom, -7.6 + dz)], 5)
            side = unit(np.array([0.35 * sgn, 0.0, -1.0]))             # across the strip: mostly front-back
            outn = unit(np.array([1.0 * sgn, 0.0, 0.35]))              # facing away from the cheek
            out.add(geo.leaf_sheet(spine, side, outn, [(0, hw * 0.8), (0.3, hw), (0.85, hw * 0.75), (1, 0.05)], 0.25,
                                   lambda s: w, n_len=8, n_wid=4, cup=0.35))
    return out


# ---------------------------------------------------------------------------------------------- back -------------

def back_details(M, back_z):
    """{"black": Part, "flame": Part, "gem": Part, "hilt": Part}; back_z(x, y) -> z of the back surface (cm)"""
    names = [b.name for b in M.bones]
    up2, up1 = names.index("上半身2"), names.index("上半身")
    up3 = names.index("上半身3") if "上半身3" in names else up2
    black, flame, gems, hilt = Part(), Part(), Part(), Part()
    back = Z
    ax_u = X                      # X x Y = +Z: plates face the back

    def wy(y):
        if y > 126:
            return geo.W1(up3)
        if y > 116:
            return geo.W1(up2)
        return geo.W1(up1)

    # the gem plate between the shoulder blades
    y0 = 136.0
    c0 = np.array([0.0, y0, back_z(0, y0) + 0.9])
    black.add(geo.polygon_plate([(0, -3.8), (3.4, -1.6), (3.9, 1.6), (0, 3.6), (-3.9, 1.6), (-3.4, -1.6)], c0, ax_u, Y, 0.8,
                                w=wy(y0), bevel=0.3, uv_fn=lambda u, v: (0.5 + u / 9.0, 0.5 - v / 9.0)))
    gems.add(geo.gem(c0 + back * 0.4, Y, ax_u, 5.0, 4.6, 1.0, w=wy(y0), tip=0.35))
    # spine lames
    for y in (129.6, 125.2, 120.8, 116.4):
        c = np.array([0.0, y, back_z(0, y) + 0.8])
        black.add(geo.polygon_plate([(-2.4, -2.6), (0, -3.3), (2.4, -2.6), (2.7, 2.3), (-2.7, 2.3)], c, ax_u,
                                    unit(Y - Z * 0.12), 0.7, w=wy(y), bevel=0.25,
                                    uv_fn=lambda u, v: (0.5 + u / 6.5, 0.5 - v / 6.5)))
    # two flame inlays forming a V on the lower back
    for sgn in (1, -1):
        pts = [(sgn * 4.6, 116.0), (sgn * 3.0, 111.5), (sgn * 0.9, 106.6)]
        ctrl = [(x, y, back_z(x, y) + 0.7) for x, y in pts]
        flame.add(leaf_blade(ctrl, 2.4, 0.7, X * sgn, wy(110), uv_rect=(0.02, 0.0, 0.48, 1.0),
                             knots=[(0, 0.7), (0.3, 1.0), (1.0, 0.0)]))
    # the waist ornament
    y1 = 107.2
    c1 = np.array([0.0, y1, back_z(0, y1) + 0.9])
    black.add(geo.polygon_plate([(0, -3.0), (2.6, -1.2), (2.6, 1.4), (0, 2.8), (-2.6, 1.4), (-2.6, -1.2)], c1, ax_u, Y, 0.8,
                                w=wy(y1), bevel=0.3, uv_fn=lambda u, v: (0.5 + u / 6.5, 0.5 - v / 7.0)))
    gems.add(geo.gem(c1 + back * 0.4, Y, ax_u, 3.2, 2.6, 0.8, w=wy(y1), tip=0.1))
    # the two short swords crossed on the back: sheath end low on the far side, hilt out past the shoulder
    w2 = geo.W1(up2)
    for sgn in (1, -1):
        tip = np.array([-sgn * 11.0, 112.0, back_z(-sgn * 9.0, 113.0) + 2.2])
        mid = np.array([sgn * 8.0, 127.5, back_z(sgn * 8.0, 127.5) + 2.4])
        end = mid + unit(mid - tip + Z * 2.0) * 21.0
        d = unit(end - mid)
        black.add(geo.tube([tip, tip + (mid - tip) * 0.5, mid], [0.5, 1.2, 1.35], sides=8, w=w2))
        black.add(geo.tube([mid - d * 0.6, mid + d * 0.6], [2.5, 2.5], sides=8, w=w2))                 # guard
        hilt.add(geo.tube([mid + d * 0.6, end - d * 2.5], [0.95, 0.85], sides=8, w=w2, cap=False))
        gems.add(geo.crystal(end - d * 2.8, d, 4.4, 1.5, np.random.default_rng(3 + sgn), sides=6, w=w2, sink=0.1))
    return {"black": black, "flame": flame, "gem": gems, "hilt": hilt}


# ---------------------------------------------------------------------------------------------- sword ------------

def greatsword(M, bone_name="上半身2", centre=(5.0, 104.0, 17.0), tilt_deg=32.0, length=160.0):
    """the crystal greatsword slung on the back: handle up over the right shoulder, tip down by the left calf.
    {"blade": Part, "dark": Part, "grip": Part, "gem": Part}.  Built along a local axis (a = cm from the pommel end
    of the grip), then turned about z and moved to `centre` (the point half way along)."""
    w = geo.W1(geo.bone_index(M, bone_name))
    axis = unit(np.array([np.sin(np.radians(tilt_deg)), -np.cos(np.radians(tilt_deg)), 0.0]))   # pommel -> tip
    wide = unit(np.cross(Z, axis))                                                              # across the blade
    origin = np.asarray(centre, float) - axis * (length / 2)

    def at(a, across=0.0, back=0.0):
        return origin + axis * a + wide * across + Z * back

    blade, dark, grip, gems = Part(), Part(), Part(), Part()
    # blade: a 42 .. 158
    aa = np.array([42, 50, 62, 80, 100, 120, 138, 150, 158.0])
    ww = np.array([9.0, 12.5, 14.5, 14.0, 12.8, 11.0, 8.4, 5.0, 0.0])
    tt = np.array([2.6, 2.6, 2.6, 2.4, 2.2, 1.9, 1.5, 1.0, 0.2])
    blade.add(geo.blade([at(a) for a in aa], ww, tt, wide, w, ridge=0.34))
    # black scale plate over the blade root + spikes pointing back along both edges
    dark.add(geo.blade([at(a, 0, 0) for a in (40, 48, 60, 72)], [10.5, 14.5, 12.0, 0.0], [3.6, 3.8, 3.4, 2.8], wide, w,
                       ridge=0.4))
    for k, a in enumerate((48, 56, 64, 72)):
        for sgn in (1, -1):
            hw = float(np.interp(a, aa, ww)) / 2
            base = at(a, sgn * (hw - 0.8), 0.0)
            tipp = at(a - 6.0, sgn * (hw + 2.6 - k * 0.3), 0.0)
            dark.add(leaf_blade([base, (base + tipp) / 2 + axis * 0.8, tipp], 3.2, 1.5, axis, w,
                                knots=[(0, 0.9), (0.3, 1.0), (1.0, 0.0)]))
    # guard: a dragon-wing plate across, hooks towards the blade
    guard = [(-16.5, 4.5), (-13.0, 0.5), (-7.0, -2.2), (-2.6, -3.4), (2.6, -3.4), (7.0, -2.2), (13.0, 0.5), (16.5, 4.5),
             (11.5, 2.8), (6.0, 3.6), (0.0, 6.5), (-6.0, 3.6), (-11.5, 2.8)]
    dark.add(geo.polygon_plate(guard, at(37.5), -wide, axis, 3.0, w=w, bevel=0.6,
                               uv_fn=lambda u, v: (0.5 + u / 36.0, 0.5 - v / 12.0)))
    gems.add(geo.gem(at(38.5, 0, 1.6), axis, wide, 5.0, 3.2, 1.0, w=w, tip=0.1))
    gems.add(geo.gem(at(38.5, 0, -1.6), axis, -wide, 5.0, 3.2, 1.0, w=w, tip=0.1))
    # grip and pommel
    grip.add(geo.tube([at(1.5), at(35.0)], [1.45, 1.6], sides=10, w=w))
    dark.add(geo.tube([at(0.0), at(2.4)], [2.3, 2.1], sides=8, w=w))
    gems.add(geo.crystal(at(0.5), -axis, 8.0, 2.0, np.random.default_rng(9), sides=6, w=w, sink=0.12))
    return {"blade": blade, "dark": dark, "grip": grip, "gem": gems}


def forearm_fins(M):
    """three black fins along the outer / back side of each forearm, sweeping towards the elbow"""
    out = Part()
    for sgn, side in ((1, "左"), (-1, "右")):
        e, wr = geo.bone_pos(M, side + "ひじ"), geo.bone_pos(M, side + "手首")
        a = unit(wr - e)
        length = float(np.linalg.norm(wr - e))
        outer = unit(np.cross(a, -Z) * sgn * 1.0)
        if outer[1] < 0:
            outer = -outer                      # the arm's upper / outer side in the A pose
        d_out = unit(outer * 0.55 + Z * 0.85)
        w = geo.W1(geo.bone_index(M, side + "ひじ"))
        for t, ln in ((0.30, 5.5), (0.52, 4.8), (0.74, 4.0)):
            base = e + a * (length * t) + d_out * 2.6
            tip = base + unit(d_out * 0.75 - a * 0.65) * ln
            out.add(leaf_blade([base - d_out * 1.0 + a * 1.2, base, tip], 2.6, 1.0, a, w, knots=[(0, 0.9), (0.4, 1.0), (1.0, 0.0)]))
    return out
