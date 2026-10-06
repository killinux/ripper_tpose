"""Survey every World Partition cell of a level: export classes (from UE Viewer's -list) and, per class, which
unversioned property indices occur how often.  -> cells_<level>.json + a summary.
  python survey_cells.py S1_Northruin_01"""
import collections
import json
import os
import re
import subprocess
import sys

import zen53

UMODEL = r"E:\tools\umodel_specific\materials\umodel_materials_ue5.exe"
LIST = r"E:\tools\vindictus\_download\utoc_files.txt"
level = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
cells = sorted({re.sub(r"^.*?/Vindictus/Content/", "Vindictus/Content/", l.strip())
                for l in open(LIST, encoding="utf-8") if "/%s/" % level in l and l.strip().endswith(".umap")})
print(len(cells), "packages")
per_class = collections.defaultdict(lambda: {"exports": 0, "indices": collections.Counter(), "sizes": []})
out = {}
for path in cells:
    pkg_path = path[len("Vindictus/Content/"):-len(".umap")]
    r = subprocess.run([UMODEL, "-game=ue5.3", "-path=E:/tools/vindictus/Vindictus/Content/Paks",
                        "-aes=@E:/tools/vindictus/_download/aes_key.txt", "-list", pkg_path],
                       capture_output=True, text=True, errors="replace")
    classes = {}
    for line in r.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)\s+(\S+)", line)
        if m:
            classes[int(m.group(1))] = (m.group(2), m.group(3))
    buf = zen53.read_package(path)
    pkg = zen53.parse(buf)
    rows = []
    for e in pkg["exports"]:
        cls = classes.get(e["index"], ("?", e["name"]))[0]
        data = buf[e["data_offset"]:e["data_offset"] + e["size"]]
        try:
            hdr, vstart = zen53.unversioned_header(data)
        except Exception:                          # noqa: BLE001
            hdr, vstart = [], -1
        idx = [i for i, has in hdr if has]
        rows.append({"index": e["index"], "name": e["name"], "class": cls, "size": e["size"], "props": idx,
                     "zero": [i for i, has in hdr if not has], "values_from": vstart})
        pc = per_class[cls]
        pc["exports"] += 1
        pc["indices"].update(idx)
        pc["sizes"].append(e["size"])
    out[path] = rows
json.dump(out, open(os.path.join(HERE, "cells_%s.json" % level), "w", encoding="utf-8"), indent=1)
for cls, pc in sorted(per_class.items(), key=lambda kv: -kv[1]["exports"]):
    common = ", ".join("%d:%d" % (i, n) for i, n in sorted(pc["indices"].items()))
    print("%-44s %5d exports  sizes %d..%d  indices %s" % (cls, pc["exports"], min(pc["sizes"]), max(pc["sizes"]), common[:300]))
