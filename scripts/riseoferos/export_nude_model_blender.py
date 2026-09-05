"""Build materialized Rise of Eros nude models in portable formats.

This is the Blender-side worker for ``export_nude_models.ps1``.  It uses the
same importer and material operators as the interactive ROE add-on, validates
that no texture from another body family was selected, and exports Blend, FBX,
XPS, PMX, or GLB from the corrected six-slot scene.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import traceback

import bpy


RESULT_PREFIX = "ROE_NUDE_EXPORT="


def result(status, **details):
    payload = {"status": status, **details}
    # Keep the machine-readable line ASCII-only. Windows PowerShell 5.1 can
    # otherwise decode Blender's UTF-8 stdout using an OEM code page and even
    # consume the closing quote after a multibyte character, producing a
    # manifest that looks plausible but is not valid JSON.
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=True, sort_keys=True))


def load_addon(path):
    spec = importlib.util.spec_from_file_location(
        "roe_nude_batch_addon", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 ROE 插件: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module


def texture_family_mismatches(images, expected_family):
    """Reject silent fallback from e.g. a missing L face to the A face."""
    mismatches = []
    common_role = re.compile(
        r"^pc_([a-z])_(?:nk|ld)_(?:face|eye|eyes|eye_iris|eyebrow|hair)",
        re.IGNORECASE,
    )
    for image in images:
        filename = os.path.basename(bpy.path.abspath(
            image.filepath or image.name))
        match = common_role.match(filename)
        if match and match.group(1).lower() != expected_family:
            mismatches.append(filename)
    return sorted(set(mismatches))


def polygon_components(mesh):
    """Return connected polygon components without changing topology."""
    parents = list(range(len(mesh.vertices)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first, second):
        first = find(first)
        second = find(second)
        if first != second:
            parents[second] = first

    for polygon in mesh.polygons:
        vertices = polygon.vertices
        for vertex in vertices[1:]:
            union(vertices[0], vertex)

    components = {}
    for polygon in mesh.polygons:
        components.setdefault(find(polygon.vertices[0]), []).append(polygon)
    return list(components.values())


def component_face_weight_ratio(obj, polygons):
    """Measure whether a component belongs to the facial rig, not the torso."""
    face_tokens = (
        "head", "face", "chin", "cheek", "lip", "nose", "jaw",
        "tongue", "teeth", "mouth", "eyelid", "eyeball", "eyebrow",
    )
    group_names = {group.index: group.name.lower()
                   for group in obj.vertex_groups}
    vertices = {vertex for polygon in polygons for vertex in polygon.vertices}
    face_weight = 0.0
    total_weight = 0.0
    for vertex_index in vertices:
        for membership in obj.data.vertices[vertex_index].groups:
            total_weight += membership.weight
            name = group_names.get(membership.group, "")
            if any(token in name for token in face_tokens):
                face_weight += membership.weight
    return face_weight / total_weight if total_weight else 0.0


def split_combined_nude_body(module, texture_dir):
    """Restore the body atlas on ``*_nk_body`` combined body/head meshes.

    The interactive material operator was originally written around HD models,
    where head and body are separate objects.  Nude models store torso, face,
    eyes and mouth pieces in one ``*_nk_body`` mesh.  Its default face classifier
    therefore assigns every unrecognized torso component to the face slot.

    Keep the operator's proven eye/lash/brow classification, but add a body slot
    and send only components substantially controlled by facial bones to the
    face atlas.  All remaining default components use the original body atlas.
    """
    candidates = [obj for obj in bpy.context.scene.objects
                  if obj.type == "MESH"
                  and re.search(r"(?:^|_)nk_body(?:\.\d+)?$", obj.name,
                                re.IGNORECASE)]
    if not candidates:
        return None
    obj = max(candidates, key=lambda item: len(item.data.polygons))
    clean_name = re.sub(r"\.\d+$", "", obj.name)
    body_texture = module.find_tex(
        texture_dir, clean_name + "*Albedo*.png")
    if not body_texture and "_fm_nk_body" in clean_name.lower():
        body_texture = module.find_tex(
            texture_dir,
            re.sub(r"_fm_nk_body$", "_nk_body", clean_name,
                   flags=re.IGNORECASE) + "*Albedo*.png",
        )
    family_match = re.match(r"pc_([a-z])\d*_(?:fm_)?nk_body$",
                            clean_name, re.IGNORECASE)
    if not body_texture and family_match:
        body_texture = module.find_tex(
            texture_dir,
            "pc_%s_nk_body*Albedo*.png" % family_match.group(1).lower(),
        )
    if not body_texture:
        raise RuntimeError("裸模身体贴图缺失: %s" % obj.name)
    if len(obj.material_slots) < 5:
        raise RuntimeError(
            "裸模头部分类未生成预期的五个槽: %s (%d)" %
            (obj.name, len(obj.material_slots)))

    old_materials = [slot.material for slot in obj.material_slots]
    old_indices = [polygon.material_index for polygon in obj.data.polygons]
    component_roles = []
    for component in polygon_components(obj.data):
        default_polygons = [polygon for polygon in component
                            if old_indices[polygon.index] == 0]
        ratio = component_face_weight_ratio(obj, component)
        component_roles.append(
            (component, bool(default_polygons) and ratio >= 0.35,
             ratio, bool(default_polygons)))

    body_material = module.albedo_mat(
        "body", body_texture, desat=True,
        saturation=bpy.context.scene.roe.skin_saturation)
    obj.data.materials.clear()
    obj.data.materials.append(body_material)
    for material in old_materials:
        obj.data.materials.append(material)

    face_components = 0
    body_components = 0
    counts = {index: 0 for index in range(len(obj.data.materials))}
    for component, is_face, _ratio, has_default in component_roles:
        if has_default:
            if is_face:
                face_components += 1
            else:
                body_components += 1
        for polygon in component:
            old_index = old_indices[polygon.index]
            if old_index == 0:
                polygon.material_index = 1 if is_face else 0
            else:
                polygon.material_index = old_index + 1
            counts[polygon.material_index] = counts.get(
                polygon.material_index, 0) + 1
    obj.data.update()

    if not counts.get(0) or not counts.get(1) or not counts.get(2):
        raise RuntimeError(
            "裸模身体/脸部分区失败: %s counts=%r" % (obj.name, counts))
    # Mark the six-slot layout for ROE_OT_export_xps.  Sniffing slot names is
    # not stable: baking the portable eye replaces the eye slot's material.
    obj["roe_nude_slots"] = 1
    return {
        "object": obj.name,
        # The body slot was prepended, so the head layout's eye slot 1 is 2.
        "eye_slot": 2,
        "body_texture": os.path.basename(body_texture),
        "face_components": face_components,
        "body_components": body_components,
        "polygon_counts": counts,
    }


def make_auxiliary_meshes_transparent(module):
    """Do not leave A00's untextured liquid helper as opaque gray geometry."""
    fixed = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not re.match(
                r"^liquid(?:\.\d+)?$", obj.name, re.IGNORECASE):
            continue
        obj.data.materials.clear()
        obj.data.materials.append(module.transparent_mat("liquid"))
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        obj.data.update()
        fixed.append(obj.name)
    return fixed


def validate_materials(module, meshes, expected_family):
    missing_slots = []
    invalid_indices = []
    images = []
    for obj in meshes:
        if not obj.material_slots:
            missing_slots.append(obj.name + ":<no slots>")
            continue
        for index, slot in enumerate(obj.material_slots):
            if slot.material is None:
                missing_slots.append("%s:%d" % (obj.name, index))
                continue
            image = module.diffuse_image(slot.material)
            if image is not None:
                images.append(image)
        slot_count = len(obj.material_slots)
        if any(poly.material_index >= slot_count for poly in obj.data.polygons):
            invalid_indices.append(obj.name)

    wrong_family = texture_family_mismatches(images, expected_family)
    diagnostic = bpy.context.scene.roe.diagnostic_report
    missing_count = 0
    match = re.search(r"缺贴图\s*(\d+)", diagnostic)
    if match:
        missing_count = int(match.group(1))

    errors = []
    if missing_slots:
        errors.append("空材质槽: %s" % ", ".join(missing_slots))
    if invalid_indices:
        errors.append("面引用了越界材质槽: %s" % ", ".join(invalid_indices))
    if missing_count:
        errors.append("插件报告缺贴图 %d" % missing_count)
    if wrong_family:
        errors.append("错误体型贴图: %s" % ", ".join(wrong_family))

    return errors, sorted({
        os.path.basename(bpy.path.abspath(image.filepath or image.name))
        for image in images
    })


def materials_images(meshes):
    """Every image reachable from the materials actually assigned to the model.

    The FBX importer creates an image datablock per texture named in the file,
    resolved beside the FBX, and those stay in the scene even though the add-on
    rebuilds materials from the staged texture directory.  Packing all of
    ``bpy.data.images`` would embed unused duplicates, and hard-fails once the
    redundant per-object texture copies are pruned from the export tree.
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
    packed = []
    failed = []
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
    selected = []
    for obj in list(meshes) + list(armatures):
        try:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.hide_render = False
            obj.select_set(True)
            selected.append(obj)
        except (ReferenceError, RuntimeError):
            pass
    if armatures:
        bpy.context.view_layer.objects.active = armatures[0]
    elif meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    return selected


def check_output(path, fmt):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("%s 未生成输出文件: %s" % (fmt.upper(), path))
    return path


def export_xps(module, path, meshes, armatures):
    def operator_ready():
        try:
            bpy.ops.xps_tools.export_model.get_rna_type()
            return True
        except Exception:
            return False

    # An installed exporter may register the operator under any module name;
    # only walk the known addon names when it is not available yet.
    if not operator_ready():
        for addon_name in ("XNALaraMesh-master", "XNALaraMesh", "b2xps_addon"):
            try:
                bpy.ops.preferences.addon_enable(module=addon_name)
            except Exception:
                continue
            if operator_ready():
                break
    if not operator_ready():
        raise RuntimeError("未找到可用的 XNALaraMesh 导出插件")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)
    select_character_objects(meshes, armatures)
    bpy.context.scene.roe.xps_out = path
    exported = bpy.ops.roe.export_xps()
    if exported != {"FINISHED"}:
        raise RuntimeError("XPS 导出失败: %r" % exported)
    return check_output(path, "xps")


def prepare_portable_eye(module, nude_split, output_root):
    """Bake the procedural sclera/iris graph for non-Blender exporters.

    Returns a status dict recorded in the manifest, so a model whose eye was
    NOT baked (a00 has no combined body/eye mesh) stays auditable instead of
    silently exporting the unevaluated procedural node graph.
    """
    if not nude_split:
        return {"status": "skipped",
                "reason": "no combined nude body mesh; nothing to bake"}
    obj = bpy.data.objects.get(nude_split["object"])
    eye_slot = nude_split.get("eye_slot", 2)
    if obj is None or len(obj.material_slots) <= eye_slot:
        raise RuntimeError(
            "裸模眼球槽丢失，无法为便携格式烘焙眼球: %r" % nude_split)
    eye_material = obj.material_slots[eye_slot].material
    iris_image = module.diffuse_image(eye_material) if eye_material else None
    iris_path = (bpy.path.abspath(iris_image.filepath)
                 if iris_image is not None else "")
    if not iris_path or not os.path.isfile(iris_path):
        raise RuntimeError("便携格式缺少可烘焙的虹膜贴图: %s" % obj.name)
    texture_dir = os.path.join(output_root, "textures")
    os.makedirs(texture_dir, exist_ok=True)
    baked_path = os.path.join(
        texture_dir,
        re.sub(r"[^A-Za-z0-9_.-]+", "_", obj.name) + "_eye_baked.png",
    )
    module.bake_eye_texture(
        obj, iris_path, baked_path, eye_slot=eye_slot)
    obj.data.materials[eye_slot] = module.albedo_mat(
        "eye_portable", baked_path, desat=False)
    obj.data.update()
    return {"status": "baked", "path": baked_path}


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
    elif fmt == "pmx":
        try:
            bpy.ops.preferences.addon_enable(module="mmd_tools")
        except Exception:
            pass
        converted = bpy.ops.mmd_tools.convert_to_mmd_model()
        if converted != {"FINISHED"}:
            raise RuntimeError("无法把裸模骨架转换为 MMD 模型: %r" % converted)
        select_character_objects(meshes, armatures)
        bpy.ops.mmd_tools.export_pmx(
            filepath=path,
            scale=12.5,  # PMX = Blender * scale (1.7 m -> ~21 units)
            copy_textures=True,
        )
    else:
        raise RuntimeError("未知便携格式: %s" % fmt)
    return check_output(path, fmt)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) not in {5, 6}:
        raise RuntimeError(
            "用法: <fbx> <贴图临时目录> <输出.blend> <roe_xps_addon.py> "
            "<validate|export> [blend,fbx,xps,pmx,glb]")

    fbx_path, texture_dir, output_path, addon_path, mode = argv[:5]
    formats = ({item.strip().lower() for item in argv[5].split(",")
                if item.strip()} if len(argv) == 6 else {"blend"})
    valid_formats = {"blend", "fbx", "xps", "pmx", "glb"}
    unknown_formats = formats - valid_formats
    if unknown_formats:
        raise RuntimeError("未知格式: %s" % ", ".join(sorted(unknown_formats)))
    if mode == "export" and not formats:
        raise RuntimeError("导出模式至少需要一种格式")
    fbx_path = os.path.abspath(fbx_path)
    texture_dir = os.path.abspath(texture_dir)
    output_path = os.path.abspath(output_path)
    addon_path = os.path.abspath(addon_path)
    if mode not in {"validate", "export"}:
        raise RuntimeError("未知模式: %s" % mode)
    for label, path, predicate in (
        ("FBX", fbx_path, os.path.isfile),
        ("贴图目录", texture_dir, os.path.isdir),
        ("ROE 插件", addon_path, os.path.isfile),
    ):
        if not predicate(path):
            raise RuntimeError("%s不存在: %s" % (label, path))

    basename = Path(fbx_path).stem.lower()
    family_match = re.match(r"pc_([a-z])", basename)
    if not family_match:
        raise RuntimeError("无法从 FBX 名称识别体型字母: %s" % basename)
    expected_family = family_match.group(1)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    module = load_addon(addon_path)
    props = bpy.context.scene.roe
    props.workflow_mode = "ROE"
    props.apply_scope = "LATEST"
    props.replace_previous = False
    props.fbx_path = fbx_path
    props.tex_dir = texture_dir

    imported = bpy.ops.roe.import_fbx()
    if imported != {"FINISHED"}:
        raise RuntimeError("FBX 导入失败: %r" % imported)
    materialized = bpy.ops.roe.apply_materials(repair_scope="ALL")
    if materialized != {"FINISHED"}:
        raise RuntimeError("材质准备失败: %r" % materialized)

    nude_split = split_combined_nude_body(module, texture_dir)
    transparent_helpers = make_auxiliary_meshes_transparent(module)

    meshes = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
    armatures = module.related_armatures(meshes)
    if not meshes:
        raise RuntimeError("导入后没有网格")
    if not armatures:
        raise RuntimeError("导入后没有关联骨架")

    errors, textures = validate_materials(module, meshes, expected_family)
    if errors:
        raise RuntimeError("；".join(errors))

    packed = []
    outputs = {}
    portable_eye = None
    if mode == "export":
        output_root = os.path.dirname(output_path)
        output_stem = Path(output_path).stem
        if "blend" in formats:
            packed, pack_failures = pack_images(meshes)
            if pack_failures:
                raise RuntimeError("贴图打包失败: %s" % "; ".join(pack_failures))
            os.makedirs(output_root, exist_ok=True)
            bpy.context.preferences.filepaths.save_version = 0
            bpy.ops.wm.save_as_mainfile(filepath=output_path, check_existing=False)
            outputs["blend"] = check_output(output_path, "blend")

        if "xps" in formats:
            # Export XPS before preparing portable formats: the XPS operator
            # bakes its own eye PNG from the procedural graph, which
            # prepare_portable_eye() replaces with a flat baked texture.
            outputs["xps"] = export_xps(
                module, os.path.join(output_root, "xps", output_stem + ".mesh"),
                meshes, armatures)

        portable_formats = formats & {"fbx", "glb", "pmx"}
        if portable_formats:
            portable_eye = prepare_portable_eye(
                module, nude_split, output_root)
        # mmd_tools' convert_to_mmd_model() rebuilds the rig in place, so any
        # format exported after it would see the MMD scene.  Keep pmx last.
        for fmt in ("fbx", "glb", "pmx"):
            if fmt not in portable_formats:
                continue
            extension = {"fbx": ".fbx", "glb": ".glb", "pmx": ".pmx"}[fmt]
            outputs[fmt] = export_portable(
                fmt, os.path.join(output_root, fmt, output_stem + extension),
                meshes, armatures)

    primary_output = (outputs.get("blend") or
                      next(iter(outputs.values()), ""))

    result(
        "PASS",
        source=fbx_path,
        output=primary_output,
        outputs=outputs,
        formats=sorted(formats) if mode == "export" else [],
        meshes=len(meshes),
        armatures=len(armatures),
        materials=sum(len(obj.material_slots) for obj in meshes),
        textures=textures,
        packed_images=len(packed),
        diagnostic=bpy.context.scene.roe.diagnostic_report,
        nude_split=nude_split,
        portable_eye=portable_eye,
        transparent_helpers=transparent_helpers,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Blender often exits 0 after Python errors.
        result("FAIL", error=str(exc), traceback=traceback.format_exc())
        traceback.print_exc()
