"""Build a browsable HTML gallery of the exported Virt-A-Mate looks, clothing and hair.

Reads ``vam_models_manifest.json`` (written by export_vam_models.py / .ps1),
shrinks every preview into a JPEG thumbnail under the export root and emits a
self-contained ``index.html`` next to this script.

The page links to the real files with ``file://`` URLs and the thumbnails live
under ``<source-root>\\_gallery\\thumbs``, so no game-derived image ever enters
the repo -- same rule as the other galleries here.  Re-run after every export.

Usage:
  python make_gallery.py
  python make_gallery.py --source-root D:\\vam_exports --force
  python make_gallery.py --manifest D:\\tmp\\shard0.json --out D:\\tmp\\shard0.html
"""

import argparse
import html
import json
import os
import re
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 720
THUMB_QUALITY = 82
PAGE_NAME = "index.html"
KIND_LABEL = {"look": "Look", "clothing": "衣服", "hair": "头发"}
KIND_ORDER = {"look": 0, "clothing": 1, "hair": 2}
# untextured slots on these body materials mean the skin really lacks a texture
BODY_SLOT_WORDS = ("face", "torso", "limbs", "genital", "lips", "nostril", "ears", "feet",
                   "fingernails", "toenails", "legs", "arms", "neck", "hip", "shoulders",
                   "forearms", "hands")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", default=r"D:\vam_exports",
                        help="export root holding looks\\ clothings\\ hairs\\ (default: %(default)s)")
    parser.add_argument("--manifest", default=None,
                        help="manifest path (default: <source-root>\\vam_models_manifest.json)")
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


def safe_name(key):
    return re.sub(r'[<>:"/\\|?*\s]+', "_", key)[:150]


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


def first_str(*values):
    for value in values:
        if value:
            return str(value)
    return ""


def collect(manifest_path, thumb_dir, force):
    with open(manifest_path, encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    models, failed = [], []
    for entry in manifest.get("results", []):
        key = entry.get("model") or ""
        kind = entry.get("kind") or "look"
        notes = entry.get("notes") or {}
        if entry.get("status") != "PASS":
            failed.append({"key": key, "kind": kind, "status": entry.get("status") or "?",
                           "reason": first_str(entry.get("reason"), entry.get("error"),
                                               notes.get("reason"))})
            continue
        blend = entry.get("output") or ""
        preview = entry.get("preview") or ""
        thumb = build_thumb(preview, os.path.join(thumb_dir, safe_name(key) + ".jpg"), force)

        warnings, infos = [], []
        for label, values in (("衣服缺依赖", notes.get("clothingMissing")),
                              ("头发缺依赖", notes.get("hairMissing")),
                              ("贴图缺失", notes.get("missingTextures")),
                              ("morph 缺失", (notes.get("morphs") or {}).get("missing"))):
            for value in values or []:
                warnings.append("%s: %s" % (label, value))
        for slot in entry.get("untextured_slots") or []:
            if any(word in str(slot).lower() for word in BODY_SLOT_WORDS):
                warnings.append("人体槽无贴图: %s" % slot)
        for value in notes.get("defaultTexturesUsed") or []:
            infos.append("回退默认皮肤: %s" % value)
        for value in notes.get("attachmentsSkipped") or []:
            infos.append("附件跳过: %s" % value)

        morphs = notes.get("morphs") or {}
        facts = []
        if kind == "look":
            facts.append("%s · %s" % (notes.get("character") or "?",
                                      "男" if notes.get("gender") == "male" else "女"))
            facts.append("morph %d 个" % (morphs.get("applied") or 0))
            facts.append("衣服 %d 件" % len(notes.get("clothing") or []))
            hair = notes.get("hair") or []
            if hair:
                facts.append("头发 %d" % len(hair))
            attachments = notes.get("attachments") or []
            if attachments:
                facts.append("附件 %d" % len(attachments))
        else:
            if notes.get("itemType"):
                facts.append(str(notes.get("itemType")))
            if notes.get("vertices"):
                facts.append("%s 顶点" % format(int(notes["vertices"]), ","))
            if entry.get("strands"):
                facts.append("%s 根发丝" % format(int(entry["strands"]), ","))
        facts.append("%d 物体 · %d 材质 · %d 贴图" % (entry.get("objects") or 0,
                                                    entry.get("materials") or 0,
                                                    entry.get("textures") or entry.get("packed_images") or 0))

        detail_lines = []
        if kind == "look":
            detail_lines.append(("衣服", notes.get("clothing") or []))
            detail_lines.append(("头发", notes.get("hair") or []))
            detail_lines.append(("附件", notes.get("attachments") or []))
            detail_lines.append(("morph", morphs.get("names") or []))
        models.append({
            "key": key,
            "kind": kind,
            "display": entry.get("display") or key,
            "package": notes.get("package") or key.split("~")[0],
            "source": entry.get("source") or notes.get("source") or "",
            "blend": blend,
            "blend_dir": os.path.dirname(blend) if blend else "",
            "preview": preview,
            "thumb": thumb or "",
            "blend_size": os.path.getsize(blend) if blend and os.path.isfile(blend) else 0,
            "facts": facts,
            "details": [(label, values) for label, values in detail_lines if values],
            "warnings": warnings,
            "infos": infos,
            "seconds": entry.get("seconds") or 0,
        })
    models.sort(key=lambda item: (KIND_ORDER.get(item["kind"], 9), item["key"].lower()))
    failed.sort(key=lambda item: (KIND_ORDER.get(item["kind"], 9), item["key"].lower()))
    return manifest, models, failed


def render_card(model):
    esc = html.escape
    thumb_uri = file_uri(model["thumb"])
    preview_uri = file_uri(model["preview"])
    blend_uri = file_uri(model["blend_dir"] or model["blend"])
    badges = '<span class="badge badge-kind">%s</span>' % esc(KIND_LABEL.get(model["kind"], model["kind"]))
    if model["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">告警 %d</span>' % (
            esc("\n".join(model["warnings"])), len(model["warnings"]))
    if model["infos"]:
        badges += '<span class="badge badge-info" title="%s">备注 %d</span>' % (
            esc("\n".join(model["infos"])), len(model["infos"]))
    search_blob = esc(" ".join([model["key"], model["display"], model["package"],
                                model["source"], model["blend"]]
                               + [v for _, values in model["details"] for v in values]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["key"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    details = ""
    for label, values in model["details"]:
        shown = values[:6]
        more = " …(+%d)" % (len(values) - len(shown)) if len(values) > len(shown) else ""
        details += '<dt>%s</dt><dd title="%s">%s%s</dd>\n            ' % (
            esc(label), esc("\n".join(values)), esc("、".join(shown)), esc(more))
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener" title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3 title="{key}">{display}</h3>{badges}
          </div>
          <div class="key"><code>{key}</code><button class="copy" data-copy="{key}">复制</button></div>
          <div class="facts">{facts}</div>
          <dl>
            <dt>包</dt><dd>{package}</dd>
            {details}<dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend_name}</a> · {size} · {seconds}s
                <button class="copy" data-copy="{blend}">复制路径</button></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, key=esc(model["key"]),
           display=esc(model["display"]), badges=badges,
           facts=" · ".join(esc(fact) for fact in model["facts"]),
           package=esc(model["package"]), details=details,
           blend_uri=esc(blend_uri), blend=esc(model["blend"]),
           blend_name=esc(os.path.basename(model["blend"]) or "-"),
           size=human_size(model["blend_size"]), seconds=esc(str(model["seconds"])))


def render(manifest, models, failed, source_root):
    esc = html.escape
    counts = {kind: sum(1 for m in models if m["kind"] == kind) for kind in KIND_ORDER}
    total_bytes = sum(model["blend_size"] for model in models)
    warned = sum(1 for model in models if model["warnings"])
    generated = (manifest.get("generatedAt") or "")[:19].replace("T", " ")
    chips = "".join(
        '<button class="chip" data-kind="%s">%s (%d)</button>' % (kind, KIND_LABEL[kind], counts[kind])
        for kind in KIND_ORDER if counts[kind])
    cards = "".join(render_card(model) for model in models)
    failed_rows = "".join(
        "        <li><code>%s</code><span class=\"st\">%s</span><span>%s</span></li>\n"
        % (esc(item["key"]), esc(item["status"]), esc(item["reason"])) for item in failed)
    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        game_root=esc(manifest.get("gameRoot") or ""),
        total=len(models), looks=counts["look"], clothing=counts["clothing"],
        hair=counts["hair"], size=human_size(total_bytes), warned=warned,
        failed_count=len(failed), chips=chips, cards=cards, failed_rows=failed_rows)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virt-A-Mate 导出总览</title>
<style>
:root {{
  --bg: #f4f1ea; --card: #fffdf8; --ink: #2b2620; --muted: #7a6f63; --line: #e4dccd;
  --accent: #8a4b2a; --warn: #b3341f; --info: #3a6ea5; --kind: #5b6b3a;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }}
header {{ padding: 26px 28px 14px; border-bottom: 1px solid var(--line); background: #ede7db; }}
h1 {{ margin: 0 0 6px; font-size: 24px; letter-spacing: .5px; }}
.sub {{ color: var(--muted); }}
.sub code {{ font-size: 12px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 18px; margin-top: 14px; }}
.stat b {{ display: block; font-size: 22px; line-height: 1.1; }}
.stat span {{ color: var(--muted); font-size: 12px; }}
.toolbar {{ position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 8px;
  align-items: center; padding: 10px 28px; background: rgba(244,241,234,.95);
  border-bottom: 1px solid var(--line); backdrop-filter: blur(4px); }}
#q {{ flex: 1 1 320px; max-width: 520px; padding: 7px 10px; border: 1px solid var(--line);
  border-radius: 8px; font-size: 14px; background: #fff; }}
.chip, .toggle {{ padding: 5px 11px; border: 1px solid var(--line); border-radius: 999px;
  background: #fff; cursor: pointer; font-size: 13px; }}
.chip.on, .toggle.on {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.count {{ margin-left: auto; color: var(--muted); }}
main {{ padding: 18px 28px 40px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
  display: flex; flex-direction: column; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
.card[hidden] {{ display: none; }}
.shot {{ display: block; background: #cfd0d6; aspect-ratio: 2 / 1; overflow: hidden; }}
.shot img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.noimg {{ height: 100%; display: grid; place-items: center; color: #666; }}
.body {{ padding: 10px 14px 14px; }}
.titlerow {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
h3 {{ margin: 0; font-size: 16px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.badge {{ font-size: 11px; padding: 2px 7px; border-radius: 999px; color: #fff; background: var(--kind); }}
.badge-warn {{ background: var(--warn); }}
.badge-info {{ background: var(--info); }}
.key {{ margin: 4px 0 6px; color: var(--muted); font-size: 12px; display: flex; gap: 6px; align-items: center; }}
.key code {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.facts {{ color: var(--muted); font-size: 12.5px; margin-bottom: 6px; }}
dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 3px 10px; margin: 0; font-size: 12.5px; }}
dt {{ color: var(--muted); }}
dd {{ margin: 0; overflow: hidden; text-overflow: ellipsis; }}
dd a {{ color: var(--accent); text-decoration: none; }}
dd a:hover {{ text-decoration: underline; }}
.copy {{ font-size: 11px; padding: 1px 7px; border: 1px solid var(--line); border-radius: 6px;
  background: #fff; cursor: pointer; margin-left: 4px; }}
.empty {{ text-align: center; color: var(--muted); padding: 40px; }}
.appendix {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--line); max-width: 960px; }}
.appendix h2 {{ font-size: 18px; }}
.appendix h3 {{ font-size: 15px; margin-bottom: 4px; }}
.appendix pre {{ background: #2b2620; color: #f4f1ea; padding: 10px 14px; border-radius: 8px;
  overflow-x: auto; font-size: 12.5px; }}
.appendix li {{ display: grid; grid-template-columns: minmax(200px, 1fr) 70px 2fr; gap: 10px; padding: 3px 0;
  border-bottom: 1px dashed var(--line); font-size: 12.5px; }}
.appendix ul {{ list-style: none; padding: 0; }}
.st {{ color: var(--warn); }}
</style>
</head>
<body>
<header>
  <h1>Virt-A-Mate 导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> · 游戏目录 <code>{game_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已导出</span></div>
    <div class="stat"><b>{looks}</b><span>Look</span></div>
    <div class="stat"><b>{clothing}</b><span>衣服</span></div>
    <div class="stat"><b>{hair}</b><span>头发</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
    <div class="stat"><b>{failed_count}</b><span>失败 / 跳过</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索名字、包名、衣服、morph 或路径…（按 / 聚焦）">
  <button class="chip on" data-kind="">全部</button>
  {chips}
  <button class="toggle" id="warnOnly">只看告警</button>
  <span class="count" id="count"></span>
</div>

<main>
  <div class="grid" id="grid">
{cards}  </div>
  <div class="empty" id="empty" hidden>没有匹配的条目</div>

  <section class="appendix">
    <h2>附录 · 未成功的条目（{failed_count}）</h2>
    <ul>
{failed_rows}    </ul>

    <h2>附录 · 导出脚本用法</h2>
    <p>脚本在 <code>scripts\\vam\\</code>，需要本机装有 VaM 1.22、Blender 3.6 与 AssetStudioModCLI。
      Look 是"基础人体 + morph + 皮肤贴图 + 衣服 + 头发 + 挂在骨骼上的 CustomUnityAsset"，
      导出的是静止 A-pose 静态网格（无骨架），贴图打包进 <code>.blend</code>。</p>
    <pre>cd E:\\code\\othercode\\ripper_tpose\\scripts\\vam

.\\export_vam_models.ps1 -List                              # 列出全部 Look / 衣服 / 头发（带序号）
.\\export_vam_models.ps1 -List -Type look -Filter tifa      # 只看 Look，名字含 tifa
.\\export_vam_models.ps1 -Only VAMSOY.Angela.1~Angela~Person  # 按 key 导出
.\\export_vam_models.ps1 -Only Angela~Person                # 唯一子串也行，逗号分隔可多项
.\\export_vam_models.ps1 -Index 125,550                     # 按 -List 序号
.\\export_vam_models.ps1 -All -Type look -Force             # 全部 Look 重导
.\\export_vam_models.ps1 -Only 瑶瑶~Person -Format blend,glb # 同时出 glb
python html\\make_gallery.py                                # 重建本页</pre>
    <p>常用开关：<code>-NoClothing</code> / <code>-NoHair</code> / <code>-NoAttachments</code> 只导人体或去掉某类；
      <code>-IncludePoseMorphs</code> 保留姿势 morph；<code>-Force</code> 覆盖已有产物（缺省已有 blend 与预览的条目 SKIP）；
      <code>-ManifestPath</code> 给并行进程各自的清单。产物在 <code>{source_root}\\looks|clothings|hairs\\&lt;key&gt;\\blend\\</code>，
      清单 <code>{source_root}\\vam_models_manifest.json</code>。缩略图写在 <code>{source_root}\\_gallery\\thumbs\\</code>。</p>
  </section>
</main>

<script>
(function () {{
  var q = document.getElementById('q');
  var grid = document.getElementById('grid');
  var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var warnOnly = document.getElementById('warnOnly');
  var count = document.getElementById('count');
  var empty = document.getElementById('empty');
  var kind = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!kind || card.dataset.kind === kind)
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
    manifest_path = args.manifest or os.path.join(source_root, "vam_models_manifest.json")
    thumb_dir = args.thumb_dir or os.path.join(source_root, "_gallery", "thumbs")
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), PAGE_NAME)
    if not os.path.isfile(manifest_path):
        raise SystemExit("manifest not found: %s\n先跑一次 export_vam_models.ps1" % manifest_path)

    manifest, models, failed = collect(manifest_path, thumb_dir, args.force)
    if not models:
        raise SystemExit("manifest has no PASS entries: %s" % manifest_path)

    page = render(manifest, models, failed, source_root)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)

    missing = [model["key"] for model in models if not model["thumb"]]
    print("models      : %d (look %d / clothing %d / hair %d)" % (
        len(models), *(sum(1 for m in models if m["kind"] == k) for k in ("look", "clothing", "hair"))))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("failed/skip : %d" % len(failed))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
