"""Offline tests of the Action Taimanin scripts (no game files, no Blender):

    python -m unittest discover -s tests
"""
import os
import struct
import sys
import tempfile
import unittest

import lz4.block
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ataimanin_anim as aa  # noqa: E402
import ataimanin_common as ac  # noqa: E402
import ataimanin_scene as asc  # noqa: E402
import tsquad_scene as ts  # noqa: E402


def make_bundle(path, nodes, block=1000, stored=()):
    """A UnityFS file like the game's: block table first, LZ4 blocks of `block` bytes, 16-byte alignment.
    nodes: [(name, bytes)]; stored: indices of blocks kept uncompressed."""
    data = b"".join(payload for _name, payload in nodes)
    chunks = [data[i:i + block] for i in range(0, len(data), block)]
    packed = [c if i in stored else lz4.block.compress(c, store_size=False) for i, c in enumerate(chunks)]
    info = b"\0" * 16 + struct.pack(">I", len(chunks))
    for i, (raw, comp) in enumerate(zip(chunks, packed)):
        info += struct.pack(">IIH", len(raw), len(comp), 0 if i in stored else 3)
    info += struct.pack(">I", len(nodes))
    offset = 0
    for name, payload in nodes:
        info += struct.pack(">qqI", offset, len(payload), 4) + name.encode() + b"\0"
        offset += len(payload)
    packed_info = lz4.block.compress(info, store_size=False)
    head = b"UnityFS\0" + struct.pack(">I", 8) + b"5.x.x\0" + b"2022.3.62f2\0"
    head += struct.pack(">qIII", 0, len(packed_info), len(info), 0x243)
    head += b"\0" * (-len(head) % 16)
    body = head + packed_info
    body += b"\0" * (-len(body) % 16)
    with open(path, "wb") as fh:
        fh.write(body + b"".join(packed))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        rng = np.random.default_rng(7)
        self.first = bytes(rng.integers(0, 4, 2500, dtype=np.uint8))       # compressible
        self.second = bytes(rng.integers(0, 256, 3300, dtype=np.uint8))
        self.path = os.path.join(self.dir.name, "model_test")
        make_bundle(self.path, [("CAB-abc", self.first), ("CAB-abc.resS", self.second)], stored=(4,))

    def test_directory(self):
        bundle = ac.Bundle(self.path)
        self.addCleanup(bundle.close)
        self.assertEqual(bundle.engine, "2022.3.62f2")
        self.assertEqual(bundle.nodes, {"CAB-abc": (0, 2500), "CAB-abc.resS": (2500, 3300)})
        self.assertEqual(len(bundle.blocks), 6)
        self.assertEqual(bundle.blocks[4][2], 0)                           # the stored block

    def test_reads_across_blocks(self):
        bundle = ac.Bundle(self.path)
        self.addCleanup(bundle.close)
        whole = self.first + self.second
        self.assertEqual(bundle.read(0, 2500), self.first)
        self.assertEqual(bundle.read(2500, 3300), self.second)
        for offset, size in ((999, 2), (1000, 1000), (2400, 250), (3990, 1500), (5799, 1)):
            self.assertEqual(bundle.read(offset, size), whole[offset:offset + size], (offset, size))

    def test_lazy_node_reads_like_a_stream(self):
        bundle = ac.Bundle(self.path)
        self.addCleanup(bundle.close)
        node = ac.LazyNode(bundle, *bundle.nodes["CAB-abc.resS"])
        node.Position = 100
        self.assertEqual(node.read_bytes(50), self.second[100:150])
        self.assertEqual(node.read_bytes(10), self.second[150:160])        # the position moves on

    def test_an_encrypted_file_is_refused(self):
        path = os.path.join(self.dir.name, "game")
        with open(path, "wb") as fh:
            fh.write(bytes(range(200)))
        with self.assertRaises(ValueError):
            ac.Bundle(path)


class ModelListTests(unittest.TestCase):
    CHARS = ("asagi", "c_yukikaze", "yukikaze", "sakura")

    def model(self, key):
        return ac.model_from_key(key, self.CHARS)

    def test_figure_with_costume(self):
        m = self.model("unit/figure/asagi_costume_29_f/asagi_costume_29_f.prefab")
        self.assertEqual((m["id"], m["category"], m["group"], m["costume"]), ("asagi_costume_29_f", "figure", "Asagi", 29))
        self.assertEqual(m["name"], "Asagi costume 29")

    def test_the_longest_character_name_wins(self):
        m = self.model("unit/figure/c_yukikaze_costume_2_f/c_yukikaze_costume_2_f.prefab")
        self.assertEqual((m["character"], m["group"], m["costume"]), ("c_yukikaze", "C_Yukikaze", 2))

    def test_figure_without_costume_number(self):
        m = self.model("unit/figure/astaroth_rabbit_f/astaroth_rabbit_f.prefab")
        self.assertEqual((m["group"], m["costume"], m["variant"]), ("Astaroth_Rabbit", None, "figure"))

    def test_game_and_lobby_units(self):
        g = self.model("unit/character/asagi_g/asagi_g.prefab")
        l = self.model("unit/character/asagi_l/asagi_l.prefab")
        self.assertEqual((g["group"], g["variant"], l["variant"]), ("Asagi", "game", "lobby"))

    def test_monsters_keep_their_own_group(self):
        m = self.model("unit/monster/ghoul_h/ghoul_h.prefab")
        self.assertEqual((m["category"], m["group"], m["character"]), ("monster", "Ghoul_H", ""))

    def test_other_assets_are_not_models(self):
        self.assertIsNone(self.model("unit/figure/asagi_costume_1_f/asagi_costume_1_f.controller"))
        self.assertIsNone(self.model("unit/shadow.prefab"))

    def test_find(self):
        models = [self.model("unit/figure/asagi_costume_%d_f/asagi_costume_%d_f.prefab" % (n, n)) for n in (1, 2)]
        models.append(self.model("unit/figure/sakura_costume_1_f/sakura_costume_1_f.prefab"))
        self.assertEqual([m["id"] for m in ac.find_models(models, ["asagi"])], ["asagi_costume_1_f", "asagi_costume_2_f"])
        self.assertEqual([m["id"] for m in ac.find_models(models, ["*_costume_1_f"])],
                         ["asagi_costume_1_f", "sakura_costume_1_f"])
        with self.assertRaises(SystemExit):
            ac.find_models(models, ["nobody"])


class MaterialHintTests(unittest.TestCase):
    def test_shader_families(self):
        self.assertEqual(asc.family("eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline OutlineBlending"), "tcp2")
        self.assertEqual(asc.family("UnityChanToonShader/Mobile/Toon_ShadingGradeMap"), "uts2")
        self.assertEqual(asc.family("Shader Forge/eye_unlit_mask_togray"), "eye")
        self.assertEqual(asc.family("Mobile/Particles/Alpha Blended"), "particle")
        self.assertEqual(asc.family("Standard"), "other")

    def test_tcp2_shadow_and_outline(self):
        spec = {"shader": "eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline OutlineBlending",
                "textures": {"_MainTex": {"file": "a.png"}}, "floats": {"_Outline": 0.1},
                "colors": {"_SColor": [0.5, 0.4, 0.6, 0.5], "_OutlineColor": [0.2, 0.1, 0.3, 0.8]}}
        hints = asc.hints(spec)
        self.assertEqual(hints["base_map"], "a.png")
        np.testing.assert_allclose(hints["shade"], [0.75, 0.7, 0.8])        # lerp(1, _SColor, _SColor.a)
        self.assertEqual(hints["outline"]["width_mm"], 1.0)                 # _Outline x 0.01 m
        self.assertEqual(hints["outline"]["alpha"], 0.8)

    def test_tcp2_without_an_outline_pass(self):
        spec = {"shader": "eTOYLab/Toony Colors Pro 2/Mobile", "textures": {}, "floats": {"_Outline": 1.0}, "colors": {}}
        self.assertNotIn("outline", asc.hints(spec))

    def test_uts2_shade_sphere_and_outline(self):
        spec = {"shader": "UnityChanToonShader/Mobile/Toon_ShadingGradeMap",
                "textures": {"_MainTex": {"file": "b.png"}, "_MatCap_Sampler": {"file": "mc.png"},
                             "_Set_MatcapMask": {"file": "spec.png"}},
                "floats": {"_Use_BaseAs1st": 1.0, "_MatCap": 1.0, "_Is_BlendAddToMatCap": 1.0,
                           "_Tweak_MatcapMaskLevel": -0.1, "_Outline_Width": 1.5, "_Is_BlendBaseColor": 1.0},
                "colors": {"_BaseColor": [0.9, 0.9, 0.9, 1], "_1st_ShadeColor": [0.45, 0.9, 1.0, 1],
                           "_MatCapColor": [0.5, 0.6, 0.7, 1], "_Outline_Color": [0.1, 0.2, 0.3, 1]}}
        hints = asc.hints(spec)
        np.testing.assert_allclose(hints["shade"], [0.5, 1.0, 1.0])         # 1st shade / base, never brighter
        self.assertEqual(hints["sphere"]["mask"], {"file": "spec.png", "channel": 1})
        self.assertEqual((hints["sphere"]["mode"], hints["sphere"]["level"]), ("add", -0.1))
        self.assertEqual((hints["outline"]["width_mm"], hints["outline"]["blend_base"]), (1.5, True))

    def test_uts2_without_outline_variant(self):
        spec = {"shader": "UnityChanToonShader/Mobile/Toon_ShadingGradeMap_Without_Outline", "textures": {},
                "floats": {"_Outline_Width": 1.0}, "colors": {}}
        self.assertNotIn("outline", asc.hints(spec))


class RigTests(unittest.TestCase):
    def test_breast_pair_by_shape(self):
        spine = (0.0, 1.3, 0.0)
        chains = [
            {"bone": "Bone005", "parent": "Bip001 Spine1", "pos": (0.057, 1.38, 0.08), "parent_pos": spine, "leaf": True},
            {"bone": "Bone006", "parent": "Bip001 Spine1", "pos": (-0.057, 1.38, 0.08), "parent_pos": spine, "leaf": True},
            {"bone": "Bone136", "parent": "Bip001 Head", "pos": (0.0, 1.6, -0.1), "parent_pos": (0, 1.6, 0), "leaf": False},
            {"bone": "Bone_wing_L", "parent": "Bip001 Spine1", "pos": (0.2, 1.4, -0.1), "parent_pos": spine, "leaf": True},
            {"bone": "Bone_wing_R", "parent": "Bip001 Spine1", "pos": (-0.2, 1.4, -0.1), "parent_pos": spine, "leaf": True},
        ]
        self.assertEqual(asc.breast_pair(chains), ["Bone005", "Bone006"])
        self.assertEqual(asc.breast_pair(chains, forward=-1.0), ["Bone_wing_L", "Bone_wing_R"])   # facing -Z

    def test_breast_pair_by_name(self):
        chains = [{"bone": "Bone_L_Bust", "parent": "X", "pos": (0, 0, 0), "leaf": False},
                  {"bone": "Bone_R_Bust", "parent": "X", "pos": (0, 0, 0), "leaf": False}]
        self.assertEqual(asc.breast_pair(chains), ["Bone_L_Bust", "Bone_R_Bust"])

    def test_of_two_nodes_named_alike_the_one_with_skin_is_the_bone(self):
        rig = [(1, "Bone_Eyeball_L", "Bone_Eyeball_L"), (2, "Bone_Eyeball_R", "Bone_Eyeball_R"),
               (3, "Point_Eyeball_L", "Point_Eyeball_L"), (4, "Point_Eyeball_R", "Point_Eyeball_R"),
               (5, "Bone_Face_Lip_UL", "Bone_Face_Lip_UL")]
        skinned = {"Bone_Eyeball_L", "Bone_Eyeball_R", "Bone_Face_Lip_UL"}
        self.assertEqual(asc.by_side(rig, asc.EYEBALL, skinned), {"L": 1, "R": 2})
        self.assertEqual(asc.by_side(list(reversed(rig)), asc.EYEBALL, skinned), {"L": 1, "R": 2})   # in any order
        self.assertEqual(asc.by_side(rig, asc.EYEBALL, set()), {"L": 1, "R": 2})                     # no skin: the first
        self.assertEqual(asc.by_side(rig, asc.LIP, skinned), {"UL": 5})

    def test_no_pair(self):
        self.assertEqual(asc.breast_pair([{"bone": "Bone136", "parent": "Bip001 Head", "pos": (0, 0, 0), "leaf": False}]), [])

    def test_body_bones_pattern(self):
        import re

        body = re.compile(asc.BODY_BONES)
        for name in ("Bone_Face_Lip_U", "Bone_Eyeball_L", "Bone_Teeth_D", "Bone_Tongue01", "root_face", "Bone_face"):
            self.assertTrue(body.match(name), name)
        for name in ("Bone136", "Bone_Fr_hair00", "Bone_hair06", "Bone005"):
            self.assertFalse(body.match(name), name)


def streamed_words(frames):
    """[(time, [(curve, c0, c1, c2, value)])] -> the uint32 words Unity stores."""
    data = b""
    for time, keys in frames:
        data += struct.pack("<fi", time, len(keys))
        for curve, c0, c1, c2, value in keys:
            data += struct.pack("<iffff", curve, c0, c1, c2, value)
    return list(struct.unpack("<%dI" % (len(data) // 4), data))


class ClipTests(unittest.TestCase):
    """Three position curves streamed, a rotation of one dense curve + three constants."""

    def setUp(self):
        self.lip, self.jaw = aa.path_hash("root_face/Bone_face/Bone_Face_Lip_L"), aa.path_hash("root_face/Bone_face")
        words = streamed_words([
            (float("-inf"), [(0, 0.0, 0.0, 0.0, 1.0), (1, 0.0, 0.0, 0.0, 2.0), (2, 0.0, 0.0, 0.0, 3.0)]),
            (0.0, [(0, 0.0, 0.0, 2.0, 1.0)]),                       # x: 1 + 2 t
            (1.0, [(0, 0.0, 0.0, 0.0, 3.0), (2, 0.0, 0.0, 0.0, 5.0)]),
        ])
        self.tree = {
            "m_Name": "ani_face_test", "m_SampleRate": 30.0,
            "m_MuscleClip": {"m_StartTime": 0.0, "m_StopTime": 1.0, "m_Clip": {"data": {
                "m_StreamedClip": {"data": words, "curveCount": 3},
                "m_DenseClip": {"m_FrameCount": 3, "m_CurveCount": 1, "m_SampleRate": 2.0, "m_BeginTime": 0.0,
                                "m_SampleArray": [0.0, 0.5, 1.0]},
                "m_ConstantClip": {"data": [0.0, 0.0, 1.0]}}}},
            "m_ClipBindingConstant": {"genericBindings": [
                {"path": self.lip, "attribute": 1, "typeID": 4}, {"path": self.jaw, "attribute": 2, "typeID": 4}]},
        }

    def test_path_hash_is_crc32(self):
        import zlib

        self.assertEqual(aa.path_hash("root_face"), zlib.crc32(b"root_face"))

    def test_streamed_keys_hold_then_follow_their_cubic(self):
        clip = aa.Clip(self.tree)
        self.assertEqual(clip.sample(0.0)[self.lip]["position"], (1.0, 2.0, 3.0))
        np.testing.assert_allclose(clip.sample(0.5)[self.lip]["position"], (2.0, 2.0, 3.0))
        np.testing.assert_allclose(clip.sample(1.0)[self.lip]["position"], (3.0, 2.0, 5.0))

    def test_dense_and_constant_curves_follow_the_streamed_ones(self):
        clip = aa.Clip(self.tree)
        np.testing.assert_allclose(clip.sample(0.25)[self.jaw]["rotation"], (0.25, 0.0, 0.0, 1.0))
        np.testing.assert_allclose(clip.sample(9.0)[self.jaw]["rotation"], (1.0, 0.0, 0.0, 1.0))     # past the end: held

    def test_frame_times(self):
        times = aa.Clip(self.tree).times()
        self.assertEqual(len(times), 31)
        self.assertEqual((times[0], times[-1]), (0.0, 1.0))


class PoseTests(unittest.TestCase):
    def test_a_keyed_value_replaces_only_its_own_part(self):
        rest = ts.trs_matrix((0.1, 0.2, 0.3), (0.0, 0.0, 0.0, 1.0), (1.0, 2.0, 3.0))
        moved = asc.posed_local(rest, {"position": (0.5, 0.2, 0.3)})
        np.testing.assert_allclose(moved[:3, 3], (0.5, 0.2, 0.3))
        np.testing.assert_allclose(moved[:3, :3], rest[:3, :3])
        half = np.sqrt(0.5)
        turned = asc.posed_local(rest, {"rotation": (0.0, 0.0, half, half)})          # 90 degrees about z
        np.testing.assert_allclose(turned[:3, :3], np.array([[0, -2, 0], [1, 0, 0], [0, 0, 3]]), atol=1e-9)
        np.testing.assert_allclose(turned[:3, 3], rest[:3, 3])
        scaled = asc.posed_local(rest, {"scale": (2.0, 2.0, 2.0)})
        np.testing.assert_allclose(scaled[:3, :3], np.eye(3) * 2.0)
        self.assertIs(asc.posed_local(rest, {}), rest)

    def test_skin_deltas(self):
        vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        indices = np.array([[0, 1], [0, 1], [1, 0]])
        weights = np.array([[1.0, 0.0], [0.5, 0.5], [2.0, 0.0]])                     # the last row is not normalised
        change = np.zeros((2, 4, 4))
        change[0, :3, 3] = (0.01, 0.0, 0.0)                                           # bone 0 slides 1 cm
        delta = asc.skin_deltas(vertices, indices, weights, change)
        np.testing.assert_allclose(delta, [[0.01, 0, 0], [0.005, 0, 0], [0, 0, 0]], atol=1e-12)

    def test_story_clip_names(self):
        match = asc.STORY_CLIP.search("animation_char/asagi/ani_story/ani_face_asagi_story_angry_01.anim")
        self.assertEqual((match.group("kind"), match.group("who"), match.group("name"), match.group("n")),
                         ("face", "asagi", "angry", "01"))
        match = asc.STORY_CLIP.search("animation_char/c_yukikaze/ani_story/ani_mouth_c_yukikaze_story_idle01.anim")
        self.assertEqual((match.group("kind"), match.group("who"), match.group("name")), ("mouth", "c_yukikaze", "idle"))
        self.assertIsNone(asc.STORY_CLIP.search("animation_char/asagi/ani_lobby/ani_face_asagi_lobby_greet.anim"))
        self.assertTrue(asc.FACE_ROOT.match("fbx_asagi_face"))
        self.assertFalse(asc.FACE_ROOT.match("fbx_asagi_face_none"))


class MadeShapeTests(unittest.TestCase):
    """The shapes the game has no clip for (lip-bone mouths, looks) and what the PMX converter is told."""

    def test_look_turn_carries_the_front_of_the_eye_the_asked_way(self):
        head = np.array([0.02, 1.56, -0.04])
        for forward in (1.0, -1.0):
            front = np.append(head + np.array([0.0, 0.0, forward * 0.038]), 1.0)
            up = (asc.look_turn(head, forward, (0.0, 1.0, 0.0), 5.0) @ front)[:3] - front[:3]
            self.assertAlmostEqual(up[1], 0.038 * np.sin(np.radians(5.0)), places=6)
            self.assertAlmostEqual(up[0], 0.0, places=9)
            side = (asc.look_turn(head, forward, (-1.0, 0.0, 0.0), 9.0) @ front)[:3] - front[:3]
            self.assertLess(side[0], -0.005)
            self.assertAlmostEqual(side[1], 0.0, places=9)
        np.testing.assert_allclose(asc.look_turn(head, 1.0, (0.0, 1.0, 0.0), 5.0) @ np.append(head, 1.0),
                                   np.append(head, 1.0), atol=1e-12)        # the bone's head stays

    def test_mouth_moves_mirror_and_scale_with_the_mouth(self):
        lips = {"L": (0.014, 1.5, 0.08), "R": (-0.014, 1.5, 0.08), "U": (0.0, 1.502, 0.085), "D": (0.0, 1.498, 0.085),
                "UL": (0.008, 1.501, 0.083), "UR": (-0.008, 1.501, 0.083)}
        moves = asc.mouth_moves(lips, asc.MOUTH_POSES["mouth_smile"], 1.0)
        np.testing.assert_allclose(moves["L"], [0.0012, 0.0024, -0.0004])
        np.testing.assert_allclose(moves["R"], [-0.0012, 0.0024, -0.0004])     # outward is away from the centre
        np.testing.assert_allclose(moves["D"], [0.0, 0.0003, 0.0])
        self.assertNotIn("U", moves)                                           # the smile leaves the upper lip
        wide = {k: (v[0] * 2.0, v[1], v[2]) for k, v in lips.items()}
        np.testing.assert_allclose(asc.mouth_moves(wide, asc.MOUTH_POSES["mouth_smile"], -1.0)["L"],
                                   [0.0024, 0.0048, 0.0008])                   # twice the mouth, facing -Z

    def test_eye_closure_is_measured_on_the_lids(self):
        bones = ["Bone_face", "Bone_Face_Eye_L_Shape_U_Mid", "Bone_Face_Eye_L_Shape_In"]
        xs = np.linspace(0.02, 0.04, 7)
        upper = np.array([[x, 1.010, 0.08] for x in xs])
        lower = np.array([[x, 1.000, 0.08] for x in xs])
        vertices = np.concatenate([upper, lower, [[0.0, 1.05, 0.08]]])
        indices = np.zeros((15, 4), dtype=np.int32)
        indices[:7, 0], indices[7:14, 0] = 1, 2
        weights = np.zeros((15, 4))
        weights[:, 0] = 1.0

        def closure(up, low):
            delta = np.zeros((15, 3))
            delta[:7, 1], delta[7:14, 1] = up, low
            return asc.eye_closure(vertices, indices, weights, bones, delta)

        self.assertEqual(list(closure(-0.010, 0.0)), ["L"])            # no lid bones on the right: no verdict
        self.assertAlmostEqual(closure(-0.010, 0.0)["L"], 1.0)         # a blink: the upper lid comes down
        self.assertAlmostEqual(closure(-0.001, 0.008)["L"], 0.9)       # "^ ^": closed from below
        self.assertAlmostEqual(closure(-0.012, 0.0)["L"], 1.0)         # lids that overlap are shut, not more
        self.assertAlmostEqual(closure(0.002, 0.0)["L"], -0.2)         # wide open

    def test_recipes_need_their_shapes(self):
        have = {"closed_eyes", "mouth_talk_a", "smile_eyes", "mouth_wide", "angry_brows", "up_eyes", "smile_face"}
        recipes, drop = asc.morph_recipes(have, True)
        names = [r[0] for r in recipes]
        self.assertEqual(names, ["笑い", "ウィンク", "ウィンク右", "い", "え", "怒り"])
        self.assertEqual(recipes[1][3], [["smile_eyes", 1.0, "L"]])
        self.assertEqual(sorted(drop), ["angry_brows", "mouth_wide", "smile_eyes", "up_eyes"])    # never a game face
        self.assertEqual([r[0] for r in asc.morph_recipes(have, False)[0]], ["い", "え", "怒り"])


if __name__ == "__main__":
    unittest.main()
