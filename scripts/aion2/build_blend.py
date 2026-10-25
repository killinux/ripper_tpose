"""AION2 - assemble UE Viewer PSK parts into one .blend with baked materials (Blender 3.6, headless).

    blender -b --factory-startup --python build_blend.py -- --spec <out_dir>/spec.json [--no-preview]

spec.json (written by export_model.py):
    {"id": "GF_Angel_01", "out_dir": "E:/aion2_exports/blend/GF_Angel_01",
     "parts": [{"name": "Body", "psk": "E:/.../GF_Angel_01_Body.psk"}, ...],
     "materials": "E:/aion2_exports/blend/GF_Angel_01/materials.json"}

1. imports every part with io_scene_psk_psa (material slots are named after the game materials);
2. merges the parts' skeletons by bone name into the one with most bones (all player parts are skinned
   to the same Bip001 skeleton; bones a part adds - face rig, hair, cape - are added where the part has them;
   a part whose shared bones sit off the base rest pose by more than REPOSE_TOLERANCE is re-posed first);
3. builds each material from materials.json (bake_materials.py): albedo (+ alpha clip / blend), ORM
   (G roughness, B metallic), the DirectX normal map with green flipped, emission;
4. copies every texture into <out_dir>/textures, saves <id>.blend (relative paths), renders preview.png
   (whole body) and preview_face.png.  Characters face -Y.

Prints AION2_REPORT=<json> at the end (export_model.py stores it in build.log).
"""
import json
import math
import os
import shutil
import sys

import addon_utils
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # nude_body.py

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SPEC = json.load(open(argv[argv.index("--spec") + 1], encoding="utf-8"))
NO_PREVIEW = "--no-preview" in argv
MODEL_ID = SPEC["id"]
OUT_DIR = os.path.normpath(SPEC["out_dir"])
TEX_DIR = os.path.join(OUT_DIR, "textures")
MATERIALS = json.load(open(SPEC["materials"], encoding="utf-8"))
MASK_CLIP = 0.33
REPOSE_TOLERANCE = 0.5     # cm
EMISSION_SCALE = 1.0       # game EmissiveDay_intensity -> Blender emission strength
os.makedirs(TEX_DIR, exist_ok=True)

report = {"id": MODEL_ID, "parts": [], "warnings": [], "materials": {}, "rig": {}}


def log(msg):
    print("[aion2] " + msg, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
if addon_utils.enable("io_scene_psk_psa", default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for this Blender (needed for PSK import)")


# ---------------------------------------------------------------- import
def import_psk(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(filepath=path, should_import_vertex_colors=True, should_import_vertex_normals=True,
                             should_import_extra_uvs=False, should_import_mesh=True, should_import_materials=True,
                             should_reuse_materials=True, should_import_skeleton=True, should_import_shape_keys=True,
                             bone_length=1.0)
    created = [o for o in bpy.data.objects if o not in before]
    return next((o for o in created if o.type == "ARMATURE"), None), [o for o in created if o.type == "MESH"]


imported = []
for part in SPEC["parts"]:
    psk = os.path.normpath(part["psk"])
    if not os.path.isfile(psk):
        report["warnings"].append("missing PSK: " + psk)
        continue
    arm, meshes = import_psk(psk)
    if arm is None or not meshes:
        report["warnings"].append("import produced no armature/mesh: " + psk)
        continue
    arm.name = "%s_%s_rig" % (MODEL_ID, part["name"])
    for i, mesh in enumerate(meshes):
        mesh.name = "%s_%s" % (MODEL_ID, part["name"]) + ("" if i == 0 else "_%d" % i)
    # slots UE Viewer could not resolve ("material_0") get the material instance export_model.py found next to
    # the mesh; renamed right away so the next part's own "material_0" is not merged into this one
    mmap = part.get("material_map") or {}
    for mesh in meshes:
        for slot in mesh.material_slots:
            if slot.material and slot.material.name.split(".")[0] in mmap:
                slot.material.name = mmap[slot.material.name.split(".")[0]]
    if part.get("skin_only"):                 # nude body: keep only the costume part's skin slot
        import bmesh
        for mesh in meshes:
            keep = {i for i, s in enumerate(mesh.material_slots)
                    if s.material and s.material.name.split(".")[0] == part["skin_only"]}
            bm = bmesh.new()
            bm.from_mesh(mesh.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index not in keep], context="FACES")
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            bm.to_mesh(mesh.data)
            bm.free()
    imported.append((part, arm, meshes))
    report["parts"].append({"name": part["name"], "psk": os.path.basename(psk), "bones": len(arm.data.bones),
                            "vertices": sum(len(m.data.vertices) for m in meshes),
                            "materials": sorted({s.material.name for m in meshes for s in m.material_slots if s.material})})
    log("imported %s: %d bones, %d verts" % (part["name"], len(arm.data.bones), report["parts"][-1]["vertices"]))
if not imported:
    raise SystemExit("nothing imported")


# ---------------------------------------------------------------- one rig
def bone_depth(bone):
    d = 0
    while bone.parent:
        bone = bone.parent
        d += 1
    return d


def repose_part(arm, meshes, base_arm):
    """Pose `arm` so its shared bones land on the base rest pose, bake the meshes in that pose."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for bone in sorted(arm.data.bones, key=bone_depth):
        target = base_arm.data.bones.get(bone.name)
        if target is not None:
            arm.pose.bones[bone.name].matrix = target.matrix_local
            bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh in meshes:
        baked = bpy.data.meshes.new_from_object(mesh.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
        old = mesh.data
        mesh.data = baked
        baked.name = old.name
        bpy.data.meshes.remove(old)


_part, base_arm, _m = max(imported, key=lambda t: len(t[1].data.bones))
base_arm.name = MODEL_ID + "_rig"
added, worst_all, reposed = 0, 0.0, []
for part, arm, meshes in imported:
    if arm is base_arm:
        continue
    worst = 0.0
    for bone in arm.data.bones:
        target = base_arm.data.bones.get(bone.name)
        if target is not None:
            worst = max(worst, max(abs(bone.matrix_local[r][c] - target.matrix_local[r][c]) for r in range(4) for c in range(4)))
    worst_all = max(worst_all, worst)
    if worst > REPOSE_TOLERANCE:
        repose_part(arm, meshes, base_arm)
        reposed.append("%s (%.2f)" % (part["name"], worst))
    missing = sorted((b for b in arm.data.bones if base_arm.data.bones.get(b.name) is None), key=bone_depth)
    if missing:
        posed = {b.name: (arm.matrix_world @ arm.pose.bones[b.name].matrix) for b in missing}
        bpy.context.view_layer.objects.active = base_arm
        bpy.ops.object.mode_set(mode="EDIT")
        edit = base_arm.data.edit_bones
        inv = base_arm.matrix_world.inverted()
        for bone in missing:
            ml = inv @ posed[bone.name]
            eb = edit.new(bone.name)
            eb.head = ml.to_translation()
            eb.tail = eb.head + (ml.to_3x3() @ Vector((0.0, 1.0, 0.0))) * max(bone.length, 0.5)
            eb.align_roll(ml.to_3x3() @ Vector((0.0, 0.0, 1.0)))
            if bone.parent and bone.parent.name in edit:
                eb.parent = edit[bone.parent.name]
            added += 1
        bpy.ops.object.mode_set(mode="OBJECT")
    for mesh in meshes:
        world = mesh.matrix_world.copy()
        bound = False
        for mod in mesh.modifiers:
            if mod.type == "ARMATURE":
                mod.object = base_arm
                bound = True
        if not bound:
            mesh.modifiers.new("Armature", "ARMATURE").object = base_arm
        mesh.parent = base_arm
        mesh.matrix_parent_inverse = base_arm.matrix_world.inverted()
        mesh.matrix_world = world
    bpy.data.objects.remove(arm, do_unlink=True)
report["rig"] = {"bones": len(base_arm.data.bones), "added_bones": added, "max_rest_deviation": round(worst_all, 3),
                 "reposed": reposed}
log("rig: %d bones (%d added), max rest deviation %.3f, reposed %s" % (len(base_arm.data.bones), added, worst_all, reposed or "none"))


# ---------------------------------------------------------------- nude body (export_model.py <G>_Nude, see nude_body.py)
NUDE_BODY = None
if any(p.get("skin_only") for p, _a, _m in imported):
    import nude_body
    skin_meshes = [m for p, _a, ms in imported if p.get("skin_only") for m in ms]
    NUDE_BODY = nude_body.build(skin_meshes, base_arm, SPEC, MATERIALS, log, report)
    if NUDE_BODY is not None:     # the skin parts were joined into one mesh: point the part list at it
        NUDE_BODY.name = "%s_Body" % MODEL_ID
        first = True
        for i, (p, a, ms) in enumerate(imported):
            if p.get("skin_only"):
                imported[i] = (dict(p, name="Body") if first else p, a, [NUDE_BODY] if first else [])
                first = False


# ---------------------------------------------------------------- helmet clip plane (export_model.helmet_rules)
def cut_hair_by_plane(clip_path):
    """The helmet's <part>_Clip static mesh is one quad: hair on the head-top side of its plane is inside the helmet
    and is removed (whole faces with every vertex on that side)."""
    import bmesh
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(filepath=clip_path, should_import_mesh=True, should_import_skeleton=True,
                             should_import_materials=False)
    created = [o for o in bpy.data.objects if o not in before]
    quad = next((o for o in created if o.type == "MESH"), None)
    if quad is None or not quad.data.polygons:
        report["warnings"].append("clip mesh without faces: " + clip_path)
        return
    poly = quad.data.polygons[0]
    centre = quad.matrix_world @ poly.center
    normal = (quad.matrix_world.to_3x3() @ poly.normal).normalized()
    for o in created:
        bpy.data.objects.remove(o, do_unlink=True)
    head = base_arm.data.bones.get("Bip001-Head")
    top = (base_arm.matrix_world @ head.head_local + Vector((0.0, 0.0, 15.0))) if head else centre + Vector((0, 0, 15.0))
    side = 1.0 if (top - centre).dot(normal) > 0 else -1.0
    removed = 0
    for part, _arm, meshes in imported:
        if part["name"] != "Hair":
            continue
        for mesh in meshes:
            bm = bmesh.new()
            bm.from_mesh(mesh.data)
            mw = mesh.matrix_world
            doomed = [f for f in bm.faces if all(side * (mw @ v.co - centre).dot(normal) > 0.0 for v in f.verts)]
            removed += len(doomed)
            bmesh.ops.delete(bm, geom=doomed, context="FACES")
            bm.to_mesh(mesh.data)
            bm.free()
    report["rig"]["hair_clip"] = {"plane": os.path.basename(clip_path), "faces_removed": removed}
    log("hair cut by %s: %d faces removed" % (os.path.basename(clip_path), removed))


if SPEC.get("hair_clip"):
    cut_hair_by_plane(SPEC["hair_clip"])


# ---------------------------------------------------------------- materials
def copy_tex(path):
    if not path or not os.path.isfile(path):
        return None
    dst = os.path.join(TEX_DIR, os.path.basename(path))
    if os.path.normcase(os.path.abspath(dst)) != os.path.normcase(os.path.abspath(path)):
        if not os.path.isfile(dst) or os.path.getmtime(dst) < os.path.getmtime(path):
            shutil.copy2(path, dst)
    return dst


def image(path, non_color=False):
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def tex(nodes, path, x, y, non_color=False, label=""):
    n = nodes.new("ShaderNodeTexImage")
    n.image = image(path, non_color)
    n.location = (x, y)
    n.label = label or os.path.basename(path)
    return n


def setup_material(mat, entry):
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    kind = entry.get("kind", "missing")
    alpha_mode = entry.get("alpha")
    if alpha_mode == "hide":
        bsdf.inputs["Alpha"].default_value = 0.0
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"
        return
    albedo = copy_tex(entry.get("albedo") or entry.get("albedo_raw"))
    if albedo:
        t = tex(nodes, albedo, -400, 250, label="albedo")
        links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha_mode in ("clip", "blend", "hashed"):
            links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            if alpha_mode == "clip":
                mat.blend_method = "CLIP"
                mat.alpha_threshold = MASK_CLIP
                mat.shadow_method = "CLIP"
            elif alpha_mode == "hashed":
                mat.blend_method = "HASHED"
                mat.shadow_method = "HASHED"
            else:
                mat.blend_method = "BLEND"
                mat.shadow_method = "NONE"
                mat.show_transparent_back = False
    else:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        report["warnings"].append("material %s (%s): no colour texture" % (mat.name, kind))
    orm = copy_tex(entry.get("orm"))
    if orm:
        t = tex(nodes, orm, -650, -50, non_color=True, label="ORM")
        sep = nodes.new("ShaderNodeSeparateRGB")
        sep.location = (-350, -50)
        links.new(t.outputs["Color"], sep.inputs["Image"])
        links.new(sep.outputs["G"], bsdf.inputs["Roughness"])
        links.new(sep.outputs["B"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = entry.get("roughness", 0.6)
        bsdf.inputs["Metallic"].default_value = 0.0
    normal = copy_tex(entry.get("normal"))
    if normal:
        t = tex(nodes, normal, -900, -350, non_color=True, label="normal (DirectX)")
        sep = nodes.new("ShaderNodeSeparateRGB")
        sep.location = (-650, -350)
        inv = nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        inv.location = (-450, -400)
        comb = nodes.new("ShaderNodeCombineRGB")
        comb.location = (-250, -350)
        nm = nodes.new("ShaderNodeNormalMap")
        nm.location = (0, -350)
        nm.inputs["Strength"].default_value = 1.0 if kind != "skin" else 0.8
        links.new(t.outputs["Color"], sep.inputs["Image"])
        links.new(sep.outputs["R"], comb.inputs["R"])
        links.new(sep.outputs["G"], inv.inputs[1])
        links.new(inv.outputs["Value"], comb.inputs["G"])
        links.new(sep.outputs["B"], comb.inputs["B"])
        links.new(comb.outputs["Image"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    emission = copy_tex(entry.get("emission"))
    if emission:
        t = tex(nodes, emission, -400, -650, label="emission")
        links.new(t.outputs["Color"], bsdf.inputs["Emission"])
        bsdf.inputs["Emission Strength"].default_value = entry.get("emission_strength", 1.0) * EMISSION_SCALE
    if kind in ("skin", "face"):
        bsdf.inputs["Subsurface"].default_value = entry.get("subsurface", 0.08)
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        if albedo:
            links.new(nodes["Image Texture"].outputs["Color"], bsdf.inputs["Subsurface Color"])
    if kind == "eye":
        bsdf.inputs["Specular"].default_value = 0.6
        bsdf.inputs["Clearcoat"].default_value = 0.6
    if kind == "hair":
        bsdf.inputs["Specular"].default_value = 0.35
    if entry.get("two_sided") or kind == "hair":
        mat.use_backface_culling = False


def remap_half_atlas(mesh, slot_index):
    """CM_HairCardCap hair: v' = 0.5 + 0.5 v on the polygons of this slot (see bake_materials.bake_hair)."""
    uv = mesh.data.uv_layers.active
    if uv is None:
        return 0
    done = set()
    for poly in mesh.data.polygons:
        if poly.material_index != slot_index:
            continue
        for li in poly.loop_indices:
            if li not in done:
                done.add(li)
                uv.data[li].uv[1] = 0.5 + 0.5 * uv.data[li].uv[1]
    return len(done)


seen = {}
for _part, _arm, meshes in imported:
    for mesh in meshes:
        for si, slot in enumerate(mesh.material_slots):
            base = slot.material.name.split(".")[0] if slot.material else ""
            if (MATERIALS.get(base) or {}).get("uv_half_atlas"):
                n = remap_half_atlas(mesh, si)
                report.setdefault("uv_half_atlas", []).append("%s/%s (%d loops)" % (mesh.name, base, n))
        for slot in mesh.material_slots:
            mat = slot.material
            if mat is None or mat.name in seen or mat.get("aion2_ready"):
                continue
            base = mat.name.split(".")[0]
            entry = MATERIALS.get(base) or MATERIALS.get(mat.name)
            if entry is None:
                report["warnings"].append("no baked entry for material " + mat.name)
                entry = {"kind": "missing"}
            setup_material(mat, entry)
            seen[mat.name] = entry.get("kind")
            for w in entry.get("warnings", []):
                report["warnings"].append("%s: %s" % (base, w))
report["materials"] = seen
log("materials: " + ", ".join("%s=%s" % kv for kv in seen.items()))


# ---------------------------------------------------------------- save
for img in bpy.data.images:
    if img.filepath:
        p = bpy.path.abspath(img.filepath)
        dst = copy_tex(p)
        if dst:
            img.filepath = dst
blend_path = os.path.join(OUT_DIR, MODEL_ID + ".blend")
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
report["blend"] = blend_path
log("saved " + blend_path)


# ---------------------------------------------------------------- previews (cameras / lights are not saved)
def bounds(objects):
    pts = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def render(path, center, ortho, size, distance, forward):
    scene = bpy.context.scene
    cd = bpy.data.cameras.new("PreviewCam")
    cd.type = "ORTHO"
    cd.ortho_scale = ortho
    cd.clip_start = 1.0
    cd.clip_end = distance * 10
    cam = bpy.data.objects.new("PreviewCam", cd)
    scene.collection.objects.link(cam)
    cam.location = center + forward * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Filmic"
    scene.eevee.taa_render_samples = 48
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.03
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cd)
    log("rendered " + path)


if not NO_PREVIEW:
    scene = bpy.context.scene
    meshes_all = [m for _p, _a, ms in imported for m in ms]
    lo, hi = bounds(meshes_all)
    center, extent = (lo + hi) / 2, hi - lo
    height = max(extent.z, 1e-6)
    forward = Vector((0.0, -1.0, 0.0))
    side = Vector((1.0, 0.0, 0.0))
    for name, (f, s, z), energy in (("Key", (1.2, 0.9, 1.2), 3.0), ("Fill", (0.9, -1.0, 0.6), 1.3), ("Rim", (-0.8, -0.2, 1.1), 1.6)):
        light = bpy.data.lights.new(name, "SUN")
        light.energy = energy
        light.angle = math.radians(10)
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + (forward * f + side * s + Vector((0.0, 0.0, z))) * height
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.56, 0.6, 1.0)
    scene.world = world
    render(os.path.join(OUT_DIR, "preview.png"), center, max(extent.z * 1.08, extent.x * 1.1), (900, 1400), height * 3, forward)
    head = base_arm.data.bones.get("Bip001-Head")
    if head is not None:
        hp = base_arm.matrix_world @ head.head_local
        render(os.path.join(OUT_DIR, "preview_face.png"), hp + Vector((0.0, 0.0, 6.0)), 30.0, (900, 900), height, forward)
    back = Vector((0.0, 1.0, 0.0))
    render(os.path.join(OUT_DIR, "preview_back.png"), center, max(extent.z * 1.08, extent.x * 1.1), (900, 1400), height * 3, back)

print("AION2_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
