"""List The First Descendant character models and their export status.

The First Descendant (Nexon, UE5, internal codename **M1**) ships one IoStore
container, ``M1-Windows.{utoc,ucas,pak}``, whose directory index is AES-encrypted
(pak v11, utoc v5, Oodle).  This reads every path out of the ``.utoc`` index (the
key is needed - see ``--aes-key`` / ``--aes-key-file`` / ``TFD_AES_KEY``; the key
never lives in the repo), groups the skeletal meshes into "models" the way the
game composes characters, and diffs them against ``<export-root>``.

The .utoc index only stores paths (no asset classes), so a part is a skeletal
mesh identified by its folder + name convention:

  descendant  Characters/PC/MESH/PRESET/<Name>/PC_<NNN>_<A|U>0101   one merged mesh
              (body+head+hair) - the default look; <NNN> maps to a name via the
              PRESET folder, A = standard, U = Ultimate.
  skin        Characters/PC/MESH/<NNN>/<A|U>/Skel/SKIN/<CAT>/<n>/..._(BODY|HEAD)_<n>
              an alternate outfit (a BODY + HEAD pair) + the character's Face.
  monster     Characters/Monster/(CMN|UNQ)/<id>/A001/MESH/Skel/MOB_...
  boss        Characters/Boss/<id>/<variant>/MESH/Skel/BOS_...
  npc         Characters/NPC/<id>/MESH/Skel/...
  weapon      Characters/Weapon/(RW|MW)/<type>/<id>/Skel/...
  accessory   Characters/ACC/<slot>/<id>/MESH/[Skel/]PC_ACC_...
  fellow      Characters/Fellow/DOG/MESH/<id>/Skel/FLW_DOG_...
  vehicle     Characters/Vehicle/HBK/MESH/<id>/Skel/VEH_HBK_...

Examples:
  python list_models.py                          # table with umodel / blend status
  python list_models.py --kind descendant        # one kind
  python list_models.py --char Bunny             # every model of one descendant
  python list_models.py --resolve Bunny --json   # one model: umodel packages + PSK paths
  python list_models.py --raw --path-filter /Monster/UNQ/

The utoc decryptor is the same one written for scripts/vindictus (both are Nexon
UE5 IoStore titles).
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

DEFAULT_GAME_ROOT = r"E:\SteamLibrary\steamapps\common\The First Descendant"
DEFAULT_EXPORT_ROOT = r"D:\tfd_exports"
DEFAULT_KEY_FILE = r"D:\tfd_exports\_keys\aes_key.txt"
CONTENT_PREFIX = "M1/Content/"
CHARACTERS = "M1/Content/Characters/"

MODEL_EXTENSIONS = (".psk", ".pskx")
# filename stems that are never a renderable mesh
NON_MESH_RE = re.compile(
    r"(_Skeleton|_Physics|_PhysicsAsset|_PHYS|ClothPhysics|PoseAsset|_MI|_LOD"
    r"|MorphData|_C|_N|_P|_ID|_E|_FX|_M|_A_C|_A_N)$", re.IGNORECASE)
TEXTURE_SUFFIX_RE = re.compile(r"_(C|N|P|ID|E|FX|M|MK|AO|RA|ORM|D)$", re.IGNORECASE)


# ---------------------------------------------------------------- utoc index
def read_key(args) -> bytes:
    key = args.aes_key or os.environ.get("TFD_AES_KEY", "")
    if not key and args.aes_key_file and os.path.isfile(args.aes_key_file):
        key = open(args.aes_key_file, encoding="utf-8").read().strip()
    key = key.strip()
    if key.lower().startswith("0x"):
        key = key[2:]
    if len(key) != 64:
        raise SystemExit("AES key missing or not 32 bytes: pass --aes-key / --aes-key-file or set TFD_AES_KEY "
                         "(recover it with find_aes_key.py)")
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
        if flags & 0x4:                       # signed
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
def content_relative(path: str) -> str:
    """'M1/Content/Characters/...uasset' -> 'Characters/...' = the umodel package path
    and the folder layout UE Viewer uses under -out."""
    rel = path[len(CONTENT_PREFIX):] if path.startswith(CONTENT_PREFIX) else path
    return os.path.splitext(rel)[0]


def stem_of(path: str) -> str:
    return os.path.basename(path)[:-7]  # strip .uasset


def is_meshy(path: str) -> bool:
    if not path.lower().endswith(".uasset"):
        return False
    for junk in ("/Material/", "/Texture/", "/Textuer/", "/Anim/", "/BP/", "/AnimBP/"):
        if junk in path:
            return False
    if "/Skel/" not in path and "/MESH/" not in path and "/Mesh/" not in path:
        return False
    stem = stem_of(path)
    if stem.startswith(("BP_", "ABP_", "CIN_")) or stem.endswith(("_AnimBP", "_AimOffset")):
        return False
    return not NON_MESH_RE.search(stem) and not TEXTURE_SUFFIX_RE.search(stem)


def part(path, name, kind):
    return {"name": name, "kind": kind, "package": content_relative(path)}


def build_catalogue(paths: list[str]) -> list[dict]:
    ch = [p for p in paths if p.startswith(CHARACTERS) and is_meshy(p)]
    models: list[dict] = []

    # -- descendant number -> name(s) from PRESET folders (A standard, U ultimate)
    num_name = {}          # (number, variant) -> descendant name
    presets = {}           # descendant name -> preset package path
    for p in ch:
        m = re.search(r"/PC/MESH/PRESET/([^/]+)/PC_(\d{3})_([AU])0101$", content_relative(p) + "")
        m = re.search(r"/PC/MESH/PRESET/([^/]+)/PC_(\d{3})_([AU])\d+$", p[:-7])
        if m:
            name, num, var = m.group(1), m.group(2), m.group(3)
            num_name[(num, var)] = name
            presets[name] = p

    def face_of(num, var):
        # PC/MESH/<num>/<var>/Skel/Face/PC_<num>_<var>_Face_000
        cand = [p for p in ch if re.search(r"/PC/MESH/%s/%s/Skel/Face/PC_%s_%s_Face_000$" % (num, var, num, var), p[:-7])]
        return part(cand[0], "Face", "face") if cand else None

    # -- descendants (default look = the PRESET merged mesh)
    for name in sorted(presets):
        m = re.search(r"PC_(\d{3})_([AU])", stem_of(presets[name]))
        num, var = m.group(1), m.group(2)
        models.append({"id": name, "kind": "descendant", "char": name, "number": num, "variant": var,
                       "parts": [part(presets[name], "Full", "full")], "extras": []})

    # -- descendant skins: SKIN/<CAT>/<n>/..._(BODY|HEAD)_<n>
    skins: dict[tuple, dict] = defaultdict(lambda: {"body": None, "head": None})
    for p in ch:
        m = re.search(r"/PC/MESH/(\d{3})/([AU])/Skel/SKIN/([A-Za-z]+)/([^/]+)/PC_\d{3}_[AU]_[A-Za-z]+_(BODY|HEAD)_", p)
        if not m:
            continue
        num, var, cat, sub, which = m.groups()
        if cat.lower() == "makeup" or "_EVT_" in p:
            continue                       # makeup = material-only; events are situational
        skins[(num, var, cat, sub)][which.lower()] = p
    for (num, var, cat, sub), bh in sorted(skins.items()):
        if not bh["body"]:
            continue
        cname = num_name.get((num, var), "PC%s_%s" % (num, var))
        parts = [part(bh["body"], "Body", "body")]
        if bh["head"]:
            parts.append(part(bh["head"], "Head", "head"))
        face = face_of(num, var)
        if face:
            parts.append(face)
        sid = re.sub(r"\.uasset$", "", sub)
        models.append({"id": "%s_%s_%s" % (cname, cat, sid), "kind": "skin", "char": cname,
                       "number": num, "variant": var, "parts": parts, "extras": []})

    # -- monsters, bosses, npcs, weapons, accessories, fellows, vehicles:
    # one model per main mesh (its stem = the id, so A001/B001 variants stay
    # separate), with any sibling Parts/Separate_Parts meshes as extras.
    def collect(tree_re, kind):
        seen_ids = set()
        mains = [p for p in ch if re.search(tree_re, p)
                 and "/Parts/" not in p and "/Separate_Parts/" not in p]
        for mp in sorted(mains):
            stem = stem_of(mp)
            if stem in seen_ids:
                continue
            seen_ids.add(stem)
            unit = mp.rsplit("/Skel/", 1)[0] if "/Skel/" in mp else os.path.dirname(mp)
            extras = [q for q in sorted(ch)
                      if q.startswith(unit + "/") and ("/Parts/" in q or "/Separate_Parts/" in q)]
            models.append({"id": stem, "kind": kind, "char": "", "number": "", "variant": "",
                           "parts": [part(mp, stem, kind)],
                           "extras": [part(q, stem_of(q), "parts") for q in extras]})

    collect(r"/Monster/(CMN|UNQ|MIN)/", "monster")
    collect(r"/Boss/\d+/", "boss")
    collect(r"/NPC/\d+/MESH/", "npc")
    collect(r"/Weapon/(RW|MW)/", "weapon")
    collect(r"/ACC/[^/]+/[^/]+/MESH/", "accessory")
    collect(r"/Fellow/[^/]+/MESH/", "fellow")
    collect(r"/Vehicle/[^/]+/MESH/", "vehicle")
    return models


# ---------------------------------------------------------------- export status
def find_psk(export_root: str, package: str) -> str:
    """The CUE4Parse export (cue4_exports/M1/Content/<package>.pskx: real material slot
    names + morph targets) wins over an older UE Viewer export of the same package."""
    rel = package.replace("/", os.sep)
    for base in (os.path.join(export_root, "cue4_exports", "M1", "Content", rel),
                 os.path.join(export_root, "umodel_exports", rel)):
        for ext in MODEL_EXTENSIONS:
            if os.path.isfile(base + ext):
                return base + ext
    return ""


def annotate(models: list[dict], export_root: str) -> None:
    for model in models:
        for x in model["parts"] + model["extras"]:
            x["psk"] = find_psk(export_root, x["package"])
            x["exported"] = bool(x["psk"])
        model["out_dir"] = os.path.join(export_root, "blend", model["id"])
        model["blend"] = os.path.join(model["out_dir"], model["id"] + ".blend")
        model["blend_exists"] = os.path.isfile(model["blend"])
        model["exported_parts"] = sum(1 for x in model["parts"] if x["exported"])


def print_table(models: list[dict]) -> None:
    print("%-38s %-11s %-10s %5s %6s %s" % ("model", "kind", "char", "parts", "umodel", "blend"))
    for m in models:
        status = "%d/%d" % (m["exported_parts"], len(m["parts"]))
        print("%-38s %-11s %-10s %5d %6s %s"
              % (m["id"][:38], m["kind"], m["char"][:10], len(m["parts"]), status,
                 "yes" if m["blend_exists"] else "-"))
    kinds = defaultdict(int)
    for m in models:
        kinds[m["kind"]] += 1
    print("%d models (%s)" % (len(models), ", ".join("%s %d" % (k, kinds[k]) for k in sorted(kinds))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-root", default=DEFAULT_GAME_ROOT)
    ap.add_argument("--paks", default="", help="Paks folder (default <game-root>/M1/Content/Paks)")
    ap.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    ap.add_argument("--aes-key", default="")
    ap.add_argument("--aes-key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--kind", default="", help="descendant|skin|monster|boss|npc|weapon|accessory|fellow|vehicle")
    ap.add_argument("--char", default="", help="filter to one descendant (e.g. Bunny)")
    ap.add_argument("--resolve", default="", help="print one model (parts, umodel packages, PSK paths)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true", help="print every path in the container instead")
    ap.add_argument("--path-filter", default="", help="substring filter for --raw")
    args = ap.parse_args()

    paks = args.paks or os.path.join(args.game_root, "M1", "Content", "Paks")
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
    annotate(models, args.export_root)
    if args.resolve:
        wanted = args.resolve.lower()
        hit = next((m for m in models if m["id"].lower() == wanted), None)
        if hit is None:
            near = [m["id"] for m in models if wanted in m["id"].lower()]
            raise SystemExit("unknown model %r%s" % (args.resolve, (" (did you mean: %s)" % ", ".join(near[:10])) if near else ""))
        print(json.dumps(hit, ensure_ascii=False, indent=1))
        return 0
    if args.kind:
        models = [m for m in models if m["kind"] == args.kind]
    if args.char:
        models = [m for m in models if m["char"].lower() == args.char.lower()]
    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=1))
    else:
        print_table(models)
    return 0


if __name__ == "__main__":
    sys.exit(main())
