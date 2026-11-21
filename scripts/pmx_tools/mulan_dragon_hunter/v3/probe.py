# What is in a PMX: materials (faces, texture), main bones (cm), rigid bodies, joints, morphs.
#   python probe.py <pmx> [--bones regex] [--all-bones]
import os
import re
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2"))
import pmxlib as L  # noqa: E402

p = sys.argv[1]
rx = None
if "--bones" in sys.argv:
    rx = re.compile(sys.argv[sys.argv.index("--bones") + 1])
M = L.load(os.path.abspath(p))
print("model:", M.name, "| verts", len(M.vertices), "faces", len(M.faces), "bones", len(M.bones), "morphs", len(M.morphs),
      "rigids", len(M.rigids), "joints", len(M.joints), "| UNIT_CM", L.UNIT_CM)
V = np.array([v.co for v in M.vertices]) * L.UNIT_CM
print("bbox cm:", V.min(0).round(1), V.max(0).round(1))
mf = L.mat_faces(M)
for i, m in enumerate(M.materials):
    s, n = mf[i]
    vs = sorted({v for f in M.faces[s:s + n] for v in f})
    b = V[vs]
    tex = os.path.basename(M.textures[m.texture].path) if m.texture >= 0 else "-"
    print("  mat %2d %-46s faces %6d  y %.0f..%.0f  x %.0f..%.0f  z %.0f..%.0f  tex %s  2side %s" % (
        i, m.name, n, b[:, 1].min(), b[:, 1].max(), b[:, 0].min(), b[:, 0].max(), b[:, 2].min(), b[:, 2].max(), tex,
        m.is_double_sided))
main = ["全ての親", "センター", "グルーブ", "腰", "下半身", "上半身", "上半身2", "上半身3", "首", "頭", "両目", "左目", "左肩", "左腕", "左腕捩",
        "左ひじ", "左手捩", "左手首", "左親指１", "左中指１", "左中指３", "左足", "左ひざ", "左足首", "左つま先", "左足D", "左ひざD", "左足首D",
        "左足先EX", "左足ＩＫ", "右肩", "右腕", "右ひじ", "右手首", "右足", "右ひざ", "右足首"]
names = [b.name for b in M.bones]
for i, b in enumerate(M.bones):
    if (rx and rx.search(b.name)) or (not rx and b.name in main) or "--all-bones" in sys.argv:
        c = np.array(b.location) * L.UNIT_CM
        par = names[b.parent] if b.parent is not None and b.parent >= 0 else "-"
        print("  bone %3d %-14s (%6.1f %6.1f %6.1f) parent %s" % (i, b.name, c[0], c[1], c[2], par))
print("morphs:", [m.name for m in M.morphs][:80])
for i, r in enumerate(M.rigids):
    c = np.array(r.location) * L.UNIT_CM
    print("  rigid %2d %-22s bone %-10s grp %2d mask %5d type %d mode %d size %s at (%.0f %.0f %.0f)" % (
        i, r.name, names[r.bone] if r.bone is not None and r.bone >= 0 else "-", r.collision_group_number,
        r.collision_group_mask, r.type, r.mode, np.round(np.array(r.size) * L.UNIT_CM, 1), c[0], c[1], c[2]))
print("joints:", len(M.joints), [j.name for j in M.joints][:10])
