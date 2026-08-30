#!/usr/bin/env python3
"""从 g1m + ktid 生成 submesh→贴图 映射 JSON。

G1MG 材质段（magic 0x00010002）：每材质 = [unk u32][texCount u32][skip 8B]
  + texCount × {slot u16, layer u16, type u16, otherType u16, tileX u16, tileY u16}
submesh 段（0x00010008）：14×u32，materialIndex 在第 7 个。
DOA6 的 slot 对应 .ktid 表（(index u32, ktid u32) 对）里的位置；
贴图真名用 filelist-DeadOrAlive6-rdb.csv（MaterialEditor 段）反查，
通道语义直接取名字里的 kids* 后缀。

ktid 槽位值是 TexContext 对象 KTID，存于 CharacterEditor/MaterialEditor 的
kidssingletondb（IDOK 记录：hdr12 + ktid + typeinfo + propCount + 属性表 + 值区；
属性 0x6c7321d2 = KTGLTexContextResourceHash，其 UInt32 值即 g1t 资源 KTID）。

用法: python g1m_matmap.py <xxx.g1m> <xxx.ktid> [-o out.json]
输出: {"submeshes": [{"index":0,"material":N,"textures":[{"slot":s,"name":..,"channel":"alb"}]}]}
"""

import argparse
import json
import os
import struct
import sys

CSV = r"E:\tools\doa6\cethleann\filelist-DeadOrAlive6-rdb.csv"
SINGLETON_DBS = [
    r"D:\doa6_exports\_objdb\CharacterEditor.kidssingletondb",
    r"D:\doa6_exports\_objdb\MaterialEditor.kidssingletondb",
]
PROP_TEXCONTEXT_HASH = 0x6C7321D2


def load_names():
    names = {}
    with open(CSV, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split(",", 2)
            if len(parts) == 3:
                try:
                    names[int(parts[1], 16)] = parts[2]
                except ValueError:
                    pass
    return names


TYPE_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 10: 16, 12: 8, 13: 12}


def load_texcontexts(paths):
    """扫 kidssingletondb 的 IDOK 记录，取 TexContext ktid -> g1t 资源 KTID。"""
    out = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            b = f.read()
        pos = b.find(b"IDOK")
        while pos >= 0:
            if pos + 24 > len(b):
                break
            (size,) = struct.unpack_from("<I", b, pos + 8)
            if size < 24 or pos + size > len(b):
                pos = b.find(b"IDOK", pos + 4)
                continue
            ktid, _tinfo, pcount = struct.unpack_from("<IIi", b, pos + 12)
            if 0 < pcount <= 64:
                p = pos + 24
                props = []
                ok = True
                for _ in range(pcount):
                    if p + 12 > pos + size:
                        ok = False
                        break
                    tid, cnt, pktid = struct.unpack_from("<IiI", b, p)
                    props.append((tid, cnt, pktid))
                    p += 12
                if ok:
                    vo = p
                    for tid, cnt, pktid in props:
                        sz = TYPE_SIZES.get(tid, 0) * max(0, cnt)
                        if pktid == PROP_TEXCONTEXT_HASH and tid == 5 and cnt >= 1 and vo + 4 <= pos + size:
                            (res,) = struct.unpack_from("<I", b, vo)
                            out[ktid] = res
                        vo += sz
            pos = b.find(b"IDOK", pos + size)
    return out


def parse_ktid(path):
    with open(path, "rb") as f:
        b = f.read()
    table = {}
    for off in range(0, len(b) - 7, 8):
        idx, ktid = struct.unpack_from("<II", b, off)
        table[idx] = ktid
    return table


def parse_g1m(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"_M1G":
        raise ValueError("not a G1M: %s" % path)
    (header_size,) = struct.unpack_from("<I", b, 12)
    pos = header_size
    materials, submeshes = [], []
    while pos + 12 <= len(b):
        magic = b[pos : pos + 4]
        (_ver, size) = struct.unpack_from("<II", b, pos + 4)
        if magic == b"GM1G":
            spos = pos + 12  # GResourceHeader
            spos += 36  # G1MGHeader: platform..sectionCount(9*u32)
            (section_count,) = struct.unpack_from("<I", b, pos + 12 + 32)
            checkpoint = spos
            for _ in range(section_count):
                s_magic, s_size, s_count = struct.unpack_from("<III", b, checkpoint)
                p = checkpoint + 12
                if s_magic == 0x00010002:  # materials
                    for _j in range(s_count):
                        (tex_count,) = struct.unpack_from("<I", b, p + 4)
                        p += 16  # unk u32 + (texCount 起算的 12B 头)，见 G1MGMaterial.h
                        texs = []
                        for _k in range(tex_count):
                            slot, layer, ttype, otype, tx, ty = struct.unpack_from("<6H", b, p)
                            texs.append({"slot": slot, "layer": layer, "type": ttype})
                            p += 12
                        materials.append(texs)
                elif s_magic == 0x00010008:  # submeshes
                    for j in range(s_count):
                        vals = struct.unpack_from("<14I", b, p)
                        submeshes.append({"index": j, "material": vals[6], "vertexCount": vals[11]})
                        p += 56
                checkpoint += s_size
        pos += size
    return materials, submeshes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("g1m")
    ap.add_argument("ktid")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    names = load_names()
    ktid_table = parse_ktid(args.ktid)
    texctx = load_texcontexts(SINGLETON_DBS)
    materials, submeshes = parse_g1m(args.g1m)

    def resolve(slot):
        obj = ktid_table.get(slot)
        if obj is None:
            return None
        ktid = texctx.get(obj, obj)  # TexContext 对象 -> g1t 资源；查不到就当直接引用
        name = names.get(ktid, "%08x" % ktid)
        base = os.path.basename(name)
        channel = base.rsplit("_kids", 1)[1].split(".")[0] if "_kids" in base else "?"
        if not base.endswith(".g1t"):
            base += ".g1t"
        return {"slot": slot, "name": base, "channel": channel}

    out = {"g1m": os.path.basename(args.g1m), "submeshes": []}
    for sm in submeshes:
        texs = []
        if sm["material"] < len(materials):
            for t in materials[sm["material"]]:
                r = resolve(t["slot"])
                if r:
                    r["layer"] = t["layer"]
                    texs.append(r)
        out["submeshes"].append({"index": sm["index"], "material": sm["material"], "vertexCount": sm["vertexCount"], "textures": texs})

    text = json.dumps(out, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote %s (%d submeshes, %d materials)" % (args.out, len(submeshes), len(materials)))
    else:
        print(text)


if __name__ == "__main__":
    main()
