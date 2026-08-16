from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from character_profiles import get_character_profile  # noqa: E402
from export_character import (  # noqa: E402
    _csv,
    claim_output_directory,
    component_plan,
    ensure_output_state,
    serializable_profile,
    validate_baseline,
)


class CharacterExportEntryTests(unittest.TestCase):
    def fixture_directory(self, name: str, files: tuple[str, ...]) -> Path:
        """Create a deterministic fixture without TemporaryDirectory ACL issues."""
        directory = SCRIPT_DIR / "tests" / name
        directory.mkdir(exist_ok=True)
        self.addCleanup(directory.rmdir)
        for filename in files:
            path = directory / filename
            path.unlink(missing_ok=True)
            self.addCleanup(path.unlink, missing_ok=True)
        return directory

    def test_format_parser_is_stable_and_rejects_unknown_values(self) -> None:
        self.assertEqual(_csv("blend,fbx,glb,blend"), ("blend", "fbx", "glb"))
        with self.assertRaisesRegex(Exception, "unknown format"):
            _csv("blend,xps")

    def test_plan_uses_curated_component_ids(self) -> None:
        plan = component_plan(get_character_profile("Nanami"))
        self.assertEqual(plan["body"]["model_index"], 722)
        self.assertEqual(plan["body"]["g1m"], "0x4a842a7d")
        self.assertEqual(plan["face"]["texture_slots"], 69)
        self.assertEqual(plan["hair"]["texture_slots"], 21)

    def test_profile_serialization_handles_read_only_nested_mappings(self) -> None:
        value = serializable_profile(get_character_profile("Honoka"))
        encoded = json.dumps(value, ensure_ascii=False)
        self.assertIn("BODY_HON_HIPHOP_1479", encoded)
        self.assertEqual(value["body_postprocess"]["rejected_body_indices"], [864])

    def test_verified_baseline_report(self) -> None:
        profile = get_character_profile("Nanami")
        directory = self.fixture_directory(
            "_export_character_baseline_fixture",
            ("report.json", "character_profile_regression.json", "model.blend"),
        )
        report = directory / "report.json"
        model = directory / "model.blend"
        model.write_bytes(b"BLENDER")
        expected = profile.expected
        report.write_text(json.dumps({
            "formats_requested": ["blend"],
            "identity_alignment": True,
            "assembly_stats": {
                "mesh_objects": expected.mesh_objects,
                "armatures": expected.armatures,
                "vertices": expected.vertices,
                "polygons": expected.polygons,
                "materials": expected.materials,
            },
            "head_fit": {"face_hair_bounds_intersect": True},
            "neck_fit": {
                "nearest_distance_min": expected.neck_min_distance,
                "sampled_vertices_within_distance": {
                    "0.001": expected.neck_vertices_within_0_001,
                },
                "face_body_vertical_bounds_overlap": 1.0,
            },
            "components": {
                role: {"source": {
                    "root_nodes_identity": True,
                    "position_accessors_all_vec3": True,
                    "images": count,
                    "external_image_files_present": count,
                }}
                for role, count in (("BODY", 55), ("FACE", 69), ("HAIR", 21))
            },
            "outputs": {"blend": str(model)},
            "blend_pack_audit": {
                "images_used": expected.blend_used_images,
                "used_images_packed": expected.blend_packed_images,
                "used_images_unpacked": [],
            },
            "previews_skipped": True,
        }), encoding="utf-8")
        result = validate_baseline(profile, report)
        self.assertTrue(result["passed"])
        self.assertTrue((directory / "character_profile_regression.json").is_file())

    def test_body_skin_link_count_is_a_checked_regression(self) -> None:
        profile = get_character_profile("Fiona")
        directory = self.fixture_directory(
            "_export_character_body_skin_fixture",
            ("report.json", "character_profile_regression.json", "model.blend"),
        )
        report_path = directory / "report.json"
        model = directory / "model.blend"
        model.write_bytes(b"BLENDER")
        expected = profile.expected
        report = {
            "formats_requested": ["blend"],
            "identity_alignment": True,
            "assembly_stats": {
                "mesh_objects": expected.mesh_objects,
                "armatures": expected.armatures,
                "vertices": expected.vertices,
                "polygons": expected.polygons,
                "materials": expected.materials,
            },
            "head_fit": {"face_hair_bounds_intersect": True},
            "neck_fit": {"face_body_vertical_bounds_overlap": 1.0},
            "components": {
                role: {
                    "source": {
                        "root_nodes_identity": True,
                        "position_accessors_all_vec3": True,
                        "images": count,
                        "external_image_files_present": count,
                    },
                    **(
                        {
                            "mesh_names": [
                                f"BODY_Mesh_{index}"
                                for index in range(expected.body_mesh_objects or 0)
                            ],
                            "rig_namespace": {
                                "armatures": [{
                                    "linked_meshes": expected.body_skin_linked_meshes
                                }]
                            },
                        }
                        if role == "BODY"
                        else {}
                    ),
                }
                for role, count in (("BODY", 54), ("FACE", 69), ("HAIR", 14))
            },
            "outputs": {"blend": str(model)},
            "blend_pack_audit": {
                "images_used": expected.blend_used_images,
                "used_images_packed": expected.blend_packed_images,
                "used_images_unpacked": [],
            },
            "previews_skipped": True,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        self.assertTrue(validate_baseline(profile, report_path)["passed"])

        report["components"]["BODY"]["rig_namespace"]["armatures"][0][
            "linked_meshes"
        ] = 31
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "verified Fiona baseline"):
            validate_baseline(profile, report_path)
        result = json.loads(
            (directory / "character_profile_regression.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["body_skin_linked_meshes"]["passed"])

    def test_nonempty_output_requires_resume(self) -> None:
        directory = self.fixture_directory(
            "_export_character_output_fixture", ("keep.txt",)
        )
        (directory / "keep.txt").write_text("user data", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "--resume"):
            ensure_output_state(directory, resume=False)
        ensure_output_state(directory, resume=True)

    def test_resume_directory_is_bound_to_one_character(self) -> None:
        directory = self.fixture_directory(
            "_export_character_owner_fixture",
            (".prism-character-export.json",),
        )
        plan = {
            "formats": ["blend", "fbx", "glb"],
            "assets_only": False,
        }
        claim_output_directory(
            directory, get_character_profile("Nanami"), plan, resume=False
        )
        with self.assertRaisesRegex(Exception, "selection differs"):
            claim_output_directory(
                directory, get_character_profile("Honoka"), plan, resume=True
            )


if __name__ == "__main__":
    unittest.main()
