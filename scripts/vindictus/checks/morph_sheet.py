"""Render the face for every bone morph of a converted blend (pose = morph offsets, like mmd_tools' View).
  blender -b <converted.blend> --python morph_sheet.py -- <outdir> [front|side]"""
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Quaternion, Vector

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
view = sys.argv[sys.argv.index("--") + 2] if len(sys.argv) > sys.argv.index("--") + 2 else "front"
os.makedirs(out, exist_ok=True)
addon_utils.enable("mmd_tools", default_set=False)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == "ARMATURE" and "backup" not in o.name.lower())
root = arm.parent
while root.parent:
    root = root.parent
for o in sc.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT") or o.type == "EMPTY" and o is not root:
        o.hide_render = True
if sc.rigidbody_world:
    sc.rigidbody_world.enabled = False
morphs = root.mmd_root.bone_morphs
bones = {i.bone for m in morphs for i in m.data}

eyes = (arm.data.bones["左目"].head_local + arm.data.bones["右目"].head_local) / 2
target = arm.matrix_world @ (eyes + Vector((0, 0, -0.035)))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 85
d = Vector((0, -1, 0.05)) if view == "front" else Vector((0.75, -0.66, 0.05))
cam.location = target + d.normalized() * 0.62
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 12
sc.render.resolution_x = sc.render.resolution_y = 360
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")    # node names follow the UI language
bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1)
bg.inputs[1].default_value = 1.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(60), 0, math.radians(-25))


def reset():
    for n in bones:
        pb = arm.pose.bones[n]
        pb.location = (0, 0, 0)
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)


def shoot(tag):
    bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(out, "%s_%s.png" % (tag, view))
    bpy.ops.render.render(write_still=True)


reset()
shoot("00_neutral")
for i, m in enumerate(morphs):
    reset()
    for it in m.data:
        pb = arm.pose.bones.get(it.bone)
        if pb is None:
            continue
        pb.location = it.location
        pb.rotation_quaternion = Quaternion(it.rotation)
    shoot("%02d_%s" % (i + 1, "".join(c if c.isalnum() or c in "_-" else "x" for c in m.name_e)))
reset()
print("SHEET DONE", len(morphs))
