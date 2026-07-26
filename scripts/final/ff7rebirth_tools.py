"""FF7 Rebirth Tools — import and prepare FModel exports in Blender.

FFVII Rebirth stores assets in Unreal IoStore archives. Archive browsing/export
is intentionally performed in FModel; this add-on starts from FModel's output.
It never reads encrypted game archives and contains no AES key or mapping data.
"""

import difflib
import json
import os
import re
import time

import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


bl_info = {
    "name": "FF7 Rebirth Tools",
    "author": "ripper_tpose",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar > FF7RB",
    "description": "选择 FModel 导出目录，导入 FFVII Rebirth 模型并匹配基础贴图",
    "category": "Import-Export",
}


MODEL_EXTENSIONS = {".glb", ".gltf", ".fbx", ".psk", ".pskx", ".obj"}
IMAGE_EXTENSIONS = {".png", ".tga", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp"}
IMPORT_BATCH_KEY = "ff7rb_import_batch"
ACTIVE_BATCH_KEY = "ff7rb_active_import_batch"

GENERIC_TOKENS = {
    "mi", "mat", "material", "inst", "instance", "tex", "texture",
    "t", "sk", "skeletal", "mesh", "ue", "end",
}
ROLE_TOKENS = {
    "base": {
        "albedo", "basecolor", "basecolour", "diffuse", "color", "colour",
        "bc", "d", "c",
    },
    "normal": {"normal", "norm", "nrm", "n"},
    "roughness": {"roughness", "rough", "rgh", "r", "mg"},
    "metallic": {"metallic", "metalness", "metal", "m", "mr"},
    "orm": {"orm", "rma", "arm", "mra"},
    "opacity": {"opacity", "alpha", "mask", "transparency", "coverage", "a"},
    "emissive": {"emissive", "emission", "emit", "e"},
}

# FModel material JSONs keep the original Unreal texture-parameter names.  These
# names are much more reliable than guessing from filenames (notably Mg/Mr and
# character-specific eye/hair materials).  Order matters: game-specific
# parameters come before generic shader defaults.
SEMANTIC_TEXTURE_KEYS = {
    "base": (
        "PM_Diffuse", "BaseColor", "Base_Color", "Diffuse", "Albedo",
        "IrisColor", "Color",
    ),
    "normal": (
        "Normal", "NormalMap", "PM_Normals", "IrisNormal", "ScrelaNormal",
    ),
    "roughness": ("Roughness", "RoughnessMap"),
    "metallic": ("Metallic", "Metalness", "MetallicMap"),
    "orm": (
        "ORM", "OcclusionRoughnessMetallic", "RMA", "MRA", "PackedMasks",
    ),
    "opacity": (
        "Coverage", "AlphaMask", "OpacityMask", "Opacity", "Transparency",
        "Alpha",
    ),
    # FF7 Rebirth's player eye shader layers a shared sclera texture with a
    # character-specific iris texture. Treating IrisColor as the whole Base
    # Color makes the sclera dark/red, so keep both references available.
    "eye_sclera": ("Color", "Common_Eye_Player_C"),
    "eye_iris": ("IrisColor", "PC0002_00_Eye_C"),
}
GENERATED_NODE_PREFIX = "FF7RB_"
EYE_IRIS_INNER_RADIUS = 0.18
EYE_IRIS_OUTER_RADIUS = 0.22
SKIN_NORMAL_STRENGTH = 0.35
DEFAULT_NORMAL_STRENGTH = 0.7


def normalized_tokens(value):
    tokens = re.findall(r"[a-z]+|\d+", os.path.splitext(os.path.basename(value))[0].lower())
    return [token for token in tokens if token not in GENERIC_TOKENS]


def texture_role(path):
    tokens = normalized_tokens(path)
    tail = tokens[-2:]
    for role in ("normal", "roughness", "metallic", "orm", "opacity", "emissive"):
        if any(token in ROLE_TOKENS[role] for token in tail):
            return role
    if any(token in ROLE_TOKENS["base"] for token in tail):
        return "base"
    joined = "_".join(tokens)
    for role in ("normal", "roughness", "metallic", "orm", "opacity", "emissive", "base"):
        # Three-letter channel tags (ARM/RMA/MRA/ORM) are valid only as whole
        # tail tokens.  Substring matching would misread "Arms_O" as ARM.
        if any(len(token) > 3 and token in joined for token in ROLE_TOKENS[role]):
            return role
    return "unknown"


def texture_stem_tokens(path):
    role_words = set().union(*ROLE_TOKENS.values())
    return [token for token in normalized_tokens(path)
            if token not in role_words and not token.isdigit()]


def discover_files(root, extensions):
    root = bpy.path.abspath(root) if root else ""
    if not os.path.isdir(root):
        return []
    matches = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs
                   if name.lower() not in {"__macosx", ".git", ".cache"}]
        for filename in files:
            if os.path.splitext(filename)[1].lower() in extensions:
                matches.append(os.path.join(current, filename))
    return matches


def discover_files_many(roots, extensions):
    matches = []
    seen = set()
    for root in roots:
        for path in discover_files(root, extensions):
            identity = os.path.normcase(os.path.abspath(path))
            if identity not in seen:
                seen.add(identity)
                matches.append(path)
    return matches


def unique_existing_roots(*roots):
    result = []
    seen = set()
    for root in roots:
        expanded = bpy.path.abspath(root) if root else ""
        if not expanded or not os.path.isdir(expanded):
            continue
        identity = os.path.normcase(os.path.abspath(expanded))
        if identity not in seen:
            seen.add(identity)
            result.append(expanded)
    return result


def material_name_aliases(value):
    basename = os.path.basename(value or "")
    if basename.lower().endswith(".json"):
        basename = os.path.splitext(basename)[0]
    # Blender adds .001/.002 when a material with the same name already exists.
    basename = re.sub(r"\.\d{3}$", "", basename)
    lowered = basename.lower()
    aliases = {lowered}
    stripped = re.sub(
        r"^(?:mi|m|mat|material)[_\-.]+", "", lowered, flags=re.IGNORECASE)
    stripped = re.sub(r"(?:[_\-.](?:inst|instance))$", "", stripped)
    aliases.add(stripped)
    tokens = "_".join(normalized_tokens(stripped))
    if tokens:
        aliases.add(tokens)
    return {alias for alias in aliases if alias}


def load_material_records(roots):
    records = []
    for path in discover_files_many(roots, {".json"}):
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, ValueError):
            continue
        textures = payload.get("Textures") if isinstance(payload, dict) else None
        if not isinstance(textures, dict):
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        records.append({
            "name": name,
            "aliases": material_name_aliases(name),
            "path": path,
            "textures": textures,
        })
    return records


def build_texture_index(textures):
    by_asset_name = {}
    for path in textures:
        asset_name = os.path.splitext(os.path.basename(path))[0].lower()
        by_asset_name.setdefault(asset_name, []).append(path)
    return by_asset_name


def unreal_package_path(reference):
    raw = str(reference or "").strip()
    quoted = re.search(r"'([^']+)'", raw)
    if quoted:
        raw = quoted.group(1)
    raw = raw.strip("'\"").replace("\\", "/")
    directory, basename = raw.rsplit("/", 1) if "/" in raw else ("", raw)
    # UE object references use Package.Asset; the exported image is named after
    # the package, not the object suffix.
    if "." in basename:
        basename = basename.split(".", 1)[0]
    return (directory + "/" + basename).strip("/")


def texture_reference_asset_name(reference):
    package = unreal_package_path(reference)
    return package.rsplit("/", 1)[-1] if package else ""


def texture_reference_score(reference, path):
    package = unreal_package_path(reference).lower()
    local = os.path.splitext(os.path.abspath(path))[0].replace("\\", "/").lower()
    relative = package[5:] if package.startswith("game/") else package
    score = 0
    if relative and local.endswith("/end/content/" + relative):
        score += 10000
    elif relative and local.endswith("/" + relative):
        score += 9000
    package_parts = [part for part in relative.split("/") if part]
    local_parts = [part for part in local.split("/") if part]
    suffix = 0
    for expected, actual in zip(reversed(package_parts), reversed(local_parts)):
        if expected != actual:
            break
        suffix += 1
    score += suffix * 100
    return score


def resolve_texture_reference(reference, texture_index):
    asset_name = texture_reference_asset_name(reference).lower()
    candidates = texture_index.get(asset_name, [])
    if not candidates:
        return ""
    scored = sorted(
        ((texture_reference_score(reference, path), path) for path in candidates),
        key=lambda item: (-item[0], item[1].lower()),
    )
    best_score, best_path = scored[0]
    # A basename-only match receives 100 points.  Keep it when it is the only
    # available file (flattened exports), but do not guess between two equally
    # weak candidates from different Unreal packages.
    if len(scored) > 1 and best_score <= 100 and scored[1][0] == best_score:
        return ""
    return best_path


def is_renderer_placeholder(reference):
    package = unreal_package_path(reference).lower()
    return package.startswith("game/renderer/texture/")


def material_record_score(material_name, record):
    if material_name_aliases(material_name) & record["aliases"]:
        return 1000.0
    return material_texture_score(material_name, record["name"])


def find_material_record(material_name, records):
    scored = [(material_record_score(material_name, record), record)
              for record in records]
    scored.sort(key=lambda item: (-item[0], item[1]["path"].lower()))
    if not scored or scored[0][0] < 7.0:
        return None
    return scored[0][1]


def normalized_parameter_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def semantic_texture_paths(material_name, material_records, texture_index):
    record = find_material_record(material_name, material_records)
    if not record:
        return {}, None, set()
    by_key = {}
    for key, reference in record["textures"].items():
        by_key.setdefault(normalized_parameter_key(key), []).append(reference)

    resolved = {}
    placeholder_only_roles = set()
    for role, preferred_keys in SEMANTIC_TEXTURE_KEYS.items():
        ordered_references = []
        for key in preferred_keys:
            normalized_key = normalized_parameter_key(key)
            references = by_key.get(normalized_key, [])
            ordered_references.extend(references)
        meaningful_references = [
            reference for reference in ordered_references
            if not is_renderer_placeholder(reference)
        ]
        if ordered_references and not meaningful_references:
            placeholder_only_roles.add(role)
        for reference in meaningful_references:
            path = resolve_texture_reference(reference, texture_index)
            if path:
                resolved[role] = path
                break
    return resolved, record, placeholder_only_roles


def actorx_file_valid(path):
    if os.path.splitext(path)[1].lower() not in {".psk", ".pskx"}:
        return False
    try:
        if os.path.getsize(path) < 32:
            return False
        with open(path, "rb") as handle:
            return handle.read(20).startswith(b"ACTRHEAD")
    except OSError:
        return False


def model_score(path):
    extension = os.path.splitext(path)[1].lower()
    extension_score = {
        # FFVII Rebirth currently exports invalid glTF tangents through FModel.
        # Prefer a structurally recognizable ActorX file during directory scans;
        # an explicitly selected model_path is still imported unchanged.
        ".pskx": 1000,
        ".psk": 950,
        ".glb": 600,
        ".gltf": 550,
        ".fbx": 500,
        ".obj": 100,
    }.get(extension, 0)
    if extension in {".psk", ".pskx"} and not actorx_file_valid(path):
        extension_score = -10000
    name = os.path.basename(path).lower()
    score = extension_score
    if re.search(r"(?:^|[_\-.])lod0(?:[_\-.]|$)", name):
        score += 80
    if re.search(r"(?:^|[_\-.])sk(?:[_\-.]|$)", name) or "skeletal" in name:
        score += 30
    lod = re.search(r"(?:^|[_\-.])lod([1-9]\d*)(?:[_\-.]|$)", name)
    if lod:
        score -= 100 + int(lod.group(1))
    try:
        score += min(os.path.getsize(path) // (1024 * 1024), 50)
    except OSError:
        pass
    return score


def best_model(root):
    models = discover_files(root, MODEL_EXTENSIONS)
    models.sort(key=lambda path: (-model_score(path), path.lower()))
    return (models[0] if models else ""), models


def operator_exists(module_name, operator_name):
    try:
        operator = getattr(getattr(bpy.ops, module_name), operator_name)
        operator.get_rna_type()
        return True
    # Blender exposes dynamic bpy.ops namespaces even when the concrete
    # operator is not registered. In Blender 3.6, get_rna_type() raises a
    # KeyError for that case.
    except (AttributeError, KeyError, RuntimeError):
        return False


def import_model(path):
    extension = os.path.splitext(path)[1].lower()
    if extension in {".glb", ".gltf"}:
        return bpy.ops.import_scene.gltf(filepath=path)
    elif extension == ".fbx":
        return bpy.ops.import_scene.fbx(filepath=path)
    elif extension == ".obj":
        if operator_exists("wm", "obj_import"):
            return bpy.ops.wm.obj_import(filepath=path)
        elif operator_exists("import_scene", "obj"):
            return bpy.ops.import_scene.obj(filepath=path)
        else:
            raise RuntimeError("当前 Blender 没有可用的 OBJ 导入器")
    elif extension in {".psk", ".pskx"}:
        if operator_exists("psk", "import_file"):
            return bpy.ops.psk.import_file(filepath=path)
        elif operator_exists("import_scene", "psk"):
            return bpy.ops.import_scene.psk(filepath=path)
        else:
            raise RuntimeError(
                "PSK/PSKX 需要 io_scene_psk_psa；Blender 3.6 请安装兼容版 5.0.6")
    else:
        raise RuntimeError("不支持的模型格式: %s" % extension)


def batch_objects(context):
    batch = context.scene.get(ACTIVE_BATCH_KEY, "")
    return [obj for obj in context.scene.objects
            if batch and obj.get(IMPORT_BATCH_KEY, "") == batch]


def remove_previous_batch(context):
    remove_objects(batch_objects(context))


def remove_objects(objects):
    for obj in list(objects):
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def created_objects(context, before):
    return [obj for obj in context.scene.objects if obj not in before]


def repair_mesh_shading(objects):
    """Use smooth vertex normals instead of broken PSK split normals."""
    repaired = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        # io_scene_psk_psa 5.0.6 imports the FF7 meshes with custom split
        # normals plus a 30-degree Auto Smooth threshold.  On these assets that
        # exposes almost every triangle and makes otherwise correct materials
        # look like crumpled foil.  Disabling Auto Smooth retains smooth vertex
        # normals while leaving the mesh, weights and UVs untouched.
        if hasattr(obj.data, "use_auto_smooth"):
            obj.data.use_auto_smooth = False
        obj.data.update()
        repaired += 1
    return repaired


def batch_armature(context):
    armatures = [obj for obj in batch_objects(context)
                 if obj.type == "ARMATURE"]
    active = getattr(context, "object", None)
    if active in armatures:
        return active
    return max(
        armatures,
        key=lambda obj: len(getattr(getattr(obj, "data", None), "bones", [])),
        default=None,
    )


def weighted_vertex_group_names(mesh):
    names = set()
    for vertex in mesh.data.vertices:
        for assignment in vertex.groups:
            if assignment.weight > 1e-8:
                names.add(mesh.vertex_groups[assignment.group].name)
    return names


def mesh_armature(mesh, candidates):
    candidates = set(candidates)
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object in candidates:
            return modifier.object
    if mesh.parent in candidates and mesh.parent.type == "ARMATURE":
        return mesh.parent
    return None


def bone_matrix_difference(first, second):
    return max(
        abs(first.matrix_local[row][column] -
            second.matrix_local[row][column])
        for row in range(4)
        for column in range(4)
    )


def validate_accessory_mesh(mesh, source_armature, target_armature,
                            tolerance=0.01):
    weighted = weighted_vertex_group_names(mesh)
    target_bones = target_armature.data.bones
    source_bones = source_armature.data.bones
    missing = sorted(name for name in weighted if target_bones.get(name) is None)
    if missing:
        return missing, 0.0, ""

    worst_difference = 0.0
    worst_bone = ""
    for name in weighted:
        source_bone = source_bones.get(name)
        target_bone = target_bones.get(name)
        if source_bone is None or target_bone is None:
            continue
        difference = bone_matrix_difference(source_bone, target_bone)
        if difference > worst_difference:
            worst_difference = difference
            worst_bone = name
    if worst_difference > tolerance:
        return [], worst_difference, worst_bone
    return [], worst_difference, ""


def rebind_accessory_mesh(mesh, source_armature, target_armature):
    # Preserve the mesh's local transform relative to its imported skeleton.
    # This also makes an accessory inherit any scale applied to the body root.
    local_matrix = source_armature.matrix_world.inverted() @ mesh.matrix_world
    retargeted = False
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == source_armature:
            modifier.object = target_armature
            retargeted = True
    # Some ActorX importers represent the skeleton relationship only through
    # parenting.  Add the missing modifier so the retained vertex groups
    # actually deform after the temporary accessory armature is removed.
    if not retargeted:
        modifier = mesh.modifiers.new(
            name="FF7RB Armature",
            type="ARMATURE",
        )
        modifier.object = target_armature
    mesh.parent = target_armature
    mesh.matrix_parent_inverse.identity()
    mesh.matrix_basis = local_matrix


def material_has_base_texture(material):
    if not material or not material.use_nodes or not material.node_tree:
        return False
    principled = next(
        (node for node in material.node_tree.nodes
         if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if not principled:
        return False
    socket = principled.inputs.get("Base Color")
    return bool(socket and socket.is_linked)


def material_texture_score(material_name, texture_path):
    material_tokens = [token for token in normalized_tokens(material_name)
                       if not token.isdigit() and token != "m"]
    texture_tokens = texture_stem_tokens(texture_path)
    if not texture_tokens:
        return 0.0
    material_joined = "_".join(material_tokens)
    texture_joined = "_".join(texture_tokens)
    overlap = set(material_tokens) & set(texture_tokens)
    overlap_score = sum(max(2, len(token)) for token in overlap)
    ratio = difflib.SequenceMatcher(None, material_joined, texture_joined).ratio()
    contains = 6.0 if (material_joined and
                       (material_joined in texture_joined or texture_joined in material_joined)) else 0.0
    return overlap_score + ratio * 8.0 + contains


def socket_named(principled, *names):
    for name in names:
        socket = principled.inputs.get(name)
        if socket is not None:
            return socket
    return None


def load_image(path, non_color=False):
    image = bpy.data.images.load(path, check_existing=True)
    try:
        # Image datablocks are shared when check_existing=True.  Set both paths
        # explicitly so a texture previously used as data cannot stay Non-Color
        # when it is later selected as a Base Color map.
        image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    except (TypeError, ValueError):
        pass
    return image


def clear_generated_nodes(material):
    if not material or not material.use_nodes or not material.node_tree:
        return
    nodes = material.node_tree.nodes
    generated = {
        node for node in nodes if node.name.startswith(GENERATED_NODE_PREFIX)
    }
    # Versions before the helper nodes were named still created them directly
    # downstream from an FF7RB image node.  Include those helpers so upgrading
    # and pressing "rematch" once also cleans the old graph.
    helpers = set()
    for node in generated:
        for output in node.outputs:
            for link in output.links:
                if link.to_node.type in {"NORMAL_MAP", "SEPRGB"}:
                    helpers.add(link.to_node)
    for node in helpers | generated:
        nodes.remove(node)


def connect_image(material, principled, path, socket, location, non_color=False):
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.label = os.path.basename(path)
    node.name = GENERATED_NODE_PREFIX + os.path.basename(path)
    node.image = load_image(path, non_color=non_color)
    node.location = location
    material.node_tree.links.new(node.outputs["Color"], socket)
    return node


def is_eye_material_name(name):
    return "eye" in normalized_tokens(name)


def normal_strength_for_material(name):
    tokens = set(normalized_tokens(name))
    if tokens & {"skin", "head", "arms", "eye", "mouth"}:
        return SKIN_NORMAL_STRENGTH
    return DEFAULT_NORMAL_STRENGTH


def connect_eye_base(material, sclera_path, iris_path, socket):
    """Layer the shared sclera and character iris used by FF7 player eyes."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    uv = nodes.new("ShaderNodeUVMap")
    uv.name = GENERATED_NODE_PREFIX + "EyeUV"
    uv.label = "FF7RB Eye UV"
    uv.uv_map = "VTXW0000"
    uv.location = (-1000, 180)

    sclera = nodes.new("ShaderNodeTexImage")
    sclera.name = GENERATED_NODE_PREFIX + os.path.basename(sclera_path)
    sclera.label = os.path.basename(sclera_path)
    sclera.image = load_image(sclera_path)
    sclera.location = (-780, 300)

    iris = nodes.new("ShaderNodeTexImage")
    iris.name = GENERATED_NODE_PREFIX + os.path.basename(iris_path)
    iris.label = os.path.basename(iris_path)
    iris.image = load_image(iris_path)
    iris.location = (-780, 80)

    distance = nodes.new("ShaderNodeVectorMath")
    distance.name = GENERATED_NODE_PREFIX + "EyeDistance"
    distance.label = "FF7RB Iris Distance"
    distance.operation = "DISTANCE"
    distance.inputs[1].default_value = (0.5, 0.5, 0.0)
    distance.location = (-760, -150)

    iris_mask = nodes.new("ShaderNodeValToRGB")
    iris_mask.name = GENERATED_NODE_PREFIX + "EyeIrisMask"
    iris_mask.label = "FF7RB Iris Mask"
    iris_mask.color_ramp.interpolation = "EASE"
    iris_mask.color_ramp.elements[0].position = EYE_IRIS_INNER_RADIUS
    iris_mask.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    iris_mask.color_ramp.elements[1].position = EYE_IRIS_OUTER_RADIUS
    iris_mask.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    iris_mask.location = (-520, -150)

    mix = nodes.new("ShaderNodeMixRGB")
    mix.name = GENERATED_NODE_PREFIX + "EyeColorMix"
    mix.label = "FF7RB Sclera + Iris"
    mix.blend_type = "MIX"
    mix.location = (-280, 240)

    links.new(uv.outputs["UV"], sclera.inputs["Vector"])
    links.new(uv.outputs["UV"], iris.inputs["Vector"])
    links.new(uv.outputs["UV"], distance.inputs[0])
    links.new(distance.outputs["Value"], iris_mask.inputs["Fac"])
    links.new(iris_mask.outputs["Color"], mix.inputs["Fac"])
    links.new(sclera.outputs["Color"], mix.inputs[1])
    links.new(iris.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], socket)
    return sclera


def best_texture(material_name, textures, role):
    candidates = [path for path in textures if texture_role(path) == role]
    if role == "base":
        candidates += [path for path in textures if texture_role(path) == "unknown"]
    scored = [(material_texture_score(material_name, path), path)
              for path in candidates]
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    if not scored or scored[0][0] < 5.0:
        return ""
    return scored[0][1]


def prepare_material(material, textures, material_records=None,
                     texture_index=None, force=False):
    if not material:
        return False

    material_records = material_records or []
    texture_index = texture_index or build_texture_index(textures)
    semantic, record, placeholder_only_roles = semantic_texture_paths(
        material.name, material_records, texture_index)

    def texture_for(role):
        path = semantic.get(role, "")
        # A declared-but-placeholder parameter means "no texture" rather than
        # "guess a similarly named file".  This is important for eyelashes and
        # opaque body materials whose inherited Opacity is a neutral white map.
        if path or (record and role in placeholder_only_roles):
            return path
        return best_texture(material.name, textures, role)

    eye_material = is_eye_material_name(material.name)
    eye_sclera = texture_for("eye_sclera") if eye_material else ""
    eye_iris = texture_for("eye_iris") if eye_material else ""
    had_base_texture = material_has_base_texture(material)
    base = eye_sclera or texture_for("base")
    if (force and not base) or (not had_base_texture and not base):
        return False
    if force:
        clear_generated_nodes(material)
        # Undo alpha state left by an earlier automatic match.  Materials that
        # genuinely need alpha are switched back to HASHED below.
        material.blend_method = "OPAQUE"

    material.use_nodes = True
    nodes = material.node_tree.nodes
    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if principled is None:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (500, 0)
    if not principled.outputs["BSDF"].is_linked:
        material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    changed = False
    base_socket = principled.inputs["Base Color"]
    base_node = None
    if base and (force or not base_socket.is_linked):
        if eye_material and eye_sclera and eye_iris:
            base_node = connect_eye_base(
                material, eye_sclera, eye_iris, base_socket)
        else:
            base_node = connect_image(
                material, principled, base, base_socket, (-600, 240))
        changed = True
    elif base_socket.is_linked:
        base_node = base_socket.links[0].from_node
    if record:
        material["ff7rb_material_json"] = record["path"]

    normal = texture_for("normal")
    normal_socket = socket_named(principled, "Normal")
    if normal and normal_socket and (force or not normal_socket.is_linked):
        normal_image = material.node_tree.nodes.new("ShaderNodeTexImage")
        normal_image.label = os.path.basename(normal)
        normal_image.name = GENERATED_NODE_PREFIX + os.path.basename(normal)
        normal_image.image = load_image(normal, non_color=True)
        normal_image.location = (-900, -120)

        # Unreal tangent-space normal maps use the DirectX Y- convention,
        # while Blender's Normal Map node expects OpenGL Y+.  Reconstruct the
        # color after flipping only the green channel.
        separate_normal = material.node_tree.nodes.new(
            "ShaderNodeSeparateRGB")
        separate_normal.name = GENERATED_NODE_PREFIX + "SeparateNormal"
        separate_normal.label = "FF7RB Split DirectX Normal"
        separate_normal.location = (-650, -120)
        invert_green = material.node_tree.nodes.new("ShaderNodeMath")
        invert_green.name = GENERATED_NODE_PREFIX + "InvertNormalGreen"
        invert_green.label = "FF7RB 1 - Green"
        invert_green.operation = "SUBTRACT"
        invert_green.inputs[0].default_value = 1.0
        invert_green.location = (-440, -180)
        combine_normal = material.node_tree.nodes.new("ShaderNodeCombineRGB")
        combine_normal.name = GENERATED_NODE_PREFIX + "CombineNormal"
        combine_normal.label = "FF7RB OpenGL Normal"
        combine_normal.location = (-220, -120)

        normal_map = material.node_tree.nodes.new("ShaderNodeNormalMap")
        normal_map.name = GENERATED_NODE_PREFIX + "NormalMap"
        normal_map.label = "FF7RB Normal"
        normal_map.inputs["Strength"].default_value = (
            normal_strength_for_material(material.name))
        normal_map.location = (0, -100)

        material.node_tree.links.new(
            normal_image.outputs["Color"], separate_normal.inputs["Image"])
        material.node_tree.links.new(
            separate_normal.outputs["R"], combine_normal.inputs["R"])
        material.node_tree.links.new(
            separate_normal.outputs["G"], invert_green.inputs[1])
        material.node_tree.links.new(
            invert_green.outputs["Value"], combine_normal.inputs["G"])
        material.node_tree.links.new(
            separate_normal.outputs["B"], combine_normal.inputs["B"])
        material.node_tree.links.new(
            combine_normal.outputs["Image"], normal_map.inputs["Color"])
        material.node_tree.links.new(normal_map.outputs["Normal"], normal_socket)
        changed = True

    packed = texture_for("orm")
    roughness_socket = socket_named(principled, "Roughness")
    metallic_socket = socket_named(principled, "Metallic")
    needs_roughness = bool(
        roughness_socket and (force or not roughness_socket.is_linked))
    needs_metallic = bool(
        metallic_socket and (force or not metallic_socket.is_linked))
    if packed and (needs_roughness or needs_metallic):
        packed_node = material.node_tree.nodes.new("ShaderNodeTexImage")
        packed_node.label = os.path.basename(packed)
        packed_node.name = GENERATED_NODE_PREFIX + os.path.basename(packed)
        packed_node.image = load_image(packed, non_color=True)
        packed_node.location = (-650, -400)
        separate = material.node_tree.nodes.new("ShaderNodeSeparateRGB")
        separate.name = GENERATED_NODE_PREFIX + "SeparateORM"
        separate.label = "FF7RB ORM"
        separate.location = (-350, -380)
        material.node_tree.links.new(packed_node.outputs["Color"], separate.inputs["Image"])
        if needs_roughness:
            material.node_tree.links.new(separate.outputs["G"], roughness_socket)
        if needs_metallic:
            material.node_tree.links.new(separate.outputs["B"], metallic_socket)
        changed = True
    else:
        roughness = texture_for("roughness")
        if roughness and needs_roughness:
            connect_image(
                material, principled, roughness, roughness_socket,
                (-650, -400), non_color=True)
            changed = True
        metallic = texture_for("metallic")
        if metallic and needs_metallic:
            connect_image(
                material, principled, metallic, metallic_socket,
                (-650, -560), non_color=True)
            changed = True

    opacity = texture_for("opacity")
    alpha_socket = socket_named(principled, "Alpha")
    if opacity and alpha_socket:
        if force or not alpha_socket.is_linked:
            connect_image(
                material, principled, opacity, alpha_socket,
                (-650, -760), non_color=True)
            changed = True
        if alpha_socket.is_linked:
            material.blend_method = "HASHED"
            material.use_screen_refraction = False
    elif any(token in material.name.lower()
              for token in ("hair", "lash", "brow", "glass", "cloth")) and alpha_socket:
        alpha_output = base_node.outputs.get("Alpha") if base_node else None
        if alpha_output and (force or not alpha_socket.is_linked):
            material.node_tree.links.new(alpha_output, alpha_socket)
            material.blend_method = "HASHED"
            changed = True

    return changed


def prepare_object_materials(objects, texture_root, force=False,
                             source_root=""):
    roots = unique_existing_roots(texture_root, source_root)
    textures = discover_files_many(roots, IMAGE_EXTENSIONS)
    material_records = load_material_records(roots)
    texture_index = build_texture_index(textures)
    materials = []
    seen = set()
    for obj in objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material and material.as_pointer() not in seen:
                seen.add(material.as_pointer())
                materials.append(material)
    prepared = sum(1 for material in materials
                   if prepare_material(
                       material,
                       textures,
                       material_records=material_records,
                       texture_index=texture_index,
                       force=force,
                   ))
    return prepared, len(materials), len(textures)


def prepare_batch_materials(context, texture_root, force=False, source_root=""):
    return prepare_object_materials(
        batch_objects(context),
        texture_root,
        force=force,
        source_root=source_root,
    )


class FF7RB_Props(PropertyGroup):
    source_dir: StringProperty(
        name="FModel 导出目录",
        description="包含 glTF/FBX/PSK 与贴图的 FModel 导出目录",
        subtype="DIR_PATH",
        default=r"D:\ff7rebirth_exports\fmodel_exports",
    )
    model_path: StringProperty(
        name="模型文件",
        description="自动扫描结果，也可手动指定 glTF/FBX/PSK/PSKX/OBJ",
        subtype="FILE_PATH",
    )
    texture_dir: StringProperty(
        name="贴图目录",
        description="留空时扫描 FModel 导出目录",
        subtype="DIR_PATH",
    )
    accessory_model_path: StringProperty(
        name="配件/武器模型",
        description="选择与当前角色共用骨骼名称的 PSK/PSKX 配件模型",
        subtype="FILE_PATH",
    )
    replace_previous: BoolProperty(
        name="替换上次导入",
        description="只删除本插件上一次导入的对象",
        default=True,
    )
    auto_materials: BoolProperty(
        name="导入后匹配基础贴图",
        description="已有 Base Color 贴图连接的材质不会被覆盖",
        default=True,
    )
    auto_fix_shading: BoolProperty(
        name="PSK 导入后修复三角反光",
        description="关闭不兼容的 PSK 分裂法线/Auto Smooth，避免表面像皱纸",
        default=True,
    )
    force_materials: BoolProperty(
        name="覆盖已有基础贴图",
        description="重新匹配材质；仅在自动结果确实需要重做时启用",
        default=False,
    )
    import_scale: FloatProperty(
        name="导入缩放",
        description="导入后应用于根对象；glTF 通常保持 1.0",
        default=1.0,
        min=0.0001,
        max=1000.0,
    )
    diagnostic_report: StringProperty(name="最近检查", default="尚未扫描")


class FF7RB_OT_scan_export(Operator):
    bl_idname = "ff7rb.scan_export"
    bl_label = "扫描导出目录"
    bl_description = "递归查找可导入模型，并优先选择 glTF/FBX、LOD0"

    def execute(self, context):
        props = context.scene.ff7rb
        root = bpy.path.abspath(props.source_dir)
        selected, models = best_model(root)
        images = discover_files(root, IMAGE_EXTENSIONS)
        psk_ready = (operator_exists("psk", "import_file")
                     or operator_exists("import_scene", "psk"))
        if selected:
            props.model_path = selected
        props.diagnostic_report = "\n".join([
            "模型 %d / 贴图 %d" % (len(models), len(images)),
            "已选: %s" % (os.path.basename(selected) if selected else "无"),
            "PSK 导入器: %s" % ("可用" if psk_ready else "未安装"),
        ])
        if not os.path.isdir(root):
            self.report({"ERROR"}, "目录不存在: %s" % root)
            return {"CANCELLED"}
        if not selected:
            self.report({"WARNING"}, "没有找到 glTF/FBX/PSK/PSKX/OBJ")
            return {"CANCELLED"}
        self.report({"INFO"}, "找到 %d 个模型，已选择 %s" %
                    (len(models), os.path.basename(selected)))
        return {"FINISHED"}


class FF7RB_OT_import_model(Operator):
    bl_idname = "ff7rb.import_model"
    bl_label = "导入选中模型"
    bl_description = "导入模型并标记为本插件的当前批次"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.ff7rb
        path = bpy.path.abspath(props.model_path)
        if not os.path.isfile(path):
            path, _ = best_model(bpy.path.abspath(props.source_dir))
            props.model_path = path
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, "请先选择有效的模型文件或扫描导出目录")
            return {"CANCELLED"}

        previous = list(batch_objects(context)) if props.replace_previous else []
        before = set(context.scene.objects)
        try:
            result = import_model(path)
        except Exception as exc:
            remove_objects(created_objects(context, before))
            self.report({"ERROR"}, "导入失败: %s" % exc)
            return {"CANCELLED"}
        created = created_objects(context, before)
        if not result or "FINISHED" not in result or not created:
            remove_objects(created)
            self.report(
                {"ERROR"},
                "导入器已取消或没有创建对象；原有模型已保留",
            )
            return {"CANCELLED"}

        created_set = set(created)
        repaired = 0
        prepared = 0
        try:
            if (props.auto_fix_shading and
                    os.path.splitext(path)[1].lower() in {".psk", ".pskx"}):
                repaired = repair_mesh_shading(created)
            if abs(props.import_scale - 1.0) > 1e-6:
                roots = [obj for obj in created
                         if obj.parent is None or obj.parent not in created_set]
                for obj in roots:
                    obj.scale = tuple(
                        value * props.import_scale for value in obj.scale)

            if props.auto_materials:
                texture_root = bpy.path.abspath(
                    props.texture_dir or props.source_dir)
                prepared, _, _ = prepare_object_materials(
                    created,
                    texture_root,
                    force=props.force_materials,
                    source_root=bpy.path.abspath(props.source_dir),
                )

            bpy.ops.object.select_all(action="DESELECT")
            for obj in created:
                obj.select_set(True)
            context.view_layer.objects.active = next(
                (obj for obj in created if obj.type == "ARMATURE"),
                created[0],
            )
        except Exception as exc:
            remove_objects(created)
            self.report(
                {"ERROR"},
                "导入后处理失败，原有模型已保留: %s" % exc,
            )
            return {"CANCELLED"}

        # Publish the new batch only after every fallible post-import step has
        # succeeded.  Until this point the previous objects and active batch
        # marker are untouched.
        batch = str(time.time_ns())
        for obj in created:
            obj[IMPORT_BATCH_KEY] = batch
        context.scene[ACTIVE_BATCH_KEY] = batch
        if previous:
            remove_objects(previous)
        self.report(
            {"INFO"},
            "已导入 %d 个对象，修复 %d 个网格，准备 %d 个材质" %
            (len(created), repaired, prepared),
        )
        return {"FINISHED"}


class FF7RB_OT_prepare_materials(Operator):
    bl_idname = "ff7rb.prepare_materials"
    bl_label = "重新匹配基础贴图"
    bl_description = "按材质名匹配 Albedo/Normal/Roughness/ORM；不会复刻游戏自定义 Shader"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.ff7rb
        if not batch_objects(context):
            self.report({"ERROR"}, "没有本插件导入的当前模型")
            return {"CANCELLED"}
        texture_root = bpy.path.abspath(props.texture_dir or props.source_dir)
        if not os.path.isdir(texture_root):
            self.report({"ERROR"}, "贴图目录不存在: %s" % texture_root)
            return {"CANCELLED"}
        prepared, materials, textures = prepare_batch_materials(
            context,
            texture_root,
            force=props.force_materials,
            source_root=bpy.path.abspath(props.source_dir),
        )
        self.report(
            {"INFO"},
            "材质 %d 个，贴图 %d 张，本次更新 %d 个" %
            (materials, textures, prepared),
        )
        return {"FINISHED"}


class FF7RB_OT_repair_shading(Operator):
    bl_idname = "ff7rb.repair_shading"
    bl_label = "修复 PSK 三角反光"
    bl_description = "关闭 PSK 导入产生的不兼容分裂法线，让皮肤和衣物恢复平滑"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = batch_objects(context)
        if not objects:
            self.report({"ERROR"}, "没有本插件导入的当前模型")
            return {"CANCELLED"}
        repaired = repair_mesh_shading(objects)
        self.report({"INFO"}, "已修复 %d 个网格的平滑法线" % repaired)
        return {"FINISHED"}


class FF7RB_OT_import_accessory(Operator):
    bl_idname = "ff7rb.import_accessory"
    bl_label = "导入并绑定同骨架配件"
    bl_description = "导入手套等独立 PSK，并在验证权重骨骼后绑定到当前身体骨架"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.ff7rb
        path = bpy.path.abspath(props.accessory_model_path)
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, "请先选择有效的配件 PSK/PSKX 文件")
            return {"CANCELLED"}

        target_armature = batch_armature(context)
        if target_armature is None:
            self.report({"ERROR"}, "请先用本插件导入角色身体模型")
            return {"CANCELLED"}

        before = set(context.scene.objects)
        try:
            result = import_model(path)
        except Exception as exc:
            remove_objects(created_objects(context, before))
            self.report({"ERROR"}, "配件导入失败: %s" % exc)
            return {"CANCELLED"}

        created = created_objects(context, before)
        imported_armatures = [obj for obj in created
                              if obj.type == "ARMATURE"]
        imported_meshes = [obj for obj in created if obj.type == "MESH"]
        if (not result or "FINISHED" not in result or
                not imported_armatures or not imported_meshes):
            remove_objects(created)
            self.report(
                {"ERROR"},
                "配件没有生成完整的骨架与网格；当前角色保持不变",
            )
            return {"CANCELLED"}

        bindings = []
        for mesh in imported_meshes:
            source_armature = mesh_armature(mesh, imported_armatures)
            if source_armature is None:
                remove_objects(created)
                self.report(
                    {"ERROR"},
                    "配件网格 %s 没有可识别的导入骨架" % mesh.name,
                )
                return {"CANCELLED"}
            missing, difference, incompatible_bone = validate_accessory_mesh(
                mesh, source_armature, target_armature)
            if missing:
                remove_objects(created)
                preview = ", ".join(missing[:5])
                self.report(
                    {"ERROR"},
                    "骨骼不兼容，身体缺少 %d 个权重骨骼: %s" %
                    (len(missing), preview),
                )
                return {"CANCELLED"}
            if incompatible_bone:
                remove_objects(created)
                self.report(
                    {"ERROR"},
                    "骨架静止姿势不兼容: %s (差异 %.6f)" %
                    (incompatible_bone, difference),
                )
                return {"CANCELLED"}
            bindings.append((mesh, source_armature))

        retained = [obj for obj in created if obj not in imported_armatures]
        prepared = 0
        try:
            for mesh, source_armature in bindings:
                rebind_accessory_mesh(
                    mesh, source_armature, target_armature)
            if props.auto_fix_shading:
                repair_mesh_shading(retained)

            if props.auto_materials:
                texture_root = bpy.path.abspath(
                    props.texture_dir or props.source_dir)
                prepared, _, _ = prepare_object_materials(
                    retained,
                    texture_root,
                    force=props.force_materials,
                    source_root=bpy.path.abspath(props.source_dir),
                )

            bpy.ops.object.select_all(action="DESELECT")
            for obj in retained:
                obj.select_set(True)
            context.view_layer.objects.active = target_armature
        except Exception as exc:
            remove_objects(created)
            self.report(
                {"ERROR"},
                "配件后处理失败，本次导入已回滚: %s" % exc,
            )
            return {"CANCELLED"}

        remove_objects(imported_armatures)
        batch = context.scene.get(ACTIVE_BATCH_KEY, "")
        for obj in retained:
            obj[IMPORT_BATCH_KEY] = batch
        self.report(
            {"INFO"},
            "已绑定 %d 个配件网格到 %s，并准备 %d 个材质" %
            (len(imported_meshes), target_armature.name, prepared),
        )
        return {"FINISHED"}


class FF7RB_PT_panel(Panel):
    bl_label = "FF7 Rebirth Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FF7RB"

    def draw(self, context):
        props = context.scene.ff7rb
        layout = self.layout

        source = layout.box()
        source.label(text="1. 先选择 FModel 导出目录", icon="FILE_FOLDER")
        source.prop(props, "source_dir", text="")
        source.operator("ff7rb.scan_export", icon="VIEWZOOM")
        for line in props.diagnostic_report.splitlines()[:3]:
            source.label(text=line)

        model = layout.box()
        model.label(text="2. 选择并导入模型", icon="OUTLINER_OB_MESH")
        model.prop(props, "model_path", text="")
        model.prop(props, "replace_previous")
        model.prop(props, "import_scale")
        model.prop(props, "auto_materials")
        model.prop(props, "auto_fix_shading")
        model.operator("ff7rb.import_model", icon="IMPORT")

        material = layout.box()
        material.label(text="3. 基础材质", icon="MATERIAL")
        material.prop(props, "texture_dir")
        material.prop(props, "force_materials")
        material.operator("ff7rb.prepare_materials", icon="FILE_REFRESH")
        material.operator("ff7rb.repair_shading", icon="MOD_NORMALEDIT")
        material.label(text="复杂皮肤/眼睛 Shader 仍需人工校正", icon="INFO")

        accessory = layout.box()
        accessory.label(text="4. 独立配件/武器", icon="MOD_ARMATURE")
        accessory.prop(props, "accessory_model_path", text="")
        accessory.operator("ff7rb.import_accessory", icon="LINKED")
        accessory.label(text="会先验证权重骨骼与静止姿势", icon="INFO")


classes = (
    FF7RB_Props,
    FF7RB_OT_scan_export,
    FF7RB_OT_import_model,
    FF7RB_OT_prepare_materials,
    FF7RB_OT_repair_shading,
    FF7RB_OT_import_accessory,
    FF7RB_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ff7rb = PointerProperty(type=FF7RB_Props)


def unregister():
    del bpy.types.Scene.ff7rb
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
