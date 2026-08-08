"""Run with Blender 3.6:

Unit coverage:
    blender --background --factory-startup --python \
        scripts/riseoferos/tests/test_fbx_missing_bind_compat_blender.py

Optional E06 integration coverage:
    blender --background --factory-startup --python \
        scripts/riseoferos/tests/test_fbx_missing_bind_compat_blender.py -- \
        <pc_e06_hd.fbx> <_textures directory>
"""
import importlib.util
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py"

spec = importlib.util.spec_from_file_location(
    "roe_fbx_missing_bind_compat_test", str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeMeshNode:
    def __init__(self, name, world_matrix):
        self.fbx_name = name
        self.armature_setup = {}
        self._world_matrix = world_matrix

    def get_world_matrix(self):
        return self._world_matrix


class FakeArmatureNode:
    is_armature = True

    def __init__(self, name, meshes, bind_matrix):
        self.fbx_name = name
        self.meshes = set(meshes)
        self.bind_matrix = bind_matrix


# Core regression: add only the missing setup and preserve valid importer data.
missing_world = object()
armature_bind = object()
missing = FakeMeshNode("wp_e_06", missing_world)
existing = FakeMeshNode("pc_e06_hd_body", object())
armature = FakeArmatureNode("Root", (missing, existing), armature_bind)
existing_setup = (object(), object())
existing.armature_setup[armature] = existing_setup
fallbacks = []

module.fill_missing_fbx_bind_setups(armature, fallbacks)

assert missing.armature_setup[armature] == (missing_world, armature_bind)
assert existing.armature_setup[armature] is existing_setup
assert fallbacks == [("Root", "wp_e_06")]

# Idempotence: recursive/duplicate collector visits must not overwrite or report.
module.fill_missing_fbx_bind_setups(armature, fallbacks)
assert fallbacks == [("Root", "wp_e_06")]


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if args:
    assert len(args) == 2, "expected <E06 FBX> <texture directory>"
    fbx_path, texture_directory = map(Path, args)
    assert fbx_path.is_file(), fbx_path
    assert texture_directory.is_dir(), texture_directory

    module.register()
    try:
        from io_scene_fbx import import_fbx as blender_import_fbx
        original_collect = (
            blender_import_fbx.FbxImportHelperNode.collect_armature_meshes)

        props = bpy.context.scene.roe
        props.workflow_mode = "ROE"
        props.fbx_path = str(fbx_path)
        props.tex_dir = str(texture_directory)

        result = bpy.ops.roe.import_fbx()
        assert result == {"FINISHED"}, result
        assert (blender_import_fbx.FbxImportHelperNode.collect_armature_meshes
                is original_collect), "FBX importer wrapper was not restored"

        expected_source_slots = {
            "pc_e06_hd_body": ["pc_e06_hd_skin", "pc_e06_hd_body"],
            "pc_e06_hd_hair": ["pc_e06_hd_hair"],
            "pc_e06_hd_head": [
                "pc_e_nk_eyebrow", "pc_e_nk_face",
                "pc_e06_hd_body", "pc_e_nk_eyes",
            ],
            "wp_e_06": ["wp_e_06_hd"],
        }
        for object_name, expected_slots in expected_source_slots.items():
            obj = bpy.data.objects[object_name]
            actual_slots = [
                slot.material.name if slot.material else None
                for slot in obj.material_slots
            ]
            assert actual_slots == expected_slots, (object_name, actual_slots)
            assert any(modifier.type == "ARMATURE"
                       for modifier in obj.modifiers), object_name

        weapon = bpy.data.objects["wp_e_06"]
        assert [group.name for group in weapon.vertex_groups] == ["ball_scale"]
        armature = bpy.data.objects["Root"]
        assert len(armature.data.bones) == 169

        result = bpy.ops.roe.apply_materials()
        assert result == {"FINISHED"}, result
        assert len(bpy.data.objects["pc_e06_hd_body"].material_slots) == 2
        assert len(bpy.data.objects["pc_e06_hd_hair"].material_slots) == 1
        assert len(bpy.data.objects["pc_e06_hd_head"].material_slots) == 5
        assert len(bpy.data.objects["wp_e_06"].material_slots) == 1
    finally:
        module.unregister()

print("ROE_FBX_MISSING_BIND_COMPAT_TEST=PASS")
