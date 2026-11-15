"""Blender 4.3+ (background) with RE Mesh Editor (NSACloud, GPLv3; kept outside the repo in E:\\tools\\re_mesh_editor):
RE Engine .mesh files (+ their .mdf2 / .tex) -> one FBX with a shared armature + a JSON of every material's texture
bindings, for build_blend.py (Blender 3.6) to rebuild.

    set BLENDER_USER_SCRIPTS=E:\\tools\\re_mesh_editor\\scripts
    blender -b --python import_re_mesh.py -- --out-fbx X.fbx --out-json X.json --mesh <body .mesh.*> [--mesh <face ...>]

* The add-on is enabled for this session only (BLENDER_USER_SCRIPTS points at the tools folder; preferences are not
  saved).  Its "show console" option is switched off: bpy.ops.wm.console_toggle crashes Blender in background mode.
* The first mesh brings the armature, the others merge into it (mergeArmature).
* Submeshes of under 10 vertices are dropped: mods hide the gear they remove by collapsing it to one triangle.
* reloadCachedTextures: the add-on caches converted textures by their GAME path, which every mod of the same
  character shares - without it the second Jill mod got the first one's blue body textures.
* Bindings come from the .mdf2 next to each mesh (the add-on's own reader); a binding resolves to the add-on's texture
  cache (.dds it converted from the mod's .tex) or stays unresolved (the texture is in the game's paks, not the mod).
"""
import importlib
import json
import os
import sys

import addon_utils
import bpy

ADDON = "RE-Mesh-Editor-main"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def args(flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


meshes = args("--mesh")
out_fbx, out_json = args("--out-fbx")[0], args("--out-json")[0]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.use_preferences_save = False
if not addon_utils.enable(ADDON, default_set=True):
    raise SystemExit("RE Mesh Editor not found - set BLENDER_USER_SCRIPTS to E:\\tools\\re_mesh_editor\\scripts")
prefs = bpy.context.preferences.addons[ADDON].preferences
prefs.showConsole = False
addon_dir = os.path.dirname(importlib.import_module(ADDON).__file__)
cache_dir = os.path.join(addon_dir, "TextureCache")
mdfmod = importlib.import_module(ADDON + ".modules.mdf.file_re_mdf")

report = {"meshes": [], "dropped": [], "materials": {}}
arm_name = ""
for path in meshes:
    before = set(bpy.data.objects)
    r = bpy.ops.re_mesh.importfile(files=[{"name": os.path.basename(path)}], directory=os.path.dirname(path),
                                   loadMaterials=True, loadMDFData=False, importShadowMeshes=False,
                                   reloadCachedTextures=True,
                                   importOcclusionMeshes=False, createCollections=False, importAllLODs=False,
                                   rotate90=True, mergeArmature=arm_name)
    new = [o for o in bpy.data.objects if o not in before]
    arms = [o for o in new if o.type == "ARMATURE"]
    if arms and not arm_name:
        arm_name = arms[0].data.name
    report["meshes"].append({"file": path, "result": list(r), "objects": [o.name for o in new]})
    # the material file of this mesh: <stem>.mdf2.* beside it
    stem = os.path.basename(path).split(".")[0]
    mdfs = [f for f in os.listdir(os.path.dirname(path)) if f.lower().startswith(stem.lower() + ".mdf2.")]
    for f in mdfs:
        mdf = mdfmod.readMDF(os.path.join(os.path.dirname(path), f))
        for mat in mdf.materialList:
            name = mat.materialName
            binds = {}
            for t in mat.textureList:
                rel = t.texturePath.replace("\\", "/")
                dds = os.path.join(cache_dir, *os.path.splitext(rel)[0].split("/")) + ".dds"
                binds[t.textureType] = {"path": rel, "dds": dds if os.path.isfile(dds) else None}
            report["materials"].setdefault(name, {"master": mat.mmtrPath, "textures": binds, "mdf": f})

for o in list(bpy.data.objects):
    if o.type == "MESH" and len(o.data.vertices) < 10:
        report["dropped"].append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
report["armature"] = arm.name if arm else None
report["objects"] = [{"name": o.name, "vertices": len(o.data.vertices),
                      "materials": [s.material.name for s in o.material_slots if s.material]}
                     for o in bpy.data.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={"ARMATURE", "MESH"},
                         add_leaf_bones=False, bake_anim=False, use_mesh_modifiers=False, mesh_smooth_type="OFF",
                         use_tspace=False, primary_bone_axis="Y", secondary_bone_axis="X", path_mode="STRIP",
                         axis_forward="-Y", axis_up="Z", apply_unit_scale=True, global_scale=1.0)
with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=1, ensure_ascii=False)
print("RE_IMPORT_DONE=" + json.dumps({"fbx": out_fbx, "objects": len(report["objects"]),
                                      "dropped": len(report["dropped"]), "materials": len(report["materials"])}))
