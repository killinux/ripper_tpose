"""把 FF7 Rebirth 的导出产物做成一页可浏览的 HTML 画廊。

读 ``ff7rebirth_gallery_manifest.json``（由 collect_manifest.py 从 export_ff7rb_models.ps1 的 manifest 转换），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\ff7rebirth_exports\\materialized --force
"""

import argparse
import datetime
import html
import json
import os
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 720
THUMB_QUALITY = 82
PAGE_NAME = "index.html"
KIND_LABELS = {"official": "主服装", "cutscene": "过场专用（PC7xxx）", "toad": "蛤蟆形态"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\ff7rebirth_exports\materialized",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\ff7rebirth_gallery_manifest.json）")
    p.add_argument("--out", default=None, help="输出 HTML（默认本脚本旁的 index.html）")
    p.add_argument("--thumb-dir", default=None,
                   help="缩略图目录（默认 <导出根>\\_gallery\\thumbs）")
    p.add_argument("--force", action="store_true", help="即使缩略图是新的也重建")
    return p.parse_args()


def human_size(num_bytes):
    if not num_bytes:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return "%.0f %s" % (num_bytes, unit) if unit == "B" else "%.1f %s" % (num_bytes, unit)
        num_bytes /= 1024.0
    return "-"


def file_uri(path):
    try:
        return Path(path).as_uri()
    except (ValueError, OSError):
        return ""


def build_thumb(preview_path, thumb_path, force):
    if not preview_path or not os.path.isfile(preview_path):
        return None
    if (not force and os.path.isfile(thumb_path)
            and os.path.getmtime(thumb_path) >= os.path.getmtime(preview_path)):
        return thumb_path
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    with Image.open(preview_path) as image:
        image = image.convert("RGB")
        if image.width > THUMB_WIDTH:
            height = max(1, round(image.height * THUMB_WIDTH / image.width))
            image = image.resize((THUMB_WIDTH, height), Image.LANCZOS)
        image.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return thumb_path


def collect(manifest_path, thumb_dir, force):
    with open(manifest_path, encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    models = []
    for entry in manifest.get("results", []):
        label = entry.get("label") or ""
        thumb = build_thumb(entry.get("preview"), os.path.join(thumb_dir, label + ".jpg"), force)
        models.append({
            "label": label,
            "char": entry.get("char") or "",
            "code": entry.get("code") or "",
            "variant": entry.get("variant") or "",
            "kind": entry.get("kind") or "official",
            "blend": entry.get("blend") or "",
            "preview": entry.get("preview") or "",
            "thumb": thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "meshes": entry.get("meshes") or 0,
            "vertices": entry.get("vertices") or 0,
            "polygons": entry.get("polygons") or 0,
            "bones": entry.get("bones") or 0,
            "materials": entry.get("materials") or 0,
            "alpha": entry.get("alphaMaterials") or 0,
            "warnings": list(entry.get("warnings") or []),
        })
    models.sort(key=lambda m: m["label"])
    return manifest, models


def render_card(model):
    esc = html.escape
    thumb_uri = file_uri(model["thumb"])
    preview_uri = file_uri(model["preview"])
    blend_uri = file_uri(model["blend"])

    badges = ""
    if model["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">告警 %d</span>' % (
            esc("; ".join(model["warnings"])), len(model["warnings"]))
    if model["kind"] != "official":
        badges += '<span class="badge badge-mod">%s</span>' % esc(KIND_LABELS[model["kind"]])
    if model["code"]:
        badges += '<span class="badge badge-code">%s</span>' % esc(model["code"])

    search_blob = esc(" ".join([model["label"], model["char"], model["variant"], model["code"], model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-chr="{chr}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{label}</h3>{badges}
          </div>
          <dl>
            <dt>角色</dt><dd>{chr} · {variant}</dd>
            <dt>规格</dt>
            <dd>{meshes} 网格 · {vertices} 顶点 · {bones} 骨骼 · {materials} 材质（{alpha} 透明） · {size}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]), chr=esc(model["char"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, label=esc(model["label"]),
           badges=badges, variant=esc(model["variant"] or "-"),
           meshes=model["meshes"], vertices=model["vertices"], bones=model["bones"],
           materials=model["materials"], alpha=model["alpha"],
           size=human_size(model["blend_size"]),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]))


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    characters = len({m["char"] for m in models})
    warned = sum(1 for m in models if m["warnings"])
    mods = sum(1 for m in models if m["kind"] != "official")
    kinds = [k for k in ("official", "cutscene", "toad") if any(m["kind"] == k for m in models)]
    per_char = {}
    for m in models:
        per_char[m["char"]] = per_char.get(m["char"], 0) + 1
    chr_options = "".join('<option value="%s">%s (%d)</option>' % (esc(c), esc(c), n)
                          for c, n in sorted(per_char.items()))
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    chips = "".join('<button class="chip" data-kind="%s">%s</button>' % (esc(k), esc(KIND_LABELS[k]))
                    for k in kinds)
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, mods=mods, chips=chips, chr_options=chr_options, cards=cards)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FF7 Rebirth 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --mod: #7a3fa0; --mod-bg: #f1e7f8; --shot: #d9dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --mod: #c99ae6; --mod-bg: #33203d; --shot: #2a2d34;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.6 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
}}
header {{ padding: 28px 32px 20px; border-bottom: 1px solid var(--line); background: var(--panel); }}
h1 {{ margin: 0 0 6px; font-size: 22px; }}
.sub {{ color: var(--muted); font-size: 13px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 26px; margin-top: 16px; }}
.stat b {{ display: block; font-size: 21px; font-weight: 600; }}
.stat span {{ color: var(--muted); font-size: 12px; }}
.toolbar {{
  position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap;
  gap: 10px; align-items: center; padding: 12px 32px;
  background: var(--panel); border-bottom: 1px solid var(--line);
}}
#q {{
  flex: 1 1 260px; min-width: 200px; padding: 8px 12px; font: inherit;
  color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 7px;
}}
.chip, .copy, .toggle {{
  font: inherit; font-size: 12px; padding: 5px 11px; cursor: pointer;
  color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 999px;
}}
.chip.on, .toggle.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
main {{ padding: 22px 32px 48px; }}
.grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }}
.card {{
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 11px; overflow: hidden; display: flex; flex-direction: column;
}}
/* 作者写的 display 会盖过 UA 的 [hidden] 规则，筛选必须显式声明 */
.card[hidden] {{ display: none !important; }}
.shot {{ display: block; background: var(--shot); line-height: 0; }}
.shot img {{ width: 100%; height: auto; display: block; }}
.noimg {{ padding: 46px 0; text-align: center; color: var(--muted); font-size: 12px; }}
.body {{ padding: 12px 14px 14px; }}
.titlerow {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
.titlerow h3 {{ margin: 0; font-size: 15px; font-family: Consolas, monospace; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; cursor: help; }}
.badge-warn {{ color: var(--warn); background: var(--warn-bg); }}
.badge-mod {{ color: var(--mod); background: var(--mod-bg); cursor: default; }}
.badge-code {{ color: var(--accent); background: var(--bg); cursor: default; font-family: Consolas, monospace; }}
#chr {{ padding: 6px 8px; font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }}
dl {{ margin: 0; display: grid; grid-template-columns: 42px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{ margin: 0; font-size: 12px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
dd a {{ color: var(--accent); text-decoration: none; }}
dd a:hover {{ text-decoration: underline; }}
.copy {{ padding: 1px 7px; margin-left: 6px; font-size: 11px; border-radius: 5px; }}
.empty {{ padding: 40px; text-align: center; color: var(--muted); }}
section.appendix {{
  margin-top: 40px; padding: 24px 28px; background: var(--panel);
  border: 1px solid var(--line); border-radius: 11px;
}}
section.appendix h2 {{ margin-top: 0; font-size: 18px; }}
section.appendix h3 {{ font-size: 14px; margin: 22px 0 6px; }}
pre {{
  background: var(--bg); border: 1px solid var(--line); border-radius: 8px;
  padding: 12px 14px; overflow-x: auto; font-family: Consolas, monospace; font-size: 12.5px;
}}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; }}
th {{ color: var(--muted); font-weight: 600; }}
td code, li code, p code {{ font-family: Consolas, monospace; }}
.note {{
  border-left: 3px solid var(--warn); background: var(--warn-bg);
  color: var(--ink); padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 14px 0;
}}
</style>
</head>
<body>
<header>
  <h1>FF7 Rebirth 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>覆盖角色</span></div>
    <div class="stat"><b>{mods}</b><span>过场/蛤蟆变体</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索角色、服装名、包编号或路径…（按 / 聚焦）">
  <select id="chr"><option value="">全部角色</option>{chr_options}</select>
  <button class="chip on" data-kind="">全部</button>
  {chips}
  <button class="toggle" id="warnOnly">只看告警</button>
  <span class="count" id="count"></span>
</div>

<main>
  <div class="grid" id="grid">
{cards}  </div>
  <div class="empty" id="empty" hidden>没有匹配的模型</div>

  <section class="appendix">
    <h2>附录 · 导出脚本用法</h2>
    <p>脚本在 <code>scripts\\final\\</code>。完整说明见 <code>docs\\final-fantasy-vii-rebirth-extraction.md</code>
      与 <code>docs\\ff7rebirth-player-export-inventory.md</code>。</p>

    <h3>三段流程</h3>
    <table>
      <tr><th>步骤</th><th>工具</th><th>做什么</th></tr>
      <tr><td>① 提取</td><td>FModel（GAME_FinalFantasy7Rebirth profile + usmap）</td><td>右键 <code>End/Content/Character/Player</code> →
        <b>Save Folder's Packages Models</b>，一次导出全部变体的 ActorX PSKX + PNG + 材质 JSON。
        网格格式必须是 <b>ActorX</b>（UEFormat 出来的 .uemodel 材质化脚本不认）。
        可用 <code>scripts\\final\\fmodel_export_player.py</code>（pywinauto）代替手点。</td></tr>
      <tr><td>② 材质化</td><td><code>export_ff7rb_models.ps1</code> + <code>export_ff7rb_model_blender.py</code></td><td>按材质 JSON 匹配贴图、DirectX→OpenGL 法线、ORM、分层眼球，出 .blend（可选 fbx/glb）</td></tr>
      <tr><td>③ 预览</td><td><code>html\\render_blend_preview.py</code></td><td>给每个 .blend 渲一张正面预览</td></tr>
    </table>
    <pre>cd E:\\code\\othercode\\ripper_tpose\\scripts\\final
.\\export_ff7rb_models.ps1 -List
.\\export_ff7rb_models.ps1                    # 磁盘上所有有模型的变体 -> .blend
blender --background --python html\\render_blend_preview.py -- D:\\ff7rebirth_exports\\materialized
python html_rebirth\\collect_manifest.py
python html_rebirth\\make_gallery.py</pre>

    <h3>命名规律</h3>
    <table>
      <tr><th>编号</th><th>含义</th></tr>
      <tr><td><code>PC0000</code>~<code>PC0008</code></td><td>Cloud / Barret / Tifa / Aerith / Red XIII / Yuffie / Sonon / Cait Sith / Zack 等</td></tr>
      <tr><td><code>_00</code>~<code>_2x</code></td><td>服装与状态变体（标准、Costa 泳装、Soldier、Loveless 舞台、换装中、无夹克…）</td></tr>
      <tr><td><code>PC7xxx</code></td><td>过场专用版本</td></tr>
      <tr><td><code>PC0099</code></td><td>蛤蟆（Toad）状态</td></tr>
    </table>
    <div class="note"><b>官方没有 nude</b>。只有材质/贴图的变体（湿身、眼泪、血迹、脏污、全息）没有独立网格，
      不出现在本页。</div>

    <h3>已知坑</h3>
    <table>
      <tr><th>症状</th><th>原因 / 处理</th></tr>
      <tr><td>FModel 日志「Read incorrect amount of tangent bytes」</td><td>Rebirth 的 tangent 精度与 reader 假设不一致，FModel 记录错误后仍保留网格并完成 ActorX 导出；glTF 会失败，所以用 ActorX</td></tr>
      <tr><td>导出目录里只有 .uemodel</td><td>FModel 的 Mesh Format 被切成了 UEFormat；改回 ActorX 重导</td></tr>
      <tr><td>贴图缺失</td><td>变体常引用其它目录的贴图，worker 的贴图索引覆盖整个 Character 树；仍缺的记在 manifest <code>missingBase</code></td></tr>
    </table>

    <h3>重新生成本页</h3>
    <pre>python scripts\\final\\html_rebirth\\collect_manifest.py
python scripts\\final\\html_rebirth\\make_gallery.py</pre>
    <p>缩略图写在 <code>_gallery\\thumbs\\</code>，<b>刻意不进仓库</b>。</p>
  </section>
</main>

<script>
(function () {{
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var q = document.getElementById('q');
  var count = document.getElementById('count');
  var empty = document.getElementById('empty');
  var warnOnly = document.getElementById('warnOnly');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var chrSel = document.getElementById('chr');
  var kind = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!kind || card.dataset.kind === kind)
        && (!chrSel.value || card.dataset.chr === chrSel.value)
        && (!onlyWarn || card.dataset.warn === '1');
      card.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
    empty.hidden = shown !== 0;
  }}

  q.addEventListener('input', apply);
  chrSel.addEventListener('change', apply);
  warnOnly.addEventListener('click', function () {{
    warnOnly.classList.toggle('on');
    apply();
  }});
  chips.forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      chips.forEach(function (other) {{ other.classList.remove('on'); }});
      chip.classList.add('on');
      kind = chip.dataset.kind || '';
      apply();
    }});
  }});
  document.addEventListener('keydown', function (event) {{
    if (event.key === '/' && document.activeElement !== q) {{
      event.preventDefault();
      q.focus();
    }}
  }});
  document.addEventListener('click', function (event) {{
    var button = event.target.closest('.copy');
    if (!button) return;
    var text = button.dataset.copy;
    var done = function () {{
      var old = button.textContent;
      button.textContent = '已复制';
      setTimeout(function () {{ button.textContent = old; }}, 1200);
    }};
    // navigator.clipboard 需要安全上下文，file:// 不是
    if (navigator.clipboard && window.isSecureContext) {{
      navigator.clipboard.writeText(text).then(done);
      return;
    }}
    var area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
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
    args = parse_args()
    source_root = os.path.abspath(args.source_root)
    manifest_path = args.manifest or os.path.join(source_root, "ff7rebirth_gallery_manifest.json")
    thumb_dir = args.thumb_dir or os.path.join(source_root, "_gallery", "thumbs")
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), PAGE_NAME)
    if not os.path.isfile(manifest_path):
        raise SystemExit("找不到 manifest: %s\n先跑一次 collect_manifest.py" % manifest_path)

    _manifest, models = collect(manifest_path, thumb_dir, args.force)
    if not models:
        raise SystemExit("manifest 里没有条目: %s" % manifest_path)

    page = render(models, source_root)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)

    missing = [m["label"] for m in models if not m["thumb"]]
    print("models      : %d（过场/蛤蟆变体 %d）" % (len(models), sum(1 for m in models if m["kind"] != "official")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
