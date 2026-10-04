"""Blender side: Taimanin Collection's materials for ../taimaninsquad/build_blend.py (--materials <this file>).

Asagi, the motorcycle and the drop ship use the shaders Action Taimanin uses (Toony Colors Pro 2 as the studio
changed it, the Shader Forge eye shader, particle cards): those are ../actiontaimanin/atm_materials.py's builders,
taken as they are.  Added here is one builder for everything that is scenery:

    Curved/Curved_BG                    the bike race: _diffuse_tex x _diffuse_color, _light_tex (the baked light,
                                        on the second UV set), _glow_tex x _glow_color x _glow_velue
    eTOYLab/bg_default                  _MainTex x _MainTex_color x _MainTex_power, _Emission x _Emission_color x power
    Mobile/Unlit (Supports Lightmap), Legacy Shaders/..., Standard      the picture as it is
    (no shader)                         materials stripped in the build: pictures found by name (tcollection_scene)

What each slot is comes in the material's "hints" (tcollection_scene.background_hints), so the builder does not
care which shader it was:

    colour = base x tint [x light map] [+ glow x glow colour x strength]

computed on display values - the game renders in GAMMA space, as Action Taimanin does - and shown unlit: the
light is in the light map.  The compiled programs of these shaders were not read; the formula is what the slot
and property names say, and the result was compared with nothing but itself (README, "已知限制").
"""
import importlib.util
import os

GAMMA = 2.2
HERE = os.path.dirname(os.path.abspath(__file__))
ACTION = os.path.join(os.path.dirname(HERE), "actiontaimanin", "atm_materials.py")


def builders(api):
    plugin = importlib.util.spec_from_file_location("tco_action_materials", ACTION)
    action = importlib.util.module_from_spec(plugin)
    plugin.loader.exec_module(action)
    rules = action.builders(api)
    tex_node, alpha_range = api["tex_node"], api["alpha_range"]

    def build_background(mat, spec):
        hints = spec.get("hints") or {}
        tree = mat.node_tree
        nodes, links = tree.nodes, tree.links
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (1100, 0)

        def gamma(socket, power, location):
            node = nodes.new("ShaderNodeGamma")
            node.location = location
            node.inputs["Gamma"].default_value = power
            links.new(socket, node.inputs["Color"])
            return node.outputs["Color"]

        def mixed(kind, a, b, location):
            """a (a socket) x / + b (a socket or a colour)."""
            node = nodes.new("ShaderNodeMixRGB")
            node.blend_type = kind
            node.location = location
            node.inputs[0].default_value = 1.0
            links.new(a, node.inputs[1])
            if isinstance(b, (tuple, list)):
                node.inputs[2].default_value = (b[0], b[1], b[2], 1.0)
            else:
                links.new(b, node.inputs[2])
            return node.outputs[0]

        tint = hints.get("tint") or [1.0, 1.0, 1.0, 1.0]
        base = tex_node(tree, spec, hints.get("base_slot"), (-900, 300)) if hints.get("base_slot") else None
        if base is not None:
            base.name = "_MainTex"                     # where the format converters look for the colour picture
            colour = mixed("MULTIPLY", gamma(base.outputs["Color"], 1.0 / GAMMA, (-600, 300)), tint[:3], (-380, 300))
        else:
            rgb = nodes.new("ShaderNodeRGB")
            rgb.location = (-600, 300)
            rgb.outputs[0].default_value = (tint[0], tint[1], tint[2], 1.0)
            colour = rgb.outputs[0]
        if hints.get("light_slot"):
            uv = nodes.new("ShaderNodeUVMap")
            uv.location = (-1150, 0)
            uv.uv_map = hints.get("light_uv") or "UVMap"
            light = tex_node(tree, spec, hints["light_slot"], (-900, 0), uv_socket=uv.outputs["UV"])
            if light is not None:
                light.name = "_LightMap"
                colour = mixed("MULTIPLY", colour, gamma(light.outputs["Color"], 1.0 / GAMMA, (-600, 0)), (-160, 200))
        if hints.get("glow_slot"):
            glow = tex_node(tree, spec, hints["glow_slot"], (-900, -300))
            if glow is not None:
                glow.name = "_Glow"
                amount = [c * hints.get("glow_strength", 1.0) for c in hints.get("glow_color") or (1.0, 1.0, 1.0)]
                lit = mixed("MULTIPLY", gamma(glow.outputs["Color"], 1.0 / GAMMA, (-600, -300)), amount, (-380, -300))
                colour = mixed("ADD", colour, lit, (60, 100))
        emit = nodes.new("ShaderNodeEmission")
        emit.location = (560, 100)
        links.new(gamma(colour, GAMMA, (300, 100)), emit.inputs["Color"])
        mode = int(spec["floats"].get("_Mode", 0))     # the Standard shader's: 1 cut out, 2 / 3 see-through
        lo, _hi = alpha_range(base.image) if base is not None else (1.0, 1.0)
        if mode >= 1 and base is not None and lo < 0.98:
            clear = nodes.new("ShaderNodeBsdfTransparent")
            clear.location = (560, -100)
            mix = nodes.new("ShaderNodeMixShader")
            mix.location = (820, 0)
            links.new(base.outputs["Alpha"], mix.inputs[0])
            links.new(clear.outputs[0], mix.inputs[1])
            links.new(emit.outputs[0], mix.inputs[2])
            links.new(mix.outputs[0], out.inputs["Surface"])
            if mode == 1:
                mat.blend_method, mat.shadow_method = "CLIP", "CLIP"
                mat.alpha_threshold = min(max(spec["floats"].get("_Cutoff", 0.5), 0.01), 0.99)
            else:
                mat.blend_method, mat.shadow_method = "BLEND", "NONE"
                mat.show_transparent_back = False
        else:
            links.new(emit.outputs[0], out.inputs["Surface"])
        mat.use_backface_culling = int(spec["floats"].get("_Cull", 2)) == 2
        mat["tsq_overlay"] = 0
        return {"kind": "unlit", "base_map": hints.get("base_map"), "outline_mm": 0.0, "outline_color": [0.0, 0.0, 0.0]}

    return rules + [(lambda shader, spec: (spec.get("hints") or {}).get("family") == "background", build_background)]
