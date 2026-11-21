"""Blender 3.6, background: a Marvel Rivals skeletal mesh (CUE4Parse .psk/.pskx) + its materials (spec JSON from
export_mod.py) -> a .blend with the game's full materials, optionally with preview renders.

    blender -b --factory-startup --python build_blend.py -- --spec spec.json --out OUT.blend [--preview DIR]

spec.json: {"name", "psk", "scale": 0.01, "materials": {slot: {"textures": {param: png}, "scalars": {},
            "vectors": {}, "blend_mode": "", "clip": 0.333, "two_sided": false, "path": mi path}}}

Materials (the game's character shaders, parameter names as the material instances use them):
  BaseColor / Diffuse / Albedo        -> Base Color (alpha cuts out only when the blend mode is Masked AND the alpha
                                         really has transparent texels)
  Normal                              -> Normal Map (UE = DirectX: green flipped)
  ORM (also SRMH-style packs in that slot) -> R ambient occlusion (multiplied into the colour), G roughness, B metallic
  SpecularTexture / Specular          -> Specular (R channel)
  Emissive*                           -> Emission
The parameter name decides first; a texture name suffix (_D / _N / _ORM ...) only fills a role still empty, and
effect / detail parameters (FX ... NoiseTex, FlowMapNormal, NormalMask_Tex, <id>_BaseNoiseTex ...) never do.
Slots whose material instance is not in the mod nor in an installed game get a flat grey and are listed in the report.
UE centimetres -> metres; the rig is turned to face -Y by the direction its toes point.
"""
import json
import math
import os
import re
import shutil
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


with open(arg("--spec"), encoding="utf-8") as fh:
    SPEC = json.load(fh)
OUT = os.path.abspath(arg("--out"))
PREVIEW = arg("--preview")
NAME = SPEC.get("name") or os.path.splitext(os.path.basename(OUT))[0]
SCALE = float(SPEC.get("scale", 0.01))
MISSING_GREY = (0.35, 0.35, 0.37, 1.0)

ROLE_RE = [
    ("basecolor", re.compile(r"^(base_?colou?r|diffuse|albedo|color|basecolor_?tex(ture)?|_?maintex)$|^d$|_d$", re.I)),
    ("normal", re.compile(r"^(normal(_?map|_?tex(ture)?)?|_?bumpmap)$|^n$", re.I)),
    ("orm", re.compile(r"^(orm|mro|rma|arm|mask|srmh|occlusion_?roughness_?metal(lic)?)$", re.I)),
    ("specular", re.compile(r"^specular(_?tex(ture)?|_?map)?$|^s$", re.I)),
    ("emissive", re.compile(r"emissi|emiss|glow", re.I)),
    ("opacity", re.compile(r"^(opacity|alpha)(_?mask)?$", re.I)),
]
SUFFIX_ROLE = [("basecolor", re.compile(r"_(d|bc|col|colo[rh]?|albedo|diffuse)$", re.I)),
               ("normal", re.compile(r"_(n|nrm|normal|norma[h]?)$", re.I)),
               ("orm", re.compile(r"_(orm|mro|rma|arm|srmh|m)$", re.I)),
               ("specular", re.compile(r"_(s|spec)$", re.I)),
               ("emissive", re.compile(r"_(e|em|emissive)$", re.I))]


def log(msg):
    print("[mr] " + msg, flush=True)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# Effect / detail / mask parameters hold textures whose names end in _D / _N / _M as well (Venom:
# "FX - ChangeColor - NoiseTex" = T_1035103_Noise_26_001_D, "FlowMapNormal", "NormalMask_Tex", "103561_BaseNoiseTex",
# "VenousGrowthPath"); they never stand in for the base colour / normal / ORM.
EFFECT_PARAM_RE = re.compile(r"fx|noise|flow|growth|venous|mask_?tex|detail|ramp|matcap|rim|dissolve|^\d{4,}_", re.I)


def param_role(param):
    for role, rx in ROLE_RE:
        if rx.search(param):
            return role
    return None


def suffix_role(tex_path):
    stem = re.sub(r"_\d{5,}$", "", os.path.splitext(os.path.basename(tex_path))[0])   # <name>_<path id>.png
    for role, rx in SUFFIX_ROLE:
        if rx.search(stem):
            return role
    return None


def assign_roles(textures):
    """role -> (param, texture).  The parameter's own name decides first (BaseColor / Normal / ORM ...); a texture's
    name suffix (_D / _N / _ORM) only fills roles that are still empty, and never from effect / detail parameters.
    2026-11-21: Venom's instances list "FX - ChangeColor - NoiseTex", "FlowMapNormal" and "NormalMask_Tex" before
    BaseColor / Normal / ORM, and first-come-first-served by suffix painted the whole body with a green noise map."""
    roles = {}
    for param, path in textures.items():
        role = param_role(param)
        if role and role not in roles:
            roles[role] = (param, path)
    for param, path in textures.items():
        if EFFECT_PARAM_RE.search(param):
            continue
        role = suffix_role(path)
        if role and role not in roles:
            roles[role] = (param, path)
    return roles


bpy.ops.wm.read_factory_settings(use_empty=True)
import addon_utils  # noqa: E402

if addon_utils.enable("io_scene_psk_psa", default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for this Blender")
before = set(bpy.data.objects)
if SPEC.get("fbx"):        # e.g. a Unity prefab exported by AssetStudio (HS2 studio items)
    bpy.ops.import_scene.fbx(filepath=SPEC["fbx"], automatic_bone_orientation=False, ignore_leaf_bones=False,
                             use_custom_normals=True)
else:
    bpy.ops.import_scene.psk(filepath=SPEC["psk"], should_import_vertex_colors=False,
                             should_import_vertex_normals=True, should_import_extra_uvs=True, should_import_mesh=True,
                             should_import_materials=True, should_reuse_materials=True, should_import_skeleton=True,
                             should_import_shape_keys=True, bone_length=2.0)
created = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in created if o.type == "ARMATURE")
meshes = [o for o in created if o.type == "MESH"]
if SPEC.get("fbx") and arm.scale.x < 0.1:
    # AssetStudio puts the prefab's x0.01 on the armature object and x100 on the meshes under it: the skin comes out
    # right but the bones are 100x too small for it, so every pose pivots in the wrong place.  The armature goes to
    # scale 1 (bones in the same units as the skin) and the meshes keep their world placement.
    keep = {m.name: m.matrix_world.copy() for m in meshes}
    arm.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    for m in meshes:
        m.matrix_world = keep[m.name]
    bpy.context.view_layer.update()
arm.name = arm.data.name = NAME + "_rig"
for i, m in enumerate(meshes):
    m.name = m.data.name = NAME if i == 0 else "%s_%d" % (NAME, i)
log("imported: %d bones, %d meshes, %d vertices" % (len(arm.data.bones), len(meshes),
                                                    sum(len(m.data.vertices) for m in meshes)))


def side_bone(patterns, side):
    for b in arm.data.bones:
        for p in patterns:
            if re.fullmatch(p % {"s": side, "S": side.upper()}, b.name):
                return b
    return None


FOOT = (r"foot_%(s)s", r"(DEF-)?foot[._]%(S)s", r"(DEF-)?foot[._]%(s)s")
TOE = (r"ball_%(s)s", r"(DEF-)?toe[._]%(S)s", r"(DEF-)?toe[._]%(s)s", r"(DEF-)?toe(_\d+)?[._]%(S)s")


def toe_direction():
    """XY direction foot -> toe (average of both feet), in armature space."""
    dirs = []
    for s in ("l", "r"):
        foot, ball = side_bone(FOOT, s), side_bone(TOE, s)
        if foot and ball:
            d = ball.head_local - foot.head_local
            dirs.append(Vector((d.x, d.y, 0.0)))
    if not dirs:
        return None
    v = sum(dirs, Vector())
    return v.normalized() if v.length > 1e-6 else None


d = toe_direction()
angle = 0.0
if d is not None:
    # rotate about Z so the toes point to -Y
    angle = math.atan2(-1.0, 0.0) - math.atan2(d.y, d.x)
arm.scale = arm.scale * SCALE if SPEC.get("fbx") else Vector((SCALE, SCALE, SCALE))
arm.rotation_euler.z += angle          # an FBX root keeps its own (Y-up -> Z-up) X rotation
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
for m in meshes:
    m.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.context.view_layer.update()
pts = [m.matrix_world @ v.co for m in meshes for v in m.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
log("turned %.0f deg, bounds %s .. %s, height %.3f m" % (math.degrees(angle), tuple(round(c, 3) for c in lo),
                                                          tuple(round(c, 3) for c in hi), hi.z - lo.z))

def joint_check():
    """Each skinned bone's head vs the weighted centre of the skin it carries (metres, mean / worst) - a skeleton in
    other units than its mesh, or wrong bone rotations, show here before anything is posed."""
    acc = {}
    for m in meshes:
        names = {g.index: g.name for g in m.vertex_groups}
        for v in m.data.vertices:
            p = m.matrix_world @ v.co
            for g in v.groups:
                if g.weight > 0:
                    a = acc.setdefault(names[g.group], [Vector(), 0.0])
                    a[0] += p * g.weight
                    a[1] += g.weight
    errs = {}
    for name, (sm, w) in acc.items():
        b = arm.data.bones.get(name)
        if b is not None and w >= 50:
            errs[name] = ((arm.matrix_world @ b.head_local) - sm / w).length
    if not errs:
        return {}
    worst = max(errs, key=errs.get)
    return {"joints": len(errs), "mean_m": round(sum(errs.values()) / len(errs), 3), "worst": worst,
            "worst_m": round(errs[worst], 3)}


JOINTS = joint_check()
log("joint check: %s" % JOINTS)
out_dir = os.path.dirname(OUT)
tex_out = os.path.join(out_dir, "textures")
os.makedirs(tex_out, exist_ok=True)


def image(path, colour):
    if not path or not os.path.isfile(path):
        return None
    dst = os.path.join(tex_out, os.path.basename(path))
    if os.path.normcase(os.path.abspath(path)) != os.path.normcase(dst) and (
            not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(path)):
        shutil.copy2(path, dst)
    img = bpy.data.images.load(dst, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


HAIRLIKE = re.compile(r"hair|lash|brow|fur|feather|lace|fringe|tassel", re.I)
FX_RE = re.compile(r"rim_?hero|herodetail|rimonly|outline|eyesfx|_fx$|vfx", re.I)


def is_dxt5nm(img, step=97):
    """Red ~1 everywhere while alpha varies: a Unity DXT5nm-packed normal map."""
    if img is None or img.channels < 4:
        return False
    import numpy as np
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    r, a = px[0::4][::step], px[3::4][::step]
    return bool(len(r)) and float(r.mean()) > 0.95 and float(a.std()) > 0.02


def alpha_share(img, cut=0.33, step=7):
    """Share of the colour map's texels with alpha below `cut` (sampled every `step` texels)."""
    if img is None or img.channels < 4:
        return 0.0
    import numpy as np
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    a = px[3::4][::step]
    return float((a < cut).mean()) if len(a) else 0.0


def build_material(mat, spec):
    nt = mat.node_tree if mat.use_nodes else None
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links

    def node(kind, x, y, label=None):
        n = N.new(kind)
        n.location = (x, y)
        if label:
            n.label = label
        return n

    out = node("ShaderNodeOutputMaterial", 700, 0)
    bsdf = node("ShaderNodeBsdfPrincipled", 350, 0)
    L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    roles = assign_roles(spec.get("textures", {}))
    used = {}
    if FX_RE.search(mat.name) and "basecolor" not in roles:
        # rim-light / effect shells (M_RimOnly, *_HeroDetails ...) are drawn by special shaders around the body;
        # as a plain surface they would cover it, so they stay in the file, invisible
        bsdf.inputs["Alpha"].default_value = 0.0
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"
        return {"hidden": "effect shell"}
    flat = spec.get("flat")           # export_mod.py --colour: a stand-in for a colour map the game could not give
    if flat:
        bsdf.label = "替身颜色（游戏贴图没读出来，--colour）"
        bsdf.inputs["Base Color"].default_value = (*[srgb_to_linear(c) for c in flat[:3]], 1.0)
        bsdf.inputs["Roughness"].default_value = flat[3]
    if not roles:
        if not flat:
            bsdf.inputs["Base Color"].default_value = MISSING_GREY
            bsdf.inputs["Roughness"].default_value = 0.6
        return {"missing": True, "flat": flat}
    base = None
    if "basecolor" in roles:
        img = image(roles["basecolor"][1], True)
        if img:
            base = node("ShaderNodeTexImage", -700, 300, roles["basecolor"][0])
            base.image = img
            used["basecolor"] = img.name
    colour_out = base.outputs["Color"] if base else None
    if "orm" in roles:
        img = image(roles["orm"][1], False)
        if img:
            t = node("ShaderNodeTexImage", -700, -50, roles["orm"][0])
            t.image = img
            sep = node("ShaderNodeSeparateRGB", -400, -50)
            L.new(t.outputs["Color"], sep.inputs["Image"])
            L.new(sep.outputs["G"], bsdf.inputs["Roughness"])
            L.new(sep.outputs["B"], bsdf.inputs["Metallic"])
            if colour_out is not None:
                ao = node("ShaderNodeMixRGB", -150, 250, "x AO (ORM R)")
                ao.blend_type = "MULTIPLY"
                ao.inputs["Fac"].default_value = 1.0
                L.new(colour_out, ao.inputs["Color1"])
                L.new(sep.outputs["R"], ao.inputs["Color2"])
                colour_out = ao.outputs["Color"]
            used["orm"] = img.name
    elif not flat:
        bsdf.inputs["Roughness"].default_value = 0.55
    if colour_out is not None:
        L.new(colour_out, bsdf.inputs["Base Color"])
    elif not flat:
        bsdf.inputs["Base Color"].default_value = MISSING_GREY
    if "normal" in roles:
        img = image(roles["normal"][1], False)
        if img:
            t = node("ShaderNodeTexImage", -1000, -400, roles["normal"][0])
            t.image = img
            sep = node("ShaderNodeSeparateRGB", -720, -400)
            opengl = "opengl" in os.path.basename(roles["normal"][1]).lower()
            inv = node("ShaderNodeMath", -540, -430, "OpenGL 法线：不翻转" if opengl else "UE 法线：绿通道翻转")
            inv.operation = "ADD" if opengl else "SUBTRACT"
            inv.inputs[0].default_value = 0.0 if opengl else 1.0
            comb = node("ShaderNodeCombineRGB", -360, -400)
            nm = node("ShaderNodeNormalMap", -180, -400)
            L.new(t.outputs["Color"], sep.inputs["Image"])
            if is_dxt5nm(img):
                # Unity "DXT5nm": X in alpha, Y in green, red 1 (the textures of HS2 bundles); Z = 1, the Normal Map
                # node normalises
                img.alpha_mode = "CHANNEL_PACKED"
                L.new(t.outputs["Alpha"], comb.inputs["R"])
                comb.inputs["B"].default_value = 1.0
                L.new(sep.outputs["G"], inv.inputs[1])
                L.new(inv.outputs["Value"], comb.inputs["G"])
                L.new(comb.outputs["Image"], nm.inputs["Color"])
                L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
                used["normal"] = img.name + " (DXT5nm)"
                img = None
        if img:
            L.new(sep.outputs["R"], comb.inputs["R"])
            L.new(sep.outputs["G"], inv.inputs[1])
            L.new(inv.outputs["Value"], comb.inputs["G"])
            comb.inputs["B"].default_value = 1.0
            L.new(sep.outputs["B"], comb.inputs["B"])
            L.new(comb.outputs["Image"], nm.inputs["Color"])
            L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
            used["normal"] = img.name
    if "specular" in roles:
        img = image(roles["specular"][1], False)
        if img:
            t = node("ShaderNodeTexImage", -700, -700, roles["specular"][0])
            t.image = img
            sep = node("ShaderNodeSeparateRGB", -400, -700)
            L.new(t.outputs["Color"], sep.inputs["Image"])
            L.new(sep.outputs["R"], bsdf.inputs["Specular"])
            used["specular"] = img.name
    if "emissive" in roles:
        img = image(roles["emissive"][1], True)
        if img:
            t = node("ShaderNodeTexImage", -700, 600, roles["emissive"][0])
            t.image = img
            L.new(t.outputs["Color"], bsdf.inputs["Emission"])
            bsdf.inputs["Emission Strength"].default_value = 1.0
            used["emissive"] = img.name
    # Cut-out only when the material says Masked.  An instance that merely overrides OpacityMaskClipValue (every Marvel
    # Rivals instance does) is not masked by that; when the blend mode is unknown (parent not available) hair-like
    # materials whose colour map really has transparent texels are cut out.
    # With current mappings the parents' blend modes come through, and Marvel Rivals' skin / body parents are all
    # Masked (M_Common_Body, M_1035001_Skin_1035 - for dissolve effects) while their colour maps are opaque: cut out
    # only when the colour map's alpha really has transparent texels.
    blend = str(spec.get("blend_mode", "")).lower()
    share = alpha_share(base.image) if base is not None else 0.0
    masked = blend.endswith("masked") and share > 0.001
    if not blend and base is not None and HAIRLIKE.search(mat.name) and share > 0.02:
        masked = True
    if masked and base is not None:
        L.new(base.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "CLIP"
        mat.shadow_method = "CLIP"
        mat.alpha_threshold = float(spec.get("clip") or 0.3333)
    mat.use_backface_culling = not spec.get("two_sided", False)
    mat["mr_instance"] = spec.get("path", "")
    return {"used": used, "masked": bool(masked and base is not None)}


report = {"materials": {}, "missing": []}
specs = {k.lower(): v for k, v in SPEC.get("materials", {}).items()}
for m in meshes:
    for slot in m.material_slots:
        mat = slot.material
        if mat is None or mat.name in report["materials"]:
            continue
        spec = specs.get(mat.name.lower()) or specs.get(re.sub(r"\.\d+$", "", mat.name).lower())
        if spec is None:
            spec = {}
        res = build_material(mat, spec)
        report["materials"][mat.name] = res
        if res.get("missing"):
            report["missing"].append(mat.name)
        log("material %s: %s" % (mat.name, res))
for m in meshes:
    for poly in m.data.polygons:
        poly.use_smooth = True
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
world = bpy.data.worlds.new("World")
world.use_nodes = True
scene.world = world
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.16, 0.17, 0.19, 1)
bg.inputs["Strength"].default_value = 0.6
os.makedirs(out_dir, exist_ok=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=OUT, relative_remap=True, compress=True)
log("saved " + OUT)


def look_at(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_views(folder):
    os.makedirs(folder, exist_ok=True)
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_gtao = True
    scene.eevee.use_ssr = True
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    centre = (lo + hi) / 2
    height = hi.z - lo.z

    def light(name, energy, loc, size, colour=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.color, ld.size = energy, colour, size
        ob = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(ob)
        ob.location = loc
        look_at(ob, centre)

    k = max(height / 1.7, 0.5)
    light("key", 300 * k * k, centre + Vector((-1.6, -2.6, 1.6)) * k, 1.2 * k)
    light("fill", 90 * k * k, centre + Vector((2.2, -1.8, 0.3)) * k, 2.0 * k, (0.85, 0.9, 1.0))
    light("rim", 320 * k * k, centre + Vector((0.8, 2.6, 1.4)) * k, 1.0 * k, (0.75, 0.85, 1.0))
    cam_data = bpy.data.cameras.new("preview_cam")
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    files = []
    for name, d in [("front", Vector((0, -1, 0))), ("three_quarter", Vector((-0.7, -0.7, 0)).normalized()),
                    ("side", Vector((1, 0, 0))), ("back", Vector((0, 1, 0)))]:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(height, hi.x - lo.x, hi.y - lo.y) * 1.08
        cam.location = centre + d * 5.0 * k
        look_at(cam, centre)
        scene.render.resolution_x, scene.render.resolution_y = 1100, 1500
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    head = arm.data.bones.get("head")
    hc = (arm.matrix_world @ head.head_local) if head else Vector((centre.x, centre.y, hi.z - 0.15 * k))
    hc = hc + Vector((0, 0, 0.06 * k))
    cam_data.type = "PERSP"
    cam_data.lens = 85
    scene.render.resolution_x = scene.render.resolution_y = 1200
    for name, d in [("head_front", Vector((0, -1, 0.1))), ("head_three_quarter", Vector((-0.75, -0.65, 0.1))),
                    ("head_side", Vector((1, 0, 0.1))), ("head_back", Vector((0.2, 1, 0.25)))]:
        cam.location = hc + d.normalized() * 1.0 * k
        look_at(cam, hc)
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    return files


previews = render_views(os.path.abspath(PREVIEW)) if PREVIEW else []
print("BUILD_DONE=" + json.dumps({"blend": OUT, "vertices": sum(len(m.data.vertices) for m in meshes),
                                  "faces": sum(len(m.data.polygons) for m in meshes), "bones": len(arm.data.bones),
                                  "height_m": round(hi.z - lo.z, 3), "turned_deg": round(math.degrees(angle), 1), "joint_check": JOINTS,
                                  "materials": report["materials"], "missing_materials": report["missing"],
                                  "previews": previews}, ensure_ascii=False))
