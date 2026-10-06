"""Contact sheet of arm_stills.py images (plain Python + Pillow): one row per label, one column per shot.

  python arm_sheet.py <stills dir> <out.jpg> <label,label,...> [--shots rest_side,bend90_side,...] [--tile 380]
          [--zoom 2.0]

``--zoom`` crops the middle 1/zoom of every image (the elbow sits in the middle); a missing image leaves its tile
grey.  Every tile is captioned "<label> <shot>".
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("stills")
ap.add_argument("out")
ap.add_argument("labels")
ap.add_argument("--shots", default="rest_side,bend90_side,bend130_side,bend90_inside,twistU80_side,twistF80_side")
ap.add_argument("--tile", type=int, default=380)
ap.add_argument("--zoom", type=float, default=2.0)
args = ap.parse_args()
labels, shots, tile = args.labels.split(","), args.shots.split(","), args.tile
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", max(12, tile // 18))
sheet = Image.new("RGB", (tile * len(shots), tile * len(labels)), (60, 60, 60))
draw = ImageDraw.Draw(sheet)
for row, label in enumerate(labels):
    for col, shot in enumerate(shots):
        path = os.path.join(args.stills, "%s_%s.png" % (label, shot))
        x, y = col * tile, row * tile
        if os.path.isfile(path):
            image = Image.open(path).convert("RGB")
            w, h = image.size
            cw, ch = w / args.zoom, h / args.zoom
            box = (int((w - cw) / 2), int((h - ch) / 2), int((w + cw) / 2), int((h + ch) / 2))
            sheet.paste(image.crop(box).resize((tile, tile)), (x, y))
        draw.text((x + 6, y + 4), "%s %s" % (label, shot), fill=(255, 230, 80), font=font)
sheet.save(args.out, quality=90)
print(args.out)
