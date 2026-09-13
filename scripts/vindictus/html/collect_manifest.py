"""汇总 Vindictus: Defying Fate 的导出产物（<导出根>\\blend\\<模型>\\），写成画廊 manifest。

不开 Blender：export_model.ps1 / build_blend.py 每个模型都留了 build.log，最后一行
``VINDICTUS_REPORT={json}`` 里有部件、骨骼、材质、贴图、重定位与告警，直接读；
spec.json 提供部件的 PSK 来源。预览用同目录的 preview.png / preview_face.png。

  python collect_manifest.py [导出根目录] [manifest 输出路径]

默认导出根 D:\\vindictus_exports，manifest 写到 <导出根>\\vindictus_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\vindictus_exports"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "vindictus_models_manifest.json")
BLEND_DIR = os.path.join(ROOT, "blend")

# 模型 id -> 中文说明（看着预览写的；游戏里没有正式名字，Pre-Alpha 资源只有编号）
NAMES = {
    "Fiona": "Fiona 默认装 · Shiningwill 银甲（master 网格）",
    "Lethita": "Lethita 默认装 · 红缨全身板甲",
    "Fiona_BaseBody": "Fiona 基础身体（SM_pc_fiona_basebody：白 T 恤 + 短裤的旧版素体，旧头已切掉换成现在的脸）",
    "PCM_BaseBody": "男性基础身体（Upper/Lower/Hand/Foot 四件 + Lethita 脸/发）",
    "Shiningwill_legacy": "旧版 Shiningwill 银甲（Biped 骨架，已转正对齐到 Fiona 的脸和头发；自带的旧发型隐藏）",
    "PCF_001": "白衬衫 + 皮短裤 + 系带长靴，颈圈",
    "PCF_001_Temp": "黑色长风衣 + 贝雷帽（WIP：裤子是占位贴图）",
    "PCF_002": "猫耳耳机 + 白色帽衫 + 紫色连体衣",
    "PCF_003": "女巫帽 + 藏青条纹连衣裙 + 单只长手套",
    "PCF_004": "耳机白帽 + 紫色露脐夹克 + 浅色运动裤",
    "PCF_005": "发冠 + 白色仙女裙 + 金色项链耳坠",
    "PCF_006": "发带 + 蓝白条纹连衣裙",
    "PCF_007": "颈圈 + 黑色系带连衣裙",
    "PCF_008": "粉色熊耳连帽衫 + 黑粉运动裤（自带发型）",
    "PCF_009": "黑色西装套装 + 高跟鞋",
    "PCF_010": "白色宽檐帽 + 绿色露肩上衣 + 牛仔短裤（自带发型）",
    "PCF_012": "白帽 + 粉色 Polo 衫 + 银色短裙",
    "PCF_067": "带角全身板甲（全罩头盔）",
    "PCM_001_Temp": "男装 001（Temp）", "PCM_002_Temp": "男装 002（Temp）", "PCM_004_Temp": "男装 004（Temp）",
}


def model_kind(mid):
    low = mid.lower()
    if low in ("fiona", "lethita"):
        return "player"
    if "basebody" in low:
        return "base"
    if low.startswith(("pcf_", "pcm_")) or low.endswith("_legacy"):
        return "outfit"
    if low.startswith(("gnoll", "kobold", "goblin")):
        return "monster"
    return "npc"


def model_body(mid):
    low = mid.lower()
    if low.startswith("pcf") or low in ("fiona", "fiona_basebody"):
        return "PCF"
    if low.startswith("pcm") or low in ("lethita",):
        return "PCM"
    if low.endswith("_legacy"):
        return "PCF"
    return ""


def read_report(log_path):
    if not os.path.isfile(log_path):
        return {}
    last = ""
    for line in open(log_path, encoding="utf-8", errors="replace"):
        if line.startswith("VINDICTUS_REPORT="):
            last = line[len("VINDICTUS_REPORT="):].strip()
    try:
        return json.loads(last) if last else {}
    except ValueError:
        return {}


def main():
    results = []
    dirs = sorted(d for d in os.listdir(BLEND_DIR) if os.path.isfile(os.path.join(BLEND_DIR, d, d + ".blend")))
    for i, mid in enumerate(dirs, 1):
        mdir = os.path.join(BLEND_DIR, mid)
        blend = os.path.join(mdir, mid + ".blend")
        rep = read_report(os.path.join(mdir, "build.log"))
        rig = rep.get("rig") or {}
        parts = rep.get("parts") or []
        warnings = list(rep.get("warnings") or [])
        if not rep:
            warnings.append("没有 build.log 报告")
        if rep.get("missing_textures"):
            warnings.append("有贴图没解析到：%s" % ", ".join(rep["missing_textures"])[:160])
        preview = os.path.join(mdir, "preview.png")
        face = os.path.join(mdir, "preview_face.png")
        results.append({
            "label": mid, "name": NAMES.get(mid, ""), "kind": model_kind(mid), "body": model_body(mid),
            "blend": blend, "blendSize": os.path.getsize(blend),
            "preview": preview if os.path.isfile(preview) else "",
            "facePreview": face if os.path.isfile(face) else "",
            "parts": [p.get("name", "") for p in parts],
            "partDetails": [{"name": p.get("name", ""), "psk": p.get("psk", ""), "vertices": p.get("vertices", 0),
                             "faces": p.get("faces", 0), "bones": p.get("bones", 0)} for p in parts],
            "vertices": sum(p.get("vertices", 0) for p in parts),
            "faces": sum(p.get("faces", 0) for p in parts),
            "bones": rig.get("bones", 0),
            "mergedBones": rig.get("added_from_parts", 0),
            "reposed": list(rig.get("reposed_parts") or []),
            "hidden": list(rig.get("hidden_parts") or []),
            "attached": list(rig.get("attached_to_head") or []),
            "materials": len(rep.get("materials") or {}),
            "materialKinds": sorted({v.get("kind", "") for v in (rep.get("materials") or {}).values() if v.get("kind")}),
            "textures": rep.get("textures_total", 0),
            "warnings": warnings,
        })
        print("[%d/%d] %s -> %s (%s)" % (i, len(dirs), mid, NAMES.get(mid, "?"), model_kind(mid)))
    manifest = {"game": "Vindictus: Defying Fate (2024-03 Pre-Alpha)", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


if __name__ == "__main__":
    main()
