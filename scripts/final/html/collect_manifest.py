"""汇总 FF7 Remake 批量导出的报告，写成 manifest 供 make_gallery.py 生成画廊。

不需要开 Blender：export_ff7remake_models.ps1 每个包都留了 validate_ff7remake_model.py 的
报告 JSON（网格/顶点/骨骼/材质/缺贴图），直接读 <导出根>\\_blends\\*.json 即可。

  python collect_manifest.py [导出根目录] [manifest 输出路径] [--mods gallery_mods.json]

默认导出根 D:\\ff7remake_exports\\player，manifest 写到 <导出根>\\ff7remake_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。

--mods：mod 的画廊条目（ff7_mod_export.py 写的 gallery_mods.json，
默认 D:/ff7remake_exports/mods/gallery_mods.json，不存在就跳过），kind = mod。

归档（scripts/archive）以后 D 盘的导出可能已经删了：D 盘上找不到的条目沿用归档里那份 manifest
（E:/game_export/FF7Remake/_meta/ff7remake_models_manifest.json），画廊不会少卡片。这些条目的路径还是 D 盘的，
生成画廊后跑 ``archive_exports.py ff7remake``（或 ``--relink``）改到 E 盘。
"""

import json
import os
import re
import sys

ARGS = [x for x in sys.argv[1:] if not x.startswith("--")]
MODS = sys.argv[sys.argv.index("--mods") + 1] if "--mods" in sys.argv else "D:/ff7remake_exports/mods/gallery_mods.json"
if MODS in ARGS:
    ARGS.remove(MODS)
ROOT = ARGS[0] if len(ARGS) > 0 else "D:/ff7remake_exports/player"
OUT = ARGS[1] if len(ARGS) > 1 else os.path.join(ROOT, "ff7remake_models_manifest.json")
BLEND_DIR = os.path.join(ROOT, "_blends")
ARCHIVED = "E:/game_export/FF7Remake/_meta/ff7remake_models_manifest.json"

# 包目录名：PC0002_01_Tifa_PurpleDress -> 角色 Tifa，变体 PurpleDress，编号 PC0002_01
LABEL_RE = re.compile(r"^(PC\d{4}_\d{2})_([A-Za-z0-9]+)_(.+)$")


def main():
    if not os.path.isdir(BLEND_DIR) and not os.path.isfile(ARCHIVED):
        raise SystemExit("找不到 _blends 目录: %s" % BLEND_DIR)
    results = []
    blends = sorted(f for f in os.listdir(BLEND_DIR) if f.lower().endswith(".blend")) if os.path.isdir(BLEND_DIR) else []
    if not blends:
        print("%s 里没有 .blend（归档后删了？），官方条目沿用 %s" % (BLEND_DIR, ARCHIVED))
    for i, fname in enumerate(blends, 1):
        label = os.path.splitext(fname)[0]
        path = os.path.join(BLEND_DIR, fname)
        m = LABEL_RE.match(label)
        code, char, variant = (m.group(1), m.group(2), m.group(3)) if m else ("", label, "")
        report_path = os.path.join(BLEND_DIR, label + ".json")
        report = {}
        if os.path.isfile(report_path):
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
        preview = os.path.join(BLEND_DIR, label + "_preview.png")
        missing = report.get("missing_preview_textures") or []
        mats = report.get("materials") or []
        warnings = []
        if not report:
            warnings.append("没有报告 JSON（导出中断？）")
        if missing:
            warnings.append("缺贴图 %d：%s" % (len(missing), "; ".join(
                "%s/%s" % (x.get("material"), x.get("kind")) for x in missing[:4])))
        if report and report.get("armatures") != 1:
            warnings.append("骨架数 %s" % report.get("armatures"))
        # _90/_91 是同网格换贴图的表情/污渍变体，Toad 是蛤蟆形态
        kind = "official"
        if code.endswith(("_90", "_91")):
            kind = "variant"
        elif char == "Toad":
            kind = "toad"
        results.append({
            "label": label,
            "code": code,
            "char": char,
            "variant": variant,
            "kind": kind,
            "blend": path,
            "preview": preview if os.path.isfile(preview) else "",
            "blendSize": os.path.getsize(path),
            "meshes": report.get("meshes", 0),
            "vertices": report.get("vertices", 0),
            "polygons": report.get("polygons", 0),
            "bones": report.get("bones", 0),
            "materials": len(mats),
            "alphaMaterials": sum(1 for x in mats if x.get("alpha")),
            "warnings": warnings,
        })
        print("[%d/%d] %s kind=%s verts=%d mats=%d %s" % (
            i, len(blends), label, kind, results[-1]["vertices"], len(mats),
            "WARN:" + ";".join(warnings) if warnings else ""))
    mods = []
    if MODS and os.path.isfile(MODS):
        with open(MODS, encoding="utf-8-sig") as f:
            for e in json.load(f).get("results", []):
                if e.get("blend") and os.path.isfile(e["blend"]):
                    pv = e.get("preview") or ""
                    mods.append(dict(e, kind="mod", preview=pv if pv and os.path.isfile(pv) else "",
                                     blendSize=os.path.getsize(e["blend"])))
        print("mods: %d 条（%s）" % (len(mods), MODS))
    results += sorted(mods, key=lambda x: x["label"])
    if os.path.isfile(ARCHIVED):
        have = {r["label"] for r in results}
        with open(ARCHIVED, encoding="utf-8-sig") as f:
            kept = [e for e in json.load(f).get("results", []) if e.get("label") not in have]
        if kept:
            print("归档里补回 %d 条（D 盘上已经没有）" % len(kept))
            results = sorted(results + kept, key=lambda x: (x.get("kind") == "mod", x["label"]))
    manifest = {"game": "FINAL FANTASY VII REMAKE INTERGRADE", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


if __name__ == "__main__":
    main()
