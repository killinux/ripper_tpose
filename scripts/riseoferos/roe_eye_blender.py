"""The game's eyeball shader (Rise of Eros "Pinkcore/Heros/Eye") as a Blender node network, on the eye slot of an
imported ROE model (PMX through mmd_tools, or the add-on's FBX build).

Why (2026-10-18, user: "加个按钮，可以把眼睛材质修复成游戏里一模一样的"): the PMX / XPS eye is one texture baked from a
flat sclera colour and the iris pasted 1:1 (roe_xps_addon.bake_eye_texture), so the pupil is 11 % of the iris (the
game draws it ~29 %), there is no limbal ring colour, no sclera texture / bump, no eyelid shading and no depth under
the cornea.  The game composes the eye from five textures every frame; this module does the same, following the
compiled shader as rebuilt in roe_fighter_unity/Assets/RoeFighter/Shaders/RoeEye.shader (tools/shader_asm.py there):

- in the eyeball's UV disc p = uv - 0.5: the iris where the mask's R says so; its albedo is read at
  lerp(_PupilMinSizeInv, _PupilMaxSizeInv, pupil) x _IrisLimbusScaleInv (that zoom is what makes the textures'
  tiny pupils normal size) and shifted by the cornea's parallax: height = mask G x _IrisParallax along
  view_ts.xy / (view_ts.z + 0.42);
- the limbal ring (pivot / width / fade / sizes) replaces the colour with _LimbusColor;
- the sclera: its own texture (x _ScleraSizeInv) and bump map, the bump flat over the iris;
- metallic / smoothness: sclera vs iris values; the occlusion map is WHITE where the eyelids shade the eyeball:
  x (1 - ao x lerp(_ScleraOcclusionAmt, _IrisOcclusionAmt, iris)); iris emission only when _EnableEmission.

The pupil size: the materials say 0.56 (a08) / 0.76 (g04), but the game's own showcase videos show the pupil at 0
(the game changes it at run time; roe_fighter_unity README) - default 0, the add-on has a slider.
Lighting is Blender's: Principled BSDF with the game's roughness (1 - smoothness, the same perceptual roughness),
metallic and 4 % F0; the game's reshaped "crisp disc" highlight is close to what a sun lamp with a small angle gives
at that roughness, not identical (and Unity's probes / tone mapping are not Blender's).

The network goes INTO the eye material (hq_* nodes + hq_output, as hq_materials_blender's in-place PMX materials):
the ROE 游戏材质 add-on switches it with the MMD shading and removes it like the others; a PMX re-export is unchanged.
"""
import json
import os
import re
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import hq_cache  # noqa: E402

PREFIX = "hq_"                      # = hq_materials_blender.PREFIX: shares its MMD / game switch and removal
NOT_EYE = re.compile(r"overlay|brow|lash|mask|tear|hl|highlight", re.I)


def is_eye_material(mat):
    """An eye slot: the add-on's "eye" material, mmd_tools' eye_portable, or a material whose colour image is a baked
    eye / an iris texture - not the overlay, brows, lashes, eye masks, tear films."""
    if mat is None or not mat.use_nodes:
        return False
    name = mat.name.lower()
    if NOT_EYE.search(name):
        return False
    if name == "eye" or name.startswith(("eye.", "eye_portable")) or mat.get("roe_hq_iris") or mat.get("roe_game_eye"):
        return True
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image and not node.name.startswith(PREFIX):
            img = node.image.name.lower()
            if "eye_baked" in img or re.search(r"_eyes?_iris|_eyes?__iris", img):
                return True
    return False


def pick_eye_material(materials, cid, suit=None):
    """The game's eye material for character `cid`: its own (pc_<cid>_..., a suit's own when one is named), else the
    family's pc_<x>_nk_eyes; never the low-detail battle eye (_ld_)."""
    eyes = [n for n, d in materials.items() if "_IrisAlbedoTex" in d.get("textures", {})]
    if not eyes:
        return None
    fam = cid[0]

    def score(n):
        low = n.lower()
        return ("_ld_" in low,
                not (suit and low.endswith("@" + suit)),
                ("pc_%s_" % cid) not in low,
                ("pc_%s_" % fam) not in low,
                "@" in low, len(n), n)
    return sorted(eyes, key=score)[0]


class _Net:
    """Small helper: hq_eye_* nodes in a material, linked as they are made."""

    def __init__(self, material):
        self.nt = material.node_tree
        self.count = 0

    def node(self, kind, x, y, name=None, **props):
        n = self.nt.nodes.new(kind)
        self.count += 1
        n.name = PREFIX + (name or "eye_%03d" % self.count)
        n.label = n.name
        n.location = (x, y)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def _in(self, socket, value):
        if hasattr(value, "is_output") or hasattr(value, "node"):
            self.link(value, socket)
        else:
            socket.default_value = value

    def math(self, op, a, b=0.0, c=0.0, x=0, y=0):
        n = self.node("ShaderNodeMath", x, y, operation=op)
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        if len(n.inputs) > 2:
            self._in(n.inputs[2], c)
        return n.outputs[0]

    def vec(self, op, a, b=(0.0, 0.0, 0.0), x=0, y=0, scale=None):
        n = self.node("ShaderNodeVectorMath", x, y, operation=op)
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        if scale is not None:
            self._in(n.inputs[3], scale)
        out = n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs["Vector"]
        return out

    def smooth(self, value, lo, hi, x=0, y=0):
        """RoeSmooth01(saturate((value - lo) / (hi - lo)))."""
        n = self.node("ShaderNodeMapRange", x, y, interpolation_type="SMOOTHSTEP", clamp=True)
        self._in(n.inputs["Value"], value)
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = lo, hi
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = 0.0, 1.0
        return n.outputs[0]

    def mix(self, kind, fac, a, b, x=0, y=0):
        n = self.node("ShaderNodeMix", x, y, data_type=kind, clamp_factor=True)
        self._in(n.inputs[0], fac)
        ia, ib, out = {"FLOAT": (2, 3, 0), "VECTOR": (4, 5, 1), "RGBA": (6, 7, 2)}[kind]
        self._in(n.inputs[ia], a)
        self._in(n.inputs[ib], b)
        return n.outputs[out]

    def tex(self, path, vector, noncolor=False, x=0, y=0, name=None):
        img = bpy.data.images.load(path, check_existing=True)
        if noncolor:
            img.colorspace_settings.name = "Non-Color"
        n = self.node("ShaderNodeTexImage", x, y, name=name, image=img, extension="EXTEND", interpolation="Linear")
        self.link(vector, n.inputs["Vector"])
        return n


def _linear(color):
    def one(c):
        c = max(0.0, float(c))
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(one(c) for c in color[:3])


def build(material, mdef, cache, uv_name, pupil=0.0):
    """Put the game eye network into `material` (its own nodes stay, hq_output becomes the active output)."""
    nt = material.node_tree
    for node in [n for n in nt.nodes if n.name.startswith(PREFIX)]:
        nt.nodes.remove(node)                       # an earlier run
    f, c, t = mdef.get("floats", {}), mdef.get("colors", {}), mdef["textures"]
    g = _Net(material)
    X = -2600
    uv = g.node("ShaderNodeUVMap", X, 0, uv_map=uv_name).outputs["UV"]
    p = g.vec("SUBTRACT", uv, (0.5, 0.5, 0.0), X + 200, 0)                     # p = uv - 0.5

    # limbal ring: the squared distance stretched by the fade ratio round the pivot radius
    pivot = f.get("_LimbusPivot", 0.3) * 0.5
    pivot2 = pivot * pivot
    width = f.get("_LimbusPivotWidth", 0.5) * 0.01
    fade = f.get("_LimbusFadeRatio", 1.0)
    pp2 = g.vec("DOT_PRODUCT", p, p, X + 400, 400)
    d2 = g.math("MULTIPLY_ADD", pp2, fade, pivot2 * (1.0 - fade), X + 600, 400)
    in_start = (pivot2 - 0.0001 - width) * (1.0 - f.get("_LimbusSizeIris", 1.0))
    in_end = pivot2 - width
    s_scl = f.get("_LimbusSizeSclera", 1.0)
    out_end = (pivot2 + width + 0.0001) * (1.0 - s_scl) + 0.25 * s_scl
    ring_in = g.smooth(d2, in_start, in_end, X + 800, 500)
    ring_out = g.smooth(d2, out_end, pivot2 + width, X + 800, 300)
    ring = g.math("ADD", g.math("ADD", ring_in, ring_out, x=X + 1000, y=400), -1.0, x=X + 1200, y=400)

    # the view direction in the eyeball's tangent frame: T and B from mikktspace (a constant "normal map" colour of
    # +X / +Y gives the world direction of the tangent / bitangent with the right handedness on a mirrored eye too)
    frame = {}
    for axis, colour in (("T", (1.0, 0.5, 0.5, 1.0)), ("B", (0.5, 1.0, 0.5, 1.0))):
        nm = g.node("ShaderNodeNormalMap", X + 200, -400 if axis == "T" else -600, space="TANGENT", uv_map=uv_name)
        nm.inputs["Color"].default_value = colour
        nm.inputs["Strength"].default_value = 1.0
        frame[axis] = nm.outputs["Normal"]
    geo = g.node("ShaderNodeNewGeometry", X + 200, -800)
    V, N = geo.outputs["Incoming"], geo.outputs["Normal"]
    vt = g.vec("DOT_PRODUCT", frame["T"], V, X + 400, -400)
    vb = g.vec("DOT_PRODUCT", frame["B"], V, X + 400, -600)
    vn = g.vec("DOT_PRODUCT", N, V, X + 400, -800)
    comb = g.node("ShaderNodeCombineXYZ", X + 600, -600)
    g.link(vt, comb.inputs[0])
    g.link(vb, comb.inputs[1])
    g.link(vn, comb.inputs[2])
    vts = g.vec("NORMALIZE", comb.outputs[0], x=X + 800, y=-600)
    sep = g.node("ShaderNodeSeparateXYZ", X + 1000, -600)
    g.link(vts, sep.inputs[0])
    denom = g.math("ADD", sep.outputs[2], 0.42, x=X + 1200, y=-700)
    off = g.node("ShaderNodeCombineXYZ", X + 1400, -600)
    g.link(g.math("DIVIDE", sep.outputs[0], denom, x=X + 1300, y=-500), off.inputs[0])
    g.link(g.math("DIVIDE", sep.outputs[1], denom, x=X + 1300, y=-650), off.inputs[1])
    offset = off.outputs[0]

    # the iris mask (R iris, G cornea height) and the parallax
    scale_inv = f.get("_IrisLimbusScaleInv", 1.0)
    muv = g.vec("ADD", g.vec("SCALE", p, x=X + 400, y=-1000, scale=scale_inv), (0.5, 0.5, 0.0), X + 600, -1000)
    mask = g.tex(hq_texture(cache, t["_IrisMaskTex"]["texture"]), muv, True, X + 800, -1000, "eye_mask")
    msep = g.node("ShaderNodeSeparateColor", X + 1100, -1000)
    g.link(mask.outputs["Color"], msep.inputs[0])
    iris_w, height = msep.outputs[0], g.math("MULTIPLY", msep.outputs[1], f.get("_IrisParallax", 0.03), x=X + 1300, y=-1100)
    shift = g.vec("SCALE", offset, x=X + 1600, y=-800, scale=height)
    pp = g.vec("SUBTRACT", p, shift, X + 1800, -800)
    zoom = (f.get("_PupilMinSizeInv", 1.0) + (f.get("_PupilMaxSizeInv", 0.4) - f.get("_PupilMinSizeInv", 1.0)) * pupil) \
        * scale_inv
    iuv = g.vec("SUBTRACT", g.vec("ADD", g.vec("SCALE", pp, x=X + 2000, y=-800, scale=zoom), (0.5, 0.5, 0.0),
                                  X + 2200, -800), shift, X + 2400, -800)
    iris_tex = g.tex(hq_texture(cache, t["_IrisAlbedoTex"]["texture"]), iuv, False, X + 2600, -800, "eye_iris")
    iris_col = c.get("_IrisColor", [1, 1, 1, 1])
    iris = g.mix("RGBA", float(iris_col[3]) if len(iris_col) > 3 else 1.0, iris_tex.outputs["Color"],
                 g.mix("RGBA", 1.0, iris_tex.outputs["Color"], (*_linear(iris_col), 1.0), X + 2900, -900), X + 3100, -800)
    iris.node.blend_type = "MIX"
    iris_col_node = iris.node.inputs[7].links[0].from_node
    iris_col_node.blend_type = "MULTIPLY"

    # the sclera
    suv = g.vec("ADD", g.vec("SCALE", p, x=X + 400, y=1000, scale=f.get("_ScleraSizeInv", 1.0)), (0.5, 0.5, 0.0),
                X + 600, 1000)
    scl_tex = g.tex(hq_texture(cache, t["_ScleraAlbedoTex"]["texture"]), suv, False, X + 800, 1000, "eye_sclera")
    scl_col = c.get("_ScleraColor", [1, 1, 1, 1])
    tinted = g.mix("RGBA", 1.0, scl_tex.outputs["Color"], (*_linear(scl_col), 1.0), X + 1100, 1100)
    tinted.node.blend_type = "MULTIPLY"
    sclera = g.mix("RGBA", float(scl_col[3]) if len(scl_col) > 3 else 1.0, scl_tex.outputs["Color"], tinted, X + 1300, 1000)

    albedo = g.mix("RGBA", iris_w, sclera, iris, X + 3300, 200)
    albedo = g.mix("RGBA", ring, albedo, (*_linear(c.get("_LimbusColor", [0.2, 0, 0, 1])), 1.0), X + 3500, 200)

    # eyelid shading: WHITE = shaded
    occ_tex = g.tex(hq_texture(cache, t["_EyeOcclusionMap"]["texture"]), uv, True, X + 400, 1400, "eye_occ")
    amt = g.mix("FLOAT", iris_w, f.get("_ScleraOcclusionAmt", 0.0), f.get("_IrisOcclusionAmt", 0.0), X + 1300, 1400)
    occl = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", occ_tex.outputs["Color"], amt, x=X + 1500, y=1400), x=X + 1700,
                  y=1400)
    base = g.mix("RGBA", 1.0, albedo, occl, X + 3700, 200)
    base.node.blend_type = "MULTIPLY"

    # surface: metallic / smoothness of sclera vs iris, the sclera's bump flat over the iris
    metal = g.mix("FLOAT", iris_w, f.get("_ScleraMetallic", 0.1), f.get("_IrisClearCoatMetallic", 1.0), X + 3300, -200)
    smooth = g.mix("FLOAT", iris_w, f.get("_ScleraSmoothness", 0.1), f.get("_IrisClearCoatSmoothness", 0.6), X + 3300, -400)
    rough = g.math("SUBTRACT", 1.0, smooth, x=X + 3500, y=-400)
    bump_name = t.get("_EyeBumpMap", {}).get("texture")
    normal = N
    if bump_name:
        btex = g.tex(hq_texture(cache, bump_name, normal=True), suv, True, X + 1100, 700, "eye_bump")
        nmap = g.node("ShaderNodeNormalMap", X + 1400, 700, space="TANGENT", uv_map=uv_name)
        nmap.inputs["Strength"].default_value = f.get("_BumpStrength", 1.0)
        g.link(btex.outputs["Color"], nmap.inputs["Color"])
        normal = g.vec("NORMALIZE", g.mix("VECTOR", iris_w, nmap.outputs["Normal"], N, X + 3300, -600), x=X + 3500, y=-600)
    spec = g.math("MULTIPLY", occl, 0.5, x=X + 3500, y=-800)              # 4 % F0, shaded by the eyelids too
    bsdf = g.node("ShaderNodeBsdfPrincipled", X + 3900, 0, name="eye_bsdf")
    g.link(base, bsdf.inputs["Base Color"])
    g.link(metal, bsdf.inputs["Metallic"])
    g.link(rough, bsdf.inputs["Roughness"])
    g.link(spec, bsdf.inputs["Specular"])
    g.link(normal, bsdf.inputs["Normal"])
    shader = bsdf.outputs[0]
    if f.get("_EnableEmission", 0.0) > 0.0:                                  # iris illumination (most eyes: off)
        glow = g.mix("RGBA", 1.0, iris, (*_linear(c.get("_IrisIllumColor", [0, 0, 0, 1])), 1.0), X + 3700, -1000)
        glow.node.blend_type = "MULTIPLY"
        em = g.node("ShaderNodeEmission", X + 3900, -1000)
        g.link(glow, em.inputs["Color"])
        g.link(iris_w, em.inputs["Strength"])
        add = g.node("ShaderNodeAddShader", X + 4200, -300)
        g.link(shader, add.inputs[0])
        g.link(em.outputs[0], add.inputs[1])
        shader = add.outputs[0]
    out = g.node("ShaderNodeOutputMaterial", X + 4500, 0, name="output")
    g.link(shader, out.inputs["Surface"])
    for node in nt.nodes:
        if node.type == "OUTPUT_MATERIAL":
            node.is_active_output = node.name == out.name
    material.blend_method = "OPAQUE"                # the eyeball is solid (mmd_tools' eye is HASHED)
    material.shadow_method = "OPAQUE"
    return g.count


def hq_texture(cache, name, normal=False):
    path = os.path.join(cache, "textures", name + ("__nrm.png" if normal else ".png"))
    if not os.path.isfile(path):
        raise RuntimeError("missing game texture %s" % path)
    return path


def apply(meshes, stem="", cache=None, python=None, pupil=0.0, log=print):
    """Every eye slot of `meshes` gets the game eye network.  Returns a report dict."""
    import hq_materials_blender as hq
    albedos = sorted({a for obj in meshes for slot in obj.material_slots if slot.material
                      for a in [hq.slot_albedo(slot.material)] if a})
    cid = hq.infer_cid(stem, albedos)
    if not cid:
        raise RuntimeError("cannot tell the character id (pc_<letter><digits>) from %r or the textures" % stem)
    cache = cache or hq_cache.default_cache()
    data, _ = hq.load_data(cid, cache, (), (), python, log)
    suit = re.match(r"pc_%s_(.+)$" % cid, (stem or "").lower())
    game = pick_eye_material(data["materials"], cid, suit.group(1) if suit else None)
    if game is None:
        raise RuntimeError("no game eye material for %s in %s.json" % (cid, cid))
    data, _ = hq.load_data(cid, cache, [game], (), python, log)       # its five textures into the cache
    mdef = data["materials"][game]
    done, eyes, errors = set(), [], []
    for obj in meshes:
        uv = obj.data.uv_layers.active.name if obj.data.uv_layers.active else "UVMap"
        for slot in obj.material_slots:
            mat = slot.material
            if not is_eye_material(mat) or mat.name in done:
                continue
            done.add(mat.name)
            try:
                build(mat, mdef, cache, uv, pupil)
            except Exception as exc:                                     # noqa: BLE001
                errors.append("%s: %s" % (mat.name, exc))
                continue
            mat["roe_game_eye"] = game
            mat["roe_game_material"] = game
            mat["roe_hq_role"] = "eye"
            mat["roe_hq_base"] = json.dumps({"role": "eye"})            # listed by hq_materials_of: switch / remove
            eyes.append("%s[%s]" % (obj.name, mat.name))
    return {"character": cid, "game": game, "eyes": eyes, "errors": errors, "pupil": pupil, "cache": cache}
