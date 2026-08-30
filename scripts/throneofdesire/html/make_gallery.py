"""把 Throne of Desire 的导出产物做成一页可浏览的 HTML 画廊。

读 ``tod_models_manifest.json``（由 collect_manifest.py 在 Blender 无头下生成），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\throneofdesire_exports --force
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
GROUP_LABELS = {"batch": "批量裸模", "single": "单独导出"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\throneofdesire_exports",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\tod_models_manifest.json）")
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
        model = entry.get("model") or ""
        group = entry.get("group") or "batch"
        # 同名模型可能既在批量里又有单独导出，缩略图按 组_模型 命名避免互相覆盖
        thumb = build_thumb(entry.get("preview"),
                            os.path.join(thumb_dir, "%s_%s.jpg" % (group, model)), force)
        models.append({
            "model": model,
            "group": group,
            "blend": entry.get("blend") or "",
            "preview": entry.get("preview") or "",
            "thumb": thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "meshes": entry.get("meshes") or 0,
            "faces": entry.get("faces") or 0,
            "armatures": entry.get("armatures") or 0,
            "materials": entry.get("materials") or 0,
            "images": entry.get("images") or 0,
            "packed": entry.get("packedImages") or 0,
            "status": entry.get("batchStatus") or "",
            "warnings": list(entry.get("warnings") or []),
        })
    models.sort(key=lambda m: (m["group"] != "batch", m["model"]))
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
    if model["group"] == "single":
        badges += '<span class="badge badge-single">单独导出</span>'

    search_blob = esc(" ".join([model["model"], model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["model"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-group="{group}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{model}</h3>{badges}
          </div>
          <dl>
            <dt>几何</dt><dd>{meshes} 网格 · {faces} 面 · {armatures} 骨架</dd>
            <dt>材质</dt><dd>{materials} 材质 · {images} 贴图（{packed} 已打包）</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button>
                <span class="size">{size}</span></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, group=esc(model["group"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, model=esc(model["model"]),
           badges=badges, meshes=model["meshes"], faces=model["faces"],
           armatures=model["armatures"], materials=model["materials"],
           images=model["images"], packed=model["packed"],
           blend_uri=esc(blend_uri), blend=esc(model["blend"]),
           size=human_size(model["blend_size"]))


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    batch = sum(1 for m in models if m["group"] == "batch")
    warned = sum(1 for m in models if m["warnings"])
    groups = [g for g in ("batch", "single") if any(m["group"] == g for m in models)]
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    chips = "".join('<button class="chip" data-group="%s">%s</button>' % (esc(g), esc(GROUP_LABELS[g]))
                    for g in groups)
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), batch=batch, size=human_size(total_bytes),
        warned=warned, chips=chips, cards=cards)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Throne of Desire 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --single: #1d5f7a; --single-bg: #e2f0f6; --shot: #d9dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --single: #7fc6e0; --single-bg: #1a3540; --shot: #2a2d34;
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
.badge-single {{ color: var(--single); background: var(--single-bg); cursor: default; }}
dl {{ margin: 0; display: grid; grid-template-columns: 42px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{ margin: 0; font-size: 12px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
dd a {{ color: var(--accent); text-decoration: none; }}
dd a:hover {{ text-decoration: underline; }}
.copy {{ padding: 1px 7px; margin-left: 6px; font-size: 11px; border-radius: 5px; }}
.size {{ color: var(--muted); margin-left: 6px; }}
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
  <h1>Throne of Desire 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{batch}</b><span>批量裸模</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索模型名或路径…（按 / 聚焦）">
  <button class="chip on" data-group="">全部</button>
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
    <p>脚本在 <code>scripts\\throneofdesire\\</code>，需在装有游戏的机器上运行。
      完整说明见同目录 <code>README.md</code> 与
      <code>docs\\throne-of-desire-extraction.md</code>。</p>

    <h3>这游戏的特别之处</h3>
    <p>不是 Unreal/Unity：X-Legend 自家的 NFS 封包 + Gamebryo 的 NIF/KFM 模型格式。
      <b>女性 h 系模型本体就是裸模</b>，衣服是默认隐藏的附件，导 FBX 时被排除，
      所以不需要额外的 nude 流程。</p>

    <h3>一次性准备（build_codecs.py）</h3>
    <pre>python scripts\\throneofdesire\\build_codecs.py</pre>
    <p>编译 LZHAM 与 ETC 解码器（通过 WSL 的 g++）。封包和贴图都用这两种压缩，
      不先编译后面会直接失败。</p>

    <h3>批量导出裸模（export_nude_models.ps1）</h3>
    <pre>cd E:\\code\\othercode\\ripper_tpose\\scripts\\throneofdesire

.\\export_nude_models.ps1              # 13 个 h 系女性基础体
.\\export_nude_models.ps1 -Only h005   # 只导一个</pre>
    <p>内部包的是 <code>batch_export_female.py</code>；产物是
      <code>&lt;导出根&gt;\\female_all\\&lt;model&gt;\\&lt;model&gt;_blender36.blend</code>
      与同名 FBX、预览图，同目录还留有 <code>source\\</code>（原始 NIF/KFM）和
      <code>textures\\</code>。批量清单写在 <code>female_all\\female_export_manifest.json</code>。</p>

    <div class="note"><b>当前限制：静态网格 + 未绑定的静止骨架。</b>
      蒙皮权重和动画还没做，导出的骨架只是摆在那里的 rest pose，不能直接摆姿势。
      需要动作的话得另外处理 KFM。</div>

    <h3>底层工具</h3>
    <table>
      <tr><th>脚本</th><th>作用</th></tr>
      <tr><td><code>extract_nfs.py</code></td><td>读 <code>packageindex</code> 与
        <code>FileListPC.txt</code>，从 NFS 封包取出 NIF/KFM</td></tr>
      <tr><td><code>extract_model_textures.py</code></td><td>取模型对应贴图并解码</td></tr>
      <tr><td><code>import_xlegend_nif36.py</code></td><td>Blender 3.6 的 NIF 导入器</td></tr>
      <tr><td><code>xlegend_nif.py</code></td><td>NIF 解析核心</td></tr>
      <tr><td><code>inspect_materials.py</code></td><td>排查材质/贴图对应关系</td></tr>
      <tr><td><code>validate_female_exports36.py</code></td><td>校验产物完整性，
        结果写 <code>female_export_validation.json</code></td></tr>
    </table>

    <h3>重新生成本页</h3>
    <pre>blender --background --factory-startup --python scripts\\throneofdesire\\html\\collect_manifest.py
python scripts\\throneofdesire\\html\\make_gallery.py</pre>
    <p>第一步递归扫导出根下全部 blend、逐个打开收集统计写成 manifest
      （<code>female_all\\</code> 下的归为批量裸模，其余归为单独导出），
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
  var group = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!group || card.dataset.group === group)
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
      group = chip.dataset.group || '';
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
    manifest_path = args.manifest or os.path.join(source_root, "tod_models_manifest.json")
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

    missing = [m["model"] for m in models if not m["thumb"]]
    print("models      : %d（批量 %d）" % (len(models), sum(1 for m in models if m["group"] == "batch")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
