"""Reader / writer for .usmap type mappings (version 0, uncompressed - the TFD file), enough to inspect a class's
unversioned schema (derived class properties first, then the super class's, shifted) and to write a patched copy.
  python usmap.py <file.usmap> <Class> [<Class> ...]   -> the full schema index list of each class"""
import struct
import sys

TYPES = ["Byte", "Bool", "Int", "Float", "Object", "Name", "Delegate", "Double", "Array", "Struct", "Str", "Text",
         "Interface", "MulticastDelegate", "WeakObject", "LazyObject", "AssetObject", "SoftObject", "UInt64",
         "UInt32", "UInt16", "Int64", "Int16", "Int8", "Map", "Set", "Enum", "FieldPath", "Optional", "Utf8Str",
         "AnsiStr"]


class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v, = struct.unpack_from("<H", self.d, self.p)
        self.p += 2
        return v

    def u32(self):
        v, = struct.unpack_from("<I", self.d, self.p)
        self.p += 4
        return v


def read_type(r):
    t = r.u8()
    if TYPES[t] == "Enum":
        return {"type": "Enum", "inner": read_type(r), "enum": r.u32()}
    if TYPES[t] == "Struct":
        return {"type": "Struct", "struct": r.u32()}
    if TYPES[t] in ("Array", "Set", "Optional"):
        return {"type": TYPES[t], "inner": read_type(r)}
    if TYPES[t] == "Map":
        return {"type": "Map", "key": read_type(r), "value": read_type(r)}
    return {"type": TYPES[t]}


def write_type(out, t):
    out.append(struct.pack("<B", TYPES.index(t["type"])))
    if t["type"] == "Enum":
        write_type(out, t["inner"])
        out.append(struct.pack("<I", t["enum"]))
    elif t["type"] == "Struct":
        out.append(struct.pack("<I", t["struct"]))
    elif t["type"] in ("Array", "Set", "Optional"):
        write_type(out, t["inner"])
    elif t["type"] == "Map":
        write_type(out, t["key"])
        write_type(out, t["value"])


def load(path):
    data = open(path, "rb").read()
    magic, ver, comp, csize, usize = struct.unpack_from("<HBBII", data, 0)
    assert magic == 0x30C4 and ver == 0 and comp == 0, (hex(magic), ver, comp)
    r = Reader(data[12:12 + usize])
    names = []
    for _ in range(r.u32()):
        n = r.u8()
        names.append(r.d[r.p:r.p + n].decode("utf-8", "replace"))
        r.p += n
    enums = []
    for _ in range(r.u32()):
        name = r.u32()
        enums.append((name, [r.u32() for _ in range(r.u8())]))
    structs = {}
    order = []
    for _ in range(r.u32()):
        name, sup = r.u32(), r.u32()
        count, serial = r.u16(), r.u16()
        props = []
        for _ in range(serial):
            props.append({"index": r.u16(), "dim": r.u8(), "name": r.u32(), "type": read_type(r)})
        structs[names[name]] = {"name": name, "super": None if sup == 0xFFFFFFFF else names[sup], "count": count,
                                "props": props}
        order.append(names[name])
    assert r.p == len(r.d), (r.p, len(r.d))
    return {"names": names, "enums": enums, "structs": structs, "order": order}


def save(m, path):
    out = []
    names = m["names"]
    out.append(struct.pack("<I", len(names)))
    for n in names:
        b = n.encode("utf-8")
        out.append(struct.pack("<B", len(b)) + b)
    out.append(struct.pack("<I", len(m["enums"])))
    for name, entries in m["enums"]:
        out.append(struct.pack("<IB", name, len(entries)))
        out.extend(struct.pack("<I", e) for e in entries)
    out.append(struct.pack("<I", len(m["order"])))
    for key in m["order"]:
        s = m["structs"][key]
        sup = 0xFFFFFFFF if s["super"] is None else names.index(s["super"])
        out.append(struct.pack("<IIHH", s["name"], sup, s["count"], len(s["props"])))
        for p in s["props"]:
            out.append(struct.pack("<HBI", p["index"], p["dim"], p["name"]))
            write_type(out, p["type"])
    payload = b"".join(out)
    open(path, "wb").write(struct.pack("<HBBII", 0x30C4, 0, 0, len(payload), len(payload)) + payload)


def type_str(m, t):
    if t["type"] == "Struct":
        return "Struct<%s>" % m["names"][t["struct"]]
    if t["type"] == "Enum":
        return "Enum<%s>" % m["names"][t["enum"]]
    if t["type"] in ("Array", "Set", "Optional"):
        return "%s<%s>" % (t["type"], type_str(m, t["inner"]))
    if t["type"] == "Map":
        return "Map<%s,%s>" % (type_str(m, t["key"]), type_str(m, t["value"]))
    return t["type"]


def schema(m, cls):
    """[(full schema index, class, property name, type)] - derived first, each super shifted by the counts before."""
    out, base = [], 0
    while cls is not None:
        s = m["structs"][cls]
        for p in s["props"]:
            for k in range(p["dim"]):
                out.append((base + p["index"] + k, cls, m["names"][p["name"]], type_str(m, p["type"])))
        base += s["count"]
        cls = s["super"]
    return out


if __name__ == "__main__":
    m = load(sys.argv[1])
    for cls in sys.argv[2:]:
        print("==", cls, "chain:", end=" ")
        c = cls
        while c:
            print("%s(%d)" % (c, m["structs"][c]["count"]), end=" ")
            c = m["structs"][c]["super"]
        print()
        for row in schema(m, cls):
            print("  %4d %-24s %-40s %s" % row)
