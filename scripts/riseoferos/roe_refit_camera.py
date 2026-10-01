"""Re-render a render_pmx_dance.py preview with the camera fitted to the whole motion.

render_pmx_dance.py frames a dance: a fixed camera 4.2 m in front, about 3 m of height in view.  Battle clips leap
1 m up (Luf skill_01) or fall 1.2 m towards the camera (die), out of that frame.  render_pmx_dance.py saves its scene
(physics baked) beside the mp4 before rendering; this opens that .blend, measures every visible mesh over the
whole frame range, moves the camera back until all of it fits the 720x1080 portrait, and renders the mp4 again.
A motion that stays on the ground (rip, lower than 0.8 m) is seen from 35 degrees above instead of level.
Before that it gives the floor a collider and bakes the physics again (roe_preview_scene.py); the framing box keeps
99.5% of the points on each axis, so one thrown strand does not move the camera.

  blender -b <preview.blend> --python roe_refit_camera.py -- <out.mp4>
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roe_preview_scene import add_floor_collider, motion_box, rebake  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
cam = scene.camera
# the physics again, now with a floor to land on (a lying clip hung its skirt through the picture-only floor)
if scene.rigidbody_world is not None:
    add_floor_collider(scene)
    rebake(scene)
# render_pmx_dance.py puts VMD frame 0 at scene frame MARGIN + 1 and eases in from the rest pose before it.  The
# lead-in is simulated (the cache is baked) but not shown: from the standing A-pose it made a lying clip (die, rip)
# stand up and fall at the start, and an H scene drop its heads into the frame.
LEAD_IN = 30
scene.frame_start += LEAD_IN
meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get()
          and not o.name.startswith("floor") and o.dimensions.length < 20]
lo, hi = (Vector(v) for v in motion_box(scene, meshes, scene.frame_start, scene.frame_end, 4))
lo.z = max(min(lo.z, 0.0), -0.05)
centre = (lo + hi) / 2
# portrait 720x1080, 50 mm lens on a 36 mm sensor fitted to the height
tan_v = 18.0 / 50.0
tan_h = tan_v * 720 / 1080
FLAT = 0.8              # a motion lower than this stays on the ground the whole time (rip)
PITCH = 35.0            # degrees the camera looks down on such a motion
if hi.z - lo.z > FLAT:
    need_v = (hi.z - lo.z) / 2 * 1.12
    need_h = (hi.x - lo.x) / 2 * 1.12
    dist = max(need_v / tan_v, need_h / tan_h, 3.0) + (hi.y - lo.y) / 2
    cam.location = Vector((centre.x, lo.y - dist + (hi.y - lo.y) / 2, centre.z))
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
else:
    # level with a body lying on the floor the camera saw it end-on, a strip at the bottom of the frame
    pitch = math.radians(PITCH)
    forward = Vector((0.0, math.cos(pitch), -math.sin(pitch)))
    right = Vector((1.0, 0.0, 0.0))
    up = right.cross(forward)
    dist = 0.0
    for x in (lo.x, hi.x):
        for y in (lo.y, hi.y):
            for z in (lo.z, hi.z):
                v = Vector((x, y, z)) - centre
                depth = v.dot(forward)
                dist = max(dist, abs(v.dot(right)) / tan_h - depth, abs(v.dot(up)) / tan_v - depth)
    dist = max(dist * 1.12, 2.0)
    cam.location = centre - forward * dist
    cam.rotation_euler = (math.radians(90) - pitch, 0.0, 0.0)
cam.data.lens = 50
cam.data.sensor_fit = "AUTO"
print("refit: bbox %s .. %s -> camera %s" % (tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi),
                                            tuple(round(v, 2) for v in cam.location)))
scene.render.filepath = out
bpy.ops.render.render(animation=True)
print("REFIT_DONE", out)
