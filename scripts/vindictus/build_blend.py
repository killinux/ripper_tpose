"""Vindictus: Defying Fate — assemble UE Viewer PSK parts into one .blend (Blender 3.6, headless).

    blender --background --factory-startup --python build_blend.py -- --spec <spec.json> [--no-preview] [--smooth]

spec.json is written by export_model.ps1:

    {
      "id": "Fiona",
      "out_dir": "D:/vindictus_exports/blend/Fiona",
      "texture_roots": ["D:/vindictus_exports/umodel_exports"],
      "parts": [{"name": "Face", "psk": "D:/.../SK_Fiona_Face01.pskx"}, ...]
    }

What it does:
  1. imports every part with io_scene_psk_psa (materials named after the PSK MATT slots);
  2. merges the per-part skeletons into one armature (union of bones, matched by name; every mesh is
     re-bound to it) so the character is one poseable rig;
  3. rebuilds each material from UE Viewer's <material>.mat / <material>.props.txt next to the PSKs:
     outfit PBR (D / N / ORM-ARM), skin (tint), hair (ODI opacity + FR root-tip gradient with the
     Root/Mid/Tip colours of the material instance), eyebrow/lash (ODI), eyes (sclera + iris mask +
     iris colours sampled from the colour-picker texture), eye occlusion / tear line shells;
  4. copies the textures used into <out_dir>/textures and saves <out_dir>/<id>.blend with relative
     paths, then renders preview.png (full body) and preview_face.png (head close-up).

A VINDICTUS_REPORT={json} line is printed at the end for the PowerShell wrapper.
"""
import json
import math
import os
import re
import shutil
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--spec" not in argv:
    raise SystemExit("usage: blender --background --factory-startup --python build_blend.py -- --spec spec.json [--no-preview] [--smooth]")
SPEC = json.load(open(argv[argv.index("--spec") + 1], encoding="utf-8"))
NO_PREVIEW = "--no-preview" in argv
SMOOTH = "--smooth" in argv          # drop the PSK split normals, shade smooth instead

MODEL_ID = SPEC["id"]
OUT_DIR = os.path.normpath(SPEC["out_dir"])
TEX_DIR = os.path.join(OUT_DIR, "textures")
TEXTURE_ROOTS = [os.path.normpath(p) for p in SPEC.get("texture_roots", [])]
PARTS = SPEC["parts"]
PSK_ADDON = "io_scene_psk_psa"

IMAGE_EXTS = (".png", ".tga", ".dds", ".hdr")   # UE Viewer writes BC6H/float textures as .hdr
# UE "Masked" materials clip at 1/3 by default; grey alpha in the outfit diffuse is a mask, not translucency.
MASK_CLIP = 0.33
SKIN_NORMAL_STRENGTH = 0.6
DEFAULT_NORMAL_STRENGTH = 1.0

report = {"id": MODEL_ID, "parts": [], "materials": {}, "missing_textures": [], "warnings": []}


def log(msg):
    print("[vindictus] " + msg, flush=True)


# ---------------------------------------------------------------- setup
bpy.ops.wm.read_factory_settings(use_empty=True)
import addon_utils  # noqa: E402

if addon_utils.enable(PSK_ADDON, default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for Blender 3.6 (needed for PSK/PSKX import)")

os.makedirs(TEX_DIR, exist_ok=True)


# ---------------------------------------------------------------- texture / material lookup
def build_index():
    """stem(lower) -> path for images, .mat and .props.txt under the export roots.

    PNG beats TGA; the game's own VindictusRoot beats Engine/_Prework copies of a same-named file."""
    images, mats, props = {}, {}, {}

    def rank(path):
        low = path.replace(os.sep, "/").lower()
        return (0 if "/vindictusroot/" in low else 1, IMAGE_EXTS.index(os.path.splitext(low)[1]) if low.endswith(IMAGE_EXTS) else 9, low)

    for root in TEXTURE_ROOTS:
        for dp, _dirs, files in os.walk(root):
            for f in files:
                low = f.lower()
                path = os.path.join(dp, f)
                if low.endswith(IMAGE_EXTS):
                    stem = os.path.splitext(low)[0]
                    if stem not in images or rank(path) < rank(images[stem]):
                        images[stem] = path
                elif low.endswith(".props.txt"):
                    props.setdefault(low[:-len(".props.txt")], path)
                elif low.endswith(".mat"):
                    mats.setdefault(low[:-4], path)
    return images, mats, props


IMAGES, MATS, PROPS = build_index()
log("index: %d images, %d .mat, %d .props.txt under %s" % (len(IMAGES), len(MATS), len(PROPS), TEXTURE_ROOTS))


def base_material_name(name):
    return re.sub(r"\.\d{3}$", "", name)


def read_mat(name):
    """UE Viewer .mat: Diffuse=..., Normal=..., Opacity=..., Other[0]=... (texture stems)."""
    path = MATS.get(name.lower())
    out = {"_others": []}
    if not path:
        return out
    for line in open(path, encoding="utf-8", errors="replace"):
        if "=" not in line:
            continue
        key, value = line.strip().split("=", 1)
        if key.startswith("Other["):
            out["_others"].append(value.strip())
        else:
            out[key.strip()] = value.strip()
    return out


_PARAM_RE = re.compile(r"ParameterInfo = \{ Name=(?P<name>[^}]*?) \}\s*ParameterValue = (?P<value>[^\n]*)")


def read_props(name):
    """UE Viewer .props.txt of a material instance: parent + texture/vector/scalar parameters."""
    path = PROPS.get(name.lower())
    out = {"parent": "", "textures": {}, "vectors": {}, "scalars": {}}
    if not path:
        return out
    text = open(path, encoding="utf-8", errors="replace").read()
    parent = re.search(r"Parent = (.*)", text)
    if parent:
        out["parent"] = parent.group(1).strip()
    for m in _PARAM_RE.finditer(text):
        key, value = m.group("name").strip(), m.group("value").strip()
        if value.startswith("Texture2D"):
            out["textures"][key] = value.rsplit(".", 1)[-1].rstrip("'")
        elif value.startswith("{"):
            nums = re.findall(r"([RGBA])=([-\d.eE+]+)", value)
            out["vectors"][key] = tuple(float(v) for _k, v in nums)
        else:
            try:
                out["scalars"][key] = float(value)
            except ValueError:
                pass
    return out


def image_path(stem):
    if not stem:
        return ""
    return IMAGES.get(stem.lower(), "")


def find_role(mat_info, props, roles, suffixes=()):
    """Pick a texture stem: material-instance parameter names first, then .mat keys, then suffix match."""
    for key, stem in props["textures"].items():
        if any(r in key.lower() for r in roles):
            return stem
    for key in mat_info:
        if key != "_others" and key.lower() in roles:
            return mat_info[key]
    for stem in mat_info["_others"]:
        if stem.lower().endswith(suffixes):
            return stem
    return ""


# ---------------------------------------------------------------- node helpers
def new_tree(material):
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (320, 0)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return tree, bsdf


def load_image(path, non_color=False):
    image = bpy.data.images.load(path, check_existing=True)
    image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return image


def tex_node(tree, path, location, non_color=False, label=""):
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = load_image(path, non_color)
    node.location = location
    node.label = label or os.path.basename(path)
    return node


def link_normal(tree, bsdf, path, strength):
    """UE normal maps are DirectX (Y-); flip green before Blender's Normal Map node."""
    img = tex_node(tree, path, (-900, -350), non_color=True)
    sep = tree.nodes.new("ShaderNodeSeparateRGB")
    sep.location = (-620, -350)
    inv = tree.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    inv.location = (-460, -420)
    comb = tree.nodes.new("ShaderNodeCombineRGB")
    comb.location = (-300, -350)
    nmap = tree.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = strength
    nmap.location = (-140, -350)
    tree.links.new(img.outputs["Color"], sep.inputs["Image"])
    tree.links.new(sep.outputs["R"], comb.inputs["R"])
    tree.links.new(sep.outputs["G"], inv.inputs[1])
    tree.links.new(inv.outputs["Value"], comb.inputs["G"])
    tree.links.new(sep.outputs["B"], comb.inputs["B"])
    tree.links.new(comb.outputs["Image"], nmap.inputs["Color"])
    tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


def link_packed(tree, bsdf, path):
    """ORM / ARM: R = ambient occlusion, G = roughness, B = metallic."""
    img = tex_node(tree, path, (-900, -700), non_color=True)
    sep = tree.nodes.new("ShaderNodeSeparateRGB")
    sep.location = (-620, -700)
    tree.links.new(img.outputs["Color"], sep.inputs["Image"])
    tree.links.new(sep.outputs["G"], bsdf.inputs["Roughness"])
    tree.links.new(sep.outputs["B"], bsdf.inputs["Metallic"])


def link_tinted_base(tree, bsdf, path, tint):
    img = tex_node(tree, path, (-900, 300))
    if tint and any(abs(c - 1.0) > 1e-3 for c in tint[:3]):
        mix = tree.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.inputs["Color2"].default_value = (tint[0], tint[1], tint[2], 1.0)
        mix.location = (-500, 300)
        tree.links.new(img.outputs["Color"], mix.inputs["Color1"])
        tree.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        tree.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    return img


def channel(tree, img, name, location):
    sep = tree.nodes.new("ShaderNodeSeparateRGB")
    sep.location = location
    tree.links.new(img.outputs["Color"], sep.inputs["Image"])
    return sep.outputs[name]


def sample_image(path, u, v):
    """Colour of one texel (u, v in 0..1, v from the bottom like Blender) of an image file."""
    image = bpy.data.images.load(path, check_existing=True)
    w, h = image.size
    x = min(w - 1, max(0, int(u * (w - 1))))
    y = min(h - 1, max(0, int((1.0 - v) * (h - 1))))   # UE V runs top-down
    px = image.pixels[(y * w + x) * image.channels:(y * w + x) * image.channels + 3]
    return tuple(px) if len(px) == 3 else (0.3, 0.25, 0.2)


def srgb_to_linear(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def map_range(tree, value_socket, from_min, from_max, to_min, to_max, location):
    node = tree.nodes.new("ShaderNodeMapRange")
    node.location = location
    node.inputs["From Min"].default_value = from_min
    node.inputs["From Max"].default_value = from_max
    node.inputs["To Min"].default_value = to_min
    node.inputs["To Max"].default_value = to_max
    tree.links.new(value_socket, node.inputs["Value"])
    return node.outputs["Result"]


def multiply_rgb(tree, a_socket, b_socket, location):
    node = tree.nodes.new("ShaderNodeMixRGB")
    node.blend_type = "MULTIPLY"
    node.inputs["Fac"].default_value = 1.0
    node.location = location
    tree.links.new(a_socket, node.inputs["Color1"])
    tree.links.new(b_socket, node.inputs["Color2"])
    return node.outputs["Color"]


# Iris layout in eyeball UV space: the eyeball UVs cover the whole sclera texture, the iris is the disc of UV
# radius IRIS_UV_RADIUS around the centre (MetaHuman convention; 0.2 matches the eye opening of these heads).
IRIS_UV_RADIUS = 0.2
PUPIL_RADIUS = 0.32          # of the iris radius, before the material's pupil scale
IRIS_BRIGHTNESS_GAIN = 1.35  # on top of the material's IrisBrightness (3 for Fiona): the game adds refraction glow
EYE_ROUGHNESS, EYE_SPECULAR = 0.12, 0.5


def build_eye(tree, bsdf, info, props, use, entry):
    """Sclera texture (+ veins) with a procedural iris: two colours blended along the radius, fibre structure
    from the iris map, limbus darkening at the rim, black pupil, wet specular and the eye normal map.

    Two shader families exist: M_PC_Skin_EyeRefractive_Old (MetaHuman-style; colours picked from
    T_PC_Iris_color_picker at IrisColor1/2 UV, T_Iris_A_M: B = radial gradient, G = fibres) and M_PC_Skin_Eye
    (Iris Color Inner/Outer vectors, T_EyeMap01: R = radial gradient, G = fibres)."""
    s, tx, vec = props["scalars"], props["textures"], props["vectors"]
    metahuman = "IrisColor1U" in s or "IrisMasks" in tx
    picker = image_path("T_PC_Iris_color_picker")
    if metahuman and picker:
        c1 = srgb_to_linear(sample_image(picker, s.get("IrisColor1U", 0.5), s.get("IrisColor1V", 0.5)))
        c2 = srgb_to_linear(sample_image(picker, s.get("IrisColor2U", 0.5), s.get("IrisColor2V", 0.5)))
        balance = s.get("IrisColorBalance", 0.5)
        gain = s.get("IrisBrightness", 3.0) * IRIS_BRIGHTNESS_GAIN
        limbus = min(0.85, s.get("LimbusDarkAmount", 0.6) + 0.1)
        pupil_scale = s.get("PupilScale", 1.0)
        iris_map = use(tx.get("IrisMasks") or "T_Iris_A_M")
        gradient_channel, fibre_lo, fibre_hi = "B", 0.3, 1.0
    else:
        c1 = tuple(vec.get("Iris Color Inner", (0.15, 0.12, 0.08, 1))[:3])
        c2 = tuple(vec.get("Iris Color Outer", (0.20, 0.13, 0.06, 1))[:3])
        balance, gain = 0.5, 4.0
        limbus = min(0.85, 0.3 + s.get("Iris Dark Edge Contrast", 1.5) * 0.25)
        pupil_scale = s.get("Pupil Scale", 1.0)
        iris_map = use(tx.get("Eye Map") or "T_EyeMap01")
        gradient_channel, fibre_lo, fibre_hi = "R", 0.0, 0.5
    entry["iris_rgb"] = [round(c, 3) for c in c1]
    L = tree.links

    # centred UV scaled so the iris texture disc (r = 1) lands on UV radius IRIS_UV_RADIUS
    coord = tree.nodes.new("ShaderNodeTexCoord")
    coord.location = (-1900, 0)
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.location = (-1700, 0)
    k = 0.5 / IRIS_UV_RADIUS
    mapping.inputs["Location"].default_value = (0.5 - 0.5 * k, 0.5 - 0.5 * k, 0.0)
    mapping.inputs["Scale"].default_value = (k, k, 1.0)
    L.new(coord.outputs["UV"], mapping.inputs["Vector"])
    sub = tree.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    sub.location = (-1500, -300)
    L.new(mapping.outputs["Vector"], sub.inputs[0])
    dist = tree.nodes.new("ShaderNodeVectorMath")
    dist.operation = "LENGTH"
    dist.location = (-1300, -300)
    L.new(sub.outputs["Vector"], dist.inputs[0])
    rad = tree.nodes.new("ShaderNodeMath")          # 0 at the iris centre, 1 at its rim
    rad.operation = "MULTIPLY"
    rad.inputs[1].default_value = 2.0
    rad.location = (-1100, -300)
    L.new(dist.outputs["Value"], rad.inputs[0])
    iris_mask = map_range(tree, rad.outputs["Value"], 0.90, 0.98, 1.0, 0.0, (-900, -300))
    limbus_fac = map_range(tree, rad.outputs["Value"], 0.70, 0.97, 1.0, 1.0 - limbus, (-900, -500))
    pupil_r = PUPIL_RADIUS * pupil_scale
    pupil_fac = map_range(tree, rad.outputs["Value"], pupil_r - 0.03, pupil_r + 0.03, 1.0, 0.0, (-900, -700))

    # iris colour
    gradient = fibres = None
    if iris_map:
        img = tex_node(tree, iris_map, (-1500, 100), non_color=True)
        img.extension = "EXTEND"
        L.new(mapping.outputs["Vector"], img.inputs["Vector"])
        sep = tree.nodes.new("ShaderNodeSeparateRGB")
        sep.location = (-1300, 100)
        L.new(img.outputs["Color"], sep.inputs["Image"])
        gradient = map_range(tree, sep.outputs[gradient_channel], balance - 0.25, balance + 0.25, 0.0, 1.0, (-1100, 200))
        fibres = map_range(tree, sep.outputs["G"], fibre_lo, fibre_hi, 0.4, 1.0, (-1100, 400))
    mixc = tree.nodes.new("ShaderNodeMixRGB")
    mixc.location = (-900, 200)
    mixc.inputs["Color1"].default_value = (c1[0] * gain, c1[1] * gain, c1[2] * gain, 1)
    mixc.inputs["Color2"].default_value = (c2[0] * gain, c2[1] * gain, c2[2] * gain, 1)
    if gradient is not None:
        L.new(gradient, mixc.inputs["Fac"])
    else:
        mixc.inputs["Fac"].default_value = 0.5
    iris = mixc.outputs["Color"]
    if fibres is not None:
        iris = multiply_rgb(tree, iris, fibres, (-700, 200))
    iris = multiply_rgb(tree, iris, limbus_fac, (-500, 200))

    # sclera (+ veins)
    sclera = use(tx.get("ScleraBaseColor") or tx.get("Sclera Color Map") or info.get("Diffuse", ""))
    veins = image_path("T_PC_Veins_D")
    if sclera:
        base = tex_node(tree, sclera, (-1500, 700)).outputs["Color"]
        if veins:
            vn = tex_node(tree, veins, (-1500, 950))
            vmix = tree.nodes.new("ShaderNodeMixRGB")
            vmix.blend_type = "MULTIPLY"
            vmix.inputs["Fac"].default_value = 0.4
            vmix.location = (-1200, 700)
            L.new(base, vmix.inputs["Color1"])
            L.new(vn.outputs["Color"], vmix.inputs["Color2"])
            base = vmix.outputs["Color"]
    else:
        rgb = tree.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (0.8, 0.76, 0.76, 1)
        rgb.location = (-1500, 700)
        base = rgb.outputs[0]

    m1 = tree.nodes.new("ShaderNodeMixRGB")    # sclera -> iris
    m1.location = (-300, 300)
    L.new(base, m1.inputs["Color1"])
    L.new(iris, m1.inputs["Color2"])
    L.new(iris_mask, m1.inputs["Fac"])
    m2 = tree.nodes.new("ShaderNodeMixRGB")    # -> pupil
    m2.location = (-100, 300)
    m2.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1)
    L.new(m1.outputs["Color"], m2.inputs["Color1"])
    L.new(pupil_fac, m2.inputs["Fac"])
    L.new(m2.outputs["Color"], bsdf.inputs["Base Color"])

    normal = use(tx.get("Eye Direction World") or info.get("Normal", "") or "T_PC_Eye_N")
    if normal:
        img = tex_node(tree, normal, (-700, -900), non_color=True)
        nm = tree.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 0.4
        nm.location = (-400, -900)
        L.new(img.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = EYE_ROUGHNESS
    bsdf.inputs["Specular"].default_value = EYE_SPECULAR


# ---------------------------------------------------------------- material kinds
def setup_material(material):
    name = base_material_name(material.name)
    info = read_mat(name)
    props = read_props(name)
    parent = props["parent"].lower()
    low = name.lower()
    entry = {"parent": props["parent"].split("'")[-2].rsplit(".", 1)[-1] if "'" in props["parent"] else "", "kind": "", "textures": []}
    report["materials"][name] = entry

    def use(stem):
        path = image_path(stem)
        if stem and not path:
            report["missing_textures"].append("%s <- %s" % (stem, name))
        elif path:
            entry["textures"].append(os.path.basename(path))
        return path

    tree, bsdf = new_tree(material)
    material.blend_method = "OPAQUE"
    material.shadow_method = "OPAQUE"

    # --- hair cards: ODI (R = opacity), FR (B = root->tip), Root/Mid/Tip colours from the instance
    if "m_pc_hair" in parent or "mob_hair" in parent or "odi map" in {k.lower() for k in props["textures"]}:
        entry["kind"] = "hair"
        odi = use(find_role(info, props, ("odi",), ("_odi",)))
        fr = use(find_role(info, props, ("fr map", "fr ",), ("_fr",)))
        root = props["vectors"].get("Color Root", (0.20, 0.14, 0.09, 1))
        mid = props["vectors"].get("Color Mid", (0.37, 0.27, 0.18, 1))
        tip = props["vectors"].get("Color Tip", (0.19, 0.13, 0.10, 1))
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        ramp.location = (-500, 300)
        ramp.color_ramp.elements[0].color = (root[0], root[1], root[2], 1)
        ramp.color_ramp.elements[1].color = (tip[0], tip[1], tip[2], 1)
        e = ramp.color_ramp.elements.new(0.5)
        e.color = (mid[0], mid[1], mid[2], 1)
        if fr:
            fr_img = tex_node(tree, fr, (-900, 300), non_color=True)
            tree.links.new(channel(tree, fr_img, "B", (-700, 300)), ramp.inputs["Fac"])
        else:
            ramp.inputs["Fac"].default_value = 0.5
        tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if odi:
            odi_img = tex_node(tree, odi, (-900, 0), non_color=True)
            tree.links.new(channel(tree, odi_img, "R", (-700, 0)), bsdf.inputs["Alpha"])
            material.blend_method = "HASHED"
            material.shadow_method = "HASHED"
        bsdf.inputs["Roughness"].default_value = props["scalars"].get("Roughness", 0.4)
        bsdf.inputs["Specular"].default_value = 0.4
        material.use_backface_culling = False
        return

    # --- eyebrow / eyelash strands: ODI red channel is the coverage
    if "eyebrow" in parent or "eyelash" in low or "eyebrow" in low:
        entry["kind"] = "brow"
        odi = use(find_role(info, props, ("odi", "diffuse"), ("_odi",)) or info.get("Diffuse", ""))
        color = props["vectors"].get("Color", props["vectors"].get("Hair Color", (0.06, 0.035, 0.02, 1)))
        bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1)
        bsdf.inputs["Roughness"].default_value = 0.6
        if odi:
            img = tex_node(tree, odi, (-900, 0), non_color=True)
            tree.links.new(channel(tree, img, "R", (-700, 0)), bsdf.inputs["Alpha"])
            material.blend_method = "HASHED"
            material.shadow_method = "HASHED"
        return

    # --- eye occlusion shell / tear line / fake reflection card: translucent helpers
    if "eyeocclusion" in parent or "eyeshdow" in low or "eyeshadow" in low:
        entry["kind"] = "eye-occlusion"
        bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
        bsdf.inputs["Alpha"].default_value = 0.12
        bsdf.inputs["Specular"].default_value = 0.0      # a pure darkening tint: highlights on the shell read as haze
        bsdf.inputs["Roughness"].default_value = 1.0
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"
        material.show_transparent_back = False
        material.use_backface_culling = True
        return
    if "skin_tear" in parent or "lacrimal" in low or "eyereflection" in low:
        entry["kind"] = "eye-wet"
        bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1)
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Specular"].default_value = 0.8
        diffuse = use(info.get("Diffuse", ""))
        if diffuse and "eyereflection" in low:
            img = tex_node(tree, diffuse, (-900, 300))
            fade = tree.nodes.new("ShaderNodeMath")     # the in-game sparkle card is far too strong under plain suns
            fade.operation = "MULTIPLY"
            fade.inputs[1].default_value = 0.4
            fade.location = (-500, 200)
            tree.links.new(img.outputs["Alpha"], fade.inputs[0])
            tree.links.new(fade.outputs["Value"], bsdf.inputs["Alpha"])
        else:
            bsdf.inputs["Alpha"].default_value = 0.15
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"
        material.show_transparent_back = False
        return

    # --- eyeball: procedural iris like the game's eye shaders (see build_eye)
    if "skin_eye" in parent or "eyeball" in low or "_eye01" in low:
        entry["kind"] = "eye"
        build_eye(tree, bsdf, info, props, use, entry)
        return

    # --- generic PBR: outfit / skin / teeth / props
    diffuse = use(props["textures"].get("BaseColor") or find_role(info, props, ("basecolor", "diffuse", "base color"), ("_d", "_bc")))
    normal = use(props["textures"].get("Normal Map") or find_role(info, props, ("normal map", "normal"), ("_n", "_na")))
    packed = use(find_role(info, props, ("arm", "orm", "rma"), ("_arm", "_orm")))
    # skin = the M_PC_Skin_* family plus the base-body instances (MI_PCF_Upper01 ...); outfit instances such as
    # MI_PCF_003_Head are ordinary PBR even though they share the MI_PCF_ prefix
    skin = "skin" in parent or "skin" in low or "face01_" in low or bool(re.match(r"^mi_pc[fm]_(upper|lower|hand|foot|body|handfoot)\d*$", low))
    entry["kind"] = "skin" if skin else ("teeth" if "teeth" in low else "pbr")
    tint = props["vectors"].get("Basecolor Tint")
    base_img = None
    if diffuse:
        base_img = link_tinted_base(tree, bsdf, diffuse, tint)
    elif skin:
        # e.g. M_female_skin_body_01: its diffuse is a virtual texture UE Viewer cannot export -> plain skin tone
        bsdf.inputs["Base Color"].default_value = (0.80, 0.60, 0.50, 1.0)
        entry["textures"].append("(flat skin tone: diffuse not exportable)")
    if normal:
        link_normal(tree, bsdf, normal, SKIN_NORMAL_STRENGTH if skin else DEFAULT_NORMAL_STRENGTH)
    if packed and not skin:
        link_packed(tree, bsdf, packed)
    else:
        bsdf.inputs["Roughness"].default_value = 0.55 if skin else 0.6
        bsdf.inputs["Specular"].default_value = 0.35
    if skin:
        bsdf.inputs["Subsurface"].default_value = 0.02
        bsdf.inputs["Subsurface Color"].default_value = (0.8, 0.3, 0.2, 1)
    # UE Masked outfits: the diffuse alpha is a cut-out mask
    if base_img is not None and (info.get("Opacity") or "opacity" in " ".join(props["textures"]).lower()):
        tree.links.new(base_img.outputs["Alpha"], bsdf.inputs["Alpha"])
        material.blend_method = "CLIP"
        material.alpha_threshold = MASK_CLIP
        material.shadow_method = "CLIP"


# ---------------------------------------------------------------- import parts
def import_psk(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(
        filepath=path,
        should_import_vertex_colors=False,
        should_import_vertex_normals=not SMOOTH,
        should_import_extra_uvs=True,
        should_import_mesh=True,
        should_import_materials=True,
        should_reuse_materials=True,
        should_import_skeleton=True,
        should_import_shape_keys=True,
        bone_length=1.0,
    )
    created = [o for o in bpy.data.objects if o not in before]
    armature = next((o for o in created if o.type == "ARMATURE"), None)
    meshes = [o for o in created if o.type == "MESH"]
    return armature, meshes


imported = []   # (part, armature, meshes)
for part in PARTS:
    psk = os.path.normpath(part["psk"])
    if not os.path.isfile(psk):
        report["warnings"].append("missing PSK: " + psk)
        log("MISSING " + psk)
        continue
    armature, meshes = import_psk(psk)
    if armature is None or not meshes:
        report["warnings"].append("import produced no armature/mesh: " + psk)
        continue
    armature.name = "%s_%s_rig" % (MODEL_ID, part["name"])
    for i, mesh in enumerate(meshes):
        mesh.name = "%s_%s" % (MODEL_ID, part["name"]) + ("" if i == 0 else "_%d" % i)
        if SMOOTH:
            for poly in mesh.data.polygons:
                poly.use_smooth = True
            if hasattr(mesh.data, "use_auto_smooth"):
                mesh.data.use_auto_smooth = False
    imported.append((part, armature, meshes))
    report["parts"].append({
        "name": part["name"], "psk": os.path.basename(psk), "bones": len(armature.data.bones),
        "vertices": sum(len(m.data.vertices) for m in meshes), "faces": sum(len(m.data.polygons) for m in meshes),
        "materials": sorted({base_material_name(s.material.name) for m in meshes for s in m.material_slots if s.material}),
        "shape_keys": sum(len(m.data.shape_keys.key_blocks) - 1 for m in meshes if m.data.shape_keys),
    })
    log("imported %s: %d bones, %d verts" % (part["name"], len(armature.data.bones), report["parts"][-1]["vertices"]))

if not imported:
    raise SystemExit("nothing imported")


# ---------------------------------------------------------------- one rig
def bone_depth(bone):
    d = 0
    while bone.parent:
        bone = bone.parent
        d += 1
    return d


base_part, base_arm, _ = max(imported, key=lambda t: len(t[1].data.bones))
base_arm.name = MODEL_ID + "_rig"
log("base skeleton from %s (%d bones)" % (base_part["name"], len(base_arm.data.bones)))
# parts with no skeleton of their own (a lone "root") are handled after the merge; remember them now,
# because their armature objects are gone once the merge loop has re-bound their meshes
socket_parts = {part["name"] for part, arm, _m in imported if arm is not base_arm and len(arm.data.bones) <= 1}

REPOSE_TOLERANCE = 0.5   # cm; the face skeleton sits ~0.25 cm off the body rig, older outfit rigs up to 7 cm


def repose_part(arm, meshes, base_arm):
    """Pose `arm` so every bone it shares with the base rig lands on the base rest transform, then bake
    the meshes in that pose.  That is what the game's skinning does with a mesh whose bind pose comes from
    another revision of the skeleton; without it a hat rigged to the old spine floats 7 cm off the head."""
    for mesh in meshes:                       # keep the per-bone depsgraph updates cheap
        mesh.hide_viewport = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for bone in sorted(arm.data.bones, key=bone_depth):     # parents first: the setter reads the parent's pose
        target = base_arm.data.bones.get(bone.name)
        if target is None:
            continue
        arm.pose.bones[bone.name].matrix = target.matrix_local
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")
    for mesh in meshes:
        mesh.hide_viewport = False
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh in meshes:
        baked = bpy.data.meshes.new_from_object(mesh.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
        old = mesh.data
        mesh.data = baked
        baked.name = old.name
        for mod in [m for m in mesh.modifiers if m.type == "ARMATURE"]:
            mesh.modifiers.remove(mod)
        bpy.data.meshes.remove(old)


added, deviation, deviation_bone, reposed = 0, 0.0, "", []
for part, arm, meshes in imported:
    if arm is base_arm:
        continue
    # how far does this part's rest pose sit from the base rig's on the bones they share?
    worst, worst_bone = 0.0, ""
    for bone in arm.data.bones:
        target = base_arm.data.bones.get(bone.name)
        if target is None:
            continue
        diff = max(abs(bone.matrix_local[r][c] - target.matrix_local[r][c]) for r in range(4) for c in range(4))
        if diff > worst:
            worst, worst_bone = diff, bone.name
    if worst > deviation:
        deviation, deviation_bone = worst, "%s/%s" % (part["name"], worst_bone)
    if worst > REPOSE_TOLERANCE and part["name"] not in socket_parts:
        repose_part(arm, meshes, base_arm)
        reposed.append("%s (%.1f cm at %s)" % (part["name"], worst, worst_bone))
    # bones the base rig lacks: add them keeping their offset to the (possibly moved) parent
    missing = sorted((b for b in arm.data.bones if base_arm.data.bones.get(b.name) is None), key=bone_depth)
    if missing:
        bpy.context.view_layer.objects.active = base_arm
        bpy.ops.object.mode_set(mode="EDIT")
        edit = base_arm.data.edit_bones
        for bone in missing:
            ml = bone.matrix_local
            if bone.parent and bone.parent.name in edit:
                ml = edit[bone.parent.name].matrix @ (bone.parent.matrix_local.inverted() @ bone.matrix_local)
            eb = edit.new(bone.name)
            eb.head = ml.to_translation()
            eb.tail = eb.head + (ml.to_3x3() @ Vector((0.0, 1.0, 0.0))) * max(bone.length, 0.5)
            eb.align_roll(ml.to_3x3() @ Vector((0.0, 0.0, 1.0)))
            if bone.parent and bone.parent.name in edit:
                eb.parent = edit[bone.parent.name]
            added += 1
        bpy.ops.object.mode_set(mode="OBJECT")
    for mesh in meshes:
        local = arm.matrix_world.inverted() @ mesh.matrix_world
        bound = False
        for mod in mesh.modifiers:
            if mod.type == "ARMATURE" and mod.object == arm:
                mod.object = base_arm
                bound = True
        if not bound:
            mesh.modifiers.new("Armature", "ARMATURE").object = base_arm
        mesh.parent = base_arm
        mesh.matrix_parent_inverse.identity()
        mesh.matrix_basis = local
    bpy.data.objects.remove(arm, do_unlink=True)

# Parts with no skeleton of their own (a lone "root" bone — e.g. Lethita's hair) are authored around the
# origin and attached to the head socket in game: parent them to the head bone instead of skinning them.
head_bone = base_arm.data.bones.get("head")
attached = []
for part, _arm, meshes in imported:
    if part["name"] not in socket_parts or head_bone is None:
        continue
    for mesh in meshes:
        for mod in [m for m in mesh.modifiers if m.type == "ARMATURE"]:
            mesh.modifiers.remove(mod)
        mesh.parent = base_arm
        mesh.parent_type = "BONE"
        mesh.parent_bone = head_bone.name
        mesh.matrix_world = Matrix.Translation(base_arm.matrix_world @ head_bone.head_local)
    attached.append(part["name"])
if attached:
    log("attached to head bone (no own skeleton): " + ", ".join(attached))

UE_FEET = (("foot_l", "ball_l"), ("foot_r", "ball_r"))                            # UE / MetaHuman names
BIP_FEET = (("Bip001_L_Foot", "Bip001_L_Toe0"), ("Bip001_R_Foot", "Bip001_R_Toe0"))   # 3ds Max Biped (legacy sets)


def forward_of(arm, pairs):
    """Horizontal ankle -> toe direction summed over the bone pairs present in `arm`, or None."""
    bones = arm.data.bones
    vec = Vector((0.0, 0.0, 0.0))
    for ankle, toe in pairs:
        if ankle in bones and toe in bones:
            vec += (arm.matrix_world @ bones[toe].head_local) - (arm.matrix_world @ bones[ankle].head_local)
    vec.z = 0.0
    return vec.normalized() if vec.length > 1e-3 else None


def character_forward(arm):
    """Facing direction in world space of the UE hierarchy: from the ankle bones to the toe (ball) bones,
    or — for a face-only rig without legs — from the head bone to the eye bones.

    UE skeletal-mesh assets are authored facing -Y (the actor rotates them), so a fixed +X camera
    only ever sees a profile; the feet tell the truth for every rig that uses the UE bone names."""
    forward = forward_of(arm, UE_FEET)
    if forward is not None:
        return forward
    bones = arm.data.bones
    eyes = [b for b in bones if b.name.startswith(("FACIAL_L_Eyesack", "FACIAL_R_Eyesack"))]
    if "head" in bones and eyes:
        mid = sum((arm.matrix_world @ b.head_local for b in eyes), Vector()) / len(eyes)
        vec = mid - (arm.matrix_world @ bones["head"].head_local)
        vec.z = 0.0
        if vec.length > 0.5:
            return vec.normalized()
    return forward_of(arm, BIP_FEET) or Vector((0.0, -1.0, 0.0))


# The skeleton asset carries the old 3ds Max Biped rig as a second root hierarchy (`Root` -> `Bip001_*`, plus
# whatever legacy parts hung under it) laid out rotated 90 degrees from the UE hierarchy (`root` -> `pelvis`...).
# Legacy outfit parts are bound to those bones, so after the merge they face +X while the face faces -Y:
# turn that whole hierarchy (bones and the meshes bound to it) to the UE facing and put its head under the
# UE head bone.
def align_secondary_hierarchies(arm, meshes):
    bones = arm.data.bones
    primary = character_forward(arm)
    primary_root = bones["pelvis"] if "pelvis" in bones else (bones["head"] if "head" in bones else None)
    while primary_root is not None and primary_root.parent is not None:
        primary_root = primary_root.parent
    moved = []
    for root in [b for b in bones if b.parent is None and b is not primary_root]:
        subtree = set()
        stack = [root]
        while stack:
            b = stack.pop()
            subtree.add(b.name)
            stack.extend(b.children)
        feet = [(a, t) for a, t in BIP_FEET + UE_FEET if a in subtree and t in subtree]
        forward = forward_of(arm, feet) if feet else None
        if forward is None:
            continue
        angle = forward.to_2d().angle_signed(primary.to_2d(), 0.0)
        offset = Vector((0.0, 0.0, 0.0))
        rotation = Matrix.Rotation(angle, 4, "Z")
        if "Bip001_Head" in subtree and "head" in bones:
            offset = (arm.matrix_world @ bones["head"].head_local) - rotation @ (arm.matrix_world @ bones["Bip001_Head"].head_local)
            offset.z = 0.0
        if abs(angle) < math.radians(5) and offset.length < 0.5:
            continue
        transform = Matrix.Translation(offset) @ rotation
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for eb in arm.data.edit_bones:
            if eb.name in subtree:
                eb.use_connect = False
        for eb in arm.data.edit_bones:
            if eb.name in subtree:
                eb.matrix = transform @ eb.matrix
        bpy.ops.object.mode_set(mode="OBJECT")
        for mesh in meshes:
            groups = {g.name for g in mesh.vertex_groups}
            if groups and len(groups & subtree) * 2 >= len(groups):
                mesh.matrix_world = transform @ mesh.matrix_world
                moved_meshes.add(mesh.name)
        moved.append("%s: rotated %.0f deg, moved %.1f cm" % (root.name, math.degrees(angle), offset.length))
    return moved


moved_meshes = set()   # meshes bound to a legacy hierarchy (filled by align_secondary_hierarchies)
aligned = align_secondary_hierarchies(base_arm, [m for _p, _a, ms in imported for m in ms])
if aligned:
    log("aligned secondary skeleton hierarchies to the UE facing: " + "; ".join(aligned))

report["rig"] = {"bones": len(base_arm.data.bones), "added_from_parts": added,
                 "rest_pose_max_deviation": round(deviation, 4), "rest_pose_worst_bone": deviation_bone,
                 "reposed_parts": reposed, "aligned_hierarchies": aligned, "attached_to_head": attached, "hidden_parts": []}
log("rig: %d bones (+%d merged), max rest deviation %.4f cm%s" % (
    len(base_arm.data.bones), added, deviation, ("; re-posed onto the base rig: " + ", ".join(reposed)) if reposed else ""))


# ---------------------------------------------------------------- materials
meshes_all = [m for _p, _a, ms in imported for m in ms]
seen = set()
for mesh in meshes_all:
    for slot in mesh.material_slots:
        if slot.material and slot.material.name not in seen:
            seen.add(slot.material.name)
            try:
                setup_material(slot.material)
            except Exception as exc:  # noqa: BLE001 - keep going, report the material
                report["warnings"].append("material %s: %s" % (slot.material.name, exc))
                log("material %s failed: %s" % (slot.material.name, exc))
log("materials: %d (%d texture names unresolved)" % (len(seen), len(report["missing_textures"])))

# The default hair is hidden (kept in the file) when the "Head" part replaces it: list_models.py flags the
# outfits whose head piece is a hairstyle or an enclosing helmet (spec "hide_hair"), and any Head part that
# carries a hair material bundles its own hair.  Chokers, hats, caps and headphones leave the hair visible.
head_meshes = [m for part, _a, ms in imported if part["name"].lower() == "head" for m in ms]
head_kinds = [report["materials"].get(base_material_name(s.material.name), {}).get("kind")
              for m in head_meshes for s in m.material_slots if s.material]
head_has_hair = "hair" in head_kinds
hidden = []
if head_meshes and head_kinds and all(k == "hair" for k in head_kinds) and all(m.name in moved_meshes for m in head_meshes):
    # a legacy set's own hairstyle was made for the old head: it hangs over the new face, so keep the current
    # default hair and hide the legacy hair part instead
    for m in head_meshes:
        m.hide_render = True
        m.hide_viewport = True
        m.hide_set(True)
    hidden.append("Head")
    report["rig"]["hidden_parts"] = hidden
    log("hidden (legacy hairstyle, default hair kept): Head")
elif head_meshes and (SPEC.get("hide_hair") or head_has_hair):
    for part, _arm, meshes in imported:
        if part["name"].lower() == "hair":
            for mesh in meshes:
                mesh.hide_render = True
                mesh.hide_viewport = True
                mesh.hide_set(True)
            hidden.append(part["name"])
    report["rig"]["hidden_parts"] = hidden
    if hidden:
        log("hidden (replaced by the Head part): " + ", ".join(hidden))


# ---------------------------------------------------------------- pack textures next to the blend, save
copied = 0
for image in list(bpy.data.images):
    src = bpy.path.abspath(image.filepath) if image.filepath else ""
    if not src or not os.path.isfile(src):
        continue
    dst = os.path.join(TEX_DIR, os.path.basename(src))
    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
        copied += 1
    image.filepath = dst
    image.filepath_raw = dst
blend_path = os.path.join(OUT_DIR, MODEL_ID + ".blend")
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=True)
report["blend"] = blend_path
report["textures_copied"] = copied
report["textures_total"] = len([i for i in bpy.data.images if i.filepath])
log("saved %s (%d textures in textures/)" % (blend_path, report["textures_total"]))


# ---------------------------------------------------------------- previews (after the save: cameras/lights stay out of the blend)
def frame_points(objects):
    pts = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, mx - mn


def render(path, center, ortho_scale, size, distance, forward):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho_scale
    cam_data.clip_start = 1.0
    cam_data.clip_end = distance * 10
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    # camera in front of the character, looking back at it
    cam.location = center + forward * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "None"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_soft_shadows = True
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    log("rendered " + path)


if not NO_PREVIEW:
    scene = bpy.context.scene
    center, extent = frame_points(meshes_all)
    height = max(extent.z, extent.y, extent.x, 1e-6)
    forward = character_forward(base_arm)
    side = forward.cross(Vector((0.0, 0.0, 1.0)))
    report["forward"] = [round(c, 3) for c in forward]
    # key / fill / rim relative to the facing direction
    for name, (f, s, z), energy in (("Key", (1.2, 0.9, 1.2), 3.0), ("Fill", (0.9, -1.0, 0.6), 1.4), ("Rim", (-0.8, -0.2, 1.1), 1.6)):
        light = bpy.data.lights.new(name, "SUN")
        light.energy = energy
        light.angle = math.radians(10)
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + (forward * f + side * s + Vector((0.0, 0.0, z))) * height
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.58, 0.58, 0.62, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world
    preview = os.path.join(OUT_DIR, "preview.png")
    render(preview, center, max(extent.z * 1.12, max(extent.x, extent.y) * 1.5), (900, 1400), height * 3, forward)
    report["preview"] = preview
    head = base_arm.data.bones.get("head")
    if head is not None:
        head_pos = base_arm.matrix_world @ head.head_local
        face_center = head_pos + Vector((0.0, 0.0, height * 0.045))
        face = os.path.join(OUT_DIR, "preview_face.png")
        render(face, face_center, height * 0.22, (900, 900), height, forward)
        report["preview_face"] = face

print("VINDICTUS_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
