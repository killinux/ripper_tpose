"""汇总 Stellar Blade 导出的 Eve 服装 .blend，写成画廊 manifest。

不开 Blender：export_outfit.ps1 / export_eve.ps1 每套都留了 validate_eve.py 的报告
（<导出根>\\validation\\Eve_<包名>.json，含网格/骨骼/材质匹配/对齐误差），直接读。
预览优先用 blender\\Eve_<包名>_gallery.png（render_blend_preview.py 出的亮预览），
没有就退回 validation\\Eve_<包名>.png（验证渲染，偏暗）。

  python collect_manifest.py [导出根目录] [manifest 输出路径]

默认导出根 D:\\stellarblade_exports，manifest 写到 <导出根>\\stellarblade_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\stellarblade_exports"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "stellarblade_models_manifest.json")
BLEND_DIR = os.path.join(ROOT, "blender")
VAL_DIR = os.path.join(ROOT, "validation")

# 编号 -> 名称（docs/stellar-blade-eve-outfits.md，来源 Stellar Blade Modding Guide ID's Library）
NAMES = {
    "02": "Daily Biker", "03": "Daily Rider", "04": "Daily Denim", "05": "Daily Sailor", "06": "Black Wave",
    "07": "Punk Top", "08": "Prototype Planet Diving Suit V2", "09": "Planet Diving Suit (7th)",
    "09_V02": "Protection Suit (7th)", "10": "Planet Diving Suit (Captain)", "11": "Raven Suit",
    "14": "Planet Diving Suit (3rd)", "14_1": "Planet Diving Suit (3rd) Prototype", "15": "Orca Engineer",
    "15_V02": "Orca Engineer", "16": "Black Kunoichi", "17": "Sporty Yellow", "18": "Daily Mascot",
    "19": "Cybernetic Bondage", "20": "Black Rose", "21": "Sky Ace", "22": "White full dress",
    "23": "Black full dress", "24": "Wasteland Adventurer", "25": "Motivation", "26": "Red Passion",
    "27": "Ocean Maid", "28": "Holliday Rabbit", "29": "Keyhole Suit", "30": "Planet Diving Suit (2nd)",
    "31": "Cybernetic Dress", "32": "Daily Knit Dress", "33": "Peony", "34": "Moutan Peony",
    "35": "Black Pearl", "36": "Junk Mechanic", "37": "Office Style", "39": "Daily Force",
    "40": "Cyber Magician", "41": "Racers High", "42": "Orca Exploration Suit", "43": "Blue Monsoon",
    "45": "Fluffy Bear", "46": "Silver Kunoichi", "47": "Cyber Bunny", "48": "Ocean String",
    "49": "White Pearl", "50": "Four Seconds Everyday Wear", "51": "Four Seconds Destroyed Denim",
    "52": "Four Seconds Black Denim", "53": "Ultimate Bunny", "54": "Neurocircuit Bondage",
    "55": "Prototype Neurolink Suit", "56": "Neurolink Suit", "57": "Neurolink Skin", "58": "War Aegis",
    "59": "War Dress", "60": "Midsummer Red Hood", "61": "Midsummer Alice", "62": "Wave Oblique Monokini",
    "63": "Wave Diver Bikini",
    "Christmas_01": "Santa Dress", "DX": "Photogenic", "Fusion": "Angelic Rose Nano Suit",
    "IberisCos": "Iberis' Costume", "InnerSuit": "Skin Suit", "InnerSuit1": "Skin Suit Blue",
    "OneMillion_01": "Crimson Wings", "RoyalGuard_01": "Royal Guard Suit",
    "Nier_01": "YoRHa Uniform No. 2 Type B (2B)", "Nier_02": "YoRHa Uniform 1",
    "Nier_03": "YoRHa Unofficial Ceremonial Attire", "Nier_04": "YoRHa Type A No. 2 (A2)",
    "Nikke_01": "Scarlet Costume", "Nikke_02": "Elegant Dress (Dorothy)", "Nikke_03": "Elysion Combat Uniform (Rapi)",
    "Nikke_04": "Never Look Back (Anis)", "Nikke_05": "Missing Link (Modernia)", "Nikke_06": "Cooling Suit (Alice)",
}
# 换色变体名（同一 ID 的 TypeB/TypeC/_02）
VARIANT_NAMES = {
    "02_TypeB": "Four Seconds Biker", "04_TypeB": "Four Seconds Denim", "05_TypeB": "Comfort Sailor",
    "06_TypeB": "Wild Wave", "07_Type_B": "Punk Style", "08_Type_B_OrangeRed": "6th V2 (OrangeRed)",
    "08_TypeC": "6th V3", "09_TypeB": "Planet Diving Suit (7th) V2", "09_TypeC": "Planet Diving Suit (7th) V3",
    "14_TypeB": "Planet Diving Suit (3rd) V2", "15_V02_TypeB": "Orca Techie", "16_TypeB": "White Kunoichi",
    "17_TypeB": "Sporty Energy", "18_TypeB": "Comfort Mascot", "19_TypeB": "Autonetic Bondage",
    "20_TypeB": "La Vie en Rose", "20_TypeC": "Angelic Rose", "21_TypeB": "Air Ace",
    "24_TypeB": "Wasteland Explorer", "25_TypeB": "Resonance", "26_TypeB": "Emerald Passion",
    "27_TypeB": "Tidal Maid", "28_typeB": "Holliday Bunny", "29_TypeB": "Stargazer Suit", "29_TypeC": "Keyhole Dress",
    "30_TypeB": "Planet Diving Suit (2nd) V2", "31_TypeB": "Cybernetic Suit", "32_TypeB": "Comfort Knit Dress",
    "33_Body_02": "Hydrangea", "34_body_02": "Black Lotus", "35_TypeB": "Red Pearl", "36_TypeB": "Junk Engineer",
    "37_TypeB": "Crew Style", "39_TypeB": "Comfort Force", "40_TypeB": "Cyber Trickster", "40_TypeC": "Cyber Illusionist",
    "41_TypeB": "Speeders High", "42_TypeB": "Orca Pathfinder", "43_TypeB": "White Monsoon", "45_TypeB": "Pink Bear",
    "46_TypeB": "Shadow Kunoichi", "49_TypeB": "Aqua Pearl", "50_TypeB": "Essential Wear", "52_TypeB": "Classic Denim",
    "53_TypeB": "Extreme Bunny", "55_TypeB": "Prototype Sensate Suit", "57_TypeB": "Sensate Skin", "59_TypeB": "War Suit",
    "DX_TypeB": "Telegenic",
}
PKG_RE = re.compile(r"^Eve_(CH_P_EVE_(.+))$")


def outfit_name(suffix):
    """suffix 形如 45_TypeB / 09_V02 / Nikke_06 / 28NH_typeB -> (显示名, 组编号)"""
    s = suffix
    key = s
    for k in sorted(VARIANT_NAMES, key=len, reverse=True):
        if s.replace("NH", "").lower() == k.lower():
            group = re.match(r"^([0-9]+|[A-Za-z]+_?[0-9]*)", s).group(1)
            return VARIANT_NAMES[k] + ("（无高跟）" if "NH" in s else ""), group
    base = re.match(r"^([0-9]+(?:_V02|_1)?|[A-Za-z]+_?[0-9]*)", s)
    grp = base.group(1) if base else s
    name = NAMES.get(grp) or NAMES.get(grp.split("_")[0]) or ""
    extra = s[len(grp):].strip("_")
    if extra.lower() in ("body",):
        extra = ""
    if "NH" in extra:
        extra = extra.replace("NH", "") + "（无高跟）"
    label = (name + (" " + extra if extra else "")).strip() or s
    return label, grp.split("_")[0]


def main():
    results = []
    blends = sorted(f for f in os.listdir(BLEND_DIR) if f.lower().endswith(".blend"))
    for i, f in enumerate(blends, 1):
        label = f[:-6]
        m = PKG_RE.match(label)
        pkg = m.group(1) if m else label
        suffix = m.group(2) if m else ""
        report_path = os.path.join(VAL_DIR, label + ".json")
        rep = {}
        if os.path.isfile(report_path):
            with open(report_path, encoding="utf-8") as fh:
                rep = json.load(fh)
        totals = rep.get("totals") or {}
        gallery_png = os.path.join(BLEND_DIR, label + "_gallery.png")
        val_png = os.path.join(VAL_DIR, label + ".png")
        preview = gallery_png if os.path.isfile(gallery_png) else (val_png if os.path.isfile(val_png) else "")
        if m:
            name, group = outfit_name(suffix)
            kind = "dlc" if suffix.startswith(("Nier_", "Nikke_")) else "official"
        else:
            name, group, kind = label.replace("Eve_", ""), "Eve", ("nude" if "Nude" in label else "other")
        warnings = []
        if not rep:
            warnings.append("没有验证报告")
        pm = rep.get("preview_materials") or {}
        unmatched = pm.get("unmatched") or pm.get("missing") or []
        if unmatched:
            warnings.append("有材质没匹配到贴图：%s" % ", ".join(map(str, unmatched))[:120])
        al = rep.get("alignment") or {}
        err = al.get("tail_anchor_error")
        if isinstance(err, (int, float)) and err > 1.0:
            warnings.append("马尾锚点误差 %.2f" % err)
        results.append({
            "label": label, "package": pkg, "name": name, "group": group, "kind": kind,
            "blend": os.path.join(BLEND_DIR, f), "preview": preview,
            "facePreview": os.path.join(VAL_DIR, label + "_face.png") if os.path.isfile(os.path.join(VAL_DIR, label + "_face.png")) else "",
            "blendSize": os.path.getsize(os.path.join(BLEND_DIR, f)),
            "meshes": totals.get("meshes", 0), "vertices": totals.get("vertices", 0),
            "polygons": totals.get("polygons", 0), "bones": totals.get("bones", 0),
            "armatures": totals.get("armatures", 0),
            "materials": len((pm.get("body_assignments") or {})),
            "morphs": (rep.get("source_morph_targets") or {}).get("source_count", 0),
            "warnings": warnings,
        })
        print("[%d/%d] %s -> %s (%s)" % (i, len(blends), label, name, kind))
    manifest = {"game": "Stellar Blade", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


if __name__ == "__main__":
    main()
