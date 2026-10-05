# -*- coding: utf-8 -*-
"""爆衣 Clothes Burst - 选中衣服，让它在指定的帧爆开。一个插件，几种做法（面板最上面选「方式」）：

  布料撕裂（Blender 里渲染用）  用布料撕裂插件（cloth_tear，同一个仓库）的撕裂做法：裂缝 + 两个布料修改器 + 几何节点
      按帧松开，爆衣在上面加范围里的随机裂缝、几帧内全部松开、按「重力的倍数」给的短促推力；外观：撕口毛边、碎片
      淡出 / 溶解（burst.py、look.py）。真的物理，带不进 MMD
  碎片飞散 / 直接消失（给 MMD 用）  做在 mmd_tools 导入的模型上：衣服复制一份切成碎片，飞出去、落地都预先算成
      顶点表情，碎片的显示 / 衣服的隐藏是材质表情，VMD 只打表情帧——MMD 里不用物理，哪个版本都能放；身体有形状键
      「裸体形状」时可以换成完整身体（两份身体）（shards.py、mmd.py、vmd.py）
界面：3D 视图侧栏（N）> 爆衣。原理见各模块开头和 docs/clothes-burst-guide.md。
"""
bl_info = {
    "name": "爆衣 Clothes Burst",
    "author": "ripper_tpose",
    "version": (2, 0, 0),
    "blender": (3, 6, 0),
    "location": "3D 视图 > 侧栏 > 爆衣",
    "description": "选中衣服，在指定的帧爆开：布料撕裂（Blender 渲染，要同时装 cloth_tear），"
                   "或碎片飞散 / 直接消失（MMD：mmd_tools 模型上做表情，导出 PMX + VMD）",
    "category": "Physics",
}

import importlib
import os

import bmesh
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)
from bpy_extras.io_utils import ExportHelper

try:
    from . import look
    importlib.reload(look)
    from . import burst
    importlib.reload(burst)
    ct = burst.ct
    MISSING = ""
except ImportError as exc:                    # 没装布料撕裂插件：只有「布料撕裂」用不了
    burst = ct = look = None
    MISSING = str(exc)
from . import vmd                             # noqa: E402  (MMD 的几种做法：不需要 cloth_tear)
from . import shards                          # noqa: E402
from . import mmd                             # noqa: E402
for _m in (vmd, shards, mmd):
    importlib.reload(_m)

D = burst.DEFAULTS if burst is not None else {}
L = look.DEFAULTS if look is not None else {}
TAG = "[爆衣]"


def _look_update(self, context):
    """外观设置改了马上用到所有爆过的衣服（只改材质里的节点组，不用重新烘焙）。"""
    if burst is None:
        return
    try:
        for line in burst.sync_look(self.opts(), context.scene):
            print(TAG, line)
    except Exception as exc:                  # 界面回调里不能抛出去
        print(TAG, "外观没更新：%s" % exc)


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

    # 外观（只改渲染，改了马上生效）
    fray: BoolProperty(name="撕口毛边", default=L.get("fray", True), update=_look_update,
                       description="撕开以后，撕口变成参差不齐的毛边，边上稍微变暗。只影响渲染，"
                                   "在「材质预览」「渲染」视图里看")
    fray_width: FloatProperty(name="宽度", default=L.get("fray_width", 0.5), min=0.0, max=3.0, precision=2,
                              update=_look_update,
                              description="毛边有多宽，按身高的百分比：0.5 ≈ 1.7 米的人身上 8 毫米；1 以上像撕纸")
    fray_dark: FloatProperty(name="变暗", default=L.get("fray_dark", 0.3), min=0.0, max=1.0, update=_look_update,
                             description="撕口附近变暗多少（像磨破、烧焦），0 = 不变暗")
    vanish: EnumProperty(name="碎片消失", default=L.get("vanish", "NONE"), update=_look_update, items=(
        ("NONE", "不消失", "碎片留在地上"),
        ("FADE", "淡出", "碎片渐渐变透明"),
        ("DISSOLVE", "溶解", "碎片一块一块地烧掉似的消失，边缘发光"),
    ))
    vanish_delay: IntProperty(name="松开后几帧开始", default=L.get("vanish_delay", 3), min=0, max=1000,
                              update=_look_update, description="碎片松开以后过几帧开始消失")
    vanish_frames: IntProperty(name="用几帧", default=L.get("vanish_frames", 12), min=1, max=1000,
                               update=_look_update, description="从开始消失到完全消失用几帧")
    rim_color: FloatVectorProperty(name="光边颜色", subtype="COLOR", size=3, min=0.0, max=1.0,
                                   default=L.get("rim_color", (1.0, 0.38, 0.08)), update=_look_update,
                                   description="溶解时边缘发光的颜色")
    glow: FloatProperty(name="光边亮度", default=L.get("glow", 6.0), min=0.0, soft_max=30.0, update=_look_update,
                        description="溶解时边缘发光有多亮（Eevee 打开「辉光」更好看），0 = 不发光")

    def opts(self):
        out = {k: getattr(self, k) for k in list(D) + list(L)}
        out["rim_color"] = tuple(out.get("rim_color", ()))
        return out


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
    bl_description = ("面板上的设置全部回到默认值。外观马上生效；其余的不改已经设好的衣服，要再点「一键爆衣」")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.clothes_burst
        for key in list(D) + list(L):
            s.property_unset(key)
        burst.sync_look(s.opts(), context.scene)                # 外观设置马上生效（property_unset 不触发回调）
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


# ---------------------------------------------------------------- 给 MMD 用：碎片飞散 / 直接消失（mmd.py）

M = mmd.DEFAULTS
T = vmd.DEFAULTS


class CB_MMDSettings(bpy.types.PropertyGroup):
    style: EnumProperty(name="做法", default="SHARDS", items=(
        ("SHARDS", "碎片飞散", "衣服碎成几百块飞出去、落到地上、淡出"),
        ("VANISH", "直接消失", "衣服一下子（或几帧内淡出）没了，没有碎片"),
    ))
    swap: BoolProperty(name="换成完整身体", default=M["swap"],
                       description="身体有形状键「裸体形状」时（ROE 的 full 版）：身体复制一份成脱衣用的，爆开后换上去"
                                   "——MMD 和 Blender 里光照都对。没有这个形状键时不起作用")
    nude_pmx: StringProperty(name="nude 版 PMX", subtype="FILE_PATH", default="",
                             description="可选：同一个身体的 nude 版 PMX，脱衣身体的法线从它拿（最准）。"
                                         "不填就用 Blender 换算的法线（极少数指甲处差几度）")
    size: FloatProperty(name="碎片大小", default=M["size"] * 100, min=1.0, max=100.0, precision=1, subtype="NONE",
                        description="碎片大概多大（厘米，按 1.6 米身高；模型高矮自动缩放）。比它的 1.5 倍还小的整块飞")
    throw_min: FloatProperty(name="飞出 最近", default=M["throw_min"] * 100, min=0.0, max=500.0, precision=1,
                             description="碎片飞出去最少多远（厘米）")
    throw_max: FloatProperty(name="最远", default=M["throw_max"] * 100, min=0.0, max=500.0, precision=1,
                             description="碎片飞出去最多多远（厘米）")
    lift: FloatProperty(name="上扬", default=M["lift"], min=0.0, max=3.0, precision=2,
                        description="往上飞的成分（0 = 只沿身体表面往外）")
    tilt: FloatProperty(name="偏转", default=M["tilt"], min=0.0, max=3.0, precision=2,
                        description="方向的随机偏转（0 = 都沿身体表面的法线）")
    turn_min: FloatProperty(name="飞出时转 最少", default=M["turn_min"], min=0.0, max=720.0, precision=0)
    turn_max: FloatProperty(name="最多", default=M["turn_max"], min=0.0, max=720.0, precision=0)
    fall_turn_min: FloatProperty(name="落下时转 最少", default=M["fall_turn_min"], min=0.0, max=720.0, precision=0)
    fall_turn_max: FloatProperty(name="最多", default=M["fall_turn_max"], min=0.0, max=720.0, precision=0)
    drift_min: FloatProperty(name="落下时漂 最少", default=M["drift_min"] * 100, min=0.0, max=500.0, precision=1,
                             description="落下时继续往外漂多远（厘米）")
    drift_max: FloatProperty(name="最多", default=M["drift_max"] * 100, min=0.0, max=500.0, precision=1)
    seed: IntProperty(name="随机种子", default=M["seed"], description="换一个数就换一种碎法和飞法")
    start: IntProperty(name="爆开帧", default=T["start"], min=1, description="VMD 里这一帧爆开（30 fps）")
    slow: FloatProperty(name="慢放", default=T["slow"], min=0.1, max=10.0, precision=2,
                        description="时间拉长几倍（1.5 = 慢一半）")
    vanish_frames: IntProperty(name="淡出用几帧", default=T["vanish_frames"], min=1, max=600,
                               description="直接消失：衣服几帧内淡出，1 = 一下子没了")
    fade: BoolProperty(name="碎片淡出", default=True, description="碎片落地后淡出消失；关掉就留在地上")
    fade_start: IntProperty(name="爆开后第几帧开始", default=T["fade_start"], min=1, max=10000)
    fade_end: IntProperty(name="第几帧没了", default=T["fade_end"], min=2, max=10000)
    merge_with: StringProperty(name="合进动作", subtype="FILE_PATH", default="",
                               description="可选：导出 VMD 时把爆衣的表情帧合进这段动作的 VMD（骨骼、别的表情原样）")
    show_more: BoolProperty(name="更多设置", default=False)

    def shard_opts(self):
        return {"style": self.style, "swap": self.swap, "nude_pmx": bpy.path.abspath(self.nude_pmx),
                "size": self.size / 100.0, "throw_min": self.throw_min / 100.0, "throw_max": self.throw_max / 100.0,
                "lift": self.lift, "tilt": self.tilt, "turn_min": self.turn_min, "turn_max": self.turn_max,
                "fall_turn_min": self.fall_turn_min, "fall_turn_max": self.fall_turn_max,
                "drift_min": self.drift_min / 100.0, "drift_max": self.drift_max / 100.0, "seed": self.seed}

    def timing(self):
        fade_end = self.fade_end if self.fade else self.fade_start
        return {"style": self.style, "start": self.start, "slow": self.slow, "vanish_frames": self.vanish_frames,
                "fade_start": self.fade_start, "fade_end": fade_end}


def mmd_tools_ready():
    return "mmd_tools" in bpy.context.preferences.addons


def active_root(context):
    return mmd.find_root(context.active_object) if mmd_tools_ready() else None


class _NeedsModel:
    @classmethod
    def poll(cls, context):
        return active_root(context) is not None


class CB_OT_mmd_outfit_toggle(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_outfit_toggle"
    bl_label = "衣服 / 不是衣服"
    bl_description = "这个材质算不算衣服（算衣服的爆开时碎掉 / 消失）"
    bl_options = {"REGISTER", "UNDO"}
    material: StringProperty()

    def execute(self, context):
        root = active_root(context)
        names = set(mmd.outfit_names(root))
        names ^= {self.material}
        mmd.set_outfit(root, names)
        return {"FINISHED"}


class CB_OT_mmd_outfit_from_morph(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_outfit_from_morph"
    bl_label = "按「衣服非表示_材質」选"
    bl_description = "模型自带的表情 衣服非表示_材質 隐藏哪些材质，就把哪些当衣服（ROE 的 full 版都有）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = active_root(context)
        names = mmd.outfit_from_morph(root)
        if not names:
            self.report({"WARNING"}, "这个模型没有 衣服非表示_材質 表情：点材质按钮手动选，或编辑模式选面")
            return {"CANCELLED"}
        mmd.set_outfit(root, names)
        self.report({"INFO"}, "衣服：" + "、".join(names))
        return {"FINISHED"}


class CB_OT_mmd_outfit_from_faces(bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_outfit_from_faces"
    bl_label = "按选中的面选"
    bl_description = "编辑模式里选中的面用到的材质都当衣服（选一件衣服上的几个面就够）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and active_root(context) is not None

    def execute(self, context):
        root = active_root(context)
        objs = [o for o in context.objects_in_mode if o.type == "MESH"]
        bpy.ops.object.mode_set(mode="OBJECT")
        names = set()
        for o in objs:
            for p in o.data.polygons:
                if p.select and p.material_index < len(o.material_slots) and o.material_slots[p.material_index].material:
                    names.add(o.material_slots[p.material_index].material.name)
        bpy.ops.object.mode_set(mode="EDIT")
        if not names:
            self.report({"WARNING"}, "没有选中面")
            return {"CANCELLED"}
        mmd.set_outfit(root, set(mmd.outfit_names(root)) | names)
        self.report({"INFO"}, "加进衣服：" + "、".join(sorted(names)))
        return {"FINISHED"}


class CB_OT_mmd_make(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_make"
    bl_label = "生成爆衣表情"
    bl_description = ("在模型上做好爆衣用的表情（碎片 + 爆衣 / 爆衣落下 / 爆衣碎片_材質，或只有 衣服非表示_材質；"
                      "勾了「换成完整身体」还有两份身体）。再点一次就按新的设置重做。之后用 mmd_tools 照常导出 PMX")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = active_root(context)
        return root is not None and not mmd.imported_burst(root)

    def execute(self, context):
        root = active_root(context)
        s = context.scene.clothes_burst_mmd
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            rep = mmd.make(root, mmd.outfit_names(root), s.shard_opts())
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        parts = ["%d 块碎片" % rep["fragments"]] if s.style == "SHARDS" else ["衣服可以直接消失"]
        if rep.get("swapped_bodies"):
            parts.append("身体换成完整的（两份身体）")
        elif mmd.two_bodies(root):
            parts.append("身体本来就是两份")
        hit = sum(i.get("normals_from_pmx", 0) for i in rep.get("nude_copies", {}).values())
        loops = sum(i.get("loops", 0) for i in rep.get("nude_copies", {}).values())
        if loops:
            parts.append("法线从 nude 版 PMX 拿：对上 %d / %d 个角" % (hit, loops))
        print(TAG, rep)
        self.report({"INFO"}, "爆衣表情做好了：%s。点「在时间轴上预览」看效果" % "，".join(parts))
        if loops and hit < 0.9 * loops:
            self.report({"WARNING"}, "nude 版 PMX 只对上 %d%% 的角：是不是选错了文件？没对上的地方用 Blender 换算的法线"
                        % (100 * hit // loops))
        return {"FINISHED"}


class CB_OT_mmd_remove(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_remove"
    bl_label = "撤掉爆衣表情"
    bl_description = "删掉碎片、脱衣身体和加的表情，模型回到生成之前（裸体形状 还原成形状键）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = active_root(context)
        return root is not None and mmd.has_burst(root)

    def execute(self, context):
        root = active_root(context)
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        mmd.clear_preview(root)
        done = mmd.remove(root)
        self.report({"INFO"}, "已撤掉：" + "；".join(done))
        return {"FINISHED"}


class CB_OT_mmd_preview(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_preview"
    bl_label = "在时间轴上预览"
    bl_description = ("在表情滑块上打好爆衣的关键帧（和导出的 VMD 一样），按空格播放就能看；不影响别的表情帧。"
                      "导入的爆衣 PMX 也能直接预览")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = active_root(context)
        return root is not None and (mmd.has_burst(root) or mmd.burst_morphs(root)["VANISH"])

    def execute(self, context):
        root = active_root(context)
        s = context.scene.clothes_burst_mmd
        have = mmd.burst_morphs(root)
        if not have[s.style]:
            self.report({"ERROR"}, "模型没有这些表情：%s——先点「生成爆衣表情」，或「做法」选直接消失"
                        % "、".join(have["missing"]))
            return {"CANCELLED"}
        first, last = mmd.preview(root, s.timing())
        context.scene.frame_set(max(context.scene.frame_start, first - 10))
        n = len(mmd.wrapped(root))
        self.report({"INFO"}, "第 %d 到 %d 帧打好了表情帧，按空格播放%s" % (
            first, last, "（%d 个不是 MMD 着色器的材质加了透明节点，材质表情才看得见）" % n if n else ""))
        return {"FINISHED"}


class CB_OT_mmd_clear_preview(_NeedsModel, bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_clear_preview"
    bl_label = "清除预览"
    bl_description = "删掉预览打的爆衣表情帧（别的表情帧不动）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = mmd.clear_preview(active_root(context))
        self.report({"INFO"}, "清掉 %d 条表情曲线" % n)
        return {"FINISHED"}


class CB_OT_mmd_export_vmd(_NeedsModel, bpy.types.Operator, ExportHelper):
    bl_idname = "clothes_burst.mmd_export_vmd"
    bl_label = "导出爆衣 VMD"
    bl_description = ("只有爆衣表情帧的 VMD（MMD 里在舞蹈动作之后读入），或填了「合进动作」时，那段动作加上爆衣的帧")
    filename_ext = ".vmd"
    filter_glob: StringProperty(default="*.vmd", options={"HIDDEN"})

    def invoke(self, context, event):
        s = context.scene.clothes_burst_mmd
        self.filepath = "爆衣_第%d帧开始.vmd" % s.start
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        root = active_root(context)
        s = context.scene.clothes_burst_mmd
        merge = bpy.path.abspath(s.merge_with) if s.merge_with else ""
        if merge and not os.path.isfile(merge):
            self.report({"ERROR"}, "找不到要合进去的动作：" + merge)
            return {"CANCELLED"}
        try:
            msg = mmd.export_vmd(self.filepath, s.timing(), merge, root.mmd_root.name or root.name)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "%s：%s" % (os.path.basename(self.filepath), msg))
        return {"FINISHED"}


class CB_OT_mmd_reset(bpy.types.Operator):
    bl_idname = "clothes_burst.mmd_reset"
    bl_label = "恢复默认设置"
    bl_description = "MMD 爆衣的设置全部回到默认值（已经生成的表情不变，要再点「生成爆衣表情」）"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.clothes_burst_mmd
        for key in s.bl_rna.properties.keys():
            if key not in ("rna_type", "name", "nude_pmx", "merge_with"):
                s.property_unset(key)
        self.report({"INFO"}, "设置已恢复默认")
        return {"FINISHED"}


def _pair(col, s, a, b, label, ta, tb):
    """一个说明 + 两个数（侧栏默认宽度下，半宽的数值框只放得下一个汉字的标签：两个字的标签、说明另起一行）。"""
    col.label(text=label)
    row = col.row(align=True)
    row.prop(s, a, text=ta)
    row.prop(s, b, text=tb)


def draw_mmd(layout, context):
    s = context.scene.clothes_burst_mmd
    if not mmd_tools_ready():
        box = layout.box()
        box.label(text="需要启用 mmd_tools 插件", icon="ERROR")
        box.label(text="（在它导入的模型上做表情）")
        return
    root = active_root(context)
    box = layout.box()
    box.label(text="1. 模型和衣服", icon="OUTLINER_OB_ARMATURE")
    if root is None:
        box.label(text="选中 mmd_tools 导入的模型", icon="INFO")
        box.label(text="（模型里随便哪个物体都行）")
        return
    name = root.mmd_root.name
    box.label(text="模型：%s" % (root.name if name in ("", "New MMD Model") else name))
    imported = mmd.imported_burst(root)
    if not imported:
        outfit = set(mmd.outfit_names(root))
        mats = mmd.model_materials(root)
        col = box.column(align=True)
        col.label(text="点材质切换，按下 = 衣服：")
        wide = max((len(m.name) for m in mats), default=0) > 12
        grid = col.grid_flow(columns=1 if wide else 2, align=True)
        for mat in mats:
            op = grid.operator("clothes_burst.mmd_outfit_toggle", text=mat.name, depress=mat.name in outfit)
            op.material = mat.name
        col = box.column(align=True)
        col.operator("clothes_burst.mmd_outfit_from_morph", icon="SHAPEKEY_DATA")
        col.operator("clothes_burst.mmd_outfit_from_faces", icon="FACESEL")

    box = layout.box()
    box.label(text="2. 做法", icon="MOD_EXPLODE")
    box.row().prop(s, "style", expand=True)
    if not imported:
        # the file has the two bodies already (ROE full versions since 10-05): nothing to swap
        given = mmd.two_bodies(root) and not mmd._record(root).get("swapped")
        has_body = any(mmd.body_key(m) is not None for m in mmd.parts(root)[1]) or mmd.has_burst(root)
        if given:
            col = box.column(align=True)
            col.label(text="身体已经有两份", icon="CHECKMARK")
            col.label(text="（「裸体形状」换身体，不用再换）")
        else:
            row = box.row()
            row.active = has_body
            row.prop(s, "swap")
            if not has_body:
                col = box.column(align=True)
                col.label(text="模型没有「裸体形状」", icon="INFO")
                col.label(text="衣服下要本来就有完整身体")
            elif s.swap:
                col = box.column(align=True)
                col.label(text="nude 版 PMX（可选）：")
                col.prop(s, "nude_pmx", text="")
        if s.style == "SHARDS":
            col = box.column(align=True)
            col.prop(s, "size", text="碎片大小 cm")
            col.prop(s, "seed")
            col = box.column(align=True)
            _pair(col, s, "throw_min", "throw_max", "飞出多远（厘米）：", "近", "远")
            col.prop(s, "lift")
            col.prop(s, "tilt")
            box.prop(s, "show_more", icon="TRIA_DOWN" if s.show_more else "TRIA_RIGHT", emboss=False)
            if s.show_more:
                col = box.column(align=True)
                _pair(col, s, "turn_min", "turn_max", "飞出时转几度：", "少", "多")
                _pair(col, s, "fall_turn_min", "fall_turn_max", "落下时转几度：", "少", "多")
                _pair(col, s, "drift_min", "drift_max", "落下时往外漂（厘米）：", "近", "远")

    box = layout.box()
    row = box.row()
    row.label(text="3. 生成", icon="SHAPEKEY_DATA")
    row.operator("clothes_burst.mmd_reset", text="", icon="LOOP_BACK")
    if imported:
        col = box.column(align=True)
        col.label(text="模型已经带着爆衣表情", icon="CHECKMARK")
        col.label(text="（导入的爆衣 PMX）")
        col.label(text="直接在第 4 步预览、导出 VMD")
        col.label(text="要重做：导入没做过爆衣的 PMX")
    else:
        row = box.row()
        row.scale_y = 1.6
        row.operator("clothes_burst.mmd_make", icon="MOD_EXPLODE")
    if mmd.has_burst(root):
        rec = mmd._record(root)
        col = box.column(align=True)
        col.label(text="已生成：" + ("碎片飞散" if rec.get("style") == "SHARDS" else "直接消失"), icon="CHECKMARK")
        if rec.get("swapped"):
            col.label(text="身体换成完整的（两份身体）")
        box.operator("clothes_burst.mmd_remove", icon="X")

    box = layout.box()
    box.label(text="4. 时间、预览、导出", icon="TIME")
    col = box.column(align=True)
    col.prop(s, "start")
    col.prop(s, "slow")
    if s.style == "SHARDS":
        box.prop(s, "fade", toggle=True)
        col = box.column(align=True)
        col.active = s.fade
        _pair(col, s, "fade_start", "fade_end", "爆开后第几帧淡出：", "从", "到")
    else:
        box.prop(s, "vanish_frames")
    row = box.row(align=True)
    row.scale_y = 1.3
    row.operator("clothes_burst.mmd_preview", icon="PLAY")
    row.operator("clothes_burst.mmd_clear_preview", text="", icon="TRASH")
    col = box.column(align=True)
    col.label(text="合进动作（可选）：")
    col.prop(s, "merge_with", text="")
    box.operator("clothes_burst.mmd_export_vmd", icon="EXPORT")
    box.label(text="PMX：用 mmd_tools 导出", icon="INFO")


class CB_PT_panel(bpy.types.Panel):
    bl_label = "爆衣"
    bl_idname = "CB_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "爆衣"

    def draw(self, context):
        layout = self.layout
        layout.row().prop(context.scene, "clothes_burst_method", expand=True)
        if context.scene.clothes_burst_method == "MMD":
            draw_mmd(layout, context)
            return
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

        box = layout.box()
        box.label(text="外观（只影响渲染，不用重烘）", icon="SHADING_RENDERED")
        col = box.column(align=True)
        col.prop(s, "fray", toggle=True)
        row = col.row(align=True)
        row.active = s.fray
        row.prop(s, "fray_width"); row.prop(s, "fray_dark")
        box.label(text="碎片消失：")
        box.row().prop(s, "vanish", expand=True)
        if s.vanish != "NONE":
            row = box.row(align=True)
            row.prop(s, "vanish_delay"); row.prop(s, "vanish_frames")
            if s.vanish == "DISSOLVE":
                row = box.row(align=True)
                row.prop(s, "rim_color", text=""); row.prop(s, "glow")
        box.label(text="在「材质预览」「渲染」视图里看", icon="INFO")

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
           CB_MMDSettings, CB_OT_mmd_outfit_toggle, CB_OT_mmd_outfit_from_morph, CB_OT_mmd_outfit_from_faces,
           CB_OT_mmd_make, CB_OT_mmd_remove, CB_OT_mmd_preview, CB_OT_mmd_clear_preview, CB_OT_mmd_export_vmd,
           CB_OT_mmd_reset, CB_PT_panel)


def register():
    for m in (vmd, shards, mmd):        # 关掉再启用插件就用上磁盘上的新代码（Blender 只在 __init__.py 改了时才重新载入 __init__）
        importlib.reload(m)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.clothes_burst = PointerProperty(type=CB_Settings)
    bpy.types.Scene.clothes_burst_mmd = PointerProperty(type=CB_MMDSettings)
    bpy.types.Scene.clothes_burst_method = EnumProperty(name="方式", default="CLOTH", items=(
        ("CLOTH", "布料撕裂", "Blender 里渲染用：真的布料物理，碎片撞到身体和地面（带不进 MMD）"),
        ("MMD", "MMD 表情", "给 MMD 用：碎片飞散 / 直接消失做成表情，mmd_tools 导出 PMX，再导出 VMD"),
    ))


def unregister():
    del bpy.types.Scene.clothes_burst_method
    del bpy.types.Scene.clothes_burst_mmd
    del bpy.types.Scene.clothes_burst
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
