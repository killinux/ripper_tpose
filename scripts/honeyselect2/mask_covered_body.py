# -*- coding: utf-8 -*-
"""Delete the body faces that clothes cover - what the games' body masks do - for clothes that were not made for this
body (Honey Select 1 clothes on an HS2 character: the HS2 body pokes through a tight suit at the belly and thighs).

    blender -b <x.blend> --python mask_covered_body.py -- --body o_body_cf --clothes-regex "^(skin|O_top_a|N_bot_d|body)"
            [--reach 0.03] [--save]

A body vertex is covered when a ray from it along its normal, outward or inward, meets the clothes within --reach
(metres): outward = the clothes lie over the skin, inward = the skin pokes out through them.  Faces whose three vertices
are covered are deleted from the body mesh (vertex groups and the rest stay).  Prints MASK_BODY={json}.
"""
import argparse
import json
import re
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--body", default="o_body_cf", help="name (or prefix) of the body mesh object")
ap.add_argument("--clothes-regex", required=True, help="regex of the clothes objects that cover the body")
ap.add_argument("--reach", type=float, default=0.03)
ap.add_argument("--save", action="store_true")
ap.add_argument("--preview", default="", help="<prefix>: render <prefix>_preview.png (front) and <prefix>_side.png")
args = ap.parse_args(argv)

dg = bpy.context.evaluated_depsgraph_get()
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(args.body))
rx = re.compile(args.clothes_regex)
clothes = [o for o in bpy.data.objects if o.type == "MESH" and o is not body and rx.search(o.name)]
verts, polys = [], []
for o in clothes:
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    base = len(verts)
    verts += [o.matrix_world @ v.co for v in me.vertices]
    polys += [[base + i for i in p.vertices] for p in me.polygons]
    ev.to_mesh_clear()
tree = BVHTree.FromPolygons(verts, polys)

evb = body.evaluated_get(dg)
bme = evb.to_mesh()
mw = body.matrix_world
nm = mw.to_3x3().inverted().transposed()
covered = []
for v in bme.vertices:
    p = mw @ v.co
    n = (nm @ v.normal).normalized()
    hit = False
    for d in (n, -n):
        loc, _nrm, _i, dist = tree.ray_cast(p - d * 0.002, d, args.reach)
        if loc is not None:
            hit = True
            break
    covered.append(hit)
evb.to_mesh_clear()

bm = bmesh.new()
bm.from_mesh(body.data)
bm.verts.ensure_lookup_table()
gone = [f for f in bm.faces if all(covered[v.index] for v in f.verts)]
n_faces = len(bm.faces)
bmesh.ops.delete(bm, geom=gone, context="FACES_ONLY")
bm.to_mesh(body.data)
bm.free()
body.data.update()
report = {"body": body.name, "clothes": [o.name for o in clothes], "faces": n_faces, "deleted": len(gone),
          "covered_vertices": int(sum(covered))}
if args.save:
    bpy.ops.wm.save_mainfile()

if args.preview:
    import math
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = "Filmic"
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("MaskW")
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
    scene.world = world
    for name, rot, energy in (("K", (50, 0, -30), 3.0), ("F", (60, 0, 40), 1.2), ("R", (70, 0, 170), 1.5)):
        li = bpy.data.lights.new("mask_" + name, "SUN")
        li.energy = energy
        lo = bpy.data.objects.new("mask_" + name, li)
        scene.collection.objects.link(lo)
        lo.rotation_euler = [math.radians(a) for a in rot]
    vis = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    dg = bpy.context.evaluated_depsgraph_get()
    pts = [o.evaluated_get(dg).matrix_world @ Vector(c) for o in vis for c in o.evaluated_get(dg).bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre, height = (mn + mx) / 2, (mx - mn).z
    cd = bpy.data.cameras.new("MaskCam")
    cd.type, cd.ortho_scale = "ORTHO", max(height, mx.x - mn.x) * 1.05
    cam = bpy.data.objects.new("MaskCam", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for tag, d, size in (("_preview.png", Vector((0, -1, 0)), (900, 1400)), ("_side.png", Vector((1, 0, 0)), (900, 1400))):
        cam.location = centre + d * height * 4
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.filepath = args.preview + tag
        bpy.ops.render.render(write_still=True)
print("MASK_BODY=" + json.dumps(report, ensure_ascii=False), flush=True)
