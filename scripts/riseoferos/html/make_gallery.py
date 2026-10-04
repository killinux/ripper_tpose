"""Build a browsable HTML gallery of the materialized Rise of Eros models.

Reads ``character_models_manifest.json`` (written by export_character_models.ps1)
and, when present, ``_suits/manifest.json`` (written by export_suits.py — the
outfit variants assembled from component meshes) and the nude bases in
``nude_materials/`` that have a preview, shrinks each composite preview
into a JPEG thumbnail and emits a self-contained ``index.html`` next to this
script.  Suit and nude-base cards sit next to their character's cards and can be
filtered with the 角色模型 / 套装 / 裸模 chips; their XPS / PMX rows come from
export_hq.py (export_suit_xps_blender.py / export_suit_pmx_blender.py).  Dressed models whose body
complete_nude.py filled in (``<id>/blend/<stem>_nude.blend``) get a 裸模 card too.

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


def pmx_note_of(mmd):
    """Card note for a PMX from its conversion stats (manifest mmdConvert / <stem>.report.json)."""
    if not mmd:
        return ""
    physics = mmd.get("physics") or {}
    note = "%s 骨 · 刚体 %s · 关节 %s · 表情 %d" % (
        mmd.get("bones", "?"), physics.get("rigid_bodies", "?"),
        physics.get("joints", "?"), len(mmd.get("face_morphs") or []))
    if mmd.get("weight_holes"):
        note += " · 权重孔洞 %s" % mmd["weight_holes"]
    if (mmd.get("distortion") or {}).get("torn"):
        note += " · 拉伸边 %s" % mmd["distortion"]["torn"]
    return note


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
        pmx = outputs.get("pmx") or ""
        if pmx and not os.path.isfile(pmx):
            pmx = ""
        mmd = entry.get("mmdConvert") or {}
        pmx_note = pmx_note_of(mmd) if pmx else ""
        # The dance preview is rendered in a separate pass, so one left over from
        # an earlier export shows defects the model no longer has.
        dance = ""
        dance_note = ""
        if pmx:
            candidate = os.path.join(os.path.dirname(os.path.dirname(pmx)),
                                     os.path.splitext(os.path.basename(pmx))[0] + "_dance.mp4")
            if os.path.isfile(candidate):
                dance = candidate
                if os.path.getmtime(candidate) < os.path.getmtime(pmx):
                    dance_note = "已过期：比 PMX 旧，用 render_pmx_dance.ps1 -Stale 重渲"
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
            "pmx": pmx,
            "pmx_note": pmx_note,
            "dance": dance,
            "dance_note": dance_note,
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


def collect_suits(source_root, thumb_dir, force):
    """Cards for the suits export_suits.py assembled (``_suits/manifest.json``)."""
    manifest_path = os.path.join(source_root, "_suits", "manifest.json")
    if not os.path.isfile(manifest_path):
        return []
    with open(manifest_path, encoding="utf-8-sig") as handle:
        manifest = json.load(handle)
    suits = []
    for entry in manifest.get("suits", []):
        blend = entry.get("blend") or ""
        if entry.get("status") not in ("PASS", "WARN") or not os.path.isfile(blend):
            continue
        key = "%s_%s" % (entry.get("id", "?"), entry.get("suit", "?"))
        preview = blend[:-len(".blend")] + "_preview.png"
        if not os.path.isfile(preview):
            preview = ""
        thumb = build_thumb(preview, os.path.join(thumb_dir, key + ".jpg"), force)
        stem = os.path.splitext(os.path.basename(blend))[0]
        xps, pmx, pmx_note = suit_formats(os.path.dirname(blend), stem)
        excluded = entry.get("excluded") or {}
        # "SAVED <blend> meshes=14 packed=22 missing=[...]" from the assembler
        saved = entry.get("saved") or ""
        meshes = packed = 0
        for token in saved.split():
            if token.startswith("meshes="):
                meshes = int(token[7:] or 0)
            elif token.startswith("packed="):
                packed = int(token[7:] or 0)
        missing = entry.get("missing") or ""
        warnings = []
        if missing and missing != "[]":
            warnings.append("缺基色贴图: " + missing.strip("[]").replace("'", ""))
        suits.append({
            "key": key,
            "family": (entry.get("id") or "?")[:1].upper(),
            "id": entry.get("id") or "",
            "suit": entry.get("suit") or "",
            "base": entry.get("base") or "",
            "blend": blend,
            "xps": xps,
            "pmx": pmx,
            "pmx_note": pmx_note,
            "preview": preview,
            "thumb": thumb or "",
            "blend_size": os.path.getsize(blend),
            "parts": entry.get("parts") or 0,
            "excluded": excluded,
            "meshes": meshes,
            "packed": packed,
            "warnings": warnings,
        })
    suits.sort(key=lambda item: item["key"])
    return suits


def suit_formats(blend_dir, stem):
    """XPS / PMX of a suit or nude base: export_suit_xps_blender.py / export_suit_pmx_blender.py write
    <id>/blend/xps/<stem>/<stem>.mesh and <id>/blend/pmx/<stem>/<stem>.pmx (+ .report.json), like the batch."""
    xps = os.path.join(blend_dir, "xps", stem, stem + ".mesh")
    pmx = os.path.join(blend_dir, "pmx", stem, stem + ".pmx")
    pmx_note = ""
    if os.path.isfile(pmx[:-4] + ".report.json"):
        with open(pmx[:-4] + ".report.json", encoding="utf-8") as handle:
            pmx_note = pmx_note_of(json.load(handle))
    return (xps if os.path.isfile(xps) else ""), (pmx if os.path.isfile(pmx) else ""), pmx_note


def collect_nudes(source_root, thumb_dir, force, main_stems):
    """Cards for the nude bases (``nude_materials/pc_<id>[_fm]_nk_bs.blend``: the body the H scenes play on)."""
    folder = os.path.join(source_root, "nude_materials")
    nudes = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".blend" or not stem.startswith("pc_") or stem in main_stems:
            continue
        blend = os.path.join(folder, name)
        cid = stem[3:6]
        key = stem[3:]
        preview = os.path.join(folder, stem + "_preview.png")
        if not os.path.isfile(preview):
            continue            # rendered by the game-material step (export_hq.py); h / i not converted yet
        xps, pmx, pmx_note = suit_formats(os.path.join(source_root, cid, "blend"), stem)
        nudes.append({
            "key": key, "family": cid[:1].upper(), "id": cid, "blend": blend, "xps": xps, "pmx": pmx,
            "pmx_note": pmx_note, "preview": preview,
            "thumb": build_thumb(preview, os.path.join(thumb_dir, key + ".jpg"), force) or "",
            "blend_size": os.path.getsize(blend), "fm": "_fm_" in stem})
    return nudes


def collect_completed(source_root, thumb_dir, force):
    """Cards for dressed models given the whole body by complete_nude.py: ``<id>/blend/<stem>_nude.blend`` (the
    skin the game deleted under the outfit filled in from the family nude base), with the dressed full-body
    ``<stem>_full`` (.blend, XPS with the outfit as optional items, PMX with the 衣服非表示 morph) as extra rows."""
    found = []
    for rid in sorted(os.listdir(source_root)) if os.path.isdir(source_root) else []:
        folder = os.path.join(source_root, rid, "blend")
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            stem, ext = os.path.splitext(name)
            if ext.lower() != ".blend" or not stem.startswith("pc_") or not stem.endswith("_nude"):
                continue
            blend = os.path.join(folder, name)
            preview = os.path.join(folder, stem + "_preview.png")
            if not os.path.isfile(preview):
                continue
            cid, key = stem[3:6], stem[3:]
            run = os.path.join(source_root, "_hq_runs", stem, "result.json")
            base = "pc_%s01_nk_bs" % cid[0]
            if os.path.isfile(run):
                with open(run, encoding="utf-8") as handle:
                    base = json.load(handle).get("nude_base") or base
            full = os.path.join(folder, stem[:-len("_nude")] + "_full.blend")
            xps, pmx, pmx_note = suit_formats(folder, stem)
            full_xps, full_pmx, _note = suit_formats(folder, stem[:-len("_nude")] + "_full")
            found.append({
                "key": key, "family": cid[:1].upper(), "id": cid, "blend": blend, "xps": xps, "pmx": pmx,
                "pmx_note": pmx_note, "preview": preview,
                "thumb": build_thumb(preview, os.path.join(thumb_dir, key + ".jpg"), force) or "",
                "blend_size": os.path.getsize(blend), "fm": False, "completed": base,
                "model": stem[:-len("_nude")], "full": full if os.path.isfile(full) else "",
                "full_xps": full_xps, "full_pmx": full_pmx})
    return found


def format_rows(item):
    """The XPS / PMX rows of a suit or nude-base card (the links point at the folder)."""
    esc = html.escape
    rows = ""
    for label, path, note in (("XPS", item["xps"], ""), ("PMX", item["pmx"], item["pmx_note"])):
        if path:
            rows += ('<dt>%s</dt>\n            <dd><a href="%s" title="%s">%s</a>\n'
                     '                <button class="copy" data-copy="%s">复制</button>%s</dd>\n            '
                     % (label, esc(file_uri(os.path.dirname(path))), esc(path), esc(path), esc(path),
                        (' <span class="rigspec">%s</span>' % esc(note)) if note else ""))
    return rows


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
                                model["blend"], model["xps"], model["pmx"]]).lower())
    xps_row = ""
    # The model rows point at the folder — you go there to open the file in a
    # tool.  The dance preview is the one thing the browser can play itself, so
    # it links to the mp4 and carries a player right in the card.
    for label, path, note, link_file in (
            ("XPS", model["xps"], "", False),
            ("PMX", model["pmx"], model["pmx_note"], False),
            ("跳舞", model["dance"], model["dance_note"], True)):
        if not path:
            continue
        target = path if link_file else os.path.dirname(path)
        xps_row += ('<dt>%s</dt>\n            <dd><a href="%s" title="%s">%s</a>\n'
                    '                <button class="copy" data-copy="%s">复制</button>%s</dd>\n            '
                    % (label, esc(file_uri(target)), esc(path), esc(path),
                       esc(path), (' <span class="rigspec">%s</span>' % esc(note)) if note else ""))
    if model["dance"]:
        xps_row += ('<dd class="clip"><video controls preload="none" '
                    'poster="%s" src="%s"></video></dd>\n            '
                    % (esc(thumb_uri or ""), esc(file_uri(model["dance"]))))
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["key"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-family="{family}" data-warn="{warn}" data-kind="model">
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


def render_suit_card(suit):
    esc = html.escape
    thumb_uri = file_uri(suit["thumb"])
    preview_uri = file_uri(suit["preview"])
    blend_uri = file_uri(suit["blend"])
    badges = '<span class="badge badge-suit" title="套装：裸模 + 头发 + 部件网格拼装（export_suits.py）">套装</span>'
    if suit["excluded"]:
        badges += '<span class="badge badge-fix" title="%s">去掉 %d</span>' % (
            esc("; ".join("%s（%s）" % (root.replace("_obj001", ""), why)
                          for root, why in suit["excluded"].items())), len(suit["excluded"]))
    if suit["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">缺图 %d</span>' % (
            esc("; ".join(suit["warnings"])), len(suit["warnings"]))
    search_blob = esc(" ".join([suit["key"], "suit 套装", suit["suit"], suit["base"], suit["blend"],
                                suit["xps"], suit["pmx"]]).lower())
    pmx_row = format_rows(suit)
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(suit["key"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    dressed = suit["parts"] - len(suit["excluded"])
    return """      <article class="card" data-search="{search}" data-family="{family}" data-warn="{warn}" data-kind="suit">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图（{family} 家族）">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{key}</h3>{badges}
          </div>
          <dl>
            <dt>底模</dt><dd>{base}.fbx + 存根 accessory_components_pc_{id}_suit_{suit}.ab</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
            {pmx_row}<dt>规格</dt>
            <dd>{parts} 个部件，穿好 {dressed} 个 · {meshes} 网格 · {packed} 贴图 · {size}</dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, family=esc(suit["family"]),
           warn="1" if suit["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, key=esc(suit["key"]),
           badges=badges, base=esc(suit["base"]), id=esc(suit["id"]), suit=esc(suit["suit"]),
           blend_uri=esc(blend_uri), blend=esc(suit["blend"]), pmx_row=pmx_row,
           parts=suit["parts"], dressed=dressed, meshes=suit["meshes"],
           packed=suit["packed"], size=human_size(suit["blend_size"]))


def render_nude_card(nude):
    esc = html.escape
    thumb_uri = file_uri(nude["thumb"])
    completed = nude.get("completed")
    if completed:
        badges = ('<span class="badge badge-suit" title="%s">补全裸模</span>'
                  % esc("%s 去掉衣服，游戏删掉的衣服下皮肤用裸模 %s 的身体补全（complete_nude.py）"
                        % (nude["model"], completed)))
    else:
        badges = ('<span class="badge badge-suit" title="官方裸体基础模型：H 场景用的身体（export_nude_models.ps1，'
                  '游戏材质 hq_materials_blender.py）">裸模</span>')
    if nude["fm"]:
        badges += '<span class="badge badge-fix" title="魔化（fm）形态的身体">魔化</span>'
    rows = format_rows(nude)
    if completed:              # the dressed version over the whole body; XPS / PMX links point at the folder
        for label, path, link, note in (
                ("带衣服", nude.get("full"), nude.get("full"), "衣服下是完整身体，爆衣插件用"),
                ("带衣服 XPS", nude.get("full_xps"), os.path.dirname(nude.get("full_xps") or ""),
                 "衣服是可选部件，XNALara / XPS 里可以单独勾掉"),
                ("带衣服 PMX", nude.get("full_pmx"), os.path.dirname(nude.get("full_pmx") or ""),
                 "表情「衣服非表示」= 1 脱掉衣服（含胸部 B 版）")):
            if path:
                rows += ('<dt>%s</dt>\n            <dd><a href="%s" title="%s">%s</a>\n'
                         '                <button class="copy" data-copy="%s">复制</button>'
                         ' <span class="rigspec">%s</span></dd>\n            '
                         % (label, esc(file_uri(link)), esc(path), esc(path), esc(path), note))
    spec = ("%s 的头、头发、骨架 + %s 的完整身体，游戏原始材质" % (nude["model"], completed) if completed
            else "身体 + 脸 + 头发，游戏原始材质")
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(nude["key"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    search_blob = esc(" ".join([nude["key"], "nude 裸模 nk_bs", "补全 complete" if completed else "", nude["blend"],
                                nude["xps"], nude["pmx"]]).lower())
    return """      <article class="card" data-search="{search}" data-family="{family}" data-warn="0" data-kind="nude">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图（{family} 家族）">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{key}</h3>{badges}
          </div>
          <dl>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
            {rows}<dt>规格</dt>
            <dd>{spec} · {size}</dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, family=esc(nude["family"]), preview=esc(file_uri(nude["preview"])),
           figure=figure, key=esc(nude["key"]), badges=badges, blend_uri=esc(file_uri(nude["blend"])),
           blend=esc(nude["blend"]), rows=rows, spec=esc(spec), size=human_size(nude["blend_size"]))


def render(manifest, models, nomesh, source_root, suits=(), nudes=()):
    esc = html.escape
    families = sorted({model["family"] for model in models} | {suit["family"] for suit in suits}
                      | {nude["family"] for nude in nudes})
    total_bytes = (sum(model["blend_size"] for model in models) + sum(suit["blend_size"] for suit in suits)
                   + sum(nude["blend_size"] for nude in nudes))
    characters = len({model["key"].split("_")[0] for model in models})
    warned = sum(1 for model in models if model["warnings"]) + sum(1 for suit in suits if suit["warnings"])
    generated = (manifest.get("generatedAt") or "")[:19].replace("T", " ")

    chips = "".join(
        '<button class="chip" data-family="%s">%s</button>' % (esc(item), esc(item))
        for item in families)
    # suit and nude-base cards sit right behind their character's cards (keys sort that way)
    entries = ([("model", model) for model in models] + [("suit", suit) for suit in suits]
               + [("nude", nude) for nude in nudes])
    entries.sort(key=lambda item: item[1]["key"])
    renderers = {"model": render_card, "suit": render_suit_card, "nude": render_nude_card}
    cards = "".join(renderers[kind](item) for kind, item in entries)
    nomesh_rows = "".join(
        "        <li><code>%s</code><span>%s</span></li>\n" % (esc(item["key"]), esc(item["reason"]))
        for item in nomesh)

    return PAGE_TEMPLATE.format(
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), suits=len(suits), nudes=len(nudes), characters=characters,
        size=human_size(total_bytes), warned=warned, nomesh_count=len(nomesh), chips=chips, cards=cards,
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
.sep {{ width: 1px; height: 22px; background: var(--line); margin: 0 4px; }}
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
.badge-suit {{ color: var(--accent); background: var(--bg); border: 1px solid var(--accent); }}
dl {{ margin: 0; display: grid; grid-template-columns: 58px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{
  margin: 0; font-size: 12px; font-family: Consolas, monospace;
  overflow-wrap: anywhere;
}}
dd a {{ color: var(--accent); text-decoration: none; }}
dd a:hover {{ text-decoration: underline; }}
.copy {{ padding: 1px 7px; margin-left: 6px; font-size: 11px; border-radius: 5px; }}
.rigspec {{ display: block; color: var(--muted); font-size: 11.5px; margin-top: 2px; }}
dd.clip {{ grid-column: 1 / -1; margin: 6px 0 2px; }}
dd.clip video {{ width: 100%; max-height: 260px; border-radius: 8px; background: #000; }}
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
    <div class="stat"><b>{suits}</b><span>套装</span></div>
    <div class="stat"><b>{nudes}</b><span>裸模</span></div>
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
  <span class="sep"></span>
  <button class="chip kind on" data-kind="">全部</button>
  <button class="chip kind" data-kind="model">角色模型</button>
  <button class="chip kind" data-kind="suit">套装</button>
  <button class="chip kind" data-kind="nude">裸模</button>
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
      <tr><td><code>-Format pmx -NoPreview</code></td><td>补 MMD 可用的 PMX 到 <code>blend\\pmx\\&lt;stem&gt;\\</code>：Convert_to_MMD5 插件转标准 MMD 骨架（IK / D 骨 / 捩骨 / 肩P / 付与）+ 身体刚体 + 裙发物理，A-pose 37°，可直接加载 VMD</td></tr>
      <tr><td><code>-NoPreview</code></td><td>不渲预览图（实测只快约 9%，一般没必要关）</td></tr>
      <tr><td><code>render_pmx_dance.ps1 -Stale</code></td><td>另一个脚本：给 PMX 渲跳舞 mp4。骨骼问题只有动起来才看得见，改完导出流程务必重渲——卡片上标「已过期」的就是比 PMX 旧的视频</td></tr>
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

    <h3>套装（suit）· export_suits.py</h3>
    <p>角色的服装变体（游戏里叫 <em>suit</em>：教师装、猫女、婚纱…）不是一个整体 FBX，而是裸模 + 头发 +
      一堆分开的部件网格。标着「套装」徽章的卡片就是拼出来的这些，每套一个 <code>.blend</code>，
      直接从 AssetBundle 读（不经 AssetStudio）：</p>
    <pre>python export_suits.py --list                     # 哪些套装、哪些已拼
python export_suits.py --lanes 4                  # 全部没拼的，4 路并行
python export_suits.py --only j01:idol,b01:* --force
python export_suits.py --exclude fm --force       # 跳过魔化（fm）套</pre>
    <p>前提只有该角色的裸模已提取（<code>extract_character.ps1 &lt;id&gt;</code>）。产物
      <code>&lt;id&gt;\\blend\\pc_&lt;id&gt;_&lt;suit&gt;.blend</code>，中间数据 <code>_suits\\&lt;id&gt;\\&lt;suit&gt;\\</code>，
      清单 <code>_suits\\manifest.json</code>。「去掉 N」徽章列的是没穿上的部件（道具、敞开/拉下的替代态、
      被上衣遮住的乳饰），规则判错的在 <code>suit_overrides.json</code> 里按 <code>&lt;id&gt;:&lt;suit&gt;</code>
      改，再 <code>--only &lt;id&gt;:&lt;suit&gt; --force</code>。部件坐标系的五种情况与「穿好」规则见
      <code>docs\\roe-suit-assembly.md</code>。</p>

    <h3>高清版一键导出 · export_hq.py</h3>
    <p>套装、裸模、主模型都用这一个入口出游戏原始材质的版本：<code>.blend</code>、PMX（含胸部 B 版）、XPS，
      想转哪个写哪个，做完可以直接归档到 E 盘并刷新本页。卡片上的 XPS / PMX 行就是它的产物。</p>
    <pre>python export_hq.py --list                         # 每个模型在 E 盘的状态，缺什么
python export_hq.py pc_b01_jeans                   # 一套服装：重拼 + 游戏材质 + PMX + 胸部 B 版 + XPS
python export_hq.py b01:jeans pc_b01_nk_bs --archive   # 加一个裸模，做完归档到 E 盘、刷新画廊
python export_hq.py pc_a01_marry --formats xps     # 只出 XPS
python export_hq.py --todo --skip h,i --lanes 4    # 没做全的全部做（h、i 除外），4 路并行</pre>
    <p>写法：服装 <code>pc_&lt;id&gt;_&lt;suit&gt;</code> 或 <code>&lt;id&gt;:&lt;suit&gt;</code>，裸模
      <code>pc_&lt;id&gt;_nk_bs</code>，主模型写编号（<code>a08</code>）。日志在
      <code>D:\\roe_exports\\_hq_runs\\&lt;stem&gt;\\</code>，详细说明见 <code>scripts\\riseoferos\\README.md</code> §8.5。</p>

    <h3>补全身体 · complete_nude.py</h3>
    <p>主模型（穿着衣服的造型）里，衣服盖住的皮肤游戏是删掉的。这个脚本用同一角色的裸模（<code>pc_&lt;字母&gt;01_nk_bs</code>）
      把身体补全，出两份，各有 .blend + XPS + PMX（含胸部 B 版）：<code>&lt;stem&gt;_nude</code>（去掉衣服的裸模，卡片标「补全裸模」）
      和 <code>&lt;stem&gt;_full</code>（衣服还在、下面是完整身体，卡片上「带衣服」那几行）。带衣服版一个文件两种用法：
      XPS 里衣服是可选部件（XNALara / XPS 可以单独勾掉），PMX 里表情「衣服非表示」= 1 就是裸的；.blend 给爆衣插件用。
      游戏战斗时才拿的武器（a08 的大剑）也加进去，PMX 里表情「武器非表示」收起。</p>
    <pre>python complete_nude.py a08                        # pc_a08_hd -&gt; pc_a08_hd_nude + pc_a08_hd_full
python complete_nude.py a08 g04 --archive          # 做完归档到 E 盘、刷新本页
python complete_nude.py g04 --variants full --formats pmx   # 只重出带衣服版的 PMX
python complete_nude.py pc_g04_hd --nude pc_g01_nk_bs      # 裸模默认是同字母的 01，也可以指定</pre>
    <p>原理和坑见 <code>docs\\roe-complete-nude.md</code>，日志在 <code>D:\\roe_exports\\_hq_runs\\&lt;stem&gt;_nude\\</code>。</p>

    <h3>重新生成本页</h3>
    <pre>python scripts\\riseoferos\\html\\make_gallery.py</pre>
    <p>读 <code>character_models_manifest.json</code>、<code>_suits\\manifest.json</code> 和
      <code>nude_materials\\*.blend</code>（有预览图的裸模），把预览图缩成
      JPEG 缩略图放进 <code>D:\\roe_exports\\_gallery\\thumbs\\</code>，再重写本页。
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
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip:not(.kind)'));
  var kinds = Array.prototype.slice.call(document.querySelectorAll('.chip.kind'));
  var family = '';
  var kind = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!family || card.dataset.family === family)
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
      family = chip.dataset.family || '';
      apply();
    }});
  }});
  kinds.forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      kinds.forEach(function (other) {{ other.classList.remove('on'); }});
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
    suits = collect_suits(source_root, thumb_dir, args.force)
    main_stems = {os.path.splitext(os.path.basename(model["blend"]))[0] for model in models}
    nudes = collect_nudes(source_root, thumb_dir, args.force, main_stems)
    nudes += collect_completed(source_root, thumb_dir, args.force)

    page = render(manifest, models, nomesh, source_root, suits, nudes)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)

    missing = [model["key"] for model in models if not model["thumb"]]
    print("models      : %d" % len(models))
    print("suits       : %d" % len(suits))
    print("nude bases  : %d" % len(nudes))
    print("no preview  : %d%s" % (len(missing),
                                  (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("nomesh      : %d" % len(nomesh))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
