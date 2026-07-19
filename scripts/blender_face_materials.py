"""Rise of Eros 角色材质一键搭建（含眼球/睫毛/眉毛修复）。

在 Blender 里对已导入的角色 FBX（extract_character.ps1 导出）自动挂材质：
  - body/hair: Albedo + 贴图自带 alpha（CLIP）
  - 皮肤类(body1/脸): HueSaturation 降饱和 0.85（否则偏粉）
  - head 网格: 按"连通块 + 骨骼权重"把面拆成 5 个材质槽
      slot0 脸皮肤 / slot1 眼球 / slot2 睫毛 / slot3 眉毛 / slot4 眼部罩层
    详见 docs/face-eye-materials.md

用法 A（GUI）: 导入 FBX 后，在 Text Editor 打开本文件，改 TEX_DIR 后 Run Script。
用法 B（无头）:
  blender --background --python blender_face_materials.py -- <fbx路径> <贴图目录> [输出.blend]
"""
import bpy
import os
import sys
import glob
import re

# GUI 方式运行时改这里（无头方式用命令行参数覆盖）
TEX_DIR = 'D:/roe_exports/g11/xps'

SKIN_DESAT = 0.85       # 皮肤降饱和
IRIS_CENTER = (0.5, 0.49)   # 虹膜在眼球 UV 上的中心
IRIS_R_IN = 0.235       # 虹膜半径（内，全虹膜）
IRIS_R_OUT = 0.285      # 虹膜半径（外，羽化到眼白）
SCLERA = (0.90, 0.88, 0.87, 1.0)
LASH_ALPHA_GAIN = 1.5   # 睫毛 alpha 增益
LASH_DARKEN = 0.55      # 睫毛颜色明度


def find_tex(tex_dir, pattern):
    hits = sorted(glob.glob(os.path.join(tex_dir, pattern)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(tex_dir, '**', pattern), recursive=True))
    return hits[0] if hits else None


def find_head(objects):
    meshes = [o for o in objects if o.type == 'MESH']
    weighted = [o for o in meshes
                if any('eyeball' in g.name.lower() for g in o.vertex_groups)]
    if weighted:
        return max(weighted, key=lambda o: len(o.data.polygons))
    named = []
    for o in meshes:
        names = (o.name, getattr(o.data, 'name', ''))
        if any('head' in re.split(r'[_\W]+', name.lower()) for name in names):
            named.append(o)
    return max(named, key=lambda o: len(o.data.polygons)) if named else None


def new_mat(name):
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


def tex_node(nt, path, loc=(-500, 200)):
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = bpy.data.images.load(path, check_existing=True)
    t.location = loc
    return t


def albedo_mat(name, tex_path, desat=False, hashed=False):
    """普通网格材质：Albedo + 贴图 alpha，可选降饱和。
    hashed=True 用 HASHED 半透明（丝袜等半透明衣物 CLIP 会被裁没）。"""
    m, nt, b = new_mat(name)
    if not tex_path:
        return m
    t = tex_node(nt, tex_path)
    if desat:
        h = nt.nodes.new('ShaderNodeHueSaturation'); h.location = (-150, 200)
        h.inputs['Saturation'].default_value = SKIN_DESAT
        nt.links.new(t.outputs['Color'], h.inputs['Color'])
        nt.links.new(h.outputs['Color'], b.inputs['Base Color'])
    else:
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    m.blend_method = 'HASHED' if hashed else 'CLIP'
    m.shadow_method = 'CLIP'
    return m


def eye_mat(name, iris_path):
    """眼球：程序化眼白 + 虹膜贴图圆盘（虹膜贴图外圈是棕色，直接贴会整眼棕）。"""
    m, nt, b = new_mat(name)
    b.inputs['Roughness'].default_value = 0.15
    t = tex_node(nt, iris_path)
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
    """眉毛/睫毛：RGB 是填充色层、alpha 通道才是毛发笔触，必须用贴图真 alpha。"""
    m, nt, b = new_mat(name)
    b.inputs['Roughness'].default_value = 0.6
    b.inputs['Specular'].default_value = 0.1
    t = tex_node(nt, tex_path)
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
    """眼部罩层：必须用 Transparent BSDF。
    Principled alpha=0 在 EEVEE 下仍残留镜面高光（会在眼周留下灰白色块）。"""
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


def classify_head(o):
    """按连通块 + 骨骼权重给 head 每个面分类。
    返回 {poly_index: slot}，slot: 1眼球 2睫毛 3眉毛 4罩层（其余留 0 脸）。"""
    me = o.data
    n = len(me.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in me.edges:
        a, b_ = e.vertices
        ra, rb = find(a), find(b_)
        if ra != rb:
            parent[ra] = rb

    gi = {g.index: g.name for g in o.vertex_groups}

    def gclass(name):
        name = name.lower()
        if 'eyeball' in name: return 'eyeball'
        if 'eyebrow' in name: return 'brow'
        if 'eyelid' in name: return 'lid'
        return 'other'

    vclass = {}
    for v in me.vertices:
        d = {}
        for g in v.groups:
            c = gclass(gi[g.group])
            d[c] = d.get(c, 0) + g.weight
        vclass[v.index] = d

    if not me.uv_layers.active:
        return {p.index: 0 for p in me.polygons}
    uvd = me.uv_layers.active.data
    comps = {}
    for p in me.polygons:
        r = find(p.vertices[0])
        c = comps.setdefault(r, {'polys': 0, 'w': {'eyeball': 0, 'brow': 0, 'lid': 0, 'other': 0},
                                 'verts': set(), 'umin': 9.0, 'umax': -9.0,
                                 'vmin': 9.0, 'vmax': -9.0})
        c['polys'] += 1
        c['verts'].update(p.vertices)
        for vi in p.vertices:
            for k, val in vclass[vi].items():
                c['w'][k] += val
        for li in p.loop_indices:
            u, v = uvd[li].uv
            if u < c['umin']: c['umin'] = u
            if u > c['umax']: c['umax'] = u
            if v < c['vmin']: c['vmin'] = v
            if v > c['vmax']: c['vmax'] = v

    for c in comps.values():
        coords = [me.vertices[vi].co for vi in c['verts']]
        c['center_z'] = sum(co.z for co in coords) / len(coords)
        c['size_z'] = max(co.z for co in coords) - min(co.z for co in coords)

    cls = {}
    has_semantic_groups = any(gclass(name) != 'other' for name in gi.values())
    eye_roots = set()
    for r, c in comps.items():
        w = c['w']
        tot = sum(w.values()) + 1e-6
        u_span = c['umax'] - c['umin']
        v_span = c['vmax'] - c['vmin']
        uv0 = c['umin'] >= -0.01 and c['umax'] <= 1.01 \
            and c['vmin'] >= -0.01 and c['vmax'] <= 1.01
        geometric_eye = (not has_semantic_groups and uv0 and 250 <= c['polys'] <= 800
                         and u_span > 0.85 and v_span > 0.85)
        if w['eyeball'] > 0.9 * tot or geometric_eye:
            eye_roots.add(r)

    eye_z = (sum(comps[r]['center_z'] for r in eye_roots) / len(eye_roots)
             if eye_roots else None)
    eye_height = (sum(comps[r]['size_z'] for r in eye_roots) / len(eye_roots)
                  if eye_roots else 0.0)

    for r, c in comps.items():
        w = c['w']
        tot = sum(w.values()) + 1e-6
        u_span = c['umax'] - c['umin']
        v_span = c['vmax'] - c['vmin']
        uv0 = c['umin'] >= -0.01 and c['umax'] <= 1.01 \
            and c['vmin'] >= -0.01 and c['vmax'] <= 1.01
        near_eye = (eye_z is not None
                    and abs(c['center_z'] - eye_z) <= max(eye_height * 0.45, 1e-6))

        if r in eye_roots:
            cls[r] = 1
        elif has_semantic_groups and c['umax'] <= 1.01 and c['polys'] < 400 \
                and w['brow'] > w['other'] and w['brow'] > w['lid']:
            cls[r] = 3
        elif has_semantic_groups and c['umax'] <= 1.01 and c['polys'] < 400 \
                and w['lid'] > w['other']:
            cls[r] = 2
        elif has_semantic_groups and c['umax'] > 1.01 and u_span < 0.15 \
                and c['polys'] > 100 and w['lid'] > 0.3 * tot:
            cls[r] = 4
        elif not has_semantic_groups and uv0 and 60 <= c['polys'] <= 300 \
                and u_span > 0.5 and v_span > 0.4 and eye_z is not None \
                and c['center_z'] > eye_z + eye_height * 0.15:
            cls[r] = 3
        elif not has_semantic_groups and uv0 and 100 <= c['polys'] <= 300 \
                and u_span > 0.45 and v_span > 0.35 and near_eye:
            cls[r] = 2
        elif not has_semantic_groups and c['umin'] > 1.0 \
                and u_span < 0.2 and v_span < 0.2 \
                and 100 <= c['polys'] <= 600 and near_eye:
            cls[r] = 4

    return {p.index: cls.get(find(p.vertices[0]), 0) for p in me.polygons}


def apply_all(tex_dir):
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    head = find_head(meshes)

    bt = None
    for o in meshes:
        match = re.match(r'pc_([a-z])\d', o.name.lower())
        if match:
            bt = match.group(1)
            break

    def pick(*patterns):
        for pattern in patterns:
            if pattern:
                hit = find_tex(tex_dir, pattern)
                if hit:
                    return hit
        return None

    face_tex = pick('pc_%s_nk_face*Albedo*.png' % bt if bt else None,
                    'pc_*_nk_face*Albedo*.png', '*face*Albedo*.png')
    iris_tex = pick('pc_%s_nk_eye_iris*Albedo*.png' % bt if bt else None,
                    '*eye_iris*Albedo*.png')
    brow_tex = pick('pc_%s_nk_eyebrow*Albedo*.png' % bt if bt else None,
                    '*eyebrow*Albedo*.png')
    hair_tex = pick('pc_%s_nk_hair*Albedo*.png' % bt if bt else None,
                    'pc_%s_*hair*Albedo*.png' % bt if bt else None,
                    '*hair*Albedo*.png')
    print('[mat] textures: face=%s iris=%s brow=%s hair=%s' %
          (face_tex, iris_tex, brow_tex, hair_tex))

    for o in meshes:
        me = o.data
        if o is head:
            continue
        if 'hair' in o.name.lower():
            m = albedo_mat(o.name + '_mat', hair_tex)
        else:
            # body 网格按自身名字匹配贴图；body1（带裸露皮肤）降饱和
            tex = find_tex(tex_dir, o.name + '*Albedo*.png')
            m = albedo_mat(o.name + '_mat', tex, desat=('body1' in o.name), hashed=True)
        me.materials.clear()
        me.materials.append(m)
        # 原 FBX 可能有多个槽（如 body1+skin），全部指向同一材质
        while len(me.materials) < max((p.material_index for p in me.polygons), default=0) + 1:
            me.materials.append(m)
        print('[mat] %s -> %s' % (o.name, m.name))

    if head is None:
        print('[mat] WARNING: 没找到 head 网格（名称或 Eyeball 顶点组均未匹配）')
        return
    missing = [name for name, path in (('face', face_tex), ('eye_iris', iris_tex),
                                       ('eyebrow', brow_tex)) if not path]
    if missing:
        print('[mat] ERROR: 缺少贴图: %s；可选择 _textures 或角色导出根目录' % ', '.join(missing))
        return
    me = head.data
    me.materials.clear()
    me.materials.append(albedo_mat('face', face_tex, desat=True))          # slot0
    me.materials.append(eye_mat('eye', iris_tex))                          # slot1
    me.materials.append(stroke_mat('lash', brow_tex, LASH_ALPHA_GAIN, LASH_DARKEN))  # slot2
    me.materials.append(stroke_mat('brow', brow_tex))                      # slot3
    me.materials.append(transparent_mat('eye_overlay'))                    # slot4
    cls = classify_head(head)
    counts = {}
    for p in me.polygons:
        idx = cls[p.index]
        p.material_index = idx
        counts[idx] = counts.get(idx, 0) + 1
    me.update()
    print('[mat] head 分槽: %s' % counts)


def main():
    global TEX_DIR
    argv = sys.argv
    if '--' in argv:
        args = argv[argv.index('--') + 1:]
        fbx, TEX_DIR = args[0], args[1]
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=fbx, automatic_bone_orientation=True,
                                 use_image_search=False)
        apply_all(TEX_DIR)
        if len(args) > 2:
            bpy.ops.wm.save_as_mainfile(filepath=args[2])
            print('[mat] saved: %s' % args[2])
    else:
        apply_all(TEX_DIR)


if __name__ == '__main__':
    main()
