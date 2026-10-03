# -*- coding: utf-8 -*-
"""A turntable video of a Taimanin Squad .blend: the model turns once under the fixed toon light,
then the camera goes to the face and the light sweeps from one side to the other (the SDF face
shadow and the cel shading change as they do in the game).

    blender -b <id>.blend --python render_turntable.py -- --out <id>_turntable.mp4
            [--seconds 6] [--fps 30] [--size 720 1080] [--no-face]

Nothing is saved back to the .blend.  Prints TSQ_TURNTABLE={json}.
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--seconds", type=float, default=6.0, help="length of the full turn")
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--size", type=int, nargs=2, default=[720, 1080])
ap.add_argument("--no-face", action="store_true", help="skip the face close-up with the light sweep")
args = ap.parse_args(argv)

scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
meshes = [o for o in scene.objects if o.type == "MESH"]
for o in meshes:
    if o.get("tsq_role") == "weapon_parked":                    # parked at the feet in the prefab pose
        o.hide_render = True
body = [o for o in meshes if not o.hide_render]
pts = [o.matrix_world @ Vector(c) for o in body for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, extent = (lo + hi) / 2, hi - lo
radius = max(extent.x, extent.y) / 2                     # the model turns: frame the widest half-width
faces = [o for o in meshes if o.get("tsq_role") == "face"]
sun = bpy.data.objects.get("TSQ_Sun")

turn = max(2, int(round(args.seconds * args.fps)))
face_frames = 0 if (args.no_face or not faces or sun is None) else int(round(4.0 * args.fps))
scene.frame_start, scene.frame_end = 1, turn + face_frames
scene.render.fps = args.fps

# the model turns once
arm.rotation_mode = "XYZ"
for frame, angle in ((1, 0.0), (turn + 1, 2.0 * math.pi)):
    arm.rotation_euler = (0.0, 0.0, angle)
    arm.keyframe_insert("rotation_euler", index=2, frame=frame)
for fc in arm.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

cam_data = bpy.data.cameras.new("TurntableCam")
cam_data.lens = 85.0
cam_data.sensor_fit = "VERTICAL"
cam = bpy.data.objects.new("TurntableCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
aspect = args.size[0] / args.size[1]
half_v = math.atan(cam_data.sensor_height / (2.0 * cam_data.lens))
half_h = math.atan(math.tan(half_v) * aspect)
dist = max(extent.z * 0.54 / math.tan(half_v), radius * 1.08 / math.tan(half_h)) + radius


def place(frame, target, distance, direction=Vector((0.0, -1.0, 0.04))):
    cam.location = target + direction.normalized() * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)


place(1, center, dist)
place(turn, center, dist)
if face_frames:
    fp = [o.matrix_world @ Vector(c) for o in faces for c in o.bound_box]
    f_lo = Vector((min(p.x for p in fp), min(p.y for p in fp), min(p.z for p in fp)))
    f_hi = Vector((max(p.x for p in fp), max(p.y for p in fp), max(p.z for p in fp)))
    f_center, f_size = (f_lo + f_hi) / 2, max((f_hi - f_lo).x, (f_hi - f_lo).z)
    f_center.z += f_size * 0.08
    f_dist = f_size * 1.15 / math.tan(half_h)
    place(turn + 1, f_center, f_dist, Vector((0.0, -1.0, 0.0)))
    place(turn + face_frames, f_center, f_dist, Vector((0.0, -1.0, 0.0)))
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    # the light swings from the character's right to her left and back to where it was
    sun.rotation_mode = "XYZ"
    home = sun.rotation_euler.copy()
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        az = math.radians(-100.0 + 200.0 * t)            # az > 0: the light is on her left (+X)
        d = Vector((math.sin(az), -math.cos(az), 0.5)).normalized()
        sun.rotation_euler = d.to_track_quat("Z", "Y").to_euler("XYZ")
        sun.keyframe_insert("rotation_euler", frame=turn + 1 + int(round(t * (face_frames - 1))))
    sun.rotation_euler = home
    sun.keyframe_insert("rotation_euler", frame=1)
    sun.keyframe_insert("rotation_euler", frame=turn)
    for fc in sun.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        for kp in fc.keyframe_points:
            if kp.co.x <= turn:
                kp.interpolation = "CONSTANT"

scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 16
scene.render.resolution_x, scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "HIGH"
scene.render.ffmpeg.audio_codec = "NONE"
scene.render.filepath = os.path.abspath(args.out)
scene.render.use_file_extension = False
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.render.render(animation=True)
print("TSQ_TURNTABLE=" + json.dumps({"video": os.path.abspath(args.out), "frames": scene.frame_end,
                                      "fps": args.fps, "face_frames": face_frames}), flush=True)
