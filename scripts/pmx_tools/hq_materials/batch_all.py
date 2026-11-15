# -*- coding: utf-8 -*-
"""make_hq_materials over every PMX of the export archive - in the background, resumable, no MMD window.

    python batch_all.py [--root E:\\game_export] [--games EldenRing,Sekiro,...] [--skip-games RiseOfEros]
                        [--steps 1,2] [--dry-run] [--low-priority] [--limit N]

- Every *.pmx under <root>\\<Game>\\... except: folders starting with "_" at any depth (theme collections, sets
  other windows look after such as _18系列_ウィンク修正, the _raymmd output itself, _meta backups, _混搭
  experiments), our own outputs (*_材质.pmx, *_raymmd.pmx) and half-written *.tmp.
- One file at a time at normal priority (one Blender at a time keeps the machine usable), small games first.
- Ledger <root>\\_raymmd\\_batch\\ledger.jsonl: one line per finished file with make_hq_materials.VERSION; a rerun
  skips files already done by the same version, so a stopped batch just continues.  Errors are logged and retried
  on the next run.
- Progress lines: "[n/total] game | file | kinds | seconds" and BATCH_DONE=<json> at the end.
"""
import argparse
import ctypes
import glob
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv, sys.argv = sys.argv, sys.argv[:1]
import make_hq_materials as hq  # noqa: E402
sys.argv = _argv

OWN = ("_材质", "_raymmd")


def pmx_files(root, games=None, skip_games=()):
    out = []
    for g in sorted(os.listdir(root)):
        if g.startswith("_") or not os.path.isdir(os.path.join(root, g)):
            continue
        if games and g not in games:
            continue
        if g in skip_games:
            continue
        for p in sorted(glob.glob(os.path.join(root, g, "**", "*.pmx"), recursive=True)):
            stem = os.path.splitext(os.path.basename(p))[0]
            if stem.endswith(OWN) or p.endswith(".tmp"):
                continue
            # folders starting with "_" at any depth: collections of hard links (_合集), backups and caches (_meta),
            # the user's experiments (_混搭) - not models of the archive
            if any(part.startswith("_") for part in os.path.relpath(os.path.dirname(p), root).split(os.sep)):
                continue
            out.append((g, p))
    return out


def read_ledger(path):
    done = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("ok"):
                done[os.path.normcase(e["file"])] = e.get("version")
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=r"E:\game_export")
    ap.add_argument("--games", help="comma separated game folders (default: all)")
    ap.add_argument("--skip-games", default="")
    ap.add_argument("--steps", default="1,2")
    ap.add_argument("--dry-run", action="store_true", help="list what would be done")
    ap.add_argument("--low-priority", action="store_true",
                    help="below-normal priority (off by default: such a Blender starved behind another window's "
                         "render on 10-06 and looked hung)")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.low_priority and os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
    files = pmx_files(a.root, set(a.games.split(",")) if a.games else None,
                      set(x for x in a.skip_games.split(",") if x))
    ledger = os.path.join(a.root, "_raymmd", "_batch", "ledger.jsonl")
    done = read_ledger(ledger)
    todo = [(g, p) for g, p in files if done.get(os.path.normcase(p)) != hq.VERSION]
    size = {}
    for g, _p in files:
        size[g] = size.get(g, 0) + 1
    todo.sort(key=lambda gp: (size[gp[0]], gp[0], gp[1]))      # small games first: every game shows results early
    by_game = {}
    for g, _p in todo:
        by_game[g] = by_game.get(g, 0) + 1
    print("BATCH_PLAN=" + json.dumps({"pmx": len(files), "todo": len(todo), "done_before": len(files) - len(todo),
                                      "by_game": by_game, "version": hq.VERSION}, ensure_ascii=False), flush=True)
    if a.dry_run:
        return
    if a.limit:
        todo = todo[:a.limit]
    args, values = hq.parse_args(["--steps", a.steps])
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    ok = err = 0
    t_start = time.time()
    for k, (g, p) in enumerate(todo, 1):
        t0 = time.time()
        entry = {"file": p, "game": g, "version": hq.VERSION, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        try:
            r = hq.process(p, args, values)
            kinds = {}
            for m in r.get("materials", []):
                kinds[m["class"]] = kinds.get(m["class"], 0) + 1
            entry.update(ok=True, seconds=round(time.time() - t0, 1), blend=r.get("blend"), kinds=kinds,
                         raymmd_dir=r.get("raymmd_dir"), step1=r.get("pmx"),
                         no_sphere=sum(1 for n in r.get("step1", []) if n.get("no_sphere")))
            ok += 1
            line = ", ".join("%s %d" % kv for kv in sorted(kinds.items()))
        except Exception as exc:  # noqa: BLE001 - one broken model must not stop the batch
            entry.update(ok=False, seconds=round(time.time() - t0, 1), error=repr(exc),
                         trace=traceback.format_exc()[-1500:])
            err += 1
            line = "ERROR " + repr(exc)[:200]
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("[%d/%d] %s | %s | %s | %.0fs" % (k, len(todo), g, os.path.relpath(p, a.root), line,
                                                time.time() - t0), flush=True)
    print("BATCH_DONE=" + json.dumps({"ok": ok, "errors": err, "hours": round((time.time() - t_start) / 3600, 2),
                                      "ledger": ledger}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
