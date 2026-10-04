"""Turn a PMX's bone morphs into vertex morphs, in the file itself: every bone morph that moves the mesh becomes a
vertex morph with the same name, English name, panel and index (group morphs and the 表情 frame keep pointing at it),
every other byte of the file stays as it was.

What a bone morph does is computed the way MMD does it, on the PMX's own data: the morph's translation and rotation
are the bones' local pose (bone frames are world-aligned in PMX, the rotation turns about the bone's position),
children follow their parents, 付与 (grant) bones take their grant parent's share, and every vertex is skinned with
its own weights (BDEF1 / BDEF2 / BDEF4; SDEF as its BDEF2 part).  The offset of each vertex from its rest position
is the vertex morph.  Morphs are kept as bone morphs when they move no vertex, or move bones an IK chain or a
physics rigid body drives (MMD would recompute those after the morph).

Why: export_character_model_blender.py now bakes the ROE face morphs to vertex morphs at export time
(bake_bone_morphs); this does the same for PMX exported before that, without exporting them again.

  python pmx_vertex_morphs.py <pmx or folder> [...] [--from <list.txt>] [--out <pmx>] [--backup <dir> --base <dir>]
                              [--dry-run]

  --from     also the files listed in a text file, one path per line
  --out      write here instead of over the input (one input file only)
  --backup   copy each changed original to <dir>\\<its path relative to --base> before it is replaced
  --dry-run  convert in memory and report, write nothing
A folder is searched for *.pmx recursively.  Prints one line per file and PMX_VERTEX_MORPHS=<json> at the end.
"""
import argparse
import json
import os
import shutil
import struct
import sys

import numpy as np

THRESHOLD = 1.25e-5     # PMX units (x12.5 = 1 micrometre): smaller vertex offsets are left out
SIZE = {0: lambda s: s["mosz"] + 4, 1: lambda s: s["vsz"] + 12, 2: lambda s: s["bsz"] + 28,
        3: lambda s: s["vsz"] + 16, 4: lambda s: s["vsz"] + 16, 5: lambda s: s["vsz"] + 16,
        6: lambda s: s["vsz"] + 16, 7: lambda s: s["vsz"] + 16, 8: lambda s: s["msz"] + 1 + 112,
        9: lambda s: s["mosz"] + 4, 10: lambda s: s["rsz"] + 1 + 24}


def index_fmt(size, unsigned=False):
    return ({1: "B", 2: "H", 4: "i"} if unsigned else {1: "b", 2: "h", 4: "i"})[size]


class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

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


def parse(data):
    """What the conversion needs: index sizes, vertices (position, bones, weights), bones, the morph records with
    their byte ranges, the bones IK and physics drive."""
    if data[:4] != b"PMX ":
        raise ValueError("not a PMX file")
    r = Reader(data)
    r.skip(8)
    n_glob = r.take("B")
    g = list(struct.unpack_from("<%dB" % n_glob, data, r.p))
    r.skip(n_glob)
    s = dict(zip(("enc", "add_uv", "vsz", "tsz", "msz", "bsz", "mosz", "rsz"), g[:8]))
    for _ in range(4):
        r.text()
    bfmt = index_fmt(s["bsz"])
    n = r.take("i")
    pos = np.zeros((n, 3))
    bones = np.full((n, 4), -1, dtype=np.int64)
    weights = np.zeros((n, 4))
    kinds = np.zeros(n, dtype=np.int8)
    for i in range(n):
        pos[i] = r.take("3f")
        r.skip(12 + 8 + 16 * s["add_uv"])
        k = r.take("B")
        kinds[i] = k
        if k == 0:
            bones[i, 0], weights[i, 0] = r.take(bfmt), 1.0
        elif k in (1, 3):                       # BDEF2, SDEF (C, R0, R1 follow)
            bones[i, :2] = r.take(bfmt), r.take(bfmt)
            w = r.take("f")
            weights[i, :2] = w, 1.0 - w
            if k == 3:
                r.skip(36)
        elif k in (2, 4):                       # BDEF4, QDEF
            bones[i] = [r.take(bfmt) for _ in range(4)]
            weights[i] = r.take("4f")
        else:
            raise ValueError("vertex %d: weight type %d" % (i, k))
        r.skip(4)
    r.skip(r.take("i") * s["vsz"])
    for _ in range(r.take("i")):
        r.text()
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(16 + 12 + 4 + 12 + 1 + 16 + 4 + 2 * s["tsz"] + 1)
        r.skip(1 if r.take("B") else s["tsz"])
        r.text()
        r.skip(4)
    blist = []
    for _ in range(r.take("i")):
        b = {"name": r.text()}
        r.text()
        b["pos"] = np.array(r.take("3f"))
        b["parent"] = r.take(bfmt)
        b["level"] = r.take("i")
        f = b["flags"] = r.take("H")
        r.skip(s["bsz"] if f & 0x0001 else 12)
        if f & 0x0300:
            b["grant"] = (r.take(bfmt), r.take("f"))
        if f & 0x0400:
            r.skip(12)
        if f & 0x0800:
            r.skip(24)
        if f & 0x2000:
            r.skip(4)
        if f & 0x0020:
            b["ik_target"] = r.take(bfmt)
            r.skip(8)
            links = []
            for _ in range(r.take("i")):
                links.append(r.take(bfmt))
                if r.take("B"):
                    r.skip(24)
            b["ik_links"] = links
        blist.append(b)
    morphs_at = r.p
    morphs = []
    for _ in range(r.take("i")):
        start = r.p
        name, name_e = r.text(), r.text()
        panel, kind = r.take("B"), r.take("B")
        count = r.take("i")
        body = r.p
        r.skip(count * SIZE[kind](s))
        morphs.append({"name": name, "name_e": name_e, "panel": panel, "kind": kind, "count": count,
                       "start": start, "body": body, "end": r.p})
    morphs_end = r.p
    for _ in range(r.take("i")):                # display frames
        r.text(), r.text()
        r.skip(1)
        for _ in range(r.take("i")):
            t = r.take("B")
            r.skip(s["mosz"] if t == 1 else s["bsz"])
    physics = set()
    for _ in range(r.take("i")):                # rigid bodies: bone, mode (0 follows the bone)
        r.text(), r.text()
        bone = r.take(bfmt)
        r.skip(1 + 2 + 1 + 12 + 12 + 12 + 4 * 5)
        if r.take("B") != 0 and bone >= 0:
            physics.add(bone)
    return {"sizes": s, "pos": pos, "bones": bones, "weights": weights, "kinds": kinds, "bone_list": blist,
            "morphs": morphs, "morphs_at": morphs_at, "morphs_end": morphs_end, "physics": physics}


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp_identity(q, t):
    """slerp from the identity rotation to q by t (q as x, y, z, w)."""
    q = np.asarray(q, dtype=np.float64)
    if q[3] < 0:
        q = -q
    angle = 2.0 * np.arccos(np.clip(q[3], -1.0, 1.0))
    s = np.sqrt(max(1.0 - q[3] * q[3], 0.0))
    if s < 1e-9:
        return np.array([0.0, 0.0, 0.0, 1.0])
    axis = q[:3] / s
    half = angle * t / 2.0
    return np.concatenate([axis * np.sin(half), [np.cos(half)]])


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def skin_matrices(pmx, local):
    """{bone: 4x4 skinning matrix} for the bones a pose moves; local = {bone: (translation, quaternion)}."""
    bl = pmx["bone_list"]
    loc = {b: (np.asarray(t, dtype=np.float64), np.asarray(q, dtype=np.float64)) for b, (t, q) in local.items()}
    # 付与: a grant child takes ratio x its grant parent's rotation / translation (in bone order, so a grant
    # parent's own grant is already in)
    for i, b in enumerate(bl):
        g = b.get("grant")
        if not g or g[0] < 0 or g[0] not in loc:
            continue
        t, q = loc.get(i, (np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0])))
        gt, gq = loc[g[0]]
        if b["flags"] & 0x0100:
            q = quat_mul(slerp_identity(gq, g[1]), q)
        if b["flags"] & 0x0200:
            t = t + gt * g[1]
        loc[i] = (t, q)
    moved = set(loc)
    changed = True
    while changed:                              # children of moved bones move too
        changed = False
        for i, b in enumerate(bl):
            if i not in moved and b["parent"] in moved:
                moved.add(i)
                changed = True
    glob = {}

    def world(i):
        if i in glob:
            return glob[i]
        b = bl[i]
        t, q = loc.get(i, (np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0])))
        m = np.eye(4)
        m[:3, :3] = quat_matrix(q)
        p = b["parent"]
        if 0 <= p < len(bl) and p != i:
            m[:3, 3] = b["pos"] - bl[p]["pos"] + t
            m = world(p) @ m
        else:
            m[:3, 3] = b["pos"] + t
        glob[i] = m
        return m

    out = {}
    for i in moved:
        back = np.eye(4)
        back[:3, 3] = -bl[i]["pos"]
        out[i] = world(i) @ back
    return out


def morph_offsets(pmx, data, morph):
    """{bone: (translation, quaternion)} of a bone morph."""
    s = pmx["sizes"]
    r = Reader(data)
    r.p = morph["body"]
    bfmt = index_fmt(s["bsz"])
    out = {}
    for _ in range(morph["count"]):
        b = r.take(bfmt)
        t = r.take("3f")
        q = r.take("4f")
        if b >= 0:
            out[b] = (t, q)
    return out


def drivers(pmx):
    """Bones whose pose MMD recomputes after the morphs: IK bones, targets and links, physics-driven bones."""
    out = set(pmx["physics"])
    for i, b in enumerate(pmx["bone_list"]):
        if "ik_links" in b:
            out.update([i, b["ik_target"]] + b["ik_links"])
    return out


def vertex_offsets(pmx, skin):
    """(vertex indices, offsets) of the vertices a set of skinning matrices moves."""
    bones, weights = pmx["bones"], pmx["weights"]
    hit = np.isin(bones, list(skin)).any(axis=1)
    idx = np.nonzero(hit)[0]
    if not len(idx):
        return idx, np.zeros((0, 3))
    p = pmx["pos"][idx]
    new = np.zeros_like(p)
    for k in range(4):
        b, w = bones[idx, k], weights[idx, k]
        for bone in np.unique(b[(w != 0) & (b >= 0)]):
            sel = (b == bone) & (w != 0)
            m = skin.get(int(bone))
            q = p[sel] if m is None else p[sel] @ m[:3, :3].T + m[:3, 3]
            new[sel] += w[sel, None] * q
    total = weights[idx].sum(axis=1)
    new += (1.0 - total)[:, None] * p       # weights that do not add up to 1: the rest stays put
    d = new - p
    keep = np.linalg.norm(d, axis=1) > THRESHOLD
    return idx[keep], d[keep]


def convert(data):
    """(new PMX bytes or None when nothing changes, report)."""
    pmx = parse(data)
    s = pmx["sizes"]
    pinned = drivers(pmx)
    vfmt = index_fmt(s["vsz"], True)
    pieces, report = [], {"converted": [], "kept": {}, "max_offset": 0.0,
                          "sdef_vertices": int((pmx["kinds"] == 3).sum())}
    pos = pmx["morphs_at"] + 4
    for m in pmx["morphs"]:
        if m["kind"] != 2:
            continue
        local = morph_offsets(pmx, data, m)
        name = m["name"].decode("utf-16-le" if s["enc"] == 0 else "utf-8", errors="replace")
        skin = skin_matrices(pmx, local)
        if pinned & set(skin):
            report["kept"][name] = "moves IK / physics bones"
            continue
        idx, d = vertex_offsets(pmx, skin)
        if not len(idx):
            report["kept"][name] = "moves no vertex"
            continue
        body = bytearray()
        for i, off in zip(idx.tolist(), d.tolist()):
            body += struct.pack("<" + vfmt + "3f", i, *off)
        record = (struct.pack("<i", len(m["name"])) + m["name"] + struct.pack("<i", len(m["name_e"])) + m["name_e"]
                  + struct.pack("<BBi", m["panel"], 1, len(idx)) + bytes(body))
        pieces.append((m["start"], m["end"], record))
        report["converted"].append(name)
        report["max_offset"] = max(report["max_offset"], float(np.abs(d).max()))
    if not pieces:
        return None, report
    out = bytearray()
    for start, end, record in pieces:
        out += data[pos:start] + record
        pos = end
    out += data[pos:]
    new = data[:pmx["morphs_at"] + 4] + bytes(out)
    check = parse(new)                          # the result reads back with the same morph table
    assert len(check["morphs"]) == len(pmx["morphs"])
    assert all(a["name"] == b["name"] for a, b in zip(check["morphs"], pmx["morphs"]))
    assert data[pmx["morphs_end"]:] == new[check["morphs_end"]:]
    report["max_offset_mm"] = round(report.pop("max_offset") / 12.5 * 1000, 3)
    return new, report


def pmx_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".pmx"):
                        yield os.path.join(root, f)
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--from", dest="listing")
    ap.add_argument("--out")
    ap.add_argument("--backup")
    ap.add_argument("--base")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.listing:
        with open(a.listing, encoding="utf-8") as fh:
            a.paths += [line.strip() for line in fh if line.strip()]
    if not a.paths:
        ap.error("no PMX given")
    files = list(pmx_files(a.paths))
    if a.out and len(files) != 1:
        sys.exit("--out takes one input file")
    if a.backup and not a.base:
        sys.exit("--backup needs --base (the folder the backup paths are relative to)")
    summary = {"files": len(files), "changed": 0, "unchanged": 0, "failed": []}
    for path in files:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            new, rep = convert(data)
        except Exception as exc:                # report it and go on with the next file
            summary["failed"].append("%s: %r" % (path, exc))
            print("FAILED %s: %r" % (path, exc), flush=True)
            continue
        if new is None:
            summary["unchanged"] += 1
            print("same   %s  (no bone morph to convert%s)" % (path, "; kept %d" % len(rep["kept"]) if rep["kept"]
                                                              else ""), flush=True)
            continue
        summary["changed"] += 1
        print("vertex %s  %d morphs, kept %d, max %.3f mm" % (path, len(rep["converted"]), len(rep["kept"]),
                                                             rep["max_offset_mm"]), flush=True)
        if a.dry_run:
            continue
        target = a.out or path
        if a.backup and not a.out:
            keep = os.path.join(a.backup, os.path.relpath(path, a.base))
            os.makedirs(os.path.dirname(keep), exist_ok=True)
            if not os.path.isfile(keep):          # a second run keeps the first original
                shutil.copy2(path, keep)
        temp = target + ".vm.tmp"
        with open(temp, "wb") as fh:
            fh.write(new)
        os.replace(temp, target)
    print("PMX_VERTEX_MORPHS=" + json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
