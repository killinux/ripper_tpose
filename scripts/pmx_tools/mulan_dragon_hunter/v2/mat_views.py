# Render a PMX material by material (each with the listed context materials kept), front + back, Eevee, no physics.
#   blender -b --factory-startup --python mat_views.py -- --pmx P --out DIR [--context skin face] [--only m1 m2] [--skip m]
#   [--centre z] [--size m] [--views front back side]
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
ap.add_argument("--context", nargs="*", default=["skin", "face", "eye", "teeth", "lash"])
ap.add_argument("--only", nargs="*", default=[])
ap.add_argument("--skip", nargs="*", default=[])
ap.add_argument("--centre", type=float, default=1.0)
ap.add_argument("--size", type=float, default=1.9)
ap.add_argument("--views", nargs="*", default=["front", "back"])
ap.add_argument("--all-in-one", action="store_true", help="one render with every non-context material instead")
args = ap.parse_args(argv)
args.out = os.path.abspath(args.out)
os.makedirs(args.out, exist_ok=True)

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
try:
    bpy.context.preferences.addons["mmd_tools"].preferences.shared_toon_folder = r"E:\tools\MikuMikuDanceE_v932x64\Data"
except Exception as e:
    print("toon folder:", e)
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=0.08, types={"MESH", "ARMATURE"})
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in scene.objects if o.type == "MESH"]
# one object per material (material alpha tricks do not hide mmd_tools materials reliably)
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.separate(type="MATERIAL")
bpy.ops.object.mode_set(mode="OBJECT")
objs = {}
mats = []
for o in scene.objects:
    if o.type != "MESH" or not o.data.polygons:
        continue
    used = {o.data.polygons[0].material_index}
    m = o.material_slots[list(used)[0]].material if o.material_slots else None
    if m is None:
        continue
    objs.setdefault(m, []).append(o)
    if m not in mats:
        mats.append(m)


def mmd_name(m):
    try:
        return m.mmd_material.name_j or m.name
    except Exception:
        return m.name


def is_context(m):
    n = mmd_name(m).lower()
    return any(c.lower() in n for c in args.context)


def show(m, on):
    for o in objs.get(m, []):
        o.hide_render = not on


scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 500
scene.render.resolution_y = 900
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.62, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(20))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = args.size
scene.collection.objects.link(cam)
scene.camera = cam
c = Vector((0.0, 0.0, args.centre))
dirs = {"front": Vector((0, -3, 0)), "side": Vector((3, 0, 0)), "back": Vector((0, 3, 0)), "sidel": Vector((-3, 0, 0))}

targets = [m for m in mats if not is_context(m) and (not args.only or any(k in mmd_name(m) for k in args.only))
           and not any(k in mmd_name(m) for k in args.skip)]
groups = [[m] for m in targets]
if args.all_in_one:
    groups = [targets]
for g in groups:
    for m in mats:
        show(m, is_context(m) or m in g)
    tag = "ALL" if args.all_in_one else mmd_name(g[0]).replace("/", "_")
    for label in args.views:
        d = dirs[label]
        cam.location = c + d
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(args.out, "%s__%s.png" % (tag, label))
        bpy.ops.render.render(write_still=True)
print("MAT_VIEWS_DONE", len(groups))
