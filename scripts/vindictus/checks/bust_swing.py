"""Bust swing over a dance at MMD scale: angle of each bust_2 bone relative to its parent's frame (0 = modelled).
  blender -b --python bust_swing.py -- <pmx> <vmd> <last frame>"""
import math
import sys

import bpy

pmx, vmd, last = sys.argv[sys.argv.index("--") + 1:][:3]
last = int(last)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=1.0, types={"MESH", "ARMATURE", "PHYSICS", "DISPLAY"})
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
root = arm
while root.parent:
    root = root.parent
from mmd_tools.core.model import Model  # noqa: E402

import os
SPRING = os.environ.get("SPRING")
for o in bpy.data.objects:
    t_ = getattr(o, "mmd_type", "")
    if t_ == "RIGID_BODY" and o.mmd_rigid.bone in ("Bip001_L_bust_2", "Bip001_R_bust_2") or (t_ == "RIGID_BODY" and "bust_2" in (o.mmd_rigid.name_j or "")):
        rb = o.rigid_body
        if os.environ.get("MASS"):
            rb.mass = float(os.environ["MASS"])
        if os.environ.get("ANGDAMP"):
            rb.angular_damping = float(os.environ["ANGDAMP"])
        if os.environ.get("LINDAMP"):
            rb.linear_damping = float(os.environ["LINDAMP"])
        if os.environ.get("MODE"):
            o.mmd_rigid.type = os.environ["MODE"]
        print("bust body", o.name, "mode", o.mmd_rigid.type, "mass", rb.mass, "damp", rb.linear_damping, rb.angular_damping)
    if t_ == "JOINT" and "bust_2" in (o.mmd_joint.name_j or o.name):
        if SPRING:
            o.mmd_joint.spring_angular = (float(SPRING),) * 3
        if os.environ.get("LIMIT"):
            import math as _m
            lim = _m.radians(float(os.environ["LIMIT"]))
            c = o.rigid_body_constraint
            c.limit_ang_x_lower = c.limit_ang_y_lower = c.limit_ang_z_lower = -lim
            c.limit_ang_x_upper = c.limit_ang_y_upper = c.limit_ang_z_upper = lim
        print("bust joint", o.name, "spring", tuple(o.mmd_joint.spring_angular))
Model(root).build()
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o.type in ("ARMATURE", "MESH", "EMPTY"):
        try:
            o.select_set(True)
        except RuntimeError:
            pass
bpy.context.view_layer.objects.active = root
bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=1.0, margin=30, bone_mapper="PMX", update_scene_settings=True)
sc = bpy.context.scene
sc.frame_end = min(sc.frame_end, last)
w = sc.rigidbody_world
w.enabled = True
if os.environ.get("SUBSTEPS"):
    w.substeps_per_frame = int(os.environ["SUBSTEPS"])
    w.solver_iterations = int(os.environ.get("ITER", "20"))
print("world substeps", w.substeps_per_frame, "iterations", w.solver_iterations, "fps", sc.render.fps)
w.point_cache.frame_start, w.point_cache.frame_end = sc.frame_start, sc.frame_end
want = tuple(os.environ.get("BUSTNAMES", "Bip001_L_bust_2,Bip001_R_bust_2").split(","))
names = [pb.name for pb in arm.pose.bones if pb.mmd_bone.name_j in want]
angles = {n: [] for n in names}
for f in range(sc.frame_start, sc.frame_end + 1):
    sc.frame_set(f)
    for n in names:
        pb = arm.pose.bones[n]
        # rotation of the bone relative to its parent, compared with the rest relation
        rel = pb.parent.matrix.inverted() @ pb.matrix
        rest = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        angles[n].append(math.degrees((rest.inverted() @ rel).to_quaternion().angle))
for n, a in angles.items():
    print("%s: lead-in frames 0-30 max %.1f deg" % (n, max(a[:31])))
    s = sorted(a)
    print("%s: median %.1f deg, 90%% %.1f, 99%% %.1f, max %.1f, frames at >= 9.5 deg: %d of %d" % (
        n, s[len(s) // 2], s[int(0.9 * (len(s) - 1))], s[int(0.99 * (len(s) - 1))], s[-1], sum(x >= 9.5 for x in a), len(a)))
print("SWING DONE")
