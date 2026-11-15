# Replace a sword's blade with a faceted crystal blade (the guard, grip and pommel stay). The blade is the part of the
# material beyond the guard (the widest slab on the blade side); a tapered flat hexagonal crystal plus a few shards at
# the ricasso replace it, all weighted to the sword's bone.
#   python crystal_blade.py <in.pmx> <out.pmx> <material> <bone> [--tip-end low|high] [--width 7] [--thick 2.2]
#                           [--texture crystal_orange.png] [--out-material crystal_blade] [--seed 3]
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402
from add_crystals import make_texture, shard_mesh, winding_flip  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("material")
ap.add_argument("bone")
ap.add_argument("--tip-end", choices=["low", "high"], default="low", help="the blade points to -axis (low t) or +axis")
ap.add_argument("--width", type=float, default=7.0, help="blade half-width cm at the widest")
ap.add_argument("--thick", type=float, default=2.2, help="blade half-thickness cm")
ap.add_argument("--texture", default="crystal_orange.png")
ap.add_argument("--out-material", default="crystal_blade")
ap.add_argument("--seed", type=int, default=3)
ap.add_argument("--shards", type=int, default=6)
ap.add_argument("--remove-guard", action="store_true", help="drop the crossguard too (a dragon head takes its place)")
a = ap.parse_args()

M = L.load(a.src)
flip = winding_flip(M)
mi = L.mat_index(M, a.material)
bone = L.bone_index(M, a.bone)
mf = L.mat_faces(M)
s, n = mf[mi]
vs = L.mat_vertices(M, mi)
P = np.array([M.vertices[v].co for v in vs]) * L.UNIT_CM
c = P.mean(0)
U, S, Vt = np.linalg.svd(P - c, full_matrices=False)
ax, ax2, ax3 = Vt[0], Vt[1], Vt[2]
if a.tip_end == "high":
    ax = -ax
t = (P - c) @ ax                                      # blade towards NEGATIVE t
# slab profile: the guard = widest slab in the half of the sword nearer the blade, excluding the far 20 cm (a flat tip)
bins = np.arange(np.floor(t.min()), t.max() + 2, 2.0)
prof = []
for lo in bins:
    m = (t >= lo) & (t < lo + 2)
    if m.sum():
        prof.append((lo, float(np.abs((P[m] - c) @ ax2).max()), int(m.sum())))
prof = np.array(prof)
tip_t = t.min()
cand = prof[(prof[:, 0] > tip_t + 20) & (prof[:, 0] < np.median(t))]
g = cand[cand[:, 1].argmax()]
t_guard = g[0]
t_cut = t_guard - 2.0                                 # faces fully beyond this are the old blade
if a.remove_guard:
    t_cut = t_guard + 3.5                             # the guard's slab (2 cm) goes too; the grip starts above
print("axis", ax.round(3), "t range", round(float(t.min()), 1), round(float(t.max()), 1), "guard at t", t_guard,
      "half-width", round(float(g[1]), 1), "cut at", t_cut)
tv = {v: tt for v, tt in zip(vs, t)}
faces = M.faces[s:s + n]
keep = [f for f in faces if not all(tv[v] < t_cut for v in f)]
print("old faces", len(faces), "kept (hilt + guard)", len(keep))
M.faces[s:s + n] = keep
M.materials[mi].vertex_count = len(keep) * 3

rng = np.random.default_rng(a.seed)
here = os.path.dirname(os.path.abspath(a.out))
os.makedirs(os.path.join(here, "textures"), exist_ok=True)
tex_path = os.path.join(here, "textures", a.texture)
if not os.path.isfile(tex_path):
    make_texture(tex_path, "orange")
tex = L.add_texture(M, os.path.abspath(tex_path))


def make_blade_texture(path):
    """512 x 512 for the hexagonal blade: 6 facet columns (u) x length (v, 0 = tip).  Columns 1 and 4 are the broad
    faces: a glowing orange core fading to dark crystalline rims at the column borders (= the blade's edges); the
    bevel columns 0 / 2 / 3 / 5 are black-purple with faint orange veins.  Along the length the tip is brightest."""
    h = w = 512
    v = np.linspace(0, 1, h)[:, None]
    u = np.linspace(0, 1, w)[None, :]
    col_id = np.floor(u * 6).astype(int) % 6
    fu = (u * 6) % 1.0                                        # position inside the facet column
    broad = (col_id == 1) | (col_id == 4)
    # core glow: bright in the middle of the broad face, dark at its borders
    core = np.exp(-((fu - 0.5) ** 2) / 0.045)
    tipness = (1 - v) ** 1.3
    orange = np.array([1.0, 0.55, 0.08])
    yellow = np.array([1.0, 0.92, 0.55])
    dark = np.array([0.16, 0.06, 0.2])
    rim = np.array([0.45, 0.12, 0.05])
    tip3 = tipness[..., None]                                 # (h,1,1)
    core3 = core[..., None]                                   # (1,w,1)
    glow = orange * (1 - tip3) + yellow * tip3                # (h,1,3)
    broad_col = rim * (1 - core3) + glow * core3 * (0.75 + 0.25 * core3)   # (h,w,3)
    # veins on the bevels
    vein = np.exp(-((fu - 0.5) ** 2) / 0.004) * 0.55 + 0.08 * np.sin(v * 60 + fu * 7) ** 2
    bevel_col = dark * 0.9 + orange * 0.9 * vein[..., None] * (0.5 + 0.5 * tip3)
    img = np.where(np.broadcast_to(broad[..., None], (h, w, 3)), broad_col, np.clip(bevel_col, 0, 1))
    img = np.clip(img, 0, 1)
    Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB").save(path)


from PIL import Image  # noqa: E402
blade_tex_path = os.path.join(here, "textures", "crystal_blade.png")
make_blade_texture(blade_tex_path)
tex_blade = L.add_texture(M, os.path.abspath(blade_tex_path))

new_faces = []


def add_tri(pts, uvs, cen_hint):
    nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    if np.dot(nrm, (pts[0] + pts[1] + pts[2]) / 3 - cen_hint) < 0:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
        nrm = -nrm
    nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
    if flip:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
    idx = [L.new_vertex(M, p / L.UNIT_CM, nrm, uv, bone) for p, uv in zip(pts, uvs)]
    new_faces.append(idx)


# --- the main blade: hexagonal cross-section (wide along ax2, thin along ax3), rings along t from the guard to the tip
L_blade = t_guard - tip_t                             # length cm
t0 = t_guard + 4.0                                    # start inside the guard
stations = [0.0, 0.12, 0.35, 0.6, 0.8, 0.92, 1.0]
width_k = [0.75, 1.0, 1.0, 0.85, 0.6, 0.3, 0.0]
thick_k = [0.9, 1.0, 1.0, 0.9, 0.7, 0.4, 0.0]
rings = []
for st, wk, tk in zip(stations, width_k, thick_k):
    tt = t0 - st * (L_blade + 4.0)
    w, th = a.width * wk, a.thick * tk
    if st == 1.0:
        rings.append([c + ax * tt] * 6)
        continue
    # hexagon: two wide points on ax2, four between with the thickness on ax3
    pts = [c + ax * tt + ax2 * w,
           c + ax * tt + ax2 * (w * 0.45) + ax3 * th,
           c + ax * tt - ax2 * (w * 0.45) + ax3 * th,
           c + ax * tt - ax2 * w,
           c + ax * tt - ax2 * (w * 0.45) - ax3 * th,
           c + ax * tt + ax2 * (w * 0.45) - ax3 * th]
    rings.append(pts)
blade_cen = c + ax * (t0 - 0.5 * L_blade)
for i in range(len(rings) - 1):
    r0, r1 = rings[i], rings[i + 1]
    v0, v1 = 1.0 - stations[i], 1.0 - stations[i + 1]   # uv v: 0 at the tip (bright)
    for k in range(6):
        k2 = (k + 1) % 6
        u0, u1 = k / 6, (k + 1) / 6
        if stations[i + 1] == 1.0:
            add_tri([r0[k], r0[k2], r1[0]], [[u0, v0], [u1, v0], [(u0 + u1) / 2, v1]], blade_cen)
        else:
            add_tri([r0[k], r0[k2], r1[k2]], [[u0, v0], [u1, v0], [u1, v1]], blade_cen)
            add_tri([r0[k], r1[k2], r1[k]], [[u0, v0], [u1, v1], [u0, v1]], blade_cen)
# base cap (inside the guard, mostly hidden)
base_c = c + ax * t0
for k in range(6):
    add_tri([rings[0][(k + 1) % 6], rings[0][k], base_c], [[0.5, 1.0], [0.5, 1.0], [0.5, 1.0]], blade_cen)
n_blade = len(new_faces)

# --- shards at the ricasso and along the blade
for i in range(a.shards):
    st = rng.uniform(0.05, 0.5) if i >= 2 else rng.uniform(0.03, 0.12)
    tt = t0 - st * L_blade
    side = 1 if i % 2 == 0 else -1
    base = c + ax * tt + ax2 * side * a.width * (0.9 if st < 0.35 else 0.75) + ax3 * rng.uniform(-0.6, 0.6)
    tilt = np.radians(rng.uniform(35, 60))
    d = ax2 * side * np.cos(tilt) - ax * np.sin(tilt) * rng.uniform(0.6, 1.0) + ax3 * rng.uniform(-0.3, 0.3)
    d /= np.linalg.norm(d)
    length = rng.uniform(7, 14) if i < 2 else rng.uniform(4, 9)
    r = rng.uniform(1.2, 2.2) if i < 2 else rng.uniform(0.8, 1.5)
    su, sw, sd = L.frame_from(d)
    R = np.stack([su, sw, sd], 1)
    for tri in shard_mesh(length, r, rng, flip):
        idx = [L.new_vertex(M, (base - d * 1.0 + R @ co) / L.UNIT_CM, R @ n_, uv, bone) for co, n_, uv in tri]
        new_faces.append(idx)

L.new_material(M, a.out_material, a.out_material, tex_blade, new_faces[:n_blade], diffuse=(1, 1, 1, 1),
               specular=(0.9, 0.8, 0.6), shininess=30, ambient=(1.0, 0.8, 0.55), edge=True,
               edge_color=(0.2, 0.04, 0.1, 1.0), edge_size=0.7, toon=0, comment="crystal blade (crystal_blade.py)")
L.new_material(M, a.out_material + "_shards", a.out_material + "_shards", tex, new_faces[n_blade:],
               diffuse=(1, 1, 1, 1), specular=(0.9, 0.8, 0.6), shininess=30, ambient=(1.0, 0.8, 0.55), edge=True,
               edge_color=(0.35, 0.08, 0.0, 1.0), edge_size=0.6, toon=0, comment="crystal blade shards")
L.save(M, a.out)
print("wrote", a.out, "blade faces", len(new_faces), "blade length cm", round(float(L_blade), 1))
