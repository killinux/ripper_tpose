# Cut a flaring collar / cape off a bodice material: faces above --min-y (cm) that sit more than --gap-cm from the
# donor's skin, plus faces whose texture colour is "blue" (the collar's top), are removed; small leftover islands too.
#   python cut_collar.py <in.pmx> <out.pmx> <material> --skin <skin material> [--min-y 134] [--gap-cm 2.0] [--blue]
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("--skin", required=True)
ap.add_argument("--min-y", type=float, default=134.0)
ap.add_argument("--gap-cm", type=float, default=2.0)
ap.add_argument("--blue", action="store_true")
ap.add_argument("--min-island", type=int, default=30)
a = ap.parse_args()

M = L.load(a.src)
mi, si = L.mat_index(M, a.material), L.mat_index(M, a.skin)
mf = L.mat_faces(M)
s, n = mf[mi]
skin = np.array([M.vertices[v].co for v in L.mat_vertices(M, si)]) * L.UNIT_CM


class _Tree:                       # brute force nearest neighbour (no scipy here)
    def __init__(self, pts):
        self.pts = pts

    def query(self, q):
        d = np.empty(len(q))
        for i in range(0, len(q), 512):
            dd = np.linalg.norm(q[i:i + 512, None, :] - self.pts[None, :, :], axis=2)
            d[i:i + 512] = dd.min(1)
        return d, None


tree = _Tree(skin)

tex = None
if a.blue:
    m = M.materials[mi]
    p = M.textures[m.texture].path
    here = os.path.dirname(os.path.abspath(a.src))
    for cand in (p, os.path.join(here, p), os.path.join(here, "textures", os.path.basename(p))):
        if os.path.isfile(cand):
            p = cand
            break
    tex = np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255
    H, W = tex.shape[:2]


def is_blue(f):
    cols = []
    for v in f:
        u, w = M.vertices[v].uv
        cols.append(tex[int(np.clip((w % 1.0) * H, 0, H - 1)), int(np.clip((u % 1.0) * W, 0, W - 1))])
    c = np.mean(cols, 0)
    mx, mn = c.max(), c.min()
    return bool(c[2] > c[0] * 1.4 and c[2] > c[1] * 1.1 and (mx - mn) / (mx + 1e-6) > 0.3 and mx > 0.25)


faces = M.faces[s:s + n]
cen = np.array([[np.mean([M.vertices[v].co[k] for v in f]) for k in range(3)] for f in faces]) * L.UNIT_CM
dist, _ = tree.query(cen)
drop = np.zeros(n, bool)
drop |= (cen[:, 1] > a.min_y) & (dist > a.gap_cm)
nb = 0
if tex is not None:
    b = np.array([is_blue(f) for f in faces])
    nb = int(b.sum())
    drop |= b
print("faces", n, "far", int(((cen[:, 1] > a.min_y) & (dist > a.gap_cm)).sum()), "blue", nb, "drop", int(drop.sum()))

# islands of the kept faces: drop the small ones
keep_idx = [i for i in range(n) if not drop[i]]
parent = {}


def find(x):
    while parent.get(x, x) != x:
        parent[x] = parent.get(parent[x], parent[x])
        x = parent[x]
    return x


def union(x, y):
    rx, ry = find(x), find(y)
    if rx != ry:
        parent[rx] = ry


pos_key = {}
for i in keep_idx:
    for v in faces[i]:
        k = tuple(np.round(np.array(M.vertices[v].co) * L.UNIT_CM, 2))
        pos_key.setdefault(k, i)
        union(i, pos_key[k])
from collections import Counter  # noqa: E402
roots = Counter(find(i) for i in keep_idx)
small = {r for r, c in roots.items() if c < a.min_island}
for i in keep_idx:
    if find(i) in small:
        drop[i] = True
print("islands", len(roots), "small dropped", len(small), "kept faces", int((~drop).sum()))

new_faces = [f for i, f in enumerate(faces) if not drop[i]]
M.faces[s:s + n] = new_faces
M.materials[mi].vertex_count = len(new_faces) * 3
L.save(M, a.out)
print("wrote", a.out)
