# -*- coding: utf-8 -*-
"""布料撕裂的实际工作（不含界面），按 B 站「blender-布料模拟撕裂效果」（峰峰居士，BV1Zk4y1x7Eo）的做法：

  布料 1      先模拟一块完整的布被拉扯（固定组 = 钩挂的顶点）
  几何节点 1  按边折痕把「裂缝」边拆开（Split Edges），再把固定组改写成
              max(原固定组, 松开带)：松开带是一条随帧移动的过渡带，从「上」往「下」把权重从 1 变成 0
  布料 2      复制布料 1 放到几何节点下面，固定组同名：权重 1 的地方完全跟着布料 1 走，
              过渡带扫过的地方就沿裂缝散开 = 撕裂
  几何节点 2  按距离合并（只合并裂缝顶点）：还没撕开的裂缝合回去，不露缝

视频里松开带是「UV 的 Y + 关键帧偏移 → 颜色渐变」；这里用场景帧算（开始帧 / 结束帧 / 过渡宽度），
不用打关键帧，坐标先归一化到 0..1，所以用 UV 或物体坐标都行。
Blender 3.6 / 4.x 通用：边折痕属性 3.x 叫 crease、4.0 起叫 crease_edge；节点组接口 4.0 起是 interface。
"""
import heapq
import math
import random

import bmesh
import bpy
from mathutils import Vector

B4 = bpy.app.version >= (4, 0, 0)
CREASE = "crease_edge" if B4 else "crease"
MOD_SPLIT, MOD_CLOTH, MOD_MERGE = "CT 拆缝", "CT 布料撕裂", "CT 合缝"
OUT_GROUP = "CT_Pin"                 # 原布料没有固定组时，松开带写进这个新顶点组
AXES = {"UV_V": ("uv", 1), "UV_U": ("uv", 0), "X": ("pos", 0), "Y": ("pos", 1), "Z": ("pos", 2)}


# --- 节点组 ---------------------------------------------------------------------------------------------
def _socket(tree, in_out, name, socket_type, default=None, lo=None, hi=None):
    if hasattr(tree, "interface"):                       # 4.0+
        sock = tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    else:
        sock = (tree.inputs if in_out == "INPUT" else tree.outputs).new(socket_type, name)
    if default is not None and hasattr(sock, "default_value"):
        sock.default_value = default
    if lo is not None and hasattr(sock, "min_value"):
        sock.min_value = lo
    if hi is not None and hasattr(sock, "max_value"):
        sock.max_value = hi
    return sock


def _out(node, name):
    """3.x 的「已命名属性」等节点每种类型各有一个同名插口，只有当前类型的那个是启用的。"""
    return next(s for s in node.outputs if s.name == name and s.enabled)


def _in(node, name):
    return next(s for s in node.inputs if s.name == name and s.enabled)


def _named(nodes, name, data_type="FLOAT", x=0, y=0):
    node = nodes.new("GeometryNodeInputNamedAttribute")
    node.data_type = data_type
    node.inputs["Name"].default_value = name
    node.location = (x, y)
    return node


def _math(nodes, op, x, y, a=None, b=None, c=None):
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    node.location = (x, y)
    for i, v in enumerate((a, b, c)):
        if v is not None:
            node.inputs[i].default_value = v
    return node


def _map_range(nodes, x, y):
    node = nodes.new("ShaderNodeMapRange")
    node.data_type = "FLOAT"
    node.clamp = True
    node.location = (x, y)
    return node                                           # inputs 0..4: Value, From Min/Max, To Min/Max


def split_tree_name(obj):
    return "CT_TearSplit_%s" % obj.name


def build_split_tree(obj, pin_group, out_group, axis="UV_V", invert=False, uv_name="UVMap"):
    """几何节点 1：拆开折痕边 + 把松开带写进 out_group。时间参数做成修改器输入（可动画、可直接调）。"""
    old = bpy.data.node_groups.get(split_tree_name(obj))
    if old is not None:
        bpy.data.node_groups.remove(old)
    tree = bpy.data.node_groups.new(split_tree_name(obj), "GeometryNodeTree")
    _socket(tree, "INPUT", "Geometry", "NodeSocketGeometry")
    s_start = _socket(tree, "INPUT", "开始帧", "NodeSocketFloat", 120.0)
    s_end = _socket(tree, "INPUT", "结束帧", "NodeSocketFloat", 170.0)
    s_width = _socket(tree, "INPUT", "过渡宽度", "NodeSocketFloat", 0.05, 0.001, 1.0)
    _socket(tree, "OUTPUT", "Geometry", "NodeSocketGeometry")
    n, link = tree.nodes, tree.links.new

    gin = n.new("NodeGroupInput"); gin.location = (-1400, 0)
    gout = n.new("NodeGroupOutput"); gout.location = (900, 0)

    # 拆开裂缝：Split Edges，选择 = 边折痕
    crease = _named(n, CREASE, "FLOAT", -1150, -150)
    split = n.new("GeometryNodeSplitEdges"); split.location = (-900, 0)
    link(gin.outputs[0], split.inputs["Mesh"])
    link(_out(crease, "Attribute"), split.inputs["Selection"])

    # 坐标：UV 或物体坐标的一个分量，用整块布的最小 / 最大值归一化到 0..1（invert 时反过来）
    source, component = AXES[axis]
    if source == "uv":
        coord_src = _named(n, uv_name, "FLOAT_VECTOR", -1150, -450)
        vec = _out(coord_src, "Attribute")
    else:
        coord_src = n.new("GeometryNodeInputPosition"); coord_src.location = (-1150, -450)
        vec = coord_src.outputs["Position"]
    sep = n.new("ShaderNodeSeparateXYZ"); sep.location = (-950, -450)
    link(vec, sep.inputs[0])
    coord = sep.outputs[component]
    stats = n.new("GeometryNodeAttributeStatistic"); stats.location = (-700, -300)
    stats.data_type, stats.domain = "FLOAT", "POINT"
    link(split.outputs["Mesh"], stats.inputs["Geometry"])
    link(coord, _in(stats, "Attribute"))
    norm = _map_range(n, -450, -450)
    link(coord, norm.inputs[0])
    link(stats.outputs["Min"], norm.inputs[1])
    link(stats.outputs["Max"], norm.inputs[2])
    norm.inputs[3].default_value, norm.inputs[4].default_value = (1.0, 0.0) if invert else (0.0, 1.0)

    # 松开带：t = 帧在 [开始, 结束] 里的进度；前沿 s 从 1+w 走到 -w；权重 = 坐标在 [s, s-w] 里的位置（1 = 固定）
    time = n.new("GeometryNodeInputSceneTime"); time.location = (-950, -800)
    prog = _map_range(n, -700, -800)
    link(time.outputs["Frame"], prog.inputs[0])
    link(gin.outputs[s_start.name], prog.inputs[1])
    link(gin.outputs[s_end.name], prog.inputs[2])
    k = _math(n, "MULTIPLY_ADD", -700, -1050, b=2.0, c=1.0)          # 1 + 2w
    link(gin.outputs[s_width.name], k.inputs[0])
    tk = _math(n, "MULTIPLY", -450, -900)
    link(prog.outputs[0], tk.inputs[0]); link(k.outputs[0], tk.inputs[1])
    one_w = _math(n, "ADD", -450, -1100, b=1.0)                       # 1 + w
    link(gin.outputs[s_width.name], one_w.inputs[0])
    front = _math(n, "SUBTRACT", -250, -950)                          # s = (1 + w) - t (1 + 2w)
    link(one_w.outputs[0], front.inputs[0]); link(tk.outputs[0], front.inputs[1])
    back = _math(n, "SUBTRACT", -250, -1150)                          # s - w
    link(front.outputs[0], back.inputs[0]); link(gin.outputs[s_width.name], back.inputs[1])
    band = _map_range(n, 0, -650)
    link(norm.outputs[0], band.inputs[0])
    link(front.outputs[0], band.inputs[1]); link(back.outputs[0], band.inputs[2])
    band.inputs[3].default_value, band.inputs[4].default_value = 0.0, 1.0

    # 固定组 = max(原固定组, 松开带)，写回顶点组（同名顶点组存在时，几何节点写的就是顶点组）
    pin = _named(n, pin_group, "FLOAT", 0, -350) if pin_group else None
    weight = band.outputs[0]
    if pin is not None:
        mx = _math(n, "MAXIMUM", 250, -400)
        link(_out(pin, "Attribute"), mx.inputs[0]); link(band.outputs[0], mx.inputs[1])
        weight = mx.outputs[0]
    store = n.new("GeometryNodeStoreNamedAttribute"); store.location = (550, 0)
    store.data_type, store.domain = "FLOAT", "POINT"
    link(split.outputs["Mesh"], store.inputs["Geometry"])
    store.inputs["Name"].default_value = out_group
    link(weight, _in(store, "Value"))
    link(store.outputs["Geometry"], gout.inputs[0])
    return tree


def build_merge_tree():
    """几何节点 2：只在裂缝顶点上按距离合并，没撕开的缝合回去。几件衣服共用一个组：已有就直接用
    （不能删了重建——别的衣服的合缝修改器正连着它，删掉就失效了）。"""
    name = "CT_TearMerge"
    old = bpy.data.node_groups.get(name)
    if old is not None and old.bl_idname == "GeometryNodeTree" and any(n.type == "MERGE_BY_DISTANCE" for n in old.nodes):
        return old
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    _socket(tree, "INPUT", "Geometry", "NodeSocketGeometry")
    s_dist = _socket(tree, "INPUT", "合并距离", "NodeSocketFloat", 0.001, 0.0, 1.0)
    _socket(tree, "OUTPUT", "Geometry", "NodeSocketGeometry")
    n, link = tree.nodes, tree.links.new
    gin = n.new("NodeGroupInput"); gin.location = (-600, 0)
    gout = n.new("NodeGroupOutput"); gout.location = (300, 0)
    crease = _named(n, CREASE, "FLOAT", -600, -200)
    merge = n.new("GeometryNodeMergeByDistance"); merge.location = (0, 0)
    link(gin.outputs[0], merge.inputs["Geometry"])
    link(_out(crease, "Attribute"), merge.inputs["Selection"])
    link(gin.outputs[s_dist.name], merge.inputs["Distance"])
    link(merge.outputs["Geometry"], gout.inputs[0])
    return tree


def socket_id(tree, name):
    """修改器上这个输入的键（3.x Input_N，4.x Socket_N）。"""
    if hasattr(tree, "interface"):
        return next(s.identifier for s in tree.interface.items_tree
                    if getattr(s, "in_out", "") == "INPUT" and s.name == name)
    return tree.inputs[name].identifier


# --- 修改器栈 --------------------------------------------------------------------------------------------
def tear_modifiers(obj):
    m = obj.modifiers
    return m.get(MOD_SPLIT), m.get(MOD_CLOTH), m.get(MOD_MERGE)


def source_cloth(obj):
    """撕裂前的那个布料修改器（不是本插件复制出来的）。"""
    return next((m for m in obj.modifiers if m.type == "CLOTH" and m.name != MOD_CLOTH), None)


def _move(obj, mod, index):
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=index)


def _copy_cloth(obj, cloth):
    """布料修改器一个物体只能「添加」一个，但能复制（视频里的 Shift+D）。"""
    before = {m.name for m in obj.modifiers}
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_copy(modifier=cloth.name)
    new = next(m for m in obj.modifiers if m.name not in before)
    new.name = MOD_CLOTH
    return new


def setup_tear(obj, axis="UV_V", invert=False, start=120.0, end=170.0, width=0.05, merge_distance=0.001,
               keep_group=None):
    """在 obj 已有布料修改器的基础上生成 / 更新整套撕裂设置。返回说明文字列表。

    keep_group：撕开以后仍固定的顶点组。None = 和布料 1 的固定组一样（视频的做法）；
    "" = 没有，撕开的全部松开；组名 = 用这个组。和布料 1 的固定组不同时，松开带写进单独的 CT_Pin
    （衣服：布料 1 全部固定 = 完全跟着身体动，撕开后只有保留组还挂在身上）。"""
    if obj is None or obj.type != "MESH":
        raise RuntimeError("先选中一个网格物体")
    cloth = source_cloth(obj)
    if cloth is None:
        raise RuntimeError("这个物体还没有布料修改器（先加布料，设好固定组和拉扯动画）")
    if seam_count(obj) == 0:
        raise RuntimeError("还没有裂缝：编辑模式选一些边点「设为裂缝」，或用「随机生成裂缝」")
    uv_name = ""
    if AXES[axis][0] == "uv":
        if not obj.data.uv_layers:
            raise RuntimeError("网格没有 UV，方向请改用 X / Y / Z")
        uv_name = (obj.data.uv_layers.active or obj.data.uv_layers[0]).name
    notes = []
    cloth_pin = cloth.settings.vertex_group_mass
    pin_group = cloth_pin if keep_group is None else keep_group
    if pin_group and pin_group not in obj.vertex_groups:
        raise RuntimeError("找不到保留组「%s」" % pin_group)
    out_group = cloth_pin if (pin_group == cloth_pin and cloth_pin) else OUT_GROUP
    if out_group == OUT_GROUP and OUT_GROUP not in obj.vertex_groups:
        obj.vertex_groups.new(name=OUT_GROUP)
    if out_group == OUT_GROUP:
        notes.append("松开带写进顶点组 %s（保留组：%s）" % (OUT_GROUP, pin_group or "无"))

    split_mod, cloth2, merge_mod = tear_modifiers(obj)
    tree = build_split_tree(obj, pin_group, out_group, axis, invert, uv_name or "UVMap")
    if split_mod is None:
        split_mod = obj.modifiers.new(MOD_SPLIT, "NODES")
    split_mod.node_group = tree
    split_mod[socket_id(tree, "开始帧")] = float(start)
    split_mod[socket_id(tree, "结束帧")] = float(end)
    split_mod[socket_id(tree, "过渡宽度")] = float(width)

    if cloth2 is None:
        cloth2 = _copy_cloth(obj, cloth)
    cloth2.settings.vertex_group_mass = out_group
    cloth2.point_cache.frame_start = cloth.point_cache.frame_start
    cloth2.point_cache.frame_end = cloth.point_cache.frame_end

    merge_tree = build_merge_tree()
    if merge_mod is None:
        merge_mod = obj.modifiers.new(MOD_MERGE, "NODES")
    merge_mod.node_group = merge_tree
    merge_mod[socket_id(merge_tree, "合并距离")] = float(merge_distance)

    # 最终顺序：（布料前的修改器）布料 → 拆缝 → 布料 2 →（布料后原有的修改器）→ 合缝
    ours = {split_mod.name, cloth2.name, merge_mod.name}
    rest = [m for m in obj.modifiers if m.name not in ours]
    at = rest.index(cloth)
    order = rest[:at + 1] + [split_mod, cloth2] + rest[at + 1:] + [merge_mod]
    for index, mod in enumerate(order):
        _move(obj, mod, index)
    obj.update_tag()
    notes.append("修改器顺序：%s" % " → ".join(m.name for m in obj.modifiers))
    notes.append("裂缝 %d 条边；第 %g–%g 帧从%s往%s松开" % (seam_count(obj), start, end,
                                                      "下" if invert else "上", "上" if invert else "下"))
    return notes


def remove_tear(obj):
    removed = []
    for mod in tear_modifiers(obj):
        if mod is not None:
            removed.append(mod.name)
            obj.modifiers.remove(mod)
    tree = bpy.data.node_groups.get(split_tree_name(obj))
    if tree is not None and tree.users == 0:
        bpy.data.node_groups.remove(tree)
    return removed


# --- 裂缝（边折痕） ----------------------------------------------------------------------------------------
def _crease_layer(bm, create=True):
    if B4:
        layer = bm.edges.layers.float.get(CREASE)
        return layer if layer is not None or not create else bm.edges.layers.float.new(CREASE)
    return bm.edges.layers.crease.verify() if create else bm.edges.layers.crease.active


def _bm_of(obj):
    if obj.mode == "EDIT":
        return bmesh.from_edit_mesh(obj.data), True
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    return bm, False


def _bm_done(obj, bm, edit):
    if edit:
        bmesh.update_edit_mesh(obj.data)
    else:
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()


def mark_seams(obj, value=1.0, only_selected=True):
    bm, edit = _bm_of(obj)
    layer = _crease_layer(bm)
    count = 0
    for e in bm.edges:
        if e.select or not only_selected:
            e[layer] = value
            count += 1
    _bm_done(obj, bm, edit)
    return count


def seam_count(obj):
    if obj is None or obj.type != "MESH":
        return 0
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        layer = _crease_layer(bm, create=False)
        return sum(1 for e in bm.edges if layer is not None and e[layer] > 0.5)
    attr = obj.data.attributes.get(CREASE)
    if attr is not None:
        return sum(1 for v in attr.data if v.value > 0.5)
    if not B4:
        return sum(1 for e in obj.data.edges if e.crease > 0.5)
    return 0


def _islands(bm):
    """互不相连的几块网格（顶点列表）。衣服常常是好几块拼的：Fiona 的连衣裙有 59 块。"""
    seen, out = set(), []
    for v0 in bm.verts:
        if v0.index in seen:
            continue
        seen.add(v0.index)
        stack, members = [v0], []
        while stack:
            cur = stack.pop()
            members.append(cur)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        out.append(members)
    return out


def _extent(verts):
    return max((max(v.co[i] for v in verts) - min(v.co[i] for v in verts)) for i in range(3))


def random_cracks(obj, count=4, seed=1, jitter=0.6, through=None, partial=False):
    """count 条锯齿状裂缝：边长加随机扰动后的最短路径。默认从布边到布边（贯穿，会撕成几块）；
    partial 时从布边撕进布里 30%–60%（不贯穿，撕出毛边和裂口）。网格由几块拼成时，每条裂缝都在
    同一块里，块越大分到的越多（不到最大一块 5% 的小块不撕）。
    through=(起点坐标, 终点坐标) 时第一条裂缝贯穿这两点附近（示例场景里用来劈开两个钩挂点之间）。"""
    rng = random.Random(seed)
    bm, edit = _bm_of(obj)
    bm.verts.ensure_lookup_table()
    layer = _crease_layer(bm)
    boundary = [v for v in bm.verts if v.is_boundary]
    islands = [isl for isl in _islands(bm) if sum(1 for v in isl if v.is_boundary) >= 4]
    if not islands:
        _bm_done(obj, bm, edit)
        raise RuntimeError("网格没有开放的边界（裂缝要从布边开始），或面数太少")
    biggest = max(len(isl) for isl in islands)
    islands = [isl for isl in islands if len(isl) >= max(12, 0.05 * biggest)]
    weights = {e.index: e.calc_length() * (1.0 + jitter * rng.random() * 2.0) for e in bm.edges}
    made = 0

    def path(a, b):
        dist, prev, todo = {a.index: 0.0}, {}, [(0.0, a.index)]
        while todo:
            d, i = heapq.heappop(todo)
            if i == b.index:
                break
            if d > dist.get(i, math.inf):
                continue
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                nd = d + weights[e.index]
                if nd < dist.get(j, math.inf):
                    dist[j], prev[j] = nd, (i, e)
                    heapq.heappush(todo, (nd, j))
        edges, i = [], b.index
        while i in prev:
            i, e = prev[i]
            edges.append(e)
        return edges

    def nearest(co):
        return min(boundary, key=lambda v: (v.co - Vector(co)).length)

    for n in range(count):
        if n == 0 and through:
            a, b = nearest(through[0]), nearest(through[1])
        else:
            island = rng.choices(islands, weights=[len(isl) for isl in islands])[0]
            edge_verts = [v for v in island if v.is_boundary]
            inner = [v for v in island if not v.is_boundary]
            size = _extent(island)
            if partial and inner:
                a = rng.choice(edge_verts)
                far = [v for v in inner if 0.3 * size < (v.co - a.co).length < 0.6 * size] or inner
                b = rng.choice(far)
            else:
                for _ in range(50):
                    a, b = rng.sample(edge_verts, 2)
                    if (a.co - b.co).length > 0.45 * size:
                        break
        marked = 0
        for e in path(a, b):
            if not e.is_boundary:
                e[layer] = 1.0
                marked += 1
        made += marked > 0
    _bm_done(obj, bm, edit)
    return made


# --- 网格准备 / 钩挂 / 固定组 ----------------------------------------------------------------------------
def subdivide_poke(obj, cuts=20, poke=True):
    """视频的做法：细分 20 刀，再 Ctrl+F 戳孔面（每格 4 个三角，撕开时边缘更碎）。"""
    bm, edit = _bm_of(obj)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    if poke:
        bmesh.ops.poke(bm, faces=bm.faces[:])
    _bm_done(obj, bm, edit)


def hook_vertex(obj, index, name):
    """给一个顶点挂一个新空物体（等于 Ctrl+H 钩挂到新物体），返回空物体。"""
    co = obj.matrix_world @ obj.data.vertices[index].co
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type, empty.empty_display_size = "PLAIN_AXES", 0.25
    empty.location = co
    for coll in obj.users_collection:
        coll.objects.link(empty)
        break
    bpy.context.view_layer.update()
    hook = obj.modifiers.new("Hook-%s" % name, "HOOK")
    hook.object = empty
    hook.vertex_indices_set([index])
    hook.center = obj.data.vertices[index].co
    hook.matrix_inverse = (obj.matrix_world.inverted() @ empty.matrix_world).inverted()
    first_cloth = next((i for i, m in enumerate(obj.modifiers) if m.type == "CLOTH"), None)
    if first_cloth is not None and first_cloth < list(obj.modifiers).index(hook):   # 钩挂要在布料前面
        _move(obj, hook, first_cloth)
    return empty


def pin_vertices(obj, indices, group="Group"):
    vg = obj.vertex_groups.get(group) or obj.vertex_groups.new(name=group)
    vg.add(list(indices), 1.0, "REPLACE")
    return vg


FOLLOW_GROUP = "CT_Follow"


FLOOR = "CT_地面碰撞"


def add_floor(z, size=20.0):
    """脚底一块不渲染的碰撞平面，撕下来的碎片落在地上，而不是一直往下掉。已有就只挪高度。"""
    floor = bpy.data.objects.get(FLOOR)
    if floor is None:
        mesh = bpy.data.meshes.new(FLOOR)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2.0)
        bm.to_mesh(mesh)
        bm.free()
        floor = bpy.data.objects.new(FLOOR, mesh)
        bpy.context.scene.collection.objects.link(floor)
        floor.modifiers.new("Collision", "COLLISION")
        floor.display_type = "WIRE"
        floor.hide_render = True
    floor.location = (0.0, 0.0, z)
    return floor


def follow_body(garments, add_collision=True, floor=True):
    """撕衣服的准备（garments：一件或几件衣服，各是带骨架修改器的单独网格）。布料 1 全部固定（顶点组
    CT_Follow 全为 1），所以撕开前衣服完全跟着身体动画走、不模拟也不穿模；关掉自碰撞。和衣服重叠的身体
    网格加碰撞（body_meshes，不含这几件衣服本身），撕下来的布落在身上滑下去；floor 时脚底再放一块地面碰撞。"""
    garments = [g for g in (garments if isinstance(garments, (list, tuple)) else [garments])
                if g is not None and g.type == "MESH"]
    if not garments:
        raise RuntimeError("先选中衣服网格")
    notes, colliders = [], []
    for obj in garments:
        notes += _follow_one(obj)
        arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        if arm_mod is not None and add_collision:
            colliders += [b for b in body_meshes(obj, arm_mod.object) if b not in garments and b not in colliders]
    for body in colliders:
        if not any(m.type == "COLLISION" for m in body.modifiers):
            body.modifiers.new("Collision", "COLLISION")
    if colliders:
        notes.append("加了碰撞：%s" % "、".join(b.name for b in colliders))
    arm_mod = next((m for g in garments for m in g.modifiers if m.type == "ARMATURE" and m.object), None)
    if floor and arm_mod is not None:
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in garments
                  and any(m.type == "ARMATURE" and m.object is arm_mod.object for m in o.modifiers)]
        if meshes:
            low = min((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
            add_floor(low)
            notes.append("脚底加了地面碰撞「%s」（不渲染）" % FLOOR)
    return notes


def _follow_one(obj):
    arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
    notes = []
    pin_vertices(obj, range(len(obj.data.vertices)), FOLLOW_GROUP)
    cloth = source_cloth(obj)
    if cloth is None:
        cloth = obj.modifiers.new("Cloth", "CLOTH")
        notes.append("加了布料修改器")
    cloth.settings.vertex_group_mass = FOLLOW_GROUP
    cloth.collision_settings.use_self_collision = False
    scene = bpy.context.scene
    cloth.point_cache.frame_start, cloth.point_cache.frame_end = scene.frame_start, scene.frame_end
    if arm_mod is not None and list(obj.modifiers).index(cloth) < list(obj.modifiers).index(arm_mod):
        _move(obj, cloth, list(obj.modifiers).index(arm_mod))
    notes.append("%s：布料 1 固定组 = %s（全部顶点）" % (obj.name, FOLLOW_GROUP))
    if arm_mod is None:
        notes.append("注意：%s 没有骨架修改器，不会跟着身体动" % obj.name)
    return notes


FIELD, FIELD_COLL, NO_FIELD_COLL = "CT_撕裂推力", "CT_撕裂力场", "CT_无力场"


def add_tear_force(garments, strength=30.0, start=30.0, end=110.0, radius_factor=1.2):
    """身体不动时，松开的碎片只会贴在身上，裂缝张不开（视频里是钩子拉着布才扯开）：在衣服中心放一个
    向外推的力场（球形、范围内恒定），只作用于撕裂用的布料 2（布料的力场集合 = CT_撕裂力场）；
    强度在开始帧–结束帧之间打开，之后关掉让碎片自然落下。刚体世界（MMD 头发物理）原来没限定力场集合时，
    改成一个空集合 CT_无力场，头发不受这个推力影响。返回说明文字。"""
    garments = [g for g in garments if g is not None]
    pts = [g.matrix_world @ Vector(c) for g in garments for c in g.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    scene = bpy.context.scene
    coll = bpy.data.collections.get(FIELD_COLL) or bpy.data.collections.new(FIELD_COLL)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    empty = bpy.data.objects.get(FIELD)
    if empty is None:
        empty = bpy.data.objects.new(FIELD, None)
        coll.objects.link(empty)
        empty.empty_display_type, empty.empty_display_size = "SPHERE", 0.5
    empty.location = (lo + hi) / 2.0
    if empty.field is None or empty.field.type != "FORCE":
        with bpy.context.temp_override(object=empty, active_object=empty):
            bpy.ops.object.forcefield_toggle()
    field = empty.field
    field.type, field.shape = "FORCE", "POINT"
    field.falloff_type, field.falloff_power = "SPHERE", 0.0
    field.use_max_distance, field.distance_max = True, radius_factor * max(hi - lo)
    if empty.animation_data and empty.animation_data.action:
        empty.animation_data_clear()
    for frame, value in ((start - 1, 0.0), (start + 5, strength), (end, strength), (end + 5, 0.0)):
        field.strength = value
        empty.keyframe_insert('field.strength', frame=frame)
    for g in garments:
        for m in g.modifiers:
            if m.type == "CLOTH":
                m.settings.effector_weights.collection = coll
    notes = ["推力场「%s」：强度 %g，第 %g–%g 帧，半径 %.1f" % (FIELD, strength, start, end, field.distance_max)]
    rbw = scene.rigidbody_world
    if rbw is not None and rbw.effector_weights.collection is None:
        rbw.effector_weights.collection = bpy.data.collections.get(NO_FIELD_COLL) or bpy.data.collections.new(NO_FIELD_COLL)
        notes.append("刚体世界（头发物理）的力场集合设成空集合「%s」，不受推力影响" % NO_FIELD_COLL)
    return notes


def remove_tear_force():
    """删掉 add_tear_force 加的推力场、两个集合，布料和刚体世界的力场集合恢复成「全部」。返回删掉的名字。"""
    removed = []
    empty = bpy.data.objects.get(FIELD)
    if empty is not None:
        bpy.data.objects.remove(empty, do_unlink=True)
        removed.append(FIELD)
    scene = bpy.context.scene
    rbw = scene.rigidbody_world
    for name in (FIELD_COLL, NO_FIELD_COLL):
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        for o in scene.objects:
            for m in o.modifiers:
                if m.type == "CLOTH" and m.settings.effector_weights.collection is coll:
                    m.settings.effector_weights.collection = None
        if rbw is not None and rbw.effector_weights.collection is coll:
            rbw.effector_weights.collection = None
        if not coll.all_objects:
            bpy.data.collections.remove(coll)
            removed.append(name)
    return removed


def model_height(garments):
    """衣服所在角色的身高：同一骨架下所有网格的包围盒高度（没有骨架就用衣服自己的）。"""
    arms = {m.object for g in garments for m in g.modifiers if m.type == "ARMATURE" and m.object}
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != FLOOR
              and any(m.type == "ARMATURE" and m.object in arms for m in o.modifiers)] if arms else []
    zs = [(o.matrix_world @ Vector(c)).z for o in (meshes or garments) for c in o.bound_box]
    return max(zs) - min(zs)


def tear_speed(garments, human=1.7):
    """模型比真人大时（PMX 原尺寸约 18 高）同样的重力看起来慢得多：撕开的碎片像慢动作。布料 2 的速度
    （时间缩放）取 sqrt(身高 / 1.7)，不小于 1 —— 这样下落和推开的快慢跟真人尺寸一样，推力强度也就不用
    跟着尺寸改；质量步数跟着提高到速度 × 5，否则一快就炸。返回 (速度, 质量步数, 身高)。"""
    height = model_height(garments)
    speed = max(1.0, math.sqrt(height / human))
    return round(speed, 2), max(5, math.ceil(5 * speed)), height


def set_tear_speed(garments, speed, quality):
    """只改撕裂用的布料 2（布料 1 跟着身体，不受影响）；质量步数只往上调。"""
    done = []
    for g in garments:
        c2 = g.modifiers.get(MOD_CLOTH)
        if c2 is not None:
            c2.settings.time_scale = speed
            c2.settings.quality = max(c2.settings.quality, quality)
            done.append(g.name)
    return done


SKIP_COLLIDE = ("hair", "eye", "lash", "brow", "mouth", "teeth", "tongue", "face", "head",
                "头发", "眼", "睫毛", "眉", "脸", "头")


def _bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def body_meshes(garment, arm, margin=0.05):
    """撕下来的布要碰的身体：同一骨架下、包围盒和衣服重叠的网格（模型按材质拆开时身体是好几块：
    Body / Legs / Arms），跳过头发、眼睛、睫毛这类和本插件加的地面。"""
    lo, hi = _bbox(garment)
    out = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o is garment or o.name == FLOOR or getattr(o, "mmd_type", "NONE") != "NONE":
            continue
        if not any(m.type == "ARMATURE" and m.object is arm for m in o.modifiers):
            continue
        if any(m.type == "CLOTH" for m in o.modifiers):          # 另一件要撕的衣服
            continue
        name = (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()
        if any(k in name for k in SKIP_COLLIDE):
            continue
        a, b = _bbox(o)
        if all(a[i] <= hi[i] + margin and b[i] >= lo[i] - margin for i in range(3)):
            out.append(o)
    return out


# --- 一键示例 ---------------------------------------------------------------------------------------------
def build_demo(context, cuts=20, cracks=4, seed=7):
    """照视频搭一个完整场景：2 m 平面细分 + 戳孔面，远端两个角钩挂空物体，第 90→190 帧把右边的空物体拉开，
    布料 + 自碰撞，随机裂缝（第一条劈开两个钩挂点之间），撕裂设置（第 120–170 帧从上往下松开）。"""
    scene = context.scene
    mesh = bpy.data.meshes.new("CT_Cloth")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0, calc_uvs=True)
    bm.to_mesh(mesh)
    bm.free()
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new("CT_Cloth", mesh)
    context.collection.objects.link(obj)
    obj.location = scene.cursor.location
    context.view_layer.objects.active = obj
    obj.select_set(True)
    subdivide_poke(obj, cuts=cuts, poke=True)
    for poly in mesh.polygons:
        poly.use_smooth = True
    corners = sorted((v for v in mesh.vertices if abs(abs(v.co.x) - 1.0) < 1e-4 and abs(v.co.y - 1.0) < 1e-4),
                     key=lambda v: v.co.x)
    left, right = corners[0].index, corners[-1].index
    pin_vertices(obj, (left, right), "Group")
    hook_vertex(obj, left, "CT_Hook_L")
    pull = hook_vertex(obj, right, "CT_Hook_R")

    cloth = obj.modifiers.new("Cloth", "CLOTH")
    cloth.settings.vertex_group_mass = "Group"
    cloth.collision_settings.use_self_collision = True
    cloth.point_cache.frame_start, cloth.point_cache.frame_end = scene.frame_start, scene.frame_end

    start = pull.location.copy()
    pull.location = start
    pull.keyframe_insert("location", frame=90)
    pull.location = start + Vector((4.0, 0.0, 0.0))
    pull.keyframe_insert("location", frame=190)
    pull.location = start

    # 一条贯穿两个钩挂点中间的主裂缝（撕成两半，各挂一边，和视频一样），其余从布边撕进去不贯穿
    random_cracks(obj, count=cracks, seed=seed, jitter=0.6, partial=True,
                  through=((0.0, 1.0, 0.0), (0.0, -1.0, 0.0)))
    notes = setup_tear(obj, axis="UV_V", invert=False, start=120, end=170, width=0.05, merge_distance=0.001)
    scene.frame_set(scene.frame_start)
    return obj, notes
