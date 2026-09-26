"""Import a PMX (0.08) and drive a few morphs through mmd_tools' morph slider (the path a VMD takes), render the face.
  blender -b --python pmx_morph_check.py -- <file.pmx> <outdir>"""
import math
import os
import sys

import bpy
from mathutils import Vector

pmx, out = sys.argv[sys.argv.index("--") + 1:][:2]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=pmx, scale=0.08, types={"MESH", "ARMATURE", "MORPHS", "DISPLAY"})
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
root = arm
while root.parent:
    root = root.parent
mmd = root.mmd_root
print("PMX morphs: bone %d, vertex %d, material %d, group %d; facial frame items %d" % (
    len(mmd.bone_morphs), len(mmd.vertex_morphs), len(mmd.material_morphs), len(mmd.group_morphs),
    len(mmd.display_item_frames["表情"].data) if "表情" in mmd.display_item_frames else -1))
from mmd_tools.core.model import Model  # noqa: E402

rig = Model(root)
rig.morph_slider.create()
rig.morph_slider.bind()
slider = rig.morph_slider.placeholder()
keys = slider.data.shape_keys.key_blocks
sc = bpy.context.scene
byj = {pb.mmd_bone.name_j: pb for pb in arm.pose.bones}
eyes = (byj["左目"].head + byj["右目"].head) / 2
target = arm.matrix_world @ eyes + Vector((0, 0, -0.035))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 85
cam.location = target + Vector((0, -1, 0.05)).normalized() * 0.62
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 12
sc.render.resolution_x = sc.render.resolution_y = 360
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.52, 1)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sc.collection.objects.link(sun)
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(60), 0, math.radians(-25))
for i, name in enumerate(("", "まばたき", "ウィンク", "あ", "い", "う", "お", "にやり", "困る", "怒り")):
    for k in keys:
        k.value = 0.0
    if name:
        keys[name].value = 1.0
    bpy.context.view_layer.update()
    sc.frame_set(sc.frame_current)
    sc.render.filepath = os.path.join(out, "%02d.png" % i)
    bpy.ops.render.render(write_still=True)
print("PMX MORPH CHECK DONE")
