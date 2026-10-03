# -*- coding: utf-8 -*-
"""Check an exported XPS the way XNALara / XPS will see it: import it back with the XNALaraMesh
add-on and render the rest pose next to a test pose (arm down, knee bent, head turned - a wrong
weight or a mis-parented bone shows at once).

    blender -b --python preview_xps_blender.py -- --xps <model.xps> [--out <png>]

Writes <name>_xps_preview.png next to the .xps (two tiles side by side).  Needs the XNALaraMesh
add-on (the importer the user works with).  The last line printed is XPS_PREVIEW={json}.
"""
import argparse
import json
import math
import os
import sys
import tempfile

import addon_utils
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--xps", required=True)
ap.add_argument("--out", default="")
args = ap.parse_args(argv)
out_path = args.out or os.path.splitext(os.path.abspath(args.xps))[0] + "_xps_preview.png"
report = {"xps": args.xps, "preview": out_path}

bpy.ops.wm.read_homefile(use_empty=True)
if not (hasattr(bpy.ops, "xps_tools") and hasattr(bpy.ops.xps_tools, "import_model")):
    for name in ("XNALaraMesh-master", "XNALaraMesh", "xps_tools"):
        try:
            addon_utils.enable(name, default_set=False)
        except Exception:  # noqa: BLE001
            continue
        if hasattr(bpy.ops, "xps_tools") and hasattr(bpy.ops.xps_tools, "import_model"):
            break
if not (hasattr(bpy.ops, "xps_tools") and hasattr(bpy.ops.xps_tools, "import_model")):
    raise SystemExit("the XNALaraMesh add-on (bpy.ops.xps_tools.import_model) is not installed")
bpy.ops.xps_tools.import_model(filepath=os.path.abspath(args.xps))
scene = bpy.context.scene
arm = next((o for o in scene.objects if o.type == "ARMATURE"), None)
meshes = [o for o in scene.objects if o.type == "MESH"]
report.update(bones=len(arm.data.bones) if arm else 0, meshes=len(meshes),
              vertices=sum(len(m.data.vertices) for m in meshes))
if not meshes:
    raise SystemExit("nothing imported from %s" % args.xps)

pts = [m.matrix_world @ Vector(c) for m in meshes for c in m.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, extent = (lo + hi) / 2, hi - lo
report["size"] = [round(extent.x, 3), round(extent.y, 3), round(extent.z, 3)]
# which way does it face?  the toes are in front of the ankles
front = Vector((0.0, -1.0, 0.0))
if arm is not None:
    ankle, toes = arm.data.bones.get("leg left ankle"), arm.data.bones.get("leg left toes")
    if ankle is not None and toes is not None:
        d = arm.matrix_world.to_3x3() @ (toes.head_local - ankle.head_local)
        d.z = 0.0
        if d.length > 1e-4:
            front = d.normalized()

scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
scene.eevee.taa_render_samples = 32
world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.42, 0.44, 0.48, 1.0)
bg.inputs["Strength"].default_value = 1.0
scene.world = world
for name, direction, energy in (("key", front + Vector((0.4, 0.0, 0.7)), 2.2), ("fill", front * 0.5 + Vector((-0.8, 0.0, 0.2)), 0.9),
                                ("rim", -front + Vector((0.0, 0.0, 0.6)), 1.2)):
    light = bpy.data.lights.new(name, "SUN")
    light.energy = energy
    obj = bpy.data.objects.new(name, light)
    scene.collection.objects.link(obj)
    obj.rotation_euler = direction.normalized().to_track_quat("Z", "Y").to_euler()


def render(path, direction):
    cam_data = bpy.data.cameras.new("c")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(extent.z * 1.08, max(extent.x, extent.y) * 1.08 * 1400 / 900)
    cam = bpy.data.objects.new("c", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + direction.normalized() * 8.0
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 900, 1400
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def turn(bone_name, world_axis, degrees):
    pb = arm.pose.bones.get(bone_name) if arm else None
    if pb is None:
        return False
    rest = (arm.matrix_world @ pb.bone.matrix_local).to_3x3()
    axis = rest.inverted() @ Vector(world_axis)
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = Matrix.Rotation(math.radians(degrees), 3, axis).to_quaternion()
    return True


tmp = tempfile.mkdtemp(prefix="xps_preview_")
render(os.path.join(tmp, "rest.png"), front)
side = Vector((0.0, 0.0, 1.0)).cross(front)             # the character's left
posed = [turn("arm left shoulder 2", front, -55.0), turn("arm right shoulder 2", front, 35.0),
         turn("arm right elbow", side, 60.0), turn("leg right thigh", side, 55.0),
         turn("leg right knee", side, -70.0), turn("head neck upper", (0.0, 0.0, 1.0), 30.0),
         turn("spine upper", (0.0, 0.0, 1.0), -15.0)]
report["posed_bones"] = sum(1 for p in posed if p)
bpy.context.view_layer.update()
render(os.path.join(tmp, "pose.png"), front + side * 0.55)


def pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    return buf.reshape(h, w, 4)


a, b = pixels(os.path.join(tmp, "rest.png")), pixels(os.path.join(tmp, "pose.png"))
sheet = np.concatenate([a, b], axis=1)
image = bpy.data.images.new("xps_preview", sheet.shape[1], sheet.shape[0], alpha=True)
image.pixels.foreach_set(sheet.ravel())
image.filepath_raw = out_path
image.file_format = "PNG"
scene.view_settings.view_transform = "Standard"
image.save()
print("XPS_PREVIEW=" + json.dumps(report, ensure_ascii=False), flush=True)
