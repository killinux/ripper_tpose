"""Index of the game materials in every archived Stellar Blade .blend (names only, via libraries.load; nothing is
opened or saved): material name -> the .blend files holding it (Eve's packages first).
    blender -b --factory-startup --python material_index.py -- <out.json>"""
import glob
import json
import os
import sys

import bpy

ROOT = r"E:\game_export\StellarBlade"
out_path = sys.argv[sys.argv.index("--") + 1]
blends = sorted(glob.glob(os.path.join(ROOT, "Eve", "blend", "*", "*.blend")))
blends += sorted(b for b in glob.glob(os.path.join(ROOT, "*", "blend", "*", "*.blend")) if b not in blends)
index = {}
for b in blends:
    if b.endswith("_HQ.blend") or os.sep + "Mod_" in b or os.sep + "_" in b.replace(ROOT, ""):
        continue                       # game packages only: no HQ copies, no mod packages, no _meta
    try:
        with bpy.data.libraries.load(b) as (src, _dst):
            names = list(src.materials)
    except Exception as e:  # noqa: BLE001
        print("skip", b, e)
        continue
    for n in names:
        index.setdefault(n, []).append(b)
json.dump(index, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("MATERIAL_INDEX %d names from %d blends -> %s" % (len(index), len(blends), out_path))
