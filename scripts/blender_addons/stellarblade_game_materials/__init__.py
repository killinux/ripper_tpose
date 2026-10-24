# -*- coding: utf-8 -*-
"""Stellar Blade Game Materials - after importing a Stellar Blade Eve PMX (export_pmx_blender.py) into Blender, give
it the game's own full materials from the archive's HQ .blend (hq_materials_blender.py): normal maps, roughness /
metallic, clear coat, sheen, emission, the knit pattern.  The PMX keeps its MMD shader (switchable) and everything
mmd_tools needs to export it again.

UI: 3D viewport sidebar > MMD tab > 剑星游戏材质.  The work is done by scripts/stellarblade/game_materials_blender.py.
A model of several outfits in layers (scripts/clothes_burst/pmx_layers.py) takes each layer from its own HQ .blend;
handlers keep the layers the step sliders hide out of sight in EEVEE (core sync()).
"""
bl_info = {
    "name": "Stellar Blade Game Materials",
    "author": "ripper_tpose",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > 剑星游戏材质",
    "description": "导入剑星（Stellar Blade）Eve 的 PMX 后，换成游戏原始的完整材质（法线、粗糙度 / 金属度、清漆、"
                   "绒毛光泽、自发光），参数可调，可随时切回 MMD 着色，不影响再导出 PMX",
    "category": "Material",
}

import importlib.util
import os
import re

import bpy
from bpy.app.handlers import persistent

_CORE = None
_BUSY = False
DEFAULT_ARCHIVE = r"E:\game_export\StellarBlade"
PARAMS = ("normal", "rough", "metal", "clearcoat", "sheen", "emission")


def core():
    """scripts/stellarblade/game_materials_blender.py: next to the repo this add-on is junctioned from, in
    STELLARBLADE_SCRIPTS, or at the default repo path."""
    global _CORE
    if _CORE is not None:
        return _CORE
    here = os.path.dirname(os.path.realpath(__file__))
    for folder in (os.path.join(os.path.dirname(os.path.dirname(here)), "stellarblade"),
                   os.environ.get("STELLARBLADE_SCRIPTS", ""), r"E:\code\othercode\ripper_tpose\scripts\stellarblade"):
        if folder and os.path.isfile(os.path.join(folder, "game_materials_blender.py")):
            # its own module name: the Vindictus add-on imports a game_materials_blender of its own
            spec = importlib.util.spec_from_file_location("sb_game_materials_core",
                                                          os.path.join(folder, "game_materials_blender.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _CORE = module
            return _CORE
    raise RuntimeError("找不到 game_materials_blender.py（仓库 scripts/stellarblade；或设置环境变量 STELLARBLADE_SCRIPTS）")


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
    meshes = [o for o in context.scene.objects if o.type == "MESH" and
              (o.parent == arm or any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers))]
    return arm, meshes


def _sync(frame=None):
    """core sync() for the layers a morph hides - only once some material needs it (set by apply)"""
    global _BUSY
    if _BUSY or not any(m.get("sbhq_hide") for m in bpy.data.materials):
        return
    _BUSY = True
    try:
        core().sync(frame=frame)
    except Exception as exc:                 # a handler must never break the scene update or a render
        print("[stellarblade_game_materials] sync:", exc)
    finally:
        _BUSY = False


@persistent
def _on_depsgraph(scene, *_args):
    _sync()                                  # a slider dragged, a mode switched


@persistent
def _on_frame(scene, *_args):
    _sync(frame=scene.frame_current + scene.frame_subframe)  # before the frame is evaluated: curves at that frame


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


class SBGM_Settings(bpy.types.PropertyGroup):
    normal: bpy.props.FloatProperty(name="法线强度", default=1.0, min=0.0, max=3.0, update=_retune,
                                    description="游戏法线强度的倍数：缝线、褶皱、夹克的绗缝和针织纹理")
    rough: bpy.props.FloatProperty(name="粗糙度", default=1.0, min=0.0, max=2.0, update=_retune,
                                   description="粗糙度的倍数：越小越亮、反光越清楚")
    metal: bpy.props.FloatProperty(name="金属度", default=1.0, min=0.0, max=2.0, update=_retune,
                                   description="金属度的倍数（扣具、金属件）")
    clearcoat: bpy.props.FloatProperty(name="清漆", default=1.0, min=0.0, max=2.0, update=_retune,
                                       description="清漆层的倍数：乳胶、漆皮那层亮面；0 = 关掉")
    sheen: bpy.props.FloatProperty(name="绒毛光泽", default=1.0, min=0.0, max=5.0, update=_retune,
                                   description="布料边缘绒毛光泽（Sheen）的倍数")
    emission: bpy.props.FloatProperty(name="自发光", default=1.0, min=0.0, max=10.0, update=_retune,
                                      description="自发光强度的倍数；0 = 关掉")
    mode: bpy.props.EnumProperty(name="着色", default="game", update=_switch,
                                 items=(("game", "游戏材质", "游戏原始的完整材质"),
                                        ("mmd", "MMD 着色", "mmd_tools 原来的 MMD 着色")))
    archive: bpy.props.StringProperty(name="存档目录", subtype="DIR_PATH",
                                      description=r"剑星存档的根目录（下面是 <角色>\blend\<服装包名>\*_HQ.blend）；"
                                                  r"留空 = E:\game_export\StellarBlade")
    blend: bpy.props.StringProperty(name="指定 .blend", subtype="FILE_PATH",
                                    description="不在存档里找，直接从这个高清 .blend 取材质（留空 = 按存档找）")
    show_advanced: bpy.props.BoolProperty(name="高级", default=False)
    report: bpy.props.StringProperty()


class SBGM_OT_apply(bpy.types.Operator):
    bl_idname = "sb_gm.apply"
    bl_label = "换上游戏原始材质"
    bl_description = ("给选中的模型（导入的剑星 Eve PMX）加上游戏原始的完整材质；原来的材质节点保留，可切回 MMD 着色，"
                      "再导出 PMX 不受影响")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.sb_gm
        root, meshes = model_of(context)
        if not meshes:
            self.report({"ERROR"}, "先选中模型（骨架、网格或 MMD 模型的根）")
            return {"CANCELLED"}
        hint = " ".join(filter(None, (root.name if root else "", getattr(getattr(root, "mmd_root", None), "name", ""),
                                      getattr(getattr(root, "mmd_root", None), "name_e", ""))))
        try:
            report = core().apply(meshes, archive_of(s), params=params_of(s), hint=hint,
                                  blend=bpy.path.abspath(s.blend) if s.blend.strip() else "")
        except Exception as exc:
            s.report = "失败：%s" % exc
            self.report({"ERROR"}, s.report)
            return {"CANCELLED"}
        s["mode"] = 0                        # the new networks are active: show 游戏材质 without re-switching
        if report["home"] is None:
            s.report = "存档里没找到这个模型的高清 .blend（*_HQ.blend）"
            self.report({"ERROR"}, s.report)
            return {"CANCELLED"}
        homes = list(dict.fromkeys(report.get("homes", {}).values())) or [report["home"]]
        home = " + ".join(os.path.splitext(os.path.basename(h))[0] for h in homes)
        s.report = "%s：换了 %d 个材质，没找到 %d 个，错误 %d" % (
            home, len(report["upgraded"]), len(report["unmatched"]), len(report["errors"]))
        if report.get("hidable"):
            s.report += "；%d 个跟着滑块显示 / 隐藏" % len(report["hidable"])
        self.report({"WARNING"} if report["errors"] or report["unmatched"] else {"INFO"}, s.report)
        for line in report["unmatched"][:10]:
            print("[stellarblade_game_materials] 没找到:", line)
        for line in report["errors"][:10]:
            print("[stellarblade_game_materials]", line)
        return {"FINISHED"}


class SBGM_OT_reset(bpy.types.Operator):
    bl_idname = "sb_gm.reset"
    bl_label = "参数恢复默认"
    bl_description = "所有调整回到游戏原始值"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.sb_gm
        for name, value in core().DEFAULT_PARAMS.items():
            setattr(s, name, value)
        return {"FINISHED"}


class SBGM_OT_remove(bpy.types.Operator):
    bl_idname = "sb_gm.remove"
    bl_label = "去掉游戏材质"
    bl_description = "删掉本插件加的节点，恢复原来的材质"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.sb_gm
        _root, meshes = model_of(context)
        module = core()
        count = module.remove(module.hq_materials_of(meshes))
        s.report = "去掉了 %d 个材质里的游戏材质节点" % count
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class SBGM_OT_rescan(bpy.types.Operator):
    bl_idname = "sb_gm.rescan"
    bl_label = "重新扫描存档"
    bl_description = "存档里加了或改了高清 .blend 以后：重新读一遍每个 .blend 里有哪些材质"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = context.scene.sb_gm
        index = core().archive_index(archive_of(s), fresh=True)
        s.report = "存档里 %d 个高清 .blend，%d 个材质" % (len(index), sum(len(e["materials"]) for e in index.values()))
        self.report({"INFO"}, s.report)
        return {"FINISHED"}


class SBGM_PT_panel(bpy.types.Panel):
    bl_label = "剑星游戏材质"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        layout = self.layout
        s = context.scene.sb_gm
        root, meshes = model_of(context)
        if not meshes:
            layout.label(text="选中一个模型（导入的剑星 Eve PMX）", icon="INFO")
        else:
            count = sum(1 for o in meshes for slot in o.material_slots
                        if slot.material is not None and slot.material.get("sb_hq_base"))
            layout.label(text="%s：%d 个网格，%d 个材质已换" % (root.name if root else "?", len(meshes), count),
                         icon="OBJECT_DATA")
            layers = []
            for o in meshes:
                for slot in o.material_slots:
                    comment = getattr(getattr(slot.material, "mmd_material", None), "comment", "") or ""
                    found = re.search(r"layer\s*=\s*([^;\n]+)", comment)
                    if found and found.group(1).strip() not in layers:
                        layers.append(found.group(1).strip())
            if len(layers) > 1:
                layout.label(text="分层模型：%s（每层用自己的高清 .blend）" % " → ".join(layers), icon="RENDERLAYERS")
        layout.operator("sb_gm.apply", icon="MATERIAL")
        row = layout.row(align=True)
        row.prop(s, "mode", expand=True)

        box = layout.box()
        box.label(text="调整（实时生效，1.0 = 游戏原始值）", icon="MODIFIER")
        col = box.column(align=True)
        for name in PARAMS:
            col.prop(s, name, slider=True)
        box.operator("sb_gm.reset", icon="LOOP_BACK")

        layout.operator("sb_gm.remove", icon="TRASH")
        layout.prop(s, "show_advanced", icon="TRIA_DOWN" if s.show_advanced else "TRIA_RIGHT", emboss=False)
        if s.show_advanced:
            box = layout.box()
            box.prop(s, "archive")
            box.prop(s, "blend")
            box.operator("sb_gm.rescan", icon="FILE_REFRESH")
        if s.report:
            layout.label(text=s.report)


CLASSES = (SBGM_Settings, SBGM_OT_apply, SBGM_OT_reset, SBGM_OT_remove, SBGM_OT_rescan, SBGM_PT_panel)


HANDLERS = ((bpy.app.handlers.depsgraph_update_post, _on_depsgraph), (bpy.app.handlers.frame_change_pre, _on_frame))


def register():
    global _CORE
    _CORE = None                             # Reload Scripts / re-enable: pick up an edited core
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sb_gm = bpy.props.PointerProperty(type=SBGM_Settings)
    for handlers, fn in HANDLERS:
        for old in [h for h in handlers if getattr(h, "__name__", "") == fn.__name__ and
                    getattr(h, "__module__", "") == fn.__module__]:
            handlers.remove(old)             # a reload leaves the previous copy behind
        handlers.append(fn)


def unregister():
    for handlers, fn in HANDLERS:
        for old in [h for h in handlers if getattr(h, "__name__", "") == fn.__name__ and
                    getattr(h, "__module__", "") == fn.__module__]:
            handlers.remove(old)
    del bpy.types.Scene.sb_gm
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
