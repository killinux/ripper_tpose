r"""Local gallery page of the Nexus-mod looks exported for Eve (2026-11-15: the 48 looks of 12 mods the user
downloaded to E:\Downloads\eve_mod_download, plus the earlier mod exports) ->
E:\game_export\StellarBlade\_mod画廊\index.html (+ thumbs\).  Reads the archive only; one card per look with its
previews, the four formats (Blender, HQ Blender, PMX, XPS), the add-on sheet, the Nexus page and notes.

    python mod_gallery.py --looks <looks.json>      (written by the export batch: label, mod, title, nexus, author,
                                                    file, notes, waiting)
Links are relative to the page, so the page works from E: directly (file://) and moves with the archive."""
import argparse
import html
import json
import os

from PIL import Image

ARCHIVE = r"E:\game_export\StellarBlade"
OUT = os.path.join(ARCHIVE, "_mod画廊")
THUMB_W = 360


def rel(path):
    return os.path.relpath(path, OUT).replace("\\", "/")


def thumb(src, name):
    os.makedirs(os.path.join(OUT, "thumbs"), exist_ok=True)
    dst = os.path.join(OUT, "thumbs", name + ".jpg")
    if not os.path.isfile(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        im = Image.open(src).convert("RGB")
        h = int(im.height * THUMB_W / im.width)
        im.resize((THUMB_W, h), Image.LANCZOS).save(dst, quality=86)
    return "thumbs/" + name + ".jpg"


def card(lk):
    pkg = lk["label"][4:] if lk["label"].startswith("Eve_") else lk["label"]
    char = lk.get("character", "Eve")
    bdir = os.path.join(ARCHIVE, char, "blend", pkg)
    pdir = os.path.join(ARCHIVE, char, "pmx", pkg)
    xdir = os.path.join(ARCHIVE, char, "xps", pkg)
    files = {
        "Blender": os.path.join(bdir, lk["label"] + ".blend"),
        "高清 Blender": os.path.join(bdir, lk["label"] + "_HQ.blend"),
        "PMX": os.path.join(pdir, lk["label"] + ".pmx"),
        "XPS": os.path.join(xdir, lk["label"] + ".xps"),
    }
    extra = {
        "插件效果对比": os.path.join(pdir, "插件效果_游戏材质对比.jpg"),
        "跳舞预览": os.path.join(pdir, "preview_dance.png"),
        "表情": os.path.join(pdir, "preview_morphs.png"),
        "背面": os.path.join(bdir, "preview_back.png"),
        "说明": os.path.join(bdir, "README.txt"),
    }
    front = next((p for p in (os.path.join(bdir, "preview.png"), os.path.join(pdir, "preview.png")) if os.path.isfile(p)),
                 None)
    have = {k: os.path.isfile(v) for k, v in files.items()}
    done = all(have.values())
    out = ['<div class="card%s" data-mod="%s" data-text="%s">' % (
        "" if done else " wait", html.escape(lk["mod"]),
        html.escape((lk["title"] + " " + lk["label"] + " " + lk.get("author", "")).lower()))]
    if front:
        out.append('<a class="pic" href="%s"><img loading="lazy" src="%s" alt=""></a>' % (
            html.escape(rel(front)), html.escape(thumb(front, pkg))))
    else:
        out.append('<div class="pic none">%s</div>' % html.escape(lk.get("waiting") or "还没导出"))
    out.append('<div class="t">%s</div>' % html.escape(lk["title"]))
    out.append('<div class="l">%s</div>' % html.escape(lk["label"]))
    out.append('<div class="f">')
    for k, v in files.items():
        if have[k]:
            out.append('<a class="fmt" href="%s">%s</a>' % (html.escape(rel(v)), k))
        else:
            out.append('<span class="fmt off">%s</span>' % k)
    out.append("</div><div class=\"x\">")
    out.append(" · ".join('<a href="%s">%s</a>' % (html.escape(rel(v)), k) for k, v in extra.items()
                          if os.path.isfile(v)))
    out.append("</div>")
    if lk.get("notes"):
        out.append('<div class="n">%s</div>' % html.escape(lk["notes"]))
    if lk.get("waiting") and not done:
        out.append('<div class="w">等下载：%s</div>' % html.escape(lk["waiting"]))
    out.append("</div>")
    return "\n".join(out), done


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>剑星 Eve mod 画廊</title>
<style>
:root { --bg:#111216; --card:#1b1d23; --line:#2b2e37; --text:#e8e8ea; --dim:#9a9ca6; --acc:#ffcf7a; --ok:#7ad3a0; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 "Microsoft YaHei", "PingFang SC", sans-serif; }
header { padding:20px 16px 8px; max-width:1500px; margin:auto; }
h1 { margin:0 0 6px; font-size:22px; }
.sub { color:var(--dim); }
.bar { position:sticky; top:0; background:rgba(17,18,22,.96); padding:10px 16px; z-index:2; border-bottom:1px solid var(--line); }
.bar .in { max-width:1500px; margin:auto; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.bar button { background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:14px; padding:3px 10px; cursor:pointer; font:inherit; }
.bar button.on { border-color:var(--acc); color:var(--acc); }
.bar input { flex:1 1 180px; min-width:150px; background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:5px 8px; font:inherit; }
main { max-width:1500px; margin:auto; padding:8px 16px 40px; }
section h2 { font-size:17px; margin:22px 0 4px; }
section .meta { color:var(--dim); margin-bottom:10px; }
section .meta a { color:var(--acc); }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px; display:flex; flex-direction:column; gap:4px; min-width:0; }
.card.wait { opacity:.55; }
.pic img { width:100%; aspect-ratio:900/1400; object-fit:cover; border-radius:5px; background:#8c8c93; display:block; }
.pic.none { aspect-ratio:900/1400; display:flex; align-items:center; justify-content:center; text-align:center; color:var(--dim); border:1px dashed var(--line); border-radius:5px; padding:10px; }
.t { font-weight:bold; }
.l { color:var(--dim); font-size:12px; word-break:break-all; }
.f { display:flex; flex-wrap:wrap; gap:4px; }
.fmt { font-size:12px; border:1px solid var(--ok); color:var(--ok); border-radius:4px; padding:0 5px; text-decoration:none; }
.fmt.off { border-color:var(--line); color:var(--dim); }
.x, .x a { font-size:12px; color:var(--dim); }
.n { font-size:12px; color:#c9c9cf; }
.w { font-size:12px; color:var(--acc); }
footer { color:var(--dim); max-width:1500px; margin:auto; padding:0 16px 30px; font-size:12px; }
</style></head><body>
<header><h1>剑星 Eve · Nexus mod 导出画廊</h1>
<div class="sub">%(summary)s</div></header>
<div class="bar"><div class="in"><button class="on" data-f="">全部</button>%(buttons)s
<input id="q" placeholder="搜索名字 / 作者"></div></div>
<main>%(sections)s</main>
<footer>本页由 ripper_tpose scripts/stellarblade/mod_gallery.py 生成（%(date)s），只读存档。每套：Blender（PMX / XPS 由它导出）、
高清 Blender（游戏参数的材质，Blender 里「剑星游戏材质」插件给 PMX 换材质时从这里取）、PMX（MMD）、XPS（XNALara）。
个人使用；转发请注明 mod 作者。</footer>
<script>
const cards = [...document.querySelectorAll('.card')], secs = [...document.querySelectorAll('section')];
let mod = '', q = '';
function apply() {
  cards.forEach(c => { c.style.display = (!mod || c.dataset.mod === mod) && (!q || c.dataset.text.includes(q)) ? '' : 'none'; });
  secs.forEach(s => { s.style.display = [...s.querySelectorAll('.card')].some(c => c.style.display !== 'none') ? '' : 'none'; });
}
document.querySelectorAll('.bar button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.bar button').forEach(x => x.classList.toggle('on', x === b)); mod = b.dataset.f; apply(); });
document.getElementById('q').oninput = e => { q = e.target.value.trim().toLowerCase(); apply(); };
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--looks", required=True)
    ap.add_argument("--date", default="")
    a = ap.parse_args()
    doc = json.load(open(a.looks, encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    sections, buttons, n_done, n_all = [], [], 0, 0
    for mod in doc["mods"]:
        cards = []
        for lk in [x for x in doc["looks"] if x["mod"] == mod["key"]]:
            c, done = card(lk)
            cards.append(c)
            n_done += done
            n_all += 1
        if not cards:
            continue
        buttons.append('<button data-f="%s">%s</button>' % (html.escape(mod["key"]), html.escape(mod["short"])))
        sections.append('<section><h2>%s</h2><div class="meta">Nexus <a href="https://www.nexusmods.com/stellarblade/mods/%d">#%d</a>'
                        ' · 作者 %s · 文件「%s」%s</div><div class="grid">%s</div></section>' % (
                            html.escape(mod["title"]), mod["nexus"], mod["nexus"], html.escape(mod["author"]),
                            html.escape(mod["file"]), (" · " + html.escape(mod["note"])) if mod.get("note") else "",
                            "\n".join(cards)))
    page = PAGE
    for k, v in (("summary", html.escape("%d 个 mod，%d 套造型，已导出 %d 套（灰色的在等下载或还没导）" % (
            len(buttons), n_all, n_done))), ("buttons", "".join(buttons)), ("sections", "\n".join(sections)),
                 ("date", html.escape(a.date))):
        page = page.replace("%%(%s)s" % k, v)          # not the % operator: the CSS has its own % signs
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print("gallery: %s (%d looks, %d done)" % (os.path.join(OUT, "index.html"), n_all, n_done))


if __name__ == "__main__":
    main()
