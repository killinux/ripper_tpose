"""Texture2D export for Marvel Heroes Omega packages: writes the largest mip stored inside the package as .dds and
converts it to .png with texconv.

The game itself keeps the big mips of its own textures in .tfc texture caches (TextureFileCacheName, e.g.
"chartextures"); a package then only carries the small mip tail.  Mods that bring their own textures (like the
Gwenom costume) store the full-size top mip inline, which is all that is needed here.  `--min-size` skips the
mip-tail leftovers of the game's own textures.

    python -I textures.py <file.upk> <out dir> [--texconv texconv.exe] [--min-size 128] [--only name,name]
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Package, Reader  # noqa: E402

TEXCONV = r"E:\tools\directxtex\texconv.exe"
FOURCC = {"pf_dxt1": b"DXT1", "pf_dxt3": b"DXT3", "pf_dxt5": b"DXT5", "pf_bc5": b"ATI2"}
# uncompressed formats: (bits per pixel, R, G, B, A masks, pixel-format flags)
RGB_FORMATS = {"pf_a8r8g8b8": (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x41),
               "pf_g8": (8, 0xFF, 0, 0, 0, 0x20000)}
BULK_UNUSED, BULK_SEPARATE = 0x20, 0x1


def dds_bytes(w, h, fmt, data):
    if fmt in FOURCC:
        pf = struct.pack("<II4sIIIII", 32, 0x4, FOURCC[fmt], 0, 0, 0, 0, 0)
        flags, pitch = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, len(data)
    else:
        bpp, rm, gm, bm, am, pff = RGB_FORMATS[fmt]
        pf = struct.pack("<II4sIIIII", 32, pff, b"\0\0\0\0", bpp, rm, gm, bm, am)
        flags, pitch = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8, w * bpp // 8
    hdr = struct.pack("<IIIIIII", 124, flags, h, w, pitch, 0, 1) + b"\0" * 44 + pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    return b"DDS " + hdr + data


def read_texture(pkg, idx):
    """-> dict(name, format, srgb, width, height, data or None, props)."""
    e = pkg.exports[idx]
    props, pos = pkg.object_props(idx)
    pv = {p[0].lower(): p[5] for p in props}
    fmt = str(pv.get("format", "")).lower()
    r = Reader(pkg.data, pos)
    r.p += 16  # SourceArt (empty bulk data in cooked packages)
    best = None
    nmips = r.i32()
    for _ in range(max(nmips, 0)):
        flags = r.i32()   # FByteBulkData: flags, element count, size on disk, offset in file
        r.i32()
        size = r.i32()
        r.i32()
        inline = not (flags & (BULK_SEPARATE | BULK_UNUSED)) and size > 0
        at = r.p
        if inline:
            r.p += size
        sx, sy = r.i32(), r.i32()
        if inline and best is None:
            best = (sx, sy, at, size)
    out = {"name": e["name"], "path": pkg.obj_path(idx + 1), "format": fmt, "srgb": bool(pv.get("srgb", 1)),
           "cache": pv.get("texturefilecachename"), "width": int(pv.get("sizex", 0)), "height": int(pv.get("sizey", 0)),
           "data": None}
    if best:
        out["mip_width"], out["mip_height"] = best[0], best[1]
        out["data"] = pkg.data[best[2]:best[2] + best[3]]
    return out


def export_textures(pkg, out_dir, texconv=TEXCONV, min_size=128, only=None, log=print):
    """Writes <name>.dds + <name>.png for every texture with an inline mip >= min_size.  -> {texture path: png}."""
    os.makedirs(out_dir, exist_ok=True)
    done = {}
    for idx in pkg.of_class("texture2d"):
        t = read_texture(pkg, idx)
        if only and t["name"].lower() not in only:
            continue
        if t["data"] is None:
            log("  no inline mip (in the game's %s cache): %s" % (t["cache"], t["path"]))
            continue
        if max(t["mip_width"], t["mip_height"]) < min_size and not only:
            continue
        if t["format"] not in FOURCC and t["format"] not in RGB_FORMATS:
            log("  format %s not handled: %s" % (t["format"], t["path"]))
            continue
        stem = t["name"].replace(" ", "_")
        dds = os.path.join(out_dir, stem + ".dds")
        with open(dds, "wb") as f:
            f.write(dds_bytes(t["mip_width"], t["mip_height"], t["format"], t["data"]))
        png = os.path.join(out_dir, stem + ".png")
        if texconv and os.path.isfile(texconv):
            subprocess.run([texconv, "-nologo", "-y", "-ft", "png", "-o", out_dir, dds], check=True,
                           stdout=subprocess.DEVNULL)
        done[t["path"]] = png
        log("  %-40s %4dx%-4d %s%s" % (stem, t["mip_width"], t["mip_height"], t["format"], "" if t["srgb"] else " linear"))
    return done


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    pkg = Package(args[0])
    texconv = args[args.index("--texconv") + 1] if "--texconv" in args else TEXCONV
    min_size = int(args[args.index("--min-size") + 1]) if "--min-size" in args else 128
    only = set(args[args.index("--only") + 1].lower().split(",")) if "--only" in args else None
    export_textures(pkg, args[1], texconv, min_size, only)


if __name__ == "__main__":
    main()
