"""Vindictus .blend (build_blend.py / package_blend.py output) -> XPS (XNALara) with blender2xps, headless.

    blender -b <look>.blend --factory-startup --python export_xps_blender.py -- --out <dir> [--name N]

Writes <out>/<name>.xps + its textures (+ blender2xps report).  Only what the .blend shows goes in (the hidden
"_未使用的默认部件" collection - default parts the look replaces - stays out).  The skeleton is renamed to 3ds Max
Biped names first (rig.py), which blender2xps maps onto the XPS standard names, so XPS poses apply.  Units are
already metres (1 game unit = 1 inch, scaled in the build; a heroine is 1.84 m).  Dye masks and other node-computed
colours are baked by blender2xps into one *_baked.png per material; the game's normal maps are DirectX (Y down),
the convention XPS uses, and go in unchanged.

Prints VINDICTUS_XPS={json}.
"""
import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
B2X = os.environ.get('BLENDER2XPS', r'E:\code\othercode\blender2xps')
if B2X not in sys.path:
    sys.path.insert(0, B2X)
from blender2xps import export_xps  # noqa: E402
import rig  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(flag, default=''):
    return argv[argv.index(flag) + 1] if flag in argv else default


out_dir = arg('--out')
if not out_dir:
    raise SystemExit('usage: blender -b X.blend --python export_xps_blender.py -- --out <dir> [--name N]')
name = arg('--name') or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {'name': name, 'blend': bpy.data.filepath, 'ok': False}
scene = bpy.context.scene
hidden = [o for o in scene.objects if o.type == 'MESH' and (o.hide_render or o.hide_get())]
summary['left_out'] = [o.name for o in hidden]
for o in hidden:
    bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
meshes = [o for o in scene.objects if o.type == 'MESH']
summary['rig'] = rig.to_biped(arm, meshes)
summary['full_sclera'] = rig.full_sclera()
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + '.xps'), fmt='AUTO', scope='VISIBLE',
                               scale=1.0, bake_mode='AUTO', bone_naming='XPS', max_weights=4, auto_facing=True)
res = export_xps.export_model(bpy.context, settings)
summary.update({'ok': not res.errors, 'path': res.path, 'fmt': res.fmt, 'bones': res.bone_count,
                'meshes': res.mesh_count, 'stats': res.stats, 'warnings': res.warnings, 'errors': res.errors,
                'seconds': round(time.time() - t0, 1)})
print('VINDICTUS_XPS=' + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
