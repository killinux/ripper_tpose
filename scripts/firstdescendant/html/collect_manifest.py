# -*- coding: utf-8 -*-
"""汇总 The First Descendant 的导出产物（<导出根>\\blend\\<模型>\\），写成画廊 manifest。

不开 Blender：``export_model.ps1`` / ``build_blend.py`` 给每个模型留了 ``build.log``，
最后一行 ``TFD_REPORT={json}`` 里有部件、骨骼、材质槽、贴图、morph 数与告警，直接读；
``materials.json`` 补上每个槽用的材质实例和贴图文件名。分类（后裔 / 皮肤 / 怪 …）、
角色名、编号、包路径来自 ``list_models.py`` 的编目——那要 AES key，没有 key 时加
``--no-catalogue``，退化成按 id 前缀猜。预览用同目录的 preview.png / preview_face.png。

  python collect_manifest.py
  python collect_manifest.py --export-root D:\\tfd_exports --out D:\\tfd_exports\\tfd_models_manifest.json
  python collect_manifest.py --no-catalogue

manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

DEFAULT_EXPORT_ROOT = r"D:\tfd_exports"

# 女性体型的后裔（list_models 的 README 记了判据：Breast_PoseAsset + SKIN/F + F 系动画）
FEMALE = {"viessa", "bunny", "freyna", "gley", "sharen", "valby", "luna", "hailey",
          "ines", "serena", "nell", "harris"}

# 说明：对着渲出来的预览图写的（包里没有正式中文名，这里写外观，不猜官方译名）
NAMES: dict[str, str] = {
    "Viessa": "白色罗纹针织连衣裙（胸前锁孔）+ 玫瑰棕绗缝皮短外套与腰带，银色机械小臂和胫甲，白金色低马尾、有雀斑",
    "Bunny": "银色兔耳头盔（面罩遮住眼睛）+ 藏青紧身衣 + 白色棱面护肩，髋部一圈蓝红电容，重装战靴",
    "Freyna": "绿色挑染短发，黑皮铆钉短夹克 + 墨绿胸衣，露腰，黑皮裤，机械小腿和利爪手套（绿色自发光）",
    "Gley": "银白高盘发 + 黑框眼镜，白色长实验袍 + 红衬衫黑领带，黑皮手套与机械护肩，黑紧身裤 + 战靴",
    "Sharen": "整套银白描金动力装甲，全罩面甲只露出头顶的粉发，碳纤维腹甲，高科技胫甲",
    "Valby": "透明球形头盔（隔着头盔能看见脸）+ 全身白色高光紧身衣 + 青绿色短夹克",
    "Luna": "头戴式耳机 + 棕色短发，灰底荧光黄的装甲连体衣，过膝灰长袜 + 运动鞋，左臂黑臂套与纹身",
    "Hailey": "赤褐短发配白色眉毛，白色野战夹克敞开 + 灰色运动内衣，白工装裤 + 大腿枪套，黑色系带靴",
    "Ines": "铂金短发 + 深肤色，全身黑色高光紧身衣 + 装甲片，露指手套，大腿束带"
            "（手比脸浅：身体和脸用了两张色调不同的皮肤图，游戏靠肤色/染色参数统一，这套没接）",
    "Serena": "铂金波波头，白色连体衣（立领和胸口是黑色蕾丝）+ 灰金护肩，机械手臂，黑色透纱大腿，装甲长靴",
    "Nell": "黑色齐耳短发，全黑长风衣 + 高领紧身衣，皮护肩与手套，黑色长靴（脸用的是 Gley/007 那套材质实例，游戏自己就这么共用的）",
    "Harris": "粉红短发，棕色皮质短飞行夹克 + 白色比基尼上衣，露腰，白色牛仔短裤 + 枪套，兔子图案白球鞋",
    "Bunny_CMN_001": "Bunny 的一套皮肤：橙白红机甲 + 双角头盔（紫色面罩）。头盔是 socket 配件，靠 Bn_Socket_Head 挂在头上",
    "MOB_CMN_1001_A001": "Vulgus 杂兵：湿漉漉的黑色皮肤 + 灰白骨甲（头、肩、胸），利爪",
}

KIND_BY_PREFIX = (
    ("MOB_", "monster"), ("BOS_", "boss"), ("NPC_", "npc"), ("RW_", "weapon"),
    ("MW_", "weapon"), ("PC_ACC", "accessory"), ("FLW_", "fellow"), ("VEH_", "vehicle"),
)


def guess_kind(mid: str) -> str:
    for prefix, kind in KIND_BY_PREFIX:
        if mid.startswith(prefix):
            return kind
    # 皮肤 id 是 <角色>_<类别>_<序号>，类别是固定的几个词
    if re.search(r"_(F|M|MF|CMN|AGT|BOS|CLB|EVO|VAR)_\w+$", mid):
        return "skin"
    return "descendant"


def base_char(mid: str) -> str:
    """Ultimate_Viessa / Viessa_CMN_001 -> Viessa（用来判性别）"""
    name = re.sub(r"^Ultimate_", "", mid)
    return re.split(r"_(F|M|MF|CMN|AGT|BOS|CLB|EVO|VAR)_", name)[0]


def load_catalogue(export_root: str, game_root: str, key_file: str) -> dict[str, dict]:
    import list_models as lm

    paks = os.path.join(game_root, "M1", "Content", "Paks")
    args = argparse.Namespace(aes_key="", aes_key_file=key_file)
    models = lm.build_catalogue(lm.all_paths(paks, lm.read_key(args)))
    lm.annotate(models, export_root)
    by_id: dict[str, dict] = {}
    for m in models:
        by_id.setdefault(m["id"], m)     # 少数 id 重名（不同树里同名网格），留第一条
    print("编目：%d 个模型 / %d 个不同 id（容器目录索引）" % (len(models), len(by_id)))
    return by_id


def read_text(path: str) -> str:
    """build.log may be UTF-8 or (from an older PowerShell ``Tee-Object``) UTF-16."""
    raw = open(path, "rb").read()
    for bom, enc in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"), (b"\xef\xbb\xbf", "utf-8-sig")):
        if raw.startswith(bom):
            return raw.decode(enc, errors="replace")
    if b"\x00" in raw[:400]:                       # UTF-16 without a BOM
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def read_report(log_path: str) -> dict:
    if not os.path.isfile(log_path):
        return {}
    last = ""
    for line in read_text(log_path).splitlines():
        if line.startswith("TFD_REPORT="):
            last = line[len("TFD_REPORT="):].strip()
    try:
        return json.loads(last) if last else {}
    except ValueError:
        return {}


def dir_size(path: str) -> int:
    if not os.path.isdir(path):
        return 0
    return sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path)
               if os.path.isfile(os.path.join(path, f)))


def build(export_root: str, catalogue: dict[str, dict]) -> list[dict]:
    blend_dir = os.path.join(export_root, "blend")
    ids = sorted(d for d in os.listdir(blend_dir)
                 if os.path.isfile(os.path.join(blend_dir, d, d + ".blend")))
    results = []
    for i, mid in enumerate(ids, 1):
        mdir = os.path.join(blend_dir, mid)
        blend = os.path.join(mdir, mid + ".blend")
        rep = read_report(os.path.join(mdir, "build.log"))
        cat = catalogue.get(mid, {})
        parts = rep.get("parts") or []
        mats = rep.get("materials") or {}
        # "socket accessory" 是装配规则生效的说明，不是问题，单独归到 notes
        raw_warnings = list(rep.get("warnings") or [])
        notes = [w for w in raw_warnings if "socket accessory" in w]
        warnings = [w for w in raw_warnings if w not in notes]
        if not rep:
            warnings.append("没有 build.log 报告（是不是手工建的 blend？）")
        if rep.get("missing_textures"):
            warnings.append("有贴图没解析到：" + ", ".join(rep["missing_textures"])[:200])

        preview = os.path.join(mdir, "preview.png")
        face = os.path.join(mdir, "preview_face.png")
        kind = cat.get("kind") or guess_kind(mid)
        char = cat.get("char") or (base_char(mid) if kind in ("descendant", "skin") else "")
        sex = ""
        if kind in ("descendant", "skin"):
            sex = "female" if base_char(mid).lower() in FEMALE else "male"

        results.append({
            "label": mid,
            "name": NAMES.get(mid, ""),
            "kind": kind,
            "char": char,
            "sex": sex,
            "number": cat.get("number", ""),
            "variant": cat.get("variant", ""),
            "ultimate": mid.startswith("Ultimate_"),
            "blend": blend,
            "blendSize": os.path.getsize(blend),
            "textureBytes": dir_size(os.path.join(mdir, "textures")),
            "preview": preview if os.path.isfile(preview) else "",
            "facePreview": face if os.path.isfile(face) else "",
            "outDir": mdir,
            "packages": [p.get("package", "") for p in (cat.get("parts") or [])],
            "parts": [p.get("name", "") for p in parts],
            "partDetails": [{"name": p.get("name", ""), "psk": p.get("psk", ""),
                             "vertices": p.get("vertices", 0), "faces": p.get("faces", 0),
                             "bones": p.get("bones", 0), "slots": p.get("slots", 0),
                             "shapeKeys": p.get("shape_keys", 0)} for p in parts],
            "vertices": sum(p.get("vertices", 0) for p in parts),
            "faces": sum(p.get("faces", 0) for p in parts),
            "bones": (rep.get("rig") or {}).get("bones", 0),
            "meshes": rep.get("meshes", 0),
            "morphs": max((p.get("shape_keys", 0) for p in parts), default=0),
            "materials": len(mats),
            "materialKinds": sorted({v.get("kind", "") for v in mats.values() if v.get("kind")}),
            "materialDetails": [{"material": k, "kind": v.get("kind", ""),
                                 "textures": list(v.get("textures") or [])} for k, v in sorted(mats.items())],
            "textures": rep.get("textures_total", 0),
            "missingTextures": list(rep.get("missing_textures") or []),
            "notes": notes,
            "warnings": warnings,
        })
        print("[%d/%d] %-26s %-10s %-8s %5d 骨 %6d 顶点 %2d 材质 %2d 贴图%s"
              % (i, len(ids), mid, kind, sex or "-", results[-1]["bones"], results[-1]["vertices"],
                 results[-1]["materials"], results[-1]["textures"], "  (!)" if warnings else ""))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    ap.add_argument("--out", default="", help="默认 <导出根>\\tfd_models_manifest.json")
    ap.add_argument("--game-root", default=r"E:\SteamLibrary\steamapps\common\The First Descendant")
    ap.add_argument("--aes-key-file", default=r"D:\tfd_exports\_keys\aes_key.txt")
    ap.add_argument("--no-catalogue", action="store_true",
                    help="不读容器（不需要 AES key），分类按 id 前缀猜")
    args = ap.parse_args()

    export_root = os.path.abspath(args.export_root)
    out = args.out or os.path.join(export_root, "tfd_models_manifest.json")
    if not os.path.isdir(os.path.join(export_root, "blend")):
        raise SystemExit("没有 %s\\blend，先跑 export_model.ps1" % export_root)

    catalogue: dict[str, dict] = {}
    if not args.no_catalogue:
        try:
            catalogue = load_catalogue(export_root, args.game_root, args.aes_key_file)
        except SystemExit as exc:        # 缺 key 之类，退化即可，不必中断
            print("跳过编目（%s），分类按 id 猜" % exc)
        except Exception as exc:         # noqa: BLE001
            print("跳过编目（%s: %s），分类按 id 猜" % (type(exc).__name__, exc))

    results = build(export_root, catalogue)
    manifest = {"game": "The First Descendant (M1)", "sourceRoot": export_root, "results": results}
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("MANIFEST=%s（%d 条）" % (out, len(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
