r"""One sheet of every exported heroine: full-body front preview + face close-up, Chinese name and outfit.

    python overview.py [--out <png>]     (default E:\game_export\VindictusNA\_overview\女性角色_效果总览.png)

Takes each heroine's look from looks.py and its previews from <export>\<Name>\blend\<Look>\.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import looks  # noqa: E402

EXPORT = os.environ.get('VINDICTUSNA_EXPORT', r'E:\game_export\VindictusNA')
ORDER = ['fiona', 'evy', 'vella', 'lynn', 'arisha', 'delia', 'miri', 'miul', 'bel', 'lethor', 'tessa', 'danah', 'letty',
         'latiya', 'czern', 'sanyaa', 'neamhain', 'calia', 'lumielle']


def font(size):
    try:
        return ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', size)
    except OSError:
        return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(EXPORT, '_overview', '女性角色_效果总览.png'))
    ap.add_argument('--cols', type=int, default=7)
    a = ap.parse_args()
    cw, bh, fh = 300, 450, 170          # cell width, body height, face height
    ch = bh + fh + 56
    heroes = [h for h in ORDER if h in looks.HEROES]
    rows = (len(heroes) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (cw * a.cols, 52 + rows * ch), (34, 36, 40))
    d = ImageDraw.Draw(sheet)
    d.text((12, 10), '洛奇英雄传 Vindictus（北美服）女性角色 19 位 · 每位一个外观 · .blend / XPS / PMX', fill=(235, 235, 235), font=font(24))
    for i, h in enumerate(heroes):
        look = looks.resolve(h)
        base = os.path.join(EXPORT, look['name'], 'blend', look['look'], look['look'])
        x, y = (i % a.cols) * cw, 52 + (i // a.cols) * ch
        try:
            body = Image.open(base + '_front.png').convert('RGB')
            w, hh = body.size
            body = body.crop((int(w * 0.18), 0, int(w * 0.82), hh)).resize((cw, bh))
            sheet.paste(body, (x, y))
            face = Image.open(base + '_face.png').convert('RGB')
            w, hh = face.size
            face = face.crop((int(w * 0.2), int(hh * 0.12), int(w * 0.8), int(hh * 0.62))).resize((cw, fh))
            sheet.paste(face, (x, y + bh))
        except OSError:
            d.text((x + 10, y + 200), '（未导出）', fill=(240, 120, 120), font=font(20))
        d.text((x + 10, y + bh + fh + 4), '%s %s' % (look['cn'], h), fill=(240, 240, 240), font=font(20))
        d.text((x + 10, y + bh + fh + 30), '%s %s' % (looks.OUTFIT_CN.get(look['outfit'], look['outfit']), look['outfit_name']),
               fill=(150, 205, 150), font=font(15))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sheet.save(a.out)
    print(a.out, sheet.size)


if __name__ == '__main__':
    main()
