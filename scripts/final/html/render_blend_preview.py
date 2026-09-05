"""给已材质化的 .blend 补渲预览图（Blender 3.6 无头）。

FF7 Rebirth 的材质化 worker（export_ff7rb_model_blender.py）不出预览图，画廊需要，
所以单独跑一遍：打开 blend、按所有网格自动取景、太阳光 + 中性灰背景、EEVEE 渲一张。

  blender --background --python render_blend_preview.py -- <blend目录或单个blend> [--force] [--suffix _preview]

输出与 blend 同目录同名 + 后缀 .png。已有且比 blend 新的跳过（--force 重渲）。
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit("用法: -- <blend目录或文件> [--force] [--suffix _preview]")
target = argv[0]
force = "--force" in argv
suffix = argv[argv.index("--suffix") + 1] if "--suffix" in argv else "_preview"

if os.path.isdir(target):
    blends = sorted(os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith(".blend"))
else:
    blends = [target]


def render_one(path):
    out = os.path.splitext(path)[0] + suffix + ".png"
    if not force and os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        print("SKIP", os.path.basename(path))
        return
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    if not meshes:
        print("NOMESH", os.path.basename(path))
        return
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2
    ext = mx - mn
    h = max(ext.z, ext.y, ext.x, 1e-6)

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = "ORTHO"
    # UE/ActorX 导入的人物正面朝 +X（与 validate_ff7remake_model.py 的取景一致），相机放在 +X 侧
    cam_data.ortho_scale = max(ext.z * 1.12, ext.y * 1.45)
    cam_data.clip_start = h * 0.01
    cam_data.clip_end = h * 50
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = Vector((ctr.x + h * 3, ctr.y, ctr.z))
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    for name, loc, energy in (("Key", (1.2, -0.9, 1.2), 2.6), ("Fill", (0.9, 1.0, 0.6), 1.2), ("Rim", (-0.8, 0.2, 1.1), 1.4)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(12)
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = ctr + Vector(loc) * h
        lo.rotation_euler = (ctr - lo.location).to_track_quat("-Z", "Y").to_euler()

    world = scene.world or bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.62, 0.62, 0.65, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 800, 1100
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("RENDERED", out)


for b in blends:
    try:
        render_one(b)
    except Exception as exc:  # noqa: BLE001
        print("FAIL", os.path.basename(b), exc)
print("RENDER_DONE=%d" % len(blends))
