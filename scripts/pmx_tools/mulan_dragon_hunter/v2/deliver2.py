# Delivery of v2 beside v1: PMX + textures_v2\ (paths rewritten) + v2_preview*.png + mp4 + 参考对比_v2.jpg
#   python deliver2.py <out_v2c dir> <views dir r_v2c> <head views dir> <delivery dir> [<v1 front png>]
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

src, views, head_views, dst = sys.argv[1:5]
v1_front = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "-" else None
ver = sys.argv[6] if len(sys.argv) > 6 else "v2"
HERE = os.path.dirname(os.path.abspath(__file__))
name = "花木兰_水晶猎龙者_仿制" + ver
os.makedirs(os.path.join(dst, "textures_" + ver), exist_ok=True)
for f in os.listdir(os.path.join(src, "textures")):
    shutil.copyfile(os.path.join(src, "textures", f), os.path.join(dst, "textures_" + ver, f))
M = L.load(os.path.abspath(os.path.join(src, name + ".pmx")))
for t in M.textures:
    t.path = os.path.abspath(os.path.join(dst, "textures_" + ver, os.path.basename(t.path)))
out_pmx = os.path.join(dst, name + ".pmx")
L.save(M, out_pmx)
back = L.load(os.path.abspath(out_pmx))
missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
print("pmx", out_pmx, "textures", len(back.textures), "missing", missing)
for f, g in (("preview.png", ver + "_preview.png"), ("preview_dance.png", ver + "_preview_dance.png"),
             ("preview_gaze.png", ver + "_preview_gaze.png"), ("preview_morphs.png", ver + "_preview_morphs.png"),
             (name + "_手势舞.mp4", name + "_手势舞.mp4")):
    shutil.copyfile(os.path.join(src, f), os.path.join(dst, g))

font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 26)
ref = Image.open(os.path.join(HERE, "..", "ref", "figure.jpg")).convert("RGB")
tiles = [("王者荣耀原画（参考）", ref)]
for p, lab in ((os.path.join(views, "ALL__front.png"), ver + " 正面"), (os.path.join(views, "ALL__side.png"), "侧面"),
               (os.path.join(views, "ALL__back.png"), "背面"), (os.path.join(head_views, "ALL__front.png"), "头部"),
               (os.path.join(head_views, "ALL__side.png"), "头部 侧面")):
    tiles.append((lab, Image.open(p).convert("RGB")))
if v1_front and os.path.isfile(v1_front):
    tiles.append(("上一版 正面", Image.open(v1_front).convert("RGB")))
h = 900
tiles = [(lab, im.resize((int(im.width * h / im.height), h), Image.LANCZOS)) for lab, im in tiles]
sheet = Image.new("RGB", (sum(im.width for _l, im in tiles), h + 40), (255, 255, 255))
d = ImageDraw.Draw(sheet)
x = 0
for lab, im in tiles:
    sheet.paste(im, (x, 40))
    d.text((x + 8, 6), lab, fill=(20, 20, 20), font=font)
    x += im.width
sheet.save(os.path.join(dst, "参考对比_" + ver + ".jpg"), quality=90)
print("delivered:", sorted(os.listdir(dst)))
