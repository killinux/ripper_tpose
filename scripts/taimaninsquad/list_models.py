"""List the 3D units of Taimanin Squad and what has been exported.

The list comes from the game's Addressables catalog (StreamingAssets/aa/catalog.json): every
``<n>_<Name>/Unit/prf_<n>.prefab`` is one model (its ``_LOD1`` twin is the low-poly version and is
not listed separately).  Categories follow the unit numbers:

  character   1 - 128     the playable cast (Asagi, Sakura, Yukikaze ...)
  costume     237 - 299   other outfits of the same characters (253_asagi, 271_asagi ...)
  monster     129 - 236   orcs, demons, drones, undead
  special     300 -       Kaliya, Ragnarok, Cromwell
  boss        B_<n>       raid / chapter bosses
  mob         997 - 999   prologue extras

Examples:
  python list_models.py                       # everything, grouped by category
  python list_models.py --category character  # one category (repeatable)
  python list_models.py --find asagi 24 kira* # ids, unit numbers, names; wildcards ok
  python list_models.py --details             # + parts, vertices, triangles, bones, blend shapes, height,
                                              #   F = has breast bones (reads every art bundle, ~1 minute, cached)
  python list_models.py --female              # only the female figures: breast bones (F), or picked by eye (f,
                                              #   tsquad_common.FEMALE_BY_LOOK); implies --details
  python list_models.py --json                # machine-readable
  python list_models.py --html                # the gallery page scripts/taimaninsquad/html/index.html
Writes <export-root>/_meta/model_list.md and model_list.json when the whole list is shown.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402


def add_details(models: list[dict], root: str, refresh: bool = False) -> None:
    """vertices / triangles / bones / shapes / height per model, cached by art bundle name
    (the name carries the content hash, so a game update invalidates exactly what changed)."""
    cache_path = os.path.join(tc.meta_dir(root), "model_details.json")
    cache = {}
    if not refresh and os.path.isfile(cache_path):
        try:
            cache = tc.load_json(cache_path)
        except (OSError, ValueError):
            cache = {}
    need = [m for m in models if cache.get(m["id"], {}).get("bundle") != m["bundle"]]
    if need:
        import tsquad_scene as ts

        print("reading %d art bundles ..." % len(need), file=sys.stderr, flush=True)
        for i, m in enumerate(need, 1):
            try:
                info = ts.unit_details(m, root=root)   # a fresh loader each: bundles are not kept in memory
            except Exception as exc:  # noqa: BLE001
                info = {"error": str(exc)}
            info["bundle"] = m["bundle"]
            cache[m["id"]] = info
            if i % 25 == 0:
                print("  %d / %d" % (i, len(need)), file=sys.stderr, flush=True)
        tc.save_json(cache_path, cache)
    for m in models:
        m["details"] = {k: v for k, v in cache.get(m["id"], {}).items() if k != "bundle"}


def fmt_row(m: dict, details: bool) -> str:
    cols = ["%-26s" % m["id"], "%-20s" % m["name"], "%-3s" % ("LOD" if m["lod1_guid"] else "")]
    if details:
        d = m.get("details") or {}
        cols += ["%2s" % len(d.get("parts", [])), "%6s" % (d.get("vertices") or "-"), "%6s" % (d.get("triangles") or "-"),
                 "%4s" % (d.get("bones") or "-"), "%3s" % (d.get("shape_keys") or "-"), "%3s" % (d.get("materials") or "-"),
                 "%5s" % (d.get("height_m") or "-"), "F" if d.get("bust") else "f" if tc.is_female(m) else " "]
    cols.append(" ".join(m["exported"]))
    return "  ".join(cols)


def header(details: bool) -> str:
    cols = ["%-26s" % "id", "%-20s" % "name", "lod"]
    if details:
        cols += ["pt", "%6s" % "verts", "%6s" % "tris", "bone", "shp", "mat", "%5s" % "m", "F"]
    return "  ".join(cols + ["exported"])


def write_lists(models: list[dict], root: str, details: bool) -> None:
    meta = tc.meta_dir(root)
    tc.save_json(os.path.join(meta, "model_list.json"), models)
    lines = ["# Taimanin Squad 模型清单", "",
             "由 `scripts/taimaninsquad/list_models.py` 生成。导出：`python export_model.py <id> [--xps] [--pmx]`，"
             "结果在 `%s\\<角色>\\<blend|xps|pmx>\\<id>\\`。" % root, ""]
    for cat in tc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        lines += ["## %s（%d）" % (tc.CATEGORY_ZH[cat], len(rows)), ""]
        head, sep = "| id | 名字 | 组 |", "|---|---|---|"
        if details:
            head += " 部件 | 顶点 | 三角面 | 蒙皮骨 | 表情 | 材质 | 高 (m) | 女 |"
            sep += "---:|---:|---:|---:|---:|---:|---:|:-:|"
        lines += [head + " 已导出 |", sep + "---|"]
        for m in rows:
            row = "| `%s` | %s | %s |" % (m["id"], m["name"], m["group"])
            if details:
                d = m.get("details") or {}
                row += " %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    len(d.get("parts", [])), d.get("vertices", ""), d.get("triangles", ""), d.get("bones", ""),
                    d.get("shape_keys", ""), d.get("materials", ""), d.get("height_m", ""), "♀" if tc.is_female(m) else "")
            lines.append(row + " %s |" % " ".join(m["exported"]))
        lines.append("")
    with open(os.path.join(meta, "model_list.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--category", choices=tc.CATEGORY_ORDER, action="append", help="repeatable")
    ap.add_argument("--find", nargs="+", default=[], help="ids / unit numbers / names, wildcards ok")
    ap.add_argument("--details", action="store_true", help="read every listed prefab: parts, vertices, bones ...")
    ap.add_argument("--female", action="store_true",
                    help="only the female figures: breast bones, plus the few picked by eye (implies --details)")
    ap.add_argument("--exported", action="store_true", help="only units already exported")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--html", action="store_true", help="write the gallery page (html/index.html) and print its path")
    ap.add_argument("--refresh", action="store_true", help="re-read the catalog and the details from the game")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()

    tc.check_game()
    models = tc.discover_models(tc.catalog_assets(a.export_root, refresh=a.refresh), a.export_root)
    full = not (a.category or a.find or a.female or a.exported)
    details = a.details or a.female or a.html
    if a.category:
        models = [m for m in models if m["category"] in a.category]
    if a.find:
        models = tc.find_models(models, a.find)
    if details:
        add_details(models, a.export_root, refresh=a.refresh)
    if a.female:
        models = [m for m in models if tc.is_female(m)]
    if a.exported:
        models = [m for m in models if m["exported"]]
    if full:
        write_lists(models, a.export_root, details)

    if a.html:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "html"))
        import make_gallery

        page = make_gallery.build(models, a.export_root)
        print(page)
        return 0
    if a.json:
        print(json.dumps(models, ensure_ascii=False, indent=1))
        return 0
    for cat in tc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        print("\n== %s  %s  (%d)" % (cat, tc.CATEGORY_ZH[cat], len(rows)))
        print(header(details))
        for m in rows:
            print(fmt_row(m, details))
    done = sum(1 for m in models if m["exported"])
    print("\n%d models, %d exported (%s)" % (len(models), done, a.export_root))
    if full:
        print("list written to %s" % os.path.join(tc.meta_dir(a.export_root), "model_list.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
