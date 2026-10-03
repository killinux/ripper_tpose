#!/usr/bin/env python3
"""DOA6 动作 -> BVH（人形骨骼命名），给别的程序重定向用（比如 ROE Fighter 的 RoeMocap 导入器）。

只导出人形的 21 节骨：髋、脊柱两节、脖子、头、锁骨、上臂、前臂、手、大腿、小腿、脚、脚尖。
名字用 Mixamo 那一套（Hips、Spine、Spine1、Neck、Head、LeftShoulder、LeftArm、LeftForeArm、LeftHand、
LeftUpLeg、LeftLeg、LeftFoot、LeftToeBase……），大多数导入器能按名字认出来。

- BVH 的零姿势 = G1M 骨架的静止姿势（A 字形，面朝 +Z，+X 是她的左边，单位厘米，髋在原点）。
- 每帧：根节点 Hips 带位移，包含动作的根运动（骨 1）；各关节的旋转 = 这一帧的姿势相对静止姿势的旋转，
  按 BVH 的规矩拆成 Z、X、Y 三个欧拉角（父关节坐标系里）。
- 手指、头发、飘带、道具骨不导出。

  python g2a_bvh.py --g1m MAI_COS_004.g1m --out <dir> clip1.g1a [clip2.g1a ...]   [--check]

--check：把写出去的 BVH 重新正向运动学算一遍，和原动作的关节位置比，打印最大误差（应在 0.01 厘米以内）。
骨号对应（DOA6 角色共用的身体骨架，按不知火舞量过；别的角色先用 `g2a.py skeleton` 核对）见 JOINTS。
"""

import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2a  # noqa: E402

# (BVH 关节名, 全局骨号, 父关节名)：父子关系和 G1M 骨架里一样（中间没有跳过的骨）
JOINTS = [
    ("Hips", 2, None),
    ("Spine", 9, "Hips"), ("Spine1", 10, "Spine"), ("Neck", 11, "Spine1"), ("Head", 12, "Neck"),
    ("LeftShoulder", 13, "Spine1"), ("LeftArm", 15, "LeftShoulder"), ("LeftForeArm", 17, "LeftArm"), ("LeftHand", 19, "LeftForeArm"),
    ("RightShoulder", 14, "Spine1"), ("RightArm", 16, "RightShoulder"), ("RightForeArm", 18, "RightArm"), ("RightHand", 20, "RightForeArm"),
    ("LeftUpLeg", 3, "Hips"), ("LeftLeg", 5, "LeftUpLeg"), ("LeftFoot", 7, "LeftLeg"), ("LeftToeBase", 23, "LeftFoot"),
    ("RightUpLeg", 4, "Hips"), ("RightLeg", 6, "RightUpLeg"), ("RightFoot", 8, "RightLeg"), ("RightToeBase", 24, "RightFoot"),
]
# 末端（End Site）：这节骨下面某根骨的静止位置（中指指尖）；None = 沿上一节的方向延长一点
ENDS = {"Head": None, "LeftHand": 52, "RightHand": 53, "LeftToeBase": None, "RightToeBase": None}


def quat_matrix(q):
    """(..., 4) 四元数 (x, y, z, w) -> (..., 3, 3)，列向量约定（和 g2a 的静止姿势一致）。"""
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (y * y + z * z); m[..., 0, 1] = 2 * (x * y - z * w); m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w); m[..., 1, 1] = 1 - 2 * (x * x + z * z); m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w); m[..., 2, 1] = 2 * (y * z + x * w); m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def euler_zxy(r):
    """(n, 3, 3) 旋转矩阵 = Rz(a) Rx(b) Ry(c) -> (n, 3) 角度 (a, b, c)，弧度。"""
    b = np.arcsin(np.clip(r[:, 2, 1], -1.0, 1.0))
    a = np.arctan2(-r[:, 0, 1], r[:, 1, 1])
    c = np.arctan2(-r[:, 2, 0], r[:, 2, 2])
    return np.stack([a, b, c], axis=1)


def matrix_zxy(e):
    """(n, 3) 弧度 (a, b, c) -> Rz(a) Rx(b) Ry(c)。"""
    a, b, c = e[:, 0], e[:, 1], e[:, 2]
    ca, sa, cb, sb, cc, sc = np.cos(a), np.sin(a), np.cos(b), np.sin(b), np.cos(c), np.sin(c)
    n = len(e)
    rz = np.zeros((n, 3, 3)); rz[:, 0, 0] = ca; rz[:, 0, 1] = -sa; rz[:, 1, 0] = sa; rz[:, 1, 1] = ca; rz[:, 2, 2] = 1
    rx = np.zeros((n, 3, 3)); rx[:, 0, 0] = 1; rx[:, 1, 1] = cb; rx[:, 1, 2] = -sb; rx[:, 2, 1] = sb; rx[:, 2, 2] = cb
    ry = np.zeros((n, 3, 3)); ry[:, 0, 0] = cc; ry[:, 0, 2] = sc; ry[:, 1, 1] = 1; ry[:, 2, 0] = -sc; ry[:, 2, 2] = cc
    return rz @ rx @ ry


class Body:
    """G1M 骨架的静止姿势和正向运动学（全部关节，世界坐标）。"""

    def __init__(self, skeleton):
        self.s = skeleton
        self.order = []
        seen = set()

        def visit(i):
            if i in seen:
                return
            p = self.s.joints[i]["parent"]
            if p is not None and p >= 0:
                visit(p)
            seen.add(i)
            self.order.append(i)

        for i in range(len(self.s.joints)):
            visit(i)
        self.rest_r = {i: quat_matrix(np.array(j["rot"], float)) for i, j in enumerate(self.s.joints)}
        self.rest_t = {i: np.array(j["pos"], float) for i, j in enumerate(self.s.joints)}
        self.rest_world_r, self.rest_world_t = self.fk(self.rest_r, self.rest_t)

    def fk(self, loc_r, loc_t):
        r, t = {}, {}
        for i in self.order:
            p = self.s.joints[i]["parent"]
            if p is None or p < 0:
                r[i], t[i] = loc_r[i], loc_t[i]
            else:
                r[i] = r[p] @ loc_r[i]
                t[i] = t[p] + np.einsum("...ij,...j->...i", r[p], loc_t[i])
        return r, t

    def pose(self, clip):
        """动作每帧所有关节的世界旋转 (n, 3, 3) 和位置 (n, 3)。"""
        n = clip.frames
        loc_r = {i: np.broadcast_to(self.rest_r[i], (n, 3, 3)) for i in self.rest_r}
        loc_t = {i: np.broadcast_to(self.rest_t[i], (n, 3)) for i in self.rest_t}
        for g, tr in clip.tracks.items():
            i = self.s.g2l.get(g)
            if i is None:
                continue
            if "rot" in tr:
                loc_r[i] = quat_matrix(np.asarray(tr["rot"], float))
            if "pos" in tr:
                loc_t[i] = np.asarray(tr["pos"], float)
        return self.fk(loc_r, loc_t)


def write_bvh(path, body, clip):
    """一个动作写成 BVH；返回 (帧数, 重新算出的关节位置 {名字: (n, 3)}, 原动作的关节位置)。"""
    g2l = body.s.g2l
    idx = {name: g2l[g] for name, g, _ in JOINTS}
    parent = {name: par for name, _, par in JOINTS}
    children = {name: [c for c, _, p in JOINTS if p == name] for name, _, _ in JOINTS}
    rw_t = body.rest_world_t
    rw_r = body.rest_world_r
    world_r, world_t = body.pose(clip)
    n = clip.frames

    # 每帧每节骨相对静止姿势的世界旋转 Q = G(t) G_rest^-1；局部 = Q_parent^-1 Q
    q = {name: world_r[idx[name]] @ rw_r[idx[name]].T for name in idx}
    local = {}
    for name in idx:
        p = parent[name]
        local[name] = q[name] if p is None else np.swapaxes(q[p], 1, 2) @ q[name]
    angles = {name: np.degrees(np.unwrap(euler_zxy(local[name]), axis=0)) for name in idx}
    root = world_t[idx["Hips"]]

    lines = ["HIERARCHY"]

    def offset(name):
        p = parent[name]
        return rw_t[idx[name]] - (rw_t[idx[p]] if p else rw_t[idx[name]])

    def end_offset(name):
        g = ENDS.get(name)
        if g is not None and g in g2l:
            return rw_t[g2l[g]] - rw_t[idx[name]]
        p = parent[name]
        d = rw_t[idx[name]] - rw_t[idx[p]]
        if name == "Head":
            return np.array([0.0, 15.0, 0.0])
        if name.endswith("ToeBase"):
            d = np.array([d[0], 0.0, d[2]])
        length = np.linalg.norm(d)
        return d / max(length, 1e-6) * 5.0

    def emit(name, depth):
        pad = "  " * depth
        o = offset(name)
        if parent[name] is None:
            lines.append(f"ROOT {name}")
            lines.append(pad + "{")
            lines.append(pad + "  OFFSET 0.000000 0.000000 0.000000")
            lines.append(pad + "  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        else:
            lines.append(pad + f"JOINT {name}")
            lines.append(pad + "{")
            lines.append(pad + f"  OFFSET {o[0]:.6f} {o[1]:.6f} {o[2]:.6f}")
            lines.append(pad + "  CHANNELS 3 Zrotation Xrotation Yrotation")
        if children[name]:
            for c in children[name]:
                emit(c, depth + 1)
        elif name in ENDS:
            e = end_offset(name)
            lines.append(pad + "  End Site")
            lines.append(pad + "  {")
            lines.append(pad + f"    OFFSET {e[0]:.6f} {e[1]:.6f} {e[2]:.6f}")
            lines.append(pad + "  }")
        lines.append(pad + "}")

    emit("Hips", 0)
    order = []

    def walk(name):
        order.append(name)
        for c in children[name]:
            walk(c)

    walk("Hips")
    lines.append("MOTION")
    lines.append(f"Frames: {n}")
    lines.append(f"Frame Time: {1.0 / clip.fps:.8f}")
    for f in range(n):
        vals = [root[f, 0], root[f, 1], root[f, 2]]
        for name in order:
            vals.extend(angles[name][f])
        lines.append(" ".join(f"{v:.6f}" for v in vals))
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    # 检查：从写出去的数重新算关节位置
    back_q = {}
    back_t = {}
    for name in order:
        rot = matrix_zxy(np.radians(angles[name]))
        p = parent[name]
        if p is None:
            back_q[name] = rot
            back_t[name] = root
        else:
            back_q[name] = back_q[p] @ rot
            back_t[name] = back_t[p] + np.einsum("nij,j->ni", back_q[p], offset(name))
    orig = {name: world_t[idx[name]] for name in order}
    return n, back_t, orig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--g1m", required=True, help="the character's model (.g1m) with the skeleton (G1MS)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    body = Body(g2a.read_g1ms(a.g1m))
    missing = [g for _, g, _ in JOINTS if g not in body.s.g2l]
    if missing:
        sys.exit(f"skeleton lacks bones {missing}")
    os.makedirs(a.out, exist_ok=True)
    for path in a.clips:
        clip = g2a.read_clip(path)
        name = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(a.out, name + ".bvh")
        n, back, orig = write_bvh(out, body, clip)
        msg = f"{out}: {n} frames, {clip.fps:g} fps, {clip.seconds:.2f} s"
        if a.check:
            err = max(float(np.abs(back[k] - orig[k]).max()) for k in back)
            msg += f", max joint error {err:.4f} cm"
        print(msg)


if __name__ == "__main__":
    main()
