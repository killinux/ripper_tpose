"""Rise of Eros: a one-bone breast whose bone already carries a static body gets its swing anyway.

scripts/mmd_dances/pmx_add_bust.py adds breast bodies where the exporter did not, but leaves a side alone when the
bone that would swing already has a body.  Misa c06's right breast is that case: one bone, Bip001 OPAI_R, and on
it the static anchor of the accessories01 chain hung on the right cup, so c06 swung on the left only.  This turns
that body into the swinging sphere with pmx_add_bust's own template and rules - placed at the weighted centre of
the vertices the bone moves (weight >= 0.3), radius 0.8 x their 75th-percentile spread kept within 3-6 cm, mass 1,
damping 0.5, friction 0.5, group 15 / mask 0 - hangs it from the nearest body above (the torso's) with
pmx_add_bust's joint (+-10 degrees, no spring, at the bone's head) and renames the bone 右胸 / 左胸 (the English
name keeps the game's).  What hangs on that body (the chain) now swings with the cup.

--merge: a completed version (complete_nude.py) has the nude body's Breast_R02 / Breast_R03 / Nipple_R under that
bone, added because c06 has no OPAI_R02 to alias them to; their weights go to the bone first, so body and cup move
as one.  --merge-only does only that, for a version without the anchor (the _nude: no chain), after which
pmx_add_bust.py swings the one-bone breast itself the same way.

    python pmx_add_bust.py in.pmx tmp.pmx --left "Bip001 OPAI_L" --no-bustb     # the other side as usual
    python pmx_breast_anchor_swing.py tmp.pmx out.pmx [--merge] [--bone "Bip001 OPAI_R"] [--name 右胸]
    python ..\\mmd_physics\\tune_bust_pmx.py out.pmx out_bustB.pmx --bones "胸|乳|chest|breast|bust|oppai|opai|xtra"
Needs Python, numpy and the pmx module inside mmd_tools (no Blender).
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mmd_dances"))
import pmx_add_bust as pab  # noqa: E402


def remap(w, src, dst):
    """One vertex's weights: bones in src become dst (a pair that becomes one bone becomes BDEF1)."""
    if w.type == 0:
        w.bones = [dst if w.bones[0] in src else w.bones[0]]
    elif w.type in (1, 3):                      # BDEF2 / SDEF: two bones, one weight
        bones = [dst if b in src else b for b in w.bones]
        if bones[0] == bones[1]:
            w.type, w.bones, w.weights = 0, [bones[0]], []
        else:
            w.bones = bones
    else:                                       # BDEF4
        acc = {}
        for b, x in zip(w.bones, w.weights):
            b = dst if b in src else b
            if b is not None and b >= 0 and x > 0:
                acc[b] = acc.get(b, 0.0) + x
        items = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
        items += [(items[0][0], 0.0)] * (4 - len(items))
        w.bones, w.weights = [b for b, _ in items], [x for _, x in items]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--bone", default="Bip001 OPAI_R", help="the one-bone breast (default %(default)s)")
    ap.add_argument("--name", default="右胸", help="its new name (default %(default)s)")
    ap.add_argument("--merge", action="store_true", help="first give it the weights of the breast bones under it")
    ap.add_argument("--merge-only", action="store_true", help="only that (a version without the anchor body)")
    args = ap.parse_args()
    args.merge = args.merge or args.merge_only
    opts = dict(pab.DEFAULTS)
    unit = opts["unit_cm"]
    pmx = pab.pmx_module()
    model = pmx.load(args.src)
    names = [b.name for b in model.bones]
    if args.bone not in names:
        sys.exit("no bone %r" % args.bone)
    root = names.index(args.bone)
    kids = pab.children(model)
    report = {}
    if args.merge:
        under = [i for i in pab.subtree(kids, root, set()) if i != root and pab.NEXT_NAME.search(names[i])
                 and not pab.HELPER.search(names[i])]
        src = set(under)
        n = 0
        for v in model.vertices:
            if any(b in src for b in v.weight.bones):
                remap(v.weight, src, root)
                n += 1
        report["merged"] = "%d vertices of %s -> %s" % (n, ", ".join(names[i] for i in under), args.bone)
    if args.merge_only:
        pmx.save(args.out, model, add_uv_count=model.header.additional_uvs)
        print("merged: %s\nwrote %s" % (report["merged"], args.out))
        return
    on_bone = {}
    for i, r in enumerate(model.rigids):
        if r.bone is not None:
            on_bone.setdefault(r.bone, i)
    if root not in on_bone:
        sys.exit("%s has no body: pmx_add_bust.py handles this side itself" % args.bone)
    body = on_bone[root]
    if model.rigids[body].mode != 0:
        sys.exit("%s's body already swings" % args.bone)
    moved = set(pab.subtree(kids, root, set(on_bone) - {root}))
    pts, ws = pab.moved_vertices(model, moved, opts["min_weight"])
    if not len(pts):
        sys.exit("no vertex follows %s by %.1f or more" % (args.bone, opts["min_weight"]))
    centre = (pts * ws[:, None]).sum(0) / ws.sum()
    dist = np.sort(np.linalg.norm(pts - centre, axis=1))
    low, high = (x / unit for x in opts["radius"])
    radius = min(high, max(low, opts["radius_scale"] * float(dist[int(0.75 * (len(dist) - 1))])))
    r = model.rigids[body]
    old = "%s: %s, mode %d, group %d" % (r.name, ["sphere", "box", "capsule"][r.type], r.mode, r.collision_group_number)
    r.type, r.size = 0, [float(radius), 0.0, 0.0]
    r.location, r.rotation = [float(x) for x in centre], [0.0, 0.0, 0.0]
    r.mass, r.velocity_attenuation, r.rotation_attenuation = opts["mass"], opts["lin_damp"], opts["ang_damp"]
    r.bounce, r.friction, r.mode = 0.0, opts["friction"], 1
    r.collision_group_number, r.collision_group_mask = opts["group"], opts["mask"]
    holder = model.bones[root].parent
    while holder is not None and holder >= 0 and holder not in on_bone:
        holder = model.bones[holder].parent
    if holder is None or holder < 0:
        sys.exit("no body above %s" % args.bone)
    limit = math.radians(opts["limit_deg"])
    j = pmx.Joint()
    j.name, j.name_e, j.mode = args.bone, "", 0
    j.src_rigid, j.dest_rigid = on_bone[holder], body
    j.location, j.rotation = [float(x) for x in model.bones[root].location], [0.0, 0.0, 0.0]
    j.minimum_location, j.maximum_location = [0.0] * 3, [0.0] * 3
    j.minimum_rotation, j.maximum_rotation = [-limit] * 3, [limit] * 3
    j.spring_constant, j.spring_rotation_constant = [0.0] * 3, [0.0] * 3
    model.joints.append(j)
    bone = model.bones[root]
    bone.name_e = bone.name_e or bone.name
    bone.name = args.name
    if r.name == args.bone:
        r.name = args.name
    report.update({"body": "%s -> swinging sphere %.2f cm at the moved vertices' centre (%d), %.2f cm from the pivot"
                   % (old, radius * unit, len(pts), float(np.linalg.norm(centre - np.array(bone.location))) * unit),
                   "joint": "%s -> %s, +-%g deg" % (model.rigids[on_bone[holder]].name, r.name, opts["limit_deg"]),
                   "renamed": "%s -> %s" % (args.bone, args.name)})
    pmx.save(args.out, model, add_uv_count=model.header.additional_uvs)
    for k, v in report.items():
        print("%s: %s" % (k, v))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
