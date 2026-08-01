"""Attach FF7 Remake Tifa's default leather gloves to an imported body.

Run with Blender after opening the body blend file::

    blender --background Tifa_Remake_validation.blend \
      --python fix_ff7remake_tifa_gloves.py -- \
      --glove WE0002_00.psk --textures Texture --output Tifa_Remake_fixed.blend

The body PSK intentionally does not contain the default glove mesh.  The game
stores it as the separate WE0002_00_Tifa_LeatherGlove skeletal mesh.  This
script imports that mesh, checks its weighted bones against the body skeleton,
then rebinds it to the body's armature without changing either rest pose.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glove", required=True)
    parser.add_argument("--textures", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", default="")
    parser.add_argument("--closeup", default="")
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


def weighted_group_names(mesh: bpy.types.Object) -> set[str]:
    names: set[str] = set()
    for vertex in mesh.data.vertices:
        for assignment in vertex.groups:
            if assignment.weight > 1.0e-8:
                names.add(mesh.vertex_groups[assignment.group].name)
    return names


def source_armature(mesh: bpy.types.Object, candidates: list[bpy.types.Object]):
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object in candidates:
            return modifier.object
    if mesh.parent in candidates and mesh.parent.type == "ARMATURE":
        return mesh.parent
    return None


def matrix_difference(first, second) -> float:
    return max(
        abs(first.matrix_local[row][column] - second.matrix_local[row][column])
        for row in range(4)
        for column in range(4)
    )


def validate_binding(mesh, imported_armature, body_armature):
    weighted = weighted_group_names(mesh)
    missing = sorted(
        name for name in weighted if body_armature.data.bones.get(name) is None
    )
    differences = []
    for name in sorted(weighted):
        source = imported_armature.data.bones.get(name)
        target = body_armature.data.bones.get(name)
        if source is not None and target is not None:
            differences.append((matrix_difference(source, target), name))
    differences.sort(reverse=True)
    worst_difference, worst_bone = differences[0] if differences else (0.0, "")
    return weighted, missing, worst_difference, worst_bone


def rebind(mesh, imported_armature, body_armature):
    local_matrix = imported_armature.matrix_world.inverted() @ mesh.matrix_world
    rebound = False
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == imported_armature:
            modifier.object = body_armature
            rebound = True
    if not rebound:
        modifier = mesh.modifiers.new(name="FF7 Remake Body Armature", type="ARMATURE")
        modifier.object = body_armature
    mesh.parent = body_armature
    mesh.matrix_parent_inverse.identity()
    mesh.matrix_basis = local_matrix


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


def input_socket(principled, *names):
    for name in names:
        socket = principled.inputs.get(name)
        if socket is not None:
            return socket
    return None


def wire_glove_materials(mesh, texture_dir: str):
    diffuse = os.path.join(texture_dir, "WE0002_00_Body_C.png")
    normal = os.path.join(texture_dir, "WE0002_00_Body_N.png")
    alpha = os.path.join(texture_dir, "WE0002_00_Body_A.png")
    for path in (diffuse, normal):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

    wired = []
    for slot in mesh.material_slots:
        material = slot.material
        if material is None:
            material = bpy.data.materials.new(slot.name or "WE0002_00_Body")
            slot.material = material
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        if "materia" in material.name.lower():
            principled.inputs["Base Color"].default_value = (0.12, 0.004, 0.008, 1.0)
            metallic = input_socket(principled, "Metallic")
            if metallic:
                metallic.default_value = 0.35
            roughness = input_socket(principled, "Roughness")
            if roughness:
                roughness.default_value = 0.18
            emission = input_socket(principled, "Emission Color", "Emission")
            if emission:
                emission.default_value = (0.65, 0.005, 0.01, 1.0)
            strength = input_socket(principled, "Emission Strength")
            if strength:
                strength.default_value = 1.4
            wired.append({"material": material.name, "mode": "materia"})
            continue

        color_node = image_node(nodes, diffuse, "Glove Base Color", "sRGB")
        links.new(color_node.outputs["Color"], principled.inputs["Base Color"])
        normal_node = image_node(nodes, normal, "Glove Normal", "Non-Color")
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = 0.8
        links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
        roughness = input_socket(principled, "Roughness")
        if roughness:
            roughness.default_value = 0.42
        if os.path.isfile(alpha):
            alpha_node = image_node(nodes, alpha, "Glove Alpha", "Non-Color")
            alpha_socket = input_socket(principled, "Alpha")
            if alpha_socket:
                links.new(alpha_node.outputs["Color"], alpha_socket)
        wired.append(
            {"material": material.name, "mode": "textured", "diffuse": diffuse, "normal": normal}
        )
    return wired


def smooth_mesh(mesh):
    for polygon in mesh.data.polygons:
        polygon.use_smooth = True
    if hasattr(mesh.data, "use_auto_smooth"):
        mesh.data.use_auto_smooth = False
    mesh.data.update()


def evaluated_world_vertices(mesh):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh.evaluated_get(depsgraph)
    return [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]


def validate_pose_deformation(mesh, body_armature, weighted):
    bound_modifiers = [
        modifier
        for modifier in mesh.modifiers
        if modifier.type == "ARMATURE" and modifier.object == body_armature
    ]
    if not bound_modifiers:
        raise RuntimeError(f"{mesh.name} is not bound to the body armature")

    preferred = ["R_Hand", "L_Hand", "R_Wrist", "L_Wrist"]
    bone_name = next(
        (name for name in preferred if name in weighted and body_armature.pose.bones.get(name)),
        None,
    )
    if bone_name is None:
        bone_name = next(
            (name for name in sorted(weighted) if body_armature.pose.bones.get(name)),
            None,
        )
    if bone_name is None:
        raise RuntimeError(f"{mesh.name} has no weighted pose bone to test")

    before = evaluated_world_vertices(mesh)
    pose_bone = body_armature.pose.bones[bone_name]
    original_matrix = pose_bone.matrix_basis.copy()
    try:
        pose_bone.matrix_basis = original_matrix @ Matrix.Rotation(
            math.radians(5.0), 4, "X"
        )
        bpy.context.view_layer.update()
        after = evaluated_world_vertices(mesh)
    finally:
        pose_bone.matrix_basis = original_matrix
        bpy.context.view_layer.update()

    maximum = max((first - second).length for first, second in zip(before, after))
    if maximum <= 0.001:
        raise RuntimeError(
            f"{mesh.name} did not deform when weighted bone {bone_name} was posed"
        )
    return {
        "mesh": mesh.name,
        "armature_modifier": bound_modifiers[0].name,
        "armature": body_armature.name,
        "test_bone": bone_name,
        "test_angle_degrees": 5.0,
        "maximum_vertex_displacement": maximum,
        "restored_after_test": True,
    }


def look_at(camera, target: Vector):
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_full(path: str):
    if not path:
        return
    scene = bpy.context.scene
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def render_wrist_closeup(path: str, glove_mesh):
    if not path:
        return
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("The validation scene has no camera")

    original = {
        "location": camera.location.copy(),
        "rotation": camera.rotation_euler.copy(),
        "type": camera.data.type,
        "ortho_scale": camera.data.ortho_scale,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "percentage": scene.render.resolution_percentage,
    }
    world_vertices = [glove_mesh.matrix_world @ vertex.co for vertex in glove_mesh.data.vertices]
    right_vertices = [vertex for vertex in world_vertices if vertex.y < 0.0]
    sample = right_vertices or world_vertices
    target = sum(sample, Vector()) / max(1, len(sample))

    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 31.0
    camera.location = Vector((190.0, target.y, target.z + 1.5))
    look_at(camera, target)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)

    camera.location = original["location"]
    camera.rotation_euler = original["rotation"]
    camera.data.type = original["type"]
    camera.data.ortho_scale = original["ortho_scale"]
    scene.render.resolution_x = original["resolution_x"]
    scene.render.resolution_y = original["resolution_y"]
    scene.render.resolution_percentage = original["percentage"]


def mesh_bounds(mesh):
    points = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    return {
        "min": [min(point[i] for point in points) for i in range(3)],
        "max": [max(point[i] for point in points) for i in range(3)],
    }


def main():
    args = parse_args()
    source_body_blend = bpy.data.filepath
    glove_path = os.path.abspath(args.glove)
    texture_dir = os.path.abspath(args.textures)
    output_path = os.path.abspath(args.output)

    if not os.path.isfile(glove_path):
        raise FileNotFoundError(glove_path)
    body_armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not body_armatures:
        raise RuntimeError("No body armature exists in the opened blend file")
    body_armature = max(body_armatures, key=lambda obj: len(obj.data.bones))
    before = set(bpy.context.scene.objects)
    result = import_psk(glove_path)
    created = [obj for obj in bpy.context.scene.objects if obj not in before]
    imported_armatures = [obj for obj in created if obj.type == "ARMATURE"]
    imported_meshes = [obj for obj in created if obj.type == "MESH"]
    if "FINISHED" not in result or not imported_armatures or not imported_meshes:
        raise RuntimeError("The glove PSK did not create a complete mesh and armature")

    validation = []
    for mesh in imported_meshes:
        imported_armature = source_armature(mesh, imported_armatures)
        if imported_armature is None:
            raise RuntimeError(f"Imported glove mesh {mesh.name} has no source armature")
        weighted, missing, worst_difference, worst_bone = validate_binding(
            mesh, imported_armature, body_armature
        )
        if missing:
            raise RuntimeError(
                f"Body armature is missing {len(missing)} weighted glove bones: {missing[:8]}"
            )
        if worst_difference > 0.01:
            raise RuntimeError(
                f"Glove rest pose differs at {worst_bone}: {worst_difference:.6f}"
            )
        rebind(mesh, imported_armature, body_armature)
        smooth_mesh(mesh)
        validation.append(
            {
                "mesh": mesh.name,
                "weighted_bones": len(weighted),
                "missing_bones": missing,
                "worst_rest_difference": worst_difference,
                "worst_rest_bone": worst_bone,
            }
        )

    for armature in imported_armatures:
        bpy.data.objects.remove(armature, do_unlink=True)

    primary_mesh = max(imported_meshes, key=lambda obj: len(obj.data.vertices))
    primary_mesh.name = "WE0002_00_Tifa_LeatherGlove"
    primary_mesh.data.name = "WE0002_00_Tifa_LeatherGlove"
    materials = wire_glove_materials(primary_mesh, texture_dir)
    pose_validation = [
        validate_pose_deformation(mesh, body_armature, weighted_group_names(mesh))
        for mesh in imported_meshes
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    render_full(os.path.abspath(args.render) if args.render else "")
    render_wrist_closeup(os.path.abspath(args.closeup) if args.closeup else "", primary_mesh)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)

    report = {
        "source_body_blend": source_body_blend,
        "source_glove": glove_path,
        "output_blend": output_path,
        "body_armature": body_armature.name,
        "body_bones": len(body_armature.data.bones),
        "glove_meshes": len(imported_meshes),
        "glove_vertices": sum(len(mesh.data.vertices) for mesh in imported_meshes),
        "glove_polygons": sum(len(mesh.data.polygons) for mesh in imported_meshes),
        "glove_bounds": mesh_bounds(primary_mesh),
        "validation": validation,
        "pose_validation": pose_validation,
        "materials": materials,
        "render": os.path.abspath(args.render) if args.render else "",
        "closeup": os.path.abspath(args.closeup) if args.closeup else "",
    }
    if args.report:
        report_path = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print("FF7REMAKE_GLOVE_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
