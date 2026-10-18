"""Front, back and head renders of a look's .blend with the camera and lights build_npc_blend.py saved in it.

    blender -b <look>.blend --python render_look.py -- <out prefix>     -> <prefix>.png, <prefix>_back.png, <prefix>_face.png
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_npc_blend as b  # noqa: E402

prefix = sys.argv[sys.argv.index("--") + 1]
# a self-contained folder: every file the .blend uses must sit under its own folder
home = os.path.normcase(os.path.dirname(bpy.data.filepath))
for p in bpy.utils.blend_paths(absolute=True, packed=False, local=False):
    if not os.path.normcase(os.path.normpath(p)).startswith(home + os.sep):
        print("SB_NPC_OUTSIDE=" + p)
scene = bpy.context.scene
cam = scene.camera
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE" and o.parent is None), None)
b.shoot(scene, cam, meshes, prefix + ".png", (1.0, -0.3, 0.06))
b.shoot(scene, cam, meshes, prefix + "_back.png", (-1.0, 0.3, 0.06))
head = b.head_point(arm)
if head is not None:
    b.shoot(scene, cam, meshes, prefix + "_face.png", (1.0, -0.25, 0.02), head=head)
