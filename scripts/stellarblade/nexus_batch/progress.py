"""Print one line per look whenever it finishes a step that matters (preview / hq / addon) or a STEP_ERROR shows up in its
batch log; exit when every look named finished `--until` (default preview), or after --minutes."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from looks import BY_LABEL, LOOKS  # noqa: E402
from run_look import WORK  # noqa: E402

a = sys.argv[1:]
until = a[a.index("--until") + 1] if "--until" in a else "preview"
minutes = float(a[a.index("--minutes") + 1]) if "--minutes" in a else 28
names = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--until", "--minutes"))]
labels = [lk["label"] for lk in LOOKS if not lk.get("needs")] if names in ([], ["ALL_READY"]) else names
seen, errs = {}, {}
end = time.time() + minutes * 60
while time.time() < end:
    left = 0
    for lb in labels:
        lk = BY_LABEL[lb]
        lw = WORK / lk["mod"] / "looks" / lb
        try:
            st = json.load(open(lw / "status.json", encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        for step in ("pmx", "preview", "hq", "addon"):
            if step in st and (lb, step) not in seen:
                seen[(lb, step)] = 1
                extra = ""
                if step == "hq":
                    extra = " HQ blend %s" % ("ok" if (st["hq"] or {}).get("hq_blend") else "MISSING")
                if step == "addon":
                    extra = " " + next((x for x in (st["addon"] or {}).get("lines", []) if x.startswith("upgraded")), "?")[:90]
                print("%s %s done%s" % (lb, step, extra), flush=True)
        try:
            log = open(lw / "batch.log", encoding="utf-8", errors="replace").read()
            n = log.count("STEP_ERROR")
            if n > errs.get(lb, 0):
                errs[lb] = n
                print("%s ERROR %s" % (lb, log[log.rfind("STEP_ERROR"):].splitlines()[0][:200]), flush=True)
        except OSError:
            pass
        if until not in st:
            left += 1
    if left == 0:
        print("ALL %d looks have %s" % (len(labels), until), flush=True)
        break
    time.sleep(20)
