"""ROE _full PMX: every fitted-body vertex hidden UNDER a breast cup takes the cup's weights at the point right above it,
so the two move as one and the skin cannot come out through the cup however the breast swings.

Why (g05, 10-18): after pmx_body_follows_cups.py the swing shares match on average, but g05's nipples sit only
0.7-6 mm under the white chest straps (16 vertices per side < 1 mm), and the remaining small differences (the tool
blends the k nearest cups' swing share, keeps the body's own bone split) still pushed a nipple tip through a strap in
a few frames of the gesture dance.  Here the covered vertices copy the cup exactly: the cup triangle whose surface is
straight above the vertex (projection inside it, offset along its normal, behind it by at most --depth cm) gives the
barycentric blend of its three vertices' weights.  Visible skin (not under a cup) is left as it is; the nude copy,
positions, normals, morphs, bones, bodies and joints are untouched.
    python pmx_body_cover_cups.py in.pmx out.pmx [--depth 1.0] [--body pc_g01_nk_body] [--skip riband]"""
import argparse
import os
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
args = ap.parse_args()
pmx = cc.load_pmx_module(cc.find_pmx_module())
m = pmx.load(args.src)
names = [b.name for b in m.bones]
kids = {}
for i, b in enumerate(m.bones):
    if b.parent is not None and b.parent >= 0:
        kids.setdefault(b.parent, []).append(i)
tree = set()
for side in ("左胸", "右胸"):
    if side in names:
        stack = [names.index(side)]
        while stack:
            k = stack.pop()
            if names[k].lower().startswith(args.skip):
                continue
            tree.add(k)
            stack.extend(kids.get(k, []))
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
cup = np.array([t for n, t in tris if "_nk_" not in n and n != body_mat and all(share[v] >= 0.3 for v in t)])
print("cup triangles: %d" % len(cup))
A, B, C = co[cup[:, 0]], co[cup[:, 1]], co[cup[:, 2]]
fn = np.cross(B - A, C - A)
fn /= np.linalg.norm(fn, axis=1)[:, None]
vn = np.array([v.normal for v in m.vertices], float)[cup].mean(1)        # outward, as the vertex normals say
fn *= np.where((fn * vn).sum(1) < 0, -1.0, 1.0)[:, None]
cent = (A + B + C) / 3
depth = args.depth / 8.0
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
