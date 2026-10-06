# -*- coding: utf-8 -*-
"""Panels and operators (3D viewport sidebar > 表情).  Every button calls api.py."""
import json
import os

import bpy

from . import api, faceit, names, recipes, sources

OUTPUTS = (("VERTEX", "顶点表情", "Every expression a shape key = PMX vertex morph: exact in MMD whatever the "
                                  "weights, linear in between (lids travel on a straight line)"),
           ("BONE", "骨骼表情", "Every expression an mmd_tools bone morph: light, rotations stay arcs; in MMD the "
                                "skin follows only the 4 largest weights per vertex"),
           ("AUTO", "自动", "Bone morph where a 4-weight PMX stays within the threshold of the real rig, "
                            "vertex morph elsewhere"))
_PREVIEW_ITEMS = []                     # EnumProperty callbacks must keep their strings alive


def _settings(context):
    return context.scene.expression_kit


def _obj(context):
    s = _settings(context)
    return s.target or context.object


def _say(context, lines):
    _settings(context).report = "\n".join(lines)
    for window in context.window_manager.windows:          # also when a script / timer ran the button
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _preview_items(self, context):
    _PREVIEW_ITEMS.clear()
    try:
        made = api.made(_obj(context))
    except (ValueError, AttributeError):
        made = {}
    seen = []
    for kind, label in (("BONE", "骨"), (recipes.MMD, "顶"), (recipes.ARKIT, "AR")):
        for n in made.get(kind, []):
            if n not in seen:
                seen.append(n)
                _PREVIEW_ITEMS.append((n, "%s  [%s]" % (n, label), ""))
    if not _PREVIEW_ITEMS:
        _PREVIEW_ITEMS.append(("", "（还没有生成的表情）", ""))
    return _PREVIEW_ITEMS


def _preview_update(self, context):
    if self.preview_name:
        try:
            api.preview(_obj(context), self.preview_name, self.preview_value)
        except ValueError:
            pass


class EK_Settings(bpy.types.PropertyGroup):
    target: bpy.props.PointerProperty(
        name="模型", type=bpy.types.Object, poll=lambda self, o: o.type == "ARMATURE",
        description="The model's armature (empty = the active object's model)")
    source: bpy.props.EnumProperty(name="来源", items=sources.KINDS, default="DNA")
    dna_path: bpy.props.StringProperty(name="DNA", subtype="FILE_PATH",
                                       description="The face's MetaHuman DNA file (.dna)")
    action: bpy.props.PointerProperty(name="动作", type=bpy.types.Action,
                                      description="Optional: an action whose pose markers (or the action itself) "
                                                  "are named like the expressions")
    use_markers: bpy.props.BoolProperty(name="按姿势标记", default=True,
                                        description="One pose per pose marker (else the whole action is one pose)")
    neutral: bpy.props.StringProperty(name="中性姿势", description="Optional: the pose every other pose is measured "
                                                                  "against (the game's idle face)")
    capture_name: bpy.props.StringProperty(name="名字", default="まばたき")
    recipe_file: bpy.props.StringProperty(name="配方文件", subtype="FILE_PATH",
                                          description="Optional JSON that overrides / adds recipes (write one with "
                                                      "'导出配方' and edit it)")
    mmd_output: bpy.props.EnumProperty(name="方式", items=OUTPUTS, default="VERTEX")
    cat_eye: bpy.props.BoolProperty(name="目", default=True)
    cat_brow: bpy.props.BoolProperty(name="眉", default=True)
    cat_mouth: bpy.props.BoolProperty(name="口", default=True)
    cat_other: bpy.props.BoolProperty(name="其他", default=True)
    extras: bpy.props.BoolProperty(name="扩展表情", default=True,
                                   description="Also the less common names (aliases, one-sided brows, あ２, ん ...)")
    s_eye: bpy.props.FloatProperty(name="目", default=1.0, min=0.0, max=3.0)
    s_brow: bpy.props.FloatProperty(name="眉", default=1.0, min=0.0, max=3.0)
    s_mouth: bpy.props.FloatProperty(name="口", default=1.0, min=0.0, max=3.0)
    replace: bpy.props.BoolProperty(name="替换同名", default=True,
                                    description="Rebuild same-named morphs even if something else made them")
    threshold: bpy.props.FloatProperty(name="误差阈值 mm", default=0.3, min=0.0, max=10.0,
                                       description="AUTO: largest allowed PMX (4-weight) error of a bone morph")
    package_path: bpy.props.StringProperty(name="游戏包", subtype="FILE_PATH",
                                           description="Cooked UE5 face package (.uasset.bin) with the full skin "
                                                       "weights (UE Viewer keeps 4 per vertex)")
    head_bone: bpy.props.StringProperty(name="头骨")
    live_source: bpy.props.EnumProperty(name="实时源", items=faceit.SOURCES, default="FACECAP")
    preview_name: bpy.props.EnumProperty(name="表情", items=_preview_items, update=_preview_update)
    preview_value: bpy.props.FloatProperty(name="权重", default=1.0, min=0.0, max=1.0, update=_preview_update)
    pmx_path: bpy.props.StringProperty(name="PMX", subtype="FILE_PATH")
    pmx_arkit: bpy.props.BoolProperty(name="带 ARKit 形态键", default=False,
                                      description="Also write the 52 ARKit keys into the PMX (as 'other' morphs)")
    pmx_scale: bpy.props.FloatProperty(name="缩放", default=12.5, min=0.01, max=1000.0)
    report: bpy.props.StringProperty()
    phone_hint: bpy.props.StringProperty()


def _src_args(s):
    return dict(dna_path=s.dna_path, action=s.action, use_markers=s.use_markers, neutral=s.neutral)


def _categories(s):
    cats = [c for c, on in (("EYE", s.cat_eye), ("EYEBROW", s.cat_brow), ("MOUTH", s.cat_mouth),
                            ("OTHER", s.cat_other)) if on]
    return cats


def _strengths(s):
    return {"EYE": s.s_eye, "EYEBROW": s.s_brow, "MOUTH": s.s_mouth, "OTHER": 1.0}


def _report_lines(rep):
    lines = []
    if rep.get("note"):
        lines.append(rep["note"])
    if rep.get("bone"):
        lines.append("骨骼表情 %d 个" % len(rep["bone"]))
    if rep.get("vertex"):
        lines.append("%s %d 个" % ("形态键" if rep["set"] == recipes.ARKIT else "顶点表情", len(rep["vertex"])))
    if rep.get("errors_mm"):
        worst = max(rep["errors_mm"].items(), key=lambda kv: kv[1])
        lines.append("PMX 误差最大 %.2f mm（%s）" % (worst[1], worst[0]))
    if rep.get("skipped"):
        lines.append("跳过 %d 个：%s" % (len(rep["skipped"]), "、".join(n for n, _r in rep["skipped"][:4])))
    if rep.get("removed"):
        lines.append("替换掉 %d 个同名旧表情" % len(rep["removed"]))
    if rep.get("disconnected"):
        lines.append("断开了 %d 根相连的骨骼" % rep["disconnected"])
    info = rep.get("source_info", {})
    if "fit_mean_mm" in info:
        lines.append("DNA 对位误差 %.2f mm（%d 根骨）" % (info["fit_mean_mm"], info["joints"]))
    return lines or ["什么也没做"]


class _Base:
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def fail(self, exc):
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class EK_OT_analyze(_Base, bpy.types.Operator):
    """Report what the model has, which sources work on it and what its weights mean for a PMX"""
    bl_idname = "expression_kit.analyze"
    bl_label = "分析模型"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = _settings(context)
        try:
            info = api.analyze(_obj(context), s.dna_path, s.action, s.use_markers)
        except (ValueError, OSError) as exc:
            return self.fail(exc)
        src = info["sources"]
        lines = ["%s（%s）" % (info["armature"], "MMD 模型" if info["mmd_model"] else "未转 MMD"),
                 "脸部网格 %d 个 · 最多 %d 权重" % (len(info["face_meshes"]), info["max_influences"])]
        if info["four_capped"]:
            lines.append("! 权重被截成 4 个：先恢复完整权重")
        elif info["over4_vertices"]:
            lines.append("超 4 权重顶点 %d（骨骼有误差）" % info["over4_vertices"])
        lines.append("DNA 骨 %d · ARKit 键 %d/52" % (src["facial_bones"], info["arkit_keys"]))
        lines.append("姿势 %d · 骨骼脸角色 %s" % (src["POSES"], src["ROLES"]["roles"] if src["ROLES"]["calibrated"] else "无"))
        if "DNA" in src:
            d = src["DNA"]
            lines.append(("DNA：%s" % d["error"]) if "error" in d else
                         "DNA 对位 %d/%d · %.2f mm" % (d["joints"], d["dna_joints"], d["fit_mean_mm"]))
        lines.append("已有 MMD：顶点 %d · 骨骼 %d" % (info["mmd_vertex_morphs"], info["mmd_bone_morphs"]))
        m = info["made"]
        lines.append("本插件做的：骨 %d · 顶 %d · AR %d" % (m["BONE"], m[recipes.MMD], m[recipes.ARKIT]))
        state = {"enabled": "已启用", "disabled": "未启用", "missing": "未安装"}[info["faceit"]]
        if info.get("faceit_registered") is not None:
            state += "，%s" % ("已注册" if info["faceit_registered"] else "未注册")
        lines.append("Faceit：%s" % state)
        if info["stashed"]:
            lines.append("! 有暂存的形态键：%d 个网格" % len(info["stashed"]))
        _say(context, lines)
        print("EXPRESSION_KIT_ANALYZE=" + json.dumps(info, ensure_ascii=False, default=str))
        return {"FINISHED"}


class EK_OT_build(_Base, bpy.types.Operator):
    """Make the expressions of a set from the chosen source"""
    bl_idname = "expression_kit.build"
    bl_label = "生成"
    set_key: bpy.props.EnumProperty(items=[(k, v, "") for k, v in recipes.SETS.items()])

    def execute(self, context):
        s = _settings(context)
        is_mmd = self.set_key == recipes.MMD
        try:
            rep = api.build(_obj(context), self.set_key, s.source, output=s.mmd_output if is_mmd else "VERTEX",
                            categories=_categories(s) if is_mmd else None, extras=s.extras, strengths=_strengths(s),
                            replace=s.replace, threshold_mm=s.threshold, recipe_file=s.recipe_file,
                            log=lambda line: None, **_src_args(s))
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return self.fail(exc)
        _say(context, _report_lines(rep))
        print("EXPRESSION_KIT_BUILD=" + json.dumps(rep, ensure_ascii=False, default=str))
        return {"FINISHED"}


class EK_OT_estimate(_Base, bpy.types.Operator):
    """How far each expression would be off as a PMX bone morph (4 weights per vertex) - nothing is written"""
    bl_idname = "expression_kit.estimate"
    bl_label = "骨骼表情误差预估"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = _settings(context)
        try:
            rep = api.estimate(_obj(context), s.source, categories=_categories(s), extras=s.extras,
                               strengths=_strengths(s), recipe_file=s.recipe_file, **_src_args(s))
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return self.fail(exc)
        errs = sorted(rep["errors_mm"].items(), key=lambda kv: -kv[1])
        lines = ["超 4 权重顶点 %d（最多 %d）" % (rep["over4_vertices"], rep["max_influences"])]
        if errs:
            bad = [n for n, e in errs if e > s.threshold]
            lines.append("超过 %.2f mm 的：%d / %d" % (s.threshold, len(bad), len(errs)))
            lines += ["  %s  %.2f mm" % (n, e) for n, e in errs[:6]]
        else:
            lines.append("PMX 和 Blender 里一样：骨骼表情没有误差")
        if rep.get("scaled"):
            lines.append("要缩放骨骼、只能做顶点表情：%s" % "、".join(rep["scaled"]))
        _say(context, lines)
        return {"FINISHED"}


class EK_OT_clear(_Base, bpy.types.Operator):
    """Remove what this add-on made for this set (other morphs and keys stay)"""
    bl_idname = "expression_kit.clear"
    bl_label = "删除生成的"
    set_key: bpy.props.EnumProperty(items=[(k, v, "") for k, v in recipes.SETS.items()])

    def execute(self, context):
        try:
            rep = api.clear(_obj(context), self.set_key)
        except ValueError as exc:
            return self.fail(exc)
        _say(context, ["删除了 形态键 %d · 骨骼表情 %d" % (len(rep["shape_keys"]), len(rep["bone_morphs"]))])
        return {"FINISHED"}


class EK_OT_register_faceit(_Base, bpy.types.Operator):
    """Register the ARKit meshes, the 52 targets, the head bone and the live source with Faceit"""
    bl_idname = "expression_kit.register_faceit"
    bl_label = "注册到 Faceit"

    def execute(self, context):
        s = _settings(context)
        try:
            rep = api.register_faceit(_obj(context), head_bone=s.head_bone, source=s.live_source)
        except (ValueError, RuntimeError) as exc:
            return self.fail(exc)
        if not s.head_bone:
            s.head_bone = rep["head"].split(" / ")[-1]
        s.phone_hint = "手机填 %s 端口 %s" % (rep["lan_ip"], rep["port"])
        lines = ["Faceit 目标 %d/52" % rep["targets"]]
        if rep["missing"]:
            lines.append("缺：%s" % "、".join(rep["missing"][:4]))
        lines += ["头骨：%s" % s.head_bone, s.phone_hint, "然后 FACEIT → Mocap → Live → Start"]
        _say(context, lines)
        return {"FINISHED"}


class EK_OT_reset(_Base, bpy.types.Operator):
    """Every expression this add-on made back to 0"""
    bl_idname = "expression_kit.reset"
    bl_label = "归零"

    def execute(self, context):
        try:
            api.reset(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        return {"FINISHED"}


class EK_OT_check(_Base, bpy.types.Operator):
    """What would go wrong in MMD or Faceit with the model as it is"""
    bl_idname = "expression_kit.check"
    bl_label = "兼容性检查"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            issues = api.check(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        _say(context, [("! " if level != "INFO" else "") + msg for level, msg in issues])
        return {"FINISHED"}


class EK_OT_stash(_Base, bpy.types.Operator):
    """Park all shape keys in a hidden copy (Convert to MMD skips pose bakes on meshes with shape keys)"""
    bl_idname = "expression_kit.stash"
    bl_label = "转换前暂存"

    def execute(self, context):
        try:
            out = api.stash(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        _say(context, ["暂存了 %d 个网格的形态键" % len(out), "转换后点「恢复」"])
        return {"FINISHED"}


class EK_OT_restore(_Base, bpy.types.Operator):
    """Put the parked shape keys back (follows a rigid move / metre scaling of the conversion)"""
    bl_idname = "expression_kit.restore"
    bl_label = "转换后恢复"

    def execute(self, context):
        try:
            rep = api.restore(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        lines = []
        for name, r in rep.items():
            if name == "_registered":
                lines.append("登记到 MMD 表情面板：%d 个" % r)
            else:
                lines.append("%s：%s" % (name, ("%d 个形态键" % r["keys"]) if isinstance(r, dict) else r))
        _say(context, lines or ["没有暂存的形态键"])
        return {"FINISHED"}


class EK_OT_restore_weights(_Base, bpy.types.Operator):
    """Put the cooked UE5 package's full skin weights back (UE Viewer keeps only 4 per vertex)"""
    bl_idname = "expression_kit.restore_weights"
    bl_label = "恢复完整权重"

    def execute(self, context):
        s = _settings(context)
        path = s.package_path or api.companion_package(s.dna_path)
        if not path:
            return self.fail("选游戏包（.uasset.bin），或把它放在 DNA 旁边同名")
        try:
            rep = api.restore_weights(_obj(context), path)
        except (ValueError, OSError) as exc:
            return self.fail(exc)
        s.package_path = s.package_path or path
        lines = ["游戏包：最多 %d 个权重" % rep["package"]["max_influences"]]
        for name, r in rep["meshes"].items():
            lines.append("%s：%s" % (name, "对不上，跳过" if "skipped" in r else "补全 %d 个顶点" % r["rewritten"]))
        _say(context, lines)
        return {"FINISHED"}


class EK_OT_export_pmx(_Base, bpy.types.Operator):
    """mmd_tools PMX export (x12.5, textures copied); ARKit keys left out unless ticked"""
    bl_idname = "expression_kit.export_pmx"
    bl_label = "导出 PMX"

    def execute(self, context):
        s = _settings(context)
        if not s.pmx_path:
            return self.fail("先选 PMX 输出路径")
        path = bpy.path.abspath(s.pmx_path)
        if not path.lower().endswith(".pmx"):
            path += ".pmx"
        try:
            rep = api.export_pmx(_obj(context), path, include_arkit=s.pmx_arkit, scale=s.pmx_scale)
        except (ValueError, RuntimeError) as exc:
            return self.fail(exc)
        _say(context, ["导出：%s" % rep["path"], "（%d 个 ARKit 键没写进去）" % rep["parked"] if rep["parked"] else ""])
        return {"FINISHED"}


class EK_OT_capture(_Base, bpy.types.Operator):
    """Store the current pose of the armature as a named pose (source: 姿势库)"""
    bl_idname = "expression_kit.capture"
    bl_label = "记录当前姿势"

    def execute(self, context):
        s = _settings(context)
        if not s.capture_name:
            return self.fail("先填名字（MMD 名或 ARKit 名）")
        try:
            n = api.capture(_obj(context), s.capture_name)
        except ValueError as exc:
            return self.fail(exc)
        _say(context, ["记录「%s」：%d 根骨" % (s.capture_name, n), "姿势库现有：%s" % "、".join(api.captured_names(_obj(context))[:8])])
        return {"FINISHED"}


class EK_OT_forget(_Base, bpy.types.Operator):
    """Delete the named captured pose"""
    bl_idname = "expression_kit.forget"
    bl_label = "删除该姿势"

    def execute(self, context):
        s = _settings(context)
        try:
            ok = api.forget(_obj(context), s.capture_name)
        except ValueError as exc:
            return self.fail(exc)
        _say(context, ["删除了「%s」" % s.capture_name if ok else "没有「%s」" % s.capture_name])
        return {"FINISHED"}


class EK_OT_save_recipes(bpy.types.Operator):
    """Write the built-in recipes of a set to a JSON file you can edit and load back as 配方文件"""
    bl_idname = "expression_kit.save_recipes"
    bl_label = "导出配方"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    set_key: bpy.props.EnumProperty(items=[(k, v, "") for k, v in recipes.SETS.items()])

    def invoke(self, context, event):
        self.filepath = "expression_recipes_%s.json" % self.set_key.lower()
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = api.save_recipes(self.set_key, self.filepath)
        _say(context, ["配方写到 %s" % path])
        return {"FINISHED"}


# -- panels ---------------------------------------------------------------------------------------------
class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "表情"


class EK_PT_main(_Panel, bpy.types.Panel):
    bl_label = "表情工具箱"
    bl_idname = "EK_PT_main"

    def draw(self, context):
        s = _settings(context)
        col = self.layout.column(align=True)
        col.prop(s, "target")
        row = col.row(align=True)
        row.operator(EK_OT_analyze.bl_idname, icon="VIEWZOOM")
        row.operator(EK_OT_check.bl_idname, icon="CHECKMARK")
        if s.report:
            box = self.layout.box()
            for line in s.report.split("\n"):
                if line:
                    box.label(text=line, icon="ERROR" if line.startswith("!") else "NONE")


class EK_PT_source(_Panel, bpy.types.Panel):
    bl_label = "1 表情来源"
    bl_parent_id = "EK_PT_main"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        layout.prop(s, "source", text="")
        if s.source == "DNA":
            layout.prop(s, "dna_path")
            box = layout.box()
            box.label(text="权重只剩 4 个时（UE Viewer）：")
            box.prop(s, "package_path")
            box.operator(EK_OT_restore_weights.bl_idname, icon="GROUP_VERTEX")
        elif s.source == "SHAPES":
            layout.label(text="用模型自己的 ARKit 形态键混合（任意写法）")
        elif s.source == "POSES":
            layout.prop(s, "action")
            row = layout.row()
            row.prop(s, "use_markers")
            row.prop(s, "neutral", text="中性")
            box = layout.box()
            box.label(text="摆好脸部骨骼 → 起名 → 记录（名字用 MMD 名或 ARKit 名）")
            row = box.row(align=True)
            row.prop(s, "capture_name", text="")
            row.operator(EK_OT_capture.bl_idname, text="记录", icon="REC")
            row.operator(EK_OT_forget.bl_idname, text="", icon="TRASH")
        else:
            layout.label(text="按眼皮 / 眉 / 下巴 / 嘴唇 / 舌头骨骼自动摆（ROE 式骨骼脸）")
        layout.prop(s, "recipe_file", text="配方")


class EK_PT_mmd(_Panel, bpy.types.Panel):
    bl_label = "2 MMD 表情"
    bl_parent_id = "EK_PT_main"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        layout.prop(s, "mmd_output", expand=True)
        row = layout.row(align=True)
        for p in ("cat_eye", "cat_brow", "cat_mouth", "cat_other"):
            row.prop(s, p, toggle=True)
        col = layout.column(align=True)
        for p, label in (("s_eye", "目 强度"), ("s_brow", "眉 强度"), ("s_mouth", "口 强度")):
            col.prop(s, p, text=label, slider=True)
        row = layout.row()
        row.prop(s, "extras")
        row.prop(s, "replace")
        if s.mmd_output == "AUTO":
            layout.prop(s, "threshold")
        row = layout.row(align=True)
        op = row.operator(EK_OT_build.bl_idname, text="生成 MMD 表情", icon="SHAPEKEY_DATA")
        op.set_key = recipes.MMD
        op = row.operator(EK_OT_clear.bl_idname, text="", icon="TRASH")
        op.set_key = recipes.MMD
        layout.operator(EK_OT_estimate.bl_idname, icon="DRIVER_DISTANCE")


class EK_PT_arkit(_Panel, bpy.types.Panel):
    bl_label = "3 ARKit 52 / Faceit"
    bl_parent_id = "EK_PT_main"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        row = layout.row(align=True)
        op = row.operator(EK_OT_build.bl_idname, text="生成 52 个 ARKit 形态键", icon="SHAPEKEY_DATA")
        op.set_key = recipes.ARKIT
        op = row.operator(EK_OT_clear.bl_idname, text="", icon="TRASH")
        op.set_key = recipes.ARKIT
        layout.prop(s, "live_source")
        obj = _obj(context)
        arm = None
        try:
            arm = api.model(obj)[0] if obj is not None else None
        except ValueError:
            pass
        if arm is not None:
            layout.prop_search(s, "head_bone", arm.data, "bones")
        state, _pkg = faceit.faceit_state()
        if state != "enabled":
            layout.label(text="Faceit %s" % {"disabled": "未启用（偏好设置 → 插件）", "missing": "未安装"}[state],
                         icon="ERROR")
        layout.operator(EK_OT_register_faceit.bl_idname, icon="LINKED")
        if s.phone_hint:
            layout.label(text=s.phone_hint, icon="INFO")


class EK_PT_preview(_Panel, bpy.types.Panel):
    bl_label = "4 预览"
    bl_parent_id = "EK_PT_main"

    def draw(self, context):
        s = _settings(context)
        row = self.layout.row(align=True)
        row.prop(s, "preview_name", text="")
        row.prop(s, "preview_value", text="", slider=True)
        row.operator(EK_OT_reset.bl_idname, text="", icon="LOOP_BACK")


class EK_PT_tools(_Panel, bpy.types.Panel):
    bl_label = "5 转换与导出"
    bl_parent_id = "EK_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        layout.label(text="Convert to MMD 前后：")
        row = layout.row(align=True)
        row.operator(EK_OT_stash.bl_idname, icon="EXPORT")
        row.operator(EK_OT_restore.bl_idname, icon="IMPORT")
        layout.prop(s, "pmx_path")
        row = layout.row()
        row.prop(s, "pmx_arkit")
        row.prop(s, "pmx_scale")
        layout.operator(EK_OT_export_pmx.bl_idname, icon="EXPORT")
        row = layout.row(align=True)
        row.label(text="导出配方：")
        op = row.operator(EK_OT_save_recipes.bl_idname, text="MMD")
        op.set_key = recipes.MMD
        op = row.operator(EK_OT_save_recipes.bl_idname, text="ARKit")
        op.set_key = recipes.ARKIT


CLASSES = (EK_Settings, EK_OT_analyze, EK_OT_build, EK_OT_estimate, EK_OT_clear, EK_OT_register_faceit, EK_OT_reset,
           EK_OT_check, EK_OT_stash, EK_OT_restore, EK_OT_restore_weights, EK_OT_export_pmx, EK_OT_capture,
           EK_OT_forget, EK_OT_save_recipes, EK_PT_main, EK_PT_source, EK_PT_mmd, EK_PT_arkit, EK_PT_preview,
           EK_PT_tools)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.expression_kit = bpy.props.PointerProperty(type=EK_Settings)


def unregister():
    del bpy.types.Scene.expression_kit
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
