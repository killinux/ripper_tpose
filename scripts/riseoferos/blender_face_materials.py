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
import json
import re

SOURCE_TEXTURE_HINTS_KEY = 'roe_source_texture_hints'

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
    # g02's original bundles spell the body color suffix "Abedo" instead of
    # "Albedo". Prefer the canonical spelling, but accept that shipped typo.
    patterns = [pattern]
    if 'Albedo' in pattern:
        patterns.append(pattern.replace('Albedo', 'Abedo'))
    roots = [tex_dir]
    normalized = os.path.normpath(tex_dir)
    if os.path.basename(normalized).lower().startswith('_textures'):
        parent = os.path.dirname(normalized)
        roots.extend(path for path in sorted(glob.glob(
            os.path.join(parent, '_textures*')))
                     if os.path.isdir(path) and path not in roots)
    for root in roots:
        for candidate in patterns:
            hits = sorted(glob.glob(os.path.join(root, candidate)))
            if not hits:
                hits = sorted(glob.glob(
                    os.path.join(root, '**', candidate), recursive=True))
            if hits:
                return hits[0]
    return None


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


def source_material_names(obj):
    """Keep the FBX slot names so applying materials again remains lossless."""
    stored = obj.get('roe_source_materials', '')
    if isinstance(stored, str) and stored:
        return stored.split('\n')
    names = [slot.material.name if slot.material else '' for slot in obj.material_slots]
    obj['roe_source_materials'] = '\n'.join(names)
    return names


def current_material_texture_hints(obj):
    hints = []
    for slot in obj.material_slots:
        candidates = []
        material = slot.material
        if material and material.use_nodes and material.node_tree:
            for node in material.node_tree.nodes:
                if node.type != 'TEX_IMAGE' or not node.image:
                    continue
                filename = (os.path.basename(bpy.path.abspath(
                    node.image.filepath or '')) or node.image.name)
                lowered = filename.lower()
                priority = (0 if 'albedo' in lowered or 'abedo' in lowered
                            else 1 if 'normal' in lowered
                            else 2 if 'mgac' in lowered or 'mga' in lowered
                            else 3)
                candidates.append((priority, filename.lower(), filename))
        hints.append(min(candidates)[2] if candidates else '')
    return hints


def source_texture_hints(obj):
    try:
        hints = json.loads(obj.get(SOURCE_TEXTURE_HINTS_KEY, '[]'))
    except (TypeError, ValueError):
        hints = []
    if not isinstance(hints, list) or not hints:
        hints = current_material_texture_hints(obj)
        obj[SOURCE_TEXTURE_HINTS_KEY] = json.dumps(hints)
    return hints


def source_role_texture_patterns(obj, role):
    if obj is None:
        return ()
    feature_tokens = {
        'eye', 'eyes', 'iris', 'eyeball', 'brow', 'eyebrow',
        'eyelid', 'lash', 'tear', 'tears',
    }
    patterns = []
    for source_name in source_material_names(obj):
        clean = re.sub(r'\.\d{3}$', '', source_name).strip()
        tokens = set(re.split(r'[_\W]+', clean.lower()))
        if role == 'face':
            matches = 'face' in tokens and not bool(tokens & feature_tokens)
        elif role == 'eye':
            matches = bool(tokens & {'eye', 'eyes', 'iris', 'eyeball'}) \
                and not bool(tokens & {'brow', 'eyebrow', 'tear', 'tears', 'lash'})
        elif role == 'brow':
            matches = bool(tokens & {'brow', 'eyebrow'})
        else:
            matches = False
        if clean and matches:
            patterns.extend((clean + '_rgbx_Albedo*.png',
                             clean + '_Albedo*.png',
                             clean + '*Albedo*.png'))
    return tuple(patterns)


def is_g09_wing_slot(obj, slot_index, source_name=None):
    """Return True only for the observed G09 HD/LD wing material slots."""
    object_name = re.sub(r'\.\d{3}$', '', obj.name).lower()
    if not re.fullmatch(r'pc_g09_(?:hd|ld)_body', object_name):
        return False
    if source_name is None:
        names = source_material_names(obj)
        source_name = names[slot_index] if slot_index < len(names) else ''
    source_name = re.sub(r'\.\d{3}$', '', source_name.lower())
    return bool(re.fullmatch(r'pc_g09_(?:hd|ld)_wings?\d*', source_name))


def is_wing_slot(obj, slot_index, source_name=None):
    """Identify wing slots without changing historical alpha export rules."""
    if source_name is None:
        names = source_material_names(obj)
        source_name = names[slot_index] if slot_index < len(names) else ''

    def has_wing_token(name):
        return any(re.fullmatch(r'wings?\d*', token)
                   for token in re.split(r'[_\W]+', name.lower()))

    object_name = re.sub(r'\.\d{3}$', '', obj.name)
    return has_wing_token(source_name) or has_wing_token(object_name)


def apply_mesh_materials(obj, tex_dir, face_tex, hair_tex, slot_filter=None):
    """Replace materials without destroying the FBX body/skin/face slot split."""
    me = obj.data
    material_indices = [poly.material_index for poly in me.polygons]
    source_names = source_material_names(obj)
    source_hints = source_texture_hints(obj)
    slot_count = max(
        len(source_names),
        max((poly.material_index for poly in me.polygons), default=0) + 1,
        1,
    )
    source_names.extend([''] * (slot_count - len(source_names)))
    source_hints.extend([''] * (slot_count - len(source_hints)))

    is_hair = 'hair' in obj.name.lower()
    body_tex = None if is_hair else find_tex(
        tex_dir, obj.name.split('.')[0] + '*Albedo*.png')

    def name_variants(name):
        variants = [name]
        without_level = re.sub(
            r'_(?:hd|ld)_', '_', name, count=1, flags=re.IGNORECASE)
        if without_level != name:
            variants.append(without_level)
        return variants

    def named_albedo(name):
        for candidate in name_variants(name):
            # Prefer the complete exported texture stem before the historical
            # broad prefix fallback.  Without this, ``..._wings*Albedo`` also
            # matches ``..._wings2_rgbx_Albedo`` and lexicographic ordering
            # gives the main G09 wing slot the individual-feather atlas.
            for pattern in (candidate + '_rgbx_Albedo*.png',
                            candidate + '_Albedo*.png',
                            candidate + '*Albedo*.png'):
                texture = find_tex(tex_dir, pattern)
                if texture:
                    return texture
        return None

    def hinted_albedo(slot_index):
        hint = source_hints[slot_index] if slot_index < len(source_hints) else ''
        stem = os.path.splitext(os.path.basename(hint))[0]
        if re.search(r'_(?:Albedo|Abedo)$', stem, re.IGNORECASE):
            albedo_stem = stem
        elif re.search(
                r'_(?:Normal|MGAC|MGA|Emission|Emmision)$', stem,
                re.IGNORECASE):
            albedo_stem = re.sub(
                r'_(?:Normal|MGAC|MGA|Emission|Emmision)$', '_Albedo', stem,
                flags=re.IGNORECASE)
        else:
            return None
        return find_tex(tex_dir, albedo_stem + '*.png')

    def slot_albedo(source_name, slot_index):
        """Resolve multi-atlas meshes such as a07 body1/body2 by source slot."""
        hinted = hinted_albedo(slot_index)
        if hinted:
            return hinted
        compact = re.sub(r'\s+', '', re.sub(r'\.\d{3}$', '', source_name))
        if compact:
            direct = named_albedo(compact)
            if direct:
                return direct
        for candidate in name_variants(compact):
            skin_match = re.search(r'skin(\d*)', candidate, re.IGNORECASE)
            if skin_match:
                atlas_number = skin_match.group(1) or '1'
                atlas_name = (
                    candidate[:skin_match.start()] + 'body' + atlas_number
                    + candidate[skin_match.end():])
                skin_tex = named_albedo(atlas_name)
                if skin_tex:
                    return skin_tex
        return body_tex

    missing = []
    materials = []
    for index, source_name in enumerate(source_names):
        if slot_filter is not None and not slot_filter(
                obj, index, source_name):
            materials.append(None)
            continue
        tokens = re.split(r'[_\W]+', source_name.lower())
        is_skin = any(token == 'skin' or re.fullmatch(r'skin\d+', token)
                      for token in tokens)
        is_tear = any(token in {'tear', 'tears'} for token in tokens)
        material_name = '%s_%02d_%s_mat'
        if is_tear:
            materials.append(transparent_mat(
                material_name % (obj.name, index, 'eye_overlay')))
            continue
        if is_hair:
            role, tex, desat, hashed = 'hair', hair_tex, False, False
        elif 'face' in tokens:
            role, tex, desat, hashed = 'face', face_tex, True, True
        elif is_skin:
            role, tex, desat, hashed = (
                'skin', slot_albedo(source_name, index), True, True)
        else:
            role = 'body'
            tex = slot_albedo(source_name, index)
            desat = 'body1' in obj.name.lower()
            hashed = True
        if is_g09_wing_slot(obj, index, source_name):
            # Binary wing cutouts are stable with CLIP in Blender 3.6; HASHED
            # shows noisy black cards where the G09 layers overlap.
            hashed = False
        if not tex:
            missing.append('%s[%d:%s]' % (obj.name, index, source_name or role))
        materials.append(albedo_mat(
            material_name % (obj.name, index, role),
            tex,
            desat=desat,
            hashed=hashed,
        ))

    if slot_filter is None:
        me.materials.clear()
        for material in materials:
            me.materials.append(material)
    else:
        while len(me.materials) < slot_count:
            placeholder = bpy.data.materials.new(
                '%s_%02d_preserved_mat' % (obj.name, len(me.materials)))
            me.materials.append(placeholder)
        for index, material in enumerate(materials):
            if material is not None:
                me.materials[index] = material
    for poly, material_index in zip(me.polygons, material_indices):
        poly.material_index = min(material_index, len(materials) - 1)
    me.update()
    print('[mat] %s source_slots=%s' % (obj.name, source_names))
    return missing


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


def classify_head(o, source_material_names=None, source_material_indices=None):
    """按连通块 + 骨骼权重给 head 每个面分类。
    返回 {poly_index: slot}，slot: 1眼球 2睫毛 3眉毛 4罩层（其余留 0 脸）。"""
    me = o.data
    if source_material_names is None:
        source_material_names = [
            slot.material.name if slot.material else '' for slot in o.material_slots]
    if source_material_indices is None:
        source_material_indices = [poly.material_index for poly in me.polygons]
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
                                 'source_mats': set(),
                                 'verts': set(), 'umin': 9.0, 'umax': -9.0,
                                 'vmin': 9.0, 'vmax': -9.0})
        c['polys'] += 1
        if p.index < len(source_material_indices):
            c['source_mats'].add(source_material_indices[p.index])
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

    def source_tokens(component):
        tokens = set()
        for material_index in component['source_mats']:
            if 0 <= material_index < len(source_material_names):
                tokens.update(re.split(
                    r'[_\W]+', source_material_names[material_index].lower()))
        return tokens

    def source_is_eye(component):
        tokens = source_tokens(component)
        eye_tokens = {'eye', 'eyes', 'iris', 'eyeball'}
        excluded = {'brow', 'eyebrow', 'eyelid', 'lash', 'tear', 'tears'}
        return bool(tokens & eye_tokens) and not bool(tokens & excluded)

    def source_is_tear(component):
        return bool(source_tokens(component) & {'tear', 'tears'})

    def source_is_face(component):
        tokens = source_tokens(component)
        excluded = {
            'eye', 'eyes', 'iris', 'eyeball', 'brow', 'eyebrow',
            'eyelid', 'lash', 'tear', 'tears',
        }
        return 'face' in tokens and not bool(tokens & excluded)

    def source_is_brow_or_lash(component):
        return bool(source_tokens(component) & {
            'brow', 'eyebrow', 'brows', 'eyebrows',
            'lash', 'lashes', 'eyelash', 'eyelashes',
        })

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
        geometric_eye = (
            (not has_semantic_groups or source_is_eye(c))
            and uv0 and 250 <= c['polys'] <= 800
            and u_span > 0.85 and v_span > 0.85
        )
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
        component_source_tokens = source_tokens(c)

        if r in eye_roots:
            cls[r] = 1
        elif source_is_tear(c):
            cls[r] = 4
        elif source_is_face(c):
            # F10's face atlas has a narrow UV island with eyelid influence;
            # explicit source semantics must win over the overlay fallback.
            cls[r] = 0
        elif has_semantic_groups and c['umax'] <= 1.01 and c['polys'] < 400 \
                and w['brow'] > w['other'] and w['brow'] > w['lid']:
            cls[r] = 3
        elif has_semantic_groups and c['umax'] <= 1.01 and c['polys'] < 400 \
                and w['lid'] > w['other']:
            cls[r] = 2
        elif has_semantic_groups and c['umax'] > 1.01 and u_span < 0.15 \
                and c['polys'] > 100 and w['lid'] > 0.3 * tot:
            cls[r] = 4
        elif source_is_brow_or_lash(c) and eye_z is not None:
            if c['center_z'] > eye_z + eye_height * 0.15:
                cls[r] = 3
            else:
                cls[r] = 2
        elif not has_semantic_groups and uv0 and 60 <= c['polys'] <= 300 \
                and u_span > 0.5 and v_span > 0.4 and eye_z is not None \
                and c['center_z'] > eye_z + eye_height * 0.15:
            cls[r] = 3
        elif not has_semantic_groups and uv0 and 100 <= c['polys'] <= 300 \
                and u_span > 0.45 and v_span > 0.35 and near_eye:
            cls[r] = 2
        elif not has_semantic_groups and uv0 and c['polys'] < 100 and near_eye \
                and (('eyebrow' in component_source_tokens
                      or 'lash' in component_source_tokens)
                     or (20 <= c['polys'] <= 50 and 0.15 <= u_span <= 0.35
                         and 0.25 <= v_span <= 0.35)):
            # Xtra-bone exports contain four small upper-lash cards (24/48 faces).
            # Geometry-only thresholds miss them, leaving solid face-texture wedges.
            cls[r] = 2
        elif not has_semantic_groups and c['umin'] > 1.0 \
                and u_span < 0.2 and v_span < 0.2 \
                and 100 <= c['polys'] <= 600 and near_eye:
            cls[r] = 4

    source_slot_tokens = [
        set(re.split(r'[_\W]+', name.lower()))
        for name in source_material_names
    ]
    feature_tokens = {
        'eye', 'eyes', 'iris', 'eyeball', 'brow', 'eyebrow',
        'eyelid', 'lash', 'tear', 'tears',
    }
    explicit_face_slots = {
        index for index, tokens in enumerate(source_slot_tokens)
        if 'face' in tokens and not bool(tokens & feature_tokens)
    }
    explicit_tear_slots = {
        index for index, tokens in enumerate(source_slot_tokens)
        if bool(tokens & {'tear', 'tears'})
    }
    has_separate_head_features = bool(explicit_face_slots) and any(
        tokens & feature_tokens for tokens in source_slot_tokens)

    classifications = {}
    for polygon in me.polygons:
        slot = cls.get(find(polygon.vertices[0]), 0)
        source_index = (source_material_indices[polygon.index]
                        if polygon.index < len(source_material_indices)
                        else -1)
        if source_index in explicit_tear_slots:
            slot = 4
        elif has_separate_head_features \
                and source_index in explicit_face_slots:
            slot = 0
        classifications[polygon.index] = slot
    return classifications


def apply_all(tex_dir, source_fbx=''):
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    head = find_head(meshes)

    bt = None
    character_prefix = None
    for o in meshes:
        match = re.match(r'pc_([a-z])\d', o.name.lower())
        if match:
            bt = match.group(1)
        prefix_match = re.match(r'(pc_[a-z]\d+_(?:hd|ld))', o.name.lower())
        if prefix_match:
            character_prefix = prefix_match.group(1)
        if bt and character_prefix:
            break
    if not (bt and character_prefix):
        path_match = re.search(
            r'(pc_([a-z])\d+_(?:hd|ld))', source_fbx.lower())
        if path_match:
            character_prefix = character_prefix or path_match.group(1)
            bt = bt or path_match.group(2)

    def pick(*patterns):
        for pattern in patterns:
            if pattern:
                hit = find_tex(tex_dir, pattern)
                if hit:
                    return hit
        return None

    face_tex = pick(*source_role_texture_patterns(head, 'face'),
                    character_prefix + '_face*Albedo*.png'
                    if character_prefix else None,
                    'pc_%s_nk_face*Albedo*.png' % bt if bt else None,
                    'pc_*_nk_face*Albedo*.png', '*face*Albedo*.png')
    iris_tex = pick(*source_role_texture_patterns(head, 'eye'),
                    character_prefix + '_eye_iris*Albedo*.png'
                    if character_prefix else None,
                    'pc_%s_nk_eye_iris*Albedo*.png' % bt if bt else None,
                    '*eye_iris*Albedo*.png',
                    'pc_%s_nk_eyes*Albedo*.png' % bt if bt else None,
                    'pc_%s_ld_eyes*Albedo*.png' % bt if bt else None)
    brow_tex = pick(*source_role_texture_patterns(head, 'brow'),
                    'pc_%s_nk_eyebrow*Albedo*.png' % bt if bt else None,
                    '*eyebrow*Albedo*.png')
    hair_tex = pick(character_prefix + '_hair*Albedo*.png'
                    if character_prefix else None,
                    'pc_%s_nk_hair*Albedo*.png' % bt if bt else None,
                    'pc_%s_*hair*Albedo*.png' % bt if bt else None,
                    '*hair*Albedo*.png')
    baked_face_strokes = bt in {'i', 'j'} and not brow_tex
    print('[mat] textures: face=%s iris=%s brow=%s hair=%s' %
          (face_tex, iris_tex, brow_tex, hair_tex))

    missing_textures = []
    for o in meshes:
        if o is head:
            continue
        missing_textures.extend(apply_mesh_materials(o, tex_dir, face_tex, hair_tex))

    if missing_textures:
        print('[mat] WARNING: 未找到贴图: %s' % ', '.join(missing_textures))

    if head is None:
        print('[mat] WARNING: 没找到 head 网格（名称或 Eyeball 顶点组均未匹配）')
        return
    missing = [name for name, path in (('face', face_tex), ('eye_iris', iris_tex),
                                       ('eyebrow', brow_tex))
               if not path and not (name == 'eyebrow' and baked_face_strokes)]
    if missing:
        print('[mat] ERROR: 缺少贴图: %s；可选择 _textures 或角色导出根目录' % ', '.join(missing))
        return
    me = head.data
    source_head_names = [
        slot.material.name if slot.material else '' for slot in head.material_slots]
    source_head_indices = [p.material_index for p in me.polygons]
    me.materials.clear()
    me.materials.append(albedo_mat('face', face_tex, desat=True))          # slot0
    me.materials.append(eye_mat('eye', iris_tex))                          # slot1
    if brow_tex:
        me.materials.append(stroke_mat(
            'lash', brow_tex, LASH_ALPHA_GAIN, LASH_DARKEN))               # slot2
        me.materials.append(stroke_mat('brow', brow_tex))                  # slot3
    else:
        me.materials.append(transparent_mat('lash'))                       # slot2
        me.materials.append(transparent_mat('brow'))                       # slot3
    me.materials.append(transparent_mat('eye_overlay'))                    # slot4
    cls = classify_head(head, source_head_names, source_head_indices)
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
        apply_all(TEX_DIR, fbx)
        if len(args) > 2:
            bpy.ops.wm.save_as_mainfile(filepath=args[2])
            print('[mat] saved: %s' % args[2])
    else:
        apply_all(TEX_DIR)


if __name__ == '__main__':
    main()
