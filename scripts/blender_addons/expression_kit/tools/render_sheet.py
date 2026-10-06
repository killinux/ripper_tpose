"""Render the face once per expression this add-on made (bone morphs posed, shape keys at 1.0).

  blender -b <model.blend> --python render_sheet.py -- <outdir> [--set MMD|ARKIT|ALL] [--view front|side]
          [--pmx <file.pmx>] [--hide <regex of materials to mask, e.g. hair>] [--size 360]

Writes <outdir>/NNN_<name>.png and index.json; tools/make_sheet.py pastes them into one labelled image.
The camera is orthographic, framed on the vertices the expressions move and placed along their mean
normal - the way the face looks, whatever axis the rig faces (--flip turns it round)."""
import json
import math
import os
import re
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
addon_utils.enable("mmd_tools", default_set=False)
from expression_kit import api, engine  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(argv[0])


def opt(flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


which, view = opt("--set", "ALL"), opt("--view", "front")
size, hide = int(opt("--size", "360")), opt("--hide", "")
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
if opt("--pmx"):
    bpy.ops.mmd_tools.import_model(filepath=opt("--pmx"), scale=0.08)
arm = next(o for o in sc.objects if o.type == "ARMATURE" and not o.name.startswith("."))
arm, meshes, root = api.model(arm)
made = api.made(arm)
names = []
for kind in ("BONE", "MMD", "ARKIT"):
    if which in ("ALL", kind) or (which == "MMD" and kind == "BONE"):
        names += [(n, kind) for n in made[kind] if n not in [x[0] for x in names]]
if sc.rigidbody_world:
    sc.rigidbody_world.enabled = False
for o in sc.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT", "TEMPORARY") or (o.type == "EMPTY" and o is not root):
        o.hide_render = True

# frame: the vertices any made expression moves
pts, normals = [], []
bones = set()
if root is not None:
    for m in root.mmd_root.bone_morphs:
        if m.name in made["BONE"]:
            bones.update(it.bone for it in m.data)
for m in meshes:
    mine = set(engine.made_keys([m]))
    moving = np.zeros(len(m.data.vertices), dtype=bool)
    if m.data.shape_keys and mine:
        base = np.empty(len(m.data.vertices) * 3)
        m.data.shape_keys.reference_key.data.foreach_get("co", base)
        for kb in m.data.shape_keys.key_blocks:
            if kb.name in mine:
                co = np.empty(len(base))
                kb.data.foreach_get("co", co)
                moving |= np.abs(co - base).reshape(-1, 3).max(1) > 1e-6
    if bones:
        idx = {g.index for g in m.vertex_groups if g.name in bones}
        for v in m.data.vertices:
            if any(g.group in idx and g.weight > 0.05 for g in v.groups):
                moving[v.index] = True
    normal_matrix = m.matrix_world.to_3x3().inverted().transposed()
    for i in np.nonzero(moving)[0][::7]:
        v = m.data.vertices[int(i)]
        pts.append(m.matrix_world @ v.co)
        normals.append((normal_matrix @ v.normal).normalized())
if not pts:
    raise SystemExit("nothing made by expression_kit in this file")
forward = sum(normals, Vector()).normalized()          # a face's vertex normals point out of the face
forward.z = 0.0
forward = (forward.normalized() if forward.length > 1e-6 else Vector((0.0, -1.0, 0.0))) * (-1 if "--flip" in argv else 1)
up = Vector((0.0, 0.0, 1.0))
right = forward.cross(up).normalized()
along = [(p.dot(right), p.z) for p in pts]
centre = sum(pts, Vector()) / len(pts)
width = max(a for a, _z in along) - min(a for a, _z in along)
height = max(z for _a, z in along) - min(z for _a, z in along)
centre = right * ((max(a for a, _z in along) + min(a for a, _z in along)) / 2 - centre.dot(right)) + centre
centre.z = (max(z for _a, z in along) + min(z for _a, z in along)) / 2
cam = bpy.data.objects.new("ek_cam", bpy.data.cameras.new("ek_cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(width, height) * 1.45
direction = forward if view == "front" else (forward + right * 0.9).normalized()
cam.location = centre + direction * max(width, height, 0.1) * 6
cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.clip_end = 1000
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.render.resolution_x = sc.render.resolution_y = size
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.view_settings.exposure, sc.view_settings.gamma = 0.0, 1.0
sc.render.film_transparent = False
world = bpy.data.worlds.new("ek_world")
sc.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")     # names follow the UI language
bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1.0)
sun = bpy.data.objects.new("ek_sun", bpy.data.lights.new("ek_sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(60), 0.0, math.radians(-25))
if hide:
    pattern = re.compile(hide, re.I)
    for m in meshes:
        slots = [i for i, s in enumerate(m.material_slots) if s.material and pattern.search(s.material.name)]
        if slots and len(slots) < len(m.material_slots):
            name = "ek_hide"
            vg = m.vertex_groups.get(name) or m.vertex_groups.new(name=name)
            verts = {v for p in m.data.polygons if p.material_index in slots for v in p.vertices}
            vg.add(sorted(verts), 1.0, "REPLACE")
            mod = m.modifiers.new(name, "MASK")
            mod.vertex_group, mod.invert_vertex_group = name, True
        elif slots:
            m.hide_render = True

index = []


def shoot(i, name, kind):
    path = os.path.join(out, "%03d_%s.png" % (i, re.sub(r"[^\w\-]", "x", name)))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    index.append({"file": os.path.basename(path), "name": name, "kind": kind})


api.reset(arm)
shoot(0, "neutral", "")
for i, (name, kind) in enumerate(names, 1):
    api.preview(arm, name, 1.0)
    bpy.context.view_layer.update()
    shoot(i, name, kind)
api.reset(arm)
with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
    json.dump(index, fh, ensure_ascii=False, indent=1)
print("SHEET_DONE %d" % len(index))
