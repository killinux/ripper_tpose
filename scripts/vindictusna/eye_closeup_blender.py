"""Close-up renders of a built Vindictus .blend's eyes (both eyes, front + 3/4), for checking the eye material.

    blender -b <look>.blend --factory-startup --python eye_closeup_blender.py -- <out_prefix> [lens_mm]
Writes <out_prefix>_eyes_front.png and <out_prefix>_eyes_34.png (1200 x 600).
"""
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
prefix = argv[0]
lens = float(argv[1]) if len(argv) > 1 else 200.0
scene = bpy.context.scene
eyes = [o for o in scene.objects if o.type == 'MESH' and 'eyeball' in o.name.lower() and not o.hide_render]
if not eyes:
    raise SystemExit('no eyeball objects')
pts = [o.matrix_world @ v.co for o in eyes for v in o.data.vertices]
ctr = sum(pts, Vector()) / len(pts)
for o in scene.objects:                       # hats / helmets in front of the face
    if o.type == 'MESH' and o.name.startswith('outfit_head'):
        o.hide_render = True
cam = scene.camera
cam.data.lens = lens
scene.render.resolution_x, scene.render.resolution_y = 1200, 600
for name, off in (('front', Vector((0.0, -0.55, 0.0))), ('34', Vector((-0.32, -0.45, 0.0)))):
    cam.location = ctr + off
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = '%s_eyes_%s.png' % (prefix, name)
    bpy.ops.render.render(write_still=True)
    print('rendered', scene.render.filepath)
