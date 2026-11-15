"""After run_look.py: archive, mod sources, HQ registry + HQ .blend, add-on check + sheet, README.txt.

    python -I -X utf8 finish.py <step> <label|mod> ...
steps:
  archive   scripts/archive/archive_exports.py stellarblade --only <packages>  (blend / xps / pmx folders -> E:)
  sources   the mods' work folders -> E:\\game_export\\StellarBlade\\_meta\\mod_sources\\<mod>\\ (download, unzipped\\,
            listing / variants / per-look logs; no staging / cue folders: hardlinks of game files, junctions)
  registry  entries in _meta\\hq_materials\\mod_outfits.json (hq_mod_outfits.py reads it)
  hq        hq_mod_outfits.py --only <package>
  addon     the stellarblade_game_materials add-on on the archived PMX (scratch sbfiona_hq\\test_addon.py) + sheet
            -> <archive>\\Eve\\pmx\\<package>\\插件效果_游戏材质对比.jpg
  readme    <archive>\\Eve\\blend\\<package>\\README.txt (UTF-8 BOM, CRLF)
"""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from looks import BY_LABEL, LOOKS, MODS  # noqa: E402
from run_look import BLENDER, PACKAGES, WORK, triple_files  # noqa: E402

ARCHIVE = r"E:\game_export\StellarBlade"
MOD_SOURCES = os.path.join(ARCHIVE, "_meta", "mod_sources")
REGISTRY = os.path.join(ARCHIVE, "_meta", "hq_materials", "mod_outfits.json")
SB = r"E:\code\othercode\ripper_tpose\scripts\stellarblade"
ARCH_SCRIPT = r"E:\code\othercode\ripper_tpose\scripts\archive\archive_exports.py"
TEST_ADDON = os.path.join(HERE, "test_addon.py")


def package(label):
    return label[4:] if label.startswith("Eve_") else label


def status(lk):
    return json.load(open(WORK / lk["mod"] / "looks" / lk["label"] / "status.json", encoding="utf-8"))


def save_status(lk, st):
    json.dump(st, open(WORK / lk["mod"] / "looks" / lk["label"] / "status.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def pick(names):
    out = []
    for n in names:
        if n in BY_LABEL:
            out.append(BY_LABEL[n])
        elif n == "ALL_READY":
            out += [lk for lk in LOOKS if not lk.get("needs")]
        else:
            out += [lk for lk in LOOKS if lk["mod"] == n]
    seen, res = set(), []
    for lk in out:
        if lk["label"] not in seen:
            seen.add(lk["label"])
            res.append(lk)
    return res


def do_archive(looks):
    pk = [package(lk["label"]) for lk in looks]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, ARCH_SCRIPT, "stellarblade", "--only"] + pk, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=os.path.dirname(ARCH_SCRIPT), timeout=7200)
    open(os.path.join(str(WORK), "archive_last.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    print("\n".join((r.stdout + r.stderr).strip().splitlines()[-25:]))
    for lk in looks:
        p = package(lk["label"])
        ok = all(os.path.isdir(os.path.join(ARCHIVE, "Eve", f, p)) for f in ("blend", "xps", "pmx"))
        print("  %-44s archived blend/xps/pmx: %s" % (p, ok))


def do_sources(looks):
    for mod in sorted({lk["mod"] for lk in looks}):
        src, dst = str(WORK / mod), os.path.join(MOD_SOURCES, mod)
        r = subprocess.run(["robocopy", src, dst, "/E", "/COPY:DAT", "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/XJ",
                            "/XD", "staging", "cue", "_probe", "_probe_P", "_game", "_witheop", "json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = [ln for ln in r.stdout.splitlines() if ln.strip()][-6:]
        print("== %s -> %s (robocopy %d)\n   %s" % (mod, dst, r.returncode, "\n   ".join(tail)))


def do_registry(looks):
    reg = json.load(open(REGISTRY, encoding="utf-8")) if os.path.isfile(REGISTRY) else {}
    for lk in looks:
        lw = WORK / lk["mod"] / "looks" / lk["label"]
        slots = json.load(open(lw / "slots.json", encoding="utf-8"))
        fill = json.load(open(lw / "fill.json", encoding="utf-8"))
        hidden = set(fill.get("hide") or [])
        files = []
        for e in lk["stage"]:
            group = []
            for f in triple_files(e):
                rel = os.path.relpath(str(f), str(WORK))           # <mod>\unzipped\<sub>\<file>
                if not os.path.isfile(os.path.join(MOD_SOURCES, rel)):
                    raise SystemExit("not in the archived mod sources (run 'sources' first): " + rel)
                group.append(rel)
            files.append(group)
        overrides, slot_materials = {}, {}
        by_index = {s["index"]: s for s in slots}
        rep = (status(lk).get("fill") or {})
        split = {(orig[:-4] if orig.endswith("_mod") else orig, n): copy for copy, orig, n in rep.get("split") or []}
        for o in fill.get("overrides") or []:
            s = by_index.get(o["index"])
            if not (s and s.get("resolved")):
                continue
            copy = split.get((s["use"], s.get("mesh_index", s["index"])))
            if copy:                                  # this slot's own copy of a shared instance (fill_materials)
                slot_materials.setdefault(copy, {"instance": s["use"], "overrides": {}})["overrides"][o["param"]] = \
                    o["texture"]
            else:
                overrides.setdefault(s["use"], {})[o["param"]] = o["texture"]
        reg[package(lk["label"])] = {
            "character": "Eve", "mod": lk["mesh"].rsplit("/", 1)[0], "packages": [lk["mesh"] + ".uasset"],
            "mesh": lk["mesh"].rsplit("/", 1)[1], "any_mount": True, "files": files,
            "slots": sorted({s["use"] for s in slots if s.get("resolved") and s["index"] not in hidden}),
            "overrides": overrides, "slot_materials": slot_materials, "nexus": MODS[lk["mod"]]["nexus"],
            "title": lk["title"]}
        print("  %-44s %d files, %d slots, %d overridden" % (package(lk["label"]), sum(len(g) for g in files),
                                                          len(reg[package(lk["label"])]["slots"]), len(overrides)))
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("registry: %d entries -> %s" % (len(reg), REGISTRY))


def hq_one(lk):
    p = package(lk["label"])
    log = WORK / lk["mod"] / "looks" / lk["label"] / "hq.log"
    t = time.time()
    with open(log, "wb") as fh:
        rc = subprocess.run([sys.executable, os.path.join(SB, "hq_mod_outfits.py"), "--only", p], stdout=fh,
                            stderr=subprocess.STDOUT, cwd=SB, env=dict(os.environ, PYTHONIOENCODING="utf-8")).returncode
    text = open(log, encoding="utf-8", errors="replace").read()
    hq = os.path.join(ARCHIVE, "Eve", "blend", p, lk["label"] + "_HQ.blend")
    st = status(lk)
    st["hq"] = {"rc": rc, "hq_blend": hq if os.path.isfile(hq) else None, "seconds": round(time.time() - t),
                "log_tail": text.strip().splitlines()[-12:]}
    save_status(lk, st)
    return p, rc, os.path.isfile(hq), round(time.time() - t), text.strip().splitlines()[-1:] if text.strip() else []


def addon_one(lk):
    p = package(lk["label"])
    pmx = os.path.join(ARCHIVE, "Eve", "pmx", p, lk["label"] + ".pmx")
    out = str(WORK / lk["mod"] / "looks" / lk["label"] / "addon")
    log = WORK / lk["mod"] / "looks" / lk["label"] / "addon.log"
    with open(log, "wb") as fh:
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python", TEST_ADDON, "--", pmx, out, "--world", "0.45"],
                       stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
    text = open(log, encoding="utf-8", errors="replace").read()
    keep = [ln for ln in text.splitlines() if ln.startswith(("APPLY", "upgraded", "MISSING_IMAGES", "LIBRARIES",
                                                             "REEXPORT", "REMOVED", "TEST_DONE"))]
    sheet = os.path.join(ARCHIVE, "Eve", "pmx", p, "插件效果_游戏材质对比.jpg")
    r = subprocess.run([sys.executable, os.path.join(HERE, "make_sheet.py"), out, sheet,
                        "Eve × %s（Nexus %d）" % (lk["title"], MODS[lk["mod"]]["nexus"])],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    st = status(lk)
    st["addon"] = {"lines": keep, "sheet": sheet if os.path.isfile(sheet) else None, "sheet_err": r.stderr[-300:]}
    save_status(lk, st)
    return p, keep


def readme_one(lk):
    p = package(lk["label"])
    st = status(lk)
    meta = MODS[lk["mod"]]
    fill = st.get("fill") or {}
    fit = (st.get("swap") or {}).get("bone_fit") or {}
    folder = os.path.join(ARCHIVE, "Eve", "blend", p)
    hq_ok = os.path.isfile(os.path.join(folder, lk["label"] + "_HQ.blend"))
    addon = ((st.get("addon") or {}).get("lines") or [])
    up = next((ln for ln in addon if ln.startswith("upgraded")), "")
    L = ["Stellar Blade - Eve - %s" % lk["label"], "=" * 60, "",
         "来源 / Source : Nexus Mods 剑星 mod %d「%s」，作者 %s" % (meta["nexus"], meta["title"], meta["author"]),
         "                https://www.nexusmods.com/stellarblade/mods/%d（文件「%s」）" % (meta["nexus"], meta["file"]),
         "                这一套：%s" % lk["title"],
         "                个人使用；转发请注明 mod 作者。Personal use only; credit the mod author.", "",
         "这个文件夹是独立的：.blend 里的贴图全部用 //textures/ 相对路径引用，整个文件夹拷到别的电脑",
         "（保持目录结构不变）直接双击 .blend 就能打开。",
         "This folder is self-contained: every texture is referenced relatively from textures\\.", "",
         "做法 / How (2026-11-15)",
         "  mod 的网格换进已归档的 %s 成品（scripts/stellarblade/swap_mod_mesh.py）：脸、头发、马尾是游戏原版，" % lk["base"],
         "  同名骨骼对齐误差 %s cm。" % fit.get("rms_cm"),
         "  The mod's mesh swapped into the archived %s package; face and hair are the game's." % lk["base"]]
    if fill.get("filled"):
        L.append("  mod 只改参数、贴图继承游戏的材质（%d 个）：接的是最近一层父材质的游戏贴图，或从游戏里导出的贴图。" % len(fill["filled"]))
    if fill.get("overrides"):
        L.append("  CNS 默认选项（%s）：底色换成默认的那张，其余贴图（ORM / 法线 / 遮罩）在高清版里。" % ", ".join(
            sorted({o[2] for o in fill["overrides"]}))[:200])
    if fill.get("hidden"):
        L.append("  游戏里默认不显示的部件已去掉：%s。" % ", ".join(str(h[1]) for h in fill["hidden"]))
    L += ["", "文件 / Files",
          "  %-40s 直接接 mod / 游戏贴图的版本（PMX / XPS 由它导出）" % (lk["label"] + ".blend")]
    if hq_ok:
        L.append("  %-40s 高清版：材质实例连同游戏里的父材质、母材质一起读出来，按游戏参数接" % (lk["label"] + "_HQ.blend"))
        L.append("  %-40s （scripts/stellarblade/hq_mod_outfits.py --only %s）" % ("", p))
        if up:
            a, _, b = up.replace(";", " ").split()[1:4]
            L.append("  %-40s Blender 里用「剑星游戏材质」插件给这套 PMX 换材质：%s/%s 个材质换得上（2026-11-15 实测）" % ("", a, b))
    L += ["  %-40s 换网格的报告" % "mod_swap.json",
          "  %-40s 正面 / 背面预览" % "preview.png / preview_back.png",
          "  %-40s 贴图：mod 自带的在 textures\\mod\\，高清版用到的游戏贴图在 textures\\extra\\" % "textures\\", "",
          "同一套的 PMX / XPS：..\\..\\pmx\\%s\\、..\\..\\xps\\%s\\" % (p, p), ""]
    text = "\r\n".join(L) + "\r\n"
    with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(text)
    return p


SHORT = {"NikkePlus": "Nikke Plus", "AlbionGirls": "Albion Nell", "CakeUnveiledCS": "Cake 冷却服",
         "YoRHaCeremonial": "YoRHa 礼服", "BlackSling": "Black Sling", "CrimsonWingsBBB": "Crimson Wings BBB",
         "CrimsonWingsOP": "Crimson Wings OP", "SkinSuitUndressed": "Skin Suit Undressed",
         "EveNudeNatural": "Nude Natural", "EveOriginalProportions": "Original Proportions",
         "RevealingCrimsonWings": "Revealing CW", "YoRHaN2TypeB": "YoRHa 2B 制服", "Earlier": "之前导过的"}
EARLIER = [   # the mod exports before 11-15 (character folder, label, title)
    ("Fiona", "Eve_Mod_VindictusFiona", "Vindictus Fiona（#1145）"),
    ("Eve", "Eve_Mod_VindictusDemonMaiden", "Vindictus Demon Maiden（#1807）"),
    ("Reika", "Eve_Mod_GantzReika_A", "Gantz Reika A（#3561）"),
    ("Reika", "Eve_Mod_GantzReika_B", "Gantz Reika B（#3561）"),
    ("Eve", "Eve_Mod_GantzSling", "Gantz Sling suit（Patreon m.tsqn）"),
    ("Eve", "Eve_Mod_GantzSling_RedKeyholeSuit", "Gantz Sling 红 keyhole（Patreon m.tsqn）"),
    ("Eve", "Eve_Mod_GantzSling_KeyholeDress", "Gantz Sling keyhole dress（Patreon m.tsqn）"),
    ("Eve", "Eve_Nude_Barefoot", "Original Proportions 赤足（#30）"),
]


def look_notes(lk):
    try:
        st = status(lk)
    except OSError:
        return ""
    f, out = st.get("fill") or {}, []
    if f.get("overrides"):
        ov = [o for o in f["overrides"] if o[3].startswith("base colour")]
        if ov:
            out.append("CNS 默认颜色：" + "、".join(sorted({o[2].rsplit(".", 1)[0] for o in ov})))
    if f.get("hidden"):
        out.append("默认不显示的 %d 个部件已去掉" % len(f["hidden"]))
    if f.get("filled"):
        out.append("%d 个材质接游戏父材质的贴图" % len(f["filled"]))
    up = next((ln for ln in ((st.get("addon") or {}).get("lines") or []) if ln.startswith("upgraded")), "")
    if up:
        a, _, b = up.replace(";", " ").split()[1:4]
        out.append("插件换上 %s/%s" % (a, b))
    return "；".join(out)


def do_gallery(looks):
    mods = [dict(key=k, short=SHORT.get(k, k), **v) for k, v in MODS.items()]
    mods.append({"key": "Earlier", "short": SHORT["Earlier"], "title": "之前导过的 mod", "nexus": 0, "author": "-",
                 "file": "-", "note": "Vindictus / GANTZ 系列和 Original Proportions 赤足"})
    items = []
    for lk in LOOKS:
        items.append({"label": lk["label"], "mod": lk["mod"], "title": lk["title"], "author": MODS[lk["mod"]]["author"],
                      "notes": look_notes(lk), "waiting": "、".join(lk.get("needs") or [])})
    for char, label, title in EARLIER:
        items.append({"label": label, "mod": "Earlier", "title": title, "character": char, "author": "", "notes": ""})
    path = os.path.join(ARCHIVE, "_mod画廊", "looks.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"mods": mods, "looks": items}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = subprocess.run([sys.executable, os.path.join(SB, "mod_gallery.py"), "--looks", path, "--date",
                        time.strftime("%Y-%m-%d %H:%M")], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print(r.stdout + r.stderr)


def main():
    step, names = sys.argv[1], sys.argv[2:]
    looks = pick(names)
    jobs = 3
    if step == "gallery":
        return do_gallery(looks)
    if step == "archive":
        do_archive(looks)
    elif step == "sources":
        do_sources(looks)
    elif step == "registry":
        do_registry(looks)
    elif step == "hq":
        with cf.ThreadPoolExecutor(jobs) as ex:
            for p, rc, ok, dt, tail in ex.map(hq_one, looks):
                print("  hq %-44s rc %s HQ %s %4d s %s" % (p, rc, ok, dt, tail), flush=True)
    elif step == "addon":
        with cf.ThreadPoolExecutor(jobs) as ex:
            for p, keep in ex.map(addon_one, looks):
                print("  addon %-40s %s" % (p, " | ".join(k[:120] for k in keep if k.startswith(("upgraded",
                                                                                                "MISSING", "REEXPORT")))),
                      flush=True)
    elif step == "readme":
        for lk in looks:
            print("  readme", readme_one(lk))
    else:
        raise SystemExit("unknown step " + step)


if __name__ == "__main__":
    main()
