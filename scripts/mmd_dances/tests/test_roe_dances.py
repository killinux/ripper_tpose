"""Offline tests of the cross-game dance scripts (no game, no Blender, no archive needed).

    python -m unittest discover -s scripts/mmd_dances/tests      # from the repo root
"""
import json
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pmx_rig_check as rig  # noqa: E402
import roe_backgrounds as bg  # noqa: E402
import roe_dances as rd  # noqa: E402


def touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def dance(folder, status="", seconds=10.0):
    return {"folder": folder, "title": folder.split("(")[0], "vmd": folder + ".vmd", "music": folder + ".wav",
            "seconds": seconds, "date": [0, 0, 0], "status": status}


def pmx_bytes(bones, vertices):
    """A PMX 2.0 that holds only what pmx_rig_check reads: `bones` [(name, parent index)], `vertices` [weights] where
    weights is one bone index (BDEF1) or [(bone, weight)] of four (BDEF4); no faces, textures, materials."""
    def text(s):
        raw = s.encode("utf-16-le")
        return struct.pack("<i", len(raw)) + raw

    out = b"PMX " + struct.pack("<f", 2.0) + bytes([8, 0, 0, 4, 1, 1, 2, 1, 1])
    out += text("model") + text("") + text("") + text("")
    out += struct.pack("<i", len(vertices))
    for w in vertices:
        out += struct.pack("<8f", 0, 0, 0, 0, 1, 0, 0, 0)
        if isinstance(w, int):
            out += bytes([0]) + struct.pack("<h", w)
        else:
            out += bytes([2]) + struct.pack("<4h4f", *[b for b, _x in w], *[x for _b, x in w])
        out += struct.pack("<f", 1.0)
    out += struct.pack("<i", 0) + struct.pack("<i", 0) + struct.pack("<i", 0)        # faces, textures, materials
    out += struct.pack("<i", len(bones))
    for name, parent in bones:
        out += text(name) + text("") + struct.pack("<3f", 0, 0, 0) + struct.pack("<h", parent)
        out += struct.pack("<i", 0) + struct.pack("<H", 0) + struct.pack("<3f", 0, 1, 0)
    return out


class RigCheckTests(unittest.TestCase):
    def test_parts_on_a_second_tree_are_loose(self):
        bones = [("全ての親", -1), ("センター", 0), ("flowe_BL_01Root", -1), ("flower_BL_01", 2), ("empty_root", -1),
                 ("AC_pistol", -1)]
        verts = [1, 1, 3, 3, [(1, 0.5), (5, 0.5), (0, 0.0), (0, 0.0)], [(1, 1.0), (5, 0.0), (0, 0.0), (0, 0.0)]]
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "m.pmx")
            touch(path, pmx_bytes(bones, verts))
            parts = rig.loose_parts(path)
        self.assertEqual(parts, [{"root": "flowe_BL_01Root", "verts": 2, "bones": ["flower_BL_01"]},
                                 {"root": "AC_pistol", "verts": 1, "bones": ["AC_pistol"]}])   # a weight 0 is no weight
        self.assertIn("flowe_BL_01Root（2 个顶点）", rig.describe(parts))

    def test_a_model_in_one_tree_has_nothing_loose(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "m.pmx")
            touch(path, pmx_bytes([("全ての親", -1), ("センター", 0), ("unused_root", -1)], [1, 1, 0]))
            self.assertEqual(rig.loose_parts(path), [])

    def test_the_check_is_cached_by_size_and_time(self):
        outfits = [{"id": "pc_e08_hd", "group": "Miri"}, {"id": "pc_e02_hd", "group": "Miri"}]
        with tempfile.TemporaryDirectory() as root:
            touch(rd.pmx_path(outfits[0], root), pmx_bytes([("全ての親", -1), ("r", -1)], [1]))
            touch(rd.pmx_path(outfits[1], root), pmx_bytes([("全ての親", -1), ("センター", 0)], [1]))
            cache = {}
            self.assertEqual(list(rd.loose_outfits(outfits, root, cache)), ["pc_e08_hd"])
            self.assertEqual(len(cache), 2)
            path = rd.pmx_path(outfits[0], root)
            cache[path][2] = []                                     # a cached answer is used while the file is the same
            self.assertEqual(rd.loose_outfits(outfits, root, cache), {})


class KindTests(unittest.TestCase):
    def test_each_kind_of_outfit_folder(self):
        cases = {"pc_g01_hd": "main", "pc_g04_outfit1_hd": "main", "pc_g01_hd_full": "full", "pc_g01_hd_nude": "nude",
                 "pc_g04_outfit1_hd_nude": "nude", "pc_g01_nk_bs": "nude_base", "pc_g01_fm_nk_bs": "nude_base",
                 "pc_a00_nk": "nude_base", "pc_a00_nk_nudebase": "nude_base", "pc_g01_fm": "fm",
                 "pc_g01_secretary": "suit", "pc_l01_swimsuit": "suit", "pc_g01_2025_rabbitgirl": "suit"}
        for name, kind in cases.items():
            self.assertEqual(rd.outfit_kind(name), kind, name)

    def test_the_dancers_by_default_are_the_dressed_outfits(self):
        self.assertEqual(set(rd.DANCERS), {"main", "suit"})
        self.assertTrue(set(rd.KIND_ZH) >= {k for k, _ in rd.KINDS})


class OutfitTests(unittest.TestCase):
    def test_only_outfits_with_their_pmx_and_no_underscore_folders(self):
        with tempfile.TemporaryDirectory() as root:
            touch(os.path.join(root, "Luf", "pmx", "pc_g01_hd", "pc_g01_hd.pmx"))
            touch(os.path.join(root, "Luf", "pmx", "pc_g01_sweater", "readme.txt"))      # no PMX: no dancer
            touch(os.path.join(root, "Kart", "pmx", "pc_b01_swim", "pc_b01_swim.pmx"))
            touch(os.path.join(root, "Kart", "blend", "pc_b02_hd", "pc_b02_hd.blend"))
            touch(os.path.join(root, "_hq_trial", "pmx", "pc_x01_hd", "pc_x01_hd.pmx"))
            got = rd.find_outfits(root)
        self.assertEqual([(m["group"], m["id"], m["kind"], m["name"]) for m in got],
                         [("Kart", "pc_b01_swim", "suit", "Kart_b01_swim"), ("Luf", "pc_g01_hd", "main", "Luf_g01_hd")])

    def test_the_hand_out_goes_round_the_characters(self):
        outfits = [{"id": "%s%d" % (g, i), "group": g} for g, n in (("A", 3), ("B", 1), ("C", 2)) for i in range(n)]
        order = rd.hand_out_order(outfits, seed=7)
        self.assertEqual(len(order), 6)
        self.assertEqual({m["group"] for m in order[:3]}, {"A", "B", "C"})        # one of each first
        self.assertEqual({m["group"] for m in order[3:5]}, {"A", "C"})            # B ran out
        self.assertEqual(order[5]["group"], "A")
        self.assertEqual([m["id"] for m in order], [m["id"] for m in rd.hand_out_order(list(reversed(outfits)), seed=7)])

    def test_an_outfit_is_named_by_id_or_by_a_piece_of_it(self):
        outfits = [{"id": i} for i in ("pc_g01_hd", "pc_g01_hd_full", "pc_g01_secretary", "pc_b01_swim")]
        self.assertEqual(rd.find(outfits, ["pc_g01_hd"])[0]["id"], "pc_g01_hd")          # exact beats a piece
        self.assertEqual(rd.find(outfits, ["Luf/pc_g01_secretary"])[0]["id"], "pc_g01_secretary")
        self.assertEqual(rd.find(outfits, ["swim"])[0]["id"], "pc_b01_swim")
        with self.assertRaises(SystemExit):
            rd.find(outfits, ["pc_g01"])                                                  # fits three
        with self.assertRaises(SystemExit):
            rd.find(outfits, ["nobody"])


class DanceTests(unittest.TestCase):
    def test_the_dances_of_another_games_batch_are_taken(self):
        with tempfile.TemporaryDirectory() as root:
            plan = os.path.join(root, "TaimaninSquad", "_videos", "_meta", "plan.json")
            touch(plan, json.dumps({"1_asagi": {"dance": "A", "backdrop": "x.png"}, "2_sakuya": {"dance": ""}}).encode())
            self.assertEqual(rd.taken_dances([plan]), {"A": "TaimaninSquad/1_asagi"})
            with self.assertRaises(SystemExit):
                rd.taken_dances([os.path.join(root, "nothing", "plan.json")])

    def test_every_folder_of_the_collection_says_what_became_of_it(self):
        dances = [dance("done"), dance("planned"), dance("squad"), dance("free"), dance("short", "不到 8 秒", 5.0)]
        outfits = [{"id": "pc_g01_hd", "group": "Luf", "outfit": "g01_hd", "kind": "main"},
                   {"id": "pc_b01_swim", "group": "Kart", "outfit": "b01_swim", "kind": "suit"},
                   {"id": "pc_e01_hd", "group": "Miri", "outfit": "e01_hd", "kind": "main"}]
        with tempfile.TemporaryDirectory() as root:
            video = os.path.join(root, "done_Luf_g01_hd.mp4")
            touch(video, b"mp4")
            data = rd.lists(outfits, {"pc_g01_hd": {"dance": "done"}, "pc_b01_swim": {"dance": "planned"}}, dances,
                            {"pc_g01_hd": {"video": video, "dance": "done", "time": "2026-10-04 20:30:00"}},
                            {"squad": "TaimaninSquad/1_asagi"}, "C:/motions", {"pc_x01_hd": "裙子穿模"})
        states = {t["folder"]: (t["state"], t["unit"]) for t in data["dances"]}
        self.assertEqual(states, {"done": ("已导出", "pc_g01_hd"), "planned": ("已分配，未导出", "pc_b01_swim"),
                                  "squad": ("别的游戏已用", "TaimaninSquad/1_asagi"), "free": ("未分配", ""),
                                  "short": ("不用", "")})
        self.assertEqual([r["id"] for r in data["units"]], ["pc_g01_hd", "pc_b01_swim"])     # no dance, no row
        s = data["summary"]
        self.assertEqual((s["outfits"], s["with_dance"], s["with_video"], s["usable"], s["exported"], s["planned"],
                          s["taken"], s["free"], s["left_out"], s["dropped"]), (3, 2, 1, 4, 1, 1, 1, 1, 1, 1))
        text = rd.markdown(data)
        self.assertIn("Rise of Eros 舞蹈视频列表", text)
        self.assertIn("裙子穿模", text)
        self.assertIn("`done_Luf_g01_hd.mp4`", text)

    def test_a_left_out_outfits_video_no_longer_counts(self):
        dances = [dance("A"), dance("B")]
        everyone = [{"id": "pc_e08_hd", "group": "Miri", "outfit": "e08_hd", "kind": "main"},
                    {"id": "pc_b04_hd", "group": "Kart", "outfit": "b04_hd", "kind": "main"}]
        loose = {"pc_e08_hd": [{"root": "flowe_BL_01Root", "verts": 840, "bones": ["flower_BL_01"]}]}
        with tempfile.TemporaryDirectory() as root:
            video = os.path.join(root, "A_Miri_e08_hd.mp4")
            touch(video, b"mp4")
            # e08 danced A, then was left out: A went to b04, which has no video of it yet
            data = rd.lists(everyone[1:], {"pc_b04_hd": {"dance": "A"}}, dances,
                            {"pc_e08_hd": {"video": video, "dance": "A"}}, {}, "C:/motions", {}, loose, everyone)
        states = {t["folder"]: (t["state"], t["unit"]) for t in data["dances"]}
        self.assertEqual(states["A"], ("已分配，未导出", "pc_b04_hd"))
        self.assertEqual(data["summary"]["with_video"], 0)
        self.assertEqual([(d["id"], d["character"]) for d in data["loose"]], [("pc_e08_hd", "Miri")])
        self.assertIn("flowe_BL_01Root（840 个顶点）", rd.markdown(data))


class BackgroundTests(unittest.TestCase):
    def test_a_texture_name_becomes_a_safe_file_name(self):
        self.assertEqual(bg.file_name("event32_ avg01_01"), "event32__avg01_01.jpg")   # as the files are named
        self.assertEqual(bg.file_name("Yoh_farm_avg01_01"), "Yoh_farm_avg01_01.jpg")

    def test_story_cgs_and_store_copies_are_no_backgrounds(self):
        self.assertIn("CG", bg.why_not("event35_cg01", set()))
        self.assertIn("CG", bg.why_not("Activity004_cg02_DMM", set()))
        self.assertIn("CG", bg.why_not("eros_pro_Lynn_cg03", set()))
        self.assertEqual(bg.why_not("level000_s01_avg01", set()), "")
        self.assertEqual(bg.why_not("cloud_avg01", set()), "")                  # "cloud" is no "cg"
        self.assertIn("商店", bg.why_not("x_avg01_DMM", {"x_avg01", "x_avg01_DMM"}))
        self.assertEqual(bg.why_not("x_avg01_DMM", {"x_avg01_DMM"}), "")       # the only copy stays

    def test_the_backdrops_are_the_written_pictures_less_the_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            where = bg.folder(root)
            for name in ("a.jpg", "b.jpg", "common_Black_avg01.jpg"):
                touch(os.path.join(where, name), b"jpg")
            index = {"pictures": {n: {"bundle": "x.ab"} for n in ("a.jpg", "b.jpg", "gone.jpg", "common_Black_avg01.jpg")},
                     "skipped": {}}
            touch(os.path.join(where, "_index.json"), json.dumps(index).encode())
            self.assertEqual(bg.backdrops(root), ["a.jpg", "b.jpg"])           # gone.jpg is not on disk
        self.assertTrue(all(why for why in bg.EXCLUDE.values()))


class BustPmxTests(unittest.TestCase):
    def test_the_bust_tuned_pmx_dances_where_there_is_one(self):
        m = {"id": "pc_j01_swim", "group": "Lynn"}
        with tempfile.TemporaryDirectory() as root:
            plain = rd.pmx_path(m, root)
            touch(plain, b"PMX ")
            self.assertEqual(rd.dance_pmx(m, root, "bustB"), plain)            # no _bustB: the plain one
            touch(plain[:-4] + "_bustB.pmx", b"PMX ")
            self.assertEqual(rd.dance_pmx(m, root, "bustB"), plain[:-4] + "_bustB.pmx")
            self.assertEqual(rd.dance_pmx(m, root, "main"), plain)
        self.assertEqual(rd.BUST_PMX, "bustB")


if __name__ == "__main__":
    unittest.main()
