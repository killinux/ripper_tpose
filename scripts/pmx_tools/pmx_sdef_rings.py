r"""SDEF on the elbows and knees of any of our PMX, helper bones included (pmx-todo item 6, 2026-11-15).

MMD skins a vertex hung on two bones linearly (BDEF): bent far, the outside of the joint flattens and the inside
folds in.  As SDEF it turns about the joint by the blend of the two rotations and keeps its distance from it - the
joint stays round.  MMD / MMM evaluate SDEF themselves; Blender's mmd_tools needs its SDEF driver bound (sidebar 杂项
-> 「MMD SDEF驱动器」-> 绑定, with 自动运行 Python 脚本 on).

scripts/vindictus/pmx_sdef.py converts only the vertices hung on exactly the joint bone and its parent; on most of our
games that is no vertex at all (11-15 survey: Stellar Blade, FF7, Honey Select 2 0; NARAKA / TFD / Taimanin a few
dozen), because their rigs carry the game's own joint helpers - Stellar Blade Ab-L-Elbow / BrochiDn / Knee-SubA,
FF7 L_Elbow_Spo / L_Knee_Spo, HS2 cf_J_ArmElboura_s_L / cf_J_LegKnee_back_s_L, NARAKA "elbow help", TFD
Bn_Shape_Elbow_L ...  In the game an animation blueprint drives them; in our PMX most just ride their parent bone.
Here every bone a ring vertex carries is put on one side of the joint:
  * the joint side: the joint bone and everything below it (the forearm's twist bones and helpers);
  * the parent side: the parent bone, everything below it, the limb bone above it (腕 above 腕捩, 足 / 足D) and bones
    granted (付与) from these (腕捩1-3);
  * a bone granted a SHARE r < 1 of the joint's rotation (Stellar Blade's Ab-L-Knee: 付与 左ひざ x0.48, a half-angle
    corrective) goes r to the joint side and 1 - r to the parent side - SDEF at that share turns it the same way.
A vertex with weight on both sides whose bones are all classified becomes SDEF between (parent, joint), the share
summed per side, C = R0 = R1 = the joint bone's head.  Anything else stays as it is.  The comment gets a line.

    python pmx_sdef_rings.py in.pmx out.pmx [--joints elbows,knees] [--dry-run] [--report r.json]
Joint names: 左ひじ / 右ひじ, knees 左ひざD / 右ひざD when the model has D bones carrying weight, else 左ひざ / 右ひざ.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "vindictus"))
import bust_physics  # noqa: E402  (load_pmx_module: mmd_tools' PMX reader / writer, plain Python)

MARK = "SDEF on the elbow / knee rings (pmx_sdef_rings.py"
MIN_OTHER = 0.01        # a vertex with more than this on an unclassified bone stays linear


def entries(weight, pmx):
    T = pmx.BoneWeight
    if weight.type == T.BDEF1:
        return [(weight.bones[0], 1.0)]
    if weight.type == T.BDEF2:
        return [(weight.bones[0], weight.weights[0]), (weight.bones[1], 1.0 - weight.weights[0])]
    if weight.type == T.BDEF4:
        return [(b, w) for b, w in zip(weight.bones, weight.weights) if b >= 0 and w > 1e-6]
    if weight.type == T.SDEF:
        return [(weight.bones[0], weight.weights.weight), (weight.bones[1], 1.0 - weight.weights.weight)]
    return [(b, w) for b, w in zip(weight.bones, getattr(weight, "weights", []) or []) if b >= 0 and w > 1e-6]


def joint_names(model, pmx, which):
    names = {b.name: i for i, b in enumerate(model.bones)}
    used = set()
    for v in model.vertices:
        used.update(b for b, w in entries(v.weight, pmx) if w > 1e-6)
    out = []
    if "elbows" in which:
        out += ["左ひじ", "右ひじ"]
    if "knees" in which:
        for side in ("左", "右"):
            d = names.get(side + "ひざD")
            out.append(side + "ひざD" if d is not None and d in used else side + "ひざ")
    return [n for n in out if n in names]


def classify(model, joint, parent):
    """{bone index: share of the joint side} for the bones that belong to the joint / parent side"""
    bones = model.bones
    n = len(bones)
    children = [[] for _ in range(n)]
    for i, b in enumerate(bones):
        if b.parent is not None and 0 <= b.parent < n:
            children[b.parent].append(i)

    def subtree(i):
        out, stack = set(), [i]
        while stack:
            k = stack.pop()
            if k not in out:
                out.add(k)
                stack.extend(children[k])
        return out

    joint_side = subtree(joint)
    parent_side = subtree(parent) - joint_side
    up = bones[parent].parent                      # 腕 above 腕捩 / the limb bone above a D bone's parent
    if up is not None and up >= 0 and any(t in bones[up].name for t in ("腕", "足")) and "肩" not in bones[up].name:
        parent_side.add(up)
    # the joint's own grant source (左ひざD <- 左ひざ): a bone granted from it is granted from the joint
    jsrc = {joint}
    g = bones[joint].additionalTransform
    if g and bones[joint].hasAdditionalRotate and abs(g[1] - 1.0) < 1e-6:
        jsrc.add(g[0])
    psrc = set(parent_side)
    g = bones[parent].additionalTransform
    if g and bones[parent].hasAdditionalRotate and abs(g[1] - 1.0) < 1e-6:
        psrc.add(g[0])
    share = {i: 1.0 for i in joint_side}
    share.update({i: 0.0 for i in parent_side})
    for i, b in enumerate(bones):
        g = b.additionalTransform
        if not g or not b.hasAdditionalRotate:
            continue
        src, r = g[0], g[1]
        if src in jsrc and i not in joint_side and 0.0 < r < 1.0:
            share[i] = r                           # a half-angle corrective (Ab-L-Knee 付与 左ひざ x0.48)
        elif src in jsrc and i not in share:
            share[i] = 1.0 if r >= 1.0 else max(0.0, r)
        elif src in psrc and i not in share:
            share[i] = 0.0                         # 腕捩1-3: granted from the upper arm's twist
    return share


def add_sdef(model, pmx, joint_list):
    bones = model.bones
    index = {b.name: i for i, b in enumerate(bones)}
    report = {}
    done = set()
    for name in joint_list:
        j = index[name]
        p = bones[j].parent
        if p is None or p < 0:
            continue
        share = classify(model, j, p)
        centre = tuple(bones[j].location)
        made = skipped = 0
        for vi, v in enumerate(model.vertices):
            if vi in done:
                continue
            e = entries(v.weight, pmx)
            if not e:
                continue
            wj = wp = other = 0.0
            for b, w in e:
                if b in share:
                    wj += w * share[b]
                    wp += w * (1.0 - share[b])
                else:
                    other += w
            if wj <= 1e-4 or wp <= 1e-4:
                continue
            if other > MIN_OTHER:
                skipped += 1
                continue
            total = wj + wp
            v.weight.type = pmx.BoneWeight.SDEF
            v.weight.bones = [p, j]
            v.weight.weights = pmx.BoneWeightSDEF(weight=wp / total, c=centre, r0=centre, r1=centre)
            done.add(vi)
            made += 1
        report[name] = {"parent": bones[p].name, "sdef": made, "skipped_other_bones": skipped,
                        "helpers": sorted(bones[b].name for b, s in share.items() if 0.0 < s < 1.0)}
    return report


def sdef_file(src, dst, joints=("elbows", "knees"), dry_run=False, report_path=""):
    pmx = bust_physics.load_pmx_module(None)
    model = pmx.load(src)
    if MARK in (model.comment or ""):
        raise SystemExit("already done: %s" % src)
    names = joint_names(model, pmx, joints)
    report = add_sdef(model, pmx, names)
    total = sum(r["sdef"] for r in report.values())
    if report_path:
        json.dump(report, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if dry_run or not total:
        return report
    note = "%s): %s, %d vertices" % (MARK, ", ".join("%s %d" % (k, r["sdef"]) for k, r in report.items()), total)
    model.comment = ((model.comment or "").rstrip() + "\r\n" + note).lstrip()
    model.comment_e = ((model.comment_e or "").rstrip() + "\r\n" + note).lstrip()
    # mmd_tools' module makes texture paths absolute on load and relative to the new file on save: keep them
    # relative to the input's folder when the output sits next to it (bust_physics.tune_file does the same)
    src_dir, dst_dir = os.path.dirname(os.path.abspath(src)), os.path.dirname(os.path.abspath(dst))
    for texture in model.textures:
        try:
            local = os.path.join(dst_dir, os.path.relpath(texture.path, src_dir))
        except ValueError:
            continue
        if os.path.isfile(local):
            texture.path = local
    tmp = dst + ".sdef.tmp"
    pmx.save(tmp, model, add_uv_count=model.header.additional_uvs)
    os.replace(tmp, dst)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="the new PMX ('-' with --dry-run)")
    ap.add_argument("--joints", default="elbows,knees")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    rep = sdef_file(a.input, a.output, tuple(a.joints.split(",")), a.dry_run, a.report)
    for k, r in rep.items():
        print("%-6s (parent %s): %5d SDEF, %4d left linear (other bones); share helpers %s" % (
            k, r["parent"], r["sdef"], r["skipped_other_bones"], ", ".join(r["helpers"]) or "-"))
    print("dry run" if a.dry_run else "wrote %s" % a.output)


if __name__ == "__main__":
    main()
