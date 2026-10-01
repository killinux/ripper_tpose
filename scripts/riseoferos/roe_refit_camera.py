"""Re-render a render_pmx_dance.py preview with the camera fitted to the whole motion.

render_pmx_dance.py frames a dance: a fixed camera 4.2 m in front, about 3 m of height in view.  Battle clips leap
1 m up (Luf skill_01) or fall 1.2 m towards the camera (die), out of that frame.  render_pmx_dance.py saves its scene
(physics baked) beside the mp4 before rendering; this opens that .blend, measures every visible mesh over the
whole frame range, moves the camera back until all of it fits the 720x1080 portrait, and renders the mp4 again.

  blender -b <preview.blend> --python roe_refit_camera.py -- <out.mp4>
"""
import math
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
cam = scene.camera
# render_pmx_dance.py puts VMD frame 0 at scene frame MARGIN + 1 and eases in from the rest pose before it.  The
# lead-in is simulated (the cache is baked) but not shown: from the standing A-pose it made a lying clip (die, rip)
# stand up and fall at the start, and an H scene drop its heads into the frame.
LEAD_IN = 30
scene.frame_start += LEAD_IN
meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get()
          and not o.name.startswith("floor") and o.dimensions.length < 20]
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for f in range(scene.frame_start, scene.frame_end + 1, 4):
    scene.frame_set(f)
    deps = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        ev = o.evaluated_get(deps)
        for c in ev.bound_box:
            p = ev.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
lo.z = min(lo.z, 0.0)
centre = (lo + hi) / 2
# portrait 720x1080, 50 mm lens on a 36 mm sensor fitted to the height
half_v = math.atan(18.0 / 50.0)
half_h = math.atan(18.0 / 50.0 * 720 / 1080)
need_v = (hi.z - lo.z) / 2 * 1.12
need_h = (hi.x - lo.x) / 2 * 1.12
dist = max(need_v / math.tan(half_v), need_h / math.tan(half_h), 3.0) + (hi.y - lo.y) / 2
cam.location = Vector((centre.x, lo.y - dist + (hi.y - lo.y) / 2, centre.z))
cam.rotation_euler = (math.radians(90), 0.0, 0.0)
cam.data.lens = 50
cam.data.sensor_fit = "AUTO"
print("refit: bbox %s .. %s -> camera %s" % (tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi),
                                            tuple(round(v, 2) for v in cam.location)))
scene.render.filepath = out
bpy.ops.render.render(animation=True)
print("REFIT_DONE", out)
