"""Render the face with each MMD expression of a converted PMX scene (export_pmx_blender.py's <look>_converted.blend):
one close-up per morph, for checking.

    blender -b <look>_converted.blend --factory-startup --python morph_sheet_blender.py -- <out_dir> [morph ...]
Writes <out_dir>/morph_<n>_<name>.png (shape keys of that name on every mesh at 1.0).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
out_dir = argv[0]
names = argv[1:] or ['まばたき', 'ウィンク', 'ウィンク右', 'あ', 'にっこり', '怒り', '困る', 'びっくり']
os.makedirs(out_dir, exist_ok=True)
scene = bpy.context.scene
meshes = [o for o in scene.objects if o.type == 'MESH' and o.data.shape_keys]
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
head = next((b for b in arm.data.bones if b.name in ('頭', 'Bip001 Head', 'head')), None)
hp = arm.matrix_world @ head.head_local + Vector((0, 0, 0.07))
cam = bpy.data.objects.new('mcam', bpy.data.cameras.new('mcam'))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 85
cam.location = hp + Vector((0.0, -0.62, 0.02))
cam.rotation_euler = (hp - cam.location).to_track_quat('-Z', 'Y').to_euler()
for nm, rot, en in (('k', (55, 0, 30), 3.0), ('f', (70, 0, -130), 1.0)):
    L = bpy.data.objects.new(nm, bpy.data.lights.new(nm, 'SUN'))
    scene.collection.objects.link(L)
    L.data.energy = en
    L.rotation_euler = tuple(math.radians(a) for a in rot)
if scene.world is None:
    scene.world = bpy.data.worlds.new('w')
scene.world.color = (0.05, 0.05, 0.06)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 600
scene.view_settings.view_transform = 'Filmic'
for o in scene.objects:                           # rigid bodies / joints are meshes too
    if getattr(o, 'mmd_type', 'NONE') not in ('NONE', '') or o.name.startswith(('rigid', 'joint')):
        o.hide_render = True


def set_all(name, v):
    for o in meshes:
        kb = o.data.shape_keys.key_blocks.get(name)
        if kb is not None:
            kb.value = v


for i, name in enumerate(['(neutral)'] + names):
    set_all(name, 1.0)
    scene.render.filepath = os.path.join(out_dir, 'morph_%02d.png' % i)
    bpy.ops.render.render(write_still=True)
    set_all(name, 0.0)
    print('rendered', i, name)
