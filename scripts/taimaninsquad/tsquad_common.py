"""Shared pieces of the Taimanin Squad pipeline: paths, the Addressables catalog, the bundle
(CAB) index and the model list.

The game (Steam, GREMORY Games, Unity 2022.3.62f3, IL2CPP) keeps everything in
``TaimaninSquad_Data/StreamingAssets/aa``: ``catalog.json`` (Addressables, 60k entries) and 999
plain UnityFS bundles (LZ4HC, not encrypted).  A unit ``<n>_<Name>`` has two bundles:

* ``localunit_aos_assets_<n>_<name>``: the art - ``<n>_<Name>/Art/fbx_<n>.fbx`` (meshes),
  ``Art/Materials`` (materials + textures) and ``Unit/prf_<n>.prefab`` (the unit prefab the
  game instantiates; ``prf_<n>_LOD1`` is the low-poly twin);
* ``localunit_assets_<n>_<name>``: animations, weapons, cutscene timelines, effects.

Bundle containers are keyed by asset GUID; the catalog maps the readable address
(``24_Kirara/Unit/prf_24.prefab``) to that GUID and to the bundle it lives in.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import math
import os
import re
import struct
import time

GAME_DIR = os.environ.get("TSQUAD_GAME_DIR", r"E:\SteamLibrary\steamapps\common\Taimanin Squad")
DATA_DIR = os.path.join(GAME_DIR, "TaimaninSquad_Data")
AA_DIR = os.path.join(DATA_DIR, "StreamingAssets", "aa")
BUNDLE_DIR = os.path.join(AA_DIR, "StandaloneWindows64")
CATALOG = os.path.join(AA_DIR, "catalog.json")
EXPORT_ROOT = os.environ.get("TSQUAD_EXPORT_ROOT", r"E:\game_export\TaimaninSquad")
BLENDER = os.environ.get("TSQUAD_BLENDER") or os.environ.get(
    "BLENDER", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")

CATEGORY_ORDER = ("character", "costume", "monster", "special", "boss", "mob")
CATEGORY_ZH = {"character": "角色", "costume": "角色的其他造型", "monster": "怪物 / 敌人", "special": "特殊单位",
               "boss": "Boss", "mob": "序章杂兵"}
UNIT_FOLDER = re.compile(r"^(B_)?(\d+)_([^/]+)$")
UNIT_PREFAB = re.compile(r"^((?:B_)?\d+_[^/]+)/Unit/(prf_[^/]+)\.prefab$")
# <n>_<Name>/Weapon/Prefab/prf_weapon_<n>_<grade>_<slot>.prefab: what the game hangs on the unit at run time.
# grade 0 / 1 / 2 = the look of the weapon as it is upgraded; slot L, R, O, R2, B ... = which of the unit's
# weapons.  Not only swords: Natsume's left arm and Saika's legs are "weapons" (see tsquad_scene.add_weapons).
WEAPON_PREFAB = re.compile(r"^((?:B_)?\d+_[^/]+)/Weapon/(?:[^/]+/)*(prf_weapon_(?:b_)?\d+_(\d+)(?:_([^/]+))?)\.prefab$",
                           re.IGNORECASE)
# icon folders, best first, used as the list thumbnail
ICON_SETS = ("Icon/Char/Portal", "Icon/Char/MainSlot", "Icon/Char/Set", "Icon/Char/BattleUnit")
# Female figures are told by their breast bones (the Magica Cloth group named Breast).  These have none
# and were picked by looking at every other unit's preview: three girls, a girl-shaped android (unit and
# boss), two masked sword maidens - and 80_shikanosuke, a boy in the story who is modelled as a girl.
FEMALE_BY_LOOK = frozenset(("80_shikanosuke", "81_library", "87_torajiro", "95_shizuku", "113_nao",
                            "158_paladin", "159_paladin2", "b_33_library"))


def log(msg: str) -> None:
    print("[tsquad] " + msg, flush=True)


def meta_dir(root: str = EXPORT_ROOT) -> str:
    return os.path.join(root, "_meta")


def work_dir(root: str = EXPORT_ROOT) -> str:
    return os.path.join(root, "_work")


def check_game() -> None:
    if not os.path.isfile(CATALOG):
        raise SystemExit("catalog.json not found: %s\nset TSQUAD_GAME_DIR to the game folder" % CATALOG)


def check_tools(need_blender: bool = True) -> None:
    check_game()
    if need_blender and not os.path.isfile(BLENDER):
        raise SystemExit("Blender not found: %s (set TSQUAD_BLENDER)" % BLENDER)


def load_json(path: str):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def save_json(path: str, data, indent=1) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


# ---------------------------------------------------------------- Addressables catalog
def _read_object(buf: bytes, off: int):
    """One serialized key / extra-data object of an Addressables 1.x catalog."""
    kind = buf[off]
    off += 1
    if kind == 0:                                   # ascii string
        n = struct.unpack_from("<i", buf, off)[0]
        return buf[off + 4:off + 4 + n].decode("ascii", "replace")
    if kind == 1:                                   # utf-16 string
        n = struct.unpack_from("<i", buf, off)[0]
        return buf[off + 4:off + 4 + n].decode("utf-16-le", "replace")
    if kind == 2:
        return struct.unpack_from("<H", buf, off)[0]
    if kind == 3:
        return struct.unpack_from("<I", buf, off)[0]
    if kind == 4:
        return struct.unpack_from("<i", buf, off)[0]
    return None                                     # hash128 / type / json object: not needed here


def parse_catalog(path: str = CATALOG) -> list[dict]:
    """Every bundled asset of the catalog: {"key", "guid", "type", "bundle"}.

    ``key`` is the address (``24_Kirara/Unit/prf_24.prefab``), ``guid`` the internal id, which is
    also the key of the bundle's own container, ``bundle`` the file the asset lives in (the first
    of the entry's dependency list)."""
    cat = load_json(path)
    ids = cat["m_InternalIds"]
    prefixes = cat.get("m_InternalIdPrefixes") or []
    providers = [p.rsplit(".", 1)[-1] for p in cat["m_ProviderIds"]]
    types = [t["m_ClassName"].rsplit(".", 1)[-1] for t in cat["m_resourceTypes"]]
    bucket = base64.b64decode(cat["m_BucketDataString"])
    key_data = base64.b64decode(cat["m_KeyDataString"])
    entry_data = base64.b64decode(cat["m_EntryDataString"])

    def internal_id(i: int) -> str:
        s = ids[i]
        if prefixes and "#" in s:
            head, rest = s.split("#", 1)
            if head.isdigit() and int(head) < len(prefixes):
                return prefixes[int(head)] + rest
        return s

    count = struct.unpack_from("<i", bucket, 0)[0]
    off = 4
    key_offsets, bucket_entries = [], []
    for _ in range(count):
        key_off, n = struct.unpack_from("<ii", bucket, off)
        off += 8
        bucket_entries.append(struct.unpack_from("<%di" % n, bucket, off))
        off += 4 * n
        key_offsets.append(key_off)
    n_entries = struct.unpack_from("<i", entry_data, 0)[0]
    entries = [struct.unpack_from("<7i", entry_data, 4 + i * 28) for i in range(n_entries)]

    def bundle_of(entry_index: int) -> str:
        return internal_id(entries[entry_index][0]).replace("\\", "/").rsplit("/", 1)[-1]

    first_bundle: dict[int, str] = {}
    assets = []
    for iid, prov, dep_key, _dep_hash, _data, primary, rtype in entries:
        if providers[prov] != "BundledAssetProvider" or dep_key < 0:
            continue
        if dep_key not in first_bundle:
            deps = bucket_entries[dep_key]
            first_bundle[dep_key] = bundle_of(deps[0]) if deps else ""
        assets.append({"key": _read_object(key_data, key_offsets[primary]), "guid": internal_id(iid),
                       "type": types[rtype], "bundle": first_bundle[dep_key]})
    return assets


def _signature() -> list:
    st = os.stat(CATALOG)
    return [st.st_size, int(st.st_mtime)]


def catalog_assets(root: str = EXPORT_ROOT, refresh: bool = False) -> list[dict]:
    """parse_catalog() cached in <root>/_meta/catalog_assets.json (re-parsed when catalog.json changes)."""
    cache = os.path.join(meta_dir(root), "catalog_assets.json")
    sig = _signature()
    if not refresh and os.path.isfile(cache):
        try:
            data = load_json(cache)
            if data.get("signature") == sig:
                return data["assets"]
        except (OSError, ValueError, KeyError):
            pass
    assets = parse_catalog()
    try:
        save_json(cache, {"signature": sig, "assets": assets}, indent=None)
    except OSError:
        pass
    return assets


# ---------------------------------------------------------------- UnityFS directory (CAB names)
def _cstr(buf: bytes, off: int):
    end = buf.index(b"\0", off)
    return buf[off:end].decode("utf-8", "replace"), end + 1


def bundle_directory(path: str) -> list[str]:
    """Names of the files inside a UnityFS bundle (``CAB-<hash>``, ``CAB-<hash>.resS``), read
    from the header and the blocks-info only - no data block is decompressed."""
    import lz4.block

    with open(path, "rb") as fh:
        head = fh.read(256)
        sig, off = _cstr(head, 0)
        if sig != "UnityFS":
            raise ValueError("not a UnityFS bundle: %s" % path)
        version = struct.unpack_from(">I", head, off)[0]
        off += 4
        _player, off = _cstr(head, off)
        _engine, off = _cstr(head, off)
        size, csize, usize, flags = struct.unpack_from(">qIII", head, off)
        off += 20
        if version >= 7:
            off = (off + 15) & ~15
        fh.seek(size - csize if flags & 0x80 else off)
        raw = fh.read(csize)
    comp = flags & 0x3F
    if comp in (2, 3):
        info = lz4.block.decompress(raw, uncompressed_size=usize)
    elif comp == 0:
        info = raw
    else:
        raise ValueError("blocks-info compression %d not handled: %s" % (comp, path))
    p = 16
    n_blocks = struct.unpack_from(">i", info, p)[0]
    p += 4 + n_blocks * 10
    n_nodes = struct.unpack_from(">i", info, p)[0]
    p += 4
    names = []
    for _ in range(n_nodes):
        p += 20
        name, p = _cstr(info, p)
        names.append(name)
    return names


def cab_index(root: str = EXPORT_ROOT, refresh: bool = False) -> dict[str, str]:
    """{cab name (lower case): bundle file name} for every bundle; cached in _meta/cab_index.json."""
    cache = os.path.join(meta_dir(root), "cab_index.json")
    files = sorted(f for f in os.listdir(BUNDLE_DIR) if f.endswith(".bundle"))
    sig = [len(files), _signature()]
    if not refresh and os.path.isfile(cache):
        try:
            data = load_json(cache)
            if data.get("signature") == sig:
                return data["index"]
        except (OSError, ValueError, KeyError):
            pass
    index = {}
    for name in files:
        try:
            for node in bundle_directory(os.path.join(BUNDLE_DIR, name)):
                index[node.lower()] = name
        except (OSError, ValueError, struct.error) as exc:
            log("skip %s: %s" % (name, exc))
    try:
        save_json(cache, {"signature": sig, "index": index}, indent=None)
    except OSError:
        pass
    return index


# ---------------------------------------------------------------- models
def category_of(folder: str) -> str:
    m = UNIT_FOLDER.match(folder)
    if m.group(1):
        return "boss"
    n = int(m.group(2))
    if n >= 997:
        return "mob"
    if n >= 300:
        return "special"
    if n >= 237:
        return "costume"
    if n >= 129:
        return "monster"
    return "character"


def _variant(prefab: str, folder: str) -> str:
    """prf_24 -> "", prf_16black -> "black", prf_58_sophie -> "sophie", prf_b_12 -> ""."""
    m = UNIT_FOLDER.match(folder)
    stem = "prf_%s%s" % ("b_" if m.group(1) else "", m.group(2))
    rest = prefab[len(stem):] if prefab.lower().startswith(stem) else prefab[4:]
    return rest.strip("_").lower()


def weapon_prefabs(assets: list[dict]) -> dict[str, list[dict]]:
    """{unit folder: [{"name", "grade", "slot", "key", "guid", "bundle"}]} - the weapon prefabs of the
    catalog without their ``_LOD1`` twins, by grade and slot."""
    out: dict[str, list[dict]] = {}
    for a in assets:
        key = a["key"]
        if not isinstance(key, str) or a["type"] != "GameObject":
            continue
        m = WEAPON_PREFAB.match(key)
        if m is None or re.search(r"_LOD\d*$", m.group(2), re.IGNORECASE):
            continue
        out.setdefault(m.group(1), []).append({
            "name": m.group(2), "grade": int(m.group(3)), "slot": (m.group(4) or "").upper(),
            "key": key, "guid": a["guid"], "bundle": a["bundle"]})
    for rows in out.values():
        rows.sort(key=lambda w: (w["slot"], w["grade"], w["name"]))
    return out


def pick_weapons(weapons: list[dict], grade: int = 0) -> list[dict]:
    """One prefab per slot: the look of weapon grade `grade`, else the nearest lower grade the slot has.
    A slot that only exists from a higher grade on (the ``_B`` extras of grades 1 and 2) is left out."""
    best: dict[str, dict] = {}
    for w in weapons:
        if w["grade"] <= grade and (w["slot"] not in best or w["grade"] > best[w["slot"]]["grade"]):
            best[w["slot"]] = w
    return [best[slot] for slot in sorted(best)]


def discover_models(assets: list[dict], root: str = EXPORT_ROOT) -> list[dict]:
    """One model per unit prefab (the ``_LOD1`` twins are attached to their LOD0 model)."""
    by_folder: dict[str, dict] = {}
    icons: dict[str, dict] = {}
    weapons = weapon_prefabs(assets)
    for a in assets:
        key = a["key"]
        if not isinstance(key, str):
            continue
        m = UNIT_PREFAB.match(key)
        if m and a["type"] == "GameObject":
            by_folder.setdefault(m.group(1), {})[m.group(2)] = a
            continue
        if a["type"] == "Texture2D" and key.startswith("Icon/Char/"):
            folder, name = key.rsplit("/", 1)
            icons.setdefault(os.path.splitext(name)[0].lower(), {})[folder] = a
    main_bundles = {}
    for a in assets:
        key = a["key"]
        if isinstance(key, str) and "/Animation/" in key and a["type"] == "AnimationClip":
            main_bundles.setdefault(key.split("/", 1)[0], a["bundle"])
    models = []
    for folder, prefabs in by_folder.items():
        m = UNIT_FOLDER.match(folder)
        if not m:
            continue
        number, name = int(m.group(2)), m.group(3)
        lod0 = {p: a for p, a in prefabs.items() if not re.search(r"_LOD\d*$", p, re.IGNORECASE)}
        if not lod0:                                   # 184_Xps11a ships only prf_184_LOD
            lod0 = dict(prefabs)
        for prefab, a in sorted(lod0.items()):
            variant = _variant(prefab, folder)
            if variant.startswith("lod"):
                variant = ""
            model_id = folder.lower() + ("_" + variant if variant else "")
            low = prefabs.get(prefab + "_LOD1")
            icon = None
            for icon_set in ICON_SETS:
                icon = icons.get(folder.lower(), {}).get(icon_set)
                if icon:
                    break
            models.append({
                "id": model_id, "folder": folder, "number": number, "boss": bool(m.group(1)),
                "name": name + ((" " + variant.capitalize()) if variant else ""), "group": name,
                "category": category_of(folder), "prefab": prefab, "key": a["key"], "guid": a["guid"],
                "bundle": a["bundle"], "main_bundle": main_bundles.get(folder),
                "weapons": weapons.get(folder, []),
                "lod1_guid": low["guid"] if low else None,
                "icon": {"key": icon["key"], "guid": icon["guid"], "bundle": icon["bundle"]} if icon else None,
                "playable": "Icon/Char/Portal" in icons.get(folder.lower(), {}),
            })
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    models.sort(key=lambda x: (order[x["category"]], x["number"], x["id"]))
    for model in models:
        model["exported"] = exported_formats(model, root)
    return models


def model_dir(model: dict, root: str = EXPORT_ROOT, fmt: str = "blend") -> str:
    """<root>/<Character>/<format>/<id>/ - the E:/game_export layout (every folder opens on its own)."""
    return os.path.join(root, model["group"], fmt, model["id"])


def exported_formats(model: dict, root: str = EXPORT_ROOT) -> list[str]:
    out = []
    for fmt, ext in (("blend", ".blend"), ("xps", ".xps"), ("pmx", ".pmx")):
        if os.path.isfile(os.path.join(model_dir(model, root, fmt), model["id"] + ext)):
            out.append(fmt)
    return out


def is_female(model: dict) -> bool:
    """Breast bones (model["details"], see list_models.add_details) or one of FEMALE_BY_LOOK."""
    return bool((model.get("details") or {}).get("bust")) or model["id"] in FEMALE_BY_LOOK


def find_models(models: list[dict], patterns: list[str]) -> list[dict]:
    """ids, numbers (``24``), names or group names, wildcards allowed; order of first match kept."""
    out, missing = [], []
    for pat in patterns:
        p = pat.lower()
        hits = [m for m in models if m["id"] == p]
        if not hits and p.isdigit():
            hits = [m for m in models if m["number"] == int(p) and not m["boss"]]
        if not hits:
            hits = [m for m in models if m["group"].lower() == p or m["name"].lower() == p]
        if not hits:
            hits = [m for m in models if fnmatch.fnmatch(m["id"], p) or fnmatch.fnmatch(m["name"].lower(), p)]
        if not hits and not any(c in p for c in "*?["):
            hits = [m for m in models if p in m["id"]]
        if not hits:
            missing.append(pat)
        for m in hits:
            if m not in out:
                out.append(m)
    if missing:
        raise SystemExit("no model matches: %s  (python list_models.py shows them)" % ", ".join(missing))
    return out


# ---------------------------------------------------------------- breast physics of the PMX
# In the game the breasts are a Magica Cloth "Bone Spring": the bone SLIDES on a spring around its place
# (up to 5 cm for Asagi, any direction) and gravity is switched off for it.  The MMD joint does the same
# with three sprung sliding axes (tsquad_blender.spring_bust).  One thing MMD cannot do is switch gravity
# off, and a spring that gives to a bounce gives to gravity just the same - it sags by g / (2 pi f)^2
# (1.5 cm at 3.6 Hz, 2.5 cm at 2.8 Hz).  So the up-down spring is the stiff one, and side to side / front
# to back, where gravity does not pull, are soft.
#
# Every value is a default: --bust key=value,... changes it (export_model.py, dance_video.py).  The springs
# and the travel were tuned on 1_Asagi.  Another unit gets them fitted (bust_fitted): a smaller breast
# travels proportionally less on proportionally stiffer springs, and no breast goes further than the game
# lets it (the limitDistance of the unit's own Bone Spring).
BUST = {
    "style": "spring",      # "spring": sliding springs as above; "swing": the worker's template (a +-10 degree pivot, no spring)
    "sway_hz": 2.2,         # side to side
    "depth_hz": 2.6,        # front to back
    "bounce_hz": 3.6,       # up and down
    "sway_cm": 5.0,         # how far it may travel: to each side,
    "depth_cm": 4.0,        # forward and back,
    "bounce_cm": 4.0,       # up and down (the sag is inside this)
    "ratio": 0.25,          # damping ratio of the softest axis: 0.1 rings on, 0.25 swings twice, 0.7 only gives way
    "tilt_deg": 0.0,        # how far the breast may also turn (0 = it only slides, like the game's)
    "tilt_hz": 3.0,
    "mass": 1.0,
    "ang_damp": 0.99,
    "amount": 1.0,          # more or less of it all: 0.5 = half the travel (on stiffer springs), 1.3 = a third more
    "size_cm": 10.9,        # the breast the values above are for (Asagi's): its skin's centre lies this far from its
    #                         bone.  A smaller breast gets proportionally less travel, a larger one more.  0 = all alike
    "game": 1.0,            # 1 = no breast travels further than the game lets this unit's (cap_cm), 0 = never mind the game
    "cap_cm": 0.0,          # that limit in cm (limitDistance x blendWeight of the unit's Bone Spring; 0 = none known).
    #                         export_model.py / dance_video.py read it from the game; name it yourself to overrule them
}
PMX_UNITS = 12.5            # one metre in PMX units (mmd_tools exports at 12.5 and imports at 0.08)
MMD_GRAVITY = 98.0          # PMX units / s^2
BUST_SIZE = (0.4, 1.2)      # how much a breast's size may change the travel (x): a flat chest still moves a little
BUST_FACTOR = (0.25, 1.6)   # and all in all: the travel between a quarter of the settings' and 1.6 times
BUST_MAX_RATE = 14.0        # MMD has one damping for a breast, the rigid body's: v *= (1 - d) ** t.  The decay rate
#                             -ln(1 - d) = 2 ratio w must stay well under 16.6, where d rounds to 1.0 in the PMX's
#                             32-bit float - a body damped by 1.0 stops dead each step and hangs on its limits


def parse_bust(text: str | None) -> dict:
    """BUST with the values of "key=value,key=value" put in ("bounce_hz=3,ratio=0.2")."""
    params = dict(BUST)
    for item in (text or "").replace(";", ",").split(","):
        if not item.strip():
            continue
        key, _eq, value = item.partition("=")
        key = key.strip()
        if key not in BUST:
            raise SystemExit("--bust: no such setting %r (there are: %s)" % (key, ", ".join(BUST)))
        if isinstance(BUST[key], str):
            params[key] = value.strip()
            continue
        try:
            params[key] = float(value)
        except ValueError:
            raise SystemExit("--bust: %s wants a number, not %r" % (key, value.strip())) from None
    if params["style"] not in ("spring", "swing"):
        raise SystemExit("--bust: style is spring or swing, not %r" % params["style"])
    return params


def bust_text(params: dict) -> str:
    """The settings as one --bust argument (what export_model.py / dance_video.py hand to Blender)."""
    return ",".join("%s=%s" % (key, params[key] if isinstance(BUST[key], str) else "%g" % params[key]) for key in BUST)


def bust_sag_cm(params: dict, gravity: float = MMD_GRAVITY) -> float:
    """How far the up-down spring gives to gravity, in cm (gravity in PMX units / s^2: MMD's 98)."""
    return gravity / PMX_UNITS / (2.0 * math.pi * params["bounce_hz"]) ** 2 * 100.0


def bust_for_unit(params: dict, spring: dict | None, text: str | None = "") -> dict:
    """`params` with the unit's travel limit put in as cap_cm: limitDistance x blendWeight of its Bone
    Spring (`spring`, from tsquad_scene.breast_spring; None = the unit has none, nothing changes).  A
    cap_cm named in the --bust `text` itself stays."""
    out = dict(params)
    named = {item.partition("=")[0].strip() for item in (text or "").replace(";", ",").split(",")}
    if spring and "cap_cm" not in named:
        blend = min(max(float(spring.get("blend_weight") or 1.0), 0.0), 1.0)
        out["cap_cm"] = round(float(spring["limit_distance"]) * blend * 100.0, 2)
    return out


def bust_fitted(params: dict, size_cm: float | None = None) -> tuple[dict, float]:
    """(the settings one breast gets, the factor they were fitted by).

    factor = amount x (the breast's size against size_cm, inside BUST_SIZE), not above cap_cm / sway_cm
    when "game" is on, and inside BUST_FACTOR.  The travel (*_cm) is multiplied by it and the springs are
    retuned so that the breast uses the same share of its travel as before: a dance that swings Asagi's
    3.7 of her 5 cm swings a breast with factor 0.5 about 1.9 of its 2.5 - sideways and front to back by
    1 / sqrt(factor) in frequency (the swing a push causes goes with 1 / f^2).  Up and down gravity has
    its say: the spring is never softened there (the breast would hang lower), only stiffened.  The
    damping ratio stays, unless the rigid body's damping could not hold it (BUST_MAX_RATE)."""
    size = 1.0
    if size_cm and params["size_cm"] > 0:
        size = min(max(size_cm / params["size_cm"], BUST_SIZE[0]), BUST_SIZE[1])
    factor = params["amount"] * size
    if params["game"] >= 0.5 and params["cap_cm"] > 0:
        factor = min(factor, params["cap_cm"] / params["sway_cm"])
    factor = round(min(max(factor, BUST_FACTOR[0]), BUST_FACTOR[1]), 2)
    out = dict(params)
    stiff = 1.0 / math.sqrt(factor)
    for key in ("sway_cm", "depth_cm", "bounce_cm"):
        out[key] = round(params[key] * factor, 2)
    out["sway_hz"] = round(params["sway_hz"] * stiff, 2)
    out["depth_hz"] = round(params["depth_hz"] * stiff, 2)
    out["bounce_hz"] = round(params["bounce_hz"] * max(1.0, stiff), 2)
    softest = 2.0 * math.pi * min(out["sway_hz"], out["depth_hz"], out["bounce_hz"])
    out["ratio"] = round(min(params["ratio"], BUST_MAX_RATE / (2.0 * softest)), 3)
    return out, factor


def record_export(root: str, reports: list[dict]) -> None:
    """Merge reports into <root>/_meta/exports.json under a lock file (batches may run in parallel)."""
    path = os.path.join(meta_dir(root), "exports.json")
    os.makedirs(meta_dir(root), exist_ok=True)
    lock = path + ".lock"
    fd = None
    for _ in range(300):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:                                       # left behind by a batch that was killed mid-write
                if time.time() - os.path.getmtime(lock) > 30:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            time.sleep(0.2)
    try:
        data = {}
        if os.path.isfile(path):
            try:
                data = load_json(path)
            except (OSError, ValueError):
                data = {}
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for rep in reports:
            if rep.get("skipped"):
                continue
            old = data.get(rep["id"], {})
            # "<stage> failed ..." of an earlier run is over once that stage has its product
            fixed = tuple(stage for stage in ("turntable", "xps", "pmx") if rep.get(stage))
            warnings = [w for w in old.get("warnings") or [] if not str(w).lower().startswith(fixed)]
            warnings += [w for w in rep.get("warnings") or [] if w not in warnings]
            entry = {**old, "time": stamp, **{k: v for k, v in rep.items() if v is not None}}
            entry.pop("warnings", None)
            if warnings:
                entry["warnings"] = warnings
            data[rep["id"]] = entry
        save_json(path, data)
    finally:
        if fd is not None:
            os.close(fd)
            os.remove(lock)
