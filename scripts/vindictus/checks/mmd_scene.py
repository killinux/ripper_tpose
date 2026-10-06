"""Shared by the bust checks: a PMX imported with mmd_tools and its physics run the way MMD runs it.

mmd_tools builds every joint as a Blender Generic Spring with SPRING2 damping 0.5, copies the angular springs
without the import scale and leaves Blender's gravity - all three make a Blender preview stiffer than MMD
(scripts/mmd_physics/README.md).  mmd_like() undoes them: SPRING1 with no joint damping (Blender hands SPRING1
damping to Bullet inverted, 0 here = MMD's 1), angular springs x scale^2, gravity 98 model units/s^2 - the same
three changes as preview_pmx_blender.py --physics mmd - and gives every body the PMX masks against all groups
(a breast) a collision layer of its own, so a hand cannot hit it either (mmd_tools only keeps it out of the way
of bodies that touch it at rest)."""
import addon_utils
import bpy

SCALE = 0.08                 # export_pmx writes x12.5: back in metres
MARGIN = 30                  # rest pose -> first dance pose blend (see render_pmx_dance.py)


def load(pmx, types=("MESH", "ARMATURE", "PHYSICS", "DISPLAY")):
    bpy.ops.wm.read_homefile(use_empty=True)
    addon_utils.enable("mmd_tools", default_set=True)
    bpy.ops.mmd_tools.import_model(filepath=pmx, scale=SCALE, types=set(types))
    scene = bpy.context.scene
    root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
    from mmd_tools.core.model import Model

    rig = Model(root)
    root.mmd_root.show_rigid_bodies = False
    root.mmd_root.show_joints = False
    root.mmd_root.show_armature = False
    for obj in scene.objects:
        if getattr(obj, "mmd_type", "") in ("RIGID_BODY", "JOINT"):
            obj.hide_render = True
    return scene, root, rig, rig.armature()


def own_layers(scene):
    """Every body the PMX lets collide with nothing gets a collision layer of its own (19, 18, ...)."""
    layer = 19
    for obj in scene.objects:
        if getattr(obj, "mmd_type", "") == "RIGID_BODY" and obj.rigid_body \
                and all(obj.mmd_rigid.collision_group_mask) and layer > 0:
            obj.rigid_body.collision_collections = [i == layer for i in range(20)]
            layer -= 1
    return 19 - layer


def mmd_like(scene, gravity=98.0):
    """Build first (rig.build()); returns how many joints were converted."""
    converted = 0
    for obj in scene.objects:
        c = obj.rigid_body_constraint
        if c is not None and c.type == "GENERIC_SPRING":
            c.spring_type = "SPRING1"
            for axis in "xyz":
                setattr(c, "spring_damping_" + axis, 0.0)
                setattr(c, "spring_damping_ang_" + axis, 0.0)
                setattr(c, "spring_stiffness_ang_" + axis, getattr(c, "spring_stiffness_ang_" + axis) * SCALE * SCALE)
            converted += 1
    own_layers(scene)
    scene.gravity = (0.0, 0.0, -gravity * SCALE)
    return converted


def addon_like(scene, root):
    """The preview physics of the user's MMD Physics add-on (E:\\code\\othercode\\mmd_physics, preview.start): gravity
    9.8 model units/s^2, rotation springs x scale^2, SPRING2 joints with 10 % of critical damping on the axes that
    have a spring (its params.preview_joint) - plus own_layers(): the add-on's preview leaves the hands free to hit
    the bust (gesture dance: 44-58 deg against an 18 deg limit), which MMD does not.  Build first."""
    addon_utils.enable("mmd_physics", default_set=True)
    from mmd_physics import params, preview
    from mmd_tools.core.model import Model

    joints = list(Model(root).joints())
    for joint in joints:
        params.preview_joint(joint, SCALE * SCALE)
    own_layers(scene)
    scene.gravity = (0.0, 0.0, -preview.MMD_GRAVITY * SCALE)
    return len(joints)


def add_motion(root, vmd, frames=0):
    """The VMD on the model with a MARGIN-frame lead-in; ``frames`` > 0 caps the motion.  Make a camera after
    this: import_vmd moves one that is already in the scene."""
    scene = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root] + list(root.children_recursive):
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                                 update_scene_settings=True)
    scene.frame_start = 1
    if frames:
        scene.frame_end = min(scene.frame_end, MARGIN + frames)


def run_physics(scene):
    """Step the simulation frame by frame from the first frame (what a render must read)."""
    world = scene.rigidbody_world
    world.enabled = True
    world.point_cache.frame_start, world.point_cache.frame_end = scene.frame_start, scene.frame_end
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        yield frame


def breast_bones(arm, scene):
    """The swinging breast bones that have a dynamic body (UE: breast_physics_02_*, Biped: Bip001_*_bust_2)."""
    dynamic = {o.mmd_rigid.bone for o in scene.objects
               if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.type != "0"}
    return [pb for pb in arm.pose.bones if pb.name in dynamic
            and (pb.name.startswith("breast_physics_02") or pb.name.endswith("_bust_2"))]


def swing_deg(pb):
    """Rotation of a pose bone relative to its parent, compared with their rest relation (degrees)."""
    import math

    rel = pb.parent.matrix.inverted() @ pb.matrix
    rest = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
    return math.degrees((rest.inverted() @ rel).to_quaternion().angle)
