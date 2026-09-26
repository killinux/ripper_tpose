# -*- coding: utf-8 -*-
"""Look at the FF7 expressions without exporting: build them on a .blend (the FF7 Face Morphs add-on's
core, scripts/blender_addons/ff7_face_morphs) and render a front close-up of the face per expression.
Nothing is saved into the .blend.

  blender -b X.blend --python ff7_face_morph_sheet.py -- --face-data <json> --out <dir>
          [--panels EYE,EYEBROW,MOUTH,OTHER] [--strength EYEBROW=1.5 ...] [--save copy.blend]

Writes <dir>/morph_NN.png (NN = 00 rest pose, then the expressions in panel order) + morphs.json.
Prints FF7_FACE_SHEET={json}.
"""
import argparse
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender_addons"))
from ff7_face_morphs import core  # noqa: E402


def render_sheet(arm, meshes, names, out_dir, size=(420, 480)):
    """Orthographic close-up of the face: the rest pose, then every expression at 1.0."""
    scn = bpy.context.scene
    for o in scn.objects:
        if o.type == "LIGHT":
            o.hide_render = True
    bones = arm.data.bones
    frame, spacing = core.face_frame(arm)
    axes = arm.matrix_world.to_3x3() @ frame.to_3x3()
    fwd, left, up = axes.col[0].normalized(), axes.col[1].normalized(), axes.col[2].normalized()
    span = spacing * arm.matrix_world.to_scale()[0]
    centre = arm.matrix_world @ ((bones["C_Chin"].head_local + bones["C_Forehead"].head_local) * 0.5)
    cam = bpy.data.objects.new("morph_cam", bpy.data.cameras.new("morph_cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", span * 3.3
    scn.collection.objects.link(cam)
    cam.location = centre + fwd * span * 10.0
    cam.rotation_euler = (-fwd).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start, cam.data.clip_end = span * 0.2, span * 40.0
    scn.camera = cam
    sun = bpy.data.objects.new("morph_key", bpy.data.lights.new("morph_key", "SUN"))
    sun.data.energy = 2.5
    scn.collection.objects.link(sun)
    sun.rotation_euler = (-(fwd * 0.8 + left * 0.35 + up * 0.5)).normalized().to_track_quat("-Z", "Y").to_euler()
    if scn.world is None:
        scn.world = bpy.data.worlds.new("morph_world")
    scn.world.use_nodes = True
    bg = next((n for n in scn.world.node_tree.nodes if n.type == "BACKGROUND"), None)   # names may be Chinese
    if bg:
        for link in list(bg.inputs[0].links):
            scn.world.node_tree.links.remove(link)
        bg.inputs[0].default_value = (0.42, 0.42, 0.42, 1)
        bg.inputs[1].default_value = 1.0
    scn.render.engine = "BLENDER_EEVEE"
    scn.eevee.taa_render_samples = 16
    scn.view_settings.view_transform = "Standard"
    scn.render.resolution_x, scn.render.resolution_y = size
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format, scn.render.image_settings.color_mode = "PNG", "RGB"
    shots = []
    for name in [""] + list(names):
        core.preview(meshes, name, 1.0)
        path = os.path.join(out_dir, "morph_%02d.png" % len(shots))
        scn.render.filepath = path
        bpy.ops.render.render(write_still=True)
        shots.append((name or "rest", path))
    core.preview(meshes, "", 0.0)
    return shots


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--face-data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--panels", default=",".join(core.CATEGORIES))
    ap.add_argument("--strength", action="append", default=[], metavar="PANEL=FACTOR")
    ap.add_argument("--save", default="", help="also save a copy of the blend with the shape keys")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    _arm, meshes = core.model_parts(arm)
    strengths = {k.strip().upper(): float(v) for k, _s, v in (x.partition("=") for x in a.strength)}
    panels = tuple(p.strip().upper() for p in a.panels.split(",") if p.strip())
    made = core.build_shape_keys(arm, meshes, core.load_face_data(a.face_data), categories=panels,
                                 strengths=strengths)
    shots = render_sheet(arm, meshes, [m[0] for m in made], a.out)
    with open(os.path.join(a.out, "morphs.json"), "w", encoding="utf-8") as fh:
        json.dump({"morphs": made, "shots": shots}, fh, ensure_ascii=False, indent=1)
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=a.save, copy=True, compress=False)
    print("FF7_FACE_SHEET=" + json.dumps({"morphs": len(made), "out": a.out}), flush=True)


if __name__ == "__main__":
    main()
