# -*- coding: utf-8 -*-
"""爆衣的实际工作（不含界面）。撕开用的是布料撕裂插件（cloth_tear）的做法：布料 1 全部固定、跟着身体走，
几何节点沿裂缝拆开、按帧松开固定组，布料 2 让松开的碎片自由运动，最后合上没撕开的缝。爆衣在这上面做三件事：

  1. 裂缝：在要爆开的范围里随机生成很多条（贯穿 + 不贯穿），套成圈的布再补一条切开；
     只爆一部分时，范围的边界（一边要爆、一边不爆的边）也设成裂缝，爆开时这块和其余部分分开。
  2. 松开：几帧之内全部松开（撕裂是几十帧从上往下扫）。只爆一部分时，范围外的顶点放进保留组 CB_Keep，
     撕开后一直固定，留在身上。
  3. 推力：一个短促的力场把碎片推出去。Blender 给布料施加力场时按面积缩放（implicit_blender.c 的
     SIM_mass_spring_force_face_extern：每个三角形 0.02 × 面积 / 3 分给三个顶点），力还要除以帧率；
     布料里的重力是 |重力| × 0.001（时间按帧算）。实测标定（六种网格 / 质量 / 帧率 / 形状，误差 < 0.1%）：
         力场的加速度 ÷ 重力 = 强度 × 0.02 × 面积 ÷（顶点质量 × 顶点数 × 帧率 × |重力| × 0.001）
     这里推力按「重力的倍数」给：每件衣服按自己（要爆开的那部分、按裂缝拆开后）的面积和顶点数算出要的强度，
     力场强度取最大的那件，其余各件用布料的力场权重（≤ 1）按比例减小——大块布和细布条推得一样远。
     力场用 Child Of 约束跟着那部分衣服权重最大的骨骼，角色在动时也是从身体往外推。

详细说明和测试见 docs/clothes-burst-guide.md。
"""
import json
import math

import bmesh
import bpy
from mathutils import Vector

from cloth_tear import core as ct

FIELD, FIELD_COLL = "CB_爆衣推力", "CB_爆衣力场"   # 每次「一键爆衣」一组：CB_爆衣推力_1 + CB_爆衣力场_1 ……
FOLLOW_CON = "CB 跟随身体"
KEEP_GROUP = "CB_Keep"        # 只爆一部分时：范围外的顶点，撕开后仍固定
REGION = "cb_region"          # 面属性（整数）：1 = 这个面要爆开；没有这个属性 = 整件
BURST = "cb_burst"            # 物体属性：上次爆衣的设置（json），也用来认出爆过的衣服
G = 9.81
DEFAULTS = {
    "frame": 30, "duration": 3,                       # 第几帧开始爆、几帧之内全部松开
    "accel": 1.0, "push_frames": 10, "shape": "LINE",  # 推力：重力的倍数、推几帧、方向
    "through": 10, "partial": 10, "jitter": 0.6, "seed": 1, "loops": True, "regen": True,
    "invert": False, "width": 0.08, "merge": 0.0005, "fast": False,
}


# --- 爆开范围 --------------------------------------------------------------------------------------------------
def region_of(obj):
    """存下来的爆开范围（面序号集合）；整件时返回 None。"""
    attr = obj.data.attributes.get(REGION)
    if attr is None or attr.domain != "FACE" or attr.data_type != "INT":
        return None
    values = [0] * len(attr.data)
    attr.data.foreach_get("value", values)
    faces = {i for i, v in enumerate(values) if v}
    return faces if 0 < len(faces) < len(obj.data.polygons) else None


def set_region(obj, faces):
    """faces：面序号集合。None、空的或包含全部面 = 整件（删掉属性）。返回存下的范围。"""
    attr = obj.data.attributes.get(REGION)
    if not faces or len(faces) >= len(obj.data.polygons):
        if attr is not None:
            obj.data.attributes.remove(attr)
        return None
    if attr is None:
        attr = obj.data.attributes.new(REGION, "INT", "FACE")
    attr.data.foreach_set("value", [1 if i in faces else 0 for i in range(len(obj.data.polygons))])
    return set(faces)


def selected_faces(obj):
    """编辑模式里选中的面（要先切回物体模式，polygon.select 才是编辑模式里的选择）。"""
    return {p.index for p in obj.data.polygons if p.select}


def region_verts(obj, region):
    """范围里的面用到的顶点；整件时是全部顶点。"""
    if region is None:
        return set(range(len(obj.data.vertices)))
    out = set()
    for p in obj.data.polygons:
        if p.index in region:
            out.update(p.vertices)
    return out


# --- 裂缝 ------------------------------------------------------------------------------------------------------
def _clear_cracks(obj):
    if ct.seam_count(obj):
        ct.mark_seams(obj, 0.0, only_selected=False)


def boundary_cracks(obj, region):
    """范围的边界（一边要爆、一边不爆的边）设成裂缝。返回边数。"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = ct._crease_layer(bm)
    n = 0
    for e in bm.edges:
        inside = [f.index in region for f in e.link_faces]
        if any(inside) and not all(inside):
            e[layer] = 1.0
            n += 1
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return n


def _region_object(obj, region):
    """只含范围里的面的临时物体（不放进场景），顶点属性 cb_orig = 原来的顶点号。范围的边界在这里是布边，
    随机裂缝就从范围的边界撕进去、在范围里贯穿。"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    orig = bm.verts.layers.int.new("cb_orig")
    for v in bm.verts:
        v[orig] = v.index
    drop = [f for f in bm.faces if f.index not in region]
    bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    mesh = bpy.data.meshes.new("cb_region_tmp")
    bm.to_mesh(mesh)
    bm.free()
    return bpy.data.objects.new("cb_region_tmp", mesh)


def _copy_cracks_back(tmp, obj):
    """临时物体上的裂缝按原顶点号抄回衣服。返回边数。"""
    bt = bmesh.new()
    bt.from_mesh(tmp.data)
    lt = ct._crease_layer(bt, create=False)
    orig = bt.verts.layers.int.get("cb_orig")
    pairs = [(e.verts[0][orig], e.verts[1][orig]) for e in bt.edges if lt is not None and e[lt] > 0.5] \
        if orig is not None else []
    bt.free()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    layer = ct._crease_layer(bm)
    n = 0
    for a, b in pairs:
        e = bm.edges.get((bm.verts[a], bm.verts[b]))
        if e is not None:
            e[layer] = 1.0
            n += 1
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return n


def burst_cracks(obj, region, through=10, partial=10, seed=1, jitter=0.6, loops=True):
    """在范围里（整件时就是整件）随机生成贯穿 / 不贯穿的裂缝，loops 时再把套成圈的布切开。
    返回 (裂缝条数, 切开套圈处数)。"""
    target = obj if region is None else _region_object(obj, region)
    made = rings = 0
    try:
        for count, part, s in ((through, False, seed), (partial, True, seed + 500)):
            if count <= 0:
                continue
            try:
                made += ct.random_cracks(target, count=count, seed=s, jitter=jitter, partial=part)
            except RuntimeError:
                if region is None:
                    raise RuntimeError("%s 没有开放的布边（或者面太少），随机裂缝没法开始" % obj.name)
                # 范围里全是很小的块：不加随机裂缝，只靠范围的边界撕下来
        if loops:
            rings = ct.cut_loops(target, seed=seed, jitter=jitter)
        if region is not None:
            _copy_cracks_back(target, obj)
    finally:
        if target is not obj:
            mesh = target.data
            bpy.data.objects.remove(target)
            bpy.data.meshes.remove(mesh)
    return made, rings


def set_keep_group(obj, region):
    """只爆一部分时：范围外的顶点（用到的面都不在范围里）放进 CB_Keep，权重 1，撕开后一直固定。
    范围边界上的顶点不放：边界拆开后两边各有一份，都放就会把爆开的那块也钉住。整件时删掉这个组。"""
    vg = obj.vertex_groups.get(KEEP_GROUP)
    if region is None:
        if vg is not None:
            obj.vertex_groups.remove(vg)
        return 0
    inside = region_verts(obj, region)
    keep = [i for i in range(len(obj.data.vertices)) if i not in inside]
    if vg is not None:
        obj.vertex_groups.remove(vg)
    vg = obj.vertex_groups.new(name=KEEP_GROUP)
    vg.add(keep, 1.0, "REPLACE")
    return len(keep)


# --- 推力 ------------------------------------------------------------------------------------------------------
def piece_stats(obj, region):
    """(面积, 顶点数)：要爆开的那部分按裂缝拆开以后（布料 2 算的就是拆开的网格），世界坐标。"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    faces = [f for f in bm.faces if region is None or f.index in region]
    layer = ct._crease_layer(bm, create=False)
    if layer is not None:
        cracks = [e for e in bm.edges if e[layer] > 0.5]
        if cracks:
            bmesh.ops.split_edges(bm, edges=cracks)
    area = sum(f.calc_area() for f in faces)
    verts = {v for f in faces for v in f.verts}
    bm.free()
    return area, len(verts)


def cloth_gravity(scene=None):
    """布料里的重力加速度（每帧²）：场景重力的大小 × 0.001（SIM_mass_spring.cpp 的 cloth_calc_force）。"""
    scene = scene or bpy.context.scene
    g = scene.gravity.length if scene.use_gravity else 0.0
    return (g or G) * 0.001


def needed_strength(obj, region, accel):
    """这件衣服（要爆开的那部分）得到 accel 倍重力的加速度要的力场强度。返回 (强度, 面积, 顶点数)。
    力场的加速度 = 强度 × 0.02 × 面积 ÷（顶点质量 × 顶点数 × 帧率），见文件开头（calib.py 实测）。"""
    area, n = piece_stats(obj, region)
    c2 = obj.modifiers.get(ct.MOD_CLOTH) or ct.source_cloth(obj)
    mass = c2.settings.mass if c2 is not None else 0.3
    fps = bpy.context.scene.render.fps
    return (accel * cloth_gravity() * mass * n * fps / (0.02 * area) if area > 0 else 0.0), area, n


def _world_points(obj, region):
    mw = obj.matrix_world
    verts = obj.data.vertices
    return [mw @ verts[i].co for i in region_verts(obj, region)]


def _pick_bone(arm, weights, share=0.9):
    """要爆开的那部分「跟着哪根骨骼走」：每根骨骼的权重加到它所有的上级骨骼上，取包住 share 以上总权重的
    最深的那根。裙子的权重分在一圈裙摆物理骨上，选出来的是它们共同的上级（下半身），而不是其中一根会甩动的
    裙摆骨；上衣是上半身那一串。"""
    bones = arm.data.bones
    total = sum(weights.values())
    subtree = {}
    for name, w in weights.items():
        b = bones.get(name)
        while b is not None:
            subtree[b.name] = subtree.get(b.name, 0.0) + w
            b = b.parent
    picked = [n for n, w in subtree.items() if w >= share * total]
    if not picked:
        return max(weights, key=weights.get)
    return max(picked, key=lambda n: len(bones[n].parent_recursive))


def _follow_bone(empty, garments, regions):
    """力场跟着要爆开的那部分的骨骼走（_pick_bone；Child Of，逆矩阵 = 这根骨骼静止时的世界矩阵的逆，
    静止姿势下力场不动）。返回骨骼名；没有骨架时去掉约束，返回 None。"""
    arm, weights = None, {}
    for g in garments:
        mod = next((m for m in g.modifiers if m.type == "ARMATURE" and m.object), None)
        if mod is None or (arm is not None and mod.object is not arm):
            continue
        arm = mod.object
        names = {vg.index: vg.name for vg in g.vertex_groups}
        inside = region_verts(g, regions.get(g.name))
        for v in g.data.vertices:
            if v.index not in inside:
                continue
            for ge in v.groups:
                name = names.get(ge.group)
                if name is not None and name in arm.data.bones:
                    weights[name] = weights.get(name, 0.0) + ge.weight
    con = empty.constraints.get(FOLLOW_CON)
    if arm is None or not weights:
        if con is not None:
            empty.constraints.remove(con)
        return None
    bone = _pick_bone(arm, weights)
    if con is None:
        con = empty.constraints.new("CHILD_OF")
        con.name = FOLLOW_CON
    con.target, con.subtarget = arm, bone
    con.inverse_matrix = (arm.matrix_world @ arm.data.bones[bone].matrix_local).inverted()
    return bone


def field_groups():
    """场景里所有爆衣推力组：[(集合, 力场物体或 None)]。"""
    out = []
    for c in bpy.data.collections:
        if c.name.startswith(FIELD_COLL + "_"):
            out.append((c, next((o for o in c.objects if o.name.startswith(FIELD + "_")), None)))
    return out


def _users(coll):
    """用这个力场集合的衣服（布料的力场集合是它）。"""
    return [o for o in bpy.data.objects if any(m.type == "CLOTH" and m.settings.effector_weights.collection is coll
                                               for m in getattr(o, "modifiers", ()))]


def _pick_group(garments):
    """这次爆衣用哪一组推力场：这几件衣服现在都在同一组、组里也没有别的衣服时接着用（再点一次「一键爆衣」），
    否则新建一组——别的衣服的推力（强度、时间）不受这次影响，不同的衣服可以在不同的帧爆开。"""
    colls = {m.settings.effector_weights.collection for g in garments for m in g.modifiers if m.type == "CLOTH"}
    if len(colls) == 1:
        coll = next(iter(colls))
        if coll is not None and coll.name.startswith(FIELD_COLL + "_") and set(_users(coll)) <= set(garments):
            return coll, next((o for o in coll.objects if o.name.startswith(FIELD + "_")), None)
    i = 1
    while (bpy.data.collections.get("%s_%d" % (FIELD_COLL, i)) is not None
           or bpy.data.objects.get("%s_%d" % (FIELD, i)) is not None):
        i += 1
    return bpy.data.collections.new("%s_%d" % (FIELD_COLL, i)), None


def _remove_group(coll):
    names = []
    for o in list(coll.objects):
        action = o.animation_data.action if o.animation_data else None
        names.append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)
        if action is not None and action.users == 0:
            bpy.data.actions.remove(action)
    names.append(coll.name)
    bpy.data.collections.remove(coll)
    return names


def prune_fields():
    """没有衣服再用的推力组删掉。返回删掉的名字。"""
    removed = []
    for coll, _ in field_groups():
        if not _users(coll):
            removed += _remove_group(coll)
    return removed


def add_burst_force(garments, regions, accel=1.0, frame=30, push_frames=10, shape="LINE"):
    """短促的推力：第 frame 帧打开，推 push_frames 帧，再过 2 帧关掉。shape = LINE（从身体中轴水平往外）
    或 POINT（从中心往四面八方）。只作用于这几件衣服的布料（力场集合 = 这一组的 CB_爆衣力场_N）；刚体世界
    没限定力场集合时设成空集合，MMD 头发不受影响。返回说明文字列表。"""
    scene = bpy.context.scene
    need = {g.name: needed_strength(g, regions.get(g.name), accel) for g in garments}
    strength = max((v[0] for v in need.values()), default=0.0)
    pts = [p for g in garments for p in _world_points(g, regions.get(g.name))]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])

    coll, empty = _pick_group(garments)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    if empty is None:
        empty = bpy.data.objects.new(FIELD + coll.name[len(FIELD_COLL):], None)
        coll.objects.link(empty)
    empty.location = (lo + hi) / 2.0
    empty.rotation_euler = (0.0, 0.0, 0.0)                  # 力场的 Z 轴 = 竖直方向（线形时是推的中轴）
    empty.scale = (1.0, 1.0, 1.0)
    if empty.field is None or empty.field.type != "FORCE":
        with bpy.context.temp_override(object=empty, active_object=empty):
            bpy.ops.object.forcefield_toggle()
    field = empty.field
    field.type, field.shape = "FORCE", shape
    field.falloff_type, field.falloff_power = "SPHERE", 0.0  # 衰减幂 0：哪里都一样大
    field.use_max_distance = field.use_min_distance = False
    empty.empty_display_type = "SINGLE_ARROW" if shape == "LINE" else "SPHERE"
    empty.empty_display_size = max(0.1, 0.5 * (hi.z - lo.z))
    bone = _follow_bone(empty, garments, regions)

    action = empty.animation_data.action if empty.animation_data else None
    if action is not None:
        empty.animation_data_clear()
        if action.users == 0:
            bpy.data.actions.remove(action)
    for f, value in ((frame - 1, 0.0), (frame, strength), (frame + push_frames, strength),
                     (frame + push_frames + 2, 0.0)):
        field.strength = value
        empty.keyframe_insert("field.strength", frame=f)
    fcurve = empty.animation_data.action.fcurves.find("field.strength")
    for key in fcurve.keyframe_points:
        key.interpolation = "LINEAR"

    weights = []
    for g in garments:
        w = need[g.name][0] / strength if strength > 0 else 0.0
        for m in g.modifiers:
            if m.type == "CLOTH":
                m.settings.effector_weights.collection = coll
                m.settings.effector_weights.force = w
        weights.append("%s %.2f" % (g.name, w))
    prune_fields()
    notes = ["推力 %.2g × 重力（%s），第 %d–%d 帧；推力场「%s」强度 %.0f，各件的力场权重：%s" % (
        accel, "水平往外" if shape == "LINE" else "四面八方", frame, frame + push_frames, empty.name, strength,
        "、".join(weights))]
    if bone:
        notes.append("推力场跟着骨骼「%s」走" % bone)
    rbw = scene.rigidbody_world
    if rbw is not None and rbw.effector_weights.collection is None:
        rbw.effector_weights.collection = (bpy.data.collections.get(ct.NO_FIELD_COLL)
                                           or bpy.data.collections.new(ct.NO_FIELD_COLL))
        notes.append("刚体世界（头发物理）的力场集合设成空集合「%s」，不受推力影响" % ct.NO_FIELD_COLL)
    return notes


def remove_fields():
    """删掉所有爆衣推力组，还在用它们的布料恢复默认的力场设置。返回删掉的名字。"""
    removed = []
    for coll, _ in field_groups():
        for o in _users(coll):
            for m in o.modifiers:
                if m.type == "CLOTH" and m.settings.effector_weights.collection is coll:
                    m.settings.effector_weights.collection = None
                    m.settings.effector_weights.force = 1.0
        removed += _remove_group(coll)
    return removed


# --- 一键爆衣 / 移除 -------------------------------------------------------------------------------------------
def burst_garments(scene=None):
    scene = scene or bpy.context.scene
    return [o for o in scene.objects if o.type == "MESH" and BURST in o]


def any_baked(scene=None):
    scene = scene or bpy.context.scene
    caches = [m.point_cache for o in scene.objects for m in getattr(o, "modifiers", ())
              if m.type in ("CLOTH", "SOFT_BODY")]
    if scene.rigidbody_world is not None:
        caches.append(scene.rigidbody_world.point_cache)
    return any(c.is_baked for c in caches)


def burst(garments, regions, opts):
    """一键爆衣。garments：衣服网格；regions：{物体名: 面序号集合 | None（整件）}；opts：DEFAULTS 里的各项。
    再点一次就按新的设置重做（裂缝默认重新生成）。返回说明文字列表。"""
    o = dict(DEFAULTS)
    o.update(opts or {})
    garments = [g for g in garments if g is not None and g.type == "MESH" and g.name != ct.FLOOR
                and getattr(g, "mmd_type", "NONE") == "NONE" and len(g.data.polygons)]
    if not garments:
        raise RuntimeError("先选中要爆开的衣服（网格物体）")
    scene = bpy.context.scene
    notes = ct.follow_body(garments)
    frame, end = int(o["frame"]), int(o["frame"]) + max(1, int(o["duration"]))
    for i, g in enumerate(garments):
        region = set_region(g, regions.get(g.name))
        if o["regen"]:
            _clear_cracks(g)
        edge = boundary_cracks(g, region) if region is not None else 0
        made, rings = burst_cracks(g, region, int(o["through"]), int(o["partial"]), int(o["seed"]) + 11 * i,
                                   float(o["jitter"]), bool(o["loops"]))
        if ct.seam_count(g) == 0:
            raise RuntimeError("%s 一条裂缝都没有：贯穿 / 不贯穿裂缝至少要有一条" % g.name)
        keep = set_keep_group(g, region)
        ct.setup_tear(g, axis="Z", invert=bool(o["invert"]), start=frame, end=end, width=float(o["width"]),
                      merge_distance=float(o["merge"]), keep_group=KEEP_GROUP if region is not None else "")
        what = "整件" if region is None else "选中的 %d 个面（边界 %d 条边是裂缝，其余 %d 个顶点留在身上）" % (
            len(region), edge, keep)
        notes.append("%s：%s；裂缝 %d 条%s，共 %d 条边" % (g.name, what, made, "、切开套圈 %d 处" % rings if rings else "",
                                                     ct.seam_count(g)))
    regions = {g.name: region_of(g) for g in garments}
    notes += add_burst_force(garments, regions, float(o["accel"]), frame, int(o["push_frames"]), o["shape"])
    speed, quality, height = ct.tear_speed(garments, fast=bool(o["fast"]))
    ct.set_tear_speed(garments, speed, quality, exact=bool(o["fast"]))
    notes.append("身高 %.1f → 布料 2 速度 %g、质量步数 %d%s" % (height, speed, quality, "（快速预览）" if o["fast"] else ""))
    for g in garments:
        g[BURST] = json.dumps({k: o[k] for k in DEFAULTS}, ensure_ascii=False)
    land = end + int(o["push_frames"]) + 40
    if scene.frame_end < land:
        notes.append("注意：场景结束帧是 %d，碎片大约第 %d 帧才落地，可以把结束帧改大再点一次「一键爆衣」"
                     "（缓存按场景的帧范围设）" % (scene.frame_end, land))
    if frame <= scene.frame_start:
        notes.append("注意：爆开帧要比场景开始帧（%d）晚，不然一开始就散了" % scene.frame_start)
    return notes


def remove_burst(obj):
    """撤掉一件衣服的爆衣：撕裂修改器、跟随身体的布料 1（衣服原来就有布料的还原设置）、CT_ / CB_ 顶点组、
    裂缝、爆开范围。身体上的碰撞和地面是几件衣服共用的，留着（「全部清理」才删）。返回做了什么。"""
    parts = ct.remove_tear(obj)
    cloth = ct.source_cloth(obj)
    backup = obj.get(ct.CLOTH_BACKUP)
    if cloth is not None and backup:
        b = json.loads(backup)
        cloth.settings.vertex_group_mass = b["pin"]
        cloth.collision_settings.use_self_collision = b["self_collision"]
        cloth.point_cache.frame_start, cloth.point_cache.frame_end = b["frame_start"], b["frame_end"]
        cloth.settings.effector_weights.collection = None
        cloth.settings.effector_weights.force = 1.0
        parts.append("%s 还原成原来的设置" % cloth.name)
    elif cloth is not None and (obj.get(ct.CLOTH_ADDED) == cloth.name
                                or cloth.settings.vertex_group_mass == ct.FOLLOW_GROUP):
        parts = [p for p in parts if not p.endswith("重新打开")] + [cloth.name]
        obj.modifiers.remove(cloth)
    for key in (ct.CLOTH_ADDED, ct.CLOTH_BACKUP, ct.CLOTH1_OFF, BURST):
        if key in obj:
            del obj[key]
    for name in (ct.FOLLOW_GROUP, ct.OUT_GROUP, KEEP_GROUP):
        vg = obj.vertex_groups.get(name)
        if vg is not None:
            obj.vertex_groups.remove(vg)
            parts.append("顶点组 " + name)
    n = ct.seam_count(obj)
    if n:
        ct.mark_seams(obj, 0.0, only_selected=False)
        parts.append("裂缝 %d 条边" % n)
    if obj.data.attributes.get(REGION) is not None:
        set_region(obj, None)
        parts.append("爆开范围")
    parts += prune_fields()
    return parts


def cleanup_all():
    """全部清理：撤掉所有爆过的衣服，删掉爆衣的推力场；再用布料撕裂插件的「全部清理」删掉身体上的碰撞、地面、
    它的推力场和没人用的节点组（布料撕裂插件撕过的衣服也会一起清掉）。返回做了什么。"""
    done = []
    for g in burst_garments():
        parts = remove_burst(g)
        if parts:
            done.append("%s：%s" % (g.name, "、".join(parts)))
    for o in bpy.context.scene.objects:                       # 万一还有留下的范围 / 保留组
        if o.type == "MESH":
            vg = o.vertex_groups.get(KEEP_GROUP)
            if vg is not None:
                o.vertex_groups.remove(vg)
            set_region(o, None)
    field = remove_fields()
    if field:
        done.append("推力场：%s" % "、".join(field))
    done += ct.cleanup_all(clear_cracks=True)
    return done


def last_settings(obj):
    try:
        return json.loads(obj.get(BURST, "{}"))
    except (TypeError, ValueError):
        return {}
