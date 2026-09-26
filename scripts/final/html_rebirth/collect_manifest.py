"""把 export_ff7rb_models.ps1 的 ff7rb_models_manifest.json 转成画廊 manifest。

不开 Blender：材质化 worker 已把网格/骨骼/材质/缺贴图统计写进 manifest，这里只补上
预览图路径（render_blend_preview.py 出的 <变体>_preview.png）、角色/服装拆分和告警。

  python collect_manifest.py [materialized 目录] [输出 manifest] [--extra 目录 ...] [--mods mods 清单]

默认读 D:/ff7rebirth_exports/materialized/ff7rb_models_manifest.json，
写 <同目录>/ff7rebirth_gallery_manifest.json。只存本机路径与统计，不含游戏素材。

--extra：其它材质化目录（默认 D:/ff7rebirth_exports/cli_materialized，即 ff7rb_cli_export.py
走 CUE4Parse CLI 补出来的、FModel 导不出的变体）。同名变体以 extra 里的 PASS 为准，
所以 FModel 那边的 FAIL / NO_MODEL 条目会被补上。
--mods：Nexus mod 的画廊条目（ff7_mod_export.py 写的 gallery_mods.json），kind = mod。

归档（scripts/archive）以后 D 盘的导出可能已经删了：D 盘上找不到的条目沿用归档里那份 manifest
（E:/game_export/FF7Rebirth/_meta/ff7rebirth_gallery_manifest.json），画廊不会少卡片。这些条目的路径还是
D 盘的，生成画廊后跑 ``archive_exports.py ff7rebirth``（或 ``--relink``）改到 E 盘。
"""

import argparse
import json
import os
import re

DEFAULT_ROOT = r"D:\ff7rebirth_exports\materialized"
DEFAULT_EXTRA = [r"D:\ff7rebirth_exports\cli_materialized"]
DEFAULT_MODS = r"D:\ff7rebirth_exports\mods\gallery_mods.json"
ARCHIVED = r"E:\game_export\FF7Rebirth\_meta\ff7rebirth_gallery_manifest.json"

# PC0002_08_Tifa_CostaClothing -> 编号 PC0002_08 / 角色 Tifa / 变体 CostaClothing
LABEL_RE = re.compile(r"^(PC\d{4}_\d{2})_([A-Za-z0-9]+)_(.+)$")
PATCH_RE = re.compile(r"blood|cutbrood|tear|wet", re.IGNORECASE)


def load_results(root, route):
    path = os.path.join(root, "ff7rb_models_manifest.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        src = json.load(f)
    out = []
    for r in src.get("results", []):
        r = dict(r)
        r["_route"] = route
        out.append(r)
    return out


def entry_for(r):
    label = r.get("variant", "")
    if r.get("status") != "PASS":
        return None
    blend = (r.get("outputs") or {}).get("blend") or r.get("output") or ""
    if not blend or not os.path.isfile(blend):
        return None
    m = LABEL_RE.match(label)
    code, char, variant = (m.group(1), m.group(2), m.group(3)) if m else ("", label, "")
    preview = os.path.splitext(blend)[0] + "_preview.png"
    warnings = []
    if r.get("missingBase"):
        warnings.append("缺底色贴图 %d：%s" % (len(r["missingBase"]), "; ".join(map(str, r["missingBase"][:4]))))
    if r.get("simplified"):
        warnings.append("材质做了简化：%s" % r["simplified"])
    if r.get("armatures") != 1:
        warnings.append("骨架数 %s" % r.get("armatures"))
    kind = "official"
    if char == "Toad":
        kind = "toad"
    elif code.startswith("PC7"):
        kind = "cutscene"
    elif PATCH_RE.search(variant) and (r.get("vertices") or 0) < 30000:
        kind = "variant"                      # 贴在身体上的血迹/泪痕小网格，不是整个人
    return {
        "label": label, "code": code, "char": char, "variant": variant, "kind": kind,
        "route": r.get("_route", "FModel"),
        "blend": blend,
        "preview": preview if os.path.isfile(preview) else "",
        "blendSize": os.path.getsize(blend),
        "meshes": r.get("meshes", 0), "vertices": r.get("vertices", 0), "polygons": r.get("polygons", 0),
        "bones": r.get("bones", 0), "materials": r.get("materials", 0),
        "alphaMaterials": 0, "textures": r.get("texturesFound", 0),
        "warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=DEFAULT_ROOT)
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--extra", action="append", default=None, help="其它材质化目录（可重复）")
    ap.add_argument("--mods", default=DEFAULT_MODS, help="Nexus mod 画廊条目 JSON（不存在就跳过）")
    a = ap.parse_args()
    out_path = a.out or os.path.join(a.root, "ff7rebirth_gallery_manifest.json")
    extras = a.extra if a.extra is not None else DEFAULT_EXTRA

    by_label = {}
    for r in load_results(a.root, "FModel"):
        e = entry_for(r)
        if e:
            by_label[e["label"]] = e
    for root in extras:
        for r in load_results(root, "CUE4Parse CLI"):
            e = entry_for(r)
            if e:
                by_label[e["label"]] = e          # extra 的 PASS 补上 FModel 的 FAIL / NO_MODEL
    results = sorted(by_label.values(), key=lambda x: x["label"])

    mods = []
    if a.mods and os.path.isfile(a.mods):
        with open(a.mods, encoding="utf-8-sig") as f:
            for e in json.load(f).get("results", []):
                if e.get("blend") and os.path.isfile(e["blend"]):
                    e = dict(e, kind="mod")
                    pv = e.get("preview") or ""
                    e["preview"] = pv if pv and os.path.isfile(pv) else ""
                    e["blendSize"] = os.path.getsize(e["blend"])
                    mods.append(e)
    kept = []
    if os.path.isfile(ARCHIVED):
        have = {x["label"] for x in results + mods}
        with open(ARCHIVED, encoding="utf-8-sig") as f:
            kept = [e for e in json.load(f).get("results", []) if e.get("label") not in have]
        results = sorted(results + [e for e in kept if e.get("kind") != "mod"], key=lambda x: x["label"])
        mods += [e for e in kept if e.get("kind") == "mod"]
        if kept:
            print("归档里补回 %d 条（D 盘上已经没有）" % len(kept))
    manifest = {"game": "FINAL FANTASY VII REBIRTH", "sourceRoot": a.root, "extraRoots": extras,
                "results": results + sorted(mods, key=lambda x: x["label"])}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条，其中 CLI 补 %d、mod %d；%d 张预览)" % (
        out_path, len(manifest["results"]), sum(1 for x in results if x["route"] != "FModel"), len(mods),
        sum(1 for x in manifest["results"] if x["preview"])))


if __name__ == "__main__":
    main()
