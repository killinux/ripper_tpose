"""How far the breasts of a PMX swing over a dance under MMD's physics (mmd_scene.mmd_like), no render.

  blender -b --factory-startup --python bust_dance.py -- <model.pmx> [--vmd <motion.vmd>] [--frames 0] [--label x]

``--vmd`` defaults to test_motion.VMD (the 10 s gesture dance), ``--frames`` 0 = the whole motion.

Per breast bone: its swing against the parent over the motion (lead-in skipped) - median, 10th / 90th
percentile, largest, the 10-90 % range (how much it moves), and the change per frame (how fast; what reads as
bouncing).  Last line printed: BUST_DANCE={...}.  2026-10-04, 900 frames of the shake dance: the template joint
(450 / +-10 deg) swung 5.6-8.6 deg (10-90 %) on PCF_002 / 008 / 012, bust_physics.py's 13-20 deg.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmd_scene  # noqa: E402
import test_motion  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("--vmd", default=test_motion.VMD)
ap.add_argument("--frames", type=int, default=0, help="motion frames after the lead-in (0 = all)")
ap.add_argument("--label", default="")
args = ap.parse_args(argv)
scene, root, rig, arm = mmd_scene.load(args.pmx)
rig.build()
mmd_scene.mmd_like(scene)
mmd_scene.add_motion(root, args.vmd, args.frames)
swing = mmd_scene.breast_bones(arm, scene)
trace = {pb.name: [] for pb in swing}
for _frame in mmd_scene.run_physics(scene):
    for pb in swing:
        trace[pb.name].append(mmd_scene.swing_deg(pb))
out = {"label": args.label or os.path.basename(args.pmx), "frames": scene.frame_end}


def pct(values, q):
    return values[int(q * (len(values) - 1))]


for bone, angles in trace.items():
    a = angles[mmd_scene.MARGIN:]
    s = sorted(a)
    step = sorted(abs(a[i + 1] - a[i]) for i in range(len(a) - 1))
    out[bone] = {"median": round(pct(s, 0.5), 1), "p10": round(pct(s, 0.1), 1), "p90": round(pct(s, 0.9), 1),
                 "max": round(s[-1], 1), "swing_10_90": round(pct(s, 0.9) - pct(s, 0.1), 1),
                 "per_frame_median": round(pct(step, 0.5), 2), "per_frame_p90": round(pct(step, 0.9), 2)}
print("BUST_DANCE=" + json.dumps(out, ensure_ascii=False), flush=True)
