"""Add a material morph to a PMX that hides some materials (diffuse and edge alpha x 0), e.g. 衣服非表示 over a
dressed model's outfit: MMD shows the body underneath when the morph is 1.

The PMX is edited in its binary form like pmx_add_scale_morph.py does: the morph is appended to the morph table and
listed in the 表情 display frame; every other byte stays where it was.  Pure Python (struct), so Blender can import
it as well (export_suit_pmx_blender.py).

  python pmx_hide_morph.py <in.pmx> <out.pmx> <morph name> <material name> [<material name> ...]

The morph name must encode in Shift-JIS (a VMD names morphs in 15 bytes of it).  A PMX that already has a morph of
that name is left alone.  add_hide_morph(..., with_morphs=["裸体形状"]) makes it a group morph that also switches on
those morphs (the full version's body shape) - the material morph is then <name>_材質.
"""
import struct
import sys

import pmx_add_scale_morph as psm


def material_names(data):
    """The PMX's material names, in order."""
    r = psm.Reader(data)
    r.skip(8)
    n_glob = r.take("B")
    glob = list(struct.unpack_from("<%dB" % n_glob, data, r.p))
    r.skip(n_glob)
    enc, add_uv, vsz, tsz, msz, bsz = glob[:6]
    E = "utf-16-le" if enc == 0 else "utf-8"
    for _ in range(4):
        r.text()
    for _ in range(r.take("i")):
        r.skip(32 + 16 * add_uv)
        kind = r.take("B")
        r.skip({0: bsz, 1: 2 * bsz + 4, 2: 4 * bsz + 16, 3: 2 * bsz + 4 + 36, 4: 4 * bsz + 16}[kind] + 4)
    r.skip(r.take("i") * vsz)
    for _ in range(r.take("i")):
        r.text()
    names = []
    for _ in range(r.take("i")):
        names.append(r.text().decode(E))
        r.text()
        r.skip(16 + 12 + 4 + 12 + 1 + 16 + 4 + 2 * tsz + 1)
        shared = r.take("B")
        r.skip(1 if shared else tsz)
        r.text()
        r.skip(4)
    return names, msz


def _text(s, enc):
    b = s.encode(enc)
    return struct.pack("<i", len(b)) + b


def _append(data, info, morph, face=True):
    """The PMX bytes with one more morph (its encoded record), listed in the 表情 frame when `face`.
    Returns (bytes, new morph index, whether the 表情 frame took it)."""
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    limit = {1: 127, 2: 32767, 4: 2 ** 31 - 1}[info["msz"]]
    if info["n_morphs"] + 1 > limit:
        raise ValueError("morph index size %d bytes cannot hold another morph" % info["msz"])
    new_index = info["n_morphs"]
    frames = [(f[0], f[1], f[2], list(f[3])) for f in info["frames"]]
    target = None
    if face:
        target = next((k for k, f in enumerate(frames) if f[2] == 1 and f[0].decode(enc) == "表情"), None)
        if target is None:
            target = next((k for k, f in enumerate(frames) if f[0].decode(enc) == "表情"), None)
        if target is not None:
            frames[target][3].append((1, new_index))
    fbytes = struct.pack("<i", len(frames))
    for fname, fname_e, special, elems in frames:
        fbytes += struct.pack("<i", len(fname)) + fname + struct.pack("<i", len(fname_e)) + fname_e
        fbytes += struct.pack("<Bi", special, len(elems))
        for t, idx in elems:
            fbytes += struct.pack("<B" + psm.index_fmt(info["msz"] if t == 1 else info["bsz"]), t, idx)
    out = (data[:info["morph_count_at"]] + struct.pack("<i", info["n_morphs"] + 1)
           + data[info["morph_count_at"] + 4:info["morphs_end"]] + morph
           + fbytes + data[info["frames_end"]:])
    return out, new_index, target is not None


def append_hide_morph(data, name, material_indices, comment="", panel=4, face=True):
    """The PMX bytes with one more material morph: multiply diffuse alpha and edge alpha of these materials by 0
    (everything else x 1).  Returns (bytes, new morph index, whether the 表情 frame took it)."""
    info = psm.parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    _names, msz = material_names(data)
    mfmt = psm.index_fmt(msz)
    one4, one3 = (1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0)
    morph = _text(name, enc) + _text(comment, enc) + struct.pack("<BBi", panel, 8, len(material_indices))
    for m in material_indices:
        morph += struct.pack("<" + mfmt + "B", m, 0)                      # 0 = multiply
        morph += struct.pack("<4f3ff3f4ff4f4f4f", 1.0, 1.0, 1.0, 0.0,      # diffuse, alpha x 0
                             *one3, 1.0, *one3,                            # specular, power, ambient
                             1.0, 1.0, 1.0, 0.0, 1.0,                      # edge colour, alpha x 0, edge size
                             *one4, *one4, *one4)                          # texture / sphere / toon tint
    return _append(data, info, morph, face)


def append_group_morph(data, name, members, comment="", panel=4, face=True):
    """The PMX bytes with one more group morph (kind 0) driving the member morphs [(index, weight)]."""
    info = psm.parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    fmt = "<" + psm.index_fmt(info["msz"]) + "f"
    morph = _text(name, enc) + _text(comment, enc) + struct.pack("<BBi", panel, 0, len(members))
    for index, weight in members:
        morph += struct.pack(fmt, index, weight)
    return _append(data, info, morph, face)


def add_hide_morph(path_in, path_out, name, materials, comment=None, with_morphs=()):
    """Hide-morph over the named materials; returns a report dict (matched / missing names).
    with_morphs: morphs already in the PMX to switch on with it (the full version's body shape 裸体形状, which
    undoes its fit under the outfit).  Then `name` is a group morph of those and the material morph
    <name>_材質."""
    name.encode("shift_jis")
    data = open(path_in, "rb").read()
    info = psm.parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    if name.encode(enc) in info["morph_names"]:
        return {"skipped": "already has %s" % name}
    names, _msz = material_names(data)
    index = {n: i for i, n in enumerate(names)}
    picked = sorted({index[m] for m in materials if m in index})
    missing = sorted({m for m in materials if m not in index})
    if not picked:
        return {"skipped": "none of the materials is in the PMX", "missing": missing}
    hide = comment if comment is not None else "hide: " + ",".join(names[i] for i in picked)
    present = [m for m in with_morphs if m.encode(enc) in info["morph_names"]]
    report = {"morph": name, "materials": [names[i] for i in picked], "missing": missing}
    if not present:
        out, mi, in_face = append_hide_morph(data, name, picked, hide)
        report.update(index=mi, in_face_frame=in_face)
    else:
        part = name + "_材質"
        part.encode("shift_jis")
        out, mi, _f = append_hide_morph(data, part, picked, hide, face=False)
        members = [(psm.parse(out)["morph_names"].index(m.encode(enc)), 1.0) for m in present] + [(mi, 1.0)]
        out, gi, in_face = append_group_morph(out, name, members, "group: %s + %s" % (part, " + ".join(present)))
        report.update(index=gi, in_face_frame=in_face, group_of=[part] + present)
    open(path_out, "wb").write(out)
    return report


def main():
    src, dst, name = sys.argv[1], sys.argv[2], sys.argv[3]
    print(add_hide_morph(src, dst, name, sys.argv[4:]))


if __name__ == "__main__":
    main()
