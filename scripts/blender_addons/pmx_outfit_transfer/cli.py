# -*- coding: utf-8 -*-
"""PMX Outfit Transfer from the command line (Blender headless or a plain Python with numpy):

    blender -b --factory-startup --python cli.py -- donor.pmx target.pmx out.pmx [options]
    python cli.py donor.pmx target.pmx out.pmx [options]            (slower: no BVH)

Options: --materials "a,b"  (donor materials; default: everything that is not body / face / hair / eyes / weapon)
         --donor-body M --target-body M  (body materials; default: ROE *_nk_body / *_nk_body_nude)
         --no-fit  --near 2 --far 12  --no-rotation  --split bone|island|none --min-piece 100  --prefix g05
         --no-isolate  --no-body-collision  --hide-morph 衣服非表示_材質  (a nude target without one: a new
         衣服非表示 for the new clothes)
         --no-follow-body  --follow-reach 1.5 --follow-fade 2  (cm: parts on the skin take the skin's weights)
         --donor-body-pmx nude.pmx  (the donor's body from the same character's nude model: outfit models of other
         games often have no body under the clothes)
         --min-gap 1.0  (mm: garment vertices closer to the target's skin, or inside it, are pushed out; 0 = off)
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
    ap.add_argument("--no-follow-body", action="store_true",
                    help="keep the donor's weights everywhere (default: parts on the skin take the skin's weights)")
    ap.add_argument("--follow-reach", type=float, default=core.FOLLOW_REACH_CM)
    ap.add_argument("--follow-fade", type=float, default=core.FOLLOW_FADE_CM)
    ap.add_argument("--donor-body-pmx", default=None,
                    help="take the donor's body from this PMX (the same character's nude model)")
    ap.add_argument("--min-gap", type=float, default=core.MIN_GAP_MM,
                    help="mm between the clothes and the target's skin (pushed out where closer); 0 = off")
    args = ap.parse_args(argv)
    mats = [s.strip() for s in args.materials.split(",") if s.strip()] or None
    report = core.transfer(args.donor, args.target, args.out, materials=mats, donor_body=args.donor_body,
                           target_body=args.target_body, fit=not args.no_fit, near_cm=args.near, far_cm=args.far,
                           align_rotation=not args.no_rotation, split=args.split, min_piece=args.min_piece,
                           prefix=args.prefix, isolate=not args.no_isolate,
                           collide_body=not args.no_body_collision, hide_morph=args.hide_morph,
                           follow_body=not args.no_follow_body, follow_reach_cm=args.follow_reach,
                           follow_fade_cm=args.follow_fade, donor_body_pmx=args.donor_body_pmx, min_gap_mm=args.min_gap,
                           log=lambda s: print(s, flush=True))
    print("REPORT " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
