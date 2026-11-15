# Drop the faces of a material whose centroid is above --max-y / below --min-y (cm), e.g. to keep only the skirt of a
# bodice+skirt part.   python cut_y.py <in.pmx> <out.pmx> <material> [--max-y 113] [--min-y -1e9]
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("--max-y", type=float, default=1e9)
ap.add_argument("--min-y", type=float, default=-1e9)
ap.add_argument("--axis", default="y", choices=["x", "y", "z"], help="cut along this axis instead (z: front -, back +)")
a = ap.parse_args()
M = L.load(a.src)
mi = L.mat_index(M, a.material)
s, n = L.mat_faces(M)[mi]
faces = M.faces[s:s + n]
k_ax = "xyz".index(a.axis)
cy = np.array([np.mean([M.vertices[v].co[k_ax] for v in f]) for f in faces]) * L.UNIT_CM
h, e = np.histogram(cy, bins=12)
print("centroid y histogram:", " ".join("%.0f:%d" % (lo, c) for lo, c in zip(e[:-1], h)))
keep = [f for f, y in zip(faces, cy) if a.min_y <= y <= a.max_y]
print("faces", n, "->", len(keep))
M.faces[s:s + n] = keep
M.materials[mi].vertex_count = len(keep) * 3
L.save(M, a.out)
print("wrote", a.out)
