# -*- coding: utf-8 -*-
"""Resolve a model's material slots to its textures and export them as PNG.

The First Descendant assigns materials per mesh slot; CUE4Parse (with the 2024
community .usmap) writes the slot's MaterialInstance NAMES into the ActorX file,
but cannot parse the instance's parameters any more (class layout changed since
that mapping was dumped).  So for every slot this script:

  1. finds the MaterialInstance package by name in the container index;
  2. reads that package's zen name map (iostore.py, no .usmap needed) - every
     texture the instance references appears there by name (``..._C``, ``_N``,
     ``_P``, ``_ID``, ``_FX``, shared ``T_*`` / ``Female_HairTex_*``);
  3. finds those texture packages and hands the whole list to cue4parse once,
     which decodes them (they are UE5 virtual textures) to PNG;
  4. runs UE Viewer on the instance package for its scalar/vector parameters
     (hair root/tip colours, emissive colour ...) - umodel reads those fine.

Writes <out_dir>/materials.json:
    {"parts": [{"pskx": ..., "slots": [{"slot": 0, "material": "PC_003_A0101_PartA_MI",
                                         "textures": {"PC_003_A0101_PartA_C": "<png>", ...},
                                         "props": "<umodel .props.txt or null>"}]}]}

Usage:
    python resolve_textures.py --out <model out dir> --pskx <a.pskx> [--pskx <b.pskx> ...]
        [--hint /PC/MESH/003/] [--game-root ...] [--export-root ...] [--aes-key-file ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import iostore  # noqa: E402

DEFAULT_GAME_ROOT = r"E:\SteamLibrary\steamapps\common\The First Descendant"
DEFAULT_EXPORT_ROOT = r"D:\tfd_exports"
DEFAULT_KEY_FILE = r"D:\tfd_exports\_keys\aes_key.txt"
DEFAULT_CUE4 = r"E:\tools\cue4parse_cli\cue4parse.exe"
DEFAULT_OODLE = r"E:\tools\cue4parse_cli\oodle-data-shared.dll"
DEFAULT_USMAP = r"E:\tools\tfd\Mappings_2024-07-16_gildor.usmap"
DEFAULT_UMODEL = r"E:\tools\umodel_specific\materials\umodel_materials_ue5.exe"
GAME_TAG = "GAME_TheFirstDescendant"

# names in a material's name map that are textures (by TFD suffix convention).
# The trailing digit is not optional decoration: Gley's face albedo really is
# ``PC_007_A0101_Face_C1``, and without it her face has no colour at all.
TEXTURE_RE = re.compile(r"(_C|_N|_P|_ID|_E|_FX|_M|_A|_D|_MK|_AO|_ORM|_Mask|_R|_Alpha|_d|_n)\d?$")

# Lash and brow instances set their ``texture`` parameter to None and inherit the strand
# atlas from the master material, so their name map lists no texture at all and the card
# would render as a flat tinted quad.  These are the master's two atlases.
PARENT_ATLAS = (
    (re.compile(r"eyel(ea|a|e)sh|_lash", re.I), "T_eyelash2_D"),     # "Eyeleash" is theirs too
    (re.compile(r"eyeb(ro|lo)w|(^|_)fur(_\d+)?_m[il]$", re.I), "T_eyebrow_d"),
)


def read_key(path: str) -> str:
    key = os.environ.get("TFD_AES_KEY", "") or open(path, encoding="utf-8").read().strip()
    return key[2:] if key.lower().startswith("0x") else key


def psk_slots(path: str) -> list[str]:
    data = open(path, "rb").read()
    pos, slots = 0, []
    while pos + 32 <= len(data):
        name = data[pos:pos + 20].split(b"\0")[0].decode(errors="replace")
        _flag, size, count = struct.unpack_from("<iii", data, pos + 20)
        pos += 32
        if name == "MATT0000":
            slots = [data[pos + i * size:pos + i * size + 64].split(b"\0")[0].decode(errors="replace")
                     for i in range(count)]
        pos += size * count
    return slots


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pskx", action="append", required=True)
    ap.add_argument("--hint", default="", help="path substring preferred when a name is ambiguous, e.g. /PC/MESH/003/")
    ap.add_argument("--game-root", default=DEFAULT_GAME_ROOT)
    ap.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    ap.add_argument("--aes-key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--cue4parse", default=DEFAULT_CUE4)
    ap.add_argument("--oodle", default=DEFAULT_OODLE)
    ap.add_argument("--usmap", default=DEFAULT_USMAP)
    ap.add_argument("--umodel", default=DEFAULT_UMODEL)
    ap.add_argument("--no-props", action="store_true", help="skip the UE Viewer parameter dump")
    args = ap.parse_args()

    paks = os.path.join(args.game_root, "M1", "Content", "Paks")
    utoc = os.path.join(paks, "M1-Windows.utoc")
    key_hex = read_key(args.aes_key_file)
    toc = iostore.Toc(utoc, bytes.fromhex(key_hex))
    oodle = iostore.Oodle(args.oodle)
    paths = toc.paths()
    by_name: dict[str, list[str]] = {}
    for p in paths:
        if p.endswith(".uasset"):
            by_name.setdefault(os.path.basename(p)[:-7], []).append(p)

    def find_pkg(name: str) -> str | None:
        cands = by_name.get(name)
        if not cands:
            return None
        if len(cands) > 1 and args.hint:
            hinted = [c for c in cands if args.hint in c]
            cands = hinted or cands
        return sorted(cands)[0]

    tex_root = os.path.join(args.export_root, "cue4_exports")
    os.makedirs(tex_root, exist_ok=True)
    parts, tex_pkgs, mi_pkgs = [], set(), {}
    for pskx in args.pskx:
        slots = []
        for i, mat in enumerate(psk_slots(pskx)):
            mi = find_pkg(mat)
            entry = {"slot": i, "material": mat, "mi_package": mi, "textures": {}, "props": None}
            if mi:
                mi_pkgs[mat] = mi
                z = iostore.parse_zen(toc.read_chunk(paths[mi], oodle))
                for n in z["names"]:
                    if n.startswith("/") or n == mat or not TEXTURE_RE.search(n):
                        continue
                    tp = find_pkg(n)
                    entry["textures"][n] = tp
                    if tp:
                        tex_pkgs.add(tp)
            if not any(entry["textures"].values()):
                for pattern, atlas in PARENT_ATLAS:
                    if pattern.search(mat):
                        tp = find_pkg(atlas)
                        if tp:
                            entry["textures"][atlas] = tp
                            tex_pkgs.add(tp)
                        break
            slots.append(entry)
        parts.append({"pskx": pskx, "slots": slots})
        print("[tex] %s: %d slots, %d material packages found"
              % (os.path.basename(pskx), len(slots), sum(1 for s in slots if s["mi_package"])))

    # textures the CUE4Parse mesh export already dropped (parent-material ones) are kept;
    # everything else is decoded now, in one cue4parse run
    todo = sorted(p for p in tex_pkgs
                  if not os.path.isfile(os.path.join(tex_root, p[:-7].replace("/", os.sep) + ".png")))
    if todo:
        lst = os.path.join(args.out, "_texture_packages.txt")
        os.makedirs(args.out, exist_ok=True)
        with open(lst, "w", encoding="utf-8") as fh:
            fh.write("\n".join(todo) + "\n")
        cmd = [args.cue4parse, "-i", paks, "-k", key_hex, "-g", GAME_TAG, "-m", args.usmap,
               "-f", "png", "-o", tex_root, "-c", lst, "-y"]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log = (run.stdout + run.stderr).replace(key_hex, "<KEY>")
        errs = [l for l in log.splitlines() if "ERR" in l or "Failed" in l]
        print("[tex] cue4parse decoded %d texture packages (%d errors)" % (len(todo), len(errs)))
        for l in errs[:8]:
            print("      " + l[:200])
        with open(os.path.join(args.out, "cue4parse_textures.log"), "w", encoding="utf-8") as fh:
            fh.write(log)

    # umodel: material instance parameters (colours, scalars) -> .props.txt
    props_root = os.path.join(args.export_root, "umodel_exports")
    if not args.no_props and mi_pkgs:
        key_file = os.path.join(args.out, "._key.tmp")
        with open(key_file, "w", encoding="ascii") as fh:
            fh.write("0x" + key_hex)
        try:
            for mat, mi in mi_pkgs.items():
                rel = mi[len("M1/Content/"):-7] if mi.startswith("M1/Content/") else mi[:-7]
                target = os.path.join(props_root, rel.replace("/", os.sep) + ".props.txt")
                if os.path.isfile(target):
                    continue
                subprocess.run([args.umodel, "-game=first", "-path=" + paks, "-aes=@" + key_file,
                                "-export", "-out=" + props_root, rel],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        finally:
            try:
                os.remove(key_file)
            except OSError:
                pass

    missing = []
    for part in parts:
        for s in part["slots"]:
            for n, tp in list(s["textures"].items()):
                png = os.path.join(tex_root, tp[:-7].replace("/", os.sep) + ".png") if tp else None
                s["textures"][n] = png if png and os.path.isfile(png) else None
                if s["textures"][n] is None:
                    if tp is None:
                        # no package of that name anywhere in the container, so it was never a
                        # texture - just a parameter whose name looks like one (Face_Dyed_Mask)
                        del s["textures"][n]
                    else:
                        missing.append(n)
            if s["mi_package"]:
                rel = s["mi_package"][len("M1/Content/"):-7]
                pt = os.path.join(props_root, rel.replace("/", os.sep) + ".props.txt")
                s["props"] = pt if os.path.isfile(pt) else None
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "materials.json")
    json.dump({"parts": parts, "missing_textures": sorted(set(missing))},
              open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    total = sum(len(s["textures"]) for p in parts for s in p["slots"])
    print("[tex] %d/%d textures resolved -> %s" % (total - len(missing), total, out))
    if missing:
        print("[tex] missing: " + ", ".join(sorted(set(missing))[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
