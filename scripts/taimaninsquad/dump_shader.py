"""Look inside the game's compiled shaders: properties, passes, keyword variants, and the D3D11
programs disassembled to text.  This is how the toon shader was rebuilt in Blender (README,
"着色器还原") - the game ships no shader source, only DXBC bytecode.

    python dump_shader.py                              # every shader in the shader bundles
    python dump_shader.py Squad/SquadToon              # properties, passes, variant counts
    python dump_shader.py Squad/SquadToon --asm        # + disassemble the ForwardLit / Outline programs
    python dump_shader.py Squad/SquadToon --asm --pass ForwardLit --keywords _MATCAP _EMISSION

--asm writes <export-root>/_work/shader/<shader>/<pass>_<vert|frag>_<blob>.asm, one file per distinct
program, each starting with the keyword set it is compiled for, plus <pass>_<stage>_index.txt.

How to read a fragment program: ``cb3`` is the material (UnityPerMaterial, in the order of the
shader's property block), ``cb0[6]`` the main light direction, ``cb0[7]`` its colour,
``cb0[64..66]`` the view matrix, ``cb2[25..31]`` the SH ambient.  Textures t0.. are bound in the
order the program samples them; match them by what is done with the sample.

Windows only: the disassembler is D3DDisassemble from d3dcompiler_47.dll (ships with Windows).
"""
from __future__ import annotations

import argparse
import ctypes
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402

SHADER_BUNDLES = ("squadtoonshader_assets_all_", "shader_assets_all_")


def disassemble(code: bytes) -> str:
    d3d = ctypes.WinDLL("d3dcompiler_47.dll")
    blob = ctypes.c_void_p()
    hr = d3d.D3DDisassemble(ctypes.c_char_p(code), ctypes.c_size_t(len(code)), ctypes.c_uint(0), None,
                            ctypes.byref(blob))
    if hr != 0 or not blob:
        return "; D3DDisassemble failed, hr=%08x" % (hr & 0xFFFFFFFF)
    vtbl = ctypes.cast(ctypes.cast(blob, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    get_ptr = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(vtbl[3])
    get_size = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(vtbl[4])
    text = ctypes.string_at(get_ptr(blob), get_size(blob)).decode("ascii", "replace")
    release(blob)
    return text.rstrip("\0")


def shaders():
    """(bundle file, object reader, parsed form) of every Shader in the shader bundles."""
    import UnityPy

    for name in sorted(os.listdir(tc.BUNDLE_DIR)):
        if not name.startswith(SHADER_BUNDLES):
            continue
        env = UnityPy.load(os.path.join(tc.BUNDLE_DIR, name))
        for obj in env.objects:
            if obj.type.name == "Shader":
                data = obj.read()
                yield name, data, data.m_ParsedForm


def programs(shader):
    """Decompress the D3D11 blob; returns a function blob index -> DXBC bytes (or None)."""
    import lz4.block

    data = b""
    for off, clen, dlen in zip(shader.offsets[0], shader.compressedLengths[0], shader.decompressedLengths[0]):
        data += lz4.block.decompress(bytes(shader.compressedBlob[off:off + clen]), uncompressed_size=dlen)
    count = struct.unpack_from("<i", data, 0)[0]
    entries = [struct.unpack_from("<iii", data, 4 + i * 12) for i in range(count)]

    def program(index):
        off, length, _segment = entries[index]
        chunk = data[off:off + length]
        k = chunk.find(b"DXBC")
        if k < 0:
            return None
        return chunk[k:k + struct.unpack_from("<I", chunk, k + 24)[0]]

    return program


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shader", nargs="?", help="shader name, e.g. Squad/SquadToon (omit to list them all)")
    ap.add_argument("--asm", action="store_true", help="write the disassembled programs")
    ap.add_argument("--pass", dest="passes", action="append", help="pass name (default ForwardLit and Outline)")
    ap.add_argument("--keywords", nargs="*", default=None, help="only variants whose keyword set contains all of these")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    tc.check_game()

    if not a.shader:
        for bundle, _data, parsed in shaders():
            print("%-70s %s" % (parsed.m_Name, bundle.split("_assets_")[0]))
        return 0
    found = next(((d, p) for _b, d, p in shaders() if p.m_Name == a.shader), None)
    if found is None:
        raise SystemExit("no shader named %r (run without arguments to list them)" % a.shader)
    shader, parsed = found
    print("shader %s" % parsed.m_Name)
    print("\nproperties (type 0 colour, 1 vector, 2 float, 3 range, 4 texture):")
    for prop in parsed.m_PropInfo.m_Props:
        print("  %-28s %-34s type %d  default (%.3g, %.3g, %.3g, %.3g) %s" % (
            prop.m_Name, prop.m_Description, prop.m_Type, prop.m_DefValue_0_, prop.m_DefValue_1_,
            prop.m_DefValue_2_, prop.m_DefValue_3_, prop.m_DefTexture.m_DefaultName))
    keyword_names = list(getattr(parsed, "m_KeywordNames", []) or [])
    wanted = a.passes or ["ForwardLit", "Outline"]
    program = programs(shader) if a.asm else None
    out_dir = os.path.join(tc.work_dir(a.export_root), "shader", re.sub(r"[^0-9A-Za-z._-]+", "_", parsed.m_Name))
    print("\npasses:")
    for si, sub in enumerate(parsed.m_SubShaders):
        for ps in sub.m_Passes:
            name = ps.m_State.m_Name
            for stage, prog in (("vert", ps.progVertex), ("frag", ps.progFragment)):
                variants = []
                for tier in (getattr(prog, "m_PlayerSubPrograms", None) or []):
                    variants.extend(tier)
                print("  subshader %d  %-16s %s  %d variants" % (si, name, stage, len(variants)))
                if not a.asm or si != 0 or name not in wanted:
                    continue
                os.makedirs(out_dir, exist_ok=True)
                by_blob = {}
                for v in variants:
                    kws = sorted(keyword_names[k] if k < len(keyword_names) else "#%d" % k
                                 for k in (getattr(v, "m_KeywordIndices", None) or []))
                    by_blob.setdefault(v.m_BlobIndex, kws)
                written = 0
                with open(os.path.join(out_dir, "%s_%s_index.txt" % (name, stage)), "w", encoding="utf-8",
                          newline="\n") as index:
                    for blob, kws in sorted(by_blob.items()):
                        index.write("%d\t%s\n" % (blob, " ".join(kws)))
                        if a.keywords is not None and not set(a.keywords) <= set(kws):
                            continue
                        code = program(blob)
                        if code is None:
                            continue
                        with open(os.path.join(out_dir, "%s_%s_%05d.asm" % (name, stage, blob)), "w",
                                  encoding="utf-8", newline="\n") as fh:
                            fh.write("; keywords: %s\n%s\n" % (" ".join(kws), disassemble(code)))
                        written += 1
                print("      wrote %d programs to %s" % (written, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
