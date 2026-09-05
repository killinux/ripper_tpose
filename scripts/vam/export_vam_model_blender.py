"""Build a VaM look or clothing item in Blender and render a preview.

Blender-side worker for ``export_vam_models.py``.  It reads the ``model.json``
+ ``model.npz`` + ``_textures/`` bundle the Python side assembled (vertices are
already in Blender axes, polygons already wound for them), creates one mesh
object per entry, builds Principled materials from the texture roles, packs
the images and writes a .blend (and optionally .glb) plus one composite
preview PNG (3/4, front, head) beside it.

Usage:
  blender --background --python export_vam_model_blender.py -- \
      <model_dir> <out.blend> <validate|export> [blend,glb] [preview:0|1]

Result marker (ASCII JSON on stdout):  VAM_EXPORT={...}
"""

import json
import math
import os
import sys
import traceback

import bpy
import numpy as np
from mathutils import Vector

RESULT_PREFIX = "VAM_EXPORT="
PREVIEW_VIEWS = ("hero", "front", "head")


def result(status, **details):
    print(RESULT_PREFIX + json.dumps({"status": status, **details},
                                     ensure_ascii=True, sort_keys=True), flush=True)


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

_IMAGE_CACHE = {}


def load_image(texture_dir, name, non_color=False):
    if not name:
        return None
    path = os.path.join(texture_dir, name)
    if not os.path.isfile(path):
        return None
    key = (path, non_color)
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    image = bpy.data.images.load(path, check_existing=not non_color)
    if non_color:
        # A dedicated datablock so the same file can be sRGB elsewhere.
        if image.colorspace_settings.name != "Non-Color" and image.users > 1:
            image = bpy.data.images.load(path, check_existing=False)
        image.colorspace_settings.name = "Non-Color"
    _IMAGE_CACHE[key] = image
    return image


def build_material(spec, texture_dir, stats):
    material = bpy.data.materials.new(spec.get("name") or "Material")
    material.use_nodes = True
    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    output = nodes.get("Material Output")
    bsdf.inputs["Roughness"].default_value = float(spec.get("roughness", 0.55))
    bsdf.inputs["Specular"].default_value = 0.35
    color = spec.get("color")
    if color:
        rgb = [max(0.0, min(1.0, float(c))) for c in color[:3]]
    else:
        rgb = [1.0, 1.0, 1.0]

    if spec.get("glass"):
        # Cornea / eye reflection / tear film: clear coat over the eye.
        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Alpha"].default_value = 0.08
        bsdf.inputs["Specular"].default_value = 0.6
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"
        material.show_transparent_back = False
        return material

    y = 300
    diffuse = load_image(texture_dir, spec.get("diffuse"))
    if diffuse is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = diffuse
        tex.location = (-620, y)
        if color and any(abs(c - 1.0) > 0.01 for c in rgb):
            mix = nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs["Fac"].default_value = 1.0
            mix.inputs["Color2"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            mix.location = (-320, y)
            links.new(tex.outputs["Color"], mix.inputs["Color1"])
            links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        stats["textured"] += 1
        diffuse_node = tex
    else:
        bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        diffuse_node = None
        if not spec.get("_unused"):
            stats["untextured"].append(spec.get("name") or "?")
    y -= 300

    normal = load_image(texture_dir, spec.get("normal"), non_color=True)
    if normal is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = normal
        tex.location = (-620, y)
        nmap = nodes.new("ShaderNodeNormalMap")
        nmap.location = (-320, y)
        nmap.inputs["Strength"].default_value = 0.8
        links.new(tex.outputs["Color"], nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        y -= 300

    gloss = load_image(texture_dir, spec.get("gloss"), non_color=True)
    if gloss is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = gloss
        tex.location = (-620, y)
        invert = nodes.new("ShaderNodeInvert")
        invert.location = (-320, y)
        links.new(tex.outputs["Color"], invert.inputs["Color"])
        links.new(invert.outputs["Color"], bsdf.inputs["Roughness"])
        y -= 300

    specular = load_image(texture_dir, spec.get("specular"), non_color=True)
    if specular is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = specular
        tex.location = (-620, y)
        links.new(tex.outputs["Color"], bsdf.inputs["Specular"])
        y -= 300

    alpha = load_image(texture_dir, spec.get("alpha"), non_color=True)
    transparent = bool(spec.get("transparent"))
    if alpha is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = alpha
        tex.location = (-620, y)
        links.new(tex.outputs["Color"], bsdf.inputs["Alpha"])
        transparent = True
    elif transparent and diffuse_node is not None:
        links.new(diffuse_node.outputs["Alpha"], bsdf.inputs["Alpha"])
    adjust = float(spec.get("alphaAdjust", 0.0) or 0.0)
    if transparent and abs(adjust) > 0.005:
        # VaM adds "Alpha Adjust" to the texture alpha; emulate with a Math node.
        add = nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.use_clamp = True
        add.inputs[1].default_value = adjust
        add.location = (-100, -900)
        source = bsdf.inputs["Alpha"].links[0].from_socket \
            if bsdf.inputs["Alpha"].links else None
        if source is not None:
            links.new(source, add.inputs[0])
        else:
            add.inputs[0].default_value = 1.0
        for link in list(bsdf.inputs["Alpha"].links):
            links.remove(link)
        links.new(add.outputs["Value"], bsdf.inputs["Alpha"])
    if spec.get("layer"):
        # Shell wrapped onto the skin (makeup, lips, nails, eye covers): BLEND
        # skips the depth prepass that z-fights a coincident HASHED surface.
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"
        material.show_transparent_back = False
        material.use_backface_culling = True
        return material
    if transparent:
        material.blend_method = "HASHED"
        # No shadows from transparent layers: a makeup/decal shell hovering a
        # fraction of a millimetre above the skin otherwise paints EEVEE's
        # hashed shadow noise onto the whole face.
        material.shadow_method = "NONE"
    material.use_backface_culling = not spec.get("backface", True)
    del output
    return material


# --------------------------------------------------------------------------
# Meshes
# --------------------------------------------------------------------------

def build_object(entry, arrays, texture_dir, stats):
    prefix = entry["prefix"]
    verts = arrays[prefix + "verts"]
    face_len = arrays[prefix + "face_len"]
    face_idx = arrays[prefix + "face_idx"]
    face_mat = arrays[prefix + "face_mat"]
    loop_uv = arrays[prefix + "loop_uv"]

    faces = []
    cursor = 0
    for size in face_len.tolist():
        faces.append(tuple(int(v) for v in face_idx[cursor:cursor + size]))
        cursor += size

    mesh = bpy.data.meshes.new(entry["name"])
    mesh.from_pydata([tuple(map(float, v)) for v in verts], [], faces)
    if len(mesh.polygons) != len(faces):
        raise RuntimeError("%s: Blender kept %d of %d polygons"
                           % (entry["name"], len(mesh.polygons), len(faces)))
    if len(mesh.loops) != loop_uv.shape[0]:
        raise RuntimeError("%s: %d loops vs %d uvs" % (entry["name"], len(mesh.loops),
                                                       loop_uv.shape[0]))
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_layer.data.foreach_set("uv", loop_uv.astype(np.float32).ravel().tolist())
    mesh.polygons.foreach_set("material_index", face_mat.astype(np.int32).tolist())
    mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
    mesh.use_auto_smooth = True
    mesh.auto_smooth_angle = math.radians(60.0)

    used = set(np.unique(face_mat).tolist())
    for index, spec in enumerate(entry["materials"]):
        if index not in used:
            # Slot without polygons (e.g. the graft's "Hidden" material):
            # keep the slot so indices line up, but do not report it.
            spec = dict(spec, name=spec.get("name"), _unused=True)
        mesh.materials.append(build_material(spec, texture_dir, stats))
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(entry["name"], mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def materials_images(objects):
    images = set()
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    images.add(node.image)
    return images


def pack_images(objects):
    packed, failed = [], []
    for image in materials_images(objects):
        if image.source != "FILE" or image.packed_file is not None:
            continue
        try:
            image.pack()
            packed.append(image.name)
        except (OSError, RuntimeError) as exc:
            failed.append("%s: %s" % (image.name, exc))
    return packed, failed


# --------------------------------------------------------------------------
# Preview (same recipe as the ROE clothed-character worker)
# --------------------------------------------------------------------------

def setup_preview_world():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("preview_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    background.inputs[1].default_value = 1.35
    scene.world = world
    for name, energy, rotation in (
        ("key", 3.2, (0.95, 0.0, 0.65)),
        ("fill", 1.1, (1.15, 0.0, -2.2)),
    ):
        data = bpy.data.lights.new(name, type="SUN")
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation


def mesh_bounds(objects):
    points = [obj.matrix_world @ Vector(corner)
              for obj in objects for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points),
                  min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points),
                   max(p.z for p in points)))
    return low, high


def render_view(camera, camera_data, target, ortho, direction, size, path):
    camera_data.ortho_scale = max(ortho, 0.01)
    camera.location = target + direction * size
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler())
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def image_array(path):
    image = bpy.data.images.load(path)
    try:
        width, height = image.size
        pixels = np.array(image.pixels[:], dtype=np.float32)
        return pixels.reshape(height, width, image.channels)
    finally:
        bpy.data.images.remove(image)


def compose_preview(tiles, out_path):
    height = max(tile.shape[0] for tile in tiles)
    backdrop = tiles[0][0, 0].copy()
    padded = []
    for tile in tiles:
        if tile.shape[0] != height:
            pad = np.empty((height, tile.shape[1], tile.shape[2]), dtype=np.float32)
            pad[:, :] = backdrop
            offset = (height - tile.shape[0]) // 2
            pad[offset:offset + tile.shape[0]] = tile
            tile = pad
        padded.append(tile)
    combined = np.concatenate(padded, axis=1)
    out_height, out_width, channels = combined.shape
    image = bpy.data.images.new("preview", width=out_width, height=out_height,
                                alpha=channels > 3)
    try:
        image.pixels = combined.ravel().tolist()
        image.filepath_raw = out_path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)
    return out_path


def render_preview(objects, out_path, scratch_prefix, has_body):
    setup_preview_world()
    scene = bpy.context.scene
    low, high = mesh_bounds(objects)
    center = (low + high) * 0.5
    extent = high - low
    distance = max(extent.length, 0.1) * 2.0

    camera_data = bpy.data.cameras.new("preview_cam")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("preview_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    tall = max(extent.z, extent.x, extent.y)
    head_target = Vector((center.x, center.y, high.z - extent.z * 0.10))
    plans = {
        "hero": (center, tall * 1.12, Vector((-0.75, -0.95, 0.12)).normalized(), 620, 940),
        "front": (center, tall * 1.12, Vector((0.0, -1.0, 0.0)), 620, 940),
        "head": (head_target, tall * 0.26, Vector((0.0, -1.0, 0.05)).normalized(), 620, 620),
    }
    views = PREVIEW_VIEWS if has_body else ("hero", "front")
    tiles = []
    temporaries = []
    for name in views:
        target, ortho, direction, width, height = plans[name]
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        tile_path = "%s_%s.png" % (scratch_prefix, name)
        render_view(camera, camera_data, target, ortho, direction, distance, tile_path)
        temporaries.append(tile_path)
        tiles.append(image_array(tile_path))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    compose_preview(tiles, out_path)
    for path in temporaries:
        try:
            os.remove(path)
        except OSError:
            pass
    return out_path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 3:
        result("FAIL", error="usage: <model_dir> <out.blend> <validate|export> "
                             "[formats] [preview]")
        return
    model_dir, out_blend, mode = argv[0], argv[1], argv[2]
    formats = [f for f in (argv[3] if len(argv) > 3 else "blend").split(",") if f]
    preview = (argv[4] if len(argv) > 4 else "1") == "1"

    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        with open(os.path.join(model_dir, "model.json"), encoding="utf-8") as handle:
            model = json.load(handle)
        arrays = np.load(os.path.join(model_dir, "model.npz"))
        texture_dir = os.path.join(model_dir, model.get("textureDir", "_textures"))
        stats = {"textured": 0, "untextured": []}
        objects = [build_object(entry, arrays, texture_dir, stats)
                   for entry in model["objects"]]
        has_body = any(entry.get("role") == "body" for entry in model["objects"])
        material_count = sum(len(obj.material_slots) for obj in objects)
        packed, pack_failed = pack_images(objects)
        if pack_failed:
            raise RuntimeError("packing failed: %s" % "; ".join(pack_failed))
        details = {
            "objects": len(objects), "materials": material_count,
            "textures": stats["textured"], "packed_images": len(packed),
            "untextured_slots": stats["untextured"],
            "polygons": sum(len(obj.data.polygons) for obj in objects),
        }
        if mode == "validate":
            result("PASS", **details)
            return
        os.makedirs(os.path.dirname(out_blend), exist_ok=True)
        outputs = []
        preview_path = None
        if preview:
            preview_path = os.path.splitext(out_blend)[0] + "_preview.png"
            scratch = os.path.join(os.path.dirname(out_blend), "_preview_tmp")
            render_preview(objects, preview_path, scratch, has_body)
            # Do not save preview helpers into the deliverable.
            for name in ("preview_cam", "key", "fill"):
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    bpy.data.objects.remove(obj, do_unlink=True)
        if "blend" in formats:
            bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=True)
            outputs.append(out_blend)
        if "glb" in formats:
            glb_dir = os.path.join(os.path.dirname(out_blend), "glb")
            os.makedirs(glb_dir, exist_ok=True)
            glb_path = os.path.join(glb_dir, os.path.splitext(os.path.basename(out_blend))[0]
                                    + ".glb")
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB",
                                      use_selection=True, export_apply=True)
            outputs.append(glb_path)
        result("PASS", output=out_blend if "blend" in formats else outputs[0],
               outputs=outputs, preview=preview_path, **details)
    except Exception as exc:  # noqa: BLE001 - reported through the marker
        result("FAIL", error=str(exc), traceback=traceback.format_exc())


if __name__ == "__main__":
    main()
