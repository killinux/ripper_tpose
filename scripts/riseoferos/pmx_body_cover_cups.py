"""ROE _full PMX: every fitted-body vertex hidden UNDER a breast cup takes the cup's weights at the point right above it,
so the two move as one and the skin cannot come out through the cup however the breast swings.

Why (g05, 10-18): after pmx_body_follows_cups.py the swing shares match on average, but g05's nipples sit only
0.7-6 mm under the white chest straps (16 vertices per side < 1 mm), and the remaining small differences (the tool
blends the k nearest cups' swing share, keeps the body's own bone split) still pushed a nipple tip through a strap in
a few frames of the gesture dance.  Here the covered vertices copy the cup exactly: the cup triangle whose surface is
straight above the vertex (projection inside it, offset along its normal, behind it by at most --depth cm) gives the
barycentric blend of its three vertices' weights.  Visible skin (not under a cup) is left as it is; the nude copy,
positions, normals, morphs, bones, bodies and joints are untouched.

--garment / --bones (10-24): any garment over the body, not only the cups.  Inase a05 full: her fitted body pokes out
through the black trousers in big patches whenever the knees bend (the archived file too: 130 body vertices out per
frame of the gesture dance, up to 17 mm) - the body has the nude base's weights, the trousers the game's, and the
trousers ride mostly on the game's thigh helpers Bip001 Xtra02 / Xtra04, which a bone list of the MMD leg bones missed.
--garment pc_a05_hd_body alone takes the whole garment (trousers and jacket) except what hangs on physics bones.
    python pmx_body_cover_cups.py in.pmx out.pmx [--depth 1.0] [--body pc_g01_nk_body] [--skip riband]
        [--garment "material,..." [--bones REGEX]]"""
import argparse
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mmd_physics"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_collision_pmx as cc  # noqa: E402
from pmx_body_follows_cups import write_weights  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--depth", type=float, default=1.0, help="cm: body vertices at most this far under a cup")
ap.add_argument("--body", default=None, help="fitted body material (default: the one ending in _nk_body)")
ap.add_argument("--skip", default="riband", help="bones under the breasts starting with this are not cups")
ap.add_argument("--bones", default=None, help="regex: the covering garment is the part on these bones (default: the "
                                              "breasts' bone trees = the cups; with --garment alone: the whole garment)")
ap.add_argument("--garment", default=None, help="only these materials cover (comma separated; default: every material "
                                                "but the body ones).  Alone (no --bones): all of them except what rides "
                                                "on physics bones (a swinging coat tail or breast would drag the skin "
                                                "under it away from the body)")
args = ap.parse_args()
pmx = cc.load_pmx_module(cc.find_pmx_module())
m = pmx.load(args.src)
names = [b.name for b in m.bones]
kids = {}
for i, b in enumerate(m.bones):
    if b.parent is not None and b.parent >= 0:
        kids.setdefault(b.parent, []).append(i)
tree = set()
whole = bool(args.garment) and not args.bones
if args.bones:
    pat = re.compile(args.bones)
    tree = {i for i, n in enumerate(names) if pat.search(n)}
    print("covering bones: %d (%s ...)" % (len(tree), ", ".join(names[i] for i in sorted(tree)[:8])))
elif whole:
    # every bone but the physics-driven ones (and everything hanging under them)
    swinging = {r.bone for r in m.rigids if r.mode in (1, 2) and r.bone is not None and r.bone >= 0}
    stack = list(swinging)
    while stack:
        k = stack.pop()
        for c in kids.get(k, []):
            if c not in swinging:
                swinging.add(c)
                stack.append(c)
    tree = set(range(len(names))) - swinging
    print("covering: the whole garment except %d physics bones" % len(swinging))
for side in (() if args.bones or whole else ("左胸", "右胸")):
    if side in names:
        stack = [names.index(side)]
        while stack:
            k = stack.pop()
            if names[k].lower().startswith(args.skip):
                continue
            tree.add(k)
            stack.extend(kids.get(k, []))
garment = {s.strip() for s in args.garment.split(",") if s.strip()} if args.garment else None
vm, tris, start = {}, [], 0
for mt in m.materials:
    for f in range(start, start + mt.vertex_count, 3):
        tri = m.faces[f // 3]
        for v in tri:
            vm[v] = mt.name
        tris.append((mt.name, tri))
    start += mt.vertex_count
body_mat = args.body or next(mt.name for mt in m.materials if mt.name.endswith("_nk_body"))
weights = [dict(cc.weights_of(pmx, v)) for v in m.vertices]
share = np.array([sum(x for b, x in w.items() if b in tree) for w in weights])
co = np.array([v.co for v in m.vertices], float)
need = 0.95 if whole else 0.3                  # the whole garment: (almost) nothing on physics bones
cup = np.array([t for n, t in tris if "_nk_" not in n and n != body_mat and (garment is None or n in garment)
                and all(share[v] >= need for v in t)])
print("%s triangles: %d" % ("covering" if args.bones or whole else "cup", len(cup)))
A, B, C = co[cup[:, 0]], co[cup[:, 1]], co[cup[:, 2]]
fn = np.cross(B - A, C - A)
fn /= np.linalg.norm(fn, axis=1)[:, None]
vn = np.array([v.normal for v in m.vertices], float)[cup].mean(1)        # outward, as the vertex normals say
fn *= np.where((fn * vn).sum(1) < 0, -1.0, 1.0)[:, None]
cent = (A + B + C) / 3
depth = args.depth / 8.0


def closest_on_triangle(p, a, b, c):
    """The point of triangle abc nearest to p and its barycentric coordinates."""
    v0, v1 = b - a, c - a
    n = np.cross(v0, v1)
    q = p - ((p - a) @ n) / (n @ n) * n
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    v2 = q - a
    den = d00 * d11 - d01 * d01
    bv = (d11 * (v2 @ v0) - d01 * (v2 @ v1)) / den
    bw = (d00 * (v2 @ v1) - d01 * (v2 @ v0)) / den
    if min(1 - bv - bw, bv, bw) >= 0:
        return q, (1 - bv - bw, bv, bw)
    best = None
    for (s, e, i, j) in ((a, b, 0, 1), (b, c, 1, 2), (c, a, 2, 0)):
        t = float(np.clip(((p - s) @ (e - s)) / ((e - s) @ (e - s)), 0, 1))
        x = s + t * (e - s)
        d = float(((p - x) ** 2).sum())
        if best is None or d < best[0]:
            bary = [0.0, 0.0, 0.0]
            bary[i], bary[j] = 1 - t, t
            best = (d, x, tuple(bary))
    return best[1], best[2]


lo, hi = np.minimum(A, np.minimum(B, C)).min(0) - depth, np.maximum(A, np.maximum(B, C)).max(0) + depth
body = sorted({v for n, t in tris if n == body_mat for v in t})
changed, moved = 0, []
for i in body:
    p = co[i]
    if (p < lo).any() or (p > hi).any():
        continue
    near = np.argsort(((cent - p) ** 2).sum(1))[:12]
    best = None
    for t in near:
        gap = float((p - A[t]) @ fn[t])
        if gap >= 0 or -gap > depth:
            continue
        q = p - gap * fn[t]                                   # projection onto the triangle's plane
        v0, v1, v2 = B[t] - A[t], C[t] - A[t], q - A[t]
        d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        bv = (d11 * d20 - d01 * d21) / den
        bw = (d00 * d21 - d01 * d20) / den
        bu = 1.0 - bv - bw
        if min(bu, bv, bw) < -0.02:
            continue                                          # not straight under this triangle
        if best is None or -gap < best[0]:
            best = (-gap, t, (max(bu, 0), max(bv, 0), max(bw, 0)))
    if best is None:
        # under a fold of the cup (a vertex or edge where its triangles bend away): the projection lands in none of
        # them, yet the nearest cup point is straight above - Inase a08's left nipple, 3.3 mm under the cup, came
        # out 2.7 mm in half of the gesture dance.  The nearest point counts when the offset runs mostly along the
        # normal (as chest_clip_blender.py pairs them).
        for t in near:
            x, bary = closest_on_triangle(p, A[t], B[t], C[t])
            off = p - x
            dist = float(np.linalg.norm(off))
            gap = float(off @ fn[t])
            if dist > depth or gap >= 0 or -gap < 0.7 * dist:
                continue
            if best is None or dist < best[0]:
                best = (dist, t, bary)
    if best is None:
        continue
    _, t, bary = best
    s = sum(bary)
    new = {}
    for vert, wt in zip(cup[t], bary):
        for b, x in weights[vert].items():
            new[b] = new.get(b, 0.0) + x * wt / s
    if m.vertices[i].weight.type == 3:
        continue                                              # SDEF keeps its own (none on g05's body)
    old = weights[i]
    diff = sum(abs(new.get(b, 0) - old.get(b, 0)) for b in set(new) | set(old)) / 2
    if diff < 1e-3:
        continue
    write_weights(m.vertices[i].weight, new)
    changed += 1
    moved.append(diff)
print("fitted-body vertices under a cup that now copy it: %d (weight moved: mean %.3f, max %.3f)" % (
    changed, float(np.mean(moved)) if moved else 0, float(np.max(moved)) if moved else 0))
pmx.save(args.out, m, add_uv_count=m.header.additional_uvs)
print("wrote", args.out)
