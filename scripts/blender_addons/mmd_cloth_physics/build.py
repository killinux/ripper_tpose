"""Turn garments into mmd_tools rigid bodies and joints.

Conventions that MMD itself cares about (all learned the hard way, see the
README's pitfalls):

* rigid body and joint empties are ``rotation_mode='YXZ'``, so every Euler
  handed to mmd_tools is ``to_euler('YXZ')`` of a proper (right-handed)
  rotation: a mirrored frame comes back from ``to_euler`` spun about one axis;
* a BOX is placed with local Y along the bone (half length), X across the
  cloth (half thickness, pointing away from the body), Z along the surface
  (half width).  X is the normal of the cloth the bone drives when the skin
  gives one, else the horizontal direction away from the anchor;
* a CAPSULE's long axis is local Z;
* a cloth joint's frame is X = tangent, Y = the cloth's normal (radial), Z =
  along the bone.  MMD's old Bullet decomposes 6DOF limits with Y as the
  singular axis, so the axis with the small twist limit has to land on PMX Y
  (= Blender Z) or a fast turn blows the whole skirt up.  Blender's newer
  Bullet tolerates anything, which is why Blender never shows this failure;
* the rigid body world is switched off while objects are created: with it on,
  every new dynamic body is stepped the moment the scene evaluates and its
  bind position drifts before the PMX is written.

Until 2026-10-18 ``box_frame`` built (x, y, y x x): a mirrored frame.  Its
Euler kept the box's length on the bone but spun it about the bone by up to
90 deg, so on 44% of the ROE models' boxes the thin side faced sideways - fins
sticking out of the skirt that a thigh slid past into the cloth (Inase a08).
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import analyze, collide, geom
from .presets import PRESETS, lerp

TAG = "mmd_cloth_physics"
RIDES = TAG + "_rides"       # set on bodies whose garment hangs on a physics body (a breast): they collide with nothing

MODE_STATIC, MODE_DYNAMIC, MODE_DYNAMIC_BONE = 0, 1, 2
SHAPE_SPHERE, SHAPE_BOX, SHAPE_CAPSULE = 0, 1, 2

GROUP_BODY = 0
GROUP_HAIR = 9
GROUP_NEAR = 10          # cloth that starts inside the body: collides with nothing
GROUP_CLOTH = 11         # free cloth: collides with the body only
NOCOLLIDE_CLOTH = (1, 8, 9, 10, 11, 15)
NOCOLLIDE_NEAR = (0, 1, 8, 9, 10, 11, 15)
NOCOLLIDE_BODY = (GROUP_NEAR,)
GLUED = 8                # shared vertices that make a chain's end glued to another body
GLUED_PER_END = 3        # bodies one chain end may be sewn onto (Eve's front hair: its root and the next strand)

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

def box_frame(head, vec, center, normal=None, inward=None):
    """(centre, euler YXZ, axes) for a BOX: Y along, X across the cloth, Z along the surface - right-handed.

    X is ``normal`` (the cloth's own normal) made square to the bone, else the horizontal direction from the anchor
    ``center``; it points away from the body: against ``inward`` (towards the nearest body collider) when given."""
    y = vec.normalized()
    centre = head + vec * 0.5
    x = None
    if normal is not None:
        x = normal - y * normal.dot(y)
        if x.length < 0.3:
            x = None                       # a normal along the bone says nothing about the thickness
    if x is None:
        x = Vector((centre.x - center.x, centre.y - center.y, 0.0))
        x = x - y * x.dot(y)
    if x.length < 1e-5:
        x = y.orthogonal()
    x.normalize()
    out = -inward if inward is not None else Vector((centre.x - center.x, centre.y - center.y, 0.0))
    if out.length > 1e-6 and x.dot(out) < 0:
        x = -x
    z = x.cross(y).normalized()
    return centre, Matrix((x, y, z)).transposed().to_euler("YXZ"), (x, y, z)


def capsule_frame(vec):
    """Euler YXZ with local Z along ``vec``."""
    z = vec.normalized() if vec.length > 1e-6 else Vector((0, 0, 1))
    ref = Vector((1, 0, 0)) if abs(z.x) < 0.9 else Vector((0, 0, 1))
    y = z.cross(ref).normalized()
    x = y.cross(z).normalized()
    return Matrix((x, y, z)).transposed().to_euler("YXZ")


def joint_frame(vec, centre, center, normal=None):
    """Cloth joint: X tangent, Y radial (the cloth's normal when given), Z along the bone."""
    z = vec.normalized()
    radial = normal if normal is not None else Vector((centre.x - center.x, centre.y - center.y, 0.0))
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


def measured_radius(arm, meshes, bone, weight_min=0.3, skin=None):
    """85th percentile of the radial distance to the bone axis over the vertices
    it drives; None when there are too few."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    axis = ((mw @ bone.tail_local) - head)
    if axis.length < 1e-6:
        return None
    axis.normalize()
    if skin is not None:
        pts = skin.points(bone.name, weight_min) - np.array(head)
        if len(pts) < 12:
            return None
        a = np.array(axis)
        return float(np.percentile(np.linalg.norm(pts - np.outer(pts @ a, a), axis=1), 85))
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


def make_kinematic(model, arm, meshes, bone, ratio=0.3, unit=1.0, skin=None):
    """A kinematic collider/anchor on ``bone`` (capsule along it)."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    vec = (mw @ bone.tail_local) - head
    length = vec.length or 0.05 * unit
    radius = measured_radius(arm, meshes, bone, skin=skin) or length * ratio
    radius = max(0.015 * unit, min(radius, 0.25 * unit))
    obj = model.createRigidBody(
        shape_type=SHAPE_CAPSULE, location=head + vec * 0.5, rotation=capsule_frame(vec),
        size=(radius, length, 0.0), dynamics_type=MODE_STATIC,
        collision_group_number=GROUP_BODY, collision_group_mask=mask16(NOCOLLIDE_BODY),
        name=bone_name_j(arm, bone), bone=bone.name,
        mass=1.0, friction=0.5, linear_damping=0.5, angular_damping=0.5, bounce=0.0)
    obj[TAG] = "body"
    return obj


def ensure_body_colliders(model, arm, meshes, log=None, unit=None, skin=None):
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
            radius = measured_radius(arm, meshes, bone, skin=skin) or vec.length * ratio
            obj = model.createRigidBody(
                shape_type=SHAPE_SPHERE, location=head + vec * 0.5, rotation=(0.0, 0.0, 0.0),
                size=(max(0.03 * unit, min(radius, 0.2 * unit)), 0.0, 0.0),
                dynamics_type=MODE_STATIC,
                collision_group_number=GROUP_BODY, collision_group_mask=mask16(NOCOLLIDE_BODY),
                name=name, bone=bone.name,
                mass=1.0, friction=0.5, linear_damping=0.5, angular_damping=0.5, bounce=0.0)
            obj[TAG] = "body"
        else:
            make_kinematic(model, arm, meshes, bone, ratio, unit, skin)
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


def fit_box(points, axes, half_len, leaf, preset, unit, thickness_scale):
    """Half sizes and offset of a box that holds the cloth its bone drives (``points``, relative to the segment's
    middle): across the cloth (X) its spread between percentiles 5 and 95 plus the preset's thickness - never thicker
    than wide - along the surface (Z) the same span, along the bone (Y) the segment; for a chain's last bone down to
    the hem, which hangs below the bone's tail (up to 3x the half segment or 15 cm).  Returns ((half X, half Y,
    half Z), (offset X, Y, Z))."""
    dx, dy, dz = (points @ np.array(a) for a in axes)
    x_lo, x_hi = np.percentile(dx, [5, 95])
    z_lo, z_hi = np.percentile(dz, [5, 95])
    half_w = max(0.015 * unit, min(0.3 * unit, (z_hi - z_lo) * 0.5))
    half_t = max(0.008 * unit, min(0.04 * unit, half_w, (x_hi - x_lo) * 0.5 + preset["thickness"] * unit * 0.5))
    half_t = min(0.05 * unit, half_t * thickness_scale)
    shift_y = 0.0
    if leaf:
        reach = min(float(np.percentile(dy, 95)), max(3.0 * half_len, 0.15 * unit))
        if reach > half_len:
            shift_y = (reach - half_len) * 0.5
            half_len = (reach + half_len) * 0.5
    return ((float(half_t), float(max(0.015 * unit, half_len)), float(half_w)),
            (float(x_lo + x_hi) * 0.5, shift_y, float(z_lo + z_hi) * 0.5))


def seat_box(centre, axes, size, euler, offset, colliders, tolerance):
    """The box moved onto its cloth by ``offset`` (X, Y, Z in its frame) - but never deeper into a body collider
    than it would sit on the bone (or than ``tolerance``): the move across the cloth is cut back first."""
    x, y, z = axes
    along = centre + y * offset[1] + z * offset[2]
    if not colliders or abs(offset[0]) < 1e-6:
        return along + x * offset[0]
    R = np.array(euler.to_matrix())

    def deepest(c):
        s = geom.Shape(geom.BOX, np.array(c), R, size)
        return max(geom.depth(s, k) for k in colliders)

    start = max(deepest(along), tolerance)
    for share in (1.0, 0.75, 0.5, 0.25):
        moved = along + x * (offset[0] * share)
        if deepest(moved) <= start:
            return moved
    return along


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
    skin = options.get("skin")
    colliders = options.get("colliders") or []
    by_part = options.get("collision", "classes") == "classes"
    seat = options.get("seat", True)
    chain_joints = options.setdefault("chain_joints", {})

    # anchor rigid body: the garment hangs off it
    anchor_bone = bones.get(garment.anchor) or find_bone(arm, garment.anchor)
    anchor_rigid = have.get(anchor_bone.name) if anchor_bone is not None else None
    if anchor_rigid is None and anchor_bone is not None:
        anchor_rigid = make_kinematic(model, arm, meshes, anchor_bone, unit=unit, skin=skin)
        have[anchor_bone.name] = anchor_rigid
    rides = anchor_rigid is not None and str(anchor_rigid.mmd_rigid.type) not in ("0", "STATIC")

    rigids, joints, lattice = 0, 0, 0
    geometry = {}
    for name in garment.bones:              # parents first
        bone = bones[name]
        row = garment.rows[name]
        head, vec = analyze.segment(arm, bone, members)
        half_len = min(vec.length * 0.5, 0.25 * unit)
        if shape == SHAPE_BOX:
            normal = analyze.panel_normal(skin.strong_points(name)) if skin is not None else None
            inward = None
            near, point = geom.nearest(colliders, np.array(head + vec * 0.5))
            if near is not None:
                inward = Vector(point.tolist()) - (head + vec * 0.5)
                inward = inward if inward.length > 1e-6 else None
            centre, euler, axes = box_frame(head, vec, garment.center, normal, inward)
        else:
            centre, euler, axes = head + vec * 0.5, capsule_frame(vec), None
        extent, size, offset = None, None, None
        if options.get("measure_skin", True):
            frame_axes = axes or (Vector((1, 0, 0)), vec.normalized(), Vector((0, 1, 0)))
            pts = skin.points(name) if skin is not None else None
            if pts is not None and shape == SHAPE_BOX and len(pts) >= 8:
                leaf = not any(c.name in members for c in bone.children)
                size, offset = fit_box(pts - np.array(centre), frame_axes, half_len, leaf, preset, unit,
                                       thickness_scale)
            elif pts is not None:
                extent = analyze.extent_of(pts, frame_axes, centre)
            else:
                extent = analyze.skin_extent(arm, meshes, name, frame_axes, head, vec)
        if size is None:
            size = rigid_size(preset, shape, half_len, extent, unit)
            if shape == SHAPE_BOX:
                size = (min(0.05 * unit, size[0] * thickness_scale), size[1], size[2])
        if offset is not None:
            centre = seat_box(centre, axes, size, euler, offset if seat else (0.0,) + offset[1:], colliders,
                              options.get("tolerance", 0.002) * unit)
        half_diag = math.sqrt(sum(s * s for s in size[:2]))
        if by_part:
            # placeholders: collide.assign gives every body its groups once all garments exist
            group, mask = (GROUP_HAIR if is_hair else GROUP_CLOTH), mask16(NOCOLLIDE_CLOTH)
        elif is_hair:
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
            if rides:
                rigid[RIDES] = 1
            have[name] = rigid
            rigids += 1
        geometry[name] = (head, vec, centre, axes)

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
        rotation = (0.0, 0.0, 0.0) if is_hair else joint_frame(vec, centre, garment.center,
                                                               axes[0] if axes else None)
        joint = model.createJoint(
            location=head, rotation=rotation, rigid_a=parent_rigid, rigid_b=rigid,
            maximum_location=(0.0, 0.0, 0.0), minimum_location=(0.0, 0.0, 0.0),
            maximum_rotation=(swing, side, twist), minimum_rotation=(-swing, -side, -twist),
            spring_linear=(0.0, 0.0, 0.0), spring_angular=(spring, spring, spring),
            name=name)
        joint[TAG] = garment.name
        chain_joints[name] = {"rotation": rotation, "limits": (swing, side, twist), "spring": spring,
                              "parent": parent_rigid.name, "garment": garment.name}
        joints += 1

    if lattice_on:
        lin = preset["lattice_lin"] * unit
        ang = tuple(math.radians(a) for a in preset["lattice_ang"])
        for name_a, name_b in garment.pairs:
            if name_a == name_b or name_a not in have or name_b not in have or name_a not in geometry:
                continue
            head_a, vec_a, centre_a, _axes = geometry[name_a]
            head_b, vec_b, centre_b, _axes = geometry.get(name_b, (None, vec_a, have[name_b].location, None))
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


def joined_pairs():
    """Rigid body name pairs already tied by a joint."""
    out = set()
    for obj in bpy.data.objects:
        if getattr(obj, "mmd_type", "") != "JOINT" or obj.rigid_body_constraint is None:
            continue
        a, b = obj.rigid_body_constraint.object1, obj.rigid_body_constraint.object2
        if a is not None and b is not None:
            out.add(frozenset((a.name, b.name)))
    return out


def attach_loose_ends(model, arm, garments, options, log=None):
    """A chain whose last piece of cloth is sewn onto another body (>= GLUED vertices driven by both and NOT by the
    bone above the last one, at the far end of the last bone or most of what it drives besides) hangs from that body
    too: Inase a08's hip chains are glued to the hip plate at their back end but hung from their front end only, so
    the back end swung free and tore the mesh.  What the last bone shares with the bone above is left out because
    that is the chain's own smooth skinning: counted, it made a link two up the chain or the neighbouring chain's
    link above look "glued" in nine chains out of ten (0.2.0).  Nor is a body two joints away ever tied on: the new
    joint would close a triangle and weld the last link.  An end sewn onto several bodies (Eve's front hair: its
    root and the next strand) is tied to each, up to GLUED_PER_END, most shared first (0.2.2; 0.2.1 took the first
    only).  The new joints have the chain's own last limits, at the shared vertices.  Returns the number added."""
    skin = options.get("skin")
    chain_joints = options.get("chain_joints", {})
    if skin is None:
        return 0
    bones = arm.data.bones
    have = existing_rigids()
    joined = joined_pairs()
    near = {}                                              # rigid body -> the bodies one joint away
    for pair in joined:
        if len(pair) == 2:
            a, b = pair
            near.setdefault(a, set()).add(b)
            near.setdefault(b, set()).add(a)
    added = 0
    for garment in garments:
        if not garment.enabled:
            continue
        members = set(garment.bones)
        for leaf in garment.bones:
            if any(c.name in members for c in bones[leaf].children) or leaf not in have or leaf not in chain_joints:
                continue
            rigid = have[leaf]
            info = chain_joints[leaf]
            head, vec = analyze.segment(arm, bones[leaf], members)
            d = np.array(vec.normalized())
            own = (skin.strong_points(leaf) - np.array(head)) @ d
            far = float(np.percentile(own, 70)) if len(own) >= 5 else vec.length * 0.7
            up = bones[leaf].parent.name if bones[leaf].parent is not None else None
            counts = skin.shared_counts(leaf, without=up)
            driven = len(skin.driven(leaf, without=up))
            close = set(near.get(rigid.name, ()))
            for n in list(close):
                close |= near.get(n, set())
            glued = []                             # every body the last piece is sewn onto, most shared first
            for other, count in sorted(counts.items(), key=lambda kv: -kv[1]):
                if count < GLUED or len(glued) >= GLUED_PER_END:
                    break
                body = have.get(other)
                if body is None or other == leaf or body.name == info["parent"] or body.name in close:
                    continue
                part = collide.CLASS_OF.get(collide.name_j(arm, body))
                if str(body.mmd_rigid.type) == "0" and part not in (None, "torso"):
                    continue                       # a hem weighted onto a leg / arm follows it by skin already
                pts = skin.shared_points(leaf, other, without=up)
                # glued: at the far end of the last bone (a neighbour hanging beside it shares cloth along its
                # side), or most of what the last bone drives besides the cloth it shares with the bone above
                # (a08's hip chain: 30 vertices, 18 shared with the link above, the other 12 all with the hip plate)
                if float((pts.mean(0) - np.array(head)) @ d) >= far or len(pts) >= 0.5 * driven:
                    glued.append((body, len(pts), pts.mean(0)))
            for body, count, where in glued:
                close = set(near.get(rigid.name, ()))
                for n in list(close):
                    close |= near.get(n, set())
                if body.name in close:
                    continue                       # this end's first joint brought it within two joints
                swing, side, twist = info["limits"]
                joint = model.createJoint(
                    location=Vector(where.tolist()), rotation=info["rotation"], rigid_a=body, rigid_b=rigid,
                    maximum_location=(0.0, 0.0, 0.0), minimum_location=(0.0, 0.0, 0.0),
                    maximum_rotation=(swing, side, twist), minimum_rotation=(-swing, -side, -twist),
                    spring_linear=(0.0, 0.0, 0.0), spring_angular=(info["spring"],) * 3,
                    name="A.%s-%s" % (body.mmd_rigid.name_j or body.name, leaf))
                joint[TAG] = garment.name
                near.setdefault(body.name, set()).add(rigid.name)
                near.setdefault(rigid.name, set()).add(body.name)
                added += 1
                if log:
                    log("  %s: last piece glued to %s (%d shared vertices) - joined there too"
                        % (leaf, body.mmd_rigid.name_j or body.name, count))
    return added


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
