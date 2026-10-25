"""Fix the cloth physics of many archived PMX at once, as side files - the 2026-10-24/25 ROE skirt batch.

    python cloth_batch_fix.py scan.json --work <folder> [--refit auto|always|never] [--margin 0.05] [--legs-min 5]
        [--legs-inside auto|never] [--addon-dir <frozen copy of blender_addons>] [--suffix _裙子碰撞修正]
        [--skin "*_nk_body_nude,*_nk_face"] [--vmd dance.vmd] [--blender blender.exe] [--only a,b] [--limit N]
        [--dry-run] [--report out.html]
    python cloth_batch_fix.py scan.json --work <folder> --report-only out.html

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
   --legs-inside auto (default) also tries the add-on's legs_inside="collide" there (cloth that starts inside a leg
   collider hits the legs anyway, pushed out in the first frames): only if its drop test settles, and kept only
   when it clips --margin less than the choice so far - tight skirts (ROE h05 913 -> 310 per frame, settled; a09
   tore two joints at rest, so not eligible);
3. the chosen files copied next to the originals as <name><suffix>.pmx at the end of the model (the originals are
   never written); <work>/results.json records variants, meters, choice and files.
Resumable: a model already in results.json is skipped; one whose folder already holds a <suffix> file it did not
write itself is skipped too (hand-made fixes stay).  A Blender run that dies (another window's jobs, memory) is tried
once more.  Use --addon-dir with a COPY of scripts/blender_addons when the batch runs for hours: the repo copy may
change under it.  The scratch PMX are deleted per model; logs and meters stay in <work>/<stem>/.
--report / --report-only: a Chinese HTML table of results.json - every model's meters and choice, cloth_check_pmx
before (the scan) and after (run here over the main side files), and the models still clipping > 100 per frame.
"""
import html
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
ap.add_argument("--legs-inside", default="auto", choices=("auto", "never"),
                help="auto: also try cloth that starts inside the legs colliding anyway (drop test must settle)")
ap.add_argument("--skip-worse", action="store_true",
                help="write no side files for a model whose chosen version clips more than the archived one "
                     "(by --margin); by default it is written and flagged (it still fixes the other faults)")
ap.add_argument("--addon-dir", default=os.path.join(os.path.dirname(TOOLS), "blender_addons"))
ap.add_argument("--suffix", default="_裙子碰撞修正")
ap.add_argument("--skin", default="*_nk_body_nude,*_nk_face", help="the _full's nude skin materials (ROE)")
ap.add_argument("--vmd", default=r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd")
ap.add_argument("--blender", default=r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
ap.add_argument("--only", default="")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--report", help="write the HTML report when done")
ap.add_argument("--report-only", help="only write the HTML report of what results.json holds")
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


CHECK = (("ignoring_legs", "不撞腿"), ("boxes_off", "盒子不贴布"), ("joints_through_body", "穿身体关节"),
         ("joints_self", "自连"), ("loose_ends", "链尾悬空"))
CHOICE = {"rebuilt": "重建", "refit": "贴合碰撞体", "legs_inside": "陷腿照撞"}


def write_report(results, scan_path, out_path):
    """The batch as a Chinese HTML table (see the module docstring)."""
    scan = {os.path.normcase(os.path.normpath(r["pmx"])): r for r in json.load(open(scan_path, encoding="utf-8"))}
    done = {k: v for k, v in results.items() if v.get("written")}
    side = {k: os.path.join(os.path.dirname(v["pmx"]), k + args.suffix + ".pmx") for k, v in done.items()}
    side = {k: p for k, p in side.items() if os.path.exists(p)}
    check_path = os.path.join(args.work, "side_check.json")
    if side:
        subprocess.run([sys.executable, os.path.join(TOOLS, "cloth_check_pmx.py")] + list(side.values())
                       + ["--json", check_path], check=True, stdout=subprocess.DEVNULL)
        after = {os.path.basename(r["pmx"])[:-len(args.suffix + ".pmx")]: r
                 for r in json.load(open(check_path, encoding="utf-8"))}
    else:
        after = {}
    before = {k: scan.get(os.path.normcase(os.path.normpath(v["pmx"]))) for k, v in done.items()}
    n = lambda r, k: len(r.get(k, [])) if r else 0                                           # noqa: E731
    used = lambda v: (v.get("meter") or {}).get(v.get("choice", "rebuilt"))                   # noqa: E731
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0                                       # noqa: E731
    fmt = lambda x: "%.1f" % x if isinstance(x, (int, float)) else "-"                      # noqa: E731
    metered = {k: v for k, v in done.items() if (v.get("meter") or {}).get("orig") is not None and used(v) is not None}
    skipped = [k for k, v in results.items() if v.get("skipped")]
    failed = [k for k, v in results.items() if v.get("error")]
    hard = sorted((k for k, v in metered.items() if used(v) > 100), key=lambda k: -used(metered[k]))
    css = (":root{--bg:#fff;--fg:#1d1d1f;--mute:#6e6e73;--line:#e5e5ea;--good:#2e7d32;--head:#f5f5f7}"
           "@media (prefers-color-scheme:dark){:root{--bg:#1c1c1e;--fg:#f2f2f7;--mute:#a1a1a6;--line:#3a3a3c;"
           "--good:#81c784;--head:#2c2c2e}}body{background:var(--bg);color:var(--fg);font:14px/1.5 'Microsoft YaHei',"
           "system-ui,sans-serif;margin:24px 16px}h1{font-size:22px}h2{font-size:17px;margin-top:28px}p{max-width:980px}"
           ".wrap{overflow:auto;max-height:80vh;margin:8px 0 16px;border:1px solid var(--line);width:fit-content;"
           "max-width:100%}table{border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:4px 10px;"
           "text-align:right;white-space:nowrap}th{background:var(--head);position:sticky;top:0}td.l,th.l{text-align:"
           "left}.good{color:var(--good);font-weight:600}.mute{color:var(--mute)}")
    out = ["<!doctype html><html lang='zh'><head><meta charset='utf-8'><meta name='viewport' content='width=device-"
           "width, initial-scale=1'><title>布料物理批量修正</title><style>%s</style></head><body>" % css,
           "<h1>布料物理批量修正</h1>",
           "<p class='mute'>%s，<code>scripts/mmd_physics/cloth_batch_fix.py</code>：每个有毛病的模型用做裙子物理的插件"
           "重建（只重建原来有物理的骨头）；布挨着腿的再试按 full 版裸体贴合碰撞体、陷腿照撞，量过选穿腿最少的（贴合 / "
           "陷腿照撞要少 %.0f%% 以上才用，陷腿照撞还要先过掉落测试）。原文件都没动，修好的另存为 "
           "<code>…%s.pmx</code>。插件：%s。</p>" % (
               time.strftime("%Y-%m-%d"), 100 * args.margin, html.escape(args.suffix),
               html.escape("、".join(sorted({v.get("addon", "?") for v in done.values()})))),
           "<p>修了 %d 个模型，写了 %d 个文件；跳过 %d 个（已经有修正版）；失败 %d 个%s。</p>" % (
               len(done), sum(len(v["written"]) for v in done.values()), len(skipped), len(failed),
               ("：" + "、".join(failed)) if failed else "")]
    if metered:
        counts = {c: sum(v.get("choice") == c for v in metered.values()) for c in CHOICE}
        o, u = avg([v["meter"]["orig"] for v in metered.values()]), avg([used(v) for v in metered.values()])
        out.append("<p>布挨着腿的 %d 个模型，手势舞每帧有多少布料顶点陷进腿里（腿上穿的什么都算）：原版平均 <b>%.1f</b>，"
                   "用的那版 <b class='good'>%.1f</b>（少 %.0f%%）。用了%s。</p>" % (
                       len(metered), o, u, 100 * (1 - u / o) if o else 0,
                       "，".join("%s %d 个" % (CHOICE[c], counts[c]) for c in CHOICE)))
    out.append("<p>检查工具（主文件）合计，原版 → 修正版：%s。</p>" % "，".join(
        "%s %d → %d" % (label, sum(n(before[k], key) for k in done), sum(n(after.get(k), key) for k in done))
        for key, label in CHECK))
    if hard:
        out.append("<h2>还剩很多的（每帧 &gt; 100）</h2><p>%s。多半是布一开始就裹在大腿碰撞体里（只能不撞腿），可试"
                   "插件的 <code>legs_inside=\"collide\"</code>，或加细骨链、单独处理大腿。</p>" % "、".join(
                       "%s %s → %s" % (html.escape(k), fmt(metered[k]["meter"]["orig"]), fmt(used(metered[k])))
                       for k in hard))
    worse = [k for k, v in metered.items() if used(v) > (1.0 + args.margin) * v["meter"]["orig"] + 0.5]
    if worse:
        out.append("<h2>修完反而更穿的</h2><p>%s。修正版还是写了（盒子、关节、碰撞组这些毛病修好了），要原版的穿腿表现就"
                   "用原文件；<code>--skip-worse</code> 让批量不写这类。ROE b10 是腿上枪套里的手枪带物理（原版就带），"
                   "量到的是枪身碰脚踝，不是裙子。</p>" % "、".join(
                       "%s %s → %s" % (html.escape(k), fmt(metered[k]["meter"]["orig"]), fmt(used(metered[k])))
                       for k in sorted(worse)))
    out.append("<h2>每个模型</h2><div class='wrap'><table><tr><th class='l'>模型</th><th>文件</th><th>挨着腿</th>"
               "<th>穿腿 原版</th><th>重建</th><th>贴合</th><th>陷腿照撞</th><th class='l'>用的</th>" +
               "".join("<th>%s 前 → 后</th>" % label for _k, label in CHECK) + "</tr>")
    for k in sorted(done, key=lambda s: -((done[s].get("meter") or {}).get("orig") or 0)):
        v, m = done[k], done[k].get("meter") or {}
        li = fmt(m.get("legs_inside")) if m.get("legs_inside") is not None else (
            html.escape(m.get("legs_inside_drop", "-"))[:24] if m else "-")
        out.append("<tr><td class='l'>%s</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                   "<td class='l'>%s</td>%s</tr>" % (
                       html.escape(k), len(v["written"]), v.get("near_legs", 0), fmt(m.get("orig")),
                       fmt(m.get("rebuilt")), fmt(m.get("refit")), li, CHOICE.get(v.get("choice"), "-"),
                       "".join("<td>%d → <span class='%s'>%d</span></td>" % (
                           n(before[k], kk), "good" if n(after.get(k), kk) < n(before[k], kk) else "",
                           n(after.get(k), kk)) for kk, _l in CHECK)))
    out.append("</table></div></body></html>")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    log("report: %s (%d models)" % (out_path, len(done)))


os.makedirs(args.work, exist_ok=True)
results = json.load(open(RESULTS, encoding="utf-8")) if os.path.exists(RESULTS) else {}
if args.report_only:
    write_report(results, args.scan, args.report_only)
    sys.exit(0)
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
    legs = r.get("near_legs", 0) >= args.legs_min                    # worth measuring at all
    refit = legs and "full" in variants and args.refit != "never"
    if args.dry_run:
        log("%s: would rebuild %s%s%s%s" % (stem, ", ".join(variants), "; measure" if legs else "",
                                           " + refit" if refit else "",
                                           " + legs-inside" if legs and args.legs_inside == "auto" else ""))
        continue
    t0 = time.time()
    wd = os.path.join(args.work, stem)
    os.makedirs(wd, exist_ok=True)
    entry = {"pmx": main, "variants": sorted(variants), "near_legs": r.get("near_legs", 0), "addon": args.addon_dir}
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
        if refit and (os.path.exists(fit) or python("cloth_collision_pmx.py",
                                                    [rebuilt["full"], fit, "--skin", args.skin, "--thigh-halves"],
                                                    fit[:-4] + ".log")):
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
        if args.legs_inside == "auto":
            li = os.path.join(wd, "main_li.pmx")
            ok = os.path.exists(li) or blender("cloth_rebuild_blender.py",
                                               [main, li, "--addon-dir", args.addon_dir, "--legs-inside", "collide",
                                                "--drop-test", "60", "--report", li[:-4] + ".json"], li[:-4] + ".log")
            try:
                drop = json.load(open(li[:-4] + ".json", encoding="utf-8")).get("drop_test", {}).get("summary", "")
            except (OSError, ValueError):
                drop = ""
            m["legs_inside_drop"] = drop or ("rebuild failed" if not ok else "no drop test")
            m["legs_inside"] = meter(li, os.path.join(wd, "meter_li.json")) if drop.startswith("settled") else None
            so_far = m["refit"] if entry["choice"] == "refit" else m["rebuilt"]
            if m["legs_inside"] is not None and so_far is not None and m["legs_inside"] < (1.0 - args.margin) * so_far:
                same = {"main": li}
                for key, src in variants.items():
                    out = os.path.join(wd, key + "_li.pmx")
                    if key != "main" and (os.path.exists(out) or blender(
                            "cloth_rebuild_blender.py", [src, out, "--addon-dir", args.addon_dir, "--legs-inside",
                                                         "collide", "--report", out[:-4] + ".json"], out[:-4] + ".log")):
                        same[key] = out
                if len(same) == len(variants):
                    chosen, entry["choice"] = same, "legs_inside"
        log("%s: meters orig %s / rebuilt %s / refit %s / legs-inside %s (%s) -> %s" % (
            stem, m["orig"], m["rebuilt"], m["refit"], m.get("legs_inside"), m.get("legs_inside_drop", "-"),
            entry["choice"]))
        now = m.get(entry["choice"])
        if m["orig"] is not None and now is not None and now > (1.0 + args.margin) * m["orig"] + 0.5:
            entry["worse_than_archive"] = True      # ROE b10: holstered pistols with physics, 33.7 -> 41.0
            if args.skip_worse:
                entry["skipped"] = "clips more than the archived file (%.1f > %.1f)" % (now, m["orig"])
                results[stem] = entry
                save(results)
                log("%s: chosen version clips more than the archive - nothing written (--skip-worse)" % stem)
                continue
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
if args.report:
    write_report(results, args.scan, args.report)
