# -*- coding: utf-8 -*-
"""An outfit mod that replaces ONE game outfit's SkeletalMesh (and some of its material instances) -> a complete Eve
.blend: the archived package of the outfit it replaces (Face_003, hair, ponytail on one armature) with its outfit
mesh swapped for the mod's.

    blender -b --factory-startup --python swap_mod_mesh.py -- --base <archived package folder> --psk <mod .psk(x)>
            --tex-root <UE Viewer export of the mod> --out <packages dir> --label Eve_Mod_<name>
            [--object Eve_Body_Mesh_01] [--title "display name"]

Why not validate_eve.py / build_standalone.py: validate_eve needs the shared Face_003 / hair exports (FModel), and
build_standalone rebuilds EVERY slot from the mod's .mat files - a slot the mod does not override (the outfit's skin
CH_P_EVE_15_BB) has no .mat there and would be hidden.  Here:
  * the package folder is copied to <out>/<label>/ (blend renamed <label>.blend, its textures/ kept);
  * the mod's PSK is imported and moved onto the package's armature by the similarity transform that best maps its
    bones onto the same-named bones of Eve_Armature (UE Viewer's PSK and validate_eve's scene differ in axes / scale);
    the fit's error is reported (a mod made on this outfit's skeleton fits to a fraction of a millimetre);
  * slots the mod overrides (a .mat under --tex-root) get a fresh Principled material from the mod's maps (Diffuse,
    DirectX Normal, ORM = R occlusion / G roughness / B metallic, Emissive x2), textures copied to textures/mod/;
    the other slots keep the package's material of the same name (the game's own, e.g. the skin);
  * the old outfit object is removed and the new one takes its name (the PMX / XPS steps look for Eve_Body_Mesh_01);
  * preview.png (front, 900 x 1400) is rendered.
Prints SB_MOD_SWAP={json}.
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
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True, help="archived package folder of the outfit the mod replaces")
ap.add_argument("--psk", required=True)
ap.add_argument("--tex-root", required=True)
ap.add_argument("--out", required=True, help="packages dir; the result goes to <out>/<label>/")
ap.add_argument("--label", required=True)
ap.add_argument("--object", default="Eve_Body_Mesh_01")
ap.add_argument("--title", default="")
ap.add_argument("--mesh-json", default="",
                help="CUE4Parse JSON of the mod's mesh: slot names in order (UE Viewer writes material_N for the "
                     "game materials it could not load from the mod alone)")
ap.add_argument("--material-from", action="append", default=[],
                help="another archived .blend to take game materials from by name (e.g. the monokini's skin)")
args = ap.parse_args(argv)

report = {"label": args.label, "base": args.base, "psk": args.psk}
dst = os.path.join(os.path.abspath(args.out), args.label)
base_blend = next(f for f in os.listdir(args.base) if f.lower().endswith(".blend"))
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(args.base, dst, ignore=shutil.ignore_patterns("*.blend1", "preview*.png", "package.json", "README.txt"))
os.rename(os.path.join(dst, base_blend), os.path.join(dst, args.label + ".blend"))
blend_path = os.path.join(dst, args.label + ".blend")
bpy.ops.wm.open_mainfile(filepath=blend_path)
scene = bpy.context.scene
old = bpy.data.objects[args.object]
arm = old.find_armature() or next(o for o in scene.objects if o.type == "ARMATURE")

# ------------------------------------------------------------------ import the mod mesh
addon_utils.enable("io_scene_psk_psa", default_set=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.psk(filepath=args.psk)
new_objs = [o for o in bpy.data.objects if o not in before]
psk_arm = next(o for o in new_objs if o.type == "ARMATURE")
psk_mesh = next(o for o in new_objs if o.type == "MESH")


def heads(a):
    return {b.name: a.matrix_world @ b.head_local for b in a.data.bones}


A, B = heads(psk_arm), heads(arm)
common = sorted(set(A) & set(B))
P = np.array([A[n] for n in common], dtype=np.float64)
Q = np.array([B[n] for n in common], dtype=np.float64)
pc, qc = P.mean(0), Q.mean(0)
H = (P - pc).T @ (Q - qc)
U, S, Vt = np.linalg.svd(H)
D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
R = Vt.T @ D @ U.T
s = float((S * np.diag(D)).sum() / ((P - pc) ** 2).sum())
t = qc - s * R @ pc
fit = np.linalg.norm((s * (R @ P.T)).T + t - Q, axis=1)
report["bone_fit"] = {"common_bones": len(common), "psk_bones": len(A), "scale": round(s, 6),
                      "rms_cm": round(float(np.sqrt((fit ** 2).mean())), 4), "max_cm": round(float(fit.max()), 4),
                      "worst": common[int(fit.argmax())]}
M = Matrix.Identity(4)
for i in range(3):
    for k in range(3):
        M[i][k] = s * R[i, k]
    M[i][3] = t[i]
psk_mesh.parent = None
psk_mesh.matrix_world = M @ psk_mesh.matrix_world
bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT")
psk_mesh.select_set(True)
bpy.context.view_layer.objects.active = psk_mesh
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for md in list(psk_mesh.modifiers):
    if md.type == "ARMATURE":
        psk_mesh.modifiers.remove(md)
bpy.data.objects.remove(psk_arm, do_unlink=True)
psk_mesh.parent = arm
psk_mesh.matrix_parent_inverse = arm.matrix_world.inverted()
mod = psk_mesh.modifiers.new("Armature", "ARMATURE")
mod.object = arm
report["groups_without_bone"] = sorted(g.name for g in psk_mesh.vertex_groups if g.name not in arm.data.bones)
for c in list(psk_mesh.users_collection):
    c.objects.unlink(psk_mesh)
for c in old.users_collection:
    c.objects.link(psk_mesh)

# ------------------------------------------------------------------ materials
png, mats = {}, {}
for root, _d, files in os.walk(args.tex_root):
    for f in files:
        stem, ext = os.path.splitext(f)
        if ext.lower() == ".png":
            png.setdefault(stem, os.path.join(root, f))
        elif ext.lower() == ".mat":
            mats.setdefault(stem, os.path.join(root, f))
tex_mod = os.path.join(dst, "textures", "mod")
os.makedirs(tex_mod, exist_ok=True)
images = {}


def image(stem, colour):
    if stem not in png:
        report.setdefault("missing_textures", []).append(stem)
        return None
    if (stem, colour) not in images:
        f = os.path.join(tex_mod, stem + ".png")
        shutil.copy2(png[stem], f)
        img = bpy.data.images.load(f, check_existing=False)
        img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        img.filepath = bpy.path.relpath(f, start=dst)
        images[(stem, colour)] = img
    return images[(stem, colour)]


def read_mat(path):
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            out[k] = v
    return out


def build(name, spec):
    m = bpy.data.materials.new(name + "_mod")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    info = {k: v for k, v in spec.items()}
    d = image(spec.get("Diffuse", ""), True)
    if d is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = d, (-700, 250)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        px = np.empty(d.size[0] * d.size[1] * 4, np.float32)
        d.pixels.foreach_get(px)
        if d.channels == 4 and px[3::4].min() < 0.05:
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
            m.blend_method = m.shadow_method = "HASHED"
            info["cutout"] = True
    nimg = image(spec.get("Normal", ""), False) if spec.get("Normal") else None
    if nimg is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = nimg, (-1000, -300)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation, inv.inputs[0].default_value = "SUBTRACT", 1.0
        comb = nt.nodes.new("ShaderNodeCombineColor")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
        nt.links.new(sep.outputs["Green"], inv.inputs[1])          # DirectX -> OpenGL: flip green
        nt.links.new(inv.outputs[0], comb.inputs["Green"])
        nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
        nt.links.new(comb.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    orm = spec.get("Other[0]", "")
    oimg = image(orm, False) if re.search(r"_(ARM|ORM)$", orm, re.I) else None
    if oimg is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = oimg, (-1000, 0)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(n.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.5
    e = spec.get("Emissive") or next((v for k, v in spec.items() if re.search(r"_E$", v)), None)
    eimg = image(e, True) if e else None
    if eimg is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = eimg, (-700, -650)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission"])
        bsdf.inputs["Emission Strength"].default_value = 2.0
        info["emission"] = True
    bsdf.inputs["Specular"].default_value = 0.4
    return m, info


def slot_names(path):
    """MaterialSlotName per slot, in order, from a CUE4Parse JSON of a SkeletalMesh."""
    def find(x):
        if isinstance(x, list) and x and all(isinstance(e, dict) and "MaterialSlotName" in e for e in x):
            return x
        if isinstance(x, dict):
            x = list(x.values())
        if isinstance(x, list):
            for e in x:
                r = find(e)
                if r:
                    return r
        return None
    with open(path, encoding="utf-8-sig") as fh:          # CUE4Parse writes a BOM
        found = find(json.load(fh)) or []
    out = []
    for e in found:
        mi = (e.get("MaterialInterface") or {}).get("ObjectName", "")
        m = re.search(r"'([^']+)'", mi)
        out.append(m.group(1) if m else e.get("MaterialSlotName"))
    return out


def from_other_blend(name):
    """append material `name` from an --material-from .blend; its images are copied into this package's textures/."""
    for src in args.material_from:
        with bpy.data.libraries.load(src, link=False) as (data_from, data_to):
            if name not in data_from.materials:
                continue
            data_to.materials = [name]
        m = data_to.materials[0]
        # appending leaves the source file as a library entry that is saved with the .blend: a reference outside
        # the package (the archive self-check fails it); the material is a local copy, so the entry can go
        for lib in list(bpy.data.libraries):
            if os.path.normcase(os.path.abspath(bpy.path.abspath(lib.filepath))) == os.path.normcase(os.path.abspath(src)):
                bpy.data.libraries.remove(lib)
        src_dir = os.path.dirname(os.path.abspath(src))
        for n in m.node_tree.nodes if m.use_nodes else []:
            if n.type == "TEX_IMAGE" and n.image:
                rel = n.image.filepath.replace("//", "", 1) if n.image.filepath.startswith("//") else n.image.filepath
                f = os.path.join(src_dir, rel)
                if os.path.isfile(f):
                    target = os.path.join(dst, "textures", os.path.basename(f))
                    if not os.path.isfile(target):
                        shutil.copy2(f, target)
                    n.image.filepath = "//textures/" + os.path.basename(f)
                    n.image.reload()
        # appended IDs also keep ID.library_weak_reference (the source file), which bpy.utils.blend_paths lists as
        # an outside file: swap them for plain copies
        for idb in [m] + [n.image for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if m.use_nodes else [m]:
            if getattr(idb, "library_weak_reference", None) is not None:
                name, new = idb.name, idb.copy()
                idb.user_remap(new)
                (bpy.data.materials if isinstance(idb, bpy.types.Material) else bpy.data.images).remove(idb)
                new.name = name
                if isinstance(new, bpy.types.Material):
                    m = new
        return m, src
    return None, None


names_by_slot = slot_names(args.mesh_json) if args.mesh_json else []
report["slot_names"] = names_by_slot
report["slots"] = {}
for i, slot in enumerate(psk_mesh.material_slots):
    name = (slot.material.name if slot.material else "slot%d" % i).split(".")[0]
    if i < len(names_by_slot) and names_by_slot[i]:
        name = names_by_slot[i]
    stem = name[3:] if name.startswith("MI_") else name
    if name in mats:
        m, info = build(name, read_mat(mats[name]))
        report["slots"][name] = dict(info, source="mod")
    elif stem + "_A" in png:
        # a game material instance the mod keeps, whose textures it replaces (same path -> the mod's wins)
        spec = {"Diffuse": stem + "_A"}
        for key, suffix in (("Normal", "_N"), ("Other[0]", "_ORM"), ("Emissive", "_E")):
            if stem + suffix in png:
                spec[key] = stem + suffix
        m, info = build(name, spec)
        report["slots"][name] = dict(info, source="game instance, the mod's textures")
    elif name in bpy.data.materials and bpy.data.materials[name] is not slot.material:
        m = bpy.data.materials[name]
        report["slots"][name] = {"source": "package (the game's)"}
    else:
        m, src = from_other_blend(name)
        if m is not None:
            report["slots"][name] = {"source": "game material from " + os.path.basename(src)}
        else:
            m = slot.material
            report["slots"][name] = {"source": "as imported" if m else "none"}
    gone = slot.material
    slot.material = m
    if gone is not None and gone is not m and gone.users == 0:
        bpy.data.materials.remove(gone)
for p in psk_mesh.data.polygons:
    p.use_smooth = True

old_name = old.name
bpy.data.objects.remove(old, do_unlink=True)
psk_mesh.name = old_name
psk_mesh.data.name = old_name
report["object"] = {"name": psk_mesh.name, "vertices": len(psk_mesh.data.vertices),
                    "faces": len(psk_mesh.data.polygons)}
for o in list(scene.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

# ------------------------------------------------------------------ preview
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 48
scene.view_settings.view_transform = "Filmic"
world = bpy.data.worlds.new("W")
world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
scene.world = world
vis = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
centre, height = (mn + mx) / 2, (mx - mn).z
for nm, rot, energy in (("Key", (50, 0, -30), 3.0), ("Fill", (60, 0, 40), 1.2), ("Rim", (70, 0, 170), 1.5)):
    li = bpy.data.lights.new(nm, "SUN")
    li.energy = energy
    lo = bpy.data.objects.new(nm, li)
    scene.collection.objects.link(lo)
    lo.rotation_euler = [np.radians(a) for a in rot]
cd = bpy.data.cameras.new("Cam")
cd.type, cd.ortho_scale = "ORTHO", height * 1.08
cd.clip_start, cd.clip_end = 0.1, height * 20
cam = bpy.data.objects.new("Cam", cd)
scene.collection.objects.link(cam)
scene.camera = cam
# the front is where her toes point (the packages keep UE Viewer's axes: she faces +-X)
forward = Vector((0.0, -1.0, 0.0))


def _bone(words):
    return next((b for b in arm.data.bones if re.sub(r"[-_ ]+", " ", b.name).lower().endswith(words)), None)


toe, foot = _bone("l toe0"), _bone("l foot")
if toe and foot:
    f = (arm.matrix_world @ toe.head_local) - (arm.matrix_world @ foot.head_local)
    f.z = 0.0
    if f.length > 1e-6:
        forward = f.normalized()
scene.render.resolution_x, scene.render.resolution_y = 900, 1400
scene.render.image_settings.file_format = "PNG"
for tag, d in (("preview.png", forward), ("preview_back.png", -forward)):
    cam.location = centre + d * height * 5
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(dst, tag)
    bpy.ops.render.render(write_still=True)
report["height_cm"] = round(height, 1)
report["blend"] = blend_path
report["title"] = args.title
with open(os.path.join(dst, "mod_swap.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
print("SB_MOD_SWAP=" + json.dumps(report, ensure_ascii=False), flush=True)
