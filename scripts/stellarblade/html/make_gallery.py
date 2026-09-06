"""把 Stellar Blade 的 Eve 服装导出产物做成一页可浏览的 HTML 画廊。

读 ``stellarblade_models_manifest.json``（由 collect_manifest.py 从 validation\\*.json 报告汇总），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\stellarblade_exports --force
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
KIND_LABELS = {"official": "本体服装", "dlc": "联动 DLC", "nude": "裸模（mod）", "other": "其它"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\stellarblade_exports",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\stellarblade_models_manifest.json）")
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
            "char": entry.get("group") or "",
            "code": entry.get("package") or "",
            "variant": entry.get("name") or "",
            "face": entry.get("facePreview") or "",
            "morphs": entry.get("morphs") or 0,
            "kind": entry.get("kind") or "official",
            "blend": entry.get("blend") or "",
            "package": entry.get("packageDir") or "",
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
        badges += '<span class="badge badge-code">%s</span>' % esc(model["code"].replace("CH_P_EVE_", ""))

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
            <dt>服装</dt><dd>{variant}</dd>
            <dt>规格</dt>
            <dd>{meshes} 网格 · {vertices} 顶点 · {bones} 骨骼 · {morphs} 表情 · {size}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>{package_row}
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]), chr=esc(model["char"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, label=esc(model["label"]),
           badges=badges, variant=esc(model["variant"] or "-"),
           meshes=model["meshes"], vertices=model["vertices"], bones=model["bones"],
           morphs=model["morphs"],
           size=human_size(model["blend_size"]),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]),
           package_row=('\n            <dt>独立包</dt>\n            <dd><a href="%s" title="整个文件夹可拷给别人：blend + textures\\ + README">%s</a>'
                        '\n                <button class="copy" data-copy="%s">复制</button></dd>'
                        % (esc(file_uri(model["package"])), esc(model["package"]), esc(model["package"])))
                       if model["package"] else "")


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    characters = len({m["char"] for m in models})
    warned = sum(1 for m in models if m["warnings"])
    mods = sum(1 for m in models if m["kind"] != "official")
    kinds = [k for k in ("official", "dlc", "nude", "other") if any(m["kind"] == k for m in models)]
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
    <p>脚本都在 <code>scripts\stellarblade\</code>，必须在<b>装有游戏的那台机器</b>上跑，产物默认落在 <code>D:\stellarblade_exports</code>（<code>-ExportRoot</code>）。
      顺序固定：FModel 手导三个共享文件 → <code>export_eve.ps1</code> 组装标准 Eve（两步都只做一次）→ <code>export_outfit.ps1 &lt;包名&gt;</code> 任意服装出带贴图的 .blend
      → 补渲亮预览、重生成本页 → <code>package_outfits.py</code> 打成可拷走的独立文件夹。原理见 <code>docs\stellar-blade-extraction.md</code>，编号→服装名见 <code>docs\stellar-blade-eve-outfits.md</code>。
      <b>以下所有命令都在 <code>〈仓库〉\scripts\stellarblade</code> 里跑，每开一个新窗口先 <code>cd</code> 进去。</b></p>

    <h3>前提 · 工具与默认路径</h3>
    <table>
      <tr><th>工具</th><th>脚本默认路径 / 说明</th></tr>
      <tr><td>游戏</td><td>Steam 版 1.4.1，<code>D:\Program Files (x86)\Steam\steamapps\common\StellarBlade</code>（<code>-GameRoot</code>）。索引未加密，<b>不需要 AES key</b></td></tr>
      <tr><td>Blender 3.6.15</td><td><code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code>），须先装好并启用 <b>io_scene_psk_psa 5.0.6</b>——脚本只探测不安装。
        从 <code>https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6</code> 下 zip（别拿最新 release，那些面向 Blender 4.x，3.6 装不上），Blender 3.6 里 Edit → Preferences → Add-ons → Install 选 zip，勾选启用后保存偏好设置；脚本用 <code>--background</code> 跑，只认已保存启用的插件</td></tr>
      <tr><td>UEFormat 导入器</td><td>不装插件：<code>export_eve.ps1</code> 自动下载钉住的快照 <code>58d1abf5…</code> 到 <code>&lt;导出根&gt;\_tools\</code>，用 <code>git apply --unidiff-zero</code> 打 <code>ueformat-blender36.patch</code>——PATH 里要有 <code>git</code> 且能连 github.com；已有补丁版就 <code>-UEFormatSource</code> 指到 <code>plugins\blender\io_scene_ueformat</code></td></tr>
      <tr><td>专用 UE Viewer</td><td><code>umodel_stellar_blade_v6.exe</code>，下载页 <code>https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/wiki/Extracting-game-files</code> 的 <code>umodel_stellar_blade_v6.zip</code>（SHA256 <code>61A641D3…FD550</code>，全值见 <code>docs\stellar-blade-extraction.md</code> §4），解压后程序自报 <code>UE Viewer build 1579 based fix2 / 2025-07-01</code>。
        <b>两个脚本默认路径不同</b>：<code>export_eve.ps1</code> 找 <code>C:\Tools\umodel_stellar_blade_v6.exe</code>，<code>export_outfit.ps1</code> 找 <code>E:\tools\umodel_stellarblade\umodel_stellar_blade_v6.exe</code>，对不上的传 <code>-UmodelExe</code>。gildor 官网普通版只看到约 7,275 个文件，不能用。扫描时出现 CEF locales <code>.pak has an unknown format</code> 可忽略（嵌入式浏览器资源）</td></tr>
      <tr><td>FModel 4.4.4</td><td>GUI，只用来手导三个共享文件；本机是 4.4.4 b270829，自行从官方发布页取。profile <code>GAME_StellarBlade</code>，local mapping <code>StellarBlade_1.1.0.usmap</code>——从 Modding Guide 仓库下载
        <code>https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/blob/main/StellarBlade_1.1.0.usmap</code>（SHA256 <code>40A8D85B…9122</code>，全值见 <code>docs\stellar-blade-extraction.md</code> §1）；文件名虽是 1.1.0，本机 1.4.1 的身体和脸已实测可解析，游戏再更新后需重新验证</td></tr>
      <tr><td>Python 3</td><td>装完勾选 Add to PATH，命令行里 <code>python</code> 要能直接调起 Python 3（Windows 11 自带的 Store 占位不算）——<code>export_outfit.ps1</code> 的兜底也靠它。<code>make_gallery.py</code> 要 <code>pip install Pillow</code>，其余只用标准库</td></tr>
      <tr><td>PowerShell</td><td>第一次跑 <code>.ps1</code> 若报 running scripts is disabled，先在当前用户范围放开脚本执行策略（RemoteSigned）再跑；两个入口都是未签名脚本，按 <code>.\名字.ps1</code> 调用</td></tr>
    </table>
    <p>环境变量只有一个可选项：手跑 <code>validate_eve.py</code> 不传 <code>--ueformat-source</code> 时读 <code>UEFORMAT_BLENDER_SOURCE</code>，走 ps1 不需要。
      开跑前关掉游戏 / FModel / UE Viewer，把 <code>SB\Content\Paks\~mods</code> 里的 Mod 暂时挪走（只有 <code>export_eve.ps1</code> 在补导时会告警，<code>export_outfit.ps1</code> 不检查；导出的会是 Mod 版）。</p>

    <h3>第零步 · 找包名（list_models.py）</h3>
    <pre>cd 〈仓库〉\scripts\stellarblade
python .\list_models.py --glob 'CH_P_EVE_*'                                  # 本体 Eve 服装里还没导过的
python .\list_models.py --glob 'CH_P_EVE_*' --path-filter 'SB/Content/DLC'   # 联动 DLC（默认过滤不含）</pre>
    <p>只读 <code>.utoc</code> 索引，不开任何工具；<code>--include-exported</code> 看全表，<code>--all-files</code> 看原始路径，<code>--csv</code> 写表。<b>包名 = 路径最后一段去掉 .uasset</b>：
      本体 <code>CH_P_EVE_NN</code> / <code>NN_Body</code>（02–63，12/13/38/44 不存在），换色 <code>_TypeB</code> / <code>_TypeC</code> / <code>_Body_02</code>，<code>NH</code> 无高跟，
      DLC <code>Nier_01~04</code> / <code>Nikke_01~06</code>（导出照样只写包名），<code>InnerSuit</code> 是 Skin Suit、也是裸模 mod 覆盖的对象。</p>

    <h3>第一步 · FModel 手导三个共享文件</h3>
    <p>FModel 无法无头跑，脚本只检查不生成。添加存档目录 <code>&lt;游戏目录&gt;\SB\Content\Paks</code>，profile 选精确的 <code>GAME_StellarBlade</code>，开 local mapping，无 AES；
      Models：LOD <code>First Level Only</code>、Texture PNG、PSK 选 <b>Don't Export Bone Sockets</b>、Morph targets 开；输出目录设成 <code>D:\stellarblade_exports\fmodel_exports</code>，
      加载 <code>pakchunk0-WindowsNoEditor.utoc</code>。在 FModel 搜索框里搜这三个包（搜路径后半段即可），右键 Save Model / Save Texture：</p>
    <pre>SB/Content/Art/Character/PC/CH_P_EVE_01/CH_P_EVE_01_Body               # Save Model，Mesh Format = ActorX
SB/Content/Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Face_003            # Save Model，Mesh Format = UEFormat，Morph targets 开
SB/Content/Art/Character/PC/CH_P_EVE_01/Tex/Body/CH_P_EVE_01_Body_D    # Save Texture</pre>
    <p>脚本要的是这三个文件（相对 <code>fmodel_exports\SB\Content\Art\Character\PC\</code>）：</p>
    <pre>CH_P_EVE_01\CH_P_EVE_01_Body.psk               # Mesh Format = ActorX
CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel         # Mesh Format = UEFormat（保 53 个表情 Morph）
CH_P_EVE_01\Tex\Body\CH_P_EVE_01_Body_D.png     # Save Texture</pre>
    <p>Mesh Format 和 Morph targets 是 FModel 的全局设置，导完身体记得切成 UEFormat 再导 Face_003。导出后先跑 <code>-List</code>，Status 列这三件都要是 <code>OK</code>（另外四件 UE Viewer 组件第一次跑就是 <code>MISSING</code>，第二步才补导）；
      显示 <code>MISSING</code> 就把 FModel 实际写出的 <code>SB\</code> 整棵目录挪到 <code>fmodel_exports\</code> 正下方，使路径与 <code>-List</code> 打印的完全一致；
      <code>BAD-HEADER</code> 表示格式选错（身体必须 ActorX，Face_003 必须 UEFormat）。</p>
    <pre>.\export_eve.ps1 -List    # 七个组件的 Status（三件 FModel + 四件 UE Viewer）+ 脸部贴图集 + 四个输出是否已存在
.\export_eve.ps1 -Check   # 体检全部输入（三件、UE Viewer 组件、UEFormat、Blender），不导任何东西</pre>
    <p>首次跑 <code>-Check</code> 只需要 <code>FModel inputs : OK</code> 和 <code>Blender : OK</code>；<code>UE Viewer set : needs export</code> 与 <code>UEFormat 3.6 : needs setup</code> 在第一次是正常的
      （快照下载和头发补导都只在正式跑时做），退出码 1 不代表失败。注意 <code>-Check</code> 不检查 <code>-UmodelExe</code> 是否存在，专用 UE Viewer 路径请自己核对。</p>

    <h3>第二步 · 标准 Eve 与共享组件（export_eve.ps1）</h3>
    <pre>.\export_eve.ps1           # 缺什么补什么，输出已存在则 SKIP；-Force 重建，-RefreshHair 先重导头发</pre>
    <p>①校验三个 FModel 文件；②UE Viewer 补导发型 / 马尾 / 短发束 / <code>PonyTail_Alpha.png</code> 到 <code>umodel_exports\</code>、Face_003 贴图到 <code>umodel_face_exports\</code>，
      并按 <code>Found N game files</code> 识别错误构建；③下载 + 补丁 UEFormat；④无头 Blender 跑 <code>validate_eve.py</code>。打印 <code>Validation PASS</code> 即成，
      产出 <code>blender\Eve_Standard_validation.blend</code> 与 <code>validation\Eve_Standard_validation.png / _face.png / .json</code>——<b>这份 .json 是所有服装的对齐参考，别删，也别改 <code>-OutputName</code></b>。</p>

    <h3>第三步 · 一套服装一条命令（export_outfit.ps1）</h3>
    <pre>.\export_outfit.ps1 CH_P_EVE_45_TypeB          # Pink Bear
.\export_outfit.ps1 CH_P_EVE_Nikke_06          # NIKKE Alice，DLC 也直接用包名
.\export_outfit.ps1 CH_P_EVE_20_TypeC -Force   # 三个产物都在会 SKIP，-Force 重做</pre>
    <p>①PSK 不在就用 UE Viewer 按名导 <code>.psk/.pskx</code> + 贴图到 <code>umodel_outfit_exports\</code>（本体在 <code>Art\Character\PC\CH_P_EVE_NN\</code>，DLC 在 <code>DLC_1\</code> / <code>DLC_2\</code> 子树下），按名导不出时自动用 <code>list_models.py</code> 查完整包路径再导；
      ②Blender 把服装身体 + 共享脸 / 发型 / 马尾 / 短发束装成<b>单一主骨骼 <code>Eve_Armature</code></b>，贴图按材质 <code>.mat</code> 逐槽匹配（相对外链到 <code>umodel_*_exports\</code>，不打进 .blend），渲染并写报告。
      打印 <code>Assembly PASS</code> 和 Blend / Render / Face / Report 四个路径即成功。</p>

    <h3>第四步 · 全部服装批量 + 亮预览</h3>
    <p>没有专门的批量脚本，README 只给了排除清单，下面这段循环是照着它写的示例（排除项以 README「全部服装批量」为准）。用 CSV 拿清单（本体 + DLC），去掉不是服装的部件包和 39_TYPE-A 废弃网格，分三个窗口跑（每个窗口都先 <code>cd</code> 到 <code>scripts\stellarblade</code>）：</p>
    <pre>python .\list_models.py --glob 'CH_P_EVE_*' --csv D:\stellarblade_exports\eve_pkgs.csv
python .\list_models.py --glob 'CH_P_EVE_*' --path-filter 'SB/Content/DLC' --csv D:\stellarblade_exports\eve_dlc.csv
$pkgs = Import-Csv D:\stellarblade_exports\eve_pkgs.csv, D:\stellarblade_exports\eve_dlc.csv |
  ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.package) } |
  Where-Object { $_ -notmatch 'CtlRig|IKDefo|LODSettings|Physics|Shadow|_sample|Test|Taper|NoHair|Clothdata|Face|Teeth|Hair|Head|TYPE-A' } |
  Sort-Object -Unique
$lane = 0; $lanes = 3        # 每个窗口把 $lane 改成 0 / 1 / 2
for ($i = $lane; $i -lt $pkgs.Count; $i += $lanes) { .\export_outfit.ps1 $pkgs[$i] }

&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --python ..\final\html\render_blend_preview.py -- D:\stellarblade_exports\blender --suffix _gallery</pre>
    <p>2026-09-05 这样跑出 146 套（本体 136 + DLC 10）；已有产物自动 SKIP，中断了重跑同一条即可续。最后一行给每个 .blend 补渲 <code>blender\Eve_&lt;包名&gt;_gallery.png</code>
      （<code>validate_eve.py</code> 自己的渲染偏暗），png 比 blend 新的跳过，<code>--force</code> 重渲。</p>

    <h3>参数表</h3>
    <table>
      <tr><th>参数</th><th>作用</th></tr>
      <tr><td><code>export_eve.ps1 -List / -Check / -RefreshHair / -OutputName</code></td><td>看组件清单 / 只体检不导 / 强制重导发型 / 马尾 / 短发束 / <code>PonyTail_Alpha</code>（脸部贴图集只在缺失时补导） / 产物基名（默认 <code>Eve_Standard_validation</code>）</td></tr>
      <tr><td><code>export_outfit.ps1 &lt;包名&gt; [-Diffuse]</code></td><td>包名是必填位置参数，只认包名不认路径；<code>-Diffuse</code> 手指贴图文件或目录，默认 PSK 旁的 <code>Tex\</code> / <code>Textures\</code></td></tr>
      <tr><td><code>-Force</code>（两脚本）</td><td>覆盖重做；不加时产物齐全会 SKIP</td></tr>
      <tr><td><code>-KeepSeparateArmatures</code>（两脚本）</td><td>不合并骨架，保留每组件独立 Armature（即不传 <code>validate_eve.py --merge-armatures</code>）</td></tr>
      <tr><td><code>-GameRoot / -ExportRoot / -BlenderExe / -UmodelExe / -UEFormatSource</code>（两脚本）</td><td>覆盖前提表里的默认路径——<b>只对两个 ps1 生效</b></td></tr>
      <tr><td>Python 脚本的路径</td><td>游戏 / 导出根不在默认位置时要另传：<code>list_models.py --paks &lt;游戏目录&gt;\SB\Content\Paks --export-root &lt;导出根&gt;</code>；<code>render_blend_preview.py</code> 的位置参数、<code>package_outfits.py --blend-dir / --out-root</code>、<code>collect_manifest.py</code> 第一个位置参数、<code>make_gallery.py --source-root</code> 都改成你的导出根；第四步和打包命令里的 <code>blender.exe</code> 路径同样按实际改。
        已知局限：<code>export_outfit.ps1</code> 按完整包路径重导的兜底调 <code>list_models.py</code> 时不带 <code>--paks</code>，游戏不在默认目录时该兜底查不到东西，脚本收尾报 <code>UE Viewer produced no …</code>。遇到 20 / 26 / 52 系这类按名导不出的包，先手动
        <code>python .\list_models.py --paks &lt;游戏目录&gt;\SB\Content\Paks --glob '&lt;包名&gt;.uasset' --all-files</code> 查到完整路径，照 <code>docs\stellar-blade-extraction.md</code> §4 的 UE Viewer 命令按该路径导出（<code>-out</code> 指到 <code>&lt;导出根&gt;\umodel_outfit_exports</code>），再跑 <code>.\export_outfit.ps1 &lt;包名&gt;</code>——PSK 已在就直接复用</td></tr>
    </table>

    <h3>产物目录（默认 D:\stellarblade_exports）</h3>
    <pre>fmodel_exports\SB\Content\Art\Character\PC\     FModel 手导的身体 PSK / Face_003.uemodel / 身体 _D.png
umodel_exports\ · umodel_face_exports\            发型 / 马尾 / 短发束 PSK 与 PonyTail_Alpha · Face_003 贴图集
umodel_outfit_exports\Art\Character\PC\CH_P_EVE_NN\  每套本体服装的 .psk/.pskx + .mat + Textures\
umodel_outfit_exports\DLC_1\ · DLC_2\             NieR / NIKKE 联动服装，同样结构挂在 DLC_N 子树下
_tools\UEFormat-&lt;commit&gt;\                        打过补丁的 UEFormat 快照
blender\Eve_&lt;包名&gt;.blend / _gallery.png          主产物 / 亮预览
validation\Eve_&lt;包名&gt;.png / _face.png / .json    验证渲染 / 脸部近景 / 报告（网格、骨骼、材质匹配、锚点误差）
stellarblade_models_manifest.json · _gallery\thumbs\ · packages\   本页的清单与缩略图 · 独立文件夹</pre>
    <p>磁盘预算：全部跑完 <code>blender\</code> 6.9 GB、<code>packages\</code> 29.8 GB，UE Viewer 导出的 PSK / 贴图另计，导出根按 40 GB 以上预留；空间紧张时打包加 <code>--no-extra</code>（每包少约 110 MB，148 个包合计 16.5 GB）。</p>

    <h3>容易踩的坑</h3>
    <table>
      <tr><th>症状</th><th>原因 → 处理</th></tr>
      <tr><td>UE Viewer 日志 <code>Found 7275 game files</code>（<code>export_eve.ps1</code> 会告警 only N game files visible；<code>export_outfit.ps1</code> 不检查，只会在后面报找不到 PSK）</td><td>普通 UE Viewer，或 <code>.pak/.utoc/.ucas</code> 基本名被改 → 换专用 v6 构建，正常是 228,867</td></tr>
      <tr><td><code>UE Viewer build not found</code> / <code>Shared Eve components missing</code> / <code>Patched UEFormat source not found</code></td><td>默认路径对不上 → <code>-UmodelExe</code>；没跑过第二步 → 先 <code>.\export_eve.ps1</code>。UEFormat 别拿上游 main，手工打补丁必须 <code>git apply --unidiff-zero</code></td></tr>
      <tr><td><code>-List</code> 显示 head 为 <code>BAD-HEADER</code></td><td>Face_003 是用 ActorX 导的 → FModel 里把 Mesh Format 切成 UEFormat 重导</td></tr>
      <tr><td>Blender 报 <code>Face_003 morph validation failed: source=N, Blender=M</code>（N 不是 53）</td><td>导 Face_003 时 Morph targets 没开 → 开了重导</td></tr>
      <tr><td>FModel 右键导出弹 <code>NullReferenceException</code></td><td>单独重启 FModel 只导目标包；仍复现就只对该组件改用专用 UE Viewer（<code>docs\stellar-blade-extraction.md</code> §3.2 / §7）</td></tr>
      <tr><td><code>No PSK importer is registered</code> / Blender produced no result marker</td><td>Blender 3.6 没启用 io_scene_psk_psa 5.0.6 → 装好再跑；脚本会打印 Blender 输出的最后 20–25 行供排查（<code>export_eve.ps1</code> 25 行，<code>export_outfit.ps1</code> 20 行）</td></tr>
      <tr><td><code>UE Viewer produced no CH_P_EVE_xx.psk/.pskx</code></td><td>包名写错 → 用 <code>list_models.py --glob 'CH_P_EVE_xx*'</code> 核对；同名对象抢先时脚本已自动改按完整包路径重导（游戏不在默认目录时见参数表的已知局限）</td></tr>
      <tr><td>装头发时报 <code>Ab-TL-HairB01 is missing</code></td><td>20 / 26 系有 <code>Temp\CH_P_EVE_20</code> 同名子包，骨架没马尾锚点 → 现版本已排除 <code>\Temp\</code>，旧导出目录里的 Temp 版删掉重跑</td></tr>
      <tr><td>整身灰白 / 皮肤贴成布料 / 01_Body 拿到 TypeB 的颜色</td><td>旧版按 <code>*_A.png</code> 猜名，01–06 系用共享 <code>ScanCloth_*_D</code> → 现版本先读 <code>.mat</code> 的 <code>Diffuse=</code>，旧产物加 <code>-Force</code> 重装</td></tr>
      <tr><td>导出来像 Mod 不像原版</td><td><code>~mods</code> 同路径包盖了原版 → 挪走后重导，结束再放回</td></tr>
    </table>
    <div class="note"><b>原版没有 nude，本页不覆盖裸模。</b>导出目录 <code>blender\</code> 里的 <code>Eve_Nude_*.blend</code> 来自作者本机安装的 EveOriginalProportions mod（覆盖 <code>CH_P_EVE_InnerSuit</code>）：要自行装 mod，手工把 mod 的 <code>.utoc/.ucas/.pak</code> 与游戏的 <code>global.utoc/ucas</code> 放到同一临时目录再用 UE Viewer 导，mod 骨架缺 <code>SC_Hair</code> 还得给 <code>validate_eve.py</code> 传 <code>--alignment-reference</code>；仓库里没有脚本，README「裸模」只是描述。
      按本页跑完应得 147 个包（146 套 + 标准 Eve），没有 <code>Eve_Nude_*</code> 和 <code>Eve_Face003_UEFormat36_test</code> 是正常的。</div>

    <h3>并行与耗时</h3>
    <p><code>export_outfit.ps1</code> 没有分片参数，并行就是第四步那样开几个窗口各跑一段，<b>同一个包别两个窗口同时跑</b>。实测三路并行每套 7–16 s，PSK 已在时约 6 s（146 套三路按此估算约十分钟）。打包脚本自带 <code>--lane/--lanes</code>。</p>

    <h3>重新生成本页</h3>
    <pre>python .\html\collect_manifest.py    # [导出根] [manifest 路径] 两个可选位置参数
python .\html\make_gallery.py         # --source-root / --manifest / --out / --thumb-dir / --force</pre>
    <p><code>collect_manifest.py</code> 不开 Blender，汇总 <code>validation\*.json</code> 写 <code>D:\stellarblade_exports\stellarblade_models_manifest.json</code>，预览优先 <code>_gallery.png</code>，有 <code>packages\&lt;label&gt;\package.json</code> 时卡片多一行「独立包」（<b>要先跑完下一节的打包</b>，再回来重跑这两条命令，卡片上才会有这一行）；
      <code>make_gallery.py</code> 把预览缩成 JPEG 放 <code>D:\stellarblade_exports\_gallery\thumbs\</code>，重写 <code>scripts\stellarblade\html\index.html</code>（<b>整页覆盖</b>：index.html 由 <code>make_gallery.py</code> 的页面模板生成，直接在 index.html 上手改的内容——包括本附录——重跑就没了，要留就改进 <code>make_gallery.py</code> 的模板）。<b>缩略图和 manifest 都留在导出根，刻意不进仓库</b>。</p>

    <h3>例外与已知局限</h3>
    <ul>
      <li><code>CH_P_EVE_39_TYPE-A</code> / <code>39_TYPE-A1</code>：材质槽全是 <code>MI_CH_Delete</code> 占位的废弃开发网格，不导。</li>
      <li><code>CH_P_EVE_11_1</code>（Raven 变体）自带发型，管线又装了默认发型，头上两套，自行删一套。</li>
      <li><code>Eve_Face003_UEFormat36_test.blend</code> 是作者机器上 <code>import_uemodel36.py</code> 留下的 UEFormat 导入探针，没贴图，打包默认跳过，按本页跑不会产生。</li>
      <li>眼睛：Eevee 不做 UE 的角膜折射，虹膜是 <code>validate_eve.py</code> 校准过的预览混合（虹膜贴图后插 HSV 提亮、眼影 / 眼罩壳层减淡），与游戏内不完全一致。</li>
    </ul>

    <h3>打包给别人（package_outfits.py）</h3>
    <p><code>blender\</code> 里的 .blend 贴图是相对外链，单拷一个文件会整身丢图。最后一步把每个 .blend 打成自足文件夹 <code>packages\&lt;label&gt;\</code>：
      <code>&lt;label&gt;.blend</code>（贴图改成 <code>//textures/</code> 相对路径）+ <code>textures\</code>（已接的 12–17 张 PNG）+ <code>textures\extra\</code>（服装自己的 _N / _ORM / _Mask / 换色图，未接节点）
      + <code>preview.png</code> / <code>preview_face.png</code> + 中英 <code>README.txt</code> + <code>package.json</code>。必须在 Blender 里跑，且<b>必须带 <code>--factory-startup</code></b>（不带的话存进 .blend 的界面来自本机启动文件）：</p>
    <pre>&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --factory-startup --python .\package_outfits.py -- --only Eve_CH_P_EVE_45_TypeB
&amp; 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --factory-startup --python .\package_outfits.py -- --lane 0 --lanes 3   # 三个窗口 0/1/2 全部打包
python .\package_outfits.py --index          # 不开 Blender，写 packages\README.md 总表 + packages_index.json</pre>
    <table>
      <tr><th>参数</th><th>作用</th></tr>
      <tr><td><code>--blend-dir / --out-root</code></td><td>默认 <code>D:\stellarblade_exports\blender</code> → <code>D:\stellarblade_exports\packages</code>，每模型一个子目录</td></tr>
      <tr><td><code>--only A B ...</code> / <code>--lane I --lanes N</code></td><td>只打这些 label（文件名去掉 .blend）/ 按排序后的 label 取第 I 片（从 0 起）</td></tr>
      <tr><td><code>--force</code> / <code>--zip</code></td><td>已有 <code>package.json</code> 且清单里的文件都在才 SKIP，加 <code>--force</code> 重做；<b>重做（含上次没做完自动重做）会先删掉该包的 <code>textures\</code> 整个目录</b>，别把自己的东西放进去 / 每包再打同名 .zip 到 out-root</td></tr>
      <tr><td><code>--no-extra / --include-probe / --validation-dir</code></td><td>不带 extra 图（每包少约 110 MB）/ 连探针也打 / 报告目录（默认 <code>&lt;blend-dir&gt;\..\validation</code>）</td></tr>
    </table>
    <p>存完会重新打开校验每张图都是 <code>//textures/</code> 且在包内，不通过的记进 package.json 的 <code>problems</code>。作者实测 148 个包（146 套 + 标准 Eve + 裸模）29.8 GB（平均 201 MB，其中 <code>textures\extra\</code> 占 16.5 GB），三路并行约 10 分钟。
      文件夹整个拷到任何装了 <b>Blender 3.6 或更新版</b>的电脑，双击 .blend 直接打开、视口切 Material Preview 就有贴图；选 <code>Eve_Armature</code> 进 Pose Mode 摆姿势，表情是头部物体 <code>Eve_Head_Mesh_01</code>（源包 Face_003）的 Object Data &gt; Shape Keys。</p>
  </section>
"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stellar Blade 模型导出总览</title>
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
  <h1>Stellar Blade · Eve 服装导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>服装编号</span></div>
    <div class="stat"><b>{mods}</b><span>DLC / 裸模</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索服装名（Pink Bear）、包名（45_TypeB）或路径…（按 / 聚焦）">
  <select id="chr"><option value="">全部编号</option>{chr_options}</select>
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
    manifest_path = args.manifest or os.path.join(source_root, "stellarblade_models_manifest.json")
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
    print("models      : %d（DLC/裸模 %d）" % (len(models), sum(1 for m in models if m["kind"] != "official")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
