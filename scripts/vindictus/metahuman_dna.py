"""MetaHuman DNA of a Vindictus face: pull it out of the game, read it, evaluate expressions.

Vindictus' player faces are MetaHumans (``SK_Face_Archetype_Skeleton``, ``ABP_FaceBasePost``).
Their expressions are not shape keys: RigLogic moves ~650 ``FACIAL_*`` joints from 269 raw
controls (``CTRL_expressions.eyeBlinkL`` ...), using the DNA stored inside the cooked face mesh
(``SK_Fiona_Face01.uasset`` carries a ``DNAAsset`` whose behaviour stream is a plain DNA v2.1
file).  UE Viewer does not export it, so the PSK has the joints but nothing that moves them.

This module is numpy-only (it also runs inside Blender):

  * ``extract``: decrypt + decompress the face package straight from the IoStore container
    (reuses scripts/firstdescendant/iostore.py) and cut the DNA stream out of it.
  * ``read``: the DNA v2.1 layout (terse, big-endian): descriptor, definition (names, joint
    hierarchy, neutral joints), behaviour (conditional table, PSDs, joint groups).
  * ``DnaFace``: what RigLogic does per frame - raw controls -> PSDs (product of weighted
    inputs, clamped 0..1) -> joint deltas (one dense sub-matrix per joint group, LOD 0) ->
    local transform = neutral translation + delta (cm), neutral rotation * delta rotation
    (Euler XYZ in degrees, R = Rz Ry Rx) -> forward kinematics.

Checked on Fiona (2026-09-26): the DNA's neutral skeleton, run through FK, lands on the exported
rig's 620 facial joints with a mean error of 0.38 mm (scale 0.01, Maya Y-up -> Blender Z-up);
eyeBlinkL moves 47 joints (upper lid 1.2 cm), jawOpen 429 (chin 5.3 cm).

    python metahuman_dna.py extract [--package <path in container>] [--out <file.dna>]
    python metahuman_dna.py info <file.dna>
"""
import argparse
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GAME = r"E:\tools\vindictus"
DEFAULT_KEY_FILE = r"E:\tools\vindictus\_download\aes_key.txt"
DEFAULT_OODLE = r"E:\tools\cue4parse_cli\oodle-data-shared.dll"
DEFAULT_PACKAGE = "Vindictus/Content/VindictusRoot/Character/Player/Fiona/Face/Model/SK_Fiona_Face01.uasset"
SIGNATURE = b"DNA\x00\x02\x00\x01"          # generation 2, version 1


# -- pulling the DNA out of the game ----------------------------------------------------------
def load_key(key_file=DEFAULT_KEY_FILE):
    key = os.environ.get("VINDICTUS_AES_KEY", "")
    if not key and os.path.isfile(key_file):
        key = open(key_file, encoding="utf-8").read().strip()
    if not key:
        raise SystemExit("no AES key: set VINDICTUS_AES_KEY or put it in %s" % key_file)
    return bytes.fromhex(key[2:] if key.lower().startswith("0x") else key)


def extract(package=DEFAULT_PACKAGE, game=DEFAULT_GAME, key_file=DEFAULT_KEY_FILE, oodle=DEFAULT_OODLE):
    """Bytes of the DNA stream embedded in a cooked face mesh package."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "firstdescendant"))
    from iostore import Oodle, Toc

    toc = Toc(os.path.join(game, "Vindictus", "Content", "Paks", "Vindictus-Windows.utoc"), load_key(key_file))
    paths = toc.paths()
    if package not in paths:
        raise SystemExit("package not in the container: %s" % package)
    return find_stream(toc.read_chunk(paths[package], Oodle(oodle)))


def find_stream(buf):
    start = buf.find(SIGNATURE)
    if start < 0:
        raise ValueError("no DNA v2.1 stream in this data")
    end = buf.find(b"AND", start)
    return buf[start:end + 3]


# -- reading ------------------------------------------------------------------------------------
class _Reader:
    def __init__(self, data, pos=0):
        self.b, self.p = data, pos

    def u16(self):
        value, = struct.unpack_from(">H", self.b, self.p)
        self.p += 2
        return value

    def u32(self):
        value, = struct.unpack_from(">I", self.b, self.p)
        self.p += 4
        return value

    def u16s(self):
        n = self.u32()
        out = np.frombuffer(self.b, dtype=">u2", count=n, offset=self.p).astype(np.int64)
        self.p += 2 * n
        return out

    def f32s(self):
        n = self.u32()
        out = np.frombuffer(self.b, dtype=">f4", count=n, offset=self.p).astype(np.float64)
        self.p += 4 * n
        return out

    def text(self):
        n = self.u32()
        out = self.b[self.p:self.p + n].decode("utf-8", "replace")
        self.p += n
        return out

    def texts(self):
        return [self.text() for _ in range(self.u32())]


def read(dna):
    """Parse a DNA v2.1 stream (bytes) into plain dicts / numpy arrays."""
    if not dna.startswith(SIGNATURE):
        raise ValueError("not a DNA v2.1 stream")
    r = _Reader(dna, 7)
    names = ("descriptor", "definition", "behavior", "controls", "joints", "blendShapeChannels",
             "animatedMaps", "geometry")
    sec = dict(zip(names, (r.u32() for _ in names)))
    r.p = sec["descriptor"]
    desc = {"name": r.text(), "archetype": r.u16(), "gender": r.u16(), "age": r.u16()}
    desc["metadata"] = [(r.text(), r.text()) for _ in range(r.u32())]
    desc["translationUnit"], desc["rotationUnit"] = r.u16(), r.u16()     # 0 = cm, 0 = degrees
    desc["coordinateSystem"] = (r.u16(), r.u16(), r.u16())                # (0, 2, 4) = right, up, front
    desc["lodCount"], desc["maxLOD"] = r.u16(), r.u16()
    desc["complexity"], desc["dbName"] = r.text(), r.text()

    r.p = sec["definition"]

    def lod_mapping():
        lods = r.u16s()
        return lods, [r.u16s() for _ in range(r.u32())]

    df = {"lodJoint": lod_mapping(), "lodBlend": lod_mapping(), "lodAnim": lod_mapping(), "lodMesh": lod_mapping()}
    df["gui"], df["raw"], df["joints"] = r.texts(), r.texts(), r.texts()
    df["blendShapes"], df["animatedMaps"], df["meshes"] = r.texts(), r.texts(), r.texts()
    df["meshBlend"] = (r.u16s(), r.u16s())
    df["hierarchy"] = r.u16s()
    df["neutralT"] = np.stack([r.f32s(), r.f32s(), r.f32s()], 1)
    df["neutralR"] = np.stack([r.f32s(), r.f32s(), r.f32s()], 1)
    if r.p != sec["behavior"]:
        raise ValueError("definition section ends at %d, behaviour starts at %d" % (r.p, sec["behavior"]))

    r.p = sec["controls"]
    controls = {"psdCount": r.u16()}
    controls["conditionals"] = [r.u16s(), r.u16s(), r.f32s(), r.f32s(), r.f32s(), r.f32s()]
    controls["psd"] = {"rows": r.u16s(), "cols": r.u16s(), "values": r.f32s()}
    r.p = sec["joints"]
    joints = {"rowCount": r.u16(), "colCount": r.u16(), "groups": []}
    for _ in range(r.u32()):
        joints["groups"].append({"lods": r.u16s(), "inputs": r.u16s(), "outputs": r.u16s(),
                                 "values": r.f32s(), "joints": r.u16s()})
    if r.p != sec["blendShapeChannels"]:
        raise ValueError("joint behaviour ends at %d, next section starts at %d" % (r.p, sec["blendShapeChannels"]))
    return {"descriptor": desc, "definition": df, "controls": controls, "joints": joints, "sections": sec}


# -- evaluating ---------------------------------------------------------------------------------
def euler_xyz(degrees):
    """Rotation matrices for rows of (x, y, z) degrees, R = Rz @ Ry @ Rx (Maya's xyz order)."""
    a, b, c = np.radians(np.atleast_2d(degrees)).T
    ca, sa, cb, sb, cc, sc = np.cos(a), np.sin(a), np.cos(b), np.sin(b), np.cos(c), np.sin(c)
    m = np.empty((len(a), 3, 3))
    m[:, 0] = np.stack([cc * cb, cc * sb * sa - sc * ca, cc * sb * ca + sc * sa], 1)
    m[:, 1] = np.stack([sc * cb, sc * sb * sa + cc * ca, sc * sb * ca - cc * sa], 1)
    m[:, 2] = np.stack([-sb, cb * sa, cb * ca], 1)
    return m


class DnaFace:
    def __init__(self, dna):
        data = read(dna)
        df, controls = data["definition"], data["controls"]
        self.descriptor = data["descriptor"]
        self.joints = list(df["joints"])
        self.parent = df["hierarchy"]
        self.neutral_t, self.neutral_r = df["neutralT"], df["neutralR"]
        self.raw = [name.split(".", 1)[-1] for name in df["raw"]]
        self.raw_index = {name: i for i, name in enumerate(self.raw)}
        self.psd_count = controls["psdCount"]
        psd = controls["psd"]
        self.psd = (psd["rows"], psd["cols"], psd["values"])
        self.groups = [(g["inputs"], g["outputs"], g["values"].reshape(len(g["outputs"]), len(g["inputs"])))
                       for g in data["joints"]["groups"] if len(g["inputs"]) and len(g["outputs"])]
        depth = np.zeros(len(self.joints), dtype=int)
        for j in range(len(self.joints)):
            k = j
            while self.parent[k] != k:
                k = self.parent[k]
                depth[j] += 1
        self.order = list(np.argsort(depth, kind="stable"))
        self.neutral_rot = euler_xyz(self.neutral_r)
        self.rest = self.fk(np.zeros((len(self.joints), 3)), np.zeros((len(self.joints), 3)))

    def inputs(self, controls):
        values = np.zeros(len(self.raw) + self.psd_count)
        for name, value in controls.items():
            if name not in self.raw_index:
                raise KeyError("no raw control %r in this DNA" % name)
            values[self.raw_index[name]] = value
        product = np.ones(self.psd_count)
        rows, cols, weights = self.psd
        for row, col, weight in zip(rows, cols, weights):
            product[row - len(self.raw)] *= values[col] * weight
        values[len(self.raw):] = np.clip(product, 0.0, 1.0)
        return values

    def deltas(self, controls):
        """(translation cm, rotation degrees, scale) deltas per joint."""
        values = self.inputs(controls)
        out = np.zeros(len(self.joints) * 9)
        for ins, outs, matrix in self.groups:
            np.add.at(out, outs, matrix @ values[ins])
        out = out.reshape(-1, 9)
        return out[:, 0:3], out[:, 3:6], out[:, 6:9]

    def fk(self, d_t, d_r):
        local = np.zeros((len(self.joints), 4, 4))
        local[:, :3, :3] = self.neutral_rot @ euler_xyz(d_r)
        local[:, :3, 3] = self.neutral_t + d_t
        local[:, 3, 3] = 1.0
        world = np.zeros_like(local)
        for j in self.order:
            p = self.parent[j]
            world[j] = local[j] if p == j else world[p] @ local[j]
        return world

    def posed(self, controls):
        """World (DNA space, cm) joint matrices for these raw control values."""
        d_t, d_r, _d_s = self.deltas(controls)
        return self.fk(d_t, d_r)


def fit_similarity(src, dst):
    """dst ~ s * R @ src + t for matched point rows (least squares, reflection allowed)."""
    cs, cd = src.mean(0), dst.mean(0)
    u, sv, vt = np.linalg.svd((src - cs).T @ (dst - cd))
    rot = (u @ vt).T
    scale = sv.sum() / ((src - cs) ** 2).sum()
    shift = cd - scale * rot @ cs
    err = np.linalg.norm((scale * (rot @ src.T)).T + shift - dst, axis=1)
    return scale, rot, shift, err


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract", help="cut the DNA out of the game's face package")
    ex.add_argument("--package", default=DEFAULT_PACKAGE)
    ex.add_argument("--game", default=DEFAULT_GAME)
    ex.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    ex.add_argument("--oodle", default=DEFAULT_OODLE)
    ex.add_argument("--out", default="")
    info = sub.add_parser("info", help="summarise a .dna file")
    info.add_argument("dna")
    args = ap.parse_args()
    if args.cmd == "extract":
        dna = extract(args.package, args.game, args.key_file, args.oodle)
        out = args.out or os.path.splitext(os.path.basename(args.package))[0] + ".dna"
        with open(out, "wb") as fh:
            fh.write(dna)
        print("wrote %s (%d bytes)" % (out, len(dna)))
        path = out
    else:
        path = args.dna
    face = DnaFace(open(path, "rb").read())
    d = face.descriptor
    print("%s: %d joints, %d raw controls, %d PSDs, %d joint groups; units %s/%s, axes %s, dbName %s" % (
        d["name"], len(face.joints), len(face.raw), face.psd_count, len(face.groups),
        ("cm", "m")[d["translationUnit"]], ("deg", "rad")[d["rotationUnit"]], d["coordinateSystem"], d["dbName"]))


if __name__ == "__main__":
    main()
