"""Per CNS zip: every outfit entry -> its variant names and the DISTINCT meshes behind them (variants that share a mesh
only differ by parameters / hidden materials).  Lenient JSON (CNS files often have trailing commas)."""
import json
import os
import re
import sys
import zipfile

root = sys.argv[1]
out = {}


def lenient(raw):
    raw = re.sub(r",\s*([\]}])", r"\1", raw)          # trailing commas
    return json.loads(raw)


for name in sorted(os.listdir(root)):
    if not name.lower().endswith(".zip"):
        continue
    with zipfile.ZipFile(os.path.join(root, name)) as z:
        for m in z.namelist():
            if not m.lower().endswith(".json"):
                continue
            doc = lenient(z.read(m).decode("utf-8-sig", "replace"))
            print("==", name)
            for fit in doc if isinstance(doc, list) else [doc]:
                names = fit.get("OutfitNames") or []
                meshes = list(fit.get("OutfitPaths") or [])
                datas = fit.get("OutfitDatas") or []
                for d in datas:
                    meshes.append(d.get("Mesh"))
                hidden = [d.get("HiddenMats") for d in datas]
                distinct = []
                for x in meshes:
                    if x not in distinct:
                        distinct.append(x)
                ut = fit.get("UserConfigs") or {}
                print("  fit %-40s %r  names %d  meshes %d distinct %d  toggles %d  textureOptions %d  shapeKeys %d" % (
                    fit.get("UniqueFitID"), fit.get("DisplayName"), len(names), len(meshes), len(distinct),
                    len(ut.get("MaterialToggles") or []), len(ut.get("TextureOptions") or []),
                    len(ut.get("ShapeKeys") or [])))
                for i, x in enumerate(distinct):
                    users = [names[k] if k < len(names) else "?" for k, y in enumerate(meshes) if y == x]
                    print("     mesh %d %s  <- %s" % (i + 1, (x or "")[-90:], "; ".join(users)[:220]))
                if any(hidden):
                    print("     hidden mats per variant:", hidden)
                for t in (ut.get("MaterialToggles") or [])[:60]:
                    print("     toggle mat %-3s %-5s %s" % (t.get("MaterialIndex"), t.get("Value"), t.get("DisplayName")))
                for t in (ut.get("TextureOptions") or []):
                    print("     texopt %s: %s" % (t.get("DisplayName"), ", ".join(t.get("OptionNames") or [])[:200]))
                for t in (ut.get("ShapeKeys") or []):
                    print("     shapekey", json.dumps(t, ensure_ascii=False)[:160])
                out.setdefault(name, []).append({"fit": fit.get("UniqueFitID"), "display": fit.get("DisplayName"),
                                                 "names": names, "meshes": meshes, "distinct": distinct,
                                                 "toggles": ut.get("MaterialToggles") or [],
                                                 "texture_options": ut.get("TextureOptions") or [],
                                                 "shape_keys": ut.get("ShapeKeys") or [], "hidden": hidden})
json.dump(out, open(r"D:\stellarblade_exports\mods\cns_meshes.json", "w", encoding="utf-8"), ensure_ascii=False,
          indent=1)
