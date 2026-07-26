"""Run with Blender 3.6:

blender --background --factory-startup --python \
    scripts/riseoferos/tests/test_body_texture_variants_blender.py
"""
import importlib.util
import os
from pathlib import Path
import tempfile

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATHS = (
    ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py",
    ROOT / "scripts" / "riseoferos" / "blender_face_materials.py",
)


def load_module(path, suffix):
    spec = importlib.util.spec_from_file_location(
        "roe_body_texture_variant_test_" + suffix, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_test_image(path, color):
    image = bpy.data.images.new(
        "test_" + os.path.basename(path), 2, 2, alpha=True)
    image.pixels = list(color) * 4
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def build_body_fixture(suffix):
    mesh = bpy.data.meshes.new("g07_body_variant_mesh_" + suffix)
    mesh.from_pydata(
        (
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (2.0, 1.0, 0.0),
            (4.0, 0.0, 0.0), (5.0, 0.0, 0.0), (4.0, 1.0, 0.0),
        ),
        [],
        ((0, 1, 2), (3, 4, 5), (6, 7, 8)),
    )
    obj = bpy.data.objects.new("pc_g07_hd_body_" + suffix, mesh)
    bpy.context.collection.objects.link(obj)
    for name in (
            "pc_g07_hd_skin", "pc_g07_hd_body1", "pc_g07_hd_body2"):
        mesh.materials.append(bpy.data.materials.new(name + "_" + suffix))
    for index, polygon in enumerate(mesh.polygons):
        polygon.material_index = index
    obj["roe_source_materials"] = "\n".join((
        "pc_g07_hd_skin",
        "pc_g07_hd_body1",
        "pc_g07_hd_body2",
    ))
    return obj


with tempfile.TemporaryDirectory() as texture_directory:
    body1 = os.path.join(
        texture_directory, "pc_g07_body1_rgbx_Albedo.png")
    body2 = os.path.join(
        texture_directory, "pc_g07_body2_rgbx_Albedo.png")
    save_test_image(body1, (0.8, 0.3, 0.2, 1.0))
    save_test_image(body2, (0.2, 0.3, 0.8, 1.0))

    for index, module_path in enumerate(MODULE_PATHS):
        module = load_module(module_path, str(index))
        body = build_body_fixture(str(index))
        missing = module.apply_mesh_materials(
            body, texture_directory, None, None)
        assert not missing, "%s reported %s" % (module_path.name, missing)

        actual = []
        for slot in body.material_slots:
            images = [
                node.image for node in slot.material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image
            ]
            assert len(images) == 1
            actual.append(os.path.basename(bpy.path.abspath(images[0].filepath)))
        assert actual == [
            "pc_g07_body1_rgbx_Albedo.png",
            "pc_g07_body1_rgbx_Albedo.png",
            "pc_g07_body2_rgbx_Albedo.png",
        ], "%s resolved %s" % (module_path.name, actual)
        bpy.data.objects.remove(body, do_unlink=True)

print("ROE_BODY_TEXTURE_VARIANTS_TEST=PASS")
