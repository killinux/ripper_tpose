"""Offline tests for the Taimanin Squad scripts (no game and no Blender needed; UnityPy, lz4, numpy and
Pillow are imported).

    python -m unittest discover -s scripts/taimaninsquad/tests      # from the repo root
"""
import base64
import json
import math
import os
import re
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import dance_video  # noqa: E402
import export_backgrounds as eb  # noqa: E402
import tsquad_common as tc  # noqa: E402
import tsquad_scene as ts  # noqa: E402

BUNDLE_PROVIDER = "UnityEngine.ResourceManagement.ResourceProviders.AssetBundleProvider"
ASSET_PROVIDER = "UnityEngine.ResourceManagement.ResourceProviders.BundledAssetProvider"


def make_catalog(bundles, assets):
    """A minimal Addressables 1.x catalog.  bundles: [file name]; assets: [(key, guid, type, [bundle indices])]."""
    ids, entries, keys, buckets = [], [], [], []

    def key(value):
        keys.append(value)
        buckets.append([])
        return len(keys) - 1

    types = ["Res.IAssetBundleResource"] + sorted({"UnityEngine." + a[2] for a in assets})
    for name in bundles:
        ids.append("{RuntimePath}\\StandaloneWindows64\\" + name)
        k = key(name)
        buckets[k].append(len(entries))
        entries.append((len(ids) - 1, 0, -1, 0, -1, k, 0))
    for address, guid, kind, deps in assets:
        dep_key = key(hash(address) & 0x7FFFFFFF)
        buckets[dep_key].extend(deps)                   # bundle entry i is entry i
        ids.append(guid)
        k = key(address)
        buckets[k].append(len(entries))
        entries.append((len(ids) - 1, 1, dep_key, 0, -1, k, types.index("UnityEngine." + kind)))
    key_blob, offsets = b"", []
    for value in keys:
        offsets.append(len(key_blob))
        if isinstance(value, str):
            raw = value.encode("ascii")
            key_blob += b"\x00" + struct.pack("<i", len(raw)) + raw
        else:
            key_blob += b"\x04" + struct.pack("<i", value)
    bucket_blob = struct.pack("<i", len(keys))
    for off, items in zip(offsets, buckets):
        bucket_blob += struct.pack("<ii", off, len(items)) + struct.pack("<%di" % len(items), *items)
    entry_blob = struct.pack("<i", len(entries)) + b"".join(struct.pack("<7i", *e) for e in entries)
    return {
        "m_InternalIds": ids, "m_ProviderIds": [BUNDLE_PROVIDER, ASSET_PROVIDER],
        "m_resourceTypes": [{"m_ClassName": t} for t in types],
        "m_KeyDataString": base64.b64encode(key_blob).decode(),
        "m_BucketDataString": base64.b64encode(bucket_blob).decode(),
        "m_EntryDataString": base64.b64encode(entry_blob).decode(),
        "m_ExtraDataString": "",
    }


ART, MAIN, ICONS = "localunit_aos_assets_24_kirara_aa.bundle", "localunit_assets_24_kirara_bb.bundle", "uiicon_aos_assets_icon_char_cc.bundle"
ASSETS = [
    {"key": "24_Kirara/Unit/prf_24.prefab", "guid": "g24", "type": "GameObject", "bundle": ART},
    {"key": "24_Kirara/Unit/prf_24_LOD1.prefab", "guid": "g24l", "type": "GameObject", "bundle": ART},
    {"key": "24_Kirara/Animation/24_kirara_idle01.anim", "guid": "a1", "type": "AnimationClip", "bundle": MAIN},
    {"key": "24_Kirara/Art/Materials/tex_d_hair_24.png", "guid": "t1", "type": "Texture2D", "bundle": ART},
    {"key": "24_Kirara/Weapon/Prefab/prf_weapon_24_1_L.prefab", "guid": "w241l", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Prefab/prf_weapon_24_0_L.prefab", "guid": "w240l", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Prefab/prf_weapon_24_0_L_LOD1.prefab", "guid": "w240ll", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Prefab/prf_weapon_24_0_R2.prefab", "guid": "w240r2", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Prefab/prf_weapon_24_2_B.prefab", "guid": "w242b", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Art/fbx_weapon_24_0_L.fbx", "guid": "w24fbx", "type": "GameObject", "bundle": MAIN},
    {"key": "24_Kirara/Weapon/Art/fbx_weapon_24_0_L.fbx", "guid": "w24mesh", "type": "Mesh", "bundle": MAIN},
    {"key": "B_12_Wednesday/Weapon/Prefab/prf_weapon_b_12_0_O.prefab", "guid": "wb12", "type": "GameObject", "bundle": "mb12.bundle"},
    {"key": "16_Asuka/Unit/prf_16.prefab", "guid": "g16", "type": "GameObject", "bundle": "a16.bundle"},
    {"key": "16_Asuka/Unit/prf_16_LOD1.prefab", "guid": "g16l", "type": "GameObject", "bundle": "a16.bundle"},
    {"key": "16_Asuka/Unit/prf_16black.prefab", "guid": "g16b", "type": "GameObject", "bundle": "a16.bundle"},
    {"key": "58_Yuphiesophie/Unit/prf_58_sophie.prefab", "guid": "g58s", "type": "GameObject", "bundle": "a58.bundle"},
    {"key": "184_Xps11a/Unit/prf_184_LOD.prefab", "guid": "g184l", "type": "GameObject", "bundle": "a184.bundle"},
    {"key": "253_Asagi/Unit/prf_253.prefab", "guid": "g253", "type": "GameObject", "bundle": "a253.bundle"},
    {"key": "130_Orc1/Unit/prf_130.prefab", "guid": "g130", "type": "GameObject", "bundle": "a130.bundle"},
    {"key": "300_Kaliya/Unit/prf_300.prefab", "guid": "g300", "type": "GameObject", "bundle": "a300.bundle"},
    {"key": "B_12_Wednesday/Unit/prf_b_12.prefab", "guid": "gb12", "type": "GameObject", "bundle": "ab12.bundle"},
    {"key": "B_12_Wednesday/Unit/prf_b_12_LOD1.prefab", "guid": "gb12l", "type": "GameObject", "bundle": "ab12.bundle"},
    {"key": "998_Prologuemob/Unit/prf_998.prefab", "guid": "g998", "type": "GameObject", "bundle": "a998.bundle"},
    {"key": "Icon/Char/MainSlot/24_Kirara.png", "guid": "i24m", "type": "Texture2D", "bundle": ICONS},
    {"key": "Icon/Char/Portal/24_Kirara.png", "guid": "i24p", "type": "Texture2D", "bundle": ICONS},
    {"key": "Icon/Char/MainSlot/130_Orc1.png", "guid": "i130", "type": "Texture2D", "bundle": ICONS},
    {"key": "Effect/FX_Resources/Materials/x.mat", "guid": "m1", "type": "Material", "bundle": "fx.bundle"},
]


class CatalogTests(unittest.TestCase):
    def test_parse_catalog(self):
        cat = make_catalog([ART, "squadtoonshader_assets_all_dd.bundle", MAIN], [
            ("24_Kirara/Unit/prf_24.prefab", "c5090ba5", "GameObject", [0, 1, 2]),
            ("24_Kirara/Animation/24_kirara_run.anim", "a098d5ed", "AnimationClip", [2]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalog.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(cat, fh)
            assets = tc.parse_catalog(path)
        self.assertEqual(assets, [
            {"key": "24_Kirara/Unit/prf_24.prefab", "guid": "c5090ba5", "type": "GameObject", "bundle": ART},
            {"key": "24_Kirara/Animation/24_kirara_run.anim", "guid": "a098d5ed", "type": "AnimationClip", "bundle": MAIN},
        ])

    def test_bundle_directory(self):
        import lz4.block

        info = b"\0" * 16 + struct.pack(">i", 1) + struct.pack(">IIH", 100, 60, 3) + struct.pack(">i", 2)
        for offset, size, name in ((0, 80, "CAB-0123"), (80, 20, "CAB-0123.resS")):
            info += struct.pack(">qqI", offset, size, 4) + name.encode() + b"\0"
        packed = lz4.block.compress(info, store_size=False)
        head = b"UnityFS\0" + struct.pack(">I", 8) + b"5.x.x\0" + b"2022.3.62f3\0"
        head += struct.pack(">qIII", 0, len(packed), len(info), 3)
        head += b"\0" * ((16 - len(head) % 16) % 16)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.bundle")
            with open(path, "wb") as fh:
                fh.write(head + packed + b"\0" * 60)
            self.assertEqual(tc.bundle_directory(path), ["CAB-0123", "CAB-0123.resS"])
            with open(path, "wb") as fh:
                fh.write(b"NotUnity" + b"\0" * 64)
            with self.assertRaises(ValueError):
                tc.bundle_directory(path)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.models = tc.discover_models(ASSETS, self.tmp.name)
        self.by_id = {m["id"]: m for m in self.models}

    def tearDown(self):
        self.tmp.cleanup()

    def test_ids_and_lod_twins(self):
        self.assertEqual(sorted(self.by_id), ["130_orc1", "16_asuka", "16_asuka_black", "184_xps11a", "24_kirara",
                                              "253_asagi", "300_kaliya", "58_yuphiesophie_sophie", "998_prologuemob",
                                              "b_12_wednesday"])
        kirara = self.by_id["24_kirara"]
        self.assertEqual((kirara["guid"], kirara["lod1_guid"], kirara["prefab"]), ("g24", "g24l", "prf_24"))
        self.assertEqual(kirara["main_bundle"], MAIN)
        self.assertIsNone(self.by_id["16_asuka_black"]["lod1_guid"])
        self.assertEqual(self.by_id["16_asuka_black"]["name"], "Asuka Black")
        self.assertEqual(self.by_id["16_asuka_black"]["group"], "Asuka")
        self.assertEqual(self.by_id["184_xps11a"]["prefab"], "prf_184_LOD")      # the only prefab it has

    def test_weapon_prefabs(self):
        kirara = self.by_id["24_kirara"]
        self.assertEqual([(w["name"], w["grade"], w["slot"]) for w in kirara["weapons"]],
                         [("prf_weapon_24_2_B", 2, "B"), ("prf_weapon_24_0_L", 0, "L"), ("prf_weapon_24_1_L", 1, "L"),
                          ("prf_weapon_24_0_R2", 0, "R2")])           # no LOD twin, no .fbx, by slot then grade
        self.assertEqual(kirara["weapons"][1]["guid"], "w240l")
        self.assertEqual([w["name"] for w in self.by_id["b_12_wednesday"]["weapons"]], ["prf_weapon_b_12_0_O"])
        self.assertEqual(self.by_id["130_orc1"]["weapons"], [])
        pick = lambda grade: [w["name"] for w in tc.pick_weapons(kirara["weapons"], grade)]  # noqa: E731
        self.assertEqual(pick(0), ["prf_weapon_24_0_L", "prf_weapon_24_0_R2"])     # B only exists from grade 2 on
        self.assertEqual(pick(1), ["prf_weapon_24_1_L", "prf_weapon_24_0_R2"])     # R2 has no grade 1: its grade 0
        self.assertEqual(pick(2), ["prf_weapon_24_2_B", "prf_weapon_24_1_L", "prf_weapon_24_0_R2"])

    def test_categories_and_order(self):
        cats = {m["id"]: m["category"] for m in self.models}
        self.assertEqual(cats["24_kirara"], "character")
        self.assertEqual(cats["253_asagi"], "costume")
        self.assertEqual(cats["130_orc1"], "monster")
        self.assertEqual(cats["300_kaliya"], "special")
        self.assertEqual(cats["b_12_wednesday"], "boss")
        self.assertEqual(cats["998_prologuemob"], "mob")
        order = [tc.CATEGORY_ORDER.index(m["category"]) for m in self.models]
        self.assertEqual(order, sorted(order))
        self.assertEqual([m["id"] for m in self.models if m["category"] == "character"],
                         ["16_asuka", "16_asuka_black", "24_kirara", "58_yuphiesophie_sophie"])

    def test_icons(self):
        self.assertEqual(self.by_id["24_kirara"]["icon"]["guid"], "i24p")         # Portal before MainSlot
        self.assertTrue(self.by_id["24_kirara"]["playable"])
        self.assertEqual(self.by_id["130_orc1"]["icon"]["guid"], "i130")
        self.assertFalse(self.by_id["130_orc1"]["playable"])
        self.assertIsNone(self.by_id["253_asagi"]["icon"])

    def test_find_models(self):
        find = lambda *p: [m["id"] for m in tc.find_models(self.models, list(p))]  # noqa: E731
        self.assertEqual(find("24_kirara"), ["24_kirara"])
        self.assertEqual(find("24"), ["24_kirara"])
        self.assertEqual(find("12"), ["b_12_wednesday"])             # substring fallback: no unit 12 here
        self.assertEqual(find("asuka"), ["16_asuka", "16_asuka_black"])
        self.assertEqual(find("Asagi"), ["253_asagi"])
        self.assertEqual(find("16_*"), ["16_asuka", "16_asuka_black"])
        self.assertEqual(find("kira"), ["24_kirara"])
        self.assertEqual(find("kirara", "24"), ["24_kirara"])
        with self.assertRaises(SystemExit):
            find("nobody")

    def test_export_layout(self):
        kirara = self.by_id["24_kirara"]
        self.assertEqual(tc.model_dir(kirara, r"E:\x", "pmx"), os.path.join(r"E:\x", "Kirara", "pmx", "24_kirara"))
        self.assertEqual(tc.exported_formats(kirara, self.tmp.name), [])
        folder = tc.model_dir(kirara, self.tmp.name, "blend")
        os.makedirs(folder)
        open(os.path.join(folder, "24_kirara.blend"), "w").close()
        self.assertEqual(tc.exported_formats(kirara, self.tmp.name), ["blend"])

    def test_record_export_merges(self):
        tc.record_export(self.tmp.name, [{"id": "24_kirara", "blend": "a.blend", "xps": None}])
        tc.record_export(self.tmp.name, [{"id": "24_kirara", "pmx": "a.pmx"}, {"id": "1_asagi", "skipped": True}])
        data = tc.load_json(os.path.join(tc.meta_dir(self.tmp.name), "exports.json"))
        self.assertEqual(sorted(data), ["24_kirara"])
        self.assertEqual((data["24_kirara"]["blend"], data["24_kirara"]["pmx"]), ("a.blend", "a.pmx"))

    def test_record_export_drops_the_warning_of_a_stage_that_now_works(self):
        tc.record_export(self.tmp.name, [{"id": "b_12_wednesday", "blend": "a.blend", "xps": "a.xps",
                                          "warnings": ["PMX failed, log: x.log", "turntable failed, log: y.log"]}])
        tc.record_export(self.tmp.name, [{"id": "b_12_wednesday", "pmx": "a.pmx"}])     # a later, good conversion
        data = tc.load_json(os.path.join(tc.meta_dir(self.tmp.name), "exports.json"))["b_12_wednesday"]
        self.assertEqual(data["warnings"], ["turntable failed, log: y.log"])
        tc.record_export(self.tmp.name, [{"id": "b_12_wednesday", "turntable": "a.mp4"}])
        data = tc.load_json(os.path.join(tc.meta_dir(self.tmp.name), "exports.json"))["b_12_wednesday"]
        self.assertNotIn("warnings", data)
        self.assertEqual(data["xps"], "a.xps")

    def test_record_export_takes_over_a_stale_lock(self):
        os.makedirs(tc.meta_dir(self.tmp.name))
        lock = os.path.join(tc.meta_dir(self.tmp.name), "exports.json.lock")
        open(lock, "w").close()                                  # what a killed batch leaves behind
        old = os.path.getmtime(lock) - 120
        os.utime(lock, (old, old))
        tc.record_export(self.tmp.name, [{"id": "24_kirara", "blend": "a.blend"}])
        self.assertFalse(os.path.exists(lock))
        self.assertIn("24_kirara", tc.load_json(os.path.join(tc.meta_dir(self.tmp.name), "exports.json")))

    def test_is_female(self):
        kirara, orc = dict(self.by_id["24_kirara"]), dict(self.by_id["130_orc1"])
        self.assertFalse(tc.is_female(kirara))                   # no details read yet
        kirara["details"] = {"bust": True}
        orc["details"] = {"bust": False}
        self.assertTrue(tc.is_female(kirara))
        self.assertFalse(tc.is_female(orc))
        by_look = {"id": "87_torajiro", "details": {"bust": False}}
        self.assertTrue(tc.is_female(by_look))                   # no breast bones: picked by eye


class SceneMathTests(unittest.TestCase):
    def test_trs_matrix(self):
        s = np.sin(np.pi / 4)
        m = ts.trs_matrix((1.0, 2.0, 3.0), (0.0, 0.0, s, s), (2.0, 2.0, 2.0))      # 90 degrees about Z, scale 2
        np.testing.assert_allclose(m @ [1.0, 0.0, 0.0, 1.0], [1.0, 4.0, 3.0, 1.0], atol=1e-9)

    def test_skin_matrices_blend_and_normalise(self):
        shift = np.eye(4)
        shift[0, 3] = 2.0
        mesh = {"vertex_count": 3, "bone_indices": np.array([[0, 1], [1, 0], [0, 0]]),
                "weights": np.array([[0.5, 0.5], [2.0, 0.0], [0.0, 0.0]])}
        out = ts.skin_matrices(mesh, np.array([np.eye(4), shift]))
        np.testing.assert_allclose(out[:, 0, 3], [1.0, 2.0, 0.0])      # half way, all (weights renormalised), bone 0
        rigid = ts.skin_matrices({"vertex_count": 2}, np.array([shift]))
        np.testing.assert_allclose(rigid[:, 0, 3], [2.0, 2.0])         # no bone indices: rigid on the first matrix
        np.testing.assert_allclose(ts.skin_matrices({"vertex_count": 2}, np.zeros((0, 4, 4))), [np.eye(4)] * 2)

    def test_drop_undrawn_submeshes(self):
        def mesh():
            return {"vertex_count": 6, "vertices": np.arange(18, dtype=np.float32).reshape(6, 3),
                    "uv0": np.arange(12, dtype=np.float32).reshape(6, 2),
                    "indices": np.array([0, 1, 2, 3, 4, 5, 2, 1, 5]),
                    "submeshes": [(0, 3, 0), (3, 3, 0), (6, 3, 0)],
                    "bindposes": np.zeros((6, 4, 4)),                 # one per BONE; six of them by chance
                    "shapes": [{"name": "a", "indices": np.array([1, 4]), "delta": np.ones((2, 3), dtype=np.float32),
                                "normal": None}]}
        full = mesh()
        self.assertEqual(ts.drop_undrawn(full, 3), 0)                 # a material slot for every sub-mesh
        self.assertEqual(full["vertex_count"], 6)
        two = mesh()
        self.assertEqual(ts.drop_undrawn(two, 2), 1)                  # the third sub-mesh is not drawn
        self.assertEqual((two["vertex_count"], len(two["submeshes"])), (6, 2))     # its vertices are all shared
        one = mesh()
        self.assertEqual(ts.drop_undrawn(one, 1), 2)
        self.assertEqual((one["vertex_count"], one["submeshes"]), (3, [(0, 3, 0)]))
        self.assertEqual(one["indices"][:3].tolist(), [0, 1, 2])
        self.assertEqual((one["vertices"].shape, one["uv0"].shape), ((3, 3), (3, 2)))
        self.assertEqual(one["vertices"][2].tolist(), [6.0, 7.0, 8.0])
        self.assertEqual(one["bindposes"].shape, (6, 4, 4))
        self.assertEqual(one["shapes"][0]["indices"].tolist(), [1])   # vertex 4 went with its sub-mesh
        self.assertEqual(one["shapes"][0]["delta"].shape, (1, 3))
        none = mesh()
        self.assertEqual(ts.drop_undrawn(none, 0), 3)                 # a renderer without materials draws nothing
        self.assertEqual((none["vertex_count"], none["submeshes"]), (0, []))

    def test_limb_aliases(self):
        def at(x, y, z):
            m = np.eye(4)
            m[:3, 3] = (x, y, z)
            return m

        scene = ts.Scene(None, "")
        bones = {"Bip001 L Thigh": at(-0.09, 0.99, 0.01), "Bone_L_Thigh": at(-0.09, 0.99, 0.01),
                 "Bip001 L Calf": at(-0.08, 0.59, 0.01), "Bone_L_Calf": at(-0.08, 0.58, 0.01),       # 1 cm off: Asagi
                 "Bip001 L UpperArm": at(-0.15, 1.40, 0.0), "Bone_LUpperArm": at(-0.40, 1.60, 0.0),  # a mech's own arm
                 "Bone_L_Thigh_side": at(-0.12, 0.95, 0.0), "Bip001 Head": at(0.0, 1.55, 0.0)}
        scene.nodes = {i: {"bone": name, "world": world} for i, (name, world) in enumerate(bones.items())}
        scene.nodes[99] = {"name": "costume_1", "world": np.eye(4)}                                 # not a bone
        self.assertEqual(scene.limb_aliases(), {"Bone_L_Thigh": "Bip001 L Thigh", "Bone_L_Calf": "Bip001 L Calf"})

    def test_twist_owner(self):
        bones = {"Bip001 Pelvis", "Bip001 L Thigh", "Bip001 LThighTwist", "Bip001 L Forearm", "Bip001 L ForeTwist"}
        self.assertEqual(ts.twist_owner("Bip001 LThighTwist", ["Bip001 Pelvis", "Bip001"], bones), "Bip001 L Thigh")
        self.assertIsNone(ts.twist_owner("Bip001 L ForeTwist", ["Bip001 L Forearm", "Bip001 L UpperArm"], bones))
        self.assertIsNone(ts.twist_owner("Bip001 RCalfTwist", ["Bip001 Pelvis"], bones))      # no such limb bone
        self.assertIsNone(ts.twist_owner("Bip001_B_NeckTwist", ["Bip001 Neck"], bones))

    def test_box_gap(self):
        lo, hi = [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]
        self.assertEqual(ts.box_gap(lo, hi, [[0.5, 1.0, 0.5]]), 0.0)                      # inside
        self.assertAlmostEqual(ts.box_gap(lo, hi, [[9.0, 9.0, 9.0], [1.3, 2.4, 0.5]]), 0.5)  # the nearer point
        self.assertEqual(ts.box_gap(lo, hi, []), float("inf"))
        self.assertTrue(ts.HAND_NAME.search("Bip001 R Hand") and ts.HAND_NAME.search("Bip002 L Hand"))
        self.assertFalse(ts.HAND_NAME.search("Bip001 R Hand_scale") or ts.BIPED_BONE.search("Bip001"))
        self.assertTrue(ts.BIPED_BONE.search("Bip001 L Calf"))

    def test_decode_shapes_takes_the_last_frame(self):
        vert = lambda x, i: {"vertex": {"x": x, "y": 0.0, "z": 0.0}, "normal": {"x": 0, "y": 0, "z": 0},  # noqa: E731
                             "tangent": {"x": 0, "y": 0, "z": 0}, "index": i}
        shapes = {"vertices": [vert(0.5, 3), vert(1.0, 3), vert(0.25, 7)],
                  "shapes": [{"firstVertex": 0, "vertexCount": 1, "hasNormals": False},
                             {"firstVertex": 1, "vertexCount": 2, "hasNormals": False}],
                  "channels": [{"name": "smile\x1f_face", "frameIndex": 0, "frameCount": 2}], "fullWeights": [50.0, 100.0]}
        out = ts.decode_shapes(shapes)
        self.assertEqual([s["name"] for s in out], ["smile_face"])       # control characters dropped
        self.assertEqual(list(out[0]["indices"]), [3, 7])
        np.testing.assert_allclose(out[0]["delta"][:, 0], [1.0, 0.25])
        self.assertEqual(ts.decode_shapes({}), [])

    def test_unpack_normal(self):
        from PIL import Image

        packed = Image.new("RGBA", (1, 1), (255, 128, 0, 200))          # DXT5nm style: x in alpha, y in green
        r, g, b = ts.unpack_normal(packed).getpixel((0, 0))
        self.assertEqual((r, g), (200, 128))
        nx = 200 / 255 * 2 - 1
        ny = 128 / 255 * 2 - 1
        self.assertAlmostEqual(b / 255, np.sqrt(1 - nx * nx - ny * ny) * 0.5 + 0.5, delta=0.01)

    def test_roles_and_breast_bones(self):
        self.assertEqual(ts.part_role("face_24_mouth_in", ["Bip001 Head"], True), "face")
        self.assertEqual(ts.part_role("asuka_face", ["Bip001 Head"], True), "face")       # 16_Asuka Black
        self.assertEqual(ts.part_role("hair_24", ["Bip001 Head"], True), "hair")
        self.assertEqual(ts.part_role("costume_24", ["Bip001 Pelvis"], True), "body")
        self.assertEqual(ts.part_role("weapon_202_0_R", ["Bone_RH_Weapon"], False), "weapon")
        self.assertEqual(ts.part_role("weapon_130_0_R", ["Bone_Weapon"], False, parked=True), "weapon_parked")
        self.assertEqual(ts.part_role("em_debuff", ["Bip001 Head"], False), "emote")
        self.assertEqual(ts.part_role("costume_10_EffectRender", ["Bip001 Pelvis"], True), "effect")
        self.assertEqual(ts.part_role("B_16_EffectRenderMesh_1", [""], True), "effect")
        self.assertEqual(ts.part_role("costume_1", ["Bone_RH_Weapon"], True), "body")   # skinned = worn, not held
        cloth = [{"name": "Magica Cloth (Hair)", "root_bones": ["Bone_B_Hair_01"]},
                 {"name": "Magica Cloth (Breast)", "root_bones": ["Bip001 Xtra01", "Bip001 Xtra01Opp"]}]
        self.assertEqual(ts.breast_bones(cloth, ["Bip001 Xtra01", "Bone_L_Bust"]), ["Bip001 Xtra01", "Bip001 Xtra01Opp"])
        self.assertEqual(ts.breast_bones([], ["Bip001 Head", "Bone_L_Bust", "Bone_RBreast"]), ["Bone_L_Bust", "Bone_RBreast"])
        self.assertEqual(ts.safe_name("Magica Cloth (Hair)"), "Magica_Cloth_Hair")


def at(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def fake(kind, **fields):
    """A component reader: .type.name, plus what the scene code asks of it."""
    return SimpleNamespace(type=SimpleNamespace(name=kind), **fields)


def transform(pid, name, pos=(0.0, 0.0, 0.0), children=(), comps=(), active=True):
    """A Transform reader that is also the PPtr to itself (FakeScene's loader.deref hands it back)."""
    return fake("Transform", path_id=pid, name=name, pos=pos, children=list(children), comps=list(comps), active=active)


def attach_object(bone, reset=1):
    return fake("MonoBehaviour", cls="AttachObject",
                read_typetree=lambda: {"kBoneName": bone, "kInitTrans": reset, "kWeaponName": "x"})


def skinned(*bone_ids):
    renderer = SimpleNamespace(m_Enabled=True, m_Mesh=SimpleNamespace(m_PathID=77),
                               m_Bones=[SimpleNamespace(m_FileID=0, m_PathID=b) for b in bone_ids])
    return fake("SkinnedMeshRenderer", read=lambda: renderer)


class FakeScene(ts.Scene):
    """Scene over hand-made transforms: no bundle, no UnityPy object."""

    def __init__(self, prefabs):
        loader = SimpleNamespace(deref=lambda p: p, container_object=lambda bundle, guid: SimpleNamespace(
            read=lambda: SimpleNamespace(comps=[prefabs[guid]])))
        super().__init__(loader, "")
        for nid, name, parent, world in ((1, "prf_20", None, at(0, 0, 0)), (2, "Bip001 L Clavicle", 1, at(-0.1, 1.3, 0)),
                                         (3, "Bip001 L UpperArm", 2, at(-0.2, 1.3, 0)),
                                         (4, "Bip001 L Forearm", 3, at(-0.45, 1.3, 0)),
                                         (5, "Bip001 L Hand", 4, at(-0.65, 1.3, 0)), (6, "Bone_LH_Weapon", 5, at(-0.7, 1.3, 0))):
            self._add_node(nid, name, parent, np.eye(4), world, True, ["Transform"], [], [])

    def _components(self, go):
        return go.comps

    def _read_transform(self, tr):
        comps = tr.comps
        return (SimpleNamespace(m_Children=tr.children), SimpleNamespace(m_Name=tr.name, m_IsActive=tr.active), comps,
                at(*tr.pos), [c.type.name for c in comps], [c.cls for c in comps if c.type.name == "MonoBehaviour"])


def weapon(name, guid):
    return {"name": name, "grade": 0, "slot": name.rsplit("_", 1)[1], "bundle": "b", "guid": guid}


class WeaponPrefabTests(unittest.TestCase):
    def arm(self):
        """Natsume's left arm: every skinned bone is a Ref_ stand-in for a bone of the unit."""
        nub = transform(14, "Bip001 L Finger0Nub", (-0.05, 0.0, 0.0))
        fore = transform(12, "Ref_Bip001 L Forearm", (-0.3, 0.0, 0.0), [nub])           # 5 cm off the unit's bone
        upper = transform(11, "Ref_Bip001 L UpperArm", (-0.1, 0.0, 0.0), [fore])
        mesh = transform(13, "fbx_weapon_20_0_L", comps=[skinned(11, 12)])
        return transform(10, "prf_weapon_20_0_L", (9.0, 9.0, 9.0), [upper, mesh], [attach_object("Bip001 L Clavicle")])

    def gun(self, reset=1, bone="Bone_LH_Weapon"):
        barrel = transform(22, "Bone_Gun_01", (0.0, 0.0, 0.2))
        clavicle = transform(24, "Bip001 L Clavicle", (0.6, 0.0, 0.0))                 # a unit bone's name, elsewhere
        hand = transform(25, "Bip001 L Hand", (0.05, -0.1, 0.0))                       # ... and one lying on it
        body = transform(21, "Bone_Gun_Root", (0.0, 0.1, 0.0), [barrel, clavicle, hand])
        mesh = transform(23, "weapon_7_0_L", comps=[skinned(21, 22, 25)])
        return transform(20, "prf_weapon_7_0_L", (0.0, 0.5, 0.0), [body, mesh], [attach_object(bone, reset)])

    def test_a_limb_is_skinned_to_the_units_own_bones(self):
        scene = FakeScene({"arm": self.arm()})
        scene.add_weapons(1, [weapon("prf_weapon_20_0_L", "arm")], "limbs")
        self.assertEqual([(w["name"], w["kind"], w["bone"]) for w in scene.weapons],
                         [("prf_weapon_20_0_L", "limb", "Bip001 L Clavicle")])
        tag = "prf_weapon_20_0_L"
        self.assertEqual(scene.alias, {(tag, 11): 3, (tag, 12): 4})
        root = scene.nodes[(tag, 10)]
        self.assertEqual(root["parent"], 2)
        np.testing.assert_allclose(root["world"], at(-0.1, 1.3, 0))            # kInitTrans: its own offset is dropped
        nub = scene.nodes[(tag, 14)]
        self.assertEqual(nub["parent"], 4)                                     # hangs from the UNIT's forearm,
        np.testing.assert_allclose(nub["world"], at(-0.5, 1.3, 0))             # placed from where that bone is
        self.assertNotIn((tag, 11), scene.nodes)                               # no node for a Ref_ stand-in
        mesh = scene.nodes[(tag, 13)]
        self.assertEqual([scene._nid(mesh, 0, 11), scene._nid(mesh, 0, 12)], [3, 4])
        self.assertIsNone(scene._nid(mesh, 1, 11))                             # another file
        self.assertEqual(scene._nid(scene.nodes[3], 0, 4), 4)                  # the unit's own references are plain ids
        keep = scene.choose_bones(1, {3, 4})
        self.assertNotIn((tag, 14), keep)                                      # a spare transform of the prefab: no bone

    def test_a_real_weapon_is_left_out_unless_asked_for(self):
        scene = FakeScene({"gun": self.gun()})
        before = set(scene.nodes)
        scene.add_weapons(1, [weapon("prf_weapon_7_0_L", "gun")], "limbs")
        self.assertEqual((scene.weapons, set(scene.nodes), scene.alias), ([], before, {}))
        self.assertEqual(scene.nodes[6]["children"], [])
        self.assertEqual([(w["name"], w["kind"]) for w in scene.weapons_left], [("prf_weapon_7_0_L", "weapon")])
        self.assertIn("--weapons", scene.weapons_left[0]["reason"])

        scene = FakeScene({"gun": self.gun()})
        scene.add_weapons(1, [weapon("prf_weapon_7_0_L", "gun")], "all")
        tag = "prf_weapon_7_0_L"
        self.assertEqual([(w["name"], w["kind"], w["bone"]) for w in scene.weapons], [(tag, "weapon", "Bone_LH_Weapon")])
        np.testing.assert_allclose(scene.nodes[(tag, 22)]["world"], at(-0.7, 1.4, 0.2))    # own bones, under the hand bone
        self.assertEqual(scene.nodes[(tag, 22)]["parent"], (tag, 21))
        self.assertIn((tag, 24), scene.nodes)                  # named like a unit bone but somewhere else: its own node
        self.assertEqual(scene.alias, {(tag, 25): 5})          # named like a unit bone AND lying on it: that bone
        keep = scene.choose_bones(1, {(tag, 21), (tag, 22), 5})
        self.assertTrue({(tag, 20), (tag, 21), (tag, 22), 6, 5} <= keep)       # skinned bones with their ancestors
        self.assertNotIn((tag, 24), keep)
        self.assertEqual(scene.nodes[(tag, 20)]["bone"], tag)

    def test_the_prefab_keeps_its_offset_without_kInitTrans(self):
        scene = FakeScene({"gun": self.gun(reset=0)})
        scene.add_weapons(1, [weapon("prf_weapon_7_0_L", "gun")], "all")
        np.testing.assert_allclose(scene.nodes[("prf_weapon_7_0_L", 20)]["world"], at(-0.7, 1.8, 0))

    def test_prefabs_that_cannot_be_attached(self):
        bare = transform(30, "prf_weapon_29_1_B", children=[transform(31, "fx", comps=[skinned(31)])])
        off = transform(40, "prf_weapon_91_0_L", comps=[attach_object("Bip001 L UpperArm")], children=[
            transform(41, "Ref_Bip001 L Forearm"), transform(42, "weapon_91_0_L", comps=[skinned(41)], active=False)])
        scene = FakeScene({"gun": self.gun(bone="Bone_RH_Weapon"), "bare": bare, "off": off})
        before = set(scene.nodes)
        scene.add_weapons(1, [weapon("prf_weapon_7_0_L", "gun"), weapon("prf_weapon_29_1_B", "bare"),
                              weapon("prf_weapon_91_0_L", "off")], "all")
        self.assertEqual((scene.weapons, set(scene.nodes), scene.alias), ([], before, {}))
        reasons = [w["reason"] for w in scene.weapons_left]
        self.assertIn("Bone_RH_Weapon", reasons[0])            # the unit has no such transform
        self.assertIn("AttachObject", reasons[1])
        self.assertIn("switched off", reasons[2])              # 91_Sensyu's second pair of arms: off in the prefab
        scene.add_weapons(1, [weapon("prf_weapon_7_0_L", "gun")], "none")
        self.assertEqual(len(scene.weapons_left), 3)


class DanceVideoTests(unittest.TestCase):
    def folder(self, *names):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name in names:
            open(os.path.join(tmp.name, name), "w").close()
        return tmp.name

    def test_a_folder_gives_its_motion_and_its_music(self):
        folder = self.folder("\u7206\u4e862026.1.18.vmd", "\u7206\u4e862026.1.18.WAV", "readme.txt")
        vmd, bgm = dance_video.pick_motion(folder)
        self.assertEqual((os.path.basename(vmd), os.path.basename(bgm)), ("\u7206\u4e862026.1.18.vmd", "\u7206\u4e862026.1.18.WAV"))
        self.assertEqual(dance_video.pick_motion(vmd), (vmd, bgm))            # the .vmd itself: the same music
        self.assertEqual(dance_video.motion_name(vmd), "\u7206\u4e862026.1.18")
        self.assertEqual(dance_video.motion_name(vmd, 'my dance: take 2?'), "my_dance_take_2")

    def test_camera_motions_and_stray_music_are_passed_over(self):
        folder = self.folder("dance.vmd", "dance_camera.vmd", "\u8868\u60c5.vmd", "song.mp3", "other.wav")
        vmd, bgm = dance_video.pick_motion(folder)
        self.assertEqual(os.path.basename(vmd), "dance.vmd")
        self.assertEqual(bgm, "")                                             # two audio files, none named like the motion
        chosen = os.path.join(folder, "other.wav")
        self.assertEqual(dance_video.pick_motion(folder, chosen), (vmd, chosen))
        with self.assertRaises(SystemExit):
            dance_video.pick_motion(folder, os.path.join(folder, "missing.wav"))
        with self.assertRaises(SystemExit):
            dance_video.pick_motion(self.folder("a.vmd", "b.vmd"))            # which one?
        with self.assertRaises(SystemExit):
            dance_video.pick_motion(self.folder("song.wav"))                  # no motion at all
        with self.assertRaises(SystemExit):
            dance_video.pick_motion(os.path.join(folder, "song.mp3"))         # not a .vmd

    def test_video_paths(self):
        model = {"id": "1_asagi", "group": "Asagi"}
        folder, mp4 = dance_video.video_paths(model, r"E:\x", "dance")
        self.assertEqual(folder, os.path.join(r"E:\x", "Asagi", "video", "1_asagi"))
        self.assertEqual(mp4, os.path.join(folder, "1_asagi_dance.mp4"))

    def test_backdrop_by_a_piece_of_its_name(self):
        root = self.folder()
        pictures = os.path.join(root, "_backgrounds")
        os.mkdir(pictures)
        for name in ("a_S018_B_club.png", "a_S018_A_street.png", "b_sky_night.png", "_sheet_club.jpg"):
            open(os.path.join(pictures, name), "w").close()
        self.assertEqual(os.path.basename(dance_video.find_backdrop("club", root)), "a_S018_B_club.png")
        self.assertEqual(os.path.basename(dance_video.find_backdrop("s018_b", root)), "a_S018_B_club.png")
        with self.assertRaises(SystemExit):
            dance_video.find_backdrop("S018", root)                           # two pictures fit
        with self.assertRaises(SystemExit):
            dance_video.find_backdrop("beach", root)                          # none does
        own = os.path.join(root, "mine.jpg")
        open(own, "w").close()
        self.assertEqual(dance_video.find_backdrop(own, root), os.path.abspath(own))    # a file of one's own
        model = {"id": "1_asagi", "group": "Asagi"}
        _folder, mp4 = dance_video.video_paths(model, root, "dance", backdrop=os.path.join(pictures, "a_S018_B_club.png"))
        self.assertTrue(mp4.endswith("1_asagi_dance_bg-a_S018_B_club.mp4"))


class BustSettingsTests(unittest.TestCase):
    def test_parse_bust(self):
        p = tc.parse_bust("bounce_hz=3, ratio=0.2;style=swing")
        self.assertEqual((p["bounce_hz"], p["ratio"], p["style"], p["sway_hz"]), (3.0, 0.2, "swing", tc.BUST["sway_hz"]))
        self.assertEqual(tc.parse_bust(None), tc.BUST)
        self.assertEqual(tc.parse_bust(""), tc.BUST)
        for bad in ("bounce=3", "style=jelly", "ratio=soft"):
            with self.assertRaises(SystemExit):
                tc.parse_bust(bad)
        self.assertEqual(tc.parse_bust(tc.bust_text(p)), p)                    # what goes to Blender comes back the same

    def test_sag(self):
        self.assertAlmostEqual(tc.bust_sag_cm(tc.BUST), 1.53, places=2)       # 98 units / s^2 against 3.6 Hz

    def test_the_game_gives_the_travel_limit(self):
        asagi = tc.bust_for_unit(tc.BUST, {"limit_distance": 0.05, "blend_weight": 1.0})
        self.assertEqual(asagi["cap_cm"], 5.0)
        rinko = tc.bust_for_unit(tc.BUST, {"limit_distance": 0.05, "blend_weight": 0.3})
        self.assertEqual(rinko["cap_cm"], 1.5)                                 # what the game shows at 30 %
        self.assertEqual(tc.bust_for_unit(tc.BUST, None), tc.BUST)             # no Bone Spring on the breasts
        mine = tc.bust_for_unit(tc.parse_bust("cap_cm=2"), {"limit_distance": 0.05, "blend_weight": 1.0}, "cap_cm=2")
        self.assertEqual(mine["cap_cm"], 2.0)                                  # named on the command line: it stays

    def test_asagi_gets_the_settings_as_they_are(self):
        fit, factor = tc.bust_fitted(tc.bust_for_unit(tc.BUST, {"limit_distance": 0.05, "blend_weight": 1.0}), 10.9)
        self.assertEqual(factor, 1.0)
        self.assertEqual({k: fit[k] for k in tc.BUST if k != "cap_cm"}, {k: tc.BUST[k] for k in tc.BUST if k != "cap_cm"})
        self.assertEqual(tc.bust_fitted(tc.BUST, 10.87)[1], 1.0)               # a millimetre of measuring is nothing
        self.assertEqual(tc.bust_fitted(tc.BUST, None), (tc.BUST, 1.0))        # size unknown: as they are

    def test_a_smaller_breast_travels_less_on_stiffer_springs(self):
        fit, factor = tc.bust_fitted(tc.BUST, 7.1)                             # Yukikaze
        self.assertEqual(factor, 0.65)
        self.assertEqual((fit["sway_cm"], fit["depth_cm"], fit["bounce_cm"]), (3.25, 2.6, 2.6))
        self.assertAlmostEqual(fit["sway_hz"], 2.2 / math.sqrt(0.65), places=2)
        self.assertAlmostEqual(tc.bust_sag_cm(fit), tc.bust_sag_cm(tc.BUST) * 0.65, places=1)   # the sag shrinks with it
        self.assertEqual(tc.bust_fitted(tc.BUST, 2.0)[1], tc.BUST_SIZE[0])     # the flattest still moves a little
        big, factor = tc.bust_fitted(tc.BUST, 15.4)                            # Rinko
        self.assertEqual(factor, tc.BUST_SIZE[1])
        self.assertLess(big["sway_hz"], tc.BUST["sway_hz"])
        self.assertEqual(big["bounce_hz"], tc.BUST["bounce_hz"])               # never softer against gravity
        self.assertEqual(tc.bust_fitted(tc.parse_bust("size_cm=0"), 4.0)[1], 1.0)   # size switched off

    def test_no_breast_goes_further_than_the_game_lets_it(self):
        capped = tc.parse_bust("cap_cm=4")
        fit, factor = tc.bust_fitted(capped, 12.5)                             # Azusa: larger than Asagi, 4 cm in the game
        self.assertEqual((factor, fit["sway_cm"]), (0.8, 4.0))
        small, factor = tc.bust_fitted(capped, 5.45)                           # half Asagi's size: the cap is not reached
        self.assertEqual((factor, small["sway_cm"]), (0.5, 2.5))
        tiny, factor = tc.bust_fitted(tc.parse_bust("cap_cm=0.2"), 10.9)
        self.assertEqual(factor, tc.BUST_FACTOR[0])                            # BUST_FACTOR holds
        free, factor = tc.bust_fitted(tc.parse_bust("cap_cm=1,game=0"), 10.9)
        self.assertEqual(factor, 1.0)                                          # the game switched off
        more, factor = tc.bust_fitted(tc.parse_bust("amount=1.3"), 10.9)
        self.assertEqual((factor, more["sway_cm"]), (1.3, 6.5))
        self.assertEqual(tc.bust_fitted(tc.parse_bust("amount=1.3,cap_cm=5"), 10.9)[1], 1.0)    # the cap still holds
        self.assertEqual(tc.bust_fitted(tc.parse_bust("amount=9"), 10.9)[1], tc.BUST_FACTOR[1])

    def test_the_damping_stays_inside_what_a_pmx_can_hold(self):
        fit, _factor = tc.bust_fitted(tc.parse_bust("cap_cm=0.5,ratio=0.6"), 10.9)
        rate = 2.0 * fit["ratio"] * 2.0 * math.pi * min(fit["sway_hz"], fit["depth_hz"], fit["bounce_hz"])
        self.assertLessEqual(rate, tc.BUST_MAX_RATE + 0.05)
        self.assertLess(fit["ratio"], 0.6)
        d = np.float32(1.0 - math.exp(-rate))
        self.assertLess(float(d), 1.0)                                         # not a body that stops dead each step
        self.assertEqual(tc.bust_fitted(tc.BUST, 10.9)[0]["ratio"], tc.BUST["ratio"])


class BackgroundTests(unittest.TestCase):
    def test_a_cubemap_becomes_a_panorama(self):
        faces = [np.full((8, 8, 3), 40 * (i + 1), dtype=np.uint8) for i in range(6)]     # +X -X +Y -Y +Z -Z
        pano = eb.cube_to_equirect(faces, 64)
        self.assertEqual(pano.shape, (32, 64, 3))
        self.assertEqual(pano[16, 32, 0], 40)              # the middle column looks along +X
        self.assertEqual(pano[16, 16, 0], 200)             # a quarter to its left: +Z, forward
        self.assertEqual(pano[16, 48, 0], 240)             # a quarter to its right: -Z
        self.assertEqual(pano[16, 0, 0], 80)               # the two ends meet behind: -X
        self.assertEqual(pano[0, 10, 0], 120)              # top row: straight up
        self.assertEqual(pano[31, 10, 0], 160)             # bottom row: straight down

    def test_the_panorama_has_no_seams(self):
        # every face painted with a smooth function of the direction it shows: the panorama must be that function
        n, width = 64, 256
        t, s = np.meshgrid((np.arange(n) + 0.5) / n * 2 - 1, (np.arange(n) + 0.5) / n * 2 - 1, indexing="ij")
        one = np.ones_like(s)
        shown = [(one, -t, -s), (-one, -t, s), (s, one, t), (s, -one, -t), (s, -t, one), (-s, -t, -one)]

        def paint(x, y, z):
            d = np.stack([x, y, z], axis=-1)
            return (d / np.linalg.norm(d, axis=-1, keepdims=True) * 0.5 + 0.5) * 255.0

        pano = eb.cube_to_equirect([paint(*d) for d in shown], width).astype(np.float64)
        lon = (0.5 - (np.arange(width) + 0.5) / width) * 2 * np.pi
        lat = (0.5 - (np.arange(width // 2) + 0.5) / (width // 2)) * np.pi
        lon, lat = np.meshgrid(lon, lat)
        want = paint(np.cos(lat) * np.cos(lon), np.sin(lat), np.cos(lat) * np.sin(lon))
        self.assertLess(np.abs(pano - want).max(), 5.0)

    def test_file_names(self):
        self.assertEqual(eb.file_stem("Prologue_Epilogue/ep_03/Episode1_3_pl/texture/pl_01.png"), "1-3_pl_01")
        self.assertEqual(eb.file_stem("UI/BackGround/BGUnit_SchoolMap.png"), "SchoolMap")
        self.assertEqual(eb.file_stem("BackGround/Share/Skybox/Above Day C Equirect.png"), "Above_Day_C_Equirect")
        self.assertEqual(eb.picture_name("a", "Story/BG/S018_B.png", "b"), "a_S018_B_b.png")
        names = [eb.picture_name(*pick) for pick in eb.PICKS]
        self.assertEqual(len(names), len({n.lower() for n in names}))          # one file each (Windows: case-blind)
        self.assertEqual({pick[0] for pick in eb.PICKS}, set(eb.CATEGORIES))
        self.assertFalse([n for n in names if re.search(r'[<>:"/\\|?*]', n)])

    def test_menu_backdrops_go_back_to_16_9(self):
        square = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
        out = eb.tidy(square, eb.SQUASHED[0])
        self.assertEqual((out.size, out.mode), ((64, 36), "RGB"))
        other = next(c for c in eb.CATEGORIES if c not in eb.SQUASHED)
        self.assertEqual(eb.tidy(square, other).size, (64, 64))               # only they are stored squashed
        glass = Image.new("RGBA", (8, 8), (10, 20, 30, 128))
        self.assertEqual(eb.tidy(glass, other).mode, "RGBA")                  # real transparency is kept

    def test_contact_sheets(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        category, rows = eb.CATEGORIES[0], []
        for i in range(3):
            path = os.path.join(tmp.name, "%s_p%d_x.png" % (category, i))
            Image.new("RGB", (40, 30), (i * 80, 0, 0)).save(path)
            rows.append({"file": path, "category": category, "label": "x", "key": "Story/BG/p%d.png" % i,
                         "width": 40, "height": 30})
        stale = os.path.join(tmp.name, "_总览_old_9.jpg")              # a sheet of an earlier run
        open(stale, "w").close()
        sheets = eb.contact_sheets(rows, tmp.name, cols=2, per_page=2)
        self.assertEqual(len(sheets), 2)
        self.assertTrue(all(os.path.isfile(p) for p in sheets))
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(all(os.path.isfile(r["file"]) for r in rows))          # the pictures themselves stay


class CompressedMeshTests(unittest.TestCase):
    def test_the_fourth_packed_weight_is_what_is_missing_from_one(self):
        # as UnityPy 1.25 hands them over: 25 + 2 + 2 thirty-firsts read, the fourth left as 1 - 29
        got = ts.packed_weights(np.array([[25 / 31, 2 / 31, 2 / 31, -28.0], [1.0, 0.0, 0.0, 0.0],
                                          [20 / 31, 11 / 31, 0.0, 0.0], [1 / 31, 0.0, 0.0, 0.0]]))
        np.testing.assert_allclose(got[0], [25 / 31, 2 / 31, 2 / 31, 2 / 31], atol=1e-6)
        np.testing.assert_allclose(got[1:3], [[1.0, 0.0, 0.0, 0.0], [20 / 31, 11 / 31, 0.0, 0.0]], atol=1e-6)
        np.testing.assert_allclose(got.sum(axis=1), 1.0, atol=1e-6)
        self.assertEqual(ts.packed_weights(np.ones((3, 1))).shape, (3, 1))     # fewer than four per vertex: as is


if __name__ == "__main__":
    unittest.main()
