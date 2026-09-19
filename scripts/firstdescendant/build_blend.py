"""The First Descendant - assemble CUE4Parse ActorX parts into one textured .blend (Blender 3.6, headless).

    blender --background --factory-startup --python build_blend.py -- --spec <spec.json> [--no-preview] [--smooth]

spec.json (written by export_model.ps1):
    { "id": "Viessa", "out_dir": "D:/tfd_exports/blend/Viessa",
      "materials": "D:/tfd_exports/blend/Viessa/materials.json",
      "parts": [ {"name": "Full", "psk": "D:/.../PC_003_A0101.pskx"} ] }

materials.json comes from resolve_textures.py: per part, per slot, the material
instance name, the PNGs it references and UE Viewer's .props.txt with its
parameters.  What this script does:

  1. imports every part with io_scene_psk_psa (real material slot names, morph
     targets as shape keys, vertex colours);
  2. merges the per-part skeletons into one armature by bone name;
  3. builds a material per slot from the instance's textures - TFD conventions:
       _C albedo, _N normal (DirectX, green flipped), _P = AO / Roughness / Metallic
       (channel-packed; skin keeps metallic 0), _FX emissive mask x Emissive_col,
       _ID is the dye mask (player recolour; the default look is the albedo, so unused),
       hair = shared Female/Male_HairTex_*_P (A alpha, G root->tip) x Hair_Root/TipColor,
       eyes = sclera + veins + a procedural iris (MetaHuman-style parameters),
       eyebrow/eyelash = the parent material's strand texture, EyeOCC / TearLine = clear;
  4. copies the textures into <out_dir>/textures, saves <id>.blend with relative
     paths and renders preview.png / preview_face.png.

Prints TFD_REPORT={json} for the PowerShell wrapper.
"""
import json
import math
import os
import re
import shutil
import sys

import addon_utils
import bpy
from mathutils import Matrix, Vector

PSK_ADDON = "io_scene_psk_psa"
if addon_utils.enable(PSK_ADDON, default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for Blender 3.6 (needed for PSK/PSKX import)")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--spec" not in argv:
    raise SystemExit("usage: blender --background --factory-startup --python build_blend.py -- --spec spec.json [--no-preview] [--smooth]")
SPEC = json.load(open(argv[argv.index("--spec") + 1], encoding="utf-8"))
NO_PREVIEW = "--no-preview" in argv
SMOOTH = "--smooth" in argv
MODEL_ID = SPEC["id"]
OUT_DIR = os.path.normpath(SPEC["out_dir"])
TEX_DIR = os.path.join(OUT_DIR, "textures")
PARTS = SPEC["parts"]
MATERIALS = {}
if SPEC.get("materials") and os.path.isfile(SPEC["materials"]):
    for part in json.load(open(SPEC["materials"], encoding="utf-8")).get("parts", []):
        MATERIALS[os.path.normcase(os.path.normpath(part["pskx"]))] = part["slots"]

MASK_CLIP = 0.33
report = {"id": MODEL_ID, "parts": [], "materials": {}, "missing_textures": [], "warnings": []}


def log(msg):
    print("[tfd] " + msg, flush=True)


# ---------------------------------------------------------------- import
def import_psk(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(
        filepath=path,
        should_import_vertex_colors=True,
        should_import_vertex_normals=not SMOOTH,
        should_import_extra_uvs=True,
        should_import_mesh=True,
        should_import_materials=True,
        should_import_skeleton=True,
        should_import_shape_keys=True,
        bone_length=1.0,
    )
    created = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in created if o.type == "ARMATURE"), None)
    meshes = [o for o in created if o.type == "MESH"]
    return arm, meshes


imported = []
for prt in PARTS:
    psk = os.path.normpath(prt["psk"])
    if not os.path.isfile(psk):
        report["warnings"].append("missing PSK: " + psk)
        log("MISSING " + psk)
        continue
    arm, meshes = import_psk(psk)
    if arm is None or not meshes:
        report["warnings"].append("no armature/mesh from " + psk)
        continue
    arm.name = "%s_%s_rig" % (MODEL_ID, prt["name"])
    for i, mesh in enumerate(meshes):
        mesh.name = "%s_%s%s" % (MODEL_ID, prt["name"], "" if i == 0 else "_%d" % i)
        mesh["tfd_pskx"] = psk
    imported.append((prt, arm, meshes))
    report["parts"].append({
        "name": prt["name"], "psk": os.path.basename(psk), "bones": len(arm.data.bones),
        "vertices": sum(len(m.data.vertices) for m in meshes),
        "faces": sum(len(m.data.polygons) for m in meshes),
        "slots": max((len(m.material_slots) for m in meshes), default=0),
        "shape_keys": sum(len(m.data.shape_keys.key_blocks) - 1 for m in meshes if m.data.shape_keys),
    })
    log("imported %s: %d bones, %d verts, %d shape keys" % (
        prt["name"], len(arm.data.bones), report["parts"][-1]["vertices"], report["parts"][-1]["shape_keys"]))

if not imported:
    print("TFD_REPORT=" + json.dumps({**report, "error": "nothing imported"}), flush=True)
    raise SystemExit("nothing imported")

# ---------------------------------------------------------------- one rig
base_prt, base_arm, _ = max(imported, key=lambda t: len(t[1].data.bones))
base_arm.name = MODEL_ID + "_rig"
base_bones = {b.name for b in base_arm.data.bones}
meshes_all = []
socket_parts = set()          # parts whose rig was consumed by the socket rule below
for prt, arm, meshes in imported:
    for mesh in meshes:
        meshes_all.append(mesh)
        if arm is base_arm or prt["name"] in socket_parts:
            continue
        # A part authored around its own root (an accessory such as a skin's helmet: a
        # 3-bone rig at the origin) must first be moved to where the base rig keeps
        # that bone, or it stays at the feet after re-binding.  The delta comes from
        # the root-most shared bone; for a same-skeleton part it is the identity.
        mw = arm.matrix_world.copy()
        shared = [b for b in arm.data.bones if b.name in base_bones]
        if not shared:
            # A socket accessory: its own little rig (Head_Root -> Pt_Head -> Bn_Socket_*)
            # shares no bone with the character and the mesh is authored around the
            # origin; the game attaches it to a socket bone.  Bone-parent it there.
            anchor = None
            for cand in ("Bn_Socket_Head", "Bip001-Head", "head", "Head", "Bip001-Neck"):
                anchor = base_arm.data.bones.get(cand)
                if anchor is not None:
                    break
            if anchor is None:
                anchor = base_arm.data.bones[0]
            target = base_arm.matrix_world @ anchor.matrix_local
            for m in meshes:
                for mod in list(m.modifiers):
                    if mod.type == "ARMATURE":
                        m.modifiers.remove(mod)
                m.parent = base_arm
                m.parent_type = "BONE"
                m.parent_bone = anchor.name
                m.matrix_parent_inverse = Matrix.Identity(4)
                m.matrix_world = target @ m.matrix_world
            report["warnings"].append("%s: socket accessory, bone-parented to %s" % (prt["name"], anchor.name))
            bpy.data.objects.remove(arm, do_unlink=True)
            socket_parts.add(prt["name"])
            continue
        if shared:
            def _depth(bone):
                d = 0
                while bone.parent:
                    bone, d = bone.parent, d + 1
                return d
            ref = min(shared, key=_depth)
            part_m = mw @ ref.matrix_local
            base_m = base_arm.matrix_world @ base_arm.data.bones[ref.name].matrix_local
            delta = base_m @ part_m.inverted()
            if (delta.to_translation().length > 0.01 or
                    abs(delta.to_quaternion().angle) > math.radians(0.5)):
                for m in meshes:
                    m.matrix_world = delta @ m.matrix_world
                mw = delta @ mw
                report["warnings"].append("%s: placed via %s (moved %.1f cm)"
                                          % (prt["name"], ref.name, delta.to_translation().length))
        # Capture bone data as plain values BEFORE the mode switch: Blender frees the
        # Python bone references across it and reading them afterwards yields garbage.
        want = [(b.name, mw @ b.head_local, mw @ b.tail_local, b.parent.name if b.parent else None)
                for b in arm.data.bones if b.name not in base_bones]
        if want:
            bpy.context.view_layer.objects.active = base_arm
            bpy.ops.object.mode_set(mode="EDIT")
            for name, head, tail, _parent in want:
                eb = base_arm.data.edit_bones.new(name)
                eb.head = head
                eb.tail = tail if (tail - head).length > 1e-4 else head + Vector((0.0, 0.0, 1.0))
            for name, _h, _t, parent in want:
                child = base_arm.data.edit_bones.get(name)
                par = base_arm.data.edit_bones.get(parent) if parent else None
                if child and par:
                    child.parent = par
            bpy.ops.object.mode_set(mode="OBJECT")
            base_bones.update(name for name, _h, _t, _p in want)
        for m in mesh.modifiers:
            if m.type == "ARMATURE":
                m.object = base_arm
        mesh.parent = base_arm
    if arm is not base_arm and prt["name"] not in socket_parts:
        bpy.data.objects.remove(arm, do_unlink=True)


# ---------------------------------------------------------------- materials
_PARAM_RE = re.compile(r"ParameterInfo = \{ Name=(?P<name>[^}]*?) \}\s*ParameterValue = (?P<value>[^\n]*)")


def read_props(path):
    """UE Viewer .props.txt -> {param name: float | (r,g,b,a)}; later duplicates win."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    text = open(path, encoding="utf-8", errors="replace").read()
    for m in _PARAM_RE.finditer(text):
        name, value = m.group("name").strip(), m.group("value").strip()
        col = re.match(r"\{ R=([-\d.eE]+), G=([-\d.eE]+), B=([-\d.eE]+), A=([-\d.eE]+) \}", value)
        if col:
            out[name] = tuple(float(c) for c in col.groups())
        else:
            try:
                out[name] = float(value)
            except ValueError:
                pass
    return out


os.makedirs(TEX_DIR, exist_ok=True)
_image_cache = {}


def local_texture(src):
    """Copy a PNG into <out>/textures once; returns the local path."""
    if not src or not os.path.isfile(src):
        return None
    dst = os.path.join(TEX_DIR, os.path.basename(src))
    if not os.path.isfile(dst):
        shutil.copy2(src, dst)
    return dst


def load_image(src, non_color=False, packed=False):
    dst = local_texture(src)
    if dst is None:
        return None
    key = (dst, non_color, packed)
    if key in _image_cache:
        return _image_cache[key]
    img = bpy.data.images.load(dst, check_existing=False)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    if packed:
        img.alpha_mode = "CHANNEL_PACKED"   # a pack/normal PNG with alpha≈0 must not premultiply
    _image_cache[key] = img
    return img


def pick(textures, *suffixes, exclude=()):
    """First texture whose name ends with one of the suffixes (case-sensitive), skipping excluded stems."""
    for suf in suffixes:
        for name, path in textures.items():
            if path and name.endswith(suf) and not any(x in name for x in exclude):
                return path
    return None


def new_tree(material):
    material.use_nodes = True
    tree = material.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return tree, bsdf, out


def tex_node(tree, img, location, label=""):
    n = tree.nodes.new("ShaderNodeTexImage")
    n.image = img
    n.location = location
    n.label = label or img.name
    n.interpolation = "Linear"
    return n


def link_normal(tree, bsdf, img, strength=1.0):
    """UE (DirectX) normal map: flip green, then a Normal Map node."""
    t = tex_node(tree, img, (-900, -500), "Normal")
    sep = tree.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-600, -500)
    inv = tree.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    inv.location = (-420, -560)
    comb = tree.nodes.new("ShaderNodeCombineColor")
    comb.location = (-240, -500)
    nm = tree.nodes.new("ShaderNodeNormalMap")
    nm.location = (-40, -500)
    nm.inputs["Strength"].default_value = strength
    tree.links.new(t.outputs["Color"], sep.inputs["Color"])
    tree.links.new(sep.outputs["Red"], comb.inputs["Red"])
    tree.links.new(sep.outputs["Green"], inv.inputs[1])
    tree.links.new(inv.outputs["Value"], comb.inputs["Green"])
    tree.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
    tree.links.new(comb.outputs["Color"], nm.inputs["Color"])
    tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def link_pack(tree, bsdf, img, metallic=True, base_socket=None):
    """_P = R AO, G roughness, B metallic.  AO darkens the base colour a little."""
    t = tex_node(tree, img, (-900, -200), "Pack (AO/R/M)")
    sep = tree.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-600, -200)
    tree.links.new(t.outputs["Color"], sep.inputs["Color"])
    tree.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    if metallic:
        tree.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = 0.0
    if base_socket is not None:
        mix = tree.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 0.5
        mix.location = (-40, 150)
        tree.links.new(base_socket, mix.inputs[6])
        tree.links.new(sep.outputs["Red"], mix.inputs[7])
        tree.links.new(mix.outputs[2], bsdf.inputs["Base Color"])


def classify(mat_name, textures):
    n = mat_name.lower()
    # hair by name OR by the shared strand atlas (PC_004_A0101_Head_999_MI is hair)
    if "hair" in n or any("HairTex" in t for t in textures):
        return "hair"
    if re.search(r"_eyes?_mi$|_eye_mi$|eyeball", n):
        return "eye"
    if "eyebrow" in n or "eyeblow" in n or "brow" in n:     # the game spells it "Eyeblow" too
        return "eyebrow"
    if "eyelash" in n or "lash" in n:
        return "eyelash"
    if "eyeocc" in n or "tearline" in n or "occlusion" in n:
        return "clear"
    if "glass" in n or "visor" in n or "lens" in n:
        return "glass"
    if "teeth" in n or "mouth" in n or "tongue" in n:
        return "teeth"
    if re.search(r"_(body|face|skin|head)_mi$", n) or any("Skin_detail" in t for t in textures):
        return "skin"
    return "cloth"


def build_material(mat, entry, mesh_name):
    textures = {k: v for k, v in (entry.get("textures") or {}).items()}
    props = read_props(entry.get("props"))
    kind = classify(entry["material"], textures)
    tree, bsdf, out = new_tree(mat)
    info = {"kind": kind, "textures": [os.path.basename(v) for v in textures.values() if v]}
    albedo = pick(textures, "_C", "_D", "_d", exclude=("Sclera", "Veins", "Mouth_N", "Dyed"))
    normal = pick(textures, "_N", "_n", exclude=("Skin_detail", "Sclera", "Mouth_N" if kind != "teeth" else "zz", "Eye_N" if kind != "eye" else "zz"))
    pack = pick(textures, "_P", exclude=("HairTex",))
    fx = pick(textures, "_FX")

    if kind == "clear":
        tree.nodes.remove(bsdf)
        transp = tree.nodes.new("ShaderNodeBsdfTransparent")
        transp.location = (250, 0)
        tree.links.new(transp.outputs["BSDF"], out.inputs["Surface"])
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"
        return info

    if kind == "glass":
        col = props.get("Color", (0.8, 0.85, 0.9, 1.0))
        bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
        bsdf.inputs["Roughness"].default_value = float(props.get("Roughness", 0.1))
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Specular"].default_value = 0.9
        # the shader's Opacity is a fade towards the rim; a flat 0.35 reads as a visor
        bsdf.inputs["Alpha"].default_value = min(0.6, max(0.15, 1.0 - float(props.get("Opacity", 0.85)) + 0.2))
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
        mat.show_transparent_back = False
        return info

    if kind == "hair":
        hair = next((v for k, v in textures.items() if "HairTex" in k and v), None) or pick(textures, "_P")
        root = props.get("Hair_RootColor", (0.08, 0.05, 0.03, 1.0))
        tip = props.get("Hair_TipColor", (0.16, 0.10, 0.06, 1.0))
        bsdf.inputs["Roughness"].default_value = 0.45
        bsdf.inputs["Specular"].default_value = 0.3
        if hair:
            img = load_image(hair, non_color=True, packed=True)
            t = tex_node(tree, img, (-900, 0), "Hair pack")
            sep = tree.nodes.new("ShaderNodeSeparateColor")
            sep.location = (-600, 0)
            tree.links.new(t.outputs["Color"], sep.inputs["Color"])
            mix = tree.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.location = (-300, 100)
            mix.inputs[6].default_value = root
            mix.inputs[7].default_value = tip
            tree.links.new(sep.outputs["Green"], mix.inputs["Factor"])
            tree.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
            tree.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.blend_method = "HASHED"
            mat.shadow_method = "HASHED"
        else:
            bsdf.inputs["Base Color"].default_value = root
        return info

    if kind == "eye":
        sclera = pick(textures, "Sclera_D", "_D")
        veins = pick(textures, "Veins_D")
        eye_n = pick(textures, "Eye_N", "Sclera_N")
        bsdf.inputs["Roughness"].default_value = 0.15
        bsdf.inputs["Specular"].default_value = 0.8
        base_socket = None
        if sclera:
            t = tex_node(tree, load_image(sclera), (-900, 200), "Sclera")
            base_socket = t.outputs["Color"]
            if veins:
                tv = tex_node(tree, load_image(veins), (-900, -50), "Veins")
                mix = tree.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs["Factor"].default_value = 0.6
                mix.location = (-600, 150)
                tree.links.new(t.outputs["Color"], mix.inputs[6])
                tree.links.new(tv.outputs["Color"], mix.inputs[7])
                base_socket = mix.outputs[2]
        # procedural iris: a dark ring + coloured disc around the UV centre, pupil inside
        iris_r = 0.2
        pupil = 0.32 * float(props.get("PupilScale", 1.0)) * iris_r
        uv = tree.nodes.new("ShaderNodeTexCoord")
        uv.location = (-1300, 500)
        sub = tree.nodes.new("ShaderNodeVectorMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = (0.5, 0.5, 0.0)
        sub.location = (-1100, 500)
        length = tree.nodes.new("ShaderNodeVectorMath")
        length.operation = "LENGTH"
        length.location = (-900, 500)
        tree.links.new(uv.outputs["UV"], sub.inputs[0])
        tree.links.new(sub.outputs["Vector"], length.inputs[0])
        iris_mask = tree.nodes.new("ShaderNodeMath")
        iris_mask.operation = "LESS_THAN"
        iris_mask.inputs[1].default_value = iris_r
        iris_mask.location = (-700, 520)
        pupil_mask = tree.nodes.new("ShaderNodeMath")
        pupil_mask.operation = "LESS_THAN"
        pupil_mask.inputs[1].default_value = pupil
        pupil_mask.location = (-700, 360)
        tree.links.new(length.outputs["Value"], iris_mask.inputs[0])
        tree.links.new(length.outputs["Value"], pupil_mask.inputs[0])
        # iris colour: the game samples a colour picker at IrisColor1U/V; approximate with a
        # warm brown scaled by the picker V (brightness) when present
        v1 = float(props.get("IrisColor1V", 0.4))
        iris_col = (0.16 * v1 * 2.2, 0.09 * v1 * 2.2, 0.04 * v1 * 2.2, 1.0)
        iris_mix = tree.nodes.new("ShaderNodeMix")
        iris_mix.data_type = "RGBA"
        iris_mix.location = (-400, 350)
        iris_mix.inputs[7].default_value = iris_col
        if base_socket is not None:
            tree.links.new(base_socket, iris_mix.inputs[6])
        else:
            iris_mix.inputs[6].default_value = (0.9, 0.88, 0.86, 1.0)
        tree.links.new(iris_mask.outputs["Value"], iris_mix.inputs["Factor"])
        pupil_mix = tree.nodes.new("ShaderNodeMix")
        pupil_mix.data_type = "RGBA"
        pupil_mix.location = (-150, 350)
        pupil_mix.inputs[7].default_value = (0.01, 0.01, 0.01, 1.0)
        tree.links.new(iris_mix.outputs[2], pupil_mix.inputs[6])
        tree.links.new(pupil_mask.outputs["Value"], pupil_mix.inputs["Factor"])
        tree.links.new(pupil_mix.outputs[2], bsdf.inputs["Base Color"])
        if eye_n:
            link_normal(tree, bsdf, load_image(eye_n, non_color=True, packed=True), 0.5)
        return info

    if kind in ("eyebrow", "eyelash"):
        strand = pick(textures, "eyebrow_d", "_d", "_D", "_C")
        col = props.get("fresnel_col", (0.05, 0.035, 0.025, 1.0))
        bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
        bsdf.inputs["Specular"].default_value = 0.2
        if strand:
            t = tex_node(tree, load_image(strand, non_color=True, packed=True), (-900, 0), "Strand alpha")
            tree.links.new(t.outputs["Color"], bsdf.inputs["Alpha"])
            mat.blend_method = "HASHED"
            mat.shadow_method = "HASHED"
        else:
            bsdf.inputs["Alpha"].default_value = 0.6
            mat.blend_method = "HASHED"
        return info

    # skin / cloth / teeth: albedo + normal + pack (+ emissive mask)
    base_socket = None
    if albedo:
        t = tex_node(tree, load_image(albedo), (-900, 300), "Albedo")
        base_socket = t.outputs["Color"]
        tree.links.new(base_socket, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.74, 1.0)
        report["missing_textures"].append("%s: no albedo" % entry["material"])
    if normal:
        link_normal(tree, bsdf, load_image(normal, non_color=True, packed=True),
                    0.6 if kind == "skin" else 1.0)
    if pack:
        link_pack(tree, bsdf, load_image(pack, non_color=True, packed=True),
                  metallic=(kind == "cloth"), base_socket=base_socket if kind == "cloth" else None)
    else:
        bsdf.inputs["Roughness"].default_value = 0.5 if kind != "skin" else 0.45
        bsdf.inputs["Metallic"].default_value = 0.0
    if kind == "skin":
        bsdf.inputs["Subsurface"].default_value = 0.03
        bsdf.inputs["Subsurface Color"].default_value = (0.8, 0.35, 0.25, 1.0)
        bsdf.inputs["Specular"].default_value = 0.4
    if fx and kind == "cloth":
        em = props.get("Emissive_col", (0.0, 0.23, 1.0, 1.0))
        tf = tex_node(tree, load_image(fx, non_color=True, packed=True), (-900, -800), "FX mask")
        sep = tree.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-600, -800)
        tree.links.new(tf.outputs["Color"], sep.inputs["Color"])
        bsdf.inputs["Emission"].default_value = (em[0], em[1], em[2], 1.0)
        tree.links.new(sep.outputs["Red"], bsdf.inputs["Emission Strength"])
    return info


for mesh in meshes_all:
    slots = MATERIALS.get(os.path.normcase(os.path.normpath(mesh.get("tfd_pskx", ""))), [])
    by_index = {s["slot"]: s for s in slots}
    built = {}
    for i, slot in enumerate(mesh.material_slots):
        entry = by_index.get(i)
        if slot.material is None:
            slot.material = bpy.data.materials.new("%s_slot%d" % (mesh.name, i))
        mat = slot.material
        if entry is None:
            continue
        # same material instance on two slots -> share one Blender material
        key = entry["material"]
        if key in built:
            slot.material = built[key]
            continue
        mat.name = entry["material"]
        info = build_material(mat, entry, mesh.name)
        built[key] = mat
        report["materials"][entry["material"]] = info
    for poly in mesh.data.polygons:
        poly.use_smooth = True

report["rig"] = {"bones": len(base_arm.data.bones)}
report["meshes"] = len(meshes_all)


# ---------------------------------------------------------------- preview
def frame_points(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, mx - mn


def render(path, center, ortho_scale, size, forward):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "VERTICAL"
    cam_data.ortho_scale = ortho_scale
    cam_data.clip_end = max(size) * 100 + 1000
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    dist = max(ortho_scale, 100) * 3
    cam.location = center + forward * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    log("rendered " + path)


if not NO_PREVIEW:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 48
    scene.eevee.use_soft_shadows = True
    scene.view_settings.view_transform = "Filmic"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
    scene.world = world
    center, extent = frame_points(meshes_all)
    height = max(extent.z, extent.x, extent.y, 1e-6)
    forward = Vector((0.0, -1.0, 0.0))
    side = forward.cross(Vector((0.0, 0.0, 1.0)))
    for name, (f, s, z), energy in (("Key", (1.0, 0.7, 1.2), 3.0), ("Fill", (0.6, -1.0, 0.4), 1.3),
                                    ("Rim", (-0.8, -0.2, 1.0), 1.7)):
        light = bpy.data.lights.new(name, "SUN")
        light.energy = energy
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + (forward * f + side * s + Vector((0.0, 0.0, z))) * height
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    preview = os.path.join(OUT_DIR, "preview.png")
    render(preview, center, height * 1.28, (900, 1400), forward)
    report["preview"] = preview
    head = None
    for candidate in ("head", "Head", "Bip001-Head", "Bip001 Head"):
        head = base_arm.data.bones.get(candidate)
        if head is not None:
            break
    if head is None:
        head = next((b for b in base_arm.data.bones if re.search(r"(^|[-_ ])head$", b.name, re.IGNORECASE)), None)
    if head is not None:
        head_pos = base_arm.matrix_world @ head.head_local
        render(os.path.join(OUT_DIR, "preview_face.png"),
               head_pos + Vector((0.0, 0.0, height * 0.03)), height * 0.20, (900, 900), forward)
        report["preview_face"] = os.path.join(OUT_DIR, "preview_face.png")

os.makedirs(OUT_DIR, exist_ok=True)
blend = os.path.join(OUT_DIR, MODEL_ID + ".blend")
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False)
try:
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False)
except Exception as exc:  # noqa: BLE001
    report["warnings"].append("relative paths: %s" % exc)
report["blend"] = blend
report["textures_total"] = len(_image_cache)
print("TFD_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
