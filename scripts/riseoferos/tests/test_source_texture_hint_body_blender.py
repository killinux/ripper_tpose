"""Verify exact Albedo recovery from the source FBX texture identity hint."""
import importlib.util
import os
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
assert len(args) == 2, "expected <pc_i03_hd.fbx> <i03 texture directory>"
fbx_path, texture_directory = args

spec = importlib.util.spec_from_file_location(
    "roe_source_texture_hint_test", str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.register()

props = bpy.context.scene.roe
props.workflow_mode = "ROE"
props.apply_scope = "LATEST"
props.replace_previous = False
props.fbx_path = fbx_path
props.tex_dir = texture_directory
assert bpy.ops.roe.import_fbx() == {"FINISHED"}

meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
head = module.find_head(meshes)
assert head is not None
head_materials = tuple(slot.material for slot in head.material_slots)
head_indices = tuple(polygon.material_index for polygon in head.data.polygons)
assert bpy.ops.roe.apply_materials(repair_scope="BODY") == {"FINISHED"}

body = bpy.data.objects["pc_i03_hd_body"]
source_names = module.source_material_names(body)
expected = {
    "pc_i03_hd_body": "pc_i03_hd_body02_rgbx_Albedo.png",
    "pc_i03_hd_skin": "pc_i03_hd_body02_rgbx_Albedo.png",
    "pc_i03_hd_body01": "pc_i03_hd_body01_rgbx_Albedo.png",
    "pc_i_nk_face": "pc_i_nk_face_rgbx_Albedo.png",
}
actual = {}
for index, source_name in enumerate(source_names):
    image = module.diffuse_image(body.material_slots[index].material)
    actual[source_name] = os.path.basename(bpy.path.abspath(image.filepath)) \
        if image else ""
assert actual == expected, actual
assert tuple(slot.material for slot in head.material_slots) == head_materials
assert tuple(polygon.material_index for polygon in head.data.polygons) \
    == head_indices

print("ROE_SOURCE_TEXTURE_HINT_BODY_TEST=PASS|mapping=%r" % actual)
