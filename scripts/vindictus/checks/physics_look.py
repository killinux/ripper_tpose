"""Head renders at frame 1 and after N frames of standing-still physics (front / back / right / left).
  blender -b --python physics_look.py -- <file.pmx> <outdir> <tag> [frames]"""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
pmx, outdir, tag = args[:3]
frames = int(args[3]) if len(args) > 3 else 150
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=0.08, types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
root = arm
while root.parent:
    root = root.parent
from mmd_tools.core.model import Model  # noqa: E402

Model(root).build()
sc = bpy.context.scene
w = sc.rigidbody_world
w.enabled = True
w.point_cache.frame_start, w.point_cache.frame_end = 1, frames
for o in bpy.data.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT") or (o.type == "EMPTY" and o is not root):
        o.hide_render = True
head = arm.matrix_world @ arm.pose.bones["頭"].head
target = head + Vector((0, 0, 0.02))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 50
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 12
sc.render.resolution_x = sc.render.resolution_y = 420
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w")
sc.world = wd
wd.use_nodes = True
next(n for n in wd.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.45, 0.45, 0.48, 1)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(55), 0, math.radians(20))


def shoot(frame_tag):
    for label, d in (("front", (0, -1, 0.1)), ("back", (0, 1, 0.1)), ("right", (-1, 0, 0.1)), ("left", (1, 0, 0.1))):
        cam.location = target + Vector(d).normalized() * 0.85
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(outdir, "%s_f%03d_%s.png" % (tag, frame_tag, label))
        bpy.ops.render.render(write_still=True)


sc.frame_set(1)
shoot(1)
for f in range(2, frames + 1):
    sc.frame_set(f)
shoot(frames)
print("LOOK DONE")
