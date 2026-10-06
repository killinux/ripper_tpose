"""Elbow close-up of a PMX dancing (mmd_scene: MMD-like physics): PNG frames + an mp4, for judging arm weights.

  blender -b --factory-startup --python arm_video.py -- <model.pmx> <out dir> <label>
          [--vmd <motion.vmd>] [--frames 0] [--side l|r] [--size 640] [--sdef]

The camera rides the upper arm (腕) and looks at the elbow from in front and a little outside, 0.6 m off, so the
upper arm holds still on screen and what moves is the elbow bending and the forearm twisting.
Same lighting and output as bust_video.py (frames_<label>/####.png, arm_<label>.mp4); bust_grid.py puts several
clips side by side.  ``--vmd`` defaults to test_motion.VMD, ``--frames`` 0 = the whole motion.
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
ap.add_argument("--side", choices=("l", "r"), default="l")
ap.add_argument("--size", type=int, default=640)
ap.add_argument("--sdef", action="store_true",
                help="drive the PMX's own SDEF vertices with mmd_tools' SDEF driver (MMD does SDEF; Blender only when bound)")
args = ap.parse_args(argv)
started = time.time()


def say(msg):
    print("[arm_video %s %4.0fs] %s" % (args.label, time.time() - started, msg), flush=True)


frames_dir = os.path.join(args.out, "frames_" + args.label)
os.makedirs(frames_dir, exist_ok=True)
scene, root, rig, arm = mmd_scene.load(args.pmx)
rig.build()
mmd_scene.mmd_like(scene)
mmd_scene.add_motion(root, args.vmd, args.frames)
scene.frame_set(1)                                   # the rest pose (the motion starts after the lead-in)
sdef_meshes = []
if args.sdef:
    from mmd_tools.core.sdef import FnSDEF
    for obj in rig.meshes():
        if FnSDEF.has_sdef_data(obj) and FnSDEF.bind(obj, bulk_update=True, use_skip=False):
            sdef_meshes.append(obj)
    say("SDEF bound on %d mesh(es)" % len(sdef_meshes))


def sdef_update():
    """Recompute the SDEF positions for the current pose (the driver may not run in a background render)."""
    from mmd_tools.core.sdef import FnSDEF
    for obj in sdef_meshes:
        key = obj.data.shape_keys.key_blocks[FnSDEF.SHAPEKEY_NAME]
        FnSDEF.driver_function(key, obj.name, bulk_update=True, use_skip=False, use_scale=False)
        key.value = 1.0

suffix = ".L" if args.side == "l" else ".R"
upper = arm.pose.bones["腕" + suffix]
mw = arm.matrix_world
elbow = mw @ arm.pose.bones["ひじ" + suffix].head
along = (elbow - mw @ upper.head).normalized()
out_dir = Vector((1.0 if args.side == "l" else -1.0, 0.0, 0.0))
side = (out_dir - along * out_dir.dot(along)).normalized()          # away from the body, square to the arm
front = along.cross(side).normalized()
if front.y > 0:                                                     # the model faces -Y
    front = -front
view = (side * 0.55 + front * 0.85).normalized()                    # in front and a little outside
centre = elbow + along * 0.05
camera_data = bpy.data.cameras.new("arm")
camera_data.lens = 50
camera = bpy.data.objects.new("arm", camera_data)
scene.collection.objects.link(camera)
wanted = Matrix.Translation(centre + view * 0.6) @ (-view).to_track_quat("-Z", "Y").to_matrix().to_4x4()
camera.parent = arm
camera.parent_type = "BONE"
camera.parent_bone = upper.name
camera.matrix_parent_inverse = Matrix.Identity(4)
camera.matrix_basis = (mw @ upper.matrix @ Matrix.Translation((0, upper.bone.length, 0))).inverted() @ wanted
scene.camera = camera
say("camera on %s" % upper.name)

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
for frame in range(scene.frame_start, scene.frame_end + 1):
    scene.frame_set(frame)
    if sdef_meshes:
        sdef_update()
        bpy.context.view_layer.update()
    scene.render.filepath = os.path.join(frames_dir, "%04d.png" % frame)
    bpy.ops.render.render(write_still=True)
    if frame % 60 == 0:
        say("rendered frame %d" % frame)
mp4 = os.path.join(args.out, "arm_%s.mp4" % args.label)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", os.path.join(frames_dir, "%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4], check=True)
say("ARM_VIDEO_DONE %s" % mp4)
