# -*- coding: utf-8 -*-
"""FF7 Remake: one character's facial expressions out of the game -> face-data JSON for ff7_face_morphs.py.

  python ff7_face_data.py --out E:/game_export/FF7Remake/_meta/face/PC0002_Tifa.json
         [--motion PC0002_Tifa] [--lipmap Tifa_Default]
         [--skeleton-mesh "*/PC0002_04_Tifa_NoGlove/Model/PC0002_04.uasset"]

Read-only on the game.  The AES key comes from FF7REMAKE_AES_KEY or --key-file (kept outside the repo).
  1. UE Viewer exports Motion/Player/<motion>/Facial00/* as .psa (the single-frame F_* face poses) and a
     body mesh of the same skeleton as .psk(x).  The mesh must not be one a ~mods pak replaces (UE Viewer
     loads ~mods too): Tifa's PC0002_04 (standard outfit, no gloves) is not modded.
  2. UE Viewer -save writes the raw LipMap package LipSync/LipMap/Player/<motion>/<lipmap>; its HSFLipMap
     export is decoded here (read_lipmap: unversioned property serialization).
  3. Blender samples every pose on the PSK skeleton (ff7_face_poses_blender.py).
  4. Everything is re-expressed in the face frame: origin C_FaceBase_a, X forward, Y left, Z up, cm.
The output is game data: keep it out of the repo.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
UMODEL = r"E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe"
PAKS = r"D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\End\Content\Paks"
KEY_FILE = r"E:\tools\umodel_ff7remake\_keys\ff7remake_aes.txt"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"


# --- a cooked UE4.18 package, just enough to reach one export's bytes -----------------------------
class _Reader:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos

    def take(self, n):
        b = self.d[self.p:self.p + n]
        if len(b) != n:
            raise EOFError("read past the end at %d" % self.p)
        self.p += n
        return b

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u8(self):
        return self.take(1)[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def fstring(self):
        n = self.i32()
        if n < 0:
            return self.take(-n * 2).decode("utf-16-le").rstrip("\0")
        return self.take(n).decode("utf-8", "replace").rstrip("\0")


def read_package(uasset):
    """-> (names, [(export name, bytes)]).  The Remake cooks unversioned (file version 0 = 4.18 layout)."""
    head = open(uasset, "rb").read()
    body = open(os.path.splitext(uasset)[0] + ".uexp", "rb").read()
    r = _Reader(head)
    if r.u32() != 0x9E2A83C1:
        raise ValueError("not a UE4 package: %s" % uasset)
    if r.i32() != -4:
        r.i32()
    r.i32(), r.i32()
    r.take(r.i32() * 20)                                   # custom versions
    total_header = r.i32()
    r.fstring()
    r.u32()
    name_count, name_offset = r.i32(), r.i32()
    r.i32(), r.i32()                                       # gatherable text
    export_count, export_offset = r.i32(), r.i32()
    rn = _Reader(head, name_offset)
    names = []
    for _ in range(name_count):
        names.append(rn.fstring())
        rn.take(4)                                         # name hashes
    re_ = _Reader(head, export_offset)
    exports = []
    for _ in range(export_count):
        re_.i32(), re_.i32(), re_.i32(), re_.i32()         # class, super, template, outer
        name = names[re_.i32()]
        re_.i32()
        re_.u32()
        size, offset = re_.i64(), re_.i64()
        re_.take(12 + 16 + 4 + 4 + 4 + 20)
        start = offset - total_header
        exports.append((name, body[start:start + size]))
    return names, exports


# --- HSFLipMap (unversioned properties: uint16 fragment headers + zero masks, no tags) ------------
SHAPE_SCALAR_SIZE = {1: 4, 2: 4, 3: 4, 4: 1, 5: 4, 6: 4, 7: 1, 8: 1, 9: 4, 10: 4, 11: 1}


def _present(r):
    """Indices of the serialized values after one unversioned header."""
    frags = []
    while True:
        v = r.u16()
        frags.append((v & 0x7F, v >> 9, bool(v & 0x80)))
        if v & 0x100:
            break
    total = sum(num for _s, num, zeros in frags if zeros)
    bits = 0
    if total:
        if total <= 8:
            bits = r.u8()
        elif total <= 16:
            bits = r.u16()
        else:
            for i in range((total + 31) // 32):
                bits |= r.u32() << (32 * i)
    present, idx, m = [], 0, 0
    for skip, num, zeros in frags:
        idx += skip
        for _ in range(num):
            zero = False
            if zeros:
                zero = bool(bits >> m & 1)
                m += 1
            if not zero:
                present.append(idx)
            idx += 1
    return present


def _fname(r, names):
    i, num = r.i32(), r.i32()
    return names[i] if num == 0 else "%s_%d" % (names[i], num - 1)


def _shape(r, names):
    """HSFLipMapShape: [0] Data = Map<bone, {Attributes: Map<type, float>}>, [1..11] scalars (skipped)."""
    present = _present(r)
    if present[0] != 0:
        raise ValueError("HSFLipMapShape without Data: %s" % present)
    r.i32()
    data = {}
    for _ in range(r.i32()):
        bone = _fname(r, names)
        if _present(r) != [0]:
            raise ValueError("unexpected channel struct on %s" % bone)
        r.i32()
        data[bone] = {}
        for _c in range(r.i32()):
            channel = _fname(r, names).split("::")[-1]
            data[bone][channel] = r.f32()
    for i in present[1:]:
        r.take(SHAPE_SCALAR_SIZE[i])
    return data


def read_lipmap(uasset):
    """HSFLipMap -> {"shapes": {viseme: {bone: {channel: value}}}, "DefaultShape": ..., ...}.
    Translate channels are absolute positions under C_FaceBase_a in a Maya frame (X left, Y up,
    Z forward, cm), Rotate channels degrees; a channel a viseme does not drive is absent."""
    names, exports = read_package(uasset)
    r = _Reader(exports[0][1])
    out = {"shapes": {}}
    for i in _present(r):
        if i == 0:
            out["version"] = _fname(r, names)
        elif i == 1:
            r.i32()
            for _ in range(r.i32()):
                name = _fname(r, names)
                out["shapes"][name] = _shape(r, names)
        elif i in (2, 3):
            out["DefaultShape" if i == 2 else "MaxDifferenceShape"] = _shape(r, names)
        else:
            raise ValueError("unknown HSFLipMap value %d" % i)
    if "DefaultShape" not in out:
        raise ValueError("HSFLipMap without DefaultShape")
    return out


# --- game extraction ------------------------------------------------------------------------------
def umodel(args, key_file, paks, exe=UMODEL):
    cmd = [exe, "-game=ue4.18", "-path=" + paks, "-aes=@" + key_file] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("UE Viewer failed (%d): %s" % (r.returncode, (r.stdout + r.stderr)[-800:]))
    return r.stdout


def find(root, suffixes):
    for base, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(suffixes):
                yield os.path.join(base, f)


def face_frame(rest):
    """4x4 face frame (columns forward, left, up; origin C_FaceBase_a) + eye spacing, from bone heads."""
    left = np.array(rest["L_Eye"]) - np.array(rest["R_Eye"])
    spacing = float(np.linalg.norm(left))
    left /= spacing
    up = np.array([0.0, 0.0, 1.0])
    up -= left * up.dot(left)
    up /= np.linalg.norm(up)
    frame = np.eye(4)
    frame[:3, 0], frame[:3, 1], frame[:3, 2] = np.cross(left, up), left, up
    frame[:3, 3] = rest["C_FaceBase_a"]
    return frame, spacing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--motion", default="PC0002_Tifa", help="Motion/Player/<motion>, LipSync/LipMap/Player/<motion>")
    ap.add_argument("--lipmap", default="Tifa_Default")
    ap.add_argument("--skeleton-mesh", default="*/PC0002_04_Tifa_NoGlove/Model/PC0002_04.uasset")
    ap.add_argument("--paks", default=PAKS)
    ap.add_argument("--key-file", default=KEY_FILE)
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    work = tempfile.mkdtemp(prefix="ff7_face_")
    key_file = a.key_file
    try:
        if os.environ.get("FF7REMAKE_AES_KEY"):
            key_file = os.path.join(work, "key.txt")
            with open(key_file, "w", encoding="ascii") as fh:
                fh.write(os.environ["FF7REMAKE_AES_KEY"].strip())
        if not os.path.isfile(key_file):
            raise SystemExit("no AES key: set FF7REMAKE_AES_KEY or pass --key-file")
        exported = os.path.join(work, "export")
        umodel(["-export", "-out=" + exported, "*/%s/Facial00/*" % a.motion], key_file, a.paks)
        umodel(["-export", "-nomat", "-out=" + exported, a.skeleton_mesh], key_file, a.paks)
        umodel(["-save", "-out=" + os.path.join(work, "raw"), "*/LipMap/Player/%s/%s*" % (a.motion, a.lipmap)],
               key_file, a.paks)
        psa = sorted(find(exported, (".psa",)))
        psk = next(find(exported, (".psk", ".pskx")), None)
        lip = next((p for p in find(os.path.join(work, "raw"), (".uasset",))
                    if os.path.basename(p).lower() == a.lipmap.lower() + ".uasset"), None)
        if not psa or not psk or not lip:
            raise SystemExit("missing export: %d psa, psk %s, lipmap %s" % (len(psa), psk, lip))
        poses_json = os.path.join(work, "poses.json")
        r = subprocess.run([a.blender, "-b", "--python", os.path.join(HERE, "ff7_face_poses_blender.py"), "--",
                            psk, os.path.dirname(psa[0]), poses_json],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not os.path.isfile(poses_json):
            raise RuntimeError("pose sampling failed: %s" % (r.stdout + r.stderr)[-1500:])
        sampled = json.load(open(poses_json, encoding="utf-8"))
        lipmap = read_lipmap(lip)
    finally:
        if not a.keep_temp:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print("temp kept:", work)

    frame, spacing = face_frame(sampled["rest"])
    inv = np.linalg.inv(frame)
    poses = {}
    for name, bones in sampled["poses"].items():
        poses[name] = {b: [round(float(x), 7) for x in (inv @ np.array(m).reshape(4, 4) @ frame).ravel()]
                       for b, m in bones.items()}
    out = {"character": a.motion, "lipmap_name": a.lipmap, "eye_spacing": spacing,
           "frame": "X forward, Y left, Z up, origin C_FaceBase_a, cm; pose deltas relative to the bind pose",
           "poses": poses, "skipped_clips": sampled["skipped"],
           "lipmap": {"DefaultShape": lipmap["DefaultShape"], "shapes": lipmap["shapes"]}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(tmp, a.out)
    print("FF7_FACE_DATA=" + json.dumps({"out": a.out, "poses": len(poses), "visemes": sorted(lipmap["shapes"]),
                                         "eye_spacing": round(spacing, 3)}))


if __name__ == "__main__":
    sys.exit(main())
