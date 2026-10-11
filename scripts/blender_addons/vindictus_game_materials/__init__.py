# -*- coding: utf-8 -*-
"""Vindictus Game Materials - after importing a Vindictus: Defying Fate PMX (Fiona's outfits and the other
archived models) into Blender, give it the game's own full materials: normal maps, roughness / metallic, skin
translucency, the hair colours, brows, lashes and the eyes.  For animating in Blender: the PMX keeps its MMD shader
(switchable) and everything mmd_tools needs to export it again.

UI: 3D viewport sidebar > MMD tab > Vindictus 游戏材质.  The work is done by
scripts/vindictus/game_materials_blender.py, which copies the materials out of the archived .blend files.
"""
bl_info = {
    "name": "Vindictus Game Materials",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > Vindictus 游戏材质",
    "description": "导入 Vindictus（洛奇英雄传：Defying Fate）的 PMX 后，换成游戏原始的完整材质（法线、粗糙度 / 金属度、"
                   "皮肤透光、发色、眼睛），参数可调，可随时切回 MMD 着色，不影响再导出 PMX",
    "category": "Material",
}

import importlib
import os
import sys

import bpy

_CORE = None
DEFAULT_ARCHIVE = r"E:\game_export\Vindictus"


def core():
    """scripts/vindictus/game_materials_blender.py: next to the repo this add-on is junctioned from, in
    VINDICTUS_SCRIPTS, or at the default repo path."""
    global _CORE
    if _CORE is not None:
        return _CORE
    here = os.path.dirname(os.path.realpath(__file__))
    for folder in (os.path.join(os.path.dirname(os.path.dirname(here)), "vindictus"),
                   os.environ.get("VINDICTUS_SCRIPTS", ""), r"E:\code\othercode\ripper_tpose\scripts\vindictus"):
        if folder and os.path.isfile(os.path.join(folder, "game_materials_blender.py")):
            if folder not in sys.path:
                sys.path.insert(0, folder)
            import game_materials_blender
            _CORE = importlib.reload(game_materials_blender)
            return _CORE
    raise RuntimeError("找不到 game_materials_blender.py（仓库 scripts/vindictus；或设置环境变量 VINDICTUS_SCRIPTS）")


PARAMS = ("normal", "rough", "metal", "sss")


def model_of(context):
    """(root object, meshes) of the model the active object belongs to: an mmd_tools model (its meshes, not rigid
    bodies / joints), else the armature and the meshes it deforms."""
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


def archive_of(settings):
    return bpy.path.abspath(settings.archive) if settings.archive.strip() else DEFAULT_ARCHIVE


def _retune(self, context):
    _root, meshes = model_of(context)
    if meshes:
        module = core()
        module.apply_params(module.hq_materials_of(meshes), params_of(self))


def _switch(self, context):
    _root, meshes = model_of(context)
    if meshes:
        module = core()
        module.set_mode(module.hq_materials_of(meshes), self.mode)


class VINDGM_Settings(bpy.types.PropertyGroup):
    normal: bpy.props.FloatProperty(name="法线强度", default=1.0, min=0.0, max=3.0, update=_retune,
                                    description="游戏法线强度的倍数：布料纹理、缝线、褶皱、皮肤的凹凸")
    rough: bpy.props.FloatProperty(name="粗糙度", default=1.0, min=0.0, max=2.0, update=_retune,
                                   description="粗糙度的倍数：越小越亮、反光越清楚")
    metal: bpy.props.FloatProperty(name="金属度", default=1.0, min=0.0, max=2.0, update=_retune,
                                   description="金属度的倍数（金饰、盔甲这类金属部分）")
    sss: bpy.props.FloatProperty(name="皮肤透光", default=1.0, min=0.0, max=10.0, update=_retune,
                                 description="皮肤次表面散射的倍数；0 = 关掉")
    mode: bpy.props.EnumProperty(name="着色", default="game", update=_switch,
                                 items=(("game", "游戏材质", "游戏原始的完整材质"),
                                        ("mmd", "MMD 着色", "mmd_tools 原来的 MMD 着色")))
    archive: bpy.props.StringProperty(name="存档目录", subtype="DIR_PATH",
                                      description=r"Vindictus 存档的根目录（下面是 <角色>\blend\<模型>\<模型>.blend）；"
                                                  r"留空 = E:\game_export\Vindictus")
    show_advanced: bpy.props.BoolProperty(name="高级", default=False)
    report: bpy.props.StringProperty()


class VINDGM_OT_apply(bpy.types.Operator):
    bl_idname = "vind_gm.apply"
    bl_label = "换上游戏原始材质"
    bl_description = ("给选中的模型（导入的 Vindictus PMX）加上游戏原始的完整材质；原来的材质节点保留，可切回 MMD 着色，"
                      "再导出 PMX 不受影响。第一次用要扫一遍存档里的 .blend，十几秒")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.vind_gm
        root, meshes = model_of(context)
        if not meshes:
            self.report({"ERROR"}, "先选中模型（骨架、网格或 MMD 模型的根）")
            return {"CANCELLED"}
        hint = " ".join(filter(None, (root.name if root else "", getattr(getattr(root, "mmd_root", None), "name", ""),
                                      getattr(getattr(root, "mmd_root", None), "name_e", ""))))
        try:
            report = core().apply(meshes, archive_of(s), params=params_of(s), hint=hint,
                                  root=root if getattr(root, "mmd_type", "") == "ROOT" else None)
        except Exception as exc:
            s.report = "失败：%s" % exc
            self.report({"ERROR"}, s.report)
            return {"CANCELLED"}
        s["mode"] = 0                        # the new networks are active: show 游戏材质 without re-switching
        home = os.path.splitext(os.path.basename(report["home"]))[0] if report["home"] else "?"
        s.report = "%s：换了 %d 个材质，之前已换 %d 个，没找到 %d 个，错误 %d" % (
            home, len(report["upgraded"]), len(report["already"]), len(report["unmatched"]), len(report["errors"]))
        self.report({"WARNING"} if report["errors"] or report["unmatched"] else {"INFO"}, s.report)
        for line in report["unmatched"][:10]:
            print("[vindictus_game_materials] 没找到:", line)
        for line in report["errors"][:10]:
            print("[vindictus_game_materials]", line)
        return {"FINISHED"}


class VINDGM_OT_reset(bpy.types.Operator):
    bl_idname = "vind_gm.reset"
    bl_label = "参数恢复默认"
    bl_description = "所有调整回到游戏原始值"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.vind_gm
        for name, value in core().DEFAULT_PARAMS.items():
            setattr(s, name, value)
        return {"FINISHED"}


class VINDGM_OT_remove(bpy.types.Operator):
    bl_idname = "vind_gm.remove"
    bl_label = "去掉游戏材质"
    bl_description = "删掉本插件加的节点，恢复原来的材质"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.vind_gm
        _root, meshes = model_of(context)
        module = core()
        count = module.remove(module.hq_materials_of(meshes))
        s.report = "去掉了 %d 个材质里的游戏材质节点" % count
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class VINDGM_OT_rescan(bpy.types.Operator):
    bl_idname = "vind_gm.rescan"
    bl_label = "重新扫描存档"
    bl_description = "存档里加了或改了 .blend 以后：重新读一遍每个 .blend 里有哪些材质"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = context.scene.vind_gm
        index = core().archive_index(archive_of(s), fresh=True)
        s.report = "存档里 %d 个 .blend，%d 个材质" % (len(index), sum(len(e["materials"]) for e in index.values()))
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class VINDGM_PT_panel(bpy.types.Panel):
    bl_label = "Vindictus 游戏材质"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        layout = self.layout
        s = context.scene.vind_gm
        root, meshes = model_of(context)
        if not meshes:
            layout.label(text="选中一个模型（导入的 Vindictus PMX）", icon="INFO")
        else:
            count = sum(1 for o in meshes for slot in o.material_slots
                        if slot.material is not None and slot.material.get("vind_hq_base"))
            layout.label(text="%s：%d 个网格，%d 个材质已换" % (root.name if root else "?", len(meshes), count),
                         icon="OBJECT_DATA")
        layout.operator("vind_gm.apply", icon="MATERIAL")
        row = layout.row(align=True)
        row.prop(s, "mode", expand=True)

        box = layout.box()
        box.label(text="调整（实时生效，1.0 = 游戏原始值）", icon="MODIFIER")
        col = box.column(align=True)
        for name in PARAMS:
            col.prop(s, name, slider=True)
        box.operator("vind_gm.reset", icon="LOOP_BACK")

        layout.operator("vind_gm.remove", icon="TRASH")
        layout.prop(s, "show_advanced", icon="TRIA_DOWN" if s.show_advanced else "TRIA_RIGHT", emboss=False)
        if s.show_advanced:
            box = layout.box()
            box.prop(s, "archive")
            box.operator("vind_gm.rescan", icon="FILE_REFRESH")
        if s.report:
            layout.label(text=s.report)


CLASSES = (VINDGM_Settings, VINDGM_OT_apply, VINDGM_OT_reset, VINDGM_OT_remove, VINDGM_OT_rescan, VINDGM_PT_panel)


def register():
    global _CORE
    _CORE = None                             # Reload Scripts / re-enable: pick up an edited core
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vind_gm = bpy.props.PointerProperty(type=VINDGM_Settings)


def unregister():
    del bpy.types.Scene.vind_gm
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
