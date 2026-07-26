import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


def load_addon_module():
    bpy = types.ModuleType("bpy")
    bpy.path = types.SimpleNamespace(abspath=os.path.abspath)
    bpy.ops = types.SimpleNamespace()
    bpy.data = types.SimpleNamespace()

    props = types.ModuleType("bpy.props")
    for name in ("BoolProperty", "FloatProperty", "PointerProperty", "StringProperty"):
        setattr(props, name, lambda **_kwargs: None)

    bpy_types = types.ModuleType("bpy.types")
    bpy_types.Operator = type("Operator", (), {})
    bpy_types.Panel = type("Panel", (), {})
    bpy_types.PropertyGroup = type("PropertyGroup", (), {})

    module_names = ("bpy", "bpy.props", "bpy.types")
    previous = {name: sys.modules.get(name) for name in module_names}
    try:
        sys.modules["bpy"] = bpy
        sys.modules["bpy.props"] = props
        sys.modules["bpy.types"] = bpy_types

        addon_path = Path(__file__).resolve().parents[1] / "ff7rebirth_tools.py"
        spec = importlib.util.spec_from_file_location(
            "_ff7rebirth_tools_test", addon_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


ADDON = load_addon_module()
TEST_TEMP_ROOT = Path(__file__).resolve().parent


class ModelSelectionTests(unittest.TestCase):
    def test_valid_pskx_beats_gltf(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            pskx = root / "PC0002_00.pskx"
            pskx.write_bytes(b"ACTRHEAD" + (b"\0" * 64))
            (root / "SK_PC0002_00_LOD0.glb").write_bytes(b"glTF")

            selected, _models = ADDON.best_model(str(root))

            self.assertEqual(pskx, Path(selected))
            self.assertTrue(ADDON.actorx_file_valid(str(pskx)))

    def test_invalid_pskx_does_not_beat_gltf(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            (root / "broken.pskx").write_bytes(b"NOT_ACTORX" + (b"\0" * 64))
            gltf = root / "fallback.gltf"
            gltf.write_text("{}", encoding="utf-8")

            selected, _models = ADDON.best_model(str(root))

            self.assertEqual(gltf, Path(selected))


class TextureResolutionTests(unittest.TestCase):
    def test_exact_unreal_path_beats_same_basename(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            exact = root / "End" / "Content" / "Character" / "Player" / "Foo" / "Texture" / "Tex.png"
            weak = root / "Other" / "Tex.png"
            reference = "/Game/Character/Player/Foo/Texture/Tex.Tex"
            index = {"tex": [str(weak), str(exact)]}

            self.assertEqual(
                os.path.normcase(str(exact)),
                os.path.normcase(ADDON.resolve_texture_reference(reference, index)),
            )

    def test_ambiguous_basename_only_match_is_rejected(self):
        reference = "/Game/Character/Player/Foo/Texture/Tex.Tex"
        index = {"tex": [os.path.join("A", "Tex.png"), os.path.join("B", "Tex.png")]}

        self.assertEqual("", ADDON.resolve_texture_reference(reference, index))

    def test_ff7_channel_suffixes_do_not_confuse_arms_with_arm(self):
        self.assertEqual("unknown", ADDON.texture_role("PC0002_00_Arms_O.png"))
        self.assertEqual("roughness", ADDON.texture_role("PC0002_00_Arms_Mg.png"))
        self.assertEqual("metallic", ADDON.texture_role("PC0002_00_Arms_Mr.png"))
        self.assertEqual("opacity", ADDON.texture_role("PC0002_00_Hair_A.png"))


class ImageColorSpaceTests(unittest.TestCase):
    def test_reused_base_image_is_reset_to_srgb(self):
        image = types.SimpleNamespace(
            colorspace_settings=types.SimpleNamespace(name="sRGB"))
        ADDON.bpy.data = types.SimpleNamespace(
            images=types.SimpleNamespace(load=lambda *_args, **_kwargs: image))

        ADDON.load_image("shared.png", non_color=True)
        self.assertEqual("Non-Color", image.colorspace_settings.name)
        ADDON.load_image("shared.png", non_color=False)
        self.assertEqual("sRGB", image.colorspace_settings.name)


class NormalMapTests(unittest.TestCase):
    def test_skin_like_materials_use_reduced_preview_strength(self):
        self.assertEqual(
            ADDON.SKIN_NORMAL_STRENGTH,
            ADDON.normal_strength_for_material("PC0002_00_Skin"),
        )
        self.assertEqual(
            ADDON.SKIN_NORMAL_STRENGTH,
            ADDON.normal_strength_for_material("Common_Mouth_Light"),
        )
        self.assertEqual(
            ADDON.DEFAULT_NORMAL_STRENGTH,
            ADDON.normal_strength_for_material("PC0002_00_Legs"),
        )

    def test_psk_shading_repair_disables_auto_smooth(self):
        polygons = [
            types.SimpleNamespace(use_smooth=False),
            types.SimpleNamespace(use_smooth=False),
        ]
        mesh_data = types.SimpleNamespace(
            polygons=polygons,
            use_auto_smooth=True,
            update=lambda: None,
        )
        mesh = types.SimpleNamespace(type="MESH", data=mesh_data)

        repaired = ADDON.repair_mesh_shading([mesh])

        self.assertEqual(1, repaired)
        self.assertFalse(mesh_data.use_auto_smooth)
        self.assertTrue(all(polygon.use_smooth for polygon in polygons))


class TransactionalImportTests(unittest.TestCase):
    class FakeObject(dict):
        def __init__(self, name, batch=""):
            super().__init__()
            self.name = name
            self.type = "MESH"
            self.parent = None
            self.scale = (1.0, 1.0, 1.0)
            self.selected = False
            if batch:
                self[ADDON.IMPORT_BATCH_KEY] = batch

        __hash__ = object.__hash__

        def select_set(self, value):
            self.selected = value

    def make_context(self, model_path):
        old = self.FakeObject("old", batch="old-batch")
        props = types.SimpleNamespace(
            model_path=str(model_path),
            source_dir=str(model_path.parent),
            replace_previous=True,
            import_scale=1.0,
            auto_materials=False,
            auto_fix_shading=False,
            texture_dir="",
            force_materials=False,
        )

        class FakeScene(dict):
            pass

        scene = FakeScene()
        scene.ff7rb = props
        scene.objects = [old]
        scene[ADDON.ACTIVE_BATCH_KEY] = "old-batch"
        view_layer = types.SimpleNamespace(
            objects=types.SimpleNamespace(active=None))
        return types.SimpleNamespace(scene=scene, view_layer=view_layer), old

    def run_operator(self, context, importer):
        original_import = ADDON.import_model
        original_remove = ADDON.remove_objects
        original_object_ops = getattr(ADDON.bpy.ops, "object", None)

        def remove_objects(objects):
            for obj in list(objects):
                if obj in context.scene.objects:
                    context.scene.objects.remove(obj)

        ADDON.import_model = importer
        ADDON.remove_objects = remove_objects
        ADDON.bpy.ops.object = types.SimpleNamespace(
            select_all=lambda **_kwargs: {"FINISHED"})
        operator = ADDON.FF7RB_OT_import_model()
        operator.report = lambda *_args, **_kwargs: None
        try:
            return operator.execute(context)
        finally:
            ADDON.import_model = original_import
            ADDON.remove_objects = original_remove
            if original_object_ops is None:
                del ADDON.bpy.ops.object
            else:
                ADDON.bpy.ops.object = original_object_ops

    def test_failed_import_removes_partial_objects_and_keeps_old_batch(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            model_path = Path(directory) / "model.pskx"
            model_path.write_bytes(b"ACTRHEAD" + (b"\0" * 64))
            context, old = self.make_context(model_path)
            partial = self.FakeObject("partial")

            def importer(_path):
                context.scene.objects.append(partial)
                raise RuntimeError("simulated failure")

            result = self.run_operator(context, importer)

            self.assertEqual({"CANCELLED"}, result)
            self.assertIn(old, context.scene.objects)
            self.assertNotIn(partial, context.scene.objects)
            self.assertEqual(
                "old-batch", context.scene[ADDON.ACTIVE_BATCH_KEY])

    def test_successful_import_commits_replacement(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            model_path = Path(directory) / "model.pskx"
            model_path.write_bytes(b"ACTRHEAD" + (b"\0" * 64))
            context, old = self.make_context(model_path)
            created = self.FakeObject("created")

            def importer(_path):
                context.scene.objects.append(created)
                return {"FINISHED"}

            result = self.run_operator(context, importer)

            self.assertEqual({"FINISHED"}, result)
            self.assertNotIn(old, context.scene.objects)
            self.assertIn(created, context.scene.objects)
            self.assertTrue(created.selected)
            self.assertNotEqual(
                "old-batch", context.scene[ADDON.ACTIVE_BATCH_KEY])

    def test_postprocess_failure_rolls_back_and_keeps_old_batch(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            model_path = Path(directory) / "model.pskx"
            model_path.write_bytes(b"ACTRHEAD" + (b"\0" * 64))
            context, old = self.make_context(model_path)
            context.scene.ff7rb.auto_materials = True
            created = self.FakeObject("created")

            def importer(_path):
                context.scene.objects.append(created)
                return {"FINISHED"}

            original_prepare = ADDON.prepare_object_materials

            def fail_materials(*_args, **_kwargs):
                raise RuntimeError("simulated unreadable texture")

            ADDON.prepare_object_materials = fail_materials
            try:
                result = self.run_operator(context, importer)
            finally:
                ADDON.prepare_object_materials = original_prepare

            self.assertEqual({"CANCELLED"}, result)
            self.assertIn(old, context.scene.objects)
            self.assertNotIn(created, context.scene.objects)
            self.assertEqual(
                "old-batch", context.scene[ADDON.ACTIVE_BATCH_KEY])


if __name__ == "__main__":
    unittest.main()
