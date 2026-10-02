"""Rise of Eros: export the models you name in the game-material (HQ) version - .blend, PMX (+ bust B), XPS -
with one command, and copy them to E: with the gallery.

    python export_hq.py --list                          # every model: HQ .blend / PMX / XPS on E:, what is missing
    python export_hq.py pc_b01_jeans                    # a suit: rebuilt, game materials, PMX + bust B, XPS
    python export_hq.py b01:jeans pc_b01_nk_bs --archive    # ... a nude base too, then to E: + gallery
    python export_hq.py pc_a01_marry --formats xps      # only the XPS, from the .blend that is there
    python export_hq.py a08 --formats pmx               # a main model (key or stem): only its PMX again
    python export_hq.py --todo --skip h,i --lanes 3     # everything --list shows missing, h / i left out
    python export_hq.py --archive-only pc_b01_jeans     # no export: copy to E:, gallery, thumbnails
    python export_hq.py c01:student --dry-run           # print the commands only

Names: a suit as pc_<id>_<suit> or <id>:<suit>; a nude base as pc_<id>_nk_bs / pc_<id>_fm_nk_bs; a main model as
its key (a08, a08_outfit1) or its stem (pc_a08_hd).  --formats picks from blend,pmx,xps (default all three):

  suit  blend  export_suits.py --only <id>:<suit> --force (a fresh .blend from the game bundles; --keep-blend
               keeps the file), then blender: fix_suit_slots_blender.py + hq_materials_blender.py --preview
        pmx    export_suit_pmx_blender.py -> <id>\\blend\\pmx\\<stem>\\<stem>.pmx, tune_bust_pmx.py -> _bustB.pmx
        xps    export_suit_xps_blender.py -> <id>\\blend\\xps\\<stem>\\<stem>.mesh (+ textures beside it)
  nude  the same on nude_materials\\<stem>.blend; blend = slot fixes + game materials built again (--rebuild)
  main  export_character_models.ps1 -Only <key> -Format <formats> -Force, then the bust B

--todo picks every model whose E: copy is not complete and gives each the formats it lacks (a .blend done again
takes its PMX and XPS along).  --lanes N runs N exports at once (all models of a character in one lane: they
share the game-material cache file).  --budget MIN starts no new model after MIN minutes (rerun with
--skip-done to go on).  --archive: html\\make_gallery.py, archive_exports.py roe --only <stems>, the thumbnails
to E: (--only never copies _meta), and a check that every gallery link exists.

Logs and results: D:\\roe_exports\\_hq_runs\\<stem>\\<step>.log + result.json.  Prints ROE_EXPORT_HQ=<json>.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
EXPORTS = r"D:\roe_exports"
ARCHIVE = r"E:\game_export\RiseOfEros"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
HQ_SINCE = datetime.datetime(2026, 10, 1)        # the game-material batch ran on 2026-10-01
FORMATS = ("blend", "pmx", "xps")
STEP_TIMEOUT = 2400                              # seconds per step
NAMES = {"a": "Inase", "b": "Kart", "c": "Misa", "d": "Erin", "e": "Miri", "f": "Rana", "g": "Luf", "h": "Fen",
         "i": "Sera", "j": "Lynn", "k": "Keleira", "l": "SFox", "m": "Amano"}   # = scripts/archive/games.py
# outputs other scripts patch after an export: a re-export drops the patch
AFTER_EXPORT = {
    "g04": "the fan-shrink morph: python pmx_add_scale_morph.py ... 扇子縮小 (docs/roe-motion-to-vmd.md)",
    "a08": "the greatsword: pmx_add_weapon.py (ROE motion work, docs/roe-motion-to-vmd.md)",
    "pc_a01_nk_bs": "the H-scene morphs: python export_roe_eros.py a08",
    "pc_g01_nk_bs": "the H-scene morphs: python export_roe_eros.py g04",
    "pc_g01_fm_nk_bs": "the H-scene morphs: python export_roe_eros.py g04",
    "a00": "the H-scene liquid morphs: python export_roe_eros.py a08 / g04",
}


def load_json(path, default):
    for _ in range(5):                  # a lane may be replacing the file right now
        try:
            with open(path, encoding="utf-8-sig") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            time.sleep(0.2)
    return default


def catalogue(exports):
    """{stem: (kind, info)} for every main model, suit and nude base on D:."""
    out = {}
    manifest = load_json(os.path.join(exports, "character_models_manifest.json"), {})
    for entry in manifest.get("results", []):
        blend = (entry.get("outputs") or {}).get("blend") or entry.get("output")
        if entry.get("status") == "PASS" and blend:
            stem = os.path.splitext(os.path.basename(blend))[0]
            out[stem] = ("main", {"key": entry["model"], "cid": entry["model"].split("_")[0], "blend": blend,
                                  "outputs": entry.get("outputs") or {}})
    suits = {(e["id"], e["suit"]) for e in load_json(os.path.join(exports, "_suits", "manifest.json"), {}).get("suits", [])}
    for path in glob.glob(os.path.join(exports, "_suits", "*", "*", "suit.json")):   # the parts dump of every suit
        cid, suit = os.path.normpath(path).split(os.sep)[-3:-1]
        suits.add((cid, suit))
    for cid, suit in sorted(suits):
        stem = "pc_%s_%s" % (cid, suit)
        out.setdefault(stem, ("suit", {"cid": cid, "suit": suit,
                                       "blend": os.path.join(exports, cid, "blend", stem + ".blend")}))
    for blend in glob.glob(os.path.join(exports, "nude_materials", "pc_*.blend")):
        stem = os.path.splitext(os.path.basename(blend))[0]
        out.setdefault(stem, ("nude", {"cid": re.match(r"pc_([a-z]\d+)", stem).group(1), "blend": blend}))
    return out


def resolve(name, cat):
    """A user's name -> stem in the catalogue (key, id:suit, or the stem itself)."""
    if name in cat:
        return name
    if ":" in name:
        cid, suit = name.split(":", 1)
        stem = "pc_%s_%s" % (cid.lower(), suit)
        return stem if stem in cat else None
    hits = [s for s, (kind, info) in cat.items() if kind == "main" and info["key"] == name.lower()]
    return hits[0] if hits else None


def pmx_of(cid, stem, exports):
    return os.path.join(exports, cid, "blend", "pmx", stem, stem + ".pmx")


def xps_of(cid, stem, exports):
    return os.path.join(exports, cid, "blend", "xps", stem, stem + ".mesh")


def on_e(stem, info, archive_root):
    """What the E: copy has: HQ .blend (dated 2026-10-01 or later: the archive keeps the D: date), PMX, XPS."""
    char = os.path.join(archive_root, NAMES.get(info["cid"][0], info["cid"][0]))
    blend = os.path.join(char, "blend", stem, stem + ".blend")
    when = datetime.datetime.fromtimestamp(os.path.getmtime(blend)) if os.path.isfile(blend) else None
    return {"blend": "HQ" if when and when >= HQ_SINCE else ("old" if when else "-"),
            "pmx": os.path.isfile(os.path.join(char, "pmx", stem, stem + ".pmx")),
            "xps": os.path.isfile(os.path.join(char, "xps", stem, stem + ".mesh"))}


def missing_formats(state):
    if state["blend"] != "HQ":
        return list(FORMATS)            # the .blend again, and the PMX / XPS made from it
    return [f for f in ("pmx", "xps") if not state[f]]


def run(cmd, log_path, dry, env=None):
    """Run one step; its whole output goes to log_path.  Returns (exit code, output)."""
    printable = " ".join('"%s"' % c if " " in c else c for c in cmd)
    print("   $ " + printable, flush=True)
    if dry:
        return 0, ""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                              timeout=STEP_TIMEOUT)
        code, text = proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code, text = -9, "TIMEOUT after %d s\n%s" % (STEP_TIMEOUT, exc.stdout or "")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(printable + "\n\n" + text)
    return code, text


def tagged(text, tag):
    """The JSON a script printed as <tag>={...}, or None."""
    m = re.search(r"^%s=(\{.*\})\s*$" % re.escape(tag), text or "", re.MULTILINE)
    try:
        return json.loads(m.group(1)) if m else None
    except ValueError:
        return None


def bust_b(pmx, logs, dry):
    """The bust-B copy (scripts/mmd_physics/tune_bust_pmx.py) when the PMX has bust physics."""
    report = load_json(pmx[:-4] + ".report.json", {})
    if not dry and not (report.get("physics") or {}).get("bust"):
        return "no bust physics, skipped"
    code, _ = run([sys.executable, os.path.join(SCRIPTS, "mmd_physics", "tune_bust_pmx.py"), pmx, pmx[:-4] + "_bustB.pmx"],
                  os.path.join(logs, "bustB.log"), dry)
    return "ok" if code == 0 else "FAILED (exit %d)" % code


def blender_step(args, blend, script, extra, log, tag):
    cmd = [args.blender, "-b", "--factory-startup", blend, "--python", os.path.join(HERE, script), "--"] + extra
    code, text = run(cmd, log, args.dry_run)
    return code, tagged(text, tag)


def do_blend(stem, kind, info, args, logs, result):
    """Suit: rebuilt from the bundles (unless --keep-blend); suit or nude base: slot fixes + game materials."""
    blend = info["blend"]
    if kind == "suit" and not args.keep_blend:
        code, text = run([sys.executable, os.path.join(HERE, "export_suits.py"), "--only",
                          "%s:%s" % (info["cid"], info["suit"]), "--force", "--lanes", "1", "--no-sheet"],
                         os.path.join(logs, "assemble.log"), args.dry_run)
        line = next((l for l in (text or "").splitlines() if re.match(r"(PASS|WARN|FAIL)\s", l)), "")
        result["assemble"] = line.split()[0] if line else ("dry" if args.dry_run else "FAILED (exit %d)" % code)
        if not args.dry_run and result["assemble"] not in ("PASS", "WARN"):
            return False
    if not args.dry_run and not os.path.isfile(blend):
        result["error"] = "no .blend: " + blend
        return False
    cmd = [args.blender, "-b", "--factory-startup", blend, "--python", os.path.join(HERE, "fix_suit_slots_blender.py"),
           "--python", os.path.join(HERE, "hq_materials_blender.py"), "--", blend, "--preview"]
    if args.rebuild or (kind == "nude" and not args.keep_blend):   # a nude base is game-material already:
        cmd.append("--rebuild")                                      # build it again (--keep-blend: only fix)
    code, text = run(cmd, os.path.join(logs, "hq.log"), args.dry_run)
    if args.dry_run:
        result["hq"] = "dry"
        return True
    data, fix = tagged(text, "ROE_HQ_BLEND"), tagged(text, "ROE_SUIT_FIX")
    if code != 0 or data is None:
        result["hq"] = "FAILED (exit %d)" % code
        return False
    result["hq"] = {"upgraded": len(data.get("upgraded", [])), "kept": len(data.get("kept", [])),
                    "errors": data.get("errors") or [], "missing": data.get("missing") or [],
                    "fixed": {k: v for k, v in (fix or {}).items() if k not in ("file", "problems") and v}}
    return not data.get("errors")


def do_pmx(stem, info, args, logs, result):
    pmx = pmx_of(info["cid"], stem, args.exports)
    code, data = blender_step(args, info["blend"], "export_suit_pmx_blender.py", [pmx],
                              os.path.join(logs, "pmx.log"), "ROE_SUIT_PMX")
    if args.dry_run:
        result["pmx"] = "dry"
    elif code != 0 or data is None:
        result["pmx"] = "FAILED (exit %d)" % code
        return False
    else:
        result["pmx"] = {"torn": data.get("torn"), "morphs": data.get("face_morphs"),
                         "bust": (data.get("physics") or {}).get("bust"),
                         "grant_order_violations": data.get("grant_order_violations")}
    result["bustB"] = bust_b(pmx, logs, args.dry_run)
    return result["bustB"] in ("ok", "no bust physics, skipped")


def do_xps(stem, info, args, logs, result):
    mesh = xps_of(info["cid"], stem, args.exports)
    folder = os.path.dirname(mesh)
    if os.path.isdir(folder) and not args.dry_run:      # a fresh folder: no textures left from an older export
        for name in os.listdir(folder):
            if name.lower().endswith((".mesh", ".png", ".json")):
                os.remove(os.path.join(folder, name))
    code, data = blender_step(args, info["blend"], "export_suit_xps_blender.py", [mesh],
                              os.path.join(logs, "xps.log"), "ROE_SUIT_XPS")
    if args.dry_run:
        result["xps"] = "dry"
        return True
    if code != 0 or data is None:
        result["xps"] = "FAILED (exit %d)" % code
        return False
    result["xps"] = {k: data.get(k) for k in ("meshes", "groups", "alpha_pieces", "missing_textures",
                                              "unweighted_vertices", "unweighted_meshes")}
    return not data.get("missing_textures") and not data.get("unweighted_vertices")


def ensure_preview(stem, info, args, logs, result):
    """A .blend without <stem>_preview.png beside it (the a/g/j nude bases got their game materials without
    one) gets the batch's preview sheet, for the gallery card; the .blend is not saved."""
    preview = os.path.splitext(info["blend"])[0] + "_preview.png"
    if os.path.isfile(preview) and not args.dry_run:
        return
    expr = ("import os, sys, bpy; sys.path.insert(0, %r); import export_character_model_blender as w; "
            "w.render_preview([o for o in bpy.data.objects if o.type == 'MESH'], %r, %r)"
            % (HERE, preview, os.path.join(os.path.dirname(preview), "." + stem)))
    code, _ = run([args.blender, "-b", "--factory-startup", info["blend"], "--python-expr", expr],
                  os.path.join(logs, "preview.log"), args.dry_run)
    result["preview"] = "dry" if args.dry_run else ("rendered" if os.path.isfile(preview) else "FAILED (exit %d)" % code)


def do_suit_or_nude(stem, kind, info, formats, args, logs):
    result = {"stem": stem, "kind": kind, "formats": formats}
    ok = do_blend(stem, kind, info, args, logs, result) if "blend" in formats else True
    if ok and "pmx" in formats:
        ok = do_pmx(stem, info, args, logs, result)
    if ok and "xps" in formats:
        ok = do_xps(stem, info, args, logs, result)
    if ok:
        ensure_preview(stem, info, args, logs, result)
    result["ok"] = ok
    return result


def do_main(stem, info, formats, args, logs):
    result = {"stem": stem, "kind": "main", "formats": formats}
    ps1 = os.path.join(HERE, "export_character_models.ps1")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, "-Only", info["key"],
           "-Format", ",".join(formats), "-Force"]
    code, text = run(cmd, os.path.join(logs, "export.log"), args.dry_run)
    done = re.search(r"Complete: PASS=(\d+) FAIL=(\d+)", text or "")      # the .ps1's last line
    result["export"] = "dry" if args.dry_run else (
        "ok" if code == 0 and done and int(done.group(1)) > 0 and done.group(2) == "0"
        else "FAILED, see %s" % os.path.join(logs, "export.log"))
    ok = result["export"] in ("ok", "dry")
    if ok and "pmx" in formats:
        result["bustB"] = bust_b(info["outputs"].get("pmx") or pmx_of(info["cid"], stem, args.exports), logs, args.dry_run)
        ok = result["bustB"] in ("ok", "no bust physics, skipped", "dry")
    result["ok"] = ok
    return result


def thumb_name(stem, kind, info):
    return {"suit": "%s_%s.jpg" % (info["cid"], info.get("suit")), "main": "%s.jpg" % info.get("key"),
            "nude": "%s.jpg" % stem[3:]}[kind]          # make_gallery.py: the card key is the stem without pc_


def archive(stems, cat, args):
    """Gallery page + thumbnails, then only these models to E:, then their thumbnails (never in --only)."""
    logs = os.path.join(args.exports, "_hq_runs", "_archive")
    out = {}
    code, _ = run([sys.executable, os.path.join(HERE, "html", "make_gallery.py")], os.path.join(logs, "gallery.log"),
                  args.dry_run)
    out["gallery"] = "ok" if code == 0 else "FAILED"
    code, text = run([sys.executable, os.path.join(SCRIPTS, "archive", "archive_exports.py"), "roe", "--only"] + stems,
                     os.path.join(logs, "archive.log"), args.dry_run)
    check = re.search(r"self-check:\s*(\d+)/(\d+) OK", text or "")
    out["archive"] = "dry" if args.dry_run else ("self-check %s/%s OK" % check.groups() if check and code == 0
                                                 else "check %s" % os.path.join(logs, "archive.log"))
    thumbs_src = os.path.join(args.exports, "_gallery", "thumbs")
    thumbs_dst = os.path.join(args.archive_root, "_meta", "gallery", "thumbs")
    copied = []
    for stem in stems:
        kind, info = cat[stem]
        name = thumb_name(stem, kind, info)
        if os.path.isfile(os.path.join(thumbs_src, name)):
            if not args.dry_run:
                os.makedirs(thumbs_dst, exist_ok=True)
                shutil.copy2(os.path.join(thumbs_src, name), os.path.join(thumbs_dst, name))
            copied.append(name)
    out["thumbs"] = len(copied)
    if not args.dry_run:
        with open(os.path.join(HERE, "html", "index.html"), encoding="utf-8") as fh:
            links = set(re.findall(r'file:///([^"\'<> ]+)', fh.read()))
        out["gallery_links"] = len(links)
        out["missing_links"] = [l for l in links if not os.path.exists(urllib.parse.unquote(l))][:20]
    return out


def status(cat, args, families=None):
    """--list: per character, every model with its E: state; the ones not complete marked with what they lack."""
    rows = []
    for stem, (kind, info) in sorted(cat.items(), key=lambda kv: (kv[1][1]["cid"], kv[1][0] != "main", kv[0])):
        if families and info["cid"][0] not in families:
            continue
        state = on_e(stem, info, args.archive_root)
        rows.append((kind, info["cid"], stem, state, missing_formats(state)))
    for kind in ("main", "suit", "nude"):
        sub = [r for r in rows if r[0] == kind]
        if sub:
            print("== %-4s %3d   HQ .blend on E: %3d   PMX %3d   XPS %3d   complete %3d" % (
                kind, len(sub), sum(r[3]["blend"] == "HQ" for r in sub), sum(r[3]["pmx"] for r in sub),
                sum(r[3]["xps"] for r in sub), sum(not r[4] for r in sub)))
    todo = [r for r in rows if r[4]]
    print("\n%d not complete on E: (blend = %s; - = not on E: at all)" % (len(todo), "dated before 2026-10-01 = old"))
    for kind, cid, stem, state, need in todo:
        print("   %-8s %-5s %-26s E: blend %-3s pmx %-3s xps %-3s  -> %s" % (
            NAMES.get(cid[0], cid[0]), kind, stem, state["blend"], "yes" if state["pmx"] else "-",
            "yes" if state["xps"] else "-", ",".join(need)))
    return todo


def lanes_of(jobs, count):
    """Jobs grouped by character id (they share <cache>\\<id>.json), groups spread over `count` lanes by cost."""
    groups = {}
    for stem, formats in jobs:
        cid = re.match(r"pc_([a-z]\d+)", stem).group(1) if stem.startswith("pc_") else stem.split("_")[0]
        groups.setdefault(cid, []).append((stem, formats))
    weight = lambda job: (6 if "blend" in job[1] else 0) + (3 if "pmx" in job[1] else 0) + (1 if "xps" in job[1] else 0)
    lanes = [[] for _ in range(count)]
    for group in sorted(groups.values(), key=lambda g: -sum(map(weight, g))):
        min(lanes, key=lambda lane: sum(map(weight, lane))).extend(group)
    return [lane for lane in lanes if lane]


def run_lanes(jobs, args):
    """Run each lane as its own export_hq.py (same options), wait for all, return their results."""
    folder = os.path.join(args.exports, "_hq_runs", "_lanes")
    os.makedirs(folder, exist_ok=True)
    procs = []
    for index, lane in enumerate(lanes_of(jobs, args.lanes)):
        plan = os.path.join(folder, "lane%d.json" % index)
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump(lane, fh)
        cmd = [sys.executable, os.path.abspath(__file__), "--plan", plan, "--exports", args.exports,
               "--archive-root", args.archive_root, "--blender", args.blender]
        cmd += [flag for flag, on in (("--keep-blend", args.keep_blend), ("--rebuild", args.rebuild),
                                      ("--skip-done", args.skip_done), ("--dry-run", args.dry_run)) if on]
        if args.budget:
            cmd += ["--budget", str(args.budget)]
        log = open(os.path.join(folder, "lane%d.log" % index), "w", encoding="utf-8")
        print("   lane %d: %d models -> %s" % (index, len(lane), log.name), flush=True)
        procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log, lane))
    results = []
    for proc, log, lane in procs:
        proc.wait()
        log.close()
        for stem, _formats in lane:
            saved = load_json(os.path.join(args.exports, "_hq_runs", stem, "result.json"), None)
            results.append(saved or {"stem": stem, "ok": False, "error": "no result (see the lane log)"})
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="pc_<id>_<suit> / <id>:<suit> / pc_<id>_nk_bs / main key or stem")
    ap.add_argument("--list", action="store_true", help="show every model's state on E: (HQ .blend / PMX / XPS)")
    ap.add_argument("--formats", default=",".join(FORMATS), help="any of blend,pmx,xps (default all)")
    ap.add_argument("--todo", action="store_true", help="every model --list shows not complete, with what it lacks")
    ap.add_argument("--family", default="", help="with --list / --todo: only these family letters, e.g. b,c")
    ap.add_argument("--skip", default="", help="with --list / --todo: leave these family letters out, e.g. h,i")
    ap.add_argument("--archive", action="store_true", help="afterwards: gallery + copy these models to E:")
    ap.add_argument("--archive-only", action="store_true", help="no export: gallery + copy the named models to E:")
    ap.add_argument("--keep-blend", action="store_true", help="suit: keep the existing .blend (no rebuild); nude base: fix only, no --rebuild")
    ap.add_argument("--rebuild", action="store_true", help="build the game materials of an earlier run again")
    ap.add_argument("--lanes", type=int, default=1, help="exports at once (one character per lane)")
    ap.add_argument("--budget", type=float, default=0, help="minutes: start no new model after this")
    ap.add_argument("--skip-done", action="store_true", help="skip models whose result.json says done for these formats")
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    ap.add_argument("--plan", help=argparse.SUPPRESS)        # a lane's [(stem, formats)] list (run_lanes)
    ap.add_argument("--exports", default=EXPORTS)
    ap.add_argument("--archive-root", default=ARCHIVE)
    ap.add_argument("--blender", default=BLENDER)
    args = ap.parse_args()
    started = time.time()
    cat = catalogue(args.exports)
    letters = lambda text: {x.strip().lower() for x in text.split(",") if x.strip()}
    families = letters(args.family) or set(NAMES)
    families -= letters(args.skip)
    if args.list or not (args.names or args.todo or args.plan):
        status(cat, args, families)
        return
    formats = [f for f in FORMATS if f in letters(args.formats)]
    if args.plan:
        jobs = [tuple(job) for job in load_json(args.plan, [])]
    elif args.todo:
        jobs = [(stem, need) for _kind, _cid, stem, _state, need in status(cat, args, families)]
        print()
    else:
        jobs, unknown = [], []
        for name in args.names:
            stem = resolve(name, cat)
            if stem:
                jobs.append((stem, formats))
            else:
                unknown.append(name)
        if unknown:
            sys.exit("unknown model(s): %s  (python export_hq.py --list shows the names)" % ", ".join(unknown))
    summary = {}
    if args.archive_only:
        summary["archive"] = archive([stem for stem, _ in jobs], cat, args)
        print("ROE_EXPORT_HQ=" + json.dumps(summary, ensure_ascii=True))
        return
    if args.lanes > 1 and len(jobs) > 1 and not args.plan:
        results = run_lanes(jobs, args)
    else:
        results = []
        for stem, job_formats in jobs:
            kind, info = cat[stem]
            logs = os.path.join(args.exports, "_hq_runs", stem)
            saved = load_json(os.path.join(logs, "result.json"), {})
            if args.skip_done and saved.get("ok") and set(job_formats) <= set(saved.get("formats", [])):
                print("== %s: done %s, skipped" % (stem, saved.get("finished", "")), flush=True)
                results.append(saved)
                continue
            if args.budget and time.time() - started > args.budget * 60:
                print("== %s: budget of %g min used, not started" % (stem, args.budget), flush=True)
                results.append({"stem": stem, "ok": False, "error": "not started (budget)"})
                continue
            print("== %s (%s: %s)" % (stem, kind, ",".join(job_formats)), flush=True)
            t0 = time.time()
            result = (do_main(stem, info, job_formats, args, logs) if kind == "main"
                      else do_suit_or_nude(stem, kind, info, job_formats, args, logs))
            reminder = AFTER_EXPORT.get(stem) or AFTER_EXPORT.get(info.get("key", ""))
            if reminder and ("pmx" in job_formats):
                result["reminder"] = "re-add " + reminder
                print("   NOTE: re-add " + reminder)
            result["seconds"] = round(time.time() - t0)
            result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if not args.dry_run:
                os.makedirs(logs, exist_ok=True)
                with open(os.path.join(logs, "result.json"), "w", encoding="utf-8") as fh:
                    json.dump(result, fh, ensure_ascii=False, indent=1)
            print("   -> %s" % json.dumps({k: v for k, v in result.items() if k not in ("stem", "kind")},
                                         ensure_ascii=False), flush=True)
            results.append(result)
    summary["models"] = results
    summary["failed"] = [r["stem"] for r in results if not r.get("ok")]
    if args.archive and not args.plan:
        done = [r["stem"] for r in results if r.get("ok")]
        print("== archive %d model(s)" % len(done), flush=True)
        summary["archive"] = archive(done, cat, args) if done else "nothing to archive"
        print("   -> %s" % json.dumps(summary["archive"], ensure_ascii=False))
    print("ROE_EXPORT_HQ=" + json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
