# v2 recolour of the 水晶猎龙者 composite textures (in place: writes <name>_mulan.png next to each original).
#   python recolor2.py <textures dir>
# Rules by texture: Eve hair -> platinum; a08 crown -> v1 dragon armour rule; Miri pauldrons gold -> dark purple with
# orange highlights; Miul claw red -> orange; Bel white/navy/cyan -> black-purple / purple / orange; Sanyaa bodice
# lace alpha filled, blue -> purple; pendant blue -> pink; sword hilt -> v1 rule; eyes -> pink.
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # ../recolor.py (v1 rules)
import recolor as r1  # noqa: E402

rgb_to_hsv, hsv_to_rgb = r1.rgb_to_hsv, r1.hsv_to_rgb


def platinum_hair(arr):
    rgb, a = arr[..., :3], arr[..., 3:]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    m = a[..., 0] > 0.5
    lo, hi = np.percentile(lum[m], 3), np.percentile(lum[m], 97)
    t = np.clip((lum - lo) / (hi - lo + 1e-6), 0, 1) ** 0.5
    shadow = np.array([0.72, 0.66, 0.58], np.float32)     # v4: whiter platinum, less khaki
    mid = np.array([0.97, 0.95, 0.90], np.float32)
    light = np.array([1.00, 1.00, 0.98], np.float32)
    t3 = t[..., None]
    col = np.where(t3 < 0.5, shadow + (mid - shadow) * (t3 / 0.5), mid + (light - mid) * ((t3 - 0.5) / 0.5))
    return np.concatenate([col, a], -1), {}


def remap(arr, rules, fill_alpha=False):
    """rules: list of (mask_fn(h,s,v) -> bool array, (hue | None, s_fn, v_fn)); first matching rule wins"""
    rgb, a = arr[..., :3].copy(), arr[..., 3:].copy()
    h, s, v = rgb_to_hsv(rgb)
    h2, s2, v2 = h.copy(), s.copy(), v.copy()
    done = np.zeros(h.shape, bool)
    info = {}
    for name, mask_fn, (hue, s_fn, v_fn) in rules:
        m = mask_fn(h, s, v) & ~done
        if hue is not None:
            h2[m] = hue
        s2[m] = np.clip(s_fn(s[m], v[m]), 0, 1)
        v2[m] = np.clip(v_fn(s[m], v[m]), 0, 1)
        done |= m
        info[name] = int(m.sum())
    out = hsv_to_rgb(h2, s2, v2)
    if fill_alpha:
        a[:] = 1.0
    return np.concatenate([out, a], -1), info


def hue_in(lo, hi):
    if lo <= hi:
        return lambda h: (h >= lo) & (h <= hi)
    return lambda h: (h >= lo) | (h <= hi)


PURPLE = 0.78
ORANGE = 0.06

# Miri's gold dragon scales: the brightest gold (v > 0.87, ~1/4) -> orange crystal, the rest -> dark purple metal; red -> orange-red
MIRI = [
    ("gold_bright", lambda h, s, v: hue_in(0.07, 0.17)(h) & (s > 0.3) & (v > 0.87), (ORANGE, lambda s, v: 0.95 + 0 * s, lambda s, v: np.clip(v * 1.05, 0, 1))),
    ("gold_dark", lambda h, s, v: hue_in(0.07, 0.17)(h) & (s > 0.3), (PURPLE, lambda s, v: 0.45 + 0 * s, lambda s, v: v * 0.26)),
    ("red", lambda h, s, v: hue_in(0.93, 0.05)(h) & (s > 0.4) & (v > 0.2), (0.04, lambda s, v: np.clip(s * 1.1, 0, 1), lambda s, v: np.clip(v * 1.15, 0, 1))),
    ("grey", lambda h, s, v: (s < 0.2) & (v > 0.35), (PURPLE, lambda s, v: 0.3 + s, lambda s, v: v * 0.6)),
]
# Miul's claw: red accents -> orange, mid grey -> purple tint
MIUL = [
    ("red", lambda h, s, v: hue_in(0.93, 0.06)(h) & (s > 0.35) & (v > 0.15), (ORANGE, lambda s, v: np.clip(s * 1.2 + 0.1, 0, 1), lambda s, v: np.clip(v * 1.3, 0, 1))),
    ("grey", lambda h, s, v: (s < 0.2) & (v > 0.3), (PURPLE, lambda s, v: 0.3 + s, lambda s, v: v * 0.8)),
]
# Bel's white shark set: white cloth / plate -> black-purple, navy -> purple, cyan -> orange
BEL = [
    ("cyan", lambda h, s, v: hue_in(0.40, 0.56)(h) & (s > 0.3) & (v > 0.2), (ORANGE, lambda s, v: 0.95 + 0 * s, lambda s, v: np.clip(v * 1.1, 0, 1))),
    ("navy", lambda h, s, v: hue_in(0.56, 0.74)(h) & (s > 0.22), (PURPLE, lambda s, v: np.clip(s * 0.9 + 0.1, 0, 1), lambda s, v: v * 0.7)),
    ("white", lambda h, s, v: (s < 0.22) & (v > 0.4), (PURPLE, lambda s, v: 0.42 + 0 * s, lambda s, v: v * 0.2 + 0.03)),
    ("grey", lambda h, s, v: (s < 0.22) & (v > 0.18), (PURPLE, lambda s, v: 0.4 + 0 * s, lambda s, v: v * 0.45)),
]
# Sanyaa's bodice: blue motifs -> purple; everything else stays black
SANYAA = [
    ("blue", lambda h, s, v: hue_in(0.52, 0.74)(h) & (s > 0.3), (ORANGE, lambda s, v: 0.95 + 0 * s, lambda s, v: np.clip(v * 1.3, 0, 1))),   # v8: orange trim like the game
]
# her pendant: blue gem -> pink
PENDANT = [
    ("blue", lambda h, s, v: hue_in(0.50, 0.75)(h) & (s > 0.25), (0.92, lambda s, v: np.clip(s * 1.4 + 0.3, 0, 1), lambda s, v: np.clip(v * 1.2, 0, 1))),
]

# Miri's bodice/skirt texture (the skirt part only is used): red cloth -> black-purple scale, gold trim -> orange, black stays
MIRI_SKIRT = [
    ("gold", lambda h, s, v: hue_in(0.07, 0.17)(h) & (s > 0.3) & (v > 0.3), (ORANGE, lambda s, v: 0.95 + 0 * s, lambda s, v: np.clip(v * 1.05, 0, 1))),
    ("red", lambda h, s, v: hue_in(0.9, 0.06)(h) & (s > 0.3) & (v > 0.12), (PURPLE, lambda s, v: 0.38 + 0 * s, lambda s, v: v * 0.2 + 0.02)),
    ("grey", lambda h, s, v: (s < 0.2) & (v > 0.35), (PURPLE, lambda s, v: 0.3 + s, lambda s, v: v * 0.5)),
]

def box_blur(x, r):
    """mean over a (2r+1)^2 window, edges clamped (numpy only)"""
    p = np.pad(x, r, mode="edge").astype(np.float64)
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    n = 2 * r + 1
    h, w = x.shape
    out = c[n:n + h, n:n + w] - c[:h, n:n + w] - c[n:n + h, :w] + c[:h, :w]
    return (out / (n * n)).astype(np.float32)


def metal_smooth(arr, mask_fn, base_hue=PURPLE, base_s=0.45, base_v=(0.10, 0.34), rim_hue=ORANGE, rim_thresh=0.05,
                 rim_width=0.06, blur=6, blur_hp=14, keep_fn=None, keep_rules=None):
    """v5 'sharp metal': inside mask, the base is a dark metal whose brightness follows the BLURRED luminance (the
    scale shading survives, the speckle does not) and only the crisp bright rims (high-pass over a wider blur) get
    the accent colour as clean lines.  keep_rules: ordinary remap rules applied first outside the mask."""
    rgb, a = arr[..., :3].copy(), arr[..., 3:].copy()
    h, s, v = rgb_to_hsv(rgb)
    m = mask_fn(h, s, v)
    vb = box_blur(v, blur)
    hp = v - box_blur(v, blur_hp)
    rim = np.clip((hp - rim_thresh) / rim_width, 0, 1) * np.clip((v - 0.55) / 0.25, 0, 1)
    base = hsv_to_rgb(np.full_like(v, base_hue), np.full_like(v, base_s), np.clip(base_v[0] + (base_v[1] - base_v[0]) * np.clip(vb, 0, 1) ** 1.4, 0, 1))
    acc = hsv_to_rgb(np.full_like(v, rim_hue), np.full_like(v, 0.95), np.clip(0.75 + 0.25 * v, 0, 1))
    metal = base * (1 - rim[..., None]) + acc * rim[..., None]
    out = rgb.copy()
    info = {"metal": int(m.sum()), "rim": int((rim > 0.5).sum())}
    if keep_rules:
        o2, i2 = remap(arr, keep_rules)
        out = o2[..., :3]
        info.update(i2)
    out[m] = metal[m]
    return np.concatenate([out, a], -1), info


# Vindictus (Defying Fate) Fiona PCF_067 plate greaves: steel -> black-purple plate, leather straps -> dark orange
PLATE_067 = [
    ("steel", lambda h, s, v: (s < 0.25) & (v > 0.45), (PURPLE, lambda s, v: 0.42 + 0 * s, lambda s, v: v * 0.22 + 0.03)),
    ("steel_dark", lambda h, s, v: (s < 0.25) & (v > 0.2), (PURPLE, lambda s, v: 0.4 + 0 * s, lambda s, v: v * 0.45)),
    ("leather", lambda h, s, v: hue_in(0.03, 0.12)(h) & (s > 0.3) & (v > 0.15), (ORANGE, lambda s, v: np.clip(s * 1.1, 0, 1), lambda s, v: v * 0.85)),
]

RULES = [
    # v5 sharp metal: smooth dark base + crisp orange rims (no speckle)
    ("MI_PCF_067_foot_baked.png", lambda a: metal_smooth(a, lambda h, s, v: (s < 0.25) & (v > 0.2), base_v=(0.07, 0.27),
                                                          base_s=0.38, rim_thresh=0.06, keep_rules=[PLATE_067[2]])),
    # v7 (the in-game 3D look): PCF_067 plate trousers like the greaves; Miul's spiked arm guard red -> orange
    ("MI_PCF_067_lower_baked.png", lambda a: metal_smooth(a, lambda h, s, v: (s < 0.25) & (v > 0.2), base_v=(0.07, 0.27),
                                                           base_s=0.38, rim_thresh=0.06, keep_rules=[PLATE_067[2]])),
    ("pc_female_devilhunter_upper_metal_baked.png", lambda a: remap(a, MIUL)),
    ("pc_female_dragon_rises_upper_baked.png", lambda a: remap(a, MIRI_SKIRT)),
    ("MI_Hair_New_Ponytail_4_baked.png", lambda a: platinum_hair(a)),
    ("MI_EVE_HR_01_TypeA_baked.png", lambda a: platinum_hair(a)),
    ("pc_a08_hd_outfit1_body2__pmx_diffuse.png", lambda a: r1.dragon_armor(a)),
    ("pc_female_dragon_rises_upper_metal_baked.png", lambda a: metal_smooth(a, lambda h, s, v: hue_in(0.07, 0.17)(h) & (s > 0.3),
                                                                             base_s=0.4, base_v=(0.08, 0.3), keep_rules=MIRI[2:])),
    ("pc_female_devilhunter_hand_metal_baked.png", lambda a: remap(a, MIUL)),
    ("pc_female_white_shark_foot_baked.png", lambda a: remap(a, BEL)),
    ("pc_female_white_shark_foot_metal_baked.png", lambda a: remap(a, BEL)),
    ("pc_female_white_shark_hand_metal_baked.png", lambda a: remap(a, BEL)),
    ("pc_female_white_shark_lower_baked.png", lambda a: remap(a, BEL)),
    ("pc_female_darknight_onepiece_baked.png", lambda a: remap(a, SANYAA, fill_alpha=True)),
    ("pc_female_darknight_onepiece_metal_baked.png", lambda a: remap(a, PENDANT)),
    ("wp_a_08_hd__pmx_diffuse.png", lambda a: r1.crystal_blade(a)),
    ("pc_a08_hd_head_eye_baked.png", lambda a: r1.pink_eyes(a)),
]

if __name__ == "__main__":
    folder = sys.argv[1]
    for name, fn in RULES:
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            print("missing", name)
            continue
        out, info = fn(r1.load(p))
        q = os.path.join(folder, os.path.splitext(name)[0] + "_mulan.png")
        r1.save(out, q)
        print("ok", name, info)
