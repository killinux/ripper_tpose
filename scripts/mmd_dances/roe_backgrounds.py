"""The story backgrounds of Rise of Eros as pictures a dancer can stand in front of.

    python roe_backgrounds.py              # write the pictures that are not there yet, and the contact sheets
    python roe_backgrounds.py --list       # only list what the bundles hold
    python roe_backgrounds.py --sheets     # only draw the contact sheets again

The game keeps the backgrounds of its story (AVG) scenes in `avg_background_image_*.ab`: plain UnityFS bundles in
its StreamingAssets/AssetBundles, one to three Texture2D each (2048 x 1152 or 3840 x 2160, DXT1).  The same bundles
hold the scenes' CG illustrations - named "..._cg01": characters, close-ups of hands, a promotion picture with QR
codes - and "_DMM" copies of a picture for another store; neither is written.  What is:

    <ROE root>/_backgrounds/<texture name>.jpg     the picture (JPEG, quality 92 - the source is DXT1 already)
    <ROE root>/_backgrounds/_index.json            picture -> bundle, texture, size; what was not written and why
    <ROE root>/_backgrounds/_sheets/sheet_<n>.jpg  contact sheets, to look at them

backdrops() is what the dance batch draws from: every picture written, less EXCLUDE - the ones looked at and found
to give a dancer nowhere to stand (EXCLUDE says why for each).  The game's files are only read.
Paths: ROE_GAME (the game folder), ROE_ARCHIVE_ROOT (the archive, as in roe_dances.py).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

GAME_DIR = os.environ.get("ROE_GAME", r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros")
BUNDLES = os.path.join(GAME_DIR, "RiseOfEros_Data", "StreamingAssets", "AssetBundles")
PATTERN = "avg_background_image_*.ab"
ROE_ROOT = os.environ.get("ROE_ARCHIVE_ROOT", r"E:\game_export\RiseOfEros")
FOLDER = "_backgrounds"
QUALITY = 92
CG = re.compile(r"(^|[_\s])cg\d*($|[_\s])", re.IGNORECASE)            # a story illustration, not a place
OTHER_STORE = re.compile(r"_DMM$", re.IGNORECASE)                      # the same picture for another store
# looked at (the contact sheets, 2026-10-04) and left out: picture -> why
EXCLUDE: dict[str, str] = {
    "UI_BG_Menu_Common_04.jpg": "界面底图，不是场景",
    "common_Black_avg01.jpg": "全黑",
    "common_memory_avg01.jpg": "回忆特效（波形），不是场景",
    "common_memory_avg02.jpg": "回忆特效（波形），不是场景",
    "event17_s01_avg03.jpg": "回忆特效（波形），不是场景",
    "event30_avg_01_01e.jpg": "带上下黑边的重复版本",
    "event30_avg_01_02e.jpg": "带上下黑边的重复版本",
    "event30_avg_01_03e.jpg": "带上下黑边的重复版本",
    "event30_avg_02_01e.jpg": "带上下黑边的重复版本",
    "event30_avg_02_02e.jpg": "带上下黑边的重复版本",
    "event30_avg_02_03e.jpg": "带上下黑边的重复版本",
    "event40_avg01_07.jpg": "近景特写（柱子和窗格），没有地面",
    "immortal_dwelling_avg02.jpg": "画面中央是一只大怪物",
    "level002_s10_avg01.jpg": "从高处俯视浮空平台，人站不上去",
    "level002_s10_avg02.jpg": "从高处俯视浮空平台，人站不上去",
    "level002_s10_avg03.jpg": "从高处俯视浮空平台，人站不上去",
}


def log(msg: str) -> None:
    print("[roe-backgrounds] " + msg, flush=True)


def file_name(texture: str) -> str:
    """The picture's file name: the texture's name made file-safe ("event32_ avg01_01" -> "event32__avg01_01.jpg")."""
    return re.sub(r"[^0-9A-Za-z._-]+", "_", texture.strip()).strip("._") + ".jpg"


def why_not(texture: str, others: set[str]) -> str:
    """Why a texture of a background bundle is not written ("" = it is): a CG illustration, or a store's copy of a
    picture that is there under its own name."""
    if CG.search(texture):
        return "剧情 CG（插画，不是场景）"
    if OTHER_STORE.search(texture) and OTHER_STORE.sub("", texture) in others:
        return "另一个商店版本的同一张图"
    return ""


def folder(root: str = ROE_ROOT) -> str:
    return os.path.join(root, FOLDER)


def read_index(root: str = ROE_ROOT) -> dict:
    try:
        with open(os.path.join(folder(root), "_index.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"pictures": {}, "skipped": {}}


def backdrops(root: str = ROE_ROOT) -> list[str]:
    """File names of the pictures a dancer can stand in front of: written, still there, not in EXCLUDE."""
    where = folder(root)
    pictures = read_index(root).get("pictures") or {}
    return sorted(f for f in pictures if f not in EXCLUDE and os.path.isfile(os.path.join(where, f)))


def extract(root: str = ROE_ROOT, bundles: str = BUNDLES, only_list: bool = False) -> dict:
    import UnityPy

    files = sorted(glob.glob(os.path.join(bundles, PATTERN)))
    if not files:
        raise SystemExit("no %s in %s (ROE_GAME = the game folder)" % (PATTERN, bundles))
    where = folder(root)
    os.makedirs(where, exist_ok=True)
    index = read_index(root)
    pictures, skipped = index.setdefault("pictures", {}), index.setdefault("skipped", {})
    written = 0
    for n, path in enumerate(files, 1):
        env = UnityPy.load(path)
        textures = [obj for obj in env.objects if obj.type.name == "Texture2D"]
        names = {obj.read().m_Name for obj in textures}
        for obj in textures:
            tex = obj.read()
            reason = why_not(tex.m_Name, names)
            bundle = os.path.basename(path)
            if only_list:
                print("%-60s %-40s %5d x %-5d %s" % (bundle, tex.m_Name, tex.m_Width, tex.m_Height, reason or "ok"))
                continue
            if reason:
                skipped[tex.m_Name] = {"bundle": bundle, "why": reason}
                continue
            name = file_name(tex.m_Name)
            if name in pictures and pictures[name]["bundle"] != bundle:
                name = file_name("%s_%s" % (os.path.splitext(bundle)[0], tex.m_Name))
            out = os.path.join(where, name)
            if not os.path.isfile(out):
                image = tex.image.convert("RGB")
                image.save(out + ".tmp", "JPEG", quality=QUALITY)
                os.replace(out + ".tmp", out)
                written += 1
            pictures[name] = {"bundle": bundle, "texture": tex.m_Name, "size": [tex.m_Width, tex.m_Height]}
        if n % 25 == 0:
            log("%d / %d bundles" % (n, len(files)))
    if not only_list:
        with open(os.path.join(where, "_index.json.tmp"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=1)
        os.replace(os.path.join(where, "_index.json.tmp"), os.path.join(where, "_index.json"))
        log("%d bundles: %d pictures (%d new), %d left out as CG / store copies" % (
            len(files), len(pictures), written, len(skipped)))
    return index


def sheets(root: str = ROE_ROOT, columns: int = 6, rows: int = 8, size: tuple = (320, 180)) -> list[str]:
    """Contact sheets of every written picture, numbered and named; the excluded ones are crossed out in red."""
    from PIL import Image, ImageDraw

    where = folder(root)
    pictures = sorted(read_index(root).get("pictures") or {})
    out_dir = os.path.join(where, "_sheets")
    os.makedirs(out_dir, exist_ok=True)
    per, done = columns * rows, []
    w, h = size
    for start in range(0, len(pictures), per):
        chunk = pictures[start:start + per]
        sheet = Image.new("RGB", (columns * w, ((len(chunk) + columns - 1) // columns) * (h + 18)), (30, 30, 30))
        draw = ImageDraw.Draw(sheet)
        for i, name in enumerate(chunk):
            x, y = (i % columns) * w, (i // columns) * (h + 18)
            try:
                im = Image.open(os.path.join(where, name)).convert("RGB")
                im.thumbnail(size)
                sheet.paste(im, (x, y + 18))
            except OSError:
                pass
            draw.text((x + 3, y + 3), "%d %s" % (start + i + 1, name[:-4][:44]), fill=(255, 230, 0))
            if name in EXCLUDE:
                draw.line((x, y + 18, x + w, y + 18 + h), fill=(255, 0, 0), width=4)
        path = os.path.join(out_dir, "sheet_%d.jpg" % (start // per + 1))
        sheet.save(path, quality=85)
        done.append(path)
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="only list the bundles' textures")
    ap.add_argument("--sheets", action="store_true", help="only draw the contact sheets again")
    ap.add_argument("--roe-root", default=ROE_ROOT, help="the ROE archive (default %(default)s)")
    ap.add_argument("--bundles", default=BUNDLES, help="the game's AssetBundles folder (default %(default)s)")
    a = ap.parse_args()
    if not a.sheets:
        extract(a.roe_root, a.bundles, a.list)
    if not a.list:
        for path in sheets(a.roe_root):
            log("sheet: %s" % path)
        log("%d pictures to stand in front of" % len(backdrops(a.roe_root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
