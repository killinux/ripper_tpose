"""Blender 3.6, background: PSK + PNG textures + material parameters (materials.json) -> a ready .blend, optionally
with preview renders.  Called by export_upk.py; can be run alone:

    blender -b --factory-startup --python build_blend.py -- --psk X.psk --textures DIR --materials materials.json
            --out OUT.blend [--preview DIR] [--name Gwenom] [--scale 0.018] [--spec-scale 0.025] [--keep-orientation]

Materials follow the game's character shader (chbasematerials_v2 / chbasematerial_v2-1, custom lighting model):
  diffusetex                               -> Base Color
  normaltex                                -> Normal Map (UE / DirectX: green flipped), strength = normalstrength
  specmult_specpow_skinmask_reflectivity   -> R channel = specular mask
  speccolortex x speccolorvalue            -> colour of the specular
  emissive x emissivemultiplier            -> Emission
The game lights these with diffuse + coloured Blinn-Phong + rim, so the Blender material is a Principled BSDF (diffuse,
low neutral specular) plus a Glossy BSDF carrying the coloured specular (spec map x colour x mask x specmult x
--spec-scale), joined by an Add Shader.  Roughness from specularpower: alpha = sqrt(2 / (n + 2)), roughness = sqrt(alpha).
"""
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


PSK = os.path.abspath(arg("--psk"))
TEX_DIR = os.path.abspath(arg("--textures"))
with open(arg("--materials"), encoding="utf-8") as fh:
    MATERIALS = json.load(fh)
OUT = os.path.abspath(arg("--out"))
PREVIEW = arg("--preview")
NAME = arg("--name", os.path.splitext(os.path.basename(PSK))[0])
# game units -> metres.  Marvel Heroes characters are ~93 units tall; 0.018 makes Gwenom 1.68 m.
SCALE = float(arg("--scale", "0.018"))
# The game's Blinn-Phong is not energy-normalised, Blender's GGX is: the same colour gives a ~5x brighter peak in
# Blender (the mask turned pale blue under a soft box).  specmult x 0.025 (20 -> 0.5, 1 -> 0.03) keeps the game's
# ratios between materials and matches the mod's own store picture: black mask, white eyes.
SPEC_SCALE = float(arg("--spec-scale", "0.025"))
FACE_MINUS_Y = "--keep-orientation" not in argv  # the game's forward is +X; Blender / MMD front is -Y
NORMAL_STRENGTH = 1.0  # when an instance does not override normalstrength


def log(msg):
    print("[mho] " + msg, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
import addon_utils  # noqa: E402

if addon_utils.enable("io_scene_psk_psa", default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for this Blender (needed to import the .psk)")

before = set(bpy.data.objects)
bpy.ops.import_scene.psk(filepath=PSK, should_import_vertex_colors=False, should_import_vertex_normals=True,
                         should_import_extra_uvs=True, should_import_mesh=True, should_import_materials=True,
                         should_reuse_materials=True, should_import_skeleton=True, should_import_shape_keys=True,
                         bone_length=2.0)
created = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in created if o.type == "ARMATURE")
mesh = next(o for o in created if o.type == "MESH")
arm.name = arm.data.name = NAME + "_rig"
mesh.name = mesh.data.name = NAME
log("imported: %d bones, %d vertices, %d faces" % (len(arm.data.bones), len(mesh.data.vertices), len(mesh.data.polygons)))

# ---- scale + orientation, applied to the armature and the mesh
arm.scale = (SCALE, SCALE, SCALE)
if FACE_MINUS_Y:
    arm.rotation_euler = (0.0, 0.0, -math.pi / 2)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
mesh.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.context.view_layer.update()
pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
log("bounds %s .. %s, height %.3f m" % (tuple(round(c, 3) for c in lo), tuple(round(c, 3) for c in hi), hi.z - lo.z))


def joint_check():
    """Each skinned bone's head vs the weighted centre of its own skin (metres).  A skeleton that does not match the
    bind pose shows here at once (the first Gwenom export had the wrist 0.65 m off and posed fingers as spikes)."""
    acc = {}
    names = {g.index: g.name for g in mesh.vertex_groups}
    for v, p in zip(mesh.data.vertices, pts):
        for g in v.groups:
            a = acc.setdefault(names[g.group], [Vector(), 0.0])
            a[0] += p * g.weight
            a[1] += g.weight
    errs = {}
    for name, (s, w) in acc.items():
        b = arm.data.bones.get(name)
        if b is None or w < 50:
            continue
        errs[name] = ((arm.matrix_world @ b.head_local) - s / w).length
    if not errs:
        return {}
    worst = max(errs, key=errs.get)
    return {"joints": len(errs), "mean_m": round(sum(errs.values()) / len(errs), 3), "worst": worst,
            "worst_m": round(errs[worst], 3)}


JOINTS = joint_check()
log("joint check: %s" % JOINTS)
if JOINTS.get("mean_m", 0) > 0.2:
    log("WARNING: the bones sit far from the skin they move - posing will tear the mesh")

# ---- textures, copied next to the .blend (relative paths)
out_dir = os.path.dirname(OUT)
tex_out = os.path.join(out_dir, "textures")
os.makedirs(tex_out, exist_ok=True)
missing = []


def image(obj_path, colour):
    if not obj_path:
        return None
    stem = obj_path.split(".")[-1].replace(" ", "_")
    src = os.path.join(TEX_DIR, stem + ".png")
    if not os.path.isfile(src):
        missing.append(stem)
        log("missing texture " + src)
        return None
    dst = os.path.join(tex_out, stem + ".png")
    if os.path.normcase(src) != os.path.normcase(dst) and (
            not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src)):
        shutil.copy2(src, dst)
    img = bpy.data.images.load(dst, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


def spec_roughness(power):
    alpha = math.sqrt(2.0 / (max(power, 0.5) + 2.0))
    return min(1.0, math.sqrt(alpha))


def build_material(mat, mic):
    t, sc, vec = mic["textures"], mic["scalars"], mic["vectors"]
    t = {k.lower(): v for k, v in t.items()}
    sc = {k.lower(): v for k, v in sc.items()}
    vec = {k.lower(): v for k, v in vec.items()}
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

    def tex(path, colour, x, y, label):
        img = image(path, colour)
        if img is None:
            return None
        n = node("ShaderNodeTexImage", x, y, label)
        n.image = img
        return n

    out = node("ShaderNodeOutputMaterial", 900, 0)
    add = node("ShaderNodeAddShader", 700, 0, "漫反射 + 彩色高光")
    bsdf = node("ShaderNodeBsdfPrincipled", 350, 250)
    gloss = node("ShaderNodeBsdfGlossy", 350, -350, "游戏的彩色高光")
    L.new(bsdf.outputs["BSDF"], add.inputs[0])
    L.new(gloss.outputs["BSDF"], add.inputs[1])
    L.new(add.outputs["Shader"], out.inputs["Surface"])
    bsdf.inputs["Specular"].default_value = 0.15
    bsdf.inputs["Roughness"].default_value = 0.7

    n = tex(t.get("diffusetex"), True, -400, 400, "diffusetex")
    if n:
        L.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    n = tex(t.get("normaltex"), False, -900, -50, "normaltex")
    if n:
        sep = node("ShaderNodeSeparateRGB", -620, -50)
        inv = node("ShaderNodeMath", -440, -80, "UE 法线：绿通道翻转")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        comb = node("ShaderNodeCombineRGB", -260, -50)
        nm = node("ShaderNodeNormalMap", -80, -50)
        nm.inputs["Strength"].default_value = float(sc.get("normalstrength", NORMAL_STRENGTH))
        L.new(n.outputs["Color"], sep.inputs["Image"])
        L.new(sep.outputs["R"], comb.inputs["R"])
        L.new(sep.outputs["G"], inv.inputs[1])
        L.new(inv.outputs["Value"], comb.inputs["G"])
        L.new(sep.outputs["B"], comb.inputs["B"])
        L.new(comb.outputs["Image"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        L.new(nm.outputs["Normal"], gloss.inputs["Normal"])
    colour = node("ShaderNodeMixRGB", 100, -350, "高光颜色 = speccolortex x speccolorvalue")
    colour.blend_type = "MULTIPLY"
    colour.inputs["Fac"].default_value = 1.0
    n = tex(t.get("speccolortex"), True, -400, -300, "speccolortex")
    if n:
        L.new(n.outputs["Color"], colour.inputs["Color1"])
    else:
        colour.inputs["Color1"].default_value = (1, 1, 1, 1)
    cv = vec.get("speccolorvalue")
    colour.inputs["Color2"].default_value = (cv[0], cv[1], cv[2], 1.0) if cv else (1, 1, 1, 1)
    strength = node("ShaderNodeMixRGB", 250, -500, "x 高光遮罩 x specmult")
    strength.blend_type = "MULTIPLY"
    strength.inputs["Fac"].default_value = 1.0
    L.new(colour.outputs["Color"], strength.inputs["Color1"])
    k = max(0.03, min(0.5, float(sc.get("specmult", 2.0)) * SPEC_SCALE)) if SPEC_SCALE > 0 else 0.0
    n = tex(t.get("specmult_specpow_skinmask_reflectivity"), False, -400, -650, "specmult_specpow_skinmask_reflectivity")
    if n:
        sep2 = node("ShaderNodeSeparateRGB", -100, -650)
        mk = node("ShaderNodeMath", 80, -650, "R x specmult x %.3f" % SPEC_SCALE)
        mk.operation = "MULTIPLY"
        mk.inputs[1].default_value = k
        L.new(n.outputs["Color"], sep2.inputs["Image"])
        L.new(sep2.outputs["R"], mk.inputs[0])
        L.new(mk.outputs["Value"], strength.inputs["Color2"])
    else:
        strength.inputs["Color2"].default_value = (k, k, k, 1)
    L.new(strength.outputs["Color"], gloss.inputs["Color"])
    gloss.inputs["Roughness"].default_value = spec_roughness(float(sc.get("specularpower", 10.0)))
    n = tex(t.get("emissive"), True, -400, 50, "emissive")
    if n:
        L.new(n.outputs["Color"], bsdf.inputs["Emission"])
        bsdf.inputs["Emission Strength"].default_value = float(sc.get("emissivemultiplier", 1.0))
    mat["mho_instance"] = mic.get("path", "")
    mat["mho_parent"] = mic.get("parent", "")
    for key in ("specmult", "specularpower", "normalstrength", "emissivemultiplier"):
        if key in sc:
            mat["mho_" + key] = float(sc[key])


by_name = {k.replace(" ", "_").lower(): v for k, v in MATERIALS.items()}
done = []
for slot in mesh.material_slots:
    mat = slot.material
    mic = by_name.get(mat.name.lower())
    if mic is None:
        log("no parameters for material " + mat.name)
        continue
    build_material(mat, mic)
    done.append(mat.name)
    log("material %s <- %s" % (mat.name, ", ".join("%s=%s" % (k, v.split(".")[-1]) for k, v in mic["textures"].items())))

for poly in mesh.data.polygons:
    poly.use_smooth = True
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
world = bpy.data.worlds.new("World")
world.use_nodes = True
scene.world = world
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.16, 0.17, 0.19, 1)
bg.inputs["Strength"].default_value = 0.45
arm["mho_source"] = os.path.basename(PSK)
os.makedirs(out_dir, exist_ok=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=OUT, relative_remap=True, compress=True)
log("saved " + OUT)


# ---- previews (rendered after saving, not part of the .blend)
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

    light("key", 260, centre + Vector((-1.6, -2.6, 1.6)), 1.0)
    light("fill", 70, centre + Vector((2.2, -1.8, 0.3)), 2.0, (0.85, 0.9, 1.0))
    light("rim", 300, centre + Vector((0.8, 2.6, 1.4)), 1.0, (0.7, 0.82, 1.0))
    cam_data = bpy.data.cameras.new("preview_cam")
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    files = []
    for name, d in [("front", Vector((0, -1, 0))), ("three_quarter", Vector((-0.7, -0.7, 0)).normalized()),
                    ("side", Vector((1, 0, 0))), ("back", Vector((0, 1, 0)))]:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(height, hi.x - lo.x, hi.y - lo.y) * 1.08
        cam.location = centre + d * 5.0
        look_at(cam, centre)
        scene.render.resolution_x, scene.render.resolution_y = 1100, 1500
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    head = arm.data.bones.get("g_head")
    hc = (arm.matrix_world @ head.head_local) if head else Vector((centre.x, centre.y, hi.z - 0.15))
    hc = hc + Vector((0, 0, 0.06))
    cam_data.type = "PERSP"
    cam_data.lens = 85
    scene.render.resolution_x = scene.render.resolution_y = 1200
    for name, d in [("head_front", Vector((0, -1, 0.1))), ("head_three_quarter", Vector((-0.75, -0.65, 0.1))),
                    ("head_side", Vector((1, 0, 0.1))), ("head_back", Vector((0.2, 1, 0.25)))]:
        cam.location = hc + d.normalized() * 1.0
        look_at(cam, hc)
        scene.render.filepath = os.path.join(folder, name + ".png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    log("previews in " + folder)
    return files


previews = render_views(os.path.abspath(PREVIEW)) if PREVIEW else []
print("BUILD_DONE=" + json.dumps({"blend": OUT, "vertices": len(mesh.data.vertices), "faces": len(mesh.data.polygons),
                                  "bones": len(arm.data.bones), "height_m": round(hi.z - lo.z, 3),
                                  "joint_check": JOINTS, "materials": done, "missing_textures": missing,
                                  "previews": previews},
                                 ensure_ascii=False))
