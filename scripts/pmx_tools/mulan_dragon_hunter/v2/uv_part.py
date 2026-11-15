# Pull the faces of a material whose UV centroid lies inside a rectangle into a NEW material (same texture), e.g. the
# dragon-head ornament that shares the pauldron's texture atlas.  Prints the 3D extent per connected piece.
#   python uv_part.py <in.pmx> <out.pmx> <material> <u0> <v0> <u1> <v1> [--name dragon_head_src] [--keep-rest]
import argparse
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("u0", type=float)
ap.add_argument("v0", type=float)
ap.add_argument("u1", type=float)
ap.add_argument("v1", type=float)
ap.add_argument("--name", default="uv_part")
ap.add_argument("--largest", action="store_true", help="keep only the largest connected piece")
a = ap.parse_args()

M = L.load(a.src)
mi = L.mat_index(M, a.material)
s, n = L.mat_faces(M)[mi]
faces = M.faces[s:s + n]
inside, rest = [], []
for f in faces:
    uv = np.mean([M.vertices[v].uv for v in f], 0)
    (inside if a.u0 <= uv[0] <= a.u1 and a.v0 <= uv[1] <= a.v1 else rest).append(f)
print("faces in the rect", len(inside), "of", n)
if inside:
    P = np.array([M.vertices[v].co for f in inside for v in f]) * L.UNIT_CM
    print("3D bbox cm", P.min(0).round(1), P.max(0).round(1))
    # connected pieces by rounded position
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    key = {}
    for i, f in enumerate(inside):
        for v in f:
            k = tuple(np.round(np.array(M.vertices[v].co) * L.UNIT_CM, 1))
            if k in key:
                rx, ry = find(i), find(key[k])
                if rx != ry:
                    parent[rx] = ry
            else:
                key[k] = i
    groups = Counter(find(i) for i in range(len(inside)))
    for r, c in groups.most_common(6):
        Q = np.array([M.vertices[v].co for i, f in enumerate(inside) if find(i) == r for v in f]) * L.UNIT_CM
        print("  piece %d faces, bbox %s %s" % (c, Q.min(0).round(1), Q.max(0).round(1)))
    if a.largest:
        big = groups.most_common(1)[0][0]
        rest += [f for i, f in enumerate(inside) if find(i) != big]
        inside = [f for i, f in enumerate(inside) if find(i) == big]
        print("kept the largest piece:", len(inside), "faces")
M.faces[s:s + n] = rest
M.materials[mi].vertex_count = len(rest) * 3
import copy  # noqa: E402
m = copy.deepcopy(M.materials[mi])
m.name = m.name_e = a.name
m.vertex_count = len(inside) * 3
M.materials.append(m)
M.faces.extend(inside)
L.save(M, a.out)
print("wrote", a.out)
