# -*- coding: utf-8 -*-
"""Expression sources: where the face movement comes from.

A source is either a POSE source (it says how the face bones move; the result can become an MMD
bone morph as it is, or be baked through the skin into shape keys) or a SHAPE source (it already
has vertex offsets; the result can only become shape keys / vertex morphs).  Each one reads the
recipes of its own vocabulary (recipes.py):

  DnaSource          MetaHuman DNA + FACIAL_* bones       pose   'metahuman'
  ShapeKeySource     existing ARKit shape keys            shape  'arkit'
  PoseLibrarySource  actions / pose markers / captured    pose   'names' (a pose named like the target)
  RoleSource         bone-only face, calibrated actions   pose   'roles'

Poses are {bone: (location, rotation quaternion)} in pose (matrix_basis) space - exactly what an
mmd_tools bone morph stores and what MMD applies.
"""
import json
import os
import re

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import dna as dnalib
from . import names, roles

POSE, SHAPE = "pose", "shape"
KINDS = (("DNA", "MetaHuman DNA", "The face's .dna file drives the FACIAL_* bones (Vindictus, MetaHuman Creator)"),
         ("SHAPES", "已有形态键", "Mix the model's own ARKit shape keys (mods, VRoid Perfect Sync, CC4 ...)"),
         ("POSES", "姿势库", "Poses you made: captured poses, actions or pose markers named like the target"),
         ("ROLES", "骨骼脸自动", "Bone-only face with no data: eyelid / brow / jaw / lip bones moved by "
                                 "calibrated recipes (Rise of Eros style)"))
EPS_LOC = 1e-6
EPS_ROT = 1e-5
EPS_SCALE = 1e-5
ONE = Vector((1.0, 1.0, 1.0))


def _tiny(loc, quat, scale=None):
    return loc.length < EPS_LOC and abs(quat.angle) < EPS_ROT and (scale is None or (scale - ONE).length < EPS_SCALE)


def entry(loc, quat, scale=None):
    """A pose entry: (location, quaternion) or, when it scales, (location, quaternion, scale).
    PMX bone morphs cannot scale, so a scaled entry forces a vertex morph (engine.py)."""
    if scale is not None and (scale - ONE).length >= EPS_SCALE:
        return (loc, quat, scale)
    return (loc, quat)


def unpack(value):
    """(location, quaternion, scale or None) of a pose entry."""
    return (value[0], value[1], value[2] if len(value) > 2 else None)


class Source:
    key, form, vocab = "", POSE, ""

    def __init__(self, arm):
        self.arm = arm

    def recipe(self, target):
        return target.get(self.vocab) or None

    def why_not(self, target):
        return "no %s recipe" % self.vocab

    def against(self, target):
        return None

    def pose(self, components, strength=1.0):
        raise NotImplementedError

    def shapes(self, components, strength=1.0):
        raise NotImplementedError

    def face_bones(self):
        """Bones this source moves (the meshes weighted to them get the shape keys)."""
        return []

    def info(self):
        return {}


# --------------------------------------------------------------------------------------------------
# MetaHuman DNA
# --------------------------------------------------------------------------------------------------
_DNA_CACHE = {}

# where a MetaHuman joint ends up after an XPS export / an MMD conversion
RENAMED = {"FACIAL_L_Eye": ("head eyeball left", "左目", "目.L"), "FACIAL_R_Eye": ("head eyeball right", "右目", "目.R"),
           "FACIAL_C_Jaw": ("head jaw",)}
FACE_WORDS = ("facial", "eye", "目", "jaw", "顎", "tongue", "teeth", "lip", "brow", "cheek", "nose", "unused")


def load_dna(path):
    path = bpy.path.abspath(path)
    key = (path, os.path.getmtime(path))
    if key not in _DNA_CACHE:
        with open(path, "rb") as fh:
            face = dnalib.DnaFace(fh.read())
        _DNA_CACHE.clear()
        _DNA_CACHE[key] = face
    return _DNA_CACHE[key]


class DnaPoser:
    """Put DNA joint poses onto the rig.  Joints pair with bones by name (exact, case-insensitive,
    'unused_' prefix of a conversion, XPS / MMD renames), then a similarity fit maps DNA space (cm,
    Maya Y-up) onto the rig; joints still unpaired pair with a face bone sitting at the fitted
    position (< 1 mm) - that catches renames nobody listed."""

    def __init__(self, face, arm, min_joints=30):
        from mathutils import kdtree

        self.face, self.arm = face, arm
        bones = arm.data.bones
        lower = {b.name.lower(): b.name for b in bones}
        mmd_j = {}
        for pb in arm.pose.bones:
            mmd = getattr(pb, "mmd_bone", None)
            if mmd is not None and mmd.name_j:
                mmd_j.setdefault(mmd.name_j, pb.name)
        match, used = {}, set()
        facial = [j for j, n in enumerate(face.joints) if n.upper().startswith("FACIAL_")]
        for j in facial:
            name = face.joints[j]
            for cand in (name, "unused_" + name) + RENAMED.get(name, ()):
                bone = cand if cand in bones else lower.get(cand.lower()) or mmd_j.get(cand)
                if bone and bone not in used:
                    match[j] = bone
                    used.add(bone)
                    break
        if len(match) < min_joints:
            raise ValueError("only %d of the DNA's %d facial joints are bones of %s (need %d) - wrong DNA, "
                             "or not a MetaHuman face rig" % (len(match), len(facial), arm.name, min_joints))
        index = sorted(match)
        src = face.rest[index, :3, 3]
        dst = np.array([list(bones[match[j]].head_local) for j in index])
        self.scale, self.rot, self.shift, err = dnalib.fit_similarity(src, dst)
        self.mm = 10.0 / self.scale                            # mm per rig unit (the DNA is in cm)
        by_name = len(match)
        free = [b.name for b in bones if b.name not in used and any(w in b.name.lower() for w in FACE_WORDS)]
        if free and len(match) < len(facial):
            kd = kdtree.KDTree(len(free))
            for i, n in enumerate(free):
                kd.insert(bones[n].head_local, i)
            kd.balance()
            tol = 1.0 / self.mm
            for j in facial:
                if j in match:
                    continue
                p = self.scale * (self.rot @ face.rest[j, :3, 3]) + self.shift
                _co, i, dist = kd.find(Vector(p.tolist()))
                if i is not None and dist < tol and free[i] not in used:
                    match[j] = free[i]
                    used.add(free[i])
        self.index = sorted(match)
        self.names = [match[j] for j in self.index]
        self.fit = {"joints": len(self.index), "by_name": by_name, "by_position": len(self.index) - by_name,
                    "dna_joints": len(facial), "scale": float(self.scale),
                    "mean_mm": float(err.mean() * self.mm), "max_mm": float(err.max() * self.mm)}
        self.rest = {n: bones[n].matrix_local.copy() for n in self.names}
        self.parent = {n: (bones[n].parent.name if bones[n].parent else None) for n in self.names}
        self.parent_rest = {n: (bones[n].parent.matrix_local.copy() if bones[n].parent else Matrix())
                            for n in self.names}

    def bases(self, controls):
        """matrix_basis per facial bone for these raw control values."""
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


class DnaSource(Source):
    key, form, vocab = "DNA", POSE, "metahuman"

    def __init__(self, arm, path):
        super().__init__(arm)
        if not path or not os.path.isfile(bpy.path.abspath(path)):
            raise ValueError("choose the face's MetaHuman DNA file (.dna)")
        self.path = path
        self.face = load_dna(path)
        self.poser = DnaPoser(self.face, arm)

    def recipe(self, target):
        comps = target.get("metahuman")
        if not comps:
            return None
        against = target.get("metahuman_against") or {}
        if any(c not in self.face.raw_index for c in list(comps) + list(against)):
            return None
        return comps

    def why_not(self, target):
        comps = target.get("metahuman")
        if not comps:
            return "no MetaHuman recipe"
        missing = [c for c in comps if c not in self.face.raw_index]
        return "DNA lacks %s" % ", ".join(missing[:3])

    def against(self, target):
        return target.get("metahuman_against")

    def pose(self, components, strength=1.0):
        out = {}
        for name, basis in self.poser.bases({k: v * strength for k, v in components.items()}).items():
            loc, quat, scale = basis.decompose()
            if not _tiny(loc, quat, scale):
                out[name] = entry(loc, quat, scale)
        return out

    def face_bones(self):
        return list(self.poser.names)

    def info(self):
        f = self.poser.fit
        return {"dna": os.path.basename(bpy.path.abspath(self.path)), "joints": f["joints"], "dna_joints": f["dna_joints"],
                "by_position": f["by_position"], "fit_mean_mm": round(f["mean_mm"], 2),
                "fit_max_mm": round(f["max_mm"], 2), "blend_shape_channels": self.face.blend_shape_channels}


# --------------------------------------------------------------------------------------------------
# existing shape keys (ARKit under any spelling)
# --------------------------------------------------------------------------------------------------
def key_coords(key):
    co = np.empty(len(key.data) * 3)
    key.data.foreach_get("co", co)
    return co.reshape(-1, 3)


class ShapeKeySource(Source):
    key, form, vocab = "SHAPES", SHAPE, "arkit"

    def __init__(self, arm, meshes):
        super().__init__(arm)
        self.meshes = [m for m in meshes if m.data.shape_keys and len(m.data.shape_keys.key_blocks) > 1]
        self.alias = {m.name: names.match_arkit([k.name for k in m.data.shape_keys.key_blocks[1:]])
                      for m in self.meshes}
        self.available = set()
        for m in self.meshes:
            self.available.update(self.alias[m.name])
            self.available.update(k.name for k in m.data.shape_keys.key_blocks[1:])

    def recipe(self, target):
        comps = target.get("arkit")
        if not comps:
            return None
        for k in comps:
            opt, name = names.optional(k)
            if not opt and name not in self.available:
                return None
        return comps

    def why_not(self, target):
        comps = target.get("arkit")
        if not comps:
            return "no ARKit recipe"
        missing = [names.optional(k)[1] for k in comps if not names.optional(k)[0]
                   and names.optional(k)[1] not in self.available]
        return "model lacks %s" % ", ".join(missing[:3])

    def shapes(self, components, strength=1.0):
        out = {}
        for m in self.meshes:
            blocks = m.data.shape_keys.key_blocks
            acc = None
            for k, w in components.items():
                _opt, name = names.optional(k)
                key = blocks.get(name) or blocks.get(self.alias[m.name].get(name, ""))
                if key is None:
                    continue
                d = (key_coords(key) - key_coords(key.relative_key)) * (w * strength)
                acc = d if acc is None else acc + d
            if acc is not None and np.abs(acc).max() > 0.0:
                out[m.name] = acc
        return out

    def info(self):
        n = max((len(a) for a in self.alias.values()), default=0)
        return {"meshes_with_keys": [m.name for m in self.meshes], "arkit_keys": n}


# --------------------------------------------------------------------------------------------------
# pose library: captured poses, actions, pose markers
# --------------------------------------------------------------------------------------------------
POSE_PROP = "expression_kit_poses"      # armature object: JSON {name: {bone: [lx, ly, lz, qw, qx, qy, qz(, sx, sy, sz)]}}
_CHANNEL = re.compile(r'^pose\.bones\["(.+)"\]\.(location|rotation_quaternion|rotation_euler|rotation_axis_angle|scale)$')


def captured(arm):
    try:
        raw = json.loads(arm.get(POSE_PROP, "{}"))
    except ValueError:
        return {}
    return {name: {b: entry(Vector(v[:3]), Quaternion(v[3:7]), Vector(v[7:10]) if len(v) >= 10 else None)
                   for b, v in pose.items()} for name, pose in raw.items()}


def capture(arm, name, selected_only=False):
    """Store the armature's current pose (bones that are not at rest) under ``name``."""
    pose = {}
    for pb in arm.pose.bones:
        if selected_only and not pb.bone.select:
            continue
        loc, quat, scale = pb.matrix_basis.decompose()
        if not _tiny(loc, quat, scale):
            pose[pb.name] = list(loc) + list(quat) + (list(scale) if len(entry(loc, quat, scale)) > 2 else [])
    if not pose:
        raise ValueError("the armature is at rest - pose the face first")
    try:
        raw = json.loads(arm.get(POSE_PROP, "{}"))
    except ValueError:
        raw = {}
    raw[name] = pose
    arm[POSE_PROP] = json.dumps(raw, ensure_ascii=False)
    return len(pose)


def forget(arm, name):
    raw = json.loads(arm.get(POSE_PROP, "{}"))
    removed = raw.pop(name, None) is not None
    arm[POSE_PROP] = json.dumps(raw, ensure_ascii=False)
    return removed


def _evaluate_action(action, frame):
    """{bone: (location, quaternion)} of an action at a frame, read from its F-curves directly."""
    chans = {}
    for fc in action.fcurves:
        m = _CHANNEL.match(fc.data_path)
        if m:
            chans.setdefault(m.group(1), {}).setdefault(m.group(2), {})[fc.array_index] = fc.evaluate(frame)
    out = {}
    for bone, ch in chans.items():
        loc = Vector([ch.get("location", {}).get(i, 0.0) for i in range(3)])
        if "rotation_quaternion" in ch:
            q = ch["rotation_quaternion"]
            quat = Quaternion([q.get(0, 1.0), q.get(1, 0.0), q.get(2, 0.0), q.get(3, 0.0)]).normalized()
        elif "rotation_euler" in ch:
            from mathutils import Euler
            quat = Euler([ch["rotation_euler"].get(i, 0.0) for i in range(3)]).to_quaternion()
        elif "rotation_axis_angle" in ch:
            a = ch["rotation_axis_angle"]
            quat = Quaternion(Vector([a.get(1, 0.0), a.get(2, 1.0), a.get(3, 0.0)]), a.get(0, 0.0))
        else:
            quat = Quaternion()
        scale = Vector([ch.get("scale", {}).get(i, 1.0) for i in range(3)])
        if not _tiny(loc, quat, scale):
            out[bone] = entry(loc, quat, scale)
    return out


def action_poses(action, use_markers=True):
    """One pose per pose marker (named after the marker), or the whole action as one pose."""
    if action is None:
        return {}
    if use_markers and len(action.pose_markers):
        return {m.name: _evaluate_action(action, m.frame) for m in action.pose_markers}
    return {action.name: _evaluate_action(action, action.frame_range[0])}


def combine(poses, weights, neutral=None):
    """Weighted mix of poses in pose space, relative to a neutral pose: translations add,
    rotations are raised to the weight and multiplied (what MMD does with several bone morphs),
    scales are raised to the weight and multiplied."""
    out = {}
    for name, w in weights.items():
        for bone, value in poses[name].items():
            loc, quat, scale = unpack(value)
            scale = scale if scale is not None else ONE.copy()
            if neutral and bone in neutral:
                n_loc, n_quat, n_scale = unpack(neutral[bone])
                loc, quat = loc - n_loc, n_quat.inverted() @ quat
                if n_scale is not None:
                    scale = Vector([a / b for a, b in zip(scale, n_scale)])
            l0, q0, s0 = out.get(bone, (Vector(), Quaternion(), ONE.copy()))
            axis, angle = quat.to_axis_angle()
            s1 = Vector([a * (max(b, 1e-6) ** w) for a, b in zip(s0, scale)])
            out[bone] = (l0 + loc * w, Quaternion(axis, angle * w) @ q0, s1)
    return {b: entry(*v) for b, v in out.items() if not _tiny(*v)}


class PoseLibrarySource(Source):
    key, form, vocab = "POSES", POSE, "names"

    def __init__(self, arm, action=None, use_markers=True, neutral=""):
        super().__init__(arm)
        self.poses = action_poses(action, use_markers)
        self.poses.update(captured(arm))
        self.neutral = self.poses.get(neutral) if neutral else None
        if not self.poses:
            raise ValueError("no poses: capture some, or pick an action with pose markers")

    def recipe(self, target):
        comps = target.get("names")
        if comps:
            return comps if all(k in self.poses for k in comps) else None
        return {target["name"]: 1.0} if target["name"] in self.poses else None

    def why_not(self, target):
        return "no pose named %s" % target["name"]

    def pose(self, components, strength=1.0):
        return combine(self.poses, {k: v * strength for k, v in components.items()}, self.neutral)

    def face_bones(self):
        return sorted({b for p in self.poses.values() for b in p})

    def info(self):
        return {"poses": sorted(self.poses)}


# --------------------------------------------------------------------------------------------------
# bone-only faces
# --------------------------------------------------------------------------------------------------
class RoleSource(Source):
    key, form, vocab = "ROLES", POSE, "roles"

    def __init__(self, arm):
        super().__init__(arm)
        self.face = roles.resolve(arm)

    def recipe(self, target):
        acts = target.get("roles")
        if not acts or not self.face.calibrated:
            return None
        if all(self.face.bone(role) is None for role, _k, _a in acts):
            return None
        return acts

    def why_not(self, target):
        if not self.face.calibrated:
            return "no eye / lid / brow pair to calibrate against"
        return "no role recipe" if not target.get("roles") else "the face lacks these bones"

    def pose(self, components, strength=1.0):
        return {b: v for b, v in roles.offsets(self.face, components, strength).items() if not _tiny(*v)}

    def face_bones(self):
        names_ = set(self.face.bones.values())
        for followers in self.face.followers.values():
            names_.update(followers)
        return sorted(names_)

    def info(self):
        return {"roles": len(self.face.bones), "calibrated": self.face.calibrated, "style": self.face.style,
                "eye_spacing": round(self.face.unit, 4), "describe": self.face.describe()}


def make(kind, arm, meshes, dna_path="", action=None, use_markers=True, neutral=""):
    if kind == "DNA":
        return DnaSource(arm, dna_path)
    if kind == "SHAPES":
        return ShapeKeySource(arm, meshes)
    if kind == "POSES":
        return PoseLibrarySource(arm, action, use_markers, neutral)
    if kind == "ROLES":
        return RoleSource(arm)
    raise ValueError("unknown source %r" % kind)
