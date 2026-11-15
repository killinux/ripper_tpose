# Put one of a08's planted greatswords on the back (hilt up over the right shoulder, tip down past the left hip):
# rigid transform of the material's vertices + normals, its bone (and that bone's descendants) moved the same way
# and re-parented to 上半身2.      python place_sword.py <in.pmx> <out.pmx> <material> <bone> [--tilt 30] [--gap 3]
import argparse
import sys

import numpy as np

sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_head_swap")
import core  # noqa: E402

oc = core.oc
U = oc.UNIT_CM
ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("bone")
ap.add_argument("--tilt", type=float, default=30.0, help="degrees the hilt leans to the model's right (-x)")
ap.add_argument("--gap", type=float, default=3.0, help="cm between the back's skin and the blade's front face")
ap.add_argument("--centre-y", type=float, default=108.0, help="cm: height of the blade's midpoint")
a = ap.parse_args()
pmx = oc.pmx_module()
M = pmx.load(a.src)
co = np.array([v.co for v in M.vertices], float) * U
names = [b.name for b in M.bones]
mf = oc.material_faces(M)
mi = [i for i, mt in enumerate(M.materials) if mt.name == a.material][0]
vs = sorted({v for f in mf[mi] for v in M.faces[f]})
P = co[vs]
# the back: the skin's largest z in the shoulder-blade band
skin = [i for i, mt in enumerate(M.materials) if "skin" in mt.name.lower() or "body1_00" in mt.name][0]
sv = sorted({v for f in mf[skin] for v in M.faces[f]})
S = co[sv]
band = S[(S[:, 1] > 100) & (S[:, 1] < 140) & (np.abs(S[:, 0]) < 15)]
back_z = band[:, 2].max()
th = np.radians(a.tilt)
R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
c0 = (P.min(0) + P.max(0)) / 2          # geometric midpoint (the vertices crowd at the hilt)
thick = P[:, 2].max() - P[:, 2].min()
target = np.array([0.0, a.centre_y, back_z + a.gap + thick / 2])
def xf(p):
    return (R @ (p - c0).T).T + target
P2 = xf(P)
print("back z %.1f cm; blade centre %s -> %s; after: x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (
    back_z, np.round(c0, 1).tolist(), np.round(target, 1).tolist(), P2[:, 0].min(), P2[:, 0].max(), P2[:, 1].min(),
    P2[:, 1].max(), P2[:, 2].min(), P2[:, 2].max()))
for k, v in enumerate(vs):
    M.vertices[v].co = [float(x) for x in P2[k] / U]
    n = np.array(M.vertices[v].normal, float)
    M.vertices[v].normal = [float(x) for x in R @ n]
# the bone and its descendants
bi = names.index(a.bone)
kids = {i for i, b in enumerate(M.bones)}
sub, stack = {bi}, [bi]
while stack:
    k = stack.pop()
    for i, b in enumerate(M.bones):
        if b.parent == k and i not in sub:
            sub.add(i)
            stack.append(i)
for i in sub:
    b = M.bones[i]
    b.location = [float(x) for x in xf(np.array(b.location, float) * U) / U]
M.bones[bi].parent = names.index("上半身2")
# rigid bodies on those bones (if any) go along
for r in M.rigids:
    if r.bone in sub:
        r.location = [float(x) for x in xf(np.array(r.location, float) * U) / U]
print("moved %d bones (%s), parent of %s -> 上半身2" % (len(sub), ", ".join(names[i] for i in sorted(sub))[:80], a.bone))
pmx.save(a.out, M, add_uv_count=M.header.additional_uvs)
print("wrote", a.out)
