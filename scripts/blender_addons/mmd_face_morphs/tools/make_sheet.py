"""Label and tile the stills of render_morph_sheet.py (system Python + Pillow).

    python make_sheet.py <render_dir> <sheet.png> [--cols 6] [--video sheet.mp4] [--hold 1.0]

The video, if asked for, holds each expression ``--hold`` seconds (ffmpeg).
"""
import glob
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = ("C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/YuGothM.ttc",
         "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/NotoSansSC-VF.ttf")


def font(size):
    for path in FONTS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def main():
    argv = sys.argv[1:]
    render_dir, sheet_path = argv[0], argv[1]
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 6
    video = argv[argv.index("--video") + 1] if "--video" in argv else None
    hold = float(argv[argv.index("--hold") + 1]) if "--hold" in argv else 1.0
    with open(os.path.join(render_dir, "index.json"), encoding="utf-8") as handle:
        index = json.load(handle)
    tiles = index["tiles"]
    # labels of an earlier, longer run would otherwise be swept into the video
    for old in glob.glob(os.path.join(render_dir, "label_*.png")):
        os.remove(old)
    big, small = font(30), font(18)
    labeled = []
    for i, tile in enumerate(tiles):
        image = Image.open(os.path.join(render_dir, tile["file"])).convert("RGB")
        w, h = image.size
        band = 52
        canvas = Image.new("RGB", (w, h + band), (24, 24, 28))
        canvas.paste(image, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, h + 6), tile["name"], font=big, fill=(255, 255, 255))
        sub = "%s  %s" % (tile["category"].lower(), tile["name_e"]) if tile["category"] else tile["name_e"]
        draw.text((w - 10 - draw.textlength(sub, font=small), h + 26), sub, font=small, fill=(170, 170, 180))
        path = os.path.join(render_dir, "label_%02d.png" % i)
        canvas.save(path)
        labeled.append(canvas)
    tw, th = labeled[0].size
    rows = (len(labeled) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (24, 24, 28))
    for i, tile in enumerate(labeled):
        sheet.paste(tile, ((i % cols) * tw, (i // cols) * th))
    sheet.save(sheet_path)
    print("sheet %dx%d, %d tiles -> %s" % (sheet.size[0], sheet.size[1], len(labeled), sheet_path))
    if video:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(1.0 / hold),
               "-i", os.path.join(render_dir, "label_%02d.png"), "-r", "30",
               "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-crf", "20", video]
        subprocess.check_call(cmd)
        print("video -> %s" % video)


if __name__ == "__main__":
    main()
