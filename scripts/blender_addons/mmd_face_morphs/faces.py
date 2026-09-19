"""Find the face bones of an mmd_tools model.

Rise of Eros ships no shape keys: eyelids, brows, jaw, lips, tongue and teeth
are skinned bones under the head.  Three spellings of the same rig exist in
the same game and the MMD conversion keeps them as they are (only the eyeballs
become 左目/右目), so every role below lists the spellings seen so far, matched
with the ``Bip001 `` / ``Bip000 `` prefix stripped and case ignored.

``AC `` bones are 3ds Max helper duplicates.  Almost all of them hang UNDER the
control they duplicate (``AC eyelid_UL`` under ``Bip001 eyelid_UL``), so moving
the control moves them and they are simply skipped.  The one exception found so
far is ``AC jaw``: it carries the skin under the chin but is parented to the
NECK, so a chin rotation would leave that patch behind.  Such a helper is kept
as a *follower* of its role - build.py gives it the same rotation about the
role's pivot.
"""
import re

from mathutils import Vector

from . import expressions

PREFIX = re.compile(r"^(?:Bip\d+|AC)\s+", re.I)
# helper duplicates and mmd_tools' own additional-transform proxies
HELPER = re.compile(r"^(?:AC\s+|_dummy_|_shadow_)", re.I)

# role -> spellings, in preference order (prefix stripped, lower case)
ROLE_NAMES = {
    "eye_L": ("左目", "目.l", "eyeball_l", "eye_l", "eyeball.l", "eye.l"),
    "eye_R": ("右目", "目.r", "eyeball_r", "eye_r", "eyeball.r", "eye.r"),
    "upper_lid_L": ("eyelid_ul", "eyelid_lt", "eyelid_up_l", "eyelid_l_up", "uppereyelid_l"),
    "upper_lid_R": ("eyelid_ur", "eyelid_rt", "eyelid_up_r", "eyelid_r_up", "uppereyelid_r"),
    "lower_lid_L": ("eyelid_bl", "eyelid_lb", "eyelid_dn_l", "eyelid_l_dn", "lowereyelid_l"),
    "lower_lid_R": ("eyelid_br", "eyelid_rb", "eyelid_dn_r", "eyelid_r_dn", "lowereyelid_r"),
    "brow_L": ("eyebrow_l", "brow_l"),
    "brow_R": ("eyebrow_r", "brow_r"),
    "chin": ("chin", "jaw"),
    "corner_L": ("lip_l", "lips_l", "mouth_l"),
    "corner_R": ("lip_r", "lips_r", "mouth_r"),
    "upper_lip_C": ("lip_uc", "lips_tc", "lips_up", "lip_u", "lips_uc"),
    "upper_lip_L": ("lip_ucl", "lips_tl", "lips_up_l"),
    "upper_lip_R": ("lip_ucr", "lips_tr", "lips_up_r"),
    "lower_lip_C": ("lip_bc", "lips_bc", "lips_dn", "lip_b", "lip_dc", "lips_dc"),
    "lower_lip_L": ("lip_bcl", "lips_bl", "lips_dn_l"),
    "lower_lip_R": ("lip_bcr", "lips_br", "lips_dn_r"),
    "tongue_0": ("tongue", "tongue01", "tongue_01", "tongue1"),
    "teeth_up": ("teeth_up", "teeth_u", "teeth_t", "teeth_upper", "upperteeth"),
    "teeth_dw": ("teeth_dw", "teeth_b", "teeth_d", "teeth_down", "teeth_lower", "lowerteeth"),
}

# the spelling of the upper-left lid names the style; families are NOT a guide
# (c01-c07 are lowercase, c08-c10 capitalised, and so on through the roster)
STYLE_OF = {"eyelid_ul": "lowercase (eyelid_UL / lip_UC / chin)",
            "eyelid_lt": "capitalised (Eyelid_LT / Lips_TC / Chin)",
            "eyelid_up_l": "b01 (eyelid_UP_L / Lips_UP / Jaw)"}

PAIRED = ("eye", "upper_lid", "lower_lid", "brow", "corner")

# every role a recipe can ask for, derived roles included
EXPECTED_ROLES = sorted({role for recipe in expressions.MORPHS
                         for role, _kind, _amount in recipe["actions"]} | set(ROLE_NAMES))


def strip(name):
    return PREFIX.sub("", name).lower()


class Face(object):
    """What was found on one armature, plus the frame the recipes need."""

    def __init__(self, arm):
        self.arm = arm
        self.bones = {}         # role -> bone name
        self.followers = {}     # role -> [helper bones that must move with it]
        self.unit = 0.06        # eye spacing in armature units
        self.calibrated = False  # True when ``unit`` was measured on a real pair
        self.front = -1.0       # sign of the armature Y axis that points forward
        self.centre_x = 0.0
        self.head = None        # head bone name
        self.style = "unknown"

    # -- lookups -------------------------------------------------------------
    def bone(self, role):
        return self.bones.get(role)

    def has(self, *roles):
        return all(role in self.bones for role in roles)

    def side_of(self, bone_name):
        """+1 for the character's left (+X in mmd_tools models), -1 right."""
        x = self.arm.data.bones[bone_name].head_local.x - self.centre_x
        return -1.0 if x < -1e-6 else 1.0

    def missing(self):
        return [role for role in EXPECTED_ROLES if role not in self.bones]

    def describe(self):
        found = sorted(self.bones)
        followers = " ".join("%s<-%s" % (role, ",".join(names)) for role, names in sorted(self.followers.items()))
        return ("style %s, unit %.3f%s, front %+d, %d roles: %s | missing: %s%s" % (
            self.style, self.unit, "" if self.calibrated else " (GUESSED, no eye/lid/brow pair)",
            int(self.front), len(found),
            " ".join("%s=%s" % (r, self.bones[r]) for r in found), " ".join(self.missing()) or "-",
            (" | followers: " + followers) if followers else ""))


def _index(arm):
    """stripped lower-case name -> bone name (helpers excluded)."""
    index = {}
    for bone in arm.data.bones:
        if HELPER.match(bone.name):
            continue
        index.setdefault(strip(bone.name), bone.name)
    return index


def _mmd_named(arm, japanese):
    for pose_bone in arm.pose.bones:
        if HELPER.match(pose_bone.name):
            continue
        mmd = getattr(pose_bone, "mmd_bone", None)
        if mmd is not None and mmd.name_j == japanese:
            return pose_bone.name
    return None


def _brow_segments(face, side):
    root = face.bone("brow_%s" % side)
    if not root:
        return
    bone = face.arm.data.bones[root]
    segments = [c for c in bone.children
                if not HELPER.match(c.name) and strip(c.name).startswith(("eyebrow", "brow"))]
    if not segments:
        # no segments: the root itself is tilted by the "tilt" role
        face.bones["brow_%s_tilt" % side] = root
        return
    segments.sort(key=lambda c: abs(c.head_local.x - face.centre_x))
    if len(segments) == 1:
        names = {"centre": segments[0].name}
    elif len(segments) == 2:
        names = {"inner": segments[0].name, "outer": segments[1].name}
    else:
        names = {"inner": segments[0].name, "centre": segments[len(segments) // 2].name,
                 "outer": segments[-1].name}
    for key, name in names.items():
        face.bones["brow_%s_%s" % (side, key)] = name


def _tongue_chain(face):
    root = face.bone("tongue_0")
    if not root:
        return
    bone = face.arm.data.bones[root]
    chain = [bone]
    while True:
        children = [c for c in bone.children if not HELPER.match(c.name)]
        if not children:
            break
        bone = max(children, key=lambda c: len(c.children_recursive))   # the longest branch
        chain.append(bone)
    for i, link in enumerate(chain[1:], 1):
        face.bones["tongue_%d" % i] = link.name


def _followers(face):
    """``AC`` helpers named like a role but living OUTSIDE that role's subtree.

    A helper under its control needs nothing (it inherits the pose); one
    parented elsewhere - ``AC jaw`` under the neck - has to be driven
    explicitly or its skin stays behind.
    """
    arm = face.arm
    by_spelling = {}
    for role, spellings in ROLE_NAMES.items():
        for spelling in spellings:
            by_spelling.setdefault(spelling, role)
    for bone in arm.data.bones:
        if not bone.name.lower().startswith("ac "):
            continue
        role = by_spelling.get(strip(bone.name))
        control = face.bone(role) if role else None
        if control is None or control == bone.name:
            continue
        control_bone = arm.data.bones[control]
        if control_bone in bone.parent_recursive:
            continue
        face.followers.setdefault(role, []).append(bone.name)


def resolve(arm):
    """Return a Face for the armature (roles may be missing; check ``has``)."""
    face = Face(arm)
    index = _index(arm)
    for role, spellings in ROLE_NAMES.items():
        for spelling in spellings:
            if spelling in index:
                face.bones[role] = index[spelling]
                if role == "upper_lid_L":
                    face.style = STYLE_OF.get(spelling, spelling)
                break
    for role, japanese in (("eye_L", "左目"), ("eye_R", "右目")):
        name = _mmd_named(arm, japanese)
        if name:
            face.bones[role] = name
    head = _mmd_named(arm, "頭") or index.get("head") or index.get("頭")
    face.head = head

    # the frame: midline, eye spacing, which way is forward
    xs = []
    for stem in PAIRED:
        left, right = face.bone(stem + "_L"), face.bone(stem + "_R")
        if left and right:
            xs.append((arm.data.bones[left].head_local.x + arm.data.bones[right].head_local.x) * 0.5)
    face.centre_x = sum(xs) / len(xs) if xs else (arm.data.bones[head].head_local.x if head else 0.0)

    for stem in ("eye", "upper_lid", "brow"):
        left, right = face.bone(stem + "_L"), face.bone(stem + "_R")
        if left and right:
            spacing = (arm.data.bones[left].head_local - arm.data.bones[right].head_local).length
            if spacing > 1e-6:
                face.unit = spacing
                face.calibrated = True
                break
    else:
        # no facial pair to measure: a guess, and the recipes refuse to build on it
        if head:
            face.unit = max(arm.data.bones[head].length * 0.5, 1e-3)

    if head:
        origin = arm.data.bones[head].head_local
        ys = [arm.data.bones[name].head_local.y - origin.y
              for role, name in face.bones.items()
              if role.startswith(("upper_lid", "lower_lid", "eye", "chin", "corner"))]
        if ys and abs(sum(ys)) > 1e-6:
            face.front = -1.0 if sum(ys) < 0 else 1.0

    for side in "LR":
        _brow_segments(face, side)
    _tongue_chain(face)
    _followers(face)
    return face


def forward(face):
    return Vector((0.0, face.front, 0.0))
