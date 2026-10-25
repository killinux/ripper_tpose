# -*- coding: utf-8 -*-
"""PMX Expression Transfer - copy one PMX model's facial expressions onto another PMX model's face.

The two faces may come from different games and have nothing in common but being faces: the eye openings, lid
margins, lip line and nose are found on both from the front, the donor's face is bent onto the target's, and every
expression is carried over as a vertex morph (eyes closing exactly, lashes / brows on the skin, teeth on the jaw)
- see core.py.  The result is a new PMX (textures copied when written elsewhere), imported into the scene.

UI: 3D viewport sidebar > MMD tab > 表情移植.  Headless: cli.py.
"""
bl_info = {
    "name": "PMX Expression Transfer",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > 表情移植",
    "description": "把一个 PMX 模型的表情（眨眼、口型、眉毛……）移植到另一个 PMX 模型的脸上，"
                   "两张脸的网格不用一样：按眼睛、嘴、鼻子对准后贴过去，眨眼闭严，睫毛眉毛跟着脸，牙齿跟着下巴",
    "category": "Import-Export",
}

import importlib
import os
import traceback

import bpy

from . import core

importlib.reload(core)

PANEL_LABEL = {1: "眉", 2: "目", 3: "口", 4: "其他", 0: "-"}


class PET_MorphItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    name_e: bpy.props.StringProperty()
    panel: bpy.props.IntProperty()
    kind: bpy.props.StringProperty()
    note: bpy.props.StringProperty()
    enabled: bpy.props.BoolProperty(default=True)


class PET_Settings(bpy.types.PropertyGroup):
    donor: bpy.props.StringProperty(name="表情来自", subtype="FILE_PATH", description="表情齐全的 PMX（来源）")
    target: bpy.props.StringProperty(name="移到", subtype="FILE_PATH", description="要加表情的 PMX（目标）")
    out: bpy.props.StringProperty(name="输出 PMX", subtype="FILE_PATH",
                                  description="留空：目标旁边新建「<目标>_表情移植」文件夹；不会覆盖已有文件")
    morphs: bpy.props.CollectionProperty(type=PET_MorphItem)
    active: bpy.props.IntProperty()
    replace: bpy.props.BoolProperty(name="同名的替换", default=False,
                                    description="目标已有同名表情时换成移植的；关掉则跳过（只补缺的）")
    lid: bpy.props.BoolProperty(name="眨眼闭严修正", default=True,
                                description="按两边眼睛张开的高度修正眼皮，来源闭上的地方目标也正好闭上")
    jaw: bpy.props.BoolProperty(name="牙齿舌头跟着下巴", default=True,
                                description="张嘴时下牙和舌头随下巴一起转，上牙不动")
    s_brow: bpy.props.FloatProperty(name="眉", default=1.0, min=0.0, max=3.0)
    s_eye: bpy.props.FloatProperty(name="目", default=1.0, min=0.0, max=3.0)
    s_mouth: bpy.props.FloatProperty(name="口", default=1.0, min=0.0, max=3.0)
    s_other: bpy.props.FloatProperty(name="其他", default=1.0, min=0.0, max=3.0)
    import_result: bpy.props.BoolProperty(name="做完导入场景", default=True)
    report: bpy.props.StringProperty()


def _settings(context):
    return context.scene.pmx_expression


def _abs(path):
    return bpy.path.abspath(path) if path else ""


class PET_OT_scan(bpy.types.Operator):
    bl_idname = "pmx_expression.scan"
    bl_label = "读取表情"
    bl_description = "列出来源 PMX 的表情；默认勾上目标没有的 MMD 标准表情"

    def execute(self, context):
        s = _settings(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not os.path.isfile(donor):
            self.report({"ERROR"}, "找不到来源 PMX: %s" % donor)
            return {"CANCELLED"}
        try:
            rows = core.list_morphs(donor, target if os.path.isfile(target) else None)
        except Exception as exc:                                    # noqa: BLE001 - shown in the panel
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        s.morphs.clear()
        for name, name_e, cat, kind, sel, note in rows:
            it = s.morphs.add()
            it.name, it.name_e, it.panel, it.kind, it.enabled, it.note = name, name_e or "", int(cat), kind, sel, note
        s.report = "%d 个表情，默认勾了 %d 个" % (len(rows), sum(1 for r in rows if r[4]))
        return {"FINISHED"}


class PET_OT_select(bpy.types.Operator):
    bl_idname = "pmx_expression.select"
    bl_label = "勾选"
    bl_description = "全部勾上 / 全部取消 / 只勾 MMD 标准表情"
    mode: bpy.props.EnumProperty(items=(("ALL", "全选", ""), ("NONE", "全不选", ""), ("STANDARD", "标准表情", "")))

    def execute(self, context):
        s = _settings(context)
        for it in s.morphs:
            usable = it.kind in ("vertex", "bone", "group")
            if self.mode == "ALL":
                it.enabled = usable
            elif self.mode == "NONE":
                it.enabled = False
            else:
                it.enabled = usable and it.name in core.STANDARD_NAMES and it.name not in core.NOT_BY_DEFAULT
        return {"FINISHED"}


class PET_OT_transfer(bpy.types.Operator):
    bl_idname = "pmx_expression.transfer"
    bl_label = "移植表情"
    bl_description = "把勾选的表情按目标的脸型贴过去，写出新的 PMX"

    def execute(self, context):
        s = _settings(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not (os.path.isfile(donor) and os.path.isfile(target)):
            self.report({"ERROR"}, "先填好来源 PMX 和目标 PMX")
            return {"CANCELLED"}
        if not len(s.morphs):
            bpy.ops.pmx_expression.scan()
        names = [it.name for it in s.morphs if it.enabled]
        if not names:
            self.report({"ERROR"}, "没有勾选任何表情")
            return {"CANCELLED"}
        out = _abs(s.out)
        if not out:
            stem = os.path.splitext(os.path.basename(target))[0]
            folder = os.path.join(os.path.dirname(target), "%s_表情移植" % stem)
            out = os.path.join(folder, "%s_表情移植.pmx" % stem)
        if os.path.exists(out):
            self.report({"ERROR"}, "输出已存在，不覆盖: %s" % out)
            return {"CANCELLED"}
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            report = core.transfer_expressions(
                donor, target, out, morphs=names, replace=s.replace, lid=s.lid, jaw=s.jaw,
                strength={1: s.s_brow, 2: s.s_eye, 3: s.s_mouth, 4: s.s_other}, log=print)
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            s.report = "失败: %s" % exc
            return {"CANCELLED"}
        s.out = out
        skipped = "、".join("%s（%s）" % (n, why) for n, why in report["skipped"][:6])
        s.report = "写出 %s：新加 %d 个，替换 %d 个，跳过 %d 个%s" % (
            os.path.basename(out), len(report["added"]), len(report["replaced"]), len(report["skipped"]),
            "；跳过：" + skipped if skipped else "")
        if s.import_result:
            if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
                self.report({"WARNING"}, "mmd_tools 没启用，结果没导入场景")
            else:
                bpy.ops.mmd_tools.import_model(filepath=out, scale=0.08,
                                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class PET_UL_morphs(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text="%s  [%s]" % (item.name, PANEL_LABEL.get(item.panel, "?")))
        if item.note:
            row.label(text=item.note)


class PET_PT_panel(bpy.types.Panel):
    bl_label = "表情移植"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "donor")
        col.prop(s, "target")
        col.prop(s, "out")
        layout.operator("pmx_expression.scan", icon="VIEWZOOM")
        if len(s.morphs):
            layout.template_list("PET_UL_morphs", "", s, "morphs", s, "active", rows=8)
            row = layout.row(align=True)
            for mode, text in (("STANDARD", "标准表情"), ("ALL", "全选"), ("NONE", "全不选")):
                row.operator("pmx_expression.select", text=text).mode = mode
        box = layout.box()
        box.prop(s, "replace")
        box.prop(s, "lid")
        box.prop(s, "jaw")
        box.label(text="强度（按面板）")
        row = box.row(align=True)
        for p in ("s_brow", "s_eye", "s_mouth", "s_other"):
            row.prop(s, p)
        box.prop(s, "import_result")
        layout.operator("pmx_expression.transfer", icon="SHAPEKEY_DATA")
        if s.report:
            for line in s.report.split("；"):
                layout.label(text=line)


CLASSES = (PET_MorphItem, PET_Settings, PET_OT_scan, PET_OT_select, PET_OT_transfer, PET_UL_morphs, PET_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pmx_expression = bpy.props.PointerProperty(type=PET_Settings)


def unregister():
    del bpy.types.Scene.pmx_expression
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
