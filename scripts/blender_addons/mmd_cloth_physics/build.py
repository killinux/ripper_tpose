"""Turn garments into mmd_tools rigid bodies and joints.

Conventions that MMD itself cares about (all learned the hard way, see the
README's pitfalls):

* rigid body and joint empties are ``rotation_mode='YXZ'``, so every Euler
  handed to mmd_tools is ``to_euler('YXZ')``;
* a BOX is placed with local Y along the bone (half length), X outward
  (half thickness), Z along the surface (half width);
* a CAPSULE's long axis is local Z;
* a cloth joint's frame is X = tangent, Y = radial, Z = along the bone.  MMD's
  old Bullet decomposes 6DOF limits with Y as the singular axis, so the axis
  with the small twist limit has to land on PMX Y (= Blender Z) or a fast turn
  blows the whole skirt up.  Blender's newer Bullet tolerates anything, which
  is why Blender never shows this failure;
* the rigid body world is switched off while objects are created: with it on,
  every new dynamic body is stepped the moment the scene evaluates and its
  bind position drifts before the PMX is written.
"""
import math

import bpy
from mathutils import Matrix, Vector

from . import analyze
from .presets import PRESETS, lerp

TAG = "mmd_cloth_physics"

MODE_STATIC, MODE_DYNAMIC, MODE_DYNAMIC_BONE = 0, 1, 2
SHAPE_SPHERE, SHAPE_BOX, SHAPE_CAPSULE = 0, 1, 2

GROUP_BODY = 0
GROUP_HAIR = 9
GROUP_NEAR = 10          # cloth that starts inside the body: collides with nothing
GROUP_CLOTH = 11         # free cloth: collides with the body only
NOCOLLIDE_CLOTH = (1, 8, 9, 10, 11, 15)
NOCOLLIDE_NEAR = (0, 1, 8, 9, 10, 11, 15)
NOCOLLIDE_BODY = (GROUP_NEAR,)

BODY_COLLIDERS = (
    # bone, shape, radius ratio of bone length when the skin cannot be measured
    ("頭", SHAPE_SPHERE, 0.9), ("首", SHAPE_CAPSULE, 0.35),
    ("上半身", SHAPE_CAPSULE, 0.45), ("上半身2", SHAPE_CAPSULE, 0.5),
    ("上半身3", SHAPE_CAPSULE, 0.5), ("下半身", SHAPE_CAPSULE, 0.5),
    ("左肩", SHAPE_CAPSULE, 0.4), ("右肩", SHAPE_CAPSULE, 0.4),
    ("左腕", SHAPE_CAPSULE, 0.22), ("右腕", SHAPE_CAPSULE, 0.22),
    ("左ひじ", SHAPE_CAPSULE, 0.18), ("右ひじ", SHAPE_CAPSULE, 0.18),
    ("左足", SHAPE_CAPSULE, 0.22), ("右足", SHAPE_CAPSULE, 0.22),
    ("左ひざ", SHAPE_CAPSULE, 0.16), ("右ひざ", SHAPE_CAPSULE, 0.16),
)


def mask16(no_collide):
    return [i in no_collide for i in range(16)]


def find_bone(arm, name):
    """A standard bone by its Japanese name, tolerating mmd_tools' .L/.R rename."""
    bones = arm.data.bones
    bone = bones.get(name)
    if bone is not None:
        return bone
    for side, suffix in (("左", ".L"), ("右", ".R")):
        if name.startswith(side):
            bone = bones.get(name[len(side):] + suffix)
            if bone is not None:
                return bone
    for bone in bones:
        if getattr(bone, "mmd_bone", None) is not None and bone.mmd_bone.name_j == name:
            return bone
    for pbone in arm.pose.bones:
        if pbone.mmd_bone.name_j == name:
            return pbone.bone
    return None


def bone_name_j(arm, bone):
    pbone = arm.pose.bones.get(bone.name)
    if pbone is not None and pbone.mmd_bone.name_j:
        return pbone.mmd_bone.name_j
    return bone.name


# ----------------------------------------------------------------- frames --

def box_frame(head, vec, center):
    """(centre, euler YXZ, axes) for a BOX: Y along, X outward, Z tangent."""
    y = vec.normalized()
    centre = head + vec * 0.5
    radial = Vector((centre.x - center.x, centre.y - center.y, 0.0))
    if radial.length < 1e-5:
        radial = Vector((0.0, -1.0, 0.0))
    x = radial.normalized()
    z = y.cross(x)
    if z.length < 1e-5:
        z = Vector((1.0, 0.0, 0.0))
    z.normalize()
    x = z.cross(y).normalized()
    return centre, Matrix((x, y, z)).transposed().to_euler("YXZ"), (x, y, z)


def capsule_frame(vec):
    """Euler YXZ with local Z along ``vec``."""
    z = vec.normalized() if vec.length > 1e-6 else Vector((0, 0, 1))
    ref = Vector((1, 0, 0)) if abs(z.x) < 0.9 else Vector((0, 0, 1))
    y = z.cross(ref).normalized()
    x = y.cross(z).normalized()
    return Matrix((x, y, z)).transposed().to_euler("YXZ")


def joint_frame(vec, centre, center):
    """Cloth joint: X tangent, Y radial, Z along the bone."""
    z = vec.normalized()
    radial = Vector((centre.x - center.x, centre.y - center.y, 0.0))
    if radial.length < 1e-5:
        radial = Vector((0.0, -1.0, 0.0))
    x = radial.cross(z)
    if x.length < 1e-5:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed().to_euler("YXZ")


def lattice_frame(centre_a, centre_b, along):
    """Horizontal joint: X from A to B, Z along the cloth, Y their cross."""
    z = along.normalized() if along.length > 1e-6 else Vector((0, 0, -1))
    x = centre_b - centre_a
    x = x - z * x.dot(z)
    if x.length < 1e-5:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed().to_euler("YXZ")


# ------------------------------------------------------------ colliders --

def existing_rigids():
    return {obj.mmd_rigid.bone: obj for obj in bpy.data.objects
            if getattr(obj, "mmd_type", "") == "RIGID_BODY" and obj.mmd_rigid.bone}


def kinematic_shapes():
    """(centre, axis, half height, radius) of every kinematic rigid body, for
    the 'does this cloth segment start inside the body' test."""
    shapes = []
    for obj in bpy.data.objects:
        if getattr(obj, "mmd_type", "") != "RIGID_BODY":
            continue
        if str(obj.mmd_rigid.type) not in ("0", "STATIC"):
            continue
        size = obj.mmd_rigid.size
        mw = obj.matrix_world
        if obj.mmd_rigid.shape == "CAPSULE":
            axis = (mw.to_3x3() @ Vector((0, 0, 1))).normalized()
            shapes.append((mw.translation.copy(), axis, max(size[1] * 0.5, 0.0), size[0]))
        elif obj.mmd_rigid.shape == "SPHERE":
            shapes.append((mw.translation.copy(), Vector((0, 0, 1)), 0.0, size[0]))
        else:
            shapes.append((mw.translation.copy(), Vector((0, 0, 1)), 0.0,
                           math.sqrt(size[0] ** 2 + size[1] ** 2 + size[2] ** 2)))
    return shapes


def near_body(shapes, centre, half_diag, margin=0.03):
    for c, axis, hh, r in shapes:
        rel = centre - c
        t = max(-hh, min(hh, rel.dot(axis)))
        if (rel - axis * t).length < r + half_diag + margin:
            return True
    return False


def measured_radius(arm, meshes, bone, weight_min=0.3):
    """85th percentile of the radial distance to the bone axis over the vertices
    it drives; None when there are too few."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    axis = ((mw @ bone.tail_local) - head)
    if axis.length < 1e-6:
        return None
    axis.normalize()
    distances = []
    for mesh in meshes:
        group = mesh.vertex_groups.get(bone.name)
        if group is None:
            continue
        index = group.index
        mwm = mesh.matrix_world
        for vertex in mesh.data.vertices:
            for item in vertex.groups:
                if item.group == index and item.weight >= weight_min:
                    rel = (mwm @ vertex.co) - head
                    distances.append((rel - axis * rel.dot(axis)).length)
                    break
    if len(distances) < 12:
        return None
    distances.sort()
    return distances[int(len(distances) * 0.85)]


def make_kinematic(model, arm, meshes, bone, ratio=0.3, unit=1.0):
    """A kinematic collider/anchor on ``bone`` (capsule along it)."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    vec = (mw @ bone.tail_local) - head
    length = vec.length or 0.05 * unit
    radius = measured_radius(arm, meshes, bone) or length * ratio
    radius = max(0.015 * unit, min(radius, 0.25 * unit))
    obj = model.createRigidBody(
        shape_type=SHAPE_CAPSULE, location=head + vec * 0.5, rotation=capsule_frame(vec),
        size=(radius, length, 0.0), dynamics_type=MODE_STATIC,
        collision_group_number=GROUP_BODY, collision_group_mask=mask16(NOCOLLIDE_BODY),
        name=bone_name_j(arm, bone), bone=bone.name,
        mass=1.0, friction=0.5, linear_damping=0.5, angular_damping=0.5, bounce=0.0)
    obj[TAG] = "body"
    return obj


def ensure_body_colliders(model, arm, meshes, log=None, unit=None):
    """Kinematic capsules on the standard body bones that have none yet."""
    if unit is None:
        unit = analyze.unit_scale(meshes)
    have = existing_rigids()
    made = 0
    for name, shape, ratio in BODY_COLLIDERS:
        bone = find_bone(arm, name)
        if bone is None or bone.name in have:
            continue
        if shape == SHAPE_SPHERE:
            mw = arm.matrix_world
            head = mw @ bone.head_local
            vec = (mw @ bone.tail_local) - head
            radius = measured_radius(arm, meshes, bone) or vec.length * ratio
            obj = model.createRigidBody(
                shape_type=SHAPE_SPHERE, location=head + vec * 0.5, rotation=(0.0, 0.0, 0.0),
                size=(max(0.03 * unit, min(radius, 0.2 * unit)), 0.0, 0.0),
                dynamics_type=MODE_STATIC,
                collision_group_number=GROUP_BODY, collision_group_mask=mask16(NOCOLLIDE_BODY),
                name=name, bone=bone.name,
                mass=1.0, friction=0.5, linear_damping=0.5, angular_damping=0.5, bounce=0.0)
            obj[TAG] = "body"
        else:
            make_kinematic(model, arm, meshes, bone, ratio, unit)
        made += 1
    if log:
        log("body colliders: %d created, %d already there" % (made, len(have)))
    return made


# ------------------------------------------------------------- garments --

def rigid_size(preset, shape, half_len, extent, unit=1.0):
    """BOX: (half thickness, half length, half width); CAPSULE: (radius, height, 0).
    Absolute sizes are metres times ``unit``."""
    if shape == SHAPE_CAPSULE:
        radius = extent[0] if extent else half_len * 0.35
        radius = max(0.012 * unit, min(radius, 0.06 * unit, half_len * 1.2 + 0.01 * unit))
        return (radius, max(0.02 * unit, half_len * 2.0), 0.0)
    half_thick = max(0.008 * unit, preset["thickness"] * unit * 0.5
                     + (extent[1] * 0.3 if extent else 0.0))
    half_width = (extent[0] if extent else half_len * 0.75)
    half_width = max(0.015 * unit, min(half_width, 0.3 * unit))
    return (min(half_thick, 0.04 * unit), max(0.015 * unit, half_len), half_width)


def build_garment(model, arm, meshes, garment, options, log=None):
    """Rigid bodies + joints for one garment.  Returns (rigids, joints, lattice)."""
    preset = PRESETS[garment.preset]
    shape = SHAPE_CAPSULE if preset["shape"] == "CAPSULE" else SHAPE_BOX
    bones = arm.data.bones
    rows = garment.depth
    members = set(garment.bones)
    have = existing_rigids()
    shapes = kinematic_shapes()
    is_hair = garment.preset == "hair"
    lattice_on = options.get("lattice", True) and preset["lattice"]
    reverse = options.get("reverse_joints", False)
    thickness_scale = options.get("thickness_scale", 1.0)
    unit = options.get("unit", 1.0)

    # anchor rigid body: the garment hangs off it
    anchor_bone = bones.get(garment.anchor) or find_bone(arm, garment.anchor)
    anchor_rigid = have.get(anchor_bone.name) if anchor_bone is not None else None
    if anchor_rigid is None and anchor_bone is not None:
        anchor_rigid = make_kinematic(model, arm, meshes, anchor_bone, unit=unit)
        have[anchor_bone.name] = anchor_rigid

    rigids, joints, lattice = 0, 0, 0
    geometry = {}
    for name in garment.bones:              # parents first
        bone = bones[name]
        row = garment.rows[name]
        head, vec = analyze.segment(arm, bone, members)
        half_len = min(vec.length * 0.5, 0.25 * unit)
        if shape == SHAPE_BOX:
            centre, euler, axes = box_frame(head, vec, garment.center)
        else:
            centre, euler, axes = head + vec * 0.5, capsule_frame(vec), None
        extent = None
        if options.get("measure_skin", True):
            frame_axes = axes or (Vector((1, 0, 0)), vec.normalized(), Vector((0, 1, 0)))
            extent = analyze.skin_extent(arm, meshes, name, frame_axes, head, vec)
        size = rigid_size(preset, shape, half_len, extent, unit)
        if shape == SHAPE_BOX:
            size = (min(0.05 * unit, size[0] * thickness_scale), size[1], size[2])
        half_diag = math.sqrt(sum(s * s for s in size[:2]))
        if is_hair:
            group, mask = GROUP_HAIR, mask16(NOCOLLIDE_CLOTH)
        elif row == 0 or near_body(shapes, centre, half_diag, 0.03 * unit):
            group, mask = GROUP_NEAR, mask16(NOCOLLIDE_NEAR)
        else:
            group, mask = GROUP_CLOTH, mask16(NOCOLLIDE_CLOTH)
        mode = preset["root_mode"] if row == 0 else MODE_DYNAMIC
        rigid = have.get(name)
        if rigid is None:
            rigid = model.createRigidBody(
                shape_type=shape, location=centre, rotation=euler, size=size,
                dynamics_type=mode, collision_group_number=group, collision_group_mask=mask,
                name=name, bone=name,
                mass=lerp(preset["mass"], row, rows), friction=preset["friction"],
                linear_damping=lerp(preset["lin_damp"], row, rows),
                angular_damping=lerp(preset["ang_damp"], row, rows), bounce=0.0)
            rigid[TAG] = garment.name
            have[name] = rigid
            rigids += 1
        geometry[name] = (head, vec, centre)

        parent = bone.parent
        parent_rigid = have.get(parent.name) if parent is not None and parent.name in members else anchor_rigid
        if parent_rigid is None:
            continue
        swing = math.radians(lerp(preset["swing"], row, rows))
        side = math.radians(lerp(preset["side"], row, rows))
        twist = math.radians(lerp(preset["twist"], row, rows))
        spring = lerp(preset["spring"], row, rows)
        # springs scale with segment length squared (inertia), as the reference
        # implementation found necessary for solver stability on short links
        spring *= min(1.0, max(0.02, (vec.length / (0.15 * unit)) ** 2))
        rotation = (0.0, 0.0, 0.0) if is_hair else joint_frame(vec, centre, garment.center)
        joint = model.createJoint(
            location=head, rotation=rotation, rigid_a=parent_rigid, rigid_b=rigid,
            maximum_location=(0.0, 0.0, 0.0), minimum_location=(0.0, 0.0, 0.0),
            maximum_rotation=(swing, side, twist), minimum_rotation=(-swing, -side, -twist),
            spring_linear=(0.0, 0.0, 0.0), spring_angular=(spring, spring, spring),
            name=name)
        joint[TAG] = garment.name
        joints += 1

    if lattice_on:
        lin = preset["lattice_lin"] * unit
        ang = tuple(math.radians(a) for a in preset["lattice_ang"])
        for name_a, name_b in garment.pairs:
            if name_a not in have or name_b not in have or name_a not in geometry:
                continue
            head_a, vec_a, centre_a = geometry[name_a]
            head_b, vec_b, centre_b = geometry[name_b]
            mid = (centre_a + centre_b) * 0.5
            rotation = lattice_frame(centre_a, centre_b, vec_a + vec_b)
            links = [(have[name_a], have[name_b], "H.%s-%s" % (name_a, name_b))]
            if reverse:
                links.append((have[name_b], have[name_a], "R.%s-%s" % (name_b, name_a)))
            for rigid_a, rigid_b, label in links:
                joint = model.createJoint(
                    location=mid, rotation=rotation, rigid_a=rigid_a, rigid_b=rigid_b,
                    maximum_location=(lin, lin, lin), minimum_location=(-lin, -lin, -lin),
                    maximum_rotation=ang, minimum_rotation=tuple(-a for a in ang),
                    spring_linear=(0.0, 0.0, 0.0), spring_angular=(0.0, 0.0, 0.0),
                    name=label)
                joint[TAG] = garment.name
                lattice += 1
    if log:
        log("%-28s %-6s %-8s chains %2d rows %d: %3d rigid bodies, %3d joints, %3d lattice"
            % (garment.name, garment.kind, garment.preset, len(garment.chains), rows,
               rigids, joints, lattice))
    return rigids, joints, lattice


def strip_dynamic_physics():
    """Delete every dynamic rigid body and every joint (whoever made them), so a
    PMX that already ships physics can be rebuilt; kinematic body colliders stay."""
    doomed = [obj for obj in bpy.data.objects
              if getattr(obj, "mmd_type", "") == "JOINT"
              or (getattr(obj, "mmd_type", "") == "RIGID_BODY"
                  and str(obj.mmd_rigid.type) not in ("0", "STATIC"))]
    for obj in doomed:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(doomed)


def clear_garment_physics(garment_names=None):
    """Delete rigid bodies and joints this add-on created (all of them when
    ``garment_names`` is None); body colliders it made are kept."""
    doomed = []
    for obj in bpy.data.objects:
        tag = obj.get(TAG)
        if tag is None or tag == "body":
            continue
        if garment_names is None or tag in garment_names:
            doomed.append(obj)
    for obj in doomed:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(doomed)


def with_world_off(func):
    """Run ``func`` with the scene's rigid body world disabled."""
    scene = bpy.context.scene
    world = scene.rigidbody_world
    was = world.enabled if world is not None else None
    if world is not None:
        world.enabled = False
    try:
        return func()
    finally:
        if world is not None and was is not None:
            world.enabled = was
