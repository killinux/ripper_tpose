# DOA6 角色组装（Blender 3.6 无头）：
# 输入若干部件目录（各含 <part>.fbx、matmap.json、_png\<贴图>.png），
# 导入拼场景、按 matmap 挂 albedo/normal、打包贴图、存 .blend、渲预览。
#
# 用法：
#   blender --background --factory-startup --python build_blend.py -- \
#       <out.blend> <preview.png|-> <部件目录1> [部件目录2 ...]

import bpy
import json
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
out_blend, preview_png = argv[0], argv[1]
part_dirs = argv[2:]

bpy.ops.wm.read_factory_settings(use_empty=True)

def build_material(name, alb_png, nmh_png):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "HASHED"
    mat.shadow_method = "HASHED"
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if alb_png and os.path.exists(alb_png):
        img = bpy.data.images.load(alb_png, check_existing=True)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-400, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if nmh_png and os.path.exists(nmh_png):
        img = bpy.data.images.load(nmh_png, check_existing=True)
        img.colorspace_settings.name = "Non-Color"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-500, -100)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-200, -100)
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat

for pdir in part_dirs:
    part = os.path.basename(pdir.rstrip("\\/"))
    fbx = os.path.join(pdir, part + ".fbx")
    with open(os.path.join(pdir, "matmap.json"), encoding="utf-8") as f:
        matmap = json.load(f)

    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx)
    new_objs = [o for o in bpy.data.objects if o not in before]

    # matmap: submesh index -> material index -> 贴图；同材质共享
    sm_info = {s["index"]: s for s in matmap["submeshes"]}
    mat_cache = {}
    for obj in new_objs:
        if obj.type != "MESH":
            if obj.type == "ARMATURE":
                obj.name = part + "_armature"
            continue
        base = obj.name.split(".")[0]  # model_0_submesh_N[.001]
        try:
            idx = int(base.rsplit("_", 1)[1])
        except ValueError:
            continue
        info = sm_info.get(idx)
        obj.name = "%s_sm%d" % (part, idx)
        if not info:
            continue
        mi = info["material"]
        if mi not in mat_cache:
            alb = nmh = None
            for t in info["textures"]:
                png = os.path.join(pdir, "_png", t["name"].replace(".g1t", ".png"))
                if t["channel"] == "alb" and alb is None:
                    alb = png
                elif t["channel"] == "nmh" and nmh is None:
                    nmh = png
            mat_cache[mi] = build_material("%s_mat%d" % (part, mi), alb, nmh)
        obj.data.materials.clear()
        obj.data.materials.append(mat_cache[mi])

# 打包贴图进 .blend（FBX 会带进指向不存在文件的占位 Image，逐个处理而非 pack_all）
for img in list(bpy.data.images):
    if img.packed_file:
        continue
    fp = bpy.path.abspath(img.filepath) if img.filepath else ""
    if fp and os.path.exists(fp):
        img.pack()
    else:
        bpy.data.images.remove(img)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("SAVED_BLEND=" + out_blend)

if preview_png != "-":
    # 相机自动取景 + 渲染
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    xs, ys, zs = [], [], []
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ __import__("mathutils").Vector(c)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    cx, cy, cz = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2
    h = max(max(xs)-min(xs), max(zs)-min(zs), max(ys)-min(ys))
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    dist = h * 1.6
    cam.location = (cx + dist * 0.35, cy - dist, cz + h * 0.08)
    direction = __import__("mathutils").Vector((cx, cy, cz)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.2
    bpy.context.scene.world = world
    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(30))
    bpy.context.collection.objects.link(sun)

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 900
    sc.render.resolution_y = 1400
    sc.render.filepath = preview_png
    bpy.ops.render.render(write_still=True)
    print("SAVED_PREVIEW=" + preview_png)

print("BUILD_BLEND=PASS")
