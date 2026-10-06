"""Put a whole nude body - taken from ANOTHER PMX of the same character - under a dressed PMX's outfit, with the
衣服非表示 switch (pmx_nude_switch.py), so the 爆衣 add-on / burst_pmx_blender.py can blow the outfit off it.

For a game whose outfits carry only the skin that shows (Vindictus Fiona: shoulders and thighs under the armour, no
torso), while a nude model exists on its own skeleton (Fiona_BaseBody: the older Bip001 prework rig - spine, neck,
arm angle and fingers 8-16 cm off the outfit's rig).  Steps, all on the PMX data (no Blender):

  1. bones by name; the nude's own helpers (Bip001_* twist / muscle bones) count as their nearest ancestor that the
     dressed rig has; --map moves weights of named bones elsewhere (the nude's breast bones onto the dressed rig's
     physics breast bones, so the bust keeps its physics);
  2. the nude mesh is posed onto the dressed skeleton, forward kinematics: parents first, every bone turned (swing
     only) so it points from its joint to its first child's joint the way the dressed rig's bone does, its joint
     carried by its parent; the nude's own bone lengths stay, so its shape does too.  Roots stay put (both models
     stand in the same place: Fiona's thighs lie 0.7 cm from the nude's).  The neck's miss is spread over the spine
     and each limb root moved onto the dressed joint (Fiona's arms stood 2.7 cm off).  --normals surface (default):
     the normals turn with the posed surface, not only with the bones - the shoulders shear when joints move, and
     bone-turned normals stood up to 70 deg off there (dark creases along the clavicle on a raised arm);
  3. --snap <material>: a material both models have vertex for vertex (the face) is laid exactly onto the dressed
     model's - the head part only: per vertex, the share of weight on bones outside the head (neck, spine,
     clavicles: the bib a head swap pulled onto the old body) keeps the posed position, smoothstep 0.05 - 0.95.  The
     dressed model's eyes, teeth, lashes, hair then sit on it as before, and its expressions are copied onto it;
  4. weights onto the dressed bones (SDEF / QDEF become BDEF2 / BDEF4), the materials and textures copied in after
     --after (draw order: the opaque body before lashes and hair), names clashing with the dressed model's get _nude;
  4a. --finger-cm (default 2.5): a phalanx bone (小指１ ...) keeps no weight of a vertex lying farther than that from
     it - Fiona_BaseBody had wrist vertices on 小指１, 7 cm away, and a fist swung them out as a fin; the rest of
     the vertex's weights are renormalised (metacarpals ..０ hold the palm and are left alone);
  4b. --weights-from: where the nude's own weights are poor (Fiona_BaseBody was a static mesh in the game - its
     skinning was ours, and the elbows folded), the nude vertices in a bone region (default: the arms, shoulder to
     wrist) take the weights at the closest point of an outfit's skin on the dressed model's rig (Fiona: PCF_007's
     MI_PCF_Body01 - the game's weights): whole within 1.5 cm, fading out by 3 cm; past the end of that skin (its
     open border: the wrist) fading out within 1.5 cm; vertices on the --weights-keep bones (the breasts' physics
     bones) keep theirs (bone weights only).  The upper body as well (^上半身: PCF_007's skin covers the back) put
     a seam down the waist where that skin ends at the side.  --weights-from / --weights-mats repeat for several
     outfits (the same body mesh cut differently): each vertex takes the closest point over all of them, a point
     inside one skin before one on another's border.  Fiona's 8 bare-skin outfits cover the hips 93 %, the thighs
     79 %, the torso 32 %; legs + hips from all 8 left steps at both hip sides with the leg out 60 deg (10-06), so
     only the arms take them;
  4c. --sdef-joints (default 左ひじ,右ひじ): the nude's elbow rings become SDEF, one centre per joint (the rule of
     scripts/vindictus/pmx_sdef.py, every vertex with 95 % of its weight on the pair) - the elbow bends round like the
     game's own skin.  (Ridges seen on the way came from the limbs standing 2.7 cm off the dressed joints, step 2.)
  5. the switch: --outfit hidden by 衣服非表示_材質, --skin (the outfit's partial skin, and the dressed face when it
     is snapped) hidden and the nude body shown by 裸体形状, group 衣服非表示.

  python pmx_add_nude.py <dressed.pmx> <nude.pmx> --take <nude materials> --outfit <names> [--skin <names>]
                         [--snap <nude material>[=<dressed material>],...] [--map <nude bone>=<dressed bone>,...]
                         [--after <dressed material>] [--suffix _nude] [--finger-cm 2.5] [--out <pmx>]
                         [--weights-from <same-rig outfit.pmx> --weights-mats <its skin materials> (repeatable)
                          [--weights-bones <regex>] [--weights-cm 1.5,3.0[,1.5]] [--weights-keep <regex>]]
                         [--normals surface|bones]

<names>: comma separated material names, shell wildcards allowed.  Written next to the dressed PMX by default
(<stem>_full.pmx); another folder gets copies of the textures.  Prints PMX_ADD_NUDE=<json>.
"""
import argparse
import copy
import json
import os
import re
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pmx_nude_switch import add_switch, pick, pmx_module, save  # noqa: E402


def material_ranges(model):
    out, s = [], 0
    for mat in model.materials:
        n = mat.vertex_count // 3
        out.append((s, s + n))
        s += n
    return out


def weights_of(pmx, v):
    """[(bone index, weight)] of a vertex, any deform type."""
    w = v.weight
    bones = w.bones if isinstance(w.bones, (list, tuple)) else [w.bones]
    ws = w.weights
    if isinstance(w.weights, pmx.BoneWeightSDEF):
        ws = [w.weights.weight, 1.0 - w.weights.weight]
    elif not isinstance(ws, (list, tuple)):
        ws = [ws]
    if len(bones) == 1:
        ws = [1.0]
    elif len(bones) == 2 and len(ws) == 1:
        ws = [ws[0], 1.0 - ws[0]]
    return [(b, float(x)) for b, x in zip(bones, ws) if b is not None and b >= 0 and x > 0]


def swing(a, b):
    """Rotation matrix turning direction a onto direction b (the shortest way)."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:                       # opposite: half turn round any perpendicular axis
        p = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1.0, 0])
        p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def _aims():
    """MMD standard bone -> the joints it runs to, first one both rigs have wins.  Root / pelvis bones (センター,
    グルーブ, 腰, 下半身, 腰キャンセル) are not in it: rigs put them at different heights by convention (Fiona's 下半身
    is 6 cm higher on the nude's rig), and turning them to their hip joints tilted the pelvis 30 degrees."""
    aims = {"上半身": ["上半身1", "上半身2"], "上半身1": ["上半身2"], "上半身2": ["上半身3", "首"],
            "上半身3": ["上半身4", "首"], "上半身4": ["首"], "首": ["頭"]}
    for s in ("左", "右"):
        aims.update({s + "肩": [s + "腕"], s + "腕": [s + "ひじ"], s + "腕捩": [s + "ひじ"], s + "ひじ": [s + "手首"],
                     s + "手捩": [s + "手首"], s + "手首": [s + "中指１"],
                     s + "足": [s + "ひざ"], s + "ひざ": [s + "足首"], s + "足首": [s + "つま先"],
                     s + "足D": [s + "ひざD"], s + "ひざD": [s + "足首D"], s + "足首D": [s + "足先EX"],
                     s + "親指０": [s + "親指１"], s + "親指１": [s + "親指２"]})
        for f in ("人指", "中指", "薬指", "小指"):
            aims.update({s + f + "１": [s + f + "２"], s + f + "２": [s + f + "３"]})
    return aims


AIMS = _aims()
MAX_TURN = 60.0     # degrees: a bigger swing means the two rigs disagree about the bone, not about the pose


def aim_bone(nude, dressed, i, children, da, loc_b):
    """The bone bone i runs to, by name in both rigs: the MMD standard chain (AIMS), else its tail bone.  Most tails
    of these PMX are offsets, and picking a child by direction chose the hip joint for 下半身."""
    nb = {b.name: k for k, b in enumerate(nude.bones)}
    for name in AIMS.get(nude.bones[i].name, ()):
        if name in nb and name in da:
            return nb[name]
    c = nude.bones[i].displayConnection
    if isinstance(c, int) and c >= 0 and nude.bones[c].name in da:
        return c
    return None


SPINE = ("上半身", "上半身1", "上半身2", "上半身3", "上半身4")


LIMB_ANCHORS = (("左腕", "左肩"), ("右腕", "右肩"), ("左足D", None), ("右足D", None))


def pose_transforms(dressed, nude, anchor="首"):
    """Per nude bone (R, h, h2): x -> R (x - h) + h2, the nude posed onto the dressed skeleton (step 2).
    With its own bone lengths the posed neck misses the dressed one (Fiona: 4.7 cm; the nude rig's spine starts 6 cm
    higher); that miss is spread over the spine bones both rigs have (equal steps, children follow) so `anchor`
    lands on the dressed rig's joint and the torso, not the few centimetres of neck, takes it up.
    Then the limbs: the weights go onto the DRESSED rig's bones, which bend about the dressed joints - a nude arm left
    2.7 cm in front of them (Fiona, both arms, after the spine) bent about a pivot behind its own elbow: the inside
    folded into a crease and the outside came to a point, whatever the weights.  So each limb root is moved onto the
    dressed joint (LIMB_ANCHORS: the arm half at the clavicle, half at the upper arm; the leg at 足D); the limbs'
    lengths match, so elbows / wrists / knees land too."""
    poses, turned = _pose(dressed, nude, {})
    da = {b.name: i for i, b in enumerate(dressed.bones)}
    nb = {b.name: i for i, b in enumerate(nude.bones)}
    loc_a = lambda name: np.array(dressed.bones[da[name]].location, dtype=np.float64)  # noqa: E731
    report, steps = {}, {}
    chain = [nb[n] for n in SPINE if n in nb and n in da]
    if anchor in nb and anchor in da and chain:
        miss = loc_a(anchor) - poses[nb[anchor]][2]
        steps = {i: miss / len(chain) for i in chain}
        poses, turned = _pose(dressed, nude, steps)
        after = loc_a(anchor) - poses[nb[anchor]][2]
        report.update({"anchor": anchor, "miss_cm": round(float(np.linalg.norm(miss)) * 8, 2),
                       "after_cm": round(float(np.linalg.norm(after)) * 8, 2), "spread_over": len(chain)})
    limbs = {}
    for joint, split in LIMB_ANCHORS:
        if joint not in nb or joint not in da:
            continue
        miss = loc_a(joint) - poses[nb[joint]][2]
        if split in nb and split in da:
            steps[nb[split]] = steps.get(nb[split], 0.0) + miss / 2
            steps[nb[joint]] = steps.get(nb[joint], 0.0) + miss / 2
        else:
            steps[nb[joint]] = steps.get(nb[joint], 0.0) + miss
        limbs[joint] = round(float(np.linalg.norm(miss)) * 8, 2)
    if limbs:
        poses, turned = _pose(dressed, nude, steps)
        report["limbs_miss_cm"] = limbs
        report["limbs_after_cm"] = {j: round(float(np.linalg.norm(loc_a(j) - poses[nb[j]][2])) * 8, 2) for j in limbs}
    return poses, turned, report


def _pose(dressed, nude, steps):
    da = {b.name: i for i, b in enumerate(dressed.bones)}
    loc_a = np.array([b.location for b in dressed.bones], dtype=np.float64)
    loc_b = np.array([b.location for b in nude.bones], dtype=np.float64)
    children = {}
    for i, b in enumerate(nude.bones):
        children.setdefault(b.parent, []).append(i)
    order, seen = [], set()
    stack = list(reversed(children.get(-1, []) + children.get(None, [])))
    while stack:                                  # parents first
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        order.append(i)
        stack.extend(reversed(children.get(i, [])))
    order += [i for i in range(len(nude.bones)) if i not in seen]
    out = [None] * len(nude.bones)
    turned = 0
    for i in order:
        b = nude.bones[i]
        parent = b.parent if b.parent is not None and b.parent >= 0 else None
        if parent is None or out[parent] is None:
            R_p, h_p, h2_p = np.eye(3), loc_b[i], loc_b[i]
        else:
            R_p, h_p, h2_p = out[parent]
        h = loc_b[i]
        h2 = R_p @ (h - h_p) + h2_p + steps.get(i, 0.0)
        R = R_p
        if b.name in da and parent is not None:
            child = aim_bone(nude, dressed, i, children, da, loc_b)
            if child is not None:
                d_b = loc_b[child] - h
                d_a = loc_a[da[nude.bones[child].name]] - loc_a[da[b.name]]
                if np.linalg.norm(d_b) > 1e-6 and np.linalg.norm(d_a) > 1e-6:
                    cos = np.dot(d_b, d_a) / (np.linalg.norm(d_b) * np.linalg.norm(d_a))
                    if np.degrees(np.arccos(np.clip(cos, -1, 1))) <= MAX_TURN:
                        R = swing(d_b, d_a)
                        turned += 1
        out[i] = (R, h, h2)
    return out, turned


def weight_map(dressed, nude, overrides):
    """nude bone index -> dressed bone index: same name, else --map, else the nearest ancestor the dressed rig has."""
    da = {b.name: i for i, b in enumerate(dressed.bones)}
    out, how = {}, {"name": 0, "map": 0, "ancestor": 0}
    for i, b in enumerate(nude.bones):
        if b.name in overrides:
            out[i] = da[overrides[b.name]]
            how["map"] += 1
            continue
        j = i
        while j is not None and j >= 0 and nude.bones[j].name not in da:
            j = nude.bones[j].parent
        if j is None or j < 0:
            out[i] = 0
        else:
            out[i] = da[nude.bones[j].name]
        how["name" if j == i else "ancestor"] += 1
    return out, how


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def head_bones(model):
    """Indices of 頭 and everything under it."""
    names = {b.name: i for i, b in enumerate(model.bones)}
    if "頭" not in names:
        return set()
    out = {names["頭"]}
    grew = True
    while grew:
        grew = False
        for i, b in enumerate(model.bones):
            if i not in out and b.parent in out:
                out.add(i)
                grew = True
    return out


ARM_BONES = r"^(左|右)(肩|腕|ひじ|手捩)|upperarm|lowerarm|clavicle|elbow"


def nearest(points, queries, cell):
    """(index, distance) of the nearest point for every query, through a uniform grid of `cell`: the query's cell and
    its 26 neighbours, so an answer farther than one cell comes back as (-1, inf).  numpy only (no scipy here)."""
    grid = {}
    keys = np.floor(points / cell).astype(np.int64)
    for i, k in enumerate(map(tuple, keys)):
        grid.setdefault(k, []).append(i)
    out_i = np.full(len(queries), -1, dtype=np.int64)
    out_d = np.full(len(queries), np.inf)
    for q, k in enumerate(np.floor(queries / cell).astype(np.int64)):
        cand = [i for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                for i in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ())]
        if cand:
            d = np.linalg.norm(points[cand] - queries[q], axis=1)
            j = int(np.argmin(d))
            out_i[q], out_d[q] = cand[j], d[j]
    return out_i, out_d


def closest_on_triangle(p, a, b, c):
    """Closest point to p on triangle abc and its barycentric weights (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return a, (1.0, 0.0, 0.0)
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return a + v * ab, (1 - v, v, 0.0)
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return a + w * ac, (1 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b), (0.0, 1 - w, w)
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return a + ab * v + ac * w, (1 - v - w, v, w)


def game_weights(pmx, dressed, donor, posed, wts):
    """--weights-from: the nude vertices in the bone region (share of weight on bones matching donor["bones"]) take
    the weights at the nearest point of the donor's skin - an outfit of the same game on the same rig that shows that
    skin (Fiona: PCF_007's bare arms, MI_PCF_Body01, with the game's weights) - full within donor["full_cm"], fading
    out to donor["max_cm"].  Bone weights only: copying the donor's SDEF C / R0 / R1 onto a mesh of another shape gave
    neighbours different centres and opened a step across the elbow; elbow_sdef() makes the SDEF afterwards.  The nude
    body's own weights there are the old prework body's (the game kept it as a static mesh; the skinning was ours) and
    the elbow folded.  The weights are interpolated at the closest point on the donor's triangles (barycentric): the
    nearest VERTEX's weights changed in steps from one nude vertex to the next and the bent elbow showed a ridge.
    Where the closest point lies on the OPEN BORDER of the donor's skin (the nude vertex is past the end of that skin:
    the wrist, a neckline) the weights fade out within donor["border_cm"] instead: the border's weights belong to the
    game's seam with another mesh (PCF_007's arm skin ends 2-8 cm before the wrist, its rim weighted to the forearm).
    Changes wts in place, returns ({}, report)."""
    da = {b.name: i for i, b in enumerate(dressed.bones)}
    region = re.compile(donor["bones"], re.I)
    in_region = {i for i, b in enumerate(dressed.bones) if region.search(b.name)}
    keep_re = re.compile(donor["keep"], re.I) if donor.get("keep") else None
    kept = {i for i, b in enumerate(dressed.bones) if keep_re and keep_re.search(b.name)}

    class Skin:
        """One donor outfit's skin: triangles, open border, weights in the dressed model's bones."""

        def __init__(self, src, mats):
            self.src = src
            self.to_a = {}
            for i, b in enumerate(src.bones):
                j = i
                while j is not None and j >= 0 and src.bones[j].name not in da:
                    j = src.bones[j].parent
                self.to_a[i] = da[src.bones[j].name] if j is not None and j >= 0 else None
            ranges = material_ranges(src)
            tris = [f for k in mats for f in src.faces[ranges[k][0]:ranges[k][1]]]
            self.verts = sorted({v for f in tris for v in f})
            self.pts = np.array([src.vertices[v].co for v in self.verts], dtype=np.float64)
            self.tris_of = {}
            for f in tris:
                for v in f:
                    self.tris_of.setdefault(v, []).append(f)
            self.loc = {v: np.array(src.vertices[v].co, dtype=np.float64) for v in self.verts}
            # the skin's open border, on vertices welded by position (a PMX mesh is split along UV seams)
            self.key = {v: tuple(np.round(self.loc[v] * 1e4).astype(np.int64)) for v in self.verts}
            edge_use = Counter()
            for f in tris:
                for p, q in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                    edge_use[(min(self.key[p], self.key[q]), max(self.key[p], self.key[q]))] += 1
            self.border_edges = {e for e, c in edge_use.items() if c == 1}
            self.border_keys = {k for e in self.border_edges for k in e}
            self.wcache = {}

        def on_border(self, f3, bary):
            zero = [i for i in range(3) if bary[i] < 1e-6]
            if len(zero) == 2:                            # at a corner
                return self.key[f3[3 - zero[0] - zero[1]]] in self.border_keys
            if len(zero) == 1:                            # on the edge across from that corner
                p, q = (f3[i] for i in range(3) if i != zero[0])
                return (min(self.key[p], self.key[q]), max(self.key[p], self.key[q])) in self.border_edges
            return False

        def weights_a(self, v):
            if v not in self.wcache:
                out = {}
                for b, x in weights_of(pmx, self.src.vertices[v]):
                    if self.to_a[b] is not None:
                        out[self.to_a[b]] = out.get(self.to_a[b], 0.0) + x
                self.wcache[v] = out
            return self.wcache[v]

        def closest(self, points):
            """Per point: (distance, triangle, barycentric, on the open border), or None past max_cm."""
            idx, _dist = nearest(self.pts, points, donor["max_cm"] / 8.0)
            out = []
            for q, p in enumerate(points):
                if idx[q] < 0:
                    out.append(None)
                    continue
                best = None                               # closest point on the triangles round the nearest vertex
                for f3 in self.tris_of[self.verts[idx[q]]]:
                    point, bary = closest_on_triangle(p, self.loc[f3[0]], self.loc[f3[1]], self.loc[f3[2]])
                    d = float(np.linalg.norm(point - p))
                    if best is None or d < best[0]:
                        best = (d, f3, bary)
                out.append((best[0], best[1], best[2], self.on_border(best[1], best[2])))
            return out

    skins = [Skin(src, mats) for src, mats in donor["sources"]]
    share = np.array([sum(x for b, x in bw if b in in_region) for bw in wts])
    keep_share = np.array([sum(x for b, x in bw if b in kept) for bw in wts])
    todo = np.nonzero(share > 0)[0]
    found = [skin.closest(posed[todo]) for skin in skins]
    sdef, full, blended, missing, past = {}, 0, 0, 0, 0       # sdef stays empty: see elbow_sdef()
    used, by_skin = [], Counter()
    for q, n in enumerate(todo):
        cands = [(c[0], k, c) for k, f in enumerate(found) for c in [f[q]] if c is not None]
        if not cands:
            missing += 1
            continue
        inside = [t for t in cands if not t[2][3]]     # a point inside one skin beats the border of another
        d, k, (_d, f3, bary, border) = min(inside or cands, key=lambda t: t[0])
        skin = skins[k]
        d_cm = d * 8.0
        if border:
            past += 1
            f = 1.0 - smoothstep(d_cm, 0.0, donor.get("border_cm", 1.5))
        else:
            f = 1.0 - smoothstep(d_cm, donor["full_cm"], donor["max_cm"])
        f *= smoothstep(share[n], 0.2, 0.7)
        f *= 1.0 - smoothstep(keep_share[n], 0.02, 0.25)     # the breasts keep theirs (their physics bones)
        if f <= 1e-3:
            continue
        theirs = {}
        for v, bw in zip(f3, bary):
            for b, x in skin.weights_a(v).items():
                theirs[b] = theirs.get(b, 0.0) + bw * x
        theirs = {b: x for b, x in theirs.items() if x > 1e-4}
        if not theirs:
            continue
        used.append(d_cm)
        by_skin[k] += 1
        if f > 0.999:
            full += 1
            wts[n] = sorted(theirs.items(), key=lambda t: -t[1])[:4]
        else:
            blended += 1
            mine = dict(wts[n])
            mix = {b: f * theirs.get(b, 0.0) + (1 - f) * mine.get(b, 0.0) for b in set(theirs) | set(mine)}
            wts[n] = sorted(mix.items(), key=lambda t: -t[1])[:4]
    return sdef, {"region_vertices": int(len(todo)), "taken_whole": full, "blended": blended,
                  "no_donor_near": missing, "past_the_border": past,
                  "donor_vertices": [len(skin.verts) for skin in skins],
                  "donor_border_edges": [len(skin.border_edges) for skin in skins],
                  "taken_per_donor": [by_skin[k] for k in range(len(skins))],
                  "distance_cm_median": round(float(np.median(used)), 2) if used else None}


def geometric_normals(co, faces):
    """Area-weighted face normals summed per vertex, vertices welded by position (a PMX mesh is split along UV seams).
    PMX front faces wind clockwise."""
    f = np.asarray(faces, dtype=np.int64)
    a, b, c = co[f[:, 0]], co[f[:, 1]], co[f[:, 2]]
    fn = -np.cross(b - a, c - a)
    keys = {}
    weld = np.array([keys.setdefault(k, len(keys)) for k in map(tuple, np.round(co * 1e4).astype(np.int64))])
    acc = np.zeros((len(keys), 3))
    for i in range(3):
        np.add.at(acc, weld[f[:, i]], fn)
    n = acc[weld]
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def transport_normals(co, posed, nrm, faces):
    """The nude's own normals carried onto the posed mesh: each one turned by the rotation that takes the surface's
    normal there (from the faces round it) before posing to the one after - not only by its bones.  The pose moves
    joints (spine spread, limb anchors: Fiona's arms 2.7 cm), so where weights mix (the shoulders) the surface shears
    as well as turns; normals turned by the bones alone stood up to 70 deg off the shoulders' and the bib's surface,
    and a raised arm showed dark creases along the clavicle.  The nude's own deviations from its geometry (seam fixes)
    stay.  Returns the new normals (rows of nrm where a vertex has no face keep their value)."""
    g0, g1 = geometric_normals(co, faces), geometric_normals(posed, faces)
    n0 = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-20)
    axis = np.cross(g0, g1)
    s = np.linalg.norm(axis, axis=1)
    c = np.einsum("ij,ij->i", g0, g1)
    k = axis / np.maximum(s, 1e-20)[:, None]
    out = (n0 * c[:, None] + np.cross(k, n0) * s[:, None]
           + k * np.einsum("ij,ij->i", k, n0)[:, None] * (1.0 - c)[:, None])         # Rodrigues, angle atan2(s, c)
    used = np.zeros(len(co), dtype=bool)
    used[np.unique(np.asarray(faces, dtype=np.int64))] = True
    out[~used] = nrm[~used]
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-20)


FINGER_JOINT = re.compile(r"(親指|人指|中指|薬指|小指)([０-９0-9])")


def finger_strays(dressed, posed, wts, limit_cm=2.5):
    """Weights on a finger SEGMENT (a phalanx: 親指１, 小指２ ...) of vertices lying more than limit_cm from that
    segment (its joint to the next joint of the same finger) are dropped and the rest renormalised; a vertex left
    with nothing goes to the first ancestor that is not a phalanx (the metacarpal ..０, or 手首).  Fiona_BaseBody's
    skinning (ours: the game kept it as a static mesh) had about 40 wrist vertices per hand on 小指１, up to 0.71 and
    7 cm from it - a fist swung them out of the wrist as a fin.  Metacarpals hold the palm, far from their own line
    in the game's skins too, and stay as they are.  Changes wts in place, returns the report."""
    pos = np.array([b.location for b in dressed.bones], dtype=np.float64)
    kids = {}
    for i, b in enumerate(dressed.bones):
        kids.setdefault(b.parent, []).append(i)

    def phalanx(i):
        m = FINGER_JOINT.search(dressed.bones[i].name)
        return m if m and m.group(2) not in ("０", "0") else None
    segs = {}
    for i, b in enumerate(dressed.bones):
        m = phalanx(i)
        if not m:
            continue
        nxt = [k for k in kids.get(i, ()) if FINGER_JOINT.search(dressed.bones[k].name)
               and FINGER_JOINT.search(dressed.bones[k].name).group(1) == m.group(1)]
        a = pos[i]
        if nxt:
            segs[i] = (a, pos[nxt[0]])
        elif b.parent is not None and b.parent >= 0:     # the last joint: on along its parent's direction
            segs[i] = (a, a + (a - pos[b.parent]) * 0.8)
        else:
            segs[i] = (a, a)
    limit = limit_cm / 8.0
    vertices, dropped, homeless, far = 0, Counter(), 0, 0.0
    for n, bw in enumerate(wts):
        bad = []
        for b, x in bw:
            if b in segs:
                a, e = segs[b]
                ab = e - a
                t = float(np.clip((posed[n] - a) @ ab / max(ab @ ab, 1e-12), 0.0, 1.0))
                d = float(np.linalg.norm(posed[n] - (a + t * ab)))
                if d > limit:
                    bad.append(b)
                    far = max(far, d * 8.0)
        if not bad:
            continue
        vertices += 1
        keep = [(b, x) for b, x in bw if b not in bad]
        for b in bad:
            dropped[dressed.bones[b].name] += 1
        if not keep:
            homeless += 1
            j = bad[0]
            while j is not None and j >= 0 and phalanx(j):
                j = dressed.bones[j].parent
            keep = [(j, 1.0)]
        tot = sum(x for _, x in keep) or 1.0
        wts[n] = [(b, x / tot) for b, x in keep]
    return {"vertices": vertices, "weights_dropped": dict(dropped.most_common()), "to_ancestor": homeless,
            "farthest_cm": round(far, 1)}


def elbow_sdef(pmx, model, first, joints, share=0.95):
    """SDEF on the joint rings of the new vertices (index >= first), the rule of scripts/vindictus/pmx_sdef.py that
    gave the outfits round elbows: a vertex weighted to a joint bone (左ひじ / 右ひじ) and its parent (腕捩) turns
    about the joint, C at the joint bone's head and R0 = R1 = C - one centre for the whole ring.
    pmx_sdef.py takes only vertices with exactly those two weights.  Weights interpolated from another mesh carry
    crumbs of a third bone (左手捩1 at 0.02) here and there, those stayed BDEF between SDEF neighbours and the bent
    elbow showed a ridge; so every vertex with at least `share` of its weight on the pair (and some on each) drops the
    crumbs and becomes SDEF - the whole bending band, no patchwork."""
    index = {b.name: i for i, b in enumerate(model.bones)}
    pairs = {}
    for name in joints:
        j = index.get(name)
        if j is not None and model.bones[j].parent is not None and model.bones[j].parent >= 0:
            pairs[frozenset((model.bones[j].parent, j))] = (model.bones[j].parent, j, list(model.bones[j].location))
    made = 0
    for v in model.vertices[first:]:
        w = {}
        for b, x in weights_of(pmx, v):
            w[b] = w.get(b, 0.0) + x
        total = sum(w.values()) or 1.0
        hit = None
        for key, (parent, joint, c) in pairs.items():
            pw, jw = w.get(parent, 0.0), w.get(joint, 0.0)
            if pw > 1e-3 and jw > 1e-3 and (pw + jw) / total >= share:
                hit = (parent, joint, c)
                break
        if hit is None:
            continue
        parent, joint, c = hit
        tot = w[parent] + w[joint]
        v.weight = pmx.BoneWeight()
        v.weight.type, v.weight.bones = pmx.BoneWeight.SDEF, [parent, joint]
        v.weight.weights = pmx.BoneWeightSDEF(weight=w[parent] / tot, c=list(c), r0=list(c), r1=list(c))
        made += 1
    return made


def add_nude(pmx, dressed, nude, take, snaps, overrides, after, suffix, donor=None, sdef_joints=(), finger_cm=2.5,
             normals="surface"):
    """Nude materials `take` of `nude` copied into `dressed` (in place), posed and snapped.  Returns (report,
    indices of the new materials in dressed)."""
    poses, turned, spread = pose_transforms(dressed, nude)
    wmap, how = weight_map(dressed, nude, overrides)
    heads = head_bones(nude)
    ra, rb = material_ranges(dressed), material_ranges(nude)
    a_names = [m.name for m in dressed.materials]
    n_uv = getattr(dressed.header, "additional_uvs", 0)
    report = {"bones_turned": turned, "spine_spread": spread, "weights": how, "snapped": {}}

    # vertices of the taken materials, in order of first use
    local, sources = {}, []
    new_faces = {}
    for k in take:
        s, e = rb[k]
        tris = []
        for f in nude.faces[s:e]:
            tri = []
            for v in f:
                if v not in local:
                    local[v] = len(sources)
                    sources.append(v)
                tri.append(local[v])
            tris.append(tri)
        new_faces[k] = tris
    co = np.array([nude.vertices[v].co for v in sources], dtype=np.float64)
    nrm = np.array([nude.vertices[v].normal for v in sources], dtype=np.float64)
    posed, pnrm = np.zeros_like(co), np.zeros_like(nrm)
    wts, head_share = [], np.zeros(len(sources))
    for n, v in enumerate(sources):
        ws = weights_of(pmx, nude.vertices[v])
        tot = sum(x for _, x in ws) or 1.0
        for bone, x in ws:
            R, h, h2 = poses[bone]
            posed[n] += x / tot * (R @ (co[n] - h) + h2)
            pnrm[n] += x / tot * (R @ nrm[n])
            if bone in heads:
                head_share[n] += x / tot
        merged = {}
        for bone, x in ws:
            merged[wmap[bone]] = merged.get(wmap[bone], 0.0) + x / tot
        wts.append(sorted(merged.items(), key=lambda t: -t[1])[:4])

    # step 3: the snapped materials lie on the dressed model's, the head part
    morph_rows = {}                                # new vertex -> dressed vertex it copies expressions from
    snap_normals = []
    for k_b, k_a in snaps:
        s_b, e_b = rb[k_b]
        s_a, e_a = ra[k_a]
        if e_b - s_b != e_a - s_a:
            raise SystemExit("--snap %s: %d faces, the dressed %s has %d" % (
                nude.materials[k_b].name, e_b - s_b, a_names[k_a], e_a - s_a))
        pairs = {}
        for fb, fa in zip(nude.faces[s_b:e_b], dressed.faces[s_a:e_a]):
            for vb, va in zip(fb, fa):
                pairs.setdefault(local[vb], va)
        idx = np.array(sorted(pairs))
        target = np.array([dressed.vertices[pairs[i]].co for i in idx], dtype=np.float64)
        keep = smoothstep(1.0 - head_share[idx], 0.05, 0.95)[:, None]      # share outside the head: keep the pose
        before = np.linalg.norm(posed[idx] - target, axis=1)
        posed[idx] = keep * posed[idx] + (1 - keep) * target
        tn = np.array([dressed.vertices[pairs[i]].normal for i in idx], dtype=np.float64)
        snap_normals.append((idx, keep, tn))
        for i in idx:
            morph_rows[i] = pairs[i]
        report["snapped"][nude.materials[k_b].name] = {
            "onto": a_names[k_a], "vertices": len(idx), "head_vertices": int((keep[:, 0] < 0.05).sum()),
            "posed_vs_dressed_cm_median": round(float(np.median(before)) * 8, 2),
            "posed_vs_dressed_cm_max": round(float(before.max()) * 8, 2)}

    # normals: turned with the posed surface (transport_normals) or by the bones alone; the snapped head part ends on
    # the dressed model's
    if normals == "surface":
        by_bones = pnrm / np.maximum(np.linalg.norm(pnrm, axis=1, keepdims=True), 1e-20)
        pnrm = transport_normals(co, posed, nrm, [tri for k in take for tri in new_faces[k]])
        turn = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", by_bones, pnrm), -1.0, 1.0)))
        report["normals"] = {"turned_with": "surface", "vs_bones_deg_median": round(float(np.median(turn)), 2),
                             "over_20_deg": int((turn > 20).sum()), "max_deg": round(float(turn.max()), 1)}
    for idx, keep, tn in snap_normals:
        pnrm[idx] = keep * pnrm[idx] + (1 - keep) * tn
    if finger_cm:
        report["finger_strays"] = finger_strays(dressed, posed, wts, finger_cm)
    sdef = {}
    if donor is not None:
        sdef, report["game_weights"] = game_weights(pmx, dressed, donor, posed, wts)

    # new vertices appended at the end
    first = len(dressed.vertices)
    for n, v in enumerate(sources):
        vert = copy.deepcopy(nude.vertices[v])
        vert.co = [float(x) for x in posed[n]]
        vert.normal = [float(x) for x in pnrm[n] / max(np.linalg.norm(pnrm[n]), 1e-20)]
        uvs = list(getattr(vert, "additional_uvs", []) or [])
        vert.additional_uvs = (uvs + [[0.0, 0.0, 0.0, 0.0]] * n_uv)[:n_uv]
        bw = wts[n]
        tot = sum(x for _, x in bw) or 1.0
        if n in sdef:
            bones, w0, c, r0, r1 = sdef[n]
            vert.weight = pmx.BoneWeight()
            vert.weight.type, vert.weight.bones = pmx.BoneWeight.SDEF, bones
            vert.weight.weights = pmx.BoneWeightSDEF(weight=w0, c=list(c), r0=list(r0), r1=list(r1))
        elif len(bw) == 1:
            vert.weight = pmx.BoneWeight()
            vert.weight.type, vert.weight.bones, vert.weight.weights = pmx.BoneWeight.BDEF1, [bw[0][0]], [1.0]
        elif len(bw) == 2:
            vert.weight = pmx.BoneWeight()
            vert.weight.type = pmx.BoneWeight.BDEF2
            vert.weight.bones, vert.weight.weights = [bw[0][0], bw[1][0]], [bw[0][1] / tot]
        else:
            bones = [b for b, _ in bw] + [-1] * (4 - len(bw))
            vals = [x / tot for _, x in bw] + [0.0] * (4 - len(bw))
            vert.weight = pmx.BoneWeight()
            vert.weight.type, vert.weight.bones, vert.weight.weights = pmx.BoneWeight.BDEF4, bones, vals
        dressed.vertices.append(vert)

    if sdef_joints:
        report["elbow_sdef"] = elbow_sdef(pmx, dressed, first, sdef_joints)

    # expressions: the dressed model's vertex / UV morph offsets onto the snapped copies
    rows_by_dressed = {}
    for nv, dv in morph_rows.items():
        rows_by_dressed.setdefault(dv, []).append(first + nv)
    added = 0
    for m in dressed.morphs:
        if isinstance(m, (pmx.VertexMorph, pmx.UVMorph)):
            extra = []
            for o in m.offsets:
                for c in rows_by_dressed.get(o.index, ()):
                    dup = copy.copy(o)
                    dup.index = c
                    extra.append(dup)
            m.offsets.extend(extra)
            added += len(extra)
    report["expression_offsets_copied"] = added

    # textures, materials (after `after`), faces
    tex_map = {}

    def tex(i):
        if i is None or i < 0:
            return i
        if i not in tex_map:
            dressed.textures.append(copy.deepcopy(nude.textures[i]))
            tex_map[i] = len(dressed.textures) - 1
        return tex_map[i]
    new_mats = []
    for k in take:
        mat = copy.deepcopy(nude.materials[k])
        if mat.name in a_names or mat.name in [m.name for m in new_mats]:
            mat.name += suffix
            mat.name_e = (mat.name_e + suffix) if mat.name_e else ""
        mat.texture = tex(mat.texture)
        mat.sphere_texture = tex(mat.sphere_texture)
        if not mat.is_shared_toon_texture:
            mat.toon_texture = tex(mat.toon_texture)
        mat.vertex_count = len(new_faces[k]) * 3
        new_mats.append(mat)
    at = (after + 1) if after is not None else len(dressed.materials)
    faces_before = ra[at - 1][1] if at > 0 else 0
    insert = [[first + v for v in tri] for k in take for tri in new_faces[k]]
    dressed.faces[faces_before:faces_before] = insert
    dressed.materials[at:at] = new_mats
    shift = len(new_mats)
    for m in dressed.morphs:
        if isinstance(m, pmx.MaterialMorph):
            for o in m.offsets:
                if o.index is not None and o.index >= at:
                    o.index += shift
    report.update(vertices_added=len(sources), faces_added=len(insert), materials_added=[m.name for m in new_mats],
                  inserted_at=at)
    return report, list(range(at, at + shift))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dressed")
    ap.add_argument("nude")
    ap.add_argument("--take", required=True, help="the nude PMX's materials to copy in")
    ap.add_argument("--outfit", required=True, help="dressed materials 衣服非表示 hides")
    ap.add_argument("--skin", default="", help="dressed materials the nude body replaces (partial skin, snapped face)")
    ap.add_argument("--snap", default="", help="nude material[=dressed material] laid onto the dressed one (face)")
    ap.add_argument("--map", default="", help="nude bone=dressed bone for the weights (breasts onto physics bones)")
    ap.add_argument("--after", default="", help="dressed material the new ones follow (default: the last --skin)")
    ap.add_argument("--suffix", default="_nude")
    ap.add_argument("--weights-from", action="append", default=[],
                    help="a PMX of the same game and rig showing that skin (step 4b); repeat for several outfits")
    ap.add_argument("--weights-mats", action="append", default=[],
                    help="its skin materials to take the weights from (one per --weights-from)")
    ap.add_argument("--weights-bones", default=ARM_BONES, help="regex: the bone region that takes them (arms)")
    ap.add_argument("--weights-keep", default="breast|胸|bust",
                    help="regex: vertices weighted to these bones keep their own weights (the breasts' physics bones)")
    ap.add_argument("--weights-cm", default="1.5,3.0",
                    help="full within, faded out by (cm); a third value: faded out by, past the skin's border (1.5)")
    ap.add_argument("--sdef-joints", default="左ひじ,右ひじ", help="joint rings of the nude body made SDEF ('' = none)")
    ap.add_argument("--normals", choices=("surface", "bones"), default="surface",
                    help="turn the nude's normals with the posed surface (default) or by the bones alone (step 2)")
    ap.add_argument("--finger-cm", type=float, default=2.5,
                    help="drop phalanx weights of vertices farther from the bone (cm, step 4a; 0 = keep all)")
    ap.add_argument("--out", default="")
    ap.add_argument("--pmx-module", default="")
    a = ap.parse_args()
    pmx = pmx_module(a.pmx_module)
    dressed, nude = pmx.load(a.dressed), pmx.load(a.nude)
    take = pick(nude, a.take, "--take")
    outfit, skin = pick(dressed, a.outfit, "--outfit"), pick(dressed, a.skin, "--skin")
    snaps = []
    for item in [s.strip() for s in a.snap.split(",") if s.strip()]:
        b_name, _, a_name = item.partition("=")
        k_b = pick(nude, b_name, "--snap")[0]
        if k_b not in take:
            raise SystemExit("--snap %s is not in --take" % b_name)
        snaps.append((k_b, pick(dressed, a_name or b_name, "--snap")[0]))
    overrides = dict(p.split("=", 1) for p in a.map.split(",") if "=" in p)
    names = {b.name for b in dressed.bones}
    bad = [d for d in overrides.values() if d not in names]
    if bad:
        raise SystemExit("--map: the dressed PMX has no bone %s" % ", ".join(bad))
    after = pick(dressed, a.after, "--after")[-1] if a.after else (max(skin) if skin else None)
    donor = None
    if a.weights_from:
        if len(a.weights_mats) != len(a.weights_from):
            raise SystemExit("give one --weights-mats per --weights-from")
        sources = []
        for path, mats in zip(a.weights_from, a.weights_mats):
            src = pmx.load(path)
            sources.append((src, pick(src, mats, "--weights-mats")))
        cm = [float(x) for x in a.weights_cm.split(",")]
        donor = {"sources": sources, "bones": a.weights_bones,
                 "full_cm": cm[0], "max_cm": cm[1], "border_cm": cm[2] if len(cm) > 2 else 1.5,
                 "keep": a.weights_keep}
    joints = [j.strip() for j in a.sdef_joints.split(",") if j.strip()]
    report, new = add_nude(pmx, dressed, nude, take, snaps, overrides, after, a.suffix, donor, joints, a.finger_cm,
                           a.normals)
    shift = len(new)
    fix = lambda ks: [k + shift if k >= new[0] else k for k in ks]          # indices after the insert
    report["switch"] = add_switch(pmx, dressed, fix(outfit), new, fix(skin))
    out = a.out or a.dressed[:-4] + "_full.pmx"
    if report["switch"]["status"] == "ok":
        report["textures_copied"] = save(pmx, dressed, a.dressed, out)
        report["written"] = os.path.abspath(out)
    print("PMX_ADD_NUDE=" + json.dumps(report, ensure_ascii=False))
    return 0 if report["switch"]["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
