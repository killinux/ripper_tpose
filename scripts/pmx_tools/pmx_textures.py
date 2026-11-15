"""A PMX's texture table, edited in place - nothing else in the file changes (no mmd_tools round trip).

    python pmx_textures.py list <file.pmx>
    python pmx_textures.py relative <file.pmx | folder | @list.txt> ... [--backup DIR] [--dry-run]
    python pmx_textures.py set <file.pmx> <material> <texture> [--backup DIR] [--dry-run]

relative  absolute texture paths (E:\\game_export\\...\\textures\\x.png) -> relative to the .pmx's folder
          (textures\\x.png), so the folder still works when it is copied elsewhere.  Folders are searched
          recursively; @list.txt = one .pmx per line.  A path on another drive, or whose file is missing, is left
          as it is and reported.  2026-11-15: the 310 ROE skirt-fix side files (*_裙子碰撞修正.pmx) had absolute
          paths - cloth_batch_fix.py exported them in its work folder and copied them next to the originals.
set       the material's colour texture (`texture` relative to the .pmx; added to the table if new) - a material
          the export left without one (ROE e10's see-through piece, j06's weapon: 2026-11-15).

Every write is checked: the new file is parsed again, and outside the texture table (and the one texture index
`set` changes) it must be byte-identical to the old one.  Written to <file>.part, then replaced.  --backup copies the
original to DIR\\<its path without the drive> first (once: an existing backup is kept).
"""
import argparse
import os
import shutil
import struct
import sys

INDEX_FMT = {1: "<b", 2: "<h", 4: "<i"}


def parse(data):
    """Offsets of the texture table and the materials' texture indices."""
    if data[:4] != b"PMX ":
        raise ValueError("not a PMX file")
    n = data[8]
    g = data[9:9 + n]
    enc = "utf-16-le" if g[0] == 0 else "utf-8"
    add_uv, vsz, tsz, bsz = g[1], g[2], g[3], g[5]
    pos = 9 + n

    def text(pos):
        (ln,) = struct.unpack_from("<i", data, pos)
        return data[pos + 4:pos + 4 + ln].decode(enc), pos + 4 + ln

    for _ in range(4):                         # model name / English name / comments
        _s, pos = text(pos)
    (nv,) = struct.unpack_from("<i", data, pos)
    pos += 4
    weight_len = {0: bsz, 1: 2 * bsz + 4, 2: 4 * bsz + 16, 3: 2 * bsz + 4 + 36, 4: 4 * bsz + 16}
    for _ in range(nv):
        pos += 32 + 16 * add_uv
        kind = data[pos]
        pos += 1 + weight_len[kind] + 4
    (nf,) = struct.unpack_from("<i", data, pos)
    pos += 4 + nf * vsz
    tex_start = pos
    (nt,) = struct.unpack_from("<i", data, pos)
    pos += 4
    textures = []
    for _ in range(nt):
        s, pos = text(pos)
        textures.append(s)
    tex_end = pos
    (nm,) = struct.unpack_from("<i", data, pos)
    pos += 4
    materials = []
    for _ in range(nm):
        name, pos = text(pos)
        _en, pos = text(pos)
        pos += 16 + 12 + 4 + 12 + 1 + 16 + 4  # diffuse, specular, power, ambient, flags, edge colour, edge size
        tex_at = pos
        (tex,) = struct.unpack_from(INDEX_FMT[tsz], data, pos)
        pos += tsz * 2 + 1                     # texture, sphere, sphere mode
        shared = data[pos]
        pos += 1 + (1 if shared else tsz)
        _memo, pos = text(pos)
        pos += 4
        materials.append({"name": name, "tex": tex, "tex_at": tex_at})
    return {"enc": enc, "tsz": tsz, "tex_start": tex_start, "tex_end": tex_end, "textures": textures,
            "materials": materials}


def table_bytes(textures, enc):
    out = [struct.pack("<i", len(textures))]
    for s in textures:
        raw = s.encode(enc)
        out.append(struct.pack("<i", len(raw)) + raw)
    return b"".join(out)


def is_absolute(path):
    return len(path) > 2 and path[1] == ":" or path.startswith(("\\\\", "//"))


def rebuild(data, info, textures, set_index=None):
    """New file bytes: the texture table replaced; set_index = (material number, texture index)."""
    table = table_bytes(textures, info["enc"])
    out = bytearray(data[:info["tex_start"]] + table + data[info["tex_end"]:])
    shift = len(table) - (info["tex_end"] - info["tex_start"])
    if set_index is not None:
        m, idx = set_index
        struct.pack_into(INDEX_FMT[info["tsz"]], out, info["materials"][m]["tex_at"] + shift, idx)
    # check: parsed again, and everything outside the table / the changed index is the old bytes
    new = parse(bytes(out))
    assert new["textures"] == textures, "texture table did not read back"
    assert bytes(out[:info["tex_start"]]) == data[:info["tex_start"]]
    tail_old, tail_new = bytearray(data[info["tex_end"]:]), bytearray(out[new["tex_end"]:])
    if set_index is not None:
        m, idx = set_index
        at = info["materials"][m]["tex_at"] - info["tex_end"]
        tail_old[at:at + info["tsz"]] = struct.pack(INDEX_FMT[info["tsz"]], idx)
        assert new["materials"][m]["tex"] == idx
    assert tail_old == tail_new, "bytes after the texture table changed"
    return bytes(out)


def write(path, out, backup, dry_run):
    if dry_run:
        return
    if backup:
        dst = os.path.join(backup, os.path.splitdrive(os.path.abspath(path))[1].lstrip("\\/"))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(path, dst)
    part = path + ".part"
    with open(part, "wb") as fh:
        fh.write(out)
    os.replace(part, path)


def make_relative(path, backup=None, dry_run=False):
    """(changed paths, problems) of one .pmx."""
    data = open(path, "rb").read()
    info = parse(data)
    folder = os.path.dirname(os.path.abspath(path))
    textures, changed, problems = [], [], []
    for t in info["textures"]:
        if not is_absolute(t):
            textures.append(t)
            continue
        try:
            rel = os.path.relpath(os.path.normpath(t), folder)
        except ValueError:                     # another drive
            problems.append("other drive: %s" % t)
            textures.append(t)
            continue
        if not os.path.isfile(os.path.join(folder, rel)):
            problems.append("missing: %s" % t)
            textures.append(t)
            continue
        textures.append(rel.replace("/", "\\"))
        changed.append((t, textures[-1]))
    if changed:
        write(path, rebuild(data, info, textures), backup, dry_run)
    return changed, problems


def set_texture(path, material, texture, backup=None, dry_run=False):
    data = open(path, "rb").read()
    info = parse(data)
    hits = [i for i, m in enumerate(info["materials"]) if m["name"] == material]
    if len(hits) != 1:
        raise SystemExit("%s: %d materials named %r" % (path, len(hits), material))
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isfile(os.path.join(folder, texture)):
        raise SystemExit("%s: no file %s next to it" % (path, texture))
    textures = list(info["textures"])
    if texture not in textures:
        textures.append(texture)
    idx = textures.index(texture)
    if idx >= 2 ** (8 * info["tsz"] - 1):
        raise SystemExit("%s: texture index %d does not fit %d bytes" % (path, idx, info["tsz"]))
    old = info["materials"][hits[0]]["tex"]
    write(path, rebuild(data, info, textures, (hits[0], idx)), backup, dry_run)
    return old, idx


def pmx_files(args):
    for a in args:
        if a.startswith("@"):
            for line in open(a[1:], encoding="utf-8"):
                if line.strip():
                    yield line.strip()
        elif os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for f in sorted(files):
                    if f.lower().endswith(".pmx"):
                        yield os.path.join(root, f)
        else:
            yield a


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("pmx")
    p = sub.add_parser("relative")
    p.add_argument("paths", nargs="+")
    p.add_argument("--backup")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("set")
    p.add_argument("pmx")
    p.add_argument("material")
    p.add_argument("texture")
    p.add_argument("--backup")
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "list":
        info = parse(open(args.pmx, "rb").read())
        for i, t in enumerate(info["textures"]):
            print("%3d  %s" % (i, t))
        for m in info["materials"]:
            print("  %-40s -> %s" % (m["name"], info["textures"][m["tex"]] if 0 <= m["tex"] < len(info["textures"])
                                      else "(none)"))
    elif args.cmd == "relative":
        files = changed_files = paths = 0
        for path in pmx_files(args.paths):
            files += 1
            try:
                changed, problems = make_relative(path, args.backup, args.dry_run)
            except (OSError, ValueError, AssertionError) as exc:   # open in another program, not a PMX ...
                print("  ! %s: %s" % (path, exc))
                continue
            if changed:
                changed_files += 1
                paths += len(changed)
            for p in problems:
                print("  ! %s: %s" % (path, p))
        print("%s%d PMX read, %d with absolute texture paths, %d paths made relative" % (
            "(dry run) " if args.dry_run else "", files, changed_files, paths))
    elif args.cmd == "set":
        old, idx = set_texture(args.pmx, args.material, args.texture, args.backup, args.dry_run)
        print("%s%s: %s texture %d -> %d (%s)" % ("(dry run) " if args.dry_run else "", args.pmx, args.material, old,
                                                 idx, args.texture))


if __name__ == "__main__":
    sys.exit(main())
