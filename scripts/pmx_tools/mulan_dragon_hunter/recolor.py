# Recolour the textures of the 水晶猎龙者 composite (in place in the given folder):
#   hair     -> platinum blonde (luminance mapped onto a blonde ramp; alpha kept)
#   armor    -> gold trims -> glowing orange crystal, dark cloth -> black-purple dragon scale, skin untouched
#   weapons  -> gold -> orange, steel blade -> dark with an orange core
#   python recolor.py <textures dir> [--dry]  (writes <name>_mulan.png next to the originals and prints them)
import colorsys
import os
import sys

import numpy as np
from PIL import Image


def load(path):
    im = Image.open(path).convert("RGBA")
    return np.asarray(im).astype(np.float32) / 255.0


def save(arr, path):
    Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(path)


def rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn + 1e-9
    h = np.zeros_like(mx)
    m = mx == r
    h[m] = ((g - b) / d)[m] % 6
    m = mx == g
    h[m] = ((b - r) / d)[m] + 2
    m = mx == b
    h[m] = ((r - g) / d)[m] + 4
    h = (h / 6) % 1.0
    s = np.where(mx > 1e-6, (mx - mn) / (mx + 1e-9), 0)
    return h, s, mx


def hsv_to_rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    out = np.zeros(h.shape + (3,), np.float32)
    for k, (a, b, c) in enumerate(((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))):
        m = i == k
        out[m, 0], out[m, 1], out[m, 2] = a[m], b[m], c[m]
    return out


def blonde_hair(arr):
    """Dark hair strands -> platinum blonde: luminance drives a ramp from warm brown shadow to near-white highlight."""
    rgb, a = arr[..., :3], arr[..., 3:]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    # stretch the dark hair's range (most of it 0.05-0.35) to 0..1
    lo, hi = np.percentile(lum[a[..., 0] > 0.5], 3), np.percentile(lum[a[..., 0] > 0.5], 97)
    t = np.clip((lum - lo) / (hi - lo + 1e-6), 0, 1) ** 0.45
    shadow = np.array([0.68, 0.58, 0.44], np.float32)     # warm shadow (strand depth)
    mid = np.array([0.95, 0.90, 0.78], np.float32)        # pale platinum blonde
    light = np.array([1.00, 1.00, 0.97], np.float32)      # highlight
    t3 = t[..., None]
    col = np.where(t3 < 0.5, shadow + (mid - shadow) * (t3 / 0.5), mid + (light - mid) * ((t3 - 0.5) / 0.5))
    return np.concatenate([col, a], -1)


def dragon_armor(arr, gold_hue=(0.07, 0.17), keep_skin=True):
    """Gold / yellow metal -> orange crystal (hue 0.05, strong, brighter); dark fabric -> black-purple scale; skin kept.
    Skin is told apart by hue (0.02-0.08) with moderate saturation and high value."""
    rgb, a = arr[..., :3].copy(), arr[..., 3:]
    h, s, v = rgb_to_hsv(rgb)
    gold = (h > gold_hue[0]) & (h < gold_hue[1]) & (s > 0.18) & (v > 0.25)
    skin = (h >= 0.0) & (h < 0.09) & (s > 0.12) & (s < 0.55) & (v > 0.45) & ~gold
    dark = (v < 0.42) & ~gold & ~skin
    # gold -> orange crystal: hue 0.045-0.09 (red-orange shadows, yellow-orange highlights), saturated, glowing
    h2, s2, v2 = h.copy(), s.copy(), v.copy()
    h2[gold] = 0.035 + np.clip((v[gold] - 0.25) / 0.75, 0, 1) * 0.05
    s2[gold] = np.clip(0.8 + s[gold] * 0.3, 0, 1)
    v2[gold] = np.clip(v[gold] ** 0.55 * 1.35, 0, 1)
    # dark cloth -> black-purple: hue 0.78, a little saturation, darker
    h2[dark] = 0.78
    s2[dark] = np.clip(s[dark] * 0.5 + 0.28, 0, 1)
    v2[dark] = np.clip(v[dark] * 0.7, 0, 1)
    # grey metal plates (the crown, pauldrons: low saturation, mid value) -> dark glossy purple
    metal = (s < 0.14) & (v >= 0.42) & (v < 0.9) & ~gold & ~skin
    h2[metal] = 0.76
    s2[metal] = np.clip(0.35 + s[metal], 0, 1)
    v2[metal] = np.clip(v[metal] * 0.55, 0, 1)
    out = hsv_to_rgb(h2, s2, v2)
    if keep_skin:
        out[skin] = rgb[skin]
    return np.concatenate([out, a], -1), {"gold": int(gold.sum()), "dark": int(dark.sum()), "metal": int(metal.sum()),
                                          "skin": int(skin.sum())}


def crystal_blade(arr):
    """Weapons: gold -> orange; grey steel (low saturation, mid value) -> dark purple-black with the brightest
    parts glowing orange (crystal edge)."""
    rgb, a = arr[..., :3].copy(), arr[..., 3:]
    h, s, v = rgb_to_hsv(rgb)
    gold = (h > 0.07) & (h < 0.17) & (s > 0.28) & (v > 0.25)
    steel = (s < 0.22) & (v > 0.12) & ~gold
    h2, s2, v2 = h.copy(), s.copy(), v.copy()
    h2[gold] = 0.055
    s2[gold] = np.clip(s[gold] * 1.3 + 0.2, 0, 1)
    v2[gold] = np.clip(v[gold] * 1.1, 0, 1)
    bright = steel & (v > 0.62)
    body = steel & ~bright
    h2[body] = 0.78
    s2[body] = 0.35
    v2[body] = np.clip(v[body] * 0.45, 0, 1)
    h2[bright] = 0.06
    s2[bright] = 0.9
    v2[bright] = np.clip(v[bright] * 1.05, 0, 1)
    out = hsv_to_rgb(h2, s2, v2)
    return np.concatenate([out, a], -1), {"gold": int(gold.sum()), "steel": int(steel.sum()), "bright": int(bright.sum())}


def pink_eyes(arr):
    """Inase's blue iris -> the skin's pink-violet (hue 0.55-0.70 and saturated -> hue 0.92), sclera / skin untouched."""
    rgb, a = arr[..., :3].copy(), arr[..., 3:]
    h, s, v = rgb_to_hsv(rgb)
    # the iris is a low-saturation blue-grey disc (s 0.08-0.3) with a saturated ring; the sclera is near white (s < 0.06)
    iris = (h > 0.45) & (h < 0.78) & (s > 0.07) & (v > 0.15)
    h2, s2, v2 = h.copy(), s.copy(), v.copy()
    h2[iris] = 0.93
    s2[iris] = np.clip(s[iris] * 1.6 + 0.3, 0, 1)
    v2[iris] = np.clip(v[iris] * 1.0, 0, 1)
    out = hsv_to_rgb(h2, s2, v2)
    return np.concatenate([out, a], -1), {"iris": int(iris.sum())}


RULES = [
    ("MI_Hair_New_Ponytail_4_baked.png", "hair"),
    ("MI_EVE_HR_01_TypeA_baked.png", "hair"),
    ("pc_a08_hd_outfit1_body1__pmx_diffuse.png", "armor"),
    ("pc_a08_hd_outfit1_body2__pmx_diffuse.png", "armor"),
    ("wp_a_08_hd__pmx_diffuse.png", "weapon"),
    ("pc_a08_hd_head_eye_baked.png", "eyes"),
]

if __name__ == "__main__":
    folder = sys.argv[1]
    for name, kind in RULES:
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            print("missing", name)
            continue
        arr = load(p)
        if kind == "hair":
            out, info = blonde_hair(arr), {}
        elif kind == "armor":
            out, info = dragon_armor(arr)
        elif kind == "eyes":
            out, info = pink_eyes(arr)
        else:
            out, info = crystal_blade(arr)
        q = os.path.join(folder, os.path.splitext(name)[0] + "_mulan.png")
        save(out, q)
        print("ok", name, "->", os.path.basename(q), info)
