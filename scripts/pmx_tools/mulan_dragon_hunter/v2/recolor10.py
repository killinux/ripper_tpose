# v10 recolour: the Nexus mod parts to the in-game 3D look (black-purple plate, orange inlays, orange crystals).
#   python recolor10.py <textures dir> [<mhw png dir with the *_CMM.png masks>]
# Writes <name>_mulan.png next to each texture it knows (assemble2.py picks those up), like recolor2.py.
#   MHW Velkhana (ice white / navy / periwinkle):
#     navy panels (and the white line art drawn inside them) -> orange glow, dark navy = deep orange, lines = yellow;
#     periwinkle / pink gems -> orange crystal; white / grey plate -> smooth dark plate with thin orange rims
#     (recolor2.metal_smooth); beige / brown leather -> near-black brown;
#     the arm atlas: where its CMM mask is full red (the crystal clusters) -> orange crystal ramp;
#     the crown atlas: all of it is crystal -> orange crystal ramp.
#   Skyrim COCO Mulan matelfull.png (dark silver) -> black-purple plate with orange rims.
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import recolor2 as R2  # noqa: E402

r1 = R2.r1
rgb_to_hsv, hsv_to_rgb = r1.rgb_to_hsv, r1.hsv_to_rgb

# stops of the orange crystal ramp (sampled from crystal_orange.png, the procedural crystals' texture)
CRYSTAL = [(0.0, (0.30, 0.06, 0.02)), (0.25, (0.55, 0.17, 0.03)), (0.5, (0.84, 0.44, 0.12)),
           (0.75, (0.96, 0.64, 0.26)), (1.0, (1.0, 0.91, 0.62))]
# orange inlay ramp (tassets.png's flame panels)
INLAY = [(0.0, (0.42, 0.10, 0.02)), (0.35, (0.72, 0.30, 0.05)), (0.7, (0.97, 0.62, 0.20)), (1.0, (1.0, 0.86, 0.50))]


def ramp(t, stops):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t[m] - t0) / (t1 - t0))[:, None]
        out[m] = np.array(c0, np.float32) * (1 - f) + np.array(c1, np.float32) * f
    return out


def norm(x, mask, lo=3, hi=97):
    if mask.sum() < 16:
        return np.clip(x, 0, 1)
    a, b = np.percentile(x[mask], lo), np.percentile(x[mask], hi)
    return np.clip((x - a) / (b - a + 1e-6), 0, 1)


def hue_in(h, lo, hi):
    return (h >= lo) & (h <= hi) if lo <= hi else (h >= lo) | (h <= hi)


def classes(rgb):
    h, s, v = rgb_to_hsv(rgb)
    navy = hue_in(h, 0.55, 0.80) & (s > 0.18) & (v < 0.62)
    gem = hue_in(h, 0.55, 0.98) & (s > 0.22) & (v >= 0.62)
    warm = hue_in(h, 0.02, 0.17) & (s >= 0.12) & (v < 0.8)
    return h, s, v, navy, gem, warm


def rect_mask(shape, rects):
    """rects in texture fractions (u0, v0, u1, v1), v downwards as the image is stored"""
    m = np.zeros(shape, bool)
    hgt, wid = shape
    for u0, v0, u1, v1 in rects or []:
        m[int(v0 * hgt):int(v1 * hgt), int(u0 * wid):int(u1 * wid)] = True
    return m


def velkhana(arr, crystal_mask=None, all_crystal=False, panels="fill", crystal_rects=None):
    """panels: "fill" = navy panels glow orange (the thigh plates' V flames), "lines" = navy turns to the dark plate
    and only the line art drawn on it turns orange.  crystal_rects: atlas rectangles whose ice-white pixels are
    crystal (the greaves' knee spikes; the arm atlas uses its CMM mask instead)."""
    rgb, a = arr[..., :3], arr[..., 3:]
    h, s, v, navy, gem, warm = classes(rgb)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    info = {}
    if all_crystal:
        cm = np.ones(v.shape, bool)
    else:
        cm = np.zeros(v.shape, bool) if crystal_mask is None else crystal_mask & (s < 0.3) & ~navy  # the mask also
        cm |= gem                                                    # covers the navy fan: that stays a panel
        if crystal_rects:
            cm |= rect_mask(v.shape, crystal_rects) & (s < 0.25) & (v > 0.45)
    # panels: navy plus the line art drawn inside it (a dilated navy region)
    panel = (R2.box_blur(navy.astype(np.float32), 4) > 0.35) & ~cm
    # base: smooth dark plate with rims everywhere (recolor2.metal_smooth), then the other classes on top
    plate, _ = R2.metal_smooth(arr, lambda h_, s_, v_: np.ones(v_.shape, bool), base_v=(0.07, 0.27), base_s=0.38,
                               rim_thresh=0.06)
    out = plate[..., :3].copy()
    leather = warm & ~panel & ~cm
    out[leather] = hsv_to_rgb(np.full(int(leather.sum()), 0.05, np.float32), np.full(int(leather.sum()), 0.5, np.float32),
                              (v[leather] * 0.22 + 0.03).astype(np.float32))
    t = norm(lum, panel, 2, 99.5)
    if panels == "fill":
        out[panel] = ramp(t, INLAY)[panel]
    else:
        # dark navy -> the plate's dark base; the light line art (t > ~0.55) -> orange lines
        dark = hsv_to_rgb(np.full(v.shape, R2.PURPLE, np.float32), np.full(v.shape, 0.42, np.float32),
                          (0.06 + 0.10 * t).astype(np.float32))
        k = np.clip((t - 0.5) / 0.2, 0, 1)[..., None]
        mix = dark * (1 - k) + ramp(np.clip((t - 0.5) / 0.5, 0, 1) * 0.8 + 0.2, INLAY) * k
        out[panel] = mix[panel]
    out[cm] = ramp(norm(lum, cm, 2, 99), CRYSTAL)[cm]
    info.update(plate=int((~panel & ~cm & ~leather).sum()), leather=int(leather.sum()), panel=int(panel.sum()),
                crystal=int(cm.sum()))
    return np.concatenate([out, a], -1), info


def coco_metal(arr):
    return R2.metal_smooth(arr, lambda h, s, v: (v > 0.04), base_v=(0.07, 0.30), base_s=0.38, rim_thresh=0.05,
                           rim_width=0.05)


def cmm_crystal(cmm_dir, stem, shape):
    p = os.path.join(cmm_dir, stem + "_CMM.png")
    if not os.path.isfile(p):
        return None
    from PIL import Image
    im = Image.open(p).convert("RGB")
    if im.size != (shape[1], shape[0]):
        im = im.resize((shape[1], shape[0]))
    return np.asarray(im)[..., 0] >= 230


def rules(cmm_dir):
    return [
        ("m_leg085_0010_BML.png", lambda a: velkhana(a, panels="fill")),        # thigh plates: orange V flames
        ("f_leg085_0000_BM.png", lambda a: velkhana(a, panels="lines",         # greaves: black, knee spikes orange
                                                    crystal_rects=[(0.72, 0.6, 0.96, 0.83), (0.6, 0.78, 0.89, 0.96),
                                                                   (0.0, 0.1, 0.41, 0.2)])),
        ("f_body085_0000_BM.png", lambda a: velkhana(a, panels="lines")),
        ("f_wst085_0000_BML.png", lambda a: velkhana(a, all_crystal=True)),
        ("f_arm085_0000_BM.png", lambda a: velkhana(a, panels="lines",
                                                    crystal_mask=cmm_crystal(cmm_dir, "f_arm085_0000", a.shape[:2]))),
        ("f_helm085_0010_BM.png", lambda a: velkhana(a, all_crystal=True)),
        ("matelfull.png", lambda a: coco_metal(a)),
    ]


if __name__ == "__main__":
    folder = sys.argv[1]
    cmm_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "mods", "velkhana_png")   # the mod's converted *_CMM.png
    for name, fn in rules(cmm_dir):
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            print("missing", name)
            continue
        out, info = fn(r1.load(p))
        q = os.path.join(folder, os.path.splitext(name)[0] + "_mulan.png")
        r1.save(out, q)
        print("ok", name, info)
