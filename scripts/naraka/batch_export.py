"""Export many NARAKA: BLADEPOINT outfits in parallel.

    python batch_export.py --sex f --out E:\\game_export\\NARAKA     # every female outfit (495)
    python batch_export.py --out E:\\game_export\\NARAKA              # all 834
    python batch_export.py --family ch_f_ming_haikou --jobs 4        # one family
    python batch_export.py --sex f --dry-run                         # show the chunks only

The outfits are cut into chunks of one family (at most --chunk outfits each) and
every chunk runs as its own export_model.py process, --jobs at a time. One process
keeps every bundle it has opened (an outfit pulls ~200), so its memory grows with
the number of outfits it exports: a chunk of 12 peaks around 2.2 GB. A new chunk only
starts while more than --reserve GB of RAM is free. (495 female outfits, 8 jobs: 26 min.)

Outfits whose .blend already exists are skipped, so after a crash just run the same
command again; failed outfits get one retry in a fresh process at the end.
Logs: <out>\\_logs\\<family>_<n>.log, summary: <out>\\_logs\\batch_summary.json,
list page: <out>\\_list\\index.html (written once at the end).
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import naraka_catalog  # noqa: E402
import naraka_manifest  # noqa: E402
from list_models import OUT, export_dir, write_html  # noqa: E402
from naraka_env import STREAMING  # noqa: E402

try:
    import psutil
except ImportError:                       # no memory guard without psutil
    psutil = None


def free_gb():
    return psutil.virtual_memory().available / 2 ** 30 if psutil else float("inf")


def chunks(items, size):
    """[(family, n, [items])], biggest families first, a family's chunks of equal size."""
    families = {}
    for item in items:
        families.setdefault(item.family, []).append(item)
    out = []
    for family, group in sorted(families.items(), key=lambda kv: -len(kv[1])):
        count = -(-len(group) // size)
        step = -(-len(group) // count)
        for k in range(count):
            out.append((family, k + 1, group[k * step:(k + 1) * step]))
    return out


def outcome(item, out):
    """'ok' + export.json facts when the .blend exists, else 'failed'."""
    folder = export_dir(item, out)
    if not os.path.isfile(os.path.join(folder, item.name + ".blend")):
        return {"status": "failed"}
    info = {"status": "ok"}
    try:
        with open(os.path.join(folder, "export.json"), encoding="utf-8") as f:
            data = json.load(f)
        info.update(unresolved=data.get("unresolved_bones", 0),
                    seconds=round(data.get("extract_s", 0) + data.get("blender_s", 0), 1))
    except (OSError, ValueError):
        pass
    return info


def failure_reason(log_path, name, offset=0):
    """The FAILED line printed under an outfit's heading (in this run's part of the log)."""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            lines = f.read().splitlines()
    except OSError:
        return "no log"
    inside = False
    for line in lines:
        if line.startswith("["):
            inside = line.split("] ", 1)[-1].startswith(name + " ")
        elif inside and line.strip().startswith("FAILED"):
            return line.strip()
    return "process ended before this outfit finished (see %s)" % os.path.basename(log_path)


def run(todo, args, passthrough, label="", prefix=""):
    """Run the chunks, --jobs at a time; returns {name: outcome}. Logs are appended
    to, so a second run of the same command keeps the first run's log."""
    logs = os.path.join(args.out, "_logs")
    os.makedirs(logs, exist_ok=True)
    pending = chunks(todo, args.chunk)
    total_chunks, total = len(pending), len(todo)
    running, results = [], {}
    t0 = last_start = time.time()
    try:
        while pending or running:
            for job in running[:]:
                if job["proc"].poll() is None:
                    continue
                running.remove(job)
                job["log"].close()
                ok = 0
                for item in job["items"]:
                    res = outcome(item, args.out)
                    res.update(family=item.family, chunk=job["tag"])
                    if res["status"] != "ok":
                        res["reason"] = failure_reason(job["log_path"], item.name, job["offset"])
                    else:
                        ok += 1
                    results[item.name] = res
                done = len(results)
                good = sum(1 for r in results.values() if r["status"] == "ok")
                elapsed = time.time() - t0
                eta = elapsed / done * (total - done) if done else 0
                print("%s[%d/%d chunks] %s: %d/%d ok in %.0fs | outfits %d/%d (%d failed) | "
                      "%.0f min elapsed, ~%.0f min left | %.0f GB free" % (
                          label, total_chunks - len(pending) - len(running), total_chunks, job["tag"], ok,
                          len(job["items"]), time.time() - job["t0"], done, total, done - good,
                          elapsed / 60, eta / 60, free_gb()), flush=True)
            can_start = pending and len(running) < args.jobs and time.time() - last_start > args.stagger
            if can_start and (not running or free_gb() > args.reserve):
                family, n, items = pending.pop(0)
                tag = "%s%s_%d" % (prefix, family, n)
                log_path = os.path.join(logs, tag + ".log")
                cmd = [sys.executable, "-u", os.path.join(HERE, "export_model.py"), "--out", args.out,
                       "--no-html", "--game-data", args.game_data] + passthrough
                for item in items:
                    cmd += ["--outfit", item.name]
                offset = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
                log = open(log_path, "a", encoding="utf-8", errors="replace")
                log.write("=== %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                log.flush()
                proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                running.append({"proc": proc, "items": items, "tag": tag, "log": log, "offset": offset,
                                "log_path": log_path, "t0": time.time()})
                last_start = time.time()
                print("%sstart %s (%d outfits), %d running" % (label, tag, len(items), len(running)), flush=True)
                continue
            time.sleep(1)
    except KeyboardInterrupt:
        for job in running:
            job["proc"].terminate()
        raise
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--sex", choices=("f", "m"))
    ap.add_argument("--family", action="append", default=[], help="only these families (repeatable)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=12, help="outfits per process")
    ap.add_argument("--reserve", type=float, default=6.0, help="GB of free RAM needed to start a chunk")
    ap.add_argument("--stagger", type=float, default=3.0, help="seconds between two starts")
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--fbx", action="store_true")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--keep-fx", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-export outfits that already have a .blend")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--game-data", default=STREAMING)
    args = ap.parse_args()

    catalog = naraka_catalog.build(naraka_manifest.read(args.game_data))
    wanted = [i for i in catalog if i.group == "outfit" and not i.ui
              and (not args.sex or i.sex == args.sex) and (not args.family or i.family in args.family)]
    done = [] if args.force else [i for i in wanted
                                  if os.path.isfile(os.path.join(export_dir(i, args.out), i.name + ".blend"))]
    todo = [i for i in wanted if i not in done]
    plan = chunks(todo, args.chunk)
    print("%d outfits selected, %d already exported, %d to export in %d chunks, %d jobs -> %s" % (
        len(wanted), len(done), len(todo), len(plan), args.jobs, args.out), flush=True)
    if args.dry_run:
        for family, n, items in plan:
            print("  %s_%d: %s" % (family, n, " ".join(i.name for i in items)))
        return
    passthrough = [flag for flag, on in (("--fbx", args.fbx), ("--no-preview", args.no_preview),
                                         ("--keep-fx", args.keep_fx), ("--force", args.force)) if on]
    t0 = time.time()
    results = run(todo, args, passthrough) if todo else {}
    for attempt in range(args.retries):
        failed = [i for i in todo if results.get(i.name, {}).get("status") != "ok"]
        if not failed:
            break
        print("retrying %d failed outfits" % len(failed), flush=True)
        retry_args = argparse.Namespace(**vars(args))
        retry_args.chunk = 1
        results.update(run(failed, retry_args, [f for f in passthrough if f != "--force"],
                           label="retry %d: " % (attempt + 1), prefix="retry%d_" % (attempt + 1)))
    for item in done:
        results[item.name] = dict(outcome(item, args.out), family=item.family, chunk="earlier run")

    write_html(os.path.join(args.out, "_list", "index.html"), [i for i in catalog if not i.ui], args.out)
    ok = sorted(n for n, r in results.items() if r["status"] == "ok")
    failed = {n: r.get("reason", "") for n, r in results.items() if r["status"] != "ok"}
    unresolved = {n: r["unresolved"] for n, r in results.items() if r.get("unresolved")}
    summary = {"out": args.out, "sex": args.sex, "families": args.family or None,
               "selected": len(wanted), "ok": len(ok), "failed": failed, "unresolved_bones": unresolved,
               "minutes": round((time.time() - t0) / 60, 1), "outfits": results}
    with open(os.path.join(args.out, "_logs", "batch_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("done in %.0f min: %d ok, %d failed, %d with unresolved bones -> %s" % (
        summary["minutes"], len(ok), len(failed), len(unresolved), os.path.join(args.out, "_list", "index.html")))
    for name, reason in sorted(failed.items()):
        print("  FAILED %s: %s" % (name, reason))


if __name__ == "__main__":
    main()
