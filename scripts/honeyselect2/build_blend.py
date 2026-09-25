"""Blender (3.6+) side of the HoneySelect 2 exporter: scene.json -> .blend (+ FBX, preview).

    blender -b --factory-startup -P build_blend.py -- --scene <dir>/scene.json --out <dir>/<name>.blend
            [--fbx] [--no-preview]

scene.json comes from export_model.py (hs2_bundle.Scene.write): nodes in Unity space with
world matrices, parts whose vertices are already skinned to the rest pose, materials with
decoded PNG textures.  Unity (left-handed, Y up, 10 units = 1 m) -> Blender (right-handed,
Z up, metres) is (x, y, z) -> (-x, -z, y) * 0.1, so triangles are re-wound.
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
SCALE = float(SCENE.get("unit_scale", 0.1))
C3 = np.array([[-1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
report = {"parts": 0, "skipped": [], "materials": 0, "missing_textures": []}


def log(msg):
    print("[hs2] " + msg, flush=True)


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
name = SCENE.get("name", "hs2")

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
for n in nodes:
    eb = arm_data.edit_bones.new(n["name"])
    m = world[n["name"]]
    head = m.to_translation()
    kids = [world[c].to_translation() for c in children.get(n["name"], [])]
    kids = [k for k in kids if (k - head).length > 1e-4]
    if len(kids) == 1:
        tail = kids[0]
    else:
        axis = m.to_3x3() @ Vector((0.0, 1.0, 0.0))
        tail = head + axis * 0.02
    if (tail - head).length < 1e-4:
        tail = head + Vector((0.0, 0.0, 0.02))
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


def has_alpha(img):
    if img is None or img.channels < 4:
        return False
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    return float(px[3::4].min()) < 0.98


def tex_node(tree, png, slot_st, label, non_color=False, uv="UV0", location=(-900, 0)):
    img = image(png)
    if img is None:
        return None
    nodes_ = tree.nodes
    node = nodes_.new("ShaderNodeTexImage")
    node.image = img
    node.label = label
    node.location = location
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    uvn = nodes_.new("ShaderNodeUVMap")
    uvn.uv_map = uv
    uvn.location = (location[0] - 400, location[1])
    src = uvn.outputs["UV"]
    if slot_st and (abs(slot_st[0] - 1) > 1e-4 or abs(slot_st[1] - 1) > 1e-4 or abs(slot_st[2]) > 1e-4 or abs(slot_st[3]) > 1e-4):
        mp = nodes_.new("ShaderNodeMapping")
        mp.location = (location[0] - 200, location[1])
        mp.inputs["Scale"].default_value = (slot_st[0], slot_st[1], 1.0)
        mp.inputs["Location"].default_value = (slot_st[2], slot_st[3], 0.0)
        tree.links.new(src, mp.inputs["Vector"])
        src = mp.outputs["Vector"]
    tree.links.new(src, node.inputs["Vector"])
    return node


def srgb_to_linear(v):
    v = max(0.0, float(v))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(c):
    """Unity material / card colours are sRGB; Blender colour sockets are linear."""
    return (srgb_to_linear(c[0]), srgb_to_linear(c[1]), srgb_to_linear(c[2]), 1.0)


def mix(tree, a, b, fac, blend="MIX", location=(0, 0)):
    """Color mix node a (fac 0) -> b (fac 1)."""
    node = tree.nodes.new("ShaderNodeMixRGB")
    node.blend_type = blend
    node.location = location
    for sock, val in ((node.inputs[1], a), (node.inputs[2], b), (node.inputs[0], fac)):
        if hasattr(val, "is_linked") or hasattr(val, "links"):
            tree.links.new(val, sock)
        elif isinstance(val, (int, float)):
            sock.default_value = val
        else:
            sock.default_value = val
    return node.outputs[0]


def channel(tree, node, ch, location):
    """Scalar output of an image node: 'A' = alpha, 'R'/'G'/'B' = that colour channel,
    'MIN' = min(R, G, B) x alpha."""
    if ch == "A":
        return node.outputs["Alpha"]
    if ch == "MIN":
        # min(R, G, B) x alpha: the hair-like masks (eyebrow, underhair, lash, highlight)
        # come as grey-on-black, as white RGB + alpha, or with the mask in only one channel
        sep = tree.nodes.new("ShaderNodeSeparateRGB")
        sep.location = location
        tree.links.new(node.outputs["Color"], sep.inputs[0])
        lo = tree.nodes.new("ShaderNodeMath")
        lo.operation = "MINIMUM"
        lo.location = (location[0] + 150, location[1])
        tree.links.new(sep.outputs["R"], lo.inputs[0])
        tree.links.new(sep.outputs["G"], lo.inputs[1])
        lo2 = tree.nodes.new("ShaderNodeMath")
        lo2.operation = "MINIMUM"
        lo2.location = (location[0] + 300, location[1])
        tree.links.new(lo.outputs[0], lo2.inputs[0])
        tree.links.new(sep.outputs["B"], lo2.inputs[1])
        m = tree.nodes.new("ShaderNodeMath")
        m.operation = "MULTIPLY"
        m.location = (location[0] + 450, location[1])
        tree.links.new(lo2.outputs[0], m.inputs[0])
        tree.links.new(node.outputs["Alpha"], m.inputs[1])
        return m.outputs[0]
    sep = tree.nodes.new("ShaderNodeSeparateRGB")
    sep.location = location
    tree.links.new(node.outputs["Color"], sep.inputs[0])
    return sep.outputs[ch]


def scaled(tree, value, factor, location):
    if factor is None or abs(factor - 1.0) < 1e-4:
        return value
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = "MULTIPLY"
    node.use_clamp = True
    node.location = location
    tree.links.new(value, node.inputs[0])
    node.inputs[1].default_value = factor
    return node.outputs[0]


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
    colors, floats, over = spec.get("colors", {}), spec.get("floats", {}), spec.get("override", {})
    role = spec.get("role", "")
    base_color = over.get("base_color") or colors.get("_Color") or [1, 1, 1, 1]

    main = tex_node(tree, tex["_MainTex"], st.get("_MainTex"), "MainTex", location=(-900, 300)) if "_MainTex" in tex else None
    color = main.outputs["Color"] if main is not None else None
    alpha = None
    if main is not None:
        if spec.get("alpha_channel"):
            alpha = channel(tree, main, spec["alpha_channel"], (-600, 450))
        elif has_alpha(main.image):
            alpha = main.outputs["Alpha"]
    if spec.get("base_solid"):
        color = None
        base_color = spec["base_solid"]

    glass = role in ("clothes", "accessory") and floats.get("_Mode", 0) >= 2 and "_ColorMask" not in tex \
        and "_MainTex" not in tex
    if glass:
        # lenses / clear plastic: CmpAccessory draws these "rendAlpha" parts in colour 4
        c = over.get("color4") or colors.get("_Color") or [0.2, 0.2, 0.2, 0.2]
        base_color = c
        spec["opacity"] = max(0.05, float(c[3]) if len(c) > 3 else 0.2)
        color = None
        bsdf.inputs["Roughness"].default_value = 0.05
    elif role in ("clothes", "accessory"):
        # Illusion colour mask (`*_mc`): black = colour 1, R = colour 2, G = colour 3,
        # B = colour 4 (metal fittings), each multiplied into the (grey) main texture
        grey = color if color is not None else (1, 1, 1, 1)

        def slot_color(i):
            fb = "_Color" if i == 1 else "_Color%d" % i
            return over.get("color%d" % i) or colors.get(fb) or [1, 1, 1, 1]

        cur = mix(tree, grey, rgb(slot_color(1)), 1.0, "MULTIPLY", location=(-400, 300))
        cm = tex_node(tree, tex["_ColorMask"], st.get("_ColorMask"), "ColorMask", True, location=(-900, -50)) \
            if "_ColorMask" in tex else None
        if cm is not None:
            sep = tree.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-600, -50)
            tree.links.new(cm.outputs["Color"], sep.inputs[0])
            for i, ch in ((2, "R"), (3, "G"), (4, "B")):
                tinted = mix(tree, grey, rgb(slot_color(i)), 1.0, "MULTIPLY", location=(-400, 200 - i * 100))
                cur = mix(tree, cur, tinted, sep.outputs[ch], location=(-200, 200 - i * 100))
        color = cur
    elif role == "hair":
        # HS2 hair textures carry no colour: main R = 1, G/B = strand detail, A = strand
        # alpha.  Colour = card base colour, blended to the top (grade mask G, roots) and
        # under colour (grade mask B, tips), darkened by the AO map, lightly modulated by G.
        cur = rgb(over.get("base_color") or colors.get("_Color") or [0.3, 0.25, 0.2, 1])
        if "_ColorMask" in tex:
            cm = tex_node(tree, tex["_ColorMask"], st.get("_ColorMask"), "GradeMask", True, location=(-900, -50))
            if cm is not None:
                sep = tree.nodes.new("ShaderNodeSeparateRGB")
                sep.location = (-600, -50)
                tree.links.new(cm.outputs["Color"], sep.inputs[0])
                for ch, k, fb, y in (("G", "top_color", "_Color2", 100), ("B", "under_color", "_Color3", 0)):
                    c2 = over.get(k) or colors.get(fb)
                    if c2:
                        cur = mix(tree, cur, rgb(c2), sep.outputs[ch], location=(-300, y))
        if "_Occlusion" in tex:
            oc = tex_node(tree, tex["_Occlusion"], st.get("_Occlusion"), "AO", True, location=(-900, -400))
            if oc is not None:
                cur = mix(tree, cur, oc.outputs["Color"], 1.0, "MULTIPLY", location=(-150, 0))
        if main is not None:
            detail = channel(tree, main, "G", (-600, 150))
            rng = tree.nodes.new("ShaderNodeMapRange")
            rng.location = (-400, 150)
            rng.inputs["To Min"].default_value = 0.85
            rng.inputs["To Max"].default_value = 1.12
            tree.links.new(detail, rng.inputs["Value"])
            gain = tree.nodes.new("ShaderNodeCombineRGB")
            gain.location = (-250, 150)
            for i in range(3):
                tree.links.new(rng.outputs["Result"], gain.inputs[i])
            cur = mix(tree, cur, gain.outputs[0], 1.0, "MULTIPLY", location=(-50, 100))
            alpha = main.outputs["Alpha"]
        color = cur
        bsdf.inputs["Roughness"].default_value = 0.45
        bsdf.inputs["Specular"].default_value = 0.35
    elif color is not None and spec.get("skin_ratio"):
        # card skin colour relative to the default one (already a linear ratio)
        r = spec["skin_ratio"]
        color = mix(tree, color, (r[0], r[1], r[2], 1.0), 1.0, "MULTIPLY", location=(-300, 250))
    elif color is not None and spec.get("base_mult"):
        color = mix(tree, color, rgb(spec["base_mult"]), 1.0, "MULTIPLY", location=(-300, 250))
    elif color is not None and role not in ("tear", "skin_head", "skin_body", "eye", "eyelash") \
            and base_color and min(base_color[:3]) < 0.999:
        color = mix(tree, color, rgb(base_color), 1.0, "MULTIPLY", location=(-300, 250))

    # overlays the game composites into the base (eyebrows / makeup on the face, nipples and
    # underhair on the body, iris / pupil / highlight on the eyes): channel-packed masks,
    # each alpha-over in its own UV set
    y = -350
    for ov in spec.get("overlays", []):
        if color is None:
            color = rgb(base_color)
        node = tex_node(tree, ov["tex"], ov.get("st"), ov.get("label", "overlay"), location=(-1100, y), uv=ov.get("uv", "UV0"))
        if node is None:
            continue
        node.extension = "CLIP"
        a = scaled(tree, channel(tree, node, ov.get("alpha", "A"), (-800, y - 100)), ov.get("strength"), (-650, y - 100))
        if ov.get("color") is not None:
            ov_col = rgb(ov["color"])
            if ov.get("shade"):
                sh = channel(tree, node, ov["shade"], (-800, y - 200))
                ov_col = mix(tree, (0, 0, 0, 1), ov_col, sh, location=(-550, y - 150))
        else:
            ov_col = node.outputs["Color"]
        color = mix(tree, color, ov_col, a, ov.get("blend", "MIX"), location=(-300, y))
        y -= 320

    if color is None:
        bsdf.inputs["Base Color"].default_value = rgb(base_color)
    elif isinstance(color, tuple):
        bsdf.inputs["Base Color"].default_value = color
    else:
        tree.links.new(color, bsdf.inputs["Base Color"])

    if "_BumpMap" in tex and role not in ("eye",):
        nt = tex_node(tree, tex["_BumpMap"], st.get("_BumpMap"), "Normal", True, location=(-900, -1200))
        if nt is not None:
            nm = tree.nodes.new("ShaderNodeNormalMap")
            nm.location = (-300, -1100)
            nm.uv_map = "UV0"
            nm.inputs["Strength"].default_value = 0.6 if role.startswith("skin") else 1.0
            tree.links.new(nt.outputs["Color"], nm.inputs["Color"])
            tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    if role.startswith("skin") or role == "nipple":
        bsdf.inputs["Roughness"].default_value = 0.5
        bsdf.inputs["Subsurface"].default_value = 0.03
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        bsdf.inputs["Subsurface Color"].default_value = (0.8, 0.4, 0.3, 1.0)
    elif role == "eye":
        bsdf.inputs["Roughness"].default_value = 0.1
    elif role in ("clothes", "accessory") and not glass:
        gloss = over.get("gloss")
        if gloss is None:
            gloss = floats.get("_Glossiness", floats.get("_Smoothness"))
        if gloss is not None:
            bsdf.inputs["Roughness"].default_value = max(0.08, 1.0 - float(gloss))
        metal = over.get("metallic", floats.get("_Metallic"))
        if metal is not None:
            bsdf.inputs["Metallic"].default_value = min(max(float(metal), 0.0), 1.0)
    elif role in ("tooth", "tongue"):
        bsdf.inputs["Roughness"].default_value = 0.3

    if spec.get("opacity") is not None:
        if alpha is None:
            bsdf.inputs["Alpha"].default_value = float(spec["opacity"])
        else:
            alpha = scaled(tree, alpha, float(spec["opacity"]), (-150, 500))
    if alpha is not None and role not in ("skin_body", "skin_head", "eye"):
        tree.links.new(alpha, bsdf.inputs["Alpha"])
    if (alpha is not None and role not in ("skin_body", "skin_head", "eye")) or spec.get("opacity") is not None:
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
    mat.use_backface_culling = False
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
bone_names = set(arm_data.bones.keys())
meshes = []
for part in SCENE["parts"]:
    data = np.load(os.path.join(SRC_DIR, part["npz"]))
    verts = conv_points(data["vertices"])
    idx = data["indices"]
    faces, face_mat = [], []
    for si, (first, count, topo) in enumerate(part["submeshes"]):
        if topo not in (0,):
            continue
        tri = idx[first:first + count].reshape(-1, 3)
        faces.append(tri[:, [0, 2, 1]])
        face_mat.append(np.full(len(tri), si, dtype=np.int32))
    if not faces:
        report["skipped"].append(part["name"])
        continue
    faces = np.concatenate(faces)
    face_mat = np.concatenate(face_mat)
    good = (faces.max(axis=1) < len(verts))
    faces, face_mat = faces[good], face_mat[good]
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
        me.use_auto_smooth = True
        me.normals_split_custom_set(nrm.tolist())
    for key in part["materials"]:
        me.materials.append(material(key))
    obj = bpy.data.objects.new(part["name"], me)
    scene.collection.objects.link(obj)
    obj["hs2_source"] = part["source"]
    obj["hs2_role"] = part["role"]
    # skin
    bones = part["bones"]
    bi, bw = data["bone_indices"], data["bone_weights"]
    groups = {}
    for slot in range(bi.shape[1]):
        for b in np.unique(bi[:, slot]):
            bname = bones[b] if b < len(bones) else part["node"]
            if bname not in bone_names:
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
    # shape keys
    if part.get("shape_keys"):
        obj.shape_key_add(name="Basis", from_mix=False)
        base = verts.astype(np.float32)
        for si, sname in enumerate(part["shape_keys"]):
            key = obj.shape_key_add(name=sname, from_mix=False)
            co = base.copy()
            idx_s = data["shape%d_idx" % si]
            co[idx_s] += (data["shape%d_delta" % si].astype(np.float64) @ C3.T * SCALE).astype(np.float32)
            key.data.foreach_set("co", co.ravel())
    meshes.append(obj)
    report["parts"] += 1
log("meshes: %d (skipped %d)" % (report["parts"], len(report["skipped"])))

# ---------------------------------------------------------------- save
out_dir = os.path.dirname(os.path.abspath(OUT_PATH))
os.makedirs(out_dir, exist_ok=True)
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
    front = Vector((0.0, -1.0, 0.0))  # HS2 characters face -Y after the axis change
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
    ortho = max(extent.z * 1.08, max(extent.x, extent.y) * 1.3)
    render(base + "_preview.png", center, ortho, (900, 1400) if extent.z > extent.x else (1200, 1000), height * 3, front)
    head = arm.data.bones.get("cf_J_FaceRoot") or arm.data.bones.get("cf_J_Head")
    if head is not None and extent.z > 1.0:
        hp = arm.matrix_world @ head.head_local + Vector((0.0, 0.0, 0.08))
        render(base + "_face.png", hp, 0.34, (900, 900), 2.0, front)
    three_q = Vector((0.7, -0.7, 0.0)).normalized()
    render(base + "_side.png", center, ortho, (900, 1400) if extent.z > extent.x else (1200, 1000), height * 3, three_q)

print("HS2_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
