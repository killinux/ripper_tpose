# -*- coding: utf-8 -*-
"""ROE Game Materials - after importing a Rise of Eros PMX (or XPS / FBX) into Blender, give it the
game's own full materials: normal maps, metallic / smoothness / AO, skin translucency and pore
detail, the hair colour.  For animating in Blender: the PMX keeps its MMD shader (switchable) and
everything mmd_tools needs to export it again.

UI: 3D viewport sidebar > MMD tab > ROE 游戏材质.  The work is done by
scripts/riseoferos/hq_materials_blender.py (the same code the batch export uses) in its in-place mode.
"""
bl_info = {
    "name": "ROE Game Materials",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > ROE 游戏材质",
    "description": "导入 Rise of Eros 的 PMX 后，换成游戏原始的完整材质（法线、金属度/光滑度/AO、皮肤透光和毛孔、"
                   "发色），参数可调，可随时切回 MMD 着色，不影响再导出 PMX",
    "category": "Material",
}

import importlib
import os
import sys

import bpy

_HQ = None


def hq():
    """scripts/riseoferos/hq_materials_blender.py: next to the repo this add-on is junctioned from,
    in ROE_SCRIPTS, or at the default repo path."""
    global _HQ
    if _HQ is not None:
        return _HQ
    here = os.path.dirname(os.path.realpath(__file__))
    for folder in (os.path.join(os.path.dirname(os.path.dirname(here)), "riseoferos"),
                   os.environ.get("ROE_SCRIPTS", ""), r"E:\code\othercode\ripper_tpose\scripts\riseoferos"):
        if folder and os.path.isfile(os.path.join(folder, "hq_materials_blender.py")):
            if folder not in sys.path:
                sys.path.insert(0, folder)
            import hq_materials_blender
            _HQ = importlib.reload(hq_materials_blender)
            return _HQ
    raise RuntimeError("找不到 hq_materials_blender.py（仓库 scripts/riseoferos；或设置环境变量 ROE_SCRIPTS）")


PARAMS = ("normal", "detail", "ao", "smooth", "metal", "sss", "hair_rough", "spec_occlusion")


def model_of(context):
    """(root object, meshes) of the model the active object belongs to: an mmd_tools model (its
    meshes, not rigid bodies / joints), else the armature and the meshes it deforms."""
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


def params_of(settings):
    return {name: getattr(settings, name) for name in PARAMS}


def _retune(self, context):
    _root, meshes = model_of(context)
    if meshes:
        module = hq()
        module.apply_params(module.hq_materials_of(meshes), params_of(self))


def _switch(self, context):
    _root, meshes = model_of(context)
    if meshes:
        module = hq()
        module.set_mode(module.hq_materials_of(meshes), self.mode)


class ROEGM_Settings(bpy.types.PropertyGroup):
    cid: bpy.props.StringProperty(name="角色代号", description="留空 = 自动（从模型名或贴图名认，比如 g05）")
    normal: bpy.props.FloatProperty(name="法线强度", default=1.0, min=0.0, max=3.0, update=_retune,
                                    description="游戏法线强度的倍数：布料纹理、缝线、褶皱的凹凸")
    detail: bpy.props.FloatProperty(name="毛孔细节", default=1.0, min=0.0, max=3.0, update=_retune,
                                    description="脸上细节法线（毛孔，游戏里平铺 70 倍）强度的倍数")
    ao: bpy.props.FloatProperty(name="AO 强度", default=1.0, min=0.0, max=2.0, update=_retune,
                                description="环境光遮蔽（凹处变暗）强度的倍数")
    smooth: bpy.props.FloatProperty(name="光滑度", default=1.0, min=0.0, max=2.0, update=_retune,
                                    description="光滑度的倍数：越大越亮、反光越清楚")
    metal: bpy.props.FloatProperty(name="金属度", default=1.0, min=0.0, max=2.0, update=_retune,
                                   description="金属度的倍数（金饰、扣子这类金属部分）")
    sss: bpy.props.FloatProperty(name="皮肤透光", default=0.1, min=0.0, max=0.5, update=_retune,
                                 description="皮肤次表面散射的量；0 = 关掉")
    hair_rough: bpy.props.FloatProperty(name="头发粗糙度", default=0.45, min=0.0, max=1.0, update=_retune,
                                        description="越小头发越亮越有光泽")
    spec_occlusion: bpy.props.BoolProperty(name="凹处高光也压暗", default=True, update=_retune,
                                           description="和游戏一样让 AO 也压暗反光；关掉后凹处的光滑面会反射整片天空")
    mode: bpy.props.EnumProperty(name="着色", default="game", update=_switch,
                                 items=(("game", "游戏材质", "游戏原始的完整材质"),
                                        ("mmd", "MMD 着色", "mmd_tools 原来的 MMD 着色")))
    cache: bpy.props.StringProperty(name="数据缓存", subtype="DIR_PATH",
                                    description=r"游戏材质数据的缓存目录；留空 = D:\roe_exports\_hq_materials")
    python: bpy.props.StringProperty(name="Python", subtype="FILE_PATH",
                                     description="装了 UnityPy 的 Python；留空 = PATH 里的 python")
    game_dir: bpy.props.StringProperty(name="游戏资源目录", subtype="DIR_PATH",
                                       description="RiseOfEros_Data\\StreamingAssets\\AssetBundles；留空 = Steam 默认位置")
    show_advanced: bpy.props.BoolProperty(name="高级", default=False)
    report: bpy.props.StringProperty()


class ROEGM_OT_apply(bpy.types.Operator):
    bl_idname = "roe_gm.apply"
    bl_label = "换上游戏原始材质"
    bl_description = ("给选中的模型（导入的 PMX / XPS / FBX）加上游戏原始的完整材质；原来的材质节点保留，"
                      "可切回 MMD 着色，再导出 PMX 不受影响。某个角色第一次用时要从游戏包读材质，需要几十秒")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.roe_gm
        root, meshes = model_of(context)
        if not meshes:
            self.report({"ERROR"}, "先选中模型（骨架、网格或 MMD 模型的根）")
            return {"CANCELLED"}
        try:
            _state, report = hq().apply(
                meshes, root.name if root else "", in_place=True, params=params_of(s),
                cid=s.cid.strip() or None, cache=bpy.path.abspath(s.cache) if s.cache else None,
                python=bpy.path.abspath(s.python) if s.python else None,
                game=bpy.path.abspath(s.game_dir) if s.game_dir else None)
        except Exception as exc:
            s.report = "失败：%s" % exc
            self.report({"ERROR"}, s.report)
            return {"CANCELLED"}
        s["mode"] = 0                        # the new networks are active: show 游戏材质 without re-switching
        s.report = "角色 %s：换了 %d 个材质，保留 %d 个（眼睛 / 睫毛 / 眉毛等），错误 %d" % (
            report["character"], len(report["upgraded"]), len(report["kept"]), len(report["errors"]))
        self.report({"WARNING"} if report["errors"] else {"INFO"}, s.report)
        for line in report["errors"][:5]:
            print("[roe_game_materials]", line)
        return {"FINISHED"}


class ROEGM_OT_reset(bpy.types.Operator):
    bl_idname = "roe_gm.reset"
    bl_label = "参数恢复默认"
    bl_description = "所有调整回到游戏原始值"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.roe_gm
        for name, value in hq().DEFAULT_PARAMS.items():
            setattr(s, name, value)
        return {"FINISHED"}


class ROEGM_OT_remove(bpy.types.Operator):
    bl_idname = "roe_gm.remove"
    bl_label = "去掉游戏材质"
    bl_description = "删掉本插件加的节点，恢复原来的材质"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.roe_gm
        _root, meshes = model_of(context)
        module = hq()
        count = module.remove_hq(module.hq_materials_of(meshes))
        s.report = "去掉了 %d 个材质里的游戏材质节点" % count
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class ROEGM_PT_panel(bpy.types.Panel):
    bl_label = "ROE 游戏材质"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        layout = self.layout
        s = context.scene.roe_gm
        root, meshes = model_of(context)
        if not meshes:
            layout.label(text="选中一个模型（导入的 PMX / XPS / FBX）", icon="INFO")
        else:
            count = sum(1 for o in meshes for slot in o.material_slots
                        if slot.material is not None and slot.material.get("roe_hq_base"))
            layout.label(text="%s：%d 个网格，%d 个材质已换" % (root.name if root else "?", len(meshes), count),
                         icon="OBJECT_DATA")
        layout.prop(s, "cid")
        layout.operator("roe_gm.apply", icon="MATERIAL")
        row = layout.row(align=True)
        row.prop(s, "mode", expand=True)

        box = layout.box()
        box.label(text="调整（实时生效，1.0 = 游戏原始值）", icon="MODIFIER")
        col = box.column(align=True)
        for name in ("normal", "detail", "ao", "smooth", "metal"):
            col.prop(s, name, slider=True)
        col = box.column(align=True)
        col.prop(s, "sss", slider=True)
        col.prop(s, "hair_rough", slider=True)
        box.prop(s, "spec_occlusion")
        box.operator("roe_gm.reset", icon="LOOP_BACK")

        layout.operator("roe_gm.remove", icon="TRASH")
        layout.prop(s, "show_advanced", icon="TRIA_DOWN" if s.show_advanced else "TRIA_RIGHT", emboss=False)
        if s.show_advanced:
            box = layout.box()
            box.prop(s, "cache")
            box.prop(s, "python")
            box.prop(s, "game_dir")
        if s.report:
            layout.label(text=s.report)


CLASSES = (ROEGM_Settings, ROEGM_OT_apply, ROEGM_OT_reset, ROEGM_OT_remove, ROEGM_PT_panel)


def register():
    global _HQ
    _HQ = None                               # Reload Scripts / re-enable: pick up an edited core
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.roe_gm = bpy.props.PointerProperty(type=ROEGM_Settings)


def unregister():
    del bpy.types.Scene.roe_gm
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
