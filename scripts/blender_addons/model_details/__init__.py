# -*- coding: utf-8 -*-
"""Model Details - small finishing touches for imported game models (Rise of Eros, Stellar Blade, Vindictus PMX and
the like), one panel per touch in the 3D viewport sidebar tab 细节.

First touch: 眼睛发亮有神 (eyes.py) - a brighter iris, a wet cornea and catchlights, laid over whatever the eye
renders with (mmd_tools' MMD shader or a game-material add-on's network), live sliders, removable.
"""
bl_info = {
    "name": "Model Details（模型细节）",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > 细节",
    "description": "导入的游戏模型的细节修饰：眼睛发亮有神（虹膜透光、角膜湿润反光、跟着镜头的眼神光），"
                   "ROE、剑星、Vindictus 的 PMX 都能用，叠在原来的着色上，可调可去掉",
    "category": "Material",
}

import importlib

import bpy

from . import eyes

importlib.reload(eyes)                    # Reload Scripts picks up an edited eyes.py

EYE_PARAMS = {"eye_glow": "glow", "eye_caustic": "caustic", "eye_sat": "sat", "eye_catch": "catch",
              "eye_catch_size": "catch_size", "eye_catch_angle": "catch_angle", "eye_wet": "wet"}


def model_of(context):
    """(root object, meshes) of the model the active object belongs to: an mmd_tools model (its meshes, not rigid
    bodies / joints), else the armature and the meshes it deforms, else the active mesh."""
    obj = context.active_object
    if obj is None:
        return None, []
    root = obj
    while root is not None and getattr(root, "mmd_type", "NONE") != "ROOT":
        root = root.parent
    if root is not None:
        return root, [o for o in root.children_recursive
                      if o.type == "MESH" and getattr(o, "mmd_type", "NONE") == "NONE"]
    arm = obj if obj.type == "ARMATURE" else (obj.parent if obj.parent and obj.parent.type == "ARMATURE" else None)
    if arm is None and obj.type == "MESH":
        arm = next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
    if arm is None:
        return obj, [obj] if obj.type == "MESH" else []
    # == not `is`: Blender hands out a new Python wrapper per access
    meshes = [o for o in context.scene.objects if o.type == "MESH" and
              (o.parent == arm or any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers))]
    return arm, meshes


def eye_params_of(settings):
    return {key: getattr(settings, prop) for prop, key in EYE_PARAMS.items()}


def _retune_eyes(self, context):
    _root, meshes = model_of(context)
    if meshes:
        eyes.retune(eyes.enhanced(meshes), eye_params_of(self))


D = eyes.DEFAULTS


class MDX_Settings(bpy.types.PropertyGroup):
    eye_glow: bpy.props.FloatProperty(name="虹膜发光", default=D["glow"], min=0.0, max=3.0, update=_retune_eyes,
                                      description="整个虹膜自己发的光：眼皮阴影里、暗场景里也亮（瞳孔不发光）")
    eye_caustic: bpy.props.FloatProperty(name="下半透光", default=D["caustic"], min=0.0, max=5.0,
                                         update=_retune_eyes,
                                         description="虹膜下半圈额外的光：光从上面穿过角膜照亮虹膜下缘，眼睛显得通透")
    eye_sat: bpy.props.FloatProperty(name="虹膜鲜艳", default=D["sat"], min=0.0, max=2.0, update=_retune_eyes,
                                     description="发出的光的颜色饱和度倍数")
    eye_catch: bpy.props.FloatProperty(name="眼神光", default=D["catch"], min=0.0, max=30.0, update=_retune_eyes,
                                       description="虹膜上两个高光点（一大一小）的亮度；0 = 不要")
    eye_catch_size: bpy.props.FloatProperty(name="眼神光大小", default=D["catch_size"], min=0.2, max=3.0,
                                            update=_retune_eyes, description="高光点大小的倍数")
    eye_catch_angle: bpy.props.FloatProperty(name="眼神光方向", default=D["catch_angle"], min=0.0, max=360.0,
                                             update=_retune_eyes,
                                             description="大高光点在屏幕上的方向（度）：0 = 右，90 = 上，145 = 左上（默认），"
                                                         "180 = 左；小的在对面。跟着镜头，两只眼睛同一边")
    eye_wet: bpy.props.FloatProperty(name="湿润反光", default=D["wet"], min=0.0, max=1.0, update=_retune_eyes,
                                     description="角膜的反光：场景里的灯在眼睛上清楚的小反光点；0.5 = 真实角膜")
    report: bpy.props.StringProperty()


class MDX_OT_eye_shine(bpy.types.Operator):
    bl_idname = "mdx.eye_shine"
    bl_label = "眼睛发亮有神"
    bl_description = ("给选中模型的眼睛加上虹膜透光、角膜湿润反光、跟着镜头方向的眼神光；叠在原来的着色上，"
                      "MMD 着色和各游戏材质插件的游戏材质都管用。换过游戏材质以后再点一次。不影响再导出 PMX")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.mdx
        _root, meshes = model_of(context)
        if not meshes:
            self.report({"ERROR"}, "先选中模型（骨架、网格或 MMD 模型的根）")
            return {"CANCELLED"}
        report = eyes.apply(meshes, eye_params_of(s))
        if not report["eyes"]:
            s.report = "没找到眼睛" + ("：%s" % "、".join(report["skipped"]) if report["skipped"] else "")
            self.report({"WARNING"}, s.report)
            return {"CANCELLED"}
        s.report = "眼睛：%s%s%s" % ("、".join(report["eyes"]),
                                   "；跳过 %s" % "、".join(report["skipped"]) if report["skipped"] else "",
                                   "；错误 %d" % len(report["errors"]) if report["errors"] else "")
        self.report({"WARNING"} if report["errors"] else {"INFO"}, s.report)
        for line in report["errors"][:5]:
            print("[model_details]", line)
        return {"FINISHED"}


class MDX_OT_eye_plain(bpy.types.Operator):
    bl_idname = "mdx.eye_plain"
    bl_label = "去掉"
    bl_description = "去掉眼睛的发亮有神效果，眼睛回到原来的样子"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.mdx
        _root, meshes = model_of(context)
        s.report = "眼睛恢复原样：%d 个材质" % eyes.remove(meshes)
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class MDX_OT_eye_reset(bpy.types.Operator):
    bl_idname = "mdx.eye_reset"
    bl_label = "恢复默认"
    bl_description = "眼睛的滑块回到默认值"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.mdx
        for prop, key in EYE_PARAMS.items():
            setattr(s, prop, eyes.DEFAULTS[key])
        return {"FINISHED"}


class MDX_PT_eyes(bpy.types.Panel):
    bl_label = "眼睛"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "细节"

    def draw(self, context):
        layout = self.layout
        s = context.scene.mdx
        root, meshes = model_of(context)
        if not meshes:
            layout.label(text="选中一个模型（导入的 PMX 等）", icon="INFO")
        else:
            done = eyes.enhanced(meshes)
            text = "%s：%s" % (root.name if root else "?", "已加发亮有神（%d 个眼睛材质）" % len(done) if done
                              else "眼睛还是原样")
            layout.label(text=text, icon="HIDE_OFF")
            if any(eyes.stale(m) for m in done):
                layout.label(text="材质换过了，再点一次「眼睛发亮有神」", icon="ERROR")
        layout.operator("mdx.eye_shine", icon="LIGHT_SUN")
        col = layout.column(align=True)
        for name in ("eye_glow", "eye_caustic", "eye_sat"):
            col.prop(s, name, slider=True)
        col = layout.column(align=True)
        for name in ("eye_catch", "eye_catch_size", "eye_catch_angle", "eye_wet"):
            col.prop(s, name, slider=True)
        row = layout.row(align=True)
        row.operator("mdx.eye_reset", icon="LOOP_BACK")
        row.operator("mdx.eye_plain", icon="X")
        if s.report:
            layout.label(text=s.report)


CLASSES = (MDX_Settings, MDX_OT_eye_shine, MDX_OT_eye_plain, MDX_OT_eye_reset, MDX_PT_eyes)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mdx = bpy.props.PointerProperty(type=MDX_Settings)


def unregister():
    del bpy.types.Scene.mdx
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
