"""把 DOA6 的导出产物做成一页可浏览的 HTML 画廊。

读 ``doa6_models_manifest.json``（由 collect_manifest.py 在 Blender 无头下生成），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\doa6_exports --force
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
KIND_LABELS = {"official": "官方", "mod": "mod 变体"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\doa6_exports",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\doa6_models_manifest.json）")
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
            "kind": entry.get("kind") or "official",
            "blend": entry.get("blend") or "",
            "preview": entry.get("preview") or "",
            "thumb": thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "meshes": entry.get("meshes") or 0,
            "armatures": entry.get("armatures") or 0,
            "materials": entry.get("materials") or 0,
            "alpha": entry.get("alphaMaterials") or 0,
            "images": entry.get("images") or 0,
            "parts": entry.get("parts") or {},
            "warnings": list(entry.get("warnings") or []),
        })
    models.sort(key=lambda m: (m["kind"] != "official", m["label"]))
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
    if model["kind"] == "mod":
        badges += '<span class="badge badge-mod">mod 变体</span>'

    parts = model["parts"]
    part_txt = " · ".join(
        "%s %d" % (label, parts.get(key, 0))
        for key, label in (("body", "身体"), ("face", "脸"), ("hair", "头发"))
        if parts.get(key))
    if parts.get("other"):
        part_txt += " · 其它 %d" % parts["other"]

    search_blob = esc(" ".join([model["label"], model["char"], model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{label}</h3>{badges}
          </div>
          <dl>
            <dt>部件</dt><dd>{parts} · {armatures} 骨架</dd>
            <dt>规格</dt>
            <dd>{meshes} 网格 · {materials} 材质（{alpha} 透明） · {images} 贴图 · {size}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, label=esc(model["label"]),
           badges=badges, parts=esc(part_txt or "-"), armatures=model["armatures"],
           meshes=model["meshes"], materials=model["materials"], alpha=model["alpha"],
           images=model["images"], size=human_size(model["blend_size"]),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]))


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    characters = len({m["char"] for m in models})
    warned = sum(1 for m in models if m["warnings"])
    mods = sum(1 for m in models if m["kind"] == "mod")
    kinds = [k for k in ("official", "mod") if any(m["kind"] == k for m in models)]
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    chips = "".join('<button class="chip" data-kind="%s">%s</button>' % (esc(k), esc(KIND_LABELS[k]))
                    for k in kinds)
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        appendix=APPENDIX_HTML,
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), characters=characters, size=human_size(total_bytes),
        warned=warned, mods=mods, chips=chips, cards=cards)


APPENDIX_HTML = r"""
<section class="appendix">
    <h2>附录 · 手工导出教程</h2>
    <p>脚本都在 <code>scripts\doa6\</code>，必须在装有 DOA6 的机器上跑（直读 Steam 目录里约 60GB 的 .rdb）。
      链路：<code>extract_rdb.py</code> 从 RDB 解出 G1M/G1T → Noesis64 + ProjectG1M 转 FBX/DDS →
      <code>g1m_matmap.py</code> 解出每个 submesh 用哪张贴图 → Blender 无头组装、打包贴图、渲预览。
      <code>export_full.ps1</code>（官方服装）和 <code>export_nude_mod.ps1</code>（社区 mod）把这四步串成一条命令；
      格式原理见同目录 <code>README.md</code>，更多操作见 <code>EXPORT_GUIDE.md</code>。</p>

    <h3>前提 · 工具与默认路径</h3>
    <table>
      <tr><th>依赖</th><th>脚本默认路径</th><th>说明 / 覆盖参数</th></tr>
      <tr><td>游戏本体</td><td><code>D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6</code></td><td>要读 <code>CharacterEditor.rdb</code>（模型）、<code>MaterialEditor.rdb</code>（贴图，45GB）、<code>KIDSSystemResource.rdb</code>；<code>-GameRoot</code>（仅 export_character.ps1 / export_nude_mod.ps1 有；export_full.ps1 没有，而且两个一键脚本都不把它转发给 export_character.ps1，见下「首次部署」）</td></tr>
      <tr><td>Python 3</td><td><code>D:\openclaw\python\python.exe</code></td><td>解包只用标准库；lz4 条目才 <code>pip install lz4</code>（DOA6 实测全 zlib）；画廊要 <code>pip install Pillow</code>；<code>-PythonExe</code></td></tr>
      <tr><td>Noesis 64 位</td><td><code>E:\tools\noesisv\Noesis64.exe</code></td><td>Noesis 是 Rich Whitehouse 的免费工具，从作者官网下载后解压到任意目录即可（表中 <code>noesisv</code> 只是解压目录名，不是软件名）；ProjectG1M 是另一个独立项目（GitHub 上的 Project-G1M，取 Releases），要自己把 64 位 <code>ProjectG1M.dll</code>（v1.7.4.2，原生插件）放进 Noesis 目录的 <code>plugins\x64\</code>，32 位 dll 放 <code>plugins\</code> 配 <code>Noesis.exe</code>；脚本全部用 <code>?cmode</code> 命令行模式调用，不用开 GUI；<code>-NoesisExe</code></td></tr>
      <tr><td>Blender 3.6.15</td><td><code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code></td><td><b>必须是 3.6 LTS</b>：4.2 及以后删掉了 <code>build_blend.py</code> 用到的 <code>Material.shadow_method</code>，<code>BLENDER_EEVEE</code> 引擎名也改了，装当前版会报 AttributeError / enum 错误、每次都「blend 未生成」，而 <code>export_full</code> 把 Blender 的 stderr 丢掉（<code>2&gt;$null</code>），通常一行堆栈都看不到，只剩一句 throw，很难定位。到 blender.org 的 LTS 下载页取 3.6.x，解压到任意位置后用 <code>-BlenderExe</code> 指定；只用内置 FBX 导入器，<code>--factory-startup</code>，不装 addon（<code>collect_manifest.py</code> 同样在 3.6 无头下跑）</td></tr>
      <tr><td>文件名清单</td><td><code>E:\tools\doa6\cethleann\filelist-DeadOrAlive6-rdb.csv</code> + <code>filelist-RDBExt-rdb.csv</code></td><td>到 Cethleann 项目的 GitHub Releases 下载 1.2.1 发行包，<b>只需要其中这两个 CSV</b>（KTID→名字/扩展名表），放到 <code>extract_rdb.py</code> 里 <code>CETHLEANN_DIR</code> 指向的目录（默认 <code>E:\tools\doa6\cethleann</code>），套件其余组件不要用（见「坑」）；<code>g1m_matmap.py</code> 另有一个写死的 <code>CSV</code> 常量指向同一份 <code>filelist-DeadOrAlive6-rdb.csv</code>。缺 CSV 的症状：<code>--list</code> 输出全是 8 位十六进制名、任何 <code>--filter</code> 都匹配不到；<code>g1m_matmap.py</code> 直接 FileNotFoundError→「matmap 失败」</td></tr>
      <tr><td>输出根</td><td><code>D:\doa6_exports</code></td><td><code>-OutRoot</code>（一键脚本）/ <code>-OutputRoot</code>（export_character）；mod 原件约定放 <code>D:\doa_mods\doa6\</code></td></tr>
    </table>
    <p>不需要任何 AES key 或自设环境变量；mod zip 会解到 <code>%TEMP%\doa6mod_&lt;zip 名&gt;\</code>。.ps1 跑在 Windows PowerShell 5.1，文件要保持 UTF-8 with BOM。</p>
    <p><b>首次部署</b>：新机器最省事的做法是把工具装到表中的默认路径。否则必须改脚本里的默认值，因为 <code>export_full.ps1</code> / <code>export_nude_mod.ps1</code> 调用 <code>export_character.ps1</code> 时只传 <code>-OutputRoot</code> 与 <code>-Force</code>，<b>不转发</b> <code>-GameRoot -PythonExe -NoesisExe</code>——哪怕给一键脚本传了覆盖参数，第①步仍用写死的默认值，直接 throw「not found: …\CharacterEditor.rdb」或找不到 python.exe。要改的地方：
      ① <code>export_character.ps1</code> 的 param() 里 <code>$GameRoot / $PythonExe / $NoesisExe</code>；
      ② <code>export_full.ps1</code>、<code>export_nude_mod.ps1</code> 的 param() 里 <code>$PythonExe / $NoesisExe / $BlenderExe</code>（export_nude_mod 还有 <code>$GameRoot</code>），<code>import_mod.ps1</code> 的 <code>$Noesis64 / $Noesis32</code>——这几个也可以每次都传参；
      ③ <code>extract_rdb.py</code> 的 <code>CETHLEANN_DIR</code>；④ <code>g1m_matmap.py</code> 的 <code>CSV</code> 与 <code>SINGLETON_DBS</code>。</p>

    <h3>第零步 · 一次性解出对象库 _objdb</h3>
    <p>第一次跑 .ps1 前，在 PowerShell 5.1 里执行一次 <code>Set-ExecutionPolicy -Scope CurrentUser RemoteSigned</code>（或每次用 <code>powershell -ExecutionPolicy Bypass -File …</code> 启动）；新装 Windows 的执行策略是 Restricted，否则会报「因为在此系统上禁止运行脚本」。
      下面的 python 请用你准备给 <code>-PythonExe</code> 的那个解释器（先 <code>$py = "…\python.exe"</code>，再 <code>&amp; $py extract_rdb.py …</code>，脚本内部也是这样走完整路径、从不依赖 PATH）；直接敲 <code>python</code> 在 Win11 上没进 PATH 时只会弹出商店存根，什么都不报、什么都不出。</p>
    <p>精确材质链是 g1m 材质槽 → 部件 <code>.ktid</code> → TexContext 对象 → g1t 名字，中间要查两份 <code>kidssingletondb</code>，
      它们在 <code>KIDSSystemResource.rdb</code> 里，<code>g1m_matmap.py</code> 只认写死的 <code>D:\doa6_exports\_objdb\</code>：</p>
    <pre>cd &lt;你的仓库路径&gt;\scripts\doa6                              # 例如 E:\code\othercode\ripper_tpose\scripts\doa6
$py = "D:\openclaw\python\python.exe"                          # 换成你要传给 -PythonExe 的解释器
$game = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6"
&amp; $py extract_rdb.py "$game\KIDSSystemResource.rdb" --list --filter "*Editor.kidssingletondb"   # 应只列出 CharacterEditor / MaterialEditor / LuminousEditor 三条
&amp; $py extract_rdb.py "$game\KIDSSystemResource.rdb" -o D:\doa6_exports\_objdb --filter "*Editor.kidssingletondb" --flat</pre>
    <div class="note"><b><code>--flat</code> 必须加</b>，否则多一层子目录。<b>过滤条件要收窄成 <code>*Editor.kidssingletondb</code></b>：<code>--filter</code> 拿整个条目名做 fnmatch，写成 <code>*.kidssingletondb</code> 会命中 KIDSSystemResource 里 347 个舞台/UI 单例库（<code>Field_S0199PIR.stage.decal.kidssingletondb</code>、<code>Layout_option_brightness.kidssingletondb</code>…），<code>--list</code> 刷几百行、提取也慢上几十倍。跑完核对 <code>D:\doa6_exports\_objdb\</code> 下确实出现 <code>CharacterEditor.kidssingletondb</code> 与 <code>MaterialEditor.kidssingletondb</code>（同时会多出一个用不上的 <code>LuminousEditor.kidssingletondb</code>，留着无妨；名字不是十六进制）——若落盘的是 <code>&lt;8 位十六进制&gt;.kidssingletondb</code>，说明 <code>filelist-DeadOrAlive6-rdb.csv</code> 没被读到，先修 <code>CETHLEANN_DIR</code>，否则与 <code>g1m_matmap.py</code> 写死的两个文件名对不上。
      <code>g1m_matmap.py</code> 对缺失的对象库<b>不报错</b>（路径不存在就 continue），只会把贴图解析成十六进制假名——症状是脚本一路 OK、blend 全白模。改了 <code>-OutRoot</code> 也要保留这个目录，或改 <code>SINGLETON_DBS</code> 常量。
      .ps1 靠 <code>$MyInvocation</code> 找同目录的 .py，所以也可以不 cd、直接用完整路径调用；本页的 <code>.\</code> 写法默认已 cd 到这里。</div>

    <h3>角色由三个部件组成 · 怎么找 ID</h3>
    <table>
      <tr><th>部件</th><th>条目名</th><th>所在 RDB</th></tr>
      <tr><td>服装 + 身体</td><td><code>&lt;角色&gt;_COS_NNN</code></td><td>CharacterEditor.rdb（g1m + ktid/mtl 配套）</td></tr>
      <tr><td>脸 / 头发</td><td><code>&lt;角色&gt;_FACE_NNN</code> / <code>&lt;角色&gt;_HAIR_NNN</code></td><td>CharacterEditor.rdb</td></tr>
      <tr><td>贴图</td><td><code>MPR_Muscle_Character_&lt;角色&gt;&lt;COS&gt;&lt;NNN&gt;_&lt;部位&gt;_kids&lt;通道&gt;.g1t</code></td><td>MaterialEditor.rdb；名字去掉下划线，脚本自动换算</td></tr>
    </table>
    <pre>.\export_character.ps1 -List                                                             # 全部 1536 个 g1m
&amp; $py extract_rdb.py "$game\CharacterEditor.rdb" --list --types g1m --filter "KAS_*"        # 一个角色有哪些编号
&amp; $py extract_rdb.py "$game\MaterialEditor.rdb" --list --types g1t --filter "*KASCOS001_*"   # 一套服装有哪些贴图</pre>
    <p>代号：HON=Honoka、KAS=Kasumi、AYA=Ayane、MAR=Marie、HTM=Hitomi、LEI=Leifang、TIN=Tina、MOM=Momiji、HEL=Helena、
      LIS=Lisa、KOK=Kokoro、PHF=Phase 4、CRI=Christie、MIL=Mila、NYO=Nyotengu、RAC=Rachel，客串 MAI / NIC / SNK，SKD=Tamaki（DLC）。<code>COS_000~0xx</code> 本体服装，<code>COS_10x</code> 起多为 DLC；
      客串角色的 <code>COS_000~003</code> 是无 ktid 的占位体，正装从 <code>004</code> 起。通道后缀 alb=Albedo、nmh=Normal、occ=AO、rfr=Roughness、emi=自发光，组装只接 alb/nmh。</p>

    <h3>快速路径 · export_full.ps1</h3>
    <pre>.\export_full.ps1 KAS                          # COS_001+HAIR_001+FACE_001 → _blends\KAS_full.blend
.\export_full.ps1 MOM -Cos 102 -Label MOM_DLC  # 换编号（-Hair/-Face 同理，前导零保留）
.\export_full.ps1 NIC -Cos 004 -Label NIC_Nico # 客串跳过占位体
.\export_full.ps1 AYA -Force                   # 覆盖重做：三个部件目录先删后重提</pre>
    <p>内部：① <code>export_character.ps1</code> 提三部件（g1m→FBX，g1t→DDS）→ ② 每部件 <code>g1m_matmap.py</code> 写 <code>matmap.json</code>
      → ③ 只把用到的 alb/nmh DDS 经 Noesis 转成 <code>_png\</code>（Blender 读不了 BC7）→ ④ <code>build_blend.py</code> 导入三个 FBX、按 matmap 挂
      Albedo+Alpha（HASHED）与 Normal、逐图打包、存 blend、EEVEE 渲 900×1400 预览。产物 <code>_blends\&lt;Label&gt;.blend</code> + <code>&lt;Label&gt;_preview.png</code>，35~60MB。
      同名 blend 已存在则 SKIP；部件目录已存在也复用，同角色第二套服装只多提一个 COS。
      成功时最后一行是 <code>OK &lt;Label&gt; : …\_blends\&lt;Label&gt;.blend (NN MB)</code>，部件目录与 <code>_blends\</code> 都自动创建。单角色首跑要几分钟（在 45GB 的 MaterialEditor 里定向抽取，再把一套服装 80~150 余张 g1t 逐张经 Noesis 转 DDS），抽取那段长时间没输出不是卡死，别中断——中断会留下半成品部件目录，下次被 SKIP（只看目录存在，不校验完整性），要 <code>-Force</code> 重来。</p>

    <h3>批量路径</h3>
    <p>脚本一次只收一个角色，也不写共享清单，批量就是循环，不用分片：</p>
    <pre>foreach ($c in "KAS","AYA","HON","MOM") { .\export_full.ps1 $c -Label "$($c)_001" }
foreach ($n in "001","002","102") { .\export_full.ps1 KAS -Cos $n -Label "KAS_COS_$n" }   # 同角色多套，HAIR/FACE 复用</pre>

    <h3>分步路径 · 出错时单独重跑</h3>
    <pre>$o = "D:\doa6_exports"
$py = "D:\openclaw\python\python.exe"                                   # 同第零步，换成你的解释器
.\export_character.ps1 MOM_COS_001,MOM_HAIR_001,MOM_FACE_001            # ① 逗号分隔；-NoTextures 跳过贴图，-NoConvert 不调 Noesis
&amp; $py g1m_matmap.py $o\MOM_COS_001\MOM_COS_001.g1m $o\MOM_COS_001\MOM_COS_001.ktid -o $o\MOM_COS_001\matmap.json   # ② HAIR/FACE 同理
New-Item -ItemType Directory -Force $o\MOM_COS_001\_png                                                         # ③ _png 要自己先建
E:\tools\noesisv\Noesis64.exe ?cmode $o\MOM_COS_001\_textures\&lt;x&gt;.dds $o\MOM_COS_001\_png\&lt;x&gt;.png                # ③ 逐张；&lt;x&gt; = matmap.json 里 submeshes[].textures[] 中 channel 为 alb/nmh 的 name 去掉 .g1t，其它通道不用转
&amp; "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" --background --factory-startup --python build_blend.py -- $o\_blends\MOM.blend $o\_blends\MOM_preview.png $o\MOM_COS_001 $o\MOM_HAIR_001 $o\MOM_FACE_001   # ④ 预览写 - 则不渲；blender 不在 PATH，用给 -BlenderExe 的完整路径，带空格要 &amp; "…"</pre>

    <h3>mod 变体 · export_nude_mod.ps1</h3>
    <div class="note"><b>官方内容没有 nude</b>（逐条目核实过），裸模只能来自 REDELBE Layer2 社区 mod：GameBanana（game id <code>6966</code>，可直连，多为微比基尼/走光级）；
      全裸整合包在 LoversLab / DeviantArt，需登录手动下。</div>
    <p>喂 zip 或已解压目录（内含 <code>Character\*.g1m</code> + <code>Material\*.g1t</code>）。mod 给什么部件就换什么，缺的用官方 <code>COS_001 / FACE_001 / HAIR_001</code> 补齐；紫色徽标的卡片就是这类。<b>注意：判据是官方部件目录里有没有 <code>matmap.json</code>，没有就用 <code>-Force</code> 调 <code>export_character.ps1</code>，把整个 <code>&lt;OutRoot&gt;\&lt;部件&gt;\</code> 删掉重提</b>（<code>_textures</code>、<code>_png</code> 和手工补进去的贴图一起没，再从 45GB 的 MaterialEditor 里重抽几分钟）——只跑过下面「分步路径」第①步、或用 <code>-NoTextures/-NoConvert</code> 导过、或被中断留下的半成品目录都算「没有 matmap.json」，先用 <code>export_full.ps1 &lt;CHR&gt;</code> 或分步路径②③把官方部件做完再来喂 mod。
      脚本只认 <code>.zip</code>（正则 <code>\.zip$</code>）；GameBanana / LoversLab 上大量是 .rar / .7z，要先用 7-Zip 解压成目录再喂（仓库记录里用的是便携 <code>E:\tools\7zr.exe</code>），否则会被当成目录去找 g1m，报「mod 里没有 g1m」或「找不到路径」而不是「不支持的压缩格式」。
      mod 目录里必须有 <code>Material</code> 子目录（否则「mod 里没有 Material 目录」），g1m 文件名必须是 <code>&lt;CHR&gt;_&lt;COS|HAIR|FACE&gt;_&lt;NNN&gt;.g1m</code>（否则「mod 的 g1m 都不是 … 命名」）。
      <b>每跑一次都会先把 <code>%TEMP%\doa6mod_&lt;zip 名&gt;\</code> 与 <code>&lt;OutRoot&gt;\&lt;Label&gt;_cos / _face / _hair</code> 整个删掉重建，并覆盖同名 blend</b>（没有 <code>-Force</code>，也没有 SKIP），所以同一个 <code>-Label</code> 重跑就是静默覆盖，别把手工改过的东西放在这些目录名下。</p>
    <pre>.\export_nude_mod.ps1 D:\doa_mods\doa6\_zips\xxx_nude_helena.zip -Label HEL_Helena_Nude   # -Chr 可省，按 g1m 名推断
.\export_nude_mod.ps1 D:\doa_mods\doa6\_zips\397318_hair_loose_hair_momiji_1.zip           # 发型 mod，-Label 缺省由 zip 名生成
.\export_nude_mod.ps1 "D:\doa_mods\doa6\_extract\...\Moka (Inner) Bikini Lisa Body Swap" -Chr KOK -Label KOK_MokaInner_Bikini -Cos 030 -Face AYA_FACE_001
.\export_nude_mod.ps1 D:\mods\ayane_malf.zip -Label AYA_Malf -Assign "3=f01,5=body"      # 纠正启发式
.\import_mod.ps1 D:\doa_mods\doa6\_zips                                                   # 只要 FBX+DDS 不组装 → D:\doa_mod_fbx\</pre>
    <table>
      <tr><th>材质路线</th><th>触发条件</th><th>可靠性</th></tr>
      <tr><td>A 精确</td><td>部件编号本机游戏里有（<code>HEL_COS_001</code>…）→ 原版 ktid 链，mod 自带 <code>&lt;id&gt;.ktid</code> 时优先</td><td>一次到位；仍有网格没 albedo 时自动改走 B</td></tr>
      <tr><td>B 启发式</td><td>编号是未装 DLC 位（<code>MOM_COS_105</code>…）→ <code>mod_matmap.py</code> 按顶点数猜部位</td><td>多数一次对；皮肤/衣服互换时把输出的 <code>assign: {3: 'body', 5: 'f01'}</code> 对调成 <code>-Assign</code> 重跑（只作用于 COS）</td></tr>
    </table>
    <p>合集包（如 Moka Pack）解压后把 <code>REDELBE\Layer2\&lt;子目录&gt;</code> 逐个喂，<code>mod.ini</code> 的 <code>work=KOK_COS_030</code> / <code>[Face] work=AYA_FACE_001</code> 对应 <code>-Cos 030 -Face AYA_FACE_001</code>。</p>

    <h3>参数表</h3>
    <table>
      <tr><th>脚本 · 参数</th><th>作用</th></tr>
      <tr><td><code>export_full.ps1 &lt;CHR&gt;</code></td><td>三字母代号，必填。<code>-Cos/-Hair/-Face</code> 编号（默认 <code>001</code>）；<code>-Label</code> 文件名（默认 <code>&lt;CHR&gt;_full</code>）；<code>-Force</code> 覆盖并重提部件；<code>-NoPreview</code> 不渲图</td></tr>
      <tr><td><code>-OutRoot -PythonExe -NoesisExe -BlenderExe</code></td><td>覆盖默认路径。<b>没有 <code>-GameRoot</code></b>，而且 <code>-PythonExe -NoesisExe</code> 也不转发给 export_character.ps1——游戏/工具装在别处要改 <code>export_character.ps1</code> param() 里 <code>$GameRoot / $PythonExe / $NoesisExe</code> 的默认值（见「首次部署」）</td></tr>
      <tr><td><code>export_nude_mod.ps1 &lt;zip|目录&gt;</code></td><td>必填；无 -Force，每次都重建 <code>&lt;Label&gt;_cos/_face/_hair</code> 与 blend。<code>-Chr</code>/<code>-Label</code> 可省；<code>-Cos/-Hair/-Face</code> 补位官方件的编号或完整名（<code>AYA_FACE_001</code>，body-swap 用别人的脸）；<code>-Assign "材质号=部位,…"</code>；<code>-NoPreview</code>；<code>-OutRoot -GameRoot -PythonExe -NoesisExe -BlenderExe</code></td></tr>
      <tr><td><code>export_character.ps1 &lt;名,名&gt;</code></td><td>单部件；<code>-List</code>；<code>-NoTextures</code>；<code>-NoConvert</code>；<code>-Force</code> 删掉重建部件目录；<code>-GameRoot -OutputRoot -PythonExe -NoesisExe</code></td></tr>
      <tr><td><code>extract_rdb.py &lt;x.rdb&gt;</code></td><td><code>--list</code> 只列；<code>-o 目录</code> 提取；<code>--filter</code> fnmatch 不分大小写；<code>--types g1m,g1t,ktid,…</code>；<code>--flat</code> 不按扩展名分子目录</td></tr>
      <tr><td><code>mod_matmap.py … --key</code> / <code>import_mod.ps1</code></td><td>多部件 mod 只认 <code>_&lt;KEY&gt;_</code> 的 g1t（一键脚本自动传）/ <code>-OutRoot</code>（默认 <code>D:\doa_mod_fbx</code>）<code>-KeepExtracted</code>（保留解压目录，默认转完即删）<code>-Noesis64 -Noesis32</code>；zip 解压临时目录写死为 <code>D:\doa_mods\_extract_tmp</code>，<b>同名子目录会先被整个删掉再解压</b>（无 D: 盘要改脚本里的 <code>$work</code>）；DOA5LR 的 TMC mod 也能转，走 <code>-Noesis32</code>（默认 <code>E:\tools\noesisv\Noesis.exe</code>）且要给 32 位 Noesis 装 <code>doa5pc_custom.py</code> 插件</td></tr>
    </table>

    <h3>产物目录</h3>
    <pre>D:\doa6_exports\
  _objdb\CharacterEditor.kidssingletondb  MaterialEditor.kidssingletondb  LuminousEditor.kidssingletondb   # 只用前两个
  &lt;CHR&gt;_COS_NNN\  &lt;CHR&gt;_HAIR_NNN\  &lt;CHR&gt;_FACE_NNN\      # 官方部件：&lt;部件&gt;.g1m/.ktid/.mtl  &lt;部件&gt;.fbx  matmap.json
      _textures\*.dds（全部通道）  _png\*.png（只有 alb/nmh）
  &lt;Label&gt;_cos\  &lt;Label&gt;_face\  &lt;Label&gt;_hair\             # mod 部件暂存，结构同上
  _blends\&lt;Label&gt;.blend  &lt;Label&gt;_preview.png  &lt;Label&gt;.log  # 成品；.log 只有 mod 脚本写
  doa6_models_manifest.json  _gallery\thumbs\&lt;Label&gt;.jpg     # 画廊用，不进仓库
  README.md                                                   # 手写的产物索引与 mod 对照表
D:\doa_mods\doa6\_zips\ _extract\ _patched\                   # mod 原件 / 解压的合集包 / 手工补贴图的副本
D:\doa_mod_fbx\&lt;mod&gt;\*.fbx + _textures\*.dds                  # import_mod.ps1</pre>
    <p>blend 里三个部件各留一副骨架（<code>&lt;部件&gt;_armature</code>，未合并），网格名 <code>&lt;部件目录名&gt;_sm&lt;N&gt;</code>，画廊靠它归类部件、判定 mod 变体。</p>

    <h3>容易踩的坑</h3>
    <table>
      <tr><th>症状</th><th>原因</th><th>处理</th></tr>
      <tr><td>Noesis 一开 g1m 就崩、无提示</td><td>Cethleann.DataExporter 解的 DOA6：zlib 每块只读一次，1536 个 g1m 里 1300 个在 ~80% 截断</td><td>只用 <code>extract_rdb.py</code>，Cethleann 只借 CSV</td></tr>
      <tr><td>blend 全白模，脚本却 OK</td><td><code>_objdb</code> 没解出 / 打开的是部件目录里的裸 FBX / 改了 <code>-OutRoot</code> 但 g1m_matmap 仍指向 <code>D:\doa6_exports\_objdb</code></td><td>补第零步 / 打开 <code>_blends\</code> 的 blend / 改 <code>SINGLETON_DBS</code></td></tr>
      <tr><td>「部件缺 FBX：XXX_COS_002」</td><td>编号不存在，或客串 NIC/MAI/SNK 撞上 <code>COS_000~003</code> 占位体</td><td><code>--list --filter "XXX_*"</code> 查编号；客串从 <code>-Cos 004</code> 起</td></tr>
      <tr><td>Phase 4 头发白模</td><td>PHF 的 <code>HAIR_001</code> 在 MaterialEditor 里确实没贴图</td><td>换别的 <code>-Hair</code> 编号</td></tr>
      <tr><td>mod 皮肤和衣服贴图互换</td><td>路线 B 猜错</td><td>按打印的 <code>assign</code> 对调，<code>-Assign</code> 重跑</td></tr>
      <tr><td>「blend 未生成」</td><td>Blender 端报错；mod 脚本把完整输出写进 <code>_blends\&lt;Label&gt;.log</code> 并打印尾部，<code>export_full</code> 不留 log、还把 stderr <code>2&gt;$null</code> 丢掉了</td><td>看 log（mod 脚本）；<code>export_full</code> 这边什么堆栈都没有，要按「分步路径」④ 手工重跑 <code>build_blend.py</code> 才看得到；常见是部件目录缺 matmap.json 或 FBX；Blender 装成 4.2+ 也是这个症状（<code>shadow_method</code> AttributeError），换 3.6</td></tr>
      <tr><td>mod 变体无头，只有警告</td><td>角色是未装 DLC（SKD Tamaki），本机没有 FACE/HAIR</td><td>装 DLC，否则只出 mod 自带部件</td></tr>
      <tr><td>mod 皮肤没贴图</td><td>mod 不带 <code>*_body_kidsalb/nmh</code>（如 Ayane Fachan2）</td><td>从同角色别的 mod 借这两张 g1t 放进副本（<code>_patched\</code>）重跑</td></tr>
      <tr><td><code>-Force</code> 后 matmap/_png 没了</td><td><code>export_character.ps1 -Force</code> 整个删掉重建部件目录</td><td>一键脚本会重生成；手工时按序重跑 ②③</td></tr>
      <tr><td><code>--filter "HON_*"</code> 找不到贴图</td><td>MaterialEditor 里贴图名不带下划线</td><td>用 <code>*HONCOS001_*</code></td></tr>
      <tr><td>GameBanana 的 zip 解压报错</td><td>大文件被截断（Moka 108MB 只到 18MB）</td><td><code>curl.exe -sL --retry 3 -o</code> 重下（PowerShell 5.1 里 <code>curl</code> 是 Invoke-WebRequest 的别名，要写 <code>curl.exe</code>）</td></tr>
      <tr><td>.ps1 报 missing terminator</td><td>存成了无 BOM 的 UTF-8，PowerShell 5.1 按 GBK 解析吞掉引号</td><td>UTF-8 with BOM 重存，字符串字面量保持 ASCII</td></tr>
    </table>

    <h3>并行与耗时</h3>
    <p>不用分片，开几个 PowerShell 窗口各跑一组角色即可。实测 19 名女性角色 19 路并行约 4 分钟全完成；45 个 mod 变体三路并行，每个 11~32 秒（官方部件已在时；本页画廊收录其中 44 个）。
      <b>同一角色不要跨窗口并行</b>——多套服装共用 HAIR/FACE 部件目录，会互相 SKIP 到半成品；同角色的 mod 先跑一次 <code>export_full.ps1 &lt;CHR&gt;</code> 备好官方部件。</p>

    <h3>重新生成本页</h3>
    <pre>cd &lt;你的仓库路径&gt;                                                     # 例如 E:\code\othercode\ripper_tpose
&amp; "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" --background --factory-startup --python scripts\doa6\html\collect_manifest.py -- D:\doa6_exports
&amp; $py scripts\doa6\html\make_gallery.py --source-root D:\doa6_exports     # --force 重建全部缩略图；$py 同第零步</pre>
    <p>第一步用 Blender 逐个打开 <code>_blends\*.blend</code> 统计网格/骨架/材质/贴图、按网格名判定官方或 mod，写 <code>D:\doa6_exports\doa6_models_manifest.json</code>（位置参数 = 导出根、manifest 路径）；
      第二步读 manifest，把预览图缩成 720 宽 JPEG 放进 <code>D:\doa6_exports\_gallery\thumbs\</code>，重写脚本旁的 <code>index.html</code>（<code>--manifest / --out / --thumb-dir</code> 可改）。<b>是整页覆盖写，不是增量</b>：页面正文连同本附录都硬编码在 <code>make_gallery.py</code> 的 <code>PAGE_TEMPLATE</code> 里，只改 <code>index.html</code> 的话下次重跑就被模板里那份旧的覆盖掉（旧附录还写着 <code>export_full.ps1</code> 根本没有的 <code>-List</code>）；改模板时注意它是 <code>str.format</code> 的非 raw 字符串，字面量大括号和反斜杠都要写两遍。
      <b>缩略图与 manifest 都留在导出根下，不进仓库</b>；页面链接全是本机 <code>file://</code>，换机器要重跑。</p>

    <h3>例外与已知限制</h3>
    <ul>
      <li>官方资源没有 nude；裸模全靠社区 mod，质量以 mod 为准（<code>AYA_Ayane_TropicalTune2</code> 身体三角面被作者删光，只剩顶点）。</li>
      <li><code>SKD_Tamaki_*</code> 六个变体无脸无头发：Tamaki 是未安装的 DLC。PHF（Phase 4）<code>HAIR_001</code> 无贴图，白发。</li>
      <li>材质只接 Albedo（含 Alpha）和 Normal；AO / Roughness / 自发光的 DDS 在 <code>_textures\</code> 里但没连进节点。</li>
      <li>三副骨架同源对齐但未合并；G1M→FBX 的骨骼无名字，要带名骨架需在 Noesis GUI 配合 <code>Oid.bin</code>（ProjectG1M 的 bLoadG1MOid 选项）手动转。</li>
      <li>本批官方条目只是每个角色的默认服装（<code>COS_001</code>，客串 <code>004</code>）；其它服装按「批量路径」追加。</li>
    </ul>
  </section>
"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DOA6 模型导出总览</title>
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
  <h1>DOA6 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{characters}</b><span>覆盖角色</span></div>
    <div class="stat"><b>{mods}</b><span>mod 变体</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索角色名或路径…（按 / 聚焦）">
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
    manifest_path = args.manifest or os.path.join(source_root, "doa6_models_manifest.json")
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
    print("models      : %d（mod 变体 %d）" % (len(models), sum(1 for m in models if m["kind"] == "mod")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
