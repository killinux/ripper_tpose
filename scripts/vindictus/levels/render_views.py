"""Blender 3.6: EEVEE stills of a level .blend made by build_level.py (positions in UE cm, converted here).

  blender -b scene.blend --python render_views.py -- --out <dir>
      [--top name:cx,cy:size_cm[:height_cm]] [--cam name:x,y,z:tx,ty,tz[:lens[:WxH]]] ... [--size 1280x720] [--samples 16]"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--top", action="append", default=[])
ap.add_argument("--cam", action="append", default=[])
ap.add_argument("--size", default="1280x720")
ap.add_argument("--samples", type=int, default=16)
ap.add_argument("--exposure", type=float, default=0.0)
ap.add_argument("--disperse", action="store_true",
                help="render like disperse_pair.py: Standard view, bloom 1.2, its shadow / AO defaults, vertical 24 mm sensor")
args = ap.parse_args(argv)
args.out = os.path.abspath(args.out)
os.makedirs(args.out, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
ee = scene.eevee
ee.taa_render_samples = args.samples
ee.use_gtao = True
ee.gtao_distance = 2.0
ee.use_soft_shadows = True
ee.shadow_cascade_size = "4096"
ee.use_bloom = False
scene.view_settings.view_transform = "Filmic"
scene.view_settings.look = "Medium High Contrast"
scene.view_settings.exposure = args.exposure
if args.disperse:
    ee.use_ssr = True
    ee.gtao_distance = 0.2
    ee.shadow_cascade_size = "2048"
    ee.use_bloom = True
    ee.bloom_threshold = 1.2
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
for o in scene.objects:
    if o.type == "LIGHT" and o.data.type == "SUN" and not args.disperse:
        o.data.shadow_cascade_max_distance = 400.0
        o.data.shadow_cascade_count = 4


def ue(x, y, z):
    return Vector((x * 0.01, -y * 0.01, z * 0.01))


cam_data = bpy.data.cameras.new("view")
cam = bpy.data.objects.new("view", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.clip_start = 0.1
cam_data.clip_end = 20000.0
if args.disperse:
    cam_data.sensor_fit = "VERTICAL"
    cam_data.clip_end = 5000.0


def shoot(name, w, h):
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.filepath = os.path.join(args.out, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("[views] wrote", scene.render.filepath, flush=True)


for spec in args.top:
    parts = spec.split(":")
    name, (cx, cy), size = parts[0], (float(v) for v in parts[1].split(",")), float(parts[2])
    height = float(parts[3]) if len(parts) > 3 else 20000.0
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size * 0.01
    cam.location = ue(cx, cy, height)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    shoot(name, 1600, 1600)

w, h = (int(v) for v in args.size.split("x"))
for spec in args.cam:
    parts = spec.split(":")
    name = parts[0]
    pos = ue(*(float(v) for v in parts[1].split(",")))
    tgt = ue(*(float(v) for v in parts[2].split(",")))
    cam_data.type = "PERSP"
    cam_data.lens = float(parts[3]) if len(parts) > 3 else 24.0
    cam.location = pos
    cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
    cw, ch = (int(v) for v in parts[4].split("x")) if len(parts) > 4 else (w, h)     # optional own size WxH
    shoot(name, cw, ch)
