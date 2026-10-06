"""Downscaled copies of a level's textures for video renders (EEVEE keeps every texture uncompressed on the GPU; the
full set of 4K / 8K maps overflowed the 16 GB card next to the two characters and other apps' VRAM).

  python shrink_textures.py <assets dir> <out dir> [--max 1024] [--landscape-mi <MI .props.txt> --landscape-max 2048]

Mirrors every .png larger than the limit into <out dir> (same relative path); level cells (_Generated_: height /
weight maps) are skipped; existing copies are kept (rerun = resume)."""
import argparse
import os
import re
from concurrent.futures import ProcessPoolExecutor

from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def shrink(job):
    src, dst, limit = job
    try:
        with Image.open(src) as im:
            w, h = im.size
            if max(w, h) <= limit:
                return src, "small"
            f = max(w, h) / float(limit)
            size = (max(1, round(w / f)), max(1, round(h / f)))
            if im.mode in ("I;16", "I;16B", "I;16L", "I"):
                out = im.convert("I").resize(size, Image.NEAREST)
            else:
                out = im.resize(size, Image.LANCZOS)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            out.save(dst + ".tmp.png")
        os.replace(dst + ".tmp.png", dst)
        return src, "%dx%d -> %dx%d" % (w, h, size[0], size[1])
    except Exception as exc:                                # noqa: BLE001 - report and go on
        return src, "ERROR %r" % exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("assets")
    ap.add_argument("out")
    ap.add_argument("--max", type=int, default=1024)
    ap.add_argument("--landscape-mi", default="")
    ap.add_argument("--landscape-max", type=int, default=2048)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    big = set()
    if args.landscape_mi:
        text = open(args.landscape_mi, encoding="utf-8", errors="replace").read()
        big = {m.lower() for m in re.findall(r"Texture2D'[^']*\.([^'.]+)'", text)}
    jobs = []
    for dp, dirs, files in os.walk(args.assets):
        if "_generated_" in dp.replace(os.sep, "/").lower():
            continue
        for f in files:
            if not f.lower().endswith(".png"):
                continue
            src = os.path.join(dp, f)
            dst = os.path.join(args.out, os.path.relpath(src, args.assets))
            if os.path.exists(dst):
                continue
            limit = args.landscape_max if f[:-4].lower() in big else args.max
            jobs.append((src, dst, limit))
    print(len(jobs), "textures to check", flush=True)
    done = shrunk = 0
    with ProcessPoolExecutor(args.workers) as pool:
        for src, what in pool.map(shrink, jobs, chunksize=4):
            done += 1
            if what != "small":
                shrunk += 1
            if what.startswith("ERROR"):
                print(src, what, flush=True)
            if done % 100 == 0:
                print("%d / %d checked, %d shrunk" % (done, len(jobs), shrunk), flush=True)
    print("done: %d checked, %d shrunk" % (done, shrunk), flush=True)


if __name__ == "__main__":
    main()
