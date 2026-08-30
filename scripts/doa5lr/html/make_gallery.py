"""把 DOA5LR 的导出产物做成一页可浏览的 HTML 画廊。

读 ``doa5lr_models_manifest.json``（由 collect_manifest.py 在 Blender 无头下生成），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\doa5lr_exports --force
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 720
THUMB_QUALITY = 82
PAGE_NAME = "index.html"
DEFAULT_GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round"
# 只扫这两个封包：常规服装/发型都在里面（其余是场景/过场，与本页无关）
ARCHIVES = ("chara_common", "chara_initial")
COS001_RE = re.compile(r"^([A-Z0-9]+)_COS_001\.TMC$")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\doa5lr_exports",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\doa5lr_models_manifest.json）")
    p.add_argument("--out", default=None, help="输出 HTML（默认本脚本旁的 index.html）")
    p.add_argument("--thumb-dir", default=None,
                   help="缩略图目录（默认 <导出根>\\_gallery\\thumbs）")
    p.add_argument("--game-root", default=DEFAULT_GAME,
                   help="游戏目录，用于标注每个角色在哪个封包；给不到就跳过该facet")
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


def map_archives(game_root):
    """角色前缀 -> 所在封包。拿不到游戏目录就返回空表（页面自动隐藏该 facet）。"""
    if not game_root or not os.path.isdir(game_root):
        return {}
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from extract_lnk import load_name_db, parse_bin
    except ImportError:
        return {}
    default_db = os.path.join(r"E:\tools\doa5lr", "file5lr.dat")
    if not os.path.isfile(default_db):
        return {}
    names = load_name_db(default_db)
    mapping = {}
    for archive in ARCHIVES:
        bin_path = os.path.join(game_root, archive + ".bin")
        if not os.path.isfile(bin_path):
            continue
        try:
            entries = parse_bin(bin_path)
        except Exception:
            continue
        for enc in entries:
            real = names.get(enc, ("", None))[0]
            # 必须精确匹配 <角色>_COS_001.TMC —— 松散地用 "in" 会被
            # KASUMI_BOSS_COS_001.TMC 之类命中，把霞误标成 chara_common
            m = COS001_RE.match(real)
            if m:
                mapping.setdefault(m.group(1), archive)
    return mapping


def collect(manifest_path, thumb_dir, force, archives):
    with open(manifest_path, encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    models = []
    for entry in manifest.get("results", []):
        label = entry.get("label") or ""
        thumb = build_thumb(entry.get("preview"), os.path.join(thumb_dir, label + ".jpg"), force)
        parts = entry.get("parts") or {}
        models.append({
            "label": label,
            "char": entry.get("char") or "",
            "archive": archives.get(entry.get("char") or "", ""),
            "blend": entry.get("blend") or "",
            "preview": entry.get("preview") or "",
            "thumb": thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "meshes": entry.get("meshes") or 0,
            "materials": entry.get("materials") or 0,
            "alpha": entry.get("alphaMaterials") or 0,
            "images": entry.get("images") or 0,
            "parts": parts,
            "part_tex": entry.get("partTextures") or {},
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
    if model["archive"]:
        badges += '<span class="badge badge-arc">%s</span>' % esc(model["archive"])

    parts = model["parts"]
    part_txt = " · ".join(
        "%s %d" % (label, parts.get(key, 0))
        for key, label in (("body", "身体"), ("face", "脸"), ("hair", "头发"))
        if parts.get(key))
    other = parts.get("other", 0)
    if other:
        part_txt += " · 其它 %d" % other

    search_blob = esc(" ".join([model["label"], model["char"], model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-arc="{arc}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{label}</h3>{badges}
          </div>
          <dl>
            <dt>部件</dt><dd>{parts}</dd>
            <dt>规格</dt>
            <dd>{meshes} 网格 · {materials} 材质（{alpha} 透明） · {images} 贴图 · {size}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, arc=esc(model["archive"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, label=esc(model["label"]),
           badges=badges, parts=esc(part_txt or "-"),
           meshes=model["meshes"], materials=model["materials"], alpha=model["alpha"],
           images=model["images"], size=human_size(model["blend_size"]),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]))


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    characters = len({m["char"] for m in models})
    warned = sum(1 for m in models if m["warnings"])
    archives = sorted({m["archive"] for m in models if m["archive"]})
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    chips = "".join('<button class="chip" data-arc="%s">%s</button>' % (esc(a), esc(a))
                    for a in archives)
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, chips=chips, cards=cards)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DOA5LR 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --arc: #1d7a52; --arc-bg: #e4f5ec; --shot: #d9dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --arc: #6fd3a4; --arc-bg: #1b3a2c; --shot: #2a2d34;
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
.badge-arc {{ color: var(--arc); background: var(--arc-bg); cursor: default; }}
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
  <h1>DOA5LR 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>覆盖角色</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索角色名或路径…（按 / 聚焦）">
  <button class="chip on" data-arc="">全部</button>
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
    <p>脚本在 <code>scripts\\doa5lr\\</code>，需在装有游戏的机器上运行。
      完整说明见同目录 <code>EXPORT_GUIDE.md</code>（操作）与 <code>README.md</code>（格式与原理）。</p>

    <h3>角色由三个 TMC 组成</h3>
    <table>
      <tr><th>部件</th><th>条目名</th><th>不加会怎样</th></tr>
      <tr><td>服装 + 身体</td><td><code>&lt;角色&gt;_COS_NNN</code></td><td>—</td></tr>
      <tr><td>脸</td><td><code>&lt;角色&gt;_FACE</code>（无编号）</td><td>不加 <code>-Face</code> → 无头</td></tr>
      <tr><td>头发</td><td><code>&lt;角色&gt;_HAIR_NNN</code></td><td>不加 <code>-Hair</code> → 光头</td></tr>
    </table>

    <h3>一键出带材质 blend（export_full.ps1）</h3>
    <pre>cd E:\\code\\othercode\\ripper_tpose\\scripts\\doa5lr

.\\export_full.ps1 KASUMI_COS_001 -Archive chara_initial -Face auto -Hair 001 -Label KASUMI_Kasumi
.\\export_full.ps1 MARIE_COS_001 -Face auto -Hair 001 -Label MARIE_MarieRose</pre>
    <p>产物是 <code>_blends\\&lt;Label&gt;.blend</code>（贴图已打包进文件）和同名
      <code>_preview.png</code>。卡片上的绿色徽标就是该角色所在封包，对应
      <code>-Archive</code> 参数。</p>

    <h3>查条目名 / 换服装</h3>
    <pre>python extract_lnk.py "&lt;游戏&gt;\\chara_initial.bin" --list --filter "KASUMI*"</pre>
    <p>服装编号是纯数字（<code>COS_001</code>、<code>DLC_011</code>），名字看不出款式，
      导出后看预览挑。模型分散在 36 个封包：常规服装在 <code>chara_initial</code> 或
      <code>chara_common</code>，过场版在 <code>rtm_common</code>，DLC 在
      <code>patch_XX_catalog</code>，场景在 <code>stage_*</code>。</p>

    <h3>社区 mod（含 nude）</h3>
    <pre>.\\export_full.ps1 -TmcFile D:\\mods\\nude.TMC -Label KAS_Nude
.\\export_full.ps1 KASUMI_COS_001 -TmcFile D:\\mods\\nude.TMC -Archive chara_initial -Hair 001 -Label KAS_Nude</pre>
    <div class="note"><b>官方内容没有 nude。</b>全部 36 个封包、12,625 个条目名搜
      <code>nude/naked/bare/skin/under/lingerie</code> 零命中，衣服底下的皮肤网格被裁掉了。
      mod 是替换用的 <code>.TMC</code> + 同名 <code>.TMCL</code>，格式与官方一致，
      <code>-TmcFile</code> 直接吃；<code>-TmcFile</code> 也接受目录。
      DOA5LR 的 mod 在 GameBanana 上是 0 个，主要在 LoversLab（需登录手动下载）。</div>

    <h3>已知坑</h3>
    <table>
      <tr><th>症状</th><th>原因 / 处理</th></tr>
      <tr><td>光头 / 无头</td><td>漏了 <code>-Hair</code> / <code>-Face</code></td></tr>
      <tr><td>皮肤半透明起噪点</td><td>已修复。DOA5LR 把高光遮罩塞在 diffuse 的 alpha 里，
        现在按数据判定（需 &gt;2% 全透明 <b>且</b> &gt;4% 全不透明像素）才接透明通道</td></tr>
      <tr><td>头发压在脸上 / 没有脸</td><td>已修复。多数角色三部件本就同处一个坐标系，
        早期版本强行按包围盒对齐反而挪歪（马尾的包围盒顶端是发梢；女天狗的翅膀撑大身体包围盒）</td></tr>
      <tr><td>Alpha-152 通体白</td><td>素材如此：三部件加起来只有 8 张贴图，
        游戏里靠特殊半透明 shader 表现，原始数据没有颜色贴图可还原</td></tr>
      <tr><td>.ps1 报 missing terminator</td><td>脚本被存成无 BOM 的 UTF-8，
        PowerShell 5.1 按 GBK 解析吞掉引号；用 UTF-8 with BOM 重存</td></tr>
    </table>

    <h3>重新生成本页</h3>
    <pre>blender --background --factory-startup --python scripts\\doa5lr\\html\\collect_manifest.py
python scripts\\doa5lr\\html\\make_gallery.py</pre>
    <p>第一步用 Blender 打开每个 blend 收集网格/材质/贴图统计写成 manifest，
      第二步把预览图缩成 JPEG 放进 <code>_gallery\\thumbs\\</code> 并重写本页。
      <b>缩略图刻意不进仓库</b> —— 和其它脚本一样，仓库不收任何游戏素材。</p>
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
  var arc = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!arc || card.dataset.arc === arc)
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
      arc = chip.dataset.arc || '';
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
    manifest_path = args.manifest or os.path.join(source_root, "doa5lr_models_manifest.json")
    thumb_dir = args.thumb_dir or os.path.join(source_root, "_gallery", "thumbs")
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), PAGE_NAME)
    if not os.path.isfile(manifest_path):
        raise SystemExit("找不到 manifest: %s\n先跑一次 collect_manifest.py" % manifest_path)

    archives = map_archives(args.game_root)
    _manifest, models = collect(manifest_path, thumb_dir, args.force, archives)
    if not models:
        raise SystemExit("manifest 里没有条目: %s" % manifest_path)

    page = render(models, source_root)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)

    missing = [m["label"] for m in models if not m["thumb"]]
    print("models      : %d" % len(models))
    print("archives    : %s" % (", ".join(sorted({m["archive"] for m in models if m["archive"]})) or "(未标注)"))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
