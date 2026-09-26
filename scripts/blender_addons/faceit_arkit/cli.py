# -*- coding: utf-8 -*-
"""Headless run of the add-on (same functions as the panel's buttons).

    blender -b --factory-startup <model.blend> --python cli.py -- --dna <face.dna> --out <out.blend>
            [--package <face.uasset.bin>] [--head <bone>] [--source FACECAP|EPIC|IFACIALMOCAP|TILE]
            [--object <any object of the model>] [--no-weights] [--no-faceit] [--no-backup]

Order: restore the full skin weights (package given, or <dna stem>.uasset.bin beside the DNA) ->
bake the 52 ARKit shape keys -> register with Faceit (enabled for this run only).  Prints
FACEIT_ARKIT_REPORT={json}.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import addon_utils  # noqa: E402
import bpy  # noqa: E402

from faceit_arkit import api, faceit_link  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--dna", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--package", default="")
    ap.add_argument("--head", default="")
    ap.add_argument("--source", default="FACECAP")
    ap.add_argument("--object", default="")
    ap.add_argument("--no-weights", action="store_true")
    ap.add_argument("--no-faceit", action="store_true")
    ap.add_argument("--no-backup", action="store_true", help="no .blend1 when --out already exists "
                    "(sets Save Versions to 0 for this run; use with --factory-startup)")
    args = ap.parse_args(argv)

    obj = bpy.data.objects[args.object] if args.object else next(
        o for o in bpy.data.objects if o.type == "ARMATURE" and any(b.name.upper().startswith("FACIAL_")
                                                                    for b in o.data.bones))
    report = {"model": obj.name}
    package = "" if args.no_weights else (args.package or api.companion_package(args.dna))
    if package:
        report["weights"] = api.restore_weights(obj, package)
    report["bake"] = api.bake_arkit(obj, args.dna)
    if not args.no_faceit:
        name = faceit_link.faceit_package()
        if name is None:
            report["faceit"] = "not installed"
        else:
            addon_utils.enable(name, default_set=False)       # session only, the preferences stay untouched
            report["faceit"] = api.register_faceit(obj, head_bone=args.head, source=args.source,
                                                   require_enabled=False)
    if args.no_backup:
        bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    report["saved"] = os.path.abspath(args.out)
    print("FACEIT_ARKIT_REPORT=" + json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
