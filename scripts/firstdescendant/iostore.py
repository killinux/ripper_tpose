"""Minimal UE5 IoStore (utoc/ucas) reader + zen package header parser for The First Descendant.

Pulls one cooked package out of the container (AES-ECB block decrypt + Oodle via the
oodle-data-shared.dll that CUE4Parse ships) and reads its name map / export map WITHOUT a
.usmap.  We use the name map to learn which textures a MaterialInstance references and which
material instances a mesh's slots use - the two facts CUE4Parse cannot give us for this game
because its 2024 mapping file no longer matches the MaterialInstance class layout.

    python iostore.py <utoc> <aes_key_file> <oodle dll> <M1/Content/.../Package.uasset>

Zen summary layout is the UE 5.2 one (TFD is 5.2-based; CUE4Parse's GAME_TheFirstDescendant
= GAME_UE5_2 + 3).  Shared with scripts/vindictus only in spirit; the container code here is
self-contained.
"""
import ctypes
import os
import struct
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

TOC_MAGIC = b"-==--==--==--==-"
NONE = 0xFFFFFFFF


class Toc:
    def __init__(self, utoc, key=None):
        self.utoc = utoc
        self.ucas = os.path.splitext(utoc)[0] + ".ucas"
        self.key = key
        with open(utoc, "rb") as fh:
            data = fh.read()
        assert data[:16] == TOC_MAGIC
        self.version = data[16]
        (hdr, n, nblk, blk_size, nmeth, meth_len, self.block_size, dir_size, parts) = struct.unpack_from("<9I", data, 20)
        self.flags = data[80]
        seeds, = struct.unpack_from("<I", data, 84)
        nohash, = struct.unpack_from("<I", data, 96)
        o = hdr
        self.chunk_ids = [data[o + 12 * i:o + 12 * i + 12] for i in range(n)]
        o += 12 * n
        self.offlen = []
        for i in range(n):
            b = data[o + 10 * i:o + 10 * i + 10]
            off = int.from_bytes(b[0:5], "big")
            ln = int.from_bytes(b[5:10], "big")
            self.offlen.append((off, ln))
        o += 10 * n
        if self.version >= 4:
            o += seeds * 4
        if self.version >= 5:
            o += nohash * 4
        self.blocks = []
        for i in range(nblk):
            b = data[o + blk_size * i:o + blk_size * i + blk_size]
            off = int.from_bytes(b[0:5], "little")
            csize = int.from_bytes(b[5:8], "little")
            usize = int.from_bytes(b[8:11], "little")
            method = b[11]
            self.blocks.append((off, csize, usize, method))
        o += blk_size * nblk
        self.methods = ["None"] + [data[o + meth_len * i:o + meth_len * i + meth_len].split(b"\0")[0].decode() for i in range(nmeth)]
        o += meth_len * nmeth
        if self.flags & 4:
            hs, = struct.unpack_from("<i", data, o)
            o += 4 + hs * 2 + nblk * 20
        self.dir_index = data[o:o + dir_size]
        if self.flags & 2:
            assert key, "encrypted container needs key"
            self.dir_index = Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(self.dir_index)
        self._paths = None

    # ---- directory index -> {path: toc entry index}
    def paths(self):
        if self._paths is not None:
            return self._paths
        idx = self.dir_index
        pos = 0
        n, = struct.unpack_from("<i", idx, pos); pos += 4
        mount = idx[pos:pos + n].decode("utf-8", "replace").rstrip("\0") if n > 0 else idx[pos:pos - 2 * n].decode("utf-16-le").rstrip("\0")
        pos += n if n > 0 else -2 * n
        dc, = struct.unpack_from("<I", idx, pos); pos += 4
        dirs = [struct.unpack_from("<4I", idx, pos + 16 * i) for i in range(dc)]; pos += 16 * dc
        fc, = struct.unpack_from("<I", idx, pos); pos += 4
        files = [struct.unpack_from("<3I", idx, pos + 12 * i) for i in range(fc)]; pos += 12 * fc
        sc, = struct.unpack_from("<I", idx, pos); pos += 4
        strings = []
        for _ in range(sc):
            n, = struct.unpack_from("<i", idx, pos); pos += 4
            if n > 0:
                strings.append(idx[pos:pos + n].decode("utf-8", "replace").rstrip("\0")); pos += n
            elif n < 0:
                strings.append(idx[pos:pos - 2 * n].decode("utf-16-le").rstrip("\0")); pos -= 2 * n
            else:
                strings.append("")
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
        self._paths = out
        return out

    # ---- read one chunk (by toc index) fully decrypted + decompressed
    def read_chunk(self, toc_index, oodle):
        off, ln = self.offlen[toc_index]
        first = off // self.block_size
        last = (off + ln - 1) // self.block_size
        out = bytearray()
        with open(self.ucas, "rb") as fh:
            for bi in range(first, last + 1):
                boff, csize, usize, method = self.blocks[bi]
                rsize = (csize + 15) & ~15 if (self.flags & 2) else csize
                fh.seek(boff)
                raw = fh.read(rsize)
                if self.flags & 2:
                    raw = Cipher(algorithms.AES(self.key), modes.ECB()).decryptor().update(raw)
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
                    raise RuntimeError("unknown compression %r" % name)
        start = off - first * self.block_size
        return bytes(out[start:start + ln])


class Oodle:
    def __init__(self, dll):
        self.lib = ctypes.CDLL(dll)
        self.fn = self.lib.OodleLZ_Decompress
        self.fn.restype = ctypes.c_size_t
        self.fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]

    def decompress(self, data, usize):
        out = ctypes.create_string_buffer(usize)
        n = self.fn(data, len(data), out, usize, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if n != usize:
            raise RuntimeError("oodle: got %d of %d" % (n, usize))
        return out.raw


# ---- zen package (UE5 cooked, io store) header
def read_name_batch(buf, pos):
    """FNameMap batch: count u32, numbytes u32, hashversion u64, hashes u64*count, headers u16*count, strings."""
    count, = struct.unpack_from("<I", buf, pos); pos += 4
    if count == 0:
        return [], pos
    nbytes, = struct.unpack_from("<I", buf, pos); pos += 4
    pos += 8  # hash version
    pos += 8 * count  # hashes
    headers = [struct.unpack_from(">H", buf, pos + 2 * i)[0] for i in range(count)]; pos += 2 * count
    names = []
    for h in headers:
        is_utf16 = h >> 15
        ln = h & 0x7FFF
        if is_utf16:
            names.append(buf[pos:pos + 2 * ln].decode("utf-16-le")); pos += 2 * ln
        else:
            names.append(buf[pos:pos + ln].decode("utf-8", "replace")); pos += ln
    return names, pos


def parse_zen(buf, ue52=True):  # noqa: C901
    """UE 5.2 zen summary (44 bytes): bHasVersioningInfo, HeaderSize, Name(FMappedName 8),
    PackageFlags, CookedHeaderSize, ImportedPublicExportHashesOffset, ImportMapOffset,
    ExportMapOffset, ExportBundleEntriesOffset, GraphDataOffset.  (5.3 adds three more int32.)"""
    has_ver, hdr_size = struct.unpack_from("<II", buf, 0)
    name_idx, name_num = struct.unpack_from("<II", buf, 8)
    pkg_flags, cooked_hdr = struct.unpack_from("<II", buf, 16)
    (imp_pub_hash_off, import_off, export_off, bundle_entries_off, graph_off) = struct.unpack_from("<5i", buf, 24)
    pos = 44 if ue52 else 52
    if has_ver:
        zen, uev, ueu, lic = struct.unpack_from("<4i", buf, pos); pos += 16
        ncv, = struct.unpack_from("<i", buf, pos); pos += 4 + 20 * ncv
    names, pos = read_name_batch(buf, pos)
    pkg_name = names[name_idx] if name_idx < len(names) else "?"
    n_imports = (export_off - import_off) // 8
    imports = [struct.unpack_from("<Q", buf, import_off + 8 * i)[0] for i in range(n_imports)]
    n_exports = (bundle_entries_off - export_off) // 72
    exports = []
    for i in range(n_exports):
        o = export_off + 72 * i
        (cso, css) = struct.unpack_from("<QQ", buf, o)
        (oname_idx, oname_num) = struct.unpack_from("<II", buf, o + 16)
        (outer, cls, sup, tmpl) = struct.unpack_from("<4Q", buf, o + 24)
        exports.append({"name": names[oname_idx] if oname_idx < len(names) else "?", "class_hash": cls,
                        "serial_offset": cso, "serial_size": css})
    return {"package": pkg_name, "flags": pkg_flags, "has_versioning": has_ver, "header_size": hdr_size,
            "names": names, "imports": imports, "exports": exports, "imported_packages": []}


if __name__ == "__main__":
    utoc, keyfile, dll, path = sys.argv[1:5]
    key = open(keyfile).read().strip()
    key = bytes.fromhex(key[2:] if key.lower().startswith("0x") else key)
    toc = Toc(utoc, key)
    print("toc v%d flags 0x%x methods %s blocks %d" % (toc.version, toc.flags, toc.methods, len(toc.blocks)))
    idx = toc.paths()[path]
    buf = toc.read_chunk(idx, Oodle(dll))
    print("chunk bytes:", len(buf))
    z = parse_zen(buf)
    print("package:", z["package"], "flags 0x%x (unversioned=%s) versioned_hdr=%s hdr %d names %d imports %d exports %d" % (z["flags"], bool(z["flags"] & 0x2000), z["has_versioning"], z["header_size"], len(z["names"]), len(z["imports"]), len(z["exports"])))
    print("exports:", [(e["name"], e["serial_size"]) for e in z["exports"]])
    print("imported packages (%d):" % len(z["imported_packages"]))
    for p in z["imported_packages"]:
        print("   ", p)
    print("names:", z["names"][:80])
