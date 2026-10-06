"""Where are the big overhanging rocks of a level?  For every large rock / cliff placement: its PSKX points and
normals in world space, the landscape height under each point; score = points more than 8 m above the ground whose
normal faces down.  Prints the best placements with the nearest ruin walls.
  python find_overhangs.py placements.json <umodel assets dir>"""
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

D = json.load(open(sys.argv[1], encoding="utf-8"))
ASSETS = sys.argv[2]

# ---- landscape height grid (UE cm), 1 sample per quad corner
total = max(max(c["section"]) + c["size"] for c in D["landscape"])
H = np.full((total + 1, total + 1), np.nan, dtype=np.float64)
cell_png = {}
for dp, _d, files in os.walk(ASSETS):
    low = dp.replace(os.sep, "/").lower()
    if "/_generated_/" in low:
        cell = low.split("/_generated_/", 1)[1].split("/", 1)[0]
        for f in files:
            cell_png[(cell, f.lower()[:-4])] = os.path.join(dp, f)
for c in D["landscape"]:
    p = cell_png.get((c["cell"].lower(), (c["heightmap"] or "").lower()))
    if not p:
        continue
    a = np.asarray(Image.open(p).convert("RGBA")).astype(np.float64)
    h16 = a[..., 0] * 256 + a[..., 1]
    n, sq, ns = c["size"], c["sub"], c["nsub"]
    idx = np.arange(n + 1)
    s = np.minimum(idx // sq, ns - 1)
    ti = s * (sq + 1) + (idx - s * sq)
    bx, by = int(c["hsb"][2] * a.shape[1]), int(c["hsb"][3] * a.shape[0])
    g = h16[(by + ti)[:, None], (bx + ti)[None, :]]
    m = c["m"]
    sx, sy = c["section"]
    H[sy:sy + n + 1, sx:sx + n + 1] = m[14] + (g - 32768) / 128.0 * m[10]
SCALE = 100.0


def ground(x, y):
    i = np.clip(np.round(y / SCALE).astype(int), 0, total)
    j = np.clip(np.round(x / SCALE).astype(int), 0, total)
    return H[i, j]


mesh_file = {}
for dp, _d, files in os.walk(ASSETS):
    for f in files:
        if f.lower().endswith(".pskx"):
            rel = os.path.relpath(os.path.join(dp, f), ASSETS).replace(os.sep, "/")
            mesh_file["/game/" + rel[:-5].lower()] = os.path.join(dp, f)
_cache = {}


def points(path):
    if path not in _cache:
        data = open(path, "rb").read()
        o, pts, nrm = 0, None, None
        while o < len(data):
            cid = data[o:o + 20].split(b"\0")[0]
            size, count = struct.unpack_from("<ii", data, o + 24)
            if cid == b"PNTS0000":
                pts = np.frombuffer(data, "<f4", count * 3, o + 32).reshape(-1, 3).astype(np.float64)
            elif cid == b"VTXNORMS":
                nrm = np.frombuffer(data, "<f4", count * 3, o + 32).reshape(-1, 3).astype(np.float64)
            o += 32 + size * count
        # PSK is Y-mirrored: back to UE local
        pts[:, 1] *= -1
        if nrm is not None:
            nrm[:, 1] *= -1
        _cache[path] = (pts[::3], nrm[::3] if nrm is not None else None)
    return _cache[path]


rows = []
for it in D["items"]:
    if it["kind"] == "foliage":
        continue
    name = it["mesh"].rsplit("/", 1)[-1]
    if not any(k in name.lower() for k in ("cliff", "rock", "boulder", "outcrop", "formation", "assembly", "cave")):
        continue
    path = mesh_file.get(it["mesh"].lower())
    if not path:
        continue
    pts, nrm = points(path)
    if nrm is None or len(pts) == 0:
        continue
    M = np.array(it["m"]).reshape(4, 4)
    w = pts @ M[:3, :3] + M[3, :3]
    ext = w.max(0) - w.min(0)
    if max(ext[0], ext[1]) < 1500:
        continue
    nw = nrm @ M[:3, :3]
    nw /= np.linalg.norm(nw, axis=1, keepdims=True) + 1e-9
    g = ground(w[:, 0], w[:, 1])
    over = (w[:, 2] - g > 800) & (nw[:, 2] < -0.6)
    score = int(over.sum())
    if score:
        c = w[over].mean(0)
        rows.append((score, name, tuple(int(v) for v in it["m"][12:15]), tuple(int(v) for v in c),
                     float((w[over, 2] - g[over]).mean() / 100)))
rows.sort(reverse=True)
walls = [tuple(it["m"][12:14]) for it in D["items"] if "HistoricRuin" in it["mesh"]]
walls = np.array(walls) if walls else np.zeros((0, 2))
print("score  mesh                                  placement            overhang centre       height  ruins<40m")
for score, name, p, c, hgt in rows[:40]:
    near = int((np.hypot(walls[:, 0] - c[0], walls[:, 1] - c[1]) < 4000).sum()) if len(walls) else 0
    print("%5d  %-36s %-20s %-21s %5.1fm %4d" % (score, name[:36], p[:2], c, hgt, near))
