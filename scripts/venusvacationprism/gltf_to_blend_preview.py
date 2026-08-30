"""Import a converted G1M glTF, save a .blend and render preview views.

Runs headless inside Blender 3.6:
  blender --background --python gltf_to_blend_preview.py -- <in.gltf> <out.blend>

Writes <out>.blend plus <out>_front.png / <out>_back.png and prints a
PRISM_MODEL_PREVIEW= JSON marker with mesh/bone statistics.
"""

import json
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
gltf_path, blend_path = argv

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=gltf_path)

meshes = [obj for obj in scene.objects if obj.type == "MESH"]
armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
if not meshes:
    raise SystemExit("glTF contained no meshes: " + gltf_path)

points = [obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]
minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
center = (minimum + maximum) * 0.5
extent = maximum - minimum
size = max(extent.x, extent.y, extent.z, 0.01)

camera_data = bpy.data.cameras.new("PreviewCam")
camera_data.type = "ORTHO"
camera_data.ortho_scale = size * 1.15
camera = bpy.data.objects.new("PreviewCam", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "SINGLE"
scene.display.shading.show_cavity = True
scene.render.resolution_x = 540
scene.render.resolution_y = 810
scene.render.image_settings.file_format = "PNG"

root = os.path.splitext(blend_path)[0]
renders = {}
for name, offset in (
    ("front", Vector((0.0, -size * 3.0, 0.0))),
    ("back", Vector((0.0, size * 3.0, 0.0))),
):
    camera.location = center + offset
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = root + "_" + name + ".png"
    bpy.ops.render.render(write_still=True)
    renders[name] = scene.render.filepath

os.makedirs(os.path.dirname(blend_path), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

report = {
    "blend": blend_path,
    "renders": renders,
    "meshes": len(meshes),
    "vertices": sum(len(obj.data.vertices) for obj in meshes),
    "polygons": sum(len(obj.data.polygons) for obj in meshes),
    "bones": sum(len(obj.data.bones) for obj in armatures),
    "height": round(extent.z, 2),
}
print("PRISM_MODEL_PREVIEW=" + json.dumps(report, ensure_ascii=False))
