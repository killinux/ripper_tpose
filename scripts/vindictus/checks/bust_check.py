"""What moves with the breasts of a PMX and how far they swing under MMD's gravity (Blender 3.6, background).

  blender -b --factory-startup --python bust_check.py -- <model.pmx> <out dir> [--deg 18] [--axis pitch|yaw]
          [--renders]

1. Pose test (no physics): both swinging breast bones turned by ``--deg`` (default: the joint's own limit) about
   the model's left-right axis (pitch: down / up) or the vertical axis (yaw).  Per material: vertices moved more
   than 3 mm, their largest / 95th-percentile move; poke-through: a vertex that sat behind another material's
   surface at rest (within 2 cm, behind its normal) and ends more than 1 mm in front of it - the skin coming out
   through a top that does not follow, or two layers of a dress sliding through each other.
2. Hop test (mmd_scene.mmd_like physics): stand 30 frames, four 5 cm dips of センター (14 frames each, ~2 Hz),
   stand 60 frames; each breast bone's swing against its parent per frame: the rest droop (frame 30), the range
   while hopping, how long it takes to calm down after.
3. ``--renders``: chest close-ups at rest (side, front) and turned down / up (side).

Writes <out>/<pmx name>_bust.json; the last line printed is BUST_CHECK={...}.  2026-10-04 on all 15 Fiona
outfits: clothes follow the breasts everywhere, 1.0-1.7 cm at the template's 10 deg (README, 胸部物理按 MMD 重力定).
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector, kdtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmd_scene  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("out")
ap.add_argument("--deg", type=float, help="pose-test angle (default: the joint's limit on that axis)")
ap.add_argument("--axis", choices=("pitch", "yaw"), default="pitch")
ap.add_argument("--renders", action="store_true")
args = ap.parse_args(argv)
name = os.path.splitext(os.path.basename(args.pmx))[0]
os.makedirs(args.out, exist_ok=True)
scene, root, rig, arm = mmd_scene.load(args.pmx)
meshes = list(rig.meshes())
swing = mmd_scene.breast_bones(arm, scene)
report = {"pmx": args.pmx, "breast_bones": [pb.name for pb in swing]}
AXIS = {"pitch": "X", "yaw": "Z"}[args.axis]
if args.deg is None and swing:
    joint = next((o for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT" and o.rigid_body_constraint
                  and o.rigid_body_constraint.object2 and o.rigid_body_constraint.object2.mmd_rigid.bone == swing[0].name),
                 None)
    upper = getattr(joint.rigid_body_constraint, "limit_ang_%s_upper" % AXIS.lower()) if joint else math.radians(10)
    angle = abs(upper)
else:
    angle = math.radians(args.deg or 10.0)
report["pose_deg"] = round(math.degrees(angle), 1)
report["pose_axis"] = args.axis


def evaluated():
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    out = []
    for obj in meshes:
        ev = obj.evaluated_get(graph)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        no = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        me.vertices.foreach_get("normal", no)
        mw = np.array(obj.matrix_world, np.float32)
        out.append((co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3], no.reshape(-1, 3) @ mw[:3, :3].T))
        ev.to_mesh_clear()
    return out


def turn(a):
    """Both breast bones turned by ``a`` about AXIS at their heads (pitch + = front down)."""
    for pb in swing:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for pb in swing:
        head = pb.head.copy()
        pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(a, 4, AXIS) @ Matrix.Translation(-head) @ pb.matrix
        bpy.context.view_layer.update()


# -- 1. pose test --------------------------------------------------------------------------------------------
if swing:
    rest = evaluated()
    posed = {}
    for label, a in (("down", angle), ("up", -angle)):
        turn(a)
        posed[label] = evaluated()
    turn(0.0)
    per_material, poke = {}, {}
    for mi, obj in enumerate(meshes):
        mat = np.full(len(obj.data.vertices), -1, np.int32)
        for poly in obj.data.polygons:
            mat[list(poly.vertices)] = poly.material_index
        names = [(s.material.name if s.material else "?") for s in obj.material_slots]
        co0, no0 = rest[mi]
        trees = {}
        for k in range(len(names)):
            idx = np.nonzero(mat == k)[0]
            if len(idx):
                tree = kdtree.KDTree(len(idx))
                for j in idx:
                    tree.insert(co0[j], int(j))
                tree.balance()
                trees[k] = tree
        for label, ((co1, no1)) in ((lbl, posed[lbl][mi]) for lbl in ("down", "up")):
            moved_cm = np.linalg.norm(co1 - co0, axis=1) * 100.0
            for k, mname in enumerate(names):
                sel = (mat == k) & (moved_cm > 0.3)
                if sel.any():
                    vals = np.sort(moved_cm[sel])
                    per_material.setdefault(mname, {})[label] = {
                        "moved": int(sel.sum()), "of": int((mat == k).sum()), "max_cm": round(float(vals[-1]), 2),
                        "p95_cm": round(float(vals[int(0.95 * (len(vals) - 1))]), 2)}
            for j in np.nonzero(moved_cm > 0.3)[0]:
                best = None
                for k, tree in trees.items():
                    if k == mat[j]:
                        continue
                    hit = tree.find(co0[j])
                    if hit[0] is None or hit[2] > 0.02:
                        continue
                    u = hit[1]
                    if np.dot(co0[j] - co0[u], no0[u]) < -0.0005:          # behind k's surface at rest
                        out = float(np.dot(co1[j] - co1[u], no1[u]))
                        if out > 0.001 and (best is None or out > best[1]):
                            best = (k, out)
                if best:
                    entry = poke.setdefault("%s through %s (%s)" % (names[mat[j]], names[best[0]], label), [0, 0.0])
                    entry[0] += 1
                    entry[1] = max(entry[1], best[1] * 100.0)
    report["pose_test"] = per_material
    report["poke_through"] = {k: {"verts": v[0], "max_cm": round(v[1], 2)} for k, v in poke.items()}

# -- 3. close-ups (before the physics is built) -------------------------------------------------------------
if swing and args.renders:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 24
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.55, 0.55, 0.58, 1)
    scene.world = world
    light = bpy.data.lights.new("Key", "SUN")
    light.energy = 2.0
    lamp = bpy.data.objects.new("Key", light)
    scene.collection.objects.link(lamp)
    lamp.rotation_euler = [math.radians(a) for a in (50, 0, -30)]
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 0.36
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x = scene.render.resolution_y = 420
    centre = sum((arm.matrix_world @ pb.head for pb in swing), Vector()) / len(swing) + Vector((0, -0.04, -0.02))
    for label, a, direction in (("rest_side", 0.0, (1, -0.35, 0)), ("rest_front", 0.0, (0, -1, 0)),
                                ("down_side", angle, (1, -0.35, 0)), ("up_side", -angle, (1, -0.35, 0))):
        turn(a)
        cam.location = centre + Vector(direction) * 10.0
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(args.out, "%s_%s.png" % (name, label))
        bpy.ops.render.render(write_still=True)
    turn(0.0)

# -- 2. hop test --------------------------------------------------------------------------------------------
if swing:
    rig.build()
    mmd_scene.mmd_like(scene)
    centre_bone = next(pb for pb in arm.pose.bones if pb.mmd_bone.name_j == "センター" or pb.name == "センター")
    to_local = centre_bone.bone.matrix_local.to_3x3().inverted()
    STAND, HOPS, PERIOD, DIP, SETTLE = 30, 4, 14, 0.05, 60
    last = STAND + HOPS * PERIOD + SETTLE
    for f in range(1, last + 1):
        t = f - STAND - 1
        z = -DIP * abs(math.sin(math.pi * t / PERIOD)) if 0 <= t < HOPS * PERIOD else 0.0
        centre_bone.location = to_local @ Vector((0.0, 0.0, z))
        centre_bone.keyframe_insert("location", frame=f)
    scene.frame_start, scene.frame_end = 1, last
    trace = {pb.name: [] for pb in swing}
    for _f in mmd_scene.run_physics(scene):
        for pb in swing:
            trace[pb.name].append(mmd_scene.swing_deg(pb))
    hop = {}
    for bone, a in trace.items():
        bounce, after = a[STAND:STAND + HOPS * PERIOD], a[STAND + HOPS * PERIOD:]
        calm = next((i for i in range(len(after)) if max(after[i:]) - min(after[i:]) < 1.0), None)
        hop[bone] = {"standing_deg": round(a[STAND - 1], 1), "hop_min_deg": round(min(bounce), 1),
                     "hop_max_deg": round(max(bounce), 1), "after_stop_max_deg": round(max(after), 1),
                     "calm_after_frames": calm, "trace": [round(x, 1) for x in a]}
    report["hop_test"] = hop
with open(os.path.join(args.out, name + "_bust.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
short = {k: v for k, v in report.items() if k not in ("hop_test", "pose_test")}
short["hop_test"] = {k: {kk: vv for kk, vv in v.items() if kk != "trace"} for k, v in report.get("hop_test", {}).items()}
print("BUST_CHECK=" + json.dumps(short, ensure_ascii=False), flush=True)
