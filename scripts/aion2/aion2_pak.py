"""AION2 (NCSOFT, Unreal Engine 5.3, Steam app 3393110) container reader - no usmap needed.

The game ships ~280 IoStore containers (``Aion2/Content/Paks/**/*.utoc|ucas``, utoc v5, Oodle) plus
legacy ``.pak`` files that only carry the pak index.  245 containers are AES-256 encrypted with the
default key (key GUID all zero) - the directory index AND every compressed block.  This module:

* reads every ``.utoc`` (header, chunk offsets, compression blocks, AES-decrypted directory index)
  and merges them into one ``path -> (container, toc entry)`` map; ``*_P`` patch containers win over
  the base ones, the way the engine mounts them;
* reads a package chunk, or just its first bytes (enough for the package header);
* parses the UE 5.3 zen package summary (52 bytes), the name map and the export map;
* resolves export classes through the script objects in ``global.utoc``
  (``/Script/Engine.SkeletalMesh`` ...).

The AES key is never in the repo: ``--key-file`` (default ``E:\\tools\\aion2\\_keys\\aes_key.txt``) or the
``AION2_AES_KEY`` environment variable.  The executable is packed by NCGuard (sections ``.ncg0``..
``.ncg6``, code encrypted on disk), so the key cannot be scanned out of the file the way
``scripts/firstdescendant/find_aes_key.py`` does for Nexon games - see README.md for where it came from.

Oodle: ``oodle-data-shared.dll`` (CUE4Parse downloads it; a copy sits next to the CUE4Parse CLI).

    python aion2_pak.py --info                                   # containers, flags, path count
    python aion2_pak.py --header AION2/Content/Character/Player/GF/Basebody/GF_BaseBody.uasset
"""
from __future__ import annotations

import argparse
import ctypes
import glob
import os
import struct
import sys

TOC_MAGIC = b"-==--==--==--==-"
NONE = 0xFFFFFFFF

DEFAULT_GAME_ROOT = r"D:\Program Files (x86)\Steam\steamapps\common\AION2"
DEFAULT_KEY_FILE = r"E:\tools\aion2\_keys\aes_key.txt"
DEFAULT_OODLE = r"E:\tools\cue4parse_cli\oodle-data-shared.dll"
KEY_ENV = "AION2_AES_KEY"

PKG_UNVERSIONED = 0x2000

# container flags
FLAG_COMPRESSED, FLAG_ENCRYPTED, FLAG_SIGNED, FLAG_INDEXED = 1, 2, 4, 8


def paks_dir(game_root: str) -> str:
    return os.path.join(game_root, "Aion2", "Content", "Paks")


def read_key(key: str | None = None, key_file: str | None = DEFAULT_KEY_FILE) -> bytes:
    key = key or os.environ.get(KEY_ENV, "")
    if not key and key_file and os.path.isfile(key_file):
        key = open(key_file, encoding="utf-8").read().strip()
    key = key.strip()
    if key.lower().startswith("0x"):
        key = key[2:]
    if len(key) != 64:
        raise SystemExit("AION2 AES key missing: put it in %s or set %s (see scripts/aion2/README.md)"
                         % (DEFAULT_KEY_FILE, KEY_ENV))
    return bytes.fromhex(key)


def _aes_ecb(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(data)


class Oodle:
    def __init__(self, dll: str = DEFAULT_OODLE):
        if not os.path.isfile(dll):
            raise SystemExit("oodle-data-shared.dll not found at %s (--oodle)" % dll)
        self.lib = ctypes.CDLL(dll)
        self.fn = self.lib.OodleLZ_Decompress
        self.fn.restype = ctypes.c_size_t
        self.fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]

    def decompress(self, data: bytes, usize: int) -> bytes:
        out = ctypes.create_string_buffer(usize)
        n = self.fn(data, len(data), out, usize, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if n != usize:
            raise RuntimeError("oodle: got %d of %d bytes" % (n, usize))
        return out.raw


class Toc:
    """One .utoc/.ucas pair (utoc v5 = PerfectHashWithOverflow, as UE 5.3 writes it)."""

    def __init__(self, utoc: str, key: bytes | None):
        self.utoc = utoc
        self.ucas = os.path.splitext(utoc)[0] + ".ucas"
        self.key = key
        with open(utoc, "rb") as fh:
            data = fh.read()
        if data[:16] != TOC_MAGIC:
            raise ValueError("not a utoc: %s" % utoc)
        self.version = data[16]
        (hdr, n, nblk, blk_size, nmeth, meth_len, self.block_size, dir_size, _parts) = struct.unpack_from("<9I", data, 20)
        self.flags = data[80]
        seeds, = struct.unpack_from("<I", data, 84)
        nohash, = struct.unpack_from("<I", data, 96)
        o = hdr
        self.chunk_ids = [data[o + 12 * i:o + 12 * i + 12] for i in range(n)]
        o += 12 * n
        self.offlen = []
        for i in range(n):
            b = data[o + 10 * i:o + 10 * i + 10]
            self.offlen.append((int.from_bytes(b[0:5], "big"), int.from_bytes(b[5:10], "big")))
        o += 10 * n
        if self.version >= 4:
            o += seeds * 4
        if self.version >= 5:
            o += nohash * 4
        self.blocks = []
        for i in range(nblk):
            b = data[o + blk_size * i:o + blk_size * i + blk_size]
            self.blocks.append((int.from_bytes(b[0:5], "little"), int.from_bytes(b[5:8], "little"),
                                int.from_bytes(b[8:11], "little"), b[11]))
        o += blk_size * nblk
        self.methods = ["None"] + [data[o + meth_len * i:o + meth_len * (i + 1)].split(b"\0")[0].decode()
                                   for i in range(nmeth)]
        o += meth_len * nmeth
        if self.flags & FLAG_SIGNED:
            hs, = struct.unpack_from("<i", data, o)
            o += 4 + hs * 2 + nblk * 20
        self.dir_index = data[o:o + dir_size]
        if self.flags & FLAG_ENCRYPTED and self.dir_index:
            if not key:
                raise ValueError("encrypted container needs the AES key: %s" % utoc)
            self.dir_index = _aes_ecb(key, self.dir_index)
        self._fh = None

    # directory index -> {path: toc entry}
    def paths(self) -> dict:
        idx = self.dir_index
        if not idx:
            return {}
        pos = 0

        def fstring(p):
            n, = struct.unpack_from("<i", idx, p)
            p += 4
            if n > 0:
                return idx[p:p + n].decode("utf-8", "replace").rstrip("\0"), p + n
            if n < 0:
                return idx[p:p - 2 * n].decode("utf-16-le").rstrip("\0"), p - 2 * n
            return "", p

        mount, pos = fstring(pos)
        dc, = struct.unpack_from("<I", idx, pos); pos += 4
        dirs = [struct.unpack_from("<4I", idx, pos + 16 * i) for i in range(dc)]; pos += 16 * dc
        fc, = struct.unpack_from("<I", idx, pos); pos += 4
        files = [struct.unpack_from("<3I", idx, pos + 12 * i) for i in range(fc)]; pos += 12 * fc
        sc, = struct.unpack_from("<I", idx, pos); pos += 4
        strings = []
        for _ in range(sc):
            s, pos = fstring(pos)
            strings.append(s)
        mount = mount.replace("\\", "/")
        while mount.startswith("../"):
            mount = mount[3:]
        out = {}
        stack = [(0, mount.rstrip("/"))]
        while stack:
            e, prefix = stack.pop()
            name, child, _sib, first_file = dirs[e]
            path = prefix if name == NONE else (prefix + "/" + strings[name] if prefix else strings[name])
            f = first_file
            while f != NONE:
                fname, nxt, user = files[f]
                out[(path + "/" + strings[fname]) if path else strings[fname]] = user
                f = nxt
            c = child
            while c != NONE:
                stack.append((c, path))
                c = dirs[c][2]
        return out

    def read(self, toc_index: int, oodle: Oodle, length: int | None = None) -> bytes:
        """Chunk bytes, decrypted + decompressed; ``length`` reads only the first bytes."""
        off, ln = self.offlen[toc_index]
        if length is not None:
            ln = min(ln, length)
        first = off // self.block_size
        last = (off + ln - 1) // self.block_size
        if self._fh is None:
            self._fh = open(self.ucas, "rb")
        fh = self._fh
        out = bytearray()
        for bi in range(first, last + 1):
            boff, csize, usize, method = self.blocks[bi]
            rsize = (csize + 15) & ~15 if self.flags & FLAG_ENCRYPTED else csize
            fh.seek(boff)
            raw = fh.read(rsize)
            if self.flags & FLAG_ENCRYPTED:
                raw = _aes_ecb(self.key, raw)
            raw = raw[:csize]
            name = self.methods[method] if method < len(self.methods) else "?"
            if method == 0:
                out += raw[:usize]
            elif name.lower().startswith("oodle"):
                out += oodle.decompress(raw, usize)
            elif name.lower() == "zlib":
                import zlib
                out += zlib.decompress(raw)
            else:
                raise RuntimeError("unknown compression %r in %s" % (name, self.utoc))
        start = off - first * self.block_size
        return bytes(out[start:start + ln])


class Game:
    """All containers of one install: ``index[path] = (container number, toc entry)``."""

    def __init__(self, game_root: str = DEFAULT_GAME_ROOT, key: bytes | None = None, oodle_dll: str = DEFAULT_OODLE,
                 load_index: bool = True):
        self.root = game_root
        self.paks = paks_dir(game_root)
        if not os.path.isdir(self.paks):
            raise SystemExit("AION2 Paks folder not found: %s (--game-root)" % self.paks)
        self.key = key
        self._oodle_dll = oodle_dll
        self._oodle = None
        utocs = sorted(glob.glob(os.path.join(self.paks, "**", "*.utoc"), recursive=True),
                       key=lambda p: (p.endswith("_P.utoc"), p.lower()))  # patches last = they win
        self.tocs = [Toc(p, key) for p in utocs]
        self.index = {}
        if load_index:
            for ci, toc in enumerate(self.tocs):
                for path, entry in toc.paths().items():
                    self.index[path] = (ci, entry)
        self._script = None

    @property
    def oodle(self) -> Oodle:
        if self._oodle is None:
            self._oodle = Oodle(self._oodle_dll)
        return self._oodle

    def container_name(self, ci: int) -> str:
        return os.path.relpath(self.tocs[ci].utoc, self.paks)

    def read(self, path: str, length: int | None = None) -> bytes:
        ci, entry = self.index[path]
        return self.tocs[ci].read(entry, self.oodle, length)

    def header(self, path: str) -> dict:
        """Zen package header of ``path`` (reads only as many blocks as the header needs)."""
        head = self.read(path, 0x10000)
        size, = struct.unpack_from("<I", head, 4)
        if size > len(head):
            head = self.read(path, size)
        return parse_zen53(head)

    # global script objects: FPackageObjectIndex -> "/Script/Engine.SkeletalMesh"
    def script_objects(self) -> dict:
        if self._script is None:
            g = next(t for t in self.tocs if os.path.basename(t.utoc).lower() == "global.utoc")
            buf = g.read(0, self.oodle)
            names, pos = read_name_batch(buf, 0)
            n, = struct.unpack_from("<i", buf, pos)
            pos += 4
            name_of, outer_of = {}, {}
            for i in range(n):
                ni, _nn, gidx, outer, _cdo = struct.unpack_from("<IIQQQ", buf, pos + 32 * i)
                name_of[gidx] = names[ni & 0x3FFFFFFF]
                outer_of[gidx] = outer
            full = {}
            for gidx in name_of:
                parts, g2 = [], gidx
                while g2 in name_of:
                    parts.append(name_of[g2])
                    g2 = outer_of[g2]
                full[gidx] = ".".join(reversed(parts))
            self._script = full
        return self._script

    def class_name(self, class_index: int) -> str:
        full = self.script_objects().get(class_index)
        return full.rsplit(".", 1)[-1] if full else "?"


# ---------------------------------------------------------------- zen package header (UE 5.3)
def read_name_batch(buf: bytes, pos: int):
    """count u32, string bytes u32, hash version u64, hashes u64*count, headers u16 BE*count, strings."""
    count, = struct.unpack_from("<I", buf, pos); pos += 4
    if count == 0:
        return [], pos
    pos += 4 + 8 + 8 * count
    headers = [struct.unpack_from(">H", buf, pos + 2 * i)[0] for i in range(count)]
    pos += 2 * count
    names = []
    for h in headers:
        ln = h & 0x7FFF
        if h >> 15:
            names.append(buf[pos:pos + 2 * ln].decode("utf-16-le")); pos += 2 * ln
        else:
            names.append(buf[pos:pos + ln].decode("utf-8", "replace")); pos += ln
    return names, pos


def parse_zen53(buf: bytes) -> dict:
    """UE 5.3 FZenPackageSummary (52 bytes): bHasVersioningInfo, HeaderSize, Name, PackageFlags,
    CookedHeaderSize, ImportedPublicExportHashesOffset, ImportMapOffset, ExportMapOffset,
    ExportBundleEntriesOffset, DependencyBundleHeadersOffset, DependencyBundleEntriesOffset,
    ImportedPackageNamesOffset; then the name map; export entries are 72 bytes."""
    has_ver, hdr_size = struct.unpack_from("<II", buf, 0)
    name_idx, _name_num = struct.unpack_from("<II", buf, 8)
    pkg_flags, _cooked = struct.unpack_from("<II", buf, 16)
    _hash_off, import_off, export_off, bundle_off = struct.unpack_from("<4i", buf, 24)
    imported_names_off, = struct.unpack_from("<i", buf, 48)
    pos = 52
    if has_ver:
        pos += 16
        ncv, = struct.unpack_from("<i", buf, pos)
        pos += 4 + 20 * ncv
    names, pos = read_name_batch(buf, pos)
    exports = []
    for i in range((bundle_off - export_off) // 72):
        o = export_off + 72 * i
        serial_off, serial_size = struct.unpack_from("<QQ", buf, o)
        oname, _onum = struct.unpack_from("<II", buf, o + 16)
        outer, cls, _sup, _tmpl = struct.unpack_from("<4Q", buf, o + 24)
        exports.append({"name": names[oname & 0x3FFFFFFF] if (oname & 0x3FFFFFFF) < len(names) else "?",
                        "class_index": cls, "outer": outer, "serial_size": serial_size})
    imported = []                     # the packages this one imports (materials, skeleton ...), a name batch in 5.3
    if 0 < imported_names_off < len(buf):
        try:
            imported, _ = read_name_batch(buf, imported_names_off)
        except (struct.error, UnicodeDecodeError):
            imported = []
    return {"package": names[name_idx & 0x3FFFFFFF] if (name_idx & 0x3FFFFFFF) < len(names) else "?",
            "flags": pkg_flags, "unversioned": bool(pkg_flags & PKG_UNVERSIONED), "header_size": hdr_size,
            "names": names, "imports": (export_off - import_off) // 8, "exports": exports,
            "imported_packages": imported}


def main_class(game: Game, header: dict, path: str) -> str:
    """Class of the package's asset: the export named like the file, else the largest export."""
    stem = os.path.splitext(os.path.basename(path))[0]
    exports = header["exports"]
    if not exports:
        return "-"
    same = [e for e in exports if e["name"] == stem]
    e = same[0] if same else max(exports, key=lambda x: x["serial_size"])
    return game.class_name(e["class_index"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-root", default=DEFAULT_GAME_ROOT)
    ap.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--oodle", default=DEFAULT_OODLE)
    ap.add_argument("--info", action="store_true", help="containers, flags and the number of paths")
    ap.add_argument("--header", metavar="PATH", help="print one package header (exports + classes)")
    args = ap.parse_args()
    game = Game(args.game_root, read_key(key_file=args.key_file), args.oodle)
    if args.info:
        enc = sum(1 for t in game.tocs if t.flags & FLAG_ENCRYPTED)
        print("containers: %d (%d encrypted), paths: %d" % (len(game.tocs), enc, len(game.index)))
    if args.header:
        h = game.header(args.header)
        print("package %s flags 0x%x unversioned=%s names %d imports %d" % (
            h["package"], h["flags"], h["unversioned"], len(h["names"]), h["imports"]))
        for e in h["exports"]:
            print("  %-48s %-32s %d" % (e["name"], game.class_name(e["class_index"]), e["serial_size"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
