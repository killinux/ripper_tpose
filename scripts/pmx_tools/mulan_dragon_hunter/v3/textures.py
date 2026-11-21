# Procedural textures of the 水晶猎龙者 v11 parts (numpy + Pillow).  Every function writes one PNG and returns its path.
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _save(arr, path):
    arr = np.clip(arr, 0, 1)
    mode = "RGBA" if arr.shape[2] == 4 else "RGB"
    Image.fromarray((arr * 255 + 0.5).astype(np.uint8), mode).save(path)
    return path


def _noise(h, w, rng, scale=8, octaves=3):
    """smooth value noise 0..1"""
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = scale * (2 ** o)
        g = rng.random((s + 1, s + 1)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += np.asarray(im, np.float32) / 255 * amp
        tot += amp
        amp *= 0.5
    return out / tot


# the palette, sampled from the MS移植 #44 previews
ARMOR_DARK = np.array([0.070, 0.040, 0.038])
ARMOR_MID = np.array([0.185, 0.092, 0.082])
ARMOR_EDGE = np.array([0.520, 0.170, 0.110])       # the red-brown line along every plate edge
CRYSTAL_TIP = np.array([1.00, 0.90, 0.38])
CRYSTAL_MID = np.array([1.00, 0.43, 0.04])
CRYSTAL_BASE = np.array([0.70, 0.10, 0.02])
FIN_YELLOW = np.array([1.00, 0.86, 0.08])


def armor_plate(path, seed=3, size=256):
    """u = distance from the plate's outline (0 at the edge .. 1 at 4 cm inside), v = free.
    A bright red-brown edge line, a dark groove behind it, a faint second line, then the plate's dark body with a
    little variation."""
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, size)[None, :]
    body = ARMOR_DARK[None, None, :] + (ARMOR_MID - ARMOR_DARK)[None, None, :] * (_noise(size, size, rng, 4)[..., None] * 0.55)
    edge = np.exp(-((u - 0.02) / 0.028) ** 2)                     # 0 - 2 mm
    groove = np.exp(-((u - 0.10) / 0.035) ** 2)
    line2 = 0.0        # (a second line 1 cm in needs a finer mesh than the shells have there)
    col = body * (1 - 0.75 * groove[..., None])
    col = col + (ARMOR_EDGE[None, None, :] - col) * np.clip(edge + line2, 0, 1)[..., None]
    return _save(col, path)


def suit(path, seed=5, size=128):
    """the tight under-suit: near black, a hint of warm variation"""
    rng = np.random.default_rng(seed)
    n = _noise(size, size, rng, 6)[..., None]
    col = np.array([0.035, 0.030, 0.034])[None, None, :] + n * np.array([0.03, 0.015, 0.015])[None, None, :]
    return _save(col, path)


def sphere_gloss(path, size=256, strength=1.0):
    """additive sphere map for the lacquered black plates: a broad soft key light upper-left, a thin strip light on the
    right, a warm rim"""
    y, x = np.mgrid[0:size, 0:size]
    u = (x - size / 2) / (size / 2)
    v = (y - size / 2) / (size / 2)
    r2 = u * u + v * v
    nz = np.sqrt(np.clip(1 - r2, 0, 1))

    def lobe(lx, ly, lz, p):
        ln = np.sqrt(lx * lx + ly * ly + lz * lz)
        return np.clip((u * lx + v * ly + nz * lz) / ln, 0, 1) ** p

    key = lobe(-0.50, -0.62, 0.60, 34) * 0.85 + lobe(-0.50, -0.62, 0.60, 7) * 0.05
    strip = np.exp(-((u - 0.62) / 0.05) ** 2) * np.clip(1 - np.abs(v + 0.1) * 1.3, 0, 1) * 0.26
    sky = np.clip((-v - 0.18) / 0.5, 0, 1) ** 1.5 * 0.10 * nz          # a faint 'sky' in the upper half: lacquer
    low = lobe(0.25, 0.80, 0.55, 30) * 0.10 + sky
    rim = np.clip((r2 - 0.72) / 0.28, 0, 1) ** 2 * 0.07
    col = np.stack([key * 1.0 + strip * 0.9 + low + rim * 1.0, key * 0.93 + strip * 0.85 + low * 0.8 + rim * 0.55,
                    key * 0.90 + strip * 0.95 + low * 0.7 + rim * 0.45], -1) * strength
    col = np.where((r2 <= 1.0)[..., None], col, 0)
    return _save(col, path)


def sphere_crystal(path, size=256):
    y, x = np.mgrid[0:size, 0:size]
    u = (x - size / 2) / (size / 2)
    v = (y - size / 2) / (size / 2)
    r2 = u * u + v * v
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    spec = np.clip((u * -0.4 + v * -0.6 + nz * 0.69), 0, 1)
    lobe = spec ** 30 * 0.6 + spec ** 6 * 0.10
    rim = np.clip((r2 - 0.55) / 0.45, 0, 1) ** 2 * 0.22
    col = np.stack([lobe + rim, lobe * 0.95 + rim * 0.72, lobe * 0.75 + rim * 0.30], -1)
    col = np.where((r2 <= 1.0)[..., None], col, 0)
    return _save(col, path)


def crystal(path, seed=2, size=256, cols=8, kind="orange"):
    """u = facet column (each facet its own brightness), v = 0 at the tip .. 1 at the root"""
    rng = np.random.default_rng(seed)
    v = np.linspace(0, 1, size)[:, None]
    x = np.linspace(0, 1, size, endpoint=False)[None, :]
    if kind == "yellow":
        tip, mid, base = np.array([1.0, 0.97, 0.55]), FIN_YELLOW, np.array([0.95, 0.45, 0.03])
    else:
        tip, mid, base = CRYSTAL_TIP, CRYSTAL_MID, CRYSTAL_BASE
    t = v ** 0.85
    col = np.where(t < 0.4, tip + (mid - tip) * (t / 0.4), mid + (base - mid) * ((t - 0.4) / 0.6))
    col = np.broadcast_to(col[:, None, :] if col.ndim == 2 else col, (size, size, 3)).copy()
    fi = np.floor(x * cols).astype(int) % cols
    bright = rng.uniform(0.62, 1.08, cols)
    col *= bright[fi][..., None]
    fx = (x * cols) % 1.0
    streak = np.exp(-((fx - 0.5) / 0.10) ** 2) * 0.16 * (1 - t)            # a soft glow down each facet's middle
    edge = np.exp(-(np.minimum(fx, 1 - fx) / 0.04) ** 2) * 0.10
    inner = _noise(size, size, rng, 6)[..., None] * 0.18 - 0.09
    col = col + streak[..., None] + edge[..., None] + inner
    return _save(col, path)


def flame_blade(path, size=(128, 512), seed=7, dark_edges=(0.20, 0.20), tip_dark=0.0):
    """for horn / fin / sword blades (geo.blade uv: u across the width, v along the length from the root).
    Black frame along one or both edges, a flame body: red-orange outside, yellow core streaks."""
    w, h = size
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, w)[None, :]
    v = np.linspace(0, 1, h)[:, None]
    core = 1 - np.abs(u - 0.5) * 2                                  # 1 on the ridge, 0 at the edges
    n1 = _noise(h, w, rng, 3)
    streaks = np.clip(np.sin((u * 3.2 + n1 * 1.2 + v * 0.8) * np.pi * 2) * 0.5 + 0.5, 0, 1) ** 2
    heat = np.clip(core * 0.62 + streaks * 0.42 + (1 - v) * 0.10 - 0.16, 0, 1)
    red = np.array([0.78, 0.09, 0.02])
    orange = np.array([1.0, 0.40, 0.03])
    yellow = np.array([1.0, 0.84, 0.22])
    col = np.where(heat[..., None] < 0.5, red + (orange - red) * (heat[..., None] / 0.5),
                   orange + (yellow - orange) * ((heat[..., None] - 0.5) / 0.5))
    frame = np.zeros((h, w), np.float32)
    if dark_edges[0] > 0:
        frame = np.maximum(frame, np.clip((dark_edges[0] - u) / 0.04, 0, 1) * np.ones((h, 1)))
    if dark_edges[1] > 0:
        frame = np.maximum(frame, np.clip((u - (1 - dark_edges[1])) / 0.04, 0, 1) * np.ones((h, 1)))
    if tip_dark > 0:
        frame = np.maximum(frame, np.clip((v - (1 - tip_dark)) / 0.03, 0, 1) * np.ones((1, w)))
    dark = ARMOR_DARK * 1.2
    col = col * (1 - frame[..., None]) + dark[None, None, :] * frame[..., None]
    # a thin bright line where the dark frame meets the flame
    fr_im = Image.fromarray((frame * 255).astype(np.uint8))
    edge = np.asarray(fr_im.filter(ImageFilter.FIND_EDGES), np.float32) / 255
    col = col + edge[..., None] * np.array([0.5, 0.25, 0.05])[None, None, :]
    return _save(col, path)


def petal(path, size=(256, 768), seed=11, dark=False):
    """skirt petal (uv: u across, v from the waist (0) to the tip (1)): orange leaf with lighter veins, darker red
    towards the root and the rim, a thin dark outline"""
    w, h = size
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, w)[None, :]
    v = np.linspace(0, 1, h)[:, None]
    core = 1 - np.abs(u - 0.5) * 2
    lo, hi = (np.array([0.36, 0.05, 0.02]), np.array([0.82, 0.24, 0.05])) if dark else \
        (np.array([0.66, 0.12, 0.03]), np.array([1.0, 0.46, 0.08]))
    base = lo + (hi - lo) * np.clip(core * 0.85 + v * 0.35 - 0.1, 0, 1)[..., None]
    img = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    vein = (214, 110, 50) if dark else (255, 168, 84)
    d.line([(w / 2, 0), (w / 2, h)], fill=vein, width=2)
    for k in range(9):
        y0 = h * (0.06 + 0.10 * k)
        for s in (-1, 1):
            x1 = w / 2 + s * w * 0.46
            y1 = y0 + h * 0.10
            d.line([(w / 2, y0), (x1, y1)], fill=vein, width=1)
            xm, ym = (w / 2 + x1) / 2, (y0 + y1) / 2
            d.line([(xm, ym), (xm + s * w * 0.12, ym + h * 0.09)], fill=vein, width=1)
    arr = np.asarray(img.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    arr = arr * (0.86 + 0.28 * _noise(h, w, rng, 5)[..., None])
    rim = np.clip((0.07 - (1 - np.abs(u - 0.5) * 2) * 0.5) / 0.03, 0, 1) * np.ones((h, 1))
    arr = arr * (1 - 0.8 * rim[..., None]) + np.array([0.20, 0.04, 0.02])[None, None, :] * 0.8 * rim[..., None]
    return _save(arr, path)


def flat(path, rgb, size=8):
    return _save(np.broadcast_to(np.asarray(rgb, np.float32)[None, None, :], (size, size, 3)).copy(), path)


def trim_plate(path, size=256, seed=13):
    """for built (not skin-grown) plates, uv = the plate's own 0..1 box: dark body, a red-brown border line 6 % in"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] / (size - 1)
    d = np.minimum(np.minimum(x, 1 - x), np.minimum(y, 1 - y))
    body = ARMOR_DARK[None, None, :] + (ARMOR_MID - ARMOR_DARK)[None, None, :] * (_noise(size, size, rng, 4)[..., None] * 0.6)
    line = np.exp(-((d - 0.05) / 0.018) ** 2)
    col = body + (ARMOR_EDGE[None, None, :] - body) * line[..., None]
    return _save(col, path)


def dark_blade(path, size=(128, 256), seed=17):
    """black blades / frames (geo.blade uv): red-brown lines just inside both edges, a faint lighter ridge"""
    w, h = size
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, w)[None, :]
    body = ARMOR_DARK[None, None, :] + (ARMOR_MID - ARMOR_DARK)[None, None, :] * (_noise(h, w, rng, 4)[..., None] * 0.6)
    edge = np.exp(-((np.minimum(u, 1 - u) - 0.045) / 0.022) ** 2) * np.ones((h, 1))
    ridge = np.exp(-((u - 0.5) / 0.03) ** 2) * 0.25 * np.ones((h, 1))
    col = body + (ARMOR_EDGE[None, None, :] - body) * np.clip(edge + ridge, 0, 1)[..., None]
    return _save(col, path)


def flame_atlas(path):
    """left half: plain flame blades; right half: horns with a black frame along the outer edge (u -> 1)"""
    import tempfile
    d = tempfile.mkdtemp()
    a = np.asarray(Image.open(flame_blade(os.path.join(d, "a.png"), dark_edges=(0.0, 0.0), seed=7)), np.float32) / 255
    b = np.asarray(Image.open(flame_blade(os.path.join(d, "b.png"), dark_edges=(0.10, 0.42), seed=9)), np.float32) / 255
    return _save(np.concatenate([a, b], 1), path)


def fin(path, size=(128, 256), seed=19):
    """hip fins: bright yellow face, orange towards the edges and the root"""
    w, h = size
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, w)[None, :]
    v = np.linspace(0, 1, h)[:, None]
    core = 1 - np.abs(u - 0.5) * 2
    k = np.clip(core * 1.6 + v * 0.3 + 0.1 + (_noise(h, w, rng, 4) - 0.5) * 0.2, 0, 1)[..., None]
    col = np.array([1.0, 0.55, 0.02])[None, None, :] * (1 - k) + FIN_YELLOW[None, None, :] * k
    hi = np.exp(-((u - 0.5) / 0.05) ** 2)[..., None] * 0.25
    return _save(col + hi, path)


def knee(path, size=256, seed=23):
    """knee guards / brooch rim: red-brown with gold lines (uv = the plate's own box)"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] / (size - 1)
    base = np.array([0.40, 0.11, 0.06])[None, None, :] * (0.75 + 0.5 * _noise(size, size, rng, 4)[..., None])
    r = np.hypot((x - 0.5) * 1.0, (y - 0.42) * 1.2)
    gold = np.array([1.0, 0.66, 0.25])
    lines = np.exp(-((r - 0.27) / 0.014) ** 2) + np.exp(-((r - 0.40) / 0.012) ** 2) * 0.9
    d = np.minimum(np.minimum(x, 1 - x), np.minimum(y, 1 - y))
    lines = np.clip(lines + np.exp(-((d - 0.04) / 0.014) ** 2), 0, 1)
    col = base + (gold[None, None, :] - base) * lines[..., None]
    return _save(col, path)


def sword_blade(path, size=(256, 1024), seed=29):
    """greatsword blade (geo.blade uv: u across, v from the guard to the tip): orange-red rim, a dark outline ring
    running parallel to the edges and closing before the tip, a yellow core"""
    w, h = size
    rng = np.random.default_rng(seed)
    u = np.linspace(0, 1, w)[None, :]
    core = 1 - np.abs(u - 0.5) * 2                     # 1 on the ridge
    heat = np.clip(core * 0.9 + 0.12 + (_noise(h, w, rng, 4) - 0.5) * 0.18, 0, 1)[..., None]
    red, orange, yellow = np.array([0.86, 0.14, 0.02]), np.array([1.0, 0.48, 0.03]), np.array([1.0, 0.88, 0.25])
    col = np.where(heat < 0.45, red + (orange - red) * (heat / 0.45), orange + (yellow - orange) * ((heat - 0.45) / 0.55))
    img = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    dark = (30, 16, 14)
    xa, xb = w * 0.27, w * 0.73
    ring = [(xa, h * 0.05), (xa, h * 0.70), (w * 0.5, h * 0.86), (xb, h * 0.70), (xb, h * 0.05)]
    d.line(ring + [ring[0]], fill=dark, width=int(w * 0.055), joint="curve")
    arr = np.asarray(img.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    return _save(arr, path)


def grip(path, size=(64, 256)):
    """sword grips / hilts: glowing orange-red with dark wrap rings"""
    w, h = size
    v = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    rings = (np.sin(v * np.pi * 2 * 9) > 0.8).astype(np.float32)
    col = np.array([0.95, 0.30, 0.04])[None, None, :] * (1 - rings[..., None]) + np.array([0.10, 0.05, 0.05])[None, None, :] * rings[..., None]
    return _save(col, path)


def hair_lock(path, size=(64, 256), seed=31):
    """platinum hair strips: fine strand lines along the length"""
    w, h = size
    rng = np.random.default_rng(seed)
    strands = rng.random(w) * 0.16
    strands = np.convolve(strands, np.ones(3) / 3, mode="same")[None, :]
    v = np.linspace(0, 1, h)[:, None]
    base = np.array([0.93, 0.91, 0.86])[None, None, :] * (0.86 + strands[..., None] - 0.06 * v[..., None])
    return _save(base * np.ones((h, w, 1)), path)


def sphere_soft(path, size=128):
    """additive sphere map for FLAT pieces (plates, petals, blades): a whole flat plate has one normal, so it takes ONE
    texel of the sphere map - with a hot spot in it the plate flashes white when it turns that way.  This one is only a
    faint, wide gradient."""
    y, x = np.mgrid[0:size, 0:size]
    u = (x - size / 2) / (size / 2)
    v = (y - size / 2) / (size / 2)
    r2 = u * u + v * v
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    wide = np.clip((u * -0.50 + v * -0.62 + nz * 0.60), 0, 1) ** 3 * 0.11
    rim = np.clip((r2 - 0.75) / 0.25, 0, 1) ** 2 * 0.05
    col = np.stack([wide + rim, wide * 0.92 + rim * 0.7, wide * 0.88 + rim * 0.6], -1)
    col = np.where((r2 <= 1.0)[..., None], col, 0)
    return _save(col, path)
