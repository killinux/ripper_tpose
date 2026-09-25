# -*- coding: utf-8 -*-
"""Check an exported PMX the way MMD will see it: import it back with mmd_tools (with
physics), put a dance VMD on it, step the physics frame by frame, and render

  preview.png          front view at rest (900 x 1400)
  preview_morphs.png   face close-ups: neutral + 11 MMD vertex morphs (4 x 3 tiles)
  preview_gaze.png     両目 (both eyes): neutral, left / right 20 deg, up / down 15 deg
  preview_dance.png    four frames of the dance, physics running (4 tiles side by side)

next to the .pmx.  Nothing is written into the PMX folder except these four PNGs.

    blender -b --python preview_pmx_blender.py -- --pmx <model.pmx> [--vmd <motion.vmd>]
            [--frames 150 400 650 900] [--margin 30]

The motion is imported with a 30-frame margin (rest pose blending into the first dance
pose); without it the first frame yanks every physics chain and the hair looks broken
in every later frame although the model is fine (MMD resets physics at the posed start).

The last line printed is PMX_PREVIEW={json}.
"""
import argparse
import json
import math
import os
import sys
import tempfile

import addon_utils
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--pmx", required=True)
ap.add_argument("--vmd", default=r"E:\Downloads\mmd\来杯好茶摇一摇2026.6.14by小王动画\适配【原神】芙宁娜.vmd")
ap.add_argument("--frames", type=int, nargs="*", default=[150, 400, 650, 900],
                help="motion frame numbers (before the margin is added)")
ap.add_argument("--margin", type=int, default=30,
                help="frames of rest-to-first-pose blend before the motion (mmd_tools import_vmd margin)")
ap.add_argument("--scale", type=float, default=0.08)
args = ap.parse_args(argv)

OUT = os.path.dirname(os.path.abspath(args.pmx))
MORPHS = ["まばたき", "笑い", "ウィンク", "あ", "い", "う", "お", "にやり", "困る", "怒り", "びっくり"]
report = {"pmx": args.pmx, "vmd": args.vmd if os.path.isfile(args.vmd) else None}

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
scene = bpy.context.scene
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=args.scale,
                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
from mmd_tools.core.model import Model  # noqa: E402

rig = Model(root)
arm = rig.armature()
meshes = list(rig.meshes())
report.update(bones=len(arm.data.bones), meshes=len(meshes),
              rigid_bodies=sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY"),
              joints=sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT"))
root.mmd_root.show_rigid_bodies = False
root.mmd_root.show_joints = False
root.mmd_root.show_armature = False
for o in scene.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT"):
        o.hide_render = True

# ---------------------------------------------------------------- lights, world, camera
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 32
scene.view_settings.view_transform = "Filmic"
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
world = bpy.data.worlds.new("W")
world.use_nodes = True
# by type: with the user's (Chinese) UI the default node is called 背景, not Background
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
scene.world = world
for name, rot, energy in (("Key", (50, 0, -30), 3.0), ("Fill", (60, 0, 40), 1.2), ("Rim", (70, 0, 170), 1.5)):
    light = bpy.data.lights.new(name, "SUN")
    light.energy = energy
    lo = bpy.data.objects.new(name, light)
    scene.collection.objects.link(lo)
    lo.rotation_euler = [math.radians(a) for a in rot]
cam_data = bpy.data.cameras.new("Cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(path, target, ortho, size, direction=Vector((0.0, -1.0, 0.0))):
    cam_data.ortho_scale = ortho
    cam_data.clip_start, cam_data.clip_end = 0.01, 100.0
    cam.location = target + direction * 10.0
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def bounds():
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def tile_sheet(paths, cols, out_path):
    """Compose equally sized PNG tiles into one sheet (row-major, top-left first)."""
    imgs = [bpy.data.images.load(p) for p in paths]
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    sheet = np.full((rows * h, cols * w, 4), 0.2, np.float32)
    sheet[..., 3] = 1.0
    for i, img in enumerate(imgs):
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * h                     # Blender pixel rows start at the bottom
        sheet[y0:y0 + h, c * w:(c + 1) * w] = px.reshape(h, w, 4)
    out = bpy.data.images.new("sheet", cols * w, rows * h, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = out_path
    out.file_format = "PNG"
    out.save()
    for img in imgs:
        bpy.data.images.remove(img)
    bpy.data.images.remove(out)


# ---------------------------------------------------------------- 1. front view at rest
mn, mx = bounds()
height = mx.z - mn.z
report["height_m"] = round(height, 3)
shoot(os.path.join(OUT, "preview.png"), (mn + mx) / 2, height * 1.08, (900, 1400))

# ---------------------------------------------------------------- 2. morph sheet
tmp = tempfile.mkdtemp(prefix="pmx_preview_")
head = arm.pose.bones.get("頭")
head_pos = (arm.matrix_world @ head.head) if head else Vector((0, 0, mx.z - 0.12))
keys = {}
for o in meshes:
    if o.data.shape_keys:
        for kb in o.data.shape_keys.key_blocks:
            keys.setdefault(kb.name, []).append(kb)
tiles, shown = [], []
for name in [None] + MORPHS:
    if name is not None and name not in keys:
        continue
    for kbs in keys.values():
        for kb in kbs:
            if kb.name != "Basis":
                kb.value = 0.0
    if name is not None:
        for kb in keys[name]:
            kb.value = 1.0
    p = os.path.join(tmp, "m%02d.png" % len(tiles))
    shoot(p, head_pos + Vector((0.0, 0.0, 0.05)), 0.30, (400, 400))
    tiles.append(p)
    shown.append(name or "neutral")
for kbs in keys.values():
    for kb in kbs:
        if kb.name != "Basis":
            kb.value = 0.0
if tiles:
    tile_sheet(tiles, 4, os.path.join(OUT, "preview_morphs.png"))
report["morphs_shown"] = shown
report["morphs_missing"] = [m for m in MORPHS if m not in keys]

# ---------------------------------------------------------------- 2b. gaze sheet
# 両目 turned in world terms (the model faces -Y): neutral, its left / right 20 deg,
# up / down 15 deg.  The rotation is expressed in the bone's rest frame, so the result
# does not depend on the bone roll the conversion gave it.
both = arm.pose.bones.get("両目")
if both is not None:
    both.rotation_mode = "QUATERNION"
    rest_rot = (arm.matrix_world @ arm.data.bones["両目"].matrix_local).to_3x3().normalized()
    gaze_tiles = []
    for yaw, pitch in ((0, 0), (20, 0), (-20, 0), (0, -15), (0, 15)):
        world = (Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(pitch), 3, "X"))
        both.rotation_quaternion = (rest_rot.inverted() @ world @ rest_rot).to_quaternion()
        p = os.path.join(tmp, "g%02d.png" % len(gaze_tiles))
        shoot(p, head_pos + Vector((0.0, 0.0, 0.05)), 0.24, (400, 400))
        gaze_tiles.append(p)
    both.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    tile_sheet(gaze_tiles, len(gaze_tiles), os.path.join(OUT, "preview_gaze.png"))
    report["gaze"] = "neutral, left 20, right 20, up 15, down 15"
else:
    report["gaze"] = "no 両目 bone"

# ---------------------------------------------------------------- 3. rest drop test
# Standing still, the first physics body of every chain (its parent bone has no body or a
# bone-following one) hangs from a fixed anchor and should barely move.  One that sinks
# drags its chain and skin along: Eve's scalp root sank 12 cm in 60 frames (bald head).
if not root.mmd_root.is_built:
    rig.build()
rbw = scene.rigidbody_world
bodies = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY"]
by_bone = {o.mmd_rigid.bone: o for o in bodies if o.mmd_rigid.bone}
firsts = []
for o in bodies:
    b = arm.data.bones.get(o.mmd_rigid.bone or "")
    if o.mmd_rigid.type == "0" or b is None:
        continue
    pb = by_bone.get(b.parent.name) if b.parent else None
    if pb is None or pb.mmd_rigid.type == "0":
        firsts.append(o)
if rbw is not None and firsts:
    rbw.enabled = True
    scene.frame_start, scene.frame_end = 1, 61
    rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, 61
    scene.frame_set(1)
    start = {o.name: o.matrix_world.translation.copy() for o in firsts}
    for f in range(2, 62):
        scene.frame_set(f)
    drift = sorted(((o.matrix_world.translation - start[o.name]).length, o.mmd_rigid.name_j) for o in firsts)
    report["rest_drop_test"] = {"chain_roots": len(firsts), "max_drift_cm": round(drift[-1][0] * 100, 1),
                                "over_3cm": ["%s %.1f cm" % (n, d * 100) for d, n in drift if d > 0.03]}
    scene.frame_set(1)

# ---------------------------------------------------------------- 4. dance with physics
if report["vmd"]:
    bpy.ops.object.select_all(action="DESELECT")
    for o in [root] + list(root.children_recursive):
        try:
            o.select_set(True)
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = root
    # margin: mmd_tools keys the rest pose at frame 1 and starts the motion at margin + 1,
    # blending in between.  With margin 0 the model jumps from the rest pose (physics was
    # built there) to the dance's first pose in one frame, the joints yank every chain and
    # the hair stays tangled for the rest of the clip (fringe flipped over the crown,
    # ponytail flung off the head).  MMD itself resets physics at the posed first frame.
    bpy.ops.mmd_tools.import_vmd(filepath=args.vmd, scale=args.scale, margin=args.margin, bone_mapper="PMX",
                                 update_scene_settings=True)
    rbw = scene.rigidbody_world
    if rbw is not None:
        rbw.enabled = False                          # drop the rest-test cache (frames 1-61)
        rbw.enabled = True
        rbw.point_cache.frame_start = scene.frame_start
        rbw.point_cache.frame_end = scene.frame_end
    shift = args.margin + 1 if args.margin > 0 else 0
    want = sorted(f + shift for f in args.frames if scene.frame_start <= f + shift <= scene.frame_end)
    hips = arm.pose.bones.get("下半身") or arm.pose.bones.get("センター")
    dance, far = [], 0.0
    for f in range(scene.frame_start, (want[-1] if want else scene.frame_start) + 1):
        scene.frame_set(f)                           # physics steps in order
        if f in want:
            c = arm.matrix_world @ hips.head if hips else Vector((0, 0, height / 2))
            target = Vector((c.x, c.y, height * 0.52))
            p = os.path.join(tmp, "d%02d.png" % len(dance))
            shoot(p, target, height * 1.25, (600, 900))
            dance.append(p)
            dyn = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.rigid_body
                   and o.rigid_body.type == "ACTIVE" and not o.rigid_body.kinematic]
            if dyn:
                far = max(far, max((o.matrix_world.translation - c).length for o in dyn))
    if dance:
        tile_sheet(dance, len(dance), os.path.join(OUT, "preview_dance.png"))
    report.update(dance_frames=[f - shift for f in want], margin=args.margin,
                  motion_frames=[scene.frame_start, scene.frame_end],
                  max_rigid_body_distance_from_hips_m=round(far, 2))

print("PMX_PREVIEW=" + json.dumps(report, ensure_ascii=False), flush=True)
