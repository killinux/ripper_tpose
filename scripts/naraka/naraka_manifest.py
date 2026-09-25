"""StreamingAssets/AppRes.info -> which bundle file holds which asset path.

AppRes.info is a zip with one member, "data", a .NET BinaryWriter stream:

    header: i32 1, strings (branch, build date, version, platform, ...)
    per bundle:
        u24     size >> 8 (bundle file size in 256-byte units)
        string  bundle path relative to StreamingAssets ("0/0/0001f46d2a9dbc1f",
                "c/o/common_character_res", "dlc/32e342eacb85413d", ...)
        i32 -1, i32 7
        u16     asset count, then that many strings ("assets/res/...prefab")
        u8, u16, u32 crc, string md5, string md5, u8
    then an index-based dependency table (not needed: every bundle's own
    AssetBundle object lists its dependencies by path).

Strings are 7-bit-length-prefixed UTF-8.  Rather than trust the header, the
parser finds the first entry and then walks entries back to back.
"""
import os
import re
import zipfile

ENTRY_TAIL = 74


def _string(d, p):
    n = shift = 0
    while True:
        b = d[p]
        p += 1
        n |= (b & 127) << shift
        shift += 7
        if b < 128:
            break
    return d[p:p + n].decode("utf-8", "replace"), p + n


def read(streaming_assets):
    """{bundle_path: [asset paths]} in manifest order."""
    data = zipfile.ZipFile(os.path.join(streaming_assets, "AppRes.info")).read("data")
    # the first entry: u24 size, len, "x/y/<16 hex>", -1, 7
    first = re.search(rb"[\x00-\xff]{3}[\x05-\x7f][0-9a-z_/]{4,120}\xff\xff\xff\xff\x07\x00\x00\x00", data)
    p = first.start() + 3
    out = {}
    while p < len(data):
        start = p
        try:
            name, p = _string(data, p)
            if data[p:p + 8] != b"\xff\xff\xff\xff\x07\x00\x00\x00" or "/" not in name:
                raise ValueError
        except (ValueError, IndexError):
            p = start
            break
        p += 8
        count = int.from_bytes(data[p:p + 2], "little")
        p += 2
        assets = []
        for _ in range(count):
            s, p = _string(data, p)
            assets.append(s)
        out[name] = assets
        p += ENTRY_TAIL + 3           # tail, then the next entry's u24 size
    return out


if __name__ == "__main__":
    import sys
    sa = sys.argv[1] if len(sys.argv) > 1 else r"E:\SteamLibrary\steamapps\common\NARAKA BLADEPOINT\NarakaBladepoint_Data\StreamingAssets"
    m = read(sa)
    print(len(m), "bundles,", sum(len(v) for v in m.values()), "assets")
    missing = [b for b in m if not os.path.isfile(os.path.join(sa, b))]
    print("missing on disk:", len(missing), missing[:5])
