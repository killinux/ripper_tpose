"""Writes a skeletal mesh read by skelmesh.py as an ActorX .psk that Blender's io_scene_psk_psa (and anything else
that reads UE Viewer exports) imports with the right handedness and joints:

- Y mirrored: positions and normals Y negated, triangle corners 0 and 1 swapped;
- bones: the package stores TRUE local rotations (checked: chained that way every joint lands inside the skin it
  carries, mean 2.9 game units; the ActorX reading - children conjugated - puts the wrist 2.6 m off).  ActorX keeps
  child rotations conjugated (the importer conjugates them back), so the root is written mirrored (x, -y, z, -w) and
  every child as the conjugate of its mirrored rotation (x, -y, z, w).  `joint_check` repeats that measurement on
  every export and the result is in the summary (a wrong convention shows as tens of units);
- points shared like UE Viewer's CVertexShare (same position, normal and influences) -> smooth shading across UV seams;
- RAWWEIGHTS per point, VTXNORMS per point, one MATT entry per material slot that is used;
- 16-bit wedges / faces up to 65536 points and wedges, 32-bit (Wedge32 + FACE3200) above.

    python -I write_psk.py <file.upk> <out.psk> [--mesh name] [--keep-dummy]
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Package  # noqa: E402
import skelmesh  # noqa: E402

JOINT_CHECK_LIMIT = 10.0   # game units: mean distance joint -> weighted centre of its own skin above this = warn


def chunk(name, size, count):
    return struct.pack("<20sIII", name.encode("ascii"), 20100422, size, count)


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _rotate(q, v):
    r = _qmul(_qmul(q, (v[0], v[1], v[2], 0.0)), (-q[0], -q[1], -q[2], q[3]))
    return r[:3]


def joint_positions(bones):
    """World joint positions in game space, local rotations taken as true rotations (parent * local)."""
    out = []
    for i, b in enumerate(bones):
        if i == 0:
            out.append((tuple(b["quat"]), tuple(b["pos"])))
            continue
        pq, pt = out[b["parent"]]
        off = _rotate(pq, b["pos"])
        out.append((_qmul(pq, tuple(b["quat"])), tuple(pt[k] + off[k] for k in range(3))))
    return [p for _q, p in out]


def joint_check(mesh):
    """Mean / max distance (game units) of each skinned joint from the weighted centre of the skin it carries -
    small when the skeleton matches the mesh's bind pose.  Joints carrying < 50 vertices' worth are skipped."""
    acc = {}
    for v, ci in zip(mesh["verts"], mesh["vertex_chunk"]):
        bmap = mesh["chunks"][ci]["bones"]
        for b, w in zip(v["bi"], v["bw"]):
            if w:
                a = acc.setdefault(bmap[b], [0.0, 0.0, 0.0, 0.0])
                for k in range(3):
                    a[k] += v["pos"][k] * w
                a[3] += w
    joints = joint_positions(mesh["bones"])
    errs = {}
    for bi, a in acc.items():
        if a[3] < 50 * 255:
            continue
        c = [a[k] / a[3] for k in range(3)]
        errs[mesh["bones"][bi]["name"]] = math.dist(c, joints[bi])
    if not errs:
        return {"joints": 0}
    worst = max(errs, key=errs.get)
    return {"joints": len(errs), "mean": round(sum(errs.values()) / len(errs), 2), "worst": worst,
            "worst_dist": round(errs[worst], 2)}


def material_name(path):
    return path.split(".")[-1].replace(" ", "_")


def write_psk(mesh, out_path, keep_dummy=False, log=print):
    """mesh = skelmesh.parse() result.  Returns a summary dict."""
    verts, indices, sections, chunks, bones = mesh["verts"], mesh["indices"], mesh["sections"], mesh["chunks"], mesh["bones"]
    names = [material_name(p) for p in mesh["materials"]]
    kept, dropped = [], []
    for s in sections:
        # Mods keep a one-triangle section on the replaced costume's original material (here spidergwen_matv2,
        # hidden inside the head) so the game's material slot 0 still exists; it is not part of the model.
        if not keep_dummy and s["tris"] <= 1:
            dropped.append("%s (%d triangle)" % (names[s["material"]], s["tris"]))
            continue
        kept.append(s)
    used = sorted({s["material"] for s in kept})
    remap = {mi: i for i, mi in enumerate(used)}
    vert_mat = {}
    for s in kept:
        for k in range(3 * s["tris"]):
            vert_mat.setdefault(indices[s["first"] + k], remap[s["material"]])
    vchunk = mesh["vertex_chunk"]
    points, normals, infl_of_point, point_key, wedges, wedge_of = [], [], [], {}, [], {}
    for v in sorted(vert_mat):
        vt = verts[v]
        bmap = chunks[vchunk[v]]["bones"]
        infl = tuple((bmap[b], w) for b, w in zip(vt["bi"], vt["bw"]) if w > 0)
        key = (tuple(vt["pos"]), tuple(round(x, 4) for x in vt["tz"][:3]), infl)
        pi = point_key.get(key)
        if pi is None:
            pi = point_key[key] = len(points)
            points.append(vt["pos"])
            normals.append(vt["tz"][:3])
            infl_of_point.append(infl)
        wedge_of[v] = len(wedges)
        wedges.append((pi, vt["uv"][0][0], vt["uv"][0][1], vert_mat[v]))
    faces = []
    for s in kept:
        for t in range(s["tris"]):
            a, b, c = (wedge_of[indices[s["first"] + 3 * t + j]] for j in range(3))
            faces.append((b, a, c, remap[s["material"]]))
    wide = len(points) > 65536 or len(wedges) > 65536
    buf = bytearray(chunk("ACTRHEAD", 0, 0))
    buf += chunk("PNTS0000", 12, len(points))
    for p in points:
        buf += struct.pack("<3f", p[0], -p[1], p[2])
    buf += chunk("VTXW0000", 16, len(wedges))
    for pi, u, v, mi in wedges:
        buf += struct.pack("<IffI", pi, u, v, mi) if wide else struct.pack("<IffBbh", pi, u, v, mi, 0, 0)
    if wide:
        buf += chunk("FACE3200", 18, len(faces))
        for a, b, c, mi in faces:
            buf += struct.pack("<3IBBi", a, b, c, mi, 0, 1)
    else:
        buf += chunk("FACE0000", 12, len(faces))
        for a, b, c, mi in faces:
            buf += struct.pack("<3HBBi", a, b, c, mi, 0, 1)
    buf += chunk("MATT0000", 88, len(used))
    for mi in used:
        buf += struct.pack("<64siIiIii", names[mi].encode("ascii", "replace")[:63], 0, 0, 0, 0, 0, 0)
    buf += chunk("REFSKELT", 120, len(bones))
    for i, b in enumerate(bones):
        qx, qy, qz, qw = b["quat"]
        px, py, pz = b["pos"]
        # mirrored rotation = (x, -y, z, -w); ActorX children carry its conjugate = (x, -y, z, w)
        q = (qx, -qy, qz, -qw) if i == 0 else (qx, -qy, qz, qw)
        buf += struct.pack("<64sIii4f3f4f", b["name"].encode("ascii", "replace")[:63], 0, b["children"],
                           b["parent"] if i else 0, q[0], q[1], q[2], q[3], px, -py, pz, 0.0, 0.0, 0.0, 0.0)
    weights = [(w / 255.0, pi, bi) for pi, infl in enumerate(infl_of_point) for bi, w in infl]
    buf += chunk("RAWWEIGHTS", 12, len(weights))
    for w, pi, bi in weights:
        buf += struct.pack("<fii", w, pi, bi)
    buf += chunk("VTXNORMS", 12, len(normals))
    for n in normals:
        buf += struct.pack("<3f", n[0], -n[1], n[2])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(buf)
    jc = joint_check(mesh)
    summary = {"psk": out_path, "points": len(points), "wedges": len(wedges), "faces": len(faces),
               "bones": len(bones), "materials": [names[mi] for mi in used], "dropped_sections": dropped,
               "joint_check": jc}
    if jc.get("mean", 0) > JOINT_CHECK_LIMIT:
        log("  WARNING: joints sit %.1f units (mean) from their skin, worst %s %.1f - the skeleton does not match the "
            "mesh; the bone rotation convention of this package may differ" % (jc["mean"], jc["worst"], jc["worst_dist"]))
    else:
        log("  joint check: %d joints, mean %.1f units from their skin (worst %s %.1f)" % (
            jc.get("joints", 0), jc.get("mean", 0), jc.get("worst"), jc.get("worst_dist", 0)))
    log("  PSK %s: %d points, %d wedges, %d faces, %d bones, materials %s%s" % (
        os.path.basename(out_path), len(points), len(wedges), len(faces), len(bones), summary["materials"],
        ("; dropped " + ", ".join(dropped)) if dropped else ""))
    return summary


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    pkg = Package(args[0])
    if "--mesh" in args:
        key = args[args.index("--mesh") + 1]
        idx = int(key) if key.isdigit() else pkg.find(key, "skeletalmesh")
    else:
        idx = max(pkg.of_class("skeletalmesh"), key=lambda i: pkg.exports[i]["size"])
    write_psk(skelmesh.parse(pkg, idx, log=print), args[1], keep_dummy="--keep-dummy" in args)


if __name__ == "__main__":
    main()
