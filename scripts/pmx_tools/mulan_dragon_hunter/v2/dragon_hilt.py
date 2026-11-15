# A stylised low-poly dragon head as the sword's guard: the blade (material from crystal_blade.py) comes out of its
# open mouth.  Frame from the crystal blade's PCA (axis = length, ax2 = the blade's width = the head's up, ax3 = the
# head's sideways).  Skull / jaws / neck cuff = lofted rings, horns = lofted along a curve, teeth / brow spikes / eyes
# = crystal shards.  Two materials: dragon_head (dark plate texture) and dragon_head_crystal (orange), bone = the sword's.
#   python dragon_hilt.py <in.pmx> <out.pmx> --blade crystal_blade --hilt wp_a08_l --bone Point007_L [--scale 1.0]
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402
from add_crystals import make_texture, shard_mesh, shard_mesh_irregular, winding_flip  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--blade", default="crystal_blade")
ap.add_argument("--hilt", default="wp_a08_l")
ap.add_argument("--bone", default="Point007_L")
ap.add_argument("--scale", type=float, default=1.0)
ap.add_argument("--seed", type=int, default=5)
a = ap.parse_args()

M = L.load(a.src)
flip = winding_flip(M)
bone = L.bone_index(M, a.bone)
rng = np.random.default_rng(a.seed)
bl = L.mat_vertices(M, L.mat_index(M, a.blade))
PB = np.array([M.vertices[v].co for v in bl]) * L.UNIT_CM
hv = L.mat_vertices(M, L.mat_index(M, a.hilt))
PH = np.array([M.vertices[v].co for v in hv]) * L.UNIT_CM
c = PB.mean(0)
U, S, Vt = np.linalg.svd(PB - c, full_matrices=False)
ax, ax2, ax3 = Vt[0], Vt[1], Vt[2]
t = (PB - c) @ ax
# +Z of the head = towards the blade's tip: the tip end is the one farther from the hilt's centroid
th = (PH.mean(0) - c) @ ax
if th > 0:                       # hilt lies at +t -> the tip is at -t
    ax = -ax
    t = -t
base_t = t.min()                 # the blade's base (nearest the grip) along +Z
Z = ax
Y = ax2 / np.linalg.norm(ax2)
X = np.cross(Y, Z)
origin = c + Z * (base_t + 3.0)   # the head's reference point: 3 cm beyond the blade's base, inside the mouth
s = a.scale


def W(p):
    """local (x sideways, y up, z towards the tip) cm -> world PMX units"""
    p = np.asarray(p, float) * s
    return (origin + X * p[0] + Y * p[1] + Z * p[2]) / L.UNIT_CM


faces_head, faces_cry = [], []
tex_dir = os.path.join(os.path.dirname(os.path.abspath(a.out)), "textures")
os.makedirs(tex_dir, exist_ok=True)
plate_png = os.path.join(tex_dir, "dragon_plate.png")
col = np.array([0.13, 0.07, 0.17])
Image.fromarray(np.tile((col * 255 + 0.5).astype(np.uint8), (64, 64, 1)), "RGB").save(plate_png)
cry_png = os.path.join(tex_dir, "crystal_orange.png")
if not os.path.isfile(cry_png):
    make_texture(cry_png, "orange")
tex_plate = L.add_texture(M, os.path.abspath(plate_png))
tex_cry = L.add_texture(M, os.path.abspath(cry_png))


def add_tri(store, pts, uvs, cen_hint, nrm_override=None):
    pts = [np.asarray(p, float) for p in pts]
    nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    if np.linalg.norm(nrm) < 1e-14:
        return
    if np.dot(nrm, (pts[0] + pts[1] + pts[2]) / 3 - cen_hint) < 0:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
        nrm = -nrm
    nrm = nrm / np.linalg.norm(nrm)
    if flip:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
    store.append([L.new_vertex(M, p, nrm, uv, bone) for p, uv in zip(pts, uvs)])


def loft(rings_local, store, close_start=True, close_end=True):
    """rings: list of lists of local points (same count); quads between rings, fan caps"""
    rings = [[W(p) for p in r] for r in rings_local]
    cen = np.mean([np.mean(r, 0) for r in rings], 0)
    n = len(rings[0])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(n):
            k2 = (k + 1) % n
            add_tri(store, [r0[k], r0[k2], r1[k2]], [[0.3, 0.5]] * 3, cen)
            add_tri(store, [r0[k], r1[k2], r1[k]], [[0.3, 0.5]] * 3, cen)
    for ring, on in ((rings[0], close_start), (rings[-1], close_end)):
        if not on:
            continue
        cc = np.mean(ring, 0)
        for k in range(n):
            add_tri(store, [ring[k], ring[(k + 1) % n], cc], [[0.3, 0.5]] * 3, cen)


def ring_box(z, y_lo, y_hi, w, round_k=0.35):
    """8-point rounded-rectangle cross-section at local z: y from y_lo to y_hi, half-width w"""
    ym = (y_lo + y_hi) / 2
    hh = (y_hi - y_lo) / 2
    pts = []
    for ang in np.linspace(0, 2 * np.pi, 8, endpoint=False) + np.pi / 8:
        cx, cy = np.cos(ang), np.sin(ang)
        # superellipse-ish: push towards a rectangle
        px = np.sign(cx) * (abs(cx) ** round_k) * w
        py = ym + np.sign(cy) * (abs(cy) ** round_k) * hh
        pts.append([px, py, z])
    return pts


# --- neck cuff around the grip end, skull + upper jaw (one loft), lower jaw (own loft).  The crystal blade is
# 14 cm wide (y +-7) a dozen cm past the mouth, so the jaws open past y +-8.
skull = [ring_box(-7, -4.0, 4.0, 3.4), ring_box(-3, -6.5, 7.0, 5.2), ring_box(2, -7.5, 9.0, 6.2),
         ring_box(7, 2.5, 9.5, 5.6), ring_box(12, 4.5, 9.5, 4.6), ring_box(17, 6.0, 8.8, 3.2),
         ring_box(21, 6.8, 8.0, 1.8)]
loft(skull, faces_head)
jaw = [ring_box(0, -8.0, -3.5, 4.8), ring_box(5, -9.5, -5.5, 4.0), ring_box(10, -11.0, -8.0, 3.2),
       ring_box(14, -12.2, -10.0, 2.3), ring_box(18, -13.0, -11.6, 1.3)]
loft(jaw, faces_head)
# cheek plates: thin fins sticking out sideways behind the eyes
for sx in (-1, 1):
    plate = [[[sx * 5.8, -3.0, 2], [sx * 5.8, 4.0, 2], [sx * 8.2, 4.5, 5], [sx * 8.8, 0.5, 8.5], [sx * 8.2, -3.5, 5]],
             [[sx * 5.8, -3.0, 2.8], [sx * 5.8, 4.0, 2.8], [sx * 8.0, 4.3, 5.6], [sx * 8.6, 0.5, 9.0], [sx * 8.0, -3.3, 5.6]]]
    loft(plate, faces_head)


# --- horns: lofted hexagons along a curve from the skull's top-back, sweeping back and up
def horn(sx):
    path = np.array([[sx * 3.6, 7.5, 0.0], [sx * 5.0, 11.5, -3.5], [sx * 6.0, 15.5, -8.0], [sx * 6.4, 18.5, -12.5],
                     [sx * 6.5, 20.0, -15.0]])
    radii = [1.9, 1.6, 1.2, 0.7, 0.15]
    rings = []
    for i, (p, r) in enumerate(zip(path, radii)):
        d = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)])
        d = d / np.linalg.norm(d)
        u, v, _ = L.frame_from(d)
        ring = [p + (u * np.cos(ang) + v * np.sin(ang)) * r * (1 + 0.15 * np.cos(3 * ang)) for ang in
                np.linspace(0, 2 * np.pi, 6, endpoint=False)]
        rings.append([list(q) for q in ring])
    loft(rings, faces_head)


horn(-1)
horn(1)


# --- crystals: eyes, teeth, brow spikes (local frames -> world)
def shard_at(local_pos, local_dir, length, r, store, gen=shard_mesh):
    p0 = W(local_pos)
    d = X * local_dir[0] + Y * local_dir[1] + Z * local_dir[2]
    d = d / np.linalg.norm(d)
    su, sw, sd = L.frame_from(d)
    R = np.stack([su, sw, sd], 1)
    for tri in gen(length * s, r * s, rng, flip):
        idx = [L.new_vertex(M, p0 + (R @ co) / L.UNIT_CM, R @ n_, uv, bone) for co, n_, uv in tri]
        store.append(idx)


for sx in (-1, 1):
    shard_at([sx * 5.4, 5.8, 6.5], [sx * 1.0, 0.25, 0.3], 2.8, 1.4, faces_cry, shard_mesh_irregular)      # eye
    shard_at([sx * 3.8, 9.2, 3.0], [sx * 0.3, 1.0, -0.4], 4.5, 0.9, faces_cry)                             # brow spike
    shard_at([sx * 2.4, 9.3, 10.0], [sx * 0.2, 1.0, 0.1], 2.8, 0.6, faces_cry)                             # nose spike
    for z, y in ((8.5, 2.8), (11.5, 4.6), (14.5, 5.8), (17.5, 6.2)):                                      # upper teeth
        shard_at([sx * (4.4 - 0.15 * z), y, z], [sx * 0.15, -1.0, 0.25], 2.6, 0.5, faces_cry)
    for z, y in ((7.0, -5.8), (11.0, -8.2), (15.0, -10.2)):                                              # lower teeth
        shard_at([sx * (3.8 - 0.14 * z), y, z], [sx * 0.15, 1.0, 0.2], 2.4, 0.45, faces_cry)
shard_at([0.0, 9.0, -2.0], [0.0, 1.0, -0.6], 5.5, 1.1, faces_cry)                                         # crest spike

L.new_material(M, "dragon_head", "dragon_head", tex_plate, faces_head, diffuse=(1, 1, 1, 1),
               specular=(0.5, 0.4, 0.55), shininess=25, ambient=(0.5, 0.45, 0.55), edge=True,
               edge_color=(0.03, 0.01, 0.05, 1.0), edge_size=0.9, toon=0, comment="dragon head guard (dragon_hilt.py)")
L.new_material(M, "dragon_head_crystal", "dragon_head_crystal", tex_cry, faces_cry, diffuse=(1, 1, 1, 1),
               specular=(0.9, 0.8, 0.6), shininess=30, ambient=(1.0, 0.8, 0.55), edge=True,
               edge_color=(0.35, 0.08, 0.0, 1.0), edge_size=0.5, toon=0, comment="dragon head eyes / teeth / spikes")
L.save(M, a.out)
print("wrote", a.out, "head faces", len(faces_head), "crystal faces", len(faces_cry), "origin cm",
      np.round(origin, 1).tolist(), "axis", np.round(Z, 3).tolist())
