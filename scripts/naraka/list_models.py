"""List the NARAKA: BLADEPOINT models that export_model.py can export.

    python list_models.py                         # summary: groups, families, counts
    python list_models.py --group outfit          # every outfit (hero skins)
    python list_models.py --family ch_f_ming_haikou
    python list_models.py --hero 宁红夜 --group outfit    # or --hero ninghongye
    python list_models.py --search yaodao --group hair
    python list_models.py --ui                    # include the *_ui lobby copies
    python list_models.py --exported              # mark what is already exported
    python list_models.py --html                  # D:\\naraka_exports\\_list\\index.html
    python list_models.py --all --csv out.csv  |  --json out.json

Only the manifest (StreamingAssets\\AppRes.info) is read, so this takes ~1 s.
The first column is what export_model.py takes (--outfit / --prefab).
"""
import argparse
import collections
import csv
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naraka_catalog  # noqa: E402
import naraka_manifest  # noqa: E402
from naraka_env import STREAMING  # noqa: E402

OUT = os.environ.get("NARAKA_OUT", r"D:\naraka_exports")
GROUP_TEXT = {
    "outfit": "外观（英雄时装）",
    "hair": "外观配套发型",
    "outfit_part": "外观附件/变体",
    "default_hair": "默认发型",
    "cosmetic": "脸/眉/眼影/胡子",
    "full_body": "怪物/NPC 整体模型",
    "dummy_body": "骨架/替身",
    "other_body": "其他角色部件",
    "weapon": "武器",
}
EXPORT_DIR = {"outfit": "outfits"}


def export_dir(item, out=OUT):
    return os.path.join(out, EXPORT_DIR.get(item.group, "items"), item.name)


def preview_of(item, out=OUT):
    p = os.path.join(export_dir(item, out), item.name + "_preview.png")
    return p if os.path.isfile(p) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-data", default=STREAMING, help="StreamingAssets folder")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--group", choices=sorted(GROUP_TEXT))
    ap.add_argument("--family")
    ap.add_argument("--hero", help="hero codename or Chinese name (宁红夜 / ninghongye)")
    ap.add_argument("--search")
    ap.add_argument("--sex", choices=("f", "m"))
    ap.add_argument("--ui", action="store_true", help="include *_ui copies")
    ap.add_argument("--all", action="store_true", help="list every item, not the summary")
    ap.add_argument("--exported", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    ap.add_argument("--html", nargs="?", const="", help="write the gallery (default <out>\\_list\\index.html)")
    args = ap.parse_args()

    items = naraka_catalog.build(naraka_manifest.read(args.game_data))
    sel = [i for i in items if (args.ui or not i.ui)
           and (not args.group or i.group == args.group)
           and (not args.family or i.family == args.family)
           and (not args.hero or args.hero in naraka_catalog.hero_label(i.family).split())
           and (not args.sex or i.sex == args.sex)
           and (not args.search or args.search.lower() in i.path.lower())]

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["name", "group", "family", "sex", "skin", "ui", "path", "bundle", "exported"])
            for i in sel:
                w.writerow([i.name, i.group, i.family, i.sex, i.skin, int(bool(i.ui)), i.path, i.bundle,
                            int(bool(preview_of(i, args.out)))])
        print("wrote %s (%d rows)" % (args.csv, len(sel)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([i.as_dict() for i in sel], f, ensure_ascii=False, indent=1)
        print("wrote %s (%d items)" % (args.json, len(sel)))
    if args.html is not None:
        path = args.html or os.path.join(args.out, "_list", "index.html")
        write_html(path, sel, args.out)
        print("wrote %s" % path)
    if args.csv or args.json or args.html is not None:
        return

    filtered = args.group or args.family or args.hero or args.search or args.sex or args.all
    if not filtered:
        by_group = collections.Counter(i.group for i in sel)
        print("%d models (without _ui copies; --ui adds them)\n" % len(sel))
        for g in GROUP_TEXT:
            print("  %-13s %5d  %s" % (g, by_group.get(g, 0), GROUP_TEXT[g]))
        fam = collections.Counter(i.family for i in sel if i.group == "outfit")
        heroes = sum(1 for f in fam if naraka_catalog.hero_of(f)[0])
        print("\noutfit families (%d; %d of them belong to the %d heroes):" % (
            len(fam), heroes, len(naraka_catalog.HEROES)))
        for f, n in sorted(fam.items(), key=lambda kv: (kv[0].split("_")[1], kv[0])):
            hairs = sum(1 for i in sel if i.group == "hair" and i.family == f)
            print("  %-26s %3d outfits  %3d hairstyles   %s" % (f, n, hairs, naraka_catalog.hero_label(f) or "-"))
        print("\nnext: --group outfit | --family <name> | --html")
        return
    for i in sel:
        mark = ""
        if args.exported:
            mark = "  [exported]" if preview_of(i, args.out) else ""
        print("%-48s %-12s %-26s %-18s %s%s" % (i.name, i.group, i.family or "",
                                                naraka_catalog.hero_label(i.family), i.bundle, mark))
    print("\n%d items" % len(sel))


def write_html(path, items, out):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    groups = collections.OrderedDict((g, []) for g in GROUP_TEXT)
    for i in items:
        groups[i.group].append(i)
    done = sum(1 for i in items if preview_of(i, out))
    rows = []
    for g, lst in groups.items():
        if not lst:
            continue
        rows.append('<h2 id="%s">%s <small>%s · %d</small></h2><div class="grid">' % (g, g, GROUP_TEXT[g], len(lst)))
        for i in lst:
            prev = preview_of(i, out)
            if prev:
                rel = os.path.relpath(prev, os.path.dirname(path)).replace("\\", "/")
                blend = os.path.relpath(os.path.join(export_dir(i, out), i.name + ".blend"),
                                        os.path.dirname(path)).replace("\\", "/")
                pic = '<a href="%s"><img loading="lazy" src="%s"></a>' % (html.escape(blend), html.escape(rel))
                cls = "card done"
            else:
                pic = '<div class="none">未导出</div>'
                cls = "card"
            hero = naraka_catalog.hero_label(i.family)
            sub = (i.family or "") + ((" · " + hero) if hero else "")
            rows.append('<div class="%s" data-k="%s">%s<b>%s</b><span>%s</span></div>' % (
                cls, html.escape((i.name + " " + i.path + " " + hero).lower()), pic, html.escape(i.name),
                html.escape(sub)))
        rows.append("</div>")
    nav = " · ".join('<a href="#%s">%s (%d)</a>' % (g, GROUP_TEXT[g], len(l)) for g, l in groups.items() if l)
    doc = """<!doctype html><meta charset="utf-8"><title>NARAKA 模型列表</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;background:#1d1f24;color:#ddd}
header{position:sticky;top:0;background:#16181c;padding:10px 16px;border-bottom:1px solid #333;z-index:2}
input{width:320px;padding:6px;background:#2a2d33;color:#eee;border:1px solid #444}
label{margin-left:12px}
a{color:#8ab4f8}
h2{margin:18px 16px 8px;font-weight:600}h2 small{color:#999;font-weight:400}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;padding:0 16px}
.card{background:#262930;border-radius:6px;padding:6px;font-size:12px;overflow:hidden}
.card img{width:100%;aspect-ratio:9/14;object-fit:cover;background:#94949e;border-radius:4px}
.card .none{aspect-ratio:9/14;display:flex;align-items:center;justify-content:center;color:#666;border:1px dashed #444;border-radius:4px}
.card b{display:block;margin-top:4px;word-break:break-all}.card span{color:#888}
</style>
<header><input id="q" placeholder="搜索：名字或路径" autofocus>
<label><input type="checkbox" id="only"> 只看已导出</label>
<span style="margin-left:12px;color:#999">@COUNT@ 个模型，已导出 @DONE@</span><div style="margin-top:6px">@NAV@</div></header>
@ROWS@
<script>
const q=document.getElementById('q'),only=document.getElementById('only');
function f(){const s=q.value.toLowerCase();for(const c of document.querySelectorAll('.card')){
c.style.display=(c.dataset.k.includes(s)&&(!only.checked||c.classList.contains('done')))?'':'none'}}
q.oninput=f;only.onchange=f;
</script>"""
    doc = doc.replace("@COUNT@", str(len(items))).replace("@DONE@", str(done)).replace("@NAV@", nav) \
        .replace("@ROWS@", "\n".join(rows))
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


if __name__ == "__main__":
    main()
