#!/usr/bin/env python3
"""Assemble prepared PRISM BODY/FACE/HAIR glTF components in Blender 3.6.

Run this file through Blender, placing its arguments after Blender's ``--``::

    blender --background --python blender_assemble_character.py -- \
      --character Nanami --body body.gltf --face face.gltf --hair hair.gltf \
      --output-dir output --formats blend,fbx,glb

This is deliberately an assembly-only stage. Character/model selection,
proprietary material-pass flattening, cloth repair, and other model-specific
work must already have been applied to the input glTF files. The assembler
never translates, rotates, scales, welds, splices, or merges components.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree


COMPONENT_COLORS = {
    "BODY": (0.72, 0.55, 0.44, 1.0),
    "FACE": (0.94, 0.68, 0.55, 1.0),
    "HAIR": (0.20, 0.14, 0.10, 1.0),
}
VALID_FORMATS = {"blend", "fbx", "glb"}


def parse_indices(value: str) -> set[int]:
    """Parse a comma-separated material-index set."""
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            index = int(item, 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid material index {item!r}"
            ) from exc
        if index < 0:
            raise argparse.ArgumentTypeError("material indices must be non-negative")
        result.add(index)
    return result


def parse_formats(values: list[str]) -> set[str]:
    requested = {
        item.strip().lower()
        for value in values
        for item in value.split(",")
        if item.strip()
    }
    invalid = requested - VALID_FORMATS
    if invalid:
        raise argparse.ArgumentTypeError(
            "unknown format(s): " + ", ".join(sorted(invalid))
        )
    if not requested:
        raise argparse.ArgumentTypeError("at least one output format is required")
    return requested


def file_stem(value: str) -> str:
    result = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("_.")
    return result or "Character"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", required=True,
                        help="Character display name used in files and reports")
    parser.add_argument("--body", required=True, type=Path,
                        help="Prepared BODY glTF")
    parser.add_argument("--face", required=False, type=Path, default=None,
                        help=(
                            "Prepared FACE glTF; optional for bodies that "
                            "already include a head (e.g. the nude base body)"
                        ))
    parser.add_argument("--hair", required=True, type=Path,
                        help="Prepared HAIR glTF")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Directory receiving models, previews, and reports")
    parser.add_argument(
        "--formats", nargs="+", default=["blend", "fbx", "glb"],
        metavar="FORMAT",
        help="blend, fbx, glb; comma-separated or space-separated",
    )
    parser.add_argument("--body-alpha", default="",
                        help="Comma-separated BODY material indices using alpha")
    parser.add_argument("--face-alpha", default="",
                        help="Comma-separated FACE material indices using alpha")
    parser.add_argument("--hair-alpha", default="",
                        help="Comma-separated HAIR material indices using alpha")
    parser.add_argument(
        "--render-mode", choices=("auto", "clay", "textured"), default="auto"
    )
    parser.add_argument("--preview-size", type=int, default=900)
    parser.add_argument(
        "--skip-previews", action="store_true",
        help="Skip the four assembly and FBX-readback preview renders",
    )
    parser.add_argument(
        "--skip-fbx-roundtrip", action="store_true",
        help="Export FBX but skip its Blender reimport validation",
    )
    parser.add_argument(
        "--keep-roundtrip-blend", action="store_true",
        help="Keep the QA-only FBX reimport Blend (normally removed after validation)",
    )
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    try:
        args.formats = parse_formats(args.formats)
        args.body_alpha = parse_indices(args.body_alpha)
        args.face_alpha = parse_indices(args.face_alpha)
        args.hair_alpha = parse_indices(args.hair_alpha)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.preview_size < 64:
        parser.error("--preview-size must be at least 64")
    return args


def close_vector(value, default, tolerance: float = 1e-7) -> bool:
    return value is None or (
        len(value) == len(default)
        and all(
            abs(float(actual) - float(expected)) <= tolerance
            for actual, expected in zip(value, default)
        )
    )


def source_audit(path: Path) -> dict:
    """Audit one external-buffer glTF before Blender imports it."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read glTF JSON {path}: {exc}") from exc
    scenes = document.get("scenes", [])
    if not scenes:
        raise RuntimeError(f"glTF has no scenes: {path}")
    scene_index = int(document.get("scene", 0))
    if scene_index < 0 or scene_index >= len(scenes):
        raise RuntimeError(f"glTF scene index is out of range: {path}")
    roots = list(scenes[scene_index].get("nodes", []))
    nodes = document.get("nodes", [])
    non_identity = []
    for index in roots:
        if index < 0 or index >= len(nodes):
            raise RuntimeError(f"glTF root node index {index} is invalid: {path}")
        node = nodes[index]
        matrix_ok = close_vector(
            node.get("matrix"),
            (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        )
        if not (
            matrix_ok
            and close_vector(node.get("translation"), (0, 0, 0))
            and close_vector(node.get("rotation"), (0, 0, 0, 1))
            and close_vector(node.get("scale"), (1, 1, 1))
        ):
            non_identity.append({
                "index": index,
                "name": node.get("name"),
                "matrix": node.get("matrix"),
                "translation": node.get("translation"),
                "rotation": node.get("rotation"),
                "scale": node.get("scale"),
            })

    accessors = document.get("accessors", [])
    position_types: list[str] = []
    vertices = 0
    triangles = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            position_index = primitive.get("attributes", {}).get("POSITION")
            if position_index is None or not 0 <= position_index < len(accessors):
                raise RuntimeError(f"glTF primitive has no valid POSITION accessor: {path}")
            accessor = accessors[position_index]
            position_types.append(str(accessor.get("type")))
            vertices += int(accessor.get("count", 0))
            index_accessor = primitive.get("indices")
            if index_accessor is not None:
                if not 0 <= index_accessor < len(accessors):
                    raise RuntimeError(f"glTF index accessor is invalid: {path}")
                triangles += int(accessors[index_accessor].get("count", 0)) // 3

    image_paths = []
    for image in document.get("images", []):
        uri = image.get("uri")
        if isinstance(uri, str) and uri and not uri.startswith("data:"):
            image_paths.append(path.parent / uri)
    return {
        "path": str(path.resolve()),
        "root_nodes": len(roots),
        "root_nodes_identity": not non_identity,
        "non_identity_roots": non_identity,
        "nodes": len(nodes),
        "meshes": len(document.get("meshes", [])),
        "skins": len(document.get("skins", [])),
        "materials": len(document.get("materials", [])),
        "images": len(document.get("images", [])),
        "external_image_files": len(image_paths),
        "external_image_files_present": sum(item.is_file() for item in image_paths),
        "position_accessor_types": sorted(set(position_types)),
        "position_accessors_all_vec3": bool(position_types)
        and all(item == "VEC3" for item in position_types),
        "vertices": vertices,
        "triangles": triangles,
    }


def source_material_index(material) -> int | None:
    match = re.search(r"Material_(\d+)", material.name)
    return int(match.group(1)) if match else None


def principled(material):
    if not material.use_nodes or not material.node_tree:
        return None
    return next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )


def upstream_node(socket, node_type: str, visited=None):
    if socket is None:
        return None
    visited = visited or set()
    for link in socket.links:
        node = link.from_node
        pointer = node.as_pointer()
        if pointer in visited:
            continue
        visited.add(pointer)
        if node.type == node_type:
            return node
        for input_socket in node.inputs:
            found = upstream_node(input_socket, node_type, visited)
            if found:
                return found
    return None


def upstream_texture(socket, visited=None):
    if socket is None:
        return None
    visited = visited or set()
    for link in socket.links:
        node = link.from_node
        pointer = node.as_pointer()
        if pointer in visited:
            continue
        visited.add(pointer)
        if node.type == "TEX_IMAGE" and node.image:
            return node
        for input_socket in node.inputs:
            texture = upstream_texture(input_socket, visited)
            if texture:
                return texture
    return None


def texture_uv_map(texture) -> str | None:
    if texture is None:
        return None
    vector = texture.inputs.get("Vector")
    uv_node = upstream_node(vector, "UVMAP")
    if uv_node:
        return uv_node.uv_map
    attribute = upstream_node(vector, "ATTRIBUTE")
    if attribute and attribute.attribute_name:
        return attribute.attribute_name
    return None


def normal_strength(shader) -> float:
    if shader is None:
        return 1.0
    node = upstream_node(shader.inputs.get("Normal"), "NORMAL_MAP")
    return float(node.inputs["Strength"].default_value) if node else 1.0


def image_summary(image) -> dict | None:
    if image is None:
        return None
    path = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
    return {
        "name": image.name,
        "size": [int(image.size[0]), int(image.size[1])],
        "decoded": int(image.size[0]) > 0 and int(image.size[1]) > 0,
        "packed": image.packed_file is not None,
        "path": str(path) if path else "",
        "exists": bool(path and path.is_file()),
    }


def configure_material(material, label: str, alpha_indices: set[int]) -> dict:
    index = source_material_index(material)
    transparent = index in alpha_indices
    if transparent:
        material.blend_method = "HASHED"
        material.shadow_method = "HASHED"
        material.alpha_threshold = 0.05
        material.show_transparent_back = label == "HAIR"
        material.use_backface_culling = False
    else:
        material.blend_method = "OPAQUE"

    shader = principled(material)
    base_texture = upstream_texture(shader.inputs.get("Base Color")) if shader else None
    normal_texture = upstream_texture(shader.inputs.get("Normal")) if shader else None
    alpha_linked = bool(
        shader and shader.inputs.get("Alpha") and shader.inputs["Alpha"].is_linked
    )
    original = material.name
    material.name = f"{label}_{original}"
    return {
        "name": material.name,
        "source_index": index,
        "transparent": transparent,
        "blend_method": material.blend_method,
        "alpha_linked": alpha_linked,
        "base": image_summary(base_texture.image if base_texture else None),
        "normal": image_summary(normal_texture.image if normal_texture else None),
        "base_uv": texture_uv_map(base_texture),
        "normal_uv": texture_uv_map(normal_texture),
        "normal_strength": normal_strength(shader),
    }


def namespace_component_rigs(label: str, meshes: list, armatures: list) -> dict:
    """Give separate component rigs globally unique FBX-safe bone names."""
    report = []
    for rig_index, rig in enumerate(armatures):
        rig_prefix = f"{label}_R{rig_index:02d}"
        rig.name = f"{rig_prefix}_Armature"
        rig.data.name = f"{rig_prefix}_ArmatureData"
        linked_meshes = []
        for mesh in meshes:
            modifier_targets = {
                modifier.object
                for modifier in mesh.modifiers
                if modifier.type == "ARMATURE" and modifier.object
            }
            if rig in modifier_targets or mesh.parent == rig:
                linked_meshes.append(mesh)
        bone_map = {bone.name: f"{rig_prefix}_{bone.name}" for bone in rig.data.bones}
        renamed_groups = 0
        for mesh in linked_meshes:
            for group in mesh.vertex_groups:
                replacement = bone_map.get(group.name)
                if replacement:
                    group.name = replacement
                    renamed_groups += 1
        for bone in rig.data.bones:
            bone.name = bone_map[bone.name]
        report.append({
            "armature": rig.name,
            "bones": len(bone_map),
            "linked_meshes": len(linked_meshes),
            "renamed_vertex_groups": renamed_groups,
            "policy": "names only; geometry, weights, and transforms unchanged",
        })
    return {"armatures": report, "global_unique_bone_names": True}


def import_component(
    label: str, path: Path, alpha_indices: set[int]
) -> dict:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    audit = source_audit(path)
    if not audit["position_accessors_all_vec3"]:
        raise RuntimeError(f"{label}: every glTF POSITION accessor must be VEC3")

    object_before = {item.as_pointer() for item in bpy.data.objects}
    material_before = {item.as_pointer() for item in bpy.data.materials}
    image_before = {item.as_pointer() for item in bpy.data.images}
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = [
        item for item in bpy.data.objects if item.as_pointer() not in object_before
    ]
    materials = [
        item for item in bpy.data.materials if item.as_pointer() not in material_before
    ]
    images = [
        item for item in bpy.data.images if item.as_pointer() not in image_before
    ]
    if not objects:
        raise RuntimeError(f"{label}: Blender imported no objects from {path}")

    for obj in objects:
        obj.name = f"{label}_{obj.name}"
        obj["prism_component"] = label
        obj["identity_assembled"] = True
        obj.color = COMPONENT_COLORS[label]
        if obj.type not in {"MESH", "ARMATURE"}:
            obj.hide_render = True
    material_audit = [
        configure_material(material, label, alpha_indices) for material in materials
    ]
    for image in images:
        image.name = f"{label}_{image.name}"
    meshes = [item for item in objects if item.type == "MESH"]
    armatures = [item for item in objects if item.type == "ARMATURE"]
    if not meshes:
        raise RuntimeError(f"{label}: Blender imported no mesh objects from {path}")
    rig_namespace = namespace_component_rigs(label, meshes, armatures)
    return {
        "label": label,
        "path": path,
        "source": audit,
        "objects": objects,
        "meshes": meshes,
        "armatures": armatures,
        "rig_namespace": rig_namespace,
        "materials": materials,
        "material_audit": material_audit,
    }


def world_vertices(objects) -> list[Vector]:
    graph = bpy.context.evaluated_depsgraph_get()
    result: list[Vector] = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        matrix = evaluated.matrix_world
        result.extend(matrix @ vertex.co for vertex in mesh.vertices)
        evaluated.to_mesh_clear()
    return result


def bounds(vertices: list[Vector]) -> dict:
    if not vertices:
        return {"min": None, "max": None, "dimensions": None}
    low = [min(item[axis] for item in vertices) for axis in range(3)]
    high = [max(item[axis] for item in vertices) for axis in range(3)]
    return {
        "min": low,
        "max": high,
        "dimensions": [high[axis] - low[axis] for axis in range(3)],
    }


def geometry(component: dict) -> tuple[dict, list[Vector]]:
    vertices = world_vertices(component["meshes"])
    return ({
        "mesh_objects": len(component["meshes"]),
        "armatures": len(component["armatures"]),
        "vertices": sum(len(item.data.vertices) for item in component["meshes"]),
        "polygons": sum(len(item.data.polygons) for item in component["meshes"]),
        "bounds": bounds(vertices),
    }, vertices)


def overlap(left, right) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def head_fit(face: list[Vector], hair: list[Vector]) -> dict:
    face_bounds = bounds(face)
    hair_bounds = bounds(hair)
    axes = [
        overlap(
            (face_bounds["min"][axis], face_bounds["max"][axis]),
            (hair_bounds["min"][axis], hair_bounds["max"][axis]),
        )
        for axis in range(3)
    ]
    return {
        "face_hair_axis_overlap": axes,
        "face_hair_bounds_intersect": all(item > 0 for item in axes),
        "note": "Both components were imported at identity; no corrective fit applied.",
    }


def neck_fit(face: list[Vector], body: list[Vector]) -> dict:
    face_bounds = bounds(face)
    body_bounds = bounds(body)
    floor = face_bounds["min"][2]
    face_band = [item for item in face if item.z <= floor + 2.0]
    body_band = [item for item in body if floor - 5.0 <= item.z <= floor + 5.0]
    if not face_band or not body_band:
        return {
            "status": "insufficient_band",
            "face_band_vertices": len(face_band),
            "body_band_vertices": len(body_band),
        }
    tree = KDTree(len(body_band))
    for index, item in enumerate(body_band):
        tree.insert(item, index)
    tree.balance()
    stride = max(1, len(face_band) // 5000)
    distances = sorted(tree.find(item)[2] for item in face_band[::stride])
    return {
        "status": "measured_identity_alignment",
        "face_lower_band_z": [floor, floor + 2.0],
        "body_search_band_z": [floor - 5.0, floor + 5.0],
        "face_band_vertices": len(face_band),
        "body_band_vertices": len(body_band),
        "sampled_face_vertices": len(distances),
        "nearest_distance_min": min(distances),
        "nearest_distance_median": statistics.median(distances),
        "nearest_distance_p95": distances[
            min(len(distances) - 1, math.floor(len(distances) * 0.95))
        ],
        "sampled_vertices_within_distance": {
            str(limit): sum(value <= limit for value in distances)
            for limit in (0.001, 0.01, 0.1, 0.5, 1.0)
        },
        "face_body_vertical_bounds_overlap": overlap(
            (face_bounds["min"][2], face_bounds["max"][2]),
            (body_bounds["min"][2], body_bounds["max"][2]),
        ),
        "note": "Diagnostic only; no vertices were moved or welded.",
    }


def look_at(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_setup(mode: str, scene_bounds: dict, size: int, prefix: str) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    if mode == "clay":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.studio_light = "paint.sl"
        scene.display.shading.color_type = "OBJECT"
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "BOTH"
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (0.055, 0.065, 0.085)
        return

    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3
    scene.eevee.gtao_factor = 1.1
    scene.eevee.use_soft_shadows = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.8
    scene.view_settings.gamma = 1.0
    world = bpy.data.worlds.new(f"{prefix}_Preview_World")
    world.use_nodes = True
    scene.world = world
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.028, 0.035, 0.055, 1)
    background.inputs["Strength"].default_value = 0.5
    low = Vector(scene_bounds["min"])
    high = Vector(scene_bounds["max"])
    center = (low + high) / 2
    extent = max((high - low).length, 100.0)
    lights = (
        ("Key", (0.55, -0.8, 0.7), 2.2, 0.18, (1.0, 0.80, 0.68)),
        ("Fill", (-0.7, -0.35, 0.3), 0.8, 0.32, (0.55, 0.68, 1.0)),
        ("Rim", (0, 0.75, 0.65), 1.4, 0.22, (0.64, 0.74, 1.0)),
    )
    for suffix, direction, energy, angle, color in lights:
        name = f"{prefix}_{suffix}"
        data = bpy.data.lights.new(name, "SUN")
        data.energy = energy
        data.angle = angle
        data.color = color
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(direction) * extent
        look_at(light, center)


def render_views(
    directory: Path, scene_bounds: dict, mode: str, prefix: str, size: int
) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    render_setup(mode, scene_bounds, size, prefix)
    camera_data = bpy.data.cameras.new(f"{prefix}_Camera")
    camera = bpy.data.objects.new(f"{prefix}_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera_data.type = "ORTHO"
    low = Vector(scene_bounds["min"])
    high = Vector(scene_bounds["max"])
    center = (low + high) / 2
    height = high.z - low.z
    width = high.x - low.x
    scale = max(height * 1.08, width * 1.28)
    head_target = Vector((0, center.y, high.z - height * 0.12))
    head_scale = max(width * 0.62, height * 0.29)
    distance = max(350.0, scale * 4)
    views = (
        ("front", Vector((0, -distance, 0)), center, scale),
        ("back", Vector((0, distance, 0)), center, scale),
        ("right", Vector((distance, 0, 0)), center, scale),
        ("head", Vector((0, -distance, 0)), head_target, head_scale),
    )
    outputs = {}
    for name, offset, target, ortho_scale in views:
        camera.location = target + offset
        camera_data.ortho_scale = max(ortho_scale, 1.0)
        look_at(camera, target)
        target_path = (directory / f"{prefix}_{name}.png").resolve()
        bpy.context.scene.render.filepath = str(target_path)
        bpy.ops.render.render(write_still=True)
        outputs[name] = str(target_path)
    return outputs


def scene_stats() -> dict:
    meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    armatures = [
        item for item in bpy.context.scene.objects if item.type == "ARMATURE"
    ]
    vertices = world_vertices(meshes)
    return {
        "mesh_objects": len(meshes),
        "armatures": len(armatures),
        "vertices": sum(len(item.data.vertices) for item in meshes),
        "polygons": sum(len(item.data.polygons) for item in meshes),
        "materials": len({
            slot.material.as_pointer()
            for item in meshes
            for slot in item.material_slots
            if slot.material
        }),
        "bounds": bounds(vertices),
    }


def select_component_objects(components: dict) -> list:
    bpy.ops.object.select_all(action="DESELECT")
    objects = [
        obj
        for component in components.values()
        for obj in component["meshes"] + component["armatures"]
        if obj.name in bpy.context.scene.objects
    ]
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
    return objects


def detach_armature_parents_for_fbx(components: dict) -> dict:
    """Detach rig roots while preserving world matrices for Blender FBX 7.4."""
    armatures = [
        armature
        for component in components.values()
        for armature in component["armatures"]
    ]
    matrices = {
        armature.as_pointer(): armature.matrix_world.copy() for armature in armatures
    }
    entries = []
    for armature in armatures:
        entries.append({
            "armature": armature.name,
            "original_parent": armature.parent.name if armature.parent else None,
            "original_parent_type": armature.parent_type,
        })
        armature.parent = None
    for armature in armatures:
        armature.matrix_world = matrices[armature.as_pointer()]
    return {
        "policy": "independent FBX rig roots; world rest matrices preserved",
        "armatures": entries,
    }


def copy_image(image, directory: Path, stem: str) -> str | None:
    if image is None or not image.filepath:
        return None
    source = Path(bpy.path.abspath(image.filepath))
    if not source.is_file():
        return None
    suffix = source.suffix.lower() or ".png"
    target = directory / f"{stem}{suffix}"
    directory.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target.name


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.").lower()


def active_material_pointers(component: dict) -> set[int]:
    return {
        slot.material.as_pointer()
        for obj in component["meshes"]
        for slot in obj.material_slots
        if slot.material
    }


def portable_mapping(
    components: dict, texture_dir: Path, alpha_map: dict[str, set[int]]
) -> dict:
    result = {}
    for label, component in components.items():
        used = active_material_pointers(component)
        for material in component["materials"]:
            if material.as_pointer() not in used:
                continue
            shader = principled(material)
            if shader is None:
                continue
            index = source_material_index(material)
            stem = safe_stem(material.name)
            base_texture = upstream_texture(shader.inputs.get("Base Color"))
            normal_texture = upstream_texture(shader.inputs.get("Normal"))
            base = base_texture.image if base_texture else None
            normal = normal_texture.image if normal_texture else None
            transparent = index in alpha_map[label]
            result[material.name] = {
                "label": label,
                "source_index": index,
                "base": copy_image(base, texture_dir, stem + "_base"),
                "normal": copy_image(normal, texture_dir, stem + "_normal"),
                "base_uv": texture_uv_map(base_texture),
                "normal_uv": texture_uv_map(normal_texture),
                "normal_strength": normal_strength(shader),
                "alpha": transparent,
                "double_sided": label == "HAIR" or transparent,
                "base_color": list(shader.inputs["Base Color"].default_value),
                "roughness": float(shader.inputs["Roughness"].default_value),
                "metallic": float(shader.inputs["Metallic"].default_value),
            }
    return result


def connect_uv(nodes, links, texture, uv_map: str | None) -> None:
    if not uv_map:
        return
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = uv_map
    links.new(uv.outputs["UV"], texture.inputs["Vector"])


def relink_one(material, entry: dict, texture_dir: Path) -> dict:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = entry["base_color"]
    shader.inputs["Roughness"].default_value = entry["roughness"]
    shader.inputs["Metallic"].default_value = entry["metallic"]
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    loaded = {"base": False, "normal": False}
    if entry.get("base") and (texture_dir / entry["base"]).is_file():
        image = bpy.data.images.load(
            str(texture_dir / entry["base"]), check_existing=True
        )
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        connect_uv(nodes, links, texture, entry.get("base_uv"))
        links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        if entry["alpha"]:
            links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
        loaded["base"] = True
    if entry.get("normal") and (texture_dir / entry["normal"]).is_file():
        image = bpy.data.images.load(
            str(texture_dir / entry["normal"]), check_existing=True
        )
        image.colorspace_settings.name = "Non-Color"
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        connect_uv(nodes, links, texture, entry.get("normal_uv"))
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = float(
            entry.get("normal_strength", 1.0)
        )
        links.new(texture.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], shader.inputs["Normal"])
        loaded["normal"] = True
    material.blend_method = "HASHED" if entry["alpha"] else "OPAQUE"
    if entry["alpha"]:
        material.shadow_method = "HASHED"
        material.show_transparent_back = bool(entry["double_sided"])
        material.use_backface_culling = False
    return loaded


def relink_scene(mapping: dict, texture_dir: Path) -> dict:
    result = {}
    for expected, entry in mapping.items():
        material = bpy.data.materials.get(expected)
        if material is None:
            material = next(
                (
                    item
                    for item in bpy.data.materials
                    if item.name.startswith(expected + ".")
                ),
                None,
            )
        if material is None:
            result[expected] = {"error": "missing material"}
        else:
            result[expected] = relink_one(material, entry, texture_dir)
    return result


def write_relink(
    path: Path, character: str, mapping_name: str, texture_relative: str
) -> None:
    source = '''#!/usr/bin/env python3
"""Restore %s FBX base/normal/alpha materials after Blender import."""
from pathlib import Path
import json
import bpy

ROOT = Path(__file__).resolve().parent
TEXTURES = ROOT / %r
MAPPING = json.loads((ROOT / %r).read_text(encoding="utf-8"))

def load(path, non_color=False):
    image = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    return image

def connect_uv(nodes, links, texture, uv_map):
    if not uv_map:
        return
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = uv_map
    links.new(uv.outputs["UV"], texture.inputs["Vector"])

updated, missing = [], []
for expected, entry in MAPPING.items():
    material = bpy.data.materials.get(expected)
    if material is None:
        material = next((item for item in bpy.data.materials
                         if item.name.startswith(expected + ".")), None)
    if material is None:
        missing.append(expected)
        continue
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = entry["base_color"]
    shader.inputs["Roughness"].default_value = entry["roughness"]
    shader.inputs["Metallic"].default_value = entry["metallic"]
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if entry.get("base") and (TEXTURES / entry["base"]).is_file():
        node = nodes.new("ShaderNodeTexImage")
        node.image = load(TEXTURES / entry["base"])
        connect_uv(nodes, links, node, entry.get("base_uv"))
        links.new(node.outputs["Color"], shader.inputs["Base Color"])
        if entry["alpha"]:
            links.new(node.outputs["Alpha"], shader.inputs["Alpha"])
    if entry.get("normal") and (TEXTURES / entry["normal"]).is_file():
        node = nodes.new("ShaderNodeTexImage")
        node.image = load(TEXTURES / entry["normal"], True)
        connect_uv(nodes, links, node, entry.get("normal_uv"))
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = float(
            entry.get("normal_strength", 1.0))
        links.new(node.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    material.blend_method = "HASHED" if entry["alpha"] else "OPAQUE"
    if entry["alpha"]:
        material.shadow_method = "HASHED"
        material.show_transparent_back = bool(entry["double_sided"])
        material.use_backface_culling = False
    updated.append(material.name)

print(f"%s FBX relink: updated {len(updated)}; missing {len(missing)}")
if missing:
    print("Missing:", ", ".join(missing))
''' % (character, texture_relative, mapping_name, character)
    path.write_text(source, encoding="utf-8")


def bounds_match(left: dict, right: dict, tolerance: float = 0.002) -> bool:
    return all(
        abs(float(left[key][axis]) - float(right[key][axis])) <= tolerance
        for key in ("min", "max")
        for axis in range(3)
    )


def main() -> int:
    args = arguments()
    if not ((3, 6, 0) <= bpy.app.version < (4, 0, 0)):
        raise RuntimeError(
            "This exporter is verified with Blender 3.6 LTS; got "
            + bpy.app.version_string
        )
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = file_stem(args.character)
    preview_dir = output_dir / "previews"
    alpha_map = {
        "BODY": args.body_alpha,
        "FACE": args.face_alpha,
        "HAIR": args.hair_alpha,
    }

    bpy.ops.wm.read_factory_settings(use_empty=True)
    requested = [("BODY", args.body)]
    if args.face is not None:
        requested.append(("FACE", args.face))
    requested.append(("HAIR", args.hair))
    components = {
        label: import_component(label, path, alpha_map[label])
        for label, path in requested
    }

    geometry_data = {}
    vertex_data = {}
    for label, component in components.items():
        geometry_data[label], vertex_data[label] = geometry(component)
    all_vertices = [
        vertex for vertices in vertex_data.values() for vertex in vertices
    ]
    scene_bounds = bounds(all_vertices)
    render_mode = args.render_mode
    if render_mode == "auto":
        render_mode = "textured" if any(
            image.size[0] > 0 and image.size[1] > 0 for image in bpy.data.images
        ) else "clay"

    original_stats = scene_stats()
    report = {
        "schema": "venus-vacation-prism-character-assembly/v1",
        "character": args.character,
        "blender_version": bpy.app.version_string,
        "formats_requested": sorted(args.formats),
        "identity_alignment": all(
            component["source"]["root_nodes_identity"]
            for component in components.values()
        ),
        "transform_policy": (
            "Source identity only; no translation, rotation, scale, weld, "
            "splice, geometry merge, or rig merge."
        ),
        "input_policy": (
            "Inputs are assembly-ready; character-specific body/material/cloth "
            "processing occurs before this stage."
        ),
        "alpha_policy": {
            label: sorted(indices) for label, indices in alpha_map.items()
        },
        "components": {
            label: {
                "source": component["source"],
                "geometry": geometry_data[label],
                "materials": component["material_audit"],
                "mesh_names": [item.name for item in component["meshes"]],
                "rig_namespace": component["rig_namespace"],
            }
            for label, component in components.items()
        },
        "combined_bounds": scene_bounds,
        "assembly_stats": original_stats,
        # Without a FACE component the body itself carries the head, so the
        # hair-fit diagnostic runs against the BODY vertices and the FACE/BODY
        # neck-seam diagnostic does not apply.
        "head_fit": head_fit(
            vertex_data["FACE" if "FACE" in vertex_data else "BODY"],
            vertex_data["HAIR"],
        ),
        "neck_fit": (
            neck_fit(vertex_data["FACE"], vertex_data["BODY"])
            if "FACE" in vertex_data
            else None
        ),
        "render_mode": render_mode,
        "preview_size": [args.preview_size, args.preview_size],
        "previews_skipped": args.skip_previews,
        "fbx_roundtrip_skipped": args.skip_fbx_roundtrip,
        "outputs": {},
    }
    report["previews"] = {}
    if not args.skip_previews:
        report["previews"] = render_views(
            preview_dir,
            scene_bounds,
            render_mode,
            f"{stem}_Complete",
            args.preview_size,
        )

    if "blend" in args.formats:
        blend_path = output_dir / f"{stem}_Complete_Rigged.blend"
        bpy.ops.file.pack_all()
        active_materials = {
            slot.material.as_pointer(): slot.material
            for component in components.values()
            for obj in component["meshes"]
            for slot in obj.material_slots
            if slot.material
        }
        used_images = {
            node.image.as_pointer(): node.image
            for material in active_materials.values()
            if material.use_nodes and material.node_tree
            for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image
        }
        report["blend_pack_audit"] = {
            "requested": True,
            "images_total": len(bpy.data.images),
            "images_used": len(used_images),
            "used_images_packed": sum(
                image.packed_file is not None for image in used_images.values()
            ),
            "used_images_unpacked": [
                image.name
                for image in used_images.values()
                if image.packed_file is None
            ],
        }
        if report["blend_pack_audit"]["used_images_unpacked"]:
            raise RuntimeError("not all used images were packed into the Blend")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        blend_path.with_suffix(".blend1").unlink(missing_ok=True)
        report["outputs"]["blend"] = str(blend_path)

    if "glb" in args.formats:
        glb_path = output_dir / f"{stem}_Complete_Rigged.glb"
        select_component_objects(components)
        bpy.ops.export_scene.gltf(
            filepath=str(glb_path),
            export_format="GLB",
            use_selection=True,
            export_yup=True,
            export_materials="EXPORT",
        )
        report["outputs"]["glb"] = str(glb_path)

    if "fbx" in args.formats:
        fbx_path = output_dir / f"{stem}_Complete_Rigged.fbx"
        texture_dir = output_dir / "textures" / "fbx"
        mapping = portable_mapping(components, texture_dir, alpha_map)
        mapping_path = output_dir / f"{stem}_FBX_Material_Mapping.json"
        mapping_path.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        relink_path = output_dir / f"{stem}_Relink_FBX_Materials.py"
        write_relink(
            relink_path,
            args.character,
            mapping_path.name,
            "textures/fbx",
        )
        report["fbx_rig_root_policy"] = detach_armature_parents_for_fbx(
            components
        )
        select_component_objects(components)
        bpy.ops.export_scene.fbx(
            filepath=str(fbx_path),
            use_selection=True,
            add_leaf_bones=False,
            bake_anim=False,
            path_mode="COPY",
            embed_textures=True,
        )
        report["outputs"].update({
            "fbx": str(fbx_path),
            "fbx_material_mapping": str(mapping_path),
            "fbx_relink_script": str(relink_path),
            "fbx_texture_directory": str(texture_dir),
        })
        report["fbx_materials"] = {
            "materials": len(mapping),
            "base_textures": sum(bool(item.get("base")) for item in mapping.values()),
            "normal_textures": sum(
                bool(item.get("normal")) for item in mapping.values()
            ),
            "alpha_materials": sum(
                bool(item.get("alpha")) for item in mapping.values()
            ),
        }

        if args.skip_fbx_roundtrip:
            report["fbx_roundtrip_validation"] = {
                "skipped": True,
                "passed": None,
            }
            report["fbx_reimport_previews"] = {}
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.fbx(filepath=str(fbx_path), use_anim=False)
            relink_audit = relink_scene(mapping, texture_dir)
            fbx_stats = scene_stats()
            missing_materials = [
                name for name, result in relink_audit.items() if result.get("error")
            ]
            missing_textures = []
            for name, entry in mapping.items():
                loaded = relink_audit.get(name) or {}
                for semantic in ("base", "normal"):
                    if entry.get(semantic) and loaded.get(semantic) is not True:
                        missing_textures.append(f"{name}:{semantic}")
            validation = {
                "skipped": False,
                "mesh_count_match": (
                    fbx_stats["mesh_objects"] == original_stats["mesh_objects"]
                ),
                "vertex_count_match": (
                    fbx_stats["vertices"] == original_stats["vertices"]
                ),
                "polygon_count_match": (
                    fbx_stats["polygons"] == original_stats["polygons"]
                ),
                "armature_count_match": (
                    fbx_stats["armatures"] == original_stats["armatures"]
                ),
                "bounds_match_0_002": bounds_match(
                    fbx_stats["bounds"], original_stats["bounds"]
                ),
                "missing_materials": missing_materials,
                "missing_textures": missing_textures,
            }
            validation["passed"] = all(
                value
                for key, value in validation.items()
                if key not in {
                    "skipped", "missing_materials", "missing_textures", "passed"
                }
            ) and not missing_materials and not missing_textures
            report["fbx_relink_audit"] = relink_audit
            report["fbx_reimport_stats"] = fbx_stats
            report["fbx_roundtrip_validation"] = validation
            report["fbx_reimport_previews"] = {}
            if not args.skip_previews:
                report["fbx_reimport_previews"] = render_views(
                    preview_dir,
                    fbx_stats["bounds"],
                    "textured" if mapping else "clay",
                    f"{stem}_FBX_Reimport",
                    args.preview_size,
                )
            reimport_blend = output_dir / f"{stem}_FBX_Reimport_Validated.blend"
            bpy.ops.file.pack_all()
            bpy.ops.wm.save_as_mainfile(filepath=str(reimport_blend))
            report["fbx_reimport_validation_blend"] = {
                "path": str(reimport_blend),
                "retained": bool(args.keep_roundtrip_blend),
            }
            if not args.keep_roundtrip_blend:
                reimport_blend.unlink(missing_ok=True)
                reimport_backup = reimport_blend.with_suffix(".blend1")
                reimport_backup.unlink(missing_ok=True)
            if not validation["passed"]:
                raise RuntimeError(
                    "FBX round-trip validation failed: "
                    + json.dumps(validation, ensure_ascii=False)
                )

    if "glb" in args.formats:
        glb_path = Path(report["outputs"]["glb"])
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        glb_stats = scene_stats()
        vertex_delta = glb_stats["vertices"] - original_stats["vertices"]
        # glTF legally splits vertices at UV, normal and material seams.  The
        # topology invariants are mesh/polygon/armature/material counts and
        # world bounds; keep a generous but finite split guard as corruption
        # protection.
        vertex_split_limit = max(1000, round(original_stats["vertices"] * 0.05))
        glb_validation = {
            "mesh_count_match": (
                glb_stats["mesh_objects"] == original_stats["mesh_objects"]
            ),
            "polygon_count_match": (
                glb_stats["polygons"] == original_stats["polygons"]
            ),
            "armature_count_match": (
                glb_stats["armatures"] == original_stats["armatures"]
            ),
            "material_count_match": (
                glb_stats["materials"] == original_stats["materials"]
            ),
            "bounds_match_0_002": bounds_match(
                glb_stats["bounds"], original_stats["bounds"]
            ),
            "vertex_delta": vertex_delta,
            "vertex_split_limit": vertex_split_limit,
            "vertex_count_preserved_with_attribute_splits": (
                0 <= vertex_delta <= vertex_split_limit
            ),
        }
        glb_validation["passed"] = all(
            value for key, value in glb_validation.items()
            if key not in {"vertex_delta", "vertex_split_limit", "passed"}
        )
        report["glb_reimport_stats"] = glb_stats
        report["glb_roundtrip_validation"] = glb_validation
        if not glb_validation["passed"]:
            raise RuntimeError(
                "GLB round-trip validation failed: "
                + json.dumps(glb_validation, ensure_ascii=False)
            )

    report_path = output_dir / f"{stem}_Complete_Rigged_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "character": args.character,
        "identity_alignment": report["identity_alignment"],
        "formats": sorted(args.formats),
        "previews_skipped": args.skip_previews,
        "fbx_roundtrip_skipped": args.skip_fbx_roundtrip,
        "outputs": report["outputs"],
        "report": str(report_path),
        "stats": original_stats,
        "head_fit": report["head_fit"],
        "neck_fit": report["neck_fit"],
        "fbx_validation": report.get("fbx_roundtrip_validation"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
