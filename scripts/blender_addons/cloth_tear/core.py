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
import json
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
    cloth2.show_viewport = cloth2.show_render = True        # 复制来的会带上布料 1 的开关
    cloth2.settings.vertex_group_mass = out_group
    cloth2.point_cache.frame_start = cloth.point_cache.frame_start
    cloth2.point_cache.frame_end = cloth.point_cache.frame_end
    notes += _template_only(obj, cloth)

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


def _fully_pinned(obj, cloth):
    """布料 1 的固定组是 CT_Follow，而且每个顶点权重都是 1（「衣服跟随身体」的设置，没被改过）。"""
    vg = obj.vertex_groups.get(FOLLOW_GROUP)
    if cloth.settings.vertex_group_mass != FOLLOW_GROUP or vg is None:
        return False
    gi = vg.index
    return all(any(g.group == gi and g.weight >= 0.999 for g in v.groups) for v in obj.data.vertices)


def _template_only(obj, cloth):
    """衣服模式下布料 1 每个点都固定：固定的点每一步都放回输入的位置，布料 1 的输出就是输入（骨架动画），
    只给布料 2 当模板（复制它的设置）。关掉它的视图 / 渲染开关就不参与计算，烘焙时间和缓存都省一半，
    结果不变。物体属性 ct_cloth1_off 记下是本插件关的：固定组被改了（不再全部固定）就重新打开，
    「移除撕裂设置」「全部清理」也会打开。"""
    if _fully_pinned(obj, cloth):
        if cloth.show_viewport or cloth.show_render:
            cloth.show_viewport = cloth.show_render = False
            obj[CLOTH1_OFF] = cloth.name
        return ["布料 1 每个点都固定，只当布料 2 的模板，关掉不算（烘焙快一倍）"]
    if obj.get(CLOTH1_OFF) == cloth.name:
        cloth.show_viewport = cloth.show_render = True
        del obj[CLOTH1_OFF]
        return ["布料 1 的固定组改过、不再全部固定，重新打开计算"]
    return []


def _restore_cloth1(obj):
    """本插件关掉的布料 1 重新打开。返回说明文字列表。"""
    cloth = source_cloth(obj)
    name = obj.get(CLOTH1_OFF)
    if name is None:
        return []
    del obj[CLOTH1_OFF]
    if cloth is None or cloth.name != name:
        return []
    cloth.show_viewport = cloth.show_render = True
    return ["%s 重新打开" % cloth.name]


def remove_tear(obj):
    removed = []
    for mod in tear_modifiers(obj):
        if mod is not None:
            removed.append(mod.name)
            obj.modifiers.remove(mod)
    tree = bpy.data.node_groups.get(split_tree_name(obj))
    if tree is not None and tree.users == 0:
        bpy.data.node_groups.remove(tree)
    return removed + _restore_cloth1(obj)


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


def _boundary_loops(members):
    """一块网格的边界圈：边界边按共用顶点连成的几串，返回 [(顶点集合, 周长)]。"""
    edges = {e for v in members for e in v.link_edges if e.is_boundary}
    seen, loops = set(), []
    for e0 in edges:
        if e0 in seen:
            continue
        seen.add(e0)
        stack, verts, length = [e0], set(), 0.0
        while stack:
            e = stack.pop()
            length += e.calc_length()
            for v in e.verts:
                verts.add(v)
                for f in v.link_edges:
                    if f in edges and f not in seen:
                        seen.add(f)
                        stack.append(f)
        loops.append((verts, length))
    return loops


def cut_loops(obj, seed=1, jitter=0.6, min_ratio=0.25):
    """把套成圈的布切开：一块布有两圈以上的大边界（腰带、袖子、裙身这种筒状或环状的布，身体从圈里穿过去）时，
    不管怎么撕都掉不下来——撕开的碎片还是一个圈，卡在腰上、脖子上。这里在每块布上加最少的裂缝，把各圈大边界
    连起来（k 圈要 k-1 条），连通后就是一整片，没有圈了。已有的裂缝先当已经撕开算，已经连通的不再加。
    小圈（周长不到这块布最大一圈的 min_ratio，如镂空花纹）不算。返回加的裂缝条数。"""
    rng = random.Random(seed + 1000)
    bm, edit = _bm_of(obj)
    bm.verts.ensure_lookup_table()
    layer = _crease_layer(bm)
    work = bm.copy()                                        # 拆开裂缝的副本，原顶点号存在 orig 层里
    orig = work.verts.layers.int.new("ct_orig")
    for v in work.verts:
        v[orig] = v.index
    wlayer = _crease_layer(work)
    bmesh.ops.split_edges(work, edges=[e for e in work.edges if e[wlayer] > 0.5])
    work.verts.index_update()
    weights = {e: e.calc_length() * (1.0 + jitter * rng.random() * 2.0) for e in work.edges}
    made = 0
    for island in _islands(work):
        loops = _boundary_loops(island)
        if len(loops) < 2:
            continue
        longest = max(length for _, length in loops)
        big = [verts for verts, length in loops if length >= min_ratio * longest and len(verts) >= 4]
        if len(big) < 2:
            continue
        joined, rest = set(big[0]), big[1:]
        while rest:
            owner = {v: i for i, verts in enumerate(rest) for v in verts}
            dist, prev = {v: 0.0 for v in joined}, {}
            todo = [(0.0, v.index, v) for v in joined]
            heapq.heapify(todo)
            hit = None
            while todo:
                d, _, v = heapq.heappop(todo)
                if d > dist.get(v, math.inf):
                    continue
                if v in owner:
                    hit = v
                    break
                for e in v.link_edges:
                    w = e.other_vert(v)
                    nd = d + weights[e]
                    if nd < dist.get(w, math.inf):
                        dist[w], prev[w] = nd, v
                        heapq.heappush(todo, (nd, w.index, w))
            if hit is None:
                break
            path, v = [hit], hit
            while v in prev:
                v = prev[v]
                path.append(v)
            marked = 0
            for a, b in zip(path, path[1:]):
                e = bm.edges.get((bm.verts[a[orig]], bm.verts[b[orig]]))
                if e is not None and not e.is_boundary:
                    e[layer] = 1.0
                    marked += 1
            made += marked > 0
            joined |= set(path) | rest.pop(owner[hit])
    work.free()
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
COLLISION = "CT 碰撞"                # 本插件给身体加的碰撞修改器（1.1 时叫 Collision）
CLOTH_ADDED, CLOTH_BACKUP = "ct_cloth_added", "ct_cloth_backup"   # 物体自定义属性：布料 1 是加的 / 原来的设置
CLOTH1_OFF = "ct_cloth1_off"         # 物体自定义属性：布料 1 全部固定、只当模板，是本插件关掉的（1.3）


FLOOR = "CT_地面碰撞"


def add_floor(z, size=20.0, center=(0.0, 0.0), thickness=0.02):
    """脚底一块不渲染的碰撞平面，撕下来的碎片落在地上，而不是一直往下掉。已有就按新的大小、位置更新。
    size = 边长：太小的话推到外面的碎片会从边上掉下去（Tifa 的碎片推到离中心 14，1.2 的地面只有 ±10）；
    单面碰撞（法线朝上），穿到下面的点会被推回地面上；thickness = 碰撞外层厚度，按模型尺寸放大。"""
    floor = bpy.data.objects.get(FLOOR)
    if floor is None:
        mesh = bpy.data.meshes.new(FLOOR)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)      # 边长 1，用缩放定大小
        bm.to_mesh(mesh)
        bm.free()
        floor = bpy.data.objects.new(FLOOR, mesh)
        bpy.context.scene.collection.objects.link(floor)
        floor.modifiers.new("Collision", "COLLISION")
        floor.display_type = "WIRE"
        floor.hide_render = True
    half = max(abs(v.co.x) for v in floor.data.vertices) or 0.5               # 1.1 / 1.2 建的网格是 ±10
    k = size / (2.0 * half)
    floor.scale = (k, k, 1.0)
    floor.location = (center[0], center[1], z)
    floor.collision.use_culling = True
    floor.collision.use_normal = True
    floor.collision.thickness_outer = thickness
    return floor


def follow_body(garments, add_collision=True, floor=True, skip_accessories=True):
    """撕衣服的准备（garments：一件或几件衣服，各是带骨架修改器的单独网格）。布料 1 全部固定（顶点组
    CT_Follow 全为 1），所以撕开前衣服完全跟着身体动画走、不模拟也不穿模；关掉自碰撞。和衣服重叠的身体
    网格加碰撞（body_meshes，不含这几件衣服本身），撕下来的布落在身上滑下去；floor 时脚底再放一块地面碰撞。
    skip_accessories：项链、耳环、臂甲这类饰品不加碰撞（衣带从项链底下穿过，碎片会被卡住吊在脖子上；
    推到手臂上的碎片会挂在臂甲尖上）。"""
    garments = [g for g in (garments if isinstance(garments, (list, tuple)) else [garments])
                if g is not None and g.type == "MESH"]
    if not garments:
        raise RuntimeError("先选中衣服网格")
    notes, colliders, skipped = [], [], []
    for obj in garments:
        notes += _follow_one(obj)
        arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        if arm_mod is not None and add_collision:
            colliders += [b for b in body_meshes(obj, arm_mod.object, skip_accessories=skip_accessories)
                          if b not in garments and b not in colliders]
            skipped += [b for b in body_meshes(obj, arm_mod.object, skip_accessories=False)
                        if b not in garments and b not in colliders and b not in skipped]
    for body in colliders:
        if not any(m.type == "COLLISION" for m in body.modifiers):
            body.modifiers.new(COLLISION, "COLLISION")
    if colliders:
        notes.append("加了碰撞：%s" % "、".join(b.name for b in colliders))
    if skipped:
        notes.append("饰品不加碰撞：%s" % "、".join(b.name for b in skipped))
    stale = [b.name for b in skipped if any(m.type == "COLLISION" for m in b.modifiers)]
    if stale:
        notes.append("注意：%s 已经有碰撞（可能是旧版加的），碎片会被它挂住，可以用「全部清理」或手动删掉" % "、".join(stale))
    arm_mod = next((m for g in garments for m in g.modifiers if m.type == "ARMATURE" and m.object), None)
    if floor and arm_mod is not None:
        # 衣服本身也算：游戏的成套模型常把皮肤和衣服放在同一个网格里（ROE 的 pc_a08_hd：皮肤 + 衣服都在 body1，
        # 另外只有头和头发），只看衣服以外的网格时地面放到了头的下沿（1.4 米高）
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"
                  and any(m.type == "ARMATURE" and m.object is arm_mod.object for m in o.modifiers)]
        if meshes:
            pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
            low, high = min(p.z for p in pts), max(p.z for p in pts)
            cx = (min(p.x for p in pts) + max(p.x for p in pts)) / 2.0
            cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2.0
            side = max(20.0, 4.0 * (high - low))
            add_floor(low, size=side, center=(cx, cy), thickness=0.02 * max(1.0, (high - low) / 1.7))
            notes.append("脚底加了地面碰撞「%s」（不渲染，边长 %.0f）" % (FLOOR, side))
    return notes


def _follow_one(obj):
    arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
    notes = []
    pin_vertices(obj, range(len(obj.data.vertices)), FOLLOW_GROUP)
    cloth = source_cloth(obj)
    if cloth is None:
        cloth = obj.modifiers.new("Cloth", "CLOTH")
        obj[CLOTH_ADDED] = cloth.name
        notes.append("加了布料修改器")
    elif cloth.settings.vertex_group_mass != FOLLOW_GROUP and CLOTH_BACKUP not in obj:
        pc = cloth.point_cache                              # 用户自己的布料：记下要改的几项，「全部清理」时还原
        obj[CLOTH_BACKUP] = json.dumps({"name": cloth.name, "pin": cloth.settings.vertex_group_mass,
                                        "self_collision": cloth.collision_settings.use_self_collision,
                                        "frame_start": pc.frame_start, "frame_end": pc.frame_end})
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


def add_tear_force(garments, strength=30.0, start=30.0, end=110.0, radius_factor=1.2, shape="LINE"):
    """身体不动时，松开的碎片只会贴在身上，裂缝张不开（视频里是钩子拉着布才扯开）：放一个向外推的力场
    （范围内恒定），只作用于撕裂用的布料 2（布料的力场集合 = CT_撕裂力场）；强度在开始帧–结束帧之间打开，
    之后关掉让碎片自然落下。刚体世界（MMD 头发物理）原来没限定力场集合时，改成一个空集合 CT_无力场，
    头发不受这个推力影响。返回说明文字。

    shape="LINE"（1.2 起）：从穿过衣服中心的竖直轴往外水平推，范围是衣服那一段高度的圆柱（管状衰减），
    肩上、脖子上的碎片被推离身体，掉到衣服下面就出了范围、自然落地。
    shape="POINT"（1.1）：从衣服中心往四面推，球形范围；中心以上的碎片是往上推的，搭在肩上的掉不下来。"""
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
    empty.location = (lo + hi) / 2.0
    empty.rotation_euler = (0.0, 0.0, 0.0)                  # 力场的 Z 轴 = 世界竖直方向
    if empty.field is None or empty.field.type != "FORCE":
        with bpy.context.temp_override(object=empty, active_object=empty):
            bpy.ops.object.forcefield_toggle()
    field = empty.field
    size = max(hi - lo)
    if shape == "LINE":
        field.type, field.shape = "FORCE", "LINE"
        field.falloff_type, field.falloff_power, field.radial_falloff = "TUBE", 0.0, 0.0
        field.use_max_distance, field.distance_max = True, 0.5 * (hi.z - lo.z) * 1.05   # 上下：衣服的高度
        field.use_radial_max, field.radial_max = True, radius_factor * size
        empty.empty_display_type, empty.empty_display_size = "SINGLE_ARROW", 0.5 * (hi.z - lo.z)
    else:
        field.type, field.shape = "FORCE", "POINT"
        field.falloff_type, field.falloff_power = "SPHERE", 0.0
        field.use_max_distance, field.distance_max = True, radius_factor * size
        field.use_radial_max = False
        empty.empty_display_type, empty.empty_display_size = "SPHERE", 0.5
    if empty.animation_data and empty.animation_data.action:
        empty.animation_data_clear()
    for frame, value in ((start - 1, 0.0), (start + 5, strength), (end, strength), (end + 5, 0.0)):
        field.strength = value
        empty.keyframe_insert('field.strength', frame=frame)
    for g in garments:
        for m in g.modifiers:
            if m.type == "CLOTH":
                m.settings.effector_weights.collection = coll
    if shape == "LINE":
        notes = ["推力场「%s」：从中轴水平往外推，强度 %g，第 %g–%g 帧，高 %.1f–%.1f、半径 %.1f" % (
            FIELD, strength, start, end, empty.location.z - field.distance_max, empty.location.z + field.distance_max,
            field.radial_max)]
    else:
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


def tear_garments(scene=None):
    """场景里用过本插件的网格：有撕裂修改器，或有 CT_Follow / CT_Pin 顶点组。"""
    scene = scene or bpy.context.scene
    return [o for o in scene.objects if o.type == "MESH" and o.name != FLOOR
            and (any(tear_modifiers(o)) or FOLLOW_GROUP in o.vertex_groups or OUT_GROUP in o.vertex_groups)]


def cleanup_all(clear_cracks=True):
    """全部清理：删掉本插件在这个场景里加的所有东西，回到用插件之前。
    每件衣服：三个撕裂修改器、「衣服跟随身体」加的布料 1（用户原来就有的布料还原固定组等设置）、CT_Follow /
    CT_Pin 顶点组、clear_cracks 时连裂缝一起清；场景：给身体加的碰撞、地面、推力场和它的集合、没人用的节点组。
    1.1 加的碰撞修改器叫 Collision，没有标记：和这些衣服重叠的同骨架网格上叫 Collision 的碰撞也删（不按名字
    跳过，项链上的也算）。钩挂、空物体、平面示例本身不动。返回做了什么（文字列表）。"""
    scene = bpy.context.scene
    garments = tear_garments(scene)
    done, old_bodies = [], set()
    for g in garments:
        arm = next((m.object for m in g.modifiers if m.type == "ARMATURE" and m.object), None)
        if arm is not None:
            old_bodies.update(body_meshes(g, arm, skip_names=False))
    for g in garments:
        parts = remove_tear(g)
        cloth = source_cloth(g)
        backup = g.get(CLOTH_BACKUP)
        if cloth is not None and backup:
            b = json.loads(backup)
            cloth.settings.vertex_group_mass = b["pin"]
            cloth.collision_settings.use_self_collision = b["self_collision"]
            cloth.point_cache.frame_start, cloth.point_cache.frame_end = b["frame_start"], b["frame_end"]
            parts.append("%s 还原成原来的设置" % cloth.name)
        elif cloth is not None and (g.get(CLOTH_ADDED) == cloth.name or cloth.settings.vertex_group_mass == FOLLOW_GROUP):
            parts = [p for p in parts if not p.endswith("重新打开")] + [cloth.name]
            g.modifiers.remove(cloth)
        for key in (CLOTH_ADDED, CLOTH_BACKUP, CLOTH1_OFF):
            if key in g:
                del g[key]
        for name in (FOLLOW_GROUP, OUT_GROUP):
            vg = g.vertex_groups.get(name)
            if vg is not None:
                g.vertex_groups.remove(vg)
                parts.append("顶点组 " + name)
        if clear_cracks:
            n = seam_count(g)
            if n:
                mark_seams(g, 0.0, only_selected=False)
                parts.append("裂缝 %d 条边" % n)
        if parts:
            done.append("%s：%s" % (g.name, "、".join(parts)))
    bodies = []
    for o in scene.objects:
        if o.type != "MESH":
            continue
        for m in list(o.modifiers):
            if m.type == "COLLISION" and (m.name == COLLISION or (m.name == "Collision" and o in old_bodies)):
                o.modifiers.remove(m)
                bodies.append(o.name)
    if bodies:
        done.append("碰撞：%s" % "、".join(bodies))
    floor = bpy.data.objects.get(FLOOR)
    if floor is not None:
        mesh = floor.data
        bpy.data.objects.remove(floor, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        done.append("地面 " + FLOOR)
    force = remove_tear_force()
    if force:
        done.append("推力场：%s" % "、".join(force))
    for ng in list(bpy.data.node_groups):
        if (ng.name == "CT_TearMerge" or ng.name.startswith("CT_TearSplit_")) and ng.users == 0:
            bpy.data.node_groups.remove(ng)
    return done


def _character_meshes(garments):
    """和衣服同一骨架的所有网格（不含地面）；衣服没有骨架时就是衣服自己。"""
    arms = {m.object for g in garments for m in g.modifiers if m.type == "ARMATURE" and m.object}
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != FLOOR
              and any(m.type == "ARMATURE" and m.object in arms for m in o.modifiers)] if arms else []
    return meshes or list(garments)


def model_height(garments):
    """衣服所在角色的身高：同一骨架下所有网格的包围盒高度（没有骨架就用衣服自己的）。"""
    zs = [(o.matrix_world @ Vector(c)).z for o in _character_meshes(garments) for c in o.bound_box]
    return max(zs) - min(zs)


def steps_for(time_scale, fast=False):
    """布料 2 的质量步数：速度 × 5（一快就炸、碎片挂在手指上的都靠它）；快速预览时速度 × 2.5。
    实测（2026-10-02，150 帧）：Fiona 98 → 52 秒、Tifa 265 → 169 秒，碎片照样撕开落地，
    但 Tifa 有一条手套挂在手上没滑下来（步数 6 时两只手都挂着）。"""
    return max(3, math.ceil(2.5 * time_scale)) if fast else max(5, math.ceil(5 * time_scale))


def tear_speed(garments, human=1.7, fast=False):
    """模型比真人大时（PMX 原尺寸约 18 高）同样的重力看起来慢得多：撕开的碎片像慢动作。布料 2 的速度
    （时间缩放）取 sqrt(身高 / 1.7)，不小于 1 —— 这样下落和推开的快慢跟真人尺寸一样，推力强度也就不用
    跟着尺寸改；质量步数见 steps_for。返回 (速度, 质量步数, 身高)。"""
    height = model_height(garments)
    speed = max(1.0, math.sqrt(height / human))
    return round(speed, 2), steps_for(speed, fast), height


def set_tear_speed(garments, speed, quality, exact=False):
    """只改撕裂用的布料 2（布料 1 跟着身体，不受影响）；质量步数只往上调，exact 时照给的值（快速预览）。"""
    done = []
    for g in garments:
        c2 = g.modifiers.get(MOD_CLOTH)
        if c2 is not None:
            c2.settings.time_scale = speed
            c2.settings.quality = quality if exact else max(c2.settings.quality, quality)
            done.append(g.name)
    return done


def set_fast(fast, scene=None):
    """快速预览开 / 关：场景里每件衣服的布料 2 按它现在的速度重设质量步数（速度 × 2.5 / × 5）。
    返回 [(衣服, 步数)]。"""
    out = []
    for g in tear_garments(scene):
        c2 = g.modifiers.get(MOD_CLOTH)
        if c2 is not None:
            c2.settings.quality = steps_for(c2.settings.time_scale, fast)
            out.append((g.name, c2.settings.quality))
    return out


SKIP_COLLIDE = ("hair", "eye", "lash", "brow", "mouth", "teeth", "tongue", "face", "head",
                "头发", "眼", "睫毛", "眉", "脸", "头")
# 饰品：衣带常从项链底下穿过，项链有碰撞时撕开的碎片被它兜住，吊在脖子上掉不下来（Fiona 实测）
# 护甲、臂甲同理：T 字姿势时碎片被推到手臂上，挂在 Fiona 的臂甲尖上（不当碰撞体后全部落地）
ACCESSORIES = ("necklace", "earring", "pendant", "choker", "bracelet", "bangle", "jewel", "piercing",
               "pad", "armor", "armour", "gauntlet", "pauldron",
               "项链", "耳环", "耳饰", "吊坠", "手镯", "手链", "首饰", "饰品", "护甲", "盔甲", "肩甲", "护肩", "臂甲",
               "ネックレス", "イヤリング", "ピアス", "アーマー", "鎧")


def _bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def body_meshes(garment, arm, margin=0.05, skip_accessories=True, skip_names=True):
    """撕下来的布要碰的身体：同一骨架下、包围盒和衣服重叠的网格（模型按材质拆开时身体是好几块：
    Body / Legs / Arms），跳过头发、眼睛、睫毛这类、项链耳环这类饰品（skip_accessories）和本插件加的地面。
    skip_names=False 时不按名字跳过（「全部清理」找 1.1 加过碰撞的网格用）。"""
    lo, hi = _bbox(garment)
    out = []
    skip = (SKIP_COLLIDE + (ACCESSORIES if skip_accessories else ())) if skip_names else ()
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o is garment or o.name == FLOOR or getattr(o, "mmd_type", "NONE") != "NONE":
            continue
        if not any(m.type == "ARMATURE" and m.object is arm for m in o.modifiers):
            continue
        if any(m.type == "CLOTH" for m in o.modifiers):          # 另一件要撕的衣服
            continue
        name = (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()
        if any(k in name for k in skip):
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
