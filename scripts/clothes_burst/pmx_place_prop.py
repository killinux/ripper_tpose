"""Put a prop (a weapon, a shield ...) somewhere else in a PMX: its materials' vertices and the bones that carry
them are turned and moved as one piece.  Made for ROE Inase's greatsword (pc_a08), which the export leaves standing
on its tip at the origin, right behind her - now planted in the ground at her right.  The 爆衣 tools never touch
it: a prop is not in 衣服非表示_材質.

    python pmx_place_prop.py in.pmx out.pmx --materials "wp_a08_l,wp_a08_r" --at=-6.5,-2,2.5
           [--turn=yaw,back,side] [--floor 0]

(write --at= / --turn= with the equals sign: a value starting with a minus is otherwise taken for an option)

--materials  the prop's materials (comma separated, wildcards).  The bones moved with it: every bone that weights
             the prop's vertices and nothing else, with the bones under it.  A bone that also carries other
             vertices, or a vertex shared with another material, stops the run (moving it would tear the model).
--at         where the pivot goes, in PMX units (x = the model's left, y = up, z = back; 1 unit = 8 cm).  The
             pivot is the bottom middle of the prop: a sword standing on its tip turns about the tip.
--turn       degrees about the pivot, in this order: yaw about the vertical (+ = the edge on the model's left
             comes forward), then lean back (+ = the top goes back), then lean sideways (+ = the top goes to the
             model's right).
--floor      what ends up below this height is laid flat on it: a sword pushed into the ground (--at y < 0)
             comes out of the ground instead of hanging through it - neither MMD (no ground mesh) nor the
             dance videos (the floor shows only shadows) hide what lies below the floor.

The prop's vertex morphs (ROE: 武器非表示, which shrinks it into its bones) move along, and so do the rigid bodies
and joints on the moved bones and the bone morphs that move them.  Prints what it did.
"""
import argparse
import fnmatch
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pmx_nude_switch import pmx_module  # noqa: E402


def rot(r):
    """Rigid / joint rotation (radians) -> matrix in PMX space = Ry @ Rx @ Rz (as mmd_tools reads it; the same
    as scripts/mmd_physics/cloth_collision_pmx.py)."""
    rx, ry, rz = r
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def euler_of(R):
    """rot() inverted."""
    rx = math.asin(max(-1.0, min(1.0, -R[1, 2])))
    if abs(math.cos(rx)) > 1e-6:
        return rx, math.atan2(R[0, 2], R[2, 2]), math.atan2(R[1, 0], R[1, 1])
    return rx, math.atan2(-R[2, 0], R[0, 0]), 0.0


def turn_matrix(yaw, back, side):
    """--turn in degrees -> the matrix: yaw first, then the two leans about the model's own axes."""
    a, b, c = (math.radians(v) for v in (yaw, back, side))
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_quat(M):
    w = math.sqrt(max(0.0, 1.0 + M[0, 0] + M[1, 1] + M[2, 2])) / 2.0
    if w > 1e-6:
        return [(M[2, 1] - M[1, 2]) / (4 * w), (M[0, 2] - M[2, 0]) / (4 * w), (M[1, 0] - M[0, 1]) / (4 * w), w]
    k = int(np.argmax([M[0, 0], M[1, 1], M[2, 2]]))
    i, j = (k + 1) % 3, (k + 2) % 3
    s = math.sqrt(max(0.0, 1.0 + M[k, k] - M[i, i] - M[j, j])) * 2.0
    q = [0.0, 0.0, 0.0, (M[j, i] - M[i, j]) / s]
    q[k], q[i], q[j] = s / 4.0, (M[i, k] + M[k, i]) / s, (M[j, k] + M[k, j]) / s
    return q


def weighted_bones(weight):
    """The bones a vertex really hangs on (weight > 0)."""
    bones, w = weight.bones, weight.weights
    if weight.type == 0:                                  # BDEF1
        pairs = [(bones[0], 1.0)]
    elif weight.type == 1:                                # BDEF2
        pairs = [(bones[0], w[0]), (bones[1], 1.0 - w[0])]
    elif weight.type == 3:                                # SDEF
        pairs = [(bones[0], w.weight), (bones[1], 1.0 - w.weight)]
    else:                                                 # BDEF4 / QDEF
        pairs = list(zip(bones, w))
    return {b for b, x in pairs if b is not None and b >= 0 and x > 0.0}


def material_vertices(model):
    """Per material: the set of vertex indices its faces use."""
    faces = np.array(model.faces).reshape(-1, 3)
    out, start = [], 0
    for mat in model.materials:
        out.append(set(np.unique(faces[start // 3:(start + mat.vertex_count) // 3]).tolist()))
        start += mat.vertex_count
    return out


def place(model, patterns, at, turn=(0.0, 0.0, 0.0), floor=None):
    names = [m.name for m in model.materials]
    pats = [p.strip() for p in patterns.split(",") if p.strip()]
    chosen = []
    for pat in pats:
        hit = [k for k, n in enumerate(names) if fnmatch.fnmatchcase(n, pat)]
        if not hit:
            raise SystemExit("no material matches %r (materials: %s)" % (pat, ", ".join(names)))
        chosen += [k for k in hit if k not in chosen]
    per_mat = material_vertices(model)
    prop = set().union(*(per_mat[k] for k in chosen))
    rest = set().union(*(per_mat[k] for k in range(len(names)) if k not in chosen))
    shared = prop & rest
    if shared:
        raise SystemExit("%d vertices of the prop are used by other materials too" % len(shared))

    carriers, others = set(), set()
    for v, vert in enumerate(model.vertices):
        (carriers if v in prop else others).update(weighted_bones(vert.weight))
    bone_names = [b.name for b in model.bones]
    torn = carriers & others
    if torn:
        raise SystemExit("bones that carry the prop AND other vertices: %s" % ", ".join(bone_names[b] for b in sorted(torn)))
    moved = set(carriers)
    grew = True
    while grew:
        grew = False
        for j, b in enumerate(model.bones):
            if j not in moved and b.parent is not None and b.parent in moved:
                moved.add(j)
                grew = True
    torn = moved & others
    if torn:
        raise SystemExit("bones under the prop carry other vertices: %s" % ", ".join(bone_names[b] for b in sorted(torn)))

    co = np.array([model.vertices[v].co for v in sorted(prop)], float)
    pivot = np.array([(co[:, 0].min() + co[:, 0].max()) / 2.0, co[:, 1].min(), (co[:, 2].min() + co[:, 2].max()) / 2.0])
    R = turn_matrix(*turn)
    at = np.array(at, float)

    def f(p):
        return R @ (np.asarray(p, float) - pivot) + at

    report = {"pivot": pivot.round(3).tolist(), "bbox_before": [co.min(0).round(2).tolist(), co.max(0).round(2).tolist()]}
    # vertex morph targets first, from the untouched positions
    morphs = {}
    for mo in model.morphs:
        if type(mo).__name__ == "VertexMorph":
            hits = [o for o in mo.offsets if o.index in prop]
            if hits:
                morphs[mo.name] = [(o, f(np.array(model.vertices[o.index].co) + np.array(o.offset))) for o in hits]
    flat = 0
    for v in prop:
        vert = model.vertices[v]
        p = f(vert.co)
        if floor is not None and p[1] < floor:
            p[1] = floor
            flat += 1
        vert.co = [float(x) for x in p]
        vert.normal = [float(x) for x in R @ np.array(vert.normal, float)]
        if vert.weight.type == 3:
            sdef = vert.weight.weights
            sdef.c, sdef.r0, sdef.r1 = ([float(x) for x in f(q)] for q in (sdef.c, sdef.r0, sdef.r1))
    for name, items in morphs.items():
        for o, target in items:
            o.offset = [float(x) for x in target - np.array(model.vertices[o.index].co)]
    for j in moved:
        b = model.bones[j]
        b.location = [float(x) for x in f(b.location)]
        if isinstance(b.displayConnection, (list, tuple)):
            b.displayConnection = [float(x) for x in R @ np.array(b.displayConnection, float)]
        if b.axis is not None:
            b.axis = [float(x) for x in R @ np.array(b.axis, float)]
        if b.localCoordinate is not None:
            lc = b.localCoordinate
            lc.x_axis = [float(x) for x in R @ np.array(lc.x_axis, float)]
            lc.z_axis = [float(x) for x in R @ np.array(lc.z_axis, float)]
    warnings = []
    for j, b in enumerate(model.bones):
        links = [l.target for l in (b.ik_links or [])] if b.isIK else []
        if b.isIK and ((j in moved) != (b.target in moved) or any((l in moved) != (j in moved) for l in links)):
            warnings.append("IK %s links the prop with the body" % b.name)
        grant = b.additionalTransform[0] if (b.hasAdditionalRotate or b.hasAdditionalLocation) and b.additionalTransform else None
        if grant is not None and (grant in moved) != (j in moved):
            warnings.append("%s takes the turn / move of %s across the prop's border" % (b.name, bone_names[grant]))
    bodies = set()
    for k, r in enumerate(model.rigids):
        if r.bone in moved:
            bodies.add(k)
            r.location = [float(x) for x in f(r.location)]
            r.rotation = [float(x) for x in euler_of(R @ rot(r.rotation))]
    for jt in model.joints:
        ends = (jt.src_rigid in bodies, jt.dest_rigid in bodies)
        if any(ends) and not all(ends):
            raise SystemExit("joint %s ties a body on the prop to one off it" % jt.name)
        if all(ends):
            jt.location = [float(x) for x in f(jt.location)]
            jt.rotation = [float(x) for x in euler_of(R @ rot(jt.rotation))]
    bone_morphs = []
    for mo in model.morphs:
        if type(mo).__name__ == "BoneMorph":
            for o in mo.offsets:
                if o.index in moved:
                    o.location_offset = [float(x) for x in R @ np.array(o.location_offset, float)]
                    o.rotation_offset = [float(x) for x in matrix_quat(R @ quat_matrix(o.rotation_offset) @ R.T)]
                    bone_morphs.append(mo.name)
    co = np.array([model.vertices[v].co for v in sorted(prop)], float)
    report.update(materials=[names[k] for k in chosen], vertices=len(prop), laid_on_floor=flat,
                  bones=[bone_names[j] for j in sorted(moved)], rigid_bodies=len(bodies),
                  vertex_morphs=sorted(morphs), bone_morphs=sorted(set(bone_morphs)), warnings=warnings,
                  bbox_after=[co.min(0).round(2).tolist(), co.max(0).round(2).tolist()])
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--materials", required=True)
    ap.add_argument("--at", required=True, help="x,y,z of the pivot afterwards (PMX units)")
    ap.add_argument("--turn", default="0,0,0", help="yaw,back,side in degrees")
    ap.add_argument("--floor", type=float, default=None)
    a = ap.parse_args()
    if os.path.abspath(a.src) == os.path.abspath(a.dst):
        raise SystemExit("refusing to overwrite the input; write a new file")
    at = [float(x) for x in a.at.split(",")]
    turn = [float(x) for x in a.turn.split(",")]
    if len(at) != 3 or len(turn) != 3:
        raise SystemExit("--at and --turn take three numbers each")
    pmx = pmx_module()
    model = pmx.load(a.src)
    report = place(model, a.materials, at, turn, a.floor)
    for key, value in report.items():
        print("%s: %s" % (key, value))
    src_dir, out_dir = os.path.dirname(os.path.abspath(a.src)), os.path.dirname(os.path.abspath(a.dst))
    for texture in model.textures:
        local = os.path.join(out_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    pmx.save(a.dst, model, add_uv_count=model.header.additional_uvs)
    print("wrote", a.dst)


if __name__ == "__main__":
    main()
