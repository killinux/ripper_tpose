"""Body colliders fitted inside the skin, and cloth / hair that collides with them, for an existing PMX.

Why (Vindictus Fiona, 2026-10-06): the exporters measured the body colliders on the DRESSED mesh - Convert_to_MMD5's
add_body_rigids takes the 85th percentile of every vertex weighted to the bone, armour included, and
mmd_cloth_physics sizes its anchors the same way.  Fiona's upper-arm capsule came out twice the arm, the thigh 1.6x,
and the skirt-scarf anchor on 上半身5 a 15 cm ball around the neck.  Nearly every cloth and hair body therefore
started inside a collider, mmd_cloth_physics put those in its "near" group (10), which collides with nothing, and no
hair, skirt or scarf of the model ever touched the body: the legs went through the skirt, the hair through the back.

What it does:
1. every body collider (a bone-following body on a standard MMD body bone) is refitted inside the nude skin given by
   ``--skin`` (material names, wildcards allowed):
   - arms and legs: a capsule along the centres of the limb's cross-sections (the bone is seldom in the middle of
     the limb), its radius the narrow side of the skin there.  A limb that tapers (Fiona's thigh: 8.5 cm at the top,
     4 cm at the knee) is split in two when the model has a second collider on it - 足D on the thigh, 腕捩 on the
     upper arm move exactly like 足 / 腕 - the upper half on one, the lower half on the other;
   - shoulders: along 肩 -> 腕 under the shoulder top; neck: 首 -> 頭; head: a ball inside the skull;
   - torso: capsules lying left-right, each the largest that stays inside the body's side profile (front / back,
     breasts left out) and its width; a spine bone with no collider between two far-apart ones gets one;
2. every dynamic body except the breasts gets the collision it can take at rest.  A body that starts inside a
   collider is first made thinner (a box on one axis, a capsule its radius - the shape only matters for collisions);
   when that is not enough it stops colliding with that CLASS of collider only (head, neck, torso, arms, legs).
   MMD filters collisions by group, so each class is a group and each combination of classes a group of its own.
   Bodies are never added to chains, removed or moved, and joints are untouched.

    python cloth_collision_pmx.py in.pmx out.pmx --skin "*BaseBody*,*Face01*_nude"
    python cloth_collision_pmx.py in.pmx - --skin ... --dry-run
    python cloth_collision_pmx.py outfit.pmx out.pmx --colliders-from full.pmx

--colliders-from: a model with no nude body (an outfit showing only some skin) takes the colliders of a model on the
same rig that has them fitted (Vindictus: the outfits <- Fiona_full): limb colliders ride their joint line, the rest
move with their bone; colliders the reference lacks (anchors sized on the outfit) shrink to ANCHOR_RADIUS.
clip_test_blender.py measures the clipping in a dance.

Needs only Python + numpy and the ``pmx`` module inside mmd_tools (no Blender); ``--pmx-module`` points at it when
the search misses.  Units are PMX units (1 = 8 cm at mmd_tools' usual 0.08 import scale).
"""
import argparse
import fnmatch
import glob
import importlib.util
import math
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

DEFAULTS = {
    "inset": 0.02,          # colliders end this far inside the skin
    "tolerance": 0.03,      # a dynamic body may start this deep in a collider and still collide with it
    "min_shrink": 0.35,     # a body is thinned to no less than this share of its size
    # breast bones / bodies, left alone: a name starting with breast, after at most one word (Breast_L02,
    # breast_physics_02_l, Bip001 Breast_L02, ROE's Point_breast_UL helpers - not Vindictus PCF_008's shirt chains
    # Outfit008_upper_breast_shirt_a_01_l, which are cloth), ROE's other spellings (g04 chest_L02, Kart / Misa
    # OPAI_L02, Inase Xtra01Opp02 / Xtra0102), and the usual MMD names.  Fiona and Inase a08 come out as before.
    "bust": r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$",
}
SIDES = ("左", "右")
# collider classes: name -> bones
CLASSES = (("head", ("頭",)),
           ("neck", ("首", "首1")),
           ("torso", ("上半身", "上半身1", "上半身2", "上半身3", "上半身4", "上半身5", "下半身", "腰")),
           ("arms", tuple(s + n for s in SIDES for n in ("肩", "腕", "腕捩", "ひじ", "手捩", "手首"))),
           ("legs", tuple(s + n for s in SIDES for n in ("足", "足D", "ひざ", "ひざD", "足首", "足首D"))))
CLASS_OF = {b: c for c, bones in CLASSES for b in bones}
SPINE = ("下半身", "上半身", "上半身1", "上半身2", "上半身3", "上半身4", "上半身5")
ANCHOR_RADIUS = 0.25        # --colliders-from: a collider the reference lacks shrinks to this (PMX units, 2 cm)


# -- pmx module ---------------------------------------------------------------------------------------------------
def find_pmx_module(explicit=None):
    if explicit:
        return explicit
    root = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py",
                    "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                    "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
        hits = sorted(glob.glob(os.path.join(root, pattern)))
        if hits:
            return hits[0]
    raise SystemExit("mmd_tools' core/pmx/__init__.py not found; pass --pmx-module")


def load_pmx_module(path):
    spec = importlib.util.spec_from_file_location("mmd_pmx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def weights_of(pmx, v):
    """[(bone index, weight)] of a vertex, any deform type."""
    w = v.weight
    bones = w.bones if isinstance(w.bones, (list, tuple)) else [w.bones]
    ws = w.weights
    if isinstance(ws, pmx.BoneWeightSDEF):
        ws = [ws.weight, 1.0 - ws.weight]
    elif not isinstance(ws, (list, tuple)):
        ws = [ws]
    if len(bones) == 1:
        ws = [1.0]
    elif len(bones) == 2 and len(ws) == 1:
        ws = [ws[0], 1.0 - ws[0]]
    return [(b, float(x)) for b, x in zip(bones, ws) if b is not None and b >= 0 and x > 0]


# -- geometry (PMX space) -----------------------------------------------------------------------------------------
def rot(r):
    """Rigid / joint rotation (radians) -> matrix in PMX space, read as mmd_tools reads it (Blender Euler
    (-x, -z, -y) in YXZ order on y/z-swapped axes) = Ry @ Rx @ Rz.  Checked against mmd_tools' imported objects."""
    rx, ry, rz = r
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def euler_of(R):
    """rot() inverted."""
    rx = math.asin(max(-1.0, min(1.0, -R[1, 2])))
    if abs(math.cos(rx)) > 1e-6:
        return rx, math.atan2(R[0, 2], R[2, 2]), math.atan2(R[1, 0], R[1, 1])
    return rx, math.atan2(-R[2, 0], R[0, 0]), 0.0


class Shape:
    """A rigid body's shape: kind 0 sphere (size[0] radius), 1 box (half extents), 2 capsule (radius, height
    along the local Y axis)."""

    def __init__(self, kind, c, R, size):
        self.kind = int(kind)
        self.c = np.array(c, float)
        self.R = np.array(R, float)
        self.size = np.array(list(size) + [0.0] * (3 - len(size)), float)[:3]
        if self.kind == 2:
            ax = self.R[:, 1] * self.size[1] * 0.5
            self.seg = (self.c - ax, self.c + ax)
        elif self.kind == 0:
            self.seg = (self.c, self.c)
        else:
            self.seg = None
        self.r = self.size[0] if self.kind != 1 else 0.0

    @classmethod
    def of(cls, rigid):
        return cls(rigid.type, rigid.location, rot(rigid.rotation), rigid.size)

    def samples(self, n=48):
        a, b = self.seg
        return a + (b - a) * np.linspace(0, 1, n)[:, None]


def point_seg(p, a, b):
    ab = b - a
    L = ab @ ab
    t = np.clip(((p - a) @ ab) / L, 0, 1) if L > 1e-12 else np.zeros(len(p))
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def signed_box(p, s):
    ex = np.abs((p - s.c) @ s.R) - s.size
    return np.linalg.norm(np.maximum(ex, 0), axis=1) + np.minimum(np.max(ex, axis=1), 0)


def box_samples(s, k=5):
    g = np.linspace(-1, 1, k)
    return s.c + (np.array([[x, y, z] for x in g for y in g for z in g]) * s.size) @ s.R.T


def depth(d, c):
    """How far shape d sits inside shape c (> 0 = overlap)."""
    if c.kind != 1 and d.kind != 1:
        return c.r + d.r - point_seg(d.samples(), *c.seg).min()
    if c.kind != 1:
        return c.r - signed_box(c.samples(), d).min()
    if d.kind != 1:
        return d.r - signed_box(d.samples(), c).min()
    return -signed_box(box_samples(d), c).min()


def surface_distance(p, s):
    """Signed distance of points to the shape's surface (< 0 inside)."""
    return signed_box(p, s) if s.kind == 1 else point_seg(p, *s.seg) - s.r


def frame_along(y):
    """A rotation whose local Y is the direction y."""
    y = y / np.linalg.norm(y)
    ref = np.array([0, 0, 1.0]) if abs(y[2]) < 0.9 else np.array([1.0, 0, 0])
    x = np.cross(y, ref)
    x /= np.linalg.norm(x)
    return np.stack([x, y, np.cross(x, y)], axis=1)


def capsule_between(a, b, r, extend=0.0):
    """Capsule from a to b; its round ends reach ``extend`` x r past a and b."""
    v = b - a
    L = float(np.linalg.norm(v))
    h = max(L * 0.35, L - 2 * r + 2 * extend * r)
    return Shape(2, (a + b) * 0.5, frame_along(v), (r, h, 0.0))


# -- the skin -----------------------------------------------------------------------------------------------------
class Skin:
    """The nude skin's vertices and, per vertex, the body part its strongest bone belongs to."""

    def __init__(self, pmx, model, patterns, bust_rx):
        self.model = model
        names = [m.name for m in model.materials]
        picked, start, verts = [], 0, set()
        for k, mat in enumerate(model.materials):
            n = mat.vertex_count
            if any(fnmatch.fnmatchcase(mat.name, p) for p in patterns):
                picked.append(names[k])
                for f in model.faces[start // 3:(start + n) // 3]:
                    verts.update(f)
            start += n
        if not verts:
            raise SystemExit("--skin matched no material; materials are: %s" % ", ".join(names))
        self.materials = picked
        self.index = np.array(sorted(verts))
        self.co = np.array([model.vertices[v].co for v in self.index], float)
        self.bones = model.bones
        self.bust = re.compile(bust_rx, re.IGNORECASE)
        cache = {}
        parts = []
        for v in self.index:
            w = weights_of(pmx, model.vertices[v])
            b = max(w, key=lambda t: t[1])[0] if w else -1
            if b not in cache:
                cache[b] = self.part_of(b)
            parts.append(cache[b])
        self.part = np.array(parts)

    def ancestry(self, b):
        """Bone names up the parents, through a D bone's grant (rate 1) to the FK bone it copies."""
        out = set()
        for _ in range(128):
            if b is None or b < 0:
                break
            bone = self.bones[b]
            out.add(bone.name)
            at = getattr(bone, "additionalTransform", None)
            if at and abs(at[1] - 1.0) < 1e-3 and getattr(bone, "hasAdditionalRotate", False):
                b = at[0]
            else:
                b = bone.parent
        return out

    def part_of(self, b):
        s = self.ancestry(b)
        for side in SIDES:
            if s & {side + "ひじ", side + "手捩", side + "手首"}:
                return side + "forearm"
            if s & {side + "腕", side + "腕捩"}:
                return side + "upperarm"
            if s & {side + "ひざ", side + "ひざD", side + "足首", side + "足首D"}:
                return side + "shin"
            if s & {side + "足", side + "足D"}:
                return side + "thigh"
            if side + "肩" in s:
                return side + "shoulder"
        if "頭" in s:
            return "head"
        if s & {"首", "首1"}:
            return "neck"
        if any(self.bust.search(x) for x in s):
            return "breast"
        if "下半身" in s and "上半身" not in s:
            return "hips"
        return "torso"

    def of(self, *parts):
        return np.isin(self.part, list(parts))


# -- fitting ------------------------------------------------------------------------------------------------------
def limb_fit(co, a, b, t0=0.05, t1=0.95, bins=9):
    """Axis through the centres of the limb's cross-sections and the skin's radius profile along it.
    -> (a', b', profile of 10 values: the 20th percentile of the distance to the axis per tenth) or None."""
    v = b - a
    L = float(np.linalg.norm(v))
    y = v / L
    t = ((co - a) @ y) / L
    keep = (t > t0) & (t < t1)
    P, t = co[keep], t[keep]
    if len(P) < 24:
        return None
    R = frame_along(y)
    u, w = R[:, 0], R[:, 2]
    cs, ts = [], []
    for k in range(bins):
        lo, hi = t0 + (t1 - t0) * k / bins, t0 + (t1 - t0) * (k + 1) / bins
        q = P[(t >= lo) & (t < hi)]
        if len(q) < 8:
            continue
        pu, pw = (q - a) @ u, (q - a) @ w
        cs.append(((np.percentile(pu, 5) + np.percentile(pu, 95)) / 2,
                   (np.percentile(pw, 5) + np.percentile(pw, 95)) / 2))
        ts.append((lo + hi) / 2)
    if len(ts) < 3:
        return None
    ts, cs = np.array(ts), np.array(cs)
    coef, *_ = np.linalg.lstsq(np.stack([np.ones_like(ts), ts], axis=1), cs, rcond=None)

    def at(tt):
        return a + y * (tt * L) + u * (coef[0, 0] + coef[1, 0] * tt) + w * (coef[0, 1] + coef[1, 1] * tt)

    a2, b2 = at(0.0), at(1.0)
    rad = point_seg(P, a2, b2)
    y2 = (b2 - a2) / np.linalg.norm(b2 - a2)
    tt = ((P - a2) @ y2) / np.linalg.norm(b2 - a2)
    prof = np.array([np.percentile(rad[(tt >= k / 10) & (tt < (k + 1) / 10)], 20)
                     if ((tt >= k / 10) & (tt < (k + 1) / 10)).sum() > 8 else np.nan for k in range(10)])
    return a2, b2, prof


def span_radius(prof, t0, t1, pct=25):
    vals = [prof[k] for k in range(10) if t0 <= (k + 0.5) / 10 <= t1 and not np.isnan(prof[k])]
    return float(np.percentile(vals, pct)) if vals else None


def torso_profile(skin, step=0.1):
    """Per height: half width, front and back of the torso (breasts left out of the front)."""
    sel = skin.of("torso", "hips", "breast", "neck", SIDES[0] + "shoulder", SIDES[1] + "shoulder",
                  SIDES[0] + "thigh", SIDES[1] + "thigh")
    P, parts = skin.co[sel], skin.part[sel]
    ys = np.arange(P[:, 1].min() + step, P[:, 1].max() - step, step)
    prof = []
    for y in ys:
        s = np.abs(P[:, 1] - y) < step
        q, pp = P[s], parts[s]
        if len(q) < 12:
            prof.append((y, np.nan, np.nan, np.nan))
            continue
        hw = np.percentile(np.abs(q[:, 0]), 97)
        mid = (np.abs(q[:, 0]) < 0.35 * hw) & (pp != "breast")
        if mid.sum() < 4:
            prof.append((y, hw, np.nan, np.nan))
            continue
        prof.append((y, hw, np.percentile(q[mid, 2], 3), np.percentile(q[mid, 2], 97)))
    prof = np.array(prof)
    # a slice far off its neighbours is the sampling's, not the body's: a coarse mesh (ROE Inase's back) can leave a
    # slice with no vertex on one side (front -1.42, back -1.29 where the torso is 1.8 deep), a dense patch (the
    # crotch) pulls the width percentile in.  Such values become unknown and the capsules ignore them.
    depth = prof[:, 3] - prof[:, 2]
    for k, y in enumerate(prof[:, 0]):
        near = np.abs(prof[:, 0] - y) < 0.35
        if near.sum() < 3:
            continue
        if not np.isnan(depth[k]) and depth[k] < 0.6 * np.nanmedian(depth[near]):
            prof[k, 2:] = np.nan
        if not np.isnan(prof[k, 1]) and prof[k, 1] < 0.85 * np.nanmedian(prof[near, 1]):
            prof[k, 1] = np.nan
    return prof


def torso_capsule(prof, y_nom, inset, shift=(-0.5, 0.2)):
    """The largest capsule lying along X, centred near y_nom, inside the side profile and the width there.
    -> (Shape, y, r, half straight length) or None."""
    found = []
    for y_c in np.arange(y_nom + shift[0], y_nom + shift[1] + 1e-6, 0.05):
        k = np.argmin(np.abs(prof[:, 0] - y_c))
        hw, front, back = prof[k, 1:]
        if np.isnan(front) or np.isnan(back):
            continue
        zc = (front + back) / 2
        r = (back - front) / 2 - inset
        while r > 0.1:
            near = np.abs(prof[:, 0] - y_c) < r
            dy = prof[near, 0] - y_c
            half = np.sqrt(np.maximum(r * r - dy * dy, 0))
            f, b_, w = prof[near, 2], prof[near, 3], prof[near, 1]
            ok = np.isnan(f) | ((zc - half >= f + inset) & (zc + half <= b_ - inset))
            if ok.all() and not np.isnan(w).all():
                straight = np.nanmin(w - inset - half)
                if straight >= 0:
                    break
            r -= 0.02
        if r <= 0.1:
            continue
        near = np.abs(prof[:, 0] - y_c) < r
        dy = prof[near, 0] - y_c
        half = np.sqrt(np.maximum(r * r - dy * dy, 0))
        straight = max(0.0, float(np.nanmin(prof[near, 1] - inset - half)))
        found.append((r - 0.5 * abs(y_c - y_nom), y_c, zc, r, straight))
    if not found:
        return None

    def shape(c):
        return Shape(2, (0.0, c[1], c[2]), rot((0.0, 0.0, math.pi / 2)), (c[3], 2 * c[4], 0.0))

    best = max(found)
    _s, y_c, zc, r, straight = best
    return shape(best), y_c, r, straight


def skull_ball(P, inset, step=0.05, window=None, closed=False, frame=None):
    """The largest ball inside the skull.  The ears stick out and the eye sockets / mouth are hollows, so the skin
    is read in two cuts: the outline of the middle slice (|x| small) all round except straight down into the neck
    - the farthest skin per 15 degrees - and the side of the head at the ball's own height and depth (the nearest
    skin out to the side there; the ears sit further out).  The centre is searched on a grid.  closed: downwards
    too (P then holds the neck's skin as well, frame the head's, which sizes the search)."""
    if len(P) < 50:
        return None
    lo, hi = np.percentile(frame if frame is not None else P, [2, 98], axis=0)
    hw = (hi[0] - lo[0]) / 2
    band = P[np.abs(P[:, 0]) < 0.3 * hw]
    best = None
    y0, y1, z0, z1 = window or (lo[1] + 0.3 * (hi[1] - lo[1]), hi[1] - 0.25 * (hi[1] - lo[1]),
                                lo[2] + 0.25 * (hi[2] - lo[2]), hi[2] - 0.25 * (hi[2] - lo[2]))
    for y_c in np.arange(y0, y1, step):
        for z_c in np.arange(z0, z1, step):
            rel = band[:, 1:] - np.array([y_c, z_c])
            dist = np.linalg.norm(rel, axis=1)
            ang = np.degrees(np.arctan2(rel[:, 1], rel[:, 0]))          # 0 = up, +-180 = down
            bins = ((ang + 180) // 15).astype(int)
            outer = [dist[bins == k].max() for k in range(24) if (bins == k).sum() >= 3
                     and (closed or abs(-180 + (k + 0.5) * 15) < 140)]
            if len(outer) < 14:
                continue
            side = P[(np.abs(P[:, 1] - y_c) < 0.1) & (np.abs(P[:, 2] - z_c) < 0.2) & (np.abs(P[:, 0]) > 0.5 * hw)]
            if len(side) < 4:
                continue
            r = min(min(outer), np.abs(side[:, 0]).min()) - inset
            if best is None or r > best[0]:
                best = (r, y_c, z_c)
    if best is None:
        return None
    return Shape(0, (0.0, best[1], best[2]), np.eye(3), (best[0], 0, 0))


def fit_colliders(model, skin, colliders, inset):
    """New shapes for the body colliders {rigid index: Shape}, notes, and spine bones that should get one."""
    bones = model.bones
    idx = {b.name: i for i, b in enumerate(bones)}
    loc = {i: np.array(b.location, float) for i, b in enumerate(bones)}
    by_bone, by_name = {}, {model.rigids[i].name: i for i in colliders}
    for i in colliders:                       # the body named after its bone wins (頭 over the 頭2 a former run added)
        bone = bones[model.rigids[i].bone].name
        if bone not in by_bone or model.rigids[i].name == bone:
            by_bone[bone] = i
    out, notes = {}, {}
    for side in SIDES:
        for col, twin, a, b, part in (("腕", "腕捩", "腕", "ひじ", "upperarm"), ("ひじ", None, "ひじ", "手首", "forearm"),
                                      ("足", "足D", "足", "ひざ", "thigh"), ("ひざ", None, "ひざ", "足首", "shin")):
            if side + col not in by_bone or side + a not in idx or side + b not in idx:
                continue
            res = limb_fit(skin.co[skin.of(side + part)], loc[idx[side + a]], loc[idx[side + b]])
            if res is None:
                notes[by_bone[side + col]] = "no skin to fit - kept"
                continue
            a2, b2, prof = res
            spans = [(side + col, 0.0, 1.0)]
            if twin and side + twin in by_bone:
                spans = [(side + col, 0.0, 0.5), (side + twin, 0.5, 1.0)]
            for name, t0, t1 in spans:
                r = span_radius(prof, t0, t1)
                if r is None:
                    continue
                whole = t0 == 0.0 and t1 == 1.0
                out[by_bone[name]] = capsule_between(a2 + (b2 - a2) * t0, a2 + (b2 - a2) * t1, r - inset,
                                                     0.5 if whole else 0.0)
                notes[by_bone[name]] = "%s %s-%s of the limb" % (side + part, "%.1f" % t0, "%.1f" % t1)
        # shoulder: along 肩 -> 腕, as thick as the skin above the bone
        if side + "肩" in by_bone and side + "腕" in idx:
            a, b = loc[idx[side + "肩"]], loc[idx[side + "腕"]]
            sel = skin.of("torso", side + "shoulder", "neck", "breast")
            P = skin.co[sel]
            v = b - a
            t = ((P - a) @ v) / (v @ v)
            up = np.array([0, 1.0, 0])
            top = P[(t > 0.2) & (t < 0.9) & (((P - a) - np.outer((P - a) @ (v / np.linalg.norm(v)),
                                                                   v / np.linalg.norm(v))) @ up > 0)]
            if len(top) >= 8:
                r = float(np.percentile(point_seg(top, a, b), 10)) - inset
                out[by_bone[side + "肩"]] = capsule_between(a, b, r, 0.0)
                notes[by_bone[side + "肩"]] = "under the shoulder top (%d skin vertices)" % len(top)
    if "首" in by_bone and "首" in idx and "頭" in idx:
        a, b = loc[idx["首"]], loc[idx["頭"]]
        ring = skin.of("neck", "head", "torso")
        P = skin.co[ring]
        near = point_seg(P, a, b) < 1.5 * np.linalg.norm(b - a)
        res = limb_fit(P[near], a, b, 0.1, 0.9, 6)
        if res is not None:
            a2, b2, prof = res
            r = span_radius(prof, 0.2, 0.8, 10)
            if r is not None:
                out[by_bone["首"]] = capsule_between(a2, b2, r - inset, 0.3)
                notes[by_bone["首"]] = "neck (whole ring of skin)"
    new_bodies = []
    if "頭" in by_bone:
        P = skin.co[skin.of("head")]
        res = skull_ball(P, inset)
        if res is not None:
            out[by_bone["頭"]] = res
            notes[by_bone["頭"]] = "inside the skull"
            # the face and jaw below that ball (front hair hangs by the cheeks and the chin): a second ball
            lo, hi = np.percentile(P, 2, axis=0), np.percentile(P, 98, axis=0)
            bottom = res.c[1] - res.r
            if bottom - lo[1] > 0.25 * (hi[1] - lo[1]):
                window = (lo[1] + 0.15 * (hi[1] - lo[1]), bottom, lo[2] + 0.1 * (hi[2] - lo[2]), res.c[2])
                jaw = skull_ball(P, inset, window=window)
                # a face mesh that ends at the chin (ROE Inase) leaves the throat to the body's mesh: read with the
                # face alone the ball grew down into the neck (1,359 skin vertices more than 8 mm inside); then
                # the neck's skin bounds it too, downwards as well
                neck_too = skin.co[skin.of("head", "neck")]
                if jaw is not None and (surface_distance(neck_too, jaw) < -0.08).sum() > 100:
                    closed = skull_ball(neck_too, inset, window=window, closed=True, frame=P)
                    if closed is not None:
                        jaw = closed
                if jaw is not None and jaw.r > 0.15:
                    if "頭2" in by_name and by_name["頭2"] != by_bone["頭"]:      # a former run's: refit it
                        out[by_name["頭2"]] = jaw
                        notes[by_name["頭2"]] = "face and jaw below the skull ball"
                    else:
                        new_bodies.append(("頭2", "頭", jaw, "face and jaw below the skull ball - new"))
    # torso
    prof = torso_profile(skin)
    spine_y = {}
    for n in SPINE:
        if n in idx:
            child = [i for i, bb in enumerate(bones) if bb.parent == idx[n] and bb.name in SPINE + ("首",)]
            end = loc[child[0]][1] if child else loc[idx[n]][1] + 1.0
            spine_y[n] = (loc[idx[n]][1] + end) / 2 if n != "下半身" else loc[idx[n]][1] - 1.0
    torso = [(by_bone[n], model.rigids[by_bone[n]].location[1]) for n in SPINE if n in by_bone]
    add = []
    ys = sorted(y for _i, y in torso)
    for n in SPINE:
        if n in by_bone or n not in spine_y:
            continue
        y = spine_y[n]
        below, above = [v for v in ys if v < y], [v for v in ys if v > y]
        if below and above and above[0] - below[-1] > 2.0 and min(y - below[-1], above[0] - y) > 0.6:
            add.append((n, y))
            ys = sorted(ys + [y])
    fitted = {}
    for i, y in torso:
        # the hips may climb from where an exporter put them up to the pelvis: ROE Inase's 下半身 sat at the crotch,
        # where the round capsule had to be thin (r 4 cm) and its middle ran through the gap between the thighs
        hips = bones[model.rigids[i].bone].name == "下半身"
        res = torso_capsule(prof, y, inset, (-0.5, 1.0) if hips else (-0.5, 0.2))
        if res is not None:
            fitted[i] = res
    for n, y in add:
        res = torso_capsule(prof, y, inset)
        if res is not None:
            new_bodies.append((n, n, res[0], "torso at %.2f (r %.2f, width %.2f) - new" % (
                res[1], res[2], 2 * (res[2] + res[3]))))
    for i, res in fitted.items():
        out[i] = res[0]
        notes[i] = "torso at %.2f (r %.2f, width %.2f)" % (res[1], res[2], 2 * (res[2] + res[3]))
    return out, notes, new_bodies


def swing(a, b):
    """Rotation matrix turning direction a onto direction b (the shortest way)."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:
        p = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
        p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


# limb-like colliders follow the line between two joints when copied onto another model of the same rig
LINES = {"首": ("首", "頭")}
for _s in SIDES:
    LINES.update({_s + "腕": (_s + "腕", _s + "ひじ"), _s + "腕捩": (_s + "腕", _s + "ひじ"),
                  _s + "ひじ": (_s + "ひじ", _s + "手首"), _s + "肩": (_s + "肩", _s + "腕"),
                  _s + "足": (_s + "足", _s + "ひざ"), _s + "足D": (_s + "足", _s + "ひざ"),
                  _s + "ひざ": (_s + "ひざ", _s + "足首")})


def copy_colliders(model, ref, colliders, label):
    """--colliders-from: the body colliders of a reference PMX on the same rig (already fitted to its nude skin), put
    on this model bone by bone - a limb collider rides the line between its joints (turned and stretched with it:
    Vindictus outfits stand on 1-2 cm heels), the others move with their bone's joint.  Matched by name and bone, then
    by bone; reference colliders this model lacks are added.  -> (shapes {rigid index: Shape}, notes, new bodies,
    colliders of this model the reference has no counterpart for)."""
    bones, rbones = model.bones, ref.bones
    idx = {b.name: i for i, b in enumerate(bones)}
    ridx = {b.name: i for i, b in enumerate(rbones)}
    loc = {i: np.array(b.location, float) for i, b in enumerate(bones)}
    rloc = {i: np.array(b.location, float) for i, b in enumerate(rbones)}
    mine = {i: (model.rigids[i].name, bones[model.rigids[i].bone].name) for i in colliders}
    out, notes, new, taken = {}, {}, [], set()
    for r in ref.rigids:
        bn = rbones[r.bone].name if r.bone is not None and r.bone >= 0 else ""
        if r.mode != 0 or bn not in CLASS_OF:
            continue
        if bn not in idx:
            print("  %s: this model has no bone %s - skipped" % (r.name, bn))
            continue
        s = Shape.of(r)
        line = LINES.get(bn)
        if line and all(j in idx and j in ridx for j in line):
            p0, p1 = rloc[ridx[line[0]]], loc[idx[line[0]]]
            d0, d1 = rloc[ridx[line[1]]] - p0, loc[idx[line[1]]] - p1
            turn, k = swing(d0, d1), float(np.linalg.norm(d1) / np.linalg.norm(d0))
            u0 = d0 / np.linalg.norm(d0)
            rel = s.c - p0
            along = float(rel @ u0)
            c = p1 + turn @ (rel - along * u0 + along * k * u0)
            R, size = turn @ s.R, s.size.copy()
            if s.kind == 2 and abs(s.R[:, 1] @ u0) > 0.9:
                size[1] *= k
        else:
            c, R, size = s.c + (loc[idx[bn]] - rloc[ridx[bn]]), s.R, s.size
        shape = Shape(s.kind, c, R, size)
        hit = next((i for i, key in mine.items() if key == (r.name, bn) and i not in taken), None)
        if hit is None:
            hit = next((i for i, key in mine.items() if key[1] == bn and i not in taken), None)
        if hit is None:
            new.append((r.name, bn, shape, "from %s - new" % label))
        else:
            taken.add(hit)
            out[hit] = shape
            notes[hit] = "from %s" % label
    return out, notes, new, [i for i in colliders if i not in taken]


# -- collision groups ---------------------------------------------------------------------------------------------
def shrink_to_clear(shape, cols, tol, min_share):
    """A thinner copy of a dynamic body that sits no deeper than tol in any collider, or None."""
    def clear(s):
        return all(depth(s, c) <= tol for c in cols)

    best = None
    if shape.kind == 1:
        for axis in range(3):
            lo, hi = min_share, 1.0
            s0 = Shape(1, shape.c, shape.R, shape.size)
            s0.size = shape.size.copy()
            s0.size[axis] *= lo
            if not clear(s0):
                continue
            for _ in range(12):                    # the largest share that clears
                mid = (lo + hi) / 2
                s1 = Shape(1, shape.c, shape.R, shape.size)
                s1.size = shape.size.copy()
                s1.size[axis] *= mid
                lo, hi = (mid, hi) if clear(s1) else (lo, mid)
            if best is None or lo > best[0]:
                s1 = Shape(1, shape.c, shape.R, shape.size)
                s1.size = shape.size.copy()
                s1.size[axis] *= lo
                best = (lo, s1)
    else:
        lo, hi = min_share, 1.0
        s0 = Shape(shape.kind, shape.c, shape.R, (shape.size[0] * lo, shape.size[1], shape.size[2]))
        if clear(s0):
            for _ in range(12):
                mid = (lo + hi) / 2
                s1 = Shape(shape.kind, shape.c, shape.R, (shape.size[0] * mid, shape.size[1], shape.size[2]))
                lo, hi = (mid, hi) if clear(s1) else (lo, mid)
            best = (lo, Shape(shape.kind, shape.c, shape.R, (shape.size[0] * lo, shape.size[1], shape.size[2])))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="new PMX path ('-' with --dry-run)")
    ap.add_argument("--skin", help="the nude skin's materials, comma separated (wildcards allowed)")
    ap.add_argument("--colliders-from", help="instead of --skin: take the body colliders of this PMX (same rig, "
                                             "already fitted, e.g. a full version with the nude body)")
    ap.add_argument("--inset", type=float, default=DEFAULTS["inset"],
                    help="colliders end this far inside the skin, PMX units (default %(default)s)")
    ap.add_argument("--tolerance", type=float, default=DEFAULTS["tolerance"],
                    help="how deep a dynamic body may start in a collider and still collide with it (default "
                         "%(default)s)")
    ap.add_argument("--min-shrink", type=float, default=DEFAULTS["min_shrink"],
                    help="a body is thinned to no less than this share of its size (default %(default)s)")
    ap.add_argument("--bust", default=DEFAULTS["bust"], help="regex: breast bodies are left alone (default %(default)s)")
    ap.add_argument("--keep-colliders", action="store_true", help="do not refit the body colliders")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pmx = load_pmx_module(find_pmx_module(args.pmx_module))
    model = pmx.load(args.input)
    bones, rigids = model.bones, model.rigids
    bname = lambda r: bones[r.bone].name if r.bone is not None and r.bone >= 0 else ""   # noqa: E731
    bust = re.compile(args.bust, re.IGNORECASE)
    if not (args.skin or args.colliders_from or args.keep_colliders):
        raise SystemExit("give --skin (fit the colliders to it), --colliders-from or --keep-colliders")
    skin = None
    if args.skin and not args.colliders_from:
        skin = Skin(pmx, model, [p.strip() for p in args.skin.split(",") if p.strip()], args.bust)
        print("skin: %d vertices from %s" % (len(skin.index), ", ".join(skin.materials)))
        print("  by part: %s" % ", ".join("%s %d" % kv for kv in sorted(Counter(skin.part.tolist()).items())))
    colliders = [i for i, r in enumerate(rigids) if r.mode == 0 and bname(r) in CLASS_OF]
    dynamic = [i for i, r in enumerate(rigids) if r.mode in (1, 2) and not bust.search(bname(r))
               and not bust.search(r.name)]
    print("%d rigid bodies: %d body colliders, %d dynamic cloth / hair bodies (breasts left alone)" % (
        len(rigids), len(colliders), len(dynamic)))

    shapes = {i: Shape.of(rigids[i]) for i in range(len(rigids))}
    new_bodies = []
    if args.colliders_from or not args.keep_colliders:
        if args.colliders_from:
            ref = pmx.load(args.colliders_from)
            print("\nbody colliders from %s (r, h, centre):" % args.colliders_from)
            fit, notes, new_bodies, unmatched = copy_colliders(model, ref, colliders,
                                                               os.path.basename(args.colliders_from))
            # a collider the reference lacks is an anchor mmd_cloth_physics sized on the outfit (PCF_003's ankles:
            # r 11 cm round the dress hem): it stays where its joints hang, shrunk so it cannot push cloth from inside
            for i in unmatched:
                old = shapes[i]
                small = old.size.copy()
                if old.kind == 1:
                    small = np.minimum(small, ANCHOR_RADIUS)
                else:
                    small[0] = min(small[0], ANCHOR_RADIUS)
                if np.allclose(small, old.size):
                    notes[i] = "no counterpart in the reference - kept as it was"
                else:
                    fit[i] = Shape(old.kind, old.c, old.R, small)
                    notes[i] = "no counterpart in the reference - an anchor: shrunk to %.2f" % ANCHOR_RADIUS
        else:
            fit, notes, new_bodies = fit_colliders(model, skin, colliders, args.inset)
            print("\nbody colliders (r, h, centre; skin vertices more than 0.08 inside):")

        def poking(s):
            """Skin vertices more than 0.08 inside the shape."""
            return int((surface_distance(skin.co, s) < -0.08).sum())

        def inside(s):
            return "" if skin is None else "%4d" % poking(s)

        for i in colliders:
            old, new = shapes[i], fit.get(i)
            if new is not None and skin is not None and old.kind == new.kind and old.kind != 1 \
                    and old.size[0] >= new.size[0] and poking(old) <= poking(new):
                # the exporter's collider is already inside the skin and no smaller (ROE Inase's neck: r 0.50 with
                # no skin inside, against a refit of 0.34 that pokes out by the jaw): keep it
                notes[i] = "kept: already inside the skin and not smaller than the refit (r %.2f)" % new.size[0]
                new = None
            if new is None:
                print("  %-6s kept   r %.2f h %.2f   %s" % (rigids[i].name, old.size[0], old.size[1], notes.get(i, "")))
                continue
            print("  %-6s r %.2f h %.2f c %-20s -> r %.2f h %.2f c %-20s  %s  %s" % (
                rigids[i].name, old.size[0], old.size[1], np.round(old.c, 2).tolist(), new.size[0], new.size[1],
                np.round(new.c, 2).tolist(), "inside %s -> %s" % (inside(old), inside(new)) if skin else "",
                notes.get(i, "")))
            shapes[i] = new
        for n, _bone, s, note in new_bodies:
            print("  %-6s new: r %.2f h %.2f c %-20s %s  %s" % (n, s.size[0], s.size[1], np.round(s.c, 2).tolist(),
                                                               "inside %s" % inside(s) if skin else "", note))

    # collider shapes per class
    cls_cols = defaultdict(list)
    for i in colliders:
        cls_cols[CLASS_OF[bname(rigids[i])]].append(("old", i))
    for k, (_n, bone, _s, _note) in enumerate(new_bodies):
        cls_cols[CLASS_OF[bone]].append(("new", k))
    shape_of = lambda ref: shapes[ref[1]] if ref[0] == "old" else new_bodies[ref[1]][2]   # noqa: E731
    classes = [c for c, _b in CLASSES if cls_cols.get(c)]

    # per dynamic body: which classes it can collide with
    combo, thinned, stats = {}, {}, Counter()
    for i in dynamic:
        s = shapes[i]
        deep = {c: max(depth(s, shape_of(ref)) for ref in cls_cols[c]) for c in classes}
        bad = [c for c in classes if deep[c] > args.tolerance]
        if bad:
            res = shrink_to_clear(s, [shape_of(ref) for c in classes for ref in cls_cols[c]], args.tolerance,
                                  args.min_shrink)
            if res is not None:
                thinned[i] = res[1]
                stats["thinned"] += 1
                bad = []
        combo[i] = tuple(c for c in classes if c not in bad)
        stats["all classes" if not bad else "some left out"] += 1

    # groups: untouched bodies keep theirs; classes and combinations take free ones
    touched = set(colliders) | set(dynamic)
    used = {rigids[i].collision_group_number for i in range(len(rigids)) if i not in touched}
    free = [g for g in range(16) if g not in used]                # in order: a second run gives the same numbers
    need = len(classes)
    combos = Counter(combo.values())
    if need + len(combos) > len(free):
        # merge the rarest combinations into the largest allocated subset of them
        keep = [c for c, _n in combos.most_common(len(free) - need)]
        for i, c in combo.items():
            if c not in keep:
                subs = [k for k in keep if set(k) <= set(c)]
                combo[i] = max(subs, key=len) if subs else ()
        combos = Counter(combo.values())
    class_group = {c: free[k] for k, c in enumerate(classes)}
    combo_group = {c: free[need + k] for k, (c, _n) in enumerate(combos.most_common())}
    print("\ncollision groups (PMX numbering 0-15; MMD / PMXEditor shows them +1):")
    for c in classes:
        print("  colliders %-5s -> group %2d (%d bodies)" % (c, class_group[c], len(cls_cols[c])))
    for c, g in combo_group.items():
        print("  dynamic hitting %-28s -> group %2d (%d bodies)" % ("+".join(c) or "nothing", g, combos[c]))
    print("  %d dynamic bodies collide with every class, %d had to be thinned for it, %d leave some out" % (
        stats["all classes"], stats["thinned"], stats["some left out"]))

    # report per garment stem
    def stem(r):
        n = bname(r) or r.name
        n = re.sub(r"_\d+(_[lr])?$", r"\1", n)
        return re.sub(r"_[a-z](_[lr])?$", r"\1", n)

    rows = defaultdict(list)
    for i in dynamic:
        rows[stem(rigids[i])].append(i)
    print("\nper garment: bodies, thinned, classes left out")
    for st, ids in sorted(rows.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        left = Counter(c for i in ids for c in classes if c not in combo[i])
        print("  %-36s %3d  thinned %2d  %s" % (st, len(ids), sum(1 for i in ids if i in thinned),
                                              ", ".join("%s %d" % kv for kv in sorted(left.items())) or "-"))
    # weightless dynamic bodies with nothing weighted under them
    wc = Counter()
    for v in model.vertices:
        for b, x in weights_of(pmx, v):
            if x > 0.01:
                wc[b] += 1
    children = defaultdict(list)
    for j in model.joints:
        if j.src_rigid is not None and j.dest_rigid is not None and j.src_rigid >= 0 and j.dest_rigid >= 0:
            children[j.src_rigid].append(j.dest_rigid)

    def carries(i, seen=()):
        r = rigids[i]
        if r.bone is not None and r.bone >= 0 and wc[r.bone]:
            return True
        return any(carries(k, seen + (i,)) for k in children[i] if k not in seen and rigids[k].mode != 0)

    idle = [rigids[i].name for i in dynamic if not carries(i)]
    weightless = [rigids[i].name for i in dynamic if rigids[i].bone is not None and not wc[rigids[i].bone]]
    print("\ndynamic bodies whose bone has no weight: %d (%d of them carry nothing further down the chain: %s)" % (
        len(weightless), len(idle), ", ".join(idle[:12]) or "-"))

    if args.dry_run:
        return
    if os.path.abspath(args.output) == os.path.abspath(args.input):
        raise SystemExit("refusing to overwrite the input; write a new file")

    def write_shape(r, s):
        r.type = s.kind
        r.location = [float(x) for x in s.c]
        r.rotation = [float(x) for x in euler_of(s.R)]
        r.size = [float(x) for x in s.size]

    dyn_groups = set(combo_group.values())
    for i in colliders:
        r = rigids[i]
        if not args.keep_colliders:
            write_shape(r, shapes[i])
        c = CLASS_OF[bname(r)]
        r.collision_group_number = class_group[c]
        r.collision_group_mask = sum(1 << g for k, g in combo_group.items() if c in k)
    bone_idx = {b.name: i for i, b in enumerate(bones)}
    for n, bone, s, _note in new_bodies:
        r = pmx.Rigid()
        r.name, r.name_e, r.bone = n, n, bone_idx[bone]
        write_shape(r, s)
        c = CLASS_OF[bone]
        r.collision_group_number = class_group[c]
        r.collision_group_mask = sum(1 << g for k, g in combo_group.items() if c in k)
        r.mass, r.velocity_attenuation, r.rotation_attenuation, r.bounce, r.friction, r.mode = 1.0, 0.5, 0.5, 0.0, 0.5, 0
        rigids.append(r)
    for i in dynamic:
        r = rigids[i]
        if i in thinned:
            write_shape(r, thinned[i])
        r.collision_group_number = combo_group[combo[i]]
        r.collision_group_mask = sum(1 << class_group[c] for c in combo[i])
    assert not (dyn_groups & set(class_group.values()))
    # keep texture paths relative to the new file when the textures were copied next to it
    src_dir, out_dir = os.path.dirname(os.path.abspath(args.input)), os.path.dirname(os.path.abspath(args.output))
    for texture in model.textures:
        local = os.path.join(out_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    pmx.save(args.output, model, add_uv_count=model.header.additional_uvs)
    print("\nwrote %s" % args.output)


if __name__ == "__main__":
    sys.exit(main())
