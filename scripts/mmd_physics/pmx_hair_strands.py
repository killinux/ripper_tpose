# -*- coding: utf-8 -*-
"""Finer hair physics for a PMX: one hair chain (a sheet of hair on a single bone chain) -> N strands x M segments,
each strand its own bone chain with its own rigid bodies and joints, the hair mesh weighted smoothly across them.

  blender -b --factory-startup --python pmx_hair_strands.py -- SRC.pmx OUT.pmx \
          --chain "^hair back [a-f]$=7x8:後髪" [--chain "^hair front [A-C]$=3x3:前髪"] [--limit 10]

What it does, per --chain (a regex for the chain's bone names, NxM strands x segments, a name stem for the new bones):
- the old chain's polyline (bone heads + the last tail) gives every vertex it carries a length t along it and a side
  offset u across it (the sheet's width axis = chain direction x the model's front, i.e. left-right for back hair);
  the width is normalised per height, left and right separately, so the strands follow the hair's own outline;
- N strand chains of M bones are placed at the centroids of the hair around (strand centre, segment boundary),
  smoothed along the chain; parents: the old chain's parent (頭) -> segment 1 -> ... -> segment M;
- the weight the vertex had on the old chain is spread over the two nearest strands (linear across the width) x the
  two nearest segments (tent between segment middles); its weights on other bones (頭 ...) stay exactly as they were,
  so the scalp stays put - the new bones take the slots left (PMX allows 4), the largest first, scaled back up to the
  old chain's share (BDEF1/2/4);
- one capsule per new bone along it (radius ~0.45 of the strand spacing), the old chain's rigid bodies copied for
  group / mask / mass / damping / mode level by level (a kinematic first segment stays kinematic), joints at every
  bone head like the old ones (world-aligned, +-limit degrees, no springs); the old chain's bodies and joints are
  removed, its bones stay (now without weight);
- everything else is written back unchanged: mmd_tools' PMX reader/writer, with the extra UV count kept and the
  texture paths made relative again, rewrites the source byte for byte when nothing is changed (checked on the three
  Tifa AC 18 PMX).
Prints HAIR_STRANDS_REPORT={json}.
"""
import argparse
import copy
import json
import math
import os
import re
import sys

import numpy as np

import addon_utils

addon_utils.enable("mmd_tools", default_set=False)
from mathutils import Matrix, Vector  # noqa: E402
from mmd_tools.core import pmx  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--chain", action="append", default=[], help='"REGEX=NxM:STEM", e.g. "^hair back [a-f]$=7x8:後髪"')
ap.add_argument("--limit", type=float, default=10.0, help="joint rotation limit per segment, degrees (the old: 10)")
ap.add_argument("--radius", type=float, default=0.45, help="capsule radius as a share of the strand spacing")
args = ap.parse_args(argv)
FRONT = np.array([0.0, 0.0, -1.0])         # PMX: the model faces -Z, +X is her left


def weights_of(v):
    w = v.weight
    if w.type == pmx.BoneWeight.BDEF1:
        return [(w.bones[0], 1.0)]
    if w.type in (pmx.BoneWeight.BDEF2, pmx.BoneWeight.SDEF):
        first = w.weights.weight if w.type == pmx.BoneWeight.SDEF else w.weights[0]
        return [(w.bones[0], first), (w.bones[1], 1.0 - first)]
    return [(b, x) for b, x in zip(w.bones, w.weights)]


def set_weights(v, others, new, w_chain):
    """The vertex's other bones (頭 ...) keep their weights; the new strand bones fill the slots left (PMX: 4), the
    largest first, scaled back up to the share the old chain had."""
    others = sorted([(b, x) for b, x in others if x > 1e-6], key=lambda p: -p[1])[:3]
    merged = {}
    for b, x in new:
        if x > 1e-6:
            merged[b] = merged.get(b, 0.0) + x
    new = sorted(merged.items(), key=lambda p: -p[1])[:4 - len(others)]
    s = sum(x for _, x in new)
    top = others + ([(b, x * w_chain / s) for b, x in new] if s > 0 else [])
    total = sum(x for _, x in top)
    top = [(b, x / total) for b, x in top]
    bw = pmx.BoneWeight()
    if len(top) == 1:
        bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF1, [top[0][0]], []
    elif len(top) == 2:
        bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF2, [top[0][0], top[1][0]], [top[0][1]]
    else:
        top += [(top[0][0], 0.0)] * (4 - len(top))
        bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF4, [b for b, _ in top], [x for _, x in top]
    v.weight = bw
    return len([1 for _, x in top if x > 0])


def tail_of(m, i):
    b = m.bones[i]
    dc = b.displayConnection
    if isinstance(dc, int):
        return np.array(m.bones[dc].location) if dc >= 0 else np.array(b.location)
    return np.array(b.location) + np.array(dc)


def chain_of(m, pattern):
    rx = re.compile(pattern)
    members = [i for i, b in enumerate(m.bones) if rx.search(b.name)]
    ms = set(members)
    roots = [i for i in members if m.bones[i].parent not in ms]
    if len(roots) != 1:
        raise SystemExit("%s: %d chain roots (%s)" % (pattern, len(roots), [m.bones[i].name for i in roots]))
    order = [roots[0]]
    while True:
        kids = [i for i in members if m.bones[i].parent == order[-1]]
        if not kids:
            break
        if len(kids) > 1:
            raise SystemExit("%s: branches at %s" % (pattern, m.bones[order[-1]].name))
        order.append(kids[0])
    if len(order) != len(members):
        raise SystemExit("%s: not one chain" % pattern)
    return order


def polyline_param(points, p):
    """Arc length along the polyline of the closest point to each p (n x 3), and that closest point."""
    best_t = np.full(len(p), np.inf)
    best_d = np.full(len(p), np.inf)
    best_q = np.zeros_like(p)
    acc = 0.0
    for a, b in zip(points[:-1], points[1:]):
        ab = b - a
        L = float(np.linalg.norm(ab))
        s = np.clip(((p - a) @ ab) / (L * L), -np.inf if acc == 0.0 else 0.0, 1.0)   # the first segment extends up
        q = a + np.outer(s, ab)
        d = np.linalg.norm(p - q, axis=1)
        better = d < best_d
        best_d[better], best_t[better], best_q[better] = d[better], acc + s[better] * L, q[better]
        acc += L
    return best_t, best_q, acc


def blender_euler_to_pmx(R_pmx_axes):
    """Rotation whose columns are the body's local X, Y, Z in PMX space -> PMX rigid / joint rotation (radians),
    the inverse of mmd_tools' import (Blender = PMX.xzy, rotation = PMX.rotation.xzy * -1, Euler YXZ; the PMX capsule
    axis Y is Blender's local Z)."""
    swap = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=np.float64)     # PMX xyz <-> Blender xzy
    x_b = swap @ R_pmx_axes[:, 0]
    z_b = swap @ R_pmx_axes[:, 1]          # the PMX local Y (capsule axis) is Blender's local Z
    y_b = np.cross(z_b, x_b)
    M = Matrix([list(x_b), list(y_b), list(z_b)]).transposed()
    e = M.to_euler("YXZ")
    return [-e.x, -e.z, -e.y]


def strands(m, pattern, n, segs, stem, report):
    chain = chain_of(m, pattern)
    cset = set(chain)
    parent = m.bones[chain[0]].parent
    pts = np.array([m.bones[i].location for i in chain] + [tail_of(m, chain[-1])], dtype=np.float64)
    co = np.array([v.co for v in m.vertices], dtype=np.float64)
    carried = []                                   # (vertex index, weight on the chain)
    for vi, v in enumerate(m.vertices):
        w = sum(x for b, x in weights_of(v) if b in cset)
        if w > 1e-6:
            carried.append((vi, w))
    vid = np.array([c[0] for c in carried])
    wold = np.array([c[1] for c in carried])
    p = co[vid]
    t, q, length = polyline_param(pts, p)
    d = pts[-1] - pts[0]
    d /= np.linalg.norm(d)
    side = np.cross(d, FRONT)
    side /= np.linalg.norm(side)
    u = (p - q) @ side
    t = np.maximum(t, 0.0)
    strong = wold >= 0.3
    hair_end = float(np.percentile(t[strong], 99.0))
    # the sheet's half widths, left / right, per height band (smoothed), so the strands follow its outline
    bands = 12
    edges = np.linspace(0.0, hair_end, bands + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    hl, hr = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (t >= a) & (t <= b) & strong
        hl.append(np.percentile(-u[sel & (u < 0)], 97) if (sel & (u < 0)).sum() > 10 else np.nan)
        hr.append(np.percentile(u[sel & (u > 0)], 97) if (sel & (u > 0)).sum() > 10 else np.nan)

    def fill(arr):
        arr = np.array(arr, dtype=np.float64)
        ok = ~np.isnan(arr)
        arr = np.interp(np.arange(len(arr)), np.flatnonzero(ok), arr[ok])
        return np.convolve(np.pad(arr, 1, mode="edge"), [0.25, 0.5, 0.25], mode="valid")
    hl, hr = fill(hl), fill(hr)
    half_l = np.interp(t, mids, hl)
    half_r = np.interp(t, mids, hr)
    un = np.clip(np.where(u < 0, u / half_l, u / half_r), -1.0, 1.0)
    centres = -1.0 + (2.0 * np.arange(n) + 1.0) / n
    # lateral weights: linear between neighbouring strand centres, the outer strands take the edges
    lat = np.zeros((len(p), n))
    if n == 1:
        lat[:, 0] = 1.0
    else:
        pos = np.clip((un - centres[0]) / (centres[1] - centres[0]), 0.0, n - 1.0)
        lo = np.floor(pos).astype(int).clip(0, n - 2)
        f = pos - lo
        lat[np.arange(len(p)), lo] = 1.0 - f
        lat[np.arange(len(p)), lo + 1] += f
    # longitudinal weights: tent between segment middles
    bounds = np.linspace(0.0, hair_end, segs + 1)
    segmid = (bounds[:-1] + bounds[1:]) / 2
    lon = np.zeros((len(p), segs))
    if segs == 1:
        lon[:, 0] = 1.0
    else:
        pos = np.clip((t - segmid[0]) / (segmid[1] - segmid[0]), 0.0, segs - 1.0)
        lo = np.floor(pos).astype(int).clip(0, segs - 2)
        f = pos - lo
        lon[np.arange(len(p)), lo] = 1.0 - f
        lon[np.arange(len(p)), lo + 1] += f
    # bone heads: centroid of the hair around (strand centre, segment boundary), smoothed along the strand
    su, st = 1.0 / n, (hair_end / segs) * 0.5
    heads = np.zeros((n, segs + 1, 3))
    for s in range(n):
        for k in range(segs + 1):
            g = np.exp(-((un - centres[s]) / su) ** 2 - ((t - bounds[k]) / st) ** 2) * strong
            if g.sum() < 1e-3:
                g = np.exp(-((un - centres[s]) / (2 * su)) ** 2 - ((t - bounds[k]) / (2 * st)) ** 2)
            heads[s, k] = (g[:, None] * p).sum(axis=0) / g.sum()
        sm = heads[s].copy()
        sm[1:-1] = 0.25 * heads[s, :-2] + 0.5 * heads[s, 1:-1] + 0.25 * heads[s, 2:]
        heads[s] = sm
    # -- bones --------------------------------------------------------------------------------------------------
    template = m.bones[chain[min(1, len(chain) - 1)]]
    stem_e = os.path.commonprefix([m.bones[i].name_e or m.bones[i].name for i in chain]).strip() or "hair"
    ids = np.zeros((n, segs), dtype=int)
    for s in range(n):
        for k in range(segs):
            b = copy.deepcopy(template)
            b.name = "%s%d_%d" % (stem, s + 1, k + 1)
            b.name_e = "%s s%d %d" % (stem_e, s + 1, k + 1)
            b.location = list(map(float, heads[s, k]))
            b.parent = parent if k == 0 else int(ids[s, k - 1])
            ids[s, k] = len(m.bones)
            m.bones.append(b)
        for k in range(segs):
            b = m.bones[ids[s, k]]
            b.displayConnection = int(ids[s, k + 1]) if k + 1 < segs else list(map(float, heads[s, segs] - heads[s, segs - 1]))
    # -- weights ------------------------------------------------------------------------------------------------
    used = {1: 0, 2: 0, 3: 0, 4: 0}
    for j, vi in enumerate(vid):
        v = m.vertices[vi]
        others = [(b, x) for b, x in weights_of(v) if b not in cset]
        new = []
        for s in np.flatnonzero(lat[j] > 1e-6):
            for k in np.flatnonzero(lon[j] > 1e-6):
                new.append((int(ids[s, k]), wold[j] * lat[j, s] * lon[j, k]))
        used[set_weights(v, others, new, wold[j])] += 1
    # -- rigid bodies: remove the chain's, one capsule per new bone ------------------------------------------------
    old_bodies = {r.bone: i for i, r in enumerate(m.rigids) if r.bone in cset}
    levels = [old_bodies.get(i) for i in chain]
    if any(x is None for x in levels):
        raise SystemExit("%s: a chain bone has no rigid body" % pattern)
    parent_body = next((i for i, r in enumerate(m.rigids) if r.bone == parent), None)
    if parent_body is None:
        raise SystemExit("%s: the chain's parent bone %s has no rigid body" % (pattern, m.bones[parent].name))
    new_bodies = []
    spacing = (np.interp(segmid, mids, hl) + np.interp(segmid, mids, hr)) / n
    for s in range(n):
        for k in range(segs):
            old = m.rigids[levels[min(len(levels) - 1, round(k * (len(levels) - 1) / max(1, segs - 1)))]]
            r = copy.deepcopy(old)
            a, b = heads[s, k], heads[s, k + 1]
            axis = b - a
            ln = float(np.linalg.norm(axis))
            ydir = -axis / ln                       # like the old bodies: local +Y points up the chain
            xdir = side - (side @ ydir) * ydir
            xdir /= np.linalg.norm(xdir)
            zdir = np.cross(xdir, ydir)
            radius = float(min(args.radius * spacing[k], 0.3 * ln))
            r.name = m.bones[ids[s, k]].name
            r.name_e = m.bones[ids[s, k]].name_e
            r.bone = int(ids[s, k])
            r.type = 2
            r.size = [radius, max(ln * 0.9 - 2 * radius, 0.05), 0.0]
            r.location = list(map(float, (a + b) / 2))
            r.rotation = blender_euler_to_pmx(np.column_stack([xdir, ydir, zdir]))
            new_bodies.append(r)
    removed = sorted(old_bodies.values())
    keep = [i for i in range(len(m.rigids)) if i not in set(removed)]
    remap = {old: new for new, old in enumerate(keep)}
    old_joints = len(m.joints)
    m.joints = [j for j in m.joints if j.src_rigid in remap and j.dest_rigid in remap]
    for j in m.joints:
        j.src_rigid, j.dest_rigid = remap[j.src_rigid], remap[j.dest_rigid]
    dropped_joints = old_joints - len(m.joints)
    m.rigids = [m.rigids[i] for i in keep]
    parent_body = remap[parent_body]
    base = len(m.rigids)
    m.rigids.extend(new_bodies)
    # -- joints: at every new bone head, world-aligned like the old ones --------------------------------------------
    chain_names = {m.bones[i].name for i in chain}
    template_joint = next((j for j in pmx_joints_backup if j.name in chain_names), None)
    lim = math.radians(args.limit)
    for s in range(n):
        for k in range(segs):
            jt = copy.deepcopy(template_joint) if template_joint else pmx.Joint()
            jt.name = m.bones[ids[s, k]].name
            jt.name_e = m.bones[ids[s, k]].name_e
            jt.mode = 0
            jt.src_rigid = parent_body if k == 0 else base + s * segs + k - 1
            jt.dest_rigid = base + s * segs + k
            jt.location = list(map(float, heads[s, k]))
            jt.rotation = [0.0, 0.0, 0.0]
            jt.minimum_location, jt.maximum_location = [0.0] * 3, [0.0] * 3
            jt.minimum_rotation, jt.maximum_rotation = [-lim] * 3, [lim] * 3
            jt.spring_constant, jt.spring_rotation_constant = [0.0] * 3, [0.0] * 3
            m.joints.append(jt)
    report[pattern] = {
        "old_chain": [m.bones[i].name for i in chain], "parent": m.bones[parent].name, "strands": n, "segments": segs,
        "vertices": int(len(vid)), "hair_length": round(hair_end, 3), "width_top": round(float(hl[0] + hr[0]), 3),
        "width_bottom": round(float(hl[-1] + hr[-1]), 3), "new_bones": [int(ids[0, 0]), int(ids[-1, -1])],
        "influences": used, "removed_bodies": len(removed), "removed_joints": dropped_joints,
        "new_bodies": len(new_bodies), "new_joints": n * segs,
        "capsule_radius": [round(float(min(args.radius * spacing[k], 0.3 * hair_end / segs)), 3) for k in range(segs)],
    }


m = pmx.load(args.src)
raw = open(args.src, "rb").read(16)
src_dir = os.path.dirname(os.path.abspath(args.src))
out_dir = os.path.dirname(os.path.abspath(args.out))
for tex in m.textures:      # absolute after load; the writer stores them relative to the output's folder, so point them
    tex.path = os.path.join(out_dir, os.path.relpath(tex.path, src_dir))   # there: the same strings as in the source
pmx_joints_backup = copy.deepcopy(m.joints)
report = {"src": args.src, "out": args.out, "limit_deg": args.limit}
for spec in args.chain or ["^hair back [a-f]$=7x8:後髪"]:
    pattern, rest = spec.rsplit("=", 1)
    shape, stem = rest.split(":", 1)
    n, segs = (int(x) for x in shape.lower().split("x"))
    strands(m, pattern, n, segs, stem, report)
report.update(bones=len(m.bones), rigids=len(m.rigids), joints=len(m.joints))
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
pmx.save(args.out, m, add_uv_count=raw[10])
print("HAIR_STRANDS_REPORT=" + json.dumps(report, ensure_ascii=False))
