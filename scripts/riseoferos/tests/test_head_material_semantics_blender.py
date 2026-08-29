"""Run with Blender 3.6:

blender --background --factory-startup --python \
    scripts/riseoferos/tests/test_head_material_semantics_blender.py
"""
import importlib.util
import math
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATHS = (
    ROOT / "scripts" / "riseoferos" / "roe_xps_addon.py",
    ROOT / "scripts" / "riseoferos" / "blender_face_materials.py",
)


def load_module(path, suffix):
    spec = importlib.util.spec_from_file_location(
        "roe_head_semantics_test_" + suffix, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_head_fixture():
    vertices = []
    faces = []
    source_indices = []
    uv_by_vertex = []

    def add_quad(center_x, center_z, source_index):
        start = len(vertices)
        vertices.extend((
            (center_x - 0.05, -0.05, center_z - 0.005),
            (center_x + 0.05, -0.05, center_z - 0.005),
            (center_x + 0.05, 0.05, center_z + 0.005),
            (center_x - 0.05, 0.05, center_z + 0.005),
        ))
        uv_by_vertex.extend(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
        first_face = len(faces)
        faces.extend((
            (start, start + 1, start + 2),
            (start, start + 2, start + 3),
        ))
        source_indices.extend((source_index, source_index))
        return range(first_face, first_face + 2)

    def add_eye_fan(polygon_count=300):
        center = len(vertices)
        vertices.append((0.0, 0.0, 0.0))
        uv_by_vertex.append((0.5, 0.5))
        ring = []
        for index in range(polygon_count):
            angle = 2.0 * math.pi * index / polygon_count
            ring.append(len(vertices))
            vertices.append((
                0.4 * math.cos(angle),
                0.4 * math.sin(angle),
                0.05 * math.sin(angle),
            ))
            uv_by_vertex.append((
                0.5 + 0.5 * math.cos(angle),
                0.5 + 0.5 * math.sin(angle),
            ))
        first_face = len(faces)
        for index in range(polygon_count):
            faces.append((center, ring[index], ring[(index + 1) % polygon_count]))
            source_indices.append(1)
        return range(first_face, first_face + polygon_count)

    def add_f10_mixed_face_fan(polygon_count=120, tear_count=8):
        """Reproduce F10's connected face/tear material boundary."""
        center = len(vertices)
        component_vertices = [center]
        vertices.append((2.0, 0.0, 0.0))
        uv_by_vertex.append((1.55, 0.60))
        ring = []
        for index in range(polygon_count):
            angle = 2.0 * math.pi * index / polygon_count
            vertex_index = len(vertices)
            ring.append(vertex_index)
            component_vertices.append(vertex_index)
            vertices.append((
                2.0 + 0.2 * math.cos(angle),
                0.2 * math.sin(angle),
                0.02 * math.sin(angle),
            ))
            uv_by_vertex.append((
                1.55 + 0.05 * math.cos(angle),
                0.60 + 0.05 * math.sin(angle),
            ))
        first_face = len(faces)
        split = polygon_count - tear_count
        for index in range(polygon_count):
            faces.append((center, ring[index], ring[(index + 1) % polygon_count]))
            source_indices.append(0 if index < split else 3)
        return (
            range(first_face, first_face + split),
            range(first_face + split, first_face + polygon_count),
            component_vertices,
        )

    f10_face, f10_tear, f10_vertices = add_f10_mixed_face_fan()

    regions = {
        "face": add_quad(-2.0, 0.0, 0),
        "f10_face": f10_face,
        "f10_tear": f10_tear,
        "eye": add_eye_fan(),
        "lower_lash": add_quad(-1.0, -0.04, 2),
        "upper_lash": add_quad(-0.6, 0.01, 2),
        "brow": add_quad(0.8, 0.10, 2),
        "tear": add_quad(1.2, 0.0, 3),
    }

    mesh = bpy.data.meshes.new("semantic_head_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_by_vertex[loop.vertex_index]

    obj = bpy.data.objects.new("pc_b02_hd_head", mesh)
    bpy.context.collection.objects.link(obj)
    # The presence of a semantic group reproduces b02's code path even though
    # its lower-lash and brow cards do not have decisive weights.
    eyelid = obj.vertex_groups.new(name="Eyelid")
    eyelid.add(f10_vertices, 1.0, 'REPLACE')
    return obj, source_indices, regions


def build_b01_weighted_eye_fixture(polygon_count=432):
    """B01 eye: one vague source slot, 80% Eyeball + 20% Head weight."""
    vertices = [(0.0, 0.0, 0.0)]
    uv = [(0.5, 0.5)]
    faces = []
    for index in range(polygon_count):
        angle = 2.0 * math.pi * index / polygon_count
        vertices.append((
            0.02 * math.cos(angle),
            0.02 * math.sin(angle),
            0.02 * math.sin(angle),
        ))
        uv.append((
            0.5 + 0.5 * math.cos(angle),
            0.5 + 0.5 * math.sin(angle),
        ))
    for index in range(polygon_count):
        faces.append((0, index + 1, (index + 1) % polygon_count + 1))

    mesh = bpy.data.meshes.new("b01_weighted_eye_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv[loop.vertex_index]

    obj = bpy.data.objects.new("pc_b01_nk_body_fixture", mesh)
    bpy.context.collection.objects.link(obj)
    all_vertices = list(range(len(vertices)))
    eyeball = obj.vertex_groups.new(name="Bip001 Eyeball_L")
    head = obj.vertex_groups.new(name="Bip001 Head")
    eyeball.add(all_vertices, 0.8, 'REPLACE')
    head.add(all_vertices, 0.2, 'REPLACE')
    return obj


SOURCE_MATERIALS = (
    "pc_b_nk_face",
    "pc_b_nk_eyes",
    "pc_b_nk_eyebrow",
    "pc_b_nk_tears",
)


for index, module_path in enumerate(MODULE_PATHS):
    module = load_module(module_path, str(index))
    head, source_indices, regions = build_head_fixture()
    classified = module.classify_head(
        head, SOURCE_MATERIALS, source_indices)

    expected_slots = {
        "face": 0,
        "f10_face": 0,
        "f10_tear": 4,
        "eye": 1,
        "lower_lash": 2,
        "upper_lash": 2,
        "brow": 3,
        "tear": 4,
    }
    for region, expected_slot in expected_slots.items():
        actual = {classified[polygon_index] for polygon_index in regions[region]}
        assert actual == {expected_slot}, (
            "%s classified as %s instead of %d in %s"
            % (region, sorted(actual), expected_slot, module_path.name))

    bpy.data.objects.remove(head, do_unlink=True)

    b01_eye = build_b01_weighted_eye_fixture()
    b01_classified = module.classify_head(
        b01_eye, ("pc_b01_nk_body",), [0] * len(b01_eye.data.polygons))
    assert set(b01_classified.values()) == {1}, (
        "B01 weighted eyeball was not classified as eye in %s"
        % module_path.name)
    bpy.data.objects.remove(b01_eye, do_unlink=True)

    tear_mesh = bpy.data.meshes.new("body_with_tear_slot_mesh")
    tear_mesh.from_pydata(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        [],
        ((0, 1, 2),),
    )
    tear_obj = bpy.data.objects.new("pc_b02_hd_body_fixture_%d" % index, tear_mesh)
    bpy.context.collection.objects.link(tear_obj)
    tear_source = bpy.data.materials.new("pc_b_nk_tears")
    tear_mesh.materials.append(tear_source)
    module.apply_mesh_materials(tear_obj, str(ROOT), None, None)
    tear_material = tear_obj.material_slots[0].material
    assert tear_material is not None
    assert any(node.type == "BSDF_TRANSPARENT"
               for node in tear_material.node_tree.nodes), (
        "non-head tear slot was not transparent in %s" % module_path.name)
    bpy.data.objects.remove(tear_obj, do_unlink=True)

print("ROE_HEAD_MATERIAL_SEMANTICS_TEST=PASS")
