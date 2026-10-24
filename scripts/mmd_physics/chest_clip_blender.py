"""How often the fitted body pokes out through the outfit over the breasts during a dance (ROE _full PMX).

Import the PMX, play the VMD with MMD-like physics (baked, as skin_clip_blender.py), then pair every fitted-body vertex
that lies UNDER a cup at rest (its nearest cup point inside a cup triangle, behind it) with that point (triangle +
barycentric coordinates).  Per frame the same pairs are re-measured on the evaluated mesh: poking out = the body vertex
in front of its cup point along the cup's normal by more than 0.5 mm.  A cup = an outfit triangle whose three
vertices have >= 0.3 of their weight on a breast's bones (左胸 / 右胸 and every bone under them).

    blender -b --factory-startup --python chest_clip_blender.py -- <pmx> <vmd> <out.json>
        [--body pc_g01_nk_body] [--outfit "pc_g05_hd_body 1,pc_g05_hd_body 2"] [--frames a-b]
Prints SUMMARY: mean / p95 / max vertices out per frame, deepest mm, worst frames, per side, and the vertices (PMX
index) that poke out in the most frames.
"""
import argparse
import os
import json
import sys
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmd_like import mmd_like_physics  # noqa: E402

SCALE, MARGIN = 0.08, 30
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("vmd")
ap.add_argument("out")
ap.add_argument("--body", default="pc_g01_nk_body")
ap.add_argument("--outfit", default="pc_g05_hd_body 1,pc_g05_hd_body 2")
ap.add_argument("--frames", default="")
ap.add_argument("--skip", default="riband", help="bones under the breast starting with this are not cups")
ap.add_argument("--bones", default="", help="regex: measure the outfit on these bones instead of the cups (Inase a05's "
                                            "trousers: 足|ひざ|Thigh|Calf|下半身)")
ap.add_argument("--radius", type=float, default=2.0, help="cm: body vertices at most this far under the outfit at rest "
                                                          "are paired (default 2)")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
args.skip = args.skip.lower()
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
print("MMD-like joints:", mmd_like_physics(scene, SCALE, 98.0, None))
world = scene.rigidbody_world
world.enabled = True
world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
    bpy.ops.ptcache.free_bake()
    bpy.ops.ptcache.bake(bake=True)
print("baked in %.0f s" % (time.time() - t0), flush=True)

mesh = max((o for o in rig.meshes()), key=lambda o: len(o.data.vertices))
jname = {}
for vg in mesh.vertex_groups:
    pb = arm.pose.bones.get(vg.name)
    if pb is not None:
        jname[vg.index] = pb.mmd_bone.name_j or pb.name
# the breast trees by Japanese name
kids = {}
for pb in arm.pose.bones:
    if pb.parent is not None:
        kids.setdefault(pb.parent.name, []).append(pb.name)
tree = {}
if args.bones:
    import re
    pat = re.compile(args.bones)
    tree["cover"] = {pb.mmd_bone.name_j or pb.name for pb in arm.pose.bones if pat.search(pb.mmd_bone.name_j or pb.name)}
for pb in (() if args.bones else arm.pose.bones):
    side = pb.mmd_bone.name_j
    if side in ("左胸", "右胸"):
        stack, names = [pb.name], set()
        while stack:
            n = stack.pop()
            jn = arm.pose.bones[n].mmd_bone.name_j or n
            if jn.lower().startswith(args.skip):
                continue                      # a ribbon chain hung on the breast swings on its own: not a cup
            names.add(jn)
            stack.extend(kids.get(n, []))
        tree[side] = names
print("breast trees:", {k: sorted(v) for k, v in tree.items()}, flush=True)
mats = [s.material.name if s.material else "" for s in mesh.material_slots]
outfit_names = {n.strip() for n in args.outfit.split(",")}
body_slots = {k for k, n in enumerate(mats) if n == args.body}
outfit_slots = {k for k, n in enumerate(mats) if n in outfit_names}
if not body_slots or not outfit_slots:
    raise SystemExit("materials not found: body %s outfit %s in %s" % (args.body, outfit_names, mats))
share = {}
for side, names in tree.items():
    s = np.zeros(len(mesh.data.vertices))
    for v in mesh.data.vertices:
        s[v.index] = sum(g.weight for g in v.groups if jname.get(g.group) in names)
    share[side] = s
cup_tris, cup_side, cup_poly, body_verts = [], [], [], set()
for p in mesh.data.polygons:
    vs = list(p.vertices)
    if p.material_index in outfit_slots:
        for side in tree:
            if all(share[side][i] >= 0.3 for i in vs):
                for k in range(1, len(vs) - 1):
                    cup_tris.append((vs[0], vs[k], vs[k + 1]))
                    cup_side.append(side)
                    cup_poly.append(p.index)
    elif p.material_index in body_slots:
        body_verts.update(vs)
body_verts = np.array(sorted(body_verts))
print("cup triangles %d, fitted-body vertices %d" % (len(cup_tris), len(body_verts)), flush=True)


def coords(depsgraph):
    ev = mesh.evaluated_get(depsgraph)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    w = np.array(mesh.matrix_world)
    return co.reshape(-1, 3) @ w[:3, :3].T + w[:3, 3]


T = np.array(cup_tris)
arm.data.pose_position = "REST"
bpy.context.view_layer.update()
co = coords(bpy.context.evaluated_depsgraph_get())
arm.data.pose_position = "POSE"
# each cup triangle's winding -> outward sign from the model's own (PMX, custom split) normals of its polygon
me0 = mesh.data
me0.calc_normals_split()
poly_n = {}
for p in me0.polygons:
    if p.material_index in outfit_slots:
        poly_n[p.index] = np.mean([np.array(me0.loops[li].normal) for li in p.loop_indices], axis=0)
w3 = np.array(mesh.matrix_world)[:3, :3]
wn = np.cross(co[T[:, 1]] - co[T[:, 0]], co[T[:, 2]] - co[T[:, 0]])
orient = np.array([1.0 if wn[k] @ (w3 @ poly_n[cup_poly[k]]) >= 0 else -1.0 for k in range(len(T))])
print("cup triangles wound against their normals (flipped): %d of %d" % (int((orient < 0).sum()), len(T)), flush=True)
tree_bvh = BVHTree.FromPolygons([Vector(p) for p in co], cup_tris, all_triangles=True)
pairs = []                                   # (body vertex, tri, (u, v, w), rest gap)
for i in body_verts:
    hit = tree_bvh.find_nearest(Vector(co[i]), args.radius / 100.0)
    if hit[0] is None:
        continue
    a, b, c = (co[j] for j in T[hit[2]])
    n = np.cross(b - a, c - a) * orient[hit[2]]
    n /= np.linalg.norm(n)
    p = np.array(hit[0])
    # barycentric of the nearest point
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    bv = (d11 * d20 - d01 * d21) / den
    bw = (d00 * d21 - d01 * d20) / den
    bu = 1.0 - bv - bw
    gap = float((co[i] - p) @ n)
    if gap >= 0:
        continue                              # in front of the cup at rest: modelled so / other side
    if -gap < 0.7 * float(np.linalg.norm(co[i] - p)):
        continue                              # beside the cup (the offset runs along it), not under it
    bu, bv, bw = max(bu, 0.0), max(bv, 0.0), max(bw, 0.0)
    s = bu + bv + bw
    bu, bv, bw = bu / s, bv / s, bw / s
    pairs.append((i, hit[2], (bu, bv, bw), gap))
pi = np.array([p[0] for p in pairs])
pt = T[np.array([p[1] for p in pairs])]
po = orient[np.array([p[1] for p in pairs])]
pw = np.array([p[2] for p in pairs])
pside = np.array([cup_side[p[1]] for p in pairs])
print("pairs (body vertex under a cup at rest): %d, rest gap mean %.1f mm" % (
    len(pairs), -1000 * np.mean([p[3] for p in pairs])), flush=True)

a, b = scene.frame_start + MARGIN, scene.frame_end
if args.frames:
    a, b = (int(x) + scene.frame_start + MARGIN for x in args.frames.split("-"))
rows = []
times_out, deepest = np.zeros(len(pairs), int), np.full(len(pairs), -1.0)
for f in range(a, b + 1):
    scene.frame_set(f)
    co = coords(bpy.context.evaluated_depsgraph_get())
    A, B, C = co[pt[:, 0]], co[pt[:, 1]], co[pt[:, 2]]
    n = np.cross(B - A, C - A) * po[:, None]
    n /= np.linalg.norm(n, axis=1)[:, None]
    P = A * pw[:, :1] + B * pw[:, 1:2] + C * pw[:, 2:3]
    d = ((co[pi] - P) * n).sum(1)
    out = d > 0.0005
    times_out += out
    deepest = np.maximum(deepest, d)
    rows.append({"frame": f - scene.frame_start - MARGIN, "out": int(out.sum()),
                 "deepest_mm": round(float(d.max()) * 1000, 1),
                 "by_side": {s: int((out & (pside == s)).sum()) for s in tree}})
# the vertices that poke out most often (mesh index = PMX vertex index: mmd_tools keeps the order)
worst = [{"vertex": int(pi[k]), "frames_out": int(times_out[k]), "deepest_mm": round(float(deepest[k]) * 1000, 1),
          "rest_gap_mm": round(-1000 * pairs[k][3], 1), "side": str(pside[k])}
         for k in np.argsort(-times_out)[:12] if times_out[k] > 0]
arr = np.array([r["out"] for r in rows])
summary = {"pmx": args.pmx, "vmd": args.vmd, "pairs": len(pairs), "frames": len(rows),
           "mean": round(float(arr.mean()), 1), "p95": round(float(np.percentile(arr, 95)), 1), "max": int(arr.max()),
           "deepest_mm": max(r["deepest_mm"] for r in rows),
           "by_side_mean": {s: round(float(np.mean([r["by_side"][s] for r in rows])), 1) for s in tree},
           "worst_frames": [r["frame"] for r in sorted(rows, key=lambda r: -r["out"])[:8]],
           "worst_vertices": worst,
           "seconds": round(time.time() - t0)}
json.dump({"summary": summary, "rows": rows}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
