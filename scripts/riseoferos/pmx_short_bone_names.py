"""Rename the bones of existing PMX files so that a VMD can address every one of them.

A VMD names each keyed bone in 15 bytes of Shift-JIS; bones with longer names, or names that collide once cut,
cannot all be keyed (see pmx_bone_names.py, which also picks the new names).  The exporter now writes short names
itself; this tool fixes PMX files exported before that.

  python pmx_short_bone_names.py <file.pmx | folder> ... [--dry-run] [--backup <dir> --root <dir>]

Only bone names change.  A renamed bone gets the short name as its Japanese name and keeps the original in its
English name when that is empty (ROE PMX leave it empty), so tools can still find the game's bone.  Every other
byte of the file stays as it was: the rewritten file is parsed again and compared field by field before it
replaces the original (through a temporary file).  Files whose names all fit already are not touched.
--backup copies each file it is about to change to <dir>\\<path relative to --root> first.
"""
import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmx_bone_names  # noqa: E402


class PMX:
    """Byte spans of a PMX file, enough to rewrite bone names: where the bone section starts and ends and,
    for each bone, the span of its two names and the rest of its record."""

    def __init__(self, data):
        if data[:4] != b"PMX ":
            raise ValueError("not a PMX file")
        self.data = data
        n_glob = data[8]
        g = list(data[9:9 + n_glob])
        self.enc, self.add_uv, self.vsz, self.tsz, self.msz, self.bsz, self.mosz, self.rsz = g[:8]
        self.codec = "utf-16-le" if self.enc == 0 else "utf-8"
        self.p = 9 + n_glob
        for _ in range(4):
            self._text()
        self._vertices()
        n = self._int()
        self.p += n * self.vsz
        for _ in range(self._int()):
            self._text()
        self._materials()
        self.bones_at = self.p
        self.bones = []
        for _ in range(self._int()):
            self.bones.append(self._bone())
        self.bones_end = self.p

    def _int(self):
        v = struct.unpack_from("<i", self.data, self.p)[0]
        self.p += 4
        return v

    def _text(self):
        n = self._int()
        s = self.data[self.p:self.p + n]
        self.p += n
        return s.decode(self.codec)

    def _vertices(self):
        b = self.bsz
        for _ in range(self._int()):
            self.p += 12 + 12 + 8 + 16 * self.add_uv
            kind = self.data[self.p]
            self.p += 1
            self.p += {0: b, 1: 2 * b + 4, 2: 4 * b + 16, 3: 2 * b + 4 + 36, 4: 4 * b + 16}[kind]
            self.p += 4

    def _materials(self):
        for _ in range(self._int()):
            self._text()
            self._text()
            self.p += 16 + 12 + 4 + 12 + 1 + 16 + 4 + self.tsz * 2 + 1
            shared = self.data[self.p]
            self.p += 1
            self.p += 1 if shared else self.tsz
            self._text()
            self.p += 4

    def _bone(self):
        start = self.p
        name_j = self._text()
        name_e = self._text()
        names_end = self.p
        b = self.bsz
        self.p += 12 + b + 4
        flags = struct.unpack_from("<H", self.data, self.p)[0]
        self.p += 2
        self.p += b if flags & 0x0001 else 12
        if flags & 0x0300:
            self.p += b + 4
        if flags & 0x0400:
            self.p += 12
        if flags & 0x0800:
            self.p += 24
        if flags & 0x2000:
            self.p += 4
        if flags & 0x0020:
            self.p += b + 8
            for _ in range(self._int()):
                self.p += b
                limited = self.data[self.p]
                self.p += 1
                if limited:
                    self.p += 24
        return {"start": start, "names_end": names_end, "end": self.p, "name_j": name_j, "name_e": name_e}

    def text_bytes(self, s):
        raw = s.encode(self.codec)
        return struct.pack("<i", len(raw)) + raw


def renamed(data):
    """(new file bytes, [(index, old, new)]) - new bytes are None when nothing needs renaming."""
    pmx = PMX(data)
    names = [b["name_j"] for b in pmx.bones]
    mapping = pmx_bone_names.short_names(names)
    if not mapping:
        return None, []
    parts = [data[:pmx.bones_at + 4]]
    for i, b in enumerate(pmx.bones):
        if i in mapping:
            name_e = b["name_e"] or b["name_j"]
            parts.append(pmx.text_bytes(mapping[i]) + pmx.text_bytes(name_e) + data[b["names_end"]:b["end"]])
        else:
            parts.append(data[b["start"]:b["end"]])
    parts.append(data[pmx.bones_end:])
    out = b"".join(parts)
    verify(pmx, PMX(out), mapping)
    return out, [(i, names[i], new) for i, new in sorted(mapping.items())]


def verify(old, new, mapping):
    """The rewrite changed bone names and nothing else."""
    d0, d1 = old.data, new.data
    assert d0[:old.bones_at] == d1[:new.bones_at], "bytes before the bones changed"
    assert d0[old.bones_end:] == d1[new.bones_end:], "bytes after the bones changed"
    assert len(old.bones) == len(new.bones), "bone count changed"
    for i, (a, b) in enumerate(zip(old.bones, new.bones)):
        assert d0[a["names_end"]:a["end"]] == d1[b["names_end"]:b["end"]], "bone %d record changed" % i
        if i in mapping:
            assert b["name_j"] == mapping[i] and b["name_e"] == (a["name_e"] or a["name_j"]), "bone %d names" % i
        else:
            assert (a["name_j"], a["name_e"]) == (b["name_j"], b["name_e"]), "bone %d renamed" % i
    final = [b["name_j"] for b in new.bones]
    assert len(set(final)) == len(final) and all(pmx_bone_names.fits(n) for n in final), "names still clash"


def pmx_files(targets):
    for t in targets:
        if os.path.isdir(t):
            for dirpath, _dirs, files in os.walk(t):
                for f in sorted(files):
                    if f.lower().endswith(".pmx"):
                        yield os.path.join(dirpath, f)
        else:
            yield t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup")
    ap.add_argument("--root")
    ap.add_argument("--quiet", action="store_true", help="one line per file, no name list")
    args = ap.parse_args()
    if args.backup and not args.root:
        sys.exit("--backup needs --root (the folder the backup mirrors)")
    changed = skipped = 0
    for path in pmx_files(args.targets):
        data = open(path, "rb").read()
        try:
            out, rows = renamed(data)
        except (AssertionError, ValueError, struct.error, KeyError) as exc:
            print("FAILED  %s: %s" % (path, exc))
            continue
        if out is None:
            skipped += 1
            print("ok      %s (all names fit)" % path)
            continue
        print("%s %s: %d bones renamed" % ("would  " if args.dry_run else "renamed", path, len(rows)))
        if not args.quiet:
            for _i, old, new in rows:
                print("          %-32s -> %s" % (old, new))
        if args.dry_run:
            continue
        if args.backup:
            dst = os.path.join(args.backup, os.path.relpath(path, args.root))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.copy2(path, dst)
        tmp = path + ".short_names.tmp"
        with open(tmp, "wb") as handle:
            handle.write(out)
        os.replace(tmp, path)
        changed += 1
    print("done: %d renamed, %d already fine" % (changed, skipped))


if __name__ == "__main__":
    main()
