"""List Vindictus: Defying Fate character models and their export status.

Reads the IoStore directory index out of every ``*.utoc`` under the game's Paks folder (the index is
AES-encrypted in this game, so the pak key is needed — see ``--aes-key`` / ``--aes-key-file`` /
``VINDICTUS_AES_KEY``; the key itself never lives in the repo), groups the skeletal meshes into
"models" the way the game composes characters, and diffs them against ``<export-root>``:

  player   Character/Player/<Name>/         face + hair + armor master meshes (Fiona, Lethita)
  outfit   Character/Outfit/PC{F,M}_Outfit/  outfit parts + the face/hair of the matching player body
  base     BaseBody_PCM parts / SK_female_base + face/hair (nude base bodies)
  monster  Character/AI/<Race>/<Type>/<Variant>/Model/
  npc      Character/Npc/**

The .utoc index only stores paths (no asset classes), so a part is "anything named SK_* under a
Model/ folder that is not a Skeleton / Physics asset".

Examples:
  python list_models.py                       # table with umodel / blend status
  python list_models.py --json                # same, as JSON
  python list_models.py --resolve Fiona --json   # one model: umodel package paths + expected PSK files
  python list_models.py --raw --path-filter /Character/Player/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from collections import defaultdict

TOC_MAGIC = b"-==--==--==--==-"
NONE_ENTRY = 0xFFFFFFFF

DEFAULT_GAME_ROOT = r"E:\tools\vindictus"
DEFAULT_EXPORT_ROOT = r"D:\vindictus_exports"
DEFAULT_KEY_FILE = r"E:\tools\vindictus\_download\aes_key.txt"
CONTENT_PREFIX = "Vindictus/Content/"
CHARACTER_PREFIX = "VindictusRoot/Character/"

# Which player character's face/hair completes an outfit of a given body type (verified through the
# skeletons UE Viewer loads: Fiona -> SK_PCF_BaseBody01_Skeleton, Lethita -> SK_PCM_BaseBody01_Skeleton).
FACE_FOR_BODY = {"PCF": "Fiona", "PCM": "Lethita"}
# Outfits whose "Head" part replaces the hair (a helmet that encloses the head); the default hair is kept in
# the .blend but hidden.  Head parts that carry a hair material (PCF_001_Temp / PCF_008 / PCF_010 bundle
# Fiona's hair, Lethita's helmet has a hair plume) are detected by build_blend.py itself; the rest are
# chokers, headphones, hats, hair bands, tiaras (PCF_005) or caps that sit on the hair.
HEAD_REPLACES_HAIR = {"PCF_067"}
NOT_PLAYERS = {"BaseBody_PCF", "BaseBody_PCM", "Common", "Outfit"}
NON_MESH_SUFFIXES = ("_skeleton", "_physics", "_physicsasset", "_phys")
MODEL_EXTENSIONS = (".psk", ".pskx")


# ---------------------------------------------------------------- utoc directory index
def read_key(args) -> bytes:
    key = args.aes_key or os.environ.get("VINDICTUS_AES_KEY", "")
    if not key and args.aes_key_file and os.path.isfile(args.aes_key_file):
        key = open(args.aes_key_file, encoding="utf-8").read().strip()
    key = key.strip()
    if key.lower().startswith("0x"):
        key = key[2:]
    if len(key) != 64:
        raise SystemExit("AES key missing or not 32 bytes: pass --aes-key / --aes-key-file or set VINDICTUS_AES_KEY")
    return bytes.fromhex(key)


def aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(data)


def read_fstring(buf: bytes, pos: int):
    (length,) = struct.unpack_from("<i", buf, pos)
    pos += 4
    if length == 0:
        return "", pos
    if length < 0:
        raw = buf[pos:pos - length * 2]
        return raw.decode("utf-16-le").rstrip("\x00"), pos - length * 2
    return buf[pos:pos + length].decode("utf-8", errors="replace").rstrip("\x00"), pos + length


def parse_utoc_paths(utoc_path: str, key: bytes | None) -> list[str]:
    """Every file path recorded in one .utoc directory index (mount point stripped of ../../../)."""
    with open(utoc_path, "rb") as fh:
        header = fh.read(144)
        if len(header) < 144 or header[:16] != TOC_MAGIC:
            raise ValueError("not an IoStore TOC: %s" % utoc_path)
        version = header[16]
        (toc_header_size, entry_count, block_count, _block_entry_size, method_count, method_length,
         _block_size, dir_index_size, _partitions) = struct.unpack_from("<9I", header, 20)
        flags = header[80]
        (seed_count,) = struct.unpack_from("<I", header, 84)
        (no_hash_count,) = struct.unpack_from("<I", header, 96)
        if dir_index_size == 0:
            return []
        offset = toc_header_size + entry_count * 12 + entry_count * 10
        if version >= 4:
            offset += seed_count * 4
        if version >= 5:
            offset += no_hash_count * 4
        offset += block_count * 12 + method_count * method_length
        if flags & 0x4:                       # signed: hash size + two hashes + one per block
            fh.seek(offset)
            (hash_size,) = struct.unpack_from("<i", fh.read(4))
            offset += 4 + hash_size * 2 + block_count * 20
        fh.seek(offset)
        index = fh.read(dir_index_size)
    if flags & 0x2:                           # encrypted
        if key is None:
            raise ValueError("directory index is AES-encrypted: %s" % utoc_path)
        index = aes_ecb_decrypt(key, index)

    mount, pos = read_fstring(index, 0)
    (dir_count,) = struct.unpack_from("<I", index, pos)
    pos += 4
    dirs = [struct.unpack_from("<4I", index, pos + 16 * i) for i in range(dir_count)]
    pos += 16 * dir_count
    (file_count,) = struct.unpack_from("<I", index, pos)
    pos += 4
    files = [struct.unpack_from("<3I", index, pos + 12 * i) for i in range(file_count)]
    pos += 12 * file_count
    (string_count,) = struct.unpack_from("<I", index, pos)
    pos += 4
    strings = []
    for _ in range(string_count):
        s, pos = read_fstring(index, pos)
        strings.append(s)

    mount = mount.replace("\\", "/")
    while mount.startswith("../"):
        mount = mount[3:]
    paths: list[str] = []
    stack = [(0, mount.rstrip("/"))]
    while stack:
        entry, prefix = stack.pop()
        name, first_child, _sibling, first_file = dirs[entry]
        path = prefix if name == NONE_ENTRY else (prefix + "/" + strings[name] if prefix else strings[name])
        f = first_file
        while f != NONE_ENTRY:
            fname, next_file, _user = files[f]
            paths.append((path + "/" + strings[fname]) if path else strings[fname])
            f = next_file
        c = first_child
        while c != NONE_ENTRY:
            stack.append((c, path))
            c = dirs[c][2]
    return paths


def all_paths(paks_dir: str, key: bytes | None) -> list[str]:
    utocs = sorted(f for f in os.listdir(paks_dir) if f.lower().endswith(".utoc"))
    if not utocs:
        raise SystemExit("no .utoc under " + paks_dir)
    out: list[str] = []
    for name in utocs:
        out.extend(parse_utoc_paths(os.path.join(paks_dir, name), key))
    return sorted(set(out))


# ---------------------------------------------------------------- catalogue
def is_mesh_asset(path: str) -> bool:
    stem = os.path.basename(path)
    if not stem.lower().endswith(".uasset"):
        return False
    low = stem[:-7].lower()
    # Fiona's nude body is a SkeletalMesh misnamed SM_pc_fiona_basebody (SK_female_base next to it is a Skeleton)
    if stem.startswith("SM_") and "basebody" in low and "/Model/Mesh/" in path:
        return True
    if not stem.startswith("SK_"):
        return False
    return not low.endswith(NON_MESH_SUFFIXES) and not low.endswith("_base")


def content_relative(path: str) -> str:
    """'Vindictus/Content/VindictusRoot/...uasset' -> 'VindictusRoot/...' (no extension) = umodel package path
    and also the folder layout UE Viewer uses under -out."""
    rel = path[len(CONTENT_PREFIX):] if path.startswith(CONTENT_PREFIX) else path
    return os.path.splitext(rel)[0]


def part_name(stem: str, prefix: str) -> str:
    name = stem[len(prefix):] if stem.startswith(prefix) else stem
    name = re.sub(r"_master$", "", name, flags=re.I)
    name = re.sub(r"01$", "", name)
    return name.strip("_") or "Body"


def build_catalogue(paths: list[str]) -> list[dict]:
    chars = [p for p in paths if p.startswith(CONTENT_PREFIX + CHARACTER_PREFIX) and is_mesh_asset(p)]
    players: dict[str, dict] = {}
    models: list[dict] = []

    def part(path, name, kind):
        return {"name": name, "kind": kind, "package": content_relative(path)}

    # players: Character/Player/<Name>/{Face,Armor,Weapon}/Model/SK_*
    by_player: dict[str, list[str]] = defaultdict(list)
    for p in chars:
        rel = p[len(CONTENT_PREFIX + CHARACTER_PREFIX):]
        segs = rel.split("/")
        if segs[0] == "Player" and len(segs) > 2 and segs[1] not in NOT_PLAYERS:
            by_player[segs[1]].append(p)
    for name in sorted(by_player):
        parts, extras = [], []
        for p in sorted(by_player[name]):
            rel = p[len(CONTENT_PREFIX + CHARACTER_PREFIX):]
            stem = os.path.basename(p)[:-7]
            if "/Face/Model/" in rel and stem.startswith("SK_%s_Face" % name):
                parts.append(part(p, "Face", "face"))
            elif "/Face/Model/" in rel and stem.startswith("SK_%s_Hair" % name):
                parts.append(part(p, "Hair", "hair"))
            elif "/Armor/Model/" in rel:
                parts.append(part(p, part_name(stem, "SK_%s_" % name), "armor"))
            elif "/Weapon/" in rel:
                extras.append(part(p, part_name(stem, "SK_"), "weapon"))
            elif "/Model/Mesh/" in rel and "basebody" in stem.lower():
                extras.append(part(p, "BaseBody", "base"))
        if parts:
            body = next((b for b, owner in FACE_FOR_BODY.items() if owner == name), "PCF")
            model = {"id": name, "kind": "player", "body": body, "parts": parts, "extras": extras}
            players[name] = model
            models.append(model)

    def face_hair(body):
        owner = players.get(FACE_FOR_BODY.get(body, ""))
        return [dict(x) for x in owner["parts"] if x["kind"] in ("face", "hair")] if owner else []

    # nude base bodies
    for name, model in players.items():
        base = [x for x in model["extras"] if x["kind"] == "base"]
        if base:
            models.append({"id": name + "_BaseBody", "kind": "base", "body": model["body"],
                           "parts": face_hair(model["body"]) + base, "extras": []})
    pcm_base = [p for p in chars if "/Player/BaseBody_PCM/Model/" in p and re.search(r"SK_PCM_(Upper|Lower|Hand|Foot)", p)]
    if pcm_base:
        models.append({"id": "PCM_BaseBody", "kind": "base", "body": "PCM",
                       "parts": face_hair("PCM") + [part(p, part_name(os.path.basename(p)[:-7], "SK_PCM_"), "body") for p in sorted(pcm_base)],
                       "extras": []})

    # outfits: Character/Outfit/PC{F,M}_Outfit/<Id>/Model/SK_*
    by_outfit: dict[str, list[str]] = defaultdict(list)
    for p in chars:
        m = re.search(r"/Character/Outfit/(PC[FM])_Outfit/([^/]+)/Model/SK_", p)
        if m:
            by_outfit[m.group(2)].append(p)
    for oid in sorted(by_outfit):
        body = "PCM" if oid.startswith("PCM") else "PCF"
        paths = sorted(by_outfit[oid])
        if len(paths) > 1:
            # PCM_001_Temp also ships SK_PCM_001_Temp, the whole set merged into one mesh (face and hair included)
            paths = [p for p in paths if os.path.basename(p)[:-7].lower() != ("sk_" + oid).lower()]
        own = [part(p, part_name(os.path.basename(p)[:-7], "SK_%s_" % oid), "outfit") for p in paths]
        models.append({"id": oid, "kind": "outfit", "body": body, "parts": face_hair(body) + own, "extras": []})

    # older outfit sets kept under Character/Player/Outfit/<Name>/Mesh/SK_PC_<female|male>_<Name>_<Part>
    by_legacy: dict[str, list[str]] = defaultdict(list)
    for p in chars:
        m = re.search(r"/Character/Player/Outfit/([^/]+)/Mesh/SK_", p)
        if m:
            by_legacy[m.group(1)].append(p)
    for name in sorted(by_legacy):
        stems = [os.path.basename(p)[:-7] for p in by_legacy[name]]
        body = "PCM" if any("_male_" in s.lower() for s in stems) and not any("_female_" in s.lower() for s in stems) else "PCF"
        own = []
        for p, stem in zip(sorted(by_legacy[name]), sorted(stems)):
            tail = re.split(re.escape(name) + "_", stem, maxsplit=1, flags=re.I)
            own.append(part(p, (tail[1] if len(tail) > 1 else stem[3:]).capitalize(), "outfit"))
        # these sets are rigged to the old 3ds Max Biped skeleton (Bip001_*); the current face skeleton still
        # carries those bones (a few cm off), so build_blend.py re-poses the parts onto it and the face fits
        models.append({"id": name + "_legacy", "kind": "outfit", "body": body, "parts": face_hair(body) + own, "extras": []})

    # monsters: Character/AI/<Race>/<Type>/<Variant>/Model/SK_*
    by_mob: dict[str, list[str]] = defaultdict(list)
    for p in chars:
        m = re.search(r"/Character/AI/([^/]+)/([^/]+)/([^/]+)/Model/SK_", p)
        if m:
            by_mob["%s_%s_%s" % m.groups()].append(p)
    for mid in sorted(by_mob):
        parts = [part(p, part_name(os.path.basename(p)[:-7], "SK_"), "weapon" if "weapon" in p.lower() else "body")
                 for p in sorted(by_mob[mid])]
        models.append({"id": mid, "kind": "monster", "body": "", "parts": parts, "extras": []})

    # NPCs: Character/Npc/**/SK_*
    for p in sorted(x for x in chars if "/Character/Npc/" in x):
        stem = os.path.basename(p)[:-7]
        models.append({"id": part_name(stem, "SK_"), "kind": "npc", "body": "", "parts": [part(p, "Body", "body")], "extras": []})
    return models


# ---------------------------------------------------------------- export status
def find_psk(export_root: str, package: str) -> str:
    base = os.path.join(export_root, "umodel_exports", package.replace("/", os.sep))
    for ext in MODEL_EXTENSIONS:
        if os.path.isfile(base + ext):
            return base + ext
    return ""


def annotate(models: list[dict], export_root: str, include_weapons: bool) -> None:
    for model in models:
        if include_weapons:
            model["parts"] = model["parts"] + [x for x in model["extras"] if x["kind"] == "weapon"]
        for x in model["parts"] + model["extras"]:
            x["psk"] = find_psk(export_root, x["package"])
            x["exported"] = bool(x["psk"])
        model["hide_hair"] = model["id"] in HEAD_REPLACES_HAIR
        model["out_dir"] = os.path.join(export_root, "blend", model["id"])
        model["blend"] = os.path.join(model["out_dir"], model["id"] + ".blend")
        model["blend_exists"] = os.path.isfile(model["blend"])
        model["exported_parts"] = sum(1 for x in model["parts"] if x["exported"])


def print_table(models: list[dict]) -> None:
    print("%-34s %-8s %-4s %5s %6s %s" % ("model", "kind", "body", "parts", "umodel", "blend"))
    for m in models:
        status = "%d/%d" % (m["exported_parts"], len(m["parts"]))
        print("%-34s %-8s %-4s %5d %6s %s" % (m["id"], m["kind"], m["body"], len(m["parts"]), status, "yes" if m["blend_exists"] else "-"))
    print("%d models" % len(models))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-root", default=DEFAULT_GAME_ROOT)
    ap.add_argument("--paks", default="", help="Paks folder (default <game-root>/Vindictus/Content/Paks)")
    ap.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    ap.add_argument("--aes-key", default="", help="0x... (or set VINDICTUS_AES_KEY)")
    ap.add_argument("--aes-key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--kind", default="", help="player|outfit|base|monster|npc")
    ap.add_argument("--resolve", default="", help="print one model (parts, umodel packages, PSK paths)")
    ap.add_argument("--include-weapons", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true", help="print every path in the containers instead")
    ap.add_argument("--path-filter", default="", help="substring filter for --raw")
    args = ap.parse_args()

    paks = args.paks or os.path.join(args.game_root, "Vindictus", "Content", "Paks")
    if not os.path.isdir(paks):
        raise SystemExit("Paks folder not found: " + paks)
    key = read_key(args)
    paths = all_paths(paks, key)

    if args.raw:
        for p in paths:
            if not args.path_filter or args.path_filter.lower() in p.lower():
                print(p)
        return 0

    models = build_catalogue(paths)
    annotate(models, args.export_root, args.include_weapons)
    if args.resolve:
        wanted = args.resolve.lower()
        hit = next((m for m in models if m["id"].lower() == wanted), None)
        if hit is None:
            candidates = [m["id"] for m in models if wanted in m["id"].lower()]
            raise SystemExit("unknown model %r%s" % (args.resolve, (" (did you mean: %s)" % ", ".join(candidates[:8])) if candidates else ""))
        print(json.dumps(hit, ensure_ascii=False, indent=1))
        return 0
    if args.kind:
        models = [m for m in models if m["kind"] == args.kind]
    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=1))
    else:
        print_table(models)
    return 0


if __name__ == "__main__":
    sys.exit(main())
