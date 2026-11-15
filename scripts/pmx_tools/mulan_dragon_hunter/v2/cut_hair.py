# Shorten long hair: drop the faces of the given materials whose centroid is below --y (cm) plus a per-strand jitter
# (hash of the face's x/z so neighbouring strands end at slightly different heights -> a ragged, natural end).
#   python cut_hair.py <in.pmx> <out.pmx> --materials m1,m2 --y 92 [--jitter 8] [--seed 3]
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--materials", required=True)
ap.add_argument("--y", type=float, default=92.0)
ap.add_argument("--jitter", type=float, default=8.0)
ap.add_argument("--seed", type=int, default=3)
a = ap.parse_args()

M = L.load(a.src)
rng = np.random.default_rng(a.seed)
total_drop = 0
for name in a.materials.split(","):
    mi = L.mat_index(M, name)
    s, n = L.mat_faces(M)[mi]
    faces = M.faces[s:s + n]
    keep = []
    for f in faces:
        P = np.array([M.vertices[v].co for v in f]) * L.UNIT_CM
        c = P.mean(0)
        key = (int(round(c[0] / 2.5)) * 73856093 ^ int(round(c[2] / 2.5)) * 19349663) & 0xFFFF
        thr = a.y + (key / 65535.0) * a.jitter
        if c[1] >= thr:
            keep.append(f)
    total_drop += n - len(keep)
    M.faces[s:s + n] = keep
    M.materials[mi].vertex_count = len(keep) * 3
    print(name, "faces", n, "->", len(keep))
L.save(M, a.out)
print("wrote", a.out, "dropped", total_drop)
