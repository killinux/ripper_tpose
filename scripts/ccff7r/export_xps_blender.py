"""CCFF7R .blend -> XPS (XNALara) with Blender2XPS, headless.

    blender -b <id>.blend --python export_xps_blender.py -- --out <dir> [--name N] [--keep-weapon]

Writes <out>/<name>/<name>.xps (+ textures + blender2xps report).  The blend comes from
build_blend.py: UE centimetres (scaled x0.01 here, Tifa 1.64 units tall like the FF7 XPS),
images packed (Blender2XPS reads packed images itself), HumanIK bone names (Hips / Spine1 /
LeftForeArm / LeftHandThumb1 ...) that Blender2XPS already maps onto the XPS standard names, so
XPS poses apply.  The <id>_weapon object (Buster Sword, shuriken ... lying at the feet in the
bind pose) is left out unless --keep-weapon.

Prints CCFF7R_XPS={json}.
"""
import json
import os
import sys
import time

import bpy

B2X = os.environ.get("BLENDER2XPS", r"E:\code\othercode\blender2xps")
if B2X not in sys.path:
    sys.path.insert(0, B2X)
from blender2xps import export_xps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


out_root = arg("--out")
if not out_root:
    raise SystemExit("usage: blender -b X.blend --python export_xps_blender.py -- --out <dir> [--name N] [--keep-weapon]")
name = arg("--name") or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {"name": name, "blend": bpy.data.filepath, "ok": False, "weapons_left_out": []}
if "--keep-weapon" not in argv:
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj.name.endswith("_weapon"):
            summary["weapons_left_out"].append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
out_dir = os.path.join(out_root, name)
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + ".xps"), fmt="AUTO", scope="VISIBLE",
                               scale=0.01, bake_mode="AUTO", bone_naming="XPS", max_weights=4, auto_facing=True)
res = export_xps.export_model(bpy.context, settings)
summary.update({"ok": not res.errors, "path": res.path, "fmt": res.fmt, "bones": res.bone_count,
                "meshes": res.mesh_count, "stats": res.stats, "warnings": res.warnings, "errors": res.errors,
                "seconds": round(time.time() - t0, 1)})
print("CCFF7R_XPS=" + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
