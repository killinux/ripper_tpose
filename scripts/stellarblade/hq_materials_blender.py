"""Wire a Stellar Blade outfit .blend the way the game shades it (hq_materials.py's materials.json): each listed
material becomes a full Principled set-up - base colour; ORM (red AO -> specular occlusion, green roughness between
the instance's min / max, blue metallic x Metallic); the baked normal map (UE / DirectX: green flipped); the
knit-style pattern normal tiled on top where the fuzz mask is (Pattern01_*); clear coat from the layer mask; sheen
from the fuzz mask; emission from the emissive mask's Emissive_CH channel x EmissiveColor (only when
EmissivePower > 0 and the colour is not black - otherwise nothing glows in the game); masked materials clip at 1/3
like the game.
(The PMX side - one colour texture per material - is export_pmx_blender.py --hq-materials.)

    blender -b <Eve_*.blend> --python hq_materials_blender.py -- --materials <dir>/materials.json
        --save <out.blend> [--copy-textures <dir>]

Image paths are stored relative to the saved .blend; --copy-textures copies maps from outside its folder (the
shared pattern normal, the _pmx colours) into <dir> first so the folder stays self-contained.  The eye's colour is
rebuilt from the game's values too (eye_material.py: the archived .blend files drew the iris at 40% of its width):
a material named like an eye instance in materials.json "eyes" gets that instance's values and textures (loaded
from hq_materials.py's paths, or by name next to materials.json / the .blend, when the material lacks them); any
other material with the game's eye textures gets materials.json "eye", or Eve's values when there is none.
"""
import argparse
import json
import os
import shutil
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))     # eye_material

EMISSION_STRENGTH = 2.0          # UE EmissivePower is HDR; 2 reads as lit in Eevee / Cycles (build_standalone: 2)
PATTERN_WEIGHT = 0.6             # the tiled detail normal's xy, scaled, where the fuzz mask is


def image(path, non_color=False, copy_to=None):
    if copy_to:
        os.makedirs(copy_to, exist_ok=True)
        dst = os.path.join(copy_to, os.path.basename(path))
        if os.path.abspath(dst) != os.path.abspath(path):
            shutil.copy2(path, dst)
        path = dst
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def base_image_node(mat, p):
    for link in p.inputs["Base Color"].links:
        if link.from_node.type == "TEX_IMAGE":
            return link.from_node
    return None


def channel(sep, ch):
    return sep.outputs["RGB".index(ch)] if ch in "RGB" else None


def unpack_normal(nodes, links, img_node, x):
    """UE (DirectX) normal colour -> tangent vector (-1..1) with green flipped"""
    sep = nodes.new("ShaderNodeSeparateRGB")
    sep.location = (x, img_node.location.y)
    links.new(img_node.outputs["Color"], sep.inputs["Image"])
    vec = nodes.new("ShaderNodeCombineXYZ")
    vec.location = (x + 360, img_node.location.y)
    for i, out in enumerate(sep.outputs):
        m = nodes.new("ShaderNodeMath")
        m.location = (x + 180, img_node.location.y - 60 * i)
        m.operation = "MULTIPLY_ADD"
        m.inputs[1].default_value = -2.0 if i == 1 else 2.0      # flip green
        m.inputs[2].default_value = 1.0 if i == 1 else -1.0
        links.new(out, m.inputs[0])
        links.new(m.outputs[0], vec.inputs[i])
    return vec.outputs["Vector"]


def wire_hq(mat, d, copy_to):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    p = principled(mat)
    if p is None:
        return "no Principled BSDF"
    tex = {k: v for k, v in d["textures"].items() if not str(v).startswith("MISSING")}
    base = base_image_node(mat, p)
    x0 = p.location.x - 1500
    y = p.location.y
    done = []
    sep_orm = None
    if "orm" in tex:
        n = nodes.new("ShaderNodeTexImage")
        n.image = image(tex["orm"], True, copy_to)
        n.location = (x0, y - 300)
        sep_orm = nodes.new("ShaderNodeSeparateRGB")
        sep_orm.location = (x0 + 300, y - 300)
        links.new(n.outputs["Color"], sep_orm.inputs["Image"])
        rng = nodes.new("ShaderNodeMapRange")
        rng.location = (x0 + 500, y - 260)
        rng.inputs["To Min"].default_value = d["roughness_min"]
        rng.inputs["To Max"].default_value = d["roughness_max"]
        links.new(sep_orm.outputs["G"], rng.inputs["Value"])
        links.new(rng.outputs["Result"], p.inputs["Roughness"])
        met = nodes.new("ShaderNodeMath")
        met.operation = "MULTIPLY"
        met.location = (x0 + 500, y - 420)
        met.inputs[1].default_value = d["metallic"]
        links.new(sep_orm.outputs["B"], met.inputs[0])
        links.new(met.outputs[0], p.inputs["Metallic"])
        spec = nodes.new("ShaderNodeMath")                    # specular occlusion: no sky in a crease
        spec.operation = "MULTIPLY"
        spec.location = (x0 + 500, y - 560)
        spec.inputs[1].default_value = 0.5
        links.new(sep_orm.outputs["R"], spec.inputs[0])
        links.new(spec.outputs[0], p.inputs["Specular"])
        done.append("orm")
    masks = {}
    for key in ("fuzz_mask", "layer_mask", "shading_mask"):
        if key in tex and tex[key] not in masks:
            n = nodes.new("ShaderNodeTexImage")
            n.image = image(tex[key], True, copy_to)
            n.location = (x0, y - 700 - 300 * len(masks))
            s = nodes.new("ShaderNodeSeparateRGB")
            s.location = (x0 + 300, n.location.y)
            links.new(n.outputs["Color"], s.inputs["Image"])
            masks[tex[key]] = s
    fuzz = None
    if "fuzz" in d and "fuzz_mask" in tex:
        fuzz = channel(masks[tex["fuzz_mask"]], d["fuzz"]["channel"])
        sh = nodes.new("ShaderNodeMath")
        sh.operation = "MULTIPLY"
        sh.location = (x0 + 500, y - 700)
        sh.inputs[1].default_value = d["fuzz"]["intensity"]
        links.new(fuzz, sh.inputs[0])
        links.new(sh.outputs[0], p.inputs["Sheen"])
        p.inputs["Sheen Tint"].default_value = 0.5
        done.append("sheen")
    if "clearcoat" in d and "layer_mask" in tex:
        cc = channel(masks[tex["layer_mask"]], d["clearcoat"]["channel"])
        links.new(cc, p.inputs["Clearcoat"])
        p.inputs["Clearcoat Roughness"].default_value = d["clearcoat"]["roughness"]
        done.append("clearcoat")
    if "normal" in tex:
        n = nodes.new("ShaderNodeTexImage")
        n.image = image(tex["normal"], True, copy_to)
        n.location = (x0, y - 1400)
        v = unpack_normal(nodes, links, n, x0 + 300)
        if "pattern" in d and "pattern_normal" in tex:
            coord = nodes.new("ShaderNodeTexCoord")
            coord.location = (x0 - 500, y - 1750)
            mp = nodes.new("ShaderNodeMapping")
            mp.location = (x0 - 300, y - 1750)
            for i in range(3):
                mp.inputs["Scale"].default_value[i] = d["pattern"]["tiling"]
            links.new(coord.outputs["UV"], mp.inputs["Vector"])
            pn = nodes.new("ShaderNodeTexImage")
            pn.image = image(tex["pattern_normal"], True, copy_to)
            pn.location = (x0, y - 1750)
            links.new(mp.outputs["Vector"], pn.inputs["Vector"])
            pv = unpack_normal(nodes, links, pn, x0 + 300)
            # UDN blend: base xy + weight x detail xy, base z
            w = nodes.new("ShaderNodeVectorMath")
            w.operation = "MULTIPLY"
            w.location = (x0 + 800, y - 1750)
            links.new(pv, w.inputs[0])
            wk = nodes.new("ShaderNodeCombineXYZ")
            wk.location = (x0 + 600, y - 1900)
            if fuzz is not None:
                for i in range(2):
                    m = nodes.new("ShaderNodeMath")
                    m.operation = "MULTIPLY"
                    m.location = (x0 + 450, y - 1900 - 60 * i)
                    m.inputs[1].default_value = PATTERN_WEIGHT
                    links.new(fuzz, m.inputs[0])
                    links.new(m.outputs[0], wk.inputs[i])
            else:
                wk.inputs[0].default_value = wk.inputs[1].default_value = PATTERN_WEIGHT
            wk.inputs[2].default_value = 0.0
            links.new(wk.outputs["Vector"], w.inputs[1])
            add = nodes.new("ShaderNodeVectorMath")
            add.operation = "ADD"
            add.location = (x0 + 1000, y - 1500)
            links.new(v, add.inputs[0])
            links.new(w.outputs["Vector"], add.inputs[1])
            v = add.outputs["Vector"]
            done.append("pattern x%g" % d["pattern"]["tiling"])
        nrm = nodes.new("ShaderNodeVectorMath")
        nrm.operation = "NORMALIZE"
        nrm.location = (x0 + 1150, y - 1450)
        links.new(v, nrm.inputs[0])
        col = nodes.new("ShaderNodeVectorMath")                # back to a colour: (v + 1) / 2
        col.operation = "MULTIPLY_ADD"
        col.location = (x0 + 1300, y - 1450)
        links.new(nrm.outputs["Vector"], col.inputs[0])
        col.inputs[1].default_value = (0.5, 0.5, 0.5)
        col.inputs[2].default_value = (0.5, 0.5, 0.5)
        nm = nodes.new("ShaderNodeNormalMap")
        nm.location = (x0 + 1450, y - 1450)
        links.new(col.outputs["Vector"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], p.inputs["Normal"])
        done.append("normal")
    if "emissive" in d and "emissive" in tex:
        n = nodes.new("ShaderNodeTexImage")                     # a mask: one channel (Emissive_CH) x EmissiveColor
        n.image = image(tex["emissive"], True, copy_to)
        n.location = (x0, y - 2100)
        ch = d["emissive"].get("channel", "R")
        if ch == "A":
            lit = n.outputs["Alpha"]
        else:
            sep = nodes.new("ShaderNodeSeparateRGB")
            sep.location = (x0 + 280, y - 2100)
            links.new(n.outputs["Color"], sep.inputs["Image"])
            lit = sep.outputs[ch]
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.location = (x0 + 460, y - 2100)
        links.new(lit, mix.inputs["Color1"])
        mix.inputs["Color2"].default_value = tuple(d["emissive"]["color"]) + (1.0,)
        links.new(mix.outputs["Color"], p.inputs["Emission"])
        p.inputs["Emission Strength"].default_value = EMISSION_STRENGTH
        done.append("emission")
    if d["blend"] == "BLEND_Masked" and base is not None:
        links.new(base.outputs["Alpha"], p.inputs["Alpha"])
        mat.blend_method = "CLIP"
        mat.shadow_method = "CLIP"
        mat.alpha_threshold = 0.3333
        done.append("alpha clip")
    mat["sb_hq_materials"] = ", ".join(done)
    return ", ".join(done)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", required=True)
    ap.add_argument("--save", required=True)
    ap.add_argument("--copy-textures", default="")
    args = ap.parse_args(argv)
    doc = json.load(open(args.materials, encoding="utf-8"))
    mats = doc["materials"]
    report = {}
    for name, d in mats.items():
        mat = bpy.data.materials.get(name)
        if mat is None or not mat.use_nodes:
            report[name] = "not in this .blend"
            continue
        report[name] = wire_hq(mat, d, args.copy_textures or None)
    import eye_material
    eyes = doc.get("eyes") or {}
    roots = [os.path.dirname(os.path.abspath(args.materials)), os.path.dirname(bpy.data.filepath)]
    for mat in bpy.data.materials:
        if mat.name in mats:
            continue
        own = eyes.get(eye_material.base_name(mat.name))
        what = eye_material.rewire_eye(mat, own or doc.get("eye"), roots,
                                       (lambda path: image(path, False, args.copy_textures or None)) if own else None)
        if what:
            report[mat.name] = what
    save = os.path.abspath(args.save)
    os.makedirs(os.path.dirname(save), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0      # saved twice below: no .blend1 next to it
    bpy.ops.wm.save_as_mainfile(filepath=save, relative_remap=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    for k, v in report.items():
        print("  %-28s %s" % (k, v))
    print("SB_HQ_MATERIALS=" + json.dumps({"saved": save, "materials": report}, ensure_ascii=False),
          flush=True)


if __name__ == "__main__":
    main()
