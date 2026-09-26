"""归档规则：每个游戏的产物在 D 盘哪里、归到哪个角色 / 格式、哪些目录是可以重新生成的中间产物。

加一个游戏 = 在下面写一个 ``Game(...)``：``collect()`` 返回 (造型列表, 附带文件列表)。
造型 (Product) 是一个能单独打开的目录：默认整目录拷到 ``<游戏>\\<角色>\\<格式>\\<造型>\\``；
``include`` 可以只挑其中几项并改名，``exclude`` 按通配符排除；``package=True`` 表示里面的 .blend
引用了目录外的贴图，要在 Blender 里收拢贴图后另存；``move=True`` 表示源已经在 E 盘，直接移动。
附带文件 (Meta)：清单、缩略图、对照图、导出日志、mod 原文件，放 ``<游戏>\\_meta\\``（``dest`` 可指定别处）。
``regenerable``：D 盘上不归档也能删的东西（原始解包、探测输出……），每项带一句原因，路径可以带通配符。
.blend1（Blender 自动备份）一律不拷、算可删。
"""

import collections
import fnmatch
import glob
import json
import os
import re


class Product:
    def __init__(self, character, fmt, model, src, main=None, preview=None, desc="", include=None, exclude=(),
                 package=False, move=False):
        self.character, self.fmt, self.model, self.src = safe(character), fmt, safe(model), src
        self.main, self.preview, self.desc = main, preview, desc
        self.include = include            # [(源相对路径, 目标相对路径)]；None = 整个目录
        self.exclude = tuple(exclude)
        self.package, self.move = package, move

    def pairs(self):
        return self.include if self.include is not None else [("", "")]

    def skip(self, rel):
        r = os.path.normcase(os.path.normpath(rel))
        if r.endswith(".blend1") or r.endswith(".part"):
            return True
        for e in self.exclude:
            e = os.path.normcase(os.path.normpath(e))
            if r == e or r.startswith(e + os.sep) or fnmatch.fnmatch(r, e) or fnmatch.fnmatch(os.path.basename(r), e):
                return True
        return False

    def dest_rel(self):
        return os.path.join(self.character, self.fmt, self.model)


class Meta:
    def __init__(self, src, name, move=False, dest=None):
        self.src, self.name, self.move, self.dest = src, name, move, dest

    def pairs(self):
        return [("", "")]

    def skip(self, rel):
        return rel.lower().endswith((".blend1", ".part"))

    def dest_rel(self):
        return self.dest or os.path.join("_meta", self.name)


class Game:
    def __init__(self, key, folder, title, sources, collect, regenerable=(), character_names=None, galleries=(),
                 aliases=None, notes=(), list_pages=()):
        self.key, self.folder, self.title = key, folder, title
        self.sources = sources            # 要报告能不能删的 D 盘目录
        self.collect = collect
        self._regen = regenerable         # [(路径或通配符, 为什么可以删)] 或返回它的函数
        self.character_names = character_names or {}
        self.galleries = galleries        # 仓库里要改链接的画廊页
        self._aliases = aliases           # 函数：game_dir -> {D 盘旧路径: E 盘新路径}
        self.notes = notes                # 写进可删除清单的备注
        self.list_pages = list_pages      # [(_meta 下的目录名, 原来所在目录)]：相对链接的列表页，归档后改链接

    def regen(self):
        return list(self._regen()) if callable(self._regen) else list(self._regen)

    def aliases(self, game_dir):
        return self._aliases(game_dir) if self._aliases else {}


INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe(name):
    """能当 Windows 目录名的名字。"""
    name = INVALID.sub("_", str(name)).strip().rstrip(". ")
    return name or "_"


def subdirs(path):
    try:
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    except FileNotFoundError:
        return []


def entries(path):
    try:
        return sorted(os.listdir(path))
    except FileNotFoundError:
        return []


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def j(*parts):
    return os.path.join(*parts)


def exists(path):
    return os.path.exists(path)


def files_in(root, pattern):
    return sorted(glob.glob(j(glob.escape(root), pattern)))


def blend_file_product(character, fmt, label, folder, desc="", extra=(), package=False):
    """同一个目录里放着很多模型时：只挑 <label>.blend + <label>_preview.png（+ extra 里存在的文件）。"""
    inc = [(label + ".blend", label + ".blend")]
    preview = None
    for f in (label + "_preview.png",) + tuple(extra):
        if exists(j(folder, f)):
            inc.append((f, f))
            if f.endswith("_preview.png"):
                preview = f
    return Product(character, fmt, label, folder, main=label + ".blend", preview=preview, desc=desc, include=inc,
                   package=package)


def everything_but(root, keep, reason):
    """root 下除了 keep 以外的每一项都算可重新生成。"""
    keep = {k.lower() for k in keep}
    return [(j(root, e), reason) for e in entries(root) if e.lower() not in keep]


# ---------------------------------------------------------------------------------------- Vindictus

VINDICTUS = r"D:\vindictus_exports"
FIONA_VAM = r"D:\vam_imports\FionaDF"


def vindictus_character(mid, info):
    low = mid.lower()
    if info.get("body") == "PCF" or low.startswith("pcf_") or mid in ("Fiona", "Fiona_BaseBody", "Shiningwill_legacy"):
        return "Fiona"
    if info.get("body") == "PCM" or low.startswith("pcm_") or mid == "Lethita":
        return "Lethita"
    for species in ("Gnoll", "Goblin", "Kobold"):
        if low.startswith(species.lower()):
            return species
    if mid == "Male_Knight":
        return "Knight"
    if mid.startswith("NPCM_RoyalArmy"):
        return "RoyalArmy"
    return mid


def collect_vindictus():
    manifest = load_json(j(VINDICTUS, "vindictus_models_manifest.json"))
    info = {r["label"]: r for r in manifest.get("results", [])}
    products = []
    for mid in subdirs(j(VINDICTUS, "blend")):
        src = j(VINDICTUS, "blend", mid)
        if os.path.isfile(j(src, mid + ".blend")):
            products.append(Product(vindictus_character(mid, info.get(mid, {})), "blend", mid, src,
                                    main=mid + ".blend", preview="preview.png", desc=info.get(mid, {}).get("name", "")))
    for mid in subdirs(j(VINDICTUS, "xps")):
        src = j(VINDICTUS, "xps", mid)
        if os.path.isfile(j(src, mid + ".xps")):
            products.append(Product(vindictus_character(mid, info.get(mid, {})), "xps", mid, src,
                                    main=mid + ".xps", desc=info.get(mid, {}).get("name", "")))
    if os.path.isdir(j(FIONA_VAM, "vam", "Custom")):
        products.append(Product(
            "Fiona", "vam", "FionaDF", FIONA_VAM,
            main="Custom/Atom/Person/Appearance/VindictusDF/Preset_Fiona DF.vap", preview="_preview/preview_front.png",
            desc="VaM 物品（scripts/vam/bring_to_vam.py）：4 件盔甲 + 头发 + 身体 / 头部 morph + 脸 / 眼贴图 + 外观预设；"
                 "Custom 整个拷进 VaM 根目录即可",
            include=[("vam/Custom", "Custom"), ("_preview", "_preview"), ("_preview_face", "_preview_face"),
                     ("items.json", "items.json"), ("_items.txt", "_items.txt"), ("_run.log", "_run.log")]))
    metas = []
    if exists(VINDICTUS):
        metas = [Meta(j(VINDICTUS, "vindictus_models_manifest.json"), "vindictus_models_manifest.json"),
                 Meta(j(VINDICTUS, "_gallery", "thumbs"), "gallery_thumbs"),
                 Meta(j(VINDICTUS, "xps", "README.md"), "xps_README.md"),
                 Meta(j(VINDICTUS, "xps", "_logs"), "xps_logs")]
        for f in entries(j(VINDICTUS, "blend")):
            if f.startswith("_") and f.lower().endswith(".png"):
                metas.append(Meta(j(VINDICTUS, "blend", f), j("contact_sheets", f)))
    return products, metas


VINDICTUS_REGEN = [
    (j(VINDICTUS, "umodel_exports"), "umodel_exports = UE Viewer 原始导出（PSK/PNG/.mat），scripts\\vindictus\\export_model.ps1 可重新生成"),
    (j(VINDICTUS, "umodel_probe"), "umodel_probe = 早期探测导出"),
    (j(FIONA_VAM, "_src"), "FionaDF\\_src、_face、*.npy/npz = bring_to_vam.py 的中间数据"),
    (j(FIONA_VAM, "_face"), "FionaDF\\_src、_face、*.npy/npz = bring_to_vam.py 的中间数据"),
    (j(FIONA_VAM, "rest_shrink.npy"), "FionaDF\\_src、_face、*.npy/npz = bring_to_vam.py 的中间数据"),
    (j(FIONA_VAM, "_diag.npz"), "FionaDF\\_src、_face、*.npy/npz = bring_to_vam.py 的中间数据"),
]


# ---------------------------------------------------------------------------------------- DOA5LR / DOA6

DOA5LR = r"D:\doa5lr_exports"


def majority_names(results, code_key="char"):
    votes = collections.defaultdict(collections.Counter)
    for r in results:
        parts = r["label"].split("_")
        if len(parts) > 1:
            votes[r[code_key]][parts[1]] += 1
    return {code: c.most_common(1)[0][0] for code, c in votes.items()}


def collect_doa5lr():
    res = load_json(j(DOA5LR, "doa5lr_models_manifest.json")).get("results", [])
    names = majority_names(res)
    info = {r["label"]: r for r in res}
    folder = j(DOA5LR, "_blends")
    products = []
    for path in files_in(folder, "*.blend"):
        label = os.path.basename(path)[:-6]
        r = info.get(label, {})
        code = r.get("char") or label.split("_")[0]
        costume = r.get("costume", "")
        products.append(blend_file_product(names.get(code, code.title()), "blend", label, folder, desc=costume))
    metas = [Meta(j(DOA5LR, "doa5lr_models_manifest.json"), "doa5lr_models_manifest.json"),
             Meta(j(DOA5LR, "_gallery"), "gallery")]
    for f in files_in(folder, "*.log") + files_in(folder, "*.md") + files_in(folder, "*.json"):
        metas.append(Meta(f, j("build_logs", os.path.basename(f))))
    for f in files_in(DOA5LR, "*.md") + files_in(DOA5LR, "*.log"):
        metas.append(Meta(f, os.path.basename(f)))
    return products, metas


def regen_doa5lr():
    keep = {"_blends", "_gallery", "doa5lr_models_manifest.json"} | {os.path.basename(f) for f in
                                                                     files_in(DOA5LR, "*.md") + files_in(DOA5LR, "*.log")}
    return everything_but(DOA5LR, keep, "<角色>_<COS|DLC>_NNN\\ 等 = 从游戏解出的 TMC/FBX/DDS 原始文件，"
                                        "extract_lnk.py + export_character.ps1 可重新生成")


DOA6 = r"D:\doa6_exports"
DOA_MODS = r"D:\doa_mods"
DOA_MOD_FBX = r"D:\doa_mod_fbx"


def collect_doa6():
    res = load_json(j(DOA6, "doa6_models_manifest.json")).get("results", [])
    official = {r["char"]: r["label"].split("_")[1] for r in res if r.get("kind") == "official" and "_" in r["label"]}
    names = dict(majority_names(res), **official)
    info = {r["label"]: r for r in res}
    folder = j(DOA6, "_blends")
    products = []
    for path in files_in(folder, "*.blend"):
        label = os.path.basename(path)[:-6]
        r = info.get(label, {})
        code = r.get("char") or label.split("_")[0]
        products.append(blend_file_product(names.get(code, code), "blend", label, folder,
                                           desc="mod" if r.get("kind") == "mod" else r.get("kind", "")))
    if exists(j(DOA6, "MOMIJI_COS001.blend")):
        products.append(blend_file_product("Momiji", "blend", "MOMIJI_COS001", DOA6, desc="早期单件测试"))
    metas = [Meta(j(DOA6, "doa6_models_manifest.json"), "doa6_models_manifest.json"),
             Meta(j(DOA6, "README.md"), "README.md"), Meta(j(DOA6, "_gallery"), "gallery"),
             Meta(j(DOA_MODS, "doa6"), j("mod_sources", "doa_mods_doa6")),
             Meta(DOA_MOD_FBX, j("mod_sources", "doa_mod_fbx"))]
    for f in files_in(folder, "*.log") + files_in(DOA6, "*.log"):
        metas.append(Meta(f, j("build_logs", os.path.basename(f))))
    return products, metas


def regen_doa6():
    keep = {"_blends", "_gallery", "readme.md", "doa6_models_manifest.json", "momiji_cos001.blend",
            "momiji_cos001_preview.png"} | {os.path.basename(f).lower() for f in files_in(DOA6, "*.log")}
    return everything_but(DOA6, keep, "<角色>_COS/FACE/HAIR_NNN\\、mod 解包目录、_objdb、_test_g1m = 从游戏 / mod 解出的 "
                                      "G1M/G1T/DDS/FBX 原始文件，extract_rdb.py + export_full.ps1 可重新生成") + \
        [(j(DOA_MODS, "_extract_tmp"), "doa_mods\\_extract_tmp = 解压临时目录")]


# ---------------------------------------------------------------------------------------- Throne of Desire

TOD = r"D:\throneofdesire_exports"


def collect_tod():
    res = load_json(j(TOD, "tod_models_manifest.json")).get("results", [])
    products = []
    for r in res:
        folder = os.path.dirname(r["blend"])
        if not exists(r["blend"]):
            continue
        mid = r["model"]
        model = mid if r.get("group") == "batch" or not any(
            x["model"] == mid and x.get("group") == "batch" for x in res) else mid + "_single"
        blend = os.path.basename(r["blend"])
        inc = [(blend, blend)] + [(f, f) for f in (mid + "_preview.png", mid + "_reopen_preview.png",
                                                   "export_manifest.json") if exists(j(folder, f))]
        products.append(Product(mid, "blend", model, folder, main=blend, preview=mid + "_preview.png",
                                desc="批量导出" if r.get("group") == "batch" else "单独导出（较早）", include=inc))
        if exists(j(folder, mid + ".fbx")):
            inc = [(mid + ".fbx", mid + ".fbx"), ("textures", "textures")] + \
                  [(f, f) for f in ("export_manifest.json",) if exists(j(folder, f))]
            products.append(Product(mid, "fbx", model, folder, main=mid + ".fbx", desc="FBX + textures\\", include=inc))
    metas = [Meta(j(TOD, "tod_models_manifest.json"), "tod_models_manifest.json"), Meta(j(TOD, "_gallery"), "gallery")]
    for f in files_in(j(TOD, "female_all"), "*.json"):
        metas.append(Meta(f, os.path.basename(f)))
    return products, metas


def regen_tod():
    out = [(j(TOD, "*", "source"), "source\\ = 从游戏拷出的 NIF/KFM/贴图原件，batch_export_female.py 可重新生成"),
           (j(TOD, "*", "*", "source"), "source\\ = 从游戏拷出的 NIF/KFM/贴图原件，batch_export_female.py 可重新生成"),
           (j(TOD, "*", "source_dependencies"), "source\\ = 从游戏拷出的 NIF/KFM/贴图原件，batch_export_female.py 可重新生成"),
           (j(TOD, "m001"), "m001 只有源文件，没有成品")]
    return out


# ---------------------------------------------------------------------------------------- FF7 Remake / Rebirth

FF7R = r"D:\ff7remake_exports"
FF7RB = r"D:\ff7rebirth_exports"
FF7_MODS = r"D:\ff7_mods"


def mod_character(name, default="Tifa"):
    return "Reika" if "reika" in name.lower() else default


def collect_mod_formats(mods_root):
    products = []
    for fmt in ("pmx", "xps"):
        for name in subdirs(j(mods_root, fmt)):
            src = j(mods_root, fmt, name)
            main = name + "." + fmt
            products.append(Product(mod_character(name), fmt, name, src, main=main if exists(j(src, main)) else None,
                                    preview="preview.png" if exists(j(src, "preview.png")) else None,
                                    desc="Nexus mod", package=(fmt == "pmx")))
    return products


def collect_ff7r():
    res = load_json(j(FF7R, "player", "ff7remake_models_manifest.json")).get("results", [])
    products = []
    for r in res:
        blend = os.path.normpath(r["blend"])
        if not exists(blend):
            continue
        folder, label = os.path.dirname(blend), os.path.basename(blend)[:-6]
        desc = "%s %s" % (r.get("kind", ""), r.get("variant", "")) if r.get("kind") != "mod" else "Nexus mod"
        if os.path.basename(folder) == "tifa_mod_natural_verified":      # 自成一个目录的交付：整个拿走
            products.append(Product(r.get("char") or "Tifa", "blend", label, folder, main=label + ".blend",
                                    preview=label + "_preview.png", desc="裸体 Tifa（zzTifaNudeNatural mod）",
                                    package=True))
            continue
        extra = (label + ".log", label + ".json")
        products.append(blend_file_product(r.get("char") or "Other", "blend", label, folder, desc=desc.strip(),
                                           extra=extra, package=True))
    products += collect_mod_formats(j(FF7R, "mods"))
    if exists(j(FF7R, "tifa_mod_natural_verified", "Tifa_Mod_Natural.blend")) and \
            not any(p.model == "Tifa_Mod_Natural" for p in products):
        products.append(Product("Tifa", "blend", "Tifa_Mod_Natural", j(FF7R, "tifa_mod_natural_verified"),
                                main="Tifa_Mod_Natural.blend", desc="裸体 Tifa（zzTifaNudeNatural mod）"))
    metas = [Meta(j(FF7R, "player", "ff7remake_models_manifest.json"), "ff7remake_models_manifest.json"),
             Meta(j(FF7R, "player", "README.md"), "README.md"), Meta(j(FF7R, "player", "_gallery"), "gallery"),
             Meta(j(FF7_MODS, "remake"), j("mod_sources", "remake")),
             Meta(j(FF7R, "mods", "gallery_mods.json"), "gallery_mods.json")]
    return products, metas


def regen_ff7r():
    return [(j(FF7R, "player", "GameContents"), "player\\GameContents、Engine = umodel 原始导出，export_ff7remake_models.ps1 可重新生成"),
            (j(FF7R, "player", "Engine"), "player\\GameContents、Engine = umodel 原始导出，export_ff7remake_models.ps1 可重新生成"),
            (j(FF7R, "umodel_batch_demo"), "umodel_batch_demo、umodel_original、tifa_purple_dress、umodel_glove_raw = 早期演示，已被 player\\ 批量版取代"),
            (j(FF7R, "umodel_original"), "umodel_batch_demo、umodel_original、tifa_purple_dress、umodel_glove_raw = 早期演示，已被 player\\ 批量版取代"),
            (j(FF7R, "tifa_purple_dress"), "umodel_batch_demo、umodel_original、tifa_purple_dress、umodel_glove_raw = 早期演示，已被 player\\ 批量版取代"),
            (j(FF7R, "umodel_glove_raw"), "umodel_batch_demo、umodel_original、tifa_purple_dress、umodel_glove_raw = 早期演示，已被 player\\ 批量版取代"),
            (j(FF7R, "mods", "*", "*", "gltf"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件"),
            (j(FF7R, "mods", "*", "*", "mod_assets"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件"),
            (j(FF7R, "mods", "*", "*", "mount"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件"),
            (j(FF7R, "mods", "*", "*", "raw"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件"),
            (j(FF7R, "mods", "*", "*", "log"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件"),
            (j(FF7R, "mods", "*", "*", "packages.json"), "mods\\<mod>\\<文件>\\ 下的 gltf / mod_assets / mount / raw / packages.json = mod 解包中间文件")]


def collect_ff7rb():
    res = load_json(j(FF7RB, "materialized", "ff7rebirth_gallery_manifest.json")).get("results", [])
    products = []
    for r in res:
        blend = os.path.normpath(r["blend"])
        if not exists(blend):
            continue
        folder, label = os.path.dirname(blend), os.path.basename(blend)[:-6]
        desc = "Nexus mod" if r.get("kind") == "mod" else "%s %s（%s）" % (r.get("kind", ""), r.get("variant", ""),
                                                                           r.get("route", ""))
        products.append(blend_file_product(r.get("char") or "Other", "blend", label, folder, desc=desc.strip(),
                                           extra=(label + ".log",)))
    products += collect_mod_formats(j(FF7RB, "mods"))   # pmx 目录里的 _converted.blend 用的是绝对路径 -> 要打包
    metas = [Meta(j(FF7RB, "materialized", "ff7rebirth_gallery_manifest.json"), "ff7rebirth_gallery_manifest.json"),
             Meta(j(FF7RB, "materialized", "ff7rb_models_manifest.json"), "ff7rb_models_manifest.json"),
             Meta(j(FF7RB, "cli_materialized", "ff7rb_models_manifest.json"), "cli_ff7rb_models_manifest.json"),
             Meta(j(FF7RB, "materialized", "README.md"), "README.md"),
             Meta(j(FF7RB, "materialized", "_gallery"), "gallery"),
             Meta(j(FF7RB, "mappings"), "mappings"),
             Meta(j(FF7RB, "mods", "pmx", "_logs"), "pmx_logs"),
             Meta(j(FF7_MODS, "rebirth"), j("mod_sources", "rebirth"))]
    for f in entries(FF7_MODS):                    # 顶层零散文件：对照图、草稿脚本、日志、mod 筛选清单
        if os.path.isfile(j(FF7_MODS, f)) and f != "cue4parse_tree.json":
            metas.append(Meta(j(FF7_MODS, f), j("ff7_mods_files", f)))
    metas.append(Meta(j(FF7RB, "mods", "gallery_mods.json"), "gallery_mods.json"))
    for f in files_in(j(FF7RB, "cli_materialized"), "*.log") + files_in(j(FF7RB, "materialized"), "*.log"):
        metas.append(Meta(f, j("build_logs", os.path.basename(f))))
    return products, metas


def regen_ff7rb():
    mods_mid = "mods\\<mod>\\<文件>\\export、cli_export.log、packages.json = CUE4Parse CLI 解包的中间文件"
    return [(j(FF7RB, "fmodel_exports"), "fmodel_exports、cli_exports = 原始解包（FModel / CUE4Parse CLI），可重新导出"),
            (j(FF7RB, "cli_exports"), "fmodel_exports、cli_exports = 原始解包（FModel / CUE4Parse CLI），可重新导出"),
            (j(FF7RB, "mods", "*", "*", "export"), mods_mid),
            (j(FF7RB, "mods", "*", "*", "cli_export.log"), mods_mid),
            (j(FF7RB, "mods", "*", "*", "packages.json"), mods_mid),
            (j(FF7RB, "blender"), "空目录"), (j(FF7RB, "xps"), "空目录"),
            (j(FF7_MODS, "_stage"), "ff7_mods\\_stage = 游戏 pak 的硬链接（给 CLI 用的暂存区），删了不腾空间"),
            (j(FF7_MODS, "_test_remake"), "ff7_mods\\_test_*、_dbg_*、_cli_test* = 调试输出"),
            (j(FF7_MODS, "_dbg_*"), "ff7_mods\\_test_*、_dbg_*、_cli_test* = 调试输出"),
            (j(FF7_MODS, "_cli_test*"), "ff7_mods\\_test_*、_dbg_*、_cli_test* = 调试输出"),
            (j(FF7_MODS, "cue4parse_tree.json"), "ff7_mods\\_test_*、_dbg_*、_cli_test* = 调试输出")]


# ---------------------------------------------------------------------------------------- Stellar Blade

SB = r"D:\stellarblade_exports"


def sb_character(label):
    low = label.lower()
    if "vindictusfiona" in low:
        return "Fiona"
    if "gantzreika" in low:
        return "Reika"
    return "Eve"


def sb_model(label):
    return label[4:] if label.startswith("Eve_") else label


def collect_sb():
    res = load_json(j(SB, "stellarblade_models_manifest.json")).get("results", [])
    info = {r["label"]: r for r in res}
    products = []
    for label in subdirs(j(SB, "packages")):
        src = j(SB, "packages", label)
        if exists(j(src, label + ".blend")):
            products.append(Product(sb_character(label), "blend", sb_model(label), src, main=label + ".blend",
                                    preview="preview.png", desc=info.get(label, {}).get("name", "")))
    for fmt in ("xps", "pmx"):
        for label in subdirs(j(SB, fmt)):
            if label.startswith("_"):
                continue
            src = j(SB, fmt, label)
            main = label + "." + fmt
            products.append(Product(sb_character(label), fmt, sb_model(label), src,
                                    main=main if exists(j(src, main)) else None,
                                    preview="preview.png" if exists(j(src, "preview.png")) else None,
                                    desc=info.get(label, {}).get("name", "Nexus mod"), package=(fmt == "pmx")))
    metas = [Meta(j(SB, "README.md"), "README.md"),
             Meta(j(SB, "stellarblade_models_manifest.json"), "stellarblade_models_manifest.json"),
             Meta(j(SB, "packages", "README.md"), "packages_README.md"),
             Meta(j(SB, "packages", "packages_index.json"), "packages_index.json"),
             Meta(j(SB, "validation"), "validation"), Meta(j(SB, "_gallery"), "gallery"),
             Meta(j(SB, "mappings"), "mappings"), Meta(j(SB, "_tools"), "_tools"),
             Meta(j(SB, "pmx", "_logs"), "pmx_logs"), Meta(j(SB, "mods"), "mod_sources")]
    for f in files_in(j(SB, "blender"), "*_gallery.png"):
        metas.append(Meta(f, j("gallery_previews", os.path.basename(f))))
    return products, metas


def regen_sb():
    return [(j(SB, "blender", "*.blend"), "blender\\*.blend = 贴图外链的版本，同一批模型的独立版就是 packages\\（已归档）"),
            (j(SB, "blender", "*.txt"), "blender\\ 里的日志"),
            (j(SB, "blender", "*.log"), "blender\\ 里的日志"),
            (j(SB, "blender", "*.json"), "blender\\ 里的日志"),
            (j(SB, "umodel_*"), "umodel_* / fmodel_exports / outfit_albedo = UE Viewer / FModel 原始导出，export_outfit.ps1 可重新生成"),
            (j(SB, "fmodel_exports"), "umodel_* / fmodel_exports / outfit_albedo = UE Viewer / FModel 原始导出，export_outfit.ps1 可重新生成"),
            (j(SB, "outfit_albedo"), "umodel_* / fmodel_exports / outfit_albedo = UE Viewer / FModel 原始导出，export_outfit.ps1 可重新生成"),
            (j(SB, "_probe_stash"), "_probe_stash = 探测输出")]


def aliases_sb(game_dir):
    """画廊里的 blender\\<label>.blend 指到归档的 packages 版。"""
    out = {}
    models = load_json(j(game_dir, "_meta", "models.json"))
    for key, m in models.items():
        if m.get("fmt") == "blend" and m.get("main"):
            label = m["main"][:-6]
            out[j(SB, "blender", label + ".blend")] = j(game_dir, m["character"], "blend", m["model"], m["main"])
    return out


# ---------------------------------------------------------------------------------------- VaM

VAM = r"D:\vam_exports"
VAM_IMPORTS = r"D:\vam_imports"


def vam_character(model):
    """<作者>.<包>.<版本>~<场景/预设>~<人物> -> 包名。"""
    package = model.split("~")[0]
    parts = package.split(".")
    name = parts[1] if len(parts) >= 3 else package
    return safe(name.replace("[Looks]_", "").replace("[Looks]", "")) or safe(package)


def collect_vam():
    res = load_json(j(VAM, "vam_models_manifest.json")).get("results", [])
    info = {r["model"]: r for r in res}
    products = []
    for kind in ("looks", "clothings"):
        for model in subdirs(j(VAM, kind)):
            src = j(VAM, kind, model, "blend")
            if not files_in(src, "*.blend"):
                continue
            r = info.get(model, {})
            products.append(Product(vam_character(model), "blend", model, src, main=model + ".blend",
                                    preview=model + "_preview.png", desc=r.get("display", "")))
    if files_in(VAM_IMPORTS, "*.duf"):
        inc = [("Fiona", "Fiona")] + [(os.path.basename(f), os.path.basename(f)) for f in files_in(VAM_IMPORTS, "*.duf")]
        products.append(Product("Fiona18", "duf", "Fiona18", VAM_IMPORTS, main="Fiona_Dress.duf", include=inc,
                                desc="Fiona 18（MMD / Genesis 8 角色）转成 VaM 游戏内创作器用的 DAZ .duf（import_to_vam.ps1）"))
    metas = [Meta(j(VAM, "vam_models_manifest.json"), "vam_models_manifest.json"), Meta(j(VAM, "_gallery"), "gallery"),
             Meta(j(VAM_IMPORTS, "_reference"), "vam_imports_reference")]
    return products, metas


def regen_vam():
    return [(j(VAM, "looks", "*", "_textures"), "looks\\<人物>\\_textures、model.json、model.npz = 导出时的贴图缓存和中间数据（.blend 已打包贴图）"),
            (j(VAM, "looks", "*", "model.json"), "looks\\<人物>\\_textures、model.json、model.npz = 导出时的贴图缓存和中间数据（.blend 已打包贴图）"),
            (j(VAM, "looks", "*", "model.npz"), "looks\\<人物>\\_textures、model.json、model.npz = 导出时的贴图缓存和中间数据（.blend 已打包贴图）"),
            (j(VAM, "looks", "*", "_attachments"), "looks\\<人物>\\_attachments = 挂件 FBX 中间文件"),
            (j(VAM, "clothings", "*", "_textures"), "looks\\<人物>\\_textures、model.json、model.npz = 导出时的贴图缓存和中间数据（.blend 已打包贴图）"),
            (j(VAM, "clothings", "*", "model.*"), "looks\\<人物>\\_textures、model.json、model.npz = 导出时的贴图缓存和中间数据（.blend 已打包贴图）"),
            (j(VAM, "_cache"), "_cache = 基础身体 / 骨骼缓存，export_vam_models.ps1 会重建")]


# ---------------------------------------------------------------------------------------- TFD

TFD = r"D:\tfd_exports"


def collect_tfd():
    res = load_json(j(TFD, "tfd_models_manifest.json")).get("results", [])
    info = {r["label"]: r for r in res}
    products = []
    for label in subdirs(j(TFD, "blend")):
        src = j(TFD, "blend", label)
        if not exists(j(src, label + ".blend")):
            continue
        r = info.get(label, {})
        char = r.get("char") or ("Monster" if label.startswith("MOB_") else label)
        products.append(Product(char, "blend", label, src, main=label + ".blend", preview="preview.png",
                                desc=r.get("name", "")))
    metas = [Meta(j(TFD, "tfd_models_manifest.json"), "tfd_models_manifest.json"), Meta(j(TFD, "_gallery"), "gallery"),
             Meta(j(TFD, "_keys"), "_keys", dest=r"E:\tools\firstdescendant\_keys")]
    return products, metas


TFD_REGEN = [(j(TFD, "cue4_exports"), "cue4_exports、umodel_exports、_probe = CUE4Parse / UE Viewer 原始导出，可重新生成"),
             (j(TFD, "umodel_exports"), "cue4_exports、umodel_exports、_probe = CUE4Parse / UE Viewer 原始导出，可重新生成"),
             (j(TFD, "_probe"), "cue4_exports、umodel_exports、_probe = CUE4Parse / UE Viewer 原始导出，可重新生成")]


# ---------------------------------------------------------------------------------------- NARAKA

NARAKA_E = r"E:\game_export\NARAKA"
NARAKA_D = r"D:\naraka_exports"
NARAKA_HEROES = {
    "ninghongye": "宁红夜", "jianan": "迦南", "temuer": "特木尔", "tianhai": "天海",
    "yaodaoji": "妖刀姬", "hutao": "胡桃", "jicanghai": "季沧海", "cuisanniang": "崔三娘",
    "yueshan": "岳山", "wuchen": "无尘", "guqinghan": "顾清寒", "wutian": "武田信忠",
    "shenmiao": "沈妙", "yinziping": "殷紫萍", "hadi": "哈迪", "huwei": "胡为",
    "yulinglong": "玉玲珑", "jiyingying": "季莹莹", "weiqing": "魏轻", "liulian": "刘炼",
    "zhangqiling": "张起灵", "lixunhuan": "李寻欢", "yexiu": "叶修",
}


def naraka_family_hero():
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "naraka"))
        import naraka_catalog
        return dict(naraka_catalog.FAMILY_HERO)
    except Exception:  # noqa: BLE001
        return {}


def naraka_hero(outfit_id, family_hero):
    family = outfit_id.split("_lv_")[0]
    code = family_hero.get(family)
    if code:
        return NARAKA_HEROES.get(code, code)
    return re.sub(r"^ch_[fm]_(ming_|japan_)?", "", family) or family


def naraka_archived_ids(game_dir):
    models = load_json(j(game_dir, "_meta", "models.json"))
    return {m["model"] for m in models.values() if m.get("source", "").lower().startswith(NARAKA_E.lower())}


def collect_naraka():
    fh = naraka_family_hero()
    products, batch = [], set()
    for oid in subdirs(j(NARAKA_E, "outfits")):
        src = j(NARAKA_E, "outfits", oid)
        batch.add(oid)
        products.append(Product(naraka_hero(oid, fh), "blend", oid, src, main=oid + ".blend",
                                preview=oid + "_preview.png", desc="女性外观批量导出（09-25）", move=True))
    batch |= naraka_archived_ids(NARAKA_E)
    for oid in subdirs(j(NARAKA_D, "outfits")):
        if oid in batch:
            continue
        products.append(Product(naraka_hero(oid, fh), "blend", oid, j(NARAKA_D, "outfits", oid), main=oid + ".blend",
                                preview=oid + "_preview.png", desc="样本导出（09-25 上午）"))
    for iid in subdirs(j(NARAKA_D, "items")):
        char = "怪物" if iid.startswith("mo_") else ("发型" if "_hair_" in iid else "武器")
        products.append(Product(char, "blend", iid, j(NARAKA_D, "items", iid), main=iid + ".blend",
                                preview=iid + "_preview.png", desc="样本导出"))
    metas = [Meta(j(NARAKA_E, "_list"), "list", move=True), Meta(j(NARAKA_E, "_logs"), "logs", move=True),
             Meta(j(NARAKA_D, "_list"), "list_samples")]
    return products, metas


def aliases_naraka(game_dir):
    """D 盘样本里和批量重复的那几套，链接指到批量版。"""
    out = {}
    for m in load_json(j(game_dir, "_meta", "models.json")).values():
        if m.get("source", "").lower().startswith(NARAKA_E.lower()):
            out[j(NARAKA_D, "outfits", m["model"])] = j(game_dir, m["character"], m["fmt"], m["model"])
    return out


def regen_naraka():
    batch = set(subdirs(j(NARAKA_E, "outfits"))) | naraka_archived_ids(NARAKA_E)
    out = [(j(NARAKA_D, "outfits", oid), "outfits\\ 里和 E 盘女性批量重复的样本（批量版更新）")
           for oid in subdirs(j(NARAKA_D, "outfits")) if oid in batch]
    out.append((j(NARAKA_D, "_test"), "_test = 调试输出"))
    return out


# ---------------------------------------------------------------------------------------- HoneySelect 2

HS2 = r"D:\hs2_exports"


def collect_hs2():
    products = []
    for card in subdirs(j(HS2, "cards")):
        src = j(HS2, "cards", card)
        scene = load_json(j(src, "scene.json"))
        char = scene.get("character") or card.replace("_nude", "")
        products.append(Product(char, "blend", card, src, main=card + ".blend", preview=card + "_preview.png",
                                desc=("裸体版" if scene.get("nude") or card.endswith("_nude") else "角色卡") +
                                     "（%s）" % scene.get("card", card), exclude=("parts",)))
    for body in subdirs(j(HS2, "bodies")):
        src = j(HS2, "bodies", body)
        products.append(Product("BaseBody", "blend", body, src, main=body + ".blend", preview=body + "_preview.png",
                                desc="基础身体", exclude=("parts",)))
    for cat in subdirs(j(HS2, "items")):
        for item in subdirs(j(HS2, "items", cat)):
            src = j(HS2, "items", cat, item)
            blends = files_in(src, "*.blend")          # <物品>_with_body\ 里的 .blend 不带 _with_body
            stem = os.path.basename(blends[0])[:-6] if blends else item
            products.append(Product("Items", "blend", item, src, main=stem + ".blend", preview=stem + "_preview.png",
                                    desc="物品 %s%s" % (cat, "（穿在身体上）" if item.endswith("_with_body") else ""),
                                    exclude=("parts",)))
    metas = [Meta(j(HS2, "_list"), "list"), Meta(j(HS2, "_gallery"), "gallery"),
             Meta(j(HS2, "_exports.jsonl"), "_exports.jsonl")]
    return products, metas


HS2_REGEN = [(j(HS2, "_cache"), "_cache、parts\\ = 导出中间数据（npz），export_model.py 可重新生成"),
             (j(HS2, "*", "*", "parts"), "_cache、parts\\ = 导出中间数据（npz），export_model.py 可重新生成"),
             (j(HS2, "items", "*", "*", "parts"), "_cache、parts\\ = 导出中间数据（npz），export_model.py 可重新生成")]


# ---------------------------------------------------------------------------------------- Venus Vacation PRISM

VVP = r"D:\venusvacationprism_exports"
VVP_MAIN = {"elise": "Elise_Complete_Rigged.blend", "fiona": "models/Fiona_Complete_Rigged.blend",
            "honoka": "Honoka_Complete_Rigged.blend", "misaki": "Misaki_Complete_Rigged.blend",
            "nanami": None, "tamaki": None}


def collect_vvp():
    products = []
    for name in ("elise", "fiona", "honoka", "misaki", "nanami", "tamaki"):
        src = j(VVP, name, "complete")
        if not exists(src):
            continue
        main = VVP_MAIN.get(name)
        if not main:
            found = files_in(src, "*.blend") or files_in(src, j("*", "*.blend"))
            main = os.path.relpath(found[0], src).replace("\\", "/") if found else None
        products.append(Product(name.title(), "blend", name.title() + "_Complete", src, main=main,
                                desc="完整交付包：.blend + .fbx（部分还有 .glb）+ 贴图 + 预览 + 报告"))
    if exists(j(VVP, "misaki", "COS_MIS_001")):
        products.append(Product("Misaki", "blend", "COS_MIS_001", j(VVP, "misaki", "COS_MIS_001"),
                                main="COS_MIS_001.blend", desc="单件服装导出"))
    for sub, model in (("complete_nnmhair", "Nude840_NNMHair"), ("complete", "Nude840_Complete")):
        src = j(VVP, "nude840", sub)
        if exists(src):
            blends = files_in(src, "*.blend")
            main = "Nude840_NNMHair_Aligned.blend" if exists(j(src, "Nude840_NNMHair_Aligned.blend")) else \
                (os.path.basename(blends[0]) if blends else None)
            products.append(Product("Nude840", "blend", model, src, main=main,
                                    desc="展示用裸体：840 身体 + 843 头 + NNM 发型（对齐版）"))
    for f in files_in(j(VVP, "nude836"), "*.blend"):
        products.append(Product("Nude836", "blend", "Nude836", j(VVP, "nude836"), main=os.path.basename(f),
                                desc="836 模特（躯干是灰色贴图）"))
    metas = [Meta(j(VVP, "inventory"), "inventory")]
    return products, metas


def regen_vvp():
    reason = "models\\、model_00xx_*、_nude_probe、各角色的 components\\ = 单件转换 / 探测输出，export_model.ps1 可重新生成"
    out = [(j(VVP, "models"), reason), (j(VVP, "model_*"), reason), (j(VVP, "_nude_probe"), reason),
           (j(VVP, "*", "components"), reason)]
    if not files_in(j(VVP, "nude836"), "*.blend"):
        out.append((j(VVP, "nude836"), reason))
    return out


# ---------------------------------------------------------------------------------------- Hotel VIP (2D)

HOTELVIP = r"D:\hotelvip_exports"


def collect_hotelvip():
    products = []
    for cat in subdirs(HOTELVIP):
        if cat.startswith("_"):
            continue
        products.append(Product("2D", "audio" if cat == "audio" else "png", cat, j(HOTELVIP, cat),
                                desc="这个游戏没有 3D 模型；导出的是 2D 美术"))
    metas = [Meta(j(HOTELVIP, "manifest.json"), "manifest.json"), Meta(j(HOTELVIP, "_gallery"), "gallery")]
    return products, metas


# ---------------------------------------------------------------------------------------- Rise of Eros

ROE = r"D:\roe_exports"
ROE_EXTRA = [r"D:\roe_exports_probe", r"D:\roe_out_a01", r"D:\roe_stage_a01"]
ROE_NAMES = {"a": "Inase", "b": "Kart", "c": "Misa", "d": "Erin", "e": "Miri", "f": "Rana", "g": "Luf", "h": "Fen",
             "i": "Sera", "j": "Lynn", "k": "Keleira", "l": "SFox", "m": "Amano"}
ROE_ID = re.compile(r"^[a-z]\d\d$")


def roe_character(key):
    """a01 / pc_a01_nk_bs -> Inase（字母 = 角色，数字 = 服装变体，见 scripts/riseoferos/character-roster.md）。"""
    m = re.match(r"^(?:pc_)?([a-z])\d", key)
    return ROE_NAMES.get(m.group(1), m.group(1)) if m else key


def collect_roe():
    products, metas = [], []
    for rid in subdirs(ROE):
        if not ROE_ID.match(rid):
            continue
        char = roe_character(rid)
        bdir = j(ROE, rid, "blend")
        for path in files_in(bdir, "*.blend"):
            stem = os.path.basename(path)[:-6]
            products.append(blend_file_product(char, "blend", stem, bdir, desc=rid))
        for stem in subdirs(j(bdir, "xps")):
            src = j(bdir, "xps", stem)
            products.append(Product(char, "xps", stem, src, main=stem + ".mesh" if exists(j(src, stem + ".mesh")) else None,
                                    desc="XPS（XNALara .mesh）"))
        for path in files_in(j(bdir, "glb"), "*.glb"):          # 套装拼装时顺带出的 glb（贴图在文件里）
            f = os.path.basename(path)
            products.append(Product(char, "glb", f[:-4], j(bdir, "glb"), main=f, include=[(f, f)], desc="glTF 二进制"))
        pdir = j(bdir, "pmx")
        stems = sorted(subdirs(pdir), key=len, reverse=True)
        owned = set()
        for stem in stems:
            # pmx\ 下以 <stem>_ 开头的场景 / 视频 / 预览（跳舞、布料、表情测试）跟着这个造型放进 _scenes\
            extra = [f for f in entries(pdir) if os.path.isfile(j(pdir, f)) and f.startswith(stem + "_")
                     and f not in owned and not f.lower().endswith((".blend1", ".part"))]
            owned.update(extra)
            inc = [("", "")] + [(j("..", f), j("_scenes", f)) for f in extra]
            products.append(Product(char, "pmx", stem, j(pdir, stem), main=stem + ".pmx",
                                    preview=j("_scenes", stem + "_pmx_preview.png") if stem + "_pmx_preview.png" in extra
                                    else None,
                                    desc="MMD PMX（Convert_to_MMD5）" + ("；_scenes\\ 里是跳舞 / 布料 / 表情测试场景和视频"
                                                                     if extra else ""),
                                    include=inc, package=True))
        for f in entries(pdir):
            if os.path.isfile(j(pdir, f)) and f not in owned and not f.lower().endswith(".blend1"):
                metas.append(Meta(j(pdir, f), j("pmx_work", rid, f)))
        if exists(j(bdir, "pmx_old")):
            metas.append(Meta(j(bdir, "pmx_old"), j("pmx_old", rid)))
    nude = j(ROE, "nude_materials")
    taken = {p.dest_rel().lower() for p in products}
    for path in files_in(nude, "*.blend"):
        stem = os.path.basename(path)[:-6]
        p = blend_file_product(roe_character(stem), "blend", stem, nude, desc="官方裸体基础模型（export_nude_models.ps1）")
        if p.dest_rel().lower() in taken:
            p.model = stem + "_nudebase"
        products.append(p)
    for fmt, pattern in (("fbx", "*.fbx"), ("glb", "*.glb")):
        for path in files_in(j(nude, fmt), pattern):
            f = os.path.basename(path)
            stem = f.rsplit(".", 1)[0]
            products.append(Product(roe_character(stem), fmt, stem, j(nude, fmt), main=f,
                                    include=[(f, f), (j("..", "textures"), "textures")], desc="官方裸体基础模型"))
    for path in files_in(j(nude, "pmx"), "*.pmx"):
        f = os.path.basename(path)
        stem = f[:-4]
        products.append(Product(roe_character(stem), "pmx", stem + "_nudebase", j(nude, "pmx"), main=f,
                                include=[(f, f), ("textures", "textures")], desc="官方裸体基础模型（早期 PMX，缩放未修正）"))
    for path in files_in(j(nude, "xps"), "*.mesh"):
        stem = os.path.basename(path)[:-5]
        products.append(Product(roe_character(stem), "xps", stem + "_nudebase", j(nude, "xps"),
                                main=os.path.basename(path), desc="官方裸体基础模型"))
    if exists(j(ROE, "en_flesh_horror_001")):
        products.append(Product("Enemy", "fbx", "en_flesh_horror_001", j(ROE, "en_flesh_horror_001"),
                                desc="敌人（AssetStudio FBX + 贴图，没有做成 .blend）"))
    metas += [Meta(j(ROE, "_gallery"), "gallery"),
              Meta(j(ROE, "character_models_manifest.json"), "character_models_manifest.json"),
              Meta(j(ROE, "character_models_manifest.pre-xps.json"), "character_models_manifest.pre-xps.json"),
              Meta(j(nude, "nude_models_manifest.json"), "nude_models_manifest.json"),
              Meta(j(nude, "textures"), "nude_textures")]
    for f in entries(j(ROE, "_suits")):
        if os.path.isfile(j(ROE, "_suits", f)):
            metas.append(Meta(j(ROE, "_suits", f), j("suits", f)))
    return products, metas


def regen_roe():
    raw = ("<角色>\\ 下除 blend\\ 以外的目录（*_obj001、Prefab_*、pc_*_hd、*.naked、_textures、export\\ ……）"
           "= AssetStudio 原始解包和早期手工导出，extract_character.ps1 可重新生成")
    out = []
    for rid in subdirs(ROE):
        if ROE_ID.match(rid):
            out += everything_but(j(ROE, rid), {"blend"}, raw)
    out += [(j(ROE, "_suits", "*", "*"), "_suits\\<角色>\\<套装>\\ = 套装零件中间数据（npz + 贴图），suit_bundle.py 可重新生成"),
            (j(ROE, "components_accessories"), "components_accessories = 饰品 FBX 原始解包，可重新生成"),
            (j(ROE, "xps_export"), "xps_export、pmx_manual = 早期手工导出，已被 blend\\xps、blend\\pmx 批量版取代"),
            (j(ROE, "pmx_manual"), "xps_export、pmx_manual = 早期手工导出，已被 blend\\xps、blend\\pmx 批量版取代"),
            (j(ROE, "dump_slots.py"), "dump_slots.py = 调试脚本"),
            (j(ROE, "nude_materials", "*.blend1"), "*.blend1 = Blender 自动备份"),
            (r"D:\roe_exports_probe", "roe_exports_probe = 09-12 检查更新时的探测解包"),
            (r"D:\roe_out_a01", "roe_out_a01、roe_stage_a01 = 07 月之前的早期试验输出 / 拷出来的 bundle"),
            (r"D:\roe_stage_a01", "roe_out_a01、roe_stage_a01 = 07 月之前的早期试验输出 / 拷出来的 bundle")]
    return out


# ---------------------------------------------------------------------------------------- misc

def collect_misc():
    return [], [Meta(r"D:\export", "D_export")]


MISC_REGEN = [(r"D:\test", "D:\\test = Vindictus PCF_005 XPS 测试输出"),
              (r"D:\tmp", "D:\\tmp = blender2xps 测试"),
              (r"D:\_claude_wip", "D:\\_claude_wip = 画廊教程草稿备份（已合进仓库）")]


# ---------------------------------------------------------------------------------------- registry

GAMES = {g.key: g for g in [
    Game("vindictus", "Vindictus", "Vindictus: Defying Fate（2024-03 Pre-Alpha）",
         sources=[VINDICTUS, FIONA_VAM], collect=collect_vindictus, regenerable=VINDICTUS_REGEN,
         galleries=["scripts/vindictus/html/index.html"],
         character_names={"Fiona": "玩家女角色 PCF", "Lethita": "玩家男角色 PCM", "Gnoll": "豺狼人",
                          "Goblin": "哥布林", "Kobold": "狗头人", "Knight": "NPC 男骑士",
                          "RoyalArmy": "王家军 NPC，只有佩剑"}),
    Game("tfd", "TheFirstDescendant", "The First Descendant",
         sources=[TFD], collect=collect_tfd, regenerable=TFD_REGEN,
         galleries=["scripts/firstdescendant/html/index.html"],
         notes=["_keys\\（AES key）拷到了 E:\\tools\\firstdescendant\\_keys，脚本默认还在读 D:\\tfd_exports\\_keys，"
                "删之后用 -AesKeyFile 指过去"]),
    Game("tod", "ThroneOfDesire", "Throne of Desire",
         sources=[TOD], collect=collect_tod, regenerable=regen_tod,
         galleries=["scripts/throneofdesire/html/index.html"]),
    Game("doa6", "DOA6", "DEAD OR ALIVE 6（本体 + mod）",
         sources=[DOA6, DOA_MODS, DOA_MOD_FBX], collect=collect_doa6, regenerable=regen_doa6,
         galleries=["scripts/doa6/html/index.html"]),
    Game("doa5lr", "DOA5LR", "DEAD OR ALIVE 5 Last Round",
         sources=[DOA5LR], collect=collect_doa5lr, regenerable=regen_doa5lr,
         galleries=["scripts/doa5lr/html/index.html"]),
    Game("ff7remake", "FF7Remake", "FINAL FANTASY VII REMAKE INTERGRADE（本体 + mod）",
         sources=[FF7R], collect=collect_ff7r, regenerable=regen_ff7r,
         galleries=["scripts/final/html/index.html"]),
    Game("ff7rebirth", "FF7Rebirth", "FINAL FANTASY VII REBIRTH（本体 + mod）",
         sources=[FF7RB, FF7_MODS], collect=collect_ff7rb, regenerable=regen_ff7rb,
         galleries=["scripts/final/html_rebirth/index.html"]),
    Game("stellarblade", "StellarBlade", "Stellar Blade（本体 + mod）",
         sources=[SB], collect=collect_sb, regenerable=regen_sb,
         galleries=["scripts/stellarblade/html/index.html"], aliases=aliases_sb,
         character_names={"Fiona": "Nexus mod「Vindictus Fiona」", "Reika": "Nexus mod「Gantz Reika」"}),
    Game("vam", "VaM", "Virt-A-Mate 1.22（外观 / 服装导出；Fiona 18 的 .duf）",
         sources=[VAM, VAM_IMPORTS], collect=collect_vam, regenerable=regen_vam,
         galleries=["scripts/vam/html/index.html"]),
    Game("naraka", "NARAKA", "NARAKA: BLADEPOINT（永劫无间）",
         sources=[NARAKA_D], collect=collect_naraka, regenerable=regen_naraka, aliases=aliases_naraka,
         character_names={zh: code for code, zh in NARAKA_HEROES.items()},
         list_pages=[("list", j(NARAKA_E, "_list")), ("list_samples", j(NARAKA_D, "_list"))]),
    Game("hs2", "HoneySelect2", "HoneySelect 2 (Libido DX)",
         sources=[HS2], collect=collect_hs2, regenerable=HS2_REGEN,
         galleries=["scripts/honeyselect2/html/index.html"], list_pages=[("list", j(HS2, "_list"))]),
    Game("vvp", "VenusVacationPRISM", "Venus Vacation PRISM",
         sources=[VVP], collect=collect_vvp, regenerable=regen_vvp),
    Game("hotelvip", "HotelVIP", "Hotel VIP（2D 游戏，没有 3D 模型）",
         sources=[HOTELVIP], collect=collect_hotelvip, galleries=["scripts/hotelvip/html/index.html"]),
    Game("roe", "RiseOfEros", "Rise of Eros",
         sources=[ROE] + ROE_EXTRA, collect=collect_roe, regenerable=regen_roe,
         galleries=["scripts/riseoferos/html/index.html"],
         character_names={v: "代号 %s" % k for k, v in ROE_NAMES.items()} | {"Enemy": "敌人"},
         notes=[r"ROE_pmx 窗口 09-26 还在 D:\roe_exports\<角色>\blend\pmx 里做东西；它的脚本默认也读写这里，"
                "等那边做完、再跑一次归档确认没有新文件再删"]),
    Game("misc", "_misc", "D 盘零散目录",
         sources=[r"D:\export", r"D:\test", r"D:\tmp", r"D:\_claude_wip"], collect=collect_misc,
         regenerable=MISC_REGEN),
]}

# 报告“还没处理”时列出的 D 盘导出目录
KNOWN_EXPORT_DIRS = [
    r"D:\doa5lr_exports", r"D:\doa6_exports", r"D:\doa_mods", r"D:\doa_mod_fbx", r"D:\export",
    r"D:\ff7_mods", r"D:\ff7rebirth_exports", r"D:\ff7remake_exports", r"D:\hotelvip_exports", r"D:\hs2_exports",
    r"D:\naraka_exports", r"D:\roe_exports", r"D:\roe_exports_probe", r"D:\roe_out_a01", r"D:\roe_stage_a01",
    r"D:\stellarblade_exports", r"D:\tfd_exports", r"D:\throneofdesire_exports", r"D:\vam_exports",
    r"D:\vam_imports", r"D:\venusvacationprism_exports", r"D:\vindictus_exports", r"D:\test", r"D:\tmp",
    r"D:\_claude_wip",
]
