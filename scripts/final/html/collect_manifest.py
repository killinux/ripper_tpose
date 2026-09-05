"""汇总 FF7 Remake 批量导出的报告，写成 manifest 供 make_gallery.py 生成画廊。

不需要开 Blender：export_ff7remake_models.ps1 每个包都留了 validate_ff7remake_model.py 的
报告 JSON（网格/顶点/骨骼/材质/缺贴图），直接读 <导出根>\\_blends\\*.json 即可。

  python collect_manifest.py [导出根目录] [manifest 输出路径]

默认导出根 D:\\ff7remake_exports\\player，manifest 写到 <导出根>\\ff7remake_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\ff7remake_exports\player"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "ff7remake_models_manifest.json")
BLEND_DIR = os.path.join(ROOT, "_blends")

# 包目录名：PC0002_01_Tifa_PurpleDress -> 角色 Tifa，变体 PurpleDress，编号 PC0002_01
LABEL_RE = re.compile(r"^(PC\d{4}_\d{2})_([A-Za-z0-9]+)_(.+)$")


def main():
    if not os.path.isdir(BLEND_DIR):
        raise SystemExit("找不到 _blends 目录: %s" % BLEND_DIR)
    results = []
    blends = sorted(f for f in os.listdir(BLEND_DIR) if f.lower().endswith(".blend"))
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
    manifest = {"game": "FINAL FANTASY VII REMAKE INTERGRADE", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


if __name__ == "__main__":
    main()
