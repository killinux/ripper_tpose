# -*- coding: utf-8 -*-
"""An outfit (coordinate) card + the zipmods it needs, worn by a character card -> .blend, like export_model.py --card.

    python coordinate_export.py --coordinate <outfit .png> --zipmod <x.zipmod> [--zipmod ...]
           --chara <character card .png | file name in UserData/chara/female> --name <label>
           [--state full|half] [--out D:\\hs2_exports] [--blender <blender 3.6>] [--force]

First use: GGAdams' "[AI/HS2] Outfit - Gantz Suit" (Patreon, free): two coordinate cards (Gantz Full / Gantz Swim) whose
clothes are all from the zipmod "[gyobobo] Gantz" (gyobobo.gantz, public Sideloader Modpack).

How:
  * a coordinate card is a PNG + 【AIS_Clothes】 block: product, marker, version, language, name, then
    int32 total + [int32 size + MessagePack] x 2 (clothes, accessories), then the plugins' extended data;
  * its part ids are the sideloader's RESOLVED ids (>= 100000000); each maps to (zipmod, category, original id).
    Here the map is by category: when a zipmod has one item in that category, that is the part (gyobobo.gantz has
    one per category); a category with several items stops with a message (the card's resolver data would be needed);
  * zipmods are unpacked once to <out>/_zipmods/<guid>/; their abdata folders are searched before the game's
    (hs2_data.abdata_path is wrapped) and their list CSVs (line 1 category, line 2 distribution, line 3 list path,
    line 4 header, then rows) join the game's lists under the resolved ids;
  * the character card keeps her body, face and hair; her clothes and accessories become the outfit card's (what
    loading a coordinate does in the game).  MaterialEditor / ABMX data in the cards is not applied.
Writes <out>/cards/<name>/ (scene.json, textures, <name>.blend, preview).  Prints HS2_COORD={json}.
"""
import argparse
import csv
import io
import json
import os
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_model as em  # noqa: E402
import hs2_data  # noqa: E402
import hs2_msgpack  # noqa: E402

RESOLVED_MIN = 100000000


def _r7(f):
    n, shift = 0, 0
    while True:
        b = f.read(1)[0]
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
    return f.read(n).decode("utf-8", "replace")


def read_coordinate(path):
    data = open(path, "rb").read()
    end = data.find(b"IEND")
    if end < 0:
        raise SystemExit("%s: not a PNG card" % path)
    f = io.BytesIO(data[end + 8:])
    struct.unpack("<i", f.read(4))
    marker = _r7(f)
    if "AIS_Clothes" not in marker:
        raise SystemExit("%s: not an HS2 / AIS coordinate card (marker %r)" % (path, marker))
    _r7(f)                                            # version
    struct.unpack("<i", f.read(4))                    # language
    name = _r7(f)
    total = struct.unpack("<i", f.read(4))[0]
    blob = f.read(total)
    g, parts = io.BytesIO(blob), []
    while g.tell() < len(blob):
        n = struct.unpack("<i", g.read(4))[0]
        parts.append(hs2_msgpack.unpackb(g.read(n)))
    return {"name": name, "clothes": parts[0], "accessory": parts[1]}


def unpack_zipmod(path, root):
    with zipfile.ZipFile(path) as z:
        manifest = z.read("manifest.xml").decode("utf-8", "replace")
        guid = manifest.split("<guid>", 1)[1].split("</guid>", 1)[0].strip()
        dst = os.path.join(root, guid)
        stamp = os.path.join(dst, ".from")
        key = "%s %d" % (os.path.basename(path), os.path.getsize(path))
        if not (os.path.isfile(stamp) and open(stamp, encoding="utf-8").read() == key):
            z.extractall(dst)
            with open(stamp, "w", encoding="utf-8") as fh:
                fh.write(key)
    rows = {}
    folder = os.path.join(dst, "abdata", "list", "characustom")
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not fn.lower().endswith(".csv"):
            continue
        lines = open(os.path.join(folder, fn), encoding="utf-8-sig").read().splitlines()
        cat, dist = int(lines[0].split(",")[0]), lines[1].split(",")[0]
        for row in csv.DictReader(lines[3:]):
            if row.get("ID", "").strip().isdigit():
                row["_dist"] = "zipmod:%s:%s" % (guid, dist)
                rows.setdefault(cat, {})[int(row["ID"])] = row
    return guid, os.path.join(dst, "abdata"), rows


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coordinate", required=True)
    ap.add_argument("--zipmod", action="append", default=[])
    ap.add_argument("--chara", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--state", choices=["full", "half"], default="full")
    ap.add_argument("--game")
    ap.add_argument("--out", default=hs2_data.EXPORTS_DEFAULT)
    ap.add_argument("--blender", default=os.environ.get("BLENDER", em.BLENDER_DEFAULT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    args.fbx, args.no_preview, args.no_blend = False, False, False

    root = hs2_data.game_root(args.game)
    lists = hs2_data.load_lists(root, os.path.join(args.out, "_cache"))
    deps = hs2_data.load_manifest_deps(root)
    extra_roots, zip_rows = [], {}
    for zp in args.zipmod:
        guid, abdata, rows = unpack_zipmod(zp, os.path.join(args.out, "_zipmods"))
        extra_roots.append(abdata)
        for cat, items in rows.items():
            zip_rows.setdefault(cat, []).extend(items.values())
    game_path = hs2_data.abdata_path

    def abdata_path(r, rel):
        for base in extra_roots:
            p = os.path.join(base, rel.replace("/", os.sep))
            if os.path.isfile(p):
                return p
        return game_path(r, rel)
    hs2_data.abdata_path = abdata_path

    coord = read_coordinate(args.coordinate)
    chara = args.chara
    if not os.path.isfile(chara):
        chara = os.path.join(root, "UserData", "chara", "female", chara if chara.lower().endswith(".png") else chara + ".png")
    card = hs2_data.read_card(chara)
    card["clothes"], card["accessory"] = coord["clothes"], coord["accessory"]
    resolved = []
    for role, cat, item_id, _extra in hs2_data.card_parts(card):
        if item_id < RESOLVED_MIN:
            # a card saved without the sideloader (the zipmod author's own) keeps the zipmod's local ids
            local = next((r for r in zip_rows.get(cat, []) if int(r["ID"]) == item_id), None)
            if local is not None and item_id not in lists.get(cat, {}):
                lists.setdefault(cat, {})[item_id] = local
                resolved.append({"role": role, "category": cat, "id": item_id, "zipmod_row": local["ID"],
                                 "prefab": local.get("MainData"), "name": local.get("Name"), "local_id": True})
            continue
        cand = zip_rows.get(cat, [])
        if len(cand) != 1:
            raise SystemExit("%s:%d - %d zipmod items in category %d; the card's resolver data would be needed"
                             % (role, item_id, len(cand), cat))
        lists.setdefault(cat, {})[item_id] = cand[0]
        resolved.append({"role": role, "category": cat, "id": item_id, "zipmod_row": cand[0]["ID"],
                         "prefab": cand[0].get("MainData"), "name": cand[0].get("Name")})

    out_dir = os.path.join(args.out, "cards", args.name)
    if not args.force and os.path.isfile(os.path.join(out_dir, args.name + ".blend")):
        print("have %s" % out_dir, flush=True)
        return
    b = em.Builder(root, lists, deps, out_dir, args.state)
    b.body(card["sex"])
    for role, cat, item_id, extra in hs2_data.card_parts(card):
        if role == "head":
            b.head(item_id)
            continue
        try:
            b.item(cat, item_id, role, extra=extra)
        except KeyError as exc:
            b.scene.warnings.append(str(exc))
    b.skin(card["face"], card["body"])
    meta = {"kind": "card", "card": os.path.basename(chara), "character": card["name"], "sex": card["sex"],
            "coordinate": os.path.basename(args.coordinate), "outfit": coord["name"],
            "zipmods": [os.path.basename(z) for z in args.zipmod], "resolved": resolved, "state": args.state}
    res = em.finish(b, out_dir, args.name, meta, args)
    print("HS2_COORD=" + json.dumps({"result": {k: v for k, v in res.items() if k != "report"}, "resolved": resolved},
                                    ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
