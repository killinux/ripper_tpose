#!/usr/bin/env python3
"""DOA6 (KTGL v2) .rdb 解包器。

替代 Cethleann.DataExporter：其 zlib 解压对每块只调一次 DeflateStream.Read，
读不满就丢弃剩余数据，导致大文件（几乎所有角色 g1m/g1t）在 ~80% 处截断。
本实现按块完整解压，产物大小与 G1M/G1T 头部声明一致。

格式（对照 Cethleann RDB.cs 与 eterniti rdbtool）：
  .rdb 索引  = RDBHeader(24B) + 数据目录字符串 + Count 个条目
  条目       = RDBEntry(48B: magic/ver/entrySize/contentSize/size/type/
               fileKTID/typeKTID/flags) + unknowns + 地址串
  地址串     = "offset@size[#binId][&binSub][?path]"（十六进制）
  数据体     = <name>.rdb.bin[<binId>][_<binSub>] 中 offset 处再包一层
               RDBEntry 头，其 content 为载荷
  flags      = 0x10000 external（散装 0x<ktid>.file）
               0x100000 zlib 分块压缩 / 0x200000 lz4
  zlib 分块  = [u32 块长][zlib 流] 重复，块长 0 或到尾部为止

文件名映射：filelist-DeadOrAlive6-rdb.csv（archive,ktid,name），
扩展名：filelist-RDBExt-rdb.csv（typeKTID,ext）。

用法：
  python extract_rdb.py <Archive.rdb> --list [--filter PAT] [--types g1m,g1t]
  python extract_rdb.py <Archive.rdb> -o <目录> [--filter PAT] [--types ...]
"""

import argparse
import fnmatch
import os
import re
import struct
import sys
import zlib

CETHLEANN_DIR = r"E:\tools\doa6\cethleann"
ADDRESS_RE = re.compile(
    r"([a-fA-F0-9]*)@([a-fA-F0-9]*)(?:#([a-fA-F0-9]*))?(?:&([a-fA-F0-9]*))?(?:\?(.*))?"
)
FLAG_EXTERNAL = 0x10000
FLAG_ZLIB = 0x100000
FLAG_LZ4 = 0x200000


def read_cstr(buf, off, end):
    stop = buf.index(b"\x00", off, end) if b"\x00" in buf[off:end] else end
    return buf[off:stop].decode("utf-8", "replace")


class RdbEntry:
    __slots__ = ("ktid", "type_ktid", "flags", "offset", "size", "bin_id", "bin_sub", "file_path", "name")

    def __init__(self):
        self.name = None


def parse_rdb(rdb_path):
    with open(rdb_path, "rb") as f:
        buf = f.read()
    magic, _ver, header_size, _system, count, name_db = struct.unpack_from("<4siIIiI", buf, 0)
    if magic not in (b"RDB\x00", b"_DRK", b"RDB "):
        # 实际魔数以文件为准，只要求头部自洽
        pass
    data_dir = read_cstr(buf, 24, header_size)
    entries = []
    off = header_size
    for _ in range(count):
        e_magic, _e_ver, entry_size, content_size, _size, _typ, ktid, type_ktid, flags = struct.unpack_from(
            "<4siqqqiIIi", buf, off
        )
        e = RdbEntry()
        e.ktid, e.type_ktid, e.flags = ktid, type_ktid, flags
        addr = buf[off + int(entry_size - content_size) : off + int(entry_size)]
        m = ADDRESS_RE.match(addr.split(b"\x00")[0].decode("ascii", "replace"))
        e.offset = int(m.group(1), 16) if m and m.group(1) else -1
        e.size = int(m.group(2), 16) if m and m.group(2) else -1
        e.bin_id = int(m.group(3), 16) if m and m.group(3) else -1
        e.bin_sub = int(m.group(4), 16) if m and m.group(4) else -1
        e.file_path = m.group(5) if m else None
        entries.append(e)
        off += (int(entry_size) + 3) & ~3
    return data_dir, entries


def load_filelists(archive_name, game_csv, ext_csv):
    names, exts = {}, {}
    if os.path.exists(game_csv):
        with open(game_csv, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split(",", 2)
                if len(parts) == 3 and parts[0] == archive_name:
                    try:
                        names[int(parts[1], 16)] = parts[2]
                    except ValueError:
                        pass
    if os.path.exists(ext_csv):
        with open(ext_csv, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith(";"):
                    continue
                parts = line.rstrip("\n").split(",", 1)
                if len(parts) == 2:
                    try:
                        exts[int(parts[0], 16)] = parts[1].strip()
                    except ValueError:
                        pass
    return names, exts


def decompress_zlib_chunks(buf, expect):
    out = bytearray()
    pos = 0
    n = len(buf)
    while pos + 4 <= n and len(out) < expect:
        (chunk_size,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        if chunk_size == 0 or pos + chunk_size > n:
            break
        out += zlib.decompress(buf[pos : pos + chunk_size])
        pos += chunk_size
    return bytes(out)


def decompress_lz4_chunks(buf, expect):
    import lz4.block  # pip install lz4

    out = bytearray()
    pos = 0
    n = len(buf)
    while pos + 4 <= n and len(out) < expect:
        (chunk_size,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        if chunk_size == 0 or pos + chunk_size > n:
            break
        out += lz4.block.decompress(buf[pos : pos + chunk_size], uncompressed_size=int(expect - len(out)))
        pos += chunk_size
    return bytes(out)


class Extractor:
    def __init__(self, rdb_path):
        self.rdb_path = rdb_path
        self.rdb_dir = os.path.dirname(os.path.abspath(rdb_path))
        self.archive = os.path.basename(rdb_path)[: -len(".rdb")]
        self.data_dir, self.entries = parse_rdb(rdb_path)
        self.names, self.exts = load_filelists(
            self.archive,
            os.path.join(CETHLEANN_DIR, "filelist-DeadOrAlive6-rdb.csv"),
            os.path.join(CETHLEANN_DIR, "filelist-RDBExt-rdb.csv"),
        )
        self._bins = {}
        self._ext_index = None

    def display_name(self, e):
        base = self.names.get(e.ktid, "%08x" % (e.ktid & 0xFFFFFFFF))
        ext = self.exts.get(e.type_ktid, "%08x" % (e.type_ktid & 0xFFFFFFFF))
        if "." not in os.path.basename(base):
            base = "%s.%s" % (base, ext)
        return base, ext

    def bin_handle(self, e):
        path = os.path.join(self.rdb_dir, self.archive + ".rdb.bin")
        if e.bin_id > -1:
            path += str(e.bin_id)
        if e.bin_sub > -1:
            path += "_%d" % e.bin_sub
        if path not in self._bins:
            self._bins[path] = open(path, "rb") if os.path.exists(path) else None
        return self._bins[path]

    def external_path(self, e):
        fname = e.file_path or ("0x%08x.file" % (e.ktid & 0xFFFFFFFF))
        for cand in (
            os.path.join(self.rdb_dir, self.data_dir, fname),
            os.path.join(self.rdb_dir, fname),
            os.path.join(self.rdb_dir, self.data_dir.replace("/", "_") + fname),
        ):
            if os.path.exists(cand):
                return cand
        if self._ext_index is None:
            self._ext_index = {}
            for root, _dirs, files in os.walk(self.rdb_dir):
                for fn in files:
                    if fn.endswith(".file") or ".file." in fn:
                        self._ext_index.setdefault(fn.split(".file")[0].lower(), os.path.join(root, fn))
        return self._ext_index.get(fname[: -len(".file")].lower() if fname.endswith(".file") else fname.lower())

    def read_entry(self, e):
        if e.flags & FLAG_EXTERNAL or e.file_path:
            path = self.external_path(e)
            if not path:
                raise FileNotFoundError("external 0x%08x.file" % (e.ktid & 0xFFFFFFFF))
            with open(path, "rb") as f:
                if e.offset > -1 and e.size > -1:
                    f.seek(e.offset)
                    blob = f.read(e.size)
                else:
                    blob = f.read()
        else:
            fh = self.bin_handle(e)
            if fh is None:
                raise FileNotFoundError("rdb.bin id=%d sub=%d" % (e.bin_id, e.bin_sub))
            fh.seek(e.offset)
            blob = fh.read(e.size)
        if len(blob) < 48:
            raise ValueError("entry blob too small (%d)" % len(blob))
        magic, _ver, entry_size, content_size, size, _typ, _ktid, _tktid, _flags = struct.unpack_from(
            "<4siqqqiIIi", blob, 0
        )
        if magic != b"IDRK":
            raise ValueError("inner magic %r != IDRK" % magic)
        payload = blob[int(entry_size - content_size) : int(entry_size)]
        if e.flags & FLAG_ZLIB:
            data = decompress_zlib_chunks(payload, size)
        elif e.flags & FLAG_LZ4:
            data = decompress_lz4_chunks(payload, size)
        else:
            data = payload
        if size and len(data) != size:
            raise ValueError("size mismatch: %d != %d" % (len(data), size))
        return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rdb_path", help=".rdb 索引路径")
    ap.add_argument("-o", "--out", help="输出目录（按扩展名分子目录）")
    ap.add_argument("--filter", default=None, help="按文件名 fnmatch 过滤（大小写不敏感）")
    ap.add_argument("--types", default=None, help="只要这些扩展名，逗号分隔（如 g1m,g1t,ktid,mtl,oid）")
    ap.add_argument("--list", action="store_true", help="只列出")
    ap.add_argument("--flat", action="store_true", help="不按扩展名分子目录")
    args = ap.parse_args()

    ex = Extractor(args.rdb_path)
    want_types = set(t.strip().lower() for t in args.types.split(",")) if args.types else None

    selected = []
    for e in ex.entries:
        name, ext = ex.display_name(e)
        if want_types and ext.lower() not in want_types:
            continue
        if args.filter and not fnmatch.fnmatch(name.lower(), args.filter.lower()):
            continue
        selected.append((e, name, ext))

    if args.list:
        for e, name, ext in selected:
            loc = "ext" if (e.flags & FLAG_EXTERNAL or e.file_path) else (
                "bin%s%s" % (e.bin_id if e.bin_id > -1 else "", "_%d" % e.bin_sub if e.bin_sub > -1 else "")
            )
            comp = "zlib" if e.flags & FLAG_ZLIB else ("lz4" if e.flags & FLAG_LZ4 else "raw")
            print("%-60s %8s %-6s %s" % (name, comp, loc, "0x%08x" % (e.ktid & 0xFFFFFFFF)))
        print("-- %d/%d 条目 (%s)" % (len(selected), len(ex.entries), ex.archive))
        return

    if not args.out:
        ap.error("需要 -o 输出目录（或 --list）")
    ok = fail = 0
    for e, name, ext in selected:
        out_dir = args.out if args.flat else os.path.join(args.out, ext)
        os.makedirs(out_dir, exist_ok=True)
        safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        try:
            data = ex.read_entry(e)
            with open(os.path.join(out_dir, safe), "wb") as f:
                f.write(data)
            ok += 1
        except Exception as err:
            print("失败 %s: %s" % (name, err), file=sys.stderr)
            fail += 1
    print("完成: %d 提取, %d 失败 -> %s" % (ok, fail, args.out))


if __name__ == "__main__":
    main()
