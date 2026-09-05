"""Build a browsable HTML gallery of the materialized Rise of Eros models.

Reads ``character_models_manifest.json`` (written by export_character_models.ps1),
shrinks each composite preview into a JPEG thumbnail and emits a self-contained
``index.html`` next to this script.

The page links to the real files with ``file://`` URLs and the thumbnails are
written under the export root, so **no game-derived image ever enters the repo**
— same rule as every other script here.  Re-run this after a new export batch.

Usage:
  python make_gallery.py
  python make_gallery.py --source-root D:\\roe_exports --force
"""

import argparse
import html
import json
import os
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 720
THUMB_QUALITY = 82
PAGE_NAME = "index.html"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=r"D:\roe_exports",
                        help="export root holding <id>\\blend\\ (default: %(default)s)")
    parser.add_argument("--manifest", default=None,
                        help="manifest path (default: <source-root>\\character_models_manifest.json)")
    parser.add_argument("--out", default=None,
                        help="output HTML (default: index.html beside this script)")
    parser.add_argument("--thumb-dir", default=None,
                        help="thumbnail directory (default: <source-root>\\_gallery\\thumbs)")
    parser.add_argument("--force", action="store_true",
                        help="rebuild thumbnails even when they are up to date")
    return parser.parse_args()


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
    """Return the thumbnail path, rebuilding it only when stale."""
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

    models, nomesh = [], []
    for entry in manifest.get("results", []):
        key = entry.get("model") or ""
        if entry.get("status") != "PASS":
            nomesh.append({
                "key": key,
                "reason": entry.get("reason") or entry.get("error") or "",
            })
            continue
        blend = entry.get("output") or ""
        preview = entry.get("preview") or ""
        outputs = entry.get("outputs") or {}
        xps = outputs.get("xps") or ""
        if xps and not os.path.isfile(xps):
            xps = ""
        thumb = build_thumb(preview, os.path.join(thumb_dir, key + ".jpg"), force)
        warnings = []
        for label, values in (("缺贴图", entry.get("untexturedSlots")),
                              ("异体型贴图", entry.get("familyMismatches"))):
            for value in (values or []):
                warnings.append("%s: %s" % (label, value))
        models.append({
            "key": key,
            "family": (key[:1] or "?").upper(),
            "source": entry.get("source") or "",
            "blend": blend,
            "xps": xps,
            "preview": preview,
            "thumb": thumb or "",
            "blend_size": os.path.getsize(blend) if blend and os.path.isfile(blend) else 0,
            "meshes": entry.get("meshes") or 0,
            "materials": entry.get("materials") or 0,
            "textures": len(entry.get("textures") or []),
            "recovered": list(entry.get("recoveredSlots") or []),
            "warnings": warnings,
        })
    models.sort(key=lambda item: item["key"])
    nomesh.sort(key=lambda item: item["key"])
    return manifest, models, nomesh


def render_card(model):
    esc = html.escape
    thumb_uri = file_uri(model["thumb"])
    preview_uri = file_uri(model["preview"])
    blend_uri = file_uri(model["blend"])
    badges = ""
    if model["recovered"]:
        badges += '<span class="badge badge-fix" title="%s">补挂 %d</span>' % (
            esc("; ".join(model["recovered"])), len(model["recovered"]))
    if model["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">缺图 %d</span>' % (
            esc("; ".join(model["warnings"])), len(model["warnings"]))
    search_blob = esc(" ".join([model["key"], os.path.basename(model["source"]),
                                model["blend"], model["xps"]]).lower())
    xps_row = ""
    if model["xps"]:
        xps_dir = os.path.dirname(model["xps"])
        xps_row = ('<dt>XPS</dt>\n            <dd><a href="%s" title="%s">%s</a>\n'
                   '                <button class="copy" data-copy="%s">复制</button></dd>\n            '
                   % (esc(file_uri(xps_dir)), esc(model["xps"]), esc(model["xps"]),
                      esc(model["xps"])))
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["key"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-family="{family}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图（{family} 家族）">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{key}</h3>{badges}
          </div>
          <dl>
            <dt>源 FBX</dt><dd>{fbx}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
            {xps_row}<dt>规格</dt>
            <dd>{meshes} 网格 · {materials} 材质槽 · {textures} 贴图 · {size}</dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, family=esc(model["family"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, key=esc(model["key"]),
           badges=badges, fbx=esc(os.path.basename(model["source"])),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]), xps_row=xps_row,
           meshes=model["meshes"], materials=model["materials"],
           textures=model["textures"], size=human_size(model["blend_size"]))


def render(manifest, models, nomesh, source_root):
    esc = html.escape
    families = sorted({model["family"] for model in models})
    total_bytes = sum(model["blend_size"] for model in models)
    characters = len({model["key"].split("_")[0] for model in models})
    warned = sum(1 for model in models if model["warnings"])
    generated = (manifest.get("generatedAt") or "")[:19].replace("T", " ")

    chips = "".join(
        '<button class="chip" data-family="%s">%s</button>' % (esc(item), esc(item))
        for item in families)
    cards = "".join(render_card(model) for model in models)
    nomesh_rows = "".join(
        "        <li><code>%s</code><span>%s</span></li>\n" % (esc(item["key"]), esc(item["reason"]))
        for item in nomesh)

    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, nomesh_count=len(nomesh), chips=chips, cards=cards,
        nomesh_rows=nomesh_rows)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rise of Eros 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --fix: #1d7a52; --fix-bg: #e4f5ec; --shot: #d9dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --fix: #6fd3a4; --fix-bg: #1b3a2c; --shot: #2a2d34;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.6 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
}}
header {{
  padding: 28px 32px 20px; border-bottom: 1px solid var(--line); background: var(--panel);
}}
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
  color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 7px;
}}
.chip, .copy, .toggle {{
  font: inherit; font-size: 12px; padding: 5px 11px; cursor: pointer;
  color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 999px;
}}
.chip.on, .toggle.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
main {{ padding: 22px 32px 48px; }}
.grid {{
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
}}
.card {{
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 11px; overflow: hidden; display: flex; flex-direction: column;
}}
/* An author `display` beats the UA rule for [hidden], so filtering needs this. */
.card[hidden] {{ display: none !important; }}
.shot {{ display: block; background: var(--shot); line-height: 0; }}
.shot img {{ width: 100%; height: auto; display: block; }}
.noimg {{
  padding: 46px 0; text-align: center; color: var(--muted);
  font-size: 12px; line-height: 1.5;
}}
.body {{ padding: 12px 14px 14px; }}
.titlerow {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.titlerow h3 {{ margin: 0; font-size: 15px; font-family: Consolas, monospace; }}
.badge {{
  font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; cursor: help;
}}
.badge-warn {{ color: var(--warn); background: var(--warn-bg); }}
.badge-fix {{ color: var(--fix); background: var(--fix-bg); }}
dl {{ margin: 0; display: grid; grid-template-columns: 58px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{
  margin: 0; font-size: 12px; font-family: Consolas, monospace;
  overflow-wrap: anywhere;
}}
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
td code, li code {{ font-family: Consolas, monospace; }}
.nomesh {{ list-style: none; padding: 0; margin: 8px 0 0;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 4px; }}
.nomesh li {{ display: flex; gap: 10px; font-size: 12.5px; }}
.nomesh span {{ color: var(--muted); }}
.note {{
  border-left: 3px solid var(--warn); background: var(--warn-bg);
  color: var(--ink); padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 14px 0;
}}
</style>
</head>
<body>
<header>
  <h1>Rise of Eros 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>覆盖角色</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有缺图告警</span></div>
    <div class="stat"><b>{nomesh_count}</b><span>无独立网格</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索模型名、源 FBX 或路径…（按 / 聚焦）">
  <button class="chip on" data-family="">全部</button>
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
    <p>脚本都在 <code>scripts\\riseoferos\\</code>，需在装有游戏的机器上运行。整个流程分两步：
      先从 AssetBundle 提取白模，再无头重建材质。</p>

    <h3>第一步 · 提取（extract_character.ps1）</h3>
    <pre>cd E:\\code\\othercode\\ripper_tpose\\scripts\\riseoferos

.\\extract_character.ps1 -List                        # 列出全部角色 ID
.\\extract_character.ps1 m02 -ExportTextures          # 提取单个角色
.\\extract_character.ps1 j10,k02,m01 -ExportTextures  # 逗号分隔批量</pre>
    <p><code>-ExportTextures</code> 必须加，否则不导贴图，第二步会因缺少共享头部贴图而失败。
      产物在 <code>D:\\roe_exports\\&lt;id&gt;\\</code>。</p>

    <h3>第二步 · 材质化（export_character_models.ps1）</h3>
    <pre>.\\export_character_models.ps1 -List            # 看可转清单和各自用哪份 FBX
.\\export_character_models.ps1                  # 全部，已有产物自动跳过
.\\export_character_models.ps1 -Only m02        # 只转一个
.\\export_character_models.ps1 -Only m02 -Force # 重做，覆盖已有产物</pre>
    <p>产出 <code>&lt;id&gt;\\blend\\&lt;模型名&gt;.blend</code>（贴图已打包进文件）
      与同名 <code>_preview.png</code>。</p>

    <table>
      <tr><th>参数</th><th>作用</th></tr>
      <tr><td><code>-Only &lt;ids&gt;</code></td><td>写 <code>m01</code> 连 outfit 变体一起转；写 <code>m01_outfit1</code> 只转那一套</td></tr>
      <tr><td><code>-Force</code></td><td>覆盖重做；不加时 blend 与预览图都在的会 SKIP</td></tr>
      <tr><td><code>-Format blend,glb</code></td><td>额外导 GLB 到 <code>blend\\glb\\</code>，缺省只有 blend</td></tr>
      <tr><td><code>-Format xps -NoPreview</code></td><td>给已有 blend 的角色补带材质 XPS 到 <code>blend\\xps\\&lt;stem&gt;\\</code>（.mesh + 同目录 PNG）</td></tr>
      <tr><td><code>-NoPreview</code></td><td>不渲预览图（实测只快约 9%，一般没必要关）</td></tr>
      <tr><td><code>-ValidateOnly</code></td><td>只检查材质不写文件，排查用</td></tr>
      <tr><td><code>-ManifestPath</code></td><td>自定义清单路径；<b>多进程分片并行时每个分片必须各给一个</b></td></tr>
    </table>

    <h3>两个容易踩的坑</h3>
    <div class="note"><b>重新提取会删掉 blend 目录。</b>
      <code>extract_character.ps1 &lt;id&gt;</code> 会把 <code>D:\\roe_exports\\&lt;id&gt;\\</code>
      整个删掉重建，第二步生成的 <code>blend\\</code> 也一起没。顺序永远是先提取后转换；
      要重提某个角色，先把 blend 挪出去。</div>
    <p>报 <code>缺少贴图: face, eye_iris, eyebrow</code> 说明该角色目录是旧流程导的、
      缺同字母体型的公共头部贴图。补跑一次
      <code>.\\extract_character.ps1 &lt;id&gt; -ExportTextures</code> 再转即可。</p>

    <h3>并行加速</h3>
    <pre>.\\export_character_models.ps1 -Only a01,a02,a03 -ManifestPath D:\\tmp\\shard0.json -Force</pre>
    <p>默认那一个清单文件不支持并发写，分片时必须各给一个，跑完再合并。
      全量 123 个条目用 6 分片并行，24 核机器约 25 分钟。</p>

    <h3>重新生成本页</h3>
    <pre>python scripts\\riseoferos\\html\\make_gallery.py</pre>
    <p>读 <code>character_models_manifest.json</code>，把预览图缩成 JPEG 缩略图放进
      <code>D:\\roe_exports\\_gallery\\thumbs\\</code>，再重写本页。
      <b>缩略图刻意不放进仓库</b>——和其它脚本一样，仓库不收任何游戏素材。</p>

    <h3>没有 blend 的 {nomesh_count} 个 ID</h3>
    <p>不是导出失败，是资源本身没有独立网格：只有 <code>chara_bare_pc_&lt;id&gt;_nk.ab</code>
      的活动 NPC，或全部候选都是纯骨架壳。它们的本体复用同字母基础体。</p>
    <ul class="nomesh">
{nomesh_rows}    </ul>
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
  var family = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!family || card.dataset.family === family)
        && (!onlyWarn || card.dataset.warn === '1');
      card.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
    empty.hidden = shown !== 0;
  }}

  q.addEventListener('input', apply);
  warnOnly.addEventListener('click', function () {{
    warnOnly.classList.toggle('on');
    apply();
  }});
  chips.forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      chips.forEach(function (other) {{ other.classList.remove('on'); }});
      chip.classList.add('on');
      family = chip.dataset.family || '';
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
    // navigator.clipboard needs a secure context, which file:// is not.
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
    manifest_path = args.manifest or os.path.join(
        source_root, "character_models_manifest.json")
    thumb_dir = args.thumb_dir or os.path.join(source_root, "_gallery", "thumbs")
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        PAGE_NAME)
    if not os.path.isfile(manifest_path):
        raise SystemExit("manifest not found: %s\n先跑一次 export_character_models.ps1"
                         % manifest_path)

    manifest, models, nomesh = collect(manifest_path, thumb_dir, args.force)
    if not models:
        raise SystemExit("manifest has no PASS entries: %s" % manifest_path)

    page = render(manifest, models, nomesh, source_root)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)

    missing = [model["key"] for model in models if not model["thumb"]]
    print("models      : %d" % len(models))
    print("no preview  : %d%s" % (len(missing),
                                  (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("nomesh      : %d" % len(nomesh))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
