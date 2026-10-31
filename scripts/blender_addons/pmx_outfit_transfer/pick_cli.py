# -*- coding: utf-8 -*-
"""Pick the parts of a PMX model from the command line: drop materials with the bones, rigid bodies, joints, morph
entries and textures that only they used (parts.py).  Blender headless or a plain Python:

    blender -b --factory-startup --python pick_cli.py -- model.pmx [out.pmx] --remove "a,b" [options]
    python pick_cli.py model.pmx [out.pmx] --remove "a,b" [options]

--remove "a,b"   materials to drop          --keep "a,b"   or: materials to keep (everything else goes)
--remove-like s  also drop every material whose name contains s (repeatable, e.g. --remove-like wp_)
--list           print the materials (index, faces) and stop
--dry-run        print what would go and stop
--keep-bones     drop vertices / faces / morph entries only, keep every bone, rigid body and joint
--keep-empty-morphs   keep morphs that lose all their entries
--split "a,b"    instead: cut these materials into parts (--split-mode bone | island, --min-piece 100) and write
                 <model>_拆开.pmx (same folder); pick from that file afterwards
out.pmx defaults to <model>_挑零件.pmx next to the model (_挑零件2 ... when taken); never overwritten.
Prints the report as JSON on the last line (REPORT {...})."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402
import parts  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(description="drop parts (materials) of a PMX with everything only they used")
    ap.add_argument("model")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--remove", default="")
    ap.add_argument("--remove-like", action="append", default=[])
    ap.add_argument("--keep", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-bones", action="store_true")
    ap.add_argument("--keep-empty-morphs", action="store_true")
    ap.add_argument("--split", default="")
    ap.add_argument("--split-mode", default="bone", choices=("bone", "island"))
    ap.add_argument("--min-piece", type=int, default=100)
    args = ap.parse_args(argv)
    if args.split:
        report = parts.split_parts(args.model, args.out, names=[s.strip() for s in args.split.split(",") if s.strip()],
                                   mode=args.split_mode, min_piece=args.min_piece, log=lambda s: print(s, flush=True))
        print("REPORT " + json.dumps(report, ensure_ascii=False), flush=True)
        return
    if args.list:
        M = core.pmx_module().load(args.model)
        for i, mt in enumerate(M.materials):
            print("%3d  %-40s %7d faces" % (i, mt.name, mt.vertex_count // 3))
        return
    remove = [s.strip() for s in args.remove.split(",") if s.strip()]
    if args.remove_like:
        M = core.pmx_module().load(args.model)
        remove += [mt.name for mt in M.materials if any(s in mt.name for s in args.remove_like)
                   and mt.name not in remove]
    keep = [s.strip() for s in args.keep.split(",") if s.strip()] if args.keep is not None else None
    report = parts.pick_parts(args.model, args.out, remove=remove, keep=keep, bones=not args.keep_bones,
                              empty_morphs=not args.keep_empty_morphs, dry_run=args.dry_run,
                              log=lambda s: print(s, flush=True))
    print("REPORT " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
