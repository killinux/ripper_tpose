# Several close-up shots of a PMX in one Blender session (mat_views2 does one framing per import).
#   blender -b --factory-startup --python mat_shots.py -- --pmx P --out DIR --shots shots.json
# shots.json: [{"name": "legs", "only": ["vk_f_leg"], "context": ["pc_a01_nk_body"], "centre": 0.5, "size": 1.1,
#               "cx": 0, "cdepth": 0, "views": ["front", "side", "back"], "res": [600, 800]}, ...]
#   "only" empty = every material; "context" = materials shown with it (substring match, not counted as "only");
#   "hide" = substrings never shown in that shot.
import argparse
import json
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
ap.add_argument("--shots", required=True)
args = ap.parse_args(argv)
args.out = os.path.abspath(args.out)
os.makedirs(args.out, exist_ok=True)
shots = json.load(open(args.shots, encoding="utf-8"))

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
meshes = [o for o in scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.separate(type="MATERIAL")
bpy.ops.object.mode_set(mode="OBJECT")
objs = {}
for o in scene.objects:
    if o.type != "MESH" or not o.data.polygons:
        continue
    m = o.material_slots[o.data.polygons[0].material_index].material if o.material_slots else None
    if m is None:
        continue
    try:
        nm = m.mmd_material.name_j or m.name
    except Exception:
        nm = m.name
    objs.setdefault(nm, []).append(o)

scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.62, 1)
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(20))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
scene.collection.objects.link(cam)
scene.camera = cam
dirs = {"front": Vector((0, -3, 0)), "side": Vector((3, 0, 0)), "back": Vector((0, 3, 0)), "sidel": Vector((-3, 0, 0)),
        "back34": Vector((-2.2, 2.2, 0.6)), "front34": Vector((2.2, -2.2, 0.4)), "front34l": Vector((-2.2, -2.2, 0.4)),
        "top": Vector((0, -0.3, 3))}
for sh in shots:
    only, ctx, hide = sh.get("only", []), sh.get("context", []), sh.get("hide", [])
    for nm, os_ in objs.items():
        on = (not only or any(k in nm for k in only) or any(k in nm for k in ctx)) and not any(k in nm for k in hide)
        for o in os_:
            o.hide_render = not on
    cam.data.ortho_scale = sh.get("size", 1.9)
    scene.render.resolution_x, scene.render.resolution_y = sh.get("res", [600, 900])
    c = Vector((sh.get("cx", 0.0), sh.get("cdepth", 0.0), sh.get("centre", 1.0)))
    for label in sh.get("views", ["front"]):
        cam.location = c + dirs[label]
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(args.out, "%s__%s.png" % (sh["name"], label))
        bpy.ops.render.render(write_still=True)
print("MAT_SHOTS_DONE", len(shots))
