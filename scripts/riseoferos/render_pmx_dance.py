"""Render a dance preview for an exported PMX: import model + VMD, write an mp4.

Blender-side worker for ``render_pmx_dance.ps1``.  Kept in the repo rather than
improvised per session because a demo video is the only place the rig defects
show at all, and a video left over from an earlier export is worse than none:
two "the knee is wrong" reports turned out to be stale mp4s beside a PMX that
had already been fixed.

Usage:
  blender --background --python render_pmx_dance.py -- \
      <in.pmx> <in.vmd> <bgm.wav|-> <out.mp4> [frames]

``frames`` caps the animation (0 = the whole motion).  A ``.blend`` is saved
beside the mp4 so a still can be re-rendered from the exact same scene.

The worker prints ``physics: N rigid bodies, M bones driven by dynamic ones``;
M is the number that proves the cloth is simulated rather than parented.
"""
import math
import os
import sys

import bpy

# mmd_tools exports at 12.5, so importing at 0.08 puts the model back in metres.
SCALE = 0.08


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) < 4:
        raise SystemExit("usage: <in.pmx> <in.vmd> <bgm|-> <out.mp4> [frames]")
    pmx_path, vmd_path, bgm_path, out_mp4 = argv[:4]
    limit = int(argv[4]) if len(argv) > 4 else 0

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
    bpy.ops.mmd_tools.import_vmd(filepath=vmd_path, scale=SCALE, margin=0,
                                 bone_mapper="PMX", update_scene_settings=True)

    scene = bpy.context.scene
    if limit:
        scene.frame_end = min(scene.frame_end, scene.frame_start + limit)
    print("VMD frames %d-%d at %d fps" % (scene.frame_start, scene.frame_end,
                                          scene.render.fps))

    # Bullet only steps while the rigid body world is on and the frame is inside
    # its cache range; rendering an animation walks the frames in order, which is
    # what the solver needs.
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
        scene.sequence_editor.sequences.new_sound("BGM", bgm_path, 1, 1)

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.filepath = out_mp4

    out_blend = os.path.splitext(out_mp4)[0] + ".blend"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend),
                                check_existing=False)
    bpy.ops.render.render(animation=True)
    print("ROE_DANCE_DONE %s" % out_mp4)


if __name__ == "__main__":
    main()
