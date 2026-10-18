r"""Build every look of npc_looks.json with build_npc_blend.py (Blender 3.6, --nude): <root>\looks\<name>\<name>.blend +
previews + report.json.

    python build_npc_looks.py [--only Raven,Lily_01] [--lanes 3] [--force]"""
import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"


def build(look, root, force):
    out = os.path.join(root, "looks", look["name"])
    if not force and os.path.exists(os.path.join(out, "report.json")) and os.path.exists(os.path.join(out, look["name"] + ".blend")):
        return look["name"], "kept"
    parts = ",".join("SB/Content/" + p for p in look["parts"])
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_npc_blend.py"), "--",
                        "--root", root, "--name", look["name"], "--parts", parts, "--out", out, "--nude"],
                       capture_output=True, text=True, errors="replace")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "build.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    line = next((l for l in r.stdout.splitlines() if l.startswith("SB_NPC_REPORT=")), None)
    return look["name"], line[len("SB_NPC_REPORT="):] if line else "FAILED (see build.log)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\stellarblade_npc")
    ap.add_argument("--only", default="")
    ap.add_argument("--lanes", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    o = ap.parse_args()
    looks = json.load(open(os.path.join(HERE, "npc_looks.json"), encoding="utf-8"))["looks"]
    only = {s for s in o.only.split(",") if s}
    looks = [l for l in looks if not only or l["name"] in only]
    with ThreadPoolExecutor(o.lanes) as pool:
        for name, result in pool.map(lambda l: build(l, o.root, o.force), looks):
            print(f"{name:16s} {result}", flush=True)


if __name__ == "__main__":
    main()
