# -*- coding: utf-8 -*-
"""Any game's character .blend -> XPS (XNALara) with blender2xps, headless, after the same rig map as the PMX
(rigs/<name>.py turns the skeleton into 3ds Max Biped names, which blender2xps maps onto the XPS standard ones, so XPS
poses apply).  The scene must be in metres, Z up, facing -Y.

    blender -b <name>.blend --factory-startup --python export_xps_blender.py -- --rig <mho|...> --out <dir>
            [--name N] [--leave-out REGEX]

Prints BIPED_XPS={json}.  Writes <out>/<name>.xps + its textures.
"""
import importlib.util
import json
import os
import re
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
B2X = os.environ.get("BLENDER2XPS", r"E:\code\othercode\blender2xps")
if B2X not in sys.path:
    sys.path.insert(0, B2X)
from blender2xps import export_xps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


def load_rig(name):
    path = os.path.join(HERE, "rigs", name + ".py")
    spec = importlib.util.spec_from_file_location("rig_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


out_dir, rig_name = arg("--out"), arg("--rig")
if not out_dir or not rig_name:
    raise SystemExit("usage: blender -b X.blend --python export_xps_blender.py -- --rig <name> --out <dir> [--name N]")
rig = load_rig(rig_name)
name = arg("--name") or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {"name": name, "blend": bpy.data.filepath, "rig": rig_name, "ok": False}
scene = bpy.context.scene
rx = re.compile(arg("--leave-out")) if arg("--leave-out") else None
summary["left_out"] = []
for o in list(scene.objects):
    if o.type == "MESH" and (o.hide_render or o.hide_get() or (rx and rx.search(o.name))):
        summary["left_out"].append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in scene.objects if o.type == "ARMATURE")
meshes = [o for o in scene.objects if o.type == "MESH"]
summary["rig_report"] = rig.to_biped(arm, meshes)


def wrap_uv_tiles(objs):
    """Faces whose UV centre lies outside 0..1 moved by whole tiles into it (textures repeat; a bake fills 0..1 only) -
    the same as scripts/stellarblade/export_pmx_blender.py wrap_uv_tiles."""
    import math
    moved = {}
    for obj in objs:
        me = obj.data
        layer = next((u for u in me.uv_layers if u.active_render), None)
        if layer is None:
            continue
        data, count = layer.data, 0
        for poly in me.polygons:
            idx = list(poly.loop_indices)
            du = math.floor(sum(data[i].uv[0] for i in idx) / len(idx))
            dv = math.floor(sum(data[i].uv[1] for i in idx) / len(idx))
            if du or dv:
                for i in idx:
                    u, v = data[i].uv
                    data[i].uv = (u - du, v - dv)
                count += 1
        if count:
            moved[obj.name] = count
    return moved


summary["uv_tiles_wrapped"] = wrap_uv_tiles(meshes)

os.makedirs(out_dir, exist_ok=True)
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + ".xps"), fmt="AUTO", scope="VISIBLE",
                               scale=1.0, bake_mode="AUTO", bone_naming="XPS", max_weights=4, auto_facing=True)
res = export_xps.export_model(bpy.context, settings)
summary.update({"ok": not res.errors, "path": res.path, "fmt": res.fmt, "bones": res.bone_count,
                "meshes": res.mesh_count, "stats": res.stats, "warnings": res.warnings, "errors": res.errors,
                "seconds": round(time.time() - t0, 1)})
print("BIPED_XPS=" + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
