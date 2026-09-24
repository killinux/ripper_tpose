# -*- coding: utf-8 -*-
"""Build a .blend from ONE self-contained Stellar Blade mesh - a mod that replaces Eve
with a whole character (body, head and face in a single SkeletalMesh).

validate_eve.py always adds Eve's Face_003, hair and ponytail; on a mesh that already
carries its own head that gives two heads, so this script takes the PSK as it is:

  * every material slot is rebuilt from UE Viewer's <slot>.mat (Diffuse / Normal /
    Other[0] = ARM); textures are found by name anywhere under --tex-root, copied into
    <out>/textures and linked relatively, so the folder travels on its own;
  * a Diffuse alpha that really cuts (min ~0) drives a hashed cutout (lace, crowns);
  * ARM = R ambient occlusion, G roughness, B metallic; normals are DirectX (flip G);
  * a slot whose colour map is flat black (a physics proxy such as "phy") or that is
    listed in --hide is split into a hidden object, not deleted;
  * renders preview.png (900x1400) and preview_face.png (900x900 at Bip001-Head).

blender --background --factory-startup --python build_standalone.py -- \
    --psk <mesh.psk> --tex-root <umodel export dir> --out <folder> --name <label>
"""
import argparse
import json
import os
import re
import shutil
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--psk", default="")
ap.add_argument("--blend", default="", help="an assembled .blend to re-material instead of a PSK")
ap.add_argument("--object", default="", help="with --blend: the mesh object to re-material")
ap.add_argument("--tex-root", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--hide", nargs="*", default=[])
args = ap.parse_args(argv)

OUT = os.path.abspath(args.out)
TEX = os.path.join(OUT, "textures")
os.makedirs(OUT, exist_ok=True)
if not args.blend:
    os.makedirs(TEX, exist_ok=True)
report = {"name": args.name, "materials": {}, "hidden": [], "missing": []}

png_index, mat_index = {}, {}
for root, _dirs, files in os.walk(args.tex_root):
    for f in files:
        stem, ext = os.path.splitext(f)
        if ext.lower() == ".png":
            png_index.setdefault(stem, os.path.join(root, f))
        elif ext.lower() == ".mat":
            mat_index.setdefault(stem, os.path.join(root, f))


def read_mat(slot):
    out = {}
    path = mat_index.get(slot)
    if path:
        for line in open(path, encoding="utf-8", errors="replace"):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                out[k] = v
    return out


if args.blend:
    bpy.ops.wm.open_mainfile(filepath=args.blend)
    meshes = [bpy.data.objects[args.object]]
    arm = meshes[0].find_armature() or next(o for o in bpy.data.objects if o.type == "ARMATURE")
    for o in list(bpy.data.objects):          # validate_eve's own camera / lights
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)
else:
    addon_utils.enable("io_scene_psk_psa", default_set=True)
    bpy.ops.import_scene.psk(filepath=args.psk)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    arm.name = args.name + "_rig"

_images = {}


def image(stem, non_color):
    if stem not in png_index:
        report["missing"].append(stem)
        return None, None
    key = (stem, non_color)
    if key not in _images:
        dst = png_index[stem]
        if not args.blend:
            dst = os.path.join(TEX, stem + ".png")
            if not os.path.isfile(dst):
                shutil.copy2(png_index[stem], dst)
        img = bpy.data.images.load(dst, check_existing=True)
        img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
        img.alpha_mode = "CHANNEL_PACKED"
        px = np.asarray(img.pixels[:], dtype=np.float32).reshape(-1, 4)[::97]
        _images[key] = (img, {"alpha_min": float(px[:, 3].min()),
                              "rgb_max": float(px[:, :3].max()), "channels": img.channels})
    return _images[key]


def link_normal(nt, bsdf, img):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image, t.location = img, (-1000, -350)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    comb = nt.nodes.new("ShaderNodeCombineColor")
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(t.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
    nt.links.new(sep.outputs["Green"], inv.inputs[1])
    nt.links.new(inv.outputs["Value"], comb.inputs["Green"])
    nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
    nt.links.new(comb.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def build(mat, slot):
    spec = read_mat(slot)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    info = {"slot": slot, **spec}
    d_img, d_stat = image(spec["Diffuse"], False) if "Diffuse" in spec else (None, None)
    if d_img is None or d_stat["rgb_max"] < 0.02:
        info["hidden"] = "no colour map" if d_img is None else "flat black proxy"
        return info, False
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image, t.location = d_img, (-700, 250)
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if d_stat["channels"] == 4 and d_stat["alpha_min"] < 0.05:
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
        info["cutout"] = True
    if "Normal" in spec:
        n_img, _ = image(spec["Normal"], True)
        if n_img:
            link_normal(nt, bsdf, n_img)
    arm_stem = spec.get("Other[0]", "")
    if arm_stem.endswith("_ARM"):
        a_img, _ = image(arm_stem, True)
        if a_img:
            ta = nt.nodes.new("ShaderNodeTexImage")
            ta.image, ta.location = a_img, (-1000, 0)
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(ta.outputs["Color"], sep.inputs["Color"])
            nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
            nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.55
        bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Specular"].default_value = 0.4
    return info, True


for mesh in list(meshes):
    if not args.blend:
        mesh.name = args.name
    hide_idx = []
    for i, slot in enumerate(mesh.material_slots):
        mat = slot.material or bpy.data.materials.new("slot%d" % i)
        slot.material = mat
        name = mat.name.split(".")[0]
        if name not in report["materials"]:
            info, visible = build(mat, name)
            if name in args.hide:
                visible, info["hidden"] = False, "--hide"
            info["visible"] = visible
            report["materials"][name] = info
        if not report["materials"][name]["visible"]:
            hide_idx.append(i)
    for poly in mesh.data.polygons:
        poly.use_smooth = True
    if hide_idx:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = mesh
        mesh.select_set(True)
        for poly in mesh.data.polygons:
            poly.select = poly.material_index in hide_idx
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        for o in bpy.context.selected_objects:
            if o is not mesh:
                o.name = args.name + "_hidden_proxy"
                o.hide_render = True
                o.hide_set(True)
                report["hidden"].append(o.name)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 48
scene.view_settings.view_transform = "Filmic"
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
scene.world = world
vis = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, height = (mn + mx) / 2, (mx - mn).z

# the front is where the toes point
forward = Vector((0.0, -1.0, 0.0))
def _bone(words):
    return next((b for b in arm.data.bones
                 if re.sub(r"[-_ ]+", " ", b.name).lower().endswith(words)), None)


toe, foot = _bone("l toe0"), _bone("l foot")
if toe and foot:
    d = (arm.matrix_world @ toe.head_local) - (arm.matrix_world @ foot.head_local)
    d.z = 0
    if d.length > 1e-6:
        forward = d.normalized()
side = forward.cross(Vector((0.0, 0.0, 1.0)))
for lname, (f, s, z), energy in (("Key", (1.0, 0.7, 1.2), 3.0), ("Fill", (0.6, -1.0, 0.4), 1.3),
                                 ("Rim", (-0.8, -0.2, 1.0), 1.7)):
    light = bpy.data.lights.new(lname, "SUN")
    light.energy = energy
    obj = bpy.data.objects.new(lname, light)
    scene.collection.objects.link(obj)
    obj.location = center + (forward * f + side * s + Vector((0.0, 0.0, z))) * height
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()


def render(path, target, ortho, size):
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    cd = bpy.data.cameras.new("Cam")
    cd.type, cd.sensor_fit, cd.ortho_scale = "ORTHO", "VERTICAL", ortho
    dist = max(ortho, 100) * 3
    cd.clip_end = dist * 3 + ortho * 10
    cam = bpy.data.objects.new("Cam", cd)
    scene.collection.objects.link(cam)
    cam.location = target + forward * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cd)


# standalone: preview.png next to the blend; --blend mode follows the outfit convention
# of <export root>alidation\<name>.png so blender\ stays blends only
if args.blend:
    vdir = os.path.join(os.path.dirname(OUT), "validation")
    os.makedirs(vdir, exist_ok=True)
    shot, face_shot = os.path.join(vdir, args.name + ".png"), os.path.join(vdir, args.name + "_face.png")
else:
    shot, face_shot = os.path.join(OUT, "preview.png"), os.path.join(OUT, "preview_face.png")
render(shot, center, height * 1.28, (900, 1400))
head = arm.data.bones.get("Bip001-Head")
if head:
    hp = arm.matrix_world @ head.head_local
    render(face_shot, hp + Vector((0, 0, height * 0.03)), height * 0.2, (900, 900))
report.update(preview=shot, preview_face=face_shot)

blend = os.path.join(OUT, args.name + ".blend")
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=blend)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend)
report.update(blend=blend, forward=tuple(round(c, 3) for c in forward), bones=len(arm.data.bones),
              vertices=sum(len(o.data.vertices) for o in vis), faces=sum(len(o.data.polygons) for o in vis))
print("STANDALONE_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
