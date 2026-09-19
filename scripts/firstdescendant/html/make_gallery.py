# -*- coding: utf-8 -*-
"""把 The First Descendant 的导出产物做成一页可浏览的 HTML 画廊。

读 ``tfd_models_manifest.json``（由 collect_manifest.py 从 blend\\<模型>\\build.log 汇总），
把每张预览图缩成 JPEG 缩略图（正身一张、脸一张小的），输出自包含的 ``index.html``
到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\tfd_exports --force
"""

import argparse
import datetime
import html
import json
import os
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 720
FACE_WIDTH = 240
THUMB_QUALITY = 82
PAGE_NAME = "index.html"

KIND_LABELS = {"descendant": "后裔", "skin": "皮肤", "monster": "怪物", "boss": "Boss",
               "npc": "NPC", "weapon": "武器", "accessory": "配饰", "fellow": "宠物", "vehicle": "载具"}
KIND_ORDER = ("descendant", "skin", "monster", "boss", "npc", "weapon", "accessory", "fellow", "vehicle")
SEX_LABELS = {"female": "女性体型", "male": "男性体型", "": "无体型（怪 / 物件）"}
MAT_LABELS = {"skin": "皮肤", "hair": "头发", "eye": "眼球", "eyebrow": "眉毛", "eyelash": "睫毛",
              "cloth": "布料/装甲", "glass": "面罩玻璃", "clear": "透明壳", "teeth": "牙齿"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\tfd_exports", help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None, help="manifest 路径（默认 <导出根>\\tfd_models_manifest.json）")
    p.add_argument("--out", default=None, help="输出 HTML（默认本脚本旁的 index.html）")
    p.add_argument("--thumb-dir", default=None, help="缩略图目录（默认 <导出根>\\_gallery\\thumbs）")
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


def thousands(n):
    return "{:,}".format(int(n or 0))


def file_uri(path):
    try:
        return Path(path).as_uri()
    except (ValueError, OSError):
        return ""


def build_thumb(preview_path, thumb_path, width, force):
    if not preview_path or not os.path.isfile(preview_path):
        return None
    if (not force and os.path.isfile(thumb_path)
            and os.path.getmtime(thumb_path) >= os.path.getmtime(preview_path)):
        return thumb_path
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    with Image.open(preview_path) as image:
        image = image.convert("RGB")
        if image.width > width:
            height = max(1, round(image.height * width / image.width))
            image = image.resize((width, height), Image.LANCZOS)
        image.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return thumb_path


def collect(manifest_path, thumb_dir, force):
    with open(manifest_path, encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    models = []
    for entry in manifest.get("results", []):
        label = entry.get("label") or ""
        thumb = build_thumb(entry.get("preview"), os.path.join(thumb_dir, label + ".jpg"), THUMB_WIDTH, force)
        face_thumb = build_thumb(entry.get("facePreview"), os.path.join(thumb_dir, label + "_face.jpg"),
                                 FACE_WIDTH, force)
        models.append({
            "label": label,
            "name": entry.get("name") or "",
            "kind": entry.get("kind") or "descendant",
            "char": entry.get("char") or "",
            "sex": entry.get("sex") or "",
            "ultimate": bool(entry.get("ultimate")),
            "blend": entry.get("blend") or "",
            "out_dir": entry.get("outDir") or "",
            "preview": entry.get("preview") or "",
            "face": entry.get("facePreview") or "",
            "thumb": thumb or "",
            "face_thumb": face_thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "texture_bytes": entry.get("textureBytes") or 0,
            "parts": list(entry.get("parts") or []),
            "part_details": list(entry.get("partDetails") or []),
            "packages": list(entry.get("packages") or []),
            "vertices": entry.get("vertices") or 0,
            "faces": entry.get("faces") or 0,
            "bones": entry.get("bones") or 0,
            "meshes": entry.get("meshes") or 0,
            "morphs": entry.get("morphs") or 0,
            "materials": entry.get("materials") or 0,
            "material_kinds": list(entry.get("materialKinds") or []),
            "material_details": list(entry.get("materialDetails") or []),
            "textures": entry.get("textures") or 0,
            "notes": list(entry.get("notes") or []),
            "warnings": list(entry.get("warnings") or []),
        })
    models.sort(key=lambda m: (KIND_ORDER.index(m["kind"]) if m["kind"] in KIND_ORDER else 9,
                               m["char"].lower(), m["label"].lower()))
    return manifest, models


def render_card(model):
    esc = html.escape
    thumb_uri = file_uri(model["thumb"])
    preview_uri = file_uri(model["preview"])
    blend_uri = file_uri(model["blend"])
    face_uri = file_uri(model["face"])
    face_thumb_uri = file_uri(model["face_thumb"])

    badges = '<span class="badge badge-kind">%s</span>' % esc(KIND_LABELS.get(model["kind"], model["kind"]))
    if model["sex"]:
        badges += '<span class="badge badge-sex badge-%s">%s</span>' % (
            esc(model["sex"]), "女" if model["sex"] == "female" else "男")
    if model["ultimate"]:
        badges += '<span class="badge badge-mod" title="Ultimate 变体（U 编号）">Ultimate</span>'
    if model["morphs"]:
        badges += '<span class="badge badge-mod" title="面部 morph target（形态键）">%d morph</span>' % model["morphs"]
    if model["notes"]:
        badges += '<span class="badge badge-mod" title="%s">socket 配件</span>' % esc("; ".join(model["notes"]))
    if model["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">告警 %d</span>' % (
            esc("; ".join(model["warnings"])), len(model["warnings"]))

    search_blob = esc(" ".join([model["label"], model["name"], model["kind"], model["char"],
                                " ".join(model["parts"]), " ".join(model["material_kinds"]),
                                " ".join(model["packages"]), model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    avatar = ('<a class="avatar" href="%s" target="_blank" rel="noopener" title="点击看脸部原图">'
              '<img loading="lazy" src="%s" alt="%s 脸部"></a>'
              % (esc(face_uri), esc(face_thumb_uri), esc(model["label"]))) if face_thumb_uri else ""

    mat_kinds = " · ".join(MAT_LABELS.get(k, k) for k in model["material_kinds"]) or "-"
    mat_title = esc("; ".join("%s = %s" % (d.get("material", ""), d.get("kind", ""))
                              for d in model["material_details"]))
    parts_title = esc("; ".join("%s %s 顶点 / %s 骨 / %d 槽" % (
        d.get("name", ""), thousands(d.get("vertices", 0)), thousands(d.get("bones", 0)), d.get("slots", 0))
        for d in model["part_details"]))
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-sex="{sex}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener" title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">{avatar}
            <div class="titletext"><h3>{label}</h3><div class="badges">{badges}</div></div>
          </div>
          <dl>
            <dt>说明</dt><dd class="prose">{name}</dd>
            <dt>部件</dt><dd title="{parts_title}">{parts}</dd>
            <dt>规格</dt>
            <dd>{vertices} 顶点 · {faces} 面 · {bones} 骨骼 · {meshes} 网格 · {size}</dd>
            <dt>材质</dt>
            <dd title="{mat_title}">{materials} 个 · {textures} 张贴图（{tex_size}）<br>{mat_kinds}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{out_dir}" title="复制整个目录路径">复制目录</button></dd>
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]), sex=esc(model["sex"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, avatar=avatar, label=esc(model["label"]),
           badges=badges, name=esc(model["name"] or "-"),
           parts=esc(" · ".join(model["parts"]) or "-"), parts_title=parts_title,
           vertices=thousands(model["vertices"]), faces=thousands(model["faces"]),
           bones=model["bones"], meshes=model["meshes"], size=human_size(model["blend_size"]),
           materials=model["materials"], textures=model["textures"],
           tex_size=human_size(model["texture_bytes"]), mat_kinds=esc(mat_kinds), mat_title=mat_title,
           blend_uri=esc(blend_uri), blend=esc(model["blend"]), out_dir=esc(model["out_dir"]))


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] + m["texture_bytes"] for m in models)
    descendants = sum(1 for m in models if m["kind"] == "descendant")
    females = sum(1 for m in models if m["kind"] == "descendant" and m["sex"] == "female")
    warned = sum(1 for m in models if m["warnings"])
    kinds = [k for k in KIND_ORDER if any(m["kind"] == k for m in models)]
    per_sex = {}
    for m in models:
        per_sex[m["sex"]] = per_sex.get(m["sex"], 0) + 1
    sex_options = "".join('<option value="%s">%s (%d)</option>' % (esc(s), esc(SEX_LABELS.get(s, s)), n)
                          for s, n in sorted(per_sex.items()))
    chips = "".join('<button class="chip" data-kind="%s">%s (%d)</button>'
                    % (esc(k), esc(KIND_LABELS[k]), sum(1 for m in models if m["kind"] == k)) for k in kinds)
    return PAGE_TEMPLATE.format(
        appendix=APPENDIX_HTML,
        generated=esc(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        source_root=esc(source_root), total=len(models), descendants=descendants, females=females,
        size=human_size(total_bytes), warned=warned, chips=chips, sex_options=sex_options,
        cards="".join(render_card(m) for m in models))


APPENDIX_HTML = r"""
<section class="appendix">
    <h2>附录 · 手工导出教程</h2>
    <p>脚本都在 <code>scripts\firstdescendant\</code>，产物默认落在 <code>D:\tfd_exports</code>（<code>-ExportRoot</code>）。
      这套和别的游戏最大的不同：<b>贴图全是 UE5 虚拟贴图（Virtual Texture）</b>，UE Viewer 一张都导不出来（日志里写
      <code>it's a virtual texture</code>，Exported 0/0），必须换 CUE4Parse；而 CUE4Parse 解本作<b>任何</b>属性都要一份
      <code>.usmap</code>（包是 unversioned properties），这份映射表在 Nexus 上已被下架，只能从论坛翻。顺序固定：
      装游戏 → 算 AES key → <code>list_models.py</code> 看清单 → <code>export_model.ps1 &lt;模型&gt;</code> 出带贴图的 .blend → 重生成本页。
      <b>以下命令都在 <code>〈仓库〉\scripts\firstdescendant</code> 里跑，每开一个新窗口先 <code>cd</code> 进去。</b></p>

    <h3>前提 · 工具与默认路径</h3>
    <table>
      <tr><th>工具</th><th>脚本默认路径 / 说明</th></tr>
      <tr><td>游戏</td><td>Steam <code>2074920</code>，装在 <code>E:\SteamLibrary\steamapps\common\The First Descendant</code>（<code>-GameRoot</code>）。
        内部代号 <b>M1</b>：容器是 <code>M1\Content\Paks\M1-Windows.{utoc,ucas,pak}</code>（ucas 70 GB），utoc v5 / pak v11 / Oodle /
        <b>目录索引 AES 加密</b>。</td></tr>
      <tr><td>CUE4Parse CLI</td><td><code>E:\tools\cue4parse_cli\cue4parse.exe</code>（<code>-Cue4ParseExe</code>）= joric/CUE4Parse.CLI 0.2.0（CUE4Parse 1.2.2）。
        首次运行会自动下 <code>oodle-data-shared.dll</code> / <code>zlib-ng2.dll</code> / <code>Detex.dll</code> 到 <code>%LOCALAPPDATA%\Temp</code>，拷到 exe 同目录即可长期用
        （这台机器之前根本没有任何 oo2core dll，<code>iostore.py</code> 也靠这个做 Oodle 解压）。GitHub 直连超时的话走本机代理。</td></tr>
      <tr><td>usmap 映射表</td><td><code>E:\tools\tfd\Mappings_2024-07-16_gildor.usmap</code>（<code>-UsmapFile</code>，1.46 MB）。见下面「usmap 从哪来」。</td></tr>
      <tr><td>UE Viewer</td><td><code>E:\tools\umodel_specific\materials\umodel_materials_ue5.exe</code>（<code>-UmodelExe</code>）。
        <b>只</b>用来读材质实例的标量/向量参数（<code>-game=first</code> 出 <code>.props.txt</code>）——它解不了虚拟贴图。</td></tr>
      <tr><td>Blender 3.6.15</td><td><code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code>），须装 <b>io_scene_psk_psa 5.0.6</b>。
        脚本用 <code>--factory-startup</code> 跑并自己 <code>addon_utils.enable</code>，所以不必在偏好里勾选。
        <b>坑</b>：<code>read_factory_settings()</code> 会把刚 enable 的插件又关掉，别调。</td></tr>
      <tr><td>Python 3</td><td><code>pip install cryptography Pillow</code>——前者解 utoc 目录索引，后者出本页缩略图。</td></tr>
    </table>

    <h3>第零步 · 算 AES key（find_aes_key.py，只做一次）</h3>
    <pre>python .\find_aes_key.py --out D:\tfd_exports\_keys\aes_key.txt</pre>
    <p>和 Vindictus 同一个 Nexon 套路：key <b>不是</b>明文躺在 exe 里，而是运行时用 8 条 <code>mov dword [..], imm32</code> 拼出来的，
      找连续 32 字节的工具会空手而回。脚本扫 <code>M1-Win64-Shipping.exe</code> 的 <code>.text</code>，把成串的立即数按顺序拼成候选，
      拿 <code>M1-Windows.pak</code> 加密索引的前 16 字节做 AES-256-ECB 试解，解出挂载点即命中（本机 60 秒，命中点在文件偏移 0x458850B）。
      之后所有脚本按 <code>TFD_AES_KEY</code> 环境变量 → <code>-AesKeyFile</code> 取 key。</p>
    <div class="note">key 只放本地文件或环境变量。仓库、CHANGELOG、本页面、聊天记录里都不要出现。
      （<code>cue4parse.exe</code> 没有 key 文件参数，key 会出现在它的命令行上，本机使用可接受。）</div>

    <h3>第一步 · 看清单（list_models.py）</h3>
    <pre>python .\list_models.py                        # 2067 个模型：id / kind / char / 部件 / 已导 / blend
python .\list_models.py --kind descendant      # descendant|skin|monster|boss|npc|weapon|accessory|fellow|vehicle
python .\list_models.py --char Bunny           # 某后裔的默认装 + 全部皮肤
python .\list_models.py --resolve Viessa --json
python .\list_models.py --raw --path-filter /Monster/UNQ/</pre>
    <p>直接解密 <code>Paks\*.utoc</code> 的 IoStore 目录索引取全部路径，不开任何外部工具。索引只有路径没有类型，所以「网格」靠目录 + 命名判：
      在 <code>/Skel/</code> 或 <code>/MESH/</code> 下、不在 <code>/Material/ /Texture/ /Textuer/ /Anim/ /BP/</code> 里、不以 <code>BP_ ABP_ CIN_</code> 开头、
      不以 <code>_AnimBP _AimOffset _Skeleton _Physics _MI</code> 等结尾。</p>
    <table>
      <tr><th>kind</th><th>容器里的位置</th><th>组成</th></tr>
      <tr><td>descendant（33）</td><td><code>PC/MESH/PRESET/&lt;名字&gt;/PC_&lt;编号&gt;_&lt;A|U&gt;0101</code></td>
        <td>21 个角色 + 12 个 Ultimate（A 标准 / U Ultimate）。<b>默认装就是这一整块合并网格</b>（身体+头+头发+脸，带面部 morph），导出最干净。</td></tr>
      <tr><td>skin（1075）</td><td><code>PC/MESH/&lt;编号&gt;/&lt;A|U&gt;/Skel/SKIN/&lt;类别&gt;/&lt;序号&gt;/..._(BODY|HEAD)</code></td>
        <td>BODY + HEAD 两件 + 该后裔的 Face 三件合成。类别 F / M / MF / CMN / AGT / BOS / CLB / EVO / VAR（Makeup 只有材质，跳过）。</td></tr>
      <tr><td>monster / boss / npc</td><td><code>Monster/(CMN|UNQ|MIN)/</code>、<code>Boss/&lt;id&gt;/</code>、<code>NPC/&lt;id&gt;/MESH/</code></td>
        <td>一个主网格一个模型（id = 网格名，所以 A001 / B001 变体各算一个），同目录 <code>Parts/</code> <code>Separate_Parts/</code> 记作 extras（<code>-IncludeExtras</code> 才并进来）。</td></tr>
      <tr><td>weapon / accessory / fellow / vehicle</td><td><code>Weapon/(RW|MW)/</code>、<code>ACC/&lt;部位&gt;/</code>、<code>Fellow/</code>、<code>Vehicle/</code></td><td>同上</td></tr>
    </table>
    <p><b>女性体型 12 个</b>：Viessa、Bunny、Freyna、Gley、Sharen、Valby、Luna、Hailey、Ines、Serena、Nell、Harris。
      判据是三条数据而不是看脸：骨架里有 <code>Breast_PoseAsset</code>、皮肤在 <code>SKIN/F</code> 类别下、用 F 系动画。</p>

    <h3>第二步 · 一个模型一条命令（export_model.ps1）</h3>
    <pre>.\export_model.ps1 Viessa                 # 后裔默认装
.\export_model.ps1 Bunny_CMN_001          # 一套皮肤（Body + Head 配件 + Face）
.\export_model.ps1 MOB_CMN_1001_A001      # 一只怪
.\export_model.ps1 BOS_1001_A001 -IncludeExtras
.\export_model.ps1 Viessa -Force          # 重做</pre>
    <p>四步，全自动：</p>
    <ol>
      <li><code>list_models.py --resolve</code> 解析出这个模型要哪几个包；</li>
      <li><b>CUE4Parse</b> 逐包导 ActorX pskx：<code>-g GAME_TheFirstDescendant -m &lt;usmap&gt; --mesh-format ActorX --export-materials</code>。
        出来的 pskx 带<b>真实材质槽名</b>（<code>PC_003_A0101_PartA_MI</code> 这种）、<b>morph target</b>、顶点色；</li>
      <li><code>resolve_textures.py</code>：槽名 → 材质实例包 → 用 <code>iostore.py</code> 读它的 zen 名字表拿到引用的贴图名 →
        CUE4Parse 一次把这些虚拟贴图解码成 PNG → UE Viewer 读材质参数，汇总成 <code>materials.json</code>；</li>
      <li>Blender 无头跑 <code>build_blend.py</code>：合成一副骨架、按槽建材质、渲两张预览、存 <code>.blend</code>（贴图拷进 <code>textures\</code> 用相对路径）。</li>
    </ol>
    <p>末尾解析 <code>TFD_REPORT=</code> 打印骨骼数、每个部件的顶点 / 槽 / morph 数、材质与贴图张数、未解析贴图、告警。
      整个 <code>blend\&lt;id&gt;\</code> 目录可以直接拷给别人。</p>

    <h3>第三步 · 批量 + 重建本页</h3>
    <pre># 12 个女性后裔，一个约 1–2 分钟
foreach ($id in 'Viessa','Bunny','Freyna','Gley','Sharen','Valby','Luna','Hailey','Ines','Serena','Nell','Harris') {
    .\export_model.ps1 $id
}

cd .\html
python .\collect_manifest.py      # 读 blend\*\build.log -> D:\tfd_exports\tfd_models_manifest.json
python .\make_gallery.py          # 缩略图 -> D:\tfd_exports\_gallery\thumbs，页面 -> 本目录 index.html</pre>
    <p>已经有 <code>.blend</code> 的会跳过（要重做加 <code>-Force</code>）。<code>collect_manifest.py</code> 会顺手读一次容器编目来给每条打上
      kind / 角色 / 编号，没有 AES key 时加 <code>--no-catalogue</code>，退化成按 id 前缀猜。</p>

    <h3>usmap 从哪来（最麻烦的一步）</h3>
    <p>本作的包是 <b>unversioned properties</b>（我直接读包头标志确认的），没有 <code>.usmap</code> 时 CUE4Parse 只会报
      <code>Could not load standard asset, check game version, mappings or keys</code>。Nexus 上原来的两个映射 mod
      （<code>thefirstdescendant/mods/1</code> 和 <code>mods/5</code>）<b>已被下架</b>——用公开 GraphQL 接口查过，整个板块只剩 1 个壁纸 mod。
      现在用的是 Gildor 论坛 TFD 帖（topic 9006）第 7 页网友发的 MediaFire 文件 <code>Mappings.usmap</code>（2024-07-16）。
      <b>它是发售版的映射，两年后已部分过期</b>：</p>
    <ul>
      <li>能解：<b>Texture2D / 虚拟贴图</b>、<b>SkeletalMesh</b>（含材质槽名、morph、顶点色）→ 网格和贴图全靠它；</li>
      <li>不能解：<b>MaterialInstanceConstant</b>（报 <code>Invalid bool value</code>），所以「这个材质引用了哪些贴图」读不出来。
        这块由 <code>iostore.py</code> 补：自己解容器（AES-ECB 分块 + Oodle）、自己读 zen 包头的名字表（UE 5.2 的 44 字节 summary），
        <b>完全不需要 usmap</b>——一个材质实例的名字表里就明晃晃列着它引用的全部贴图名。</li>
    </ul>
    <p>自己生成新 usmap 要往带 EAC + Nexon 反作弊的游戏进程里注入 Dumper-7 / UE4SS，有封号风险，没做。
      <b>另一个坑</b>：拿通用的 <code>-g GAME_UE5_2</code> 代替 TFD 专用枚举，网格能出但贴图会解坏
      （<code>Failed to parse pixel format: PF_DXT5_0</code>、<code>Serialized FString is not null terminated</code>）。</p>

    <h3>贴图约定（build_blend.py 按这个建材质）</h3>
    <table>
      <tr><th>后缀</th><th>内容</th><th>用法</th></tr>
      <tr><td><code>_C</code></td><td>颜色</td><td>Base Color（sRGB）</td></tr>
      <tr><td><code>_N</code></td><td>法线，<b>DirectX 约定</b></td><td>翻绿通道再进 Normal Map</td></tr>
      <tr><td><code>_P</code></td><td>打包图 <b>R=AO，G=粗糙度，B=金属度</b>（alpha≈0）</td>
        <td>必须按 <b>Channel Packed</b> 读，否则 alpha 预乘会把 RGB 抹黑；皮肤的 <code>_P</code> 是另一个母材质（B 恒 255），金属度强制 0</td></tr>
      <tr><td><code>_ID</code></td><td>六色硬边区域遮罩（红/绿/蓝/品红/黄/青 = 染色区 A–F）</td><td>玩家染色系统用；默认外观直接用 <code>_C</code>，没接</td></tr>
      <tr><td><code>_FX</code></td><td>自发光遮罩（R）</td><td>× 材质参数 <code>Emissive_col</code></td></tr>
      <tr><td><code>Female/Male_HairTex_NNN_P</code></td><td>共享发丝图：A=透明度，G=发根→发梢，R/B=深度/AO</td>
        <td>颜色 = <code>Hair_RootColor</code> → <code>Hair_TipColor</code> 按 G 混合</td></tr>
      <tr><td>眼睛</td><td><code>T_Sclera_D</code> + <code>T_Veins_D</code> + <code>T_Eye_N</code>；虹膜是 MetaHuman 式程序化（<code>IrisColor1U/V</code> 去 <code>iris_color_picker</code> 取色）</td>
        <td>巩膜贴图 + 程序化虹膜圆盘（<b>颜色目前是近似棕色，取色还没接</b>）</td></tr>
      <tr><td>眉 / 睫</td><td>父材质的 <code>T_eyebrow_d</code> / <code>T_eyelash2_D</code></td><td>深色 + alpha</td></tr>
      <tr><td><code>*Glass_MI</code></td><td>面罩</td><td>参数 <code>Color</code>/<code>Opacity</code>/<code>Roughness</code> → 半透明</td></tr>
      <tr><td><code>EyeOCC</code> / <code>TearLine</code></td><td>眼部遮挡壳 / 泪线</td><td>全透明</td></tr>
    </table>
    <p>材质实例名就是 pskx 的槽名，<code>classify()</code> 按名字<b>和贴图</b>判类型。游戏方的拼写要注意：<code>Eyeblow</code>（= 眉毛）、
      <code>Textuer</code>、<code>_Ml</code>；<code>Head_999_MI</code> 这种不带 hair 字样的按有没有 <code>HairTex</code> 贴图识别；
      <code>Face_Dyed_Mask</code> 是参数名不是贴图，别去找。</p>

    <h3>多部件怎么合</h3>
    <ul>
      <li><b>同骨架部件</b>（皮肤的 Body / Face）：按骨名并入底模骨架，缺的骨按父子关系补进去。
        Blender 坑：跨 <code>mode_set</code> 切换后不能再读旧的骨引用（会 <code>UnicodeDecodeError</code>），合骨前先把骨名 / 坐标拉成普通值。</li>
      <li><b>socket 配件</b>（皮肤 HEAD 里的头盔：自带 <code>Head_Root → Pt_Head → Bn_Socket_*</code> 三根骨、和角色骨架<b>无一根同名</b>、网格画在原点）：
        不能蒙皮，整体骨父级到底模的 <code>Bn_Socket_Head</code>（退而求其次 <code>Bip001-Head</code>），用该骨的完整矩阵。不这么做它会掉在脚边。</li>
      <li>部件自己的骨和底模同名骨位置不一致时，用最靠根的共享骨算刚体差把部件挪过去（同骨架时为恒等）。</li>
      <li>骨架是 3ds Max Biped：<code>Bip001-Head</code>、<code>Bn_*</code>、<code>Pt_*</code>、<code>Dm_*</code>。</li>
    </ul>

    <h3>容易踩的坑</h3>
    <ul>
      <li><b>PowerShell 5.1 + 原生程序的 stderr</b>：cue4parse 把日志写 stderr，在 <code>$ErrorActionPreference='Stop'</code> 下配 <code>2&gt;&amp;1</code>，
        第一行日志就会变成终止性的 <code>NativeCommandError</code>。调用处临时切 <code>Continue</code>，<code>finally</code> 里切回来。</li>
      <li><b>.ps1 里的字符串必须全 ASCII</b>：PowerShell 5.1 按 OEM 代码页读无 BOM 的 .ps1，引号里的多字节中文会把解析搞坏。中文放 Python / Markdown 里。</li>
      <li><b>打包图别用默认色彩空间</b>：<code>_P</code> 的 alpha≈0，Blender 里不勾 Channel Packed 就会预乘成黑的，模型全成了 AO 全黑。</li>
      <li><b>怪物清单会混进蓝图</b>：<code>BP_</code> / <code>ABP_</code> / <code>_AnimBP</code> 也在 <code>MESH/</code> 下，不过滤会把 201 只怪虚报成几百。</li>
      <li><b>一个目录里有多个变体</b>：<code>MOB_CMN_1001</code> 下同时有 A001 和 B001，按主网格分组（id = 网格名）才不会被合成一个。</li>
      <li>预览图取脸的位置按 <code>Bip001-Head</code> 找；相机 <code>sensor_fit = VERTICAL</code>，否则竖构图会把人裁掉。</li>
    </ul>

    <h3>产物目录（默认 D:\tfd_exports）</h3>
    <pre>cue4_exports\M1\Content\...               CUE4Parse 原始导出（pskx + 贴图 PNG，按游戏目录结构）
umodel_exports\...                        UE Viewer 的 .props.txt（材质参数）
blend\&lt;id&gt;\&lt;id&gt;.blend                     一副骨架 + 全部部件 + 材质（相对路径）
blend\&lt;id&gt;\textures\                      这个模型用到的 PNG
blend\&lt;id&gt;\preview.png / preview_face.png / materials.json / spec.json / build.log
tfd_models_manifest.json                  collect_manifest.py 的汇总；_gallery\thumbs\ 是本页缩略图
_keys\aes_key.txt                         AES key（不进仓库）</pre>

    <h3>已知局限</h3>
    <ul>
      <li><b>虹膜颜色是近似值</b>：游戏用 <code>IrisColor1U/V</code> 去 <code>iris_color_picker</code> 取色，图已经解出来在
        <code>cue4_exports\M1\Content\BaseMaterials\Character\Material\Eyes\Texture\</code>，采样还没接。</li>
      <li><b>染色系统没接</b>（<code>_ID</code> + <code>ID_A..F_col</code>）：默认外观就是 <code>_C</code> 的颜色。</li>
      <li>usmap 是 2024 年的：后续赛季新加的材质母版若改了布局，个别贴图 / 网格可能解不出，卡片上会显示「告警」，
        <code>materials.json</code> 里也有 <code>missing_textures</code>。</li>
      <li>怪物 / 武器 / 载具只按目录并网格，材质母版没有逐个核对。</li>
      <li>本页所有路径都是本机 <code>file://</code>，换机器要重新导出 + 重新生成。</li>
    </ul>
</section>
"""


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The First Descendant 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --mod: #7a3fa0; --mod-bg: #f1e7f8; --kind: #1f7a4d; --kind-bg: #e3f4ea; --shot: #d9dbe2;
  --f: #b03a72; --f-bg: #fae6ef; --m: #2d6ea8; --m-bg: #e3eefa;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --mod: #c99ae6; --mod-bg: #33203d; --kind: #7fd1a3; --kind-bg: #1c3527; --shot: #2a2d34;
    --f: #f0a0c4; --f-bg: #3c2030; --m: #96c3ef; --m-bg: #1c2c3e;
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
#sex {{ padding: 6px 8px; font: inherit; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 7px; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
main {{ padding: 22px 32px 48px; }}
.grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); }}
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
.titlerow {{ display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }}
.titletext {{ min-width: 0; flex: 1; }}
.titlerow h3 {{ margin: 0 0 4px; font-size: 15px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.avatar {{ flex: 0 0 auto; line-height: 0; }}
.avatar img {{
  width: 52px; height: 52px; object-fit: cover; border-radius: 50%;
  border: 1px solid var(--line); background: var(--shot);
}}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; cursor: help; }}
.badge-warn {{ color: var(--warn); background: var(--warn-bg); }}
.badge-mod {{ color: var(--mod); background: var(--mod-bg); }}
.badge-kind {{ color: var(--kind); background: var(--kind-bg); cursor: default; }}
.badge-female {{ color: var(--f); background: var(--f-bg); cursor: default; }}
.badge-male {{ color: var(--m); background: var(--m-bg); cursor: default; }}
dl {{ margin: 0; display: grid; grid-template-columns: 42px 1fr; gap: 3px 10px; }}
dt {{ color: var(--muted); font-size: 12px; }}
dd {{ margin: 0; font-size: 12px; font-family: Consolas, monospace; overflow-wrap: anywhere; }}
dd.prose {{ font-family: inherit; }}
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
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
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
  <h1>The First Descendant · 模型导出总览</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{descendants}</b><span>后裔</span></div>
    <div class="stat"><b>{females}</b><span>女性后裔</span></div>
    <div class="stat"><b>{size}</b><span>blend + 贴图</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索 id（Viessa）、说明（冰）、部件（Body）、材质（头发）或包路径…（按 / 聚焦）">
  <select id="sex"><option value="">全部体型</option>{sex_options}</select>
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
  var sexSel = document.getElementById('sex');
  var kind = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!kind || card.dataset.kind === kind)
        && (!sexSel.value || card.dataset.sex === sexSel.value)
        && (!onlyWarn || card.dataset.warn === '1');
      card.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
    empty.hidden = shown !== 0;
  }}

  q.addEventListener('input', apply);
  sexSel.addEventListener('change', apply);
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
    manifest_path = args.manifest or os.path.join(source_root, "tfd_models_manifest.json")
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
    no_desc = [m["label"] for m in models if not m["name"]]
    print("models      : %d（后裔 %d，其中女性 %d）"
          % (len(models), sum(1 for m in models if m["kind"] == "descendant"),
             sum(1 for m in models if m["kind"] == "descendant" and m["sex"] == "female")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("no desc     : %d%s" % (len(no_desc), (" -> " + ", ".join(no_desc[:10])) if no_desc else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
