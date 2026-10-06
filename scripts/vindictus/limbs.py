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

Bones and weights are read by name - the arm chains are a parameter - so any rig the plugin converts can use it.
"""
import math

import bpy
from mathutils import Matrix

# Blender2XPS's names for (upper arm, forearm, hand) on each side - the UE body as XNALaraMesh imports it.
XPS_ARMS = (("arm left shoulder 2", "arm left elbow", "arm left wrist"),
            ("arm right shoulder 2", "arm right elbow", "arm right wrist"))


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


def straighten_forearms(arm, meshes, chains=XPS_ARMS, min_deg=0.5):
    """Lay each bent forearm along its upper arm, rest mesh and bones both (see the module docstring).

    A vertex's forearm share is the weight on bones below the elbow over its whole bone weight; it turns by that
    share of the angle about the elbow.  Shape keys turn with the base mesh.  Returns one line per arm."""
    plans = forearm_plans(arm, chains, min_deg)
    if not plans:
        return []
    deform = {b.name for b in arm.data.bones if b.use_deform}
    to_world = arm.matrix_world
    report = []
    for el_name, elbow, axis, angle, subtree in plans:
        moved = 0
        for mesh in meshes:
            to_arm = to_world.inverted() @ mesh.matrix_world
            back = to_arm.inverted()
            index_bone = {g.index: g.name for g in mesh.vertex_groups if g.name in deform}
            below = {i for i, name in index_bone.items() if name in subtree}
            if not below:
                continue
            turns = {}
            for v in mesh.data.vertices:
                total = share = 0.0
                for g in v.groups:
                    if g.group in index_bone and g.weight > 0.0:
                        total += g.weight
                        if g.group in below:
                            share += g.weight
                if share > 0.0:
                    turn = Matrix.Rotation(angle * share / total, 4, axis)
                    turns[v.index] = back @ Matrix.Translation(elbow) @ turn @ Matrix.Translation(-elbow) @ to_arm
            blocks = mesh.data.shape_keys.key_blocks if mesh.data.shape_keys else []
            for index, m in turns.items():
                mesh.data.vertices[index].co = m @ mesh.data.vertices[index].co
                for block in blocks:
                    block.data[index].co = m @ block.data[index].co
            mesh.data.update()
            moved += len(turns)
        report.append("%s: %.1f deg straightened, %d vertices turned" % (el_name, math.degrees(angle), moved))

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit = arm.data.edit_bones
        for el_name, elbow, axis, angle, subtree in plans:
            turn = Matrix.Translation(elbow) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-elbow)
            old = {name: edit[name].matrix.copy() for name in subtree if name in edit}
            for name in sorted(old, key=lambda n: len(edit[n].parent_recursive)):
                edit[name].matrix = turn @ old[name]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return report
