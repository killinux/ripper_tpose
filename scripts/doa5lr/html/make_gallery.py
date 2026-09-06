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
COSTUME_TMC_RE = re.compile(r"^([A-Z0-9]+_(?:COS|DLC|DLCU)_\d+)\.TMC$")


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
    """服装条目（KASUMI_COS_002）-> 所在封包。拿不到游戏目录就返回空表（页面自动隐藏该 facet）。"""
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
            # 必须整名精确匹配 <角色>_COS_NNN.TMC —— 松散地用 "in" 会被
            # KASUMI_BOSS_COS_001.TMC 之类命中，把霞误标成 chara_common
            m = COSTUME_TMC_RE.match(real)
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
        char_code = entry.get("char") or ""
        costume = entry.get("costume") or (char_code + "_COS_001")
        models.append({
            "label": label,
            "char": char_code,
            "costume": costume,
            "archive": archives.get(costume, ""),
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
    if model["costume"]:
        badges += '<span class="badge badge-cos">%s</span>' % esc(model["costume"].split("_", 1)[1])

    parts = model["parts"]
    part_txt = " · ".join(
        "%s %d" % (label, parts.get(key, 0))
        for key, label in (("body", "身体"), ("face", "脸"), ("hair", "头发"))
        if parts.get(key))
    other = parts.get("other", 0)
    if other:
        part_txt += " · 其它 %d" % other

    search_blob = esc(" ".join([model["label"], model["char"], model["costume"], model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-arc="{arc}" data-chr="{chr}" data-warn="{warn}">
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
""".format(search=search_blob, arc=esc(model["archive"]), chr=esc(model["char"]),
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
    per_char = {}
    for m in models:
        per_char[m["char"]] = per_char.get(m["char"], 0) + 1
    chr_options = "".join('<option value="%s">%s (%d)</option>' % (esc(c), esc(c), n)
                          for c, n in sorted(per_char.items()))
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        appendix=APPENDIX_HTML,
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, chips=chips, chr_options=chr_options, cards=cards)


APPENDIX_HTML = r"""
<section class="appendix">
    <h2>附录 · 手工导出教程</h2>
    <p>脚本都在 <code>scripts\doa5lr\</code>，必须在<b>装有游戏的那台机器</b>上跑（Windows PowerShell 5.1）。
    链路：<code>.bin/.lnk</code> 封包 → <code>extract_lnk.py</code> 解出 TMC/TMCL → 32 位 Noesis 转 FBX + DDS → Blender 无头组装成带贴图的
    <code>.blend</code> 并渲预览。日常只需 <code>export_full.ps1</code> 一条命令。原理见同目录 <code>README.md</code>，更多用例见 <code>EXPORT_GUIDE.md</code>。</p>

    <h3>前提 · 工具与默认路径</h3>
    <table>
      <tr><th>依赖</th><th>脚本默认路径（覆盖参数）</th><th>说明</th></tr>
      <tr><td>游戏本体</td><td><code>D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round</code>（<code>-GameRoot</code>）</td><td>Steam 版：Steam 库里右键游戏 → 管理 → 浏览本地文件，打开的就是游戏根目录，里面直接是 <code>chara_common.bin/.lnk</code>、<code>chara_initial.bin/.lnk</code> 等成对文件（<code>.lnk</code> 是数据体不是快捷方式，必须与 <code>.bin</code> 同名同目录，<code>extract_lnk.py</code> 按 <code>.bin</code> 路径换扩展名找它）。本机是 36 对，含 <code>patch_XX_catalog</code> 这类后期 DLC 封包；数目不同不影响主流程，建索引时按实际存在的 <code>*.bin</code> 扫</td></tr>
      <tr><td>Python 3</td><td><code>D:\openclaw\python\python.exe</code>（<code>-PythonExe</code>）</td><td>任意 Python 3 即可，但要两处都能找到：页面里写 <code>python</code> 的命令走 PATH，两个 .ps1 走 <code>-PythonExe</code>（默认这个路径，装在别处就改 param() 默认值，见参数表末行）。解包只用标准库；画廊用 <code>python -m pip install pillow</code>，装到跑 <code>make_gallery.py</code> 的那个 python 里</td></tr>
      <tr><td>Noesis <b>32 位</b></td><td><code>E:\tools\noesisv\Noesis.exe</code>（<code>-NoesisExe</code>）</td><td>Noesis 官网（richwhitehouse.com）下载，解压即用，本文用其中 32 位 <code>Noesis.exe</code>（同包的 <code>Noesis64.exe</code> 是 DOA6 用的，不是它）。DOA5 插件来自日本 DOA5LR mod 社区分发的三个 zip（与下面的 Archive Tool 同源，需自行搜索下载）：<code>for_Noesis_TMC_Plugin_Custom_2.2.zip</code> → <code>doa5pc_custom.py</code>（TMC→FBX，自动读同目录 TMCL 出 DDS，<b>必需</b>）；<code>for_Noesis_H_P_Plugin.zip</code> → <code>fmt_doa5pc_tex.py</code>、<code>for_Noesis_tmcmesh_Plugin_1.1.zip</code> → <code>fmt_doa5pc_tmcmesh.py</code>（<code>--H/--P</code> 与 tmcmesh 用，可选）。三个 .py 原样解压放进 <code>plugins\python\</code>，不用改文件顶部的 user settings，本管线用的就是出厂默认值</td></tr>
      <tr><td>Blender 3.6.15</td><td><code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code>）</td><td>必须 3.x（实测 3.6.15，blender.org 的 release/Blender3.6 归档，zip 便携版即可）。4.x 不能用：<code>build_blend.py</code> 用的是 3.6 的 Principled BSDF <code>Specular</code> 输入、<code>mat.shadow_method</code> 与 <code>BLENDER_EEVEE</code> 引擎名，4.x 改名/移除后脚本 Traceback，blend 不生成；<code>collect_manifest.py</code> 也要用同版本开这些 blend。自带 FBX 导入器与 numpy，不装插件，<code>--factory-startup</code> 下 FBX 导入器默认启用</td></tr>
      <tr><td>doaKey / file5lr.dat</td><td><code>E:\tools\doa5lr\</code></td><td>来自社区 Archive Tool 1.2.1（7z 包，日本 DOA5LR mod 社区的 5LRTools 分发目录，需自行搜索下载）。解压后 <code>file5lr.dat</code> 在根目录（DLC Tool JPN Custom 也附一份）；<code>doaKey</code> 不是随包放在根目录的文件，而是 C# 工程的嵌入资源，在 <code>src\Archive Tool\Resources\doaKey</code>（522 字节）。把这两个文件拷到 <code>E:\tools\doa5lr\</code>，路径与文件名必须一致：<code>extract_lnk.py</code> 虽有 <code>--key</code>/<code>--db</code>，但 .ps1 与画廊脚本调用时都不传，只按此目录找。验证：<code>python extract_lnk.py "&lt;游戏目录&gt;\chara_initial.bin" --list --filter "KASUMI_FACE*"</code> 能列出条目且没有 <code>doaKey 长度 ... != 522</code> 警告（霞的三个部件都在 <code>chara_initial</code>；换成 <code>chara_common.bin</code> 时这个过滤器 0 命中、只打印 <code>-- 0/2867 条目</code>，那不代表工具没装好）。<code>file5lr.dat</code> 是社区维护的名字表，旧于游戏补丁时 <code>--list</code> 末尾报 <code>N 个未知名</code>，属正常</td></tr>
      <tr><td>导出根</td><td><code>D:\doa5lr_exports</code></td><td><code>export_full.ps1 -OutRoot</code> / <code>export_character.ps1 -OutputRoot</code>，参数名不同</td></tr>
    </table>
    <p>不需要环境变量。表里的路径是脚本硬编码的默认值，最省事的做法是原样照搬这些目录。命令里的 <code>python</code>/<code>blender</code> 都指前提表里那两个可执行文件，不在 PATH 就写全路径（.ps1 内部已写死，不受影响）。
    两个 .ps1 存的是 UTF-8 with BOM，重存别丢。全新 Windows 客户端的执行策略默认是 Restricted，<code>.\xxx.ps1</code> 会被拒（<code>running scripts is disabled on this system</code>）：
    首次跑前放开一次 <code>Set-ExecutionPolicy -Scope CurrentUser RemoteSigned</code>，或不改策略、改用 <code>powershell -ExecutionPolicy Bypass -File .\export_full.ps1 ...</code>。
    本文命令都在 Windows PowerShell 5.1（<code>powershell.exe</code>）里验证。</p>

    <h3>角色 = 三个 TMC</h3>
    <table>
      <tr><th>部件</th><th>条目名</th><th>不加会怎样</th></tr>
      <tr><td>服装 + 身体</td><td><code>&lt;角色&gt;_COS_NNN</code> / <code>_DLC_NNN</code> / <code>_DLCU_NNN</code></td><td>—（位置参数，必给）</td></tr>
      <tr><td>脸</td><td><code>&lt;角色&gt;_FACE</code>（无编号）</td><td>不加 <code>-Face</code> → 无头</td></tr>
      <tr><td>头发</td><td><code>&lt;角色&gt;_HAIR_NNN</code></td><td>不加 <code>-Hair</code> → 光头</td></tr>
    </table>
    <p>角色代码即前缀，本页 19 人：<code>ALPHA152 AYANE CHRISTIE HELENA HITOMI HONOKA KASUMI KOKORO LEIFANG LISA MARIE MILA MOMIJI NYOTENGU PAI PHASE4 RACHEL SARAH TINA</code>。
    服装号是纯数字，看不出款式，导出后看预览挑；<code>DLCU_NNN</code> 是「Ultimate」系 DLC 位，与同号 <code>DLC</code> 不是同一套。</p>

    <h3>第一步 · 查条目名（extract_lnk.py --list）</h3>
    <p>以下所有命令都在仓库的 <code>scripts\doa5lr\</code> 目录里执行（把 <code>E:\code\othercode\ripper_tpose</code> 换成你 clone 的位置）。.ps1 通过 <code>$scriptDir</code>
    找同目录的 <code>extract_lnk.py</code>/<code>build_blend.py</code>，用绝对路径调用也行；但 <code>..\doa6\import_mod.ps1</code>、<code>html\...</code> 这类相对写法要求当前目录正确。</p>
    <pre>cd E:\code\othercode\ripper_tpose\scripts\doa5lr
$game = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round"

python extract_lnk.py "$game\chara_initial.bin" --list --filter "KASUMI*"       # 霞在该封包的全部条目
python extract_lnk.py "$game\chara_common.bin"  --list --filter "*_HAIR_*.TMC"  # 该封包里的发型（霞/绫音的在 chara_initial，要再查一次）
.\export_character.ps1 -List                                                    # 无过滤地列 chara_common 全部 2867 条；不能带 --filter，要筛用上面的 python</pre>
    <p>每行 <code>序号 真实名 flags 大小 @偏移</code>。<code>--filter</code> 是 fnmatch 通配符、不分大小写，<code>KASUMI*</code> 会连 <code>KASUMI_BOSS_*</code>
    和 <code>--H/--HL</code> 物理文件一起列出，要精确写 <code>KASUMI_COS_*.TMC</code>。模型分散在 36 个封包：常规服装/发型在 <code>chara_initial</code>
    与 <code>chara_common</code>，过场版在 <code>rtm_common</code>，后期 DLC 在 <code>patch_XX_catalog</code>。<code>export_full.ps1</code> 首次运行会扫全部
    <code>.bin</code> 写出 <code>D:\doa5lr_exports\_archive_index.txt</code>（每行 <code>条目名 封包</code>），之后直接查它：</p>
    <pre>Select-String '^KASUMI_(COS|DLC|DLCU)_\d+ ' D:\doa5lr_exports\_archive_index.txt</pre>
    <p>建索引时 <code>extract_lnk.py</code> 的 stderr 被 <code>2&gt;$null</code> 吞掉，脚本又是 <code>$ErrorActionPreference = "Stop"</code>：doaKey/file5lr.dat 没放对时，
    「建立封包索引」之后只会看到一行类似 <code>python.exe : Traceback (most recent call last):</code> 就中止，真正的原因（哪个文件找不到）看不见，索引文件也不会生成。
    所以首次运行前务必先用上面的 <code>extract_lnk.py --list</code> 跑通一次（这一步能看到完整报错）；建完索引后检查
    <code>(Get-Content D:\doa5lr_exports\_archive_index.txt).Count</code>，正常约 1099 行（TMC 总数），明显偏少说明有封包解析失败，修好后删掉该文件再跑。</p>

    <h3>第二步 · 一键出带材质 blend（export_full.ps1）</h3>
    <pre>.\export_full.ps1 KASUMI_COS_001 -Face auto -Hair 001 -Label KASUMI_Kasumi            # 默认服装
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002    # 换装：脸/发型已提取过就复用
.\export_full.ps1 HONOKA_COS_001 -Face auto -Hair HONOKA_HAIR_002 -Label HONOKA_Honoka_COS_001   # -Hair 也可给完整名</pre>
    <p>脚本依次：查索引定位封包并调 <code>export_character.ps1</code> 解出 TMC/TMCL → Noesis <code>?cmode</code> 转 FBX，同目录落下 <code>Tex_NN(L_x).dds</code>
    → 每张 DDS 再转同名 PNG（Blender 读不了部分 BC 格式）→ <code>build_blend.py</code> 按 服装 → 脸 → 头发 顺序导入，只在部件确实不在身体坐标系时才搬，
    把 1.6 cm 高的模型归一到约 1.7 单位，按 Diffuse/Normal/Specular 重建 Principled 材质，打包贴图，EEVEE 渲 900×1400 预览。
    正常会依次打印 <code>FBX_IMPORTED=3</code>、<code>PART_ALIGNED</code>（脸、发各一行，单部件时没有）、<code>SCALE_NORMALIZED</code>、<code>MATERIALS_REBUILT</code>、<code>IMAGES_PACKED</code>、
    <code>SAVED_BLEND</code>、<code>SAVED_PREVIEW</code>、<code>BUILD_BLEND=PASS</code>，最后绿色 <code>OK &lt;Label&gt; (xx MB)</code>。单套 5–16 秒。</p>
    <p><code>-Label</code> 按 <code>&lt;角色&gt;_&lt;英文名&gt;_&lt;COS|DLC|DLCU&gt;_&lt;NNN&gt;</code> 起（默认装可省尾缀）：画廊靠文件名解析服装号，带中文或多余下划线的
    会被当成 <code>COS_001</code>。目标 blend 已存在时打印 <code>SKIP</code> 返回，加 <code>-Force</code> 才重做。</p>

    <h3>批量 · 一个角色的全部服装</h3>
    <pre>$entries = Get-Content D:\doa5lr_exports\_archive_index.txt |        # 先单跑过一次第二步，索引才存在
  ForEach-Object { if ($_ -match '^(KASUMI_(COS|DLC|DLCU)_\d+) ') { $Matches[1] } } |
  Sort-Object -Unique
foreach ($entry in $entries) {
  $suffix = $entry.Substring($entry.IndexOf('_') + 1)                 # COS_002 / DLC_011 / DLCU_003
  if ($suffix -eq 'COS_001') { continue }                             # 默认装已按 KASUMI_Kasumi 出过，Label 不同不会 SKIP
  try   { .\export_full.ps1 $entry -Face auto -Hair 001 -Label "KASUMI_Kasumi_$suffix" }
  catch { Write-Warning "$entry : $_" }                                # 占位条目会抛错，别让它中断循环
}</pre>
    <p>换角色只改正则和 Label 前缀。已有 blend 自动 SKIP，中断后重跑即续传。头发一律 <code>-Hair 001</code>——每套服装的官方默认发型无法从条目名得知，
    要别的发型用 <code>-Hair 003</code> 之类另出一份。</p>

    <h3>只要 FBX + DDS（export_character.ps1）</h3>
    <pre>.\export_character.ps1 HONOKA                                 # HONOKA_* 全部条目（含发型），一个条目一个子目录
.\export_character.ps1 KASUMI_COS_002 -Archive chara_initial   # 指定封包；缺省 chara_common，不是 auto
.\export_character.ps1 HONOKA -NoConvert                       # 只解 TMC/TMCL，不转 FBX</pre>
    <p>产物在 <code>D:\doa5lr_exports\&lt;名字&gt;\&lt;条目&gt;\</code>：<code>.TMC/.TMCL/.fbx</code> + <code>Tex_NN(L_x).dds</code>（L 全尺寸、M 小 mip）。<code>&lt;条目&gt;\</code> 子目录只在转换那一步建，
    <code>-NoConvert</code> 不建它——<code>.TMC/.TMCL</code> 直接躺在 <code>D:\doa5lr_exports\&lt;名字&gt;\</code> 下，不是解包失败。
    目录已存在会 SKIP，<code>-Force</code> 则整个删掉重建（<code>Remove-Item -Recurse</code>）。</p>

    <h3>社区 mod（含 nude）</h3>
    <pre>.\export_full.ps1 -TmcFile D:\mods\KasumiNude.TMC -Label KAS_Nude                                   # 纯 mod
.\export_full.ps1 -TmcFile D:\mods\body.TMC -FaceTmc D:\mods\face.TMC -HairTmc D:\mods\hair.TMC -Label X
.\export_full.ps1 KASUMI_COS_001 -TmcFile D:\mods\nude.TMC -Face auto -Hair 001 -Label KAS_Nude    # mod 身体 + 官方脸/发型
..\doa6\import_mod.ps1 D:\mods\some_mod.zip                                                          # 只要 FBX+DDS，zip/目录批量</pre>
    <div class="note"><b>官方内容没有 nude。</b>36 个封包、12,625 个条目名搜 <code>nude/naked/bare/skin/under/lingerie</code> 零命中。
    mod 就是替换用的 <code>.TMC</code> + 同名 <code>.TMCL</code>，格式与官方一致，<code>-TmcFile</code> 直接吃（给目录则取第一个 <code>.TMC</code>），缺 <code>.TMCL</code>
    会警告并出白模；中转目录 <code>D:\doa5lr_exports\_mods\&lt;TMC名&gt;\</code>——<b>每次跑到这一步都会先整个删掉再重建</b>（与 <code>-Force</code> 无关，只有目标 blend
    已存在 SKIP 时才不动），别把手改的文件放在里面。<code>-Face auto</code>/<code>-Hair 001</code> 靠位置参数里的角色名推导前缀，
    纯 mod 请用 <code>-FaceTmc</code>/<code>-HairTmc</code>。mod 在 GameBanana 上是 0 个，主要在 LoversLab（需登录手动下载）。</div>
    <p><code>..\doa6\import_mod.ps1</code> 是 DOA5/DOA6 通用脚本，按扩展名自动判别 TMC/g1m：产物在 <code>D:\doa_mod_fbx\&lt;zip 或目录名&gt;\</code>（<code>-OutRoot</code> 改；<b>此脚本既没有 SKIP 也没有 <code>-Force</code>，重跑同一个 zip/目录会直接覆盖该目录里的同名 FBX/DDS</b>）；
    zip 会先解压到 <code>D:\doa_mods\_extract_tmp\&lt;名字&gt;\</code>（硬编码；<b>解压前该目录若已存在会先整个删掉</b>，处理完再删一次，<code>-KeepExtracted</code> 只是保留处理完那一次）；32 位 Noesis 路径用 <code>-Noesis32</code> 指定（不是 <code>-NoesisExe</code>）。</p>

    <h3>export_full.ps1 参数表</h3>
    <table>
      <tr><th>参数</th><th>作用</th></tr>
      <tr><td>位置参数 <code>&lt;条目名&gt;</code></td><td>服装条目，自动转大写；也是 <code>-Face</code>/<code>-Hair</code> 推导前缀的来源</td></tr>
      <tr><td><code>-Face auto</code></td><td>用 <code>&lt;角色&gt;_FACE</code>；给带下划线的完整名则转大写后直接用</td></tr>
      <tr><td><code>-Hair 001</code></td><td>编号（写满三位）或完整名 <code>KASUMI_HAIR_001</code></td></tr>
      <tr><td><code>-Archive auto</code></td><td>缺省，每个部件各自查索引；手动指定（如 <code>chara_initial</code>）时三个部件共用同一封包</td></tr>
      <tr><td><code>-Label</code></td><td>产物文件名；缺省用条目名或 mod TMC 文件名</td></tr>
      <tr><td><code>-TmcFile / -FaceTmc / -HairTmc</code></td><td>外部 TMC 文件或目录，替代对应部件</td></tr>
      <tr><td><code>-Force</code></td><td>覆盖已有 blend，<b>并把三个部件目录 <code>&lt;OutRoot&gt;\&lt;条目&gt;\</code> 整个删掉重解</b>（<code>Remove-Item -Recurse</code>，里面手改、手补的文件一起没）。注意不给 <code>-Force</code> 也可能重解：脚本判定复用只看 <code>&lt;OutRoot&gt;\&lt;条目&gt;\&lt;条目&gt;\&lt;条目&gt;.fbx</code> 在不在，不在（上次 Noesis 失败，或先用 <code>-NoConvert</code> 只解过 TMC）就固定带 <code>-Force</code> 去调 <code>export_character.ps1</code>，同样是整个删掉重建，别把手改的文件放在里面</td></tr>
      <tr><td><code>-NoPreview</code></td><td>不渲预览图。预览用 EEVEE 渲染，需要 GPU/OpenGL：在 VM、远程桌面或无显卡机器上渲染失败时 blend 其实已先存好（已打印 <code>SAVED_BLEND</code>，脚本仍显示 OK 但没有 <code>SAVED_PREVIEW</code>），加 <code>-NoPreview</code> 跳过即可，画廊显示「无预览图」</td></tr>
      <tr><td><code>-GameRoot / -OutRoot / -PythonExe / -NoesisExe / -BlenderExe</code></td><td>只对 <code>export_full.ps1</code> 自己的步骤（建索引、DDS→PNG、mod TMC 转换、Blender 组装）生效；内部调用的 <code>export_character.ps1</code> 只收到 <code>-Archive</code>/<code>-OutputRoot</code>（即 <code>-OutRoot</code>）/<code>-Force</code>，<b>不接收</b> <code>-GameRoot/-PythonExe/-NoesisExe</code>，解包那一步仍用它自己的默认值——游戏不在默认路径会直接抛 <code>archive not found</code>。路径不同的机器请直接改两个 .ps1 param() 块里的默认值（<code>export_full.ps1</code> 第 31–35 行、<code>export_character.ps1</code> 第 14–18 行）和 <code>extract_lnk.py</code> 的 <code>DEFAULT_TOOLS_DIR = r"E:\tools\doa5lr"</code>，或干脆把工具装到前提表的默认路径</td></tr>
    </table>

    <h3>产物目录</h3>
    <pre>D:\doa5lr_exports\
├─ _archive_index.txt               条目名 → 封包（-Archive auto 首次生成，删掉可重建）
├─ KASUMI_COS_002\KASUMI_COS_002\   部件中转目录：.TMC .TMCL .fbx Tex_NN(L_x).dds + 同名 .png
├─ KASUMI_FACE\KASUMI_FACE\         脸、发型同上，被同角色所有服装复用
├─ KASUMI_HAIR_001\KASUMI_HAIR_001\
├─ _mods\&lt;TMC名&gt;\                  外部 mod 的中转目录（每次运行整个重建）
├─ _blends\&lt;Label&gt;.blend           成品，贴图已打包
├─ _blends\&lt;Label&gt;_preview.png     预览 900×1400
├─ doa5lr_models_manifest.json      collect_manifest.py 的统计清单
└─ _gallery\thumbs\&lt;Label&gt;.jpg     本页缩略图</pre>

    <h3>容易踩的坑</h3>
    <table>
      <tr><th>症状</th><th>原因 → 处理</th></tr>
      <tr><td>.ps1 报 <code>running scripts is disabled on this system</code></td><td>执行策略还是默认的 Restricted → 见前提段，<code>Set-ExecutionPolicy -Scope CurrentUser RemoteSigned</code> 或 <code>-ExecutionPolicy Bypass</code></td></tr>
      <tr><td>光头 / 无头</td><td>漏了 <code>-Hair</code> / <code>-Face</code> → 补参数加 <code>-Force</code> 重出</td></tr>
      <tr><td>「建立封包索引」后只报一行 <code>Traceback (most recent call last):</code> 就中止</td><td>doaKey/file5lr.dat 没放对或 python 跑不起 <code>extract_lnk.py</code>，stderr 被吞只剩首行 → 手跑第一步的 <code>extract_lnk.py --list</code> 看完整报错</td></tr>
      <tr><td><code>封包索引里没有 X.TMC</code></td><td>条目名拼错或索引过期 → <code>--list --filter</code> 核对；删 <code>_archive_index.txt</code> 重建。索引行数远少于 1099 → 建索引时有封包解析失败，见第一步</td></tr>
      <tr><td><code>没有生成 FBX</code> / <code>无 TMCL 或插件不识别</code></td><td>封包选错（<code>export_character.ps1</code> 缺省 <code>chara_common</code>），或 Noesis 不是 32 位、没装 <code>doa5pc_custom.py</code></td></tr>
      <tr><td><code>-Face 需要同时给出角色名</code></td><td>只给了 <code>-TmcFile</code> 没有位置参数 → 改 <code>-FaceTmc</code>/<code>-HairTmc</code></td></tr>
      <tr><td>并行时脸/发型目录突然没了</td><td>另一路带 <code>-Force</code> 在重解同角色的 <code>FACE</code>/<code>HAIR</code> → 并行只按角色切分，且不带 <code>-Force</code></td></tr>
      <tr><td>皮肤/衣服半透明起噪点</td><td>老版本把 diffuse alpha 里的高光遮罩当透明度；现按数据判定（&gt;2% 全透明 <b>且</b> &gt;4% 全不透明才接 Alpha）→ 旧 blend <code>-Force</code> 重出</td></tr>
      <tr><td>头发压在脸上 / 没有脸 / 兔耳装脸发上浮</td><td>老版本强行按包围盒对齐，马尾发梢、女天狗翅膀、兔耳都会骗过包围盒；现默认不动，只搬顶端够不到身体顶端 25% 的部件 → 旧 blend <code>-Force</code> 重出</td></tr>
      <tr><td>Alpha-152 通体白</td><td>素材如此：三部件加起来只有 8 张 DDS（其中服装 2 张），成品 blend 里只打包了 5 张图，画廊因此标「贴图仅 5 张」告警；游戏靠特殊半透明 shader，没有颜色贴图可还原</td></tr>
      <tr><td><code>MILA_COS_008</code>、<code>SARAH_DLC_002</code>、<code>PAI_DLC_002</code> 报错</td><td>10 KB 占位条目，无网格 → 跳过</td></tr>
      <tr><td>.ps1 报 <code>missing terminator</code></td><td>脚本被存成无 BOM 的 UTF-8，PowerShell 5.1 按 GBK 解析吞掉引号 → 用 UTF-8 with BOM 重存</td></tr>
    </table>

    <h3>并行与耗时</h3>
    <p>脚本没有分片参数，并行就是开几个 PowerShell 窗口各跑一份上面的循环，<b>按角色切分</b>。先在单窗口跑通任意一套（让索引建好，首次要扫 36 个封包）
    再开并行；脸/发型目录已存在就复用，不同路之间不要用 <code>-Force</code>。实测单套 5–16 秒：COS/DLC 的 223 套三路并行跑完，DLCU 的 47 套随后同法补出，合计 270 套换装；19 人默认装当初是 19 路并行 129 秒。画廊现共 291 个模型（19 默认装 + 270 换装 + 2 件早期 KASUMI_DLC_011 对照件）。
    <code>-NoPreview</code> 省掉的只是一次 EEVEE 渲染。</p>

    <h3>重新生成本页</h3>
    <pre>cd E:\code\othercode\ripper_tpose\scripts\doa5lr
blender --background --factory-startup --python html\collect_manifest.py -- D:\doa5lr_exports   # 根目录可省，第二个参数可指定 manifest 路径
python html\make_gallery.py            # 读 manifest、生成缩略图、重写 html\index.html
python html\make_gallery.py --force    # 预览图没变也重建缩略图</pre>
    <p><code>blender</code>/<code>python</code> 即前提表里那两个可执行文件，不在 PATH 就写全路径（pillow 要装在这个 python 里）。第一步逐个打开 <code>_blends\*.blend</code>，按网格名前缀
    （<code>WGT_body*</code>/<code>WGT_face*</code>/<code>WGT_hair*</code>/<code>MOT01_Head*</code>）统计部件、材质、透明材质、贴图数，缺脸、缺发、贴图少于 10 张记为告警，
    写 <code>doa5lr_models_manifest.json</code>；第二步把预览缩成 720 px 宽 JPEG 放进 <code>_gallery\thumbs\</code>，输出 <code>scripts\doa5lr\html\index.html</code>。
    可选 <code>--source-root</code>、<code>--manifest</code>、<code>--out</code>、<code>--thumb-dir</code>、<code>--game-root</code>（封包徽标要现扫
    <code>chara_common.bin</code>/<code>chara_initial.bin</code> 并读 <code>file5lr.dat</code>，拿不到就隐藏该筛选）。
    <b>manifest 与缩略图都留在导出根，刻意不进仓库</b>——仓库不收任何游戏素材；页面链接是本机 <code>file://</code> 路径，换机器要重新生成。</p>

    <h3>例外与已知限制</h3>
    <ul>
      <li>本页只覆盖 19 名女性角色的默认装与全部 <code>COS/DLC/DLCU</code> 换装。游戏共 34 名角色、678 个角色模型：男性角色、<code>rtm_common</code> 过场版、<code>*_BOSS_*</code> 变体、<code>stage_*</code> 场景都能用同样命令导，只是没纳入本批。</li>
      <li>所有条目统一 <code>HAIR_001</code>，不代表该服装在游戏里的默认发型。</li>
      <li>本页那份 <code>KASUMI_DLC_011</code> 是未加 <code>-Hair</code> 的光头对照件，告警属实；少数 DLC 服装（如它）自带头部，<code>COS_</code> 系一律不带。</li>
      <li>没有官方 nude，只能走 mod 路线。</li>
    </ul>
</section>
"""

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
.badge-cos {{ background: #eef2ff; color: #3730a3; }}
#chr {{ padding: 6px 8px; border: 1px solid #ddd; border-radius: 8px; background: #fff; }}
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
  <input id="q" type="search" placeholder="搜索角色名/服装号或路径…（按 / 聚焦）">
  <select id="chr"><option value="">全部角色</option>{chr_options}</select>
  <button class="chip on" data-arc="">全部封包</button>
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
  var arc = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!arc || card.dataset.arc === arc)
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
