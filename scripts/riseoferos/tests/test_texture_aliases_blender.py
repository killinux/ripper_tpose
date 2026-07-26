"""Run with Blender 3.6:

blender --background --factory-startup --python \
    scripts/riseoferos/tests/test_texture_aliases_blender.py
"""
import importlib.util
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATHS = (
    ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py",
    ROOT / "scripts" / "riseoferos" / "blender_face_materials.py",
)


def load_module(path, suffix):
    spec = importlib.util.spec_from_file_location(
        "roe_texture_alias_test_" + suffix, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_find_tex(module):
    with tempfile.TemporaryDirectory() as directory:
        nested = Path(directory) / "_textures"
        nested.mkdir()
        typo = nested / "pc_g02_hd_body_rgbx_Abedo.png"
        typo.touch()

        pattern = "pc_g02_hd_body*Albedo*.png"
        found = module.find_tex(directory, pattern)
        assert found
        assert os.path.basename(found) == typo.name

        canonical = nested / "pc_g02_hd_body_rgbx_Albedo.png"
        canonical.touch()
        found = module.find_tex(directory, pattern)
        assert found
        assert os.path.basename(found) == canonical.name


for index, module_path in enumerate(MODULE_PATHS):
    verify_find_tex(load_module(module_path, str(index)))

print("ROE_TEXTURE_ALIAS_TEST=PASS")
