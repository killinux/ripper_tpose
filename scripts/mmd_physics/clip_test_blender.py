"""How much cloth / hair goes into the body during a dance: import a PMX, play a VMD with MMD-like physics (baked), and
per frame count the vertices that physics moves (their strongest bone carries a dynamic rigid body, breasts left out)
lying more than 5 mm inside the BODY.  The body volume is the body colliders of a reference PMX - the output of
cloth_collision_pmx.py, capsules and balls fitted inside the nude skin - posed with this model's bones, so the model
before and after the fix is measured with the same yardstick (pass the fixed PMX as the reference for both).

    blender -b --factory-startup --python clip_test_blender.py -- <pmx> <vmd> <reference pmx> <out.json> [step] [mmd|blender]

Prints a line per 60 frames and SUMMARY <json>: frames, mean / 95th percentile / max vertices inside, frames with any,
the deepest point (cm), the mean per garment (the bone name without its _01_l ending) and the worst frames; the JSON
file also has every frame.  Give Blender absolute paths.  Vindictus Fiona, gesture dance: 37.7 -> 5.4 per frame.
"""
import json
import os
import re
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cloth_collision_pmx as cc  # noqa: E402
from mmd_like import mmd_like_physics  # noqa: E402

SCALE, MARGIN = 0.08, 30            # import scale; lead-in frames before VMD frame 0 (as render_pmx_dance.py)
argv = sys.argv[sys.argv.index("--") + 1:]
pmx_path, vmd_path, ref_path, out_path = argv[:4]
step = int(argv[4]) if len(argv) > 4 else 1
physics = argv[5] if len(argv) > 5 else "mmd"
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"},
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
bpy.ops.mmd_tools.import_vmd(filepath=vmd_path, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                             update_scene_settings=True)
scene = bpy.context.scene
if physics == "mmd":
    print("MMD-like joints:", mmd_like_physics(scene, SCALE, 98.0, None))
world = scene.rigidbody_world
world.enabled = True
world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
    bpy.ops.ptcache.free_bake()
    bpy.ops.ptcache.bake(bake=True)
print("baked %d frames in %.0f s" % (scene.frame_end - scene.frame_start + 1, time.time() - t0), flush=True)

# the body volume: the reference's capsules / balls in Blender rest space (PMX -> Blender swaps Y and Z), per bone
pmx = cc.load_pmx_module(cc.find_pmx_module())
ref = pmx.load(ref_path)
P = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], float)
pbs = {(pb.mmd_bone.name_j or pb.name): pb for pb in arm.pose.bones}
vols = []
for r in ref.rigids:
    bn = ref.bones[r.bone].name if r.bone is not None and r.bone >= 0 else ""
    if r.mode != 0 or bn not in cc.CLASS_OF or bn not in pbs:
        continue
    s = cc.Shape.of(r)
    if s.kind == 1:
        continue
    a, b = s.seg
    vols.append((bn, P @ a * SCALE, P @ b * SCALE, s.r * SCALE))
print("body volume: %d capsules / balls" % len(vols))

# vertices moved by physics, labelled by garment
src = pmx.load(pmx_path)
dyn_bones = {src.bones[r.bone].name for r in src.rigids if r.mode in (1, 2) and r.bone is not None and r.bone >= 0}
bust = re.compile(cc.DEFAULTS["bust"], re.I)


def garment(name):
    return re.sub(r"_[a-z]?_?\d+(_[lr])?$", "", name)


sel = []
for o in rig.meshes():
    names = {}
    for vg in o.vertex_groups:
        pb = arm.pose.bones.get(vg.name)
        if pb is not None:                         # mmd_tools adds mmd_edge_scale / mmd_vertex_order groups too
            names[vg.index] = pb.mmd_bone.name_j or pb.name
    idx, lab = [], []
    for v in o.data.vertices:
        gs = [g for g in v.groups if g.group in names]
        if not gs:
            continue
        n = names[max(gs, key=lambda x: x.weight).group]
        if n in dyn_bones and not bust.search(n):
            idx.append(v.index)
            lab.append(garment(n))
    if idx:
        sel.append((o, np.array(idx), np.array(lab)))
print("physics-driven vertices:", {o.name: len(i) for o, i, _l in sel}, flush=True)


def seg_dist(p, a, b):
    ab = b - a
    L = ab @ ab
    t = np.clip(((p - a) @ ab) / L, 0, 1) if L > 1e-12 else np.zeros(len(p))
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


rows = []
for f in range(scene.frame_start + MARGIN, scene.frame_end + 1, step):
    scene.frame_set(f)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mw = arm.matrix_world
    posed = []
    for bn, a, b, r in vols:
        pb = pbs[bn]
        M = np.array(mw @ pb.matrix @ pb.bone.matrix_local.inverted() @ mw.inverted())
        posed.append((M[:3, :3] @ a + M[:3, 3], M[:3, :3] @ b + M[:3, 3], r))
    counts, deep, total = {}, 0.0, 0
    for o, idx, lab in sel:
        ev = o.evaluated_get(depsgraph)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        world_m = np.array(o.matrix_world)
        co = co.reshape(-1, 3)[idx] @ world_m[:3, :3].T + world_m[:3, 3]
        inside = np.zeros(len(co))
        for A, B, r in posed:
            inside = np.maximum(inside, r - seg_dist(co, A, B))
        hit = inside > 0.005                       # more than 5 mm inside the body volume
        total += int(hit.sum())
        deep = max(deep, float(inside.max()))
        for g in np.unique(lab[hit]):
            counts[g] = counts.get(g, 0) + int((hit & (lab == g)).sum())
    rows.append({"frame": f, "inside": total, "deepest_m": round(deep, 4), "by": counts})
    if f % 60 == 0:
        print("frame %d: %d vertices inside (deepest %.1f cm) %s" % (f, total, deep * 100, counts), flush=True)
arr = np.array([r["inside"] for r in rows])
garments = sorted({g for r in rows for g in r["by"]})
summary = {"pmx": pmx_path, "vmd": vmd_path, "reference": ref_path, "frames": len(rows),
           "mean_inside": round(float(arr.mean()), 2), "p95_inside": float(np.percentile(arr, 95)),
           "max_inside": int(arr.max()), "frames_with_clipping": int((arr > 0).sum()),
           "deepest_cm": round(100 * max(r["deepest_m"] for r in rows), 1),
           "by_garment_mean": {g: round(float(np.mean([r["by"].get(g, 0) for r in rows])), 2) for g in garments},
           "worst_frames": [r["frame"] for r in sorted(rows, key=lambda r: -r["inside"])[:8]],
           "seconds": round(time.time() - t0)}
json.dump({"summary": summary, "rows": rows}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SUMMARY", json.dumps(summary, ensure_ascii=False))
