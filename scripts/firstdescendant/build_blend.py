"""The First Descendant - assemble UE Viewer PSK parts into one .blend (Blender 3.6, headless).

    blender --background --factory-startup --python build_blend.py -- --spec <spec.json> [--no-preview] [--smooth]

spec.json (written by export_model.ps1):
    { "id": "Bunny", "out_dir": "D:/tfd_exports/blend/Bunny",
      "parts": [ {"name": "Full", "psk": "D:/.../PC_004_A0101.pskx"} ] }

What it does:
  1. imports every part with io_scene_psk_psa;
  2. merges the per-part skeletons into one armature by bone name (a descendant's
     default look is a single merged mesh, so most models are one part; a skin is
     Body + Head + Face on the same skeleton);
  3. gives every slot a neutral material - The First Descendant's textures are UE5
     **virtual textures**, which UE Viewer cannot decode, so a umodel-only export
     is untextured by design (see the README for the FModel + .usmap route to full
     textures).  The geometry, rig and material-slot split are all intact;
  4. renders preview.png (+ preview_face.png) and saves <id>.blend.

Prints TFD_REPORT={json} for the PowerShell wrapper.
"""
import json
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Vector

PSK_ADDON = "io_scene_psk_psa"
if addon_utils.enable(PSK_ADDON, default_set=False) is None:
    raise SystemExit("io_scene_psk_psa is not installed for Blender 3.6 (needed for PSK/PSKX import)")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--spec" not in argv:
    raise SystemExit("usage: blender --background --factory-startup --python build_blend.py -- --spec spec.json [--no-preview] [--smooth]")
SPEC = json.load(open(argv[argv.index("--spec") + 1], encoding="utf-8"))
NO_PREVIEW = "--no-preview" in argv
SMOOTH = "--smooth" in argv
MODEL_ID = SPEC["id"]
OUT_DIR = os.path.normpath(SPEC["out_dir"])
PARTS = SPEC["parts"]

report = {"id": MODEL_ID, "parts": [], "warnings": []}


def log(msg):
    print("[tfd] " + msg, flush=True)


def import_psk(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(
        filepath=path,
        should_import_vertex_normals=not SMOOTH,
        should_import_extra_uvs=True,
        should_import_mesh=True,
        should_import_materials=True,
        should_import_skeleton=True,
        should_import_shape_keys=True,
        bone_length=1.0,
    )
    created = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in created if o.type == "ARMATURE"), None)
    meshes = [o for o in created if o.type == "MESH"]
    return arm, meshes


imported = []
for prt in PARTS:
    psk = os.path.normpath(prt["psk"])
    if not os.path.isfile(psk):
        report["warnings"].append("missing PSK: " + psk)
        log("MISSING " + psk)
        continue
    arm, meshes = import_psk(psk)
    if arm is None or not meshes:
        report["warnings"].append("no armature/mesh from " + psk)
        continue
    arm.name = "%s_%s_rig" % (MODEL_ID, prt["name"])
    for i, mesh in enumerate(meshes):
        mesh.name = "%s_%s%s" % (MODEL_ID, prt["name"], "" if i == 0 else "_%d" % i)
        if SMOOTH:
            for poly in mesh.data.polygons:
                poly.use_smooth = True
    imported.append((prt, arm, meshes))
    report["parts"].append({
        "name": prt["name"], "psk": os.path.basename(psk), "bones": len(arm.data.bones),
        "vertices": sum(len(m.data.vertices) for m in meshes),
        "faces": sum(len(m.data.polygons) for m in meshes),
        "slots": max((len(m.material_slots) for m in meshes), default=0),
    })
    log("imported %s: %d bones, %d verts" % (prt["name"], len(arm.data.bones),
                                             report["parts"][-1]["vertices"]))

if not imported:
    print("TFD_REPORT=" + json.dumps({**report, "error": "nothing imported"}), flush=True)
    raise SystemExit("nothing imported")

# ---- one rig: keep the part with the most bones, rebind the others onto it ----
base_prt, base_arm, _ = max(imported, key=lambda t: len(t[1].data.bones))
base_arm.name = MODEL_ID + "_rig"
base_bones = {b.name for b in base_arm.data.bones}
meshes_all = []
for prt, arm, meshes in imported:
    for mesh in meshes:
        meshes_all.append(mesh)
        if arm is base_arm:
            continue
        # add bones this part has that the base lacks (parent-relative), so its
        # weights survive; then retarget the armature modifier to the base rig.
        # Capture everything as plain values FIRST: Blender frees bone Python
        # references across a mode switch, and reading them afterwards yields
        # garbage (a UnicodeDecodeError on b.name).
        mw = arm.matrix_world.copy()
        want = [(b.name, mw @ b.head_local, mw @ b.tail_local,
                 b.parent.name if b.parent else None)
                for b in arm.data.bones if b.name not in base_bones]
        if want:
            bpy.context.view_layer.objects.active = base_arm
            bpy.ops.object.mode_set(mode="EDIT")
            for name, head, tail, _parent in want:
                eb = base_arm.data.edit_bones.new(name)
                eb.head = head
                eb.tail = tail if (tail - head).length > 1e-4 else head + Vector((0.0, 0.0, 1.0))
                eb.roll = 0.0
            for name, _h, _t, parent in want:         # parent after all exist
                if not parent:
                    continue
                child = base_arm.data.edit_bones.get(name)
                par = base_arm.data.edit_bones.get(parent)
                if child and par:
                    child.parent = par
            bpy.ops.object.mode_set(mode="OBJECT")
            base_bones.update(name for name, _h, _t, _p in want)
        for m in mesh.modifiers:
            if m.type == "ARMATURE":
                m.object = base_arm
        mesh.parent = base_arm
    if arm is not base_arm:
        bpy.data.objects.remove(arm, do_unlink=True)

# ---- neutral material on every slot (VT textures are not available via umodel) ----
clay = bpy.data.materials.get("TFD_Clay") or bpy.data.materials.new("TFD_Clay")
clay.use_nodes = True
bsdf = clay.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.74, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
for mesh in meshes_all:
    if not mesh.data.materials:
        mesh.data.materials.append(clay)
    else:
        for i in range(len(mesh.data.materials)):
            mesh.data.materials[i] = clay
    for poly in mesh.data.polygons:
        poly.use_smooth = True

report["rig"] = {"bones": len(base_arm.data.bones)}
report["meshes"] = len(meshes_all)


# ---------------------------------------------------------------- preview
def frame_points(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, mx - mn


def render(path, center, ortho_scale, size, forward):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "VERTICAL"
    cam_data.ortho_scale = ortho_scale
    cam_data.clip_end = max(size) * 100 + 1000
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    dist = max(ortho_scale, 100) * 3
    cam.location = center + forward * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    log("rendered " + path)


if not NO_PREVIEW:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 32
    scene.view_settings.view_transform = "Filmic"
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
    scene.world = world
    center, extent = frame_points(meshes_all)
    height = max(extent.z, extent.x, extent.y, 1e-6)
    forward = Vector((0.0, -1.0, 0.0))            # TFD meshes face -Y in this import
    side = forward.cross(Vector((0.0, 0.0, 1.0)))
    for name, (f, s, z), energy in (("Key", (1.0, 0.7, 1.2), 3.0), ("Fill", (0.6, -1.0, 0.4), 1.3),
                                    ("Rim", (-0.8, -0.2, 1.0), 1.7)):
        light = bpy.data.lights.new(name, "SUN")
        light.energy = energy
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + (forward * f + side * s + Vector((0.0, 0.0, z))) * height
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    preview = os.path.join(OUT_DIR, "preview.png")
    render(preview, center, height * 1.28, (900, 1400), forward)
    report["preview"] = preview
    head = base_arm.data.bones.get("head") or base_arm.data.bones.get("Head")
    if head is not None:
        head_pos = base_arm.matrix_world @ head.head_local
        render(os.path.join(OUT_DIR, "preview_face.png"),
               head_pos + Vector((0.0, 0.0, height * 0.03)), height * 0.20, (900, 900), forward)
        report["preview_face"] = os.path.join(OUT_DIR, "preview_face.png")

os.makedirs(OUT_DIR, exist_ok=True)
blend = os.path.join(OUT_DIR, MODEL_ID + ".blend")
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False)
report["blend"] = blend
print("TFD_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
