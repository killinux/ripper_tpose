"""HoneySelect 2 (Libido DX) game data: item lists, bundle dependencies, character cards.

Everything here is read-only and needs only UnityPy (the lists are MessagePack inside
TextAssets; `hs2_msgpack` decodes them).  Used by list_models.py and export_model.py.
"""
import io
import json
import os
import struct

import hs2_msgpack

GAME_DEFAULT = r"E:\SteamLibrary\steamapps\common\HoneySelect2Libido DX"
EXPORTS_DEFAULT = r"D:\hs2_exports"

# categoryNo -> (list key, sex, group, 中文名).  Only the categories whose rows point at a
# prefab (MainAB + MainData) are "models"; skins/makeup/etc. are texture lists used for lookups.
MODEL_CATEGORIES = {
    210: ("fo_head", "female", "head", "脸型"),
    110: ("mo_head", "male", "head", "脸型"),
    240: ("fo_top", "female", "clothes", "上衣"),
    241: ("fo_bot", "female", "clothes", "下装"),
    242: ("fo_inner_t", "female", "clothes", "内衣（上）"),
    243: ("fo_inner_b", "female", "clothes", "内衣（下）"),
    244: ("fo_gloves", "female", "clothes", "手套"),
    245: ("fo_panst", "female", "clothes", "连裤袜"),
    246: ("fo_socks", "female", "clothes", "袜子"),
    247: ("fo_shoes", "female", "clothes", "鞋"),
    140: ("mo_top", "male", "clothes", "上衣"),
    141: ("mo_bot", "male", "clothes", "下装"),
    144: ("mo_gloves", "male", "clothes", "手套"),
    147: ("mo_shoes", "male", "clothes", "鞋"),
    300: ("so_hair_b", "both", "hair", "后发"),
    301: ("so_hair_f", "both", "hair", "前发"),
    302: ("so_hair_s", "both", "hair", "侧发"),
    303: ("so_hair_o", "both", "hair", "附加发"),
    351: ("ao_head", "both", "accessory", "饰品·头"),
    352: ("ao_ear", "both", "accessory", "饰品·耳"),
    353: ("ao_glasses", "both", "accessory", "饰品·眼镜"),
    354: ("ao_face", "both", "accessory", "饰品·脸"),
    355: ("ao_neck", "both", "accessory", "饰品·颈"),
    356: ("ao_shoulder", "both", "accessory", "饰品·肩"),
    357: ("ao_chest", "both", "accessory", "饰品·胸"),
    358: ("ao_waist", "both", "accessory", "饰品·腰"),
    359: ("ao_back", "both", "accessory", "饰品·背"),
    360: ("ao_arm", "both", "accessory", "饰品·臂"),
    361: ("ao_hand", "both", "accessory", "饰品·手"),
    362: ("ao_leg", "both", "accessory", "饰品·腿"),
    363: ("ao_kokan", "both", "accessory", "饰品·股间"),
}
KEY_TO_CATEGORY = {v[0]: k for k, v in MODEL_CATEGORIES.items()}

# texture lists a character build looks up (card id -> texture names)
CAT_SKIN_FACE = {"female": 211, "male": 111}
CAT_DETAIL_FACE = {"female": 212, "male": 112}
CAT_SKIN_BODY = {"female": 231, "male": 131}
CAT_DETAIL_BODY = {"female": 232, "male": 132}
CAT_EYEBROW, CAT_EYELASH, CAT_EYE, CAT_EYEBLACK, CAT_EYE_HL = 314, 315, 317, 318, 319
CAT_NIP, CAT_UNDERHAIR = 334, 335

# the two base bodies live in chara/oo_base.unity3d, head skeleton alongside them
BASE_BUNDLE = "chara/oo_base.unity3d"
# p_cf_anim is the runtime skeleton (both sexes; carries the 40 body N_* accessory nodes);
# the body mesh prefabs carry a same-pose copy of its bones that is re-bound by name.
BODIES = {
    "female": {"skeleton": "p_cf_anim", "prefab": "p_cf_body_00", "head_bone": "p_cf_head_bone", "head_cat": 210, "default_head": 0},
    "male": {"skeleton": "p_cf_anim", "prefab": "p_cm_body_00", "head_bone": "p_cf_head_bone", "head_cat": 110, "default_head": 0},
}
# clothes slot order in a card's Coordinate block (female 240+i, male 140+i)
CLOTHES_SLOTS = ["top", "bot", "inner_t", "inner_b", "gloves", "panst", "socks", "shoes"]
HAIR_SLOTS = ["back", "front", "side", "option"]  # 300+i
ACCESSORY_NONE = 350


def game_root(arg=None):
    root = arg or os.environ.get("HS2_ROOT") or GAME_DEFAULT
    if not os.path.isdir(os.path.join(root, "abdata")):
        raise SystemExit("HoneySelect 2 not found at %s (pass --game or set HS2_ROOT)" % root)
    return root


def abdata_path(root, rel):
    return os.path.join(root, "abdata", rel.replace("/", os.sep))


def _text_bytes(text_asset):
    raw = text_asset.m_Script
    return raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else bytes(raw)


# ---------------------------------------------------------------- item lists

def _list_bundles(root):
    folder = os.path.join(root, "abdata", "list", "characustom")
    return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                  if f.endswith(".unity3d") and f != "namelist.unity3d")


def load_lists(root, cache_dir=None):
    """{categoryNo: {id: row}} merged over every distribution bundle (00, 02, ..., 60).

    A row is {column: value} plus "_dist" (the list bundle it came from).  Cached as JSON
    keyed by the list bundles' sizes and mtimes, so a second call costs ~50 ms.
    """
    import UnityPy

    bundles = _list_bundles(root)
    stamp = [[os.path.basename(p), os.path.getsize(p), int(os.path.getmtime(p))] for p in bundles]
    cache = os.path.join(cache_dir, "lists.json") if cache_dir else None
    if cache and os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("stamp") == stamp:
                return {int(c): {int(i): row for i, row in rows.items()} for c, rows in data["lists"].items()}
        except (OSError, ValueError):
            pass
    lists = {}
    for path in bundles:
        dist = os.path.splitext(os.path.basename(path))[0]
        env = UnityPy.load(path)
        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue
            try:
                data = hs2_msgpack.unpackb(_text_bytes(obj.read()))
            except Exception:
                continue
            if not isinstance(data, dict) or "categoryNo" not in data:
                continue
            cols = data["lstKey"]
            rows = lists.setdefault(int(data["categoryNo"]), {})
            for values in data["dictList"].values():
                row = dict(zip(cols, values))
                try:
                    item_id = int(row["ID"])
                except (KeyError, ValueError):
                    continue
                row["_dist"] = dist
                rows[item_id] = row
    if cache:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"stamp": stamp, "lists": lists}, f, ensure_ascii=False)
    return lists


def is_model_row(row):
    main = (row.get("MainData") or "").strip()
    return bool(main) and main not in ("0", "p_dummy") and bool((row.get("MainAB") or "").strip())


def display_name(row, lang="zh"):
    order = {"zh": ("ZH_CN", "Name", "EN_US"), "en": ("EN_US", "Name", "ZH_CN"), "ja": ("Name", "ZH_CN", "EN_US")}[lang]
    for key in order:
        value = (row.get(key) or "").strip()
        if value and value != "0":
            return value
    return ""


def model_items(lists, lang="zh"):
    """Every list row that is a real prefab, as flat dicts, in category/id order."""
    out = []
    for cat in sorted(MODEL_CATEGORIES):
        key, sex, group, label = MODEL_CATEGORIES[cat]
        for item_id, row in sorted(lists.get(cat, {}).items()):
            if not is_model_row(row):
                continue
            out.append({
                "ref": "%s:%d" % (key, item_id), "category": cat, "key": key, "id": item_id,
                "sex": sex, "group": group, "label": label,
                "name": display_name(row, lang), "name_ja": (row.get("Name") or "").strip(),
                "name_en": (row.get("EN_US") or "").strip(),
                "bundle": row["MainAB"], "prefab": row["MainData"], "dist": row["_dist"],
                "thumb": [row.get("ThumbAB") or "", row.get("ThumbTex") or ""],
                "parent": (row.get("Parent") or "").strip(),
            })
    return out


def parse_ref(text):
    """'fo_top:12' / '240:12' -> (category, id)."""
    key, _, item = text.partition(":")
    if not item:
        raise ValueError("item ref must look like fo_top:12 or 240:12, got %r" % text)
    cat = int(key) if key.isdigit() else KEY_TO_CATEGORY.get(key)
    if cat is None:
        raise ValueError("unknown category %r (known: %s)" % (key, ", ".join(sorted(KEY_TO_CATEGORY))))
    return cat, int(item)


# ---------------------------------------------------------------- bundle dependencies

def load_manifest_deps(root):
    """{bundle rel path: [dependency rel paths]} from every AssetBundleManifest in abdata/."""
    import UnityPy

    deps = {}
    folder = os.path.join(root, "abdata")
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or "." in name:
            continue
        try:
            env = UnityPy.load(path)
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != "AssetBundleManifest":
                continue
            tree = obj.read_typetree()
            names = {k: v for k, v in tree["AssetBundleNames"]}
            for k, info in tree["AssetBundleInfos"]:
                deps.setdefault(names[k], [names[d] for d in info["AssetBundleDependencies"]])
    return deps


# ---------------------------------------------------------------- character cards

def _read_7bit_string(f):
    n, shift = 0, 0
    while True:
        b = f.read(1)[0]
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
    return f.read(n).decode("utf-8")


def _length_prefixed(raw):
    f, out = io.BytesIO(raw), []
    while f.tell() < len(raw):
        n = struct.unpack("<i", f.read(4))[0]
        out.append(hs2_msgpack.unpackb(f.read(n)))
    return out


def read_card(path):
    """Parse an HS2/AIS character card (PNG + 【AIS_Chara】 block) into plain dicts."""
    data = open(path, "rb").read()
    end = data.find(b"IEND")
    if end < 0:
        raise ValueError("%s: not a PNG card" % path)
    f = io.BytesIO(data[end + 8:])
    product = struct.unpack("<i", f.read(4))[0]
    marker = _read_7bit_string(f)
    if "AIS_Chara" not in marker:
        raise ValueError("%s: not an HS2/AIS card (marker %r)" % (path, marker))
    version = _read_7bit_string(f)
    language = struct.unpack("<i", f.read(4))[0]
    _read_7bit_string(f)  # user id
    _read_7bit_string(f)  # data id
    header_len = struct.unpack("<i", f.read(4))[0]
    header = hs2_msgpack.unpackb(f.read(header_len))
    struct.unpack("<q", f.read(8))
    base = f.tell()
    blocks = {}
    for info in header["lstInfo"]:
        f.seek(base + info["pos"])
        blocks[info["name"]] = f.read(info["size"])
    face, body, hair = _length_prefixed(blocks["Custom"])
    coordinate = _length_prefixed(blocks["Coordinate"])
    clothes, accessory = coordinate[0], coordinate[1]
    parameter = hs2_msgpack.unpackb(blocks["Parameter"]) if "Parameter" in blocks else {}
    sex = "male" if parameter.get("sex", 1) == 0 else "female"
    return {
        "path": path, "product": product, "version": version, "language": language,
        "name": parameter.get("fullname", ""), "sex": sex, "parameter": parameter,
        "face": face, "body": body, "hair": hair, "clothes": clothes, "accessory": accessory,
    }


def card_parts(card):
    """The list refs a card wears: [(role, category, id, extra)]."""
    sex = card["sex"]
    parts = [("head", 210 if sex == "female" else 110, int(card["face"].get("headId", 0)), {})]
    for i, part in enumerate(card["hair"].get("parts", [])[:4]):
        parts.append(("hair_" + HAIR_SLOTS[i], 300 + i, int(part.get("id", 0)), {"hair": part}))
    base = 240 if sex == "female" else 140
    for i, part in enumerate(card["clothes"].get("parts", [])[:8]):
        cat = base + i
        if cat not in MODEL_CATEGORIES:
            continue
        parts.append(("clothes_" + CLOTHES_SLOTS[i], cat, int(part.get("id", 0)), {"clothes": part}))
    for i, part in enumerate(card["accessory"].get("parts", [])):
        cat = int(part.get("type", ACCESSORY_NONE))
        if cat == ACCESSORY_NONE or cat not in MODEL_CATEGORIES:
            continue
        parts.append(("acc_%02d" % i, cat, int(part.get("id", 0)), {"accessory": part}))
    return parts


def list_cards(root):
    out = []
    for sex in ("female", "male"):
        folder = os.path.join(root, "UserData", "chara", sex)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".png"):
                continue
            path = os.path.join(folder, name)
            try:
                card = read_card(path)
            except Exception as exc:  # noqa: BLE001 - list the broken card instead of dying
                out.append({"file": name, "path": path, "error": str(exc)})
                continue
            out.append({"file": name, "path": path, "name": card["name"], "sex": card["sex"],
                        "parts": card_parts(card)})
    return out
