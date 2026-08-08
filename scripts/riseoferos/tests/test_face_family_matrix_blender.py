"""Blender 3.6 integration test for ROE face-resource family variants.

Arguments::

    <fbx> <texture-dir> <face-image> <eye-image> <slot-counts-json>
    <stroke-mode> [brow-image]

``stroke-mode`` is ``transparent`` for families whose strokes are baked into
the face Albedo, otherwise ``textured``.
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
assert len(args) in {6, 7}, (
    "expected <fbx> <texture-dir> <face-image> <eye-image> "
    "<slot-counts-json> <transparent|textured> [brow-image]")
fbx_path, texture_directory, expected_face, expected_eye, counts_spec, mode = \
    args[:6]
expected_brow = args[6] if len(args) == 7 else ""
expected_counts = {
    int(part.split(":", 1)[0]): int(part.split(":", 1)[1])
    for part in counts_spec.split(",")
}

spec = importlib.util.spec_from_file_location(
    "roe_face_family_matrix_test", str(MODULE_PATH))
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
assert dict(counts) == expected_counts, counts

def image_name(slot_index):
    image = module.diffuse_image(head.material_slots[slot_index].material)
    return os.path.basename(bpy.path.abspath(image.filepath)) if image else ""


assert image_name(0) == expected_face
assert image_name(1) == expected_eye
if mode == "transparent":
    assert module.material_is_transparent_only(head.material_slots[2].material)
    assert module.material_is_transparent_only(head.material_slots[3].material)
else:
    assert mode == "textured"
    assert image_name(2) == expected_brow
    assert image_name(3) == expected_brow

assert non_head_materials == {
    obj.name: tuple(slot.material for slot in obj.material_slots)
    for obj in meshes if obj is not head
}
assert non_head_indices == {
    obj.name: tuple(polygon.material_index for polygon in obj.data.polygons)
    for obj in meshes if obj is not head
}

print("ROE_FACE_FAMILY_MATRIX_TEST=PASS|head=%s|counts=%r|face=%s|eye=%s" % (
    head.name, dict(counts), expected_face, expected_eye))
