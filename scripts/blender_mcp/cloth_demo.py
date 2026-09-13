"""Runs INSIDE Blender (send it with mcp_exec.py): load a prepared mmd_tools
scene, build cloth physics with the mmd_cloth_physics panel operators, frame the
model and start playback so the person at the screen sees the cloth move.

    python scripts/blender_mcp/mcp_exec.py scripts/blender_mcp/cloth_demo.py 600

Edit BLEND below for another model.  The scene is expected to hold one mmd_tools
model whose dynamic physics has been stripped (the add-on's "Strip dynamic
physics" does that) and, optionally, a VMD already imported.

Everything that needs a window - opening a file, view3d operators, playback,
and the add-on's own operators (they read context.active_object) - runs under a
temp_override of the first window's 3D view, because blender-mcp executes this
code from a bpy.app.timers callback, which has no window context of its own.
"""
import bpy

BLEND = r"D:\roe_exports\b14\blend\pmx\pc_b14_outfit1_hd_clothlab.blend"

for module in ("mmd_tools", "mmd_cloth_physics"):
    if module not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=module)

window = bpy.context.window_manager.windows[0]
with bpy.context.temp_override(window=window, screen=window.screen):
    bpy.ops.wm.open_mainfile(filepath=BLEND, load_ui=False)   # keep the user's layout
print("opened", bpy.data.filepath)

scene = bpy.context.scene
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.parent == root)

with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                               scene=scene):
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm

    print("analyze:", bpy.ops.mmd_cloth.analyze(), scene.mmd_cloth.report)
    for item in scene.mmd_cloth.garments:
        print("   %-28s -> %-8s %s" % (item.name, item.preset, item.summary))
    print("build:", bpy.ops.mmd_cloth.build(), scene.mmd_cloth.report)
    print("preview:", bpy.ops.mmd_cloth.preview(), scene.mmd_cloth.report)

    # a clean picture: no rigid body / joint / bone helpers, textured solid
    # shading, front view framed on the meshes
    root.mmd_root.show_rigid_bodies = False
    root.mmd_root.show_joints = False
    root.mmd_root.show_armature = False
    space = area.spaces.active
    space.shading.type = "SOLID"
    space.shading.color_type = "TEXTURE"
    space.shading.light = "STUDIO"
    space.overlay.show_relationship_lines = False
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.find_armature() == arm:
            obj.select_set(True)
    bpy.ops.view3d.view_axis(type="FRONT")
    bpy.ops.view3d.view_selected()
    bpy.ops.object.select_all(action="DESELECT")

    # the rigid body cache only advances on consecutive frames: never let the
    # player drop frames or the cloth freezes while the body keeps dancing
    scene.sync_mode = "NONE"
    scene.frame_set(scene.frame_start)
    bpy.ops.screen.animation_play()

print("playing:", window.screen.is_animation_playing,
      "| rigid body world:", scene.rigidbody_world.enabled,
      "| cache %d-%d" % (scene.rigidbody_world.point_cache.frame_start,
                         scene.rigidbody_world.point_cache.frame_end))
