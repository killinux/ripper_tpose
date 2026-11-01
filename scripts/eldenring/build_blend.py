# -*- coding: utf-8 -*-
"""unpack_mod.py's work folder -> .blend with the game's full-size PBR materials (Blender 3.6, headless).

    blender -b --factory-startup --python build_blend.py -- --work <work dir> --out <file.blend>
            [--name N] [--preview <png>] [--hide-weapon]

  * one armature (the merged player skeleton, FromSoftware's bone names; bones point along their +X like 3ds Max);
  * one mesh object per FLVER mesh (named after its material), in a collection per part (头部 / 身体 / 手臂 /
    腿部 / 武器), with the game's vertex normals as custom normals, UV0 / UV1, the FLVER vertex colour as an
    attribute ("FLVER_color", not shaded) and normalised weights;
  * materials: Principled BSDF - colour + alpha from _a, metallic from _m red, roughness = 1 - gloss (_n blue),
    normal from _n red/green as OpenGL (unpack_mod.py converted the DirectX maps); alpha hashed where _a has holes
    (hair, lashes, the suit's tears); two-sided like the game (its face sets do not cull);
  * textures are copied next to the .blend (textures/) and linked relatively, so the folder can move.
Prints ER_BLEND={json}.
"""
import json
import math
import os
import shutil
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv else default


work = arg("--work")
out_blend = arg("--out")
if not work or not out_blend:
    raise SystemExit("usage: blender -b --python build_blend.py -- --work <dir> --out <file.blend> [--name N]")
name = arg("--name") or os.path.splitext(os.path.basename(out_blend))[0]
preview = arg("--preview")
GLOW = float(arg("--glow-strength", "6"))
t0 = time.time()

with open(os.path.join(work, "model.json"), encoding="utf-8") as fh:
    model = json.load(fh)
arrays = np.load(os.path.join(work, "model.npz"))
out_dir = os.path.dirname(os.path.abspath(out_blend))
tex_out = os.path.join(out_dir, "textures")
os.makedirs(tex_out, exist_ok=True)

# --------------------------------------------------------------------------------------------- empty scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"

# --------------------------------------------------------------------------------------------- skeleton
arm_data = bpy.data.armatures.new(name + "_骨架")
arm = bpy.data.objects.new(name, arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bones = model["bones"]
by_name = {b["name"]: b for b in bones}
children = {}
for b in bones:
    if b["parent"]:
        children.setdefault(b["parent"], []).append(b["name"])
for b in bones:
    eb = arm_data.edit_bones.new(b["name"])
    head = Vector(b["head"])
    x = Vector(b["x"]).normalized()
    length = None
    for c in children.get(b["name"], []):
        d = Vector(by_name[c]["head"]) - head
        if d.length > 0.005 and d.normalized().dot(x) > 0.9:
            length = d.length if length is None else min(length, d.length)
    if length is None:
        length = 0.04 if not b.get("weapon") else 0.15
    eb.head = head
    eb.tail = head + x * length
    eb.align_roll(Vector(b["z"]))
for b in bones:
    if b["parent"] and b["parent"] in arm_data.edit_bones:
        arm_data.edit_bones[b["name"]].parent = arm_data.edit_bones[b["parent"]]
bpy.ops.object.mode_set(mode="OBJECT")
arm_data.display_type = "STICK"
arm.show_in_front = True

# --------------------------------------------------------------------------------------------- materials
images = {}


def image(file, colour):
    if not file:
        return None
    key = (file, colour)
    if key in images:
        return images[key]
    src = os.path.join(work, "textures", file)
    dst = os.path.join(tex_out, file)
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        shutil.copy2(src, dst)
    dx = os.path.splitext(src)[0] + "_dx.png"                      # the DirectX normal map export_xps swaps in
    if file.endswith("_nrm.png") and os.path.exists(dx):
        shutil.copy2(dx, os.path.join(tex_out, os.path.basename(dx)))
    img = bpy.data.images.load(dst, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    images[key] = img
    return img


def build_material(key, m):
    mat = bpy.data.materials.new(m["name"] if m["name"] not in bpy.data.materials else key.replace("|", "_"))
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tx = m["textures"]
    y = 300
    alb = tx.get("albedo")
    if alb:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(alb["file"], True)
        n.location = (-400, y)
        n.label = "颜色 (_a)"
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        if alb.get("alpha"):
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.blend_method = "HASHED"
            mat.shadow_method = "HASHED"
        y -= 280
    met = tx.get("metallic")
    if met and met.get("metal"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(met["metal"], False)
        n.location = (-400, y)
        n.label = "金属度 (_m 红)"
        nt.links.new(n.outputs["Color"], bsdf.inputs["Metallic"])
        y -= 280
    else:
        bsdf.inputs["Metallic"].default_value = 0.0
    nrm = tx.get("normal")
    if nrm and nrm.get("rough"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(nrm["rough"], False)
        n.location = (-400, y)
        n.label = "粗糙度 (1 - _n 蓝)"
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
        y -= 280
    else:
        bsdf.inputs["Roughness"].default_value = 0.6
    if nrm and nrm.get("nrm"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(nrm["nrm"], False)
        n.location = (-400, y)
        n.label = "法线 (_n 红绿, OpenGL)"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-100, y)
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    emi = tx.get("emission")
    if emi:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(emi["file"], True)
        n.location = (-400, y - 280)
        n.label = "自发光（蓝灯）"
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission"])
        bsdf.inputs["Emission Strength"].default_value = GLOW
    bsdf.inputs["Specular"].default_value = 0.5
    mat.use_backface_culling = bool(m.get("backface_culling"))
    mat.show_transparent_back = True
    # what the XPS / PMX steps read back
    mat["er_part"] = m["part"]
    mat["er_shader"] = m["shader"]
    for role, t in tx.items():
        if t:
            mat["er_" + role] = t["file"]
    return mat


materials = {k: build_material(k, m) for k, m in model["materials"].items()}

# --------------------------------------------------------------------------------------------- meshes
part_label = {p["id"]: "%s %s" % (p["label"], p["id"]) for p in model["parts"]}
collections = {}
for pid, label in part_label.items():
    c = bpy.data.collections.new(label)
    scene.collection.children.link(c)
    collections[pid] = c

stats = []
for m in model["meshes"]:
    mid = m["id"]
    V = arrays[mid + "_pos"]
    N = arrays[mid + "_nrm"]
    T = arrays[mid + "_tri"]
    me = bpy.data.meshes.new(m["name"])
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    nl = len(T) * 3
    me.loops.add(nl)
    me.loops.foreach_set("vertex_index", T.ravel().astype(np.int32))
    me.polygons.add(len(T))
    me.polygons.foreach_set("loop_start", np.arange(0, nl, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(T), 3, dtype=np.int32))
    me.update(calc_edges=True)
    loop_v = T.ravel()
    for k in range(m["uv_sets"]):
        uv = arrays[mid + "_uv%d" % k]
        layer = me.uv_layers.new(name="UVMap" if k == 0 else "UVMap%d" % k)
        layer.data.foreach_set("uv", uv[loop_v].ravel())
    if mid + "_col" in arrays:
        col = arrays[mid + "_col"]
        attr = me.attributes.new("FLVER_color", "FLOAT_COLOR", "POINT")
        attr.data.foreach_set("color", np.clip(col, 0, 1).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(T), dtype=bool))
    me.use_auto_smooth = True
    me.auto_smooth_angle = math.pi
    me.normals_split_custom_set_from_vertices([tuple(n) for n in N])
    me.materials.append(materials[m["material"]])
    ob = bpy.data.objects.new(m["name"], me)
    collections[m["part"]].objects.link(ob)
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    bix = arrays[mid + "_bix"]
    wgt = arrays[mid + "_wgt"]
    groups = [ob.vertex_groups.new(name=bn) for bn in m["bone_names"]]
    total = np.zeros((len(V), len(groups)), dtype=np.float32)
    for s in range(4):
        sel = wgt[:, s] > 0
        np.add.at(total, (np.nonzero(sel)[0], bix[sel, s]), wgt[sel, s])
    for gi, g in enumerate(groups):
        idx = np.nonzero(total[:, gi] > 0)[0]
        w = total[idx, gi]
        for value in np.unique(np.round(w, 4)):
            vs = idx[np.round(w, 4) == value]
            g.add(vs.tolist(), float(value), "REPLACE")
    ob["er_part"] = m["part"]
    ob["er_mesh"] = mid
    stats.append({"object": ob.name, "vertices": len(me.vertices), "faces": len(me.polygons)})

if "--hide-weapon" in argv:
    for pid, c in collections.items():
        if pid.startswith("wp_"):
            c.hide_render = True
            for o in c.objects:
                o.hide_set(True)

# --------------------------------------------------------------------------------------------- scene / preview
scene.render.engine = "BLENDER_EEVEE"
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.33, 0.36, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
for nm, rot, energy in (("主光", (math.radians(50), 0, math.radians(-30)), 3.0),
                        ("补光", (math.radians(60), 0, math.radians(150)), 1.2)):
    ld = bpy.data.lights.new(nm, "SUN")
    ld.energy = energy
    lo = bpy.data.objects.new(nm, ld)
    lo.rotation_euler = rot
    scene.collection.objects.link(lo)
scene.eevee.use_ssr = True
scene.eevee.use_gtao = True
scene.eevee.use_soft_shadows = True
scene.view_settings.view_transform = "Filmic"
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend), relative_remap=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()


def render_views(path):
    """front / left side / back of the whole model in one strip."""
    objs = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    pts = np.array([o.matrix_world @ Vector(c) for o in objs for c in o.bound_box])
    lo, hi = pts.min(0), pts.max(0)
    centre = (lo + hi) / 2
    size = max(hi[2] - lo[2], hi[0] - lo[0], hi[1] - lo[1]) * 1.08
    cam_data = bpy.data.cameras.new("预览相机")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size
    cam = bpy.data.objects.new("预览相机", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 900, 1200
    scene.render.film_transparent = False
    files = []
    for k, ang in enumerate((0, 90, 180)):
        a = math.radians(ang)
        d = Vector((math.sin(a), -math.cos(a), 0))
        cam.location = Vector(centre) + d * 10
        cam.rotation_euler = (math.radians(90), 0, a)
        f = path + ".%d.png" % k
        scene.render.filepath = f
        bpy.ops.render.render(write_still=True)
        files.append(f)
    bpy.data.objects.remove(cam)
    return files


summary = {"blend": os.path.abspath(out_blend), "objects": len(stats), "bones": len(bones),
           "materials": len(materials), "vertices": sum(s["vertices"] for s in stats),
           "faces": sum(s["faces"] for s in stats), "images": len(images)}
if preview:
    summary["preview_views"] = render_views(preview)
summary["seconds"] = round(time.time() - t0, 1)
print("ER_BLEND=" + json.dumps(summary, ensure_ascii=False), flush=True)
