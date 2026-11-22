"""Sections the game simulates as cloth hang from where they attach (2026-11-22, Laniakea's arm streamers).

    blender -b <package.blend> --factory-startup --python hang_cloth.py -- --slots 4[,7] [--min-length 25]

A section with a clothing asset (CorrespondClothAssetIndex >= 0, slots.json "cloth") is drawn by NvCloth in the
game; the mesh keeps its BIND pose, and Laniakea's streamers there trail a metre straight back from the forearms -
in the game they fall.  Without a simulation:
  * the slots' faces are split into connected pieces, the pieces grouped by the bone that carries most of their
    weight (a streamer and the loose ornaments at its end ride the same forearm twist bone);
  * a group's attachment point is its vertex nearest that bone's segment; a group reaching less than --min-length
    cm from it (the small flaps on the upper arms) stays as it is;
  * the rest is turned rigidly about the attachment point so that it points straight down (world -Z);
  * and gets a bone chain down its length (Streamer_<L/R>_01.., 3-8 links of ~15 cm, under the bone it hangs from),
    its vertices weighted to the two nearest links (the top 4 cm keep their weights on the forearm): the PMX
    export's mmd_cloth_physics makes such a chain a ribbon - without it the piece rode the forearm rigidly and stood
    up over the head whenever the arm was raised (Laniakea's dance preview).
Edits the .blend in place.  Prints SB_CLOTH={json}."""
import argparse
import json
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--slots", required=True)
ap.add_argument("--object", default="Eve_Body_Mesh_01")
ap.add_argument("--min-length", type=float, default=25.0)
args = ap.parse_args(argv)
slots = {int(x) for x in args.slots.split(",") if x}

ob = bpy.data.objects[args.object]
arm = ob.find_armature()
mw, mwi = ob.matrix_world, ob.matrix_world.inverted()
names = {g.index: g.name for g in ob.vertex_groups}
bm = bmesh.new()
bm.from_mesh(ob.data)
bm.verts.ensure_lookup_table()
faces = [f for f in bm.faces if f.material_index in slots]

# connected pieces (through shared vertices of these faces)
parent = {}


def find(x):
    while parent.setdefault(x, x) != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


for f in faces:
    vs = [v.index for v in f.verts]
    for v in vs[1:]:
        ra, rb = find(vs[0]), find(v)
        if ra != rb:
            parent[ra] = rb
pieces = {}
for f in faces:
    for v in f.verts:
        pieces.setdefault(find(v.index), set()).add(v.index)


def dominant_bone(vids):
    w = {}
    for i in vids:
        for g in ob.data.vertices[i].groups:
            n = names.get(g.group)
            if n and n in arm.data.bones:
                w[n] = w.get(n, 0.0) + g.weight
    return max(w, key=w.get) if w else None


groups = {}
for vids in pieces.values():
    groups.setdefault(dominant_bone(vids), set()).update(vids)

report = {"slots": sorted(slots), "faces": len(faces), "pieces": len(pieces), "groups": []}
for bone_name, vids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    rec = {"bone": bone_name, "vertices": len(vids)}
    report["groups"].append(rec)
    if bone_name is None:
        rec["skipped"] = "no weights"
        continue
    b = arm.data.bones[bone_name]
    h, t = arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local
    seg = t - h
    pos = {i: mw @ bm.verts[i].co for i in vids}

    def dist_to_bone(p):
        x = max(0.0, min(1.0, (p - h).dot(seg) / max(seg.length_squared, 1e-9)))
        return (p - (h + seg * x)).length
    anchor_i = min(vids, key=lambda i: dist_to_bone(pos[i]))
    a = pos[anchor_i]
    far_i = max(vids, key=lambda i: (pos[i] - a).length)
    length = (pos[far_i] - a).length
    rec["length_cm"] = round(length, 1)
    if length < args.min_length:
        rec["skipped"] = "shorter than %.0f cm" % args.min_length
        continue
    d = (pos[far_i] - a).normalized()
    q = d.rotation_difference(Vector((0.0, 0.0, -1.0)))
    for i in vids:
        bm.verts[i].co = mwi @ (a + q @ (pos[i] - a))
    rec["turned_deg"] = round(q.angle * 57.2958, 1)
    rec["anchor"] = [round(x, 1) for x in a]
    rec["_vids"], rec["_a"] = vids, a
bm.to_mesh(ob.data)
ob.data.update()

# a bone chain down each turned piece, so the PMX export's mmd_cloth_physics makes it hang in MMD too ("streamer" in
# the name = its ribbon preset); without it the piece rides the forearm rigidly and stands up when the arm is raised
groups_to_chain = [r for r in report["groups"] if "_vids" in r]
if groups_to_chain:
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    inv = arm.matrix_world.inverted()
    for k, rec in enumerate(groups_to_chain):
        side = "L" if "-L-" in rec["bone"] or rec["bone"].endswith("_L") else "R" if "-R-" in rec["bone"] or \
            rec["bone"].endswith("_R") else str(k + 1)
        n = max(3, min(8, round(rec["length_cm"] / 15.0)))
        names, prev = [], eb[rec["bone"]]
        for j in range(n):
            b = eb.new("Streamer_%s_%02d" % (side, j + 1))
            b.head = inv @ (rec["_a"] + Vector((0.0, 0.0, -rec["length_cm"] * j / n)))
            b.tail = inv @ (rec["_a"] + Vector((0.0, 0.0, -rec["length_cm"] * (j + 1) / n)))
            b.parent = prev
            b.use_connect = j > 0
            names.append(b.name)
            prev = b
        rec["chain"] = names
    bpy.ops.object.mode_set(mode="OBJECT")
    keep_top = 4.0                                     # cm: the top stays on the forearm as it was
    for rec in groups_to_chain:
        names, n = rec["chain"], len(rec["chain"])
        vgs = [ob.vertex_groups.get(nm) or ob.vertex_groups.new(name=nm) for nm in names]
        moved = 0
        for i in rec["_vids"]:
            p = mw @ ob.data.vertices[i].co
            along = rec["_a"].z - p.z
            if along < keep_top:
                continue
            for g in list(ob.data.vertices[i].groups):
                ob.vertex_groups[g.group].remove([i])
            s = max(0.0, min(n - 1e-6, along / rec["length_cm"] * n))
            j, f = int(s), s - int(s)
            vgs[j].add([i], 1.0 - f if j + 1 < n else 1.0, "REPLACE")
            if j + 1 < n and f > 0.0:
                vgs[j + 1].add([i], f, "REPLACE")
            moved += 1
        rec["chain_bones"], rec["reweighted"] = n, moved
for rec in report["groups"]:
    rec.pop("_vids", None)
    a = rec.pop("_a", None)
bpy.ops.wm.save_mainfile()
print("SB_CLOTH=" + json.dumps(report, ensure_ascii=False))
