"""Collision groups by body part, once every garment is built.

MMD filters collisions by group only.  Until 2026-10-18 this add-on put every cloth body that started near the
body - the first row, or anything within a bounding-sphere test of a collider - in group 10, which collides with
nothing, and the rest in 11, which collides with the whole body (group 0).  On a skirt that is nearly every body
round the hips: over the ROE models, 81 had cloth hanging by the legs and every one of them had more than half of it
going through the legs.

Now, as scripts/mmd_physics/cloth_collision_pmx.py does for a finished PMX: the body colliders of each part (head,
neck, torso, arms, legs; by their MMD bone names) share a group, and each dynamic body collides with every part it
does not start inside.  A body that starts inside is first made thinner (a box on one axis, a capsule its radius,
down to ``min_share`` of its size - the shape only matters for collisions); when that is not enough it stops
colliding with that part only.  Each combination of parts gets a group of its own.  A garment hanging on a physics
body (chest ribbons on a breast) collides with nothing: a hand hitting it would yank the breast.  Breasts and bodies
that collided with nothing before are left alone, and so are the groups of everything else.
"""
import re
from collections import Counter, defaultdict

from . import geom

SIDES = ("左", "右")
CLASSES = (("head", ("頭",)),
           ("neck", ("首", "首1")),
           ("torso", ("上半身", "上半身1", "上半身2", "上半身3", "上半身4", "上半身5", "下半身", "腰")),
           ("arms", tuple(s + n for s in SIDES for n in ("肩", "腕", "腕捩", "ひじ", "手捩", "手首"))),
           ("legs", tuple(s + n for s in SIDES for n in ("足", "足D", "ひざ", "ひざD", "足首", "足首D"))))
CLASS_OF = {b: c for c, bones in CLASSES for b in bones}
# breast bones (cloth_collision_pmx.py's list): Breast_L02, ROE chest_L02 / OPAI_L02 / Xtra01Opp02, MMD 胸 / 乳
BUST = re.compile(r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$",
                  re.IGNORECASE)
TAG = "mmd_cloth_physics"
RIDES = TAG + "_rides"


def name_j(arm, obj):
    """The MMD (Japanese) name of the bone a rigid body follows."""
    bone = obj.mmd_rigid.bone
    pbone = arm.pose.bones.get(bone) if bone else None
    if pbone is not None and pbone.mmd_bone.name_j:
        return pbone.mmd_bone.name_j
    return bone or ""


def blocked(a, b):
    """mmd_tools masks: True = 'does not collide with that group'; MMD needs both sides to allow it."""
    ra, rb = a.mmd_rigid, b.mmd_rigid
    return bool(ra.collision_group_mask[rb.collision_group_number] or rb.collision_group_mask[ra.collision_group_number])


def shrink_to_clear(shape, cols, tol, min_share):
    """A thinner copy of a dynamic body that sits no deeper than tol in any collider, or None."""
    def clear(s):
        return all(geom.depth(s, c) <= tol for c in cols)

    best = None
    if shape.kind == geom.BOX:
        for axis in range(3):
            size = shape.size.copy()
            size[axis] *= min_share
            if not clear(shape.resized(size)):
                continue
            lo, hi = min_share, 1.0
            for _ in range(12):                    # the largest share that clears
                mid = (lo + hi) / 2
                size = shape.size.copy()
                size[axis] *= mid
                lo, hi = (mid, hi) if clear(shape.resized(size)) else (lo, mid)
            if best is None or lo > best[0]:
                size = shape.size.copy()
                size[axis] *= lo
                best = (lo, shape.resized(size))
    else:
        size = shape.size.copy()
        size[0] *= min_share
        if clear(shape.resized(size)):
            lo, hi = min_share, 1.0
            for _ in range(12):
                mid = (lo + hi) / 2
                size = shape.size.copy()
                size[0] *= mid
                lo, hi = (mid, hi) if clear(shape.resized(size)) else (lo, mid)
            size = shape.size.copy()
            size[0] *= lo
            best = (lo, shape.resized(size))
    return best


def assign(arm, rigid_objects, unit=1.0, tolerance=0.002, min_share=0.35, log=None, keep_size=()):
    """Give the body colliders a group per part and every dynamic body the parts it may hit (see the module
    docstring).  ``tolerance`` (metres) is how deep a body may start in a collider and still collide with it - 2 mm,
    as the ROE / Stellar Blade exporters' release_rest_overlaps, which runs after this and so finds nothing left to
    release.  ``keep_size``: names of bodies never made thinner - one that starts inside a part leaves that part out
    (hair: a thinned tip resting on the shoulders or the back chatters against it every frame, 2026-10-24).
    Returns a report dict."""
    rigids = [o for o in rigid_objects if getattr(o, "mmd_type", "") == "RIGID_BODY"]
    tol = tolerance * unit
    colliders = [o for o in rigids if str(o.mmd_rigid.type) == "0" and name_j(arm, o) in CLASS_OF]
    if not colliders:
        if log:
            log("collision groups: no body colliders on MMD bones - groups left as built")
        return {"classes": {}, "combos": {}, "thinned": 0}
    dynamic, quiet = [], []
    for o in rigids:
        if str(o.mmd_rigid.type) == "0":
            continue
        nm = name_j(arm, o)
        if BUST.search(nm) or BUST.search(o.mmd_rigid.name_j or ""):
            continue
        ours = o.get(TAG) not in (None, "body")
        if not ours and all(blocked(o, c) for c in colliders):
            continue                               # someone else's body that never touched the body: theirs
        (quiet if o.get(RIDES) else dynamic).append(o)

    cls_cols = defaultdict(list)
    shapes = {}
    for o in colliders:
        shapes[o.name] = geom.of_object(o)
        cls_cols[CLASS_OF[name_j(arm, o)]].append(shapes[o.name])
    classes = [c for c, _b in CLASSES if cls_cols.get(c)]
    every = [s for c in classes for s in cls_cols[c]]
    combo, thinned, stats = {}, {}, Counter()
    for o in dynamic:
        s = geom.of_object(o)
        bad = [c for c in classes if max(geom.depth(s, k) for k in cls_cols[c]) > tol]
        if bad and o.name not in keep_size:
            res = shrink_to_clear(s, every, tol, min_share)
            if res is not None:
                thinned[o.name] = res[1]
                bad = []
        combo[o.name] = tuple(c for c in classes if c not in bad)
        stats["all" if not bad else "some left out"] += 1
    for o in quiet:
        combo[o.name] = ()

    touched = {o.name for o in colliders} | {o.name for o in dynamic} | {o.name for o in quiet}
    used = {o.mmd_rigid.collision_group_number for o in rigids if o.name not in touched}
    free = [g for g in range(16) if g not in used]
    need = len(classes)
    combos = Counter(combo.values())
    if need + len(combos) > len(free):
        keep = [c for c, _n in combos.most_common(max(0, len(free) - need))]
        for k, c in combo.items():
            if c not in keep:
                subs = [x for x in keep if set(x) <= set(c)]
                combo[k] = max(subs, key=len) if subs else ()
        combos = Counter(combo.values())
    if need + len(combos) > len(free):
        if log:
            log("collision groups: only %d free groups for %d parts + %d combinations - left as built"
                % (len(free), need, len(combos)))
        return {"classes": {}, "combos": {}, "thinned": 0}
    class_group = {c: free[k] for k, c in enumerate(classes)}
    combo_group = {c: free[need + k] for k, (c, _n) in enumerate(combos.most_common())}

    for o in colliders:
        c = CLASS_OF[name_j(arm, o)]
        allow = {g for k, g in combo_group.items() if c in k}
        o.mmd_rigid.collision_group_number = class_group[c]
        o.mmd_rigid.collision_group_mask = [g not in allow for g in range(16)]
    for o in dynamic + quiet:
        allow = {class_group[c] for c in combo[o.name]}
        if o.name in thinned:
            o.mmd_rigid.size = tuple(float(v) for v in thinned[o.name].size)
        o.mmd_rigid.collision_group_number = combo_group[combo[o.name]]
        o.mmd_rigid.collision_group_mask = [g not in allow for g in range(16)]

    left = defaultdict(Counter)
    for o in dynamic + quiet:
        garment = o.get(TAG) or "-"
        for c in classes:
            if c not in combo[o.name]:
                left[garment][c] += 1
    report = {"classes": {c: class_group[c] for c in classes},
              "combos": {"+".join(c) or "nothing": [combo_group[c], n] for c, n in combos.items()},
              "thinned": len(thinned), "riding": len(quiet),
              "left_out": {g: dict(cnt) for g, cnt in left.items()}}
    if log:
        log("collision groups (PMX numbering; PMXEditor shows +1): %s"
            % ", ".join("%s %d" % (c, g) for c, g in report["classes"].items()))
        for c, (g, n) in sorted(report["combos"].items(), key=lambda kv: -kv[1][1]):
            log("  group %2d: %3d bodies hitting %s" % (g, n, c.replace("+", ", ")))
        log("  %d bodies hit every part, %d of them thinned for it; %d leave some part out; %d ride a physics "
            "body and hit nothing" % (stats["all"], len(thinned), stats["some left out"], len(quiet)))
        for g, cnt in sorted(left.items()):
            log("  %-28s leaves out %s" % (g, ", ".join("%s %d" % kv for kv in sorted(cnt.items()))))
    return report
