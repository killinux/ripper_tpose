"""CRISIS CORE -FINAL FANTASY VII- REUNION: PSK + material spec -> textured .blend (Blender 3.6, headless).

    blender --background --factory-startup --python build_blend.py -- --spec <spec.json>

The spec comes from export_model.py: the PSK, and per material instance its family, the parameters
merged over its parent chain and the PNG of every texture parameter.  How the game's shaders are
approximated (channels measured on the textures, see README.md):

  standard  MI_ch_Standard / EMStandard (M_ch_StandardSS)   Tex_Color = albedo (+ alpha when Masked
            and the instance does not set UseMaskDisable); Tex_MultiMask R = metallic (polished edges,
            studs, buckles), G = roughness (Roughness_Min..Max), B = AO; Tex_BakedNormal (DirectX,
            green flipped); Tex_2ndMultiMask R = emissive mask (Emi_ONOFF, x EmissiveColor x Emi_Int)
  skin      MI_ch_Human_Skin / Human_Mouth                    AlbedMap x BaseColor_Tint; MultiMaskMap
            R = subsurface amount (skin ~0.58, scalp 0), G = roughness, B = AO; BakedNormalMap; pores:
            PoreSpec tiled PoreTiling times as a bump, masked by PoreMask G (the *_MM2 map)
  hair      MI_ch_Hair (M_ch_Hair / HairSimple)               Tex_BaseColor x Brightness^0.15 (UseDiffuseBaseColor)
            with its alpha as strand mask (HASHED), Tex_Multi B = per-strand AO, Roughness, 0.6 x Specular
  eye       MI_ch_Eye2_ad                                     Tex_Colormap is the whole eye; glossy
  eyelash   MI_ch_Eyelash                                     Tex_Color x Color_Tint x Color_Int, alpha strands
  glass     MI_ch_Glass                                       Color_Tint (x Tex_Color), mostly transparent
  gem       MI_ch_GemStandard                                 Color_Main + "Add to emissive"

Everything is kept in UE centimetres (like the FF7 Rebirth / TFD blends, so the same XPS / PMX tools
apply).  Images are packed, so <out_dir> opens on its own.  Prints CCFF7R_REPORT={json}.
"""
import json
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Vector

if addon_utils.enable("io_scene_psk_psa", default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for Blender 3.6 (needed for PSK import)")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--spec" not in argv:
    raise SystemExit("usage: blender -b --factory-startup --python build_blend.py -- --spec spec.json")
SPEC = json.load(open(argv[argv.index("--spec") + 1], encoding="utf-8"))
MODEL_ID = SPEC["id"]
OUT_DIR = os.path.normpath(SPEC["out_dir"])
AO_MIX = 0.6          # how much of the baked AO darkens the albedo (UE only applies it to indirect light)
HAIR_BRIGHTNESS_EXP = 0.15   # hair colour x Brightness ** this (see build_hair)
HAIR_SPECULAR = 0.6          # x the instance's Specular
report = {"id": MODEL_ID, "warnings": [], "materials_built": {}, "missing_textures": []}


def log(msg):
    print("[ccff7r] " + msg, flush=True)


# ---------------------------------------------------------------- import
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
    for block in list(datablocks):
        datablocks.remove(block)

before = set(bpy.data.objects)
bpy.ops.import_scene.psk(
    filepath=SPEC["psk"],
    should_import_vertex_colors=True,
    should_import_vertex_normals=True,
    should_import_extra_uvs=True,
    should_import_mesh=True,
    should_import_materials=True,
    should_import_skeleton=True,
    should_import_shape_keys=True,
    bone_length=2.0,
)
created = [o for o in bpy.data.objects if o not in before]
arm = next((o for o in created if o.type == "ARMATURE"), None)
meshes = [o for o in created if o.type == "MESH"]
if arm is None or not meshes:
    print("CCFF7R_REPORT=" + json.dumps({**report, "error": "PSK import produced no armature/mesh"}), flush=True)
    raise SystemExit("nothing imported from " + SPEC["psk"])
arm.name = MODEL_ID + "_rig"
arm.data.name = MODEL_ID + "_rig"
for i, m in enumerate(meshes):
    m.name = MODEL_ID if i == 0 else "%s_%d" % (MODEL_ID, i)
    m.data.name = m.name

coll = bpy.data.collections.new(MODEL_ID)
bpy.context.scene.collection.children.link(coll)
for obj in [arm] + meshes:
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def split_weapon(mesh):
    """Zack's Buster Sword, Sephiroth's Masamune, Cissnei's shuriken are sections of the body mesh,
    skinned to the wpn / wpn_body / pivot bones that sit at the origin in the bind pose (the game's
    animations carry them to the hand or back sockets) - so they lie flat at the feet.  Faces whose
    vertices all follow those bones become their own object, still skinned to the same rig."""
    names = {g.index: g.name for g in mesh.vertex_groups}
    weapon_groups = {i for i, n in names.items() if n.lower().startswith(("wpn", "weapon")) or n.lower() == "pivot"}
    if not weapon_groups:
        return None
    is_weapon = []
    for v in mesh.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        is_weapon.append(best is not None and best.group in weapon_groups)
    polys = [p for p in mesh.data.polygons if all(is_weapon[i] for i in p.vertices)]
    if not polys or len(polys) == len(mesh.data.polygons):
        return None
    for p in mesh.data.polygons:
        p.select = False
    for p in polys:
        p.select = True
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")
    weapon = next(o for o in bpy.context.selected_objects if o is not mesh)
    weapon.name = mesh.name + "_weapon"
    weapon.data.name = weapon.name
    # drop the body's material slots the weapon does not use (and vice versa)
    for obj in (mesh, weapon):
        used = {p.material_index for p in obj.data.polygons}
        for i in reversed(range(len(obj.material_slots))):
            if i not in used:
                obj.active_material_index = i
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.material_slot_remove()
    return weapon


weapons = [w for w in (split_weapon(m) for m in list(meshes)) if w is not None]
report["weapon_objects"] = [w.name for w in weapons]
if weapons:
    log("weapon split off: %s" % ", ".join(w.name for w in weapons))
report["bones"] = len(arm.data.bones)
report["vertices"] = sum(len(m.data.vertices) for m in meshes)
report["faces"] = sum(len(m.data.polygons) for m in meshes)
log("imported %s: %d bones, %d vertices, %d faces" % (MODEL_ID, report["bones"], report["vertices"], report["faces"]))


# ---------------------------------------------------------------- node helpers
_images = {}


def image(path, color):
    key = (os.path.normcase(path), color)
    if key not in _images:
        img = bpy.data.images.load(path, check_existing=False)
        img.colorspace_settings.name = "sRGB" if color else "Non-Color"
        if not color:
            img.alpha_mode = "CHANNEL_PACKED"
        _images[key] = img
    return _images[key]


def new_tree(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (500, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return nt, bsdf


def tex(nt, path, color, loc, label, vector=None):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = image(path, color)
    n.location = loc
    n.label = label
    if vector is not None:
        nt.links.new(vector, n.inputs["Vector"])
    return n


def feed(nt, value, socket):
    """Link a socket, or set a constant (float or RGB(A))."""
    if hasattr(value, "is_output"):
        nt.links.new(value, socket)
    elif isinstance(value, (tuple, list)):
        v = list(value) + [1.0] * (4 - len(value))
        socket.default_value = v[:len(socket.default_value)] if hasattr(socket.default_value, "__len__") else v[0]
    else:
        socket.default_value = value if not hasattr(socket.default_value, "__len__") else (value, value, value, 1.0)


def separate(nt, socket, loc):
    n = nt.nodes.new("ShaderNodeSeparateColor")
    n.location = loc
    nt.links.new(socket, n.inputs["Color"])
    return n


def multiply(nt, a, b, fac, loc):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    n.blend_type = "MULTIPLY"
    n.location = loc
    n.inputs["Factor"].default_value = fac
    feed(nt, a, n.inputs[6])
    feed(nt, b, n.inputs[7])
    return n.outputs[2]


def scale(nt, color, factor, loc):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = "SCALE"
    n.location = loc
    feed(nt, color, n.inputs[0])
    n.inputs["Scale"].default_value = factor
    return n.outputs["Vector"]


def map_range(nt, socket, lo, hi, loc):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.location = loc
    nt.links.new(socket, n.inputs["Value"])
    n.inputs["To Min"].default_value = lo
    n.inputs["To Max"].default_value = hi
    return n.outputs["Result"]


def math_node(nt, op, a, b, loc):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.location = loc
    feed(nt, a, n.inputs[0])
    feed(nt, b, n.inputs[1])
    return n.outputs["Value"]


def normal_map(nt, path, strength, loc=(-1300, -700)):
    """UE normal maps are DirectX style: flip green for Blender."""
    t = tex(nt, path, False, loc, "Normal (DX)")
    sep = separate(nt, t.outputs["Color"], (loc[0] + 300, loc[1]))
    inv = math_node(nt, "SUBTRACT", 1.0, sep.outputs["Green"], (loc[0] + 500, loc[1] - 80))
    comb = nt.nodes.new("ShaderNodeCombineColor")
    comb.location = (loc[0] + 700, loc[1])
    nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
    nt.links.new(inv, comb.inputs["Green"])
    nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (loc[0] + 900, loc[1])
    nm.inputs["Strength"].default_value = strength
    nt.links.new(comb.outputs["Color"], nm.inputs["Color"])
    return nm.outputs["Normal"]


def is_white(col):
    return col is None or all(abs(c - 1.0) < 1e-3 for c in col[:3])


def blend_mode(ov):
    return str(ov.get("BlendMode", "")).split("::")[-1]


def apply_alpha(nt, mat, bsdf, alpha, ov, soft=False):
    """Masked -> clip at OpacityMaskClipValue (hashed for strands); UseMaskDisable -> opaque."""
    mode = blend_mode(ov)
    if alpha is None or ov.get("UseMaskDisable") or mode not in ("BLEND_Masked", "BLEND_Translucent"):
        return "opaque"
    nt.links.new(alpha, bsdf.inputs["Alpha"])
    if mode == "BLEND_Translucent" or soft:
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
        return "hashed"
    mat.blend_method = "CLIP"
    mat.shadow_method = "CLIP"
    mat.alpha_threshold = float(ov.get("OpacityMaskClipValue", 0.3333))
    return "clip %.3f" % mat.alpha_threshold


# ---------------------------------------------------------------- material families
def build_standard(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc, vec, sw, ov = p["scalars"], p["vectors"], p["switches"], p["overrides"]
    bc_path = tf.get("Tex_Color") or next((v for k, v in tf.items() if v.endswith("_BC.png")), None)
    bc = tex(nt, bc_path, True, (-1300, 400), "Color") if bc_path else None
    base = bc.outputs["Color"] if bc else (0.55, 0.55, 0.55, 1.0)
    if not bc:
        report["missing_textures"].append("%s: no colour map" % mat.name)
    if not is_white(vec.get("Color_Tint")):
        base = multiply(nt, base, vec["Color_Tint"], 1.0, (-800, 450))
    if tf.get("Tex_MultiMask"):
        mm = tex(nt, tf["Tex_MultiMask"], False, (-1300, 0), "MultiMask R metal G rough B AO")
        sep = separate(nt, mm.outputs["Color"], (-1000, 0))
        nt.links.new(map_range(nt, sep.outputs["Green"], sc.get("Roughness_Min", 0.0), sc.get("Roughness_Max", 1.0),
                               (-700, -50)), bsdf.inputs["Roughness"])
        nt.links.new(map_range(nt, sep.outputs["Red"], sc.get("Metallic_Min", 0.0), sc.get("Metallic_Max", 1.0),
                               (-700, -300)), bsdf.inputs["Metallic"])
        base = multiply(nt, base, sep.outputs["Blue"], AO_MIX * sc.get("AO_Int", 1.0), (-400, 400))
    else:
        bsdf.inputs["Roughness"].default_value = 0.6
    feed(nt, base, bsdf.inputs["Base Color"])
    bsdf.inputs["Specular"].default_value = 0.5
    if tf.get("Tex_BakedNormal"):
        nt.links.new(normal_map(nt, tf["Tex_BakedNormal"], sc.get("BakedNormal_Scale", 1.0)), bsdf.inputs["Normal"])
    if sw.get("Emi_ONOFF") and tf.get("Tex_2ndMultiMask"):
        m2 = tex(nt, tf["Tex_2ndMultiMask"], False, (-1300, -1100), "2ndMultiMask R emissive")
        sep2 = separate(nt, m2.outputs["Color"], (-1000, -1100))
        glow = base if is_white(vec.get("EmissiveColor")) else multiply(nt, base, vec["EmissiveColor"], 1.0, (-400, -900))
        feed(nt, glow, bsdf.inputs["Emission"])
        nt.links.new(math_node(nt, "MULTIPLY", sep2.outputs["Red"], sc.get("Emi_Int", 1.0), (-700, -1100)),
                     bsdf.inputs["Emission Strength"])
        info["emissive"] = sc.get("Emi_Int", 1.0)
    info["alpha"] = apply_alpha(nt, mat, bsdf, bc.outputs["Alpha"] if bc else None, ov)


def build_skin(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc, vec, ov = p["scalars"], p["vectors"], p["overrides"]
    bc = tex(nt, tf["AlbedMap"], True, (-1300, 400), "Albedo") if tf.get("AlbedMap") else None
    base = bc.outputs["Color"] if bc else (0.8, 0.62, 0.52, 1.0)
    if not bc:
        report["missing_textures"].append("%s: no AlbedMap" % mat.name)
    if not is_white(vec.get("BaseColor_Tint")):
        base = multiply(nt, base, vec["BaseColor_Tint"], 1.0, (-800, 450))
    if tf.get("MultiMaskMap"):
        mm = tex(nt, tf["MultiMaskMap"], False, (-1300, 0), "MultiMask R sss G rough B AO")
        sep = separate(nt, mm.outputs["Color"], (-1000, 0))
        rough = map_range(nt, sep.outputs["Green"], sc.get("Roughness_Min", 0.0), sc.get("Roughness_Max", 1.0), (-700, -50))
        if abs(sc.get("RoughnessScale", 1.0) - 1.0) > 1e-3:
            rough = math_node(nt, "MULTIPLY", rough, sc["RoughnessScale"], (-500, -50))
        nt.links.new(rough, bsdf.inputs["Roughness"])
        nt.links.new(math_node(nt, "MULTIPLY", sep.outputs["Red"], 0.6, (-700, -250)), bsdf.inputs["Subsurface"])
        base = multiply(nt, base, sep.outputs["Blue"], AO_MIX * 0.8, (-400, 400))
    else:
        bsdf.inputs["Roughness"].default_value = 0.5
        bsdf.inputs["Subsurface"].default_value = 0.3
    feed(nt, base, bsdf.inputs["Base Color"])
    feed(nt, base, bsdf.inputs["Subsurface Color"])
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    bsdf.inputs["Specular"].default_value = min(1.0, 0.5 * sc.get("Spec_Int", 1.0))
    normal = None
    if tf.get("BakedNormalMap"):
        normal = normal_map(nt, tf["BakedNormalMap"], sc.get("BakedNormalScale", 1.0))
    if tf.get("PoreSpec") and tf.get("PoreMask"):
        uv = nt.nodes.new("ShaderNodeTexCoord")
        uv.location = (-1800, -1300)
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.location = (-1600, -1300)
        tiles = sc.get("PoreTiling", 20.0)
        mapping.inputs["Scale"].default_value = (tiles, tiles, 1.0)
        nt.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
        pore = tex(nt, tf["PoreSpec"], False, (-1300, -1300), "Pores (tiled)", mapping.outputs["Vector"])
        mask = tex(nt, tf["PoreMask"], False, (-1300, -1650), "PoreMask G")
        msep = separate(nt, mask.outputs["Color"], (-1000, -1650))
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-300, -1300)
        bump.inputs["Distance"].default_value = 0.02
        nt.links.new(math_node(nt, "MULTIPLY", msep.outputs["Green"], 0.25 * sc.get("PoreNMScale", 1.0), (-700, -1600)),
                     bump.inputs["Strength"])
        nt.links.new(pore.outputs["Color"], bump.inputs["Height"])
        if normal is not None:
            nt.links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs["Normal"]
        info["pores"] = tiles
    if normal is not None:
        nt.links.new(normal, bsdf.inputs["Normal"])
    info["alpha"] = apply_alpha(nt, mat, bsdf, bc.outputs["Alpha"] if bc else None, ov)


def build_hair(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc, vec, sw, ov = p["scalars"], p["vectors"], p["switches"], p["overrides"]
    root, tip = vec.get("RootColor", [1, 1, 1, 1]), vec.get("TipColor", [1, 1, 1, 1])
    bc = tex(nt, tf["Tex_BaseColor"], True, (-1300, 400), "Hair colour + strands") if tf.get("Tex_BaseColor") else None
    mm = sep = None
    if tf.get("Tex_Multi"):
        mm = tex(nt, tf["Tex_Multi"], False, (-1300, 0), "Multi B AO")
        sep = separate(nt, mm.outputs["Color"], (-1000, 0))
    if bc and sw.get("UseDiffuseBaseColor", True):
        # Brightness (Tifa 3.35) compensates UE's MSM_Hair, whose diffuse is far darker than a Lambert
        # lobe; applied in full to a Principled BSDF it turned black hair mid-grey.  Compressed:
        # 3.35 -> 1.2, 1 -> 1 (renders compared against the game's near-black hair, README).
        col = scale(nt, bc.outputs["Color"], max(sc.get("Brightness", 1.0), 0.01) ** HAIR_BRIGHTNESS_EXP,
                    (-900, 400))
        avg = [(a + b) / 2 for a, b in zip(root[:3], tip[:3])]
        if not is_white(avg):
            col = multiply(nt, col, avg, 1.0, (-700, 450))
    else:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.location = (-700, 450)
        mix.inputs[6].default_value = root
        mix.inputs[7].default_value = tip
        if sep:
            nt.links.new(sep.outputs["Green"], mix.inputs["Factor"])
        col = mix.outputs[2]
    if sep:
        col = multiply(nt, col, sep.outputs["Blue"], 0.7 * sc.get("Blend_AO_Int", 1.0), (-400, 400))
    feed(nt, col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = sc.get("Roughness", 0.45)
    # full Specular on hair cards mirrors the grey sky at every grazing strand
    bsdf.inputs["Specular"].default_value = min(1.0, HAIR_SPECULAR * sc.get("Specular", 0.5))
    if tf.get("Tex_BakedNormal"):
        nt.links.new(normal_map(nt, tf["Tex_BakedNormal"], sc.get("BakedNormal_Scale", 1.0)), bsdf.inputs["Normal"])
    alpha = bc.outputs["Alpha"] if bc and not sw.get("BCAlphaNotUse") else None
    info["alpha"] = apply_alpha(nt, mat, bsdf, alpha, ov, soft=True)


def build_eye(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc = p["scalars"]
    if tf.get("Tex_Colormap"):
        t = tex(nt, tf["Tex_Colormap"], True, (-900, 200), "Eye")
        col = t.outputs["Color"]
        if abs(sc.get("Eye_Blightness", 1.0) - 1.0) > 1e-3:
            col = scale(nt, col, sc["Eye_Blightness"], (-500, 200))
        feed(nt, col, bsdf.inputs["Base Color"])
    else:
        report["missing_textures"].append("%s: no Tex_Colormap" % mat.name)
    bsdf.inputs["Roughness"].default_value = 0.08
    bsdf.inputs["Specular"].default_value = 0.6
    info["alpha"] = "opaque"


def build_eyelash(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc, vec, ov = p["scalars"], p["vectors"], p["overrides"]
    tint = vec.get("Color_Tint", [1.0, 1.0, 1.0, 1.0])
    k = sc.get("Color_Int", 0.1)
    bc = tex(nt, tf["Tex_Color"], True, (-1000, 200), "Lashes") if tf.get("Tex_Color") else None
    if bc:
        col = multiply(nt, bc.outputs["Color"], [c * k for c in tint[:3]], 1.0, (-500, 250))
        feed(nt, col, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.03, 0.02, 0.02, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Specular"].default_value = 0.1
    info["alpha"] = apply_alpha(nt, mat, bsdf, bc.outputs["Alpha"] if bc else None,
                                {**ov, "BlendMode": ov.get("BlendMode", "BLEND_Masked")}, soft=True)


def build_glass(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    vec = p["vectors"]
    tint = vec.get("Color_Tint", [0.8, 0.85, 0.9, 1.0])
    col = tint
    if tf.get("Tex_Color"):
        col = multiply(nt, tex(nt, tf["Tex_Color"], True, (-900, 200), "Glass").outputs["Color"], tint, 1.0, (-500, 200))
    feed(nt, col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["Specular"].default_value = 0.9
    bsdf.inputs["Alpha"].default_value = 0.25
    mat.blend_method = "BLEND"
    mat.shadow_method = "NONE"
    mat.show_transparent_back = False
    info["alpha"] = "blend 0.25"


def build_gem(mat, p, tf, info):
    nt, bsdf = new_tree(mat)
    sc, vec = p["scalars"], p["vectors"]
    bsdf.inputs["Base Color"].default_value = tuple(vec.get("Color_Main", [0.2, 0.6, 0.3, 1.0])[:3]) + (1.0,)
    bsdf.inputs["Emission"].default_value = tuple(vec.get("Add to emissive", [0.0, 0.0, 0.0, 1.0])[:3]) + (1.0,)
    bsdf.inputs["Roughness"].default_value = sc.get("Roughness", 0.15)
    bsdf.inputs["Metallic"].default_value = sc.get("Metallic", 0.0)
    if tf.get("Normal"):
        nt.links.new(normal_map(nt, tf["Normal"], 1.0), bsdf.inputs["Normal"])
    info["alpha"] = "opaque"


BUILDERS = {"standard": build_standard, "skin": build_skin, "hair": build_hair, "eye": build_eye,
            "eyelash": build_eyelash, "glass": build_glass, "gem": build_gem}

materials = SPEC["materials"]
built = {}
for mesh in meshes + weapons:
    for slot in mesh.material_slots:
        mat = slot.material
        if mat is None:
            continue
        key = mat.name.rsplit(".", 1)[0] if mat.name.rsplit(".", 1)[-1].isdigit() else mat.name
        if key in built:
            continue
        p = materials.get(key)
        if p is None:
            report["warnings"].append("slot material %s has no instance data - left grey" % mat.name)
            built[key] = None
            continue
        tf = {k: v for k, v in (p.get("texture_files") or {}).items() if v and os.path.isfile(v)}
        info = {"family": p["family"], "chain": p.get("chain", [])[1:],
                "textures": sorted(os.path.basename(v) for v in tf.values())}
        BUILDERS.get(p["family"], build_standard)(mat, p, tf, info)
        report["materials_built"][key] = info
        built[key] = mat
        log("material %-40s %-8s %s" % (key, p["family"], info.get("alpha", "")))
    for poly in mesh.data.polygons:
        poly.use_smooth = True


# ---------------------------------------------------------------- previews
def world_bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def bone_pos(*names):
    for n in names:
        b = arm.data.bones.get(n)
        if b is not None:
            return arm.matrix_world @ b.head_local
    return None


def facing():
    """Horizontal direction the character faces (head -> nose bone), default -Y (Blender front)."""
    head, nose = bone_pos("Head", "head"), bone_pos("hi_nose", "nose", "Nose")
    if head is not None and nose is not None:
        d = nose - head
        d.z = 0.0
        if d.length > 1e-3:
            return d.normalized()
    return Vector((0.0, -1.0, 0.0))


lo, hi = world_bounds(meshes)
center = (lo + hi) / 2
size = hi - lo
height = max(size.z, 1e-3)
FORWARD = facing()
UP = Vector((0.0, 0.0, 1.0))
report["height_cm"] = round(height, 1)
report["facing"] = [round(c, 3) for c in FORWARD]


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_percentage = 100
    ee = scene.eevee
    ee.taa_render_samples = 64
    ee.use_gtao = True
    ee.gtao_distance = max(5.0, height * 0.08)
    ee.use_soft_shadows = True
    ee.shadow_cube_size = "2048"
    ee.shadow_cascade_size = "4096"
    ee.sss_samples = 9
    scene.view_settings.view_transform = "Filmic"
    world = bpy.data.worlds.get("CCFF7R_World") or bpy.data.worlds.new("CCFF7R_World")
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.42, 0.42, 0.45, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world


def add_lights(direction):
    side = direction.cross(UP).normalized()
    made = []
    for name, (f, s, z), energy in (("Key", (1.0, 0.8, 1.1), 3.2), ("Fill", (0.8, -1.0, 0.3), 1.2),
                                    ("Rim", (-1.0, -0.3, 0.9), 2.2)):
        data = bpy.data.lights.new("CCFF7R_" + name, "SUN")
        data.energy = energy
        data.angle = math.radians(8)
        data.shadow_cascade_max_distance = height * 6
        obj = bpy.data.objects.new("CCFF7R_" + name, data)
        bpy.context.scene.collection.objects.link(obj)
        d = (direction * f + side * s + UP * z).normalized()
        obj.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        made.append(obj)
    return made


def render(path, target, direction, frame, res):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = res
    cam_data = bpy.data.cameras.new("CCFF7R_Cam")
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "VERTICAL" if res[1] >= res[0] else "HORIZONTAL"
    cam_data.ortho_scale = frame
    dist = height * 4 + frame * 4
    cam_data.clip_start = 1.0
    cam_data.clip_end = dist * 3
    cam = bpy.data.objects.new("CCFF7R_Cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = target + direction * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    lights = add_lights(direction)
    scene.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    for obj in [cam] + lights:
        data, kind = obj.data, obj.type
        bpy.data.objects.remove(obj, do_unlink=True)
        (bpy.data.cameras if kind == "CAMERA" else bpy.data.lights).remove(data)
    log("rendered " + path)


def body_width(direction):
    side = direction.cross(UP).normalized()
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    return max(p.dot(side) for p in pts) - min(p.dot(side) for p in pts)


def body_res(direction):
    """Portrait for figures, landscape for swords / vehicles lying along the view."""
    return (1500, 1000) if body_width(direction) > height * 1.25 else (1000, 1500)


def body_frame(direction, res):
    """Ortho scale that fits the whole figure seen from `direction` in a res-shaped frame (the camera's
    sensor_fit follows the longer side of res, so the scale is measured along that side)."""
    width = body_width(direction)
    if res[1] >= res[0]:
        return max(height, width * res[1] / res[0]) * 1.06
    return max(width, height * res[0] / res[1]) * 1.06


def rotate(v, degrees):
    a = math.radians(degrees)
    return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a), 0.0)).normalized()


head_pos = bone_pos("Head", "head")
face_target = None
face_frame = max(20.0, min(80.0, height * 0.19))
if head_pos is not None:
    face_target = head_pos + UP * (face_frame * 0.18)

if SPEC.get("preview", True):
    setup_render()
    os.makedirs(OUT_DIR, exist_ok=True)
    for w in weapons:                      # a sword at the feet is not the character
        w.hide_render = True
    res = body_res(FORWARD)
    preview = os.path.join(OUT_DIR, MODEL_ID + "_preview.png")
    render(preview, center, FORWARD, body_frame(FORWARD, res), res)
    report["preview"] = preview
    if face_target is not None:
        face = os.path.join(OUT_DIR, MODEL_ID + "_face.png")
        render(face, face_target, FORWARD, face_frame, (900, 900))
        report["face"] = face
    if SPEC.get("views"):
        vdir = SPEC["views_dir"]
        for label, deg in (("front", 0), ("left34", 35), ("left", 90), ("back", 180), ("right", -90), ("right34", -35)):
            d = rotate(FORWARD, deg)
            res = body_res(d)
            render(os.path.join(vdir, "%s_%s.png" % (MODEL_ID, label)), center, d, body_frame(d, res), res)
        if face_target is not None:
            for label, deg in (("face_front", 0), ("face_left34", 35), ("face_right34", -35), ("face_side", 90)):
                render(os.path.join(vdir, "%s_%s.png" % (MODEL_ID, label)), face_target, rotate(FORWARD, deg),
                       face_frame, (900, 900))
        report["views_dir"] = vdir
else:
    setup_render()

# ---------------------------------------------------------------- viewport, pack, save
for w in weapons:
    w.hide_render = False
view_rot = FORWARD.to_track_quat("Z", "Y")
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type != "VIEW_3D":
                continue
            space.clip_start = 0.5
            space.clip_end = max(20000.0, height * 50)
            space.shading.type = "MATERIAL"
            r3d = space.region_3d
            if r3d is not None:
                r3d.view_location = center
                r3d.view_distance = height * 1.4
                r3d.view_rotation = view_rot
                r3d.view_perspective = "PERSP"

if SPEC.get("save", True):
    packed = 0
    for img in bpy.data.images:
        if img.source == "FILE" and img.packed_file is None and img.filepath:
            img.pack()
            packed += 1
    report["images_packed"] = packed
    os.makedirs(OUT_DIR, exist_ok=True)
    blend = os.path.join(OUT_DIR, MODEL_ID + ".blend")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False, compress=False)
    report["blend"] = blend
    report["blend_mb"] = round(os.path.getsize(blend) / 1048576, 1)
print("CCFF7R_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
