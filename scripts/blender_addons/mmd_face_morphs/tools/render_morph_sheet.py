"""Render every bone morph of an mmd_tools model as a face close-up (Blender
side; ``make_sheet.py`` then labels and tiles the PNGs).

    blender --background --python render_morph_sheet.py -- <model.pmx|model.blend> <out_dir>
            [--setup] [--size 480 560] [--lens 90] [--only name,...] [--hide regex]

``--setup`` runs the add-on first (rebuilding same-named morphs), so a PMX
that already carries an older expression set is rendered with the new one.
``--hide`` hides every mesh whose name or material matches the regex - use it
for a fringe that covers the eyebrows, which otherwise cannot be judged.
A ``.pmx`` is imported at 0.08 (metres); a ``.blend`` is opened as is.
Writes ``NN.png`` per morph plus ``00.png`` (neutral) and ``index.json``.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

SCALE = 0.08


def option(argv, flag, count, default):
    if flag not in argv:
        return default
    i = argv.index(flag)
    values = argv[i + 1:i + 1 + count]
    if len(values) != count or any(v.startswith("--") for v in values):
        raise SystemExit("%s needs %d value(s)" % (flag, count))
    return values


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out_dir = argv[0], argv[1]
    width, height = (int(v) for v in option(argv, "--size", 2, ("480", "560")))
    lens = float(option(argv, "--lens", 1, ("90",))[0])
    only = option(argv, "--only", 1, (None,))[0]
    only = set(only.split(",")) if only else None
    hide = option(argv, "--hide", 1, (None,))[0]
    os.makedirs(out_dir, exist_ok=True)

    if src.lower().endswith(".pmx"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.preferences.addon_enable(module="mmd_tools")
        bpy.ops.mmd_tools.import_model(filepath=src, scale=SCALE,
                                       types={"MESH", "ARMATURE", "MORPHS"})
    else:
        bpy.ops.wm.open_mainfile(filepath=src, load_ui=False)
    sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
    from mmd_face_morphs import api, build, faces

    # through mmd_tools, not "the first armature": a .blend touched by the
    # morph slider also holds its ".dummy_armature", which sorts first
    candidates = [o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT"] or list(bpy.data.objects)
    root, arm = build.model_of(candidates[0])

    if "--setup" in argv:
        api.setup(root, log=lambda line: print("setup: " + line))
    face = faces.resolve(arm)
    print("face: " + face.describe())

    if hide:
        import re as _re
        pattern = _re.compile(hide, _re.I)
        for obj in bpy.data.objects:
            if obj.type != "MESH" or obj.find_armature() != arm:
                continue
            materials = [slot.material.name for slot in obj.material_slots if slot.material]
            # whole-object only when nothing of it would survive; a PMX import
            # is usually ONE merged mesh carrying every material, so matching a
            # single material there must mask faces, not hide the head
            if pattern.search(obj.name) or (materials and all(pattern.search(n) for n in materials)):
                obj.hide_render = True
                print("hidden mesh %s" % obj.name)
                continue
            drop = {i for i, slot in enumerate(obj.material_slots)
                    if slot.material and pattern.search(slot.material.name)}
            if not drop:
                continue
            keep = set()
            hidden = 0
            for polygon in obj.data.polygons:
                if polygon.material_index in drop:
                    hidden += 1
                else:
                    keep.update(polygon.vertices)
            group = obj.vertex_groups.new(name="mfm_keep")
            group.add(sorted(keep), 1.0, "REPLACE")
            modifier = obj.modifiers.new("mfm_hide", "MASK")
            modifier.vertex_group = group.name
            print("masked %d of %d faces on %s (%s)"
                  % (hidden, len(obj.data.polygons), obj.name,
                     ", ".join(obj.material_slots[i].material.name for i in sorted(drop))))

    # -- camera on the face ---------------------------------------------------
    bones = arm.data.bones
    if face.has("eye_L", "eye_R"):
        eyes = (bones[face.bone("eye_L")].head_local + bones[face.bone("eye_R")].head_local) * 0.5
    elif face.head:
        eyes = bones[face.head].head_local + Vector((0.0, 0.0, face.unit * 0.8))
    else:
        eyes = Vector((0.0, 0.0, 1.5))
    target = arm.matrix_world @ (eyes + Vector((0.0, 0.0, -0.55 * face.unit)))
    distance = 9.5 * face.unit * arm.matrix_world.to_scale().y
    forward = Vector((0.0, face.front, 0.0))
    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new("face_cam")
    camera_data.lens = lens
    camera = bpy.data.objects.new("face_cam", camera_data)
    scene.collection.objects.link(camera)
    camera.location = target + forward * distance
    camera.rotation_euler = (math.radians(90), 0.0, 0.0 if face.front < 0 else math.pi)
    scene.camera = camera

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = 16
    world = bpy.data.worlds.new("face_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.36, 0.36, 0.39, 1.0)
    background.inputs[1].default_value = 1.3
    scene.world = world
    flip = 0.0 if face.front < 0 else math.pi
    for name, energy, rotation in (("key", 3.0, (0.95, 0.0, 0.65 + flip)),
                                   ("fill", 1.4, (1.2, 0.0, -0.6 + flip))):
        data = bpy.data.lights.new(name, type="SUN")
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation
    scene.render.image_settings.file_format = "PNG"

    # -- one still per morph ---------------------------------------------------
    index = []

    def shoot(number, name, name_e, category):
        path = os.path.join(out_dir, "%02d.png" % number)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        index.append({"file": os.path.basename(path), "name": name, "name_e": name_e,
                      "category": category})
        print("rendered %02d %s" % (number, name))

    build.reset_pose(root, arm)
    shoot(0, "neutral", "neutral", "")
    number = 1
    for morph in root.mmd_root.bone_morphs:
        if only and morph.name not in only:
            continue
        build.pose_morph(root, arm, morph.name, 1.0)
        shoot(number, morph.name, morph.name_e, morph.category)
        number += 1
    build.reset_pose(root, arm)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as handle:
        json.dump({"source": src, "face": face.describe(), "tiles": index}, handle,
                  ensure_ascii=False, indent=1)
    print("FACE_SHEET_DONE %d tiles -> %s" % (len(index), out_dir))


if __name__ == "__main__":
    main()
