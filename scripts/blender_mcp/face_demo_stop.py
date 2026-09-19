"""Runs INSIDE Blender: stop the playback started by face_demo.py, unbind the
morph slider (so the Face Morphs panel's Preview drives the bones again) and
put the face back to rest.  The demo scene is kept.

    python scripts/blender_mcp/mcp_exec.py scripts/blender_mcp/face_demo_stop.py
"""
import sys

import bpy

scene = bpy.data.scenes.get("face_demo") or bpy.context.scene
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")

with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                               scene=scene):
    if window.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=False)
    from mmd_tools.core.model import Model

    rig = Model(root)
    arm = rig.armature()
    rig.morph_slider.unbind()
    scene.frame_set(scene.frame_start)
    sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
    from mmd_face_morphs import build

    build.reset_pose(root, arm)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    root.mmd_root.show_armature = True
print("stopped | frame", scene.frame_current, "| slider unbound; the panel's Preview works now")
