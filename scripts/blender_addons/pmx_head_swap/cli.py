# -*- coding: utf-8 -*-
"""PMX Head Swap from the command line (Blender headless or a plain Python with numpy + Pillow):

    blender -b --factory-startup --python cli.py -- head_donor.pmx body_target.pmx out.pmx [options]
    python cli.py head_donor.pmx body_target.pmx out.pmx [options]

Options: --head "a,b"      the donor's head materials (default: face / eyes / lashes / brows / hair by name)
         --remove "a,b"    the target's materials that go (default: the same kinds, incl. *_nude copies)
         --blend 4         cm up the neck over which the head's neck takes the body's ring (default 4)
         --tone seam|whole|none   skin colour of the face texture: gain + seam gradient (default) / gain only / as is
         --scale 1.0       head scale about the neck ring
         --prefix a08
Prints the report as JSON on the last line (REPORT {...})."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(description="put one PMX model's head on another PMX model's body")
    ap.add_argument("donor")
    ap.add_argument("target")
    ap.add_argument("out")
    ap.add_argument("--head", default="")
    ap.add_argument("--remove", default=None)
    ap.add_argument("--blend", type=float, default=4.0)
    ap.add_argument("--tone", default="seam", choices=("seam", "whole", "none"))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args(argv)
    head = [s.strip() for s in args.head.split(",") if s.strip()] or None
    remove = None if args.remove is None else [s.strip() for s in args.remove.split(",") if s.strip()]
    report = core.swap_head(args.donor, args.target, args.out, head_materials=head, remove_materials=remove,
                            blend_cm=args.blend, tone=args.tone, scale=args.scale, prefix=args.prefix,
                            log=lambda s: print(s, flush=True))
    print("REPORT " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
