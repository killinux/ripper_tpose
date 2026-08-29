"""Build materialized FF7 Rebirth player models in portable formats.

This is the Blender-side worker for ``export_ff7rb_models.ps1``.  It reuses the
module-level helpers of ``ff7rebirth_tools.py`` (model import, PSK shading
repair, FModel material-JSON driven texture matching), validates the imported
character, and exports Blend, FBX, or GLB.

The saved ``.blend`` keeps the full generated node graphs (layered player eye,
DirectX->OpenGL normal reconstruction, ORM split).  FBX/glTF exporters cannot
serialize those graphs, so portable exports first bake the layered eye into a
single PNG and pre-flip the normal maps' green channel into ``*_gl.png``
copies wired directly to the Normal Map node.
"""

import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

import bpy


RESULT_PREFIX = "FF7RB_EXPORT="
VALID_FORMATS = {"blend", "fbx", "glb"}


def result(status, **details):
    payload = {"status": status, **details}
    # Keep the machine-readable line ASCII-only: Windows PowerShell 5.1 can
    # otherwise decode Blender's UTF-8 stdout with an OEM code page and corrupt
    # the JSON payload (see the ROE nude worker for the original incident).
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=True, sort_keys=True))


def load_tools(path):
    spec = importlib.util.spec_from_file_location(
        "ff7rb_batch_tools", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 FF7RB 插件模块: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Module-level helpers only; the operator/panel classes stay unregistered.
    return module


def ensure_psk_importer(module):
    def importer_ready():
        return (module.operator_exists("psk", "import_file")
                or module.operator_exists("import_scene", "psk"))

    if importer_ready():
        return
    for addon_name in ("io_scene_psk_psa", "io_import_scene_psk"):
        try:
            bpy.ops.preferences.addon_enable(module=addon_name)
        except Exception:
            continue
        if importer_ready():
            return
    raise RuntimeError(
        "PSK/PSKX 需要 io_scene_psk_psa；Blender 3.6 请安装并启用兼容版 5.0.6")


def image_pixels(path):
    import numpy as np

    image = bpy.data.images.load(path, check_existing=True)
    width, height = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32)
    return pixels.reshape(height, width, 4)


def resample_nearest(array, width, height):
    import numpy as np

    src_height, src_width = array.shape[:2]
    rows = np.minimum(
        (np.arange(height) * src_height // height), src_height - 1)
    cols = np.minimum(
        (np.arange(width) * src_width // width), src_width - 1)
    return array[rows][:, cols]


def blend_eye_arrays(sclera, iris, inner=0.18, outer=0.22):
    """Reproduce the FF7RB_EyeColorMix graph: sclera outside, iris inside.

    The generated ColorRamp runs white->black between ``inner`` and ``outer``
    UV distance from (0.5, 0.5) with EASE interpolation, approximated here by
    smoothstep.  Fac=1 selects the iris (mix input 2).
    """
    import numpy as np

    height = max(sclera.shape[0], iris.shape[0])
    width = max(sclera.shape[1], iris.shape[1])
    sclera = resample_nearest(sclera, width, height)
    iris = resample_nearest(iris, width, height)
    ys, xs = np.mgrid[0:height, 0:width]
    u = (xs + 0.5) / width
    v = (ys + 0.5) / height
    distance = np.sqrt((u - 0.5) ** 2 + (v - 0.5) ** 2)
    t = np.clip((outer - distance) / max(outer - inner, 1e-6), 0.0, 1.0)
    factor = (t * t * (3 - 2 * t))[..., None]
    out = sclera * (1 - factor) + iris * factor
    out[..., 3] = 1.0
    return out


def save_pixels(array, path):
    name = os.path.basename(path)
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    height, width = array.shape[:2]
    image = bpy.data.images.new(name, width, height)
    image.pixels = array.ravel().tolist()
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return image


def unique_materials(meshes):
    materials = []
    seen = set()
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material and material.as_pointer() not in seen:
                seen.add(material.as_pointer())
                materials.append(material)
    return materials


def find_generated(material, suffix):
    if not material.use_nodes or not material.node_tree:
        return None
    return material.node_tree.nodes.get("FF7RB_" + suffix)


def bake_layered_eyes(module, meshes, texture_dir):
    """Collapse the sclera+iris mix into one PNG wired to Base Color."""
    baked = []
    for material in unique_materials(meshes):
        mix = find_generated(material, "EyeColorMix")
        if mix is None:
            continue
        links = material.node_tree.links
        sclera_node = (mix.inputs[1].links[0].from_node
                       if mix.inputs[1].links else None)
        iris_node = (mix.inputs[2].links[0].from_node
                     if mix.inputs[2].links else None)
        if not (sclera_node and sclera_node.image
                and iris_node and iris_node.image):
            raise RuntimeError("眼球混合节点缺少贴图: %s" % material.name)
        inner, outer = 0.18, 0.22
        mask = find_generated(material, "EyeIrisMask")
        if mask is not None and len(mask.color_ramp.elements) >= 2:
            inner = mask.color_ramp.elements[0].position
            outer = mask.color_ramp.elements[1].position
        sclera = image_pixels(bpy.path.abspath(sclera_node.image.filepath))
        iris = image_pixels(bpy.path.abspath(iris_node.image.filepath))
        os.makedirs(texture_dir, exist_ok=True)
        baked_path = os.path.join(
            texture_dir, "%s_eye_baked.png" % material.name.replace(" ", "_"))
        baked_image = save_pixels(
            blend_eye_arrays(sclera, iris, inner, outer), baked_path)

        principled = next((node for node in material.node_tree.nodes
                           if node.type == "BSDF_PRINCIPLED"), None)
        if principled is None:
            raise RuntimeError("眼球材质缺少 Principled 节点: %s" % material.name)
        base_socket = principled.inputs["Base Color"]
        for link in list(base_socket.links):
            links.remove(link)
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = "FF7RB_PortableEye"
        node.label = os.path.basename(baked_path)
        node.image = baked_image
        node.location = (-600, 240)
        links.new(node.outputs["Color"], base_socket)
        baked.append(material.name)
    return baked


def flip_directx_normals(meshes, texture_dir):
    """Replace the Separate/Invert/Combine chain with a pre-flipped PNG."""
    import numpy as np

    flipped = []
    converted = {}
    for material in unique_materials(meshes):
        normal_map = find_generated(material, "NormalMap")
        separate = find_generated(material, "SeparateNormal")
        if normal_map is None or separate is None:
            continue
        source_links = separate.inputs["Image"].links
        source_node = source_links[0].from_node if source_links else None
        if not (source_node and getattr(source_node, "image", None)):
            continue
        source_path = bpy.path.abspath(source_node.image.filepath)
        gl_path = converted.get(source_path)
        if gl_path is None:
            pixels = image_pixels(source_path)
            pixels = pixels.copy()
            pixels[..., 1] = 1.0 - pixels[..., 1]
            os.makedirs(texture_dir, exist_ok=True)
            gl_path = os.path.join(
                texture_dir,
                Path(source_path).stem + "_gl.png")
            save_pixels(pixels, gl_path)
            converted[source_path] = gl_path

        links = material.node_tree.links
        color_socket = normal_map.inputs["Color"]
        for link in list(color_socket.links):
            links.remove(link)
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = "FF7RB_PortableNormal"
        node.label = os.path.basename(gl_path)
        node.image = bpy.data.images.load(gl_path, check_existing=True)
        node.image.colorspace_settings.name = "Non-Color"
        node.location = (-600, -120)
        links.new(node.outputs["Color"], color_socket)
        flipped.append(material.name)
    return flipped, sorted(converted.values())


def pack_images():
    packed = []
    failed = []
    for image in bpy.data.images:
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


def check_output(path, fmt):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("%s 未生成输出文件: %s" % (fmt.upper(), path))
    return path


def export_portable(fmt, path, meshes, armatures):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)
    select_character_objects(meshes, armatures)
    if fmt == "fbx":
        bpy.ops.export_scene.fbx(
            filepath=path,
            use_selection=True,
            object_types={"ARMATURE", "MESH"},
            apply_scale_options="FBX_SCALE_ALL",
            add_leaf_bones=False,
            bake_anim=False,
            use_mesh_modifiers=True,
            mesh_smooth_type="FACE",
            path_mode="COPY",
            embed_textures=True,
        )
    elif fmt == "glb":
        bpy.ops.export_scene.gltf(
            filepath=path,
            export_format="GLB",
            use_selection=True,
            export_skins=True,
            export_morph=True,
            export_animations=False,
        )
    else:
        raise RuntimeError("未知便携格式: %s" % fmt)
    return check_output(path, fmt)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) not in {5, 6}:
        raise RuntimeError(
            "用法: <model.psk|pskx> <变体目录> <输出.blend> "
            "<ff7rebirth_tools.py> <validate|export> [blend,fbx,glb]")

    model_path, variant_root, output_path, tools_path, mode = argv[:5]
    formats = ({item.strip().lower() for item in argv[5].split(",")
                if item.strip()} if len(argv) == 6 else {"blend"})
    unknown_formats = formats - VALID_FORMATS
    if unknown_formats:
        raise RuntimeError(
            "未知格式: %s（支持 %s；XPS/PMX 在 FF7RB 管线尚未验证）" % (
                ", ".join(sorted(unknown_formats)),
                ", ".join(sorted(VALID_FORMATS))))
    if mode not in {"validate", "export"}:
        raise RuntimeError("未知模式: %s" % mode)
    model_path = os.path.abspath(model_path)
    variant_root = os.path.abspath(variant_root)
    output_path = os.path.abspath(output_path)
    tools_path = os.path.abspath(tools_path)
    for label, path, predicate in (
        ("模型", model_path, os.path.isfile),
        ("变体目录", variant_root, os.path.isdir),
        ("FF7RB 插件", tools_path, os.path.isfile),
    ):
        if not predicate(path):
            raise RuntimeError("%s不存在: %s" % (label, path))

    # read_homefile keeps the user's enabled add-ons (the PSK importer is an
    # installed add-on, unlike ROE's bundled importers), while still starting
    # from an empty scene.
    bpy.ops.wm.read_homefile(use_empty=True)
    module = load_tools(tools_path)
    ensure_psk_importer(module)

    if os.path.splitext(model_path)[1].lower() in {".psk", ".pskx"} \
            and not module.actorx_file_valid(model_path):
        raise RuntimeError("不是有效的 ActorX 文件（缺少 ACTRHEAD）: %s" % model_path)

    imported = module.import_model(model_path)
    if imported != {"FINISHED"}:
        raise RuntimeError("模型导入失败: %r" % imported)

    objects = list(bpy.context.scene.objects)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if not meshes:
        raise RuntimeError("导入后没有网格")
    if not armatures:
        raise RuntimeError("导入后没有骨架")
    unbound = [mesh.name for mesh in meshes
               if not any(modifier.type == "ARMATURE"
                          and modifier.object in armatures
                          for modifier in mesh.modifiers)]
    if unbound:
        raise RuntimeError("网格未绑定到导入骨架: %s" % ", ".join(unbound))

    repaired = module.repair_mesh_shading(meshes)
    # The material JSONs reference exact Unreal package paths that often live
    # OUTSIDE this variant's folder: PC0002_11 reuses PC0002_00's skin/hair
    # atlases, and the eye/mouth share Character\Common.  Build the semantic
    # lookup index over the whole exported Character tree (safe: references
    # are matched by full package path, scored by texture_reference_score),
    # while the name-guessing fallback keeps searching only this variant +
    # Common so it can never borrow another outfit's textures.
    character_root = os.path.normpath(
        os.path.join(variant_root, "..", ".."))
    common_root = os.path.join(character_root, "Common")
    narrow_roots = module.unique_existing_roots(
        variant_root, common_root if os.path.isdir(common_root) else "")
    textures = module.discover_files_many(narrow_roots, module.IMAGE_EXTENSIONS)
    material_records = module.load_material_records(narrow_roots)
    index_roots = (module.unique_existing_roots(character_root)
                   or narrow_roots)
    indexed_textures = module.discover_files_many(
        index_roots, module.IMAGE_EXTENSIONS)
    texture_index = module.build_texture_index(indexed_textures)

    prepare_targets = unique_materials(meshes)
    prepared = sum(1 for material in prepare_targets
                   if module.prepare_material(
                       material, textures,
                       material_records=material_records,
                       texture_index=texture_index))
    total_materials = len(prepare_targets)
    texture_count = len(textures)

    empty_slots = ["%s:%d" % (obj.name, index)
                   for obj in meshes
                   for index, slot in enumerate(obj.material_slots)
                   if slot.material is None]
    if empty_slots:
        raise RuntimeError("空材质槽: %s" % ", ".join(empty_slots))
    if not total_materials:
        raise RuntimeError("导入后没有任何材质")

    missing_base = sorted(
        material.name for material in unique_materials(meshes)
        if not module.material_has_base_texture(material))
    if len(missing_base) == total_materials:
        raise RuntimeError(
            "没有任何材质匹配到 Base Color 贴图（贴图目录: %s）" % variant_root)
    layered_eyes = sorted(
        material.name for material in unique_materials(meshes)
        if find_generated(material, "EyeColorMix") is not None)

    outputs = {}
    packed = []
    simplified = None
    if mode == "export":
        output_root = os.path.dirname(output_path)
        output_stem = Path(output_path).stem
        if "blend" in formats:
            # Save the blend FIRST so it keeps the full node graphs; the
            # portable simplification below rewires eye and normal inputs.
            packed, pack_failures = pack_images()
            if pack_failures:
                raise RuntimeError("贴图打包失败: %s" % "; ".join(pack_failures))
            os.makedirs(output_root, exist_ok=True)
            bpy.context.preferences.filepaths.save_version = 0
            bpy.ops.wm.save_as_mainfile(
                filepath=output_path, check_existing=False)
            outputs["blend"] = check_output(output_path, "blend")

        portable_formats = formats & {"fbx", "glb"}
        if portable_formats:
            texture_dir = os.path.join(output_root, "textures")
            baked_eyes = bake_layered_eyes(module, meshes, texture_dir)
            flipped, gl_textures = flip_directx_normals(meshes, texture_dir)
            simplified = {
                "baked_eyes": baked_eyes,
                "flipped_normal_materials": flipped,
                "gl_normal_textures": [os.path.basename(p)
                                       for p in gl_textures],
            }
        for fmt in sorted(portable_formats):
            extension = {"fbx": ".fbx", "glb": ".glb"}[fmt]
            outputs[fmt] = export_portable(
                fmt, os.path.join(output_root, fmt, output_stem + extension),
                meshes, armatures)

    result(
        "PASS",
        source=model_path,
        output=(outputs.get("blend") or next(iter(outputs.values()), "")),
        outputs=outputs,
        formats=sorted(formats) if mode == "export" else [],
        meshes=len(meshes),
        armatures=len(armatures),
        bones=len(armatures[0].data.bones),
        vertices=sum(len(mesh.data.vertices) for mesh in meshes),
        polygons=sum(len(mesh.data.polygons) for mesh in meshes),
        materials=total_materials,
        prepared_materials=prepared,
        textures_found=texture_count,
        indexed_textures=len(indexed_textures),
        missing_base=missing_base,
        layered_eyes=layered_eyes,
        repaired_shading=repaired,
        packed_images=len(packed),
        simplified=simplified,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Blender often exits 0 after Python errors.
        result("FAIL", error=str(exc), traceback=traceback.format_exc())
        traceback.print_exc()
