"""Build a Vindictus (Mabinogi Heroes, Source engine) character in Blender from .mdl files, with game materials.

    blender -b --factory-startup -P build_blend.py -- <config.json>        (written by export_model.py)

One armature (the shared ValveBiped female skeleton, game bone names), one object per <tag>.<material>, every piece
skinned to it; model space -> Blender: 1 unit = 1 inch (scale 0.0254), turned to face -Y.  Materials follow the
game shaders:
  dye masks (Heroes_Armor / hair / brows) -> node group "VindDye": albedo = sum_c (k*mask_c)^2.2 * colour_c
  Heroes_Faceskin skin    -> base + normal (DirectX, green flipped) + subsurface (real-skin radii) + phong-exponent
                             map as roughness;  $surface metal / cloth -> metal / satin;  Refract -> glass
  hair ($hairmask)        -> anisotropic along the strands, hashed alpha
  eyes                    -> sclera (mesh UV) + iris projected like studiorender (IrisUV)
Per model spec (config 'models'): only_materials / hide_materials / skip_models, uv_from (borrow UVs from another
model's surface; normal_match + warp for borrowed faces), feet_from, replace_region, extend_skin / skin_fill / tuck.
Config: alias / override / synth / solid materials, dye colours, figure (the heroine's .fig body shape, baked into the
rest pose), flexes (Source facial flexes -> shape keys, default on), lights / HDRI, preview views, out_blend.
"""
import bpy, sys, os, json, math, re, glob
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import source_mdl

cfg = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))
SCALE = cfg.get('scale', 0.0254)
FLIP_NORMAL_G = cfg.get('flip_normal_green', True)
stats = json.load(open(cfg['tex_stats'])) if cfg.get('tex_stats') else {}
ALIAS = {k.lower(): v.lower() for k, v in cfg.get('alias', {}).items()}
OVERRIDE = {k.lower(): v.lower() for k, v in cfg.get('override', {}).items()}
SYNTH = {k.lower(): v for k, v in cfg.get('synth', {}).items()}
SOLID = {k.lower(): v for k, v in cfg.get('solid', {}).items()}     # texture not in the data -> plain colour (e.g. a scalp)
METAL_CH = {k.lower(): v for k, v in cfg.get('metal_channels', {}).items()}
DYE = {k.lower(): v for k, v in cfg.get('dye', {}).items()}
FORCE_DYE = {k.lower() for k in cfg.get('force_dye', [])}    # masks the purity test misses (mixed R+G dots etc.)
DYE_DEFAULT = cfg.get('dye_default', [[0.5, 0.03, 0.05], [0.8, 0.55, 0.18], [0.02, 0.02, 0.025]])
DYE_GAIN = cfg.get('dye_gain', 2.0)

# ------------------------------------------------------------------ material index (vmt + png)
vmt_by_path, vmt_by_base, png_by_base = {}, {}, {}
for root in cfg['material_roots']:
    for p in glob.glob(os.path.join(root, 'materials', '**', '*.vmt'), recursive=True):
        rel = os.path.relpath(p, os.path.join(root, 'materials')).replace('\\', '/').lower()
        if rel.startswith('vgui/'):
            continue
        vmt_by_path[rel] = p
        vmt_by_base.setdefault(os.path.splitext(os.path.basename(p))[0].lower(), p)
for d in cfg['png_dirs']:
    for p in glob.glob(os.path.join(d, '*.png')):
        png_by_base.setdefault(os.path.splitext(os.path.basename(p))[0].lower(), p)


def parse_vmt(path):
    t = open(path, 'r', errors='ignore').read()
    t = re.sub(r'//[^\n]*', '', t)            # commented-out parameters are not used by the game
    shader = (re.match(r'\s*"?([A-Za-z0-9_]+)"?', t) or [None, ''])[1].lower()
    kv = {}
    for k, v in re.findall(r'"\$([a-z0-9_]+)"\s+"?([^"\r\n]*)"?', t, re.I):
        kv[k.lower()] = v.strip()
    return shader, kv


def find_vmt(name, cddirs):
    n = name.lower()
    if n in OVERRIDE and OVERRIDE[n] in vmt_by_base:
        return vmt_by_base[OVERRIDE[n]]
    for cd in cddirs:
        p = vmt_by_path.get((cd.replace('\\', '/').lower() + n + '.vmt').lstrip('/'))
        if p:
            return p
    if n in vmt_by_base:
        return vmt_by_base[n]
    if n in ALIAS and ALIAS[n] in vmt_by_base:
        return vmt_by_base[ALIAS[n]]
    return None


def png_of(texpath):
    if not texpath:
        return None
    b = os.path.basename(texpath.replace('\\', '/')).lower()
    # a texture missing from the data can be aliased like a material (e.g. an iris -> another eye's iris)
    return png_by_base.get(b) or png_by_base.get(ALIAS.get(b, ''))

# ------------------------------------------------------------------ coordinates
AX = Matrix.Identity(3)       # decided after loading (front -> -Y)


def conv(p):
    return (AX @ Vector(p)) * SCALE


def convd(n):
    return (AX @ Vector(n)).normalized()


def mat3x4(f):
    return Matrix(((f[0], f[1], f[2], f[3]), (f[4], f[5], f[6], f[7]), (f[8], f[9], f[10], f[11]), (0, 0, 0, 1)))

# ------------------------------------------------------------------ load models
models = []
for spec in cfg['models']:
    sm = source_mdl.load_model(spec['mdl'])
    models.append((spec, sm))
    print('loaded', os.path.basename(spec['mdl']), 'bones', len(sm.bones))

# bone bind matrices (model space) by name, from the first model that has the bone
bind = {}
parent_of = {}
order = []
for spec, sm in models:
    for b in sm.bones:
        if b.name in bind:
            continue
        bind[b.name] = mat3x4(b.pose_to_bone).inverted()
        parent_of[b.name] = sm.bones[b.parent].name if b.parent >= 0 else None
        order.append(b.name)

# facing: eyes are in front of the head bone -> that side becomes -Y
front_sign = -1
for spec, sm in models:
    for bp in sm.bodyparts:
        for md in bp.models:
            for e in md.eyeballs:
                hb = bind[sm.bones[e.bone].name]
                eo = hb @ Vector(e.org)
                front_sign = 1 if (eo.y - hb.translation.y) > 0 else -1
                break
if front_sign > 0:
    AX = Matrix.Rotation(math.pi, 3, 'Z')
print('front along model %sY -> rotated %s' % ('+' if front_sign > 0 else '-', front_sign > 0))

# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
colls = {}


def coll(name):
    if name not in colls:
        c = bpy.data.collections.new(name)
        scene.collection.children.link(c)
        colls[name] = c
    return colls[name]

# armature
arm_data = bpy.data.armatures.new(cfg.get('name', 'Vindictus') + '_rig')
arm = bpy.data.objects.new(cfg.get('name', 'Vindictus') + '_rig', arm_data)
coll(cfg.get('rig_collection', 'Rig')).objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
R = Matrix(((0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))   # blender bone axes from source bone axes
A4 = AX.to_4x4()
heads = {n: (A4 @ bind[n]).translation * SCALE for n in order}
children = {}
for n in order:
    if parent_of[n]:
        children.setdefault(parent_of[n], []).append(n)
ebs = {}
for n in order:
    eb = arm_data.edit_bones.new(n)
    kids = [heads[c] for c in children.get(n, [])]
    L = max(((k - heads[n]).length for k in kids), default=0) or 0.04
    L = min(max(L, 0.01), 0.25)
    eb.head = (0, 0, 0)
    eb.tail = (0, L, 0)
    M = A4 @ bind[n] @ R
    M.translation = heads[n]
    eb.matrix = M
    ebs[n] = eb
for n in order:
    if parent_of[n]:
        ebs[n].parent = ebs[parent_of[n]]
bpy.ops.object.mode_set(mode='OBJECT')

# ------------------------------------------------------------------ materials
def dye_group():
    g = bpy.data.node_groups.get('VindDye')
    if g:
        return g
    g = bpy.data.node_groups.new('VindDye', 'ShaderNodeTree')
    gi = g.nodes.new('NodeGroupInput'); go = g.nodes.new('NodeGroupOutput')
    g.inputs.new('NodeSocketColor', 'Mask (RGB, Non-Color)')
    g.inputs.new('NodeSocketColor', '染色1 (R)'); g.inputs.new('NodeSocketColor', '染色2 (G)'); g.inputs.new('NodeSocketColor', '染色3 (B)')
    g.inputs.new('NodeSocketFloat', '强度 Gain'); g.inputs['强度 Gain'].default_value = DYE_GAIN
    g.outputs.new('NodeSocketColor', 'Color')
    sep = g.nodes.new('ShaderNodeSeparateRGB')
    g.links.new(gi.outputs[0], sep.inputs[0])
    acc = None
    for c, sock in enumerate(('R', 'G', 'B')):
        mul = g.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'
        g.links.new(sep.outputs[sock], mul.inputs[0]); g.links.new(gi.outputs[4], mul.inputs[1])
        pw = g.nodes.new('ShaderNodeMath'); pw.operation = 'POWER'; pw.inputs[1].default_value = 2.2
        g.links.new(mul.outputs[0], pw.inputs[0])
        mix = g.nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1.0
        g.links.new(pw.outputs[0], mix.inputs[1]); g.links.new(gi.outputs[1 + c], mix.inputs[2])
        if acc is None:
            acc = mix
        else:
            add = g.nodes.new('ShaderNodeMixRGB'); add.blend_type = 'ADD'; add.inputs[0].default_value = 1.0
            g.links.new(acc.outputs[0], add.inputs[1]); g.links.new(mix.outputs[0], add.inputs[2])
            acc = add
    g.links.new(acc.outputs[0], go.inputs[0])
    return g


def img(path, noncolor=False):
    im = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = 'Non-Color'
    return im


def fnum(kv, key, default):
    try:
        return float(str(kv.get(key, default)).strip('[] '))
    except ValueError:
        return default


def phong_to_rough(exp):
    """Blinn-Phong exponent -> GGX roughness (r = sqrt(2 / (n + 2)))"""
    return max(0.04, min(0.9, (2.0 / (max(exp, 0.0) + 2.0)) ** 0.5))


def add_normal(nt, bsdf, path, x=-900, y=-420):
    """normal map; Vindictus maps are DirectX (Y down) -> green flipped (curl-tested on every map)"""
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img(path, True); t.location = (x, y)
    src = t.outputs['Color']
    if FLIP_NORMAL_G:
        sep = nt.nodes.new('ShaderNodeSeparateRGB'); sep.location = (x + 250, y)
        inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0; inv.location = (x + 400, y - 80)
        com = nt.nodes.new('ShaderNodeCombineRGB'); com.location = (x + 550, y)
        nt.links.new(src, sep.inputs[0]); nt.links.new(sep.outputs['R'], com.inputs['R'])
        nt.links.new(sep.outputs['G'], inv.inputs[1]); nt.links.new(inv.outputs[0], com.inputs['G'])
        nt.links.new(sep.outputs['B'], com.inputs['B'])
        src = com.outputs[0]
    nm = nt.nodes.new('ShaderNodeNormalMap'); nm.location = (x + 700, y)
    nt.links.new(src, nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return t


def map_range(nt, src, lo, hi, x, y):
    m = nt.nodes.new('ShaderNodeMapRange'); m.location = (x, y)
    m.inputs['To Min'].default_value = lo; m.inputs['To Max'].default_value = hi
    nt.links.new(src, m.inputs['Value'])
    return m.outputs['Result']


def set_in(bsdf, key, val):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = val


# Blender 3.x Principled: the scatter distance is Subsurface Radius * Subsurface.  Real skin ~ 3.6 / 1.35 / 0.75 mm
# (R/G/B).  The old 0.12 * (1, 0.22, 0.1) m = 12 cm of red scatter bled the red out of thin parts (cyan neck and
# fingers, glowing nose tip).
SSS_W = cfg.get('sss_weight', 0.3)
SSS_MM = cfg.get('sss_radius_mm', [3.6, 1.35, 0.75])


def set_skin_sss(bsdf):
    set_in(bsdf, 'Subsurface', SSS_W)
    set_in(bsdf, 'Subsurface Radius', tuple(r / 1000.0 / max(SSS_W, 1e-4) for r in SSS_MM))


def build_material(name, cddirs, eyeball=None):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (0, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    synth = SYNTH.get(name.lower())
    vp = find_vmt(name, cddirs)
    shader, kv = parse_vmt(vp) if vp else ('', {})
    mat['vind_vmt'] = vp or ''
    if synth and not vp:
        # material missing from the game data (e.g. qipao upper_m = collar ornaments): plain metal, documented
        set_in(bsdf, 'Base Color', (*synth['metal'], 1)); set_in(bsdf, 'Metallic', 1.0)
        set_in(bsdf, 'Roughness', synth.get('roughness', 0.28)); set_in(bsdf, 'Specular', 0.5)
        mat['vind_kind'] = 'synth_metal'
        print('MAT %-30s SYNTH metal %s' % (name, synth['metal']))
        return mat
    base = png_of(kv.get('basetexture')) or png_by_base.get(ALIAS.get(name.lower(), name.lower()))
    solid = SOLID.get(name.lower())
    if solid and not base:
        set_in(bsdf, 'Base Color', (*solid, 1)); set_in(bsdf, 'Roughness', 0.55); set_in(bsdf, 'Specular', 0.25)
        mat['vind_kind'] = 'solid'
        print('MAT %-30s SOLID %s (texture not in the game data)' % (name, solid))
        return mat
    bump = png_of(kv.get('bumpmap') or kv.get('normalmap'))
    hairmask = png_of(kv.get('hairmask'))
    pe = png_of(kv.get('phongexponentmap'))
    st = stats.get(os.path.splitext(os.path.basename(base))[0].lower(), {}) if base else {}
    is_dye = st.get('dye', False) or name.lower() in FORCE_DYE
    alphatest = kv.get('alphatest', '0') == '1'
    translucent = kv.get('translucent', '0') == '1'
    surface = kv.get('surface', '').lower()
    phong = kv.get('phong_enable', '0') == '1'
    has_env = bool(kv.get('envmap'))
    if shader == 'eyes' and eyeball is not None:
        kind = 'eye'
    elif shader == 'refract':
        kind = 'glass'
    elif hairmask:
        kind = 'hair'
    elif surface == 'metal' and shader in ('heroes_armor', 'heroes_faceskin'):
        kind = 'metal'
    elif shader == 'heroes_faceskin' and not is_dye and surface != 'cloth':
        kind = 'skin'
    elif shader in ('heroes_armor', 'heroes_faceskin'):
        kind = 'cloth'      # newer outfits use Heroes_Faceskin with "$surface cloth" for their fabric
    else:
        kind = 'basic'
    mat['vind_shader'] = shader; mat['vind_kind'] = kind; mat['vind_base'] = base or ''
    print('MAT %-30s %-16s kind=%-5s dye=%-5s base=%s bump=%s mask=%s pe=%s' % (
        name, shader, kind, is_dye, os.path.basename(base) if base else None, os.path.basename(bump) if bump else None,
        os.path.basename(hairmask) if hairmask else None, os.path.basename(pe) if pe else None))

    color_out, tex = None, None
    if kind == 'glass':
        tint = [float(x) for x in kv.get('refracttint', '1 1 1').strip('[] ').split()[:3]]
        tint = [c ** 2.2 for c in tint]
        tt = png_of(kv.get('refracttinttexture'))
        if tt:
            tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img(tt, True); tex.location = (-900, 200)
            sep = nt.nodes.new('ShaderNodeSeparateRGB'); sep.location = (-650, 200)
            nt.links.new(tex.outputs['Color'], sep.inputs[0])
            k = map_range(nt, sep.outputs['R'], 0.35, 1.0, -450, 200)
            mul = nt.nodes.new('ShaderNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1.0; mul.location = (-250, 200)
            mul.inputs[1].default_value = (*tint, 1)
            nt.links.new(k, mul.inputs[2])
            nt.links.new(mul.outputs[0], bsdf.inputs['Base Color'])
        else:
            set_in(bsdf, 'Base Color', (*tint, 1))
        set_in(bsdf, 'Transmission', 1.0); set_in(bsdf, 'Roughness', 0.05); set_in(bsdf, 'IOR', 1.55); set_in(bsdf, 'Specular', 0.5)
        mat.use_screen_refraction = True
        mat.refraction_depth = 0.01
        if bump:
            add_normal(nt, bsdf, bump)
        return mat

    if base:
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.location = (-900, 200)
        if is_dye:
            tex.image = img(base, True)
            dg = nt.nodes.new('ShaderNodeGroup'); dg.node_tree = dye_group(); dg.location = (-450, 200)
            nt.links.new(tex.outputs['Color'], dg.inputs[0])
            cols = DYE.get(name.lower()) or DYE.get(ALIAS.get(name.lower(), '')) or DYE_DEFAULT
            for c in range(3):
                dg.inputs[1 + c].default_value = (*cols[c], 1.0)
            color_out = dg.outputs[0]
        else:
            tex.image = img(base)
            color_out = tex.outputs['Color']
    if kind == 'eye' and base and color_out is not None:
        # the game's eyeball texture is black outside the almond the lids leave open (lid shadow baked in): fine while
        # the ball stays put, as in the game.  A full sclera (textures.fill_sclera) sits beside it behind a switch:
        # node "FullSclera" 0 = the game's look, 1 = full sclera (XPS / PMX export sets 1 - their eye bones turn the ball)
        sc = png_by_base.get(os.path.splitext(os.path.basename(base))[0].lower() + '_sclera')
        if sc:
            t2 = nt.nodes.new('ShaderNodeTexImage'); t2.image = img(sc); t2.location = (-900, 420)
            sw = nt.nodes.new('ShaderNodeValue'); sw.name = 'FullSclera'; sw.label = '完整眼白 0=游戏原样 1=完整'
            sw.outputs[0].default_value = 0.0; sw.location = (-900, 620)
            mx = nt.nodes.new('ShaderNodeMixRGB'); mx.location = (-650, 300)
            nt.links.new(sw.outputs[0], mx.inputs[0]); nt.links.new(color_out, mx.inputs[1]); nt.links.new(t2.outputs['Color'], mx.inputs[2])
            color_out = mx.outputs[0]
    if kind == 'eye' and kv.get('iris'):
        ip = png_of(kv['iris'])
        if ip:
            it = nt.nodes.new('ShaderNodeTexImage'); it.image = img(ip); it.location = (-900, -150)
            it.extension = 'CLIP'
            uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = 'IrisUV'; uvn.location = (-1150, -150)
            nt.links.new(uvn.outputs[0], it.inputs[0])
            mix = nt.nodes.new('ShaderNodeMixRGB'); mix.location = (-450, 0)
            nt.links.new(it.outputs['Alpha'], mix.inputs[0]); nt.links.new(color_out, mix.inputs[1]); nt.links.new(it.outputs['Color'], mix.inputs[2])
            color_out = mix.outputs[0]
        # wet cornea over a soft sclera/iris
        set_in(bsdf, 'Roughness', 0.3); set_in(bsdf, 'Specular', 0.5)
        set_in(bsdf, 'Clearcoat', 1.0); set_in(bsdf, 'Clearcoat Roughness', 0.02)
    if color_out is not None:
        nt.links.new(color_out, bsdf.inputs['Base Color'])
    else:
        set_in(bsdf, 'Base Color', (0.8, 0.8, 0.8, 1))
    if tex is not None and (alphatest or translucent or kind == 'hair'):
        nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        mat.blend_method = 'HASHED'
        mat.shadow_method = 'HASHED'
        mat.alpha_threshold = 0.5
    ntex = add_normal(nt, bsdf, bump) if (bump and kind != 'eye') else None

    if kind == 'skin':
        set_skin_sss(bsdf)
        if color_out is not None:
            nt.links.new(color_out, bsdf.inputs['Subsurface Color'])
        set_in(bsdf, 'Roughness', 0.5)
        set_in(bsdf, 'Specular', min(0.5, 0.25 + 0.1 * fnum(kv, 'phongboost', 1.0)))
        set_in(bsdf, 'Sheen', 0.15)
        if pe:   # phong exponent map: bright = tight highlight (lips)
            pt = nt.nodes.new('ShaderNodeTexImage'); pt.image = img(pe, True); pt.location = (-900, -800)
            sep = nt.nodes.new('ShaderNodeSeparateRGB'); sep.location = (-650, -800)
            nt.links.new(pt.outputs['Color'], sep.inputs[0])
            nt.links.new(map_range(nt, sep.outputs['R'], 0.6, 0.22, -450, -800), bsdf.inputs['Roughness'])
        if ntex is not None and pe:   # normal-map alpha = specular mask on the face
            nt.links.new(map_range(nt, ntex.outputs['Alpha'], 0.18, 0.65, -450, -650), bsdf.inputs['Specular'])
    elif kind == 'hair':
        tg = nt.nodes.new('ShaderNodeTangent'); tg.direction_type = 'UV_MAP'; tg.uv_map = 'UVMap'; tg.location = (-300, -600)
        nt.links.new(tg.outputs['Tangent'], bsdf.inputs['Tangent'])
        set_in(bsdf, 'Anisotropic', 0.6); set_in(bsdf, 'Anisotropic Rotation', 0.25)   # strands run along V
        set_in(bsdf, 'Roughness', 0.42)
        mt = nt.nodes.new('ShaderNodeTexImage'); mt.image = img(hairmask, True); mt.location = (-900, -600)
        sep = nt.nodes.new('ShaderNodeSeparateRGB'); sep.location = (-650, -600)
        nt.links.new(mt.outputs['Color'], sep.inputs[0])
        nt.links.new(map_range(nt, sep.outputs['G'], 0.06, 0.32, -450, -600), bsdf.inputs['Specular'])
    elif kind == 'metal':
        set_in(bsdf, 'Metallic', 1.0)
        set_in(bsdf, 'Roughness', phong_to_rough(fnum(kv, 'phongexponent', 30)))
        set_in(bsdf, 'Specular', 0.5)
    elif kind == 'cloth':
        rough = phong_to_rough(fnum(kv, 'phongexponent', 10)) if phong else (0.38 if has_env else 0.55)
        set_in(bsdf, 'Roughness', rough)
        set_in(bsdf, 'Specular', 0.45 if has_env else 0.3)
        set_in(bsdf, 'Sheen', 0.25)
        mc = METAL_CH.get(name.lower())
        if mc and tex is not None and is_dye:
            # the dye channel painted as gold reads as metal (the game gets this look from its cubemap)
            sep = nt.nodes.new('ShaderNodeSeparateRGB'); sep.location = (-650, -150)
            nt.links.new(tex.outputs['Color'], sep.inputs[0])
            mk = map_range(nt, sep.outputs[mc], 0.0, 1.0, -450, -150)
            mk.node.inputs['From Min'].default_value = 0.04; mk.node.inputs['From Max'].default_value = 0.2
            nt.links.new(mk, bsdf.inputs['Metallic'])
            mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (-250, -250)
            mr.inputs['To Min'].default_value = rough; mr.inputs['To Max'].default_value = 0.28
            nt.links.new(mk, mr.inputs['Value'])
            nt.links.new(mr.outputs['Result'], bsdf.inputs['Roughness'])
    else:   # vertexlitgeneric etc. (lashes, brows, teeth)
        set_in(bsdf, 'Roughness', 0.5); set_in(bsdf, 'Specular', 0.3)
    if kv.get('nocull', '0') == '1' or kind in ('hair', 'basic'):
        mat.use_backface_culling = False
    return mat

# ------------------------------------------------------------------ meshes
hidden = set()
for spec, sm in models:
    hide = {h.lower() for h in spec.get('hide_materials', [])}
    only = {h.lower() for h in spec.get('only_materials', [])}
    skip_models = [s.lower() for s in spec.get('skip_models', [])]   # e.g. 'censor' = the CN-censored bodygroup copy
    tag = spec.get('tag') or os.path.splitext(os.path.basename(spec['mdl']))[0]
    c = coll(spec.get('collection', 'Model'))
    for bp in sm.bodyparts:
        for md in bp.models:
            if any(s in md.name.lower() for s in skip_models):
                print('skip bodygroup model', md.name)
                continue
            for mi, me in enumerate(md.meshes):
                if not me.tris or (only and me.material.lower() not in only):
                    continue
                verts = [conv(v[0]) for v in me.verts]
                faces = [(t[0], t[2], t[1]) for t in me.tris]          # D3D clockwise -> Blender CCW
                mesh = bpy.data.meshes.new('%s.%s' % (tag, me.material))
                mesh.from_pydata([tuple(v) for v in verts], [], faces)
                mesh.update()
                # winding sanity: faces should agree with the vertex normals
                nrm = [convd(v[1]) for v in me.verts]
                agree = sum(p.normal.dot(nrm[p.vertices[0]]) for p in mesh.polygons)
                if agree < 0:
                    mesh.flip_normals()
                uvl = mesh.uv_layers.new(name='UVMap')
                lv = [0] * len(mesh.loops)
                mesh.loops.foreach_get('vertex_index', lv)
                uvs = []
                for vi in lv:
                    u, v = me.verts[vi][2]
                    uvs += [u, 1.0 - v]
                uvl.data.foreach_set('uv', uvs)
                eyeball = None
                if me.mtype == 1 and me.mparam < len(md.eyeballs):
                    e = md.eyeballs[me.mparam]
                    hb = bind[sm.bones[e.bone].name]
                    org = hb @ Vector(e.org)
                    up = (hb.to_3x3() @ Vector(e.up)).normalized()
                    fwd = -(hb.to_3x3() @ Vector(e.forward)).normalized()
                    right = fwd.cross(up).normalized()
                    fwd = (fwd + right * (2 * e.zoffset)).normalized()
                    right = fwd.cross(up).normalized(); up = right.cross(fwd).normalized()
                    s = e.iris_scale
                    iuv = mesh.uv_layers.new(name='IrisUV')
                    vals = []
                    for vi in lv:
                        p = Vector(me.verts[vi][0]) - org
                        vals += [-s * p.dot(right) + 0.5, 1.0 - (-s * p.dot(up) + 0.5)]
                    iuv.data.foreach_set('uv', vals)
                    eyeball = e
                    print('eyeball %s org %s fwd(model) %s' % (me.material, tuple(round(x, 2) for x in org), tuple(round(x, 2) for x in fwd)))
                mesh.uv_layers.active = uvl
                mesh.use_auto_smooth = True
                mesh.normals_split_custom_set_from_vertices([tuple(n) for n in nrm])
                mesh.materials.append(build_material(me.material, sm.cdtextures, eyeball))
                ob = bpy.data.objects.new(mesh.name, mesh)
                if getattr(me, 'flexes', None) and cfg.get('flexes', True):
                    # the face's Source flexes (blink, smile, wink, chew ...) -> shape keys of the same name on every
                    # mesh that has them (face skin, lashes, teeth): one name drives the whole expression
                    ob.shape_key_add(name='Basis', from_mix=False)
                    base_co = [0.0] * (len(mesh.vertices) * 3)
                    mesh.vertices.foreach_get('co', base_co)
                    for fname, deltas in me.flexes:
                        kb = mesh.shape_keys.key_blocks.get(fname) or ob.shape_key_add(name=fname, from_mix=False)
                        co = [0.0] * len(base_co)
                        kb.data.foreach_get('co', co)        # a second flex of the same name adds on top
                        for li, dv in deltas:
                            dd = (AX @ Vector(dv)) * SCALE
                            co[3 * li] += dd.x; co[3 * li + 1] += dd.y; co[3 * li + 2] += dd.z
                        kb.data.foreach_set('co', co)
                    mesh.shape_keys.use_relative = True
                c.objects.link(ob)
                # skin weights
                groups = {}
                for vi, v in enumerate(me.verts):
                    for bi, w in v[3]:
                        if w <= 0:
                            continue
                        bn = sm.bones[bi].name
                        groups.setdefault(bn, []).append((vi, w))
                for bn, lst in groups.items():
                    vg = ob.vertex_groups.new(name=bn)
                    for vi, w in lst:
                        vg.add([vi], w, 'REPLACE')
                ob.parent = arm
                mod = ob.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
                if me.material.lower() in hide:
                    ob.hide_render = True; ob.hide_viewport = True
                    hidden.add(ob.name)

print('hidden:', sorted(hidden))

# ------------------------------------------------------------------ UVs borrowed from another model's identical mesh
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform


def uv_from(ob, src_mdl, src_material, use_material, normal_match=None, warp=False):
    """The inner-wear bodies keep hands + feet in a separate mesh ("fiona_skin_body_hand") whose texture is not in
    the game data.  The hands are vertex-for-vertex the hands of the player body (fiona.mdl), whose UVs point into
    fiona_skin_body01; the feet are a finer bare-foot mesh over the player body's simpler feet.
    Per corner: UV of the closest point on the source surface (interpolated inside that triangle, no
    extrapolation).  If a face's corners land in different UV islands of the source (a seam), the whole face
    takes the affine map of the one source triangle nearest its centre instead, so no face spans two islands."""
    sm = source_mdl.load_model(src_mdl)
    P, T, UV, N = [], [], [], []
    for bp in sm.bodyparts:
        for md in bp.models:
            for me in md.meshes:
                if me.material.lower() != src_material.lower():
                    continue
                base = len(P)
                P += [conv(v[0]) for v in me.verts]
                N += [convd(v[1]) for v in me.verts]
                UV += [Vector((v[2][0], 1.0 - v[2][1], 0.0)) for v in me.verts]
                T += [(base + t[0], base + t[1], base + t[2]) for t in me.tris]
    if not T:
        print('uv_from: no %s in %s' % (src_material, src_mdl))
        return
    # UV islands of the source: Source meshes split vertices at UV seams, so shared vertex = same island
    parent = list(range(len(P)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in T:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    island = [find(t[0]) for t in T]
    tree = BVHTree.FromPolygons(P, T)
    # normal_match (cosine): take the closest source point whose face looks the same way as the target vertex -
    # for a face borrowed from another head the lips would otherwise pick up the inside of the other mouth
    # the BVH's polygon normals follow the file's winding; orient them by the game's vertex normals
    sgn = 1.0 if sum((P[b] - P[a]).cross(P[c] - P[a]).dot(N[a] + N[b] + N[c]) for a, b, c in T) >= 0 else -1.0

    def nearest(p, vn):
        if normal_match is None or vn is None:
            return tree.find_nearest(p)
        best = None
        for co, nrm, idx, dist in tree.find_nearest_range(p, 0.02):
            if sgn * nrm.dot(vn) >= normal_match and (best is None or dist < best[3]):
                best = (co, nrm, idx, dist)
        return best or tree.find_nearest(p)
    isl_tris = {}
    for ti, k in enumerate(island):
        isl_tris.setdefault(k, []).append(ti)
    isl_tree = {}

    def island_tree(k):
        # BVH over one UV island; its polygon indices map back through isl_tris[k]
        if k not in isl_tree:
            isl_tree[k] = BVHTree.FromPolygons(P, [T[ti] for ti in isl_tris[k]])
        return isl_tree[k]
    me = ob.data
    uvl = me.uv_layers['UVMap']
    own_uv = {li: tuple(uvl.data[li].uv) for li in range(len(me.loops))}
    closest_uv = {}
    far = fallback = 0
    for poly in me.polygons:
        hits = []
        for li in poly.loop_indices:
            vtx = me.vertices[me.loops[li].vertex_index]
            p = vtx.co
            h = nearest(p, vtx.normal)
            hits.append((li, p, h))
        if any(h[2] is None for _li, _p, h in hits):
            continue
        if max(h[3] for _li, _p, h in hits) > 0.005:
            far += 1
        isls = [island[h[2]] for _li, _p, h in hits]
        if len(set(isls)) > 1:
            # the face spans a seam of the source: keep it in one island (the one nearest the face centre) and
            # look every corner up inside that island only, so the face never stretches across the texture
            fallback += 1
            k = island[tree.find_nearest(poly.center)[2]]
            it = island_tree(k)
            hits = [(li, p, (lambda r: (r[0], r[1], isl_tris[k][r[2]], r[3]))(it.find_nearest(p))) for li, p, _h in hits]
        for li, p, h in hits:
            a, b, cc = T[h[2]]
            uv = barycentric_transform(h[0], P[a], P[b], P[cc], UV[a], UV[b], UV[cc])
            closest_uv[li] = (uv.x, uv.y, h[3])
    if warp:
        warp_uvs(me, own_uv, closest_uv)
    else:
        for li, (u, v, _d) in closest_uv.items():
            uvl.data[li].uv = (u, v)
    me.materials.clear()
    me.materials.append(build_material(use_material, sm.cdtextures))
    print('uv_from %s <- %s (%s): %d faces, %d off the source surface (>5 mm), %d across a seam (face-affine)%s' % (
        ob.name, os.path.basename(src_mdl), src_material, len(me.polygons), far, fallback, ' -> smooth warp' if warp else ''))


def warp_uvs(me, own_uv, closest_uv, degree=4):
    """Borrowed face textures: the closest-point UVs follow the other head's shape corner by corner, so where the
    two faces differ (lips, eyelids) features tear.  Face UV layouts in this game come from one template, so instead
    fit one smooth polynomial map  own UV -> other face's UV  per own UV island (robust least squares over the
    closest-point pairs, outliers down-weighted) and apply it to the face's own UVs: features stay whole and land
    where the template puts them."""
    import numpy as np
    uvl = me.uv_layers['UVMap']
    # own UV islands: loops of the same vertex with the same own UV are connected
    lis = sorted(own_uv)
    parent = {li: li for li in lis}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    by_vert = {}
    for li in lis:
        key = (me.loops[li].vertex_index, round(own_uv[li][0], 5), round(own_uv[li][1], 5))
        if key in by_vert:
            parent[find(li)] = find(by_vert[key])
        else:
            by_vert[key] = li
    for poly in me.polygons:
        ls = list(poly.loop_indices)
        for li in ls[1:]:
            parent[find(li)] = find(ls[0])
    groups = {}
    for li in lis:
        groups.setdefault(find(li), []).append(li)

    def basis(u, v):
        return np.stack([u ** i * v ** j for i in range(degree + 1) for j in range(degree + 1 - i)], -1)
    n_fit = 0
    for g in groups.values():
        src = np.array([own_uv[li] for li in g])
        dst = np.array([closest_uv[li][:2] for li in g if li in closest_uv])
        if len(dst) < len(g) or len(g) < 40:
            for li in g:
                if li in closest_uv:
                    uvl.data[li].uv = closest_uv[li][:2]
            continue
        lo, hi = src.min(0), src.max(0)
        sc = np.maximum(hi - lo, 1e-6)
        A = basis(*((src - lo) / sc).T)
        ok = np.isfinite(dst).all(1) & np.isfinite(A).all(1)      # degenerate source triangles give NaN
        w = ok.astype(float)
        try:
            for _ in range(6):
                sw = np.sqrt(w)[:, None]
                coef = np.linalg.lstsq((A * sw)[ok], (np.nan_to_num(dst) * sw)[ok], rcond=None)[0]
                r = np.linalg.norm(A @ coef - np.nan_to_num(dst), axis=1)
                w = np.where(ok, 1.0 / (1.0 + (r / 0.006) ** 2), 0.0)
        except (np.linalg.LinAlgError, ValueError) as e:
            print('  warp island %d loops failed (%s) - closest-point UVs kept' % (len(g), e))
            for li in g:
                uvl.data[li].uv = closest_uv[li][:2]
            continue
        out = A @ coef
        for li, (u, v) in zip(g, out):
            uvl.data[li].uv = (float(u), float(v))
        n_fit += 1
        print('  warp island %d loops: median residual %.4f' % (len(g), float(np.median(r))))
    print('  warped %d of %d own UV islands' % (n_fit, len(groups)))


def weld_key(co):
    return (round(co[0], 5), round(co[1], 5), round(co[2], 5))


def feet_from(ob, src_mdl, src_material, use_material, z_max=12.0):
    """Swap the bare feet of a hand/foot mesh for the player body's own feet.  The inner-wear feet are finer
    (separate toes) but their texture is not in the data; the player body (fiona.mdl) has simpler feet whose
    toes are painted in fiona_skin_body01 and which meet the leg at the very same ankle ring (all ring vertices
    coincide).  Removes the target's foot islands (parts entirely below z_max) and adds the source faces below the
    ankle ring as '<object>_feet' with exact game UVs, normals and weights."""
    zc = z_max * SCALE
    me = ob.data
    # the ankle ring = foot vertices that also exist in the sibling skin object (the legs end there).  Open edges
    # alone are not enough: Source meshes are split at every UV seam, so seams look like boundaries too.
    prefix = ob.name.split('.')[0] + '.'
    other = set()
    for o in bpy.data.objects:
        if o is not ob and o.type == 'MESH' and o.name.startswith(prefix):
            other.update(weld_key(v.co) for v in o.data.vertices if v.co.z < zc)
    bm = bmesh.new(); bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    # foot islands of the target = connected parts that stay below z_max
    seen, kill, ring = set(), [], set()
    for v0 in bm.verts:
        if v0 in seen:
            continue
        comp, st = [], [v0]
        while st:
            v = st.pop()
            if v in seen:
                continue
            seen.add(v); comp.append(v)
            st += [e.other_vert(v) for e in v.link_edges]
        if max(v.co.z for v in comp) < zc:
            kill += comp
            for v in comp:
                k = weld_key(v.co)
                if k in other or any((Vector(k) - Vector(o)).length < 0.0005 for o in other if abs(o[2] - k[2]) < 0.001):
                    ring.add(k)
    if not kill:
        bm.free()
        print('feet_from: no foot part below z %.1f in %s' % (z_max, ob.name))
        return
    bmesh.ops.delete(bm, geom=kill, context='VERTS')
    bm.to_mesh(me); bm.free(); me.update()
    # source faces below the ring: flood from the lowest faces without crossing ring edges (welded positions)
    sm = source_mdl.load_model(src_mdl)
    V, T = [], []
    for bp in sm.bodyparts:
        for md in bp.models:
            for m in md.meshes:
                if m.material.lower() != src_material.lower():
                    continue
                b = len(V)
                V += m.verts
                T += [(b + t[0], b + t[1], b + t[2]) for t in m.tris]
    P = [conv(v[0]) for v in V]
    K = [weld_key(p) for p in P]
    on_ring = [k in ring or min((Vector(k) - Vector(r)).length for r in ring) < 0.0005 for k in K] if len(ring) < 400 else [k in ring for k in K]
    edge_faces = {}
    for fi, t in enumerate(T):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edge_faces.setdefault(tuple(sorted((K[a], K[b]))), []).append(fi)
    ring_edge = lambda a, b: on_ring[a] and on_ring[b]
    feet = set()
    for side in (1, -1):
        cand = [fi for fi, t in enumerate(T) if all(P[i].x * side > 0 for i in t) and max(P[i].z for i in t) < zc]
        if not cand:
            continue
        start = min(cand, key=lambda fi: min(P[i].z for i in T[fi]))
        st = [start]
        while st:
            fi = st.pop()
            if fi in feet:
                continue
            feet.add(fi)
            t = T[fi]
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if ring_edge(a, b):
                    continue
                st += [g for g in edge_faces[tuple(sorted((K[a], K[b])))] if g not in feet]
    if any(max(P[i].z for i in T[fi]) > zc for fi in feet):
        print('feet_from: flood leaked above z_max - ring not closed, skipped')
        return
    used = sorted({i for fi in feet for i in T[fi]})
    idx = {i: n for n, i in enumerate(used)}
    nm = bpy.data.meshes.new(ob.name + '_feet')
    nm.from_pydata([tuple(P[i]) for i in used], [], [(idx[T[fi][0]], idx[T[fi][2]], idx[T[fi][1]]) for fi in sorted(feet)])
    nm.update()
    nrm = [convd(V[i][1]) for i in used]
    if sum(p.normal.dot(nrm[p.vertices[0]]) for p in nm.polygons) < 0:
        nm.flip_normals()
    uvl = nm.uv_layers.new(name='UVMap')
    for lp in nm.loops:
        u, v = V[used[lp.vertex_index]][2]
        uvl.data[lp.index].uv = (u, 1.0 - v)
    nm.use_auto_smooth = True
    nm.normals_split_custom_set_from_vertices([tuple(n) for n in nrm])
    nm.materials.append(bpy.data.materials.get(use_material) or build_material(use_material, sm.cdtextures))
    fo = bpy.data.objects.new(ob.name + '_feet', nm)
    for c in ob.users_collection:
        c.objects.link(fo)
    for n, i in enumerate(used):
        for bi, w in V[i][3]:
            if w > 0:
                bn = sm.bones[bi].name
                vg = fo.vertex_groups.get(bn) or fo.vertex_groups.new(name=bn)
                vg.add([n], w, 'REPLACE')
    fo.parent = ob.parent
    mod = fo.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    print('feet_from %s: removed %d foot verts (ring %d), added %d faces from %s' % (
        ob.name, len(kill), len(ring), len(feet), os.path.basename(src_mdl)))


def replace_region(ob, src_mdl, src_material, x_range, z_range):
    """Swap the part of a skin mesh inside a box (game units) for the same part of another model's skin.
    For bodies that share the skin layout (same vertices and UVs outside the box), e.g. the one closed inner-wear
    body has a garter band modelled into its right thigh; the next body's clean thigh goes in its place.  Target
    faces entirely inside the box are deleted, source faces entirely inside are added (UVs, normals, weights from
    the game file) and the coinciding border vertices are welded."""
    x0, x1 = sorted(conv((x, 0, 0)).x for x in x_range)
    z0, z1 = z_range[0] * SCALE, z_range[1] * SCALE
    inside = lambda co: x0 <= co[0] <= x1 and z0 <= co[2] <= z1
    me = ob.data
    me.calc_normals_split()
    nrm_by_key = {}
    for lp in me.loops:
        k = weld_key(me.vertices[lp.vertex_index].co)
        nrm_by_key[k] = nrm_by_key.get(k, Vector()) + Vector(lp.normal)
    sm = source_mdl.load_model(src_mdl)
    V, T = [], []
    for bp in sm.bodyparts:
        for md in bp.models:
            if 'censor' in md.name.lower():
                continue
            for m in md.meshes:
                if m.material.lower() == src_material.lower():
                    b = len(V)
                    V += m.verts
                    T += [(b + t[0], b + t[1], b + t[2]) for t in m.tris]
    P = [conv(v[0]) for v in V]
    add = [t for t in T if all(inside(P[i]) for i in t)]
    bm = bmesh.new(); bm.from_mesh(me)
    uvl = bm.loops.layers.uv['UVMap']
    dl = bm.verts.layers.deform.verify()
    kill = [f for f in bm.faces if all(inside(v.co) for v in f.verts)]
    n_kill = len(kill)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    newv = {}
    for t in add:
        for i in t:
            if i not in newv:
                nv = bm.verts.new(P[i])
                for bi, w in V[i][3]:
                    if w > 0:
                        bn = sm.bones[bi].name
                        g = ob.vertex_groups.get(bn) or ob.vertex_groups.new(name=bn)
                        nv[dl][g.index] = w
                newv[i] = nv
                k = weld_key(P[i])
                nrm_by_key.setdefault(k, convd(V[i][1]))
    bm.verts.ensure_lookup_table()
    for t in add:
        try:
            f = bm.faces.new((newv[t[0]], newv[t[2]], newv[t[1]]))
        except ValueError:
            continue
        for lp in f.loops:
            src = next(i for i in t if newv[i] is lp.vert)
            u, v = V[src][2]
            lp[uvl].uv = (u, 1.0 - v)
    # weld the border: new vertices onto old ones at the same place
    border = [v for v in bm.verts if v.is_boundary]
    bmesh.ops.remove_doubles(bm, verts=border, dist=0.00002)
    bm.to_mesh(me); bm.free(); me.update()
    me.normals_split_custom_set_from_vertices(
        [tuple(nrm_by_key.get(weld_key(v.co), Vector(v.normal)).normalized()) for v in me.vertices])
    print('replace_region %s: -%d faces, +%d faces from %s (%s)' % (ob.name, n_kill, len(add), os.path.basename(src_mdl), src_material))


import bmesh
for spec, sm in models:
    tag = spec.get('tag') or os.path.splitext(os.path.basename(spec['mdl']))[0]
    for rr in spec.get('replace_region', []):
        ob = bpy.data.objects.get('%s.%s' % (tag, rr['material']))
        if ob:
            replace_region(ob, rr['mdl'], rr['src_material'], rr['x_range'], rr['z_range'])
    for uf in spec.get('uv_from', []):
        ob = bpy.data.objects.get('%s.%s' % (tag, uf['material']))
        if ob:
            uv_from(ob, uf['mdl'], uf['src_material'], uf.get('use_material', uf['src_material']), uf.get('normal_match'),
                    uf.get('warp', False))
    for ff in spec.get('feet_from', []):
        ob = bpy.data.objects.get('%s.%s' % (tag, ff['material']))
        if ob:
            feet_from(ob, ff['mdl'], ff['src_material'], ff.get('use_material', ff['src_material']), ff.get('z_max', 12.0))

# ------------------------------------------------------------------ skin extension (fill a hole edge upward)
import bmesh


def extend_skin(ob, z_lo, z_hi, z_to, rings=5, damp=0.85):
    """Extrude the open boundary edges whose verts lie in [z_lo, z_hi] (metres) up to z_to.
    Positions and UVs continue the slope of the strip just below the boundary; weights are copied."""
    me = ob.data
    old_normals = [tuple(v.normal) for v in me.vertices]
    try:
        me.calc_normals_split()
        acc = [Vector() for _ in me.vertices]
        for lp in me.loops:
            acc[lp.vertex_index] += Vector(lp.normal)
        old_normals = [tuple(a.normalized()) if a.length else old_normals[i] for i, a in enumerate(acc)]
    except Exception:
        pass
    n_old = len(me.vertices)
    bm = bmesh.new(); bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    uvl = bm.loops.layers.uv['UVMap']
    dl = bm.verts.layers.deform.verify()
    bedges = [e for e in bm.edges if e.is_boundary and all(z_lo <= v.co.z <= z_hi for v in e.verts)]
    bverts = {v for e in bedges for v in e.verts}
    info = {}
    for v in bverts:
        min_dz = 0.15 * SCALE
        lower = [e.other_vert(v) for e in v.link_edges if e.other_vert(v).co.z < v.co.z - min_dz]
        if not lower:     # fall back to the 2-ring below
            ring2 = {e2.other_vert(n1) for e in v.link_edges for n1 in [e.other_vert(v)] for e2 in n1.link_edges}
            lower = [x for x in ring2 if x.co.z < v.co.z - min_dz]
        if not lower:
            continue
        # the most vertical lower neighbour (steepest), i.e. the one straight below along the leg
        n = max(lower, key=lambda x: (v.co.z - x.co.z) / max(1e-6, (v.co - x.co).length))
        dz = v.co.z - n.co.z
        d3 = (v.co - n.co) / dz
        h = Vector((d3.x, d3.y))
        if h.length > 1.0:                   # clamp the horizontal slope to 45 degrees
            h = h.normalized()
        d3 = Vector((h.x * damp, h.y * damp, 1.0))
        uv_v = uv_n = None
        for f in v.link_faces:
            if n in f.verts:
                for lp in f.loops:
                    if lp.vert is v: uv_v = lp[uvl].uv.copy()
                    if lp.vert is n: uv_n = lp[uvl].uv.copy()
                break
        if uv_v is None or uv_n is None:
            for lp in v.link_loops:
                uv_v = lp[uvl].uv.copy(); break
            uv_n = uv_v
        info[v] = (d3, uv_v, (uv_v - uv_n) / dz)
    bedges = [e for e in bedges if all(v in info for v in e.verts)]
    rings_v = [{v: v for v in info}]
    for k in range(1, rings + 1):
        cur = {}
        for v, (d3, uv_v, duv) in info.items():
            dzk = (z_to - v.co.z) * k / rings
            nv = bm.verts.new(v.co + d3 * dzk)
            for gi, gw in v[dl].items():
                nv[dl][gi] = gw
            cur[v] = nv
        rings_v.append(cur)
    newf = 0
    for e in bedges:
        a, b = e.verts
        f_old = e.link_faces[0]
        lps = list(f_old.loops)
        ia = [i for i, lp in enumerate(lps) if lp.vert is a][0]
        if lps[(ia + 1) % len(lps)].vert is b:
            a, b = b, a                       # new face must run against the old face's edge direction
        for k in range(rings):
            ra, rb = rings_v[k][a], rings_v[k][b]
            na, nb = rings_v[k + 1][a], rings_v[k + 1][b]
            try:
                f = bm.faces.new((ra, rb, nb, na))
            except ValueError:
                continue
            newf += 1
            for lp in f.loops:
                src = a if lp.vert in (ra, na) else b
                d3, uv_v, duv = info[src]
                dzk = (lp.vert.co.z - src.co.z) if k or lp.vert in (na, nb) else 0.0
                lp[uvl].uv = uv_v + duv * dzk
    bm.to_mesh(me); bm.free()
    me.update()
    geo = [tuple(v.normal) for v in me.vertices]
    me.normals_split_custom_set_from_vertices(old_normals[:n_old] + geo[n_old:])
    print('extended %s: %d boundary verts, %d new faces, %d -> %d verts' % (ob.name, len(info), newf, n_old, len(me.vertices)))


def tuck_inside(body, covers, z_max, margin=0.0015, reach=0.02):
    """Push body vertices below z_max that stick out of the cover meshes back under them."""
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for c in covers:
        if c:
            ce = c.evaluated_get(dg)
            trees.append(BVHTree.FromObject(ce, dg))
    if not trees:
        return
    moved = 0
    for v in body.data.vertices:
        if v.co.z > z_max:
            continue
        best = None
        for t in trees:
            hit = t.find_nearest(v.co, reach)
            if hit[0] is not None and (best is None or hit[3] < best[3]):
                best = hit
        if best is None:
            continue
        p, n, _i, d = best
        if (v.co - p).dot(n) > -margin:          # outside (or on) the cover surface
            v.co = p - n * margin
            moved += 1
    body.data.update()
    print('tucked %d verts of %s inside %s' % (moved, body.name, [c.name for c in covers if c]))


def skin_fill_from(src, z_min, color, name='skin_fill', shrink=0.0008):
    """Re-use a hidden layer (e.g. the default inner armour) above z_min as plain skin."""
    import bmesh as _bm
    ob = src.copy(); ob.data = src.data.copy(); ob.name = src.name + '_' + name
    for c in src.users_collection:
        c.objects.link(ob)
    bm = _bm.new(); bm.from_mesh(ob.data)
    _bm.ops.delete(bm, geom=[f for f in bm.faces if max(v.co.z for v in f.verts) < z_min], context='FACES')
    for v in bm.verts:
        v.co -= v.normal * shrink
    bm.to_mesh(ob.data); bm.free()
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*color, 1)
    set_skin_sss(b)
    b.inputs['Subsurface Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = 0.5
    ob.data.materials.clear(); ob.data.materials.append(mat)
    ob.hide_render = False; ob.hide_viewport = False
    print('skin fill', ob.name, len(ob.data.polygons), 'faces')
    return ob


for spec, sm in models:
    tag = spec.get('tag') or os.path.splitext(os.path.basename(spec['mdl']))[0]
    for sf in spec.get('skin_fill', []):
        src = bpy.data.objects.get('%s.%s' % (tag, sf['material']))
        if src:
            skin_fill_from(src, sf['z_min'] * SCALE, sf['color'])
    for tk in spec.get('tuck', []):
        body = bpy.data.objects.get(tk.get('object') or '%s.%s' % (tag, tk['material']))
        covers = [bpy.data.objects.get(n) for n in tk['covers']]
        if body:
            tuck_inside(body, covers, tk['z_max'] * SCALE, tk.get('margin', 0.0015), tk.get('reach', 0.02))

for spec, sm in models:
    for ext in spec.get('extend_skin', []):
        tag = spec.get('tag') or os.path.splitext(os.path.basename(spec['mdl']))[0]
        ob = bpy.data.objects.get('%s.%s' % (tag, ext['material']))
        if ob:
            u = SCALE
            extend_skin(ob, ext['z_range'][0] * u, ext['z_range'][1] * u, ext['to'] * u, ext.get('rings', 5), ext.get('damp', 0.85))

# ------------------------------------------------------------------ the heroine's body shape
def parse_keyvalues(text):
    """Valve KeyValues text -> nested dicts (keys lower-cased)"""
    toks = re.findall(r'"([^"]*)"|([{}])', re.sub(r'//[^\n]*', '', text))
    pos = 0

    def block():
        nonlocal pos
        out = {}
        while pos < len(toks):
            s, br = toks[pos]
            if br == '}':
                pos += 1
                return out
            key = s.lower()
            pos += 1
            s2, br2 = toks[pos]
            if br2 == '{':
                pos += 1
                out[key] = block()
            else:
                out[key] = s2
                pos += 1
        return out
    return block()


def apply_figure(path):
    """The game gives every heroine a default figure (csf/bodyshape_<hero>_default.fig): per bone a scale (and
    sometimes a shift) in the bone's own axes, e.g. Bel's thighs 0.95 and calves 0.90 long with the pelvis lowered by
    3.3 units so the feet stay on the ground.  "isIndependentFromChild" 1 = the children move with the scaled bone but
    keep their own size - Blender's inherit scale NONE (checked: a child's head follows a parent scaled along its
    length, its own length stays).  The shape is posed, baked into the meshes and made the rest pose, so the .blend,
    XPS and PMX all carry it.  Source bone axes -> Blender bone axes (see R above): X -> Y, Y -> -X, Z -> Z."""
    kv = parse_keyvalues(open(path, encoding='utf-8', errors='ignore').read())
    fig = kv.get('figurebonematrix', {})
    pbones = {b.name.lower(): b for b in arm.pose.bones}
    done, skipped = [], []
    for bname, e in fig.items():
        pb = pbones.get(bname)
        if pb is None or str(e.get('isenable', '1')) != '1':
            skipped.append(bname)
            continue
        rows = [[float(x) for x in e['scalemat'][str(i)].split()] for i in range(3)]
        sx, sy, sz = rows[0][0], rows[1][1], rows[2][2]
        tx, ty, tz = rows[0][3], rows[1][3], rows[2][3]
        if any(abs(rows[i][j]) > 1e-4 for i in range(3) for j in range(3) if i != j):
            print('figure: %s has off-diagonal terms, only the scale is used' % bname)
        pb.scale = (sy, sx, sz)
        pb.location = (-ty * SCALE, tx * SCALE, tz * SCALE)
        inherit = 'NONE' if str(e.get('isindependentfromchild', '0')) == '1' else 'FULL'
        for c in pb.bone.children:
            c.inherit_scale = inherit
        done.append(bname)
    if not done:
        return
    bpy.context.view_layer.update()
    for ob in [o for o in scene.objects if o.type == 'MESH']:
        was_hidden = ob.hide_viewport
        ob.hide_viewport = False                  # hidden default parts get the shape too
        if ob.data.shape_keys:
            # Blender will not apply a modifier to a mesh with shape keys: evaluate the armature on every key
            # alone and write the deformed positions back into the keys
            keys = ob.data.shape_keys.key_blocks
            ob.show_only_shape_key = True
            deformed = []
            for i in range(len(keys)):
                ob.active_shape_key_index = i
                bpy.context.view_layer.update()
                ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
                co = [0.0] * (len(ev.data.vertices) * 3)
                ev.data.vertices.foreach_get('co', co)
                deformed.append(co)
            ob.show_only_shape_key = False
            ob.active_shape_key_index = 0
            for mod in [m for m in ob.modifiers if m.type == 'ARMATURE']:
                ob.modifiers.remove(mod)
            for kb, co in zip(keys, deformed):
                kb.data.foreach_set('co', co)
            ob.data.vertices.foreach_set('co', deformed[0])
            ob.data.update()
        else:
            for mod in [m for m in ob.modifiers if m.type == 'ARMATURE']:
                with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
        ob.hide_viewport = was_hidden
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    for b in arm.data.bones:
        b.inherit_scale = 'FULL'
    for ob in [o for o in scene.objects if o.type == 'MESH']:
        mod = ob.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    print('figure %s: %d bones shaped %s' % (os.path.basename(path), len(done), ('(not in the rig: %s)' % skipped) if skipped else ''))


if cfg.get('figure') and os.path.exists(cfg['figure']):
    apply_figure(cfg['figure'])

# ------------------------------------------------------------------ render + save
vis = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in vis:
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
ctr = (lo + hi) / 2; dims = hi - lo
print('bounds', tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi))
world = bpy.data.worlds.new('VindWorld'); world.use_nodes = True
wn = world.node_tree; wn.nodes.clear()
wout = wn.nodes.new('ShaderNodeOutputWorld')
bg_cam = wn.nodes.new('ShaderNodeBackground'); bg_cam.inputs[0].default_value = (0.045, 0.05, 0.06, 1); bg_cam.inputs[1].default_value = 1.0
if cfg.get('hdri') and os.path.exists(cfg['hdri']):
    env = wn.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(cfg['hdri'], check_existing=True)
    bg_env = wn.nodes.new('ShaderNodeBackground'); bg_env.inputs[1].default_value = cfg.get('hdri_strength', 0.8)
    wn.links.new(env.outputs['Color'], bg_env.inputs['Color'])
    lp = wn.nodes.new('ShaderNodeLightPath'); mixw = wn.nodes.new('ShaderNodeMixShader')
    wn.links.new(lp.outputs['Is Camera Ray'], mixw.inputs[0])
    wn.links.new(bg_env.outputs[0], mixw.inputs[1]); wn.links.new(bg_cam.outputs[0], mixw.inputs[2])
    wn.links.new(mixw.outputs[0], wout.inputs[0])
else:
    wn.links.new(bg_cam.outputs[0], wout.inputs[0])
scene.world = world
for nm, rot, en, col in [('key', (55, 0, 35), cfg.get('key', 3.0), (1, 0.97, 0.93)), ('fill', (65, 0, -125), cfg.get('fill', 0.9), (0.85, 0.9, 1)), ('rim', (-15, 0, 175), cfg.get('rim', 2.0), (1, 1, 1))]:
    L = bpy.data.objects.new(nm, bpy.data.lights.new(nm, 'SUN')); scene.collection.objects.link(L)
    L.data.energy = en; L.data.color = col; L.rotation_euler = tuple(math.radians(a) for a in rot)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); scene.collection.objects.link(cam)
scene.camera = cam; cam.data.lens = cfg.get('lens', 70)     # 70 mm at 2.35 x height frames the whole figure
scene.render.engine = 'BLENDER_EEVEE'
ee = scene.eevee
for attr, val in (('use_gtao', True), ('use_ssr', True), ('use_ssr_refraction', True), ('use_soft_shadows', True), ('taa_render_samples', 96), ('sss_samples', 9)):
    if hasattr(ee, attr):
        setattr(ee, attr, val)
scene.render.resolution_x, scene.render.resolution_y = cfg.get('res', [800, 1200])
scene.view_settings.view_transform = 'Filmic'
scene.view_settings.look = 'Medium Contrast'
os.makedirs(cfg['render_dir'], exist_ok=True)
tag = cfg.get('tag', 'model')
height = dims.z
views = cfg.get('views', {'front': [0, -1, 0.08], '34': [-0.7, -0.8, 0.1], 'side': [-1, 0, 0.08], 'back': [0, 1, 0.08]})
for vn, d in views.items():
    v = Vector(d).normalized()
    cam.location = ctr + v * height * cfg.get('cam_dist', 2.35)
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(cfg['render_dir'], '%s_%s.png' % (tag, vn))
    bpy.ops.render.render(write_still=True)
    print('rendered', vn)
# face close-up
head = arm.data.bones.get('ValveBiped.Bip01_Head1')
if head:
    hp = arm.matrix_world @ head.head_local + Vector((0, 0, 0.06))
    cam.data.lens = 85
    cam.location = hp + Vector((0, -0.75, 0.02))
    cam.rotation_euler = (hp - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(cfg['render_dir'], '%s_face.png' % tag)
    face_hide = [o for o in vis if any(h in o.name for h in cfg.get('face_hide', []))]   # e.g. a hat over the face
    for o in face_hide:
        o.hide_render = True
    bpy.ops.render.render(write_still=True)
    for o in face_hide:
        o.hide_render = False
    print('rendered face', '(hidden: %s)' % [o.name for o in face_hide] if face_hide else '')
cam.data.lens = 85
if cfg.get('out_blend'):
    bpy.ops.wm.save_as_mainfile(filepath=cfg['out_blend'])
    print('saved', cfg['out_blend'])
