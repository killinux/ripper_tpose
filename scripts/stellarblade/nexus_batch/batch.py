"""Run run_look.py for many looks in parallel; looks that share a staging key get their stage + umodel steps one at a
time first.

    python -I -X utf8 batch.py --jobs 3 --steps stage,umodel,cue,swap <label|mod|ALL_READY> ...
"""
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from looks import BY_LABEL, LOOKS  # noqa: E402
from run_look import WORK, stage_key  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def pick(names):
    out = []
    for n in names:
        if n == "ALL_READY":
            out += [lk["label"] for lk in LOOKS if not lk.get("needs")]
        elif n in BY_LABEL:
            out.append(n)
        else:
            out += [lk["label"] for lk in LOOKS if lk["mod"] == n]
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


def one(label, steps, redo):
    cmd = [sys.executable, "-I", "-X", "utf8", os.path.join(HERE, "run_look.py"), label, "--steps", steps]
    if redo:
        cmd += ["--redo", redo]
    lk = BY_LABEL[label]
    log = WORK / lk["mod"] / "looks" / label / "batch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    t = time.time()
    with open(log, "ab") as fh:
        fh.write(("\n==== %s %s\n" % (time.strftime("%H:%M:%S"), " ".join(cmd[4:]))).encode())
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
    tail = open(log, encoding="utf-8", errors="replace").read().strip().splitlines()[-1:]
    return label, rc, time.time() - t, tail[0] if tail else ""


def main():
    a = sys.argv[1:]
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 3
    steps = a[a.index("--steps") + 1] if "--steps" in a else "stage,umodel,cue,swap,fill,texfix,cloth,hair,xps,pmx,preview"
    redo = a[a.index("--redo") + 1] if "--redo" in a else ""
    names = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--jobs", "--steps", "--redo"))]
    labels = pick(names)
    print("%d looks, %d jobs, steps %s" % (len(labels), jobs, steps), flush=True)
    # one look per staging key does stage + umodel first, serially per key (they share the export folder)
    first = {}
    for lb in labels:
        lk = BY_LABEL[lb]
        first.setdefault((lk["mod"], stage_key(lk["stage"])), lb)
    pre = [s for s in ("stage", "umodel") if s in steps.split(",")]
    if pre:
        with cf.ThreadPoolExecutor(jobs) as ex:
            for lb, rc, dt, tail in ex.map(lambda x: one(x, ",".join(pre), redo), first.values()):
                print("  pre %-46s rc %s %5.0f s  %s" % (lb, rc, dt, tail[:150]), flush=True)
    results = []
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = [ex.submit(one, lb, steps, redo) for lb in labels]
        for f in cf.as_completed(futs):
            lb, rc, dt, tail = f.result()
            results.append((lb, rc))
            print("  %-46s rc %s %5.0f s  %s" % (lb, rc, dt, tail[:160]), flush=True)
    bad = [lb for lb, rc in results if rc != 0]
    print("DONE %d ok, %d failed%s" % (len(results) - len(bad), len(bad), (": " + ", ".join(bad)) if bad else ""))


if __name__ == "__main__":
    main()
