# Monster Hunter World .tex (version 0x10) -> .dds (DX10 header), then texconv -> png.
#   python mhw_tex2dds.py <in dir> <out dir>
# Header (little endian u32 at): 0x00 'TEX\0', 0x04 version 0x10, 0x14 mipCount, 0x18 width, 0x1C height, 0x20 arrays(1),
# 0x24 format id, ...; mip offset table (u64 each, mipCount * arrays) starts at 0xB8; pixel data at the first offset.
# Format ids seen in MHW: 0x16 BC1_UNORM, 0x17 BC1_UNORM_SRGB, 0x18 BC2, 0x19 BC3_UNORM, 0x1A BC5_UNORM (normal maps),
# 0x1C BC6H, 0x1E BC7_UNORM, 0x1F BC7_UNORM_SRGB, 0x07 R8G8B8A8_UNORM, 0x09 R8G8B8A8_SRGB.
import glob
import os
import struct
import subprocess
import sys

DXGI = {0x16: (71, 8), 0x17: (72, 8), 0x18: (74, 16), 0x19: (77, 16), 0x1A: (83, 16), 0x1B: (84, 16), 0x1C: (95, 16),
        0x1D: (96, 16), 0x1E: (98, 16), 0x1F: (99, 16), 0x07: (28, 0), 0x09: (29, 0), 0x0A: (28, 0)}
TEXCONV = r"E:\tools\directxtex\texconv.exe"


def convert(src, dst_dds):
    b = open(src, "rb").read()
    assert b[:4] == b"TEX\x00", src
    version, = struct.unpack_from("<I", b, 4)
    mips, = struct.unpack_from("<I", b, 0x14)
    w, h, arrays, fmt = struct.unpack_from("<4I", b, 0x18)
    if fmt not in DXGI:
        raise ValueError("unknown format 0x%x in %s" % (fmt, src))
    dxgi, block = DXGI[fmt]
    # offset table: find the first plausible u64 offset after the header
    first_off = None
    for k in range(0xB8, 0x100, 8):
        v, = struct.unpack_from("<Q", b, k)
        if 0xB8 < v < len(b):
            first_off = v
            break
    if first_off is None:
        first_off = 0xC0 + 8 * mips * arrays
    data = b[first_off:]
    # DDS header
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000 | (0x20000 if mips > 1 else 0)
    if block:
        pitch = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    else:
        pitch = w * 4
        flags = (flags & ~0x80000) | 0x8
    caps = 0x1000 | (0x400008 if mips > 1 else 0)
    hdr = struct.pack("<4s7I11I", b"DDS ", 124, flags, h, w, pitch, 1, mips, *([0] * 11))
    pf = struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    hdr += pf + struct.pack("<IIIII", caps, 0, 0, 0, 0)
    dx10 = struct.pack("<IIIII", dxgi, 3, 0, max(1, arrays), 0)
    open(dst_dds, "wb").write(hdr + dx10 + data)
    return w, h, mips, fmt, dxgi, first_off


src_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
dds_dir = os.path.join(out_dir, "_dds")
os.makedirs(dds_dir, exist_ok=True)
ok = 0
for f in sorted(glob.glob(os.path.join(src_dir, "*.tex"))):
    name = os.path.splitext(os.path.basename(f))[0]
    dds = os.path.join(dds_dir, name + ".dds")
    try:
        info = convert(f, dds)
    except Exception as e:
        print("SKIP", name, e)
        continue
    r = subprocess.run([TEXCONV, "-ft", "png", "-y", "-o", out_dir, "-nologo", dds], capture_output=True, text=True)
    png = os.path.join(out_dir, name + ".png")
    good = os.path.isfile(png)
    ok += good
    print("%-28s %4dx%-4d mips %2d fmt 0x%02x dxgi %3d off 0x%x %s" % (name, info[0], info[1], info[2], info[3], info[4], info[5], "ok" if good else "FAILED " + r.stdout[-200:].replace("\n", " ")))
print("converted", ok)
