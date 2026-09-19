# -*- coding: utf-8 -*-
"""Batch-assemble every Rise of Eros 'suit' (outfit variant) into its own .blend.

For each ``accessory_components_pc_<id>_suit_<suit>.ab`` stub in the game (the
``common`` pool of seasonal accessories is not a suit and is skipped):

1. ``suit_bundle.export_suit`` reads the parts, textures and dressed selection
   straight from the bundles into ``<exports>/_suits/<id>/<suit>/``;
2. Blender runs ``assemble_suit_blender.py --suit`` on top of the character's
   extracted nude base (``<exports>/<id>/pc_<id>_nk`` from extract_character.ps1)
   and writes ``<exports>/<id>/blend/pc_<id>_<suit>.blend`` + ``_preview.png``.

Several Blender lanes run in parallel; a manifest with every part's status lands
in ``<exports>/_suits/manifest.json`` and ``--sheet`` tiles all previews into one
contact sheet for a visual pass.

    python export_suits.py --list
    python export_suits.py                       # everything not built yet
    python export_suits.py --only j01:prouniform,b01:*  --force
    python export_suits.py --sheet               # only rebuild the contact sheet
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import suit_bundle  # noqa: E402

GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles"
EXPORTS = r"D:\roe_exports"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
ASSEMBLER = os.path.join(HERE, "assemble_suit_blender.py")
SKIP_SUITS = {"common"}
_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def list_suits(game):
    out = []
    for name in sorted(os.listdir(game)):
        m = re.match(r"accessory_components_pc_([a-z]\d+)_suit_(.+)\.ab$", name.lower())
        if m and m.group(2) not in SKIP_SUITS:
            out.append((m.group(1), m.group(2)))
    return out


def wanted(selection, cid, suit):
    if not selection:
        return True
    for item in selection:
        want_id, _, want_suit = item.partition(":")
        if want_id == cid and (want_suit in ("", "*", suit)):
            return True
    return False


def blend_path(exports, cid, suit):
    return os.path.join(exports, cid, "blend", "pc_%s_%s.blend" % (cid, suit))


def build_one(args, cid, suit):
    started = time.time()
    out_blend = blend_path(args.exports, cid, suit)
    work = os.path.join(args.exports, "_suits", cid, suit)
    entry = {"id": cid, "suit": suit, "blend": out_blend, "status": "PENDING"}
    try:
        if not args.skip_extract or not os.path.isfile(os.path.join(work, "suit.json")):
            manifest = suit_bundle.export_suit(args.game, cid, suit, work, os.path.join(args.exports, cid))
        else:
            with open(os.path.join(work, "suit.json"), encoding="utf-8") as fh:
                manifest = json.load(fh)
        entry["parts"] = len(manifest["parts"])
        entry["excluded"] = manifest["excluded"]
        entry["base"] = manifest["base"]
        base_fbx = os.path.join(args.exports, cid, manifest["base"], "FBX_GameObjects", manifest["base"], manifest["base"] + ".fbx")
        if not os.path.isfile(base_fbx):
            raise FileNotFoundError("base body FBX missing: %s (run extract_character.ps1 %s first)" % (base_fbx, cid))
        cmd = [args.blender, "--background", "--factory-startup", "--python", ASSEMBLER, "--",
               "--root", os.path.join(args.exports, cid), "--tex", os.path.join(args.exports, cid, "_textures"),
               "--out", out_blend, "--suit", os.path.join(work, "suit.json"), "--glb", "1" if args.glb else "0"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        with open(os.path.join(work, "build.log"), "w", encoding="utf-8") as fh:
            fh.write(text)
        parts = []
        for line in text.splitlines():
            if line.startswith("PART "):
                parts.append(line[5:].strip())
        saved = next((l for l in text.splitlines() if l.startswith("SAVED ")), "")
        entry["blender_parts"] = parts
        entry["saved"] = saved
        if "ASSEMBLE_DONE" in text and os.path.isfile(out_blend):
            entry["status"] = "PASS"
            m = re.search(r"missing=(\[.*\])", saved)
            if m and m.group(1) != "[]":
                entry["status"] = "WARN"
                entry["missing"] = m.group(1)
        else:
            entry["status"] = "FAIL"
            tail = [l for l in text.splitlines() if l.strip()][-12:]
            entry["error"] = "\n".join(tail)
    except Exception as exc:  # noqa: BLE001
        entry["status"] = "FAIL"
        entry["error"] = "%s: %s" % (type(exc).__name__, exc)
    entry["seconds"] = round(time.time() - started, 1)
    log("%-5s %s:%s  %ss  %s" % (entry["status"], cid, suit, entry["seconds"], entry.get("error", "")[:160].replace("\n", " | ")))
    return entry


def contact_sheet(exports, suits, out_path, thumb_h=360):
    from PIL import Image, ImageDraw
    tiles = []
    for cid, suit in suits:
        path = blend_path(exports, cid, suit).replace(".blend", "_preview.png")
        if not os.path.isfile(path):
            continue
        img = Image.open(path).convert("RGB")
        img = img.resize((int(img.width * thumb_h / img.height), thumb_h))
        tiles.append(("%s:%s" % (cid, suit), img))
    if not tiles:
        return None
    cols = 3
    w = max(t.width for _, t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, thumb_h * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * thumb_h
        sheet.paste(img, (x, y))
        draw.rectangle((x, y, x + 8 * len(label) + 8, y + 16), fill="black")
        draw.text((x + 4, y + 2), label, fill="yellow")
    sheet.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", default=GAME)
    ap.add_argument("--exports", default=EXPORTS)
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--only", default="", help="comma list of id:suit or id:* (default: all)")
    ap.add_argument("--exclude", default="", help="comma list of suit keys to leave out, e.g. fm")
    ap.add_argument("--lanes", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="rebuild even when the .blend exists")
    ap.add_argument("--skip-extract", action="store_true", help="reuse an existing suit.json / parts dump")
    ap.add_argument("--glb", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sheet", action="store_true", help="only tile the existing previews into a contact sheet")
    args = ap.parse_args()

    suits = list_suits(args.game)
    selection = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    excluded_suits = {s.strip().lower() for s in args.exclude.split(",") if s.strip()}
    suits = [(c, s) for c, s in suits if wanted(selection, c, s) and s not in excluded_suits]
    manifest_path = os.path.join(args.exports, "_suits", "manifest.json")
    if args.list:
        for cid, suit in suits:
            print("%s:%-16s %s" % (cid, suit, "built" if os.path.isfile(blend_path(args.exports, cid, suit)) else "-"))
        print(len(suits), "suits")
        return
    if args.sheet:
        print(contact_sheet(args.exports, suits, os.path.join(args.exports, "_suits", "_contact.png")))
        return
    todo = [(c, s) for c, s in suits if args.force or not os.path.isfile(blend_path(args.exports, c, s))]
    print("%d suits selected, %d to build, %d lanes" % (len(suits), len(todo), args.lanes), flush=True)
    os.makedirs(os.path.join(args.exports, "_suits"), exist_ok=True)
    previous = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            previous = {"%s:%s" % (e["id"], e["suit"]): e for e in json.load(fh).get("suits", [])}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.lanes)) as pool:
        for entry in pool.map(lambda cs: build_one(args, *cs), todo):
            results.append(entry)
            previous["%s:%s" % (entry["id"], entry["suit"])] = entry
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "suits": [previous[k] for k in sorted(previous)]}, fh, indent=1, ensure_ascii=False)
    counts = {}
    for entry in results:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print("done:", counts, "manifest:", manifest_path)
    sheet = contact_sheet(args.exports, suits, os.path.join(args.exports, "_suits", "_contact.png"))
    if sheet:
        print("contact sheet:", sheet)


if __name__ == "__main__":
    main()
