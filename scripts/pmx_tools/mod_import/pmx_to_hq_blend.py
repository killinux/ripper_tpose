# Import a PMX with mmd_tools and turn its materials into "HQ" node materials from the texture set next to the base
# colour map, then pack and save a .blend (+ a 900x1400 preview).  Naming conventions:
#   MHW:   <x>_BM.png / <x>_BML.png = base colour; <x>_NM.png = normal (BC5: RG only, B rebuilt); <x>_RMT.png =
#          R roughness, G metallic; <x>_EM.png = emissive
#   Skyrim: <x>.png = diffuse; <x>_n.png = normal (alpha = specular); <x>_m.png = env/metal mask
#   blender -b --factory-startup --python pmx_to_hq_blend.py -- --pmx P --out X.blend [--tex-dir D] [--preview P.png]
import argparse
import math
import os
import sys

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--pmx", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--tex-dir", default="", help="folder holding the extra maps (default: the PMX's textures folder)")
ap.add_argument("--preview", default="")
ap.add_argument("--scale", type=float, default=0.08)
args = ap.parse_args(argv)

bpy.ops.wm.read_homefile(use_empty=True)
addon_utils.enable("mmd_tools", default_set=True)
try:
    bpy.context.preferences.addons["mmd_tools"].preferences.shared_toon_folder = r"E:\tools\MikuMikuDanceE_v932x64\Data"
except Exception:
    pass
bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=args.scale, types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"})
tex_dir = args.tex_dir or os.path.join(os.path.dirname(os.path.abspath(args.pmx)), "textures")


def find_map(base_png, suffixes):
    stem = os.path.splitext(os.path.basename(base_png))[0]
    for cut in ("_BM", "_BML"):
        if stem.endswith(cut):
            stem = stem[: -len(cut)]
    for suf in suffixes:
        p = os.path.join(tex_dir, stem + suf + ".png")
        if os.path.isfile(p):
            return p
    return None


def image(path, non_color):
    for im in bpy.data.images:
        if im.filepath and os.path.abspath(bpy.path.abspath(im.filepath)) == os.path.abspath(path):
            img = im
            break
    else:
        img = bpy.data.images.load(path)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


done = 0
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    nt = mat.node_tree
    tex_nodes = [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image and n.image.filepath]
    if not tex_nodes:
        continue
    base = bpy.path.abspath(tex_nodes[0].image.filepath)
    nm = find_map(base, ["_NM", "_n"])
    rmt = find_map(base, ["_RMT"])
    em = find_map(base, ["_EM"])
    skm = find_map(base, ["_m"])
    if not (nm or rmt or em or skm):
        continue
    # rebuild: keep mmd_tools' diffuse image, add a Principled chain with the maps
    out_node = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out_node is None:
        continue
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 300)
    base_tex = nt.nodes.new("ShaderNodeTexImage")
    base_tex.image = tex_nodes[0].image
    base_tex.location = (-600, 400)
    nt.links.new(base_tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(base_tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    mat.blend_method = "HASHED"
    if nm:
        n_tex = nt.nodes.new("ShaderNodeTexImage")
        n_tex.image = image(nm, True)
        n_tex.location = (-900, -100)
        if nm.endswith("_NM.png"):                      # BC5: only R/G - rebuild B
            sep = nt.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-650, -100)
            comb = nt.nodes.new("ShaderNodeCombineRGB")
            comb.location = (-450, -100)
            comb.inputs[2].default_value = 1.0
            nt.links.new(n_tex.outputs["Color"], sep.inputs[0])
            nt.links.new(sep.outputs[0], comb.inputs[0])
            nt.links.new(sep.outputs[1], comb.inputs[1])
            src = comb.outputs[0]
        else:
            src = n_tex.outputs["Color"]
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-250, -100)
        nmap.inputs["Strength"].default_value = 1.0
        nt.links.new(src, nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        if nm.endswith("_n.png"):                       # Skyrim: alpha = specular -> roughness
            inv = nt.nodes.new("ShaderNodeInvert")
            inv.location = (-250, -400)
            nt.links.new(n_tex.outputs["Alpha"], inv.inputs["Color"])
            nt.links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])
    if rmt:
        r_tex = nt.nodes.new("ShaderNodeTexImage")
        r_tex.image = image(rmt, True)
        r_tex.location = (-900, -500)
        sep2 = nt.nodes.new("ShaderNodeSeparateRGB")
        sep2.location = (-600, -500)
        nt.links.new(r_tex.outputs["Color"], sep2.inputs[0])
        nt.links.new(sep2.outputs[0], bsdf.inputs["Roughness"])
        nt.links.new(sep2.outputs[1], bsdf.inputs["Metallic"])
    if skm:
        m_tex = nt.nodes.new("ShaderNodeTexImage")
        m_tex.image = image(skm, True)
        m_tex.location = (-900, -700)
        nt.links.new(m_tex.outputs["Color"], bsdf.inputs["Metallic"])
    if em:
        e_tex = nt.nodes.new("ShaderNodeTexImage")
        e_tex.image = image(em, False)
        e_tex.location = (-900, -900)
        nt.links.new(e_tex.outputs["Color"], bsdf.inputs["Emission"])
        bsdf.inputs["Emission Strength"].default_value = 2.0
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    done += 1
print("HQ materials:", done, "of", len(bpy.data.materials))

# pack and save
try:
    bpy.ops.file.pack_all()
except Exception as e:
    print("pack:", e)
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0     # re-running over an archive: no .blend1 backups
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out), compress=True)
print("saved", args.out)

if args.preview:
    scene = bpy.context.scene
    for o in list(scene.objects):
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"      # mmd_tools' import leaves an animation format behind
    scene.render.resolution_x, scene.render.resolution_y = 900, 1400
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.62, 1)
    scene.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(20))
    scene.collection.objects.link(sun)
    from mathutils import Vector
    meshes = [o for o in scene.objects if o.type == "MESH"]
    lo = Vector((min(min((o.matrix_world @ Vector(c))[i] for c in o.bound_box) for o in meshes) for i in range(3)))
    hi = Vector((max(max((o.matrix_world @ Vector(c))[i] for c in o.bound_box) for o in meshes) for i in range(3)))
    centre = (lo + hi) / 2
    size = max(hi.z - lo.z, (hi.x - lo.x) * 1400 / 900) * 1.1
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = centre + Vector((0, -5, 0))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.abspath(args.preview)
    bpy.ops.render.render(write_still=True)
    print("preview", args.preview)
print("HQ_BLEND_DONE")
