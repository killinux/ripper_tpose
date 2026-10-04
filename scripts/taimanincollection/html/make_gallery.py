"""Gallery page of Taimanin Collection's 3D models: how to export one (the short way first, then step by step),
what was exported (pictures and links into the export folder) and the whole list by category.

    python list_models.py --html        # writes html/index.html next to this file and prints its path

The page holds file:/// links to this machine's export folder and nothing of the game itself.
"""
from __future__ import annotations

import datetime
import html
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tcollection_common as tcc  # noqa: E402
from tcollection_common import tc  # noqa: E402

SHOWN_FIRST = ("character", "vehicle", "scene", "prop", "level", "set")     # the order of the exported cards
# what one full export prints (prf_asagi_costume_1 into an empty export folder, 2026-10-04: 3 min 19 s)
SAMPLE_RUN = """[tcollection] (1/1) prf_asagi_costume_1  角色
[tcollection] prf_asagi_costume_1: reading unit_art/model/asagi/prf_asagi_costume_1
[tcollection] prf_asagi_costume_1: 29 expression shapes (the game's clips + lip / gaze recipes): angry_face closed_eyes ...
[tcollection] prf_asagi_costume_1: building {root}\\Asagi\\blend\\prf_asagi_costume_1\\prf_asagi_costume_1.blend (5 parts, 102 bones, 7 materials)
[tsquad] prf_asagi_costume_1: turntable video ...
[tsquad] prf_asagi_costume_1: XPS ...
[tsquad] prf_asagi_costume_1: PMX ...
[tcollection] prf_asagi_costume_1: {root}\\Asagi\\blend\\prf_asagi_costume_1\\prf_asagi_costume_1.blend  (9323 verts, 13773 faces, 102 bones, 7 materials, 29 shape keys, 31 s)
[tcollection]   TURNTABLE {root}\\Asagi\\blend\\prf_asagi_costume_1\\prf_asagi_costume_1_turntable.mp4
[tcollection]   XPS {root}\\Asagi\\xps\\prf_asagi_costume_1\\prf_asagi_costume_1.xps
[tcollection]   PMX {root}\\Asagi\\pmx\\prf_asagi_costume_1\\prf_asagi_costume_1.pmx
[tcollection]   PMX: 196 bones, 24 rigid bodies, torn 0, stretched 14, grant violations 0, bust 2, morphs 37
[tcollection]   PMX breasts: size 8.3 cm -> factor 0.76: travel [3.8, 3.04, 3.04] cm, [2.52, 2.98, 4.13] Hz, sag 1.16 cm
[tcollection] done: 1 built, 0 skipped, 0 failed"""

CSS = """
:root{color-scheme:dark}
body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#1c1d22;color:#ddd;margin:0;padding:0 24px 60px;font-size:14px;line-height:1.6}
h1{font-size:24px;margin:22px 0 4px} h2{font-size:18px;margin:30px 0 10px;border-bottom:1px solid #444;padding-bottom:4px}
h3{font-size:14px;margin:14px 0 6px;color:#bbb} a{color:#8ec7ff;text-decoration:none} a:hover{text-decoration:underline}
.note{color:#aaa;font-size:13px;line-height:1.7} code{background:#2b2d35;padding:1px 5px;border-radius:3px;color:#e8d9a0;font-family:Consolas,monospace;font-size:12.5px}
pre{background:#2b2d35;padding:10px 14px;border-radius:5px;color:#e8d9a0;overflow-x:auto;font:12.5px/1.5 Consolas,monospace}
details{background:#24262d;border-radius:6px;padding:8px 16px;margin:10px 0} summary{cursor:pointer;font-weight:600}
ol,ul{margin:6px 0;padding-left:22px} li{margin:4px 0}
.quick{border:1px solid #8ec7ff;border-radius:8px;padding:10px 16px 6px;margin:12px 0;background:#22242b}
.cmd{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;margin:3px 0;padding:4px 10px;background:#2b2d35;border-radius:5px}
.cmd code{background:none;padding:0;white-space:pre-wrap;word-break:break-all} .cmd .what{color:#aaa;font-size:13px;flex:1 1 240px}
.copy{font:inherit;font-size:11px;padding:1px 8px;cursor:pointer;color:#ddd;background:#3a3d48;border:1px solid #555;border-radius:999px}
.ok,.no{font-size:11px;padding:1px 7px;border-radius:999px;white-space:nowrap} .ok{background:#2f5a3a;color:#e6ffe9} .no{background:#5a2f3a;color:#ffe6ea}
.cards{display:flex;flex-wrap:wrap;gap:14px} .card{background:#262830;border-radius:6px;padding:10px;width:330px}
.card img{max-width:160px;max-height:220px;border-radius:4px;background:#111;margin-right:4px;vertical-align:top}
.card .title{font-weight:600;margin:6px 0 2px;font-family:Consolas,monospace} .card .small{font-size:12px;color:#aaa;line-height:1.6}
.chips{display:flex;flex-wrap:wrap;gap:5px} .chip{font-size:12px;background:#2b2d35;border-radius:10px;padding:2px 9px;color:#bbb}
.chip.done{background:#2f5a3a;color:#e6ffe9} table{border-collapse:collapse;font-size:13px;margin:6px 0}
td,th{border:1px solid #444;padding:4px 10px;text-align:left;vertical-align:top}
"""

SCRIPT = """
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('.copy') : null;
  if (!b) return;
  var text = b.getAttribute('data-copy');
  function done() { var old = b.textContent; b.textContent = '已复制'; setTimeout(function () { b.textContent = old; }, 1200); }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { window.prompt('复制：', text); });
  } else { window.prompt('复制：', text); }
});
"""


def uri(path: str) -> str:
    try:
        return Path(path).as_uri()
    except (ValueError, OSError):
        return ""


def link(path: str, text: str) -> str:
    return '<a href="%s" title="%s">%s</a>' % (html.escape(uri(path)), html.escape(path), html.escape(text))


def img(path: str) -> str:
    return '<a href="%s"><img src="%s" loading="lazy" alt=""></a>' % ((html.escape(uri(path)),) * 2)


def commands(rows) -> str:
    """[(command, what it does - HTML)] -> one copyable line each."""
    return "\n".join('<div class="cmd"><code>%s</code><button class="copy" data-copy="%s">复制</button>'
                     '<span class="what">%s</span></div>' % (html.escape(c), html.escape(c), what) for c, what in rows)


def mark(found: bool) -> str:
    return '<span class="ok">本机已有</span>' if found else '<span class="no">本机没找到</span>'


def howto(root: str, counts: dict) -> str:
    """How to export a model: the short way, what is needed, finding one, exporting, the result, failures."""
    esc = html.escape
    scripts = os.path.dirname(HERE)
    repo = os.path.dirname(os.path.dirname(scripts))
    b2x = os.environ.get("BLENDER2XPS", os.path.join(os.path.dirname(repo), "blender2xps"))
    full = "python export_model.py prf_asagi_costume_1 --xps --pmx --turntable"
    return """
<p class="note">这个游戏本体是 2D 卡牌（843 张卡是加密的图片，没有模型）。3D 的东西都在
<code>{data}</code> 这一个文件里：<b>阿莎姬</b>一个角色、摩托小游戏用的<b>摩托车、运输机、桥面赛道和道具</b>，
以及一批 Action Taimanin 留下来、这个游戏并不显示的<b>残留</b>（材质被剥掉的两套城市布景、{raw} 个几乎都只有默认材质的原始模型）。
<b>导出</b> = 把一个 prefab 读出来做成能直接打开的 <code>.blend</code>（游戏的材质 + 骨架 + 表情），需要的话再转 XPS 和 MMD 的 PMX。
不用启动游戏、不用联网、不需要密钥。</p>

<div class="quick"><b>最短的路：三条命令</b> <span class="note">（第一次用，先看下面的「第 0 步」）</span>
<ol>
<li>打开 PowerShell，进到脚本目录：{cd}</li>
<li>导出一个模型。这里是阿莎姬；换别的就把 <code>prf_asagi_costume_1</code> 换成下面清单里的 id：{full}
约 3 分钟（只要 <code>.blend</code> 就去掉后面三个开关，约 30 秒）。最后一行是 <code>done: 1 built, 0 skipped, 0 failed</code> 就成了。</li>
<li>刷新本页，「已导出」里会多出这个模型的卡片：{refresh}</li>
</ol></div>

<details open><summary>第 0 步　准备（只做一次）</summary>
<ol>
<li>装 Python 包：{pip}</li>
<li><b>Blender 3.6</b>：<code>{blender}</code> {blender_mark}（别处就设环境变量 <code>TSQUAD_BLENDER</code>）。</li>
<li><b>游戏</b>在 <code>{game}</code> {game_mark}（别处就设 <code>TCOLLECTION_GAME_DIR</code>）；<b>导出到</b> <code>{root}</code>（<code>TCOLLECTION_EXPORT_ROOT</code>）。</li>
<li>按想要的格式再准备：
<table><tr><th>想要什么</th><th>命令里加</th><th>另外需要</th></tr>
<tr><td><code>.blend</code> + 预览图（角色另有脸部特写和表情总览）</td><td>什么都不加</td><td>不需要别的</td></tr>
<tr><td>转台视频（只有角色）</td><td><code>--turntable</code></td><td>同上</td></tr>
<tr><td>XPS</td><td><code>--xps</code></td><td>Blender2XPS，放在仓库旁边：<code>{b2x}</code> {b2x_mark}（别处就设 <code>BLENDER2XPS</code>）</td></tr>
<tr><td>PMX</td><td><code>--pmx</code></td><td>Blender 3.6 的插件 <code>mmd_tools</code>、<code>Convert_to_MMD5</code>、<code>mmd_cloth_physics</code>
（和 Taimanin Squad 的导出相同，装上就行，脚本自己启用）</td></tr></table></li>
<li>脚本复用了旁边两个目录的代码：<code>scripts\\taimaninsquad</code>（Blender 端和格式转换）和 <code>scripts\\actiontaimanin</code>
（读角色、材质）。三个目录要在一起。</li>
</ol></details>

<details open><summary>第 1 步　找到要导的模型</summary>
<p class="note">本页下面的「全部清单」按类别列出了 {total} 个带网格的对象，绿色的是已导出的。命令行里：</p>
{listing}
<p class="note"><b>id 就是 prefab 自己的名字</b>（<code>prf_asagi_costume_1</code>、<code>fbx_motorcycle_rig</code>），场景是
<code>scene_&lt;场景名&gt;</code>，场景里单独一个根物体是 <code>scene_&lt;场景名&gt;_&lt;根物体名&gt;</code>
（装好轮子的整辆摩托是 <code>scene_race_bridge_bikeobj</code>）。</p>
</details>

<details open><summary>第 2 步　导出</summary>
{exporting}
<h3>这条命令做了什么</h3>
<ol>
<li><b>读游戏数据</b>（Python + UnityPy，整个文件读进来约 15 秒）：按 id 找到 prefab，读出骨架、网格、材质的全部参数和贴图、
Dynamic Bone 的物理链；角色另外把脸部的表情动画片段做成形状键。临时放在 <code>{root}\\_work\\scenes\\&lt;id&gt;</code>（建好后删掉，<code>--keep-work</code> 保留）。</li>
<li><b>建 <code>.blend</code></b>（Blender 3.6 后台）：角色和载具用游戏的卡通着色（Toony Colors Pro 2）加描边；场景件是不受光的贴图 ×
烘焙光照图 + 发光图。渲预览图，贴图打包进文件 → <code>&lt;组&gt;\\blend\\&lt;id&gt;\\</code>。</li>
<li><code>--turntable</code>（角色）：转一圈 + 脸部特写的视频。</li>
<li><code>--xps</code>：Blender2XPS 导出，再读回 Blender 渲一张检查图 → <code>&lt;组&gt;\\xps\\&lt;id&gt;\\</code>。</li>
<li><code>--pmx</code>：角色转成 MMD 标准骨架，加物理（胸、头发）、切出 MMD 标准表情，再读回套舞蹈、渲表情表；
载具 / 道具 / 场景不是人形，保持游戏原来的骨头，没有 IK 和物理 → <code>&lt;组&gt;\\pmx\\&lt;id&gt;\\</code>。</li>
<li>数字记进 <code>{root}\\_meta\\exports.json</code>。</li>
</ol>
<p class="note">终端里看到的是这样（实测，阿莎姬全套，3 分 19 秒）。要看的是最后一行的 <code>0 failed</code> 和 PMX 那行的
<code>torn 0</code>、<code>grant violations 0</code>：</p>
<pre>{sample}</pre>
<p class="note">导出时可能出现的三句提示（都不是错）：<br>
<code>… material(s) lost their properties in the build - pictures taken by name</code>：这个材质在游戏的构建里被剥掉了着色器和全部参数
（残留布景），贴图是<b>按名字猜的</b>（<code>mat_x</code> → <code>tex_x</code>、<code>tex_x_lm</code>、<code>tex_x_e</code>）。<br>
<code>… left plain</code>：同上，但连同名的贴图也没有，这个材质是纯色的。<br>
<code>… carry Unity's default material - dressed as the game dresses the same mesh</code>：这个原始模型只挂着默认材质，
用的是游戏在别处（过场演出里）给同一个网格挂的材质 —— 运输机就是这样。</p>
</details>

<details open><summary>第 3 步　看结果、打开</summary>
<pre>{root}\\&lt;组&gt;\\                          &lt;组&gt; = 角色名（Asagi）或类别（Vehicles、Props、Levels、Scenes、Sets）
  blend\\&lt;id&gt;\\&lt;id&gt;.blend              贴图已打包；&lt;id&gt;_preview.png，角色另有 _face.png / _expressions.png / _turntable.mp4
  xps\\&lt;id&gt;\\&lt;id&gt;.xps + 贴图           &lt;id&gt;_xps_preview.png = 读回 Blender 的检查图
  pmx\\&lt;id&gt;\\&lt;id&gt;.pmx + textures\\      角色另有 preview.png / preview_dance.png / preview_morphs.png
{root}\\_meta\\exports.json、model_list.md     导出记录、全部对象的清单
{root}\\_work\\logs\\&lt;id&gt;.*.log         每一步的 Blender 日志（出问题时看）</pre>
<ul>
<li><b>.blend</b>：Blender 3.6 打开，视图着色切到「材质预览」或「渲染」。角色的表情在脸部网格的形态键里；转动 <code>TSQ_Sun</code> 物体改光照方向。</li>
<li><b>XPS</b>：XNALara XPS 里把 <code>.xps</code> 拖进窗口。</li>
<li><b>PMX</b>：MikuMikuDance 里拖进 <code>.pmx</code>。1 米 = 12.5 个 MMD 单位，所以摩托车和桥的大小和阿莎姬是配套的。</li>
</ul></details>

<details><summary>出问题时　终端里的这些话是什么意思</summary>
<table><tr><th>看到</th><th>意思和办法</th></tr>
<tr><td><code>data file not found: …</code></td><td>游戏不在默认位置：设 <code>TCOLLECTION_GAME_DIR</code> 为游戏文件夹</td></tr>
<tr><td><code>Blender not found: …</code></td><td>设 <code>TSQUAD_BLENDER</code> 为 <code>blender.exe</code> 的完整路径（要 3.6）</td></tr>
<tr><td><code>no model matches: xxx</code></td><td>id 写错了：<code>python list_models.py --find xxx</code></td></tr>
<tr><td><code>&lt;id&gt;: already exported (…) - --force to redo</code></td><td>不是错：<code>.blend</code> 已经有了。重做加 <code>--force</code></td></tr>
<tr><td><code>FAILED &lt;id&gt;: the prefab has no enabled renderer</code></td><td>这个对象里的网格都是关着的，没有东西可导</td></tr>
<tr><td><code>FAILED &lt;id&gt;: Blender failed for &lt;id&gt; (exit N), log: …</code></td><td>建 <code>.blend</code> 失败：看它给的日志最后几十行</td></tr>
<tr><td><code>! XPS failed: …</code> / <code>! PMX failed, log: …</code></td><td>看 <code>&lt;id&gt;.xps.log</code> / <code>&lt;id&gt;.pmx.log</code>；先确认第 0 步里的 Blender2XPS / 三个插件</td></tr>
<tr><td><code>PMX: not a human figure - …</code></td><td>不是错：载具、道具、场景都走这条路，骨头保持游戏原名，没有 IK 和物理</td></tr>
</table></details>

<details><summary>手工路线（不用脚本）</summary>
<p class="note">没有实测过。原理上：<code>data.unity3d</code> 是没加密的 UnityFS，AssetStudio 能打开，在 Asset List 里按 Mesh / Texture2D
筛选可以把网格和贴图导出来。但这是一份<b>不带类型树的玩家构建</b>，脚本组件（Dynamic Bone）它读不出来；材质要自己接
（<code>mat_asagi_*</code> → <code>tex_asagi_*</code>）；脸没有形态键，表情是动画片段。同一个阿莎姬在 Action Taimanin 里更完整，
手工步骤见那边的画廊页。</p></details>
""".format(data=esc(tcc.DATA_FILE), raw=counts.get("raw", 0), total=counts["total"],
           cd=commands([("cd " + scripts, "")]), full=commands([(full, "")]),
           refresh=commands([("python list_models.py --html", "")]),
           pip=commands([("pip install UnityPy lz4 numpy pillow", "")]),
           blender=esc(tc.BLENDER), blender_mark=mark(os.path.isfile(tc.BLENDER)),
           game=esc(tcc.GAME_DIR), game_mark=mark(os.path.isfile(tcc.DATA_FILE)), root=esc(root),
           b2x=esc(b2x), b2x_mark=mark(os.path.isdir(b2x)),
           listing=commands([
               ("python list_models.py", "全部 %d 个，按类别；最后一列是已导出的格式" % counts["total"]),
               ("python list_models.py --category prop level", "只看某几类"),
               ("python list_models.py --find asagi \"*truck*\"", "按 id / 角色名找，支持通配符"),
               ("python list_models.py --details", "多列出顶点 / 三角面 / 骨骼 / 材质（其中几个是默认 / 被剥掉的）/ 着色器"),
               ("python list_models.py --html", "重新生成本页"),
           ]),
           exporting=commands([
               ("python export_model.py prf_asagi_costume_1", "只出 <code>.blend</code> 和预览图，约 30 秒"),
               (full, "角色全套：<code>.blend</code> + XPS + PMX + 转台视频，约 3 分钟"),
               ("python export_model.py fbx_motorcycle_rig fbx_dropship_rig --xps --pmx", "一次几个"),
               ("python export_model.py --category vehicle prop scene --xps --pmx", "按类别"),
               ("python export_model.py --game", "游戏实际显示的全部（角色、载具、道具、赛道段、场景）；残留的不算"),
               ("python export_model.py prf_asagi_costume_1 --xps --pmx --force", "已经有的也重做"),
               ("python export_model.py prf_asagi_costume_1 --pmx --reconvert --bust amount=1.3",
                "只从现有的 <code>.blend</code> 重做 PMX，胸部幅度 1.3 倍"),
               ("python export_model.py scene_race_bridge --preview-view 1,0,0.3", "道具 / 场景的预览换个方向看"),
           ]),
           sample=esc(SAMPLE_RUN.format(root=root)))


def card(model: dict, entry: dict, root: str) -> str:
    blend_dir = tc.model_dir(model, root, "blend")
    pictures = [os.path.join(blend_dir, model["id"] + s) for s in ("_preview.png", "_face.png")]
    out = ['<div class="card">'] + [img(p) for p in pictures if os.path.isfile(p)]
    out.append('<div class="title">%s</div>' % html.escape(model["id"]))
    out.append('<div class="small">%s · 顶点 %s · 三角面 %s · 骨骼 %s · 材质 %s</div>' % (
        html.escape(tcc.CATEGORY_ZH.get(model["category"], model["category"]).split("（")[0]),
        entry.get("vertices", "?"), entry.get("faces", "?"), entry.get("bones", "?"),
        len(entry.get("materials_built") or {}) or "?"))
    rows = [link(blend_dir, "blend 文件夹")]
    for name, label in ((model["id"] + "_expressions.png", "形状键表"), (model["id"] + "_turntable.mp4", "转台视频")):
        if os.path.isfile(os.path.join(blend_dir, name)):
            rows.append(link(os.path.join(blend_dir, name), label))
    if "xps" in model["exported"]:
        xps_dir = tc.model_dir(model, root, "xps")
        rows.append(link(xps_dir, "xps 文件夹"))
        check = os.path.join(xps_dir, model["id"] + "_xps_preview.png")
        if os.path.isfile(check):
            rows.append(link(check, "xps 检查图"))
    if "pmx" in model["exported"]:
        pmx_dir = tc.model_dir(model, root, "pmx")
        rows.append(link(pmx_dir, "pmx 文件夹"))
        for name, label in (("preview.png", "pmx 检查图"), ("preview_dance.png", "舞蹈检查图"), ("preview_morphs.png", "表情表")):
            if os.path.isfile(os.path.join(pmx_dir, name)):
                rows.append(link(os.path.join(pmx_dir, name), label))
    out.append('<div class="small">%s</div>' % " · ".join(rows))
    report = entry.get("pmx_report") or {}
    if report:
        fit = (report.get("bust_springs") or [{}])[0]
        note = "pmx：骨骼 %s，刚体 %s" % (report.get("bones"), report.get("rigid_bodies"))
        if report.get("plain_rig"):
            note += "（不是人形：游戏原骨，没有 IK 和物理）"
        if fit.get("travel_cm"):
            note += "，胸部最多晃 ±%s cm" % fit["travel_cm"][0]
        if report.get("vertex_morphs"):
            note += "，表情 %d 个" % len(report["vertex_morphs"])
        out.append('<div class="small">%s</div>' % html.escape(note))
    for key, text in (("guessed_materials", "%d 个材质的贴图是按名字猜的"), ("plain_materials", "%d 个材质没有贴图，纯色"),
                      ("borrowed_materials", "%d 个部件借用了游戏在别处给同一网格的材质")):
        if entry.get(key):
            out.append('<div class="small">%s</div>' % html.escape(text % len(entry[key])))
    out.append("</div>")
    return "\n".join(out)


def chip(model: dict) -> str:
    d = model.get("details") or {}
    tip = "%s · %s" % (model["key"], " ".join(model["exported"]) or "未导出")
    if d.get("vertices"):
        tip += " · %s 顶点 / %s 三角面" % (d["vertices"], d.get("triangles"))
    return '<span class="chip%s" title="%s">%s</span>' % (" done" if model["exported"] else "", html.escape(tip),
                                                          html.escape(model["id"]))


def build(models: list[dict], root: str = tcc.EXPORT_ROOT, out: str | None = None) -> str:
    exports = {}
    path = os.path.join(tc.meta_dir(root), "exports.json")
    if os.path.isfile(path):
        exports = tc.load_json(path)
    order = {c: i for i, c in enumerate(SHOWN_FIRST)}
    done = sorted((m for m in models if m["exported"]), key=lambda m: (order.get(m["category"], 99), m["id"]))
    counts = {c: sum(1 for m in models if m["category"] == c) for c in tcc.CATEGORY_ORDER}
    counts["total"] = len(models)
    page = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>Taimanin Collection 模型</title>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<style>%s</style></head><body>" % CSS,
            "<h1>Taimanin Collection 的 3D 模型</h1>",
            '<p class="note">生成于 %s · 共 %d 个带网格的对象（%s），已导出 %d 个 · 导出目录 %s · '
            '<a href="#howto">怎么导出</a> · <a href="#done">已导出</a> · <a href="#all">全部清单</a></p>' % (
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), len(models),
                "、".join("%s %d" % (tcc.CATEGORY_ZH[c].split("（")[0], counts[c]) for c in tcc.CATEGORY_ORDER if counts[c]),
                len(done), link(root, root)),
            "<h2 id='howto'>怎么导出模型（操作说明）</h2>", howto(root, counts),
            "<h2 id='done'>已导出（%d）</h2>" % len(done), '<div class="cards">']
    page += [card(m, exports.get(m["id"], {}), root) for m in done]
    page += ["</div>", "<h2 id='all'>全部清单（%d）</h2>" % len(models),
             '<p class="note">绿色 = 已导出；鼠标停在上面看它在游戏数据里的路径。</p>']
    for cat in tcc.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if rows:
            page.append("<h3>%s（%d）</h3>" % (html.escape(tcc.CATEGORY_ZH[cat]), len(rows)))
            page.append('<div class="chips">%s</div>' % "".join(chip(m) for m in rows))
    page.append("<script>%s</script></body></html>" % SCRIPT)
    out = out or os.path.join(HERE, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(page))
    return out


if __name__ == "__main__":
    print(build(tcc.discover_models()))
