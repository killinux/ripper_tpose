# -*- coding: utf-8 -*-
"""Blender-side helpers the rig maps (rigs/*.py) use to turn a game skeleton into a 3ds Max Biped one.

The repo's PMX / XPS chain (Stellar Blade's export_pmx_blender.py on the Rise of Eros worker, blender2xps) reads
Biped names: Bip001, Bip001 Pelvis / Spine / Spine1 / Spine2 / Neck / Head, Bip001 L Clavicle / UpperArm / Forearm /
Hand / Thigh / Calf / Foot / Toe0, Bip001 L Finger0 / 01 / 02 ... Finger4 / 41 / 42, twist helpers Bip001 L UpArmTwist,
ForeTwist, ThighTwist, CalfTwist.  A rig map renames the game's bones to those names and fixes what a Biped would not
have (legs hanging from the root, "offset" bones between joints, one bone for both breasts).  All functions run in
object mode and return to it.
"""
import re

import bpy
import numpy as np
from mathutils import Vector


def weighted_bone_names(meshes, min_weight=1e-4):
    """Names of the vertex groups that carry weight on any of the meshes."""
    out = set()
    for m in meshes:
        names = {g.index: g.name for g in m.vertex_groups}
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > min_weight:
                    out.add(names.get(g.group))
    out.discard(None)
    return out


def rename_bones(arm, meshes, mapping):
    """{old: new} exact names; vertex groups follow (also on meshes whose group was not renamed by Blender)."""
    done = 0
    for old, new in mapping.items():
        b = arm.data.bones.get(old)
        if b is None or old == new:
            continue
        b.name = new
        for m in meshes:
            vg = m.vertex_groups.get(old)
            if vg is not None and m.vertex_groups.get(new) is None:
                vg.name = new
        done += 1
    return done


def _edit(arm):
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    return arm.data.edit_bones


def reparent(arm, pairs):
    """[(child, new parent), ...] keeping every bone where it is.  Missing names are skipped.  Returns done pairs."""
    eb = _edit(arm)
    done = []
    for child, parent in pairs:
        c, p = eb.get(child), eb.get(parent)
        if c is None or p is None or c.parent == p:
            continue
        c.use_connect = False
        c.parent = p
        done.append("%s -> %s" % (child, parent))
    bpy.ops.object.mode_set(mode="OBJECT")
    return done


def collapse(arm, names):
    """Removes bones in between (offset / null bones without skin): their children go to their parent."""
    eb = _edit(arm)
    gone = []
    for name in names:
        b = eb.get(name)
        if b is None:
            continue
        for c in list(b.children):
            c.use_connect = False
            c.parent = b.parent
        eb.remove(b)
        gone.append(name)
    bpy.ops.object.mode_set(mode="OBJECT")
    return gone


def drop_unweighted(arm, meshes, keep=(), keep_re=None):
    """Deletes bones with no skin of their own and no skinned descendant (IK targets, attach points, unused hair /
    eye / jaw bones), except `keep` and names matching `keep_re`."""
    weighted = weighted_bone_names(meshes)
    rx = re.compile(keep_re) if keep_re else None

    def needed(b):
        return (b.name in weighted or b.name in keep or (rx and rx.search(b.name))
                or any(needed(c) for c in b.children))
    doomed = [b.name for b in arm.data.bones if not needed(b)]
    eb = _edit(arm)
    for name in doomed:
        b = eb.get(name)
        if b is not None:
            eb.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")
    return doomed


def merge_into(arm, meshes, names, target):
    """Moves the weights of `names` onto `target` (summed) and deletes those bones - e.g. a face rig with no
    expressions to keep, which the cloth / hair detection would otherwise take for chains.  Returns the count."""
    tgt_groups = {}
    done = 0
    for m in meshes:
        dst = m.vertex_groups.get(target) or m.vertex_groups.new(name=target)
        tgt_groups[m.name] = dst
        idx = {m.vertex_groups[n].index: n for n in names if m.vertex_groups.get(n)}
        if not idx:
            continue
        for v in m.data.vertices:
            add = sum(g.weight for g in v.groups if g.group in idx)
            if add > 0:
                dst.add([v.index], add, "ADD")
        for n in idx.values():
            m.vertex_groups.remove(m.vertex_groups[n])
    eb = _edit(arm)
    for n in names:
        b = eb.get(n)
        if b is not None:
            for c in list(b.children):
                c.parent = b.parent
            eb.remove(b)
            done += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    return done


def split_bone_by_side(arm, meshes, source, left, right, parent=None, blend=0.02):
    """One bone carrying both breasts -> two new bones `left` / `right` (+X = her left), weights moved by side with
    a `blend` metre hand-over at the middle.  Each new bone starts at the source bone's head moved sideways to that
    side's weighted centre and points forward.  Returns a report line."""
    pts, rows = [], []
    for m in meshes:
        vg = m.vertex_groups.get(source)
        if vg is None:
            continue
        for v in m.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 1e-4:
                    p = m.matrix_world @ v.co
                    rows.append((m, v.index, p.x, g.weight))
                    pts.append((p.x, p.y, p.z, g.weight))
    if len(rows) < 20:
        return "%s: too little weight to split (%d vertices)" % (source, len(rows))
    a = np.array(pts)
    inv = arm.matrix_world.inverted()
    eb = _edit(arm)
    src = eb[source]
    head_w = arm.matrix_world @ src.head
    made = {}
    for name, sel in ((left, a[:, 0] > 0.0), (right, a[:, 0] < 0.0)):
        if not sel.any():
            continue
        w = a[sel, 3]
        cx = float((a[sel, 0] * w).sum() / w.sum())
        cy = float((a[sel, 1] * w).sum() / w.sum())
        cz = float((a[sel, 2] * w).sum() / w.sum())
        b = eb.new(name)
        b.head = inv @ Vector((cx, head_w.y, cz))
        b.tail = inv @ Vector((cx, min(cy, head_w.y) - 0.06, cz))
        b.parent = eb.get(parent) if parent else src.parent
        b.use_deform = True
        made[name] = (cx, cy, cz)
    bpy.ops.object.mode_set(mode="OBJECT")
    moved = 0
    for m in {r[0] for r in rows}:
        vg = m.vertex_groups[source]
        gl = m.vertex_groups.get(left) or m.vertex_groups.new(name=left)
        gr = m.vertex_groups.get(right) or m.vertex_groups.new(name=right)
        for (mm, vi, x, wt) in rows:
            if mm is not m:
                continue
            t = min(max((x + blend / 2) / blend, 0.0), 1.0)      # 0 = right side, 1 = left side
            for grp, share in ((gl, t), (gr, 1.0 - t)):
                if share > 0:
                    grp.add([vi], wt * share, "ADD")
            vg.remove([vi])
            moved += 1
    arm.data.bones[source].use_deform = False
    return "%s: %d vertices -> %s / %s at %s" % (source, moved, left, right,
                                                 {k: tuple(round(c, 3) for c in v) for k, v in made.items()})
