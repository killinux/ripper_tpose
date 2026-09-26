"""Standing-still physics check of a PMX: import with PHYSICS (env SCALE, default 1.0 = MMD units), build, step
150 frames in the rest pose, report how far every physics-driven bone's tail moved (sag / blow-up) and the bust swing angle.
  blender -b --python physics_standing.py -- <file.pmx>     env: SCALE=1.0|0.08, NOHAIRCOLL=1"""
import math
import sys

import bpy
from mathutils import Vector

pmx = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
import os
SCALE = float(os.environ.get("SCALE", "1.0"))     # 1.0 = MMD units (MMD-like gravity); 0.08 = metres
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=SCALE, types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
root = arm
while root.parent:
    root = root.parent
from mmd_tools.core.model import Model  # noqa: E402

import os as _os
if _os.environ.get("NOHAIRCOLL"):
    n = 0
    for o in bpy.data.objects:
        if getattr(o, "mmd_type", "") == "RIGID_BODY" and "hair" in o.mmd_rigid.bone.lower():
            for g in (0, 1, 2, 3, 4, 5, 6, 7):
                o.mmd_rigid.collision_group_mask[g] = True
            n += 1
    print("hair bodies no longer colliding with groups 0-7:", n)
Model(root).build()
sc = bpy.context.scene
world = sc.rigidbody_world
world.enabled = True
world.point_cache.frame_start, world.point_cache.frame_end = 1, 150
tracked = [pb for pb in arm.pose.bones if "mmd_tools_rigid_track" in pb.constraints]
print("rigid bodies %d, bones driven by physics %d" % (len(world.collection.objects), len(tracked)))
sc.frame_set(1)
rest = {pb.name: (arm.matrix_world @ pb.tail).copy() for pb in tracked}
rest_dir = {pb.name: (pb.tail - pb.head).normalized() for pb in tracked}
samples = {}
for f in range(1, 151):
    sc.frame_set(f)
    if f in (30, 60, 150):
        samples[f] = {pb.name: ((arm.matrix_world @ pb.tail) - rest[pb.name]).length for pb in tracked}
end = samples[150]
worst = sorted(end.items(), key=lambda kv: -kv[1])[:10]
CM = 0.08 * 100 / SCALE
print("tail drift at frame 150: worst %s" % ", ".join("%s %.1f cm" % (n, d * CM) for n, d in worst))
hair = [n for n in end if "hair" in n.lower()]
bust = [n for n in end if "bust" in n.lower() or "胸" in arm.pose.bones[n].mmd_bone.name_j]
for label, names in (("hair", hair), ("bust", bust)):
    if names:
        vals = sorted(end[n] for n in names)
        print("%s: %d bones, drift median %.1f cm, 90%% %.1f cm, max %.1f cm; frame 30 max %.1f, frame 60 max %.1f" % (
            label, len(names), vals[len(vals) // 2] * CM, vals[int(0.9 * (len(vals) - 1))] * CM, vals[-1] * CM,
            max(samples[30][n] for n in names) * CM, max(samples[60][n] for n in names) * CM))
for n in bust:
    pb = arm.pose.bones[n]
    ang = math.degrees(rest_dir[n].angle((pb.tail - pb.head).normalized(), 0.0))
    print("   %s swung %.1f deg from rest" % (n, ang))
chains = {}
for pb in tracked:
    if "hair" in pb.name.lower() and not any("hair" in c.name.lower() and c in tracked for c in pb.children):
        v = (arm.matrix_world @ pb.tail) - rest[pb.name]
        chains[pb.name] = v
for n, v in sorted(chains.items(), key=lambda kv: -kv[1].length)[:8]:
    print("   tip %-26s moved %.1f cm  dir (%.2f, %.2f, %.2f)" % (n, v.length * CM, *(v.normalized())))
far = [n for n, d in end.items() if d * CM > 50]
print("blown up (> 50 cm):", far[:10], "PHYS DONE")
