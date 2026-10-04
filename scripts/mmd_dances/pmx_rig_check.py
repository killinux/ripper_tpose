"""What of a PMX will not follow the dancer: mesh weighted to bones that hang from no other bone (read-only).

    python pmx_rig_check.py <file.pmx | folder> ...      # a folder: every .pmx under it

A PMX keeps its bones in one tree under 全ての親; a dance (VMD) moves that tree.  A bone without a parent that is
not 全ての親 is a second tree nobody moves: whatever is weighted to it, or to a bone below it, stays where it stood in
the rest pose while the body dances away - a flower in the air beside the skirt, a gun floating at hip height.
Rise of Eros has such bones where the game attaches a part by code at run time (a weapon to the hand, "prop_L_Dummy",
"Bip001 Prop1", "AC_pistol") or the exporter lost a parent ("flowe_BL_01Root"); MMD shows the part standing still
just the same - it is the model's fault, not the renderer's.

loose_parts() returns, for each such tree that carries vertices, its root, the number of vertices and the bones of
it that carry them.  Only the vertex weights and the bone list are read.
"""
from __future__ import annotations

import os
import struct
import sys

ROOTS_OK = ("全ての親",)                                # the root a VMD moves (all else hangs from it)


class _Reader:
    def __init__(self, data: bytes):
        if data[:4] != b"PMX ":
            raise ValueError("not a PMX file")
        self.d = data
        n = data[8]
        g = list(data[9:9 + n])
        self.enc, self.add_uv, self.vsz, self.tsz, self.msz, self.bsz = g[:6]
        self.codec = "utf-16-le" if self.enc == 0 else "utf-8"
        self.p = 9 + n

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def text(self) -> str:
        n = self.i32()
        s = self.d[self.p:self.p + n].decode(self.codec, errors="replace")
        self.p += n
        return s

    def bone_index(self) -> int:
        v = struct.unpack_from({1: "<b", 2: "<h", 4: "<i"}[self.bsz], self.d, self.p)[0]
        self.p += self.bsz
        return v


def read_rig(path: str) -> tuple[dict, list]:
    """({bone index: number of vertices weighted to it}, [(bone name, parent index)])."""
    with open(path, "rb") as fh:
        r = _Reader(fh.read())
    for _ in range(4):                                  # model name / comment, Japanese and English
        r.text()
    d, b = r.d, r.bsz
    kind = {1: "b", 2: "h", 4: "i"}[b]
    one, two, four = struct.Struct("<" + kind), struct.Struct("<2%sf" % kind), struct.Struct("<4%s4f" % kind)
    skip = 32 + 16 * r.add_uv                           # position, normal, uv, additional uvs
    count = {}
    p = r.p
    n = struct.unpack_from("<i", d, p)[0]
    p += 4
    for _ in range(n):
        p += skip
        weight = d[p]
        p += 1
        if weight == 0:                                 # BDEF1
            bi = one.unpack_from(d, p)[0]
            count[bi] = count.get(bi, 0) + 1
            p += b
        elif weight in (1, 3):                          # BDEF2, SDEF (+ C, R0, R1)
            b1, b2, x = two.unpack_from(d, p)
            if x > 0:
                count[b1] = count.get(b1, 0) + 1
            if x < 1:
                count[b2] = count.get(b2, 0) + 1
            p += 2 * b + 4 + (36 if weight == 3 else 0)
        elif weight in (2, 4):                          # BDEF4, QDEF
            v = four.unpack_from(d, p)
            for bi, x in zip(v[:4], v[4:]):
                if x > 0:
                    count[bi] = count.get(bi, 0) + 1
            p += 4 * b + 16
        else:
            raise ValueError("unknown weight type %d" % weight)
        p += 4                                          # edge scale
    r.p = p
    faces = r.i32()                                     # (two steps: r.p += r.i32() ... would lose the count's 4 bytes)
    r.p += faces * r.vsz
    for _ in range(r.i32()):                            # textures
        r.text()
    for _ in range(r.i32()):                            # materials
        r.text()
        r.text()
        r.p += 16 + 12 + 4 + 12 + 1 + 16 + 4 + r.tsz * 2 + 1
        shared = d[r.p]
        r.p += 1
        r.p += 1 if shared else r.tsz
        r.text()
        r.p += 4
    bones = []
    for _ in range(r.i32()):
        name = r.text()
        r.text()
        r.p += 12
        parent = r.bone_index()
        r.p += 4
        flags = struct.unpack_from("<H", d, r.p)[0]
        r.p += 2
        r.p += b if flags & 0x0001 else 12              # tail: a bone, or an offset
        if flags & 0x0300:                              # grant rotation / translation
            r.p += b + 4
        if flags & 0x0400:                              # fixed axis
            r.p += 12
        if flags & 0x0800:                              # local axes
            r.p += 24
        if flags & 0x2000:                              # external parent
            r.p += 4
        if flags & 0x0020:                              # IK
            r.p += b + 8
            for _ in range(r.i32()):
                r.p += b
                limited = d[r.p]
                r.p += 1 + (24 if limited else 0)
        bones.append((name, parent))
    return count, bones


def loose_parts(path: str, roots_ok: tuple = ROOTS_OK) -> list[dict]:
    """[{"root", "verts", "bones"}] - each bone without a parent (but those in `roots_ok`) whose tree carries
    vertices: how many, and which of its bones carry them.  [] for a model that moves as one."""
    count, bones = read_rig(path)
    kids = {}
    for i, (_name, parent) in enumerate(bones):
        kids.setdefault(parent, []).append(i)
    out = []
    for i, (name, parent) in enumerate(bones):
        if parent >= 0 or name in roots_ok:
            continue
        tree, stack = [], [i]
        while stack:
            j = stack.pop()
            tree.append(j)
            stack += kids.get(j, [])
        verts = sum(count.get(j, 0) for j in tree)
        if verts:
            out.append({"root": name, "verts": verts, "bones": [bones[j][0] for j in sorted(tree) if count.get(j)]})
    return out


def describe(parts: list[dict]) -> str:
    """One line for the lists: '有部件没有父骨骼…: flowe_BL_01Root (840 个顶点), …'."""
    return "有部件挂在没有父骨骼的骨骼上，跳舞时会停在原地：" + "，".join(
        "%s（%d 个顶点）" % (p["root"], p["verts"]) for p in parts)


def main() -> int:
    paths = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            paths += sorted(os.path.join(dp, f) for dp, _dn, fs in os.walk(arg) for f in fs if f.lower().endswith(".pmx"))
        else:
            paths.append(arg)
    if not paths:
        print(__doc__)
        return 2
    bad = 0
    for path in paths:
        parts = loose_parts(path)
        bad += bool(parts)
        print("%s  %s" % (path, "; ".join("%s: %d verts (%s)" % (p["root"], p["verts"], ", ".join(p["bones"][:4]))
                                          for p in parts) or "ok"))
    print("%d of %d have parts that do not follow the body" % (bad, len(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
