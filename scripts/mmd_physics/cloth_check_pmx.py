"""Read-only health check of the cloth physics in PMX files: the faults that put ROE Inase a08's skirt through her
legs (2026-10-18), counted per model.

    python cloth_check_pmx.py a.pmx [b.pmx ...] [--json out.json] [--csv out.csv]

Over the dynamic bodies of each model (breasts left out, cloth_collision_pmx.py's bust regex):
- boxes off their cloth: a BOX whose thin axis (of the two across its bone) is more than --max-angle off the normal
  of the cloth its bone drives (>= 20 vertices whose strongest bone it is, flat enough to have a normal).
  mmd_cloth_physics' box frames were left-handed until 2026-10-18, so most of its boxes were spun about their length
  (a08's front panels 60-73 deg);
- joints between bodies that share no cloth: a joint between two dynamic bodies that are not parent and child in the
  bone tree, whose bones' cloth shares neither a vertex nor a mesh edge; how many of those pass through a body
  collider (a08: the front panels tied to the back ones through the thighs); joints of a body with itself;
- cloth and the legs: dynamic bodies within 5 cm of a leg collider at rest that can never collide with it (group /
  mask: mmd_cloth_physics' "near" group 10 collides with nothing), and cloth starting more than 8 mm inside a
  collider it does collide with (pushed out at the first frame);
- loose ends: a chain's last body whose cloth is glued to another body it has no joint to - >= 8 vertices driven by
  both and NOT by the bone above the last one (that much is the chain's own smooth skinning), at the far end of its
  bone or most of what it drives besides; a body two joints away does not count (a joint to it would close a
  triangle and lock the last link).  a08's hip chains: back end glued to the hip plate, hanging from the front only.
  Until 2026-10-24 the shared vertices of the bone above were counted too, which made a link two up the chain or the
  neighbouring chain's link above look glued (ROE scan: 817 loose ends in 166 models, 235 in 70 with the fix).
One line per model and a total; --json keeps the bones of every fault, --csv one row per model.  Units: PMX units
(1 = 8 cm at mmd_tools' usual 0.08 import); the printed lengths are cm.  Needs numpy and mmd_tools' pmx module, as
cloth_collision_pmx.py.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cloth_collision_pmx as cc  # noqa: E402

CM = 8.0                    # cm per PMX unit
NEAR_LEGS = 5.0 / CM        # "near a leg collider"
DEEP_START = 0.8 / CM       # "starts inside"
GLUED = 8                   # shared vertices that make a glued end


def mesh_contact(pmx, model):
    """Strongest bone per vertex, and per bone pair the vertices they share (weight > 0.05 from both) plus the mesh
    edges running from one's cloth into the other's."""
    strongest = np.full(len(model.vertices), -1)
    shared, driven = Counter(), Counter()
    where = defaultdict(list)
    for k, v in enumerate(model.vertices):
        w = cc.weights_of(pmx, v)
        if not w:
            continue
        strongest[k] = max(w, key=lambda t: t[1])[0]
        bs = sorted({b for b, x in w if x > 0.05})
        driven.update(bs)
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                shared[(bs[i], bs[j])] += 1
                where[(bs[i], bs[j])].append(k)
    faces = np.array([list(f) for f in model.faces], dtype=np.int64).reshape(-1, 3)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    a, b = strongest[edges[:, 0]], strongest[edges[:, 1]]
    keep = (a >= 0) & (b >= 0) & (a != b)
    across = Counter(zip(np.minimum(a[keep], b[keep]).tolist(), np.maximum(a[keep], b[keep]).tolist()))
    return strongest, shared, across, where, driven


def collides(r1, r2):
    """MMD filters both ways: a set bit in the file's mask means 'collides with that group'."""
    return bool((r1.collision_group_mask >> r2.collision_group_number) & 1) and \
        bool((r2.collision_group_mask >> r1.collision_group_number) & 1)


def through(c1, c2, colliders, shapes, inside=0.1):
    """Does the straight line between two body centres run through a body collider (deeper than ``inside``)?"""
    pts = c1 + (c2 - c1) * np.linspace(0.15, 0.85, 15)[:, None]
    return any((cc.surface_distance(pts, shapes[i]) < -inside).any() for i in colliders)


def check(pmx, path, max_angle, bust_re):
    model = pmx.load(path)
    bones, rigids = model.bones, model.rigids
    bname = lambda r: bones[r.bone].name if r.bone is not None and 0 <= r.bone < len(bones) else ""   # noqa: E731
    dyn = [i for i, r in enumerate(rigids) if r.mode in (1, 2) and not bust_re.search(bname(r))
           and not bust_re.search(r.name)]
    colliders = [i for i, r in enumerate(rigids) if r.mode == 0 and bname(r) in cc.CLASS_OF]
    legs = [i for i in colliders if cc.CLASS_OF[bname(rigids[i])] == "legs"]
    out = {"pmx": path, "rigids": len(rigids), "dynamic": len(dyn), "joints": len(model.joints)}
    if not dyn:
        return out
    shapes = {i: cc.Shape.of(r) for i, r in enumerate(rigids)}
    co = np.array([v.co for v in model.vertices], float)
    strongest, shared, across, where, driven = mesh_contact(pmx, model)
    body_on = {}
    for i, r in enumerate(rigids):
        if r.bone is not None and 0 <= r.bone < len(bones):
            body_on.setdefault(r.bone, i)

    def parent_body(i):
        b = bones[rigids[i].bone].parent if rigids[i].bone is not None and rigids[i].bone >= 0 else -1
        while b is not None and 0 <= b < len(bones):
            if b in body_on:
                return body_on[b]
            b = bones[b].parent
        return None

    def contact(i, j):
        a, b = rigids[i].bone, rigids[j].bone
        if a is None or b is None or a < 0 or b < 0:
            return 0
        k = (min(a, b), max(a, b))
        return shared.get(k, 0) + across.get(k, 0)

    dset = set(dyn)
    dset_bones = {rigids[i].bone for i in dyn}
    parent = {i: parent_body(i) for i in dyn}
    # boxes off their cloth
    boxes, off = 0, []
    for i in dyn:
        r = rigids[i]
        if r.type != 1:
            continue
        P = co[strongest == r.bone]
        if len(P) < 20:
            continue
        lam, vec = np.linalg.eigh(np.cov((P - P.mean(0)).T))
        if lam[1] <= 0 or lam[0] / lam[1] > 0.3:
            continue                                       # not flat: no normal to compare with
        s = shapes[i]
        along = bone_direction(bones, r.bone, dset_bones)
        if along @ along > 1e-12:                         # the axis along the bone is its length, whatever its size
            if abs(float(vec[:, 0] @ along)) > 0.9 * np.linalg.norm(along):
                continue                                   # a bone sticking out of its skin (SB Eve's armpit helpers)
            side = [k for k in range(3) if k != int(np.argmax(np.abs(s.R.T @ along)))]
            thin = s.R[:, min(side, key=lambda k: s.size[k])]
        else:
            thin = s.R[:, int(np.argmin(s.size))]
        boxes += 1
        angle = math.degrees(math.acos(min(1.0, abs(float(vec[:, 0] @ thin)))))
        if angle > max_angle:
            off.append((bname(r), round(angle, 1), int(len(P))))
    out["boxes_checked"], out["boxes_off"] = boxes, off
    # joints
    no_cloth, body_cross, self_j, joined = [], [], [], defaultdict(set)
    for j in model.joints:
        a, b = j.src_rigid, j.dest_rigid
        if a is None or b is None or a < 0 or b < 0:
            continue
        joined[a].add(b)
        joined[b].add(a)
        if a == b:
            if a in dset:
                self_j.append(j.name)
            continue
        if a not in dset or b not in dset or parent.get(b) == a or parent.get(a) == b:
            continue
        if contact(a, b) == 0:
            no_cloth.append((j.name, bname(rigids[a]), bname(rigids[b])))
            if through(shapes[a].c, shapes[b].c, colliders, shapes):
                body_cross.append(j.name)
    out["joints_no_cloth"], out["joints_through_body"], out["joints_self"] = no_cloth, body_cross, self_j
    # legs
    near, ignoring, deep = [], [], []
    for i in dyn:
        s = shapes[i]
        for c in legs:
            d = cc.depth(s, shapes[c])
            if d > -NEAR_LEGS:
                near.append(i)
                if not collides(rigids[i], rigids[c]):
                    ignoring.append(i)
                break
        for c in colliders:
            if collides(rigids[i], rigids[c]) and cc.depth(s, shapes[c]) > DEEP_START:
                deep.append((bname(rigids[i]), rigids[c].name, round(float(cc.depth(s, shapes[c])) * CM, 1)))
                break
    out["near_legs"] = len(near)
    out["near_legs_bones"] = sorted({bname(rigids[i]) for i in near})
    out["ignoring_legs"] = [bname(rigids[i]) for i in ignoring]
    out["start_inside"] = deep
    # loose ends, as mmd_cloth_physics' attach_loose_ends finds them: the vertices the chain's last bone shares with
    # another body but NOT with the bone above it (that much is the chain's own smooth skinning) sit at the far end of
    # the last bone (P70 of its own vertices along it; a neighbour hanging beside it shares cloth along its side) or
    # are most of what it drives besides; a body two joints away is no loose end (a joint would weld the last link)
    children = Counter(parent[i] for i in dyn if parent[i] is not None)
    loose = []
    for i in dyn:
        if children.get(i):
            continue
        a = rigids[i].bone
        up = bones[a].parent if bones[a].parent is not None and 0 <= bones[a].parent < len(bones) else None
        above = set(where[(min(a, up), max(a, up))]) if up is not None else set()
        own = driven[a] - len(above)
        head = bone_ends(bones, a)[0]
        seg = bone_direction(bones, a, dset_bones)
        if seg @ seg < 1e-8:
            continue
        d = seg / np.linalg.norm(seg)
        mine = (co[strongest == a] - head) @ d
        far = float(np.percentile(mine, 70)) if len(mine) >= 5 else 0.7 * float(np.linalg.norm(seg))
        close = set(joined[i])
        for k in list(close):
            close |= joined[k]
        best = None
        for k, r in enumerate(rigids):
            if k == i or k == parent.get(i) or k in close or r.bone is None or r.bone < 0 or r.bone == a:
                continue
            if k not in dset and (k not in colliders or cc.CLASS_OF[bname(r)] != "torso"):
                continue                                   # a hem weighted onto a limb / the head follows it by skin
            key = (min(a, r.bone), max(a, r.bone))
            if shared.get(key, 0) < GLUED:
                continue
            pts = [v for v in where[key] if v not in above]
            n = len(pts)
            if n < GLUED or (best is not None and n <= best[1]):
                continue
            if float((co[pts].mean(0) - head) @ d) >= far or n >= 0.5 * own:
                best = (r.name, n)
        if best:
            loose.append((bname(rigids[i]),) + best)
    out["loose_ends"] = loose
    return out


def bone_direction(bones, b, cloth):
    """Which way a cloth bone runs, as mmd_cloth_physics measures it: to its child among the ``cloth`` bones, else its
    tail - unless the tail is a stub (game rigs: 1-2 cm), then on in the direction of the link above it."""
    head, tail = bone_ends(bones, b)
    kids = [k for k, bone in enumerate(bones) if bone.parent == b and k in cloth]
    if kids:
        return np.array(bones[kids[0]].location, float) - head
    up = bones[b].parent
    if up is not None and up in cloth:
        above = head - np.array(bones[up].location, float)
        if np.linalg.norm(tail - head) < 0.3 * np.linalg.norm(above):
            return above
    return tail - head


def bone_ends(bones, b):
    """Head and tail of a bone in PMX space (tail = its tail bone, or its offset)."""
    bone = bones[b]
    head = np.array(bone.location, float)
    tail = bone.displayConnection
    if isinstance(tail, int):
        return head, (np.array(bones[tail].location, float) if 0 <= tail < len(bones) else head)
    return head, head + np.array(tail, float)


def line(r):
    if not r.get("dynamic"):
        return "%-34s no dynamic bodies" % os.path.basename(r["pmx"])
    return ("%-34s dyn %3d | boxes off %2d/%-3d | joints w/o cloth %2d (through body %2d) self %d | near legs %3d, "
            "ignoring them %3d | start inside %2d | loose ends %d" % (
                os.path.basename(r["pmx"]), r["dynamic"], len(r["boxes_off"]), r["boxes_checked"],
                len(r["joints_no_cloth"]), len(r["joints_through_body"]), len(r["joints_self"]), r["near_legs"],
                len(r["ignoring_legs"]), len(r["start_inside"]), len(r["loose_ends"])))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pmx", nargs="+")
    ap.add_argument("--max-angle", type=float, default=35.0, help="a box this far off its cloth is reported (deg)")
    ap.add_argument("--bust", default=cc.DEFAULTS["bust"], help="regex: breast bodies are left out")
    ap.add_argument("--json", help="write every model's details here")
    ap.add_argument("--csv", help="write one row per model here")
    ap.add_argument("--pmx-module", default=None)
    args = ap.parse_args()
    pmx = cc.load_pmx_module(cc.find_pmx_module(args.pmx_module))
    bust_re = re.compile(args.bust, re.IGNORECASE)
    results = []
    for path in args.pmx:
        try:
            r = check(pmx, path, args.max_angle, bust_re)
        except Exception as exc:                      # one broken file must not end a batch
            r = {"pmx": path, "error": "%s: %s" % (type(exc).__name__, exc)}
            print("%-34s ERROR %s" % (os.path.basename(path), r["error"]), flush=True)
            results.append(r)
            continue
        results.append(r)
        print(line(r), flush=True)
    ok = [r for r in results if r.get("dynamic")]
    if len(results) > 1:
        print("\n%d models, %d with dynamic bodies: boxes off %d, joints without shared cloth %d (through the body "
              "%d), self %d, bodies ignoring the legs %d, starting inside %d, loose ends %d" % (
                  len(results), len(ok), sum(len(r["boxes_off"]) for r in ok),
                  sum(len(r["joints_no_cloth"]) for r in ok), sum(len(r["joints_through_body"]) for r in ok),
                  sum(len(r["joints_self"]) for r in ok), sum(len(r["ignoring_legs"]) for r in ok),
                  sum(len(r["start_inside"]) for r in ok), sum(len(r["loose_ends"]) for r in ok)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pmx", "dynamic", "boxes_checked", "boxes_off", "joints_no_cloth", "joints_through_body",
                        "joints_self", "near_legs", "ignoring_legs", "start_inside", "loose_ends", "error"])
            for r in results:
                w.writerow([r["pmx"], r.get("dynamic", ""), r.get("boxes_checked", ""), len(r.get("boxes_off", [])),
                            len(r.get("joints_no_cloth", [])), len(r.get("joints_through_body", [])),
                            len(r.get("joints_self", [])), r.get("near_legs", ""), len(r.get("ignoring_legs", [])),
                            len(r.get("start_inside", [])), len(r.get("loose_ends", [])), r.get("error", "")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
