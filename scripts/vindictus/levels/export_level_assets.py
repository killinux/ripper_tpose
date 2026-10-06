"""UE Viewer export of what a level needs: every mesh package in placements.json (PSKX + materials + textures) and
the level cells that hold landscape components (height / weight maps, landscape material instances).

  python export_level_assets.py <placements.json> <out dir> [--lanes 3] [--cells-only] [--meshes-only]

One package per UE Viewer call, a few calls at a time at below-normal priority; a package whose PSKX already exists
is skipped (rerun = resume).  The out dir must be a short path (MAX_PATH) - the junction C:\\...\\Temp\\vdfs."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import time

UMODEL = r"E:\tools\umodel_specific\materials\umodel_materials_ue5.exe"
PAKS = r"E:\tools\vindictus\Vindictus\Content\Paks"
KEYFILE = r"E:\tools\vindictus\_download\aes_key.txt"
LIST = r"E:\tools\vindictus\_download\utoc_files.txt"
BELOW_NORMAL = 0x4000

ap = argparse.ArgumentParser()
ap.add_argument("placements")
ap.add_argument("out")
ap.add_argument("--lanes", type=int, default=3)
ap.add_argument("--cells-only", action="store_true")
ap.add_argument("--meshes-only", action="store_true")
args = ap.parse_args()

container = {}
for line in open(LIST, encoding="utf-8"):
    line = line.strip().replace("\\", "/")
    if "Vindictus/Content/" in line:
        c = line[line.index("Vindictus/Content/") + len("Vindictus/Content/"):]
        container[c.rsplit(".", 1)[0].lower()] = c.rsplit(".", 1)[0]

d = json.load(open(args.placements, encoding="utf-8"))
jobs = []
if not args.cells_only:
    for mesh in sorted({it["mesh"] for it in d["items"]}):
        rel = container.get(mesh[len("/Game/"):].lower())
        if rel is None:
            print("not in the container:", mesh)
            continue
        if os.path.exists(os.path.join(args.out, rel + ".pskx")) or os.path.exists(os.path.join(args.out, rel + ".psk")):
            continue
        jobs.append(rel)
if not args.meshes_only:
    level_dir = None
    for cell in sorted({l["cell"] for l in d["landscape"]}):
        rel = next((v for k, v in container.items() if k.endswith("/_generated_/" + cell.lower())), None)
        if rel and not os.path.exists(os.path.join(args.out, rel + ".done")):
            jobs.append(rel)
print(len(jobs), "packages to export")


def run(rel):
    t = time.time()
    r = subprocess.run([UMODEL, "-game=ue5.3", "-path=" + PAKS, "-aes=@" + KEYFILE, "-export", "-png", "-nooverwrite",
                        "-out=" + args.out, rel], capture_output=True, text=True, errors="replace",
                       creationflags=BELOW_NORMAL)
    tail = [l for l in r.stdout.splitlines() if l.startswith("Exported") or "rror" in l][-2:]
    if "/_Generated_/" in rel and r.returncode == 0:
        os.makedirs(os.path.dirname(os.path.join(args.out, rel)), exist_ok=True)
        open(os.path.join(args.out, rel + ".done"), "w").write(r.stdout)
    return rel, r.returncode, time.time() - t, tail


done = 0
with concurrent.futures.ThreadPoolExecutor(args.lanes) as pool:
    for rel, code, dt, tail in pool.map(run, jobs):
        done += 1
        print("%3d/%d %5.1fs rc=%d %s %s" % (done, len(jobs), dt, code, rel.rsplit("/", 1)[-1], " | ".join(tail)),
              flush=True)
