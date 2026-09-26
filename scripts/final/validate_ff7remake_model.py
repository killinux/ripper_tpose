"""Import and validate an FF7 Remake ActorX character in Blender 3.6.

Example::

    blender --background --python validate_ff7remake_model.py -- \
      --model PC0002_01.pskx --asset-root D:\\ff7remake_exports\\tifa_purple_dress \
      --material-dir Material --output Tifa_PurpleDress.blend \
      --render Tifa_PurpleDress.png --report Tifa_PurpleDress.json

The preview material is intentionally basic.  It resolves the Diffuse and
Normal entries written by UE Viewer, uses a sibling alpha mask when present,
and converts Unreal's DirectX normal-map green channel to Blender's OpenGL
convention.  Packed renderer-specific masks are preserved in the export but
are not guessed here.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--asset-root", required=True)
    parser.add_argument("--material-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", default="")
    parser.add_argument("--report", default="")
    # mod exports: textures/.mat under this root win over same-named ones in --asset-root
    parser.add_argument("--overlay-root", default="")
    # {material instance: {parameter: texture}} (ff7_mod_export.py, from "umodel -dump")
    parser.add_argument("--material-params", default="")
    return parser.parse_args(argv)


def operator_exists(module_name: str, operator_name: str) -> bool:
    try:
        operator = getattr(getattr(bpy.ops, module_name), operator_name)
        operator.get_rna_type()
        return True
    except (AttributeError, KeyError, RuntimeError):
        return False


def import_psk(path: str):
    if path.lower().endswith((".gltf", ".glb")):
        # FF7R-mesh-importer output (mod meshes the Remake UE Viewer build cannot read)
        return bpy.ops.import_scene.gltf(filepath=path)
    if operator_exists("psk", "import_file"):
        return bpy.ops.psk.import_file(filepath=path)
    if operator_exists("import_scene", "psk"):
        return bpy.ops.import_scene.psk(filepath=path)
    raise RuntimeError(
        "No PSK importer is registered; enable io_scene_psk_psa 5.0.6 in Blender 3.6"
    )


def clear_scene():
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object else None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def parse_material(path: str) -> dict[str, str]:
    """读 UE Viewer 写的 .mat：Diffuse/Normal 直接取，Other[n] 全部收进 "_refs"（材质实际引用的贴图名集合）。"""
    values: dict[str, str] = {}
    refs: set[str] = set()
    if not os.path.isfile(path):
        return values
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            key, separator, value = line.strip().partition("=")
            if not separator:
                continue
            value = value.strip()
            if key in {"Diffuse", "Normal"}:
                values[key] = value
            refs.add(value.lower())
    values["_refs"] = refs  # type: ignore[assignment]
    return values


def image_index(asset_root: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for root, _dirs, files in os.walk(asset_root):
        for filename in files:
            if os.path.splitext(filename)[1].lower() not in {".png", ".tga", ".hdr"}:
                continue
            stem = os.path.splitext(filename)[0].lower()
            index.setdefault(stem, []).append(os.path.join(root, filename))
    return index


def material_index(asset_root: str) -> dict[str, str]:
    """整个导出根下的 .mat：变体包（如 Yuffie Moogle）会直接引用基础包（Yuffie Standard）的材质，
    自己的 Material 目录里没有对应 .mat，要到别的包目录去找。"""
    index: dict[str, str] = {}
    for root, _dirs, files in os.walk(asset_root):
        for filename in files:
            if filename.lower().endswith(".mat"):
                index.setdefault(filename[:-4].lower(), os.path.join(root, filename))
    return index


def resolve_image(index: dict[str, list[str]], name: str) -> str:
    matches = index.get(name.lower(), [])
    if not matches:
        return ""
    return sorted(matches, key=lambda path: (len(path), path.lower()))[0]


def image_node(nodes, path: str, name: str, colorspace: str):
    node = nodes.new("ShaderNodeTexImage")
    node.name = name
    node.label = name
    node.image = bpy.data.images.load(path, check_existing=True)
    try:
        node.image.colorspace_settings.name = colorspace
    except TypeError:
        pass
    return node


def connect_directx_normal(nodes, links, texture_node, principled):
    separate = nodes.new("ShaderNodeSeparateRGB")
    invert_green = nodes.new("ShaderNodeMath")
    invert_green.operation = "SUBTRACT"
    invert_green.inputs[0].default_value = 1.0
    combine = nodes.new("ShaderNodeCombineRGB")
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = 0.8
    links.new(texture_node.outputs["Color"], separate.inputs["Image"])
    links.new(separate.outputs["R"], combine.inputs["R"])
    links.new(separate.outputs["G"], invert_green.inputs[1])
    links.new(invert_green.outputs[0], combine.inputs["G"])
    links.new(separate.outputs["B"], combine.inputs["B"])
    links.new(combine.outputs["Image"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])


def material_basename(name: str) -> str:
    if name.rsplit(".", 1)[-1].isdigit():
        return name.rsplit(".", 1)[0]
    return name


# Mods re-texture body slots with another piece's maps: Remake #967 puts the MarineCharm
# textures on PC0002_01_Skin (the suit), and that material's list then also carries
# MarineCharm_A - which its opaque skin shader never reads.  Wired as alpha it cut holes
# through the torso (the hair behind showed through).  For mod exports a body-like slot
# gets no _A mask; hair / lashes / brows / charms keep theirs.
MOD_OPAQUE_SLOT = re.compile(r"skin|body|suit|dress|tops|bottoms|pants|head|face", re.IGNORECASE)
MOD_ALPHA_SLOT = re.compile(r"hair|lash|brow", re.IGNORECASE)


OPACITY_PARAM = re.compile(r"^(opacity|opacitymask|coverage|alpha|alphamask|transparency)$", re.IGNORECASE)

# masks left off because they would have erased the geometry assigned to them (see below)
MASKS_DROPPED: list[str] = []


def mask_hidden_fraction(meshes, material, mask_path: str) -> float:
    """Share of the faces using ``material`` that the mask would erase completely (every corner
    and the centre on a texel below 0.5).

    Mods park other pieces in a masked slot.  Remake #668 put Tifa's stockings, boots, arm guards
    and earrings into one section on PC0002_00_Earring, whose Coverage map BodyA_A is black
    everywhere except the earring cut-outs: wired as alpha, 98% of that section vanished (no legs,
    no arms), while the mod's own in-game screenshots show all of it.  A mask that would hide
    nearly everything it is given is not a mask for that geometry."""
    import numpy as np

    image = bpy.data.images.load(mask_path, check_existing=True)
    width, height = image.size
    if not width or not height:
        return 0.0
    pixels = np.empty(width * height * image.channels, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    red = pixels.reshape(height, width, image.channels)[:, :, 0]

    def texel(u, v):
        return red[min(height - 1, int((v % 1.0) * height)), min(width - 1, int((u % 1.0) * width))]

    total = hidden = 0
    for mesh in meshes:
        slots = {i for i, slot in enumerate(mesh.material_slots) if slot.material == material}
        layer = mesh.data.uv_layers.active
        if not slots or layer is None:
            continue
        uv = layer.data
        for poly in mesh.data.polygons:
            if poly.material_index not in slots:
                continue
            total += 1
            corners = [uv[li].uv for li in poly.loop_indices]
            centre = (sum(c[0] for c in corners) / len(corners), sum(c[1] for c in corners) / len(corners))
            if texel(*centre) < 0.5 and all(texel(c[0], c[1]) < 0.5 for c in corners):
                hidden += 1
    return hidden / total if total else 0.0


def wire_materials(meshes, material_dir: str, asset_root: str, overlay_root: str = "", params=None):
    index = image_index(asset_root)
    mat_index = material_index(asset_root)
    overlay_mats = {}
    if overlay_root:
        index.update(image_index(overlay_root))          # the mod's own textures win
        overlay_mats = material_index(overlay_root)
    wired = []
    missing = []
    handled = set()
    for mesh in meshes:
        for slot in mesh.material_slots:
            material = slot.material
            if material is None or material.name in handled:
                continue
            handled.add(material.name)
            base_name = material_basename(material.name)
            mat_path = overlay_mats.get(base_name.lower(), os.path.join(material_dir, base_name + ".mat"))
            if not os.path.isfile(mat_path):
                mat_path = mat_index.get(base_name.lower(), mat_path)
            properties = parse_material(mat_path)
            if base_name.lower() in overlay_mats:
                # a mod material instance that only overrides a mask (#1364's MarineCharm: Coverage
                # only) inherits the other textures from its parent, the game's own instance
                base_props = parse_material(mat_index.get(base_name.lower(),
                                                          os.path.join(material_dir, base_name + ".mat")))
                for key in ("Diffuse", "Normal"):
                    if not properties.get(key) and base_props.get(key):
                        properties[key] = base_props[key]
            diffuse = resolve_image(index, properties.get("Diffuse", ""))
            normal = resolve_image(index, properties.get("Normal", ""))
            # 同名 _A 遮罩只在该材质的 .mat 确实引用它时才接 Alpha：
            # 同一张 BodyA_A 常常只被耳环/头发这类 Coverage 材质引用，
            # 而 BodyA 本体不用它——盲目按名字配对会把衣服、丝袜整片透掉（Tifa 踩过）。
            alpha_name = ""
            diffuse_name = properties.get("Diffuse", "")
            if diffuse_name.endswith("_C"):
                candidate = diffuse_name[:-2] + "_A"
                if candidate.lower() in properties.get("_refs", set()):
                    alpha_name = candidate
            table = (params or {}).get(base_name)
            if table is not None:
                # parameter names known: only a texture bound to an opacity-type parameter
                # ("0:5:DetailOpacity" is an emissive-detail mask, not coverage)
                masks = [tex for key, tex in table.items()
                         if tex and OPACITY_PARAM.match(re.sub(r"^[0-9:]+", "", key))]
                alpha_name = next((m for m in masks if m == alpha_name), masks[0] if masks else "")
            alpha = resolve_image(index, alpha_name) if alpha_name else ""
            # A body-like slot of a mod keeps its _A only when the mod repainted the very mask the
            # game's own material for that slot reads: #1364 blacks the purple dress out around a
            # bikini, #1358 cuts it into lace (both ship PC0002_01_PurpleDress_A; the base
            # PurpleDress .mat references it).  Anything else there is a borrowed mask (#967).
            mod_edit = False
            if alpha and table is None and overlay_root and MOD_OPAQUE_SLOT.search(base_name) \
                    and not MOD_ALPHA_SLOT.search(base_name):
                in_mod = os.path.normcase(os.path.abspath(alpha)).startswith(
                    os.path.normcase(os.path.abspath(overlay_root)) + os.sep)
                base_mat = mat_index.get(base_name.lower(), os.path.join(material_dir, base_name + ".mat"))
                mod_edit = in_mod and alpha_name.lower() in parse_material(base_mat).get("_refs", set())
                if not mod_edit:
                    alpha = ""
            # Only a mask the mod did NOT choose is tested: a Coverage map the mod binds in its own
            # material instance is deliberate (#1358 blacks out the MarineCharm necklace that way).
            # Hair / lash / brow cards are thin strands: a card's corners and centre often all fall
            # between strands while the strands still cross it, so they are never tested either.
            if alpha and table is None and not mod_edit and not MOD_ALPHA_SLOT.search(base_name):
                share = mask_hidden_fraction(meshes, material, alpha)
                if share >= 0.9:
                    MASKS_DROPPED.append("%s: %s would hide %.0f%%" % (base_name, os.path.basename(alpha),
                                                                        share * 100))
                    alpha = ""

            material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            nodes.clear()
            output = nodes.new("ShaderNodeOutputMaterial")
            principled = nodes.new("ShaderNodeBsdfPrincipled")
            principled.inputs["Roughness"].default_value = (
                0.32 if "hair" in base_name.lower() else 0.48
            )
            links.new(principled.outputs["BSDF"], output.inputs["Surface"])

            if diffuse:
                color = image_node(nodes, diffuse, "Base Color", "sRGB")
                links.new(color.outputs["Color"], principled.inputs["Base Color"])
                if alpha:
                    alpha_node = image_node(nodes, alpha, "Opacity Mask", "Non-Color")
                    links.new(alpha_node.outputs["Color"], principled.inputs["Alpha"])
                    material.blend_method = "HASHED"
                    material.shadow_method = "HASHED"     # EEVEE: cut-away parts cast no shadow
                    material.use_screen_refraction = False
                elif any(token in base_name.lower() for token in ("hair", "eyelash", "eyebrow")):
                    links.new(color.outputs["Alpha"], principled.inputs["Alpha"])
                    material.blend_method = "HASHED"
                    material.shadow_method = "HASHED"
            else:
                missing.append({"material": base_name, "kind": "Diffuse"})

            if normal:
                normal_node = image_node(nodes, normal, "Normal (DirectX)", "Non-Color")
                connect_directx_normal(nodes, links, normal_node, principled)
            else:
                missing.append({"material": base_name, "kind": "Normal"})

            wired.append(
                {
                    "material": base_name,
                    "diffuse": diffuse,
                    "normal": normal,
                    "alpha": alpha,
                }
            )
    return wired, missing


def scene_bounds(meshes):
    points = [mesh.matrix_world @ vertex.co for mesh in meshes for vertex in mesh.data.vertices]
    if not points:
        raise RuntimeError("Imported model contains no mesh vertices")
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def look_at(obj, target: Vector):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_preview_scene(meshes, render_path: str):
    minimum, maximum = scene_bounds(meshes)
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.62, 0.62, 0.65, 1.0)
        background.inputs["Strength"].default_value = 1.0
    scene.view_settings.exposure = 0.0
    scene.view_settings.look = "None"

    camera_data = bpy.data.cameras.new("ValidationCamera")
    camera = bpy.data.objects.new("ValidationCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(extent.z * 1.12, extent.y * 1.45)
    camera.location = Vector((maximum.x + max(extent.z, 200.0) * 2.2, center.y, center.z))
    look_at(camera, center)

    # 场景单位是厘米（人物 ~170 高），面光在 250cm 外要几万瓦才够；改用太阳光，强度与距离无关
    lights = [
        ("Key", (250.0, -180.0, 260.0), 2.6),
        ("Fill", (180.0, 220.0, 150.0), 1.2),
        ("Rim", (-160.0, 20.0, 250.0), 1.4),
    ]
    for name, location, energy in lights:
        light_data = bpy.data.lights.new(name, "SUN")
        light_data.energy = energy
        light_data.angle = math.radians(12.0)
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = Vector(location)
        look_at(light, center)

    if render_path:
        scene.render.filepath = render_path
        bpy.ops.render.render(write_still=True)
    return minimum, maximum


def main():
    args = parse_args()
    model_path = os.path.abspath(args.model)
    asset_root = os.path.abspath(args.asset_root)
    material_dir = os.path.abspath(args.material_dir)
    output_path = os.path.abspath(args.output)
    render_path = os.path.abspath(args.render) if args.render else ""
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)
    if not os.path.isdir(material_dir):
        raise NotADirectoryError(material_dir)

    clear_scene()
    result = import_psk(model_path)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if "FINISHED" not in result or not meshes or len(armatures) != 1:
        raise RuntimeError("PSK import did not create one complete skeletal model")
    for mesh in meshes:
        for polygon in mesh.data.polygons:
            polygon.use_smooth = True
        mesh.data.update()

    overlay_root = os.path.abspath(args.overlay_root) if args.overlay_root else ""
    params = {}
    if args.material_params and os.path.isfile(args.material_params):
        with open(args.material_params, encoding="utf-8") as handle:
            params = json.load(handle)
    materials, missing = wire_materials(meshes, material_dir, asset_root, overlay_root, params)
    minimum, maximum = create_preview_scene(meshes, render_path)
    armature = armatures[0]
    weighted_groups = set()
    bound_meshes = []
    for mesh in meshes:
        for vertex in mesh.data.vertices:
            for assignment in vertex.groups:
                if assignment.weight > 1.0e-8:
                    weighted_groups.add(mesh.vertex_groups[assignment.group].name)
        if any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in mesh.modifiers
        ):
            bound_meshes.append(mesh.name)
    if len(bound_meshes) != len(meshes):
        raise RuntimeError("One or more imported meshes are not bound to the imported armature")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)

    report = {
        "source_model": model_path,
        "output_blend": output_path,
        "render": render_path,
        "meshes": len(meshes),
        "vertices": sum(len(mesh.data.vertices) for mesh in meshes),
        "polygons": sum(len(mesh.data.polygons) for mesh in meshes),
        "armatures": len(armatures),
        "bones": len(armature.data.bones),
        "weighted_vertex_groups": len(weighted_groups),
        "armature_bound_meshes": bound_meshes,
        "material_slots": sum(len(mesh.material_slots) for mesh in meshes),
        "uv_layers": sum(len(mesh.data.uv_layers) for mesh in meshes),
        "bounds": {"min": list(minimum), "max": list(maximum)},
        "materials": materials,
        "missing_preview_textures": missing,
        "masks_dropped": MASKS_DROPPED,
    }
    if args.report:
        report_path = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print("FF7REMAKE_MODEL_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
