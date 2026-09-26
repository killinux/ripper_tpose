# -*- coding: utf-8 -*-
"""Headless FF7 Rebirth export with the CUE4Parse CLI - the part FModel needed a GUI for.

Writes the same tree that "Save Model" in FModel writes (End/Content/.../Model/<id>.psk,
Texture/*.png, Material/*.json with a "Textures" table), so export_ff7rb_models.ps1 and
ff7rebirth_tools.py materialize it unchanged.

Two things the CLI does differently, both handled here:
  * its mesh export writes every material JSON as "{}" (the CUE4Parse material exporter gets
    nothing out of the Rebirth material instances).  We re-read each material instance as raw
    properties (-f json), walk its Parent chain up to the base Material and rebuild the
    FModel-style table: CachedReferencedTextures keyed by texture name, then
    TextureParameterValues keyed by parameter name (child overrides parent).
  * it reads a whole game directory, so a mod has to be mounted next to the game: --mod
    builds a staging tree of hard links to the game containers (no copy, same volume)
    plus the .pak/.utoc/.ucas of the mod under Paks/~mods.

It also reads the 13 Player meshes FModel 4.4.4 rejected with "Read incorrect amount of
tangent bytes" (CUE4Parse 1.2.2 in the CLI handles them).

Usage:
  python ff7rb_cli_export.py --out D:/ff7rebirth_exports/cli_exports
      --package End/Content/Character/Player/PC0099_00_Toad_Standard/Model/PC0099_00.uasset
  python ff7rb_cli_export.py --out <dir> --mod <folder with the mod pak/utoc/ucas> --list
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

# CUE4Parse.CLI rebuilt from joric/CUE4Parse.CLI ab447bb + scripts/final/cue4parse_ff7_mod_tangents.patch (E:/tools/_cli_src, .NET 10 SDK in E:/tools/dotnet); the 0.2.0 release cannot read mod meshes
CLI = "E:/tools/cue4parse_cli_ff7/cue4parse.exe"
GAME = r"D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH"
USMAP_CANDIDATES = (
    r"D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap",
    # the E: archive keeps a copy (scripts/archive, 2026-09-26) - D:\ff7rebirth_exports may be deleted
    r"E:\game_export\FF7Rebirth\_meta\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap",
)
USMAP = next((p for p in USMAP_CANDIDATES if os.path.isfile(p)), USMAP_CANDIDATES[0])
GAME_ENUM = "GAME_FinalFantasy7Rebirth"
CONTAINER_EXT = (".pak", ".utoc", ".ucas", ".sig")
QUOTE = chr(39)


def run_cli(a, input_root, packages, out, fmt=None, listing=False):
    cmd = [a.cli, "-i", input_root, "-g", GAME_ENUM, "-m", a.usmap, "-y"]
    if out:
        cmd += ["-o", out]
    if fmt:
        cmd += ["-f", fmt]
    if listing:
        cmd += ["-l"]
    for p in packages:
        cmd += ["-p", p]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("cue4parse exit %d: %s" % (r.returncode, (r.stdout + r.stderr)[-1500:]))
    return r.stdout


# ------------------------------------------------------------------ staging for mods
def link_or_copy(src, dst):
    try:
        os.link(src, dst)                         # same volume: no extra space, original untouched
    except OSError:
        shutil.copy2(src, dst)


def mod_containers(a):
    for mod_dir in a.mod:
        for path in glob.glob(os.path.join(mod_dir, "**", "*"), recursive=True):
            if os.path.isfile(path) and path.lower().endswith(CONTAINER_EXT):
                yield path


def build_stage(a):
    """Hard links to every game container, plus the mod containers in Paks/~mods."""
    paks = os.path.join(a.stage, "End", "Content", "Paks")
    mods = os.path.join(paks, "~mods")
    if os.path.isdir(mods):
        shutil.rmtree(mods)                       # only ever our own links/copies
    os.makedirs(mods, exist_ok=True)
    game_paks = os.path.join(a.game, "End", "Content", "Paks")
    for name in os.listdir(game_paks):
        src = os.path.join(game_paks, name)
        dst = os.path.join(paks, name)
        if os.path.isfile(src) and name.lower().endswith(CONTAINER_EXT) and not os.path.exists(dst):
            os.link(src, dst)
    for path in mod_containers(a):
        link_or_copy(path, os.path.join(mods, os.path.basename(path)))
    return a.stage


def mod_only_root(a):
    """A game-shaped tree holding only the mod containers and global.utoc/ucas (for listing)."""
    root = a.stage + "_modonly"
    paks = os.path.join(root, "End", "Content", "Paks")
    if os.path.isdir(paks):
        shutil.rmtree(paks)
    os.makedirs(os.path.join(paks, "~mods"))
    for name in ("global.utoc", "global.ucas"):
        link_or_copy(os.path.join(a.game, "End", "Content", "Paks", name), os.path.join(paks, name))
    for path in mod_containers(a):
        link_or_copy(path, os.path.join(paks, "~mods", os.path.basename(path)))
    return root


# ------------------------------------------------------------------ materials
def object_path_to_package(object_path):
    """/Game/Renderer/X/RMI_Y.0 -> End/Content/Renderer/X/RMI_Y.uasset;
    /TifaGANTZ/Material/X.0 (a DRESSCODE plugin mod) -> End/Mods/TifaGANTZ/Content/Material/X.uasset"""
    p = object_path.split(".")[0]
    if p.startswith("/Game/"):
        p = "End/Content/" + p[len("/Game/"):]
    elif p.startswith("/") and p.split("/")[1] not in ("Engine", "Script"):
        root = p.split("/")[1]
        p = "End/Mods/%s/Content/%s" % (root, p[len(root) + 2:])
    return p.lstrip("/") + ".uasset"


def rel_to_package(rel):
    """Exported file (no extension) -> package path.  The CLI writes plugin assets by object
    path (TifaGANTZ/MetaData/fullsuit) but lists them by package (End/Mods/TifaGANTZ/Content/...)."""
    if rel.startswith("End/"):
        return rel + ".uasset"
    root, _, rest = rel.partition("/")
    return "End/Mods/%s/Content/%s.uasset" % (root, rest)


def asset_name(ref):
    name = ref.get("ObjectName") or ""
    if QUOTE in name:
        return name.split(QUOTE)[1].split(".")[-1]
    return os.path.basename((ref.get("ObjectPath") or "").split(".")[0])


def load_raw(raw_root, package):
    path = os.path.join(raw_root, package[:-len(".uasset")] + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    for exp in data if isinstance(data, list) else [data]:
        if exp.get("Type") in ("MaterialInstanceConstant", "MaterialInstanceDynamic", "Material"):
            return exp
    return None


def fix_materials(a, input_root, out):
    """Every empty material JSON under out -> FModel-style {"Textures": {...}}."""
    empties = []
    for path in glob.glob(os.path.join(out, "**", "*.json"), recursive=True):
        # any folder: plugin mods keep materials elsewhere (Gantz_Reika: Aseets/Materiales)
        if "_raw_materials" in path:
            continue
        try:
            with open(path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except ValueError:
            data = {}
        ours = isinstance(data, dict) and str(data.get("_source", "")).startswith("ff7rb_cli_export.py")
        if ours or not (isinstance(data, dict) and data.get("Textures")):   # rebuild our own tables too
            rel = os.path.relpath(path, out).replace(os.sep, "/")
            empties.append((path, rel_to_package(rel[:-len(".json")])))
    if not empties:
        return 0
    raw_root = os.path.join(out, "_raw_materials")
    wanted = {pkg for _p, pkg in empties}
    done = set()
    while wanted - done:                          # material instances, then their parents
        batch = sorted(wanted - done)
        run_cli(a, input_root, batch, raw_root, fmt="json")
        done |= set(batch)
        for pkg in batch:
            exp = load_raw(raw_root, pkg)
            parent = ((exp or {}).get("Properties") or {}).get("Parent") or {}
            if exp and exp.get("Type") != "Material" and parent.get("ObjectPath"):
                wanted.add(object_path_to_package(parent["ObjectPath"]))
    fixed = 0
    for path, pkg in empties:
        chain, cur = [], pkg
        while cur and len(chain) < 12:
            exp = load_raw(raw_root, cur)
            if not exp:
                break
            chain.append(exp)
            parent = (exp.get("Properties") or {}).get("Parent") or {}
            cur = object_path_to_package(parent["ObjectPath"]) if parent.get("ObjectPath") else None
        textures = {}
        for exp in reversed(chain):               # base first, the instance itself last (wins)
            props = exp.get("Properties") or {}
            # the base Material's texture-parameter defaults (renderer placeholders such as
            # Coverage -> FFFFFFFF_BC4): FModel writes them too, and ff7rebirth_tools only skips
            # name-guessing a role when it sees such a placeholder; without them the head/tops
            # got PC0002_00_Hair_A as alpha and the face turned see-through
            ced = exp.get("CachedExpressionData") or props.get("CachedExpressionData") or {}
            params = ced.get("Parameters") or {}
            values = params.get("TextureValues") or []
            for key, entry in params.items():
                infos = entry.get("ParameterInfos") if isinstance(entry, dict) else None
                if key.startswith("RuntimeEntries") and infos and len(infos) == len(values):
                    for info, val in zip(infos, values):
                        if info.get("Name") and isinstance(val, dict) and val.get("ObjectPath"):
                            textures.setdefault(info["Name"], val["ObjectPath"])
            for ref in props.get("CachedReferencedTextures") or []:
                if isinstance(ref, dict) and ref.get("ObjectPath"):
                    textures[asset_name(ref)] = ref["ObjectPath"]
            for tp in props.get("TextureParameterValues") or []:
                name = (tp.get("ParameterInfo") or {}).get("Name")
                val = tp.get("ParameterValue") or {}
                if name and isinstance(val, dict) and val.get("ObjectPath"):
                    textures[name] = val["ObjectPath"]
        if textures:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"Textures": textures, "_source": "ff7rb_cli_export.py (raw MI chain + base defaults)",
                           "_chain": [e.get("Name") for e in chain]}, fh, ensure_ascii=False, indent=2)
            fixed += 1
    return fixed


TEXTURE_EXT = (".png", ".tga", ".dds", ".hdr")
NOT_EXPORTED = ("/Game/Renderer/Texture/", "/Engine/", "/Script/")   # renderer placeholders, engine defaults


def exported_texture(out, object_path):
    """Where the CLI wrote a texture: /Game/... by package path, a plugin's /X/... by object path."""
    stems = [os.path.join(out, object_path_to_package(object_path)[:-len(".uasset")])]
    if not object_path.startswith("/Game/"):
        stems.append(os.path.join(out, object_path.split(".")[0].lstrip("/")))
    for stem in stems:
        for ext in TEXTURE_EXT:
            if os.path.isfile(stem + ext):
                return stem + ext
    return ""


def export_missing_textures(a, input_root, out):
    """Textures a material table names that the mesh export did not write - a mod's material
    instance pointing at base-game maps (#1198's Eve_Skin reads PC0002_00_Skin_Mr) - are exported
    too; otherwise the worker had nothing but a look-alike from another material to go on."""
    wanted = set()
    for path in glob.glob(os.path.join(out, "**", "*.json"), recursive=True):
        if "_raw_materials" in path:
            continue
        try:
            with open(path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except ValueError:
            continue
        textures = data.get("Textures") if isinstance(data, dict) else None
        for ref in (textures or {}).values() if isinstance(textures, dict) else ():
            if isinstance(ref, str) and ref.startswith("/") and not ref.startswith(NOT_EXPORTED) \
                    and not exported_texture(out, ref):
                wanted.add(object_path_to_package(ref))
    if not wanted:
        return []
    try:
        run_cli(a, input_root, sorted(wanted), out)
    except RuntimeError:                          # one bad package: the rest one by one
        for pkg in sorted(wanted):
            try:
                run_cli(a, input_root, [pkg], out)
            except RuntimeError:
                pass
    return sorted(wanted)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--package", action="append", default=[], help="package path (repeatable)")
    ap.add_argument("--mod", action="append", default=[], help="folder holding mod containers (repeatable)")
    ap.add_argument("--stage", default=r"D:\ff7_mods\_stage\rebirth", help="staging tree for --mod")
    ap.add_argument("--list", action="store_true", help="--mod: list the packages inside the mod only")
    ap.add_argument("--game", default=GAME)
    ap.add_argument("--usmap", default=USMAP)
    ap.add_argument("--cli", default=CLI)
    a = ap.parse_args()
    if a.list:
        if not a.mod:
            raise SystemExit("--list needs --mod")
        print(run_cli(a, mod_only_root(a), ["*"], None, listing=True))
        return 0
    # always a stage of hard links: mods installed in the game's own Paks\~mods (replacers such as
    # #363, which swaps all of Tifa's outfits) must not leak into an export of the official models
    input_root = build_stage(a)
    if a.package:
        print(run_cli(a, input_root, a.package, a.out)[-600:])
    fixed = fix_materials(a, input_root, a.out)
    textures = export_missing_textures(a, input_root, a.out)
    print("FF7RB_CLI_EXPORT=" + json.dumps({"out": a.out, "packages": a.package, "materials_fixed": fixed,
                                          "textures_added": len(textures), "input": input_root}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
