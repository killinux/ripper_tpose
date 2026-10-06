"""Chest close-up of a PMX dancing under MMD's physics (mmd_scene.mmd_like): PNG frames + an mp4.

  blender -b --factory-startup --python bust_video.py -- <model.pmx> <out dir> <label>
          [--vmd <motion.vmd>] [--frames 0] [--yaw 70] [--size 640] [--physics mmd|addon]
          [--distance 0.78] [--lift 0] [--fixed] [--sdef] [--kawaii [--kawaii-carrier 下半身] [--kawaii-capsules]]

``--vmd`` defaults to test_motion.VMD (the 10 s gesture dance), ``--frames`` 0 = the whole motion.

The camera rides the bone the breasts hang from (上半身4 on the UE body), ``--yaw`` degrees round from the front
towards the model's left (70: the silhouette shows the bounce), so the torso holds still on screen and what moves
is the breast physics; ``--fixed`` leaves it where it starts (``--distance 3.2 --lift -0.45``: the whole body
dancing).  Writes <out>/frames_<label>/####.png and <out>/chest_<label>.mp4; bust_grid.py puts
several clips side by side.  About 0.5 s a frame (EEVEE, 16 samples): 600 frames ~ 5 min.

Lighter than scripts/riseoferos/render_pmx_dance.py's chest view (no morph sliders, no saved .blend; a 40-frame
test with that one ran past 15 minutes on PCF_012).  The camera is made after the motion import - import_vmd moves
a camera that is already in the scene - and a bone parent holds a child at the bone's tail, so the camera's
place is set through matrix_basis.
"""
import argparse
import math
import os
import subprocess
import sys
import time

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmd_scene  # noqa: E402
import test_motion  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("out")
ap.add_argument("label")
ap.add_argument("--vmd", default=test_motion.VMD)
ap.add_argument("--frames", type=int, default=0, help="motion frames after the lead-in (0 = all)")
ap.add_argument("--yaw", type=float, default=70.0)
ap.add_argument("--distance", type=float, default=0.78, help="camera distance (m); ~1.5 frames the upper body")
ap.add_argument("--lift", type=float, default=0.0, help="raise the aim point (m), e.g. 0.12 for the upper body")
ap.add_argument("--fixed", action="store_true",
                help="camera stays where it starts instead of riding the chest, e.g. --distance 3.2 --lift -0.45: "
                     "the whole body dancing")
ap.add_argument("--sdef", action="store_true",
                help="drive the PMX's own SDEF vertices with mmd_tools' SDEF driver (run Blender with -y)")
ap.add_argument("--size", type=int, default=640)
ap.add_argument("--physics", choices=("mmd", "addon"), default="mmd",
                help="mmd: mmd_scene.mmd_like (gravity 98); addon: the user's MMD Physics add-on preview (gravity 9.8)")
ap.add_argument("--kawaii", action="store_true",
                help="breasts by the MMD Physics add-on's spring-bone solver (KawaiiPhysics, Vindictus values) instead "
                     "of their rigid bodies (those are switched to follow the bones)")
ap.add_argument("--kawaii-carrier", default="", help="bone taken as the character body (e.g. 下半身); '' = none")
ap.add_argument("--kawaii-capsules", action="store_true", help="the game's arm capsules (DA_Breast)")
args = ap.parse_args(argv)
started = time.time()


def say(msg):
    print("[bust_video %s %4.0fs] %s" % (args.label, time.time() - started, msg), flush=True)


frames_dir = os.path.join(args.out, "frames_" + args.label)
os.makedirs(frames_dir, exist_ok=True)
scene, root, rig, arm = mmd_scene.load(args.pmx)
kawaii = None
if args.kawaii:
    import addon_utils
    addon_utils.enable("mmd_physics", default_set=False)
    from mmd_physics import kawaii
    say("breast bodies follow the bones: %s" % kawaii.bodies_follow_bones(arm))
rig.build()
if args.physics == "addon":
    mmd_scene.addon_like(scene, root)
else:
    mmd_scene.mmd_like(scene)
mmd_scene.add_motion(root, args.vmd, args.frames)
if kawaii is not None:
    scene.rigidbody_world.enabled = False             # the solver reads the animated pose only
    say("kawaii %s" % kawaii.bake(scene, arm, capsules=args.kawaii_capsules, carrier=args.kawaii_carrier or None))
    scene.rigidbody_world.enabled = True
scene.frame_set(1)                                   # the rest pose (the motion starts after the lead-in)

# camera: aimed at the breast bodies, carried by the first bone above the breast chain
swing = mmd_scene.breast_bones(arm, scene)
if not swing:              # --kawaii switched the breast bodies to follow the bones: aim at the same bones anyway
    swing = [pb for pb in arm.pose.bones if pb.name in ("breast_physics_02_l", "breast_physics_02_r")]
balls = [o.matrix_world.translation.copy() for o in scene.objects
         if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.bone in {pb.name for pb in swing}]
if not balls:              # no bust physics (PCF_067's steel breastplate): the breast bones are still there
    balls = [arm.matrix_world @ pb.head for pb in arm.pose.bones
             if pb.name.startswith("breast_physics_02") or pb.name.endswith("_bust_2")]
centre = sum(balls, Vector()) / len(balls) if balls else arm.matrix_world @ arm.pose.bones["上半身2"].tail
centre += Vector((0.0, 0.03, -0.04 + args.lift))
anchor = swing[0].parent if swing else arm.pose.bones["上半身2"]
while anchor.parent is not None and ("breast" in anchor.name.lower() or "bust" in anchor.name.lower()):
    anchor = anchor.parent
camera_data = bpy.data.cameras.new("chest")
camera_data.lens = 50
camera = bpy.data.objects.new("chest", camera_data)
scene.collection.objects.link(camera)
offset = Matrix.Rotation(math.radians(args.yaw), 3, "Z") @ Vector((0.0, -args.distance, 0.06))
wanted = Matrix.Translation(centre + offset) @ (-offset).to_track_quat("-Z", "Y").to_matrix().to_4x4()
if args.fixed:
    camera.matrix_world = wanted
    say("camera fixed")
else:
    camera.parent = arm
    camera.parent_type = "BONE"
    camera.parent_bone = anchor.name
    camera.matrix_parent_inverse = Matrix.Identity(4)
    camera.matrix_basis = (arm.matrix_world @ anchor.matrix @ Matrix.Translation((0, anchor.bone.length, 0))).inverted() \
        @ wanted
    say("camera on %s" % anchor.name)
scene.camera = camera

scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 16
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_x = scene.render.resolution_y = args.size
world = bpy.data.worlds.new("W")
world.use_nodes = True
tree = world.node_tree
white = next(n for n in tree.nodes if n.type == "BACKGROUND")
white.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)          # MMD look: a material shows as its texture
white.inputs[1].default_value = 0.8
backdrop = tree.nodes.new("ShaderNodeBackground")
backdrop.inputs[0].default_value = (0.42, 0.42, 0.45, 1.0)
path = tree.nodes.new("ShaderNodeLightPath")
mix = tree.nodes.new("ShaderNodeMixShader")
tree.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
tree.links.new(white.outputs[0], mix.inputs[1])
tree.links.new(backdrop.outputs[0], mix.inputs[2])
tree.links.new(mix.outputs[0], next(n for n in tree.nodes if n.type == "OUTPUT_WORLD").inputs[0])
scene.world = world
sun = bpy.data.lights.new("Key", "SUN")
sun.energy = 0.6
lamp = bpy.data.objects.new("Key", sun)
scene.collection.objects.link(lamp)
lamp.rotation_euler = [math.radians(a) for a in (50, 0, -30)]

for frame in mmd_scene.run_physics(scene):
    if frame % 120 == 0:
        say("simulated frame %d" % frame)
with bpy.context.temp_override(scene=scene, point_cache=scene.rigidbody_world.point_cache):
    bpy.ops.ptcache.bake_from_cache()
sdef_meshes = []
if args.sdef:
    from mmd_tools.core.sdef import FnSDEF
    for obj in rig.meshes():
        if FnSDEF.has_sdef_data(obj) and FnSDEF.bind(obj, bulk_update=True, use_skip=False):
            sdef_meshes.append(obj)
    say("SDEF bound on %d mesh(es)" % len(sdef_meshes))
for frame in range(scene.frame_start, scene.frame_end + 1):
    scene.frame_set(frame)
    if sdef_meshes:                                  # the driver may not run in a background render
        for obj in sdef_meshes:
            key = obj.data.shape_keys.key_blocks[FnSDEF.SHAPEKEY_NAME]
            FnSDEF.driver_function(key, obj.name, bulk_update=True, use_skip=False, use_scale=False)
            key.value = 1.0
        bpy.context.view_layer.update()
    scene.render.filepath = os.path.join(frames_dir, "%04d.png" % frame)
    bpy.ops.render.render(write_still=True)
    if frame % 60 == 0:
        say("rendered frame %d" % frame)
mp4 = os.path.join(args.out, "chest_%s.mp4" % args.label)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", os.path.join(frames_dir, "%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4], check=True)
say("BUST_VIDEO_DONE %s" % mp4)
