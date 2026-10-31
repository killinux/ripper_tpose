# -*- coding: utf-8 -*-
"""AION2 face expressions: the game's ARKit FACS pose asset -> one shape key per pose (Blender, before the face
bones are merged into the head by export_pmx_blender.py).

The player and NPC heads share one face rig: ``Face_Root``'s ``b_*`` joints under ``Bip001-Head`` (brows, lids,
cheeks, lips, ``b_C_TeethLower_0``).  The game drives it with a PoseAsset of the 52 ARKit shapes
(``GF_Head_006_FACS_PA``: browInnerUp ... mouthStretchRight, tongueOut, sub_jawOpen).  Each pose is ADDITIVE in
local space and, in UE 5.3, stored sparsely: ``Tracks[t]`` names the bone, ``TrackPoseInfluenceIndices[t]`` lists
(PoseIndex, BoneTransformIndex) pairs into ``Poses[PoseIndex].LocalSpacePose``.  UE applies an additive local pose
as R = dR * R_ref, T = T_ref + dT, S = S_ref * (1 + dS) on each bone's own reference pose, so the deltas fit any
head built on the rig - NPC faces put the joints elsewhere, in the same frames.

The reference frames are read from the head part's PSK.  UE Viewer writes that skeleton mirrored in Y: position
(x, -y, z) and rotation conj(mirror(q)), mirror(x, y, z, w) = (x, -y, z, -w) - checked against the pose asset's own
reference pose on the body bones.  Rest and posed component-space matrices give each bone's world delta, which is
mirrored into Blender (the PSK import keeps the PSK's axes) and applied to the pose bones; the deformed meshes are
read from the depsgraph and every mesh the pose moved gets a shape key of the pose's name.

The pose asset comes out of the game as CUE4Parse JSON (face_data.py); nothing of it is in the repo.
"""
import json
import struct

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

MIRROR = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
FACE_ROOT = "Face_Root"


def read_psk_skeleton(path):
    """[(name, parent index, (qx, qy, qz, qw), (px, py, pz))] from a PSK's REFSKELT chunk."""
    data = open(path, "rb").read()
    off = 0
    while off + 32 <= len(data):
        cid, _flags, size, count = struct.unpack_from("<20sIII", data, off)
        off += 32
        if cid.split(b"\0")[0] == b"REFSKELT":
            out = []
            for i in range(count):
                b = off + i * size
                name = data[b:b + 64].split(b"\0")[0].decode("utf-8", "replace")
                parent = struct.unpack_from("<i", data, b + 72)[0]
                q = struct.unpack_from("<4f", data, b + 76)
                p = struct.unpack_from("<3f", data, b + 92)
                out.append((name, parent, q, p))
            return out
        off += size * count
    raise RuntimeError("no REFSKELT chunk in %s" % path)


def ue_local_from_psk(q, p):
    """UE Viewer's PSK joint -> the UE local transform (T, quaternion)."""
    qx, qy, qz, qw = q
    return Vector((p[0], -p[1], p[2])), Quaternion((-qw, -qx, qy, -qz))     # mathutils order: w, x, y, z


def load_pose_asset(path):
    """CUE4Parse JSON of a PoseAsset -> (pose names, {pose: {track: (dT, dq, dS)}}, additive)."""
    doc = json.load(open(path, encoding="utf-8-sig"))
    props = next(o for o in doc if o.get("Type") == "PoseAsset")["Properties"]
    pc = props["PoseContainer"]
    names = [p["DisplayName"] for p in pc["PoseNames"]]
    poses = {n: {} for n in names}
    for track, inf in zip(pc["Tracks"], pc["TrackPoseInfluenceIndices"]):
        for e in inf.get("Influences", []):
            pi, bi = e["PoseIndex"], e["BoneTransformIndex"]
            tr = pc["Poses"][pi]["LocalSpacePose"][bi]
            t, r, s = tr["Translation"], tr["Rotation"], tr["Scale3D"]
            poses[names[pi]][track] = (Vector((t["X"], t["Y"], t["Z"])),
                                       Quaternion((r["W"], r["X"], r["Y"], r["Z"])),
                                       Vector((s["X"], s["Y"], s["Z"])))
    return names, poses, bool(props.get("bAdditivePose", True))


def _matrix(t, q, s=(1.0, 1.0, 1.0)):
    return Matrix.Translation(t) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))


def component_space(skeleton, locals_):
    out = []
    for i, (_name, parent, _q, _p) in enumerate(skeleton):
        m = _matrix(*locals_[i])
        out.append(out[parent] @ m if 0 <= parent < i else m)
    return out


def _coords(obj, depsgraph):
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    return co.reshape(-1, 3)


def build_shape_keys(arm, meshes, psk_path, pose_asset_path, min_move=1e-4, log=print):
    """One shape key per pose on every mesh the pose moves.  Returns a report dict."""
    skeleton = read_psk_skeleton(psk_path)
    index = {name: i for i, (name, _p, _q, _t) in enumerate(skeleton)}
    names, poses, additive = load_pose_asset(pose_asset_path)
    if not additive:
        raise RuntimeError("%s is not an additive pose asset" % pose_asset_path)
    report = {"psk_bones": len(skeleton), "poses": len(names), "keys": {}, "empty_poses": [],
              "missing_tracks": sorted({t for p in poses.values() for t in p if t not in index})}
    rest_locals = [ue_local_from_psk(q, p) for _n, _par, q, p in skeleton]
    rest_locals = [(t, q, Vector((1.0, 1.0, 1.0))) for t, q in rest_locals]
    rest_cs = component_space(skeleton, rest_locals)

    # the mirrored PSK frames are world space and must land on the armature's rest joints: else the deltas go
    # the wrong way
    bones = arm.data.bones
    errors = [((MIRROR @ rest_cs[i]).to_translation() - arm.matrix_world @ bones[n].head_local).length
              for n, i in index.items() if n in bones]
    report["frame_check_cm"] = round(max(errors), 4) if errors else None
    if not errors or max(errors) > 0.05:
        raise RuntimeError("the head PSK's skeleton does not match the armature (%.3f)" % max(errors or [1e9]))

    # only the meshes skinned to a bone some pose moves (or to one below it)
    moving = {t for p in poses.values() for t in p if t in bones}
    for b in bones:
        if b.parent is not None and b.parent.name in moving:
            moving.add(b.name)
    for b in list(bones):                              # descendants of descendants
        p = b.parent
        while p is not None and b.name not in moving:
            if p.name in moving:
                moving.add(b.name)
            p = p.parent
    meshes = [m for m in meshes if any(vg.name in moving for vg in m.vertex_groups)]
    report["meshes"] = [m.name for m in meshes]

    rest_inv = [m.inverted() for m in rest_cs]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    pose_bones = arm.pose.bones
    for pb in pose_bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    base = {m.name: _coords(m, depsgraph) for m in meshes}
    order = []                                         # parents before children
    stack = [b for b in bones if b.parent is None]
    while stack:
        b = stack.pop()
        order.append(b)
        stack.extend(b.children)
    a_mat = {b.name: arm.matrix_world @ b.matrix_local for b in bones}
    for name in names:
        delta = poses[name]
        if not delta:
            report["empty_poses"].append(name)
            continue
        locals_ = []
        for i, (bone_name, _par, _q, _p) in enumerate(skeleton):
            t, q, s = rest_locals[i]
            d = delta.get(bone_name)
            if d is not None:
                dt, dq, ds = d
                t, q = t + dt, dq @ q
                s = Vector((s[0] * (1 + ds[0]), s[1] * (1 + ds[1]), s[2] * (1 + ds[2])))
            locals_.append((t, q, s))
        posed = component_space(skeleton, locals_)
        world = {}                                     # Blender world delta per armature bone
        for b in order:
            i = index.get(b.name)
            if i is not None:
                world[b.name] = MIRROR @ (posed[i] @ rest_inv[i]) @ MIRROR
            else:
                world[b.name] = world[b.parent.name] if b.parent else Matrix.Identity(4)
            a = a_mat[b.name]
            dp = world[b.parent.name] if b.parent else Matrix.Identity(4)
            pose_bones[b.name].matrix_basis = a.inverted() @ dp.inverted() @ world[b.name] @ a
        bpy.context.view_layer.update()
        biggest = 0.0
        for m in meshes:
            co = _coords(m, depsgraph)
            move = np.abs(co - base[m.name]).max(axis=1)
            biggest = max(biggest, float(move.max()))
            moved = move > min_move
            if not moved.any():
                continue
            if m.data.shape_keys is None:
                m.shape_key_add(name="Basis", from_mix=False)
            key = m.data.shape_keys.key_blocks.get(name) or m.shape_key_add(name=name, from_mix=False)
            rest = np.empty(len(m.data.vertices) * 3)
            m.data.shape_keys.key_blocks[0].data.foreach_get("co", rest)
            rest = rest.reshape(-1, 3)
            out = rest.copy()
            out[moved] += co[moved] - base[m.name][moved]
            key.data.foreach_set("co", out.ravel())
            key.value = 0.0
            report["keys"].setdefault(m.name, []).append(name)
        report.setdefault("max_move", {})[name] = round(biggest, 3)
    for pb in pose_bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    log("[aion2 facs] %d poses -> keys on %s (frames checked to %.4f cm)"
        % (len(names) - len(report["empty_poses"]), ", ".join("%s %d" % (k, len(v)) for k, v in report["keys"].items()),
           report["frame_check_cm"]))
    return report
