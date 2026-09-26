"""Repair the iris of already exported FF7 Rebirth blends (huge black pupils).

FF7 Rebirth's iris maps (IrisColor / IrisNormal / IrisOcclusion) are iris-only images:
pupil in the middle, iris filling the whole square.  The eye mesh has one UV set shared
with the sclera map; the game samples the iris maps at that UV scaled x2 about the centre.
Blends built before ff7rebirth_tools.EYE_IRIS_UV_SCALE existed sampled the iris map at the
raw eye UV, so only the middle of the map - mostly pupil - showed.  This inserts the
FF7RB_EyeIrisUV mapping node and moves the iris mask to 0.225-0.25 (see
ff7rebirth_tools.repair_eye_iris_uv); nothing else in the file changes.

Driver (plain Python), any mix of .blend files and folders (searched recursively;
``*_converted.blend`` PMX intermediates and ``.blend1`` backups are skipped)::

    python fix_ff7rb_eyes.py E:/game_export/FF7Rebirth --backup E:/_backup/ff7rebirth_eyes
    python fix_ff7rb_eyes.py <blend> --dry-run

Each blend is opened in Blender in the background, repaired, and saved in place
(uncompressed like the originals, no .blend1); with --backup the untouched original is
copied there first, keeping its path relative to the common root.  Already repaired or
non-Rebirth blends are reported and left alone.  Report line: ``FF7RB_EYE_FIX={json}``.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

RESULT_PREFIX = "FF7RB_EYE_FIX="
DEFAULT_BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_tools():
    spec = importlib.util.spec_from_file_location(
        "ff7rb_eye_fix_tools", os.path.join(HERE, "ff7rebirth_tools.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)      # module-level helpers only; nothing is registered
    return module


def worker(argv):
    import bpy

    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default="")
    a = ap.parse_args(argv)
    tools = load_tools()
    path = bpy.data.filepath
    fixed = []
    for material in bpy.data.materials:
        if a.dry_run:
            nodes = material.node_tree.nodes if material.use_nodes and material.node_tree else {}
            if (nodes and nodes.get("FF7RB_EyeColorMix") and nodes.get("FF7RB_EyeIrisMask")
                    and not nodes.get("FF7RB_EyeIrisUV")):
                fixed.append(material.name)
        elif tools.repair_eye_iris_uv(material):
            fixed.append(material.name)
    already = [m.name for m in bpy.data.materials
               if m.use_nodes and m.node_tree and m.node_tree.nodes.get("FF7RB_EyeIrisUV")
               and m.name not in fixed]
    saved = False
    if fixed and not a.dry_run:
        if a.backup:
            os.makedirs(os.path.dirname(a.backup), exist_ok=True)
            if not os.path.exists(a.backup):
                shutil.copy2(path, a.backup)
        bpy.context.preferences.filepaths.save_version = 0     # no .blend1 next to the archive copy
        bpy.ops.wm.save_mainfile(filepath=path, compress=False)
        saved = True
    print(RESULT_PREFIX + json.dumps({"blend": path, "fixed": fixed, "already": already,
                                      "saved": saved, "dry_run": a.dry_run}, ensure_ascii=True))


def collect(paths):
    blends = []
    for p in paths:
        if os.path.isfile(p):
            blends.append(os.path.abspath(p))
            continue
        for root, _dirs, files in os.walk(p):
            for name in files:
                if name.lower().endswith(".blend") and not name.lower().endswith("_converted.blend"):
                    blends.append(os.path.abspath(os.path.join(root, name)))
    return sorted(set(blends))


def driver(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--backup", default="", help="folder for the untouched originals")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--blender", default=DEFAULT_BLENDER)
    ap.add_argument("--report", default="", help="write all result lines to this JSON file")
    a = ap.parse_args(argv)
    blends = collect(a.paths)
    common = os.path.commonpath([os.path.dirname(b) for b in blends]) if blends else ""
    results = []
    for i, blend in enumerate(blends, 1):
        cmd = [a.blender, "-b", blend, "--factory-startup", "--python", os.path.abspath(__file__), "--", "--worker"]
        if a.dry_run:
            cmd.append("--dry-run")
        if a.backup:
            cmd += ["--backup", os.path.join(a.backup, os.path.relpath(blend, common))]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = next((l for l in run.stdout.splitlines() if l.startswith(RESULT_PREFIX)), "")
        if line:
            res = json.loads(line[len(RESULT_PREFIX):])
        else:
            res = {"blend": blend, "error": (run.stdout + run.stderr)[-600:], "returncode": run.returncode}
        results.append(res)
        state = ("ERROR" if "error" in res else "fixed %d" % len(res["fixed"]) if res["fixed"]
                 else "already ok" if res["already"] else "no Rebirth eye")
        print("[%d/%d] %-12s %s" % (i, len(blends), state, blend), flush=True)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    bad = [r for r in results if "error" in r]
    print("total %d, fixed %d, already %d, untouched %d, errors %d" % (
        len(results), sum(1 for r in results if r.get("fixed")),
        sum(1 for r in results if not r.get("fixed") and r.get("already")),
        sum(1 for r in results if "error" not in r and not r.get("fixed") and not r.get("already")), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--worker" in args:
        worker(args)
    else:
        sys.exit(driver(args))
