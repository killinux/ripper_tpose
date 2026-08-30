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
import re
import time
import json

import bmesh
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup

bl_info = {
    "name": "ROE XPS Tools",
    "author": "ripper_tpose",
    "version": (1, 1, 13),
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
SOURCE_INDEX_ATTRIBUTE = 'roe_source_material_index'
SOURCE_MATERIALS_KEY = 'roe_source_materials'
SOURCE_TEXTURE_HINTS_KEY = 'roe_source_texture_hints'
SOURCE_FBX_KEY = 'roe_source_fbx'
IMPORT_BATCH_KEY = 'roe_import_batch'
ACTIVE_IMPORT_BATCH_KEY = 'roe_active_import_batch'
SLOT_OVERRIDES_KEY = 'roe_slot_overrides'
HEAD_REGION_ATTRIBUTE = 'roe_head_region_override'


# ---------------------------------------------------------------- utils

def find_tex(tex_dir, pattern):
    import glob
    # g02's original bundles spell the body color suffix "Abedo" instead of
    # "Albedo". Prefer the canonical spelling, but accept that shipped typo.
    patterns = [pattern]
    if 'Albedo' in pattern:
        patterns.append(pattern.replace('Albedo', 'Abedo'))
    # Some exports (notably k06) split the body and shared head resources into
    # sibling ``_textures`` and ``_textures_head`` folders.  Keep the selected
    # directory first, then search only companion folders under the same
    # character root; never cross into a different character export.
    roots = [tex_dir]
    normalized = os.path.normpath(tex_dir)
    if os.path.basename(normalized).lower().startswith('_textures'):
        parent = os.path.dirname(normalized)
        roots.extend(path for path in sorted(glob.glob(
            os.path.join(parent, '_textures*')))
                     if os.path.isdir(path) and path not in roots)
    # Accept either an exported texture directory or the character export root.
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

    # Some AssetStudio exports rename all facial bones to Xtra*, but preserve the
    # renderer/object name (for example pc_a05_hd_head).
    named = []
    for o in meshes:
        names = (o.name, getattr(o.data, 'name', ''))
        if any('head' in re.split(r'[_\W]+', name.lower()) for name in names):
            named.append(o)
    return max(named, key=lambda o: len(o.data.polygons)) if named else None


def canonical_object_name(name):
    return re.sub(r'\.\d{3}$', '', name)


def scene_meshes():
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    props = getattr(bpy.context.scene, 'roe', None)
    scope = getattr(props, 'apply_scope', 'LATEST')
    if scope == 'SELECTED':
        selected = [o for o in meshes if o.select_get()]
        if selected:
            return selected
    if scope == 'VISIBLE':
        return [o for o in meshes if not o.hide_get()]
    batch = bpy.context.scene.get(ACTIVE_IMPORT_BATCH_KEY, '')
    active = [o for o in meshes if o.get(IMPORT_BATCH_KEY, '') == batch]
    return active or [o for o in meshes if not o.hide_get()]


def effective_workflow(props, meshes):
    if props.workflow_mode != 'AUTO':
        return props.workflow_mode
    roe_name = re.compile(r'^pc_[a-z]\d+_(?:hd|ld)_(?:body|head|hair)',
                          re.IGNORECASE)
    return 'ROE' if any(roe_name.match(canonical_object_name(o.name))
                        for o in meshes) else 'GENERIC'


def related_armatures(meshes):
    armatures = set()
    for obj in meshes:
        if obj.parent and obj.parent.type == 'ARMATURE':
            armatures.add(obj.parent)
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                armatures.add(modifier.object)
    if not armatures:
        visible = [obj for obj in bpy.context.scene.objects
                   if obj.type == 'ARMATURE' and not obj.hide_get()]
        if len(visible) == 1:
            armatures.add(visible[0])
    return sorted(armatures, key=lambda obj: obj.name)


def current_material_names(obj):
    return [slot.material.name if slot.material else ''
            for slot in obj.material_slots]


def current_material_texture_hints(obj):
    """Keep one imported image name per FBX slot as an atlas identity hint.

    AssetStudio FBX files often connect Normal or MGAC instead of Albedo in
    Blender 3.6.  The image stem is still valuable: i03's ``body`` and ``skin``
    slots both point at body02 Normal, while its ``body01`` slot points at
    body01 Normal.  Preserving that identity avoids guessing by slot name.
    """
    hints = []
    for slot in obj.material_slots:
        material = slot.material
        candidates = []
        if material and material.use_nodes and material.node_tree:
            for node in material.node_tree.nodes:
                if node.type != 'TEX_IMAGE' or not node.image:
                    continue
                path = bpy.path.abspath(node.image.filepath or '')
                filename = os.path.basename(path) or node.image.name
                lowered = filename.lower()
                if 'albedo' in lowered or 'abedo' in lowered:
                    priority = 0
                elif 'normal' in lowered:
                    priority = 1
                elif 'mgac' in lowered or 'mga' in lowered:
                    priority = 2
                else:
                    priority = 3
                candidates.append((priority, filename.lower(), filename))
        hints.append(min(candidates)[2] if candidates else '')
    return hints


def source_texture_hints(obj):
    try:
        hints = json.loads(obj.get(SOURCE_TEXTURE_HINTS_KEY, '[]'))
    except (TypeError, ValueError):
        return None
    return hints if isinstance(hints, list) else None


def source_layout_is_cached(obj):
    stored = obj.get(SOURCE_MATERIALS_KEY, '')
    attr = obj.data.attributes.get(SOURCE_INDEX_ATTRIBUTE)
    return (isinstance(stored, str) and bool(stored)
            and attr is not None and attr.data_type == 'INT'
            and attr.domain == 'FACE'
            and len(attr.data) == len(obj.data.polygons))


def store_source_layout(obj, names=None, indices=None, fbx_path=None,
                        texture_hints=None):
    """Persist the FBX slot names and per-face assignments on the mesh."""
    names = list(names if names is not None else current_material_names(obj))
    texture_hints = list(
        texture_hints if texture_hints is not None
        else current_material_texture_hints(obj))
    texture_hints = (texture_hints + [''] * len(names))[:len(names)]
    indices = list(indices if indices is not None else
                   (poly.material_index for poly in obj.data.polygons))
    if len(indices) != len(obj.data.polygons):
        raise ValueError('Source material index count does not match %s' % obj.name)

    attr = obj.data.attributes.get(SOURCE_INDEX_ATTRIBUTE)
    if attr and (attr.data_type != 'INT' or attr.domain != 'FACE'):
        obj.data.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = obj.data.attributes.new(
            SOURCE_INDEX_ATTRIBUTE, type='INT', domain='FACE')
    attr.data.foreach_set('value', indices)
    obj[SOURCE_MATERIALS_KEY] = '\n'.join(names)
    obj[SOURCE_TEXTURE_HINTS_KEY] = json.dumps(texture_hints)
    if fbx_path:
        obj[SOURCE_FBX_KEY] = fbx_path
    obj.data.update()


def cached_source_indices(obj):
    if not source_layout_is_cached(obj):
        return None
    values = [0] * len(obj.data.polygons)
    obj.data.attributes[SOURCE_INDEX_ATTRIBUTE].data.foreach_get('value', values)
    return values


def cached_source_layout_is_suspicious(obj):
    """Reject collapsed or out-of-range caches before they overwrite face slots."""
    indices = cached_source_indices(obj)
    if indices is None:
        return True
    names = obj.get(SOURCE_MATERIALS_KEY, '').split('\n')
    if not names or any(index < 0 or index >= len(names) for index in indices):
        return True

    # ROE multi-atlas bodies use body/skin slots for different UV islands. Old
    # plugin versions could preserve their names while collapsing every face to
    # slot zero, which looks valid structurally but produces white/wrong legs.
    is_roe_body = re.match(
        r'^pc_[a-z]\d+_(?:hd|ld)_body$',
        canonical_object_name(obj.name),
        re.IGNORECASE,
    )
    return bool(is_roe_body and len(names) > 1 and len(set(indices)) <= 1)


def restore_source_layout(obj):
    indices = cached_source_indices(obj)
    if indices is None:
        return False
    for polygon, material_index in zip(obj.data.polygons, indices):
        polygon.material_index = material_index
    obj.data.update()
    return True


def generated_material_layout(obj):
    """Detect meshes whose original FBX slots were already overwritten."""
    names = current_material_names(obj)
    if not names:
        return True
    head_names = {'face', 'eye', 'lash', 'brow', 'eye_overlay'}
    if set(name.lower() for name in names).issubset(head_names):
        return True
    generated = re.compile(
        r'_\d{2}_(?:body|skin|hair|face)_mat(?:\.\d{3})?$', re.IGNORECASE)
    return all(not name or generated.search(name) for name in names)


def topology_matches(first, second):
    if (len(first.data.vertices) != len(second.data.vertices)
            or len(first.data.polygons) != len(second.data.polygons)):
        return False
    return all(tuple(a.vertices) == tuple(b.vertices)
               for a, b in zip(first.data.polygons, second.data.polygons))


def fill_missing_fbx_bind_setups(helper_node, fallback_bindings):
    """Supply bind matrices omitted by some AssetStudio FBX exports.

    Blender 3.6 collects every mesh below an armature, then assumes each one
    has an ``armature_setup`` entry created from an FBX skin cluster.  E06's
    ``wp_e_06`` is weighted to ``ball_scale`` but its exported cluster omits
    that bind setup.  The stock importer consequently raises ``KeyError:
    Root`` before it links materials or finishes vertex weights.

    Use the same world/bind matrices the importer uses when cluster matrices
    are present.  Existing setups are deliberately left untouched so ordinary
    FBX files and previously working ROE characters retain Blender's original
    import path.
    """
    if not getattr(helper_node, 'is_armature', False):
        return
    meshes = getattr(helper_node, 'meshes', None)
    if not meshes:
        return

    for mesh_node in tuple(meshes):
        setups = getattr(mesh_node, 'armature_setup', None)
        if setups is None or helper_node in setups:
            continue
        setups[helper_node] = (
            mesh_node.get_world_matrix(),
            getattr(helper_node, 'bind_matrix', None),
        )
        fallback_bindings.append((
            getattr(helper_node, 'fbx_name', '<armature>'),
            getattr(mesh_node, 'fbx_name', '<mesh>'),
        ))


def import_fbx_compat(**kwargs):
    """Run Blender's FBX importer with a scoped missing-bind compatibility fix.

    ``FbxImportHelperNode`` is an implementation detail of Blender's bundled
    3.6 importer, so feature-detect it and fall back to the untouched operator
    on Blender versions that do not expose it.  The temporary method wrapper is
    always restored, including when the import itself raises an exception.
    """
    fallback_bindings = []
    try:
        from io_scene_fbx import import_fbx as import_fbx_module
    except ImportError:
        return bpy.ops.import_scene.fbx(**kwargs), fallback_bindings

    helper_type = getattr(import_fbx_module, 'FbxImportHelperNode', None)
    original_collect = getattr(helper_type, 'collect_armature_meshes', None)
    if helper_type is None or not callable(original_collect):
        return bpy.ops.import_scene.fbx(**kwargs), fallback_bindings

    def collect_armature_meshes_compat(helper_node):
        result = original_collect(helper_node)
        fill_missing_fbx_bind_setups(helper_node, fallback_bindings)
        return result

    helper_type.collect_armature_meshes = collect_armature_meshes_compat
    try:
        result = bpy.ops.import_scene.fbx(**kwargs)
    finally:
        # Avoid leaving a global Blender importer monkey-patch behind after this
        # operator call. Blender runs operators on the main thread, so the
        # scoped replacement cannot race another UI import.
        if helper_type.collect_armature_meshes is collect_armature_meshes_compat:
            helper_type.collect_armature_meshes = original_collect

    if fallback_bindings:
        print('[fbx] supplied missing bind setups: %s' % ', '.join(
            '%s -> %s' % binding for binding in fallback_bindings))
    return result, fallback_bindings


def recover_source_layouts_from_fbx(targets, fbx_path):
    """Recover old scenes by importing the FBX only long enough to copy slots."""
    before_objects = set(bpy.data.objects)
    before_meshes = set(bpy.data.meshes)
    before_materials = set(bpy.data.materials)
    before_armatures = set(bpy.data.armatures)
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    recovered = []
    try:
        import_fbx_compat(filepath=fbx_path,
                          automatic_bone_orientation=True,
                          use_image_search=False)
        imported = [obj for obj in bpy.data.objects if obj not in before_objects]
        imported_meshes = [obj for obj in imported if obj.type == 'MESH']
        for target in targets:
            candidates = [
                source for source in imported_meshes
                if canonical_object_name(source.name)
                == canonical_object_name(target.name)
                and topology_matches(target, source)
            ]
            if len(candidates) != 1:
                continue
            source = candidates[0]
            names = [re.sub(r'\.\d{3}$', '', name)
                     for name in current_material_names(source)]
            indices = [poly.material_index for poly in source.data.polygons]
            hints = current_material_texture_hints(source)
            store_source_layout(target, names, indices, fbx_path, hints)
            restore_source_layout(target)
            recovered.append(target.name)
    finally:
        imported = [obj for obj in bpy.data.objects if obj not in before_objects]
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh not in before_meshes and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for material in list(bpy.data.materials):
            if material not in before_materials and material.users == 0:
                bpy.data.materials.remove(material)
        for armature in list(bpy.data.armatures):
            if armature not in before_armatures and armature.users == 0:
                bpy.data.armatures.remove(armature)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if active and active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = active
    return recovered


def prepare_source_layouts(meshes, fbx_path):
    """Restore cached layouts or reconstruct missing ones from the source FBX."""
    pending = []
    hint_pending = []
    captured = []
    for obj in meshes:
        if (source_layout_is_cached(obj)
                and not cached_source_layout_is_suspicious(obj)):
            restore_source_layout(obj)
            hints = source_texture_hints(obj)
            names = obj.get(SOURCE_MATERIALS_KEY, '').split('\n')
            if hints is None or len(hints) < len(names):
                hint_pending.append(obj)
        elif not generated_material_layout(obj):
            store_source_layout(obj, fbx_path=fbx_path)
            captured.append(obj.name)
        else:
            pending.append(obj)

    recovered = []
    recovery_targets = pending + [obj for obj in hint_pending
                                  if obj not in pending]
    if recovery_targets and fbx_path and os.path.isfile(fbx_path):
        recovered = recover_source_layouts_from_fbx(recovery_targets, fbx_path)
    unresolved = [obj.name for obj in pending if obj.name not in recovered]
    return captured, recovered, unresolved


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


def _upstream_image(socket, visited=None):
    if socket is None:
        return None
    visited = visited or set()
    for link in socket.links:
        node = link.from_node
        if node in visited:
            continue
        visited.add(node)
        if node.type == 'TEX_IMAGE' and node.image:
            return node.image
        for input_socket in node.inputs:
            image = _upstream_image(input_socket, visited)
            if image:
                return image
    return None


def diffuse_image(material):
    """Find the image that actually feeds Base Color, not a normal/roughness map."""
    if not material or not material.use_nodes or not material.node_tree:
        return None
    nodes = material.node_tree.nodes
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            image = _upstream_image(node.inputs.get('Base Color'))
            if image:
                return image
        elif node.type == 'GROUP' and node.node_tree \
                and node.node_tree.name.startswith('XPS Shader'):
            socket = node.inputs.get('Diffuse')
            image = _upstream_image(socket) if socket else None
            if image:
                return image
    excluded = re.compile(r'normal|rough|metal|spec|bump|mask', re.IGNORECASE)
    return next((node.image for node in nodes
                 if node.type == 'TEX_IMAGE' and node.image
                 and not excluded.search(node.name + ' ' + node.label)), None)


def material_base_color(material):
    if material and material.use_nodes and material.node_tree:
        principled = next((node for node in material.node_tree.nodes
                           if node.type == 'BSDF_PRINCIPLED'), None)
        if principled:
            return tuple(principled.inputs['Base Color'].default_value)
    return tuple(material.diffuse_color) if material else (0.8, 0.8, 0.8, 1.0)


def material_uses_alpha(material):
    if not material:
        return False
    if material.blend_method != 'OPAQUE' or material.diffuse_color[3] < 0.999:
        return True
    if material.use_nodes and material.node_tree:
        principled = next((node for node in material.node_tree.nodes
                           if node.type == 'BSDF_PRINCIPLED'), None)
        return bool(principled and principled.inputs['Alpha'].is_linked)
    return False


def material_is_transparent_only(material):
    if not material or not material.use_nodes or not material.node_tree:
        return False
    nodes = material.node_tree.nodes
    return (
        any(node.type == 'BSDF_TRANSPARENT' for node in nodes)
        and not any(node.type == 'BSDF_PRINCIPLED' for node in nodes)
    )


def is_g09_wing_slot(obj, slot_index, source_name=None):
    """Return True only for the observed G09 HD/LD wing material slots."""
    object_name = canonical_object_name(obj.name).lower()
    if not re.fullmatch(r'pc_g09_(?:hd|ld)_body', object_name):
        return False
    if source_name is None:
        names = source_material_names(obj)
        source_name = names[slot_index] if slot_index < len(names) else ''
    source_name = re.sub(r'\.\d{3}$', '', source_name.lower())
    return bool(re.fullmatch(r'pc_g09_(?:hd|ld)_wings?\d*', source_name))


def is_wing_slot(obj, slot_index, source_name=None):
    """Identify wing slots without opting other alpha materials into wing rules."""
    if source_name is None:
        names = source_material_names(obj)
        source_name = names[slot_index] if slot_index < len(names) else ''

    def has_wing_token(name):
        return any(re.fullmatch(r'wings?\d*', token)
                   for token in re.split(r'[_\W]+', name.lower()))

    return has_wing_token(source_name) or has_wing_token(
        canonical_object_name(obj.name))


def roe_xps_render_group(obj, slot_index, material):
    """Keep normal ROE body slots opaque, except G09's alpha wing atlases.

    The G09 body mesh contains both the opaque body/skin and two wing slots.
    Treating every slot on a ROE body as RG5 discards the wing Albedo alpha and
    turns the feather cards into solid polygons. Source material names survive
    material preparation in ``roe_source_materials``, so they are the narrowest
    reliable way to opt only G09 wing slots into RG7.  The character guard is
    intentional: older characters keep their historical render-group behavior.
    """
    if 'hair' in canonical_object_name(obj.name).lower():
        return '7'
    if not material_uses_alpha(material):
        return '5'

    return '7' if is_g09_wing_slot(obj, slot_index) else '5'


def albedo_mat(name, tex_path, desat=False, hashed=False,
               saturation=SKIN_DESAT):
    m, nt, b = _new_mat(name)
    if not tex_path:
        return m
    t = _tex_node(nt, tex_path)
    if desat:
        h = nt.nodes.new('ShaderNodeHueSaturation'); h.location = (-150, 200)
        h.inputs['Saturation'].default_value = saturation
        nt.links.new(t.outputs['Color'], h.inputs['Color'])
        nt.links.new(h.outputs['Color'], b.inputs['Base Color'])
    else:
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
    # 丝袜等半透明衣物 CLIP 会被裁没，body 用 HASHED
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


def source_role_texture_patterns(obj, role):
    """Return exact Albedo patterns implied by the original FBX slot names."""
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
        matches = False
        if role == 'face':
            matches = 'face' in tokens and not bool(tokens & feature_tokens)
        elif role == 'eye':
            matches = bool(tokens & {'eye', 'eyes', 'iris', 'eyeball'}) \
                and not bool(tokens & {'brow', 'eyebrow', 'tear', 'tears', 'lash'})
        elif role == 'brow':
            matches = bool(tokens & {'brow', 'eyebrow'})
        if not clean or not matches:
            continue
        patterns.extend((clean + '_rgbx_Albedo*.png',
                         clean + '_Albedo*.png',
                         clean + '*Albedo*.png'))
    return tuple(patterns)


def slot_overrides(obj):
    try:
        data = json.loads(obj.get(SLOT_OVERRIDES_KEY, '{}'))
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def apply_mesh_materials(obj, tex_dir, face_tex, hair_tex,
                         skin_saturation=SKIN_DESAT, slot_filter=None):
    """Replace materials without destroying the FBX body/skin/face slot split."""
    me = obj.data
    material_indices = [poly.material_index for poly in me.polygons]
    source_names = source_material_names(obj)
    source_hints = source_texture_hints(obj) or []
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
        if not stem:
            return None
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
    overrides = slot_overrides(obj)
    for index, source_name in enumerate(source_names):
        if slot_filter is not None and not slot_filter(
                obj, index, source_name):
            materials.append(None)
            continue
        tokens = re.split(r'[_\W]+', source_name.lower())
        is_skin = any(token == 'skin' or re.fullmatch(r'skin\d+', token)
                      for token in tokens)
        is_tear = any(token in {'tear', 'tears'} for token in tokens)
        override = overrides.get(str(index), {})
        override_role = override.get('role', 'AUTO')
        override_tex = bpy.path.abspath(override.get('texture', ''))
        material_name = '%s_%02d_%s_mat'
        if override_role == 'TRANSPARENT' \
                or (override_role == 'AUTO' and is_tear):
            materials.append(transparent_mat(
                material_name % (obj.name, index, 'eye_overlay')))
            continue
        if override_role == 'HAIR' or (override_role == 'AUTO' and is_hair):
            role, tex, desat, hashed = 'hair', hair_tex, False, False
        elif override_role == 'FACE' or (override_role == 'AUTO' and 'face' in tokens):
            # Some outfits keep the neck seam in a dedicated face-texture slot.
            role, tex, desat, hashed = 'face', face_tex, True, True
        elif override_role == 'SKIN' or (override_role == 'AUTO' and is_skin):
            role, tex, desat, hashed = (
                'skin', slot_albedo(source_name, index), True, True)
        else:
            role = 'body'
            tex = slot_albedo(source_name, index)
            desat = 'body1' in obj.name.lower()
            hashed = True
        if is_g09_wing_slot(obj, index, source_name):
            # G09's wing atlases use mostly binary cutout alpha.  Alpha Hashed
            # produces the noisy black feather-card pattern seen in Blender 3.6
            # Material Preview, especially where the wing layers overlap.
            # CLIP is deterministic in the viewport; XPS export still uses RG7.
            hashed = False
        if override_tex and os.path.isfile(override_tex):
            tex = override_tex
        if not tex:
            missing.append('%s[%d:%s]' % (obj.name, index, source_name or role))
        materials.append(albedo_mat(
            material_name % (obj.name, index, role),
            tex,
            desat=desat,
            hashed=hashed,
            saturation=skin_saturation,
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


def eye_mat(name, iris_path, center=IRIS_CENTER,
            radius_inner=IRIS_R_IN, radius_outer=IRIS_R_OUT):
    """程序化眼白 + 中心圆盘虹膜（虹膜贴图外圈是棕色，整张贴会没有眼白）。"""
    m, nt, b = _new_mat(name)
    b.inputs['Roughness'].default_value = 0.15
    t = _tex_node(nt, iris_path)
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.location = (-900, 0)
    uv.uv_map = 'UV0'
    dist = nt.nodes.new('ShaderNodeVectorMath'); dist.location = (-700, 0)
    dist.operation = 'DISTANCE'
    dist.inputs[1].default_value = (center[0], center[1], 0.0)
    nt.links.new(uv.outputs['UV'], dist.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (-500, 0)
    mr.interpolation_type = 'SMOOTHSTEP'
    mr.inputs['From Min'].default_value = radius_inner
    mr.inputs['From Max'].default_value = radius_outer
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

def classify_head(o, source_material_names=None, source_material_indices=None):
    """连通块 + 骨骼权重分类。返回 {poly_index: slot}，
    slot: 0脸 1眼球 2睫毛 3眉毛 4罩层。原理见 docs/face-eye-materials.md。"""
    me = o.data
    if source_material_names is None:
        source_material_names = [
            slot.material.name if slot.material else '' for slot in o.material_slots]
    if source_material_indices is None:
        source_material_indices = [poly.material_index for poly in me.polygons]

    # Some bundles ship a partial head dump: f05 keeps only ``pc_f_nk_eyebrow``
    # and ``pc_f_nk_tears`` while the face and eye slots are gone, and every
    # face polygon carries one of the two surviving indices.  Trusting that list
    # sends the whole face into brow/lash/overlay and leaves slot 0 with zero
    # polygons — a head with no face.  An incomplete list is worse than none, so
    # drop it and let the geometry/bone fallbacks classify the head.
    _slot_tokens = [set(re.split(r'[_\W]+', name.lower()))
                    for name in source_material_names]
    _feature_tokens = {'eye', 'eyes', 'iris', 'eyeball', 'brow', 'eyebrow',
                       'eyelid', 'lash', 'tear', 'tears'}
    _has_face_slot = any('face' in tokens and not (tokens & _feature_tokens)
                         for tokens in _slot_tokens)
    _has_feature_slot = any(tokens & _feature_tokens for tokens in _slot_tokens)
    if _has_feature_slot and not _has_face_slot:
        source_material_names = []
        source_material_indices = []

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
        # Some characters (notably a08) keep Eyeball-named vertex groups, but
        # their eyeball vertices are not weighted to those groups.  The old
        # logic saw the semantic groups and disabled the geometry fallback,
        # classifying all 864 eye polygons as face.  A source material explicitly
        # named eye/eyes/iris is strong enough to re-enable that fallback for
        # the matching connected components without changing a06/a07 behavior.
        geometric_eye = (
            (not has_semantic_groups or source_is_eye(c))
            and uv0 and 250 <= c['polys'] <= 800
            and u_span > 0.85 and v_span > 0.85
        )
        # B01's two 432-polygon eyeballs are deliberately blended about
        # 80/20 between Eyeball and Head.  Requiring 90% Eyeball weight leaves
        # the generated eye material unused.  A majority Eyeball weight is
        # safe here only when the component also has the characteristic
        # compact eye topology and full 0-1 iris UV map.
        weighted_geometric_eye = (
            w['eyeball'] > 0.65 * tot
            and uv0 and 250 <= c['polys'] <= 800
            and u_span > 0.85 and v_span > 0.85
        )
        if w['eyeball'] > 0.9 * tot or weighted_geometric_eye \
                or geometric_eye:
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
            # b02 stores many tiny cornea/tear cards in pc_b_nk_tears.  Their
            # Eyelid weights vary from card to card, so a weight-only test made
            # part of the layer opaque face and part dark lash ("one-eye
            # glasses").  The original material name is unambiguous.
            cls[r] = 4
        elif source_is_face(c):
            # F10's face atlas contains a large, narrow UV island influenced by
            # eyelid bones.  The historical geometry fallback interpreted that
            # island as an eye overlay and made most of the face transparent.
            # An explicit source ``..._face`` slot is stronger evidence and is
            # safe to honor before the legacy bone/UV fallbacks below.
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
            # Some ROE heads (b02) pack brows plus upper/lower lashes into one
            # "eyebrow" source material and leave particular cards without a
            # decisive Eyebrow/Eyelid weight.  Use height only as a fallback
            # after the historical bone rules, so a06/a07/a08 keep their
            # established classifications.
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
                and source_index in explicit_face_slots \
                and slot != 1:
            # F10 shares vertices across source material boundaries, so one
            # connected component can contain both face and tear polygons.
            # Preserve the explicit per-face FBX assignment before applying
            # component-level geometry fallbacks. Heads with only one vague
            # source slot still use the historical classifier unchanged.
            #
            # Eyeballs are exempt: g05 ships no separate ``pc_g_nk_eyes`` slot,
            # so its eyeballs live inside the face material and this override
            # dragged them back out of the eye slot, leaving blank white eyes.
            # A component that is ~100% Eyeball-weighted with a full 0-1 iris UV
            # is stronger evidence than a shared source material index.
            slot = 0
        classifications[polygon.index] = slot
    return classifications


def apply_head_region_overrides(head, classifications):
    attr = head.data.attributes.get(HEAD_REGION_ATTRIBUTE)
    if not attr or attr.data_type != 'INT' or attr.domain != 'FACE' \
            or len(attr.data) != len(head.data.polygons):
        return classifications
    values = [0] * len(attr.data)
    attr.data.foreach_get('value', values)
    for polygon_index, value in enumerate(values):
        if 1 <= value <= 5:
            classifications[polygon_index] = value - 1
    return classifications


# ------------------------------------------------------------ eye texture bake

def bake_eye_texture(head, iris_path, out_path, eye_slot=1):
    """把"程序化眼白+虹膜圆盘"烘成一张 PNG（XPS 不支持节点，必须烘焙）。
    参数优先从 head 槽 1 的眼球材质节点里读（保持和视口一致）。"""
    import numpy as np

    center, r_in, r_out, sclera = IRIS_CENTER, IRIS_R_IN, IRIS_R_OUT, SCLERA
    if len(head.material_slots) > eye_slot \
            and head.material_slots[eye_slot].material:
        nt = head.material_slots[eye_slot].material.node_tree
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
    workflow_mode: EnumProperty(
        name="工作流",
        items=(
            ('AUTO', "自动识别", "只有识别为 ROE 的模型才执行专用修复"),
            ('GENERIC', "通用模型", "保留任意模型的现有材质并转换 XPS"),
            ('ROE', "ROE 增强", "修复 ROE 的脸、眼睛、睫毛和多图集材质"),
        ),
        default='AUTO',
    )
    apply_scope: EnumProperty(
        name="处理范围",
        items=(
            ('LATEST', "最新导入", "处理本插件最近一次导入的模型"),
            ('SELECTED', "所选网格", "处理从任意格式导入后选中的网格"),
            ('VISIBLE', "所有可见", "处理场景中全部可见网格"),
        ),
        default='LATEST',
    )
    replace_previous: BoolProperty(
        name="重复导入时隐藏旧网格",
        description="再次导入同名模型时隐藏旧网格，避免重叠造成材质异常",
        default=True,
    )
    fbx_path: StringProperty(
        name="FBX", subtype='FILE_PATH',
        description="可选 FBX 源文件；也用于恢复旧场景丢失的材质分区")
    tex_dir: StringProperty(
        name="ROE 贴图目录", subtype='DIR_PATH',
        description="ROE 增强模式使用的 Albedo 贴图目录")
    xps_out: StringProperty(
        name="XPS 输出", subtype='FILE_PATH',
        description="输出 .mesh 路径；通用模型建议明确指定")
    show_advanced: BoolProperty(name="高级材质调整", default=False)
    skin_saturation: FloatProperty(
        name="皮肤饱和度", default=SKIN_DESAT, min=0.0, max=1.5)
    lash_alpha_gain: FloatProperty(
        name="睫毛透明度", default=LASH_ALPHA_GAIN, min=0.0, max=4.0)
    lash_darken: FloatProperty(
        name="睫毛亮度", default=LASH_DARKEN, min=0.0, max=2.0)
    iris_center_u: FloatProperty(
        name="虹膜中心 U", default=IRIS_CENTER[0], min=0.0, max=1.0)
    iris_center_v: FloatProperty(
        name="虹膜中心 V", default=IRIS_CENTER[1], min=0.0, max=1.0)
    iris_radius_inner: FloatProperty(
        name="虹膜内半径", default=IRIS_R_IN, min=0.01, max=0.5)
    iris_radius_outer: FloatProperty(
        name="虹膜外半径", default=IRIS_R_OUT, min=0.01, max=0.5)
    slot_role: EnumProperty(
        name="当前槽用途",
        items=(
            ('AUTO', "自动", "根据原始材质名称判断"),
            ('BODY', "身体/衣服", "按身体或衣服处理"),
            ('SKIN', "皮肤", "按皮肤处理并允许降低饱和度"),
            ('FACE', "脸", "使用脸部共享贴图"),
            ('HAIR', "头发", "使用带透明通道的头发材质"),
            ('TRANSPARENT', "透明罩/隐藏", "使用纯透明材质并在 ROE XPS 导出时跳过"),
        ),
        default='AUTO',
    )
    slot_texture: StringProperty(
        name="当前槽贴图覆盖", subtype='FILE_PATH',
        description="可为活动网格的当前材质槽指定 Base Color 贴图")
    head_region: EnumProperty(
        name="所选头部面指定为",
        items=(
            ('AUTO', "自动", "清除人工分类，恢复自动判断"),
            ('FACE', "脸", "指定为脸部材质"),
            ('EYE', "眼球", "指定为眼球材质"),
            ('LASH', "睫毛", "指定为睫毛材质"),
            ('BROW', "眉毛", "指定为眉毛材质"),
            ('OVERLAY', "透明罩", "指定为不导出的透明眼部罩层"),
        ),
        default='AUTO',
    )
    diagnostic_report: StringProperty(name="最近检查", default="尚未检查")


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
        _, fallback_bindings = import_fbx_compat(
            filepath=fbx,
            automatic_bone_orientation=True,
            use_image_search=p.workflow_mode == 'GENERIC')
        new = [o for o in bpy.context.scene.objects if o not in before]
        meshes = [o for o in new if o.type == 'MESH']
        batch = str(time.time_ns())
        for obj in new:
            obj[IMPORT_BATCH_KEY] = batch
        for obj in meshes:
            store_source_layout(obj, fbx_path=fbx)
        context.scene[ACTIVE_IMPORT_BATCH_KEY] = batch

        hidden = []
        if p.replace_previous:
            new_names = {canonical_object_name(obj.name) for obj in meshes}
            for obj in before:
                if (obj.type == 'MESH'
                        and canonical_object_name(obj.name) in new_names
                        and not obj.hide_get()):
                    obj.hide_set(True)
                    obj.hide_render = True
                    hidden.append(obj.name)

        # 旧版导出(scale-factor 1)是厘米级，自动放大
        scaled = False
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
                scaled = True
        for area in (context.screen.areas if context.screen else []):
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
        detail = "，已自动 x100" if scaled else ""
        if fallback_bindings:
            detail += "，兼容修复 %d 个缺失骨架绑定" % len(fallback_bindings)
        if hidden:
            detail += "，隐藏 %d 个同名旧网格" % len(hidden)
        self.report({'INFO'}, "导入完成: %d 个物体%s" % (len(new), detail))
        return {'FINISHED'}


class ROE_OT_apply_materials(Operator):
    bl_idname = "roe.apply_materials"
    bl_label = "2. 检查并准备材质"
    bl_description = "通用模型保留原材质；ROE 模型额外修复脸、眼睛和多图集材质"
    bl_options = {'REGISTER', 'UNDO'}
    repair_scope: EnumProperty(
        name="修复范围",
        items=(
            ('ALL', "全部", "保持旧版的一键材质准备行为"),
            ('FACE', "脸部", "只修复脸、眼球、睫毛、眉毛和眼部透明层"),
            ('BODY', "身体", "只修复非头部、非翅膀的身体/衣装/头发材质槽"),
            ('WING', "翅膀", "只修复名称明确为 wing/wings 的材质槽"),
        ),
        default='ALL',
        options={'HIDDEN'},
    )

    def execute(self, context):
        p = context.scene.roe
        repair_scope = self.repair_scope
        meshes = [o for o in scene_meshes() if not re.match(r'^\d+_', o.name)]
        if not meshes:
            self.report({'ERROR'}, "处理范围内没有网格")
            return {'CANCELLED'}

        workflow = effective_workflow(p, meshes)
        if workflow == 'GENERIC':
            if repair_scope != 'ALL':
                self.report({'ERROR'}, "分区材质修复只适用于 ROE 增强工作流")
                return {'CANCELLED'}
            created = []
            for obj in meshes:
                if not obj.material_slots:
                    material = bpy.data.materials.new(obj.name + '_material')
                    material.use_nodes = True
                    material.diffuse_color = (0.8, 0.8, 0.8, 1.0)
                    obj.data.materials.append(material)
                    for polygon in obj.data.polygons:
                        polygon.material_index = 0
                    created.append(obj.name)
                if not source_layout_is_cached(obj):
                    store_source_layout(
                        obj,
                        fbx_path=bpy.path.abspath(p.fbx_path)
                        if p.fbx_path else None,
                    )
            p.diagnostic_report = (
                "通用模式: %d 个网格，%d 个关联骨架，%d 个默认材质"
                % (len(meshes), len(related_armatures(meshes)), len(created)))
            self.report({'INFO'}, p.diagnostic_report)
            return {'FINISHED'}

        tex_dir = bpy.path.abspath(p.tex_dir)
        if not os.path.isdir(tex_dir):
            self.report({'ERROR'}, "ROE 贴图目录无效: %s" % tex_dir)
            return {'CANCELLED'}

        fbx = bpy.path.abspath(p.fbx_path) if p.fbx_path else ''
        if not os.path.isfile(fbx):
            fbx = next((bpy.path.abspath(obj.get(SOURCE_FBX_KEY, ''))
                        for obj in meshes
                        if os.path.isfile(bpy.path.abspath(
                            obj.get(SOURCE_FBX_KEY, '')))), '')
        head = find_head(meshes)
        if repair_scope == 'FACE' and head is None:
            self.report({'ERROR'}, "没有找到 head 网格")
            return {'CANCELLED'}
        if repair_scope == 'ALL':
            layout_targets = meshes
        elif repair_scope == 'FACE':
            layout_targets = [head]
        else:
            layout_targets = [obj for obj in meshes if obj is not head]
        captured, recovered, unresolved = prepare_source_layouts(
            layout_targets, fbx)
        head = find_head(meshes)

        # 体型字母(pc_g11_... -> g)：贴图目录里有多体型/LD 共享贴图，必须精确匹配
        bt = None
        character_prefix = None
        for o in meshes:
            mm = re.match(r'pc_([a-z])\d', o.name)
            if mm:
                bt = mm.group(1)
            cm = re.match(r'(pc_[a-z]\d+_(?:hd|ld))', o.name.lower())
            if cm:
                character_prefix = cm.group(1)
            if bt and character_prefix:
                break
        if not (bt and character_prefix):
            path_match = re.search(
                r'(pc_([a-z])\d+_(?:hd|ld))', fbx.lower())
            if path_match:
                character_prefix = character_prefix or path_match.group(1)
                bt = bt or path_match.group(2)

        def pick(*patterns):
            for pat in patterns:
                if pat:
                    hit = find_tex(tex_dir, pat)
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
        if baked_face_strokes:
            print('[mat] i/j-family eyebrows/eyeliner are baked into face Albedo; '
                  'untextured stroke geometry will stay transparent')

        no_tex = []
        processed_slots = 0
        if repair_scope in {'ALL', 'BODY', 'WING'}:
            for o in meshes:
                if o is head:
                    continue
                slot_filter = None
                if repair_scope == 'BODY':
                    slot_filter = (
                        lambda obj, index, name: not is_wing_slot(
                            obj, index, name))
                elif repair_scope == 'WING':
                    slot_filter = is_wing_slot

                source_names = source_material_names(o)
                slot_count = max(
                    len(source_names),
                    max((poly.material_index for poly in o.data.polygons),
                        default=0) + 1,
                    1,
                )
                padded_names = source_names + [''] * (
                    slot_count - len(source_names))
                selected_slots = sum(
                    1 for index, source_name in enumerate(padded_names)
                    if slot_filter is None
                    or slot_filter(o, index, source_name))
                if not selected_slots:
                    continue
                processed_slots += selected_slots
                no_tex.extend(apply_mesh_materials(
                    o, tex_dir, face_tex, hair_tex,
                    skin_saturation=p.skin_saturation,
                    slot_filter=slot_filter))

        if repair_scope in {'BODY', 'WING'}:
            label = "身体/衣装" if repair_scope == 'BODY' else "翅膀"
            p.diagnostic_report = (
                "%s修复: %d 个材质槽，恢复 %d，未恢复 %d，缺贴图 %d"
                % (label, processed_slots, len(recovered), len(unresolved),
                   len(no_tex)))
            if repair_scope == 'WING' and not processed_slots:
                self.report({'INFO'}, "没有识别到 wing/wings 翅膀材质槽，未修改模型")
            elif no_tex:
                self.report({'WARNING'},
                            "%s修复完成，但这些槽没找到贴图: %s"
                            % (label, ', '.join(no_tex)))
            else:
                self.report({'INFO'}, "%s修复完成: %d 个材质槽"
                            % (label, processed_slots))
            return {'FINISHED'}

        if head is None:
            self.report({'WARNING'}, "没找到 head 网格(名称或 Eyeball 顶点组均未匹配)，只处理了 body/hair")
            return {'FINISHED'}
        if not (face_tex and iris_tex and (brow_tex or baked_face_strokes)):
            missing = [name for name, path in (('face', face_tex), ('eye_iris', iris_tex),
                                               ('eyebrow', brow_tex))
                       if not path and not (name == 'eyebrow'
                                            and baked_face_strokes)]
            self.report({'ERROR'}, "缺少贴图: %s；可选择 _textures 或角色导出根目录" % ', '.join(missing))
            return {'CANCELLED'}

        me = head.data
        source_head_names = source_material_names(head)
        source_head_indices = cached_source_indices(head) or [
            q.material_index for q in me.polygons]
        me.materials.clear()
        me.materials.append(albedo_mat(
            'face', face_tex, desat=True, saturation=p.skin_saturation))
        me.materials.append(eye_mat(
            'eye', iris_tex,
            center=(p.iris_center_u, p.iris_center_v),
            radius_inner=p.iris_radius_inner,
            radius_outer=p.iris_radius_outer))
        if brow_tex:
            me.materials.append(stroke_mat(
                'lash', brow_tex, p.lash_alpha_gain, p.lash_darken))
            me.materials.append(stroke_mat('brow', brow_tex))
        else:
            me.materials.append(transparent_mat('lash'))
            me.materials.append(transparent_mat('brow'))
        me.materials.append(transparent_mat('eye_overlay'))
        cls = apply_head_region_overrides(
            head, classify_head(head, source_head_names, source_head_indices))
        counts = {}
        for q in me.polygons:
            q.material_index = cls[q.index]
            counts[q.material_index] = counts.get(q.material_index, 0) + 1
        me.update()
        print('[mat] head=%s slots=%s' % (head.name, counts))
        p.diagnostic_report = (
            "%s: %d 网格，恢复 %d，未恢复 %d，缺贴图 %d"
            % ("脸部修复" if repair_scope == 'FACE' else "ROE",
               len(meshes), len(recovered), len(unresolved), len(no_tex)))
        if no_tex:
            self.report({'WARNING'},
                        "完成，但这些网格没找到贴图(导出会是 missing.png): %s" % ', '.join(no_tex))
        else:
            detail = "；自动恢复 %d 个旧网格" % len(recovered) if recovered else ""
            message = ("脸部修复完成(head 已分 5 槽)" if repair_scope == 'FACE'
                       else "材质完成(head 已分 5 槽)")
            self.report({'INFO'}, "%s%s" % (message, detail))
        return {'FINISHED'}


class ROE_OT_repair_eyes(Operator):
    bl_idname = "roe.repair_eyes"
    bl_label = "修复眼睛"
    bl_description = (
        "按骨骼权重、几何和原始眼睛材质名重新识别眼球面；"
        "适用于 a08 等存在 Eyeball 组但眼球权重缺失的模型"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.roe
        meshes = [obj for obj in scene_meshes()
                  if not re.match(r'^\d+_', obj.name)]
        if not meshes:
            self.report({'ERROR'}, "处理范围内没有网格")
            return {'CANCELLED'}
        if effective_workflow(p, meshes) != 'ROE':
            self.report({'ERROR'}, "修复眼睛只适用于 ROE 增强工作流")
            return {'CANCELLED'}

        tex_dir = bpy.path.abspath(p.tex_dir)
        if not os.path.isdir(tex_dir):
            self.report({'ERROR'}, "ROE 贴图目录无效: %s" % tex_dir)
            return {'CANCELLED'}

        head = find_head(meshes)
        if head is None:
            self.report({'ERROR'}, "没有找到 head 网格")
            return {'CANCELLED'}

        recovered_source = False
        if not source_layout_is_cached(head):
            fbx = bpy.path.abspath(p.fbx_path) if p.fbx_path else ''
            if not os.path.isfile(fbx):
                fbx = next((bpy.path.abspath(obj.get(SOURCE_FBX_KEY, ''))
                            for obj in meshes
                            if os.path.isfile(bpy.path.abspath(
                                obj.get(SOURCE_FBX_KEY, '')))), '')
            prepare_source_layouts(meshes, fbx)
            meshes = [obj for obj in scene_meshes()
                      if not re.match(r'^\d+_', obj.name)]
            head = find_head(meshes)
            recovered_source = bool(
                head is not None and source_layout_is_cached(head))
            if head is None:
                self.report({'ERROR'}, "恢复原始分区后仍未找到 head 网格")
                return {'CANCELLED'}

        # A raw FBX does not yet have the generated face/eye/lash/brow slots.
        # Run the normal preparation once, then limit subsequent repairs to the
        # eye material and polygons only.
        if recovered_source or not generated_material_layout(head) \
                or len(head.material_slots) < 5:
            result = bpy.ops.roe.apply_materials()
            if 'FINISHED' not in result:
                self.report({'ERROR'}, "请先完成“检查并准备材质”")
                return {'CANCELLED'}
            meshes = [obj for obj in scene_meshes()
                      if not re.match(r'^\d+_', obj.name)]
            head = find_head(meshes)
            if head is None or len(head.material_slots) < 5:
                self.report({'ERROR'}, "头部没有生成完整的 5 个材质槽")
                return {'CANCELLED'}

        character_prefix = None
        body_type = None
        for obj in meshes:
            name = canonical_object_name(obj.name).lower()
            prefix_match = re.match(r'(pc_([a-z])\d+_(?:hd|ld))', name)
            if prefix_match:
                character_prefix = prefix_match.group(1)
                body_type = prefix_match.group(2)
                if 'head' in re.split(r'[_\W]+', name):
                    break
        if not (body_type and character_prefix):
            identity_source = bpy.path.abspath(p.fbx_path) if p.fbx_path else ''
            if not identity_source:
                identity_source = bpy.path.abspath(
                    head.get(SOURCE_FBX_KEY, ''))
            path_match = re.search(
                r'(pc_([a-z])\d+_(?:hd|ld))', identity_source.lower())
            if path_match:
                character_prefix = character_prefix or path_match.group(1)
                body_type = body_type or path_match.group(2)

        iris_tex = None
        patterns = source_role_texture_patterns(head, 'eye') + (
            character_prefix + '_eye_iris*Albedo*.png'
            if character_prefix else None,
            'pc_%s_nk_eye_iris*Albedo*.png' % body_type
            if body_type else None,
            '*eye_iris*Albedo*.png',
            'pc_%s_nk_eyes*Albedo*.png' % body_type
            if body_type else None,
            'pc_%s_ld_eyes*Albedo*.png' % body_type
            if body_type else None,
        )
        for pattern in patterns:
            if pattern:
                iris_tex = find_tex(tex_dir, pattern)
                if iris_tex:
                    break
        if not iris_tex:
            self.report({'ERROR'}, "没有找到 eye_iris Albedo 贴图")
            return {'CANCELLED'}

        source_names = source_material_names(head)
        source_indices = cached_source_indices(head) or [
            polygon.material_index for polygon in head.data.polygons]
        classifications = apply_head_region_overrides(
            head, classify_head(head, source_names, source_indices))
        eye_polygons = {
            polygon_index for polygon_index, slot in classifications.items()
            if slot == 1
        }
        if not eye_polygons:
            self.report({'ERROR'}, "没有识别到眼球面；可在高级设置中手工标记")
            return {'CANCELLED'}

        head.data.materials[1] = eye_mat(
            'eye', iris_tex,
            center=(p.iris_center_u, p.iris_center_v),
            radius_inner=p.iris_radius_inner,
            radius_outer=p.iris_radius_outer)
        changed = 0
        for polygon in head.data.polygons:
            expected = classifications[polygon.index]
            if polygon.index in eye_polygons:
                if polygon.material_index != 1:
                    changed += 1
                polygon.material_index = 1
            elif polygon.material_index == 1:
                polygon.material_index = expected
                changed += 1
        head.data.update()

        p.diagnostic_report = (
            "眼睛修复: %d 个眼球面，调整 %d 个面；来源 %s"
            % (len(eye_polygons), changed,
               os.path.basename(iris_tex)))
        self.report({'INFO'}, p.diagnostic_report)
        return {'FINISHED'}


class ROE_OT_adopt_selection(Operator):
    bl_idname = "roe.adopt_selection"
    bl_label = "将所选网格设为当前模型"
    bl_description = "采用通过 FBX/OBJ/glTF 或其他插件导入的所选网格"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, "请先选择至少一个网格对象")
            return {'CANCELLED'}
        batch = str(time.time_ns())
        for obj in meshes:
            obj[IMPORT_BATCH_KEY] = batch
            if not source_layout_is_cached(obj) and not generated_material_layout(obj):
                store_source_layout(obj)
        for armature in related_armatures(meshes):
            armature[IMPORT_BATCH_KEY] = batch
        context.scene[ACTIVE_IMPORT_BATCH_KEY] = batch
        context.scene.roe.apply_scope = 'LATEST'
        self.report({'INFO'}, "已采用 %d 个网格" % len(meshes))
        return {'FINISHED'}


class ROE_OT_diagnose_model(Operator):
    bl_idname = "roe.diagnose_model"
    bl_label = "检查模型"
    bl_description = "检查骨架、UV、材质槽、贴图和重复网格，不修改模型"

    def execute(self, context):
        p = context.scene.roe
        meshes = [obj for obj in scene_meshes()
                  if not re.match(r'^\d+_', obj.name)]
        if not meshes:
            p.diagnostic_report = "未找到网格"
            self.report({'ERROR'}, p.diagnostic_report)
            return {'CANCELLED'}

        issues = []
        flat_materials = 0
        for obj in meshes:
            if not obj.data.polygons:
                issues.append("%s 没有面" % obj.name)
            if not obj.data.uv_layers:
                issues.append("%s 没有 UV" % obj.name)
            if not obj.material_slots:
                issues.append("%s 没有材质" % obj.name)
                continue
            used = {polygon.material_index for polygon in obj.data.polygons}
            if used and max(used) >= len(obj.material_slots):
                issues.append("%s 面索引超出材质槽" % obj.name)
            for index in used:
                material = obj.material_slots[index].material
                if material is None:
                    issues.append("%s 槽 %d 为空" % (obj.name, index))
                elif diffuse_image(material) is None \
                        and not material_is_transparent_only(material):
                    flat_materials += 1

        armatures = related_armatures(meshes)
        if len(armatures) > 1:
            issues.append("检测到 %d 个关联骨架；XPS 通常应使用一个" % len(armatures))

        visible_groups = {}
        for obj in context.scene.objects:
            if obj.type == 'MESH' and not obj.hide_get():
                visible_groups.setdefault(canonical_object_name(obj.name), []).append(obj)
        duplicates = [name for name, objects in visible_groups.items()
                      if len(objects) > 1]
        if duplicates:
            issues.append("存在 %d 组可见同名网格" % len(duplicates))

        workflow = effective_workflow(p, meshes)
        if workflow == 'ROE':
            lost = [obj.name for obj in meshes
                    if generated_material_layout(obj)
                    and not source_layout_is_cached(obj)]
            if lost:
                issues.append("%d 个 ROE 网格需要从原 FBX 恢复分区" % len(lost))

        summary = "%s: %d 网格 / %d 骨架 / %d 纯色材质" % (
            "ROE" if workflow == 'ROE' else "通用",
            len(meshes), len(armatures), flat_materials)
        p.diagnostic_report = summary if not issues else summary + "；" + "；".join(issues[:4])
        self.report({'WARNING'} if issues else {'INFO'}, p.diagnostic_report)
        return {'FINISHED'}


class ROE_OT_set_slot_override(Operator):
    bl_idname = "roe.set_slot_override"
    bl_label = "保存当前槽覆盖"
    bl_description = "为活动网格的当前材质槽保存用途和 Base Color 贴图覆盖"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        p = context.scene.roe
        if not obj or obj.type != 'MESH' or not obj.material_slots:
            self.report({'ERROR'}, "请先选择带材质槽的网格")
            return {'CANCELLED'}
        index = obj.active_material_index
        data = slot_overrides(obj)
        texture = p.slot_texture
        if p.slot_role == 'AUTO' and not texture:
            data.pop(str(index), None)
        else:
            data[str(index)] = {'role': p.slot_role, 'texture': texture}
        obj[SLOT_OVERRIDES_KEY] = json.dumps(data, ensure_ascii=True)
        self.report({'INFO'}, "已保存 %s 槽 %d 的覆盖" % (obj.name, index))
        return {'FINISHED'}


class ROE_OT_clear_slot_override(Operator):
    bl_idname = "roe.clear_slot_override"
    bl_label = "清除当前槽覆盖"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        data = slot_overrides(obj)
        data.pop(str(obj.active_material_index), None)
        obj[SLOT_OVERRIDES_KEY] = json.dumps(data, ensure_ascii=True)
        self.report({'INFO'}, "当前槽已恢复自动判断")
        return {'FINISHED'}


class ROE_OT_set_head_region(Operator):
    bl_idname = "roe.set_head_region"
    bl_label = "标记所选头部面"
    bl_description = "持久覆盖自动头部分类；请在编辑模式中选择需要修正的面"
    bl_options = {'REGISTER', 'UNDO'}

    VALUES = {
        'AUTO': 0,
        'FACE': 1,
        'EYE': 2,
        'LASH': 3,
        'BROW': 4,
        'OVERLAY': 5,
    }

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请先选择头部网格")
            return {'CANCELLED'}
        value = self.VALUES[context.scene.roe.head_region]
        count = 0
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.faces.layers.int.get(HEAD_REGION_ATTRIBUTE)
            if layer is None:
                layer = bm.faces.layers.int.new(HEAD_REGION_ATTRIBUTE)
            for face in bm.faces:
                if face.select:
                    face[layer] = value
                    if value:
                        face.material_index = value - 1
                    count += 1
            bmesh.update_edit_mesh(obj.data)
        else:
            attr = obj.data.attributes.get(HEAD_REGION_ATTRIBUTE)
            if attr and (attr.data_type != 'INT' or attr.domain != 'FACE'):
                obj.data.attributes.remove(attr)
                attr = None
            if attr is None:
                attr = obj.data.attributes.new(
                    HEAD_REGION_ATTRIBUTE, type='INT', domain='FACE')
            for polygon in obj.data.polygons:
                if polygon.select:
                    attr.data[polygon.index].value = value
                    if value:
                        polygon.material_index = value - 1
                    count += 1
            obj.data.update()
        if count == 0:
            self.report({'WARNING'}, "没有选中的面")
            return {'CANCELLED'}
        self.report({'INFO'}, "已标记 %d 个面；重新准备材质后仍会保留" % count)
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
        meshes = [o for o in scene_meshes() if not re.match(r'^\d+_', o.name)]
        if not meshes:
            self.report({'ERROR'}, "处理范围内没有可导出的网格")
            return {'CANCELLED'}
        workflow = effective_workflow(p, meshes)
        is_roe = workflow == 'ROE'
        head = find_head(meshes) if is_roe else None
        # 批量裸模 worker 会在对象上打 roe_nude_slots 标记；材质名嗅探只留给
        # 没有标记的旧 .blend——便携眼球烘焙会换掉 eye 槽材质名，嗅探并不稳定。
        combined_nude = bool(head and (
            head.get('roe_nude_slots')
            or (re.search(r'(?:^|_)nk_body(?:\.\d+)?$', head.name,
                          re.IGNORECASE)
                and len(head.material_slots) >= 6
                and [re.sub(r'\.\d+$', '', slot.material.name.lower())
                     if slot.material else ''
                     for slot in head.material_slots[:3]] ==
                    ['body', 'face', 'eye'])))
        head_slots = ({
            0: ('body', '5'),
            1: ('face', '5'),
            2: ('eye', '5'),
            3: ('lash', '7'),
            4: ('brow', '7'),
        } if combined_nude else self.HEAD_SLOTS)
        eye_slot = 2 if combined_nude else 1
        tex_dir = bpy.path.abspath(p.tex_dir) if p.tex_dir else ''
        if not os.path.isdir(tex_dir):
            fbx = bpy.path.abspath(p.fbx_path) if p.fbx_path else ''
            tex_dir = os.path.dirname(fbx) if os.path.isfile(fbx) else ''
        base = (head.name.split('.')[0] if head else meshes[0].name.split('.')[0])
        if base.endswith('_head'):
            base = base[:-5]
        if p.xps_out:
            out_path = bpy.path.abspath(p.xps_out)
        elif tex_dir:
            out_path = os.path.join(tex_dir, base + '_fixed.mesh')
        else:
            self.report({'ERROR'}, "通用模型请设置 XPS 输出路径")
            return {'CANCELLED'}
        if not out_path.lower().endswith('.mesh'):
            out_path += '.mesh'
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)
        armatures = related_armatures(meshes)
        if len(armatures) > 1:
            self.report({'ERROR'}, "当前模型关联了多个骨架，请只选择一个角色的网格")
            return {'CANCELLED'}

        fallback_group = []  # 兜底自建的组，导出后删除（防止污染后续 XPS 导入）

        def group_output_linked(gt):
            gout = next((n for n in gt.nodes if n.type == 'GROUP_OUTPUT'), None)
            return bool(gout and any(l.to_node == gout for l in gt.links))

        def repair_group(gt):
            """半成品组（建组中途异常）：内部 Principled 没连到组输出 -> 材质全黑。
            补上缺失的输出连接。"""
            principled = next((n for n in gt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            gout = next((n for n in gt.nodes if n.type == 'GROUP_OUTPUT'), None)
            if principled and gout and not any(l.to_node == gout for l in gt.links):
                try:
                    gt.links.new(principled.outputs['BSDF'], gout.inputs[0])
                except Exception:
                    pass
            return group_output_linked(gt)

        def group_valid(gt):
            return gt is not None and 'Alpha' in gt.inputs and group_output_linked(gt)

        def claim_xps_group_name(gt):
            """XNALaraMesh ignores valid groups named XPS Shader.001."""
            current = bpy.data.node_groups.get('XPS Shader')
            if current is not None and current is not gt:
                current.name = 'XPS Shader.broken.%d' % time.time_ns()
            gt.name = 'XPS Shader'
            return gt

        def get_xps_group():
            """XNALaraMesh 导出器只认 'XPS Shader' 节点组（按输入插槽名找贴图）。
            优先用 XNALaraMesh 自己的 xps_shader_group() 创建，保证与其导入器兼容——
            残缺组会让 XPS 导入报 KeyError: 'Alpha' 或渲染全黑（缺输出连接）。"""
            gt = bpy.data.node_groups.get('XPS Shader')
            if gt is not None and not group_valid(gt):
                if 'Alpha' not in gt.inputs or not repair_group(gt):
                    gt.name = 'XPS Shader.broken'   # 修不好的残缺组：改名让位
                    gt = None
            if gt:
                return claim_xps_group_name(gt)
            import importlib
            for modname in ('XNALaraMesh-master', 'XNALaraMesh'):
                try:
                    mc = importlib.import_module(modname + '.material_creator')
                    gt = mc.xps_shader_group()
                    if group_valid(gt) or repair_group(gt):
                        return claim_xps_group_name(gt)
                    gt.name = 'XPS Shader.broken'
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
            return claim_xps_group_name(gt)

        used_images = []
        temp_images = []

        def flat_image(name, material):
            safe = re.sub(r'[^A-Za-z0-9.-]+', '-', name).strip('-') or 'material'
            path = os.path.join(out_dir, safe + '_diffuse.png')
            image = bpy.data.images.new(
                'xps_flat_%s_%d' % (safe, time.time_ns()), 4, 4, alpha=True)
            color = material_base_color(material)
            image.pixels = list(color) * 16
            image.filepath_raw = path
            image.file_format = 'PNG'
            image.save()
            temp_images.append(image)
            return image

        def image_for_slot(obj, slot_index, material):
            override = slot_overrides(obj).get(str(slot_index), {})
            override_path = bpy.path.abspath(override.get('texture', ''))
            if override_path and os.path.isfile(override_path):
                return bpy.data.images.load(override_path, check_existing=True)
            return diffuse_image(material) or flat_image(
                '%s-%d' % (obj.name, slot_index), material)

        def simple_export_mat(name, image, source_material=None):
            image = image or flat_image(name, source_material)
            source_path = bpy.path.abspath(image.filepath)
            if not os.path.isfile(source_path):
                safe = re.sub(r'[^A-Za-z0-9.-]+', '-', name).strip('-') or 'texture'
                copy = image.copy()
                copy.filepath_raw = os.path.join(out_dir, safe + '_diffuse.png')
                copy.file_format = 'PNG'
                copy.save()
                temp_images.append(copy)
                image = copy
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

        temps, temp_mats, hidden = [], [], []
        try:
            # 眼球贴图烘焙
            baked = None
            if is_roe and head:
                iris = find_tex(tex_dir, '*eye_iris*Albedo*.png')
                if iris or (len(head.material_slots) > 1):
                    baked = bake_eye_texture(head, iris,
                                             os.path.join(out_dir, 'roe_eye_baked.png'),
                                             eye_slot=eye_slot)

            # 复制 body/hair。多材质 body 必须按槽拆开，否则颈部 face 槽会被
            # 第一个 body 贴图覆盖，导出的 XPS 会重新出现黑色/粉色碎片。
            for o in meshes:
                if is_roe and o is head:
                    continue
                base_name = o.name.split('.')[0].replace('_', '-')
                used_slots = sorted({q.material_index for q in o.data.polygons})
                for slot_index in used_slots:
                    pm = (o.material_slots[slot_index].material
                          if slot_index < len(o.material_slots) else None)
                    if is_roe and material_is_transparent_only(pm):
                        continue
                    part = o.copy(); part.data = o.data.copy()
                    context.collection.objects.link(part)
                    if len(used_slots) > 1:
                        bm = bmesh.new()
                        bm.from_mesh(part.data)
                        remove = [face for face in bm.faces
                                  if face.material_index != slot_index]
                        bmesh.ops.delete(bm, geom=remove, context='FACES')
                        bm.to_mesh(part.data)
                        bm.free()
                        part.data.update()

                    img = image_for_slot(o, slot_index, pm)
                    m = simple_export_mat(
                        '%s-%d' % (o.name, slot_index), img, pm)
                    part.data.materials.clear()
                    part.data.materials.append(m)
                    temp_mats.append(m)
                    for q in part.data.polygons:
                        q.material_index = 0
                    if is_roe:
                        rg = roe_xps_render_group(o, slot_index, pm)
                    else:
                        rg = '7' if material_uses_alpha(pm) else '5'
                    suffix = '-slot%d' % slot_index if len(used_slots) > 1 else ''
                    part.name = '%s_%s%s_0.1' % (rg, base_name, suffix)
                    temps.append(part)

            # 复制 head 并按材质槽拆分
            if is_roe and head:
                if len(head.material_slots) >= 5:
                    used_slots = {polygon.material_index
                                  for polygon in head.data.polygons}
                    for idx, (xname, rg) in head_slots.items():
                        if idx not in used_slots:
                            continue
                        pm = head.material_slots[idx].material
                        if material_is_transparent_only(pm):
                            continue
                        part = head.copy(); part.data = head.data.copy()
                        context.collection.objects.link(part)
                        bm = bmesh.new()
                        bm.from_mesh(part.data)
                        remove = [face for face in bm.faces
                                  if face.material_index != idx]
                        bmesh.ops.delete(bm, geom=remove, context='FACES')
                        bm.to_mesh(part.data)
                        bm.free()
                        part.data.update()
                        img = baked if idx == eye_slot else diffuse_image(pm)
                        m = simple_export_mat(xname, img, pm)
                        part.data.materials.clear()
                        part.data.materials.append(m)
                        temp_mats.append(m)
                        for q in part.data.polygons:
                            q.material_index = 0
                        part.name = '%s_%s_0.1' % (rg, xname)
                        temps.append(part)
                else:
                    dup = head.copy(); dup.data = head.data.copy()
                    context.collection.objects.link(dup)
                    pm = (head.material_slots[0].material
                          if head.material_slots else None)
                    img = diffuse_image(pm)
                    m = simple_export_mat('face', img, pm)
                    dup.data.materials.clear()
                    dup.data.materials.append(m)
                    temp_mats.append(m)
                    dup.name = '5_face_0.1'
                    temps.append(dup)

            # 输出目录可能不存在；贴图不在输出目录时复制过去（XPS 按 .mesh 同目录找贴图）
            import shutil
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
            if armatures:
                armatures[0].select_set(True)
                context.view_layer.objects.active = armatures[0]

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
            for image in temp_images:
                try:
                    bpy.data.images.remove(image)
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


class ROE_OT_fix_xps_armature(Operator):
    bl_idname = "roe.fix_xps_armature"
    bl_label = "4. 修正XPS骨架方向"
    bl_description = "XPS 是 Y-up 坐标系，XNALaraMesh 导入后骨架躺在地上；转正(+90°X 烘进骨架数据)，网格不受影响"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import math
        fixed = []
        for arm in [o for o in context.scene.objects if o.type == 'ARMATURE']:
            heads = [b.head_local for b in arm.data.bones]
            if not heads:
                continue
            zs = max(abs(h.z) for h in heads)
            ys = max(abs(h.y) for h in heads)
            if ys <= zs * 2 or ys < 0.3:   # 骨架不是躺平的，跳过
                continue
            kids = [o for o in context.scene.objects if o.parent is arm]
            mats = {o: o.matrix_world.copy() for o in kids}
            for o in kids:                  # 暂时解除父子，网格保持原位
                o.parent = None
                o.matrix_world = mats[o]
            arm.rotation_euler.x += math.radians(90)
            bpy.ops.object.select_all(action='DESELECT')
            arm.select_set(True)
            context.view_layer.objects.active = arm
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
            for o in kids:                  # 挂回去
                o.parent = arm
                o.matrix_parent_inverse = arm.matrix_world.inverted()
            fixed.append(arm.name)
        if fixed:
            self.report({'INFO'}, "已转正骨架: %s" % ', '.join(fixed))
        else:
            self.report({'INFO'}, "没有发现躺平的骨架")
        return {'FINISHED'}


# ----------------------------------------------------------------------- panel

class ROE_PT_panel(Panel):
    bl_label = "Universal XPS / ROE"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ROE'

    def draw(self, context):
        p = context.scene.roe
        layout = self.layout
        layout.prop(p, 'workflow_mode')
        layout.prop(p, 'apply_scope')

        source = layout.box()
        source.label(text="模型来源", icon='OUTLINER_OB_MESH')
        source.prop(p, 'fbx_path')
        source.prop(p, 'replace_previous')
        row = source.row(align=True)
        row.operator('roe.import_fbx', text="导入 FBX", icon='IMPORT')
        row.operator('roe.adopt_selection', text="采用所选", icon='RESTRICT_SELECT_OFF')

        if p.workflow_mode != 'GENERIC':
            layout.prop(p, 'tex_dir')

        row = layout.row(align=True)
        row.operator('roe.diagnose_model', icon='VIEWZOOM')
        row.operator('roe.apply_materials', icon='MATERIAL')
        repair = layout.row(align=True)
        operator = repair.operator('roe.apply_materials', text="修复脸部")
        operator.repair_scope = 'FACE'
        operator = repair.operator('roe.apply_materials', text="修复身体")
        operator.repair_scope = 'BODY'
        operator = repair.operator('roe.apply_materials', text="修复翅膀")
        operator.repair_scope = 'WING'
        layout.operator('roe.repair_eyes', icon='HIDE_OFF')
        report = layout.box()
        report.label(text="最近检查")
        for line in p.diagnostic_report.split('；')[:4]:
            report.label(text=line)

        layout.prop(p, 'show_advanced', toggle=True)
        if p.show_advanced:
            advanced = layout.box()
            if p.workflow_mode != 'GENERIC':
                advanced.label(text="ROE 皮肤 / 眼睛 / 睫毛")
                advanced.prop(p, 'skin_saturation')
                advanced.prop(p, 'lash_alpha_gain')
                advanced.prop(p, 'lash_darken')
                row = advanced.row(align=True)
                row.prop(p, 'iris_center_u')
                row.prop(p, 'iris_center_v')
                row = advanced.row(align=True)
                row.prop(p, 'iris_radius_inner')
                row.prop(p, 'iris_radius_outer')

            obj = context.object
            if obj and obj.type == 'MESH' and obj.material_slots:
                advanced.separator()
                advanced.label(text="当前网格: %s / 槽 %d" %
                               (obj.name, obj.active_material_index))
                advanced.prop(p, 'slot_role')
                advanced.prop(p, 'slot_texture')
                row = advanced.row(align=True)
                row.operator('roe.set_slot_override', icon='CHECKMARK')
                row.operator('roe.clear_slot_override', icon='X')
                if p.workflow_mode != 'GENERIC':
                    advanced.separator()
                    advanced.label(text="编辑模式选择头部面后人工分类")
                    advanced.prop(p, 'head_region')
                    advanced.operator('roe.set_head_region', icon='FACESEL')

        output = layout.box()
        output.label(text="XPS 输出", icon='EXPORT')
        output.prop(p, 'xps_out', text="")
        output.operator('roe.export_xps', icon='EXPORT')
        output.operator('roe.fix_xps_armature', icon='ARMATURE_DATA')


classes = (ROE_Props, ROE_OT_import_fbx, ROE_OT_apply_materials,
           ROE_OT_repair_eyes,
           ROE_OT_adopt_selection, ROE_OT_diagnose_model,
           ROE_OT_set_slot_override, ROE_OT_clear_slot_override,
           ROE_OT_set_head_region,
           ROE_OT_export_xps, ROE_OT_fix_xps_armature, ROE_PT_panel)


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
