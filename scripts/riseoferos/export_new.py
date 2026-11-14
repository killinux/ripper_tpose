"""Rise of Eros: what a game update added, by name, in one command - the game-material (HQ) .blend, PMX (+ bust B)
and XPS of a model, its _nude / _full (complete_nude.py), or a suit; then copied to E: with its gallery cards.

    python export_new.py --list                    # what the game has and E: lacks: models, outfits, suits
    python export_new.py i05                       # a model by id: i05 and its outfits (i05_outfit1)
    python export_new.py "Sera 5" f13              # by family name + number (Alana = Rana's game name) or id
    python export_new.py i05_outfit1               # one outfit of a model only
    python export_new.py f01:oni e01:latex_v2      # suits (a variant like latex_v2 comes from suit_overrides.json)
    python export_new.py i05 --no-nude             # without _nude / _full
    python export_new.py i05 --no-archive          # everything stays on D: (no E:, no gallery)
    python export_new.py i05 --from complete       # go on from a step (after a stop): extract export post nude
                                                   #   complete variants archive
    python export_new.py i05 --dry-run             # print the steps only
    python export_new.py i05 --detach              # run in a process of its own (the log path is printed)

A model, step by step (what was done by hand for e11 / c09_outfit1 on 10-17 and i05 / f13 on 11-14):
  extract    extract_character.ps1 <id> -ExportTextures (install dir + the runtime cache: an update's new files)
  export     export_character_models.ps1 -Only <id> -Format blend,pmx,xps -Force: HQ .blend + PMX + XPS of the id
             and of every outfit of it (-Only matches i05_outfit1 too)
  post       per PMX: expressions copied from the family's pc_<letter>01_hd.pmx on E: when the head has none of its
             own (pmx_copy_face_morphs.py --family; a head with its own 56-58 gets nothing); breasts: the exporter's
             bust -> _bustB.pmx (tune_bust_pmx.py), breast bones it did not know -> pmx_add_bust.py
  nude       the family nude base pc_<letter>01_nk_bs in D:\\roe_exports\\nude_materials: copied from E: if missing and
             given its game materials (export_hq.py --formats blend).  It is the donor of _nude / _full only and is
             never copied back to E: (the h / i families stay the user's non-HQ files there, 10-02)
  complete   complete_nude.py <key>: _nude / _full, each .blend + XPS + PMX (+ bust B); a body unlike the family
             base follows the model's own skin (--follow auto, docs/roe-complete-nude.md section 20)
  variants   the same expressions / breasts for the _nude / _full PMX, and the _full body follows the cups
             (pmx_body_follows_cups.py)
  archive    html/make_gallery.py --only <the new cards> --thumb-dir <E: thumbs>, archive_exports.py roe --only <the
             new stems> (copies, self-checks, relinks the gallery to E:), then every gallery link is checked
A suit: extract (when the id's base body FBX is not on D:), export_hq.py <id>:<suit> (assembled from the bundles, slot
fixes, game materials, preview, PMX + bust B, XPS), archive.
Logs and the result: D:\\roe_exports\\_new_runs\\<name>\\ (one .log per step + result.json).  A model takes 20-40 min
(a followed body: + 4 min per version), a suit 3-5 min.
"""
import argparse
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
sys.path.insert(0, HERE)
import export_hq as hq  # noqa: E402
import export_suits  # noqa: E402
import suit_bundle  # noqa: E402

STEPS = ("extract", "export", "post", "nude", "complete", "variants", "archive")
POWERSHELL = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
ALIASES = {"alana": "f", "ines": "a"}       # the game's English / internal family names our folders do not use
THUMBS = os.path.join(hq.ARCHIVE, "_meta", "gallery", "thumbs")
ID_RE = r"[a-z]\d+|[a-z]_[a-z]+\d+"


# ------------------------------------------------------------------ what the game has
def armor_keys(names):
    """{model key: id} of every dressed model in the bundles: chara_armor_pc_<id>_hd & ld_hd(_tutorial).ab, and the
    outfits meta_armor_pc_<id>_outfit<N>_hd & ld.ab (their meshes come from the id's own bundle)."""
    out = {}
    for name in names:
        low = name.lower()
        m = re.match(r"chara_armor_pc_(%s)_hd & ld_hd(_tutorial)?\.ab$" % ID_RE, low)
        if m:
            out[m.group(1)] = m.group(1)
        m = re.match(r"meta_armor_pc_(%s)_(outfit\d+)_hd & ld\.ab$" % ID_RE, low)
        if m:
            out["%s_%s" % (m.group(1), m.group(2))] = m.group(1)
    return out


def all_ids(names):
    return sorted({m.group(1) for m in (re.match(r"chara_(?:armor|bare)_pc_(%s)(?:_|\.)" % ID_RE, n.lower())
                                        for n in names) if m})


def on_e(stem, cid):
    return os.path.isfile(os.path.join(hq.ARCHIVE, hq.NAMES.get(cid[0], cid[0]), "blend", stem, stem + ".blend"))


def newest_files(dirs, count=1):
    best = []
    for d in dirs:
        for name in os.listdir(d):
            best.append((os.path.getmtime(os.path.join(d, name)), name))
    return sorted(best)[-count:]


def list_new(game):
    dirs = suit_bundle.bundle_dirs(game)
    names = suit_bundle.bundle_names(game)
    when = newest_files(dirs)
    print("bundles: %s  (newest file %s)" % (" + ".join(dirs), time.strftime("%Y-%m-%d %H:%M", time.localtime(when[0][0]))
                                             if when else "-"))
    keys = armor_keys(names)
    todo = [(k, cid) for k, cid in sorted(keys.items()) if not on_e("pc_%s_hd" % k, cid)]
    print("\nmodels the game has and E: lacks (%d of %d):" % (len(todo), len(keys)))
    for key, cid in todo:
        what = "outfit of %s" % cid if key != cid else "%s %s" % (hq.NAMES.get(cid[0], "?"), int(re.sub(r"\D", "", cid) or 0))
        print("   %-16s %-22s -> python export_new.py %s" % (key, what, key))
    stubs = [i for i in all_ids(names) if i not in keys.values() and not glob.glob(
        os.path.join(hq.ARCHIVE, hq.NAMES.get(i[0], i[0]), "blend", "pc_%s_*" % i))]
    print("\nids with no dressed model in the bundles (rig / H-scene / not out yet), not on E: (%d): %s"
          % (len(stubs), ", ".join(stubs) or "-"))
    suits = [(c, s) for c, s in export_suits.list_suits(game) if not on_e("pc_%s_%s" % (c, s), c)]
    print("\nsuits the game has and E: lacks (%d of %d):" % (len(suits), len(export_suits.list_suits(game))))
    for c, s in suits:
        print("   %-22s %-10s -> python export_new.py %s:%s" % ("%s:%s" % (c, s), hq.NAMES.get(c[0], "?"), c, s))


# ------------------------------------------------------------------ names
def resolve(name, keys, suits):
    """('model', id, [keys]) or ('suit', id, suit) for an id, key, stem, <id>:<suit> or a name like "Sera 5"."""
    n = name.strip()
    low = n.lower()
    if ":" in low:
        cid, suit = low.split(":", 1)
        if (cid, suit) in suits:
            return "suit", cid, suit
        raise SystemExit("no suit %s (python export_suits.py --list)" % n)
    m = re.match(r"^(?:pc_)?(%s)(?:_(outfit\d+))?(?:_hd)?$" % ID_RE, low)
    if m:
        cid = m.group(1)
        key = cid + ("_" + m.group(2) if m.group(2) else "")
        if key in keys:
            return "model", cid, [key] if m.group(2) else sorted(k for k, c in keys.items() if c == cid)
        raise SystemExit("no dressed model %s in the bundles (python export_new.py --list)" % n)
    m = re.match(r"^pc_(%s)_(.+)$" % ID_RE, low)
    if m and (m.group(1), m.group(2)) in suits:
        return "suit", m.group(1), m.group(2)
    m = re.match(r"^([a-z]+)[\s_]*(\d+)$", low)
    if m:
        letter = ALIASES.get(m.group(1)) or next((k for k, v in hq.NAMES.items() if v.lower() == m.group(1)), None)
        if letter:
            return resolve("%s%02d" % (letter, int(m.group(2))), keys, suits)
    raise SystemExit("cannot read %r: an id (i05), key (i05_outfit1), <id>:<suit> or a name + number (Sera 5)" % n)


# ------------------------------------------------------------------ steps
class Run:
    def __init__(self, label, args):
        self.args = args
        self.logs = os.path.join(args.exports, "_new_runs", re.sub(r"[^\w.-]+", "_", label))
        self.result = {"name": label, "steps": {}}

    def step(self, name):
        return STEPS.index(name) >= STEPS.index(self.args.start)

    def call(self, cmd, log):
        code, text = hq.run(cmd, os.path.join(self.logs, log), self.args.dry_run)
        return code, text or ""

    def save(self):
        if not self.args.dry_run:
            os.makedirs(self.logs, exist_ok=True)
            with open(os.path.join(self.logs, "result.json"), "w", encoding="utf-8") as fh:
                json.dump(self.result, fh, ensure_ascii=False, indent=1)


def has_bust(pmx):
    """A PMX whose breasts already swing: a non-static rigid body on 左胸 / 右胸 or a bone under them."""
    sys.path.insert(0, os.path.join(SCRIPTS, "clothes_burst"))
    from pmx_nude_switch import pmx_module
    m = pmx_module().load(pmx)
    under = {i for i, b in enumerate(m.bones) if b.name in ("左胸", "右胸")}
    grew = True
    while grew:
        grew = False
        for i, b in enumerate(m.bones):
            if i not in under and b.parent in under:
                under.add(i)
                grew = True
    return any(r.bone in under and r.mode != 0 for r in m.rigids)


def face_morphs(run, pmx):
    code, text = run.call([sys.executable, os.path.join(HERE, "pmx_copy_face_morphs.py"), "--family", pmx, pmx],
                          "face_%s.log" % os.path.basename(pmx)[:-4])
    hit = re.findall(r"^added: (\d+)", text, re.MULTILINE)
    return "FAILED" if code else ("+%s" % hit[-1] if hit else "dry")


def add_bust(run, pmx):
    base = pmx[:-4]
    if not run.args.dry_run and os.path.isfile(base + "_bustB.pmx"):
        os.remove(base + "_bustB.pmx")
    code, _ = run.call([sys.executable, os.path.join(SCRIPTS, "mmd_dances", "pmx_add_bust.py"), pmx, base + "__b.pmx"],
                       "bust_%s.log" % os.path.basename(base))
    if code:
        return "NO BUST (pmx_add_bust failed)"
    if not run.args.dry_run:
        shutil.move(base + "__b.pmx", pmx)
        shutil.move(base + "__b_bustB.pmx", base + "_bustB.pmx")
    return "added + _bustB"


def post_pmx(run, pmx, variant):
    """Expressions and breasts of one PMX (as the 10-06 / 10-17 / 11-14 runs did by hand: post.sh)."""
    if not run.args.dry_run and not os.path.isfile(pmx):
        return {"pmx": pmx, "error": "missing"}
    out = {"pmx": os.path.basename(pmx), "face": face_morphs(run, pmx)}
    base = pmx[:-4]
    swings = run.args.dry_run or has_bust(pmx)
    if variant:
        if os.path.isfile(base + "_bustB.pmx"):
            out["face_bustB"] = face_morphs(run, base + "_bustB.pmx")
        out["bust"] = "the body's (kept)" if swings else add_bust(run, pmx)
    elif swings:
        code, _ = run.call([sys.executable, os.path.join(SCRIPTS, "mmd_physics", "tune_bust_pmx.py"), pmx,
                            base + "_bustB.pmx"], "bustB_%s.log" % os.path.basename(base))
        out["bust"] = "the exporter's + _bustB" if not code else "BUSTB FAILED"
    else:
        out["bust"] = add_bust(run, pmx)
    return out


def follow_cups(run, full_pmx):
    out = {}
    for f in (full_pmx, full_pmx[:-4] + "_bustB.pmx"):
        if not run.args.dry_run and not os.path.isfile(f):
            continue
        code, text = run.call([sys.executable, os.path.join(HERE, "pmx_body_follows_cups.py"), f, f[:-4] + "__f.pmx"],
                              "cups_%s.log" % os.path.basename(f)[:-4])
        if code:
            out[os.path.basename(f)] = "FAILED: " + (text.strip().splitlines() or [""])[-1][:160]
        else:
            if not run.args.dry_run:
                shutil.move(f[:-4] + "__f.pmx", f)
            out[os.path.basename(f)] = "ok"
    return out


def ensure_nude_base(run, letter):
    """D:\\roe_exports\\nude_materials\\pc_<letter>01_nk_bs.blend with its game materials (the donor of _nude / _full)."""
    stem = "pc_%s01_nk_bs" % letter
    dst = os.path.join(run.args.exports, "nude_materials", stem + ".blend")
    if os.path.isfile(dst):
        return {"nude_base": stem, "state": "on D:"}
    src = os.path.join(hq.ARCHIVE, hq.NAMES.get(letter, letter), "blend", stem, stem + ".blend")
    if not os.path.isfile(src):
        return {"nude_base": stem, "error": "not on D: nor E: (%s) - make it: extract_character.ps1 nude:%s01" % (src, letter)}
    if not run.args.dry_run:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    code, text = run.call([sys.executable, os.path.join(HERE, "export_hq.py"), stem, "--formats", "blend"],
                          "nude_base.log")
    return {"nude_base": stem, "state": "copied from E:, game materials %s" % ("ok" if not code else "FAILED")}


def export_model(cid, keys, args):
    run = Run(keys[0] if len(keys) == 1 else cid, args)
    res = run.result
    res.update(kind="model", id=cid, keys=keys)
    print("== %s (%s %s): %s" % (cid, hq.NAMES.get(cid[0], "?"), cid[1:], ", ".join(keys)), flush=True)
    if run.step("extract"):
        code, text = run.call(POWERSHELL + [os.path.join(HERE, "extract_character.ps1"), cid, "-ExportTextures"],
                              "extract.log")
        res["steps"]["extract"] = "ok" if not code else "FAILED (exit %d)" % code
        if code:
            return res
    if run.step("export"):
        code, text = run.call(POWERSHELL + [os.path.join(HERE, "export_character_models.ps1"), "-Only", cid,
                                            "-Format", "blend,pmx,xps", "-Force"], "export.log")
        summary = re.findall(r"Complete:.*", text)
        res["steps"]["export"] = (summary[-1].strip() if summary else "ok") if not code else "FAILED (exit %d)" % code
        if code:
            return res
    pmx_of = lambda key, v="": os.path.join(args.exports, cid, "blend", "pmx", "pc_%s_hd%s" % (key, v),
                                            "pc_%s_hd%s.pmx" % (key, v))
    if run.step("post"):
        res["steps"]["post"] = [post_pmx(run, pmx_of(k), False) for k in keys]
    if not args.no_nude:
        if run.step("nude"):
            res["steps"]["nude"] = ensure_nude_base(run, cid[0])
            if res["steps"]["nude"].get("error"):
                return res
        if run.step("complete"):
            res["steps"]["complete"] = {}
            for key in keys:
                code, text = run.call([sys.executable, os.path.join(HERE, "complete_nude.py"), key],
                                      "complete_%s.log" % key)
                data = hq.tagged(text, "ROE_COMPLETE") if text else None
                res["steps"]["complete"][key] = "ok" if not code else "FAILED (exit %d)" % code
                if data and data.get("failed"):
                    res["steps"]["complete"][key] = "FAILED: %s" % data["failed"]
        if run.step("variants"):
            res["steps"]["variants"] = {}
            for key in keys:
                res["steps"]["variants"][key] = [post_pmx(run, pmx_of(key, "_" + v), True) for v in ("nude", "full")]
                res["steps"]["variants"][key].append(follow_cups(run, pmx_of(key, "_full")))
    stems = ["pc_%s_hd" % k for k in keys] + ([] if args.no_nude else
                                             ["pc_%s_hd_%s" % (k, v) for k in keys for v in ("nude", "full")])
    cards = list(keys) + ([] if args.no_nude else ["%s_hd_nude" % k for k in keys])
    if not args.no_archive and run.step("archive"):
        res["steps"]["archive"] = archive(run, stems, cards)
    res["stems"] = stems
    run.save()
    return res


def export_suit(cid, suit, args):
    run = Run("%s_%s" % (cid, suit), args)
    res = run.result
    res.update(kind="suit", id=cid, suit=suit)
    print("== %s:%s (%s)" % (cid, suit, hq.NAMES.get(cid[0], "?")), flush=True)
    base_fbx = glob.glob(os.path.join(args.exports, cid, "pc_%s_nk*" % cid, "FBX_GameObjects", "*", "*.fbx"))
    if run.step("extract") and not base_fbx:      # the base body the suit sits on
        code, _ = run.call(POWERSHELL + [os.path.join(HERE, "extract_character.ps1"), cid, "-ExportTextures"],
                           "extract.log")
        res["steps"]["extract"] = "ok" if not code else "FAILED (exit %d)" % code
        if code:
            return res
    if run.step("export"):
        code, text = run.call([sys.executable, os.path.join(HERE, "export_hq.py"), "%s:%s" % (cid, suit)],
                              "export_hq.log")
        data = hq.tagged(text, "ROE_EXPORT_HQ") if text else None
        res["steps"]["export"] = data or ("ok" if not code else "FAILED (exit %d)" % code)
        if code or (data and data.get("failed")):
            run.save()
            return res
    stem = "pc_%s_%s" % (cid, suit)
    if not args.no_archive and run.step("archive"):
        res["steps"]["archive"] = archive(run, [stem], ["%s_%s" % (cid, suit)])
    res["stems"] = [stem]
    run.save()
    return res


def archive(run, stems, cards):
    """Gallery cards for these models only (a page built from all of D: would also take the nude bases there, which
    stay off E:), then these stems to E:, then every gallery link checked."""
    out = {}
    code, _ = run.call([sys.executable, os.path.join(HERE, "html", "make_gallery.py"), "--only", ",".join(cards),
                        "--thumb-dir", THUMBS], "gallery.log")
    out["gallery"] = "ok" if not code else "FAILED"
    code, text = run.call([sys.executable, os.path.join(SCRIPTS, "archive", "archive_exports.py"), "roe", "--only"]
                          + stems, "archive.log")
    check = re.search(r"self-check:\s*(\d+)/(\d+) OK", text)
    out["archive"] = ("self-check %s/%s OK" % check.groups() if check and not code else
                      ("dry" if run.args.dry_run else "check %s" % os.path.join(run.logs, "archive.log")))
    if not run.args.dry_run:
        with open(os.path.join(HERE, "html", "index.html"), encoding="utf-8") as fh:
            links = set(re.findall(r'file:///([^"\'<> ]+)', fh.read()))
        out["gallery_links"] = len(links)
        out["missing_links"] = [urllib.parse.unquote(l) for l in links
                                if not os.path.exists(urllib.parse.unquote(l))][:20]
    return out


def detach(argv, exports):
    os.makedirs(os.path.join(exports, "_new_runs"), exist_ok=True)
    log = os.path.join(exports, "_new_runs", "detached_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
    flags = 0x00000008 | 0x00000200                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + argv, stdout=fh,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    print("running as pid %d, log: %s" % (proc.pid, log))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="id (i05), key (i05_outfit1), <id>:<suit> (f01:oni) or name (Sera 5)")
    ap.add_argument("--list", action="store_true", help="what the game has and E: lacks")
    ap.add_argument("--no-nude", action="store_true", help="models: no _nude / _full")
    ap.add_argument("--no-archive", action="store_true", help="leave everything on D: (no E:, no gallery)")
    ap.add_argument("--from", dest="start", choices=STEPS, default=STEPS[0], help="go on from this step")
    ap.add_argument("--dry-run", action="store_true", help="print the steps only")
    ap.add_argument("--detach", action="store_true", help="run in a process of its own, output to a log")
    ap.add_argument("--exports", default=hq.EXPORTS)
    ap.add_argument("--game", default=export_suits.GAME)
    args = ap.parse_args()
    if args.list:
        list_new(args.game)
        return
    if not args.names:
        ap.error("name a model or suit, or --list")
    if args.detach:
        detach([a for a in sys.argv[1:] if a != "--detach"], args.exports)
        return
    names = suit_bundle.bundle_names(args.game)
    keys, suits = armor_keys(names), set(export_suits.list_suits(args.game))
    jobs = [resolve(n, keys, suits) for n in args.names]          # all names first: a typo stops before any work
    results = []
    for job in jobs:
        res = export_model(job[1], job[2], args) if job[0] == "model" else export_suit(job[1], job[2], args)
        results.append(res)
        print("   -> %s" % json.dumps(res["steps"], ensure_ascii=False)[:600], flush=True)
    print("ROE_EXPORT_NEW=" + json.dumps(results, ensure_ascii=True))


if __name__ == "__main__":
    main()
