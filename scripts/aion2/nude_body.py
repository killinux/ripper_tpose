"""AION2 nude body - the Blender side of export_model.py <G>_Nude (called by build_blend.py).

Why it is built this way is in nude_survey.py: the body is ONE costume's skin (default the underwear set, Body +
Pants welded at the waist) and each of its openings except the neck gets a cap:
  1. filled, triangulated, refined to ~EDGE cm edges and relaxed into a smooth membrane;
  2. shaped onto a guide surface, rays along the vertex normal both ways, the guide-to-rim offset measured on the
     rim and spread over the cap by inverse squared distance (so the cap meets the rim exactly), relaxed, 4 rounds:
       - the other costumes' skin when it covers SKIN_SHARE of the cap within SKIN_REACH (the cups: it IS the body);
       - else the shop mannequin (the bikini area, which no costume shows);
  3. textured: a cap whose rim stays inside one UV island (rim UVs span < UV_COMPACT) keeps the UVs interpolated
     across it; otherwise its faces get the material <skin>_fill whose colour is a vertex colour "fill_color":
     the skin texture sampled at the rim, diffused inwards - no seam in colour at the rim, no stretched texture.
The face attribute "nude_fill" (> 0) marks the caps (select them in Edit mode to repaint / sculpt).
"""
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

WELD = 0.001          # cm: Body / Pants of one set share their waist seam exactly
EDGE = 0.9            # cm: cap edge length after refining
SKIN_REACH = 3.0      # cm
SKIN_SHARE = 0.9
MANNEQUIN_REACH = 8.0  # cm
UV_COMPACT = 0.3
ROUNDS = 4


def boundary_loops(bm):
    bnd = [e for e in bm.edges if e.is_boundary]
    adj = {}
    for e in bnd:
        for v in e.verts:
            adj.setdefault(v, []).append(e)
    seen, loops = set(), []
    for e in bnd:
        if e in seen:
            continue
        loop, stack = [], [e]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            loop.append(x)
            for v in x.verts:
                stack.extend(y for y in adj[v] if y not in seen)
        loops.append(loop)
    return loops


def bvh_of(tris):
    tris = np.asarray(tris, dtype=np.float64)
    verts = tris.reshape(-1, 3).tolist()
    return BVHTree.FromPolygons(verts, np.arange(len(verts)).reshape(-1, 3).tolist())


class SkinGuides:
    """The other costumes' skin near the openings, one BVH per part (nude_survey.py writes them)."""

    def __init__(self, path):
        self.data = dict(np.load(path)) if path and os.path.isfile(path) else {}
        self.cache = {}

    def bvh(self, stem):
        if stem not in self.cache:
            self.cache[stem] = bvh_of(self.data[stem])
        return self.cache[stem]

    def best(self, mw, rim_verts, inner_verts, log, top=5):
        """The part whose surface passes closest to the rim (mean distance) among those covering the cap."""
        if not self.data or not rim_verts:
            return None, 0.0, None
        rim = [mw @ v.co for v in rim_verts]
        ranked = []
        for stem in self.data:
            b = self.bvh(stem)
            ds = [b.find_nearest(p)[3] for p in rim]
            ds = [d for d in ds if d is not None]
            if len(ds) > 0.8 * len(rim):
                ranked.append((float(np.mean(ds)), stem))
        ranked.sort()
        for off, stem in ranked[:top]:
            share = coverage(self.bvh(stem), mw, inner_verts, SKIN_REACH)
            if share >= SKIN_SHARE:
                return stem, share, off
        return None, (coverage(self.bvh(ranked[0][1]), mw, inner_verts, SKIN_REACH) if ranked else 0.0), None


def bvh_from_psks(paths):
    verts, polys = [], []
    for path in [p for p in paths or [] if os.path.isfile(p)]:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.psk(filepath=path, should_import_mesh=True, should_import_skeleton=True,
                                 should_import_materials=False)
        created = [o for o in bpy.data.objects if o not in before]
        for o in created:
            if o.type == "MESH":
                base = len(verts)
                verts += [tuple(o.matrix_world @ v.co) for v in o.data.vertices]
                polys += [[base + i for i in p.vertices] for p in o.data.polygons]
        for o in created:
            bpy.data.objects.remove(o, do_unlink=True)
    return BVHTree.FromPolygons(verts, polys) if polys else None


def ray_hit(guide, p, n, reach):
    best = None
    for d in (n, -n):
        hit = guide.ray_cast(p, d, reach)
        if hit[0] is not None and (best is None or hit[3] < best[1]):
            best = (hit[0], hit[3])
    return best[0] if best else None


def coverage(guide, mw, verts, reach):
    if guide is None or not verts:
        return 0.0
    rot = mw.to_3x3()
    hits = sum(1 for v in verts if ray_hit(guide, mw @ v.co, (rot @ v.normal).normalized(), reach) is not None)
    return hits / len(verts)


def snap(guide, mw, inner, rim, reach):
    """Inner vertices onto the guide + the rim's guide offset spread by inverse squared distance."""
    inv = mw.inverted()
    rot = mw.to_3x3()
    rim_p, rim_o = [], []
    for v in rim:
        p = mw @ v.co
        q = guide.find_nearest(p)[0]
        if q is not None:
            rim_p.append(p)
            rim_o.append(p - q)
    if not rim_p:
        return
    rp = np.array([tuple(p) for p in rim_p])
    ro = np.array([tuple(o) for o in rim_o])
    for v in inner:
        p = mw @ v.co
        q = ray_hit(guide, p, (rot @ v.normal).normalized(), reach)
        if q is None:
            q = guide.find_nearest(p)[0]
        if q is None:
            continue
        w = 1.0 / np.maximum(((rp - np.array(tuple(p))) ** 2).sum(axis=1), 1e-3)
        off = (ro * w[:, None]).sum(axis=0) / w.sum()
        v.co = inv @ (q + Vector(off))


PATCH_GAP = 0.4        # cm left between the rim and a mannequin patch, closed by bridging the two loops
PATCH_RAY = 1.6        # cm: a mannequin face finding no skin along its normal this far is over the opening
PATCH_NEAR = 1.0       # cm: ... and the rim is at most this much farther than its nearest skin
PATCH_SIDE = 0.15      # cm: or its nearest skin point is on the rim
BRIDGE = "zipper"      # "zipper" (zipper_stitch: both loops split at each other's arc-length parameters and
                       # welded), "stitch" (stitch_patch: vertex counts equalised and paired by index - sheared where
                       # the spacing differs), "bmesh" (bmesh.ops.bridge_loops: twisted at the crotch), "strip"
                       # (strip_bridge: long triangles folded up when relaxed) - all tried on 10-25


def import_mannequin(paths):
    """The mannequin parts as one mesh object (its own armature removed; vertex groups keep the bone names)."""
    objs, arms = [], []
    for path in [p for p in paths or [] if os.path.isfile(p)]:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.psk(filepath=path, should_import_mesh=True, should_import_skeleton=True,
                                 should_import_materials=False, should_import_vertex_normals=False)
        for o in bpy.data.objects:
            if o not in before:
                (objs if o.type == "MESH" else arms).append(o)
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    m = objs[0]
    for mod in list(m.modifiers):
        m.modifiers.remove(mod)
    world = m.matrix_world.copy()
    m.parent = None
    m.matrix_world = world
    for a in arms:
        bpy.data.objects.remove(a, do_unlink=True)
    return m


def seg_dist(points, a, b):
    """Distance of each point (n, 3) to the closest of the segments a-b (m, 3)."""
    ab = b - a
    best = np.full(len(points), np.inf)
    for i in range(0, len(a), 64):
        aa, bb = a[i:i + 64], ab[i:i + 64]
        ap = points[:, None, :] - aa[None]
        t = np.clip((ap * bb[None]).sum(-1) / np.maximum((bb * bb).sum(-1), 1e-12)[None], 0, 1)
        d = np.linalg.norm(ap - t[..., None] * bb[None], axis=-1).min(axis=1)
        best = np.minimum(best, d)
    return best


def mannequin_patch(body, rim_world, rim_edges_world, mannequin_paths, cid, log, guides=None):
    """Cut the mannequin's faces over one opening, move them onto the body's level, join them into `body` and
    bridge them to the rim.  Returns the number of faces added."""
    m = import_mannequin(mannequin_paths)
    if m is None:
        return 0
    deps = bpy.context.evaluated_depsgraph_get()
    skin = BVHTree.FromObject(body, deps)
    mw = m.matrix_world
    bm = bmesh.new()
    bm.from_mesh(m.data)
    bm.normal_update()
    rot = mw.to_3x3()
    cents = np.array([tuple(mw @ f.calc_center_median()) for f in bm.faces])
    # a mannequin face is over the opening when no skin lies along its normal (both ways) within PATCH_RAY: under
    # the skin it always finds it 0.7-1.4 cm away.  (A nearest-point test lost the crotch, where the inner thighs
    # are nearer than the rim, and the bridge twisted there - 10-25.)
    covered = np.array([ray_hit(skin, Vector(c), (rot @ f.normal).normalized(), PATCH_RAY) is not None
                        for c, f in zip(cents, bm.faces)])
    d_skin = np.array([(Vector(c) - skin.find_nearest(Vector(c))[0]).length for c in cents])
    a = np.array([e[0] for e in rim_edges_world])
    b = np.array([e[1] for e in rim_edges_world])
    d_rim = seg_dist(cents, a, b)
    # ...and its nearest skin is (about) the rim: where the mannequin sits more than PATCH_RAY under the skin the
    # ray alone let pieces through at the back of the waist (shards poking out, 10-25)
    near_rim = d_rim - d_skin < PATCH_SIDE           # its nearest skin is the rim (the first rule)
    open_ray = ~covered & (d_rim - d_skin < PATCH_NEAR)   # or no skin along its normal (the crotch)
    over = (near_rim | open_ray) & (d_rim > PATCH_GAP) & (d_rim < 30.0)
    faces = list(bm.faces)
    keep = {faces[i] for i in np.nonzero(over)[0]}
    # largest connected piece (edge-adjacent)
    best, seen = [], set()
    for f in keep:
        if f in seen:
            continue
        comp, stack = [], [f]
        seen.add(f)
        while stack:
            x = stack.pop()
            comp.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y in keep and y not in seen:
                        seen.add(y)
                        stack.append(y)
        if len(comp) > len(best):
            best = comp
    keep = set(best)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # holes inside the piece (faces that failed the test) are closed; only the outer loop is bridged
    loops = boundary_loops(bm)
    if len(loops) > 1:
        outer = max(loops, key=lambda l: sum(e.calc_length() for e in l))
        for l in loops:
            if l is not outer:
                bmesh.ops.holes_fill(bm, edges=l, sides=0)
    # move the piece onto the body's level: the rim's offset to the mannequin, spread by inverse squared distance
    rim_p = np.array(rim_world)
    full = import_mannequin(mannequin_paths)
    fb = BVHTree.FromObject(full, bpy.context.evaluated_depsgraph_get())
    offs = np.array([tuple(Vector(r) - fb.find_nearest(Vector(r))[0]) for r in rim_world])
    bpy.data.objects.remove(full, do_unlink=True)
    inv = mw.inverted()
    for v in bm.verts:
        p = np.array(tuple(mw @ v.co))
        w = 1.0 / np.maximum(((rim_p - p) ** 2).sum(axis=1), 1e-3)
        v.co = inv @ Vector(p + (offs * w[:, None]).sum(axis=0) / w.sum())
    tag = bm.faces.layers.int.get("nude_fill") or bm.faces.layers.int.new("nude_fill")
    for f in bm.faces:
        f[tag] = cid
    n_patch = len(bm.faces)
    bm.to_mesh(m.data)
    bm.free()
    # join into the body and bridge the patch's outer loop to the rim
    bpy.ops.object.select_all(action="DESELECT")
    m.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    me = body.data
    bm = bmesh.new()
    bm.from_mesh(me)
    tag = bm.faces.layers.int.get("nude_fill")
    loops = boundary_loops(bm)
    rim_set = {tuple(round(c, 3) for c in p) for p in rim_world}
    bw = body.matrix_world

    def rim_score(l):
        vs = {v for e in l for v in e.verts}
        return sum(1 for v in vs if tuple(round(c, 3) for c in (bw @ v.co)) in rim_set) / max(1, len(vs))

    rim_loop = max(loops, key=rim_score)
    patch_loops = [l for l in loops if all(lf[tag] == cid for e in l for lf in e.link_faces)]
    if not patch_loops:
        bm.to_mesh(me)
        bm.free()
        log("  mannequin patch: no outer loop to bridge")
        return n_patch
    patch_loop = max(patch_loops, key=lambda l: sum(e.calc_length() for e in l))
    if BRIDGE == "zipper":
        zipper_stitch(bm, rim_loop, patch_loop, tag, cid)
        new = []
        refit = refit_to_skin(bm, body.matrix_world, tag, cid, guides, log)
        if refit:
            log("  mannequin patch pulled onto %s" % refit)
        # where the patch narrows into a strip (between the buttocks, between the legs) the mannequin's few faces
        # leave pockets and a ridge: relax the whole inside of the patch (seam fixed); the wings keep their shape,
        # skin holds them on both sides
        inside = list({v for f in bm.faces if f[tag] == cid for v in f.verts
                       if all(lf[tag] == cid for lf in v.link_faces)})
        for _ in range(PATCH_RELAX):
            bmesh.ops.smooth_vert(bm, verts=inside, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        seam = {v for f in bm.faces if f[tag] == cid for v in f.verts if any(lf[tag] != cid for lf in v.link_faces)}
        ring = set(seam)
        for _ in range(2):
            ring |= {w for v in ring for e in v.link_edges for w in e.verts}
        for _ in range(8):
            bmesh.ops.smooth_vert(bm, verts=list(seam), factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
            bmesh.ops.smooth_vert(bm, verts=list(ring - seam), factor=0.25, use_axis_x=True, use_axis_y=True,
                                  use_axis_z=True)
    elif BRIDGE == "stitch":
        ok = stitch_patch(bm, rim_loop, patch_loop, tag, cid,
                          lambda: max([l for l in boundary_loops(bm) if not all(lf[tag] == cid for e in l for lf in e.link_faces)],
                                      key=rim_score))
        if not ok:
            log("  mannequin patch: could not equalise the loops, bridging instead")
        new = [] if ok else bmesh.ops.bridge_loops(bm, edges=rim_loop + patch_loop).get("faces", [])
        if ok:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
            refit = refit_to_skin(bm, body.matrix_world, tag, cid, guides, log)
            if refit:
                log("  mannequin patch pulled onto %s" % refit)
            # the base costume cut its garment edge as a sawtooth (hidden by the strap in game): smooth the seam
            # and two rings either side, the seam hardest
            seam = {v for f in bm.faces if f[tag] == cid for v in f.verts if any(lf[tag] != cid for lf in v.link_faces)}
            ring = set(seam)
            for _ in range(2):
                ring |= {w for v in ring for e in v.link_edges for w in e.verts}
            for _ in range(8):
                bmesh.ops.smooth_vert(bm, verts=list(seam), factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
                bmesh.ops.smooth_vert(bm, verts=list(ring - seam), factor=0.25, use_axis_x=True, use_axis_y=True,
                                      use_axis_z=True)
    elif BRIDGE == "strip":
        new = strip_bridge(bm, ordered(rim_loop), ordered(patch_loop))
    else:
        new = bmesh.ops.bridge_loops(bm, edges=rim_loop + patch_loop).get("faces", [])
    for f in new:
        f[tag] = cid
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    # relax the seam: three rings into the patch, then - gently - the rim and one ring of skin, so no step is left
    band = {v for f in new for v in f.verts} | {v for f in bm.faces if f[tag] == cid for v in f.verts
                                                  if any(lf[tag] != cid for lf in v.link_faces)}
    for _ in range(3):
        band |= {w for v in band for e in v.link_edges for w in e.verts
                 if all(lf[tag] == cid for lf in w.link_faces)}
    inner = [v for v in band if all(lf[tag] == cid for lf in v.link_faces)]
    for _ in range(12):
        bmesh.ops.smooth_vert(bm, verts=inner, factor=0.4, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    rim_ring = {v for v in band if any(lf[tag] != cid for lf in v.link_faces)}
    rim_ring |= {w for v in rim_ring for e in v.link_edges for w in e.verts}
    for _ in range(4):
        bmesh.ops.smooth_vert(bm, verts=list(rim_ring), factor=0.25, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bmesh.ops.smooth_vert(bm, verts=inner, factor=0.3, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(me)
    bm.free()
    return n_patch + len(new)


REFIT_REACH = 2.5      # cm: patch vertices this close (along the normal) to a costume's skin are pulled onto it
REFIT_PULL = 0.7
REFIT_FADE = 2.0       # cm from the seam over which the pull fades in
PATCH_RELAX = 15       # relax passes over the whole inside of a mannequin patch after it is stitched and refitted
PATCH_EDGE = 1.0       # cm: the mannequin is coarse (27 inner vertices over the bikini area) - refined to this first


def refit_to_skin(bm, mw, tag, cid, guides, log):
    """Where some costume does show the skin inside the opening (thongs show the upper buttocks), pull the patch
    onto that real surface - the mannequin's own buttocks are smaller and left a hollow above them (10-25).  One
    part, the one covering most of the patch, so the surface stays consistent."""
    for _ in range(4):                   # refine the patch inside (never its seam edges: no T-junction with the skin)
        edges = list({e for f in bm.faces if f[tag] == cid for e in f.edges if len(e.link_faces) == 2
                      and all(lf[tag] == cid for lf in e.link_faces) and e.calc_length() > PATCH_EDGE})
        if not edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if f[tag] == cid and len(f.verts) > 3])
    if guides is None or not guides.data:
        return None
    inner = [v for f in bm.faces if f[tag] == cid for v in f.verts if all(lf[tag] == cid for lf in v.link_faces)]
    inner = list(set(inner))
    if not inner:
        return None
    bm.normal_update()
    best, best_cov = None, 0.0
    for stem in guides.data:
        cov = coverage(guides.bvh(stem), mw, inner, REFIT_REACH)
        if cov > best_cov:
            best, best_cov = stem, cov
    if best is None or best_cov < 0.1:
        return None
    b = guides.bvh(best)
    inv = mw.inverted()
    rot = mw.to_3x3()
    # pull fades in over REFIT_FADE from the seam: that costume's skin sits a few mm off the base skin, a full pull
    # right next to the seam folded thin triangles over it (a dark zigzag along the bikini line, 10-25)
    from mathutils.kdtree import KDTree
    seam = [v for f in bm.faces if f[tag] == cid for v in f.verts if any(lf[tag] != cid for lf in v.link_faces)]
    kd = KDTree(len(seam))
    for i, v in enumerate(seam):
        kd.insert(v.co, i)
    kd.balance()
    weight = {v: REFIT_PULL * min(kd.find(v.co)[2] / REFIT_FADE, 1.0) ** 2 for v in inner}
    for _ in range(3):
        bm.normal_update()
        for v in inner:
            hit = ray_hit(b, mw @ v.co, (rot @ v.normal).normalized(), REFIT_REACH)
            if hit is not None:
                v.co = v.co.lerp(inv @ hit, weight[v])
        for _ in range(3):
            bmesh.ops.smooth_vert(bm, verts=inner, factor=0.3, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    return "%s (%.0f%% of the patch)" % (best, 100 * best_cov)


def loop_params(vs):
    """Cumulative arc length of a closed loop, normalised: len(vs) + 1 values, 0 .. 1."""
    d = [0.0]
    for i in range(1, len(vs) + 1):
        d.append(d[-1] + (vs[i % len(vs)].co - vs[i - 1].co).length)
    total = d[-1] or 1.0
    return [x / total for x in d]


def point_at(vs, ts, t):
    """The point of the closed polyline vs (params ts) at parameter t."""
    import bisect
    k = min(max(bisect.bisect_right(ts, t) - 1, 0), len(vs) - 1)
    span = ts[k + 1] - ts[k]
    f = 0.0 if span <= 0 else (t - ts[k]) / span
    return vs[k].co.lerp(vs[(k + 1) % len(vs)].co, f)


def split_at(bm, vs, ts, insert):
    """Split the edges of the closed loop vs (params ts) at the parameters `insert`, each new vertex placed at
    `insert[t]` (a position).  Returns {t: new vertex}."""
    import bisect
    out = {}
    by_seg = {}
    for t, pos in insert.items():
        k = min(max(bisect.bisect_right(ts, t) - 1, 0), len(vs) - 1)
        if t - ts[k] < 1e-6 or ts[k + 1] - t < 1e-6:
            continue                            # lands on an existing vertex
        by_seg.setdefault(k, []).append((t, pos))
    for k, items in by_seg.items():
        a, b = vs[k], vs[(k + 1) % len(vs)]
        prev, t_prev = a, ts[k]
        edge = next((e for e in a.link_edges if b in e.verts), None)
        for t, pos in sorted(items):
            if edge is None:
                break
            fac = (t - t_prev) / max(ts[k + 1] - t_prev, 1e-9)
            _ne, nv = bmesh.utils.edge_split(edge, prev, fac)
            nv.co = pos
            out[t] = nv
            edge = next((e for e in nv.link_edges if b in e.verts), None)
            prev, t_prev = nv, t
    return out


def zipper_stitch(bm, rim_loop, patch_loop, tag, cid):
    """Close the gap between a patch's outer loop and the rim like a zipper: both loops parameterised by arc length
    (aligned start, same direction); the patch boundary moves onto the rim polyline at its own parameters, its
    inside follows harmonically; each loop is split at the other's parameters; the coincident pairs are welded.
    (Pairing by index after equalising the vertex counts sheared the patch where the two loops' spacing differs:
    crinkles on one side of the back, 10-25.)"""
    rim = ordered(rim_loop)
    patch = align(rim, ordered(patch_loop))
    tr, tp = loop_params(rim), loop_params(patch)
    # monotonic correspondence by dynamic time warping on the distances (the patch's outline is not the rim's:
    # matching by arc length alone slid the whole patch along the rim and folded it - 10-25)
    n, m = len(rim), len(patch)
    R = np.array([tuple(v.co) for v in rim + [rim[0]]])
    P = np.array([tuple(v.co) for v in patch + [patch[0]]])
    C = np.linalg.norm(R[:, None, :] - P[None, :, :], axis=2)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = C[0, 0]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            best = min(D[i - 1, j] if i else np.inf, D[i, j - 1] if j else np.inf,
                       D[i - 1, j - 1] if i and j else np.inf)
            D[i, j] = C[i, j] + best
    i, j, path = n, m, [(n, m)]
    while i or j:
        steps = []
        if i and j:
            steps.append((D[i - 1, j - 1], i - 1, j - 1))
        if i:
            steps.append((D[i - 1, j], i - 1, j))
        if j:
            steps.append((D[i, j - 1], i, j - 1))
        _d, i, j = min(steps)
        path.append((i, j))
    on_rim = {}
    for i, j in path:
        on_rim.setdefault(j, []).append(tr[i])
    s = [float(np.mean(on_rim[j])) for j in range(m)]
    for j in range(1, m):                      # strictly increasing, so no two patch vertices meet on the rim
        s[j] = max(s[j], s[j - 1] + 1e-4)
    s = [min(x, 1.0 - 1e-4 * (m - j)) for j, x in enumerate(s)]
    targets = {p: point_at(rim, tr, s[j]) for j, p in enumerate(patch)}
    tp = s + [1.0]                             # the patch's parameters ARE its rim positions from here on
    verts = list({v for f in bm.faces if f[tag] == cid for v in f.verts})
    idx = {v: i for i, v in enumerate(verts)}
    disp = np.zeros((len(verts), 3))
    fixed = np.zeros(len(verts), bool)
    for p, t in targets.items():
        disp[idx[p]] = np.array(tuple(t - p.co))
        fixed[idx[p]] = True
    pairs = np.array([(idx[e.verts[0]], idx[e.verts[1]]) for e in {e for v in verts for e in v.link_edges}
                      if e.verts[0] in idx and e.verts[1] in idx])
    for _ in range(600):
        s = np.zeros_like(disp)
        c = np.zeros(len(verts))
        np.add.at(s, pairs[:, 0], disp[pairs[:, 1]])
        np.add.at(c, pairs[:, 0], 1)
        np.add.at(s, pairs[:, 1], disp[pairs[:, 0]])
        np.add.at(c, pairs[:, 1], 1)
        upd = ~fixed & (c > 0)
        disp[upd] = s[upd] / c[upd, None]
    for v in verts:
        v.co = v.co + Vector(disp[idx[v]])
    # split each loop at the other's parameters (positions on the rim polyline), then weld everything coincident
    split_at(bm, rim, tr, {tp[j]: point_at(rim, tr, tp[j]) for j in range(len(patch))})
    split_at(bm, patch, tp, {tr[k]: rim[k].co.copy() for k in range(len(rim))})
    seam = [v for v in bm.verts if v.is_valid and v.is_boundary]
    bmesh.ops.remove_doubles(bm, verts=seam, dist=0.0005)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    return True


def align(rim, patch):
    """Rotate / reverse the patch loop so patch[0] is nearest rim[0] and both run the same way."""
    j0 = min(range(len(patch)), key=lambda j: (patch[j].co - rim[0].co).length)
    fwd = patch[j0:] + patch[:j0]
    rev = [patch[j0]] + list(reversed(patch[:j0])) + list(reversed(patch[j0 + 1:]))

    def mismatch(p):
        n, m = len(rim), len(p)
        return sum((rim[int(k * n / 16)].co - p[int(k * m / 16)].co).length for k in range(1, 16))

    return fwd if mismatch(fwd) <= mismatch(rev) else rev


def stitch_patch(bm, rim_loop, patch_loop, tag, cid, find_rim):
    """Give the patch's outer loop exactly the rim's vertex count, pair the two loops by order (aligned, same
    direction), move the patch boundary onto the rim with a harmonic displacement of its inside, weld the pairs.
    The seam is then a plain edge loop of the mesh: no strip of long triangles, no twist."""
    n = len(rim_loop)                    # a closed loop has as many vertices as edges

    def patch_boundary():
        edges = [e for e in bm.edges if e.is_boundary and all(f[tag] == cid for f in e.link_faces)]
        return edges

    for _ in range(40):                                    # equalise the vertex counts
        edges = patch_boundary()
        m = len(edges)
        if m == n:
            break
        if m < n:
            longest = sorted(edges, key=lambda e: -e.calc_length())[:min(n - m, m)]
            bmesh.ops.subdivide_edges(bm, edges=longest, cuts=1, use_grid_fill=False)
            bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if f[tag] == cid and len(f.verts) > 3])
        else:
            used, pick = set(), []
            for e in sorted(edges, key=lambda e: e.calc_length()):
                if len(pick) >= m - n:
                    break
                if not (set(e.verts) & used):
                    pick.append(e)
                    used.update(e.verts)
            bmesh.ops.collapse(bm, edges=pick, uvs=False)
    edges = patch_boundary()
    if len(edges) != n:
        return False
    rim = ordered(find_rim())            # BMVert references do not survive subdivide_edges: look the rim up again
    if len(rim) != n:
        return False
    patch = align(rim, ordered(edges))
    # harmonic displacement: boundary -> rim, inside follows (Jacobi on the patch's edge graph)
    verts = list({v for f in bm.faces if f[tag] == cid for v in f.verts})
    idx = {v: i for i, v in enumerate(verts)}
    disp = np.zeros((len(verts), 3))
    fixed = np.zeros(len(verts), bool)
    for r, p in zip(rim, patch):
        disp[idx[p]] = np.array(tuple(r.co - p.co))
        fixed[idx[p]] = True
    pairs = np.array([(idx[e.verts[0]], idx[e.verts[1]]) for e in {e for v in verts for e in v.link_edges}
                      if e.verts[0] in idx and e.verts[1] in idx])
    for _ in range(600):
        s = np.zeros_like(disp)
        c = np.zeros(len(verts))
        np.add.at(s, pairs[:, 0], disp[pairs[:, 1]])
        np.add.at(c, pairs[:, 0], 1)
        np.add.at(s, pairs[:, 1], disp[pairs[:, 0]])
        np.add.at(c, pairs[:, 1], 1)
        upd = ~fixed & (c > 0)
        disp[upd] = s[upd] / c[upd, None]
    for v in verts:
        v.co = v.co + Vector(disp[idx[v]])
    for r, p in zip(rim, patch):
        bmesh.ops.pointmerge(bm, verts=[p, r], merge_co=r.co)
    return True


def ordered(loop):
    """The vertices of a closed boundary loop in walking order."""
    adj = {}
    for e in loop:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = loop[0].verts[0]
    out, prev, cur = [start], None, start
    while True:
        nxt = [w for w in adj[cur] if w is not prev]
        if not nxt or nxt[0] is start:
            break
        prev, cur = cur, nxt[0]
        out.append(cur)
        if len(out) > len(adj):
            break
    return out


def strip_bridge(bm, rim, patch):
    """Triangle strip between two closed loops, both parameterised by arc length from aligned starts and run the
    same way (no twist), advancing on whichever loop is behind."""
    def params(vs):
        d = [0.0]
        for i in range(1, len(vs) + 1):
            d.append(d[-1] + (vs[i % len(vs)].co - vs[i - 1].co).length)
        total = d[-1] or 1.0
        return [x / total for x in d]
    j0 = min(range(len(patch)), key=lambda j: (patch[j].co - rim[0].co).length)
    fwd = patch[j0:] + patch[:j0]
    rev = [patch[j0]] + list(reversed(patch[:j0])) + list(reversed(patch[j0 + 1:]))

    def mismatch(p):
        tr, tp = params(rim), params(p)
        err = 0.0
        for k in range(1, 12):
            t = k / 12
            i = min(range(len(rim)), key=lambda i: abs(tr[i] - t))
            j = min(range(len(p)), key=lambda j: abs(tp[j] - t))
            err += (rim[i].co - p[j].co).length
        return err

    patch = fwd if mismatch(fwd) <= mismatch(rev) else rev
    tr, tp = params(rim), params(patch)
    n, m = len(rim), len(patch)
    i = j = 0
    faces = []
    while i < n or j < m:
        a, b = rim[i % n], patch[j % m]
        if j >= m or (i < n and tr[i + 1] <= tp[j + 1]):
            tri = (a, rim[(i + 1) % n], b)
            i += 1
        else:
            tri = (a, patch[(j + 1) % m], b)
            j += 1
        if len(set(tri)) == 3:
            try:
                faces.append(bm.faces.new(tri))
            except ValueError:              # the face exists already
                pass
    return faces


def cleanup(body, log):
    """Duplicate / degenerate faces the caps left (holes_fill on the thin strap slits, subdividing next to the seam
    made edges with four faces - 8 of them on 10-25): drop duplicates, dissolve degenerates, then re-cap whatever
    is still non-manifold."""
    me = body.data
    bm = bmesh.new()
    bm.from_mesh(me)
    tag = bm.faces.layers.int.get("nude_fill")
    seen, dup = set(), []
    for f in bm.faces:
        k = tuple(sorted(v.index for v in f.verts))
        if k in seen:
            dup.append(f)
        seen.add(k)
    bmesh.ops.delete(bm, geom=dup, context="FACES")
    bmesh.ops.dissolve_degenerate(bm, dist=0.005, edges=bm.edges[:])
    bad = [e for e in bm.edges if len(e.link_faces) > 2]
    refilled = 0
    if bad and tag is not None:
        doomed = {f for e in bad for f in e.link_faces if f[tag] > 0}
        ids = {f[tag] for f in doomed}
        bmesh.ops.delete(bm, geom=list(doomed), context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        loops = [l for l in boundary_loops(bm) if sum(e.calc_length() for e in l) < 25.0]   # not the neck
        for l in loops:
            new = bmesh.ops.holes_fill(bm, edges=l, sides=0)["faces"]
            for f in bmesh.ops.triangulate(bm, faces=new)["faces"]:
                f[tag] = min(ids) if ids else 1
            refilled += 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.to_mesh(me)
    bm.free()
    log("nude body cleanup: %d duplicate faces, %d non-manifold edges re-capped (%d holes), %d left" % (
        len(dup), len(bad), refilled, nm))


def image_pixels(path):
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4), img


def build(skin_meshes, arm, spec, materials, log, report):
    """Join the base skin meshes, cap their openings (but the neck) and return the body object."""
    if not skin_meshes:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for m in skin_meshes:
        m.select_set(True)
    body = skin_meshes[0]
    bpy.context.view_layer.objects.active = body
    if len(skin_meshes) > 1:
        bpy.ops.object.join()
    me = body.data
    mw = body.matrix_world
    bm = bmesh.new()
    bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD)
    welded = n0 - len(bm.verts)
    loops = boundary_loops(bm)

    def centre(loop):
        vs = {v for e in loop for v in e.verts}
        return sum((mw @ v.co for v in vs), Vector()) / len(vs)

    neck = max(loops, key=lambda l: centre(l).z) if loops else None
    guides = SkinGuides(spec.get("nude_skin_guide"))
    mannequin = bvh_from_psks(spec.get("nude_guide"))
    uvl = bm.loops.layers.uv.active
    tag = bm.faces.layers.int.get("nude_fill") or bm.faces.layers.int.new("nude_fill")
    color_caps, info, pending = [], [], []
    for li, loop in enumerate(loops):
        if loop is neck:
            continue
        cid = li + 1
        per = sum(e.calc_length() for e in loop)
        rim_pos = [tuple(mw @ v.co) for v in {v for e in loop for v in e.verts}]
        rim_seg = [(tuple(mw @ e.verts[0].co), tuple(mw @ e.verts[1].co)) for e in loop]
        rim_uv = []
        for e in loop:
            for v in e.verts:
                for l in v.link_loops:
                    rim_uv.append(tuple(l[uvl].uv))
        new_faces = bmesh.ops.holes_fill(bm, edges=loop, sides=0)["faces"]
        if not new_faces:
            continue
        for f in new_faces:
            for l in f.loops:
                other = [ol for ol in l.vert.link_loops if ol.face not in new_faces]
                if other:
                    l[uvl].uv = other[0][uvl].uv
        for f in bmesh.ops.triangulate(bm, faces=new_faces)["faces"]:
            f[tag] = cid

        def cap():
            return [f for f in bm.faces if f[tag] == cid]

        def inner_edges():
            return list({e for f in cap() for e in f.edges if len(e.link_faces) == 2
                         and all(lf[tag] == cid for lf in e.link_faces)})

        bmesh.ops.beautify_fill(bm, faces=cap(), edges=inner_edges())
        for _ in range(8):
            long_edges = [e for e in inner_edges() if e.calc_length() > EDGE]
            if not long_edges:
                break
            bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=False)
            bmesh.ops.triangulate(bm, faces=[f for f in cap() if len(f.verts) > 3])
            bmesh.ops.beautify_fill(bm, faces=cap(), edges=inner_edges())
        verts = {v for f in cap() for v in f.verts}
        rim = [v for v in verts if any(lf[tag] != cid for lf in v.link_faces)]     # refs do not survive subdivide
        inner = [v for v in verts if all(lf[tag] == cid for lf in v.link_faces)]
        for _ in range(40):
            bmesh.ops.smooth_vert(bm, verts=inner, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.normal_update()
        stem, share, off = guides.best(mw, rim, inner, log)
        if stem is None and spec.get("nude_guide"):
            # no costume shows this area (the bikini): reopen it, it gets the mannequin's own faces afterwards
            bmesh.ops.delete(bm, geom=cap(), context="FACES")
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            pending.append((cid, per, share, rim_pos, rim_seg))
            continue
        if stem is not None:
            guide, reach, gname = guides.bvh(stem), SKIN_REACH, "%s's skin (rim %.2f cm off)" % (stem, off)
        else:
            guide, reach, gname = mannequin, MANNEQUIN_REACH, "mannequin"
        if guide is not None and inner:
            for rnd in range(ROUNDS):
                bm.normal_update()
                snap(guide, mw, inner, rim, reach)
                for _ in range(4 if rnd < ROUNDS - 1 else 1):
                    bmesh.ops.smooth_vert(bm, verts=inner, factor=0.3, use_axis_x=True, use_axis_y=True,
                                          use_axis_z=True)
        uvs = np.array(rim_uv) if rim_uv else np.zeros((1, 2))
        spread = float((uvs.max(axis=0) - uvs.min(axis=0)).max())
        mode = "uv" if spread < UV_COMPACT else "colour"
        if mode == "colour":
            color_caps.append(cid)
        info.append("%.0f cm: %s guide (skin cover %.0f%%), %s" % (per, gname if guide else "no", 100 * share, mode))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for cid, per, share, rim_pos, rim_seg in pending:
        n = mannequin_patch(body, rim_pos, rim_seg, spec.get("nude_guide"), cid, log, guides)
        color_caps.append(cid)
        info.append("%.0f cm: mannequin's own faces bridged in (%d faces; skin cover %.0f%%), colour" % (per, n, 100 * share))
    me = body.data
    cleanup(body, log)

    skin_name = spec.get("nude_skin_material")
    if color_caps and skin_name:
        fill_colour(body, color_caps, materials.get(skin_name, {}), skin_name)
    bpy.context.view_layer.objects.active = body
    if me.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for p in me.polygons:
        p.use_smooth = True
    if hasattr(me, "use_auto_smooth"):
        me.use_auto_smooth = False
    bpy.ops.object.material_slot_remove_unused()        # the garment slots of the base set
    report["rig"]["nude"] = {"welded_vertices": welded, "caps": info}
    log("nude body: %d vertices welded at the waist; caps: %s" % (welded, "; ".join(info)))
    return body


def fill_colour(body, cap_ids, skin_entry, skin_name):
    """Material <skin>_fill on the colour caps: vertex colour "fill_color" = skin texture at the rim, diffused in."""
    me = body.data
    albedo = skin_entry.get("albedo")
    if not albedo or not os.path.isfile(albedo):
        return
    px, _img = image_pixels(albedo)
    h, w = px.shape[:2]
    caps = set(cap_ids)
    tag = me.attributes["nude_fill"].data
    uv = me.uv_layers.active.data
    nv = len(me.vertices)
    col = np.zeros((nv, 4), np.float32)
    known = np.zeros(nv, bool)
    acc, cnt = np.zeros((nv, 3)), np.zeros(nv)
    in_cap = np.zeros(nv, bool)
    for p in me.polygons:
        is_cap = tag[p.index].value in caps
        for li in p.loop_indices:
            vi = me.loops[li].vertex_index
            if is_cap:
                in_cap[vi] = True
            else:                                        # rim / skin vertices: sample the texture
                u, v = uv[li].uv
                x = min(max(int(u % 1.0 * w), 0), w - 1)
                y = min(max(int(v % 1.0 * h), 0), h - 1)
                acc[vi] += px[y, x, :3]
                cnt[vi] += 1
    known = cnt > 0
    srgb = acc[known] / cnt[known, None]          # 8-bit sRGB texture values -> linear for the FLOAT_COLOR attribute
    col[known, :3] = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    col[:, 3] = 1.0
    # diffuse into the caps' interiors (Jacobi over the edges, rim fixed)
    edges = np.array([tuple(e.vertices) for e in me.edges], dtype=np.int64)
    free = in_cap & ~known
    for _ in range(300):
        s = np.zeros((nv, 3))
        n = np.zeros(nv)
        np.add.at(s, edges[:, 0], col[edges[:, 1], :3])
        np.add.at(n, edges[:, 0], 1)
        np.add.at(s, edges[:, 1], col[edges[:, 0], :3])
        np.add.at(n, edges[:, 1], 1)
        upd = free & (n > 0)
        col[upd, :3] = s[upd] / n[upd, None]
    attr = me.color_attributes.get("fill_color") or me.color_attributes.new("fill_color", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", col.ravel())
    # the fill material: same skin, colour from the attribute
    name = skin_name + "_fill"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    ca = nt.nodes.new("ShaderNodeVertexColor")
    ca.layer_name = "fill_color"
    ca.location = (-100, 0)
    nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ca.outputs["Color"], bsdf.inputs["Subsurface Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Subsurface"].default_value = 0.08
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    mat["aion2_ready"] = True
    if name not in [s.material.name for s in body.material_slots if s.material]:
        body.data.materials.append(mat)
    slot = [i for i, s in enumerate(body.material_slots) if s.material and s.material.name == name][0]
    for p in me.polygons:
        if tag[p.index].value in caps:
            p.material_index = slot
