"""Blender (3.6+) dump of a skinned character for vam_items / bring_to_vam.py.

    blender -b <character.blend> --factory-startup -P blender_dump_skinned.py -- <out_dir>
        [--bake <material>[,<material>...]] [--bake-size 2048]

Writes <out_dir>/src.npz and <out_dir>/src.json:

* every mesh object deformed by an armature: world-space rest vertices (the armature is
  expected to be in its rest pose), polygons (loop vertex indices + sizes), the first UV
  layer per loop, per-polygon material index, and the vertex-group weights as a sparse
  (vertex, group, weight) triplet list with the group names;
* the armature: bone names, parents, rest head / tail / 4x4 matrix in world space;
* materials: every image a material node tree uses (absolute path + node label + the
  colour space), plus the colour-ramp stops (hair root / mid / tip colours) and the
  Principled BSDF defaults, so the VaM side can rebuild textures without Blender;
* with ``--bake``: the base colour of each named material baked into its own UVs
  (``bake_<material>.png``, Cycles emission bake of whatever feeds Base Color) -- for
  procedural materials such as a game eye shader (iris colours picked from a palette, pupil
  and limbus drawn by nodes), which have no single texture to hand over.

Coordinates are Blender's (Z up, whatever unit the file uses); the VaM side converts.
"""
import json
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv and not argv[0].startswith("--") else os.path.join(os.path.dirname(bpy.data.filepath), "_dump")
BAKE = argv[argv.index("--bake") + 1].split(",") if "--bake" in argv else []
BAKE_SIZE = int(argv[argv.index("--bake-size") + 1]) if "--bake-size" in argv else 2048
os.makedirs(OUT, exist_ok=True)

arrays = {}
meta = {"source": bpy.data.filepath, "objects": [], "armature": None, "materials": {}}

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if rig is not None:
    bones = rig.data.bones
    names = [b.name for b in bones]
    heads = np.array([rig.matrix_world @ b.head_local for b in bones], dtype=np.float64)
    tails = np.array([rig.matrix_world @ b.tail_local for b in bones], dtype=np.float64)
    mats = np.array([np.array(rig.matrix_world @ b.matrix_local) for b in bones], dtype=np.float64)
    arrays["bone_head"] = heads
    arrays["bone_tail"] = tails
    arrays["bone_matrix"] = mats
    meta["armature"] = {"name": rig.name, "bones": names,
                        "parents": [b.parent.name if b.parent else None for b in bones]}

for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    me = obj.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(obj.matrix_world)
    world = co @ mw[:3, :3].T + mw[:3, 3]
    nl = len(me.loops)
    loop_vert = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", loop_vert)
    npoly = len(me.polygons)
    loop_start = np.empty(npoly, dtype=np.int32)
    loop_total = np.empty(npoly, dtype=np.int32)
    mat_index = np.empty(npoly, dtype=np.int32)
    me.polygons.foreach_get("loop_start", loop_start)
    me.polygons.foreach_get("loop_total", loop_total)
    me.polygons.foreach_get("material_index", mat_index)
    uv = np.zeros((nl, 2), dtype=np.float32)
    if me.uv_layers:
        flat = np.empty(nl * 2, dtype=np.float32)
        me.uv_layers[0].data.foreach_get("uv", flat)
        uv = flat.reshape(-1, 2)
    wv, wg, ww = [], [], []
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 0.0:
                wv.append(v.index)
                wg.append(g.group)
                ww.append(g.weight)
    key = "obj%d" % len(meta["objects"])
    arrays[key + "_verts"] = world
    arrays[key + "_loop_vert"] = loop_vert
    arrays[key + "_loop_start"] = loop_start
    arrays[key + "_loop_total"] = loop_total
    arrays[key + "_mat"] = mat_index
    arrays[key + "_uv"] = uv
    arrays[key + "_w_vert"] = np.array(wv, dtype=np.int32)
    arrays[key + "_w_group"] = np.array(wg, dtype=np.int32)
    arrays[key + "_w_weight"] = np.array(ww, dtype=np.float32)
    meta["objects"].append({
        "key": key, "name": obj.name, "hidden": bool(obj.hide_get() or obj.hide_render),
        "verts": nv, "polys": npoly, "uv_layer": me.uv_layers[0].name if me.uv_layers else None,
        "materials": [m.name if m else None for m in me.materials],
        "groups": [g.name for g in obj.vertex_groups],
    })

for mat in bpy.data.materials:
    entry = {"images": [], "ramps": [], "bsdf": {}, "blend_method": mat.blend_method}
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                img = node.image
                path = bpy.path.abspath(img.filepath) if img.filepath else ""
                if img.packed_file is not None and (not path or not os.path.isfile(path)):
                    # packed only: write it next to the dump
                    path = os.path.join(OUT, "images", bpy.path.clean_name(img.name) + ".png")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    img.filepath_raw = path
                    img.file_format = "PNG"
                    img.save()
                links = [l.to_socket.name + "@" + l.to_node.type for o in node.outputs for l in o.links]
                entry["images"].append({"label": node.label or node.name, "image": img.name, "path": path,
                                        "colorspace": img.colorspace_settings.name, "size": list(img.size),
                                        "links": links})
            elif node.type == "VALTORGB":
                entry["ramps"].append([[e.position, list(e.color)] for e in node.color_ramp.elements])
            elif node.type == "BSDF_PRINCIPLED":
                for name in ("Base Color", "Roughness", "Metallic", "Specular", "Alpha"):
                    sock = node.inputs.get(name)
                    if sock is not None and not sock.is_linked:
                        val = sock.default_value
                        entry["bsdf"][name] = list(val) if hasattr(val, "__len__") else float(val)
    meta["materials"][mat.name] = entry



def bake_base_colour(mat, size, path):
    """Bake what feeds the material's Base Color into its UV layout (emission bake on a
    temporary copy of the mesh that keeps only this material's polygons: every material of a
    baked object needs a target image, and the other materials' UVs would overwrite it)."""
    import bmesh

    owner = next((o for o in bpy.data.objects if o.type == "MESH"
                  and any(sl.material == mat for sl in o.material_slots)), None)
    if owner is None:
        print("BAKE_SKIPPED %s: no mesh uses it" % mat.name)
        return None
    slot = next(i for i, sl in enumerate(owner.material_slots) if sl.material == mat)
    tmp = owner.copy()
    tmp.data = owner.data.copy()
    tmp.modifiers.clear()
    bpy.context.scene.collection.objects.link(tmp)
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != slot], context="FACES")
    bm.to_mesh(tmp.data)
    bm.free()
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    emit = nt.nodes.new("ShaderNodeEmission")
    if bsdf is not None and bsdf.inputs["Base Color"].is_linked:
        nt.links.new(bsdf.inputs["Base Color"].links[0].from_socket, emit.inputs["Color"])
    elif bsdf is not None:
        emit.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
    surface = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    img = bpy.data.images.new("bake_" + mat.name, size, size, alpha=False)
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.nodes.active = node
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 4
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    tmp.hide_set(False)
    tmp.hide_render = False
    tmp.select_set(True)
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.object.bake(type="EMIT", margin=16, use_clear=True)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    # leave the file's material as it was
    nt.nodes.remove(node)
    nt.nodes.remove(emit)
    if surface is not None:
        nt.links.new(surface, out.inputs["Surface"])
    bpy.data.objects.remove(tmp, do_unlink=True)
    print("BAKED %s -> %s" % (mat.name, path))
    return path


for name in BAKE:
    mat = bpy.data.materials.get(name)
    if mat is None or not mat.use_nodes:
        print("BAKE_SKIPPED %s: no such node material" % name)
        continue
    path = bake_base_colour(mat, BAKE_SIZE, os.path.join(OUT, "bake_%s.png" % bpy.path.clean_name(name)))
    if path:
        meta["materials"][name]["baked_base_color"] = path

np.savez_compressed(os.path.join(OUT, "src.npz"), **arrays)
with open(os.path.join(OUT, "src.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print("DUMP_DONE objects=%d bones=%d" % (len(meta["objects"]), len(meta["armature"]["bones"]) if meta["armature"] else 0))
