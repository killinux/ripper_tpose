"""Blender (3.6) preview of VaM items the way VaM builds them: read each item's .vab, rebuild every
vertex from its DAZSkinWrapStore on the G2F base body, put the .vaj textures on, render.

    blender -b --factory-startup -P blender_preview_items.py -- --out <dir> [--thumbs] [--morph <m.vmb>]...
        [--skin <character texture index.json>] [--face <face diffuse>] [--irises <eye diffuse>]
        [--list <file>] <item.vam> ...

Writes <dir>/preview_front.png, _side.png, _back.png (body + all items) and, with --thumbs,
a 512x512 <item>.jpg next to every .vam (the thumbnail VaM shows in its clothing/hair browser).
``--morph`` may repeat (body and head morph together, the way the preset wears them).  With
``--skin`` the body is textured per VaM texture region (face / torso / limbs / genitals, eyes,
mouth, lashes) from a character's cached textures (``_cache/textures/<bundle>/index.json``);
``--face`` / ``--irises`` override the face diffuse and the eye texture, as a preset's
``textures.faceDiffuseUrl`` / ``irises.customTexture_MainTex`` do.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vam_lib as vl  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else os.getcwd()
THUMBS = "--thumbs" in argv
ITEMS = [a for a in argv if a.lower().endswith(".vam")]
if "--list" in argv:
    with open(argv[argv.index("--list") + 1], encoding="utf-8") as _f:
        ITEMS += [ln.strip() for ln in _f if ln.strip()]
CACHE = r"D:\vam_exports\_cache"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def to_blender(v):
    v = np.asarray(v, dtype=np.float64)
    return np.stack([-v[:, 0], -v[:, 2], v[:, 1]], axis=1)


def make_mesh(name, verts_vam, poly_len, poly_idx, uv_poly_idx=None, uvs=None, poly_mat=None, mats=()):
    me = bpy.data.meshes.new(name)
    v = to_blender(verts_vam)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.astype(np.float32).ravel())
    nl = int(np.sum(poly_len))
    me.loops.add(nl)
    me.loops.foreach_set("vertex_index", np.asarray(poly_idx, dtype=np.int32))
    me.polygons.add(len(poly_len))
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]]).astype(np.int32)
    me.polygons.foreach_set("loop_start", starts)
    me.polygons.foreach_set("loop_total", np.asarray(poly_len, dtype=np.int32))
    if poly_mat is not None:
        me.polygons.foreach_set("material_index", np.asarray(poly_mat, dtype=np.int32))
    if uvs is not None:
        layer = me.uv_layers.new(name="UV")
        layer.data.foreach_set("uv", np.asarray(uvs, dtype=np.float32)[np.asarray(uv_poly_idx)].ravel())
    me.update(calc_edges=True)
    for m in mats:
        me.materials.append(m)
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True
    return obj


def material(name, folder, storable):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    main = storable.get("customTexture_MainTex")
    alpha = storable.get("customTexture_AlphaTex")
    bump = storable.get("customTexture_BumpMap")
    gloss = storable.get("customTexture_GlossTex")
    if main and os.path.isfile(os.path.join(folder, main)):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(folder, main), check_existing=True)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha and os.path.isfile(os.path.join(folder, alpha)):
        a = nt.nodes.new("ShaderNodeTexImage")
        a.image = bpy.data.images.load(os.path.join(folder, alpha), check_existing=True)
        a.image.colorspace_settings.name = "Non-Color"
        nt.links.new(a.outputs["Color"], bsdf.inputs["Alpha"])
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
    if bump and os.path.isfile(os.path.join(folder, bump)):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(folder, bump), check_existing=True)
        n.image.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if gloss and os.path.isfile(os.path.join(folder, gloss)):
        g = nt.nodes.new("ShaderNodeTexImage")
        g.image = bpy.data.images.load(os.path.join(folder, gloss), check_existing=True)
        g.image.colorspace_settings.name = "Non-Color"
        inv = nt.nodes.new("ShaderNodeInvert")
        nt.links.new(g.outputs["Color"], inv.inputs["Color"])
        nt.links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])
    mat.use_backface_culling = False
    return mat


base = np.load(os.path.join(CACHE, "base_female.npz"))
base_meta = json.load(open(os.path.join(CACHE, "base_female.json"), encoding="utf-8"))
bverts = base["verts"].astype(np.float64)
for _k, _a in enumerate(argv):
    if _a == "--morph":
        # morphs (.vmb) on, the way the preset wears the items
        _mi, _md = vl.parse_vmb(open(argv[_k + 1], "rb").read())
        bverts[_mi] += _md
bnorm = vl.outward_normals(bverts.astype(np.float32), base["poly_len"], base["poly_idx"])


def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None


def image_material(name, path, roughness=0.5, alpha=False, color=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    if color is not None:
        bsdf.inputs["Base Color"].default_value = tuple(color) + (1,)
    if path and os.path.isfile(path):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path, check_existing=True)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.blend_method = "HASHED"
            mat.shadow_method = "HASHED"
    return mat


def body_materials():
    """One material per G2F material slot, textured by VaM texture region when --skin is given."""
    names = base_meta["materialNames"]
    if not arg("--skin"):
        skin = image_material("skin", None, 0.55, color=(0.8, 0.6, 0.5))
        return [skin] * len(names), set()
    index = json.load(open(arg("--skin"), encoding="utf-8"))
    tex = {k: v for k, v in index.items()}
    if arg("--face"):
        tex["face|diffuse"] = arg("--face")
    if arg("--irises"):
        tex["eyes|diffuse"] = arg("--irises")
    region = {}
    for group, reg in (("face", "face"), ("torso", "torso"), ("limb", "limbs"), ("genital", "genitals")):
        for i in base_meta["textureGroups"].get(group, []):
            region[i] = reg
    cache = {}
    mats, hidden = [], set()
    for i, name in enumerate(names):
        if name in ("Hidden", "Cornea", "EyeReflection", "Tear"):
            hidden.add(i)
            key = ("none",)
        elif i in region:
            key = (region[i],)
        elif name in ("Irises", "Sclera", "Pupils"):
            key = ("eyes",)
        elif name in ("Teeth", "Gums", "Tongue", "InnerMouth"):
            key = ("mouth",)
        elif name == "Eyelashes":
            key = ("lashes",)
        elif name == "Lacrimals":
            key = ("lacrimals",)
        else:
            key = ("torso",)
        if key not in cache:
            k = key[0]
            if k == "lashes":
                cache[key] = image_material("g2f_lashes", tex.get("lashes|diffuse"), 0.6, alpha=True)
            elif k == "lacrimals":
                cache[key] = image_material("g2f_lacrimals", None, 0.2, color=(0.75, 0.5, 0.5))
            elif k == "none":
                cache[key] = image_material("g2f_hidden", None)
            else:
                cache[key] = image_material("g2f_" + k, tex.get(k + "|diffuse"), 0.35 if k == "eyes" else 0.5)
        mats.append(cache[key])
    return mats, hidden


_mats, _hidden = body_materials()
_keep = ~np.isin(base["poly_mat"], list(_hidden))
_starts = np.concatenate([[0], np.cumsum(base["poly_len"])[:-1]])
_loops = np.concatenate([np.arange(_starts[p], _starts[p] + base["poly_len"][p]) for p in np.nonzero(_keep)[0]])
_used = sorted(set(int(m) for m in np.unique(base["poly_mat"][_keep])))
_slot = {m: k for k, m in enumerate(_used)}
body = make_mesh("G2F", bverts, base["poly_len"][_keep], base["poly_idx"][_loops], base["uv_poly_idx"][_loops],
                 base["uvs"], np.array([_slot[int(m)] for m in base["poly_mat"][_keep]]), [_mats[m] for m in _used])

objects = []
for vam_path in ITEMS:
    folder = os.path.dirname(vam_path)
    stem = os.path.splitext(vam_path)[0]
    vaj = vl.lenient_json_loads(open(stem + ".vaj", encoding="utf-8").read())
    data = open(stem + ".vab", "rb").read()
    mesh = vl.parse_dazmesh_vab(data)
    offset = vl.wrap_surface_offset(vaj)
    tris, coeffs = mesh.wrap
    placed = vl.wrap_to_body(tris, coeffs, bverts, bnorm, offset)
    mats = []
    stor = {s["id"]: s for s in vaj["storables"]}
    for name in mesh.material_names:
        st = next((s for sid, s in stor.items() if sid.endswith("Material" + name)), {})
        mats.append(material(os.path.basename(stem) + "_" + name, folder, st))
    obj = make_mesh(os.path.basename(stem), placed, mesh.poly_len, mesh.poly_idx, mesh.uv_poly_idx, mesh.uvs,
                    mesh.poly_mat, mats)
    objects.append((vam_path, obj))

# lights / world
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.56, 0.6, 1)
scene.world = world
for name, rot, energy in (("key", (0.9, 0.2, 0.6), 3.5), ("fill", (1.1, 0.0, -1.2), 1.5), ("rim", (1.2, 0.0, 3.0), 2.0)):
    light = bpy.data.lights.new(name, "SUN")
    light.energy = energy
    lo = bpy.data.objects.new(name, light)
    lo.rotation_euler = rot
    scene.collection.objects.link(lo)
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 32
scene.view_settings.view_transform = "Filmic"


def render(path, target, size, direction, extent, res=(900, 1400)):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = extent
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = target + direction * 5
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


front = Vector((0, -1, 0))
center = Vector((0, 0, 0.9))
render(os.path.join(OUT, "preview_front.png"), center, None, front, 2.0)
render(os.path.join(OUT, "preview_side.png"), center, None, Vector((1, -0.35, 0)).normalized(), 2.0)
render(os.path.join(OUT, "preview_back.png"), center, None, Vector((0, 1, 0)), 2.0)
render(os.path.join(OUT, "preview_head.png"), Vector((0, 0, 1.62)), None, Vector((0.35, -1, 0.05)).normalized(), 0.5, (800, 800))
if "--face-closeups" in argv:
    render(os.path.join(OUT, "face_front.png"), Vector((0, 0, 1.64)), None, Vector((0, -1, 0)), 0.32, (800, 800))
    render(os.path.join(OUT, "face_34.png"), Vector((0, 0, 1.64)), None, Vector((0.7, -1, 0)).normalized(), 0.32, (800, 800))
    render(os.path.join(OUT, "face_side.png"), Vector((0, 0, 1.64)), None, Vector((1, 0, 0)), 0.32, (800, 800))
if "--closeups" in argv:
    render(os.path.join(OUT, "close_feet_side.png"), Vector((0.12, 0, 0.1)), None, Vector((1, 0, 0)), 0.45, (700, 700))
    render(os.path.join(OUT, "close_feet_front.png"), Vector((0, 0, 0.1)), None, Vector((0, -1, 0.25)).normalized(), 0.5, (700, 700))
    render(os.path.join(OUT, "close_hand.png"), Vector((0.62, 0, 1.46)), None, Vector((0, -1, 0.3)).normalized(), 0.35, (700, 700))
    render(os.path.join(OUT, "close_chest.png"), Vector((0, 0, 1.3)), None, Vector((0.2, -1, 0)).normalized(), 0.7, (700, 700))

if THUMBS:
    for vam_path, obj in objects:
        for other in scene.objects:
            if other.type == "MESH":
                other.hide_render = other is not obj
        pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (mn + mx) / 2
        ext = max(mx.x - mn.x, mx.z - mn.z) * 1.15
        jpg_png = os.path.splitext(vam_path)[0] + "_thumb.png"
        render(jpg_png, c, None, Vector((0.25, -1, 0.1)).normalized(), ext, (512, 512))
    for other in scene.objects:
        other.hide_render = False
print("PREVIEW_DONE")
