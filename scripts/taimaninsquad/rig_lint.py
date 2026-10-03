"""Does the skin around every limb follow that limb's bone?  A check over the unit prefabs, no Blender.

    python rig_lint.py                  # every Biped unit; writes <export-root>/_meta/rig_lint.json
    python rig_lint.py asagi 13 24      # some units (ids / numbers / names, as in list_models.py)
    python rig_lint.py --no-fixes       # the rigs as the game has them (before the exporter's repairs)
    python rig_lint.py --weapons none   # the unit prefabs alone: shows the limbs the game keeps as weapons

A model can look right in its rest pose and still be useless: Asagi's shins are skinned to
``Bone_L_Calf``, a bone of a second leg chain that hangs under the THIGH, so bending ``Bip001 L Calf``
left the shin where it was and tore the foot off (the XPS pose test and the MMD dance showed it;
tsquad_scene.Scene.limb_aliases repairs it).  This script measures that for every unit instead of
waiting to see it: for thigh / calf / upper arm / forearm on both sides it takes the vertices around
the middle of the segment (nearer to this side's bone than to the other side's) and adds up their
weights by owner - bones in the segment's own subtree versus anything else.

A low "own" share is a lead, not a verdict.  Skirts, coats, capes and shoulder armour hang over limbs
and are meant to follow their own bones; a shin or forearm whose skin is owned by ANOTHER LIMB-LIKE
bone is the case to look at.  Units the exporter repairs show the bones it remapped.

It also lists the limbs that carry NO skin ("NO SKIN on: L Forearm, L Hand"): upper arm, forearm,
hand, thigh, calf and foot, each with everything below it - nothing is skinned to it, or a stump's
worth (under 15 % of what the same limb on the other side carries and under 1 % of the unit's
vertices) - and hands whose finger bones carry nothing (a sleeve skinned to the hand bone hides a
missing hand).  That is how a missing limb shows:
20_Natsume's left arm is not in her unit prefab - the game keeps it as a weapon prefab and hangs it on
at run time (tsquad_scene.Scene.add_weapons does the same now; with --weapons none the check shows what
the unit prefabs lack by themselves).  What is left with the default are bodies that really have
nothing there: a ghost's robe without legs, a monster with mittens for hands.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402
import tsquad_scene as ts  # noqa: E402

SEGMENTS = (("Thigh", "Calf"), ("Calf", "Foot"), ("UpperArm", "Forearm"), ("Forearm", "Hand"))
LIMBS = ("UpperArm", "Forearm", "Hand", "Thigh", "Calf", "Foot")
FINGER = re.compile(r"^Bip001 [LR] Finger\d+$")
STUMP = 0.15                                           # of the skin the other side's limb carries
STUMP_SHARE = 0.01                                     # of the unit's skinned vertices


class LintScene(ts.Scene):
    """A Scene that keeps the baked parts in memory and decodes no texture."""

    fixes = True

    def texture(self, pptr, prop):
        return None

    def limb_aliases(self):
        return super().limb_aliases() if self.fixes else {}

    def _write_part(self, node, mesh, matrices, bone_names, materials, skinned):
        ts.drop_undrawn(mesh, len(materials))
        n = mesh["vertex_count"]
        if not n:
            return
        blend = ts.skin_matrices(mesh, matrices)
        verts = np.einsum("nij,nj->ni", blend[:, :3, :3], mesh["vertices"][:, :3].astype(np.float64)) + blend[:, :3, 3]
        idx = mesh.get("bone_indices")
        if idx is None:
            idx, w = np.zeros((n, 1), dtype=np.int64), np.ones((n, 1))
        else:
            w = mesh.get("weights")
            if w is None:
                w = np.zeros(idx.shape)
                w[:, 0] = 1.0
        self.parts.append({"name": node["name"], "verts": verts, "bones": bone_names, "skinned": skinned,
                           "idx": np.clip(idx.astype(np.int64), 0, max(0, len(bone_names) - 1)),
                           "w": w.astype(np.float64),
                           "role": ts.part_role(node["name"], bone_names, skinned)})


def axis_distance(points, start, seg):
    """(t along the segment, distance from its axis) of every point."""
    rel = points - start
    t = rel @ seg / float(seg @ seg)
    return t, np.linalg.norm(rel - np.outer(t, seg), axis=1)


def lint_unit(model: dict, loader: ts.Loader, fixes: bool = True, weapons: str = "limbs") -> dict:
    scene = LintScene(loader, "")
    scene.fixes = fixes
    ts.load_unit(scene, model, weapons=weapons)
    bones = {n["bone"]: n for n in scene.nodes.values() if "bone" in n}
    parent, moved = {}, {}
    for name, node in bones.items():
        chain, cur = [], node["parent"]
        while cur is not None:
            if "bone" in scene.nodes[cur]:
                chain.append(scene.nodes[cur]["bone"])
            cur = scene.nodes[cur]["parent"]
        owner = ts.twist_owner(name, chain, bones) if fixes else None
        if owner:
            moved[name] = owner
        parent[name] = owner or (chain[0] if chain else None)

    def subtree(name):
        out, grew = {name}, True
        while grew:
            grew = False
            for b, p in parent.items():
                if p in out and b not in out:
                    out.add(b)
                    grew = True
        return out

    carried, skin = {}, 0                              # bone -> the skin weight it carries; vertices of the unit
    for part in scene.parts:
        if not part["skinned"] or part["role"] == "effect":
            continue
        skin += len(part["verts"])
        for k in range(part["idx"].shape[1]):
            sums = np.bincount(part["idx"][:, k], weights=part["w"][:, k], minlength=len(part["bones"]))
            for bi in np.nonzero(sums > 0.0)[0]:
                carried[part["bones"][bi]] = carried.get(part["bones"][bi], 0.0) + float(sums[bi])

    # limbs that carry no skin, or a stump's worth: under 15 % of the other side AND under 1 % of the unit
    # (measured: Natsume's shoulder stump 156 of 30145 vertices, her right arm 1881; a whole calf next to
    # one wrapped in 20000 vertices of chain, 53_Toyo, is 3046 of 84393 and no stump)
    bare = []
    for limb in LIMBS:
        left, right = "Bip001 L " + limb, "Bip001 R " + limb
        if left not in bones or right not in bones:
            continue
        load = {side: sum(carried.get(b, 0.0) for b in subtree(name)) for side, name in (("L", left), ("R", right))}
        for side, other in (("L", "R"), ("R", "L")):
            if load[side] < 0.5 or (load[side] < STUMP * load[other] and load[side] < STUMP_SHARE * skin):
                bare.append("%s %s" % (side, limb))
    for side in ("L", "R"):                            # a sleeve skinned to the hand bone hides a missing hand:
        fingers = [b for b in bones if FINGER.match(b) and b[7] == side]    # the fingers tell (87_Torajiro)
        if fingers and "%s Hand" % side not in bare and sum(carried.get(b, 0.0) for b in fingers) < 0.5:
            bare.append("%s Fingers" % side)

    segments = {}
    for side, other_side in (("L", "R"), ("R", "L")):
        for a, b in SEGMENTS:
            ja, jb = bones.get("Bip001 %s %s" % (side, a)), bones.get("Bip001 %s %s" % (side, b))
            oa, ob = bones.get("Bip001 %s %s" % (other_side, a)), bones.get("Bip001 %s %s" % (other_side, b))
            if ja is None or jb is None:
                continue
            start, seg = ja["world"][:3, 3], jb["world"][:3, 3] - ja["world"][:3, 3]
            length = float(np.linalg.norm(seg))
            if length < 1e-4:
                continue
            own, mine, others = subtree(ja["bone"]), 0.0, {}
            for part in scene.parts:
                if not part["skinned"] or part["role"] == "effect":
                    continue
                t, lateral = axis_distance(part["verts"], start, seg)
                sel = (t > 0.3) & (t < 0.7) & (lateral < 0.3 * length)
                if oa is not None and ob is not None:   # legs close together: keep this side's skin only
                    _t, far = axis_distance(part["verts"], oa["world"][:3, 3], ob["world"][:3, 3] - oa["world"][:3, 3])
                    sel &= lateral <= far
                if not sel.any():
                    continue
                for k in range(part["idx"].shape[1]):
                    weights, index = part["w"][sel, k], part["idx"][sel, k]
                    for bi in np.unique(index):
                        total = float(weights[index == bi].sum())
                        if total <= 0.0:
                            continue
                        name = part["bones"][bi]
                        if name in own:
                            mine += total
                        else:
                            others[name] = others.get(name, 0.0) + total
            total = mine + sum(others.values())
            if total > 0.0:
                top = sorted(others.items(), key=lambda kv: -kv[1])[:3]
                segments["%s %s" % (side, a)] = {"own": round(mine / total, 3),
                                                 "others": [[n, round(v / total, 3)] for n, v in top]}
    return {"segments": segments, "no_skin": bare, "limb_aliases": scene.aliases, "twist_links": moved,
            "effect_overlays": [p["name"] for p in scene.parts if p["role"] == "effect"],
            "weapon_prefabs": ["%s (%s)" % (w["name"], w["kind"]) for w in scene.weapons],
            "weapon_prefabs_left_out": [w["name"] for w in scene.weapons_left]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="ids / unit numbers / names (default: every unit)")
    ap.add_argument("--no-fixes", action="store_true", help="measure the rigs without the exporter's repairs")
    ap.add_argument("--below", type=float, default=0.5, help="list the segments whose own share is under this (0.5)")
    ap.add_argument("--weapons", choices=("limbs", "all", "none"), default="limbs",
                    help="which weapon prefabs are hung on the unit first: the body parts among them (default, "
                         "what export_model.py does), all of them, or none (the unit prefab alone)")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    tc.check_tools(need_blender=False)
    models = tc.discover_models(tc.catalog_assets(a.export_root), a.export_root)
    if a.models:
        models = tc.find_models(models, a.models)
    loader = ts.Loader(a.export_root)
    rows, flagged, bare = {}, 0, 0
    for model in models:
        try:
            rows[model["id"]] = lint_unit(model, loader, fixes=not a.no_fixes, weapons=a.weapons)
        except Exception as exc:  # noqa: BLE001 - a prefab without a skeleton is just not a Biped unit
            rows[model["id"]] = {"error": str(exc)}
            continue
        row = rows[model["id"]]
        low = ["%s %.2f (%s)" % (k, v["own"], ", ".join("%s %.2f" % (n or "-", s) for n, s in v["others"]))
               for k, v in row["segments"].items() if v["own"] < a.below]
        notes = []
        if row["no_skin"]:
            bare += 1
            left = row["weapon_prefabs_left_out"]
            notes.append("NO SKIN on: " + ", ".join(row["no_skin"])
                         + ("   (weapon prefabs not hung on: %s)" % ", ".join(left) if left else ""))
        if row["weapon_prefabs"]:
            notes.append("weapon prefabs hung on: " + ", ".join(row["weapon_prefabs"]))
        if row["limb_aliases"]:
            notes.append("skin handed over: " + ", ".join("%s -> %s" % kv for kv in sorted(row["limb_aliases"].items())))
        if row["twist_links"]:
            notes.append("twist links moved under their limb: " + ", ".join(sorted(row["twist_links"])))
        if row["effect_overlays"]:
            notes.append("effect overlays hidden: " + ", ".join(row["effect_overlays"]))
        if low or notes:
            flagged += 1 if low else 0
            print("%-22s %s" % (model["id"], "; ".join(low) if low else "ok"))
            for note in notes:
                print("%-22s   %s" % ("", note))
    if not a.models and a.weapons == "limbs" and not a.no_fixes:
        tc.save_json(os.path.join(tc.meta_dir(a.export_root), "rig_lint.json"), rows)
    print("%d units, %d with a limb segment under %.2f, %d with a limb segment without any skin" % (
        len(rows), flagged, a.below, bare))
    return 0


if __name__ == "__main__":
    sys.exit(main())
