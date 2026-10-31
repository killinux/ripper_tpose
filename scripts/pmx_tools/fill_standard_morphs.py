# -*- coding: utf-8 -*-
"""Fill in the MMD standard expressions a PMX lacks by mixing the vertex morphs it has (plain Python + mmd_tools' PMX
module), as a new file beside the original.

Taimanin Squad's PMX (151, 2026-10-04) have 14 of the 30 usual names: the game's faces are anime-style - the eyes are
painted on the texture, there is no eyeball mesh - so the PMX Expression Transfer add-on cannot read them, and the
exporter only cut what the game's whole-face shapes give (まばたき, 笑い, ウィンク.., あいうえお, にっこり, 口角下げ,
困る, 怒り).  The missing ones are mixes of those, already split by face region:

    じと目 = まばたき x 0.45            びっくり = まばたき x -0.3 (the lids open wider)
    なごみ = 笑い x 0.75                はぅ = 笑い x 0.5 + まばたき x 0.5 + 怒り x 0.3
    真面目 = 怒り x 0.5                 下 = 怒り x 0.7
    上 = 怒り x -0.6 (brows up and out) にこり = the brows of smile_face (else 怒り x -0.3)
    ∧ = 口角下げ                        口角上げ = にっこり x 0.5
    口横広げ = い x 0.6                 にやり = にっこり + い x 0.3
    ワ = あ + い x 0.5                  ん = い x 0.25 + う x 0.15
    (ω has nothing to be mixed from: left out)

A recipe source may be limited to a region - "brow" (above the eyes), "eye", "mouth" (below the eyes) - measured on
the vertices まばたき moves.  Two closing shapes mixed at weights adding up to 1 stay closed (a convex mix), so はぅ
does not push the lids through.  Recipes whose sources are missing fall back to the next alternative or are skipped;
existing names are never replaced.  The new morphs join the 表情 display frame.

    python fill_standard_morphs.py <file or folder> ... [--suffix _表情补全] [--contains text] [--dry-run]
                                   [--report out.json] [--only じと目,ワ]
Writes <stem><suffix>.pmx beside each input (same folder: textures resolve as before; the original is only read).
"""
import argparse
import glob
import importlib.util
import json
import os

BROW, EYE, MOUTH = 1, 2, 3

# name, English name, panel, alternatives [ {source: weight or (weight, region)} ]
RECIPES = [
    ("じと目", "jito-eye", EYE, [{"まばたき": 0.45}]),
    ("びっくり", "surprised", EYE, [{"まばたき": -0.3}]),
    ("なごみ", "calm", EYE, [{"笑い": 0.75}, {"まばたき": 0.7}]),
    ("はぅ", "close><", EYE, [{"笑い": 0.5, "まばたき": 0.5, "怒り": 0.3}, {"まばたき": 1.0, "怒り": 0.3}]),
    ("真面目", "serious", BROW, [{"怒り": 0.5}]),
    ("下", "brow_down", BROW, [{"怒り": 0.7}]),
    ("上", "brow_up", BROW, [{"怒り": -0.6}]),
    ("にこり", "cheerful", BROW, [{"smile_face": (1.0, "brow")}, {"怒り": -0.3}]),
    ("∧", "mouth_∧", MOUTH, [{"口角下げ": 1.0}]),
    ("口角上げ", "mouth_corner_up", MOUTH, [{"にっこり": 0.5}]),
    ("口横広げ", "mouth_wide", MOUTH, [{"い": 0.6}]),
    ("にやり", "grin", MOUTH, [{"にっこり": 1.0, "い": 0.3}]),
    ("ワ", "wa", MOUTH, [{"あ": 1.0, "い": 0.5}]),
    ("ん", "n", MOUTH, [{"い": 0.25, "う": 0.15}]),
]


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


def vertex_offsets(model, morph, factor=1.0, depth=0):
    """{vertex index: [dx, dy, dz]} of a vertex morph, group morphs expanded."""
    out = {}
    if isinstance(morph, pmx.VertexMorph):
        for o in morph.offsets:
            d = out.setdefault(o.index, [0.0, 0.0, 0.0])
            for k in range(3):
                d[k] += o.offset[k] * factor
    elif isinstance(morph, pmx.GroupMorph) and depth < 4:
        for o in morph.offsets:
            if o.morph is not None and 0 <= o.morph < len(model.morphs):
                for i, d in vertex_offsets(model, model.morphs[o.morph], factor * o.factor, depth + 1).items():
                    acc = out.setdefault(i, [0.0, 0.0, 0.0])
                    for k in range(3):
                        acc[k] += d[k]
    return out


def eye_band(model, by_name):
    """(low, high) height of what まばたき moves - the eyes."""
    m = by_name.get("まばたき")
    if m is None:
        return None
    ys = [model.vertices[i].co[1] for i, d in vertex_offsets(model, m).items() if sum(c * c for c in d) > 1e-12]
    if not ys:
        return None
    ys.sort()
    return ys[int(0.02 * (len(ys) - 1))], ys[int(0.98 * (len(ys) - 1))]


def in_region(y, region, band):
    if region is None or band is None:
        return True
    low, high = band
    pad = 0.15 * (high - low)
    if region == "brow":
        return y > high + pad
    if region == "mouth":
        return y < low - pad
    return low - pad <= y <= high + pad


def fill(model, only=None):
    by_name = {m.name: m for m in model.morphs}
    band = eye_band(model, by_name)
    made, skipped = [], []
    for name, name_e, panel, alternatives in RECIPES:
        if only and name not in only:
            continue
        if name in by_name:
            continue
        recipes = [alt for alt in alternatives if all(src in by_name for src in alt)]
        if not recipes:
            skipped.append("%s: no source" % name)
            continue
        offsets = []
        for recipe in recipes:                       # the next alternative when a mix moves nothing (smile_face
            acc = {}                                 # without brows -> にこり from 怒り)
            for src, spec in recipe.items():
                weight, region = spec if isinstance(spec, tuple) else (spec, None)
                for i, d in vertex_offsets(model, by_name[src], weight).items():
                    if not in_region(model.vertices[i].co[1], region, band):
                        continue
                    a = acc.setdefault(i, [0.0, 0.0, 0.0])
                    for k in range(3):
                        a[k] += d[k]
            for i, d in sorted(acc.items()):
                if sum(c * c for c in d) > 1e-14:
                    o = pmx.VertexMorphOffset()
                    o.index, o.offset = i, d
                    offsets.append(o)
            if offsets:
                break
        if not offsets:
            skipped.append("%s: the mix moves nothing" % name)
            continue
        morph = pmx.VertexMorph(name, name_e, panel)
        morph.offsets = offsets
        model.morphs.append(morph)
        by_name[name] = morph
        made.append(name)
    if made:                                         # list them in the 表情 display frame
        frame = next((f for f in model.display if f.name == "表情"), None)
        if frame is not None:
            index = {m.name: i for i, m in enumerate(model.morphs)}
            listed = {i for k, i in frame.data if k == 1}
            for name in made:
                if index[name] not in listed:
                    frame.data.append((1, index[name]))
    return made, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--suffix", default="_表情补全")
    ap.add_argument("--contains", default="")
    ap.add_argument("--only", default="", help="comma separated: build only these names")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s}
    files = []
    for item in args.inputs:
        if os.path.isdir(item):
            files += [f for f in sorted(glob.glob(os.path.join(item, "**", "*.pmx"), recursive=True))
                      if args.suffix not in os.path.basename(f) and args.contains in f]
        else:
            files.append(item)
    results = []
    for path in files:
        stem, ext = os.path.splitext(path)
        out = stem + args.suffix + ext
        try:
            model = pmx.load(path)
            made, skipped = fill(model, only)
            res = {"file": path, "made": made, "skipped": skipped}
            if made and not args.dry_run:
                tmp = out + ".tmp"                   # renamed once it reads back: no half-written file if stopped
                pmx.save(tmp, model, add_uv_count=model.header.additional_uvs)
                pmx.load(tmp)
                os.replace(tmp, out)
                res["out"] = out
        except Exception as exc:  # noqa: BLE001 - one broken file must not stop the batch
            res = {"file": path, "error": repr(exc)}
        results.append(res)
        print("%-40s %s" % (("+%d" % len(res.get("made", []))) if "error" not in res else res["error"][:40],
                            os.path.basename(path)), flush=True)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    print("FILL_SUMMARY files %d, written %d, errors %d" % (
        len(results), sum(1 for r in results if r.get("out")), sum(1 for r in results if "error" in r)))


if __name__ == "__main__":
    main()
