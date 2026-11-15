# Copy one material of a donor PMX into the target as a rigid prop on a bone: scaled about its bbox centre, rotated so
# that the prop's own axes (snout / up, given in its source coordinates) match a target frame taken from the crystal
# blade (snout -> along the blade towards the tip, up -> the blade's width direction), placed at the blade's base.
#   python place_prop.py <donor.pmx> <donor material> <target.pmx> <out.pmx> --bone Point007_L --blade crystal_blade
#        --hilt wp_a08_l --snout 0,1,0 --up 0,0,-1 --scale 5.5 --offset 3 --name dragon_head --mirror-x
import argparse
import copy
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("donor")
ap.add_argument("material")
ap.add_argument("target")
ap.add_argument("out")
ap.add_argument("--bone", default="Point007_L")
ap.add_argument("--blade", default="crystal_blade")
ap.add_argument("--hilt", default="wp_a08_l")
ap.add_argument("--snout", default="0,1,0", help="the prop's forward axis in its own coordinates")
ap.add_argument("--up", default="0,0,-1", help="the prop's up axis in its own coordinates")
ap.add_argument("--scale", type=float, default=5.5)
ap.add_argument("--offset", type=float, default=3.0, help="cm: the prop's centre beyond the blade's base")
ap.add_argument("--lift", type=float, default=0.0, help="cm: shift along the blade's width direction")
ap.add_argument("--name", default="dragon_head")
ap.add_argument("--mirror-x", action="store_true", help="also add the mirror image (x of the prop flipped)")
a = ap.parse_args()


def vec(s):
    v = np.array([float(x) for x in s.split(",")])
    return v / np.linalg.norm(v)


D = L.load(os.path.abspath(a.donor))
T = L.load(os.path.abspath(a.target))
dmi = L.mat_index(D, a.material)
ds, dn = L.mat_faces(D)[dmi]
dfaces = D.faces[ds:ds + dn]
dvs = sorted({v for f in dfaces for v in f})
P = np.array([D.vertices[v].co for v in dvs]) * L.UNIT_CM
c0 = (P.min(0) + P.max(0)) / 2
# target frame from the crystal blade
bl = L.mat_vertices(T, L.mat_index(T, a.blade))
PB = np.array([T.vertices[v].co for v in bl]) * L.UNIT_CM
hv = L.mat_vertices(T, L.mat_index(T, a.hilt))
PH = np.array([T.vertices[v].co for v in hv]) * L.UNIT_CM
c = PB.mean(0)
U, S, Vt = np.linalg.svd(PB - c, full_matrices=False)
ax, ax2 = Vt[0], Vt[1]
t = (PB - c) @ ax
if (PH.mean(0) - c) @ ax > 0:
    ax, t = -ax, -t
Zt = ax                                         # towards the tip
Yt = ax2 / np.linalg.norm(ax2)
Xt = np.cross(Yt, Zt)
target_centre = c + Zt * (t.min() + a.offset) + Yt * a.lift
# source frame
zs = vec(a.snout)
ys = vec(a.up)
ys = ys - zs * (ys @ zs)
ys /= np.linalg.norm(ys)
xs = np.cross(ys, zs)
Rs = np.stack([xs, ys, zs], 1)                  # source local -> source world
Rt = np.stack([Xt, Yt, Zt], 1)                  # local -> target world
R = Rt @ Rs.T                                   # source world -> target world
bone = L.bone_index(T, a.bone)
tex_src = D.textures[D.materials[dmi].texture].path
tex_name = os.path.basename(tex_src)
tdir = os.path.join(os.path.dirname(os.path.abspath(a.out)), "textures")
os.makedirs(tdir, exist_ok=True)
dst_tex = os.path.join(tdir, tex_name)
if not os.path.isfile(dst_tex):
    shutil.copyfile(tex_src, dst_tex)
tex = L.add_texture(T, os.path.abspath(dst_tex))
flip_src = L.__dict__.get("winding_flip")


def add_copy(mirror):
    new = {}
    faces = []
    for f in dfaces:
        idx = []
        for v in f:
            key = (v, mirror)
            if key not in new:
                src = D.vertices[v]
                p = np.array(src.co) * L.UNIT_CM - c0
                nrm = np.array(src.normal, float)
                if mirror:
                    p = p * np.array([-1, 1, 1])
                    nrm = nrm * np.array([-1, 1, 1])
                wp = target_centre + R @ (p * a.scale)
                wn = R @ nrm
                new[key] = L.new_vertex(T, wp / L.UNIT_CM, wn, list(src.uv), bone)
            idx.append(new[key])
        faces.append(idx[::-1] if mirror else idx)
    return faces


faces = add_copy(False)
if a.mirror_x:
    faces += add_copy(True)
m0 = D.materials[dmi]
mi = L.new_material(T, a.name, a.name, tex, faces, diffuse=tuple(m0.diffuse), specular=tuple(m0.specular),
                    shininess=m0.shininess, ambient=tuple(m0.ambient), edge=True, edge_color=(0.03, 0.01, 0.05, 1.0),
                    edge_size=0.8, toon=0, comment="prop from %s (place_prop.py)" % a.material)
L.save(T, a.out)
print("placed", a.material, "->", a.name, "faces", len(faces), "scale", a.scale, "centre cm", np.round(target_centre, 1).tolist(),
      "size cm", np.round((P.max(0) - P.min(0)) * a.scale, 1).tolist())
