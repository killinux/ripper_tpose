# -*- coding: utf-8 -*-
"""PMX Expression Transfer from the command line (Blender headless or a plain Python with numpy):

    blender -b --factory-startup --python cli.py -- donor.pmx target.pmx out.pmx [options]
    python cli.py donor.pmx target.pmx out.pmx [options]
    python cli.py donor.pmx target.pmx --list          # what would be carried, and why not

Options: --morphs "あ,い,う"   the donor's expressions to carry (default: its MMD expressions the target lacks)
         --replace           a same-named expression of the target is replaced (default: skipped)
         --no-lid            no lid closure correction
         --no-jaw            teeth and tongue stay still
         --strength "brow=1,eye=1,mouth=1,other=1"
Prints the report as JSON on the last line (REPORT {...})."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

PANELS = {"brow": 1, "eye": 2, "mouth": 3, "other": 4}


def main(argv):
    ap = argparse.ArgumentParser(description="copy one PMX model's facial expressions onto another PMX model's face")
    ap.add_argument("donor")
    ap.add_argument("target")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--morphs", default="")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--no-lid", action="store_true")
    ap.add_argument("--no-jaw", action="store_true")
    ap.add_argument("--strength", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    if args.list or not args.out:
        for name, name_e, cat, kind, sel, note in core.list_morphs(args.donor, args.target):
            print("%s %-10s %-12s panel %d  %-8s %s" % ("[x]" if sel else "[ ]", name, name_e, cat, kind, note))
        return
    morphs = [s.strip() for s in args.morphs.split(",") if s.strip()] or None
    strength = {}
    for part in args.strength.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            strength[PANELS[k.strip()]] = float(v)
    report = core.transfer_expressions(args.donor, args.target, args.out, morphs=morphs, replace=args.replace,
                                       lid=not args.no_lid, jaw=not args.no_jaw, strength=strength,
                                       log=lambda s: print(s, flush=True))
    print("REPORT " + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
