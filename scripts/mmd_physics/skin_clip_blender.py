"""How deep a skirt goes into the LEG SURFACE you see during a dance - the real skin (or boots / greaves), not the
inset body colliders clip_test_blender.py measures against.

Import the PMX, play the VMD with MMD-like physics (baked, as clip_test_blender.py), then per frame every skirt vertex
(its strongest bone matches --bones) is tested against the evaluated leg surface - the faces of the --surface
materials whose vertices' strongest bone is a leg bone (MMD names, and ROE's ThighTwist_LT / LCalfTwist twist bones,
which carry half of a08's thigh skin and the greaves): inside = behind the nearest face by more than 3 mm and within
8 cm of it.  Vertices already inside in the rest pose (modelled that way) are left out.

    blender -b --factory-startup --python skin_clip_blender.py -- <pmx> <vmd> <out.json>
        [--surface skin] [--bones "skirt|skir_chain"] [--frames a-b] [--leave "Skirt_L_00,Skirt_R_00"]

--surface: material name parts, comma separated (default "skin"; a08's greaves: body1_01; "*" = every material, i.e.
whatever the legs wear).  --bones "auto": every bone with a dynamic rigid body, breasts and hair (under 頭 / 首) left
out - for batches over models whose cloth bones are named anything.  --leave: bones whose
vertices are counted apart (a08's hip plates: the cloth's top corners follow them into the groin crease whenever the
legs close - the pose and the weights, not the physics).  Prints SUMMARY: mean / 95th percentile / max per frame,
the same without the --leave bones, the deepest point, per (skirt bone > leg bone) pair the mean count and the
deepest, the worst frames; the JSON file also has every frame.  Give Blender absolute paths.
ROE Inase a08 (2026-10-18), gesture dance, skin without the hip plates: archived 705 -> fixed 30 per frame.
"""
import argparse
import json
import os
import re
import sys
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mmd_like import mmd_like_physics  # noqa: E402

SCALE, MARGIN = 0.08, 30
BUST = r"^(?:[a-z0-9]+[ _])?(?:breast|chest_[lr])|bust|胸|乳|oppai|opai_[lr]|xtra01(?:opp)?(?:02)?$"
LEG = re.compile(r"^(?:[左右](?:足|ひざ|足首|つま先|足D|ひざD|足首D|足先EX)|ThighTwist_[LR]T|[LR]CalfTwist1?)$")
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("vmd")
ap.add_argument("out")
ap.add_argument("--surface", default="skin")
ap.add_argument("--bones", default=r"skirt|skir_chain")
ap.add_argument("--frames", default="", help="a-b in scene frames (default: the whole dance after the lead-in)")
ap.add_argument("--leave", default="", help="bones counted apart, comma separated")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
t0 = time.time()
leave = {b for b in args.leave.split(",") if b}
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
print("MMD-like joints:", mmd_like_physics(scene, SCALE, 98.0, None))
world = scene.rigidbody_world
world.enabled = True
world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
    bpy.ops.ptcache.free_bake()
    bpy.ops.ptcache.bake(bake=True)
print("baked in %.0f s" % (time.time() - t0), flush=True)

if args.bones == "auto":
    bust = re.compile(BUST, re.I)
    cloth = set()
    for o in rig.rigidBodies():
        pb = arm.pose.bones.get(o.mmd_rigid.bone) if o.mmd_rigid.bone else None
        if str(o.mmd_rigid.type) == "0" or pb is None:
            continue
        name = pb.mmd_bone.name_j or pb.name
        up = pb.parent
        while up is not None and (up.mmd_bone.name_j or up.name) not in ("頭", "首"):
            up = up.parent
        if up is None and not bust.search(name) and not bust.search(o.mmd_rigid.name_j or ""):
            cloth.add(name)
    pat = re.compile("^(?:%s)$" % "|".join(re.escape(n) for n in sorted(cloth)) if cloth else r"(?!)")
    print("cloth bones (auto): %d" % len(cloth), flush=True)
else:
    pat = re.compile(args.bones, re.I)
parts = [p.strip().lower() for p in args.surface.split(",") if p.strip()]
every_material = "*" in parts
surface_obj, tris, tri_bone, skirt = None, [], [], []
for o in rig.meshes():
    names = {}
    for vg in o.vertex_groups:
        pb = arm.pose.bones.get(vg.name)
        if pb is not None:                         # mmd_tools adds mmd_edge_scale / mmd_vertex_order groups too
            names[vg.index] = pb.mmd_bone.name_j or pb.name
    strongest = []
    for v in o.data.vertices:
        gs = [g for g in v.groups if g.group in names]
        strongest.append(names[max(gs, key=lambda g: g.weight).group] if gs else "")
    strongest = np.array(strongest, dtype=object)
    mats = [s.material.name.lower() if s.material else "" for s in o.material_slots]
    mine, mine_bone = [], []
    for p in o.data.polygons:
        if (every_material or any(k in mats[p.material_index] for k in parts)) \
                and all(LEG.match(strongest[i]) for i in p.vertices):
            vs = list(p.vertices)
            for k in range(1, len(vs) - 1):
                mine.append((vs[0], vs[k], vs[k + 1]))
                mine_bone.append(strongest[vs[0]])
    if len(mine) > len(tris):
        surface_obj, tris, tri_bone = o, mine, mine_bone
    idx = [i for i, n in enumerate(strongest) if n and pat.search(n)]
    if idx:
        skirt.append((o, np.array(idx), strongest[idx]))
if surface_obj is None:
    raise SystemExit("no leg faces in materials matching %r" % args.surface)
print("leg surface: %s, %d triangles; skirt vertices: %s" % (surface_obj.name, len(tris),
      {o.name: len(i) for o, i, _ in skirt}), flush=True)


def coords(o, depsgraph):
    ev = o.evaluated_get(depsgraph)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    w = np.array(o.matrix_world)
    return co.reshape(-1, 3) @ w[:3, :3].T + w[:3, 3]


def inside_now(depsgraph):
    tree = BVHTree.FromPolygons([Vector(p) for p in coords(surface_obj, depsgraph)], tris, all_triangles=True)
    out = []
    for o, idx, _lab in skirt:
        depth = np.zeros(len(idx))
        leg = np.array([""] * len(idx), dtype=object)
        for k, p in enumerate(coords(o, depsgraph)[idx]):
            hit = tree.find_nearest(Vector(p), 0.08)
            if hit[0] is None:
                continue
            d = (Vector(p) - hit[0]).dot(hit[1])
            if d < -0.003:
                depth[k], leg[k] = -d, tri_bone[hit[2]]
        out.append((depth, leg))
    return out


arm.data.pose_position = "REST"
bpy.context.view_layer.update()
rest_mask = [d > 0 for d, _l in inside_now(bpy.context.evaluated_depsgraph_get())]
arm.data.pose_position = "POSE"
print("inside at rest (modelled, left out):", sum(int(m.sum()) for m in rest_mask), flush=True)

a, b = scene.frame_start + MARGIN, scene.frame_end
if args.frames:
    a, b = (int(x) for x in args.frames.split("-"))
rows = []
for f in range(a, b + 1):
    scene.frame_set(f)
    total, kept, deep, pairs = 0, 0, 0.0, {}
    for (o, idx, lab), (depth, leg), rm in zip(skirt, inside_now(bpy.context.evaluated_depsgraph_get()), rest_mask):
        hit = (depth > 0) & ~rm
        total += int(hit.sum())
        for k in np.nonzero(hit)[0]:
            key = "%s>%s" % (lab[k], leg[k])
            c, dmax = pairs.get(key, (0, 0.0))
            pairs[key] = (c + 1, max(dmax, round(float(depth[k]) * 100, 2)))
            if lab[k] not in leave:
                kept += 1
                deep = max(deep, float(depth[k]))
    rows.append({"frame": f, "inside": total, "without_left": kept, "deepest_cm": round(deep * 100, 2), "pairs": pairs})
    if f % 60 == 0:
        print("frame %d: %d inside (%d without %s), deepest %.1f cm" % (f, total, kept, args.leave or "-", deep * 100),
              flush=True)
arr = np.array([r["inside"] for r in rows])
kep = np.array([r["without_left"] for r in rows])
keys = {k for r in rows for k in r["pairs"]}
summary = {"pmx": args.pmx, "vmd": args.vmd, "surface": args.surface, "frames": len(rows),
           "mean": round(float(arr.mean()), 2), "p95": round(float(np.percentile(arr, 95)), 1), "max": int(arr.max()),
           "without_left": {"bones": sorted(leave), "mean": round(float(kep.mean()), 2),
                            "p95": round(float(np.percentile(kep, 95)), 1), "max": int(kep.max()),
                            "deepest_cm": max(r["deepest_cm"] for r in rows)},
           "pairs_mean": dict(sorted(((k, round(float(np.mean([r["pairs"].get(k, (0, 0))[0] for r in rows])), 2))
                                      for k in keys), key=lambda kv: -kv[1])[:12]),
           "pairs_deepest_cm": dict(sorted(((k, max(r["pairs"].get(k, (0, 0))[1] for r in rows)) for k in keys),
                                           key=lambda kv: -kv[1])[:12]),
           "worst_frames": [r["frame"] for r in sorted(rows, key=lambda r: -r["without_left"])[:8]],
           "seconds": round(time.time() - t0)}
json.dump({"summary": summary, "rows": rows}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
