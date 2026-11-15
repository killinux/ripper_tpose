# Contact sheet of preview images: python sheet.py <out.jpg> <cell_w> <cell_h> <cols> <label=path> ...
import sys

from PIL import Image, ImageDraw, ImageFont

out, cw, ch, cols = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
items = [a.split("=", 1) for a in sys.argv[5:]]
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (cw * cols, (ch + 18) * rows), (40, 40, 40))
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
except Exception:
    font = ImageFont.load_default()
d = ImageDraw.Draw(sheet)
for k, (label, path) in enumerate(items):
    x, y = (k % cols) * cw, (k // cols) * (ch + 18)
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((cw, ch))
        sheet.paste(im, (x + (cw - im.width) // 2, y + 18 + (ch - im.height) // 2))
    except Exception as e:
        d.text((x + 4, y + 30), str(e)[:40], fill=(255, 80, 80), font=font)
    d.text((x + 3, y + 2), label, fill=(255, 255, 255), font=font)
sheet.save(out, quality=88)
print("ok", out, sheet.size)
