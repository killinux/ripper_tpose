"""Stellar Blade's other women (not Eve): every mesh of their character folders exported with CUE4Parse CLI -
the mesh (.psk/.pskx) and its textures into <root>\\raw, and the JSON of the mesh and of every material instance it uses,
with their parents up to the master material, into <root>\\json.

    python export_npc_raw.py [--root D:\\stellarblade_npc] [--only Raven,Lily]

The characters and their meshes are in npc_characters.json (next to this script)."""
import argparse
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = r"E:\tools\cue4parse_cli_ff7\cue4parse.exe"
PAKS = r"D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks"
USMAP = r"E:\game_export\StellarBlade\_meta\mappings\StellarBlade_1.1.0.usmap"


def cli(out, packages, fmt=None):
    for i in range(0, len(packages), 50):
        args = [CLI, "-i", PAKS, "-g", "GAME_StellarBlade", "-m", USMAP, "-o", out, "-y"]
        if fmt:
            args += ["-f", fmt]
        for p in packages[i:i + 50]:
            args += ["-p", p + ".*"]
        subprocess.run(args, capture_output=True)


def json_path(root, package):
    return os.path.join(root, "json", *package.split("/")) + ".json"


def load(root, package):
    try:
        return json.load(open(json_path(root, package), encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []


def package_of(object_path):
    """'/Game/Art/X/MI_A.0' -> 'SB/Content/Art/X/MI_A'; '/Engine/...' is left out."""
    if not object_path.startswith("/Game/"):
        return None
    return "SB/Content/" + object_path[len("/Game/"):].rsplit(".", 1)[0]


def material_refs(exports):
    refs = []
    for e in exports:
        if e.get("Type") == "SkeletalMesh":
            for m in e.get("SkeletalMaterials") or []:
                refs.append(package_of((m.get("Material") or {}).get("ObjectPath", "")))
        elif e.get("Type", "").startswith("MaterialInstance"):
            refs.append(package_of(((e.get("Properties") or {}).get("Parent") or {}).get("ObjectPath", "")))
    return [r for r in refs if r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\stellarblade_npc")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    opts = ap.parse_args()
    chars = json.load(open(os.path.join(HERE, "npc_characters.json"), encoding="utf-8"))["characters"]
    only = {s for s in opts.only.split(",") if s}
    meshes = [m for c in chars if not only or c["name"] in only for m in c["meshes"]]
    raw = os.path.join(opts.root, "raw")
    todo = [m for m in meshes if opts.force or not any(
        os.path.exists(os.path.join(raw, *m.split("/")) + ext) for ext in (".psk", ".pskx"))]
    print(f"[raw] {len(todo)} of {len(meshes)} meshes to export")
    cli(raw, todo)
    seen = set()
    wave = list(meshes)
    while wave:
        cli(os.path.join(opts.root, "json"), [p for p in wave if opts.force or not os.path.exists(json_path(opts.root, p))], "json")
        seen.update(wave)
        wave = sorted({r for p in wave for r in material_refs(load(opts.root, p))} - seen)
        print(f"[json] next wave: {len(wave)} materials")
    # textures the mesh export left out: a master material's own (its ReferencedTextures - brows, lashes) and the
    # instances' parameters that only a parent instance sets
    textures = set()
    for p in seen:
        for e in load(opts.root, p):
            props = e.get("Properties") or {}
            refs = [(t.get("ParameterValue") or {}) for t in props.get("TextureParameterValues") or []]
            refs += ((props.get("CachedExpressionData") or {}).get("ReferencedTextures") or [])
            for r in refs:
                pkg = package_of((r or {}).get("ObjectPath", ""))
                if pkg and not os.path.exists(os.path.join(raw, *pkg.split("/")) + ".png"):
                    textures.add(pkg)
    print(f"[raw] {len(textures)} textures the mesh export left out")
    cli(raw, sorted(textures), "png")
    missing = [m for m in meshes if not any(os.path.exists(os.path.join(raw, *m.split("/")) + ext) for ext in (".psk", ".pskx"))]
    for m in missing:
        print("[raw] NOT EXPORTED", m)


if __name__ == "__main__":
    main()
