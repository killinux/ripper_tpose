"""ROE PMX Tools - the batch PMX export as four buttons, so a Rise of Eros
character can be converted by hand in Blender and inspected between stages.

Every button calls the same functions the batch worker
(scripts/riseoferos/export_character_model_blender.py) runs headless, in the
same order, so a manual export and a batch export of the same FBX are the same
file.  UI: 3D viewport sidebar > ROE tab > "PMX 导出（MMD）", below the ROE XPS
Tools panel whose FBX / texture fields it shares.
"""
bl_info = {
    "name": "ROE PMX Tools",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > ROE > PMX 导出（MMD）",
    "description": "Rise of Eros character -> MMD-ready PMX in four inspectable stages "
                   "(materials, rig prep, MMD conversion + physics + expressions, export)",
    "category": "Import-Export",
}

import importlib
import json
import os
import sys
import traceback

import bpy

# realpath resolves the junction the add-on is installed through, so the batch
# worker is found next to the repo copy even when Blender loads us from
# %APPDATA%\...\addons\roe_pmx_tools
HERE = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
WORKER_DIRS = (os.path.normpath(os.path.join(HERE, "..", "..", "riseoferos")),
               r"E:\code\othercode\ripper_tpose\scripts\riseoferos")

_state = {}       # what the stages hand to each other (see the worker's export_pmx)


def worker(reload=False):
    """The batch worker module, imported lazily (it pulls in numpy).

    ``reload`` re-reads the file: stage 1 asks for it so an edit to the worker
    lands on the next run without restarting Blender (junction install)."""
    for path in WORKER_DIRS:
        if os.path.isfile(os.path.join(path, "export_character_model_blender.py")):
            if path not in sys.path:
                sys.path.insert(0, path)
            module = importlib.import_module("export_character_model_blender")
            if reload:
                module = importlib.reload(module)
            return module
    raise RuntimeError("export_character_model_blender.py not found (looked in %s)" % "; ".join(WORKER_DIRS))


def roe_module():
    """The ROE XPS Tools add-on (importer + material pass), which must be enabled."""
    module = sys.modules.get("roe_xps_addon")
    if module is None or not hasattr(bpy.ops, "roe") or not hasattr(bpy.ops.roe, "import_fbx"):
        raise RuntimeError("enable the ROE XPS Tools add-on first (roe_xps_addon.py)")
    return module


def scene_model(module):
    meshes = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("no character mesh in the scene - run stage 1 first")
    armatures = module.related_armatures(meshes)
    if not armatures:
        raise RuntimeError("the meshes have no armature")
    return meshes, armatures


class ROEPMX_Settings(bpy.types.PropertyGroup):
    pmx_out: bpy.props.StringProperty(
        name="PMX 输出", subtype="FILE_PATH",
        description="留空: D:\\roe_exports\\pmx_manual\\<模型名>\\<模型名>.pmx（不要放进会被重新提取清空的角色目录）")
    stage: bpy.props.IntProperty(default=0)
    report: bpy.props.StringProperty()


def _count(value):
    """The worker reports some stages as a list and some as a count."""
    try:
        return len(value)
    except TypeError:
        return int(value or 0)


def _log(settings, *lines):
    text = "\n".join(str(line) for line in lines)
    settings.report = text
    for line in text.split("\n"):
        print("[roe pmx] " + line)


def _fail(operator, settings, exc):
    traceback.print_exc()
    _log(settings, "失败: %s" % exc)
    operator.report({"ERROR"}, str(exc))
    return {"CANCELLED"}


# ---------------------------------------------------------------------------
class ROEPMX_OT_materials(bpy.types.Operator):
    """Stage 1: the XPS add-on's import + material pass, plus the batch's
    leftover-texture recovery and fused-head eyeball fix."""
    bl_idname = "roe_pmx.materials"
    bl_label = "① 导入 FBX 并挂材质"
    bl_description = "用 ROE XPS Tools 的 FBX / 贴图目录导入并准备材质（等于它的第 1、2 步，再补批处理的漏网贴图）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.roe_pmx
        try:
            module = roe_module()
            work = worker(reload=True)
            props = context.scene.roe
            if not props.fbx_path or not os.path.isfile(bpy.path.abspath(props.fbx_path)):
                raise RuntimeError("先在上面 ROE XPS Tools 面板里填 FBX 路径")
            if not props.tex_dir or not os.path.isdir(bpy.path.abspath(props.tex_dir)):
                raise RuntimeError("先在上面 ROE XPS Tools 面板里填贴图目录")
            props.workflow_mode = "ROE"
            props.apply_scope = "LATEST"
            props.replace_previous = False
            if bpy.ops.roe.import_fbx() != {"FINISHED"}:
                raise RuntimeError("FBX import failed")
            meshes = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
            if not meshes:
                raise RuntimeError("this FBX holds no geometry (rig-only prefab)")
            if bpy.ops.roe.apply_materials(repair_scope="ALL") != {"FINISHED"}:
                raise RuntimeError("material pass failed")
            meshes, armatures = scene_model(module)
            # the batch's extras: textures the material pass could not place,
            # and a00-style heads fused into the body with bare eyeballs
            texture_dir = bpy.path.abspath(props.tex_dir)
            stem = os.path.splitext(os.path.basename(bpy.path.abspath(props.fbx_path)))[0]
            character_id = stem.lower()[3:6] if stem.lower().startswith("pc_") else ""
            index = work.build_albedo_index(texture_dir)
            recovered = []
            for obj in meshes:
                for slot_index, slot in enumerate(obj.material_slots):
                    material = slot.material
                    if material is not None and (module.diffuse_image(material) is not None
                                                 or module.material_is_transparent_only(material)):
                        continue
                    path = work.resolve_leftover_texture(index, obj.name, character_id)
                    if path:
                        slot.material = module.albedo_mat("%s_%02d_recovered" % (obj.name, slot_index), path)
                        recovered.append("%s[%d] <- %s" % (obj.name, slot_index, os.path.basename(path)))
            head = module.find_head(meshes)
            fused = [] if head is not None else work.attach_fused_head_eyeballs(
                module, meshes, texture_dir, character_id[:1])
            untextured = sum(1 for obj in meshes for slot in obj.material_slots
                             if slot.material is None or (module.diffuse_image(slot.material) is None
                                                          and not module.material_is_transparent_only(slot.material)))
            _state.clear()
            _state.update(module=module, work=work, meshes=meshes, armatures=armatures, stem=stem,
                          head=head, texture_dir=texture_dir)
            settings.stage = 1
            _log(settings, "① %d 个网格, %d 个骨架, 头部%s" % (len(meshes), len(armatures), "已分槽" if head else "未识别"),
                 "   补回贴图 %d, 融合头眼球 %d, 仍无贴图的槽 %d" % (len(recovered), len(fused), untextured),
                 "   下一步: ② 骨架预处理（可先在视口检查材质）")
        except Exception as exc:
            return _fail(self, settings, exc)
        return {"FINISHED"}


class ROEPMX_OT_prepare(bpy.types.Operator):
    """Stage 2: Biped slot resolution, rig bake, limb-helper re-parenting,
    shoulder relax, 37-degree A-pose, skin snapshot."""
    bl_idname = "roe_pmx.prepare"
    bl_label = "② 骨架预处理"
    bl_description = ("认 Biped 骨位、烘正骨架、把挂错父级的肢体辅助骨按比例交还关节、"
                      "松肩膀权重、手臂放到 37° A-pose")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.roe_pmx
        try:
            if "meshes" not in _state:
                module = roe_module()
                meshes, armatures = scene_model(module)
                _state.update(module=module, work=worker(), meshes=meshes, armatures=armatures,
                              stem=armatures[0].name, head=module.find_head(meshes), texture_dir="")
            work, meshes, arm = _state["work"], _state["meshes"], _state["armatures"][0]
            slots, missing_optional = work.resolve_roe_slots(arm)
            missing_required = [role for role in work.ROE_MMD_REQUIRED_SLOTS if not slots[role]]
            if missing_required:
                raise RuntimeError("rig lacks joints the MMD conversion needs: %s" % ", ".join(missing_required))
            before = work.edge_lengths(meshes)
            work.bake_rig_transforms(arm, meshes)
            helper_plans, helper_report = work.plan_joint_helper_moves(arm, meshes, slots)
            helpers = work.apply_joint_helper_moves(arm, helper_plans)
            relaxed = work.relax_shoulder_weights(arm, slots)
            apose = work.apose_arms(arm, meshes, slots)
            skin_before = work.snapshot_skin(arm, meshes)
            _state.update(slots=slots, missing_optional=missing_optional, before=before,
                          helper_plans=helper_plans, helpers=helpers, relaxed=relaxed, apose=apose,
                          skin_before=skin_before)
            settings.stage = 2
            _log(settings, "② Biped 前缀 %s, 可选骨位缺 %d 个" % (slots["lower_body_bone"].split(" ")[0], len(missing_optional)),
                 "   辅助骨重新挂父级 %d 根, 肩膀松权重 %d 组, 手臂 %.1f°/%.1f°" % (
                     _count(helpers), _count(relaxed), apose[0], apose[1]),
                 "   下一步: ③ 转 MMD（现在可在视口检查 A-pose 和肢体）")
        except Exception as exc:
            return _fail(self, settings, exc)
        return {"FINISHED"}


class ROEPMX_OT_convert(bpy.types.Operator):
    """Stage 3: Convert_to_MMD5 one-click conversion + helper grants + stray
    weight guard + 両目 + expressions + body colliders + cloth physics."""
    bl_idname = "roe_pmx.convert"
    bl_label = "③ 转 MMD 骨架 + 物理 + 表情"
    bl_description = ("Convert_to_MMD5 一键转换成 MMD 标准骨，辅助骨付与、両目、"
                      "mmd_face_morphs 表情、身体碰撞胶囊、mmd_cloth_physics 布料")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.roe_pmx
        try:
            if "slots" not in _state:
                raise RuntimeError("先跑 ② 骨架预处理")
            work = _state["work"]
            work.enable_addon("mmd_tools")
            work.enable_addon("Convert_to_MMD5")
            if not hasattr(bpy.ops.object, "one_click_convert"):
                raise RuntimeError("Convert_to_MMD5 did not register one_click_convert")
            meshes, arm = _state["meshes"], _state["armatures"][0]
            root, stats = work.convert_rig_to_mmd(arm, meshes, _state["slots"], _state["missing_optional"],
                                                  _state["helper_plans"], _state["skin_before"])
            stats["arm_down_deg"] = _state["apose"]
            stats["reparented_helpers"] = _state["helpers"]
            stats["relaxed_groups"] = _state["relaxed"]
            stats["distortion"] = work.mesh_distortion(_state["before"], meshes)
            stats["biped_prefix"] = _state["slots"]["lower_body_bone"].split(" ")[0]
            _state.update(root=root, stats=stats)
            settings.stage = 3
            physics = stats.get("physics") or {}
            _log(settings, "③ %d 根骨, 両目 %s, 表情 %d, 权重空洞 %d" % (
                     stats.get("bones", 0), "有" if stats.get("both_eyes_bone") else "无",
                     _count(stats.get("face_morphs")), stats.get("weight_holes", 0)),
                 "   物理: 身体 %s, 布料 %s (%d 件), 撕裂边 %d" % (
                     physics.get("body", "-"), physics.get("cloth", "-"), _count(physics.get("garments")),
                     (stats.get("distortion") or {}).get("torn", 0)),
                 "   下一步: ④ 导出 PMX（可先用 MMD 页签的 Cloth Physics / Face Morphs 面板调整）")
        except Exception as exc:
            return _fail(self, settings, exc)
        return {"FINISHED"}


def default_pmx_path(stem):
    return os.path.join(r"D:\roe_exports\pmx_manual", stem, stem + ".pmx")


class ROEPMX_OT_export(bpy.types.Operator):
    """Stage 4: eye bake, transparent slots to alpha 0, mmd_tools export at
    12.5 with textures, deform-order check, JSON report."""
    bl_idname = "roe_pmx.export"
    bl_label = "④ 导出 PMX"
    bl_description = "烘眼球贴图、透明槽 alpha 0、mmd_tools 以 12.5 倍导出并复制贴图、回读校验付与顺序"

    def execute(self, context):
        settings = context.scene.roe_pmx
        try:
            if "root" not in _state:
                raise RuntimeError("先跑 ③ 转 MMD")
            work, module, meshes, root, stats = (_state["work"], _state["module"], _state["meshes"],
                                                 _state["root"], _state["stats"])
            path = bpy.path.abspath(settings.pmx_out) if settings.pmx_out else default_pmx_path(_state["stem"])
            if not path.lower().endswith(".pmx"):
                path = os.path.join(path, _state["stem"] + ".pmx")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.isfile(path):
                os.remove(path)
            stats["portable_eye"] = work.bake_portable_eye(module, _state.get("head"),
                                                           os.path.join(os.path.dirname(path), "textures"))
            stats["hidden_materials"] = work.hide_transparent_materials(meshes)
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.select_all(action="DESELECT")
            stack = [root]
            while stack:
                obj = stack.pop()
                try:
                    obj.hide_set(False)
                    obj.select_set(True)
                except (ReferenceError, RuntimeError):
                    pass
                stack.extend(obj.children)
            context.view_layer.objects.active = root
            bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True, log_level="ERROR")
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise RuntimeError("PMX not written: %s" % path)
            try:
                stats["grant_order_violations"] = work.verify_grant_order(path)
            except Exception as exc:
                stats["grant_order_violations"] = ["check skipped: %s" % exc]
            stats["pmx"] = path
            with open(os.path.splitext(path)[0] + ".report.json", "w", encoding="utf-8") as handle:
                json.dump(stats, handle, ensure_ascii=False, indent=1, default=str)
            settings.stage = 4
            _log(settings, "④ 已写 %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6),
                 "   付与顺序违规 %d, 透明槽 %d, 眼球 %s; 报告 %s" % (
                     _count(stats["grant_order_violations"]), _count(stats["hidden_materials"]),
                     (stats["portable_eye"] or {}).get("status", "-"), os.path.basename(os.path.splitext(path)[0] + ".report.json")))
        except Exception as exc:
            return _fail(self, settings, exc)
        return {"FINISHED"}


class ROEPMX_OT_run_all(bpy.types.Operator):
    bl_idname = "roe_pmx.run_all"
    bl_label = "一键 ①→④"
    bl_description = "四步连跑，等于批处理 export_character_models.ps1 -Format pmx 对一个模型做的事"

    def execute(self, context):
        for op in (bpy.ops.roe_pmx.materials, bpy.ops.roe_pmx.prepare, bpy.ops.roe_pmx.convert,
                   bpy.ops.roe_pmx.export):
            if op() != {"FINISHED"}:
                return {"CANCELLED"}
        return {"FINISHED"}


class ROEPMX_OT_forget(bpy.types.Operator):
    bl_idname = "roe_pmx.forget"
    bl_label = "重来"
    bl_description = "忘掉各阶段的中间结果（场景不动）；换模型前点一下"

    def execute(self, context):
        _state.clear()
        context.scene.roe_pmx.stage = 0
        context.scene.roe_pmx.report = ""
        return {"FINISHED"}


class ROEPMX_PT_panel(bpy.types.Panel):
    bl_label = "PMX 导出（MMD）"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ROE"
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        settings = context.scene.roe_pmx
        if not hasattr(context.scene, "roe"):
            layout.label(text="需要先启用 ROE XPS Tools 插件", icon="ERROR")
            return
        col = layout.column(align=True)
        col.label(text="FBX / 贴图目录用上面 XPS 面板的字段", icon="INFO")
        col.operator("roe_pmx.materials", icon="IMPORT")
        col.operator("roe_pmx.prepare", icon="ARMATURE_DATA")
        col.operator("roe_pmx.convert", icon="MOD_ARMATURE")
        layout.prop(settings, "pmx_out")
        col = layout.column(align=True)
        col.operator("roe_pmx.export", icon="EXPORT")
        row = col.row(align=True)
        row.operator("roe_pmx.run_all", icon="PLAY")
        row.operator("roe_pmx.forget", icon="LOOP_BACK")
        if settings.report:
            box = layout.box()
            for line in settings.report.split("\n"):
                box.label(text=line)


CLASSES = (ROEPMX_Settings, ROEPMX_OT_materials, ROEPMX_OT_prepare, ROEPMX_OT_convert,
           ROEPMX_OT_export, ROEPMX_OT_run_all, ROEPMX_OT_forget, ROEPMX_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.roe_pmx = bpy.props.PointerProperty(type=ROEPMX_Settings)


def unregister():
    del bpy.types.Scene.roe_pmx
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
