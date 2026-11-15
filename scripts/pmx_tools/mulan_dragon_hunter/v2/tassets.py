# A plate skirt (tassets) like the in-game 水晶猎龙者: N dark plates hanging from the hips, each with an orange flame
# panel inset; plates follow the hip's outline (skin ring at the belt height), flare outward towards the bottom.
# Front / back plates on 下半身, side plates blended to 左足D / 右足D so they swing with the legs.
#   python tassets.py <in.pmx> <out.pmx> --skin pc_a01_nk_body [--n 8] [--top 101] [--length 24] [--width 11]
#                     [--flare 12] [--gap 1.5] [--material tassets]
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402
from add_crystals import winding_flip  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--skin", default="pc_a01_nk_body")
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--top", type=float, default=101.0, help="cm: hanging edge height")
ap.add_argument("--length", type=float, default=24.0)
ap.add_argument("--width", type=float, default=11.0, help="cm at the top")
ap.add_argument("--flare", type=float, default=12.0, help="degrees the plate leans outward")
ap.add_argument("--gap", type=float, default=1.5, help="cm off the skin at the top")
ap.add_argument("--thick", type=float, default=0.8)
ap.add_argument("--start-deg", type=float, default=22.5, help="angle of the first plate (0 = front)")
ap.add_argument("--material", default="tassets")
ap.add_argument("--seed", type=int, default=5)
a = ap.parse_args()

M = L.load(a.src)
flip = winding_flip(M)
rng = np.random.default_rng(a.seed)
si = L.mat_index(M, a.skin)
sv = L.mat_vertices(M, si)
SP = np.array([M.vertices[v].co for v in sv]) * L.UNIT_CM
band = SP[(SP[:, 1] > a.top - 4) & (SP[:, 1] < a.top + 4)]
cx, cz = band[:, 0].mean(), band[:, 2].mean()
ang_s = np.arctan2(band[:, 0] - cx, -(band[:, 2] - cz))        # 0 = front (-z), + = model's left (+x)
rad_s = np.hypot(band[:, 0] - cx, band[:, 2] - cz)


def hip_radius(theta):
    d = np.abs((ang_s - theta + np.pi) % (2 * np.pi) - np.pi)
    sel = d < np.radians(14)
    return float(np.percentile(rad_s[sel], 90)) if sel.sum() > 5 else float(rad_s.max())


bone_lower = L.bone_index(M, "下半身")
bone_l = L.bone_index(M, "左足D") if "左足D" in [b.name for b in M.bones] else L.bone_index(M, "左足")
bone_r = L.bone_index(M, "右足D") if "右足D" in [b.name for b in M.bones] else L.bone_index(M, "右足")


def weight_for(theta):
    """BDEF2 下半身 + the near leg, by how far to the side the plate hangs"""
    side = abs(np.sin(theta))                 # 0 front/back, 1 sides
    leg = bone_l if np.sin(theta) > 0 else bone_r
    w_leg = float(np.clip((side - 0.3) / 0.6, 0, 1)) * 0.7
    w = L.pmx.BoneWeight()
    if w_leg < 0.02:
        w.type, w.bones, w.weights = L.pmx.BoneWeight.BDEF1, [bone_lower], []
    else:
        w.type, w.bones, w.weights = L.pmx.BoneWeight.BDEF2, [bone_lower, leg], [1.0 - w_leg]
    return w


here = os.path.dirname(os.path.abspath(a.out))
tdir = os.path.join(here, "textures")
os.makedirs(tdir, exist_ok=True)
# textures: dark plate (left half of the image) and the flame panel (right half) -> one texture, u picks the half
img = np.zeros((512, 512, 3), np.float32)
img[:, :256] = np.array([0.09, 0.05, 0.12])
yy = np.linspace(0, 1, 512)[:, None]
xx = np.linspace(0, 1, 256)[None, :]
flame = np.zeros((512, 256, 3), np.float32)
base = np.array([0.95, 0.35, 0.05]) * (1 - yy) + np.array([1.0, 0.85, 0.35]) * yy       # orange top -> yellow tip
edge = np.clip(1 - np.abs(xx - 0.5) * 2.6, 0, 1) ** 0.6                                    # dark toward the rim
streak = np.exp(-((xx - 0.5) ** 2) / 0.01) * 0.25
flame = base[:, None, :] * (0.35 + 0.65 * edge)[..., None] + streak[..., None]
img[:, 256:] = np.clip(flame, 0, 1)
tex_path = os.path.join(tdir, "tassets.png")
Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB").save(tex_path)
tex = L.add_texture(M, os.path.abspath(tex_path))

faces = []


def add_tri(pts, uvs, nrm_hint, w):
    pts = [np.asarray(p, float) for p in pts]
    nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    if np.linalg.norm(nrm) < 1e-12:
        return
    if np.dot(nrm, nrm_hint) < 0:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
        nrm = -nrm
    nrm = nrm / np.linalg.norm(nrm)
    if flip:
        pts = [pts[0], pts[2], pts[1]]
        uvs = [uvs[0], uvs[2], uvs[1]]
    idx = []
    for p, uv in zip(pts, uvs):
        v = L.pmx.Vertex()
        v.co = [float(x) for x in p / L.UNIT_CM]
        v.normal = [float(x) for x in nrm]
        v.uv = [float(uv[0]), float(uv[1])]
        v.additional_uvs = [[0.0, 0.0, 0.0, 0.0]] * M.header.additional_uvs
        import copy
        v.weight = copy.deepcopy(w)
        v.edge_scale = 1.0
        M.vertices.append(v)
        idx.append(len(M.vertices) - 1)
    faces.append(idx)


def plate(theta, w):
    """one plate: outline points down the hang direction; outer dark plate (both sides + rim) and the inset flame panel"""
    r0 = hip_radius(theta) + a.gap
    out_dir = np.array([np.sin(theta), 0.0, -np.cos(theta)])      # outward
    tang = np.array([np.cos(theta), 0.0, np.sin(theta)])          # along the ring (to the model's left)
    hang = np.array([np.sin(theta) * np.sin(np.radians(a.flare)), -np.cos(np.radians(a.flare)),
                     -np.cos(theta) * np.sin(np.radians(a.flare))])
    hang /= np.linalg.norm(hang)
    centre_top = np.array([cx, a.top, cz]) + out_dir * r0
    # outline (local: s along tang, t down hang), tapered to a point, with a notch shoulder
    half = a.width / 2
    prof = [(-half, 0.0), (half, 0.0), (half * 1.05, 0.35), (half * 0.7, 0.72), (0.0, 1.0), (-half * 0.7, 0.72), (-half * 1.05, 0.35)]
    pts = [centre_top + tang * s + hang * (t * a.length) for s, t in prof]
    n_out = out_dir * 0.9 + np.array([0, 0.25, 0])
    th = a.thick

    def fan(poly, uvs, offset, hint, w):
        c = np.mean(poly, 0) + offset
        uc = np.mean(uvs, 0)
        for i in range(len(poly)):
            add_tri([poly[i] + offset, poly[(i + 1) % len(poly)] + offset, c], [uvs[i], uvs[(i + 1) % len(poly)], uc], hint, w)

    uv_dark = [[0.1 + 0.3 * (s / half + 1) / 2, t] for s, t in prof]
    fan(pts, uv_dark, out_dir * th * 0.5, n_out, w)                        # outer face
    fan(pts, uv_dark, -out_dir * th * 0.5, -n_out, w)                      # inner face
    for i in range(len(pts)):                                              # rim
        p0, p1 = pts[i], pts[(i + 1) % len(pts)]
        o = out_dir * th * 0.5
        mid = (p0 + p1) / 2 - np.mean(pts, 0)
        add_tri([p0 + o, p1 + o, p1 - o], [[0.2, 0.5]] * 3, mid, w)
        add_tri([p0 + o, p1 - o, p0 - o], [[0.2, 0.5]] * 3, mid, w)
    # flame panel: inset 75 %, floating 0.3 cm in front of the outer face
    cen = np.mean(pts, 0)
    inset = [cen + (p - cen) * 0.72 for p in pts]
    inset = [p + hang * 1.5 for p in inset]
    uv_fl = [[0.55 + 0.4 * (s / half + 1) / 2, t] for s, t in prof]
    fan(inset, uv_fl, out_dir * (th * 0.5 + 0.3), n_out, w)
    fan(inset, uv_fl, out_dir * (th * 0.5 + 0.05), -n_out, w)


for k in range(a.n):
    theta = np.radians(a.start_deg) + 2 * np.pi * k / a.n
    plate(theta, weight_for(theta))

L.new_material(M, a.material, a.material, tex, faces, diffuse=(1, 1, 1, 1), specular=(0.5, 0.4, 0.55), shininess=30,
               ambient=(0.5, 0.45, 0.55), edge=True, edge_color=(0.04, 0.02, 0.06, 1.0), edge_size=0.6, toon=0,
               comment="plate skirt with flame panels (tassets.py)")
L.save(M, a.out)
print("wrote", a.out, "plates", a.n, "faces", len(faces), "hip centre", round(float(cx), 1), round(float(cz), 1),
      "radius front/side", round(hip_radius(0.0), 1), round(hip_radius(np.pi / 2), 1))
