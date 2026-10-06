"""Elbow close-ups for judging arm weights, grey solid (workbench): rest, the elbow bent to 90 and 130 deg (the angle
between upper arm and forearm), and for a PMX also 腕捩 / 手捩 twisted 80 deg.  Two views of each: along the hinge axis
from outside the arm (the elbow's profile) and from in front (into the crease).

    PMX:  blender -b --factory-startup --python arm_stills.py -- pmx <file.pmx> <out dir> <label> [--axis x,y,z]
    game: blender -b <id>.blend --factory-startup --python arm_stills.py -- game - <out dir> <label>
          [--side l|r] [--size 560] [--sdef]

Writes <out>/<label>_<pose>_<view>.png (pose rest / bend90 / bend130 / twistU80 / twistF80, view side / inside);
arm_sheet.py lays several labels out side by side.  The game run (build_blend.py's .blend, UE names) prints
ELBOW_AXIS=: the hinge its rest pose bends the forearm about (the Vindictus UE body rests at 36.7 deg).  Pass that
to the PMX runs to bend in the same plane; without it a straight PMX arm bends forward (the model faces -Y).

``--sdef`` shows MMD's SDEF at the elbow through mmd_tools' SDEF driver (run Blender with -y): a PMX with SDEF data of
its own gets that bound; otherwise every vertex weighted to exactly 腕捩 + ひじ gets SDEF data with C at the elbow
joint, as a preview.  Tried on PCF_005 2026-10-04: a rounder elbow at 130 deg, but the arm wrap's zigzag edge and the
skin under it part where the game weights the two layers differently - not the default; the user compares.
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("kind", choices=("pmx", "game"))
ap.add_argument("path")
ap.add_argument("out")
ap.add_argument("label")
ap.add_argument("--axis", default="", help="hinge axis x,y,z (world) - the game run's ELBOW_AXIS")
ap.add_argument("--side", choices=("l", "r"), default="l")
ap.add_argument("--size", type=int, default=560)
ap.add_argument("--sdef", action="store_true", help="PMX: preview SDEF on the 腕捩 + ひじ elbow ring (needs -y)")
args = ap.parse_args(argv)
os.makedirs(args.out, exist_ok=True)

if args.kind == "pmx":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mmd_scene  # noqa: E402
    scene, root, rig, arm = mmd_scene.load(args.path, types=("MESH", "ARMATURE"))
    s = ".L" if args.side == "l" else ".R"           # mmd_tools names the sides .L / .R
    UP, FORE, HAND, TW_UP, TW_FORE = "腕" + s, "ひじ" + s, "手首" + s, "腕捩" + s, "手捩" + s
else:
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    s = "_" + args.side
    UP, FORE, HAND, TW_UP, TW_FORE = "upperarm" + s, "lowerarm" + s, "hand" + s, None, None
    for o in scene.objects:
        if o.type not in ("MESH", "ARMATURE"):
            o.hide_render = True
mw = arm.matrix_world
pose = arm.pose.bones


def head(name):
    return mw @ arm.data.bones[name].head_local


S, J, W = head(UP), head(FORE), head(HAND)
u, f = (J - S).normalized(), (W - J).normalized()
rest_deg = math.degrees(u.angle(f))
if args.axis:
    n = Vector([float(x) for x in args.axis.split(",")]).normalized()
    if args.side == "r":
        n = Vector((n.x, -n.y, -n.z))                 # mirror the left hinge across x = 0
elif rest_deg > 1.0:
    n = u.cross(f).normalized()
    print("ELBOW_AXIS=%.6f,%.6f,%.6f rest bend %.1f deg" % (n.x, n.y, n.z, rest_deg), flush=True)
else:
    n = u.cross(Vector((0.0, -1.0, 0.0))).normalized()
L = (J - S).length
print("rest elbow angle %.1f deg, upper arm %.3f" % (rest_deg, L), flush=True)


def rotate(name, pivot, axis, deg):
    pb = pose[name]
    inv = mw.inverted()
    p = inv @ pivot
    a = (inv.to_3x3() @ axis).normalized()
    pb.matrix = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, a) @ Matrix.Translation(-p) @ pb.matrix
    bpy.context.view_layer.update()


def reset():
    for pb in pose:
        pb.matrix_basis = Matrix()
    bpy.context.view_layer.update()


SDEF = []
if args.sdef and args.kind == "pmx":
    from mmd_tools.core.sdef import FnSDEF
    pair = {TW_UP, FORE}
    for obj in [o for o in scene.objects if o.type == "MESH" and o.modifiers.get("mmd_bone_order_override")]:
        if FnSDEF.has_sdef_data(obj):              # the PMX has its own SDEF vertices: drive those
            FnSDEF.bind(obj, bulk_update=True, use_skip=False)
            SDEF.append(obj)
            print("SDEF %s: the PMX's own SDEF data bound" % obj.name, flush=True)
            continue
        index = {g.index: g.name for g in obj.vertex_groups}
        ring = [v.index for v in obj.data.vertices
                if {index.get(g.group) for g in v.groups if g.weight > 0 and index.get(g.group) in pose.keys()} == pair
                and sum(1 for g in v.groups if g.weight > 0 and index.get(g.group) in pose.keys()) == 2]
        if not ring:
            continue
        if not obj.data.shape_keys:
            obj.shape_key_add(name="Basis", from_mix=False)
        centre = obj.matrix_world.inverted() @ J
        for key in ("mmd_sdef_c", "mmd_sdef_r0", "mmd_sdef_r1"):
            block = obj.shape_key_add(name=key, from_mix=False)
            for i in ring:
                block.data[i].co = centre
        FnSDEF.bind(obj, bulk_update=True, use_skip=False)
        SDEF.append(obj)
        print("SDEF %s: %d ring vertices" % (obj.name, len(ring)), flush=True)

render = scene.render
render.engine = "BLENDER_WORKBENCH"
render.resolution_x = render.resolution_y = args.size
render.film_transparent = False
render.image_settings.file_format = "PNG"
shading = scene.display.shading
shading.light, shading.color_type, shading.single_color = "STUDIO", "SINGLE", (0.72, 0.72, 0.72)
shading.show_cavity = True
shading.cavity_type = "WORLD"
shading.background_type = "VIEWPORT"
camera_data = bpy.data.cameras.new("elbow")
camera_data.type = "ORTHO"
camera_data.ortho_scale = 1.6 * L
camera_data.clip_end = 20 * L
camera = bpy.data.objects.new("elbow", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera


def shoot(tag, view, up=Vector((0.0, 0.0, 1.0))):
    z = view.normalized()
    x = up.cross(z).normalized()
    camera.location = (mw @ pose[FORE].head) + z * 3.0 * L
    camera.rotation_euler = Matrix((x, z.cross(x), z)).transposed().to_euler()
    render.filepath = os.path.join(args.out, "%s_%s.png" % (args.label, tag))
    bpy.ops.render.render(write_still=True)


def shots(tag):
    if SDEF:
        from mmd_tools.core.sdef import FnSDEF
        for obj in SDEF:
            key = obj.data.shape_keys.key_blocks[FnSDEF.SHAPEKEY_NAME]
            FnSDEF.driver_function(key, obj.name, bulk_update=True, use_skip=False, use_scale=False)
            key.value = 1.0
        bpy.context.view_layer.update()
    elbow = mw @ pose[FORE].head
    upper = (elbow - (mw @ pose[UP].head)).normalized()
    fore = ((mw @ pose[HAND].head) - elbow).normalized()
    crease = fore - upper if (fore - upper).length > 1e-4 else n.cross(upper)
    outside = -n if args.side == "l" else n
    shoot(tag + "_side", outside)
    shoot(tag + "_inside", crease.normalized() + 0.6 * outside)


reset()
shots("rest")
for target in (90, 130):
    reset()
    rotate(FORE, J, n, target - rest_deg)
    shots("bend%d" % target)
if TW_UP:
    for name, tag in ((TW_UP, "twistU80"), (TW_FORE, "twistF80")):
        reset()
        bone = arm.data.bones[name]
        rotate(name, mw @ pose[name].head, mw.to_3x3() @ (bone.tail_local - bone.head_local), 80)
        shots(tag)
print("ARM_STILLS_DONE", flush=True)
