# -*- coding: utf-8 -*-
"""DNA joint poses -> the rig's bones -> ARKit shape keys on every mesh the face bones move."""
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import arkit, dna

TAG = "faceit_arkit"            # custom property on a mesh: which keys this add-on made


def find_armature(obj):
    if obj is None:
        return None
    if obj.type == "ARMATURE":
        return obj
    arm = obj.find_armature()
    if arm is None and obj.parent is not None and obj.parent.type == "ARMATURE":
        arm = obj.parent
    return arm


def skinned_meshes(arm, bone_names):
    """Meshes deformed by ``arm`` with a vertex group for any of ``bone_names`` (a mesh whose facial
    groups happen to be empty just gets no keys: bake skips meshes that never move)."""
    names = set(bone_names)
    return [obj for obj in bpy.data.objects
            if obj.type == "MESH" and obj.find_armature() == arm and any(g.name in names for g in obj.vertex_groups)]


class DnaPoser:
    """Put DNA joint poses onto the armature bones of the same names (exact, else case-insensitive)."""

    def __init__(self, face, arm, min_joints=30):
        self.face, self.arm = face, arm
        bones = arm.data.bones
        lower = {b.name.lower(): b.name for b in bones}
        self.index, self.names = [], []
        for j, name in enumerate(face.joints):
            bone = name if name in bones else lower.get(name.lower())
            if bone and name.upper().startswith("FACIAL_"):
                self.index.append(j)
                self.names.append(bone)
        if len(self.index) < min_joints:
            raise ValueError("only %d of the DNA's facial joints exist as bones in %s (need %d) - "
                             "is this the right DNA / a MetaHuman face rig?" % (len(self.index), arm.name, min_joints))
        src = face.rest[self.index, :3, 3]
        dst = np.array([list(bones[n].head_local) for n in self.names])
        self.scale, self.rot, self.shift, err = dna.fit_similarity(src, dst)
        self.mm = 10.0 / self.scale                      # mm per rig unit (the DNA is in centimetres)
        self.fit = {"joints": len(self.index), "dna_joints": sum(1 for n in face.joints if n.upper().startswith("FACIAL_")),
                    "scale": float(self.scale), "mean_mm": float(err.mean() * self.mm),
                    "max_mm": float(err.max() * self.mm)}
        self.rest = {n: bones[n].matrix_local.copy() for n in self.names}
        self.parent = {n: (bones[n].parent.name if bones[n].parent else None) for n in self.names}
        self.parent_rest = {n: (bones[n].parent.matrix_local.copy() if bones[n].parent else Matrix())
                            for n in self.names}

    def bases(self, controls):
        """Pose-bone matrix_basis per facial bone for these raw control values."""
        posed = self.face.posed(controls)
        rest = self.face.rest
        want = {}
        for j, name in zip(self.index, self.names):
            d_rot = posed[j][:3, :3] @ rest[j][:3, :3].T
            move = self.scale * (self.rot @ (posed[j][:3, 3] - rest[j][:3, 3]))
            spin = Matrix((self.rot @ d_rot @ self.rot.T).tolist()).to_4x4()
            head = self.rest[name].to_translation()
            want[name] = (Matrix.Translation(head + Vector(move.tolist())) @ spin
                          @ Matrix.Translation(-head) @ self.rest[name])
        out = {}
        for name, posed_matrix in want.items():
            parent_pose = want.get(self.parent[name], self.parent_rest[name])
            local_rest = self.parent_rest[name].inverted() @ self.rest[name]
            out[name] = local_rest.inverted() @ parent_pose.inverted() @ posed_matrix
        return out


def disconnect(arm, names):
    """Connected bones cannot translate in Blender - a DNA pose moves most facial joints, so free them."""
    connected = [n for n in names if arm.data.bones[n].use_connect]
    if not connected:
        return 0
    view_layer = bpy.context.view_layer
    active, mode = view_layer.objects.active, (bpy.context.object.mode if bpy.context.object else "OBJECT")
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    hidden = arm.hide_get()
    arm.hide_set(False)
    view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for n in connected:
        arm.data.edit_bones[n].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.hide_set(hidden)
    view_layer.objects.active = active
    return len(connected)


class _RestState:
    """Whole armature in rest pose, constraints muted, only Armature modifiers live on the meshes;
    everything is put back on exit."""

    def __init__(self, arm, meshes):
        self.arm, self.meshes = arm, meshes

    def __enter__(self):
        self.pose = {pb.name: pb.matrix_basis.copy() for pb in self.arm.pose.bones}
        self.position = self.arm.data.pose_position
        self.muted = [c for pb in self.arm.pose.bones for c in pb.constraints if not c.mute]
        self.mods = [(m, m.show_viewport) for o in self.meshes for m in o.modifiers if m.type != "ARMATURE"]
        self.keys = {o.name: {k.name: k.value for k in o.data.shape_keys.key_blocks} if o.data.shape_keys else {}
                     for o in self.meshes}
        self.show_only = {o.name: o.show_only_shape_key for o in self.meshes}
        self.arm.data.pose_position = "POSE"
        for c in self.muted:
            c.mute = True
        for m, _v in self.mods:
            m.show_viewport = False
        for o in self.meshes:
            o.show_only_shape_key = False
            if o.data.shape_keys:
                for k in o.data.shape_keys.key_blocks:
                    k.value = 0.0
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix()
        return self

    def __exit__(self, *exc):
        for pb in self.arm.pose.bones:
            if pb.name in self.pose:
                pb.matrix_basis = self.pose[pb.name]
        self.arm.data.pose_position = self.position
        for c in self.muted:
            c.mute = False
        for m, visible in self.mods:
            m.show_viewport = visible
        for o in self.meshes:
            o.show_only_shape_key = self.show_only[o.name]
            if o.data.shape_keys:
                old = self.keys.get(o.name, {})
                for k in o.data.shape_keys.key_blocks:
                    k.value = old.get(k.name, 0.0)
        bpy.context.view_layer.update()
        return False


def _evaluated(obj):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3)


def _apply(poser, bases):
    pose = poser.arm.pose.bones
    for name in poser.names:
        pose[name].matrix_basis = bases.get(name, Matrix())


def bake(arm, face, meshes=None, names=None, recipes=None, dna_path="", log=print):
    """Shape keys named after the ARKit shapes on every mesh the facial bones move.
    Returns a report dict (fit, meshes, per-shape vertex counts and largest move in mm)."""
    recipes = recipes or arkit.metahuman_recipes()
    names = [n for n in (names or arkit.ARKIT_52)]
    poser = DnaPoser(face, arm)
    missing = sorted({c for n in names for c in list(recipes[n][0]) + list(recipes[n][1] or {})}
                     - set(face.raw_index))
    if missing:
        raise ValueError("this DNA lacks the raw controls %s" % ", ".join(missing[:8]))
    meshes = meshes or skinned_meshes(arm, poser.names)
    if not meshes:
        raise ValueError("no mesh of %s carries weight on the facial bones" % arm.name)
    mm = poser.mm
    report = {"fit": poser.fit, "meshes": {}, "shapes": {}, "disconnected": disconnect(arm, poser.names)}
    with _RestState(arm, meshes):
        rest, base = {}, {}
        for obj in meshes:
            rest[obj.name] = _evaluated(obj)
            co = np.empty(len(obj.data.vertices) * 3)
            obj.data.vertices.foreach_get("co", co)
            base[obj.name] = co.reshape(-1, 3)
            if len(rest[obj.name]) != len(base[obj.name]):
                raise ValueError("%s: its Armature modifier changes the vertex count - can't bake" % obj.name)
        made = {obj.name: [] for obj in meshes}
        for name in names:
            controls, against = recipes[name]
            _apply(poser, poser.bases(controls))
            posed = {obj.name: _evaluated(obj) for obj in meshes}
            if against:
                _apply(poser, poser.bases(against))
                ref = {obj.name: _evaluated(obj) for obj in meshes}
            else:
                ref = rest
            biggest, moved_total = 0.0, 0
            for obj in meshes:
                delta = posed[obj.name] - ref[obj.name]
                delta[np.abs(delta) < 1e-5 / mm] = 0.0
                length = np.linalg.norm(delta, axis=1)
                moved = int((length > 0.1 / mm).sum())        # > 0.1 mm
                if moved == 0 and not (obj.data.shape_keys and name in obj.data.shape_keys.key_blocks):
                    continue                                   # this mesh never moves for this shape
                if obj.data.shape_keys is None:
                    obj.shape_key_add(name="Basis", from_mix=False)
                keys = obj.data.shape_keys.key_blocks
                if name in keys:
                    obj.shape_key_remove(keys[name])
                key = obj.shape_key_add(name=name, from_mix=False)
                key.data.foreach_set("co", (base[obj.name] + delta).ravel())
                key.slider_min, key.slider_max, key.value = 0.0, 1.0, 0.0
                made[obj.name].append(name)
                biggest = max(biggest, float(length.max()) * mm)
                moved_total += moved
            report["shapes"][name] = {"moved_verts": moved_total, "max_mm": round(biggest, 2)}
            log("  %-20s %6d verts  max %5.1f mm" % (name, moved_total, biggest))
    for obj in meshes:
        if made[obj.name]:
            obj[TAG] = {"dna": dna_path, "shapes": made[obj.name], "fit_mm": round(poser.fit["mean_mm"], 3)}
        report["meshes"][obj.name] = len(made[obj.name])
    return report


def clear(meshes):
    """Remove the shape keys this add-on made (recorded on each mesh)."""
    removed = 0
    for obj in meshes:
        info = obj.get(TAG)
        if not info or obj.data.shape_keys is None:
            continue
        keys = obj.data.shape_keys.key_blocks
        for name in list(info.get("shapes", [])):
            if name in keys:
                obj.shape_key_remove(keys[name])
                removed += 1
        if len(obj.data.shape_keys.key_blocks) == 1:          # only Basis left
            obj.shape_key_remove(obj.data.shape_keys.key_blocks[0])
        del obj[TAG]
    return removed
