"""眼睛发亮有神: brighter irises, a wet cornea and catchlights on the eyes of an imported model - Rise of Eros,
Stellar Blade, Vindictus PMX (and any eye whose texture is an eyeball: sclera round an iris disc).

The effect is laid OVER whatever the eye renders with (mmd_tools' MMD shader, or a game-material add-on's network:
ROE 游戏材质 / 2.6 game eye "hq_", 剑星游戏材质 "sbhq_", Vindictus 游戏材质 "vhq_"): every material output's surface
goes through a mix with a glossy cornea and then an add of the light, so the add-ons' MMD / game switches keep the
effect.  No output node is added (the add-ons find "their" output as the first one without their prefix) and our
nodes are named mdx_eye_* (none of their prefixes), so their switch and removal leave us alone.

Per material, measured from its own eye texture (measure_iris): the iris centre, the iris and the pupil radius, by
the radial profile of brightness round the pupil.  ROE's baked eye: iris r ~0.25 on a light sclera, tiny pupil;
Stellar Blade's: iris r ~0.09 in a sclera disc on black; Vindictus' (MetaHuman): iris r ~0.18, large pupil, a
reddish rim.  Everything else is relative to those radii:
- light in the iris: emission of the texture colour (saturation x `sat`) x `glow` over the iris, plus x `caustic`
  over its lower half (light from above lights the far side of the iris through the cornea); the pupil is left out;
- catchlights: a round disc at `catch_angle` as seen on screen (default 145 deg = upper left), 36 % of the iris
  radius out, and a smaller one opposite.  The screen direction becomes a UV direction through the UV's world
  tangent / bitangent (a constant tangent-space normal map) taken to camera space and flattened onto the image
  plane, so both eyes show it on the same side, it stays there when the camera or the viewport turns, it rides with
  the iris and the eyelids cover it;
- wet cornea: a glossy BSDF (roughness 0.03) mixed in by a Fresnel of IOR 1.376 x 2 `wet` (wet 0.5 = the real
  cornea's 2.5 % at normal incidence): the scene's lights show as small sharp spots.
Shader camera space (Vector Transform): +Z looks INTO the scene in Cycles and EEVEE alike, +X right, +Y up.
"""
import json
import math
import re

import bpy

PREFIX = "mdx_eye_"
KEY = "mdx_eye"                          # material custom property: what measure_iris found (JSON)
NAME_EYE = re.compile(r"eye|iris|眼|瞳|目玉|hitomi", re.I)
NAME_NOT = re.compile(r"lash|brow|light|shadow|occlusion|overlay|tear|wet|blend|mask|highlight|cornea|shell|"
                      r"睫|眉|影|涙|ハイライト|まつ", re.I)
WHITE = (1.0, 0.98, 0.95)
# out, radius (x iris r), gain, turn.  Vindictus' upper lid covers the iris above ~0.36 r: at 125 deg / 0.45 r out /
# 0.15 r it hid half the main disc, so 145 deg / 0.36 r / 0.13 r (its top edge at 0.34 r)
CATCH = {"main": (0.36, 0.13, 1.0, 0.0), "small": (0.34, 0.065, 0.45, math.pi)}
DEFAULTS = {"glow": 0.35, "caustic": 1.2, "sat": 1.15, "catch": 6.0, "catch_size": 1.0, "catch_angle": 145.0,
            "wet": 0.5}


# --- finding the eyes -----------------------------------------------------------------------------------------
def eye_image(mat):
    """The eye's colour texture: mmd_tools' mmd_base_tex, else the first image texture that is not ours."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    nodes = mat.node_tree.nodes
    node = nodes.get("mmd_base_tex")
    if node is not None and node.type == "TEX_IMAGE" and node.image:
        return node.image
    for node in nodes:
        if node.type == "TEX_IMAGE" and node.image and not node.name.startswith(PREFIX):
            return node.image
    return None


def measure_iris(image):
    """{"c": (u, v), "r": iris radius, "rp": pupil radius, "sclera": lum, "iris": lum} in UV units, or None when the
    texture does not look like an eyeball (no darker disc on a lighter sclera round the middle)."""
    import numpy as np
    w, h = image.size
    if not w or not h:
        return None
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    step = max(1, max(w, h) // 256)
    px = px[::step, ::step]
    hh, ww = px.shape[:2]
    rgb = px[..., :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    vv, uu = np.mgrid[0:hh, 0:ww]
    u, v = (uu + 0.5) / ww, (vv + 0.5) / hh                  # image rows run up the texture like UV v

    edges = np.arange(0.0, 0.48, 0.005)

    def profile(c):
        r = np.sqrt((u - c[0]) ** 2 + (v - c[1]) ** 2)
        prof = np.array([lum[(r >= a) & (r < a + 0.005)].mean() if ((r >= a) & (r < a + 0.005)).any() else np.nan
                         for a in edges])
        if np.isnan(prof[:60]).any():
            return None
        k_sclera = int(np.nanargmax(prof[8:90])) + 8          # the brightest ring past the middle = the sclera
        k_pupil = 0
        while k_pupil < k_sclera and prof[k_pupil] < 0.12:
            k_pupil += 1
        part = prof[k_pupil:k_sclera]
        if len(part) < 2:
            return None
        iris = float(np.median(part[: max(2, len(part) // 2)]))
        sclera = float(prof[k_sclera])
        half = iris + 0.5 * (sclera - iris)
        k_iris = next((k for k in range(k_pupil + 1, k_sclera + 1) if prof[k] >= half), k_sclera)
        return r, float(edges[k_iris]), float(edges[k_pupil]), iris, sclera, half

    # 1. the pupil: near-black pixels round the middle (ROE / Stellar Blade / Vindictus pupils are black; a darker
    #    threshold, 0.12, took in ROE's shaded upper iris and moved the centre 0.06 up)
    near = (u - 0.5) ** 2 + (v - 0.5) ** 2 < 0.2 ** 2
    black = near & (lum < 0.06)
    c_pupil = (float(u[black].mean()), float(v[black].mean())) if black.sum() >= 8 else (0.5, 0.5)
    got = profile(c_pupil)
    if got is None:
        return None
    r, r_iris, r_pupil, iris, sclera, half = got
    # 2. the iris disc's own centre (ROE's pupil sits 0.011 above it): centroid of the disc's pixels
    disc = (r < r_iris) & (lum < half)
    c = (float(u[disc].mean()), float(v[disc].mean())) if disc.sum() >= 20 else c_pupil
    got = profile(c)
    if got is None:
        return None
    _r, r_iris, _rp, iris, sclera, _half = got
    if sclera - iris < 0.15 or not 0.04 <= r_iris <= 0.45 or r_pupil > 0.8 * r_iris:
        return None
    shift = math.hypot(c[0] - c_pupil[0], c[1] - c_pupil[1])
    return {"c": [round(c[0], 4), round(c[1], 4)], "r": round(r_iris, 4), "rp": round(r_pupil + shift, 4),
            "sclera": round(sclera, 3), "iris": round(iris, 3)}


def eye_materials(meshes, skipped=None):
    """[(material, uv map, measured)] of the eye slots of `meshes`, each material once.  Eye-named materials whose
    texture is not an eyeball go to `skipped` with the reason."""
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name in seen or not NAME_EYE.search(mat.name) or NAME_NOT.search(mat.name):
                continue
            seen.add(mat.name)
            image = eye_image(mat)
            found = measure_iris(image) if image is not None else None
            if found is None:
                if skipped is not None:
                    skipped.append("%s（%s）" % (mat.name, "没有贴图" if image is None else "贴图里认不出虹膜"))
                continue
            found["image"] = image.name
            uv = obj.data.uv_layers.active.name if obj.data.uv_layers.active else "UVMap"
            out.append((mat, uv, found))
    return out


def enhanced(meshes):
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.get(KEY) and mat.name not in seen:
                seen.add(mat.name)
                out.append(mat)
    return out


def stale(mat):
    """True when an output of an enhanced material does not go through our wrap (a game-material add-on rebuilt
    its network after us): pressing the button again fixes it."""
    for node in mat.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and node.inputs["Surface"].is_linked:
            if not node.inputs["Surface"].links[0].from_node.name.startswith(PREFIX):
                return True
    return False


# --- the network ----------------------------------------------------------------------------------------------
def _sock(node, *names):
    for name in names:
        if name in node.inputs:
            return node.inputs[name]
    raise KeyError("%s has none of %s" % (node.name, names))


def build(mat, uv_name, found, params=None):
    """Lay the effect over every output of `mat`.  Returns the number of outputs wrapped."""
    remove_one(mat)
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    image = bpy.data.images[found["image"]]
    cx, cy = found["c"]
    R, RP = found["r"], found["rp"]
    outs = [n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.inputs["Surface"].is_linked]
    x0 = max((n.location.x for n in nodes), default=0.0) + 400
    y0 = min((n.location.y for n in nodes), default=0.0) - 400

    def new(kind, name, x, y, **props):
        n = nodes.new(kind)
        n.name = n.label = PREFIX + name
        n.location = (x0 + x, y0 + y)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def ramp(name, value, a, b, x, y):
        n = new("ShaderNodeMapRange", name, x, y, interpolation_type="SMOOTHSTEP", clamp=True)
        links.new(value, n.inputs["Value"])
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = a, b
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = 0.0, 1.0
        return n.outputs[0]

    def math_node(name, op, a, b, x, y):
        n = new("ShaderNodeMath", name, x, y, operation=op)
        for sock, val in ((n.inputs[0], a), (n.inputs[1], b)):
            if hasattr(val, "links"):
                links.new(val, sock)
            else:
                sock.default_value = val
        return n.outputs[0]

    uv = new("ShaderNodeUVMap", "uv", 0, 0, uv_map=uv_name)
    tex = new("ShaderNodeTexImage", "tex", 200, 0, image=image, interpolation="Linear", extension="EXTEND")
    links.new(uv.outputs["UV"], tex.inputs["Vector"])
    rel = new("ShaderNodeVectorMath", "rel", 200, -300, operation="SUBTRACT")
    links.new(uv.outputs["UV"], rel.inputs[0])
    rel.inputs[1].default_value = (cx, cy, 0.0)
    dist = new("ShaderNodeVectorMath", "r", 350, -300, operation="LENGTH")
    links.new(rel.outputs["Vector"], dist.inputs[0])
    sep = new("ShaderNodeSeparateXYZ", "sep", 350, -450)
    links.new(rel.outputs["Vector"], sep.inputs[0])
    r_out = dist.outputs["Value"]

    # light in the iris
    iris = ramp("iris", r_out, 0.97 * R, 0.82 * R, 500, -300)
    p0 = max(RP, 0.08 * R)
    no_pupil = ramp("nopupil", r_out, p0, p0 + 0.15 * R, 500, -450)
    lower = ramp("lower", sep.outputs["Y"], 0.08 * R, -0.7 * R, 500, -600)
    hsv = new("ShaderNodeHueSaturation", "hsv", 500, 100)
    links.new(tex.outputs["Color"], hsv.inputs["Color"])
    glow_f = math_node("fglow", "MULTIPLY", math_node("irisin", "MULTIPLY", iris, no_pupil, 650, -350), 1.0, 800, -300)
    caus_f = math_node("fcaus", "MULTIPLY",
                       math_node("crescent", "MULTIPLY", math_node("lowerin", "MULTIPLY", lower, no_pupil, 650, -550),
                                 iris, 800, -500), 1.0, 950, -500)
    f = math_node("f", "ADD", glow_f, caus_f, 1100, -350)
    glow = new("ShaderNodeVectorMath", "glow", 1250, -200, operation="SCALE")
    links.new(hsv.outputs["Color"], glow.inputs[0])
    links.new(f, glow.inputs["Scale"])

    # catchlights
    frame = {}
    for i, (axis, colour) in enumerate((("T", (1.0, 0.5, 0.5, 1.0)), ("B", (0.5, 1.0, 0.5, 1.0)))):
        nm = new("ShaderNodeNormalMap", "frame_" + axis, 200, -900 - 250 * i, space="TANGENT", uv_map=uv_name)
        nm.inputs["Color"].default_value = colour
        nm.inputs["Strength"].default_value = 1.0
        cam = new("ShaderNodeVectorTransform", "cam_" + axis, 400, -900 - 250 * i, vector_type="VECTOR",
                  convert_from="WORLD", convert_to="CAMERA")
        links.new(nm.outputs["Normal"], cam.inputs["Vector"])
        flat = new("ShaderNodeVectorMath", "flat_" + axis, 550, -900 - 250 * i, operation="MULTIPLY")
        links.new(cam.outputs["Vector"], flat.inputs[0])
        flat.inputs[1].default_value = (1.0, 1.0, 0.0)
        unit = new("ShaderNodeVectorMath", "screen_" + axis, 700, -900 - 250 * i, operation="NORMALIZE")
        links.new(flat.outputs["Vector"], unit.inputs[0])
        frame[axis] = unit.outputs["Vector"]
    catch_sum = None
    for k, (name, (out_r, _rad, _gain, _turn)) in enumerate(CATCH.items()):
        y = -1500 - 450 * k
        spot = new("ShaderNodeCombineXYZ", "spot_" + name, 1100, y)
        for i, axis in enumerate("TB"):
            dot = new("ShaderNodeVectorMath", "dir%s_%s" % (axis, name), 900, y - 120 * i, operation="DOT_PRODUCT")
            links.new(frame[axis], dot.inputs[1])
            at = math_node("at%s_%s" % (axis, name), "MULTIPLY_ADD", dot.outputs["Value"], out_r * R, 1000, y - 120 * i)
            at.node.inputs[2].default_value = (cx, cy)[i]
            links.new(at, spot.inputs[i])
        d = new("ShaderNodeVectorMath", "d_" + name, 1250, y, operation="DISTANCE")
        links.new(uv.outputs["UV"], d.inputs[0])
        links.new(spot.outputs["Vector"], d.inputs[1])
        disc = ramp("catch_" + name, d.outputs["Value"], 0.1, 0.07, 1400, y)          # retune sets the size
        strength = math_node("cstr_" + name, "MULTIPLY", disc, 1.0, 1550, y)
        catch_sum = strength if catch_sum is None else math_node("catches", "ADD", catch_sum, strength, 1700, y)
    white = new("ShaderNodeVectorMath", "white", 1850, -1500, operation="SCALE")
    white.inputs[0].default_value = WHITE
    links.new(catch_sum, white.inputs["Scale"])
    light = new("ShaderNodeVectorMath", "light", 2000, -300, operation="ADD")
    links.new(glow.outputs["Vector"], light.inputs[0])
    links.new(white.outputs["Vector"], light.inputs[1])
    em = new("ShaderNodeEmission", "emission", 2150, -300)
    links.new(light.outputs["Vector"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0

    # wet cornea
    fres = new("ShaderNodeFresnel", "fresnel", 1850, 200)
    fres.inputs["IOR"].default_value = 1.376
    wet = math_node("wet", "MULTIPLY", fres.outputs["Fac"], 1.0, 2000, 200)
    wet.node.use_clamp = True
    gloss = new("ShaderNodeBsdfGlossy", "gloss", 2000, 400)
    gloss.inputs["Roughness"].default_value = 0.03

    # every output: (its shader mixed with the cornea) + the light
    for k, out in enumerate(outs):
        src = out.inputs["Surface"].links[0].from_socket
        mix = new("ShaderNodeMixShader", "mix_%d" % k, 2300, 300 - 250 * k)
        links.new(wet, mix.inputs[0])
        links.new(src, mix.inputs[1])
        links.new(gloss.outputs[0], mix.inputs[2])
        add = new("ShaderNodeAddShader", "add_%d" % k, 2450, 300 - 250 * k)
        links.new(mix.outputs[0], add.inputs[0])
        links.new(em.outputs[0], add.inputs[1])
        add["mdx_output"] = out.name
        links.new(add.outputs[0], out.inputs["Surface"])
    found = dict(found, outputs=[o.name for o in outs])
    mat[KEY] = json.dumps(found)
    retune(mat, params)
    return len(outs)


def retune(materials, params=None):
    """The add-on's sliders onto every enhanced material."""
    p = dict(DEFAULTS, **(params or {}))
    count = 0
    for mat in (materials if isinstance(materials, (list, tuple, set)) else [materials]):
        if mat is None or not mat.use_nodes or not mat.get(KEY):
            continue
        found = json.loads(mat[KEY])
        nodes = mat.node_tree.nodes

        def put(name, index, value):
            node = nodes.get(PREFIX + name)
            if node is not None:
                node.inputs[index].default_value = value
        put("hsv", "Saturation", p["sat"])
        put("fglow", 1, p["glow"])
        put("fcaus", 1, p["caustic"])
        put("wet", 1, 2.0 * p["wet"])
        angle = math.radians(p["catch_angle"])
        for name, (_out, rad, gain, turn) in CATCH.items():
            radius = rad * found["r"] * max(p["catch_size"], 0.05)
            put("catch_" + name, "From Min", radius)
            put("catch_" + name, "From Max", 0.7 * radius)
            put("cstr_" + name, 1, p["catch"] * gain)
            screen = (math.cos(angle + turn), math.sin(angle + turn), 0.0)
            for axis in "TB":
                put("dir%s_%s" % (axis, name), 0, screen)
        count += 1
    return count


def remove_one(mat):
    """Take our nodes out; each wrapped output gets back what fed our wrap (its own shader, as it is now)."""
    if mat is None or not mat.use_nodes:
        return False
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    ours = [n for n in nodes if n.name.startswith(PREFIX)]
    if not ours and not mat.get(KEY):
        return False
    for add in [n for n in ours if n.get("mdx_output")]:
        out = nodes.get(add["mdx_output"])
        mix = add.inputs[0].links[0].from_node if add.inputs[0].is_linked else None
        src = mix.inputs[1].links[0].from_socket if mix is not None and mix.inputs[1].is_linked else None
        if out is not None and src is not None and out.inputs["Surface"].is_linked \
                and out.inputs["Surface"].links[0].from_node.name == add.name:
            links.new(src, out.inputs["Surface"])
    for node in ours:
        nodes.remove(node)
    if KEY in mat:
        del mat[KEY]
    return True


# --- what the add-on calls ----------------------------------------------------------------------------------
def apply(meshes, params=None):
    done, errors, skipped = [], [], []
    for mat, uv, found in eye_materials(meshes, skipped):
        try:
            n = build(mat, uv, found, params)
            done.append("%s（虹膜半径 %.3f，%d 个输出）" % (mat.name, found["r"], n))
        except Exception as exc:                                      # noqa: BLE001
            errors.append("%s: %s" % (mat.name, exc))
    return {"eyes": done, "errors": errors, "skipped": skipped}


def remove(meshes):
    return sum(1 for mat in enhanced(meshes) if remove_one(mat))
