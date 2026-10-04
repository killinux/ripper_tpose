"""把 Taimanin Squad 的全部 3D 单位做成一页可浏览的 HTML：导出过的显示预览图和 .blend / XPS / PMX 的位置，
没导出的显示渲染预览（没有就用游戏自带头像）和导出命令；页首是「怎么导出模型」的操作说明 —— 最短的三条命令，
然后一步一步：准备什么、怎么找模型、导出命令做了什么、结果怎么看怎么打开、舞蹈视频、出问题时终端里的话是什么意思。

页面用 ``file://`` 链接指向本机真实文件；游戏头像和缩略图写在导出根目录的 ``_meta\\gallery`` 下，
**任何游戏素材都不会进仓库** —— 和这里其它游戏的画廊同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py                 # 生成本脚本旁的 index.html
  python make_gallery.py --force         # 缩略图全部重做
  python ..\\list_models.py --html        # 同一件事（顺便刷新清单）
"""
import argparse
import datetime
import html
import os
import shutil
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tsquad_common as tc  # noqa: E402

THUMB_WIDTH = 520
THUMB_QUALITY = 84
PAGE_NAME = "index.html"
# 手动说明里提到的图形界面工具；本机没有的那一项只写名字，不写路径
TOOLS = {
    "assetstudio": os.environ.get("ASSETSTUDIO_GUI",
                                  r"E:\tools\AssetStudioMod_v0.19.0\AssetStudioModGUI_net8_win64\AssetStudioModGUI.exe"),
    "xps": os.environ.get("XPS_EXE", r"E:\tools\XPS 11.8\XNALara XPS.exe"),
    "mmd": os.environ.get("MMD_EXE", r"E:\tools\MikuMikuDanceE_v932x64\MikuMikuDance.exe"),
}
# 说明里「本机已有 / 本机没找到」看的插件文件夹（Blender 3.6 的用户插件目录）
ADDON_DIR = os.environ.get("TSQUAD_BLENDER_ADDONS", os.path.join(
    os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "3.6", "scripts", "addons"))
# 一次全套导出在终端里打印的内容：24_kirara 导到一个空的导出目录，2026-10-04 实测，从头到尾 2 分 02 秒
SAMPLE_RUN = """[tsquad] (1/1) 24_kirara  Kirara
[tsquad] 24_kirara: reading 24_Kirara/Unit/prf_24.prefab from localunit_aos_assets_24_kirara_2f523ece….bundle
[tsquad] 24_kirara: building {out}\\Kirara\\blend\\24_kirara\\24_kirara.blend (6 parts, 113 bones, 10 materials)
[tsquad] 24_kirara: turntable video ...
[tsquad] 24_kirara: XPS ...
[tsquad] 24_kirara: PMX ...
[tsquad] 24_kirara: {out}\\Kirara\\blend\\24_kirara\\24_kirara.blend  (41291 verts, 62212 faces, 113 bones, 10 materials, 19 shape keys, 14 s)
[tsquad]   TURNTABLE {out}\\Kirara\\blend\\24_kirara\\24_kirara_turntable.mp4
[tsquad]   XPS {out}\\Kirara\\xps\\24_kirara\\24_kirara.xps
[tsquad]   PMX {out}\\Kirara\\pmx\\24_kirara\\24_kirara.pmx
[tsquad]   PMX: 222 bones, 46 rigid bodies, torn 0, stretched 2, grant violations 0, bust 2, morphs 31
[tsquad]   PMX breasts: size 13.2 cm, the game allows 4.0 cm -> factor 0.8: travel [4.0, 3.2, 3.2] cm, [2.46, 2.91, 4.02] Hz, sag 1.23 cm
[tsquad] done: 1 built, 0 skipped, 0 failed"""


def file_uri(path):
    try:
        return Path(path).as_uri() if path else ""
    except (ValueError, OSError):
        return ""


def human_size(num_bytes):
    if not num_bytes:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return "%.0f %s" % (num_bytes, unit) if unit == "B" else "%.1f %s" % (num_bytes, unit)
        num_bytes /= 1024.0
    return "-"


def build_thumb(source, thumb, force=False):
    from PIL import Image

    if not source or not os.path.isfile(source):
        return ""
    if not force and os.path.isfile(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(source):
        return thumb
    os.makedirs(os.path.dirname(thumb), exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        if image.width > THUMB_WIDTH:
            image = image.resize((THUMB_WIDTH, max(1, round(image.height * THUMB_WIDTH / image.width))), Image.LANCZOS)
        image.save(thumb, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return thumb


def collect(models, root, force=False):
    """Per model: what exists on disk (by the folder convention), thumbnails, the game icon."""
    import tsquad_scene as ts

    gallery = os.path.join(tc.meta_dir(root), "gallery")
    icons = ts.export_icons(models, os.path.join(gallery, "icons"), root)
    try:
        records = tc.load_json(os.path.join(tc.meta_dir(root), "exports.json"))
    except (OSError, ValueError):
        records = {}
    batch = {u["id"]: u["video"] for u in video_lists(root).get("units", []) if u.get("video")}    # dance_batch.py
    rows = []
    for m in models:
        mid = m["id"]
        blend_dir = tc.model_dir(m, root, "blend")
        files = {
            "blend": os.path.join(blend_dir, mid + ".blend"),
            "preview": os.path.join(blend_dir, mid + "_preview.png"),
            "face": os.path.join(blend_dir, mid + "_face.png"),
            "expressions": os.path.join(blend_dir, mid + "_expressions.png"),
            "xps": os.path.join(tc.model_dir(m, root, "xps"), mid + ".xps"),
            "pmx": os.path.join(tc.model_dir(m, root, "pmx"), mid + ".pmx"),
            "pmx_dance": os.path.join(tc.model_dir(m, root, "pmx"), "preview_dance.png"),
            "pmx_morphs": os.path.join(tc.model_dir(m, root, "pmx"), "preview_morphs.png"),
            "turntable": os.path.join(blend_dir, mid + "_turntable.mp4"),
            "xps_preview": os.path.join(tc.model_dir(m, root, "xps"), mid + "_xps_preview.png"),
            # export_model.py --preview-only: a render of a unit that has not been exported
            "survey": os.path.join(tc.work_dir(root), "previews", mid + "_preview.png"),
        }
        files = {k: (v if os.path.isfile(v) else "") for k, v in files.items()}
        video_dir = tc.model_dir(m, root, "video")       # dance_video.py: <id>_<motion>.mp4
        videos = [os.path.join(video_dir, f) for f in sorted(os.listdir(video_dir))
                  if f.lower().endswith(".mp4")] if os.path.isdir(video_dir) else []
        if os.path.isfile(batch.get(mid, "")):
            videos.insert(0, batch[mid])
        shot = files["preview"] if files["blend"] else files["survey"]
        thumb = build_thumb(shot, os.path.join(gallery, "thumbs", mid + ".jpg"), force)
        rows.append({"model": m, "files": files, "thumb": thumb, "shot": shot, "icon": icons.get(mid, ""),
                     "videos": videos,
                     "blend_size": os.path.getsize(files["blend"]) if files["blend"] else 0,
                     "pmx_note": pmx_note((records.get(mid) or {}).get("pmx_report")) if files["pmx"] else "",
                     "weapons": weapon_note(m, (records.get(mid) or {}).get("weapon_prefabs") if files["blend"] else None)})
    return rows


def video_lists(root):
    """The lists dance_batch.py keeps (<root>/_videos/_meta/list.json): {} when there are none."""
    try:
        return tc.load_json(os.path.join(root, "_videos", "_meta", "list.json"))
    except (OSError, ValueError):
        return {}


def render_videos(root):
    """The 舞蹈视频 section: the videos of dance_batch.py as tiles, then who is still without one, who was
    dropped (dance_batch.py --drop) and why, and what became of every dance of the collection.  '' when no
    batch has run."""
    esc = html.escape
    data = video_lists(root)
    if not data:
        return ""
    s = data["summary"]
    done = [u for u in data["units"] if u.get("video") and os.path.isfile(u["video"])]
    todo = [u for u in data["units"] if u not in done]
    tiles = []
    for u in done:
        picture = ('<img loading="lazy" src="%s" alt="%s">' % (esc(file_uri(u["thumb"])), esc(u["id"]))
                   if u.get("thumb") and os.path.isfile(u["thumb"]) else '<div class="noimg">没有缩略图</div>')
        tiles.append('      <a class="vid" href="%s" target="_blank" rel="noopener" title="%s">%s'
                     '<span class="cap"><b>%s</b><br>%s · %s 秒<br><span class="muted">%s</span></span></a>' % (
                         esc(file_uri(u["video"])), esc(u["video"]), picture, esc(u["name"]), esc(u["dance"]),
                         esc("%g" % u["seconds"]), esc(os.path.splitext(u.get("backdrop") or "")[0] or "没有背景")))
    waiting = "".join("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        esc(u["id"]), esc(u["name"]), esc(u["dance"] or "（没有分到动作）"), esc(os.path.splitext(u.get("backdrop") or "")[0]))
        for u in todo)
    dropped = data.get("dropped") or []
    left_out = "" if not dropped else (
        '    <details><summary>不做视频的角色（%d）：看过之后决定不要的</summary>\n'
        '      <table class="list"><tr><th>单位</th><th>名字</th><th>原因</th></tr>%s</table>\n'
        '      <p class="muted">模型本身照常在下面的模型列表里。放回来：<code>python dance_batch.py --undrop &lt;单位&gt;</code></p>\n'
        '    </details>\n' % (len(dropped), "".join(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (esc(d["id"]), esc(d["name"]), esc(d.get("why") or "（没写）"))
            for d in dropped)))
    order = {"已导出": 0, "已分配，未导出": 1, "未分配": 2, "不用": 3}
    dances = "".join('<tr class="st%d"><td>%s</td><td class="muted">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        order.get(t["state"], 3), esc(t["title"]), esc(t["folder"]), esc("%g" % t["seconds"]) if t["seconds"] else "",
        esc(t["state"]), "<code>%s</code>" % esc(t["unit"]) if t["unit"] else esc(t["why"]))
        for t in sorted(data["dances"], key=lambda t: (order.get(t["state"], 3), t["title"], t["folder"])))
    folder = os.path.join(root, "_videos")
    return """  <section class="howto" id="videos">
    <h2>舞蹈视频</h2>
    <p>每个女性角色（每套服装算一个，不含怪物和 Boss）配一支不同的舞和一张随机的游戏背景，由 <code>dance_batch.py</code> 渲到
      <a href="{folder_uri}"><code>{folder}</code></a>，文件名「动作名_角色名」。列表更新于 {generated}（<a href="{list_uri}">_列表.md</a>）。</p>
    <p><b>角色</b>：{units} 个，已导出 <b>{with_video}</b>，未导出 {without}{dropped}。
      <b>动作</b>：合集里 {folders} 个文件夹，可用 {usable} 支（单人、有配乐、8 秒以上、同一支舞取最新版）——
      已导出 <b>{exported}</b>，已分配未导出 {planned}，未分配 {free}；不用的 {left_out} 个。
      怎么渲、怎么续、怎么去掉一个：上面操作说明的<a href="#howto">第 4 步</a>。</p>
    <div class="vids">
{tiles}
    </div>
    <details><summary>还没导出视频的角色（{without}）</summary>
      <table class="list"><tr><th>单位</th><th>名字</th><th>分到的动作</th><th>背景</th></tr>{waiting}</table>
    </details>
{dropped_list}    <details><summary>动作列表（{folders}）：哪些导出了，哪些没有，哪些不用</summary>
      <table class="list"><tr><th>动作</th><th>文件夹</th><th>秒</th><th>状态</th><th>角色 / 不用的原因</th></tr>{dances}</table>
    </details>
  </section>
""".format(folder_uri=esc(file_uri(folder)), folder=esc(folder), generated=esc(data.get("generated", "")),
           list_uri=esc(file_uri(os.path.join(folder, "_列表.md"))), units=s["units"], with_video=len(done),
           without=len(todo), folders=s["folders"], usable=s["usable"], exported=s["exported"], planned=s["planned"],
           free=s["free"], left_out=s["left_out"], tiles="\n".join(tiles), waiting=waiting, dances=dances,
           dropped="；另有 %d 个看过之后决定不做（见下）" % len(dropped) if dropped else "", dropped_list=left_out)


def weapon_note(model, attached):
    """HTML for the 武器 row: the weapon prefabs in this export, and how many more the unit has."""
    attached = attached or []
    names = {w.get("name") for w in attached}
    rest = [w for w in tc.pick_weapons(model.get("weapons") or [], 0) if w["name"] not in names]
    parts = []
    limbs = [w["name"] for w in attached if w.get("kind") == "limb"]
    others = [w["name"] for w in attached if w.get("kind") != "limb"]
    if limbs:
        parts.append('已带上 %s <span class="muted" title="游戏把这部分身体放在武器栏里，运行时才装到骨架上">（身体的一部分）</span>'
                     % "、".join("<code>%s</code>" % html.escape(n) for n in limbs))
    if others:
        parts.append("已带上武器 %s" % "、".join("<code>%s</code>" % html.escape(n) for n in others))
    if rest:
        parts.append('<span class="muted">另有 %d 个武器 prefab 默认不带（加 <code>--weapons</code>）</span>' % len(rest))
    return " · ".join(parts)


def pmx_note(report):
    """'222 骨 · 46 刚体 · 31 表情（标准 19）' from the export record of a PMX; '' without one."""
    if not report:
        return ""
    morphs = report.get("vertex_morphs") or []
    made = report.get("morphs_made") or []
    note = "%s 骨 · %s 刚体 · %d 表情" % (report.get("bones", "?"), report.get("rigid_bodies", "?"), len(morphs))
    if morphs:
        note += "（标准 %d）" % len(made) if made else "（只有游戏原名的，没有标准 MMD 表情）"
    if report.get("plain_rig"):
        note += " · 不是人形：骨架保持游戏原样，没有 IK 和物理"
    springs = report.get("bust_springs") or []
    if springs and springs[0].get("travel_cm"):         # the breast physics this unit got (tsquad_common.bust_fitted)
        s = springs[0]
        note += " · 胸部最多晃 ±%g cm（系数 %g：大小 %s cm%s）" % (
            s["travel_cm"][0], s.get("factor"), s.get("size_cm"),
            "，游戏上限 %g cm" % s["cap_cm"] if s.get("cap_cm") else "")
    return note


def render_card(row):
    esc = html.escape
    m, f, d = row["model"], row["files"], row["model"].get("details") or {}
    exported = bool(f["blend"])
    female = tc.is_female(m)
    badges = '<span class="badge badge-kind">%s</span>' % esc(tc.CATEGORY_ZH.get(m["category"], m["category"]))
    if female:
        badges += '<span class="badge badge-f" title="%s">♀</span>' % (
            "有胸部骨（Magica Cloth 的 Breast 组）" if d.get("bust") else "没有胸部骨，看预览图认的女性体型")
    for fmt in ("blend", "xps", "pmx"):
        if f[fmt]:
            badges += '<a class="badge badge-fmt" href="%s" title="%s">%s</a>' % (
                esc(file_uri(os.path.dirname(f[fmt]))), esc(os.path.dirname(f[fmt])), fmt)
    if row["thumb"]:
        figure = '<a class="shot" href="%s" target="_blank" rel="noopener" title="点击看原图"><img loading="lazy" src="%s" alt="%s">%s</a>' % (
            esc(file_uri(row["shot"])), esc(file_uri(row["thumb"])), esc(m["id"]),
            "" if exported else '<span class="ribbon">未导出 · 只是预览渲染</span>')
    elif row["icon"]:
        figure = '<div class="shot icon"><img loading="lazy" src="%s" alt="%s"></div>' % (esc(file_uri(row["icon"])), esc(m["id"]))
    else:
        figure = '<div class="shot"><div class="noimg">没有头像</div></div>'
    spec = "-"
    if d.get("vertices"):
        spec = "%s 顶点 · %s 三角面 · %s 蒙皮骨 · %s 表情 · %s 材质" % (
            d.get("vertices"), d.get("triangles"), d.get("bones"), d.get("shape_keys") or 0, d.get("materials"))
        if d.get("height_m"):
            spec += " · 高 %s m" % d["height_m"]
    command = "python export_model.py %s --xps --pmx --turntable" % m["id"]
    lines = ['<dt>名字</dt><dd>%s <span class="muted">%s</span></dd>' % (esc(m["name"]), esc(m["folder"])),
             '<dt>规格</dt><dd>%s</dd>' % esc(spec),
             '<dt>命令</dt><dd><code>%s</code> <button class="copy" data-copy="%s">复制</button></dd>' % (esc(command), esc(command))]
    if row.get("weapons"):
        lines.append('<dt>武器</dt><dd>%s</dd>' % row["weapons"])
    if exported:
        lines.append('<dt>blend</dt><dd><a href="%s" title="%s">%s</a> <span class="muted">%s</span> '
                     '<button class="copy" data-copy="%s">复制</button></dd>' % (
                         esc(file_uri(f["blend"])), esc(f["blend"]), esc(os.path.basename(f["blend"])),
                         human_size(row["blend_size"]), esc(f["blend"])))
        extra = []
        for key, label in (("face", "脸部"), ("expressions", "表情总览"), ("turntable", "转台视频"), ("xps_preview", "XPS 读回"),
                           ("pmx_dance", "PMX 舞蹈"), ("pmx_morphs", "PMX 表情")):
            if f[key]:
                extra.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(file_uri(f[key])), label))
        if extra:
            lines.append('<dt>图</dt><dd>%s</dd>' % " · ".join(extra))
        if row.get("videos"):                          # motions put on the PMX by dance_video.py / dance_batch.py
            def label(path):
                stem = os.path.splitext(os.path.basename(path))[0]
                return (stem[len(m["id"]) + 1:] if stem.startswith(m["id"] + "_") else stem) or "视频"

            links = ['<a href="%s" target="_blank" rel="noopener" title="%s">%s</a>' % (
                esc(file_uri(v)), esc(v), esc(label(v))) for v in row["videos"]]
            lines.append('<dt>视频</dt><dd>%s</dd>' % " · ".join(links))
        for fmt in ("xps", "pmx"):
            if f[fmt]:
                note = ' <span class="muted">%s</span>' % esc(row["pmx_note"]) if fmt == "pmx" and row.get("pmx_note") else ""
                lines.append('<dt>%s</dt><dd><a href="%s" title="%s">%s</a> <button class="copy" data-copy="%s">复制</button>%s</dd>' % (
                    fmt, esc(file_uri(os.path.dirname(f[fmt]))), esc(f[fmt]), esc(os.path.basename(f[fmt])), esc(f[fmt]), note))
    search = esc(" ".join([m["id"], m["name"], m["folder"], m["category"], m["group"]]).lower())
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-exported="{exp}" data-female="{fem}">
        {figure}
        <div class="body">
          <div class="titlerow"><h3>{mid}</h3>{badges}</div>
          <dl>
            {lines}
          </dl>
        </div>
      </article>
""".format(search=search, kind=esc(m["category"]), exp="1" if exported else "0", fem="1" if female else "0",
           figure=figure, mid=esc(m["id"]), badges=badges, lines="\n            ".join(lines))


def command_rows(rows):
    """[(command, what it does)] -> one copyable line each."""
    esc = html.escape
    return "\n".join('      <div class="cmd"><code>%s</code><button class="copy" data-copy="%s">复制</button>'
                     '<span class="what">%s</span></div>' % (esc(c), esc(c), what) for c, what in rows)


def tool_path(key, name):
    """The tool's name, with where it is on this machine when it is there."""
    path = TOOLS.get(key, "")
    return "%s（<code>%s</code>）" % (name, html.escape(path)) if path and os.path.isfile(path) else name


def on_this_machine(found):
    """A small mark for the manual: is the thing on the machine this page was made on."""
    return '<span class="ok">本机已有</span>' if found else '<span class="no">本机没找到</span>'


def addon_mark(name, *folders):
    """The add-on's name, and whether Blender's add-on folder (ADDON_DIR) holds it under one of `folders`."""
    return "<code>%s</code> %s" % (html.escape(name), on_this_machine(
        any(os.path.exists(os.path.join(ADDON_DIR, f)) for f in folders or (name,))))


def render_howto(root, counts):
    """The manual: how to export a model - the short way first, then step by step (what is needed, finding a
    model, exporting, looking at the result, dance videos), what the lines of a failed run mean, and the route
    without the scripts."""
    esc = html.escape
    scripts = os.path.dirname(HERE)
    repo = os.path.dirname(os.path.dirname(scripts))
    blender2xps = os.environ.get("BLENDER2XPS", os.path.join(os.path.dirname(repo), "blender2xps"))
    out = esc(root)
    full = "python export_model.py 24_kirara --xps --pmx --turntable"
    listing = command_rows([
        ("python list_models.py", "全部 %d 个单位，按类别分组，最后一列是已导出的格式" % counts["total"]),
        ("python list_models.py --female", "只列女性体型（%d 个）" % counts["female"]),
        ("python list_models.py --category character",
         "只看一类：<code>character</code> 角色 / <code>costume</code> 其他造型 / <code>monster</code> 怪物 / "
         "<code>special</code> / <code>boss</code> / <code>mob</code>"),
        ("python list_models.py --find asagi 24 kira*", "按名字、单位编号、id 找，支持通配符"),
        ("python list_models.py --details", "多列出顶点 / 三角面 / 蒙皮骨 / 表情数 / 身高（第一次要读一遍美术包，之后走缓存）"),
        ("python list_models.py --exported", "只列已经导出过的"),
        ("python list_models.py --html", "重新生成本页"),
    ])
    basic = command_rows([
        ("python export_model.py 24_kirara", "只出 <code>.blend</code>（卡通着色 + 描边）和三张检查图，约 15 秒"),
        (full, "全套：<code>.blend</code> + XPS + PMX + 转台视频，连同各自的检查图，约 2 分钟"),
        ("python export_model.py 24_kirara --xps --pmx",
         "不要转台视频。已经有 <code>.blend</code> 时这条只做转换，不重建 <code>.blend</code>"),
    ])
    batch = command_rows([
        ("python export_model.py asagi sakura 7", "一次几个：名字 = 这个角色的全部造型，数字 = 单位编号"),
        ("python export_model.py --category costume --xps --pmx", "一整类"),
        ("python export_model.py --female --xps --pmx --turntable --jobs 4",
         "全部女性体型，4 个同时跑。<b>中途停掉也没关系</b>，再跑同一条命令会跳过已有的接着做"),
        ("python export_model.py --category character --preview-only",
         "只渲预览图、不存 <code>.blend</code>（到 <code>_work\\previews</code>）：先看一批长什么样。"
         "本页没导出的卡片上那张「只是预览渲染」的图就是这么来的"),
    ])
    redo = command_rows([
        ("python export_model.py 24_kirara --xps --pmx --turntable --force", "已经有的也全部重做（<code>.blend</code>、转台视频、XPS、PMX）"),
        ("python export_model.py 24_kirara --xps --pmx --reconvert", "只从现有的 <code>.blend</code> 重做 XPS / PMX"),
        ("python export_model.py 24_kirara --xps --pmx --repreview", "只重渲 XPS / PMX 的检查图"),
    ])
    weapons = command_rows([
        ("python export_model.py 212_dullahan --xps --pmx --weapons --force",
         "连武器一起导：刀、枪、肩甲、头饰 …… 按游戏 prefab 里的位置装上"),
        ("python export_model.py 20_natsume --xps --pmx --weapon-grade 1 --force",
         "武器的升级外观：<code>0</code> 初始（默认）/ <code>1</code> / <code>2</code>"),
        ("python export_model.py 130_orc1 --xps --pmx --keep-weapon", "XPS / PMX 里带上停在原点的武器（默认不带）"),
    ])
    bust = command_rows([
        ("python export_model.py 1_asagi --pmx --reconvert --bust amount=1.3",
         "<code>amount</code> 整体幅度（1.3 = 多三成，0.5 = 减半）；<code>game=0</code> 不管游戏给这个角色的"
         "行程上限；<code>bounce_hz</code> / <code>sway_hz</code> / <code>ratio</code> 调软硬和阻尼（全部设置见 README）"),
    ])
    dancing = command_rows([
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>"',
         "给导出的 PMX 套一段 MMD 动作（<code>.vmd</code>，文件夹里的配乐会自动带上），渲成竖屏视频，"
         "放在 <code>&lt;角色&gt;\\video\\&lt;id&gt;\\</code>；同时存一份能直接打开播放的 <code>.blend</code>"),
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>" --backdrop 夜店舞台',
         "同上，换背景：写背景图名字里的一段（<code>_backgrounds</code> 里的图），或者任意一张图的路径"),
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>" --view chest --bust amount=1.3',
         "胸部特写（相机跟着上半身走），并只在这段视频里试别的胸部物理 —— 满意了再用第 2 步的 <code>--bust</code> 写进 PMX"),
        ("python export_backgrounds.py",
         "游戏里的背景图（剧情背景、过场画、天空全景，共 128 张）→ <code>%s\\_backgrounds\\</code>，"
         "里面的 <code>_总览_*.jpg</code> 是带名字的缩略图" % out),
    ])
    dance_batch = command_rows([
        ("python dance_batch.py --count 10 --jobs 1 --full-speed",
         "接着渲 10 个还没有视频的角色，一次一个（人还在用这台机器时用这个；机器空着可以 <code>--jobs 3</code>）"),
        ("python dance_batch.py 5_sakura 24_kirara", "指定角色"),
        ("python dance_batch.py --plan", "只算谁跳哪支舞、写列表，不渲"),
        ('python dance_batch.py --drop 58_yuphiesophie --why "原因"',
         "看过之后不要某个角色的视频：删掉它的视频，以后也不再给它渲，它的舞让给别人（<code>--undrop</code> 放回来）"),
        ("python dance_batch.py --list", "只重写列表和本页（比如手动删了某个视频之后）"),
    ])
    return """  <section class="howto" id="howto">
    <h2>怎么导出模型（操作说明）</h2>
    <p>下面每张卡片是游戏里的一个 3D 单位。<b>导出</b> = 把它从游戏的资源包里读出来，做成能直接打开的
      <code>.blend</code>（游戏的卡通着色 + 描边 + 骨架 + 表情），需要的话再转成 <b>XPS</b>（XNALara）和 <b>PMX</b>（MMD，带物理和表情）。
      不用启动游戏、不用联网、不需要密钥。两条路：<b>A. 用仓库里的脚本</b>（推荐，一条命令全做完 —— 下面的第 0–4 步）；
      <b>B. 完全不用脚本</b>，用现成的图形界面工具（只能拿到带骨架的原始模型，材质要自己接 —— 最后一栏）。</p>

    <div class="quick">
      <b>最短的路：三条命令</b> <span class="muted">（第一次用，先做下面的「第 0 步」）</span>
      <ol>
        <li>打开 PowerShell，进到脚本目录：
{cd}</li>
        <li>导出一个模型。这里是 Kirara；换别的模型就把 <code>24_kirara</code> 换成它的 id ——
          <b>每张卡片的「命令」一行就是它自己的这条命令</b>，点「复制」即可：
{full}
          约 2 分钟。最后一行是 <code>done: 1 built, 0 skipped, 0 failed</code> 就成了。</li>
        <li>刷新本页：这张卡片上会出现 <code>blend</code> / <code>xps</code> / <code>pmx</code> 的链接和各张检查图。
{refresh}</li>
      </ol>
    </div>

    <details open>
      <summary>第 0 步　准备（只做一次）</summary>
      <ol>
        <li>装 Python 包（读游戏的资源包、解贴图用；不需要 AssetStudio / AssetRipper）：
{pip}</li>
        <li><b>Blender 3.6</b>：<code>{blender}</code> {blender_mark}（装在别处就设环境变量 <code>TSQUAD_BLENDER</code>）。</li>
        <li><b>游戏</b>在 <code>{game}</code> {game_mark}（别处就设 <code>TSQUAD_GAME_DIR</code>）；<b>导出到</b> <code>{out}</code>
          （<code>TSQUAD_EXPORT_ROOT</code>）。</li>
        <li>按想要的格式，再准备右边一列：
          <table class="list">
            <tr><th>想要什么</th><th>命令里加</th><th>另外需要</th></tr>
            <tr><td><code>.blend</code> + 全身 / 脸部预览 + 表情总览图</td><td>什么都不加</td><td>不需要别的，Blender 里不用装任何插件</td></tr>
            <tr><td>转台视频</td><td><code>--turntable</code></td><td>同上</td></tr>
            <tr><td>XPS</td><td><code>--xps</code></td><td>Blender2XPS，放在仓库旁边：<code>{b2x}</code> {b2x_mark}（别处就设 <code>BLENDER2XPS</code>）；
              导完的读回检查图还要 Blender 插件 {xnalara}</td></tr>
            <tr><td>PMX</td><td><code>--pmx</code></td><td>Blender 3.6 的三个插件：{mmd_tools}、{convert}、{cloth}
              （最后一个在仓库的 <code>scripts\\blender_addons</code> 里）</td></tr>
            <tr><td>舞蹈视频</td><td>另外的脚本，见第 4 步</td><td>先有这个模型的 PMX，Blender 里有 <code>mmd_tools</code>；批量时
              <code>ffmpeg</code> / <code>ffprobe</code> 要在 PATH 里 {ffmpeg_mark}（缩略图、按配乐长度收尾用）</td></tr>
          </table>
          插件装上就行，不用自己去打勾 —— 脚本运行时会自己启用。「本机已有 / 本机没找到」是生成本页时在这台机器上看的；
          插件看的是 <code>{addons}</code> 这个文件夹（装在别处的会显示没找到，不影响使用）。</li>
      </ol>
    </details>

    <details open>
      <summary>第 1 步　找到要导的模型</summary>
      <p><b>在这一页找：</b>上面的搜索框输名字或编号；类别按钮、「只看女性」「只看已导出」可以叠加。没导出的卡片上是预览渲染
        （或游戏头像），<b>卡片的「命令」一行就是这个单位的导出命令</b>。「女性」的依据：游戏的配置表解不开，没有性别字段，所以按<b>胸部骨</b>认
        （{with_bust} 个），另有 {by_look} 个没有胸部骨的是看预览图补进名单的（卡片上 ♀ 的悬停提示会注明）。</p>
      <p><b>在命令行找：</b></p>
{listing}
      <p>整份清单同时写在 <code>{out}\\_meta\\model_list.md</code>。<b>id 的规则</b>：<code>&lt;单位编号&gt;_&lt;名字&gt;</code>，
        同一个角色的几套造型名字相同、编号不同（<code>1_asagi</code>、<code>253_asagi</code>、<code>271_asagi</code>），
        Boss 是 <code>b_&lt;编号&gt;_&lt;名字&gt;</code>。导出命令里写 id、编号或名字都行。</p>
    </details>

    <details open>
      <summary>第 2 步　导出</summary>
      <h3>一个模型</h3>
{basic}
      <h3>这条命令做了什么</h3>
      <ol>
        <li><b>读游戏资源</b>（Python + UnityPy，几秒）：在游戏的资源目录 <code>catalog.json</code> 里找到这个单位的美术包，读出骨架、网格、
          表情形态、材质的全部参数和贴图，临时放在 <code>{out}\\_work\\scenes\\&lt;id&gt;</code>（建好 <code>.blend</code> 后自动删掉，
          <code>--keep-work</code> 保留）。游戏把手臂或腿放在「武器栏」里的单位，那部分身体会自动带上。</li>
        <li><b>建 <code>.blend</code></b>（Blender 3.6 在后台运行，约 15 秒）：建骨架，把 UV 接缝处拆开的顶点焊回去，还原游戏的卡通着色
          （阴影色图、遮罩、MatCap、脸部阴影、边缘光）和描边，渲全身和脸部预览、每个表情一格的总览图，贴图打包进文件 →
          <code>&lt;角色&gt;\\blend\\&lt;id&gt;\\</code>。</li>
        <li><code>--turntable</code>：从 <code>.blend</code> 渲一段转台视频（转一圈 + 脸部特写扫光）。</li>
        <li><code>--xps</code>：用 Blender2XPS 导出 XPS（骨名换成 XPS 标准名，每个材质配它的底色图）→ <code>&lt;角色&gt;\\xps\\&lt;id&gt;\\</code>，
          再读回 Blender 摆一个姿势渲检查图。</li>
        <li><code>--pmx</code>：转成 MMD 标准骨架（Convert_to_MMD5），加物理（胸部、头发、裙子、丝带），从游戏的整脸表情里切出标准 MMD 表情，
          用 mmd_tools 导出 → <code>&lt;角色&gt;\\pmx\\&lt;id&gt;\\</code>；再把 PMX 读回来套一段舞蹈跑物理、把每个表情渲一格，作为检查图。</li>
        <li>把这次导出的数字记进 <code>{out}\\_meta\\exports.json</code>（卡片上 PMX 那行的「222 骨 · 46 刚体 · 31 表情」就来自它）。</li>
      </ol>
      <p>终端里看到的是这样（实测：全新的导出目录，从头到尾 2 分 02 秒）：</p>
      <pre>{sample}</pre>
      <p>要看的是最后一行的 <code>0 failed</code>，和 PMX 那行的 <code>torn 0</code>（把站姿转成 MMD 的 A-pose 时没有被扯开的边）、
        <code>grant violations 0</code>（付与骨的顺序没错）。</p>
      <h3>一批模型</h3>
{batch}
      <h3>重做</h3>
{redo}
      <h3>武器</h3>
{weapons}
      <p>游戏把「武器」做成单独的 prefab，运行时才挂到角色骨架上，而且<b>不只是刀枪</b> ——
        Natsume 的左臂、Tsuru 的右前臂（枪）、Snake Lady 的双臂、Saika 的双腿都放在武器栏里。这类<b>身体的一部分</b>默认就会带上
        （卡片的「武器」一行写着带了哪个）；真正的武器默认不带，加 <code>--weapons</code> 才带：位置取自 prefab 本身，
        握在手里、背在身上、戴在头上的大多是对的，但靠动作摆位的（Sayaneo 的爪链、Anje 的触手）会横着伸出去，
        挂点停在原点的会留在 <code>.blend</code> 的隐藏集合 <code>Weapons (parked)</code> 里、不进 XPS / PMX。</p>
      <h3>PMX 的胸部物理</h3>
{bust}
    </details>

    <details open>
      <summary>第 3 步　看结果、打开</summary>
      <pre>{out}\\&lt;角色&gt;\\                        &lt;角色&gt; = 单位的名字：1_asagi、253_asagi 都在 Asagi\\ 下
  blend\\&lt;id&gt;\\&lt;id&gt;.blend            贴图已打包在里面，整个文件夹可以单独拷走
                 &lt;id&gt;_preview.png / _face.png / _expressions.png（每个表情一格）/ _turntable.mp4
  xps\\&lt;id&gt;\\&lt;id&gt;.xps                + 贴图 + &lt;id&gt;_xps_preview.png（读回 Blender 摆了姿势渲的）
  pmx\\&lt;id&gt;\\&lt;id&gt;.pmx                + textures\\ + preview.png + preview_dance.png（套舞蹈跑物理）
                                       + preview_morphs.png（每个 MMD 表情一格，带名字）
  video\\&lt;id&gt;\\&lt;id&gt;_&lt;动作&gt;.mp4      dance_video.py 渲的视频；同名 .blend 里是模型 + 动作 + 烘好的物理，打开按播放就能看
{out}\\_videos\\&lt;动作名&gt;_&lt;角色名&gt;.mp4   dance_batch.py：每个角色一支舞（本页「舞蹈视频」一栏）
{out}\\_backgrounds\\                  export_backgrounds.py：游戏里的背景图 + _总览_*.jpg（缩略图总览）
{out}\\_meta\\exports.json             每次导出的记录；旁边的 model_list.md 是全部单位的清单
{out}\\_work\\logs\\&lt;id&gt;.*.log          每一步的 Blender 日志（出问题时看）</pre>
      <p><b>先看检查图</b> —— 不用开 Blender / XPS / MMD，卡片上「图」一行就是它们：</p>
      <table class="list">
        <tr><th>卡片上的链接</th><th>文件</th><th>看什么</th></tr>
        <tr><td>卡片大图、脸部</td><td><code>blend\\&lt;id&gt;\\&lt;id&gt;_preview.png</code>、<code>_face.png</code></td>
          <td>卡通着色和描边对不对，有没有缺的部件、没贴图的面</td></tr>
        <tr><td>表情总览</td><td><code>&lt;id&gt;_expressions.png</code></td><td>游戏原有的每个表情一格</td></tr>
        <tr><td>XPS 读回</td><td><code>xps\\&lt;id&gt;\\&lt;id&gt;_xps_preview.png</code></td>
          <td>XPS 读回 Blender，放下手臂、抬腿屈膝、转头：皮有没有跟着骨头走，贴图在不在</td></tr>
        <tr><td>PMX 舞蹈</td><td><code>pmx\\&lt;id&gt;\\preview_dance.png</code></td>
          <td>PMX 套一段舞蹈跑物理的 4 帧：头发、裙子、胸在动，没有东西飞出去</td></tr>
        <tr><td>PMX 表情</td><td><code>pmx\\&lt;id&gt;\\preview_morphs.png</code></td><td>每个 MMD 表情拉满渲一格，带名字</td></tr>
      </table>
      <p><b>再打开用：</b></p>
      <ul>
        <li><b>.blend</b>：用 Blender 3.6 打开（更新的版本没测过）。视图着色切到「材质预览」或「渲染」就是游戏的卡通着色；
          转动 <code>TSQ_Sun</code> 物体 = 改光照方向；表情在脸部网格 <code>face_*</code> 的形态键里，嘴里的牙和舌头会跟着走；
          描边是每个网格上的 <code>TSQ Outline</code> 修改器，不要就关掉。</li>
        <li><b>XPS</b>：{xps}，把 <code>&lt;id&gt;.xps</code> 拖进窗口，或菜单 Modify → Load Generic_Item 选它。
          骨名是 XPS 标准名，现成的姿势可以直接套。</li>
        <li><b>PMX</b>：{mmd}，把 <code>&lt;id&gt;.pmx</code> 拖进窗口，或在「モデル操作」面板点「読込」。带物理（头发、裙子、胸）和表情；
          视线用 <code>目上 / 目下 / 目左 / 目右</code> 四个表情（模型没有眼球骨）。</li>
      </ul>
    </details>

    <details>
      <summary>第 4 步（可选）　舞蹈视频和背景图</summary>
      <h3>一个模型套一段动作</h3>
{dancing}
      <h3>每个角色一支舞（本页「舞蹈视频」一栏就是这么来的）</h3>
{dance_batch}
      <p>批量的视频在 <code>{out}\\_videos\\</code>，文件名「动作名_角色名」；同一个文件夹里的 <code>_列表.md</code> 写着谁做了、谁没做、
        每支舞用没用。谁跳哪支舞只抽一次（记在 <code>_meta\\plan.json</code>），以后再跑不会变。动作合集只读，不往里写东西。</p>
    </details>

    <details>
      <summary>出问题时　终端里的这些话是什么意思</summary>
      <table class="list">
        <tr><th>看到</th><th>意思和办法</th></tr>
        <tr><td><code>catalog.json not found: …</code></td><td>游戏不在默认位置。设环境变量 <code>TSQUAD_GAME_DIR</code> 为游戏文件夹，
          PowerShell 里是 <code>$env:TSQUAD_GAME_DIR = "D:\\…\\Taimanin Squad"</code></td></tr>
        <tr><td><code>Blender not found: …</code></td><td>设 <code>TSQUAD_BLENDER</code> 为 <code>blender.exe</code> 的完整路径（要 3.6）</td></tr>
        <tr><td><code>no model matches: xxx</code></td><td>id 写错了。<code>python list_models.py --find xxx</code> 找一下，或者直接复制卡片上的命令</td></tr>
        <tr><td><code>&lt;id&gt;: already exported (…) - --force to redo</code></td><td>不是错：<code>.blend</code> 已经有了，又没要 XPS / PMX / 转台视频，
          所以没事可做。要重做加 <code>--force</code></td></tr>
        <tr><td><code>FAILED &lt;id&gt;: Blender failed for &lt;id&gt; (exit N), log: …</code></td><td>建 <code>.blend</code> 这一步失败。打开它给的日志
          （<code>{out}\\_work\\logs\\&lt;id&gt;.blender.log</code>），看最后几十行里的 Python 报错</td></tr>
        <tr><td><code>! XPS failed: …</code></td><td>看 <code>&lt;id&gt;.xps.log</code>；先确认第 0 步里的 Blender2XPS 在不在</td></tr>
        <tr><td><code>! PMX failed, log: …</code></td><td>看 <code>&lt;id&gt;.pmx.log</code>；先确认第 0 步里的三个插件都装了</td></tr>
        <tr><td><code>! turntable failed, log: …</code></td><td>看 <code>&lt;id&gt;.turntable.log</code>（<code>.blend</code> 本身不受影响）</td></tr>
        <tr><td><code>PMX: not a human figure - …</code></td><td>不是错：蛇身、鱼尾、翅膀代替手臂的 4 个单位套不了标准 MMD 骨架，PMX 保持游戏原来的骨头，
          没有 IK 和物理，也套不了舞蹈</td></tr>
        <tr><td><code>no PMX yet - run: python export_model.py &lt;id&gt; --pmx</code></td><td>渲舞蹈视频之前要先有这个模型的 PMX</td></tr>
        <tr><td>最后一行 <code>done: N built, N skipped, N failed</code></td><td>有 failed 时它下面逐个列出失败的模型和原因。修好后把同一条命令再跑一遍，
          已经成功的会跳过</td></tr>
      </table>
      <p>游戏更新后清单没跟着变：<code>python list_models.py --refresh</code>（重新读一遍游戏的资源目录）。
        想确认有没有哪个单位缺胳膊少腿：<code>python rig_lint.py</code> 会列出「肢体上没有皮」的单位。</p>
    </details>

    <details>
      <summary>B　完全不用脚本：AssetStudio + Blender（实测过的手工路线）</summary>
      <p class="muted">实测对象是 Kirara（<code>prf_24</code>）：导出用的是 AssetStudioMod v0.19.0 的命令行版（和图形界面同一个内核），
        再把 FBX 导进 Blender 3.6；下面的菜单名取自图形界面程序本身。</p>
      <ol>
        <li><b>看有哪些模型</b>：资源管理器打开 <code>{bundles}</code>，搜索 <code>localunit_aos_assets_</code>。
          每个文件是一个单位的美术包，文件名就是 <code>localunit_aos_assets_&lt;编号&gt;_&lt;名字&gt;_&lt;hash&gt;.bundle</code>
          （例：<code>localunit_aos_assets_24_kirara_….bundle</code>，6 MB）。不带 <code>aos</code> 的
          <code>localunit_assets_*</code> 是同一个单位的动作和武器包。</li>
        <li><b>取出模型</b>：打开 {assetstudio} → <code>File &gt; Load file</code> 选那个美术包 → <code>Asset List</code> 页里
          用 <code>Filter Type</code> 只留 Animator → 右键 <code>prf_&lt;编号&gt;</code>（带 <code>_LOD1</code> 的是低模）→
          <code>Export Animator + selected AnimationClips</code>。得到 <code>prf_&lt;编号&gt;.fbx</code> 和同一文件夹里的 PNG 贴图。
          （另一种点法：<code>Scene Hierarchy</code> 页勾上 <code>prf_&lt;编号&gt;</code> → <code>Model &gt; Export selected objects (merge)</code>。）</li>
        <li><b>大小</b>：AssetStudio 默认的 FBX 进 Blender 只有 1.9 厘米高。两个办法任选其一：导出前在
          <code>Options &gt; Export options</code> 把 <code>ScaleFactor</code> 改成 100；或者 Blender 导入 FBX 时把「缩放」填 100。
          两种都实测过，Kirara 进来是 1.88 米。</li>
        <li><b>进 Blender</b>：<code>文件 &gt; 导入 &gt; FBX</code>。骨架、蒙皮、脸上的表情形态键（<code>closed_eyes</code>、
          <code>smile_face</code> ……）都在。</li>
        <li><b>贴图要自己接</b>：游戏着色器的贴图槽叫 <code>_BaseMap</code>，AssetStudio 只认 <code>_MainTex</code>，所以导入后
          材质几乎都是空的。按名字接底色图：<code>mat_face*</code> → <code>tex_d_face</code>，<code>mat_hair*</code> → <code>tex_d_hair</code>，
          <code>mat_skin / span / metal</code> → <code>tex_d_costume</code>，<code>mat_cloth</code> → <code>tex_d_cloth</code>。
          其余几张：<code>tex_s_*</code> 是阴影色（暗部直接换成它），<code>tex_m_*</code> 是遮罩（R 自发光 / G 高光 / B MatCap），
          <code>tex_on_face</code> 是脸部阴影的阈值图。</li>
        <li><b>手工路线拿不到的</b>（脚本替你做了的）：卡通着色和描边；UV 接缝处拆开的顶点没有焊回去；嘴里的形态键不会跟着脸走；
          <code>em_*</code> 表情贴片没有藏起来；Magica Cloth 的布料组只是一堆空物体；阿莎姬、不知火、飞鸟、胧的腿蒙在另一条骨链上，
          摆腿时小腿不跟着走（脚本导出时修掉了）；以及 XPS / PMX。</li>
        <li><b>再往 XPS / PMX 走</b>：手工步骤和别的游戏一样，见仓库里的 <code>docs\\vindictus-fiona-manual-export.md</code>
          第 5 节（Blender2XPS 导出 XPS）和第 6 节（Convert to MMD 5 转 PMX）。</li>
      </ol>
    </details>
  </section>
""".format(cd=command_rows([("cd " + scripts, "")]), full=command_rows([(full, "")]),
           refresh=command_rows([("python list_models.py --html", "")]),
           pip=command_rows([("pip install UnityPy lz4 numpy pillow", "")]),
           blender=esc(tc.BLENDER), blender_mark=on_this_machine(os.path.isfile(tc.BLENDER)),
           game=esc(tc.GAME_DIR), game_mark=on_this_machine(os.path.isfile(tc.CATALOG)), out=out,
           b2x=esc(blender2xps), b2x_mark=on_this_machine(os.path.isdir(blender2xps)),
           xnalara=addon_mark("XNALaraMesh", "XNALaraMesh-master", "XNALaraMesh", "xps_tools"),
           mmd_tools=addon_mark("mmd_tools"), convert=addon_mark("Convert_to_MMD5"), cloth=addon_mark("mmd_cloth_physics"),
           ffmpeg_mark=on_this_machine(bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))),
           addons=esc(ADDON_DIR), bundles=esc(tc.BUNDLE_DIR),
           with_bust=counts["female"] - counts["by_look"], by_look=counts["by_look"],
           listing=listing, basic=basic, sample=esc(SAMPLE_RUN.format(out=root)), batch=batch, redo=redo,
           weapons=weapons, bust=bust, dancing=dancing, dance_batch=dance_batch,
           xps=tool_path("xps", "XNALara XPS 11.8"), mmd=tool_path("mmd", "MikuMikuDance"),
           assetstudio=tool_path("assetstudio", "AssetStudioMod 的 GUI"))


def render(rows, root):
    esc = html.escape
    exported = [r for r in rows if r["files"]["blend"]]
    female = [r for r in rows if tc.is_female(r["model"])]
    kinds = [k for k in tc.CATEGORY_ORDER if any(r["model"]["category"] == k for r in rows)]
    chips = "".join('<button class="chip" data-kind="%s">%s (%d)</button>' % (
        esc(k), esc(tc.CATEGORY_ZH[k]), sum(1 for r in rows if r["model"]["category"] == k)) for k in kinds)
    exported_first = sorted(rows, key=lambda r: (0 if r["files"]["blend"] else 1))
    by_look = sum(1 for r in female if not (r["model"].get("details") or {}).get("bust"))
    counts = {"total": len(rows), "female": len(female), "by_look": by_look}
    return PAGE_TEMPLATE.format(
        generated=esc(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")), root=esc(root),
        total=len(rows), exported=len(exported),
        xps=sum(1 for r in rows if r["files"]["xps"]), pmx=sum(1 for r in rows if r["files"]["pmx"]),
        female=len(female), female_done=sum(1 for r in female if r["files"]["blend"]),
        by_look=by_look,
        size=human_size(sum(r["blend_size"] for r in rows)), chips=chips, howto=render_howto(root, counts),
        videos=render_videos(root),
        cards="".join(render_card(r) for r in exported_first))


def build(models=None, root=tc.EXPORT_ROOT, out=None, force=False):
    """Write the page; returns its path.  `models` = list_models' list (with details) or None to read it here."""
    if models is None:
        sys.path.insert(0, os.path.dirname(HERE))
        import list_models

        models = tc.discover_models(tc.catalog_assets(root), root)
        list_models.add_details(models, root)
    rows = collect(models, root, force)
    out = out or os.path.join(HERE, PAGE_NAME)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(rows, root))
    return out


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Taimanin Squad 模型画廊</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --kind: #1f7a4d; --kind-bg: #e3f4ea;
  --f: #b0306a; --f-bg: #fbe6ef; --fmt: #7a3fa0; --fmt-bg: #f1e7f8; --shot: #9fa3ac;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --kind: #7fd1a3; --kind-bg: #1c3527;
    --f: #f39ac0; --f-bg: #3d1f2c; --fmt: #c99ae6; --fmt-bg: #33203d; --shot: #5d616b;
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
.toolbar {{ position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  padding: 12px 32px; background: var(--panel); border-bottom: 1px solid var(--line); }}
#q {{ flex: 1 1 260px; min-width: 200px; padding: 8px 12px; font: inherit; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }}
.chip, .copy, .toggle {{ font: inherit; font-size: 12px; padding: 5px 11px; cursor: pointer; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 999px; }}
.chip.on, .toggle.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.copy {{ padding: 1px 8px; font-size: 11px; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
.jump {{ font-size: 12px; }}
main {{ padding: 22px 32px 48px; }}
.grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); align-items: start; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 11px; overflow: hidden;
  display: flex; flex-direction: column; }}
.card[hidden] {{ display: none !important; }}
.shot {{ display: block; position: relative; background: var(--shot); line-height: 0; text-align: center; }}
.shot img {{ width: 100%; height: auto; display: block; }}
.shot.icon {{ padding: 14px 0; }}
.shot.icon img {{ width: auto; max-width: 70%; max-height: 190px; display: inline-block; }}
.ribbon {{ position: absolute; left: 8px; top: 8px; padding: 2px 9px; border-radius: 999px; line-height: 1.6;
  font-size: 11px; color: #fff; background: rgba(20, 22, 28, .62); }}
.noimg {{ padding: 46px 0; color: var(--muted); font-size: 12px; line-height: 1.6; }}
.body {{ padding: 12px 14px 14px; }}
.titlerow {{ display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }}
.titlerow h3 {{ margin: 0 4px 0 0; font-size: 15px; font-family: Consolas, monospace; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; text-decoration: none; }}
.badge-kind {{ color: var(--kind); background: var(--kind-bg); }}
.badge-f {{ color: var(--f); background: var(--f-bg); cursor: help; }}
.badge-fmt {{ color: var(--fmt); background: var(--fmt-bg); font-family: Consolas, monospace; }}
dl {{ margin: 0; display: grid; grid-template-columns: 42px 1fr; gap: 3px 10px; font-size: 13px; }}
dt {{ color: var(--muted); }}
dd {{ margin: 0; word-break: break-all; }}
code {{ font-family: Consolas, monospace; font-size: 12px; }}
a {{ color: var(--accent); }}
.muted {{ color: var(--muted); font-size: 12px; }}
.howto {{ margin: 0 0 22px; padding: 16px 20px 8px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 11px; font-size: 13px; scroll-margin-top: 64px; }}
.howto h2 {{ margin: 0 0 6px; font-size: 17px; }}
.howto h3 {{ margin: 12px 0 4px; font-size: 13.5px; }}
.howto p {{ margin: 6px 0; }}
.quick {{ margin: 10px 0 12px; padding: 10px 14px 4px; background: var(--bg); border: 1px solid var(--accent);
  border-radius: 9px; }}
.quick > b {{ font-size: 14px; }}
.ok, .no {{ font-size: 11px; padding: 1px 7px; border-radius: 999px; white-space: nowrap; }}
.ok {{ color: var(--kind); background: var(--kind-bg); }}
.no {{ color: var(--f); background: var(--f-bg); }}
.howto details {{ border-top: 1px solid var(--line); padding: 8px 0; }}
.howto summary {{ cursor: pointer; font-weight: 600; font-size: 14px; padding: 2px 0; }}
.howto ol, .howto ul {{ margin: 6px 0; padding-left: 22px; }}
.howto li {{ margin: 5px 0; }}
.howto pre {{ margin: 6px 0; padding: 10px 12px; overflow-x: auto; background: var(--bg); border: 1px solid var(--line);
  border-radius: 7px; font: 12px/1.55 Consolas, monospace; }}
.cmd {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin: 3px 0; padding: 4px 10px;
  background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }}
.cmd > code {{ font-size: 12.5px; white-space: pre-wrap; word-break: break-all; }}
.cmd .what {{ color: var(--muted); flex: 1 1 260px; }}
h2.listhead {{ margin: 0 0 12px; font-size: 17px; scroll-margin-top: 64px; }}
.vids {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); margin: 12px 0 14px; }}
.vid {{ display: block; text-decoration: none; color: var(--ink); background: var(--bg); border: 1px solid var(--line);
  border-radius: 9px; overflow: hidden; }}
.vid img {{ width: 100%; height: auto; display: block; }}
.vid .cap {{ display: block; padding: 6px 8px 8px; font-size: 12px; line-height: 1.45; word-break: break-all; }}
table.list {{ border-collapse: collapse; margin: 8px 0 4px; font-size: 12.5px; width: 100%; }}
table.list th, table.list td {{ text-align: left; padding: 3px 10px 3px 0; border-bottom: 1px solid var(--line);
  vertical-align: top; }}
table.list tr.st0 td:nth-child(4) {{ color: var(--kind); font-weight: 600; }}
table.list tr.st3 td {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>Taimanin Squad 模型画廊</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{root}</code> · 由 <code>scripts/taimaninsquad/html/make_gallery.py</code> 生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>游戏里的 3D 单位</span></div>
    <div class="stat" title="有胸部骨的，加上 {by_look} 个没有胸部骨、看预览图认出来的"><b>{female}</b><span>女性体型（已导出 {female_done}）</span></div>
    <div class="stat"><b>{exported}</b><span>已导出 .blend</span></div>
    <div class="stat"><b>{xps}</b><span>XPS</span></div>
    <div class="stat"><b>{pmx}</b><span>PMX</span></div>
    <div class="stat"><b>{size}</b><span>.blend 合计</span></div>
  </div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="搜索 id / 名字，例如 asagi、24、yukikaze" autocomplete="off">
  {chips}
  <button class="toggle" id="only-exported">只看已导出</button>
  <button class="toggle" id="only-female">只看女性</button>
  <a class="jump" href="#howto">怎么导出</a>
  <a class="jump" href="#videos">舞蹈视频</a>
  <a class="jump" href="#models">模型列表</a>
  <span class="count" id="count"></span>
</div>
<main>
{howto}
{videos}  <h2 class="listhead" id="models">模型列表</h2>
  <div class="grid" id="grid">
{cards}  </div>
</main>
<script>
(function () {{
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var q = document.getElementById('q'), count = document.getElementById('count');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var onlyExported = document.getElementById('only-exported'), onlyFemale = document.getElementById('only-female');
  var kind = '';
  function apply() {{
    var words = q.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
    cards.forEach(function (c) {{
      var text = c.getAttribute('data-search');
      var ok = words.every(function (w) {{ return text.indexOf(w) >= 0; }});
      if (kind && c.getAttribute('data-kind') !== kind) ok = false;
      if (onlyExported.classList.contains('on') && c.getAttribute('data-exported') !== '1') ok = false;
      if (onlyFemale.classList.contains('on') && c.getAttribute('data-female') !== '1') ok = false;
      c.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
  }}
  chips.forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      var k = chip.getAttribute('data-kind');
      kind = (kind === k) ? '' : k;
      chips.forEach(function (c) {{ c.classList.toggle('on', c.getAttribute('data-kind') === kind); }});
      apply();
    }});
  }});
  [onlyExported, onlyFemale].forEach(function (b) {{
    b.addEventListener('click', function () {{ b.classList.toggle('on'); apply(); }});
  }});
  q.addEventListener('input', apply);
  document.addEventListener('click', function (e) {{
    var b = e.target.closest ? e.target.closest('.copy') : null;
    if (!b) return;
    var text = b.getAttribute('data-copy');
    function done() {{ var old = b.textContent; b.textContent = '已复制'; setTimeout(function () {{ b.textContent = old; }}, 1200); }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text).then(done, function () {{ window.prompt('复制：', text); }});
    }} else {{ window.prompt('复制：', text); }}
  }});
  apply();
}})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT, help="导出根目录（默认 %(default)s）")
    ap.add_argument("--out", default=None, help="输出 HTML（默认本脚本旁的 index.html）")
    ap.add_argument("--force", action="store_true", help="即使缩略图是新的也重建")
    a = ap.parse_args()
    print(build(None, a.export_root, a.out, a.force))


if __name__ == "__main__":
    main()
