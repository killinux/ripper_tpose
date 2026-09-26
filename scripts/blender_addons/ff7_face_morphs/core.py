# -*- coding: utf-8 -*-
"""FF7 Remake face expressions -> shape keys with MMD names (a PMX export writes them as vertex morphs).

The Remake face is a bone rig (~104 bones under C_FaceBase_a: lids, lashes, brows, lips, jaw, tongue,
cheeks) with no shape keys, and the game keeps its expressions as data:

  * Motion/Player/<char>/Facial00/F_*.uasset - single-frame, non-additive AnimSequences, one full face
    pose each (F_Eyelid_blink01, F_Smile01, F_Angry01, F_Brow_up01 ...; F_Idle01 = the neutral face);
  * LipSync/LipMap/Player/<char>/<Name>_Default.uasset - the HSF lip-sync visemes aa / ee / oo / sh /
    fv / ln / bmp as per-bone Maya channels (translate = absolute position under C_FaceBase_a in cm,
    X left / Y up / Z forward; rotate in degrees; DefaultShape = the rest values).

scripts/final/ff7_face_data.py turns both into a face-data JSON (kept outside the repo: game data).
Every MMD expression here is a RECIPE of those poses restricted to a face REGION (the eye morphs take
only the lid bones of a pose, the brow morphs only the brow bones ...).  A pose counts relative to
F_Idle01, not to the bind pose: the game's neutral face is not the bind pose (tongue 5 mm back, inner
lips 1.5 mm) and subtracting the bind pose would put that offset into every morph.

build_shape_keys() must run while the face bones exist (export_ff7_pmx_blender.py merges them into
the head): it poses the bones, evaluates the skinned mesh and stores the difference to the rest mesh
as a shape key.  stash() / restore() take the keys off around a Convert_to_MMD5 conversion - its pose
bakes (_bake_pose_delta_to_rest: A-pose, arm / finger alignment) SKIP every mesh that has shape keys,
and an FF7 body is one mesh.  register_morphs() files the keys under the PMX panels.
"""
import glob
import json
import math
import os
import re

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

FACE_ROOT = "C_FaceBase_a"
TAG = "ff7_face_morphs"                   # object property: the shape keys this add-on built
STASH_TAG = "ff7_face_morphs_stash"       # object property: mesh datablock holding the stashed keys
STASH_PREFIX = "FF7FaceMorphs_stash_"
NO_MORPH = re.compile(r"^[LR]_Eye$|^C_FaceBase|^C_Ex_")       # gaze stays on the eye bones
REGIONS = {
    "eye_l": r"^L_(Ulid|Dlid|Ulash|Fold|Eyebag)_",
    "eye_r": r"^R_(Ulid|Dlid|Ulash|Fold|Eyebag)_",
    "cheek_l": r"^L_(Cheek_A|Zygoma)$",
    "cheek_r": r"^R_(Cheek_A|Zygoma)$",
    "brow": r"^[CLR]_(Brow_[A-Z]|Forehead|Glabella)$",
    "mouth": r"lip|cor|^C_Chin$|teeth|Tong|Laughline|Cheek_[BC]$|Gonion|Throat|Nose_[AB]$",
}
EYES = ("eye_l", "eye_r")
CHEEKS = ("cheek_l", "cheek_r")
ALL = tuple(REGIONS)
CATEGORIES = ("EYE", "EYEBROW", "MOUTH", "OTHER")

# (MMD name, English name, panel, [(kind, source, regions, weight), ...])
#   kind "pose": a game pose (Facial00) minus F_Idle01; kind "lip": a lip-map viseme minus DefaultShape.
RECIPES = [
    # --- eyes
    ("まばたき", "blink", "EYE", [("pose", "F_Eyelid_blink01", EYES, 1.0)]),
    ("笑い", "smile", "EYE", [("pose", "F_Eyelid_blink01", EYES, 1.0), ("pose", "F_Glad01", CHEEKS, 1.0)]),
    ("ウィンク", "wink", "EYE", [("pose", "F_Eyelid_blink01", ("eye_l",), 1.0),
                               ("pose", "F_Glad01", ("cheek_l",), 1.0)]),
    ("ウィンク右", "wink_R", "EYE", [("pose", "F_Eyelid_blink01", ("eye_r",), 1.0),
                                  ("pose", "F_Glad01", ("cheek_r",), 1.0)]),
    ("ウィンク２", "wink2", "EYE", [("pose", "F_Eyelid_blink01", ("eye_l",), 1.0)]),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", [("pose", "F_Eyelid_blink01", ("eye_r",), 1.0)]),
    ("じと目", "jito-eye", "EYE", [("pose", "F_Eyelid_down01", EYES, 1.0)]),
    ("びっくり", "surprised", "EYE", [("pose", "F_Surprise01", EYES, 1.0)]),
    ("はぅ", "close><", "EYE", [("pose", "F_Dmg02", EYES + CHEEKS, 1.0)]),     # Dmg01 squeezes one eye only
    ("なごみ", "calm", "EYE", [("pose", "F_Tired01", EYES, 1.0)]),
    # --- brows
    ("真面目", "serious", "EYEBROW", [("pose", "F_Serious01", ("brow",), 1.0)]),
    ("困る", "trouble", "EYEBROW", [("pose", "F_Sad01", ("brow",), 1.0)]),
    ("にこり", "cheerful", "EYEBROW", [("pose", "F_Glad01", ("brow",), 1.0)]),
    ("怒り", "anger", "EYEBROW", [("pose", "F_Angry01", ("brow",), 1.0)]),
    ("上", "brow_up", "EYEBROW", [("pose", "F_Brow_up01", ("brow",), 1.0)]),
    ("下", "brow_down", "EYEBROW", [("pose", "F_Brow_down01", ("brow",), 1.0)]),
    # --- mouth: the vowels are the game's own lip-sync shapes
    ("あ", "a", "MOUTH", [("lip", "aa", ("mouth",), 1.0)]),
    ("い", "i", "MOUTH", [("lip", "ee", ("mouth",), 1.0)]),
    ("う", "u", "MOUTH", [("lip", "oo", ("mouth",), 1.0)]),
    ("え", "e", "MOUTH", [("lip", "aa", ("mouth",), 0.5), ("lip", "ee", ("mouth",), 0.6)]),
    ("お", "o", "MOUTH", [("lip", "oo", ("mouth",), 1.0), ("lip", "aa", ("mouth",), 0.45)]),
    ("ん", "n", "MOUTH", [("lip", "bmp", ("mouth",), 1.0)]),
    ("ワ", "wa", "MOUTH", [("pose", "F_Glad01", ("mouth",), 1.0), ("lip", "aa", ("mouth",), 0.4)]),
    ("にっこり", "smile_mouth", "MOUTH", [("pose", "F_Smile01", ("mouth",), 1.0)]),
    ("にやり", "grin", "MOUTH", [("pose", "F_Sneer01", ("mouth",), 1.0)]),
    ("∧", "mouth_∧", "MOUTH", [("pose", "F_Sad01", ("mouth",), 1.0)]),
    ("口角上げ", "mouth_corner_up", "MOUTH", [("pose", "F_Smile01", ("mouth",), 0.6)]),
    ("口角下げ", "mouth_corner_down", "MOUTH", [("pose", "F_Disgust01", ("mouth",), 1.0)]),
    ("口横広げ", "mouth_wide", "MOUTH", [("lip", "ee", ("mouth",), 0.6)]),
]
# The game's whole-face expressions, under 'other' with their game names.
GAME_FACES = ("F_Smile01", "F_Glad01", "F_Surprise01", "F_Sad01", "F_Angry01", "F_Angry02", "F_Serious01",
              "F_Disgust01", "F_Sneer01", "F_Tired01", "F_Dmg01", "F_Dmg02", "F_Attack01", "F_Attack02")
MIN_OFFSET_CM = 1e-3      # vertex offsets below this (in centimetres, scaled to the model) are rounding noise
DATA_DIRS = [d for d in (os.environ.get("FF7_FACE_DATA_DIR"), r"E:\game_export\FF7Remake\_meta\face") if d]


# --- model ------------------------------------------------------------------------------------------
def model_parts(obj, scene=None):
    """(armature, [meshes deformed by it]) for any object of the model (armature, mesh, mmd root)."""
    scene = scene or bpy.context.scene
    arm = None
    if obj is not None and obj.type == "ARMATURE":
        arm = obj
    elif obj is not None and obj.type == "MESH":
        arm = next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        if arm is None and obj.parent is not None and obj.parent.type == "ARMATURE":
            arm = obj.parent
    elif obj is not None:
        stack = list(obj.children)
        while stack and arm is None:
            o = stack.pop()
            if o.type == "ARMATURE":
                arm = o
            stack.extend(o.children)
    if arm is None:
        raise RuntimeError("select the character's armature or one of its meshes")
    meshes = [o for o in scene.objects if o.type == "MESH" and
              any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
    return arm, meshes


def face_bones(arm):
    root = arm.data.bones.get(FACE_ROOT)
    return [] if root is None else [b.name for b in root.children if not NO_MORPH.search(b.name)]


def skinned(meshes, bones):
    names = set(bones)
    return [m for m in meshes if any(vg.name in names for vg in m.vertex_groups)]


def tagged(obj):
    """Names of the shape keys this add-on built on obj (stored as one newline-joined string)."""
    return [n for n in str(obj.get(TAG, "")).split("\n") if n]


def _add_tagged(obj, names):
    have = tagged(obj)
    obj[TAG] = "\n".join(have + [n for n in names if n not in have])


def mmd_root_of(obj):
    while obj is not None:
        if getattr(obj, "mmd_type", "") == "ROOT":
            return obj
        obj = obj.parent
    return None


# --- face data --------------------------------------------------------------------------------------
def character_code(arm, meshes=()):
    for name in [arm.name, arm.data.name] + [m.name for m in meshes] + [bpy.path.basename(bpy.data.filepath)]:
        m = re.search(r"PC\d{4}", name or "", re.IGNORECASE)
        if m:
            return m.group(0).upper()
    return ""


def find_face_data(arm, meshes=()):
    """The face-data JSON for this character in DATA_DIRS (PC0002 -> PC0002_Tifa.json), or ""."""
    code = character_code(arm, meshes)
    found = []
    for folder in DATA_DIRS:
        found += sorted(glob.glob(os.path.join(folder, "*.json")))
    for path in found:
        if code and os.path.basename(path).upper().startswith(code):
            return path
    return found[0] if len(found) == 1 else ""


def load_face_data(path):
    with open(bpy.path.abspath(path), encoding="utf-8") as fh:
        data = json.load(fh)
    if "poses" not in data or "lipmap" not in data:
        raise RuntimeError("not a face-data file (ff7_face_data.py output): %s" % path)
    return data


def face_frame(arm):
    """Armature-space matrix of the face frame: origin C_FaceBase_a, X forward, Y left, Z up."""
    bones = arm.data.bones
    if "L_Eye" not in bones or "R_Eye" not in bones or FACE_ROOT not in bones:
        raise RuntimeError("no FF7 face rig here (C_FaceBase_a / L_Eye / R_Eye) - open the source .blend, "
                           "not a converted PMX")
    left = bones["L_Eye"].head_local - bones["R_Eye"].head_local
    spacing = left.length
    left.normalize()
    up = Vector((0.0, 0.0, 1.0))
    up = (up - left * up.dot(left)).normalized()
    fwd = left.cross(up)
    frame = Matrix((fwd, left, up)).transposed().to_4x4()
    frame.translation = bones[FACE_ROOT].head_local
    return frame, spacing


def _mat(flat):
    return Matrix([flat[0:4], flat[4:8], flat[8:12], flat[12:16]])


def _split(d, head):
    """Rigid delta -> (translation of the bone head, rotation quaternion)."""
    return (d @ head) - head, d.to_quaternion()


def _join(head, move, rot):
    return Matrix.Translation(head + move) @ rot.to_matrix().to_4x4() @ Matrix.Translation(-head)


def _scaled(rot, weight):
    """rot ** weight (any weight, also above 1)."""
    axis, angle = rot.to_axis_angle()
    return Quaternion(axis, angle * weight)


class FaceData:
    """Poses and lip shapes of one character, re-expressed on a target armature."""

    MAYA_TO_FACE = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))   # (X left, Y up, Z fwd) -> (fwd, left, up)

    def __init__(self, data, arm):
        self.data, self.arm = data, arm
        self.frame, spacing = face_frame(arm)
        self.scale = spacing / data["eye_spacing"]
        self.rot = self.frame.to_3x3()

    def _to_arm(self, d_face):
        s = Matrix.Diagonal((self.scale,) * 3).to_4x4()
        return self.frame @ s @ d_face @ s.inverted() @ self.frame.inverted()

    def pose(self, name):
        """{bone: armature-space delta} of a game pose relative to F_Idle01."""
        poses = self.data["poses"]
        idle = poses.get("F_Idle01", {})
        out = {}
        for bone, flat in poses[name].items():
            if bone not in self.arm.data.bones or NO_MORPH.search(bone):
                continue
            d = self._to_arm(_mat(flat))
            if bone in idle:
                d = d @ self._to_arm(_mat(idle[bone])).inverted()
            out[bone] = d
        return out

    def lip(self, name):
        """{bone: armature-space delta} of a lip-map viseme relative to DefaultShape."""
        lipmap = self.data["lipmap"]
        default = lipmap["DefaultShape"]
        p = self.MAYA_TO_FACE
        out = {}
        for bone, ch in lipmap["shapes"][name].items():
            if bone not in self.arm.data.bones or NO_MORPH.search(bone):
                continue
            base = default.get(bone, {})
            t = Vector([ch.get("Translate" + k, base.get("Translate" + k, 0.0)) - base.get("Translate" + k, 0.0)
                        for k in "XYZ"])
            r = Euler([math.radians(ch.get("Rotate" + k, 0.0) - base.get("Rotate" + k, 0.0)) for k in "XYZ"],
                      "XYZ").to_matrix()
            head = self.arm.data.bones[bone].head_local
            move = self.rot @ (p @ t) * self.scale
            rot = (self.rot @ p @ r @ p.transposed() @ self.rot.transposed()).to_quaternion()
            out[bone] = _join(head, move, rot)
        return out


def recipes_for(data, categories=CATEGORIES):
    """RECIPES whose sources this character has (+ the whole-face game poses as OTHER), in panel order."""
    poses, shapes = data["poses"], data["lipmap"]["shapes"]
    out = []
    for name, name_e, category, components in RECIPES:
        if category in categories and all((s in poses) if k == "pose" else (s in shapes)
                                          for k, s, _r, _w in components):
            out.append((name, name_e, category, components))
    if "OTHER" in categories:
        for game in GAME_FACES:
            if game in poses:
                out.append((game, game, "OTHER", [("pose", game, ALL, 1.0)]))
    return out


def recipe_deltas(face, components, strength=1.0):
    """Combine weighted, region-restricted components into one {bone: delta}."""
    bones = face.arm.data.bones
    moves, rots = {}, {}
    for kind, source, regions, weight in components:
        pattern = re.compile("|".join("(?:%s)" % REGIONS[r] for r in regions))
        deltas = face.pose(source) if kind == "pose" else face.lip(source)
        w = weight * strength
        for bone, d in deltas.items():
            if not pattern.search(bone):
                continue
            head = bones[bone].head_local
            move, rot = _split(d, head)
            moves[bone] = moves.get(bone, Vector()) + move * w
            rots[bone] = _scaled(rot, w) @ rots.get(bone, Quaternion())
    return {b: _join(bones[b].head_local, moves[b], rots[b]) for b in moves}


# --- baking -----------------------------------------------------------------------------------------
class _RestState:
    """Everything that would leak into the evaluated mesh besides the face bones: the armature's pose,
    other shape keys' values, modifiers that are not the armature.  Saved on enter, restored on exit."""

    def __init__(self, arm, meshes):
        self.arm, self.meshes = arm, meshes

    def __enter__(self):
        self.pose = {pb.name: pb.matrix_basis.copy() for pb in self.arm.pose.bones}
        self.pose_position = self.arm.data.pose_position
        self.arm.data.pose_position = "POSE"
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        self.keys, self.mods = {}, {}
        for m in self.meshes:
            if m.data.shape_keys:
                self.keys[m.name] = [(kb.name, kb.value, kb.mute) for kb in m.data.shape_keys.key_blocks]
                for kb in m.data.shape_keys.key_blocks:
                    kb.value = 0.0
            self.mods[m.name] = [(mod.name, mod.show_viewport) for mod in m.modifiers]
            for mod in m.modifiers:
                if mod.type != "ARMATURE":
                    mod.show_viewport = False
        bpy.context.view_layer.update()
        return self

    def set_face_pose(self, deltas):
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        for bone, d in deltas.items():
            rest = self.arm.data.bones[bone].matrix_local
            self.arm.pose.bones[bone].matrix_basis = rest.inverted() @ d @ rest
        bpy.context.view_layer.update()

    def __exit__(self, *exc):
        for name, basis in self.pose.items():
            pb = self.arm.pose.bones.get(name)
            if pb is not None:
                pb.matrix_basis = basis
        self.arm.data.pose_position = self.pose_position
        for m in self.meshes:
            keys = m.data.shape_keys.key_blocks if m.data.shape_keys else {}
            for name, value, mute in self.keys.get(m.name, []):
                kb = keys.get(name)
                if kb is not None:
                    kb.value, kb.mute = value, mute
            for name, shown in self.mods.get(m.name, []):
                mod = m.modifiers.get(name)
                if mod is not None:
                    mod.show_viewport = shown
        bpy.context.view_layer.update()
        return False


def _coords(obj):
    import numpy as np
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3)


def build_shape_keys(arm, meshes, data, categories=CATEGORIES, strengths=None, log=None):
    """Add one shape key per expression to every mesh skinned to face bones.  Returns
    [(name, name_e, category, moved_vertices)].  The scene's pose / key values come back unchanged."""
    import numpy as np
    face = FaceData(data, arm)
    strengths = strengths or {}
    targets = skinned(meshes, face_bones(arm))
    if not targets:
        raise RuntimeError("no mesh is skinned to the face bones under %s" % FACE_ROOT)
    min_offset = MIN_OFFSET_CM * face.scale
    made = []
    with _RestState(arm, targets) as state:
        rest = {}
        for m in targets:
            rest[m.name] = _coords(m)
            if len(rest[m.name]) != len(m.data.vertices):
                raise RuntimeError("%s: the evaluated mesh has a different vertex count" % m.name)
        for name, name_e, category, components in recipes_for(data, categories):
            state.set_face_pose(recipe_deltas(face, components, strengths.get(category, 1.0)))
            moved = 0
            for m in targets:
                off = _coords(m) - rest[m.name]
                off[np.linalg.norm(off, axis=1) < min_offset] = 0.0
                moved += int(np.count_nonzero(np.any(off != 0.0, axis=1)))
                if m.data.shape_keys is None:
                    m.shape_key_add(name="Basis", from_mix=False)
                keys = m.data.shape_keys.key_blocks
                key = keys.get(name) or m.shape_key_add(name=name, from_mix=False)
                base = np.empty(len(m.data.vertices) * 3)
                keys[0].data.foreach_get("co", base)
                key.data.foreach_set("co", (base.reshape(-1, 3) + off).ravel())
                key.value = 0.0
            made.append((name, name_e, category, moved))
            if log:
                log("%s (%s): %d vertices" % (name_e, category, moved))
    for m in targets:
        _add_tagged(m, [x[0] for x in made])
    return made


def built_names(meshes):
    names = []
    for m in meshes:
        for n in tagged(m):
            if n not in names:
                names.append(n)
    order = {r[0]: i for i, r in enumerate(RECIPES)}
    order.update({g: len(RECIPES) + i for i, g in enumerate(GAME_FACES)})
    return sorted(names, key=lambda n: order.get(n, 10 ** 6))


def clear(meshes):
    """Remove the shape keys this add-on built (never anything else).  Returns their names."""
    removed = []
    for m in meshes:
        mine = set(tagged(m))
        if not mine or not m.data.shape_keys:
            m.pop(TAG, None)
            continue
        # by name: removing a key block invalidates the Python references to the others
        for name in [kb.name for kb in m.data.shape_keys.key_blocks][1:]:
            if name in mine:
                m.shape_key_remove(m.data.shape_keys.key_blocks[name])
                removed.append(name)
        if m.data.shape_keys and len(m.data.shape_keys.key_blocks) == 1:
            m.shape_key_clear()
        m.pop(TAG, None)
    return sorted(set(removed))


def preview(meshes, name, weight):
    """Show one built expression at `weight` (all other built ones at 0)."""
    for m in meshes:
        if not m.data.shape_keys:
            continue
        mine = set(tagged(m))
        for kb in m.data.shape_keys.key_blocks:
            if kb.name in mine:
                kb.value = weight if kb.name == name else 0.0


# --- around a Convert_to_MMD5 conversion ------------------------------------------------------------
def stash(meshes):
    """Move every shape key of these meshes into a fake-user copy of the mesh data (kept in the .blend,
    so it survives save / reload) and take them off the mesh.  Convert_to_MMD5's pose bakes skip meshes
    that have shape keys.  Returns {object: stash datablock}."""
    out = {}
    for m in meshes:
        if not m.data.shape_keys or len(m.data.shape_keys.key_blocks) < 2:
            continue
        old = bpy.data.meshes.get(m.get(STASH_TAG, ""))
        if old is not None:
            bpy.data.meshes.remove(old)
        copy = m.data.copy()
        if copy.shape_keys is None:
            bpy.data.meshes.remove(copy)
            raise RuntimeError("%s: copying the mesh lost its shape keys" % m.name)
        copy.name = STASH_PREFIX + m.name
        copy.use_fake_user = True
        m[STASH_TAG] = copy.name
        m.shape_key_clear()
        out[m.name] = copy.name
    return out


def _fit_linear(src, dst):
    """Least-squares similarity (rotation * scale) taking centred src onto centred dst."""
    import numpy as np
    a, b = src - src.mean(axis=0), dst - dst.mean(axis=0)
    u, s, vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(u @ vt))
    rot = (u @ np.diag([1.0, 1.0, d]) @ vt).T
    scale = (s * [1.0, 1.0, d]).sum() / max((a * a).sum(), 1e-12)
    return rot * scale


def restore(meshes, relative_tolerance=1e-4):
    """Put stashed keys back.  The face should not have moved during the conversion (it poses arms,
    fingers and legs); if it moved rigidly (turned, scaled to metres) the offsets follow it; if it
    deformed, the keys are dropped and reported.  Returns {object: report}."""
    import numpy as np
    report = {}
    for m in meshes:
        copy = bpy.data.meshes.get(m.get(STASH_TAG, ""))
        if copy is None:
            continue
        n = len(m.data.vertices)
        keys = copy.shape_keys.key_blocks if copy.shape_keys else []
        if len(copy.vertices) != n or len(keys) < 2:
            report[m.name] = "vertex count changed (%d -> %d) - expressions dropped" % (len(copy.vertices), n)
            continue
        base = np.empty(n * 3)
        keys[0].data.foreach_get("co", base)
        base = base.reshape(-1, 3)
        deltas, touched = [], np.zeros(n, dtype=bool)
        for kb in list(keys)[1:]:
            co = np.empty(n * 3)
            kb.data.foreach_get("co", co)
            d = co.reshape(-1, 3) - base
            idx = np.nonzero(np.any(d != 0.0, axis=1))[0]
            deltas.append((kb.name, idx, d[idx]))
            touched[idx] = True
        now = np.empty(n * 3)
        m.data.vertices.foreach_get("co", now)
        now = now.reshape(-1, 3)
        ref = np.nonzero(touched)[0]
        src, dst = base[ref], now[ref]
        size = float(np.abs(dst - dst.mean(axis=0)).max()) if len(ref) else 1.0
        tolerance = max(size, 1e-9) * relative_tolerance
        moved = float(np.abs(dst - src).max()) if len(ref) else 0.0
        lin = np.eye(3)
        if moved > tolerance:
            lin = _fit_linear(src, dst)
            fitted = (src - src.mean(axis=0)) @ lin.T + dst.mean(axis=0)
            residual = float(np.abs(fitted - dst).max())
            if residual > tolerance:
                report[m.name] = "face deformed during the conversion (%.6f) - expressions dropped" % residual
                continue
        if m.data.shape_keys is None:
            m.shape_key_add(name="Basis", from_mix=False)
        live = m.data.shape_keys.key_blocks
        for name, idx, d in deltas:
            kb = live.get(name) or m.shape_key_add(name=name, from_mix=False)
            buf = now.copy()
            buf[idx] += d @ lin.T
            kb.data.foreach_set("co", buf.ravel())
            kb.value = 0.0
        _add_tagged(m, [d[0] for d in deltas])
        del m[STASH_TAG]
        bpy.data.meshes.remove(copy)
        report[m.name] = {"keys": len(deltas), "face_moved": round(moved, 6)}
    return report


def stashed(meshes):
    return [m.name for m in meshes if bpy.data.meshes.get(m.get(STASH_TAG, "")) is not None]


def register_morphs(root, meshes):
    """mmd_tools model: name_e + panel for every built expression, RECIPES order first, facial display
    frame rebuilt.  Returns the names registered."""
    info = {r[0]: (r[1], r[2]) for r in RECIPES}
    info.update({g: (g, "OTHER") for g in GAME_FACES})
    names = [n for n in built_names(meshes)
             if any(m.data.shape_keys and n in m.data.shape_keys.key_blocks for m in meshes)]
    mmd = root.mmd_root
    have = {m.name: m for m in mmd.vertex_morphs}
    for name in names:
        item = have.get(name)
        if item is None:
            item = mmd.vertex_morphs.add()
            item.name = name
        item.name_e, item.category = info.get(name, (name, "OTHER"))
    for target, name in enumerate(names):
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(name), target)
    from mmd_tools.operators.display_item import DisplayItemQuickSetup
    if "表情" in mmd.display_item_frames:
        mmd.display_item_frames["表情"].data.clear()
    DisplayItemQuickSetup.load_facial_items(mmd)
    return names
