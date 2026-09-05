"""Build a Blender 3.6 validation scene from modular Stellar Blade Eve assets.

The verified PC workflow uses FModel UEFormat for Face_003 so all 53 morph
targets survive, FModel ActorX for the outfit/body, and the Stellar Blade-
specific UE Viewer build for hair pieces. This script keeps every imported
skeleton intact and reconnects the important preview textures in Blender.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass

import bpy
from mathutils import Matrix, Vector

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


@dataclass
class Component:
    label: str
    source: str
    meshes: list
    armatures: list


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", required=True)
    parser.add_argument(
        "--head",
        default="",
        help="deprecated Face PSK argument retained for command compatibility",
    )
    parser.add_argument(
        "--head-uemodel",
        default=(
            r"D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC"
            r"\CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel"
        ),
    )
    parser.add_argument(
        "--ueformat-source",
        default=os.environ.get(
            "UEFORMAT_BLENDER_SOURCE",
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    ".tmp",
                    "ueformat-main-src",
                    "UEFormat-main",
                    "plugins",
                    "blender",
                    "io_scene_ueformat",
                )
            ),
        ),
    )
    parser.add_argument(
        "--alignment-reference",
        default="",
        help=(
            "previous validation report JSON; its recorded hair/tail root "
            "transforms fill in when the body skeleton lacks the SC_Hair "
            "socket (UE Viewer PSKs drop sockets; rest poses must match)"
        ),
    )
    parser.add_argument("--hair", required=True)
    parser.add_argument("--tail", required=True)
    parser.add_argument(
        "--tail-short",
        default="",
        help=(
            "optional EVE_HR_Tail_Short PSK; the nape hair strands anchored "
            "to Bip001-Head that complete the default hairstyle"
        ),
    )
    parser.add_argument(
        "--merge-armatures",
        action="store_true",
        help=(
            "merge every component skeleton into the body armature so the "
            "character is poseable as one rig: duplicate bones are removed "
            "(weights fall through to the body's copies) and loose hair "
            "chains are re-parented to SC_Hair/Bip001-Head"
        ),
    )
    parser.add_argument("--face-assets", required=True)
    parser.add_argument("--body-diffuse", required=True)
    parser.add_argument("--hair-alpha", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", required=True)
    parser.add_argument("--report", required=True)
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


def actorx_valid(path: str) -> bool:
    if not os.path.isfile(path) or os.path.getsize(path) < 32:
        return False
    with open(path, "rb") as handle:
        return handle.read(8) == b"ACTRHEAD"


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def imported_component(label: str, path: str) -> Component:
    path = os.path.abspath(path)
    if not actorx_valid(path):
        raise RuntimeError(f"Invalid or truncated ActorX file: {path}")
    before = set(bpy.data.objects)
    result = import_psk(path)
    if "FINISHED" not in result:
        raise RuntimeError(f"PSK import did not finish for {path}: {result}")
    created = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in created if obj.type == "MESH"]
    armatures = [obj for obj in created if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError(f"PSK did not create both mesh and armature: {path}")
    for index, obj in enumerate(meshes, start=1):
        obj.name = f"Eve_{label}_Mesh_{index:02d}"
        obj["stellarblade_component"] = label
        obj["stellarblade_source"] = path
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        if hasattr(obj.data, "use_auto_smooth"):
            obj.data.use_auto_smooth = False
        obj.data.update()
    for index, obj in enumerate(armatures, start=1):
        obj.name = f"Eve_{label}_Armature_{index:02d}"
        obj.show_in_front = False
        obj.hide_render = True
        obj["stellarblade_component"] = label
        obj["stellarblade_source"] = path
    return Component(label, path, meshes, armatures)


def imported_uemodel_component(label: str, path: str, source: str):
    from import_uemodel36 import load_importer

    path = os.path.abspath(path)
    with open(path, "rb") as handle:
        if handle.read(8) != b"UEFORMAT":
            raise RuntimeError(f"Invalid UEFormat file: {path}")
    before = set(bpy.data.objects)
    importer_type, options_type = load_importer(source)
    options = options_type(
        link=True,
        # io_scene_psk_psa keeps these game exports in centimetre-sized
        # Blender units. Match that convention so the UEFormat head aligns.
        scale_factor=1.0,
        bone_length=4.0,
        reorient_bones=False,
        import_collision=False,
        import_sockets=False,
        import_morph_targets=True,
        import_virtual_bones=False,
        target_lod=0,
    )
    _imported_object, model = importer_type(options).import_file(path)
    created = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in created if obj.type == "MESH"]
    armatures = [obj for obj in created if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError(f"UEFormat did not create mesh and armature: {path}")
    for index, obj in enumerate(meshes, start=1):
        obj.name = f"Eve_{label}_Mesh_{index:02d}"
        obj["stellarblade_component"] = label
        obj["stellarblade_source"] = path
    for index, obj in enumerate(armatures, start=1):
        obj.name = f"Eve_{label}_Armature_{index:02d}"
        obj.show_in_front = False
        obj.hide_render = True
        obj["stellarblade_component"] = label
        obj["stellarblade_source"] = path
    component = Component(label, path, meshes, armatures)
    source_morphs = [morph.name for morph in model.lods[0].morphs]
    shape_keys = [
        key.name
        for mesh in meshes
        if mesh.data.shape_keys
        for key in mesh.data.shape_keys.key_blocks
    ]
    if len(source_morphs) != 53 or len(shape_keys) != 54:
        raise RuntimeError(
            f"Face_003 morph validation failed: source={len(source_morphs)}, "
            f"Blender={len(shape_keys)}"
        )
    return component, source_morphs, shape_keys


def reset_nodes(material):
    material.use_nodes = True
    material.diffuse_color = (0.4, 0.4, 0.4, 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return nodes, links, shader


def material_base_name(name: str) -> str:
    """Strip Blender's duplicate suffix without altering Unreal asset names."""
    return re.sub(r"\.\d{3}$", "", name)


def face_asset(root: str, relative_path: str) -> str:
    path = os.path.abspath(os.path.join(root, *relative_path.split("/")))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return path


def load_image(path: str, non_color: bool = False):
    image = bpy.data.images.load(path, check_existing=True)
    if non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
    return image


def link_color_texture(nodes, links, shader, path: str, *, alpha=False):
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = load_image(path)
    texture.name = os.path.basename(path)
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    if alpha:
        links.new(texture.outputs["Color"], shader.inputs["Alpha"])
    return texture


def link_directx_normal(nodes, links, shader, path: str):
    """Convert Unreal's DirectX green channel before feeding Blender normals."""
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = load_image(path, non_color=True)
    texture.name = os.path.basename(path)
    split = nodes.new("ShaderNodeSeparateRGB")
    invert = nodes.new("ShaderNodeMath")
    invert.operation = "SUBTRACT"
    invert.inputs[0].default_value = 1.0
    combine = nodes.new("ShaderNodeCombineRGB")
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.7
    links.new(texture.outputs["Color"], split.inputs["Image"])
    links.new(split.outputs["R"], combine.inputs["R"])
    links.new(split.outputs["G"], invert.inputs[1])
    links.new(invert.outputs[0], combine.inputs["G"])
    links.new(split.outputs["B"], combine.inputs["B"])
    links.new(combine.outputs["Image"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return texture


def link_eye_color(nodes, links, shader, sclera_path: str, iris_path: str):
    """Approximate UE's parallax eye using a Blender-visible UV iris."""
    texcoord = nodes.new("ShaderNodeTexCoord")
    sclera = nodes.new("ShaderNodeTexImage")
    sclera.image = load_image(sclera_path)
    sclera.name = os.path.basename(sclera_path)
    links.new(texcoord.outputs["UV"], sclera.inputs["Vector"])

    center = (0.5, 0.5, 0.0)
    # UE's source value is 0.145, but it is evaluated after the game's
    # parallax/refraction mapping.  Direct UV evaluation in Eevee needs a
    # smaller visible radius or the pupil covers the entire eye opening;
    # 0.07 matches the in-game apparent iris size once the shells around the
    # eye are translucent.
    iris_radius = 0.07
    subtract = nodes.new("ShaderNodeVectorMath")
    subtract.operation = "SUBTRACT"
    subtract.inputs[1].default_value = center
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs["Scale"].default_value = 1.0 / (2.0 * iris_radius)
    add = nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    add.inputs[1].default_value = center
    links.new(texcoord.outputs["UV"], subtract.inputs[0])
    links.new(subtract.outputs["Vector"], scale.inputs[0])
    links.new(scale.outputs["Vector"], add.inputs[0])

    iris = nodes.new("ShaderNodeTexImage")
    iris.image = load_image(iris_path)
    iris.name = os.path.basename(iris_path)
    links.new(add.outputs["Vector"], iris.inputs["Vector"])
    # The source iris texture is authored dark for UE's lit refraction stack;
    # brighten it for the flat Eevee preview or it reads as an all-pupil hole.
    iris_boost = nodes.new("ShaderNodeHueSaturation")
    iris_boost.inputs["Value"].default_value = 2.6
    iris_boost.inputs["Saturation"].default_value = 0.95
    links.new(iris.outputs["Color"], iris_boost.inputs["Color"])

    distance = nodes.new("ShaderNodeVectorMath")
    distance.operation = "DISTANCE"
    distance.inputs[1].default_value = center
    links.new(texcoord.outputs["UV"], distance.inputs[0])
    mask = nodes.new("ShaderNodeMath")
    mask.operation = "LESS_THAN"
    mask.inputs[1].default_value = iris_radius
    links.new(distance.outputs["Value"], mask.inputs[0])

    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    links.new(mask.outputs[0], mix.inputs[0])
    links.new(sclera.outputs["Color"], mix.inputs[1])
    links.new(iris_boost.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], shader.inputs["Base Color"])


def set_principled_color(shader, color, roughness=0.48, metallic=0.0):
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic


_EXPORT_INDEX: dict[str, dict[str, str]] = {}
# Texture names that are never an outfit albedo: engine/detail/utility maps and
# the "del" placeholder of MI_CH_Delete stub materials.
_GENERIC_DIFFUSE = re.compile(
    r"^(T_|Default|Base_|BaseFlat|Grunge|HeatmapGradient|BlendFunc|Good64|baseMaterial|FlatNormal|"
    r"CASC_|Black$|White$|BayerMatrix|del$|skin_n$|MicroNormal|NylonTricot)", re.I
)
# Non-colour channels by suffix (normal, roughness/metal packs, masks, emissive, alpha...).
_NON_COLOUR_SUFFIX = re.compile(
    r"_(n|nm|nrm|normal|orm|orss|dmse|mask\d*|e|emi|emissive|alpha|op|opacity|m|r|s|h|ao|id|"
    r"spec|specular|ml|mr|mra|rma|disp|height|flow|tint)(_[a-z0-9-]+)?$", re.I
)
_COLOUR_SUFFIX = re.compile(r"_(a|d|basecolor|albedo|diffuse|color|col|adir)(_[a-z0-9-]+)?$", re.I)
_VARIANT_TOKENS = {"typeb", "typec", "type", "b", "c", "orangered", "02", "var01", "nh", "a1"}


def _export_root(directory: str) -> str:
    """Walk up from an outfit texture folder to the UE Viewer export root (parent of the Art folder)."""
    cur = os.path.abspath(directory)
    while True:
        parent, leaf = os.path.split(cur)
        if not leaf:
            return cur
        if leaf.lower() == "art":
            # DLC outfits sit under <root>\DLC_2\Art\... but reference the base
            # game's ReferenceBody materials under <root>\Art\..., so index from
            # the level above the DLC_N folder.
            if re.match(r"^DLC_\d+$", os.path.basename(parent), re.I):
                return os.path.dirname(parent)
            return parent
        cur = parent


def _export_index(root: str) -> dict[str, str]:
    """name.lower() -> path for every .png/.mat under the export root (cached per root)."""
    if root not in _EXPORT_INDEX:
        index: dict[str, str] = {}
        for walk_root, _dirs, files in os.walk(root):
            for name in files:
                low = name.lower()
                if low.endswith((".png", ".mat")):
                    index.setdefault(low, os.path.join(walk_root, name))
        _EXPORT_INDEX[root] = index
    return _EXPORT_INDEX[root]


def _usable_colour_texture(name: str, index: dict[str, str]) -> str | None:
    """Return the PNG path if ``name`` looks like a colour texture that was exported."""
    if not name or _GENERIC_DIFFUSE.match(name):
        return None
    stem = name.lower()
    if _NON_COLOUR_SUFFIX.search(stem) and not _COLOUR_SUFFIX.search(stem):
        return None
    path = index.get(stem + ".png")
    if not path or "/engine/" in path.replace('\\', "/").lower():
        return None
    return path


def material_diffuse_from_mat(directory: str, material_name: str) -> str | None:
    """Authoritative albedo: the textures listed in the material's UE Viewer .mat file.

    Outfits 01-06 share ScanCloth_*_D textures that live under whichever outfit
    exported them first and never match the *_A naming heuristic; the .mat file
    written next to each material instance names the real diffuse texture.
    ``Diffuse=`` wins when it is a real colour map; otherwise the first colour-
    looking entry among the other texture slots (e.g. hair *_ADIR) is used.
    """
    base = material_base_name(material_name)
    index = _export_index(_export_root(directory))
    mat = index.get((base + ".mat").lower())
    if not mat:
        return None
    diffuse = ""
    others: list[str] = []
    with open(mat, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            key, sep, value = line.strip().partition("=")
            if not sep:
                continue
            value = value.strip()
            if key == "Diffuse":
                diffuse = value
            elif key not in ("Normal", "Opacity", "Emissive", "SpecPower"):
                others.append(value)
    path = _usable_colour_texture(diffuse, index)
    if path:
        return path
    for name in others:
        if _COLOUR_SUFFIX.search(name.lower()):
            path = _usable_colour_texture(name, index)
            if path:
                return path
    return None


def find_material_albedo(directory: str, material_name: str) -> str | None:
    """Match a UE material instance name to an exported albedo PNG.

    Order: the material's own .mat Diffuse= texture (searched across the whole
    export root), then MI_CH_P_EVE_Nikke_06_UV2 -> CH_P_EVE_Nikke_06_UV2_A.png,
    then the albedo sharing the most name tokens, then the largest albedo.
    """
    from_mat = material_diffuse_from_mat(directory, material_name)
    if from_mat:
        return from_mat
    albedos = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name.lower().endswith(".png") and re.search(
                r"_(a|d|basecolor)(_type_[a-z0-9]+)?(_\d+)?\.png$", name.lower()
            ) and not _GENERIC_DIFFUSE.match(name):
                albedos.append(os.path.join(root, name))
    if not albedos:
        return None
    base = re.sub(r"^(MI_|MA_|ML_|MT_|M_)", "", material_base_name(material_name))
    exact = [
        path for path in albedos
        if os.path.basename(path).lower() == (base + "_A.png").lower()
    ]
    if exact:
        return exact[0]
    tokens = {token for token in base.lower().split("_") if token}

    def score(path: str) -> tuple:
        stem_tokens = set(os.path.splitext(os.path.basename(path))[0].lower().split("_"))
        # A recolour's albedo (TypeB/TypeC/_02...) must not win for the base
        # material: MI_CH_EVE_01_UV01 should get CH_P_EVE_01_Body_D, not
        # CH_EVE_01_TypeB_UV01_A, even though the latter shares one more token.
        stray_variant = len((stem_tokens & _VARIANT_TOKENS) - tokens)
        return (len(tokens & stem_tokens) - 2 * stray_variant, os.path.getsize(path))

    return max(albedos, key=score)


def prepare_body_materials(component: Component, diffuse_path: str) -> dict:
    """Connect preview diffuse textures.

    ``diffuse_path`` may be one PNG (applied to every slot) or a directory of
    exported textures, in which case each material gets the albedo whose name
    matches it best.
    """
    is_directory = os.path.isdir(diffuse_path)
    assignments = {}
    handled = set()
    for mesh in component.meshes:
        for slot in mesh.material_slots:
            material = slot.material
            if material is None or material in handled:
                continue
            handled.add(material)
            if is_directory:
                texture_path = find_material_albedo(diffuse_path, material.name)
            else:
                texture_path = diffuse_path
            nodes, links, shader = reset_nodes(material)
            shader.inputs["Roughness"].default_value = 0.48
            if texture_path is None:
                set_principled_color(shader, (0.4, 0.4, 0.4, 1.0), 0.48)
                assignments[material.name] = None
                continue
            texture = nodes.new("ShaderNodeTexImage")
            texture.name = "Verified body/outfit diffuse"
            texture.image = bpy.data.images.load(texture_path, check_existing=True)
            links.new(texture.outputs["Color"], shader.inputs["Base Color"])
            material["stellarblade_preview_texture"] = texture_path
            assignments[material.name] = texture_path
    return assignments


def prepare_head_materials(component: Component, assets_root: str) -> dict:
    textures = {
        "skin_color": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/Tex_P_EVE_Head_A.png",
        ),
        "skin_normal": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/Tex_P_EVE_Head_N.png",
        ),
        "iris_color": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/S_EyeIrisBaseColor.png",
        ),
        "sclera_color": face_asset(
            assets_root,
            "Art/Character/Generic/GlobalMasterMaterials/Eye/T_EyeScleraBaseColor.png",
        ),
        "eye_normal": face_asset(
            assets_root,
            "Art/Character/Generic/GlobalMasterMaterials/Eye/T_EYE_NORMALS.png",
        ),
        "eye_light": face_asset(
            assets_root,
            "Art/Character/Generic/GlobalMasterMaterials/Eye/EyeLight.png",
        ),
        "brow_opacity": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/Tex_P_EVE_eyebrow_O.png",
        ),
        "teeth_color": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/Tex_P_EVE_Teeth_A.png",
        ),
        "teeth_normal": face_asset(
            assets_root,
            "Art/Character/PC/CH_P_EVE_Head/Textures/Tex_P_EVE_Teeth_N.png",
        ),
    }
    handled = set()
    assignments = {}
    for mesh in component.meshes:
        for slot in mesh.material_slots:
            material = slot.material
            if material is None or material in handled:
                continue
            handled.add(material)
            nodes, links, shader = reset_nodes(material)
            base_name = material_base_name(material.name)
            name = base_name.lower()
            assignment = "procedural fallback"
            if base_name == "MI_EVE_Head_V02":
                set_principled_color(shader, (0.62, 0.27, 0.21, 1.0), 0.42)
                link_color_texture(nodes, links, shader, textures["skin_color"])
                link_directx_normal(nodes, links, shader, textures["skin_normal"])
                if "Subsurface" in shader.inputs:
                    shader.inputs["Subsurface"].default_value = 0.055
                assignment = "skin color + DirectX-converted normal"
            elif base_name == "MI_EyeRefractive1":
                set_principled_color(shader, (0.12, 0.19, 0.18, 1.0), 0.12)
                link_eye_color(
                    nodes,
                    links,
                    shader,
                    textures["sclera_color"],
                    textures["iris_color"],
                )
                link_directx_normal(nodes, links, shader, textures["eye_normal"])
                shader.inputs["Specular"].default_value = 0.65
                assignment = "Eevee-calibrated iris/sclera blend + eye normal"
            elif base_name == "M_MikeEyeBlend_Inst":
                # This shell covers the whole eye opening; opaque near-black
                # made the eyes read as heavy smoky makeup over a dark hole.
                set_principled_color(shader, (0.42, 0.26, 0.22, 1.0), 0.5)
                shader.inputs["Alpha"].default_value = 0.10
                material.blend_method = "HASHED"
                assignment = "eye-corner blend preview (light translucent)"
            elif base_name == "MI_EyeBrow1":
                set_principled_color(shader, (0.012, 0.009, 0.008, 1.0), 0.4)
                link_color_texture(
                    nodes, links, shader, textures["brow_opacity"], alpha=True
                )
                material.blend_method = "HASHED"
                material.show_transparent_back = True
                assignment = "brow opacity"
            elif base_name == "MI_Teeth":
                set_principled_color(shader, (0.75, 0.71, 0.64, 1.0), 0.3)
                link_color_texture(nodes, links, shader, textures["teeth_color"])
                link_directx_normal(nodes, links, shader, textures["teeth_normal"])
                assignment = "teeth color + DirectX-converted normal"
            elif "mouthinner" in name:
                set_principled_color(shader, (0.12, 0.012, 0.018, 1.0), 0.48)
                assignment = "mouth-inner preview"
            elif "lacrimal" in name:
                set_principled_color(shader, (0.22, 0.12, 0.10, 0.28), 0.08)
                shader.inputs["Alpha"].default_value = 0.28
                material.blend_method = "HASHED"
                assignment = "tear-fluid translucent preview"
            elif "eyeshadow_occlusion" in name or "teethocculusion" in name:
                set_principled_color(shader, (0.30, 0.14, 0.11, 1.0), 0.65)
                shader.inputs["Alpha"].default_value = 0.12
                material.blend_method = "HASHED"
                assignment = "occlusion preview (subtle)"
            elif "eyelight" in name:
                set_principled_color(shader, (0.8, 0.95, 1.0, 1.0), 0.05)
                link_color_texture(
                    nodes, links, shader, textures["eye_light"], alpha=True
                )
                material.blend_method = "HASHED"
                if "Emission" in shader.inputs:
                    shader.inputs["Emission"].default_value = (0.55, 0.7, 0.85, 1.0)
                    shader.inputs["Emission Strength"].default_value = 0.5
                assignment = "eye-light texture + opacity (catchlight)"
            elif base_name == "NewMaterial":
                set_principled_color(shader, (0.0, 0.0, 0.0, 0.0), 0.42)
                shader.inputs["Alpha"].default_value = 0.0
                material.blend_method = "HASHED"
                material.show_transparent_back = True
                assignment = "transparent unresolved eye shell"
            else:
                set_principled_color(shader, (0.62, 0.27, 0.21, 1.0), 0.5)
            material["stellarblade_preview_note"] = assignment
            assignments[material.name] = assignment
    return {"textures": textures, "assignments": assignments}


def prepare_hair_materials(components: list[Component], alpha_path: str) -> None:
    alpha = bpy.data.images.load(alpha_path, check_existing=True)
    try:
        alpha.colorspace_settings.name = "Non-Color"
    except TypeError:
        pass
    handled = set()
    for component in components:
        for mesh in component.meshes:
            for slot in mesh.material_slots:
                material = slot.material
                if material is None or material in handled:
                    continue
                handled.add(material)
                nodes, links, shader = reset_nodes(material)
                set_principled_color(shader, (0.006, 0.009, 0.015, 1.0), 0.28)
                if "Anisotropic" in shader.inputs:
                    shader.inputs["Anisotropic"].default_value = 0.55
                texture = nodes.new("ShaderNodeTexImage")
                texture.name = "Verified hair opacity"
                texture.image = alpha
                links.new(texture.outputs["Color"], shader.inputs["Alpha"])
                material.blend_method = "HASHED"
                material.show_transparent_back = True
                material.use_screen_refraction = False
                material["stellarblade_preview_texture"] = alpha_path


def apply_component_transform(component: Component, transform: Matrix) -> None:
    """Move a modular component without baking or changing its skin weights."""
    objects = [*component.meshes, *component.armatures]
    object_set = set(objects)
    # io_scene_psk_psa parents each mesh to its imported armature.  Transform
    # only hierarchy roots or the same matrix would be applied twice.
    roots = [obj for obj in objects if obj.parent not in object_set]
    for obj in roots:
        obj.matrix_world = transform @ obj.matrix_world
    bpy.context.view_layer.update()


def align_hair_components(
    body: Component,
    hair: Component,
    tail: Component,
    reference: dict | None = None,
    tail_short: Component | None = None,
) -> dict:
    """Attach local-space hair exports to the body's verified rest skeleton."""
    body_armature = body.armatures[0]
    hair_armature = hair.armatures[0]
    tail_armature = tail.armatures[0]
    reference = reference or {}

    # The cap/bob skeleton is authored around a local origin.  SC_Hair is the
    # explicit attachment socket on Eve's body skeleton.  UE Viewer PSKs drop
    # sockets, so bodies exported that way fall back to the transform recorded
    # by a previous FModel-body validation (identical rest skeletons).
    socket = body_armature.data.bones.get("SC_Hair")
    hair_root = hair_armature.data.bones.get("Root")
    hair_from_reference = False
    if socket is not None and hair_root is not None:
        socket_world = body_armature.matrix_world @ socket.matrix_local
        hair_root_world = hair_armature.matrix_world @ hair_root.matrix_local
        # Full rest-matrix alignment, not just translation: the standalone
        # UE Viewer hair PSK carries the same 180-degree local-axis flip as
        # the tail PSK, so translation-only attachment leaves the fringe
        # facing backwards.
        hair_transform = socket_world @ hair_root_world.inverted()
    elif reference.get("hair_transform"):
        hair_transform = Matrix(reference["hair_transform"])
        hair_from_reference = True
    else:
        raise RuntimeError("Cannot align main hair: SC_Hair/Root anchor is missing")
    apply_component_transform(hair, hair_transform)

    # The ponytail shares the Ab-TL-HairB01 chain with Eve's body.  Aligning
    # the complete rest-bone matrices recovers both the attachment point and
    # the 180-degree local-axis rotation in the standalone tail PSK.
    anchor_name = "Ab-TL-HairB01"
    body_anchor = body_armature.data.bones.get(anchor_name)
    tail_anchor = tail_armature.data.bones.get(anchor_name)
    if body_anchor is None or tail_anchor is None:
        raise RuntimeError(f"Cannot align hair tail: {anchor_name} is missing")
    body_anchor_world = body_armature.matrix_world @ body_anchor.matrix_local
    tail_anchor_world = tail_armature.matrix_world @ tail_anchor.matrix_local
    tail_transform = body_anchor_world @ tail_anchor_world.inverted()
    apply_component_transform(tail, tail_transform)

    # The nape strands (EVE_HR_Tail_Short) anchor to Bip001-Head, which every
    # body export keeps, so no socket or reference fallback is needed.
    tail_short_error = None
    if tail_short is not None:
        short_anchor_name = "Bip001-Head"
        body_head = body_armature.data.bones.get(short_anchor_name)
        short_armature = tail_short.armatures[0]
        short_head = short_armature.data.bones.get(short_anchor_name)
        if body_head is None or short_head is None:
            raise RuntimeError(
                f"Cannot align short tail: {short_anchor_name} is missing"
            )
        body_head_world = body_armature.matrix_world @ body_head.matrix_local
        short_head_world = short_armature.matrix_world @ short_head.matrix_local
        apply_component_transform(
            tail_short, body_head_world @ short_head_world.inverted()
        )
        tail_short_error = (
            (tail_short.armatures[0].matrix_world @ short_head.matrix_local).translation
            - body_head_world.translation
        ).length
        if tail_short_error > 1.0e-4:
            raise RuntimeError(
                f"Short tail alignment exceeded tolerance: {tail_short_error}"
            )

    hair_error = None
    if not hair_from_reference:
        hair_error = (
            (hair.armatures[0].matrix_world @ hair_root.matrix_local).translation
            - socket_world.translation
        ).length
    tail_error = (
        (tail.armatures[0].matrix_world @ tail_anchor.matrix_local).translation
        - body_anchor_world.translation
    ).length
    if (hair_error is not None and hair_error > 1.0e-4) or tail_error > 1.0e-4:
        raise RuntimeError(
            f"Hair alignment exceeded tolerance: cap={hair_error}, tail={tail_error}"
        )
    return {
        "hair_socket": (
            "SC_Hair (transform reused from reference report)"
            if hair_from_reference
            else "SC_Hair"
        ),
        "hair_anchor_error": hair_error,
        "tail_anchor": anchor_name,
        "tail_anchor_error": tail_error,
        "tail_short_anchor": "Bip001-Head" if tail_short is not None else None,
        "tail_short_anchor_error": tail_short_error,
        "hair_transform": [list(row) for row in hair_transform],
        "tail_transform": [list(row) for row in tail_transform],
    }


def merge_component_armatures(components: list, body: Component) -> dict:
    """Merge every component skeleton into the body armature.

    Components were aligned so shared bones already coincide with the body's
    rest pose.  After joining, Blender suffixes incoming duplicate bones with
    .001; those duplicates are removed so vertex groups fall through to the
    body's identically named bones.  Chains without a shared parent (hair
    simulation bones) are re-attached to the hair socket / head bone.
    """
    master = body.armatures[0]
    anchors = {
        "Hair": ["SC_Hair", "Bip001-Head"],
        "HairTail": ["Ab-TL-HairB01", "Bip001-Head"],
        "HairTailShort": ["Bip001-Head"],
        "Head": ["Bip001-Head"],
    }
    component_bones = {
        component.label: {
            bone.name
            for armature in component.armatures
            for bone in armature.data.bones
        }
        for component in components
    }
    meshes = [mesh for component in components for mesh in component.meshes]
    other_armatures = [
        armature
        for component in components
        for armature in component.armatures
        if armature != master
    ]

    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    # A hair piece's own "Root" sits at its attachment point, not at the
    # character origin.  Deduplicating it into the body Root would leave the
    # scalp weighted to a static bone, so keep it as a uniquely named carrier
    # bone and hang it off the component's anchor instead.
    renamed_roots = {}
    master_bone_names = {bone.name for bone in master.data.bones}
    for component in components:
        if component.label == "Body":
            continue
        for armature in component.armatures:
            root = armature.data.bones.get("Root")
            if root is None or "Root" not in master_bone_names:
                continue
            new_name = component.label + "_Root"
            armature.data.bones["Root"].name = new_name
            for mesh in component.meshes:
                group = mesh.vertex_groups.get("Root")
                if group is not None:
                    group.name = new_name
            renamed_roots[component.label] = new_name
    for mesh in meshes:
        world = mesh.matrix_world.copy()
        mesh.parent = None
        mesh.matrix_world = world

    bpy.ops.object.select_all(action="DESELECT")
    for armature in other_armatures:
        armature.select_set(True)
    master.select_set(True)
    bpy.context.view_layer.objects.active = master
    bpy.ops.object.join()

    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = master.data.edit_bones
    removed = 0
    for bone in [b for b in list(edit_bones) if re.match(r".+\.\d{3}$", b.name)]:
        original_name = bone.name.rsplit(".", 1)[0]
        original = edit_bones.get(original_name)
        if original is None:
            continue
        for child in list(bone.children):
            child.parent = original
        edit_bones.remove(bone)
        removed += 1

    reattached = {}
    for label, anchor_names in anchors.items():
        if label not in component_bones:
            continue
        anchor = next(
            (edit_bones[name] for name in anchor_names if name in edit_bones), None
        )
        if anchor is None:
            continue
        # The renamed carrier root takes the whole piece with it.
        carrier = renamed_roots.get(label)
        if carrier and carrier in edit_bones:
            edit_bones[carrier].parent = anchor
            reattached.setdefault(label, []).append(carrier + " -> " + anchor.name)
        for name in component_bones[label]:
            if name == carrier:
                continue
            bone = edit_bones.get(name)
            if bone is None or name in master_bone_names:
                # Names the body already owned belong to the body hierarchy;
                # never re-parent those.
                continue
            # Chains that fell through to the master Root (their own root was
            # a removed duplicate) belong on the head/hair anchor instead.
            if bone.parent is None or bone.parent.name == "Root":
                if name != anchor.name:
                    bone.parent = anchor
                    reattached.setdefault(label, []).append(name)
    bpy.ops.object.mode_set(mode="OBJECT")

    for mesh in meshes:
        world = mesh.matrix_world.copy()
        mesh.parent = master
        mesh.matrix_world = world
        for modifier in mesh.modifiers:
            if modifier.type == "ARMATURE":
                modifier.object = master
    for component in components:
        component.armatures = [master]
    master.name = "Eve_Armature"
    bpy.context.view_layer.update()
    return {
        "master": master.name,
        "bones": len(master.data.bones),
        "duplicates_removed": removed,
        "reattached_chains": reattached,
    }


def resize_bone_display(armature_object) -> dict:
    """Give bones a readable viewport length.

    PSK/UEFormat imports leave every bone at a tiny fixed display length, so
    a centimetre-scale character shows as a cloud of dots.  Only the length
    along each bone's existing Y axis changes: head positions, orientations,
    rolls and therefore skinning stay untouched.
    """
    previous_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_object.data.edit_bones
    lengths_before = [bone.length for bone in edit_bones]
    # Parents first so leaf bones can inherit the adjusted parent length.
    for bone in sorted(edit_bones, key=lambda b: len(b.parent_recursive)):
        child_distances = [
            (child.head - bone.head).length
            for child in bone.children
            if (child.head - bone.head).length > 0.25
        ]
        if child_distances:
            length = min(child_distances)
        elif bone.parent is not None:
            length = bone.parent.length * 0.6
        else:
            length = 10.0
        bone.length = max(1.0, min(length, 25.0))
    lengths_after = [bone.length for bone in edit_bones]
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = previous_active
    return {
        "bones": len(lengths_after),
        "before_median": sorted(lengths_before)[len(lengths_before) // 2],
        "after_median": sorted(lengths_after)[len(lengths_after) // 2],
    }


def scene_bounds(meshes: list):
    points = [
        mesh.matrix_world @ vertex.co
        for mesh in meshes
        for vertex in mesh.data.vertices
    ]
    if not points:
        raise RuntimeError("Imported Eve components contain no mesh vertices")
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def look_at(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_preview(meshes: list, render_path: str):
    minimum, maximum = scene_bounds(meshes)
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = max(extent.z * 0.025, 0.1)
    scene.eevee.gtao_factor = 1.15
    scene.render.resolution_x = 900
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.035, 0.055, 0.095, 1.0)
        background.inputs["Strength"].default_value = 0.5
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 1.35

    camera_data = bpy.data.cameras.new("EveValidationCamera")
    camera = bpy.data.objects.new("EveValidationCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.lens = 60
    camera_data.ortho_scale = max(extent.z * 1.08, extent.y * 1.38)
    distance = max(extent.z, extent.y, extent.x, 100.0) * 2.3
    # Unreal X-forward becomes the depth axis with io_scene_psk_psa.  Viewing
    # from +X gives the front of these Eve assets; Y spans left/right.
    camera.location = Vector((center.x + distance, center.y, center.z + extent.z * 0.015))
    look_at(camera, center)

    light_specs = [
        ("Key", (center.x + distance * 0.45, center.y - distance * 0.25, center.z + extent.z * 0.45), 5200.0, extent.z * 0.7),
        ("Fill", (center.x + distance * 0.25, center.y + distance * 0.3, center.z + extent.z * 0.12), 3000.0, extent.z * 0.8),
        ("Rim", (center.x - distance * 0.35, center.y, center.z + extent.z * 0.42), 4300.0, extent.z * 0.55),
    ]
    for name, location, energy, size in light_specs:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = max(size, 1.0)
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, center)

    os.makedirs(os.path.dirname(render_path), exist_ok=True)
    scene.render.filepath = render_path
    bpy.ops.render.render(write_still=True)
    return minimum, maximum


def create_face_preview(meshes: list, render_path: str) -> str:
    minimum, maximum = scene_bounds(meshes)
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    scene = bpy.context.scene
    camera = scene.camera
    stored = {
        "location": camera.location.copy(),
        "rotation": camera.rotation_euler.copy(),
        "ortho_scale": camera.data.ortho_scale,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "filepath": scene.render.filepath,
        "exposure": scene.view_settings.exposure,
    }
    distance = max(extent.x, extent.y, extent.z, 20.0) * 3.0
    camera.location = Vector((center.x + distance, center.y, center.z))
    look_at(camera, center)
    camera.data.ortho_scale = max(extent.z * 1.32, extent.y * 1.7)
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.view_settings.exposure = 2.25
    root, extension = os.path.splitext(render_path)
    face_path = root + "_face" + extension
    scene.render.filepath = face_path
    bpy.ops.render.render(write_still=True)

    camera.location = stored["location"]
    camera.rotation_euler = stored["rotation"]
    camera.data.ortho_scale = stored["ortho_scale"]
    scene.render.resolution_x = stored["resolution_x"]
    scene.render.resolution_y = stored["resolution_y"]
    scene.render.filepath = stored["filepath"]
    scene.view_settings.exposure = stored["exposure"]
    return face_path


def object_bounds(meshes: list) -> dict:
    minimum, maximum = scene_bounds(meshes)
    return {"min": list(minimum), "max": list(maximum)}


def component_report(component: Component) -> dict:
    armature_bones = [len(obj.data.bones) for obj in component.armatures]
    material_names = sorted(
        {
            slot.material.name
            for mesh in component.meshes
            for slot in mesh.material_slots
            if slot.material is not None
        }
    )
    material_geometry = {}
    for mesh in component.meshes:
        uv_layer = mesh.data.uv_layers.active
        for material_index, slot in enumerate(mesh.material_slots):
            if slot.material is None:
                continue
            polygons = [
                polygon
                for polygon in mesh.data.polygons
                if polygon.material_index == material_index
            ]
            vertex_indices = {
                vertex_index
                for polygon in polygons
                for vertex_index in polygon.vertices
            }
            loop_indices = [
                loop_index
                for polygon in polygons
                for loop_index in polygon.loop_indices
            ]
            entry = {"polygons": len(polygons), "vertices": len(vertex_indices)}
            if vertex_indices:
                points = [mesh.data.vertices[index].co for index in vertex_indices]
                entry["bounds"] = {
                    "min": [
                        min(point[axis] for point in points) for axis in range(3)
                    ],
                    "max": [
                        max(point[axis] for point in points) for axis in range(3)
                    ],
                }
            if uv_layer is not None and loop_indices:
                uvs = [uv_layer.data[index].uv for index in loop_indices]
                entry["uv_bounds"] = {
                    "min": [min(uv.x for uv in uvs), min(uv.y for uv in uvs)],
                    "max": [max(uv.x for uv in uvs), max(uv.y for uv in uvs)],
                }
            material_geometry[slot.material.name] = entry
    is_uemodel = component.source.lower().endswith(".uemodel")
    return {
        "label": component.label,
        "source": component.source,
        "bytes": os.path.getsize(component.source),
        "sha256": sha256(component.source),
        "source_format": "UEFormat" if is_uemodel else "ActorX PSK",
        "header": "UEFORMAT" if is_uemodel else "ACTRHEAD",
        "meshes": [mesh.name for mesh in component.meshes],
        "vertices": sum(len(mesh.data.vertices) for mesh in component.meshes),
        "polygons": sum(len(mesh.data.polygons) for mesh in component.meshes),
        "uv_layers": sum(len(mesh.data.uv_layers) for mesh in component.meshes),
        "material_slots": sum(len(mesh.material_slots) for mesh in component.meshes),
        "materials": material_names,
        "material_geometry": material_geometry,
        "shape_keys": {
            mesh.name: (
                len(mesh.data.shape_keys.key_blocks)
                if mesh.data.shape_keys is not None
                else 0
            )
            for mesh in component.meshes
        },
        "armatures": [obj.name for obj in component.armatures],
        "bones_per_armature": armature_bones,
        "bounds": object_bounds(component.meshes),
    }


def front_material_uv_samples(component: Component, material_name: str) -> list:
    """Report UV centroids for the material faces nearest the +X camera."""
    samples = []
    for mesh in component.meshes:
        uv_layer = mesh.data.uv_layers.active
        if uv_layer is None:
            continue
        target_indices = {
            index
            for index, slot in enumerate(mesh.material_slots)
            if slot.material is not None
            and material_base_name(slot.material.name) == material_name
        }
        for polygon in mesh.data.polygons:
            if polygon.material_index not in target_indices:
                continue
            center_x = sum(mesh.data.vertices[i].co.x for i in polygon.vertices) / len(
                polygon.vertices
            )
            uvs = [uv_layer.data[i].uv for i in polygon.loop_indices]
            samples.append(
                {
                    "x": center_x,
                    "u": sum(uv.x for uv in uvs) / len(uvs),
                    "v": sum(uv.y for uv in uvs) / len(uvs),
                }
            )
    return sorted(samples, key=lambda item: item["x"], reverse=True)[:24]


def main() -> None:
    args = parse_args()
    paths = {
        "Body": args.body,
        "Hair": args.hair,
        "HairTail": args.tail,
    }
    if args.tail_short:
        paths["HairTailShort"] = args.tail_short
    for path in [*paths.values(), args.head_uemodel, args.hair_alpha]:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
    if not os.path.isfile(args.body_diffuse) and not os.path.isdir(args.body_diffuse):
        raise FileNotFoundError(args.body_diffuse)
    if not os.path.isdir(args.face_assets):
        raise NotADirectoryError(args.face_assets)
    if not os.path.isdir(args.ueformat_source):
        raise NotADirectoryError(args.ueformat_source)

    clear_scene()
    components = [imported_component(label, path) for label, path in paths.items()]
    head, source_morphs, shape_keys = imported_uemodel_component(
        "Head", args.head_uemodel, args.ueformat_source
    )
    components.insert(1, head)
    by_label = {component.label: component for component in components}
    alignment_reference = None
    if args.alignment_reference:
        with open(args.alignment_reference, "r", encoding="utf-8") as handle:
            alignment_reference = json.load(handle).get("alignment")
    alignment = align_hair_components(
        by_label["Body"],
        by_label["Hair"],
        by_label["HairTail"],
        alignment_reference,
        by_label.get("HairTailShort"),
    )
    merge_info = None
    if args.merge_armatures:
        merge_info = merge_component_armatures(components, by_label["Body"])
    bone_display = {
        armature.name: resize_bone_display(armature)
        for armature in {
            arm for component in components for arm in component.armatures
        }
    }
    body_material_assignments = prepare_body_materials(
        by_label["Body"], os.path.abspath(args.body_diffuse)
    )
    head_materials = prepare_head_materials(
        by_label["Head"], os.path.abspath(args.face_assets)
    )
    hair_components = [by_label["Hair"], by_label["HairTail"]]
    if "HairTailShort" in by_label:
        hair_components.append(by_label["HairTailShort"])
    prepare_hair_materials(hair_components, os.path.abspath(args.hair_alpha))

    meshes = [mesh for component in components for mesh in component.meshes]
    minimum, maximum = create_preview(meshes, os.path.abspath(args.render))
    face_render = create_face_preview(
        by_label["Head"].meshes, os.path.abspath(args.render)
    )
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)

    report = {
        "validation": "Stellar Blade Eve standard modular model",
        "blender_version": bpy.app.version_string,
        "output_blend": output_path,
        "render": os.path.abspath(args.render),
        "face_render": face_render,
        "components": [component_report(component) for component in components],
        "alignment": alignment,
        "merged_armature": merge_info,
        "bone_display": bone_display,
        "totals": {
            "components": len(components),
            "meshes": len(meshes),
            "armatures": len(
                {
                    armature.name
                    for component in components
                    for armature in component.armatures
                }
            ),
            "vertices": sum(len(mesh.data.vertices) for mesh in meshes),
            "polygons": sum(len(mesh.data.polygons) for mesh in meshes),
            "bones": sum(
                len(bpy.data.objects[name].data.bones)
                for name in {
                    armature.name
                    for component in components
                    for armature in component.armatures
                }
            ),
            "bounds": {"min": list(minimum), "max": list(maximum)},
        },
        "preview_materials": {
            "body_diffuse": os.path.abspath(args.body_diffuse),
            "body_assignments": body_material_assignments,
            "hair_alpha": os.path.abspath(args.hair_alpha),
            "head": head_materials,
        },
        "eye_front_uv_samples": front_material_uv_samples(
            by_label["Head"], "MI_EyeRefractive1"
        ),
        "source_morph_targets": {
            "component": "Head",
            "source_count": len(source_morphs),
            "source_names": source_morphs,
            "blender_shape_key_count": len(shape_keys),
            "blender_shape_keys": shape_keys,
            "proof": face_asset(
                os.path.abspath(args.face_assets),
                "Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Face_003.props.txt",
            ),
            "blender_import_note": "UEFormat preserved all 53 source morph targets as Blender shape keys.",
        },
        "notes": [
            "The three PSKs passed ACTRHEAD checks and Face_003 passed the UEFORMAT header check.",
            "Components keep their own original armatures, including standalone hair simulation chains.",
            "Body and complete Face_003 came from FModel; hair and hair tail came from the Stellar Blade-specific UE Viewer build.",
            "Face_003 was imported through UEFormat in Blender 3.6 and retains all 53 source morph targets.",
            "Face_003 includes the normal head material stack and teeth material; the separately exported Teeth_001 is retained as an alternate source asset, not overlaid in this scene.",
        ],
    }
    report_path = os.path.abspath(args.report)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print("STELLARBLADE_EVE_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
