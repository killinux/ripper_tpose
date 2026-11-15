# List a PMX's materials: index, name, faces, vertex count, bbox in cm, texture.
#   python probe_mats.py model.pmx [filter-substring]
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

M = L.load(sys.argv[1])
flt = sys.argv[2] if len(sys.argv) > 2 else ""
U = L.UNIT_CM
print("unit cm", U, "verts", len(M.vertices), "faces", len(M.faces), "mats", len(M.materials), "bones", len(M.bones))
for i, m in enumerate(M.materials):
    if flt and flt not in m.name:
        continue
    vs = L.mat_vertices(M, i)
    co = np.array([M.vertices[v].co for v in vs]) * U if vs else np.zeros((1, 3))
    lo, hi = co.min(0), co.max(0)
    tex = M.textures[m.texture].path if m.texture >= 0 else "-"
    print("%3d %-44s f%6d v%6d  x[%6.1f %6.1f] y[%6.1f %6.1f] z[%6.1f %6.1f]  %s" % (
        i, m.name, m.vertex_count // 3, len(vs), lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], os.path.basename(tex)))
