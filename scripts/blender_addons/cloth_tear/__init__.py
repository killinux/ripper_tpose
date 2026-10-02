# -*- coding: utf-8 -*-
"""布料撕裂 Cloth Tear - 把 B 站「blender-布料模拟撕裂效果」（峰峰居士，BV1Zk4y1x7Eo）的做法做成一键操作：
两个布料修改器的混合，中间一个几何节点按边折痕拆开裂缝、按帧把固定组从上往下松开，最后再合上没撕开的缝。

界面：3D 视图侧栏（N）> 布料撕裂。原理见 core.py 开头和 docs/cloth-tear-guide.md。
"""
bl_info = {
    "name": "布料撕裂 Cloth Tear",
    "author": "ripper_tpose",
    "version": (1, 3, 0),
    "blender": (3, 6, 0),
    "location": "3D 视图 > 侧栏 > 布料撕裂",
    "description": "一键布料撕裂：裂缝（边折痕）+ 几何节点按帧松开固定组 + 第二个布料修改器，附示例场景",
    "category": "Physics",
}

import importlib

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

from . import core

importlib.reload(core)

AXIS_ITEMS = (
    ("UV_V", "UV 的 V（上下）", "和视频一样用 UV 的 Y：V 大的一边先松开"),
    ("UV_U", "UV 的 U（左右）", "U 大的一边先松开"),
    ("Z", "物体 Z", "物体坐标 Z 大的一边先松开"),
    ("Y", "物体 Y", "物体坐标 Y 大的一边先松开"),
    ("X", "物体 X", "物体坐标 X 大的一边先松开"),
)


def _fast_update(self, context):
    for name, steps in core.set_fast(self.fast, context.scene):
        print("[布料撕裂] 快速预览%s：%s 布料 2 质量步数 %d" % ("开" if self.fast else "关", name, steps))


class CT_Settings(bpy.types.PropertyGroup):
    axis: EnumProperty(name="松开方向", items=AXIS_ITEMS, default="UV_V")
    invert: BoolProperty(name="反过来", description="从另一边开始松开（例如从下往上撕）", default=False)
    start: FloatProperty(name="开始帧", default=120.0, description="这一帧之前碎片全部跟着完整的布走")
    end: FloatProperty(name="结束帧", default=170.0, description="到这一帧所有碎片都松开了")
    width: FloatProperty(name="过渡宽度", default=0.05, min=0.001, max=1.0,
                         description="松开带的宽度（占整块布的比例），越大撕得越慢越柔和")
    merge: FloatProperty(name="合并距离", default=0.001, min=0.0, max=0.1, unit="LENGTH", precision=4,
                         description="裂缝两边离得比这还近就合在一起，没撕开的缝不会露出来")
    cuts: IntProperty(name="细分刀数", default=20, min=1, max=100)
    poke: BoolProperty(name="戳孔面", default=True, description="每格拆成 4 个三角（视频里的 Ctrl+F），撕口更碎")
    cracks: IntProperty(name="裂缝条数", default=4, min=1, max=50)
    seed: IntProperty(name="随机种子", default=1)
    jitter: FloatProperty(name="锯齿程度", default=0.6, min=0.0, max=3.0)
    partial: BoolProperty(name="不贯穿", default=False,
                          description="从布边撕进去一段就停（撕出裂口和毛边）；关掉时从布边到布边，会撕成几块")
    loops: BoolProperty(name="切开套圈", default=True,
                        description="生成裂缝后再看每块布：套成圈的（腰带、袖子、筒裙，身体从圈里穿过去）补最少的裂缝把它切开，"
                                    "不然撕完还卡在身上。只想撕出口子、不想让衣服掉下来时关掉")
    keep_mode: EnumProperty(name="撕开后仍固定", default="SAME", items=(
        ("SAME", "同布料固定组", "和视频一样：布料 1 的固定组撕开后也一直挂着（例如两个钩挂角）"),
        ("NONE", "无（全部掉落）", "撕开的部分全部松开，衣服用「跟随身体」时选这个就是整件撕掉"),
        ("GROUP", "自选顶点组", "只有这个顶点组撕开后还挂在身上（例如领口、腰带）"),
    ))
    keep_group: bpy.props.StringProperty(name="保留组", description="撕开后仍固定的顶点组")
    force: FloatProperty(name="推力强度", default=25.0, min=0.0, soft_max=200.0,
                         description="把撕开的碎片往外推的力。配合「按尺寸调快」时和模型大小无关，25 左右；"
                                     "碎片贴在身上不动就加大，炸飞就减小")
    auto_speed: BoolProperty(name="按尺寸调快", default=True,
                             description="模型比真人大（PMX 原尺寸约 18 高）时重力看着像慢动作：布料 2 的速度取 "
                                         "√(身高 / 1.7)，质量步数跟着调高")
    fast: BoolProperty(name="快速预览", default=False, update=_fast_update,
                       description="布料 2 的质量步数减半（速度 × 2.5，平时 × 5），烘焙快将近一倍，先看撕的时机和样子；"
                                   "碎片可能挂在手指上滑不下来，定稿前关掉再清除烘焙、烘焙一次")


def _obj(context):
    obj = context.active_object
    return obj if obj is not None and obj.type == "MESH" else None


def _targets(context):
    """选中的网格（含活动物体）；什么都没选就用活动物体。"""
    obj = _obj(context)
    picked = [o for o in context.selected_objects if o.type == "MESH"]
    if obj is not None and obj not in picked:
        picked.insert(0, obj)
    return picked


class CT_OT_demo(bpy.types.Operator):
    bl_idname = "cloth_tear.demo"
    bl_label = "一键创建撕裂示例"
    bl_description = "照视频搭一个完整场景：平面 + 两个钩挂点 + 拉扯动画 + 布料 + 裂缝 + 撕裂设置，播放或烘焙即可"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.cloth_tear
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            obj, notes = core.build_demo(context, cuts=s.cuts, cracks=s.cracks, seed=s.seed)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for o in context.selected_objects:
            o.select_set(o is obj)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, "示例已建好：从第 1 帧播放，或点「烘焙」后拖时间轴（%s）" % notes[-1])
        return {"FINISHED"}


class CT_OT_prepare(bpy.types.Operator):
    bl_idname = "cloth_tear.prepare"
    bl_label = "细分网格"
    bl_description = "按设置的刀数细分整个网格，可选戳孔面（会改网格，已有布料缓存要重新烘焙）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        s = context.scene.cloth_tear
        core.subdivide_poke(_obj(context), cuts=s.cuts, poke=s.poke)
        return {"FINISHED"}


class CT_OT_hook(bpy.types.Operator):
    bl_idname = "cloth_tear.hook"
    bl_label = "选中顶点钩挂 + 固定"
    bl_description = "编辑模式里选中的每个顶点各挂一个空物体（Ctrl+H），并加进固定组 Group，之后给空物体打关键帧就能拉扯"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        obj = _obj(context)
        was_edit = obj.mode == "EDIT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        picked = [v.index for v in obj.data.vertices if v.select]
        if not picked or len(picked) > 16:
            if was_edit:
                bpy.ops.object.mode_set(mode="EDIT")
            self.report({"ERROR"}, "在编辑模式选 1–16 个顶点（例如布的两个角）")
            return {"CANCELLED"}
        core.pin_vertices(obj, picked, "Group")
        for i in picked:
            core.hook_vertex(obj, i, "CT_Hook_%d" % i)
        cloth = core.source_cloth(obj)
        if cloth is not None and not cloth.settings.vertex_group_mass:
            cloth.settings.vertex_group_mass = "Group"
        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, "%d 个顶点已钩挂并加入固定组 Group" % len(picked))
        return {"FINISHED"}


class CT_OT_follow(bpy.types.Operator):
    bl_idname = "cloth_tear.follow"
    bl_label = "衣服跟随身体（撕衣服用）"
    bl_description = ("选中的衣服（可多选）：布料 1 全部固定，撕开前完全跟着身体动画走；和衣服重叠的身体网格加碰撞"
                      "（项链、耳环、臂甲这类饰品不加，免得把碎片挂住），脚底加地面碰撞，撕下来的布落在身上和地上。"
                      "撕裂设置的「撕开后仍固定」会改成「无」")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        obj = _obj(context)
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        garments = [o for o in context.selected_objects if o.type == "MESH"] or [obj]
        try:
            notes = core.follow_body(garments)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if context.scene.cloth_tear.keep_mode == "SAME":
            context.scene.cloth_tear.keep_mode = "NONE"
        for line in notes:
            print("[布料撕裂]", line)
        self.report({"INFO"}, "；".join(notes))
        return {"FINISHED"}


class CT_OT_mark(bpy.types.Operator):
    bl_idname = "cloth_tear.mark"
    bl_label = "设为裂缝"
    bl_description = "编辑模式选中的边设为裂缝（边折痕 = 1，等于视频里 Shift+E 拉到 1）"
    bl_options = {"REGISTER", "UNDO"}
    value: FloatProperty(default=1.0)
    only_selected: BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        obj = _obj(context)
        if self.only_selected and obj.mode != "EDIT":
            self.report({"ERROR"}, "先进编辑模式（Tab），用边选择模式选好裂缝的边")
            return {"CANCELLED"}
        n = core.mark_seams(obj, self.value, self.only_selected)
        self.report({"INFO"}, "%d 条边%s" % (n, "设为裂缝" if self.value > 0 else "取消裂缝"))
        return {"FINISHED"}


class CT_OT_cracks(bpy.types.Operator):
    bl_idname = "cloth_tear.cracks"
    bl_label = "随机生成裂缝"
    bl_description = ("在布边上随机取点，连出锯齿状的裂缝（加在已有裂缝上）。选中几件衣服就每件各生成这么多条，"
                      "每件的随机种子依次加 1。打开「切开套圈」时，套成圈的布再补裂缝切开")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        s, done = context.scene.cloth_tear, []
        for i, obj in enumerate(_targets(context)):
            try:
                n = core.random_cracks(obj, count=s.cracks, seed=s.seed + i, jitter=s.jitter, partial=s.partial)
                rings = core.cut_loops(obj, seed=s.seed + i, jitter=s.jitter) if s.loops else 0
            except Exception as exc:
                self.report({"ERROR"}, "%s：%s" % (obj.name, exc))
                return {"CANCELLED"}
            done.append("%s %d 条%s（共 %d 条边）" % (obj.name, n, "、切开套圈 %d 处" % rings if rings else "",
                                                 core.seam_count(obj)))
        self.report({"INFO"}, "生成了裂缝：" + "；".join(done))
        return {"FINISHED"}


class CT_OT_loops(bpy.types.Operator):
    bl_idname = "cloth_tear.loops"
    bl_label = "只切开套圈"
    bl_description = ("不加随机裂缝，只检查每块布：套成圈的（腰带、袖子、筒裙）补最少的裂缝把圈切开，"
                      "已有的裂缝算已经撕开。手动画的裂缝也能用。选中几件衣服就每件都查")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        s, done = context.scene.cloth_tear, []
        for i, obj in enumerate(_targets(context)):
            rings = core.cut_loops(obj, seed=s.seed + i, jitter=s.jitter)
            done.append("%s %d 处" % (obj.name, rings))
        self.report({"INFO"}, "切开套圈：" + "；".join(done) + "（0 处 = 没有套成圈的布，或已经切开了）")
        return {"FINISHED"}


class CT_OT_setup(bpy.types.Operator):
    bl_idname = "cloth_tear.setup"
    bl_label = "生成 / 更新撕裂"
    bl_description = ("在已有布料修改器后面加「拆缝几何节点 → 第二个布料 → 合缝几何节点」，再点一次就是按当前设置更新。"
                      "选中几件衣服就每件都生成")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def execute(self, context):
        s, obj = context.scene.cloth_tear, _obj(context)
        mode = obj.mode
        if mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        keep = {"SAME": None, "NONE": ""}.get(s.keep_mode, s.keep_group)
        targets, done = _targets(context), []
        bad = ["%s 没有布料修改器" % o.name for o in targets if core.source_cloth(o) is None]
        bad += ["%s 还没有裂缝" % o.name for o in targets if core.seam_count(o) == 0]
        if bad:                                  # 一件都不改，免得选多了只改了一半
            if mode == "EDIT":
                bpy.ops.object.mode_set(mode="EDIT")
            self.report({"ERROR"}, "；".join(bad) + "（只选要撕的衣服）")
            return {"CANCELLED"}
        try:
            for target in targets:
                notes = core.setup_tear(target, s.axis, s.invert, s.start, s.end, s.width, s.merge,
                                        keep_group=keep)
                for line in notes:
                    print("[布料撕裂]", target.name, line)
                done.append("%s（裂缝 %d 条边）" % (target.name, core.seam_count(target)))
        except Exception as exc:
            self.report({"ERROR"}, "%s：%s" % (target.name, exc))
            return {"CANCELLED"}
        finally:
            if mode == "EDIT":
                bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, "%s：第 %g–%g 帧从%s往%s松开" % ("、".join(done), s.start, s.end,
                                                               "下" if s.invert else "上", "上" if s.invert else "下"))
        return {"FINISHED"}


class CT_OT_force(bpy.types.Operator):
    bl_idname = "cloth_tear.force"
    bl_label = "加推力场"
    bl_description = ("身体不动时撕开的碎片只会贴在身上：放一个从身体中轴水平往外推的力场（范围是衣服那一段高度），"
                      "只推撕裂用的布料 2，从撕裂开始帧推到结束帧后 10 帧。勾「按尺寸调快」时同时按身高调快布料 2。"
                      "再点一次就是更新")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(core.tear_modifiers(o)[1] for o in _targets(context))

    def execute(self, context):
        s = context.scene.cloth_tear
        garments = [o for o in _targets(context) if core.tear_modifiers(o)[1] is not None]
        notes = core.add_tear_force(garments, strength=s.force, start=s.start, end=s.end + 10)
        if s.auto_speed:
            speed, quality, height = core.tear_speed(garments, fast=s.fast)
            core.set_tear_speed(garments, speed, quality, exact=s.fast)
            notes.append("身高 %.1f → 布料 2 速度 %g、质量步数 %s %d%s" % (height, speed, "=" if s.fast else "≥", quality,
                                                                      "（快速预览）" if s.fast else ""))
        for line in notes:
            print("[布料撕裂]", line)
        self.report({"INFO"}, "；".join(notes) + "（改完要清除烘焙再烘焙）")
        return {"FINISHED"}


class CT_OT_force_remove(bpy.types.Operator):
    bl_idname = "cloth_tear.force_remove"
    bl_label = "移除推力场"
    bl_description = "删掉推力场和它的两个集合，布料和刚体世界恢复受全部力场影响（布料 2 的速度不变）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bpy.data.objects.get(core.FIELD) is not None

    def execute(self, context):
        removed = core.remove_tear_force()
        self.report({"INFO"}, "已移除：%s" % "、".join(removed))
        return {"FINISHED"}


class CT_OT_remove(bpy.types.Operator):
    bl_idname = "cloth_tear.remove"
    bl_label = "移除撕裂设置"
    bl_description = "删掉本插件加的三个修改器（原布料、钩挂、裂缝都保留）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None and any(core.tear_modifiers(_obj(context)))

    def execute(self, context):
        removed = core.remove_tear(_obj(context))
        self.report({"INFO"}, "已移除：%s" % "、".join(removed))
        return {"FINISHED"}


class CT_OT_cleanup(bpy.types.Operator):
    bl_idname = "cloth_tear.cleanup"
    bl_label = "全部清理"
    bl_description = ("删掉本插件在这个场景里加的所有东西，回到用插件之前：每件衣服的撕裂修改器、跟随身体的布料 1、"
                      "CT_ 顶点组和裂缝，身体上的碰撞、地面、推力场。钩挂和空物体不动。可以 Ctrl+Z 撤销")
    bl_options = {"REGISTER", "UNDO"}
    cracks: BoolProperty(name="也清除裂缝", default=True,
                         description="关掉时裂缝（边折痕）留着，之后可以直接重新「生成 / 更新撕裂」")

    @classmethod
    def poll(cls, context):
        return bool(core.tear_garments(context.scene)) or any(
            bpy.data.objects.get(n) is not None for n in (core.FLOOR, core.FIELD))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="删掉本插件在这个场景里加的所有东西：")
        col.label(text="  " + ("、".join(o.name for o in core.tear_garments(context.scene)) or "（没有衣服）"))
        col.prop(self, "cracks")

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        done = core.cleanup_all(clear_cracks=self.cracks)
        for line in done:
            print("[布料撕裂] 清理", line)
        self.report({"INFO"}, "已清理：" + ("；".join(done) if done else "没有要清理的"))
        return {"FINISHED"}


class CT_OT_bake(bpy.types.Operator):
    bl_idname = "cloth_tear.bake"
    bl_label = "烘焙"
    bl_description = ("烘焙场景里所有物理缓存（两个布料按顺序一起算），算完才返回，给脚本和后台用；"
                      "面板上的按钮是 Blender 自带的烘焙，有进度条")
    free: BoolProperty(default=False)

    def execute(self, context):
        if self.free:
            bpy.ops.ptcache.free_bake_all()
            self.report({"INFO"}, "已清除烘焙")
        else:
            context.scene.frame_set(context.scene.frame_start)
            bpy.ops.ptcache.bake_all(bake=True)
            self.report({"INFO"}, "烘焙完成")
        return {"FINISHED"}


class CT_PT_panel(bpy.types.Panel):
    bl_label = "布料撕裂"
    bl_idname = "CT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "布料撕裂"

    def draw(self, context):
        layout, s, obj = self.layout, context.scene.cloth_tear, _obj(context)

        box = layout.box()
        box.label(text="一键示例", icon="MOD_CLOTH")
        row = box.row(align=True)
        row.prop(s, "cuts"); row.prop(s, "seed")
        box.operator("cloth_tear.demo", icon="PLAY")

        box = layout.box()
        box.label(text="1. 网格和固定", icon="MESH_GRID")
        row = box.row(align=True)
        row.prop(s, "cuts"); row.prop(s, "poke", toggle=True)
        box.operator("cloth_tear.prepare", icon="MOD_SUBSURF")
        box.operator("cloth_tear.hook", icon="HOOK")
        box.operator("cloth_tear.follow", icon="ARMATURE_DATA")

        box = layout.box()
        box.label(text="2. 裂缝（当前 %d 条边）" % core.seam_count(obj) if obj else "2. 裂缝", icon="MOD_EDGESPLIT")
        row = box.row(align=True)
        op = row.operator("cloth_tear.mark", text="选中边设为裂缝"); op.value, op.only_selected = 1.0, True
        op = row.operator("cloth_tear.mark", text="取消选中"); op.value, op.only_selected = 0.0, True
        op = box.operator("cloth_tear.mark", text="清除全部裂缝", icon="X"); op.value, op.only_selected = 0.0, False
        row = box.row(align=True)
        row.prop(s, "cracks"); row.prop(s, "jitter")
        row = box.row(align=True)
        row.prop(s, "seed"); row.prop(s, "partial", toggle=True); row.prop(s, "loops", toggle=True)
        row = box.row(align=True)
        row.operator("cloth_tear.cracks", icon="FORCE_TURBULENCE")
        row.operator("cloth_tear.loops", icon="MOD_EDGESPLIT")

        box = layout.box()
        box.label(text="3. 撕裂", icon="MOD_PHYSICS")
        box.prop(s, "axis")
        box.prop(s, "invert")
        box.prop(s, "keep_mode")
        if s.keep_mode == "GROUP" and obj is not None:
            box.prop_search(s, "keep_group", obj, "vertex_groups", text="保留组")
        row = box.row(align=True)
        row.prop(s, "start"); row.prop(s, "end")
        row = box.row(align=True)
        row.prop(s, "width"); row.prop(s, "merge")
        box.operator("cloth_tear.setup", icon="MOD_CLOTH")
        if obj is not None:
            split_mod, cloth2, merge_mod = core.tear_modifiers(obj)
            if split_mod is not None and split_mod.node_group is not None:
                col = box.column(align=True)
                col.label(text="已生成，可直接调（不用重新生成）：")
                tree = split_mod.node_group
                for name in ("开始帧", "结束帧", "过渡宽度"):
                    try:
                        col.prop(split_mod, '["%s"]' % core.socket_id(tree, name), text=name)
                    except StopIteration:
                        pass
                if merge_mod is not None and merge_mod.node_group is not None:
                    try:
                        col.prop(merge_mod, '["%s"]' % core.socket_id(merge_mod.node_group, "合并距离"),
                                 text="合并距离")
                    except StopIteration:
                        pass
                if obj.get(core.CLOTH1_OFF):
                    col.label(text="布料 1 每个点都固定，只当模板，不参与计算", icon="INFO")
            box.operator("cloth_tear.remove", icon="TRASH")

        box = layout.box()
        box.label(text="4. 推力（身体不动时用）", icon="FORCE_FORCE")
        row = box.row(align=True)
        row.prop(s, "force"); row.prop(s, "auto_speed", toggle=True)
        row = box.row(align=True)
        row.operator("cloth_tear.force", icon="FORCE_FORCE")
        row.operator("cloth_tear.force_remove", text="", icon="TRASH")
        cloth2 = core.tear_modifiers(obj)[1] if obj is not None else None
        if cloth2 is not None:
            row = box.row(align=True)
            row.prop(cloth2.settings, "time_scale", text="布料 2 速度")
            row.prop(cloth2.settings, "quality", text="质量步数")

        box = layout.box()
        box.label(text="5. 烘焙", icon="FILE_CACHE")
        box.prop(s, "fast", toggle=True, icon="FF")
        if s.fast:
            box.label(text="步数减半：碎片可能挂在手指上，定稿前关掉再烘", icon="INFO")
        row = box.row(align=True)
        # Blender 自带的「烘焙所有动力学解算结果」：从按钮调用是后台任务，状态栏有进度条，Esc 取消
        row.operator("ptcache.bake_all", text="烘焙", icon="REC").bake = True
        row.operator("ptcache.free_bake_all", text="清除烘焙", icon="TRASH")

        box = layout.box()
        box.label(text="6. 清理", icon="BRUSH_DATA")
        box.operator("cloth_tear.cleanup", icon="TRASH")


CLASSES = (CT_Settings, CT_OT_demo, CT_OT_prepare, CT_OT_hook, CT_OT_follow, CT_OT_mark, CT_OT_cracks, CT_OT_loops,
           CT_OT_setup, CT_OT_force, CT_OT_force_remove, CT_OT_remove, CT_OT_cleanup, CT_OT_bake, CT_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cloth_tear = PointerProperty(type=CT_Settings)


def unregister():
    del bpy.types.Scene.cloth_tear
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
