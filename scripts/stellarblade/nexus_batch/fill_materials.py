"""Second pass on a swap_mod_mesh.py package: materials of the mod's mesh that came out empty, the CNS defaults.

    blender -b --factory-startup <package>.blend --python fill_materials.py -- <fill.json>

fill.json (written by run_look.py's fill step):
  "object": the outfit object (Eve_Body_Mesh_01)
  "slots": [{"index", "name" (the instance), "need": true when swap_mod_mesh left it empty,
             "ancestors": [parent instance, ..., master] (from the game's JSON),
             "sources": {ancestor name: [archived .blend, ...]},   (material_index.json)
             "textures": {"base", "normal", "orm", "alpha_masked"},   (PNG files for an instance no .blend has)
             "retex": {ancestor: [{"param", "from", "png"}]}}]       (maps the instance sets itself, retex.py: put
                                                                    into the ancestor's copy in place of image "from")
  "overrides": [{"index", "param", "png"}]   CNS default texture options (base colour ones are applied here)
  "hide": [slot index, ...]                  CNS material toggles that are off by default: their faces go
An empty slot gets, in this order: a copy of the nearest ancestor material found in this .blend (also as <name>_mod)
or in an archived game .blend (appended; its images copied into the package's textures\\), renamed to the slot's own
instance name (the HQ step and the add-on look materials up by that name), with the maps the instance sets itself
swapped in ("retex"); else - also when the copy's colour image is none of the instance's maps ("own_maps": the
master's default texture, wrong on the mod's UVs) - a Principled material built from the instance's flattened maps
(base colour, DirectX normal, ORM = R occlusion / G roughness / B metallic), what they lack taken from its values
(colour vector, roughness, a translucent one's face-on opacity); a colour that is no map goes in as an 8 x 8 texture
(constant_image: the exporters read colour and transparency from the colour texture).
Prints SB_FILL={json}."""
import json
import os
import re
import shutil
import sys

import bpy

spec = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
pkg = os.path.dirname(bpy.data.filepath)
obj = bpy.data.objects[spec.get("object", "Eve_Body_Mesh_01")]
report = {"filled": {}, "overrides": [], "hidden": [], "left_empty": []}
BASE_PARAMS = {"basecolor", "base color", "diffuse", "albedo", "basecolour", "base_color", "color"}


def has_images(mat):
    return mat is not None and mat.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in mat.node_tree.nodes)


def localize(mat, src_blend):
    """images of an appended material: copied into the package's textures\\, relative paths; library entries go"""
    src_dir = os.path.dirname(os.path.abspath(src_blend))
    for n in mat.node_tree.nodes if mat.use_nodes else []:
        if n.type == "TEX_IMAGE" and n.image:
            fp = n.image.filepath
            rel = fp[2:] if fp.startswith("//") else fp
            f = rel if os.path.isabs(rel) else os.path.join(src_dir, rel)
            if os.path.isfile(f):
                target = os.path.join(pkg, "textures", os.path.basename(f))
                if not os.path.isfile(target):
                    shutil.copy2(f, target)
                n.image.filepath = "//textures/" + os.path.basename(f)
                n.image.reload()
    for lib in list(bpy.data.libraries):
        if os.path.normcase(os.path.abspath(bpy.path.abspath(lib.filepath))) == os.path.normcase(os.path.abspath(src_blend)):
            bpy.data.libraries.remove(lib)
    for idb in [mat] + [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]:
        if getattr(idb, "library_weak_reference", None) is not None:
            name, new = idb.name, idb.copy()
            idb.user_remap(new)
            (bpy.data.materials if isinstance(idb, bpy.types.Material) else bpy.data.images).remove(idb)
            new.name = name
            if isinstance(new, bpy.types.Material):
                mat = new
    return mat


def append(name, blend):
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        if name not in src.materials:
            return None
        dst.materials = [name]
    return localize(dst.materials[0], blend)


def image(path, colour):
    target = os.path.join(pkg, "textures", "mod", os.path.basename(path))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.abspath(path) != os.path.abspath(target):
        shutil.copy2(path, target)
    img = bpy.data.images.load(target, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    img.filepath = "//textures/mod/" + os.path.basename(path)
    return img


def lin2srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def constant_image(name, rgb, alpha):
    """An 8 x 8 PNG of one colour + alpha in the package's textures\\mod\\.  The exporters take a material's colour
    and transparency from its colour texture: a constant Base Color / Alpha alone reads as a helper shell when the
    alpha is under 0.5 (blender2xps material_is_translucent_shell -> PMX alpha 0, the part vanishes: Crimson Wings'
    vinyl, Black Sling's dark lens), and with a normal map as the only image the PMX takes that as its colour."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    path = os.path.join(pkg, "textures", "mod", safe + "_colour.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gen = bpy.data.images.new(safe + "_colour_gen", 8, 8, alpha=True)
    gen.pixels = [lin2srgb(rgb[0]), lin2srgb(rgb[1]), lin2srgb(rgb[2]), max(0.0, min(1.0, alpha))] * 64
    gen.filepath_raw = path
    gen.file_format = "PNG"
    gen.save()
    bpy.data.images.remove(gen)                 # a generated image would come back blank from the saved .blend
    return image(path, True)


def build(name, tex):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(p.outputs["BSDF"], out.inputs["Surface"])
    p.inputs["Specular"].default_value = 0.4
    p.inputs["Roughness"].default_value = 0.5
    if tex.get("base"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = image(tex["base"], True), (-700, 250)
        nt.links.new(n.outputs["Color"], p.inputs["Base Color"])
        if tex.get("alpha_masked"):
            nt.links.new(n.outputs["Alpha"], p.inputs["Alpha"])
            m.blend_method = m.shadow_method = "HASHED"
    if tex.get("normal"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = image(tex["normal"], False), (-1000, -300)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation, inv.inputs[0].default_value = "SUBTRACT", 1.0
        comb = nt.nodes.new("ShaderNodeCombineColor")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
        nt.links.new(sep.outputs["Green"], inv.inputs[1])           # DirectX -> OpenGL
        nt.links.new(inv.outputs[0], comb.inputs["Green"])
        nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
        nt.links.new(comb.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    if tex.get("orm"):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image, n.location = image(tex["orm"], False), (-1000, 0)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(n.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], p.inputs["Metallic"])
    return m


def base_image_node(mat):
    """the image node that feeds the Principled Base Color (through mix / multiply nodes)"""
    p = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if p is None or not p.inputs["Base Color"].is_linked:
        return None
    stack, seen = [p.inputs["Base Color"].links[0].from_node], set()
    while stack:
        n = stack.pop(0)
        if n.name in seen:
            continue
        seen.add(n.name)
        if n.type == "TEX_IMAGE":
            return n
        for s in n.inputs:
            for lk in s.links:
                stack.append(lk.from_node)
    return None


slots = obj.material_slots
for s in spec["slots"]:
    i, name = s["index"], s["name"]
    if i >= len(slots) or not s.get("need"):
        continue
    cur = slots[i].material
    if has_images(cur):
        continue
    done_before = bpy.data.materials.get(name)
    if done_before is not None and done_before is not cur and has_images(done_before) and name in report["filled"]:
        slots[i].material = done_before         # a second section of the same slot (Crimson Wings OP's UV2)
        if cur is not None and cur.users == 0:
            bpy.data.materials.remove(cur)
        continue
    new, how, used = None, None, None
    for a in s.get("ancestors", []):
        for cand in (a, a + "_mod"):
            m = bpy.data.materials.get(cand)
            if m is not None and m is not cur and has_images(m):
                new, how = m.copy(), "copy of %s (in this .blend)" % cand
                break
        if new is None:
            for blend in s.get("sources", {}).get(a, []):
                m = append(a, blend)
                if m is not None and has_images(m):
                    new, how = m, "copy of %s from %s" % (a, os.path.basename(blend))
                    break
                if m is not None:
                    bpy.data.materials.remove(m)
        if new is not None:
            used = a
            break
    # the maps the instance sets itself (retex.py): swapped into the copy, found by the ancestor's image names
    for r in (s.get("retex") or {}).get(used, []) if used else []:
        hits = 0
        if r.get("png") and os.path.isfile(r["png"]):
            for n in new.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    stem = os.path.splitext(os.path.basename(bpy.path.abspath(n.image.filepath) or n.image.name))[0]
                    if stem.lower() == r["from"].lower():
                        n.image = image(r["png"], n.image.colorspace_settings.name == "sRGB")
                        hits += 1
        report.setdefault("retextured", {}).setdefault(name, []).append(
            [r["param"], r["from"], os.path.basename(r.get("png") or "") or None, hits])
    # an ancestor copy whose colour image is none of this instance's maps shows the master graph's default texture
    # (the archived vinyl MI_EVE_Cos_08_Vinyl: an NPC skin atlas) on the mod's UVs - build from the instance instead
    if new is not None and used is not None and s.get("own_maps") is not None:
        bn = base_image_node(new)
        if bn is not None:
            stem = os.path.splitext(os.path.basename(bpy.path.abspath(bn.image.filepath) or bn.image.name))[0]
            if stem.lower() not in {x.lower() for x in s["own_maps"]}:
                report.setdefault("foreign_colour", {})[name] = [used, stem]
                bpy.data.materials.remove(new)
                new, how, used = None, None, None
    tex = s.get("textures") or {}
    col = next((v for k, v in (s.get("vectors") or {}).items() if "color" in k.lower()
                and "emissive" not in k.lower() and isinstance(v, dict)), None)
    if new is None and (tex.get("base") or tex.get("normal") or col is not None):
        # the instance's own maps; what they lack from its values: colour (BlackSling's dark sunglass lens, the
        # vinyl's black GlassColor), roughness, and for a translucent one its face-on opacity
        new = build(name + "__tmp", tex)
        p = next(n for n in new.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        notes = []
        if not tex.get("base") and col is not None:
            p.inputs["Base Color"].default_value = (col.get("R", 0.5), col.get("G", 0.5), col.get("B", 0.5), 1.0)
            notes.append("colour %.2f %.2f %.2f" % tuple(p.inputs["Base Color"].default_value[:3]))
        sc = {k.lower(): v for k, v in (s.get("scalars") or {}).items() if isinstance(v, (int, float))}
        if not tex.get("orm"):
            rough = next((v for k, v in sc.items() if "rough" in k), None)
            if rough is not None:
                p.inputs["Roughness"].default_value = max(0.0, min(1.0, rough))
                notes.append("roughness %.2f" % p.inputs["Roughness"].default_value)
        translucent = (s.get("blend") or "").endswith("Translucent")
        if translucent:
            op = sc.get("opacity")
            if op is None:
                op = next((v for k, v in sc.items() if "opacity" in k and "inner" in k), None)
            if op is None:
                op = next((v for k, v in sc.items() if "opacity" in k and "fresnel" not in k), 0.6)
            p.inputs["Alpha"].default_value = max(0.05, min(1.0, op))
            new.blend_method, new.shadow_method = "BLEND", "HASHED"
            notes.append("alpha %.2f" % p.inputs["Alpha"].default_value)
        if not tex.get("base"):
            # the colour (and alpha) as a texture, so the XPS / PMX exporters see the part (constant_image)
            n = new.node_tree.nodes.new("ShaderNodeTexImage")
            n.location = (-700, 250)
            n.image = constant_image(name, p.inputs["Base Color"].default_value[:3],
                                     p.inputs["Alpha"].default_value if translucent else 1.0)
            new.node_tree.links.new(n.outputs["Color"], p.inputs["Base Color"])
            if translucent:
                new.node_tree.links.new(n.outputs["Alpha"], p.inputs["Alpha"])
            notes.append("colour texture %s" % os.path.basename(n.image.filepath))
        maps = [k for k in ("base", "normal", "orm") if tex.get(k)]
        how = ("built from the game's maps (%s)" % ", ".join(maps) if maps else "constant") + \
              (" + the instance's values (%s)" % ", ".join(notes) if notes else "")
    if new is None:
        report["left_empty"].append(name)
        continue
    if cur is not None and cur.name == name:
        cur.name = name + "__empty"
    new.name = name
    for sl in slots:
        if sl.material is cur:
            sl.material = new
    if cur is not None and cur.users == 0:
        bpy.data.materials.remove(cur)
    report["filled"][name] = how

# CNS sets its texture options on each slot's own dynamic instance; one instance on two slots with different options
# (the Nikke Plus jacketless mesh: slot 0 and slot 1 both MI_CH_P_EVE_Nikke_06_UV1, suit colour vs top colour) needs
# two materials here: the later slots get a copy named <material>__slot<mesh slot>
mesh_index = {int(k): v for k, v in (spec.get("mesh_index") or {}).items()}
by_slot = {}
for o in spec.get("overrides", []):
    by_slot.setdefault(o["index"], []).append((o["param"].lower(), os.path.basename(o["png"])))
first_sig = {}
report["split"] = []
for i in sorted(by_slot):
    if i >= len(slots) or slots[i].material is None:
        continue
    mat, sig = slots[i].material, tuple(sorted(by_slot[i]))
    if mat.name not in first_sig:
        first_sig[mat.name] = sig
        continue
    if first_sig[mat.name] == sig:
        continue
    copy = mat.copy()
    copy.name = "%s__slot%d" % (mat.name, mesh_index.get(i, i))
    slots[i].material = copy
    report["split"].append([copy.name, mat.name, mesh_index.get(i, i)])

for o in spec.get("overrides", []):
    i = o["index"]
    if i >= len(slots) or slots[i].material is None:
        continue
    mat = slots[i].material
    if o["param"].lower() not in BASE_PARAMS:
        report["overrides"].append([mat.name, o["param"], os.path.basename(o["png"]), "left for the HQ .blend"])
        continue
    node = base_image_node(mat)
    if node is None:
        report["overrides"].append([mat.name, o["param"], os.path.basename(o["png"]), "no base colour image node"])
        continue
    old = node.image.name if node.image else None
    node.image = image(o["png"], True)
    report["overrides"].append([mat.name, o["param"], os.path.basename(o["png"]), "base colour (was %s)" % old])

if spec.get("hide"):
    import bmesh
    hide = set(spec["hide"])
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    gone = [f for f in bm.faces if f.material_index in hide]
    bmesh.ops.delete(bm, geom=gone, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    report["hidden"] = [[i, slots[i].material.name if slots[i].material else None] for i in sorted(hide) if i < len(slots)]
    report["hidden_faces"] = len(gone)

bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()

# previews again (swap_mod_mesh.py rendered them before these materials existed): same set-up as there; the scene
# additions below are not saved
import re  # noqa: E402

import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

scene = bpy.context.scene
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
arm = obj.find_armature()
forward = Vector((0.0, -1.0, 0.0))


def _bone(words):
    return next((b for b in arm.data.bones if re.sub(r"[-_ ]+", " ", b.name).lower().endswith(words)), None)


toe, foot = (_bone("l toe0"), _bone("l foot")) if arm else (None, None)
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
    scene.render.filepath = os.path.join(pkg, tag)
    bpy.ops.render.render(write_still=True)
report["previews"] = ["preview.png", "preview_back.png"]
print("SB_FILL=" + json.dumps(report, ensure_ascii=False), flush=True)
