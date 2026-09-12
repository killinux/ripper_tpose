"""Checks that Blender's Bullet can actually answer.

Blender's Bullet is newer and stiffer than MMD's (2.75, soft constraints), so
it cannot reproduce MMD's dynamic feel or its joint-frame explosions.  What it
can tell reliably: whether a chain is structurally healthy - built in the
rest pose, does it settle without flying away?  The reference implementation
used "< 0.17 m of drift after 60 frames" as its health line; the drop test
here reports, per dynamic rigid body, how far it drifted, how much the joint
holding it stretched (the tear signal) and whether it is still moving at the
end (the "never settles" signal).
"""
import bpy

from . import analyze, api


def drop_test(obj, frames=60):
    """Build the mmd_tools physics, step ``frames`` in the rest pose, report
    drift per rigid body, then unbuild.  Returns {"summary", "lines", "worst"}."""
    model, root, arm, meshes = api.model_of(obj)
    scene = bpy.context.scene
    rigids = [o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "RIGID_BODY"
              and str(o.mmd_rigid.type) != "0"]
    start = {o.name: o.matrix_world.translation.copy() for o in rigids}
    # everything the simulation may move goes back exactly where it was, so a
    # PMX exported afterwards still carries the bind positions
    snapshot = {o.name: (o.parent, o.matrix_parent_inverse.copy(), o.matrix_basis.copy())
                for o in bpy.data.objects if getattr(o, "mmd_type", "") in ("RIGID_BODY", "JOINT")}
    was_built = root.mmd_root.is_built
    frame_was = scene.frame_current
    pose_was = arm.data.pose_position
    arm.data.pose_position = "REST"
    if not was_built:
        model.build()
    world = scene.rigidbody_world
    if world is None:
        raise RuntimeError("no rigid body world after build")
    cache_was = (world.point_cache.frame_start, world.point_cache.frame_end)
    world.enabled = True
    world.point_cache.frame_start = 1
    world.point_cache.frame_end = frames + 1
    # rest distance between the two bodies of every joint: a chain that is being
    # torn apart shows up as one of these growing, while a sleeve swinging from
    # the A-pose to vertical keeps every link at its length
    unit = analyze.unit_scale(meshes)
    links = {}
    for o in bpy.data.objects:
        if getattr(o, "mmd_type", "") != "JOINT" or o.rigid_body_constraint is None:
            continue
        a, b = o.rigid_body_constraint.object1, o.rigid_body_constraint.object2
        if a is None or b is None or b.name not in start:
            continue
        rest = (a.matrix_world.translation - b.matrix_world.translation).length
        links.setdefault(b.name, []).append((a, rest))
    scene.frame_set(1)
    for frame in range(2, frames + 2):
        scene.frame_set(frame)
        if frame == frames - 8:
            before_end = {o.name: o.matrix_world.translation.copy() for o in rigids}
    drift = []
    for o in rigids:
        pos = o.matrix_world.translation
        moved = (pos - start[o.name]).length
        stretch = 1.0
        for a, rest in links.get(o.name, ()):
            now = (a.matrix_world.translation - pos).length
            stretch = max(stretch, (now + 0.01 * unit) / (rest + 0.01 * unit))
        speed = (pos - before_end[o.name]).length / 8.0
        drift.append((moved, stretch, speed, o.name, o.mmd_rigid.bone))
    # restore
    world.enabled = False
    world.point_cache.frame_start, world.point_cache.frame_end = cache_was
    scene.frame_set(frame_was)
    if not was_built:
        model.clean()
    for name, (parent, inverse, basis) in snapshot.items():
        o = bpy.data.objects.get(name)
        if o is None:
            continue
        if o.parent != parent:
            o.parent = parent
        o.matrix_parent_inverse = inverse
        o.matrix_basis = basis
    arm.data.pose_position = pose_was
    bpy.context.view_layer.update()
    torn = [d for d in drift if d[1] > 1.5]
    restless = [d for d in drift if d[2] > 0.02 * unit]
    drift.sort(key=lambda d: -d[1])
    lines = ["drop test: %d dynamic rigid bodies, %d frames in the rest pose" % (len(drift), frames),
             "  torn (a joint stretched past 1.5x its rest length): %d" % len(torn),
             "  still moving at the end (>2 cm/frame): %d" % len(restless),
             "  worst stretch / drift / end speed:"]
    for moved, stretch, speed, name, bone in drift[:8]:
        lines.append("    %.2fx  %.3f m  %.3f m/f  %s" % (stretch, moved, speed, bone or name))
    if torn or restless:
        summary = "%d torn, %d restless of %d rigid bodies" % (len(torn), len(restless), len(drift))
    else:
        summary = "settled: worst stretch %.2fx, worst drift %.3f m" % (
            drift[0][1] if drift else 1.0, max((d[0] for d in drift), default=0.0))
    return {"summary": summary, "lines": lines, "worst": drift[:8],
            "bad": len(torn) + len(restless)}
