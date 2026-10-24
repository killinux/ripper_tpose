r"""Stellar Blade eye colour the way the game computes it, as Blender nodes (Blender 3.6).

Every character's eye is an instance of ``M_EyeRefractive`` (UE's refractive eye, extended by Shift Up), read with
CUE4Parse - Eve's is ``MI_EyeRefractive1`` (SB/Content/Art/Character/PC/CH_P_EVE_Head/Materials).  Its colour,
before the cornea's refraction:

  * the whole eye UV is scaled about the centre by ``ScaleByCenter`` - UE's ScaleUVsByCenter, (uv - 0.5) / s + 0.5,
    so the CONTENT shrinks to 85%;
  * the iris texture (``IrisColor``) fills the disc of radius ``Iris UV Radius`` in that UV
    ((uv' - 0.5) / (2 r) + 0.5), its pupil drawn in by ``PupilScale`` (radii near the centre read further out; the
    iris edge stays);
  * the iris colour is hue-rotated by ``IrisHueShift`` (UE's HueShift: a turn about the grey axis, 1 = 360 deg),
    multiplied by ``IrisHueTint`` and by ``IrisBrightness``; the sclera texture (``ScleraColor``) by ``ScleraTint``
    and ``ScleraBrightness``;
  * iris -> sclera over ``LimbusUVWidthColor`` inside the iris edge.

The tint is how one texture gives every eye colour: S_EyeIrisBaseColor is orange-brown, and the game's
MI_MetaEyes_BlueEyes / _GreenEyes / _BrownEyes use that same texture with tints (0.05, 0.30, 0.89),
(0.35, 0.86, 0.91), (0.22, 0.26, 0.44) - the blue one at IrisBrightness 14.9 to make up for the darkening.  Eve's
tint (0.656, 0.598, 1) takes some of the orange out of her brown.  An instance that leaves a value out has the parent
material's (M_EYE_REFRACTIVE, from M_EyeRefractive's CachedExpressionData), not Eve's.

On the eyeball mesh (cornea apex at UV 0.5, 0.5; the back half folds onto the same disc) Eve's iris edge is at UV
radius 0.145 x 0.849798 = 0.123.  Checked against an in-game render of Eve (ClearReward_Nikke_01): iris width /
corner-to-corner eye width 0.49 in the game, 0.50 with these nodes; the iris touches both lids.  Not reproduced:
the refraction (DepthScale - in the game it magnifies the pupil a little), the limbus darkening (LimbusDarkScale,
0 for Eve) and the eye-corner shadow (ShadowRadius, EyeCornerDarknessColor).

validate_eve.py before 2026-10-17 put the iris at radius 0.07 with a guessed 2.6x brightness: 40% of the game's
width, and a darker, greyer brown.  rewire_eye() replaces such a network in place (export_pmx_blender.py,
hq_materials_blender.py), so archived .blend files need not be rebuilt.  The tint and the hue shift came in on
2026-10-18 (before that the iris was S_EyeIrisBaseColor x 5 untinted, a brighter orange).
"""
import json
import math
import os
import re

# M_EyeRefractive's own values: what an instance leaves out
M_EYE_REFRACTIVE = {
    "iris_uv_radius": 0.15,
    "scale_by_center": 1.0,
    "pupil_scale": 0.7,
    "limbus_uv_width": 0.035,
    "iris_brightness": 1.0,
    "sclera_brightness": 0.9,
    "iris_tint": (1.0, 1.0, 1.0),
    "iris_hue_shift": 0.0,
    "sclera_tint": (1.0, 1.0, 1.0),
}
M_EYE_TEXTURES = {"iris": "T_EyeIrisBaseColor_Example_2", "sclera": "T_EyeScleraBaseColor"}
# Eve's MI_EyeRefractive1 - the default when no instance is given
GAME = dict(M_EYE_REFRACTIVE, iris_uv_radius=0.145, scale_by_center=0.849798, pupil_scale=0.861905,
            limbus_uv_width=0.045, iris_brightness=5.0, sclera_brightness=1.6, iris_tint=(0.656316, 0.597641, 1.0))
GAME_TEXTURES = {"iris": "S_EyeIrisBaseColor", "sclera": "T_EyeScleraBaseColor"}
# M_EYE_TEXTURES + Eve's iris as PNG (CUE4Parse), for an instance whose textures are not next to the model
SHARED_TEXTURES = r"E:\game_export\StellarBlade\_meta\hq_materials\_eye_textures"
MARK = "sb_eye"                   # material property: which eye network it carries
IRIS_IMAGE = "eyeiris"            # S_EyeIrisBaseColor, T_EyeIrisBaseColor_Example_2
SCLERA_IMAGE = "eyesclera"        # T_EyeScleraBaseColor
# M_EyeRefractive's parameters -> params keys
MI_SCALARS = {"Iris UV Radius": "iris_uv_radius", "ScaleByCenter": "scale_by_center", "PupilScale": "pupil_scale",
              "LimbusUVWidthColor": "limbus_uv_width", "IrisBrightness": "iris_brightness",
              "ScleraBrightness": "sclera_brightness", "IrisHueShift": "iris_hue_shift"}
MI_VECTORS = {"IrisHueTint": "iris_tint", "ScleraTint": "sclera_tint"}
MI_TEXTURES = {"IrisColor": "iris", "ScleraColor": "sclera"}
EYE_PARENT = "M_EyeRefractive"


def full_params(params=None):
    """params over Eve's values (None = Eve's); tints as tuples"""
    p = dict(GAME)
    p.update(params or {})
    for key in ("iris_tint", "sclera_tint"):
        p[key] = tuple(float(c) for c in p[key])
    return p


def iris_radius_on_mesh(params=None):
    p = full_params(params)
    return p["iris_uv_radius"] * p["scale_by_center"]


def params_from_values(scalars, vectors=None):
    """a character's own M_EyeRefractive instance ({UE parameter name: value}, vectors as {R, G, B ...}); what it
    leaves out is the parent's (M_EYE_REFRACTIVE)"""
    p = dict(M_EYE_REFRACTIVE)
    for ue, key in MI_SCALARS.items():
        if ue in scalars:
            p[key] = float(scalars[ue])
    for ue, key in MI_VECTORS.items():
        v = (vectors or {}).get(ue)
        if v:
            p[key] = (float(v["R"]), float(v["G"]), float(v["B"]))
    return p


def describe(params):
    p = full_params(params)
    return "iris r %.4f on the mesh, x %s x %.3g%s" % (
        iris_radius_on_mesh(p), "(%.3f %.3f %.3f)" % p["iris_tint"], p["iris_brightness"],
        ", hue %+.3f" % p["iris_hue_shift"] if p["iris_hue_shift"] % 1.0 else "")


def eye_from_instance(name, parent, scalars, vectors, textures):
    """one M_EyeRefractive instance -> {material, params, textures: {iris, sclera: texture name}}; None for other
    parents"""
    if parent != EYE_PARENT:
        return None
    tex = dict(M_EYE_TEXTURES)
    for ue, key in MI_TEXTURES.items():
        if textures.get(ue):
            tex[key] = textures[ue]
    return {"material": name, "params": params_from_values(scalars, vectors), "textures": tex}


def eye_from_mi_json(path):
    """the eye record of a CUE4Parse JSON (e.g. <char>/Materials/MI_CH_NPC_Lilly_Eyes.json)"""
    for e in json.load(open(path, encoding="utf-8-sig")):
        if not e.get("Type", "").startswith("MaterialInstance"):
            continue
        props = e.get("Properties") or {}
        parent = ((props.get("Parent") or {}).get("ObjectPath") or "").split("/")[-1].split(".")[0]
        values = {}
        for kind in ("ScalarParameterValues", "VectorParameterValues", "TextureParameterValues"):
            values[kind] = {s["ParameterInfo"]["Name"]: s["ParameterValue"] for s in props.get(kind) or []}
        textures = {k: ((v or {}).get("ObjectPath") or "").split("/")[-1].split(".")[0]
                    for k, v in values["TextureParameterValues"].items()}
        eye = eye_from_instance(e["Name"], parent, values["ScalarParameterValues"],
                                values["VectorParameterValues"], textures)
        if eye is None:
            raise ValueError("%s: %s is not an %s instance (parent %s)" % (path, e["Name"], EYE_PARENT, parent))
        eye["file"] = os.path.abspath(path)
        return eye
    raise ValueError("no material instance in %s" % path)


def find_texture_file(name, roots):
    for root in roots:
        for sub in ("", "extra", "textures", os.path.join("textures", "extra")):
            path = os.path.join(root, sub, name + ".png")
            if os.path.isfile(path):
                return os.path.abspath(path)
    return None


def link_eye_colour(nodes, links, shader, sclera_image, iris_image, params=None, x=-1500.0, y=300.0):
    """The game's iris / sclera / limbus colour into shader's Base Color; returns the mix node.  params = an
    instance's values (params_from_values), None = Eve's."""
    p = full_params(params)
    s, r, w = p["scale_by_center"], p["iris_uv_radius"], p["limbus_uv_width"]

    def node(kind, dx, dy, label=""):
        n = nodes.new(kind)
        n.location = (x + dx, y + dy)
        n.label = label
        n[MARK] = 1
        return n

    uv = node("ShaderNodeTexCoord", 0, 0)
    eye_uv = node("ShaderNodeMapping", 200, 0, "ScaleByCenter")     # (uv - 0.5) / s + 0.5
    eye_uv.vector_type = "POINT"
    eye_uv.inputs["Scale"].default_value = (1.0 / s, 1.0 / s, 1.0)
    eye_uv.inputs["Location"].default_value = (0.5 - 0.5 / s, 0.5 - 0.5 / s, 0.0)
    links.new(uv.outputs["UV"], eye_uv.inputs["Vector"])

    sclera = node("ShaderNodeTexImage", 450, 300, "sclera")
    sclera.image = sclera_image
    links.new(eye_uv.outputs["Vector"], sclera.inputs["Vector"])
    sclera_t = node("ShaderNodeVectorMath", 750, 300, "ScleraTint")
    sclera_t.operation = "MULTIPLY"
    sclera_t.inputs[1].default_value = p["sclera_tint"]
    links.new(sclera.outputs["Color"], sclera_t.inputs[0])
    sclera_b = node("ShaderNodeVectorMath", 950, 300, "ScleraBrightness")
    sclera_b.operation = "SCALE"
    sclera_b.inputs["Scale"].default_value = p["sclera_brightness"]
    links.new(sclera_t.outputs["Vector"], sclera_b.inputs[0])

    centred = node("ShaderNodeMapping", 450, -50, "iris UV - 0.5")   # (uv' - 0.5) / (2 r)
    centred.vector_type = "POINT"
    k = 1.0 / (2.0 * r)
    centred.inputs["Scale"].default_value = (k, k, 1.0)
    centred.inputs["Location"].default_value = (-0.5 * k, -0.5 * k, 0.0)
    links.new(eye_uv.outputs["Vector"], centred.inputs["Vector"])
    length = node("ShaderNodeVectorMath", 650, -200, "")
    length.operation = "LENGTH"
    links.new(centred.outputs["Vector"], length.inputs[0])
    pupil = node("ShaderNodeMapRange", 800, -200, "PupilScale")   # 1 / PupilScale at the centre -> 1 at the edge
    pupil.inputs["From Min"].default_value = 0.0
    pupil.inputs["From Max"].default_value = 0.5
    pupil.inputs["To Min"].default_value = 1.0 / p["pupil_scale"]
    pupil.inputs["To Max"].default_value = 1.0
    pupil.clamp = True
    links.new(length.outputs["Value"], pupil.inputs["Value"])
    drawn = node("ShaderNodeVectorMath", 1000, -50, "")
    drawn.operation = "SCALE"
    links.new(centred.outputs["Vector"], drawn.inputs[0])
    links.new(pupil.outputs["Result"], drawn.inputs["Scale"])
    iris_uv = node("ShaderNodeVectorMath", 1150, -50, "")
    iris_uv.operation = "ADD"
    iris_uv.inputs[1].default_value = (0.5, 0.5, 0.0)
    links.new(drawn.outputs["Vector"], iris_uv.inputs[0])
    iris = node("ShaderNodeTexImage", 1300, -50, "iris")
    iris.image = iris_image
    iris.extension = "EXTEND"
    links.new(iris_uv.outputs["Vector"], iris.inputs["Vector"])
    hue = node("ShaderNodeVectorRotate", 1600, -50, "IrisHueShift")  # UE HueShift: a turn about the grey axis
    hue.rotation_type = "AXIS_ANGLE"
    hue.inputs["Axis"].default_value = (1.0, 1.0, 1.0)
    hue.inputs["Angle"].default_value = 2.0 * math.pi * p["iris_hue_shift"]
    links.new(iris.outputs["Color"], hue.inputs["Vector"])
    tint = node("ShaderNodeVectorMath", 1800, -50, "IrisHueTint")
    tint.operation = "MULTIPLY"
    tint.inputs[1].default_value = p["iris_tint"]
    links.new(hue.outputs["Vector"], tint.inputs[0])
    iris_b = node("ShaderNodeVectorMath", 2000, -50, "IrisBrightness")
    iris_b.operation = "SCALE"
    iris_b.inputs["Scale"].default_value = p["iris_brightness"]
    links.new(tint.outputs["Vector"], iris_b.inputs[0])

    dist = node("ShaderNodeVectorMath", 650, -400, "")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (0.5, 0.5, 0.0)
    links.new(eye_uv.outputs["Vector"], dist.inputs[0])
    limbus = node("ShaderNodeMapRange", 1000, -400, "iris mask (limbus)")
    limbus.interpolation_type = "SMOOTHSTEP"
    limbus.inputs["From Min"].default_value = r - w
    limbus.inputs["From Max"].default_value = r
    limbus.inputs["To Min"].default_value = 1.0
    limbus.inputs["To Max"].default_value = 0.0
    limbus.clamp = True
    links.new(dist.outputs["Value"], limbus.inputs["Value"])

    mix = node("ShaderNodeMixRGB", 2200, 100, "game eye colour")
    mix.blend_type = "MIX"
    links.new(limbus.outputs["Result"], mix.inputs["Fac"])
    links.new(sclera_b.outputs["Vector"], mix.inputs["Color1"])
    links.new(iris_b.outputs["Vector"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], shader.inputs["Base Color"])
    return mix


def _upstream(socket):
    seen, todo = set(), [link.from_node for link in socket.links]
    while todo:
        n = todo.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        for s in n.inputs:
            todo += [link.from_node for link in s.links]
    return seen


def texture_name(value):
    """a texture entry (a .png path, "MISSING:<name>" or a bare name) -> the texture's name"""
    value = str(value or "")
    if value.startswith("MISSING:"):
        return value.split(":", 1)[1]
    return os.path.splitext(os.path.basename(value))[0]


def _images_by_name(mat, names):
    """{key: first image in mat whose name / file name contains names[key] (case-insensitive)}"""
    found = {}
    for n in mat.node_tree.nodes:
        if n.type != "TEX_IMAGE" or n.image is None:
            continue
        text = (n.image.name + " " + os.path.basename(n.image.filepath)).lower()
        for key, name in names.items():
            if name and key not in found and name.lower() in text:
                found[key] = n.image
    return found


def eye_images(mat):
    """(sclera, iris) of the game's shared eye textures in an eye material, or None"""
    found = _images_by_name(mat, {"iris": IRIS_IMAGE, "sclera": SCLERA_IMAGE})
    return (found["sclera"], found["iris"]) if len(found) == 2 else None


def base_name(name):
    """a Blender datablock name without its .001 suffix"""
    return re.sub(r"\.\d{3}$", "", name)


def images_for(mat, eye=None, roots=(), load=None):
    """(sclera, iris) for an eye record: the instance's own textures where the material has them, else (with load,
    a callable path -> image) loaded from the record's file or found by name under roots, else the shared eye
    textures in the material; None if a side is missing"""
    textures = (eye or {}).get("textures") or {}
    names = {k: texture_name(v) for k, v in textures.items() if k in ("iris", "sclera")}
    found = _images_by_name(mat, names)
    for key, name in names.items():
        if key in found or load is None:
            continue
        value = str(textures[key])
        path = value if os.path.isfile(value) else find_texture_file(name, roots)
        if path:
            found[key] = load(path)
    for key, image in _images_by_name(mat, {"iris": IRIS_IMAGE, "sclera": SCLERA_IMAGE}).items():
        found.setdefault(key, image)
    return (found["sclera"], found["iris"]) if "sclera" in found and "iris" in found else None


def rewire_eye(mat, eye=None, roots=(), load=None):
    """Replace whatever drives the eye material's Base Color with the game's network (nodes that only fed the base
    colour go).  eye = the character's eye record ({material, params, textures} from eye_from_mi_json or
    hq_materials.py's materials.json), None = Eve's MI_EyeRefractive1; load (path -> image) + roots: bring in the
    record's textures when the material lacks them - only for a material known to be this eye (by name), or any
    material would pass.  Returns a short description, or None when mat is not an eye material (no Principled
    BSDF, or no iris / sclera texture)."""
    if not mat.use_nodes or mat.node_tree is None:
        return None
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    images = images_for(mat, eye, roots, load) if shader is not None else None
    if images is None:
        return None
    p = full_params((eye or {}).get("params"))
    keep = set()
    for s in shader.inputs:
        if s.name != "Base Color":
            keep |= _upstream(s)
    for n in [n for n in nodes if n.name in _upstream(shader.inputs["Base Color"]) - keep]:
        nodes.remove(n)
    loc = shader.location
    link_eye_colour(nodes, links, shader, images[0], images[1], p, x=loc.x - 2500, y=loc.y + 300)
    mat[MARK] = "game eye of %s: %s; textures %s, %s" % (
        (eye or {}).get("material") or "Eve's MI_EyeRefractive1", describe(p), images[1].name, images[0].name)
    return mat[MARK]
