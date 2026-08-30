#!/usr/bin/env python3
"""DOA5LR .bin/.lnk 解包器（Archive Tool 1.2.1 算法的 Python 移植）。

游戏数据以 .bin（LFMO 索引，混淆文件名）+ .lnk（CHCM 数据体）成对存放。
文件名映射与 flags 来自社区维护的 file5lr.dat；加密条目用 doaKey（522 字节，
Archive Tool 资源里带的许可证文本片段）+ 由解压大小推导的 4 字节动态 key
做 XOR 流解密，再按 16 字节对齐的分块 zlib 解压。

用法：
  python extract_lnk.py <archive.bin> --list [--filter PATTERN]
  python extract_lnk.py <archive.bin> -o <输出目录> [--filter PATTERN]

PATTERN 是 fnmatch 通配符（大小写不敏感），如 "HONOKA*"、"*.TMC"。
"""

import argparse
import fnmatch
import os
import struct
import sys
import zlib

DEFAULT_TOOLS_DIR = r"E:\tools\doa5lr"


def load_name_db(dat_path):
    """file5lr.dat：制表符分隔，加密名 -> (真实名, flags)。

    同一加密名可能出现多行（不同索引/历史补丁），Archive Tool 按顺序消耗；
    对纯提取而言取第一条即可。end_flag 之后的行是当前补丁未使用的历史条目。
    """
    db = {}
    with open(dat_path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts or parts[0] == "end_flag":
                continue
            name = parts[1] if len(parts) > 1 else ""
            flags = parts[2] if len(parts) > 2 and parts[2] else "00000000"
            if parts[0] not in db:
                db[parts[0]] = (name, flags)
    return db


def parse_bin(bin_path):
    """LFMO 索引 -> 加密文件名列表（存储偏移 +1 跳过 '/' 前缀字节）。"""
    with open(bin_path, "rb") as f:
        data = f.read()
    if data[:4] != b"LFMO":
        raise ValueError("不是 LFMO 索引: %s" % bin_path)
    (count,) = struct.unpack_from("<I", data, 8)
    names = []
    pos = 0x30
    for i in range(count):
        (off,) = struct.unpack_from("<I", data, pos)
        off += 1
        end = data.index(b"\x00", off)
        names.append(data[off:end].decode("ascii"))
        pos += 12
    return names


def parse_lnk_entries(lnk_path):
    """条目表 @0x20，步长 0x20：offset u32, pad, size u32。

    魔数是每个封包各自的 4 字节标签（chara_common=CHCM、chara_initial=CHIN、
    stage_common=STCM、patch_25_catalog=P25C …），结构一致，所以只做长度校验，
    不锁定具体标签。
    """
    with open(lnk_path, "rb") as f:
        head = f.read(12)
        (count,) = struct.unpack_from("<I", head, 8)
        if count <= 0 or count > 1_000_000:
            raise ValueError("条目数异常 (%d)，可能不是 lnk 数据体: %s" % (count, lnk_path))
        f.seek(0)
        table = f.read((count + 1) * 32)
    entries = []
    pos = 0x20
    for i in range(count):
        offset, _, size = struct.unpack_from("<III", table, pos)
        entries.append((offset, size))
        pos += 32
    return entries


def decrypt(buf, decomp_size, doa_key):
    """XOR 流解密（条目前 4 字节是解压大小头，不参与）。

    动态 key：uint32 运算 (((n+0x3E7)*7)/0xB)+(n%0x11)+0x1AC，
    取其小端字节的倒序并剔除零字节。0 字节与恰好等于 key 流字节的
    字节保持原样（C# 端同款判断，保证可逆）。
    """
    n = decomp_size & 0xFFFFFFFF
    v = ((((n + 0x3E7) * 7) & 0xFFFFFFFF) // 0xB + (n % 0x11) + 0x1AC) & 0xFFFFFFFF
    crypt_key = bytes(b for b in struct.pack("<I", v)[::-1] if b != 0)
    out = bytearray(buf)
    ck_len, dk_len = len(crypt_key), len(doa_key)
    for i in range(4, len(out)):
        x = crypt_key[(i - 4) % ck_len] ^ doa_key[(i - 4) % dk_len]
        b = out[i]
        if b != 0 and b != x:
            out[i] = b ^ x
    return bytes(out)


def decompress_entry(buf):
    """[u32 解压大小][分块]，块头 u32：>0x8000 为 zlib 块（减 0x8000 得长度），
    否则原样块；每块后按 (pos-4) 对 16 字节对齐。"""
    (decomp_size,) = struct.unpack_from("<I", buf, 0)
    out = bytearray()
    pos = 4
    end = len(buf)
    while pos + 4 <= end and len(out) < decomp_size:
        (raw,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        chunk = raw - 0x8000
        if chunk > 0:
            out += zlib.decompress(buf[pos : pos + chunk])
            pos += chunk
        else:
            out += buf[pos : pos + raw]
            pos += raw
        if (pos - 4) % 16 != 0:
            pos = pos - ((pos - 4) % 16) + 16
    return bytes(out), decomp_size


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin_path", help=".bin 索引路径（.lnk 需同名同目录）")
    ap.add_argument("-o", "--out", help="输出目录（省略且未 --list 时报错）")
    ap.add_argument("--filter", default=None, help="fnmatch 通配符过滤真实文件名（大小写不敏感）")
    ap.add_argument("--list", action="store_true", help="只列出条目，不提取")
    ap.add_argument("--db", default=os.path.join(DEFAULT_TOOLS_DIR, "file5lr.dat"), help="file5lr.dat 路径")
    ap.add_argument("--key", default=os.path.join(DEFAULT_TOOLS_DIR, "doaKey"), help="doaKey 路径")
    args = ap.parse_args()

    lnk_path = os.path.splitext(args.bin_path)[0] + ".lnk"
    db = load_name_db(args.db)
    with open(args.key, "rb") as f:
        doa_key = f.read()
    if len(doa_key) != 522:
        print("警告: doaKey 长度 %d != 522，可能不是正确的 key 文件" % len(doa_key), file=sys.stderr)

    names = parse_bin(args.bin_path)
    entries = parse_lnk_entries(lnk_path)
    if len(names) != len(entries):
        raise ValueError("索引/数据条目数不一致: %d vs %d" % (len(names), len(entries)))

    unknown = 0
    selected = []
    for i, enc in enumerate(names):
        real, flags = db.get(enc, ("", None))
        if flags is None:
            unknown += 1
            real, flags = enc, "00000000"
        elif not real:
            real = enc
        if args.filter and not fnmatch.fnmatch(real.lower(), args.filter.lower()):
            continue
        selected.append((i, enc, real, flags))

    if args.list:
        for i, enc, real, flags in selected:
            off, size = entries[i]
            print("%5d  %-40s %8s  %10d  @0x%X" % (i, real, flags, size, off))
        print("-- %d/%d 条目%s" % (len(selected), len(names), "，%d 个未知名" % unknown if unknown else ""))
        return

    if not args.out:
        ap.error("需要 -o 输出目录（或用 --list）")
    os.makedirs(args.out, exist_ok=True)

    ok = warn = 0
    with open(lnk_path, "rb") as lnk:
        for i, enc, real, flags in selected:
            off, size = entries[i]
            lnk.seek(off)
            buf = lnk.read(size)
            out_name = real.translate(str.maketrans('\\/:*?"<>|', "_________"))
            out_path = os.path.join(args.out, out_name)
            try:
                if flags[0] != "0":
                    if flags[0] in ("E", "C"):
                        (dsz,) = struct.unpack_from("<I", buf, 0)
                        buf = decrypt(buf, dsz, doa_key)
                    data, expect = decompress_entry(buf)
                    if len(data) != expect:
                        print("警告: %s 解压大小 %d != %d" % (real, len(data), expect), file=sys.stderr)
                        warn += 1
                else:
                    data = buf
                with open(out_path, "wb") as f:
                    f.write(data)
                ok += 1
            except Exception as e:
                print("失败: %s (#%d, flags=%s): %s" % (real, i, flags, e), file=sys.stderr)
                warn += 1
    print("完成: %d 提取, %d 警告/失败 -> %s" % (ok, warn, args.out))


if __name__ == "__main__":
    main()
