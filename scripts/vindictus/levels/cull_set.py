"""Video version of a level .blend made by build_level.py: only what disperse_pair.py's camera can see over the whole
clip (orbit + push-in) plus a ring of shadow casters around her, and the textures from a downscaled copy.
EEVEE re-syncs every object each frame and redraws the sun's shadow cascades every sample - 3367 objects, the grass
and 4K / 8K maps made a frame 50-120 s; this keeps it near the plain-background cost.

  blender -b <level.blend> --factory-startup --python cull_set.py -- --spot X,Y,Z --out <video.blend>
      [--turn 90:110] [--height 1.8] [--dist 4.4] [--push 0.55] [--ring 35] [--margin 8] [--lo <assets_lo dir>]

Spot / out in Blender units (m); --turn = the camera's turn range in degrees (disperse: turn +- orbit)."""
import argparse
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--spot", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--turn", default="90:110")
ap.add_argument("--height", type=float, default=1.8)
ap.add_argument("--dist", type=float, default=4.4)
ap.add_argument("--push", type=float, default=0.55)
ap.add_argument("--lens", type=float, default=50.0)
ap.add_argument("--aspect", type=float, default=9 / 16)
ap.add_argument("--ring", type=float, default=35.0)
ap.add_argument("--grass-ring", type=float, default=8.0)
ap.add_argument("--margin", type=float, default=8.0)
ap.add_argument("--lo", default="")
args = ap.parse_args(argv)
spot = Vector(tuple(float(v) for v in args.spot.split(",")))
h = args.height

# ---- the cameras of the clip (disperse_pair.py: pivot at her feet turned by turn +- orbit, push-in at the end)
t0, t1 = (math.radians(float(v)) for v in args.turn.split(":"))
cams = []
for k in range(7):
    t = t0 + (t1 - t0) * k / 6
    for dist, zc, za in ((args.dist, 0.53 * h, 0.5 * h), (args.dist * args.push, 0.72 * h, 0.70 * h)):
        cam = spot + Matrix.Rotation(t, 3, "Z") @ Vector((0.0, -dist, zc))
        fwd = (spot + Vector((0.0, 0.0, za)) - cam).normalized()
        right = fwd.cross(Vector((0.0, 0.0, 1.0))).normalized()
        up = right.cross(fwd)
        cams.append((cam, fwd, right, up))
vh = math.atan(12.0 / args.lens)                                 # vertical sensor 24 mm
hh = math.atan(math.tan(vh) * args.aspect)
tv, th = math.tan(vh + math.radians(args.margin)), math.tan(hh + math.radians(args.margin))
C = np.array([c[0] for c in cams])
F, R, U = (np.array([c[i] for c in cams]) for i in (1, 2, 3))


def keep(centers, radii, ring):
    """bool per sphere: inside a camera frustum (+ margin) or within `ring` m of her"""
    centers = np.asarray(centers, dtype=np.float64).reshape(-1, 3)
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    out = np.linalg.norm(centers - np.array(spot), axis=1) - radii <= ring
    for i in range(len(C)):
        v = centers - C[i]
        depth = v @ F[i]
        ok = (depth >= -radii) & (depth <= 5000.0 + radii)
        ok &= np.abs(v @ R[i]) <= np.maximum(depth, 0.0) * th + radii * 1.2
        ok &= np.abs(v @ U[i]) <= np.maximum(depth, 0.0) * tv + radii * 1.2
        out |= ok
    return out


def world_sphere(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    c = sum(pts, Vector()) / 8.0
    return c, max((p - c).length for p in pts)


def local_radius(obj):
    pts = [Vector(c) for c in obj.bound_box]
    return max(p.length for p in pts)                           # around the origin = the instance pivot


sources = set(bpy.data.collections["VDF_sources"].objects) if "VDF_sources" in bpy.data.collections else set()
removed = kept = 0
pts_before = pts_after = 0
used_sources = set()
for obj in list(bpy.data.objects):
    if obj in sources or obj.type != "MESH":
        continue
    mod = next((m for m in obj.modifiers if m.type == "NODES"), None)
    if obj.name == "VDF_Grass":
        continue
    if mod and mod.node_group and mod.node_group.name.startswith("VDF_Instancer"):
        src = mod[mod.node_group.inputs["Source"].identifier]
        me = obj.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        scl = np.empty(n * 3, dtype=np.float32)
        me.attributes["scl"].data.foreach_get("vector", scl)
        r = local_radius(src) * np.abs(scl.reshape(-1, 3)).max(1)
        k = keep(co.reshape(-1, 3), r, args.ring)
        pts_before += n
        if not k.any():
            bpy.data.objects.remove(obj)
            removed += 1
            continue
        if not k.all():
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.verts.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(~k)[0]], context="VERTS")
            bm.to_mesh(me)
            bm.free()
        pts_after += int(k.sum())
        used_sources.add(src)
        kept += 1
        continue
    if obj.name.split(".")[0] == "Landscape":                    # one mesh for the whole terrain: always kept
        kept += 1
        continue
    c, r = world_sphere(obj)
    if keep([tuple(c)], [r], args.ring)[0]:
        kept += 1
        for s in sources:
            if s.data == obj.data:
                used_sources.add(s)
                break
    else:
        bpy.data.objects.remove(obj)
        removed += 1
print("[cull] objects kept %d, removed %d; instances %d -> %d" % (kept, removed, pts_before, pts_after), flush=True)

# ---- the grass carrier: faces in view or near her
grass = bpy.data.objects.get("VDF_Grass")
if grass:
    me = grass.data
    bm = bmesh.new()
    bm.from_mesh(me)
    faces = list(bm.faces)
    cen = np.array([tuple(f.calc_center_median()) for f in faces])
    k = keep(cen, np.full(len(faces), 1.5), args.grass_ring)
    bmesh.ops.delete(bm, geom=[f for f, ok in zip(faces, k) if not ok], context="FACES")
    bm.to_mesh(me)
    bm.free()
    print("[cull] grass carrier faces %d -> %d" % (len(faces), int(k.sum())), flush=True)
    for node in grass.modifiers[0].node_group.nodes:
        if node.type == "OBJECT_INFO" and node.inputs["Object"].default_value:
            used_sources.add(node.inputs["Object"].default_value)

# ---- sources nothing uses any more (no linked copy, no instancer, no grass)
linked = {o.data for o in bpy.data.objects if o not in sources}
dropped = 0
for s in list(sources):
    if s not in used_sources and s.data not in linked:
        bpy.data.objects.remove(s)
        dropped += 1
print("[cull] sources dropped %d, kept %d" % (dropped, len(sources) - dropped), flush=True)
bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

# ---- downscaled textures
if args.lo:
    lo = os.path.abspath(args.lo)
    swapped = 0
    for img in bpy.data.images:
        if img.packed_file or img.source != "FILE":
            continue
        p = os.path.abspath(bpy.path.abspath(img.filepath))
        low = p.replace(os.sep, "/").lower()
        i = low.find("/assets/")
        if i < 0:
            continue
        cand = os.path.join(lo, p[i + len("/assets/"):])
        if os.path.exists(cand):
            img.filepath = cand
            swapped += 1
    print("[cull] textures swapped to the downscaled copies: %d of %d" % (swapped, len(bpy.data.images)), flush=True)

# ---- every image path ABSOLUTE through the short junction: Blender opens a .blend by its real (long) path but
# disperse_pair.py appends it by the junction path, so a relative path written against one resolves to a wrong
# folder from the other (10-06: grass, creepers and the sky came out magenta in the transformation stills)
JUNCTION = r"C:\Users\haoni\AppData\Local\Temp\vdfs"
REAL = os.path.realpath(JUNCTION)
fixed = 0
for img in bpy.data.images:
    if img.packed_file or img.source != "FILE":
        continue
    n = os.path.normpath(bpy.path.abspath(img.filepath))
    if n.lower().startswith(REAL.lower()):
        n = JUNCTION + n[len(REAL):]
    if img.filepath != n:
        img.filepath = n
        fixed += 1
missing = [img.name for img in bpy.data.images
           if img.source == "FILE" and not img.packed_file and not os.path.exists(img.filepath)]
print("[cull] image paths made absolute: %d; missing files: %d %s" % (fixed, len(missing), missing[:5]), flush=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out), compress=True, relative_remap=False)
print("[cull] saved", args.out, flush=True)
