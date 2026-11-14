# -*- coding: utf-8 -*-
"""A themed collection folder across games: hard links of archived exports + a local gallery that says where every
model comes from.

    python make_collection.py collections/gantz.json [--dry-run]

The spec (JSON) names the output folder, the archive root (E:\\game_export) and the sections - one per source (a mod,
a Patreon post, a downloaded pack): its game, title, author, link, date, the files that were downloaded, how it was
converted and what it lacks, and which archived folders belong to it ("glob" under the root: <Game>/<Character>/
<format>/<model>, or a "fmt" for folders laid out otherwise).  For every section the script
  * hard-links every file of those folders into <out>/<section dir>/<format>/<model>/ (same volume as the archive:
    no extra space; editing a file there edits the archived one - the gallery says so);
  * makes a thumbnail per model (_thumbs/, from the folder's preview image or a "thumb_from" pattern; an item's
    "thumb_panels": n says that preview is n views side by side, front first - the thumbnail keeps the front one);
  * copies the source's own picture (the mod page's image) into _thumbs/source/.
Then writes <out>/index.html (the gallery, local files only) and <out>/说明.md.  Re-running replaces the links;
folders the spec no longer names are left alone (listed in the run's output).
"""
import argparse
import datetime
import glob
import html
import json
import os
import shutil
import sys

try:
    from PIL import Image
except ImportError:  # thumbnails need Pillow
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS = ("pmx", "xps", "blend")
MAIN_EXT = {"pmx": ".pmx", "xps": ".xps", "blend": ".blend"}
PREVIEWS = ("preview.png", "preview.jpg", "*_preview.png", "preview_front.png", "*.png")


def link_tree(src, dst, stats):
    for dp, _dirs, files in os.walk(src):
        rel = os.path.relpath(dp, src)
        out = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(out, exist_ok=True)
        for f in files:
            s, d = os.path.join(dp, f), os.path.join(out, f)
            if os.path.exists(d):
                if os.path.samefile(s, d):
                    stats["kept"] += 1
                    continue
                os.remove(d)
            try:
                os.link(s, d)
                stats["linked"] += 1
            except OSError:
                shutil.copy2(s, d)
                stats["copied"] += 1
            stats["bytes"] += os.path.getsize(s)


def find_preview(folder, model):
    for pat in PREVIEWS:
        hits = sorted(glob.glob(os.path.join(folder, pat.replace("*", glob.escape(model) + "*") if pat.startswith("*_")
                                             else pat)))
        hits = [h for h in hits if "textures" not in os.path.relpath(h, folder).replace("\\", "/").split("/")[0]]
        if hits:
            return hits[0]
    return None


def thumb(src, dst, height=420, panels=1):
    if Image is None or not src or not os.path.isfile(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im = Image.open(src).convert("RGB")
    if panels > 1 and im.width > 1.5 * im.height:     # front / side / back strip: keep the front view
        im = im.crop((0, 0, im.width // panels, im.height))
    if im.height > height:
        im = im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
    im.save(dst, quality=86)
    return True


def main_file(folder, fmt):
    ext = MAIN_EXT[fmt]
    hits = sorted(f for f in os.listdir(folder) if f.lower().endswith(ext) and not f.lower().endswith("_converted.blend"))
    return hits[0] if hits else None


def build(spec, dry):
    root, out = spec["root"], spec["out"]
    os.makedirs(os.path.join(out, "_thumbs", "source"), exist_ok=True)
    sections = []
    stats = {"linked": 0, "kept": 0, "copied": 0, "bytes": 0}
    for sec in spec["sections"]:
        models = {}
        for item in sec.get("models", []):
            pattern = os.path.join(root, item["glob"])
            for folder in sorted(glob.glob(pattern)):
                if not os.path.isdir(folder) or any(x in os.path.basename(folder) for x in item.get("exclude", [])):
                    continue
                parts = os.path.relpath(folder, root).replace("\\", "/").split("/")
                fmt = item.get("fmt") or (parts[2] if len(parts) >= 4 and parts[2] in FORMATS else None)
                if fmt not in FORMATS:
                    continue
                name = os.path.basename(folder)
                m = models.setdefault(name, {"name": name, "formats": {}, "thumb": None, "label": item.get("label", "")})
                dst = os.path.join(out, sec["dir"], fmt, name)
                if not dry:
                    link_tree(folder, dst, stats)
                mf = main_file(folder, fmt)
                m["formats"][fmt] = {"dir": os.path.relpath(dst, out).replace("\\", "/"),
                                     "main": mf, "src": folder}
                prev = None
                if item.get("thumb_from"):
                    prev = item["thumb_from"].replace("{name}", name)
                if not prev or not os.path.isfile(prev):
                    prev = find_preview(folder, name)
                if prev and (m["thumb"] is None or fmt == "blend"):
                    t = os.path.join(out, "_thumbs", sec["dir"], name + ".jpg")
                    if dry or thumb(prev, t, panels=item.get("thumb_panels", 1)):
                        m["thumb"] = os.path.relpath(t, out).replace("\\", "/")
        pic = sec.get("source", {}).get("picture")
        pic_rel = None
        if pic:
            src = pic if os.path.isabs(pic) else os.path.join(spec.get("source_images", ""), pic)
            if os.path.isfile(src):
                t = os.path.join(out, "_thumbs", "source", sec["dir"] + ".jpg")
                if dry or thumb(src, t, height=360):
                    pic_rel = os.path.relpath(t, out).replace("\\", "/")
        sections.append(dict(sec, model_list=sorted(models.values(), key=lambda m: m["name"].lower()), picture_rel=pic_rel))
        print("%-34s %3d models" % (sec["dir"], len(models)), flush=True)
    known = {s["dir"] for s in spec["sections"]} | {"_thumbs"}
    stray = [d for d in os.listdir(out) if os.path.isdir(os.path.join(out, d)) and d not in known]
    if stray:
        print("folders the spec does not name (left alone):", stray)
    if not dry:
        write_html(spec, sections, out)
        write_md(spec, sections, out)
    print("COLLECTION=" + json.dumps({"out": out, "sections": len(sections),
                                      "models": sum(len(s["model_list"]) for s in sections), **stats},
                                     ensure_ascii=False), flush=True)


def esc(x):
    return html.escape(str(x or ""), quote=True)


def href(path):
    return esc(path.replace("\\", "/").replace("#", "%23").replace("?", "%3F"))


CSS = """
:root{--bg:#f6f6f4;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e2e2de;--accent:#0f766e;--chip:#eef6f5}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141416;--card:#1e1e22;--ink:#ececef;
--muted:#9a9aa3;--line:#2e2e34;--accent:#5eead4;--chip:#1f2f2d}}
:root[data-theme="dark"]{--bg:#141416;--card:#1e1e22;--ink:#ececef;--muted:#9a9aa3;--line:#2e2e34;--accent:#5eead4;--chip:#1f2f2d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,
"Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1280px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 6px}h2{font-size:20px;margin:0}a{color:var(--accent)}
.lead{color:var(--muted);margin:0 0 18px}.toc{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 28px;padding:0;list-style:none}
.toc a{display:inline-block;padding:4px 10px;border:1px solid var(--line);border-radius:999px;text-decoration:none;
background:var(--card)}section{margin:0 0 36px;padding:18px;background:var(--card);border:1px solid var(--line);
border-radius:14px}.head{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start}
.head img{width:220px;max-width:38vw;border-radius:10px;border:1px solid var(--line)}
.meta{margin:6px 0 0;color:var(--muted);font-size:14px}.meta b{color:var(--ink);font-weight:600}
.notes{margin:10px 0 0;font-size:14px}.files{font-size:13px;color:var(--muted);word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:16px}
.m{border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.m .ph{aspect-ratio:3/4;background:var(--bg);display:flex;align-items:center;justify-content:center}
.m .ph img{width:100%;height:100%;object-fit:contain}.m .ph span{color:var(--muted);font-size:13px}
.m .t{padding:8px 10px 10px;font-size:13px;word-break:break-all}.chips{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.chips a{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--chip);text-decoration:none}
.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:var(--chip);margin-left:6px;
color:var(--accent)}footer{color:var(--muted);font-size:13px}
@media (max-width:560px){.head{grid-template-columns:1fr}.head img{width:100%;max-width:none}}
"""


def write_html(spec, sections, out):
    n_models = sum(len(s["model_list"]) for s in sections)
    parts = ["<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
             "<title>%s</title><style>%s</style></head><body><main>" % (esc(spec["title"]), CSS),
             "<h1>%s</h1><p class=\"lead\">%s</p>" % (esc(spec["title"]), esc(spec.get("intro", ""))),
             "<p class=\"lead\">%d 个来源，%d 个模型。更新于 %s。</p>" % (
                 len(sections), n_models, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
             "<ul class=\"toc\">"]
    for s in sections:
        parts.append("<li><a href=\"#%s\">%s <span class=\"badge\">%d</span></a></li>" % (
            href(s["dir"]), esc(s.get("short") or s["title"]), len(s["model_list"])))
    parts.append("</ul>")
    for s in sections:
        src = s.get("source", {})
        parts.append("<section id=\"%s\"><div class=\"head\">" % href(s["dir"]))
        parts.append("<img src=\"%s\" alt=\"\">" % href(s["picture_rel"]) if s.get("picture_rel") else "<div></div>")
        parts.append("<div><h2>%s</h2>" % esc(s["title"]))
        meta = ["<b>%s</b>" % esc(s.get("game", ""))]
        if src.get("author"):
            meta.append("作者 %s" % esc(src["author"]))
        if src.get("date"):
            meta.append("发布 %s" % esc(src["date"]))
        if src.get("url"):
            meta.append("<a href=\"%s\">%s</a>" % (esc(src["url"]), esc(src.get("site") or src["url"])))
        parts.append("<p class=\"meta\">%s</p>" % " · ".join(meta))
        if src.get("files"):
            parts.append("<p class=\"files\">下载的文件：%s</p>" % "；".join(esc(f) for f in src["files"]))
        if s.get("converted"):
            parts.append("<p class=\"notes\"><b>怎么转的</b>：%s</p>" % esc(s["converted"]))
        if s.get("notes"):
            parts.append("<p class=\"notes\"><b>说明</b>：%s</p>" % esc(s["notes"]))
        parts.append("<p class=\"files\">文件夹：<a href=\"%s/\">%s\\</a></p></div></div>" % (href(s["dir"]), esc(s["dir"])))
        parts.append("<div class=\"grid\">")
        for m in s["model_list"]:
            ph = ("<img loading=\"lazy\" src=\"%s\" alt=\"\">" % href(m["thumb"])) if m["thumb"] else "<span>没有预览图</span>"
            chips = []
            for fmt in FORMATS:
                f = m["formats"].get(fmt)
                if not f:
                    continue
                target = f["dir"] + "/" + f["main"] if f["main"] else f["dir"] + "/"
                chips.append("<a href=\"%s\">%s</a>" % (href(target), fmt.upper()))
                chips.append("<a href=\"%s/\" title=\"打开文件夹\">📁</a>" % href(f["dir"]))
            parts.append("<div class=\"m\"><div class=\"ph\">%s</div><div class=\"t\">%s%s<div class=\"chips\">%s</div>"
                         "</div></div>" % (ph, esc(m["name"]), (" · " + esc(m["label"])) if m["label"] else "",
                                           "".join(chips)))
        parts.append("</div></section>")
    parts.append("<footer><p>%s</p></footer></main></body></html>" % esc(spec.get("footer", "")))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def write_md(spec, sections, out):
    lines = ["# %s" % spec["title"], "", spec.get("intro", ""), "",
             "画廊：[index.html](index.html)（本地网页，双击打开）。", "",
             "| 目录 | 游戏 | 来源 | 作者 | 模型数 |", "|---|---|---|---|---|"]
    for s in sections:
        src = s.get("source", {})
        lines.append("| `%s` | %s | [%s](%s) | %s | %d |" % (s["dir"], s.get("game", ""), s["title"], src.get("url", ""),
                                                          src.get("author", ""), len(s["model_list"])))
    lines.append("")
    for s in sections:
        src = s.get("source", {})
        lines += ["## %s" % s["title"], "", "- 游戏：%s" % s.get("game", ""),
                  "- 来源：%s %s" % (src.get("site", ""), src.get("url", "")),
                  "- 作者：%s" % src.get("author", ""), "- 发布：%s" % src.get("date", "")]
        if src.get("files"):
            lines.append("- 下载的文件：%s" % "；".join(src["files"]))
        if s.get("converted"):
            lines.append("- 怎么转的：%s" % s["converted"])
        if s.get("notes"):
            lines.append("- 说明：%s" % s["notes"])
        lines.append("- 模型（%d）：" % len(s["model_list"]))
        for m in s["model_list"]:
            lines.append("  - `%s`：%s" % (m["name"], " / ".join(f.upper() for f in FORMATS if f in m["formats"])))
        lines.append("")
    lines += [spec.get("footer", ""), ""]
    with open(os.path.join(out, "说明.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    path = args.spec if os.path.isfile(args.spec) else os.path.join(HERE, args.spec)
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    build(spec, args.dry_run)


if __name__ == "__main__":
    main(sys.argv[1:])
