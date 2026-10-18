"""One look of a Stellar Blade woman (not Eve) as a .blend with the game's textures, plus preview renders.

    blender -b --factory-startup --python build_npc_blend.py -- --root D:\\stellarblade_npc --name Raven_Destroyed_01 \\
        --parts SB/Content/Art/Character/Monster/CH_M_NA_53/CH_M_NA_53_Destroyed_01,SB/Content/.../CH_M_NA_53_Facial \\
        --out D:\\stellarblade_npc\\looks\\Raven_Destroyed_01 [--nude] [--no-save] [--quick]

Parts are mesh packages exported by export_npc_raw.py (mesh + textures in <root>\\raw, the JSON of the materials in
<root>\\json). Every part is imported with io_scene_psk_psa; the parts of one character share the skeleton's rest pose,
so a body and its separate face line up without moving anything (the extra armatures are parented to the first).

Materials are a plain Principled setup from the material instance's parameters, resolved up its parents (a master
material's own textures - its ReferencedTextures - stand in where the instance names none, e.g. brows and lashes):
  - base colour map (x BaseTint when given), normal map, cut-out alpha (MA_DitherAlpha, OpacityMask);
  - hair (MA_CH_Hair & co.): mean of Root / Tip colour x Brightness x 2 like the fighter's sb_textures.py, cut out by
    its cards' map (*_ADIR: red) or its Alpha map;
  - brows / lashes: their own colour (BaseColour / Colour / root color), else the hair's x 0.7, cut out by their mask;
  - eyes (M_EyeRefractive): the game's iris / sclera network from ../eye_material.py with the character's own instance
    values (Iris UV Radius, ScaleByCenter, PupilScale, brightness) and the iris x IrisHueTint;
  - overlay shells (eye wet film, eye shadow, tear line, teeth occlusion, 'Hide' / MA_Clear slots) hidden.
This is the preview build; the HQ build is the SB HQ scripts (hq_materials.py -> hq_materials_blender.py).

Renders: preview.png (front), preview_back.png, preview_face.png; with --nude also preview_nude.png / _nude_back.png,
where every 'cloth' and 'hair' slot is hidden - what is left shows whether a body is under the clothes (report.json
lists every slot with its master and kind, and nude_hidden)."""
import argparse
import glob
import json
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Vector

# the game's eye colour network (the SB HQ scripts' eye_material.py, used read-only); without it eyes get the iris map
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import eye_material
except ImportError:
    eye_material = None

HIDE_MASTERS = {"MA_Clear", "M_EyeBlend", "MA_TeethOcculusion", "MA_Tearline", "M_lacrimal_fluid", "M_Eye_Occlusion"}
HIDE_WORDS = ("tearline", "eyeshadow", "eyeocclusion", "eyeocc", "occulusion", "occlusion", "_fluid", "eyeblend",
              "lacimal", "lacrimal", "mouthoc", "hide", "ma_clear", "lens", "newmaterial", "glass")
BODY_MASTERS = ("MA_Skin", "MA_Teeth", "MA_Meta_Teeth", "MA_CH_XionCitizen_Head")
HAIR_MASTERS = ("MA_CH_Hair", "MA_CH_Hair_High", "MA_CH_MetaLowHair", "Mat_Hair_V1", "Temp_MA_CH_M_NA_21_HR",
                "MA_CH_M_NA_21_Hair_New2")
BROW_MASTERS = {"MA_CH_NPC_Lilly_Eyebrow", "MA_CH_M_NA_53_Eyebrow", "MA_CH_M_NA_961_Eyebrow", "MA_CH_NPC_Motherspier_Eyebrow",
                "testmaterial_eyebrow", "M_Lashes", "MA_CH_M_NA_21_Eyelashes_2", "MA_CH_LowEyelashe"}
BODY_WORDS = ("skin", "body_01", "basebody", "head", "face", "teeth")
HAIR_ALPHA_BOOST = 3.0
BASE_KEYS = ("Basecolor", "BaseColor", "BaseColor Texture", "Albedo", "Diffuse", "TeethColor", "TeethA")
NORMAL_KEYS = ("Baked NormalMap", "BaseNormal", "BakeNormal", "BakedNormal", "NormalMap", "BaseNormal Texture", "04.Normal",
               "TeethN")


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\stellarblade_npc")
    ap.add_argument("--name", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nude", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--res", type=int, default=900)
    ap.add_argument("--quick", action="store_true", help="front render only (the variant survey)")
    return ap.parse_args(argv)


def quoted(ref):
    """"Texture2D'Name'" -> "Name" """
    return ref.split("'")[1] if "'" in ref else ref


class Materials:
    def __init__(self, root):
        self.mi = {}
        for f in glob.glob(os.path.join(root, "json", "**", "*.json"), recursive=True):
            try:
                data = json.load(open(f, encoding="utf-8-sig"))
            except ValueError:
                continue
            for e in data if isinstance(data, list) else []:
                if e.get("Type", "").startswith("MaterialInstance") or e.get("Type") == "Material":
                    p = e.get("Properties") or {}
                    refs = (p.get("CachedExpressionData") or {}).get("ReferencedTextures") or []
                    self.mi[e["Name"]] = {
                        "parent": quoted((p.get("Parent") or {}).get("ObjectName", "")),
                        "tex": {t["ParameterInfo"]["Name"]: quoted((t.get("ParameterValue") or {}).get("ObjectName", ""))
                                for t in p.get("TextureParameterValues") or []},
                        "vec": {t["ParameterInfo"]["Name"]: [t["ParameterValue"][k] for k in "RGBA"]
                                for t in p.get("VectorParameterValues") or [] if isinstance(t.get("ParameterValue"), dict)},
                        "sca": {t["ParameterInfo"]["Name"]: t["ParameterValue"] for t in p.get("ScalarParameterValues") or []},
                        "refs": [quoted((r or {}).get("ObjectName", "")) for r in refs if r],
                    }
        self.png = {}
        for f in glob.glob(os.path.join(root, "raw", "**", "*.png"), recursive=True):
            self.png.setdefault(os.path.splitext(os.path.basename(f))[0].lower(), f)

    def resolve(self, name):
        """(master, textures, vectors, scalars, the master's own textures) - an instance's values over its parents'"""
        chain, n = [], name
        while n in self.mi and len(chain) < 10:
            chain.append(self.mi[n])
            if not self.mi[n]["parent"]:
                break
            n = self.mi[n]["parent"]
        tex, vec, sca = {}, {}, {}
        for m in reversed(chain):
            tex.update({k: v for k, v in m["tex"].items() if v})
            vec.update(m["vec"])
            sca.update(m["sca"])
        refs = chain[-1]["refs"] if chain else []
        return n, tex, vec, sca, refs

    def texture(self, name):
        return self.png.get((name or "").lower())


def image(path, colour):
    img = bpy.data.images.load(path, check_existing=True)
    if not colour:
        img.colorspace_settings.name = "Non-Color"
    return img


def coverage(nt, img, x=-800, y=-250, red=False):
    """socket with a mask's coverage: its alpha when the map has one, else its red; red=True for a hair cards' *_ADIR
    map (alpha, depth, ID, root - its own alpha channel is the root gradient, which left every crown bald)"""
    import numpy as np

    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = img
    n.location = (x, y)
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    if not red and img.channels == 4 and float(px[3::4].min()) < 0.99:
        return n.outputs["Alpha"]
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (x + 280, y)
    nt.links.new(n.outputs["Color"], sep.inputs["Color"])
    return sep.outputs["Red"]


def classify(name, master):
    low = name.lower()
    if master in HIDE_MASTERS or any(w in low for w in HIDE_WORDS):
        return "hidden"
    if master == "M_EyeRefractive":
        return "eye"
    if "brow" in low or "lash" in low or master in BROW_MASTERS:
        return "brow"
    if master in HAIR_MASTERS or master.startswith("MA_CH_Hair"):
        return "hair"
    if master.startswith(BODY_MASTERS) or any(w in low for w in BODY_WORDS):
        return "body"
    return "cloth"


def hair_colour(master, vec, sca):
    """MA_CH_Hair's colour the way the fighter's sb_textures.py takes it: mean of root and tip x Brightness x 2, a
    light colour brought down whole so its hue stays"""
    if master == "Mat_Hair_V1":
        root, tip = vec.get("Color Gradient A", [0.3, 0.25, 0.2, 1])[:3], vec.get("Color Gradient B", [0.3, 0.25, 0.2, 1])[:3]
        lin = [0.5 * (a + b) for a, b in zip(root, tip)]
    elif "Param" in vec and "RootColor" not in vec:
        lin = list(vec["Param"][:3])
    else:
        root = vec.get("RootColor", [0.1, 0.07, 0.05, 1])[:3]
        tip = vec.get("TipColor", root)[:3]
        if max(root + tip) <= 0.0 and "RootColorBlended" in vec:
            root, tip = vec["RootColorBlended"][:3], vec.get("TipColorBlended", vec["RootColorBlended"])[:3]
        lin = [0.5 * (a + b) * sca.get("Brightness", 1.0) * 2.0 for a, b in zip(root, tip)]
    top = max(1.0, max(lin))
    return [c / top for c in lin]


def principled(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (-300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Specular"].default_value = 0.35
    mat.use_backface_culling = False
    return nt, bsdf


def eye(mat, nt, bsdf, mats, tex, vec, sca, info):
    iris = mats.texture(tex.get("IrisColor")) or mats.texture("S_EyeIrisBaseColor")
    sclera = mats.texture(tex.get("ScleraColor")) or mats.texture("T_EyeScleraBaseColor")
    if eye_material and iris and sclera:
        own_tint = not hasattr(eye_material, "params_from_values")
        if own_tint:          # eye_material.py before 10-18: no tints of its own
            params = eye_material.params_from_scalars(sca)
        else:
            params = eye_material.params_from_values(sca, {k: dict(zip("RGBA", v)) for k, v in vec.items()})
        mix = eye_material.link_eye_colour(nt.nodes, nt.links, bsdf, image(sclera, True), image(iris, True), params)
        tint = vec.get("IrisHueTint")
        if tint and own_tint:   # every NPC shares the iris map S_EyeIrisBaseColor; IrisHueTint makes the colour theirs
            mul = nt.nodes.new("ShaderNodeVectorMath")
            mul.operation = "MULTIPLY"
            mul.inputs[1].default_value = tint[:3]
            mul.location = (mix.location.x - 150, mix.location.y - 250)
            nt.links.new(mix.inputs["Color2"].links[0].from_socket, mul.inputs[0])
            nt.links.new(mul.outputs["Vector"], mix.inputs["Color2"])
        info["eye"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in params.items()}
        info["iris_tint"] = [round(c, 3) for c in (tint or [1, 1, 1])[:3]]
    elif iris:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(iris, True)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.08
    bsdf.inputs["Specular"].default_value = 0.5


def brow(mat, nt, bsdf, mats, master, tex, vec, sca, refs, info):
    mask = next((tex[k] for k in ("Mask", "Alpha", "HairTexture", "Diffuse") if tex.get(k)), "")
    if not mats.texture(mask):
        mask = next((r for r in refs if ("brow" in r.lower() or "lash" in r.lower()) and mats.texture(r)), "")
        mask = mask or next((r for r in refs if mats.texture(r)), "")
    col = vec.get("BaseColour") or vec.get("Colour") or vec.get("root color")
    if col is None and ("RootColor" in vec or "TipColor" in vec):
        col = hair_colour(master, vec, sca)
    if col is None:
        info["needs_hair_colour"] = True
        col = [0.03, 0.02, 0.015]
    bsdf.inputs["Base Color"].default_value = list(col[:3]) + [1]
    bsdf.inputs["Roughness"].default_value = 0.7
    if mats.texture(mask):
        nt.links.new(coverage(nt, image(mats.texture(mask), False)), bsdf.inputs["Alpha"])
        info["mask"] = mask
    else:
        bsdf.inputs["Alpha"].default_value = 0.0      # no mask found: better no brow than an opaque shell
        info["mask"] = None
    mat.blend_method = "CLIP"
    mat.alpha_threshold = 0.3
    mat.shadow_method = "NONE"


def build_material(mat, mats):
    master, tex, vec, sca, refs = mats.resolve(mat.name.split(".")[0])
    low = mat.name.lower()
    kind = classify(mat.name, master)
    nt, bsdf = principled(mat)
    info = {"material": mat.name, "master": master, "kind": kind}
    if kind == "hidden":
        bsdf.inputs["Alpha"].default_value = 0.0
        mat.blend_method = "CLIP"
        mat.shadow_method = "NONE"
        return info
    if kind == "eye":
        eye(mat, nt, bsdf, mats, tex, vec, sca, info)
        return info
    if kind == "brow":
        brow(mat, nt, bsdf, mats, master, tex, vec, sca, refs, info)
        return info
    alpha = None
    base_name = next((tex[k] for k in BASE_KEYS if tex.get(k) and mats.texture(tex[k])), "")
    if kind == "hair" and not base_name:
        colour = hair_colour(master, vec, sca)
        bsdf.inputs["Base Color"].default_value = colour + [1]
        bsdf.inputs["Roughness"].default_value = min(0.8, sca.get("Roughness", 0.4) + 0.15)
        hair_tex = tex.get("HairTexture", "")
        a_name = hair_tex if hair_tex.endswith("_ADIR") and mats.texture(hair_tex) else (tex.get("Alpha") or hair_tex)
        if mats.texture(a_name):
            # the game draws layered cards dithered; cut out at 0.35 the thin strands of an atlas vanish: coverage x 3
            # before the cut
            boost = nt.nodes.new("ShaderNodeMath")
            boost.operation = "MULTIPLY"
            boost.use_clamp = True
            boost.inputs[1].default_value = HAIR_ALPHA_BOOST
            nt.links.new(coverage(nt, image(mats.texture(a_name), False), red=a_name.endswith("_ADIR")), boost.inputs[0])
            alpha = boost.outputs["Value"]
            info["alpha"] = a_name
        info["hair_colour"] = [round(c, 3) for c in colour]
    elif base_name:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(mats.texture(base_name), True)
        n.location = (-900, 200)
        colour = n.outputs["Color"]
        tint = vec.get("BaseTint") or vec.get("Base Color Tint") or vec.get("Tint")
        if tint and [round(c, 3) for c in tint[:3]] != [1.0, 1.0, 1.0]:
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs["Fac"].default_value = 1.0
            mix.inputs["Color2"].default_value = list(tint[:3]) + [1]
            mix.location = (-600, 200)
            nt.links.new(colour, mix.inputs["Color1"])
            colour = mix.outputs["Color"]
        nt.links.new(colour, bsdf.inputs["Base Color"])
        info["base"] = base_name
        if master == "MA_DitherAlpha" or tex.get("OpacityMask"):
            a_name = tex.get("OpacityMask")
            alpha = coverage(nt, image(mats.texture(a_name), False)) if mats.texture(a_name) else n.outputs["Alpha"]
    else:
        col = vec.get("BaseColor") or vec.get("Basecolor") or vec.get("Color") or vec.get("Base Color")
        ref = "" if col else next((r for r in refs if mats.texture(r) and r.lower().endswith(("_a", "_d", "_basecolor", "_bc"))), "")
        if ref:
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = image(mats.texture(ref), True)
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
            info["base"] = ref + " (master's own)"
        else:
            col = col or [0.5, 0.5, 0.5, 1]
            bsdf.inputs["Base Color"].default_value = list(col[:3]) + [1]
            info["base"] = "(colour %s)" % [round(c, 3) for c in col[:3]]
    if alpha is not None:
        nt.links.new(alpha, bsdf.inputs["Alpha"])
        mat.blend_method = "CLIP"
        mat.alpha_threshold = 0.35
        mat.shadow_method = "CLIP"
    normal_name = next((tex[k] for k in NORMAL_KEYS if tex.get(k)), "")
    if normal_name and mats.texture(normal_name) and kind != "hair":
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(mats.texture(normal_name), False)
        n.location = (-900, -400)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-550, -400)
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if master.startswith("MA_Skin") or (kind == "body" and ("skin" in low or "head" in low)):
        bsdf.inputs["Subsurface"].default_value = 0.08
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        bsdf.inputs["Subsurface Color"].default_value = (0.9, 0.5, 0.4, 1)
        bsdf.inputs["Roughness"].default_value = 0.5
    return info


def colour_brows(report):
    """brows without a colour of their own take the look's hair colour, a little darker"""
    hair = next((m["hair_colour"] for m in report["materials"] if m.get("hair_colour")), None)
    for m in report["materials"]:
        if m.pop("needs_hair_colour", False) and hair:
            bsdf = next(n for n in bpy.data.materials[m["material"]].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            bsdf.inputs["Base Color"].default_value = [c * 0.7 for c in hair] + [1]
            m["brow_colour"] = "hair x 0.7"


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def head_point(arm):
    """world position of the head (Bip001-Head's middle), or None"""
    if arm is None:
        return None
    bone = arm.data.bones.get("Bip001-Head") or next((b for b in arm.data.bones if b.name.lower().endswith("head")), None)
    if bone is None:
        return None
    return arm.matrix_world @ ((bone.head_local + bone.tail_local) / 2)


def setup_scene(res):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_gtao = True
    scene.eevee.taa_render_samples = 32
    scene.render.resolution_x, scene.render.resolution_y = int(res * 0.62), res
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"
    world = bpy.data.worlds.new("preview")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.22, 0.23, 0.26, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    for name, rot, energy in (("key", (55, 0, 70), 3.2), ("fill", (65, 0, -110), 1.2), ("rim", (60, 0, 180), 1.6)):
        ld = bpy.data.lights.new("preview_" + name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(8)
        ob = bpy.data.objects.new("preview_" + name, ld)
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)
    cam = bpy.data.objects.new("preview_camera", bpy.data.cameras.new("preview_camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, cam


def shoot(scene, cam, meshes, path, direction, head=None):
    lo, hi = bounds(meshes)
    centre, size = (lo + hi) / 2, hi - lo
    height = size.z
    if head is not None:          # a portrait: 34 cm high around the head
        centre, height = head + Vector((0, 0, -2.0)), 34.0
    cam.data.lens = 85
    dist = height * 1.15 * 85 / 36 + 10
    d = Vector(direction).normalized()
    cam.location = centre + d * dist
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = dist * 4
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    o = args()
    os.makedirs(o.out, exist_ok=True)
    addon_utils.enable("io_scene_psk_psa", default_set=False)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    mats = Materials(o.root)
    first_arm = None
    for package in o.parts.split(","):
        base = os.path.join(o.root, "raw", *package.strip().split("/"))
        path = next((base + e for e in (".psk", ".pskx") if os.path.exists(base + e)), None)
        if not path:
            raise SystemExit(f"[npc] not exported: {package}")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.psk(filepath=path)
        new = [ob for ob in bpy.data.objects if ob not in before]
        arm = next((ob for ob in new if ob.type == "ARMATURE"), None)
        if first_arm is None:
            first_arm = arm
            arm.name = o.name
        elif arm is not None:
            arm.parent = first_arm
    meshes = [ob for ob in bpy.data.objects if ob.type == "MESH"]
    report = {"name": o.name, "parts": o.parts.split(","), "materials": []}
    for mat in {s.material for m in meshes for s in m.material_slots if s.material}:
        report["materials"].append(build_material(mat, mats))
    report["materials"].sort(key=lambda m: m["material"])
    colour_brows(report)
    report["vertices"] = sum(len(m.data.vertices) for m in meshes)
    report["polygons"] = sum(len(m.data.polygons) for m in meshes)
    report["bones"] = len(first_arm.data.bones) if first_arm else 0
    lo, hi = bounds(meshes)
    report["height_cm"] = round(hi.z - lo.z, 1)
    scene, cam = setup_scene(o.res)
    # Stellar Blade's characters face +x after the PSK import
    shoot(scene, cam, meshes, os.path.join(o.out, "preview.png"), (1.0, -0.3, 0.06))
    if o.quick:
        json.dump(report, open(os.path.join(o.out, "report.json"), "w", encoding="utf-8"), indent=1)
        return
    shoot(scene, cam, meshes, os.path.join(o.out, "preview_back.png"), (-1.0, 0.3, 0.06))
    head = head_point(first_arm)
    if head is not None:
        shoot(scene, cam, meshes, os.path.join(o.out, "preview_face.png"), (1.0, -0.25, 0.02), head=head)
    if not o.no_save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(o.out, o.name + ".blend"))
    if o.nude:
        hidden = []
        for m in report["materials"]:
            if m["kind"] in ("cloth", "hair"):     # hair too: long hair hid what is (not) under the clothes
                mat = bpy.data.materials[m["material"]]
                hidden.append(mat.name)
                bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                for link in list(bsdf.inputs["Alpha"].links):
                    mat.node_tree.links.remove(link)
                bsdf.inputs["Alpha"].default_value = 0.0
                mat.blend_method = "CLIP"
                mat.shadow_method = "NONE"
        report["nude_hidden"] = hidden
        shoot(scene, cam, meshes, os.path.join(o.out, "preview_nude.png"), (1.0, -0.3, 0.06))
        shoot(scene, cam, meshes, os.path.join(o.out, "preview_nude_back.png"), (-1.0, 0.3, 0.06))
    json.dump(report, open(os.path.join(o.out, "report.json"), "w", encoding="utf-8"), indent=1)
    print("SB_NPC_REPORT=" + json.dumps({k: report[k] for k in ("name", "vertices", "polygons", "bones", "height_cm")}))


main()
