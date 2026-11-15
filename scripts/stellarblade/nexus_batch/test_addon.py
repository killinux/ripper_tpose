"""stellarblade_game_materials add-on (real operators) on a PMX (10-18 Reika test + a face shot): report, missing images, renders game / MMD,
re-export in both modes, remove.
    blender -b --factory-startup --python test_reika_addon.py -- <pmx> <out dir> [--no-render]"""
import hashlib
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
PMX, OUT = argv[0], os.path.abspath(argv[1])
RENDER = "--no-render" not in argv
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
import addon_utils  # noqa: E402

addon_utils.enable("mmd_tools", default_set=True)
import stellarblade_game_materials as addon  # noqa: E402

addon.register()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
bpy.ops.mmd_tools.import_model(filepath=PMX, scale=0.08, types={"MESH", "ARMATURE", "MORPHS"}, log_level="ERROR")
scene = bpy.context.scene
root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
bpy.context.view_layer.objects.active = root
root.select_set(True)
_r, meshes = addon.model_of(bpy.context)
res = bpy.ops.sb_gm.apply()
print("APPLY", res, scene.sb_gm.report)
core = addon.core()
hq = core.hq_materials_of(meshes)
allm = core.materials_of(meshes)
print("upgraded %d of %d; not upgraded: %s" % (len(hq), len(allm), sorted(m.name for m in allm if m not in hq)))
for m in sorted(hq, key=lambda m: m.name):
    theirs, mine = core.outputs(m)
    imgs = sorted({n.image.name for n in m.node_tree.nodes if n.name.startswith("sbhq_") and getattr(n, "image", None)})
    print("  %-28s active=%s blend=%s nodes=%d imgs=%s" % (m.name, "game" if mine and mine.is_active_output else "mmd",
                                                       m.blend_method, len(m.node_tree.nodes), imgs))
missing = sorted(i.name for i in bpy.data.images if i.source == "FILE" and i.filepath and
                 not os.path.exists(bpy.path.abspath(i.filepath)))
print("MISSING_IMAGES", missing)
print("LIBRARIES", [l.filepath for l in bpy.data.libraries])

if RENDER:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 64
    scene.view_settings.view_transform = "Filmic"
    zs = [(m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box]
    top, bot = max(zs), min(zs)
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.type = "ORTHO"
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    if scene.world is None:
        scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    if "--world" in argv:                       # a light grey surrounding instead of the default near-black one
        g = float(argv[argv.index("--world") + 1])
        scene.world.node_tree.nodes["Background"].inputs[0].default_value = (g, g, g, 1.0)
        scene.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    def shot(name, centre_z, scale, res, x=0.0):
        cam.location = Vector((x, -6.0, centre_z))
        cam.rotation_euler = (math.radians(90), 0, 0)
        cam_data.ortho_scale = scale
        scene.render.resolution_x, scene.render.resolution_y = res
        scene.render.filepath = os.path.join(OUT, name + ".png")
        bpy.ops.render.render(write_still=True)

    h = top - bot
    for mode in ("game", "mmd"):
        scene.sb_gm.mode = mode
        shot("%s_full" % mode, bot + h * 0.5, h * 1.08, (800, 1150))
        shot("%s_chest" % mode, bot + h * 0.66, h * 0.36, (900, 900))
        shot("%s_hips" % mode, bot + h * 0.45, h * 0.30, (900, 900))
        shot("%s_face" % mode, bot + h * 0.925, h * 0.14, (900, 900))
    scene.sb_gm.mode = "game"

bpy.ops.object.select_all(action="DESELECT")
root.select_set(True)
bpy.context.view_layer.objects.active = root
digests = {}
for mode in ("game", "mmd"):
    scene.sb_gm.mode = mode
    path = os.path.join(OUT, "reexport_%s.pmx" % mode)
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=False, log_level="ERROR")
    digests[mode] = hashlib.md5(open(path, "rb").read()).hexdigest()
print("REEXPORT", digests, "identical" if digests["game"] == digests["mmd"] else "DIFFERENT")
bpy.ops.sb_gm.remove()
left = [n.name for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes if n.name.startswith("sbhq_")]
print("REMOVED", scene.sb_gm.report, "nodes left:", len(left))
print("TEST_DONE", flush=True)
