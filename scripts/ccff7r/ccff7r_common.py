"""Shared settings and helpers for the CRISIS CORE -FINAL FANTASY VII- REUNION (CCFF7R) scripts.

The game is Unreal Engine 4.27.2 with IoStore containers (.utoc/.ucas), an AES-encrypted pak index
and unversioned properties, so every read goes through the patched CUE4Parse CLI with:

  * the AES key   - recovered from the exe by scripts/firstdescendant/find_aes_key.py and kept in
                    KEY_FILE (outside the repo) or the CCFF7R_AES_KEY environment variable;
  * a .usmap      - TheNaeem/Unreal-Mappings-Archive CCFF7R/Mappings.usmap (2022-12-17); without it
                    CUE4Parse refuses every package ("Could not load standard asset").

Nothing secret lives in this file.  Paths can be overridden with CCFF7R_* environment variables.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

GAME_DIR = os.environ.get("CCFF7R_GAME_DIR", r"E:\SteamLibrary\steamapps\common\CCFF7R")
CLI = os.environ.get("CCFF7R_CLI", r"E:\tools\cue4parse_cli_ff7\cue4parse.exe")
KEY_FILE = os.environ.get("CCFF7R_AES_KEY_FILE", r"E:\tools\ccff7r\_keys\ccff7r_aes.txt")
USMAP = os.environ.get("CCFF7R_USMAP", r"E:\tools\ccff7r\mappings\CCFF7R-4.27-20221217-Mappings.usmap")
GAME_VERSION = "GAME_UE4_27"
EXPORT_ROOT = os.environ.get("CCFF7R_EXPORT_ROOT", r"E:\game_export\CCFF7R")
BLENDER = os.environ.get("CCFF7R_BLENDER", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")

PROJECT = "CCFF7R/Content/"
MESH_RE = re.compile(r"^CCFF7R/Content/Fair/Character/(?P<cat>0\d_[a-z]+)/(?P<folder>[^/]+)/Mesh/(?P<mesh>SK_[^/]+)\.uasset$")
OBJECT_RE = re.compile(r"^CCFF7R/Content/Fair/Object/(?P<folder>[^/]+)/Mesh/(?P<mesh>SK_[^/]+)\.uasset$")
FOLDER_RE = re.compile(r"^(CCFF7R/Content/Fair/(?:Character/0\d_[a-z]+|Object)/[^/]+/)")
SW_RE = re.compile(r"_sw$", re.IGNORECASE)   # the "_SW" twin: same geometry, *_Lite materials

CATEGORIES = {"01_named": "named", "02_limit": "limit", "03_mob": "npc", "04_enemy": "enemy"}
CATEGORY_ORDER = ["named", "limit", "npc", "enemy", "object"]
CATEGORY_ZH = {"named": "主要角色", "limit": "召唤兽 (DMW)", "npc": "NPC", "enemy": "敌人", "object": "道具 / 武器"}

# folder -> (group folder under EXPORT_ROOT, English, Chinese).  Folders of one person share a group
# (zack_s11 ... zack_costa -> Zack), like the other games in E:\game_export.
NAMED = {
    "aerith": ("Aerith", "Aerith", "爱丽丝"),
    "angeal": ("Angeal", "Angeal", "安吉尔"),
    "angeal2": ("Angeal", "Angeal", "安吉尔"),
    "angeal_mon": ("Angeal", "Angeal", "安吉尔"),
    "angeal_wing": ("Angeal", "Angeal", "安吉尔"),
    "cloud_hei": ("Cloud", "Cloud", "克劳德"),
    "cloud_sol": ("Cloud", "Cloud", "克劳德"),
    "genesis01": ("Genesis", "Genesis", "杰内西斯"),
    "genesis_wing": ("Genesis", "Genesis", "杰内西斯"),
    "genesis_worse": ("Genesis", "Genesis", "杰内西斯"),
    "genesis_worse2": ("Genesis", "Genesis", "杰内西斯"),
    "gillian": ("Gillian", "Gillian", "吉莉安"),
    "hojo": ("Hojo", "Hojo", "宝条"),
    "hollander": ("Hollander", "Hollander", "霍兰德"),
    "hollander_worse": ("Hollander", "Hollander", "霍兰德"),
    "hollander_worse2": ("Hollander", "Hollander", "霍兰德"),
    "lazard": ("Lazard", "Lazard", "拉扎德"),
    "lazard_worse": ("Lazard", "Lazard", "拉扎德"),
    "nero": ("Nero", "Nero", "尼禄"),
    "reno": ("Reno", "Reno", "雷诺"),
    "rude": ("Rude", "Rude", "路德"),
    "sephiroth": ("Sephiroth", "Sephiroth", "萨菲罗斯"),
    "sephiroth_evil": ("Sephiroth", "Sephiroth", "萨菲罗斯"),
    "tian": ("Cissnei", "Cissnei", "西丝妮"),
    "tian_costa": ("Cissnei", "Cissnei", "西丝妮"),
    "tifa": ("Tifa", "Tifa", "蒂法"),
    "tseng": ("Tseng", "Tseng", "曾"),
    "weiss": ("Weiss", "Weiss", "维斯"),
    "yuffie": ("Yuffie", "Yuffie", "尤菲"),
    "zack_costa": ("Zack", "Zack", "扎克斯"),
    "zack_s11": ("Zack", "Zack", "扎克斯"),
    "zack_s12": ("Zack", "Zack", "扎克斯"),
    "zack_s13": ("Zack", "Zack", "扎克斯"),
    "zack_s21": ("Zack", "Zack", "扎克斯"),
    "cait_sith1": ("CaitSith", "Cait Sith", "凯特·西"),
    "chocobo1": ("Chocobo", "Chocobo", "陆行鸟"),
    "moogle": ("Moogle", "Moogle", "莫古利"),
}


# ---------------------------------------------------------------- paths
def meta_dir(root: str = EXPORT_ROOT) -> str:
    return os.path.join(root, "_meta")


def work_dir(root: str = EXPORT_ROOT) -> str:
    """CLI output (PSK / PNG / JSON) and build specs: a cache, safe to delete, rebuilt on demand."""
    return os.path.join(root, "_work")


def object_to_package(object_path: str) -> str | None:
    """'/Game/Fair/X/T_a.0' -> 'CCFF7R/Content/Fair/X/T_a.uasset' ('/Engine/...' -> 'Engine/Content/...')."""
    if not object_path:
        return None
    path = object_path.split("'")[1] if "'" in object_path else object_path
    base, dot, tail = path.rpartition(".")
    if dot and "/" not in tail:
        path = base
    if path.startswith("/Game/"):
        return PROJECT + path[len("/Game/"):] + ".uasset"
    if path.startswith("/Engine/"):
        return "Engine/Content/" + path[len("/Engine/"):] + ".uasset"
    return None


def package_file(root: str, package: str, ext: str) -> str:
    """Where the CLI writes a package's export: <root>/<package path without .uasset><ext>."""
    stem = package[:-len(".uasset")] if package.endswith(".uasset") else package
    return os.path.join(root, *stem.split("/")) + ext


def asset_name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1].split(".")[0]


# ---------------------------------------------------------------- grouping / names
_ENEMY_TAIL = re.compile(r"(_lw\d*|_worse\d*|_evt|_d|_w|\d+)$")


def enemy_group(folder: str) -> str:
    """behemoth2 -> Behemoth, black_mask_w_worse -> BlackMask, g_copy_aw1 -> GCopyAw."""
    name = folder
    while True:
        new = _ENEMY_TAIL.sub("", name)
        if new == name or not new:
            break
        name = new
    return "".join(part.capitalize() for part in name.split("_") if part) or folder


def describe(category: str, folder: str) -> tuple[str, str, str]:
    """(group folder, English name, Chinese name) for a model folder."""
    if folder in NAMED:
        return NAMED[folder]
    if category == "npc":
        return "NPC", folder, ""
    if category == "enemy":
        return "Enemy_" + enemy_group(folder), folder, ""
    if category == "object":
        return "Objects", folder, ""
    return folder.capitalize(), folder, ""


def model_dir(model: dict, root: str = EXPORT_ROOT, fmt: str = "blend") -> str:
    return os.path.join(root, model["group"], fmt, model["id"])


# ---------------------------------------------------------------- CLI
def read_key() -> str:
    key = os.environ.get("CCFF7R_AES_KEY", "").strip()
    if not key and os.path.isfile(KEY_FILE):
        key = open(KEY_FILE, encoding="utf-8").read().strip()
    if not key:
        raise SystemExit("no AES key: put the 0x... key into %s or set CCFF7R_AES_KEY "
                         "(recover it with scripts/firstdescendant/find_aes_key.py, see README)" % KEY_FILE)
    return key


def check_tools(need_blender: bool = False) -> None:
    items = [("game", GAME_DIR), ("CUE4Parse CLI", CLI), ("usmap", USMAP)]
    if need_blender:
        items.append(("Blender 3.6", BLENDER))
    missing = ["%s: %s" % (label, path) for label, path in items if not os.path.exists(path)]
    if missing:
        raise SystemExit("missing:\n  " + "\n  ".join(missing))


def run_cli(args: list[str], timeout: int = 3600) -> str:
    """Run the CLI on the game with key + mappings; returns stdout.  The key never reaches the error text."""
    key = read_key()
    cmd = [CLI, "-i", GAME_DIR, "-g", GAME_VERSION, "-k", key, "-m", USMAP] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or "")).replace("\r", "\n").replace(key, "<key>")
        tail = "\n".join(line for line in tail.splitlines() if line.strip() and "Exporting package" not in line)
        raise RuntimeError("cue4parse exit %d:\n%s" % (r.returncode, tail[-2500:]))
    return r.stdout or ""


def export_packages(packages, out_dir: str, fmt: str | None = None, extra=()) -> None:
    """Export packages through a list file.  Duplicates are dropped first: the CLI exports in parallel
    and two entries for one package race on the same output file (IOException, whole run aborts)."""
    unique = sorted({p for p in packages if p})
    if not unique:
        return
    os.makedirs(out_dir, exist_ok=True)
    fd, list_path = tempfile.mkstemp(prefix="ccff7r_packages_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(unique) + "\n")
    try:
        args = ["-c", list_path, "-o", out_dir, "-y"]
        if fmt:
            args += ["-f", fmt]
        run_cli(args + list(extra))
    finally:
        os.remove(list_path)


def game_signature() -> str:
    """Sizes + mtimes of the containers: the cached package list is rebuilt when the game updates."""
    paks = os.path.join(GAME_DIR, "CCFF7R", "Content", "Paks")
    parts = []
    for name in sorted(os.listdir(paks)):
        if name.endswith((".pak", ".utoc")):
            st = os.stat(os.path.join(paks, name))
            parts.append("%s:%d:%d" % (name, st.st_size, int(st.st_mtime)))
    return "|".join(parts)


def list_packages(root: str = EXPORT_ROOT, refresh: bool = False) -> list[str]:
    """Every package path in the game (70,666 on build 10871899), cached in <root>/_meta/packages.txt."""
    cache = os.path.join(meta_dir(root), "packages.txt")
    sig_path = cache + ".sig"
    sig = game_signature()
    if (not refresh and os.path.isfile(cache) and os.path.isfile(sig_path)
            and open(sig_path, encoding="utf-8").read() == sig):
        with open(cache, encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip()]
    out = run_cli(["-l"])
    packages = sorted({line.strip() for line in out.splitlines()
                       if line.strip().startswith(("CCFF7R/", "Engine/"))})
    if not packages:
        raise SystemExit("the CLI listed no packages - wrong AES key or game folder?")
    os.makedirs(meta_dir(root), exist_ok=True)
    with open(cache, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(packages) + "\n")
    with open(sig_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sig)
    return packages


# ---------------------------------------------------------------- models
def discover_models(packages: list[str], include_objects: bool = True, root: str = EXPORT_ROOT) -> list[dict]:
    """One model per SK_* mesh (its "_SW" twin recorded alongside), with per-folder asset counts."""
    folders: dict[tuple[str, str], dict] = {}
    for pkg in packages:
        m = MESH_RE.match(pkg)
        category = None
        if m:
            category = CATEGORIES.get(m.group("cat"))
            prefix = pkg[:pkg.index("/Mesh/") + 1]
        elif include_objects:
            m = OBJECT_RE.match(pkg)
            if m:
                category = "object"
                prefix = pkg[:pkg.index("/Mesh/") + 1]
        if not m or not category:
            continue
        entry = folders.setdefault((category, m.group("folder")), {"prefix": prefix, "meshes": {}, "sw": {}})
        mesh = m.group("mesh")
        if SW_RE.search(mesh):
            entry["sw"][SW_RE.sub("", mesh).lower()] = pkg
        else:
            entry["meshes"][mesh] = pkg

    counts: dict[str, dict] = {}
    prefixes = {e["prefix"] for e in folders.values()}
    for pkg in packages:
        m = FOLDER_RE.match(pkg)
        if not m or not pkg.endswith(".uasset") or m.group(1) not in prefixes:
            continue
        c = counts.setdefault(m.group(1), {"textures": 0, "materials": 0, "animations": 0})
        if "/Texture/" in pkg:
            c["textures"] += 1
        elif "/Material/" in pkg and "/CutScene/" not in pkg:
            c["materials"] += 1
        elif "/Animation/" in pkg:
            c["animations"] += 1

    models = []
    for (category, folder), entry in folders.items():
        meshes = sorted(entry["meshes"].items())
        for mesh, pkg in meshes:
            model_id = folder if len(meshes) == 1 else mesh.lower()
            group, name_en, name_zh = describe(category, folder)
            c = counts.get(entry["prefix"], {})
            model = {
                "id": model_id, "category": category, "folder": folder, "mesh": mesh, "package": pkg,
                "sw_package": entry["sw"].get(mesh.lower()), "group": group, "name_en": name_en,
                "name_zh": name_zh, "textures": c.get("textures", 0), "materials": c.get("materials", 0),
                "animations": c.get("animations", 0),
            }
            blend = os.path.join(model_dir(model, root), model_id + ".blend")
            model["blend"] = blend
            model["exported"] = os.path.isfile(blend)
            models.append(model)
    models.sort(key=lambda m: (CATEGORY_ORDER.index(m["category"]), m["group"], m["id"]))
    return models


def find_models(models: list[dict], selectors: list[str]) -> list[dict]:
    """Select by id, folder, mesh name, group (Zack), English/Chinese name or category; '*' wildcards."""
    chosen = []
    for sel in selectors:
        s = sel.lower()
        # an exact id wins: "sephiroth" is that model, not the whole Sephiroth group
        hits = [m for m in models if m["id"].lower() == s]
        rx = re.compile("^" + re.escape(s).replace(r"\*", ".*") + "$")
        hits = hits or [m for m in models if any(rx.match(str(v).lower()) for v in (
            m["id"], m["folder"], m["mesh"], m["group"], m["name_en"], m["name_zh"], m["category"]) if v)]
        if not hits:
            raise SystemExit("no model matches %r (python list_models.py --find ... shows the ids)" % sel)
        for m in hits:
            if m not in chosen:
                chosen.append(m)
    return chosen


def load_json(path: str):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)
