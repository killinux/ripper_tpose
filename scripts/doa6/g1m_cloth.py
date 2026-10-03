#!/usr/bin/env python3
"""DOA6 服装 .g1m 里的布料数据一览：哪些网格是布料、布料网格多大、挂在哪根骨上、物理参数块。

格式照 Project G1M 源码（E:\\tools\\doa6\\project_g1m）的 G1M.h / G1MG.h / G1MGMesh.h / NUNO.h / NUNV.h / NUNS.h：

  G1M  = 若干块：G1MF / G1MS（骨架）/ G1MM / G1MG（几何）/ COLL / NUNO（布）/ NUNV / NUNS / SOFT / EXTR ...
  NUNO = 布料。每个条目挂在一根骨上（parentID），有 N 个控制点（x, y, z, w）和每点 6 个数的连接
         （P1..P4 是相邻控制点的下标，-1 = 没有；P3 = 链上的上一个点，-1 = 直接挂在骨上），
         前面一段是这块布的物理参数（float，含义没有公开资料）。NUNO1 / NUNO3 / NUNO5 是三个版本。
  NUNV = 同样的控制点结构（Noesis 导出成 nunv1_* 骨），NUNS 多了 2 个 float 和一段 "BLW0"（风？）。
  G1MG 的网格组里，每个网格有 16 字节名字（是哈希）、类型（0 普通蒙皮 / 1 布料：顶点每帧从控制点网格插值 + 沿法线加厚度 /
  2 蒙皮在控制点上 / 4 软体）和 externalID（0-9999 = 第几个 NUNO1，10000+ = NUNV1，20000+ = NUNO3；类型 4 时是第几个软体）。
  SOFT = 胸、臀这类软体（节点 + 影响）。COLL = 碰撞体表，按布分组。
  调研结论见 docs/doa-clothing-and-cloth.md。

用法：
  python g1m_cloth.py <服装.g1m> [--params] [--json out.json]
"""

import argparse
import json
import struct
import sys
from collections import Counter, defaultdict

CHUNK_NAMES = {b"FM1G": "G1MF", b"SM1G": "G1MS", b"MM1G": "G1MM", b"GM1G": "G1MG", b"LLOC": "COLL",
               b"RIAH": "HAIR", b"ONUN": "NUNO", b"VNUN": "NUNV", b"SNUN": "NUNS", b"TFOS": "SOFT",
               b"RTXE": "EXTR"}


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def chunks(buf):
    if buf[:4] != b"_M1G":
        raise ValueError("不是 G1M")
    first, _res, count = struct.unpack_from("<III", buf, 12)
    off = first
    out = []
    for _ in range(count):
        magic, ver, size = struct.unpack_from("<4sII", buf, off)
        out.append((CHUNK_NAMES.get(magic, magic.decode("latin1")), ver, off, size))
        off += size
    return out


def ver_str(v):
    return struct.pack("<I", v).decode("latin1")


def read_points(buf, off, n, stride_cp=16, stride_inf=24):
    cps = [struct.unpack_from("<4f", buf, off + 16 * i) for i in range(n)]
    off += 16 * n
    infl = [struct.unpack_from("<4i2f", buf, off + 24 * i) for i in range(n)]
    off += 24 * n
    return cps, infl, off


def parse_nuno(buf, start, ver):
    off = start + 12
    n_sec = u32(buf, off)
    off += 4
    entries = []
    for _ in range(n_sec):
        magic, size, count = struct.unpack_from("<III", buf, off)
        off += 12
        sec_start = off
        kind = {0x00030001: "NUNO1", 0x00030002: "NUNO2", 0x00030003: "NUNO3", 0x00030004: "NUNO4", 0x00030005: "NUNO5"}.get(magic, hex(magic))
        if kind == "NUNO1":
            for _ in range(count):
                e0 = off
                parent, n, n_unk, s1, s2, s3 = struct.unpack_from("<6I", buf, off)
                off += 24
                plen = 0x3C + (0x10 if ver > 0x30303233 else 0) + (0x10 if ver >= 0x30303235 else 0)
                params = struct.unpack_from("<%df" % (plen // 4), buf, off)
                off += plen
                cps, infl, off = read_points(buf, off, n)
                off += 48 * n_unk + 4 * (s1 + s2 + s3)
                entries.append(dict(kind=kind, parent=parent, n=n, cps=cps, infl=infl, params=params, size=off - e0))
        elif kind == "NUNO3":
            for _ in range(count):
                e0 = off
                parent, n, n_unk, s1, _x, s2, s3, s4 = struct.unpack_from("<8I", buf, off)
                off += 32
                if ver < 0x30303330:
                    plen = 0xA8 + (0x10 if ver >= 0x30303235 else 0)
                    params = struct.unpack_from("<%df" % (plen // 4), buf, off)
                    off += plen
                else:
                    off += 8
                    t = u32(buf, off)
                    params = struct.unpack_from("<%df" % (t // 4), buf, off)
                    off += t
                cps, infl, off = read_points(buf, off, n)
                off += 48 * n_unk + 4 * s1 + 8 * s2 + 12 * s3 + 8 * s4
                entries.append(dict(kind=kind, parent=parent, n=n, cps=cps, infl=infl, params=params, size=off - e0))
        else:
            off = sec_start + size - 12
            entries.append(dict(kind=kind, count=count, skipped=True))
            continue
        off = sec_start + size - 12 if size else off
    return entries


def parse_nunv(buf, start, ver):
    off = start + 12
    n_sec = u32(buf, off)
    off += 4
    entries = []
    for _ in range(n_sec):
        magic, size, count = struct.unpack_from("<III", buf, off)
        off += 12
        sec_start = off
        if magic == 0x00050001:
            for _ in range(count):
                e0 = off
                parent, n, n_unk, s1 = struct.unpack_from("<4I", buf, off)
                off += 16
                plen = 0x54 + (0x10 if ver >= 0x30303131 else 0)
                params = struct.unpack_from("<%df" % (plen // 4), buf, off)
                off += plen
                cps, infl, off = read_points(buf, off, n)
                off += 48 * n_unk + 4 * s1
                entries.append(dict(kind="NUNV1", parent=parent, n=n, cps=cps, infl=infl, params=params, size=off - e0))
        else:
            entries.append(dict(kind=hex(magic), count=count, skipped=True))
        off = sec_start + size - 12
    return entries


def parse_soft(buf, start, ver):
    """SOFT = 软体（DarkStarSword 的 decode_doa6_soft.py / Project G1M SOFT.h）：每个条目挂在一根骨上，若干节点。"""
    off = start + 12
    n_sec = u32(buf, off)
    off += 4
    entries = []
    for _ in range(n_sec):
        magic, size, count = struct.unpack_from("<III", buf, off)
        off += 12
        sec_start = off
        if magic == 0x00080001:
            for _ in range(count):
                e0 = off
                h = struct.unpack_from("<13I", buf, off)
                node_count, u4, len3, parent, u6 = h[1], h[4], h[6], h[7], h[8]
                off += 52 + 96
                nodes = []
                for _ in range(node_count):
                    nid = u32(buf, off)
                    pos = struct.unpack_from("<3f", buf, off + 4)
                    n_inf = u32(buf, off + 36)
                    nodes.append((nid, pos, n_inf))
                    off += 40 + (n_inf + 1) * 8 + 0x18
                off += 4 * (u4 + node_count + u6 + 3 * len3 + 1)
                len5 = u32(buf, off)
                off += 4 * (len5 // 4 - 1)
                entries.append(dict(kind="SOFT1", parent=parent, n=node_count, nodes=nodes, size=off - e0))
        else:
            entries.append(dict(kind=hex(magic), count=count, skipped=True))
        off = sec_start + size - 12
    return entries


def parse_coll(buf, start):
    """COLL = 碰撞体表：若干组（看起来一块布 / 一个软体一组），每组若干条，每条 112 字节：
    类型 5、骨、-1、0、3 个尺寸参数、3×3 旋转 + 位移。返回 [(组标记, [骨, ...]), ...]。"""
    d = buf[start + 12:]
    n_groups = u32(d, 12)
    p = 16
    groups = []
    for _ in range(n_groups):
        flag, cnt = struct.unpack_from("<2I", d, p)
        p += 8
        bones = []
        for _ in range(cnt):
            kind, bone, m1, _z = struct.unpack_from("<4I", d, p)
            if kind != 5 or m1 != 0xFFFFFFFF:
                return groups
            bones.append(bone)
            p += 112
        groups.append((flag, bones))
    return groups


def parse_g1mg_meshes(buf, start, ver):
    off = start + 12
    _platform, _res = struct.unpack_from("<II", buf, off)
    n_sec = u32(buf, off + 32)
    off += 36
    submeshes, groups = [], []
    for _ in range(n_sec):
        magic, size, count = struct.unpack_from("<III", buf, off)
        p = off + 12
        if magic == 0x00010008:
            for j in range(count):
                v = struct.unpack_from("<14I", buf, p + 56 * j)
                submeshes.append(dict(vb=v[1], material=v[6], vertex_count=v[11], index_count=v[13]))
        elif magic == 0x00010009:
            for _ in range(count):
                if ver > 0x30303330:
                    lod, grp, gidx, c1, c2 = struct.unpack_from("<5I", buf, p)
                    p += 36 if ver > 0x30303430 else 20
                else:
                    lod, c1, c2 = struct.unpack_from("<3I", buf, p)
                    grp = gidx = 0
                    p += 12
                meshes = []
                for _ in range(c1 + c2):
                    name = buf[p:p + 16].split(b"\x00")[0].decode("latin1")
                    mtype, _pad, ext, n_idx = struct.unpack_from("<HHII", buf, p + 16)
                    p += 28
                    idx = list(struct.unpack_from("<%dI" % n_idx, buf, p)) if n_idx else []
                    p += 4 * n_idx if n_idx else 4
                    meshes.append(dict(name=name, type=mtype, external=ext, submeshes=idx))
                groups.append(dict(lod=lod, group=grp, meshes=meshes))
        off += size
    return submeshes, groups


def grid_shape(entry):
    """按连接数出布料网格的列（直接挂在骨上的点数）和行（最长的链）。"""
    infl = entry["infl"]
    n = len(infl)
    roots = [i for i, f in enumerate(infl) if f[2] == -1]
    depth = {}

    def d(i, guard=0):
        if i in depth:
            return depth[i]
        p = infl[i][2]
        depth[i] = 1 if p < 0 or p >= n or guard > n else d(p, guard + 1) + 1
        return depth[i]

    rows = max((d(i) for i in range(n)), default=0)
    return len(roots), rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("g1m")
    ap.add_argument("--params", action="store_true", help="打印每块布的物理参数块（float）")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    buf = open(args.g1m, "rb").read()
    cl = chunks(buf)
    print("块：", ", ".join("%s(v%s, %d KB)" % (n, ver_str(v), s // 1024) for n, v, _o, s in cl))
    cloth = {"NUNO1": [], "NUNO3": [], "NUNV1": []}
    meshes = []
    submeshes = []
    for name, ver, off, size in cl:
        if name == "NUNO":
            for e in parse_nuno(buf, off, ver):
                if not e.get("skipped"):
                    cloth[e["kind"]].append(e)
                else:
                    print("  （跳过的 NUNO 小节 %s ×%d）" % (e["kind"], e["count"]))
        elif name == "NUNV":
            for e in parse_nunv(buf, off, ver):
                if not e.get("skipped"):
                    cloth["NUNV1"].append(e)
        elif name == "SOFT":
            try:
                softs = parse_soft(buf, off, ver)
            except struct.error as err:
                softs = []
                print("  （SOFT 没读完：%s）" % err)
            for k, e in enumerate(softs):
                if e.get("skipped"):
                    print("  （跳过的 SOFT 小节 %s ×%d）" % (e["kind"], e["count"]))
                    continue
                ys = [p[1][1] for p in e["nodes"]] or [0]
                print("SOFT1 #%d  挂在骨 %d  节点 %d  节点 y %.1f..%.1f  每个节点的影响数 %s" % (
                    k, e["parent"] & 0x7FFFFFFF, e["n"], min(ys), max(ys), dict(Counter(p[2] for p in e["nodes"]).most_common(4))))
        elif name == "COLL":
            try:
                cg = parse_coll(buf, off)
                print("碰撞体：%d 组，%s 条；各组的骨 %s" % (len(cg), "+".join(str(len(b)) for _f, b in cg), [b for _f, b in cg]))
            except struct.error as err:
                print("  （COLL 没读完：%s）" % err)
        elif name == "G1MG":
            submeshes, groups = parse_g1mg_meshes(buf, off, ver)
            meshes = [m for g in groups if g["lod"] == 0 for m in g["meshes"]] or [m for g in groups for m in g["meshes"]]
    # 布料条目 -> 网格名
    by_ext = defaultdict(list)
    for m in meshes:
        if m["type"] in (1, 2):
            by_ext[(m["type"], m["external"])].append(m)
    print("\n网格（LOD0）：%d 个；类型统计 %s" % (len(meshes), dict(Counter(m["type"] for m in meshes))))
    for m in meshes:
        vc = sum(submeshes[i]["vertex_count"] for i in m["submeshes"] if i < len(submeshes))
        print("  %-16s 类型 %d  external %-6d 子网格 %-12s 顶点 %d" % (m["name"], m["type"], m["external"], m["submeshes"][:6], vc))
    out = []
    for kind, base in (("NUNO1", 0), ("NUNV1", 10000), ("NUNO3", 20000)):
        for k, e in enumerate(cloth[kind]):
            cols, rows = grid_shape(e)
            ys = [c[1] for c in e["cps"]]
            ws = Counter(round(c[3], 3) for c in e["cps"])
            names = sorted({m["name"] for (t, x), ms in by_ext.items() if x == base + k for m in ms})
            print("\n%s #%d  挂在骨 %d  控制点 %d = %d 列 × 最长 %d 行  高度 %.1f..%.1f  w 值 %s  用到它的网格 %s" % (
                kind, k, e["parent"] & 0x7FFFFFFF, e["n"], cols, rows, min(ys), max(ys), dict(ws.most_common(4)), names))
            if args.params:
                print("  参数 %s" % ", ".join("%.4g" % p for p in e["params"]))
            out.append(dict(kind=kind, index=k, parent=e["parent"] & 0x7FFFFFFF, n=e["n"], cols=cols, rows=rows,
                            meshes=names, params=list(e["params"]), cps=e["cps"], links=[list(f) for f in e["infl"]]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(dict(meshes=meshes, cloth=out), f)
        print("\n写出", args.json)


if __name__ == "__main__":
    sys.exit(main())
