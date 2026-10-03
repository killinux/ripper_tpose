"""Gallery page of the Action Taimanin models: what was exported (with pictures and links into the export
folder) and the whole model list by category and character, with a how-to at the top.

    python list_models.py --html        # writes html/index.html next to this file and prints its path
"""
from __future__ import annotations

import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ataimanin_common as ac  # noqa: E402
from ataimanin_common import tc  # noqa: E402

CSS = """
body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#1c1d22;color:#ddd;margin:0;padding:0 24px 60px}
h1{font-size:24px;margin:22px 0 4px} h2{font-size:18px;margin:30px 0 10px;border-bottom:1px solid #444;padding-bottom:4px}
h3{font-size:14px;margin:14px 0 6px;color:#bbb} a{color:#8ec7ff;text-decoration:none} a:hover{text-decoration:underline}
.note{color:#aaa;font-size:13px;line-height:1.7} code{background:#2b2d35;padding:1px 5px;border-radius:3px;color:#e8d9a0}
pre{background:#2b2d35;padding:10px 14px;border-radius:5px;color:#e8d9a0;overflow-x:auto;font-size:12.5px;line-height:1.5}
details{background:#24262d;border-radius:6px;padding:8px 16px;margin:10px 0} summary{cursor:pointer;font-weight:600}
.cards{display:flex;flex-wrap:wrap;gap:14px} .card{background:#262830;border-radius:6px;padding:10px;width:300px}
.card img{width:140px;height:218px;object-fit:cover;border-radius:4px;background:#111;margin-right:4px}
.card .title{font-weight:600;margin:6px 0 2px} .card .small{font-size:12px;color:#aaa;line-height:1.6}
.chips{display:flex;flex-wrap:wrap;gap:5px} .chip{font-size:12px;background:#2b2d35;border-radius:10px;padding:2px 9px;color:#bbb}
.chip.done{background:#2f5a3a;color:#e6ffe9} table{border-collapse:collapse;font-size:13px}
td,th{border:1px solid #444;padding:4px 10px;text-align:left}
"""

HOWTO = """
<details open><summary>A. 用脚本（推荐）</summary>
<p class="note">脚本在 <code>scripts\\actiontaimanin\\</code>，游戏目录默认 <code>{game}</code>（环境变量 <code>ATAIMANIN_GAME_DIR</code> 可改），
导出目录默认 <code>{root}</code>（<code>ATAIMANIN_EXPORT_ROOT</code>）。只需要 Python（UnityPy、lz4、numpy、Pillow）和 Blender 3.6；不需要 key，不需要启动游戏。</p>
<pre>python list_models.py                         # 全部模型（1384 个），按类别
python list_models.py --find asagi            # 某个角色的全部模型
python list_models.py --details               # 顶点 / 面数 / 骨骼 / 材质 / 着色器（约 5 分钟，有缓存）
python list_models.py --html                  # 重新生成本页

python export_model.py asagi_costume_1_f                  # 导出一个：卡通材质的 .blend + 预览图
python export_model.py asagi_costume_1_f --xps --pmx      # 再出 XPS 和 MMD 的 PMX（带检查图）
python export_model.py asagi --xps --pmx --jobs 4         # 一个角色的全部服装，4 个并行
python export_model.py asagi_costume_1_f --pmx --reconvert --bust amount=1.3   # 只重做 PMX，胸部幅度 1.3 倍</pre>
<p class="note">结果：<code>&lt;导出目录&gt;\\&lt;角色&gt;\\blend|xps|pmx\\&lt;id&gt;\\</code>，每个文件夹可以单独打开（贴图已打包 / 已复制）。
模型 id 的含义：<code>&lt;角色&gt;_costume_&lt;编号&gt;_f</code> = 该角色穿第几套服装的展示用模型（身体 + 头发 + 脸已经拼好），
<code>&lt;角色&gt;_g / _l</code> = 战斗 / 大厅用的同一角色，<code>monster\\…</code> = 敌人。</p>
</details>
<details><summary>B. 不用脚本，手工看模型和导出（AssetStudio + Blender）</summary>
<p class="note">
1. 用 AssetStudio（或 AssetRipper）打开 <code>{game}\\ActionTaimanin_Data\\StreamingAssets\\AssetBundles\\pc\\</code> 里的
<code>unit</code>、<code>model_char</code>、<code>shader</code> 三个文件（一起加载，<code>model_char</code> 有 1 GB，要等一会；
<code>game</code> / <code>string</code> / <code>system</code> 是加密的数据表，打不开，模型用不到）。<br>
2. 在 Scene Hierarchy 里找 <code>&lt;角色&gt;_costume_&lt;n&gt;_F</code>（来自 <code>unit</code>），勾上它，Model → Export selected objects (merge) 导出 FBX；
贴图在 Asset List 里按 Texture2D 筛选、按名字 <code>tex_&lt;角色&gt;…</code> / <code>tex_costume_&lt;角色&gt;_&lt;n&gt;…</code> 导出。<br>
3. 一个角色的零件分开存放：身体在 <code>model_char/&lt;角色&gt;/costume_&lt;角色&gt;_&lt;n&gt;/</code>，脸和各套服装的头发在
<code>model_char/&lt;角色&gt;/body_&lt;角色&gt;/</code>；只有 <code>unit</code> 里的 prefab 把它们拼在一起，所以要从 prefab 导而不是单独导网格。<br>
4. FBX 导入 Blender 后：<code>fbx_&lt;角色&gt;_face_none</code> 是没有骨骼的备用脸、<code>emotion_shy</code> 是脸红贴片，隐藏即可；
Asagi 头两侧绕出去的两缕细发是角色本来的造型（Taimanin Squad 里的她也一样），不是导出错误。<br>
5. 材质要手工连：主贴图 <code>_MainTex</code>，阴影色是材质参数（TCP2 的 <code>_SColor</code> / UTS2 的 <code>_1st_ShadeColor</code>），
服装颜色来自 <code>_PartsColorMask</code> 三个通道 × <code>_PartsColorR/G/B</code>。脚本导出的 .blend 里这些已经连好。<br>
6. 表情：脸是骨骼驱动的（约 28 根脸部骨），没有 blend shape；手工摆表情就是在姿态模式里移动 <code>Bone_Face_*</code>。</p>
</details>
"""


def link(path: str, text: str) -> str:
    return '<a href="file:///%s">%s</a>' % (path.replace("\\", "/"), html.escape(text))


def img(path: str) -> str:
    return '<a href="file:///%s"><img src="file:///%s" loading="lazy"></a>' % ((path.replace("\\", "/"),) * 2)


def card(model: dict, entry: dict, root: str) -> str:
    blend_dir = tc.model_dir(model, root, "blend")
    pictures = [os.path.join(blend_dir, model["id"] + s) for s in ("_preview.png", "_face.png")]
    out = ['<div class="card">'] + [img(p) for p in pictures if os.path.isfile(p)]
    out.append('<div class="title">%s</div>' % html.escape(model["id"]))
    stats = "%s · 顶点 %s · 三角面 %s · 骨骼 %s" % (html.escape(model["name"]), entry.get("vertices", "?"),
                                              entry.get("faces", "?"), entry.get("bones", "?"))
    out.append('<div class="small">%s</div>' % stats)
    rows = [link(blend_dir, "blend 文件夹")]
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
        if fit.get("travel_cm"):
            note += "，胸部最多晃 ±%s cm（系数 %s）" % (fit["travel_cm"][0], fit.get("factor"))
        out.append('<div class="small">%s</div>' % html.escape(note))
    out.append("</div>")
    return "\n".join(out)


def build(models: list[dict], root: str = ac.EXPORT_ROOT) -> str:
    exports = {}
    path = os.path.join(tc.meta_dir(root), "exports.json")
    if os.path.isfile(path):
        exports = tc.load_json(path)
    done = [m for m in models if m["exported"]]
    page = ["<!doctype html><html lang='zh'><head><meta charset='utf-8'><title>Action Taimanin 模型</title>",
            "<style>%s</style></head><body>" % CSS,
            "<h1>Action Taimanin（アクション対魔忍）模型</h1>",
            '<p class="note">共 %d 个模型（%s），已导出 %d 个。导出目录 %s</p>' % (
                len(models), "、".join("%s %d" % (ac.CATEGORY_ZH[c].split("（")[0], sum(1 for m in models if m["category"] == c))
                                     for c in ac.CATEGORY_ORDER), len(done), link(root, root)),
            "<h2>怎么看模型、怎么导出</h2>", HOWTO.format(game=html.escape(ac.GAME_DIR), root=html.escape(root)),
            "<h2>已导出（%d）</h2>" % len(done), '<div class="cards">']
    page += [card(m, exports.get(m["id"], {}), root) for m in done]
    page.append("</div>")
    for cat in ac.CATEGORY_ORDER:
        rows = [m for m in models if m["category"] == cat]
        if not rows:
            continue
        page.append("<h2>%s（%d）</h2>" % (html.escape(ac.CATEGORY_ZH[cat]), len(rows)))
        groups: dict[str, list[dict]] = {}
        for m in rows:
            groups.setdefault(m["group"] if cat in ("figure", "character") else cat, []).append(m)
        for group, items in groups.items():
            if cat in ("figure", "character"):
                page.append("<h3>%s（%d）</h3>" % (html.escape(group), len(items)))
            page.append('<div class="chips">%s</div>' % "".join(
                '<span class="chip%s" title="%s">%s</span>' % (
                    " done" if m["exported"] else "", html.escape(" ".join(m["exported"]) or "未导出"), html.escape(m["id"]))
                for m in items))
    page.append("</body></html>")
    out = os.path.join(HERE, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(page))
    return out


if __name__ == "__main__":
    print(build(ac.discover_models()))
