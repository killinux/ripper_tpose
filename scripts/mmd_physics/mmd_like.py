"""Make Blender's Bullet run an imported PMX's joints the way MMD does (import inside Blender).

mmd_tools builds every PMX joint as a Generic Spring constraint with all six
springs switched on and leaves Blender's defaults, which differ from MMD in
three ways that all make a Blender preview stiffer and calmer than MMD:

1. Spring type SPRING2 (btGeneric6DofSpring2) with damping 0.5 on every axis.
   That damping works on the joint's relative motion even at stiffness 0, and
   MMD has nothing like it: a PMX joint has no damping field, and MMD's Bullet
   2.75 uses the older btGeneric6DofSpring.  On g05 it held the breasts nearly
   still.  -> SPRING1.  Blender hands SPRING1 damping to Bullet INVERTED
   (``1 - value``, intern/rigidbody/rb_bullet_api.cpp), so Bullet's default 1.0,
   the value MMD runs with, is 0.0 here; at 1.0 the spring only brakes.
2. Rotation springs copied without unit conversion: at import scale s they are
   1/s^2 too stiff (156x at 0.08).  Linear springs are scale-free.
3. Gravity: 9.8 x 10 model units/s^2 in three.js MMDPhysics, saba and
   MMDAgent-EX (MMD itself does not say); Blender's 9.81 m/s^2 is 25% more at 0.08.

Checked with physics_calibration_pmx.py in Blender 3.6: after this conversion an
arm sprung for 10 degrees by Hooke's law settles at 9.5-9.8 degrees at 60, 120
and 300 Hz, and a free body falls 49 units in the first second, so Blender then
runs PMX springs as the ideal springs their numbers describe.  (Very stiff
springs, 30x that arm's, come out softer at 60 Hz.)  Whether MMD does the same
is what the calibration model shows when opened in MMD.  Joint limits stay
Blender's (MMD's are softer).  A breast that carries other bodies (g05's
pendants) sags by their weight too - tune_bust_pmx.py counts it.
"""


def mmd_like_physics(scene, scale, gravity=98.0, substeps=None):
    """Convert every mmd_tools joint in ``scene``; returns how many were converted."""
    count = 0
    for obj in scene.objects:
        constraint = obj.rigid_body_constraint
        if constraint is None or constraint.type != "GENERIC_SPRING":
            continue
        constraint.spring_type = "SPRING1"
        for axis in "xyz":
            setattr(constraint, "spring_damping_" + axis, 0.0)
            setattr(constraint, "spring_damping_ang_" + axis, 0.0)
            stiffness = getattr(constraint, "spring_stiffness_ang_" + axis)
            setattr(constraint, "spring_stiffness_ang_" + axis, stiffness * scale * scale)
        count += 1
    scene.gravity = (0.0, 0.0, -gravity * scale)
    if substeps and scene.rigidbody_world is not None:
        scene.rigidbody_world.substeps_per_frame = substeps
    return count
