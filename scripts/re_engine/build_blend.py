"""Blender 3.6, background: the FBX + material JSON from import_re_mesh.py (Blender 4.5 + RE Mesh Editor) -> a .blend
with the RE Engine materials rebuilt, and preview renders.

    blender -b --factory-startup --python build_blend.py -- --fbx X.fbx --json X.json --textures DIR --out OUT.blend
            [--name N] [--preview DIR] [--colour MATERIAL=r,g,b ...]

Texture bindings (RE Engine, as RE Mesh Editor reads them):
  BaseMetalMap  ALBM  RGB colour, A metallic          BaseAlphaMap / BaseMap  ALBA / ALB  colour (A alpha)
  NormalRoughnessMap  NRMR  RGB normal (OpenGL - no flip), A roughness   NormalMap  normal   RoughnessMap  roughness
  AlphaTranslucentOcclusionSSSMap  ATOS  R alpha, G translucency, B ambient occlusion, A cavity
Masters: *Cornea / *Tear / *EyeShadow -> invisible glass shells; Hair -> cut-out from ATOS alpha.  A material whose
colour map is not in the mod (it lives in the game's paks) gets a flat colour: --colour NAME=r,g,b (sRGB 0-1), else a
grey; the report lists them.
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


def args(flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


FBX, OUT, TEX_DIR = arg("--fbx"), os.path.abspath(arg("--out")), arg("--textures")
NAME = arg("--name") or os.path.splitext(os.path.basename(OUT))[0]
PREVIEW = arg("--preview")
with open(arg("--json"), encoding="utf-8") as fh:
    INFO = json.load(fh)
COLOURS = {}
for c in args("--colour"):
    k, v = c.split("=", 1)
    COLOURS[k.lower()] = tuple(float(x) for x in v.split(","))
GLASS_RE = re.compile(r"cornea|tear|eyeshadow|eye_?shadow|wet", re.I)
HAIR_RE = re.compile(r"(^|/)hair", re.I)


def log(msg):
    print("[re] " + msg, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX, use_custom_normals=True, automatic_bone_orientation=False,
                         ignore_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
arm.name = NAME + "_rig"
log("imported %d meshes, %d bones" % (len(meshes), len(arm.data.bones)))


def toes():
    b = arm.data.bones
    dirs = []
    for s in ("l", "r"):
        a, t = b.get("%s_leg_ankle" % s), b.get("%s_leg_ball" % s)
        if a and t:
            d = (arm.matrix_world @ t.head_local) - (arm.matrix_world @ a.head_local)
            dirs.append(Vector((d.x, d.y, 0)))
    v = sum(dirs, Vector()) if dirs else None
    return v.normalized() if v is not None and v.length > 1e-6 else None


d = toes()
angle = (math.atan2(-1.0, 0.0) - math.atan2(d.y, d.x)) if d is not None else 0.0
if abs(angle) > 1e-3:
    arm.rotation_euler.z += angle
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
for m in meshes:
    m.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
pts = [m.matrix_world @ v.co for m in meshes for v in m.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
log("turned %.0f deg, height %.3f m" % (math.degrees(angle), hi.z - lo.z))

out_dir = os.path.dirname(OUT)
tex_out = os.path.join(out_dir, "textures")
os.makedirs(tex_out, exist_ok=True)


def image(binding, colour, packed_alpha=False):
    """binding -> the PNG export_mod.py converted (TEX_DIR/<texture name>.png) loaded from beside the .blend."""
    if not binding or not binding.get("dds"):
        return None
    stem = os.path.splitext(os.path.basename(binding["dds"]))[0]
    src = os.path.join(TEX_DIR, stem + ".png")
    if not os.path.isfile(src):
        return None
    dst = os.path.join(tex_out, stem + ".png")
    if not os.path.isfile(dst):
        shutil.copy2(src, dst)
    img = bpy.data.images.load(dst, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    # ALBM keeps metalness, NRMR roughness, ATOS a cavity mask in alpha - data, not transparency.  As STRAIGHT alpha
    # Blender multiplies the colour by it: the PMX bake of Jill's face (ALBM alpha 0.28 on average) came out black.
    if packed_alpha:
        img.alpha_mode = "CHANNEL_PACKED"
    return img


def build(mat, spec):
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
    t = spec.get("textures", {})
    master = spec.get("master", "")
    res = {"master": master.split("/")[-1], "used": []}
    if GLASS_RE.search(master) or GLASS_RE.search(mat.name):
        bsdf.inputs["Alpha"].default_value = 0.0
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"
        res["shell"] = True
        return res

    def tex(binding, colour, x, y, label):
        img = image(t.get(binding), colour, packed_alpha=binding not in ("BaseAlphaMap", "BaseMap"))
        if img is None:
            return None
        n = node("ShaderNodeTexImage", x, y, label)
        n.image = img
        res["used"].append(binding)
        return n

    colour = None
    for b in ("BaseMetalMap", "BaseAlphaMap", "BaseMap", "BaseDielectricMap"):
        n = tex(b, True, -700, 300, b)
        if n:
            colour = n
            if b == "BaseMetalMap":
                L.new(n.outputs["Alpha"], bsdf.inputs["Metallic"])
            break
    col_out = colour.outputs["Color"] if colour else None
    atos = tex("AlphaTranslucentOcclusionSSSMap", False, -700, -350, "ATOS")
    alpha_src = None
    if atos:
        sep = node("ShaderNodeSeparateRGB", -420, -350)
        L.new(atos.outputs["Color"], sep.inputs["Image"])
        if col_out is not None:
            ao = node("ShaderNodeMixRGB", -150, 250, "x AO (ATOS B)")
            ao.blend_type = "MULTIPLY"
            ao.inputs["Fac"].default_value = 1.0
            L.new(col_out, ao.inputs["Color1"])
            L.new(sep.outputs["B"], ao.inputs["Color2"])
            col_out = ao.outputs["Color"]
        alpha_src = sep.outputs["R"]
    if col_out is not None:
        L.new(col_out, bsdf.inputs["Base Color"])
    else:
        c = COLOURS.get(mat.name.lower()) or COLOURS.get(res["master"].split(".")[0].lower()) or (0.5, 0.5, 0.52)
        lin = [((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c[:3]]
        bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
        res["flat_colour"] = c
    nrm = tex("NormalRoughnessMap", False, -700, -50, "NRMR") or tex("NormalMap", False, -700, -50, "NormalMap")
    if nrm:
        nm = node("ShaderNodeNormalMap", -150, -50)
        L.new(nrm.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        if "NormalRoughnessMap" in res["used"]:
            L.new(nrm.outputs["Alpha"], bsdf.inputs["Roughness"])
    rgh = tex("RoughnessMap", False, -700, -650, "RoughnessMap")
    if rgh:
        L.new(rgh.outputs["Color"], bsdf.inputs["Roughness"])
    if HAIR_RE.search(master):
        a = alpha_src if alpha_src is not None else (colour.outputs["Alpha"] if colour and "BaseAlphaMap" in res["used"] else None)
        if a is not None:
            L.new(a, bsdf.inputs["Alpha"])
            mat.blend_method = "CLIP"
            mat.shadow_method = "CLIP"
            mat.alpha_threshold = 0.5
            res["cutout"] = True
        bsdf.inputs["Roughness"].default_value = 0.45
    elif "BaseAlphaMap" in res["used"] and colour is not None:
        L.new(colour.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "CLIP"
        mat.shadow_method = "CLIP"
        mat.alpha_threshold = 0.5
        res["cutout"] = True
    if re.search(r"skin", master, re.I):
        bsdf.inputs["Subsurface"].default_value = 0.03
        bsdf.inputs["Subsurface Color"].default_value = (0.8, 0.35, 0.25, 1)
    mat["re_master"] = master
    return res


report = {"materials": {}, "flat": []}
specs = {k.lower(): v for k, v in INFO.get("materials", {}).items()}
for m in meshes:
    for slot in m.material_slots:
        mat = slot.material
        if mat is None or mat.name in report["materials"]:
            continue
        key = re.sub(r"\.\d{3}$", "", mat.name).lower()
        spec = specs.get(key, {})
        res = build(mat, spec)
        report["materials"][mat.name] = res
        if "flat_colour" in res:
            report["flat"].append(mat.name)
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
for img in list(bpy.data.images):      # the FBX's own texture references (rebuilt above from the PNGs)
    if img.users == 0:
        bpy.data.images.remove(img)
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

    light("key", 300, centre + Vector((-1.6, -2.6, 1.6)), 1.2)
    light("fill", 90, centre + Vector((2.2, -1.8, 0.3)), 2.0, (0.85, 0.9, 1.0))
    light("rim", 320, centre + Vector((0.8, 2.6, 1.4)), 1.0, (0.75, 0.85, 1.0))
    cam_data = bpy.data.cameras.new("preview_cam")
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    files = []
    for name, dvec in [("front", Vector((0, -1, 0))), ("three_quarter", Vector((-0.7, -0.7, 0)).normalized()),
                       ("side", Vector((1, 0, 0))), ("back", Vector((0, 1, 0)))]:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(height, hi.x - lo.x, hi.y - lo.y) * 1.08
        cam.location = centre + dvec * 5.0
        look_at(cam, centre)
        scene.render.resolution_x, scene.render.resolution_y = 1100, 1500
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    head = arm.data.bones.get("head")
    hc = (arm.matrix_world @ head.head_local) if head else Vector((centre.x, centre.y, hi.z - 0.15))
    hc = hc + Vector((0, 0, 0.06))
    cam_data.type = "PERSP"
    cam_data.lens = 85
    scene.render.resolution_x = scene.render.resolution_y = 1200
    for name, dvec in [("head_front", Vector((0, -1, 0.1))), ("head_three_quarter", Vector((-0.75, -0.65, 0.1))),
                       ("head_side", Vector((1, 0, 0.1))), ("head_back", Vector((0.2, 1, 0.25)))]:
        cam.location = hc + dvec.normalized() * 1.0
        look_at(cam, hc)
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    return files


previews = render_views(os.path.abspath(PREVIEW)) if PREVIEW else []
print("BUILD_DONE=" + json.dumps({"blend": OUT, "vertices": sum(len(m.data.vertices) for m in meshes),
                                  "bones": len(arm.data.bones), "height_m": round(hi.z - lo.z, 3),
                                  "turned_deg": round(math.degrees(angle), 1), "materials": report["materials"],
                                  "flat_materials": report["flat"], "previews": previews}, ensure_ascii=False))
