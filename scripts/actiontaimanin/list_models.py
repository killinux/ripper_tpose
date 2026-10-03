"""List the 3D models of Action Taimanin and what has been exported.

The list is the prefabs of the ``unit`` bundle (its container paths; the bundle is read block by block,
about 2 seconds):

  figure      unit/figure/<char>_costume_<n>_f      a character in one costume, put together for display
                                                    (body + hair + face) - the ones to export
  character   unit/character/<char>_g | _l          the same character as the game (g) / the lobby (l) uses it
  monster     unit/monster/<name>                   enemies; ``monster_<char>_<n>`` = a playable character as a boss
  npc         unit/npc/<name>                       NPCs and props
  weapon      unit/weapon/<name>                    weapon prefabs (the game hangs them on ``Bip001 Prop1``)

Examples:
  python list_models.py                       # everything, grouped by category
  python list_models.py --category figure     # one category (repeatable)
  python list_models.py --find asagi "rin*"   # ids, character names; wildcards ok
  python list_models.py --details             # + parts, vertices, triangles, bones, face bones, materials,
                                              #   shader families, Dynamic Bone chains (reads every listed
                                              #   prefab: about 5 minutes for all, cached)
  python list_models.py --exported            # only what has been exported
  python list_models.py --json                # machine-readable
  python list_models.py --html                # the gallery page scripts/actiontaimanin/html/index.html
Writes <export-root>/_meta/model_list.md and model_list.json when the whole list is shown.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ataimanin_common as ac  # noqa: E402
from ataimanin_common import tc  # noqa: E402


def add_details(models: list[dict], root: str, game: ac.Game | None = None, refresh: bool = False) -> None:
    """vertices / triangles / bones / materials per model, cached with the unit bundle's signature."""
    cache_path = os.path.join(tc.meta_dir(root), "model_details.json")
    cache = {}
    if not refresh and os.path.isfile(cache_path):
        try:
            cache = tc.load_json(cache_path)
        except (OSError, ValueError):
            cache = {}
    if cache.get("signature") != ac.signature():
        cache = {"signature": ac.signature(), "models": {}}
    known = cache["models"]
    need = [m for m in models if m["id"] not in known]
    if need:
        import ataimanin_scene as asc

        game = game or ac.Game()
        print("reading %d prefabs ..." % len(need), file=sys.stderr, flush=True)
        for i, m in enumerate(need, 1):
            try:
                known[m["id"]] = asc.unit_details(m, game)
            except Exception as exc:  # noqa: BLE001
                known[m["id"]] = {"error": str(exc)}
            if i % 100 == 0:
                print("  %d / %d" % (i, len(need)), file=sys.stderr, flush=True)
                tc.save_json(cache_path, cache)
        tc.save_json(cache_path, cache)
    for m in models:
        m["details"] = known.get(m["id"], {})


def fmt_row(m: dict, details: bool) -> str:
    cols = ["%-34s" % m["id"], "%-26s" % m["name"]]
    if details:
        d = m.get("details") or {}
        cols += ["%2s" % len(d.get("parts", [])), "%6s" % (d.get("vertices") or "-"), "%6s" % (d.get("triangles") or "-"),
                 "%4s" % (d.get("bones") or "-"), "%3s" % (d.get("face_bones") or "-"), "%3s" % (d.get("materials") or "-"),
                 "%2s" % (d.get("dynamic_bones") or "-"), "%-9s" % "+".join(d.get("shaders") or [])]
    cols.append(" ".join(m["exported"]))
    return "  ".join(cols)


def header(details: bool) -> str:
    cols = ["%-34s" % "id", "%-26s" % "name"]
    if details:
        cols += ["pt", "%6s" % "verts", "%6s" % "tris", "bone", "fac", "mat", "db", "%-9s" % "shaders"]
    return "  ".join(cols + ["exported"])


def write_lists(models: list[dict], root: str, details: bool) -> None:
    meta = tc.meta_dir(root)
    tc.save_json(os.path.join(meta, "model_list.json"), models)
    lines = ["# Action Taimanin 模型清单", "",
             "由 `scripts/actiontaimanin/list_models.py` 生成。导出：`python export_model.py <id> [--xps] [--pmx]`，"
             "结果在 `%s\\<角色>\\<blend|xps|pmx>\\<id>\\`。" % root, ""]
    for cat in ac.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        lines += ["## %s（%d）" % (ac.CATEGORY_ZH[cat], len(rows)), ""]
        head, sep = "| id | 名字 | 组 |", "|---|---|---|"
        if details:
            head += " 部件 | 顶点 | 三角面 | 蒙皮骨 | 脸部骨 | 材质 | Dynamic Bone | 着色器 |"
            sep += "---:|---:|---:|---:|---:|---:|---:|---|"
        lines += [head + " 已导出 |", sep + "---|"]
        for m in rows:
            row = "| `%s` | %s | %s |" % (m["id"], m["name"], m["group"])
            if details:
                d = m.get("details") or {}
                row += " %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    len(d.get("parts", [])), d.get("vertices", ""), d.get("triangles", ""), d.get("bones", ""),
                    d.get("face_bones", ""), d.get("materials", ""), d.get("dynamic_bones", ""),
                    " + ".join(d.get("shaders") or []))
            lines.append(row + " %s |" % " ".join(m["exported"]))
        lines.append("")
    with open(os.path.join(meta, "model_list.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--category", choices=ac.CATEGORY_ORDER, action="append", help="repeatable")
    ap.add_argument("--find", nargs="+", default=[], help="ids / character names, wildcards ok")
    ap.add_argument("--details", action="store_true", help="read every listed prefab: parts, vertices, bones ...")
    ap.add_argument("--exported", action="store_true", help="only models already exported")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--html", action="store_true", help="write the gallery page (html/index.html) and print its path")
    ap.add_argument("--refresh", action="store_true", help="re-read the model list and the details from the game")
    ap.add_argument("--export-root", default=ac.EXPORT_ROOT)
    a = ap.parse_args()

    ac.check_game()
    game = ac.Game()
    models = ac.discover_models(a.export_root, game, refresh=a.refresh)
    everything = list(models)
    full = not (a.category or a.find or a.exported)
    if a.category:
        models = [m for m in models if m["category"] in a.category]
    if a.find:
        models = ac.find_models(models, a.find)
    if a.exported:
        models = [m for m in models if m["exported"]]
    if a.details:
        add_details(models, a.export_root, game, refresh=a.refresh)
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
    for cat in ac.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        print("\n== %s  %s  (%d)" % (cat, ac.CATEGORY_ZH[cat], len(rows)))
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
