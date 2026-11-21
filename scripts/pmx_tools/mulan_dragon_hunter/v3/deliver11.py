# Delivery of v11 beside v1..v10: PMX + textures_v11\ (paths rewritten) + v11_preview*.png + mp4 + 参考对比_v11.jpg
# (the MS移植 #44 previews | v11 front / three-quarter / back / head | the previous version).
#   python deliver11.py <out dir of assemble11> <views dir of render_views (front f34 back head .png)> <delivery dir>
#                       [--ref-front PNG] [--ref-back PNG] [--prev JPG/PNG]
import argparse
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2"))
import pmxlib as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("views")
ap.add_argument("dst")
ap.add_argument("--ver", default="v11")
ap.add_argument("--ref-front", default="")
ap.add_argument("--ref-back", default="")
ap.add_argument("--prev", default="")
a = ap.parse_args()
ver = a.ver
name = "花木兰_水晶猎龙者_仿制" + ver
tex_dst = os.path.join(a.dst, "textures_" + ver)
os.makedirs(tex_dst, exist_ok=True)
for f in os.listdir(os.path.join(a.src, "textures")):
    shutil.copyfile(os.path.join(a.src, "textures", f), os.path.join(tex_dst, f))
M = L.load(os.path.abspath(os.path.join(a.src, name + ".pmx")))
for t in M.textures:
    t.path = os.path.abspath(os.path.join(tex_dst, os.path.basename(t.path)))
out_pmx = os.path.join(a.dst, name + ".pmx")
L.save(M, out_pmx)
back = L.load(os.path.abspath(out_pmx))
missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
print("pmx", out_pmx, "textures", len(back.textures), "missing", missing)
for f, g in (("preview.png", ver + "_preview.png"), ("preview_dance.png", ver + "_preview_dance.png"),
             ("preview_gaze.png", ver + "_preview_gaze.png"), ("preview_morphs.png", ver + "_preview_morphs.png"),
             (name + "_手势舞.mp4", name + "_手势舞.mp4")):
    p = os.path.join(a.src, f)
    if os.path.isfile(p):
        shutil.copyfile(p, os.path.join(a.dst, g))
    else:
        print("  (no %s)" % f)

font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 26)
tiles = []
if a.ref_front and os.path.isfile(a.ref_front):
    tiles.append(("参考：MS移植第44期 正面", Image.open(a.ref_front).convert("RGB")))
if a.ref_back and os.path.isfile(a.ref_back):
    tiles.append(("参考 背面", Image.open(a.ref_back).convert("RGB")))
for f, lab in (("front.png", ver + " 正面"), ("f34.png", "斜前"), ("back.png", "背面"), ("head.png", "头部")):
    p = os.path.join(a.views, f)
    if os.path.isfile(p):
        tiles.append((lab, Image.open(p).convert("RGB")))
if a.prev and os.path.isfile(a.prev):
    tiles.append(("上一版 v10 正面", Image.open(a.prev).convert("RGB")))
h = 900
tiles = [(lab, im.resize((int(im.width * h / im.height), h), Image.LANCZOS)) for lab, im in tiles]
sheet = Image.new("RGB", (sum(im.width for _l, im in tiles), h + 40), (255, 255, 255))
d = ImageDraw.Draw(sheet)
x = 0
for lab, im in tiles:
    sheet.paste(im, (x, 40))
    d.text((x + 8, 6), lab, fill=(20, 20, 20), font=font)
    x += im.width
sheet.save(os.path.join(a.dst, "参考对比_" + ver + ".jpg"), quality=90)
print("delivered:", [f for f in sorted(os.listdir(a.dst)) if ver in f])
