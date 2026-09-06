"""把 FF7 Remake INTERGRADE 的导出产物做成一页可浏览的 HTML 画廊。

读 ``ff7remake_models_manifest.json``（由 collect_manifest.py 从各包的报告 JSON 汇总），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\ff7remake_exports\\player --force
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
KIND_LABELS = {"official": "主服装", "variant": "泪痕/血迹贴片", "toad": "蛤蟆形态"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\ff7remake_exports\player",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\ff7remake_models_manifest.json）")
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
    kinds = [k for k in ("official", "variant", "toad") if any(m["kind"] == k for m in models)]
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
    <p>脚本都在 <code>scripts\final\</code>，必须在<b>装有游戏的那台机器</b>上跑（直接读 Steam 目录下的 pak）。
      两段流程：① Remake 专用 UE Viewer 按包路径解 pak，得到 PSKX + PNG + .mat；② Blender 3.6 无头导入、按 .mat 接贴图、渲预览、写报告。
      <code>export_ff7remake_models.ps1</code> 把两段串成一条命令；背景见 <code>docs\final-fantasy-vii-remake-extraction.md</code>。
      本页所有 <code>E:\code\othercode\ripper_tpose</code> 都是作者的 clone 位置，换成你自己 clone 仓库的目录；只有「相对于仓库根」这一点不能变
      （批量脚本按自己所在目录往上两层找 <code>docs\ff7remake-player-model-files.txt</code>，也可以用 <code>-ListFile</code> 显式指过去）。
      下面的 PowerShell 命令除「重新生成本页」外都在 <code>scripts\final</code> 目录下执行；<code>$root</code> / <code>$pkg</code> / <code>$glove</code> / <code>$out</code> /
      <code>$umodel</code> / <code>$paks</code> / <code>$rawRoot</code> 是同一会话里定义的变量。换窗口要重新执行第一步的 <code>Set-ExecutionPolicy</code> 和
      <code>cd</code>，并重新赋值变量（<code>-SkipExtract</code> 的窗口不需要 key）。</p>

    <h3>前提 · 机器、工具与路径</h3>
    <table>
      <tr><th>项目</th><th>要求 / 脚本默认值</th></tr>
      <tr><td>游戏</td><td>Steam 版 FF7 REMAKE INTERGRADE，默认 <code>D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE</code>
        （<code>ff7remake_export.ps1 -GameRoot</code>）。导出前<b>关掉游戏</b>，脚本查到 <code>ff7remake</code> 进程会直接退出</td></tr>
      <tr><td>UE Viewer</td><td>Intergrade 专用构建 <code>umodel_FFVII_intergrade_v8.exe</code>——UE Viewer 官方论坛 Remake 兼容帖
        <code>https://www.gildor.org/smf/index.php?topic=6925.120</code> 里的 v8 专用构建（通用命令行说明见
        <code>https://www.gildor.org/en/projects/umodel</code>）。自己建 <code>E:\tools\umodel_ff7remake\</code>，把压缩包<b>整个</b>解压进去
        （作者目录里 exe 旁边还有 <code>SDL2_64.dll</code>，要一起放）；exe 名字若不是 <code>umodel_FFVII_intergrade_v8.exe</code> 就改成这个名——
        这是 <code>ff7remake_export.ps1 -UmodelExe</code> 的默认值，批量脚本没有 <code>-UmodelExe</code>，改名比走下面「路径不在默认位置时」省事。
        找不到时脚本报 <code>UE Viewer executable not found: …</code>。脚本以 <code>-game=ue4.18</code> 调用。普通 umodel / FModel 导不出 Remake 网格</td></tr>
      <tr><td>Blender</td><td>3.6.15，<code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code>）。
        从 blender.org 的 3.6 LTS 下载页取 windows-x64 zip 解压即得这个目录名；用安装器装的在
        <code>C:\Program Files\Blender Foundation\Blender 3.6\blender.exe</code>，批量给 <code>-BlenderExe</code>，本页「拆开跑」「手套」「重新生成本页」三处的
        <code>&amp; 'D:\Program Files\...'</code> 也要跟着改。要 3.6，不要 4.x（<code>validate_ff7remake_model.py</code> / <code>render_blend_preview.py</code>
        写死 <code>BLENDER_EEVEE</code>，4.2+ 的引擎枚举已改名；docs 里的导入器 5.0.6 也只在 3.6 验证过）。
        先在 <code>-BlenderExe</code> 指向的那份 Blender 3.6 里装 <b>io_scene_psk_psa 5.0.6</b>：从
        <code>https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6</code> 下 ZIP，Edit &gt; Preferences &gt; Add-ons &gt; Install… 选 ZIP 并勾选启用，
        确认 File &gt; Import 里出现 <b>Unreal PSK (.psk/.pskx)</b>。无头启动不加载用户插件，批量脚本用 <code>enable_psk_addon.py</code> 前置启用，但装要自己装；
        装错版本的 Blender（例如同时有 4.x）就是 FAIL 的第一嫌疑</td></tr>
      <tr><td>Python 3</td><td>只有画廊要。装 Python 3（python.org 安装包，勾 Add to PATH；新装 Win11 直接敲 <code>python</code> 会跳微软商店，那不是装好了），
        然后 <code>python -m pip install pillow</code>（保证装进你敲 <code>python</code> 时用的那个解释器）。<code>collect_manifest.py</code> 只用标准库，
        <code>make_gallery.py</code> 用 Pillow 做缩略图；导出根不是默认值时分别用位置参数 / <code>--source-root</code> 指过去</td></tr>
      <tr><td>AES key</td><td>pak 加密。自己合法取得后放环境变量 <code>FF7REMAKE_AES_KEY</code>（仓库、脚本、本页都没有）。
        脚本把它写进随机临时文件以 <code>-aes=@file</code> 交给 umodel，跑完即删</td></tr>
      <tr><td>导出根</td><td><code>D:\ff7remake_exports\player</code>（<code>-OutputRoot</code>）。36 个包共用一个根，别放进游戏目录</td></tr>
    </table>
    <div class="note"><b>路径不在默认位置时：</b>批量脚本 <code>export_ff7remake_models.ps1</code> 没有 <code>-GameRoot</code> / <code>-UmodelExe</code>，只能改
      <code>-OutputRoot</code> / <code>-BlenderExe</code>。游戏或 umodel 不在默认路径，设好 key（第一步）后先用提取脚本自己指路径把 36 个包一次提到同一个根
      （清单文件每行一个包路径、无注释，可直接喂给 <code>-Package</code>；不加 <code>-NoOverwrite</code> 时 umodel 会覆盖根下已有的同名提取物），再只做材质化：
      <pre>.\ff7remake_export.ps1 -GameRoot 'C:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE' `
  -UmodelExe 'C:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe' `
  -OutputRoot D:\ff7remake_exports\player `
  -Package (Get-Content ..\..\docs\ff7remake-player-model-files.txt)     # 相对路径以 scripts\final 为准
.\export_ff7remake_models.ps1 -SkipExtract      # 之后所有批量命令都带 -SkipExtract</pre>
      没有 D: 盘的把 <code>-OutputRoot</code>（两个脚本都要给）以及后面 collect_manifest.py 的位置参数、make_gallery.py 的 <code>--source-root</code>、
      render_blend_preview.py 的 <code>_blends</code> 路径，以及「手套」一节的 <code>$rawRoot</code> 和
      <code>-out=D:\ff7remake_exports\umodel_glove_raw</code>，全部换成自己的根。</div>

    <h3>第一步 · 设 key，看清单</h3>
    <pre>Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # 只对当前窗口生效，新机器 Windows PowerShell 5.1 默认 Restricted 跑不了 .ps1
cd E:\code\othercode\ripper_tpose\scripts\final     # 即 &lt;仓库根&gt;\scripts\final，换成你自己 clone 的位置
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'   # 只在当前会话；脚本只临时写一个随机 temp 文件给 umodel，跑完即删

.\export_ff7remake_models.ps1 -List                # 36 个包：folder / id / 完整包路径
.\export_ff7remake_models.ps1 -List -Only PC0002   # 只看 Tifa 系</pre>
    <p>Windows PowerShell 5.1 和 pwsh 7 的 <code>Set-ExecutionPolicy</code> 用法相同；策略只改当前进程，不动系统设置。
      清单是 <code>docs\ff7remake-player-model-files.txt</code>，一行一个包路径，形如
      <code>End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset</code>；带角色名的对照表在
      <code>docs\ff7remake-player-model-inventory.md</code>。<code>PC0000</code>~<code>PC0006</code> = Cloud / Barret / Tifa / Aerith / Red XIII / Yuffie / Sonon，
      <code>_00</code>~<code>_05</code> 服装，<code>_90</code>/<code>_91</code> 过场贴片，<code>PC0099_xx</code> 蛤蟆。</p>
    <p>清单外的包（武器 <code>WE*</code>、NPC）要自己找完整包路径。不装 FModel 也能列：用同一个 umodel 的 <code>-list</code>
      （docs 的 Mod 教程用它列过 Mod-only 挂载里的 14 个包；对整个游戏的 pak 集没验证过，包多时很慢、也可能中途报错），
      对加密 pak 加上和「手套」一节相同的 <code>-aes=@临时文件</code>，并先把包名收窄到角色目录、结果重定向到文件：</p>
    <pre>$umodel  = 'E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe'
$paks    = 'D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\End\Content\Paks'
$keyFile = Join-Path ([IO.Path]::GetTempPath()) ("ff7remake-aes-" + [guid]::NewGuid() + ".txt")
try {
  [IO.File]::WriteAllText($keyFile, $env:FF7REMAKE_AES_KEY)
  &amp; $umodel '-list' '-game=ue4.18' "-aes=@$keyFile" "-path=$paks" 'End/Content/GameContents/Character/Weapon/*' &gt; "$env:TEMP\ff7r-weapon-list.txt"
} finally { Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue }</pre>
    <p>收窄的通配符匹配不到时再退回 <code>'*'</code>（NPC 目录同理换成它自己的路径），同样重定向到文件再搜——整个游戏的列表很长，这一步可能要等很久。
      输出里 <code>/End/Content/GameContents/Character/…/Model/XXXX.uasset</code> 去掉开头的 <code>/</code> 就是 <code>-Package</code> 要的字符串。GUI 路线是 FModel（<code>https://github.com/4sval/FModel</code>，README 默认放
      <code>E:\tools\FModel\FModel.exe</code>，首次启动按它的 Getting Started 页 <code>https://github.com/4sval/FModel/wiki/Getting-Started</code> 配置）：
      Directory Selector 里加游戏根目录，在它的 Settings 里填自己的 AES key（只填在 FModel 设置里，不进仓库），不需要 .usmap 就能展开
      <code>End/Content/GameContents/Character/...</code> 目录树抄路径——FModel 双击模型会解析失败是正常的（缺 Remake 的 usmap），网格一律交给专用 umodel。
      路径格式照清单：<code>End/Content/GameContents/Character/&lt;Player|Weapon&gt;/&lt;目录名&gt;/Model/&lt;编号&gt;.uasset</code>，抄好后走「拆开跑」。</p>

    <h3>第二步 · 一条命令：提取 + 材质化</h3>
    <pre>.\export_ff7remake_models.ps1 -Only PC0002_00        # 单个：Tifa 标准装，先拿它验证环境
.\export_ff7remake_models.ps1                        # 全部 36 个；已有 .blend 的 SKIP
.\export_ff7remake_models.ps1 -Only PC0002,PC0003    # Tifa 全系（含 _90/_91）+ Aerith 全系（PC0003 没有 _90/_91）
.\export_ff7remake_models.ps1 -SkipExtract -Force    # 提取物已在，只重做材质化；会覆盖 _blends\ 里已有的 .blend/.json/_preview.png/.log
Remove-Item Env:FF7REMAKE_AES_KEY                    # 做完清掉</pre>
    <p>脚本先把所有还没有 <code>Model\&lt;id&gt;.psk*</code> 的包一次交给 <code>ff7remake_export.ps1</code>（隔离 <code>~mods</code>、关动画、写临时 key），
      再逐包起无头 Blender。每包打印 <code>OK &lt;包目录名&gt; (xx MB, ns)</code>，行尾 <code>缺贴图 n</code> 是报告里的缺图数；
      <code>FAIL</code> 时回显 <code>_blends\&lt;包目录名&gt;.log</code> 最后 8 行。</p>

    <h3>拆开跑 · ff7remake_export.ps1 + validate_ff7remake_model.py</h3>
    <p>要用 <code>-AllLods</code>、<code>-IncludeMods</code>、改 umodel / 游戏路径，或导清单外的包时两段自己跑——批量脚本只透传
      <code>-Package</code>、<code>-OutputRoot</code>、<code>-AesKey</code>。<code>-OutputRoot</code> 要显式给成同一个根（单独用时缺省是
      <code>D:\ff7remake_exports\umodel_original</code>）；之后清单内的包用 <code>-SkipExtract</code> 接材质化；清单外的包（武器、NPC）批量脚本不会碰，
      按下面的 Blender 命令手动材质化——但 <code>--output</code> 要写到 <code>_blends\</code> 以外（例如 <code>&lt;导出根&gt;\_extra\</code>）：<code>collect_manifest.py</code>
      会把 <code>_blends\</code> 里的每个 .blend 都当一个 Player 包收进画廊，<code>WE*</code> / NPC 的名字不合 <code>PCxxxx_yy_角色_变体</code> 规律，
      会在角色下拉和「覆盖角色」统计里多出一条垃圾条目。</p>
    <pre>.\ff7remake_export.ps1 -OutputRoot D:\ff7remake_exports\player -Package @(
  'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset',
  'End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset'
)

$root = 'D:\ff7remake_exports\player'
$pkg  = "$root\GameContents\Character\Player\PC0002_00_Tifa_Standard"
# 注意：直接调 Blender 没有批量脚本「.blend 在就 SKIP」那层保护，--output/--render/--report 会无条件覆盖 _blends\ 下同名的 .blend/_preview.png/.json；要保留旧产物就换个输出目录
&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background `
  --python .\enable_psk_addon.py --python .\validate_ff7remake_model.py -- `
  --model "$pkg\Model\PC0002_00.pskx" --asset-root "$root\GameContents" `
  --material-dir "$pkg\Material" --output "$root\_blends\PC0002_00_Tifa_Standard.blend" `
  --render "$root\_blends\PC0002_00_Tifa_Standard_preview.png" `
  --report "$root\_blends\PC0002_00_Tifa_Standard.json"</pre>
    <p>直接从 pak 提取手套包在本机文档里<b>未单独验证</b>；上面那条跑完 <code>Weapon\...\Model\</code> 下没出 <code>WE0002_00.psk*</code>，
      就走「手套」一节的两步法：同一个 umodel 先 <code>-save</code> 存出原始包，再把保存根当 <code>-path</code> 只导主网格包（不用装 FModel）。</p>
    <p>手敲 umodel 时把 <code>-game=ue4.18</code> 当数组里一个完整字符串传，别拼进动态命令串，PowerShell 会把版本号拆开。</p>

    <h3>参数表</h3>
    <table>
      <tr><th>export_ff7remake_models.ps1</th><th>作用</th></tr>
      <tr><td><code>-Only &lt;子串,…&gt;</code></td><td>按包目录名子串筛（不分大小写）：<code>PC0002</code> 整个 Tifa 系，<code>PC0002_00</code> 一套；写 <code>Tifa</code> 会连 <code>PC0099_03_Toad_Tifa</code> 带上</td></tr>
      <tr><td><code>-List</code></td><td>只打印匹配到的包</td></tr>
      <tr><td><code>-SkipExtract</code></td><td>不调 umodel，只材质化（不需要 key）</td></tr>
      <tr><td><code>-Force</code></td><td>提取物、.blend 都重做；不加时 <code>Model\&lt;id&gt;.psk*</code> 在就不重提，<code>.blend</code> 在就 SKIP。加了就无条件覆盖 <code>_blends\</code> 里已有的 .blend/.json/_preview.png/.log</td></tr>
      <tr><td><code>-NoPreview</code></td><td>不渲 <code>_preview.png</code>（渲染发生在保存 .blend 之前，没有 GPU 的会话靠它先出 .blend），之后可用 <code>render_blend_preview.py</code> 补</td></tr>
      <tr><td><code>-Lane n -Lanes N</code></td><td>材质化只做第 n 路（0 起）；提取段不分片</td></tr>
      <tr><td><code>-OutputRoot</code> / <code>-BlenderExe</code> / <code>-AesKey</code> / <code>-ListFile</code></td><td>路径与 key 覆盖；<code>-AesKey</code> 缺省读 <code>$env:FF7REMAKE_AES_KEY</code>；换清单也只认 <code>Character\Player\</code> 下的包</td></tr>
    </table>
    <table>
      <tr><th>ff7remake_export.ps1</th><th>作用</th></tr>
      <tr><td><code>-Package &lt;路径[]&gt;</code></td><td>必填，一个或多个完整包路径；别传整个 <code>Player</code> 目录，会带出几十 GB 动画与依赖</td></tr>
      <tr><td><code>-GameRoot</code> / <code>-OutputRoot</code> / <code>-UmodelExe</code></td><td>游戏、输出、umodel 路径覆盖</td></tr>
      <tr><td><code>-AesKey</code></td><td>缺省读 <code>$env:FF7REMAKE_AES_KEY</code>；两者都没有就抛 <code>AES key is required. Set FF7REMAKE_AES_KEY or pass -AesKey.</code></td></tr>
      <tr><td><code>-WithAnimations</code> / <code>-AllLods</code> / <code>-AllWeights</code></td><td>缺省 <code>-noanim</code>（主角动画集是几十 GB PSA）；全部 LOD；保留全部骨骼影响</td></tr>
      <tr><td><code>-IncludeMods</code></td><td>不隔离 <code>~mods</code>；缺省把 <code>~mods\*.pak</code> 临时改名为 <code>*.pak.codex-disabled</code>，finally 里恢复。
        没装过 mod 就没有 <code>~mods</code> 目录，这一步什么都不做；有 mod 但改名报 <code>Access … is denied</code> 时用管理员 PowerShell 再跑，
        或先把 mod 手动挪出 <code>~mods</code>（原版导出不要用 <code>-IncludeMods</code> 绕过）</td></tr>
      <tr><td><code>-NoOverwrite</code></td><td>跳过已存在的导出文件；不加时 umodel 覆盖同名文件</td></tr>
    </table>

    <h3>产物布局</h3>
    <pre>D:\ff7remake_exports\player\
├─ GameContents\Character\Player\&lt;包目录名&gt;\Model\PCxxxx_yy.pskx   umodel 提取物
│                                            \Texture\*.png  \Material\*.mat
├─ GameContents\...                        Common 眼/口共享贴图，只提取一次
├─ _blends\&lt;包目录名&gt;.blend                贴图外链到上面的 GameContents\，不打包
├─ _blends\&lt;包目录名&gt;_preview.png / .json / .log   预览、报告、Blender 日志
├─ _gloves\PC0002_00_Tifa_Standard_gloves.*  合并手套后的 .blend / .png / .json（见「手套」）
├─ ff7remake_models_manifest.json          collect_manifest.py 汇总
└─ _gallery\thumbs\&lt;包目录名&gt;.jpg          make_gallery.py 缩略图</pre>
    <p>umodel 输出时去掉包路径的 <code>End/Content/</code> 前缀，所以 <code>.../Character/Weapon/...</code> 手套包也直接落在
      <code>&lt;根&gt;\GameContents\Character\Weapon\...</code>；<code>.pskx</code> 前 8 字节应为 <code>ACTRHEAD</code>。</p>
    <p>报告 JSON 记 <code>meshes</code>、<code>vertices</code>、<code>bones</code>、<code>material_slots</code>、<code>uv_layers</code>、每个材质接的三张图和
      <code>missing_preview_textures</code>。材质只是预览近似：Diffuse → Base Color、Normal 反转 G 通道进 Normal Map、被引用的 <code>_A</code> 接 Alpha
      （材质名含 hair/eyelash/eyebrow 且没有 <code>_A</code> 时用 Diffuse 自带的 Alpha 通道）；
      <code>_M</code>/<code>_B</code>/<code>_O</code> 打包遮罩留在 Texture 里不接。</p>

    <h3>容易踩的坑</h3>
    <div class="note"><b>.blend 不带贴图。</b>贴图外链到同根 <code>GameContents\</code>，单独拷走 <code>_blends\</code> 或换机器就全白；要搬整根搬，或在 Blender 里 File &gt; External Data &gt; Pack Resources。</div>
    <table>
      <tr><th>症状</th><th>原因</th><th>处理</th></tr>
      <tr><td><code>AES key is required. Set FF7REMAKE_AES_KEY or pass -AesKey.</code></td><td>当前会话没设变量</td><td>第一步的 <code>Read-Host</code></td></tr>
      <tr><td><code>FINAL FANTASY VII REMAKE is running</code></td><td>游戏没关</td><td>关游戏再跑</td></tr>
      <tr><td><code>Temporary disabled path already exists: …codex-disabled</code></td><td>上次跑到一半被杀，<code>~mods</code> 里留了改名文件</td><td>手动把 <code>*.pak.codex-disabled</code> 改回 <code>.pak</code>，同时删掉 <code>%TEMP%\ff7remake-aes-*.txt</code>（脚本写 key 的临时文件，正常结束会自删，被杀就留下明文 key）；每次跑完顺手看一眼这两处</td></tr>
      <tr><td><code>No PSK importer is registered; enable io_scene_psk_psa 5.0.6</code></td><td>那份 Blender 没装插件（脚本只负责启用）</td><td>先看 <code>_blends\&lt;包目录名&gt;.log</code> 开头一行 <code>[enable_psk] io_scene_psk_psa enabled=True</code>；是 <code>enabled=False</code> 或 <code>error:</code> 就是 <code>-BlenderExe</code> 指向的那份 Blender 没装到插件，按前提表在 GUI 装一次</td></tr>
      <tr><td>每个包都 FAIL，log 尾部是 render / OpenGL / GPU 相关错误而不是 PSK 错误</td><td>预览渲染在保存 .blend 之前执行（<code>validate_ff7remake_model.py</code> 先 <code>create_preview_scene</code> 再 <code>save_as_mainfile</code>），渲不了就没有 .blend</td><td>加 <code>-NoPreview</code> 先出 .blend，有 GPU 的机器再用 <code>render_blend_preview.py</code> 补图</td></tr>
      <tr><td>衣服、袖套、丝袜整片透明</td><td>旧版脚本按名字把 <code>BodyA_A</code> 当 Alpha，这张遮罩 99% 全黑，只有耳环材质真用它</td><td>仓库 2026-09-05 起（commit e2f8cb6）的 <code>validate_ff7remake_model.py</code> 已按 <code>.mat</code> 的 Other[n] 引用判断；若用旧版脚本导过，拉新代码后 <code>-SkipExtract -Force</code> 重做材质化即可（会覆盖 <code>_blends\</code> 里已有的产物）</td></tr>
      <tr><td>Yuffie 莫古利装缺 24/34 张贴图</td><td>变体包直接引用 <code>PC0005_00</code> 基础包的材质，自己 <code>Material\</code> 没那些 .mat</td><td>同一次修复：本目录找不到就搜整个导出根——所以 36 个包必须共用一个根</td></tr>
      <tr><td>Tifa 标准装手掌悬空、手指和手套分离</td><td>皮手套是独立武器网格 <code>WE0002_00</code>，主体 PSK 本来就没有</td><td>见「手套」；不是权重错，别手动挪顶点</td></tr>
      <tr><td>导出的是 mod / 想要 mod</td><td>加了 <code>-IncludeMods</code>；缺省隔离</td><td>原版重导到新目录。mod 主体 v8 会报 <code>LODModels.Num() == LODInfo.Num()</code>，走 <code>docs\ff7remake-mod-manual-export.md</code> 的 -save + glTF 路线</td></tr>
    </table>

    <h3>并行与耗时</h3>
    <p>实测 umodel 提取 36 个包约 3 分钟，材质化每包 2–8 s（36 包合计约 1–5 分钟），一般不必并行。<code>-Lane/-Lanes</code> 只切材质化段，
      提取段每个进程都会做，两份 umodel 同时跑会撞 <code>~mods</code> 改名——先让一路把提取跑完，其余路 <code>-SkipExtract</code>。
      窗口 2/3 是新的 PowerShell 进程，第一步的执行策略和 <code>cd</code> 都不带过去，要重做（不需要 key）：</p>
    <pre>.\export_ff7remake_models.ps1 -Lane 0 -Lanes 3                # 窗口 1：先提取全部，再做第 0 路
# 等窗口 1 打出 "Export complete"（提取物已齐全时打的是「提取物已齐全，跳过 umodel」）后再开窗口 2/3，每个新窗口先：
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd E:\code\othercode\ripper_tpose\scripts\final               # &lt;仓库根&gt;\scripts\final
.\export_ff7remake_models.ps1 -SkipExtract -Lane 1 -Lanes 3   # 窗口 2
.\export_ff7remake_models.ps1 -SkipExtract -Lane 2 -Lanes 3   # 窗口 3</pre>

    <h3>Tifa 标准装的手套</h3>
    <p>已验证：<code>PC0002_00</code> 标准装需要合并手套，<code>PC0002_01</code> PurpleDress 主网格自带手掌不需要；ChinaDress / WutaiDress / NoGlove 未单独核对，以预览图为准。
      手套包 <code>WE0002_00_Tifa_LeatherGlove</code> 不在清单里。先花半分钟试直接提取：按「拆开跑」把它和主体一起交给
      <code>ff7remake_export.ps1 -Package</code>，提到同一个根。本机文档里这条路<b>未单独验证</b>（作者导出根的 <code>Character\</code> 下只有
      Common / Player / Summon，没有 Weapon），umodel 报找不到该包或 <code>Weapon\...\Model\</code> 下没出 .psk 时，走下面第一段：
      用同一个 umodel 先 <code>-save</code> 把原始包从加密 pak 存出来（<code>docs\ff7remake-mod-manual-export.md</code> §10.1），再把保存根当
      loose-package 的 <code>-path</code> 只 <code>-export</code> 主网格包（<code>docs\final-fantasy-vii-remake-extraction.md</code>「从 FModel 原始包转成 ActorX」）。
      <code>-save</code> 只取原始包，不进网格导出代码。<code>-save</code> 段要像 docs 的 FModel 变体一样，把 Model / Material / Texture 三个子目录的原始包都存出来
      （extraction 文档的第二段就是从这样一个保存根跑的；下面的通配符若匹配不到，就把三个子目录各传一次）；只存 Model 包，第二段导不出
      <code>WE0002_00_Body_C.png</code> / <code>_N.png</code>，<code>fix_ff7remake_tifa_gloves.py</code> 必然 FileNotFoundError。
      然后用 <code>fix_ff7remake_tifa_gloves.py</code> 复用 PSK 自带权重改绑主体骨架（校验骨名与 rest 矩阵、删重复骨架、转一根骨验证形变；<b>不算</b>自动权重）。
      <code>--textures</code> 目录里必须有 <code>WE0002_00_Body_C.png</code> 和 <code>WE0002_00_Body_N.png</code>，脚本缺一即报 FileNotFoundError。</p>
    <pre># 只在直接提取拿不到手套 .psk 时用：-save 原始包 -&gt; 从原始包根 -export（两段分别抄自 docs）
$umodel  = 'E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe'
$paks    = 'D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\End\Content\Paks'
$rawRoot = 'D:\ff7remake_exports\fmodel_raw'          # 原始包保存根：-save 的 -out；改用 FModel 保存时就是 FModel 的保存根
$glovePackage = 'End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset'
$keyFile = Join-Path ([IO.Path]::GetTempPath()) ("ff7remake-aes-" + [guid]::NewGuid() + ".txt")
try {
  [IO.File]::WriteAllText($keyFile, $env:FF7REMAKE_AES_KEY)
  &amp; $umodel '-save' '-game=ue4.18' "-aes=@$keyFile" "-path=$paks" "-out=$rawRoot" 'End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/*'
  if ($LASTEXITCODE -ne 0) { throw 'Saving glove package failed' }
} finally { Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue }
# 存出来的应是 $rawRoot\End\Content\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\ 下的 Model / Material / Texture 三个子目录
$gloveRaw = "$rawRoot\End\Content\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove"
if (-not (Test-Path "$gloveRaw\Texture")) { throw '只存到 Model：-save 要覆盖整个包目录，否则下一段 -export 出不了 WE0002_00_Body_C/_N.png' }

$umodelArgs = @(
  '-export', '-png', '-game=ue4.18', '-noanim',
  "-path=$rawRoot",
  '-out=D:\ff7remake_exports\umodel_glove_raw',
  $glovePackage
)
&amp; $umodel @umodelArgs
# 之后下面改成 $glove = 'D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove'</pre>
    <p>不想手敲 <code>-save</code> 也可以用 FModel：搜 <code>WE0002_00_Tifa_LeatherGlove</code>，保持 <code>End/Content/...</code> 相对目录保存
      Model / Material / Texture 里目标包的原始 <code>.uasset/.uexp</code>，含 <code>End\Content\…</code> 的那一层就是上面的 <code>$rawRoot</code>，
      跳过 <code>-save</code> 段直接跑 <code>-export</code> 段。手敲 umodel 不经过 <code>ff7remake_export.ps1</code>，不会隔离 <code>~mods</code>，装了 mod 的先手动挪走。</p>
    <pre># 在 scripts\final 下；换过窗口就重新赋值
$root  = 'D:\ff7remake_exports\player'
$glove = "$root\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove"
$out   = "$root\_gloves"
&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background "$root\_blends\PC0002_00_Tifa_Standard.blend" `
  --python .\enable_psk_addon.py --python .\fix_ff7remake_tifa_gloves.py -- `
  --glove "$glove\Model\WE0002_00.psk" --textures "$glove\Texture" `
  --output "$out\PC0002_00_Tifa_Standard_gloves.blend" `
  --render "$out\PC0002_00_Tifa_Standard_gloves.png" `
  --closeup "$out\PC0002_00_Tifa_Standard_gloves_closeup.png" `
  --report "$out\PC0002_00_Tifa_Standard_gloves.json"</pre>
    <p>不要写进 <code>_blends\</code>：<code>collect_manifest.py</code> 会把那里的每个 .blend 当一个包收进画廊，手套报告没有 <code>meshes/vertices/armatures</code> 字段，
      会出一张 0 顶点、无预览的坏卡片。本机验证 13,110 顶点、30 根权重骨、缺失骨 0、最坏 rest 矩阵差 6.56e-7。
      手套提取出来是 <code>.psk</code> 还是 <code>.pskx</code> 以实际文件为准。</p>

    <h3>重新生成本页</h3>
    <pre>cd E:\code\othercode\ripper_tpose     # 即 &lt;仓库根&gt;，换成你自己 clone 的位置；这一节都在仓库根下执行
python scripts\final\html\collect_manifest.py      # 读 _blends\*.json -&gt; &lt;导出根&gt;\ff7remake_models_manifest.json，不开 Blender
python scripts\final\html\make_gallery.py          # 缩略图 -&gt; &lt;导出根&gt;\_gallery\thumbs\，页面 -&gt; scripts\final\html\index.html（直接覆盖仓库里已有的那份）
python scripts\final\html\make_gallery.py --source-root D:\ff7remake_exports\player --force   # 换根 / 强制重建缩略图</pre>
    <p><code>collect_manifest.py</code> 可接位置参数 <code>[导出根] [manifest 路径]</code>；<code>make_gallery.py</code> 另有
      <code>--manifest</code>、<code>--out</code>、<code>--thumb-dir</code>。用了 <code>-NoPreview</code> 的先补渲（同样在仓库根下；它只打开做好的 .blend，不需要 PSK 插件）：</p>
    <pre>&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --python scripts\final\html\render_blend_preview.py -- D:\ff7remake_exports\player\_blends
# 已有且比 .blend 新的 _preview.png 跳过，比 .blend 旧的照样重渲并覆盖；--force 无条件重渲全部；也可以只给单个 .blend 路径；--suffix _preview 是缺省后缀</pre>
    <p>manifest、缩略图、预览都留在导出根下，<b>刻意不进仓库</b>；页面里全是 <code>file://</code> 本机链接，换机器要重生成。</p>

    <h3>不在本页 / 没导的东西</h3>
    <ul>
      <li>清单只有 36 个 Player 主模型：武器（含 Tifa 手套）、NPC、敌人没批量导，需要就走「拆开跑」。</li>
      <li><code>_90/_91</code> 7 个是泪痕/血迹叠加贴片（约 1000 顶点 + 遮罩 + 法线，无颜色图，预览只有一小片脸），<code>PC0099</code> 7 个是蛤蟆；完整人物 22 个。</li>
      <li>官方没有 nude：<code>PC0000_05_Cloud_Naked</code> 是浴场剧情版，网格与标准装一致（预览看起来相同）。Tifa 裸模来自 <code>~mods</code> 社区 mod，专用 umodel 导不出那张大网格，流程在 <code>docs\ff7remake-mod-manual-export.md</code>，不在本页范围。</li>
      <li>动画缺省不导；材质只到 Diffuse/Normal/Alpha，Renderer 专用 shader 无法重建；导入时报 384 个顶点顶点色歧义是无害告警。</li>
    </ul>
</section>
"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FF7 Remake 模型导出总览</title>
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
  <h1>FF7 Remake INTERGRADE 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>覆盖角色</span></div>
    <div class="stat"><b>{mods}</b><span>贴片/蛤蟆变体</span></div>
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
    manifest_path = args.manifest or os.path.join(source_root, "ff7remake_models_manifest.json")
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
    print("models      : %d（表情/蛤蟆变体 %d）" % (len(models), sum(1 for m in models if m["kind"] != "official")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
