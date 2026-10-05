# -*- coding: utf-8 -*-
"""碎片飞散（给 MMD 用的爆衣）的几何部分：把一份衣服的副本切成撕裂状的碎片，每块挂一根骨头，再把飞出去、落到地上
算成两个形态键（mmd_tools 导出时就是顶点表情 爆衣 / 爆衣落下）。不依赖 mmd_tools：任何用骨架蒙皮的网格都行，
mmd.py 把它接到 mmd_tools 的模型上，scripts/riseoferos 的批量也用它。

碎片：衣服里连在一起的一块（共边的面；同一位置的顶点算一个——网格沿 UV 缝是断开的）比 size x whole 小就整块飞
（护甲片、圆环）；大的切成约 size 大小：最远点采样撒种子，每个面归到沿面走过去最近的种子，每一步的长度乘一个随机
系数（jitter，边界像撕开的布一样锯齿），相邻面属于不同碎片的边切开。
骨头：每块碎片 100 % 挂到一根骨头上——它的权重最多的那根，往上找到第一根主骨骼（骨盆、脊椎、四肢、手指；不是
物理骨、扭转骨、辅助骨）。顶点表情在蒙皮之前移动顶点，挂在几根骨头上的碎片飞到一米外时会被扯成条；挂一根骨头
它是一整块硬片，还跟着身体动。
飞行：爆衣 = 沿碎片下面身体表面的法线飞出去（加随机偏转和一点上扬）并转一个角度；爆衣落下 = 再落到地面
（模型最低点）、接着转、往外漂一点。两个都到 1 时碎片落在地上。尺寸按身高 1.6 米给，按模型实际高度缩放。
"""
import heapq
import math
import random
import re

import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

THROW_KEY, FALL_KEY = "爆衣", "爆衣落下"
REFERENCE_HEIGHT = 1.6       # 下面的长度按这个身高给，按模型实际高度缩放
DEFAULTS = {
    "size": 0.10,            # 碎片大小（米）
    "whole": 1.5,            # 比 size x whole 小的块整块飞
    "jitter": 0.8,           # 边界锯齿程度
    "throw_min": 0.15, "throw_max": 0.35,      # 飞出去多远（米）
    "tilt": 0.35,            # 方向的随机偏转（其余是身体表面法线）
    "lift": 0.25,            # 往上的分量
    "turn_min": 15.0, "turn_max": 45.0,        # 飞出时转多少度
    "fall_turn_min": 30.0, "fall_turn_max": 90.0,  # 落下时再转多少度
    "drift_min": 0.05, "drift_max": 0.25,      # 落下时往外漂多远（米）
    "land": 0.01,            # 落地时碎片中心离地面多高（米）
    "seed": 1,
}
WELD = 1e-5          # 同一位置算一个顶点（米，按 1.6 米身高；跟着模型高度缩放：导入缩放 0.08 和 1.0 结果一样）
# 主骨骼：MMD 标准骨骼名，和没转换过的 3ds Max Biped 骨骼
CORE_MMD = re.compile(r"^(センター|グルーブ|腰|下半身|上半身[123]?|首|頭|[左右](肩|腕|ひじ|手首|足|ひざ|足首|足D|ひざD|足首D|足先EX)"
                      r"|[左右](親指|人指|中指|薬指|小指)[０-３0-3])$")
CORE_BIPED = re.compile(r"^Bip0\d\d( ?[LR])? ?(Pelvis|Spine\d*|Neck\d*|Head|Clavicle|UpperArm|UpArm|Forearm|ForeArm"
                        r"|Hand|Finger\d+|Thigh|Calf|Foot|Toe\d*)$", re.IGNORECASE)
TWIST = re.compile(r"捩|twist", re.IGNORECASE)


def is_core(name):
    return bool((CORE_MMD.match(name) or CORE_BIPED.match(name)) and not TWIST.search(name))


def world_co(obj):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    m = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def surface(points, triangles):
    """BVH of a surface (world space points, triangles as index triples)."""
    return BVHTree.FromPolygons([Vector(p) for p in points], [tuple(t) for t in triangles])


def random_unit(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.01 < v.length <= 1.0:
            return v.normalized()


def weld_ids(points, tol=WELD):
    keys = np.round(points / tol).astype(np.int64)
    _, ids = np.unique(keys, axis=0, return_inverse=True)
    return ids.ravel()


def fragments(bm, world, size, whole, jitter, rng, weld=WELD):
    """{face index: fragment id}, whole pieces, cut pieces."""
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    vid = weld_ids(world, weld)
    faces = list(bm.faces)
    centre = np.array([world[[v.index for v in f.verts]].mean(0) for f in faces])
    area = np.zeros(len(faces))
    for f in faces:
        q = world[[v.index for v in f.verts]]
        area[f.index] = 0.5 * np.linalg.norm(np.cross(q[1:-1] - q[0], q[2:] - q[0]).sum(0))
    by_edge = {}
    for f in faces:
        vs = [vid[v.index] for v in f.verts]
        for a, b in zip(vs, vs[1:] + vs[:1]):
            by_edge.setdefault((min(a, b), max(a, b)), []).append(f.index)
    near = [[] for _ in faces]
    for fs in by_edge.values():
        for i in fs:
            for j in fs:
                if i != j:
                    near[i].append(j)
    label = np.full(len(faces), -1, dtype=np.int64)
    piece = np.full(len(faces), -1, dtype=np.int64)
    pieces = 0
    for start in range(len(faces)):
        if piece[start] >= 0:
            continue
        stack, piece[start] = [start], pieces
        while stack:
            i = stack.pop()
            for j in near[i]:
                if piece[j] < 0:
                    piece[j] = pieces
                    stack.append(j)
        pieces += 1
    next_id, n_whole, n_cut = 0, 0, 0
    for p in range(pieces):
        members = np.nonzero(piece == p)[0]
        pts = world[np.unique([v.index for i in members for v in faces[i].verts])]
        extent = float((pts.max(0) - pts.min(0)).max())
        if extent < size * whole or len(members) < 8:
            label[members] = next_id
            next_id += 1
            n_whole += 1
            continue
        n_cut += 1
        k = max(2, int(round(area[members].sum() / (size * size))))
        k = min(k, len(members) // 4 or 1)
        seeds = [int(members[rng.randrange(len(members))])]
        dist = np.linalg.norm(centre[members] - centre[seeds[0]], axis=1)
        while len(seeds) < k:
            far = int(members[int(np.argmax(dist))])
            seeds.append(far)
            dist = np.minimum(dist, np.linalg.norm(centre[members] - centre[far], axis=1))
        best = {int(i): math.inf for i in members}
        todo = []
        for s_i, s in enumerate(seeds):
            best[s] = 0.0
            label[s] = next_id + s_i
            heapq.heappush(todo, (0.0, s, next_id + s_i))
        jit = {}
        while todo:
            d, i, lab = heapq.heappop(todo)
            if d > best[i]:
                continue
            label[i] = lab
            for j in near[i]:
                key = (min(i, j), max(i, j))
                if key not in jit:
                    jit[key] = 1.0 + jitter * rng.random()
                nd = d + float(np.linalg.norm(centre[i] - centre[j])) * jit[key]
                if nd < best.get(j, math.inf):
                    best[j] = nd
                    heapq.heappush(todo, (nd, j, lab))
        next_id += len(seeds)
    return label, n_whole, n_cut


LR_RENAMED = re.compile(r"^(.+)[._]([LR])$")


def mmd_name(arm, bone):
    """The bone's MMD name.  mmd_tools keeps it in the pose bone's mmd_bone.name_j: its import option "rename bones"
    (on by default) makes the Blender names 腕.L / ひじ.R ..., which the main-bone names here never match - every arm
    and leg fragment then went up to 上半身2 / 下半身 and stayed there when the arms moved.  Without mmd_tools data:
    腕.L / 腕_L read back as 左腕."""
    pb = arm.pose.bones.get(bone.name)
    name = getattr(getattr(pb, "mmd_bone", None), "name_j", "") if pb is not None else ""
    if name:
        return name
    m = LR_RENAMED.match(bone.name)
    return ("左" if m.group(2) == "L" else "右") + m.group(1) if m else bone.name


def core_map(arm, excluded=()):
    """{bone: the bone a fragment on it is skinned to}: itself or its first ancestor that is a main skeleton bone
    (is_core, by its MMD name) and not in `excluded` (bones physics drives); the top bone when none is."""
    out = {}
    for bone in arm.data.bones:
        b, last = bone, bone
        while b is not None:
            if is_core(mmd_name(arm, b)) and b.name not in excluded:
                break
            last = b
            b = b.parent
        out[bone.name] = (b or last).name
    return out


def rigid_weights(obj, vert_label, mapping):
    """Every fragment 100 % on one bone: its weights summed after moving each group to mapping[group], the biggest
    wins.  Only groups named after bones (mapping's keys) count and are replaced; the rest stay (mmd_tools keeps the
    edge scale in a group mmd_edge_scale - weight 1 everywhere, it would win every fragment).  Returns
    {bone: fragments}."""
    names = {g.index: g.name for g in obj.vertex_groups if g.name in mapping}
    acc = {}
    for v in obj.data.vertices:
        lab = vert_label[v.index]
        if lab < 0:
            continue
        for g in v.groups:
            if g.weight > 0 and g.group in names:
                bone = mapping[names[g.group]]
                acc.setdefault(lab, {})
                acc[lab][bone] = acc[lab].get(bone, 0.0) + g.weight
    chosen = {lab: max(w, key=w.get) for lab, w in acc.items()}
    members = {}
    for i, lab in enumerate(vert_label):
        if lab in chosen:
            members.setdefault(chosen[lab], []).append(i)
    for g in [g for g in obj.vertex_groups if g.name in mapping]:
        obj.vertex_groups.remove(g)
    for bone, verts in members.items():
        obj.vertex_groups.new(name=bone).add(verts, 1.0, "REPLACE")
    count = {}
    for bone in chosen.values():
        count[bone] = count.get(bone, 0) + 1
    return count


def shatter(obj, body_tree, floor, height, opts, mapping=None):
    """Cut obj (a copy of the clothes, nothing else on it) into fragments, skin each to one bone (mapping, see
    core_map; None = leave the weights) and add the shape keys THROW_KEY / FALL_KEY.  body_tree: BVH of the body
    in world space (the normal under each fragment); floor: world z the fragments land on; height: the model's
    height (scales the lengths in opts).  Returns a report."""
    o = dict(DEFAULTS, **(opts or {}))
    k = height / REFERENCE_HEIGHT if height > 0 else 1.0
    rng = random.Random(o["seed"])
    me = obj.data
    if me.shape_keys:
        for key in reversed(list(me.shape_keys.key_blocks)):
            obj.shape_key_remove(key)
    bm = bmesh.new()
    bm.from_mesh(me)
    world = world_co(obj)
    label, n_whole, n_cut = fragments(bm, world, o["size"] * k, o["whole"], o["jitter"], rng, WELD * k)
    bm.faces.ensure_lookup_table()
    split = [e for e in bm.edges if len(e.link_faces) == 2
             and label[e.link_faces[0].index] != label[e.link_faces[1].index]]
    bmesh.ops.split_edges(bm, edges=split)
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    vert_label = np.full(len(bm.verts), -1, dtype=np.int64)
    for v in bm.verts:
        labs = {label[f.index] for f in v.link_faces}
        if labs:
            vert_label[v.index] = min(labs)
    bm.to_mesh(me)
    bm.free()
    me.update()
    bones = rigid_weights(obj, vert_label, mapping) if mapping is not None else {}
    world = world_co(obj)
    inv = np.array(obj.matrix_world.inverted())
    up = Vector((0.0, 0.0, 1.0))
    key1, key2 = world.copy(), world.copy()
    count = 0
    for lab in np.unique(vert_label[vert_label >= 0]):
        idx = np.nonzero(vert_label == lab)[0]
        p = world[idx]
        c = Vector(p.mean(0))
        hit = body_tree.find_nearest(c) if body_tree is not None else (None, None, None, None)
        normal = hit[1] if hit[0] is not None else (c - Vector((0.0, 0.0, c.z))).normalized()
        direction = (normal + o["tilt"] * random_unit(rng) + o["lift"] * up).normalized()
        throw = rng.uniform(o["throw_min"], o["throw_max"]) * k
        r1 = np.array(Matrix.Rotation(math.radians(rng.uniform(o["turn_min"], o["turn_max"])), 3, random_unit(rng)))
        r2 = np.array(Matrix.Rotation(math.radians(rng.uniform(o["fall_turn_min"], o["fall_turn_max"])), 3,
                                      random_unit(rng)))
        flat = Vector((direction.x, direction.y, 0.0))
        flat = flat.normalized() if flat.length > 1e-6 else random_unit(rng)
        top = c + direction * throw
        drop = Vector(flat * rng.uniform(o["drift_min"], o["drift_max"]) * k) + Vector(
            (0.0, 0.0, floor + o["land"] * k - top.z))
        rel = p - np.array(c)
        key1[idx] = np.array(c) + rel @ r1.T + np.array(direction * throw)
        # 爆衣落下 adds to 爆衣: both at 1 put the fragment at c + r2 r1 (p - c) + throw + drop
        key2[idx] = p + rel @ (r2 @ r1 - r1).T + np.array(drop)
        count += 1
    obj.shape_key_add(name="Basis", from_mix=False)
    for name, pts in ((THROW_KEY, key1), (FALL_KEY, key2)):
        kb = obj.shape_key_add(name=name, from_mix=False)
        local = pts @ inv[:3, :3].T + inv[:3, 3]
        kb.data.foreach_set("co", local.astype(np.float32).ravel())
        kb.value = 0.0
    return {"fragments": int(count), "whole_pieces": n_whole, "cut_pieces": n_cut, "splits": len(split),
            "verts": len(me.vertices), "bones": bones, "scale": round(k, 3)}
