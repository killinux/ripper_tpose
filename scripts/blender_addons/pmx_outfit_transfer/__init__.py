# -*- coding: utf-8 -*-
"""PMX Outfit Transfer - dress a PMX model in another PMX model's clothes, fitted to its body.

The clothes (chosen by material) come with their bones, rigid bodies, joints, materials and textures; they are
re-skinned to the target's skeleton and shrink-fitted to the target's nude body (core.py).  The two outfits'
rigid bodies never collide with each other.  The result is a new PMX next to the target (textures copied), imported
into the scene for picking the parts to keep.

UI: 3D viewport sidebar > MMD tab > 换装（服装移植）.  Headless: cli.py.
"""
bl_info = {
    "name": "PMX Outfit Transfer",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > 换装（服装移植）",
    "description": "把一个 PMX 模型的衣服贴身穿到另一个 PMX 模型的裸体上（骨骼重定向 + 按身体形状拟合），"
                   "连同骨骼、刚体、关节、材质贴图；两套衣服的刚体互不碰撞",
    "category": "Import-Export",
}

import importlib
import os
import traceback

import bpy

from . import core

importlib.reload(core)


class POT_MaterialItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    faces: bpy.props.IntProperty()
    enabled: bpy.props.BoolProperty(default=True)


class POT_Settings(bpy.types.PropertyGroup):
    donor: bpy.props.StringProperty(name="衣服来自", subtype="FILE_PATH", description="提供衣服的 PMX")
    target: bpy.props.StringProperty(name="穿到", subtype="FILE_PATH", description="要穿衣服的 PMX（目标）")
    out: bpy.props.StringProperty(name="输出 PMX", subtype="FILE_PATH",
                                  description="留空：目标旁边新建「<目标>_穿<前缀>衣服」文件夹；不会覆盖已有文件")
    materials: bpy.props.CollectionProperty(type=POT_MaterialItem)
    active: bpy.props.IntProperty()
    donor_body: bpy.props.StringProperty(name="源的身体材质",
                                         description="衣服是在这个身体上做的（ROE：*_nk_body，衣服下那份）")
    target_body: bpy.props.StringProperty(name="目标的裸体材质",
                                          description="衣服贴到这个身体上（ROE full：*_nk_body_nude）")
    prefix: bpy.props.StringProperty(name="新材质前缀", description="留空：从源文件名取（pc_g05_... → g05）")
    fit: bpy.props.BoolProperty(name="按身体形状贴身拟合", default=True,
                                description="关掉只按骨骼位置重定向，不管两个人身材的差别")
    near_cm: bpy.props.FloatProperty(name="贴身距离 cm", default=2.0, min=0.0, max=30.0,
                                     description="离源身体不超过这个距离的衣服完全跟着身体形状走")
    far_cm: bpy.props.FloatProperty(name="远离距离 cm", default=12.0, min=1.0, max=100.0,
                                    description="离源身体超过这个距离的部分（光环、法杖）只按骨骼走")
    align_rotation: bpy.props.BoolProperty(name="按骨骼方向旋转", default=True,
                                           description="两个模型休息姿势不同（T 形 / A 形）时需要；相同时没影响")
    split: bpy.props.EnumProperty(
        name="拆分材质", default="bone",
        items=(("bone", "按挂的骨头", "每个零件归到它主要挂着的骨头下，一根骨头一个材质（光环、叶子、前片……），方便挑零件"),
               ("island", "按连通块", "每块连在一起的布一个材质，小碎块按骨头合并"),
               ("none", "不拆", "源模型的材质原样搬过来")))
    min_piece: bpy.props.IntProperty(name="最小零件顶点数", default=100, min=1,
                                     description="按连通块拆时，比这小的碎块按骨头合并成「…_小件」")
    isolate: bpy.props.BoolProperty(name="两套衣服的刚体互不碰撞", default=True)
    collide_body: bpy.props.BoolProperty(name="新衣服碰目标的身体", default=True,
                                         description="新衣服的刚体和目标身体碰撞体碰撞（像在源模型上那样）")
    hide_with_outfit: bpy.props.BoolProperty(name="加进「衣服非表示」", default=False,
                                             description="full 版：拉「衣服非表示」时新衣服也一起藏起来")
    import_result: bpy.props.BoolProperty(name="做完导入场景", default=True)
    report: bpy.props.StringProperty()


def _settings(context):
    return context.scene.pmx_outfit


def _abs(path):
    return bpy.path.abspath(path) if path else ""


class POT_OT_scan(bpy.types.Operator):
    bl_idname = "pmx_outfit.scan"
    bl_label = "读取源模型的材质"
    bl_description = "列出衣服来源 PMX 的材质，勾选要搬的；顺便认出两边的身体材质"

    def execute(self, context):
        s = _settings(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not os.path.isfile(donor):
            self.report({"ERROR"}, "找不到源 PMX: %s" % donor)
            return {"CANCELLED"}
        try:
            pmx = core.pmx_module()
            D = pmx.load(donor)
            auto = set(core.auto_outfit_materials(D))
            s.materials.clear()
            for mt in D.materials:
                it = s.materials.add()
                it.name, it.faces, it.enabled = mt.name, mt.vertex_count // 3, mt.name in auto
            s.donor_body = core.auto_body(D, nude=False) or ""
            if os.path.isfile(target):
                T = pmx.load(target)
                s.target_body = core.auto_body(T, nude=True) or ""
            if not s.prefix:
                s.prefix = core.prefix_of(donor)
            s.report = "%d 个材质，默认勾了 %d 个" % (len(D.materials), len(auto))
        except Exception as exc:                                    # noqa: BLE001 - shown in the panel
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class POT_OT_transfer(bpy.types.Operator):
    bl_idname = "pmx_outfit.transfer"
    bl_label = "换装"
    bl_description = "把勾选的材质连同骨骼、刚体、关节搬到目标模型上，贴身拟合，写出新的 PMX"

    def execute(self, context):
        s = _settings(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not (os.path.isfile(donor) and os.path.isfile(target)):
            self.report({"ERROR"}, "先填好源 PMX 和目标 PMX")
            return {"CANCELLED"}
        if not len(s.materials):
            bpy.ops.pmx_outfit.scan()
        mats = [it.name for it in s.materials if it.enabled]
        if not mats:
            self.report({"ERROR"}, "没有勾选任何材质")
            return {"CANCELLED"}
        prefix = s.prefix or core.prefix_of(donor)
        out = _abs(s.out)
        if not out:
            stem = os.path.splitext(os.path.basename(target))[0]
            folder = os.path.join(os.path.dirname(target), "%s_穿%s衣服" % (stem, prefix))
            out = os.path.join(folder, "%s_穿%s衣服.pmx" % (stem, prefix))
        if os.path.exists(out):
            self.report({"ERROR"}, "输出已存在，不覆盖: %s" % out)
            return {"CANCELLED"}
        os.makedirs(os.path.dirname(out), exist_ok=True)
        lines = []
        try:
            report = core.transfer(donor, target, out, materials=mats, donor_body=s.donor_body or None,
                                   target_body=s.target_body or None, fit=s.fit, near_cm=s.near_cm, far_cm=s.far_cm,
                                   align_rotation=s.align_rotation, split=s.split, min_piece=s.min_piece,
                                   prefix=prefix, isolate=s.isolate, collide_body=s.collide_body,
                                   hide_morph="衣服非表示_材質" if s.hide_with_outfit else "",
                                   log=lambda t: (print(t), lines.append(t)))
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            s.report = "失败: %s" % exc
            return {"CANCELLED"}
        s.out = out
        s.report = "写出 %s：%d 个新材质，%d 根骨，%d 刚体，%d 关节%s" % (
            os.path.basename(out), len(report["materials_added"]), report["bones_added"], report["rigids_added"],
            report["joints_added"], "；" + "；".join(report["warnings"]) if report["warnings"] else "")
        if s.import_result:
            if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
                self.report({"WARNING"}, "mmd_tools 没启用，结果没导入场景")
            else:
                bpy.ops.mmd_tools.import_model(filepath=out, scale=0.08,
                                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class POT_UL_materials(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text="%s  (%d 面)" % (item.name, item.faces))


class POT_PT_panel(bpy.types.Panel):
    bl_label = "换装（服装移植）"
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
        layout.operator("pmx_outfit.scan", icon="VIEWZOOM")
        if len(s.materials):
            layout.template_list("POT_UL_materials", "", s, "materials", s, "active", rows=6)
        col = layout.column(align=True)
        col.prop(s, "donor_body")
        col.prop(s, "target_body")
        col.prop(s, "prefix")
        box = layout.box()
        box.prop(s, "fit")
        row = box.row(align=True)
        row.prop(s, "near_cm")
        row.prop(s, "far_cm")
        box.prop(s, "align_rotation")
        box.prop(s, "split")
        if s.split == "island":
            box.prop(s, "min_piece")
        box.prop(s, "isolate")
        box.prop(s, "collide_body")
        box.prop(s, "hide_with_outfit")
        box.prop(s, "import_result")
        layout.operator("pmx_outfit.transfer", icon="MOD_CLOTH")
        if s.report:
            for line in s.report.split("；"):
                layout.label(text=line)


CLASSES = (POT_MaterialItem, POT_Settings, POT_OT_scan, POT_OT_transfer, POT_UL_materials, POT_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pmx_outfit = bpy.props.PointerProperty(type=POT_Settings)


def unregister():
    del bpy.types.Scene.pmx_outfit
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
