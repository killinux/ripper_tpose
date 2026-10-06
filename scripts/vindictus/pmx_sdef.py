"""MMD's spherical skinning (SDEF) on the elbow rings of a finished PMX - plain Python, any PMX.

A vertex weighted to the two bones of a joint, as BDEF2, moves on the straight line between the two places each
bone alone would put it: bent far, the outside of the joint flattens and the inside folds in.  As SDEF it turns
about the joint by the blend of the two rotations and keeps its distance from it - the joint stays round.  MMD and
MMM evaluate SDEF themselves; in Blender mmd_tools needs its SDEF driver bound (sidebar 杂项 tab ->
「MMD SDEF驱动器」-> 绑定, with 偏好设置 > 文件路径 > 自动运行 Python 脚本 on).

For each joint bone (default 左ひじ / 右ひじ) the pair is that bone and its parent in the PMX (腕捩 after Convert to
MMD 5, 腕 without it).  Every vertex whose only weights are those two bones becomes SDEF with C at the joint bone's
head and R0 = R1 = C; nothing else changes and the comment gets a line saying so.  The PMX module's round trip is
byte-identical, so a file written next to its input differs only in those vertices.

    python pmx_sdef.py in.pmx out.pmx                                  # the elbows
    python pmx_sdef.py in.pmx out.pmx --joints 左ひじ,右ひじ,左ひざ,右ひざ  # other joints too (knees: untested)
    python pmx_sdef.py in.pmx - --dry-run                              # count only
    python pmx_sdef.py in.pmx out.pmx --fold                           # EXPERIMENTAL 2026-10-06 (see add_sdef)

export_pmx.py runs sdef_file() on the PMX it has written (``--no-sdef`` skips it).  Tried on Vindictus PCF_005
(2026-10-04, checks/arm_stills.py --sdef, checks/arm_video.py --sdef): 467 vertices; at 90-130 deg the elbow
stays round outside and does not pinch inside.  The arm wrap's zigzag edge and the skin under it are weighted a
little differently in the game, and SDEF, turning each by its own blend, shows that as specks where the two layers
cross.  The user preferred SDEF anyway.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)

JOINTS = ("左ひじ", "右ひじ")
FOLD_MARK = "twist helpers folded at the SDEF joints"
FADE = 0.3                      # forearm twist fades back in over this share of the joint -> twist bone distance
                                # (PCF_005: 6.4 cm; 0.15 made the twist ramp 3x the original's slope)


def joint_pairs(model, joints=JOINTS):
    """(parent index, joint index, C, "parent:joint") for each joint bone the model has."""
    index = {bone.name: i for i, bone in enumerate(model.bones)}
    pairs = []
    for name in joints:
        child = index.get(name)
        if child is None:
            continue
        parent = model.bones[child].parent
        if parent is None or parent < 0:
            continue
        centre = tuple(model.bones[child].location)
        pairs.append((parent, child, centre, "%s:%s" % (model.bones[parent].name, name)))
    return pairs


def twist_helpers(model, parent, child):
    """The twist bones that move exactly like the joint bone or its parent while the arm only bends:
    (child side, parent side, the child's own twist bone or None).  After Convert to MMD 5: 手捩 and 手捩1-3 (children
    of ひじ, 手捩1-3 granted from 手捩) on the forearm side; 腕捩1-3 (siblings of 腕捩, granted from it) on the upper arm."""
    bones = model.bones
    child_side, own = set(), None
    for i, bone in enumerate(bones):
        if bone.parent == child and "捩" in bone.name:
            child_side.add(i)
            if not bone.additionalTransform:
                own = i
    parent_side = set()
    for i, bone in enumerate(bones):
        grant = bone.additionalTransform
        if i != parent and bone.parent == bones[parent].parent and grant and grant[0] == parent:
            parent_side.add(i)
    return child_side, parent_side, own


def _entries(weight, pmx):
    if weight.type == pmx.BoneWeight.BDEF1:
        return [(weight.bones[0], 1.0)]
    if weight.type == pmx.BoneWeight.BDEF2:
        return [(weight.bones[0], weight.weights[0]), (weight.bones[1], 1.0 - weight.weights[0])]
    if weight.type == pmx.BoneWeight.BDEF4:
        return [(b, w) for b, w in zip(weight.bones, weight.weights) if b >= 0]
    if weight.type == pmx.BoneWeight.SDEF:
        return [(weight.bones[0], weight.weights.weight), (weight.bones[1], 1.0 - weight.weights.weight)]
    return []


def _set_linear(weight, entries, pmx):
    """BDEF1 / 2 / 4 for the (bone, weight) list, weights normalised."""
    entries = [(b, w) for b, w in entries if w > 1e-6]
    total = sum(w for _b, w in entries)
    entries = sorted(((b, w / total) for b, w in entries), key=lambda e: -e[1])
    if len(entries) == 1:
        weight.type, weight.bones, weight.weights = pmx.BoneWeight.BDEF1, [entries[0][0]], []
    elif len(entries) == 2:
        weight.type, weight.bones, weight.weights = pmx.BoneWeight.BDEF2, [b for b, _w in entries], [entries[0][1]]
    else:
        entries = (entries + [(-1, 0.0)] * 4)[:4]
        weight.type = pmx.BoneWeight.BDEF4
        weight.bones, weight.weights = [b for b, _w in entries], [w for _b, w in entries]


def add_sdef(model, pmx, joints=JOINTS, fold=False, fade=FADE, stats=None):
    """Turn the vertices of each joint ring into SDEF in place; returns {"parent:joint": vertices}.

    Without ``fold`` (the default) only vertices on exactly the two bones.  With it (2026-10-06, EXPERIMENTAL: the
    fold line below got smaller in Blender, but the user still saw a fault at the elbow in their own test), a vertex that
    also carries one of the joint's twist helpers (twist_helpers: 手捩1 on the forearm side, 腕捩3 on the upper arm)
    has that weight moved onto the bone of its own side and becomes SDEF too.  Left linear, those vertices (PCF_005:
    155 per elbow, 4-6.6 cm down the forearm) sagged while their SDEF neighbours stayed round, and the elbow showed a
    fold along the line between them whenever it bent.  The helpers only add twist, so this changes nothing in a
    bend; the forearm twist then starts where the ring ends instead of inside it, and fades in over ``fade`` x the
    joint -> twist bone distance (the forearm-side helper weight of the next vertices moves onto the joint bone in
    proportion), so twisting shows no step.  Folding is done once: the comment gets FOLD_MARK.  ``stats`` (a dict)
    receives "folded" and "faded": {"parent:joint": vertices}."""
    pairs = joint_pairs(model, joints)
    made = {label: 0 for _p, _c, _x, label in pairs}
    if fold and FOLD_MARK in (model.comment or ""):
        fold = False
    info = []
    for parent, child, centre, label in pairs:
        child_side, parent_side, own = twist_helpers(model, parent, child) if fold else (set(), set(), None)
        axis = None
        if own is not None:
            d = [a - b for a, b in zip(model.bones[own].location, centre)]
            length = sum(x * x for x in d) ** 0.5
            axis = ([x / length for x in d], length) if length > 1e-6 else None
        info.append((parent, child, centre, label, child_side | {child}, parent_side | {parent}, axis))
    folded = {label: 0 for _p, _c, _x, label in pairs}
    faded = {label: 0 for _p, _c, _x, label in pairs}

    def along(vertex, centre, axis):
        return sum((p - c) * a for p, c, a in zip(vertex.co, centre, axis[0]))

    # pass 1: the ring of each joint = vertices weighted to both sides (SDEF already or not); how far it reaches
    ring_end = {}
    for vertex in model.vertices:
        entries = [(b, w) for b, w in _entries(vertex.weight, pmx) if w > 1e-6]
        bones = {b for b, _w in entries}
        for parent, child, centre, label, cside, pside, axis in info:
            if axis and bones <= cside | pside and bones & cside and bones & pside:
                ring_end[label] = max(ring_end.get(label, 0.0), along(vertex, centre, axis))
    # pass 2
    for vertex in model.vertices:
        weight = vertex.weight
        if weight.type == pmx.BoneWeight.SDEF:
            continue
        entries = [(b, w) for b, w in _entries(weight, pmx) if w > 1e-6]
        bones = {b for b, _w in entries}
        for parent, child, centre, label, cside, pside, axis in info:
            if not bones <= cside | pside:
                continue
            w_child = sum(w for b, w in entries if b in cside)
            w_parent = sum(w for b, w in entries if b in pside)
            if w_child > 0 and w_parent > 0:                       # on the ring: SDEF between the two bones
                exact = bones == {parent, child}
                total = w_child + w_parent
                if exact:                                           # as before folding existed (byte-identical)
                    first = entries[0][0]
                    share = entries[0][1] if abs(total - 1.0) < 1e-4 else entries[0][1] / total
                else:
                    first, share = parent, w_parent / total
                weight.type = pmx.BoneWeight.SDEF
                weight.bones = [first, child if first == parent else parent]
                weight.weights = pmx.BoneWeightSDEF(weight=share, c=centre, r0=centre, r1=centre)
                made[label] += 1
                if not exact:
                    folded[label] += 1
                break
            if axis and label in ring_end and w_parent == 0 and bones & (cside - {child}):
                s = along(vertex, centre, axis)                     # just past the ring: fade the twist in
                f = 1.0 if s <= ring_end[label] else 1.0 - (s - ring_end[label]) / (fade * axis[1])
                if f > 0:
                    helper = sum(w for b, w in entries if b != child)
                    rest = [(b, w * (1.0 - f)) for b, w in entries if b != child]
                    _set_linear(weight, [(child, w_child - helper + helper * f)] + rest, pmx)
                    faded[label] += 1
                break
    if stats is not None:
        stats.update(folded=folded, faded=faded)
    return made


def sdef_file(src, dst, joints=JOINTS, model_name="", dry_run=False, pmx_module=None, fold=False, fade=FADE,
              stats=None):
    """add_sdef on a PMX file; ``dst`` may be ``src`` (written through a temporary file).  Returns the counts."""
    pmx = bust_physics.load_pmx_module(pmx_module)
    model = pmx.load(src)
    stats = {} if stats is None else stats
    made = add_sdef(model, pmx, joints, fold, fade, stats)
    if dry_run:
        return made
    changed = sum(stats.get("folded", {}).values()) + sum(stats.get("faded", {}).values())
    if changed:
        note = "%s: %s moved onto the joint pair, %s faded (pmx_sdef.py)" % (
            FOLD_MARK, sum(stats["folded"].values()), sum(stats["faded"].values()))
        model.comment = ((model.comment or "").rstrip() + "\r\n" + note).lstrip()
        model.comment_e = ((model.comment_e or "").rstrip() + "\r\n" + note).lstrip()
    # the PMX module makes texture paths absolute on load and relative to the new file on save: keep the old
    # relative path when the output folder has its own copy (see bust_physics.tune_file)
    src_dir, dst_dir = os.path.dirname(os.path.abspath(src)), os.path.dirname(os.path.abspath(dst))
    for texture in model.textures:
        try:
            local = os.path.join(dst_dir, os.path.relpath(texture.path, src_dir))
        except ValueError:                                  # texture on another drive than the input: keep its path
            continue
        if os.path.isfile(local):
            texture.path = local
    total = sum(made.values())
    if total:
        note = "SDEF on the joint rings %s (C = the joint), %d vertices" % (",".join(made), total)
        model.comment = ((model.comment or "").rstrip() + "\r\n" + note).lstrip()
        model.comment_e = ((model.comment_e or "").rstrip() + "\r\n" + note).lstrip()
    if model_name:
        model.name = model.name_e = model_name
    temporary = dst + ".sdef.tmp"
    pmx.save(temporary, model, add_uv_count=model.header.additional_uvs)
    os.replace(temporary, dst)
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="the new PMX (may be the input; '-' with --dry-run)")
    ap.add_argument("--joints", default=",".join(JOINTS),
                    help="joint bones, each paired with its parent bone (default %(default)s)")
    ap.add_argument("--model-name", default="", help="rename the model (both names)")
    ap.add_argument("--fold", action="store_true",
                    help="EXPERIMENTAL: also the ring vertices that carry a twist helper (see add_sdef); default: only "
                         "vertices on exactly the two bones")
    ap.add_argument("--fade", type=float, default=FADE,
                    help="forearm twist fade-in length as a share of the joint -> twist bone distance (%(default)s)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    args = ap.parse_args(argv)
    joints = [name.strip() for name in args.joints.split(",") if name.strip()]
    stats = {}
    made = sdef_file(args.input, args.output, joints, args.model_name, args.dry_run, args.pmx_module,
                     args.fold, args.fade, stats)
    print("SDEF vertices: %s" % (made or "none - no joint bone with a parent found"), flush=True)
    if stats.get("folded") is not None:
        print("of them with twist helpers moved onto the pair: %s; twist faded in on %s" % (
            stats["folded"], stats["faded"]), flush=True)
    print("dry run, nothing written" if args.dry_run else "wrote %s" % args.output)


if __name__ == "__main__":
    sys.exit(main())
