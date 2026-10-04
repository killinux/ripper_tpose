"""Does every part of a built .blend still sit on its bones?  For each part mesh: the vertices skinned mostly (> 0.6)
to a foot / hand / head bone, their centroid in that bone's own frame, in the built blend and in the part's own PSK.
A part that moved rigidly with its bone keeps the same numbers; a difference is how far the build moved the bone away
from the mesh.  Before the 10-03 fix of build_blend.py the shoes of 9 Fiona outfits were 12.6-13.0 cm off.
  blender -b --factory-startup --python part_alignment.py -- <id> [id ...]     env ROOT (default D:\\vindictus_exports\\blend)"""
import json
import os
import sys

import bpy

ids = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.environ.get("ROOT", r"D:\vindictus_exports\blend")
KEYS = ("foot_r", "foot_l", "hand_r", "head", "Bip001_R_Foot", "Bip001_L_Foot", "Bip001_R_Hand", "Bip001_Head")
LIMIT = 1.0          # cm


def offsets(arm, meshes):
    """{bone: (centroid of its vertices in the bone's frame, count)}"""
    out = {}
    for o in meshes:
        names = {g.index: g.name for g in o.vertex_groups}
        acc = {}
        for v in o.data.vertices:
            if not v.groups:
                continue
            g = max(v.groups, key=lambda g: g.weight)
            n = names.get(g.group)
            if n in KEYS and n in arm.data.bones and g.weight > 0.6:
                s, c = acc.get(n, (None, 0))
                p = o.matrix_world @ v.co
                acc[n] = (p if s is None else s + p, c + 1)
        for n, (s, c) in acc.items():
            if c >= 20:
                inv = (arm.matrix_world @ arm.data.bones[n].matrix_local).inverted()
                out[n] = (inv @ (s / c), c)
    return out


bad = 0
for mid in ids:
    spec = json.load(open(os.path.join(ROOT, mid, "spec.json"), encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, mid, mid + ".blend"))
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    built = {}
    for part in spec["parts"]:
        objs = [o for o in bpy.data.objects if o.type == "MESH" and o.name.split(".")[0].endswith("_" + part["name"])]
        if objs:
            built[part["name"]] = offsets(arm, objs)
    for part in spec["parts"]:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.preferences.addon_enable(module="io_scene_psk_psa")
        bpy.ops.import_scene.psk(filepath=part["psk"])
        own_arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
        if own_arm is None:
            continue
        own = offsets(own_arm, [o for o in bpy.data.objects if o.type == "MESH"])
        for bone, (vec, count) in sorted(own.items()):
            got = built.get(part["name"], {}).get(bone)
            if got is None:
                continue
            d = (got[0] - vec).length
            bad += d > LIMIT
            print("ALIGN %s %-10s %-14s %5d verts  off by %.1f cm%s" % (
                mid, part["name"], bone, count, d, "   <<< off its bone" if d > LIMIT else ""), flush=True)
print("ALIGN_DONE %d part/bone pairs off by more than %.1f cm" % (bad, LIMIT))
