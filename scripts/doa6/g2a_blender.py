"""Blender 3.6：把 DOA6 的动作（.g1a/.g2a）套到已导出的 DOA6 角色 .blend 上，可选渲染预览视频。

  blender -b <角色>.blend --python g2a_blender.py -- --g1m <服装>.g1m --clips a.g1a b.g1a ...
          [--render-dir D:\\out\\frames] [--res 960x540] [--save out.blend]

做法：
- 动作里的骨骼编号 = G1M 骨架（G1MS）的全局编号；Noesis 导出的骨架把骨头命名为 bone_<全局编号>。
- 每帧按 G1MS 的父子关系正向算出每节骨的世界变换 W_anim（G1M 坐标，Y 朝上）。动作里没有的骨用静止姿势。
- Blender 骨头的静止矩阵 rest(b) 和 G1MS 静止的世界变换 W_rest 只差一个固定的轴向修正（FBX 导入带来的），
  所以 pose(b) = W_anim · W_rest⁻¹ · rest(b)，再换算成 pose bone 的局部变换写关键帧。
  不在 G1MS 里的骨（布料物理骨等）跟着父骨走。
- .blend 里有身体 / 脸 / 头发三个骨架（同源），三个都套同一个动作。
- 渲染：EEVEE，镜头跟着胯部水平移动，每个动作单独出一串 PNG（<渲染目录>/<动作名>/0001.png ...）。
"""

import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2a  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--g1m", required=True, help="提供骨架的 .g1m（和 .blend 里身体是同一件）")
    ap.add_argument("--clips", nargs="+", required=True)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--render-dir", default=None)
    ap.add_argument("--res", default="960x540")
    ap.add_argument("--save", default=None, help="把带动作的场景另存为 .blend")
    ap.add_argument("--lead", type=int, default=10, help="每个动作前面停在第 0 帧的帧数（预览用）")
    ap.add_argument("--tail", type=int, default=12, help="每个动作后面停在最后一帧的帧数（预览用）")
    ap.add_argument("--droop", type=float, default=0.8,
                    help="物理链（布料、头发饰物）往下垂的程度 0..1，游戏里是实时模拟的，动作里没有（默认 0.8）")
    ap.add_argument("--cam", default="3.6,2.2,0.55",
                    help="镜头相对胯部的位置：前方,右侧,上方（米，按角色第 0 帧的朝向；默认右前方 3/4）")
    return ap.parse_args(argv)


def quat_xyzw(q):
    return Quaternion((q[3], q[0], q[1], q[2]))


def trs(pos, rot, scale):
    m = quat_xyzw(rot).to_matrix().to_4x4()
    if scale is not None:
        m = m @ Matrix.Diagonal(Vector((scale[0], scale[1], scale[2], 1.0)))
    m.translation = Vector(pos)
    return m


class Rig:
    def __init__(self, skel):
        self.skel = skel
        self.order = []  # 局部索引，父在前
        seen = set()

        def visit(i):
            if i in seen:
                return
            p = skel.joints[i]["parent"]
            if p is not None and p >= 0:
                visit(p)
            seen.add(i)
            self.order.append(i)

        for i in range(len(skel.joints)):
            visit(i)
        self.rest_local = {}
        for i, j in enumerate(skel.joints):
            self.rest_local[i] = trs(j["pos"], j["rot"], j["scale"])
        self.rest_world = self.fk({})

    def fk(self, local_override):
        world = {}
        for i in self.order:
            j = self.skel.joints[i]
            m = local_override.get(i, self.rest_local[i])
            p = j["parent"]
            world[i] = world[p] @ m if p is not None and p >= 0 else m
        return world


def frame_locals(rig, tracks, f):
    out = {}
    for g, tr in tracks.items():
        i = rig.skel.g2l.get(g)
        if i is None:
            continue
        j = rig.skel.joints[i]
        pos = tr["pos"][f] if "pos" in tr else j["pos"]
        rot = tr["rot"][f] if "rot" in tr else j["rot"]
        scale = tr["scale"][f] if "scale" in tr else j["scale"]
        out[i] = trs(pos, rot, scale)
    return out


def bone_global(name):
    if name.startswith("bone_"):
        try:
            return int(name[5:])
        except ValueError:
            return None
    return None


def chain_end(b):
    while b.children:
        b = max(b.children, key=lambda c: c.length)
    return b


def apply_clip(arm, rig, tracks, n_frames, action_name, frame_offset=1, droop=0.0):
    """在骨架 arm 上建 action（帧号从 frame_offset 开始）。

    droop：布料 / 头发这些物理链（不在 G1MS 里、父骨在 G1MS 里的链根）游戏里是实时模拟的，
    动作里没有它们。预览时让整条链绕链根往下垂（0 = 跟父骨刚性走，1 = 整条链朝正下方）。
    """
    bones = arm.data.bones
    rest = {b.name: b.matrix_local.copy() for b in bones}
    rest_inv = {k: v.inverted() for k, v in rest.items()}
    w_rest_inv = {i: m.inverted() for i, m in rig.rest_world.items()}
    order = []
    seen = set()

    def visit(b):
        if b.name in seen:
            return
        if b.parent:
            visit(b.parent)
        seen.add(b.name)
        order.append(b)

    for b in bones:
        visit(b)

    def in_rig(bone):
        g = bone_global(bone.name)
        return g is not None and g in rig.skel.g2l

    # 物理链根：自己不在骨架里、父骨在；记下静止时整条链（链根头 -> 链尾）的向量
    chain_vec = {}
    if droop > 0:
        for b in bones:
            if not in_rig(b) and b.parent is not None and in_rig(b.parent):
                end = chain_end(b)
                chain_vec[b.name] = (end.tail_local - b.head_local)
    # 骨架空间里的"正下方"：骨架物体把 G1M 的 Y 朝上转到 Blender 的 Z 朝上
    down = (arm.matrix_world.to_3x3().inverted() @ Vector((0, 0, -1))).normalized()

    # G1MS 里也有"拍平的链"：一串兄弟骨头挂在同一根父骨下、沿着饰物排开（不知火舞背后的流苏
    # 800-812 都直接挂在 bone 9 下），游戏里由物理 / rigbin 驱动，动作里没有。同一父骨下的
    # 这些骨按位置连成串（相邻 20 厘米内），至少 5 根、铺开 30 厘米以上的才算链（胸部、背后的
    # 绳结这种一团的不算），整串绕离父骨最近的那根往下垂。
    groups = []  # (父骨局部索引, 成员集合, 锚点静止位置, 静止时 锚点->最远成员)
    if droop > 0:
        animated = {rig.skel.g2l[g] for g in tracks if g in rig.skel.g2l}
        by_parent = {}
        for i, j in enumerate(rig.skel.joints):
            p = j["parent"]
            if i in animated or p is None or p < 0 or p not in animated:
                continue
            by_parent.setdefault(p, []).append(i)
        for p, members in by_parent.items():
            heads = {i: rig.rest_world[i].translation for i in members}
            left = set(members)
            while left:
                seed = left.pop()
                cl, frontier = {seed}, [seed]
                while frontier:
                    a = frontier.pop()
                    for b in list(left):
                        if (heads[a] - heads[b]).length < 20.0:  # G1M 单位是厘米
                            left.discard(b)
                            cl.add(b)
                            frontier.append(b)
                if len(cl) < 5:
                    continue
                ph = rig.rest_world[p].translation
                anchor = min(cl, key=lambda i: (heads[i] - ph).length)
                far = max(cl, key=lambda i: (heads[i] - heads[anchor]).length)
                span = heads[far] - heads[anchor]
                if span.length < 30.0:
                    continue
                groups.append((p, cl, heads[anchor].copy(), span))
    member_of = {i: k for k, (_p, ms, _, _) in enumerate(groups) for i in ms}
    for _p, ms, _h, sp in groups:
        print("[g2a] %s: 下垂的饰物链 %d 根骨（铺开 %.0f 厘米）" % (arm.name, len(ms), sp.length))

    act = bpy.data.actions.new(action_name)
    arm.animation_data_create()
    arm.animation_data.action = act
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"

    keys = {}  # bone -> list of (loc, quat, scale)
    for f in range(n_frames):
        world = rig.fk(frame_locals(rig, tracks, f))
        sag = {}
        for k, (p, _ms, a_head, span) in enumerate(groups):
            m = world[p] @ w_rest_inv[p]
            v = (m.to_3x3() @ span).normalized()
            target = v.lerp(down, droop)
            if target.length < 1e-6:
                continue
            h = m @ a_head
            sag[k] = Matrix.Translation(h) @ v.rotation_difference(target.normalized()).to_matrix().to_4x4() @ Matrix.Translation(-h)
        pose = {}
        for b in order:
            g = bone_global(b.name)
            i = rig.skel.g2l.get(g) if g is not None else None
            if i is not None:
                pose[b.name] = world[i] @ w_rest_inv[i] @ rest[b.name]
                if i in member_of and member_of[i] in sag:
                    pose[b.name] = sag[member_of[i]] @ pose[b.name]
            elif b.parent:
                pose[b.name] = pose[b.parent.name] @ rest_inv[b.parent.name] @ rest[b.name]
                v_rest = chain_vec.get(b.name)
                if v_rest is not None and v_rest.length > 1e-6:
                    m = pose[b.name] @ rest_inv[b.name]
                    v = (m.to_3x3() @ v_rest).normalized()
                    target = v.lerp(down, droop)
                    if target.length > 1e-6:
                        rot = v.rotation_difference(target.normalized()).to_matrix().to_4x4()
                        head = pose[b.name].translation.copy()
                        pose[b.name] = Matrix.Translation(head) @ rot @ Matrix.Translation(-head) @ pose[b.name]
            else:
                pose[b.name] = rest[b.name]
            if b.parent:
                basis = (rest_inv[b.parent.name] @ rest[b.name]).inverted() @ pose[b.parent.name].inverted() @ pose[b.name]
            else:
                basis = rest_inv[b.name] @ pose[b.name]
            loc, q, sc = basis.decompose()
            keys.setdefault(b.name, []).append((loc, q, sc))

    for b in order:
        ks = keys[b.name]
        # 全程都是单位变换的骨不写关键帧
        moving = any((k[0].length > 1e-5) or (abs(k[1].w) < 0.999999) or (k[2] - Vector((1, 1, 1))).length > 1e-5 for k in ks)
        if not moving:
            continue
        # 四元数连续（避免插值翻转）
        prev = None
        for idx, (loc, q, sc) in enumerate(ks):
            if prev is not None and prev.dot(q) < 0:
                q.negate()
            prev = q
        base = 'pose.bones["%s"].' % b.name
        for prop, n, getter in (("location", 3, lambda k, c: k[0][c]),
                                ("rotation_quaternion", 4, lambda k, c: k[1][c]),
                                ("scale", 3, lambda k, c: k[2][c])):
            for c in range(n):
                fc = act.fcurves.new(base + prop, index=c, action_group=b.name)
                fc.keyframe_points.add(len(ks))
                co = []
                for idx, k in enumerate(ks):
                    co += [frame_offset + idx, getter(k, c)]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.update()
    return act


def hips_track(rig, tracks, n_frames, hip_local):
    out = []
    for f in range(n_frames):
        world = rig.fk(frame_locals(rig, tracks, f))
        out.append(world[hip_local].translation.copy())
    return out


def setup_render(res, fps):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    w, h = (int(x) for x in res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.fps = int(fps)
    sc.render.image_settings.file_format = "PNG"
    sc.eevee.taa_render_samples = 16
    sc.eevee.use_gtao = True
    sc.view_settings.view_transform = "Filmic"
    sc.view_settings.look = "Medium High Contrast"
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.32, 0.34, 0.38, 1.0)
        bg.inputs[1].default_value = 0.8
    # 灯：主光 + 补光
    for name, rot, energy in (("KeySun", (math.radians(50), 0, math.radians(-35)), 3.5),
                              ("FillSun", (math.radians(65), 0, math.radians(150)), 1.2)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = rot
        sc.collection.objects.link(lo)
    # 地面
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    mat = bpy.data.materials.new("FloorMat")
    mat.use_nodes = True
    p = mat.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (0.18, 0.19, 0.21, 1)
    p.inputs["Roughness"].default_value = 0.85
    floor.data.materials.append(mat)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 40
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam, floor


def main():
    args = parse_args()
    skel = g2a.read_g1ms(args.g1m)
    rig = Rig(skel)
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        raise SystemExit("场景里没有骨架")
    body = max(arms, key=lambda o: len(o.data.bones))
    print("[g2a] 骨架:", [(a.name, len(a.data.bones)) for a in arms], "G1MS 关节", len(skel.joints))

    # 自检：G1MS 静止的世界位置 == Blender 骨头头部（骨架空间，G1M 坐标）
    errs = []
    for b in body.data.bones:
        g = bone_global(b.name)
        i = skel.g2l.get(g) if g is not None else None
        if i is not None:
            errs.append((rig.rest_world[i].translation - b.head_local).length)
    print("[g2a] 静止姿势对齐误差：最大 %.4f，平均 %.4f（%d 节骨）" % (max(errs), sum(errs) / len(errs), len(errs)))

    # 胯部 = 动作里带位移的第一根非根骨（打印出来核对）
    sc = bpy.context.scene
    cam = floor = None
    if args.render_dir:
        cam, floor = setup_render(args.res, args.fps)

    for path in args.clips:
        clip = g2a.read_clip(path)
        n, tracks = g2a.resample(clip, args.fps)
        name = os.path.splitext(os.path.basename(path))[0]
        moved = sorted(g for g, t in tracks.items() if "pos" in t)
        print("[g2a] %s: %d 帧 @%g，%d 根骨，带位移的骨 %s" % (name, n, args.fps, len(tracks), moved))
        # 预览：前后各停几帧
        frames = list(range(n))
        seq = [0] * args.lead + frames + [n - 1] * args.tail
        tracks_seq = {g: {k: v[seq] for k, v in t.items()} for g, t in tracks.items()}
        for a in arms:
            apply_clip(a, rig, tracks_seq, len(seq), "%s_%s" % (name, a.name), droop=args.droop)
        sc.frame_start, sc.frame_end = 1, len(seq)

        # 地面高度 = 全程脚最低点；胯部轨迹给镜头
        hip_g = 2 if 2 in skel.g2l else moved[0]
        hip_i = skel.g2l[hip_g]
        mw = body.matrix_world
        hips = [mw @ v for v in hips_track(rig, tracks_seq, len(seq), hip_i)]
        # 第 0 帧的朝向：静止时角色朝 G1M 的 +Z，动作的根骨可能把她转过去
        w0 = rig.fk(frame_locals(rig, tracks_seq, 0))
        turn = (w0[hip_i] @ rig.rest_world[hip_i].inverted()).to_3x3()
        fwd = mw.to_3x3() @ (turn @ Vector((0, 0, 1)))
        fwd.z = 0
        fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((0, -1, 0))
        right = fwd.cross(Vector((0, 0, 1)))
        print("[g2a] %s: 第 0 帧朝向 (%.2f, %.2f)" % (name, fwd.x, fwd.y))
        low = []
        for f in range(0, len(seq), 3):
            sc.frame_set(f + 1)
            dg = bpy.context.evaluated_depsgraph_get()
            ev = body.evaluated_get(dg)
            low.append(min((ev.matrix_world @ pb.head).z for pb in ev.pose.bones if bone_global(pb.name) is not None and bone_global(pb.name) < 200))
        # 地面按最后一帧（动作都落回地上站着）定；全程最低点、第一帧都会被从台下升起的出场动作带偏
        ground = low[-1]
        print("[g2a] %s: 骨头最低点 z=%.3f，胯部 z %.3f..%.3f" % (name, ground, min(h.z for h in hips), max(h.z for h in hips)))
        if not args.render_dir:
            continue
        floor.location.z = ground - 0.025  # 最低的骨头在脚尖，鞋底再低一点
        # 镜头：右前方 3/4，跟着胯部走（水平平滑 0.25 秒；跳起来时也往上跟，平滑 0.1 秒）
        k, kz = 15, 6
        c_fwd, c_right, c_up = (float(x) for x in args.cam.split(","))
        off = fwd * c_fwd + right * c_right + Vector((0, 0, c_up))
        for f in range(len(seq)):
            lo, hi = max(0, f - k), min(len(seq), f + k + 1)
            cx = sum(h.x for h in hips[lo:hi]) / (hi - lo)
            cy = sum(h.y for h in hips[lo:hi]) / (hi - lo)
            lo, hi = max(0, f - kz), min(len(seq), f + kz + 1)
            hz = sum(h.z for h in hips[lo:hi]) / (hi - lo)
            target = Vector((cx, cy, max(ground + 0.85, hz + 0.05)))
            cam.location = target + off
            cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
            cam.keyframe_insert("location", frame=f + 1)
            cam.keyframe_insert("rotation_euler", frame=f + 1)
        out = os.path.join(args.render_dir, name)
        os.makedirs(out, exist_ok=True)
        sc.render.filepath = os.path.join(out, "")
        bpy.ops.render.render(animation=True)
        cam.animation_data_clear()
        print("[g2a] 渲染完 %s -> %s" % (name, out))

    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=args.save, compress=True)
        print("[g2a] 另存", args.save)


main()
