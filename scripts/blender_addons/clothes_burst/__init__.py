# -*- coding: utf-8 -*-
"""爆衣 Clothes Burst - 选中衣服（或衣服的一部分），一键让它在指定的帧炸开、碎片飞出去再落地。

用布料撕裂插件（cloth_tear，同一个仓库）的撕裂做法：裂缝 + 两个布料修改器 + 几何节点按帧松开。
爆衣在上面加：范围里随机裂缝、几帧内全部松开、按「重力的倍数」给的短促推力（每件衣服自动换算）。
界面：3D 视图侧栏（N）> 爆衣。原理见 burst.py 开头和 docs/clothes-burst-guide.md。
"""
bl_info = {
    "name": "爆衣 Clothes Burst",
    "author": "ripper_tpose",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "3D 视图 > 侧栏 > 爆衣",
    "description": "选中衣服或衣服的一部分，一键在指定的帧炸开（需要同时装布料撕裂插件 cloth_tear）",
    "category": "Physics",
}

import importlib

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

try:
    from . import burst
    importlib.reload(burst)
    ct = burst.ct
    MISSING = ""
except ImportError as exc:                    # 没装布料撕裂插件
    burst = ct = None
    MISSING = str(exc)

D = burst.DEFAULTS if burst is not None else {}
TAG = "[爆衣]"


def _fast_update(self, context):
    if ct is None:
        return
    names = {g.name for g in burst.burst_garments(context.scene)}
    for g in context.scene.objects:
        c2 = g.modifiers.get(ct.MOD_CLOTH) if g.name in names else None
        if c2 is not None:
            c2.settings.quality = ct.steps_for(c2.settings.time_scale, self.fast)


class CB_Settings(bpy.types.PropertyGroup):
    frame: IntProperty(name="爆开帧", default=D.get("frame", 30), min=1,
                       description="这一帧开始炸开；之前衣服完整地跟着身体动")
    duration: IntProperty(name="松开用几帧", default=D.get("duration", 3), min=1, max=120,
                          description="几帧之内全部裂缝松开：小 = 一下子炸开，大 = 从上往下很快地撕开")
    accel: FloatProperty(name="推力（× 重力）", default=D.get("accel", 0.6), min=0.0, soft_max=5.0, precision=2,
                         description="把碎片推出去的力，按重力的倍数算：每件衣服按自己的面积和顶点数自动换算，"
                                     "大块布和细布条推得一样远。0 = 不推，只是散开掉下去；越大飞得越远")
    push_frames: IntProperty(name="推几帧", default=D.get("push_frames", 10), min=1, max=120,
                             description="推力从爆开帧开始持续几帧，越长飞得越远")
    shape: EnumProperty(name="推的方向", default=D.get("shape", "LINE"), items=(
        ("LINE", "水平往外", "从身体中轴往四周水平推（不往上飞）"),
        ("POINT", "四面八方", "从中心往所有方向推：上半身的碎片会往上飞"),
    ))
    through: IntProperty(name="贯穿裂缝", default=D.get("through", 10), min=0, max=200,
                         description="从布边到布边的裂缝条数（每件衣服），越多碎片越多越碎")
    partial: IntProperty(name="不贯穿裂缝", default=D.get("partial", 10), min=0, max=200,
                         description="从布边撕进去一段就停的裂缝条数（每件衣服），撕出裂口和毛边")
    jitter: FloatProperty(name="锯齿程度", default=D.get("jitter", 0.6), min=0.0, max=3.0,
                          description="裂缝弯弯曲曲的程度")
    seed: IntProperty(name="随机种子", default=D.get("seed", 1), description="换一个数就换一种碎法")
    loops: BoolProperty(name="切开套圈", default=D.get("loops", True),
                        description="套成圈的布（腰带、袖子、筒裙）再补一条裂缝切开，不然碎片卡在身上掉不下来")
    regen: BoolProperty(name="重新生成裂缝", default=D.get("regen", True),
                        description="每次「一键爆衣」都清掉旧裂缝、重新随机生成；关掉时保留已有的裂缝"
                                    "（例如用布料撕裂插件手画的），只补范围边界")
    invert: BoolProperty(name="从下往上", default=D.get("invert", False),
                         description="「松开用几帧」大于几帧时看得出来：默认从上往下松开")
    width: FloatProperty(name="过渡宽度", default=D.get("width", 0.08), min=0.001, max=1.0,
                         description="松开带的宽度（占整件衣服高度的比例）")
    merge: FloatProperty(name="合并距离", default=D.get("merge", 0.0005), min=0.0, max=0.1, precision=4,
                         unit="LENGTH", description="还没松开的裂缝两边合在一起，不露缝")
    fast: BoolProperty(name="快速预览", default=D.get("fast", False), update=_fast_update,
                       description="布料 2 的质量步数减半，烘焙快将近一倍，先看效果；定稿前关掉，清除烘焙再烘")
    show_more: BoolProperty(name="更多设置", default=False)

    def opts(self):
        return {k: getattr(self, k) for k in D}


def _garment_candidates(context):
    """物体模式：选中的网格，活动物体排第一（没选中的活动物体不算，免得把身体也炸了）。"""
    act = context.active_object
    picked = [o for o in context.selected_objects if o.type == "MESH" and (ct is None or o.name != ct.FLOOR)]
    if act in picked:
        picked.remove(act)
        picked.insert(0, act)
    return picked


class CB_OT_burst(bpy.types.Operator):
    bl_idname = "clothes_burst.burst"
    bl_label = "一键爆衣"
    bl_description = ("物体模式：选中的衣服整件爆开（可多选）。编辑模式：只爆开选中的面，其余留在身上。"
                      "裂缝、松开、推力、碰撞、地面一次设好；再点一次就按新的设置重做。之后点「烘焙」")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if burst is None:
            return False
        if context.mode == "EDIT_MESH":
            return True
        return context.mode == "OBJECT" and bool(_garment_candidates(context))

    def execute(self, context):
        s = context.scene.clothes_burst
        regions, skipped = {}, []
        if context.mode == "EDIT_MESH":
            objs = [o for o in context.objects_in_mode if o.type == "MESH"]
            bpy.ops.object.mode_set(mode="OBJECT")
            garments = []
            for o in objs:
                faces = burst.selected_faces(o)
                if faces:
                    garments.append(o)
                    regions[o.name] = faces
                else:
                    skipped.append(o.name)
            if not garments:
                bpy.ops.object.mode_set(mode="EDIT")
                self.report({"ERROR"}, "编辑模式下先选中要爆开的面（面选择模式，或选中顶点围成的面）")
                return {"CANCELLED"}
        else:
            garments = _garment_candidates(context)
            regions = {g.name: burst.region_of(g) for g in garments}
        notes = []
        if burst.any_baked(context.scene):
            bpy.ops.ptcache.free_bake_all()
            notes.append("原来的烘焙已清除")
        try:
            notes += burst.burst(garments, regions, s.opts())
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if skipped:
            notes.append("没有选中面、没动：%s" % "、".join(skipped))
        for o in context.view_layer.objects:
            o.select_set(o in garments)
        context.view_layer.objects.active = garments[0]
        context.scene.frame_set(context.scene.frame_start)
        for line in notes:
            print(TAG, line)
        self.report({"INFO"}, "爆衣设好了（%s），点「烘焙」后从第 %d 帧播放：%s" % (
            "、".join(g.name for g in garments), context.scene.frame_start, "；".join(notes[-3:])))
        return {"FINISHED"}


class CB_OT_show_region(bpy.types.Operator):
    bl_idname = "clothes_burst.show_region"
    bl_label = "显示范围"
    bl_description = "进编辑模式，选中当前衣服要爆开的那部分面（可以接着改选择，再点「一键爆衣」）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return burst is not None and obj is not None and obj.type == "MESH" and burst.region_of(obj) is not None

    def execute(self, context):
        obj = context.active_object
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        region = burst.region_of(obj)
        for o in context.view_layer.objects:
            o.select_set(o is obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bm = bmesh.from_edit_mesh(obj.data)
        for f in bm.faces:
            f.select_set(False)
        for f in bm.faces:
            if f.index in region:
                f.select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, "%s：要爆开的 %d 个面已选中" % (obj.name, len(region)))
        return {"FINISHED"}


class CB_OT_whole(bpy.types.Operator):
    bl_idname = "clothes_burst.whole"
    bl_label = "改成整件"
    bl_description = "去掉存下的爆开范围，下次「一键爆衣」时整件爆开（要再点一次「一键爆衣」才生效）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return burst is not None and context.mode == "OBJECT" and any(
            burst.region_of(o) is not None for o in _garment_candidates(context))

    def execute(self, context):
        done = [o.name for o in _garment_candidates(context) if burst.region_of(o) is not None]
        for o in _garment_candidates(context):
            burst.set_region(o, None)
        self.report({"INFO"}, "%s 改成整件，再点「一键爆衣」生效" % "、".join(done))
        return {"FINISHED"}


class CB_OT_reset(bpy.types.Operator):
    bl_idname = "clothes_burst.reset"
    bl_label = "恢复默认设置"
    bl_description = "面板上的设置全部回到默认值（不改已经设好的衣服，要再点「一键爆衣」）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.clothes_burst
        for key in D:
            s.property_unset(key)
        self.report({"INFO"}, "设置已恢复默认")
        return {"FINISHED"}


class CB_OT_remove(bpy.types.Operator):
    bl_idname = "clothes_burst.remove"
    bl_label = "撤掉选中衣服的爆衣"
    bl_description = ("选中的衣服回到爆衣之前：撕裂修改器、跟随身体的布料、裂缝、爆开范围都删掉。"
                      "身体上的碰撞和地面是共用的，留着（「全部清理」才删）")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return burst is not None and context.mode == "OBJECT" and any(
            burst.BURST in o for o in _garment_candidates(context))

    def execute(self, context):
        done = []
        for o in _garment_candidates(context):
            if burst.BURST in o:
                parts = burst.remove_burst(o)
                done.append("%s（%s）" % (o.name, "、".join(parts)))
        for line in done:
            print(TAG, "撤掉", line)
        self.report({"INFO"}, "已撤掉：" + "；".join(done))
        return {"FINISHED"}


class CB_OT_cleanup(bpy.types.Operator):
    bl_idname = "clothes_burst.cleanup"
    bl_label = "全部清理"
    bl_description = ("删掉爆衣和布料撕裂插件在这个场景里加的所有东西：每件衣服的撕裂设置、裂缝、范围，"
                      "身体上的碰撞、地面、推力场。可以 Ctrl+Z 撤销")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return burst is not None and (bool(burst.burst_garments(context.scene)) or bool(ct.tear_garments(context.scene))
                                      or bool(burst.field_groups())
                                      or any(bpy.data.objects.get(n) is not None for n in (ct.FLOOR, ct.FIELD)))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="删掉爆衣 / 布料撕裂在这个场景里加的所有东西：")
        names = {o.name for o in burst.burst_garments(context.scene)} | {o.name for o in ct.tear_garments(context.scene)}
        col.label(text="  " + ("、".join(sorted(names)) or "（没有衣服）"))
        col.label(text="  还有身体上的碰撞、地面、推力场")

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        done = burst.cleanup_all()
        for line in done:
            print(TAG, "清理", line)
        self.report({"INFO"}, "已清理：" + ("；".join(done) if done else "没有要清理的"))
        return {"FINISHED"}


class CB_PT_panel(bpy.types.Panel):
    bl_label = "爆衣"
    bl_idname = "CB_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "爆衣"

    def draw(self, context):
        layout = self.layout
        if burst is None:
            col = layout.column()
            col.label(text="需要同时安装「布料撕裂 Cloth Tear」插件", icon="ERROR")
            col.label(text="（scripts/blender_addons/cloth_tear，和这个插件放在同一个插件目录）")
            col.label(text=MISSING[:80])
            return
        s = context.scene.clothes_burst

        box = layout.box()
        box.label(text="1. 选衣服", icon="RESTRICT_SELECT_OFF")
        col = box.column(align=True)
        if context.mode == "EDIT_MESH":
            objs = [o for o in context.objects_in_mode if o.type == "MESH"]
            col.label(text="编辑模式：只爆开选中的面，其余留在身上")
            col.label(text="  " + "、".join("%s 选中 %d 面" % (o.name, o.data.total_face_sel) for o in objs))
        else:
            picked = _garment_candidates(context)
            col.label(text="物体模式：选中的衣服整件爆开（可多选）")
            col.label(text="只爆一部分：Tab 进编辑模式选中那部分的面")
            if picked:
                col.label(text="  选中：" + "、".join(o.name for o in picked[:4]) + (" 等 %d 件" % len(picked)
                                                                                 if len(picked) > 4 else ""))
            else:
                col.label(text="  （还没选中衣服）", icon="INFO")

        box = layout.box()
        box.label(text="2. 爆开", icon="FORCE_FORCE")
        row = box.row()
        row.scale_y = 1.6
        row.operator("clothes_burst.burst", icon="MOD_EXPLODE")
        box.prop(s, "fast", toggle=True, icon="FF")
        row = box.row(align=True)
        # Blender 自带的「烘焙所有动力学解算结果」：从按钮调用是后台任务，状态栏有进度条，Esc 取消
        row.operator("ptcache.bake_all", text="烘焙", icon="REC").bake = True
        row.operator("ptcache.free_bake_all", text="清除烘焙", icon="TRASH")
        box.label(text="改了设置要再点「一键爆衣」，再清除烘焙、烘焙", icon="INFO")

        box = layout.box()
        row = box.row()
        row.label(text="设置（都有默认值）", icon="PREFERENCES")
        row.operator("clothes_burst.reset", text="", icon="LOOP_BACK")
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(s, "frame"); row.prop(s, "duration")
        row = col.row(align=True)
        row.prop(s, "accel"); row.prop(s, "push_frames")
        box.row().prop(s, "shape", expand=True)
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(s, "through"); row.prop(s, "partial")
        row = col.row(align=True)
        row.prop(s, "jitter"); row.prop(s, "seed")
        box.prop(s, "show_more", icon="TRIA_DOWN" if s.show_more else "TRIA_RIGHT", emboss=False)
        if s.show_more:
            col = box.column(align=True)
            row = col.row(align=True)
            row.prop(s, "loops", toggle=True); row.prop(s, "regen", toggle=True); row.prop(s, "invert", toggle=True)
            row = col.row(align=True)
            row.prop(s, "width"); row.prop(s, "merge")

        obj = context.active_object
        if obj is not None and obj.type == "MESH" and burst.BURST in obj:
            box = layout.box()
            box.label(text="当前：%s" % obj.name, icon="OUTLINER_OB_MESH")
            region = burst.region_of(obj)
            row = box.row(align=True)
            row.label(text="范围：整件" if region is None else "范围：一部分（%d 个面）" % len(region))
            row.operator("clothes_burst.show_region", text="", icon="EDITMODE_HLT")
            row.operator("clothes_burst.whole", text="", icon="FULLSCREEN_ENTER")
            last = burst.last_settings(obj)
            if last:
                box.label(text="上次：第 %s 帧爆开、推力 %s × 重力推 %s 帧、裂缝 %s + %s" % (
                    last.get("frame"), last.get("accel"), last.get("push_frames"), last.get("through"),
                    last.get("partial")))
            c2 = ct.tear_modifiers(obj)[1]
            if c2 is not None:
                row = box.row(align=True)
                row.prop(c2.settings, "time_scale", text="布料 2 速度")
                row.prop(c2.settings, "quality", text="质量步数")
                coll = c2.settings.effector_weights.collection
                box.label(text="推力组 %s，力场权重 %.2f（按面积自动算）" % (
                    coll.name if coll is not None else "无", c2.settings.effector_weights.force))

        box = layout.box()
        box.label(text="清理", icon="BRUSH_DATA")
        row = box.row(align=True)
        row.operator("clothes_burst.remove", icon="X")
        row.operator("clothes_burst.cleanup", icon="TRASH")


CLASSES = (CB_Settings, CB_OT_burst, CB_OT_show_region, CB_OT_whole, CB_OT_reset, CB_OT_remove, CB_OT_cleanup,
           CB_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.clothes_burst = PointerProperty(type=CB_Settings)


def unregister():
    del bpy.types.Scene.clothes_burst
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
