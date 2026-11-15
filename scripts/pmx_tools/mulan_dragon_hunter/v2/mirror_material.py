# Mirror a material to the other side of the body: x flipped (vertices, normals, SDEF centres), winding flipped, bone
# weights moved to the 左/右 counterpart bone (by name; a bone without a counterpart keeps itself).  The copy is a new
# material "<name>_mirror" (same texture / parameters) appended at the end; the original stays.
#   python mirror_material.py <in.pmx> <out.pmx> <material> [--suffix _mirror]
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("--suffix", default="_mirror")
a = ap.parse_args()

M = L.load(a.src)
pmx = L.pmx
mi = L.mat_index(M, a.material)
s, n = L.mat_faces(M)[mi]
names = [b.name for b in M.bones]
index = {b: i for i, b in enumerate(names)}
counterpart = {}
missing = set()
for i, nm in enumerate(names):
    other = L.swap_lr(nm)
    if other != nm and other in index:
        counterpart[i] = index[other]
    else:
        counterpart[i] = i
        if other != nm:
            missing.add(nm)

new = {}


def dup(v):
    if v in new:
        return new[v]
    src = M.vertices[v]
    nv = copy.deepcopy(src)
    nv.co = [-src.co[0], src.co[1], src.co[2]]
    nv.normal = [-src.normal[0], src.normal[1], src.normal[2]]
    w = nv.weight
    if isinstance(w.bones, (list, tuple)):
        w.bones = [counterpart.get(b, b) if b is not None and b >= 0 else b for b in w.bones]
    if w.type == pmx.BoneWeight.SDEF:
        for attr in ("c", "r0", "r1"):
            val = getattr(w.weights, attr, None)
            if val is not None:
                setattr(w.weights, attr, [-val[0], val[1], val[2]])
    M.vertices.append(nv)
    new[v] = len(M.vertices) - 1
    return new[v]


faces = [[dup(f[0]), dup(f[2]), dup(f[1])] for f in M.faces[s:s + n]]
m0 = M.materials[mi]
m = copy.deepcopy(m0)
m.name = m0.name + a.suffix
m.name_e = (m0.name_e or m0.name) + a.suffix
m.vertex_count = len(faces) * 3
M.materials.append(m)
M.faces.extend(faces)
used = sorted({b for v in new.values() for b in (M.vertices[v].weight.bones or []) if b is not None and b >= 0})
print("mirrored", a.material, "->", m.name, "faces", len(faces), "verts", len(new))
print("bones used by the copy:", ", ".join(names[b] for b in used)[:300])
if missing:
    print("WARNING bones without a counterpart:", ", ".join(sorted(missing))[:300])
L.save(M, a.out)
print("wrote", a.out)
