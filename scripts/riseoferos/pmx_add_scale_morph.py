"""Add a vertex morph to a PMX that scales the vertices of some bones about those bones' heads.

MMD bones cannot scale, but some game motions do: Rise of Eros' g04 holds its battle fan at 15% of the
bind size in every showcase clip (idle_ur01, idle_02, react_01/02), so the PMX playing those motions
waved a 2.5 m fan.  A vertex morph does the scaling in rest space before skinning, which is exact while
the scaled bones share one pivot (the fan ribs all hinge on the fan's axis) and the factor holds still
through the clip.  make_roe_vmd.py keys the morph from the VMD (--morph NAME=VALUE).

The PMX is edited in place in its binary form: the new morph is appended to the morph table and to the
表情 display frame, every other byte stays as it was (a round trip through mmd_tools would rewrite the
whole file).

  python pmx_add_scale_morph.py <in.pmx> <out.pmx> <morph name> <factor> <bone> [<bone> ...]

The morph name must encode in Shift-JIS (a VMD names morphs in 15 bytes of it): 扇子縮小, not 扇子缩小.
Running it again on a PMX that already has the morph replaces nothing and stops.
"""
import struct
import sys


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def take(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]

    def text(self):
        n = self.take("i")
        s = self.d[self.p:self.p + n]
        self.p += n
        return s

    def skip(self, n):
        self.p += n


def index_fmt(size, unsigned=False):
    if unsigned:
        return {1: "B", 2: "H", 4: "i"}[size]
    return {1: "b", 2: "h", 4: "i"}[size]


def parse(data):
    """Offsets of the sections and what the morph needs: vertices (position, fan weights), bones."""
    r = Reader(data)
    assert data[:4] == b"PMX ", "not a PMX file"
    r.skip(8)
    n_glob = r.take("B")
    glob = list(struct.unpack_from("<%dB" % n_glob, data, r.p))
    r.skip(n_glob)
    enc, add_uv, vsz, tsz, msz, bsz, mosz, rsz = glob[:8]
    for _ in range(4):
        r.text()
    vfmt, bfmt = index_fmt(vsz, True), index_fmt(bsz)
    verts = []
    uvs = []
    for _ in range(r.take("i")):
        pos = r.take("3f")
        r.skip(12)
        uvs.append(r.take("2f"))
        r.skip(16 * add_uv)
        kind = r.take("B")
        if kind == 0:
            weights = [(r.take(bfmt), 1.0)]
        elif kind in (1, 3):
            b1, b2 = r.take(bfmt), r.take(bfmt)
            w = r.take("f")
            weights = [(b1, w), (b2, 1.0 - w)]
            if kind == 3:
                r.skip(36)
        else:
            bones = [r.take(bfmt) for _ in range(4)]
            ws = r.take("4f")
            weights = list(zip(bones, ws))
        r.skip(4)
        verts.append((pos, weights))
    n_faces = r.take("i")
    r.skip(n_faces * vsz)
    for _ in range(r.take("i")):
        r.text()
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(16 + 12 + 4 + 12 + 1 + 16 + 4)
        r.skip(tsz * 2 + 1)
        shared = r.take("B")
        r.skip(1 if shared else tsz)
        r.text()
        r.skip(4)
    bones = []
    for _ in range(r.take("i")):
        name = r.text()
        r.text()
        pos = r.take("3f")
        r.skip(bsz + 4)
        flags = r.take("H")
        r.skip(bsz if flags & 0x0001 else 12)
        if flags & 0x0300:
            r.skip(bsz + 4)
        if flags & 0x0400:
            r.skip(12)
        if flags & 0x0800:
            r.skip(24)
        if flags & 0x2000:
            r.skip(4)
        if flags & 0x0020:
            r.skip(bsz + 8)
            for _ in range(r.take("i")):
                r.skip(bsz)
                if r.take("B"):
                    r.skip(24)
        bones.append((name, pos))
    morph_count_at = r.p
    n_morphs = r.take("i")
    names = []
    names_e = []
    for _ in range(n_morphs):
        names.append(r.text())
        names_e.append(r.text())
        r.skip(1)
        kind = r.take("B")
        count = r.take("i")
        # material morphs index materials (msz), group/flip morphs index morphs (mosz)
        size = {0: mosz + 4, 1: vsz + 12, 2: bsz + 28, 3: vsz + 16, 4: vsz + 16, 5: vsz + 16, 6: vsz + 16,
                7: vsz + 16, 8: msz + 1 + 112, 9: mosz + 4, 10: rsz + 1 + 24}[kind]
        r.skip(count * size)
    morphs_end = r.p
    frames_at = r.p
    frames = []
    for _ in range(r.take("i")):
        fname, fname_e = r.text(), r.text()
        special = r.take("B")
        elems = []
        for _ in range(r.take("i")):
            t = r.take("B")
            elems.append((t, r.take(index_fmt(mosz if t == 1 else bsz))))
        frames.append((fname, fname_e, special, elems))
    return {"enc": enc, "vsz": vsz, "msz": mosz, "bsz": bsz, "verts": verts, "uvs": uvs, "bones": bones,
            "morph_count_at": morph_count_at, "n_morphs": n_morphs, "morph_names": names, "morph_names_e": names_e,
            "morphs_end": morphs_end, "frames_at": frames_at, "frames_end": r.p, "frames": frames}


def main():
    src, dst, name, factor = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
    bone_names = sys.argv[5:]
    name.encode("shift_jis")                     # a VMD has to be able to name it
    data = open(src, "rb").read()
    info = parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    if name.encode(enc) in info["morph_names"]:
        sys.exit("%s already has a morph named %s" % (src, name))
    index = {n.decode(enc): i for i, (n, _p) in enumerate(info["bones"])}
    missing = [b for b in bone_names if b not in index]
    if missing:
        sys.exit("bones not in the PMX: %s" % missing)
    chosen = {index[b] for b in bone_names}
    heads = {i: info["bones"][i][1] for i in chosen}
    offsets = []
    for vi, (pos, weights) in enumerate(info["verts"]):
        d = [0.0, 0.0, 0.0]
        for b, w in weights:
            if b in chosen and w > 0:
                for k in range(3):
                    d[k] += w * (factor - 1.0) * (pos[k] - heads[b][k])
        if any(abs(c) > 1e-7 for c in d):
            offsets.append((vi, d))
    if not offsets:
        sys.exit("no vertex is weighted to %s" % bone_names)
    # the English name records what the morph scales: a later run can tell a same-named morph of other bones
    out, new_index, in_face = append_vertex_morph(data, info, name, offsets,
                                                  "scale %g: %s" % (factor, ",".join(bone_names)))
    open(dst, "wb").write(out)
    print("added morph %s (index %d): %d vertices scaled x%g about %d bone heads; %s display frame"
          % (name, new_index, len(offsets), factor, len(chosen), "in the 表情" if in_face else "no 表情"))


def append_vertex_morph(data, info, name, offsets, comment="", panel=4):
    """The PMX bytes with one more vertex morph (offsets: [(vertex index, (dx, dy, dz))] in PMX units), listed in
    the 表情 display frame; returns (bytes, new morph index, whether the 表情 frame took it).  ``info`` is
    parse(data); every byte outside the morph table and the display frames stays as it was."""
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    limit = {1: 127, 2: 32767, 4: 2 ** 31 - 1}[info["msz"]]
    if info["n_morphs"] + 1 > limit:
        raise ValueError("morph index size %d bytes cannot hold another morph" % info["msz"])

    def text(s):
        b = s.encode(enc)
        return struct.pack("<i", len(b)) + b

    vfmt = index_fmt(info["vsz"], True)
    morph = text(name) + text(comment) + struct.pack("<BBi", panel, 1, len(offsets))
    morph += b"".join(struct.pack("<" + vfmt + "3f", vi, *d) for vi, d in offsets)
    new_index = info["n_morphs"]
    frames = [(f[0], f[1], f[2], list(f[3])) for f in info["frames"]]
    face = next((k for k, f in enumerate(frames) if f[2] == 1 and f[0].decode(enc) == "表情"), None)
    if face is None:
        face = next((k for k, f in enumerate(frames) if f[0].decode(enc) == "表情"), None)
    if face is not None:
        frames[face][3].append((1, new_index))
    fbytes = struct.pack("<i", len(frames))
    for fname, fname_e, special, elems in frames:
        fbytes += struct.pack("<i", len(fname)) + fname + struct.pack("<i", len(fname_e)) + fname_e
        fbytes += struct.pack("<Bi", special, len(elems))
        for t, idx in elems:
            fbytes += struct.pack("<B" + index_fmt(info["msz"] if t == 1 else info["bsz"]), t, idx)
    out = (data[:info["morph_count_at"]] + struct.pack("<i", info["n_morphs"] + 1)
           + data[info["morph_count_at"] + 4:info["morphs_end"]] + morph
           + fbytes + data[info["frames_end"]:])
    return out, new_index, face is not None


if __name__ == "__main__":
    main()
