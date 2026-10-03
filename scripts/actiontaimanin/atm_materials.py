"""Blender side: Action Taimanin's materials for ../taimaninsquad/build_blend.py (--materials <this file>).

builders(api) gets build_blend.py's globals (the node helper N, new_group, tex_node, the light group ...)
and returns [(match(shader, spec), build(mat, spec))].  A build returns {"kind", "base_map",
"outline_mm", "outline_color"} - what build_blend.py keeps on the material for the format converters.

The game renders in GAMMA space: its shaders multiply and add display values.  So do the groups here -
a texture is turned into display values first (x ^ 1/2.2), material colours go in as they are, and the
result is turned back (x ^ 2.2) for Blender's linear pipeline; a texture alone comes out unchanged.

Toony Colors Pro 2, as the studio changed it ("eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline ..."),
read off the compiled program (README, "着色器"):

    albedo = MainTex x _Color
    albedo = lerp(albedo, mean(albedo) x _WhiteBalance x _PartsColorR|G|B, PartsColorMask.r|g|b)
    albedo = lerp(albedo, _RimColor.rgb, smoothstep(_RimMin, _RimMax, 1 - N.V) x _RimColor.a)
    ramp   = smoothstep(_RampThreshold -/+ _RampSmooth / 2, N.L x 0.5 + 0.5)
    high   = 1 (parts: sat(_PartsColor + 0.5));  shadow = lerp(high, _SColor.rgb, _SColor.a) (parts: x 0.4)
    colour = albedo x light x lerp(shadow, high, ramp) + Emission x _Emission_color x _Emission_power

Unity-Chan Toon Shader 2.0.8, "Mobile/Toon_ShadingGradeMap" (the public source, checked against the
compiled program): base / 1st shade / 2nd shade by two feathered steps of the shading grade, high colour,
rim light (+ the antipodean one), MatCap added or multiplied, emissive - and the studio's parts colour
applied to the FINAL colour here, not to the albedo.
"""
import bpy
import numpy as np

GAMMA = 2.2
OUTPUTS = [("NodeSocketShader", "Shader", None), ("NodeSocketColor", "Color", None),
           ("NodeSocketFloat", "Alpha", None), ("NodeSocketFloat", "Lit", None)]
WHITE, BLACK = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)
TCP2_INPUTS = [
    ("NodeSocketColor", "Base Color", WHITE), ("NodeSocketFloat", "Base Alpha", 1.0),
    ("NodeSocketColor", "Tint", WHITE), ("NodeSocketFloat", "Tint Alpha", 1.0),
    ("NodeSocketColor", "Parts Mask", BLACK), ("NodeSocketColor", "Parts R", WHITE),
    ("NodeSocketColor", "Parts G", WHITE), ("NodeSocketColor", "Parts B", WHITE),
    ("NodeSocketFloat", "White Balance", 2.0),
    ("NodeSocketColor", "Shadow Color", (0.195, 0.195, 0.195, 1.0)), ("NodeSocketFloat", "Shadow Alpha", 1.0),
    ("NodeSocketFloat", "Ramp Threshold", 0.5), ("NodeSocketFloat", "Ramp Smooth", 0.1),
    ("NodeSocketFloat", "Wrapped", 1.0),
    ("NodeSocketColor", "Rim Color", (0.8, 0.8, 0.8, 1.0)), ("NodeSocketFloat", "Rim Alpha", 0.6),
    ("NodeSocketFloat", "Rim Min", 0.5), ("NodeSocketFloat", "Rim Max", 1.0),
    ("NodeSocketColor", "Emission Tex", BLACK), ("NodeSocketColor", "Emission Tint", BLACK),
    ("NodeSocketFloat", "Cull Back", 1.0),
]
UTS2_INPUTS = [
    ("NodeSocketColor", "Base Color", WHITE), ("NodeSocketFloat", "Base Alpha", 1.0),
    ("NodeSocketColor", "Base Tint", WHITE),
    ("NodeSocketColor", "Shade1 Map", WHITE), ("NodeSocketColor", "Shade1 Color", WHITE),
    ("NodeSocketColor", "Shade2 Map", WHITE), ("NodeSocketColor", "Shade2 Color", WHITE),
    ("NodeSocketVector", "Normal", None),
    ("NodeSocketFloat", "Shading Grade", 1.0), ("NodeSocketFloat", "Shadow Level", 1.0),
    ("NodeSocketFloat", "Step1", 0.5), ("NodeSocketFloat", "Feather1", 0.0001),
    ("NodeSocketFloat", "Step2", 0.0), ("NodeSocketFloat", "Feather2", 0.0001),
    ("NodeSocketColor", "HC Tex", WHITE), ("NodeSocketColor", "HC Color", BLACK),
    ("NodeSocketFloat", "HC Power", 0.0), ("NodeSocketFloat", "HC Specular", 0.0),
    ("NodeSocketFloat", "HC Add", 0.0), ("NodeSocketFloat", "HC Mask", 1.0), ("NodeSocketFloat", "HC Shadow", 1.0),
    ("NodeSocketFloat", "Rim", 0.0), ("NodeSocketColor", "Rim Color", WHITE),
    ("NodeSocketFloat", "Rim Power", 0.1), ("NodeSocketFloat", "Rim Inside", 0.0001),
    ("NodeSocketFloat", "Rim Feather Off", 0.0), ("NodeSocketFloat", "Rim Light Mask", 0.0),
    ("NodeSocketFloat", "Rim Light Level", 0.0), ("NodeSocketFloat", "Ap Rim", 0.0),
    ("NodeSocketColor", "Ap Rim Color", WHITE), ("NodeSocketFloat", "Ap Rim Power", 0.1),
    ("NodeSocketFloat", "Ap Feather Off", 0.0), ("NodeSocketFloat", "Rim Mask", 1.0),
    ("NodeSocketFloat", "MatCap", 0.0), ("NodeSocketColor", "MatCap Tex", BLACK),
    ("NodeSocketColor", "MatCap Tint", WHITE), ("NodeSocketFloat", "MatCap Add", 1.0),
    ("NodeSocketFloat", "MatCap Mask", 1.0), ("NodeSocketFloat", "MatCap Shadow", 1.0),
    ("NodeSocketColor", "Emissive Tex", BLACK), ("NodeSocketFloat", "Emissive Alpha", 1.0),
    ("NodeSocketColor", "Emissive Tint", BLACK),
    ("NodeSocketColor", "Parts Mask", BLACK), ("NodeSocketColor", "Parts R", WHITE),
    ("NodeSocketColor", "Parts G", WHITE), ("NodeSocketColor", "Parts B", WHITE),
    ("NodeSocketFloat", "White Balance", 2.0),
    ("NodeSocketFloat", "Cull Back", 1.0),
]


def display(c, alpha=1.0):
    """A material colour as the gamma-space shader uses it: the stored numbers."""
    return (float(c[0]), float(c[1]), float(c[2]), alpha)


def builders(api):
    N, new_group, tex_node, image = api["N"], api["new_group"], api["tex_node"], api["image"]
    light_group, matcap_uv = api["LIGHT_GROUP"], api["MATCAP_UV_GROUP"]
    alpha_range = api["alpha_range"]
    groups = {}

    def gamma(b, color, power):
        node = b.node("ShaderNodeGamma")
        b.put(node.inputs["Color"], color)
        node.inputs["Gamma"].default_value = power
        return node.outputs["Color"]

    def smooth(b, value, lo, hi):
        node = b.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        b.put(node.inputs["Value"], value)
        b.put(node.inputs["From Min"], lo)
        b.put(node.inputs["From Max"], hi)
        return node.outputs["Result"]

    def clamp01(b, color):
        return b.vmath("MINIMUM", b.vmath("MAXIMUM", color, (0.0, 0.0, 0.0)), (1.0, 1.0, 1.0))

    def recolour(b, color, mask, parts, balance):
        """lerp(color, mean(color) x White Balance x Parts Colour, mask) for R, G, B in turn."""
        s = b.separate_xyz(color)
        grey = b.math("MULTIPLY", b.math("MULTIPLY", b.math("ADD", b.math("ADD", s[0], s[1]), s[2]), 1.0 / 3.0), balance)
        for channel, part in zip(mask, parts):
            color = b.mix(channel, color, b.vmath("SCALE", part, scale=grey))
        return color

    def finish(tree, b, gout, geo, color, alpha, cull, lit):
        out = gamma(b, color, GAMMA)
        # back faces: EEVEE culls them through the material setting, Cycles through this
        alpha = b.math("MULTIPLY", alpha, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", geo.outputs["Backfacing"], cull)))
        emit = b.node("ShaderNodeEmission")
        tree.links.new(out, emit.inputs["Color"])
        clear = b.node("ShaderNodeBsdfTransparent")
        mix = b.node("ShaderNodeMixShader")
        tree.links.new(alpha, mix.inputs[0])
        tree.links.new(clear.outputs[0], mix.inputs[1])
        tree.links.new(emit.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], gout.inputs["Shader"])
        tree.links.new(out, gout.inputs["Color"])
        tree.links.new(alpha, gout.inputs["Alpha"])
        tree.links.new(lit, gout.inputs["Lit"])

    def tcp2_group():
        if "tcp2" in groups:
            return groups["tcp2"]
        tree, gin, gout = new_group("ATM TCP2", TCP2_INPUTS, OUTPUTS)
        i = gin.outputs
        b = N(tree, -1100, 1200)
        light = b.node("ShaderNodeGroup", node_tree=light_group, label="light")
        geo = b.node("ShaderNodeNewGeometry")
        nrm = b.vmath("NORMALIZE", geo.outputs["Normal"])
        view = b.vmath("NORMALIZE", geo.outputs["Incoming"])
        ldir = light.outputs["Light Dir"]
        mask = b.separate(i["Parts Mask"])
        parts = (i["Parts R"], i["Parts G"], i["Parts B"])
        base = b.vmath("MULTIPLY", gamma(b, i["Base Color"], 1.0 / GAMMA), i["Tint"])
        base = recolour(b, base, mask, parts, i["White Balance"])
        facing = b.math("MAXIMUM", b.vmath("DOT_PRODUCT", nrm, view), 0.0, clamp=True)
        rim = b.math("MULTIPLY", smooth(b, b.math("SUBTRACT", 1.0, facing), i["Rim Min"], i["Rim Max"]), i["Rim Alpha"])
        base = b.mix(rim, base, i["Rim Color"])
        b.x, b.y = -500, 1200
        ndl = b.vmath("DOT_PRODUCT", nrm, ldir)
        wrapped = b.math("MAXIMUM", b.math("ADD", b.math("MULTIPLY", ndl, 0.5), 0.5), 0.0)
        x = b.lerp(i["Wrapped"], b.math("MAXIMUM", ndl, 0.0), wrapped)
        half = b.math("MULTIPLY", i["Ramp Smooth"], 0.5)
        ramp = smooth(b, x, b.math("SUBTRACT", i["Ramp Threshold"], half), b.math("ADD", i["Ramp Threshold"], half))
        high, shadow, shadow_a = WHITE, i["Shadow Color"], i["Shadow Alpha"]
        for channel, part in zip(mask, parts):
            high = b.mix(channel, high, clamp01(b, b.vmath("ADD", part, (0.5, 0.5, 0.5))))
            shadow = b.mix(channel, shadow, b.vmath("SCALE", part, scale=0.4))
            shadow_a = b.lerp(channel, shadow_a, 0.4)
        b.x, b.y = 100, 1200
        shade = b.mix(shadow_a, high, shadow)
        lit = b.mix(ramp, shade, high)
        color = b.vmath("MULTIPLY", b.vmath("MULTIPLY", base, light.outputs["Light Color"]), lit)
        color = b.vmath("ADD", color, b.vmath("MULTIPLY", gamma(b, i["Emission Tex"], 1.0 / GAMMA), i["Emission Tint"]))
        alpha = b.math("MULTIPLY", i["Base Alpha"], i["Tint Alpha"], clamp=True)
        finish(tree, b, gout, geo, color, alpha, i["Cull Back"], ramp)
        groups["tcp2"] = tree
        return tree

    def uts2_group():
        if "uts2" in groups:
            return groups["uts2"]
        tree, gin, gout = new_group("ATM UTS2", UTS2_INPUTS, OUTPUTS)
        i = gin.outputs
        b = N(tree, -1100, 1400)
        light = b.node("ShaderNodeGroup", node_tree=light_group, label="light")
        geo = b.node("ShaderNodeNewGeometry")
        flat = b.vmath("NORMALIZE", geo.outputs["Normal"])
        nrm = b.vmath("NORMALIZE", i["Normal"])
        view = b.vmath("NORMALIZE", geo.outputs["Incoming"])
        ldir = light.outputs["Light Dir"]
        lcol = light.outputs["Light Color"]
        # three basic colours
        main = gamma(b, i["Base Color"], 1.0 / GAMMA)
        base = b.vmath("MULTIPLY", b.vmath("MULTIPLY", main, i["Base Tint"]), lcol)
        first = b.vmath("MULTIPLY", b.vmath("MULTIPLY", gamma(b, i["Shade1 Map"], 1.0 / GAMMA), i["Shade1 Color"]), lcol)
        second = b.vmath("MULTIPLY", b.vmath("MULTIPLY", gamma(b, i["Shade2 Map"], 1.0 / GAMMA), i["Shade2 Color"]), lcol)
        half_lambert = b.math("ADD", b.math("MULTIPLY", b.vmath("DOT_PRODUCT", nrm, ldir), 0.5), 0.5)
        grade = b.math("MULTIPLY", b.math("MULTIPLY", i["Shading Grade"], half_lambert), i["Shadow Level"])

        def shade_mask(step, feather):                 # 1 in the shade: sat(1 - (grade - (step - feather)) / feather)
            edge = b.math("SUBTRACT", step, feather)
            return b.math("SUBTRACT", 1.0, b.math("DIVIDE", b.math("SUBTRACT", grade, edge),
                                                  b.math("MAXIMUM", feather, 1e-4)), clamp=True)

        mask1 = shade_mask(i["Step1"], i["Feather1"])
        mask2 = shade_mask(i["Step2"], i["Feather2"])
        final = b.mix(mask1, base, b.mix(mask2, first, second))
        # high colour
        b.x, b.y = -500, 1400
        half = b.vmath("NORMALIZE", b.vmath("ADD", view, ldir))
        spec = b.math("ADD", b.math("MULTIPLY", b.vmath("DOT_PRODUCT", half, nrm), 0.5), 0.5)
        hard = b.math("GREATER_THAN", spec, b.math("SUBTRACT", 1.0, b.math("POWER", i["HC Power"], 5.0)))
        soft = b.math("POWER", b.math("MAXIMUM", spec, 0.0),
                      b.math("POWER", 2.0, b.math("SUBTRACT", 11.0, b.math("MULTIPLY", i["HC Power"], 10.0))))
        tweak = b.math("MULTIPLY", i["HC Mask"], b.lerp(i["HC Specular"], hard, soft))
        high = b.vmath("SCALE", b.vmath("MULTIPLY", b.vmath("MULTIPLY", gamma(b, i["HC Tex"], 1.0 / GAMMA), i["HC Color"]), lcol),
                       scale=tweak)
        keep = b.lerp(i["HC Specular"], i["HC Add"], 1.0)
        cut = clamp01(b, b.vmath("SUBTRACT", final, b.combine_xyz(tweak, tweak, tweak)))
        on_shadow = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", mask1, b.math("SUBTRACT", 1.0, i["HC Shadow"])))
        set_high = b.vmath("ADD", b.mix(keep, cut, final), b.vmath("SCALE", high, scale=on_shadow))
        # rim light
        b.x, b.y = -200, 1400
        area = b.math("MAXIMUM", b.math("SUBTRACT", 1.0, b.vmath("DOT_PRODUCT", nrm, view)), 0.0)
        inside = i["Rim Inside"]
        span = b.math("MAXIMUM", b.math("SUBTRACT", 1.0, inside), 1e-4)

        def rim_shape(power, feather_off):
            p = b.math("POWER", area, b.math("POWER", 2.0, b.math("MULTIPLY", b.math("SUBTRACT", 1.0, power), 3.0)))
            soft_edge = b.math("DIVIDE", b.math("SUBTRACT", p, inside), span)
            return b.lerp(feather_off, soft_edge, b.math("GREATER_THAN", p, inside))

        vert_hl = b.math("ADD", b.math("MULTIPLY", b.vmath("DOT_PRODUCT", flat, ldir), 0.5), 0.5)
        rim_in = b.math("MAXIMUM", b.math("MINIMUM", rim_shape(i["Rim Power"], i["Rim Feather Off"]), 1.0), 0.0)
        masked = b.math("SUBTRACT", rim_in, b.math("ADD", b.math("SUBTRACT", 1.0, vert_hl), i["Rim Light Level"]), clamp=True)
        rim = b.vmath("SCALE", b.vmath("MULTIPLY", i["Rim Color"], lcol), scale=b.lerp(i["Rim Light Mask"], rim_in, masked))
        ap = b.math("SUBTRACT", rim_shape(i["Ap Rim Power"], i["Ap Feather Off"]),
                    b.math("ADD", b.math("MINIMUM", b.math("MAXIMUM", vert_hl, 0.0), 1.0), i["Rim Light Level"]), clamp=True)
        ap_rim = b.vmath("SCALE", b.vmath("MULTIPLY", i["Ap Rim Color"], lcol), scale=b.math("MULTIPLY", ap, i["Ap Rim"]))
        rim_total = b.vmath("SCALE", b.vmath("ADD", rim, ap_rim), scale=b.math("MULTIPLY", i["Rim Mask"], i["Rim"]))
        rim_var = b.vmath("ADD", set_high, rim_total)
        # matcap
        b.x, b.y = 100, 1400
        mc = b.vmath("MULTIPLY", b.vmath("MULTIPLY", gamma(b, i["MatCap Tex"], 1.0 / GAMMA), i["MatCap Tint"]), lcol)
        dim = b.math("MULTIPLY", mask1, b.math("SUBTRACT", 1.0, i["MatCap Shadow"]))      # mask1 x (1 - Tweak)
        shown = b.math("SUBTRACT", 1.0, dim)
        set_mc = b.vmath("ADD", b.vmath("SCALE", mc, scale=shown),
                         b.vmath("SCALE", set_high, scale=b.math("MULTIPLY", dim, b.math("SUBTRACT", 1.0, i["MatCap Add"]))))
        add_mode = b.vmath("ADD", rim_var, b.vmath("SCALE", set_mc, scale=i["MatCap Mask"]))
        mm = b.math("MULTIPLY", i["MatCap Mask"], shown)
        mul_mode = b.vmath("ADD", b.vmath("ADD", b.vmath("SCALE", set_high, scale=b.math("SUBTRACT", 1.0, mm)),
                                          b.vmath("SCALE", b.vmath("MULTIPLY", set_high, set_mc), scale=mm)), rim_total)
        with_mc = b.mix(i["MatCap Add"], mul_mode, add_mode)
        color = clamp01(b, b.mix(i["MatCap"], rim_var, with_mc))
        # emissive, then the parts colour on the finished colour
        b.x, b.y = 400, 1400
        emissive = b.vmath("SCALE", b.vmath("MULTIPLY", gamma(b, i["Emissive Tex"], 1.0 / GAMMA), i["Emissive Tint"]),
                           scale=i["Emissive Alpha"])
        color = b.vmath("ADD", color, emissive)
        color = recolour(b, color, b.separate(i["Parts Mask"]), (i["Parts R"], i["Parts G"], i["Parts B"]),
                         i["White Balance"])
        finish(tree, b, gout, geo, color, i["Base Alpha"], i["Cull Back"], b.math("SUBTRACT", 1.0, mask1))
        groups["uts2"] = tree
        return tree

    # ------------------------------------------------------------ per material
    def group_node(mat, tree_group, label):
        tree = mat.node_tree
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        out.location = (700, 0)
        node = tree.nodes.new("ShaderNodeGroup")
        node.node_tree = tree_group
        node.location = (300, 0)
        node.width = 260
        node.name = "TSQ Toon"                         # the name build_blend.py looks up to switch culling off
        node.label = label
        tree.links.new(node.outputs["Shader"], out.inputs["Surface"])
        return tree, node

    def link_parts(tree, spec, node, y):
        f, c = spec["floats"], spec["colors"]
        mask = tex_node(tree, spec, "_PartsColorMask", (-500, y), non_color=True)
        if mask is not None:
            tree.links.new(mask.outputs["Color"], node.inputs["Parts Mask"])
        for key in "RGB":
            node.inputs["Parts " + key].default_value = display(c.get("_PartsColor" + key, WHITE))
        node.inputs["White Balance"].default_value = f.get("_WhiteBalance", 2.0)

    def mean_colour(png):
        img = image(png)
        if img is None or not img.size[0]:
            return np.ones(3)
        px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(px)                     # an 8-bit sRGB picture: display values
        px = px.reshape(-1, 4)
        solid = px[px[:, 3] > 0.5]
        return (solid if len(solid) else px)[:, :3].mean(axis=0)

    def made(spec, kind="toon"):
        hints = spec.get("hints") or {}
        outline = hints.get("outline") or {}
        color = list(outline.get("color") or (0.0, 0.0, 0.0))
        if outline.get("blend_base") and hints.get("base_map"):     # uts2: outline x (base colour)^2
            base = mean_colour(hints["base_map"]) * np.array(spec["colors"].get("_BaseColor", WHITE)[:3])
            color = [float(c * b * b) for c, b in zip(color, base)]
        return {"kind": kind, "base_map": hints.get("base_map"),
                "outline_mm": float(outline.get("width_mm", 0.0)) * float(outline.get("alpha", 1.0) > 0.05),
                "outline_color": color}

    def build_tcp2(mat, spec):
        f, c, shader = spec["floats"], spec["colors"], spec["shader"]
        tree, node = group_node(mat, tcp2_group(), "ATM TCP2")
        base = tex_node(tree, spec, "_MainTex", (-500, 420))
        tint = c.get("_Color", WHITE)
        blended = shader.endswith(" Blend")
        cutoff = f.get("_Cutoff", 0.0)
        lo, _hi = alpha_range(base.image) if base is not None else (1.0, 1.0)
        if base is not None:
            tree.links.new(base.outputs["Color"], node.inputs["Base Color"])
            if (blended or cutoff > 0.0) and lo < 0.98:
                tree.links.new(base.outputs["Alpha"], node.inputs["Base Alpha"])
        link_parts(tree, spec, node, 140)
        emission = tex_node(tree, spec, "_Emission", (-500, -140))
        power = f.get("_Emission_power", 0.0)
        if emission is not None and power > 0.0:
            tree.links.new(emission.outputs["Color"], node.inputs["Emission Tex"])
            e = c.get("_Emission_color", WHITE)
            node.inputs["Emission Tint"].default_value = (e[0] * power, e[1] * power, e[2] * power, 1.0)
        shadow, rim = c.get("_SColor", (0.195, 0.195, 0.195, 1.0)), c.get("_RimColor", (0.8, 0.8, 0.8, 0.6))
        rim_min = f.get("_RimMin", 0.5)
        values = {
            "Tint": display(tint), "Tint Alpha": tint[3] if blended else 1.0,
            "Shadow Color": display(shadow), "Shadow Alpha": shadow[3],
            "Ramp Threshold": f.get("_RampThreshold", 0.5), "Ramp Smooth": max(f.get("_RampSmooth", 0.1), 1e-3),
            "Wrapped": 0.0 if "TCP2_DISABLE_WRAPPED_LIGHT" in spec.get("keywords", []) else 1.0,
            "Rim Color": display(rim), "Rim Alpha": rim[3] if "Rim" in shader.rsplit("/", 1)[-1] else 0.0,
            "Rim Min": rim_min, "Rim Max": max(f.get("_RimMax", 1.0), rim_min + 1e-3),
            "Cull Back": 1.0 if int(f.get("_Cull", 2)) == 2 else 0.0,
        }
        for key, value in values.items():
            node.inputs[key].default_value = value
        mat.use_backface_culling = int(f.get("_Cull", 2)) == 2
        mat.show_transparent_back = False
        if blended and (lo < 0.98 or tint[3] < 0.98):
            mat.blend_method, mat.shadow_method = "BLEND", "HASHED"
        elif cutoff > 0.0 and lo < 0.98:
            mat.blend_method, mat.shadow_method, mat.alpha_threshold = "CLIP", "CLIP", min(max(cutoff, 0.01), 0.99)
        else:
            mat.blend_method, mat.shadow_method = "OPAQUE", "OPAQUE"
        return made(spec)

    def build_uts2(mat, spec):
        f, c, shader = spec["floats"], spec["colors"], spec["shader"]
        tree, node = group_node(mat, uts2_group(), "ATM UTS2")

        def on(key, default=0.0):
            return 1.0 if f.get(key, default) >= 0.5 else 0.0

        base = tex_node(tree, spec, "_MainTex", (-500, 700))
        shade1 = base if on("_Use_BaseAs1st") else (tex_node(tree, spec, "_1st_ShadeMap", (-500, 420)) or base)
        shade2 = shade1 if on("_Use_1stAs2nd") else (tex_node(tree, spec, "_2nd_ShadeMap", (-800, 420)) or shade1)
        for source, socket in ((base, "Base Color"), (shade1, "Shade1 Map"), (shade2, "Shade2 Map")):
            if source is not None:
                tree.links.new(source.outputs["Color"], node.inputs[socket])
        normal = tex_node(tree, spec, "_NormalMap", (-800, 140), non_color=True) if on("_Is_NormalMapToBase") else None
        if normal is not None:
            nm = tree.nodes.new("ShaderNodeNormalMap")
            nm.location = (-500, 140)
            nm.inputs["Strength"].default_value = f.get("_BumpScale", 1.0)
            tree.links.new(normal.outputs["Color"], nm.inputs["Color"])
            tree.links.new(nm.outputs["Normal"], node.inputs["Normal"])
        else:
            geo = tree.nodes.new("ShaderNodeNewGeometry")
            geo.location = (-500, 140)
            tree.links.new(geo.outputs["Normal"], node.inputs["Normal"])

        def masked(prop, level, socket, y, inverse=False):
            """sat(mask.g + level) into a socket; without the texture the mask is white."""
            tex = tex_node(tree, spec, prop, (-800, y), non_color=True)
            if tex is None:
                node.inputs[socket].default_value = min(max(1.0 + level, 0.0), 1.0)
                return
            sep = tree.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-500, y)
            tree.links.new(tex.outputs["Color"], sep.inputs[0])
            add = tree.nodes.new("ShaderNodeMath")
            add.operation, add.use_clamp, add.location = "ADD", True, (-300, y)
            add.inputs[1].default_value = level
            source = sep.outputs["G"]
            if inverse:
                inv = tree.nodes.new("ShaderNodeMath")
                inv.operation, inv.location = "SUBTRACT", (-400, y - 60)
                inv.inputs[0].default_value = 1.0
                tree.links.new(source, inv.inputs[1])
                source = inv.outputs[0]
            tree.links.new(source, add.inputs[0])
            tree.links.new(add.outputs[0], node.inputs[socket])

        grade = tex_node(tree, spec, "_ShadingGradeMap", (-800, -140), non_color=True)
        if grade is not None:                          # r < 0.95 ? r + level : 1
            sep = tree.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-500, -140)
            tree.links.new(grade.outputs["Color"], sep.inputs[0])
            b = N(tree, -300, -140)
            shifted = b.math("ADD", sep.outputs["R"], f.get("_Tweak_ShadingGradeMapLevel", 0.0), clamp=True)
            low = b.math("LESS_THAN", sep.outputs["R"], 0.95)
            tree.links.new(b.lerp(low, 1.0, shifted), node.inputs["Shading Grade"])
        high_tex = tex_node(tree, spec, "_HighColor_Tex", (-500, -420))
        if high_tex is not None:
            tree.links.new(high_tex.outputs["Color"], node.inputs["HC Tex"])
        masked("_Set_HighColorMask", f.get("_Tweak_HighColorMaskLevel", 0.0), "HC Mask", -700)
        masked("_Set_RimLightMask", f.get("_Tweak_RimLightMaskLevel", 0.0), "Rim Mask", -980)
        use_matcap = on("_MatCap") and "_MatCap_Sampler" in spec["textures"]
        if use_matcap:
            uvg = tree.nodes.new("ShaderNodeGroup")
            uvg.node_tree = matcap_uv
            uvg.location = (-760, -1260)
            uvg.inputs["Scale"].default_value = f.get("_Tweak_MatCapUV", 0.0)
            mc = tex_node(tree, spec, "_MatCap_Sampler", (-500, -1260), uv_socket=uvg.outputs["UV"], extension="EXTEND")
            if mc is not None:
                tree.links.new(mc.outputs["Color"], node.inputs["MatCap Tex"])
            masked("_Set_MatcapMask", f.get("_Tweak_MatcapMaskLevel", 0.0), "MatCap Mask", -1540,
                   inverse=bool(on("_Inverse_MatcapMask")))
        emissive = tex_node(tree, spec, "_Emissive_Tex", (-500, -1820))
        e = c.get("_Emissive_Color", BLACK)
        if emissive is not None and max(e[:3]) > 0.0:
            tree.links.new(emissive.outputs["Color"], node.inputs["Emissive Tex"])
            tree.links.new(emissive.outputs["Alpha"], node.inputs["Emissive Alpha"])
            node.inputs["Emissive Tint"].default_value = display(e)
        link_parts(tree, spec, node, -2100)
        step1, step2 = f.get("_1st_ShadeColor_Step", 0.5), f.get("_2nd_ShadeColor_Step", 0.0)
        values = {
            "Base Tint": display(c.get("_BaseColor", WHITE)),
            "Shade1 Color": display(c.get("_1st_ShadeColor", WHITE)),
            "Shade2 Color": display(c.get("_2nd_ShadeColor", WHITE)),
            "Shadow Level": min(max(1.0 + f.get("_Tweak_SystemShadowsLevel", 0.0), 1e-4), 1.0)
            if on("_Set_SystemShadowsToBase", 1.0) else 1.0,
            "Step1": step1, "Feather1": f.get("_1st_ShadeColor_Feather", 0.0001),
            "Step2": step2, "Feather2": f.get("_2nd_ShadeColor_Feather", 0.0001),
            "HC Color": display(c.get("_HighColor", BLACK)), "HC Power": f.get("_HighColor_Power", 0.0),
            "HC Specular": on("_Is_SpecularToHighColor"), "HC Add": on("_Is_BlendAddToHiColor"),
            "HC Shadow": f.get("_TweakHighColorOnShadow", 0.0) if on("_Is_UseTweakHighColorOnShadow") else 1.0,
            "Rim": on("_RimLight"), "Rim Color": display(c.get("_RimLightColor", WHITE)),
            "Rim Power": f.get("_RimLight_Power", 0.1), "Rim Inside": f.get("_RimLight_InsideMask", 0.0001),
            "Rim Feather Off": on("_RimLight_FeatherOff"), "Rim Light Mask": on("_LightDirection_MaskOn"),
            "Rim Light Level": f.get("_Tweak_LightDirection_MaskLevel", 0.0),
            "Ap Rim": on("_Add_Antipodean_RimLight"), "Ap Rim Color": display(c.get("_Ap_RimLightColor", WHITE)),
            "Ap Rim Power": f.get("_Ap_RimLight_Power", 0.1), "Ap Feather Off": on("_Ap_RimLight_FeatherOff"),
            "MatCap": 1.0 if use_matcap else 0.0, "MatCap Tint": display(c.get("_MatCapColor", WHITE)),
            "MatCap Add": on("_Is_BlendAddToMatCap", 1.0),
            "MatCap Shadow": f.get("_TweakMatCapOnShadow", 0.0) if on("_Is_UseTweakMatCapOnShadow") else 1.0,
            "Cull Back": 1.0 if int(f.get("_CullMode", 2)) == 2 else 0.0,
        }
        for key, value in values.items():
            node.inputs[key].default_value = value
        mat.use_backface_culling = int(f.get("_CullMode", 2)) == 2
        mat.show_transparent_back = False
        lo, _hi = alpha_range(base.image) if base is not None else (1.0, 1.0)
        tail = shader.rsplit("/", 1)[-1]
        if "Clipping" in tail and base is not None and lo < 0.98 and on("_IsBaseMapAlphaAsClippingMask"):
            tree.links.new(base.outputs["Alpha"], node.inputs["Base Alpha"])
            if "TransClipping" in tail:                # the alpha is shown, not only cut
                mat.blend_method, mat.shadow_method = "HASHED", "HASHED"
            else:
                mat.blend_method, mat.shadow_method = "CLIP", "CLIP"
                mat.alpha_threshold = min(max(0.5 - f.get("_Clipping_Level", 0.0), 0.01), 0.99)
        else:
            mat.blend_method, mat.shadow_method = "OPAQUE", "OPAQUE"
        return made(spec)

    def build_flat(mat, spec, blend):
        """Eyes (Shader Forge/eye_unlit_mask_togray) and particle cards: the picture as it is."""
        tree = mat.node_tree
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        out.location = (500, 0)
        prop = next((p for p in ("_diffuse_map", "_MainTex", "_Main_Tex") if p in spec["textures"]), None)
        base = tex_node(tree, spec, prop, (-400, 100)) if prop else None
        emit = tree.nodes.new("ShaderNodeEmission")
        emit.location = (0, 100)
        if base is not None:
            base.name = "_MainTex"                     # where the format converters look for the colour picture
            tree.links.new(base.outputs["Color"], emit.inputs["Color"])
        lo, _hi = alpha_range(base.image) if base is not None else (1.0, 1.0)
        if blend and base is not None and lo < 0.98:
            clear = tree.nodes.new("ShaderNodeBsdfTransparent")
            clear.location = (0, -100)
            mix = tree.nodes.new("ShaderNodeMixShader")
            mix.location = (250, 0)
            tree.links.new(base.outputs["Alpha"], mix.inputs[0])
            tree.links.new(clear.outputs[0], mix.inputs[1])
            tree.links.new(emit.outputs[0], mix.inputs[2])
            tree.links.new(mix.outputs[0], out.inputs["Surface"])
            mat.blend_method, mat.shadow_method = "BLEND", "NONE"
            mat.show_transparent_back = False
        else:
            tree.links.new(emit.outputs[0], out.inputs["Surface"])
        mat.use_backface_culling = int(spec["floats"].get("_Cull", 2)) == 2
        if not blend:                                  # the eye material also draws the brows, lashes and teeth: it
            mat["tsq_overlay"] = 0                     # is the face, not a card hidden in the head (PMX morph cutter)
        return made(spec, "unlit")

    def family(name):
        return lambda shader, spec: (spec.get("hints") or {}).get("family") == name

    return [(family("tcp2"), build_tcp2), (family("uts2"), build_uts2),
            (family("eye"), lambda mat, spec: build_flat(mat, spec, False)),
            (family("particle"), lambda mat, spec: build_flat(mat, spec, True))]
