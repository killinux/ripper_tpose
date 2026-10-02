# -*- coding: utf-8 -*-
"""FF7 Rebirth: one character's face data -> the face-data JSON that Convert_to_MMD5's 表情 tab
(FF7 face-bone source) and ff7_face_morphs read.

  python ff7rb_face_data.py --out E:/game_export/FF7Rebirth/_meta/face/PC0002_Tifa.json
         [--motion PC0002_Tifa] [--lipmap Tifa]
         [--poses-from E:/game_export/FF7Remake/_meta/face/PC0002_Tifa.json]

How Rebirth does faces (see docs/ff7rebirth-face.md): ~103 face bones under C_FaceBase_a; the
character Anim Blueprint plays face poses in a "FacialSlot" (AnimNode_EndFacialPrimary) and lip sync
on top (AnimNode_EndFacialSecondary: HSFLipMap visemes driven by HSFLipSyncDataPack keyframes).

What is read here (CUE4Parse CLI with the Rebirth .usmap; read-only on the game):
  * Motion/Player/<motion>/Facial00/F_* - the single-frame face poses.  CUE4Parse 1.2.2 cannot
    deserialize Rebirth's AnimSequence, so the packages are exported raw and decoded here: the UE4.26
    IoStore package's one export holds the TrackToSkeletonMapTable property and an ACL 1.3 compressed
    clip.  A pose clip has two identical frames, so every track is default or constant, and ACL keeps
    constant values at full precision - no variable-bit-rate decoding is needed.  The few clips with
    animated tracks (Tifa: F_Angry02; Cloud's idle / limit faces) are skipped, or taken from
    --poses-from (the Remake face data of the same character, same rig).
  * the Skeleton the poses name (bone names, parents, reference pose), as JSON.
  * LipSync/LipMap/Player/<motion>/<lipmap>_{Default,Loud,Smile} - HSFLipMap: 7 visemes as per-bone
    Maya channels (translate = absolute position under C_FaceBase_a in cm, X left / Y up / Z
    forward; rotate in degrees) + DefaultShape (rest values).
  * Motion/Player/<motion>/Facial00/F_Eyelid_move01 - the BlendSpace that makes the lids follow the
    gaze: its sample positions are the gaze angles the lid poses belong to (Tifa: up 13, down 20,
    left / right 22 degrees).
Poses come out as ff7_face_data.py (Remake) writes them: per face bone the delta
D = FaceBase_rest * FaceBase_pose^-1 * Bone_pose * Bone_rest^-1, re-expressed in the face frame (X
forward, Y left, Z up, origin C_FaceBase_a, cm; UE's Y mirrored as Blender imports it).  Tifa's 23
decoded poses match the Remake ones within 0.4 mm (relative to F_Idle01).
The output is game data: keep it out of the repo.
"""
import argparse
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

CLI = "E:/tools/cue4parse_cli_ff7/cue4parse.exe"
STAGE = r"D:\ff7_mods\_stage\rebirth"           # hard links to the game containers, no ~mods (ff7rb_cli_export.py)
GAME = r"D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH"
USMAP_CANDIDATES = (r"D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap",
                    r"E:\game_export\FF7Rebirth\_meta\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap")
GAME_ENUM = "GAME_FinalFantasy7Rebirth"
VARIANTS = ("Default", "Loud", "Smile")
FACE_ROOT = "C_FaceBase_a"
ACL_CLIP_TAG = 0xAC10AC10                        # ACL 1.x compressed clip
MIRROR_Y = np.diag([1.0, -1.0, 1.0, 1.0])        # UE -> Blender (as the PSK / game-export importers do)


def run_cli(a, packages, out, fmt="json"):
    cmd = [a.cli, "-i", a.input, "-g", GAME_ENUM, "-m", a.usmap, "-y", "-f", fmt, "-o", out]
    for p in packages:
        cmd += ["-p", p]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("cue4parse exit %d: %s" % (r.returncode, (r.stdout + r.stderr)[-1500:]))


def load_export(path, type_name):
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    for exp in data if isinstance(data, list) else [data]:
        if exp.get("Type") == type_name:
            return exp
    raise ValueError("%s: no %s export" % (path, type_name))


# --- lip maps, lid gaze -----------------------------------------------------------------------------
def shape(entry):
    """HSFLipMapShape -> {bone: {channel: value}} (channel 'TranslateY', 'RotateX' ...)."""
    out = {}
    for b in entry.get("Attributes") or []:
        out[b["Key"]] = {d["Key"].split("::")[-1]: d["Value"] for d in b["Value"]["Data"]}
    return out


def lipmap(exp):
    p = exp["Properties"]
    return {"version": p.get("Version"), "DefaultShape": shape(p["DefaultShape"]),
            "shapes": {s["Key"]: shape(s["Value"]) for s in p["Shapes"]},
            "timing": {s["Key"]: {k: s["Value"].get(k) for k in ("AudioMin", "AudioMax", "AudioPower",
                                                                 "BlendIn", "BlendOut")}
                       for s in p["Shapes"]}}


def gaze(exp):
    """F_Eyelid_move01 samples -> {lid pose: (horizontal, vertical) gaze angle in degrees}."""
    out = {}
    for s in exp["Properties"].get("SampleData") or []:
        name = (s.get("Animation") or {}).get("ObjectName", "").split("'")[1:2]
        if name:
            v = s.get("SampleValue") or {}
            out[name[0]] = [v.get("X", 0.0), v.get("Y", 0.0)]
    return out


# --- face poses: raw IoStore package -> ACL 1.3 constant tracks ---------------------------------------
def zen_package(path):
    """UE4.26 IoStore package -> (name map, bytes of its first export)."""
    d = open(path, "rb").read()
    names_off, names_size, _h_off, _h_size, _imports, exports_off, _bundles, graph_off, graph_size = \
        struct.unpack_from("<9i", d, 24)
    names, p = [], names_off
    while p < names_off + names_size:
        head = struct.unpack_from(">H", d, p)[0]
        n, p = head & 0x7FFF, p + 2
        if head & 0x8000:
            names.append(d[p:p + 2 * n].decode("utf-16-le"))
            p += 2 * n
        else:
            names.append(d[p:p + n].decode("latin-1"))
            p += n
    size = struct.unpack_from("<Q", d, exports_off + 8)[0]
    start = graph_off + graph_size                   # the exports follow the package header
    return names, d[start:start + size]


def track_table(export, num_bones):
    """The TrackToSkeletonMapTable property (unversioned): int32 count, then per FTrackToSkeletonMap a
    uint16 header - 0x0380 + zero mask 01 for bone 0, 0x0300 + int32 otherwise."""
    for p in range(min(len(export) - 8, 256)):
        n = struct.unpack_from("<i", export, p)[0]
        if not 0 < n <= 4096:
            continue
        q, out = p + 4, []
        try:
            for _ in range(n):
                head = struct.unpack_from("<H", export, q)[0]
                if head == 0x0380 and export[q + 2] == 1:
                    out.append(0)
                    q += 3
                elif head == 0x0300:
                    out.append(struct.unpack_from("<i", export, q + 2)[0])
                    q += 6
                else:
                    break
        except (struct.error, IndexError):
            continue
        if len(out) == n and len(set(out)) == n and all(0 <= i < num_bones for i in out):
            return out
    raise ValueError("no TrackToSkeletonMapTable")


def acl_constant_clip(export):
    """The ACL 1.3 clip in an AnimSequence export -> per track ((x, y, z, w), translation, scale).
    Raises ValueError unless every track is default or constant (single-frame poses are)."""
    p = export.find(struct.pack("<I", ACL_CLIP_TAG))
    if p < 8:
        raise ValueError("no ACL clip")
    clip = export[p - 8:p - 8 + struct.unpack_from("<I", export, p - 8)[0]]
    version, algorithm = struct.unpack_from("<HB", clip, 12)
    if version != 5 or algorithm != 0:
        raise ValueError("ACL clip version %d / algorithm %d (decoder knows 1.3 = 5, uniform = 0)" % (version, algorithm))
    h = 16                                            # ClipHeader after the CompressedClip header
    (num_bones, _segments, rotation_format, _tf, _sf, _crr, _srr, has_scale, default_scale, _pad,
     num_samples, _rate) = struct.unpack_from("<HHBBBBBBBBIf", clip, h)
    # offsets: segment start indices, segment headers, default bitset, constant bitset, constant data, ranges
    offsets = struct.unpack_from("<6H", clip, h + 20)
    per_bone = 3 if has_scale else 2
    bits = num_bones * per_bone

    def bitset(off):
        words = struct.unpack_from("<%dI" % ((bits + 31) // 32), clip, h + off)
        return [bool(words[i // 32] >> (31 - i % 32) & 1) for i in range(bits)]

    default, constant = bitset(offsets[2]), bitset(offsets[3])
    animated = sum(1 for i in range(bits) if not (default[i] or constant[i]))
    if animated:
        raise ValueError("%d animated tracks" % animated)
    if num_samples > 2:
        raise ValueError("%d frames: not a pose" % num_samples)
    q = h + offsets[4]
    one = 1.0 if default_scale else 0.0
    tracks = []
    for b in range(num_bones):
        i = b * per_bone
        rot, move, scale = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (one, one, one)
        if not default[i]:
            if rotation_format == 0:                   # Quat_128
                rot, q = struct.unpack_from("<4f", clip, q), q + 16
            else:                                      # drop-W formats keep x, y, z with w >= 0
                (x, y, z), q = struct.unpack_from("<3f", clip, q), q + 12
                rot = (x, y, z, max(0.0, 1.0 - x * x - y * y - z * z) ** 0.5)
        if not default[i + 1]:
            move, q = struct.unpack_from("<3f", clip, q), q + 12
        if has_scale and not default[i + 2]:
            scale, q = struct.unpack_from("<3f", clip, q), q + 12
        tracks.append((rot, move, scale))
    return tracks


def transform(rot, move, scale):
    """FTransform -> 4x4 (column vectors: T * R * S)."""
    x, y, z, w = rot
    m = np.eye(4)
    m[:3, :3] = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]) * np.array(scale)
    m[:3, 3] = move
    return m


def skeleton_package(names):
    """'/Game/.../X_Skeleton' named in a pose package -> the CUE4Parse package path."""
    for n in names:
        if n.startswith("/Game/") and n.endswith("Skeleton"):
            return "End/Content/" + n[len("/Game/"):] + ".uasset"
    raise ValueError("the pose package names no Skeleton")


def face_poses(pose_files, skeleton):
    """Decoded F_* clips -> ({pose: {face bone: flat 4x4 in the face frame}}, skipped {pose: why},
    eye spacing)."""
    ref = skeleton["ReferenceSkeleton"]
    names = [b["Name"] for b in ref["FinalRefBoneInfo"]]
    parents = [b["ParentIndex"] for b in ref["FinalRefBoneInfo"]]
    local_rest = []
    for t in ref["FinalRefBonePose"]:
        r, m, s = t["Rotation"], t["Translation"], t["Scale3D"]
        local_rest.append(transform((r["X"], r["Y"], r["Z"], r["W"]), (m["X"], m["Y"], m["Z"]),
                                    (s["X"], s["Y"], s["Z"])))
    comp = []
    for i, p in enumerate(parents):                   # parents come before children in a ref skeleton
        comp.append(local_rest[i] if p < 0 else comp[p] @ local_rest[i])
    fb = names.index(FACE_ROOT)
    kids = [i for i, p in enumerate(parents) if p == fb]

    def head(name):
        return (MIRROR_Y @ comp[names.index(name)])[:3, 3]
    left = head("L_Eye") - head("R_Eye")
    spacing = float(np.linalg.norm(left))
    left /= spacing
    up = np.array([0.0, 0.0, 1.0])
    up -= left * up.dot(left)
    up /= np.linalg.norm(up)
    frame = np.eye(4)
    frame[:3, 0], frame[:3, 1], frame[:3, 2], frame[:3, 3] = np.cross(left, up), left, up, head(FACE_ROOT)
    to_face = np.linalg.inv(frame) @ MIRROR_Y @ comp[fb]
    from_face = np.linalg.inv(comp[fb]) @ MIRROR_Y @ frame

    poses, skipped = {}, {}
    for path in pose_files:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            export = zen_package(path)[1]
            tracks = acl_constant_clip(export)
            table = track_table(export, len(names))
            if len(table) != len(tracks):
                raise ValueError("%d tracks for %d table entries" % (len(tracks), len(table)))
        except ValueError as exc:
            skipped[name] = str(exc)
            continue
        posed = {table[t]: transform(*tracks[t]) for t in range(len(tracks))}
        poses[name] = {names[i]: [round(float(x), 7) for x in
                                  (to_face @ posed.get(i, local_rest[i]) @ np.linalg.inv(local_rest[i])
                                   @ from_face).ravel()]
                       for i in kids}
    return poses, skipped, spacing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--motion", default="PC0002_Tifa", help="Motion/Player/<motion>, LipSync/LipMap/Player/<motion>")
    ap.add_argument("--lipmap", default="Tifa", help="lip map name stem: <stem>_Default / _Loud / _Smile")
    ap.add_argument("--poses-from", default="",
                    help="Remake face-data JSON of the same character: fills the poses that can't be decoded")
    ap.add_argument("--input", default=STAGE if os.path.isdir(STAGE) else GAME)
    ap.add_argument("--usmap", default=next((p for p in USMAP_CANDIDATES if os.path.isfile(p)), USMAP_CANDIDATES[0]))
    ap.add_argument("--cli", default=CLI)
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    facial = "End/Content/Motion/Player/%s/Facial00" % a.motion
    lip_dir = "End/Content/LipSync/LipMap/Player/%s" % a.motion
    blend = facial + "/F_Eyelid_move01.uasset"
    work = tempfile.mkdtemp(prefix="ff7rb_face_")
    try:
        run_cli(a, [facial + "/F_*"], os.path.join(work, "raw"), fmt="raw")
        pose_files = sorted(glob.glob(os.path.join(work, "raw", facial, "F_*.uasset")))
        skeleton = ""
        for path in pose_files:
            try:
                skeleton = skeleton_package(zen_package(path)[0])
                break
            except ValueError:
                continue
        packages = ["%s/%s_%s.uasset" % (lip_dir, a.lipmap, v) for v in VARIANTS] + [blend]
        run_cli(a, packages + ([skeleton] if skeleton else []), work)
        maps = {}
        for v in VARIANTS:
            path = os.path.join(work, lip_dir, "%s_%s.json" % (a.lipmap, v))
            if os.path.isfile(path):
                maps[v] = lipmap(load_export(path, "HSFLipMap"))
        if "Default" not in maps:
            raise SystemExit("no %s_Default lip map under %s" % (a.lipmap, lip_dir))
        gaze_path = os.path.join(work, blend[:-len(".uasset")] + ".json")
        lid_gaze = gaze(load_export(gaze_path, "BlendSpace")) if os.path.isfile(gaze_path) else {}
        poses, skipped, spacing = {}, {}, None
        skel_path = os.path.join(work, skeleton[:-len(".uasset")] + ".json") if skeleton else ""
        if os.path.isfile(skel_path):
            poses, skipped, spacing = face_poses(pose_files, load_export(skel_path, "Skeleton"))
        # BlendSpaces (F_Brow, F_Emotion01, F_Eyelid_move01) hold no clip of their own
        skipped = {k: v for k, v in skipped.items() if v != "no ACL clip"}
    finally:
        if a.keep_temp:
            print("temp kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)

    sources = {"FF7 Rebirth": sorted(poses)}
    if a.poses_from:
        with open(a.poses_from, encoding="utf-8") as fh:
            remake = json.load(fh)
        filled = sorted(set(remake.get("poses", {})) - set(poses))
        for name in filled:
            poses[name] = remake["poses"][name]
        if filled:
            sources["FF7 Remake (%s)" % os.path.basename(a.poses_from)] = filled
        spacing = spacing or remake.get("eye_spacing")
    out = {"character": a.motion, "game": "FF7 Rebirth", "lipmap_name": a.lipmap + "_Default",
           "frame": "X forward, Y left, Z up, origin C_FaceBase_a, cm; pose deltas relative to the bind pose",
           "eye_spacing": spacing, "poses": poses, "poses_from": sources, "skipped_clips": skipped,
           "skeleton": skeleton,
           "lipmap": {"DefaultShape": maps["Default"]["DefaultShape"], "shapes": maps["Default"]["shapes"]},
           "lipmaps": maps, "lid_gaze": lid_gaze}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(tmp, a.out)
    print("FF7RB_FACE_DATA=" + json.dumps({"out": a.out, "poses": len(poses),
                                           "from": {k: len(v) for k, v in sources.items()},
                                           "skipped": skipped, "visemes": sorted(out["lipmap"]["shapes"]),
                                           "lipmaps": sorted(maps), "lid_gaze": lid_gaze,
                                           "eye_spacing": spacing}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
