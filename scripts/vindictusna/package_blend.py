"""Make a built .blend standalone and comfortable to open:  -- <in.blend> <out_dir> <name> <note.txt> [<face_hide>]
textures copied to <out_dir>/textures (relative paths), viewport = material preview with scene lights,
unused default parts moved into a hidden collection, a 说明 text block, previews rendered next to the file.
face_hide = comma-separated name parts hidden only for the face preview (e.g. a hat that shades the face)."""
import bpy, sys, os, shutil, math
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
src, out_dir, name, note = argv[0], argv[1], argv[2], argv[3]
face_hide = [s for s in (argv[4].split(',') if len(argv) > 4 else []) if s]
bpy.ops.wm.open_mainfile(filepath=src)
os.makedirs(os.path.join(out_dir, 'textures'), exist_ok=True)
scene = bpy.context.scene

# unused default parts -> hidden collection
hid = bpy.data.collections.get('_未使用的默认部件') or bpy.data.collections.new('_未使用的默认部件')
if hid.name not in scene.collection.children:
    scene.collection.children.link(hid)
for ob in list(scene.objects):
    if ob.type == 'MESH' and ob.hide_render:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        hid.objects.link(ob)
hid.hide_render = True
hid.hide_viewport = True

# textures next to the file
for im in bpy.data.images:
    if im.source != 'FILE' or not im.filepath:
        continue
    p = bpy.path.abspath(im.filepath)
    if os.path.exists(p):
        dst = os.path.join(out_dir, 'textures', os.path.basename(p))
        if not os.path.exists(dst):
            shutil.copy2(p, dst)
        im.filepath = dst

# note
t = bpy.data.texts.get('说明') or bpy.data.texts.new('说明')
t.from_string(open(note, encoding='utf-8').read())

# viewport: material preview with the scene lights/world, look through the camera
for scr in bpy.data.screens:
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = 'MATERIAL'
                    sp.shading.use_scene_lights = True
                    sp.shading.use_scene_world = True
                    sp.region_3d.view_perspective = 'CAMERA'
                    sp.overlay.show_bones = False
        if area.type == 'TEXT_EDITOR':
            for sp in area.spaces:
                if sp.type == 'TEXT_EDITOR':
                    sp.text = t

# camera: full body front
vis = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in vis:
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
ctr = (lo + hi) / 2; h = (hi - lo).z
cam = scene.camera
cam.data.lens = 70
scene.render.resolution_x, scene.render.resolution_y = 1000, 1500
views = {'front': (0, -1, 0.05), '34': (-0.65, -0.85, 0.08), 'side': (-1, 0, 0.05), 'back': (0, 1, 0.05)}
for vn, d in views.items():
    v = Vector(d).normalized()
    cam.location = ctr + v * h * 2.35
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(out_dir, '%s_%s.png' % (name, vn))
    bpy.ops.render.render(write_still=True)
arm = [o for o in scene.objects if o.type == 'ARMATURE'][0]
hb = arm.pose.bones.get('ValveBiped.Bip01_Head1')
if hb:
    hp = arm.matrix_world @ hb.head + Vector((0, 0, 0.07))
    cam.data.lens = 85
    cam.location = hp + Vector((0.12, -0.8, 0.02))
    cam.rotation_euler = (hp - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.resolution_x, scene.render.resolution_y = 1000, 1000
    scene.render.filepath = os.path.join(out_dir, '%s_face.png' % name)
    fh = [o for o in vis if any(s in o.name for s in face_hide)]
    for o in fh:
        o.hide_render = True
    bpy.ops.render.render(write_still=True)
    for o in fh:
        o.hide_render = False
# leave the camera on the full-body front view
v = Vector(views['front']).normalized()
cam.data.lens = 70
cam.location = ctr + v * h * 2.35
cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.resolution_x, scene.render.resolution_y = 1000, 1500
out = os.path.join(out_dir, name + '.blend')
bpy.context.preferences.filepaths.save_version = 0      # no .blend1 next to the delivered file
bpy.ops.wm.save_as_mainfile(filepath=out, relative_remap=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print('saved', out, 'images', len(bpy.data.images))
