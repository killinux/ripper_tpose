# Render a PMX from several angles (Eevee, mmd_tools materials, rest pose, no physics).
#   blender -b --factory-startup --python render_views.py -- --pmx P --out DIR --views name:yaw:pitch:centre_m:size_m ...
#           [--res 700x1100] [--dark] [--persp]
# yaw 0 = front, 90 = the model's left side, 180 = back; pitch > 0 looks down.
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
ap.add_argument("--out", required=True)
ap.add_argument("--views", nargs="+", default=["front:0:0:0.86:1.95"])
ap.add_argument("--res", default="700x1100")
ap.add_argument("--dark", action="store_true", help="dark studio background like the HS2 previews")
ap.add_argument("--hide", nargs="*", default=[], help="material name substrings to hide")
args = ap.parse_args(argv)
args.out = os.path.abspath(args.out)
os.makedirs(args.out, exist_ok=True)

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
try:
    bpy.context.preferences.addons["mmd_tools"].preferences.shared_toon_folder = r"E:\tools\MikuMikuDanceE_v932x64\Data"
except Exception as e:
    print("toon folder:", e)
bpy.ops.mmd_tools.import_model(filepath=os.path.abspath(args.pmx), scale=0.08, types={"MESH", "ARMATURE"})
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o, do_unlink=True)
if args.hide:
    meshes = [o for o in scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="MATERIAL")
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in scene.objects:
        if o.type != "MESH" or not o.data.polygons or not o.material_slots:
            continue
        m = o.material_slots[o.data.polygons[0].material_index].material
        try:
            nm = m.mmd_material.name_j or m.name
        except Exception:
            nm = m.name
        if any(h in nm for h in args.hide):
            o.hide_render = True
w, h = (int(x) for x in args.res.split("x"))
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = w, h
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.eevee.taa_render_samples = 32
world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = (0.045, 0.045, 0.05, 1) if args.dark else (0.6, 0.6, 0.62, 1)
world.node_tree.nodes["Background"].inputs[0].default_value = bg
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
for spec in args.views:
    name, yaw, pitch, centre, size = spec.split(":")
    yaw, pitch, centre, size = math.radians(float(yaw)), math.radians(float(pitch)), float(centre), float(size)
    cx = 0.0
    if "@" in name:                       # name@x_offset_m : shift the look-at point sideways (model x, metres)
        name, cxs = name.split("@")
        cx = float(cxs)
    c = Vector((cx, 0.0, centre))
    # Blender: model faces -Y; model's left = +X
    d = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))) * 4.0
    cam.location = c + d
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = size * max(1.0, w / h) if w > h else size
    cam.data.ortho_scale = size
    cam.data.sensor_fit = "VERTICAL"
    sun.rotation_euler = (math.radians(52), 0, yaw + math.radians(24))
    scene.render.filepath = os.path.join(args.out, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath, flush=True)
print("RENDER_VIEWS_DONE")
