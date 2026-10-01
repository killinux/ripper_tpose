"""Blender worker for export_roe_motions.py: which skinned bones a decoded clip scales, relative to the pose the
PMX was built in (the bind pose).  MMD bones cannot scale; export_roe_motions.py turns each uniformly scaled bone
group into a vertex morph (pmx_add_scale_morph.py) and keys it frame by frame.

  blender -b --factory-startup --python roe_motion_scale.py -- <out.json> <clip1.json> [<clip2.json> ...]

Output: {clip name: {"groups": [{"bones": [...], "factors": [per frame], "uniform": bool}], "frames": n}}.
A group is the bones whose scale curve is the same frame by frame (the g04 fan: 7 ribs at 0.15 in every showcase
clip).  "uniform" is False when the three axes differ by more than 3% (thigh "Muscle Strand" helpers stretch
along one axis): a vertex morph about the bone head cannot reproduce that, so it is only reported.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_roe_vmd import Game  # noqa: E402

TOL = 0.03          # a bone counts as scaled when its world scale leaves 1 +- 3% of its bind scale


def analyse(path):
    game = Game(json.load(open(path, encoding="utf-8")))
    rest = game.rest_world()
    rest_scale = [m.to_scale() for m in rest]
    curves, uneven = {}, set()
    for f in range(len(game.frames)):
        world = game.world(f)
        for i, m in enumerate(world):
            if "bind" not in game.bones[i]:
                continue                      # only skinned bones change what the mesh looks like
            s = m.to_scale()
            ratios = [s[k] / rest_scale[i][k] for k in range(3)]
            mean = sum(ratios) / 3
            if max(ratios) - min(ratios) > TOL * max(abs(mean), 1e-6):
                uneven.add(i)
            curves.setdefault(i, []).append(mean)
    scaled = {i: c for i, c in curves.items() if max(abs(v - 1.0) for v in c) > TOL}
    groups = {}
    for i, c in scaled.items():
        key = tuple(round(v, 3) for v in c)
        groups.setdefault(key, []).append(i)
    out = []
    for key, members in groups.items():
        out.append({"bones": sorted(game.bones[i]["name"] for i in members),
                    "factors": [round(v, 5) for v in scaled[members[0]]],
                    "uniform": not any(i in uneven for i in members)})
    return {"groups": out, "frames": len(game.frames)}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    report = {}
    for path in args[1:]:
        name = os.path.splitext(os.path.basename(path))[0]
        report[name] = analyse(path)
        for g in report[name]["groups"]:
            print("SCALE %-12s %-55s %s %.3f..%.3f" % (name, ",".join(g["bones"])[:55], "uniform" if g["uniform"] else "UNEVEN",
                                                      min(g["factors"]), max(g["factors"])))
    json.dump(report, open(args[0], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ROE_SCALE_DONE", args[0])


if __name__ == "__main__":
    main()
