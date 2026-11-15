"""Wait (read-only) until a not-yet-seen file of deps.json shows up in E:\\Downloads\\eve_mod_download or E:\\Downloads,
matched by mod id in the name plus the exact Nexus byte size, and its size has been stable for 15 s; print it and
exit (so the caller is woken).  Files already reported in deps_seen.json are skipped.  Gives up after --hours."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTS = [r"E:\Downloads\eve_mod_download", r"E:\Downloads"]
deps = json.load(open(os.path.join(HERE, "deps.json")))
seen_path = r"D:\stellarblade_exports\mods\deps_seen.json"
seen = json.load(open(seen_path)) if os.path.isfile(seen_path) else {}
hours = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 6.0
end = time.time() + hours * 3600


def scan():
    hits = []
    for root in ROOTS:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            if not os.path.isfile(p):
                continue
            size = os.path.getsize(p)
            for d in deps:
                if d["name"] in seen:
                    continue
                if size == d["size"] and str(d["mod"]) in n:
                    hits.append((d, p))
    return hits


while time.time() < end:
    hits = scan()
    if hits:
        time.sleep(15)
        stable = [(d, p) for d, p in hits if os.path.isfile(p) and os.path.getsize(p) == d["size"]]
        if stable:
            for d, p in stable:
                seen[d["name"]] = p
                print("ARRIVED #%d %s -> %s" % (d["mod"], d["name"], p), flush=True)
            json.dump(seen, open(seen_path, "w"), indent=1)
            left = [d["name"] for d in deps if d["name"] not in seen]
            print("STILL MISSING: %s" % (", ".join(left) or "none"), flush=True)
            sys.exit(0)
    time.sleep(20)
print("TIMEOUT; missing: %s" % ", ".join(d["name"] for d in deps if d["name"] not in seen))
