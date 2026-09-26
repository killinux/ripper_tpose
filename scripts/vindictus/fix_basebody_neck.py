"""基础身体换脸后的脖子接缝：把新脸的颈部 / 锁骨“围兜”贴到旧身体表面上，删掉被它盖住的旧身体，法线、肤色接上。

Fiona_BaseBody = 老版素体（裸体身体 + 贴身白 T 恤 / 短裤那层 `inner`，自带一个旧头）+ 现在的脸 + 头发。
build_blend.py 的 cut_legacy_head() 按主权重删掉旧头 / 旧脖子（不碰 `inner`）以后，两层皮在脖子根互相穿插：

- 新脸（MetaHuman 式的头）自带一圈“围兜”（顶点主权重在 spine_04 / clavicle_l / clavicle_r），前面浮在旧身体
  外面 1 cm 左右，穿上 T 恤时从衣服里透出来（一块方形肤色）；后背那片又沉在旧身体里面 1 cm 左右；
- 旧身体剩下的脖子根、100 个旧脸材质的碎面插在新脖子里；T 恤领口是照旧脖子做的，比新脖子宽。

这个素体要能脱掉 T 恤当裸体用，所以不能靠衣服遮：身体本身必须是完整的一层皮。做法（fit_face_to_body）：

1. 围兜贴到旧身体上：新脸每个顶点算“身体骨骼的权重占比” w（spine* / clavicle* / upperarm* 的权重 / 总权重），
   t = smoothstep(w 从 0.05 到 0.95)，顶点往旧身体皮肤上最近的点（沿那一点的平滑法线外移 offset）挪 t。
   w ≥ 0.95 的围兜完全贴上（和旧身体一个形状，T 恤本来就是照旧身体做的，穿上盖得住），脖子（w ≤ 0.05）
   不动，中间是过渡带。旧身体的脖子根比新脖子粗、还往前倾，过渡带太窄（第一次试的 w 0.1~0.7，只有 2 cm 左右）
   脖子根一圈会折出一道棱。
   过渡带里的位移量再在网格上平滑 20 遍（强度 4t(1-t)，两头不动）：旧脖子切口附近“最近点”跳来跳去、
   投到旧身体一块块平面上带来的小棱都磨掉；平滑的是位移，不是坐标，脸本身的形状细节不丢。
   围兜外沿（皮肤面的开放边）往里 edge_ramp 以内，外移量从 offset 慢慢降到 edge_offset（负数 = 压进旧皮下面）：
   外沿由旧皮盖住，两层在外沿里面交叉过去，贴着表面看也没有缝。外沿 keep_edge 以内不参与平滑。
2. 法线：两块网格都带自定义法线（PSK 里来的），自定义法线是相对面的方向存的，顶点一挪就歪了（后背那片和身体
   差 18° 左右，素模下看得出一道弧）。挪过的顶点重新写法线：t = 1 用旧身体在最近点的法线（重心插值），
   t = 0 用原来的，中间那圈过渡带用新形状自己的几何法线。围兜上的明暗因此和旁边的身体完全一样。
3. 骨骼权重（摆姿势用）：贴好的围兜（t = 1）改用旧身体在同一点的权重（Biped 骨，三角形重心插值），过渡带按 t
   和脸自己的权重混合；离 T 恤 garment_gap 以内的顶点全用身体的权重，到 garment_far 慢慢回到按 t 混合（领口边上）。
   不换的话静止姿势看不出来，一摆姿势围兜按脸的 UE 骨动、T 恤按身体的 Biped 骨动，肩膀、锁骨上的皮从衣服里穿出来。
4. 衣服底下留够空隙：围兜往外碰到 T 恤、空隙不到 garment_clearance 的几个顶点往里收（V 领下面的过渡带）；
   T 恤在盖住围兜的地方往外放，离围兜至少 garment_room（从衣服顶点往里量、也从围兜顶点往外量——衣服的面是平的，
   在锁骨这种凸的地方两个顶点之间更贴皮）。原因：旧皮每个顶点最多 4 根骨，XPS 也只存 4 个权重，围兜插值来的
   5~10 根骨被截断后，某些姿势会比衣服多偏 2 mm 左右。改衣服不改皮，脱掉 T 恤看的效果不变。
5. 旧身体：顶点沿法线正反 cover 以内碰到新脸皮肤 = 被围兜盖住；面的所有角和中心都被盖住才删，旧脸材质的残片全删。
   外沿那一圈只删围兜在上面的面（围兜压在下面的地方旧皮留着盖边）。
   删面、挪衣服会改变顶点的自定义法线（相对周围面存的），之前记下、之后原样写回——不然那一圈的明暗会变。

肤色（match_bib_tone）：围兜每个顶点记下贴上去那一点在旧身体贴图上的 UV；材质建好以后，两边贴图都先按块模糊，
逐顶点算 旧身体颜色 / 围兜颜色（含脸材质里 HSV、乘色节点的倍数），在网格上平滑 10 遍，按 w 从 1 过渡到这个比值，
写进顶点颜色属性 `bib_tone`，在脸皮肤材质的 Base Color 后面串一个 Mix MULTIPLY。围兜外沿因此和旁边的身体同色，
往脖子上慢慢回到脸本来的颜色。只动低频的色调，贴图细节保留。

踩过的坑（2026-09-26，前几版用户一眼看出不对）：
- 第一版按 T 恤领口高度把整片围兜切掉：领口比新脖子宽，空隙里只剩旧身体的皮（两侧各一条深色带）。
- 第二版按“是否盖在 T 恤外面”删围兜、按“离新皮肤多近”删旧身体：穿着 T 恤没问题，脱掉以后锁骨和后背一圈
  缺了皮（被删的围兜正好是两层之间的过渡）。“删掉挡在外面的那层”只在有衣服遮的时候成立。
- 第三版按 w 线性挪（t = w）：后背围兜原来沉在旧身体里 1 cm，w = 0.8 的地方只挪回去 80%，留下 1~2 mm 的凹坑，
  外沿附近 w 不到 1 的顶点还在旧身体下面，一圈旧皮从围兜里戳出来；再加上没重写法线、肤色用全局一个比值
  （前胸合适、后背偏亮），后背围兜下沿看得出一道弧。
- 围兜外沿浮在旧皮上面（+0.05 cm，旁边的旧皮再往下按一点免得戳出来）：正面看没问题，从侧面贴着肩膀顶看，
  视线从外沿底下的缝钻进去，看到围兜的背面，素模和贴图下都是一道细黑线。外沿要压在旧皮下面。
- `inner` 是一整件内衬，领口里面还有一层紧贴皮肤的“碗底”；在领口附近用射线判断“被 T 恤盖住”没有意义。
- 导出 XPS 摆姿势才发现：只贴形状不换权重，抬手 / 弯腰 / 转头时左肩领口大片皮肤从 T 恤里穿出来；换成身体权重后
  还剩领口边几个碎片（过渡带顶点带着脸的颈部修正骨），再加上领口附近按距离用身体权重、衣服放宽到 4 mm 才没有。
  试过把围兜权重限成 4 根骨：XPS 里没变化，Blender 里反而更差，没用。

长度参数按厘米给，unit = 场景单位对应的米数（Vindictus 是厘米场景，0.01）。

  blender -b <in.blend> --factory-startup --python fix_basebody_neck.py -- --out <out.blend>
      [--ramp 0.05,0.95] [--offset 0.05] [--edge-offset -0.05] [--edge-ramp 1.5] [--keep-edge 3] [--smooth 20]
      [--cover 0.5] [--tone 0.05,0.8] [--garment-gap 0.3] [--garment-far 1.5] [--garment-clearance 0.2]
      [--garment-room 0.4] [--face <脸网格物体名>] [--body <身体网格物体名>]
  （build_blend.py：造型之后调 fit_face_to_body()，材质建好之后调 match_bib_tone()）
"""
import re
import sys
from collections import namedtuple

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

TORSO_BONES = re.compile(r"^(spine|clavicle|upperarm|pectoral|breast)", re.I)
TONE_NODE = "bib tone -> body"
_BARY = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))

FitResult = namedtuple("FitResult", "moved deleted tucked samples")


def torso_weight(v, torso_groups):
    """顶点的权重里身体骨骼（脊柱 / 锁骨 / 上臂）占多少：1 = 围兜，0 = 脖子 / 头。"""
    total = sum(g.weight for g in v.groups)
    if total <= 0:
        return 0.0
    return sum(g.weight for g in v.groups if g.group in torso_groups) / total


def ramp(w, w0, w1):
    x = min(1.0, max(0.0, (w - w0) / (w1 - w0)))
    return x * x * (3 - 2 * x)


def skin_material(obj):
    """面数最多的材质 = 皮肤。"""
    counts = {}
    for p in obj.data.polygons:
        counts[p.material_index] = counts.get(p.material_index, 0) + 1
    return max(counts, key=counts.get) if counts else -1


class SkinSurface:
    """一组材质的三角面：最近点，以及那一点的平滑法线 / UV（按三角形重心插值，世界坐标）。"""

    def __init__(self, obj, materials):
        me = obj.data
        me.calc_loop_triangles()
        me.calc_normals_split()
        mw = obj.matrix_world
        nm = mw.to_3x3().inverted().transposed()
        self.co = [mw @ v.co for v in me.vertices]
        # 普通元组，不留网格数据的引用（换了文件 / 删了面以后还能用）
        self.tris = [(tuple(t.vertices), tuple(t.loops), t.material_index)
                     for t in me.loop_triangles if t.material_index in materials]
        self.normals = [(nm @ l.normal).normalized() for l in me.loops]
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        self.uvs = [uv[i].uv.copy() for i in range(len(me.loops))] if uv else None
        self.bvh = BVHTree.FromPolygons(self.co, [t[0] for t in self.tris], all_triangles=True)

    def nearest(self, p, reach):
        hit = self.nearest_tri(p, reach)
        return hit[:4] if hit else None

    def nearest_tri(self, p, reach):
        """(位置, 平滑法线, UV, 材质, 三角形的三个顶点, 重心坐标)。"""
        loc, _n, i, _d = self.bvh.find_nearest(p, reach)
        if loc is None:
            return None
        verts, loops, mat = self.tris[i]
        a, b, c = (self.co[k] for k in verts)
        bc = barycentric_transform(loc, a, b, c, *_BARY)
        if any(x != x for x in bc):                         # 退化三角形
            bc = Vector((1 / 3, 1 / 3, 1 / 3))
        l0, l1, l2 = loops
        n = (self.normals[l0] * bc.x + self.normals[l1] * bc.y + self.normals[l2] * bc.z).normalized()
        uv = None
        if self.uvs:
            uv = tuple(self.uvs[l0] * bc.x + self.uvs[l1] * bc.y + self.uvs[l2] * bc.z)
        return loc, n, uv, mat, verts, tuple(bc)


def vertex_weights(obj):
    """每个顶点的 {顶点组名: 权重}。"""
    names = {g.index: g.name for g in obj.vertex_groups}
    return [{names[g.group]: g.weight for g in v.groups if g.weight > 0 and g.group in names}
            for v in obj.data.vertices]


def blend_in_weights(obj, targets, min_w=1e-4, max_influences=0):
    """targets = {顶点: (t, {组名: 权重})}：顶点原来的权重（归一化）乘 1-t，加上 t 倍的目标权重，只留最大的
    max_influences 个（0 = 不限），再归一化；缺的顶点组按名字新建。返回改了的顶点数。
    默认不限：试过限成 4 个（旧身体每个顶点最多 4 根骨，XPS 也只存 4 个），XPS 里一样，Blender 里反而更差。"""
    names = {g.index: g.name for g in obj.vertex_groups}
    groups = {g.name: g for g in obj.vertex_groups}
    for vi, (t, target) in targets.items():
        v = obj.data.vertices[vi]
        old = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0}
        tot = sum(old.values()) or 1.0
        new = {k: (1 - t) * w / tot for k, w in old.items()}
        for k, w in target.items():
            new[k] = new.get(k, 0.0) + t * w
        new = {k: w for k, w in new.items() if w >= min_w}
        if max_influences and len(new) > max_influences:
            new = dict(sorted(new.items(), key=lambda kv: -kv[1])[:max_influences])
        s = sum(new.values()) or 1.0
        for k in old:
            if k not in new:
                groups[k].remove([vi])
        for k, w in new.items():
            if k not in groups:
                groups[k] = obj.vertex_groups.new(name=k)
            groups[k].add([vi], w / s, "REPLACE")
    return len(targets)


def _delete_faces(obj, indices):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in indices], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _set_loop_normals_through(obj, loop_normals, edit):
    """edit(obj) 会删面 / 挪顶点：删之前的自定义法线（物体空间，每个 loop 一个）记在一个 corner 属性里带过去，
    之后原样写回——自定义法线是相对面方向存的，旁边的面没了、顶点动了，它就跟着变。"""
    me = obj.data
    a = me.attributes.new("_fix_neck_n", "FLOAT_VECTOR", "CORNER")
    a.data.foreach_set("vector", [c for n in loop_normals for c in n])
    edit(obj)
    me = obj.data
    a = me.attributes["_fix_neck_n"]
    buf = [0.0] * (len(me.loops) * 3)
    a.data.foreach_get("vector", buf)
    me.attributes.remove(a)
    me.normals_split_custom_set([buf[i:i + 3] for i in range(0, len(buf), 3)])
    me.update()


def boundary_distance(obj, material, weights, min_w=0.5, limit=1e9):
    """沿网格边走到“围兜外沿”（该材质面的开放边、顶点 w > min_w）的距离（世界坐标，limit 以内）。"""
    import heapq
    me = obj.data
    mw = obj.matrix_world
    co = [mw @ v.co for v in me.vertices]
    edge_faces = {}
    for p in me.polygons:
        if p.material_index == material:
            for ek in p.edge_keys:
                edge_faces[ek] = edge_faces.get(ek, 0) + 1
    start = {v for ek, c in edge_faces.items() if c == 1 for v in ek if weights[v] > min_w}
    adj = {}
    for a, b in edge_faces:
        d = (co[a] - co[b]).length
        adj.setdefault(a, []).append((b, d))
        adj.setdefault(b, []).append((a, d))
    dist = {v: 0.0 for v in start}
    heap = [(0.0, v) for v in start]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist.get(v, 1e18):
            continue
        for u, l in adj.get(v, ()):
            nd = d + l
            if nd <= limit and nd < dist.get(u, 1e18):
                dist[u] = nd
                heapq.heappush(heap, (nd, u))
    return dist, start


def fit_face_to_body(face, body, garment="inner", legacy_materials=(), unit=0.01, ramp_w=(0.05, 0.95), offset=0.05,
                     edge_offset=-0.05, edge_ramp=1.5, keep_edge=3.0, smooth=20, reach=10.0, cover=0.5, garment_gap=0.3,
                     garment_far=1.5, garment_clearance=0.2, garment_room=0.4, log=print):
    """face / body：网格物体（静止姿势）。返回 FitResult(挪动的脸顶点数, 删掉的身体面数, 外沿压进旧皮的脸顶点数,
    samples = {脸顶点: (w, 旧身体上最近点的 UV, 那里的身体材质名)}，给 match_bib_tone 用)。
    围兜里面高出旧皮 offset；离外沿 edge_ramp 以内慢慢降到 edge_offset（负 = 压进旧皮下面），外沿由旧皮盖住：
    外沿要是浮在旧皮上面，贴着表面看（比如从侧面看肩膀顶）会从缝里看到围兜的背面，是一道黑线。"""
    s = 0.01 / unit
    names = [m.name.split(".")[0] if m else "" for m in body.data.materials]
    gidx = names.index(garment) if garment in names else -1
    legacy = {m.split(".")[0] for m in legacy_materials}
    legacy_idx = {i for i, n in enumerate(names) if n in legacy}
    skin_mats = {i for i in range(len(names)) if i != gidx and i not in legacy_idx}
    surf = SkinSurface(body, skin_mats)                      # 旧身体的皮（不含衣服、旧脸残片）
    body_vw = vertex_weights(body)                           # 删面之前取（顶点编号会变）

    # 1) 围兜按身体骨骼权重贴到旧身体表面（外沿一圈压进旧皮下面）；2) 挪过的顶点重写法线；
    # 3) 贴上去的部分改用旧身体在同一点的骨骼权重（按 t 混合），摆姿势时和身体、T 恤一起动
    fme = face.data
    fme.calc_normals_split()
    orig_n = [l.normal.copy() for l in fme.loops]
    fmw = face.matrix_world
    fmwi = fmw.inverted()
    to_local = fmw.to_3x3().transposed()                     # 世界 -> 物体空间的法线
    torso_groups = {g.index for g in face.vertex_groups if TORSO_BONES.match(g.name)}
    weights = [torso_weight(v, torso_groups) for v in fme.vertices]
    fskin = skin_material(face)
    skin_vs = {vi for p in fme.polygons if p.material_index == fskin for vi in p.vertices}
    bdist, rim = boundary_distance(face, fskin, weights, limit=3 * edge_ramp * s)
    samples, blend, disp, wmix = {}, {}, {}, {}
    tucked = 0
    for v in fme.vertices:
        w = weights[v.index]
        if w <= 1e-3:
            continue
        co = fmw @ v.co
        hit = surf.nearest_tri(co, reach * s)
        if hit is None:
            continue
        loc, n, uv, mi, tri, bc = hit
        samples[v.index] = (w, uv, names[mi])
        t = ramp(w, *ramp_w)
        if t > 0:
            off = offset
            d = bdist.get(v.index)
            if d is not None and d < edge_ramp * s:
                off = edge_offset + (offset - edge_offset) * ramp(d, 0.0, edge_ramp * s)
                tucked += off < 0
            disp[v.index] = co.lerp(loc + n * off * s, t) - co
            blend[v.index] = (t, (to_local @ n).normalized())
        sw = {}
        for k, b in zip(tri, bc):
            for g, gw in body_vw[k].items():
                sw[g] = sw.get(g, 0.0) + b * gw
        tot = sum(sw.values())
        if tot > 0:
            wmix[v.index] = (t, {g: gw / tot for g, gw in sw.items()})
    # 过渡带里的位移场在网格上平滑：旧脖子切口附近最近点跳来跳去、投到旧身体一块块平面上带来的棱磨掉，
    # 脸本身的形状细节不动。强度 4t(1-t)：带子中间最强，两头（贴好的围兜 / 没挪的脖子）不动，接得上；
    # 围兜外沿 keep_edge 以内（要和旧皮精确交叉）也不动
    free = {vi: 4 * t * (1 - t) for vi, (t, _n) in blend.items()
            if t < 1 and bdist.get(vi, 1e18) >= keep_edge * s}
    adj = {vi: [] for vi in free}
    for e in fme.edges:
        a, b = e.vertices
        if a in adj:
            adj[a].append(b)
        if b in adj:
            adj[b].append(a)
    zero = Vector()
    for _ in range(smooth):
        upd = {}
        for vi, k in free.items():
            nb = adj[vi]
            if nb:
                avg = sum((disp.get(j, zero) for j in nb), Vector()) / len(nb)
                upd[vi] = disp[vi].lerp(avg, 0.5 * k)
        disp.update(upd)
    for vi, d in disp.items():
        v = fme.vertices[vi]
        v.co = fmwi @ (fmw @ v.co + d)
    fme.update()
    # 衣服底下留够空隙：T 恤离旧身体的皮至少 2 mm（游戏里就是这么做的），过渡带在 V 领下面比旧皮鼓，只剩 0.7 mm，
    # 一摆姿势就顶穿。沿法线往外打射线碰到衣服、空隙不到 garment_clearance 的顶点往里收，收的量向周围摊开几圈免得有坑；
    # 领口开口里露在外面的脖子（往外碰不到衣服）不动
    gbvh = None
    if gidx >= 0:
        bmw = body.matrix_world
        gco = [bmw @ v.co for v in body.data.vertices]
        gbvh = BVHTree.FromPolygons(gco, [tuple(p.vertices) for p in body.data.polygons if p.material_index == gidx],
                                    all_triangles=False)
    tightened = 0
    if gbvh is not None and garment_clearance > 0:
        bm = bmesh.new()
        bm.from_mesh(fme)
        bm.normal_update()
        wn = [(fmw.to_3x3() @ v.normal).normalized() for v in bm.verts]
        bm.free()
        cand = [vi for vi in samples if vi in skin_vs]
        push = {}
        for vi in cand:
            co = fmw @ fme.vertices[vi].co
            hit = gbvh.ray_cast(co, wn[vi], 1.0 * s)
            if hit[0] is not None and hit[3] < garment_clearance * s:
                push[vi] = garment_clearance * s - hit[3]
        tightened = len(push)
        nbr = {vi: [] for vi in cand}
        for e in fme.edges:
            a, b = e.vertices
            if a in nbr and b in nbr:
                nbr[a].append(b)
                nbr[b].append(a)
        for _ in range(4):
            spread = {}
            for vi in cand:
                around = [push.get(j, 0.0) for j in nbr[vi]]
                p = max(push.get(vi, 0.0), 0.5 * sum(around) / len(around) if around else 0.0)
                if p > 1e-6:
                    spread[vi] = p
            push = spread
        for vi, p in push.items():
            v = fme.vertices[vi]
            v.co = fmwi @ (fmw @ v.co - wn[vi] * p)
        fme.update()
    bm = bmesh.new()
    bm.from_mesh(fme)
    bm.normal_update()
    geom = [v.normal.copy() for v in bm.verts]
    bm.free()
    new_n = []
    for l in fme.loops:
        e = blend.get(l.vertex_index)
        if e is None:
            new_n.append(orig_n[l.index])
            continue
        t, nb = e
        n = orig_n[l.index].lerp(nb, t).lerp(geom[l.vertex_index], 4 * t * (1 - t))
        new_n.append(n.normalized())
    fme.normals_split_custom_set(new_n)
    fme.update()
    # 骨骼权重：贴好的围兜（t = 1）完全用旧身体在同一点的权重（Biped 骨），过渡带按 t 和脸自己的权重混合。
    # 不换的话静止姿势看不出来，一摆姿势（抬手、转头）围兜按脸的 UE 骨动、T 恤按身体的 Biped 骨动，肩膀上皮从衣服里穿出来。
    # 离衣服近的过渡带顶点也改用身体的权重：离衣服 garment_gap 以内全用，到 garment_far 慢慢回到按 t 混合。
    # 它们在领口边上（衣服底下或领口开口里），权重和衣服不一样，一转头、弯腰就从领口顶出来
    near_cloth = 0
    if gbvh is not None and garment_gap > 0:
        for vi, (t, sw) in list(wmix.items()):
            if t >= 1:
                continue
            co = fmw @ fme.vertices[vi].co
            loc, _n, _i, d = gbvh.find_nearest(co, garment_far * s)
            if loc is None:
                continue
            c = 1.0 - ramp(d / s, garment_gap, garment_far)  # 离衣服 gap 以内 1，到 far 慢慢降到 0
            if c > t:
                wmix[vi] = (c, sw)
                near_cloth += 1
    reweighted = blend_in_weights(face, {vi: e for vi, e in wmix.items() if e[0] > 0})

    # 4) 被贴好的围兜盖住的旧身体面、旧脸残片：删。外沿那一圈（围兜压在旧皮下面）只删围兜在上面的面，
    #    剩下的旧皮盖住围兜的边，两层在外沿里面平滑地交叉过去
    skin_polys = [p for p in fme.polygons if p.material_index == fskin]
    fco = [fmw @ v.co for v in fme.vertices]
    skin = BVHTree.FromPolygons(fco, [tuple(p.vertices) for p in skin_polys], all_triangles=False)
    near_edge = 1.2 * edge_ramp * s
    bme = body.data
    bme.calc_normals_split()
    loop_n = [l.normal.copy() for l in bme.loops]
    bw = body.matrix_world
    bn = bw.to_3x3().inverted().transposed()
    garment_vs = {vi for p in bme.polygons if p.material_index == gidx for vi in p.vertices}
    vsum = [Vector() for _ in bme.vertices]
    for l in bme.loops:
        vsum[l.vertex_index] += l.normal

    def covered(co, n):
        loc, _n, i, d = skin.ray_cast(co - n * cover * s, n, 2 * cover * s)
        if loc is None:
            return False
        if min(bdist.get(vi, 1e18) for vi in skin_polys[i].vertices) < near_edge:
            return d - cover * s > 0.005 * s                 # 外沿附近：围兜得在上面
        return True

    hidden = set()
    for v in bme.vertices:
        if v.index in garment_vs or vsum[v.index].length < 1e-8:
            continue
        if covered(bw @ v.co, (bn @ vsum[v.index]).normalized()):
            hidden.add(v.index)
    doomed = []
    for p in bme.polygons:
        if p.material_index in legacy_idx:
            doomed.append(p.index)
        elif p.material_index != gidx and all(i in hidden for i in p.vertices) and \
                covered(bw @ p.center, (bn @ p.normal).normalized()):
            doomed.append(p.index)

    # 5) T 恤在盖住围兜的地方往外放一点，离围兜至少 garment_room（旧皮在衣服底下是 2~3 mm）。
    #    XPS 每个顶点只存 4 个骨骼权重，围兜插值来的权重被截断后，某些姿势会比 T 恤多偏 2 mm 左右，从锁骨上穿出一点；
    #    改衣服不改皮肤，脱掉 T 恤看的效果不变，穿着看不出衣服动过（< 1 mm）
    tee_move = {}
    if gidx >= 0 and garment_room > 0:
        tee_vs = sorted(garment_vs)
        tnb = {vi: [] for vi in tee_vs}
        for e in bme.edges:
            a, b = e.vertices
            if a in tnb and b in tnb:
                tnb[a].append(b)
                tnb[b].append(a)
        tn = {vi: (bn @ vsum[vi]).normalized() for vi in tee_vs if vsum[vi].length > 1e-8}
        push = {}
        for vi, n in tn.items():                              # 从衣服顶点往里量
            hit = skin.ray_cast(bw @ bme.vertices[vi].co, -n, 1.0 * s)
            if hit[0] is not None and hit[3] < garment_room * s:
                push[vi] = garment_room * s - hit[3]
        # 再从围兜顶点往外量：衣服的面是平的，在锁骨这种凸的地方两个顶点之间离皮肤更近；碰到的那块衣服整体往外推
        tee_polys = [tuple(p.vertices) for p in bme.polygons if p.material_index == gidx]
        tbvh = BVHTree.FromPolygons([bw @ v.co for v in bme.vertices], tee_polys, all_triangles=False)
        for vi in skin_vs:
            if vi not in samples:
                continue
            hit = tbvh.ray_cast(fmw @ fme.vertices[vi].co, (fmw.to_3x3() @ geom[vi]).normalized(), 1.0 * s)
            if hit[0] is not None and hit[3] < garment_room * s:
                for tv in tee_polys[hit[2]]:
                    if tv in tn:
                        push[tv] = max(push.get(tv, 0.0), garment_room * s - hit[3])
        for _ in range(4):
            spread = {}
            for vi in tn:
                around = [push.get(j, 0.0) for j in tnb[vi]]
                p = max(push.get(vi, 0.0), 0.5 * sum(around) / len(around) if around else 0.0)
                if p > 1e-6:
                    spread[vi] = p
            push = spread
        bwi = bw.inverted()
        tee_move = {vi: bwi @ (bw @ bme.vertices[vi].co + tn[vi] * p) for vi, p in push.items()}

    def edit(obj):
        for vi, co in tee_move.items():
            obj.data.vertices[vi].co = co
        _delete_faces(obj, doomed)

    _set_loop_normals_through(body, loop_n, edit)
    log("fit_face_to_body: %d face verts pulled onto the old body (w %.2f-%.2f ramp, displacement smoothed x%d on %d "
        "verts), %d verts moved in to keep %.1f cm under the %s, normals rewritten, %d verts take the body's bone weights "
        "(by t; %d more near the collar), "
        "outer edge (%d rim verts) tucked %.2f cm under the old skin (%d verts); body -%d faces under the bib or legacy (%s); "
        "%s eased out over the bib (%d verts, >= %.1f cm room)" % (
            len(blend), ramp_w[0], ramp_w[1], smooth, len(free), tightened, garment_clearance, garment, reweighted,
            near_cloth, len(rim), -edge_offset,
            tucked, len(doomed), ", ".join(sorted(legacy)) or "-", garment, len(tee_move), garment_room))
    return FitResult(len(blend), len(doomed), tucked, samples)


# ---------------------------------------------------------------- tone
def _srgb_to_linear(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _image_array(img):
    import numpy as np
    w, h = img.size
    if not w or not h:
        return None
    buf = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(buf)
    a = buf.reshape(h, w, img.channels)[:, :, :3]
    return _srgb_to_linear(a) if img.colorspace_settings.name == "sRGB" else a


class BlurredTexture:
    """贴图按 block x block 求平均（去掉毛孔、痣这种细节），双线性取样；v = 0 是图片最下面一行（Blender 的像素顺序）。"""

    def __init__(self, img, block=16):
        import numpy as np
        a = _image_array(img)
        if a is None:
            raise ValueError("image %s has no pixels" % img.name)
        h, w = a.shape[:2]
        b = max(1, min(block, h, w))
        hh, ww = h // b, w // b
        self.a = a[:hh * b, :ww * b].reshape(hh, b, ww, b, 3).mean(axis=(1, 3))
        self.h, self.w = hh, ww
        self.np = np

    def __call__(self, uv):
        x = (uv[0] % 1.0) * self.w - 0.5
        y = (uv[1] % 1.0) * self.h - 0.5
        x0, y0 = int(self.np.floor(x)), int(self.np.floor(y))
        fx, fy = x - x0, y - y0

        def px(i, j):
            return self.a[min(self.h - 1, max(0, j)), min(self.w - 1, max(0, i))]

        return (px(x0, y0) * (1 - fx) * (1 - fy) + px(x0 + 1, y0) * fx * (1 - fy)
                + px(x0, y0 + 1) * (1 - fx) * fy + px(x0 + 1, y0 + 1) * fx * fy)


def _base_color_chain(mat):
    """(贴图节点, 贴图之后到 Base Color 的倍数)：认 build_blend 的两种皮肤写法——贴图直连，或者
    贴图 -> 色相/饱和度/明度（只看 Value）-> Mix MULTIPLY（肤色）。已经串上的 TONE_NODE 不算。"""
    tree = mat.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if tree else None
    gain = [1.0, 1.0, 1.0]
    if bsdf is None:
        return None, gain
    node = bsdf.inputs["Base Color"].links[0].from_node if bsdf.inputs["Base Color"].is_linked else None
    while node is not None and node.type != "TEX_IMAGE":
        if node.type == "MIX_RGB" and node.blend_type == "MULTIPLY":
            if node.name != TONE_NODE:
                c = node.inputs["Color2"].default_value
                fac = node.inputs["Fac"].default_value
                gain = [g * (1 - fac + fac * c[i]) for i, g in enumerate(gain)]
            node = node.inputs["Color1"].links[0].from_node if node.inputs["Color1"].is_linked else None
        elif node.type == "HUE_SAT":
            v = node.inputs["Value"].default_value
            fac = node.inputs["Fac"].default_value
            gain = [g * (1 - fac + fac * v) for g in gain]
            node = node.inputs["Color"].links[0].from_node if node.inputs["Color"].is_linked else None
        else:
            return None, gain
    return node, gain


def match_bib_tone(face, body, samples, tone_w=(0.05, 0.8), block=16, passes=10, attr="bib_tone", log=print):
    """围兜的肤色逐顶点往旧身体上对应那一点的肤色靠（材质建好以后调；samples 来自 fit_face_to_body）。"""
    import numpy as np
    fme = face.data
    fskin = skin_material(face)
    fmat = fme.materials[fskin]
    ftex, fgain = _base_color_chain(fmat)
    if ftex is None or ftex.image is None:
        log("match_bib_tone: face skin texture not found, nothing done")
        return None
    fblur = BlurredTexture(ftex.image, block)
    fgain = np.array(fgain)
    needed = {bname for _w, _uv, bname in samples.values()}
    bodies = {}
    for m in body.data.materials:
        key = m.name.split(".")[0] if m else ""
        if key not in needed or key in bodies:
            continue
        tex, gain = _base_color_chain(m)
        bodies[key] = (BlurredTexture(tex.image, block), np.array(gain)) if tex is not None and tex.image else None
    uv = fme.uv_layers.active.data
    fcol = {}
    for p in fme.polygons:
        if p.material_index != fskin:
            continue
        for li in p.loop_indices:
            vi = fme.loops[li].vertex_index
            if vi in samples:
                fcol.setdefault(vi, []).append(fblur(uv[li].uv))
    ratio = {}
    for vi, cols in fcol.items():
        _w, buv, bname = samples[vi]
        src = bodies.get(bname)
        if buv is None or src is None:
            continue
        bc = src[0](buv) * src[1]
        fc = np.mean(cols, axis=0) * fgain
        ratio[vi] = np.clip(bc / np.maximum(fc, 1e-4), 0.5, 2.0)
    if not ratio:
        log("match_bib_tone: no bib samples, nothing done")
        return None
    nbrs = {vi: [] for vi in ratio}
    for e in fme.edges:
        a, b = e.vertices
        if a in ratio and b in ratio:
            nbrs[a].append(b)
            nbrs[b].append(a)
    for _ in range(passes):
        ratio = {vi: (0.5 * r + 0.5 * np.mean([ratio[j] for j in nbrs[vi]], axis=0)) if nbrs[vi] else r
                 for vi, r in ratio.items()}
    layer = fme.color_attributes.get(attr) or fme.color_attributes.new(attr, "FLOAT_COLOR", "POINT")
    cols = np.ones((len(fme.vertices), 4), dtype=np.float32)
    edge = []
    for vi, r in ratio.items():
        w = samples[vi][0]
        tt = ramp(w, *tone_w)
        cols[vi, :3] = 1 + (r - 1) * tt
        if tt > 0.99:
            edge.append(r)
    layer.data.foreach_set("color", cols.ravel())

    tree = fmat.node_tree
    bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    if TONE_NODE not in tree.nodes:
        src = bsdf.inputs["Base Color"].links[0].from_socket
        attr_node = tree.nodes.new("ShaderNodeVertexColor")
        attr_node.name = attr_node.label = TONE_NODE + " (attr)"
        attr_node.location = (bsdf.location.x - 400, bsdf.location.y + 300)
        mix = tree.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.name = mix.label = TONE_NODE
        mix.location = (bsdf.location.x - 200, bsdf.location.y + 200)
        mix.inputs["Fac"].default_value = 1.0
        tree.links.new(src, mix.inputs["Color1"])
        tree.links.new(attr_node.outputs["Color"], mix.inputs["Color2"])
        tree.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    tree.nodes[TONE_NODE + " (attr)"].layer_name = attr
    e = np.array(edge) if edge else np.array(list(ratio.values()))
    log("match_bib_tone: %d bib verts, per-vertex body/bib ratio (outer bib: min %s, median %s, max %s), attr %s" % (
        len(ratio), np.round(e.min(axis=0), 3).tolist(), np.round(np.median(e, axis=0), 3).tolist(),
        np.round(e.max(axis=0), 3).tolist(), attr))
    return ratio


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fit_opts, tone_opts = {}, {}
    for flag, key, kind, dest in (("--ramp", "ramp_w", "pair", fit_opts), ("--offset", "offset", "float", fit_opts),
                                  ("--edge-offset", "edge_offset", "float", fit_opts),
                                  ("--edge-ramp", "edge_ramp", "float", fit_opts),
                                  ("--keep-edge", "keep_edge", "float", fit_opts), ("--smooth", "smooth", "int", fit_opts),
                                  ("--cover", "cover", "float", fit_opts), ("--tone", "tone_w", "pair", tone_opts),
                                  ("--garment-gap", "garment_gap", "float", fit_opts),
                                  ("--garment-far", "garment_far", "float", fit_opts),
                                  ("--garment-clearance", "garment_clearance", "float", fit_opts),
                                  ("--garment-room", "garment_room", "float", fit_opts)):
        if flag in argv:
            val = argv[argv.index(flag) + 1]
            dest[key] = tuple(float(x) for x in val.split(",")) if kind == "pair" else (
                int(val) if kind == "int" else float(val))

    out = argv[argv.index("--out") + 1] if "--out" in argv else bpy.data.filepath
    # 物体名：自动构建是 <模型>_Face / <模型>_BaseBody；手工组装的文件可以用 --face / --body 指定
    face = bpy.data.objects[argv[argv.index("--face") + 1]] if "--face" in argv else next(
        o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith("_Face"))
    body = bpy.data.objects[argv[argv.index("--body") + 1]] if "--body" in argv else next(
        o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith("_BaseBody"))
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "neck_01" in o.data.bones)
    neck = rig.matrix_world @ rig.data.bones["neck_01"].head_local
    legacy = [m.name for m in body.data.materials if m and ("face" in m.name.lower() or "hair" in m.name.lower())]
    unit = 0.01 if neck.z > 10 else 1.0
    res = fit_face_to_body(face, body, legacy_materials=legacy, unit=unit, **fit_opts)
    match_bib_tone(face, body, res.samples, **tone_opts)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=out, copy=out != bpy.data.filepath)
    print("SAVED", out)


if __name__ == "__main__":
    main()
