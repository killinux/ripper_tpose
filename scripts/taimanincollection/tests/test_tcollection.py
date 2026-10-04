"""Offline tests for the Taimanin Collection scripts (no game and no Blender needed; UnityPy, numpy and Pillow
are imported).

    python -m unittest discover -s scripts/taimanincollection/tests      # from the repo root
"""
import argparse
import os
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import tcollection_common as tcc  # noqa: E402
import tcollection_scene as tcs  # noqa: E402
import ataimanin_scene as asc  # noqa: E402
import export_model  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "html"))
import make_gallery  # noqa: E402


class ModelListTests(unittest.TestCase):
    def test_where_a_prefab_lies_says_what_it_is(self):
        cases = {
            "unit_art/model/asagi/prf_asagi_costume_1": "character",
            "unit/asagi_g/asagi_g": "unit",
            "unit_art/model/asagi/costume_asagi_1/fbx_asagi_face": "part",
            "background/art/movie/fbx_motorcycle_rig": "vehicle",
            "background/art/movie/fbx_goldbox": "raw",
            "bike/level/prf_race_trackobject_57": "level",
            "bike/level/race_game_manager_01": "raw",
            "bike/background/prf_racebridge_track01": "prop",
            "bike/skybox/prf_night_skydome01": "prop",
            "bike/background/race_bridge/fbx_racebridge_track01": "raw",
            "background/art/movie/asagi_select/prf_asagi_bg": "set",
            "background/art/movie/in_game_movie/prf_movie_ch01_02": "set",
            "bike/director/drt_race_start_asagi": "director",
            "director/drt_gacha_card_10n": "director",
            "effect/art/effect_fbx/fbx_fx_ring_01": "effect",
            "ui/popup/MenuPopup": "",
        }
        for path, category in cases.items():
            self.assertEqual(tcc.category_of(path), category, path)
        self.assertIsNone(tcc.model_from_path("ui/popup/MenuPopup"))

    def test_ids_and_groups(self):
        asagi = tcc.model_from_path("unit_art/model/asagi/prf_asagi_costume_1")
        self.assertEqual((asagi["id"], asagi["group"], asagi["character"]), ("prf_asagi_costume_1", "Asagi", "asagi"))
        unit = tcc.model_from_path("unit/asagi_g/asagi_g")
        self.assertEqual((unit["id"], unit["group"], unit["category"]), ("asagi_g", "Asagi", "unit"))
        bike = tcc.model_from_path("background/art/movie/fbx_motorcycle_rig")
        self.assertEqual((bike["id"], bike["group"], bike["character"]), ("fbx_motorcycle_rig", "Vehicles", ""))
        self.assertEqual(tcc.model_from_path("bike/background/prf_truck_transportation")["group"], "Props")
        twin = tcc.model_from_path("bike/background/race_bridge/fbx_x", taken={"fbx_x"})    # a name met before
        self.assertEqual(twin["id"], "race_bridge_fbx_x")
        self.assertEqual(tc_dir(asagi, "pmx"), os.path.join("ROOT", "Asagi", "pmx", "prf_asagi_costume_1"))

    def test_a_scene_gives_itself_and_its_roots(self):
        none = {"skinned": 0, "rigid": 0, "particles": 0, "nodes": 3}
        bike = {"skinned": 4, "rigid": 0, "particles": 20, "nodes": 41}
        back = {"skinned": 0, "rigid": 16, "particles": 2, "nodes": 33}
        models = tcc.scene_models("level2", "race_bridge", [("UI Root", none), ("BikeObj", bike), ("background", back)])
        self.assertEqual([(m["id"], m["key"]) for m in models], [
            ("scene_race_bridge", "scene:level2"), ("scene_race_bridge_bikeobj", "scene:level2/BikeObj"),
            ("scene_race_bridge_background", "scene:level2/background")])
        self.assertEqual((models[0]["skinned"], models[0]["rigid"], models[0]["category"], models[0]["group"]),
                         (4, 16, "scene", "Scenes"))
        self.assertEqual(tcc.scene_models("level0", "Title", [("UI Root", none)]), [])            # nothing drawn
        alone = tcc.scene_models("level1", "Lobby", [("Director", back), ("UI Root", none)])
        self.assertEqual([m["id"] for m in alone], ["scene_lobby"])                                # one root: no split

    def test_find(self):
        models = [{"id": "prf_asagi_costume_1", "character": "asagi"}, {"id": "asagi_g", "character": "asagi"},
                  {"id": "fbx_motorcycle_rig", "character": ""}, {"id": "prf_truck_transportation", "character": ""}]
        ids = lambda found: [m["id"] for m in found]  # noqa: E731
        self.assertEqual(ids(tcc.find_models(models, ["asagi"])), ["prf_asagi_costume_1", "asagi_g"])
        self.assertEqual(ids(tcc.find_models(models, ["*truck*", "fbx_motorcycle_rig"])),
                         ["prf_truck_transportation", "fbx_motorcycle_rig"])
        self.assertEqual(ids(tcc.find_models(models, ["motorcycle"])), ["fbx_motorcycle_rig"])
        with self.assertRaises(SystemExit):
            tcc.find_models(models, ["yukikaze"])


def tc_dir(model, fmt):
    return tcc.tc.model_dir(model, "ROOT", fmt)


class PlayerBuildTests(unittest.TestCase):
    """What a build without type trees needs: the script of a component from its raw header, the layouts."""

    def test_the_script_of_a_component_is_in_its_header(self):
        raw = struct.pack("<iq", 0, 6377) + b"\x01\x00\x00\x00" + struct.pack("<iq", 1, 748) + struct.pack("<i", 0)
        self.assertEqual(tcc.script_reference(raw), (1, 748))
        self.assertEqual(tcc.script_reference(b"\x00" * 8), (0, 0))

    def test_the_dynamic_bone_layouts(self):
        nodes = tcc.type_nodes()
        self.assertEqual(sorted(nodes), ["DynamicBone", "DynamicBoneCollider"])
        fields = [child.m_Name for child in nodes["DynamicBone"].m_Children]
        self.assertEqual(fields[:5], ["m_GameObject", "m_Enabled", "m_Script", "m_Name", "m_Root"])
        for name in ("m_Damping", "m_Elasticity", "m_Stiffness", "m_Inert", "m_EndOffset", "m_Colliders", "m_FreezeAxis"):
            self.assertIn(name, fields)
        self.assertEqual([c.m_Name for c in nodes["DynamicBoneCollider"].m_Children][4:],
                         ["m_Direction", "m_Center", "m_Bound", "m_Radius", "m_Height"])

    def test_a_component_reads_itself_with_its_layout(self):
        class Reader:
            type = SimpleNamespace(name="MonoBehaviour")
            path_id = 7

            def read_typetree(self, node=None):
                return {"with": node}

        known = tcc.Component(Reader(), "DynamicBone", node="LAYOUT")
        self.assertEqual((known.script, known.path_id, known.type.name), ("DynamicBone", 7, "MonoBehaviour"))
        self.assertEqual(known.read_typetree(), {"with": "LAYOUT"})
        with self.assertRaises(ValueError):
            tcc.Component(Reader(), "UISprite").read_typetree()

    def test_the_face_clips_come_under_action_taimanins_paths(self):
        game = object.__new__(tcc.Game)
        clip = lambda path_id: SimpleNamespace(path_id=path_id)  # noqa: E731
        game._named = {"AnimationClip": {
            "ani_face_asagi_story_smile_01": [clip(3775), clip(3790)],      # the older set, then the one with all mouths
            "ani_mouth_asagi_story_smile_01": [clip(3797)],
            "ani_asagi_battle_run": [clip(10)], "ani_face_asagi_lobby_select": [clip(11)]}}
        table = game.container("animation_char")
        self.assertEqual(game.container("unit"), {})
        self.assertEqual([(key, reader.path_id) for key, reader in sorted(table.items())], [
            ("animation_char/asagi/ani_story/ani_face_asagi_story_smile_01.anim", 3790),
            ("animation_char/asagi/ani_story/ani_mouth_asagi_story_smile_01.anim", 3797),
            ("animation_char/asagi_older1/ani_story/ani_face_asagi_story_smile_01.anim", 3775)])
        for key in table:                               # ... and Action Taimanin's reader takes them as its own
            found = asc.STORY_CLIP.search(key)
            self.assertEqual((found.group("who"), found.group("name")), ("asagi", "smile"))


class MaterialTests(unittest.TestCase):
    def test_families(self):
        self.assertEqual(tcs.family("eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline OutlineBlending"), "tcp2")
        self.assertEqual(tcs.family("eTOYLab/Toony Colors Pro 2/Mobile"), "tcp2")
        self.assertEqual(tcs.family("Shader Forge/eye_unlit_mask_togray"), "eye")
        self.assertEqual(tcs.family("Mobile/Particles/Alpha Blended"), "particle")
        for shader in ("Curved/Curved_BG", "eTOYLab/bg_default", "Mobile/Unlit (Supports Lightmap)", "Standard",
                       "Legacy Shaders/Reflective/Diffuse Brightness Control", ""):
            self.assertEqual(tcs.family(shader), "background", shader)
        self.assertEqual(tcs.family("etoylab_effect/fx_sea02"), "other")

    @staticmethod
    def tex(name):
        return {"file": name, "scale": [1.0, 1.0], "offset": [0.0, 0.0]}

    def test_only_what_the_shader_declares_counts(self):
        spec = {"textures": {"_diffuse_tex": self.tex("bridge.png"), "_light_tex": self.tex("bridge_lm.png"),
                             "_glow_tex": self.tex("bridge_e.png"), "_MainTex": self.tex("dead.png")},
                "floats": {"_glow_velue": 2.0, "_glow_value": 0.0, "_MainTex_power": 5.0},
                "colors": {"_diffuse_color": [1.0, 0.5, 1.0, 1.0], "_glow_color": [0.0, 0.418, 1.0, 1.0],
                           "_Color": [0.1, 0.1, 0.1, 1.0]},
                "declared": ["_diffuse_color", "_diffuse_tex", "_light_tex", "_glow_velue", "_glow_tex", "_glow_color"]}
        hints = tcs.background_hints(spec)
        self.assertEqual((hints["base_slot"], hints["light_slot"], hints["glow_slot"]), ("_diffuse_tex", "_light_tex", "_glow_tex"))
        self.assertEqual((hints["base_map"], hints["tint"]), ("bridge.png", [1.0, 0.5, 1.0, 1.0]))   # not x the dead power
        self.assertEqual((hints["glow_color"], hints["glow_strength"]), ([0.0, 0.418, 1.0], 2.0))

    def test_a_second_slot_with_the_same_picture_adds_nothing(self):
        spec = {"textures": {"_diffuse_tex": self.tex("truck.png"), "_glow_tex": self.tex("truck.png"),
                             "_light_tex": self.tex("truck.png")},
                "floats": {"_glow_velue": 1.0}, "colors": {}, "declared": []}
        hints = tcs.background_hints(spec)
        self.assertEqual((hints["base_slot"], hints["light_slot"], hints["glow_slot"]), ("_diffuse_tex", None, None))
        self.assertEqual(hints["tint"], [1.0, 1.0, 1.0, 1.0])

    def test_a_stripped_material_takes_what_was_found_by_name(self):
        spec = {"textures": {"_MainTex": self.tex("tex_asagi_build01.png"), "_LightMap": self.tex("tex_asagi_build01_lm.png"),
                             "_Emission": self.tex("tex_asagi_build01_e.png")}, "floats": {}, "colors": {}, "declared": []}
        hints = tcs.background_hints(spec)
        self.assertEqual((hints["base_slot"], hints["light_slot"], hints["glow_slot"]), ("_MainTex", "_LightMap", "_Emission"))
        self.assertEqual(hints["glow_strength"], 1.0)
        zero = dict(spec, floats={"_Emission_power": 0.0})
        self.assertIsNone(tcs.background_hints(zero)["glow_slot"])                       # a glow of strength 0: none

    def test_the_light_map_lies_on_the_second_uv_set_when_all_have_one(self):
        materials = {"a": {"hints": {"light_slot": "_light_tex"}}, "b": {"hints": {"light_slot": "_LightMap"}},
                     "c": {"hints": {"light_slot": None}}}
        parts = [{"materials": ["a", "c"], "uv_sets": ["uv0", "uv1"]}, {"materials": ["b"], "uv_sets": ["uv0", "uv1"]},
                 {"materials": ["b", None], "uv_sets": ["uv0"]}]
        tcs.light_map_uv(parts, materials)
        self.assertEqual(materials["a"]["hints"]["light_uv"], "UV1")
        self.assertEqual(materials["b"]["hints"]["light_uv"], "UVMap")                  # one of its parts has no second set
        self.assertNotIn("light_uv", materials["c"]["hints"])

    def test_half_float_pictures(self):
        values = np.array([[[0.25, 0.5, 2.0, 1.0], [0.0, 1.0, 7.5, 1.0]],
                           [[1.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0]]], dtype="<f2")   # rows bottom-up, as Unity keeps them
        image = tcs.float_image(2, 2, 17, values.tobytes())
        self.assertEqual(image.size, (2, 2))
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))                           # the upper row is the file's last
        self.assertEqual(image.getpixel((0, 1)), (64, 128, 255))                        # 2.0 is cut off at 1
        self.assertEqual(image.getpixel((1, 1)), (0, 255, 255))
        self.assertIsNone(tcs.float_image(4, 4, 17, values.tobytes()))                  # too little data
        self.assertEqual(tcs.float_image(2, 2, 20, values.astype("<f4").tobytes()).getpixel((1, 0)), (0, 0, 255))


class ExportTests(unittest.TestCase):
    def test_what_is_no_character_gets_no_turntable_and_no_dance(self):
        a = argparse.Namespace(turntable=True, no_pmx_preview=False, xps=True, pmx=True)
        self.assertIs(export_model.converting({"category": "character"}, a), a)
        prop = export_model.converting({"category": "prop"}, a)
        self.assertEqual((prop.turntable, prop.no_pmx_preview, prop.xps, prop.pmx), (False, True, True, True))
        self.assertTrue(a.turntable)                                                     # the options themselves stay

    def test_the_game_set_leaves_the_leftovers_out(self):
        self.assertEqual(set(export_model.GAME_SET) & {"set", "raw", "part", "unit", "effect", "director"}, set())
        self.assertTrue(set(export_model.GAME_SET) <= set(tcc.CATEGORY_ORDER))
        self.assertEqual(set(tcc.CATEGORY_ZH), set(tcc.CATEGORY_ORDER))
        self.assertEqual(len([float(v) for v in export_model.PREVIEW_VIEW.split(",")]), 3)


class GalleryTests(unittest.TestCase):
    def test_the_manual_says_how_to_export_a_model(self):
        page = make_gallery.howto(r"E:\out", {"total": 276, "raw": 221})
        for piece in ("最短的路", "第 0 步", "第 1 步", "第 2 步", "第 3 步", "出问题时", "手工路线",
                      "python export_model.py prf_asagi_costume_1 --xps --pmx --turntable", "python list_models.py --html",
                      "221 个几乎都只有默认材质的原始模型", r"E:\out\_meta\exports.json",
                      r"building E:\out\Asagi\blend\prf_asagi_costume_1\prf_asagi_costume_1.blend",
                      "done: 1 built, 0 skipped, 0 failed", "按名字猜的"):
            self.assertIn(piece, page)
        self.assertNotIn("{", page)                                                      # every field is filled
        for tag in ("details", "table", "ol", "ul", "pre", "div"):
            self.assertEqual(page.count("<" + tag), page.count("</%s>" % tag), tag)

    def test_the_page(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = os.path.join(tmp.name, "export")
        asagi = tcc.model_from_path("unit_art/model/asagi/prf_asagi_costume_1")
        truck = tcc.model_from_path("bike/background/prf_truck_transportation")
        raw = tcc.model_from_path("bike/background/stage_downtown/fbx_downtown_building01")
        for model, formats in ((asagi, ["blend", "xps", "pmx"]), (truck, ["blend"]), (raw, [])):
            model.update(skinned=1, rigid=0, exported=formats, details={"vertices": 100, "triangles": 50})
        folder = tcc.tc.model_dir(asagi, root, "blend")
        os.makedirs(folder)
        open(os.path.join(folder, "prf_asagi_costume_1_preview.png"), "w").close()
        tcc.tc.save_json(os.path.join(root, "_meta", "exports.json"), {
            "prf_asagi_costume_1": {"vertices": 9323, "faces": 13773, "bones": 102, "materials_built": {"a": "toon"},
                                    "pmx_report": {"bones": 196, "rigid_bodies": 24, "vertex_morphs": ["a"] * 37}},
            "prf_truck_transportation": {"vertices": 4702, "guessed_materials": ["m"],
                                         "pmx_report": {"bones": 4, "rigid_bodies": 0, "plain_rig": "no legs"}}})
        out = make_gallery.build([raw, truck, asagi], root, os.path.join(tmp.name, "page.html"))
        with open(out, encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn("已导出（2）", page)
        self.assertLess(page.index('<div class="title">prf_asagi_costume_1'), page.index('<div class="title">prf_truck_transportation'))
        self.assertIn("pmx：骨骼 196，刚体 24，表情 37 个", page)
        self.assertIn("不是人形", page)
        self.assertIn("1 个材质的贴图是按名字猜的", page)
        self.assertIn('<span class="chip" title="bike/background/stage_downtown/fbx_downtown_building01 · 未导出 · 100 顶点 / 50 三角面">', page)
        self.assertEqual(page.count('class="chip done"'), 2)
        self.assertIn("prf_asagi_costume_1_preview.png", page)


if __name__ == "__main__":
    unittest.main()
