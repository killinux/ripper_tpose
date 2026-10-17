"""Arm skin for MMD from a game rig whose rest pose bends the elbow (Blender, before Convert to MMD 5).

MMD motions are made for a model whose forearm is in line with its upper arm at rest, so Convert to MMD 5 (step 1.5,
fix_forearm_bend) straightens a bent forearm: it poses the elbow and applies the armature modifier as the new rest
mesh.  That is linear blend skinning: a vertex the game shares between upper arm and forearm moves along the chord
between where each bone alone would take it, so the elbow narrows as it unbends.  The Vindictus UE body rests with
the elbow bent 36.7 deg; straightened that way, PCF_005's arm came out with a waist at the elbow.

straighten_forearms() does the straightening first, the way MMD's SDEF deforms: every vertex turns about the elbow
by its own forearm share of the angle, so the skin keeps its distance from the joint and nothing narrows; the
forearm's bones (hand, fingers, everything hanging below the elbow) turn with it.  The plugin then finds the arm
straight and skips its own bake (it skips anything under 2 deg).

raise_arms() (2026-10-11) turns each whole arm about the shoulder the same way, up to the angle MMD motions are made
for (40 deg below the horizontal; the UE body rests at 52.9): the plugin then builds 腕捩 / 手捩 and their helpers on
the final arm.

straighten_fingers() (2026-10-11) lays each finger along its metacarpal and the thumb's tip along its first bone, joint
by joint from the knuckle out: the UE body binds them curled (knuckle 12-24 deg, middle joint 12-26, thumb 21), and
MMD motions take straight fingers for rest - an open hand came out half closed, a fist closed into the palm.  The
last joint of each finger has no bone after it to measure and stays as bound (0.1-4.6 deg, the thumb's 8.4).  The
game's half bones (index_01_half, ...: in the game they turn half as far as their joint) count half, so the skin they
carry over the knuckle turns half the angle; that needs their own weights, so it runs before merge_into_parent.

Bones and weights are read by name - the arm chains are a parameter - so any rig the plugin converts can use it.
"""
import math

import bpy
from mathutils import Matrix, Vector

# Blender2XPS's names for (upper arm, forearm, hand) on each side - the UE body as XNALaraMesh imports it.
XPS_ARMS = (("arm left shoulder 2", "arm left elbow", "arm left wrist"),
            ("arm right shoulder 2", "arm right elbow", "arm right wrist"))
# ... and for each finger from the knuckle out: the bone the finger is laid along (the metacarpal, the thumb's first
# bone), then the bones whose joints are straightened; the last bone only gives the direction of the one before it.
XPS_FINGERS = tuple(
    chain for side, s in (("left", "l"), ("right", "r")) for chain in
    [("arm %s finger 1a" % side, "arm %s finger 1b" % side, "arm %s finger 1c" % side)]
    + [("unused_%s_metacarpal_%s" % (finger, s),) + tuple("arm %s finger %s%s" % (side, n, j) for j in "abc")
       for n, finger in (("2", "index"), ("3", "middle"), ("4", "ring"), ("5", "pinky"))])
HALF = "_half_"                  # the UE body's half bones (index_01_half_l, ...), children of the joint they halve


def forearm_plans(arm, chains=XPS_ARMS, min_deg=0.5):
    """(forearm bone, elbow, axis, angle, forearm subtree) per bent arm, in armature space: turning the subtree by
    ``angle`` about ``axis`` through the elbow lays the forearm along the upper arm."""
    bones = arm.data.bones
    plans = []
    for up_name, el_name, wr_name in chains:
        up, el, wr = bones.get(up_name), bones.get(el_name), bones.get(wr_name)
        if up is None or el is None or wr is None:
            continue
        elbow = el.head_local.copy()
        upper = (elbow - up.head_local).normalized()
        fore = (wr.head_local - elbow).normalized()
        angle = upper.angle(fore)
        if angle < math.radians(min_deg):
            continue
        axis = fore.cross(upper).normalized()
        subtree = {el.name} | {b.name for b in el.children_recursive}
        plans.append((el.name, elbow, axis, angle, subtree))
    return plans


def turn_by_share(arm, meshes, plans):
    """Turn each plan's subtree about its pivot: every vertex by its own share of weight on the subtree's bones (its
    weight there over its whole bone weight) of the angle - about the pivot, so it keeps its distance from it -
    shape keys with the base mesh; the subtree's bones rigidly.  plans: (bone name, pivot, axis, angle, subtree
    names[, {bone name: factor}]), armature space; a factor scales what that bone's weight counts (default 1).
    Returns the vertices turned per plan."""
    deform = {b.name for b in arm.data.bones if b.use_deform}
    to_world = arm.matrix_world
    counts = []
    for plan in plans:
        _name, pivot, axis, angle, subtree = plan[:5]
        factors = plan[5] if len(plan) > 5 and isinstance(plan[5], dict) else {}
        moved = 0
        for mesh in meshes:
            to_arm = to_world.inverted() @ mesh.matrix_world
            back = to_arm.inverted()
            index_bone = {g.index: g.name for g in mesh.vertex_groups if g.name in deform}
            below = {i: factors.get(name, 1.0) for i, name in index_bone.items() if name in subtree}
            if not below:
                continue
            turns = {}
            for v in mesh.data.vertices:
                total = share = 0.0
                for g in v.groups:
                    if g.group in index_bone and g.weight > 0.0:
                        total += g.weight
                        if g.group in below:
                            share += g.weight * below[g.group]
                if share > 0.0:
                    turn = Matrix.Rotation(angle * share / total, 4, axis)
                    turns[v.index] = back @ Matrix.Translation(pivot) @ turn @ Matrix.Translation(-pivot) @ to_arm
            blocks = mesh.data.shape_keys.key_blocks if mesh.data.shape_keys else []
            for index, m in turns.items():
                mesh.data.vertices[index].co = m @ mesh.data.vertices[index].co
                for block in blocks:
                    block.data[index].co = m @ block.data[index].co
            mesh.data.update()
            moved += len(turns)
        counts.append(moved)

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit = arm.data.edit_bones
        for _name, pivot, axis, angle, subtree in (plan[:5] for plan in plans):
            turn = Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)
            old = {name: edit[name].matrix.copy() for name in subtree if name in edit}
            for name in sorted(old, key=lambda n: len(edit[n].parent_recursive)):
                edit[name].matrix = turn @ old[name]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return counts


def straighten_forearms(arm, meshes, chains=XPS_ARMS, min_deg=0.5):
    """Lay each bent forearm along its upper arm, rest mesh and bones both (see the module docstring).

    A vertex's forearm share is the weight on bones below the elbow over its whole bone weight; it turns by that
    share of the angle about the elbow.  Shape keys turn with the base mesh.  Returns one line per arm."""
    plans = forearm_plans(arm, chains, min_deg)
    if not plans:
        return []
    counts = turn_by_share(arm, meshes, plans)
    return ["%s: %.1f deg straightened, %d vertices turned" % (plan[0], math.degrees(plan[3]), n)
            for plan, n in zip(plans, counts)]


def arm_plans(arm, chains=XPS_ARMS, angle=40.0, min_deg=0.5):
    """(upper arm bone, shoulder joint, axis, angle, arm subtree) per arm, armature space: turning the subtree by
    ``angle`` about ``axis`` through the shoulder brings the upper arm to ``angle`` deg below the horizontal, in the
    vertical plane through it."""
    bones = arm.data.bones
    up_world = arm.matrix_world.inverted().to_3x3() @ Vector((0.0, 0.0, 1.0))
    up_world.normalize()
    plans = []
    for up_name, el_name, _wr_name in chains:
        up, el = bones.get(up_name), bones.get(el_name)
        if up is None or el is None:
            continue
        shoulder = up.head_local.copy()
        d = (el.head_local - shoulder).normalized()
        down = math.degrees(math.asin(max(-1.0, min(1.0, -d.dot(up_world)))))
        if abs(down - angle) < min_deg:
            continue
        axis = d.cross(up_world).normalized()
        subtree = {up.name} | {b.name for b in up.children_recursive}
        plans.append((up.name, shoulder, axis, math.radians(down - angle), subtree, down))
    return plans


def raise_arms(arm, meshes, chains=XPS_ARMS, angle=40.0, min_deg=0.5):
    """Bring the upper arms to ``angle`` deg below the horizontal (the angle MMD motions are made for; the Vindictus
    UE body rests at 52.9), rest mesh and bones both, the way straighten_forearms unbends the elbow: each vertex
    turns about the shoulder joint by its own share of weight on the arm, so the shoulder and armpit blend without
    narrowing.  Run after straighten_forearms and before the plugin, so it builds its twist bones on the final arm.
    Returns one line per arm."""
    plans = arm_plans(arm, chains, angle, min_deg)
    if not plans:
        return []
    counts = turn_by_share(arm, meshes, [plan[:5] for plan in plans])
    return ["%s: %.1f -> %.1f deg below the horizontal, %d vertices turned" % (plan[0], plan[5], angle, n)
            for plan, n in zip(plans, counts)]


def finger_plans(arm, level, chains=XPS_FINGERS, min_deg=0.5, half=HALF):
    """(bone, joint, axis, angle, subtree, {half-bone subtree: 0.5}) per finger for its level-th joint from the
    knuckle (the head of chain[level]), armature space: turning the subtree by ``angle`` about ``axis`` through the
    joint lays chain[level] along chain[level - 1].  The half bones hanging under chain[level] count half."""
    bones = arm.data.bones
    plans = []
    for chain in chains:
        if level + 1 >= len(chain):
            continue
        before, bone, after = (bones.get(name) for name in chain[level - 1:level + 2])
        if before is None or bone is None or after is None:
            continue
        joint = bone.head_local.copy()
        along = (joint - before.head_local).normalized()
        out = (after.head_local - joint).normalized()
        angle = along.angle(out)
        if angle < math.radians(min_deg):
            continue
        axis = out.cross(along).normalized()
        subtree = {bone.name} | {b.name for b in bone.children_recursive}
        halves = {b.name for h in bone.children if half in h.name for b in [h] + list(h.children_recursive)}
        plans.append((bone.name, joint, axis, angle, subtree, dict.fromkeys(halves, 0.5)))
    return plans


def straighten_fingers(arm, meshes, chains=XPS_FINGERS, min_deg=0.5):
    """Straighten the fingers joint by joint from the knuckle out, rest mesh and bones both (see the module
    docstring): each vertex turns about the joint by its own share of weight on the bones beyond it, the half
    bones' weight counting half.  Run before merge_into_parent (it needs the half bones' own weights).  Returns
    one line per joint."""
    lines = []
    for level in range(1, max(len(chain) for chain in chains) - 1):
        plans = finger_plans(arm, level, chains, min_deg)
        if plans:
            counts = turn_by_share(arm, meshes, plans)
            lines += ["%s: %.1f deg straightened, %d vertices turned" % (plan[0], math.degrees(plan[3]), n)
                      for plan, n in zip(plans, counts)]
    return lines
