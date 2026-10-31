# -*- coding: utf-8 -*-
"""PMX Head Swap - put one PMX model's head on another PMX model's body with an invisible neck seam.

The head (face, eyes, lashes, brows, hair - chosen by material) comes with its bones, hair physics, textures and
expressions; the neck ring of the head is welded onto the body's neck ring exactly, normals / weights / skin tone made
continuous there (core.py).  The target's own head goes.  UI: 3D viewport sidebar > MMD tab > 换头.  Headless: cli.py.
Needs the pmx_outfit_transfer add-on folder next to this one (shared helpers).
"""
bl_info = {
    "name": "PMX Head Swap",
    "author": "ripper_tpose",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > 换头",
    "description": "把一个 PMX 模型的头（脸、眼睛、睫毛、眉毛、头发、表情、头发物理）换到另一个 PMX 模型的身体上，"
                   "脖子接缝顶点对顶点焊接，法线、权重、肤色在接缝处连续",
    "category": "Import-Export",
}

import importlib
import os
import traceback

import bpy

from . import core

importlib.reload(core)


class PHS_MaterialItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    faces: bpy.props.IntProperty()
    enabled: bpy.props.BoolProperty(default=True)


class PHS_Settings(bpy.types.PropertyGroup):
    donor: bpy.props.StringProperty(name="头来自", subtype="FILE_PATH", description="提供头的 PMX")
    target: bpy.props.StringProperty(name="换到", subtype="FILE_PATH", description="要换头的 PMX（身体留下）")
    out: bpy.props.StringProperty(name="输出 PMX", subtype="FILE_PATH",
                                  description="留空：目标旁边新建「<目标>_换<前缀>头」文件夹；不会覆盖已有文件")
    materials: bpy.props.CollectionProperty(type=PHS_MaterialItem)
    active: bpy.props.IntProperty()
    remove: bpy.props.StringProperty(name="目标去掉的材质",
                                     description="逗号分隔；默认是目标自己的脸、眼睛、睫毛、眉毛、头发（含 _nude 副本）")
    blend_cm: bpy.props.FloatProperty(name="脖子过渡 cm", default=4.0, min=0.5, max=15.0,
                                      description="头的脖子在接缝以上这段距离里逐渐变成身体那一圈的形状、法线、权重")
    tone: bpy.props.EnumProperty(
        name="肤色", default="seam",
        items=(("seam", "匹配 + 接缝渐变", "整张脸贴图乘一个增益让脖子上下肤色一样，剩下的局部差别在接缝带里烘成渐变"),
               ("whole", "只匹配整张", "只乘增益"),
               ("none", "不动", "贴图原样")))
    scale: bpy.props.FloatProperty(name="头的缩放", default=1.0, min=0.5, max=2.0,
                                   description="以脖子那一圈为中心缩放整个头")
    prefix: bpy.props.StringProperty(name="前缀", description="新骨骼显示枠、重名材质用；留空从源文件名取")
    face: bpy.props.StringProperty(name="源的脸材质",
                                   description="开口边就是脖子接缝的那个材质；留空按名字认（ROE _nk_face），认不出取勾选的第一个")
    body: bpy.props.StringProperty(name="目标的身体材质",
                                   description="脖子接缝在这个材质上；留空用 ROE 的 *_nk_body，没有就按 body / skin 认；几个用逗号隔开")
    import_result: bpy.props.BoolProperty(name="做完导入场景", default=True)
    report: bpy.props.StringProperty()


def _s(context):
    return context.scene.pmx_head_swap


def _abs(path):
    return bpy.path.abspath(path) if path else ""


class PHS_OT_scan(bpy.types.Operator):
    bl_idname = "pmx_head_swap.scan"
    bl_label = "读取源模型的材质"
    bl_description = "列出提供头的 PMX 的材质，勾选属于头的；顺便填好目标要去掉的材质"

    def execute(self, context):
        s = _s(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not os.path.isfile(donor):
            self.report({"ERROR"}, "找不到源 PMX: %s" % donor)
            return {"CANCELLED"}
        try:
            pmx = core.oc.pmx_module()
            D = pmx.load(donor)
            auto = set(core.auto_head_materials(D))
            s.materials.clear()
            for mt in D.materials:
                it = s.materials.add()
                it.name, it.faces, it.enabled = mt.name, mt.vertex_count // 3, mt.name in auto
            if os.path.isfile(target):
                T = pmx.load(target)
                s.remove = ", ".join(core.auto_head_materials(T, with_nude=True))
            if not s.prefix:
                s.prefix = core.oc.prefix_of(donor)
            s.report = "%d 个材质，默认勾了 %d 个" % (len(D.materials), len(auto))
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class PHS_OT_swap(bpy.types.Operator):
    bl_idname = "pmx_head_swap.swap"
    bl_label = "换头"
    bl_description = "把勾选的头材质连同骨骼、物理、表情换到目标身体上，脖子接缝焊接，写出新的 PMX"

    def execute(self, context):
        s = _s(context)
        donor, target = _abs(s.donor), _abs(s.target)
        if not (os.path.isfile(donor) and os.path.isfile(target)):
            self.report({"ERROR"}, "先填好源 PMX 和目标 PMX")
            return {"CANCELLED"}
        if not len(s.materials):
            bpy.ops.pmx_head_swap.scan()
        head = [it.name for it in s.materials if it.enabled]
        if not head:
            self.report({"ERROR"}, "没有勾选任何材质")
            return {"CANCELLED"}
        remove = [x.strip() for x in s.remove.split(",") if x.strip()]
        prefix = s.prefix or core.oc.prefix_of(donor)
        out = _abs(s.out)
        if not out:
            stem = os.path.splitext(os.path.basename(target))[0]
            folder = os.path.join(os.path.dirname(target), "%s_换%s头" % (stem, prefix))
            out = os.path.join(folder, "%s_换%s头.pmx" % (stem, prefix))
        if os.path.exists(out):
            self.report({"ERROR"}, "输出已存在，不覆盖: %s" % out)
            return {"CANCELLED"}
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            report = core.swap_head(donor, target, out, head_materials=head, remove_materials=remove,
                                    blend_cm=s.blend_cm, tone=s.tone, scale=s.scale, prefix=prefix,
                                    face=s.face or None, body=s.body or None, log=print)
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            s.report = "失败: %s" % exc
            return {"CANCELLED"}
        s.out = out
        s.report = "写出 %s：接缝 %s，%d 根新骨，%d 刚体，%d 表情%s" % (
            os.path.basename(out), report.get("ring", {}).get("pairing", "-"), report["bones_added"],
            report["rigids_added"], report["morphs"],
            "；" + "；".join(report["warnings"]) if report["warnings"] else "")
        if s.import_result:
            if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
                self.report({"WARNING"}, "mmd_tools 没启用，结果没导入场景")
            else:
                bpy.ops.mmd_tools.import_model(filepath=out, scale=0.08,
                                               types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class PHS_UL_materials(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text="%s  (%d 面)" % (item.name, item.faces))


class PHS_PT_panel(bpy.types.Panel):
    bl_label = "换头"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        s = _s(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "donor")
        col.prop(s, "target")
        col.prop(s, "out")
        layout.operator("pmx_head_swap.scan", icon="VIEWZOOM")
        if len(s.materials):
            layout.template_list("PHS_UL_materials", "", s, "materials", s, "active", rows=5)
        layout.prop(s, "remove")
        box = layout.box()
        box.prop(s, "blend_cm")
        box.prop(s, "tone")
        box.prop(s, "scale")
        box.prop(s, "prefix")
        box.prop(s, "face")
        box.prop(s, "body")
        box.prop(s, "import_result")
        layout.operator("pmx_head_swap.swap", icon="USER")
        if s.report:
            for line in s.report.split("；"):
                layout.label(text=line)


CLASSES = (PHS_MaterialItem, PHS_Settings, PHS_OT_scan, PHS_OT_swap, PHS_UL_materials, PHS_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pmx_head_swap = bpy.props.PointerProperty(type=PHS_Settings)


def unregister():
    del bpy.types.Scene.pmx_head_swap
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
