# "Sharper" armour in MMD: crisp toon edge lines, stronger specular, and an additive sphere map (a generated metal /
# glass highlight) on the armour and crystal materials of a PMX.  Runs on the assembled PMX (textures beside it).
#   python sharpen_materials.py <pmx> [--metal regex] [--crystal regex] [--skin regex]
import argparse
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("--metal", default=r"^(miri_|miul_|vdf_|san_|a08_body2|wp_a08|dragon_head$|chest_plate)")
ap.add_argument("--crystal", default=r"^(crystals|crystal_pink|crystal_blade|crystal_blade_shards|dragon_head_crystal)$")
ap.add_argument("--edge-size", type=float, default=0.55)
a = ap.parse_args()


def sphere_map(path, kind):
    """256x256 additive sphere map: a glossy highlight lobe upper-left + a faint rim (Fresnel) ring"""
    n = 256
    y, x = np.mgrid[0:n, 0:n]
    u = (x - n / 2) / (n / 2)
    v = (y - n / 2) / (n / 2)
    r2 = u * u + v * v
    inside = r2 <= 1.0
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    if kind == "metal":
        lx, ly, lz = -0.45, -0.55, 0.70
        spec = np.clip(u * (-lx) * -1 + v * (-ly) * -1 + nz * lz, 0, 1)   # dot(n, L)
        lobe = spec ** 28 * 0.30                                     # v5b: a small hard highlight only
        rim = np.clip((r2 - 0.75) / 0.25, 0, 1) ** 2 * 0.05
        col = np.stack([lobe * 0.9 + rim * 0.75, lobe * 0.8 + rim * 0.6, lobe * 1.0 + rim * 0.9], -1)
    else:
        lx, ly, lz = -0.4, -0.6, 0.69
        spec = np.clip(u * (-lx) * -1 + v * (-ly) * -1 + nz * lz, 0, 1)
        lobe = spec ** 30 * 0.55 + spec ** 8 * 0.08
        rim = np.clip((r2 - 0.6) / 0.4, 0, 1) ** 2 * 0.15
        col = np.stack([lobe * 1.0 + rim * 1.0, lobe * 0.95 + rim * 0.75, lobe * 0.8 + rim * 0.45], -1)
    col = np.where(inside[..., None], col, 0)
    Image.fromarray((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path)


M = L.load(os.path.abspath(a.pmx))
tdir = os.path.join(os.path.dirname(os.path.abspath(a.pmx)), "textures")
os.makedirs(tdir, exist_ok=True)
sp_metal = os.path.join(tdir, "sph_metal.png")
sp_cry = os.path.join(tdir, "sph_crystal.png")
sphere_map(sp_metal, "metal")
sphere_map(sp_cry, "crystal")
ti_metal = L.add_texture(M, os.path.abspath(sp_metal))
ti_cry = L.add_texture(M, os.path.abspath(sp_cry))
rm, rc = re.compile(a.metal), re.compile(a.crystal)
n_m = n_c = 0
for m in M.materials:
    if rc.search(m.name):
        m.sphere_texture, m.sphere_texture_mode = ti_cry, 2        # ADD
        m.specular, m.shininess = [1.0, 0.95, 0.85], 60.0
        m.enabled_toon_edge, m.edge_size = True, a.edge_size
        m.edge_color = [0.25, 0.05, 0.02, 1.0]
        n_c += 1
    elif rm.search(m.name):
        m.sphere_texture, m.sphere_texture_mode = ti_metal, 2
        m.specular, m.shininess = [0.55, 0.5, 0.65], 40.0
        m.enabled_toon_edge, m.edge_size = True, a.edge_size
        m.edge_color = [0.04, 0.02, 0.06, 1.0]
        n_m += 1
L.save(M, os.path.abspath(a.pmx))
print("sharpened: metal", n_m, "crystal", n_c, "materials;", os.path.basename(sp_metal), os.path.basename(sp_cry))
