"""Write a small PMX that measures, inside MMD itself, the two numbers breast (and
cloth) physics depend on but no document states: how strong MMD's gravity is in
model units, and how much of a joint's rotation spring MMD actually applies.

    python physics_calibration_pmx.py out.pmx [--sag 10] [--lever 3] [--mass 1]

Load it in MMD, make sure physics is on, play ~3 seconds and take a screenshot:

- The white square on the left (with the coloured ruler) falls freely: with
  gravity 98 u/s^2 (9.8 x 10, what three.js / saba / MMDAgent-EX use) it is out
  of the picture within a second; with 9.8 u/s^2 it drops only ~5 u per second.
- Five horizontal arms hang on joints whose rotation spring is sized, by Hooke's
  law and g = 98, to hold the arm ``--sag`` degrees below horizontal - times 1,
  3, 10, 30 and 100 from left to right (the dots above each pivot count 1-5).
  The fan of coloured rays behind each arm marks 0/10/20/30/45/60/80 degrees.
  If MMD's springs are the ideal springs their numbers say and g = 98, the
  leftmost arm settles on the 10-degree ray (green) and the others at 3.3 / 1 /
  0.3 / 0.1 degrees; an arm that sags more means MMD's spring is weaker than its
  number by that ratio; with g = 9.8 every arm droops 10x less.

calibration_blender.py runs the same model in Blender (mmd_like.py) at 60 / 120
/ 300 Hz: the leftmost arm settles at 9.5-9.8 degrees and the square falls 49
units in the first second, i.e. the ideal-spring, g = 98 answer.

Needs Python and the ``pmx`` module inside mmd_tools (see tune_bust_pmx.py).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tune_bust_pmx import find_pmx_module, load_pmx_module  # noqa: E402

MULTIPLIERS = (1, 3, 10, 30, 100)
RAYS = ((0, (1.0, 1.0, 1.0)), (10, (0.1, 0.8, 0.2)), (20, (0.95, 0.85, 0.1)), (30, (1.0, 0.5, 0.1)),
        (45, (0.9, 0.1, 0.1)), (60, (0.8, 0.2, 0.8)), (80, (0.2, 0.4, 1.0)))
BANDS = ((0, 5, (0.9, 0.1, 0.1)), (5, 10, (1.0, 0.5, 0.1)), (10, 15, (0.95, 0.85, 0.1)),
         (15, 20, (0.1, 0.8, 0.2)), (20, 25, (0.2, 0.4, 1.0)))


class Builder:
    def __init__(self, pmx):
        self.pmx = pmx
        self.model = pmx.Model()
        self.model.name = self.model.name_e = "physics calibration"
        self.model.comment = ("MMD 物理标定：左侧方块测重力，五个摆臂测关节弹簧的实际强度（从左到右 x1 x3 x10 x30 x100）。"
                              "由 scripts/mmd_physics/physics_calibration_pmx.py 生成")
        self.model.comment_e = "MMD physics calibration: free fall (gravity) + five sprung arms (spring strength)"
        self.materials = {}          # name -> (colour, [faces])

    def bone(self, name, location, parent):
        bone = self.pmx.Bone()
        bone.name, bone.name_e = name, name
        bone.location = list(location)
        bone.parent = parent
        bone.displayConnection = -1
        self.model.bones.append(bone)
        return len(self.model.bones) - 1

    def quad(self, material, colour, corners, bone):
        """A flat quad in the XY plane facing the camera, skinned 100% to ``bone``."""
        start = len(self.model.vertices)
        for x, y, z in corners:
            vertex = self.pmx.Vertex()
            vertex.co = [x, y, z]
            vertex.normal = [0.0, 0.0, -1.0]
            vertex.uv = [0.0, 0.0]
            vertex.weight = self.pmx.BoneWeight()
            vertex.weight.type = self.pmx.BoneWeight.BDEF1
            vertex.weight.bones = [bone]
            vertex.weight.weights = []
            self.model.vertices.append(vertex)
        faces = self.materials.setdefault(material, (colour, []))[1]
        faces += [(start, start + 1, start + 2), (start, start + 2, start + 3)]

    def bar(self, material, colour, a, b, width, bone, z=0.0):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * width / 2, dx / length * width / 2
        self.quad(material, colour, [(a[0] + nx, a[1] + ny, z), (b[0] + nx, b[1] + ny, z),
                                     (b[0] - nx, b[1] - ny, z), (a[0] - nx, a[1] - ny, z)], bone)

    def square(self, material, colour, centre, size, bone, z=0.0):
        h = size / 2
        x, y = centre
        self.quad(material, colour, [(x - h, y - h, z), (x - h, y + h, z), (x + h, y + h, z), (x + h, y - h, z)],
                  bone)

    def rigid(self, name, bone, location, radius, mode, mass=1.0, damping=(0.0, 0.0)):
        rigid = self.pmx.Rigid()
        rigid.name, rigid.name_e = name, name
        rigid.bone = bone
        rigid.collision_group_number = 15
        rigid.collision_group_mask = 0            # collides with nothing
        rigid.type = 0
        rigid.size = [radius, 0.0, 0.0]
        rigid.location = list(location)
        rigid.rotation = [0.0, 0.0, 0.0]
        rigid.mass = mass
        rigid.velocity_attenuation, rigid.rotation_attenuation = damping
        rigid.bounce, rigid.friction = 0.0, 0.5
        rigid.mode = mode
        self.model.rigids.append(rigid)
        return len(self.model.rigids) - 1

    def joint(self, name, src, dest, location, swing_limit, spring_z):
        joint = self.pmx.Joint()
        joint.name, joint.name_e = name, name
        joint.mode = 0
        joint.src_rigid, joint.dest_rigid = src, dest
        joint.location = list(location)
        joint.rotation = [0.0, 0.0, 0.0]
        joint.minimum_location = joint.maximum_location = [0.0, 0.0, 0.0]
        joint.minimum_rotation = [0.0, 0.0, -swing_limit]
        joint.maximum_rotation = [0.0, 0.0, swing_limit]
        joint.spring_constant = [0.0, 0.0, 0.0]
        joint.spring_rotation_constant = [0.0, 0.0, spring_z]
        self.model.joints.append(joint)

    def finish(self):
        for name, (colour, faces) in self.materials.items():
            material = self.pmx.Material()
            material.name, material.name_e = name, name
            material.diffuse = list(colour) + [1.0]
            material.specular = [0.0, 0.0, 0.0]
            material.shininess = 5.0
            material.ambient = [c * 0.6 for c in colour]
            material.edge_color = [0.0, 0.0, 0.0, 1.0]
            material.is_double_sided = True
            material.enabled_toon_edge = False
            material.vertex_count = len(faces) * 3
            self.model.materials.append(material)
            # the module writes each face reversed (Blender winding -> PMX)
            self.model.faces += [(c, b, a) for a, b, c in faces]
        root = self.model.display[0]
        root.data = [(0, 0)]
        frame = self.pmx.Display()
        frame.name, frame.name_e = "物理", "physics"
        frame.data = [(0, i) for i in range(1, len(self.model.bones))]
        self.model.display.append(frame)
        return self.model


def build(pmx, sag_deg=10.0, lever=3.0, mass=1.0, gravity=98.0):
    b = Builder(pmx)
    root = b.bone("全ての親", (0.0, 0.0, 0.0), None)

    # free fall: ruler + square, no joint, no damping
    fall_x, fall_y = -18.0, 20.0
    for low, high, colour in BANDS:
        b.quad("ruler%02d" % low, colour, [(-20.0, low, 0.0), (-20.0, high, 0.0), (-19.2, high, 0.0),
                                           (-19.2, low, 0.0)], root)
    fall = b.bone("落下", (fall_x, fall_y, 0.0), root)
    b.square("falling", (1.0, 1.0, 1.0), (fall_x, fall_y), 1.0, fall, z=-0.05)
    b.rigid("落下", fall, (fall_x, fall_y, 0.0), 0.5, mode=1, mass=mass, damping=(0.0, 0.0))

    # sprung arms: Hooke's law with g = 98 would hold each at sag_deg; multipliers left to right
    k_hooke = mass * gravity * lever / math.radians(sag_deg)
    pivots_x = (-12.0, -5.0, 2.0, 9.0, 16.0)
    pivot_y = 13.0
    springs = []
    for n, (x, multiplier) in enumerate(zip(pivots_x, MULTIPLIERS)):
        pivot = (x, pivot_y)
        for angle, colour in RAYS:
            a = math.radians(-angle)
            tip = (x + (lever + 0.8) * math.cos(a), pivot_y + (lever + 0.8) * math.sin(a))
            b.bar("ray%02d" % angle, colour, pivot, tip, 0.07, root)
        for dot in range(n + 1):
            b.square("dots", (1.0, 1.0, 1.0), (x - 0.6 * n / 2 + 0.6 * dot, pivot_y + 1.0), 0.3, root)
        arm = b.bone("振子%d_x%d" % (n + 1, multiplier), (x, pivot_y, 0.0), root)
        b.bar("arm", (0.15, 0.15, 0.15), pivot, (x + lever, pivot_y), 0.22, arm, z=-0.05)
        b.square("arm", (0.15, 0.15, 0.15), (x + lever, pivot_y), 0.6, arm, z=-0.05)
        anchor = b.rigid("支点%d" % (n + 1), root, (x, pivot_y, 0.0), 0.2, mode=0)
        ball = b.rigid("振子%d" % (n + 1), arm, (x + lever, pivot_y, 0.0), 0.3, mode=1, mass=mass,
                       damping=(0.95, 0.95))
        spring = k_hooke * multiplier
        b.joint("振子%d_x%d" % (n + 1, multiplier), anchor, ball, (x, pivot_y, 0.0), math.radians(85), spring)
        springs.append(spring)
    return b.finish(), springs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("output")
    ap.add_argument("--sag", type=float, default=10.0,
                    help="droop in degrees Hooke's law predicts for the x1 arm with g = 98 (default %(default)s)")
    ap.add_argument("--lever", type=float, default=3.0, help="arm length in model units (default %(default)s)")
    ap.add_argument("--mass", type=float, default=1.0, help="arm body mass (default %(default)s)")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    args = ap.parse_args()
    pmx = load_pmx_module(find_pmx_module(args.pmx_module))
    model, springs = build(pmx, args.sag, args.lever, args.mass)
    pmx.save(args.output, model)
    print("wrote %s: %d vertices, %d bones, %d rigid bodies, %d joints" % (
        args.output, len(model.vertices), len(model.bones), len(model.rigids), len(model.joints)))
    print("arm springs (x1 x3 x10 x30 x100): " + ", ".join("%.0f" % s for s in springs))


if __name__ == "__main__":
    main()
