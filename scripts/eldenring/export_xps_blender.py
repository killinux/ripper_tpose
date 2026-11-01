# -*- coding: utf-8 -*-
"""Elden Ring mod .blend (build_blend.py) -> XPS (XNALara) with blender2xps, headless.

    blender -b <name>.blend --factory-startup --python export_xps_blender.py -- --out <dir> [--name N]
            [--leave-out REGEX]

The skeleton is renamed to 3ds Max Biped names first (rig.py), which blender2xps maps onto the XPS standard names,
so XPS poses apply.  Metres already (Elden Ring units).  The normal maps go in the DirectX way XPS reads them
(<map>_nrm_dx.png beside the .blend's OpenGL _nrm.png; green down, blue rebuilt - the game's blue is gloss).
--leave-out drops the mesh objects (named after the FLVER materials) the regex matches, e.g. a hardsuit.
Prints ER_XPS={json}.  Writes <out>/<name>.xps + its textures.
"""
import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
B2X = os.environ.get("BLENDER2XPS", r"E:\code\othercode\blender2xps")
if B2X not in sys.path:
    sys.path.insert(0, B2X)
from blender2xps import export_xps  # noqa: E402
import rig  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


out_dir = arg("--out")
if not out_dir:
    raise SystemExit("usage: blender -b X.blend --python export_xps_blender.py -- --out <dir> [--name N]")
name = arg("--name") or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {"name": name, "blend": bpy.data.filepath, "ok": False}
scene = bpy.context.scene
summary["left_out"] = rig.leave_out(scene, arg("--leave-out"))
arm = next(o for o in scene.objects if o.type == "ARMATURE")
meshes = [o for o in scene.objects if o.type == "MESH"]
summary["rig"] = rig.to_biped(arm, meshes)

swapped = 0
for mat in {s.material for o in meshes for s in o.material_slots if s.material and s.material.use_nodes}:
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and n.image.filepath.endswith("_nrm.png"):
            dx = bpy.path.abspath(n.image.filepath)[:-4] + "_dx.png"
            if os.path.isfile(dx):
                img = bpy.data.images.load(dx, check_existing=True)
                img.colorspace_settings.name = "Non-Color"
                n.image = img
                swapped += 1
summary["normal_maps_directx"] = swapped

os.makedirs(out_dir, exist_ok=True)
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + ".xps"), fmt="AUTO", scope="VISIBLE",
                               scale=1.0, bake_mode="AUTO", bone_naming="XPS", max_weights=4, auto_facing=True)
res = export_xps.export_model(bpy.context, settings)
summary.update({"ok": not res.errors, "path": res.path, "fmt": res.fmt, "bones": res.bone_count,
                "meshes": res.mesh_count, "stats": res.stats, "warnings": res.warnings, "errors": res.errors,
                "seconds": round(time.time() - t0, 1)})
print("ER_XPS=" + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
