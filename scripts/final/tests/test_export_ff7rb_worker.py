"""Pure-python tests for export_ff7rb_model_blender.py helpers.

Runs without Blender: ``bpy`` is mocked the same way as in
``test_ff7rebirth_helpers.py``.  Only the numpy math and constants are
covered here; the Blender-dependent flow is exercised by the batch script
against real FModel exports.
"""

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

import numpy


def load_worker_module():
    bpy = types.ModuleType("bpy")
    bpy.path = types.SimpleNamespace(abspath=os.path.abspath)
    bpy.ops = types.SimpleNamespace()
    bpy.data = types.SimpleNamespace()
    bpy.context = types.SimpleNamespace()

    module_names = ("bpy",)
    previous = {name: sys.modules.get(name) for name in module_names}
    try:
        sys.modules["bpy"] = bpy
        path = Path(__file__).resolve().parents[1] / "export_ff7rb_model_blender.py"
        spec = importlib.util.spec_from_file_location(
            "export_ff7rb_worker_under_test", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


WORKER = load_worker_module()


def solid(height, width, rgba):
    array = numpy.zeros((height, width, 4), dtype=numpy.float32)
    array[:] = rgba
    return array


class BlendEyeArraysTest(unittest.TestCase):
    def test_iris_center_sclera_outside(self):
        sclera = solid(64, 64, (1.0, 1.0, 1.0, 1.0))
        iris = solid(64, 64, (0.0, 0.0, 1.0, 1.0))
        out = WORKER.blend_eye_arrays(sclera, iris, inner=0.18, outer=0.22)
        # UV (0.5, 0.5) is the iris center; the corner is far outside.
        center = out[32, 32]
        corner = out[0, 0]
        self.assertAlmostEqual(center[2], 1.0, places=5)
        self.assertAlmostEqual(center[0], 0.0, places=5)
        self.assertAlmostEqual(corner[0], 1.0, places=5)
        self.assertAlmostEqual(corner[2], 1.0, places=5)
        # Alpha is forced opaque for portable exporters.
        self.assertTrue(numpy.all(out[..., 3] == 1.0))

    def test_transition_band_blends(self):
        sclera = solid(128, 128, (1.0, 1.0, 1.0, 1.0))
        iris = solid(128, 128, (0.0, 0.0, 0.0, 1.0))
        out = WORKER.blend_eye_arrays(sclera, iris, inner=0.18, outer=0.22)
        # A pixel at distance 0.20 from center sits mid-transition.
        row = 64
        col = int(round((0.5 + 0.20) * 128 - 0.5))
        value = out[row, col, 0]
        self.assertGreater(value, 0.1)
        self.assertLess(value, 0.9)

    def test_iris_map_is_read_at_its_own_scaled_uv(self):
        # iris-only map: "pupil" blue inside radius 0.3 of the map, red iris outside
        size = 128
        ys, xs = numpy.mgrid[0:size, 0:size]
        radius = numpy.hypot((xs + 0.5) / size - 0.5, (ys + 0.5) / size - 0.5)
        iris = solid(size, size, (1.0, 0.0, 0.0, 1.0))
        iris[radius < 0.3] = (0.0, 0.0, 1.0, 1.0)
        sclera = solid(size, size, (1.0, 1.0, 1.0, 1.0))
        row = 64
        col = int(round((0.5 + 0.20) * size - 0.5))    # eye-UV radius 0.20: inside the iris mask
        scaled = WORKER.blend_eye_arrays(sclera, iris, inner=0.225, outer=0.25, iris_scale=2.0)
        raw = WORKER.blend_eye_arrays(sclera, iris, inner=0.225, outer=0.25, iris_scale=1.0)
        # x2: eye radius 0.20 reads the map at 0.40 -> iris red; unscaled it hits the "pupil"
        self.assertGreater(scaled[row, col, 0], 0.9)
        self.assertLess(scaled[row, col, 2], 0.1)
        self.assertGreater(raw[row, col, 2], 0.9)
        # the centre still shows the pupil
        self.assertGreater(scaled[64, 64, 2], 0.9)

    def test_mismatched_sizes_use_larger_canvas(self):
        sclera = solid(32, 32, (1.0, 0.0, 0.0, 1.0))
        iris = solid(64, 64, (0.0, 1.0, 0.0, 1.0))
        out = WORKER.blend_eye_arrays(sclera, iris)
        self.assertEqual(out.shape, (64, 64, 4))


class ResampleNearestTest(unittest.TestCase):
    def test_identity(self):
        array = numpy.arange(2 * 3 * 4, dtype=numpy.float32).reshape(2, 3, 4)
        out = WORKER.resample_nearest(array, 3, 2)
        self.assertTrue(numpy.array_equal(out, array))

    def test_upscale_preserves_quadrants(self):
        array = numpy.zeros((2, 2, 4), dtype=numpy.float32)
        array[0, 0] = (1.0, 0.0, 0.0, 1.0)
        array[1, 1] = (0.0, 0.0, 1.0, 1.0)
        out = WORKER.resample_nearest(array, 4, 4)
        self.assertEqual(out.shape, (4, 4, 4))
        self.assertTrue(numpy.array_equal(out[0, 0], array[0, 0]))
        self.assertTrue(numpy.array_equal(out[3, 3], array[1, 1]))


class FormatContractTest(unittest.TestCase):
    def test_portable_formats_exclude_unvalidated(self):
        # XPS/PMX are intentionally not offered for FF7RB yet.
        self.assertEqual(WORKER.VALID_FORMATS, {"blend", "fbx", "glb"})

    def test_result_prefix_matches_driver(self):
        driver = (Path(__file__).resolve().parents[1] /
                  "export_ff7rb_models.ps1").read_text(encoding="utf-8")
        self.assertIn("'" + WORKER.RESULT_PREFIX + "'", driver)


if __name__ == "__main__":
    unittest.main()
