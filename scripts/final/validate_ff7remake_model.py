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
    return parser.parse_args(argv)


def operator_exists(module_name: str, operator_name: str) -> bool:
    try:
        operator = getattr(getattr(bpy.ops, module_name), operator_name)
        operator.get_rna_type()
        return True
    except (AttributeError, KeyError, RuntimeError):
        return False


def import_psk(path: str):
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
    values: dict[str, str] = {}
    if not os.path.isfile(path):
        return values
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            key, separator, value = line.strip().partition("=")
            if separator and key in {"Diffuse", "Normal"}:
                values[key] = value.strip()
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


def wire_materials(meshes, material_dir: str, asset_root: str):
    index = image_index(asset_root)
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
            properties = parse_material(os.path.join(material_dir, base_name + ".mat"))
            diffuse = resolve_image(index, properties.get("Diffuse", ""))
            normal = resolve_image(index, properties.get("Normal", ""))
            alpha_name = ""
            diffuse_name = properties.get("Diffuse", "")
            if diffuse_name.endswith("_C"):
                alpha_name = diffuse_name[:-2] + "_A"
            alpha = resolve_image(index, alpha_name) if alpha_name else ""

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
                    material.use_screen_refraction = False
                elif any(token in base_name.lower() for token in ("hair", "eyelash", "eyebrow")):
                    links.new(color.outputs["Alpha"], principled.inputs["Alpha"])
                    material.blend_method = "HASHED"
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
        background.inputs["Color"].default_value = (0.045, 0.045, 0.045, 1.0)
        background.inputs["Strength"].default_value = 0.45
    scene.view_settings.exposure = 1.0
    scene.view_settings.look = "Medium High Contrast"

    camera_data = bpy.data.cameras.new("ValidationCamera")
    camera = bpy.data.objects.new("ValidationCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(extent.z * 1.12, extent.y * 1.45)
    camera.location = Vector((maximum.x + max(extent.z, 200.0) * 2.2, center.y, center.z))
    look_at(camera, center)

    lights = [
        ("Key", (250.0, -180.0, 260.0), 4200.0, 180.0),
        ("Fill", (180.0, 220.0, 150.0), 2600.0, 200.0),
        ("Rim", (-160.0, 20.0, 250.0), 3200.0, 160.0),
    ]
    for name, location, energy, size in lights:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
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

    materials, missing = wire_materials(meshes, material_dir, asset_root)
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
    }
    if args.report:
        report_path = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print("FF7REMAKE_MODEL_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
