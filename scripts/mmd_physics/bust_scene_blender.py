"""A .blend that plays a PMX's physics in Blender the way MMD would - open it and press play (Space).

bust_variants.py runs this once per breast setting.  The scene: the PMX imported by mmd_tools with its physics, a
dance VMD (+ its music, 1 s lead-in), the joints converted by mmd_like.py (MMD's spring type, no extra damping,
springs at the import scale, MMD's gravity), bodies the PMX lets touch nothing kept out of every collision (mmd_tools
would let a passing elbow knock the breasts), SDEF bound (MMD always applies it), lights and a floor, a chest camera
that follows the upper body and a full-body one, the rigid-body cache baked into the file.  The file opens in the 3D
view looking through the chest camera in textured solid shading, bones hidden, playback synced to the music.
Texture paths are saved relative to the .blend.  SDEF elbows are a Python driver: Blender asks to allow scripts
(without them the elbows bend linearly; nothing else changes).

    blender -b --factory-startup --python bust_scene_blender.py -- <pmx> <vmd> <wav|-> <out.blend>
        [--video out.mp4] [--view chest|full] [--substeps N]
--video renders the animation through the chosen camera (720 x 720 chest / 720 x 1080 full, EEVEE) after saving.
--substeps: physics steps per frame (Blender's 10 by default).  2 = 60 Hz, MMD's step, is not smoother here: on
PCF_005's no-spring breast it trades the hard landings on the joint limit for steady small jitter, and the joint
stretches up to 1 cm.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mmd_like import mmd_like_physics  # noqa: E402

SCALE = 0.08            # mmd_tools import scale: 1 PMX unit = 8 cm
MARGIN = 30             # frames of lead-in before the dance (the physics settles)
GRAVITY = 98.0          # MMD's, in model units / s^2
BREASTS = (("左胸", "右胸"), ("breast_l", "breast_r"), ("breast_physics_01_l", "breast_physics_01_r"))


def chest_camera(scene, arm, yaw_deg=28.0):
    """A 50 mm camera on the breasts (or the upper body), 28 degrees to the side, riding 上半身3."""
    bones = {pb.mmd_bone.name_j or pb.name: pb for pb in arm.pose.bones}
    anchor = bones.get("上半身3") or bones.get("上半身2") or bones.get("上半身")
    heads = []
    for pair in BREASTS:
        heads = [arm.matrix_world @ bones[n].head for n in pair if n in bones]
        if heads:
            break
    target = (sum(heads, Vector()) / len(heads)) if heads else arm.matrix_world @ anchor.head
    target = target + Vector((0.0, -0.08, -0.02))
    offset = Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Vector((0.0, -0.62, 0.06))
    cam = bpy.data.objects.new("胸部特写", bpy.data.cameras.new("胸部特写"))
    cam.data.lens = 50
    scene.collection.objects.link(cam)
    cam.matrix_world = Matrix.Translation(target + offset) @ (-offset).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    world = cam.matrix_world.copy()
    cam.parent, cam.parent_type, cam.parent_bone = arm, "BONE", anchor.name
    cam.matrix_world = world
    return cam


def stage(scene):
    """Grey world, two suns, a floor, a full-body camera (as the ROE / Vindictus dance videos)."""
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.35
    scene.world = world
    for name, energy, rotation in (("key", 3.2, (0.95, 0.0, 0.65)), ("fill", 1.1, (1.15, 0.0, -2.2))):
        lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, type="SUN"))
        lamp.data.energy = energy
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation
    mesh = bpy.data.meshes.new("floor")
    mesh.from_pydata([(-4, -4, 0), (4, -4, 0), (4, 4, 0), (-4, 4, 0)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("floor", mesh)
    scene.collection.objects.link(floor)
    material = bpy.data.materials.new("floor")
    material.diffuse_color = (0.28, 0.28, 0.30, 1.0)
    mesh.materials.append(material)
    cam = bpy.data.objects.new("全身", bpy.data.cameras.new("全身"))
    scene.collection.objects.link(cam)
    cam.data.lens = 50
    cam.location = (0.0, -4.2, 0.95)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    return cam


def mmd_collisions(scene):
    """mmd_tools leaves every rigid body in Blender's first collision collection and turns the PMX's masked pairs off
    only for bodies that sit close together at rest, so a body the PMX lets touch nothing (the breasts) still gets hit
    by a passing elbow in Blender: on PCF_005 the elbow knocked the breast 38 degrees and 4 cm out of its joint.  Such
    bodies leave every collection (Blender then lets them pass through everything, as MMD does).  Returns (bodies
    taken out, masked pairs Blender still lets collide)."""
    bodies = [o for o in scene.objects if o.rigid_body is not None and getattr(o, "mmd_type", "") == "RIGID_BODY"]
    off = set()
    for obj in scene.objects:
        rbc = obj.rigid_body_constraint
        if rbc is not None and rbc.disable_collisions and rbc.object1 and rbc.object2:
            off.add(frozenset((rbc.object1, rbc.object2)))
    group = {o: o.mmd_rigid.collision_group_number for o in bodies}
    ignores = {o: [bool(v) for v in o.mmd_rigid.collision_group_mask] for o in bodies}
    lonely, left = [], 0
    for a in bodies:
        partners = [b for b in bodies if b is not a and not ignores[a][group[b]] and not ignores[b][group[a]]]
        if not partners:
            lonely.append(a)
    for a in lonely:
        a.rigid_body.collision_collections = [False] * 20
    alone = set(lonely)
    for i, a in enumerate(bodies):
        for b in bodies[i + 1:]:
            if a in alone or b in alone or frozenset((a, b)) in off:
                continue
            if ignores[a][group[b]] or ignores[b][group[a]]:
                left += 1
    return len(lonely), left


def viewports():
    """Every 3D view in the file: through the scene camera, textured solid, no bone overlay."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.shading.type = "SOLID"
            space.shading.color_type = "TEXTURE"
            space.overlay.show_bones = False
            space.overlay.show_relationship_lines = False


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    pmx_path, vmd_path, wav, out_blend = argv[:4]
    video = argv[argv.index("--video") + 1] if "--video" in argv else None
    view = argv[argv.index("--view") + 1] if "--view" in argv else "chest"
    substeps = int(argv[argv.index("--substeps") + 1]) if "--substeps" in argv else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True      # the SDEF driver is Python
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"})
    from mmd_tools.core.model import Model
    from mmd_tools.core.sdef import FnSDEF
    root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
    rig = Model(root)
    arm = rig.armature()
    rig.build()
    rig.morph_slider.create()
    rig.morph_slider.bind()
    for flag in ("show_rigid_bodies", "show_joints", "show_temporary_objects"):
        if hasattr(root.mmd_root, flag):
            setattr(root.mmd_root, flag, False)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if obj.type in ("ARMATURE", "MESH", "EMPTY"):
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.import_vmd(filepath=vmd_path, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                                 update_scene_settings=True)
    sdef = [m.name for m in rig.meshes() if FnSDEF.bind(m, bulk_update=True, use_skip=False)]
    scene = bpy.context.scene
    converted = mmd_like_physics(scene, SCALE, GRAVITY, substeps)
    lonely, left = mmd_collisions(scene)
    world = scene.rigidbody_world
    if world is not None:
        world.enabled = True
        world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.eevee.taa_render_samples = 16
    cam_full = stage(scene)
    if wav != "-" and os.path.isfile(wav):
        scene.sequence_editor_create()
        scene.sequence_editor.sequences.new_sound("BGM", wav, 1, MARGIN + 1)
        scene.sync_mode = "AUDIO_SYNC"                  # play at real speed with the music
    scene.frame_set(scene.frame_start)
    cam_chest = chest_camera(scene, arm)
    scene.camera = cam_chest if view == "chest" else cam_full
    if world is not None:
        with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
            bpy.ops.ptcache.bake(bake=True)
    viewports()
    scene.frame_set(scene.frame_start)
    os.makedirs(os.path.dirname(os.path.abspath(out_blend)), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend), check_existing=False)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    bodies = sum(1 for o in scene.objects if o.rigid_body is not None)
    print("BUST_SCENE=%s frames %d-%d, %d rigid bodies (%d touch nothing, as in the PMX; %d masked pairs still collide), "
          "%d joints made MMD-like, SDEF on %d meshes, camera %s" % (
              out_blend, scene.frame_start, scene.frame_end, bodies, lonely, left, converted, len(sdef),
              scene.camera.name))
    if video:
        scene.render.resolution_x, scene.render.resolution_y = (720, 720) if view == "chest" else (720, 1080)
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.audio_codec = "AAC"
        scene.render.filepath = os.path.abspath(video)
        bpy.ops.render.render(animation=True)
        print("BUST_VIDEO=" + scene.render.filepath)


if __name__ == "__main__":
    main()
