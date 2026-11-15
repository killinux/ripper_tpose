"""comparison sheet: MMD shading vs the stellarblade_game_materials add-on's game materials
    python make_sheet.py <test_addon out dir> <sheet.jpg> "<title>" """
import os
import sys

from PIL import Image, ImageDraw, ImageFont

font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 26)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 22)
H = 900
src, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
shots = [("mmd_full", "MMD 着色"), ("game_full", "游戏材质"), ("mmd_chest", "MMD 着色"), ("game_chest", "游戏材质"),
         ("mmd_hips", "MMD 着色"), ("game_hips", "游戏材质"), ("mmd_face", "MMD 着色"), ("game_face", "游戏材质")]
tiles = []
for name, label in shots:
    p = os.path.join(src, name + ".png")
    if not os.path.isfile(p):
        continue
    im = Image.open(p).convert("RGB")
    im = im.resize((int(im.width * H / im.height), H), Image.LANCZOS)
    t = Image.new("RGB", (im.width, H + 44), (24, 24, 28))
    t.paste(im, (0, 44))
    ImageDraw.Draw(t).text((10, 6), label, fill=(255, 225, 150), font=font)
    tiles.append(t)
if not tiles:
    raise SystemExit("no renders in " + src)
head = 56
sheet = Image.new("RGB", (sum(t.width for t in tiles) + 6 * (len(tiles) - 1), tiles[0].height + head), (10, 10, 12))
ImageDraw.Draw(sheet).text((12, 12), title + "：剑星游戏材质插件，左 MMD 着色 / 右 游戏材质"
                           "（Blender 3.6 EEVEE，Filmic，同一盏太阳光 + 浅灰环境光）", fill=(235, 235, 235), font=small)
x = 0
for t in tiles:
    sheet.paste(t, (x, head))
    x += t.width + 6
sheet.save(out, quality=88)
print(out, sheet.size, os.path.getsize(out))
