"""Chest / full dance preview at MMD scale (model + VMD imported at 1.0, gravity 9.81 units/s^2 like MMD).
Baked physics, stills of chosen frames instead of a video.
  blender -b --python dance_mmdscale.py -- <pmx> <vmd> <outdir> <tag> <last frame> <frames,comma,list> [chest|full]"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
pmx, vmd, outdir, tag, last = a[0], a[1], a[2], a[3], int(a[4])
frames = [] if a[5] == "video" else [int(x) for x in a[5].split(",")]
view = a[6] if len(a) > 6 else "chest"
S = 12.5                                   # metres -> MMD units for camera placement
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=1.0, types={"MESH", "ARMATURE", "PHYSICS", "DISPLAY"})
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
root = arm
while root.parent:
    root = root.parent
from mmd_tools.core.model import Model  # noqa: E402

Model(root).build()
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o.type in ("ARMATURE", "MESH", "EMPTY"):
        try:
            o.select_set(True)
        except RuntimeError:
            pass
bpy.context.view_layer.objects.active = root
bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=1.0, margin=30, bone_mapper="PMX", update_scene_settings=True)
sc = bpy.context.scene
sc.frame_end = min(sc.frame_end, last)
w = sc.rigidbody_world
w.enabled = True
w.point_cache.frame_start, w.point_cache.frame_end = sc.frame_start, sc.frame_end
for o in bpy.data.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT") or (o.type == "EMPTY" and o is not root):
        o.hide_render = True
bones = {pb.mmd_bone.name_j or pb.name: pb for pb in arm.pose.bones}
sc.frame_set(sc.frame_start)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 50
cam.data.clip_end = 1000
if view == "chest":
    anchor = bones["上半身3"]
    heads = [arm.matrix_world @ bones[n].head for n in ("Bip001_L_bust_2", "Bip001_R_bust_2") if n in bones]
    target = sum(heads, Vector()) / len(heads) + Vector((0.0, -0.08, -0.02)) * S
    offset = Matrix.Rotation(math.radians(28.0), 3, "Z") @ Vector((0.0, -0.62, 0.06)) * S
    cam.matrix_world = Matrix.Translation(target + offset) @ (-offset).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    world = cam.matrix_world.copy()
    cam.parent, cam.parent_type, cam.parent_bone = arm, "BONE", anchor.name
    cam.matrix_world = world
    sc.render.resolution_x = sc.render.resolution_y = 720
else:
    cam.location = (0.0, -4.2 * S, 0.95 * S)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.render.resolution_x, sc.render.resolution_y = 720, 1080
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w")
sc.world = wd
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.34, 0.34, 0.37, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 1.35
for name, energy, rot in (("key", 3.2, (0.95, 0.0, 0.65)), ("fill", 1.1, (1.15, 0.0, -2.2))):
    lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
    lamp.data.energy = energy
    lamp.rotation_euler = rot
    sc.collection.objects.link(lamp)
cache = w.point_cache
with bpy.context.temp_override(scene=sc, point_cache=cache):
    bpy.ops.ptcache.bake(bake=True)
print("baked %d-%d" % (cache.frame_start, cache.frame_end))
if a[5] == "video":
    bgm = os.environ.get("BGM", "")
    if bgm and os.path.isfile(bgm):
        sc.sequence_editor_create()
        sc.sequence_editor.sequences.new_sound("BGM", bgm, 1, 31)
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    sc.render.ffmpeg.constant_rate_factor = "MEDIUM"
    sc.render.ffmpeg.audio_codec = "AAC"
    sc.render.filepath = os.path.join(outdir, "%s_%s.mp4" % (tag, view))
    bpy.ops.render.render(animation=True)
    print("MMDSCALE DONE")
    raise SystemExit(0)
sc.render.image_settings.file_format = "PNG"
for f in frames:
    sc.frame_set(f)
    sc.render.filepath = os.path.join(outdir, "%s_%s_f%03d.png" % (tag, view, f))
    bpy.ops.render.render(write_still=True)
print("MMDSCALE DONE")
