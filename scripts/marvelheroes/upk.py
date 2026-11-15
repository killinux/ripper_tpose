"""Reader for an uncompressed UE3 package as Marvel Heroes Omega writes it (file version 868, licensee 3):
summary, name / import / export tables and tagged properties.

UE Viewer has no Marvel Heroes support and stops on these packages (see README.md), so the mesh, material and
texture readers next to this file parse the objects themselves.  The tables and the property tags are plain UE3.

    python -I upk.py <file.upk>                      list every export (index, class, path, offset, size)
    python -I upk.py <file.upk> imports              list the imports
    python -I upk.py <file.upk> props <index|name>   tagged properties of one export
    python -I upk.py <file.upk> hex <index|name> [n] first n bytes of one export
"""
import struct
import sys

PKG_STORE_COMPRESSED = 0x02000000
TAG = 0x9E2A83C1
# property type names are stored lower-case in these packages ("structproperty"); compare case-insensitively
CANON = {k.lower(): k for k in ("IntProperty", "FloatProperty", "ObjectProperty", "ComponentProperty", "ClassProperty",
                                  "NameProperty", "StrProperty", "BoolProperty", "ByteProperty", "StructProperty",
                                  "ArrayProperty", "InterfaceProperty", "DelegateProperty")}


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def _take(self, fmt, size):
        v = struct.unpack_from(fmt, self.d, self.p)[0]
        self.p += size
        return v

    def i32(self):
        return self._take("<i", 4)

    def u32(self):
        return self._take("<I", 4)

    def u64(self):
        return self._take("<Q", 8)

    def f32(self):
        return self._take("<f", 4)

    def u16(self):
        return self._take("<H", 2)

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def raw(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            return self.raw(n)[:-1].decode("latin-1")
        return self.raw(-n * 2)[:-2].decode("utf-16-le")


class Package:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        r = Reader(self.data)
        if r.u32() != TAG:
            raise ValueError("not an Unreal package (bad tag): %s" % path)
        self.ver = r.u16()
        self.lic = r.u16()
        self.header_size = r.i32()
        self.folder = r.fstring()
        self.flags = r.u32()
        self.name_count, self.name_off = r.i32(), r.i32()
        self.export_count, self.export_off = r.i32(), r.i32()
        self.import_count, self.import_off = r.i32(), r.i32()
        self.depends_off = r.i32()
        self.engine_ver = self.cooker_ver = None
        self.compression = 0
        compressed_chunks = 0
        if self.ver >= 623:
            r.i32(), r.i32(), r.i32()  # ImportExportGuidsOffset, ImportGuidsCount, ExportGuidsCount
            r.i32()                    # ThumbnailTableOffset
            r.raw(16)                  # package GUID
            gens = r.i32()
            r.raw(12 * max(gens, 0))   # generations: export count, name count, net object count
            self.engine_ver = r.i32()
            self.cooker_ver = r.i32()
            self.compression = r.i32()
            compressed_chunks = r.i32()
        if (self.flags & PKG_STORE_COMPRESSED) or compressed_chunks > 0:
            raise ValueError("compressed package (flags %08X, %d chunks) - decompress it first; mod packages are "
                             "usually stored uncompressed" % (self.flags, compressed_chunks))
        r.p = self.name_off
        self.names = []
        for _ in range(self.name_count):
            self.names.append(r.fstring())
            r.u64()  # name flags
        r.p = self.import_off
        self.imports = []
        for _ in range(self.import_count):
            cpkg = self.fname(r)
            cname = self.fname(r)
            outer = r.i32()
            oname = self.fname(r)
            self.imports.append({"class_pkg": cpkg, "class": cname, "outer": outer, "name": oname})
        r.p = self.export_off
        self.exports = []
        for _ in range(self.export_count):
            e = {"class_idx": r.i32(), "super_idx": r.i32(), "outer": r.i32()}
            e["name"] = self.fname(r)
            e["archetype"] = r.i32()
            e["flags"] = r.u64()
            e["size"] = r.i32()
            e["offset"] = r.i32()
            e["export_flags"] = r.u32()
            n = r.i32()
            r.raw(4 * n)       # generation net object counts
            r.raw(16)          # package GUID
            e["pkg_flags"] = r.u32()
            self.exports.append(e)
        for e in self.exports:
            e["class"] = self.obj_name(e["class_idx"]) if e["class_idx"] else "Class"

    # ---- names and object references --------------------------------------------------------------------
    def fname(self, r):
        i = r.i32()
        n = r.i32()
        s = self.names[i] if 0 <= i < len(self.names) else "<bad name %d>" % i
        return s if n == 0 else "%s_%d" % (s, n - 1)

    def obj_name(self, idx):
        if idx > 0:
            return self.exports[idx - 1]["name"]
        if idx < 0:
            return self.imports[-idx - 1]["name"]
        return "None"

    def obj_path(self, idx):
        parts = []
        while idx:
            if idx > 0:
                e = self.exports[idx - 1]
                parts.append(e["name"])
                idx = e["outer"]
            else:
                im = self.imports[-idx - 1]
                parts.append(im["name"])
                idx = im["outer"]
        return ".".join(reversed(parts))

    def find(self, name, cls=None):
        """0-based export index of the export called `name` (optionally of class `cls`), case-insensitive."""
        for i, e in enumerate(self.exports):
            if e["name"].lower() == name.lower() and (cls is None or e["class"].lower() == cls.lower()):
                return i
        raise KeyError(name)

    def of_class(self, cls):
        return [i for i, e in enumerate(self.exports) if e["class"].lower() == cls.lower()]

    # ---- tagged properties -------------------------------------------------------------------------------
    def read_props(self, r, end):
        """Property tags until 'None' -> list of (name, type, size, array index, extra, value).

        extra = struct name / enum name / bool value.  Arrays come back as ("array", count, data offset, data size)."""
        out = []
        while r.p < end:
            name = self.fname(r)
            if name.lower() == "none":
                break
            ptype = self.fname(r)
            ptype = CANON.get(ptype.lower(), ptype)
            size = r.i32()
            index = r.i32()
            extra = None
            if ptype == "StructProperty":
                extra = self.fname(r)
            elif ptype == "BoolProperty":
                extra = r.u8() if self.ver >= 673 else r.i32()
            elif ptype == "ByteProperty" and self.ver >= 633:
                extra = self.fname(r)
            start = r.p
            val = self.prop_value(r, ptype, size, extra)
            r.p = start + size
            out.append((name, ptype, size, index, extra, val))
        return out

    def object_props(self, idx):
        """(properties, offset right after them) of export `idx`.  Every object starts with its NetIndex."""
        e = self.exports[idx]
        r = Reader(self.data, e["offset"])
        r.i32()
        props = self.read_props(r, e["offset"] + e["size"])
        return props, r.p

    def prop_value(self, r, ptype, size, extra):
        if ptype == "IntProperty":
            return r.i32()
        if ptype == "FloatProperty":
            return r.f32()
        if ptype in ("ObjectProperty", "ComponentProperty", "ClassProperty"):
            i = r.i32()
            return (i, self.obj_path(i))
        if ptype == "NameProperty":
            return self.fname(r)
        if ptype == "StrProperty":
            return r.fstring()
        if ptype == "BoolProperty":
            return extra
        if ptype == "ByteProperty":
            if extra and extra.lower() != "none":
                return self.fname(r)
            return r.u8()
        if ptype == "StructProperty":
            ex = (extra or "").lower()
            fixed = {"vector": "<3f", "linearcolor": "<4f", "rotator": "<3i", "vector2d": "<2f"}
            if ex in fixed:
                return struct.unpack_from(fixed[ex], self.data, r.p)
            if ex == "color":
                return tuple(self.data[r.p:r.p + 4])
            if ex == "guid":
                return self.data[r.p:r.p + 16].hex()
            try:  # other structs are tagged property lists themselves
                return self.read_props(Reader(self.data, r.p), r.p + size)
            except Exception as err:  # noqa: BLE001 - unknown native struct: keep the raw size
                return "<struct %s %d bytes: %s>" % (extra, size, err)
        if ptype == "ArrayProperty":
            n = r.i32()
            return ("array", n, r.p, size - 4)
        return "<%s %d bytes>" % (ptype, size)

    def struct_array(self, value):
        """Elements of an ArrayProperty whose elements are tagged structs -> list of {name: value}."""
        _, n, start, size = value
        r = Reader(self.data, start)
        items = []
        for _ in range(n):
            items.append({p[0]: p[5] for p in self.read_props(r, start + size)})
        return items


def dump_props(props, ind=""):
    for name, ptype, size, index, extra, val in props:
        tag = "%s%s[%d] %s%s (%d)" % (ind, name, index, ptype, ("<%s>" % extra) if extra is not None else "", size)
        if isinstance(val, list):
            print(tag)
            dump_props(val, ind + "    ")
        else:
            print(tag, "=", val)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    pkg = Package(sys.argv[1])
    cmd = sys.argv[2] if len(sys.argv) > 2 else "list"
    print("ver %d/%d engine %s flags %08X names %d exports %d imports %d" % (
        pkg.ver, pkg.lic, pkg.engine_ver, pkg.flags, pkg.name_count, pkg.export_count, pkg.import_count))
    if cmd == "list":
        for i, e in enumerate(pkg.exports):
            print("%5d %-28s %-60s off %08X size %08X" % (i, e["class"], pkg.obj_path(i + 1), e["offset"], e["size"]))
    elif cmd == "imports":
        for i, im in enumerate(pkg.imports):
            print("%5d %-20s %s" % (-i - 1, im["class"], pkg.obj_path(-i - 1)))
    elif cmd in ("props", "hex"):
        key = sys.argv[3]
        idx = int(key) if key.isdigit() else pkg.find(key)
        e = pkg.exports[idx]
        print("export", idx, e["class"], pkg.obj_path(idx + 1), "off %X size %X" % (e["offset"], e["size"]))
        if cmd == "hex":
            n = int(sys.argv[4]) if len(sys.argv) > 4 else 256
            blob = pkg.data[e["offset"]:e["offset"] + n]
            for k in range(0, len(blob), 16):
                print("%06X  %s" % (k, blob[k:k + 16].hex(" ")))
            return
        props, end = pkg.object_props(idx)
        dump_props(props)
        print("props end at +%X of %X" % (end - e["offset"], e["size"]))


if __name__ == "__main__":
    main()
