"""Blender (3.6) side of the Taimanin Squad exporter: scene.json -> .blend (+ previews).

    blender -b --factory-startup -P build_blend.py -- --scene <dir>/scene.json --out <id>.blend
            [--no-preview] [--views <dir>] [--tiles <dir>] [--no-outline] [--no-weld] [--no-save]

scene.json comes from export_model.py (tsquad_scene.py): the skeleton in Unity space with world
matrices, parts whose vertices are already skinned to the prefab pose, materials with decoded
PNG textures.  Unity (left-handed, Y up, metres) -> Blender (right-handed, Z up, metres) is
(x, y, z) -> (-x, -z, y); the character ends up facing -Y, its left side at +X.

The materials rebuild the game's own toon shader (Squad/SquadToon) from its compiled program,
term by term (see the README, "着色器还原"):

    lit      = sat((N.L * 0.5 + 0.5 - Shadow1Step + Shadow1Feather) / Shadow1Feather)
    diffuse  = lerp(InShadowMap, BaseMap * BaseColor, lit)
    specular = BaseMap * SpecColor * Mask.g^2 * toon-stepped GGX (or the view-normal band) * lit
    rim      = RimColor * stepped fresnel, blended with -L.V and with lit / 1 - lit
    matcap   = MatCapMap(view normal) * MatCapColor * Mask.b * lit
    emission = Mask.r * BaseMap * BaseColor * _EmissionColor
    face     : lit comes from the SDF threshold map (tex_on) and the head / light directions

Everything is emission-based maths on the normal, the view vector and one light direction, so it
looks the same in EEVEE and Cycles and does not depend on lamp strength.  The light direction is
the +Z axis of the object "TSQ_Sun" (rotate it to relight); the head axes for the face shadow
follow the head bone.  Both are fed by plain transform drivers (no Python expressions).
The outline is the game's inverted hull: a Solidify modifier, flipped, _Outline_Width mm wide.
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
VIEWS_DIR = arg("--views")
TILES_DIR = arg("--tiles")                                # one face close-up per shape key (export_model.py tiles them)
NO_PREVIEW = "--no-preview" in argv
NO_OUTLINE = "--no-outline" in argv
NO_WELD = "--no-weld" in argv
NO_SAVE = "--no-save" in argv
SRC_DIR = os.path.dirname(os.path.abspath(SCENE_PATH))
with open(SCENE_PATH, encoding="utf-8") as fh:
    SCENE = json.load(fh)
SCALE = float(SCENE.get("unit_scale", 1.0))
C3 = np.array([[-1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
LIGHT_DIR = Vector((0.42, -0.72, 0.55)).normalized()      # towards the light: front, upper left of the character
report = {"id": SCENE.get("id"), "parts": 0, "vertices": 0, "faces": 0, "bones": 0, "materials_built": {},
          "missing_textures": [], "warnings": list(SCENE.get("warnings", [])), "shape_keys": 0, "welded": 0}


def log(msg):
    print("[tsquad] " + msg, flush=True)


def conv_points(arr):
    return (np.asarray(arr, dtype=np.float64) @ C3.T) * SCALE


def conv_matrix(m):
    m = np.asarray(m, dtype=np.float64)
    r = C3 @ m[:3, :3] @ C3.T
    r = r / np.maximum(np.linalg.norm(r, axis=0, keepdims=True), 1e-12)   # drop scale
    out = np.eye(4)
    out[:3, :3] = r
    out[:3, 3] = C3 @ m[:3, 3] * SCALE
    return Matrix(out.tolist())


def srgb_to_linear(v):
    v = max(0.0, float(v))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgba(c, alpha=1.0):
    """Unity material colours are sRGB; Blender colour sockets are linear."""
    return (srgb_to_linear(c[0]), srgb_to_linear(c[1]), srgb_to_linear(c[2]), alpha)


# ---------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.view_settings.view_transform = "Standard"           # the textures are the final colours
scene.view_settings.look = "None"
NAME = SCENE.get("id", "tsquad")

# ---------------------------------------------------------------- armature
nodes = SCENE["nodes"]
arm_data = bpy.data.armatures.new(NAME + "_Armature")
arm = bpy.data.objects.new(NAME + "_Armature", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
arm_data.display_type = "STICK"
arm.show_in_front = True
children = {}
for n in nodes:
    children.setdefault(n["parent"], []).append(n["name"])
world = {n["name"]: conv_matrix(n["world"]) for n in nodes}
parent_of = {n["name"]: n["parent"] for n in nodes}
lengths = {}


def bone_tail(name):
    """Tail along the bone's own axis: Biped / Bone_* chains run along local -X in the game's
    Unity space, which is still local -X after the axis change (the handedness flip is in C3)."""
    m = world[name]
    head = m.to_translation()
    axis = (m.to_3x3() @ Vector((-1.0, 0.0, 0.0))).normalized()
    kids = [world[c].to_translation() for c in children.get(name, [])]
    kids = [k for k in kids if (k - head).length > 1e-3]
    if len(kids) == 1:
        return kids[0]
    best = None
    for k in kids:
        d = (k - head)
        if d.normalized().dot(axis) > 0.9 and (best is None or d.length > best):
            best = d.length
    if best is None:
        parent = parent_of.get(name)
        best = min(0.1, max(0.01, lengths.get(parent, 0.06) * 0.5))
        if head.length < 1e-4 and abs(axis.z) < 0.5:      # a root at the origin: stand it up
            axis = Vector((0.0, 0.0, 1.0))
    return head + axis * best


bpy.ops.object.mode_set(mode="EDIT")
ebones = {}
for n in nodes:
    name = n["name"]
    eb = arm_data.edit_bones.new(name)
    m = world[name]
    head = m.to_translation()
    tail = bone_tail(name)
    if (tail - head).length < 1e-4:
        tail = head + Vector((0.0, 0.0, 0.02))
    eb.head, eb.tail = head, tail
    lengths[name] = (tail - head).length
    eb.align_roll(m.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    ebones[name] = eb
for n in nodes:
    if n["parent"] in ebones:
        ebones[n["name"]].parent = ebones[n["parent"]]
bpy.ops.object.mode_set(mode="OBJECT")
skinned = set(SCENE.get("skinned_bones", []))
for bone in arm_data.bones:
    bone.use_deform = bone.name in skinned
report["bones"] = len(nodes)
log("armature: %d bones (%d skinned)" % (len(nodes), len(skinned)))

# ---------------------------------------------------------------- light rig
sun_data = bpy.data.lights.new("TSQ_Sun", "SUN")
sun_data.energy = 2.0
sun = bpy.data.objects.new("TSQ_Sun", sun_data)
scene.collection.objects.link(sun)
sun.location = (0.6, -1.2, 2.2)
sun.rotation_mode = "XYZ"
sun.rotation_euler = LIGHT_DIR.to_track_quat("Z", "Y").to_euler("XYZ")


# ---------------------------------------------------------------- node helpers
def new_group(name, inputs, outputs):
    """inputs / outputs: [(socket type, name, default)]"""
    tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
    for kind, label, default in inputs:
        sock = tree.inputs.new(kind, label)
        if default is not None and hasattr(sock, "default_value"):
            sock.default_value = default
    for kind, label, _default in outputs:
        tree.outputs.new(kind, label)
    gin = tree.nodes.new("NodeGroupInput")
    gin.location = (-1400, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.location = (1600, 0)
    return tree, gin, gout


class N:
    """Small node-graph builder: every method returns an output socket."""

    def __init__(self, tree, x=0, y=0):
        self.tree = tree
        self.x, self.y = x, y

    def _place(self, node):
        node.location = (self.x, self.y)
        self.y -= 160
        if self.y < -2400:
            self.y = 0
            self.x += 220
        return node

    def put(self, sock, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, sock)
        elif value is not None:
            if isinstance(value, (int, float)) and hasattr(sock.default_value, "__len__"):
                sock.default_value = (value,) * len(sock.default_value)
            else:
                sock.default_value = value

    def math(self, op, a, b=None, c=None, clamp=False):
        node = self._place(self.tree.nodes.new("ShaderNodeMath"))
        node.operation = op
        node.use_clamp = clamp
        self.put(node.inputs[0], a)
        if b is not None:
            self.put(node.inputs[1], b)
        if c is not None:
            self.put(node.inputs[2], c)
        return node.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        node = self._place(self.tree.nodes.new("ShaderNodeVectorMath"))
        node.operation = op
        self.put(node.inputs[0], a)
        if b is not None:
            self.put(node.inputs[1], b)
        if scale is not None:
            self.put(node.inputs[3], scale)
        return node.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else node.outputs["Vector"]

    def mix(self, fac, a, b):
        """lerp(a, b, fac) on colours / vectors."""
        node = self._place(self.tree.nodes.new("ShaderNodeMixRGB"))
        node.blend_type = "MIX"
        self.put(node.inputs[0], fac)
        self.put(node.inputs[1], a)
        self.put(node.inputs[2], b)
        return node.outputs[0]

    def lerp(self, fac, a, b):
        """lerp(a, b, fac) on scalars: a + fac * (b - a)."""
        return self.math("ADD", a, self.math("MULTIPLY", fac, self.math("SUBTRACT", b, a)))

    def ramp(self, value, step, feather, floor=1e-4):
        """sat((value - step + feather) / max(feather, floor)) - the shader's toon step."""
        num = self.math("ADD", self.math("SUBTRACT", value, step), feather)
        return self.math("DIVIDE", num, self.math("MAXIMUM", feather, floor), clamp=True)

    def separate(self, color):
        node = self._place(self.tree.nodes.new("ShaderNodeSeparateRGB"))
        self.put(node.inputs[0], color)
        return node.outputs

    def combine_xyz(self, x, y, z):
        node = self._place(self.tree.nodes.new("ShaderNodeCombineXYZ"))
        for sock, value in zip(node.inputs, (x, y, z)):
            self.put(sock, value)
        return node.outputs[0]

    def separate_xyz(self, vec):
        node = self._place(self.tree.nodes.new("ShaderNodeSeparateXYZ"))
        self.put(node.inputs[0], vec)
        return node.outputs

    def node(self, kind, **props):
        node = self._place(self.tree.nodes.new(kind))
        for k, v in props.items():
            setattr(node, k, v)
        return node


def rotation_driver(tree, node, target_object, bone=""):
    """Drive a Combine XYZ node's three inputs with the world-space XYZ Euler rotation of an
    object (or one of its pose bones).  One TRANSFORMS variable per driver, type SUM: no Python."""
    for i, axis in enumerate(("ROT_X", "ROT_Y", "ROT_Z")):
        fcurve = node.inputs[i].driver_add("default_value")
        driver = fcurve.driver
        driver.type = "SUM"
        var = driver.variables.new()
        var.name = "rot"
        var.type = "TRANSFORMS"
        target = var.targets[0]
        target.id = target_object
        if bone:
            target.bone_target = bone
        target.transform_type = axis
        target.transform_space = "WORLD_SPACE"
        target.rotation_mode = "XYZ"


def axis_from_rotation(b, euler_socket, local_axis):
    """World direction of a constant local axis under the driven Euler rotation."""
    node = b.node("ShaderNodeVectorRotate", rotation_type="EULER_XYZ")
    node.inputs["Vector"].default_value = tuple(local_axis)
    node.inputs["Center"].default_value = (0.0, 0.0, 0.0)
    b.tree.links.new(euler_socket, node.inputs["Rotation"])
    return node.outputs["Vector"]


# ---------------------------------------------------------------- shared groups
def make_light_group():
    tree, _gin, gout = new_group("TSQ Light", [], [("NodeSocketVector", "Light Dir", None),
                                                   ("NodeSocketColor", "Light Color", None),
                                                   ("NodeSocketFloat", "Ambient", None)])
    b = N(tree, -600, 200)
    euler = b.node("ShaderNodeCombineXYZ", label="TSQ_Sun rotation (driver)")
    rotation_driver(tree, euler, sun)
    direction = axis_from_rotation(b, euler.outputs[0], (0.0, 0.0, 1.0))
    color = b.node("ShaderNodeRGB", label="Light Color")
    color.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    ambient = b.node("ShaderNodeValue", label="Ambient (albedo x this is added)")
    ambient.outputs[0].default_value = 0.0
    tree.links.new(b.vmath("NORMALIZE", direction), gout.inputs["Light Dir"])
    tree.links.new(color.outputs[0], gout.inputs["Light Color"])
    tree.links.new(ambient.outputs[0], gout.inputs["Ambient"])
    return tree


LIGHT_GROUP = make_light_group()

TOON_INPUTS = [
    ("NodeSocketColor", "Base Color", (1, 1, 1, 1)), ("NodeSocketFloat", "Base Alpha", 1.0),
    ("NodeSocketColor", "Shade Color", (0.5, 0.5, 0.5, 1)), ("NodeSocketColor", "Mask", (1, 1, 1, 1)),
    ("NodeSocketColor", "MatCap", (0, 0, 0, 1)),
    ("NodeSocketFloat", "Lit Override", 1.0), ("NodeSocketFloat", "Use Lit Override", 0.0),
    ("NodeSocketColor", "Base Tint", (1, 1, 1, 1)), ("NodeSocketFloat", "Tint Alpha", 1.0),
    ("NodeSocketFloat", "Shadow Step", 0.5), ("NodeSocketFloat", "Shadow Feather", 0.02),
    ("NodeSocketFloat", "Shadow Colors", 0.0), ("NodeSocketColor", "Shadow1 Color", (0.8, 0.8, 0.8, 1)),
    ("NodeSocketColor", "Shadow2 Color", (0.5, 0.5, 0.5, 1)), ("NodeSocketFloat", "Shadow2 Step", 0.5),
    ("NodeSocketFloat", "Shadow2 Feather", 0.05),
    ("NodeSocketFloat", "Specular", 1.0), ("NodeSocketColor", "Spec Color", (1, 1, 1, 1)),
    ("NodeSocketFloat", "Smoothness", 0.5), ("NodeSocketFloat", "Spec Step", 0.5),
    ("NodeSocketFloat", "Spec Feather", 0.05), ("NodeSocketFloat", "Spec View Normal", 0.0),
    ("NodeSocketColor", "Rim Color", (0, 0, 0, 1)), ("NodeSocketFloat", "Rim Step", 0.5),
    ("NodeSocketFloat", "Rim Feather", 0.05), ("NodeSocketFloat", "Rim Flip", 0.0),
    ("NodeSocketFloat", "Rim Blend Shadow", 0.5), ("NodeSocketFloat", "Rim Blend LdotV", 0.5),
    ("NodeSocketColor", "MatCap Color", (1, 1, 1, 1)), ("NodeSocketFloat", "MatCap Ignore Shadow", 0.0),
    ("NodeSocketFloat", "Emission", 0.0),
    ("NodeSocketFloat", "Cull Back", 1.0),
]


def make_toon_group():
    tree, gin, gout = new_group("TSQ Toon", TOON_INPUTS, [
        ("NodeSocketShader", "Shader", None), ("NodeSocketColor", "Color", None),
        ("NodeSocketFloat", "Alpha", None), ("NodeSocketFloat", "Lit", None)])
    i = gin.outputs
    b = N(tree, -1100, 1200)
    light = b.node("ShaderNodeGroup", node_tree=LIGHT_GROUP, label="light")
    geo = b.node("ShaderNodeNewGeometry")
    nrm = b.vmath("NORMALIZE", geo.outputs["Normal"])
    view = b.vmath("NORMALIZE", geo.outputs["Incoming"])
    ldir = light.outputs["Light Dir"]
    ndl = b.vmath("DOT_PRODUCT", nrm, ldir)
    half_lambert = b.math("ADD", b.math("MULTIPLY", ndl, 0.5), 0.5)
    lit = b.lerp(i["Use Lit Override"], b.ramp(half_lambert, i["Shadow Step"], i["Shadow Feather"]),
                 i["Lit Override"])

    # diffuse: the shade texture, or (keyword _SHADOWCOLOR) two tinted steps of the albedo
    albedo = b.vmath("MULTIPLY", i["Base Color"], i["Base Tint"])
    ramp2 = b.ramp(half_lambert, i["Shadow2 Step"], i["Shadow2 Feather"])
    tinted = b.mix(ramp2, b.vmath("MULTIPLY", albedo, i["Shadow2 Color"]),
                   b.vmath("MULTIPLY", albedo, i["Shadow1 Color"]))
    shade = b.mix(i["Shadow Colors"], i["Shade Color"], tinted)
    diffuse = b.mix(lit, shade, albedo)

    # specular: URP's GGX term, cut by a toon step on the normalised lobe
    b.x, b.y = -500, 1200
    mask = b.separate(i["Mask"])
    smooth = b.math("MULTIPLY", b.math("MULTIPLY", i["Smoothness"], i["Smoothness"]), i["Base Alpha"])
    rough = b.math("MAXIMUM", b.math("POWER", b.math("SUBTRACT", 1.0, smooth), 2.0), 0.0078125)
    rough2 = b.math("MULTIPLY", rough, rough)
    half = b.vmath("NORMALIZE", b.vmath("ADD", view, ldir))
    noh = b.math("MAXIMUM", b.vmath("DOT_PRODUCT", nrm, half), 0.0, clamp=True)
    loh = b.math("MAXIMUM", b.vmath("DOT_PRODUCT", ldir, half), 0.0, clamp=True)
    d = b.math("ADD", b.math("MULTIPLY", b.math("MULTIPLY", noh, noh), b.math("SUBTRACT", rough2, 1.0)), 1.00001)
    d2 = b.math("MULTIPLY", d, d)
    loh2 = b.math("MAXIMUM", b.math("MULTIPLY", loh, loh), 0.1)
    norm = b.math("ADD", b.math("MULTIPLY", rough, 4.0), 2.0)
    spec_term = b.math("DIVIDE", rough2, b.math("MULTIPLY", b.math("MULTIPLY", d2, loh2), norm))
    lobe = b.math("DIVIDE", b.math("MULTIPLY", rough2, rough2), d2)
    brdf = b.math("MINIMUM", b.math("MAXIMUM", b.math("MULTIPLY", spec_term,
                  b.ramp(lobe, i["Spec Step"], i["Spec Feather"])), 0.0), 100.0)
    # _HAIRSPECULARVIEWNORMAL: a band where the normal faces the camera horizontally
    b.x, b.y = -200, 1200
    nx = b.separate_xyz(nrm)
    vx = b.separate_xyz(view)
    nh = b.vmath("NORMALIZE", b.combine_xyz(nx[0], nx[1], 0.0))
    vh = b.vmath("NORMALIZE", b.combine_xyz(vx[0], vx[1], 0.0))
    facing = b.math("MAXIMUM", b.vmath("DOT_PRODUCT", nh, vh), 0.0, clamp=True)
    power = b.math("MINIMUM", b.math("MAXIMUM", b.math("SUBTRACT", b.math("DIVIDE", 2.0,
                   b.math("ADD", rough2, 1e-4)), 2.0), 1e-4), 10000.0)
    band = b.ramp(b.math("POWER", facing, power), i["Spec Step"], i["Spec Feather"])
    spec = b.math("MULTIPLY", b.lerp(i["Spec View Normal"], brdf, band), i["Specular"])
    spec = b.math("MULTIPLY", b.math("MULTIPLY", spec, lit), b.math("MULTIPLY", mask[1], mask[1]))
    spec_rgb = b.vmath("SCALE", b.vmath("MULTIPLY", i["Base Color"], i["Spec Color"]), scale=spec)

    # rim
    b.x, b.y = 100, 1200
    fresnel = b.math("SUBTRACT", 1.0, b.math("MAXIMUM", b.vmath("DOT_PRODUCT", nrm, view), 0.0, clamp=True))
    rim = b.ramp(fresnel, i["Rim Step"], i["Rim Feather"])
    back = b.math("ADD", b.math("MULTIPLY", b.vmath("DOT_PRODUCT", b.vmath("SCALE", ldir, scale=-1.0), view), 0.5), 0.5)
    rim = b.lerp(i["Rim Blend LdotV"], rim, b.math("MULTIPLY", rim, back))
    side = b.lerp(i["Rim Flip"], lit, b.math("SUBTRACT", 1.0, lit))
    rim = b.lerp(i["Rim Blend Shadow"], rim, b.math("MULTIPLY", rim, side))
    rim_rgb = b.vmath("SCALE", i["Rim Color"], scale=rim)

    # matcap
    mc = b.vmath("MULTIPLY", i["MatCap"], i["MatCap Color"])
    mc = b.vmath("SCALE", mc, scale=b.math("MULTIPLY", mask[2], b.lerp(i["MatCap Ignore Shadow"], lit, 1.0)))

    # sum
    b.x, b.y = 400, 1200
    direct = b.vmath("ADD", b.vmath("ADD", diffuse, spec_rgb), b.vmath("ADD", rim_rgb, mc))
    direct = b.vmath("MULTIPLY", direct, light.outputs["Light Color"])
    ambient = b.vmath("SCALE", albedo, scale=light.outputs["Ambient"])
    emission = b.vmath("SCALE", albedo, scale=b.math("MULTIPLY", mask[0], i["Emission"]))
    color = b.vmath("ADD", b.vmath("ADD", direct, ambient), emission)
    alpha = b.math("MULTIPLY", i["Base Alpha"], i["Tint Alpha"], clamp=True)
    # back faces: EEVEE culls them through the material setting; Cycles has no such setting, so they are
    # made transparent here (the eyes are layered cards that only work with culling)
    alpha = b.math("MULTIPLY", alpha, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", geo.outputs["Backfacing"], i["Cull Back"])))
    emit = b.node("ShaderNodeEmission")
    tree.links.new(color, emit.inputs["Color"])
    clear = b.node("ShaderNodeBsdfTransparent")
    mix = b.node("ShaderNodeMixShader")
    tree.links.new(alpha, mix.inputs[0])
    tree.links.new(clear.outputs[0], mix.inputs[1])
    tree.links.new(emit.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], gout.inputs["Shader"])
    tree.links.new(color, gout.inputs["Color"])
    tree.links.new(alpha, gout.inputs["Alpha"])
    tree.links.new(lit, gout.inputs["Lit"])
    return tree


TOON_GROUP = make_toon_group()


def make_matcap_uv_group():
    """uv = (N_view.xy * 0.5 + 0.5 - s) / (1 - 2 s),  s = _MatCapUVScale."""
    tree, gin, gout = new_group("TSQ MatCap UV", [("NodeSocketFloat", "Scale", 0.0)],
                                [("NodeSocketVector", "UV", None)])
    b = N(tree, -900, 200)
    geo = b.node("ShaderNodeNewGeometry")
    cam = b.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="WORLD", convert_to="CAMERA")
    tree.links.new(geo.outputs["Normal"], cam.inputs[0])
    n = b.vmath("NORMALIZE", cam.outputs[0])
    xyz = b.separate_xyz(n)
    s = gin.outputs["Scale"]
    inv = b.math("DIVIDE", 1.0, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", s, 2.0)))
    # Blender camera space looks down -Z with +Y up, like Unity's view space looks down +Z: x, y are the same
    u = b.math("MULTIPLY", b.math("SUBTRACT", b.math("ADD", b.math("MULTIPLY", xyz[0], 0.5), 0.5), s), inv)
    v = b.math("MULTIPLY", b.math("SUBTRACT", b.math("ADD", b.math("MULTIPLY", xyz[1], 0.5), 0.5), s), inv)
    tree.links.new(b.combine_xyz(u, v, 0.0), gout.inputs["UV"])
    return tree


MATCAP_UV_GROUP = make_matcap_uv_group()
HEAD_BONE = next((n for n in ("Bip001 Head", "Bip001 Neck") if n in arm_data.bones), None)


def make_face_groups():
    """TSQ Face SDF UV: (UV, Bright Side) -> (UV mirrored to the lit side, K);
    TSQ Face Lit: (SDF, K, Step, Feather) -> Lit.  K = sat(F.L * 0.5 + 0.5) in the head's
    horizontal plane; the map is sampled mirrored when the light is on the other side."""
    tree, gin, gout = new_group("TSQ Face SDF UV", [("NodeSocketVector", "UV", None),
                                                    ("NodeSocketFloat", "Bright Side", 1.0)],
                                [("NodeSocketVector", "UV", None), ("NodeSocketFloat", "K", None)])
    b = N(tree, -900, 300)
    light = b.node("ShaderNodeGroup", node_tree=LIGHT_GROUP)
    ldir = light.outputs["Light Dir"]
    if HEAD_BONE:
        rest = (arm.matrix_world @ arm_data.bones[HEAD_BONE].matrix_local).to_3x3()
        inv = rest.inverted()
        euler = b.node("ShaderNodeCombineXYZ", label="head bone rotation (driver)")
        rotation_driver(tree, euler, arm, HEAD_BONE)
        forward = axis_from_rotation(b, euler.outputs[0], inv @ Vector((0.0, -1.0, 0.0)))
        left = axis_from_rotation(b, euler.outputs[0], inv @ Vector((1.0, 0.0, 0.0)))
        up = axis_from_rotation(b, euler.outputs[0], inv @ Vector((0.0, 0.0, 1.0)))
    else:
        forward, left, up = (0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)

    def vec(v):
        if isinstance(v, bpy.types.NodeSocket):
            return v
        node = b.node("ShaderNodeCombineXYZ")
        for sock, value in zip(node.inputs, v):
            sock.default_value = value
        return node.outputs[0]

    forward, left, up = vec(forward), vec(left), vec(up)
    flat = b.vmath("NORMALIZE", b.vmath("SUBTRACT", ldir, b.vmath("SCALE", up, scale=b.vmath("DOT_PRODUCT", ldir, up))))
    fdl = b.vmath("DOT_PRODUCT", forward, flat)
    sdl = b.vmath("DOT_PRODUCT", left, flat)
    k = b.math("ADD", b.math("MULTIPLY", fdl, 0.5), 0.5, clamp=True)
    # flip when the light is not on the bright side: sdl * Bright Side < 0
    flip = b.math("LESS_THAN", b.math("MULTIPLY", sdl, gin.outputs["Bright Side"]), 0.0)
    uv = b.separate_xyz(gin.outputs["UV"])
    u = b.lerp(flip, uv[0], b.math("SUBTRACT", 1.0, uv[0]))
    tree.links.new(b.combine_xyz(u, uv[1], 0.0), gout.inputs["UV"])
    tree.links.new(k, gout.inputs["K"])

    tree2, gin2, gout2 = new_group("TSQ Face Lit", [("NodeSocketFloat", "SDF", 1.0), ("NodeSocketFloat", "K", 1.0),
                                                    ("NodeSocketFloat", "Shadow Step", 0.5),
                                                    ("NodeSocketFloat", "Shadow Feather", 0.02)],
                                   [("NodeSocketFloat", "Lit", None)])
    b = N(tree2, -700, 200)
    j = gin2.outputs
    x = b.math("SUBTRACT", b.math("SUBTRACT", b.math("SUBTRACT", 1.0, j["SDF"]), j["K"]),
               b.math("SUBTRACT", b.math("MULTIPLY", j["Shadow Step"], 2.0), 1.0))
    t = b.math("ADD", b.math("DIVIDE", x, b.math("MAXIMUM", j["Shadow Feather"], 0.001)), 1.0, clamp=True)
    tree2.links.new(b.math("SUBTRACT", 1.0, t), gout2.inputs["Lit"])
    return tree, tree2


FACE_UV_GROUP, FACE_LIT_GROUP = make_face_groups()

# ---------------------------------------------------------------- materials
IMAGES = {}


def image(png, non_color=False):
    if png in IMAGES:
        return IMAGES[png]
    path = os.path.join(SRC_DIR, "textures", png)
    if not os.path.isfile(path):
        report["missing_textures"].append(png)
        IMAGES[png] = None
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    IMAGES[png] = img
    return img


def alpha_range(img):
    if img is None or img.channels < 4:
        return 1.0, 1.0
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    a = px[3::4]
    return float(a.min()), float(a.max())


def tex_node(tree, spec, prop, location, non_color=False, uv_socket=None, extension="REPEAT"):
    info = spec["textures"].get(prop)
    if not info:
        return None
    img = image(info["file"], non_color)
    if img is None:
        return None
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.label = prop
    node.name = prop
    node.location = location
    node.extension = extension
    src = uv_socket
    sx, sy = info.get("scale", [1, 1])
    ox, oy = info.get("offset", [0, 0])
    if abs(sx - 1) > 1e-4 or abs(sy - 1) > 1e-4 or abs(ox) > 1e-4 or abs(oy) > 1e-4:
        if src is None:
            uvn = tree.nodes.new("ShaderNodeUVMap")
            uvn.location = (location[0] - 420, location[1])
            src = uvn.outputs["UV"]
        mp = tree.nodes.new("ShaderNodeMapping")
        mp.location = (location[0] - 220, location[1])
        mp.inputs["Scale"].default_value = (sx, sy, 1.0)
        mp.inputs["Location"].default_value = (ox, oy, 0.0)
        tree.links.new(src, mp.inputs["Vector"])
        src = mp.outputs["Vector"]
    if src is not None:
        tree.links.new(src, node.inputs["Vector"])
    return node


def blend_mode(mat, spec, base_img):
    """Opaque unless the material really alpha-blends (SrcAlpha / OneMinusSrcAlpha) AND has alpha."""
    f = spec["floats"]
    blending = int(f.get("_SrcBlend", 1)) == 5 and int(f.get("_DstBlend", 0)) == 10
    lo, _hi = alpha_range(base_img)
    tint_a = spec["colors"].get("_BaseColor", [1, 1, 1, 1])[3]
    transparent = blending and (lo < 0.98 or tint_a < 0.98)
    if transparent:
        mat.blend_method = "HASHED" if int(f.get("_ZWrite", 1)) else "BLEND"
        mat.shadow_method = "HASHED"
    else:
        mat.blend_method = "OPAQUE"
        mat.shadow_method = "OPAQUE"
    mat.use_backface_culling = int(f.get("_Cull", 2)) == 2
    mat.show_transparent_back = False
    return transparent


def build_toon(mat, spec, sdf_side):
    tree = mat.node_tree
    f, c, kw = spec["floats"], spec["colors"], set(spec.get("keywords", []))
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    toon = tree.nodes.new("ShaderNodeGroup")
    toon.node_tree = TOON_GROUP
    toon.location = (300, 0)
    toon.width = 260
    toon.name = toon.label = "TSQ Toon"
    tree.links.new(toon.outputs["Shader"], out.inputs["Surface"])
    base = tex_node(tree, spec, "_BaseMap", (-500, 420))
    if base is not None:
        tree.links.new(base.outputs["Color"], toon.inputs["Base Color"])
        tree.links.new(base.outputs["Alpha"], toon.inputs["Base Alpha"])
    shade = tex_node(tree, spec, "_InShadowMap", (-500, 140))
    shadow_colors = "_SHADOWCOLOR" in kw
    if shade is not None and not shadow_colors:
        tree.links.new(shade.outputs["Color"], toon.inputs["Shade Color"])
    elif base is not None and not shadow_colors:        # no shade map: the white default -> shade = albedo * Shadow1
        shadow_colors = True
    mask = tex_node(tree, spec, "_MaskMap", (-500, -140), non_color=True)
    if mask is not None:
        tree.links.new(mask.outputs["Color"], toon.inputs["Mask"])
    if "_MATCAP" in kw and "_MatCapMap" in spec["textures"]:
        uvg = tree.nodes.new("ShaderNodeGroup")
        uvg.node_tree = MATCAP_UV_GROUP
        uvg.location = (-760, -420)
        uvg.inputs["Scale"].default_value = f.get("_MatCapUVScale", 0.0)
        mc = tex_node(tree, spec, "_MatCapMap", (-500, -420), uv_socket=uvg.outputs["UV"], extension="EXTEND")
        if mc is not None:
            tree.links.new(mc.outputs["Color"], toon.inputs["MatCap"])
    if "_SDFSHADOWMAP" in kw and "_SDFShadowMap" in spec["textures"]:
        uvn = tree.nodes.new("ShaderNodeUVMap")
        uvn.location = (-1240, -700)
        fuv = tree.nodes.new("ShaderNodeGroup")
        fuv.node_tree = FACE_UV_GROUP
        fuv.location = (-1020, -700)
        fuv.inputs["Bright Side"].default_value = sdf_side
        tree.links.new(uvn.outputs["UV"], fuv.inputs["UV"])
        sdf = tex_node(tree, spec, "_SDFShadowMap", (-760, -700), non_color=True, uv_socket=fuv.outputs["UV"])
        if sdf is not None:
            sdf.interpolation = "Linear"
            sep = tree.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-460, -700)
            tree.links.new(sdf.outputs["Color"], sep.inputs[0])
            fl = tree.nodes.new("ShaderNodeGroup")
            fl.node_tree = FACE_LIT_GROUP
            fl.location = (-240, -700)
            fl.inputs["Shadow Step"].default_value = f.get("_Shadow1Step", 0.5)
            fl.inputs["Shadow Feather"].default_value = f.get("_Shadow1Feather", 0.02)
            tree.links.new(sep.outputs["R"], fl.inputs["SDF"])
            tree.links.new(fuv.outputs["K"], fl.inputs["K"])
            tree.links.new(fl.outputs["Lit"], toon.inputs["Lit Override"])
            toon.inputs["Use Lit Override"].default_value = 1.0
    white = [1.0, 1.0, 1.0, 1.0]
    tint = c.get("_BaseColor", white)
    values = {
        "Base Tint": rgba(tint), "Tint Alpha": tint[3],
        "Shadow Step": f.get("_Shadow1Step", 0.5), "Shadow Feather": f.get("_Shadow1Feather", 0.05),
        "Shadow Colors": 1.0 if shadow_colors else 0.0,
        "Shadow1 Color": rgba(c.get("_Shadow1Color", [0.8, 0.8, 0.8, 1])),
        "Shadow2 Color": rgba(c.get("_Shadow2Color", [0.5, 0.5, 0.5, 1])),
        "Shadow2 Step": f.get("_Shadow2Step", 0.5), "Shadow2 Feather": f.get("_Shadow2Feather", 0.05),
        "Specular": 0.0 if "_SPECULARHIGHLIGHTS_OFF" in kw else 1.0,
        "Spec Color": rgba(c.get("_SpecColor", white)), "Smoothness": f.get("_Smoothness", 0.5),
        "Spec Step": f.get("_SpecularStep", 0.5), "Spec Feather": f.get("_SpecularFeather", 0.05),
        "Spec View Normal": 1.0 if "_HAIRSPECULARVIEWNORMAL" in kw else 0.0,
        "Rim Color": rgba(c.get("_RimColor", [0, 0, 0, 1])), "Rim Step": f.get("_RimStep", 0.5),
        "Rim Feather": f.get("_RimFeather", 0.05), "Rim Flip": f.get("_RimFlip", 0.0),
        "Rim Blend Shadow": f.get("_RimBlendShadow", 0.5), "Rim Blend LdotV": f.get("_RimBlendLdotV", 0.5),
        "MatCap Color": rgba(c.get("_MatCapColor", white)),
        "MatCap Ignore Shadow": 1.0 if "_IgnoreShadowMatCap" in kw else 0.0,
        "Emission": f.get("_EmissionColor", 0.0) if "_EMISSION" in kw else 0.0,
        "Cull Back": 1.0 if int(f.get("_Cull", 2)) == 2 else 0.0,
    }
    if not shadow_colors and shade is None:
        values["Shadow Colors"] = 1.0
    for key, value in values.items():
        toon.inputs[key].default_value = value
    transparent = blend_mode(mat, spec, base.image if base is not None else None)
    if not transparent:                                # opaque: the shader ignores the alpha
        for link in list(toon.inputs["Base Alpha"].links):
            alpha_source = link.from_socket
            tree.links.remove(link)
        toon.inputs["Tint Alpha"].default_value = 1.0
        if base is not None:                           # the alpha still scales the smoothness: keep it there
            pass
    return "toon"


def build_unlit(mat, spec):
    """Universal Render Pipeline/Unlit and effect shaders: the texture as it is, alpha-blended if asked."""
    tree = mat.node_tree
    f, c = spec["floats"], spec["colors"]
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    prop = next((p for p in ("_BaseMap", "_MainTex", "_MainTexture") if p in spec["textures"]), None)
    tint = c.get("_BaseColor", c.get("_Color", c.get("_TintColor", [1, 1, 1, 1])))
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.location = (0, 100)
    base = tex_node(tree, spec, prop, (-500, 200)) if prop else None
    if base is not None:
        mul = tree.nodes.new("ShaderNodeMixRGB")
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 1.0
        mul.inputs[2].default_value = rgba(tint)
        mul.location = (-200, 200)
        tree.links.new(base.outputs["Color"], mul.inputs[1])
        tree.links.new(mul.outputs[0], emit.inputs["Color"])
    else:
        emit.inputs["Color"].default_value = rgba(tint)
    surface = int(f.get("_Surface", f.get("_SurfaceType", 0)))
    transparent = surface == 1 or (int(f.get("_SrcBlend", 1)) == 5 and int(f.get("_DstBlend", 0)) == 10)
    if transparent:
        clear = tree.nodes.new("ShaderNodeBsdfTransparent")
        clear.location = (0, -100)
        mix = tree.nodes.new("ShaderNodeMixShader")
        mix.location = (250, 0)
        if base is not None:
            alpha = tree.nodes.new("ShaderNodeMath")
            alpha.operation = "MULTIPLY"
            alpha.location = (-200, -100)
            alpha.inputs[1].default_value = tint[3]
            tree.links.new(base.outputs["Alpha"], alpha.inputs[0])
            tree.links.new(alpha.outputs[0], mix.inputs[0])
        else:
            mix.inputs[0].default_value = tint[3]
        tree.links.new(clear.outputs[0], mix.inputs[1])
        tree.links.new(emit.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], out.inputs["Surface"])
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"
        mat.show_transparent_back = False
    else:
        tree.links.new(emit.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = int(f.get("_Cull", 2)) == 2
    return "unlit"


def build_lit(mat, spec):
    """URP Lit / anything else: a plain Principled BSDF from the usual property names."""
    tree = mat.node_tree
    f, c = spec["floats"], spec["colors"]
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    prop = next((p for p in ("_BaseMap", "_MainTex") if p in spec["textures"]), None)
    tint = c.get("_BaseColor", c.get("_Color", [1, 1, 1, 1]))
    base = tex_node(tree, spec, prop, (-500, 200)) if prop else None
    if base is not None:
        tree.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = rgba(tint)
    bsdf.inputs["Roughness"].default_value = 1.0 - f.get("_Smoothness", 0.5)
    bsdf.inputs["Metallic"].default_value = f.get("_Metallic", 0.0)
    nrm = tex_node(tree, spec, "_BumpMap", (-500, -200), non_color=True)
    if nrm is not None:
        nm = tree.nodes.new("ShaderNodeNormalMap")
        nm.location = (-200, -200)
        tree.links.new(nrm.outputs["Color"], nm.inputs["Color"])
        tree.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    return "lit"


MATS = {}
# --materials <file.py>: another game's shaders (scripts/actiontaimanin/atm_materials.py).  The module's
# builders(globals of this script) returns [(match(shader, spec), build(mat, spec))]; a build returns
# {"kind", "base_map", "outline_mm", "outline_color"} - what is kept on the material below.
EXTRA_BUILDERS = []
if arg("--materials"):
    import importlib.util

    _plugin_spec = importlib.util.spec_from_file_location("tsq_material_plugin", arg("--materials"))
    _plugin = importlib.util.module_from_spec(_plugin_spec)
    _plugin_spec.loader.exec_module(_plugin)
    EXTRA_BUILDERS = _plugin.builders(globals())


def material(key, sdf_side=1.0):
    if key is None:
        return None
    if key in MATS:
        return MATS[key]
    spec = SCENE["materials"][key]
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    for node in list(mat.node_tree.nodes):
        mat.node_tree.nodes.remove(node)
    shader = spec.get("shader", "")
    extra = next((build for match, build in EXTRA_BUILDERS if match(shader, spec)), None)
    made = extra(mat, spec) if extra is not None else {}
    if made:
        kind = made["kind"]
    elif shader.startswith("Squad/"):
        kind = build_toon(mat, spec, sdf_side)
    elif "Unlit" in shader or shader.startswith(("etoylab", "EP1Shader", "eTOYLab")):
        kind = build_unlit(mat, spec)
    else:
        kind = build_lit(mat, spec)
    mat["tsq_shader"] = shader
    mat["tsq_kind"] = kind
    mat["tsq_keywords"] = " ".join(spec.get("keywords", []))
    if made.get("base_map"):
        mat["tsq_base_map"] = made["base_map"]
    elif spec["textures"].get("_BaseMap"):
        mat["tsq_base_map"] = spec["textures"]["_BaseMap"]["file"]
    for prop in ("_MatCapMap", "_InShadowMap", "_MaskMap", "_SDFShadowMap"):
        if spec["textures"].get(prop):
            mat["tsq" + prop.lower()] = spec["textures"][prop]["file"]
    f = spec["floats"]
    outlined = (kind == "toon" and f.get("_EnableOutline", 0.0) > 0.5
                and "SRPDEFAULTUNLIT" not in spec.get("disabled_passes", []))
    mat["tsq_outline_width"] = f.get("_Outline_Width", 0.0) if outlined else 0.0
    mat["tsq_outline_color"] = spec["colors"].get("_Outline_Color", [0, 0, 0, 1])[:3]
    if "outline_mm" in made:
        mat["tsq_outline_width"] = made["outline_mm"]
        mat["tsq_outline_color"] = list(made.get("outline_color") or (0.0, 0.0, 0.0))[:3]
    # the game's own material record, so the XPS / PMX converters (and anyone curious) need no scene.json
    mat["tsq_spec"] = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    report["materials_built"][key] = kind
    MATS[key] = mat
    return mat


OUTLINES = {}


def outline_material(color):
    key = "none" if color is None else "%02x%02x%02x" % tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in color)
    if key in OUTLINES:
        return OUTLINES[key]
    mat = bpy.data.materials.new("TSQ Outline " + key)
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    clear = tree.nodes.new("ShaderNodeBsdfTransparent")
    clear.location = (0, -120)
    if color is None:
        tree.links.new(clear.outputs[0], out.inputs["Surface"])
        mat.blend_method = "CLIP"
        mat.alpha_threshold = 0.5
        mat.shadow_method = "NONE"
    else:
        emit = tree.nodes.new("ShaderNodeEmission")
        emit.location = (0, 80)
        emit.inputs["Color"].default_value = rgba(color)
        geo = tree.nodes.new("ShaderNodeNewGeometry")
        geo.location = (-250, 200)
        mix = tree.nodes.new("ShaderNodeMixShader")       # Cycles has no backface culling: hide them here
        mix.location = (200, 0)
        tree.links.new(geo.outputs["Backfacing"], mix.inputs[0])
        tree.links.new(emit.outputs[0], mix.inputs[1])
        tree.links.new(clear.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], out.inputs["Surface"])
        mat.use_backface_culling = True
        mat.shadow_method = "NONE"
    mat["tsq_kind"] = "outline"
    OUTLINES[key] = mat
    return mat


# ---------------------------------------------------------------- meshes
def weld(verts, normals, bone_idx, bone_w, shape_cols):
    """Merge the vertices Unity split at UV seams: same position, normal, skin and blend-shape
    deltas.  Hard edges and double-sided layers (different normals) stay apart; so do lips that
    touch at rest but part in a blend shape.  Returns (kept vertex ids, old -> new index)."""
    cols = [np.round(verts * 1e5).astype(np.int64)]
    if normals is not None:
        cols.append(np.round(normals * 500.0).astype(np.int64))
    skin = (bone_idx.astype(np.int64) + 1) * 100000 + np.round(bone_w * 10000.0).astype(np.int64)
    skin[bone_w <= 1e-5] = 0
    cols.append(np.sort(skin, axis=1))
    cols.extend(shape_cols)
    key = np.concatenate(cols, axis=1)
    _u, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return first[order], rank[np.asarray(inverse).ravel()]


def sdf_bright_side(part_verts, uv, mat_spec):
    """+1 when the unmirrored SDF map is brighter on the character's left (+X in Blender), -1 otherwise."""
    info = mat_spec["textures"].get("_SDFShadowMap")
    if not info or uv is None:
        return 1.0
    img = image(info["file"], True)
    if img is None:
        return 1.0
    w, h = img.size
    px = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(px)
    red = px.reshape(h, w, img.channels)[..., 0]
    x = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    value = red[y, x]
    cx = part_verts[:, 0] - np.median(part_verts[:, 0])
    left, right = value[cx > 0.005], value[cx < -0.005]
    if len(left) < 10 or len(right) < 10:
        return 1.0
    return 1.0 if left.mean() >= right.mean() else -1.0


bone_names = set(arm_data.bones.keys())
meshes = []
for part in SCENE["parts"]:
    data = np.load(os.path.join(SRC_DIR, part["npz"]))
    verts_all = conv_points(data["vertices"])
    normals_all = (data["normals"].astype(np.float64) @ C3.T) if "normals" in data else None
    idx = data["indices"]
    tri_list, slot_list = [], []
    slot_keys, slot_of = [], {}
    for si, (first, count, topo) in enumerate(part["submeshes"]):
        if topo != 0 or count < 3:
            continue
        key = part["materials"][si] if si < len(part["materials"]) else None
        if key not in slot_of:
            slot_of[key] = len(slot_keys)
            slot_keys.append(key)
        tri = idx[first:first + count].reshape(-1, 3)
        tri_list.append(tri[:, [0, 2, 1]])              # mirrored space: re-wind
        slot_list.append(np.full(len(tri), slot_of[key], dtype=np.int32))
    if not tri_list:
        report["warnings"].append("%s: no triangles" % part["name"])
        continue
    tris = np.concatenate(tri_list)
    face_slot = np.concatenate(slot_list)
    good = tris.max(axis=1) < len(verts_all)
    tris, face_slot = tris[good], face_slot[good]
    bi, bw = data["bone_indices"], data["bone_weights"]
    shape_names = part.get("shape_keys", [])
    dense = []
    for si in range(len(shape_names)):
        delta = np.zeros((len(verts_all), 3), dtype=np.float64)
        delta[data["shape%d_idx" % si]] = data["shape%d_delta" % si].astype(np.float64) @ C3.T * SCALE
        dense.append(delta)
    if NO_WELD:
        keep = np.arange(len(verts_all))
        remap = keep
    else:
        keep, remap = weld(verts_all, normals_all, bi, bw, [np.round(d * 1e5).astype(np.int64) for d in dense])
    report["welded"] += len(verts_all) - len(keep)
    new_tris = remap[tris]
    ok = (new_tris[:, 0] != new_tris[:, 1]) & (new_tris[:, 1] != new_tris[:, 2]) & (new_tris[:, 0] != new_tris[:, 2])
    tris, new_tris, face_slot = tris[ok], new_tris[ok], face_slot[ok]
    verts = verts_all[keep]

    me = bpy.data.meshes.new(part["name"])
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(len(new_tris) * 3)
    me.loops.foreach_set("vertex_index", new_tris.astype(np.int32).ravel())
    me.polygons.add(len(new_tris))
    me.polygons.foreach_set("loop_start", np.arange(0, len(new_tris) * 3, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(new_tris), 3, dtype=np.int32))
    me.polygons.foreach_set("material_index", face_slot)
    me.polygons.foreach_set("use_smooth", np.ones(len(new_tris), dtype=bool))
    corner = tris.ravel()                               # per-loop source vertex (before welding)
    uv_first = None
    for ui, uv_key in enumerate(k for k in ("uv0", "uv1", "uv2", "uv3") if k in data):
        layer = me.uv_layers.new(name="UVMap" if uv_key == "uv0" else uv_key.upper())
        layer.data.foreach_set("uv", data[uv_key][corner].astype(np.float32).ravel())
        if uv_key == "uv0":
            uv_first = data[uv_key]
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    # validate() drops the second copy of a face drawn twice (the game doubles faces, wound both ways, to
    # show both sides under back-face culling): such parts get two-sided materials below
    doubled = len(me.polygons) != len(new_tris)
    if normals_all is not None:
        # every welded vertex has ONE normal (it is part of the weld key), so per-loop = per-vertex
        loop_vertex = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", loop_vertex)
        me.use_auto_smooth = True
        me.normals_split_custom_set(normals_all[keep][loop_vertex].tolist())
    side = 1.0
    for key in slot_keys:
        spec = SCENE["materials"].get(key) if key else None
        if spec and "_SDFShadowMap" in spec["textures"] and uv_first is not None:
            side = sdf_bright_side(verts_all, uv_first, spec)
            break
    for key in slot_keys:
        mat = material(key, side)
        me.materials.append(mat)
        if doubled and mat is not None:
            mat.use_backface_culling = False
            node = mat.node_tree.nodes.get("TSQ Toon")
            if node is not None:
                node.inputs["Cull Back"].default_value = 0.0
    if doubled:
        report.setdefault("two_sided_parts", []).append(part["name"])
    obj = bpy.data.objects.new(part["name"], me)
    scene.collection.objects.link(obj)
    obj["tsq_mesh"] = part.get("mesh", "")
    obj["tsq_role"] = part.get("role", "body")
    if part.get("weapon"):                              # out of a weapon prefab the game hangs on the unit
        obj["tsq_weapon"] = part["weapon"]
    # skin
    bones = part["bones"]
    kbi, kbw = bi[keep], bw[keep]
    groups = {}
    for slot in range(kbi.shape[1]):
        for b_index in np.unique(kbi[:, slot]):
            bname = bones[b_index] if b_index < len(bones) else part.get("node", "")
            if bname not in bone_names:
                continue
            sel = np.nonzero((kbi[:, slot] == b_index) & (kbw[:, slot] > 0))[0]
            if len(sel) == 0:
                continue
            vg = groups.get(bname) or obj.vertex_groups.new(name=bname)
            groups[bname] = vg
            w = kbw[sel, slot]
            for value in np.unique(w):
                vg.add(sel[w == value].tolist(), float(value), "ADD")
    obj.parent = arm
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    # shape keys
    if shape_names:
        obj.shape_key_add(name="Basis", from_mix=False)
        base = verts.astype(np.float32)
        for si, sname in enumerate(shape_names):
            kb = obj.shape_key_add(name=sname, from_mix=False)
            kb.data.foreach_set("co", (base + dense[si][keep].astype(np.float32)).ravel())
        report["shape_keys"] += len(shape_names)
        # the expression the prefab starts with (SkinnedMeshRenderer.m_BlendShapeWeights): the model looks
        # like the game when the file opens; the converters bake it into the rest shape
        defaults = {k: float(v) for k, v in (part.get("shape_defaults") or {}).items()
                    if k in obj.data.shape_keys.key_blocks}
        if defaults:
            for kname, value in defaults.items():
                kb = obj.data.shape_keys.key_blocks[kname]
                kb.slider_max = max(kb.slider_max, value)
                kb.value = value
            obj["tsq_shape_defaults"] = json.dumps(defaults)
            report.setdefault("shape_defaults", {})[part["name"]] = defaults
    # outline: inverted hull
    widths = [float(m["tsq_outline_width"]) if m is not None else 0.0 for m in me.materials]
    if not NO_OUTLINE and max(widths, default=0.0) > 0.0:
        widest = max(widths)
        factor = np.zeros(len(verts), dtype=np.float32)
        for s, wd in enumerate(widths):
            if wd > 0.0:
                used = np.unique(new_tris[face_slot == s])
                factor[used] = np.maximum(factor[used], wd / widest)
        vg = obj.vertex_groups.new(name="tsq_outline")
        for value in np.unique(factor):
            if value > 0.0:
                vg.add(np.nonzero(factor == value)[0].tolist(), float(value), "REPLACE")
        count = len(me.materials)
        for s in range(count):
            m = me.materials[s]
            me.materials.append(outline_material(list(m["tsq_outline_color"]) if widths[s] > 0.0 else None))
        sol = obj.modifiers.new("TSQ Outline", "SOLIDIFY")
        sol.thickness = widest * 0.001                  # _Outline_Width is in millimetres at close range
        sol.offset = 1.0
        sol.use_flip_normals = True
        sol.use_rim = False
        sol.use_quality_normals = True
        sol.vertex_group = "tsq_outline"
        # the materials without an outline keep 0.1 mm of (invisible) shell: at exactly zero the shell lies
        # in the layer itself, and Cycles then loses the layer behind it (lashes, irises, brows went missing)
        sol.thickness_vertex_group = min(0.5, 0.0001 / sol.thickness)
        sol.material_offset = count
        sol.show_in_editmode = False
        obj["tsq_outline_mm"] = widest
    meshes.append(obj)
    report["parts"] += 1
    report["vertices"] += len(verts)
    report["faces"] += len(new_tris)
log("meshes: %d, %d vertices (%d welded away), %d faces, %d shape keys" % (
    report["parts"], report["vertices"], report["welded"], report["faces"], report["shape_keys"]))



def link_mouth_keys():
    """face_<n>_mouth_in (teeth, tongue) carries a "..._mouth_in" key for each face expression that opens
    the mouth: give those the face key's name and drive them from it, so one slider moves both (and the
    PMX export, which joins the meshes, gets one morph per expression)."""
    def is_mouth(obj):
        return "mouth_in" in obj.name.lower()

    suffix = "_mouth_in"
    faces = [o for o in meshes if o.data.shape_keys and not is_mouth(o)]
    for obj in faces:                                  # 122_Saya: a FACE key misnamed dissatisfied_face_mouth_in
        names = {kb.name for kb in obj.data.shape_keys.key_blocks}
        for kb in obj.data.shape_keys.key_blocks[1:]:
            if kb.name.endswith("_face" + suffix) and kb.name[:-len(suffix)] not in names:
                kb.name = kb.name[:-len(suffix)]
    owners = {}
    for obj in faces:
        for kb in obj.data.shape_keys.key_blocks[1:]:
            owners.setdefault(kb.name, obj)
    linked = 0
    for obj in meshes:
        if not obj.data.shape_keys or not is_mouth(obj):
            continue
        for kb in obj.data.shape_keys.key_blocks[1:]:
            # the spellings in the game: the face key's own name (4_Kuro), smile_face_mouth_in /
            # smile_mouth_in -> smile_face, mouth_in_talk_A -> mouth_talk_A
            options = (kb.name, kb.name.replace(suffix, ""), kb.name.replace(suffix, "_face"),
                       kb.name.replace("mouth_in_", "mouth_"))
            base = next((n for n in options if n in owners), None)
            if base is None:
                continue
            src = owners[base]
            kb.name = base
            driver = kb.driver_add("value").driver
            driver.type = "SUM"
            var = driver.variables.new()
            var.name = "face"
            var.type = "SINGLE_PROP"
            var.targets[0].id_type = "KEY"
            var.targets[0].id = src.data.shape_keys
            var.targets[0].data_path = 'key_blocks["%s"].value' % base
            linked += 1
    return linked


report["linked_mouth_keys"] = link_mouth_keys()


def move_to_collection(objs, name):
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    for o in objs:
        scene.collection.objects.unlink(o)
        coll.objects.link(o)
    return coll


# Three kinds of parts stay in the file but hidden, each in its own collection (unhide to use them):
# the weapons that are not on the body in this pose (tsquad_scene: their bone waits at the origin for an
# animation), the em_* cards (tears, sweat drop, anger mark) the game switches on with an expression,
# and the ...EffectRender overlays (the body drawn again with an additive glow shader).
weapons = [o for o in meshes if o.get("tsq_role") == "weapon_parked"]
emotes = [o for o in meshes if o.get("tsq_role") == "emote"]
effects = [o for o in meshes if o.get("tsq_role") == "effect"]
for objs, name, key in ((weapons, "Weapons (parked)", "weapons_parked"), (emotes, "Emotes (hidden)", "emotes"),
                        (effects, "Effects (hidden)", "effects")):
    if objs:
        move_to_collection(objs, name)
        for o in objs:
            o.hide_viewport = True
            o.hide_render = True
        report[key] = [o.name for o in objs]
report["weapons"] = [o.name for o in meshes if o.get("tsq_role") == "weapon"]

arm["tsq_id"] = SCENE.get("id", "")
arm["tsq_name"] = SCENE.get("name", "")
arm["tsq_prefab"] = SCENE.get("prefab", "")
arm["tsq_game"] = SCENE.get("game", "Taimanin Squad")
# skinned bones that are the body itself (a regular expression; Action Taimanin's face bones) - for the PMX
# converter, which takes every other chain of skinned bones for a garment
arm["tsq_body_bones"] = SCENE.get("body_bones", "")
# {converter role: [shape key names]} put in front of export_pmx_blender.SOURCES (shapes made from another
# game's expression clips have their own names)
arm["tsq_morph_sources"] = json.dumps(SCENE.get("morph_sources") or {}, ensure_ascii=False)
arm["tsq_cloth"] = json.dumps(SCENE.get("cloth", []), ensure_ascii=False)
arm["tsq_breast_bones"] = json.dumps(SCENE.get("breast_bones", []), ensure_ascii=False)
# bones whose skin was handed to the Biped bone they lie on (tsquad_scene.Scene.limb_aliases)
arm["tsq_limb_aliases"] = json.dumps(SCENE.get("limb_aliases") or {}, ensure_ascii=False)
report["limb_aliases"] = SCENE.get("limb_aliases") or {}
# sub-meshes without a material slot: the game does not draw them, the extraction left them out
report["undrawn_submeshes"] = SCENE.get("undrawn_submeshes") or []
arm["tsq_undrawn_submeshes"] = json.dumps(report["undrawn_submeshes"], ensure_ascii=False)
# the weapon prefabs hung on the unit (tsquad_scene.Scene.add_weapons): kind "limb" = an arm, a pair of legs
arm["tsq_weapon_prefabs"] = json.dumps(SCENE.get("weapon_prefabs") or [], ensure_ascii=False)
arm["tsq_weapon_prefabs_left_out"] = json.dumps(SCENE.get("weapon_prefabs_left_out") or [], ensure_ascii=False)


# ---------------------------------------------------------------- preview
def frame(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, mx - mn


def render(path, center, ortho, size, direction, distance=6.0):
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho
    cam_data.clip_start = 0.01
    cam_data.clip_end = distance * 10
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + direction.normalized() * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = 32
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    log("rendered " + path)


world_data = bpy.data.worlds.new("TSQ_World")
world_data.use_nodes = True
bg = next(n for n in world_data.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.42, 0.44, 0.48, 1.0)
scene.world = world_data
out_dir = os.path.dirname(os.path.abspath(OUT_PATH)) if OUT_PATH else SRC_DIR
os.makedirs(out_dir, exist_ok=True)
base_path = os.path.splitext(OUT_PATH)[0] if OUT_PATH else os.path.join(SRC_DIR, NAME)

body = [o for o in meshes if o.get("tsq_role") not in ("weapon_parked", "emote", "effect")] or meshes
if meshes:
    center, extent = frame(body)
    report["size_m"] = [round(extent.x, 3), round(extent.y, 3), round(extent.z, 3)]
    head_pos, face_ortho = None, 0.36
    faces = [o for o in meshes if o.get("tsq_role") == "face"]
    if faces:                                          # frame the face meshes: head bones sit at different heights
        fc, fe = frame(faces)
        head_pos = fc + Vector((0.0, 0.0, fe.z * 0.06))
        face_ortho = max(fe.x, fe.z) * 2.3
    elif HEAD_BONE:
        hb = arm_data.bones[HEAD_BONE]
        head_pos = arm.matrix_world @ hb.head_local + Vector((0.0, 0.0, 0.07))
    if not NO_PREVIEW:
        front = Vector((0.0, -1.0, 0.0))
        tall = extent.z >= extent.x
        size = (900, 1400) if tall else (1400, 1000)
        ortho = max(extent.z * 1.06, extent.x * 1.06 * (size[1] / size[0])) if tall else \
            max(extent.x * 1.06, extent.z * 1.06 * (size[0] / size[1]))
        render(base_path + "_preview.png", center, ortho, size, front)
        report["preview"] = base_path + "_preview.png"
        if head_pos is not None:
            render(base_path + "_face.png", head_pos, face_ortho, (900, 900), Vector((0.12, -1.0, 0.03)))
            report["face"] = base_path + "_face.png"
        if VIEWS_DIR:
            os.makedirs(VIEWS_DIR, exist_ok=True)
            for label, direction in (("front", front), ("three_quarter", Vector((0.7, -0.7, 0.1))),
                                     ("side", Vector((1.0, 0.0, 0.0))), ("back", Vector((0.0, 1.0, 0.0))),
                                     ("three_quarter_back", Vector((-0.7, 0.7, 0.15)))):
                render(os.path.join(VIEWS_DIR, "%s_%s.png" % (NAME, label)), center, ortho, size, direction)
            if head_pos is not None:
                for label, direction in (("face_front", Vector((0.0, -1.0, 0.0))), ("face_left", Vector((0.8, -0.6, 0.0))),
                                         ("face_right", Vector((-0.8, -0.6, 0.0))), ("face_up", Vector((0.0, -1.0, 0.5)))):
                    render(os.path.join(VIEWS_DIR, "%s_%s.png" % (NAME, label)), head_pos, face_ortho, (900, 900), direction)

    if not NO_PREVIEW and TILES_DIR and head_pos is not None:
        keyed = [o for o in meshes if o.data.shape_keys]
        names = []
        for o in keyed:
            for kb in o.data.shape_keys.key_blocks[1:]:
                if kb.name not in names:
                    names.append(kb.name)
        if names:
            os.makedirs(TILES_DIR, exist_ok=True)
            look = Vector((0.0, -1.0, 0.0))
            # where each key rests: 0, or the value the prefab starts with
            rest = {(o.name, kb.name): kb.value for o in keyed for kb in o.data.shape_keys.key_blocks[1:]}
            render(os.path.join(TILES_DIR, "00_neutral.png"), head_pos, face_ortho * 0.8, (360, 360), look)
            for i, key_name in enumerate(names, 1):
                for o in keyed:                         # driven twins (the mouth interior) follow by themselves
                    kb = o.data.shape_keys.key_blocks.get(key_name)
                    if kb is not None:
                        kb.value = 1.0
                render(os.path.join(TILES_DIR, "%02d_%s.png" % (i, key_name)), head_pos, face_ortho * 0.8, (360, 360), look)
                for o in keyed:
                    kb = o.data.shape_keys.key_blocks.get(key_name)
                    if kb is not None:
                        kb.value = rest.get((o.name, key_name), 0.0)
            report["shape_key_names"] = names

# ---------------------------------------------------------------- save
if OUT_PATH and not NO_SAVE:
    for img in bpy.data.images:
        if img.filepath and img.source == "FILE" and not img.packed_file:
            img.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH, compress=True)
    report["blend"] = OUT_PATH
    report["blend_bytes"] = os.path.getsize(OUT_PATH)
    log("saved " + OUT_PATH)

print("TSQ_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
