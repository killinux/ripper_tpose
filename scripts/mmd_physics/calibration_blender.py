"""What Blender predicts for the MMD physics calibration model, per physics rate.

    blender --background --python calibration_blender.py -- <calibration.pmx> <out_dir> [substeps,...] [gravity]

Imports the model the way render_pmx_dance.py does (mmd_tools, scale 0.08,
physics built, joints converted by mmd_like.py), simulates 3 seconds at 30 fps
with each ``substeps`` value (default 2,4,10 = 60 / 120 / 300 Hz) and prints one
``CALIBRATION=`` line per rate: how far the free square has fallen after 0.5 s
and 1 s, and the angle each sprung arm settles at below horizontal.  A still of
the last frame, framed like MMD's default camera, goes to
``<out_dir>/calibration_<hz>hz.png`` for a side-by-side with an MMD screenshot.
"""
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmd_like import mmd_like_physics  # noqa: E402

SCALE = 0.08


def run(pmx, out_dir, substeps, gravity):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    bpy.ops.mmd_tools.import_model(filepath=pmx, scale=SCALE, types={"MESH", "ARMATURE", "PHYSICS"})
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    root = arm
    while root.parent:
        root = root.parent
    from mmd_tools.core.model import Model
    Model(root).build()
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 1, 91
    mmd_like_physics(scene, SCALE, gravity, substeps)
    world = scene.rigidbody_world
    world.enabled = True
    world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end

    rigids = {o.mmd_rigid.name_j: o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY"}
    joints = sorted((o for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT"),
                    key=lambda o: o.mmd_joint.name_j)
    fall = rigids["落下"]
    fall_start = fall.matrix_world.translation.z
    arms = []
    for joint in joints:
        ball = joint.rigid_body_constraint.object2
        arms.append((joint.mmd_joint.name_j, joint.matrix_world.translation.copy(), ball))
    drop, angles = {}, {name: [] for name, _, _ in arms}
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        t = (frame - scene.frame_start) / 30.0
        if abs(t - 0.5) < 1e-6 or abs(t - 1.0) < 1e-6:
            drop["%.1fs" % t] = round((fall_start - fall.matrix_world.translation.z) / SCALE, 2)
        for name, pivot, ball in arms:
            d = ball.matrix_world.translation - pivot
            angles[name].append(math.degrees(math.atan2(-d.z, d.x)))
    settled = {name: round(sum(v[-15:]) / 15, 1) for name, v in angles.items()}

    camera_data = bpy.data.cameras.new("mmd_default")
    camera_data.sensor_fit = "VERTICAL"
    camera_data.angle_y = math.radians(30.0)
    camera = bpy.data.objects.new("mmd_default", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0.0, -45.0 * SCALE, 10.0 * SCALE)
    camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    worldsky = bpy.data.worlds.new("sky")
    worldsky.use_nodes = True
    background = [n for n in worldsky.node_tree.nodes if n.type == "BACKGROUND"][0]
    background.inputs[0].default_value = (0.3, 0.3, 0.33, 1.0)
    background.inputs[1].default_value = 2.0
    scene.world = worldsky
    scene.render.filepath = os.path.join(out_dir, "calibration_%dhz.png" % (30 * substeps))
    bpy.ops.render.render(write_still=True)
    return {"hz": 30 * substeps, "gravity": gravity, "fall_units": drop, "arm_deg_below_horizontal": settled}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    pmx, out_dir = args[0], args[1]
    rates = [int(v) for v in args[2].split(",")] if len(args) > 2 else [2, 4, 10]
    gravity = float(args[3]) if len(args) > 3 else 98.0
    os.makedirs(out_dir, exist_ok=True)
    for substeps in rates:
        print("CALIBRATION=" + json.dumps(run(pmx, out_dir, substeps, gravity), ensure_ascii=False))


if __name__ == "__main__":
    main()
