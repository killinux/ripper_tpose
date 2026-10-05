# -*- coding: utf-8 -*-
"""爆衣的外观：撕口毛边 / 变暗，碎片淡出或溶解（带光边）。只改渲染，不改模拟，改了马上生效、不用重新烘焙。

做法分两半：
  1. 每件爆过的衣服写四个顶点属性（在原网格上；骨架、拆缝、布料、合缝这些修改器都会把它带下去，
     拆开的裂缝两边各带一份）：
       cb_t     这个顶点被松开的帧（按松开带扫过它的时间算，留在身上的顶点也有）
       cb_free  1 = 会飞出去，0 = 留在身上（只爆一部分时范围外的顶点）
       cb_edge  到最近一条「会撕开的裂缝」的距离（沿网格的边走，按身高归一化，最多 CAP）
       cb_rest  静止时的位置（按身高归一化）：噪波贴在布上，碎片飞走时花纹不会滑
  2. 一个着色器节点组「CB_爆衣外观」插在衣服材质的输出前面：读这几个属性和当前帧（节点组里一个值节点，
     驱动器 = frame），算出
       撕口：撕开以后，离裂缝近于「宽度 × 噪波」的地方透明（毛边），再近一点的地方变暗；
       消失：松开后过「开始」帧，「用几帧」之内淡出（透明度渐变），或按噪波一块块溶解，溶解的边缘发光、
             边缘里面一圈焦黑。
     参数都是节点组里的值节点（几件衣服共用一组），面板改了就写进去。

没有这些属性的物体（身体等和衣服共用材质的）不受影响：cb_t 读出来是 0，判为「没有数据」。
Eevee 需要材质的混合模式不是「不透明」：原来是不透明的改成 Alpha Hashed，记在材质属性 cb_blend 里，移除时还原。
"""
import heapq
import json

import bmesh
import bpy

from cloth_tear import core as ct

OLD_EEVEE = bpy.app.version < (4, 2, 0)
GROUP = "CB_爆衣外观"          # 着色器节点组
NODE = "CB 爆衣外观"           # 材质里那个组节点的名字（材质有几个输出节点时加 2、3 ……）
BLEND_PROP = "cb_blend"        # 材质属性：本插件改之前的 [混合模式, 阴影模式]
ATTRS = ("cb_t", "cb_free", "cb_edge", "cb_rest")
CAP = 0.1                      # cb_edge 最多记到身高的 10%（撕口宽度最大 3%，变暗带是 3 倍宽度 = 9%，不能超过它）
DEFAULTS = {
    "fray": True, "fray_width": 0.5, "fray_dark": 0.3,                 # 撕口：开关、宽度（身高的 %）、变暗
    "vanish": "NONE", "vanish_delay": 3, "vanish_frames": 12,           # 消失：NONE / FADE / DISSOLVE，松开后几帧开始、用几帧
    "rim_color": (1.0, 0.38, 0.08), "glow": 6.0,                        # 溶解的光边颜色、亮度
}
LOOK_KEYS = tuple(DEFAULTS)
MODES = {"NONE": 0.0, "FADE": 1.0, "DISSOLVE": 2.0}
# 节点组里的参数（值节点名 -> 默认值）；面板没有的几项（噪波大小、光边宽度、焦黑颜色）要改就直接改节点组
PARAMS = {"cb_mode": 0.0, "cb_delay": 3.0, "cb_length": 12.0, "cb_glow": 6.0, "cb_rim": 0.06,
          "cb_scale": 9.0, "cb_fray_on": 1.0, "cb_fray_w": 0.005, "cb_fray_scale": 160.0, "cb_fray_dark": 0.3}


# --- 顶点属性 -------------------------------------------------------------------------------------------------
def _set_attr(mesh, name, kind, values):
    attr = mesh.attributes.get(name)
    if attr is not None and (attr.domain != "POINT" or attr.data_type != kind):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(name, kind, "POINT")
    attr.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value", values)


def has_attributes(obj):
    return obj.type == "MESH" and all(obj.data.attributes.get(a) is not None for a in ATTRS)


def remove_attributes(obj):
    removed = []
    for name in ATTRS:
        attr = obj.data.attributes.get(name)
        if attr is not None:
            obj.data.attributes.remove(attr)
            removed.append(name)
    return removed


def _crack_edges(obj):
    """裂缝边的序号。3.6 的边折痕不在 mesh.attributes 里（4.0 起才是属性 crease_edge），用 bmesh 读。"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = ct._crease_layer(bm, create=False)
    out = [] if layer is None else [e.index for e in bm.edges if e[layer] > 0.5]
    bm.free()
    return out


def write_attributes(obj, frame, end, width=0.08, invert=False, keep=(), height=None):
    """按这次爆衣的设置写 cb_t / cb_free / cb_edge / cb_rest。keep：留在身上的顶点序号；height：角色身高
    （默认按同一骨架的网格算）。返回 (会撕开的裂缝边数, 撕口最远记到的距离)。"""
    mesh = obj.data
    n = len(mesh.vertices)
    if n == 0:
        return 0, 0.0
    height = height or ct.model_height([obj]) or 1.0
    mw = obj.matrix_world
    co = [v.co.copy() for v in mesh.vertices]
    world = [mw @ c for c in co]

    # 松开的帧：和「CT 拆缝」里的松开带一样（物体坐标的 Z 归一化到 0..1，前沿从 1 + w 扫到 -w），取权重到 0 的时刻
    zs = [c.z for c in co]
    lo, hi = min(zs), max(zs)
    span = (hi - lo) or 1.0
    t = []
    for z in zs:
        nz = (z - lo) / span
        if invert:
            nz = 1.0 - nz
        t.append(frame + (end - frame) * (1.0 + width - nz) / (1.0 + 2.0 * width))
    keep = set(keep)
    free = [0.0 if i in keep else 1.0 for i in range(n)]

    # 到裂缝的距离：只算会撕开的裂缝（两头都留在身上的裂缝不会开，例如范围外原有的手画裂缝）
    edges = [tuple(e.vertices) for e in mesh.edges]
    sources = set()
    opened = 0
    for i in _crack_edges(obj):
        a, b = edges[i]
        if a in keep and b in keep:
            continue
        sources.update((a, b))
        opened += 1
    adj = [[] for _ in range(n)]
    for a, b in edges:
        d = (world[a] - world[b]).length / height
        adj[a].append((b, d))
        adj[b].append((a, d))
    dist = [CAP] * n
    heap = [(0.0, s) for s in sources]
    for s in sources:
        dist[s] = 0.0
    heapq.heapify(heap)
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for u, w in adj[v]:
            nd = d + w
            if nd < dist[u]:
                dist[u] = nd
                heapq.heappush(heap, (nd, u))

    rest = []
    for p in world:
        rest.extend((p.x / height, p.y / height, p.z / height))
    _set_attr(mesh, "cb_t", "FLOAT", t)
    _set_attr(mesh, "cb_free", "FLOAT", free)
    _set_attr(mesh, "cb_edge", "FLOAT", dist)
    _set_attr(mesh, "cb_rest", "FLOAT_VECTOR", rest)
    mesh.update()
    return opened, max((d for d in dist if d < CAP), default=0.0)


# --- 节点组 ---------------------------------------------------------------------------------------------------
def _node(nodes, kind, x, y, name=None, label=None, **props):
    node = nodes.new(kind)
    node.location = (x, y)
    if name:
        node.name = name
    if label:
        node.label = label
    for k, v in props.items():
        setattr(node, k, v)
    return node


def _math(nodes, op, x, y, a=None, b=None, c=None, clamp=False):
    node = _node(nodes, "ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b, c)):
        if v is not None:
            node.inputs[i].default_value = v
    return node


def _value(nodes, name, label, value, x, y):
    node = _node(nodes, "ShaderNodeValue", x, y, name=name, label=label)
    node.outputs[0].default_value = value
    return node


LABELS = {"cb_mode": "消失方式（0 不消失 / 1 淡出 / 2 溶解）", "cb_delay": "松开后几帧开始消失", "cb_length": "消失用几帧",
          "cb_glow": "光边亮度", "cb_rim": "光边宽度（0..1）", "cb_scale": "溶解花纹的大小（每个身高几块）",
          "cb_fray_on": "撕口开关（0 / 1）", "cb_fray_w": "撕口宽度（身高的比例）", "cb_fray_scale": "毛边的细碎程度",
          "cb_fray_dark": "撕口变暗（0..1）"}


def build_group():
    """建（或取已有的）节点组。已有时不重建：材质里的组节点正连着它。"""
    tree = bpy.data.node_groups.get(GROUP)
    if tree is not None and tree.bl_idname == "ShaderNodeTree" and tree.nodes.get("cb_frame") is not None:
        return tree
    tree = bpy.data.node_groups.new(GROUP, "ShaderNodeTree")
    ct._socket(tree, "INPUT", "Shader", "NodeSocketShader")
    ct._socket(tree, "OUTPUT", "Shader", "NodeSocketShader")
    n, link = tree.nodes, tree.links.new
    gin = _node(n, "NodeGroupInput", -2200, 300)
    gout = _node(n, "NodeGroupOutput", 1400, 300)

    # 参数
    frame = _value(n, "cb_frame", "当前帧（驱动器 frame）", 1.0, -2200, -100)
    fc = frame.outputs[0].driver_add("default_value")
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = "frame"
    p = {k: _value(n, k, LABELS[k], v, -2200, -250 - 110 * i) for i, (k, v) in enumerate(PARAMS.items())}
    rim_color = _node(n, "ShaderNodeRGB", -1950, -1500, name="cb_rim_color", label="光边颜色")
    rim_color.outputs[0].default_value = (1.0, 0.38, 0.08, 1.0)
    dark_color = _node(n, "ShaderNodeRGB", -1750, -1500, name="cb_dark_color", label="焦黑颜色")
    dark_color.outputs[0].default_value = (0.012, 0.006, 0.003, 1.0)

    def attr(name, y):
        node = _node(n, "ShaderNodeAttribute", -1950, y, label=name)
        node.attribute_type, node.attribute_name = "GEOMETRY", name
        return node
    a_t, a_free, a_edge, a_rest = attr("cb_t", 700), attr("cb_free", 500), attr("cb_edge", 300), attr("cb_rest", 100)

    # 撕开了没有：有数据（cb_t > 0）且当前帧 ≥ cb_t
    since = _math(n, "SUBTRACT", -1700, 650)
    link(frame.outputs[0], since.inputs[0]); link(a_t.outputs["Fac"], since.inputs[1])
    has = _math(n, "GREATER_THAN", -1700, 800, b=0.5)
    link(a_t.outputs["Fac"], has.inputs[0])
    after = _math(n, "GREATER_THAN", -1500, 650, b=-0.001)
    link(since.outputs[0], after.inputs[0])
    torn = _math(n, "MULTIPLY", -1300, 700)
    link(after.outputs[0], torn.inputs[0]); link(has.outputs[0], torn.inputs[1])

    # 消失进度 p：松开后过 delay 帧开始，length 帧走完；只对会飞出去的顶点
    sd = _math(n, "SUBTRACT", -1500, 450)
    link(since.outputs[0], sd.inputs[0]); link(p["cb_delay"].outputs[0], sd.inputs[1])
    length = _math(n, "MAXIMUM", -1500, 300, b=1.0)
    link(p["cb_length"].outputs[0], length.inputs[0])
    prog = _math(n, "DIVIDE", -1300, 450, clamp=True)
    link(sd.outputs[0], prog.inputs[0]); link(length.outputs[0], prog.inputs[1])
    pf = _math(n, "MULTIPLY", -1100, 450)
    link(prog.outputs[0], pf.inputs[0]); link(a_free.outputs["Fac"], pf.inputs[1])
    pp = _math(n, "MULTIPLY", -900, 450)
    link(pf.outputs[0], pp.inputs[0]); link(has.outputs[0], pp.inputs[1])
    started = _math(n, "GREATER_THAN", -700, 600, b=0.0005)
    link(pp.outputs[0], started.inputs[0])
    is_fade = _math(n, "COMPARE", -1100, -100, b=1.0, c=0.1)
    link(p["cb_mode"].outputs[0], is_fade.inputs[0])
    is_dis = _math(n, "COMPARE", -1100, -250, b=2.0, c=0.1)
    link(p["cb_mode"].outputs[0], is_dis.inputs[0])

    # 溶解：噪波 n（0..1）> 阈值 th 的地方还在；th = p (1.01 + 光边) - 光边，p = 0 时全在，p = 1 时全没
    noise = _node(n, "ShaderNodeTexNoise", -1500, 100)
    noise.inputs["Detail"].default_value = 2.0
    link(a_rest.outputs["Vector"], noise.inputs["Vector"]); link(p["cb_scale"].outputs[0], noise.inputs["Scale"])
    n01 = _node(n, "ShaderNodeMapRange", -1300, 100, clamp=True)
    n01.inputs[1].default_value, n01.inputs[2].default_value = 0.3, 0.7
    link(noise.outputs["Fac"], n01.inputs[0])
    k = _math(n, "ADD", -1300, -100, b=1.01)
    link(p["cb_rim"].outputs[0], k.inputs[0])
    th0 = _math(n, "MULTIPLY", -1100, 100)
    link(pp.outputs[0], th0.inputs[0]); link(k.outputs[0], th0.inputs[1])
    th = _math(n, "SUBTRACT", -900, 100)
    link(th0.outputs[0], th.inputs[0]); link(p["cb_rim"].outputs[0], th.inputs[1])
    dd = _math(n, "SUBTRACT", -700, 200)
    link(n01.outputs[0], dd.inputs[0]); link(th.outputs[0], dd.inputs[1])
    vis = _math(n, "GREATER_THAN", -500, 250, b=0.0)
    link(dd.outputs[0], vis.inputs[0])
    in_rim = _math(n, "LESS_THAN", -500, 100)
    link(dd.outputs[0], in_rim.inputs[0]); link(p["cb_rim"].outputs[0], in_rim.inputs[1])
    rim = _math(n, "MULTIPLY", -300, 150)
    link(vis.outputs[0], rim.inputs[0]); link(in_rim.outputs[0], rim.inputs[1])
    rim2 = _math(n, "MULTIPLY", -100, 150)
    link(rim.outputs[0], rim2.inputs[0]); link(started.outputs[0], rim2.inputs[1])
    rim3 = _math(n, "MULTIPLY", 100, 150)
    link(rim2.outputs[0], rim3.inputs[0]); link(is_dis.outputs[0], rim3.inputs[1])
    # 光边里面一圈焦黑：dd 在 [光边, 2.5 × 光边] 里从 0.8 降到 0
    rim3x = _math(n, "MULTIPLY", -500, -100, b=2.5)
    link(p["cb_rim"].outputs[0], rim3x.inputs[0])
    char = _node(n, "ShaderNodeMapRange", -300, -50, clamp=True)
    char.inputs[3].default_value, char.inputs[4].default_value = 0.8, 0.0
    link(dd.outputs[0], char.inputs[0]); link(p["cb_rim"].outputs[0], char.inputs[1]); link(rim3x.outputs[0], char.inputs[2])
    char2 = _math(n, "MULTIPLY", -100, -50)
    link(char.outputs[0], char2.inputs[0]); link(started.outputs[0], char2.inputs[1])
    char3 = _math(n, "MULTIPLY", 100, -50)
    link(char2.outputs[0], char3.inputs[0]); link(is_dis.outputs[0], char3.inputs[1])

    # 消失的透明度：1 - 淡出 × p - 溶解 × (1 - 还在)
    fade_a = _math(n, "MULTIPLY", -300, 450)
    link(is_fade.outputs[0], fade_a.inputs[0]); link(pp.outputs[0], fade_a.inputs[1])
    gone = _math(n, "SUBTRACT", -300, 300, a=1.0)
    link(vis.outputs[0], gone.inputs[1])
    dis_a = _math(n, "MULTIPLY", -100, 300)
    link(is_dis.outputs[0], dis_a.inputs[0]); link(gone.outputs[0], dis_a.inputs[1])
    a1 = _math(n, "SUBTRACT", 100, 450, a=1.0)
    link(fade_a.outputs[0], a1.inputs[1])
    a2 = _math(n, "SUBTRACT", 300, 400, clamp=True)
    link(a1.outputs[0], a2.inputs[0]); link(dis_a.outputs[0], a2.inputs[1])

    # 撕口：撕开后，离裂缝近于「宽度 × (0.2 + 0.8 × 细噪波)」的地方透明；3 倍宽度以内渐渐变暗
    fnoise = _node(n, "ShaderNodeTexNoise", -1500, -500)
    fnoise.inputs["Detail"].default_value = 3.0
    link(a_rest.outputs["Vector"], fnoise.inputs["Vector"]); link(p["cb_fray_scale"].outputs[0], fnoise.inputs["Scale"])
    f01 = _node(n, "ShaderNodeMapRange", -1300, -500, clamp=True)
    f01.inputs[1].default_value, f01.inputs[2].default_value = 0.3, 0.7
    link(fnoise.outputs["Fac"], f01.inputs[0])
    fw = _math(n, "MULTIPLY_ADD", -1100, -500, b=0.8, c=0.2)
    link(f01.outputs[0], fw.inputs[0])
    wcut = _math(n, "MULTIPLY", -900, -500)
    link(fw.outputs[0], wcut.inputs[0]); link(p["cb_fray_w"].outputs[0], wcut.inputs[1])
    near = _math(n, "LESS_THAN", -700, -500)
    link(a_edge.outputs["Fac"], near.inputs[0]); link(wcut.outputs[0], near.inputs[1])
    fray_gate = _math(n, "MULTIPLY", -700, -700)
    link(torn.outputs[0], fray_gate.inputs[0]); link(p["cb_fray_on"].outputs[0], fray_gate.inputs[1])
    cut = _math(n, "MULTIPLY", -500, -550)
    link(near.outputs[0], cut.inputs[0]); link(fray_gate.outputs[0], cut.inputs[1])
    w3 = _math(n, "MULTIPLY", -900, -750, b=3.0)
    link(p["cb_fray_w"].outputs[0], w3.inputs[0])
    dark_r = _node(n, "ShaderNodeMapRange", -500, -750, clamp=True)
    dark_r.inputs[1].default_value = 0.0
    dark_r.inputs[3].default_value, dark_r.inputs[4].default_value = 1.0, 0.0
    link(a_edge.outputs["Fac"], dark_r.inputs[0]); link(w3.outputs[0], dark_r.inputs[2])
    dk1 = _math(n, "MULTIPLY", -300, -750)
    link(dark_r.outputs[0], dk1.inputs[0]); link(p["cb_fray_dark"].outputs[0], dk1.inputs[1])
    dk2 = _math(n, "MULTIPLY", -100, -750)
    link(dk1.outputs[0], dk2.inputs[0]); link(fray_gate.outputs[0], dk2.inputs[1])
    dark = _math(n, "MAXIMUM", 300, -300)
    link(dk2.outputs[0], dark.inputs[0]); link(char3.outputs[0], dark.inputs[1])

    keep = _math(n, "SUBTRACT", -300, -550, a=1.0)
    link(cut.outputs[0], keep.inputs[1])
    alpha = _math(n, "MULTIPLY", 500, 300)
    link(a2.outputs[0], alpha.inputs[0]); link(keep.outputs[0], alpha.inputs[1])

    # 合成：原材质 → 混进焦黑 → 加光边 → 按透明度混进透明
    e_dark = _node(n, "ShaderNodeEmission", 500, -100)
    link(dark_color.outputs[0], e_dark.inputs["Color"])
    e_dark.inputs["Strength"].default_value = 1.0
    mix_dark = _node(n, "ShaderNodeMixShader", 750, 100)
    link(dark.outputs[0], mix_dark.inputs[0]); link(gin.outputs[0], mix_dark.inputs[1]); link(e_dark.outputs[0], mix_dark.inputs[2])
    glow = _math(n, "MULTIPLY", 500, -300)
    link(rim3.outputs[0], glow.inputs[0]); link(p["cb_glow"].outputs[0], glow.inputs[1])
    e_rim = _node(n, "ShaderNodeEmission", 750, -200)
    link(rim_color.outputs[0], e_rim.inputs["Color"]); link(glow.outputs[0], e_rim.inputs["Strength"])
    add = _node(n, "ShaderNodeAddShader", 1000, 0)
    link(mix_dark.outputs[0], add.inputs[0]); link(e_rim.outputs[0], add.inputs[1])
    clear = _node(n, "ShaderNodeBsdfTransparent", 1000, 300)
    out = _node(n, "ShaderNodeMixShader", 1200, 300)
    link(alpha.outputs[0], out.inputs[0]); link(clear.outputs[0], out.inputs[1]); link(add.outputs[0], out.inputs[2])
    link(out.outputs[0], gout.inputs[0])
    return tree


def set_params(tree, o):
    """面板的外观设置（DEFAULTS 里的各项）写进节点组。"""
    vals = {"cb_mode": MODES.get(o["vanish"], 0.0), "cb_delay": float(o["vanish_delay"]),
            "cb_length": float(o["vanish_frames"]), "cb_glow": float(o["glow"]),
            "cb_fray_on": 1.0 if o["fray"] else 0.0, "cb_fray_w": float(o["fray_width"]) / 100.0,
            "cb_fray_dark": float(o["fray_dark"])}
    for name, value in vals.items():
        node = tree.nodes.get(name)
        if node is not None:
            node.outputs[0].default_value = value
    node = tree.nodes.get("cb_rim_color")
    if node is not None:
        node.outputs[0].default_value = tuple(o["rim_color"])[:3] + (1.0,)


def enabled(o):
    return bool(o["fray"]) or o["vanish"] != "NONE"


# --- 材质 -----------------------------------------------------------------------------------------------------
def _ours(mat):
    tree = bpy.data.node_groups.get(GROUP)
    if tree is None or not mat.use_nodes or mat.node_tree is None:
        return []
    return [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree is tree]


def materials_of(obj):
    return [s.material for s in obj.material_slots if s.material is not None]


def attach(mat, tree):
    """组节点插到材质每个输出节点的「表面」前面（已插过就不动）。返回 True = 这次插了。"""
    if not mat.use_nodes or mat.node_tree is None or _ours(mat):
        return False
    nt = mat.node_tree
    done = 0
    for out in [x for x in nt.nodes if x.bl_idname == "ShaderNodeOutputMaterial"]:
        sock = out.inputs["Surface"]
        if not sock.is_linked:
            continue
        src = sock.links[0].from_socket
        node = nt.nodes.new("ShaderNodeGroup")
        node.node_tree = tree
        node.name = node.label = NODE if done == 0 else "%s %d" % (NODE, done + 1)
        node.location = (out.location.x, out.location.y + 220)
        nt.links.new(src, node.inputs[0])
        nt.links.new(node.outputs[0], sock)
        done += 1
    if not done:
        return False
    # Eevee（4.2 以前）的「不透明」材质不会透明；4.2 起的新 Eevee 默认就能透明，也没有阴影模式了
    if OLD_EEVEE and (mat.blend_method == "OPAQUE" or mat.shadow_method == "OPAQUE"):
        mat[BLEND_PROP] = json.dumps([mat.blend_method, mat.shadow_method])
        if mat.blend_method == "OPAQUE":
            mat.blend_method = "HASHED"
        if mat.shadow_method == "OPAQUE":
            mat.shadow_method = "HASHED"
    return True


def detach(mat):
    """拿掉组节点，原来的连线接回去，混合模式还原。返回 True = 这次拿掉了。"""
    nodes = _ours(mat)
    nt = mat.node_tree if nodes else None
    for node in nodes:
        src = node.inputs[0].links[0].from_socket if node.inputs[0].is_linked else None
        targets = [l.to_socket for l in node.outputs[0].links]
        nt.nodes.remove(node)
        if src is not None:
            for sock in targets:
                nt.links.new(src, sock)
    if BLEND_PROP in mat:
        try:
            blend, shadow = json.loads(mat[BLEND_PROP])
            if OLD_EEVEE:
                mat.blend_method, mat.shadow_method = blend, shadow
        except (TypeError, ValueError):
            pass
        del mat[BLEND_PROP]
    return bool(nodes)


def remove_group_if_unused():
    tree = bpy.data.node_groups.get(GROUP)
    if tree is not None and tree.users == 0:
        bpy.data.node_groups.remove(tree)
        return True
    return False


def sync(garments, o, keep_for=None):
    """把外观设置用到这些衣服上：有一项打开就建节点组、写参数、插进它们的材质；都关了就从所有材质拿掉。
    keep_for(衣服) -> 留在身上的顶点序号（还没写属性的衣服现补）。返回说明文字列表。"""
    notes = []
    if not enabled(o) or not garments:
        n = sum(detach(m) for m in bpy.data.materials)
        remove_group_if_unused()
        if n:
            notes.append("外观关掉了，%d 个材质还原" % n)
        return notes
    tree = build_group()
    set_params(tree, o)
    mats, skipped = [], []
    for g in garments:
        for m in materials_of(g):
            if m in mats:
                continue
            mats.append(m)
            if not m.use_nodes:
                skipped.append(m.name)
            else:
                attach(m, tree)
    parts = []
    if o["fray"]:
        parts.append("撕口毛边 %.2g%% 身高" % o["fray_width"])
    if o["vanish"] != "NONE":
        parts.append("碎片%s（松开后第 %d 帧开始，用 %d 帧）" % ("淡出" if o["vanish"] == "FADE" else "溶解",
                                                       o["vanish_delay"], o["vanish_frames"]))
    notes.append("外观：%s，用在 %d 个材质上（在「材质预览」「渲染」视图和渲染里看得到）" % ("、".join(parts), len(mats) - len(skipped)))
    if skipped:
        notes.append("这些材质没用节点，外观不起作用：%s" % "、".join(skipped))
    return notes


def forget(obj, still_used):
    """撤掉一件衣服的外观：删它的属性；它的材质如果别的爆过的衣服（still_used）都不用，就拿掉组节点。
    返回做了什么（文字列表）。"""
    parts = ["外观属性"] if remove_attributes(obj) else []
    others = [g for g in still_used if g is not obj]
    used = {m for g in others for m in materials_of(g)}
    for m in materials_of(obj):
        if m not in used and detach(m):
            parts.append("材质 %s 还原" % m.name)
    if not others:
        remove_group_if_unused()
    return parts


def cleanup(scene=None):
    """全部清理：所有材质拿掉组节点、混合模式还原，网格上的 cb_ 属性删掉，节点组删掉。返回做了什么。"""
    scene = scene or bpy.context.scene
    done = []
    mats = [m.name for m in bpy.data.materials if detach(m)]
    if mats:
        done.append("材质还原：%s" % "、".join(mats))
    meshes = [o.name for o in scene.objects if o.type == "MESH" and remove_attributes(o)]
    if meshes:
        done.append("外观属性：%s" % "、".join(meshes))
    if remove_group_if_unused():
        done.append("节点组 " + GROUP)
    return done
