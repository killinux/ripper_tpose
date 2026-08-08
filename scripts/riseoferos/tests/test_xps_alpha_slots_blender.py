"""Run with Blender 3.6:

blender --background --factory-startup --python \
    scripts/riseoferos/tests/test_xps_alpha_slots_blender.py
"""
import importlib.util
import os
from pathlib import Path
import tempfile

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py"

spec = importlib.util.spec_from_file_location(
    "roe_xps_alpha_slot_test", str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def alpha_material(name):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.blend_method = "HASHED"
    nodes = material.node_tree.nodes
    texture = nodes.new("ShaderNodeTexImage")
    principled = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    material.node_tree.links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
    return material


def save_test_image(path, color):
    image = bpy.data.images.new(
        "test_" + os.path.basename(path), 2, 2, alpha=True)
    image.pixels = list(color) * 4
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


mesh = bpy.data.meshes.new("g09_body_mesh")
mesh.from_pydata(
    (
        (0, 0, 0), (1, 0, 0), (0, 1, 0),
        (2, 0, 0), (3, 0, 0), (2, 1, 0),
        (4, 0, 0), (5, 0, 0), (4, 1, 0),
        (6, 0, 0), (7, 0, 0), (6, 1, 0),
    ),
    [],
    ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)),
)
body = bpy.data.objects.new("pc_g09_hd_body", mesh)
bpy.context.collection.objects.link(body)

source_names = (
    "pc_g09_hd_body",
    "pc_g09_hd_skin",
    "pc_g09_hd_wings2",
    "pc_g09_hd_wings",
)
body["roe_source_materials"] = "\n".join(source_names)
for name in source_names:
    mesh.materials.append(alpha_material(name))

with tempfile.TemporaryDirectory() as texture_directory:
    for texture_name, color in (
            ("pc_g09_hd_body_rgbx_Albedo.png", (0.8, 0.7, 0.6, 1.0)),
            ("pc_g09_hd_wings_rgbx_Albedo.png", (0.9, 0.9, 0.9, 0.5)),
            ("pc_g09_hd_wings2_rgbx_Albedo.png", (0.7, 0.7, 0.7, 0.5))):
        save_test_image(os.path.join(texture_directory, texture_name), color)

    missing = module.apply_mesh_materials(
        body, texture_directory, None, None)
    assert not missing, missing
    images = []
    for slot in body.material_slots:
        image = module.diffuse_image(slot.material)
        assert image is not None
        images.append(os.path.basename(bpy.path.abspath(image.filepath)))
    assert images == [
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_wings2_rgbx_Albedo.png",
        "pc_g09_hd_wings_rgbx_Albedo.png",
    ], images

    blend_methods = [slot.material.blend_method for slot in body.material_slots]
    assert blend_methods == ["HASHED", "HASHED", "CLIP", "CLIP"], blend_methods

    # Upgrade path for an already-open v1.1.8-or-older scene: reproduce the
    # bad main-wing assignment and HASHED setting, then prepare materials again.
    body.data.materials[3] = body.data.materials[2]
    body.data.materials[2].blend_method = "HASHED"
    missing = module.apply_mesh_materials(
        body, texture_directory, None, None)
    assert not missing, missing
    repaired_images = [
        os.path.basename(bpy.path.abspath(
            module.diffuse_image(slot.material).filepath))
        for slot in body.material_slots
    ]
    assert repaired_images == [
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_wings2_rgbx_Albedo.png",
        "pc_g09_hd_wings_rgbx_Albedo.png",
    ], repaired_images
    repaired_blends = [slot.material.blend_method for slot in body.material_slots]
    assert repaired_blends == [
        "HASHED", "HASHED", "CLIP", "CLIP"], repaired_blends

    # The new three-button workflow must not rebuild neighboring categories.
    wing_materials_before_body_repair = (
        body.material_slots[2].material,
        body.material_slots[3].material,
    )
    body.data.materials[0] = alpha_material("damaged_body_slot")
    body.data.materials[1] = alpha_material("damaged_skin_slot")
    missing = module.apply_mesh_materials(
        body, texture_directory, None, None,
        slot_filter=lambda obj, index, name: not module.is_wing_slot(
            obj, index, name))
    assert not missing, missing
    assert (body.material_slots[2].material,
            body.material_slots[3].material) == wing_materials_before_body_repair

    body_materials_before_wing_repair = (
        body.material_slots[0].material,
        body.material_slots[1].material,
    )
    body.data.materials[2] = alpha_material("damaged_wings2_slot")
    body.data.materials[3] = alpha_material("damaged_wings_slot")
    missing = module.apply_mesh_materials(
        body, texture_directory, None, None,
        slot_filter=module.is_wing_slot)
    assert not missing, missing
    assert (body.material_slots[0].material,
            body.material_slots[1].material) == body_materials_before_wing_repair
    scoped_images = [
        os.path.basename(bpy.path.abspath(
            module.diffuse_image(slot.material).filepath))
        for slot in body.material_slots
    ]
    assert scoped_images == [
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_body_rgbx_Albedo.png",
        "pc_g09_hd_wings2_rgbx_Albedo.png",
        "pc_g09_hd_wings_rgbx_Albedo.png",
    ], scoped_images

    groups = [
        module.roe_xps_render_group(body, index, slot.material)
        for index, slot in enumerate(body.material_slots)
    ]
    assert groups == ["5", "5", "7", "7"], groups

hair_mesh = bpy.data.meshes.new("g09_hair_mesh")
hair = bpy.data.objects.new("pc_g09_hd_hair", hair_mesh)
bpy.context.collection.objects.link(hair)
hair_mesh.materials.append(alpha_material("pc_g_nk_hair"))
assert module.roe_xps_render_group(
    hair, 0, hair.material_slots[0].material) == "7"

# Historical compatibility: an alpha-linked wing slot on another character
# keeps the old ROE body behavior instead of being opted into RG7 globally.
legacy_mesh = bpy.data.meshes.new("legacy_wing_mesh")
legacy = bpy.data.objects.new("pc_a01_hd_body", legacy_mesh)
bpy.context.collection.objects.link(legacy)
legacy["roe_source_materials"] = "pc_a01_hd_wings"
legacy_mesh.materials.append(alpha_material("pc_a01_hd_wings"))
assert module.roe_xps_render_group(
    legacy, 0, legacy.material_slots[0].material) == "5"
assert not module.is_g09_wing_slot(legacy, 0)

# Even a G09 wing remains opaque when the material has no alpha behavior.
opaque_mesh = bpy.data.meshes.new("g09_opaque_wing_mesh")
opaque = bpy.data.objects.new("pc_g09_ld_body", opaque_mesh)
bpy.context.collection.objects.link(opaque)
opaque["roe_source_materials"] = "pc_g09_ld_wings"
opaque_material = bpy.data.materials.new("pc_g09_ld_wings")
opaque_material.use_nodes = True
opaque_mesh.materials.append(opaque_material)
assert module.roe_xps_render_group(
    opaque, 0, opaque.material_slots[0].material) == "5"

print("ROE_XPS_ALPHA_SLOTS_TEST=PASS")
