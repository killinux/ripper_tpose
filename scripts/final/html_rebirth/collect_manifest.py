"""把 export_ff7rb_models.ps1 的 ff7rb_models_manifest.json 转成画廊 manifest。

不开 Blender：材质化 worker 已把网格/骨骼/材质/缺贴图统计写进 manifest，这里只补上
预览图路径（render_blend_preview.py 出的 <变体>_preview.png）、角色/服装拆分和告警。

  python collect_manifest.py [materialized 目录] [输出 manifest]

默认读 D:\\ff7rebirth_exports\\materialized\\ff7rb_models_manifest.json，
写 <同目录>\\ff7rebirth_gallery_manifest.json。只存本机路径与统计，不含游戏素材。
"""

import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\ff7rebirth_exports\materialized"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "ff7rebirth_gallery_manifest.json")
SRC = os.path.join(ROOT, "ff7rb_models_manifest.json")

# PC0002_08_Tifa_CostaClothing -> 编号 PC0002_08 / 角色 Tifa / 变体 CostaClothing
LABEL_RE = re.compile(r"^(PC\d{4}_\d{2})_([A-Za-z0-9]+)_(.+)$")


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        src = json.load(f)
    results = []
    for r in src.get("results", []):
        label = r.get("variant", "")
        if r.get("status") != "PASS":
            continue
        blend = (r.get("outputs") or {}).get("blend") or r.get("output") or ""
        if not blend or not os.path.isfile(blend):
            continue
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
        results.append({
            "label": label, "code": code, "char": char, "variant": variant, "kind": kind,
            "blend": blend,
            "preview": preview if os.path.isfile(preview) else "",
            "blendSize": os.path.getsize(blend),
            "meshes": r.get("meshes", 0), "vertices": r.get("vertices", 0), "polygons": r.get("polygons", 0),
            "bones": r.get("bones", 0), "materials": r.get("materials", 0),
            "alphaMaterials": 0, "textures": r.get("texturesFound", 0),
            "warnings": warnings,
        })
    results.sort(key=lambda x: x["label"])
    manifest = {"game": "FINAL FANTASY VII REBIRTH", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条，%d 张预览)" % (OUT, len(results), sum(1 for x in results if x["preview"])))


if __name__ == "__main__":
    main()
