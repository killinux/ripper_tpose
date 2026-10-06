"""The blueprint packages a level's cells use as component templates, as container paths for CUE4Parse's -p
(level_extract.py needs their JSON: components of blueprint actors keep only what differs from the template).

    python list_templates.py <cells json root> [--utoc E:\\tools\\vindictus\\_download\\utoc_files.txt] > tpl_container.txt

Template object paths are matched to the container's file list without regard to case (the level writes
/Game/.../BluePrint/..., the container has Blueprint); paths the container lacks are reported on stderr."""
import argparse
import glob
import json
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("cells", help="the CUE4Parse JSON of the level's .umap cells")
ap.add_argument("--utoc", default=r"E:\tools\vindictus\_download\utoc_files.txt",
                help="the container's file list (one package path per line)")
args = ap.parse_args()
sys.stdout.reconfigure(newline="\n", encoding="utf-8")         # read back line by line in Bash

templates = set()
for path in glob.glob(os.path.join(args.cells, "**", "*.json"), recursive=True):
    for export in json.load(open(path, encoding="utf-8-sig")):        # CUE4Parse writes a BOM
        t = export.get("Template") if isinstance(export, dict) else None
        if t and "/_Generated_/" not in t["ObjectPath"] and not t["ObjectPath"].startswith("/Script/"):
            templates.add(t["ObjectPath"].rsplit(".", 1)[0])

container = {}
for line in open(args.utoc, encoding="utf-8"):
    p = line.strip().replace("\\", "/")
    if "Vindictus/Content/" in p:
        p = p[p.index("Vindictus/Content/"):]
        container[p.lower()] = p

missing = 0
for t in sorted(templates):
    base = "Vindictus/Content/" + t[len("/Game/"):]
    hit = container.get((base + ".uasset").lower()) or container.get((base + ".umap").lower())
    if hit:
        print(hit)
    else:
        missing += 1
        print("not in the container: " + base, file=sys.stderr)
print("%d templates, %d not found" % (len(templates), missing), file=sys.stderr)
