# -*- coding: utf-8 -*-
"""FF7 Face Morphs - MMD expressions for FINAL FANTASY VII REMAKE characters, made from the game's own
facial poses and lip-sync shapes (shape keys -> PMX vertex morphs).

Blender add-on package.  UI: 3D viewport sidebar > MMD tab > FF7 Face Morphs.
Scripts: ``from ff7_face_morphs import api``; the batch exporter scripts/final/export_ff7_pmx_blender.py
(--face-data) runs the same core.
"""
bl_info = {
    "name": "FF7 Face Morphs",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > FF7 Face Morphs",
    "description": "MMD expressions (まばたき, あいうえお, 眉 ...) for FF7 Remake models from the game's own "
                   "facial poses and lip-sync data; one-click PMX export with expressions",
    "category": "Object",
}

# junction-installed from the repo: on Reload Scripts / re-enable refresh the submodules as well
if "bpy" in locals():
    import importlib

    for _module in (core, export, api):        # noqa: F821  (dependency order)
        importlib.reload(_module)

import os
import tempfile
import time

import bpy

from . import api, core, export

PANEL_LABEL = {"EYE": "目", "EYEBROW": "眉", "MOUTH": "口", "OTHER": "其他"}


def _active(context):
    obj = getattr(context, "active_object", None)
    if obj is None and getattr(context, "view_layer", None) is not None:
        obj = context.view_layer.objects.active
    return obj


def _parts(context):
    try:
        return core.model_parts(_active(context), context.scene)
    except Exception:
        return None, []


def _apply_preview(self, context):
    _arm, meshes = _parts(context)
    if meshes and self.morph:
        core.preview(meshes, self.morph, self.weight)


def _redraw():
    wm = bpy.context.window_manager
    for window in getattr(wm, "windows", []):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class FF7FM_Settings(bpy.types.PropertyGroup):
    data_path: bpy.props.StringProperty(name="表情数据", subtype="FILE_PATH",
                                        description="face-data JSON written by scripts/final/ff7_face_data.py "
                                                    "(the game's facial poses + lip-sync shapes of one character)")
    do_eye: bpy.props.BoolProperty(name="目", default=True, description="まばたき, 笑い, ウィンク ... (10)")
    do_brow: bpy.props.BoolProperty(name="眉", default=True, description="真面目, 困る, 怒り, 上, 下 ... (6)")
    do_mouth: bpy.props.BoolProperty(name="口", default=True, description="あいうえお, ん, にっこり ... (13)")
    do_other: bpy.props.BoolProperty(name="其他", default=True,
                                     description="the game's whole-face expressions F_Smile01 ... (14)")
    eye: bpy.props.FloatProperty(name="目 强度", default=1.0, min=0.1, max=3.0)
    brow: bpy.props.FloatProperty(name="眉 强度", default=1.0, min=0.1, max=3.0,
                                  description="the game's brows are subtle; 1.3-1.5 reads better in MMD")
    mouth: bpy.props.FloatProperty(name="口 强度", default=1.0, min=0.1, max=3.0)
    other: bpy.props.FloatProperty(name="其他 强度", default=1.0, min=0.1, max=3.0)
    morph: bpy.props.StringProperty(name="表情", update=_apply_preview,
                                    description="expression to show (only the ones this add-on built)")
    weight: bpy.props.FloatProperty(name="权重", default=1.0, min=0.0, max=1.0, update=_apply_preview)
    out_dir: bpy.props.StringProperty(name="输出文件夹", subtype="DIR_PATH")
    pmx_name: bpy.props.StringProperty(name="文件名", description="default: the .blend's name")
    model_name: bpy.props.StringProperty(name="模型名", description="name shown in MMD (default: file name)")
    skirt_to_legs: bpy.props.BoolProperty(
        name="裙骨皮肤跟大腿", default=False,
        description="skin weighted to the base outfit's skirt bones follows the thighs (TheWolfster GANTZ "
                    "suits #1707 / Rebirth #817); leave off for real skirts")
    previews: bpy.props.BoolProperty(name="渲染预览图", default=False,
                                     description="also render preview.png / preview_morphs.png / dance (+1 min)")
    show_manual: bpy.props.BoolProperty(name="手动转换（Convert_to_MMD5）", default=False)
    report: bpy.props.StringProperty()
    model_report: bpy.props.StringProperty()


def _settings(context):
    return context.scene.ff7_face


def _categories(s):
    return tuple(c for c, on in (("EYE", s.do_eye), ("EYEBROW", s.do_brow), ("MOUTH", s.do_mouth),
                                 ("OTHER", s.do_other)) if on)


def _strengths(s):
    return {"EYE": s.eye, "EYEBROW": s.brow, "MOUTH": s.mouth, "OTHER": s.other}


def _data_path(context):
    s = _settings(context)
    if s.data_path and os.path.isfile(bpy.path.abspath(s.data_path)):
        return bpy.path.abspath(s.data_path)
    arm, meshes = _parts(context)
    found = core.find_face_data(arm, meshes) if arm is not None else ""
    if found:
        s.data_path = found
    return found


class FF7FM_OT_find_data(bpy.types.Operator):
    bl_idname = "ff7_face.find_data"
    bl_label = "查找表情数据"
    bl_description = "Look for this character's face-data JSON (PC0002 -> PC0002_Tifa.json) in %s" % (
        "; ".join(core.DATA_DIRS) or "FF7_FACE_DATA_DIR")

    def execute(self, context):
        s = _settings(context)
        s.data_path = ""
        path = _data_path(context)
        if not path:
            self.report({"WARNING"}, "no face data found - run scripts/final/ff7_face_data.py first")
            return {"CANCELLED"}
        s.report = "表情数据：" + os.path.basename(path)
        return {"FINISHED"}


class FF7FM_OT_analyze(bpy.types.Operator):
    bl_idname = "ff7_face.analyze"
    bl_label = "分析模型"
    bl_description = "Find the face rig, the meshes skinned to it and what the face data can build"

    def execute(self, context):
        s = _settings(context)
        try:
            info = api.analyze(_active(context), _data_path(context) or None)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        lines = ["骨架 %s：脸部骨骼 %d 根，蒙皮网格 %d 个" % (info["armature"], info["face_bones"], len(info["meshes"]))]
        if info.get("data"):
            lines.append("数据 %s：姿势 %d，口型 %d" % (info["data"], info["poses"], info["visemes"]))
            lines.append("可生成 %d 个表情（目 %d / 眉 %d / 口 %d / 其他 %d）" % (
                info["possible"], *[info["by_panel"].get(c, 0) for c in core.CATEGORIES]))
        else:
            lines.append("没有表情数据：点放大镜查找，或先运行 ff7_face_data.py")
        if info["built"]:
            lines.append("已有本插件生成的表情 %d 个" % len(info["built"]))
        if info["stashed"]:
            lines.append("已暂存：转换完成后点「恢复并登记」")
        s.model_report = "\n".join(lines)
        return {"FINISHED"}


class FF7FM_OT_build(bpy.types.Operator):
    bl_idname = "ff7_face.build"
    bl_label = "生成表情"
    bl_description = ("Pose the face bones as each expression and store the skinned result as a shape key "
                      "(same-named keys are rebuilt; the scene's pose and key values stay as they were)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = _settings(context)
        path = _data_path(context)
        if not path:
            self.report({"ERROR"}, "no face data - set the path or run scripts/final/ff7_face_data.py")
            return {"CANCELLED"}
        try:
            made = api.build(_active(context), path, categories=_categories(s), strengths=_strengths(s))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        counts = {c: sum(1 for m in made if m[2] == c) for c in core.CATEGORIES}
        s.report = "生成 %d 个表情：目 %d / 眉 %d / 口 %d / 其他 %d" % (len(made), *[counts[c] for c in core.CATEGORIES])
        if made:
            s.morph = made[0][0]
        return {"FINISHED"}


class FF7FM_OT_clear(bpy.types.Operator):
    bl_idname = "ff7_face.clear"
    bl_label = "清除"
    bl_description = "Remove the shape keys this add-on built (never any other shape key)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = _settings(context)
        try:
            removed = api.clear(_active(context))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        s.morph = ""
        s.report = "已删除 %d 个表情" % len(removed)
        return {"FINISHED"}


class FF7FM_OT_reset_preview(bpy.types.Operator):
    bl_idname = "ff7_face.reset_preview"
    bl_label = "归零"
    bl_description = "Set every expression this add-on built back to 0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _arm, meshes = _parts(context)
        core.preview(meshes, "", 0.0)
        return {"FINISHED"}


class FF7FM_OT_stash(bpy.types.Operator):
    bl_idname = "ff7_face.stash"
    bl_label = "转换前暂存"
    bl_description = ("Before Convert_to_MMD5: its A-pose / arm alignment bakes skip meshes that have shape "
                      "keys, so move the keys into the .blend (a hidden mesh copy) until the conversion is done")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = _settings(context)
        try:
            done = api.stash(_active(context))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not done:
            self.report({"WARNING"}, "no shape keys to stash")
            return {"CANCELLED"}
        s.report = "已暂存 %d 个网格的形态键；转换完成后点「恢复并登记」" % len(done)
        return {"FINISHED"}


class FF7FM_OT_restore(bpy.types.Operator):
    bl_idname = "ff7_face.restore"
    bl_label = "恢复并登记"
    bl_description = ("After the conversion: put the stashed keys back (following the model if it was turned "
                      "or scaled) and file them under 目 / 眉 / 口 / その他 of the mmd_tools model")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = _settings(context)
        try:
            result = api.restore(_active(context))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        bad = [v for v in result["restored"].values() if isinstance(v, str)]
        if bad:
            self.report({"ERROR"}, bad[0])
        s.report = "恢复 %d 个网格；登记到 MMD 模型 %d 个表情" % (
            len(result["restored"]) - len(bad), len(result["registered"]))
        return {"FINISHED"} if not bad else {"CANCELLED"}


def _export_tick():
    result = export.poll()
    _redraw()
    return 2.0 if result is None else None


class FF7FM_OT_export_pmx(bpy.types.Operator):
    bl_idname = "ff7_face.export_pmx"
    bl_label = "导出带表情的 PMX"
    bl_description = ("Convert this .blend to PMX with the expressions in a background Blender (the batch "
                      "script export_ff7_pmx_blender.py; the open scene is not touched).  "
                      "The folder <output>/<name>/ is replaced")

    @classmethod
    def poll(cls, context):
        return export.available() and not export.running()

    def execute(self, context):
        s = _settings(context)
        path = _data_path(context)
        if not path:
            self.report({"ERROR"}, "no face data - set the path or run scripts/final/ff7_face_data.py")
            return {"CANCELLED"}
        stem = os.path.splitext(bpy.path.basename(bpy.data.filepath))[0] or "ff7_model"
        name = s.pmx_name.strip() or stem
        out_dir = bpy.path.abspath(s.out_dir) if s.out_dir else export.default_out()
        blend, temp = bpy.data.filepath, ""
        if not bpy.data.is_saved or bpy.data.is_dirty:
            temp = os.path.join(tempfile.gettempdir(), "ff7_face_pmx_src_%s.blend" % time.strftime("%H%M%S"))
            bpy.ops.wm.save_as_mainfile(filepath=temp, copy=True)
            blend = temp
        try:
            export.start(blend, out_dir, name, path, model_name=s.model_name.strip(), skirt_to_legs=s.skirt_to_legs,
                         categories=_categories(s), strengths=_strengths(s), previews=s.previews, temp_copy=temp)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        bpy.app.timers.register(_export_tick, first_interval=2.0)
        s.report = "后台导出到 %s" % os.path.join(out_dir, name)
        return {"FINISHED"}


class FF7FM_OT_open_folder(bpy.types.Operator):
    bl_idname = "ff7_face.open_folder"
    bl_label = "打开文件夹"
    bl_description = "Open the folder of the last exported PMX"

    def execute(self, context):
        pmx = export.STATUS.get("pmx")
        if not pmx:
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=os.path.dirname(pmx))
        return {"FINISHED"}


class FF7FM_PT_panel(bpy.types.Panel):
    bl_label = "FF7 Face Morphs"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        layout = self.layout
        s = _settings(context)
        arm, meshes = _parts(context)
        row = layout.row(align=True)
        row.prop(s, "data_path", text="")
        row.operator("ff7_face.find_data", text="", icon="VIEWZOOM")
        layout.operator("ff7_face.analyze", icon="INFO")
        for line in s.model_report.split("\n") if s.model_report else []:
            layout.label(text=line)
        if arm is None:
            layout.label(text="选中 FF7 模型的骨架或网格", icon="ERROR")

        box = layout.box()
        box.label(text="生成表情", icon="SHAPEKEY_DATA")
        row = box.row(align=True)
        for prop in ("do_eye", "do_brow", "do_mouth", "do_other"):
            row.prop(s, prop, toggle=True)
        col = box.column(align=True)
        for prop, on in (("eye", s.do_eye), ("brow", s.do_brow), ("mouth", s.do_mouth), ("other", s.do_other)):
            sub = col.row()
            sub.enabled = on
            sub.prop(s, prop, slider=True)
        row = box.row(align=True)
        row.operator("ff7_face.build", icon="ADD")
        row.operator("ff7_face.clear", icon="TRASH")

        box = layout.box()
        box.label(text="预览", icon="HIDE_OFF")
        keyed = next((m for m in meshes if m.data.shape_keys and core.tagged(m)), None)
        if keyed is not None:
            box.prop_search(s, "morph", keyed.data.shape_keys, "key_blocks", text="表情")
            row = box.row(align=True)
            row.prop(s, "weight", slider=True)
            row.operator("ff7_face.reset_preview", text="", icon="LOOP_BACK")
        else:
            box.label(text="还没有生成表情")

        box = layout.box()
        box.label(text="导出 PMX（后台，不改当前文件）", icon="EXPORT")
        box.prop(s, "out_dir")
        if not s.out_dir:
            box.label(text="默认：" + export.default_out())
        box.prop(s, "pmx_name")
        box.prop(s, "model_name")
        box.prop(s, "skirt_to_legs")
        box.prop(s, "previews")
        box.operator("ff7_face.export_pmx", icon="EXPORT")
        if not export.available():
            box.label(text="找不到 export_ff7_pmx_blender.py（插件要从仓库安装）", icon="ERROR")
        if export.STATUS.get("text"):
            box.label(text=export.STATUS["text"])
        if export.STATUS.get("pmx"):
            box.label(text=export.STATUS["pmx"])
            box.operator("ff7_face.open_folder", icon="FILE_FOLDER")

        box = layout.box()
        box.prop(s, "show_manual", icon="TRIA_DOWN" if s.show_manual else "TRIA_RIGHT", emboss=False)
        if s.show_manual:
            col = box.column(align=True)
            col.label(text="Convert_to_MMD5 烘 A 字姿势时会跳过带形态键的网格：")
            col.label(text="生成表情 → 转换前暂存 → 转换 → 恢复并登记 → 导出")
            row = box.row(align=True)
            row.operator("ff7_face.stash", icon="IMPORT")
            row.operator("ff7_face.restore", icon="LOOP_BACK")
            if meshes and core.stashed(meshes):
                box.label(text="已暂存，等待恢复", icon="TIME")
        if s.report:
            layout.label(text=s.report)


CLASSES = (FF7FM_Settings, FF7FM_OT_find_data, FF7FM_OT_analyze, FF7FM_OT_build, FF7FM_OT_clear,
           FF7FM_OT_reset_preview, FF7FM_OT_stash, FF7FM_OT_restore, FF7FM_OT_export_pmx, FF7FM_OT_open_folder,
           FF7FM_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ff7_face = bpy.props.PointerProperty(type=FF7FM_Settings)


def unregister():
    if bpy.app.timers.is_registered(_export_tick):
        bpy.app.timers.unregister(_export_tick)
    del bpy.types.Scene.ff7_face
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
