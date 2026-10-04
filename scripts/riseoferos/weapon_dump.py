"""Dump an outfit's battle weapon (Rise of Eros) for Blender: the battle (LD) prefab's skinned wp_* meshes at the HD
rest, in Unity world space, with the HD skeleton's rest - add_weapon_blender.py builds them into a .blend.

The HD prefab of some outfits has no weapon mesh (a08's greatsword is shown only in battle).  pmx_add_weapon.py
appends it to a PMX; this gives the same meshes, rest and texture to the .blend (and so to the XPS made from it).

  python weapon_dump.py a08 --out D:\\roe_exports\\_hq_runs\\pc_a08_hd\\weapon.json
  options: --albedo <texture name> (default <weapon>_rgbx_Albedo)
Exit 3 (no file written) when the outfit's battle prefab has no skinned weapon.
"""
import argparse
import json
import os
import sys

import UnityPy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decode_roe_clip as dec  # noqa: E402
import pmx_add_weapon as paw  # noqa: E402
from roe_motion_common import bundles  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="outfit id, e.g. a08")
    ap.add_argument("--out", required=True)
    ap.add_argument("--albedo", help="the weapon material's albedo (default <weapon>_rgbx_Albedo)")
    args = ap.parse_args()
    found = bundles(args.id)
    if not found["showcase"] or not found["battle"]:
        sys.exit("need both bundles of %s: %s" % (args.id, found))
    skeleton = dec.read_skeleton(UnityPy.load(found["showcase"]))
    renderers = paw.weapon_renderers(UnityPy.load(found["battle"]))
    if not renderers:
        print("no skinned wp_* renderer in %s" % found["battle"])
        sys.exit(3)
    world = paw.rest_worlds(skeleton)
    world_of = {b["name"]: world[i] for i, b in enumerate(skeleton)}
    prefix = os.path.commonprefix([r["name"] for r in renderers]).rstrip("_")
    albedo = args.albedo or "%s_rgbx_Albedo" % prefix
    tex_src, material = paw.weapon_texture(args.id, albedo, print)
    out = {"id": args.id, "material": material, "albedo": albedo, "pmx_texture": tex_src,
           "battle_bundle": os.path.basename(found["battle"]),
           "skeleton": [{"name": b["name"], "parent": b["parent"], "world": world[i].tolist()}
                        for i, b in enumerate(skeleton)],
           "renderers": []}
    for r in renderers:
        V, N = paw.skin_at_rest(r, world_of)
        out["renderers"].append({"name": r["name"], "v": V.tolist(), "n": N.tolist(), "uv": r["uv"].tolist(),
                                 "tris": [list(t) for t in r["tris"]], "bones": r["bones"],
                                 "skin": [[[r["bones"][slot], float(w)] for slot, w in pairs] for pairs in r["skin"]]})
        print("   %s: %d vertices, %d triangles, bones %s" % (r["name"], len(V), len(r["tris"]), ", ".join(r["bones"])))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print("ROE_WEAPON_DUMP=" + json.dumps({"out": args.out, "material": material,
                                          "renderers": [r["name"] for r in out["renderers"]]}))


if __name__ == "__main__":
    main()
