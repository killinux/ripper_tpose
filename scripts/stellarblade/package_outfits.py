"""把每个 Eve .blend 打成一个可整体拷走的独立文件夹。

每个文件夹 = ``<label>.blend`` + ``textures\\``（该模型用到的全部贴图，路径改成 ``//textures/..`` 相对
引用）+ ``textures\\extra\\``（服装自己目录里没接节点的 _N / _ORM / _Mask / 换色图）+ ``preview.png`` /
``preview_face.png`` + 中英 ``README.txt`` + ``package.json``。
文件夹拷到任何一台装了 Blender 3.6+ 的电脑上都能直接双击打开、贴图齐全。

  blender --background --factory-startup --python package_outfits.py -- [选项]

``--factory-startup`` 不是可选的：不带它，存进 .blend 的界面来自本机的启动文件（中文工作区名、
文件浏览器里作者的 Documents 路径）。

选项
  --blend-dir DIR   源 .blend 目录（默认 D:\\stellarblade_exports\\blender）
  --out-root DIR    输出根目录（默认 D:\\stellarblade_exports\\packages），每个模型一个子目录
  --only A B ...    只打包这些 label（不带 .blend），可多个
  --force           已有 package.json 的也重做
  --lane I --lanes N  多进程分片：按排序后的 label 取第 I 片（I 从 0 起）
  --no-extra        不附带 textures\\extra\\
  --include-probe   连 Eve_Face003_UEFormat36_test（UEFormat 导入探针，没有贴图）也打包
  --zip             每个文件夹再打一个同名 .zip 放在 out-root 下

  python package_outfits.py --index [--out-root DIR]
    不开 Blender，扫描各子目录的 package.json 写 <out-root>\\README.md 总索引。

流程：open_mainfile -> 收集每张 FILE 图片的来源（同名不同源的两边都加上一级目录名前缀）-> 拷进
textures\\ -> 图片路径先指向绝对新位置 -> save_as 到目标 -> make_paths_relative -> 路径统一成正斜杠
-> 再存一次 -> 重新打开校验每张图片都是 //textures/ 相对路径且文件在包内。对象 / 材质自定义属性里
以导出根开头的绝对路径改成相对，Scene 上其它插件（faceit_*）残留的属性删掉。
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
    "Eve_Standard_validation": ("标准 Eve（CH_P_EVE_01 默认身体）", "Eve"),
    "Eve_Nude_Barefoot": ("裸模（EveOriginalProportions mod，赤足）", "Eve"),
}
KIND_TEXT = {
    "official": "本体服装 (base game outfit)",
    "dlc": "联动 DLC (collab DLC)",
    "nude": "裸模 mod (nude mod, not in the base game)",
    "other": "其它 (other)",
}
# 共享部件目录：脸 / 发 / 参考身体，不算某套服装自己的目录
SHARED_PART_DIRS = ("ch_p_eve_head", "ch_p_eve_hair", "ch_p_eve_face", "ch_p_eve_referencebody")
# 不带 --factory-startup 时中文 Blender 存下来的工作区名 -> 英文
WORKSPACE_NAMES = {
    "布局": "Layout", "建模": "Modeling", "雕刻": "Sculpting", "UV编辑": "UV Editing",
    "纹理绘制": "Texture Paint", "着色": "Shading", "动画": "Animation", "渲染": "Rendering",
    "合成": "Compositing", "几何节点": "Geometry Nodes", "脚本": "Scripting",
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
    args = p.parse_args(argv)
    args.blend_dir = os.path.abspath(args.blend_dir)
    args.out_root = os.path.abspath(args.out_root)
    args.validation_dir = os.path.abspath(args.validation_dir) if args.validation_dir else os.path.join(
        os.path.dirname(args.blend_dir), "validation")
    if args.lanes < 1 or not 0 <= args.lane < args.lanes:
        raise SystemExit("--lane 必须在 0..lanes-1 之间，--lanes >= 1")
    return args


def _prefix_for(src):
    """同名冲突时用来区分的前缀：上一级目录名；目录叫 Textures/Tex 时再上一级（如 CH_P_EVE_Head）。"""
    parent_dir = os.path.dirname(src)
    parent = os.path.basename(parent_dir) or "x"
    if parent.lower() in ("textures", "texture", "tex"):
        parent = os.path.basename(os.path.dirname(parent_dir)) or parent
    return parent


def assign_names(sources):
    """来源绝对路径列表 -> {来源: 目标文件名}。同名（不分大小写）的全部加前缀，与枚举顺序无关。"""
    by_base = {}
    for src in sources:
        by_base.setdefault(os.path.basename(src).lower(), []).append(src)
    names = {}
    for base, group in by_base.items():
        if len(group) == 1:
            names[group[0]] = os.path.basename(group[0])
            continue
        used = set()
        for src in sorted(group, key=os.path.normcase):
            cand = _prefix_for(src) + "_" + os.path.basename(src)
            n = 2
            while cand.lower() in used:
                cand = "%s_%d_%s" % (_prefix_for(src), n, os.path.basename(src))
                n += 1
            used.add(cand.lower())
            names[src] = cand
    return names


def outfit_root_of(path, export_root):
    """从贴图路径往上找服装自己的目录（名字以 CH_P_EVE_ 开头且不是共享部件目录）。"""
    cur = os.path.dirname(os.path.abspath(path))
    stop = os.path.normcase(os.path.abspath(export_root))
    while os.path.normcase(cur).startswith(stop) and len(cur) > len(stop):
        base = os.path.basename(cur)
        if base.lower().startswith("ch_"):          # CH_P_EVE_45、DLC 的 CH_M_NA_961 之类角色目录
            return None if base.lower() in SHARED_PART_DIRS else cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return None


def copy_extra_maps(textures, wired_sources, tex_dir, export_root):
    """把服装自己目录树里其余 PNG（法线 / ORM / Mask / 换色）拷到 textures\\extra\\，不接节点。

    服装目录从已接贴图的来源往上找（01 系在 CH_P_EVE_01\\Tex\\Body、Tex\\Boost，
    49_TypeB 在 CH_P_EVE_49\\Textures\\TypeB），整棵树递归收；同名的用子目录名做前缀。
    """
    roots = []
    for t in textures:
        root = outfit_root_of(os.path.join(export_root, *t["source"].split("/")), export_root)
        if root and os.path.normcase(root) not in {os.path.normcase(r) for r in roots}:
            roots.append(root)
    candidates = []
    seen = set()

    def add(full):
        key = os.path.normcase(full)
        if key in wired_sources or key in seen or not full.lower().endswith(".png"):
            return
        seen.add(key)
        candidates.append(full)

    for root in roots:
        for walk_root, _dirs, files in os.walk(root):
            for f in sorted(files):
                add(os.path.join(walk_root, f))
    # 共享目录（ReferenceBody 皮肤 / Head / Hair）太大且多是别的版本，只带已接贴图的同名副图：
    # 接了 CH_P_EVE_BB_V03_TypeA_A.png 就带 CH_P_EVE_BB_V03_TypeA_N / _DMSE / _ORSS
    for t in textures:
        src = os.path.join(export_root, *t["source"].split("/"))
        if outfit_root_of(src, export_root) is not None:
            continue
        stem = os.path.splitext(os.path.basename(src))[0]
        prefix = stem.rsplit("_", 1)[0] + "_" if "_" in stem else stem
        src_dir = os.path.dirname(src)
        for f in sorted(os.listdir(src_dir)):
            if f.lower().startswith(prefix.lower()):
                add(os.path.join(src_dir, f))
    if not candidates:
        return []
    extra_dir = os.path.join(tex_dir, "extra")
    os.makedirs(extra_dir, exist_ok=True)
    names = assign_names(candidates)
    extras = []
    for full in candidates:
        dst = os.path.join(extra_dir, names[full])
        shutil.copy2(full, dst)
        extras.append({
            "file": "textures/extra/" + names[full], "bytes": os.path.getsize(full),
            "source": os.path.relpath(full, export_root).replace("\\", "/"),
        })
    return extras


def relativize_custom_props(export_root):
    """各数据块自定义属性里以导出根开头的绝对路径改成 'umodel_.../x.psk' 相对写法；删掉 faceit_* 残留。"""
    root = os.path.normcase(os.path.abspath(export_root)) + os.sep
    changed = 0
    for coll in (bpy.data.objects, bpy.data.materials, bpy.data.meshes, bpy.data.armatures, bpy.data.scenes):
        for block in coll:
            for key in list(block.keys()):
                if key.startswith("faceit_"):
                    del block[key]
                    changed += 1
                    continue
                val = block.get(key)
                if not isinstance(val, str) or not val or not os.path.isabs(val):
                    continue
                if os.path.normcase(os.path.abspath(val)).startswith(root):
                    block[key] = os.path.relpath(os.path.abspath(val), export_root).replace("\\", "/")
                    changed += 1
    for ws in bpy.data.workspaces:
        if ws.name in WORKSPACE_NAMES and WORKSPACE_NAMES[ws.name] not in bpy.data.workspaces:
            ws.name = WORKSPACE_NAMES[ws.name]
            changed += 1
    return changed


def scrub_ui_paths():
    """界面里的文件浏览器默认目录（factory 启动也会填成本机 Documents）清掉，别把用户名带出去。"""
    cleared = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "FILE_BROWSER" and getattr(space, "params", None) is not None:
                    try:
                        space.params.directory = b""
                        cleared += 1
                    except (AttributeError, TypeError):
                        pass
    return cleared


def scrub_blend_bytes(path, needles):
    """未压缩 .blend 里定长 char 缓冲区残留的本机路径（文件浏览器目录等）就地填 NUL。

    只在 RNA 够不着的地方用（后台模式下 SpaceFileBrowser.params 是 None）；缓冲区是定长的，
    从命中处填到下一个 NUL 不改变任何结构长度。
    """
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    hits = 0
    for needle in needles:
        if not needle:
            continue
        start = 0
        while True:
            i = data.find(needle, start)
            if i < 0:
                break
            j = data.find(b"\x00", i)
            if j < 0:
                j = len(data)
            data[i:j] = b"\x00" * (j - i)
            hits += 1
            start = j
    if hits:
        with open(path, "wb") as fh:
            fh.write(data)
    return hits


def live_stats():
    """从打开的文件直接数：网格对象 / 顶点 / 骨骼 / 表情（Shape Keys 去掉 Basis）。"""
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    morphs = 0
    for o in meshes:
        if o.data.shape_keys:
            morphs = max(morphs, len(o.data.shape_keys.key_blocks) - 1)
    return {
        "meshes": len(meshes),
        "vertices": sum(len(o.data.vertices) for o in meshes),
        "bones": sum(len(a.bones) for a in bpy.data.armatures),
        "morphs": morphs,
        "objects": {o.type: sorted(x.name for x in bpy.data.objects if x.type == o.type) for o in bpy.data.objects},
    }


def read_report(validation_dir, label):
    path = os.path.join(validation_dir, label + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_readme(dest, package, name, kind, stats, textures, extras, blend_name, notes, version):
    head = stats.get("head_object") or "Eve_Head_Mesh_01"
    parts = stats.get("mesh_objects") or []
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
        "      Blender %s 保存；Blender 3.6 及更新版本都能打开（4.5 和 5.1 已实测）。" % version,
        "      Saved with Blender %s; opens in 3.6 and newer (tested in 4.5 and 5.1)." % version,
        "  textures\\           %d 张 PNG，材质节点里已经接好 / %d PNGs, already wired in the materials" % (len(textures), len(textures)),
    ]
    if extras:
        lines += [
            "  textures\\extra\\     %d 张服装自己的法线 / ORM / Mask / 换色贴图，没接节点，按需自己接" % len(extras),
            "                       %d extra maps (_N / _ORM / _Mask / recolour) from the outfit's own folder, not wired" % len(extras),
        ]
    lines += [
        "  preview.png          正面预览 / front preview",
        "  preview_face.png     头部特写（验证渲染，偏暗） / head close-up (validation render, dim lighting)",
        "  package.json         清单：贴图来源、网格统计 / manifest: texture sources, mesh stats",
        "",
        "模型 / Model",
        "  网格 / meshes   : %s" % stats.get("meshes", "?"),
        "  顶点 / vertices : %s" % stats.get("vertices", "?"),
        "  骨骼 / bones    : %s（单一骨架 Eve_Armature，可直接摆姿势 / one armature, pose-ready）" % stats.get("bones", "?"),
        "  表情 / morphs   : %s（头部物体 %s 的 Shape Keys / shape keys on the %s object）" % (stats.get("morphs", "?"), head, head),
        "  单位 / units    : 厘米，身高约 175；Blender 里显示成 175 m 是正常的",
        "                    centimetres (1 Blender unit = 1 cm, about 175 tall); Blender showing \"175 m\" is expected",
        "  物体 / objects  : " + (", ".join(parts) if parts else "服装身体 + 脸 + 发型 + 马尾（+ 短发束）"),
        "                    outfit body + head + hair + ponytail (+ short hair strands), plus Eve_Armature",
        "",
        "怎么用 / How to use",
        "  1. 打开 .blend，视口切到 Material Preview 就能看到贴图。",
        "     Open the .blend and switch the viewport to Material Preview to see the textures.",
        "  2. 选中 Eve_Armature 进 Pose Mode 摆姿势；表情在 %s 的 Object Data > Shape Keys。" % head,
        "     （如果服装带头套或头盔，表情会被挡住，先把身体物体隐藏（H）再看）",
        "     Select Eve_Armature > Pose Mode to pose; expressions are Shape Keys on %s." % head,
        "     (If the outfit has a mask or helmet, hide the body object (H) to see them.)",
        "  3. 要导去别的软件用 File > Export（FBX / glTF）。先选中 Eve_Armature 和几个网格物体再勾 Selected Objects，",
        "     场景里还有一个验证相机和三盏灯，不选就不会带出去。",
        "     Export to other tools with File > Export (FBX / glTF): select Eve_Armature and the mesh objects, then tick",
        "     Selected Objects so the validation camera and the three lights stay behind.",
        "",
        "材质说明 / Materials",
        "  皮肤、服装、眼睛、牙齿都是 Principled BSDF + 贴图：接了颜色（Base Color），脸 / 眼 / 牙还接了法线；",
        "  头发只接了透明度贴图（PonyTail_Alpha），颜色是固定的深色。金属度、粗糙度是预览用的近似值。",
        "  Skin, outfit, eyes and teeth are Principled BSDF + textures: Base Color wired, plus normal maps on face,",
        "  eyes and teeth; hair only has its alpha map wired with a fixed dark colour. Roughness/metallic are",
        "  preview approximations.",
    ]
    if extras:
        lines += [
            "  textures\\extra\\ 里是服装自己的 _N / _ORM / _Mask 贴图，要更细的效果自己再接。",
            "  The outfit's _N / _ORM / _Mask maps sit in textures\\extra\\ for you to wire if you want more detail.",
        ]
    if notes:
        lines += ["", "备注 / Notes"] + ["  - " + n for n in notes]
    lines += [
        "",
        "来源 / Source",
        "  Stellar Blade (c) SHIFT UP / Sony Interactive Entertainment。模型与贴图版权归原公司；本包是非官方的",
        "  个人提取，仅供个人学习研究，请勿再分发、出售或商用。",
        "  Stellar Blade (c) SHIFT UP / Sony Interactive Entertainment. Models and textures remain the property of",
        "  their owners. This is an unofficial fan extraction for personal study only; do not redistribute or sell.",
        "  制作方式 / made with: 用 UE Viewer (umodel) 和 FModel 从游戏文件导出，在 Blender 3.6 里组装。",
        "  Exported from the game files with UE Viewer (umodel) and FModel, assembled in Blender 3.6.",
        "",
    ]
    with open(os.path.join(dest, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write("\n".join(lines))


def write_json(path, data):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_zip(dest, label, out_root):
    """把 <out_root>\\<label>\\ 整个打成 <out_root>\\<label>.zip（zip 里带一层同名目录）。"""
    zpath = os.path.join(out_root, label + ".zip")
    tmp = zpath + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for root, _dirs, files in os.walk(dest):
            for f in sorted(files):
                full = os.path.join(root, f)
                zf.write(full, os.path.relpath(full, out_root))
    os.replace(tmp, zpath)
    return os.path.basename(zpath)


def package_complete(dest, info):
    """package.json 说的东西都还在才算已完成（重做中途被杀会留下旧 marker）。"""
    if not os.path.isfile(os.path.join(dest, info.get("blend", ""))):
        return False
    for t in info.get("textures", []) + info.get("extra_textures", []):
        if not os.path.isfile(os.path.join(dest, *t["file"].split("/"))):
            return False
    return True


def package_one(label, args, cm):
    src_blend = os.path.join(args.blend_dir, label + ".blend")
    dest = os.path.join(args.out_root, label)
    marker = os.path.join(dest, "package.json")
    export_root = os.path.dirname(args.blend_dir)
    if os.path.isfile(marker) and not args.force:
        with open(marker, encoding="utf-8") as fh:
            info = json.load(fh)
        if package_complete(dest, info):
            if args.zip and not os.path.isfile(os.path.join(args.out_root, label + ".zip")):
                info["zip"] = write_zip(dest, label, args.out_root)
                write_json(marker, info)
                print("[pkg] ZIP  %s (已有包，只补 zip)" % label, flush=True)
            else:
                print("[pkg] SKIP %s (已有 package.json)" % label, flush=True)
            return info
        print("[pkg] 上次没做完，重做 %s" % label, flush=True)
    package, name, group, kind = describe(label, cm)
    tex_dir = os.path.join(dest, "textures")
    os.makedirs(dest, exist_ok=True)
    if os.path.isfile(marker):
        os.remove(marker)                   # 做完才重新写，中途被杀不会留下假的“已完成”
    if os.path.isdir(tex_dir):
        shutil.rmtree(tex_dir)              # 重做时清掉旧贴图
    os.makedirs(tex_dir, exist_ok=True)
    for stale in os.listdir(dest):
        if stale.endswith((".blend1", ".blend@", ".part")):
            os.remove(os.path.join(dest, stale))

    bpy.ops.wm.open_mainfile(filepath=src_blend, load_ui=False)
    bpy.context.preferences.filepaths.save_version = 0

    problems = []
    images = []                             # (image, 来源绝对路径)
    for im in bpy.data.images:
        if im.type != "IMAGE":
            continue
        if im.source != "FILE":
            problems.append("image %s has source %s (not handled)" % (im.name, im.source))
            continue
        if im.packed_file is not None:
            problems.append("image %s is packed inside the blend (left as is)" % im.name)
        src = bpy.path.abspath(im.filepath)
        if not src or not os.path.isfile(src):
            problems.append("missing source texture: %s (%s)" % (im.name, im.filepath))
            continue
        images.append((im, os.path.abspath(src)))
    unique_sources = sorted({os.path.normcase(s): s for _im, s in images}.values(), key=os.path.normcase)
    names = assign_names(unique_sources)
    names = {os.path.normcase(k): v for k, v in names.items()}
    textures = []
    for src in unique_sources:
        dest_name = names[os.path.normcase(src)]
        shutil.copy2(src, os.path.join(tex_dir, dest_name))
        textures.append({
            "file": "textures/" + dest_name, "bytes": os.path.getsize(src),
            "source": os.path.relpath(src, export_root).replace("\\", "/"),
            "images": sorted(im.name for im, s in images if os.path.normcase(s) == os.path.normcase(src)),
        })
    for im, src in images:
        im.filepath = os.path.join(tex_dir, names[os.path.normcase(src)])   # 先绝对，保存后再统一转相对

    wired = set(names.keys())
    extras = [] if args.no_extra else copy_extra_maps(textures, wired, tex_dir, export_root)

    # validate_eve.py 留在材质上的预览贴图路径也改成包内相对路径
    for mat in bpy.data.materials:
        p = mat.get("stellarblade_preview_texture")
        if isinstance(p, str) and p and os.path.normcase(os.path.abspath(p)) in names:
            mat["stellarblade_preview_texture"] = "textures/" + names[os.path.normcase(os.path.abspath(p))]
    bpy.context.scene.render.filepath = "//render.png"
    relativize_custom_props(export_root)
    scrub_ui_paths()
    stats = live_stats()

    blend_name = label + ".blend"
    dest_blend = os.path.join(dest, blend_name)
    bpy.ops.wm.save_as_mainfile(filepath=dest_blend, relative_remap=True, compress=False, copy=False)
    bpy.ops.file.make_paths_relative()
    for im, _src in images:
        im.filepath = im.filepath.replace("\\", "/")        # //textures/x.png，跨平台都认
    bpy.ops.wm.save_mainfile(filepath=dest_blend, compress=False)
    for stale in os.listdir(dest):
        if stale.endswith(".blend1"):
            os.remove(os.path.join(dest, stale))
    # 界面数据里 RNA 够不着的本机路径（用户目录、导出根）按字节清掉
    home = os.path.expanduser("~")
    scrub_blend_bytes(dest_blend, [
        home.encode("utf-8"),
        os.path.splitdrive(home)[1].encode("utf-8"),      # 缓冲区里可能只剩 ':\Users\<name>\Documents'
        os.path.basename(home).encode("utf-8"),
        os.path.abspath(export_root).encode("utf-8"),
        os.path.basename(export_root).encode("utf-8"),
    ])

    # 重新打开校验：每张图片必须是 //textures/ 相对路径且文件在包内
    bpy.ops.wm.open_mainfile(filepath=dest_blend, load_ui=False)
    checked = 0
    tex_prefix = os.path.normcase(os.path.abspath(tex_dir)) + os.sep
    for im in bpy.data.images:
        if im.type != "IMAGE" or im.source != "FILE":
            continue
        ap = os.path.abspath(bpy.path.abspath(im.filepath))
        inside = os.path.normcase(ap).startswith(tex_prefix)
        # 文件里存的是 //textures/x.png，Blender 读回来会换成本机分隔符，比较前统一成 /
        if not im.filepath.replace("\\", "/").startswith("//textures/") or not inside or not os.path.isfile(ap):
            problems.append("bad path after save: %s -> %s" % (im.name, im.filepath))
        checked += 1
    for lib in bpy.data.libraries:
        problems.append("linked library: %s" % lib.filepath)
    for txt in bpy.data.texts:
        if txt.filepath and not txt.is_in_memory:
            problems.append("external text: %s" % txt.filepath)

    # 预览与报告
    report = read_report(args.validation_dir, label)
    if not report:
        problems.append("no validation report")
    totals = report.get("totals") or {}
    for key in ("meshes", "vertices", "bones"):
        if totals.get(key) and totals[key] != stats[key]:
            problems.append("validation %s=%s but blend has %s" % (key, totals[key], stats[key]))
    mesh_objects = stats["objects"].get("MESH", [])
    stats["mesh_objects"] = mesh_objects
    stats["head_object"] = next((o for o in mesh_objects if "head" in o.lower()), mesh_objects[0] if mesh_objects else "")
    gallery_png = os.path.join(args.blend_dir, label + "_gallery.png")
    val_png = os.path.join(args.validation_dir, label + ".png")
    face_png = os.path.join(args.validation_dir, label + "_face.png")
    if os.path.isfile(gallery_png):
        shutil.copy2(gallery_png, os.path.join(dest, "preview.png"))
    elif os.path.isfile(val_png):
        shutil.copy2(val_png, os.path.join(dest, "preview.png"))
    else:
        problems.append("no preview image")
    if os.path.isfile(face_png):
        shutil.copy2(face_png, os.path.join(dest, "preview_face.png"))
    notes = []
    if label == "Eve_CH_P_EVE_11_1":
        notes.append("这个包自带 Raven 发型，打包时又加了 Eve 默认发型，头上有两套头发，按需删一套。"
                     " / This package has its own (Raven) hair and Eve's default hair was added as well; delete the one you do not want.")
    if kind == "nude":
        notes.append("来自 EveOriginalProportions mod，不是游戏原版资源。 / From the EveOriginalProportions mod, not a stock asset.")
    if kind == "dlc":
        notes.append("联动 DLC 服装。 / Collaboration DLC outfit.")
    write_readme(dest, package, name, kind, stats, textures, extras, blend_name, notes, bpy.app.version_string)

    info = {
        "label": label, "package": package, "name": name, "group": group, "kind": kind,
        "blend": blend_name, "blender_version": bpy.app.version_string,
        "blend_bytes": os.path.getsize(dest_blend),
        "textures": textures, "texture_bytes": sum(t["bytes"] for t in textures),
        "extra_textures": extras, "extra_bytes": sum(t["bytes"] for t in extras),
        "images_checked": checked,
        "meshes": stats["meshes"], "vertices": stats["vertices"], "bones": stats["bones"], "morphs": stats["morphs"],
        "objects": stats["objects"], "head_object": stats["head_object"],
        "problems": problems,
    }
    write_json(marker, info)
    if args.zip:
        info["zip"] = write_zip(dest, label, args.out_root)
        write_json(marker, info)
    total_mb = (info["blend_bytes"] + info["texture_bytes"] + info["extra_bytes"]) / 1e6
    print("[pkg] %s %s -> %s | %d tex + %d extra, %.0f MB%s" % (
        "WARN" if problems else "OK", label, name, len(textures), len(extras), total_mb,
        (" | " + "; ".join(problems)) if problems else ""), flush=True)
    return info


def human(n):
    return "%.1f GB" % (n / 1024 ** 3) if n >= 1024 ** 3 else "%.0f MB" % (n / 1024 ** 2)


def write_index(out_root):
    rows = []
    for d in sorted(os.listdir(out_root)):
        marker = os.path.join(out_root, d, "package.json")
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as fh:
                rows.append(json.load(fh))
    kinds = {"official": "本体服装", "dlc": "联动 DLC", "nude": "裸模 mod", "other": "其它"}
    lines = [
        "# Stellar Blade · Eve 模型包（每个文件夹可单独拷走）",
        "",
        "每个子目录都是一个完整、自足的模型：`.blend` + `textures\\`（已接的贴图）+ `textures\\extra\\`",
        "（服装自己的法线 / ORM / Mask 图，没接节点）+ 预览 + `README.txt` + `package.json`。",
        "贴图全部是 `//textures/` 相对路径，整个子目录拷到别的电脑直接打开即可（Blender 3.6 及以上）。",
        "每个文件夹里的 `README.txt` 有中英文使用说明。",
        "",
        "| 文件夹 | 服装 | 类型 | 网格 | 顶点 | 骨骼 | 表情 | 贴图（已接 + 附带） | 大小 (MiB) | 问题 |",
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
    write_json(os.path.join(out_root, "packages_index.json"), rows)
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
        raise SystemExit("打包要在 Blender 里跑：blender --background --factory-startup --python package_outfits.py -- ...")
    cm = load_outfit_names()
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
    results = [package_one(l, args, cm) for l in labels]
    bad = [r["label"] for r in results if r["problems"]]
    print("PACKAGE_DONE lane=%d ok=%d problems=%d%s" % (
        args.lane, len(results) - len(bad), len(bad), (" " + ",".join(bad)) if bad else ""), flush=True)


if __name__ == "__main__":
    main()
