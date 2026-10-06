"""Edge padding for the colour maps of a finished PMX - plain Python (numpy + Pillow), any PMX.

The baked colour maps (``*_baked.png``, Blender2XPS -> mmd_tools) go straight from an island's last pixel to
transparent black: Blender2XPS bakes with an 8 px margin, but those pixels keep alpha 0 and come out black.
A texture is sampled between pixels (bilinear, and from smaller mip levels the further away it is), so along
every UV seam the transparent black outside the island bleeds in: a thin dark line, in Blender and in MMD.  On
the Vindictus body it runs round the shoulder (the arm island of MI_PCF_Upper01 ends there) and shows as soon
as the arm is raised.

Per texture (all materials using it):
- the UV triangles are drawn into a coverage mask; when every pixel inside it (shrunk by 2 px) is opaque, the
  texture is opaque (skin, face, cloth) and its alpha becomes 255 everywhere; a texture with real transparency
  inside its islands (hair, lashes, brows, lace) keeps its alpha;
- every pixel with alpha > 0 keeps its colour; the others are filled by a pull-push pyramid that first grows
  the filled area 2 pixels at every level, so the pixels right at an island's border take that island's
  colour (aligned 2x2 blocks alone hand them a coarse average of far-off islands).
Nothing the model shows changes; the file is rewritten (through a temporary file) only when a pixel did.

    python pad_textures.py <model.pmx> [--mirror <dir> ...] [--dry-run]

``--mirror``: another folder with copies of the same maps (the XPS export): a file there with the same name
and the same bytes as the original is replaced by the padded one.  export_pmx.py runs pad_pmx() on the PMX it
has written (``--no-pad`` skips it).  First used 2026-10-05 on the 16 archived Fiona PMX + their XPS.
"""
import argparse
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)

ERODE = 2                     # pixels the coverage shrinks before its alpha is judged
OPAQUE_HOLES = 0.001          # share of not fully opaque pixels inside the islands still counted as opaque
RINGS = 2                     # pixels the filled area grows at every pyramid level


def _shifted(a, dy, dx):
    """out[y, x] = a[y + dy, x + dx] (edges repeat)."""
    h, w = a.shape[:2]
    if h <= abs(dy) or w <= abs(dx):
        return a.copy()
    out = np.empty_like(a)
    ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    out[yd, xd] = a[ys, xs]
    if dy > 0:
        out[h - dy:] = out[h - dy - 1:h - dy]
    elif dy < 0:
        out[:-dy] = out[-dy:-dy + 1]
    if dx > 0:
        out[:, w - dx:] = out[:, w - dx - 1:w - dx]
    elif dx < 0:
        out[:, :-dx] = out[:, -dx:-dx + 1]
    return out


def grow(rgb, filled, rings):
    """Each ring of empty pixels next to filled ones takes a filled neighbour's colour, ``rings`` times."""
    rgb, filled = rgb.copy(), filled.copy()
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
    for _ in range(rings):
        done = np.zeros_like(filled)
        for dy, dx in steps:
            take = ~filled & ~done & _shifted(filled, dy, dx)
            if take.any():
                rgb[take] = _shifted(rgb, dy, dx)[take]
                done |= take
        if not done.any():
            break
        filled |= done
    return rgb, filled


def pull_push(rgb, filled, rings=RINGS):
    """Fill the pixels that are not ``filled`` from the nearest filled ones (see the module docstring)."""
    levels = []
    c, w = rgb.astype(np.float32), filled.copy()
    while True:
        c, w = grow(c, w, rings)
        levels.append((c, w))
        h, wd = w.shape
        if h == 1 and wd == 1:
            break
        h2, w2 = (h + 1) // 2, (wd + 1) // 2
        cw = c * w[..., None]
        ww = w.astype(np.float32)
        if h % 2 or wd % 2:
            cw = np.pad(cw, ((0, h2 * 2 - h), (0, w2 * 2 - wd), (0, 0)))
            ww = np.pad(ww, ((0, h2 * 2 - h), (0, w2 * 2 - wd)))
        cs = cw.reshape(h2, 2, w2, 2, -1).sum((1, 3))
        ws = ww.reshape(h2, 2, w2, 2).sum((1, 3))
        c, w = cs / np.maximum(ws, 1e-8)[..., None], ws > 0
    color = levels[-1][0]
    for c, w in reversed(levels[:-1]):
        h, wd = w.shape
        up = np.repeat(np.repeat(color, 2, 0), 2, 1)[:h, :wd]
        color = np.where(w[..., None], c, up)
    return color


def _erode(mask, n):
    m = mask.copy()
    for _ in range(n):
        e = m.copy()
        e[1:] &= m[:-1]
        e[:-1] &= m[1:]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return m


def uv_triangles(model):
    """{texture path: [[(u, v) x 3], ...]} over every material that has a colour map (the path as the PMX spells
    it: the files are rewritten under their own names, not normcase's lower case)."""
    out, spelled = {}, {}
    start = 0
    for m in model.materials:
        n = m.vertex_count // 3
        tris = model.faces[start:start + n]
        start += n
        if m.texture is None or m.texture < 0:
            continue
        path = os.path.abspath(model.textures[m.texture].path)
        path = spelled.setdefault(os.path.normcase(path), path)
        out.setdefault(path, []).extend([[tuple(model.vertices[i].uv) for i in t] for t in tris])
    return out


def pad_image(rgba, triangles):
    """(padded RGBA array, stats) for one texture and the UV triangles that use it."""
    h, w = rgba.shape[:2]
    cover = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(cover)
    for tri in triangles:
        draw.polygon([(u * w, v * h) for u, v in tri], fill=255)
    inside = _erode(np.asarray(cover) > 0, ERODE)
    alpha = rgba[..., 3]
    holes = float((alpha[inside] < 255).mean()) if inside.any() else 0.0
    opaque = holes < OPAQUE_HOLES
    seen = alpha > 0
    rgb = np.where(seen[..., None], rgba[..., :3],
                   np.clip(np.rint(pull_push(rgba[..., :3], seen)), 0, 255)).astype(np.uint8)
    padded = np.dstack([rgb, np.full_like(alpha, 255) if opaque else alpha])
    return padded, {"opaque": opaque, "holes": round(holes, 5), "empty": round(1.0 - float(seen.mean()), 4)}


def _write_png(path, array):
    temporary = path + ".pad.tmp"
    Image.fromarray(array, "RGBA").save(temporary, format="PNG")
    os.replace(temporary, path)


def pad_pmx(pmx_path, mirrors=(), dry_run=False, log=print, pmx_module=None):
    """Pad every colour map of ``pmx_path`` in place; returns {file name: stats}."""
    pmx = bust_physics.load_pmx_module(pmx_module)
    model = pmx.load(pmx_path)
    listings = [(folder, {os.path.normcase(f): f for f in os.listdir(folder)}) for folder in mirrors
                if os.path.isdir(folder)]
    report = {}
    for path, triangles in sorted(uv_triangles(model).items()):
        name = os.path.basename(path)
        if not os.path.isfile(path):
            report[name] = {"missing": True}
            log("%-40s missing" % name)
            continue
        t0 = time.time()
        original = open(path, "rb").read()
        image = Image.open(path)
        rgba = np.asarray(image.convert("RGBA"))
        padded, stats = pad_image(rgba, triangles)
        stats["changed"] = bool((padded != rgba).any())
        stats["mirrors"] = []
        if stats["changed"] and not dry_run:
            _write_png(path, padded)
            data = open(path, "rb").read()
            for folder, listing in listings:
                own = listing.get(os.path.normcase(name))         # the copy's own spelling
                copy = os.path.join(folder, own) if own else ""
                if own and os.path.isfile(copy) and open(copy, "rb").read() == original:
                    temporary = copy + ".pad.tmp"
                    with open(temporary, "wb") as fh:
                        fh.write(data)
                    os.replace(temporary, copy)
                    stats["mirrors"].append(copy)
        stats["seconds"] = round(time.time() - t0, 1)
        report[name] = stats
        log("%-40s %s" % (name, stats))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pmx")
    ap.add_argument("--mirror", action="append", default=[],
                    help="a folder with copies of the same maps (same name + same bytes are replaced too)")
    ap.add_argument("--dry-run", action="store_true", help="classify and count only, write nothing")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = pad_pmx(args.pmx, args.mirror, args.dry_run, pmx_module=args.pmx_module)
    changed = sum(1 for s in report.values() if s.get("changed"))
    print("%d of %d colour maps %s" % (changed, len(report), "would change" if args.dry_run else "padded"))


if __name__ == "__main__":
    sys.exit(main())
