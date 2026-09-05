"""扫描 DOA6 导出的 .blend，收集统计写成 manifest，供 make_gallery.py 生成画廊。

在 Blender 无头下运行（需要打开每个 .blend 读网格/材质信息）：

  blender --background --factory-startup --python collect_manifest.py -- \
      [导出根目录] [manifest 输出路径]

默认导出根 D:\\doa6_exports，manifest 写到 <导出根>\\doa6_models_manifest.json。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import bpy
import json
import os
import re
import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = argv[0] if argv else r"D:\doa6_exports"
OUT = argv[1] if len(argv) > 1 else os.path.join(ROOT, "doa6_models_manifest.json")

BLEND_DIR = os.path.join(ROOT, "_blends")

# build_blend.py 组装时把网格重命名成 <部件目录名>_sm<N>，所以名字自带语义：
#   MOM_COS_001_sm3 / MOM_FACE_001_sm5 / MOM_HAIR_001_sm0
#   mod 变体的部件目录是 <Label>_cos / _face / _hair（小写）→ HEL_Helena_Nude_cos_sm1
OFFICIAL_COS_RE = re.compile(r"_COS_\d+_sm\d+$", re.I)
MOD_COS_RE = re.compile(r"_cos_sm\d+$")
MOD_PART_RE = re.compile(r"_(cos|face|hair)_sm\d+$")


def classify_mesh(name):
    if "_FACE_" in name.upper():
        return "face"
    if "_HAIR_" in name.upper():
        return "hair"
    if OFFICIAL_COS_RE.search(name) or MOD_COS_RE.search(name):
        return "body"
    return "other"


def is_mod_variant(names):
    """任一部件来自 <Label>_cos/_face/_hair 暂存目录 → 这是社区 mod 变体，不是官方内容。"""
    return any(MOD_PART_RE.search(n) for n in names)


def count_part_textures(root, label, char_code):
    total = {}
    candidates = [("%s_cos" % label, "MOD_COS"), ("%s_face" % label, "MOD_FACE"), ("%s_hair" % label, "MOD_HAIR")]
    for suffix in ("COS_001", "FACE_001", "HAIR_001"):
        candidates.append(("%s_%s" % (char_code, suffix), suffix))
    for dirname, key in candidates:
        d = os.path.join(root, dirname)
        if os.path.isdir(d):
            n = 0
            for dirpath, _dirs, files in os.walk(d):
                n += sum(1 for f in files if f.lower().endswith(".dds"))
            if n:
                total[key] = n
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
        preview = os.path.join(BLEND_DIR, label + "_preview.png")

        bpy.ops.wm.open_mainfile(filepath=path)

        parts = {}
        mesh_names = []
        armatures = 0
        for o in bpy.data.objects:
            if o.type == "ARMATURE":
                armatures += 1
                continue
            if o.type != "MESH":
                continue
            mesh_names.append(o.name)
            k = classify_mesh(o.name)
            parts[k] = parts.get(k, 0) + 1

        alpha_mats = 0
        for m in bpy.data.materials:
            if not m.use_nodes:
                continue
            bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf and bsdf.inputs["Alpha"].links:
                alpha_mats += 1

        images = [im for im in bpy.data.images if im.name != "Render Result"]
        warnings = []
        if not parts.get("face"):
            warnings.append("没有脸部网格")
        if not parts.get("hair"):
            warnings.append("没有头发网格")
        if len(images) < 6:
            warnings.append("贴图仅 %d 张，可能有部件缺贴图" % len(images))

        results.append({
            "label": label,
            "char": char_code,
            "kind": "mod" if is_mod_variant(mesh_names) else "official",
            "blend": path,
            "preview": preview if os.path.isfile(preview) else "",
            "blendSize": os.path.getsize(path),
            "meshes": len(mesh_names),
            "armatures": armatures,
            "parts": parts,
            "materials": len(bpy.data.materials),
            "alphaMaterials": alpha_mats,
            "images": len(images),
            "partTextures": count_part_textures(ROOT, label, char_code),
            "warnings": warnings,
        })
        print("[%d/%d] %s kind=%s meshes=%d mats=%d imgs=%d %s"
              % (i, len(blends), label, results[-1]["kind"], len(mesh_names),
                 len(bpy.data.materials), len(images),
                 "WARN:" + ";".join(warnings) if warnings else ""))

    manifest = {"game": "Dead or Alive 6", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


main()
