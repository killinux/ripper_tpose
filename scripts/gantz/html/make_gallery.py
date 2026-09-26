"""GANTZ（杀戮都市）主题 mod 导出的全部模型做成一页画廊：FF7 Remake / FF7 Rebirth / Stellar Blade。

只收 GANTZ 相关的：下面 ``MODS`` 里登记的 5 个 Nexus mod 导出的模型（23 个）。数据全从 ``E:\\game_export``
归档读，不碰 D 盘：

* 各游戏 ``_meta\\models.json``：造型的主文件、预览图（按 ``<角色>/<格式>/<造型>`` 查）；
* 各游戏的画廊清单（``_meta`` 下的 manifest）：顶点 / 骨骼 / 材质、PMX 检查结果；
* 缩略图直接用各游戏画廊已经生成好的 ``_meta\\gallery\\thumbs\\<label>.jpg``。

页面用 ``file://`` 链接指向本机文件，**任何游戏素材都不会进仓库** —— 和这里其它画廊同一条规矩。
以后再导出新的 GANTZ mod：先照各游戏的流程导出、归档到 E 盘，再在 ``MODS`` 里加一行，重跑：

  python scripts\\gantz\\html\\make_gallery.py
"""

import datetime
import html
import json
import os
from pathlib import Path

ARCHIVE = r"E:\game_export"
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
GAMES = {
    "FF7Remake": {"title": "FF7 Remake", "manifest": "ff7remake_models_manifest.json"},
    "FF7Rebirth": {"title": "FF7 Rebirth", "manifest": "ff7rebirth_gallery_manifest.json"},
    "StellarBlade": {"title": "Stellar Blade", "manifest": "stellarblade_models_manifest.json"},
}
MODS = [
    {"game": "FF7Remake", "id": 967, "domain": "finalfantasy7remake", "char": "Tifa", "prefix": "mod967_",
     "name": "Tifa - Gantz Suit", "author": "MonkeyMan Mods", "body": "normal", "adult": True},
    {"game": "FF7Remake", "id": 1707, "domain": "finalfantasy7remake", "char": "Tifa", "prefix": "mod1707_",
     "name": "Tifa Gantz Basic Suit (Custom Emission)", "author": "TheWolfster", "body": "normal"},
    {"game": "FF7Rebirth", "id": 817, "domain": "finalfantasy7rebirth", "char": "Tifa", "prefix": "mod817_",
     "name": "GANTZ Basic Suit (Tifa)", "author": "TheWolfster", "body": "normal"},
    {"game": "FF7Rebirth", "id": 1613, "domain": "finalfantasy7rebirth", "char": "Reika", "prefix": "mod1613_",
     "name": "Gantz - Reika (DRESSCODE)", "author": "SeeS", "body": "big", "adult": True},
    {"game": "StellarBlade", "id": 3561, "domain": "stellarblade", "char": "Reika", "prefix": "Mod_GantzReika_",
     "name": "Gantz Reika (CNS)", "author": "Hawkins（hwahwa）", "body": "eve", "adult": True},
]
BODY = {"normal": "原版 Tifa 身材", "big": "夸张身材（mod 原设计）", "eve": "正常身材（Eve 的身体）"}
# 每个造型一句话（缩略图看不出来的差别）
NOTES = {
    "mod967_Tifa_Mod_Tifa_Gantz_Suit_Full_suit_version": "全身紧身衣",
    "mod967_Tifa_Mod_Tifa_Gantz_Suit_Sexy_version": "性感版：胸腹和大腿露肤",
    "mod1707_PC0002_00_Tifa_Gantz_Basic_Suit": "普通款",
    "mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy": "暴露款",
    "mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Hair_and_Makeup_Ad": "普通款 + 发型妆容附加包",
    "mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy_Hair_and_Ma": "暴露款 + 发型妆容附加包",
    "mod1707_PC0002_00_Hair_and_Makeup_Add_on": "发型妆容附加包单独套在原版标准服上（没做 XPS / PMX）",
    "mod1707_PC0002_01_Hair_and_Makeup_Add_on": "发型妆容附加包单独套在原版紫裙上（没做 XPS / PMX）",
    "mod817_PC0002_00_Tifa_GANTZ_Basic_Suit": "替换版：普通款，mod 自带发型",
    "mod817_PC0002_00_Tifa_GANTZ_Basic_Suit_Standard_Hair": "替换版：普通款，原版发型",
    "mod817_PC0002_00_Tifa_GANTZ_Basic_Suit_Skimpy": "替换版：暴露款，mod 自带发型",
    "mod817_PC0002_00_Tifa_GANTZ_Basic_Suit_Skimpy_Standard_Ha": "替换版：暴露款，原版发型",
    "mod817_fullsuit_Tifa_GANTZ_DRESSCODE_1_005": "Dresscode 版：全身",
    "mod817_fullsuit_purple_Tifa_GANTZ_DRESSCODE_1_005": "Dresscode 版：全身，紫色发光",
    "mod817_skimpy_Tifa_GANTZ_DRESSCODE_1_005": "Dresscode 版：暴露款",
    "mod817_skimpy_purple_Tifa_GANTZ_DRESSCODE_1_005": "Dresscode 版：暴露款，紫色发光",
    "mod1613_Reika_Final_Gantz_Reika_Dresscode_for_1_005": "开胸款，配长筒袜",
    "mod1613_Reika_Finalcomplet_Gantz_Reika_Dresscode_for_1_005": "全包款",
    "mod1613_Reika_NUDE_Gantz_Reika_Dresscode_for_1_005": "裸体，留手套和靴子",
    "mod1613_Reika_Viesassuit_Gantz_Reika_Dresscode_for_1_005": "机甲装甲版",
    "mod1613_Reika_ViesassuitNosuit_Gantz_Reika_Dresscode_for_1_005": "机甲装甲，不穿紧身衣",
    "Mod_GantzReika_A": "全套紧身衣",
    "Mod_GantzReika_B": "暴露款",
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def file_uri(path):
    try:
        return Path(path).as_uri() if path else ""
    except ValueError:
        return ""


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return "%.1f %s" % (num, unit) if unit != "B" else "%d B" % num
        num /= 1024.0
    return "-"


def collect():
    models = []
    for game, info in GAMES.items():
        game_dir = os.path.join(ARCHIVE, game)
        registry = load_json(os.path.join(game_dir, "_meta", "models.json"), {})
        manifest = load_json(os.path.join(game_dir, "_meta", info["manifest"]), {}).get("results", [])
        for mod in [m for m in MODS if m["game"] == game]:
            char_dir = os.path.join(game_dir, mod["char"])
            names = sorted({n for fmt in ("blend", "xps", "pmx") if os.path.isdir(os.path.join(char_dir, fmt))
                            for n in os.listdir(os.path.join(char_dir, fmt)) if n.startswith(mod["prefix"])})
            for name in names:
                files = {}
                for fmt in ("blend", "xps", "pmx"):
                    rec = registry.get("%s/%s/%s" % (mod["char"], fmt, name)) or {}
                    folder = os.path.join(char_dir, fmt, name)
                    main = os.path.join(folder, rec["main"]) if rec.get("main") else ""
                    if main and os.path.isfile(main):
                        files[fmt] = {"main": main, "folder": folder,
                                      "preview": os.path.join(folder, rec["preview"]) if rec.get("preview") else ""}
                blend_main = files.get("blend", {}).get("main", "")
                label = os.path.splitext(os.path.basename(blend_main))[0] if blend_main else name
                entry = next((e for e in manifest if e.get("label") in (label, name)), {})
                thumb = next((p for p in (os.path.join(game_dir, "_meta", "gallery", "thumbs", x + ".jpg")
                                          for x in (label, name)) if os.path.isfile(p)), "")
                preview = files.get("blend", {}).get("preview", "")
                dance = os.path.join(files["pmx"]["folder"], "preview_dance.png") if "pmx" in files else ""
                report = entry.get("pmx_report") or {}
                models.append({
                    "game": game, "game_title": info["title"], "mod": mod, "name": name, "char": mod["char"],
                    "note": NOTES.get(name, entry.get("variant") or ""), "files": files,
                    "thumb": thumb or (preview if os.path.isfile(preview) else ""),
                    "preview": preview if os.path.isfile(preview) else "",
                    "dance": dance if dance and os.path.isfile(dance) else "",
                    "vertices": entry.get("vertices") or 0, "bones": entry.get("bones") or 0,
                    "materials": entry.get("materials") or 0, "morphs": entry.get("morphs") or 0,
                    "size": os.path.getsize(blend_main) if blend_main else 0,
                    "height": report.get("height_m"), "rigid": report.get("rigid_bodies"),
                    "torn": (report.get("distortion") or {}).get("torn"),
                    "drift": (report.get("drop_test") or {}).get("max_drift_cm"),
                })
    return models


def render_card(m):
    esc = html.escape
    mod = m["mod"]
    url = "https://www.nexusmods.com/%s/mods/%d" % (mod["domain"], mod["id"])
    links = []
    for fmt, label in (("blend", "blend"), ("xps", "XPS"), ("pmx", "PMX")):
        f = m["files"].get(fmt)
        if f:
            links.append('<a href="%s">%s</a> <a class="dir" href="%s" title="打开目录">目录</a>' % (
                esc(file_uri(f["main"])), label, esc(file_uri(f["folder"]))))
    if m["dance"]:
        links.append('<a href="%s">PMX 跳舞预览</a>' % esc(file_uri(m["dance"])))
    spec = "%s 顶点 · %d 骨骼 · %d 材质%s · %s" % (
        "{:,}".format(m["vertices"]), m["bones"], m["materials"],
        (" · %d 表情" % m["morphs"]) if m["morphs"] else "", human_size(m["size"]))
    pmx = ""
    if m["height"]:
        pmx = "<dt>检查</dt><dd>PMX 身高 %.3f m · 刚体 %s · 撕裂 %s · 漂移 %s cm</dd>" % (
            m["height"], m["rigid"], m["torn"], m["drift"])
    # 每种格式的主文件位置：可点开，带复制按钮
    paths = "".join('<dt>%s</dt><dd><a href="%s">%s</a> <button class="copy" data-copy="%s">复制</button></dd>' % (
        label, esc(file_uri(m["files"][fmt]["main"])), esc(m["files"][fmt]["main"]), esc(m["files"][fmt]["main"]))
        for fmt, label in (("blend", "blend"), ("xps", "XPS"), ("pmx", "PMX")) if fmt in m["files"])
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(file_uri(m["thumb"])), esc(m["name"]))
              if m["thumb"] else '<div class="noimg">无预览图</div>')
    search = " ".join([m["name"], m["note"], m["char"], m["game_title"], mod["name"], mod["author"], str(mod["id"])]).lower()
    return """      <article class="card" data-search="{search}" data-game="{game}" data-mod="{modid}" data-body="{body}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener" title="点击看原图">{figure}</a>
        <div class="body">
          <div class="titlerow"><h3>{name}</h3></div>
          <div class="badges"><span class="badge badge-game">{game_title}</span><span class="badge badge-char">{char}</span>
            <span class="badge badge-body badge-{body}">{body_text}</span></div>
          <p class="note">{note}</p>
          <dl>
            <dt>mod</dt><dd><a href="{url}" target="_blank" rel="noopener">#{modid} {modname}</a> · 作者 {author}</dd>
            <dt>文件</dt><dd>{links}</dd>
            <dt>规格</dt><dd>{spec}</dd>
            {pmx}
            {paths}
          </dl>
        </div>
      </article>
""".format(search=esc(search), game=esc(m["game"]), modid=mod["id"], body=mod["body"],
           preview=esc(file_uri(m["preview"] or m["thumb"])), figure=figure, name=esc(m["name"]),
           game_title=esc(m["game_title"]), char=esc(m["char"]), body_text=esc(BODY[mod["body"]]),
           note=esc(m["note"]), url=esc(url), modname=esc(mod["name"]), author=esc(mod["author"]),
           links=" · ".join(links), spec=esc(spec), pmx=pmx, paths=paths)


def render(models):
    esc = html.escape
    games = [g for g in GAMES if any(m["game"] == g for m in models)]
    game_chips = "".join('<button class="chip" data-game="%s">%s</button>' % (g, esc(GAMES[g]["title"])) for g in games)
    mod_options = "".join('<option value="%d">#%d %s（%s）</option>' % (
        m["id"], m["id"], esc(m["name"]), esc(GAMES[m["game"]]["title"])) for m in MODS)
    body_options = "".join('<option value="%s">%s</option>' % (k, esc(v)) for k, v in BODY.items())
    rows = "".join("<tr><td>%s</td><td><a href=\"https://www.nexusmods.com/%s/mods/%d\" target=\"_blank\" rel=\"noopener\">#%d %s</a></td>"
                   "<td>%s</td><td>%s</td><td>%d</td><td>%s</td></tr>" % (
                       esc(GAMES[m["game"]]["title"]), m["domain"], m["id"], m["id"], esc(m["name"]), esc(m["author"]),
                       esc(m["char"]), sum(1 for x in models if x["mod"] is m), esc(BODY[m["body"]])) for m in MODS)
    return PAGE_TEMPLATE.format(
        generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), total=len(models), mods=len(MODS),
        games=len(games), xps=sum(1 for m in models if "xps" in m["files"]),
        pmx=sum(1 for m in models if "pmx" in m["files"]), size=human_size(sum(m["size"] for m in models)),
        game_chips=game_chips, mod_options=mod_options, body_options=body_options, rows=rows,
        cards="".join(render_card(m) for m in models))


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GANTZ mod 模型总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --shot: #d9dbe2;
  --mod: #7a3fa0; --mod-bg: #f1e7f8; --warn: #b4600a; --warn-bg: #fdf1e0; --ok: #1f7a3a; --ok-bg: #e3f4e6;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --shot: #2a2d34;
    --mod: #c99ae6; --mod-bg: #33203d; --warn: #e3a765; --warn-bg: #3a2c19; --ok: #5cc47e; --ok-bg: #1f3a28;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.6 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }}
header {{ padding: 28px 32px 20px; border-bottom: 1px solid var(--line); background: var(--panel); }}
h1 {{ margin: 0 0 6px; font-size: 22px; }}
.sub {{ color: var(--muted); font-size: 13px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 26px; margin-top: 16px; }}
.stat b {{ display: block; font-size: 21px; font-weight: 600; }}
.stat span {{ color: var(--muted); font-size: 12px; }}
.intro {{ margin-top: 14px; font-size: 13px; }}
.intro table {{ border-collapse: collapse; width: 100%; max-width: 980px; margin-top: 8px; }}
.intro th, .intro td {{ border-bottom: 1px solid var(--line); padding: 4px 8px; text-align: left; }}
.intro th {{ color: var(--muted); font-weight: 600; }}
.intro a {{ color: var(--accent); text-decoration: none; }}
.toolbar {{ position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  padding: 12px 32px; background: var(--panel); border-bottom: 1px solid var(--line); }}
#q {{ flex: 1 1 240px; min-width: 180px; padding: 8px 12px; font: inherit; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }}
select {{ padding: 6px 8px; font: inherit; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 7px; max-width: 100%; }}
.chip, .copy {{ font: inherit; font-size: 12px; padding: 5px 11px; cursor: pointer; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 999px; }}
.chip.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
main {{ padding: 22px 32px 48px; }}
.grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 11px; overflow: hidden;
  display: flex; flex-direction: column; }}
.card[hidden] {{ display: none !important; }}
.shot {{ display: block; background: var(--shot); line-height: 0; }}
.shot img {{ width: 100%; height: auto; display: block; }}
.noimg {{ padding: 46px 0; text-align: center; color: var(--muted); font-size: 12px; line-height: 1.6; }}
.body {{ padding: 12px 14px 14px; }}
.titlerow h3 {{ margin: 0 0 6px; font-size: 14px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
.badge-game {{ color: var(--accent); background: var(--bg); }}
.badge-char {{ color: var(--mod); background: var(--mod-bg); }}
.badge-normal, .badge-eve {{ color: var(--ok); background: var(--ok-bg); }}
.badge-big {{ color: var(--warn); background: var(--warn-bg); }}
.note {{ margin: 0 0 8px; font-size: 13px; }}
dl {{ margin: 0; display: grid; grid-template-columns: 42px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{ margin: 0; font-size: 12px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
dd a {{ color: var(--accent); text-decoration: none; }}
dd a:hover {{ text-decoration: underline; }}
dd a.dir {{ color: var(--muted); font-size: 11px; }}
.copy {{ padding: 1px 7px; margin-left: 6px; font-size: 11px; border-radius: 5px; }}
.empty {{ padding: 40px; text-align: center; color: var(--muted); }}
@media (max-width: 600px) {{
  header, .toolbar, main {{ padding-left: 16px; padding-right: 16px; }}
  .grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<header>
  <h1>GANTZ（杀戮都市）主题 mod 模型总览</h1>
  <div class="sub">生成于 {generated} · 只收 GANTZ 相关的 mod · 文件都在 <code>E:\\game_export</code> 归档里（本机链接，换机器需重新生成）</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>模型</span></div>
    <div class="stat"><b>{mods}</b><span>Nexus mod</span></div>
    <div class="stat"><b>{games}</b><span>游戏</span></div>
    <div class="stat"><b>{xps}</b><span>有 XPS</span></div>
    <div class="stat"><b>{pmx}</b><span>有 PMX</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
  </div>
  <div class="intro">
    <table>
      <tr><th>游戏</th><th>mod</th><th>作者</th><th>角色</th><th>模型</th><th>身材</th></tr>
      {rows}
    </table>
    <p>做法见仓库 <code>docs\\ff7-nexus-mods-export.md</code>（FF7 两作）、<code>scripts\\stellarblade\\README.md</code>（Stellar Blade）。
    画廊由 <code>scripts\\gantz\\html\\make_gallery.py</code> 生成。</p>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索模型名、说明、mod、作者…（按 / 聚焦）">
  <button class="chip on" data-game="">全部游戏</button>
  {game_chips}
  <select id="mod"><option value="">全部 mod</option>{mod_options}</select>
  <select id="body"><option value="">全部身材</option>{body_options}</select>
  <span class="count" id="count"></span>
</div>

<main>
  <div class="grid" id="grid">
{cards}  </div>
  <div class="empty" id="empty" hidden>没有匹配的模型</div>
</main>

<script>
(function () {{
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var q = document.getElementById('q'), count = document.getElementById('count'), empty = document.getElementById('empty');
  var modSel = document.getElementById('mod'), bodySel = document.getElementById('body');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var game = '';
  function apply() {{
    var term = q.value.trim().toLowerCase(), shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1) && (!game || card.dataset.game === game)
        && (!modSel.value || card.dataset.mod === modSel.value) && (!bodySel.value || card.dataset.body === bodySel.value);
      card.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
    empty.hidden = shown !== 0;
  }}
  q.addEventListener('input', apply);
  modSel.addEventListener('change', apply);
  bodySel.addEventListener('change', apply);
  chips.forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      chips.forEach(function (other) {{ other.classList.remove('on'); }});
      chip.classList.add('on');
      game = chip.dataset.game || '';
      apply();
    }});
  }});
  document.addEventListener('keydown', function (event) {{
    if (event.key === '/' && document.activeElement !== q) {{ event.preventDefault(); q.focus(); }}
  }});
  document.addEventListener('click', function (event) {{
    var button = event.target.closest('.copy');
    if (!button) return;
    var text = button.dataset.copy;
    var done = function () {{ var old = button.textContent; button.textContent = '已复制';
      setTimeout(function () {{ button.textContent = old; }}, 1200); }};
    if (navigator.clipboard && window.isSecureContext) {{ navigator.clipboard.writeText(text).then(done); return; }}
    var area = document.createElement('textarea');       // file:// 不是安全上下文
    area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.appendChild(area); area.select();
    try {{ document.execCommand('copy'); done(); }} catch (err) {{ /* ignore */ }}
    document.body.removeChild(area);
  }});
  apply();
}})();
</script>
</body>
</html>
"""


def main():
    models = collect()
    if not models:
        raise SystemExit("E:\\game_export 里没找到 GANTZ mod 的模型")
    with open(PAGE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(models))
    missing = [m["name"] for m in models if not m["thumb"]]
    print("models      : %d（%s）" % (len(models), "、".join(
        "%s %d" % (GAMES[g]["title"], sum(1 for m in models if m["game"] == g)) for g in GAMES)))
    print("xps / pmx   : %d / %d" % (sum(1 for m in models if "xps" in m["files"]),
                                     sum(1 for m in models if "pmx" in m["files"])))
    print("no thumbnail: %d%s" % (len(missing), (" -> " + ", ".join(missing)) if missing else ""))
    print("page        : %s" % PAGE)


if __name__ == "__main__":
    main()
