"""把 Vindictus: Defying Fate 的导出产物做成一页可浏览的 HTML 画廊。

读 ``vindictus_models_manifest.json``（由 collect_manifest.py 从 blend\\<模型>\\build.log 汇总），
把每张预览图缩成 JPEG 缩略图，输出自包含的 ``index.html`` 到本脚本旁边。

页面用 ``file://`` 链接指向本机真实文件，缩略图写在导出根目录下，
**任何游戏素材都不会进仓库** —— 和这里其它脚本同一条规矩。每批新导出后重跑即可。

用法：
  python make_gallery.py
  python make_gallery.py --source-root D:\\vindictus_exports --force
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
KIND_LABELS = {"player": "主角默认装", "outfit": "服装", "base": "基础身体", "monster": "怪物", "npc": "NPC"}
KIND_ORDER = ("player", "outfit", "base", "monster", "npc")
BODY_LABELS = {"PCF": "女（Fiona）", "PCM": "男（Lethita）", "": "其它"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", default=r"D:\vindictus_exports",
                   help="导出根目录（默认 %(default)s）")
    p.add_argument("--manifest", default=None,
                   help="manifest 路径（默认 <导出根>\\vindictus_models_manifest.json）")
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
        face_thumb = build_thumb(entry.get("facePreview"), os.path.join(thumb_dir, label + "_face.jpg"), force)
        models.append({
            "label": label,
            "name": entry.get("name") or "",
            "kind": entry.get("kind") or "outfit",
            "body": entry.get("body") or "",
            "blend": entry.get("blend") or "",
            "preview": entry.get("preview") or "",
            "face": entry.get("facePreview") or "",
            "thumb": thumb or "",
            "face_thumb": face_thumb or "",
            "blend_size": entry.get("blendSize") or 0,
            "parts": list(entry.get("parts") or []),
            "vertices": entry.get("vertices") or 0,
            "faces": entry.get("faces") or 0,
            "bones": entry.get("bones") or 0,
            "merged": entry.get("mergedBones") or 0,
            "materials": entry.get("materials") or 0,
            "textures": entry.get("textures") or 0,
            "reposed": list(entry.get("reposed") or []),
            "hidden": list(entry.get("hidden") or []),
            "warnings": list(entry.get("warnings") or []),
        })
    models.sort(key=lambda m: (KIND_ORDER.index(m["kind"]) if m["kind"] in KIND_ORDER else 9, m["label"].lower()))
    return manifest, models


def render_card(model):
    esc = html.escape
    thumb_uri = file_uri(model["thumb"])
    preview_uri = file_uri(model["preview"])
    blend_uri = file_uri(model["blend"])
    face_uri = file_uri(model["face"])

    badges = '<span class="badge badge-kind">%s</span>' % esc(KIND_LABELS.get(model["kind"], model["kind"]))
    if model["body"]:
        badges += '<span class="badge badge-code">%s</span>' % esc(model["body"])
    if model["hidden"]:
        badges += '<span class="badge badge-mod" title="Head 部件替代了默认头发，头发留在文件里但隐藏">隐藏 %s</span>' % esc("/".join(model["hidden"]))
    if model["reposed"]:
        badges += '<span class="badge badge-mod" title="%s">重定位 %d</span>' % (
            esc("绑在另一版骨架上的部件已按底骨架重新烘焙：" + "; ".join(model["reposed"])), len(model["reposed"]))
    if model["warnings"]:
        badges += '<span class="badge badge-warn" title="%s">告警 %d</span>' % (
            esc("; ".join(model["warnings"])), len(model["warnings"]))

    search_blob = esc(" ".join([model["label"], model["name"], model["kind"], model["body"], " ".join(model["parts"]), model["blend"]]).lower())
    figure = ('<img loading="lazy" src="%s" alt="%s">' % (esc(thumb_uri), esc(model["label"]))
              if thumb_uri else '<div class="noimg">无预览图</div>')
    face_row = ('\n            <dt>脸部</dt>\n            <dd><a href="%s" target="_blank" rel="noopener">preview_face.png</a></dd>' % esc(face_uri)) if face_uri else ""
    return """      <article class="card" data-search="{search}" data-kind="{kind}" data-body="{body}" data-warn="{warn}">
        <a class="shot" href="{preview}" target="_blank" rel="noopener"
           title="点击查看原图">{figure}</a>
        <div class="body">
          <div class="titlerow">
            <h3>{label}</h3>{badges}
          </div>
          <dl>
            <dt>说明</dt><dd class="prose">{name}</dd>
            <dt>部件</dt><dd>{parts}</dd>
            <dt>规格</dt>
            <dd>{vertices} 顶点 · {faces} 面 · {bones} 骨骼（合并 {merged}）· {materials} 材质 · {textures} 贴图 · {size}</dd>
            <dt>blend</dt>
            <dd><a href="{blend_uri}" title="{blend}">{blend}</a>
                <button class="copy" data-copy="{blend}">复制</button></dd>{face_row}
          </dl>
        </div>
      </article>
""".format(search=search_blob, kind=esc(model["kind"]), body=esc(model["body"]),
           warn="1" if model["warnings"] else "0",
           preview=esc(preview_uri), figure=figure, label=esc(model["label"]),
           badges=badges, name=esc(model["name"] or "-"), parts=esc(" · ".join(model["parts"]) or "-"),
           vertices=model["vertices"], faces=model["faces"], bones=model["bones"], merged=model["merged"],
           materials=model["materials"], textures=model["textures"],
           size=human_size(model["blend_size"]),
           blend_uri=esc(blend_uri), blend=esc(model["blend"]), face_row=face_row)


def render(models, source_root):
    esc = html.escape
    total_bytes = sum(m["blend_size"] for m in models)
    outfits = sum(1 for m in models if m["kind"] == "outfit")
    warned = sum(1 for m in models if m["warnings"])
    kinds = [k for k in KIND_ORDER if any(m["kind"] == k for m in models)]
    per_body = {}
    for m in models:
        per_body[m["body"]] = per_body.get(m["body"], 0) + 1
    body_options = "".join('<option value="%s">%s (%d)</option>' % (esc(b), esc(BODY_LABELS.get(b, b)), n)
                           for b, n in sorted(per_body.items()))
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    chips = "".join('<button class="chip" data-kind="%s">%s</button>' % (esc(k), esc(KIND_LABELS[k]))
                    for k in kinds)
    cards = "".join(render_card(m) for m in models)
    return PAGE_TEMPLATE.format(
        appendix=APPENDIX_HTML,
        generated=esc(generated), source_root=esc(source_root),
        total=len(models), outfits=outfits, size=human_size(total_bytes),
        warned=warned, chips=chips, body_options=body_options, cards=cards)


APPENDIX_HTML = r"""
<section class="appendix">
    <h2>附录 · 手工导出教程</h2>
    <p>脚本都在 <code>scripts\vindictus\</code>，产物默认落在 <code>D:\vindictus_exports</code>（<code>-ExportRoot</code>）。这套和别的游戏最大的不同：
      <b>游戏没发售</b>（Steam 商店页写 2027），能拿到的只有 2024-03-14 那次 Pre-Alpha 测试的客户端，而且它的 pak/utoc 索引是 <b>AES 加密</b>的，
      key 不在任何公开网页上——要自己从 exe 里算出来（<code>find_aes_key.py</code>，一分多钟）。顺序固定：装客户端 → 算 key → <code>list_models.py</code> 看清单
      → <code>export_model.ps1 &lt;模型&gt;</code> 出带贴图、一副骨架的 .blend → 重生成本页。
      <b>以下所有命令都在 <code>〈仓库〉\scripts\vindictus</code> 里跑，每开一个新窗口先 <code>cd</code> 进去。</b></p>

    <h3>前提 · 工具与默认路径</h3>
    <table>
      <tr><th>工具</th><th>脚本默认路径 / 说明</th></tr>
      <tr><td>客户端</td><td>archive.org 项目 <code>vindictus-defying-fate.-7z</code>（<code>Vindictus_Defying_Fate.7z</code>，15,150,318,532 字节，md5 <code>801374e112f438af9d401579c75fc6c1</code>，
        种子在同一页）。解压后把压缩包顶层的 <code>Vindictus\</code> 当游戏根放到 <code>E:\tools\vindictus</code>（<code>-GameRoot</code>），
        即 <code>E:\tools\vindictus\Vindictus.exe</code> 和 <code>E:\tools\vindictus\Vindictus\Content\Paks\Vindictus-Windows.ucas</code>（15.04 GB）。
        国内直连 archive.org 不通、普通 HTTP 代理只有几十 KB/s——走本机 VPN 客户端的系统代理端口并开 8 个 Range 连接可到 14 MB/s（20 分钟）。
        2025-06 的 Alpha Demo（Steam <code>3576170</code>）测试结束后被换成 348 MB 空壳，<b>下不到</b>。</td></tr>
      <tr><td>UE Viewer</td><td>必须是 spiritovod 的 <b>UE5 specific build</b>：Gildor 论坛 <code>https://www.gildor.org/smf/index.php?topic=7906.0</code> 首帖的 Google Drive
        <code>umodel_materials.zip</code>，取里面的 <code>umodel_materials_ue5.exe</code>（本机是 build 1579 based fix282 / 2026-09-05）放到
        <code>E:\tools\umodel_specific\materials\</code>（<code>-UmodelExe</code>）。Oodle 已内置，不需要额外 dll；官网普通版对 UE 5.3 会报
        <code>Serializing behind stopper</code>。<code>E:\tools\umodel_stellarblade</code>、<code>umodel_ff7remake</code> 那两个专用版<b>不能</b>用在这里。</td></tr>
      <tr><td>Blender 3.6.15</td><td><code>D:\Program Files\blender-3.6.15-windows-x64\blender.exe</code>（<code>-BlenderExe</code>），须先装好并启用 <b>io_scene_psk_psa 5.0.6</b>
        （<code>https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6</code>，别拿面向 4.x 的新版）。脚本用 <code>--factory-startup</code> 跑，
        自己 <code>addon_utils.enable</code> 这个插件，所以只要装在用户目录即可，不必在偏好里勾选。</td></tr>
      <tr><td>Python 3</td><td><code>python</code> 要能直接调起 Python 3；<code>pip install cryptography Pillow</code>——前者解 utoc 目录索引和试解密 pak 索引，后者出缩略图。</td></tr>
      <tr><td>PowerShell</td><td>未签名脚本，第一次跑先在当前用户范围放开执行策略（RemoteSigned），按 <code>.\export_model.ps1</code> 调用。</td></tr>
    </table>

    <h3>第零步 · 算 AES key（find_aes_key.py，只做一次）</h3>
    <pre>cd 〈仓库〉\scripts\vindictus
python .\find_aes_key.py --out E:\tools\vindictus\_download\aes_key.txt      # 默认就扫 E:\tools\vindictus 的 exe 和 pak</pre>
    <p>key <b>不是</b>明文躺在 exe 里的：Nexon 用 8 条 <code>mov dword [..], imm32</code> 在运行时把 32 字节拼起来，所以 UnrealKey 之类找连续 32 字节的工具会空手而回。
      脚本先扫一遍连续窗口，再收集 <code>.text</code> 里成串的立即数（imm64×4 / imm32×8 / imm8×32）和成对的 xmm 常量，按顺序拼成候选，
      拿 <code>Vindictus-Windows.pak</code> 加密索引的前 16 字节做 AES-256-ECB 试解密，解出挂载点 <code>../../../</code> 即命中（本机 80 秒）。
      命中后写成一行 <code>0x…</code>。之后所有脚本按 <code>VINDICTUS_AES_KEY</code> 环境变量 → <code>-AesKeyFile</code>（默认就是上面这个路径）的顺序取 key，
      再经临时文件以 <code>-aes=@file</code> 交给 UE Viewer，命令行里不出现。</p>
    <div class="note">key 只放本地文件或环境变量。仓库、CHANGELOG、本页面、聊天记录里都不要出现——和 FF7 Remake 的 key 同一条规矩。</div>

    <h3>第一步 · 看清单（list_models.py）</h3>
    <pre>python .\list_models.py                          # 36 个模型：id / kind / body / 部件数 / umodel 已导 / blend 已建
python .\list_models.py --kind outfit --json
python .\list_models.py --resolve PCF_003 --json  # 一个模型的包路径、PSK 状态
python .\list_models.py --raw --path-filter /Character/AI/   # 容器里的原始路径</pre>
    <p>直接解密并解析 <code>Paks\*.utoc</code> 的 IoStore 目录索引（16,703 条路径），不开 UE Viewer。索引只有路径没有类型，所以「部件」= <code>Model\</code> 下名为
      <code>SK_*</code> 且不是 <code>_Skeleton / _Physics / _PhysicsAsset</code> 的资源，再按游戏的拼装方式分组：</p>
    <table>
      <tr><th>kind</th><th>目录</th><th>组成</th></tr>
      <tr><td>player</td><td><code>Character\Player\&lt;Name&gt;\</code></td><td>Fiona（女，PCF 骨架）、Lethita（男，PCM 骨架）：<code>Face\Model\SK_&lt;Name&gt;_Face01</code> + <code>_Hair01</code> + <code>Armor\Model\SK_&lt;Name&gt;_*_master</code></td></tr>
      <tr><td>outfit</td><td><code>Character\Outfit\PC{F,M}_Outfit\&lt;Id&gt;\Model\</code></td><td>服装部件（Upper/Lower 或 Onepiece + Hand/Foot/Head）+ 对应主角的脸和头发；<code>Player\Outfit\Shiningwill\Mesh</code> 下的旧版整套记作 <code>Shiningwill_legacy</code>（3ds Max Biped 骨架 <code>Bip001_*</code>，脸骨架里还留着这套骨、只是转了 90°，脚本会把它转正再配脸/发）</td></tr>
      <tr><td>base</td><td><code>BaseBody_PCM</code> 四件 / Fiona <code>SK_female_base</code></td><td>裸体基础身体 + 脸/发</td></tr>
      <tr><td>monster / npc</td><td><code>Character\AI\&lt;Race&gt;\&lt;Type&gt;\&lt;Variant&gt;\Model\</code>、<code>Character\Npc\**</code></td><td>目录下全部 SK（武器标为 weapon，<code>--include-weapons</code> 才并入）</td></tr>
    </table>
    <p>女性角色只有 Fiona 一个（NPC 的 Female_adult 只有骨架）；女装 15 套 = 默认装 + <code>Shiningwill_legacy</code> + 13 套 <code>PCF_*</code>（其中 002/003/005/006/007 是连衣裙）。</p>

    <h3>第二步 · 一个模型一条命令（export_model.ps1）</h3>
    <pre>.\export_model.ps1 -List                  # = list_models.py
.\export_model.ps1 Fiona                  # 主角默认装
.\export_model.ps1 PCF_003                # 一套服装 + Fiona 脸/发
.\export_model.ps1 PCF_067 -Force         # 重导 + 重建
.\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview</pre>
    <p>三步：<code>list_models.py --resolve</code> 解析包路径（UE Viewer 接受 <code>VindictusRoot/Character/.../SK_xxx</code> 这种 Content 相对路径，避开容器里 178 个重名 stem）；
      对缺失的包逐个 <code>umodel_materials_ue5.exe -game=ue5.3 -path=&lt;Paks&gt; -aes=@tmp -export -png -out=&lt;导出根&gt;\umodel_exports &lt;包&gt;</code>，
      得到 PSK/PSKX + PNG + <code>.mat</code>/<code>.props.txt</code>（材质实例的贴图、向量、标量参数）；然后写 <code>blend\&lt;id&gt;\spec.json</code>，
      无头跑 <code>build_blend.py</code>，解析 <code>VINDICTUS_REPORT=</code> 打印骨骼数、各部件顶点、材质/贴图数、重定位、告警。</p>
    <p><code>build_blend.py</code> 做的事：① UE Viewer 给每个网格导的是它自己的骨架子集（Fiona 脸 658 根、发 274、上身 531、脚 30……），取最多的一副为底按名字补缺、
      所有网格重绑到同一副（Fiona 1415 根）；② 部件绑在另一版骨架上的（8 套服装的 Head 脊柱链差 6.9 cm）先把自己的骨架摆到底骨架的 rest 姿势再烘焙，
      只有一根 <code>root</code> 的部件（Lethita 头发）挂到 <code>head</code> 骨；③ 材质从 <code>.mat</code> + <code>.props.txt</code> 重建——服装 D/N/ORM|ARM、皮肤 D×Tint、
      头发 ODI.R 透明 + FR.B 驱动 Root/Mid/Tip 渐变、眉睫 ODI.R、眼球程序化虹膜（色板采样 → 线性 × IrisBrightness、纤维、limbus、瞳孔）；
      ④ 贴图拷到 <code>textures\</code>、相对路径保存，渲 <code>preview.png</code> / <code>preview_face.png</code>（相机按脚骨方向判断朝向）。</p>

    <h3>第三步 · 批量</h3>
    <pre># 1) 先顺序把包都导出来（UE Viewer 并发会互相覆盖共享贴图，这一步不能并行）
python .\list_models.py --kind outfit --json | ConvertFrom-Json | Where-Object body -eq PCF | ForEach-Object { .\export_model.ps1 $_.id -NoBlend }
# 2) 再分几路并行跑 Blender（PSK 都在了，脚本会跳过 UE Viewer）
foreach ($id in 'PCF_001','PCF_002','PCF_003') { .\export_model.ps1 $id }</pre>
    <p>每套 Blender 约 2–3 分钟；15 套女装三路并行十几分钟。</p>

    <h3>参数表</h3>
    <table>
      <tr><th>参数</th><th>默认</th><th>说明</th></tr>
      <tr><td><code>-GameRoot</code></td><td><code>E:\tools\vindictus</code></td><td>游戏根（含 <code>Vindictus.exe</code>）</td></tr>
      <tr><td><code>-ExportRoot</code></td><td><code>D:\vindictus_exports</code></td><td>产物根</td></tr>
      <tr><td><code>-UmodelExe</code> / <code>-BlenderExe</code> / <code>-PythonExe</code></td><td>见前提表</td><td>工具路径</td></tr>
      <tr><td><code>-AesKeyFile</code></td><td><code>E:\tools\vindictus\_download\aes_key.txt</code></td><td>没设 <code>VINDICTUS_AES_KEY</code> 时从这里读</td></tr>
      <tr><td><code>-Force</code></td><td>关</td><td>重导包 + 重建 blend（否则 blend 已存在就跳过）</td></tr>
      <tr><td><code>-NoBlend</code> / <code>-NoPreview</code></td><td>关</td><td>只到 UE Viewer 为止 / 不渲预览</td></tr>
      <tr><td><code>-Smooth</code></td><td>关</td><td>丢掉 PSK 自带的拆分法线改平滑着色</td></tr>
      <tr><td><code>-IncludeWeapons</code></td><td>关</td><td>把 <code>Weapon\</code> 下的 SK 也并进模型</td></tr>
    </table>

    <h3>产物目录（默认 D:\vindictus_exports）</h3>
    <pre>umodel_exports\VindictusRoot\...          UE Viewer 原始导出（按游戏目录结构：PSK/PSKX、PNG、.mat、.props.txt）
blend\&lt;id&gt;\&lt;id&gt;.blend                     一副骨架 + 全部部件 + 材质（相对路径）
blend\&lt;id&gt;\textures\                      用到的贴图（PNG）
blend\&lt;id&gt;\preview.png / preview_face.png / spec.json / build.log
vindictus_models_manifest.json            collect_manifest.py 的汇总；_gallery\thumbs\ 是本页缩略图</pre>
    <p>整个 <code>blend\&lt;id&gt;\</code> 目录可以直接拷给别人。</p>

    <h3>容易踩的坑</h3>
    <ul>
      <li><b>Head 部件不都是头盔</b>：项链/颈圈（001、007、009）、耳机（002、004）、帽子（003、012）、发带（006）、发冠（005）、自带发型（001_Temp、008、010 打包了 Fiona 的头发）、全盔（067）。
        只有 Head 里带头发材质或 <code>list_models.py</code> 的 <code>HEAD_REPLACES_HAIR</code>（067）标了的才隐藏默认头发；头发仍在文件里（<code>&lt;id&gt;_Hair</code>），要显示就取消隐藏。按几何（贴头皮比例、盖脸比例）分不开耳机和发型，别再试。</li>
      <li><b>部件绑在另一版骨架上</b>：002/003/004/006/007/009/010/012 的 Hand/Head/Upper/Lower 到 <code>head</code>、脚趾差 6.9–13 cm；不重定位帽子会飘在头顶上方。脚本自动烘焙，报告里 <code>reposed_parts</code> 列出。</li>
      <li><b>旧版 Biped 骨架朝向不同</b>：脸骨架里的 <code>Root → Bip001_*</code> 子树相对 UE 骨架转了 90°（面朝 +X），<code>Shiningwill_legacy</code> 绑在它上面会侧着身、脸朝前。脚本把这棵子树连同绑在上面的网格转正、按 <code>Bip001_Head</code>→<code>head</code> 平移对齐，报告里 <code>aligned_hierarchies</code>；它自带的旧发型盖到新脸的眼睛上，所以隐藏旧发型、保留默认头发。</li>
      <li><b>UE Viewer 不能并行</b>：不同模型共用 Fiona 脸/发/眼睛贴图，同时写会互相覆盖。先 <code>-NoBlend</code> 顺序导完再并行 Blender。</li>
      <li><b>virtual texture 导不出</b>：静态物件贴图全是；角色里 <code>T_pc_fiona_basebody_01_D</code>（<code>M_female_skin_body_01</code>，PCF_001_Temp 用）也是——这类皮肤材质用纯肤色代替，报告里会列「未解析」。</li>
      <li><b>BC6H 贴图写成 .hdr</b>：PCF_012 的 <code>_B</code> 基色是 <code>.hdr</code>，脚本已按 <code>.hdr</code> 索引；别按 png 去找。</li>
      <li><b>PCF_001_Temp 是 WIP 服装</b>：裤子的彩虹格/棋盘是资源自带的占位贴图，不是导出坏了。</li>
      <li><b>眼睛</b>：<code>T_Iris_A_M</code> 的 B 是径向渐变、G 是纤维、alpha 是瞳孔，不是遮罩；从色板贴图采到的颜色是 sRGB 值，喂给节点前要转线性——否则虹膜是一团白雾。</li>
      <li><b>UE Viewer 报 Oodle 解压错误</b>：多半是下载的包坏了，核对 md5。</li>
      <li>morph target 导不出（脸包里的 MetaHuman <code>DNAAsset</code> 也不导），面部没有形态键；Nanite 只有基础几何。</li>
    </ul>

    <h3>重新生成本页</h3>
    <pre>cd 〈仓库〉\scripts\vindictus\html
python .\collect_manifest.py          # 读 blend\*\build.log -> D:\vindictus_exports\vindictus_models_manifest.json
python .\make_gallery.py              # 缩略图 -> D:\vindictus_exports\_gallery\thumbs，页面 -> 本目录 index.html</pre>

    <h3>例外与已知局限</h3>
    <ul>
      <li>怪物 / NPC 目前只是按目录把 SK 并起来，材质母板没逐个核对。</li>
      <li>眼球是近似：没有角膜折射，虹膜半径 0.2 是按这批头的眼裂宽度定的；皮肤 <code>_Mask</code>、头发高光随机度等参数没用上。</li>
      <li><code>SK_Fiona_Lower01_master</code> 里带一段 <code>PCF_005_Onepiece</code> 材质，是 master 网格自带的，渲染上被裙甲盖住。</li>
      <li>正式版发售后目录结构、骨架版本都可能变，本页所有数字只对 2024-03 Pre-Alpha 客户端成立。</li>
    </ul>
</section>
"""


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vindictus: Defying Fate 模型导出总览</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --warn: #b4600a; --warn-bg: #fdf1e0;
  --mod: #7a3fa0; --mod-bg: #f1e7f8; --kind: #1f7a4d; --kind-bg: #e3f4ea; --shot: #d9dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16171b; --panel: #1f2126; --ink: #e9eaee; --muted: #9aa0ab;
    --line: #2e3138; --accent: #7ea2ff; --warn: #e3a765; --warn-bg: #3a2c19;
    --mod: #c99ae6; --mod-bg: #33203d; --kind: #7fd1a3; --kind-bg: #1c3527; --shot: #2a2d34;
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
.badge-mod {{ color: var(--mod); background: var(--mod-bg); }}
.badge-kind {{ color: var(--kind); background: var(--kind-bg); cursor: default; }}
.badge-code {{ color: var(--accent); background: var(--bg); cursor: default; font-family: Consolas, monospace; }}
#body {{ padding: 6px 8px; font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }}
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
  <h1>Vindictus: Defying Fate · 模型导出总览（2024-03 Pre-Alpha）</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{source_root}</code> ·
    图片与 blend 均为本机文件，换机器需重新生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>已转模型</span></div>
    <div class="stat"><b>{outfits}</b><span>服装</span></div>
    <div class="stat"><b>{size}</b><span>blend 总体积</span></div>
    <div class="stat"><b>{warned}</b><span>有告警</span></div>
  </div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="搜索模型 id（PCF_003）、说明（女巫帽）、部件（Onepiece）或路径…（按 / 聚焦）">
  <select id="body"><option value="">全部身体</option>{body_options}</select>
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
  var bodySel = document.getElementById('body');
  var kind = '';

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var onlyWarn = warnOnly.classList.contains('on');
    var shown = 0;
    cards.forEach(function (card) {{
      var ok = (!term || card.dataset.search.indexOf(term) !== -1)
        && (!kind || card.dataset.kind === kind)
        && (!bodySel.value || card.dataset.body === bodySel.value)
        && (!onlyWarn || card.dataset.warn === '1');
      card.hidden = !ok;
      if (ok) shown++;
    }});
    count.textContent = shown + ' / ' + cards.length;
    empty.hidden = shown !== 0;
  }}

  q.addEventListener('input', apply);
  bodySel.addEventListener('change', apply);
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
    manifest_path = args.manifest or os.path.join(source_root, "vindictus_models_manifest.json")
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
    print("models      : %d（服装 %d）" % (len(models), sum(1 for m in models if m["kind"] == "outfit")))
    print("no preview  : %d%s" % (len(missing), (" -> " + ", ".join(missing[:10])) if missing else ""))
    print("thumbnails  : %s" % thumb_dir)
    print("page        : %s (%s)" % (out_path, human_size(os.path.getsize(out_path))))


if __name__ == "__main__":
    main()
