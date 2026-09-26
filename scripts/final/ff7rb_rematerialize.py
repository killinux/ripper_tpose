"""Rebuild chosen materials of an exported FF7 Rebirth blend straight from the game files.

ff7rebirth_tools builds every material from its material table (one JSON per material instance,
written by FModel or ff7rb_cli_export.py).  Some exported blends lack the right table for a few
materials and so got textures guessed by file name, or were not recognised as an eye:
  * PC0000_17 Cloud (Loveless, no mask) wears PC0000_11's material instances - FModel wrote only the
    tables of the model's own folder, so nine materials had no base colour: a grey Cloud;
  * PC0010_10 Sephiroth's transformation uses PC0010_00_Eye - no table, and the name guess gave the
    eye the wing's roughness / alpha maps (see-through, no iris);
  * Vincent's PC0011_00_EyeL / EyeR were not taken for eyes (is_eye_material_name knew only "eye"),
    so his iris map covered the whole eyeball.

Per blend:
  1. which materials: --material NAME (repeatable), --no-base (every used material whose Base Color
     is not linked) and/or --no-record (every used material built without a table, i.e. with
     textures guessed by file name) - the two lists are asked from Blender first;
  2. finds each material instance in the game by name (CUE4Parse CLI listing of
     End/Content/*/Material/<name>.uasset; a name found in more than one folder is skipped);
  3. rebuilds its table exactly like ff7rb_cli_export.fix_materials (raw parent chain + the base
     Material's defaults) and exports the textures it references as PNG;
  4. in Blender runs ff7rebirth_tools.prepare_material(force=True) on those materials only - the
     same code the batch export uses - packs the new images into the blend and saves it in place
     (uncompressed like the originals, no .blend1); with --backup the untouched original is copied
     there first.

  python ff7rb_rematerialize.py <blend> --material PC0011_00_EyeL --material PC0011_00_EyeR --backup DIR
  python ff7rb_rematerialize.py <blend> --no-base --no-record --backup DIR
  python ff7rb_rematerialize.py <blend> --no-record --dry-run      # only find the materials in the game

Report line: FF7RB_REMAT={json}
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT_PREFIX = "FF7RB_REMAT="
LIST_PREFIX = "FF7RB_REMAT_NOBASE="
DEFAULT_BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
PLACEHOLDER_PREFIX = "/game/renderer/texture/"      # renderer default textures, never exported as files


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tables_under(work):
    for root, _dirs, files in os.walk(work):
        if "_raw_materials" in root.replace("\\", "/").split("/"):
            continue
        for name in files:
            if name.lower().endswith(".json"):
                yield os.path.join(root, name)


def images_under(work):
    for root, _dirs, files in os.walk(work):
        for name in files:
            if name.lower().endswith((".png", ".tga", ".jpg", ".jpeg", ".exr", ".hdr")):
                yield os.path.join(root, name)


# ------------------------------------------------------------------ Blender side
def worker(argv):
    import bpy

    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--list-no-base", action="store_true")
    ap.add_argument("--work", default="")
    ap.add_argument("--material", action="append", default=[])
    ap.add_argument("--backup", default="")
    a = ap.parse_args(argv)
    tools = load_module("ff7rb_remat_tools", "ff7rebirth_tools.py")
    if a.list_no_base:
        used = [m for m in bpy.data.materials if m.users]
        print(LIST_PREFIX + json.dumps({
            "no_base": sorted(m.name for m in used if not tools.material_has_base_texture(m)),
            # built without a table (textures guessed by file name): prepare_material stamps the table path
            "no_record": sorted(m.name for m in used if not m.get("ff7rb_material_json")),
        }, ensure_ascii=True))
        return
    records = tools.load_material_records([a.work])
    textures = sorted(images_under(a.work))
    index = tools.build_texture_index(textures)
    work_abs = os.path.normcase(os.path.abspath(a.work))
    done = {}
    for name in a.material:
        material = bpy.data.materials.get(name)
        if material is None:
            done[name] = {"ok": False, "why": "not in blend"}
            continue
        ok = bool(tools.prepare_material(material, textures, records, index, force=True))
        nodes = material.node_tree.nodes if material.use_nodes and material.node_tree else {}
        done[name] = {"ok": ok, "base": tools.material_has_base_texture(material),
                      "layered_eye": bool(nodes and nodes.get("FF7RB_EyeColorMix")),
                      "blend_method": material.blend_method,
                      "images": sorted({n.image.name for n in nodes if getattr(n, "image", None)}) if nodes else []}
    packed = 0
    for image in bpy.data.images:
        path = os.path.normcase(os.path.abspath(bpy.path.abspath(image.filepath))) if image.filepath else ""
        if path.startswith(work_abs) and not image.packed_file and image.users:
            image.pack()
            packed += 1
    saved = False
    if any(r.get("ok") for r in done.values()):
        if a.backup:
            os.makedirs(os.path.dirname(a.backup), exist_ok=True)
            if not os.path.exists(a.backup):
                shutil.copy2(bpy.data.filepath, a.backup)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_mainfile(filepath=bpy.data.filepath, compress=False)
        saved = True
    print(RESULT_PREFIX + json.dumps({"blend": bpy.data.filepath, "materials": done, "packed_images": packed,
                                      "saved": saved}, ensure_ascii=True))


# ------------------------------------------------------------------ driver
def blender_line(cmd, prefix):
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = next((l for l in run.stdout.splitlines() if l.startswith(prefix)), "")
    if not line:
        raise RuntimeError("no %s line: %s" % (prefix, (run.stdout + run.stderr)[-800:]))
    return json.loads(line[len(prefix):])


def driver(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend")
    ap.add_argument("--material", action="append", default=[])
    ap.add_argument("--no-base", action="store_true", help="also every used material without a Base Color link")
    ap.add_argument("--no-record", action="store_true",
                    help="also every used material built without a material table (textures guessed by name)")
    ap.add_argument("--work", default="", help="CLI output (default: %%TEMP%%/ff7rb_rematerialize/<blend name>)")
    ap.add_argument("--backup", default="", help="folder for the untouched original")
    ap.add_argument("--dry-run", action="store_true", help="find the materials in the game, change nothing")
    ap.add_argument("--blender", default=DEFAULT_BLENDER)
    a = ap.parse_args(argv)
    cli = load_module("ff7rb_remat_cli", "ff7rb_cli_export.py")
    ca = types.SimpleNamespace(cli=cli.CLI, usmap=cli.USMAP, game=cli.GAME)
    blend = os.path.abspath(a.blend)
    stem = os.path.splitext(os.path.basename(blend))[0]
    work = os.path.abspath(a.work or os.path.join(tempfile.gettempdir(), "ff7rb_rematerialize", stem))
    me = os.path.abspath(__file__)
    names = list(dict.fromkeys(a.material))
    if a.no_base or a.no_record:
        lists = blender_line([a.blender, "-b", blend, "--factory-startup", "--python", me, "--",
                              "--worker", "--list-no-base"], LIST_PREFIX)
        for key, wanted in (("no_base", a.no_base), ("no_record", a.no_record)):
            if wanted:
                names += [n for n in lists[key] if n not in names]
    if not names:
        print(RESULT_PREFIX + json.dumps({"blend": blend, "materials": {}, "note": "nothing to rebuild"}))
        return 0
    listing = cli.run_cli(ca, ca.game, ["End/Content/*/Material/%s.uasset" % n for n in names], None, listing=True)
    found = {}
    for line in listing.splitlines():
        pkg = line.strip().replace("\\", "/")
        if pkg.endswith(".uasset") and "/Material/" in pkg:
            found.setdefault(os.path.splitext(os.path.basename(pkg))[0], set()).add(pkg)
    located, problems = {}, {}
    for n in names:
        pkgs = sorted(found.get(n, ()))
        if len(pkgs) == 1:
            located[n] = pkgs[0]
        else:
            problems[n] = "not found in the game" if not pkgs else "several packages: %s" % pkgs
    if a.dry_run or not located:
        print(RESULT_PREFIX + json.dumps({"blend": blend, "located": located, "problems": problems,
                                          "dry_run": a.dry_run}, ensure_ascii=False))
        return 0 if located or a.dry_run else 1
    if os.path.isdir(work):
        shutil.rmtree(work)             # our own scratch only
    for pkg in located.values():
        path = os.path.join(work, pkg[:-len(".uasset")] + ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{}")              # an empty table: fix_materials rebuilds it from the game
    cli.fix_materials(ca, ca.game, work)
    wanted = set()
    for path in tables_under(work):
        with open(path, encoding="utf-8-sig") as fh:
            table = json.load(fh).get("Textures") or {}
        for ref in table.values():
            if isinstance(ref, str) and not ref.lower().startswith(PLACEHOLDER_PREFIX):
                wanted.add(cli.object_path_to_package(ref))
    if wanted:
        cli.run_cli(ca, ca.game, sorted(wanted), work)
    cmd = [a.blender, "-b", blend, "--factory-startup", "--python", me, "--", "--worker", "--work", work]
    for n in located:
        cmd += ["--material", n]
    if a.backup:
        cmd += ["--backup", os.path.join(os.path.abspath(a.backup), os.path.basename(blend))]
    result = blender_line(cmd, RESULT_PREFIX)
    result.update({"located": located, "problems": problems, "textures_exported": len(wanted), "work": work})
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False))
    return 0 if all(r.get("ok") for r in result["materials"].values()) else 1


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--worker" in args:
        worker(args)
    else:
        sys.exit(driver(args))
