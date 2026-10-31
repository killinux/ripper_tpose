# -*- coding: utf-8 -*-
"""Put ウィンク / ウィンク右 (and ウィンク２ / ｳｨﾝｸ２右) on the right eyes of PMX files, as new files beside a copy of the
folder tree (plain Python + mmd_tools' PMX module; the originals are only read).

MMD's convention - Japanese / East-Asian models, the Expression Kit, ROE / FF7 / Stellar Blade / Vindictus / AION2
exporters - is ウィンク (and ウィンク２) = the model's OWN LEFT eye, the 左腕 side, +X in PMX space; ウィンク右 the right.
The downloaded Western "18" series (Daz / XPS conversions: Fiona 18, Reika 18, Tifa ... 18) has them the other way
round, so every dance that winks closes the wrong eye (checked on 409 PMX, 2026-09-27).

    python fix_wink_sides.py <file or folder> ... --out <folder> [--base <folder>] [--suffix _winkfix]
                             [--dry-run] [--skip-existing] [--report out.json]

Per PMX: the side each wink morph moves - vertex offsets at their vertices, bone moves at their bones, a group morph
through its members, each weighted by how far it moves - is the mean X of what moves.  When ウィンク moves the right
eye and ウィンク右 the left, the two morphs' names (Japanese and English) are swapped; the same for ウィンク２ /
ｳｨﾝｸ２右 (also spelt ウィンク２右).  A pair already right, a pair with a morph missing or one that moves both eyes is left
alone.  The fixed file goes to <out>/<path relative to --base>/<stem><suffix>.pmx; mmd_tools writes texture paths
relative to the new file, so it still reads the original folder's textures (same drive); the file is read back and its
sides checked again.  Without --base the relative path starts at each input folder.
"""
import argparse
import glob
import importlib.util
import json
import os
import sys

PAIRS = (("ウィンク", ("ウィンク右",)), ("ウィンク２", ("ｳｨﾝｸ２右", "ウィンク２右")))
SIDE_MIN = 0.15            # |mean X| / spread below this = both eyes (or none): not a one-sided wink


def find_pmx_module():
    root = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py", "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                    "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
        hits = sorted(glob.glob(os.path.join(root, pattern)))
        if hits:
            spec = importlib.util.spec_from_file_location("mmd_pmx", hits[0])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise SystemExit("mmd_tools' core/pmx/__init__.py not found")


pmx = find_pmx_module()


def side_points(model, morph, factor=1.0, depth=0):
    """[(x, weight)] of what a morph moves."""
    out = []
    if isinstance(morph, pmx.VertexMorph):
        for o in morph.offsets:
            w = sum(c * c for c in o.offset) ** 0.5
            if w > 0:
                out.append((model.vertices[o.index].co[0], w * factor))
    elif isinstance(morph, pmx.BoneMorph):
        for o in morph.offsets:
            if o.index is None or o.index < 0:
                continue
            q = o.rotation_offset
            w = sum(c * c for c in o.location_offset) ** 0.5 + 2.0 * (1.0 - min(1.0, abs(q[3])))
            if w > 0:
                out.append((model.bones[o.index].location[0], w * factor))
    elif isinstance(morph, pmx.GroupMorph) and depth < 4:
        for o in morph.offsets:
            if o.morph is not None and 0 <= o.morph < len(model.morphs):
                out += side_points(model, model.morphs[o.morph], factor * abs(o.factor), depth + 1)
    return out


def side_of(model, morph):
    """'L' (+X, the model's own left), 'R', or '' (both / nothing / not measurable)."""
    pts = side_points(model, morph)
    total = sum(w for _x, w in pts)
    if total <= 0:
        return ""
    mean = sum(x * w for x, w in pts) / total
    spread = (sum(abs(x) * w for x, w in pts) / total) or 1e-9
    if abs(mean) / spread < SIDE_MIN:
        return ""
    return "L" if mean > 0 else "R"


def check(model):
    """[(left name, right name, side of left, side of right, index L, index R)] for the pairs present."""
    by_name = {m.name: i for i, m in enumerate(model.morphs)}
    out = []
    for left, rights in PAIRS:
        right = next((r for r in rights if r in by_name), None)
        if left not in by_name or right is None:
            continue
        il, ir = by_name[left], by_name[right]
        out.append((left, right, side_of(model, model.morphs[il]), side_of(model, model.morphs[ir]), il, ir))
    return out


def fix_file(path, out_path, dry_run=False):
    model = pmx.load(path)
    pairs = check(model)
    res = {"file": path, "pairs": [{"names": [l, r], "sides": [sl, sr]} for l, r, sl, sr, _a, _b in pairs]}
    swaps = [(il, ir) for _l, _r, sl, sr, il, ir in pairs if sl == "R" and sr == "L"]
    if not pairs:
        res["action"] = "no wink morphs"
        return res
    if not swaps:
        res["action"] = "already right" if all(sl == "L" and sr == "R" for _l, _r, sl, sr, _a, _b in pairs) \
            else "left alone (a side not clear)"
        return res
    for il, ir in swaps:
        a, b = model.morphs[il], model.morphs[ir]
        a.name, b.name = b.name, a.name
        a.name_e, b.name_e = b.name_e, a.name_e
    res["action"] = "swapped %d pair(s)" % len(swaps)
    res["out"] = out_path
    if dry_run:
        return res
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # written next to the target (texture paths are made relative to that folder) and renamed only after it reads
    # back: a batch stopped mid-save left a half-written file that --skip-existing then took for done (10-31)
    tmp = out_path + ".tmp"
    pmx.save(tmp, model, add_uv_count=model.header.additional_uvs)
    again = check(pmx.load(tmp))
    os.replace(tmp, out_path)
    res["after"] = [[sl, sr] for _l, _r, sl, sr, _a, _b in again]
    res["ok"] = all(sl == "L" and sr == "R" for _l, _r, sl, sr, _a, _b in again if sl and sr)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+", help="PMX files or folders (searched recursively)")
    ap.add_argument("--out", required=True, help="where the fixed copies go")
    ap.add_argument("--base", help="relative paths below --out start here (default: each input folder)")
    ap.add_argument("--suffix", default="_winkfix")
    ap.add_argument("--contains", default="", help="only files whose path contains this (e.g. ' 18')")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-existing", action="store_true", help="leave files whose fixed copy is already there")
    ap.add_argument("--report", help="write every file's result as JSON")
    args = ap.parse_args()
    jobs = []
    for item in args.inputs:
        if os.path.isdir(item):
            base = args.base or item
            for f in sorted(glob.glob(os.path.join(item, "**", "*.pmx"), recursive=True)):
                if args.suffix not in os.path.basename(f) and args.contains in f:
                    jobs.append((f, base))
        else:
            jobs.append((item, args.base or os.path.dirname(item)))
    results, counts = [], {}
    for path, base in jobs:
        rel = os.path.relpath(path, base)
        stem, ext = os.path.splitext(rel)
        out_path = os.path.join(args.out, stem + args.suffix + ext)
        if args.skip_existing and os.path.isfile(out_path):
            res = {"file": path, "out": out_path, "action": "exists (skipped)"}
            results.append(res)
            counts["exists"] = counts.get("exists", 0) + 1
            continue
        try:
            res = fix_file(path, out_path, args.dry_run)
        except Exception as exc:  # noqa: BLE001 - one broken file must not stop the batch
            res = {"file": path, "action": "error: %r" % exc}
        results.append(res)
        key = res["action"].split(" (")[0] if not res["action"].startswith("error") else "error"
        counts[key] = counts.get(key, 0) + 1
        print("%-34s %s" % (res["action"][:34], rel), flush=True)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    print("WINK_SUMMARY " + json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
