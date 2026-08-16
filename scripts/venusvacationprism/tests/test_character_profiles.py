from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from character_profiles import (  # noqa: E402
    CHARACTER_PROFILES,
    FALLBACK_REQUIRED_SUPPORT,
    FULL_SUPPORT,
    LEGACY_VERIFIED_SUPPORT,
    enabled_character_profiles,
    get_character_profile,
    resolve_character_key,
)
from prism_rdb import rdb_name_hash  # noqa: E402


EXPECTED_COMPONENTS = {
    "misaki": {
        "BODY": (837, 0x8BAAA1CE, 0xBCEA6C57, 0xAEE4A5D0,
                 0xC3D9FDD5, 0x2DEDAD04, 0xBD258495, 11),
        "FACE": (847, 0x91DDC350, 0x6ED8E62F, 0x60D31FA8,
                 0x75C877AD, 0xB9CE6E2C, 0x6F13FE6D, 69),
        "HAIR": (723, 0x2C910555, 0xA23CFD34, 0x943736AD,
                 0xA92C8EB2, 0xF2ED37C7, 0xA2781572, 26),
    },
    "elise": {
        "BODY": (834, 0x8BAAA1CE, 0xA37B6D08, 0x9575A681,
                 0xAA6AFE86, 0x197CC273, 0xA3B68546, 46),
        "FACE": (773, 0x3455A5E5, 0x44B32DC4, 0x36AD673D,
                 0x4BA2BF42, 0x9F3D1937, 0x44EE4602, 69),
        "HAIR": (867, 0xCF08E7EA, 0x781744C9, 0x6A117E42,
                 0x7F06D647, 0xD85BE2D2, 0x78525D07, 14),
    },
    "honoka": {
        "BODY": (1479, 0xF1C80847, 0xA3BDDE26, 0x95B8179F,
                 0xAAAD6FA4, 0x21887515, 0xA3F8F664, 48),
        "FACE": (824, 0x71FD9D40, 0x63A9B01F, 0x55A3E998,
                 0x6A99419D, 0x5F16E23C, 0x63E4C85D, 69),
        "HAIR": (117, 0x0CB0DF45, 0x970DC724, 0x8908009D,
                 0x9DFD58A2, 0x9835ABD7, 0x9748DF62, 19),
    },
    "nanami": {
        "BODY": (722, 0x26C40D9E, 0x4A842A7D, 0x3C7E63F6,
                 0x5173BBFB, 0x538BB39E, 0x4ABF42BB, 55),
        "FACE": (858, 0xAEF558E6, 0x4C9271C5, 0x3E8CAB3E,
                 0x53820343, 0x93465556, 0x4CCD8A03, 69),
        "HAIR": (815, 0x49A89AEB, 0x7FF688CA, 0x71F0C243,
                 0x86E61A48, 0xCC651EF1, 0x8031A108, 21),
    },
    "fiona": {
        "BODY": (857, 0xAB6B8248, 0x1257E927, 0x045222A0,
                 0x19477AA5, 0x862FCA34, 0x12930165, 54),
        "FACE": (1125, 0xDD9A6ABE, 0xAFF2DB9D, 0xA1ED1516,
                 0xB6E26D1B, 0x9BF3267E, 0xB02DF3DB, 69),
        "HAIR": (828, 0x784DACC3, 0xE356F2A2, 0xD5512C1B,
                 0xEA468420, 0xD511F019, 0xE3920AE0, 14),
    },
    "tamaki": {
        "BODY": (842, 0x8BAAA1CE, 0x50A25411, 0x429C8D8A,
                 0x5791E58F, 0x1132BC8A, 0x50DD6C4F, 33),
        "FACE": (850, 0xA00AAF19, 0xF34EAAF8, 0xE548E471,
                 0xFA3E3C76, 0xC4114283, 0xF389C336, 69),
        "HAIR": (813, 0x3ABDF11E, 0x26B2C1FD, 0x18ACFB76,
                 0x2DA2537B, 0xFD300C1E, 0x26EDDA3B, 14),
    },
}


EXPECTED_BASELINES = {
    "misaki": (54, 3, 160_036, 262_859, 16, 60),
    "elise": (71, 3, 176_094, 260_140, 21, 34),
    "honoka": (71, 3, 297_544, 420_661, 24, 67),
    "nanami": (75, 4, 230_539, 352_425, 28, 72),
    "fiona": (78, 3, 281_364, 428_599, 25, 65),
    "tamaki": (78, 3, 358_368, 468_659, 22, 60),
}


class CharacterProfileTests(unittest.TestCase):
    def test_has_the_six_formally_verified_profiles(self) -> None:
        self.assertEqual(
            set(CHARACTER_PROFILES),
            {"misaki", "elise", "honoka", "nanami", "fiona", "tamaki"},
        )

    def test_resolves_english_code_and_chinese_aliases(self) -> None:
        cases = {
            "Misaki": "misaki",
            " MIS ": "misaki",
            "海咲": "misaki",
            "Elise": "elise",
            "ELS": "elise",
            "伊莉丝": "elise",
            "Honoka": "honoka",
            "H-O-N": "honoka",
            "穗香": "honoka",
            "Nanami": "nanami",
            "N_N_M": "nanami",
            "七海": "nanami",
            "Fiona": "fiona",
            "FON": "fiona",
            "菲欧娜": "fiona",
            "Tamaki": "tamaki",
            "TAM": "tamaki",
            "环": "tamaki",
            "たまき": "tamaki",
        }
        for alias, expected in cases.items():
            with self.subTest(alias=alias):
                self.assertEqual(resolve_character_key(alias), expected)
                self.assertEqual(get_character_profile(alias).key, expected)

        with self.assertRaisesRegex(KeyError, "Unknown character"):
            get_character_profile("not-a-character")

    def test_resource_bundles_match_formal_manifests(self) -> None:
        for key, expected_components in EXPECTED_COMPONENTS.items():
            profile = CHARACTER_PROFILES[key]
            self.assertEqual(set(profile.components), {"BODY", "FACE", "HAIR"})
            for role, expected in expected_components.items():
                component = profile.components[role]
                actual = (
                    component.model_index,
                    component.package_id,
                    component.g1m,
                    component.oid,
                    component.grp,
                    component.ktid,
                    component.mtl,
                    component.texture_slots,
                )
                with self.subTest(character=key, component=role):
                    self.assertEqual(actual, expected)
                    self.assertEqual(
                        component.package_name,
                        f"0x{component.package_id:08x}.fdata")

    def test_only_named_labels_are_filename_hash_inputs(self) -> None:
        for profile in CHARACTER_PROFILES.values():
            for component in profile.components.values():
                with self.subTest(profile=profile.key, label=component.label):
                    if component.kind == "named":
                        self.assertEqual(component.internal_name, component.label)
                        for extension, expected in component.resource_ids.items():
                            self.assertEqual(
                                rdb_name_hash(component.label, extension), expected)
                    else:
                        self.assertEqual(component.kind, "curated_body")
                        self.assertIsNone(component.internal_name)
                        self.assertNotEqual(
                            rdb_name_hash(component.label, "g1m"), component.g1m)

    def test_full_automation_is_enabled_only_for_current_full_profiles(self) -> None:
        self.assertEqual(CHARACTER_PROFILES["honoka"].support_level, FULL_SUPPORT)
        self.assertEqual(CHARACTER_PROFILES["nanami"].support_level, FULL_SUPPORT)
        self.assertEqual(CHARACTER_PROFILES["fiona"].support_level, FULL_SUPPORT)
        self.assertEqual(CHARACTER_PROFILES["tamaki"].support_level, FULL_SUPPORT)
        self.assertEqual(
            CHARACTER_PROFILES["misaki"].support_level, LEGACY_VERIFIED_SUPPORT)
        self.assertEqual(
            CHARACTER_PROFILES["elise"].support_level, FALLBACK_REQUIRED_SUPPORT)
        self.assertEqual(
            {profile.key for profile in enabled_character_profiles()},
            {"honoka", "nanami", "fiona", "tamaki"},
        )
        for profile in CHARACTER_PROFILES.values():
            self.assertTrue(profile.limitations)
            self.assertTrue(profile.verified.source_assets)
            self.assertTrue(profile.verified.blend_roundtrip)
            self.assertTrue(profile.verified.fbx_roundtrip)
            self.assertTrue(profile.verified.visual_review)

    def test_alpha_sets_are_explicit_and_stable(self) -> None:
        self.assertEqual(CHARACTER_PROFILES["honoka"].alpha.body, (2, 4))
        self.assertEqual(CHARACTER_PROFILES["nanami"].alpha.body, ())
        self.assertEqual(CHARACTER_PROFILES["misaki"].alpha.hair, (0, 1, 2, 3))
        self.assertEqual(CHARACTER_PROFILES["elise"].alpha.hair, (0, 1))
        self.assertEqual(
            CHARACTER_PROFILES["fiona"].alpha.body,
            (0, 1, 2, 3, 6, 7, 8, 11),
        )
        self.assertEqual(CHARACTER_PROFILES["tamaki"].alpha.body, ())
        for profile in CHARACTER_PROFILES.values():
            self.assertEqual(profile.alpha.face, (1, 4, 5, 6, 8, 9, 10))
            self.assertEqual(profile.alpha.face_iris, (2, 3))
            self.assertEqual(profile.alpha.mode, "HASHED")

    def test_character_specific_body_rules_are_not_lost(self) -> None:
        elise = CHARACTER_PROFILES["elise"].body_postprocess
        self.assertEqual(elise["resolved_texture_slots"], 22)
        self.assertEqual(elise["unresolved_texture_slots"], 24)
        self.assertEqual(elise["skin_fallback_material_index"], 2)

        honoka = CHARACTER_PROFILES["honoka"].body_postprocess
        self.assertEqual(honoka["resolved_texture_slots"], 48)
        self.assertEqual(honoka["rejected_body_indices"], (864,))

        nanami = CHARACTER_PROFILES["nanami"].body_postprocess
        self.assertEqual(nanami["active_conditional_mesh_indices"], (7, 8, 9, 30))
        self.assertEqual(nanami["common_required_mesh_indices"], (23, 24))
        self.assertEqual(
            nanami["excluded_runtime_dt2_mesh_indices"], (10, 11, 12, 31, 32, 33))
        self.assertEqual(nanami["base_color_slots"], (21, 22))
        self.assertAlmostEqual(nanami["slot22_overlay_factor"], 0.054318)
        self.assertEqual(nanami["normal_slot"], 23)
        self.assertAlmostEqual(nanami["normal_strength"], 0.15)
        self.assertTrue(nanami["repair_cloth_normals_and_tangents"])
        self.assertEqual(nanami["rejected_body_indices"], (830,))

        fiona = CHARACTER_PROFILES["fiona"].body_postprocess
        self.assertEqual(fiona["resolved_texture_slots"], 54)
        self.assertEqual(fiona["rejected_face_indices"], (860,))
        self.assertEqual(fiona["skin_linked_meshes_after_conversion"], 32)
        self.assertEqual(
            fiona["static_nun_mesh_indices"],
            (5, 6, 8, 9, 10, 11, 17, 18),
        )
        self.assertEqual(fiona["static_nun_vertex_count"], 12_813)
        self.assertFalse(fiona["game_cloth_simulation_reproduced"])

        tamaki = CHARACTER_PROFILES["tamaki"].body_postprocess
        self.assertEqual(tamaki["resolved_texture_slots"], 30)
        self.assertEqual(tamaki["unresolved_texture_slots"], 3)
        self.assertEqual(tamaki["unresolved_texture_slot_indices"], (26, 27, 32))
        self.assertEqual(tamaki["static_cloth_meshes"], (11,))
        self.assertEqual(tamaki["static_cloth_invalid_joint_slots"], (6, 7))

    def test_regression_baselines_match_formal_readbacks(self) -> None:
        for key, expected in EXPECTED_BASELINES.items():
            baseline = CHARACTER_PROFILES[key].expected
            actual = (
                baseline.mesh_objects,
                baseline.armatures,
                baseline.vertices,
                baseline.polygons,
                baseline.materials,
                baseline.blend_packed_images,
            )
            with self.subTest(character=key):
                self.assertEqual(actual, expected)
                self.assertEqual(
                    baseline.blend_used_images, baseline.blend_packed_images)
                self.assertTrue(baseline.visual_assertions)

        nanami = CHARACTER_PROFILES["nanami"].expected
        honoka = CHARACTER_PROFILES["honoka"].expected
        self.assertEqual(honoka.output_formats, ("blend", "fbx", "glb"))
        self.assertEqual(honoka.glb_readback_vertices, 299_948)
        self.assertEqual(honoka.glb_readback_polygons, 420_661)
        self.assertTrue(CHARACTER_PROFILES["honoka"].verified.glb_roundtrip)

        self.assertEqual(nanami.output_formats, ("blend", "fbx", "glb"))
        self.assertEqual(nanami.glb_readback_vertices, 231_023)
        self.assertEqual(nanami.glb_readback_polygons, 352_425)
        self.assertEqual(nanami.neck_vertices_within_0_001, 43)
        self.assertTrue(CHARACTER_PROFILES["nanami"].verified.glb_roundtrip)

        fiona = CHARACTER_PROFILES["fiona"].expected
        tamaki = CHARACTER_PROFILES["tamaki"].expected
        self.assertEqual(fiona.glb_readback_vertices, 283_178)
        self.assertEqual(fiona.glb_readback_polygons, 428_599)
        self.assertEqual(fiona.body_mesh_objects, 40)
        self.assertEqual(fiona.body_skin_linked_meshes, 32)
        self.assertEqual(tamaki.glb_readback_vertices, 362_419)
        self.assertEqual(tamaki.glb_readback_polygons, 468_659)
        self.assertEqual(tamaki.neck_vertices_within_0_001, 43)
        self.assertEqual(tamaki.body_mesh_objects, 32)
        self.assertEqual(tamaki.body_skin_linked_meshes, 25)

        self.assertIn(
            "fiona/complete/validation/Fiona_delivery_manifest.json",
            CHARACTER_PROFILES["fiona"].verified.evidence,
        )
        self.assertIn(
            "tamaki/complete/components/body/cloth_static_fallback_report.json",
            CHARACTER_PROFILES["tamaki"].verified.evidence,
        )


if __name__ == "__main__":
    unittest.main()
