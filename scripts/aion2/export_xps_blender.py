"""AION2 .blend (build_blend.py) -> XPS (XNALara) with Blender2XPS, headless.

    blender -b <id>.blend --python export_xps_blender.py -- --out <dir> [--name N] [--keep-weapon]

Like scripts/ccff7r/export_xps_blender.py.  AION2 spells its Biped bones with hyphens (``Bip001-L-UpperArm``); they
are renamed to the space form Blender2XPS maps onto the XPS standard names (``arm left shoulder 2`` ...), and the eye
bones ``b_L_Eye_0`` / ``b_R_Eye_0`` (``Bone_eye_L`` / ``_R`` on the cutscene rig) to ``Bip001 L / R Eye``, so XPS
poses move them.  The face rig, cloth and hair chains keep their game names.  Centimetres are scaled x0.01 (Yustiel
1.84 units tall); the colours are the .blend's baked albedo maps.  XPS has no morphs: the expressions are in the PMX.

Prints AION2_XPS={json}.  Writes <out>/<name>/<name>.xps + its textures.
"""
import json
import os
import re
import sys
import time

import bmesh
import bpy

B2X = os.environ.get("BLENDER2XPS", r"E:\code\othercode\blender2xps")
if B2X not in sys.path:
    sys.path.insert(0, B2X)
from blender2xps import export_xps  # noqa: E402

EYES = (("b_L_Eye_0", "Bip001 L Eye"), ("b_R_Eye_0", "Bip001 R Eye"),
        ("Bone_eye_L", "Bip001 L Eye"), ("Bone_eye_R", "Bip001 R Eye"))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


out_root = arg("--out")
if not out_root:
    raise SystemExit("usage: blender -b X.blend --python export_xps_blender.py -- --out <dir> [--name N] [--keep-weapon]")
name = arg("--name") or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
t0 = time.time()
summary = {"name": name, "blend": bpy.data.filepath, "ok": False, "renamed": 0, "weapons_left_out": []}

# as export_pmx_blender.py: weapons hanging off the root lose their skin (Siel's orb, 3.4 m away in the cut-scene's
# bind pose) unless --keep-weapon, and a giant (head joint above 2 m: Siel 2.73 m) is scaled to 1.67 m
WEAPON_RE = re.compile(r"(^|_)weapon", re.IGNORECASE)
scale = 0.01
for arm in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    weapons = {b.name for b in arm.data.bones if WEAPON_RE.search(b.name) and
               (b.parent is None or b.parent.parent is None)} if "--keep-weapon" not in argv else set()
    for m in [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() == arm]:
        idx = {vg.index for vg in m.vertex_groups if vg.name in weapons}
        doomed = [v.index for v in m.data.vertices if idx and sum(g.weight for g in v.groups if g.group in idx) >= 0.5]
        if doomed:
            bm = bmesh.new()
            bm.from_mesh(m.data)
            bm.verts.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context="VERTS")
            bm.to_mesh(m.data)
            bm.free()
    summary["weapons_left_out"] += sorted(weapons)
    head = arm.data.bones.get("Bip001-Head") or arm.data.bones.get("Bip001 Head")
    if head is not None:
        z = (arm.matrix_world @ head.head_local).z
        if z > 200.0:
            scale = 0.01 * 166.9 / z
            summary["rescaled"] = "head at %.2f m -> 1.67 m" % (z / 100.0)
for arm in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    for bone in arm.data.bones:                    # Blender renames the skinned meshes' vertex groups too
        if bone.name.startswith("Bip001-"):
            bone.name = bone.name.replace("-", " ")
            summary["renamed"] += 1
    for old, new in EYES:
        if old in arm.data.bones and new not in arm.data.bones:
            arm.data.bones[old].name = new
            summary["renamed"] += 1
out_dir = os.path.join(out_root, name)
settings = export_xps.Settings(filepath=os.path.join(out_dir, name + ".xps"), fmt="AUTO", scope="VISIBLE",
                               scale=scale, bake_mode="AUTO", bone_naming="XPS", max_weights=4, auto_facing=True)
res = export_xps.export_model(bpy.context, settings)
summary.update({"ok": not res.errors, "path": res.path, "fmt": res.fmt, "bones": res.bone_count,
                "meshes": res.mesh_count, "stats": res.stats, "warnings": res.warnings, "errors": res.errors,
                "seconds": round(time.time() - t0, 1)})
if os.path.isdir(out_dir):                          # the gallery reads it (which .blend the XPS came from)
    with open(os.path.join(out_dir, name + "_xps.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=str)
print("AION2_XPS=" + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
