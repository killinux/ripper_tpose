"""Same-camera renders of a built Vindictus look for texture comparisons: face, eyes, outfit (chest), full body.
    blender -b <look>.blend --factory-startup --python compare_views_blender.py -- <out_prefix>
Writes <out_prefix>_face.png (1400x1400), _eyes.png (1600x800), _outfit.png (1200x1500), _body.png (1000x1500)."""
import sys

import bpy
from mathutils import Vector

prefix = sys.argv[sys.argv.index('--') + 1:][0]
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
# build_blend.py's texture-alpha rule (10-31) for looks built before it: their images are STRAIGHT and EEVEE multiplied
# the face texture's mask alpha into its colour (darker eye creases, lip line, nostrils), so a game-size look built
# then and its HD copy built now would differ by more than their textures
see_through = {n.image.name for m in bpy.data.materials if m.use_nodes and m.blend_method != 'OPAQUE'
               for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
for im in bpy.data.images:
    if im.source == 'FILE' and im.name not in see_through and im.alpha_mode == 'STRAIGHT':
        im.alpha_mode = 'CHANNEL_PACKED'


def bone(n):
    pb = arm.pose.bones.get(n)
    return arm.matrix_world @ pb.head


eyes = [o for o in scene.objects if o.type == 'MESH' and 'eyeball' in o.name.lower() and not o.hide_render]
pts = [o.matrix_world @ v.co for o in eyes for v in o.data.vertices]
eye_c = sum(pts, Vector()) / len(pts)
hats = [o for o in scene.objects if o.type == 'MESH' and o.name.startswith('outfit_head') and not o.hide_render]
vis = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for o in vis:
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        lo, hi = Vector(map(min, lo, w)), Vector(map(max, hi, w))
cam = scene.camera
scene.render.resolution_percentage = 100


def shot(name, target, offset, lens, res, hide=()):
    for o in hide:
        o.hide_render = True
    cam.data.lens = lens
    cam.location = target + offset
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = '%s_%s.png' % (prefix, name)
    bpy.ops.render.render(write_still=True)
    for o in hide:
        o.hide_render = False
    print('rendered', scene.render.filepath, flush=True)


shot('face', eye_c + Vector((0, 0, -0.025)), Vector((0.0, -0.42, 0.0)), 85, (1400, 1400), hats)
shot('eyes', eye_c, Vector((0.0, -0.55, 0.0)), 200, (1600, 800), hats)
shot('outfit', bone('ValveBiped.Bip01_Spine2'), Vector((-0.3, -1.05, 0.06)), 85, (1200, 1500))
ctr, h = (lo + hi) / 2, (hi - lo).z
shot('body', ctr, Vector((0, -1, 0.05)).normalized() * h * 2.35, 70, (1000, 1500))
