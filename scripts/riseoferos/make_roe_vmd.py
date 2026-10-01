"""Turn a decoded Rise of Eros motion (decode_roe_clip.py JSON) into a VMD for the character's PMX.

  blender -b --factory-startup --python make_roe_vmd.py -- <clip.json> <model.pmx> <out.vmd>
          [--compare <game.fbx> <out.mp4>]

How the motion is moved onto the PMX
------------------------------------
The PMX is not the game rig: Convert_to_MMD5 renamed the Biped bones (Bip001 L UpperArm -> 左腕),
added MMD bones (センター, 腕捩, 手捩, D bones, IK) and posed the arms down into MMD's A stance
before baking the rest pose.  Copying local rotations would therefore be wrong.  Instead, for every
PMX bone that has a game counterpart, its *world* rotation change from the rest pose is taken from
the game bone (Unity space mapped to Blender: x -> -x, Y up -> Z up):

    D_pmx(t) = D_game(t) * S^-1          D_game(t) = G(t) * G_rest^-1

where S is the swing that turns the game bone's rest direction into the PMX bone's rest direction
(the arms' A stance; identity where the rigs agree).  A PMX bone without a counterpart follows its
parent.  The pose basis written to the action is then  Rrest^-1 * D_parent^-1 * D * Rrest.
MMD conventions on top: センター carries the pelvis translation, 腕 keeps the swing of the upper arm
and 腕捩 its twist, 手捩 takes the hand's twist about the forearm, bones the PMX drives itself
(additional transform, dynamic rigid bodies) get no keys, and the leg/toe IK is switched off in the
VMD so MMD plays the game's own leg rotations.

``--compare`` renders the game mesh (AssetStudio FBX, driven straight from the decoded clip) next
to the PMX with the exported VMD imported back through mmd_tools: the round trip the user makes.
"""
import json
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SCALE = 0.08            # mmd_tools import scale used across this repo (PMX units -> metres)
# mmd_tools maps Blender frame 1 to VMD frame 0 (export subtracts 1 and drops frame 0, import adds 1),
# so clip frame f is keyed at f + FRAME0.  Keyed from 0, a VMD lost its first frame and played a
# frame early; the round trip hid it everywhere but frame 0, 16 cm off on the fast battle clips.
FRAME0 = 1
# Unity (left-handed, Y up, character faces +Z) -> Blender (Z up, character faces -Y)
K = Matrix(((-1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))

# MMD bone (name_j) -> Biped role; roles resolved on the game rig by resolve_roe_slots().
ROLE_TO_MMD = {
    "lower_body_bone": "下半身", "upper_body_bone": "上半身", "upper_body2_bone": "上半身2",
    "upper_body3_bone": "上半身3", "neck_bone": "首", "head_bone": "頭",
}
for _side, _s in (("left", "左"), ("right", "右")):
    ROLE_TO_MMD.update({
        "%s_shoulder_bone" % _side: _s + "肩", "%s_upper_arm_bone" % _side: _s + "腕",
        "%s_lower_arm_bone" % _side: _s + "ひじ", "%s_hand_bone" % _side: _s + "手首",
        "%s_thigh_bone" % _side: _s + "足", "%s_calf_bone" % _side: _s + "ひざ",
        "%s_foot_bone" % _side: _s + "足首", "%s_toe_bone" % _side: _s + "足先EX",
        "%s_eye_bone" % _side: _s + "目", "%s_chest_bone" % _side: _s + "胸",
    })
    for _f, _jp, _segs in (("thumb", "親指", "012"), ("index", "人指", "123"), ("middle", "中指", "123"),
                           ("ring", "薬指", "123"), ("pinky", "小指", "123")):
        for _seg in _segs:
            ROLE_TO_MMD["%s_%s_%s" % (_side, _f, _seg)] = _s + _jp + "０１２３"[int(_seg)]


# --------------------------------------------------------------------------- game skeleton
def quat_u(q):
    return Quaternion((q[3], q[0], q[1], q[2]))


def trs(pos, rot, scale):
    m = quat_u(rot).to_matrix().to_4x4()
    for i in range(3):
        for j in range(3):
            m[i][j] *= scale[j]
    m.translation = Vector(pos)
    return m


class Game:
    """Unity world matrices of the clip's skeleton at rest and per frame, mapped into Blender."""

    def __init__(self, data):
        self.bones = data["bones"]
        self.frames = data["frames"]
        self.fps = data["fps"]
        self.index = {b["name"]: i for i, b in enumerate(self.bones)}

    def world(self, frame=None):
        local = self.frames[frame] if frame is not None else {}
        out = []
        for i, b in enumerate(self.bones):
            cur = local.get(str(i), {})
            m = trs(cur.get("pos", b["pos"]), cur.get("rot", b["rot"]), cur.get("scale", b["scale"]))
            out.append(m if b["parent"] < 0 else out[b["parent"]] @ m)
        return [K @ m @ K for m in out]          # K is its own inverse

    def rest_world(self):
        """The pose our FBX/PMX were built in: a skinned bone's bind pose, else its Transform rest.
        bone world at bind = renderer world * inverse(bindpose) (Unity), then mapped like world()."""
        rest = self.world()
        out = []
        for i, b in enumerate(self.bones):
            bind = b.get("bind")
            if bind is None:
                out.append(rest[i])
                continue
            renderer_unity = K @ rest[bind["renderer"]] @ K
            bindpose = Matrix(bind["inv"])
            out.append(K @ (renderer_unity @ bindpose.inverted()) @ K)
        return out


class _Bone:
    def __init__(self, name):
        self.name, self.parent = name, None


class _Bones(list):
    def get(self, name):
        return next((b for b in self if b.name == name), None)


def game_slots(game):
    """resolve_roe_slots() from the exporter, run on the decoded skeleton."""
    from export_character_model_blender import resolve_roe_slots
    bones = _Bones(_Bone(b["name"]) for b in game.bones)
    for b, src in zip(bones, game.bones):
        if src["parent"] >= 0:
            b.parent = bones[src["parent"]]

    class Arm:
        class data:
            pass
    Arm.data.bones = bones
    slots, _missing = resolve_roe_slots(Arm)
    return slots


# --------------------------------------------------------------------------- helpers
def fit_scale_offset(pairs):
    """Least squares s, offset with  b ~= s * a + offset  for point pairs (a, b)."""
    n = len(pairs)
    ca = sum((a for a, _ in pairs), Vector()) / n
    cb = sum((b for _, b in pairs), Vector()) / n
    num = sum((a - ca).dot(b - cb) for a, b in pairs)
    den = sum((a - ca).length_squared for a, _ in pairs)
    s = num / den
    off = cb - s * ca
    resid = max((s * a + off - b).length for a, b in pairs)
    return s, off, resid


def swing_twist(q, axis):
    """q = swing @ twist with twist about `axis` (unit, same frame as q)."""
    p = Vector((q.x, q.y, q.z)).project(axis)
    twist = Quaternion((q.w, p.x, p.y, p.z))
    if twist.magnitude < 1e-9:
        twist = Quaternion()
    twist.normalize()
    swing = q @ twist.inverted()
    return swing, twist


def rot_of(m):
    return m.to_quaternion()


def topo(arm):
    out, seen = [], set()

    def add(b):
        if b.name in seen:
            return
        if b.parent:
            add(b.parent)
        seen.add(b.name)
        out.append(b)
    for b in arm.data.bones:
        add(b)
    return out


# --------------------------------------------------------------------------- PMX side
def load_pmx(path):
    addon_utils.enable("mmd_tools", default_set=False)
    bpy.ops.mmd_tools.import_model(filepath=path, scale=SCALE,
                                   types={"MESH", "ARMATURE", "PHYSICS", "MORPHS", "DISPLAY"})
    root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
    from mmd_tools.core.model import Model
    return root, Model(root).armature()


def driven_bones(root, arm):
    """Bones the PMX animates itself: additional transform (grants) or dynamic rigid bodies."""
    out = set()
    for pb in arm.pose.bones:
        mb = pb.mmd_bone
        if mb.has_additional_rotation or mb.has_additional_location:
            out.add(pb.name)
    for o in root.children_recursive:
        if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.type in ("1", "2"):
            name = o.mmd_rigid.bone
            if name in arm.pose.bones:
                out.add(name)
    return out


def build_map(arm, game):
    """PMX pose bone name -> game bone index."""
    slots = game_slots(game)
    by_j = {pb.mmd_bone.name_j: pb.name for pb in arm.pose.bones}
    mapping = {}
    for role, mmd in ROLE_TO_MMD.items():
        gname = slots.get(role)
        if gname and mmd in by_j and gname in game.index:
            mapping[by_j[mmd]] = game.index[gname]
    used = set(mapping.values())
    for pb in arm.pose.bones:         # bones the converter kept by name (hair, ribbons, face, helpers)
        # a name shortened for the VMD (pmx_bone_names.py: Bip001 eyebrow_LC -> eyebrow_LC) keeps the
        # game's name as the bone's English name
        gi = next((game.index[k] for k in (pb.mmd_bone.name_j, pb.name, pb.mmd_bone.name_e) if k in game.index),
                  None)
        if pb.name not in mapping and gi is not None and gi not in used:
            mapping[pb.name] = gi
    return mapping


def granted(arm, name, dq):
    """The rotation MMD adds to a bone with an additional (grant) rotation: the source's own rotation
    relative to its parent, times the influence.  D bones (足首D copies 足首 x1), 肩C (-1 x 肩P) and
    the twist splitters (腕捩1-3) follow their source, not their parent; children of 足首D such as
    足先EX are keyed against that.  World deltas compose like local rotations here because a grant
    source and its target share their rest frames in these PMX."""
    mb = arm.pose.bones[name].mmd_bone
    src = mb.additional_transform_bone
    if not mb.has_additional_rotation or src not in dq or arm.data.bones[src].parent is None:
        return Quaternion()
    rel = dq[arm.data.bones[src].parent.name].inverted() @ dq[src]
    inf = mb.additional_transform_influence
    if inf < 0:
        rel, inf = rel.inverted(), -inf
    return Quaternion().slerp(rel, min(inf, 1.0)) if inf < 0.999 else rel


def follow(w, rest_w, gi, point, s, off):
    """Where `point` (PMX armature space, rest) goes if it rides rigidly on game bone `gi`."""
    local = rest_w[gi].inverted() @ ((point - off) / s)
    return s * (w[gi] @ local) + off


def retarget(arm, game, mapping, skip, twist_pairs, center, frames, roles, pinned=()):
    """Key the PMX armature; returns per-frame stats."""
    rest_w = game.rest_world()
    bones = topo(arm)
    rrest = {b.name: b.matrix_local.to_quaternion() for b in bones}
    # direction-based swing S per mapped bone
    S = {}
    head = {b.name: b.head_local for b in bones}
    tail = {b.name: b.tail_local for b in bones}
    for b in bones:
        if b.name not in mapping:
            continue
        gi = mapping[b.name]
        best = None
        for c in b.children_recursive:
            # only a child sitting on the tail says where the bone points (arms, legs, spine); a
            # prop bone's tail is arbitrary, and a bogus 3.6 deg on the 1.36 m fan carrier threw the
            # fan 15 cm when the tolerance was a quarter of the bone length
            if c.name in mapping and (c.head_local - tail[b.name]).length < max(0.002, 0.02 * b.length):
                d = (c.head_local - tail[b.name]).length
                if best is None or d < best[0]:
                    best = (d, c.name)
        if best is None:
            continue
        dp = (tail[b.name] - head[b.name]).normalized()
        dg = (rest_w[mapping[best[1]]].translation - rest_w[gi].translation)
        if dg.length < 1e-6:
            continue
        S[b.name] = dg.normalized().rotation_difference(dp)
    for b in bones:                     # leaves inherit the parent's stance
        if b.name in mapping and b.name not in S:
            p = b.parent
            while p is not None and p.name not in S:
                p = p.parent
            S[b.name] = S[p.name] if p is not None else Quaternion()

    # positions: game rest joints vs PMX rest heads on bones the stance does not touch
    pairs = []
    for b in bones:
        j = b.name
        # 下半身 is left out: the converter moves its head up to the spine
        if j in mapping and S[j].angle < math.radians(2) and arm.pose.bones[j].mmd_bone.name_j in (
                "上半身", "上半身3", "首", "頭", "左足", "右足", "左ひざ", "右ひざ",
                "左足首", "右足首"):
            pairs.append((rest_w[mapping[j]].translation, head[j]))
    s, off, resid = fit_scale_offset(pairs)
    print("position fit: %d joints, scale %.4f, worst residual %.1f mm" % (len(pairs), s, resid * 1000))
    for b in bones:
        if b.name in mapping and arm.pose.bones[b.name].mmd_bone.name_j in (
                "下半身", "上半身", "上半身2", "上半身3", "首", "頭", "左足", "右足", "左ひざ", "右ひざ",
                "左足首", "右足首", "左腕", "右腕", "左手首", "右手首"):
            g = s * rest_w[mapping[b.name]].translation + off
            print("   %-6s %-22s game %s  pmx %s  diff %.1f mm" % (
                arm.pose.bones[b.name].mmd_bone.name_j, game.bones[mapping[b.name]]["name"],
                tuple(round(v, 3) for v in g), tuple(round(v, 3) for v in head[b.name]),
                (g - head[b.name]).length * 1000))
    stance = sorted((math.degrees(q.angle), arm.pose.bones[n].mmd_bone.name_j) for n, q in S.items())
    print("stance swings > 3 deg:", [(round(a, 1), n) for a, n in stance if a > 3][-12:])

    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    pelvis_rest = rest_w[mapping[center[1]]].translation if center else None
    # bones whose head the clip moves (props, face, ribbon roots): keyed with a location too
    role_bones = set(roles) - set(pinned)
    move = set(pinned)
    worlds = {f: game.world(f) for f in frames}
    for name, gi in mapping.items():
        if name in skip or name in role_bones:
            continue
        seq = [game.frames[f].get(str(gi), {}).get("pos") for f in frames]
        rest_pos = game.bones[gi]["pos"]
        # how far the clip takes the bone off its parent's bind frame: a00's semen bones (liquid01x) sit 1 m
        # away, hidden, in the prefab and all through the clip, while the PMX has them where the mesh was
        # bound, so the prefab-rest test above them sees no motion
        gp = game.bones[gi]["parent"]
        drift = 0.0
        if gp >= 0:
            bound = rest_w[gp].inverted() @ rest_w[gi].translation
            drift = max((worlds[f][gi].translation - worlds[f][gp] @ bound).length for f in frames)
        if any(p is not None and max(abs(p[k] - rest_pos[k]) for k in range(3)) > 0.0005 for p in seq) \
                or s * drift > 0.0005:
            move.add(name)
        # the converter parks some children of the Biped root on 全ての親 (a00's genitals Bip000 Xtra01/02,
        # props, cape bases): nothing above them moves, so rotations alone leave them at the origin
        elif not any(p.name in mapping for p in arm.data.bones[name].parent_recursive):
            move.add(name)
        # rest disagreement (an older PMX had the whole fan 39 mm off the game's): the copied
        # rotations would swing it on a different lever, so its head is placed every frame too
        elif (s * rest_w[gi].translation + off - head[name]).length > 0.001:
            if S[name].angle < math.radians(2):
                move.add(name)
            else:
                print("   rest differs but the stance swings it (%.1f deg), not pinned: %s"
                      % (math.degrees(S[name].angle), arm.pose.bones[name].mmd_bone.name_j))
    rl = {b.name: b.matrix_local for b in bones}
    if os.environ.get("ROE_VMD_CHAIN"):
        b = arm.data.bones.get(os.environ["ROE_VMD_CHAIN"])
        chain = []
        while b is not None:
            chain.append(b)
            b = b.parent
        for b in reversed(chain):
            mb = arm.pose.bones[b.name].mmd_bone
            print("   chain %-18s mapped %-5s skip %-5s move %-5s grant %s from %r x%.2f S %.1f"
                  % (b.name, b.name in mapping, b.name in skip, b.name in move, mb.has_additional_rotation or
                     mb.has_additional_location, mb.additional_transform_bone, mb.additional_transform_influence,
                     math.degrees(S[b.name].angle) if b.name in S else -1))
    print("bones keyed with a location:", len(move),
          "of them not movable in the PMX:", sorted(n for n in move if all(arm.pose.bones[n].lock_location)))
    for f in frames:
        w = worlds[f]
        dq = {}
        for b in bones:
            parent = dq[b.parent.name] if b.parent else Quaternion()
            if b.name in mapping and b.name not in skip:
                gi = mapping[b.name]
                # the product first: a constant scale (decoration bones carry -1, the fan carrier 2.19)
                # cancels; quaternions of mirrored matrices taken one by one do not
                d = (w[gi] @ rest_w[gi].inverted()).to_quaternion() @ S[b.name].inverted()
            else:
                d = parent
            dq[b.name] = d
        # MMD twist conventions
        for swing_bone, twist_bone, kind in twist_pairs:
            if kind == "upper":          # 腕 keeps the swing, 腕捩 the twist of the upper arm
                parent = dq[arm.data.bones[swing_bone].parent.name]
                local = parent.inverted() @ dq[swing_bone]
                axis = (tail[swing_bone] - head[swing_bone]).normalized()
                sw, _tw = swing_twist(local, axis)
                full = dq[swing_bone]
                dq[swing_bone] = parent @ sw
                dq[twist_bone] = full
            else:                        # 手捩 takes the hand's twist about the forearm
                elbow, hand = swing_bone, kind
                local = dq[elbow].inverted() @ dq[hand]
                axis = (tail[twist_bone] - head[twist_bone]).normalized()
                _sw, tw = swing_twist(local, axis)
                dq[twist_bone] = dq[elbow] @ tw
        # children of re-split bones that follow their parent must follow the new value
        own = {t[1] for t in twist_pairs}
        for b in bones:
            if (b.name not in mapping or b.name in skip) and b.parent and b.name not in own:
                dq[b.name] = dq[b.parent.name] @ granted(arm, b.name, dq)
        posed = {}
        for b in bones:
            pb = arm.pose.bones[b.name]
            parent = dq[b.parent.name] if b.parent else Quaternion()
            basis = rrest[b.name].inverted() @ parent.inverted() @ dq[b.name] @ rrest[b.name]
            # where the bone's frame sits before its own basis (armature space)
            x = posed[b.parent.name] @ rl[b.parent.name].inverted() @ rl[b.name] if b.parent else rl[b.name].copy()
            loc = Vector()
            if center and b.name == center[0]:
                # センター moves the body so that 上半身's head sits on the game's spine joint: the
                # converter moved 下半身's head up to the spine, so the pelvis is the wrong pivot
                pivot = center[1]
                want = s * w[mapping[pivot]].translation + off
                loc = rrest[b.name].inverted() @ (want - head[pivot])
            elif b.name in move:
                loc = x.inverted() @ follow(w, rest_w, mapping[b.name], head[b.name], s, off)
            posed[b.name] = x @ Matrix.Translation(loc) @ basis.to_matrix().to_4x4()
            if b.name in skip:
                continue
            pb.rotation_quaternion = basis
            pb.keyframe_insert("rotation_quaternion", frame=f + FRAME0)
            if b.name in move or (center and b.name == center[0]):
                pb.location = loc
                pb.keyframe_insert("location", frame=f + FRAME0)
    return s, off, move, S


def ik_off(arm, frame=FRAME0):
    names = []
    for pb in arm.pose.bones:
        if "ＩＫ" in pb.mmd_bone.name_j:
            pb.mmd_ik_toggle = False
            pb.keyframe_insert("mmd_ik_toggle", frame=frame)
            names.append(pb.mmd_bone.name_j)
    return names


def vmd_add_morph_keys(path, keys):
    """Append morph keys [(name, VMD frame, weight)] to a VMD's morph section (mmd_tools writes the
    bones; the morphs keyed here are ones the motion needs but the PMX animates no other way, such as
    pmx_add_scale_morph.py's 扇子縮小).  Names are 15 bytes of Shift-JIS, like everything in a VMD."""
    import struct
    data = bytearray(open(path, "rb").read())
    pos = 50
    n_bones, = struct.unpack_from("<I", data, pos)
    pos += 4 + n_bones * 111
    n_morphs, = struct.unpack_from("<I", data, pos)
    records = b"".join(name.encode("shift_jis")[:15].ljust(15, b"\0") + struct.pack("<If", frame, weight)
                       for name, frame, weight in keys)
    data[pos:pos + 4] = struct.pack("<I", n_morphs + len(keys))
    at = pos + 4 + n_morphs * 23
    data[at:at] = records
    open(path, "wb").write(bytes(data))


def verify_round_trip(root, arm, game, mapping, roles, s, off, vmd, frames, move=(), S=None):
    """Re-import the VMD through mmd_tools onto the bare PMX and measure, frame by frame, how far
    each mapped joint lands from the game's own joint (same scale/offset as the rest fit)."""
    arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.location, pb.rotation_quaternion = Vector(), Quaternion()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=SCALE, margin=0, update_scene_settings=False)
    scene = bpy.context.scene
    worst, worst_rot = {}, {}
    rest_w = game.rest_world()
    heads = {b.name: b.head_local for b in arm.data.bones}
    for f in frames[::8] + [frames[-1]]:
        scene.frame_set(f + FRAME0)
        w = game.world(f)
        for name, gi in mapping.items():
            # the PMX bone's own head carried by the game bone's motion (= the game joint when the
            # rests agree, which they do for the body)
            want = follow(w, rest_w, gi, heads[name], s, off) if name in move else s * w[gi].translation + off
            got = arm.matrix_world @ arm.pose.bones[name].head
            err = (got - want).length
            if err > worst.get(name, (0, 0))[0]:
                worst[name] = (err, f)
            # a spin about the bone's own axis moves no joint (the g04 fan turned edge-on): compare
            # the world rotation change too
            # 腕 hands its twist to 腕捩 on purpose, so only its swing would match
            if S is not None and name in S and arm.pose.bones[name].mmd_bone.name_j not in ("左腕", "右腕"):
                pb = arm.pose.bones[name]
                got_q = (arm.matrix_world @ pb.matrix).to_quaternion() @ \
                    (arm.matrix_world @ pb.bone.matrix_local).to_quaternion().inverted()
                want_q = (w[gi] @ rest_w[gi].inverted()).to_quaternion() @ S[name].inverted()
                ang = math.degrees(got_q.rotation_difference(want_q).angle)
                ang = min(ang, 360.0 - ang)          # q and -q are the same rotation
                if ang > worst_rot.get(name, (0, 0))[0]:
                    worst_rot[name] = (ang, f)
    body = sorted(((e, f, arm.pose.bones[n].mmd_bone.name_j) for n, (e, f) in worst.items() if n in roles), reverse=True)
    rest = sorted(((e, f, arm.pose.bones[n].mmd_bone.name_j) for n, (e, f) in worst.items() if n not in roles), reverse=True)
    if os.environ.get("ROE_VMD_TRACE"):
        by_j = {pb.mmd_bone.name_j: pb.name for pb in arm.pose.bones}
        for f in (0, 16, 32, 48, 64):
            scene.frame_set(f + FRAME0)
            w = game.world(f)
            row = []
            for j in os.environ["ROE_VMD_TRACE"].split(","):
                n = by_j.get(j)
                if n in mapping:
                    want = s * w[mapping[n]].translation + off
                    row.append("%s %.0f" % (j, ((arm.matrix_world @ arm.pose.bones[n].head) - want).length * 1000))
                elif n:
                    row.append("%s (unmapped, parent %s)" % (j, arm.pose.bones[n].parent.mmd_bone.name_j))
            print("trace f%d: %s" % (f, ", ".join(row)))
    if os.environ.get("ROE_VMD_OFFSET"):
        role_names = [n for n in mapping if n in roles]
        for f in (0, 8, 16, 24):
            if f >= len(frames):
                continue
            scene.frame_set(f + FRAME0)
            got = {n: arm.matrix_world @ arm.pose.bones[n].head for n in role_names}
            row = []
            for k in (f - 1, f, f + 1):
                if 0 <= k < len(frames):
                    wk = game.world(k)
                    err = sum((got[n] - (s * wk[mapping[n]].translation + off)).length for n in role_names) / len(role_names)
                    row.append("data f%d: %.1f mm" % (k, err * 1000))
            print("offset probe scene f%d: %s" % (f, ", ".join(row)))
    rot = sorted(((a, f, arm.pose.bones[n].mmd_bone.name_j) for n, (a, f) in worst_rot.items()), reverse=True)
    print("round trip, rotations: worst %s" % [("%s %.1f deg @%d" % (n, a, f)) for a, f, n in rot[:10]])
    print("round trip, body joints: worst %s" % [("%s %.1f mm @%d" % (n, e * 1000, f)) for e, f, n in body[:8]])
    print("round trip, other joints: worst %s" % [("%s %.1f mm @%d" % (n, e * 1000, f)) for e, f, n in rest[:8]])
    return body, rest


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    clip_json, pmx, out_vmd = argv[:3]
    compare = argv[argv.index("--compare") + 1:argv.index("--compare") + 3] if "--compare" in argv else None
    # --morph NAME=VALUE (repeatable): hold a PMX morph at VALUE for the whole motion
    morph_keys = [(a.split("=")[0], 0, float(a.split("=")[1]))
                  for k, a in zip(argv, argv[1:]) if k == "--morph"]
    # --morphs FILE.json: {name: value} or {name: [value per clip frame]} (export_roe_motions.py writes it for
    # bone groups the clip scales; every frame is keyed so held stretches stay held under MMD's linear blend)
    if "--morphs" in argv:
        spec = json.load(open(argv[argv.index("--morphs") + 1], encoding="utf-8"))
        for name, value in spec.items():
            if isinstance(value, list):
                morph_keys += [(name, f, float(v)) for f, v in enumerate(value)]
            else:
                morph_keys.append((name, 0, float(value)))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    game = Game(json.load(open(clip_json, encoding="utf-8")))
    root, arm = load_pmx(pmx)
    by_j = {pb.mmd_bone.name_j: pb.name for pb in arm.pose.bones}
    mapping = build_map(arm, game)
    skip = driven_bones(root, arm)
    # A VMD names a bone in 15 bytes of Shift-JIS and MMD matches only those bytes, so bones whose
    # names collide once cut (the 8 'Bip001 eyebrow_*' -> 'Bip001 eyebrow_') would all receive one
    # bone's keys.  They get none: still is better than wrong.
    cut = {}
    for pb in arm.pose.bones:
        cut.setdefault(pb.mmd_bone.name_j.encode("shift_jis", "replace")[:15], []).append(pb.name)
    clash = {n for names in cut.values() if len(names) > 1 for n in names}
    dropped = sorted(arm.pose.bones[n].mmd_bone.name_j for n in clash if n in mapping and n not in skip)
    skip |= clash
    print("VMD name clashes (15-byte cut): %d bones left unkeyed: %s" % (len(dropped), dropped))
    for n in list(skip):                 # a driven bone with a mapped twin is still driven
        mapping.pop(n, None)
    twist = []
    for s in "左右":
        if all(x in by_j for x in (s + "腕", s + "腕捩")):
            twist.append((by_j[s + "腕"], by_j[s + "腕捩"], "upper"))
        if all(x in by_j for x in (s + "ひじ", s + "手捩", s + "手首")):
            twist.append((by_j[s + "ひじ"], by_j[s + "手捩"], by_j[s + "手首"]))
    center = (by_j["センター"], by_j["上半身"]) if "センター" in by_j and "上半身" in by_j else None
    # The PMX hangs the shoulders (肩P) on 上半身2 while the game hangs the clavicles on the neck,
    # above Spine2, so whenever the chest bends the copied rotations leave the shoulders 4-12 cm
    # behind.  肩 is a movable bone in these PMX, so it gets a location key that puts its head on the
    # game's clavicle joint; everything from the spine up keeps the game's own rotations.
    pinned = {by_j[n] for n in ("左肩", "右肩") if by_j.get(n) in mapping and not all(arm.pose.bones[by_j[n]].lock_location)}
    print("mapped %d PMX bones (%d by role), %d driven by the PMX itself"
          % (len(mapping), sum(1 for r, m in ROLE_TO_MMD.items() if m in by_j and by_j[m] in mapping), len(skip)))
    frames = list(range(len(game.frames)))
    roles = {by_j[m] for m in ROLE_TO_MMD.values() if m in by_j and by_j[m] in mapping}
    s, off, move, S = retarget(arm, game, mapping, skip, twist, center, frames, roles, pinned)
    print("IK off:", ik_off(arm))
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = FRAME0, frames[-1] + FRAME0
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    os.makedirs(os.path.dirname(os.path.abspath(out_vmd)), exist_ok=True)
    bpy.ops.mmd_tools.export_vmd(filepath=out_vmd, scale=1.0 / SCALE)
    if morph_keys:
        vmd_add_morph_keys(out_vmd, morph_keys)
        names = sorted({k[0] for k in morph_keys})
        print("morph keys: %s" % ", ".join("%s x%d (%.3f..%.3f)" % (
            n, sum(1 for k in morph_keys if k[0] == n), min(k[2] for k in morph_keys if k[0] == n),
            max(k[2] for k in morph_keys if k[0] == n)) for n in names))
    print("VMD written: %s (%d frames, %.2f s)" % (out_vmd, len(frames), (len(frames) - 1) / game.fps))
    verify_round_trip(root, arm, game, mapping, roles, s, off, out_vmd, frames, move, S)
    if compare:
        from roe_vmd_compare import render_compare
        render_compare(game, pmx, out_vmd, compare[0], compare[1])


if __name__ == "__main__":
    main()
