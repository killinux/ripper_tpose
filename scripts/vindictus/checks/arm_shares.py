"""Does the conversion keep the game's arm skin where the game put it?  Per vertex, the share of its weight on the upper
arm, the forearm and the hand - in Convert to MMD 5's input (the XPS as XNALaraMesh imports it: UE names, a bone
counts for the arm segment whose subtree it is in) and in its output (<id>_converted.blend: 腕 + 腕捩*, ひじ + 手捩*,
手首 + fingers) - binned along the arm (0 shoulder, 1 elbow, 2 wrist).  Same vertex order on both sides (the
conversion never re-orders; meshes are paired by vertex count).

    blender -b <id>_converted.blend --factory-startup --python arm_shares.py -- <id>.xps [l|r]

Expected after the 2026-10-04 fix (export_pmx: helpers folded into their segment, limbs.straighten_forearms): no
change from 0.4 to 1.7, 0.02 at 1.8; what is left is the plugin's own design - its armpit smoothing adds 肩 weight to
腕 near the shoulder (complete_missing_bones), its wrist reclaim moves 手首 weight on the forearm onto 手捩 from 1.8 on
(add_twist_bone).  The archived PCF_005 (10-03) had 0.60: the lowest eighth of the upper arm rode ひじ.  Prints
ARM_SHARES= per side with the worst mean change between 0.4 and 1.8.
"""
import re
import sys
from collections import defaultdict

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
XPS = argv[0]
SIDES = argv[1:] or ["l", "r"]

converted = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "左腕" in o.data.bones)
converted_meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() == converted]
addon_utils.enable("XNALaraMesh-master", default_set=True)
before = set(bpy.data.objects)
bpy.ops.xps_tools.import_model(filepath=XPS)
new = [o for o in bpy.data.objects if o not in before]
source = next(o for o in new if o.type == "ARMATURE")
source_meshes = [o for o in new if o.type == "MESH"]
# Bones whose skin keeps their own name through the conversion (cloth / outfit chains such as PCF_005's arm feathers,
# which hang under the upper arm and swing with the physics) are not arm skin: counted on neither side.
kept = set()
for mesh in converted_meshes:
    names = {g.index: g.name for g in mesh.vertex_groups}
    for v in mesh.data.vertices:
        kept.update(names[g.group] for g in v.groups if g.weight > 0.0)


def shares(meshes, family):
    out = {}
    for mesh in meshes:
        names = {g.index: g.name for g in mesh.vertex_groups}
        rows = []
        for v in mesh.data.vertices:
            acc, total = defaultdict(float), 0.0
            for g in v.groups:
                if g.weight > 0.0:
                    total += g.weight
                    acc[family(names.get(g.group, ""))] += g.weight
            rows.append(tuple(acc[k] / total if total else 0.0 for k in "UFH"))
        out[mesh] = rows
    return out


for side in SIDES:
    jp, xs = {"l": ("左", "left"), "r": ("右", "right")}[side]
    sb = source.data.bones
    up, lo, hd = sb["arm %s shoulder 2" % xs], sb["arm %s elbow" % xs], sb["arm %s wrist" % xs]

    def source_family(name, up=up, lo=lo, hd=hd):
        if name in kept:
            return None
        b = sb.get(name)
        while b is not None:
            if b == hd:
                return "H"
            if b == lo:
                return "F"
            if b == up:
                return "U"
            b = b.parent
        return None

    def converted_family(name, jp=jp):
        if re.match(jp + r"(腕捩\d?|腕)$", name):
            return "U"
        if re.match(jp + r"(ひじ|手捩\d?)$", name):
            return "F"
        if name.startswith(jp) and re.search(r"(手首|指)", name):
            return "H"
        return None

    a = shares(source_meshes, source_family)
    b = shares(converted_meshes, converted_family)
    sh, el, wr = up.head_local, lo.head_local, hd.head_local
    to_arm = source.matrix_world.inverted()

    def along(p):
        t = (p - sh).dot(el - sh) / (el - sh).length_squared
        return t if t <= 1.0 else 1.0 + (p - el).dot(wr - el) / (wr - el).length_squared

    bins = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0])
    for mesh in source_meshes:
        pair = [c for c in converted_meshes if len(c.data.vertices) == len(mesh.data.vertices)]
        if not pair:
            print("  no converted mesh for %s (%d vertices)" % (mesh.name, len(mesh.data.vertices)))
            continue
        other = min(pair, key=lambda c: c.name.split(".")[0] != mesh.name.split(".")[0])
        m = to_arm @ mesh.matrix_world
        for i, v in enumerate(mesh.data.vertices):
            s0, s1 = a[mesh][i], b[other][i]
            if sum(s0) < 0.05 and sum(s1) < 0.05:
                continue
            k = round(along(m @ v.co) * 10) / 10
            if -0.5 <= k <= 2.3:
                row = bins[k]
                row[0] += 1
                for j in range(3):
                    row[1 + j] += abs(s1[j] - s0[j])
                row[4] += max(abs(s1[j] - s0[j]) for j in range(3)) > 0.2
    print("\nARM %s: share change through the conversion (U upper arm, F forearm, H hand)" % xs)
    print("  along  verts  mean|dU|  mean|dF|  mean|dH|  verts >0.2")
    worst_elbow = 0.0
    for k in sorted(bins):
        n, du, df, dh, big = bins[k]
        print("  %5.1f  %5d   %6.3f    %6.3f    %6.3f    %5d" % (k, n, du / n, df / n, dh / n, big))
        if 0.4 <= k <= 1.8:
            worst_elbow = max(worst_elbow, du / n, df / n, dh / n)
    print("ARM_SHARES=%s worst mean change 0.4-1.8: %.3f" % (side, worst_elbow), flush=True)
