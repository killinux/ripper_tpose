"""Turn expression recipes into mmd_tools bone morphs."""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import expressions, faces

TAG = "mmd_face_morphs"       # root custom property listing the morphs built here

AXES = {"pitch": Vector((1.0, 0.0, 0.0)), "roll": Vector((0.0, 1.0, 0.0)), "yaw": Vector((0.0, 0.0, 1.0))}


def model_of(obj):
    from mmd_tools.core.model import Model

    root = Model.findRoot(obj) if obj is not None else None
    if root is None:
        raise RuntimeError("select an object of an mmd_tools model")
    arm = Model(root).armature()
    if arm is None:
        raise RuntimeError("the model has no armature")
    return root, arm


# -- frames --------------------------------------------------------------------
def _rest(arm, bone_name):
    """3x3 rest orientation of the bone in armature space."""
    return arm.data.bones[bone_name].matrix_local.to_3x3()


def local_rotation(arm, bone_name, axis, degrees):
    """Quaternion in the bone's own (pose) space for a rotation about an armature axis."""
    local_axis = _rest(arm, bone_name).inverted() @ axis
    if local_axis.length < 1e-9 or abs(degrees) < 1e-9:
        return Quaternion((1.0, 0.0, 0.0, 0.0))
    return Quaternion(local_axis.normalized(), math.radians(degrees))


def local_translation(arm, bone_name, vector):
    return _rest(arm, bone_name).inverted() @ vector


def rotation_sign(axis, probe, want):
    """+1 if a small positive rotation about ``axis`` moves ``probe`` (offset
    from the pivot) along ``want``, else -1."""
    moved = Matrix.Rotation(math.radians(1.0), 3, axis) @ probe
    return 1.0 if (moved - probe).dot(want) >= 0.0 else -1.0


def offsets(face, actions, scales=None, missing=None):
    """bone name -> [Vector location, Quaternion rotation] in pose space."""
    scales = scales or {}
    arm = face.arm
    fwd = faces.forward(face)
    per_bone = {}
    for role, kind, amount in actions:
        bone_name = face.bone(role)
        if not bone_name:
            if missing is not None:
                missing.add(role)
            continue
        side = face.side_of(bone_name)
        scale = scales.get(expressions.scale_group(role), 1.0)
        entry = per_bone.setdefault(bone_name, [Vector((0.0, 0.0, 0.0)), Quaternion((1.0, 0.0, 0.0, 0.0))])
        if kind == "move":
            out, forward, up = amount
            vector = Vector((out * side, forward * face.front, up)) * face.unit * scale
            entry[0] += local_translation(arm, bone_name, vector)
            continue
        axis = AXES[kind]
        if kind == "pitch":
            probe, want = fwd, Vector((0.0, 0.0, -1.0))
        elif kind == "roll":
            probe, want = Vector((side, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))
        else:
            probe, want = fwd, Vector((side, 0.0, 0.0))
        degrees = rotation_sign(axis, probe, want) * amount * scale
        entry[1] = entry[1] @ local_rotation(arm, bone_name, axis, degrees)
    return per_bone


# -- morphs --------------------------------------------------------------------
def remove_morphs(root, names):
    mmd_root = root.mmd_root
    removed = []
    for name in list(names):
        index = mmd_root.bone_morphs.find(name)
        if index >= 0:
            mmd_root.bone_morphs.remove(index)
            removed.append(name)
    return removed


def _ensure_facial_frame(root):
    from mmd_tools.core.model import Model

    if "表情" not in root.mmd_root.display_item_frames:
        Model(root).initialDisplayFrames(reset=False)


def refresh_facial_frame(root):
    """List every morph in the 表情 display frame (MMD's expression panel reads
    that frame, not the morph lists)."""
    from mmd_tools.operators.display_item import DisplayItemQuickSetup

    _ensure_facial_frame(root)
    DisplayItemQuickSetup.load_facial_items(root.mmd_root)


def build(root, arm, recipes, scales=None, replace=True, log=None):
    """Create the recipes' morphs on the model.  Returns (created, skipped)."""
    face = faces.resolve(arm)
    mmd_root = root.mmd_root
    created, skipped = [], []
    if replace:
        removed = remove_morphs(root, [r["name"] for r in recipes])
        if removed and log:
            log("replaced %d existing morphs" % len(removed))
    for recipe in recipes:
        name = recipe["name"]
        if mmd_root.bone_morphs.find(name) >= 0:
            skipped.append((name, "exists"))
            continue
        missing = set()
        per_bone = offsets(face, recipe["actions"], scales, missing)
        if not per_bone:
            skipped.append((name, "no bones: " + " ".join(sorted(missing))))
            continue
        morph = mmd_root.bone_morphs.add()
        morph.name = name
        morph.name_e = recipe["name_e"]
        morph.category = recipe["category"]
        for bone_name, (location, rotation) in per_bone.items():
            item = morph.data.add()
            item.bone = bone_name
            item.location = location
            item.rotation = rotation
        created.append(name)
        if log:
            log("%-8s %-10s %d bones%s" % (recipe["category"].lower(), name, len(per_bone),
                                          ("  (missing %s)" % " ".join(sorted(missing))) if missing else ""))
    tracked = set(root.get(TAG, [])) | set(created)
    root[TAG] = sorted(tracked)
    if created:
        try:
            refresh_facial_frame(root)
        except Exception as exc:       # the frame is cosmetic; the morphs are in
            if log:
                log("facial display frame: %s" % exc)
        mmd_root.active_morph_type = "bone_morphs"
        mmd_root.active_morph = mmd_root.bone_morphs.find(created[-1])
    return created, skipped, face


def clear(root, names=None):
    """Remove the morphs this add-on built (or ``names``)."""
    names = list(names) if names else list(root.get(TAG, [])) or expressions.NAMES
    removed = remove_morphs(root, names)
    root[TAG] = sorted(set(root.get(TAG, [])) - set(removed))
    if removed:
        try:
            refresh_facial_frame(root)
        except Exception:
            pass
    return removed


# -- posing --------------------------------------------------------------------
def morph_bones(root):
    names = set()
    for morph in root.mmd_root.bone_morphs:
        for item in morph.data:
            if item.bone:
                names.add(item.bone)
    return names


def reset_pose(root, arm, extra=()):
    """Clear the pose of every bone a bone morph uses, plus ``extra``.

    The face bones are included unconditionally: after Clear (or on a model
    whose morphs were never built) the morph list is empty, and a reset that
    only walked the morphs would leave a previewed pose standing - which is
    exactly what would then be baked into an export.
    """
    names = set(morph_bones(root)) | set(extra)
    names |= {name for name in faces.resolve(arm).bones.values()}
    for name in names:
        pose_bone = arm.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.matrix_basis.identity()


def pose_morph(root, arm, name, weight=1.0, additive=False):
    """Put the bones where the morph says (like mmd_tools' View, with a weight)."""
    morph = root.mmd_root.bone_morphs.get(name)
    if morph is None:
        raise RuntimeError("no bone morph named %s" % name)
    if not additive:
        reset_pose(root, arm)
    for item in morph.data:
        pose_bone = arm.pose.bones.get(item.bone)
        if pose_bone is None:
            continue
        axis, angle = Quaternion(item.rotation).to_axis_angle()
        rotation = Quaternion(axis, angle * weight)
        matrix = (pose_bone.matrix_basis.to_3x3() @ rotation.to_matrix()).to_4x4()
        matrix.translation = pose_bone.location + Vector(item.location) * weight
        pose_bone.matrix_basis = matrix
    return len(morph.data)
