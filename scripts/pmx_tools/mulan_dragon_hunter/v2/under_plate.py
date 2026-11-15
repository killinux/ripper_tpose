# A plate under a cut-out garment: the skin faces within --reach cm of the garment (inside its height range) are copied,
# pushed --offset cm out along their normals, given a plain dark texture and the skin's own weights (they follow the
# bust physics).  Fills the holes of a lace / strappy top with "plate" instead of skin.
#   python under_plate.py <in.pmx> <out.pmx> --skin <skin material> --over <garment material> [--reach 2.2]
#                         [--offset 0.4] [--material chest_plate] [--color 0.16,0.08,0.22]
import argparse
import copy
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--skin", required=True)
ap.add_argument("--over", required=True)
ap.add_argument("--reach", type=float, default=2.2)
ap.add_argument("--offset", type=float, default=0.4)
ap.add_argument("--margin-y", type=float, default=0.5, help="cm the plate may exceed the garment's height range")
ap.add_argument("--material", default="chest_plate")
ap.add_argument("--color", default="0.16,0.08,0.22")
ap.add_argument("--texture", default="plate_dark.png")
a = ap.parse_args()

M = L.load(a.src)
mf = L.mat_faces(M)
si, oi = L.mat_index(M, a.skin), L.mat_index(M, a.over)
ov = L.mat_vertices(M, oi)
OV = np.array([M.vertices[v].co for v in ov]) * L.UNIT_CM
ylo, yhi = OV[:, 1].min() - a.margin_y, OV[:, 1].max() + a.margin_y
sv = L.mat_vertices(M, si)
SV = np.array([M.vertices[v].co for v in sv]) * L.UNIT_CM
cand = np.where((SV[:, 1] > ylo) & (SV[:, 1] < yhi))[0]
near = np.zeros(len(sv), bool)
for i in range(0, len(cand), 256):
    idx = cand[i:i + 256]
    d = np.linalg.norm(SV[idx][:, None, :] - OV[None, :, :], axis=2).min(1)
    near[idx] = d < a.reach
sel = {sv[i] for i in np.where(near)[0]}
s, n = mf[si]
faces = [f for f in M.faces[s:s + n] if all(v in sel for v in f)]
print("garment y %.1f..%.1f, skin verts near %d, plate faces %d" % (ylo, yhi, len(sel), len(faces)))

here = os.path.dirname(os.path.abspath(a.out))
os.makedirs(os.path.join(here, "textures"), exist_ok=True)
col = np.array([float(x) for x in a.color.split(",")])
tex_path = os.path.join(here, "textures", a.texture)
Image.fromarray(np.tile((col * 255 + 0.5).astype(np.uint8), (64, 64, 1)), "RGB").save(tex_path)
tex = L.add_texture(M, os.path.abspath(tex_path))

new = {}


def dup(v):
    if v not in new:
        src = M.vertices[v]
        nv = copy.deepcopy(src)
        nrm = np.array(src.normal, float)
        nv.co = [float(x) for x in np.array(src.co, float) + nrm * (a.offset / L.UNIT_CM)]
        nv.uv = [0.5, 0.5]
        M.vertices.append(nv)
        new[v] = len(M.vertices) - 1
    return new[v]


plate_faces = [[dup(v) for v in f] for f in faces]
L.new_material(M, a.material, a.material, tex, plate_faces, diffuse=(1, 1, 1, 1), specular=(0.5, 0.4, 0.55),
               shininess=25, ambient=(0.45, 0.4, 0.5), edge=True, edge_color=(0.05, 0.02, 0.08, 1.0), edge_size=0.8,
               toon=0, comment="plate under %s (under_plate.py)" % a.over)
L.save(M, a.out)
print("wrote", a.out)
