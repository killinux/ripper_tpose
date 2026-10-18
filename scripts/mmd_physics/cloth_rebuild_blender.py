"""Rebuild the cloth physics of an existing PMX with the mmd_cloth_physics add-on - the physics a fresh export with
the current add-on would get, without exporting the model again.

    blender -b --factory-startup --python cloth_rebuild_blender.py -- in.pmx out.pmx
        [--body-regex "^Bip0\\d\\d\\b"] [--addon-dir <folder holding mmd_cloth_physics>] [--report out.json]
        [--collision classes|near] [--no-seat] [--no-attach]

Imports the PMX with mmd_tools, deletes its dynamic bodies (breasts kept, cloth_collision_pmx.py's bust regex) and
every joint on them, runs ``mmd_cloth_physics.api.setup`` (the repo copy unless --addon-dir points at another, e.g. an
older checkout to compare), exports a scratch PMX and copies ONLY its rigid bodies and joints into the input's data:
vertices, materials, morphs and texture paths of the output are the input's, byte for byte.  The body colliders keep
their shapes (the add-on regroups them); breasts and their joints keep everything.

--body-regex: bones of the body skeleton besides the MMD standard ones (default ROE / 3ds Max Biped's ``^Bip0\\d\\d\\b``);
--same-bones instead rebuilds exactly the bones that had dynamic bodies (any game, whatever its exporter's regex).
Give Blender absolute paths.  ROE Inase a08 (2026-10-18): see scripts/mmd_physics/README.md section 8.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ADDONS = os.path.join(os.path.dirname(HERE), "blender_addons")
BUST = r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$"
SCALE = 0.08

ap = argparse.ArgumentParser()
ap.add_argument("input")
ap.add_argument("output")
ap.add_argument("--body-regex", default=r"^Bip0\d\d\b")
ap.add_argument("--same-bones", action="store_true",
                help="rebuild exactly the bones that carried dynamic bodies in the input (every other bone counts as "
                     "body) - for models whose exporter's body regex you do not know")
ap.add_argument("--prop-regex", default=r"\bProp\d*$")
ap.add_argument("--addon-dir", default=REPO_ADDONS)
ap.add_argument("--report")
ap.add_argument("--collision", default="classes", choices=("classes", "near"))
ap.add_argument("--no-seat", action="store_true")
ap.add_argument("--no-attach", action="store_true")
ap.add_argument("--drop-test", type=int, default=0, metavar="FRAMES",
                help="also run the add-on's drop test (rest pose, this many frames) and report torn / restless bodies")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
if os.path.abspath(args.input) == os.path.abspath(args.output):
    raise SystemExit("refusing to overwrite the input; write a new file")
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=args.input, scale=SCALE,
                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"}, log_level="ERROR")
from mmd_tools.core import pmx  # noqa: E402
from mmd_tools.core.model import Model  # noqa: E402

root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
model = Model(root)
arm = model.armature()
bust = re.compile(BUST, re.IGNORECASE)


def bone_j(obj):
    pb = arm.pose.bones.get(obj.mmd_rigid.bone) if obj.mmd_rigid.bone else None
    return (pb.mmd_bone.name_j or pb.name) if pb is not None else ""


rigids = list(model.rigidBodies())
doomed = {o.name for o in rigids if str(o.mmd_rigid.type) != "0"
          and not bust.search(bone_j(o)) and not bust.search(o.mmd_rigid.name_j or "")}
cloth_bones = sorted({bpy.data.objects[n].mmd_rigid.bone for n in doomed if bpy.data.objects[n].mmd_rigid.bone})
body_regex = args.body_regex
if args.same_bones:
    body_regex = r"^(?!(?:%s)$)" % "|".join(re.escape(n) for n in cloth_bones) if cloth_bones else r"^"
joints = list(model.joints())
dead_joints = [j for j in joints if j.rigid_body_constraint is None
               or j.rigid_body_constraint.object1 is None or j.rigid_body_constraint.object2 is None
               or j.rigid_body_constraint.object1.name in doomed or j.rigid_body_constraint.object2.name in doomed]
for j in dead_joints:
    bpy.data.objects.remove(j, do_unlink=True)
for name in doomed:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
print("stripped %d dynamic bodies and %d joints (kept %d bodies, %d joints)" % (
    len(doomed), len(dead_joints), len(rigids) - len(doomed), len(joints) - len(dead_joints)), flush=True)

sys.path.insert(0, args.addon_dir)
from mmd_cloth_physics import api  # noqa: E402

print("add-on:", os.path.dirname(api.__file__), flush=True)
kwargs = {}
if "collision" in api.setup.__code__.co_varnames:          # an older copy (for comparisons) has no such options
    kwargs = {"collision": args.collision, "seat": not args.no_seat, "attach_ends": not args.no_attach}
report = api.setup(root, body_regex=body_regex, prop_regex=args.prop_regex, log=print, **kwargs)
if args.drop_test:
    from mmd_cloth_physics import validate  # noqa: E402

    drop = validate.drop_test(root, args.drop_test)
    for line in drop["lines"]:
        print(line)
    report["drop_test"] = {"summary": drop["summary"], "bad": drop["bad"],
                           "worst": [[round(m, 3), round(s, 2), round(v, 3), b] for m, s, v, _n, b in drop["worst"]]}

scratch = tempfile.mkdtemp(prefix="cloth_rebuild_")
tmp = os.path.join(scratch, "rebuilt.pmx")
bpy.ops.object.select_all(action="DESELECT")
for obj in [root] + list(root.children_recursive):
    try:
        obj.hide_set(False)
        obj.select_set(True)
    except RuntimeError:
        pass
bpy.context.view_layer.objects.active = root
bpy.ops.mmd_tools.export_pmx(filepath=tmp, scale=1.0 / SCALE, copy_textures=False, log_level="ERROR")

# splice: the input's data with the rebuilt rigid bodies and joints (bone indices mapped by name)
src = pmx.load(args.input)
new = pmx.load(tmp)
index = {b.name: i for i, b in enumerate(src.bones)}
for r in new.rigids:
    if r.bone is not None and r.bone >= 0:
        name = new.bones[r.bone].name
        if name not in index:
            raise SystemExit("rebuilt rigid body %s follows bone %s, which the input does not have" % (r.name, name))
        r.bone = index[name]
src.rigids, src.joints = new.rigids, new.joints
pmx.save(args.output, src, add_uv_count=src.header.additional_uvs)
for f in os.listdir(scratch):
    os.remove(os.path.join(scratch, f))
os.rmdir(scratch)
summary = {"input": args.input, "output": args.output, "rigids": len(src.rigids), "joints": len(src.joints),
           "stripped": len(doomed), "addon": os.path.dirname(api.__file__), "seconds": round(time.time() - t0)}
for key, value in report.items():                          # the add-on's counts (what it built) under their own names
    if key != "garments":
        summary.setdefault(key if key not in summary else "addon_" + key, value)
summary["garments"] = report.get("garments", [])
brief = {k: summary[k] for k in ("rigids", "joints", "stripped", "seconds")}
if "drop_test" in report:
    brief["drop_test"] = report["drop_test"]["summary"]
print("SUMMARY", json.dumps(brief, ensure_ascii=False), flush=True)
if args.report:
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
print("wrote %s" % args.output, flush=True)
