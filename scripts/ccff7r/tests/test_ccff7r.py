"""Offline tests for the CCFF7R scripts (no game, CLI or Blender needed).

    python -m unittest discover -s scripts/ccff7r/tests      # from the repo root
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import ccff7r_common as cc  # noqa: E402
import export_model as em  # noqa: E402

PACKAGES = [
    "CCFF7R/Content/Fair/Character/01_named/tifa/Mesh/SK_CH_tifa.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Mesh/SK_CH_tifa_SW.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Mesh/SKL_CH_tifa.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Texture/T_CH_tifa_body_BC.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Texture/T_CH_tifa_body_BC.ubulk",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Material/MI_CH_tifa_body.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Material/CutScene/MI_CH_tifa_body_CS.uasset",
    "CCFF7R/Content/Fair/Character/01_named/tifa/Animation/Face/AS_tifa_fcm_EYE_OPEN.uasset",
    "CCFF7R/Content/Fair/Character/01_named/zack_s12/Mesh/SK_CH_zack_s12.uasset",
    "CCFF7R/Content/Fair/Character/01_named/zack_s21/Mesh/SK_CH_zack_s21.uasset",
    "CCFF7R/Content/Fair/Character/04_enemy/behemoth2/Mesh/SK_CH_behemoth2.uasset",
    "CCFF7R/Content/Fair/Character/03_mob/npc_girl/Mesh/SK_CH_npc_girl.uasset",
    "CCFF7R/Content/Fair/Object/letter_aerith/Mesh/SK_OB_letter_aerith.uasset",
    "CCFF7R/Content/Fair/Object/letter_aerith/Mesh/SK_OB_letter_aerith_sw.uasset",
    "CCFF7R/Content/Fair/Object/chair/Mesh/SK_OB_chair_a.uasset",
    "CCFF7R/Content/Fair/Object/chair/Mesh/SK_OB_chair_b.uasset",
    "CCFF7R/Content/Fair/Map/mid5_06/Material/MI_en_mid5_06.uasset",
]


class PathTests(unittest.TestCase):
    def test_object_paths_map_to_packages(self):
        self.assertEqual(cc.object_to_package("/Game/Fair/Character/01_named/tifa/Material/MI_CH_tifa_hair.0"),
                         "CCFF7R/Content/Fair/Character/01_named/tifa/Material/MI_CH_tifa_hair.uasset")
        self.assertEqual(cc.object_to_package("Texture2D'/Game/Fair/X/T_a.T_a'"), "CCFF7R/Content/Fair/X/T_a.uasset")
        self.assertEqual(cc.object_to_package("/Engine/EngineMaterials/DefaultNormal.0"),
                         "Engine/Content/EngineMaterials/DefaultNormal.uasset")
        self.assertIsNone(cc.object_to_package("/SomePlugin/Thing.0"))
        self.assertIsNone(cc.object_to_package(None))

    def test_package_file(self):
        p = cc.package_file(r"E:\w\raw", "CCFF7R/Content/Fair/A/T_x.uasset", ".png")
        self.assertEqual(p, os.path.join(r"E:\w\raw", "CCFF7R", "Content", "Fair", "A", "T_x") + ".png")


class NamingTests(unittest.TestCase):
    def test_enemy_groups(self):
        self.assertEqual(cc.enemy_group("behemoth2"), "Behemoth")
        self.assertEqual(cc.enemy_group("black_mask_w_worse"), "BlackMask")
        self.assertEqual(cc.enemy_group("seaworm3_lw"), "Seaworm")
        self.assertEqual(cc.enemy_group("g_copy_aw1"), "GCopyAw")

    def test_describe(self):
        self.assertEqual(cc.describe("named", "tifa"), ("Tifa", "Tifa", "蒂法"))
        self.assertEqual(cc.describe("named", "tian_costa")[0], "Cissnei")
        self.assertEqual(cc.describe("npc", "npc_girl")[0], "NPC")
        self.assertEqual(cc.describe("enemy", "behemoth2")[0], "Enemy_Behemoth")
        self.assertEqual(cc.describe("object", "bustersword")[0], "Objects")


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self.models = cc.discover_models(PACKAGES, root=r"Z:\nowhere")

    def test_one_model_per_mesh_with_sw_twin(self):
        tifa = next(m for m in self.models if m["id"] == "tifa")
        self.assertEqual(tifa["mesh"], "SK_CH_tifa")
        self.assertTrue(tifa["sw_package"].endswith("SK_CH_tifa_SW.uasset"))
        self.assertEqual((tifa["textures"], tifa["materials"], tifa["animations"]), (1, 1, 1))
        self.assertEqual(tifa["group"], "Tifa")
        self.assertFalse(tifa["exported"])
        self.assertTrue(tifa["blend"].endswith(os.path.join("Tifa", "blend", "tifa", "tifa.blend")))

    def test_sw_twins_are_not_models(self):
        ids = [m["id"] for m in self.models]
        self.assertNotIn("tifa_sw", ids)
        self.assertEqual(len([i for i in ids if i.startswith("letter_aerith")]), 1)
        self.assertTrue(next(m for m in self.models if m["id"] == "letter_aerith")["sw_package"])

    def test_folders_with_several_meshes_use_mesh_ids(self):
        ids = {m["id"] for m in self.models if m["folder"] == "chair"}
        self.assertEqual(ids, {"sk_ob_chair_a", "sk_ob_chair_b"})

    def test_categories_and_order(self):
        cats = [m["category"] for m in self.models]
        self.assertEqual(cats, sorted(cats, key=cc.CATEGORY_ORDER.index))
        self.assertEqual(next(m for m in self.models if m["id"] == "behemoth2")["category"], "enemy")

    def test_find_models(self):
        self.assertEqual([m["id"] for m in cc.find_models(self.models, ["tifa"])], ["tifa"])
        self.assertEqual({m["id"] for m in cc.find_models(self.models, ["Zack"])}, {"zack_s12", "zack_s21"})
        self.assertEqual({m["id"] for m in cc.find_models(self.models, ["zack_s1*"])}, {"zack_s12"})
        self.assertEqual({m["id"] for m in cc.find_models(self.models, ["扎克斯"])}, {"zack_s12", "zack_s21"})
        with self.assertRaises(SystemExit):
            cc.find_models(self.models, ["cloud"])


class MaterialTests(unittest.TestCase):
    def test_family_from_shared_parents(self):
        self.assertEqual(em.family_of(["MI_CH_tifa_head", "MI_ch_Human_Skin", "M_ch_Human_Skin"]), "skin")
        self.assertEqual(em.family_of(["MI_ch_Human_Mouth", "M_ch_Human_Skin"]), "skin")
        self.assertEqual(em.family_of(["MI_CH_tifa_eyelash", "MI_ch_Eyelash", "M_ch_Eyelash"]), "eyelash")
        self.assertEqual(em.family_of(["MI_CH_tifa_eye", "MI_ch_Eye2_ad", "M_ch_Eye2_ad"]), "eye")
        self.assertEqual(em.family_of(["MI_CH_npc_hair", "MI_ch_mob_Hair", "MI_ch_Hair", "M_ch_Hair"]), "hair")
        self.assertEqual(em.family_of(["MI_CH_hojo_glass", "MI_ch_Glass", "M_ch_Glass"]), "glass")
        self.assertEqual(em.family_of(["MI_CH_huge_materia1", "MI_ch_GemStandard", "M_ch_Gem"]), "gem")
        # a per-character name must not decide: an "_eye" patch on a Standard parent is cloth
        self.assertEqual(em.family_of(["MI_CH_x_eyepatch", "MI_ch_Standard", "M_ch_StandardSS"]), "standard")
        self.assertEqual(em.family_of(["MI_OB_bustersword"]), "standard")

    def test_merge_chain_child_wins_parent_defaults_kept(self):
        child = {"textures": {"AlbedMap": "/Game/a_BC.0"}, "scalars": {"Spec_Int": 0.85}, "vectors": {},
                 "switches": {}, "overrides": {"UseMaskDisable": True}}
        parent = {"textures": {"AlbedMap": "/Game/default.0", "PoreSpec": "/Game/pore.0"},
                  "scalars": {"Spec_Int": 1.0, "PoreTiling": 20.0}, "vectors": {"SSC": [1, 0, 0, 1]},
                  "switches": {}, "overrides": {"BlendMode": "EBlendMode::BLEND_Masked"}}
        m = em.merge_chain([child, parent])
        self.assertEqual(m["textures"], {"AlbedMap": "/Game/a_BC.0", "PoreSpec": "/Game/pore.0"})
        self.assertEqual(m["scalars"], {"Spec_Int": 0.85, "PoreTiling": 20.0})
        self.assertEqual(m["overrides"], {"UseMaskDisable": True, "BlendMode": "EBlendMode::BLEND_Masked"})

    def test_mi_record(self):
        export = {"Type": "MaterialInstanceConstant", "Name": "MI_CH_tifa_body", "Properties": {
            "Parent": {"ObjectPath": "/Game/Fair/Character/00_Common/Materials/MI_ch_Standard.0"},
            "TextureParameterValues": [{"ParameterInfo": {"Name": "Tex_Color"},
                                        "ParameterValue": {"ObjectPath": "/Game/T_CH_tifa_body_BC.0"}}],
            "ScalarParameterValues": [{"ParameterInfo": {"Name": "Roughness_Min"}, "ParameterValue": 0.1}],
            "VectorParameterValues": [{"ParameterInfo": {"Name": "Color_Tint"},
                                       "ParameterValue": {"R": 0.45, "G": 0.45, "B": 0.45, "A": 1.0}}],
            "StaticParameters": {"StaticSwitchParameters": [{"ParameterInfo": {"Name": "AO_2ndUV"}, "Value": True}]},
            "BasePropertyOverrides": {"BlendMode": "EBlendMode::BLEND_Masked", "OpacityMaskClipValue": 0.3333},
            "bUseMaskDisable": True}}
        rec = em.mi_record(export)
        self.assertEqual(rec["parent"], "/Game/Fair/Character/00_Common/Materials/MI_ch_Standard.0")
        self.assertEqual(rec["textures"], {"Tex_Color": "/Game/T_CH_tifa_body_BC.0"})
        self.assertEqual(rec["scalars"], {"Roughness_Min": 0.1})
        self.assertEqual(rec["vectors"], {"Color_Tint": [0.45, 0.45, 0.45, 1.0]})
        self.assertEqual(rec["switches"], {"AO_2ndUV": True})
        self.assertTrue(rec["overrides"]["UseMaskDisable"])
        self.assertEqual(rec["overrides"]["OpacityMaskClipValue"], 0.3333)


if __name__ == "__main__":
    unittest.main()
