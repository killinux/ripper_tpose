"""List the models of CRISIS CORE -FINAL FANTASY VII- REUNION and whether they are exported yet.

Reads the package list straight from the game's IoStore containers through the CUE4Parse CLI (AES key
+ usmap, see ccff7r_common.py; the list is cached in <export-root>/_meta/packages.txt and refreshed when
the containers change).  A "model" is one skeletal mesh:

  named   Fair/Character/01_named/<folder>/Mesh/SK_CH_<folder>   Zack, Tifa, Aerith, Sephiroth ... (34)
  limit   Fair/Character/02_limit/...                             DMW summons: Cait Sith, Chocobo, Moogle
  npc     Fair/Character/03_mob/...                               town people, Shinra staff, troopers
  enemy   Fair/Character/04_enemy/...                             monsters, bosses, Genesis copies
  object  Fair/Object/<folder>/Mesh/SK_OB_<folder>                Buster Sword, props, vehicles

Every mesh has an "_SW" twin with the same geometry and cheaper *_Lite materials; it is shown as a flag
and export_model.py takes the full one unless told --sw.

Examples:
  python list_models.py                     # everything, grouped by category
  python list_models.py --category named    # the main cast only
  python list_models.py --find tifa zack*   # a few, by id / name / group (wildcards ok)
  python list_models.py --details           # + vertices, triangles, material slots, height (reads each mesh)
  python list_models.py --json              # machine-readable
Writes <export-root>/_meta/model_list.md and model_list.json when the whole list is shown.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import ccff7r_common as cc


def mesh_details(models: list[dict], root: str) -> None:
    """Vertex / triangle / slot counts and height, from the meshes' JSON (one CLI run for all of them)."""
    props = os.path.join(cc.work_dir(root), "props")
    need = [m["package"] for m in models if not os.path.isfile(cc.package_file(props, m["package"], ".json"))]
    if need:
        print("reading %d meshes ..." % len(need), file=sys.stderr, flush=True)
        cc.export_packages(need, props, fmt="json")
    for m in models:
        path = cc.package_file(props, m["package"], ".json")
        try:
            data = cc.load_json(path)
        except (OSError, ValueError):
            continue
        mesh = next((e for e in data if e.get("Type") == "SkeletalMesh"), None)
        if not mesh:
            continue
        lods = mesh.get("LODModels") or []
        if lods:
            m["vertices"] = lods[0].get("NumVertices")
            m["triangles"] = sum(s.get("NumTriangles", 0) for s in lods[0].get("Sections", []))
        m["lods"] = len(lods)
        m["slots"] = len(mesh.get("SkeletalMaterials") or [])
        ext = (mesh.get("ImportedBounds") or {}).get("BoxExtent") or {}
        if ext:
            m["height_cm"] = round(2 * ext.get("Z", 0.0), 1)


def fmt_row(m: dict, details: bool) -> str:
    name = m["name_en"] + (" " + m["name_zh"] if m["name_zh"] else "")
    cols = ["%-20s" % m["id"], "%-22s" % name, "%-18s" % m["group"],
            "%3d" % m["textures"], "%3d" % m["materials"], "%4d" % m["animations"]]
    if details:
        cols += ["%7s" % (m.get("vertices") or "-"), "%7s" % (m.get("triangles") or "-"),
                 "%3s" % (m.get("slots") or "-"), "%6s" % (m.get("height_cm") or "-")]
    cols.append("SW" if m["sw_package"] else "  ")
    cols.append("已导出" if m["exported"] else "")
    return "  ".join(cols)


def header(details: bool) -> str:
    cols = ["%-20s" % "id", "%-22s" % "name", "%-18s" % "group", "tex", "mat", "anim"]
    if details:
        cols += ["%7s" % "verts", "%7s" % "tris", "%3s" % "slt", "%6s" % "cm"]
    return "  ".join(cols + ["sw", "blend"])


def write_lists(models: list[dict], root: str, details: bool) -> None:
    meta = cc.meta_dir(root)
    os.makedirs(meta, exist_ok=True)
    with open(os.path.join(meta, "model_list.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(models, fh, ensure_ascii=False, indent=1)
    lines = ["# CRISIS CORE -FINAL FANTASY VII- REUNION 模型清单", "",
             "由 `scripts/ccff7r/list_models.py` 生成。导出：`python export_model.py <id>`，"
             "结果在 `%s\\<组>\\blend\\<id>\\`。" % root, ""]
    for cat in cc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        lines += ["## %s（%d）" % (cc.CATEGORY_ZH[cat], len(rows)), ""]
        head = "| id | 名字 | 组 | 贴图 | 材质 | 动作 |"
        sep = "|---|---|---|---:|---:|---:|"
        if details:
            head += " 顶点 | 三角面 | 材质槽 | 高 (cm) |"
            sep += "---:|---:|---:|---:|"
        lines += [head + " 已导出 |", sep + "---|"]
        for m in rows:
            name = m["name_en"] + (" " + m["name_zh"] if m["name_zh"] else "")
            row = "| `%s` | %s | %s | %d | %d | %d |" % (m["id"], name, m["group"], m["textures"],
                                                          m["materials"], m["animations"])
            if details:
                row += " %s | %s | %s | %s |" % (m.get("vertices", ""), m.get("triangles", ""),
                                                 m.get("slots", ""), m.get("height_cm", ""))
            lines.append(row + (" ✓ |" if m["exported"] else " |"))
        lines.append("")
    with open(os.path.join(meta, "model_list.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--category", choices=cc.CATEGORY_ORDER, action="append", help="repeatable")
    ap.add_argument("--find", nargs="+", default=[], help="ids / names / groups, wildcards ok")
    ap.add_argument("--no-objects", action="store_true", help="characters only")
    ap.add_argument("--details", action="store_true", help="read every listed mesh: vertices, slots, height")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="re-read the package list from the game")
    ap.add_argument("--export-root", default=cc.EXPORT_ROOT)
    a = ap.parse_args()

    cc.check_tools()
    packages = cc.list_packages(a.export_root, refresh=a.refresh)
    models = cc.discover_models(packages, include_objects=not a.no_objects, root=a.export_root)
    full = not a.category and not a.find
    if a.category:
        models = [m for m in models if m["category"] in a.category]
    if a.find:
        models = cc.find_models(models, a.find)
    if a.details:
        mesh_details(models, a.export_root)
    if full:
        write_lists(models, a.export_root, a.details)

    if a.json:
        print(json.dumps(models, ensure_ascii=False, indent=1))
        return 0
    for cat in cc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        print("\n== %s  %s  (%d)" % (cat, cc.CATEGORY_ZH[cat], len(rows)))
        print(header(a.details))
        for m in rows:
            print(fmt_row(m, a.details))
    done = sum(1 for m in models if m["exported"])
    print("\n%d models, %d exported (%s)" % (len(models), done, a.export_root))
    if full:
        print("list written to %s" % os.path.join(cc.meta_dir(a.export_root), "model_list.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
