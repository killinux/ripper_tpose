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


def local_matrix(arm, bone_name, rotation):
    """Pose-space quaternion for an armature-space rotation matrix."""
    rest = _rest(arm, bone_name)
    return (rest.inverted() @ rotation @ rest).to_quaternion()


def local_translation(arm, bone_name, vector):
    return _rest(arm, bone_name).inverted() @ vector


def rotation_sign(axis, probe, want):
    """+1 if a small positive rotation about ``axis`` moves ``probe`` (offset
    from the pivot) along ``want``, else -1."""
    moved = Matrix.Rotation(math.radians(1.0), 3, axis) @ probe
    return 1.0 if (moved - probe).dot(want) >= 0.0 else -1.0


def offsets(face, actions, scales=None, missing=None):
    """bone name -> [Vector location, Quaternion rotation] in pose space.

    Rotations and translations are first accumulated per ROLE in armature
    space (a roll after a pitch composes as world rotations, in recipe order),
    then converted into each bone's pose space.  A role's followers get the
    same rotation about the ROLE's pivot: rotating a helper about its own head
    would move its skin along a different arc, so the pivot difference is
    turned into a translation, ``(R - I) (h_follower - h_role)``.
    """
    scales = scales or {}
    arm = face.arm
    fwd = faces.forward(face)
    per_role = {}       # role -> [Matrix rotation, Vector translation]
    for role, kind, amount in actions:
        bone_name = face.bone(role)
        if not bone_name:
            if missing is not None:
                missing.add(role)
            continue
        side = face.side_of(bone_name)
        scale = scales.get(expressions.scale_group(role), 1.0)
        entry = per_role.setdefault(role, [Matrix.Identity(3), Vector((0.0, 0.0, 0.0))])
        if kind == "move":
            out, forward, up = amount
            entry[1] += Vector((out * side, forward * face.front, up)) * face.unit * scale
            continue
        axis = AXES[kind]
        if kind == "pitch":
            probe, want = fwd, Vector((0.0, 0.0, -1.0))
        elif kind == "roll":
            probe, want = Vector((side, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))
        else:
            probe, want = fwd, Vector((side, 0.0, 0.0))
        degrees = rotation_sign(axis, probe, want) * amount * scale
        if abs(degrees) > 1e-9:
            entry[0] = Matrix.Rotation(math.radians(degrees), 3, axis) @ entry[0]

    per_bone = {}
    identity = Matrix.Identity(3)
    for role, (rotation, translation) in per_role.items():
        bone_name = face.bone(role)
        per_bone[bone_name] = [local_translation(arm, bone_name, translation),
                               local_matrix(arm, bone_name, rotation)]
        pivot = arm.data.bones[bone_name].head_local
        for follower in face.followers.get(role, ()):
            shift = (rotation - identity) @ (arm.data.bones[follower].head_local - pivot)
            per_bone[follower] = [local_translation(arm, follower, translation + shift),
                                  local_matrix(arm, follower, rotation)]
    return per_bone


# -- morph slider ----------------------------------------------------------------
class _SliderState(object):
    """Suspend mmd_tools' morph slider while the morph lists change.

    The slider (Morph Tools panel) mirrors every morph into a placeholder
    shape key with drivers onto the bones.  Adding or removing bone morphs
    behind its back leaves those drivers pointing at the old offsets, so
    Blender previews one thing and the PMX carries another.  Unbind first,
    then re-create (and re-bind if it was bound) afterwards.
    """

    def __init__(self, root):
        from mmd_tools.core.model import Model

        self.slider = Model(root).morph_slider
        self.existed = self.slider.placeholder() is not None
        self.bound = self.existed and self.slider.placeholder(binded=True) is not None

    def __enter__(self):
        if self.bound:
            self.slider.unbind()
        return self

    def __exit__(self, *exc):
        if self.existed:
            try:
                self.slider.create()
                if self.bound:
                    self.slider.bind()
            except Exception as error:          # the slider is a preview aid; never lose the morphs over it
                print("[mmd_face] morph slider not restored: %s" % error)
        return False


# -- morphs --------------------------------------------------------------------
def _clamp_active(mmd_root):
    mmd_root.active_morph_type = "bone_morphs"
    mmd_root.active_morph = max(0, min(mmd_root.active_morph, len(mmd_root.bone_morphs) - 1))


def remove_morphs(root, names):
    mmd_root = root.mmd_root
    removed = []
    for name in list(names):
        index = mmd_root.bone_morphs.find(name)
        if index >= 0:
            mmd_root.bone_morphs.remove(index)
            removed.append(name)
    if removed:
        _clamp_active(mmd_root)
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
    """Create the recipes' morphs on the model.  Returns (created, skipped, face)."""
    face = faces.resolve(arm)
    mmd_root = root.mmd_root
    created, skipped = [], []
    if not face.calibrated:
        # nothing to measure the amplitudes against (the ROE males: teeth and
        # Xtra bones only) - a morph built here would be sized by a guess and
        # would hide the "no facial morphs" signal downstream
        for recipe in recipes:
            skipped.append((recipe["name"], "no eye/lid/brow pair to calibrate against"))
        if log:
            log("face: %s" % face.describe())
        return created, skipped, face
    # a standing Preview pose would otherwise be subtracted from every offset
    # by mmd_tools' exporter once the model is built (BoneConverterPoseMode)
    reset_pose(root, arm)
    with _SliderState(root):
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
    """Remove the morphs this add-on built on this root, or exactly ``names``.

    Nothing is removed on a root that carries no record: the standard names
    are also what hand-made models and the ROE worker's earlier exports use,
    and "Clear" must not eat those.
    """
    names = list(names) if names else list(root.get(TAG, []))
    if not names:
        return []
    with _SliderState(root):
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
    """Clear the pose of every bone a bone morph uses, plus the face bones.

    The face bones are included unconditionally: after Clear (or on a model
    whose morphs were never built) the morph list is empty, and a reset that
    only walked the morphs would leave a previewed pose standing - which is
    exactly what would then be baked into an export.
    """
    face = faces.resolve(arm)
    names = set(morph_bones(root)) | set(extra) | set(face.bones.values())
    for followers in face.followers.values():
        names.update(followers)
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
