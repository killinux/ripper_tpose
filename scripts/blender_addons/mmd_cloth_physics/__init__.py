"""MMD Cloth Physics - lattice rigid bodies, presets and a drop test for
mmd_tools models.

Blender add-on package.  The UI lives in the 3D viewport sidebar under the
"MMD" tab (next to mmd_tools' own panels); scripts use ``api.setup``.
"""
bl_info = {
    "name": "MMD Cloth Physics",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > MMD > Cloth Physics",
    "description": "Skirt/cape/ribbon/hair rigid bodies and joints for mmd_tools models: "
                   "garments found by shape, PMXEditor-style lattice, presets, drop test",
    "category": "Object",
}

import bpy

from . import api, build, validate
from .presets import PRESET_ITEMS

_garments = []      # analysis result of the last Analyze, index-aligned with the UI list


class MCP_GarmentItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()
    summary: bpy.props.StringProperty()
    preset: bpy.props.EnumProperty(items=PRESET_ITEMS, name="Preset")
    enabled: bpy.props.BoolProperty(default=True)


class MCP_Settings(bpy.types.PropertyGroup):
    body_regex: bpy.props.StringProperty(
        name="Body bone regex", default=r"^Bip0\d\d\b",
        description="Bones of the body skeleton besides the MMD standard ones "
                    "(3ds Max Biped keeps its prefix)")
    prop_regex: bpy.props.StringProperty(
        name="Prop bone regex", default=r"\bProp\d*$",
        description="Anything under a bone matching this is a held prop, never cloth")
    include_hair: bpy.props.BoolProperty(name="Hair too", default=True)
    lattice: bpy.props.BoolProperty(
        name="Lattice joints", default=True,
        description="Horizontal joints between neighbouring chains of a skirt or sheet")
    reverse_joints: bpy.props.BoolProperty(
        name="Reverse lattice joints", default=False,
        description="Add each horizontal joint a second time with A and B swapped "
                    "(PMXEditor 裏ジョイント), for a stiffer, more stable surface")
    measure_skin: bpy.props.BoolProperty(
        name="Size from skin", default=True,
        description="Rigid body width/thickness from the vertices the bone drives")
    thickness_scale: bpy.props.FloatProperty(
        name="Thickness", default=1.0, min=0.3, max=4.0,
        description="Scale of the box thickness (thicker stops legs poking through)")
    drop_frames: bpy.props.IntProperty(name="Drop test frames", default=60, min=10, max=600)
    garments: bpy.props.CollectionProperty(type=MCP_GarmentItem)
    active: bpy.props.IntProperty()
    report: bpy.props.StringProperty()


def _sync_ui(settings, garments):
    settings.garments.clear()
    for garment in garments:
        item = settings.garments.add()
        item.name = garment.name
        item.kind = garment.kind
        item.preset = garment.preset
        item.enabled = garment.enabled
        item.summary = "%s  %d chains x %d rows, %d bones, %d pairs" % (
            garment.kind, len(garment.chains), garment.depth, len(garment.bones),
            len(garment.pairs))


def _sync_back(settings, garments):
    for item, garment in zip(settings.garments, garments):
        garment.preset = item.preset
        garment.enabled = item.enabled


class MCP_OT_analyze(bpy.types.Operator):
    bl_idname = "mmd_cloth.analyze"
    bl_label = "Analyze garments"
    bl_description = "Find cloth chains by shape and guess a preset for each"

    def execute(self, context):
        settings = context.scene.mmd_cloth
        try:
            garments = api.analyze_model(context.active_object, settings.body_regex or None,
                                         settings.prop_regex or None, settings.include_hair)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _garments[:] = garments
        _sync_ui(settings, garments)
        settings.report = "%d garments" % len(garments)
        return {"FINISHED"}


class MCP_OT_build(bpy.types.Operator):
    bl_idname = "mmd_cloth.build"
    bl_label = "Build physics"
    bl_description = "Rigid bodies and joints for the enabled garments (Analyze first)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_cloth
        if not _garments:
            bpy.ops.mmd_cloth.analyze()
        _sync_back(settings, _garments)
        lines = []
        try:
            report = api.setup(context.active_object, garments=_garments,
                               body_regex=settings.body_regex or None,
                               prop_regex=settings.prop_regex or None,
                               include_hair=settings.include_hair, lattice=settings.lattice,
                               reverse_joints=settings.reverse_joints,
                               measure_skin=settings.measure_skin,
                               thickness_scale=settings.thickness_scale, log=lines.append)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.report = "%d rigid bodies, %d joints (%d lattice)" % (
            report["rigid_bodies"], report["joints"], report["lattice"])
        for line in lines:
            print(line)
        return {"FINISHED"}


class MCP_OT_strip(bpy.types.Operator):
    bl_idname = "mmd_cloth.strip"
    bl_label = "Strip dynamic physics"
    bl_description = ("Delete every dynamic rigid body and joint the model came with "
                      "(body colliders stay), so Analyze can see the cloth bones again")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = build.with_world_off(build.strip_dynamic_physics)
        _garments[:] = []
        context.scene.mmd_cloth.garments.clear()
        context.scene.mmd_cloth.report = "stripped %d rigid bodies / joints" % removed
        return {"FINISHED"}


class MCP_OT_clear(bpy.types.Operator):
    bl_idname = "mmd_cloth.clear"
    bl_label = "Clear"
    bl_description = "Delete the rigid bodies and joints this add-on built (colliders stay)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = build.with_world_off(lambda: build.clear_garment_physics())
        context.scene.mmd_cloth.report = "removed %d objects" % removed
        return {"FINISHED"}


class MCP_OT_colliders(bpy.types.Operator):
    bl_idname = "mmd_cloth.colliders"
    bl_label = "Body colliders"
    bl_description = "Kinematic capsules on the standard body bones that have none"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            model, root, arm, meshes = api.model_of(context.active_object)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        made = build.with_world_off(lambda: build.ensure_body_colliders(model, arm, meshes))
        context.scene.mmd_cloth.report = "%d colliders created" % made
        return {"FINISHED"}


class MCP_OT_drop_test(bpy.types.Operator):
    bl_idname = "mmd_cloth.drop_test"
    bl_label = "Drop test"
    bl_description = ("Build the physics, let it settle for N frames in the rest pose and "
                      "report how far every rigid body drifted (save first)")

    def execute(self, context):
        settings = context.scene.mmd_cloth
        try:
            result = validate.drop_test(context.active_object, settings.drop_frames)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.report = result["summary"]
        for line in result["lines"]:
            print(line)
        return {"FINISHED"}


class MCP_UL_garments(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text=item.name)
        row.prop(item, "preset", text="")


class MCP_PT_panel(bpy.types.Panel):
    bl_label = "Cloth Physics"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        settings = context.scene.mmd_cloth
        layout = self.layout
        col = layout.column(align=True)
        col.prop(settings, "body_regex")
        col.prop(settings, "prop_regex")
        row = col.row(align=True)
        row.prop(settings, "include_hair")
        row.prop(settings, "lattice")
        row = col.row(align=True)
        row.prop(settings, "reverse_joints")
        row.prop(settings, "measure_skin")
        col.prop(settings, "thickness_scale")
        row = layout.row(align=True)
        row.operator("mmd_cloth.strip", icon="X")
        row.operator("mmd_cloth.analyze", icon="VIEWZOOM")
        layout.template_list("MCP_UL_garments", "", settings, "garments", settings, "active",
                             rows=4)
        if 0 <= settings.active < len(settings.garments):
            layout.label(text=settings.garments[settings.active].summary)
        row = layout.row(align=True)
        row.operator("mmd_cloth.colliders", icon="MESH_CAPSULE")
        row.operator("mmd_cloth.build", icon="PHYSICS")
        row.operator("mmd_cloth.clear", icon="TRASH")
        row = layout.row(align=True)
        row.prop(settings, "drop_frames")
        row.operator("mmd_cloth.drop_test", icon="PLAY")
        if settings.report:
            layout.label(text=settings.report)


CLASSES = (MCP_GarmentItem, MCP_Settings, MCP_OT_analyze, MCP_OT_build, MCP_OT_strip,
           MCP_OT_clear, MCP_OT_colliders, MCP_OT_drop_test, MCP_UL_garments, MCP_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mmd_cloth = bpy.props.PointerProperty(type=MCP_Settings)


def unregister():
    del bpy.types.Scene.mmd_cloth
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
