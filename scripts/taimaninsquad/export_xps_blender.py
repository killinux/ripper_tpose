"""Taimanin Squad .blend -> XPS (XNALara) with Blender2XPS, headless.

    blender -b <id>.blend --python export_xps_blender.py -- --out <dir> [--name N] [--keep-weapon] [--unlit]

Writes <out>/<name>/<name>.xps (+ textures + the Blender2XPS report).  The blend comes from
build_blend.py: metres, facing -Y, a 3ds Max Biped skeleton (``Bip001 L UpperArm`` ...), which
Blender2XPS already maps onto the XPS standard bone names, so XPS poses apply.

XPS has no toon shader: the outline hull is removed and every material becomes its base map
(tex_d, the game's lit colour); _BaseColor tints are baked in.  ``--unlit`` picks the shadeless
render groups (10 / 21), which show exactly those colours whatever the XPS lights do; the default
groups (5 / 7) let XPS shade the model.  Blend shapes do not exist in XPS: the rest face is exported.
Weapons carried on the body are exported; those parked at the origin in the prefab pose (the
"Weapons (parked)" collection) only with --keep-weapon.

Prints TSQ_XPS={json}.
"""
import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
B2X = os.environ.get("BLENDER2XPS", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "blender2xps"))
if B2X not in sys.path:
    sys.path.insert(0, B2X)
import tsquad_blender as tb  # noqa: E402
from blender2xps import export_xps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


out_root = arg("--out")
if not out_root:
    raise SystemExit("usage: blender -b X.blend --python export_xps_blender.py -- --out <dir> [--name N] "
                     "[--keep-weapon] [--unlit]")
name = arg("--name") or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {"name": name, "blend": bpy.data.filepath, "ok": False}
arm, meshes, removed = tb.scene_parts(keep_weapon="--keep-weapon" in argv)
summary["weapons_left_out"] = removed
summary["outline_modifiers_removed"] = tb.strip_outline(meshes)
tb.clear_shape_key_drivers(meshes)
summary["plain_materials"] = len(tb.plain_materials(meshes))
out_dir = os.path.join(out_root, name)
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + ".xps"), fmt="AUTO", scope="VISIBLE",
                               scale=1.0, bake_mode="AUTO", bone_naming="XPS", max_weights=4, auto_facing=True,
                               unlit="--unlit" in argv)
res = export_xps.export_model(bpy.context, settings)
summary.update({"ok": not res.errors, "path": res.path, "fmt": res.fmt, "bones": res.bone_count,
                "meshes": res.mesh_count, "stats": res.stats, "warnings": res.warnings, "errors": res.errors,
                "seconds": round(time.time() - t0, 1)})
print("TSQ_XPS=" + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
