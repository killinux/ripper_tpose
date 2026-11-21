# Shaded orthographic maps of a PMX material with a cm grid - the canvas the armour outlines are designed on.
#   python bodymap.py <pmx> <material[,material...]> <out prefix> <view front|back|left|right> <x0> <x1> <y0> <y1> [px_per_cm]
# front: image x = model x (model's left on the image right, as a viewer facing her sees it mirrored: +x drawn on the RIGHT)
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2"))
import pmxlib as L  # noqa: E402

pmx_path, mats, prefix, view = sys.argv[1:5]
x0, x1, y0, y1 = map(float, sys.argv[5:9])
ppc = float(sys.argv[9]) if len(sys.argv) > 9 else 12.0
M = L.load(os.path.abspath(pmx_path))
V = np.array([v.co for v in M.vertices]) * L.UNIT_CM
mf = L.mat_faces(M)
F = []
for name in mats.split(","):
    s, n = mf[L.mat_index(M, name)]
    F += M.faces[s:s + n]
F = np.array(F)
# view axes: (h, v, depth) with larger depth = nearer to the camera
if view == "front":
    H, D = V[:, 0], -V[:, 2]
elif view == "back":
    H, D = -V[:, 0], V[:, 2]
elif view == "left":      # camera on the model's left (+x), looking towards -x: image right = back (+z)
    H, D = V[:, 2], V[:, 0]
else:
    H, D = -V[:, 2], -V[:, 0]
Y = V[:, 1]
W_, H_ = int((x1 - x0) * ppc), int((y1 - y0) * ppc)
px = (H - x0) * ppc
py = (y1 - Y) * ppc
zbuf = np.full((H_, W_), -1e9, np.float32)
shade = np.zeros((H_, W_), np.float32)
P3 = np.stack([H, Y, D], 1)
light = np.array([-0.35, 0.45, 0.82])
light /= np.linalg.norm(light)
for f in F:
    a, b, c = f
    xs, ys = px[[a, b, c]], py[[a, b, c]]
    if xs.max() < 0 or xs.min() >= W_ or ys.max() < 0 or ys.min() >= H_:
        continue
    n = np.cross(P3[b] - P3[a], P3[c] - P3[a])
    ln = np.linalg.norm(n)
    if ln < 1e-12:
        continue
    n /= ln
    if n[2] < 0:
        n = -n
    ix0, ix1 = max(int(np.floor(xs.min())), 0), min(int(np.ceil(xs.max())), W_ - 1)
    iy0, iy1 = max(int(np.floor(ys.min())), 0), min(int(np.ceil(ys.max())), H_ - 1)
    if ix1 < ix0 or iy1 < iy0:
        continue
    gx, gy = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
    den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
    if abs(den) < 1e-9:
        continue
    w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
    w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
    w2 = 1 - w0 - w1
    inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    if not inside.any():
        continue
    dep = w0 * D[a] + w1 * D[b] + w2 * D[c]
    sub = zbuf[iy0:iy1 + 1, ix0:ix1 + 1]
    upd = inside & (dep > sub)
    sub[upd] = dep[upd]
    shade[iy0:iy1 + 1, ix0:ix1 + 1][upd] = 0.25 + 0.75 * max(float(np.dot(n, light)), 0.0)
img = np.full((H_, W_, 3), 40, np.uint8)
hit = zbuf > -1e8
g = (shade * 235).clip(0, 255).astype(np.uint8)
img[hit] = np.stack([g, g, g], -1)[hit]
im = Image.fromarray(img, "RGB")
d = ImageDraw.Draw(im)
font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 13)
for yy in range(int(np.ceil(y0)), int(y1) + 1):
    if yy % 5 == 0:
        r = (y1 - yy) * ppc
        d.line([(0, r), (W_, r)], fill=(255, 80, 80) if yy % 10 == 0 else (120, 60, 60), width=1)
        d.text((2, r - 13), str(yy), fill=(255, 220, 120), font=font)
for xx in range(int(np.ceil(x0)), int(x1) + 1):
    if xx % 5 == 0:
        c = (xx - x0) * ppc
        d.line([(c, 0), (c, H_)], fill=(80, 160, 255) if xx % 10 == 0 else (50, 80, 120), width=1)
        d.text((c + 2, 2), str(xx), fill=(160, 220, 255), font=font)
out = "%s_%s.png" % (prefix, view)
im.save(out)
np.save("%s_%s_depth.npy" % (prefix, view), zbuf)
print("wrote", out, im.size)
