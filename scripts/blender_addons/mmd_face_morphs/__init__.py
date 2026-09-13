"""MMD Face Morphs - the standard MMD expression set as bone morphs, for models
whose face is rigged with bones instead of shape keys (Rise of Eros and other
game rigs).

Blender add-on package.  UI: 3D viewport sidebar > MMD tab > Face Morphs.
Scripts: ``api.setup(obj)``.
"""
bl_info = {
    "name": "MMD Face Morphs",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > Face Morphs",
    "description": "Blink / smile / brows / あいうえお / tongue as PMX bone morphs for "
                   "mmd_tools models with bone-driven faces",
    "category": "Object",
}

import bpy

from . import api, build, expressions

_morph_items = [("NONE", "-", "")]      # kept alive for the dynamic enum


def _morph_enum(self, context):
    global _morph_items
    items = []
    try:
        root, _arm = build.model_of(context.active_object)
        for i, morph in enumerate(root.mmd_root.bone_morphs):
            items.append((morph.name, "%s  [%s]" % (morph.name, morph.category.lower()), morph.name_e, i))
    except Exception:
        pass
    _morph_items = items or [("NONE", "-", "")]
    return _morph_items


class MFM_Settings(bpy.types.PropertyGroup):
    eyes: bpy.props.FloatProperty(name="Eyes", default=1.0, min=0.1, max=3.0,
                                  description="Multiplier on the eyelid angles (blink closes at 33 deg)")
    brows: bpy.props.FloatProperty(name="Brows", default=1.0, min=0.1, max=3.0,
                                   description="Multiplier on the eyebrow travel")
    mouth: bpy.props.FloatProperty(name="Mouth", default=1.0, min=0.1, max=3.0,
                                   description="Multiplier on the jaw angles and lip travel (あ opens 18 deg)")
    tongue: bpy.props.FloatProperty(name="Tongue", default=1.0, min=0.1, max=3.0)
    do_brows: bpy.props.BoolProperty(name="眉 brows", default=True)
    do_eyes: bpy.props.BoolProperty(name="目 eyes", default=True)
    do_mouth: bpy.props.BoolProperty(name="口 mouth", default=True)
    replace: bpy.props.BoolProperty(name="Replace same-named morphs", default=True,
                                    description="Rebuild morphs that already exist under these names")
    morph: bpy.props.EnumProperty(name="Morph", items=_morph_enum)
    weight: bpy.props.FloatProperty(name="Weight", default=1.0, min=0.0, max=2.0)
    report: bpy.props.StringProperty()
    face_report: bpy.props.StringProperty()


def _scales(settings):
    return {expressions.EYES: settings.eyes, expressions.BROWS: settings.brows,
            expressions.MOUTH: settings.mouth, expressions.TONGUE: settings.tongue}


def _categories(settings):
    return tuple(c for c, on in (("EYEBROW", settings.do_brows), ("EYE", settings.do_eyes),
                                 ("MOUTH", settings.do_mouth)) if on)


class MFM_OT_analyze(bpy.types.Operator):
    bl_idname = "mmd_face.analyze"
    bl_label = "Analyze face"
    bl_description = "Find the eyelid / brow / jaw / lip / tongue / teeth bones"

    def execute(self, context):
        settings = context.scene.mmd_face
        try:
            face = api.analyze_model(context.active_object)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        names = api.possible(face)
        roles = sorted(face.bones)
        settings.face_report = "%s | %d bones | %d/%d morphs possible" % (
            face.style, len(roles), len(names), len(expressions.MORPHS))
        settings.report = " ".join("%s=%s" % (r, face.bones[r]) for r in roles)
        print("[mmd_face] " + face.describe())
        return {"FINISHED"}


class MFM_OT_build(bpy.types.Operator):
    bl_idname = "mmd_face.build"
    bl_label = "Build morphs"
    bl_description = "Create the standard expression set as bone morphs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_face
        lines = []
        try:
            report = api.setup(context.active_object, categories=_categories(settings),
                               scales=_scales(settings), replace=settings.replace, log=lines.append)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for line in lines:
            print("[mmd_face] " + line)
        by = report["by_category"]
        settings.report = "%d morphs: %d 眉, %d 目, %d 口; %d skipped" % (
            len(report["morphs"]), len(by["EYEBROW"]), len(by["EYE"]), len(by["MOUTH"]),
            len(report["skipped"]))
        settings.face_report = "%s | unit %.3f" % (report["style"], report["unit"])
        if report["morphs"]:
            settings.morph = report["morphs"][0]
        return {"FINISHED"}


class MFM_OT_clear(bpy.types.Operator):
    bl_idname = "mmd_face.clear"
    bl_label = "Clear"
    bl_description = "Remove the morphs this add-on built"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            root, arm = build.model_of(context.active_object)
            build.reset_pose(root, arm)
            removed = build.clear(root)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.scene.mmd_face.report = "%d morphs removed" % len(removed)
        return {"FINISHED"}


class MFM_OT_preview(bpy.types.Operator):
    bl_idname = "mmd_face.preview"
    bl_label = "Preview"
    bl_description = "Pose the bones as the selected morph (at the weight); Reset puts them back"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_face
        try:
            root, arm = build.model_of(context.active_object)
            count = build.pose_morph(root, arm, settings.morph, settings.weight)
            root.mmd_root.active_morph_type = "bone_morphs"
            root.mmd_root.active_morph = root.mmd_root.bone_morphs.find(settings.morph)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.report = "%s: %d bones posed" % (settings.morph, count)
        return {"FINISHED"}


class MFM_OT_reset(bpy.types.Operator):
    bl_idname = "mmd_face.reset"
    bl_label = "Reset"
    bl_description = "Clear the pose of every bone any bone morph uses"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            root, arm = build.model_of(context.active_object)
            build.reset_pose(root, arm)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class MFM_PT_panel(bpy.types.Panel):
    bl_label = "Face Morphs"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mmd_face
        layout.operator("mmd_face.analyze", icon="VIEWZOOM")
        if settings.face_report:
            layout.label(text=settings.face_report)
        box = layout.box()
        row = box.row(align=True)
        row.prop(settings, "do_brows", toggle=True)
        row.prop(settings, "do_eyes", toggle=True)
        row.prop(settings, "do_mouth", toggle=True)
        col = box.column(align=True)
        col.prop(settings, "eyes")
        col.prop(settings, "brows")
        col.prop(settings, "mouth")
        col.prop(settings, "tongue")
        box.prop(settings, "replace")
        row = layout.row(align=True)
        row.operator("mmd_face.build", icon="SHADERFX")
        row.operator("mmd_face.clear", icon="TRASH")
        box = layout.box()
        box.prop(settings, "morph")
        box.prop(settings, "weight", slider=True)
        row = box.row(align=True)
        row.operator("mmd_face.preview", icon="HIDE_OFF")
        row.operator("mmd_face.reset", icon="LOOP_BACK")
        if settings.report:
            layout.label(text=settings.report)


CLASSES = (MFM_Settings, MFM_OT_analyze, MFM_OT_build, MFM_OT_clear, MFM_OT_preview,
           MFM_OT_reset, MFM_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mmd_face = bpy.props.PointerProperty(type=MFM_Settings)


def unregister():
    del bpy.types.Scene.mmd_face
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
