# DOA5LR 组装（Blender 3.6 无头）：导入 Noesis 出的 FBX，整理材质、打包贴图、
# 存 .blend、渲预览。
#
# 与 DOA6 不同，DOA5LR 的 FBX **自带**材质→贴图连接（Noesis 的 doa5pc 插件按 TMC
# 材质写入 Diffuse/Normal/Specular），所以不需要 matmap 解析：本脚本只读取 FBX
# 已有的图像分配，再用统一的 Principled 接法重建（法线转 Non-Color + Normal Map
# 节点、Alpha 走 HASHED，头发/睫毛才不会是黑片）。
#
# 用法：
#   blender --background --factory-startup --python build_blend.py -- \
#       <out.blend> <preview.png|-> <部件目录1> [部件目录2 ...]
#
# 每个部件目录里应有 <名字>.fbx 与同目录的 Tex_NN(L_N).dds；若旁边存在同名 .png
# （PS1 包装脚本会预先转好），优先用 PNG——Blender 读不了部分 BC 压缩格式。
# 多目录用于拼完整角色：DOA5LR 的头发是独立 TMC（<角色>_HAIR_00N），
# 服装 TMC 只带光头。各部件贴图同名（Tex_00…），所以必须留在各自目录里导入。

import bpy
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
out_blend, preview_png = argv[0], argv[1]
part_dirs = argv[2:]

bpy.ops.wm.read_factory_settings(use_empty=True)

imported = 0
part_objects = []  # [(part_dir, [objects])]，按导入顺序，第一个是身体/服装
for part_dir in part_dirs:
    fbxs = [f for f in os.listdir(part_dir) if f.lower().endswith(".fbx")]
    if not fbxs:
        print("WARN: 目录里没有 FBX，跳过: %s" % part_dir)
        continue
    before = set(bpy.data.objects)
    for fbx in fbxs:
        bpy.ops.import_scene.fbx(filepath=os.path.join(part_dir, fbx))
        imported += 1
    part_objects.append((part_dir, [o for o in bpy.data.objects if o not in before]))
if imported == 0:
    raise SystemExit("没有导入任何 FBX")
print("FBX_IMPORTED=%d" % imported)


def bbox_of(objs, name_filter=None):
    """objs 中（可选按名字子串过滤）网格的世界空间包围盒 (min_v, max_v)。"""
    from mathutils import Vector
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        if name_filter and name_filter not in o.name.lower():
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return None
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


# 部件对齐。实测结论（务必先读，别再"好心"去对齐）：
#   **绝大多数角色的脸/头发 TMC 本来就和服装同处一个坐标系**，直接叠加即正确。
#   早期版本无条件按包围盒对齐，反而把对的挪歪了——马尾的包围盒顶端是发梢不是
#   头顶、包围盒中心也不在头中心，于是头发被压到脸前面（红叶/穗香）。
# 所以默认**不动**，只在部件确实不在身体坐标系时才搬：
#   - 判定用部件**顶端**是否够到身体顶端（马尾底端会垂到腰，用底端会误判）。
#   - 少数角色（霞，来自 chara_initial）的脸有 X 存储偏置、头发用自己的局部原点，
#     这类才需要居中/搬运。
# 搬运时的头部锚点优先级：服装自带的 head 网格 > 已就位的脸 > 身体包围盒顶部，
# 因此部件顺序必须是 服装 → 脸 → 头发（export_full.ps1 已保证）。
if len(part_objects) > 1:
    body_objs = part_objects[0][1]
    body_bb = bbox_of(body_objs)
    anchor_bb = bbox_of(body_objs, "head")  # 服装自带头部时直接用它
    if body_bb:
        b_mn, b_mx = body_bb
        b_ctr = (b_mn + b_mx) / 2
        body_h = max(b_mx.z - b_mn.z, 1e-9)
        for pdir, objs in part_objects[1:]:
            bb = bbox_of(objs)
            if not bb:
                continue
            p_mn, p_mx = bb
            p_ctr = (p_mn + p_mx) / 2
            width_x = max(p_mx.x - p_mn.x, 1e-9)
            # 是否已处在身体坐标系：看部件**顶端**是否够到身体顶端。
            # 用顶端而不是底端——马尾/长发的底端会垂到腰部，用底端会误判；
            # 余量取身体高度 5%，且不能被翅膀等附件撑大的包围盒带偏（女天狗踩过这个坑）。
            in_place = p_mx.z >= b_mx.z - body_h * 0.05
            if in_place:
                # 已就位：Z/Y 一律不动。只有明显存在“存储偏置”时才把 X 拉回中线
                # （霞的脸就整体偏在 X+ 一侧；多数角色本就对称，此处为 0）。
                dy = dz = 0.0
                dx = -p_ctr.x if abs(p_ctr.x) > width_x * 0.25 else 0.0
            else:
                dx = b_ctr.x - p_ctr.x
                ref_mn, ref_mx = anchor_bb if anchor_bb else (b_mn, b_mx)
                dy = ((ref_mn + ref_mx) / 2).y - p_ctr.y
                dz = ref_mx.z - p_mx.z
            for o in objs:
                if o.parent is None:
                    o.location = (o.location[0] + dx, o.location[1] + dy, o.location[2] + dz)
            bpy.context.view_layer.update()
            if in_place:
                anchor_bb = bbox_of(objs)  # 就位的脸成为后续头发的锚点
            print("PART_ALIGNED=%s dx=%.5g dy=%.5g dz=%.5g%s"
                  % (os.path.basename(pdir), dx, dy, dz, " (in-place)" if in_place else ""))


def world_bounds():
    from mathutils import Vector
    xs, ys, zs = [], [], []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return xs, ys, zs


# Noesis 的 DOA5 FBX 以 scale 0.01 导出，角色只有 ~1.6cm 高：既落在相机默认近裁剪
# 面内（渲染全空），在视口里也难操作。归一到约 1.7 单位（≈ 人高米数）。
_xs, _ys, _zs = world_bounds()
if _xs:
    _h = max(max(_xs) - min(_xs), max(_ys) - min(_ys), max(_zs) - min(_zs))
    if 0 < _h < 0.5 or _h > 50:
        _f = 1.7 / _h
        for o in bpy.data.objects:
            if o.parent is None:
                o.scale = tuple(s * _f for s in o.scale)
                o.location = tuple(l * _f for l in o.location)
        bpy.context.view_layer.update()
        print("SCALE_NORMALIZED=%.4g (height %.4g -> 1.7)" % (_f, _h))

def prefer_png(img):
    """DDS 读不出像素时换同名 PNG。"""
    fp = bpy.path.abspath(img.filepath) if img.filepath else ""
    if not fp:
        return
    png = os.path.splitext(fp)[0] + ".png"
    if os.path.exists(png) and (not img.has_data or fp.lower().endswith(".dds")):
        img.filepath = png
        try:
            img.reload()
        except RuntimeError:
            pass

for img in bpy.data.images:
    prefer_png(img)

_alpha_cache = {}


def has_real_transparency(img):
    """判断 diffuse 的 alpha 是不是真的透明度遮罩。

    DOA5LR 的部分贴图把高光/遮罩塞在 alpha 里，会被误当成透明度，结果皮肤/衣服
    变成半透明抖动噪点。两条判据同时满足才认定是真透明遮罩：

      ① 有足够的**全透明**像素（>2%）——排除霞 Tex_27 那种 0.00~0.91 连续、
         既无全透明也无全不透明像素的高光遮罩；
      ② 有足够的**全不透明**像素（>4%）——镂空遮罩必然是"该实的地方全实、该空的
         地方全空"。这条排除两类冒充者：穗香 Tex_01（62% 全透明但最大只有 0.34）
         和穗香脸部那张（3% 全透明、max 0.99，但均值仅 0.12 → 几乎没有实心区域，
         当成透明度会让整张脸和皮肤透光起噪点）。

    实测参考（通过）：头发卡片 全不透明 6~54% / 全透明 30~40%；服装镂空 16%/17%。
    （不通过）：身体贴图 alpha 恒为 1（全透明 0%）；各类遮罩通道见上。
    """
    key = img.name_full
    if key in _alpha_cache:
        return _alpha_cache[key]
    result = False
    try:
        import numpy as np
        n = len(img.pixels)
        if n and img.size[0]:
            buf = np.empty(n, dtype=np.float32)
            img.pixels.foreach_get(buf)
            a = buf[3::4]
            result = bool((a < 0.01).mean() > 0.02 and (a > 0.99).mean() > 0.04)
    except Exception as e:
        print("WARN alpha 检测失败 %s: %s" % (img.name, e))
    _alpha_cache[key] = result
    return result


def classify(node_name):
    n = node_name.lower()
    if n.startswith("normal"):
        return "normal"
    if n.startswith("specular"):
        return "specular"
    if n.startswith("diffuse"):
        return "diffuse"
    return None

rebuilt = 0
alpha_mats = 0
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    # 收集 FBX 导入时建立的图像分配
    # 语义在图像数据块名上（Noesis 写的 "Diffuse/Normal/Specular Texture[.NNN]"），
    # 不是节点名——节点名是 Blender 导入时统一生成的。
    found = {}
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            kind = classify(node.image.name)
            if kind and kind not in found:
                found[kind] = node.image
    if not found:
        continue

    # 用干净的 Principled 重建
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.55

    use_alpha = False
    if "diffuse" in found:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = found["diffuse"]
        tex.location = (-400, 250)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        # 只有真的是透明度遮罩才接 Alpha，否则皮肤会变半透明噪点（见 has_real_transparency）
        if has_real_transparency(found["diffuse"]):
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            use_alpha = True
    if "normal" in found:
        img = found["normal"]
        img.colorspace_settings.name = "Non-Color"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-500, -80)
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-180, -80)
        nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if "specular" in found:
        img = found["specular"]
        img.colorspace_settings.name = "Non-Color"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-500, -400)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Specular"])

    mat.blend_method = "HASHED" if use_alpha else "OPAQUE"
    mat.shadow_method = "HASHED" if use_alpha else "OPAQUE"
    rebuilt += 1
    if use_alpha:
        alpha_mats += 1

print("MATERIALS_REBUILT=%d ALPHA_MATERIALS=%d" % (rebuilt, alpha_mats))

# 打包贴图（逐个：失效引用直接删，pack_all 会因它们报错）
packed = 0
for img in list(bpy.data.images):
    if img.packed_file:
        continue
    fp = bpy.path.abspath(img.filepath) if img.filepath else ""
    if fp and os.path.exists(fp):
        img.pack()
        packed += 1
    else:
        bpy.data.images.remove(img)
print("IMAGES_PACKED=%d" % packed)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("SAVED_BLEND=" + out_blend)

if preview_png != "-":
    from mathutils import Vector

    xs, ys, zs = world_bounds()
    if not xs:
        raise SystemExit("场景里没有网格，无法取景")
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    h = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    cam_data = bpy.data.cameras.new("cam")
    # 按模型尺度设裁剪面，否则小模型整个落在默认 0.1 近裁剪面内 → 渲染全空
    cam_data.clip_start = max(h / 1000.0, 1e-4)
    cam_data.clip_end = max(h * 100.0, 100.0)
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    dist = h * 1.6
    cam.location = (cx + dist * 0.35, cy - dist, cz + h * 0.08)
    cam.rotation_euler = (Vector((cx, cy, cz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.2
    bpy.context.scene.world = world
    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(30))
    bpy.context.collection.objects.link(sun)

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 900
    sc.render.resolution_y = 1400
    sc.render.filepath = preview_png
    bpy.ops.render.render(write_still=True)
    print("SAVED_PREVIEW=" + preview_png)

print("BUILD_BLEND=PASS")
