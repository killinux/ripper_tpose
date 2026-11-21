# Quick deformation check: import a PMX and a VMD, jump to a few frames (no physics) and render stills.
#   blender -b --factory-startup --python pose_test.py -- --pmx P --vmd V --out DIR --frames 60 120 185 [--res 600x900]
#           [--yaws 0 150] [--centre 0.95] [--size 2.2]
import argparse
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--pmx", required=True)
ap.add_argument("--vmd", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--frames", nargs="+", type=int, default=[60, 120, 185])
ap.add_argument("--yaws", nargs="+", type=float, default=[0.0, 150.0])
ap.add_argument("--res", default="600x900")
ap.add_argument("--centre", type=float, default=0.95)
ap.add_argument("--size", type=float, default=2.3)
args = ap.parse_args(argv)
os.makedirs(args.out, exist_ok=True)

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
try:
    bpy.context.preferences.addons["mmd_tools"].preferences.shared_toon_folder = r"E:\tools\MikuMikuDanceE_v932x64\Data"
except Exception as e:
    print("toon folder:", e)
bpy.ops.mmd_tools.import_model(filepath=os.path.abspath(args.pmx), scale=0.08, types={"MESH", "ARMATURE"})
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
root = arm.parent
bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.mmd_tools.import_vmd(filepath=os.path.abspath(args.vmd), scale=0.08, margin=0)
for o in list(scene.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o, do_unlink=True)
w, h = (int(x) for x in args.res.split("x"))
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = w, h
scene.render.image_settings.file_format = "PNG"
scene.eevee.taa_render_samples = 16
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.62, 1)
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = args.size
cam.data.sensor_fit = "VERTICAL"
scene.collection.objects.link(cam)
scene.camera = cam
bones = {pb.mmd_bone.name_j or pb.name: pb for pb in arm.pose.bones}
for f in args.frames:
    scene.frame_set(f)
    bpy.context.view_layer.update()
    hip = arm.matrix_world @ bones["下半身"].head if "下半身" in bones else Vector((0, 0, 1))
    c = Vector((hip.x, hip.y, args.centre))
    for yaw in args.yaws:
        a = math.radians(yaw)
        d = Vector((math.sin(a), -math.cos(a), 0.12)) * 4.0
        cam.location = c + d
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sun.rotation_euler = (math.radians(52), 0, a + math.radians(24))
        scene.render.filepath = os.path.join(os.path.abspath(args.out), "f%04d_y%03d.png" % (f, int(yaw)))
        bpy.ops.render.render(write_still=True)
        print("RENDERED", scene.render.filepath, flush=True)
print("POSE_TEST_DONE")
