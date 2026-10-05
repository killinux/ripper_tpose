# -*- coding: utf-8 -*-
"""给 MMD 用的爆衣，做在 mmd_tools 导入的模型上（任何 PMX）：表情加进模型，mmd_tools 照常导出 PMX，VMD 由
vmd.py 写。两种做法：

  碎片飞散  衣服复制一份切成碎片（shards.py），碎片的材质 <材质>_burst 在文件里透明，爆衣碎片_材質 把它们显示出来，
            顶点表情 爆衣 / 爆衣落下 让它们飞出去、落地
  直接消失  只有 衣服非表示_材質（衣服的材质 alpha x 0），VMD 让它一下子或几帧内淡出

衣服下面要有完整的身体（不然露出身体上的洞）。模型的身体有形状键「裸体形状」时（ROE 的 full 版：身体平时收在衣服里，
这个形状键是它自己的形状）可以「换成完整身体」：身体复制一份成脱衣用的（位置是裸体形状、法线也是那个形状的，
材质 <材质>_nude 在文件里透明），裸体形状 从顶点表情改成换身体的材质表情（原来的身体 alpha x 0、脱衣那份 alpha 加回来）。
MMD 不为顶点表情重算法线（一份身体靠形状键变回去，光照还是收在衣服里那个形状的），Blender 的自定义法线会跟着形状键转
——两份身体在两边都对。

加了什么都记在根物体的 cb_mmd 里，「撤掉」按它删干净（脱衣身体删掉时 裸体形状 形状键从它还原）。
"""
import json

import bmesh
import bpy
import numpy as np

from . import shards, vmd

SHARD_SUFFIX = "_burst"
NUDE_SUFFIX = "_nude"
TAG = "cb_mmd"                  # 根物体：这次加了什么（json）
SHARD_TAG = "cb_mmd_shards"     # 碎片物体
NUDE_TAG = "cb_mmd_nude"        # 脱衣身体物体
SRC_ATTR = "cb_src"             # 脱衣身体：每个顶点从原网格哪个顶点复制来
DEFAULTS = dict(shards.DEFAULTS, style="SHARDS", swap=True)


def _model():
    from mmd_tools.core.model import Model
    return Model


def find_root(obj):
    """obj 所在 mmd_tools 模型的根物体（不是 mmd_tools 模型时 None）。"""
    if obj is None:
        return None
    try:
        return _model().findRoot(obj)
    except Exception:
        return None


def parts(root):
    """(骨架, 模型自己的网格——不含这里加的碎片 / 脱衣身体)。"""
    rig = _model()(root)
    arm = rig.armature()
    meshes = [m for m in rig.meshes() if not m.get(SHARD_TAG) and not m.get(NUDE_TAG)]
    return arm, meshes


def model_materials(root):
    """模型网格上的材质，按出现顺序（不含加的副本：这里生成的，或导入的爆衣 PMX 里碎片 / 脱衣身体的）。"""
    copies = copy_materials(root)
    out = []
    for mesh in parts(root)[1]:
        for slot in mesh.material_slots:
            if slot.material is not None and slot.material not in out and slot.material.name not in copies:
                out.append(slot.material)
    return out


def copy_materials(root):
    """碎片和脱衣身体的材质：爆衣碎片_材質、换身体的 裸体形状 里加回 alpha 的那些。"""
    out = set()
    for name in (vmd.SHARDS, vmd.BODY):
        morph = root.mmd_root.material_morphs.get(name)
        for d in getattr(morph, "data", ()):
            if d.material and d.offset_type == "ADD":
                out.add(d.material)
    return out


def burst_morphs(root):
    """模型里已经有的爆衣表情：{"SHARDS": 碎片飞散要的都在, "VANISH": 直接消失要的在, "missing": 碎片飞散缺的}。"""
    mm = root.mmd_root
    have = {vmd.THROW: mm.vertex_morphs.get(vmd.THROW) is not None,
            vmd.FALL: mm.vertex_morphs.get(vmd.FALL) is not None,
            vmd.SHARDS: mm.material_morphs.get(vmd.SHARDS) is not None,
            vmd.OUTFIT: mm.material_morphs.get(vmd.OUTFIT) is not None}
    return {"SHARDS": all(have.values()), "VANISH": have[vmd.OUTFIT],
            "missing": [name for name, ok in have.items() if not ok]}


def imported_burst(root):
    """模型带着爆衣碎片的表情、却不是在这个文件里生成的（导入的爆衣 PMX）：不能再生成一次，可以直接预览、导出 VMD。
    只有两份身体（`裸体形状` 是换身体的材质表情，ROE 的 full 版 10-05 起都是）不算：照常生成碎片，身体不再换。"""
    if has_burst(root):
        return False
    mm = root.mmd_root
    return mm.vertex_morphs.get(vmd.THROW) is not None or mm.material_morphs.get(vmd.SHARDS) is not None


def two_bodies(root):
    """模型里已经有两份身体：`裸体形状` 是材质表情、有加回透明度的条目（pmx_two_bodies.py 或这个插件做的）。"""
    morph = root.mmd_root.material_morphs.get(vmd.BODY)
    return morph is not None and any(d.offset_type == "ADD" for d in morph.data)


def outfit_names(root):
    try:
        return list(json.loads(root.get("cb_outfit", "[]")))
    except ValueError:
        return []


def set_outfit(root, names):
    root["cb_outfit"] = json.dumps(sorted(set(names)), ensure_ascii=False)


def outfit_from_morph(root):
    """衣服非表示_材質 里 alpha 乘 0 的材质（ROE 的 full 版自带这个表情）。"""
    morph = root.mmd_root.material_morphs.get(vmd.OUTFIT)
    if morph is None:
        return []
    return [d.material for d in morph.data
            if d.material and d.offset_type == "MULT" and d.diffuse_color[3] < 1e-6]


def _record(root):
    try:
        return json.loads(root.get(TAG, "{}"))
    except ValueError:
        return {}


def has_burst(root):
    return bool(root.get(TAG))


def world_co(obj, co=None):
    if co is None:
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
    m = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def physics_bones(root):
    """被物理（动态刚体）带着的骨头：碎片不挂在它们上面。"""
    out = set()
    for obj in _model()(root).rigidBodies():
        rigid = getattr(obj, "mmd_rigid", None)
        if rigid is not None and rigid.type in ("1", "2") and rigid.bone:
            out.add(rigid.bone)
    return out


def body_key(mesh):
    keys = mesh.data.shape_keys
    return keys.key_blocks.get(vmd.BODY) if keys else None


def key_co(kb):
    co = np.empty(len(kb.data) * 3)
    kb.data.foreach_get("co", co)
    return co.reshape(-1, 3)


def body_slots(mesh, outfit):
    """形状键 裸体形状 移动的身体：不是衣服、而且有面碰到被移动顶点的材质槽。"""
    kb = body_key(mesh)
    if kb is None:
        return set()
    moved = np.linalg.norm(key_co(kb) - key_co(kb.relative_key), axis=1) > 1e-6
    slots = set()
    for p in mesh.data.polygons:
        mat = mesh.material_slots[p.material_index].material if p.material_index < len(mesh.material_slots) else None
        if mat is not None and mat.name not in outfit and moved[list(p.vertices)].any():
            slots.add(p.material_index)
    return slots


def copy_material(mat, suffix, alpha=None):
    """mat 的副本 <名字><suffix>：mmd_tools 的材质编号重新分配（复制来的编号和原来的一样，材质表情会指到原材质上），
    alpha 给了就设成它（边线 alpha 一起）。"""
    from mmd_tools.core.material import FnMaterial
    new = mat.copy()
    new.name = mat.name + suffix
    mm = new.mmd_material
    mm.name_j = (mat.mmd_material.name_j or mat.name) + suffix
    if mat.mmd_material.name_e:
        mm.name_e = mat.mmd_material.name_e + suffix
    mm.material_id = -1
    FnMaterial(new).material_id
    if alpha is not None:
        ec = tuple(mm.edge_color)
        if new.use_nodes and new.node_tree is not None and new.node_tree.nodes.get("mmd_shader") is None:
            # 不是 mmd_tools 的着色器（「Convert Materials For Cycles」转过的之类）：通过属性设，mmd_tools 会把它自己的
            # 着色器塞回材质、连到输出上，副本就和原材质不一样了（爆开 / 换身体那一下质感一跳）。只写数值（导出 PMX
            # 用它），Blender 里靠 alpha_wrap 的透明节点显示
            mm["alpha"] = alpha
            mm["edge_color"] = (ec[0], ec[1], ec[2], alpha)
        else:
            mm.alpha = alpha
            mm.edge_color = (ec[0], ec[1], ec[2], alpha)
        # 副本和原来的面重合：mmd_tools 设 alpha 时给的 HASHED 在 EEVEE 里画成黑块（alpha 0 也一样），它的导入器对
        # 重合的面用的是 BLEND + 不显示背面
        new.blend_method = "BLEND"
        new.show_transparent_back = False
    return new


def split_copy(src, slots, name):
    """src 的副本，只留 slots 这几个材质槽的面（别的槽删掉），同一个父物体、同样的修改器。"""
    obj = src.copy()
    obj.data = src.data.copy()
    obj.name = obj.data.name = name
    for coll in src.users_collection:
        coll.objects.link(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index not in slots], context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    for i in sorted(set(range(len(obj.material_slots))) - set(slots), reverse=True):
        obj.data.materials.pop(index=i)
    for key in [k for k in list(obj.keys()) if k.startswith("cb_")]:
        del obj[key]
    return obj


def _morph_entry(morph, mat, mode, mesh_name, alpha=1.0, edge=1.0):
    d = morph.data.add()
    d.related_mesh = mesh_name
    d.material = mat.name
    d.offset_type = mode
    one, zero = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    if mode == "MULT":                  # alpha x 0, everything else x 1
        d.diffuse_color = (1.0, 1.0, 1.0, 0.0)
        d.specular_color = one
        d.shininess = 1.0
        d.ambient_color = one
        d.edge_color = (1.0, 1.0, 1.0, 0.0)
        d.edge_weight = 1.0
        d.texture_factor = d.sphere_texture_factor = d.toon_texture_factor = (1.0, 1.0, 1.0, 1.0)
    else:                               # the alpha the file took away, added back
        d.diffuse_color = (0.0, 0.0, 0.0, alpha)
        d.specular_color = zero
        d.shininess = 0.0
        d.ambient_color = zero
        d.edge_color = (0.0, 0.0, 0.0, edge)
        d.edge_weight = 0.0
        d.texture_factor = d.sphere_texture_factor = d.toon_texture_factor = (0.0, 0.0, 0.0, 0.0)


def material_morph(root, name, entries):
    """材质表情 name（有就清空重写）：entries = [(材质, "MULT" | "ADD", 所在网格名, alpha, 边线 alpha)]。"""
    morphs = root.mmd_root.material_morphs
    morph = morphs.get(name)
    if morph is None:
        morph = morphs.add()
        morph.name = name
        morph.category = "OTHER"
    morph.data.clear()
    for mat, mode, mesh_name, alpha, edge in entries:
        _morph_entry(morph, mat, mode, mesh_name, alpha, edge)
    return morph


def _remove_named(collection, name):
    i = collection.find(name)
    if i >= 0:
        collection.remove(i)


def display(root, name, morph_type, add=True):
    frame = root.mmd_root.display_item_frames.get("表情")
    if frame is None:
        return
    for i, item in enumerate(frame.data):
        if item.type == "MORPH" and item.name == name and item.morph_type == morph_type:
            if not add:
                frame.data.remove(i)
            return
    if add:
        item = frame.data.add()
        item.type = "MORPH"
        item.morph_type = morph_type
        item.name = name


def retype(root, name, old, new):
    """组合表情和表情显示框里 name 的类型 old -> new（裸体形状 在顶点表情和材质表情之间换）。"""
    for group in root.mmd_root.group_morphs:
        for d in group.data:
            if d.name == name and d.morph_type == old:
                d.morph_type = new
    frame = root.mmd_root.display_item_frames.get("表情")
    for item in getattr(frame, "data", ()):
        if item.type == "MORPH" and item.name == name and item.morph_type == old:
            item.morph_type = new


def shape_normals(mesh_data, co):
    """mesh_data 的顶点放到 co 时的分割法线（每个角一个，自定义法线跟着形状转——和 Blender 显示形状键时一样）。"""
    data = mesh_data.copy()
    try:
        if data.shape_keys:
            holder = bpy.data.objects.new("cb_shape_normals", data)
            for kb in reversed(list(data.shape_keys.key_blocks)):
                holder.shape_key_remove(kb)
            bpy.data.objects.remove(holder)
        data.vertices.foreach_set("co", co.astype(np.float32).ravel())
        data.update()
        data.calc_normals_split()
        out = np.empty(len(data.loops) * 3, dtype=np.float32)
        data.loops.foreach_get("normal", out)
        return out.reshape(-1, 3)
    finally:
        bpy.data.meshes.remove(data)


TRUST = 0.0       # a turned custom normal pointing away from the smooth one (more than 90 degrees) is not trusted


def smooth_normals(mesh_data, co):
    """Per loop: the smooth normal of the surface with its vertices at co - angle-weighted face normals summed over
    the vertices at the same place (the mesh is split along UV seams; welded here, so no seam shows)."""
    mesh_data.calc_loop_triangles()
    tris = np.array([t.vertices[:] for t in mesh_data.loop_triangles], dtype=np.int64).reshape(-1, 3)
    weld = shards.WELD * max(float(np.ptp(co[:, 2])), 1e-9) / shards.REFERENCE_HEIGHT    # any import scale
    _, ids = np.unique(np.round(co / weld).astype(np.int64), axis=0, return_inverse=True)
    ids = ids.ravel()
    p = co[tris]
    face = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    face /= np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-20)
    acc = np.zeros((ids.max() + 1, 3))
    for k in range(3):
        u = p[:, (k + 1) % 3] - p[:, k]
        v = p[:, (k + 2) % 3] - p[:, k]
        cos = (u * v).sum(1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-20)
        np.add.at(acc, ids[tris[:, k]], face * np.arccos(np.clip(cos, -1.0, 1.0))[:, None])
    vn = acc[ids]
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)
    lv = np.empty(len(mesh_data.loops), dtype=np.int64)
    mesh_data.loops.foreach_get("vertex_index", lv)
    return vn[lv]


def nude_normals(mesh_data, co):
    """The normals the nude copy keeps: the custom normals turned into the shape co (as Blender shows a shape key),
    except where the turn flipped them - skin folded under the outfit (a08's nails: up to 171 degrees off the nude
    version) - there the smooth normal of the shape.  Smooth normals are no reference anywhere else: they round off
    the nails' own creases (a 20-degree test replaced 30,000 loops and made 707 vertices worse).  For exact normals
    take them from the nude version's PMX (normals_from_pmx).  Returns (per-loop normals, loops replaced)."""
    turned = shape_normals(mesh_data, co)
    smooth = smooth_normals(mesh_data, co)
    dot = (turned * smooth).sum(1) / np.maximum(np.linalg.norm(turned, axis=1), 1e-20)
    bad = dot < TRUST
    turned[bad] = smooth[bad]
    return turned, int(bad.sum())


def nude_copy(mesh, slots):
    """脱衣身体：mesh 里 slots 这些材质槽的面复制出来，位置换成 裸体形状、法线是那个形状的（固定下来），别的形状键
    （表情）跟着平移；材质 <材质>_nude 透明。mesh 上的 裸体形状 删掉。返回 (副本, [(原材质, 副本材质)])。"""
    kb = body_key(mesh)
    nude = key_co(kb)
    normals, replaced = nude_normals(mesh.data, nude)
    copy = mesh.copy()
    copy.data = mesh.data.copy()
    copy.name = copy.data.name = mesh.name + NUDE_SUFFIX
    for coll in mesh.users_collection:
        coll.objects.link(copy)
    me = copy.data
    attr = me.attributes.new("cb_nude_normal", "FLOAT_VECTOR", "CORNER")
    attr.data.foreach_set("vector", normals.ravel())
    src = me.attributes.new(SRC_ATTR, "INT", "POINT")
    src.data.foreach_set("value", np.arange(len(me.vertices), dtype=np.int32))
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index not in slots], context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    idx = np.empty(len(me.vertices), dtype=np.int32)
    me.attributes[SRC_ATTR].data.foreach_get("value", idx)
    # 形状键：基础形状换成 裸体形状，别的（表情）保持相对基础形状的位移，mmd_bind*（滑块绑定）和 裸体形状 本身去掉
    keep = []
    for key in copy.data.shape_keys.key_blocks[1:]:
        if key.name == vmd.BODY or key.name.startswith("mmd_bind"):
            continue
        keep.append((key.name, nude[idx] + (key_co(key) - key_co(key.relative_key))))
    for key in reversed(list(copy.data.shape_keys.key_blocks)):
        copy.shape_key_remove(key)
    me.vertices.foreach_set("co", nude[idx].astype(np.float32).ravel())
    if keep:
        copy.shape_key_add(name="Basis", from_mix=False)
        for name, co in keep:
            copy.shape_key_add(name=name, from_mix=False).data.foreach_set("co", co.astype(np.float32).ravel())
    loop_normals = np.empty(len(me.loops) * 3, dtype=np.float32)
    me.attributes["cb_nude_normal"].data.foreach_get("vector", loop_normals)
    me.attributes.remove(me.attributes["cb_nude_normal"])
    me.update()
    me.use_auto_smooth = True
    me.normals_split_custom_set(loop_normals.reshape(-1, 3).tolist())
    pairs = []
    keep_slots = sorted(slots)
    for i in sorted(set(range(len(copy.material_slots))) - set(keep_slots), reverse=True):
        me.materials.pop(index=i)
    for slot in copy.material_slots:
        if slot.material is not None:
            new = copy_material(slot.material, NUDE_SUFFIX, alpha=0.0)
            pairs.append((slot.material, new))
            slot.material = new
    for key in [k for k in list(copy.keys()) if k.startswith("cb_")]:
        del copy[key]
    copy[NUDE_TAG] = json.dumps({"source": mesh.name, "smooth_loops": replaced}, ensure_ascii=False)
    mesh.shape_key_remove(kb)
    return copy, pairs


def _rebuild_sliders(rig, bind=True):
    """mmd_tools' morph_slider.create() makes its hidden .dummy_armature the active object: the user's stays."""
    vl = bpy.context.view_layer
    active = vl.objects.active
    rig.morph_slider.create()
    if bind:
        rig.morph_slider.bind()
    if active is not None and vl.objects.active is not active and active.name in vl.objects:
        vl.objects.active = active


def _sliders(root):
    rig = _model()(root)
    placeholder = rig.morph_slider.placeholder()
    bound = placeholder is not None and rig.morph_slider.placeholder(binded=True) is not None
    return rig, placeholder, bound


# ---- 材质表情在 Blender 里看得见：不是 mmd_tools 着色器的材质（「Convert Materials For Cycles」转成了原理化BSDF
# 之类），mmd_tools 的材质表情节点留在材质里却没连到着色器上，衣服非表示_材質 / 爆衣碎片_材質 / 裸体形状 拉满了也看不出来。
# 这种材质在材质输出前面插一个小节点组：按这几个表情给的 alpha（文件里的 alpha x 乘算条目 + 加算条目，MMD 的顺序）
# 和「透明」混合，系数由表情滑块驱动。mmd_tools 着色器的材质不用插（它自己连好了）。

WRAP = "CB 爆衣透明"          # 材质里插的节点
WRAP_TREE = "CB_爆衣透明"     # 它用的节点组：混合着色器（透明, 原来的表面, 系数 = alpha）
BLEND_PROP = "cb_mmd_blend"   # 材质原来的混合模式（不透明 / 裁剪改成了 HASHED，撤掉时还原）


def _wrap_tree():
    tree = bpy.data.node_groups.get(WRAP_TREE)
    if tree is not None:
        return tree
    tree = bpy.data.node_groups.new(WRAP_TREE, "ShaderNodeTree")
    if hasattr(tree, "interface"):                                      # Blender 4.0+
        tree.interface.new_socket("Shader", in_out="INPUT", socket_type="NodeSocketShader")
        alpha = tree.interface.new_socket("Alpha", in_out="INPUT", socket_type="NodeSocketFloat")
        tree.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    else:
        tree.inputs.new("NodeSocketShader", "Shader")
        alpha = tree.inputs.new("NodeSocketFloatFactor", "Alpha")
        tree.outputs.new("NodeSocketShader", "Shader")
    alpha.default_value, alpha.min_value, alpha.max_value = 1.0, 0.0, 1.0
    nodes, links = tree.nodes, tree.links
    gin, gout = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
    clear, mix = nodes.new("ShaderNodeBsdfTransparent"), nodes.new("ShaderNodeMixShader")
    gin.location, clear.location, mix.location, gout.location = (-400, 0), (-200, 120), (0, 0), (200, 0)
    links.new(gin.outputs[1], mix.inputs[0])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(gin.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], gout.inputs[0])
    return tree


def _wrappers(mat):
    nt = mat.node_tree if mat is not None else None
    return [n for n in getattr(nt, "nodes", ()) if n.type == "GROUP" and n.node_tree and n.node_tree.name == WRAP_TREE]


def alpha_terms(root):
    """{材质名: (文件里的 alpha, [("MULT" | "ADD", 条目的 alpha, [(滑块, 系数)])])}：爆衣的几个材质表情。
    一个表情的权重 = 它自己的滑块 + 含有它的组合表情的滑块 x 系数（mmd_tools 绑定滑块也是这样算）。"""
    groups = {}
    for g in root.mmd_root.group_morphs:
        for d in g.data:
            if d.morph_type == "material_morphs":
                groups.setdefault(d.name, []).append((g.name, d.factor))
    out = {}
    for name in (vmd.OUTFIT, vmd.SHARDS, vmd.BODY):
        morph = root.mmd_root.material_morphs.get(name)
        for d in getattr(morph, "data", ()):
            mat = bpy.data.materials.get(d.material) if d.material else None
            if mat is None:
                continue
            entry = out.setdefault(mat.name, (mat.mmd_material.alpha, []))
            entry[1].append((d.offset_type, d.diffuse_color[3], [(name, 1.0)] + groups.get(name, [])))
    return out


def alpha_wrap(root):
    """不是 mmd_tools 着色器的材质插上 WRAP（已经有就只更新驱动器）。没有表情滑块时系数是常数（文件里的 alpha：
    衣服显示、碎片和脱衣身体隐藏），有了就跟着滑块。返回插了的材质名。"""
    _rig, placeholder, _bound = _sliders(root)
    key = placeholder.data.shape_keys if placeholder is not None else None
    done = []
    for mat_name, (base, entries) in alpha_terms(root).items():
        mat = bpy.data.materials.get(mat_name)
        nt = mat.node_tree if mat.use_nodes else None
        if nt is None or nt.nodes.get("mmd_shader") is not None:
            continue
        nodes = _wrappers(mat)
        if not nodes:
            outs = []
            for target in ("EEVEE", "CYCLES"):
                out = nt.get_output_node(target)
                if out is not None and out not in outs and out.inputs["Surface"].is_linked:
                    outs.append(out)
            for out in outs:
                link = out.inputs["Surface"].links[0]
                node = nt.nodes.new("ShaderNodeGroup")
                node.node_tree = _wrap_tree()
                node.name = node.label = WRAP
                node.location = (out.location.x, out.location.y - 160)
                nt.links.new(link.from_socket, node.inputs[0])
                nt.links.new(node.outputs[0], out.inputs["Surface"])
                nodes.append(node)
        if not nodes:
            continue
        sliders = []

        def var(n):
            if n not in sliders:
                sliders.append(n)
            return "s%d" % sliders.index(n)

        mult, add = "", ""
        for mode, alpha, terms in entries:
            used = [(n, f) for n, f in terms if key is not None and key.key_blocks.get(n) is not None]
            w = "+".join(var(n) if f == 1.0 else "%s*%g" % (var(n), f) for n, f in used) or "0"
            if mode == "MULT":
                mult += "*(1-(%s)*%g)" % (w, 1.0 - alpha)
            else:
                add += "+(%s)*%g" % (w, alpha)
        expr = "min(max(%g%s%s,0),1)" % (base, mult, add)
        for node in nodes:
            sock = node.inputs[1]
            sock.driver_remove("default_value")
            drv = sock.driver_add("default_value").driver
            drv.type = "SCRIPTED"
            for i, n in enumerate(sliders):
                v = drv.variables.new()
                v.name, v.type = "s%d" % i, "SINGLE_PROP"
                v.targets[0].id_type = "KEY"
                v.targets[0].id = key
                v.targets[0].data_path = 'key_blocks["%s"].value' % bpy.utils.escape_identifier(n)
            drv.expression = expr
        if mat.blend_method in ("OPAQUE", "CLIP"):
            mat[BLEND_PROP] = mat.blend_method
            mat.blend_method = "HASHED"
        done.append(mat.name)
    return done


def wrapped(root):
    """插着 WRAP 的材质名。"""
    return sorted({m.name for m in _model()(root).materials() if m is not None and _wrappers(m)})


def alpha_unwrap(root):
    """alpha_wrap 插的节点拿掉（原来的连线接回去），混合模式还原。返回拿掉了的材质名。"""
    done = []
    for mat in set(_model()(root).materials()):
        if mat is None:
            continue
        for node in _wrappers(mat):
            nt = node.id_data
            src = node.inputs[0].links[0].from_socket if node.inputs[0].is_linked else None
            targets = [link.to_socket for link in node.outputs[0].links]
            node.inputs[1].driver_remove("default_value")
            nt.nodes.remove(node)
            for sock in targets if src is not None else ():
                nt.links.new(src, sock)
            if mat.name not in done:
                done.append(mat.name)
        if BLEND_PROP in mat:
            mat.blend_method = mat[BLEND_PROP]
            del mat[BLEND_PROP]
    tree = bpy.data.node_groups.get(WRAP_TREE)
    if tree is not None and tree.users == 0:
        bpy.data.node_groups.remove(tree)
    return done


def pmx_scale(arm, model):
    """Blender units per PMX unit, from the bones the armature and the PMX share (mmd_tools keeps each bone's PMX
    name in mmd_bone.name_j): the median over bone pairs of their distance here over their distance in the PMX.
    The import scale is not stored anywhere, and mmd_tools' default differs between versions (0.08 or 1.0).  A few
    bones may sit elsewhere in the other PMX (a08 full vs nude: センター / グルーブ / 腰 follow the heels) - the median
    ignores them, a spread around the centre was 1.6e-4 off and lost the corners far from it.  None when < 3 bones
    match."""
    if arm is None:
        return None
    pmx_at = {b.name: b.location for b in model.bones if b.name}
    pairs = []
    for pb in arm.pose.bones:
        name = getattr(getattr(pb, "mmd_bone", None), "name_j", "") or pb.name
        if name in pmx_at:
            pairs.append((tuple(arm.matrix_world @ pb.bone.head_local), tuple(pmx_at[name])))
    if len(pairs) < 3:
        return None
    here = np.array([p[0] for p in pairs], dtype=np.float64)
    there = np.array([p[1] for p in pairs], dtype=np.float64)
    i, j = np.triu_indices(len(pairs), 1)
    if len(i) > 200000:
        pick = np.random.default_rng(0).choice(len(i), 200000, replace=False)
        i, j = i[pick], j[pick]
    d_there = np.linalg.norm(there[i] - there[j], axis=1)
    d_here = np.linalg.norm(here[i] - here[j], axis=1)
    ok = d_there > 1e-6 * max(float(d_there.max()), 1e-12)
    return float(np.median(d_here[ok] / d_there[ok])) if ok.any() else None


def normals_from_pmx(obj, path, scale=None, arm=None):
    """obj's normals from another PMX of the same body (the nude version of a full model): each corner takes the
    normal of the PMX vertex at the same place (PMX units x scale) with the same UV.  scale None = from the bones
    (pmx_scale), else 0.08.  Returns (corners matched, scale used)."""
    from mmd_tools.core import pmx as pmx_core
    model = pmx_core.load(path)
    if not scale:
        scale = pmx_scale(arm, model) or 0.08
    pco = np.array([v.co for v in model.vertices], dtype=np.float64)[:, [0, 2, 1]] * scale    # mmd_tools: .xzy
    pno = np.array([v.normal for v in model.vertices], dtype=np.float64)[:, [0, 2, 1]]
    puv = np.array([v.uv for v in model.vertices], dtype=np.float64)
    puv[:, 1] = 1.0 - puv[:, 1]
    me = obj.data
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    co = world_co(obj)[lv]
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    tol = 2e-4 * max(scale / 0.08, 1e-6)
    cells = {}
    for j, key in enumerate(map(tuple, np.floor(pco / tol).astype(np.int64))):
        cells.setdefault(key, []).append(j)
    me.calc_normals_split()
    out = np.empty(len(me.loops) * 3, dtype=np.float32)
    me.loops.foreach_get("normal", out)
    out = out.reshape(-1, 3)
    near = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)]
    hit = 0
    for i, (c, u) in enumerate(zip(co, uv)):
        x, y, z = np.floor(c / tol).astype(np.int64)
        best, bd = -1, tol
        for dx, dy, dz in near:
            for j in cells.get((x + dx, y + dy, z + dz), ()):
                if abs(puv[j, 0] - u[0]) > 1e-3 or abs(puv[j, 1] - u[1]) > 1e-3:
                    continue
                d = float(np.linalg.norm(pco[j] - c))
                if d <= bd:
                    best, bd = j, d
        if best >= 0:
            out[i] = pno[best]
            hit += 1
    me.use_auto_smooth = True
    me.normals_split_custom_set(out.tolist())
    return hit, scale


def make(root, outfit, opts=None):
    """root 这个模型加上爆衣（先撤掉上一次的）。outfit：衣服的材质名。返回报告。"""
    o = dict(DEFAULTS, **(opts or {}))
    if imported_burst(root):
        raise ValueError("这个模型已经带着爆衣表情（导入的爆衣 PMX）：直接预览、导出 VMD 就行；"
                         "要换设置重做，请导入没做过爆衣的 PMX")
    remove(root)
    rig, placeholder, bound = _sliders(root)
    if bound:
        rig.morph_slider.unbind()
    arm, meshes = parts(root)
    outfit = set(outfit)
    if not outfit:
        raise ValueError("还没选衣服的材质")
    if not any(s.material and s.material.name in outfit for m in meshes for s in m.material_slots):
        raise ValueError("模型上没有这些材质：%s" % "、".join(sorted(outfit)))
    rec = {"style": o["style"], "objects": [], "materials": [], "created_morphs": [], "vertex_morphs": [],
           "swapped": False}
    co_all = np.concatenate([world_co(m) for m in meshes])
    floor, height = float(co_all[:, 2].min()), float(co_all[:, 2].max() - co_all[:, 2].min())
    swap = {m.name: body_slots(m, outfit) for m in meshes} if o["swap"] else {}
    swap = {k: v for k, v in swap.items() if v}
    report = {"floor": round(floor, 4), "height": round(height, 4), "fragments": 0, "objects": {}}

    if o["style"] == "SHARDS":
        pts, tris, offset = [], [], 0              # 碎片下面的身体：有 裸体形状 时用它移动的身体，否则不是衣服的面
        for mesh in meshes:
            body = swap.get(mesh.name)
            mesh.data.calc_loop_triangles()
            co = world_co(mesh)
            sel = [t for t in mesh.data.loop_triangles
                   if (t.material_index in body if body else
                       mesh.material_slots[t.material_index].material is not None
                       and mesh.material_slots[t.material_index].material.name not in outfit)]
            if sel:
                pts.append(co)
                tris += [tuple(i + offset for i in t.vertices) for t in sel]
                offset += len(co)
        tree = shards.surface(np.concatenate(pts), tris) if pts else None
        mapping = shards.core_map(arm, physics_bones(root)) if arm is not None else None
        entries = []
        for mesh in meshes:
            slots = [i for i, s in enumerate(mesh.material_slots) if s.material and s.material.name in outfit]
            if not slots:
                continue
            copy = split_copy(mesh, slots, mesh.name + SHARD_SUFFIX)
            for slot in copy.material_slots:
                orig = slot.material
                slot.material = copy_material(orig, SHARD_SUFFIX, alpha=0.0)
                entries.append((slot.material, "ADD", copy.data.name, orig.mmd_material.alpha,
                                orig.mmd_material.edge_color[3]))
                rec["materials"].append(slot.material.name)
            copy[SHARD_TAG] = 1
            rep = shards.shatter(copy, tree, floor, height, o, mapping)
            report["objects"][copy.name] = rep
            report["fragments"] += rep["fragments"]
            rec["objects"].append(copy.name)
        vm = root.mmd_root.vertex_morphs
        for name in (shards.THROW_KEY, shards.FALL_KEY):
            if vm.get(name) is None:
                m = vm.add()
                m.name = name
                m.category = "OTHER"
                rec["vertex_morphs"].append(name)
            display(root, name, "vertex_morphs")
        material_morph(root, vmd.SHARDS, entries)
        rec["created_morphs"].append(["material_morphs", vmd.SHARDS])
        display(root, vmd.SHARDS, "material_morphs")

    if root.mmd_root.material_morphs.get(vmd.OUTFIT) is None:
        entries = [(s.material, "MULT", m.data.name, 0.0, 0.0) for m in meshes for s in m.material_slots
                   if s.material and s.material.name in outfit]
        material_morph(root, vmd.OUTFIT, entries)
        rec["created_morphs"].append(["material_morphs", vmd.OUTFIT])
        display(root, vmd.OUTFIT, "material_morphs")

    if swap:
        entries = []
        for mesh in meshes:
            if mesh.name not in swap:
                continue
            copy, pairs = nude_copy(mesh, swap[mesh.name])
            rec["objects"].append(copy.name)
            info = report.setdefault("nude_copies", {}).setdefault(copy.name, {})
            info["flipped_loops_smoothed"] = json.loads(copy[NUDE_TAG])["smooth_loops"]
            if o.get("nude_pmx"):
                hit, scale = normals_from_pmx(copy, o["nude_pmx"], o.get("scale"), arm)
                info["normals_from_pmx"], info["pmx_scale"] = hit, round(scale, 5)
                info["loops"] = len(copy.data.loops)
            for orig, new in pairs:
                entries.append((orig, "MULT", mesh.data.name, 0.0, 0.0))
                entries.append((new, "ADD", copy.data.name, orig.mmd_material.alpha, orig.mmd_material.edge_color[3]))
                rec["materials"].append(new.name)
        rec["body_vertex_morph_index"] = root.mmd_root.vertex_morphs.find(vmd.BODY)
        _remove_named(root.mmd_root.vertex_morphs, vmd.BODY)
        material_morph(root, vmd.BODY, entries)
        retype(root, vmd.BODY, "vertex_morphs", "material_morphs")
        display(root, vmd.BODY, "material_morphs")
        rec["swapped"] = True
        report["swapped_bodies"] = sorted(swap)

    body_type = "material_morphs" if rec["swapped"] else (
        "vertex_morphs" if any(body_key(m) for m in meshes) else None)
    group = root.mmd_root.group_morphs.get(vmd.GROUP)
    if group is None:
        group = root.mmd_root.group_morphs.add()
        group.name = vmd.GROUP
        group.category = "OTHER"
        rec["created_morphs"].append(["group_morphs", vmd.GROUP])
        display(root, vmd.GROUP, "group_morphs")
    have = {(d.name, d.morph_type) for d in group.data}
    for name, kind in ((vmd.OUTFIT, "material_morphs"), (vmd.BODY, body_type)):
        if kind and (name, kind) not in have:
            d = group.data.add()
            d.name, d.morph_type, d.factor = name, kind, 1.0
            rec.setdefault("group_entries", []).append([name, kind])
    root[TAG] = json.dumps(dict(rec, opts=o), ensure_ascii=False)
    if placeholder is not None:
        _rebuild_sliders(rig, bound)
    report["alpha_wrapped"] = alpha_wrap(root)
    return report


def remove(root):
    """撤掉 make() 加的东西。返回做了什么。"""
    rec = _record(root)
    if not rec:
        return []
    unwrapped = alpha_unwrap(root)
    done = ["%d 个材质的透明节点拿掉" % len(unwrapped)] if unwrapped else []
    rig, placeholder, bound = _sliders(root)
    if bound:
        rig.morph_slider.unbind()
    for name in rec.get("objects", []):
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if obj.get(NUDE_TAG):                     # 裸体形状 形状键从脱衣身体还原
            info = json.loads(obj[NUDE_TAG])
            src = bpy.data.objects.get(info.get("source", ""))
            if src is not None and body_key(src) is None:
                idx = np.empty(len(obj.data.vertices), dtype=np.int32)
                obj.data.attributes[SRC_ATTR].data.foreach_get("value", idx)
                co = np.empty(len(obj.data.vertices) * 3)
                obj.data.vertices.foreach_get("co", co)
                if src.data.shape_keys is None:
                    src.shape_key_add(name="Basis", from_mix=False)
                kb = src.shape_key_add(name=vmd.BODY, from_mix=False)
                full = key_co(kb)
                full[idx] = co.reshape(-1, 3)
                kb.data.foreach_set("co", full.astype(np.float32).ravel())
                kb.value = 0.0
                done.append("%s 的裸体形状还原" % src.name)
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
        done.append("删掉 %s" % name)
    for name in rec.get("materials", []):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
    mm = root.mmd_root
    if rec.get("swapped"):
        _remove_named(mm.material_morphs, vmd.BODY)
        display(root, vmd.BODY, "material_morphs", add=False)
        if mm.vertex_morphs.get(vmd.BODY) is None:
            m = mm.vertex_morphs.add()
            m.name = vmd.BODY
            m.category = "OTHER"
            at = rec.get("body_vertex_morph_index", -1)
            if 0 <= at < len(mm.vertex_morphs) - 1:       # back in its place: the PMX's morph order follows this list
                mm.vertex_morphs.move(len(mm.vertex_morphs) - 1, at)
        retype(root, vmd.BODY, "material_morphs", "vertex_morphs")
        display(root, vmd.BODY, "vertex_morphs")
    for kind, name in rec.get("created_morphs", []):
        _remove_named(getattr(mm, kind), name)
        display(root, name, kind, add=False)
        for group in mm.group_morphs:
            for i in reversed(range(len(group.data))):
                if group.data[i].name == name and group.data[i].morph_type == kind:
                    group.data.remove(i)
    for name in rec.get("vertex_morphs", []):
        _remove_named(mm.vertex_morphs, name)
        display(root, name, "vertex_morphs", add=False)
    group = mm.group_morphs.get(vmd.GROUP)
    for name, kind in rec.get("group_entries", []):
        if group is None:
            break
        for i in reversed(range(len(group.data))):
            if group.data[i].name == name and group.data[i].morph_type == kind:
                group.data.remove(i)
    del root[TAG]
    done.append("表情还原")
    if placeholder is not None:
        _rebuild_sliders(rig, bound)
    return done


def timing(opts):
    """vmd.burst_keys 的参数：面板上的「方式」决定碎片飞散还是直接消失。"""
    o = dict(vmd.DEFAULTS, **(opts or {}))
    if "style" in o:
        o["shards"] = o["style"] == "SHARDS"
    return {k: o[k] for k in vmd.DEFAULTS}


def preview(root, opts):
    """在时间轴上打上爆衣的表情帧（表情滑块，直线插值），播放就能看。返回 (第一帧, 最后一帧)。"""
    t = timing(opts)
    keys = vmd.burst_keys(**t)
    rig = _model()(root)
    _rebuild_sliders(rig)
    clear_preview(root)
    placeholder = rig.morph_slider.placeholder()
    sk = placeholder.data.shape_keys
    for name, frame, weight in keys:
        kb = sk.key_blocks.get(name)
        if kb is None:
            continue
        kb.value = weight
        kb.keyframe_insert("value", frame=frame)
    for fc in getattr(getattr(sk.animation_data, "action", None), "fcurves", ()):
        if any(fc.data_path == 'key_blocks["%s"].value' % n for n in {k[0] for k in keys}):
            for p in fc.keyframe_points:
                p.interpolation = "LINEAR"
    first, last = min(k[1] for k in keys), max(k[1] for k in keys)
    scene = bpy.context.scene
    scene.frame_end = max(scene.frame_end, last + 30)
    alpha_wrap(root)
    return first, last


def clear_preview(root):
    """删掉预览打的表情帧；导入的爆衣 PMX 上预览插的透明节点也拿掉（生成的那些归「撤掉」管）。"""
    if not has_burst(root):
        alpha_unwrap(root)
    rig = _model()(root)
    placeholder = rig.morph_slider.placeholder()
    if placeholder is None or placeholder.data.shape_keys is None:
        return 0
    sk = placeholder.data.shape_keys
    action = getattr(sk.animation_data, "action", None)
    gone = 0
    if action is not None:
        names = {vmd.OUTFIT, vmd.SHARDS, vmd.THROW, vmd.FALL, vmd.BODY}
        for fc in list(action.fcurves):
            if any(fc.data_path == 'key_blocks["%s"].value' % n for n in names):
                action.fcurves.remove(fc)
                gone += 1
    for name in (vmd.OUTFIT, vmd.SHARDS, vmd.THROW, vmd.FALL, vmd.BODY):
        kb = sk.key_blocks.get(name)
        if kb is not None:
            kb.value = 0.0
    return gone


def export_vmd(path, opts, merge_with="", model=""):
    keys = vmd.burst_keys(**timing(opts))
    if merge_with:
        replaced = vmd.merge(merge_with, path, keys)
        return "%d 个表情帧合进 %s（替换旧帧 %d 个）" % (len(keys), merge_with, replaced)
    vmd.write_morph_vmd(path, keys, model)
    return "%d 个表情帧" % len(keys)
