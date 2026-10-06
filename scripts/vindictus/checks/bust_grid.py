"""Put bust_video.py clips side by side with captions (plain Python: Pillow + ffmpeg).

  python bust_grid.py <out.mp4> <clips dir> <columns> "<label>=<caption>" ["<label>=<caption>" ...] [--tile 560]
          [--audio test|<file.wav>]

Each label is a bust_video.py clip (<clips dir>/frames_<label>/); they fill the grid row by row, ``columns`` per
row; the caption is drawn on the tile ("PCF_005|C 方案" puts the part after | on a second line).  ``--audio test``
lays test_motion.BGM under it from 1 s on (the clips' motion starts after a 30-frame lead-in).
"""
import argparse
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_motion  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("clips")
ap.add_argument("columns", type=int)
ap.add_argument("tiles", nargs="+")
ap.add_argument("--tile", type=int, default=560)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--audio", default="", help="'test' = test_motion.BGM, or a sound file")
ap.add_argument("--audio-start", type=float, default=1.0, help="seconds (the clips' 30-frame lead-in)")
args = ap.parse_args()
tiles = [t.split("=", 1) for t in args.tiles]
rows = (len(tiles) + args.columns - 1) // args.columns
big = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 26)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 22)
folders = [os.path.join(args.clips, "frames_" + label) for label, _ in tiles]
count = min(len([f for f in os.listdir(d) if f.endswith(".png")]) for d in folders)
grid = os.path.splitext(args.out)[0] + "_frames"
os.makedirs(grid, exist_ok=True)
for frame in range(1, count + 1):
    sheet = Image.new("RGB", (args.tile * args.columns, args.tile * rows), (40, 40, 44))
    draw = ImageDraw.Draw(sheet)
    for i, ((_label, caption), folder) in enumerate(zip(tiles, folders)):
        x, y = (i % args.columns) * args.tile, (i // args.columns) * args.tile
        image = Image.open(os.path.join(folder, "%04d.png" % frame)).convert("RGB")
        sheet.paste(image.resize((args.tile, args.tile), Image.LANCZOS), (x, y))
        first, _, second = caption.partition("|")
        draw.text((x + 10, y + 8), first, font=big, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        if second:
            draw.text((x + 10, y + 42), second, font=small, fill=(255, 240, 160), stroke_width=2, stroke_fill=(0, 0, 0))
    sheet.save(os.path.join(grid, "%04d.png" % frame))
command = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps), "-i", os.path.join(grid, "%04d.png")]
audio = test_motion.BGM if args.audio == "test" else args.audio
if audio:
    # no -shortest: a sound shorter than the clip just ends early (the old shake-dance BGM.wav was 7 s)
    command += ["-itsoffset", str(args.audio_start), "-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac",
                "-b:a", "160k"]
command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", args.out]
subprocess.run(command, check=True)
print("wrote %s (%d frames, frames in %s)" % (args.out, count, grid))
