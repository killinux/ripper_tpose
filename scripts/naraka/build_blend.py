"""Blender (3.6+) side of the NARAKA exporter: scene.json -> .blend (+ FBX, preview).

    blender -b --factory-startup -P build_blend.py -- --scene <dir>/scene.json --out <dir>/<name>.blend
            [--fbx] [--no-preview]

scene.json comes from naraka_scene.Scene.write: nodes (full transform paths) with rest
world matrices in Unity space, parts whose vertices are already in the rest pose,
materials with decoded PNG textures.  Unity (left-handed, Y up, metres) -> Blender
(right-handed, Z up) is (x, y, z) -> (-x, -z, y), so triangles are re-wound.  Bone names
are the leaf names of the paths (Blender caps names at 63 bytes); duplicates get ".001".
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


SCENE_PATH = arg("--scene")
OUT_PATH = arg("--out")
WANT_FBX = "--fbx" in argv
NO_PREVIEW = "--no-preview" in argv
SRC_DIR = os.path.dirname(os.path.abspath(SCENE_PATH))
with open(SCENE_PATH, encoding="utf-8") as f:
    SCENE = json.load(f)
SCALE = float(SCENE.get("unit_scale", 1.0))
C3 = np.array([[-1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
report = {"parts": 0, "skipped": [], "materials": 0, "missing_textures": []}


def log(msg):
    print("[naraka] " + msg, flush=True)


def conv_points(arr):
    return (np.asarray(arr, dtype=np.float64) @ C3.T) * SCALE


def conv_matrix(m):
    m = np.asarray(m, dtype=np.float64)
    r = C3 @ m[:3, :3] @ C3.T
    r = r / np.maximum(np.linalg.norm(r, axis=0, keepdims=True), 1e-12)  # drop scale
    out = np.eye(4)
    out[:3, :3] = r
    out[:3, 3] = C3 @ m[:3, 3] * SCALE
    return Matrix(out.tolist())


# ---------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
name = SCENE.get("name", "naraka")

# ---------------------------------------------------------------- armature
arm_data = bpy.data.armatures.new(name + "_Armature")
arm = bpy.data.objects.new(name + "_Armature", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
arm_data.display_type = "STICK"
bpy.ops.object.mode_set(mode="EDIT")
nodes = SCENE["nodes"]
children = {}
for n in nodes:
    children.setdefault(n["parent"], []).append(n["name"])
world = {n["name"]: conv_matrix(n["world"]) for n in nodes}
ebones = {}
BONE = {}          # node path -> bone name
for n in nodes:
    leaf = n["name"].rsplit("/", 1)[-1][:60]
    eb = arm_data.edit_bones.new(leaf)
    BONE[n["name"]] = eb.name
    m = world[n["name"]]
    head = m.to_translation()
    kids = [world[c].to_translation() for c in children.get(n["name"], [])]
    kids = [k for k in kids if (k - head).length > 1e-4]
    if len(kids) == 1:
        tail = kids[0]
    else:
        axis = m.to_3x3() @ Vector((1.0, 0.0, 0.0))   # 3ds Max bones run along local X
        tail = head + axis * 0.03
    if (tail - head).length < 1e-4:
        tail = head + Vector((0.0, 0.0, 0.03))
    eb.head, eb.tail = head, tail
    eb.align_roll(m.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    ebones[n["name"]] = eb
for n in nodes:
    if n["parent"] in ebones:
        ebones[n["name"]].parent = ebones[n["parent"]]
bpy.ops.object.mode_set(mode="OBJECT")
log("armature: %d bones" % len(nodes))

# ---------------------------------------------------------------- materials
IMAGES = {}


def image(png):
    if png in IMAGES:
        return IMAGES[png]
    path = os.path.join(SRC_DIR, "textures", png)
    if not os.path.isfile(path):
        report["missing_textures"].append(png)
        IMAGES[png] = None
        return None
    img = bpy.data.images.load(path, check_existing=True)
    IMAGES[png] = img
    return img


def tex_node(tree, png, st, label, non_color=False, uv="UV0", location=(-900, 0)):
    img = image(png)
    if img is None:
        return None
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.label = label
    node.location = location
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    uvn = tree.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = uv
    uvn.location = (location[0] - 400, location[1])
    src = uvn.outputs["UV"]
    if st and (abs(st[0] - 1) > 1e-4 or abs(st[1] - 1) > 1e-4 or abs(st[2]) > 1e-4 or abs(st[3]) > 1e-4):
        mp = tree.nodes.new("ShaderNodeMapping")
        mp.location = (location[0] - 200, location[1])
        mp.inputs["Scale"].default_value = (st[0], st[1], 1.0)
        mp.inputs["Location"].default_value = (st[2], st[3], 0.0)
        tree.links.new(src, mp.inputs["Vector"])
        src = mp.outputs["Vector"]
    tree.links.new(src, node.inputs["Vector"])
    return node


def srgb_to_linear(v):
    v = max(0.0, float(v))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(c):
    return (srgb_to_linear(c[0]), srgb_to_linear(c[1]), srgb_to_linear(c[2]), 1.0)


def separate(tree, color_socket, location):
    sep = tree.nodes.new("ShaderNodeSeparateRGB")
    sep.location = location
    tree.links.new(color_socket, sep.inputs[0])
    return sep


def mix(tree, a, b, fac, blend="MIX", location=(0, 0)):
    node = tree.nodes.new("ShaderNodeMixRGB")
    node.blend_type = blend
    node.location = location
    for sock, val in ((node.inputs[1], a), (node.inputs[2], b), (node.inputs[0], fac)):
        if hasattr(val, "links") or hasattr(val, "is_linked"):
            tree.links.new(val, sock)
        else:
            sock.default_value = val
    return node.outputs[0]


def culling(key):
    """Unity CullMode of a material: 0 off, 1 front, 2 back.  General LX22 shaders
    call it _Culling, the effect/character ones _Cull."""
    if key is None or key not in SCENE["materials"]:
        return 0
    fl = SCENE["materials"][key].get("floats", {})
    return int(fl.get("_Culling", fl.get("_Cull", 0)) or 0)


def build_material(key, spec):
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tex, st = spec["textures"], spec.get("tex_st", {})
    colors, floats = spec.get("colors", {}), spec.get("floats", {})
    role = spec.get("role", "")
    kw = spec.get("keywords", "")
    tint = colors.get("_Color") or [1, 1, 1, 1]

    main = tex_node(tree, tex["_MainTex"], st.get("_MainTex"), "MainTex", location=(-900, 300)) \
        if "_MainTex" in tex else None
    color = main.outputs["Color"] if main is not None else None
    alpha = None

    if role == "hair" and spec.get("hair_color"):
        # LX22 hair: _MainTex is a strand-ID map, alpha = strand coverage; colour is a
        # flat approximation (mean of the outfit's SH table)
        base = rgb(spec["hair_color"])
        if main is not None:
            sep = separate(tree, main.outputs["Color"], (-600, 300))
            rng = tree.nodes.new("ShaderNodeMapRange")
            rng.location = (-420, 300)
            rng.inputs["To Min"].default_value = 0.75
            rng.inputs["To Max"].default_value = 1.15
            tree.links.new(sep.outputs["B"], rng.inputs["Value"])
            color = mix(tree, base, rng.outputs["Result"], 1.0, "MULTIPLY", location=(-250, 300))
            color = mix(tree, base, color, 0.5, "MIX", location=(-100, 300))
            alpha = main.outputs["Alpha"]
        else:
            color = base
        bsdf.inputs["Roughness"].default_value = 0.45
    elif main is not None:
        if min(tint[:3]) < 0.999:
            color = mix(tree, color, rgb(tint), 1.0, "MULTIPLY", location=(-300, 300))
        if "_USE_CUTOUT" in kw or role in ("eyelash", "hair") or floats.get("_Mode", 0) >= 1:
            alpha = main.outputs["Alpha"]

    # mrav: R metallic, G roughness, B ambient occlusion
    if "_SpecGlossMap" in tex and role not in ("skin_body", "skin_head"):
        mr = tex_node(tree, tex["_SpecGlossMap"], st.get("_SpecGlossMap"), "MRAV", True, location=(-900, -150))
        if mr is not None:
            sep = separate(tree, mr.outputs["Color"], (-600, -150))
            tree.links.new(sep.outputs["R"], bsdf.inputs["Metallic"])
            tree.links.new(sep.outputs["G"], bsdf.inputs["Roughness"])
            if color is not None and not isinstance(color, tuple):
                color = mix(tree, color, sep.outputs["B"], 0.8, "MULTIPLY", location=(-100, 150))

    if color is None:
        bsdf.inputs["Base Color"].default_value = rgb(tint)
    elif isinstance(color, tuple):
        bsdf.inputs["Base Color"].default_value = color
    else:
        tree.links.new(color, bsdf.inputs["Base Color"])

    # _NormalBentMap (skin) is not a plain tangent normal map - it blotches; skip it
    ntex = tex.get("_BumpMap")
    if ntex and role not in ("eye", "hair"):
        slot = "_BumpMap"
        nt = tex_node(tree, ntex, st.get(slot), "Normal", True, location=(-900, -500))
        if nt is not None:
            nm = tree.nodes.new("ShaderNodeNormalMap")
            nm.location = (-300, -500)
            nm.uv_map = "UV0"
            nm.inputs["Strength"].default_value = 0.8
            tree.links.new(nt.outputs["Color"], nm.inputs["Color"])
            tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    if role.startswith("skin"):
        bsdf.inputs["Roughness"].default_value = 0.5
        bsdf.inputs["Subsurface"].default_value = 0.03
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        bsdf.inputs["Subsurface Color"].default_value = (0.8, 0.4, 0.3, 1.0)
    elif role == "eye":
        bsdf.inputs["Roughness"].default_value = 0.1

    if alpha is not None:
        tree.links.new(alpha, bsdf.inputs["Alpha"])
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
    # culling as in the game: cull-back materials hide back faces; cull-front ones
    # (the *_cf inner lining of double-sided cloth) get their faces flipped at
    # mesh build time, so they too show only what the game shows
    mat.use_backface_culling = culling(key) in (1, 2)
    report["materials"] += 1
    return mat


MATS = {}


def material(key):
    if key is None:
        return None
    if key not in MATS:
        MATS[key] = build_material(key, SCENE["materials"][key])
    return MATS[key]


# ---------------------------------------------------------------- meshes
meshes = []
for part in SCENE["parts"]:
    data = np.load(os.path.join(SRC_DIR, part["npz"]))
    verts = conv_points(data["vertices"])
    idx = data["indices"]
    faces, face_mat, face_flip = [], [], []
    for si, (first, count, topo) in enumerate(part["submeshes"]):
        if topo not in (0,):
            continue
        tri = idx[first:first + count].reshape(-1, 3)
        mi = min(si, max(len(part["materials"]) - 1, 0))
        flip = bool(part["materials"]) and culling(part["materials"][mi]) == 1
        # the handedness change re-winds every triangle; cull-front ones are flipped back
        faces.append(tri if flip else tri[:, [0, 2, 1]])
        face_mat.append(np.full(len(tri), mi, dtype=np.int32))
        face_flip.append(np.full(len(tri), flip))
    if not faces:
        report["skipped"].append(part["name"])
        continue
    faces = np.concatenate(faces)
    face_mat = np.concatenate(face_mat)
    face_flip = np.concatenate(face_flip)
    good = (faces.max(axis=1) < len(verts))
    faces, face_mat, face_flip = faces[good], face_mat[good], face_flip[good]
    me = bpy.data.meshes.new(part["name"])
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(len(faces) * 3)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, len(faces) * 3, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(faces), 3, dtype=np.int32))
    me.polygons.foreach_set("material_index", face_mat)
    for uv_key, uv_name in (("uv0", "UV0"), ("uv1", "UV1"), ("uv2", "UV2")):
        if uv_key in data:
            layer = me.uv_layers.new(name=uv_name)
            uv = data[uv_key][faces.ravel()]
            layer.data.foreach_set("uv", uv.astype(np.float32).ravel())
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    if "normals" in data and len(me.loops) == len(faces) * 3:
        nrm = (data["normals"].astype(np.float64) @ C3.T)[faces.ravel()]
        nrm[np.repeat(face_flip, 3)] *= -1.0
        me.use_auto_smooth = True
        me.normals_split_custom_set(nrm.tolist())
    for key in part["materials"]:
        me.materials.append(material(key))
    obj = bpy.data.objects.new(part["name"], me)
    scene.collection.objects.link(obj)
    obj["naraka_source"] = part["source"]
    obj["naraka_role"] = part["role"]
    bones = part["bones"]
    bi, bw = data["bone_indices"], data["bone_weights"]
    groups = {}
    for slot in range(bi.shape[1]):
        for b in np.unique(bi[:, slot]):
            path = bones[b] if b < len(bones) else None
            bname = BONE.get(path)
            if bname is None:
                continue
            sel = np.nonzero((bi[:, slot] == b) & (bw[:, slot] > 0))[0]
            if len(sel) == 0:
                continue
            vg = groups.get(bname) or obj.vertex_groups.new(name=bname)
            groups[bname] = vg
            w = bw[sel, slot]
            for value in np.unique(w):
                vg.add(sel[w == value].tolist(), float(value), "ADD")
    obj.parent = arm
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    meshes.append(obj)
    report["parts"] += 1
log("meshes: %d (skipped %d)" % (report["parts"], len(report["skipped"])))

# ---------------------------------------------------------------- save
os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
for img in bpy.data.images:
    if img.filepath:
        img.pack()
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH, compress=True)
report["blend"] = OUT_PATH
log("saved " + OUT_PATH)
if WANT_FBX:
    fbx = os.path.splitext(OUT_PATH)[0] + ".fbx"
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=False, add_leaf_bones=False,
                             path_mode="COPY", embed_textures=True, mesh_smooth_type="FACE")
    report["fbx"] = fbx
    log("saved " + fbx)


# ---------------------------------------------------------------- preview (after the save)
def frame(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, mx - mn


def render(path, center, ortho, size, distance, direction):
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho
    cam_data.clip_start = 0.01
    cam_data.clip_end = distance * 10
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + direction * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Filmic"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_soft_shadows = True
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    log("rendered " + path)


if not NO_PREVIEW and meshes:
    center, extent = frame(meshes)
    height = max(extent.x, extent.y, extent.z, 1e-3)
    front = Vector((0.0, -1.0, 0.0))  # Unity +Z (character forward) -> Blender -Y
    for lname, loc, energy in (("Key", (1.0, -1.2, 1.2), 3.0), ("Fill", (-1.2, -0.8, 0.5), 1.3), ("Rim", (0.3, 1.2, 1.0), 1.8)):
        light = bpy.data.lights.new(lname, "SUN")
        light.energy = energy
        light.angle = math.radians(10)
        lo = bpy.data.objects.new(lname, light)
        scene.collection.objects.link(lo)
        lo.location = center + Vector(loc) * height
        lo.rotation_euler = (center - lo.location).to_track_quat("-Z", "Y").to_euler()
    wd = bpy.data.worlds.new("PreviewWorld")
    wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs["Color"].default_value = (0.58, 0.58, 0.62, 1.0)
    scene.world = wd
    base = os.path.splitext(OUT_PATH)[0]

    def shot(path, direction, width, height_):
        """Ortho render that frames a width x height_ (metres) silhouette."""
        tall = height_ >= width
        res = (900, 1400) if tall else (1400, 900)
        long_, short = max(res), min(res)
        ortho = max(height_, width * long_ / short) if tall else max(width, height_ * long_ / short)
        render(path, center, ortho * 1.08, res, height * 3, direction)

    head = arm.data.bones.get("gMan Head")
    if head is not None:
        # characters: front, three-quarter, back, face
        shot(base + "_preview.png", front, extent.x, extent.z)
        shot(base + "_side.png", Vector((0.7, -0.7, 0.0)).normalized(), max(extent.x, extent.y), extent.z)
        shot(base + "_back.png", Vector((0.0, 1.0, 0.0)), extent.x, extent.z)
        if extent.z > 1.0:
            hp = arm.matrix_world @ head.head_local + Vector((0.0, 0.0, 0.08))
            render(base + "_face.png", hp, 0.36, (900, 900), 2.0, front)
    else:
        # weapons / props / creatures: look along the thinnest axis (a sword lying
        # along Y is seen from the side, not end-on), plus a three-quarter view
        ax = min(range(3), key=lambda i: extent[i])
        if ax == 1 or extent.z > 1.2 * max(extent.x, extent.y):
            d, w, h = front, extent.x, extent.z
        elif ax == 0:
            d, w, h = Vector((1.0, 0.0, 0.0)), extent.y, extent.z
        else:
            d, w, h = Vector((0.0, -0.05, 1.0)).normalized(), extent.x, extent.y
        shot(base + "_preview.png", d, w, h)
        shot(base + "_side.png", Vector((0.7, -0.7, 0.5)).normalized(), max(extent.x, extent.y) * 1.2,
             max(extent.z, max(extent.x, extent.y) * 0.5))

print("NARAKA_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
