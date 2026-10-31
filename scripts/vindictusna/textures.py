r"""Textures for the Blender build (system Python, needs numpy + Pillow):

  * VTF -> PNG with Noesis (NOESIS, default E:\tools\noesisv\Noesis64.exe), full resolution, existing PNGs kept;
  * dye-mask statistics: which textures are dye masks (R / G / B = the item's three dye slots, brightness = shading,
    the game multiplies in the player's colours) and which are true colour - stats.json, read by build_blend.py;
  * face composite: the game lays the face layers (brows, make-up from materials/models/player/face_layer/<hero>/)
    over the face texture at run time; composite() bakes them in.
"""
import glob
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

NOESIS = os.environ.get('NOESIS', r'E:\tools\noesisv\Noesis64.exe')
SKIP_SUB = ('normal', 'brow0', 'makeup', 'painting', 'piercing', 'scar')
SKIP_END = ('_mask', '_sp', '_pe')


# uncompressed VTF formats: enum -> (bytes per pixel, channel order of the stored bytes)
_RAW = {0: (4, 'RGBA'), 1: (4, 'ABGR'), 2: (3, 'RGB'), 3: (3, 'BGR'), 12: (4, 'BGRA'), 16: (4, 'BGRX'), 11: (4, 'ARGB')}


def raw_vtf_to_png(src, dst):
    """Fallback for the few uncompressed VTFs Noesis rejects (e.g. a 128 px ABGR8888 normal map): the largest mip
    is the last w x h block of the file for a single-frame, single-face texture."""
    import struct
    import numpy as np
    from PIL import Image
    d = open(src, 'rb').read()
    if d[:4] != b'VTF\0':
        return False
    w, h = struct.unpack_from('<2H', d, 16)
    frames = struct.unpack_from('<H', d, 24)[0]
    fmt = struct.unpack_from('<i', d, 52)[0]
    if fmt not in _RAW or frames != 1:
        return False
    bpp, order = _RAW[fmt]
    n = w * h * bpp
    if len(d) < n:
        return False
    px = np.frombuffer(d[len(d) - n:], np.uint8).reshape(h, w, bpp)
    ch = {c: px[..., i] for i, c in enumerate(order)}
    a = ch.get('A', np.full((h, w), 255, np.uint8)) if 'X' not in order else np.full((h, w), 255, np.uint8)
    Image.fromarray(np.dstack([ch['R'], ch['G'], ch['B'], a]), 'RGBA').save(dst)
    return True


def vtf_to_png(jobs, threads=8):
    """jobs = [(vtf path, png path)]; returns the number written"""
    todo = [j for j in jobs if not os.path.exists(j[1])]

    def one(job):
        src, dst = job
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run([NOESIS, '?cmode', src, dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(dst):
            try:
                raw_vtf_to_png(src, dst)
            except Exception:           # noqa: BLE001 - reported as not converted below
                pass
        return os.path.exists(dst)
    with ThreadPoolExecutor(threads) as ex:
        ok = sum(ex.map(one, todo))
    if ok < len(todo):
        print('  %d of %d textures did not convert' % (len(todo) - ok, len(todo)))
    return ok


def stat(p):
    """pure = share of the lit pixels (max > 0.2) whose second-strongest channel is under 0.3 x the strongest.
    Over the 282 textures of 19 heroines it splits cleanly: true colour (faces, eyes, teeth, skin) 0.00-0.07,
    dye masks 0.42-1.00 (masks with gradients between slots - two-tone hair tips, R->B fades - sit at 0.4-0.9;
    a 'pure > 0.88 over max > 0.08' test calls them true colour and a sock comes out bright green)."""
    import numpy as np
    from PIL import Image
    im = Image.open(p)
    size = list(im.size)
    a = np.asarray(im.convert('RGBA').resize((128, 128)), dtype=np.float32) / 255
    rgb, alpha = a[..., :3], a[..., 3]
    mx = rgb.max(-1)
    second = np.sort(rgb, -1)[..., 1]
    live = (mx > 0.2) & (alpha > 0.05)
    if live.sum() < 20:
        return None
    pure = ((second < 0.3 * mx) & live).sum() / live.sum()
    dom = np.argmax(rgb, -1)
    use = [float(((dom == c) & live).sum() / live.sum()) for c in range(3)]
    return {'dye': bool(pure > 0.3), 'pure': round(float(pure), 3), 'use_rgb': [round(u, 3) for u in use],
            'alpha_mean': round(float(alpha.mean()), 3), 'size': size}


def update_stats(stats_path, png_dir):
    stats = json.load(open(stats_path)) if os.path.exists(stats_path) else {}
    n = 0
    for p in sorted(glob.glob(os.path.join(png_dir, '*.png'))):
        k = os.path.splitext(os.path.basename(p))[0].lower()
        if k in stats or any(s in k for s in SKIP_SUB) or k.endswith(SKIP_END):
            continue
        s = stat(p)
        if s:
            stats[k] = s
            n += 1
    if n:                                   # written only when something is new (parallel exports share the file)
        tmp = stats_path + '.%d.tmp' % os.getpid()
        json.dump(stats, open(tmp, 'w'), indent=1)
        os.replace(tmp, stats_path)
    return n


def fill_sclera(src_png, dst_png):
    """The game's eyeball textures are not a sclera: black, with only the almond the lids leave open painted white
    (the lids' shadow is baked in).  Fine while the eye stays put - the game slides only its projected iris - but a
    PMX / XPS eye bone turns the whole ball and the black comes into the eye opening.  Fill the dark part with the
    texture's own sclera colour (median of its bright core), a little darker away from the almond, and keep the
    almond itself unchanged so the eye at rest looks exactly as before."""
    import numpy as np
    from PIL import Image
    im = np.asarray(Image.open(src_png).convert('RGBA'), dtype=np.float32) / 255
    rgb, a = im[..., :3], im[..., 3:4]
    lum = rgb.max(-1)
    top = float(np.percentile(lum, 99.5))
    if top < 0.2:
        return None
    core = lum > 0.8 * top
    colour = np.median(rgb[core], axis=0)
    h, w = lum.shape
    ys, xs = np.nonzero(lum > 0.5 * top)
    cy, cx = ys.mean(), xs.mean()
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((yy - cy) / (h / 2)) ** 2 + ((xx - cx) / (w / 2)) ** 2)
    shade = 1.0 - 0.22 * np.clip(r, 0, 1) ** 2
    fill = colour[None, None, :] * shade[..., None]
    out = np.maximum(rgb, fill)            # never darker than the fill: no dark ring left round the almond
    Image.fromarray((np.clip(np.concatenate([out, a], -1), 0, 1) * 255 + 0.5).astype(np.uint8), 'RGBA').save(dst_png)
    return dst_png


def composite(face_png, out_png, layers):
    """layers = [(png, tint sRGB 0-255 or None, opacity)]; a tint recolours the layer keeping its own brightness
    pattern.  The face's alpha (spec / SSS mask) is kept."""
    import numpy as np
    from PIL import Image
    face = np.asarray(Image.open(face_png).convert('RGBA'), dtype=np.float32) / 255
    rgb = face[..., :3].copy()
    for path, tint, opacity in layers:
        lay = Image.open(path).convert('RGBA')
        if lay.size != (face.shape[1], face.shape[0]):
            lay = lay.resize((face.shape[1], face.shape[0]), Image.LANCZOS)
        lay = np.asarray(lay, dtype=np.float32) / 255
        a = lay[..., 3:4] * opacity
        col = lay[..., :3]
        if tint is not None:
            lum = col.max(-1, keepdims=True)
            on = lay[..., 3] > 0.3
            ref = np.percentile(lum[on], 90) if on.any() else 1.0
            col = np.clip(np.clip(lum / max(ref, 1e-3), 0, 1.4) * np.array(tint, dtype=np.float32) / 255, 0, 1)
        rgb = rgb * (1 - a) + col * a
    out = np.concatenate([rgb, face[..., 3:4]], -1)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGBA').save(out_png)
    return out_png
