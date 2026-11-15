"""Linear vs SDEF in motion: a PMX and its SDEF version (pmx_sdef_rings.py) side by side under the same motion,
with close-ups that ride the right elbow and the left knee square to their bend plane, plus the ring metric per
frame (distance of the joint ring's vertices to the joint centre, posed / rest: linear skinning pulls the ring in -
the "collapse" at the crease - SDEF keeps it near 1).

Blender 3.6, background, mmd_tools enabled:

    blender -b --factory-startup --python sdef_compare_video.py -- <linear.pmx> <sdef.pmx> <out dir>
        [--vmd motion.vmd] [--frames N] [--bend]

  --vmd     the motion (mmd_tools import, 30 lead-in frames like render_pmx_dance.py; IK and 付与 work as in MMD)
  --bend    no motion file: the right elbow bends 0 -> 140 -> 0 deg, then the left knee 0 -> 130 -> 0 deg (thigh
            raised 60 deg first), IK muted - the cleanest view of the crease
  --frames  cap the frame count (0 = all)
  --step    render every N-th frame (the video plays at fps / N; ~7 s per frame for two 100k-vertex models)

Writes <out>/tiles/<frame>_<lin|sdef>_<full|elbow|knee>.png and <out>/metrics.json, prints SDEF_VIDEO_DONE=<json>.
compose_sdef_video.py (system Python + Pillow + ffmpeg) puts the tiles together with labels and the music.

SDEF in Blender: mmd_tools keeps SDEF as a shape key that a SCRIPTED driver rewrites every frame
(FnSDEF.bind).  Background Blender does not run scripted drivers unless auto-run is on, so this script removes the
driver after binding and calls FnSDEF.driver_function itself after each frame change (value pinned at 1).
MMD itself computes SDEF natively - this is only for looking at it in Blender.
"""
import json
import math
import os
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
LINEAR, SDEF, OUT = argv[0], argv[1], os.path.abspath(argv[2])


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


VMD = opt("--vmd")
FRAMES = int(opt("--frames", "0"))
STEP = max(1, int(opt("--step", "1")))     # render every STEP-th frame (the video then plays at fps / STEP)
BEND = "--bend" in argv
SCALE = 0.08          # mmd_tools exports at 12.5: 0.08 puts the model back in metres
MARGIN = 30           # lead-in frames before VMD frame 0 (as render_pmx_dance.py)
GAP = 4.0             # metres between the two models (each full-body camera sees only its own)
TILE = 560
ELBOW = ("右腕", "右ひじ", "右手首")
KNEE = ("左足", "左ひざ", "左足首")
os.makedirs(os.path.join(OUT, "tiles"), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
from mmd_tools.core.sdef import FnSDEF  # noqa: E402

scene = bpy.context.scene


def import_model(path, x):
    before = set(bpy.data.objects)
    bpy.ops.mmd_tools.import_model(filepath=path, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS"},
                                   log_level="ERROR")
    new = [o for o in bpy.data.objects if o not in before]
    root = next(o for o in new if o.parent is None)
    root.location.x = x
    arm = next(o for o in new if o.type == "ARMATURE")
    meshes = [o for o in new if o.type == "MESH" and o.find_armature() is arm]
    if VMD:
        bpy.ops.object.select_all(action="DESELECT")
        for o in new:
            if o.type in ("ARMATURE", "MESH", "EMPTY"):
                o.select_set(True)
        bpy.context.view_layer.objects.active = root
        bpy.ops.mmd_tools.import_vmd(filepath=VMD, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                                     update_scene_settings=True)
    else:
        for pb in arm.pose.bones:
            for c in pb.constraints:
                if c.type == "IK":
                    c.mute = True
    bones = {(pb.mmd_bone.name_j or pb.name): pb for pb in arm.pose.bones}
    return {"root": root, "arm": arm, "meshes": meshes, "bones": bones}


lin = import_model(LINEAR, -GAP / 2)
sdf = import_model(SDEF, GAP / 2)
models = (("lin", lin), ("sdef", sdf))

# SDEF: bind, drop the scripted driver, pin the key at 1; driver_function is called per frame below
sdef_meshes = []
for o in sdf["meshes"]:
    if FnSDEF.has_sdef_data(o) and FnSDEF.bind(o, bulk_update=True, use_skip=False):
        o.data.shape_keys.driver_remove('key_blocks["%s"].value' % FnSDEF.SHAPEKEY_NAME)
        o.data.shape_keys.key_blocks[FnSDEF.SHAPEKEY_NAME].value = 1.0
        sdef_meshes.append(o)
print("SDEF meshes:", [o.name for o in sdef_meshes])
if not sdef_meshes:
    raise SystemExit("the SDEF model has no SDEF vertices (mmd_tools shape keys mmd_sdef_c / r0 / r1 missing)")


def update_sdef():
    for o in sdef_meshes:
        key = o.data.shape_keys.key_blocks[FnSDEF.SHAPEKEY_NAME]
        FnSDEF.driver_function(key, o.name, bulk_update=True, use_skip=False, use_scale=False)
        o.data.update()
    bpy.context.view_layer.update()


def world_coords(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    co = co.reshape(-1, 3)
    M = np.array(obj.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def joint(m, names):
    mw = m["arm"].matrix_world
    return [mw @ m["bones"][n].head for n in names]


# ---- ring vertices: the vertices the tool made SDEF near each joint, read from the SDEF model's shape keys
def body_mesh(m):
    return max(m["meshes"], key=lambda o: len(o.data.vertices))


def basis_world(obj):
    """The mesh as stored (= the PMX rest pose), in world space."""
    co = np.empty(len(obj.data.vertices) * 3, np.float32)
    obj.data.vertices.foreach_get("co", co)
    M = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def rest_joint(m, name):
    arm = m["arm"]
    return arm.matrix_world @ arm.data.bones[m["bones"][name].name].head_local


bpy.context.view_layer.update()
rings = {}
sb = body_mesh(sdf)
lb = body_mesh(lin)
if len(sb.data.vertices) != len(lb.data.vertices):
    raise SystemExit("the two PMX differ in vertex count (%d / %d) - not a side file of the same model"
                     % (len(lb.data.vertices), len(sb.data.vertices)))
kb = sb.data.shape_keys.key_blocks
c_co = np.empty(len(sb.data.vertices) * 3, np.float32)
b_co = np.empty(len(sb.data.vertices) * 3, np.float32)
kb["mmd_sdef_c"].data.foreach_get("co", c_co)
sb.data.vertices.foreach_get("co", b_co)
has_sdef = np.linalg.norm(c_co.reshape(-1, 3) - b_co.reshape(-1, 3), axis=1) > 1e-7
rest_s, rest_l = basis_world(sb), basis_world(lb)
for tag, names, radius in (("elbow", ELBOW, 0.09), ("knee", KNEE, 0.12)):
    j_s, j_l = np.array(rest_joint(sdf, names[1])), np.array(rest_joint(lin, names[1]))
    ids = np.where(has_sdef & (np.linalg.norm(rest_s - j_s, axis=1) < radius))[0]
    rings[tag] = {"ids": ids, "names": names, "rest_s": np.linalg.norm(rest_s[ids] - j_s, axis=1),
                  "rest_l": np.linalg.norm(rest_l[ids] - j_l, axis=1)}
    print("ring %s: %d SDEF vertices within %.2f m of %s" % (tag, len(ids), radius, names[1]))
    if not len(ids):
        raise SystemExit("no SDEF vertices around %s" % names[1])


def ring_metrics():
    """{elbow|knee: {lin|sdef: (mean, min)}} of posed / rest distance to the joint centre, this frame."""
    co = {"lin": world_coords(lb), "sdef": world_coords(sb)}
    out = {}
    for tag, r in rings.items():
        out[tag] = {}
        for key, m, rest in (("lin", lin, r["rest_l"]), ("sdef", sdf, r["rest_s"])):
            j = np.array(joint(m, r["names"])[1])
            ratio = np.linalg.norm(co[key][r["ids"]] - j, axis=1) / np.maximum(rest, 1e-6)
            out[tag][key] = (float(ratio.mean()), float(ratio.min()))
    return out


def bend_angle(m, names):
    a, b, c = joint(m, names)
    u, v = (a - b).normalized(), (c - b).normalized()
    return 180.0 - math.degrees(u.angle(v))


# ---- cameras and render settings
def make_camera(name, ortho):
    cd = bpy.data.cameras.new(name)
    if ortho:
        cd.type = "ORTHO"
    else:
        cd.lens = 50
    cam = bpy.data.objects.new(name, cd)
    scene.collection.objects.link(cam)
    return cam


cams = {}
for key, m in models:
    x = m["root"].location.x
    c = make_camera(key + "_full", False)
    c.location = Vector((x, -3.2, 0.95))
    c.rotation_euler = (Vector((x, 0, 0.88)) - c.location).to_track_quat("-Z", "Y").to_euler()
    cams[key, "full"] = c
    cams[key, "elbow"] = make_camera(key + "_elbow", True)
    cams[key, "knee"] = make_camera(key + "_knee", True)
prev_n = {"elbow": None, "knee": None}


CENTRE = {"elbow": ("左腕", "右腕"), "knee": ("左足", "右足")}


def aim_closeups():
    """Square to the bend plane of the LINEAR model's limb (both models move alike), the upper bone pointing up, and
    always from OUTSIDE the body (else the torso / the other leg stands in front of the joint)."""
    for tag, names, size in (("elbow", ELBOW, 0.36), ("knee", KNEE, 0.46)):
        a, b, c = joint(lin, names)
        n = (b - a).cross(c - b)
        nearly_straight = bend_angle(lin, names) < 15.0
        if n.length < 1e-6 or (nearly_straight and prev_n[tag] is not None):
            # a straight limb has no bend plane: keep the last view instead of spinning the camera
            n = prev_n[tag] or Vector((1, 0, 0))
        n = n.normalized()
        centre = sum(joint(lin, CENTRE[tag]), Vector()) / 2      # mid shoulders / mid hips
        out = b - centre
        out.z = 0.0
        if out.length > 1e-4 and abs(n.dot(out.normalized())) > 0.25:
            if n.dot(out) < 0:
                n = -n                                           # the camera on the joint's outer side
        elif prev_n[tag] is not None and n.dot(prev_n[tag]) < 0:
            n = -n                                               # no clear outside: keep the last side
        if prev_n[tag] is not None and n.dot(prev_n[tag]) > 0:
            n = (prev_n[tag] * 0.6 + n * 0.4).normalized()      # smooth: no jitter between frames
        prev_n[tag] = n
        up = (a - b)
        up = (up - n * up.dot(n)).normalized()
        x_axis = up.cross(n)
        rot = Matrix((x_axis, up, n)).transposed().to_4x4()
        for key, m in models:
            j = joint(m, names)[1]
            cam = cams[key, tag]
            cam.data.ortho_scale = size
            cam.data.clip_start, cam.data.clip_end = 1.0 - 0.11, 1.0 + 0.11
            cam.matrix_world = Matrix.Translation(j + n * 1.0) @ rot


scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = scene.render.resolution_y = TILE
scene.render.image_settings.file_format = "PNG"
sh = scene.display.shading
sh.light = "STUDIO"
sh.show_cavity, sh.cavity_type = True, "BOTH"
sh.show_specular_highlight = True
world = bpy.data.worlds.new("W")
scene.world = world
world.color = (0.30, 0.31, 0.33)
sh.background_type = "WORLD"


def render(tag_file, cam, closeup):
    scene.camera = cam
    sh.color_type = "SINGLE" if closeup else "TEXTURE"
    sh.single_color = (0.80, 0.68, 0.60)
    scene.render.filepath = tag_file
    bpy.ops.render.render(write_still=True)


# ---- the frames
if BEND:
    seg = 60
    total = 4 * seg
    start, end = 1, total
else:
    start, end = scene.frame_start, scene.frame_end
start = int(opt("--from", start))         # first frame (a trial on a stretch in the middle)
if FRAMES:
    end = min(end, start + FRAMES - 1)


def bend_pose(f):
    """--bend: pose both models procedurally for frame f (rest pose + rotations about the bend axis, in world)."""
    k = f - 1
    elbow = knee = 0.0
    thigh = 0.0
    if k < 2 * seg:
        elbow = 140.0 * math.sin(math.pi * k / (2 * seg))
    else:
        kk = k - 2 * seg
        thigh = 60.0 * min(1.0, kk / 20.0) if kk < 2 * seg - 20 else 60.0 * max(0.0, (2 * seg - kk) / 20.0)
        knee = 130.0 * math.sin(math.pi * kk / (2 * seg))
    for _, m in models:
        arm = m["arm"]
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix()
        bpy.context.view_layer.update()
        mw = arm.matrix_world

        def rot(bone, child, hint, deg):
            if not deg:
                return
            pb = m["bones"][bone]
            head = mw @ pb.head
            d = (mw @ m["bones"][child].head - head).normalized()
            axis = d.cross(hint).normalized()
            R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
            pb.matrix = mw.inverted() @ R @ mw @ pb.matrix
            bpy.context.view_layer.update()

        # rotating the child direction d about d x hint turns it towards hint; the model faces -Y
        rot("左足", "左ひざ", Vector((0, -1, 0)), thigh)      # thigh raised forward
        rot("右ひじ", "右手首", Vector((0, -1, 0)), elbow)    # forearm forward-up
        rot("左ひざ", "左足首", Vector((0, 1, 0)), knee)      # shin back
    return {"elbow_set": elbow, "knee_set": knee}


metrics = []
for f in range(start, end + 1, STEP):
    if BEND:
        extra = bend_pose(f)
    else:
        scene.frame_set(f)
        extra = {}
    update_sdef()
    aim_closeups()
    row = {"frame": f, "elbow_deg": round(bend_angle(lin, ELBOW), 1), "knee_deg": round(bend_angle(lin, KNEE), 1)}
    for tag, mt in ring_metrics().items():
        row[tag] = {k: [round(v[0], 3), round(v[1], 3)] for k, v in mt.items()}
    row.update(extra)
    metrics.append(row)
    for key, _ in models:
        for view in ("full", "elbow", "knee"):
            render(os.path.join(OUT, "tiles", "%05d_%s_%s.png" % (f, key, view)), cams[key, view], view != "full")
    if f % 25 == 0:
        print("frame %d/%d" % (f, end), flush=True)

with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as fh:
    json.dump({"linear": LINEAR, "sdef": SDEF, "vmd": VMD, "bend": BEND, "fps": scene.render.fps / STEP,
               "scene_fps": scene.render.fps, "step": STEP,
               "frame_start": start, "frame_end": end, "lead_in": 0 if BEND else MARGIN,
               "rings": {k: int(len(v["ids"])) for k, v in rings.items()}, "frames": metrics}, fh, ensure_ascii=False)


def worst(tag, key):
    vals = [r[tag][key][1] for r in metrics]
    return round(min(vals), 3) if vals else None


print("SDEF_VIDEO_DONE=" + json.dumps({"out": OUT, "frames": len(metrics),
                                       "rings": {k: int(len(v["ids"])) for k, v in rings.items()},
                                       "elbow_worst": {"lin": worst("elbow", "lin"), "sdef": worst("elbow", "sdef")},
                                       "knee_worst": {"lin": worst("knee", "lin"), "sdef": worst("knee", "sdef")}},
                                      ensure_ascii=False))
