"""List the HoneySelect 2 (Libido DX) models: base bodies, list items and character cards.

    python list_models.py                         # summary: counts per category + bodies + cards
    python list_models.py --category fo_top       # every item of one category (list key or number)
    python list_models.py --group hair --search 马尾
    python list_models.py --cards                 # the character cards and what each one wears
    python list_models.py --all --json D:\\hs2_exports\\_list\\models.json
    python list_models.py --html                  # D:\\hs2_exports\\_list\\index.html with game thumbnails
    python list_models.py --exported              # mark what export_model.py has already built

Refs printed in the first column (`fo_top:28`, `so_hair_b:9`, ...) are what
`export_model.py --item` takes.
"""
import argparse
import csv
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hs2_data  # noqa: E402

GROUP_LABEL = {"head": "脸型", "clothes": "衣服", "hair": "头发", "accessory": "饰品"}


def _console_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def exported_refs(out_root):
    """{ref: blend path} for items export_model.py has built (items/<key>/<name>/<name>.blend)."""
    done = {}
    base = os.path.join(out_root, "items")
    if not os.path.isdir(base):
        return done
    for key in os.listdir(base):
        kdir = os.path.join(base, key)
        if not os.path.isdir(kdir):
            continue
        for name in os.listdir(kdir):
            d = os.path.join(kdir, name)
            if not name.startswith(key + "_") or not os.path.isdir(d):
                continue
            try:
                item_id = int(name[len(key) + 1:].split("_")[0])  # <key>_<id3>_<prefab>[_with_body]
            except ValueError:
                continue
            blends = [f for f in os.listdir(d) if f.endswith(".blend")]
            if blends:
                done.setdefault("%s:%d" % (key, item_id), os.path.join(d, blends[0]))
    return done


def extract_thumbs(root, items, thumb_dir, deps):
    """Game thumbnails (ThumbAB/ThumbTex) -> <thumb_dir>/<key>_<id>.png; returns {ref: file}."""
    import UnityPy

    os.makedirs(thumb_dir, exist_ok=True)
    wanted = {}
    for it in items:
        ab, tex = it["thumb"]
        if ab and tex and ab != "0" and tex != "0":
            wanted.setdefault(ab, {}).setdefault(tex, []).append(it["ref"])
    out = {}
    for ab, texes in sorted(wanted.items()):
        todo = {}
        for tex, refs in texes.items():
            for ref in refs:
                fname = ref.replace(":", "_") + ".png"
                if os.path.isfile(os.path.join(thumb_dir, fname)):
                    out[ref] = fname
                else:
                    todo.setdefault(tex, []).append((ref, fname))
        if not todo:
            continue
        path = hs2_data.abdata_path(root, ab)
        if not os.path.isfile(path):
            continue
        env = UnityPy.load(path)
        for obj in env.objects:
            if obj.type.name not in ("Texture2D", "Sprite"):
                continue
            data = obj.read()
            if data.m_Name not in todo:
                continue
            try:
                img = data.image
            except Exception:  # noqa: BLE001
                continue
            img.thumbnail((160, 160))
            for ref, fname in todo.pop(data.m_Name):
                img.save(os.path.join(thumb_dir, fname))
                out[ref] = fname
            if not todo:
                break
    return out


def write_html(path, items, cards, thumbs, done, bodies):
    groups = {}
    for it in items:
        groups.setdefault((it["group"], it["category"]), []).append(it)
    css = """
:root{--bg:#f6f5f2;--fg:#1d1d1f;--mut:#6b6b70;--card:#fff;--line:#e3e1dc;--acc:#2f6f5e}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececef;--mut:#9a9aa2;--card:#202024;--line:#33333a;--acc:#6cc3a6}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Microsoft YaHei",sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}p.m{color:var(--mut);margin:0 0 16px}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2}
input{width:100%;max-width:420px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.it{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px;font-size:12px}
.it img{width:100%;aspect-ratio:1;object-fit:contain;background:#8882;border-radius:6px}
.it b{display:block;font-size:13px;margin-top:4px}.it code{color:var(--mut)}
.it.done{border-color:var(--acc)}.ok{color:var(--acc);font-weight:600}
table{border-collapse:collapse}td,th{border-bottom:1px solid var(--line);padding:4px 10px;text-align:left}
"""
    out = ["<title>HS2 Models</title><style>%s</style>" % css, "<h1>HoneySelect 2 模型列表</h1>",
           "<p class=m>%d 个物品 · %d 张角色卡 · 引用列可直接传给 <code>export_model.py --item</code></p>" % (len(items), len(cards)),
           "<div class=bar><input id=q placeholder='搜索名称 / 引用 / prefab'></div>"]
    out.append("<h2>底模</h2><table><tr><th>命令</th><th>prefab</th></tr>")
    for sex, info in bodies.items():
        out.append("<tr><td><code>--body %s</code></td><td>%s</td></tr>" % (sex, info["prefab"]))
    out.append("</table>")
    if cards:
        out.append("<h2>角色卡（UserData/chara）</h2><table><tr><th>文件</th><th>名字</th><th>性别</th><th>穿戴</th></tr>")
        for c in cards:
            wear = ", ".join("%s:%d" % (hs2_data.MODEL_CATEGORIES[cat][0], i) for _r, cat, i, _e in c.get("parts", []))
            out.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td style='font-size:11px'>%s</td></tr>" % (
                html.escape(c["file"]), html.escape(c.get("name", "")), c.get("sex", "?"), html.escape(wear)))
        out.append("</table>")
    for (group, cat), its in sorted(groups.items(), key=lambda kv: (list(GROUP_LABEL).index(kv[0][0]), kv[0][1])):
        key, sex, _g, label = hs2_data.MODEL_CATEGORIES[cat]
        out.append("<h2>%s · %s <code>%s</code> <small>(%d)</small></h2><div class=grid>" % (
            GROUP_LABEL[group], label, key, len(its)))
        for it in its:
            img = thumbs.get(it["ref"])
            tag = "<img loading=lazy src='thumbs/%s' alt=''>" % img if img else "<img alt=''>"
            cls = "it done" if it["ref"] in done else "it"
            search = " ".join([it["ref"], it["name"], it["name_en"], it["name_ja"], it["prefab"]]).lower()
            out.append("<div class='%s' data-s='%s'>%s<b>%s</b><code>%s</code><br><small>%s</small>%s</div>" % (
                cls, html.escape(search, True), tag, html.escape(it["name"] or it["prefab"]), it["ref"],
                html.escape(it["prefab"]), " <span class=ok>已导出</span>" if it["ref"] in done else ""))
        out.append("</div>")
    out.append("""<script>
const q=document.getElementById('q');q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();
document.querySelectorAll('.it').forEach(e=>{e.hidden=v&&!e.dataset.s.includes(v)})});
</script>""")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def main():
    _console_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="HoneySelect 2 folder (default %s or HS2_ROOT)" % hs2_data.GAME_DEFAULT)
    ap.add_argument("--out", default=hs2_data.EXPORTS_DEFAULT, help="export root (cache, html, exported marks)")
    ap.add_argument("--group", choices=sorted(GROUP_LABEL))
    ap.add_argument("--category", help="list key or categoryNo, e.g. fo_top / 240")
    ap.add_argument("--sex", choices=["female", "male"])
    ap.add_argument("--search", help="substring of name (zh/ja/en) or prefab")
    ap.add_argument("--all", action="store_true", help="print every item, not just the summary")
    ap.add_argument("--cards", action="store_true", help="list the character cards")
    ap.add_argument("--lang", choices=["zh", "en", "ja"], default="zh")
    ap.add_argument("--exported", action="store_true", help="mark items already built by export_model.py")
    ap.add_argument("--json", help="write the (filtered) list as JSON")
    ap.add_argument("--csv", help="write the (filtered) list as CSV")
    ap.add_argument("--html", nargs="?", const="", help="write an HTML list with thumbnails (default <out>/_list/index.html)")
    args = ap.parse_args()

    root = hs2_data.game_root(args.game)
    lists = hs2_data.load_lists(root, os.path.join(args.out, "_cache"))
    items = hs2_data.model_items(lists, args.lang)
    cat_filter = None
    if args.category:
        cat_filter = int(args.category) if args.category.isdigit() else hs2_data.KEY_TO_CATEGORY.get(args.category)
        if cat_filter is None:
            raise SystemExit("unknown category %r; known: %s" % (args.category, ", ".join(sorted(hs2_data.KEY_TO_CATEGORY))))
    sel = []
    needle = (args.search or "").lower()
    for it in items:
        if args.group and it["group"] != args.group:
            continue
        if cat_filter is not None and it["category"] != cat_filter:
            continue
        if args.sex and it["sex"] not in (args.sex, "both"):
            continue
        if needle and needle not in " ".join([it["name"], it["name_ja"], it["name_en"], it["prefab"]]).lower():
            continue
        sel.append(it)
    done = exported_refs(args.out) if (args.exported or args.html is not None) else {}
    filtered = bool(args.group or args.category or args.sex or args.search)

    print("HoneySelect 2: %s" % root)
    summary = not filtered and not args.all and not args.cards
    if summary:
        print("\n底模 (export_model.py --body <sex>):")
        for sex, info in hs2_data.BODIES.items():
            print("  %-7s %s + %s  (%s)" % (sex, info["prefab"], info["head_bone"], hs2_data.BASE_BUNDLE))
        print("\n物品 (export_model.py --item <ref>):  共 %d" % len(items))
        print("  %-12s %-6s %-14s %5s  %s" % ("list key", "cat", "类别", "数量", "性别"))
        counts = {}
        for it in items:
            counts[it["category"]] = counts.get(it["category"], 0) + 1
        for cat in sorted(counts, key=lambda c: (list(GROUP_LABEL).index(hs2_data.MODEL_CATEGORIES[c][2]), c)):
            key, sex, group, label = hs2_data.MODEL_CATEGORIES[cat]
            extra = ""
            if args.exported:
                n = sum(1 for it in items if it["category"] == cat and it["ref"] in done)
                extra = "  已导出 %d" % n
            print("  %-12s %-6d %-14s %5d  %s%s" % (key, cat, GROUP_LABEL[group] + "/" + label, counts[cat], sex, extra))
    if filtered or args.all:
        print("\n%-16s %-24s %-26s %-8s %s" % ("ref", "名称", "prefab", "dist", "bundle"))
        for it in sel:
            mark = "  [已导出]" if it["ref"] in done else ""
            print("%-16s %-24s %-26s %-8s %s%s" % (it["ref"], it["name"][:24], it["prefab"][:26], it["dist"], it["bundle"], mark))
        print("(%d 个)" % len(sel))
    cards = []
    if args.cards or summary or args.html is not None or args.json:
        cards = hs2_data.list_cards(root)
    if args.cards or summary:
        print("\n角色卡 (export_model.py --card <file> [--nude]):  %d 张" % len(cards))
        for c in cards:
            if "error" in c:
                print("  %-22s !! %s" % (c["file"], c["error"]))
                continue
            real = [r for r in c["parts"] if hs2_data.is_model_row(lists.get(r[1], {}).get(r[2], {}))]
            count = lambda g: sum(1 for r in real if hs2_data.MODEL_CATEGORIES[r[1]][2] == g)  # noqa: E731
            print("  %-22s %-6s %-22s 头发 %d / 衣服 %d / 饰品 %d" % (
                c["file"], c["sex"], c["name"][:22], count("hair"), count("clothes"), count("accessory")))
            if args.cards:
                for role, cat, item_id, _extra in c["parts"]:
                    row = lists.get(cat, {}).get(item_id, {})
                    print("      %-16s %s:%d  %s" % (role, hs2_data.MODEL_CATEGORIES[cat][0], item_id, hs2_data.display_name(row, args.lang)))
    out_items = sel if filtered else items
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"game": root, "bodies": hs2_data.BODIES, "items": out_items,
                       "cards": [{k: v for k, v in c.items()} for c in cards]}, f, ensure_ascii=False, indent=1)
        print("wrote %s" % args.json)
    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        cols = ["ref", "category", "key", "id", "group", "label", "sex", "name", "name_ja", "name_en", "prefab", "bundle", "dist", "parent"]
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(out_items)
        print("wrote %s" % args.csv)
    if args.html is not None:
        path = args.html or os.path.join(args.out, "_list", "index.html")
        thumbs = extract_thumbs(root, out_items, os.path.join(os.path.dirname(path), "thumbs"), None)
        write_html(path, out_items, cards, thumbs, done, hs2_data.BODIES)
        print("wrote %s (%d thumbnails)" % (path, len(thumbs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
