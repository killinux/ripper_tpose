"""把 AION2 的模型做成一页可浏览的 HTML：导出过的模型显示预览图和 .blend 的位置；游戏里全部 6,426 个模型按类别列出、
可搜索、可只看女性，每个都带它自己的导出命令；页首是「怎么导出模型」的操作说明 —— 最短的三条命令，然后一步一步：
准备什么、怎么找模型、导出命令做了什么、结果怎么看怎么打开、出问题时终端里的话是什么意思。

页面用 ``file://`` 链接指向本机真实文件；缩略图写在导出根目录的 ``_meta\\gallery`` 下，
**任何游戏素材都不会进仓库** —— 和这里其它游戏的画廊同一条规矩。每次导出之后重跑即可。

数据来源：
  <导出根>\\_meta\\aion2_models.json   模型总目录（list_models.py --catalogue；没有时本脚本自己调它生成）
  <导出根>\\blend\\<输出名>\\            每次导出的 spec.json、build.log（AION2_REPORT 一行）、三张预览图

用法：
  python make_gallery.py                 # 生成本脚本旁的 index.html
  python make_gallery.py --force         # 缩略图全部重做
  python make_gallery.py --export-root D:\\别的导出目录
"""
import argparse
import datetime
import html
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import aion2_pak as pak  # noqa: E402
import export_model as em  # noqa: E402
import list_models as lm  # noqa: E402

THUMB_WIDTH = 520
THUMB_QUALITY = 84
PAGE_NAME = "index.html"

KIND_ZH = {
    "outfit": "盔甲套装", "costume": "时装", "hat": "帽子", "polymorph": "变身套装", "outfit_common": "共用部件",
    "base": "底模", "head": "脸", "hair": "发型", "acc": "饰品", "beard": "胡子", "player_misc": "玩家杂项",
    "weapon": "武器", "wing": "翅膀", "shoulderwear": "肩饰", "headwear": "头饰",
    "npc": "NPC", "monster": "怪物", "monster_starter": "新手区怪物", "veh": "坐骑 / 宠物", "etc": "道具外观",
    "other_skeletal": "过场 / 摆设 / 其他", "test": "测试", "nude": "裸体（拼出来的）",
}
# 按钮一组一个；没列到的类别归进「其他」
CHIP_GROUPS = [
    ("player", "玩家穿戴", ("outfit", "costume", "hat", "polymorph")),
    ("look", "脸 / 发型", ("head", "hair")),
    ("npc", "NPC", ("npc",)),
    ("monster", "怪物", ("monster", "monster_starter")),
    ("cine", "过场 / 摆设", ("other_skeletal",)),
    ("weapon", "武器", ("weapon",)),
    ("acc", "饰品 / 翅膀", ("acc", "wing", "shoulderwear", "headwear")),
    ("other", "其他", ()),
]
WHY_ZH = {"name": "名字里的 F_ / …F", "player parts": "用了玩家女性（GF）的部件", "chest bones": "骨架里有女性胸部骨"}

# 2026-10-25 实测：一个全新的空导出目录，先 list_models.py --scan（53 秒），再导 NPC_Yustiel_01（111 秒）
SAMPLE_SCAN = """scanning 480500 package headers with 6 workers ...
  40000/480500 packages, 4656/s, 95 s left
  ...
  440000/480500 packages, 10186/s, 4 s left
packages scanned: 480500   SkeletalMesh 9822   StaticMesh 9610   ...
(下面是各类模型的数量表，最后一行 total 6426 9822)"""
SAMPLE_RUN = """NPC_Yustiel_01 (npc -): 5 parts
  umodel AION2/Character/NPC/Humanform/Yustiel/Yustiel_01/NPC_Yustiel_01_Body: Exported 48/48 objects in 0.9 sec
  umodel AION2/Character/NPC/Humanform/Yustiel/Yustiel_01/NPC_Yustiel_01_Pants: Exported 48/48 objects in 0.8 sec
  umodel AION2/Character/NPC/Humanform/Yustiel/Yustiel_01/NPC_Yustiel_01_Head: Exported 72/72 objects in 1.4 sec
  umodel AION2/Character/NPC/Humanform/Yustiel/Yustiel_01/NPC_Yustiel_01_Hair: Exported 32/32 objects in 0.8 sec
  umodel AION2/Character/NPC/Humanform/Yustiel/Yustiel_01/NPC_Yustiel_01_Gloves: Exported 40/40 objects in 0.8 sec
UE Viewer: 5/5 parts in 75 s
baking 7 materials
  MI_NPC_Yustiel_01_Body       armor    ok
  GF_BaseBody                  skin     ok
  MI_NPC_Yustiel_01_Head       face     ok
  MI_NPC_Yustiel_01_Eye_AO     eye_ao   ok
  MI_EyeAO_Tear                tear     ok
  MI_NPC_Yustiel_01_Eye        eye      ok
  MI_NPC_Yustiel_01_Hair       hair     ok
[aion2] imported Body: 146 bones, 28036 verts
[aion2] imported Pants: 32 bones, 3824 verts
[aion2] imported Head: 174 bones, 8579 verts
[aion2] imported Hair: 10 bones, 31023 verts
[aion2] imported Gloves: 36 bones, 1690 verts
[aion2] rig: 315 bones (141 added), max rest deviation 0.002, reposed none
[aion2] materials: MI_NPC_Yustiel_01_Body=armor, GF_BaseBody=skin, MI_NPC_Yustiel_01_Head=face, ...
[aion2] saved {out}\\blend\\NPC_Yustiel_01\\NPC_Yustiel_01.blend
[aion2] rendered {out}\\blend\\NPC_Yustiel_01\\preview.png
[aion2] rendered {out}\\blend\\NPC_Yustiel_01\\preview_face.png
[aion2] rendered {out}\\blend\\NPC_Yustiel_01\\preview_back.png
Blender: 22 s, 0 warnings
done: {out}\\blend\\NPC_Yustiel_01\\NPC_Yustiel_01.blend"""


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


def load_catalogue(root):
    """aion2_models.json -> {id: model}; written by list_models.py --catalogue (run here when it is missing)."""
    path = os.path.join(root, "_meta", "aion2_models.json")
    if not os.path.isfile(path):
        print("no catalogue yet - running list_models.py --catalogue ...", flush=True)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "list_models.py"), "--catalogue", "--export-root", root])
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["models"]
    except (OSError, ValueError, KeyError):
        return {}


def read_report(build_log):
    """The AION2_REPORT line export_model.py writes at the end of build.log (None when the build failed)."""
    try:
        with open(build_log, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("AION2_REPORT="):
                    return json.loads(line[len("AION2_REPORT="):])
    except (OSError, ValueError):
        pass
    return None


def collect_exports(root, force=False):
    """One row per <root>\\blend\\<output>\\ that has a spec.json."""
    rows = []
    blend_root = os.path.join(root, "blend")
    thumbs = os.path.join(root, "_meta", "gallery", "thumbs")
    for name in sorted(os.listdir(blend_root)) if os.path.isdir(blend_root) else []:
        d = os.path.join(blend_root, name)
        try:
            with open(os.path.join(d, "spec.json"), encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        blend = os.path.join(d, name + ".blend")
        shots = {k: os.path.join(d, f) for k, f in (("front", "preview.png"), ("back", "preview_back.png"),
                                                     ("face", "preview_face.png"), ("sheet", "preview_sheet.jpg"))}
        shots = {k: v for k, v in shots.items() if os.path.isfile(v)}
        closeups = sorted(os.path.join(d, "closeups", f) for f in os.listdir(os.path.join(d, "closeups"))
                          if f.lower().endswith((".jpg", ".png"))) if os.path.isdir(os.path.join(d, "closeups")) else []
        rows.append({"name": name, "dir": d, "spec": spec, "report": read_report(os.path.join(d, "build.log")),
                     "blend": blend if os.path.isfile(blend) else "",
                     "blend_size": os.path.getsize(blend) if os.path.isfile(blend) else 0,
                     "shots": shots, "closeups": closeups,
                     "thumb": build_thumb(shots.get("front"), os.path.join(thumbs, name + ".jpg"), force),
                     "mtime": os.path.getmtime(blend) if os.path.isfile(blend) else 0})
    return rows


def chip_of(kind):
    for key, _label, kinds in CHIP_GROUPS:
        if kind in kinds:
            return key
    return "other"


def rebuild_command(spec):
    cmd = "python export_model.py " + spec.get("model", "")
    g = spec.get("gender") or ""
    if spec.get("head") and spec["head"] != lm.DEFAULT_HEAD.get(g):
        cmd += " --head " + spec["head"]
    if spec.get("hair") and spec["hair"] != lm.DEFAULT_HAIR.get(g):
        cmd += " --hair " + spec["hair"]
    name = os.path.basename(spec.get("out_dir", ""))
    if name.endswith("__B") or "__B__" in name:
        cmd += " --variant B"
    return cmd


def render_card(row, catalogue):
    esc = html.escape
    spec, rep = row["spec"], row["report"] or {}
    model = spec.get("model", row["name"])
    entry = catalogue.get(model) or {}
    kind = spec.get("kind") or entry.get("kind", "")
    sex = "F" if spec.get("gender") == "GF" or entry.get("sex") == "F" or model.startswith("GF_") else ""
    badges = '<span class="badge badge-kind">%s</span>' % esc(KIND_ZH.get(kind, kind))
    if sex == "F":
        badges += '<span class="badge badge-f">♀</span>'
    if row["blend"]:
        badges += '<a class="badge badge-fmt" href="%s" title="%s">blend</a>' % (esc(file_uri(row["dir"])), esc(row["dir"]))
    if row["thumb"]:
        figure = '<a class="shot" href="%s" target="_blank" rel="noopener" title="点击看原图"><img loading="lazy" src="%s" alt="%s"></a>' % (
            esc(file_uri(row["shots"]["front"])), esc(file_uri(row["thumb"])), esc(row["name"]))
    else:
        figure = '<div class="shot"><div class="noimg">没有预览图（build.log 里看原因）</div></div>'
    parts = rep.get("parts") or []
    rig = rep.get("rig") or {}
    spec_line = "%d 个部件 · %s 骨 · %s 顶点 · %d 个材质" % (
        len(parts), rig.get("bones", "?"), "{:,}".format(sum(p.get("vertices", 0) for p in parts)),
        len(rep.get("materials") or {})) if rep else "没有 AION2_REPORT（Blender 那一步没跑完）"
    lines = ['<dt>模型</dt><dd><code>%s</code> <span class="muted">%s</span></dd>' % (
        esc(model), esc(" ".join(p["name"] for p in spec.get("parts", []))))]
    if spec.get("head") or spec.get("hair"):
        lines.append('<dt>脸发</dt><dd><code>%s</code> · <code>%s</code></dd>' % (esc(spec.get("head") or "-"), esc(spec.get("hair") or "-")))
    lines.append('<dt>规格</dt><dd>%s</dd>' % esc(spec_line))
    command = rebuild_command(spec)
    lines.append('<dt>命令</dt><dd><code>%s</code> <button class="copy" data-copy="%s">复制</button></dd>' % (esc(command), esc(command)))
    if row["blend"]:
        lines.append('<dt>blend</dt><dd><a href="%s" title="%s">%s</a> <span class="muted">%s</span> '
                     '<button class="copy" data-copy="%s">复制</button></dd>' % (
                         esc(file_uri(row["blend"])), esc(row["blend"]), esc(os.path.basename(row["blend"])),
                         human_size(row["blend_size"]), esc(row["blend"])))
    links = []
    for key, label in (("back", "背面"), ("face", "脸部"), ("sheet", "总图")):
        if key in row["shots"]:
            links.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(file_uri(row["shots"][key])), label))
    for c in row["closeups"]:
        links.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (
            esc(file_uri(c)), esc(os.path.splitext(os.path.basename(c))[0].replace("_closeups", "") + "近景")))
    links.append('<a href="%s">build.log</a>' % esc(file_uri(os.path.join(row["dir"], "build.log"))))
    lines.append('<dt>图</dt><dd>%s</dd>' % " · ".join(links))
    warnings = rep.get("warnings") or []
    notes = [n for n in spec.get("notes", [])]
    if warnings or notes:
        lines.append('<dt>提示</dt><dd class="muted">%s</dd>' % esc("；".join(warnings + notes))[:600])
    when = datetime.datetime.fromtimestamp(row["mtime"]).strftime("%m-%d %H:%M") if row["mtime"] else ""
    search = esc(" ".join([row["name"], model, kind, KIND_ZH.get(kind, "")]).lower())
    return """      <article class="card" data-search="{search}" data-chip="{chip}" data-female="{fem}">
        {figure}
        <div class="body">
          <div class="titlerow"><h3>{name}</h3>{badges}<span class="muted when">{when}</span></div>
          <dl>
            {lines}
          </dl>
        </div>
      </article>
""".format(search=search, chip=chip_of(kind), fem="1" if sex == "F" else "0", figure=figure, name=esc(row["name"]),
           badges=badges, when=esc(when), lines="\n            ".join(lines))


def model_rows(catalogue, exports):
    """Compact rows for the full list (rendered by the page's script): [id, kind, sex, parts, folder, exported] -
    exported models first, then player wearables, faces / hair, NPCs, monsters ... (CHIP_GROUPS order)."""
    done = {}
    for r in exports:
        done.setdefault(r["spec"].get("model", ""), []).append(r["name"])
    order = {key: i for i, (key, _label, _kinds) in enumerate(CHIP_GROUPS)}
    rows = []
    for mid, m in sorted(catalogue.items(), key=lambda kv: (0 if kv[0] in done else 1,
                                                            order[chip_of(kv[1].get("kind", ""))], kv[0].lower())):
        folder = m.get("folder", "")
        for prefix in ("AION2/Content/Character/", "AION2/Content/", "AION2/"):
            if folder.startswith(prefix):
                folder = folder[len(prefix):]
                break
        rows.append([mid, m.get("kind", ""), m.get("sex", ""), len(m.get("parts", [])), folder,
                     ", ".join(done.get(mid, []))])
    return rows


def command_rows(rows):
    esc = html.escape
    return "\n".join('      <div class="cmd"><code>%s</code><button class="copy" data-copy="%s">复制</button>'
                     '<span class="what">%s</span></div>' % (esc(c), esc(c), what) for c, what in rows)


def mark(found):
    return '<span class="ok">本机已有</span>' if found else '<span class="no">本机没找到</span>'


def python_has(*modules):
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in modules)


def render_howto(root, counts):
    esc = html.escape
    out = esc(root)
    key_file = pak.DEFAULT_KEY_FILE
    key_ok = bool(os.environ.get("AION2_AES_KEY")) or os.path.isfile(key_file)
    addon_dir = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "3.6", "scripts", "addons")
    psk_ok = os.path.isdir(os.path.join(addon_dir, "io_scene_psk_psa"))
    listing = command_rows([
        ("python list_models.py", "全部模型按类别和性别计数（共 %s 个）" % "{:,}".format(counts["total"])),
        ("python list_models.py --find yustiel leda siel", "按名字找，列出 id 里含任一个词的；支持 <code>*</code> <code>?</code> 通配符（<code>--find \"gf_*maid*\"</code>）"),
        ("python list_models.py --women --kind npc", "女性 NPC（%d 个，含修果族等非人类；儿童不算）" % counts["female_npc"]),
        ("python list_models.py --kind costume --gender GF", "女性时装（%d 套）；<code>--kind outfit</code> 是编号盔甲套装" % counts["gf_costume"]),
        ("python list_models.py --kind hair --gender GF", "女性发型（%d 款）；<code>--kind head</code> 是脸（%d 张）" % (counts["gf_hair"], counts["gf_head"])),
        ("python list_models.py --resolve GF_Angel_01", "一个模型由哪些部件拼成（导出时会用到哪些游戏包）"),
        ("python list_models.py --catalogue", "重写模型总目录 <code>_meta\\aion2_models.json</code>（本页读它）"),
    ])
    basic = command_rows([
        ("python export_model.py NPC_Yustiel_01", "一个 NPC，原样导出（身体、头、头发都是它自己的）"),
        ("python export_model.py GF_Angel_01", "一套女性时装：自动配上 001 号脸、001 号发型；时装没有的身体部位用底模补"),
        ("python export_model.py GF_Angel_01 --hair GF_Hair_308 --head GF_Head_006",
         "换发型、换脸；输出文件夹名会加后缀（<code>GF_Angel_01__Head_006__Hair_308</code>）"),
        ("python export_model.py GF_Cat_03 --variant B", "同一部位有 A / B 两版的（猫咪装、企鹅装的兜帽）用 B 版，默认 A"),
        ("python export_model.py GF_0001_T04 --keep-hair",
         "全盔默认会按游戏的设置换成贴头皮的短发或剪掉头顶的头发；加这个保留原发型"),
    ])
    nude = command_rows([
        ("python nude_survey.py --gender GF --write", "只做一次：量出底子的开口、存各套时装的皮肤做参考（约 15 秒）"),
        ("python export_model.py GF_Nude --hair GF_Hair_308", "裸体 + 001 号脸 + 308 号头发（约 1 分钟）"),
    ])
    redo = command_rows([
        ("python export_model.py NPC_Leda_01 --force", "从游戏重新导出这个模型的全部部件和贴图（游戏更新后用）"),
        ("python export_model.py NPC_Leda_01 --no-preview", "只出 <code>.blend</code>，不渲预览图"),
        ("python export_model.py NPC_Leda_01 --no-blend", "只做 UE Viewer 导出和材质烘焙，不开 Blender"),
    ])
    batch = command_rows([
        ('foreach ($m in "NPC_Yustiel_01", "NPC_Leda_01", "NPC_Siel_01") { python export_model.py $m }',
         "一次几个（PowerShell）。一个一个按顺序导，每个 1–2 分钟"),
    ])
    return """  <section class="howto" id="howto">
    <h2>怎么导出模型（操作说明）</h2>
    <p>下面列的是游戏里的全部 3D 模型。<b>导出</b> = 从游戏的资源包里读出网格、骨架、材质参数和贴图，
      做成能直接打开的 <code>.blend</code>（材质已经烘成普通的颜色 / 粗糙度 / 金属度 / 法线贴图），并渲三张检查图。
      不用启动游戏、不用联网；需要一把 AES 密钥（第 0 步）。脚本都在 <code>{scripts}</code>。</p>

    <div class="quick">
      <b>最短的路：三条命令</b> <span class="muted">（第一次用，先做下面的「第 0 步」）</span>
      <ol>
        <li>打开 PowerShell，进到脚本目录：
{cd}</li>
        <li>导出一个模型。这里是 Yustiel；换别的就把 <code>NPC_Yustiel_01</code> 换成它的 id ——
          <b>下面「全部模型」每一行的「复制」就是它自己的这条命令</b>：
{full}
          约 2 分钟。最后一行是 <code>done: …\\NPC_Yustiel_01.blend</code> 就成了。</li>
        <li>刷新本页：「已导出」里会多出这张卡片（预览图、<code>.blend</code> 的位置）。
{refresh}</li>
      </ol>
    </div>

    <details open>
      <summary>第 0 步　准备（只做一次）</summary>
      <ol>
        <li><b>Python 3</b> 和三个包：<code>numpy</code>、<code>Pillow</code>、<code>cryptography</code> {py_mark}
{pip}</li>
        <li><b>游戏</b>装在 <code>{game}</code> {game_mark}（别处就在命令后面加 <code>--game-root 路径</code>）。</li>
        <li><b>AES 密钥</b>：一行 <code>0x…</code> 写在 <code>{key}</code>，或者放进环境变量 <code>AION2_AES_KEY</code> {key_mark}。
          游戏的资源包是加密的，没有它什么都读不出来。密钥<b>不进仓库</b>，从哪来、游戏更新后怎么判断它失效了，见
          <a href="{readme}">README</a> 的「容器和密钥」一节。</li>
        <li><b>Oodle 解压库</b> <code>{oodle}</code> {oodle_mark}（<code>--oodle</code> 可改）。</li>
        <li><b>UE Viewer 的 UE5 特制版</b>（Gildor 论坛 spiritovod 的版本）<code>{umodel}</code> {umodel_mark}（<code>--umodel</code> 可改）。
          普通版的 UE Viewer 读不了这个游戏。</li>
        <li><b>Blender 3.6</b> <code>{blender}</code> {blender_mark}（<code>--blender</code> 可改），装好 PSK 导入插件
          <code>io_scene_psk_psa</code> {psk_mark}（插件装上就行，脚本运行时自己启用）。</li>
        <li><b>建索引</b>：读一遍游戏里全部 48 万个包的包头，记下每个包是什么（网格、贴图、材质……），再写模型总目录。
{scan}
          实测（全新的空目录）：第一条 53 秒，第二条十几秒。游戏更新后第一条要重跑（会提示 <code>class cache is from another game version</code>）。
          <pre>{sample_scan}</pre></li>
      </ol>
      <p>准备好以后，<code>{out}\\_meta</code> 里有：<code>aion2_classes.json</code>（包的类型，约 50 MB）、
        <code>aion2_models.json</code>（模型总目录）、<code>aion2_genders.json</code>（NPC 和怪物的性别判断）。</p>
    </details>

    <details open>
      <summary>第 1 步　找到要导的模型</summary>
      <p><b>在这一页找：</b>工具栏的搜索框输名字（英文 id 里的一段，例如 <code>leda</code>、<code>angel</code>、<code>maid</code>）；
        类别按钮、「只看女性」「只看已导出」可以叠加。「全部模型」每一行最后是导出命令，点「复制」。</p>
      <p><b>在命令行找：</b></p>
{listing}
      <p><b>id 的规则</b>：</p>
      <table class="list">
        <tr><th>类别</th><th>id 的样子</th><th>说明</th></tr>
        <tr><td>玩家的套装</td><td><code>GF_0001_T04</code>、<code>GF_Angel_01</code></td>
          <td><code>GF</code> = 女、<code>GM</code> = 男。编号盔甲 = <code>&lt;性别&gt;_&lt;编号&gt;_T&lt;阶&gt;</code>；时装用英文名（Angel、Maid、Qipao、Swimsuit_07……）。
            导出时自动配脸和发型</td></tr>
        <tr><td>脸、发型</td><td><code>GF_Head_001</code>、<code>GF_Hair_308</code></td><td>给套装用的 <code>--head</code> / <code>--hair</code>；也能单独导</td></tr>
        <tr><td>NPC</td><td><code>NPC_Yustiel_01</code>、<code>NPC_F_Refugee_01</code></td>
          <td>有名字的角色用名字；路人用 <code>NPC_F_…</code>（女）/ <code>NPC_M_…</code>（男）</td></tr>
        <tr><td>怪物、Boss</td><td><code>MOB_Cromede_01</code></td><td><code>_V01</code>、<code>_CV01</code> 是换色 / 变体</td></tr>
        <tr><td>过场动画里的</td><td><code>NPC_Siel_01</code>、<code>Seq_Cromede_01_V02_Body</code></td><td>用游戏里的文件名；有些只有身体或只有头</td></tr>
      </table>
      <p><b>「女性」怎么认的</b>：玩家部件看 <code>GF</code>；NPC、怪物、过场模型游戏里没有性别字段，按顺序看四条，先成立的算数：
        ① 名字里有 <code>F_</code> / <code>M_</code>；② 名字里的词以 F / M 结尾（<code>VillagerF</code>、<code>ShugoAF</code>）；
        ③ 网格用了玩家女性的部件（Yustiel 的脸、Leda 的头发都是玩家的）；④ 骨架里有女性的胸部骨。名字或文件夹里有 Kid / Child 的是儿童，
        不算进「女性」。全部模型里每一行的 ♀ 悬停能看到是按哪一条认的。没逐个看图，可能差一两个。</p>
    </details>

    <details open>
      <summary>第 2 步　导出</summary>
      <h3>一个模型</h3>
{basic}
      <h3>这条命令做了什么</h3>
      <ol>
        <li><b>拼部件</b>（<code>list_models.resolve</code>）：找出这个模型由哪些网格组成。玩家套装 = 套装的身体、裤子、手套、鞋、头盔、肩甲、披风
          + 脸 + 发型；套装没有身体 / 裤子时用底模补。戴全盔时按游戏的设置换发型或剪头发。</li>
        <li><b>UE Viewer 导出</b>：每个部件调一次 UE Viewer，导出网格（<code>.psk</code>）、材质参数（<code>.props.txt</code>）和贴图（<code>.png</code>）
          到 <code>{out}\\umodel_exports</code>（已经有的跳过）。第一次每个部件 10–20 秒（实测 Yustiel 5 个部件 75 秒），之后几乎不花时间。</li>
        <li><b>烘材质</b>（<code>bake_materials.py</code>）：游戏的材质是运行时合成的，直接用导出的贴图是灰的。按材质类型（盔甲染色、皮肤、脸和眉毛、
          眼球、睫毛、头发）算成普通的颜色 / ORM / 自发光贴图 → <code>&lt;输出&gt;\\textures\\</code>，记录在 <code>materials.json</code>。</li>
        <li><b>建 .blend</b>（Blender 3.6 在后台运行，20–80 秒）：导入各部件，按骨骼名把骨架合成一副，接上材质，保存，渲正面、背面、脸部三张图。</li>
      </ol>
      <p>终端里看到的是这样（实测：全新的导出目录，第 0 步之后，从头到尾 111 秒）：</p>
      <pre>{sample}</pre>
      <p>要看的是：<code>UE Viewer: 5/5 parts</code>（分子分母相等 = 部件都导出来了）、材质那几行都是 <code>ok</code>、
        <code>Blender: … 0 warnings</code>，最后一行 <code>done:</code>。</p>
      <h3>裸体</h3>
      <p>游戏里没有现成的裸体，<code>GF_Nude</code> 是用内衣时装的皮肤、别的时装露出来的皮肤和商店人台拼出来的（做法见 README 的「裸体版本」）：</p>
{nude}
      <h3>重做、只做一部分</h3>
{redo}
      <h3>一次导几个</h3>
{batch}
    </details>

    <details open>
      <summary>第 3 步　看结果、打开</summary>
      <pre>{out}\\blend\\&lt;输出名&gt;\\               输出名 = 模型 id，换了脸 / 发型 / B 版时加后缀（GF_Angel_01__Hair_308）
  &lt;输出名&gt;.blend                     一副骨架 + 各部件网格 + 材质；贴图在旁边的 textures\\（相对路径：整个文件夹一起拷走）
  preview.png / preview_back.png / preview_face.png    正面、背面全身和脸部（本页卡片上的图）
  materials.json                     每个材质的类型和烘焙结果
  spec.json / build.log              用了哪些部件、提示和告警；build.log 最后一行 AION2_REPORT 是骨骼数、顶点数
{out}\\umodel_exports\\                 UE Viewer 导出的原始网格、材质参数、贴图（缓存；删了下次会重新导）
{out}\\_meta\\                          索引、模型总目录、性别判断；gallery\\thumbs\\ 是本页的缩略图</pre>
      <ul>
        <li><b>先看检查图</b>：卡片上的大图是正面，「图」一行有背面、脸部；看有没有缺部件、没贴图的面（洋红或纯灰）、头发是不是方块。</li>
        <li><b>打开 .blend</b>：Blender 3.6 双击打开，视图着色切到「材质预览」。骨架是 <code>Bip001</code>（3ds Max Biped 的骨骼名），
          各部件是 <code>&lt;输出名&gt;_Body</code>、<code>_Head</code>、<code>_Hair</code>…… 角色面朝 -Y，单位厘米。
          材质只用 Principled BSDF + 烘好的贴图，所以换引擎、转格式都能直接用。</li>
        <li>XPS / PMX 还没做（要的话说一声）。</li>
      </ul>
    </details>

    <details>
      <summary>第 4 步　出问题时：终端里的话是什么意思</summary>
      <table class="list">
        <tr><th>看到</th><th>意思</th><th>怎么办</th></tr>
        <tr><td><code>no class cache yet: run python list_models.py --scan first</code></td><td>还没建索引</td><td>做第 0 步最后一条</td></tr>
        <tr><td><code>class cache is from another game version - run with --scan</code></td><td>游戏更新过</td><td><code>python list_models.py --scan</code>，再 <code>--catalogue</code></td></tr>
        <tr><td><code>encrypted container needs the AES key</code></td><td>找不到密钥</td><td>第 0 步第 3 条</td></tr>
        <tr><td>解出 0 个路径、包头读出来是乱码</td><td>密钥不对（游戏更新换了密钥）</td><td>README「容器和密钥」：找新的公开密钥</td></tr>
        <tr><td><code>AION2 Paks folder not found</code></td><td>游戏不在默认位置</td><td>加 <code>--game-root</code></td></tr>
        <tr><td><code>unknown model or part …</code></td><td>id 拼错了，或 <code>--head</code> / <code>--hair</code> 给的不存在</td><td><code>python list_models.py --find 名字的一段</code></td></tr>
        <tr><td><code>umodel …: nothing exported</code> 和 <code>MISSING PSK for &lt;部件&gt;</code></td><td>UE Viewer 没读出这个部件</td>
          <td>这个部件会缺，其余照常；检查 UE Viewer 是不是特制版、密钥对不对</td></tr>
        <tr><td><code>material … not exported by UE Viewer</code></td><td>这个材质没导出来</td><td>那块面是灰的；<code>--force</code> 重导一次</td></tr>
        <tr><td><code>eyebrow texture slice N not found</code></td><td>眉毛贴图缺这一张</td><td>脸上没有画眉毛，其余正常</td></tr>
        <tr><td><code>Blender failed (rc N)</code> 加 25 行日志</td><td>Blender 那一步出错</td><td>看日志最后几行；常见的是 Blender 路径不对、PSK 插件没装</td></tr>
        <tr><td><code>no nude recipe yet: run python nude_survey.py …</code></td><td>要先量一次底子</td><td>照提示跑那条命令</td></tr>
      </table>
    </details>

    <details>
      <summary>已知的不足</summary>
      <ul>
        <li>脸部妆容只做了眉毛（眼影、眼线、唇妆图层没烘）；捏脸变形（MorphTarget）UE Viewer 导不出来，所以没有表情。</li>
        <li>NPC 的头发如果用的是玩家发型（Leda），颜色是那款发型材质的默认色，游戏里 NPC 可能另外调过。</li>
        <li>有些 NPC 文件夹里只有头或只有头盔（Grisilla、Chloris），剩下的部分游戏是按 NPC 外观数据拼的，这部分数据还没解。</li>
        <li>自发光（光环、Siel 裙子上的亮片）按材质里的强度烘，静止的图里会比游戏里亮；在 Blender 材质里调 Emission Strength。</li>
        <li>完整清单见 <a href="{readme}">README</a> 的「已知限制」。</li>
      </ul>
    </details>
  </section>
""".format(
        scripts=esc(SCRIPTS), out=out, readme=esc(file_uri(os.path.join(SCRIPTS, "README.md"))),
        cd=command_rows([("cd " + SCRIPTS, "")]),
        full=command_rows([("python export_model.py NPC_Yustiel_01", "")]),
        refresh=command_rows([("python html\\make_gallery.py", "约 5 秒")]),
        pip=command_rows([("pip install numpy pillow cryptography", "")]), py_mark=mark(python_has("numpy", "PIL", "cryptography")),
        game=esc(pak.DEFAULT_GAME_ROOT), game_mark=mark(os.path.isdir(pak.DEFAULT_GAME_ROOT)),
        key=esc(key_file), key_mark=mark(key_ok),
        oodle=esc(pak.DEFAULT_OODLE), oodle_mark=mark(os.path.isfile(pak.DEFAULT_OODLE)),
        umodel=esc(em.DEFAULT_UMODEL), umodel_mark=mark(os.path.isfile(em.DEFAULT_UMODEL)),
        blender=esc(em.DEFAULT_BLENDER), blender_mark=mark(os.path.isfile(em.DEFAULT_BLENDER)), psk_mark=mark(psk_ok),
        scan=command_rows([("python list_models.py --scan", "读全部包头（6 个进程，约 1 分钟）"),
                           ("python list_models.py --catalogue", "写模型总目录，顺便判断 NPC / 怪物的性别")]),
        sample_scan=esc(SAMPLE_SCAN), listing=listing, basic=basic, sample=esc(SAMPLE_RUN.replace("{out}", root)),
        nude=nude, redo=redo, batch=batch)


def render(catalogue, exports, root):
    esc = html.escape
    female = [m for m in catalogue.values() if m.get("sex") == "F"]
    counts = {
        "total": len(catalogue),
        "female": len(female),
        "female_npc": sum(1 for m in female if m.get("kind") == "npc"),
        "female_mob": sum(1 for m in female if m.get("kind") in ("monster", "monster_starter")),
        "gf_wear": sum(1 for m in catalogue.values() if m.get("gender") == "GF" and m.get("kind") in ("outfit", "costume", "hat", "polymorph")),
        "gf_costume": sum(1 for m in catalogue.values() if m.get("gender") == "GF" and m.get("kind") == "costume"),
        "gf_hair": sum(1 for m in catalogue.values() if m.get("gender") == "GF" and m.get("kind") == "hair"),
        "gf_head": sum(1 for m in catalogue.values() if m.get("gender") == "GF" and m.get("kind") == "head"),
    }
    chip_counts = {}
    for m in catalogue.values():
        k = chip_of(m.get("kind", ""))
        chip_counts[k] = chip_counts.get(k, 0) + 1
    chips = "".join('<button class="chip" data-chip="%s">%s (%s)</button>' % (
        key, esc(label), "{:,}".format(chip_counts.get(key, 0))) for key, label, _k in CHIP_GROUPS if chip_counts.get(key))
    exports = sorted(exports, key=lambda r: -r["mtime"])
    rows = model_rows(catalogue, exports)
    why = {mid: WHY_ZH.get(m.get("why", ""), "") for mid, m in catalogue.items() if m.get("sex") == "F" and m.get("why")}
    data = json.dumps({"rows": rows, "kinds": KIND_ZH, "chips": {k: chip_of(k) for k in KIND_ZH}, "why": why},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return PAGE_TEMPLATE.format(
        generated=esc(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")), root=esc(root),
        total="{:,}".format(counts["total"]), gf_wear=counts["gf_wear"], gf_head=counts["gf_head"], gf_hair=counts["gf_hair"],
        female_npc=counts["female_npc"], female_mob=counts["female_mob"], exported=len(exports),
        size=human_size(sum(r["blend_size"] for r in exports)), chips=chips, howto=render_howto(root, counts),
        cards="".join(render_card(r, catalogue) for r in exports) or '<p class="muted">还没有导出过模型。</p>',
        data=data)


def build(root=lm.DEFAULT_EXPORT_ROOT, out=None, force=False):
    catalogue = load_catalogue(root)
    exports = collect_exports(root, force)
    out = out or os.path.join(HERE, PAGE_NAME)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(catalogue, exports, root))
    return out


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>AION2 模型画廊</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f6f8; --panel: #ffffff; --ink: #1b1c20; --muted: #6b6f78;
  --line: #e2e4ea; --accent: #3b6ef5; --kind: #1f7a4d; --kind-bg: #e3f4ea;
  --f: #b0306a; --f-bg: #fbe6ef; --fmt: #7a3fa0; --fmt-bg: #f1e7f8; --shot: #b4b6bd;
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
.chip, .copy, .toggle, .more {{ font: inherit; font-size: 12px; padding: 5px 11px; cursor: pointer; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 999px; }}
.chip.on, .toggle.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.copy {{ padding: 1px 8px; font-size: 11px; }}
.count {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
.jump {{ font-size: 12px; }}
main {{ padding: 22px 32px 48px; }}
.grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); align-items: start; margin-bottom: 26px; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 11px; overflow: hidden;
  display: flex; flex-direction: column; }}
.card[hidden] {{ display: none !important; }}
.shot {{ display: block; position: relative; background: var(--shot); line-height: 0; text-align: center; }}
.shot img {{ width: 100%; height: auto; display: block; }}
.noimg {{ padding: 46px 0; color: var(--muted); font-size: 12px; line-height: 1.6; }}
.body {{ padding: 12px 14px 14px; }}
.titlerow {{ display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }}
.titlerow h3 {{ margin: 0 4px 0 0; font-size: 15px; font-family: Consolas, monospace; word-break: break-all; }}
.when {{ margin-left: auto; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; text-decoration: none; }}
.badge-kind {{ color: var(--kind); background: var(--kind-bg); }}
.badge-f {{ color: var(--f); background: var(--f-bg); }}
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
.howto h3 {{ margin: 12px 0 4px; font-size: 13.5px; }}
.howto p {{ margin: 6px 0; }}
.quick {{ margin: 10px 0 12px; padding: 10px 14px 4px; background: var(--bg); border: 1px solid var(--accent);
  border-radius: 9px; }}
.quick > b {{ font-size: 14px; }}
.ok, .no {{ font-size: 11px; padding: 1px 7px; border-radius: 999px; white-space: nowrap; }}
.ok {{ color: var(--kind); background: var(--kind-bg); }}
.no {{ color: var(--f); background: var(--f-bg); }}
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
table.list {{ border-collapse: collapse; margin: 8px 0 4px; font-size: 12.5px; width: 100%; }}
table.list th, table.list td {{ text-align: left; padding: 3px 10px 3px 0; border-bottom: 1px solid var(--line);
  vertical-align: top; }}
#models-table {{ table-layout: fixed; }}
#models-table th:nth-child(1) {{ width: 31%; }} #models-table th:nth-child(2) {{ width: 12%; }}
#models-table th:nth-child(3) {{ width: 3%; }} #models-table th:nth-child(4) {{ width: 5%; }}
#models-table th:nth-child(5) {{ width: 39%; }} #models-table th:nth-child(6) {{ width: 10%; }}
#models-table td {{ word-break: break-all; }}
#models-table td:first-child code {{ font-size: 12.5px; }}
dd code {{ word-break: normal; overflow-wrap: anywhere; }}
#models-table .f {{ color: var(--f); cursor: help; }}
#models-table td.cmdcell {{ white-space: nowrap; }}
.listbox {{ background: var(--panel); border: 1px solid var(--line); border-radius: 11px; padding: 10px 16px 14px; overflow-x: auto; }}
</style>
</head>
<body>
<header>
  <h1>AION2 模型画廊</h1>
  <div class="sub">生成于 {generated} · 导出根目录 <code>{root}</code> · 由 <code>scripts/aion2/html/make_gallery.py</code> 生成</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>游戏里的模型（骨骼网格按游戏的拼法归组）</span></div>
    <div class="stat"><b>{gf_wear}</b><span>女性玩家套装 / 时装 / 帽子 / 变身</span></div>
    <div class="stat"><b>{gf_head} / {gf_hair}</b><span>女性的脸 / 发型</span></div>
    <div class="stat"><b>{female_npc}</b><span>女性 NPC</span></div>
    <div class="stat"><b>{female_mob}</b><span>女性怪物 / Boss</span></div>
    <div class="stat"><b>{exported}</b><span>已导出 .blend（{size}）</span></div>
  </div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="搜索 id，例如 yustiel、angel、maid、hair_308" autocomplete="off">
  {chips}
  <button class="toggle" id="only-female">只看女性</button>
  <button class="toggle" id="only-exported">只看已导出</button>
  <a class="jump" href="#howto">怎么导出</a>
  <a class="jump" href="#exported">已导出</a>
  <a class="jump" href="#models">全部模型</a>
</div>
<main>
{howto}
  <h2 class="listhead" id="exported">已导出 <span class="muted" id="count-cards"></span></h2>
  <div class="grid" id="grid">
{cards}  </div>
  <h2 class="listhead" id="models">全部模型 <span class="muted" id="count-rows"></span></h2>
  <div class="listbox">
    <table class="list" id="models-table">
      <thead><tr><th>id</th><th>类别</th><th></th><th>部件</th><th>游戏里的位置</th><th>导出</th></tr></thead>
      <tbody></tbody>
    </table>
    <button class="more" id="more" hidden>再显示 300 行</button>
  </div>
</main>
<script id="data" type="application/json">{data}</script>
<script>
(function () {{
  var D = JSON.parse(document.getElementById('data').textContent);
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var q = document.getElementById('q');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var onlyFemale = document.getElementById('only-female'), onlyExported = document.getElementById('only-exported');
  var tbody = document.querySelector('#models-table tbody'), more = document.getElementById('more');
  var chip = '', limit = 300, PAGE = 300;
  function esc(s) {{ return String(s).replace(/[&<>"]/g, function (c) {{ return {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}}[c]; }}); }}
  function words() {{ return q.value.toLowerCase().split(/\\s+/).filter(Boolean); }}
  function rowOk(r, w) {{
    var text = (r[0] + ' ' + r[1] + ' ' + (D.kinds[r[1]] || '') + ' ' + r[4]).toLowerCase();
    if (!w.every(function (x) {{ return text.indexOf(x) >= 0; }})) return false;
    if (chip && (D.chips[r[1]] || 'other') !== chip) return false;
    if (onlyFemale.classList.contains('on') && r[2] !== 'F') return false;
    if (onlyExported.classList.contains('on') && !r[5]) return false;
    return true;
  }}
  function renderRows() {{
    var w = words(), hits = D.rows.filter(function (r) {{ return rowOk(r, w); }});
    var html = [];
    hits.slice(0, limit).forEach(function (r) {{
      var cmd = 'python export_model.py ' + r[0];
      var sex = r[2] === 'F' ? '<span class="f" title="' + esc(D.why[r[0]] || '玩家女性部件（GF）') + '">♀</span>' : (r[2] === 'M' ? '<span class="muted">♂</span>' : '');
      html.push('<tr><td><code>' + esc(r[0]) + '</code>' + (r[5] ? ' <span class="muted">已导出：' + esc(r[5]) + '</span>' : '') + '</td><td>' +
        esc(D.kinds[r[1]] || r[1]) + '</td><td>' + sex + '</td><td>' + r[3] + '</td><td class="muted">' + esc(r[4]) +
        '</td><td class="cmdcell"><button class="copy" data-copy="' + esc(cmd) + '" title="' + esc(cmd) + '">复制命令</button></td></tr>');
    }});
    tbody.innerHTML = html.join('');
    more.hidden = hits.length <= limit;
    document.getElementById('count-rows').textContent = '（' + Math.min(hits.length, limit) + ' / ' + hits.length + ' 个符合，共 ' + D.rows.length + '）';
  }}
  function apply() {{
    var w = words(), shown = 0;
    cards.forEach(function (c) {{
      var ok = w.every(function (x) {{ return c.getAttribute('data-search').indexOf(x) >= 0; }});
      if (chip && c.getAttribute('data-chip') !== chip) ok = false;
      if (onlyFemale.classList.contains('on') && c.getAttribute('data-female') !== '1') ok = false;
      c.hidden = !ok;
      if (ok) shown++;
    }});
    document.getElementById('count-cards').textContent = '（' + shown + ' / ' + cards.length + '）';
    limit = PAGE;
    renderRows();
  }}
  chips.forEach(function (c) {{
    c.addEventListener('click', function () {{
      var k = c.getAttribute('data-chip');
      chip = (chip === k) ? '' : k;
      chips.forEach(function (x) {{ x.classList.toggle('on', x.getAttribute('data-chip') === chip); }});
      apply();
    }});
  }});
  [onlyFemale, onlyExported].forEach(function (b) {{ b.addEventListener('click', function () {{ b.classList.toggle('on'); apply(); }}); }});
  more.addEventListener('click', function () {{ limit += PAGE; renderRows(); }});
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
    ap.add_argument("--export-root", default=lm.DEFAULT_EXPORT_ROOT, help="导出根目录（默认 %(default)s）")
    ap.add_argument("--out", default=None, help="输出 HTML（默认本脚本旁的 index.html）")
    ap.add_argument("--force", action="store_true", help="即使缩略图是新的也重建")
    a = ap.parse_args()
    print(build(a.export_root, a.out, a.force))


if __name__ == "__main__":
    main()
