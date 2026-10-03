#!/usr/bin/env python3
"""DOA6 动作解码：G2A（游戏里的 .g1a 文件其实大多是 G2A）+ G1A + G1M 里的骨架（G1MS）。

算法照 Project G1M（Noesis 插件，源码在 E:\\tools\\doa6\\project_g1m）的 G2A.h / G1A.h /
G1MS.h / Utils.h 移植，纯 Python + numpy，不依赖 Noesis：

  G2A  每根骨若干条曲线（0 旋转 / 1 位移 / 2 缩放），关键帧之间是三次多项式，
       系数量化成 4 个 u64（每个 u64 = 4 位指数 + 3 个 20 位有符号数），
       旋转曲线给的是轴角向量，转成四元数。
  G1A  老格式：每个分量一条三次样条，系数是 float。
  G1MS 骨架：每节骨 48 字节（缩放、父骨、四元数、位置），局部索引 -> 全局索引。
       动作里的骨骼编号是全局索引，Noesis 导出的骨架把骨头命名成 bone_<全局索引>。

四元数一律按文件里的原样 (x, y, z, w) 返回；Project G1M 在送进 Noesis 前对旋转取共轭
（G1MS 是 ToMat43().GetInverse()，G2A/G1A 是 Transpose），两者一致，所以只要静止姿势
和动作用同一个约定即可。

用法：
  python g2a.py info <clip.g1a> [...]           每个动作：格式、帧率、帧数、动的骨头数
  python g2a.py skeleton <model.g1m>             骨架概况
  python g2a.py dump <clip.g1a> --out x.json     逐帧采样（60 fps）写 JSON
"""

import argparse
import json
import math
import os
import struct
import sys

import numpy as np

V_G2A5 = 0x30303530  # "0500"
V_G2A4 = 0x30303430  # "0400"


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


# --------------------------------------------------------------------------- G2A

def _dequant(rows, t):
    """rows: (4,) uint64 = 常数 / 一次 / 二次 / 三次项；t: (n,) 0..1 -> (n, 3)。"""
    out = np.zeros((len(t), 3), dtype=np.float64)
    powers = [np.ones_like(t), t, t * t, t * t * t]
    for k in range(4):
        r = int(rows[k])
        e = (((r >> 37) & 0x7800000) + 0x32000000) & 0xFFFFFFFF
        scale = struct.unpack("<f", struct.pack("<I", e))[0]
        comps = []
        for sh in ("x", "y", "z"):
            if sh == "x":
                v = (r >> 28) & 0xFFFFF000
            elif sh == "y":
                v = (r >> 8) & 0xFFFFF000
            else:
                v = (r << 12) & 0xFFFFFFFF
            v &= 0xFFFFFFFF
            if v & 0x80000000:
                v -= 1 << 32
            comps.append(float(v) * scale)
        out += np.outer(powers[k], np.array(comps))
    return out


def _axis_angle_to_quat(v):
    """(n,3) 轴角 -> (n,4) xyzw，和 Utils.h function2 一样（小角度用 0.5 近似）。"""
    ang = np.linalg.norm(v, axis=1)
    s = np.sin(ang * 0.5)
    c = np.cos(ang * 0.5)
    k = np.where(ang > 0.000011920929, s / np.maximum(ang, 1e-30), 0.5)
    q = np.empty((len(v), 4))
    q[:, :3] = v * k[:, None]
    q[:, 3] = c
    return q


class Clip:
    """一个动作：fps、frames（帧数，= 动作长度 + 1 个采样点）、tracks[骨全局编号] = {rot/pos/scale: (frames, n)}。"""

    def __init__(self, fmt, fps, length, tracks, version):
        self.format = fmt
        self.fps = fps
        self.length = length  # 最后一帧的序号（G2A 的 animationLength）
        self.tracks = tracks
        self.version = version

    @property
    def frames(self):
        return self.length + 1

    @property
    def seconds(self):
        return self.length / self.fps if self.fps else 0.0


def read_g2a(buf):
    magic, ver, _size = struct.unpack_from("<4sII", buf, 0)
    if magic != b"_A2G":
        raise ValueError("不是 G2A: %r" % magic)
    is5, is4 = ver == V_G2A5, ver == V_G2A4
    off = 12
    fps = struct.unpack_from("<f", buf, off)[0]
    off += 4
    packed = _u32(buf, off)
    off += 4
    length = packed & 0x3FFF
    bone_info_size = (packed >> 18) & 0x3FFC
    timing_size, _entry_count = struct.unpack_from("<II", buf, off)
    off += 8
    if is5 or is4:
        off += 4
    checkpoint = off
    n_info = bone_info_size >> 2
    tracks = {}
    last_id = 0
    global_off = 0
    for i in range(n_info):
        p = _u32(buf, checkpoint + 4 * i)
        n_curves = p & 0xF
        bone = (p >> 4) & (0xFF if is5 else 0x3FF)
        tim_off = (p >> 12) if is5 else (p >> 14)
        if bone < last_id:
            global_off += 1
        last_id = bone
        bone += global_off * (256 if is5 else 1024)
        o = checkpoint + bone_info_size + tim_off
        o -= o % 4
        tr = tracks.setdefault(bone, {})
        for _ in range(n_curves):
            opcode, nkf, first = struct.unpack_from("<HHI", buf, o)
            o += 8
            times = list(struct.unpack_from("<%dH" % nkf, buf, o))
            o += 2 * nkf
            if o % 4:
                o += 4 - o % 4
            back = o
            doff = checkpoint + bone_info_size + timing_size + first * 32
            q = np.frombuffer(buf, dtype="<u8", count=4 * nkf, offset=doff).reshape(nkf, 4)
            vals = np.zeros((length + 1, 3))
            if nkf == 1:
                vals[:] = _dequant(q[0], np.zeros(1))[0]
            else:
                if times[-1] != length:
                    times.append(length)
                for k in range(len(times) - 1):
                    k1, k2 = times[k], times[k + 1]
                    if k2 <= k1:
                        continue
                    t = np.arange(k2 - k1, dtype=np.float64) / (k2 - k1)
                    vals[k1:k2] = _dequant(q[k], t)
                # 最后一帧（= length）：最后一段在 t=1 处的值
                k1, k2 = times[-2], times[-1]
                if k2 > k1:
                    vals[length] = _dequant(q[len(times) - 2], np.ones(1))[0]
            if opcode == 0:
                tr["rot"] = _axis_angle_to_quat(vals)
            elif opcode == 1:
                tr["pos"] = vals
            elif opcode == 2:
                tr["scale"] = vals
            o = back
    return Clip("g2a", fps, length, tracks, ver)


# --------------------------------------------------------------------------- G1A

def read_g1a(buf, fps=30.0):
    magic, ver, _size = struct.unpack_from("<4sII", buf, 0)
    if magic != b"_A1G":
        raise ValueError("不是 G1A: %r" % magic)
    off = 12
    _anim_type = struct.unpack_from("<H", buf, off)[0]
    off += 4
    duration = struct.unpack_from("<f", buf, off)[0]
    off += 32
    n_info, _max_id = struct.unpack_from("<HH", buf, off)
    off += 4
    checkpoint = off
    length = int(round(duration * fps))
    times_out = np.arange(length + 1) / fps
    tracks = {}
    layouts = {1: (2, None, None, None), 2: (4, None, 0, None), 4: (7, None, 0, 4), 6: (10, 0, 3, 7), 8: (7, 0, 3, None)}
    for i in range(n_info):
        bone, spline_off = struct.unpack_from("<II", buf, checkpoint + i * 8)
        c2 = checkpoint - 4 + spline_off * 0x10
        opcode = _u32(buf, c2)
        if opcode not in layouts:
            continue
        ncomp, i_s, i_r, i_l = layouts[opcode]
        chans = []
        for j in range(ncomp):
            nkf, doff = struct.unpack_from("<II", buf, c2 + 4 + j * 8)
            o = c2 + doff * 0x10
            if ver > 0x30303430:
                coef = np.frombuffer(buf, "<f4", 4 * nkf, o).reshape(nkf, 4)
                tk = np.frombuffer(buf, "<f4", nkf, o + 16 * nkf)
            else:
                tk = np.frombuffer(buf, "<f4", nkf, o)
                coef = np.frombuffer(buf, "<f4", 4 * nkf, o + 4 * nkf).reshape(nkf, 4)
            chans.append((tk.astype(np.float64), coef.astype(np.float64)))

        def evaluate(ch):
            tk, coef = ch
            idx = np.searchsorted(tk, times_out, side="right")
            idx = np.minimum(idx, len(tk) - 1)
            t1 = tk[idx]
            t0 = np.where(idx > 0, tk[np.maximum(idx - 1, 0)], 0.0)
            r = (times_out - t0) / np.where(t1 - t0 == 0, 1, t1 - t0)
            a, b, c, d = coef[idx].T
            return a * r ** 3 + b * r ** 2 + c * r + d

        tr = tracks.setdefault(bone, {})
        if i_r is not None:
            tr["rot"] = np.stack([evaluate(chans[i_r + k]) for k in range(4)], 1)
        if i_l is not None:
            tr["pos"] = np.stack([evaluate(chans[i_l + k]) for k in range(3)], 1)
        if i_s is not None:
            tr["scale"] = np.stack([evaluate(chans[i_s + k]) for k in range(3)], 1)
    return Clip("g1a", fps, length, tracks, ver)


def read_clip(path):
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] == b"_A2G":
        return read_g2a(buf)
    if buf[:4] == b"_A1G":
        return read_g1a(buf)
    raise ValueError("%s: 未知动作格式 %r" % (path, buf[:4]))


def resample(clip, fps):
    """把每条轨道线性插值（旋转用归一化线性插值）到新帧率，返回 (n, tracks)。"""
    n = int(math.floor(clip.seconds * fps + 1e-6)) + 1
    src = np.arange(n) * clip.fps / fps
    i0 = np.minimum(np.floor(src).astype(int), clip.length)
    i1 = np.minimum(i0 + 1, clip.length)
    w = (src - i0)[:, None]
    out = {}
    for bone, tr in clip.tracks.items():
        o = {}
        for k, v in tr.items():
            a, b = v[i0], v[i1]
            if k == "rot":
                b = np.where((np.sum(a * b, 1) < 0)[:, None], -b, b)
                r = a * (1 - w) + b * w
                r /= np.linalg.norm(r, axis=1, keepdims=True)
                o[k] = r
            else:
                o[k] = a * (1 - w) + b * w
        out[bone] = o
    return n, out


# --------------------------------------------------------------------------- G1MS

class Skeleton:
    """G1M 内置骨架：joints[local] = dict(parent=local|-1, rot=xyzw, pos, scale)，local<->global。"""

    def __init__(self, joints, l2g):
        self.joints = joints
        self.l2g = l2g
        self.g2l = {g: l for l, g in l2g.items()}


def read_g1ms(path):
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] != b"_M1G":
        raise ValueError("不是 G1M: %r" % buf[:4])
    first, _res, count = struct.unpack_from("<III", buf, 12)
    off = first
    skels = []
    for _ in range(count):
        magic, ver, size = struct.unpack_from("<4sII", buf, off)
        if magic == b"SM1G":
            start = off
            jinfo, _u1, jcount, jidx_count, _layer, _pad = struct.unpack_from("<IIHHHH", buf, off + 12)
            l2g = {}
            if ver >= 0x30303332:
                idx = struct.unpack_from("<%dH" % jidx_count, buf, off + 12 + 16)
                for g, l in enumerate(idx):
                    if l != 0xFFFF:
                        l2g[l] = g
            else:
                l2g = {i: i for i in range(jcount)}
            joints = []
            for j in range(jcount):
                vals = struct.unpack_from("<3fI4f3ff", buf, start + jinfo + 48 * j)
                parent = vals[3]
                joints.append({
                    "scale": vals[0:3],
                    "parent": -1 if parent == 0xFFFFFFFF else (None if parent & 0x80000000 else parent),
                    "raw_parent": parent,
                    "rot": vals[4:8],
                    "pos": vals[8:11],
                })
            skels.append(Skeleton(joints, l2g))
        off += size
    if not skels:
        raise ValueError("%s 里没有 G1MS 骨架" % path)
    return skels[0]


# --------------------------------------------------------------------------- CLI

def _cmd_info(paths):
    for p in paths:
        try:
            c = read_clip(p)
        except Exception as e:  # noqa: BLE001
            print("%-40s 失败: %s" % (os.path.basename(p), e))
            continue
        nrot = sum(1 for t in c.tracks.values() if "rot" in t)
        npos = sum(1 for t in c.tracks.values() if "pos" in t)
        print("%-40s %s v%s %4.0f fps %5d 帧 %6.2f 秒  骨 %3d（转 %3d / 移 %3d）" % (
            os.path.basename(p), c.format, struct.pack("<I", c.version).decode(), c.fps, c.frames, c.seconds,
            len(c.tracks), nrot, npos))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info")
    a.add_argument("paths", nargs="+")
    b = sub.add_parser("skeleton")
    b.add_argument("g1m")
    c = sub.add_parser("dump")
    c.add_argument("clip")
    c.add_argument("--fps", type=float, default=60.0)
    c.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "info":
        _cmd_info(args.paths)
    elif args.cmd == "skeleton":
        s = read_g1ms(args.g1m)
        roots = [i for i, j in enumerate(s.joints) if j["parent"] == -1]
        print("关节 %d，全局编号 %d 个，根 %s" % (len(s.joints), len(s.l2g), [s.l2g.get(r) for r in roots]))
        for i, j in enumerate(s.joints[:12]):
            print(i, "g=%s" % s.l2g.get(i), j)
    elif args.cmd == "dump":
        clip = read_clip(args.clip)
        n, tracks = resample(clip, args.fps)
        out = {"source": os.path.basename(args.clip), "fps": args.fps, "frames": n,
               "tracks": {str(b): {k: np.round(v, 6).tolist() for k, v in t.items()} for b, t in tracks.items()}}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f)
        print("写出 %s：%d 帧，%d 根骨" % (args.out, n, len(tracks)))


if __name__ == "__main__":
    sys.exit(main())
