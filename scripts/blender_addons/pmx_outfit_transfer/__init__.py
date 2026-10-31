# -*- coding: utf-8 -*-
"""PMX Outfit Transfer - dress a PMX model in another PMX model's clothes, fitted to its body.

The clothes (chosen by material) come with their bones, rigid bodies, joints, materials and textures; they are
re-skinned to the target's skeleton and shrink-fitted to the target's nude body (core.py).  The two outfits'
rigid bodies never collide with each other.  The result is a new PMX next to the target (textures copied), imported
into the scene for picking the parts to keep.  Picking (parts.py): the materials left unticked go with the bones,
rigid bodies, joints, morph entries and textures only they used.

UI: 3D viewport sidebar > MMD tab > 换装（服装移植） and 挑零件.  Headless: cli.py, pick_cli.py.
"""
bl_info = {
    "name": "PMX Outfit Transfer",
    "author": "ripper_tpose",
    "version": (0, 4, 0),
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
from . import parts

importlib.reload(core)
importlib.reload(parts)


class POT_MaterialItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    faces: bpy.props.IntProperty()
    enabled: bpy.props.BoolProperty(default=True)


class POT_PartItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    faces: bpy.props.IntProperty()
    keep: bpy.props.BoolProperty(name="留下", default=True)


class POT_Settings(bpy.types.PropertyGroup):
    donor: bpy.props.StringProperty(name="衣服来自", subtype="FILE_PATH", description="提供衣服的 PMX")
    target: bpy.props.StringProperty(name="穿到", subtype="FILE_PATH", description="要穿衣服的 PMX（目标）")
    out: bpy.props.StringProperty(name="输出 PMX", subtype="FILE_PATH",
                                  description="留空：目标旁边新建「<目标>_穿<前缀>衣服」文件夹；不会覆盖已有文件")
    materials: bpy.props.CollectionProperty(type=POT_MaterialItem)
    active: bpy.props.IntProperty()
    donor_body: bpy.props.StringProperty(name="源的身体材质",
                                         description="衣服是在这个身体上做的（ROE：*_nk_body，衣服下那份）；几个材质用逗号隔开")
    donor_body_pmx: bpy.props.StringProperty(
        name="源的身体在另一个 PMX", subtype="FILE_PATH",
        description="衣服模型里没有衣服底下的身体时（星刃的套装、Vindictus 的连衣裙），填同一个角色的裸体 PMX："
                    "先把它摆成衣服模型的姿势，再拿它量衣服；「源的身体材质」填这个文件里的材质名，留空自动认")
    target_body: bpy.props.StringProperty(name="目标的裸体材质",
                                          description="衣服贴到这个身体上（ROE full：*_nk_body_nude）；几个材质用逗号隔开")
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
                                             description="full 版：拉「衣服非表示」时新衣服也一起藏起来；"
                                                         "目标是裸体模型（没有这个表情）时新建一个只管新衣服的「衣服非表示」")
    follow_body: bpy.props.BoolProperty(name="贴身部分跟着皮肤动", default=True,
                                        description="贴在目标皮肤上的部分（胸带、腰带、腿环……）改用皮肤在那里的权重，"
                                                    "跳舞时和皮肤一起动，皮肤基本不会从衣服里顶出来；挂在衣服物理骨上的份额不变，"
                                                    "目标的身体不动")
    follow_reach_cm: bpy.props.FloatProperty(name="跟随距离 cm", default=core.FOLLOW_REACH_CM, min=0.0, max=10.0,
                                             description="离皮肤不超过这个距离的衣服完全用皮肤的权重")
    follow_fade_cm: bpy.props.FloatProperty(name="过渡 cm", default=core.FOLLOW_FADE_CM, min=0.0, max=10.0,
                                            description="再往外这么远渐变回衣服自己的权重")
    min_gap_mm: bpy.props.FloatProperty(name="和皮肤的最小间隙 mm", default=core.MIN_GAP_MM, min=0.0, max=10.0,
                                        description="贴身衣服离目标皮肤不到这么远（或陷进去）就往外推，皮肤从衣服里顶出来的地方也推；"
                                                    "鞋不推。0 = 不推（和 0.3 之前一样）")
    import_result: bpy.props.BoolProperty(name="做完导入场景", default=True)
    report: bpy.props.StringProperty()

    parts_src: bpy.props.StringProperty(name="模型", subtype="FILE_PATH",
                                        description="要挑零件的 PMX（任何 PMX 都行）；留空用上面换装写出的那个")
    parts: bpy.props.CollectionProperty(type=POT_PartItem)
    parts_active: bpy.props.IntProperty()
    parts_filter: bpy.props.StringProperty(name="名字含",
                                           description="配合「勾上」「去掉」：名字里有这段字的零件一起改；留空 = 全部")
    parts_out: bpy.props.StringProperty(name="输出 PMX", subtype="FILE_PATH",
                                        description="留空：模型旁边「<模型>_挑零件.pmx」（已有就 _挑零件2、3…）；"
                                                    "不会覆盖已有文件；换了文件夹会把贴图拷过去")
    parts_bones: bpy.props.BoolProperty(name="骨骼、刚体、关节一起删", default=True,
                                        description="只挂在删掉的零件上的骨骼（MMD 标准骨除外）连同上面的刚体和关节一起删；"
                                                    "关掉就只删网格和表情项，和在 PMXEditor 里删材质一样")
    parts_empty_morphs: bpy.props.BoolProperty(name="删掉变空的表情", default=True,
                                               description="只管删掉的零件的表情（比如只藏武器的「武器非表示」）跟着删")
    parts_import: bpy.props.BoolProperty(name="做完导入场景", default=True,
                                         description="导入结果，场景里原来那个模型藏起来（大纲里点眼睛能再显示）")
    parts_split_mode: bpy.props.EnumProperty(
        name="拆法", default="bone",
        items=(("bone", "按挂的骨头", "连在一起的每一块按它主要挂的骨头归类，一根骨头一个零件（头饰、裙子、袖子……）"),
               ("island", "按连通块", "每块连在一起的布一个零件，小碎块按骨头合并")))
    parts_report: bpy.props.StringProperty()


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
            body_file = _abs(s.donor_body_pmx)
            body = pmx.load(body_file) if os.path.isfile(body_file) else None
            auto = set(core.auto_outfit_materials(D, body))
            s.materials.clear()
            for mt in D.materials:
                it = s.materials.add()
                it.name, it.faces, it.enabled = mt.name, mt.vertex_count // 3, mt.name in auto
            s.donor_body = core.auto_body(body if body is not None else D, nude=False) or ""
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
                                   follow_body=s.follow_body, follow_reach_cm=s.follow_reach_cm,
                                   follow_fade_cm=s.follow_fade_cm, donor_body_pmx=_abs(s.donor_body_pmx) or None,
                                   min_gap_mm=s.min_gap_mm, log=lambda t: (print(t), lines.append(t)))
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
        col.prop(s, "donor_body_pmx")
        col.prop(s, "target_body")
        col.prop(s, "prefix")
        box = layout.box()
        box.prop(s, "fit")
        row = box.row(align=True)
        row.prop(s, "near_cm")
        row.prop(s, "far_cm")
        box.prop(s, "align_rotation")
        box.prop(s, "follow_body")
        if s.follow_body:
            row = box.row(align=True)
            row.prop(s, "follow_reach_cm")
            row.prop(s, "follow_fade_cm")
        box.prop(s, "min_gap_mm")
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


# -- 挑零件 ----------------------------------------------------------------------------------------------------------------

def _parts_src(s):
    return _abs(s.parts_src) or _abs(s.out)


class POT_OT_parts_scan(bpy.types.Operator):
    bl_idname = "pmx_outfit.parts_scan"
    bl_label = "读取零件"
    bl_description = "列出模型的全部材质（一个材质 = 一个零件），默认都勾着 = 都留下"

    def execute(self, context):
        s = _settings(context)
        src = _parts_src(s)
        if not os.path.isfile(src):
            self.report({"ERROR"}, "找不到模型 PMX: %s" % src)
            return {"CANCELLED"}
        try:
            M = core.pmx_module().load(src)
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        s.parts_src = src
        s.parts.clear()
        for mt in M.materials:
            it = s.parts.add()
            it.name, it.faces, it.keep = mt.name, mt.vertex_count // 3, True
        s.parts_report = "%d 个零件；把不要的去掉勾" % len(M.materials)
        return {"FINISHED"}


class POT_OT_parts_mark(bpy.types.Operator):
    bl_idname = "pmx_outfit.parts_mark"
    bl_label = "勾上 / 去掉"
    bl_description = "名字里有「名字含」那段字的零件一起勾上（留下）或去掉；留空 = 全部"
    keep: bpy.props.BoolProperty()

    def execute(self, context):
        s = _settings(context)
        key = s.parts_filter.strip().lower()
        n = 0
        for it in s.parts:
            if not key or key in it.name.lower():
                it.keep = self.keep
                n += 1
        self.report({"INFO"}, "%s %d 个" % ("勾上" if self.keep else "去掉", n))
        return {"FINISHED"}


class POT_OT_parts_from_selection(bpy.types.Operator):
    bl_idname = "pmx_outfit.parts_from_selection"
    bl_label = "去掉选中的面所在的零件"
    bl_description = "在 3D 视图里选中模型网格上的面（编辑模式，L 选一整块），这些面所在的材质在列表里去掉勾"

    def execute(self, context):
        s = _settings(context)
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "先选中模型的网格，进编辑模式选面")
            return {"CANCELLED"}
        if obj.mode == "EDIT":
            obj.update_from_editmode()
        slots = {p.material_index for p in obj.data.polygons if p.select}
        if not slots:
            self.report({"ERROR"}, "网格上没有选中的面")
            return {"CANCELLED"}
        names = set()
        for k in slots:
            mat = obj.material_slots[k].material if k < len(obj.material_slots) else None
            if mat is not None:
                mmd = getattr(mat, "mmd_material", None)
                names.add(mmd.name_j if mmd is not None and mmd.name_j else mat.name)
        hit = [it for it in s.parts if it.name in names]
        if not hit:
            self.report({"ERROR"}, "选中的面不在列表这个模型里（%s）" % "、".join(sorted(names))[:200])
            return {"CANCELLED"}
        for it in hit:
            it.keep = False
        self.report({"INFO"}, "去掉 %d 个：%s" % (len(hit), "、".join(it.name for it in hit))[:300])
        return {"FINISHED"}


def _import_replacing(context, path, old_name):
    """Import a written PMX and hide the scene's models that came from the one it was made from."""
    if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
        return False
    old_roots = [o for o in context.scene.objects if getattr(o, "mmd_type", "") == "ROOT" and o.mmd_root.name == old_name]
    bpy.ops.mmd_tools.import_model(filepath=path, scale=0.08, types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
    for root in old_roots:
        for o in [root] + list(root.children_recursive):
            try:
                o.hide_set(True)
            except RuntimeError:
                pass
    return bool(old_roots)


class POT_OT_parts_split(bpy.types.Operator):
    bl_idname = "pmx_outfit.parts_split"
    bl_label = "拆开选中的这个零件"
    bl_description = ("列表里选中（高亮）的那个零件按「拆法」拆成几块，写出 <模型>_拆开.pmx 并导入，列表换成拆开后的；"
                      "比如 ROE 的衣服整套在一两个材质里，拆开才能只留头饰")

    def execute(self, context):
        s = _settings(context)
        src = _parts_src(s)
        if not (len(s.parts) and 0 <= s.parts_active < len(s.parts)):
            self.report({"ERROR"}, "先「读取零件」，在列表里点一下要拆的那个")
            return {"CANCELLED"}
        name = s.parts[s.parts_active].name
        keep = {it.name: it.keep for it in s.parts}
        try:
            report = parts.split_parts(src, None, names=[name], mode=s.parts_split_mode, log=print)
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        out, pieces = report["out"], report["parts"][name]
        M = core.pmx_module().load(out)
        s.parts.clear()
        for mt in M.materials:
            it = s.parts.add()
            it.name, it.faces = mt.name, mt.vertex_count // 3
            it.keep = keep.get(mt.name, keep.get(name, True))
        s.parts_src = out
        s.parts_report = "%s 拆成 %d 块，写出 %s" % (name, len(pieces), os.path.basename(out))
        if _import_replacing(context, out, report["source_name"]):
            s.parts_report += "；场景里原来的模型藏起来了"
        self.report({"INFO"}, s.parts_report)
        return {"FINISHED"}


class POT_OT_parts_remove(bpy.types.Operator):
    bl_idname = "pmx_outfit.parts_remove"
    bl_label = "删掉没勾的零件"
    bl_description = ("没勾的材质连同只给它们用的骨骼、刚体、关节、表情项、贴图一起删，写出新的 PMX（原文件不动）；"
                      "full 版删了贴身那份身体，裸体那份自动改成默认显示")

    def execute(self, context):
        s = _settings(context)
        src = _parts_src(s)
        if not os.path.isfile(src):
            self.report({"ERROR"}, "找不到模型 PMX: %s" % src)
            return {"CANCELLED"}
        if not len(s.parts):
            self.report({"ERROR"}, "先点「读取零件」")
            return {"CANCELLED"}
        remove = [it.name for it in s.parts if not it.keep]
        if not remove:
            self.report({"ERROR"}, "都勾着，没有要删的")
            return {"CANCELLED"}
        lines = []
        try:
            report = parts.pick_parts(src, _abs(s.parts_out) or None, remove=remove, bones=s.parts_bones,
                                      empty_morphs=s.parts_empty_morphs, log=lambda t: (print(t), lines.append(t)))
        except Exception as exc:                                    # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            s.parts_report = "失败: %s" % exc
            return {"CANCELLED"}
        out = report["out"]
        s.parts_report = "写出 %s：删了 %d 个零件、%d 根骨、%d 刚体、%d 关节、%d 个表情%s" % (
            os.path.basename(out), len(report["removed_materials"]), len(report["removed_bones"]),
            len(report["removed_rigids"]), len(report["removed_joints"]), len(report["removed_morphs"]),
            "".join("；" + t for t in report["swaps"]))
        if s.parts_import:
            if not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "import_model"):
                self.report({"WARNING"}, "mmd_tools 没启用，结果没导入场景")
            elif _import_replacing(context, out, report["source_name"]):
                s.parts_report += "；场景里原来的模型藏起来了（大纲里点眼睛能再显示）"
        s.parts_src = out                                         # the list now shows the new model: pick again
        for i in reversed(range(len(s.parts))):
            if not s.parts[i].keep:
                s.parts.remove(i)
        self.report({"INFO"}, s.parts_report)
        return {"FINISHED"}


class POT_UL_parts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "keep", text="")
        row.label(text="%s  (%d 面)" % (item.name, item.faces))


class POT_PT_parts(bpy.types.Panel):
    bl_label = "挑零件（删掉不要的零件）"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        layout.prop(s, "parts_src")
        layout.operator("pmx_outfit.parts_scan", icon="VIEWZOOM")
        if len(s.parts):
            layout.template_list("POT_UL_parts", "", s, "parts", s, "parts_active", rows=8)
            row = layout.row(align=True)
            row.prop(s, "parts_filter")
            row.operator("pmx_outfit.parts_mark", text="勾上").keep = True
            row.operator("pmx_outfit.parts_mark", text="去掉").keep = False
            layout.operator("pmx_outfit.parts_from_selection", icon="RESTRICT_SELECT_OFF")
            row = layout.row(align=True)
            row.prop(s, "parts_split_mode", text="")
            row.operator("pmx_outfit.parts_split", icon="MOD_EXPLODE")
            n_off = sum(1 for it in s.parts if not it.keep)
            layout.label(text="勾着的留下：%d 个；没勾的删掉：%d 个" % (len(s.parts) - n_off, n_off))
        layout.prop(s, "parts_out")
        box = layout.box()
        box.prop(s, "parts_bones")
        box.prop(s, "parts_empty_morphs")
        box.prop(s, "parts_import")
        layout.operator("pmx_outfit.parts_remove", icon="TRASH")
        if s.parts_report:
            for line in s.parts_report.split("；"):
                layout.label(text=line)


CLASSES = (POT_MaterialItem, POT_PartItem, POT_Settings, POT_OT_scan, POT_OT_transfer, POT_UL_materials, POT_PT_panel,
           POT_OT_parts_scan, POT_OT_parts_mark, POT_OT_parts_from_selection, POT_OT_parts_split, POT_OT_parts_remove,
           POT_UL_parts, POT_PT_parts)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pmx_outfit = bpy.props.PointerProperty(type=POT_Settings)


def unregister():
    del bpy.types.Scene.pmx_outfit
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
