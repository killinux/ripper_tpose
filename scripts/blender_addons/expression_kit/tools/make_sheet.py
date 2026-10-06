"""Paste the renders of render_sheet.py into one labelled contact sheet (plain Python + Pillow).

  python make_sheet.py <render dir> <sheet.jpg> [--cols 8]
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

src, dst = sys.argv[1], sys.argv[2]
cols = int(sys.argv[sys.argv.index("--cols") + 1]) if "--cols" in sys.argv else 8
with open(os.path.join(src, "index.json"), encoding="utf-8") as fh:
    index = json.load(fh)
first = Image.open(os.path.join(src, index[0]["file"]))
w, h, top = first.width, first.height, 26
rows = (len(index) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * (h + top)), (30, 30, 30))
font = ImageFont.load_default()
for face in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msgothic.ttc"):     # kana + simplified Chinese
    try:
        font = ImageFont.truetype(face, 18)
        break
    except OSError:
        pass
draw = ImageDraw.Draw(sheet)
tags = {"BONE": "骨", "MMD": "顶", "ARKIT": "AR", "": ""}
for i, item in enumerate(index):
    x, y = (i % cols) * w, (i // cols) * (h + top)
    sheet.paste(Image.open(os.path.join(src, item["file"])).convert("RGB"), (x, y + top))
    label = item["name"] + ("  [%s]" % tags[item["kind"]] if item["kind"] else "")
    draw.text((x + 5, y + 2), label, fill=(255, 255, 255), font=font)
sheet.save(dst, quality=88)
print(len(index), sheet.size)
