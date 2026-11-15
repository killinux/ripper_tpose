"""SkeletalMesh reader for Marvel Heroes Omega packages (UE3 file version 868): bounds, material slots, reference
skeleton and LOD 0 (sections, index buffer, chunks with their bone maps, GPU-skin vertex buffer).

The native layout is the stock UE3 one (as in UE Viewer's UnMesh3.cpp for this version); it is UE Viewer's property
handling that trips over these packages, not the mesh data.  Every step is checked (see `check`), so a package that
does differ stops with a clear message instead of producing a broken mesh.

    python -I skelmesh.py <file.upk> [mesh name or export index]     prints a summary of the mesh
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Package, Reader  # noqa: E402

RIGID_VERT_SIZE = 61    # FRigidVertex3: pos 12, 3 packed normals 12, 4 UV 32, colour 4, bone 1 (ver >= 710)
SMOOTH_VERT_SIZE = 68   # FSmoothVertex3: pos 12, 3 packed normals 12, 4 UV 32, colour 4, 4 x (bone, weight) 8


class MeshFormatError(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise MeshFormatError(msg)


def half(h):
    return struct.unpack("<e", struct.pack("<H", h))[0]


def unpack_normal(u):
    """FPackedNormal: 4 bytes, each b / 127.5 - 1 (w = binormal sign)."""
    return [((u >> (8 * i)) & 0xFF) / 127.5 - 1.0 for i in range(4)]


def read_bulk_array(r):
    """TArray::BulkSerialize: element size, count, data."""
    elsize = r.i32()
    count = r.i32()
    start = r.p
    check(0 < elsize <= 256 and 0 <= count < 50_000_000, "bad bulk array header (%d x %d)" % (elsize, count))
    r.p += elsize * count
    return elsize, count, start


def bone_map_at(d, q, nbones):
    """True when a plausible chunk bone map (int32 count + int16 bone indices) starts at q."""
    try:
        nbm = struct.unpack_from("<i", d, q)[0]
        if not 0 < nbm <= nbones:
            return False
        return all(0 <= b < nbones for b in struct.unpack_from("<%dh" % nbm, d, q + 4))
    except struct.error:
        return False


def skip_cpu_verts(r, d, count, size, nbones, rigid=False):
    """Skips a chunk's CPU vertex array (cooked UE3 packages keep these) and returns the element size used.

    The size is verified against what follows: for smooth verts the chunk's bone map, for rigid verts the smooth
    vertex count (and the bone map when that count is 0).  If the stock size does not fit, sizes 40..119 are tried."""
    def fits(es):
        q = r.p + es * count
        if not rigid:
            return bone_map_at(d, q, nbones)
        try:
            nsm = struct.unpack_from("<i", d, q)[0]
        except struct.error:
            return False
        return nsm == 0 and bone_map_at(d, q + 4, nbones) or 0 < nsm < 1_000_000
    if fits(size):
        r.p += size * count
        return size
    for es in range(40, 120):
        if fits(es):
            r.p += es * count
            return es
    raise MeshFormatError("CPU vertex array of %d entries: element size not found" % count)


def parse(pkg, idx, log=None):
    """Export `idx` (0-based) -> dict with materials, bones, sections, chunks, verts, indices, notes."""
    log = log or (lambda s: None)
    d = pkg.data
    out = {"name": pkg.exports[idx]["name"], "path": pkg.obj_path(idx + 1), "notes": []}
    props, pos = pkg.object_props(idx)
    out["props"] = {p[0]: p[5] for p in props if p[1] not in ("ArrayProperty", "StructProperty")}
    r = Reader(d, pos)
    out["bounds"] = struct.unpack_from("<7f", d, r.p)
    r.p += 28
    n = r.i32()
    check(0 <= n < 256, "material count %d" % n)
    out["materials"] = [pkg.obj_path(r.i32()) for _ in range(n)]
    r.p += 24  # MeshOrigin, RotOrigin
    nb = r.i32()
    check(0 < nb < 2048, "bone count %d" % nb)
    bones = []
    for _ in range(nb):
        name = pkg.fname(r)
        r.u32()  # flags
        q = struct.unpack_from("<4f", d, r.p)
        t = struct.unpack_from("<3f", d, r.p + 16)
        r.p += 28
        children = r.i32()
        parent = r.i32()
        r.u32()  # bone colour
        check(0 <= parent < nb, "bone %s parent %d" % (name, parent))
        bones.append({"name": name, "quat": q, "pos": t, "parent": parent, "children": children})
    out["bones"] = bones
    out["depth"] = r.i32()
    nlod = r.i32()
    check(nlod >= 1, "no LODs")
    out["lods"] = nlod
    log("%s: %d materials, %d bones, %d LODs" % (out["path"], n, nb, nlod))
    # ---- LOD 0
    nsec = r.i32()
    check(0 < nsec < 512, "section count %d" % nsec)
    secs = []
    for _ in range(nsec):
        mi, ci = struct.unpack_from("<hh", d, r.p)
        first, ntri = struct.unpack_from("<ii", d, r.p + 4)
        secs.append({"material": mi, "chunk": ci, "first": first, "tris": ntri, "sort": d[r.p + 12]})
        r.p += 13
    out["sections"] = secs
    r.i32()  # NeedsCPUAccess
    r.u8()   # DataTypeSize
    ielsize, icount, istart = read_bulk_array(r)
    check(ielsize in (2, 4), "index size %d" % ielsize)
    check(sum(3 * s["tris"] for s in secs) <= icount, "sections need more indices than the buffer has")
    n_used = r.i32()
    r.p += 2 * n_used  # active bone indices
    nchunk = r.i32()
    check(0 < nchunk < 512, "chunk count %d" % nchunk)
    chunks = []
    for ci in range(nchunk):
        first = r.i32()
        nrig = r.i32()
        if nrig:
            es = skip_cpu_verts(r, d, nrig, RIGID_VERT_SIZE, nb, rigid=True)
            if es != RIGID_VERT_SIZE:
                out["notes"].append("chunk %d rigid CPU vertex size %d (expected %d)" % (ci, es, RIGID_VERT_SIZE))
        nsm = r.i32()
        if nsm:
            es = skip_cpu_verts(r, d, nsm, SMOOTH_VERT_SIZE, nb)
            if es != SMOOTH_VERT_SIZE:
                out["notes"].append("chunk %d smooth CPU vertex size %d (expected %d)" % (ci, es, SMOOTH_VERT_SIZE))
        nbm = r.i32()
        bmap = list(struct.unpack_from("<%dh" % nbm, d, r.p))
        r.p += 2 * nbm
        nrv, nsv, maxinf = r.i32(), r.i32(), r.i32()
        check(all(0 <= b < nb for b in bmap), "chunk %d bone map out of range" % ci)
        check(0 < maxinf <= 8, "chunk %d max influences %d" % (ci, maxinf))
        chunks.append({"first": first, "bones": bmap, "rigid": nrv, "smooth": nsv, "maxinf": maxinf})
    out["chunks"] = chunks
    r.i32()  # Size
    nverts = r.i32()
    nreq = r.i32()
    r.p += nreq  # RequiredBones
    # RawPointIndices (FIntBulkData): flags, element count, size on disk, offset in file, [inline data]
    bflags = r.i32()
    r.i32()
    bsize = r.i32()
    r.i32()
    if not (bflags & 0x1) and not (bflags & 0x20) and bsize > 0:
        r.p += bsize
    r.i32()  # NumTexCoords
    nuv = r.i32()
    full_uv = r.i32()
    packed = r.i32()
    ext = struct.unpack_from("<3f", d, r.p)
    org = struct.unpack_from("<3f", d, r.p + 12)
    r.p += 24
    elsize, vcount, vstart = read_bulk_array(r)
    expect = 16 + (4 if packed else 12) + nuv * (8 if full_uv else 4)
    check(elsize == expect, "GPU vertex size %d, expected %d (uv sets %d, full uv %d, packed %d)" % (
        elsize, expect, nuv, full_uv, packed))
    check(vcount == nverts, "vertex buffer has %d vertices, LOD says %d" % (vcount, nverts))
    check(sum(c["rigid"] + c["smooth"] for c in chunks) == vcount, "chunks do not cover the vertex buffer")
    log("  LOD 0: %d sections, %d indices, %d chunks, %d vertices (%d bytes, %d UV sets)" % (
        nsec, icount, nchunk, vcount, elsize, nuv))
    verts = []
    for i in range(vcount):
        p = vstart + i * elsize
        tx, tz = struct.unpack_from("<II", d, p)
        bi = list(d[p + 8:p + 12])
        bw = list(d[p + 12:p + 16])
        q = p + 16
        if packed:
            pv = struct.unpack_from("<I", d, q)[0]
            q += 4
            x = ((pv & 0x7FF) - 1023.0) / 1023.0
            y = (((pv >> 11) & 0x7FF) - 1023.0) / 1023.0
            z = (((pv >> 22) & 0x3FF) - 511.0) / 511.0
            pos = [org[0] + x * ext[0], org[1] + y * ext[1], org[2] + z * ext[2]]
        else:
            pos = list(struct.unpack_from("<3f", d, q))
            q += 12
        uvs = []
        for _ in range(nuv):
            if full_uv:
                uvs.append(list(struct.unpack_from("<2f", d, q)))
                q += 8
            else:
                hu, hv = struct.unpack_from("<HH", d, q)
                uvs.append([half(hu), half(hv)])
                q += 4
        verts.append({"pos": pos, "tx": unpack_normal(tx), "tz": unpack_normal(tz), "bi": bi, "bw": bw, "uv": uvs})
    out["verts"] = verts
    out["indices"] = list(struct.unpack_from("<%d%s" % (icount, "H" if ielsize == 2 else "I"), d, istart))
    check(max(out["indices"]) < vcount, "index past the vertex buffer")
    bad_w = sum(1 for v in verts if abs(sum(v["bw"]) - 255) > 2)
    check(bad_w == 0, "%d vertices whose weights do not add up to 255" % bad_w)
    # every vertex's chunk (its bone indices index the chunk's bone map)
    for c in chunks:
        for v in range(c["first"], c["first"] + c["rigid"] + c["smooth"]):
            for b, w in zip(verts[v]["bi"], verts[v]["bw"]):
                check(w == 0 or b < len(c["bones"]), "vertex %d bone %d outside its chunk's bone map" % (v, b))
    out["vertex_chunk"] = [None] * vcount
    for ci, c in enumerate(chunks):
        for v in range(c["first"], c["first"] + c["rigid"] + c["smooth"]):
            out["vertex_chunk"][v] = ci
    out["uv_sets"] = nuv
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pkg = Package(sys.argv[1])
    meshes = pkg.of_class("skeletalmesh")
    if len(sys.argv) > 2:
        key = sys.argv[2]
        idx = int(key) if key.isdigit() else pkg.find(key, "skeletalmesh")
    else:
        idx = max(meshes, key=lambda i: pkg.exports[i]["size"])
    m = parse(pkg, idx, log=print)
    for s in m["sections"]:
        print("  section: material %d %-50s %6d triangles" % (s["material"], m["materials"][s["material"]], s["tris"]))
    pos = [v["pos"] for v in m["verts"]]
    print("  bounds: x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % (
        min(p[0] for p in pos), max(p[0] for p in pos), min(p[1] for p in pos), max(p[1] for p in pos),
        min(p[2] for p in pos), max(p[2] for p in pos)))
    for n in m["notes"]:
        print("  note:", n)


if __name__ == "__main__":
    main()
