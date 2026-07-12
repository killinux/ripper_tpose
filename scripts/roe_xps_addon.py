"""ROE XPS Tools —— Rise of Eros 角色一步步转 XPS 的 Blender 插件。

N 面板(侧边栏) > ROE 页签，三步：
  1. 导入 FBX（extract_character.ps1 的导出物，自动处理缩放）
  2. 挂材质（含眼球/睫毛/眉毛修复，同 blender_face_materials.py，原理见
     docs/face-eye-materials.md）
  3. 导出 XPS .mesh（烘焙眼球贴图 → head 按材质拆分 → 设 render group →
     调 XNALaraMesh 导出，场景本身不受影响）

安装: Edit > Preferences > Add-ons > Install... 选本文件，勾选启用。
依赖: 第 3 步需要 XNALaraMesh 插件已启用。
"""
import os

import bpy
from bpy.props import StringProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

bl_info = {
    "name": "ROE XPS Tools",
    "author": "ripper_tpose",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar > ROE",
    "description": "Rise of Eros 角色: 导入 FBX / 修脸材质 / 导出 XPS",
    "category": "Import-Export",
}

# 默认参数（与 docs/face-eye-materials.md 一致）
SKIN_DESAT = 0.85
IRIS_CENTER = (0.5, 0.49)
IRIS_R_IN = 0.235
IRIS_R_OUT = 0.285
SCLERA = (0.90, 0.88, 0.87, 1.0)
LASH_ALPHA_GAIN = 1.5
LASH_DARKEN = 0.55


# ---------------------------------------------------------------- utils

def find_tex(tex_dir, pattern):
    import glob
    hits = sorted(glob.glob(os.path.join(tex_dir, pattern)))
    return hits[0] if hits else None


def find_head(objects):
    return next((o for o in objects if o.type == 'MESH'
                 and any('Eyeball' in g.name for g in o.vertex_groups)), None)


def scene_meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH']


# ------------------------------------------------------- material builders

def _new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (600, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (250, 0)
    b.inputs['Metallic'].default_value = 0
    b.inputs['Roughness'].default_value = 0.4
    nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])
    return m, nt, b


def _tex_node(nt, path, loc=(-500, 200)):
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = bpy.data.images.load(path, check_existing=True)
    t.location = loc
    return t


def albedo_mat(name, tex_path, desat=False, hashed=False):
    m, nt, b = _new_mat(name)
    if not tex_path:
        return m
    t = _tex_node(nt, tex_path)
    if desat:
        h = nt.nodes.new('ShaderNodeHueSaturation'); h.location = (-150, 200)
        h.inputs['Saturation'].default_value = SKIN_DESAT
        nt.links.new(t.outputs['Color'], h.inputs['Color'])
        nt.links.new(h.outputs['Color'], b.inputs['Base Color'])
    else:
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    # 丝袜等半透明衣物 CLIP 会被裁没，body 用 HASHED
    m.blend_method = 'HASHED' if hashed else 'CLIP'
    m.shadow_method = 'CLIP'
    return m


def eye_mat(name, iris_path):
    """程序化眼白 + 中心圆盘虹膜（虹膜贴图外圈是棕色，整张贴会没有眼白）。"""
    m, nt, b = _new_mat(name)
    b.inputs['Roughness'].default_value = 0.15
    t = _tex_node(nt, iris_path)
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.location = (-900, 0)
    uv.uv_map = 'UV0'
    dist = nt.nodes.new('ShaderNodeVectorMath'); dist.location = (-700, 0)
    dist.operation = 'DISTANCE'
    dist.inputs[1].default_value = (IRIS_CENTER[0], IRIS_CENTER[1], 0.0)
    nt.links.new(uv.outputs['UV'], dist.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (-500, 0)
    mr.interpolation_type = 'SMOOTHSTEP'
    mr.inputs['From Min'].default_value = IRIS_R_IN
    mr.inputs['From Max'].default_value = IRIS_R_OUT
    mr.inputs['To Min'].default_value = 1.0
    mr.inputs['To Max'].default_value = 0.0
    nt.links.new(dist.outputs['Value'], mr.inputs['Value'])
    mix = nt.nodes.new('ShaderNodeMixRGB'); mix.location = (-100, 150)
    mix.inputs['Color1'].default_value = SCLERA
    nt.links.new(t.outputs['Color'], mix.inputs['Color2'])
    nt.links.new(mr.outputs['Result'], mix.inputs['Fac'])
    nt.links.new(mix.outputs['Color'], b.inputs['Base Color'])
    m.blend_method = 'OPAQUE'
    return m


def stroke_mat(name, tex_path, alpha_gain=1.0, darken=1.0):
    """眉毛/睫毛：RGB 是填充色层，真正的毛发笔触在 alpha 通道。"""
    m, nt, b = _new_mat(name)
    b.inputs['Roughness'].default_value = 0.6
    b.inputs['Specular'].default_value = 0.1
    t = _tex_node(nt, tex_path)
    if darken != 1.0:
        h = nt.nodes.new('ShaderNodeHueSaturation'); h.location = (-150, 200)
        h.inputs['Value'].default_value = darken
        nt.links.new(t.outputs['Color'], h.inputs['Color'])
        nt.links.new(h.outputs['Color'], b.inputs['Base Color'])
    else:
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    if alpha_gain != 1.0:
        mul = nt.nodes.new('ShaderNodeMath'); mul.location = (-150, -100)
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = alpha_gain
        mul.use_clamp = True
        nt.links.new(t.outputs['Alpha'], mul.inputs[0])
        nt.links.new(mul.outputs['Value'], b.inputs['Alpha'])
    else:
        nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    m.blend_method = 'BLEND'
    m.shadow_method = 'NONE'
    m.show_transparent_back = False
    return m


def transparent_mat(name):
    """罩层：必须用 Transparent BSDF（Principled alpha=0 残留镜面高光）。"""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (300, 0)
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    nt.links.new(tr.outputs['BSDF'], out.inputs['Surface'])
    m.blend_method = 'BLEND'
    m.shadow_method = 'NONE'
    return m


# ------------------------------------------------- head submesh classification

def classify_head(o):
    """连通块 + 骨骼权重分类。返回 {poly_index: slot}，
    slot: 0脸 1眼球 2睫毛 3眉毛 4罩层。原理见 docs/face-eye-materials.md。"""
    me = o.data
    parent = list(range(len(me.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in me.edges:
        a, b = e.vertices
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    gi = {g.index: g.name for g in o.vertex_groups}

    def gclass(name):
        if 'Eyeball' in name: return 'eyeball'
        if 'Eyebrow' in name: return 'brow'
        if 'Eyelid' in name or 'eyelid' in name: return 'lid'
        return 'other'

    vclass = {}
    for v in me.vertices:
        d = {}
        for g in v.groups:
            c = gclass(gi[g.group])
            d[c] = d.get(c, 0) + g.weight
        vclass[v.index] = d

    uvd = me.uv_layers.active.data
    comps = {}
    for p in me.polygons:
        r = find(p.vertices[0])
        c = comps.setdefault(r, {'polys': 0, 'w': {'eyeball': 0, 'brow': 0, 'lid': 0, 'other': 0},
                                 'umin': 9.0, 'umax': -9.0})
        c['polys'] += 1
        for vi in p.vertices:
            for k, val in vclass[vi].items():
                c['w'][k] += val
        for li in p.loop_indices:
            u = uvd[li].uv[0]
            if u < c['umin']: c['umin'] = u
            if u > c['umax']: c['umax'] = u

    cls = {}
    for r, c in comps.items():
        w = c['w']
        tot = sum(w.values()) + 1e-6
        if w['eyeball'] > 0.9 * tot:
            cls[r] = 1
        elif c['umax'] <= 1.01 and c['polys'] < 400 and w['brow'] > w['other'] and w['brow'] > w['lid']:
            cls[r] = 3
        elif c['umax'] <= 1.01 and c['polys'] < 400 and w['lid'] > w['other']:
            cls[r] = 2
        elif c['umax'] > 1.01 and (c['umax'] - c['umin']) < 0.15 and c['polys'] > 100 and w['lid'] > 0.3 * tot:
            cls[r] = 4
    return {p.index: cls.get(find(p.vertices[0]), 0) for p in me.polygons}


# ------------------------------------------------------------ eye texture bake

def bake_eye_texture(head, iris_path, out_path):
    """把"程序化眼白+虹膜圆盘"烘成一张 PNG（XPS 不支持节点，必须烘焙）。
    参数优先从 head 槽 1 的眼球材质节点里读（保持和视口一致）。"""
    import numpy as np

    center, r_in, r_out, sclera = IRIS_CENTER, IRIS_R_IN, IRIS_R_OUT, SCLERA
    if len(head.material_slots) > 1 and head.material_slots[1].material:
        nt = head.material_slots[1].material.node_tree
        if nt:
            for n in nt.nodes:
                if n.type == 'MAP_RANGE':
                    r_in = n.inputs['From Min'].default_value
                    r_out = n.inputs['From Max'].default_value
                elif n.type == 'VECT_MATH' and n.operation == 'DISTANCE':
                    v = n.inputs[1].default_value
                    center = (v[0], v[1])
                elif n.type == 'MIX_RGB':
                    sclera = tuple(n.inputs['Color1'].default_value)
                elif n.type == 'TEX_IMAGE' and n.image:
                    iris_path = bpy.path.abspath(n.image.filepath)

    img = bpy.data.images.load(iris_path, check_existing=True)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    ys, xs = np.mgrid[0:h, 0:w]
    u = (xs + 0.5) / w
    v = (ys + 0.5) / h        # image.pixels 第一行是底部，与 UV v 方向一致
    d = np.sqrt((u - center[0]) ** 2 + (v - center[1]) ** 2)
    t = np.clip((r_out - d) / max(r_out - r_in, 1e-6), 0.0, 1.0)
    mask = (t * t * (3 - 2 * t))[..., None]     # smoothstep
    sc = np.array(sclera, dtype=np.float32)
    out = sc[None, None, :] * (1 - mask) + px * mask
    out[..., 3] = 1.0

    name = os.path.basename(out_path)
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    baked = bpy.data.images.new(name, w, h)
    baked.pixels = out.ravel().tolist()
    baked.filepath_raw = out_path
    baked.file_format = 'PNG'
    baked.save()
    return baked


# ------------------------------------------------------------------ properties

class ROE_Props(PropertyGroup):
    fbx_path: StringProperty(name="FBX", subtype='FILE_PATH',
                             description="extract_character.ps1 导出的角色 FBX")
    tex_dir: StringProperty(name="贴图目录", subtype='DIR_PATH',
                            description="含 *_Albedo.png 的目录(如 D:/roe_exports/g11/xps)")
    xps_out: StringProperty(name="XPS 输出", subtype='FILE_PATH',
                            description="输出 .mesh 路径；留空则自动放到贴图目录")


# ------------------------------------------------------------------- operators

class ROE_OT_import_fbx(Operator):
    bl_idname = "roe.import_fbx"
    bl_label = "1. 导入 FBX"
    bl_description = "导入角色 FBX（自动骨骼朝向；模型过小时自动 x100）"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.roe
        fbx = bpy.path.abspath(p.fbx_path)
        if not os.path.isfile(fbx):
            self.report({'ERROR'}, "FBX 路径无效: %s" % fbx)
            return {'CANCELLED'}
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.fbx(filepath=fbx, automatic_bone_orientation=True,
                                 use_image_search=False)
        new = [o for o in bpy.context.scene.objects if o not in before]
        meshes = [o for o in new if o.type == 'MESH']
        # 旧版导出(scale-factor 1)是厘米级，自动放大
        if meshes:
            size = max(max(o.dimensions) for o in meshes)
            if size < 0.5:
                for o in new:
                    if o.parent is None:
                        o.scale = (o.scale[0] * 100, o.scale[1] * 100, o.scale[2] * 100)
                bpy.ops.object.select_all(action='DESELECT')
                for o in new:
                    o.select_set(True)
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                self.report({'INFO'}, "导入完成(已自动 x100): %d 个物体" % len(new))
                return {'FINISHED'}
        for area in (context.screen.areas if context.screen else []):
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
        self.report({'INFO'}, "导入完成: %d 个物体" % len(new))
        return {'FINISHED'}


class ROE_OT_apply_materials(Operator):
    bl_idname = "roe.apply_materials"
    bl_label = "2. 挂材质(修眼睛)"
    bl_description = "body/hair 挂 Albedo；head 按连通块分 5 槽(脸/眼球/睫毛/眉毛/罩层)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.roe
        tex_dir = bpy.path.abspath(p.tex_dir)
        if not os.path.isdir(tex_dir):
            self.report({'ERROR'}, "贴图目录无效: %s" % tex_dir)
            return {'CANCELLED'}

        face_tex = find_tex(tex_dir, '*face*Albedo*.png')
        iris_tex = find_tex(tex_dir, '*eye_iris*Albedo*.png')
        brow_tex = find_tex(tex_dir, '*eyebrow*Albedo*.png')
        hair_tex = find_tex(tex_dir, '*hair*Albedo*.png')

        meshes = scene_meshes()
        head = find_head(meshes)

        for o in meshes:
            if o is head:
                continue
            me = o.data
            if 'hair' in o.name.lower():
                m = albedo_mat(o.name + '_mat', hair_tex)
            else:
                tex = find_tex(tex_dir, o.name.split('.')[0] + '*Albedo*.png')
                m = albedo_mat(o.name + '_mat', tex, desat=('body1' in o.name), hashed=True)
            me.materials.clear()
            me.materials.append(m)
            while len(me.materials) < max((q.material_index for q in me.polygons), default=0) + 1:
                me.materials.append(m)

        if head is None:
            self.report({'WARNING'}, "没找到 head 网格(无 Eyeball 顶点组)，只处理了 body/hair")
            return {'FINISHED'}
        if not (face_tex and iris_tex and brow_tex):
            self.report({'ERROR'}, "缺少 face/eye_iris/eyebrow 贴图，检查贴图目录")
            return {'CANCELLED'}

        me = head.data
        me.materials.clear()
        me.materials.append(albedo_mat('face', face_tex, desat=True))
        me.materials.append(eye_mat('eye', iris_tex))
        me.materials.append(stroke_mat('lash', brow_tex, LASH_ALPHA_GAIN, LASH_DARKEN))
        me.materials.append(stroke_mat('brow', brow_tex))
        me.materials.append(transparent_mat('eye_overlay'))
        cls = classify_head(head)
        for q in me.polygons:
            q.material_index = cls[q.index]
        me.update()
        self.report({'INFO'}, "材质完成(head 已分 5 槽)。EEVEE 编译 shader 需几秒")
        return {'FINISHED'}


class ROE_OT_export_xps(Operator):
    bl_idname = "roe.export_xps"
    bl_label = "3. 导出 XPS(.mesh)"
    bl_description = "烘焙眼球贴图 -> head 按材质拆分 -> 设 render group -> XNALaraMesh 导出"
    bl_options = {'REGISTER', 'UNDO'}

    # head 槽 -> (XPS 名, render group)。RG5=仅diffuse无alpha RG7=仅diffuse带alpha；罩层不导出
    HEAD_SLOTS = {0: ('face', '5'), 1: ('eye', '5'), 2: ('lash', '7'), 3: ('brow', '7')}

    def execute(self, context):
        if not hasattr(bpy.ops, 'xps_tools') or not hasattr(bpy.ops.xps_tools, 'export_model'):
            self.report({'ERROR'}, "需要先启用 XNALaraMesh 插件")
            return {'CANCELLED'}
        p = context.scene.roe
        tex_dir = bpy.path.abspath(p.tex_dir)
        meshes = scene_meshes()
        head = find_head(meshes)
        if not meshes:
            self.report({'ERROR'}, "场景里没有网格")
            return {'CANCELLED'}
        if not os.path.isdir(tex_dir):
            tex_dir = os.path.dirname(bpy.path.abspath(p.fbx_path))
        base = (head.name.split('.')[0] if head else meshes[0].name.split('.')[0])
        if base.endswith('_head'):
            base = base[:-5]
        out_path = bpy.path.abspath(p.xps_out) if p.xps_out else \
            os.path.join(tex_dir, base + '_fixed.mesh')

        fallback_group = []  # 兜底自建的组，导出后删除（防止污染后续 XPS 导入）

        def get_xps_group():
            """XNALaraMesh 导出器只认 'XPS Shader' 节点组（按输入插槽名找贴图）。
            优先用 XNALaraMesh 自己的 xps_shader_group() 创建，保证与其导入器兼容——
            残缺的同名组会让 XPS 导入报 KeyError: 'Alpha'。"""
            gt = bpy.data.node_groups.get('XPS Shader')
            if gt is not None and 'Alpha' not in gt.inputs:
                gt.name = 'XPS Shader.broken'   # 旧版插件建的残缺组：改名让位
                gt = None
            if gt:
                return gt
            import importlib
            for modname in ('XNALaraMesh-master', 'XNALaraMesh'):
                try:
                    mc = importlib.import_module(modname + '.material_creator')
                    return mc.xps_shader_group()
                except Exception:
                    continue
            # 兜底：自建最小组（含 Alpha），仅本次导出用，结束即删
            gt = bpy.data.node_groups.new('XPS Shader', 'ShaderNodeTree')
            for s in ('Diffuse', 'Lightmap', 'Specular', 'Emission', 'Bump Map',
                      'Bump Mask', 'MicroBump 1', 'MicroBump 2', 'Environment'):
                gt.inputs.new('NodeSocketColor', s)
            a = gt.inputs.new('NodeSocketFloatFactor', 'Alpha')
            a.default_value = 1.0
            gt.outputs.new('NodeSocketShader', 'Shader')
            gi = gt.nodes.new('NodeGroupInput'); gi.location = (-300, 0)
            go = gt.nodes.new('NodeGroupOutput'); go.location = (300, 0)
            em = gt.nodes.new('ShaderNodeEmission')
            gt.links.new(gi.outputs['Diffuse'], em.inputs['Color'])
            gt.links.new(em.outputs['Emission'], go.inputs['Shader'])
            fallback_group.append(gt)
            return gt

        used_images = []

        def simple_export_mat(name, image):
            m = bpy.data.materials.new('xps_' + name)
            m.use_nodes = True
            nt = m.node_tree
            nt.nodes.clear()
            out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
            grp = nt.nodes.new('ShaderNodeGroup'); grp.location = (100, 0)
            grp.node_tree = get_xps_group()
            t = nt.nodes.new('ShaderNodeTexImage'); t.location = (-300, 100)
            t.image = image
            used_images.append(image)
            nt.links.new(t.outputs['Color'], grp.inputs['Diffuse'])
            nt.links.new(grp.outputs[0], out.inputs['Surface'])
            return m

        def first_image(mat):
            if mat and mat.node_tree:
                for n in mat.node_tree.nodes:
                    if n.type == 'TEX_IMAGE' and n.image:
                        return n.image
            return None

        temps, temp_mats, hidden = [], [], []
        try:
            # 眼球贴图烘焙
            baked = None
            if head:
                iris = find_tex(tex_dir, '*eye_iris*Albedo*.png')
                if iris or (len(head.material_slots) > 1):
                    baked = bake_eye_texture(head, iris,
                                             os.path.join(tex_dir, 'roe_eye_baked.png'))

            # 复制 body/hair
            for o in meshes:
                if o is head:
                    continue
                dup = o.copy(); dup.data = o.data.copy()
                context.collection.objects.link(dup)
                img = first_image(o.material_slots[0].material if o.material_slots else None)
                m = simple_export_mat(o.name, img) if img else None
                dup.data.materials.clear()
                if m:
                    dup.data.materials.append(m)
                    temp_mats.append(m)
                # XPS 网格名用 _ 作分隔符，名字本体里的 _ 必须换掉
                dup.name = '7_%s_0.1' % o.name.split('.')[0].replace('_', '-')
                temps.append(dup)

            # 复制 head 并按材质槽拆分
            if head:
                dup = head.copy(); dup.data = head.data.copy()
                context.collection.objects.link(dup)
                bpy.ops.object.select_all(action='DESELECT')
                dup.select_set(True)
                context.view_layer.objects.active = dup
                if len(head.material_slots) >= 5:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.separate(type='MATERIAL')
                    bpy.ops.object.mode_set(mode='OBJECT')
                    parts = [o for o in context.selected_objects if o.type == 'MESH']
                    slot_mats = [s.material for s in head.material_slots]
                    for part in parts:
                        pm = part.material_slots[0].material if part.material_slots else None
                        idx = slot_mats.index(pm) if pm in slot_mats else 0
                        if idx not in self.HEAD_SLOTS:      # 罩层：不导出
                            bpy.data.objects.remove(part, do_unlink=True)
                            continue
                        xname, rg = self.HEAD_SLOTS[idx]
                        img = baked if idx == 1 else first_image(pm)
                        m = simple_export_mat(xname, img) if img else None
                        part.data.materials.clear()
                        if m:
                            part.data.materials.append(m)
                            temp_mats.append(m)
                        part.name = '%s_%s_0.1' % (rg, xname)
                        temps.append(part)
                else:
                    img = first_image(head.material_slots[0].material
                                      if head.material_slots else None)
                    m = simple_export_mat('face', img) if img else None
                    dup.data.materials.clear()
                    if m:
                        dup.data.materials.append(m)
                        temp_mats.append(m)
                    dup.name = '5_face_0.1'
                    temps.append(dup)

            # 输出目录可能不存在；贴图不在输出目录时复制过去（XPS 按 .mesh 同目录找贴图）
            import shutil
            out_dir = os.path.dirname(out_path)
            os.makedirs(out_dir, exist_ok=True)
            for img in used_images:
                if img is None:
                    continue
                src = bpy.path.abspath(img.filepath)
                if os.path.isfile(src) and \
                        os.path.normcase(os.path.dirname(src)) != os.path.normcase(out_dir):
                    shutil.copy2(src, out_dir)

            # 隐藏原件，只导出临时件 + 骨架
            for o in meshes:
                if not o.hide_get():
                    o.hide_set(True)
                    hidden.append(o)
            bpy.ops.object.select_all(action='DESELECT')
            for o in temps:
                o.select_set(True)
            arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
            if arm:
                arm.select_set(True)
                context.view_layer.objects.active = arm

            try:
                bpy.ops.xps_tools.export_model(filepath=out_path, exportOnlySelected=True)
            except TypeError:
                bpy.ops.xps_tools.export_model(filepath=out_path)
        except Exception as e:
            self.report({'ERROR'}, "导出失败: %s" % e)
            return {'CANCELLED'}
        finally:
            for o in temps:
                try:
                    bpy.data.objects.remove(o, do_unlink=True)
                except Exception:
                    pass
            for m in temp_mats:
                try:
                    bpy.data.materials.remove(m)
                except Exception:
                    pass
            for gt in fallback_group:
                try:
                    if gt.users == 0:
                        bpy.data.node_groups.remove(gt)
                except Exception:
                    pass
            for o in hidden:
                try:
                    o.hide_set(False)
                except Exception:
                    pass

        if not os.path.isfile(out_path):
            self.report({'ERROR'}, "导出后没有找到文件: %s" % out_path)
            return {'CANCELLED'}
        self.report({'INFO'}, "XPS 已导出: %s" % out_path)
        return {'FINISHED'}


# ----------------------------------------------------------------------- panel

class ROE_PT_panel(Panel):
    bl_label = "ROE XPS Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ROE'

    def draw(self, context):
        p = context.scene.roe
        col = self.layout.column()
        col.prop(p, 'fbx_path')
        col.prop(p, 'tex_dir')
        col.separator()
        col.operator('roe.import_fbx', icon='IMPORT')
        col.operator('roe.apply_materials', icon='MATERIAL')
        col.separator()
        col.prop(p, 'xps_out')
        col.operator('roe.export_xps', icon='EXPORT')


classes = (ROE_Props, ROE_OT_import_fbx, ROE_OT_apply_materials,
           ROE_OT_export_xps, ROE_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.roe = PointerProperty(type=ROE_Props)


def unregister():
    del bpy.types.Scene.roe
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == '__main__':
    register()
