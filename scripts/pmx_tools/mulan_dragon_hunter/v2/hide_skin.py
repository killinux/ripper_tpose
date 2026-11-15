# Remove skin faces that are covered by rigid armour (a full-armour model does not need legs under plate greaves):
# faces of the skin material whose centroid is below --below-y (cm) are dropped.
#   python hide_skin.py <in.pmx> <out.pmx> --skin pc_a01_nk_body --below-y 99
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--skin", default="pc_a01_nk_body")
ap.add_argument("--below-y", type=float, default=99.0)
a = ap.parse_args()
M = L.load(a.src)
mi = L.mat_index(M, a.skin)
s, n = L.mat_faces(M)[mi]
faces = M.faces[s:s + n]
keep = [f for f in faces if np.mean([M.vertices[v].co[1] for v in f]) * L.UNIT_CM >= a.below_y]
M.faces[s:s + n] = keep
M.materials[mi].vertex_count = len(keep) * 3
L.save(M, a.out)
print("skin faces", n, "->", len(keep), "(dropped below y %.0f cm)" % a.below_y)
