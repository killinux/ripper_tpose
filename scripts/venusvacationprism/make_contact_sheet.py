"""Compose labeled contact sheets from model thumbnails (Pillow).

  python make_contact_sheet.py <tiles.json> <out_prefix>

tiles.json: [{"png": "...", "label": "830  34.4MiB"}, ...]
Writes <out_prefix>_1.png, _2.png ... with at most ROWS*COLS tiles each.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

COLS = 6
ROWS = 4
TILE_W = 300
TILE_H = 450
LABEL_H = 22

tiles_path, out_prefix = sys.argv[1], sys.argv[2]
# utf-8-sig: PowerShell 5.1 Out-File -Encoding utf8 writes a BOM.
with open(tiles_path, "r", encoding="utf-8-sig") as handle:
    tiles = json.load(handle)

per_sheet = COLS * ROWS
sheets = []
for start in range(0, len(tiles), per_sheet):
    chunk = tiles[start:start + per_sheet]
    rows = (len(chunk) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TILE_W, rows * (TILE_H + LABEL_H)), (34, 36, 42))
    draw = ImageDraw.Draw(sheet)
    for position, tile in enumerate(chunk):
        x = (position % COLS) * TILE_W
        y = (position // COLS) * (TILE_H + LABEL_H)
        if tile.get("png") and os.path.isfile(tile["png"]):
            image = Image.open(tile["png"]).convert("RGB")
            image.thumbnail((TILE_W, TILE_H))
            sheet.paste(image, (x + (TILE_W - image.width) // 2, y))
        else:
            draw.text((x + 8, y + TILE_H // 2), "RENDER FAILED", fill=(255, 90, 90))
        draw.text((x + 6, y + TILE_H + 4), tile.get("label", "?"), fill=(240, 240, 240))
    out_path = f"{out_prefix}_{start // per_sheet + 1}.png"
    sheet.save(out_path)
    sheets.append(out_path)

print(json.dumps({"sheets": sheets, "tiles": len(tiles)}, ensure_ascii=False))
