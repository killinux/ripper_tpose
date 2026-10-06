"""Minimal UE 5.3 zen package reader for the Vindictus level cells: summary (52 bytes), name map, export map
(72-byte entries), export bundle entries -> each export's serialized bytes; plus the unversioned property header.
  python zen53.py <package path in the container> [export name regex]"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "firstdescendant"))
import iostore  # noqa: E402

PAKS = r"E:\tools\vindictus\Vindictus\Content\Paks"
KEYFILE = r"E:\tools\vindictus\_download\aes_key.txt"
OODLE = r"E:\tools\cue4parse_cli\oodle-data-shared.dll"
_toc = None


def key():
    k = open(KEYFILE, encoding="utf-8").read().strip()
    return bytes.fromhex(k[2:] if k.lower().startswith("0x") else k)


def read_package(path):
    global _toc
    if _toc is None:
        _toc = (iostore.Toc(os.path.join(PAKS, "Vindictus-Windows.utoc"), key()), iostore.Oodle(OODLE))
    toc, oodle = _toc
    return toc.read_chunk(toc.paths()[path], oodle)


def parse(buf):
    has_ver, hdr_size = struct.unpack_from("<II", buf, 0)
    name_idx, _num = struct.unpack_from("<II", buf, 8)
    pkg_flags, cooked_hdr = struct.unpack_from("<II", buf, 16)
    (pub_hash_off, import_off, export_off, bundle_off, dep_hdr_off, dep_ent_off, imp_pkg_names_off) = \
        struct.unpack_from("<7i", buf, 24)
    pos = 52
    if has_ver:
        pos += 16
        ncv, = struct.unpack_from("<i", buf, pos)
        pos += 4 + 20 * ncv
    names, pos = iostore.read_name_batch(buf, pos)
    n_exports = (bundle_off - export_off) // 72
    exports = []
    for i in range(n_exports):
        o = export_off + 72 * i
        cso, css = struct.unpack_from("<QQ", buf, o)
        on_idx, on_num = struct.unpack_from("<II", buf, o + 16)
        outer, cls, sup, tmpl, pub = struct.unpack_from("<5Q", buf, o + 24)
        flags, = struct.unpack_from("<I", buf, o + 64)
        name = names[on_idx & 0x3FFFFFFF] if (on_idx & 0x3FFFFFFF) < len(names) else "?"
        if on_num:
            name += "_%d" % (on_num - 1)
        exports.append({"index": i, "name": name, "cooked_offset": cso, "size": css, "outer": outer, "class": cls,
                        "template": tmpl, "flags": flags})
    # export bundle entries: (LocalExportIndex, CommandType 0 create / 1 serialize), data laid out in that order
    entries = []
    o = bundle_off
    while o + 8 <= dep_hdr_off:
        idx, cmd = struct.unpack_from("<II", buf, o)
        entries.append((idx, cmd))
        o += 8
    # the serialized exports follow the header in CookedSerialOffset order (= export index order here),
    # not in export bundle order (checked on a North Ruin cell: bundle order put two components 18 bytes off)
    pos = hdr_size
    for e in sorted(exports, key=lambda e: e["cooked_offset"]):
        e["data_offset"] = pos
        pos += e["size"]
    imports = [struct.unpack_from("<Q", buf, import_off + 8 * i)[0] for i in range((export_off - import_off) // 8)]
    return {"names": names, "exports": exports, "imports": imports, "header_size": hdr_size, "end": pos,
            "length": len(buf), "flags": pkg_flags}


def unversioned_header(data, pos=0):
    """[(schema index, has value / zero)] from FUnversionedHeader at data[pos:]; returns (entries, value start)."""
    frags = []
    while True:
        f, = struct.unpack_from("<H", data, pos)
        pos += 2
        skip, zeroes, last, num = f & 0x7F, bool(f & 0x80), bool(f & 0x100), f >> 9
        frags.append((skip, zeroes, num))
        if last:
            break
    zero_bits = sum(num for skip, zeroes, num in frags if zeroes)
    mask = []
    if zero_bits:
        nbytes = 1 if zero_bits <= 8 else 2 if zero_bits <= 16 else 4 * ((zero_bits + 31) // 32)
        raw = int.from_bytes(data[pos:pos + nbytes], "little")
        pos += nbytes
        mask = [(raw >> i) & 1 for i in range(zero_bits)]
    out, index, bit = [], 0, 0
    for skip, zeroes, num in frags:
        index += skip
        for _ in range(num):
            is_zero = False
            if zeroes:
                is_zero = bool(mask[bit])
                bit += 1
            out.append((index, not is_zero))
            index += 1
    return out, pos


if __name__ == "__main__":
    pkg = parse(read_package(sys.argv[1]))
    print("header %d, data end %d, package length %d, flags 0x%x, %d exports" % (
        pkg["header_size"], pkg["end"], pkg["length"], pkg["flags"], len(pkg["exports"])))
    pat = re.compile(sys.argv[2] if len(sys.argv) > 2 else ".")
    buf = read_package(sys.argv[1])
    for e in pkg["exports"]:
        if not pat.search(e["name"]) or "data_offset" not in e:
            continue
        data = buf[e["data_offset"]:e["data_offset"] + e["size"]]
        hdr, vpos = unversioned_header(data)
        print("== %d %s size %d class %016x  props %s  values from %d" % (
            e["index"], e["name"], e["size"], e["class"], hdr, vpos))
        print("   ", data.hex(" "))
