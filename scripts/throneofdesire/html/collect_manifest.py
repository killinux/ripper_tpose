"""扫描 Throne of Desire 导出的 .blend，收集统计写成 manifest，供 make_gallery.py 用。

在 Blender 无头下运行（需要打开每个 .blend 读网格/材质信息）：

  blender --background --factory-startup --python collect_manifest.py -- \
      [导出根目录] [manifest 输出路径]

默认导出根 D:\\throneofdesire_exports，manifest 写到
<导出根>\\tod_models_manifest.json。递归扫全部 .blend，按路径分两组：
``female_all\\`` 下的是 export_nude_models.ps1 的批量裸模，其余是单独导出。
manifest 只存本机路径与统计，不含任何游戏素材——和其它脚本同一条规矩。
"""

import bpy
import json
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = argv[0] if argv else r"D:\throneofdesire_exports"
OUT = argv[1] if len(argv) > 1 else os.path.join(ROOT, "tod_models_manifest.json")

BATCH_DIR = "female_all"


def find_preview(blend_path, model):
    """优先同名 <model>_preview.png，否则取同目录第一张 *_preview.png。"""
    folder = os.path.dirname(blend_path)
    exact = os.path.join(folder, model + "_preview.png")
    if os.path.isfile(exact):
        return exact
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith("_preview.png"):
            return os.path.join(folder, name)
    return ""


def load_batch_status(root):
    """读 export_nude_models.ps1 留下的 manifest，取每个模型的状态。"""
    path = os.path.join(root, BATCH_DIR, "female_export_manifest.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:
        return {}
    return {r.get("model"): {"status": r.get("status"), "reason": r.get("reason") or ""}
            for r in data.get("records", []) if r.get("model")}


def main():
    if not os.path.isdir(ROOT):
        raise SystemExit("找不到导出根目录: %s" % ROOT)

    blends = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for name in files:
            if name.lower().endswith(".blend"):
                blends.append(os.path.join(dirpath, name))
    blends.sort()
    if not blends:
        raise SystemExit("导出根目录下没有 .blend: %s" % ROOT)

    batch_status = load_batch_status(ROOT)
    results = []
    for i, path in enumerate(blends, 1):
        folder = os.path.dirname(path)
        model = os.path.basename(folder)
        rel = os.path.relpath(path, ROOT)
        group = "batch" if rel.split(os.sep)[0] == BATCH_DIR else "single"

        bpy.ops.wm.open_mainfile(filepath=path)

        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        images = [im for im in bpy.data.images if im.name != "Render Result"]
        packed = sum(1 for im in images if im.packed_file)
        tris = sum(len(o.data.polygons) for o in meshes)

        warnings = []
        if not armatures:
            warnings.append("没有骨架")
        if packed < len(images):
            warnings.append("有 %d 张贴图未打包进 blend" % (len(images) - packed))
        if not images:
            warnings.append("没有贴图")

        info = batch_status.get(model, {})
        results.append({
            "model": model,
            "group": group,
            "blend": path,
            "preview": find_preview(path, model),
            "blendSize": os.path.getsize(path),
            "meshes": len(meshes),
            "faces": tris,
            "armatures": len(armatures),
            "materials": len(bpy.data.materials),
            "images": len(images),
            "packedImages": packed,
            "batchStatus": info.get("status", ""),
            "batchReason": info.get("reason", ""),
            "warnings": warnings,
        })
        print("[%d/%d] %s group=%s meshes=%d mats=%d imgs=%d %s"
              % (i, len(blends), model, group, len(meshes),
                 len(bpy.data.materials), len(images),
                 "WARN:" + ";".join(warnings) if warnings else ""))

    manifest = {"game": "Throne of Desire", "sourceRoot": ROOT, "results": results}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("MANIFEST=%s (%d 条)" % (OUT, len(results)))


main()
