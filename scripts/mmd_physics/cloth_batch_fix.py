"""Fix the cloth physics of many archived PMX at once, as side files - the 2026-10-24/25 ROE skirt batch.

    python cloth_batch_fix.py scan.json --work <folder> [--refit auto|always|never] [--margin 0.05] [--legs-min 5]
        [--addon-dir <frozen copy of blender_addons>] [--suffix _裙子碰撞修正] [--skin "*_nk_body_nude,*_nk_face"]
        [--vmd dance.vmd] [--blender blender.exe] [--only a,b] [--limit N] [--dry-run]

scan.json: cloth_check_pmx.py --json over the main PMX; every model it flags (bodies ignoring the legs, boxes off
their cloth, joints through the body / to themselves, loose ends) is fixed.  Variants follow the ROE archive layout:
<stem>.pmx, <stem>_bustB.pmx in the same folder, <folder>_full/<stem>_full(_bustB).pmx; whichever exist.

Per model, one Blender at a time:
1. every variant rebuilt by cloth_rebuild_blender.py (default: the bones that had physics, see there);
2. models with --legs-min or more bodies by the legs (cloth_check_pmx's near_legs) and a _full: the body colliders
   refitted inside the _full's nude skin (cloth_collision_pmx.py --skin ... --thigh-halves on the rebuilt _full,
   --colliders-from it for the dressed variants), and the main PMX measured in the gesture dance
   (skin_clip_blender.py: archived / rebuilt / refitted).  --refit auto keeps the refit only when it clips
   --margin less than the rebuild: on the 13-model sample it helped where cloth by the legs still could not collide
   (-28..-37 %) and hurt where the legs wear stockings or boots (the nude-fitted thighs are thinner than what the
   meter sees: b14 / d07 / j07 up to 2x).  always / never skip the choice;
3. the chosen files copied next to the originals as <name><suffix>.pmx at the end of the model (the originals are
   never written); <work>/results.json records variants, meters, choice and files.
Resumable: a model already in results.json is skipped; one whose folder already holds a <suffix> file it did not
write itself is skipped too (hand-made fixes stay).  A Blender run that dies (another window's jobs, memory) is tried
once more.  Use --addon-dir with a COPY of scripts/blender_addons when the batch runs for hours: the repo copy may
change under it.  The scratch PMX are deleted per model; logs and meters stay in <work>/<stem>/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("scan")
ap.add_argument("--work", required=True, help="folder for results.json and the per-model logs / meters")
ap.add_argument("--refit", default="auto", choices=("auto", "always", "never"))
ap.add_argument("--margin", type=float, default=0.05, help="auto: the refit must clip this much less (0.05 = 5 %%)")
ap.add_argument("--legs-min", type=int, default=5, help="bodies by the legs that make a model worth measuring")
ap.add_argument("--addon-dir", default=os.path.join(os.path.dirname(TOOLS), "blender_addons"))
ap.add_argument("--suffix", default="_裙子碰撞修正")
ap.add_argument("--skin", default="*_nk_body_nude,*_nk_face", help="the _full's nude skin materials (ROE)")
ap.add_argument("--vmd", default=r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd")
ap.add_argument("--blender", default=r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
ap.add_argument("--only", default="")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()
RESULTS = os.path.join(args.work, "results.json")
KEYS = ("ignoring_legs", "boxes_off", "joints_through_body", "joints_self", "loose_ends")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(cmd, logfile, timeout=1800):
    with open(logfile, "w", encoding="utf-8", errors="replace") as fh:
        try:
            return subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return -9


def blender(script, argv, logfile, tries=2):
    for k in range(tries):
        code = run([args.blender, "-b", "--factory-startup", "--python", os.path.join(TOOLS, script), "--"] + argv,
                   logfile)
        if code == 0:
            return True
        log("   blender %s exit %s (try %d)" % (script, code, k + 1))
    return False


def python(script, argv, logfile):
    return run([sys.executable, os.path.join(TOOLS, script)] + argv, logfile) == 0


def meter(pmx, out):
    if not os.path.exists(out) and not blender("skin_clip_blender.py",
                                               [pmx, args.vmd, out, "--surface", "*", "--bones", "auto"],
                                               out[:-5] + ".log"):
        return None
    try:
        return json.load(open(out, encoding="utf-8"))["summary"]["mean"]
    except (OSError, ValueError, KeyError):
        return None


def save(results):
    with open(RESULTS, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)


os.makedirs(args.work, exist_ok=True)
results = json.load(open(RESULTS, encoding="utf-8")) if os.path.exists(RESULTS) else {}
todo = [r for r in json.load(open(args.scan, encoding="utf-8")) if r.get("dynamic") and any(r.get(k) for k in KEYS)]
only = {x for x in args.only.split(",") if x}
done_now = 0
for r in todo:
    main = os.path.normpath(r["pmx"])
    folder, stem = os.path.dirname(main), os.path.basename(main)[:-4]
    if (only and stem not in only) or (stem in results and not results[stem].get("redo")):
        continue
    own = set(results.get(stem, {}).get("written", []))
    full_dir = folder + "_full"
    present = [os.path.join(folder, n) for n in os.listdir(folder)]
    if os.path.isdir(full_dir):
        present += [os.path.join(full_dir, n) for n in os.listdir(full_dir)]
    if any(args.suffix in os.path.basename(p) and p not in own for p in present):
        results[stem] = {"skipped": "already has a %s side file" % args.suffix}
        save(results)
        log("%s: skipped (side files exist)" % stem)
        continue
    variants = {"main": main}
    for key, path in (("bustB", os.path.join(folder, stem + "_bustB.pmx")),
                      ("full", os.path.join(full_dir, stem + "_full.pmx")),
                      ("full_bustB", os.path.join(full_dir, stem + "_full_bustB.pmx"))):
        if os.path.exists(path):
            variants[key] = path
    legs = r.get("near_legs", 0) >= args.legs_min and "full" in variants and args.refit != "never"
    if args.dry_run:
        log("%s: would rebuild %s%s" % (stem, ", ".join(variants), "; measure + refit" if legs else ""))
        continue
    t0 = time.time()
    wd = os.path.join(args.work, stem)
    os.makedirs(wd, exist_ok=True)
    entry = {"pmx": main, "variants": sorted(variants), "near_legs": r.get("near_legs", 0)}
    log("%s: %d variants, %d bodies by the legs" % (stem, len(variants), entry["near_legs"]))
    rebuilt = {}
    for key, src in variants.items():
        out = os.path.join(wd, key + "_rb.pmx")
        if not os.path.exists(out) and not blender("cloth_rebuild_blender.py",
                                                   [src, out, "--addon-dir", args.addon_dir,
                                                    "--report", out[:-4] + ".json"], out[:-4] + ".log"):
            break
        rebuilt[key] = out
    if len(rebuilt) < len(variants):
        entry["error"] = "rebuild failed"
        results[stem] = entry
        save(results)
        log("%s: REBUILD FAILED - nothing written" % stem)
        continue
    chosen, entry["choice"] = dict(rebuilt), "rebuilt"
    if legs:
        coll, fit = {}, os.path.join(wd, "full_coll.pmx")
        if os.path.exists(fit) or python("cloth_collision_pmx.py",
                                         [rebuilt["full"], fit, "--skin", args.skin, "--thigh-halves"], fit[:-4] + ".log"):
            coll["full"] = fit
            for key in ("main", "bustB"):
                out = os.path.join(wd, key + "_coll.pmx")
                if key in rebuilt and (os.path.exists(out) or python(
                        "cloth_collision_pmx.py", [rebuilt[key], out, "--colliders-from", fit], out[:-4] + ".log")):
                    coll[key] = out
            out = os.path.join(wd, "full_bustB_coll.pmx")
            if "full_bustB" in rebuilt and (os.path.exists(out) or python(
                    "cloth_collision_pmx.py", [rebuilt["full_bustB"], out, "--skin", args.skin, "--thigh-halves"],
                    out[:-4] + ".log")):
                coll["full_bustB"] = out
        m = {"orig": meter(main, os.path.join(wd, "meter_orig.json")),
             "rebuilt": meter(rebuilt["main"], os.path.join(wd, "meter_rb.json")),
             "refit": meter(coll["main"], os.path.join(wd, "meter_coll.json")) if "main" in coll else None}
        entry["meter"] = m
        complete = set(coll) >= set(rebuilt)
        if complete and (args.refit == "always" or (m["rebuilt"] is not None and m["refit"] is not None
                                                    and m["refit"] < (1.0 - args.margin) * m["rebuilt"])):
            chosen, entry["choice"] = coll, "refit"
        log("%s: meters orig %s / rebuilt %s / refit %s -> %s" % (stem, m["orig"], m["rebuilt"], m["refit"],
                                                                  entry["choice"]))
    written = []
    for key, path in chosen.items():
        src = variants[key]
        dst = os.path.join(os.path.dirname(src), os.path.basename(src)[:-4] + args.suffix + ".pmx")
        if os.path.exists(dst) and dst not in own:
            entry.setdefault("kept_existing", []).append(dst)
            continue
        shutil.copyfile(path, dst)
        written.append(dst)
    entry["written"], entry["seconds"] = written, round(time.time() - t0)
    results[stem] = entry
    save(results)
    for f in os.listdir(wd):
        if f.endswith(".pmx"):
            os.remove(os.path.join(wd, f))
    log("%s: wrote %d files in %d s" % (stem, len(written), entry["seconds"]))
    done_now += 1
    if args.limit and done_now >= args.limit:
        break
log("BATCH DONE (%d models this run, %d in results)" % (done_now, len(results)))
