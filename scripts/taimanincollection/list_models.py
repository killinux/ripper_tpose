"""List the 3D models of Taimanin Collection and what has been exported.

The game is a 2D card game; its 3D is what the bike mini-game shows, plus leftovers of Action Taimanin.  The list
is every prefab under Resources/ of data.unity3d that draws a mesh, and the scenes that do (the file is read
whole, about 15 seconds; the list is cached):

  character   unit_art/model/<char>/prf_*          a character put together: body + hair + face - the one to export
  vehicle     background/art/movie/*_rig           rigged vehicles: the motorcycle (wheels apart), the drop ship
  prop        bike/background/prf_*, bike/skybox   what the bike race is built of: track, barricade, coin, truck ...
  level       bike/level/prf_race_trackobject_*    the pieces the race track is put together from
  scene       Assets/Scenes/*.unity                a scene of the build as a whole, and its roots one by one
  set         background/art/movie/.../prf_*       city sets left over from Action Taimanin: materials stripped
  unit        unit/<name>                          the unit prefab the game spawns: the character again + a camera
  part        unit_art/model/<char>/<costume>/     the parts a character is put together from
  effect, director                                 effect meshes; cutscene set-ups (Timeline)
  raw         everything else                      raw model imports with Unity's default material (leftovers)

Examples:
  python list_models.py                       # everything, grouped by category
  python list_models.py --category prop level # some categories
  python list_models.py --find asagi "*truck*"   # ids, character names; wildcards ok
  python list_models.py --details             # + parts, vertices, triangles, bones, materials (and how many of
                                              #   them are Unity's default / stripped), shaders, Dynamic Bone
  python list_models.py --exported            # only what has been exported
  python list_models.py --json                # machine-readable
  python list_models.py --html                # the gallery page scripts/taimanincollection/html/index.html
Writes <export-root>/_meta/model_list.md and model_list.json when the whole list is shown.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tcollection_common as tcc  # noqa: E402
from tcollection_common import tc  # noqa: E402


def add_details(models: list[dict], root: str, game: tcc.Game | None = None, refresh: bool = False) -> None:
    """vertices / triangles / bones / materials per model, cached with the data file's signature."""
    cache_path = os.path.join(tc.meta_dir(root), "model_details.json")
    cache = {}
    if not refresh and os.path.isfile(cache_path):
        try:
            cache = tc.load_json(cache_path)
        except (OSError, ValueError):
            cache = {}
    if cache.get("signature") != tcc.signature():
        cache = {"signature": tcc.signature(), "models": {}}
    known = cache["models"]
    need = [m for m in models if m["id"] not in known]
    if need:
        import tcollection_scene as tcs

        game = game or tcc.Game()
        print("reading %d prefabs ..." % len(need), file=sys.stderr, flush=True)
        for m in need:
            try:
                known[m["id"]] = tcs.details(m, game)
            except Exception as exc:  # noqa: BLE001
                known[m["id"]] = {"error": str(exc)}
        tc.save_json(cache_path, cache)
    for m in models:
        m["details"] = known.get(m["id"], {})


def material_note(d: dict) -> str:
    """'3' or '3 (2 default)' / '(9 stripped)' - how many of the materials say nothing."""
    notes = ["%d %s" % (d[key], label) for key, label in (("default_materials", "default"), ("stripped_materials", "stripped"))
             if d.get(key)]
    return "%s%s" % (d.get("materials", ""), " (%s)" % ", ".join(notes) if notes else "")


def fmt_row(m: dict, details: bool) -> str:
    cols = ["%-36s" % m["id"], "%2d" % m["skinned"], "%3d" % m["rigid"]]
    if details:
        d = m.get("details") or {}
        cols += ["%7s" % (d.get("vertices") or "-"), "%7s" % (d.get("triangles") or "-"), "%4s" % (d.get("bones") or "-"),
                 "%-16s" % material_note(d), "%2s" % (d.get("dynamic_bones") or "-"), "%-18s" % "+".join(d.get("shaders") or [])]
    cols.append(" ".join(m["exported"]))
    return "  ".join(cols)


def header(details: bool) -> str:
    cols = ["%-36s" % "id", "sk", "rig"]
    if details:
        cols += ["%7s" % "verts", "%7s" % "tris", "bone", "%-16s" % "materials", "db", "%-18s" % "shaders"]
    return "  ".join(cols + ["exported"])


def write_lists(models: list[dict], root: str, details: bool) -> None:
    meta = tc.meta_dir(root)
    tc.save_json(os.path.join(meta, "model_list.json"), models)
    lines = ["# Taimanin Collection 模型清单", "",
             "由 `scripts/taimanincollection/list_models.py` 生成。导出：`python export_model.py <id> [--xps] [--pmx]`，"
             "结果在 `%s\\<组>\\<blend|xps|pmx>\\<id>\\`。" % root, ""]
    for cat in tcc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        lines += ["## %s（%d）" % (tcc.CATEGORY_ZH[cat], len(rows)), ""]
        head, sep = "| id | 来源 | 蒙皮网格 | 刚体网格 |", "|---|---|---:|---:|"
        if details:
            head += " 顶点 | 三角面 | 蒙皮骨 | 材质 | Dynamic Bone | 着色器 |"
            sep += "---:|---:|---:|---|---:|---|"
        lines += [head + " 已导出 |", sep + "---|"]
        for m in rows:
            row = "| `%s` | `%s` | %d | %d |" % (m["id"], m["key"], m["skinned"], m["rigid"])
            if details:
                d = m.get("details") or {}
                row += " %s | %s | %s | %s | %s | %s |" % (
                    d.get("vertices", ""), d.get("triangles", ""), d.get("bones", ""), material_note(d),
                    d.get("dynamic_bones", ""), " + ".join(d.get("shaders") or []))
            lines.append(row + " %s |" % " ".join(m["exported"]))
        lines.append("")
    with open(os.path.join(meta, "model_list.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--category", choices=tcc.CATEGORY_ORDER, nargs="+", action="extend", default=[])
    ap.add_argument("--find", nargs="+", default=[], help="ids / character names, wildcards ok")
    ap.add_argument("--details", action="store_true", help="read every listed prefab: vertices, bones, materials ...")
    ap.add_argument("--exported", action="store_true", help="only models already exported")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--html", action="store_true", help="write the gallery page (html/index.html) and print its path")
    ap.add_argument("--refresh", action="store_true", help="re-read the model list and the details from the game")
    ap.add_argument("--export-root", default=tcc.EXPORT_ROOT)
    a = ap.parse_args()

    tcc.check_game()
    game = None
    cached = os.path.isfile(os.path.join(tc.meta_dir(a.export_root), "models.json")) and not a.refresh
    if not cached or a.details:
        game = tcc.Game()
    models = tcc.discover_models(a.export_root, game, refresh=a.refresh)
    everything = list(models)
    full = not (a.category or a.find or a.exported)
    if a.category:
        models = [m for m in models if m["category"] in a.category]
    if a.find:
        models = tcc.find_models(models, a.find)
    if a.exported:
        models = [m for m in models if m["exported"]]
    if a.details or a.html:
        add_details(everything if a.html else models, a.export_root, game, refresh=a.refresh)
    if full:
        write_lists(models, a.export_root, a.details)

    if a.html:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "html"))
        import make_gallery

        print(make_gallery.build(everything, a.export_root))
        return 0
    if a.json:
        print(json.dumps(models, ensure_ascii=False, indent=1))
        return 0
    for cat in tcc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        print("\n== %s  %s  (%d)" % (cat, tcc.CATEGORY_ZH[cat], len(rows)))
        print(header(a.details))
        for m in rows:
            print(fmt_row(m, a.details))
    done = sum(1 for m in models if m["exported"])
    print("\n%d models, %d exported (%s)" % (len(models), done, a.export_root))
    if full:
        print("list written to %s" % os.path.join(tc.meta_dir(a.export_root), "model_list.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
