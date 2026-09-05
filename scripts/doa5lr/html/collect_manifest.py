"""扫描 DOA5LR 导出的 .blend，收集统计写成 manifest，供 make_gallery.py 生成画廊。

在 Blender 无头下运行（需要打开每个 .blend 读网格/材质信息）：

  blender --background --factory-startup --python collect_manifest.py -- \
      [导出根目录] [manifest 输出路径]

默认导出根 D:\\doa5lr_exports，manifest 写到 <导出根>\\doa5lr_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import bpy
import json
import os
import re
import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = argv[0] if argv else r"D:\doa5lr_exports"
OUT = argv[1] if len(argv) > 1 else os.path.join(ROOT, "doa5lr_models_manifest.json")

BLEND_DIR = os.path.join(ROOT, "_blends")

# 网格名前缀 -> 部件类别。DOA5LR 的网格名带语义：
#   WGT_body*/WGT_cos* 身体+服装，WGT_face*/MOT01_Head* 脸，WGT_hair* 头发
PART_RULES = (
    ("hair", ("wgt_hair", "wgt_zdmodel")),
    ("face", ("wgt_face", "mot01_head", "wgt_leye", "wgt_reye", "wgt_tooth")),
    ("body", ("wgt_body", "wgt_cos", "wgt_skirt")),
)


def classify_mesh(name):
    low = name.lower()
    for part, prefixes in PART_RULES:
        if any(low.startswith(p) for p in prefixes):
            return part
    return "other"


# 文件名约定：<角色>_<显示名>.blend 是默认服装 COS_001；
# 换装批量出的是 <角色>_<显示名>_<COS|DLC>_<NNN>.blend
COSTUME_RE = re.compile(r"^([A-Z0-9]+)_[A-Za-z0-9]+_(COS|DLC|DLCU)_(\d+)$")


def costume_of(label):
    m = COSTUME_RE.match(label)
    if m:
        return "%s_%s_%s" % (m.group(1), m.group(2), m.group(3))
    return label.split("_")[0] + "_COS_001"


def count_part_textures(root, char_code, costume):
    """按约定的部件目录数贴图（DDS），拿不到就返回 0。"""
    total = {}
    for suffix in (costume[len(char_code) + 1:], "FACE", "HAIR_001"):
        d = os.path.join(root, "%s_%s" % (char_code, suffix))
        if os.path.isdir(d):
            n = 0
            for dirpath, _dirs, files in os.walk(d):
                n += sum(1 for f in files if f.lower().endswith(".dds"))
            total[suffix] = n
    return total


def main():
    if not os.path.isdir(BLEND_DIR):
        raise SystemExit("找不到 _blends 目录: %s" % BLEND_DIR)

    results = []
    blends = sorted(f for f in os.listdir(BLEND_DIR) if f.lower().endswith(".blend"))
    for i, fname in enumerate(blends, 1):
        path = os.path.join(BLEND_DIR, fname)
        label = os.path.splitext(fname)[0]
        char_code = label.split("_")[0]
        costume = costume_of(label)
        preview = os.path.join(BLEND_DIR, label + "_preview.png")

        bpy.ops.wm.open_mainfile(filepath=path)

        parts = {}
        meshes = 0
        for o in bpy.data.objects:
            if o.type != "MESH":
                continue
            meshes += 1
            parts[classify_mesh(o.name)] = parts.get(classify_mesh(o.name), 0) + 1

        alpha_mats = 0
        for m in bpy.data.materials:
            if not m.use_nodes:
                continue
            bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf and bsdf.inputs["Alpha"].links:
                alpha_mats += 1

        warnings = []
        if not parts.get("face"):
            warnings.append("没有脸部网格（导出时漏了 -Face）")
        if not parts.get("hair"):
            warnings.append("没有头发网格（导出时漏了 -Hair）")
        images = [im for im in bpy.data.images if im.name != "Render Result"]
        if len(images) < 10:
            warnings.append("贴图仅 %d 张，原始素材可能就没有贴图" % len(images))

        results.append({
            "label": label,
            "char": char_code,
            "costume": costume,
            "blend": path,
            "preview": preview if os.path.isfile(preview) else "",
            "blendSize": os.path.getsize(path),
            "meshes": meshes,
            "parts": parts,
            "materials": len(bpy.data.materials),
            "alphaMaterials": alpha_mats,
            "images": len(images),
            "partTextures": count_part_textures(ROOT, char_code, costume),
            "warnings": warnings,
        })
        print("[%d/%d] %s meshes=%d mats=%d alpha=%d imgs=%d %s"
              % (i, len(blends), label, meshes, len(bpy.data.materials), alpha_mats,
                 len(images), "WARN:" + ";".join(warnings) if warnings else ""))

    manifest = {"game": "Dead or Alive 5 Last Round", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


main()
