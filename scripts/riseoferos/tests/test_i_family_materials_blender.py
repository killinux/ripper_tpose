"""Run an i-family integration case with Blender 3.6.

Example for i03 (run again with i04 and its expected values)::

    blender --background --factory-startup --python \
        scripts/riseoferos/tests/test_i_family_materials_blender.py -- \
        <pc_i03_hd.fbx> <i03/_textures> \
        pc_i_nk_face_rgbx_Albedo.png 11616

i04 expects ``pc_i04_hd_face_rgbx_Albedo.png`` and ``12172`` face polygons.
"""
import collections
import importlib.util
import os
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
assert len(args) == 4, (
    "expected <i-family FBX> <texture directory> "
    "<expected face image name> <expected face polygon count>")
fbx_path, texture_directory, expected_face_image, expected_face_count = args
expected_face_count = int(expected_face_count)

spec = importlib.util.spec_from_file_location(
    "roe_i_family_material_test", str(MODULE_PATH))
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
non_head_materials = {
    obj.name: tuple(slot.material for slot in obj.material_slots)
    for obj in meshes if obj is not head
}
non_head_indices = {
    obj.name: tuple(polygon.material_index for polygon in obj.data.polygons)
    for obj in meshes if obj is not head
}

assert bpy.ops.roe.apply_materials(repair_scope="FACE") == {"FINISHED"}
counts = collections.Counter(
    polygon.material_index for polygon in head.data.polygons)
assert dict(counts) == {
    0: expected_face_count,
    1: 864,
    2: 636,
    4: 3284,
}, counts

face_image = module.diffuse_image(head.material_slots[0].material)
eye_image = module.diffuse_image(head.material_slots[1].material)
assert os.path.basename(bpy.path.abspath(face_image.filepath)) \
    == expected_face_image
assert os.path.basename(bpy.path.abspath(eye_image.filepath)) \
    == "pc_i_ld_eyes_rgbx_Albedo.png"
assert module.material_is_transparent_only(head.material_slots[2].material)
assert module.material_is_transparent_only(head.material_slots[3].material)
assert non_head_materials == {
    obj.name: tuple(slot.material for slot in obj.material_slots)
    for obj in meshes if obj is not head
}
assert non_head_indices == {
    obj.name: tuple(polygon.material_index for polygon in obj.data.polygons)
    for obj in meshes if obj is not head
}

print("ROE_I_FAMILY_MATERIAL_TEST=PASS|head=%s|counts=%r|face=%s" % (
    head.name, dict(counts), expected_face_image))
