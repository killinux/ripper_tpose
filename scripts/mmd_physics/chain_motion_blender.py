"""How chain ends move in a dance: per chain end its turn against the bone above it (pose vs rest), every frame of the
MMD-like baked physics (as skin_clip_blender.py bakes it) - to see chain ends that are locked (tiny swing) or that
twitch (the turn changes direction from frame to frame).

    blender -b --factory-startup --python chain_motion_blender.py -- <pmx> <vmd> <out.json>
        [--bones auto | "a,b,c"] [--series "a,b"] [--frames a-b]

--bones auto (default): every chain end - a bone with a dynamic rigid body whose parent has one and whose children
have none - breasts left out.  Per bone, in degrees:
  mean      average turn away from the rest pose
  range     5-95 % spread of that turn (how far it swings)
  per_frame average turn from one frame to the next
  jitter    how much that frame-to-frame turn changes from one frame to the next, against the turn itself:
            ~0.3-0.6 a smooth swing, ~1 and above a chain end that keeps reversing (twitching), up to 2
The summary has the medians and how many ends jitter above 1.0.  --series writes those bones' per-frame turn into the
JSON (plot them to tell a swing from a twitch).  Angles are the shortest rotation (q and -q are the same turn).

Found with it (2026-10-24, gesture dance): mmd_cloth_physics 0.2.0's false "A." joints held chain ends at 7-11 deg
mean turn (13 deg swing); free they hang at 19-20 deg and swing 16-24 deg.  Cloth that collides with the body twitches
(median jitter ROE j07 0.57 -> 1.04, d07 0.72 -> 1.15) - see scripts/blender_addons/mmd_cloth_physics README 0.2.3.
Give Blender absolute paths.
"""
import argparse
import json
import math
import os
import re
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mmd_like import mmd_like_physics  # noqa: E402

SCALE, MARGIN = 0.08, 30
BUST = r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$"
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("vmd")
ap.add_argument("out")
ap.add_argument("--bones", default="auto", help='"auto" (every chain end) or PMX bone names, comma separated')
ap.add_argument("--series", default="", help="bones whose per-frame turn goes into the JSON (comma separated)")
ap.add_argument("--frames", default="", help="a-b in scene frames (default: the whole dance after the lead-in)")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"},
                               log_level="ERROR")
from mmd_tools.core.model import Model  # noqa: E402

root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
rig = Model(root)
arm = rig.armature()
rig.build()
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o.type in ("ARMATURE", "MESH", "EMPTY"):
        try:
            o.select_set(True)
        except RuntimeError:
            pass
bpy.context.view_layer.objects.active = root
bpy.ops.mmd_tools.import_vmd(filepath=args.vmd, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                             update_scene_settings=True)
scene = bpy.context.scene
mmd_like_physics(scene, SCALE, 98.0, None)
world = scene.rigidbody_world
world.enabled = True
world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
    bpy.ops.ptcache.free_bake()
    bpy.ops.ptcache.bake(bake=True)
print("baked in %.0f s" % (time.time() - t0), flush=True)

by_name = {(pb.mmd_bone.name_j or pb.name): pb for pb in arm.pose.bones}
if args.bones == "auto":
    bust = re.compile(BUST, re.IGNORECASE)
    dyn = set()
    for o in rig.rigidBodies():
        pb = arm.pose.bones.get(o.mmd_rigid.bone) if o.mmd_rigid.bone else None
        if pb is not None and str(o.mmd_rigid.type) != "0":
            dyn.add(pb.mmd_bone.name_j or pb.name)
    want = sorted(n for n in dyn if not bust.search(n) and by_name[n].parent is not None
                  and (by_name[n].parent.mmd_bone.name_j or by_name[n].parent.name) in dyn
                  and not any((c.mmd_bone.name_j or c.name) in dyn for c in by_name[n].children))
else:
    want = [b for b in args.bones.split(",") if b]
missing = [b for b in want if b not in by_name or by_name[b].parent is None]
if missing:
    print("not found / no parent:", missing)
track = [b for b in want if b not in missing]
rest = {b: (by_name[b].parent.bone.matrix_local.inverted() @ by_name[b].bone.matrix_local).to_quaternion()
        for b in track}
if args.frames:
    f0, f1 = (int(x) for x in args.frames.split("-"))
else:
    f0, f1 = scene.frame_start + MARGIN, scene.frame_end
series = {b: [] for b in track}
for f in range(f0, f1 + 1):
    scene.frame_set(f)
    for b in track:
        pb = by_name[b]
        series[b].append(rest[b].rotation_difference((pb.parent.matrix.inverted() @ pb.matrix).to_quaternion()))


def turn(q):
    """The rotation's angle, 0-180 deg: q and -q are the same rotation (Quaternion.angle gives 2 acos w, up to 360)."""
    return math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))


keep = {b for b in args.series.split(",") if b}
out = {"pmx": args.pmx, "vmd": args.vmd, "frames": f1 - f0 + 1, "bones": {}, "series": {}}
for b, qs in series.items():
    ang = np.array([turn(q) for q in qs])
    inc = [qs[k].rotation_difference(qs[k + 1]) for k in range(len(qs) - 1)]
    step = np.array([turn(d) for d in inc])
    accel = np.array([turn(inc[k].rotation_difference(inc[k + 1])) for k in range(len(inc) - 1)])
    out["bones"][b] = {"mean": round(float(ang.mean()), 2),
                       "range": round(float(np.percentile(ang, 95) - np.percentile(ang, 5)), 2),
                       "per_frame": round(float(step.mean()), 3),
                       "jitter": round(float(accel.mean() / max(step.mean(), 1e-6)), 3)}
    if b in keep:
        out["series"][b] = [round(float(a), 3) for a in ang]
vals = list(out["bones"].values())
if vals:
    med = lambda k: float(np.median([v[k] for v in vals]))          # noqa: E731
    out["summary"] = {"ends": len(vals), "jitter_median": round(med("jitter"), 3),
                      "jitter_above_1": sum(v["jitter"] > 1.0 for v in vals), "range_median": round(med("range"), 2),
                      "mean_median": round(med("mean"), 2), "seconds": round(time.time() - t0)}
    for b, v in sorted(out["bones"].items(), key=lambda kv: -kv[1]["jitter"]):
        print("%-28s mean %6.2f  range %6.2f  per frame %6.3f  jitter %.2f" % (b, v["mean"], v["range"],
                                                                             v["per_frame"], v["jitter"]))
    print("SUMMARY", json.dumps(out["summary"]), flush=True)
with open(args.out, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
