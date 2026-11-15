# Grow crystal shards (faceted hexagonal prisms with pointed tips) on a PMX: each cluster snaps to the nearest vertex of
# the given material(s), takes that vertex's normal as the growing direction and its heaviest bone as the shards' bone.
#   python add_crystals.py <in.pmx> <out.pmx> <spec.json>
# spec: {"material": "crystals", "texture": "crystal_orange.png", "seed": 1, "edge": true,
#        "clusters": [{"name": "...", "mats": ["m1", ...], "point_cm": [x, y, z], "bone": "auto" | "右肩",
#                      "count": 3, "len_cm": [5, 10], "r_cm": [1.0, 1.8], "spread_deg": 25, "radius_cm": 2.0,
#                      "sink_cm": 1.0, "up_bias": 0.3, "dir": [x, y, z] (optional, cm space, replaces the normal),
#                      "mirror": true, "mats_mirror": [...] (optional)}]}
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402
from PIL import Image  # noqa: E402


def make_texture(path, kind="orange"):
    """256 x 256: rows = along the shard (top = tip, bright), columns = facets with a little variation"""
    h = w = 256
    y = np.linspace(0, 1, h)[:, None]          # 0 at the tip
    x = np.linspace(0, 1, w)[None, :]
    if kind == "orange":
        tip = np.array([1.00, 0.95, 0.70])
        mid = np.array([1.00, 0.55, 0.08])
        base = np.array([0.55, 0.12, 0.02])
    else:                                      # pink gem
        tip = np.array([1.00, 0.85, 0.95])
        mid = np.array([0.95, 0.30, 0.65])
        base = np.array([0.35, 0.05, 0.25])
    t = y ** 0.8
    col = np.where(t < 0.45, tip + (mid - tip) * (t / 0.45), mid + (base - mid) * ((t - 0.45) / 0.55))
    col = np.broadcast_to(col, (h, w, 3)).copy()
    # v5: stronger facet contrast (0.68 / 0.86 / 1.0 cycling) and a hard bright line at one facet edge -> crisp faceting
    fi = np.floor(x * 6) % 3
    facet = np.where(fi == 0, 1.0, np.where(fi == 1, 0.86, 0.68))
    col *= facet[..., None]
    fx = (x * 6) % 1.0
    streak = (np.exp(-((fx - 0.08) ** 2) / 0.0015) * 0.45 + np.exp(-((x - 0.5) ** 2) / 0.02) * 0.2) * (1 - t * 0.6)
    col = np.clip(col + streak[..., None], 0, 1)
    Image.fromarray((col * 255 + 0.5).astype(np.uint8), "RGB").save(path)


def shard_mesh(length, r, rng, flip):
    """local shard: axis +z, base ring at z=0, bottom apex sunk, pointed tip at z=length. Returns (tris) where each tri
    is a list of 3 (co, normal, uv)"""
    n = 6
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + rng.uniform(0, np.pi / 3)
    jit = rng.uniform(0.85, 1.15, n)
    ring0 = np.stack([r * jit * np.cos(ang), r * jit * np.sin(ang), np.zeros(n)], 1)
    z1 = length * rng.uniform(0.5, 0.65)
    jit1 = rng.uniform(0.9, 1.2, n)
    ring1 = np.stack([r * jit1 * np.cos(ang + rng.uniform(-0.15, 0.15, n)), r * jit1 * np.sin(ang + rng.uniform(-0.15, 0.15, n)),
                      np.full(n, z1)], 1)
    tip = np.array([rng.uniform(-0.15, 0.15) * r, rng.uniform(-0.15, 0.15) * r, length])
    bottom = np.array([0.0, 0.0, -0.35 * length])
    zmin, zmax = bottom[2], length
    u_off = rng.uniform(0, 1)

    def uv(p, k):
        return [((k + 0.5) / n + u_off) % 1.0, 1.0 - (p[2] - zmin) / (zmax - zmin)]

    tris = []

    def tri(a, b, c, k):
        pts = [np.asarray(a), np.asarray(b), np.asarray(c)]
        nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        cen = (pts[0] + pts[1] + pts[2]) / 3
        out = cen - np.array([0, 0, z1 * 0.5])
        if np.dot(nrm, out) < 0:
            pts = [pts[0], pts[2], pts[1]]
            nrm = -nrm
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        if flip:
            pts = [pts[0], pts[2], pts[1]]
        tris.append([(p, nrm, uv(p, k)) for p in pts])

    for k in range(n):
        k2 = (k + 1) % n
        tri(bottom, ring0[k], ring0[k2], k)
        tri(ring0[k], ring1[k], ring1[k2], k)
        tri(ring0[k], ring1[k2], ring0[k2], k)
        tri(ring1[k], tip, ring1[k2], k)
    return tris


def shard_mesh_sharp(length, r, rng, flip, aniso=None):
    """v5 'sharp' crystal: a slim hexagonal prism (almost no jitter), straight, the tip a clean six-facet point over
    the last 30 % of the length - reads as a crystal spike, not a rock.  aniso=(sx, sy) squashes the cross-section
    (v9 'plate': (2.2, 0.3) = a flat crystal flake, wide along local x, thin along local y)."""
    n = 6
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + (np.pi / 6 if aniso else rng.uniform(0, np.pi / 3))
    jit = rng.uniform(0.96, 1.04, n)
    sx, sy = aniso if aniso else (1.0, 1.0)
    ring0 = np.stack([r * jit * np.cos(ang) * sx, r * jit * np.sin(ang) * sy, np.zeros(n)], 1)
    z1 = length * rng.uniform(0.62, 0.72)
    ring1 = np.stack([r * jit * 1.04 * np.cos(ang) * sx, r * jit * 1.04 * np.sin(ang) * sy, np.full(n, z1)], 1)
    tip = np.array([rng.uniform(-0.05, 0.05) * r * sx, rng.uniform(-0.05, 0.05) * r * sy, length])
    bottom = np.array([0.0, 0.0, -0.3 * length])
    zmin, zmax = bottom[2], length
    u_off = rng.uniform(0, 1)

    def uv(p, k):
        return [((k + 0.5) / n + u_off) % 1.0, 1.0 - (p[2] - zmin) / (zmax - zmin)]

    tris = []

    def tri(a, b, c, k):
        pts = [np.asarray(a), np.asarray(b), np.asarray(c)]
        nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        cen = (pts[0] + pts[1] + pts[2]) / 3
        if np.dot(nrm, cen - np.array([0, 0, z1 * 0.5])) < 0:
            pts = [pts[0], pts[2], pts[1]]
            nrm = -nrm
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        if flip:
            pts = [pts[0], pts[2], pts[1]]
        tris.append([(p, nrm, uv(p, k)) for p in pts])

    for k in range(n):
        k2 = (k + 1) % n
        tri(bottom, ring0[k], ring0[k2], k)
        tri(ring0[k], ring1[k], ring1[k2], k)
        tri(ring0[k], ring1[k2], ring0[k2], k)
        tri(ring1[k], tip, ring1[k2], k)
    return tris


def shard_mesh_irregular(length, r, rng, flip):
    """irregular chunk: 5-8 uneven sides, a leaning bulge ring, a chisel tip made of two offset apexes (like the big
    crystals in the splash art), bottom apex sunk.  Same return shape as shard_mesh."""
    n = int(rng.integers(5, 9))
    step = 2 * np.pi / n
    ang = np.cumsum(rng.uniform(0.6, 1.4, n)) * step
    ang = ang / ang[-1] * 2 * np.pi + rng.uniform(0, 2 * np.pi)
    jit = rng.uniform(0.7, 1.3, n)
    ring0 = np.stack([r * jit * np.cos(ang), r * jit * np.sin(ang), np.zeros(n)], 1)
    z1 = length * rng.uniform(0.45, 0.7)
    lean = rng.uniform(-0.3, 0.3, 2) * r
    jit1 = rng.uniform(0.9, 1.45, n)
    ang1 = ang + rng.uniform(-0.2, 0.2, n)
    ring1 = np.stack([r * jit1 * np.cos(ang1) + lean[0], r * jit1 * np.sin(ang1) + lean[1], np.full(n, z1)], 1)
    off = rng.uniform(0.3, 0.7) * r
    da = rng.uniform(0, 2 * np.pi)
    apex1 = np.array([lean[0] + off * np.cos(da) * 0.4, lean[1] + off * np.sin(da) * 0.4, length])
    apex2 = np.array([lean[0] - off * np.cos(da), lean[1] - off * np.sin(da), length * rng.uniform(0.72, 0.9)])
    bottom = np.array([0.0, 0.0, -0.35 * length])
    zmin, zmax = bottom[2], length
    u_off = rng.uniform(0, 1)
    half = n // 2

    def uv(p, k):
        return [((k + 0.5) / n + u_off) % 1.0, 1.0 - (p[2] - zmin) / (zmax - zmin)]

    tris = []
    cen_ref = np.array([lean[0], lean[1], z1 * 0.5])

    def tri(a, b, c, k):
        pts = [np.asarray(a), np.asarray(b), np.asarray(c)]
        nrm = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        if np.linalg.norm(nrm) < 1e-9:
            return
        cen = (pts[0] + pts[1] + pts[2]) / 3
        if np.dot(nrm, cen - cen_ref) < 0:
            pts = [pts[0], pts[2], pts[1]]
            nrm = -nrm
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        if flip:
            pts = [pts[0], pts[2], pts[1]]
        tris.append([(p, nrm, uv(p, k)) for p in pts])

    for k in range(n):
        k2 = (k + 1) % n
        tri(bottom, ring0[k], ring0[k2], k)
        tri(ring0[k], ring1[k], ring1[k2], k)
        tri(ring0[k], ring1[k2], ring0[k2], k)
        apex = apex1 if k < half else apex2
        apex_next = apex1 if k2 < half else apex2
        if apex is apex_next:
            tri(ring1[k], apex, ring1[k2], k)
        else:                                   # the seam between the two apexes: a quad
            tri(ring1[k], apex, ring1[k2], k)
            tri(ring1[k2], apex, apex_next, k)
    return tris


def winding_flip(M):
    """True when PMX faces in this file are stored so that cross(v1-v0, v2-v0) points AGAINST the vertex normals"""
    agree = 0
    tot = 0
    for f in M.faces[:: max(1, len(M.faces) // 500)]:
        p = [np.array(M.vertices[v].co) for v in f]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        vn = sum(np.array(M.vertices[v].normal) for v in f)
        if np.linalg.norm(nrm) < 1e-12:
            continue
        tot += 1
        agree += np.dot(nrm, vn) > 0
    return agree < tot / 2


def main():
    src, out, spec_path = sys.argv[1:4]
    spec = json.load(open(spec_path, encoding="utf-8"))
    M = L.load(src)
    rng = np.random.default_rng(spec.get("seed", 1))
    flip = winding_flip(M)
    print("winding flip:", flip)
    here = os.path.dirname(os.path.abspath(out))
    os.makedirs(os.path.join(here, "textures"), exist_ok=True)
    tex_name = spec.get("texture", "crystal_orange.png")
    make_texture(os.path.join(here, "textures", tex_name), spec.get("kind", "orange"))
    tex = L.add_texture(M, "textures\\" + tex_name)

    mat_cache = {}

    def mat_pts(names):
        key = tuple(names)
        if key not in mat_cache:
            vs = []
            for nm in names:
                vs += L.mat_vertices(M, L.mat_index(M, nm))
            vs = sorted(set(vs))
            mat_cache[key] = (vs, np.array([M.vertices[v].co for v in vs]) * L.UNIT_CM)
        return mat_cache[key]

    faces = []
    report = []
    bone_names = [b.name for b in M.bones]

    def grow(c, point, mats, bone_name):
        vs, P = mat_pts(mats)
        d = np.linalg.norm(P - np.array(point), axis=1)
        k = int(d.argmin())
        v = vs[k]
        p = P[k]
        nrm = np.array(M.vertices[v].normal, float)
        surf_n = nrm / (np.linalg.norm(nrm) + 1e-12)     # the armour's surface normal at the anchor (for plates)
        if c.get("dir"):
            nrm = np.array(c["dir"], float)
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        ub = c.get("up_bias", 0.0)
        nrm = nrm * (1 - ub) + np.array([0, 1.0, 0]) * ub
        nrm /= np.linalg.norm(nrm) + 1e-12
        if bone_name == "auto":
            bone = L.dominant_bone(M, v)
        else:
            bone = bone_names.index(bone_name)
        u, w, _ = L.frame_from(nrm)
        cnt = c.get("count", 3)
        lens = np.sort(rng.uniform(c["len_cm"][0], c["len_cm"][1], cnt))[::-1]
        rs = np.sort(rng.uniform(c["r_cm"][0], c["r_cm"][1], cnt))[::-1]
        for i in range(cnt):
            if i == 0:
                base = p.copy()
                dd = nrm
            else:
                a = rng.uniform(0, 2 * np.pi)
                rad = rng.uniform(0.4, 1.0) * c.get("radius_cm", 2.0)
                base = p + (u * np.cos(a) + w * np.sin(a)) * rad
                tilt = np.radians(rng.uniform(0.5, 1.0) * c.get("spread_deg", 25))
                dd = nrm * np.cos(tilt) + (u * np.cos(a) + w * np.sin(a)) * np.sin(tilt)
                dd /= np.linalg.norm(dd) + 1e-12
            base = base - nrm * c.get("sink_cm", 1.0)
            style = c.get("style", spec.get("style", "shard"))
            if style == "plate":
                # a flake lies flat on the armour: thin axis = the surface normal (minus its part along the growth
                # direction), wide axis across; the growth direction keeps the tip pointing up / out
                thin = surf_n - dd * float(surf_n @ dd)
                if np.linalg.norm(thin) < 1e-6:
                    thin = L.frame_from(dd)[0]
                thin /= np.linalg.norm(thin)
                wide = np.cross(dd, thin)
                R = np.stack([wide, thin, dd], 1)
                tris = shard_mesh_sharp(lens[i], rs[i], rng, flip, aniso=(2.2, 0.3))
            else:
                su, sw, sd = L.frame_from(dd)
                R = np.stack([su, sw, sd], 1)          # local xyz -> world
                gen = {"chunk": shard_mesh_irregular, "sharp": shard_mesh_sharp}.get(style, shard_mesh)
                tris = gen(lens[i], rs[i], rng, flip)
            for tri in tris:
                idx = []
                for co, n_, uv in tri:
                    wc = (base + R @ co) / L.UNIT_CM
                    wn = R @ n_
                    idx.append(L.new_vertex(M, wc, wn, uv, bone))
                faces.append(idx)
        report.append({"name": c["name"], "snapped_cm": [round(float(x), 1) for x in p], "bone": bone_names[bone],
                       "count": cnt, "len_cm": [round(float(x), 1) for x in lens]})

    for c in spec["clusters"]:
        grow(c, c["point_cm"], c["mats"], c.get("bone", "auto"))
        if c.get("mirror"):
            pm = [-c["point_cm"][0], c["point_cm"][1], c["point_cm"][2]]
            mats = c.get("mats_mirror", [L.swap_lr(m) for m in c["mats"]])
            mats = [m for m in mats if any(mm.name == m for mm in M.materials)] or c["mats"]
            bn = c.get("bone", "auto")
            cm = dict(c)
            if c.get("dir"):
                cm["dir"] = [-c["dir"][0], c["dir"][1], c["dir"][2]]
            grow(cm, pm, mats, bn if bn == "auto" else L.swap_lr(bn))

    name = spec.get("material", "crystals")
    L.new_material(M, name, name, tex, faces, diffuse=(1, 1, 1, 1), specular=(0.9, 0.8, 0.6), shininess=30,
                   ambient=(1.0, 0.8, 0.55), edge=spec.get("edge", True), edge_color=(0.35, 0.08, 0.0, 1.0),
                   edge_size=0.6, toon=0, comment="procedural crystal shards (add_crystals.py)")
    L.save(M, out)
    print("wrote", out, "faces", len(faces))
    for r in report:
        print(" ", r)


if __name__ == "__main__":
    main()
