"""Blender helpers shared by the physics previews (roe_refit_camera.py, roe_eros_preview.py): a floor the physics
lands on, re-baking, and a framing box that one stray piece cannot blow up.

A preview floor used to be only a picture: a lying clip (a08's die and rip) hung its skirt through it, and in rip the
pieces below the floor stretched the camera so far and so low that the body all but vanished.  The collider lives in
the preview scene only; the PMX and the VMD are not touched.
"""
import bpy
import numpy as np


def add_floor_collider(scene, size=12.0, depth=1.0):
    """A hidden passive box whose top is the floor (z = 0), colliding with every rigid body group.  Blender centres a
    box shape on the object's origin, whatever the mesh, so the origin goes to the middle of the box: with the origin
    on the top face the box reached half its depth above the floor, and a long skirt that starts inside it was thrown
    up in the first frame."""
    half, mid = size / 2, depth / 2
    verts = [(x, y, z) for z in (-mid, mid) for y in (-half, half) for x in (-half, half)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new("floor_collider")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("floor_collider", me)
    ob.location = (0.0, 0.0, -mid)
    scene.collection.objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.rigidbody.object_add(type="PASSIVE")
    rb = ob.rigid_body
    rb.collision_shape = "BOX"
    rb.friction = 0.6
    rb.restitution = 0.0
    rb.use_margin = True
    rb.collision_margin = 0.002
    rb.collision_collections = [True] * len(rb.collision_collections)
    return ob


def rebake(scene):
    cache = scene.rigidbody_world.point_cache
    with bpy.context.temp_override(scene=scene, point_cache=cache):
        bpy.ops.ptcache.free_bake()
        bpy.ops.ptcache.bake(bake=True)


def shown_points(o, deps):
    """World positions of the mesh's vertices, minus those a scale morph has folded away (縮小_* at > 0.5: a00's
    semen mesh, which the clip parks 1 m off)."""
    ev = o.evaluated_get(deps)
    n = len(ev.data.vertices)
    co = np.empty(n * 3)
    ev.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    keep = np.ones(n, bool)
    keys = o.data.shape_keys
    if keys is not None and len(o.data.vertices) == n:
        base = np.empty(n * 3)
        keys.reference_key.data.foreach_get("co", base)
        for kb in keys.key_blocks:
            if kb.name.startswith("縮小_") and kb.value > 0.5:
                d = np.empty(n * 3)
                kb.data.foreach_get("co", d)
                keep &= np.abs(d - base).reshape(-1, 3).max(1) < 1e-6
    m = np.array(ev.matrix_world)
    return co[keep] @ m[:3, :3].T + m[:3, 3]


def motion_box(scene, meshes, start, end, step=3, keep=0.995):
    """(lo, hi) of what the meshes show over the frames, trimmed to the central ``keep`` share of the points on
    each axis (a strand of hair or a skirt corner thrown out for a frame does not move the camera)."""
    pts = []
    for f in range(start, end + 1, step):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        for o in meshes:
            p = shown_points(o, deps)
            if len(p):
                pts.append(p[:: max(1, len(p) // 20000)])
    allp = np.concatenate(pts)
    cut = (1.0 - keep) / 2 * 100
    return np.percentile(allp, cut, axis=0), np.percentile(allp, 100 - cut, axis=0)
