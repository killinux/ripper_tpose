# -*- coding: utf-8 -*-
"""Faceit ARKit - give a model the 52 ARKit expressions and hook it into Faceit for live capture
(iPhone Face Cap / Live Link Face -> Faceit -> shape keys).

MetaHuman faces (FACIAL_* bones + the face's DNA file): the 52 shapes are evaluated from the DNA.
Models that already have ARKit shape keys under any common spelling: only the Faceit step.
UE Viewer exports keep 4 bone influences per vertex; with the cooked package the full weights
(up to 12 on a MetaHuman face) go back first, or every expression comes out lumpy.

Blender add-on package.  UI: 3D viewport sidebar > ARKit tab.  Scripts: ``api`` (see api.py).
"""
bl_info = {
    "name": "Faceit ARKit",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > ARKit",
    "description": "52 ARKit shape keys from a MetaHuman DNA (+ full UE skin weights), registered "
                   "with Faceit for iPhone Face Cap / Live Link Face capture",
    "category": "Animation",
}

# junction-installed from the repo: on Reload Scripts / re-enable refresh the submodules too
if "bpy" in locals():
    import importlib

    for _module in (arkit, dna, bake, ue_weights, faceit_link, api):     # noqa: F821 (dependency order)
        importlib.reload(_module)

import json
import os

import bpy

from . import api, arkit, bake, dna, faceit_link, ue_weights


def _preview_update(self, context):
    obj = self.target or context.object
    if obj is not None and self.preview_name:
        try:
            api.preview(obj, self.preview_name, self.preview_value)
        except ValueError:
            pass


class FARK_Settings(bpy.types.PropertyGroup):
    target: bpy.props.PointerProperty(
        name="Model", type=bpy.types.Object, poll=lambda self, o: o.type == "ARMATURE",
        description="The model's armature (empty = the active object's model)")
    dna_path: bpy.props.StringProperty(
        name="DNA", subtype="FILE_PATH",
        description="The face's MetaHuman DNA file (.dna; Vindictus: scripts/vindictus/extract_face_data.py)")
    package_path: bpy.props.StringProperty(
        name="Package", subtype="FILE_PATH",
        description="Optional: the cooked face package (.uasset.bin) to restore the full skin weights "
                    "that UE Viewer cut to 4 per vertex. Empty = <DNA name>.uasset.bin if it exists")
    head_bone: bpy.props.StringProperty(name="Head bone", description="Bone the phone's head rotation drives "
                                        "(empty = detect: the facial root's parent / head / Bip001 Head ...)")
    source: bpy.props.EnumProperty(name="Live source", items=faceit_link.SOURCES, default="FACECAP")
    preview_name: bpy.props.EnumProperty(name="Shape", items=[(n, n, "") for n in arkit.ARKIT_52],
                                         update=_preview_update)
    preview_value: bpy.props.FloatProperty(name="Value", default=1.0, min=0.0, max=1.0, update=_preview_update)
    report: bpy.props.StringProperty()
    phone_hint: bpy.props.StringProperty()


def _settings(context):
    return context.scene.faceit_arkit


def _obj(context):
    s = _settings(context)
    return s.target or context.object


def _say(context, lines):
    _settings(context).report = "\n".join(lines)


class _Base:
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _obj(context) is not None

    def fail(self, exc):
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class FARK_OT_analyze(_Base, bpy.types.Operator):
    """Report what the model has: face meshes, facial bones, DNA fit, influences, ARKit keys, Faceit state"""
    bl_idname = "faceit_arkit.analyze"
    bl_label = "分析模型"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = _settings(context)
        try:
            info = api.analyze(_obj(context), s.dna_path if s.dna_path else "")
        except (ValueError, OSError, KeyError) as exc:
            return self.fail(exc)
        lines = ["骨架：%s" % info["armature"],
                 "脸部网格：%d 个" % len(info["meshes"]),
                 "面部骨骼：%d 根" % info["facial_bones"],
                 "每顶点权重：最多 %d 个" % info["max_influences"]]
        if info["four_capped"]:
            lines.append("! 权重被截成 4 个，先恢复")
        if "dna" in info:
            d = info["dna"]
            lines.append("DNA 关节：%d/%d" % (d["joints"], d["dna_joints"]))
            lines.append("DNA 误差：%.2f mm" % d["fit_mean_mm"])
        lines.append("ARKit 表情：%d/52" % info["arkit_keys"])
        if info["renamed_keys"]:
            lines.append("（其中 %d 个是别的写法）" % info["renamed_keys"])
        state = {"enabled": "已启用", "disabled": "未启用", "missing": "未安装"}[info["faceit"]]
        if info["faceit"] == "enabled":
            state += "，%s" % ("已注册" if info.get("faceit_registered") else "未注册")
        lines.append("Faceit：%s" % state)
        lines.append("头部骨骼：%s" % (info["head_bone"] or "?"))
        _say(context, lines)
        print("FACEIT_ARKIT_ANALYZE=" + json.dumps(info, ensure_ascii=False))
        return {"FINISHED"}


class FARK_OT_restore(_Base, bpy.types.Operator):
    """Put the cooked package's full skin weights back (UE Viewer keeps only 4 per vertex)"""
    bl_idname = "faceit_arkit.restore_weights"
    bl_label = "恢复完整权重"

    def execute(self, context):
        s = _settings(context)
        path = s.package_path or api.companion_package(s.dna_path)
        if not path:
            return self.fail("选一个 .uasset.bin 游戏包（或把它放在 DNA 旁边，同名）")
        try:
            rep = api.restore_weights(_obj(context), path)
        except (ValueError, OSError) as exc:
            return self.fail(exc)
        s.package_path = s.package_path or path
        lines = ["游戏包：最多 %d 个权重" % rep["package"]["max_influences"]]
        for name, r in rep["meshes"].items():
            if "skipped" in r:
                lines.append("%s：对不上，跳过" % name)
                print("faceit_arkit: %s skipped: %s" % (name, r["skipped"]))
            else:
                lines += [name, "  补全 %d 个顶点" % r["rewritten"],
                          "  原本完整 %d，保留 %d" % (r["already_complete"], r["left_alone"])]
        _say(context, lines)
        return {"FINISHED"}


class FARK_OT_bake(_Base, bpy.types.Operator):
    """Evaluate the 52 ARKit expressions from the DNA and store them as shape keys"""
    bl_idname = "faceit_arkit.bake"
    bl_label = "生成 52 个 ARKit 表情"

    def execute(self, context):
        s = _settings(context)
        if not s.dna_path or not os.path.isfile(bpy.path.abspath(s.dna_path)):
            return self.fail("先选这张脸的 DNA 文件（.dna）")
        try:
            rep = api.bake_arkit(_obj(context), s.dna_path, log=lambda line: None)
        except (ValueError, OSError, KeyError) as exc:
            return self.fail(exc)
        _say(context, ["生成 %d 个表情形态键" % len(rep["shapes"])] +
             ["  %s" % m for m in rep["meshes"]] + ["DNA 误差：%.2f mm" % rep["fit"]["mean_mm"]])
        return {"FINISHED"}


class FARK_OT_clear(_Base, bpy.types.Operator):
    """Remove the shape keys this add-on made (other shape keys stay)"""
    bl_idname = "faceit_arkit.clear"
    bl_label = "删除生成的表情"

    def execute(self, context):
        try:
            n = api.clear_arkit(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        _say(context, ["删除了 %d 个形态键" % n])
        return {"FINISHED"}


class FARK_OT_register(_Base, bpy.types.Operator):
    """Register the face meshes, the 52 ARKit targets, the head bone and the live source with Faceit"""
    bl_idname = "faceit_arkit.register_faceit"
    bl_label = "注册到 Faceit"

    def execute(self, context):
        s = _settings(context)
        try:
            rep = api.register_faceit(_obj(context), head_bone=s.head_bone, source=s.source)
        except (ValueError, RuntimeError) as exc:
            return self.fail(exc)
        if not s.head_bone:
            s.head_bone = rep["head"].split(" / ")[-1]
        s.phone_hint = "手机填 %s 端口 %s" % (rep["lan_ip"], rep["port"])
        lines = ["Faceit 目标：%d/52" % rep["targets"]]
        if rep["missing"]:
            lines.append("缺：%s" % ", ".join(rep["missing"][:3]))
        lines += ["头部骨骼：%s" % s.head_bone, s.phone_hint, "然后 FACEIT → Mocap", "→ Live Recorder → Start"]
        _say(context, lines)
        return {"FINISHED"}


class FARK_OT_all(_Base, bpy.types.Operator):
    """Restore weights (if a package is given / found), bake the 52 shapes, register with Faceit"""
    bl_idname = "faceit_arkit.run_all"
    bl_label = "一键完成"

    def execute(self, context):
        s = _settings(context)
        if not s.dna_path or not os.path.isfile(bpy.path.abspath(s.dna_path)):
            return self.fail("先选这张脸的 DNA 文件（.dna）")
        try:
            out = api.run_all(_obj(context), s.dna_path, package_path=s.package_path, head_bone=s.head_bone,
                              source=s.source, log=lambda line: None)
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return self.fail(exc)
        lines = []
        if "weights" in out:
            done = sum(r.get("rewritten", 0) for r in out["weights"]["meshes"].values())
            s.package_path = s.package_path or out.get("package", "")
            lines.append("权重：补全 %d 个顶点" % done)
        lines.append("表情：%d 个，误差 %.2f mm" % (len(out["bake"]["shapes"]), out["bake"]["fit"]["mean_mm"]))
        if isinstance(out["faceit"], dict):
            f = out["faceit"]
            if not s.head_bone:
                s.head_bone = f["head"].split(" / ")[-1]
            s.phone_hint = "手机填 %s 端口 %s" % (f["lan_ip"], f["port"])
            lines += ["Faceit 目标：%d/52" % f["targets"], "头部骨骼：%s" % s.head_bone, s.phone_hint]
        else:
            lines.append("Faceit 未启用：表情已生成")
        _say(context, lines)
        return {"FINISHED"}


class FARK_OT_reset(_Base, bpy.types.Operator):
    """All ARKit shape keys back to 0"""
    bl_idname = "faceit_arkit.reset"
    bl_label = "表情归零"

    def execute(self, context):
        try:
            api.reset(_obj(context))
        except ValueError as exc:
            return self.fail(exc)
        return {"FINISHED"}


class FARK_PT_panel(bpy.types.Panel):
    bl_label = "Faceit ARKit"
    bl_idname = "FARK_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ARKit"

    def draw(self, context):
        s = _settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "target")
        col.operator(FARK_OT_analyze.bl_idname, icon="VIEWZOOM")
        if s.report:
            box = layout.box()
            for line in s.report.split("\n"):
                box.label(text=line, icon="ERROR" if line.startswith("!") else "NONE")

        box = layout.box()
        box.label(text="1 表情数据", icon="SHAPEKEY_DATA")
        box.prop(s, "dna_path", text="DNA")
        box.prop(s, "package_path", text="游戏包")
        row = box.row(align=True)
        row.operator(FARK_OT_restore.bl_idname, icon="GROUP_VERTEX")
        row = box.row(align=True)
        row.operator(FARK_OT_bake.bl_idname, icon="SHAPEKEY_DATA")
        row.operator(FARK_OT_clear.bl_idname, text="", icon="TRASH")

        box = layout.box()
        box.label(text="2 预览", icon="HIDE_OFF")
        row = box.row(align=True)
        row.prop(s, "preview_name", text="")
        row.prop(s, "preview_value", text="", slider=True)
        row.operator(FARK_OT_reset.bl_idname, text="", icon="LOOP_BACK")

        box = layout.box()
        box.label(text="3 Faceit 实时捕捉", icon="CON_CAMERASOLVER")
        arm = bake.find_armature(_obj(context))
        box.prop(s, "source", text="来源")
        if arm is not None:
            box.prop_search(s, "head_bone", arm.data, "bones", text="头骨")
        state, _pkg = faceit_link.faceit_state()
        if state != "enabled":
            box.label(text="Faceit %s" % {"disabled": "未启用（偏好设置 → 插件）", "missing": "未安装"}[state],
                      icon="ERROR")
        box.operator(FARK_OT_register.bl_idname, icon="LINKED")
        if s.phone_hint:
            box.label(text=s.phone_hint, icon="INFO")

        layout.operator(FARK_OT_all.bl_idname, icon="PLAY")


CLASSES = (FARK_Settings, FARK_OT_analyze, FARK_OT_restore, FARK_OT_bake, FARK_OT_clear, FARK_OT_register,
           FARK_OT_all, FARK_OT_reset, FARK_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.faceit_arkit = bpy.props.PointerProperty(type=FARK_Settings)


def unregister():
    del bpy.types.Scene.faceit_arkit
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
