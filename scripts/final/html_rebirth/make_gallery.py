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
        appendix=APPENDIX_HTML,
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, mods=mods, chips=chips, chr_options=chr_options, cards=cards)


APPENDIX_HTML = r"""
<section class="appendix">
    <h2>附录 · 手工导出教程</h2>
    <p>脚本都在 <code>scripts\final\</code>，必须在装有游戏的机器上跑（FModel 直接读安装目录里的 <code>.utoc/.ucas</code>；游戏本身不用开，只有生成 mapping 那一次要）。
      三段：FModel 把 IoStore 里的 Player 变体导成 ActorX → 无头 Blender 按材质 JSON 配贴图出 .blend → 补渲预览、生成本页。下面的命令都在 <code>scripts\final</code> 下执行；
      <code>E:\code\othercode\ripper_tpose</code> 是作者的 clone 位置，换成你自己的。
      原理全文见 <code>docs\final-fantasy-vii-rebirth-extraction.md</code>，109 个变体的逐项状态见 <code>docs\ff7rebirth-player-export-inventory.md</code> §0
      （同文件 §1 的计数和 §5 的勾选清单还是 2026-09-05 批量之前的旧状态，别照着看）。</p>

    <h3>前提</h3>
    <table>
      <tr><th>工具</th><th>从哪里拿 / 脚本默认认的位置与版本</th></tr>
      <tr><td>游戏</td><td>Steam 版，<code>D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH</code>（<code>prepare_fmodel.ps1 -GameRoot</code> 默认值）。
        位置不同：Steam 库里右键游戏 → 管理 → 浏览本地文件</td></tr>
      <tr><td>FModel 4.4.4.0</td><td><code>https://github.com/4sval/FModel</code> 的 Releases 下载，放到 <code>E:\tools\FModel\FModel.exe</code>（<code>-FModelExe</code> 默认值；<code>fmodel_export_player.py</code> 顶部的 <code>FMODEL</code> 常量
        写作 <code>E:\tools\fmodel\FModel.exe</code>，Windows 不区分大小写，同一个文件）。无命令行；设置在 <code>%APPDATA%\FModel\AppSettings.json</code>。
        脚本按 4.4.4.0 的菜单名 / 设置键写，别的版本不保证</td></tr>
      <tr><td>.usmap</td><td><code>D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap</code>。仓库不带、也没有下载来源：用 UE4SS v3.0.1 Beta
        （<code>https://github.com/UE4SS-RE/RE-UE4SS</code> 的 Releases）在游戏里 DumpUSMAP 一次，步骤见下面的 note；生成后 FModel 离线读包，游戏不用再开</td></tr>
      <tr><td>Blender 3.6.15</td><td>blender.org 的 3.6 LTS 下载页取 <code>blender-3.6.15-windows-x64.zip</code>，解压到 <code>D:\Program Files\</code> 得到默认路径
        <code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code> 默认值）；用安装器装的（<code>C:\Program Files\Blender Foundation\Blender 3.6\blender.exe</code>）
        第二步给 <code>-BlenderExe</code>，第三步命令里的路径也跟着改。要 3.6，别用 4.x。
        然后<b>在这份 3.6 里</b>装 <b>io_scene_psk_psa 5.0.6</b>：<code>https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6</code> 下 ZIP，
        Edit &gt; Preferences &gt; Add-ons &gt; Install… 选 ZIP 并勾选启用，File &gt; Import 里出现 <b>Unreal PSK (.psk/.pskx)</b> 即可。
        装在 4.x 里 3.6 看不到；装了没勾启用也行，无头 worker 会自己 <code>addon_enable</code></td></tr>
      <tr><td>仓库插件</td><td><code>ff7rebirth_tools.py</code>（0.3.0）按路径加载，不必装进 Blender；想在 GUI 里手工导入或绑手套（<b>FF7RB</b> 页签）才装：Add-ons &gt; Install… 选这个 .py</td></tr>
      <tr><td>Python 3</td><td>python.org 的 3.x 安装包，勾 Add to PATH（新装 Win11 直接敲 <code>python</code> 会跳微软商店，那不是装好了）；用系统 Python，不是 Blender 自带的。
        然后 <code>pip install pywinauto Pillow</code>：前者驱动 FModel，后者缩本页缩略图</td></tr>
    </table>
    <p>这条线<b>不需要设任何环境变量</b>。本机验证时 Rebirth 的 profile <b>没有</b>填 AES key，Load 直接成功；FModel 把 archive 标成 disabled 或 Folders 里看不到
      <code>End/Content/Character</code>，先查 Directory Selector 加的是不是游戏根、profile 是不是 Final Fantasy VII Rebirth、mapping 是否选中并重开过 FModel。
      真需要 key 也只填在 FModel 自己的设置里，不写进仓库或本页。</p>
    <div class="note"><b>生成 .usmap（只做一次，要开游戏）：</b>① UE4SS v3.0.1 Beta 解压到游戏的 <code>End\Binaries\Win64\</code>，得到 <code>End\Binaries\Win64\ue4ss\</code>
      （<b>这几步会改游戏安装目录</b>：已经装过 UE4SS 的先把整个 <code>ue4ss\</code> 备份出来，②③ 会覆盖里面现有的 <code>UE4SS-settings.ini</code>
      和 <code>mods.txt</code>；mapping 出来以后把 <code>ue4ss\</code> 移走即可恢复原样，FModel 之后不需要它）；
      ② <code>ue4ss\UE4SS-settings.ini</code> 里所有以 <code>Hook</code> 开头的项（<code>HookProcessInternal</code>、<code>HookLoadMap</code>、<code>HookUObjectProcessEvent</code>……）逐个改成 <code>0</code>，
      <code>bUseUObjectArrayCache = false</code>，关掉文本 / GUI Console；
      ③ <code>ue4ss\Mods\mods.txt</code> 禁用其它 Mod，只留 <code>Keybinds : 1</code>；
      ④ 从 Steam 启动游戏到能响应键盘的界面，按 <code>Ctrl+Numpad6</code>（DumpUSMAP），等 <code>ue4ss\UE4SS.log</code> 出现 <code>Mappings Generation Completed Successfully!</code>；
      ⑤ 关游戏，把 <code>ue4ss\--&lt;sha&gt;.usmap</code>（本机是 <code>--c838a8ac.usmap</code>）复制到 <code>D:\ff7rebirth_exports\mappings\</code>——目录自己
      <code>New-Item -ItemType Directory</code>，<code>prepare_fmodel.ps1</code> 不建它；文件名随意，FModel 里选它即可，顺手 <code>Get-FileHash -Algorithm SHA256</code> 记个哈希。
      之后游戏就算因 UE4SS 注入报 Fatal Error 也不影响 FModel；游戏或 UE4SS 更新后重生成。</div>

    <h3>第零步 · 工作区与 FModel 配置（prepare_fmodel.ps1）</h3>
    <pre>Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # 只对当前窗口生效；新机器 Windows PowerShell 5.1 默认 Restricted 跑不了 .ps1
cd &lt;仓库&gt;\scripts\final                # 作者机是 E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1                  # 校验 .utoc/.ucas 配对，建 D:\ff7rebirth_exports 下的 fmodel_exports、blender、xps（不建 mappings）
.\prepare_fmodel.ps1 -LaunchFModel    # 顺手启动 FModel；路径不同加 -GameRoot / -WorkspaceRoot / -FModelExe</pre>
    <p>脚本只查目录、建目录，不解包。然后在 FModel 里手工配一次：Directory Selector 加<b>游戏根目录</b>（不是 <code>End\Content\Paks</code>）；profile 选
      <b>Final Fantasy VII Rebirth</b>（<code>GAME_FinalFantasy7Rebirth = 68812805</code>，别用通用 UE4.26 / Latest）；mapping 指向上面的 .usmap；Settings &gt; Models：
      Mesh Format = <b>ActorX (psk / pskx)</b>、LOD = First Level Only、PNG、Keep Directory Structure 开。
      输出目录不止一项：Settings 里 <b>Output / Raw Data / Properties / Textures / Models 几个 Directory 都</b>填 <code>D:\ff7rebirth_exports\fmodel_exports</code>
      （对应 <code>AppSettings.json</code> 的 <code>OutputDirectory</code> / <code>RawDataDirectory</code> / <code>PropertiesDirectory</code> / <code>TextureDirectory</code> / <code>ModelDirectory</code>）；
      第一步的批量脚本只会替你改写 <code>OutputDirectory</code> 和 <code>ModelDirectory</code>，JSON / PNG 的目录不改——指错了 .pskx 落在导出根、材质 JSON 和 PNG 却在别处，
      第二步每个变体都报「没有任何材质匹配到 Base Color 贴图」。
      换过 profile 或 mapping 要重开 FModel，日志里应同时出现 <code>GAME_FinalFantasy7Rebirth</code> 和 <code>Mappings pulled from</code>。配完保存并<b>正常关闭 FModel</b>，第一步要读盘上的设置文件。</p>

    <h3>第一步 · 从 IoStore 导出 ActorX（fmodel_export_player.py）</h3>
    <pre>pip install pywinauto
python fmodel_export_player.py                       # 整个 End/Content/Character/Player，约 1 h 45 min
python fmodel_export_player.py --folder &lt;子目录&gt;    # Character 下别的一级子目录，整棵子树一起导；只跑过 Player
python fmodel_export_player.py --restore             # 中途失败后还原 AppSettings 备份：用 .bak 覆盖当前 AppSettings.json 再把 .bak 删掉，
                                                     # 中间为别的游戏改的 FModel 设置会一并丢失，且无法撤销</pre>
    <p>跑之前先把第零步在 FModel 里配完并<b>正常关闭 FModel</b>：脚本直接 <code>json.load</code> <code>%APPDATA%\FModel\AppSettings.json</code>，FModel 从没启动过就没有这个文件（直接报错），
      设置没保存就会读到旧配置。脚本启动前会先 <code>taskkill /F</code> 掉所有已开着的 FModel.exe，别开着它干别的。
      <code>GAME</code> 必须和 Directory Selector 里加的那一行路径<b>完全一致</b>——FModel 的 profile（<code>UeVersion</code>）、AES key 这类每游戏设置是按这个字符串存在
      <code>AppSettings.json</code> 的 <code>PerDirectory</code> 里的，不一致就退回通用 profile，Load 后看不到 Rebirth 的包。
      游戏根 / FModel / 导出根是脚本顶部的 <code>GAME</code> / <code>FMODEL</code> / <code>EXPORT_ROOT</code> 常量，没有命令行参数，位置不同直接改。</p>
    <p>FModel 没有命令行，目录右键的 <b>Save Folder's Packages Models</b> 是唯一批量入口，脚本用 pywinauto 替你点：备份 <code>AppSettings.json</code> 为同目录的
      <code>AppSettings.json.before_rebirth_batch.bak</code>，改写游戏 / 输出目录、关新浏览器、强制 <code>MeshExportFormat=0</code>（ActorX）；启动 FModel → Load → 展开到目标目录 →
      <code>Shift+F10</code> 触发导出 → 3 分钟没新文件即算完 → 再强杀一次 FModel、还原设置（<code>--keep-settings</code> 则既不杀也不还原）。<b>跑的时候别碰键鼠。</b>
      <code>--folder</code> 的粒度是 <code>Character</code> 下的一级子目录，整棵子树一起导，没法只挑一个模型。</p>
    <p>产物在 <code>D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\&lt;变体&gt;\</code> 下的 <code>Model\PC????_??.pskx</code>（偶见 <code>.psk</code>）、
      <code>Material\*.json</code>、<code>Texture\*.png</code>；共享眼白 / 口腔在 <code>Character\Common\</code>。层级必须原样保留；<code>.pskx</code> 前 8 字节应为 <code>ACTRHEAD</code>，
      PowerShell 里这样看（应输出 <code>ACTRHEAD</code>），或者直接跑第二步的 <code>-ValidateOnly</code>，它先校验文件头：</p>
    <pre>[Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes('D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx'), 0, 8)</pre>
    <p><b>只要一个模型</b>就在 FModel 里手点：Folders → <code>Player/&lt;变体&gt;/Model</code> → 双击与目录编号同名的 <code>PC????_??.uasset</code>（不是 <code>_Condition</code> / Skeleton / BNM / KDI）
      → 3D Viewer 的 Outliner 里右键网格 → <b>Save Model</b>；再右键 <code>Material</code> → <b>Save Folder's Packages Properties (.json)</b>，右键 <code>Texture</code> → <b>Save Folder's Packages Textures</b>。</p>
    <p><b>找编号</b>：85 个主模型包一行一个在 <code>docs\ff7rebirth-player-model-files.txt</code>，FModel Folders 页可搜全名，已落盘的用 <code>-List</code> 看。
      命名 <code>PC&lt;角色&gt;_&lt;服装&gt;_&lt;名&gt;_&lt;变体&gt;</code>：0000 Cloud、0001 Barret、0002 Tifa、0003 Aerith、0004 RedXIII、0005 Yuffie、0006 Sonon、0007 CaitSith、
      0008 Debumoogle、0009 Zack、0010 Sephiroth、0011 Vincent、0012 Cid；<code>PC0099</code> 蛤蟆，<code>PC7xxx</code> 过场专用。</p>

    <h3>第二步 · 材质化（export_ff7rb_models.ps1）</h3>
    <pre>.\export_ff7rb_models.ps1 -List                              # 磁盘上的变体：MODEL / NO_MODEL
.\export_ff7rb_models.ps1                                    # 全部 MODEL 变体 -&gt; .blend，产物齐全的 SKIP；manifest 整份重写（见下方 note）
.\export_ff7rb_models.ps1 -Only PC0002_00                    # 单个：PC 编号前缀或变体全名；结果合并进已有 manifest
.\export_ff7rb_models.ps1 -Only PC0002_00,PC0003_00 -Format blend,fbx,glb -Force
.\export_ff7rb_models.ps1 -ValidateOnly                      # 只导入 + 校验，不写产物</pre>
    <div class="note"><b>全部导完后别再空跑一次全量。</b>不带 <code>-Only</code> 的全量跑会整份重写 <code>ff7rb_models_manifest.json</code>，产物齐全的变体写成 SKIP 条目，
      只有 variant / status / source / outputs / reason，不带网格 / 骨骼 / 顶点 / 材质统计；<code>collect_manifest.py</code> 只收 PASS——71 个 .blend 一个没动，画廊 manifest 却变成 0 条。
      补单个用 <code>-Only</code>（会合并进已有 manifest）；<b><code>-Force</code> 不是只刷新统计</b>——它会逐个重开无头 Blender
      把变体整个重导一遍并覆盖已有产物（全量就是 71 个 .blend、约 6.8 GB，fbx / glb 会先删后写），没有只重建 manifest 的开关。</div>
    <p>每个变体起一个无头 Blender 跑 <code>export_ff7rb_model_blender.py</code>：校验 <code>ACTRHEAD</code> → 导入 → 全部面 Smooth、关 Auto Smooth（修 PSK 三角反光）→
      在整个已导出 <code>Character</code> 树上按包路径建贴图索引 → 按材质 JSON 接 Base Color、Normal（DirectX 绿通道 1-G 重建）、Roughness / Metallic 或 ORM、Opacity，
      眼睛做巩膜 + 虹膜分层 → 贴图打包进文件 → 存 .blend。FBX / GLB 前做便携简化：眼球烘成单张 <code>textures\&lt;材质名&gt;_eye_baked.png</code>、法线预翻转成
      <code>textures\*_gl.png</code>，manifest 的 <code>simplified</code> 记下改动。</p>

    <h3>第三步 · 预览图（html\render_blend_preview.py）</h3>
    <pre>&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --python html\render_blend_preview.py -- D:\ff7rebirth_exports\materialized
&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --python html\render_blend_preview.py -- D:\ff7rebirth_exports\materialized\PC0002_00_Tifa_Standard.blend --force</pre>
    <p>材质化 worker 不出预览，这步单独补：自动取景（人物正面朝 +X）、太阳光 + 中性灰背景、EEVEE 渲 800×1100 到同目录 <code>&lt;变体&gt;_preview.png</code>。
      已有且比 blend 新的跳过，<code>--force</code> 重渲；<code>--suffix</code> 可换后缀，但画廊只认默认的 <code>_preview</code>。</p>

    <h3>参数表</h3>
    <table>
      <tr><th>参数</th><th>作用</th></tr>
      <tr><td><code>-Only &lt;ids&gt;</code></td><td>变体全名或 PC 编号前缀，逗号分隔；写 <code>PC0002</code> 带上该角色全部服装。只有带 <code>-Only</code> 时结果才合并进已有 manifest，不带就是整份重写</td></tr>
      <tr><td><code>-Format blend,fbx,glb</code></td><td>缺省只 blend；fbx / glb 各进子目录并做便携简化。XPS / PMX 未验证，不提供</td></tr>
      <tr><td><code>-Force</code></td><td>覆盖重做；不加时所请求格式的产物都在就 SKIP（SKIP 条目不带统计，全量跑会拿它覆盖 manifest）</td></tr>
      <tr><td><code>-ValidateOnly</code></td><td>只导入校验（含 <code>ACTRHEAD</code> 文件头），写独立快照 <code>ff7rb_models_manifest.validate.json</code></td></tr>
      <tr><td><code>-List</code></td><td>列磁盘上的变体和 MODEL / NO_MODEL；从没在 FModel 存过的不会出现</td></tr>
      <tr><td><code>-SourceRoot</code> / <code>-PlayerSubPath</code></td><td>FModel 导出根（默认 <code>D:\ff7rebirth_exports\fmodel_exports</code>）与 Player 相对路径（默认 <code>End\Content\Character\Player</code>）</td></tr>
      <tr><td><code>-OutputDir</code> / <code>-BlenderExe</code></td><td>产物目录（默认 <code>D:\ff7rebirth_exports\materialized</code>）与 Blender 路径</td></tr>
      <tr><td><code>fmodel_export_player.py --folder / --restore / --keep-settings</code></td><td>要整目录导出的 Character 一级子目录（默认 <code>Player</code>，整棵子树一起导）/ 只还原备份 / 跑完不杀 FModel、不还原设置</td></tr>
    </table>

    <h3>产物</h3>
    <pre>D:\ff7rebirth_exports\
├─ mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap    自己生成的 mapping（目录也是自己建的）
├─ fmodel_exports\End\Content\Character\
│  ├─ Player\&lt;变体&gt;\Model | Material | Texture\        FModel 原始导出（第一步）
│  ├─ Common\                                          共享眼白 / 口腔贴图
│  └─ Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk   Tifa 手套，手工 Save Model（见坑表）
├─ materialized\
│  ├─ &lt;变体&gt;.blend  &lt;变体&gt;_preview.png              贴图已打包（第二步）/ 第三步
│  ├─ fbx\  glb\  textures\*_gl.png  textures\*_eye_baked.png   只在要了便携格式时出现：预翻转法线 / 烘平的眼球
│  ├─ ff7rb_models_manifest.json                       每变体 status / 骨骼 / 顶点 / 材质 / missingBase / simplified / traceback
│  ├─ ff7rebirth_gallery_manifest.json                 画廊清单
│  └─ _gallery\thumbs\&lt;变体&gt;.jpg                    本页缩略图
└─ blender\  xps\                                      prepare_fmodel.ps1 建的空目录，给手工存档用</pre>

    <h3>容易踩的坑</h3>
    <table>
      <tr><th>症状</th><th>原因 → 处理</th></tr>
      <tr><td>FModel 日志 <code>Read incorrect amount of tangent bytes</code></td><td>Rebirth 每顶点切线 8 字节、CUE4Parse 按 16 字节读；glTF 保存另有一条独立错误（CUE4Parse 把整个 tangent Vector4 连手性 W 一起归一化，SharpGLTF 严格校验拒绝，报 <code>Invalid Tangent</code>），两处要分别修，所以只用 ActorX。<code>.pskx</code> 写出且头是 ACTRHEAD 就照用；13 个包网格没保住（见末尾）</td></tr>
      <tr><td>导出目录里只有 <code>.uemodel</code></td><td>Mesh Format 是 FModel 全局设置，被别的游戏切成了 UEFormat → 改回 ActorX 重导；脚本会强制 <code>MeshExportFormat=0</code></td></tr>
      <tr><td>脚本报「没找到菜单项 Save Folder's Packages Models」</td><td>「Preview New Explorer System」下目录没有右键菜单 → 脚本已写 <code>FeaturePreviewNewAssetExplorer=false</code>，手动跑要切回经典浏览器；跑的时候动了键鼠也会丢焦点</td></tr>
      <tr><td><code>-List</code> 里是 NO_MODEL</td><td>湿身 / 眼泪 / 全息这类只有贴图的变体本来就没网格，或 FModel 没写出 PSKX → 不算失败，全量跑会跳过</td></tr>
      <tr><td><code>-List</code> 是 MODEL，但每个变体都 FAIL「没有任何材质匹配到 Base Color 贴图」</td><td>FModel 的 Properties / Texture 目录没指到导出根，材质 JSON 和 PNG 落在别处（批量脚本只改 <code>OutputDirectory</code> / <code>ModelDirectory</code>）→ 第零步把几个 Directory 都改成 <code>D:\ff7rebirth_exports\fmodel_exports</code>，重导 Material / Texture</td></tr>
      <tr><td>worker 报 <code>PSK/PSKX 需要 io_scene_psk_psa</code></td><td>Blender 3.6 没装 5.0.6 → 用 3.6 本体装 ZIP（装在 4.x 里 3.6 看不到）；装了没勾启用也行，worker 会自己 <code>addon_enable</code>，但必须是 3.6 的 Add-ons 列表里有它</td></tr>
      <tr><td>画廊变空、<code>collect_manifest.py</code> 报 0 条</td><td>全部导完后又空跑了一次不带 <code>-Only</code> 的全量，manifest 被只有 SKIP 的结果整份重写 → 逐个 <code>-Only</code> 补，或 <code>-Force</code> 全量重跑（那是把 71 个 .blend 整个重导一遍，不是只刷统计）</td></tr>
      <tr><td>整模灰白 / 换装变体贴图全错</td><td>材质 JSON 引用的贴图在别的目录（换装复用 <code>PC0002_00</code> 的 atlas，眼白口腔在 <code>Common</code>）→ 把整个 Player（至少同角色 <code>_00</code>）和 Common 导全，别把 PNG 打平；残留缺图记在 manifest <code>missingBase</code>，发光 / <code>Common_Mouth_Light</code> 本就没 Base Color</td></tr>
      <tr><td>Tifa 没有手掌</td><td>皮手套是独立 Weapon SkeletalMesh <code>WE0002_00_Tifa_LeatherGlove</code>，按单个模型手点：FModel 搜 <code>WE0002_00_Tifa_LeatherGlove</code> → <code>Model</code> → 双击 <code>WE0002_00.uasset</code>（预览应是左右手套）→ Outliner 右键 → <b>Save Model</b>，再对同目录 <code>Material</code> / <code>Texture</code> 分别 Save Folder's Packages Properties (.json) / Textures；落盘的是 <code>Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk</code>（<code>.psk</code> 不是 <code>.pskx</code>，正常）。然后在 FF7RB 面板「导入并绑定同骨架配件」；批量脚本不做这步。<code>--folder Weapon</code> 会把整个 Weapon 树全导，没试过，别为一副手套用它</td></tr>
    </table>

    <h3>并行与耗时</h3>
    <p>第一步只能单线：一个 FModel 实例、一个键盘焦点，整个 Player（85 个主模型包）约 <b>1 小时 45 分</b>，每包 30–60 s，多数时间在写贴图，期间机器不能干别的 GUI 活。
      第二步<b>没有分片 / lane 参数</b>，manifest 只有一份，两个进程同时写同一个 <code>-OutputDir</code> 会互相覆盖，老实串行；单个 .blend 11–183 MB，全量 71 个 .blend 共 6.8 GB（<code>materialized</code> 目录连预览图约 7.3 GB）。</p>

    <h3>重新生成本页</h3>
    <pre>cd &lt;仓库根&gt;                                             # 两脚本不依赖当前目录，从哪里跑都行
python scripts\final\html_rebirth\collect_manifest.py      # 可选位置参数：[materialized 目录] [输出 manifest]
python scripts\final\html_rebirth\make_gallery.py          # --source-root / --manifest / --out / --thumb-dir / --force</pre>
    <p><code>collect_manifest.py</code> 不开 Blender：读 <code>ff7rb_models_manifest.json</code>，只留 PASS 且 blend 真在的条目，补 <code>_preview.png</code> 和告警，写
      <code>ff7rebirth_gallery_manifest.json</code>；<code>make_gallery.py</code> 把预览缩成 720 px JPEG 放 <code>materialized\_gallery\thumbs\</code>，重写
      <code>scripts\final\html_rebirth\index.html</code>（固定在脚本旁，<code>--out</code> 可改）。两脚本的默认路径都是绝对的 <code>D:\ff7rebirth_exports\materialized</code>，
      导出根不同就给位置参数 / <code>--source-root</code>。图片和 blend 链接全是 <code>file://</code> 本机路径；<b>缩略图和两份 manifest 都留在导出根下，刻意不进仓库</b>，换机器把三步重跑一遍即可。</p>

    <h3>没有出现在本页的变体</h3>
    <p>Player 虚拟目录 109 项里 24 项没有主模型包（<code>Model\PC????_??.uasset</code>），多是湿身、眼泪、全息这类只有材质贴图的变体，
      血迹和脏污版有自己的网格、不在这 24 项里；85 个主模型包中 FModel 写出 72 个 PSKX、材质化成功 71 个。缺的 14 个：</p>
    <ul>
      <li><b>13 个 FModel 读 SkeletalMesh 失败且网格没保住</b>：Cloud 血迹版 <code>PC0000_13 / 14 / 15 / 25 CutBrood*</code>、<code>PC0003_18_Aerith_NoRibbonBlood</code>、<code>PC0006_91_Sonon_BloodPSBL00910</code>、<code>PC0099_00_Toad_Standard</code>，以及 6 个过场版 <code>PC7000_00 / 7001_00 / 7002_00 / 7005_00 / 7008_00 / 7010_00 *_StandardCFEnd2</code>。要等 CUE4Parse 按 tangent itemSize 选 8 / 16 字节的 reader 修复，本仓库不改 FModel。</li>
      <li><b>1 个材质化 FAIL</b>：<code>PC0004_06_RedXIII_OnceHologram</code>，原因在 manifest 的 <code>error</code> / <code>traceback</code> 里。</li>
    </ul>
    <div class="note"><b>官方没有 nude。</b>真正没有独立网格的是那 24 个只有材质 / 贴图的变体：湿身（<code>*Wet</code>）、眼泪（<code>*CutTear*</code>）、
      多数全息（<code>*Hologram</code>），外加 <code>PC0006_01_Sonon_Ghost</code>、<code>PC0012_01_Cid_NoAmbientOcclusion</code> 等，它们复用同编号
      <code>_00</code> 的网格，本页不单列。<b>血迹和脏污不算在内</b>：5 个 <code>*Dirty*</code>（<code>PC0000_12</code> / <code>PC0000_19</code> /
      <code>PC0003_04</code> / <code>PC0004_08</code> / <code>PC0009_02</code>）有自己的网格，本页就有；6 个血迹版和
      <code>PC0004_06_RedXIII_OnceHologram</code> 也有网格，只是导出 / 材质化失败（见上）。</div>
  </section>
"""

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

{appendix}
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
