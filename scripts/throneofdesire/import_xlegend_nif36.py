"""Import X-Legend/Gamebryo character meshes into Blender 3.6.

The Steam build of Throne of Desire stores an optimized X-Legend variant of
Gamebryo 20.3.3.2 NIF.  Its header uses an encrypted string table, 32-bit
block hashes, byte-sized type indices, and 24-bit block sizes.  Blender
NifTools does not understand that header.  This importer reads the static
NiTriShapeData-compatible geometry blocks directly.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from xlegend_nif import (  # noqa: E402
    GEOMETRY_HASH,
    NODE_HASH,
    SHAPE_HASH,
    parse_geometry,
    parse_nif,
    parse_node,
    parse_shape,
    parse_skin_instance,
    diffuse_texture_name,
    is_primary_character_shape,
    shape_texture_names,
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--render", type=Path)
    parser.add_argument("--textures", type=Path)
    parser.add_argument("--fbx", type=Path)
    parser.add_argument("--include-helpers", action="store_true")
    return parser.parse_args(argv)


def texture_path(texture_dir: Path | None, dds_name: str) -> Path | None:
    if texture_dir is None:
        return None
    stem = Path(dds_name).stem
    for suffix in (".tga", ".png"):
        candidate = texture_dir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def image_node(
    material: bpy.types.Material,
    path: Path,
    label: str,
    *,
    non_color: bool = False,
) -> bpy.types.ShaderNodeTexImage:
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.name = label
    node.label = label
    node.image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    if non_color:
        node.image.colorspace_settings.name = "Non-Color"
    return node


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    texture_names: list[str],
    texture_dir: Path | None,
    *,
    use_base_alpha: bool = True,
    use_base_color_texture: bool = True,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.62
    principled.inputs["Specular"].default_value = 0.25
    material["xlegend_texture_references"] = texture_names

    base_name = diffuse_texture_name(texture_names)
    specular_name = next(
        (value for value in texture_names if Path(value).stem.lower().endswith("_specular")),
        None,
    )
    gloss_name = next(
        (value for value in texture_names if Path(value).stem.lower().endswith("_gloss")),
        None,
    )
    normal_name = next(
        (value for value in texture_names if Path(value).stem.lower().endswith("_normal")),
        None,
    )

    base_path = texture_path(texture_dir, base_name) if base_name else None
    if base_path:
        base = image_node(material, base_path, "Base Color")
        base.location = (-700, 180)
        if not use_base_color_texture:
            base.image.alpha_mode = "CHANNEL_PACKED"
            material["xlegend_base_status"] = (
                "loaded but disconnected: cross-model masked body overlay"
            )
        elif use_base_alpha:
            material.node_tree.links.new(
                base.outputs["Color"], principled.inputs["Base Color"]
            )
            material.node_tree.links.new(base.outputs["Alpha"], principled.inputs["Alpha"])
            material.blend_method = "HASHED"
            material.shadow_method = "HASHED"
        else:
            # Legacy body textures use alpha as a paint mask.  Preserve RGB
            # independently from alpha, then composite it over the material's
            # base skin colour instead of making the whole mesh transparent.
            base.image.alpha_mode = "CHANNEL_PACKED"
            mix = material.node_tree.nodes.new("ShaderNodeMixRGB")
            mix.name = "Base Color Alpha Mask"
            mix.label = "Base Color Alpha Mask"
            mix.location = (-420, 180)
            mix.inputs[1].default_value = color
            material.node_tree.links.new(base.outputs["Alpha"], mix.inputs[0])
            material.node_tree.links.new(base.outputs["Color"], mix.inputs[2])
            material.node_tree.links.new(
                mix.outputs["Color"], principled.inputs["Base Color"]
            )
        material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
        material["xlegend_base_texture"] = str(base_path.resolve())

    specular_path = texture_path(texture_dir, specular_name) if specular_name else None
    if specular_path:
        specular = image_node(material, specular_path, "Specular", non_color=True)
        specular.location = (-700, -40)
        material["xlegend_specular_texture"] = str(specular_path.resolve())

    gloss_path = texture_path(texture_dir, gloss_name) if gloss_name else None
    if gloss_path:
        gloss = image_node(material, gloss_path, "Gloss", non_color=True)
        gloss.location = (-700, -260)
        invert = material.node_tree.nodes.new("ShaderNodeInvert")
        invert.name = "Gloss to Roughness"
        invert.location = (-440, -260)
        material.node_tree.links.new(gloss.outputs["Color"], invert.inputs["Color"])
        material["xlegend_gloss_texture"] = str(gloss_path.resolve())

    normal_path = texture_path(texture_dir, normal_name) if normal_name else None
    if normal_path:
        normal = image_node(material, normal_path, "Normal", non_color=True)
        normal.location = (-700, -500)
        normal_map = material.node_tree.nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-420, -500)
        # Preserve the decoded legacy normal map for inspection, but do not
        # drive the shader by default.  X-Legend's EAC channel convention is
        # not fully recovered and produces severe skin mottling in Blender.
        normal_map.inputs["Strength"].default_value = 0.0
        material.node_tree.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        material["xlegend_normal_texture"] = str(normal_path.resolve())
        material["xlegend_normal_status"] = "loaded but disconnected pending EAC convention validation"
    return material


def add_mesh(
    name: str,
    geometry: dict,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(geometry["vertices"], [], geometry["faces"])
    mesh.update()
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    uvs = geometry["uv_sets"][0] if geometry["uv_sets"] else None
    if uvs:
        layer = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            u, v = uvs[loop.vertex_index]
            layer.data[loop.index].uv = (u, 1.0 - v)

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def node_matrix(node: dict) -> Matrix:
    rotation = node["rotation"]
    rotation_matrix = Matrix(
        (
            rotation[0:3],
            rotation[3:6],
            rotation[6:9],
        )
    ).to_4x4()
    return (
        Matrix.Translation(Vector(node["translation"]))
        @ rotation_matrix
        @ Matrix.Scale(node["scale"], 4)
    )


def add_skeleton(
    data: bytes,
    nif,
    shapes: list[dict],
    model_id: str,
    collection: bpy.types.Collection,
) -> bpy.types.Object | None:
    bone_refs = []
    skin_links = []
    for shape in shapes:
        skin_ref = shape["skin_instance_ref"]
        if not (0 <= skin_ref < len(nif.blocks)):
            continue
        try:
            skin = parse_skin_instance(data, nif.blocks[skin_ref])
        except (ValueError, IndexError):
            continue
        skin_links.append(skin)
        for bone_ref in skin["bone_refs"]:
            if bone_ref not in bone_refs:
                bone_refs.append(bone_ref)

    nodes = {}
    for bone_ref in bone_refs:
        if not (0 <= bone_ref < len(nif.blocks)):
            continue
        block = nif.blocks[bone_ref]
        if block.type_hash != NODE_HASH:
            continue
        try:
            nodes[bone_ref] = parse_node(data, nif, block)
        except ValueError:
            continue
    if not nodes:
        return None

    parent_by_child = {}
    for block_index, node in nodes.items():
        for child in node["children"]:
            if child in nodes:
                parent_by_child[child] = block_index

    world_matrices = {}

    def world_matrix(block_index: int, stack: set[int] | None = None) -> Matrix:
        if block_index in world_matrices:
            return world_matrices[block_index]
        stack = set() if stack is None else stack
        if block_index in stack:
            return node_matrix(nodes[block_index])
        stack.add(block_index)
        local = node_matrix(nodes[block_index])
        parent = parent_by_child.get(block_index)
        world = world_matrix(parent, stack) @ local if parent in nodes else local
        world_matrices[block_index] = world
        return world

    armature_data = bpy.data.armatures.new(f"{model_id}_skeleton")
    armature = bpy.data.objects.new(f"{model_id}_skeleton", armature_data)
    collection.objects.link(armature)
    armature.show_in_front = True
    armature.data.display_type = "STICK"
    armature["xlegend_status"] = (
        "Rest skeleton reconstructed; optimized skin weights are cataloged but not applied"
    )
    armature["xlegend_bone_count"] = len(nodes)
    armature["xlegend_skin_links"] = [item["block"] for item in skin_links]

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = {}
    for block_index, node in nodes.items():
        world = world_matrix(block_index)
        head = world.translation
        child_positions = [
            world_matrix(child).translation
            for child in node["children"]
            if child in nodes
        ]
        tail = child_positions[0] if child_positions else head + world.to_3x3() @ Vector((0.04, 0, 0))
        if (tail - head).length < 0.005:
            tail = head + world.to_3x3() @ Vector((0.04, 0, 0))
        edit_bone = armature.data.edit_bones.new(node["name"])
        edit_bone.head = head
        edit_bone.tail = tail
        edit_bones[block_index] = edit_bone

    for child, parent in parent_by_child.items():
        if child in edit_bones and parent in edit_bones:
            edit_bones[child].parent = edit_bones[parent]
            edit_bones[child].use_connect = (
                edit_bones[child].head - edit_bones[parent].tail
            ).length < 0.005
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    return armature


def add_import_report(
    model_id: str,
    nif,
    base_objects: list[bpy.types.Object],
    attachment_objects: list[bpy.types.Object],
    armature,
    texture_dir: Path | None,
) -> None:
    report = bpy.data.texts.new("XLegend_Import_Report.txt")
    texture_names = [value for value in nif.strings if value.lower().endswith(".dds")]
    objects = base_objects + attachment_objects
    report.write(
        f"X-Legend Gamebryo {model_id} import\n"
        f"Base meshes: {len(base_objects)}\n"
        f"Hidden attachment meshes: {len(attachment_objects)}\n"
        f"Vertices: {sum(len(obj.data.vertices) for obj in objects)}\n"
        f"Triangles: {sum(len(obj.data.polygons) for obj in objects)}\n"
        f"Recovered string table entries: {len(nif.strings)}\n"
        f"Rest skeleton bones: {len(armature.data.bones) if armature else 0}\n"
        f"NIF texture references: {', '.join(texture_names) or '(none)'}\n\n"
        f"Converted texture directory: {texture_dir or '(not supplied)'}\n\n"
        "Known limitation: X-Legend's optimized skin-weight stream is not yet "
        "applied. Geometry, UVs, mapped materials, and the inspectable rest "
        "skeleton are present.\n"
    )


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup_scene(objects: list[bpy.types.Object]) -> None:
    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.render.resolution_x = 720
    bpy.context.scene.render.resolution_y = 960
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.film_transparent = False
    bpy.context.scene.world.color = (0.025, 0.025, 0.035)

    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (minimum + maximum) * 0.5
    height = max(maximum.z - minimum.z, 0.1)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = center + Vector((height * 1.35, -height * 2.6, height * 0.18))
    camera_data.lens = 58
    look_at(camera, center + Vector((0.0, 0.0, height * 0.06)))
    bpy.context.scene.camera = camera

    key_data = bpy.data.lights.new("Key", "AREA")
    key_data.energy = 320
    key_data.size = height * 1.5
    key = bpy.data.objects.new("Key", key_data)
    key.location = center + Vector((height * 1.7, -height * 1.5, height * 1.4))
    look_at(key, center)
    bpy.context.collection.objects.link(key)

    fill_data = bpy.data.lights.new("Fill", "AREA")
    fill_data.energy = 140
    fill_data.size = height * 1.2
    fill = bpy.data.objects.new("Fill", fill_data)
    fill.location = center + Vector((-height * 1.3, -height * 0.8, height * 0.8))
    look_at(fill, center)
    bpy.context.collection.objects.link(fill)

    rim_data = bpy.data.lights.new("Rim", "AREA")
    rim_data.energy = 260
    rim_data.size = height
    rim = bpy.data.objects.new("Rim", rim_data)
    rim.location = center + Vector((0.0, height * 1.2, height * 1.2))
    look_at(rim, center)
    bpy.context.collection.objects.link(rim)


def main() -> None:
    args = parse_args()
    data = args.input.read_bytes()
    nif = parse_nif(data)
    model_id = args.input.stem.lower()

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    base_collection = bpy.data.collections.new(f"{model_id}_Base")
    attachment_collection = bpy.data.collections.new(f"{model_id}_Attachments")
    skeleton_collection = bpy.data.collections.new(f"{model_id}_Skeleton")
    bpy.context.scene.collection.children.link(base_collection)
    bpy.context.scene.collection.children.link(attachment_collection)
    bpy.context.scene.collection.children.link(skeleton_collection)
    attachment_collection.hide_viewport = True
    attachment_collection.hide_render = True

    palette = [
        (0.72, 0.48, 0.40, 1.0),
        (0.18, 0.20, 0.27, 1.0),
        (0.34, 0.16, 0.20, 1.0),
        (0.40, 0.43, 0.52, 1.0),
        (0.12, 0.13, 0.17, 1.0),
    ]
    base_objects = []
    attachment_objects = []
    imported_shapes = []
    shapes_by_data = {}
    palette_by_texture_set = {}
    for block in nif.blocks:
        if block.type_hash != SHAPE_HASH:
            continue
        try:
            shape = parse_shape(data, nif, block)
        except ValueError:
            continue
        shapes_by_data[shape["data_ref"]] = shape

    geometry_index = 0
    for block in nif.blocks:
        if block.type_hash != GEOMETRY_HASH:
            continue
        geometry = parse_geometry(data, block)
        shape = shapes_by_data.get(block.index)
        is_skinned = bool(shape and shape["skin_instance_ref"] >= 0)
        if not args.include_helpers and (
            len(geometry["vertices"]) <= 100 or not is_skinned
        ):
            continue
        mesh_name = shape["name"] if shape else f"{model_id}_mesh_{block.index:03d}"
        shape_textures = shape_texture_names(data, nif, shape) if shape else []
        is_base = is_skinned and is_primary_character_shape(
            model_id, mesh_name, shape_textures
        )
        collection = base_collection if is_base else attachment_collection
        texture_key = tuple(value.lower() for value in shape_textures)
        if texture_key:
            color_index = palette_by_texture_set.setdefault(
                texture_key, len(palette_by_texture_set)
            )
        else:
            color_index = geometry_index
        base_texture_name = diffuse_texture_name(shape_textures)
        cross_model_body_overlay = bool(
            mesh_name.lower().endswith("_b")
            and base_texture_name
            and not Path(base_texture_name).stem.lower().startswith(f"{model_id}_")
        )
        material = make_material(
            f"{mesh_name}_material",
            palette[color_index % len(palette)],
            shape_textures,
            args.textures,
            # Body/genital diffuse alpha stores a mask/channel rather than
            # surface opacity (h996 would otherwise render nearly invisible).
            use_base_alpha=not mesh_name.lower().endswith(("_b", "_p")),
            use_base_color_texture=not cross_model_body_overlay,
        )
        obj = add_mesh(mesh_name, geometry, material, collection)
        obj["xlegend_geometry_block"] = block.index
        obj["xlegend_category"] = "base" if is_base else "attachment"
        if shape:
            obj["xlegend_shape_block"] = shape["block"]
            obj["xlegend_skin_instance_block"] = shape["skin_instance_ref"]
            imported_shapes.append(shape)
        if is_base:
            base_objects.append(obj)
        else:
            attachment_objects.append(obj)
        geometry_index += 1

    objects = base_objects + attachment_objects
    if not objects:
        raise RuntimeError("no X-Legend geometry blocks were found")
    armature = add_skeleton(
        data, nif, imported_shapes, model_id, skeleton_collection
    )
    add_import_report(
        model_id, nif, base_objects, attachment_objects, armature, args.textures
    )
    setup_scene(base_objects or objects)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.textures:
        bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))
    if args.render:
        args.render.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(args.render)
        bpy.ops.render.render(write_still=True)
    if args.fbx:
        args.fbx.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in base_objects:
            obj.select_set(True)
        if armature:
            armature.select_set(True)
        bpy.ops.export_scene.fbx(
            filepath=str(args.fbx),
            use_selection=True,
            add_leaf_bones=False,
            bake_anim=False,
            path_mode="COPY",
            embed_textures=True,
        )

    total_vertices = sum(len(obj.data.vertices) for obj in objects)
    total_triangles = sum(len(obj.data.polygons) for obj in objects)
    print(
        f"Imported {len(base_objects)} base and {len(attachment_objects)} attachment "
        f"meshes, {total_vertices} vertices, "
        f"{total_triangles} triangles, "
        f"{len(armature.data.bones) if armature else 0} rest-skeleton bones"
    )


if __name__ == "__main__":
    main()
