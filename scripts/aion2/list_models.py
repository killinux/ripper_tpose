"""List the AION2 models (counts by kind) and the parts each exportable model is built from.

Step 1 (``--scan``, ~1 min with 6 workers): read the package header of every ``.uasset`` in the game
(480k) and record the class of its asset (``SkeletalMesh``, ``StaticMesh``, ``Texture2D`` ...) in
``<export-root>\\_meta\\aion2_classes.json``.  The cache is keyed by the containers' sizes and dates, so a
game update triggers a rescan; without ``--scan`` an existing cache is used as is.

Step 2: group the meshes into models the way the game composes characters:

  outfit      Character/Player/<GF|GM>/Armor/<NNNN>/<G>_<NNNN>_<Txx>/   a numbered armour set: Body, Pants,
              Glove, Boots, Helmet, Shoulder, Cape; exported with a head + hair (defaults <G>_Head_001 /
              <G>_Hair_001, --head / --hair) and the base body for a missing Body / Pants slot
  costume     .../Armor/Special/<set>/          fashion sets (angel, maid, qipao, swimsuits ...), same parts
  hat         .../Armor/Helmet/<set>/           hats and masks (one or two meshes)
  polymorph   .../Armor/Polymorph/<set>/        transformation suits
  outfit_common .../Armor/Common*/              skirts and hair bands shared by many sets
  base        .../Basebody/<G>_Base*            the base body parts (default top + skirt, legs, shoes, head)
  head, hair  .../Head|Hair/...                 character-creation options; a hairstyle's _Type1/_Type2
                                                meshes (the versions worn under hats) belong to it
  acc, beard  .../ACC|Beard/...
  weapon      Character/Player/Weapon/<type>/<id>/     one model per folder (an off-hand pair = one model)
  wing, shoulderwear, headwear                  one model per mesh
  npc         Character/NPC/<type>/<name>/<id>/ one model per folder (Body, Head, Hair, Pants ... of one NPC)
  monster, monster_starter, veh, etc            one model per skeletal mesh
  other_skeletal                                skeletal meshes outside Character/ (cut scenes, quest props)

GF = female player, GM = male player (the game's gender codes).  StaticMeshes are counted, not grouped.

Examples:
  python list_models.py --scan                 # build / refresh the class cache, print the summary
  python list_models.py                        # summary table (counts by kind and gender)
  python list_models.py --kind outfit --gender GF        # every female armour set
  python list_models.py --resolve GF_0001_T04 --json     # parts + umodel package paths of one model
  python list_models.py --raw --path-filter /Monster/Boss/ --class SkeletalMesh
  python list_models.py --find yustiel leda siel          # find models by name (* ? wildcards too)
  python list_models.py --women --kind npc                # NPCs judged female (see model_genders)
  python list_models.py --catalogue                       # every model -> _meta\\aion2_models.json (the gallery reads it)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aion2_pak as pak  # noqa: E402

DEFAULT_EXPORT_ROOT = r"E:\aion2_exports"
CONTENT = "AION2/Content/"
CHAR = CONTENT + "Character/"
DEFAULT_HEAD = {"GF": "GF_Head_001", "GM": "GM_Head_001"}
DEFAULT_HAIR = {"GF": "GF_Hair_001", "GM": "GM_Hair_001"}


# ---------------------------------------------------------------- class cache
def _signature(game: pak.Game) -> list:
    return sorted([os.path.basename(t.utoc), os.path.getsize(t.ucas), int(os.path.getmtime(t.utoc))] for t in game.tocs)


_worker_game = None


def _worker_init(root, key_hex, oodle):
    global _worker_game
    _worker_game = pak.Game(root, bytes.fromhex(key_hex), oodle)


def _worker_scan(paths):
    out = {}
    for p in paths:
        try:
            out[p] = pak.main_class(_worker_game, _worker_game.header(p), p)
        except Exception as e:  # keep going, report later
            out[p] = "!error " + repr(e)[:80]
    return out


def scan_classes(game: pak.Game, key: bytes, oodle: str, cache_file: str, workers: int, limit: int = 0) -> dict:
    paths = sorted(p for p in game.index if p.endswith(".uasset"))
    if limit:
        paths = paths[:limit]
    chunks = [paths[i:i + 2000] for i in range(0, len(paths), 2000)]
    t0 = time.time()
    classes = {}
    with Pool(workers, initializer=_worker_init, initargs=(game.root, key.hex(), oodle)) as pool:
        for i, part in enumerate(pool.imap_unordered(_worker_scan, chunks), 1):
            classes.update(part)
            if i % 20 == 0 or i == len(chunks):
                done = len(classes)
                rate = done / max(time.time() - t0, 1e-6)
                print("  %d/%d packages, %.0f/s, %.0f s left" % (done, len(paths), rate, (len(paths) - done) / rate),
                      flush=True)
    if not limit:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump({"signature": _signature(game), "classes": classes}, fh)
    return classes


def load_classes(game: pak.Game, cache_file: str):
    if not os.path.isfile(cache_file):
        return None
    with open(cache_file, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("signature") != _signature(game):
        print("class cache is from another game version - run with --scan", file=sys.stderr)
    return data["classes"]


# ---------------------------------------------------------------- grouping
def stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def pkg(path: str) -> str:
    """umodel package name: AION2/Content/X/Y.uasset -> AION2/X/Y"""
    p = path[:-len(".uasset")] if path.endswith(".uasset") else path
    return p.replace("AION2/Content/", "AION2/", 1)


ARMOR_KINDS = {"Special": "costume", "Helmet": "hat", "Polymorph": "polymorph", "RVR": "outfit",
               "Common": "outfit_common", "Common_Global": "outfit_common"}
TYPE_RE = re.compile(r"_Type\d+$")


def kind_of(path: str):
    """(kind, gender, model id) for a SkeletalMesh path.  Meshes with the same id form one model."""
    rel = path[len(CHAR):] if path.startswith(CHAR) else None
    s = stem(path)
    if rel is None:
        return ("other_skeletal", "", s)
    parts = rel.split("/")
    if "/Test/" in path or s.startswith(("Test_", "test_")) or "/TestVEH/" in path or "/TestDummy/" in path:
        return ("test", "", s)
    top = parts[0]
    if top == "Player" and len(parts) > 2 and parts[1] in ("GF", "GM"):
        g, sub = parts[1], parts[2]
        if sub == "Armor" and len(parts) >= 5:
            cat = parts[3]
            kind = "outfit" if cat.isdigit() else ARMOR_KINDS.get(cat, "outfit")
            return (kind, g, parts[4] if len(parts) >= 6 else s)        # set folder (GF_0001_T04, GF_Angel_01)
        if sub == "Basebody":
            return ("base", g, s)
        if sub == "Head":
            return ("head", g, s)
        if sub == "Hair":
            return ("hair", g, TYPE_RE.sub("", s))                        # _Type1/_Type2 = versions under hats
        if sub == "ACC":
            return ("acc", g, s)
        if sub == "Beard":
            return ("beard", g, s)
        return ("player_misc", g, s)
    if top == "Player":
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "Weapon":
            return ("weapon", "", os.path.basename(os.path.dirname(path)))   # OR_0000_T01 = its _L + _R
        return ({"Wing": "wing", "ShoulderWear": "shoulderwear", "HeadWear": "headwear"}.get(sub, "player_misc"), "", s)
    if top == "NPC":
        return ("npc", "", "NPC_" + os.path.basename(os.path.dirname(path)))   # Body, Head, Hair, Pants ... of one NPC
    if top in ("Monster", "MonsterStarter", "VEH", "ETC"):
        kind = {"Monster": "monster", "MonsterStarter": "monster_starter", "VEH": "veh", "ETC": "etc"}[top]
        return (kind, "", s)
    return ("other_skeletal", "", s)


def build_models(classes: dict) -> dict:
    """model id -> {kind, gender, parts: [paths], folder}"""
    models = {}
    for path, cls in sorted(classes.items()):
        if cls != "SkeletalMesh":
            continue
        kind, gender, mid = kind_of(path)
        folder = os.path.dirname(path)
        m = models.get(mid)
        if m is not None and (m["kind"] != kind or (kind not in ("hair", "npc", "weapon") and m["folder"] != folder
                                                   and kind not in ("outfit", "costume", "hat", "polymorph"))):
            mid = pkg(path).replace("AION2/", "").replace("/", "__")     # same name somewhere else
            m = models.get(mid)
        if m is None:
            m = models[mid] = {"kind": kind, "gender": gender, "parts": [], "folder": folder}
        m["parts"].append(path)
    for m in models.values():
        m["parts"].sort()
    return models


PART_ORDER = ["Body", "Pants", "Glove", "Boots", "Helmet", "Shoulder", "Cape"]
WEARABLE = ("outfit", "costume", "polymorph")
# slots the base body fills when a set has no part for them (the game shows the base body there)
BASE_FOR_SLOT = {"Body": "{g}_BaseBody", "Pants": "{g}_BasePants"}
VARIANT_RE = re.compile(r"^(?P<slot>.+?)_(?P<v>[A-Z])$")


def part_name(path: str, model_id: str) -> str:
    s = stem(path)
    if s.lower().startswith(model_id.lower() + "_"):
        return s[len(model_id) + 1:]
    if model_id.startswith("NPC_") and s.lower().startswith(model_id.lower() + "_"):
        return s[len(model_id) + 1:]
    return s


def resolve(models: dict, mid: str, head: str | None = None, hair: str | None = None, variant: str = "A") -> dict:
    """The parts one export assembles: {"id", "kind", "gender", "parts": [{"name", "path", "package"}], "notes"}.

    Wearable sets (outfit / costume / polymorph) get the base body where they have no Body / Pants part and a
    head + hair (defaults <G>_Head_001 / <G>_Hair_001).  A slot with lettered alternatives (Body_A / Body_B:
    hood up / down and the like) uses `variant` (default A)."""
    m = models.get(mid)
    if m is None:
        raise KeyError(mid)
    out = {"id": mid, "kind": m["kind"], "gender": m["gender"], "folder": m["folder"], "parts": [], "notes": []}
    chosen = {}
    for p in m["parts"]:
        name = part_name(p, mid)
        if m["kind"] == "hair" and TYPE_RE.search(stem(p)):
            continue                                       # the hat versions of a hairstyle
        mv = VARIANT_RE.match(name)
        slot = mv.group("slot") if mv else name
        if mv and mv.group("v") != variant:
            other = [q for q in m["parts"] if VARIANT_RE.match(part_name(q, mid)) and
                     VARIANT_RE.match(part_name(q, mid)).group("slot") == slot and
                     VARIANT_RE.match(part_name(q, mid)).group("v") == variant]
            if other:
                out["notes"].append("%s: variant %s used (%s skipped)" % (slot, variant, name))
                continue
        chosen.setdefault(slot, p)
    if head and m["kind"] not in WEARABLE:
        # an NPC with a player head instead of its own: Satia's own head carries one phantom material for skin and
        # eyes alike (her face is GF_Head_006's)
        if head not in models:
            raise KeyError("head %s" % head)
        if "Head" in chosen:
            out["notes"].append("own head %s replaced by %s" % (stem(chosen["Head"]), head))
        chosen["Head"] = models[head]["parts"][0]
        out["head"] = head
    for slot, p in chosen.items():
        out["parts"].append({"name": slot, "path": p, "package": pkg(p)})
    if m["kind"] in WEARABLE and m["gender"]:
        g = m["gender"]
        for slot, base in BASE_FOR_SLOT.items():
            if slot not in chosen:
                bid = base.format(g=g)
                if bid in models:
                    bp = models[bid]["parts"][0]
                    out["parts"].append({"name": "Base" + slot, "path": bp, "package": pkg(bp)})
                    out["notes"].append("no %s part: base body %s" % (slot, bid))
        for name, wanted in (("Head", head or DEFAULT_HEAD[g]), ("Hair", hair or DEFAULT_HAIR[g])):
            if name in chosen:
                out["notes"].append("the set has its own %s part" % name)
                continue
            if wanted not in models:
                raise KeyError("%s %s" % (name.lower(), wanted))
            hp = models[wanted]["parts"][0]
            out["parts"].append({"name": name, "path": hp, "package": pkg(hp)})
        out["head"], out["hair"] = head or DEFAULT_HEAD[g], hair or DEFAULT_HAIR[g]
    order = {n: i for i, n in enumerate(PART_ORDER + ["BaseBody", "BasePants", "Head", "Hair"])}
    out["parts"].sort(key=lambda x: (order.get(x["name"], 50), x["name"]))
    return out


# ---------------------------------------------------------------- women among the npc / monster models
# Only player parts carry a gender code (GF / GM).  NPCs, monsters and cut-scene meshes are judged by evidence, the
# first that decides wins (model_genders):
#   1. a name token F / M: NPC_F_Refugee_01, MOB_Lepharist_F_01, NPC_M_LegionF_01 (male: the M token comes first);
#   2. a word ending in F / M: VillagerF, ShugoAF, FighterF, KoboWorkF, ShugoM (NPC_ShugoM_Hair_007 imports GF parts);
#   3. the player parts the meshes import (zen header): GF only -> F (Yustiel's head is GF_Head_041's face, Hadar
#      wears GF_Hair_401), GM only -> M;
#   4. female chest jiggle bones in the model's own skeleton (FEMALE_BONE_RE): Kromede (Breast_L_Bone01), Protect,
#      DranaFairy, DarkLeda (the GF rig's b_L_Breast_Base).
# Children (Kid / Child in the name or the folder) are marked and left out of --women.  Measured 10-25 on the 2,973 npc / monster /
# other models: 63 adult human women among the NPCs, ~16 female monster looks.
GENDERED_KINDS = ("npc", "monster", "monster_starter", "other_skeletal")
CHILD_RE = re.compile(r"kid|child|baby", re.I)
OWN_SKELETON_RE = re.compile(r"(/SK_[^/]*|_SK|_Sk|Skeleton[^/]*|_Skel[^/]*)$")
# b_L_Breast_Base / _001 (GF rig), Breast_L_Bone01, Bone_Breast, Bip001-L-Breast01, L_Breast_Sub_01; NOT the GM rig's
# plain L_Breast / R_breast (pectorals, also on Israphel) nor the owls' Chest_L_Bone_*
FEMALE_BONE_RE = re.compile(r"breast.*(\d|base|sub|bone)|bone.*breast", re.I)
SUFFIX_GENDER_RE = re.compile(r"[a-z][A-Z]?([FM])$")


def _token_gender(mid: str) -> str:
    tokens = mid.split("_")
    for t in tokens:
        if t in ("F", "M"):
            return t
    return ""


def _suffix_gender(mid: str) -> str:
    for t in mid.split("_"):
        m = SUFFIX_GENDER_RE.search(t)
        if m:
            return m.group(1)
    return ""


def judge_gender(game: pak.Game, mid: str, m: dict, bones_cache: dict) -> dict:
    """{"gender": "F" | "M" | "", "child": bool, "why": str} for one npc / monster / other model."""
    out = {"gender": "", "child": bool(CHILD_RE.search(mid) or CHILD_RE.search(m["folder"].split("/NPC/")[-1])),
           "why": ""}
    g = _token_gender(mid) or _suffix_gender(mid)
    if g:
        out.update(gender=g, why="name")
        return out
    imports = set()
    for p in m["parts"]:
        try:
            imports.update(game.header(p).get("imported_packages", []))
        except (KeyError, ValueError):
            continue
    f = any("/Player/GF/" in i for i in imports)
    mm = any("/Player/GM/" in i for i in imports)
    if f != mm:
        out.update(gender="F" if f else "M", why="player parts")
        return out
    for imp in sorted(imports):
        if "/Weapon/" in imp or not OWN_SKELETON_RE.search(imp) or not imp.startswith("/Game/"):
            continue
        if imp not in bones_cache:
            path = CONTENT + imp[len("/Game/"):] + ".uasset"
            try:
                bones_cache[imp] = any(FEMALE_BONE_RE.search(n) for n in game.header(path)["names"])
            except (KeyError, ValueError):
                bones_cache[imp] = False
        if bones_cache[imp]:
            out.update(gender="F", why="chest bones")
            return out
    return out


def model_genders(game: pak.Game, models: dict, cache_file: str, refresh: bool = False) -> dict:
    """model id -> judge_gender() for the GENDERED_KINDS, cached in <export-root>\\_meta\\aion2_genders.json
    (rebuilt with the class cache's signature: a game update re-judges)."""
    sig = _signature(game)
    if not refresh and os.path.isfile(cache_file):
        with open(cache_file, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("signature") == sig:
            return data["genders"]
    t0 = time.time()
    bones_cache = {}
    todo = sorted(mid for mid, m in models.items() if m["kind"] in GENDERED_KINDS)
    out = {mid: judge_gender(game, mid, models[mid], bones_cache) for mid in todo}
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as fh:
        json.dump({"signature": sig, "genders": out}, fh, indent=0)
    print("judged %d npc / monster / other models in %.0f s -> %s" % (len(out), time.time() - t0, cache_file),
          file=sys.stderr)
    return out


def gender_of(mid: str, m: dict, genders: dict) -> str:
    """'F' / 'M' / '': the part's own code (GF / GM), else the judged one; children count as ''."""
    if m["gender"]:
        return m["gender"][1]
    j = genders.get(mid) or {}
    return "" if j.get("child") else j.get("gender", "")


def summary(classes: dict, models: dict) -> str:
    lines = []
    cls_count = Counter(classes.values())
    lines.append("packages scanned: %d   SkeletalMesh %d   StaticMesh %d   Texture2D %d   MaterialInstanceConstant %d"
                 "   AnimSequence %d" % (len(classes), cls_count["SkeletalMesh"], cls_count["StaticMesh"],
                                         cls_count["Texture2D"], cls_count["MaterialInstanceConstant"],
                                         cls_count["AnimSequence"]))
    by = Counter((m["kind"], m["gender"]) for m in models.values())
    parts = Counter()
    for m in models.values():
        parts[(m["kind"], m["gender"])] += len(m["parts"])
    lines.append("")
    lines.append("%-18s %-6s %8s %8s" % ("kind", "gender", "models", "meshes"))
    for (kind, gender), n in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append("%-18s %-6s %8d %8d" % (kind, gender or "-", n, parts[(kind, gender)]))
    lines.append("%-18s %-6s %8d %8d" % ("total", "", sum(by.values()), sum(parts.values())))
    statics = Counter()
    for path, cls in classes.items():
        if cls == "StaticMesh":
            statics["/".join(path.split("/")[2:3])] += 1
    lines.append("")
    lines.append("StaticMesh by top folder: " + ", ".join("%s %d" % kv for kv in statics.most_common(12)))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-root", default=pak.DEFAULT_GAME_ROOT)
    ap.add_argument("--key-file", default=pak.DEFAULT_KEY_FILE)
    ap.add_argument("--oodle", default=pak.DEFAULT_OODLE)
    ap.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    ap.add_argument("--scan", action="store_true", help="(re)build the class cache")
    ap.add_argument("--scan-limit", type=int, default=0, help="test the scan speed on the first N packages")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--kind")
    ap.add_argument("--gender", choices=["GF", "GM"])
    ap.add_argument("--resolve", metavar="MODEL", help="parts + umodel packages of one model")
    ap.add_argument("--head", help="head for an outfit (default <G>_Head_001)")
    ap.add_argument("--hair", help="hair for an outfit (default <G>_Hair_001)")
    ap.add_argument("--raw", action="store_true", help="list packages instead of models")
    ap.add_argument("--class", dest="cls", help="with --raw: only this class")
    ap.add_argument("--path-filter", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--catalogue", action="store_true",
                    help="write every model (id, kind, gender, parts) to <export-root>\\_meta\\aion2_models.json")
    ap.add_argument("--find", nargs="+", metavar="WORD",
                    help="models whose id contains any of the words (case ignored; * and ? as wildcards)")
    ap.add_argument("--women", action="store_true",
                    help="female models only: GF player parts + the npc / monster models judged female "
                         "(first run ~2 min, then cached in _meta\\aion2_genders.json)")
    ap.add_argument("--regender", action="store_true", help="judge the npc / monster genders again")
    args = ap.parse_args()

    key = pak.read_key(key_file=args.key_file)
    game = pak.Game(args.game_root, key, args.oodle)
    cache = os.path.join(args.export_root, "_meta", "aion2_classes.json")
    classes = None if args.scan or args.scan_limit else load_classes(game, cache)
    if classes is None:
        print("scanning %d package headers with %d workers ..." % (
            sum(1 for p in game.index if p.endswith(".uasset")), args.workers), flush=True)
        classes = scan_classes(game, key, args.oodle, cache, args.workers, args.scan_limit)
        if args.scan_limit:
            print(Counter(classes.values()).most_common(10))
            return 0
    models = build_models(classes)

    genders = {}
    if args.women or args.regender or args.catalogue or args.find or args.kind or args.gender:
        genders = model_genders(game, models, os.path.join(args.export_root, "_meta", "aion2_genders.json"),
                                args.regender)

    if args.catalogue:
        path = os.path.join(args.export_root, "_meta", "aion2_models.json")
        counts = Counter("%s %s" % (m["kind"], m["gender"] or "-") for m in models.values())
        data = {"counts": dict(sorted(counts.items())),
                "skeletal_meshes": sum(1 for c in classes.values() if c == "SkeletalMesh"),
                "static_meshes": sum(1 for c in classes.values() if c == "StaticMesh"),
                "models": {mid: {"kind": m["kind"], "gender": m["gender"], "folder": m["folder"],
                                 "sex": gender_of(mid, m, genders),          # judged for npc / monster too
                                 "child": bool((genders.get(mid) or {}).get("child")),
                                 "why": (genders.get(mid) or {}).get("why", ""),
                                 "parts": [pkg(p) for p in m["parts"]]} for mid, m in sorted(models.items())}}
        with open(path + ".tmp", "w", encoding="utf-8") as fh:          # a failed run keeps the old catalogue
            json.dump(data, fh, indent=1)
        os.replace(path + ".tmp", path)
        print("%d models -> %s" % (len(models), path))
        return 0

    if args.raw:
        rows = [(p, c) for p, c in sorted(classes.items()) if args.path_filter in p and (not args.cls or c == args.cls)]
        if args.json:
            print(json.dumps(rows, indent=1))
        else:
            for p, c in rows:
                print("%-28s %s" % (c, p))
        return 0

    if args.resolve:
        try:
            out = resolve(models, args.resolve, args.head, args.hair)
        except KeyError as e:
            raise SystemExit("unknown model %s (see --kind ...)" % e)
        print(json.dumps(out, indent=1, ensure_ascii=False) if args.json else
              "\n".join(["%s (%s %s)" % (args.resolve, out["kind"], out["gender"] or "-")] +
                        ["  %-10s %s" % (x["name"], x["package"]) for x in out["parts"]] +
                        ["  note: " + n for n in out["notes"]]))
        return 0

    if args.kind or args.gender or args.find or args.women:
        def wanted(mid, m):
            if args.find:                      # any word: --find yustiel leda siel lists all three
                low = mid.lower()
                if not any(fnmatch.fnmatch(low, w.lower()) if any(c in w for c in "*?") else w.lower() in low
                           for w in args.find):
                    return False
            if args.women and gender_of(mid, m, genders) != "F":
                return False
            return ((not args.kind or m["kind"] == args.kind) and (not args.gender or m["gender"] == args.gender)
                    and args.path_filter in m["folder"])

        rows = sorted((mid, m) for mid, m in models.items() if wanted(mid, m))
        if args.json:
            print(json.dumps({mid: m for mid, m in rows}, indent=1))
        else:
            for mid, m in rows:
                sex = m["gender"] or (gender_of(mid, m, genders) or "-") + (
                    " (%s)" % genders[mid]["why"] if genders.get(mid, {}).get("why") else "")
                print("%-34s %-14s %-18s %2d  %s" % (mid, m["kind"], sex, len(m["parts"]),
                                                    " ".join(part_name(p, mid) for p in m["parts"])[:100]))
            print("%d models" % len(rows))
        return 0

    print(summary(classes, models))
    return 0


if __name__ == "__main__":
    sys.exit(main())
