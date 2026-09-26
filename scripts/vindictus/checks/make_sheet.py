import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

src, dst, view = sys.argv[1], sys.argv[2], sys.argv[3]
names = {"blink": "まばたき", "smile": "笑い", "wink": "ウィンク", "wink_R": "ウィンク右", "wink2": "ウィンク２",
         "wink2_R": "ｳｨﾝｸ２右", "surprised": "びっくり", "jito-eye": "じと目", "closexx": "はぅ", "serious": "真面目",
         "trouble": "困る", "cheerful": "にこり", "anger": "怒り", "brow_up": "上", "brow_down": "下", "a": "あ",
         "i": "い", "u": "う", "e": "え", "o": "お", "grin": "にやり", "smile_mouth": "にっこり", "mouth_x": "∧",
         "mouth_corner_up": "口角上げ", "mouth_corner_down": "口角下げ", "mouth_wide": "口横広げ", "neutral": "無表情"}
files = sorted(glob.glob(os.path.join(src, "*_%s.png" % view)))
cols, w, h, top = 7, 360, 360, 28
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * (h + top)), (30, 30, 30))
font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", 22)
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    x, y = (i % cols) * w, (i // cols) * (h + top)
    sheet.paste(Image.open(f).convert("RGB"), (x, y + top))
    key = os.path.basename(f)[3:-(len(view) + 5)]
    d.text((x + 6, y + 2), names.get(key, key), fill=(255, 255, 255), font=font)
sheet.save(dst, quality=88)
print(len(files), sheet.size)
