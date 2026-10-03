# -*- coding: utf-8 -*-
"""An MMD motion on an exported PMX, rendered to a video with its music - inside Blender 3.6 (headless).

    blender -b --python render_dance_blender.py -- --pmx <model.pmx> --vmd <motion.vmd> --out <video.mp4>
            [--bgm <music.wav>] [--size 1080x1920] [--frames N] [--margin 30] [--samples 32]
            [--view full|chest|chest:<deg>] [--physics mmd|blender] [--bust key=value,...]
            [--backdrop <picture>] [--backdrop-turn <deg>] [--shadow 0.45]
            [--stills N] [--no-video] [--no-edge] [--no-blend]

dance_video.py is the command to use; this is its Blender side.

What it does, in this order (the order matters, each line was learnt on another game):

  * imports the PMX with mmd_tools WITH its physics, then Model.build(): without the build no bone reads
    its rigid body and every hair / skirt chain rides its parent bone like a plank;
  * binds the morph sliders, or the VMD's expression keys (blinks, mouth) drive nothing;
  * toon edges: mmd_tools' own edge preview (an inverted hull from the PMX edge colour and width);
  * imports the VMD with a lead-in (--margin frames of rest pose blending into the first pose): a model that
    jumps from the rest pose into the dance in one frame gets its hair flung over its head for good;
  * --physics mmd (the default): the joints run the way MMD's Bullet runs them, not the way mmd_tools leaves
    them - without the 0.5 damping Blender puts on every joint axis (it holds soft springs nearly still: no
    breast bounce), rotation springs in PMX units, gravity 98 - and bodies whose PMX mask says "collide with
    nothing" really collide with nothing (tsquad_blender.mmd_like_joints / isolate_loners);
  * BAKES the rigid body simulation over lead-in + motion and only then renders - an animation rendered on
    a live cache shows physics the model does not have;
  * lights the way MMD shows a toon model: white ambient light so that a material comes out as its texture,
    one weak sun for shape and a ground shadow, the Standard view transform (see scripts/taimaninsquad/README);
  * the camera is fixed and frames everything the model touches during the motion (measured on the baked
    frames), portrait by default; --view chest is a close-up that rides the upper body instead, so the torso
    holds still on screen and what moves is the breast physics (chest:60 looks from 60 degrees to the side);
  * --backdrop puts a picture behind the model (the game's own: export_backgrounds.py).  A panorama (twice as
    wide as high) is what the camera sees of the world, so it turns with the camera; any other picture sits on a
    plane that fills the frame behind everything.  The model is lit as before; the floor becomes see-through and
    only darkens the picture where the model's shadow falls;
  * renders the motion without its lead-in: the first video frame is VMD frame 0, where the music starts.

--stills N renders N frames spread over the motion as PNG next to the video (<out stem>_stills/) - look at
them before rendering the whole thing (--no-video).  A .blend with everything in it (images and music
packed, physics baked) is saved next to the video: open it in Blender and press play.

--bust key=value,... tries other breast physics on THIS video only (the PMX file is not changed; the
settings are tsquad_blender.BUST: bounce_hz, sway_hz, ratio ...).  To put them into the PMX:
export_model.py <id> --pmx --reconvert --bust ...

The last line printed is TSQ_DANCE={json}.
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_blender as tb  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--pmx", required=True)
ap.add_argument("--vmd", required=True)
ap.add_argument("--out", required=True, help="the .mp4 to write")
ap.add_argument("--bgm", default="", help="music (wav / mp3 / ogg); starts with VMD frame 0")
ap.add_argument("--size", default="", help="WIDTHxHEIGHT (default 1080x1920, portrait; 1080x1080 for --view chest)")
ap.add_argument("--frames", type=int, default=0, help="only the first N frames of the motion (0 = all)")
ap.add_argument("--margin", type=int, default=30, help="lead-in frames before the motion (not rendered)")
ap.add_argument("--samples", type=int, default=32, help="EEVEE samples per frame")
ap.add_argument("--scale", type=float, default=0.08, help="import scale: 0.08 puts a 12.5-scale PMX back in metres")
ap.add_argument("--view", default="full", help="full (default) | chest | chest:<degrees round to the model's left>")
ap.add_argument("--physics", choices=("mmd", "blender"), default="mmd",
                help="mmd (default): joints as MMD runs them; blender: as mmd_tools leaves them (stiffer, calmer)")
ap.add_argument("--gravity", type=float, default=98.0, help="with --physics mmd: PMX units / s^2 (MMD: 98)")
ap.add_argument("--bust", default=None, help="breast physics for this video only: key=value,... (tsquad_common.BUST), "
                "fitted to the breasts' size and cap_cm like the PMX export does")
ap.add_argument("--backdrop", default="", help="a picture behind the model; it fills the frame.  Of a panorama "
                "(twice as wide as high) a view is taken first")
ap.add_argument("--backdrop-as", choices=("auto", "flat", "view", "world"), default="auto",
                help="auto (default): a picture twice as wide as high is a panorama and a 'view' of it is used, any "
                     "other picture is 'flat' | world: the panorama as the world around the scene (it turns with "
                     "the camera, but a long lens shows a blurred corner of it)")
ap.add_argument("--backdrop-fov", type=float, default=70.0, help="panorama: how many degrees of it the view shows, top to bottom")
ap.add_argument("--backdrop-turn", type=float, default=0.0, help="panorama: look this many degrees to the right of its middle")
ap.add_argument("--backdrop-tilt", type=float, default=0.0, help="panorama: look this many degrees up")
ap.add_argument("--shadow", type=float, default=0.45, help="with --backdrop: how dark the model's shadow on the ground is (0 = none)")
ap.add_argument("--stills", type=int, default=0, help="also render N check frames as PNG")
ap.add_argument("--no-video", action="store_true")
ap.add_argument("--no-edge", action="store_true", help="no toon outline")
ap.add_argument("--no-blend", action="store_true", help="do not save the .blend next to the video")
args = ap.parse_args(argv)

CHEST = args.view.startswith("chest")
if not (CHEST or args.view == "full"):
    raise SystemExit("--view is full, chest or chest:<degrees>")
WIDTH, HEIGHT = (int(v) for v in (args.size or ("1080x1080" if CHEST else "1080x1920")).lower().split("x"))
OUT = os.path.abspath(args.out)
STEM = os.path.splitext(OUT)[0]
AMBIENT, SUN, SUN_TILT = 0.8, 0.6, math.radians(50.0)       # the "mmd look" of preview_pmx_blender.py
BACKDROP = (0.50, 0.51, 0.55)
report = {"pmx": args.pmx, "vmd": args.vmd, "bgm": args.bgm or None, "out": OUT, "size": [WIDTH, HEIGHT]}


def log(text):
    print("[dance] " + text, flush=True)


# ---------------------------------------------------------------- model
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="mmd_tools")
scene = bpy.context.scene
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=args.scale,
                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
from mmd_tools.core.model import Model  # noqa: E402

root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
rig = Model(root)
arm = rig.armature()
meshes = list(rig.meshes())
if args.bust is not None:                               # other breast physics, for this video only
    params = tb.parse_bust(args.bust)
    if params["style"] == "spring":
        report["bust_override"] = tb.spring_bust(scene, params)
rig.build()                                             # bones follow their rigid bodies from here on
if args.physics == "mmd":
    report["no_collision_bodies"] = tb.isolate_loners(scene)
rig.morph_slider.create()
rig.morph_slider.bind()
root.mmd_root.show_rigid_bodies = root.mmd_root.show_joints = False
root.mmd_root.show_armature = False
for o in scene.objects:
    if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT") or o.type in ("ARMATURE", "EMPTY"):
        o.hide_render = True


def select_model():
    bpy.ops.object.select_all(action="DESELECT")
    for o in [root] + list(root.children_recursive):
        try:
            o.select_set(True)
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = root


if not args.no_edge:
    select_model()
    try:
        bpy.ops.mmd_tools.edge_preview_setup(action="CREATE")
        report["edges"] = sum(1 for o in meshes if "mmd_edge_preview" in o.modifiers)
    except RuntimeError as exc:
        report["edges"] = "failed: %s" % exc

# ---------------------------------------------------------------- motion
select_model()
bpy.ops.mmd_tools.import_vmd(filepath=args.vmd, scale=args.scale, margin=args.margin, bone_mapper="PMX",
                             update_scene_settings=True)
first = args.margin + 1 if args.margin > 0 else scene.frame_start      # scene frame of VMD frame 0
last = scene.frame_end
if args.frames:
    last = min(last, first + args.frames - 1)
scene.frame_start, scene.frame_end = 1, last
scene.render.fps = 30
report.update(motion_frames=last - first + 1, first_frame=first, last_frame=last, fps=scene.render.fps)
log("motion: scene frames %d-%d (%d frames, %.1f s), lead-in %d" % (first, last, last - first + 1,
                                                                     (last - first + 1) / 30.0, args.margin))

# ---------------------------------------------------------------- physics: bake, then look
rbw = scene.rigidbody_world
report["physics"] = args.physics
if rbw is not None and args.physics == "mmd":
    report["mmd_like_joints"] = tb.mmd_like_joints(scene, args.scale, args.gravity)
if rbw is not None:
    rbw.enabled = True
    rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, last
    with bpy.context.temp_override(scene=scene, point_cache=rbw.point_cache):
        bpy.ops.ptcache.bake(bake=True)
    driven = sum(1 for b in arm.pose.bones if "mmd_tools_rigid_track" in b.constraints)
    report.update(rigid_bodies=len(rbw.collection.objects) if rbw.collection else 0, bones_on_physics=driven)
    log("physics baked: frames 1-%d, %s rigid bodies, %d bones driven by them" % (last, report["rigid_bodies"], driven))
else:
    report.update(rigid_bodies=0, bones_on_physics=0)

# everything the model touches during the motion (every 3rd frame), and how far its loose bodies stray
hips = arm.pose.bones.get("下半身") or arm.pose.bones.get("センター")
dynamic = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.rigid_body
           and o.rigid_body.type == "ACTIVE" and not o.rigid_body.kinematic]
lo, hi, far = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9)), 0.0
for f in list(range(first, last + 1, 3)) + [last]:
    scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            p = ev.matrix_world @ Vector(c)
            lo = Vector((min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z)))
            hi = Vector((max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z)))
    if hips is not None and dynamic:
        c = arm.matrix_world @ hips.head
        far = max(far, max((o.matrix_world.translation - c).length for o in dynamic))
report.update(bounds=[[round(v, 3) for v in lo], [round(v, 3) for v in hi]],
              max_rigid_body_distance_from_hips_m=round(far, 2))

# how much the breasts move against the chest, in numbers: "is there any bounce" should not be a matter of
# squinting at a video.  Axes: to the model's left, to its front, up - as the chest stands in the rest pose.
by_name = {(b.mmd_bone.name_j or b.name): b for b in arm.pose.bones}
chest = by_name.get("上半身3") or by_name.get("上半身2") or by_name.get("上半身")
busts = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.name_j in tb.BUST_BONES]
if chest is not None and busts:
    import numpy as np

    rest_axes = (arm.matrix_world @ chest.bone.matrix_local).to_3x3()
    tracks = {o.mmd_rigid.name_j: [] for o in busts}
    for f in range(1, last + 1):
        scene.frame_set(f)
        frame = (arm.matrix_world @ chest.matrix).inverted()
        for o in busts:
            tracks[o.mmd_rigid.name_j].append((rest_axes @ (frame @ o.matrix_world.translation))[:])
    report["bust_motion"] = {}
    for name, track in tracks.items():
        t = (np.array(track) - np.array(track[0])) * 100.0 * np.array([1.0, -1.0, 1.0])     # cm: left, front, up
        m = t[first - 1:]
        speed = np.linalg.norm(np.diff(m, axis=0), axis=1)
        report["bust_motion"][name] = {
            "settles_at_cm": [round(float(v), 2) for v in m[0]],
            "travel_cm": [round(float(v), 2) for v in (m.max(axis=0) - m.min(axis=0))],
            "speed_cm_per_frame": {"median": round(float(np.median(speed)), 3), "p95": round(float(np.percentile(speed, 95)), 3)},
        }
    one = next(iter(report["bust_motion"].values()))
    log("breasts: travel %s cm (left-right, front-back, up-down), %.2f cm per frame (median), %.2f (fast 5%%)" % (
        one["travel_cm"], one["speed_cm_per_frame"]["median"], one["speed_cm_per_frame"]["p95"]))

# ---------------------------------------------------------------- look
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = args.samples
scene.eevee.use_soft_shadows = True
scene.eevee.shadow_cascade_size = "2048"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.render.film_transparent = False
world = bpy.data.worlds.new("TSQ Dance")
world.use_nodes = True
wt = world.node_tree
white = next(n for n in wt.nodes if n.type == "BACKGROUND")
white.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)      # what lights the model: a material comes out as its texture
white.inputs[1].default_value = AMBIENT
backdrop = wt.nodes.new("ShaderNodeBackground")           # what the camera sees
backdrop.inputs[0].default_value = BACKDROP + (1.0,)
path = wt.nodes.new("ShaderNodeLightPath")
mix = wt.nodes.new("ShaderNodeMixShader")
wt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
wt.links.new(white.outputs[0], mix.inputs[1])
wt.links.new(backdrop.outputs[0], mix.inputs[2])
wt.links.new(mix.outputs[0], next(n for n in wt.nodes if n.type == "OUTPUT_WORLD").inputs[0])
scene.world = world



def panorama_view(image, width, height, fov_deg, turn_deg, tilt_deg):
    """A straight view into an equirectangular picture, as a new packed image width x height: fov_deg from top
    to bottom, looking turn_deg to the right of the picture's middle and tilt_deg up.  (The scene camera is a
    long lens: of a 4096 px panorama it would see a strip 300 px high.  The backdrop gets a lens of its own.)"""
    import numpy as np

    w, h = image.size
    src = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(src)                         # display values, rows bottom-up
    src = src.reshape(h, w, 4)
    focal = 0.5 * height / math.tan(math.radians(fov_deg) / 2.0)
    x, y = np.meshgrid(np.arange(width) - (width - 1) / 2.0, np.arange(height) - (height - 1) / 2.0)
    z = np.full_like(x, focal)
    tilt = math.radians(tilt_deg)                         # about the axis to the right: up is +y
    y, z = y * math.cos(tilt) + z * math.sin(tilt), z * math.cos(tilt) - y * math.sin(tilt)
    lon = np.arctan2(x, z) + math.radians(turn_deg)
    lat = np.arctan2(y, np.hypot(x, z))
    u = ((lon / (2.0 * math.pi) + 0.5) % 1.0) * w - 0.5
    v = np.clip((lat / math.pi + 0.5) * h - 0.5, 0.0, h - 1.0)
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    u1, v1 = (u0 + 1) % w, np.minimum(v0 + 1, h - 1)
    u0 %= w
    out = (src[v0, u0] * (1 - fu) * (1 - fv) + src[v0, u1] * fu * (1 - fv)
           + src[v1, u0] * (1 - fu) * fv + src[v1, u1] * fu * fv)
    out[..., 3] = 1.0
    view = bpy.data.images.new(os.path.splitext(image.name)[0] + "_view", width, height, alpha=False)
    view.pixels.foreach_set(np.ascontiguousarray(out, dtype=np.float32).ravel())
    view.pack()
    return view


# --backdrop: a picture on a plane behind everything, made further down once the camera is known (the light
# stays the white ambient: the model is lit as before).  "world" instead shows the panorama as the world.
PICTURE, WORLD_PICTURE = None, False
if args.backdrop:
    PICTURE = bpy.data.images.load(os.path.abspath(args.backdrop))
    kind = args.backdrop_as
    if kind == "auto":
        kind = "view" if PICTURE.size[0] == 2 * PICTURE.size[1] else "flat"
    report["backdrop"] = {"picture": os.path.abspath(args.backdrop), "size": list(PICTURE.size), "as": kind}
    if kind == "view":
        PICTURE = panorama_view(PICTURE, WIDTH, HEIGHT, args.backdrop_fov, args.backdrop_turn, args.backdrop_tilt)
        report["backdrop"].update(fov_deg=args.backdrop_fov, turn_deg=args.backdrop_turn, tilt_deg=args.backdrop_tilt)
    elif kind == "world":
        WORLD_PICTURE = True
        coord = wt.nodes.new("ShaderNodeTexCoord")
        turn = wt.nodes.new("ShaderNodeMapping")
        # Blender shows the middle of an equirectangular picture along -X; the camera looks along +Y: a quarter turn
        turn.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(90.0 + args.backdrop_turn))
        env = wt.nodes.new("ShaderNodeTexEnvironment")
        env.image = PICTURE
        wt.links.new(coord.outputs["Generated"], turn.inputs["Vector"])
        wt.links.new(turn.outputs["Vector"], env.inputs["Vector"])
        wt.links.new(env.outputs["Color"], backdrop.inputs[0])
        report["backdrop"]["turn_deg"] = args.backdrop_turn
sun_data = bpy.data.lights.new("Key", "SUN")
sun_data.energy = SUN
sun_data.angle = math.radians(6.0)                        # a soft edge on the ground shadow
sun_data.shadow_cascade_max_distance = 30.0
sun = bpy.data.objects.new("Key", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (SUN_TILT, 0.0, math.radians(-30.0))

# The floor shows nothing but the model's shadow: its lit colour is the backdrop's, so there is no horizon.
# (Diffuse -> Shader to RGB reads the light the floor gets: AMBIENT in the shadow, more in the sun.)
size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 2.0) * 6.0
floor_mesh = bpy.data.meshes.new("Floor")
floor_mesh.from_pydata([(-size, -size, 0.0), (size, -size, 0.0), (size, size, 0.0), (-size, size, 0.0)], [], [(0, 1, 2, 3)])
floor = bpy.data.objects.new("Floor", floor_mesh)
scene.collection.objects.link(floor)
fm = bpy.data.materials.new("Floor")
fm.use_nodes = True
ft = fm.node_tree
for node in list(ft.nodes):
    ft.nodes.remove(node)
diffuse = ft.nodes.new("ShaderNodeBsdfDiffuse")
diffuse.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
to_rgb = ft.nodes.new("ShaderNodeShaderToRGB")
lit = AMBIENT + SUN / math.pi * math.cos(SUN_TILT)
ramp = ft.nodes.new("ShaderNodeMapRange")
ramp.inputs["From Min"].default_value = AMBIENT + 0.15 * (lit - AMBIENT)
ramp.inputs["From Max"].default_value = AMBIENT + 0.85 * (lit - AMBIENT)
shade = ft.nodes.new("ShaderNodeMixRGB")
shade.inputs[1].default_value = tuple(c * 0.62 for c in BACKDROP) + (1.0,)
shade.inputs[2].default_value = BACKDROP + (1.0,)
emit = ft.nodes.new("ShaderNodeEmission")
out_node = ft.nodes.new("ShaderNodeOutputMaterial")
ft.links.new(diffuse.outputs[0], to_rgb.inputs[0])
ft.links.new(to_rgb.outputs["Color"], ramp.inputs["Value"])
ft.links.new(ramp.outputs[0], shade.inputs[0])
ft.links.new(shade.outputs[0], emit.inputs["Color"])
ft.links.new(emit.outputs[0], out_node.inputs["Surface"])
if PICTURE is not None:
    # over a picture the floor is see-through and only darkens what lies behind it where the shadow falls
    clear = ft.nodes.new("ShaderNodeBsdfTransparent")
    emit.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    ft.links.remove(emit.inputs["Color"].links[0])
    in_shadow = ft.nodes.new("ShaderNodeMath")
    in_shadow.operation = "SUBTRACT"
    in_shadow.inputs[0].default_value = 1.0
    darken = ft.nodes.new("ShaderNodeMath")
    darken.operation = "MULTIPLY"
    darken.inputs[1].default_value = max(0.0, min(1.0, args.shadow))
    blend = ft.nodes.new("ShaderNodeMixShader")
    ft.links.new(ramp.outputs[0], in_shadow.inputs[1])
    ft.links.new(in_shadow.outputs[0], darken.inputs[0])
    ft.links.new(darken.outputs[0], blend.inputs[0])
    ft.links.new(clear.outputs[0], blend.inputs[1])
    ft.links.new(emit.outputs[0], blend.inputs[2])
    ft.links.new(blend.outputs[0], out_node.inputs["Surface"])
    fm.blend_method = "BLEND"
    fm.shadow_method = "NONE"
floor_mesh.materials.append(fm)

# ---------------------------------------------------------------- camera: fixed, everything in frame
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 70.0
cam_data.sensor_fit = "VERTICAL"
cam_data.sensor_height = 36.0
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = WIDTH, HEIGHT, 100
tall, wide = (hi.z - min(lo.z, 0.0)) * 1.10, (hi.x - lo.x) * 1.10
v_half = math.atan(18.0 / cam_data.lens)
h_half = math.atan(18.0 * WIDTH / HEIGHT / cam_data.lens)
distance = max(tall / 2.0 / math.tan(v_half), wide / 2.0 / math.tan(h_half))
target = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, (min(lo.z, 0.0) + hi.z) / 2.0))
cam.location = target + Vector((0.0, -1.0, 0.0)) * (distance + (hi.y - lo.y) / 2.0)    # the model faces -Y
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
cam_data.clip_start, cam_data.clip_end = 0.05, 200.0
sun_data.shadow_cascade_max_distance = distance * 1.6 + 2.0          # the shadow map covers what the camera sees
report["camera"] = {"view": args.view, "lens_mm": cam_data.lens, "distance_m": round(distance, 2),
                    "target": [round(v, 3) for v in target]}
if CHEST:
    # A close-up that rides the upper body: the torso holds still on screen, what moves is the physics.
    if chest is None:
        raise SystemExit("--view chest: the model has no 上半身 bone")
    yaw = math.radians(float(args.view.split(":", 1)[1])) if ":" in args.view else 0.0
    scene.frame_set(1)                                    # the rest pose (the lead-in starts from it)
    spots = [o.matrix_world.translation.copy() for o in busts] or [arm.matrix_world @ chest.head]
    aim = sum(spots, Vector()) / len(spots)
    cam_data.lens = 50.0
    reach = 0.42 / math.tan(math.atan(18.0 / cam_data.lens))          # 84 cm of chest, top to bottom
    spot = aim + Matrix.Rotation(yaw, 3, "Z") @ Vector((0.0, -reach, 0.04))      # the model faces -Y
    world_matrix = Matrix.Translation(spot) @ (aim - spot).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    # Parented to the bone with the inverse written out.  (Setting matrix_world right after the parent uses
    # the parent matrix of BEFORE the change until the view layer updates: the camera then sat somewhere
    # else and the chest wandered through the picture.)  A bone parent holds its child at the bone's tail.
    cam.parent, cam.parent_type, cam.parent_bone = arm, "BONE", chest.name
    cam.matrix_parent_inverse = (arm.matrix_world @ chest.matrix @ Matrix.Translation((0.0, chest.length, 0.0))).inverted()
    cam.matrix_basis = world_matrix
    sun_data.shadow_cascade_max_distance = 12.0
    report["camera"].update(lens_mm=cam_data.lens, distance_m=round(reach, 2), rides=chest.name)

if PICTURE is not None and not WORLD_PICTURE:
    # The picture: on a plane that fills the frame, far behind the model, held by the camera.  The picture
    # keeps its proportions and covers the frame - what does not fit is cut off evenly at both sides (a 4:3
    # picture in a portrait frame shows its middle 42 %), or at top and bottom.
    far = 60.0
    half_h = far * 18.0 / cam_data.lens
    half_w = half_h * WIDTH / HEIGHT
    frame_ratio, picture_ratio = WIDTH / HEIGHT, PICTURE.size[0] / PICTURE.size[1]
    du, dv = min(1.0, frame_ratio / picture_ratio) / 2.0, min(1.0, picture_ratio / frame_ratio) / 2.0
    plane_mesh = bpy.data.meshes.new("Backdrop")
    plane_mesh.from_pydata([(-half_w, -half_h, -far), (half_w, -half_h, -far), (half_w, half_h, -far),
                            (-half_w, half_h, -far)], [], [(0, 1, 2, 3)])
    uv_layer = plane_mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(uv_layer.data, ((0.5 - du, 0.5 - dv), (0.5 + du, 0.5 - dv), (0.5 + du, 0.5 + dv),
                                        (0.5 - du, 0.5 + dv))):
        loop.uv = uv
    plane = bpy.data.objects.new("Backdrop", plane_mesh)
    scene.collection.objects.link(plane)
    plane.parent = cam                                    # its corners are written in the camera's own space
    pm = bpy.data.materials.new("Backdrop")
    pm.use_nodes = True
    pt = pm.node_tree
    for node in list(pt.nodes):
        pt.nodes.remove(node)
    picture = pt.nodes.new("ShaderNodeTexImage")
    picture.image = PICTURE
    picture.extension = "EXTEND"
    glow = pt.nodes.new("ShaderNodeEmission")             # unlit: the picture as it is
    plane_out = pt.nodes.new("ShaderNodeOutputMaterial")
    pt.links.new(picture.outputs["Color"], glow.inputs["Color"])
    pt.links.new(glow.outputs[0], plane_out.inputs["Surface"])
    pm.shadow_method = "NONE"
    plane_mesh.materials.append(pm)
    report["backdrop"]["shown"] = [round(2.0 * du, 3), round(2.0 * dv, 3)]      # the share of the picture in frame

# ---------------------------------------------------------------- music
if args.bgm and os.path.isfile(args.bgm):
    scene.sequence_editor_create()
    scene.sequence_editor.sequences.new_sound("BGM", args.bgm, 1, first)
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.ffmpeg.audio_bitrate = 192
    scene.render.ffmpeg.audio_mixrate = 48000

os.makedirs(os.path.dirname(OUT), exist_ok=True)
scene.frame_start, scene.frame_end = first, last          # the lead-in is simulated, not shown


def video_settings():
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.gopsize = 30
    scene.render.use_file_extension = False
    scene.render.filepath = OUT


video_settings()                                          # in the saved .blend too: Render Animation redoes the video

# ---------------------------------------------------------------- the .blend: everything inside
if not args.no_blend:
    try:
        bpy.ops.file.pack_all()
    except RuntimeError as exc:
        report["pack"] = "not everything packed: %s" % exc
    bpy.context.preferences.filepaths.save_version = 0
    scene.frame_set(first)
    bpy.ops.wm.save_as_mainfile(filepath=STEM + ".blend", check_existing=False, compress=True)
    report["blend"] = STEM + ".blend"
    log("saved " + STEM + ".blend")

# ---------------------------------------------------------------- check frames
if args.stills > 0:
    folder = STEM + "_stills"
    os.makedirs(folder, exist_ok=True)
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_file_extension = True
    count = max(1, args.stills)
    picks = sorted({first + round(i * (last - first) / max(1, count - 1)) for i in range(count)}) if count > 1 else [first]
    report["stills"] = []
    for f in picks:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(folder, "frame_%04d.png" % (f - first))
        bpy.ops.render.render(write_still=True)
        report["stills"].append(scene.render.filepath)
    log("stills: %d in %s" % (len(picks), folder))

# ---------------------------------------------------------------- the video
if not args.no_video:
    video_settings()
    bpy.ops.render.render(animation=True)
    report["video"] = OUT if os.path.isfile(OUT) else None
    report["video_bytes"] = os.path.getsize(OUT) if os.path.isfile(OUT) else 0
    log("video: %s" % OUT)

print("TSQ_DANCE=" + json.dumps(report, ensure_ascii=False), flush=True)
