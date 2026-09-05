"""把每个 Eve .blend 打成一个可整体拷走的独立文件夹。

每个文件夹 = ``<label>.blend`` + ``textures\\``（该模型用到的全部贴图，路径改成 ``//textures/..`` 相对
引用）+ ``preview.png`` / ``preview_face.png`` + ``README.txt`` + ``package.json``。
文件夹拷到任何一台装了 Blender 3.6+ 的电脑上都能直接双击打开、贴图齐全。

  blender --background --python package_outfits.py -- [选项]

选项
  --blend-dir DIR   源 .blend 目录（默认 D:\\stellarblade_exports\\blender）
  --out-root DIR    输出根目录（默认 D:\\stellarblade_exports\\packages），每个模型一个子目录
  --only A B ...    只打包这些 label（不带 .blend），可多个
  --force           已有 package.json 的也重做
  --lane I --lanes N  多进程分片：按排序后的 label 取第 I 片（I 从 0 起）
  --include-probe   连 Eve_Face003_UEFormat36_test（UEFormat 导入探针，没有贴图）也打包
  --zip             每个文件夹再打一个同名 .zip 放在 out-root 下

  python package_outfits.py --index [--out-root DIR]
    不开 Blender，扫描各子目录的 package.json 写 <out-root>\\README.md 总索引。

流程：open_mainfile -> 把每张 FILE 图片拷进 textures\\（同名不同源的加父目录前缀）-> 图片路径先指向
绝对新位置 -> save_as 到目标 -> make_paths_relative -> 再存一次 -> 重新打开校验每张图片都是 //textures/
相对路径且文件在包内。材质上 validate_eve.py 留的 stellarblade_preview_texture 也改成包内相对路径。
"""

import argparse
import json
import os
import shutil
import sys
import zipfile

try:
    import bpy
except ImportError:  # --index 模式在普通 python 下跑
    bpy = None

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_LABEL = "Eve_Face003_UEFormat36_test"
SPECIAL_NAMES = {
    "Eve_Standard_validation": ("标准 Eve（CH_P_EVE_01_Body 默认身体）", "Eve"),
    "Eve_Nude_Barefoot": ("裸模（EveOriginalProportions mod，赤足）", "Eve"),
}
KIND_TEXT = {
    "official": "本体服装 (base game outfit)",
    "dlc": "联动 DLC (collab DLC)",
    "nude": "裸模 mod (nude mod, not in the base game)",
    "other": "其它 (other)",
}


def load_outfit_names():
    """借用画廊 manifest 脚本里的编号->名称表，避免两份表。"""
    saved = sys.argv
    sys.argv = [saved[0]]
    try:
        sys.path.insert(0, os.path.join(HERE, "html"))
        import collect_manifest  # noqa: E402
    finally:
        sys.argv = saved
    return collect_manifest


def describe(label, cm):
    m = cm.PKG_RE.match(label)
    if m:
        name, group = cm.outfit_name(m.group(2))
        kind = "dlc" if m.group(2).startswith(("Nier_", "Nikke_")) else "official"
        return m.group(1), name, group, kind
    if label in SPECIAL_NAMES:
        name, group = SPECIAL_NAMES[label]
        return label, name, group, ("nude" if "Nude" in label else "other")
    return label, label, "Eve", "other"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend-dir", default=r"D:\stellarblade_exports\blender")
    p.add_argument("--out-root", default=r"D:\stellarblade_exports\packages")
    p.add_argument("--validation-dir", default=None, help="默认 <blend-dir>\\..\\validation")
    p.add_argument("--only", nargs="*", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--lane", type=int, default=0)
    p.add_argument("--lanes", type=int, default=1)
    p.add_argument("--include-probe", action="store_true")
    p.add_argument("--no-extra", action="store_true", help="不附带服装目录里没接到材质上的 _N/_ORM/_Mask 贴图")
    p.add_argument("--zip", action="store_true")
    p.add_argument("--index", action="store_true")
    return p.parse_args(argv)


def unique_texture_name(basename, src, taken):
    """同名不同源时用父目录名做前缀（如 Textures\\Old\\Tex_P_EVE_Head_A.png -> Old_Tex_P_EVE_Head_A.png）。"""
    key = basename.lower()
    if key not in taken or os.path.normcase(taken[key]) == os.path.normcase(src):
        return basename
    parent_dir = os.path.dirname(src)
    parent = os.path.basename(parent_dir) or "x"
    if parent.lower() in ("textures", "texture"):     # 只写 Textures_ 没意义，用上一级（如 CH_P_EVE_Head）
        parent = os.path.basename(os.path.dirname(parent_dir)) or parent
    cand = parent + "_" + basename
    n = 2
    while cand.lower() in taken and os.path.normcase(taken[cand.lower()]) != os.path.normcase(src):
        cand = "%s_%d_%s" % (parent, n, basename)
        n += 1
    return cand


SHARED_PART_DIRS = ("ch_p_eve_head", "ch_p_eve_hair", "ch_p_eve_face", "ch_p_eve_body")


def copy_extra_maps(textures, by_src, tex_dir, blend_dir):
    """把服装自己的 Textures\\ 目录里其余 PNG（法线 / ORM / Mask / 换色）拷到 textures\\extra\\。

    只看已接上贴图的来源目录：目录名是 Textures、上一级是 CH_P_EVE_<服装>（不含共享的
    Head / Hair 目录）。这些图没接到材质节点上，给拿到包的人自己接。
    """
    extra_dir = os.path.join(tex_dir, "extra")
    done_dirs = set()
    extras = []
    export_root = os.path.dirname(os.path.abspath(blend_dir))
    for t in textures:
        src_dir = os.path.dirname(os.path.join(export_root, *t["source"].split("/")))
        parent = os.path.basename(os.path.dirname(src_dir))
        if os.path.basename(src_dir).lower() not in ("textures", "texture", "tex") or not parent.lower().startswith("ch_p_eve_"):
            continue
        if parent.lower() in SHARED_PART_DIRS or os.path.normcase(src_dir) in done_dirs:
            continue
        done_dirs.add(os.path.normcase(src_dir))
        for f in sorted(os.listdir(src_dir)):
            full = os.path.join(src_dir, f)
            if not f.lower().endswith(".png") or not os.path.isfile(full) or os.path.normcase(full) in by_src:
                continue
            os.makedirs(extra_dir, exist_ok=True)
            dst = os.path.join(extra_dir, f)
            if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(full):
                shutil.copy2(full, dst)
            extras.append({
                "file": "textures/extra/" + f, "bytes": os.path.getsize(full),
                "source": os.path.relpath(full, export_root).replace("\\", "/"),
            })
    return extras


def relativize_custom_props(export_root):
    """把各数据块自定义属性里以导出根开头的绝对路径改成 'umodel_.../x.psk' 这种相对写法。"""
    root = os.path.normcase(os.path.abspath(export_root)) + os.sep
    changed = 0
    for coll in (bpy.data.objects, bpy.data.materials, bpy.data.meshes, bpy.data.armatures, bpy.data.scenes):
        for block in coll:
            for key in list(block.keys()):
                val = block.get(key)
                if not isinstance(val, str) or not val or not os.path.isabs(val):
                    continue
                if os.path.normcase(os.path.abspath(val)).startswith(root):
                    block[key] = os.path.relpath(os.path.abspath(val), export_root).replace("\\", "/")
                    changed += 1
    return changed


def read_report(validation_dir, label):
    path = os.path.join(validation_dir, label + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_readme(dest, package, name, kind, report, textures, extras, blend_name, notes):
    totals = report.get("totals") or {}
    morphs = (report.get("source_morph_targets") or {}).get("source_count", 0)
    lines = [
        "Stellar Blade - Eve - %s" % name,
        "=" * 60,
        "",
        "包名 / Package : %s" % package,
        "服装 / Outfit  : %s" % name,
        "类型 / Kind    : %s" % KIND_TEXT[kind],
        "",
        "这个文件夹是独立的：.blend 里的贴图全部用 //textures/ 相对路径引用，整个文件夹拷到别的电脑",
        "（保持目录结构不变）直接双击 .blend 就能打开，不需要本机的任何其它文件。",
        "This folder is self-contained: every texture is referenced relatively from textures\\, so copy the",
        "whole folder (keep its layout) to any PC with Blender and just open the .blend.",
        "",
        "文件 / Files",
        "  %s" % blend_name,
        "      Blender 3.6.15 保存；Blender 3.6 及更新版本（4.x）都能打开。",
        "      Saved with Blender 3.6.15; opens in 3.6 and newer (4.x).",
        "  textures\\           %d 张 PNG，材质节点里已经接好 / %d PNGs, already wired in the materials" % (len(textures), len(textures)),
        "  textures\\extra\\     %d 张服装自己的法线 / ORM / Mask / 换色贴图，没接节点，按需自己接" % len(extras),
        "                       %d extra maps (_N / _ORM / _Mask / recolour) from the outfit's own texture folder, not wired" % len(extras),
        "  preview.png          正面预览 / front preview",
        "  preview_face.png     脸部特写 / face close-up",
        "  package.json         清单：贴图来源、网格统计 / manifest: texture sources, mesh stats",
        "",
        "模型 / Model",
        "  网格 / meshes   : %s" % totals.get("meshes", "?"),
        "  顶点 / vertices : %s" % totals.get("vertices", "?"),
        "  骨骼 / bones    : %s（单一骨架 Eve_Armature，可直接摆姿势 / one armature, pose-ready）" % totals.get("bones", "?"),
        "  表情 / morphs   : %s（Face_003 网格的 Shape Keys / shape keys on the Face_003 mesh）" % morphs,
        "  组成 / parts    : 服装身体 + 脸 Face_003 + 发型 + 马尾（+ 短发束）",
        "                    outfit body + Face_003 head + hair + ponytail (+ short hair strands)",
        "",
        "怎么用 / How to use",
        "  1. 打开 .blend，视口切到 Material Preview 就能看到贴图。",
        "     Open the .blend and switch the viewport to Material Preview to see the textures.",
        "  2. 选中 Eve_Armature 进 Pose Mode 摆姿势；表情在 Face_003 的 Object Data > Shape Keys。",
        "     Select Eve_Armature > Pose Mode to pose; expressions are Shape Keys on Face_003.",
        "  3. 要导去别的软件用 File > Export（FBX / glTF）。",
        "     Export to other tools with File > Export (FBX / glTF).",
        "",
        "材质说明 / Materials",
        "  皮肤、服装、头发、眼睛都是 Principled BSDF + 贴图；只接了颜色（Base Color）和必要的透明/法线，",
        "  金属度、粗糙度是预览用的近似值。textures\\extra\\ 里是服装自己的 _N/_ORM/_Mask 贴图，要更细的效果自己再接。",
        "  Materials are Principled BSDF with the colour (and needed alpha/normal) maps wired; roughness/metallic",
        "  are preview approximations. The outfit's _N/_ORM/_Mask maps sit in textures\\extra\\ for you to wire.",
    ]
    if notes:
        lines += ["", "备注 / Notes"] + ["  - " + n for n in notes]
    lines += [
        "",
        "来源 / Source",
        "  Stellar Blade (c) SHIFT UP / Sony Interactive Entertainment。模型与贴图版权归原公司，仅供个人学习研究。",
        "  Model and textures belong to their owners; for personal study only.",
        "  提取管线 / pipeline: ripper_tpose/scripts/stellarblade (UE Viewer -> Blender 3.6, validate_eve.py).",
        "",
    ]
    with open(os.path.join(dest, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write("\n".join(lines))


def package_one(label, args, cm, validation_dir):
    src_blend = os.path.join(args.blend_dir, label + ".blend")
    dest = os.path.join(args.out_root, label)
    marker = os.path.join(dest, "package.json")
    if os.path.isfile(marker) and not args.force:
        with open(marker, encoding="utf-8") as fh:
            info = json.load(fh)
        if args.zip and not os.path.isfile(os.path.join(args.out_root, label + ".zip")):
            info["zip"] = write_zip(dest, label, args.out_root)
            with open(marker, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(info, fh, ensure_ascii=False, indent=1)
            print("[pkg] ZIP  %s (已有包，只补 zip)" % label, flush=True)
        else:
            print("[pkg] SKIP %s (已有 package.json)" % label, flush=True)
        return info
    package, name, group, kind = describe(label, cm)
    tex_dir = os.path.join(dest, "textures")
    if os.path.isdir(tex_dir):          # 重做时清掉旧贴图，别留上一版的文件
        shutil.rmtree(tex_dir)
    os.makedirs(tex_dir, exist_ok=True)
    for stale in os.listdir(dest):
        if stale.endswith((".blend1", ".blend@")):
            os.remove(os.path.join(dest, stale))

    bpy.ops.wm.open_mainfile(filepath=src_blend, load_ui=False)
    bpy.context.preferences.filepaths.save_version = 0

    taken = {}      # 目标文件名(lower) -> 源绝对路径
    by_src = {}     # 源绝对路径(normcase) -> 目标文件名
    textures = []
    problems = []
    for im in bpy.data.images:
        if im.type != "IMAGE" or im.source != "FILE":
            continue
        src = bpy.path.abspath(im.filepath)
        if not src or not os.path.isfile(src):
            problems.append("missing source texture: %s (%s)" % (im.name, im.filepath))
            continue
        src_abs = os.path.abspath(src)
        key = os.path.normcase(src_abs)
        if key in by_src:
            dest_name = by_src[key]
        else:
            dest_name = unique_texture_name(os.path.basename(src_abs), src_abs, taken)
            taken[dest_name.lower()] = src_abs
            by_src[key] = dest_name
            dst = os.path.join(tex_dir, dest_name)
            if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src_abs):
                shutil.copy2(src_abs, dst)
            textures.append({
                "file": "textures/" + dest_name,
                "bytes": os.path.getsize(src_abs),
                "source": os.path.relpath(src_abs, os.path.dirname(os.path.abspath(args.blend_dir))).replace("\\", "/"),
                "images": [],
            })
        for t in textures:
            if t["file"] == "textures/" + dest_name:
                t["images"].append(im.name)
        im.filepath = os.path.join(tex_dir, dest_name)   # 先绝对，保存后再统一转相对

    # 服装自己的贴图目录里没接到材质上的 _N / _ORM / _Mask 等也一并给（textures\extra\，不接节点）
    extras = [] if args.no_extra else copy_extra_maps(textures, by_src, tex_dir, args.blend_dir)

    # validate_eve.py 留在材质上的预览贴图路径也改成包内相对路径
    for mat in bpy.data.materials:
        p = mat.get("stellarblade_preview_texture")
        if isinstance(p, str) and p:
            key = os.path.normcase(os.path.abspath(p))
            if key in by_src:
                mat["stellarblade_preview_texture"] = "textures/" + by_src[key]
    bpy.context.scene.render.filepath = "//render.png"
    # 对象上 stellarblade_source 之类记录的源 PSK 绝对路径改成相对导出根，别把本机路径带给别人
    relativize_custom_props(os.path.dirname(os.path.abspath(args.blend_dir)))

    blend_name = label + ".blend"
    dest_blend = os.path.join(dest, blend_name)
    bpy.ops.wm.save_as_mainfile(filepath=dest_blend, relative_remap=True, compress=False, copy=False)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(filepath=dest_blend, compress=False)
    for stale in os.listdir(dest):
        if stale.endswith(".blend1"):
            os.remove(os.path.join(dest, stale))

    # 重新打开校验：每张图片必须是 //textures/ 相对路径且文件在包内
    bpy.ops.wm.open_mainfile(filepath=dest_blend, load_ui=False)
    checked = 0
    tex_prefix = os.path.normcase(os.path.abspath(tex_dir)) + os.sep
    for im in bpy.data.images:
        if im.type != "IMAGE" or im.source != "FILE":
            continue
        fp = im.filepath.replace("\\", "/")
        ap = os.path.abspath(bpy.path.abspath(im.filepath))
        inside = os.path.normcase(ap).startswith(tex_prefix)
        if not fp.startswith("//textures/") or not inside or not os.path.isfile(ap):
            problems.append("bad path after save: %s -> %s" % (im.name, im.filepath))
        checked += 1
    for lib in bpy.data.libraries:
        problems.append("linked library: %s" % lib.filepath)

    # 预览与报告
    report = read_report(validation_dir, label)
    gallery_png = os.path.join(args.blend_dir, label + "_gallery.png")
    val_png = os.path.join(validation_dir, label + ".png")
    face_png = os.path.join(validation_dir, label + "_face.png")
    if os.path.isfile(gallery_png):
        shutil.copy2(gallery_png, os.path.join(dest, "preview.png"))
    elif os.path.isfile(val_png):
        shutil.copy2(val_png, os.path.join(dest, "preview.png"))
    if os.path.isfile(face_png):
        shutil.copy2(face_png, os.path.join(dest, "preview_face.png"))
    notes = []
    if label == "Eve_CH_P_EVE_11_1":
        notes.append("这个包自带 Raven 发型，管线又装了 Eve 默认发型，头上有两套头发，按需删一套。"
                     " / This package ships its own (Raven) hair and also got Eve's default hair; delete one.")
    if kind == "nude":
        notes.append("来自 EveOriginalProportions mod，不是游戏原版资源。 / From the EveOriginalProportions mod, not a stock asset.")
    if kind == "dlc":
        notes.append("联动 DLC 服装。 / Collaboration DLC outfit.")
    write_readme(dest, package, name, kind, report, textures, extras, blend_name, notes)

    totals = report.get("totals") or {}
    info = {
        "label": label, "package": package, "name": name, "group": group, "kind": kind,
        "blend": blend_name, "blender_version": bpy.app.version_string,
        "blend_bytes": os.path.getsize(dest_blend),
        "textures": textures, "texture_bytes": sum(t["bytes"] for t in textures),
        "extra_textures": extras, "extra_bytes": sum(t["bytes"] for t in extras),
        "images_checked": checked,
        "meshes": totals.get("meshes", 0), "vertices": totals.get("vertices", 0),
        "bones": totals.get("bones", 0),
        "morphs": (report.get("source_morph_targets") or {}).get("source_count", 0),
        "problems": problems,
    }
    if args.zip:
        info["zip"] = write_zip(dest, label, args.out_root)
    with open(marker, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    total_mb = (info["blend_bytes"] + info["texture_bytes"] + info["extra_bytes"]) / 1e6
    print("[pkg] %s %s -> %s | %d tex + %d extra, %.0f MB%s" % (
        "WARN" if problems else "OK", label, name, len(textures), len(extras), total_mb,
        (" | " + "; ".join(problems)) if problems else ""), flush=True)
    return info


def write_zip(dest, label, out_root):
    """把 <out_root>\\<label>\\ 整个打成 <out_root>\\<label>.zip（zip 里带一层同名目录）。"""
    zpath = os.path.join(out_root, label + ".zip")
    tmp = zpath + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for root, _dirs, files in os.walk(dest):
            for f in sorted(files):
                full = os.path.join(root, f)
                zf.write(full, os.path.relpath(full, out_root))
    if os.path.isfile(zpath):
        os.remove(zpath)
    os.replace(tmp, zpath)
    return zpath


def human(n):
    return "%.1f GB" % (n / 1e9) if n >= 1e9 else "%.0f MB" % (n / 1e6)


def write_index(out_root):
    rows = []
    for d in sorted(os.listdir(out_root)):
        marker = os.path.join(out_root, d, "package.json")
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as fh:
                rows.append(json.load(fh))
    kinds = {"official": "本体服装", "dlc": "联动 DLC", "nude": "裸模 mod", "other": "其它"}
    lines = [
        "# Stellar Blade · Eve 独立模型包（每个文件夹可单独拷走）",
        "",
        "每个子目录都是一个完整、自足的模型：`<label>.blend` + `textures\\` + 预览 + `README.txt` + `package.json`。",
        "贴图全部是 `//textures/` 相对路径，整个子目录拷到别的电脑直接打开即可（Blender 3.6 及以上）。",
        "由 `ripper_tpose\\scripts\\stellarblade\\package_outfits.py` 从 `..\\blender\\` 的 .blend 生成。",
        "",
        "| 文件夹 | 服装 | 类型 | 网格 | 顶点 | 骨骼 | 表情 | 贴图（已接 + 附带） | 大小 | 问题 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    total = 0
    for r in rows:
        size = r["blend_bytes"] + r["texture_bytes"] + r.get("extra_bytes", 0)
        total += size
        lines.append("| `%s` | %s | %s | %d | %d | %d | %d | %d + %d | %s | %s |" % (
            r["label"], r["name"], kinds.get(r["kind"], r["kind"]), r["meshes"], r["vertices"], r["bones"],
            r["morphs"], len(r["textures"]), len(r.get("extra_textures", [])), human(size),
            "; ".join(r["problems"]) if r["problems"] else ""))
    lines += ["", "合计 %d 个模型包，%s。" % (len(rows), human(total)), ""]
    with open(os.path.join(out_root, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    with open(os.path.join(out_root, "packages_index.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("INDEX %d packages %s -> %s" % (len(rows), human(total), os.path.join(out_root, "README.md")))
    bad = [r["label"] for r in rows if r["problems"]]
    if bad:
        print("WITH PROBLEMS: " + ", ".join(bad))


def main():
    args = parse_args()
    if args.index:
        write_index(args.out_root)
        return
    if bpy is None:
        raise SystemExit("打包要在 Blender 里跑：blender --background --python package_outfits.py -- ...")
    cm = load_outfit_names()
    validation_dir = args.validation_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.blend_dir)), "validation")
    labels = sorted(f[:-6] for f in os.listdir(args.blend_dir) if f.lower().endswith(".blend"))
    if not args.include_probe:
        labels = [l for l in labels if l != PROBE_LABEL]
    if args.only:
        wanted = {o[:-6] if o.lower().endswith(".blend") else o for o in args.only}
        missing = wanted - set(labels)
        if missing:
            raise SystemExit("没有这些 .blend: " + ", ".join(sorted(missing)))
        labels = [l for l in labels if l in wanted]
    labels = labels[args.lane::args.lanes]
    os.makedirs(args.out_root, exist_ok=True)
    print("[pkg] lane %d/%d: %d 个模型 -> %s" % (args.lane, args.lanes, len(labels), args.out_root), flush=True)
    results = [package_one(l, args, cm, validation_dir) for l in labels]
    bad = [r["label"] for r in results if r["problems"]]
    print("PACKAGE_DONE lane=%d ok=%d problems=%d%s" % (
        args.lane, len(results) - len(bad), len(bad), (" " + ",".join(bad)) if bad else ""), flush=True)


if __name__ == "__main__":
    main()
