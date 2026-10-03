# -*- coding: utf-8 -*-
"""Read an exported PMX back with mmd_tools and render one face tile per vertex morph, so the MMD
expressions can be judged without opening MMD.

    blender -b --python preview_pmx_morphs.py -- --pmx <model.pmx> --tiles <dir> [--all] [--size 360]

Tiles are written as <dir>/NN.png; the framing is the box of everything the standard morphs move
(eyes, brows, mouth).  Without --all only the panels 眉 / 目 / 口 are rendered, with it the game's own
shapes (panel その他) too.  export_model.py labels the tiles and joins them into preview_morphs.png.

The last line printed is PMX_MORPHS={json}: {"tiles": [{"file", "name", "name_e", "panel"}], ...}.
"""
import argparse
import json
import math
import os
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--pmx", required=True)
ap.add_argument("--tiles", required=True)
ap.add_argument("--all", action="store_true", help="also the morphs of the panel その他 (the game's own shapes)")
ap.add_argument("--size", type=int, default=360)
ap.add_argument("--scale", type=float, default=0.08)
args = ap.parse_args(argv)

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
scene = bpy.context.scene
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=args.scale, types={"MESH", "ARMATURE", "MORPHS"})
root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
from mmd_tools.core.model import Model  # noqa: E402

rig = Model(root)
arm = rig.armature()
meshes = list(rig.meshes())
root.mmd_root.show_armature = False

scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 32
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
world = bpy.data.worlds.new("W")
world.use_nodes = True
# by type: with a localized UI the default node is not called "Background"
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.42, 0.42, 0.45, 1.0)
scene.world = world
for name, rot, energy in (("Key", (55, 0, -25), 2.2), ("Fill", (60, 0, 40), 0.8)):
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

keys = {}
for o in meshes:
    if o.data.shape_keys:
        for kb in o.data.shape_keys.key_blocks[1:]:
            keys.setdefault(kb.name, []).append((o, kb))


def coords(data):
    out = np.empty(len(data) * 3)
    data.foreach_get("co", out)
    return out.reshape(-1, 3)


morphs = [m for m in root.mmd_root.vertex_morphs if m.name in keys and (args.all or m.category != "OTHER")]
standard = [m for m in morphs if m.category != "OTHER"] or morphs
lo_pt, hi_pt = None, None
for m in standard:                                     # the box of what the standard morphs move
    for o, kb in keys[m.name]:
        base = coords(o.data.shape_keys.key_blocks[0].data)
        moved = np.linalg.norm(coords(kb.data) - base, axis=1) > 2e-4
        if not moved.any():
            continue
        world_pts = base[moved] @ np.array(o.matrix_world.to_3x3()).T + np.array(o.matrix_world.translation)
        lo_pt = world_pts.min(axis=0) if lo_pt is None else np.minimum(lo_pt, world_pts.min(axis=0))
        hi_pt = world_pts.max(axis=0) if hi_pt is None else np.maximum(hi_pt, world_pts.max(axis=0))
if lo_pt is None:                                      # no morph moves anything: frame the head bone
    head = arm.pose.bones.get("頭")
    c = arm.matrix_world @ head.head if head else Vector((0.0, 0.0, 1.5))
    lo_pt, hi_pt = np.array(c) - 0.08, np.array(c) + 0.08
centre = Vector(((lo_pt[0] + hi_pt[0]) / 2, (lo_pt[1] + hi_pt[1]) / 2, (lo_pt[2] + hi_pt[2]) / 2))
cam_data.ortho_scale = max(hi_pt[0] - lo_pt[0], hi_pt[2] - lo_pt[2]) * 1.45
cam_data.clip_start, cam_data.clip_end = 0.01, 100.0
cam.location = centre + Vector((0.0, -10.0, 0.0))
cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
scene.render.resolution_x = scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100


def reset():
    for pairs in keys.values():
        for _o, kb in pairs:
            kb.value = 0.0


os.makedirs(args.tiles, exist_ok=True)
tiles = []
for m in [None] + morphs:
    reset()
    if m is not None:
        for _o, kb in keys[m.name]:
            kb.value = 1.0
    path = os.path.join(args.tiles, "%02d.png" % len(tiles))
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    tiles.append({"file": path, "name": m.name if m else "", "name_e": m.name_e if m else "neutral",
                  "panel": m.category if m else ""})
reset()
print("PMX_MORPHS=" + json.dumps({"pmx": args.pmx, "tiles": tiles, "morphs_in_pmx": len(root.mmd_root.vertex_morphs)},
                                 ensure_ascii=False), flush=True)
