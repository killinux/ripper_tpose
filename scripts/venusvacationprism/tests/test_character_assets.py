from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from character_assets import (  # noqa: E402
    CharacterAssetError,
    _parse_ktid,
    _profile_to_specs,
)
from character_profiles import get_character_profile  # noqa: E402
from g1m_to_gltf import validate_external_gltf  # noqa: E402


class CharacterAssetProfileTests(unittest.TestCase):
    def test_nanami_profile_preserves_scoped_body_policy(self) -> None:
        character, specs = _profile_to_specs(get_character_profile("七海"))
        self.assertEqual(character, "Nanami")
        self.assertEqual({item.role for item in specs}, {"body", "face", "hair"})
        body = next(item for item in specs if item.role == "body")
        self.assertEqual(body.g1m_id, 0x4A842A7D)
        self.assertEqual(body.postprocess["kind"], "nanami_body722")
        self.assertEqual(body.postprocess["hidden_dt2_meshes"], [10, 11, 12, 31, 32, 33])
        self.assertEqual(body.postprocess["base_slot"], 21)
        self.assertEqual(body.postprocess["overlay_slot"], 22)
        self.assertAlmostEqual(body.postprocess["normal_strength"], 0.15)

    def test_ktid_requires_zero_based_contiguous_slots(self) -> None:
        payload = b"".join(
            struct.pack("<II", slot, 0x10000000 + slot) for slot in range(3)
        )
        self.assertEqual(
            _parse_ktid(payload),
            [(0, 0x10000000), (1, 0x10000001), (2, 0x10000002)],
        )
        with self.assertRaisesRegex(CharacterAssetError, "not contiguous"):
            _parse_ktid(struct.pack("<II", 1, 0x12345678))


class ExternalGltfValidationTests(unittest.TestCase):
    def fixture(self, name: str) -> tuple[Path, Path]:
        root = SCRIPT_DIR / "tests"
        gltf = root / f"_{name}.gltf"
        buffer = root / f"_{name}.bin"
        gltf.unlink(missing_ok=True)
        buffer.unlink(missing_ok=True)
        self.addCleanup(gltf.unlink, missing_ok=True)
        self.addCleanup(buffer.unlink, missing_ok=True)
        return gltf, buffer

    @staticmethod
    def document(uri: str, accessor_type: str = "VEC3") -> dict:
        return {
            "asset": {"version": "2.0"},
            "buffers": [{"uri": uri, "byteLength": 12}],
            "accessors": [{"type": accessor_type, "componentType": 5126}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        }

    def test_accepts_local_vec3_external_buffer(self) -> None:
        gltf, buffer = self.fixture("valid_external_gltf")
        buffer.write_bytes(b"\0" * 12)
        gltf.write_text(
            json.dumps(self.document(buffer.name)), encoding="utf-8"
        )
        report = validate_external_gltf(gltf)
        self.assertTrue(report["passed"])
        self.assertEqual(report["buffer_actual_bytes"], 12)

    def test_rejects_absolute_uri_and_vec4_position(self) -> None:
        gltf, buffer = self.fixture("invalid_external_gltf")
        buffer.write_bytes(b"\0" * 12)
        gltf.write_text(
            json.dumps(self.document(str(buffer.resolve()), "VEC4")),
            encoding="utf-8",
        )
        report = validate_external_gltf(gltf)
        self.assertFalse(report["passed"])
        self.assertIn("buffer URI must be relative", report["errors"])
        self.assertTrue(
            any("non-VEC3" in message for message in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
