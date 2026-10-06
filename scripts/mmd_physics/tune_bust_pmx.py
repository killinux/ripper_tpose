"""Re-tune the breast physics of an existing PMX without re-exporting the model.

Rewrites the joints that hang a dynamic breast body on the chest (rotation
limits and springs) and those bodies' damping, and writes a new PMX (next to a
copy of the textures folder, or pointing back at the original's).  Every value
has a default and every default can be overridden on the command line.

    python tune_bust_pmx.py in.pmx out.pmx                       # recommended defaults
    python tune_bust_pmx.py in.pmx out.pmx --sag 8 --lin-damp 0.99 --ang-damp 0.99
    python tune_bust_pmx.py in.pmx - --dry-run                   # only print what it would do

Springs are sized from gravity rather than guessed.  With no spring, gravity
parks the body on its rotation limit (the template ROE shipped with); with a
spring k on the pitch axis the body settles at ``sag = torque / k``, so ``--sag``
picks the rest droop and the spring follows.  The torque counts everything the
breast carries: its own body AND every body hung on it through joints (g05's
pendants: three bodies of mass 1 per side, 3.4x the breast's own torque, which
dragged a spring sized for the breast alone onto its limit).  ``--hanging-scale``
multiplies those bodies' masses and their joints' springs by the same factor:
their own swing stays the same (spring/mass unchanged) while they pull on the
breast that much less - pendants weigh little next to a breast.

Sag and bounce speed come as a pair: the swing frequency is about
``sqrt(k / I) / 2pi`` (I = inertia about the pivot, hanging bodies counted as if
rigid, so the printed figure is a lower bound).  ``--gravity`` is MMD's gravity
in model units: 98 u/s^2 (9.8 x 10) in every MMD-compatible implementation that
publishes one (three.js MMDPhysics, saba, MMDAgent-EX);
physics_calibration_pmx.py checks it in MMD itself.

Axes are the joint's own: X = pitch (up/down), Y = yaw (sideways), Z = twist
about the forward axis, the way MMD reads them for a joint with rotation 0.
Needs only Python and the ``pmx`` module that ships inside mmd_tools (no
Blender); ``--pmx-module`` points at it when the search below misses.
"""
import argparse
import glob
import importlib.util
import math
import os
import re
import sys

DEFAULTS = {
    "gravity": 98.0,        # MMD units / s^2
    "sag": 15.0,            # degrees the breast droops at rest (pitch)
    "twist_sag": 4.0,       # degrees it may roll about the forward axis at rest
    "yaw_scale": 1.0,       # yaw spring = pitch spring x this
    "pitch_limit": 25.0,    # degrees
    "yaw_limit": 20.0,
    "twist_limit": 5.0,
    "lin_damp": 0.95,       # 移動減衰 of the swinging body
    "ang_damp": 0.95,       # 回転減衰
    "hanging_scale": 0.2,   # mass (and joint springs) of bodies hung on the breast
    "bones": r"胸|乳|chest|breast|bust|oppai",
}
AXES = ("pitch", "yaw", "twist")


def find_pmx_module(explicit=None):
    if explicit:
        return explicit
    roots = [os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")]
    patterns = ["3.6/scripts/addons/mmd_tools/core/pmx/__init__.py",
                "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                "*/extensions/*/mmd_tools/core/pmx/__init__.py"]
    for root in roots:
        for pattern in patterns:
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits:
                return hits[0]
    raise SystemExit("mmd_tools' core/pmx/__init__.py not found; pass --pmx-module")


def load_pmx_module(path):
    spec = importlib.util.spec_from_file_location("mmd_pmx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def joint_frame(rx, ry, rz):
    """Axes of a PMX joint frame in PMX coordinates, read the way mmd_tools reads them:
    Blender Euler (-rx, -rz, -ry) in 'YXZ' order on y/z-swapped axes.  Identity for
    rotation 0, which is every joint the ROE exporter writes."""
    def rot(axis, angle):
        c, s = math.cos(angle), math.sin(angle)
        return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
                "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
                "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
    blender = _mul(_mul(rot("z", -ry), rot("x", -rx)), rot("y", -rz))
    swap = [[1, 0, 0], [0, 0, 1], [0, 1, 0]]
    return _mul(_mul(swap, blender), swap)


def to_frame(matrix, v):
    """World vector -> joint axes (the transpose of an orthonormal matrix inverts it)."""
    return [sum(matrix[r][c] * v[r] for r in range(3)) for c in range(3)]


def own_inertia(rigid):
    """Inertia of a body about its own centre per axis.  Exact for a sphere (every ROE
    breast body); boxes and capsules ignore their own rotation."""
    m = rigid.mass
    if rigid.type == 0:
        return [0.4 * m * rigid.size[0] ** 2] * 3
    if rigid.type == 1:
        x, y, z = (2 * s for s in rigid.size[:3])
        return [m * (y * y + z * z) / 12, m * (x * x + z * z) / 12, m * (x * x + y * y) / 12]
    r, h = rigid.size[0], rigid.size[1]
    return [m * (3 * r * r + h * h) / 12, 0.4 * m * r * r, m * (3 * r * r + h * h) / 12]


def bust_joints(model, pattern):
    names = re.compile(pattern, re.IGNORECASE)
    found = []
    for index, joint in enumerate(model.joints):
        if joint.src_rigid is None or joint.dest_rigid is None:
            continue
        body = model.rigids[joint.dest_rigid]
        if body.mode == 0 or body.bone is None:
            continue
        if names.search(model.bones[body.bone].name) or names.search(joint.name):
            found.append(index)
    return found


def hanging(model, ball):
    """Dynamic bodies hung on ``ball`` through joints (src -> dest), and those joints."""
    out_joints = {}
    for index, joint in enumerate(model.joints):
        out_joints.setdefault(joint.src_rigid, []).append(index)
    bodies, joints, stack = [], [], [ball]
    seen = {ball}
    while stack:
        current = stack.pop()
        for index in out_joints.get(current, []):
            dest = model.joints[index].dest_rigid
            if dest is None or dest in seen or model.rigids[dest].mode == 0:
                continue
            seen.add(dest)
            bodies.append(dest)
            joints.append(index)
            stack.append(dest)
    return bodies, joints


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="new PMX path ('-' with --dry-run)")
    ap.add_argument("--gravity", type=float, default=DEFAULTS["gravity"],
                    help="MMD gravity in model units/s^2 (default %(default)s)")
    ap.add_argument("--sag", type=float, default=DEFAULTS["sag"],
                    help="rest droop in degrees that sizes the pitch spring (default %(default)s)")
    ap.add_argument("--twist-sag", type=float, default=DEFAULTS["twist_sag"],
                    help="rest roll in degrees that sizes the twist spring (default %(default)s)")
    ap.add_argument("--yaw-scale", type=float, default=DEFAULTS["yaw_scale"],
                    help="yaw spring as a multiple of the pitch spring (default %(default)s)")
    ap.add_argument("--spring-pitch", type=float, help="explicit pitch spring (overrides --sag)")
    ap.add_argument("--spring-yaw", type=float, help="explicit yaw spring")
    ap.add_argument("--spring-twist", type=float, help="explicit twist spring (overrides --twist-sag)")
    ap.add_argument("--pitch-limit", type=float, default=DEFAULTS["pitch_limit"],
                    help="+- degrees (default %(default)s)")
    ap.add_argument("--yaw-limit", type=float, default=DEFAULTS["yaw_limit"],
                    help="+- degrees (default %(default)s)")
    ap.add_argument("--twist-limit", type=float, default=DEFAULTS["twist_limit"],
                    help="+- degrees (default %(default)s)")
    ap.add_argument("--lin-damp", type=float, default=DEFAULTS["lin_damp"],
                    help="移動減衰 of the breast body (default %(default)s)")
    ap.add_argument("--ang-damp", type=float, default=DEFAULTS["ang_damp"],
                    help="回転減衰 of the breast body (default %(default)s)")
    ap.add_argument("--mass", type=float, help="breast body mass (default: keep)")
    ap.add_argument("--hanging-scale", type=float, default=DEFAULTS["hanging_scale"],
                    help="mass and joint springs of bodies hung on a breast x this; 1 keeps them "
                         "(default %(default)s)")
    ap.add_argument("--bones", default=DEFAULTS["bones"],
                    help="regex for the breast body's bone or joint name (default %(default)s)")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pmx = load_pmx_module(find_pmx_module(args.pmx_module))
    model = pmx.load(args.input)
    indices = bust_joints(model, args.bones)
    if not indices:
        raise SystemExit("no joint hangs a dynamic body on a breast bone (--bones %r)" % args.bones)

    limits = [math.radians(v) for v in (args.pitch_limit, args.yaw_limit, args.twist_limit)]
    scaled_bodies, scaled_joints = set(), set()
    for index in indices:
        joint = model.joints[index]
        ball = joint.dest_rigid
        body = model.rigids[ball]
        if args.mass is not None:
            body.mass = args.mass
        extra, extra_joints = hanging(model, ball)
        if args.hanging_scale != 1.0:
            for i in extra:
                if i not in scaled_bodies:
                    model.rigids[i].mass *= args.hanging_scale
                    scaled_bodies.add(i)
            for i in extra_joints:
                if i not in scaled_joints:
                    hung = model.joints[i]
                    hung.spring_constant = [v * args.hanging_scale for v in hung.spring_constant]
                    hung.spring_rotation_constant = [v * args.hanging_scale
                                                     for v in hung.spring_rotation_constant]
                    scaled_joints.add(i)

        frame = joint_frame(*joint.rotation)
        down = to_frame(frame, [0.0, -1.0, 0.0])
        torque, moment, own_torque = [0.0] * 3, [0.0] * 3, None
        for i in [ball] + extra:
            rigid = model.rigids[i]
            arm = to_frame(frame, [rigid.location[k] - joint.location[k] for k in range(3)])
            weight = [rigid.mass * args.gravity * c for c in down]
            t = [arm[1] * weight[2] - arm[2] * weight[1],
                 arm[2] * weight[0] - arm[0] * weight[2],
                 arm[0] * weight[1] - arm[1] * weight[0]]
            r2 = sum(c * c for c in arm)
            own = own_inertia(rigid)
            for k in range(3):
                torque[k] += t[k]
                moment[k] += rigid.mass * (r2 - arm[k] ** 2) + own[k]
            if own_torque is None:
                own_torque = t
        pitch = args.spring_pitch if args.spring_pitch is not None else \
            abs(torque[0]) / math.radians(args.sag)
        yaw = args.spring_yaw if args.spring_yaw is not None else pitch * args.yaw_scale
        twist = args.spring_twist if args.spring_twist is not None else \
            max(pitch, abs(torque[2]) / math.radians(args.twist_sag))
        springs = [pitch, yaw, twist]
        freq = [math.sqrt(k / i) / (2 * math.pi) if k > 0 and i > 0 else 0.0 for k, i in zip(springs, moment)]
        rest = [math.degrees(abs(t) / k) if k > 0 else float("inf") for t, k in zip(torque, springs)]
        print("%s: body %s, mass %.2f, %d bodies hung on it (x%.2f); gravity torque pitch %.1f "
              "(its own %.1f), twist %.1f" % (joint.name, model.bones[body.bone].name, body.mass, len(extra),
                                             args.hanging_scale, abs(torque[0]), abs(own_torque[0]),
                                             abs(torque[2])))
        print("   springs pitch/yaw/twist %.0f / %.0f / %.0f -> rest droop %.1f deg, roll %.1f deg;"
              " swing >= %.1f / %.1f / %.1f Hz" % (springs[0], springs[1], springs[2], rest[0], rest[2],
                                                    freq[0], freq[1], freq[2]))
        print("   limits +-%.0f / +-%.0f / +-%.0f deg, damping %.3f / %.3f (was %.3f / %.3f, limits %s deg,"
              " springs %s)" % (args.pitch_limit, args.yaw_limit, args.twist_limit, args.lin_damp,
                                args.ang_damp, body.velocity_attenuation, body.rotation_attenuation,
                                tuple(round(math.degrees(v), 1) for v in joint.maximum_rotation),
                                tuple(round(v, 1) for v in joint.spring_rotation_constant)))
        for axis, limit in enumerate(limits):
            if rest[axis] > math.degrees(limit):
                print("   ! the %s spring cannot hold the body inside its limit" % AXES[axis])
        joint.maximum_rotation = list(limits)
        joint.minimum_rotation = [-v for v in limits]
        joint.spring_rotation_constant = springs
        body.velocity_attenuation = args.lin_damp
        body.rotation_attenuation = args.ang_damp

    if args.dry_run:
        return
    if os.path.abspath(args.output) == os.path.abspath(args.input):
        raise SystemExit("refusing to overwrite the input; write a new file")
    # The pmx module makes texture paths absolute on load and relative to the new
    # file on save, so a copy written elsewhere would point back at the original
    # folder (..\pmx\<stem>\textures\...).  Keep the original relative path when the
    # texture also sits next to the output (the folder was copied with it).
    src_dir, out_dir = os.path.dirname(os.path.abspath(args.input)), os.path.dirname(os.path.abspath(args.output))
    for texture in model.textures:
        local = os.path.join(out_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    pmx.save(args.output, model, add_uv_count=model.header.additional_uvs)
    print("wrote %s (%d breast joints re-tuned, %d hung bodies x%.2f)"
          % (args.output, len(indices), len(scaled_bodies), args.hanging_scale))


if __name__ == "__main__":
    sys.exit(main())
