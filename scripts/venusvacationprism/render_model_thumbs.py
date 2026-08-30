"""Render front-view thumbnails for converted G1M glTFs (Blender 3.6, headless).

  blender --background --python render_model_thumbs.py -- <jobs.json>

jobs.json: [{"gltf": "...", "png": "..."}, ...]; existing PNGs are skipped.
Prints PRISM_THUMBS= JSON with per-item status when done.
"""

import json
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
(jobs_path,) = argv
# utf-8-sig: PowerShell 5.1 Out-File -Encoding utf8 writes a BOM.
with open(jobs_path, "r", encoding="utf-8-sig") as handle:
    jobs = json.load(handle)

results = []
for job in jobs:
    source_path = job.get("source") or job["gltf"]
    png_path = job["png"]
    if os.path.isfile(png_path):
        results.append({"png": png_path, "status": "cached"})
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    try:
        if source_path.lower().endswith(".fbx"):
            bpy.ops.import_scene.fbx(filepath=source_path)
        else:
            bpy.ops.import_scene.gltf(filepath=source_path)
    except Exception as error:  # noqa: BLE001 - record and continue the batch
        results.append(
            {"png": png_path, "status": "import-failed", "error": str(error)[:300]}
        )
        continue
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        results.append({"png": png_path, "status": "no-meshes"})
        continue
    points = [obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    # ortho_scale maps to the larger render dimension (450px portrait
    # height); frame the full body height with margin, and widths too
    # (visible width = 2/3 of ortho_scale at 300x450).
    size = max(extent.z * 0.95, extent.x * 1.35, 0.01)

    camera_data = bpy.data.cameras.new("Cam")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = size * 1.15
    camera = bpy.data.objects.new("Cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.location = center + Vector((0.0, -size * 3.0, 0.0))
    camera.rotation_euler = (
        (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 300
    scene.render.resolution_y = 450
    scene.render.image_settings.file_format = "PNG"
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    scene.render.filepath = png_path
    bpy.ops.render.render(write_still=True)
    results.append({"png": png_path, "status": "rendered"})

print("PRISM_THUMBS=" + json.dumps(results, ensure_ascii=False))
