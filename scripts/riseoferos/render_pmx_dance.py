"""Render a dance preview for an exported PMX: import model + VMD, write an mp4.

Blender-side worker for ``render_pmx_dance.ps1``.  Kept in the repo rather than
improvised per session because a demo video is the only place the rig defects
show at all, and a video left over from an earlier export is worse than none:
two "the knee is wrong" reports turned out to be stale mp4s beside a PMX that
had already been fixed.

Usage:
  blender --background --python render_pmx_dance.py -- \
      <in.pmx> <in.vmd> <bgm.wav|-> <out.mp4> [frames] [full|chest|chest:<deg>] \
      [blender|mmd|mmd:<gravity>[:<substeps>]]

``frames`` caps the animation (0 = the whole motion).  A ``.blend`` is saved
beside the mp4 so a still can be re-rendered from the exact same scene.
``chest`` swaps the whole-body camera for a close-up that rides the upper body
(parented to 上半身3, three-quarter front), so the torso holds still on screen
and whatever moves is the breast physics, not the dance.  ``chest:<deg>`` turns
that camera round the body: 28 is the default three-quarter front, 90 the
model's left side, where a bounce shows as the silhouette moving.

The worker prints ``physics: N rigid bodies, M bones driven by dynamic ones``;
M is the number that proves the cloth is simulated rather than parented.  The
simulation is baked before rendering (``physics baked: frames a-b``); an
unbaked animation render shows physics the model does not have.

The last argument picks how the joints are simulated.  ``blender`` (default)
keeps what mmd_tools builds; ``mmd`` makes the joints behave the way MMD's own
Bullet does (scripts/mmd_physics/mmd_like.py), ``mmd:<gravity>`` sets the
gravity in model units/s^2 (default 98) and ``mmd:<gravity>:<substeps>`` the
physics steps per frame (the spring strength depends on it).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mmd_physics"))
from mmd_like import mmd_like_physics  # noqa: E402

# mmd_tools exports at 12.5, so importing at 0.08 puts the model back in metres.
SCALE = 0.08
# mmd_tools keys the rest pose first and puts VMD frame 0 at scene frame
# MARGIN + 1.  With no lead-in the model jumps from the rest pose into the first
# dance pose in one frame and physics flings every chain (a fringe flipped over,
# a ponytail thrown), which reads as a model defect.  scripts/stellarblade found
# it first; 30 frames is what it uses.  The music starts with VMD frame 0.
MARGIN = 30


def chest_camera(scene, arm, yaw_deg=28.0):
    """A close-up camera parented to 上半身3 at chest height, ``yaw_deg`` round
    from the front towards the model's left (28 = three-quarter front)."""
    bones = {pb.mmd_bone.name_j or pb.name: pb for pb in arm.pose.bones}
    anchor = bones.get("上半身3") or bones.get("上半身2")
    if anchor is None:
        raise SystemExit("no 上半身3/上半身2 bone for the chest camera")
    heads = [arm.matrix_world @ bones[n].head for n in ("左胸", "右胸") if n in bones]
    target = (sum(heads, Vector()) / len(heads)) if heads else arm.matrix_world @ anchor.head
    target = target + Vector((0.0, -0.08, -0.02))           # the model faces -Y
    yaw = math.radians(yaw_deg)
    offset = Matrix.Rotation(yaw, 3, "Z") @ Vector((0.0, -0.62, 0.06))
    camera_data = bpy.data.cameras.new("chest_cam")
    camera_data.lens = 50
    camera = bpy.data.objects.new("chest_cam", camera_data)
    scene.collection.objects.link(camera)
    direction = target - (target + offset)
    camera.matrix_world = Matrix.Translation(target + offset) @ \
        direction.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    world = camera.matrix_world.copy()
    camera.parent = arm
    camera.parent_type = "BONE"
    camera.parent_bone = anchor.name
    camera.matrix_world = world
    return camera


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) < 4:
        raise SystemExit("usage: <in.pmx> <in.vmd> <bgm|-> <out.mp4> [frames] "
                         "[full|chest|chest:<deg>] [blender|mmd|mmd:<gravity>[:<substeps>]]")
    pmx_path, vmd_path, bgm_path, out_mp4 = argv[:4]
    limit = int(argv[4]) if len(argv) > 4 else 0
    view = argv[5] if len(argv) > 5 else "full"
    physics = argv[6] if len(argv) > 6 else "blender"

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    # PHYSICS matters: without it the rigid bodies and joints are not imported at
    # all and every skirt, cape and tentacle simply rides its parent bone.  A
    # preview rendered that way cannot show cloth working *or* exploding, which
    # is exactly what a preview is for.
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=SCALE,
                                   types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"})
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    root = arm
    while root.parent:
        root = root.parent

    from mmd_tools.core.model import Model

    rig = Model(root)
    # Importing PHYSICS only creates the rigid body and joint objects.  Bullet
    # moves those, but no bone reads them until Model.build() (the "Build"
    # button of the physics panel) adds the mmd_tools_rigid_track constraints,
    # so without this every cloth chain still rides its parent bone while a
    # perfectly good simulation runs beside it, unseen: b14's metre-long sleeve
    # stuck out of the forearm like a plank.  Build in the rest pose, before
    # the motion is applied.
    rig.build()
    # Without the morph slider the VMD's expression keys drive nothing, and the
    # blinks are the easiest way to tell a live face from a frozen one.
    rig.morph_slider.create()
    rig.morph_slider.bind()

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if obj.type in ("ARMATURE", "MESH", "EMPTY"):
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.import_vmd(filepath=vmd_path, scale=SCALE, margin=MARGIN,
                                 bone_mapper="PMX", update_scene_settings=True)

    scene = bpy.context.scene
    if limit:
        scene.frame_end = min(scene.frame_end, scene.frame_start + limit)
    print("VMD frames %d-%d at %d fps" % (scene.frame_start, scene.frame_end,
                                          scene.render.fps))
    if physics.startswith("mmd"):
        parts = physics.split(":")
        gravity = float(parts[1]) if len(parts) > 1 and parts[1] else 98.0
        substeps = int(parts[2]) if len(parts) > 2 else None
        converted = mmd_like_physics(scene, SCALE, gravity, substeps)
        print("physics: MMD-like joints (%d converted), gravity %.1f u/s^2 = %.2f m/s^2, %s substeps"
              % (converted, gravity, gravity * SCALE, substeps or "default"))

    # Bullet only steps while the rigid body world is on and the frame is inside
    # its cache range.  The cache is baked below, before the render: see there.
    world = scene.rigidbody_world
    if world is not None:
        world.enabled = True
        world.point_cache.frame_start = scene.frame_start
        world.point_cache.frame_end = scene.frame_end
        bound = sum(1 for bone in arm.pose.bones
                    if "mmd_tools_rigid_track" in bone.constraints)
        print("physics: %d rigid bodies, %d bones driven by dynamic ones"
              % (len(world.collection.objects) if world.collection else 0, bound))
    else:
        print("physics: no rigid body world in this model")

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("dance_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    background.inputs[1].default_value = 1.35
    scene.world = world
    for name, energy, rotation in (("key", 3.2, (0.95, 0.0, 0.65)),
                                   ("fill", 1.1, (1.15, 0.0, -2.2))):
        data = bpy.data.lights.new(name, type="SUN")
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation

    floor_mesh = bpy.data.meshes.new("floor")
    floor_mesh.from_pydata([(-4, -4, 0), (4, -4, 0), (4, 4, 0), (-4, 4, 0)],
                           [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("floor", floor_mesh)
    scene.collection.objects.link(floor)
    floor_material = bpy.data.materials.new("floor")
    floor_material.diffuse_color = (0.28, 0.28, 0.30, 1.0)
    floor_mesh.materials.append(floor_material)

    if view.startswith("chest"):
        yaw = float(view.split(":", 1)[1]) if ":" in view else 28.0
        scene.frame_set(scene.frame_start)              # rest pose: place the camera
        scene.camera = chest_camera(scene, arm, yaw)
        scene.render.resolution_x, scene.render.resolution_y = 720, 720
    else:
        camera_data = bpy.data.cameras.new("cam")
        camera_data.lens = 50
        camera = bpy.data.objects.new("cam", camera_data)
        scene.collection.objects.link(camera)
        camera.location = (0.0, -4.2, 0.95)
        camera.rotation_euler = (math.radians(90), 0.0, 0.0)
        scene.camera = camera
        scene.render.resolution_x, scene.render.resolution_y = 720, 1080
    scene.eevee.taa_render_samples = 16

    if bgm_path != "-" and os.path.isfile(bgm_path):
        scene.sequence_editor_create()
        scene.sequence_editor.sequences.new_sound("BGM", bgm_path, 1, MARGIN + 1)

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.filepath = out_mp4

    # Bake the simulation, then render.  Rendering the animation on a live cache
    # does NOT replay what stepping the frames does: on g05 the bodies the render
    # used were not the simulated ones, so every mode-1 bone was dragged away from
    # its body - breasts stretched back toward the rest pose, pendants and sleeve
    # ribbons thrown across the chest, the costume torn open - in every frame of
    # the mp4, while the same frames stepped with frame_set and rendered as stills
    # were clean.  Baked, the render reads exactly the stepped simulation (and the
    # saved .blend replays it).  Previews made before 2026-09-26 did not bake.
    if scene.rigidbody_world is not None:
        cache = scene.rigidbody_world.point_cache
        with bpy.context.temp_override(scene=scene, point_cache=cache):
            bpy.ops.ptcache.bake(bake=True)
        print("physics baked: frames %d-%d" % (cache.frame_start, cache.frame_end))

    out_blend = os.path.splitext(out_mp4)[0] + ".blend"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend),
                                check_existing=False)
    bpy.ops.render.render(animation=True)
    print("ROE_DANCE_DONE %s" % out_mp4)


if __name__ == "__main__":
    main()
