"""Rise of Eros full versions (complete_nude.py): the body fitted under the outfit swings with the cups over it.

A _full PMX carries the body twice (pmx_two_bodies.py): <family>_nk_body, fitted under the outfit and shown with it,
and <family>_nk_body_nude, shown when 衣服非表示 hides the outfit.  The body keeps the nude base's weights
(docs/roe-complete-nude.md section 5), the outfit the game's.  On the breasts both now hang on the same bones (the
outfit's own breast bones, complete_nude's aliases; bodies by scripts/mmd_dances/pmx_add_bust.py), but they split
their weight differently between the breast's static root and its swinging bone - b01's cups put 14 % on the
swinging bone, the body under them 26 %.  When the breasts sag (the _bustB springs hold them at 15 degrees) and
bounce, the two part by that difference times the distance from the pivot: up to 2 cm at the joint limit, against
3-7 mm of room between them at rest, so the skin shows through the cups.

This gives every fitted-body vertex under a cup the cups' weight on the swinging bone (inverse-distance mean of the
--k nearest cup vertices; a cup = an outfit vertex with >= 0.3 of its weight on that breast's bones), and moves the
difference to or from the breast's static root, which moves with the torso, so nothing else about the vertex
changes.  Vertices past --reach cm from the cups fade back to their own weights over --fade cm.  The nude copy keeps
its weights; positions, normals, morphs, bones, bodies and joints are untouched.  Run it on the _full PMX and its
_bustB (they share their weights).  Needs Python, numpy and the pmx module inside mmd_tools (no Blender).

    python pmx_body_follows_cups.py in.pmx out.pmx [--reach 1.5] [--fade 2.0] [--k 4] [--dry-run]
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mmd_dances"))
import pmx_add_bust as pab  # noqa: E402

UNIT_CM = 8.0
SIDES = ("左胸", "右胸")


def vertex_materials(model):
    out, start = {}, 0
    for mat in model.materials:
        for f in range(start, start + mat.vertex_count):
            out[model.faces[f // 3][f % 3]] = mat.name
        start += mat.vertex_count
    return out


def write_weights(w, weights):
    """{bone: weight} back into a BDEF1 / BDEF2 / BDEF4 record (at most four bones, renormalised)."""
    items = sorted(((b, x) for b, x in weights.items() if x > 1e-6), key=lambda kv: -kv[1])[:4]
    total = sum(x for _, x in items)
    items = [(b, x / total) for b, x in items]
    if len(items) == 1:
        w.type, w.bones, w.weights = 0, [items[0][0]], []
    elif len(items) == 2:
        w.type, w.bones, w.weights = 1, [items[0][0], items[1][0]], [items[0][1]]
    else:
        items += [(items[0][0], 0.0)] * (4 - len(items))
        w.type, w.bones, w.weights = 2, [b for b, _ in items], [x for _, x in items]


def follow(model, reach_cm=1.5, fade_cm=2.0, k=4):
    names = [b.name for b in model.bones]
    kids = pab.children(model)
    on_bone = {}
    for i, r in enumerate(model.rigids):
        if r.bone is not None:
            on_bone.setdefault(r.bone, i)
    swinging = {b for b, i in on_bone.items() if model.rigids[i].mode in (1, 2)}
    vmat = vertex_materials(model)
    fitted = [i for i, n in vmat.items() if n.endswith("_nk_body")]
    outfit = [i for i, n in vmat.items() if "_nk_body" not in n]
    if not fitted:
        raise SystemExit("no fitted body (*_nk_body): not a complete_nude _full PMX")
    weights = [pab.read_weights(v) for v in model.vertices]
    co = np.array([v.co for v in model.vertices], dtype=np.float64)
    report = {}
    for side in SIDES:
        if side not in names:
            continue
        root = names.index(side)
        # the breast's swinging bones: the root itself when its body swings (c06's one-bone right breast), else
        # breast bones under it (an accessory chain hung on the breast has bodies of its own and stays out)
        main = [b for b in pab.subtree(kids, root, set()) if b in swinging
                and (b == root or pab.NEXT_NAME.search(names[b]))]
        if not main:
            report[side] = "no swinging body"
            continue
        core = set(pab.subtree(kids, root, set(on_bone) - {root} - set(main)))
        swing = set()                   # the swinging bones and what hangs on them without a body of its own
        for b in main:
            swing.update(pab.subtree(kids, b, set(on_bone) - {b}))
        anchor = root if root not in swing else model.bones[root].parent
        tree = core
        cups = [i for i in outfit if sum(x for b, x in weights[i].items() if b in tree) >= 0.3]
        if not cups:
            report[side] = "no cup over the body"
            continue
        cup_co = co[cups]
        cup_swing = np.array([sum(x for b, x in weights[i].items() if b in swing) for i in cups])
        reach, fade = reach_cm / UNIT_CM, fade_cm / UNIT_CM
        lo, hi = cup_co.min(0) - reach - fade, cup_co.max(0) + reach + fade
        changed, moved = 0, []
        for i in fitted:
            p = co[i]
            if (p < lo).any() or (p > hi).any():
                continue
            d = np.sqrt(((cup_co - p) ** 2).sum(1))
            near = np.argsort(d)[:k]
            if d[near[0]] > reach + fade:
                continue
            wk = 1.0 / (d[near] + 1e-4)
            target = float((cup_swing[near] * wk).sum() / wk.sum())
            t = 1.0 if d[near[0]] <= reach else (reach + fade - d[near[0]]) / fade
            w = dict(weights[i])
            cur = sum(x for b, x in w.items() if b in swing)
            new = cur + (target - cur) * t
            delta = new - cur
            if abs(delta) < 1e-3 or model.vertices[i].weight.type == 3:     # an SDEF vertex keeps its weights
                continue
            if cur > 1e-6:
                for b in [b for b in w if b in swing]:
                    w[b] *= new / cur
            else:
                w[main[0]] = w.get(main[0], 0.0) + delta
            if delta < 0:
                w[anchor] = w.get(anchor, 0.0) - delta
            else:                       # take it from the static root, then from the rest
                need = delta
                take = min(need, w.get(anchor, 0.0))
                if take:
                    w[anchor] -= take
                    need -= take
                rest = [b for b in w if b not in swing and w[b] > 0]
                pool = sum(w[b] for b in rest)
                if need > 1e-9 and pool > 0:
                    for b in rest:
                        w[b] -= need * w[b] / pool
            write_weights(model.vertices[i].weight, w)
            changed += 1
            moved.append(abs(delta))
        report[side] = {"cups": len(cups), "body_vertices_changed": changed,
                        "swing_change_mean": round(float(np.mean(moved)), 3) if moved else 0.0,
                        "swing_change_max": round(float(np.max(moved)), 3) if moved else 0.0,
                        "swinging": [names[b] for b in main], "static": names[anchor] if anchor >= 0 else None}
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--reach", type=float, default=1.5, help="cm: body vertices this close to a cup follow it fully")
    ap.add_argument("--fade", type=float, default=2.0, help="cm past --reach over which they fade back")
    ap.add_argument("--k", type=int, default=4, help="nearest cup vertices averaged")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pmx = pab.pmx_module()
    model = pmx.load(args.src)
    report = follow(model, args.reach, args.fade, args.k)
    for side, line in report.items():
        print("%s: %s" % (side, line))
    if not args.dry_run:
        pmx.save(args.out, model, add_uv_count=model.header.additional_uvs)
        print("wrote", args.out)


if __name__ == "__main__":
    main()
