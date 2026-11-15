"""Put the tiles of sdef_compare_video.py together: 2 rows (原版 / SDEF) x 3 columns (全身 / 右手肘 / 左膝), labels and
the ring metric of each frame, then an mp4 (with the music when given).  System Python with Pillow + ffmpeg.

    python compose_sdef_video.py <out dir of sdef_compare_video.py> <out.mp4> [--bgm music.wav] [--title "..."]
    python compose_sdef_video.py <out dir> <sheet.jpg> --sheet [--title "..."]

--sheet writes one picture instead: per row the frame where the linear elbow / knee collapsed most, both versions.
Prints COMPOSE_DONE=<path>."""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msyh.ttc"
ROWS = (("lin", "原版（线性蒙皮）"), ("sdef", "SDEF"))
COLS = (("full", "全身"), ("elbow", "右手肘（正对弯曲平面）"), ("knee", "左膝（正对弯曲平面）"))


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def tile_text(row, key, view):
    if view == "full":
        return None
    v = row[view][key]
    deg = row["%s_deg" % view]
    return "弯 %d°   一圈平均 %.2f   最塌 %.2f" % (round(deg), v[0], v[1])


def frame_image(d, row, title, tiles=None):
    f = row["frame"]
    paths = tiles or {(k, v): os.path.join(d, "tiles", "%05d_%s_%s.png" % (f, k, v)) for k, _ in ROWS for v, _ in COLS}
    first = Image.open(next(iter(paths.values())))
    t = first.width
    head, lab = 86, 30
    W, H = t * 3, head + 2 * (t + lab)
    W, H = W + W % 2, H + H % 2
    img = Image.new("RGB", (W, H), (24, 25, 28))
    dr = ImageDraw.Draw(img)
    dr.text((14, 8), title, font=font(26), fill=(255, 226, 150))
    dr.text((14, 46), "距离比 = 关节一圈 SDEF 顶点到关节中心的距离 ÷ 静止时（1.00 = 不塌，越小塌得越多）   帧 %d" % f,
            font=font(18), fill=(200, 200, 205))
    for r, (key, rname) in enumerate(ROWS):
        y = head + r * (t + lab)
        for c, (view, cname) in enumerate(COLS):
            x = c * t
            p = paths[key, view]
            if os.path.isfile(p):
                img.paste(Image.open(p).convert("RGB"), (x, y + lab))
            dr.rectangle((x, y, x + t - 1, y + lab - 1), fill=(36, 37, 42))
            dr.text((x + 8, y + 3), "%s · %s" % (rname, cname), font=font(17),
                    fill=(255, 210, 120) if key == "sdef" else (230, 230, 235))
            txt = tile_text(row, key, view)
            if txt:
                bad = row[view][key][1] < 0.8
                dr.rectangle((x, y + lab + t - 30, x + t - 1, y + lab + t - 1), fill=(20, 20, 24))
                dr.text((x + 8, y + lab + t - 28), txt, font=font(17),
                        fill=(255, 120, 110) if bad else (150, 230, 150))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("out")
    ap.add_argument("--bgm")
    ap.add_argument("--title", default="SDEF 对比：同一个动作，上排原版、下排 SDEF")
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.dir, "metrics.json"), encoding="utf-8"))
    rows = meta["frames"]
    if a.sheet:
        picks = [min(rows, key=lambda r: r["elbow"]["lin"][1]), min(rows, key=lambda r: r["knee"]["lin"][1])]
        ims = [frame_image(a.dir, r, a.title) for r in picks]
        sheet = Image.new("RGB", (ims[0].width, sum(i.height for i in ims)))
        y = 0
        for im in ims:
            sheet.paste(im, (0, y))
            y += im.height
        sheet.save(a.out, quality=90)
        print("COMPOSE_DONE=" + a.out)
        return
    fdir = os.path.join(a.dir, "frames")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    for i, r in enumerate(rows):
        frame_image(a.dir, r, a.title).save(os.path.join(fdir, "%05d.jpg" % i), quality=92)
    fps = meta.get("fps") or 30                      # of the video: the scene's fps / the render step
    scene_fps = meta.get("scene_fps") or fps
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "%g" % fps, "-i", os.path.join(fdir, "%05d.jpg")]
    if a.bgm and not meta.get("bend"):
        # the music starts with VMD frame 0, which mmd_tools puts at scene frame lead_in + 1
        delay = (meta.get("lead_in", 30) + 1 - meta["frame_start"]) / float(scene_fps)
        cmd += ["-itsoffset", "%.3f" % delay, "-i", a.bgm, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", a.out]
    subprocess.run(cmd, check=True)
    print("COMPOSE_DONE=" + a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
