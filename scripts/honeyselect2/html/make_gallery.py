"""把 HoneySelect 2 的导出产物做成一页可浏览的 HTML 画廊。

扫描导出根（默认 D:\\hs2_exports）下 cards\\ / bodies\\ / items\\ 每个目录的 scene.json（export_model.py
写的：来源、部件、骨骼、材质、告警）和 .blend / 预览图，把预览缩成 JPEG 缩略图写到
<导出根>\\_gallery\\thumbs\\，页面写到本脚本旁的 index.html。页面只用 file:// 指向本机文件，
**游戏素材不进仓库**——和这里其它画廊同一条规矩。每批新导出后重跑即可。

  python make_gallery.py
  python make_gallery.py --source-root D:\\hs2_exports --force
"""
import argparse
import datetime
import html
import json
import os
from pathlib import Path

from PIL import Image

THUMB_HEIGHT = 900
KINDS = [("card", "角色卡 · 穿好"), ("card_nude", "角色卡 · 裸"), ("body", "底模"), ("item", "单件")]
GROUPS = {"head": "脸型", "clothes": "衣服", "hair": "头发", "accessory": "饰品"}
ROLE_LABELS = {"head": "脸", "hair_back": "后发", "hair_front": "前发", "hair_side": "侧发", "hair_option": "附加发",
               "clothes_top": "上衣", "clothes_bot": "下装", "clothes_inner_t": "内衣上", "clothes_inner_b": "内衣下",
               "clothes_gloves": "手套", "clothes_panst": "连裤袜", "clothes_socks": "袜子", "clothes_shoes": "鞋"}


def file_uri(path):
    try:
        return Path(path).as_uri() if path else ""
    except (ValueError, OSError):
        return ""


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "-"


def thumb(src, dst, force):
    if not src or not os.path.isfile(src):
        return ""
    if not force and os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.height > THUMB_HEIGHT:
            im = im.resize((round(im.width * THUMB_HEIGHT / im.height), THUMB_HEIGHT), Image.LANCZOS)
        im.save(dst, "JPEG", quality=84, optimize=True)
    return dst


def collect(root, thumb_dir, force):
    entries = []
    for top in ("cards", "bodies", "items"):
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            if "scene.json" not in files:
                continue
            blends = [f for f in files if f.endswith(".blend")]
            if not blends:
                continue
            with open(os.path.join(dirpath, "scene.json"), encoding="utf-8") as f:
                scene = json.load(f)
            name = scene.get("name") or os.path.splitext(blends[0])[0]
            blend = os.path.join(dirpath, name + ".blend")
            if not os.path.isfile(blend):
                blend = os.path.join(dirpath, blends[0])
            kind = scene.get("kind", "item")
            if kind == "card" and scene.get("nude"):
                kind = "card_nude"
            label = os.path.basename(dirpath)
            pv = {s: os.path.join(dirpath, name + "_" + s + ".png") for s in ("preview", "side", "face")}
            thumbs = {s: thumb(p, os.path.join(thumb_dir, label + "_" + s + ".jpg"), force) for s, p in pv.items()}
            verts = sum(p.get("verts", 0) for p in scene.get("parts", []))
            shapes = sum(len(p.get("shape_keys", [])) for p in scene.get("parts", []))
            sources = scene.get("sources", [])
            entries.append({
                "label": label, "kind": kind, "name": name, "dir": dirpath, "blend": blend,
                "blend_size": os.path.getsize(blend), "mtime": os.path.getmtime(blend),
                "character": scene.get("character", ""), "sex": scene.get("sex", ""),
                "card": scene.get("card", ""), "ref": scene.get("ref", ""), "group": scene.get("group", ""),
                "with_body": label.endswith("_with_body"),
                "sources": sources, "parts": len(scene.get("parts", [])), "bones": len(scene.get("nodes", [])),
                "materials": len(scene.get("materials", {})), "verts": verts, "shapes": shapes,
                "warnings": scene.get("warnings", []),
                "previews": {s: p if os.path.isfile(p) else "" for s, p in pv.items()}, "thumbs": thumbs,
                "fbx": os.path.join(dirpath, name + ".fbx") if os.path.isfile(os.path.join(dirpath, name + ".fbx")) else "",
            })
    order = {k: i for i, (k, _l) in enumerate(KINDS)}
    entries.sort(key=lambda e: (order.get(e["kind"], 9), e["group"], e["label"]))
    return entries


def render_card(e):
    esc = html.escape
    kind_label = dict(KINDS).get(e["kind"], e["kind"])
    badges = '<span class="badge k">%s</span>' % esc(kind_label)
    if e["group"]:
        badges += '<span class="badge">%s</span>' % esc(GROUPS.get(e["group"], e["group"]))
    if e["with_body"]:
        badges += '<span class="badge">穿在底模上</span>'
    if e["sex"]:
        badges += '<span class="badge">%s</span>' % ("女" if e["sex"] == "female" else "男")
    if e["warnings"]:
        badges += '<span class="badge w" title="%s">告警 %d</span>' % (esc("; ".join(e["warnings"])), len(e["warnings"]))
    if e["kind"].startswith("card"):
        title = "%s <small>%s</small>" % (esc(e["character"] or e["label"]), esc(e["card"]))
    else:
        title = esc(e["label"])
    wear = []
    for s in e["sources"]:
        if s.get("role") == "body":
            continue
        role = ROLE_LABELS.get(s.get("role", ""), "饰品" if s.get("role", "").startswith("acc_") else s.get("role", ""))
        wear.append("%s <code>%s</code> %s" % (esc(role), esc(s.get("ref", "")), esc(s.get("name", "") or "")))
    shots = ""
    for s, lab in (("side", "3/4"), ("face", "脸")):
        if e["thumbs"].get(s):
            shots += '<a href="%s" target="_blank" rel="noopener"><img loading="lazy" src="%s" alt="%s"></a>' % (
                esc(file_uri(e["previews"][s])), esc(file_uri(e["thumbs"][s])), lab)
    main = ('<img loading="lazy" src="%s" alt="">' % esc(file_uri(e["thumbs"]["preview"]))) if e["thumbs"].get("preview") else '<div class="noimg">无预览</div>'
    search = " ".join([e["label"], e["character"], e["card"], e["ref"], kind_label] +
                      [s.get("ref", "") + " " + (s.get("name") or "") for s in e["sources"]]).lower()
    fbx = ('<dt>fbx</dt><dd><a href="%s">%s</a></dd>' % (esc(file_uri(e["fbx"])), esc(os.path.basename(e["fbx"])))) if e["fbx"] else ""
    return """<article class="card" data-kind="{kind}" data-search="{search}">
  <a class="shot" href="{pv}" target="_blank" rel="noopener">{main}</a>
  <div class="thumbs">{shots}</div>
  <div class="body">
    <h3>{title}</h3><div class="badges">{badges}</div>
    <dl>
      <dt>组成</dt><dd class="wear">{wear}</dd>
      <dt>规格</dt><dd>{parts} 部件 · {verts:,} 顶点 · {bones} 骨骼 · {mats} 材质{shapes} · {size}</dd>
      <dt>blend</dt><dd><a href="{blend_uri}" title="{blend}">{blend_name}</a> <button class="copy" data-copy="{blend}">复制路径</button></dd>
      {fbx}
    </dl>
  </div>
</article>
""".format(kind=esc(e["kind"]), search=esc(search, True), pv=esc(file_uri(e["previews"]["preview"])), main=main,
           shots=shots, title=title, badges=badges, wear="<br>".join(wear) or "-",
           parts=e["parts"], verts=e["verts"], bones=e["bones"], mats=e["materials"],
           shapes=(" · %d 形态键" % e["shapes"]) if e["shapes"] else "", size=human_size(e["blend_size"]),
           blend_uri=esc(file_uri(e["blend"])), blend=esc(e["blend"]), blend_name=esc(os.path.basename(e["blend"])), fbx=fbx)


CSS = """
:root{--bg:#f5f3ef;--fg:#1c1b1a;--mut:#6d6a66;--card:#fff;--line:#e2ded7;--acc:#8a3b52;--acc2:#f3e6ea;--warn:#a45a00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151416;--fg:#ecebea;--mut:#9d9a97;--card:#1f1e21;--line:#343238;--acc:#e28aa4;--acc2:#3a2530;--warn:#f0a040;color-scheme:dark}}
:root[data-theme=dark]{--bg:#151416;--fg:#ecebea;--mut:#9d9a97;--card:#1f1e21;--line:#343238;--acc:#e28aa4;--acc2:#3a2530;--warn:#f0a040;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:26px;margin:0}.sub{color:var(--mut);margin:4px 0 18px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.stat b{font-size:20px;display:block}.stat span{color:var(--mut);font-size:12px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-bottom:1px solid var(--line)}
.chip{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:99px;padding:5px 12px;cursor:pointer;font:inherit}
.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
input[type=search]{flex:1;min-width:200px;max-width:380px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:inherit}
.count{color:var(--mut);margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.shot{display:block;background:#9a9aa0}.shot img{width:100%;aspect-ratio:9/14;object-fit:contain;display:block}
.noimg{aspect-ratio:9/14;display:grid;place-items:center;color:#fff}
.thumbs{display:flex;gap:2px;background:#9a9aa0}.thumbs a{flex:1}.thumbs img{width:100%;height:120px;object-fit:cover;object-position:center 30%;display:block}
.body{padding:10px 12px 12px}h3{margin:0;font-size:16px}h3 small{color:var(--mut);font-weight:400;font-size:12px}
.badges{margin:5px 0 6px}.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;background:var(--acc2);color:var(--acc);margin:0 4px 3px 0}
.badge.k{background:var(--acc);color:#fff}.badge.w{background:transparent;border:1px solid var(--warn);color:var(--warn)}
dl{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;margin:0;font-size:12px}dt{color:var(--mut)}dd{margin:0;overflow-wrap:anywhere}
.wear code{color:var(--mut)}a{color:var(--acc)}
.copy{font-size:11px;border:1px solid var(--line);background:transparent;color:var(--mut);border-radius:6px;cursor:pointer;padding:0 6px}
.appendix{margin-top:40px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 20px 16px}
.appendix pre{background:var(--bg);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:12.5px}
.appendix table{border-collapse:collapse;font-size:13px}.appendix td,.appendix th{border-bottom:1px solid var(--line);padding:4px 10px;text-align:left;vertical-align:top}
"""

APPENDIX = r"""
<section class="appendix">
<h2>附录 · 怎么导出 / 重新生成本页</h2>
<p>脚本在 <code>〈仓库〉\scripts\honeyselect2\</code>，只需 Python 3（<code>pip install UnityPy Pillow numpy</code>）+ Blender 3.6
（默认 <code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>）。游戏默认
<code>E:\SteamLibrary\steamapps\common\HoneySelect2Libido DX</code>（<code>--game</code> / <code>HS2_ROOT</code>），产物默认 <code>D:\hs2_exports</code>。</p>
<pre>cd 〈仓库〉\scripts\honeyselect2
python list_models.py                         # 底模、31 类 812 件物品、角色卡
python list_models.py --html                  # 带游戏缩略图的全部物品列表 D:\hs2_exports\_list\index.html
python export_model.py --card HS2_ill_F_000   # 角色卡穿好；--nude 去掉衣服和饰品
python export_model.py --all-cards [--nude]
python export_model.py --body female|male
python export_model.py --item fo_top:28 [--with-body]
python export_model.py --all-items --group hair   # 批量；--fbx 另出 FBX
python html\make_gallery.py                   # 重新生成本页</pre>
<table>
<tr><th>产物</th><th>说明</th></tr>
<tr><td><code>cards\&lt;卡&gt;[_nude]\</code></td><td>整张角色卡：骨架 p_cf_anim + 身体 + 脸 + 头发 + 衣服 + 饰品，卡里的颜色 / 皮肤 / 眼睛 / 眉毛</td></tr>
<tr><td><code>bodies\body_female|male\</code></td><td>裸底模 + 默认脸</td></tr>
<tr><td><code>items\&lt;list key&gt;\&lt;key&gt;_&lt;id&gt;_&lt;prefab&gt;[_with_body]\</code></td><td>单件：自带骨骼，或穿在默认底模上</td></tr>
<tr><td>每个目录</td><td><code>&lt;名&gt;.blend</code>（贴图已打包）、<code>_preview / _side / _face.png</code>、<code>scene.json</code>、<code>parts\</code>、<code>textures\</code>、<code>build.log</code></td></tr>
</table>
<p>原理与限制见仓库 <code>docs\honey-select-2-extraction.md</code>：体型滑块、衣服图案、脸部妆、衣服下的身体遮罩未做。</p>
</section>
"""


def render(entries, root):
    esc = html.escape
    counts = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    chips = '<button class="chip on" data-kind="">全部</button>' + "".join(
        '<button class="chip" data-kind="%s">%s <small>%d</small></button>' % (k, esc(lab), counts[k])
        for k, lab in KINDS if counts.get(k))
    stats = "".join('<div class="stat"><b>%d</b><span>%s</span></div>' % (counts.get(k, 0), esc(lab)) for k, lab in KINDS)
    stats += '<div class="stat"><b>%s</b><span>blend 合计</span></div>' % human_size(sum(e["blend_size"] for e in entries))
    return """<title>HS2 Gallery</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{css}</style>
<div class="wrap">
<h1>HoneySelect 2 导出画廊</h1>
<p class="sub">{n} 个 .blend · 导出根 <code>{root}</code> · 生成于 {when} · 点图看原尺寸预览</p>
<div class="stats">{stats}</div>
<div class="bar">{chips}<input type="search" id="q" placeholder="搜索：角色名 / 卡名 / 物品引用 / 物品名"><span class="count" id="count"></span></div>
<div class="grid" id="grid">
{cards}</div>
{appendix}
</div>
<script>
let kind='';const q=document.getElementById('q'),cards=[...document.querySelectorAll('.card')],cnt=document.getElementById('count');
function apply(){{const v=q.value.trim().toLowerCase();let n=0;cards.forEach(c=>{{const ok=(!kind||c.dataset.kind===kind)&&(!v||c.dataset.search.includes(v));c.hidden=!ok;if(ok)n++}});cnt.textContent=n+' / '+cards.length}}
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));b.classList.add('on');kind=b.dataset.kind;apply()}});
q.oninput=apply;
document.querySelectorAll('.copy').forEach(b=>b.onclick=()=>{{navigator.clipboard&&navigator.clipboard.writeText(b.dataset.copy);b.textContent='已复制';setTimeout(()=>b.textContent='复制路径',1200)}});
apply();
</script>
""".format(css=CSS, n=len(entries), root=esc(root), when=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           stats=stats, chips=chips, cards="".join(render_card(e) for e in entries), appendix=APPENDIX)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-root", default=r"D:\hs2_exports")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))
    ap.add_argument("--thumb-dir")
    ap.add_argument("--force", action="store_true", help="重建全部缩略图")
    args = ap.parse_args()
    thumb_dir = args.thumb_dir or os.path.join(args.source_root, "_gallery", "thumbs")
    entries = collect(args.source_root, thumb_dir, args.force)
    page = render(entries, args.source_root)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    kinds = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("wrote %s: %d entries %s" % (args.out, len(entries), kinds))


if __name__ == "__main__":
    main()
