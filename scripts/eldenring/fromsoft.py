# -*- coding: utf-8 -*-
"""FromSoftware file formats as Elden Ring mods ship them, read in plain Python (+ numpy):

  DCX     compressed wrapper: DFLT (zlib) or KRAK (Oodle Kraken, decoded with the Oodle DLL CUE4Parse downloads)
  BND4    archive (.partsbnd, .matbinbnd ...): named entries
  TPF     texture pack: whole DDS files
  FLVER2  model: dummies, materials, textures, bones, meshes (vertex buffers + face sets)
  MATBIN  material: shader path, parameters, samplers (texture slots) - Elden Ring keeps a material's texture
          paths here when the FLVER leaves them empty

Layouts follow SoulsFormats (JKAnderson / Meowmaritus).  Only reading; nothing is written back.

    python fromsoft.py <file.dcx|.bnd|.flver|.tpf> ...      prints what is inside
"""
import ctypes
import os
import struct
import sys
import zlib

import numpy as np

DEFAULT_OODLE = os.environ.get("OODLE_DLL", r"E:\tools\cue4parse_cli\oodle-data-shared.dll")


# ----------------------------------------------------------------------------------------------------------- DCX
class _Oodle:
    _lib = None

    @classmethod
    def decompress(cls, data, usize, dll=DEFAULT_OODLE):
        if cls._lib is None:
            if not os.path.isfile(dll):
                raise SystemExit("Oodle DLL not found at %s (set OODLE_DLL)" % dll)
            cls._lib = ctypes.CDLL(dll)
            fn = cls._lib.OodleLZ_Decompress
            fn.restype = ctypes.c_size_t
            fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        out = ctypes.create_string_buffer(usize)
        n = cls._lib.OodleLZ_Decompress(data, len(data), out, usize, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if n != usize:
            raise RuntimeError("Oodle: got %d of %d bytes" % (n, usize))
        return out.raw


def is_dcx(data):
    return data[:4] == b"DCX\0"


def dcx_decompress(data):
    """-> (raw bytes, format name).  Not a DCX -> returned as it is."""
    if not is_dcx(data):
        return data, None
    if data[0x18:0x1C] != b"DCS\0" or data[0x24:0x28] != b"DCP\0":
        raise ValueError("unknown DCX header")
    usize, csize = struct.unpack(">II", data[0x1C:0x24])
    fmt = data[0x28:0x2C].decode("ascii")
    dca = data.find(b"DCA\0", 0x2C, 0x80)
    start = dca + struct.unpack(">I", data[dca + 4:dca + 8])[0]
    comp = data[start:start + csize]
    if fmt == "DFLT":
        raw = zlib.decompress(comp)
    elif fmt == "KRAK":
        raw = _Oodle.decompress(comp, usize)
    else:
        raise NotImplementedError("DCX format %s" % fmt)
    if len(raw) != usize:
        raise ValueError("DCX %s: %d bytes, header says %d" % (fmt, len(raw), usize))
    return raw, fmt


def read_file(path):
    with open(path, "rb") as fh:
        return dcx_decompress(fh.read())[0]


# ---------------------------------------------------------------------------------------------------- helpers
def _utf16(data, off):
    end = off
    while data[end:end + 2] != b"\0\0":
        end += 2
    return data[off:end].decode("utf-16-le")


def _sjis(data, off):
    end = data.index(b"\0", off)
    return data[off:end].decode("shift_jis", errors="replace")


def _reverse_bits(b):
    return int("{:08b}".format(b)[::-1], 2)


# ----------------------------------------------------------------------------------------------------------- BND4
class BND4:
    """entries: list of (id, name, bytes)."""

    def __init__(self, data):
        if data[:4] != b"BND4":
            raise ValueError("not a BND4")
        big = data[9] == 1
        bit_big = data[0xA] == 1
        if big:
            raise NotImplementedError("big-endian BND4")
        count, = struct.unpack_from("<i", data, 0xC)
        self.version = data[0x18:0x20].rstrip(b"\0").decode("ascii", "replace")
        header_size, = struct.unpack_from("<q", data, 0x20)
        unicode_ = data[0x30] == 1
        raw = data[0x31]
        # SoulsFormats' Binder.Format bits, most significant first: BigEndian 0x80, IDs 0x40, Names1 0x20,
        # Names2 0x10, LongOffsets 0x08, Compression 0x04; the byte is stored bit-reversed unless BitBigEndian
        reverse = bit_big or ((raw & 1) != 0 and (raw & 0x80) == 0)
        fmt = raw if reverse else _reverse_bits(raw)
        has_ids, has_names = bool(fmt & 0x40), bool(fmt & 0x30)
        long_off, compressed = bool(fmt & 0x08), bool(fmt & 0x04)
        self.entries = []
        pos = 0x40
        for _ in range(count):
            p = pos
            flags = data[p]
            p += 8
            csize, = struct.unpack_from("<q", data, p)
            p += 8
            usize = csize
            if compressed:
                usize, = struct.unpack_from("<q", data, p)
                p += 8
            if long_off:
                off, = struct.unpack_from("<q", data, p)
                p += 8
            else:
                off, = struct.unpack_from("<I", data, p)
                p += 4
            fid = -1
            if has_ids:
                fid, = struct.unpack_from("<i", data, p)
                p += 4
            name = None
            if has_names:
                noff, = struct.unpack_from("<I", data, p)
                p += 4
                name = _utf16(data, noff) if unicode_ else _sjis(data, noff)
            body = data[off:off + csize]
            if is_dcx(body):
                body = dcx_decompress(body)[0]
            self.entries.append((fid, name, body, flags))
            pos += header_size

    def find(self, suffix):
        s = suffix.lower()
        return [(n, b) for _i, n, b, _f in self.entries if n and n.lower().endswith(s)]


# ------------------------------------------------------------------------------------------------------------ TPF
DDS_FORMATS = {0: "DXT1", 1: "DXT1", 5: "DXT5", 6: "B5G5R5A1", 9: "B8G8R8A8", 10: "R8G8B8", 16: "A8",
               22: "R16G16B16A16F", 23: "DXT5", 24: "BC4", 25: "BC1", 33: "DXT5", 100: "BC6H", 102: "BC7",
               103: "BC4", 104: "BC5", 105: "B8G8R8A8", 106: "BC7", 107: "BC7", 108: "DXT1", 109: "DXT1",
               110: "DXT5", 112: "BC7", 113: "BC7"}


class TPF:
    """textures: list of (name, format code, dds bytes)."""

    def __init__(self, data):
        if data[:4] != b"TPF\0":
            raise ValueError("not a TPF")
        count, = struct.unpack_from("<i", data, 8)
        platform, _flag2, encoding = data[0xC], data[0xD], data[0xE]
        if platform != 0:
            raise NotImplementedError("TPF platform %d (only PC)" % platform)
        self.textures = []
        p = 0x10
        for _ in range(count):
            off, size = struct.unpack_from("<Ii", data, p)
            fmt, _type, _mips, flags1 = data[p + 8], data[p + 9], data[p + 10], data[p + 11]
            noff, has_float = struct.unpack_from("<Ii", data, p + 12)
            p += 20
            if has_float:
                _unk, length = struct.unpack_from("<ii", data, p)
                p += 8 + length
            name = _utf16(data, noff) if encoding == 1 else _sjis(data, noff)
            body = data[off:off + size]
            if flags1 in (2, 3):
                body = dcx_decompress(body)[0]
            self.textures.append((name, fmt, body))


# --------------------------------------------------------------------------------------------------------- MATBIN
class MATBIN:
    def __init__(self, data):
        if data[:4] != b"MAB\0":
            raise ValueError("not a MATBIN")
        shader_off, source_off = struct.unpack_from("<qq", data, 8)
        self.shader = _utf16(data, shader_off)
        self.source = _utf16(data, source_off)
        _key, n_params, n_samplers = struct.unpack_from("<Iii", data, 0x18)
        p = 0x38
        self.params = {}
        for _ in range(n_params):
            noff, voff = struct.unpack_from("<qq", data, p)
            _k, typ = struct.unpack_from("<Ii", data, p + 16)
            name = _utf16(data, noff)
            # SoulsFormats MATBIN.ParamType: 0 bool, 4 int, 5 int2, 8 float, 9 float2, 10 float3, 11 float4, 12 float5
            n = {0: 1, 4: 1, 5: 2, 8: 1, 9: 2, 10: 3, 11: 4, 12: 5}.get(typ, 0)
            if typ == 0:
                val = bool(data[voff])
            elif typ in (4, 5):
                val = list(struct.unpack_from("<%di" % n, data, voff))
            else:
                val = list(struct.unpack_from("<%df" % n, data, voff))
            self.params[name] = val[0] if isinstance(val, list) and len(val) == 1 else val
            p += 0x28
        self.samplers = []
        for _ in range(n_samplers):
            toff, poff = struct.unpack_from("<qq", data, p)
            _k, u0, u1 = struct.unpack_from("<Iff", data, p + 16)
            self.samplers.append((_utf16(data, toff), _utf16(data, poff), (u0, u1)))
            p += 0x30


# ---------------------------------------------------------------------------------------------------------- FLVER
SEM = {0: "position", 1: "weights", 2: "bones", 3: "normal", 5: "uv", 6: "tangent", 7: "bitangent", 10: "color"}
TYPE_SIZE = {0x01: 8, 0x02: 12, 0x03: 16, 0x10: 4, 0x11: 4, 0x12: 4, 0x13: 4, 0x15: 4, 0x16: 8, 0x18: 8,
             0x1A: 8, 0x2E: 8, 0x2F: 4, 0xF0: 0}


class Bone:
    __slots__ = ("name", "translation", "rotation", "scale", "parent", "child", "next", "prev", "bbmin", "bbmax",
                 "unk3c")


class Material:
    __slots__ = ("name", "mtd", "textures", "flags", "gx_offset", "unk18")


class Mesh:
    __slots__ = ("dynamic", "material", "default_bone", "bone_indices", "face_sets", "buffers", "vertex_count",
                 "attrs", "faces")


class FLVER:
    def __init__(self, data):
        if data[:6] != b"FLVER\0":
            raise ValueError("not a FLVER")
        if data[6:8] != b"L\0":
            raise NotImplementedError("big-endian FLVER")
        (self.version, data_off, _data_len, n_dummy, n_mat, n_bone, n_mesh, n_vb) = struct.unpack_from("<8i", data, 8)
        self.bbmin = struct.unpack_from("<3f", data, 0x28)
        self.bbmax = struct.unpack_from("<3f", data, 0x34)
        self.index_size = data[0x48]
        self.unicode = data[0x49] == 1
        n_faceset, n_layout, n_tex = struct.unpack_from("<3i", data, 0x50)
        s = (lambda o: _utf16(data, o)) if self.unicode else (lambda o: _sjis(data, o))
        uv_factor = 2048.0 if self.version >= 0x2000F else 1024.0
        p = 0x80
        # dummies (0x40 each): position, colour, forward, parent bone, attach bone, upward ...
        self.dummies = []
        for _ in range(n_dummy):
            pos = struct.unpack_from("<3f", data, p)
            fwd = struct.unpack_from("<3f", data, p + 0x10)
            ref_id, parent = struct.unpack_from("<hh", data, p + 0x1C)
            up = struct.unpack_from("<3f", data, p + 0x20)
            attach, = struct.unpack_from("<h", data, p + 0x2C)
            self.dummies.append({"pos": pos, "forward": fwd, "up": up, "ref_id": ref_id, "parent": parent,
                                 "attach": attach})
            p += 0x40
        mats_raw = []
        for _ in range(n_mat):
            mats_raw.append(struct.unpack_from("<8i", data, p))
            p += 0x20
        self.bones = []
        for _ in range(n_bone):
            b = Bone()
            b.translation = struct.unpack_from("<3f", data, p)
            noff, = struct.unpack_from("<i", data, p + 12)
            b.rotation = struct.unpack_from("<3f", data, p + 16)
            b.parent, b.child = struct.unpack_from("<hh", data, p + 28)
            b.scale = struct.unpack_from("<3f", data, p + 32)
            b.next, b.prev = struct.unpack_from("<hh", data, p + 44)
            b.bbmin = struct.unpack_from("<3f", data, p + 48)
            b.unk3c, = struct.unpack_from("<i", data, p + 60)
            b.bbmax = struct.unpack_from("<3f", data, p + 64)
            b.name = s(noff)
            self.bones.append(b)
            p += 0x80
        meshes_raw = []
        for _ in range(n_mesh):
            meshes_raw.append(struct.unpack_from("<B3x11i", data, p))
            p += 0x30
        facesets = []
        for _ in range(n_faceset):
            flags, = struct.unpack_from("<I", data, p)
            strip, cull = data[p + 4], data[p + 5]
            count, ioff = struct.unpack_from("<ii", data, p + 8)
            isize = 0
            if self.version > 0x20005:
                isize, = struct.unpack_from("<i", data, p + 24)
                p += 32
            else:
                p += 16
            facesets.append({"flags": flags, "strip": bool(strip), "cull": bool(cull), "count": count,
                             "offset": ioff, "index_size": isize or self.index_size})
        vbufs = []
        for _ in range(n_vb):
            bi, li, vsize, vcount = struct.unpack_from("<4i", data, p)
            boff, = struct.unpack_from("<i", data, p + 28)
            vbufs.append({"buffer_index": bi, "layout": li, "size": vsize, "count": vcount, "offset": boff})
            p += 0x20
        layouts = []
        for _ in range(n_layout):
            mcount, _a, _b, moff = struct.unpack_from("<4i", data, p)
            members = []
            for k in range(mcount):
                unk00, soff, typ, sem, idx = struct.unpack_from("<iiIIi", data, moff + 0x14 * k)
                members.append({"unk00": unk00, "offset": soff, "type": typ, "semantic": sem, "index": idx})
            layouts.append(members)
            p += 0x10
        textures = []
        for _ in range(n_tex):
            poff, toff = struct.unpack_from("<ii", data, p)
            scale = struct.unpack_from("<2f", data, p + 8)
            textures.append({"path": s(poff), "type": s(toff), "scale": scale})
            p += 0x20
        self.materials = []
        for (noff, mtdoff, tcount, tidx, flags, gxoff, unk18, _z) in mats_raw:
            m = Material()
            m.name, m.mtd = s(noff), s(mtdoff)
            m.textures = textures[tidx:tidx + tcount]
            m.flags, m.gx_offset, m.unk18 = flags, gxoff, unk18
            self.materials.append(m)
        self.meshes = []
        for (dyn, mat, _z1, _z2, dbone, bcount, _bboff, boff, fscount, fsoff, vbcount, vboff) in meshes_raw:
            m = Mesh()
            m.dynamic, m.material, m.default_bone = dyn, mat, dbone
            m.bone_indices = list(struct.unpack_from("<%di" % bcount, data, boff)) if bcount else []
            m.face_sets = [facesets[i] for i in struct.unpack_from("<%di" % fscount, data, fsoff)]
            m.buffers = [vbufs[i] for i in struct.unpack_from("<%di" % vbcount, data, vboff)]
            self._read_vertices(m, data, data_off, layouts, uv_factor)
            self._read_faces(m, data, data_off)
            self.meshes.append(m)

    # ---------------------------------------------------------------------------------------------- vertices
    @staticmethod
    def _read_vertices(m, data, data_off, layouts, uv_factor):
        n = m.buffers[0]["count"]
        m.vertex_count = n
        a = {"uv": [], "color": [], "tangent": []}
        for vb in m.buffers:
            if vb["count"] != n:
                raise ValueError("vertex buffers of one mesh disagree on the vertex count")
            raw = np.frombuffer(data, dtype=np.uint8, count=n * vb["size"], offset=data_off + vb["offset"])
            raw = raw.reshape(n, vb["size"])
            for mem in layouts[vb["layout"]]:
                t, sem, o = mem["type"], SEM.get(mem["semantic"]), mem["offset"]
                size = TYPE_SIZE.get(t)
                if size is None:
                    raise NotImplementedError("vertex member type %#x" % t)
                col = np.ascontiguousarray(raw[:, o:o + size])

                def f32(k):
                    return col.view("<f4").reshape(n, k)

                def i16(k):
                    return col.view("<i2").reshape(n, k).astype(np.float32)

                def u8():
                    return col.reshape(n, 4).astype(np.float32)

                if sem == "position":
                    a["position"] = f32(3 if t == 0x02 else 4)[:, :3].copy()
                elif sem == "weights":
                    if t in (0x10, 0x13):
                        a["weights"] = u8() / 255.0
                    elif t in (0x16, 0x1A):
                        a["weights"] = i16(4) / 32767.0
                    else:
                        raise NotImplementedError("bone weights type %#x" % t)
                elif sem == "bones":
                    if t in (0x11, 0x2F, 0x10, 0x13):
                        a["bones"] = col.reshape(n, 4).astype(np.int32)
                    elif t == 0x18:
                        a["bones"] = col.view("<u2").reshape(n, 4).astype(np.int32)
                    else:
                        raise NotImplementedError("bone indices type %#x" % t)
                elif sem == "normal":
                    if t == 0x02:
                        a["normal"] = f32(3).copy()
                    elif t == 0x03:
                        a["normal"] = f32(4)[:, :3].copy()
                    elif t in (0x10, 0x11, 0x13, 0x2F):
                        a["normal"] = (u8()[:, :3] - 127.0) / 127.0
                    elif t == 0x1A:
                        a["normal"] = i16(4)[:, :3] / 32767.0
                    elif t == 0x2E:
                        a["normal"] = (col.view("<u2").reshape(n, 4)[:, :3].astype(np.float32) - 32767.0) / 32767.0
                    elif t == 0x12:
                        b = col.reshape(n, 4).view(np.int8).astype(np.float32)
                        a["normal"] = b[:, [3, 2, 1]] / 127.0
                    else:
                        raise NotImplementedError("normal type %#x" % t)
                elif sem == "uv":
                    if t == 0x01:
                        a["uv"].append(f32(2).copy())
                    elif t == 0x02:
                        a["uv"].append(f32(3)[:, :2].copy())
                    elif t == 0x03:
                        v = f32(4)
                        a["uv"] += [v[:, :2].copy(), v[:, 2:4].copy()]
                    elif t in (0x10, 0x11, 0x12, 0x13, 0x15):
                        a["uv"].append(i16(2) / uv_factor)
                    elif t == 0x16:
                        v = i16(4) / uv_factor
                        a["uv"] += [v[:, :2].copy(), v[:, 2:4].copy()]
                    elif t == 0x2E:
                        a["uv"].append(i16(4)[:, :2] / uv_factor)
                    else:
                        raise NotImplementedError("uv type %#x" % t)
                elif sem == "tangent":
                    if t == 0x03:
                        a["tangent"].append(f32(4).copy())
                    elif t in (0x10, 0x11, 0x13, 0x2F):
                        a["tangent"].append((u8() - 127.0) / 127.0)
                    elif t == 0x1A:
                        a["tangent"].append(i16(4) / 32767.0)
                elif sem == "color":
                    if t == 0x03:
                        a["color"].append(f32(4).copy())
                    elif t in (0x10, 0x13):
                        a["color"].append(u8() / 255.0)
                # bitangent: rebuilt from normal x tangent where needed
        m.attrs = a

    # ------------------------------------------------------------------------------------------------- faces
    @staticmethod
    def _read_faces(m, data, data_off):
        main = [fs for fs in m.face_sets if fs["flags"] == 0] or \
               [fs for fs in m.face_sets if not fs["flags"] & 0x03000000] or m.face_sets[:1]
        tris = []
        for fs in main[:1]:
            dt = "<u2" if fs["index_size"] == 16 else "<u4"
            idx = np.frombuffer(data, dtype=dt, count=fs["count"], offset=data_off + fs["offset"]).astype(np.int64)
            if fs["strip"]:
                out = []
                flip = False
                for k in range(len(idx) - 2):
                    a, b, c = idx[k], idx[k + 1], idx[k + 2]
                    if a == 0xFFFF or b == 0xFFFF or c == 0xFFFF:
                        flip = False
                        continue
                    if a != b and b != c and a != c:
                        out.append((a, c, b) if flip else (a, b, c))
                    flip = not flip
                tris.append(np.array(out, dtype=np.int64).reshape(-1, 3))
            else:
                tris.append(idx[:len(idx) // 3 * 3].reshape(-1, 3))
        m.faces = np.concatenate(tris) if tris else np.zeros((0, 3), dtype=np.int64)

    # ---------------------------------------------------------------------------------------------- skeleton
    def bone_matrices(self):
        """Local and model-space 4x4 matrices of every bone (game axes; column vectors, M @ p)."""
        def rot(axis, a):
            c, s_ = np.cos(a), np.sin(a)
            r = np.eye(4)
            if axis == "x":
                r[1, 1], r[1, 2], r[2, 1], r[2, 2] = c, -s_, s_, c
            elif axis == "y":
                r[0, 0], r[0, 2], r[2, 0], r[2, 2] = c, s_, -s_, c
            else:
                r[0, 0], r[0, 1], r[1, 0], r[1, 1] = c, -s_, s_, c
            return r
        local, world = [], [None] * len(self.bones)
        for b in self.bones:
            t = np.eye(4)
            t[:3, 3] = b.translation
            sc = np.diag(list(b.scale) + [1.0])
            # SoulsFormats: Scale * RotX * RotZ * RotY * Translation (row vectors) = T Ry Rz Rx S (column vectors)
            local.append(t @ rot("y", b.rotation[1]) @ rot("z", b.rotation[2]) @ rot("x", b.rotation[0]) @ sc)

        def w(i):
            if world[i] is None:
                p = self.bones[i].parent
                world[i] = local[i] if p < 0 else w(p) @ local[i]
            return world[i]
        for i in range(len(self.bones)):
            w(i)
        return local, world


# -------------------------------------------------------------------------------------------------------- main
def describe(path):
    data = read_file(path)
    if data[:4] == b"BND4":
        bnd = BND4(data)
        print("%s: BND4 %s, %d entries" % (path, bnd.version, len(bnd.entries)))
        for fid, name, body, _flags in bnd.entries:
            print("  %6d %10d  %s" % (fid, len(body), name))
        return bnd
    if data[:6] == b"FLVER\0":
        f = FLVER(data)
        print("FLVER %#x: %d bones, %d materials, %d meshes, %d dummies" % (
            f.version, len(f.bones), len(f.materials), len(f.meshes), len(f.dummies)))
        return f
    if data[:4] == b"TPF\0":
        t = TPF(data)
        for name, fmt, body in t.textures:
            print("  %-40s fmt %3d %8d bytes" % (name, fmt, len(body)))
        return t
    print(path, "unknown", data[:8])
    return None


if __name__ == "__main__":
    for a in sys.argv[1:]:
        describe(a)
