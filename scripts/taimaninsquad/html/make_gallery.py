"""把 Taimanin Squad 的全部 3D 单位做成一页可浏览的 HTML：导出过的显示预览图和 .blend / XPS / PMX 的位置，
没导出的显示渲染预览（没有就用游戏自带头像）和导出命令；页首是「手动操作说明」—— 自己怎么列模型、怎么导出。

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
        shot = files["preview"] if files["blend"] else files["survey"]
        thumb = build_thumb(shot, os.path.join(gallery, "thumbs", mid + ".jpg"), force)
        rows.append({"model": m, "files": files, "thumb": thumb, "shot": shot, "icon": icons.get(mid, ""),
                     "videos": videos,
                     "blend_size": os.path.getsize(files["blend"]) if files["blend"] else 0,
                     "pmx_note": pmx_note((records.get(mid) or {}).get("pmx_report")) if files["pmx"] else "",
                     "weapons": weapon_note(m, (records.get(mid) or {}).get("weapon_prefabs") if files["blend"] else None)})
    return rows


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
        if row.get("videos"):                          # motions put on the PMX by dance_video.py
            links = ['<a href="%s" target="_blank" rel="noopener" title="%s">%s</a>' % (
                esc(file_uri(v)), esc(v), esc(os.path.splitext(os.path.basename(v))[0][len(m["id"]) + 1:] or "视频"))
                for v in row["videos"]]
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


def render_howto(root, counts):
    """The manual: how to list the models and export them yourself - with the scripts, or by hand."""
    esc = html.escape
    scripts = os.path.dirname(HERE)
    repo = os.path.dirname(os.path.dirname(scripts))
    blender2xps = os.path.join(os.path.dirname(repo), "blender2xps")
    out = esc(root)
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
    exporting = command_rows([
        ("python export_model.py 24_kirara", "只出 <code>.blend</code>（卡通着色 + 描边，约 10 秒）"),
        ("python export_model.py 24_kirara --xps --pmx --turntable",
         "<code>.blend</code> + XPS + MMD PMX + 转台视频，连同各自的检查图，约 2 分钟"),
        ("python export_model.py asagi sakura 7", "一次几个：名字 = 这个角色的全部造型，数字 = 单位编号"),
        ("python export_model.py --category costume --xps --pmx", "一整类"),
        ("python export_model.py --female --xps --pmx --turntable --jobs 4",
         "全部女性体型，4 个同时跑。中途停掉也没关系，再跑同一条命令会跳过已有的接着做"),
        ("python export_model.py 24_kirara --xps --pmx --force", "已经有的也全部重做"),
        ("python export_model.py 24_kirara --xps --pmx --reconvert", "只从现有的 <code>.blend</code> 重做 XPS / PMX"),
        ("python export_model.py 212_dullahan --xps --pmx --weapons --force",
         "连武器一起导：刀、枪、肩甲、头饰 …… 按游戏 prefab 里的位置装上（见下面的说明）"),
        ("python export_model.py 20_natsume --xps --pmx --weapon-grade 1 --force",
         "武器的升级外观：<code>0</code> 初始（默认）/ <code>1</code> / <code>2</code>"),
        ("python export_model.py 130_orc1 --xps --pmx --keep-weapon", "XPS / PMX 里带上停在原点的武器（默认不带）"),
        ("python export_model.py 1_asagi --pmx --reconvert --bust amount=1.3",
         "PMX 的胸部物理：<code>amount</code> 整体幅度（1.3 = 多三成，0.5 = 减半）；<code>game=0</code> 不管游戏给这个角色的"
         "行程上限；<code>bounce_hz</code> / <code>sway_hz</code> / <code>ratio</code> 调软硬和阻尼（全部设置见 README）"),
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>"',
         "给导出的 PMX 套一段 MMD 动作（<code>.vmd</code>，文件夹里的配乐会自动带上），渲成竖屏视频，"
         "放在 <code>&lt;角色&gt;\\video\\&lt;id&gt;\\</code>；同时存一份能直接打开播放的 <code>.blend</code>"),
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>" --backdrop 夜店舞台',
         "同上，换背景：写背景图名字里的一段（下面那个文件夹里的图），或者任意一张图的路径"),
        ('python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\<动作文件夹>" --view chest --bust amount=1.3',
         "胸部特写（相机跟着上半身走），并只在这段视频里试别的胸部物理 —— 满意了再用上一条写进 PMX"),
        ("python export_backgrounds.py",
         "游戏里的背景图（剧情背景、过场画、天空全景，共 128 张）→ <code>%s\\_backgrounds\\</code>，"
         "里面的 <code>_总览_*.jpg</code> 是带名字的缩略图" % out),
        ("python list_models.py --html", "导完刷新本页"),
    ])
    return """  <section class="howto" id="howto">
    <h2>手动操作说明：怎么看有哪些模型、怎么导出</h2>
    <p>下面每张卡片是游戏里的一个 3D 单位。自己动手有两条路：<b>A. 用仓库里的脚本</b>（推荐，一条命令出卡通着色的
      <code>.blend</code>、XPS、PMX）；<b>B. 完全不用脚本</b>，用现成的图形界面工具（只能拿到带骨架的原始模型，材质要自己接）。</p>

    <details open>
      <summary>A-1　准备（只做一次）</summary>
      <ol>
        <li>打开 PowerShell，进到脚本目录：
{cd}</li>
        <li>装 Python 包：
{pip}</li>
        <li>Blender 3.6：<code>{blender}</code>（装在别处就设环境变量 <code>TSQUAD_BLENDER</code>）。只出 <code>.blend</code> 不需要任何插件。</li>
        <li>要出 XPS：仓库旁边要有 Blender2XPS（<code>{b2x}</code>）。要出 PMX：Blender 3.6 里要装好
          <code>mmd_tools</code>、<code>Convert_to_MMD5</code>、<code>mmd_cloth_physics</code> 三个插件。</li>
        <li>游戏在 <code>{game}</code>（别处就设 <code>TSQUAD_GAME_DIR</code>），导出到 <code>{out}</code>
          （<code>TSQUAD_EXPORT_ROOT</code>）。不用启动游戏、不用联网、不需要密钥。</li>
      </ol>
    </details>

    <details open>
      <summary>A-2　看有哪些模型</summary>
      <p><b>在这一页看：</b>上面的搜索框输名字或编号；类别按钮、「只看女性」「只看已导出」可以叠加。没导出的卡片上是预览渲染
        （或游戏头像），带着这个单位的导出命令。「女性」的依据：游戏的配置表解不开，没有性别字段，所以按<b>胸部骨</b>认
        （{with_bust} 个），另有 {by_look} 个没有胸部骨的是看预览图补进名单的（卡片上 ♀ 的悬停提示会注明）。</p>
      <p><b>在命令行看：</b></p>
{listing}
      <p>整份清单同时写在 <code>{out}\\_meta\\model_list.md</code>。<b>id 的规则</b>：<code>&lt;单位编号&gt;_&lt;名字&gt;</code>，
        同一个角色的几套造型名字相同、编号不同（<code>1_asagi</code>、<code>253_asagi</code>、<code>271_asagi</code>），
        Boss 是 <code>b_&lt;编号&gt;_&lt;名字&gt;</code>。导出命令里写 id、编号或名字都行。</p>
    </details>

    <details open>
      <summary>A-3　导出</summary>
{exporting}
      <p><b>关于武器：</b>游戏把「武器」做成单独的 prefab，运行时才挂到角色骨架上，而且<b>不只是刀枪</b> ——
        Natsume 的左臂、Tsuru 的右前臂（枪）、Snake Lady 的双臂、Saika 的双腿都放在武器栏里。这类<b>身体的一部分</b>默认就会带上
        （卡片的「武器」一行写着带了哪个）；真正的武器默认不带，加 <code>--weapons</code> 才带：位置取自 prefab 本身，
        握在手里、背在身上、戴在头上的大多是对的，但靠动作摆位的（Sayaneo 的爪链、Anje 的触手）会横着伸出去，
        挂点停在原点的会留在 <code>.blend</code> 的隐藏集合 <code>Weapons (parked)</code> 里、不进 XPS / PMX。</p>
      <p>导出失败时看 <code>{out}\\_work\\logs\\&lt;id&gt;.*.log</code>（每一步各有一份 Blender 日志）；每次导出的数字记录在
        <code>{out}\\_meta\\exports.json</code>。想确认有没有哪个单位缺胳膊少腿：<code>python rig_lint.py</code>
        会列出「肢体上没有皮」的单位。</p>
    </details>

    <details>
      <summary>A-4　导出的东西在哪、怎么打开</summary>
      <pre>{out}\\&lt;角色&gt;\\
  blend\\&lt;id&gt;\\&lt;id&gt;.blend            贴图已打包在里面，整个文件夹可以单独拷走
                 &lt;id&gt;_preview.png / _face.png / _expressions.png（每个表情一格）/ _turntable.mp4
  xps\\&lt;id&gt;\\&lt;id&gt;.xps                + 贴图 + &lt;id&gt;_xps_preview.png（读回 Blender 摆了姿势渲的）
  pmx\\&lt;id&gt;\\&lt;id&gt;.pmx                + textures\\ + preview.png + preview_dance.png（套舞蹈跑物理）
                                       + preview_morphs.png（每个 MMD 表情一格，带名字）
  video\\&lt;id&gt;\\&lt;id&gt;_&lt;动作&gt;.mp4      dance_video.py 渲的视频；同名 .blend 里是模型 + 动作 + 烘好的物理，打开按播放就能看
{out}\\_backgrounds\\                  export_backgrounds.py：游戏里的背景图 + _总览_*.jpg（缩略图总览）</pre>
      <ul>
        <li><b>.blend</b>：用 Blender 3.6 打开（更新的版本没测过）。视图着色切到「材质预览」或「渲染」就是游戏的卡通着色；
          转动 <code>TSQ_Sun</code> 物体 = 改光照方向；表情在脸部网格 <code>face_*</code> 的形态键里，嘴里的牙和舌头会跟着走；
          描边是每个网格上的 <code>TSQ Outline</code> 修改器，不要就关掉。</li>
        <li><b>XPS</b>：{xps}，把 <code>&lt;id&gt;.xps</code> 拖进窗口，或菜单 Modify → Load Generic_Item 选它。
          骨名是 XPS 标准名，现成的姿势可以直接套。</li>
        <li><b>PMX</b>：{mmd}，把 <code>&lt;id&gt;.pmx</code> 拖进窗口，或在「モデル操作」面板点「読込」。带物理（头发、裙子、胸）和表情；
          视线用 <code>目上 / 目下 / 目左 / 目右</code> 四个表情（模型没有眼球骨）。</li>
        <li>卡片上的「XPS 读回」「PMX 舞蹈」「PMX 表情」就是上面那几张检查图，不开 XPS / MMD 也能先看一眼结果。</li>
      </ul>
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
""".format(cd=command_rows([("cd " + scripts, "")]),
           pip=command_rows([("pip install UnityPy lz4 numpy pillow", "")]),
           blender=esc(tc.BLENDER), b2x=esc(blender2xps), game=esc(tc.GAME_DIR), out=out, bundles=esc(tc.BUNDLE_DIR),
           with_bust=counts["female"] - counts["by_look"], by_look=counts["by_look"],
           listing=listing, exporting=exporting, xps=tool_path("xps", "XNALara XPS 11.8"),
           mmd=tool_path("mmd", "MikuMikuDance"), assetstudio=tool_path("assetstudio", "AssetStudioMod 的 GUI"))


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
.howto p {{ margin: 6px 0; }}
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
  <a class="jump" href="#howto">操作说明</a>
  <a class="jump" href="#models">模型列表</a>
  <span class="count" id="count"></span>
</div>
<main>
{howto}
  <h2 class="listhead" id="models">模型列表</h2>
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
