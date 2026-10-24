# -*- coding: utf-8 -*-
"""PMX Outfit Transfer from the command line (Blender headless or a plain Python with numpy):

    blender -b --factory-startup --python cli.py -- donor.pmx target.pmx out.pmx [options]
    python cli.py donor.pmx target.pmx out.pmx [options]            (slower: no BVH)

Options: --materials "a,b"  (donor materials; default: everything that is not body / face / hair / eyes / weapon)
         --donor-body M --target-body M  (body materials; default: ROE *_nk_body / *_nk_body_nude)
         --no-fit  --near 2 --far 12  --no-rotation  --split bone|island|none --min-piece 100  --prefix g05
         --no-isolate  --no-body-collision  --hide-morph 衣服非表示_材質
Prints the report as JSON on the last line (REPORT {...})."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(description="dress one PMX in another PMX's clothes")
    ap.add_argument("donor")
    ap.add_argument("target")
    ap.add_argument("out")
    ap.add_argument("--materials", default="")
    ap.add_argument("--donor-body", default=None)
    ap.add_argument("--target-body", default=None)
    ap.add_argument("--no-fit", action="store_true")
    ap.add_argument("--near", type=float, default=2.0)
    ap.add_argument("--far", type=float, default=12.0)
    ap.add_argument("--no-rotation", action="store_true")
    ap.add_argument("--split", default="bone", choices=("bone", "island", "none"),
                    help="new materials: one per bone the pieces hang on / one per connected piece / as the donor's")
    ap.add_argument("--min-piece", type=int, default=100)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--no-isolate", action="store_true")
    ap.add_argument("--no-body-collision", action="store_true")
    ap.add_argument("--hide-morph", default="")
    args = ap.parse_args(argv)
    mats = [s.strip() for s in args.materials.split(",") if s.strip()] or None
    report = core.transfer(args.donor, args.target, args.out, materials=mats, donor_body=args.donor_body,
                           target_body=args.target_body, fit=not args.no_fit, near_cm=args.near, far_cm=args.far,
                           align_rotation=not args.no_rotation, split=args.split, min_piece=args.min_piece,
                           prefix=args.prefix, isolate=not args.no_isolate,
                           collide_body=not args.no_body_collision, hide_morph=args.hide_morph,
                           log=lambda s: print(s, flush=True))
    print("REPORT " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
