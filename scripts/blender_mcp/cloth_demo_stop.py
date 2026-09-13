"""Runs INSIDE Blender: stop the playback started by cloth_demo.py and put the
model back into its export state (mmd_tools Clean, rigid bodies at their bind
positions), then show the helpers again.

    python scripts/blender_mcp/mcp_exec.py scripts/blender_mcp/cloth_demo_stop.py
"""
import bpy

scene = bpy.context.scene
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.parent == root)

with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                               scene=scene):
    if window.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=True)
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    print("stop preview:", bpy.ops.mmd_cloth.stop_preview(), scene.mmd_cloth.report)
    root.mmd_root.show_rigid_bodies = True
    root.mmd_root.show_joints = True
    root.mmd_root.show_armature = True
print("frame", scene.frame_current, "| built:", root.mmd_root.is_built)
