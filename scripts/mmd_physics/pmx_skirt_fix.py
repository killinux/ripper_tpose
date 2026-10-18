"""Skirt rigid bodies on their cloth, and skirt chains joined where the cloth is one piece - for a PMX whose skirt
physics was built by mmd_cloth_physics (or anything else) and goes through the legs.

Why (ROE Inase a08, 2026-10-18): the archived a08 skirt went through both thighs and the greaves in every dance.
Besides the collision groups (cloth_collision_pmx.py), two things in the skirt itself were wrong:

1. **Boxes across their panel.**  The whole front chain on both sides (and a few lower back pieces) had boxes whose
   thin side faced sideways - fins sticking forward from the thigh instead of plates lying on the panel, 60-73 deg
   off.  The panel reached up to 7 cm past the box on both sides, so a thigh coming forward slid past the box straight
   into the cloth.  ``--boxes`` turns every box that is more than ``--max-angle`` off its panel back onto it: X = the
   panel's normal (the thinnest direction of the vertices whose strongest bone is the body's bone), Z along the chain,
   width and length from the panel, thickness kept, the inner face on the panel's innermost points (the side facing
   the nearest body collider).  Chain roots (a dynamic body hung on a bone-following one, e.g. a hip plate) and pieces
   with fewer than 20 vertices are left alone.
2. **Chains joined across the legs.**  mmd_cloth_physics joins neighbouring chains row by row ("H." joints) after
   sorting them by the angle of their ROOT bones round the waist.  a08's side, front and back chains all start under
   one hip plate, so the order came out wrong: the left front panel was tied to the left back panel through the
   thigh, the right front one to the back centre across the right thigh, the right side to the back instead of the
   front, and four joints tied a body to itself.  The hip chains hung from their front end only, though their back
   end is glued to the hip plate in the mesh.  ``--links`` rebuilds these joints from the mesh: two bones "share cloth"
   when at least ``--min-shared`` vertices carry weight (> 0.05) from both; a body is joined to the bone it shares most
   cloth with in each other chain (parent / child excluded); joints between bodies that share no cloth, or a body with
   itself, go; the missing ones are added like the model's own (limits / springs of the nearest existing good one, at
   the midpoint, X along the link, Y up), a chain end that shares cloth with a chain root (the hip plate) is attached
   to it with the chain's own joint limits, at the shared vertices.

Run it BEFORE cloth_collision_pmx.py (which then fits the body colliders and the groups to the turned boxes):

    python pmx_skirt_fix.py in.pmx fixed.pmx                      # --boxes and --links (the default: both)
    python pmx_skirt_fix.py in.pmx - --dry-run                    # only print
    python cloth_collision_pmx.py fixed.pmx out.pmx --colliders-from full_fitted.pmx

Needs only Python + numpy and mmd_tools' pmx module (as cloth_collision_pmx.py).  Units are PMX units.
"""
import argparse
import math
import re
import sys
from collections import Counter, defaultdict

import numpy as np

import cloth_collision_pmx as cc

LATTICE = ("H.", "R.", "A.")


def strongest_bones(pmx, model):
    names = [b.name for b in model.bones]
    out = []
    for v in model.vertices:
        w = cc.weights_of(pmx, v)
        out.append(names[max(w, key=lambda t: t[1])[0]] if w else "")
    return np.array(out, dtype=object)


def chain_parents(model, dynamic):
    """dynamic body -> the body its chain joint hangs it on (lattice joints left out)."""
    parent = {}
    for j in model.joints:
        a, b = j.src_rigid, j.dest_rigid
        if b in dynamic and a is not None and a >= 0 and a != b and not j.name.startswith(LATTICE):
            parent.setdefault(b, a)
    return parent


def turn_boxes(pmx, model, pat, max_angle, log, seat=0.0):
    names = [b.name for b in model.bones]
    co = np.array([v.co for v in model.vertices], float)
    strong = strongest_bones(pmx, model)
    followers = [cc.Shape.of(r) for r in model.rigids if r.mode == 0 and r.type != 1 and r.bone is not None
                 and r.bone >= 0 and names[r.bone] in cc.CLASS_OF]
    dynamic = {i for i, r in enumerate(model.rigids) if r.mode in (1, 2)}
    parent = chain_parents(model, dynamic)
    turned = 0
    for i, r in enumerate(model.rigids):
        if r.type != 1 or i not in dynamic or r.bone is None or r.bone < 0 or not pat.search(names[r.bone]):
            continue
        if parent.get(i) not in dynamic:
            continue                                      # a chain root (hip plate): its mesh wraps the hip
        P = co[strong == names[r.bone]]
        if len(P) < 20 or not followers:
            continue
        s = cc.Shape.of(r)
        n = np.linalg.eigh(np.cov((P - P.mean(0)).T))[1][:, 0]
        angle = math.degrees(math.acos(min(1.0, abs(n @ s.R[:, 0]))))
        if angle <= max_angle:
            if seat <= 0:
                continue
            # a box lying on its panel, but the panel's inner side reaches past the box's inner face: slide it in
            x = s.R[:, 0]
            near = min(followers, key=lambda f: cc.surface_distance(s.c[None], f)[0])
            inner = 1.0 if ((near.seg[0] + near.seg[1]) / 2 - s.c) @ x > 0 else -1.0
            reach = float(np.percentile(((P - s.c) @ x) * inner, 97))       # how far the panel goes towards the body
            over = reach - float(s.size[0])
            if over > seat:
                # never deeper into a body collider than cloth_collision_pmx.py lets a body start (its tolerance)
                start = max(cc.depth(s, f) for f in followers)
                for share in (1.0, 0.75, 0.5, 0.25):
                    moved = cc.Shape(s.kind, s.c + x * inner * over * share, s.R, s.size)
                    if max(cc.depth(moved, f) for f in followers) <= max(start, cc.DEFAULTS["tolerance"]):
                        break
                else:
                    log("  box %-14s on its panel, the cloth reaches %.1f cm past it, but moving it in would put it "
                        "inside the body: left" % (r.name, over * 8))
                    continue
                r.location = [float(v) for v in moved.c]
                log("  box %-14s %4d vertices, on its panel (%4.1f deg) but the cloth reaches %.1f cm past its inner "
                    "face: moved in %.1f cm" % (r.name, len(P), angle, over * 8, over * share * 8))
                turned += 1
            continue
        along = s.R[:, 2] - (s.R[:, 2] @ n) * n            # the boxes run along the chain on local Z
        along /= np.linalg.norm(along)
        R = np.column_stack([n, np.cross(along, n), along])
        L = (P - P.mean(0)) @ R
        lo, hi = np.percentile(L, 3, axis=0), np.percentile(L, 97, axis=0)
        mid = P.mean(0) + R @ ((lo + hi) / 2)
        near = min(followers, key=lambda f: cc.surface_distance(mid[None], f)[0])
        inner = 1.0 if ((near.seg[0] + near.seg[1]) / 2 - mid) @ n > 0 else -1.0
        half_t = float(s.size[0])
        edge = hi[0] if inner > 0 else lo[0]              # the panel's innermost points along its normal
        centre = P.mean(0) + R @ np.array([edge - inner * half_t, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2])
        size = [half_t, float(max((hi[1] - lo[1]) / 2, half_t)), float(max((hi[2] - lo[2]) / 2, half_t))]
        log("  box %-14s %4d vertices, %4.1f deg off its panel: size %s -> %s, moved %.1f cm" % (
            r.name, len(P), angle, np.round(s.size, 2), np.round(size, 2), np.linalg.norm(centre - s.c) * 8))
        r.location = [float(v) for v in centre]
        r.rotation = [float(v) for v in cc.euler_of(R)]
        r.size = size
        turned += 1
    return turned


def relink(pmx, model, pat, min_shared, log):
    R, B = model.rigids, model.bones
    body_of = {}
    for i, r in enumerate(R):
        if r.mode in (1, 2) and r.bone is not None and r.bone >= 0 and pat.search(B[r.bone].name):
            body_of[r.bone] = i
    dyn = set(body_of.values())
    parent = chain_parents(model, dyn)
    children = defaultdict(list)
    for c, p in parent.items():
        children[p].append(c)

    def chain_key(i):                                     # up while the parent hangs only this one chain
        while i in parent and parent[i] in dyn and len([c for c in children[parent[i]] if c in dyn]) == 1:
            i = parent[i]
        return i

    roots = {i for i in dyn if not (i in parent and parent[i] in dyn)}
    share, where = Counter(), defaultdict(list)
    for v in model.vertices:
        bs = sorted({body_of[b] for b, w in cc.weights_of(pmx, v) if w > 0.05 and b in body_of})
        for x in range(len(bs)):
            for y in range(x + 1, len(bs)):
                share[(bs[x], bs[y])] += 1
                where[(bs[x], bs[y])].append(v.co)
    related = {(min(c, p), max(c, p)) for c, p in parent.items()}
    chains = defaultdict(list)
    for i in dyn:
        chains[chain_key(i)].append(i)
    want = set()
    for a in dyn:
        best = {}
        for c, members in chains.items():
            if a in members:
                continue
            for b in members:
                k = (min(a, b), max(a, b))
                n = share.get(k, 0)
                if n >= min_shared and k not in related and n > best.get(c, (0, None))[0]:
                    best[c] = (n, b)
        want |= {(min(a, b), max(a, b)) for n, b in best.values()}
    have, remove = {}, []
    for ji, j in enumerate(model.joints):
        a, b = j.src_rigid, j.dest_rigid
        if a not in dyn and b not in dyn:
            continue
        if a == b:
            remove.append((ji, "a body with itself"))
            continue
        k = (min(a, b), max(a, b))
        if a in dyn and b in dyn and k not in related:
            if k in want and k not in have:
                have[k] = ji
            else:
                remove.append((ji, "duplicate" if k in want else "shares %d vertices" % share.get(k, 0)))
    lattice = [model.joints[ji] for k, ji in have.items() if not ({k[0], k[1]} & roots)]
    added = []
    for k in sorted(want - set(have)):
        a, b = k
        if b in roots and a not in roots:
            a, b = b, a                                   # the root first: the body the chain end hangs on
        if a in roots:
            tpl = next((j for j in model.joints if j.dest_rigid == b and not j.name.startswith(LATTICE)), None)
            if tpl is None:
                continue
            loc, rot, name = np.mean(np.array(where[k]), axis=0), tuple(tpl.rotation), "A.%s-%s" % (R[a].name, R[b].name)
        else:
            if not lattice:
                continue
            mid = (np.array(R[a].location) + np.array(R[b].location)) / 2
            tpl = min(lattice, key=lambda j: np.linalg.norm(np.array(j.location) - mid))
            d = np.array(R[b].location) - np.array(R[a].location)
            x = np.array([d[0], 0.0, d[2]])
            x = x / np.linalg.norm(x) if np.linalg.norm(x) > 1e-6 else np.array([1.0, 0.0, 0.0])
            y = np.array([0.0, 1.0, 0.0])
            loc, rot, name = mid, cc.euler_of(np.column_stack([x, y, np.cross(x, y)])), "H.%s-%s" % (R[a].name, R[b].name)
        j = pmx.Joint()
        j.name = j.name_e = name
        j.mode, j.src_rigid, j.dest_rigid = 0, a, b
        j.location, j.rotation = [float(v) for v in loc], [float(v) for v in rot]
        for attr in ("maximum_location", "minimum_location", "maximum_rotation", "minimum_rotation", "spring_constant",
                     "spring_rotation_constant"):
            setattr(j, attr, list(getattr(tpl, attr)))
        added.append((j, share[k], tpl.name))
    for ji, why in remove:
        j = model.joints[ji]
        log("  joint - %-30s %-16s %-16s (%s)" % (j.name, R[j.src_rigid].name, R[j.dest_rigid].name, why))
    for j, n, tpl in added:
        log("  joint + %-30s %-16s %-16s (shares %d vertices; limits of %s)" % (
            j.name, R[j.src_rigid].name, R[j.dest_rigid].name, n, tpl))
    doomed = {ji for ji, _ in remove}
    model.joints = [j for ji, j in enumerate(model.joints) if ji not in doomed] + [j for j, _, _ in added]
    return len(remove), len(added), len(have)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="the fixed PMX ('-' with --dry-run)")
    ap.add_argument("--bones", default=r"skirt|skir_chain", help="regex of the skirt bones (default skirt|skir_chain)")
    ap.add_argument("--boxes", action="store_true", help="only turn the boxes onto their panels")
    ap.add_argument("--links", action="store_true", help="only rebuild the joints between chains")
    ap.add_argument("--max-angle", type=float, default=35.0, help="a box this far off its panel is turned (deg)")
    ap.add_argument("--seat", type=float, default=0.0,
                    help="also slide boxes that lie on their panel inwards when the cloth reaches this far past their "
                         "inner face (PMX units, e.g. 0.06 = 5 mm; default 0 = off)")
    ap.add_argument("--min-shared", type=int, default=8, help="vertices two bones must share to be one cloth")
    ap.add_argument("--pmx-module", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    both = not (args.boxes or args.links)
    pmx = cc.load_pmx_module(cc.find_pmx_module(args.pmx_module))
    model = pmx.load(args.input)
    pat = re.compile(args.bones, re.I)
    if both or args.boxes:
        print("boxes:")
        print("%d boxes turned onto / seated on their panel" % turn_boxes(pmx, model, pat, args.max_angle, print,
                                                                           args.seat))
    if both or args.links:
        print("joints between chains:")
        removed, added, kept = relink(pmx, model, pat, args.min_shared, print)
        print("%d kept, %d removed, %d added" % (kept, removed, added))
    if args.dry_run:
        return 0
    pmx.save(args.output, model, add_uv_count=model.header.additional_uvs)
    print("wrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
