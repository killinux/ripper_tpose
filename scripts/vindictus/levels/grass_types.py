"""Decode Vindictus LandscapeGrassType packages (UE 5.3 FGrassVariety, 26 unversioned properties) without a usmap:
mesh, density per 100 m2, cull distances, scale ranges, rotation / align flags.  -> grass_types.json
  python grass_types.py <package> [...]"""
import json
import os
import struct
import sys

import zen53
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "firstdescendant"))
import iostore  # noqa: E402


def imported_packages(buf):
    off = struct.unpack_from("<7i", buf, 24)[6]
    names, _ = iostore.read_name_batch(buf, off)
    return names


class R:
    def __init__(self, d, p):
        self.d, self.p = d, p

    def i32(self):
        v, = struct.unpack_from("<i", self.d, self.p)
        self.p += 4
        return v

    def f32(self):
        v, = struct.unpack_from("<f", self.d, self.p)
        self.p += 4
        return v

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v


def per_platform(r, quality=False):
    cooked, value = r.i32(), r.f32() if not quality else r.f32()
    if quality:
        r.p += 4 * 0 + 0
        n = r.i32()
        r.p += n * 8
    return value


FIELDS = ["GrassMesh", "OverrideMaterials", "GrassDensity", "GrassDensityQuality", "bUseGrid", "PlacementJitter",
          "StartCullDistance", "StartCullDistanceQuality", "EndCullDistance", "EndCullDistanceQuality", "MinLOD",
          "Scaling", "ScaleX", "ScaleY", "ScaleZ", "RandomRotation", "AlignToSurface", "bUseLandscapeLightmap",
          "LightingChannels", "bReceivesDecals", "bAffectDistanceFieldLighting", "bCastDynamicShadow",
          "bCastContactShadow", "bKeepInstanceBufferCPUCopy", "InstanceWorldPositionOffsetDisableDistance",
          "ShadowCacheInvalidationBehavior"]


def interval(r):
    hdr, p = zen53.unversioned_header(r.d, r.p)
    r.p = p
    out = [0.0, 0.0]
    for idx, has in hdr:
        if has:
            out[idx] = r.f32()
    return out


def variety(r, imports, pkgs):
    hdr, p = zen53.unversioned_header(r.d, r.p)
    r.p = p
    v = {}
    present = {idx for idx, has in hdr if has}
    for idx in range(len(FIELDS)):
        name = FIELDS[idx]
        if idx not in present:
            continue
        if name == "GrassMesh":
            i = r.i32()
            imp = imports[-i - 1] if i < 0 else None
            v[name] = pkgs[(imp >> 32) & 0x3FFFFFFF] if imp is not None else None
        elif name == "OverrideMaterials":
            n = r.i32()
            r.p += 4 * n
        elif name in ("GrassDensity", "StartCullDistance", "EndCullDistance"):
            r.i32()
            v[name] = r.f32() if name == "GrassDensity" else r.i32()
        elif name.endswith("Quality"):
            r.i32()
            v[name] = r.f32() if name == "GrassDensityQuality" else r.i32()
            n = r.i32()
            r.p += 8 * n
        elif name in ("ScaleX", "ScaleY", "ScaleZ"):
            v[name] = interval(r)
        elif name == "LightingChannels":
            h, p = zen53.unversioned_header(r.d, r.p)
            r.p = p + sum(1 for _i, has in h if has)
        elif name in ("PlacementJitter",):
            v[name] = r.f32()
        elif name in ("MinLOD", "InstanceWorldPositionOffsetDisableDistance"):
            v[name] = r.i32()
        else:                                           # bools / 1-byte enums
            v[name] = r.u8()
    return v


out = {}
for path in sys.argv[1:]:
    buf = zen53.read_package(path)
    pkg = zen53.parse(buf)
    pkgs = imported_packages(buf)
    e = pkg["exports"][0]
    data = buf[e["data_offset"]:e["data_offset"] + e["size"]]
    hdr, p = zen53.unversioned_header(data)
    r = R(data, p)
    n = r.i32()
    vs = [variety(r, pkg["imports"], pkgs) for _ in range(n)]
    name = path.rsplit("/", 1)[-1].split(".")[0]
    out[name] = vs
    print("==", name, n, "varieties, ended at", r.p, "of", len(data))
    for v in vs:
        print("   %-70s dens %6.1f / q %6.1f  grid %s jitter %s  cull %s-%s  scale %s %s align %s" % (
            (v.get("GrassMesh") or "?")[-70:], v.get("GrassDensity", 0), v.get("GrassDensityQuality", 0),
            v.get("bUseGrid"), v.get("PlacementJitter"), v.get("StartCullDistance"), v.get("EndCullDistance"),
            v.get("ScaleX"), v.get("ScaleZ"), v.get("AlignToSurface")))
json.dump(out, open("grass_types.json", "w"), indent=1)
