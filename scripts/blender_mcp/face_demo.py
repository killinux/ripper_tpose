"""Runs INSIDE Blender (send it with mcp_exec.py): show the face morphs live.

    python scripts/blender_mcp/mcp_exec.py scripts/blender_mcp/face_demo.py 600

In a NEW scene of the open file (whatever was open stays untouched): import
the re-exported b14_outfit1 PMX, run the Face Morphs panel (Analyze + Build,
so the sidebar shows what it found), bind mmd_tools' morph slider, load a
lipsync VMD, hang a camera off the head bone so the face stays framed while
she dances, switch the viewport to that camera and play.

Everything that needs a window runs under a temp_override of the first
window's 3D view: blender-mcp executes this from a bpy.app.timers callback,
which has no window context of its own.
"""
import sys

import bpy
from mathutils import Matrix, Vector

PMX = r"D:\roe_exports\b14\blend\pmx\pc_b14_outfit1_hd\pc_b14_outfit1_hd.pmx"
VMD = r"E:\Downloads\mmd\客官不可以2026.6.16by小王动画\适配【原神】芙宁娜.vmd"
SCALE = 0.08          # mmd_tools exports at 12.5; 0.08 brings the PMX back to metres

for module in ("mmd_tools", "mmd_face_morphs"):
    if module not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=module)

window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")

with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
    bpy.ops.scene.new(type="NEW")
    scene = bpy.context.scene
    scene.name = "face_demo"
    window.scene = scene

with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                               scene=scene):
    bpy.ops.mmd_tools.import_model(filepath=PMX, scale=SCALE,
                                   types={"MESH", "ARMATURE", "MORPHS"})
    root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
    from mmd_tools.core.model import Model

    rig = Model(root)
    arm = rig.armature()

    # the panel, so its report is on screen: Analyze + Build (rebuilds the 58
    # the PMX already carries - same numbers, but now the panel knows them)
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    print("analyze:", bpy.ops.mmd_face.analyze(), "|", scene.mmd_face.face_report)
    print("build:  ", bpy.ops.mmd_face.build(), "|", scene.mmd_face.report)
    scene.mmd_face.morph = "笑い"

    # the slider is what a VMD's expression keys drive (by morph name)
    rig.morph_slider.create()
    rig.morph_slider.bind()

    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.import_vmd(filepath=VMD, scale=SCALE, margin=0, bone_mapper="PMX",
                                 update_scene_settings=True)
    print("VMD frames %d-%d" % (scene.frame_start, scene.frame_end))

    # a camera that rides the head bone: framed on the face, following the dance
    sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
    from mmd_face_morphs import faces

    face = faces.resolve(arm)
    bones = arm.data.bones
    eyes = (bones[face.bone("eye_L")].head_local + bones[face.bone("eye_R")].head_local) * 0.5
    target = arm.matrix_world @ (eyes + Vector((0.0, 0.0, -0.55 * face.unit)))
    forward = Vector((0.0, face.front, 0.0))
    camera_data = bpy.data.cameras.new("face_cam")
    camera_data.lens = 85
    camera = bpy.data.objects.new("face_cam", camera_data)
    scene.collection.objects.link(camera)
    camera.location = target + forward * 9.5 * face.unit
    camera.rotation_euler = (1.5707963, 0.0, 0.0 if face.front < 0 else 3.1415927)
    follow = camera.constraints.new("CHILD_OF")
    follow.target = arm
    follow.subtarget = face.head
    # Set Inverse by hand: the constraint maps through the bone's pose matrix,
    # so cancelling that at rest keeps the camera where it was placed
    # against the REST matrix, not the pose at whatever frame the VMD import
    # left the scene on: the camera was placed from rest positions, so at
    # rest it must land exactly there and follow the head from there
    follow.inverse_matrix = (arm.matrix_world @ arm.data.bones[face.head].matrix_local).inverted()
    scene.camera = camera

    # a clean picture: no bone overlay, textured solid shading, camera view
    root.mmd_root.show_armature = False
    space = area.spaces.active
    space.shading.type = "SOLID"
    space.shading.color_type = "TEXTURE"
    space.shading.light = "STUDIO"
    space.overlay.show_relationship_lines = False
    space.region_3d.view_perspective = "CAMERA"
    bpy.ops.object.select_all(action="DESELECT")

    # the morph slider evaluates per frame; never let the player drop frames
    scene.sync_mode = "NONE"
    scene.frame_set(scene.frame_start)
    bpy.ops.screen.animation_play()

print("playing:", window.screen.is_animation_playing, "| scene:", scene.name,
      "| morphs:", len(root.mmd_root.bone_morphs))
