"""Materialize a clothed Rise of Eros character and render a preview.

Blender-side worker for ``export_character_models.ps1``.  It drives the same
importer and material operators as the interactive ROE add-on, then writes a
packed .blend plus a single side-by-side preview PNG (3/4, front, head).

Unlike ``export_nude_model_blender.py`` this worker makes no assumption that the
body is a single combined nude mesh: it neither splits the body into six slots
nor fails on a missing nude atlas, so it accepts any dressed HD/LD model.

Usage:
  blender --background --python export_character_model_blender.py -- \
      <fbx>[;<fallback fbx>...] <texture_dir> <out.blend> <roe_xps_addon.py> \
      <validate|export> [blend,glb] [preview:0|1]

Candidates are tried in order and the first one that actually imports geometry
wins: several characters ship a ``*_nk_bs.fbx`` that holds only a rig, and an
event NPC may ship nothing but that.  When no candidate yields a mesh the worker
reports status NOMESH, which is a property of the bundles rather than a failure.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import traceback

import bpy
import numpy as np
from mathutils import Vector

RESULT_PREFIX = "ROE_CHAR_EXPORT="

# Views composited into the single preview image, left to right.
PREVIEW_VIEWS = ("hero", "front", "head")


def result(status, **details):
    # ASCII-only so PowerShell 5.1 cannot corrupt the marker by decoding
    # Blender's UTF-8 stdout with an OEM code page.
    print(RESULT_PREFIX + json.dumps({"status": status, **details},
                                     ensure_ascii=True, sort_keys=True))


def load_addon(path):
    spec = importlib.util.spec_from_file_location("roe_char_addon", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ROE add-on: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module


def family_mismatches(images, expected_family):
    """Flag a shared head/hair texture borrowed from another body family."""
    mismatches = []
    common_role = re.compile(
        r"^pc_([a-z])_(?:nk|ld)_(?:face|eye|eyes|eye_iris|eyebrow|hair)",
        re.IGNORECASE)
    for image in images:
        filename = os.path.basename(bpy.path.abspath(
            image.filepath or image.name))
        match = common_role.match(filename)
        if match and match.group(1).lower() != expected_family:
            mismatches.append(filename)
    return sorted(set(mismatches))


ALBEDO_NAME = re.compile(r"_(?:albedo|abedo)", re.IGNORECASE)


def _normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _texture_key(stem):
    return _normalize(re.split(r"_rgbx", stem, flags=re.IGNORECASE)[0])


def build_albedo_index(texture_dir):
    """Map a normalized asset name to its best Albedo PNG (HD beats LD)."""
    index = {}
    for root, _dirs, files in os.walk(texture_dir):
        for name in files:
            if not name.lower().endswith(".png") or not ALBEDO_NAME.search(name):
                continue
            stem = os.path.splitext(name)[0]
            rank = 2 if re.search(r"_ld$", stem, re.IGNORECASE) else (
                0 if re.search(r"_hd$", stem, re.IGNORECASE) else 1)
            key = _texture_key(stem)
            current = index.get(key)
            if current is None or rank < current[0]:
                index[key] = (rank, os.path.join(root, name))
    return {key: value[1] for key, value in index.items()}


def resolve_leftover_texture(index, object_name, character_id):
    """Second-chance lookup for a slot the add-on left without a Base Color.

    Only an unambiguous hit is accepted.  Meshes are numbered more finely than
    the atlases they use (``..._armor01`` against ``..._armor``, ``wp_x_09_hd``
    against ``wp_x_09``), and a weapon mesh is usually named after its hand
    socket rather than its atlas, so the character's own ``wp_<id>`` atlas is
    tried last.  Anything that could match two atlases is left grey on purpose:
    a wrong texture is worse than an obviously missing one.
    """
    norm = _normalize(object_name)
    probes = []
    for candidate in (norm, re.sub(r"(?:hd|ld)$", "", norm)):
        probes.extend([candidate, re.sub(r"\d+$", "", candidate)])
    if norm.startswith("wp") and character_id:
        probes.append("wp" + _normalize(character_id))
    for probe in probes:
        if probe and probe in index:
            return index[probe]
    return None


def _mesh_components(mesh):
    """Group polygons into connected components (same union-find as the add-on)."""
    parent = list(range(len(mesh.vertices)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for edge in mesh.edges:
        first, second = edge.vertices
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[root_a] = root_b

    components = {}
    for polygon in mesh.polygons:
        components.setdefault(find(polygon.vertices[0]), []).append(polygon)
    return components


def attach_fused_head_eyeballs(module, meshes, texture_dir, family):
    """Give eyeballs a real eye material when head and body share one mesh.

    a00's head is fused into the body mesh and carries no ``Eyeball`` vertex
    group, so ``find_head`` returns None and the add-on skips eye/lash/brow
    classification entirely.  Its two 432-polygon eyeballs then sample the body
    atlas through a full 0-1 iris UV, which renders as torn white/brown smears.

    Only components with the unmistakable ROE eyeball signature are touched:
    250-800 polygons whose UV island covers essentially the whole 0-1 square.
    """
    if not family:
        return []
    iris = (module.find_tex(texture_dir, "pc_%s_nk_eye_iris*Albedo*.png" % family)
            or module.find_tex(texture_dir, "pc_%s_nk_eyes*Albedo*.png" % family)
            or module.find_tex(texture_dir, "pc_%s_ld_eyes*Albedo*.png" % family))
    if not iris:
        return []

    attached = []
    for obj in meshes:
        mesh = obj.data
        if not mesh.uv_layers.active:
            continue
        uv_data = mesh.uv_layers.active.data
        targets = []
        for polygons in _mesh_components(mesh).values():
            if not 250 <= len(polygons) <= 800:
                continue
            u_min = v_min = 9.0
            u_max = v_max = -9.0
            for polygon in polygons:
                for loop in polygon.loop_indices:
                    u, v = uv_data[loop].uv
                    u_min, u_max = min(u_min, u), max(u_max, u)
                    v_min, v_max = min(v_min, v), max(v_max, v)
            if (u_min >= -0.01 and u_max <= 1.01 and v_min >= -0.01 and v_max <= 1.01
                    and u_max - u_min > 0.85 and v_max - v_min > 0.85):
                targets.extend(polygons)
        if not targets:
            continue
        mesh.materials.append(module.eye_mat("%s_eye" % obj.name, iris))
        eye_index = len(mesh.materials) - 1
        for polygon in targets:
            polygon.material_index = eye_index
        mesh.update()
        attached.append("%s[%d] <- %s (%d faces)"
                        % (obj.name, eye_index, os.path.basename(iris), len(targets)))
    return attached


def materials_images(meshes):
    """Every image reachable from the materials actually assigned to the model.

    The FBX importer creates an image datablock per texture named in the file,
    resolved beside the FBX.  Those datablocks stay in the scene even though the
    add-on rebuilds materials from the ``_textures`` copies, so packing all of
    ``bpy.data.images`` would embed unused duplicates — and hard-fail once the
    redundant per-object copies are pruned from disk.
    """
    images = set()
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    images.add(node.image)
    return images


def pack_images(meshes):
    packed, failed = [], []
    for image in materials_images(meshes):
        if image.source != "FILE":
            continue
        try:
            image.pack()
            packed.append(image.name)
        except (OSError, RuntimeError) as exc:
            failed.append("%s: %s" % (image.name, exc))
    return packed, failed


def select_character_objects(meshes, armatures):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in list(meshes) + list(armatures):
        try:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.hide_render = False
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass
    if armatures:
        bpy.context.view_layer.objects.active = armatures[0]
    elif meshes:
        bpy.context.view_layer.objects.active = meshes[0]


def setup_preview_world():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    # Filmic (Blender's default) desaturates the albedo atlases, which makes a
    # preview useless for judging whether the right texture was bound.
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("preview_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    background.inputs[1].default_value = 1.35
    scene.world = world

    # Key light slightly camera-left, fill from the opposite side so the far
    # cheek and the back of a dark costume do not read as a silhouette.
    for name, energy, rotation in (
        ("key", 3.2, (0.95, 0.0, 0.65)),
        ("fill", 1.1, (1.15, 0.0, -2.2)),
    ):
        data = bpy.data.lights.new(name, type="SUN")
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation


def mesh_bounds(meshes):
    points = [obj.matrix_world @ Vector(corner)
              for obj in meshes for corner in obj.bound_box]
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
    """Concatenate rendered tiles horizontally into one PNG."""
    height = max(tile.shape[0] for tile in tiles)
    # Pad short tiles with the rendered backdrop rather than black, sampled from
    # a corner pixel so it tracks the world colour and the view transform.
    backdrop = tiles[0][0, 0].copy()
    padded = []
    for tile in tiles:
        if tile.shape[0] != height:
            pad = np.empty((height, tile.shape[1], tile.shape[2]),
                           dtype=np.float32)
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


def render_preview(meshes, out_path, scratch_prefix):
    setup_preview_world()
    scene = bpy.context.scene
    low, high = mesh_bounds(meshes)
    center = (low + high) * 0.5
    extent = high - low
    distance = max(extent.length, 0.1) * 2.0

    camera_data = bpy.data.cameras.new("preview_cam")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("preview_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    head_target = Vector((center.x, center.y, high.z - extent.z * 0.10))
    plans = {
        # 3/4 hero angle first: it shows silhouette and side detail at once.
        "hero": (center, extent.z * 1.12, Vector((-0.75, -0.95, 0.12)).normalized(),
                 620, 940),
        "front": (center, extent.z * 1.12, Vector((0.0, -1.0, 0.0)), 620, 940),
        "head": (head_target, extent.z * 0.26, Vector((0.0, -1.0, 0.05)).normalized(),
                 620, 620),
    }
    tiles = []
    temporaries = []
    for name in PREVIEW_VIEWS:
        target, ortho, direction, width, height = plans[name]
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        tile_path = "%s_%s.png" % (scratch_prefix, name)
        render_view(camera, camera_data, target, ortho, direction, distance,
                    tile_path)
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) not in {5, 6, 7}:
        raise RuntimeError(
            "usage: <fbx> <texture_dir> <out.blend> <roe_xps_addon.py> "
            "<validate|export> [blend,glb] [preview:0|1]")

    candidates = [os.path.abspath(item) for item in argv[0].split(";")
                  if item.strip()]
    texture_dir, output_path, addon_path = (
        os.path.abspath(argv[index]) for index in range(1, 4))
    mode = argv[4]
    formats = ({item.strip().lower() for item in argv[5].split(",")
                if item.strip()} if len(argv) >= 6 else {"blend"})
    want_preview = argv[6] != "0" if len(argv) == 7 else True

    unknown = formats - {"blend", "glb"}
    if unknown:
        raise RuntimeError("unknown format(s): %s" % ", ".join(sorted(unknown)))
    if mode not in {"validate", "export"}:
        raise RuntimeError("unknown mode: %s" % mode)
    if not candidates:
        raise RuntimeError("no FBX candidate given")
    for label, path, predicate in (
        ("FBX", candidates[0], os.path.isfile),
        ("texture dir", texture_dir, os.path.isdir),
        ("ROE add-on", addon_path, os.path.isfile),
    ):
        if not predicate(path):
            raise RuntimeError("%s not found: %s" % (label, path))

    stem = Path(output_path).stem
    family_match = re.match(r"pc_([a-z])", stem.lower())
    expected_family = family_match.group(1) if family_match else ""

    bpy.ops.wm.read_factory_settings(use_empty=True)
    module = load_addon(addon_path)

    fbx_path = ""
    meshes = []
    empty_candidates = []
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        props = bpy.context.scene.roe
        props.workflow_mode = "ROE"
        props.apply_scope = "LATEST"
        props.replace_previous = False
        props.fbx_path = candidate
        props.tex_dir = texture_dir

        imported = bpy.ops.roe.import_fbx()
        if imported != {"FINISHED"}:
            raise RuntimeError("FBX import failed: %r" % (imported,))
        found = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
        if not found:
            # Rig-only prefab: the material pass would abort on it, so move on
            # to the next candidate before touching materials.
            empty_candidates.append(os.path.basename(candidate))
            continue
        applied = bpy.ops.roe.apply_materials(repair_scope="ALL")
        if applied != {"FINISHED"}:
            raise RuntimeError("material pass failed: %r" % (applied,))
        fbx_path = candidate
        meshes = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
        break

    if not meshes:
        result("NOMESH", source=candidates[0],
               candidates=[os.path.basename(item) for item in candidates],
               empty_candidates=empty_candidates,
               error="no candidate FBX contains geometry (rig-only prefabs)")
        return
    armatures = module.related_armatures(meshes)

    id_match = re.match(r"pc_([a-z]\d+)", stem.lower())
    character_id = id_match.group(1) if id_match else ""
    albedo_index = build_albedo_index(texture_dir)
    recovered = []
    for obj in meshes:
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material is not None:
                if module.diffuse_image(material) is not None:
                    continue
                if module.material_is_transparent_only(material):
                    continue
            path = resolve_leftover_texture(albedo_index, obj.name, character_id)
            if not path:
                continue
            slot.material = module.albedo_mat(
                "%s_%02d_recovered" % (obj.name, index), path)
            recovered.append("%s[%d] <- %s"
                             % (obj.name, index, os.path.basename(path)))

    # Must run before the texture audit so the iris it binds is counted.
    head = module.find_head(meshes)
    fused_eyes = ([] if head is not None else attach_fused_head_eyeballs(
        module, meshes, texture_dir, character_id[:1] if character_id else ""))

    images = []
    untextured = []
    for obj in meshes:
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material is None:
                untextured.append("%s[%d] <empty>" % (obj.name, index))
                continue
            image = module.diffuse_image(material)
            if image is None:
                # A deliberately transparent slot (eye overlay, hidden helper)
                # has no Base Color image and is not a defect.
                if not module.material_is_transparent_only(material):
                    untextured.append("%s[%d] %s"
                                      % (obj.name, index, material.name))
                continue
            images.append(image)

    # A head can come back fully textured yet have every face polygon routed
    # into lash/brow/overlay, which renders as a faceless head while every other
    # check reports success.  Count the polygons per head slot so an empty face
    # slot is a hard signal instead of something only a human notices.
    head_slots = {}
    head_face_polygons = -1
    if head is not None:
        counts = {}
        for polygon in head.data.polygons:
            counts[polygon.material_index] = counts.get(polygon.material_index, 0) + 1
        for index, slot in enumerate(head.material_slots):
            name = slot.material.name if slot.material else "slot%d" % index
            head_slots[name] = counts.get(index, 0)
        head_face_polygons = head_slots.get("face", -1)

    textures = sorted({
        os.path.basename(bpy.path.abspath(image.filepath or image.name))
        for image in images})
    mismatches = family_mismatches(images, expected_family) if expected_family else []

    outputs = {}
    preview_path = ""
    packed = []
    if mode == "export":
        output_root = os.path.dirname(output_path)
        os.makedirs(output_root, exist_ok=True)
        if want_preview:
            preview_path = render_preview(
                meshes, os.path.join(output_root, stem + "_preview.png"),
                os.path.join(output_root, "." + stem))
        if "blend" in formats:
            packed, failures = pack_images(meshes)
            if failures:
                raise RuntimeError("image packing failed: %s"
                                   % "; ".join(failures))
            bpy.context.preferences.filepaths.save_version = 0
            bpy.ops.wm.save_as_mainfile(filepath=output_path,
                                        check_existing=False)
            if not os.path.isfile(output_path):
                raise RuntimeError("blend not written: %s" % output_path)
            outputs["blend"] = output_path
        if "glb" in formats:
            glb_path = os.path.join(output_root, "glb", stem + ".glb")
            os.makedirs(os.path.dirname(glb_path), exist_ok=True)
            select_character_objects(meshes, armatures)
            bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB",
                                      use_selection=True, export_apply=False)
            if not os.path.isfile(glb_path) or os.path.getsize(glb_path) == 0:
                raise RuntimeError("GLB not written: %s" % glb_path)
            outputs["glb"] = glb_path

    result(
        "PASS",
        source=fbx_path,
        output=outputs.get("blend") or next(iter(outputs.values()), ""),
        outputs=outputs,
        preview=preview_path,
        formats=sorted(formats) if mode == "export" else [],
        meshes=len(meshes),
        armatures=len(armatures),
        materials=sum(len(obj.material_slots) for obj in meshes),
        textures=textures,
        packed_images=len(packed),
        untextured_slots=untextured,
        recovered_slots=recovered,
        family_mismatches=mismatches,
        head_slots=head_slots,
        head_face_polygons=head_face_polygons,
        fused_head_eyes=fused_eyes,
        diagnostic=bpy.context.scene.roe.diagnostic_report,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Blender often exits 0 after a Python error.
        result("FAIL", error=str(exc), traceback=traceback.format_exc())
