"""Breast physics sized from MMD's gravity - the joint that hangs each breast body on its static base.

export_pmx.py lays the bust out as the user's MMD template (乳奶1 / 乳奶2: a static body on breast_physics_01, a
dynamic sphere on 02, joint +-10 deg) with an angular spring of 450 (BUST there).  That spring was sized on
2026-09-26 for a gravity of 9.8 model units/s^2; MMD-compatible physics runs 98 (three.js MMDPhysics, saba,
MMDAgent-EX - see scripts/mmd_physics/README.md), and under it (measured 2026-10-04 on all 15 Fiona outfits with
scripts/mmd_physics/mmd_like.py physics):

- standing still, every breast droops 7-12 deg, against its 10 deg limit;
- the limit caps the bounce: at 10 deg the front of the chest moves 1.0-1.7 cm, in a dance about 1 cm;
- PCF_008 hangs eight cloth bodies per side (the hoodie's chest panels) on each breast body - ten times the
  breast's own weight - and its breasts sit on the limit and barely move.

This module re-sizes that joint (the defaults below; first "C" with damping 0.99 and +-18 deg, since the user's
pick later on 2026-10-04 the bigger bounce):

- **Springs from gravity.**  Rest droop = gravity torque / (spring - gravity stiffness), so the spring is
  torque / sag + gravity stiffness.  The torque counts every dynamic body hung on the breast; those bodies' masses
  and their own joint springs are scaled by ``hanging_scale`` first (they swing as before - spring / mass is the
  same - but pull on the breast less).  The gravity stiffness is the rig's geometry: breast_physics_02's head sits
  low in the breast and the body (the centre of the skin it moves) 1.5-7.6 cm above it, an inverted pendulum whose
  torque grows as it tips.  Sized without that term, a spring meant for 8 deg left PCF_002 at 11 deg and one meant
  for 15 deg on its 25 deg limit.
- **Limits** pitch / yaw / twist 25 / 15 / 5 deg.  Turned onto its limit in a still pose, the skin pokes through
  the clothes at the neckline on five outfits at 25 deg (default armour, PCF_003 / 005 / 006 / 008: up to 57
  vertices, 1.7 cm), at 18 deg 0.8 cm at most - ``pitch_limit=18`` where that shows.
- **Damping** 0.5 (移動 and 回転減衰).  0.99 settled in about a second with a bounce twice the template's (shake
  dance swing 10-90 % 5.6-8.6 -> 13-20 deg at the same mean droop); the user, trying values live in Blender,
  wanted more: 0.5 with the 25 deg limit swings PCF_005 14.2-15.9 deg in the gesture dance (0.99 / 18 deg:
  11.4-13.1, the template 8.1-8.9), peaks 29-30 (23-24, 16-17.5).

Every value has a default (DEFAULTS) and can be overridden.

    python bust_physics.py in.pmx out.pmx                              # a finished PMX, no Blender
    python bust_physics.py in.pmx out.pmx --sag 10 --pitch-limit 20   # other values
    python bust_physics.py in.pmx out.pmx --hanging-only               # only lighten what hangs on the breasts
    python bust_physics.py in.pmx - --dry-run                          # print what it would do

export_pmx.py calls tune_scene() on the mmd_tools objects before it writes the PMX.  A tuned PMX carries MARK in
its comment; the command line refuses to tune it again (the hung bodies would be lightened twice).

Joint axes are the joint's own (rotation 0 = model axes): pitch = left-right axis (up / down swing), yaw = vertical
axis, twist = front-back axis - the PMX order of a joint's limit and spring triples.
"""
import argparse
import glob
import importlib.util
import math
import os
import re
import sys

DEFAULTS = {
    "gravity": 98.0,        # model units / s^2 (9.8 x 10, see above)
    "sag": 8.0,             # degrees the breast droops at rest (pitch): sizes the pitch spring
    "twist_sag": 4.0,       # degrees it may roll about the front-back axis at rest: sizes the twist spring
    "yaw_scale": 1.0,       # yaw spring = pitch spring x this
    "pitch_limit": 25.0,    # +- degrees (18: the calmer "C")
    "yaw_limit": 15.0,
    "twist_limit": 5.0,
    "lin_damp": 0.5,        # 移動減衰 of the breast body (0.99: "C")
    "ang_damp": 0.5,        # 回転減衰
    "hanging_scale": 0.2,   # mass and joint springs of the dynamic bodies hung on a breast
    "bones": r"胸|乳|chest|breast|bust|oppai",
}
AXES = ("pitch", "yaw", "twist")
MARK = "bust physics sized for gravity 98 (scripts/vindictus/bust_physics.py)"


# -- the sizing -----------------------------------------------------------------------------------
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def own_inertia(shape, size, mass):
    """A body's inertia about its own centre per axis (PMX shape 0 sphere / 1 box / 2 capsule, PMX size)."""
    if shape == 0:
        return (0.4 * mass * size[0] ** 2,) * 3
    if shape == 1:
        x, y, z = (2 * s for s in size[:3])
        return (mass * (y * y + z * z) / 12, mass * (x * x + z * z) / 12, mass * (x * x + y * y) / 12)
    r, h = size[0], size[1]
    return (mass * (3 * r * r + h * h) / 12, 0.4 * mass * r * r, mass * (3 * r * r + h * h) / 12)


def size_joint(bodies, down, params):
    """Springs for one breast joint.

    ``bodies``: (mass, arm, own inertia) of the breast body and of every body hung on it (masses as they will be
    written), ``arm`` = body centre - joint, both in the joint's axes and in model units; ``down`` the unit gravity
    direction in the joint's axes.  Per axis k: gravity torque t = sum arm x (m g down); gravity stiffness G =
    sum (arm_k w_k - arm . w) - how much that torque grows per radian of rotation (positive = the body sits above
    the pivot and tips over); inertia about the pivot.  Spring = |t| / sag + G, so the body rests ``sag`` from its
    modelled place, and never less than half of |t| / sag (a body far below the pivot would need almost none)."""
    torque, stiff, moment = [0.0] * 3, [0.0] * 3, [0.0] * 3
    for mass, arm, own in bodies:
        w = [mass * params["gravity"] * c for c in down]
        t = _cross(arm, w)
        aw = _dot(arm, w)
        r2 = _dot(arm, arm)
        for k in range(3):
            torque[k] += t[k]
            stiff[k] += arm[k] * w[k] - aw
            moment[k] += mass * (r2 - arm[k] ** 2) + own[k]

    def spring(k, sag_deg, at_least=0.0):
        plain = abs(torque[k]) / math.radians(sag_deg)
        return max(plain + stiff[k], 0.5 * plain, at_least, 1.0)

    pitch = spring(0, params["sag"])
    yaw = spring(1, params["sag"], pitch * params["yaw_scale"])
    twist = spring(2, params["twist_sag"], pitch)
    springs = (pitch, yaw, twist)
    net = [k - g for k, g in zip(springs, stiff)]
    return {
        "springs": tuple(round(k, 1) for k in springs),
        "torque": tuple(round(abs(t), 2) for t in torque),
        "gravity_stiffness": tuple(round(g, 2) for g in stiff),
        "rest_deg": tuple(round(math.degrees(abs(t) / n), 1) if n > 0 else None for t, n in zip(torque, net)),
        "hz": tuple(round(math.sqrt(n / i) / (2 * math.pi), 2) if n > 0 and i > 0 else 0.0
                    for n, i in zip(net, moment)),
    }


def limits_rad(params):
    return tuple(math.radians(params[a + "_limit"]) for a in AXES)


def joint_frame(rx, ry, rz):
    """Axes of a PMX joint (rotation as written in the PMX) in PMX coordinates, the way mmd_tools reads them:
    Blender Euler (-rx, -rz, -ry) in 'YXZ' order on y/z-swapped axes.  Identity for rotation 0."""
    def rot(axis, angle):
        c, s = math.cos(angle), math.sin(angle)
        return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]], "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
                "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    swap = [[1, 0, 0], [0, 0, 1], [0, 1, 0]]
    return mul(mul(swap, mul(mul(rot("z", -ry), rot("x", -rx)), rot("y", -rz))), swap)


def to_frame(frame, v):
    return tuple(sum(frame[r][c] * v[r] for r in range(3)) for c in range(3))


# -- graph shared by both front ends ----------------------------------------------------------------
def breast_joints(joints, bodies, bone_name, pattern):
    """Joint indices that hang a dynamic body on a breast bone from a bone-following (static) body - the template's
    base.  ``joints``: (src, dest) body indices; ``bodies``: their mode (0 static).  Cloth hung on a breast (PCF_008's
    chest panels, bones *_breast_shirt_*) hangs from a dynamic body and is no breast."""
    names = re.compile(pattern, re.IGNORECASE)
    out = []
    for index, (src, dest) in enumerate(joints):
        if src is None or dest is None or bodies[dest] == 0 or bodies[src] != 0:
            continue
        name = bone_name(dest)
        if name and names.search(name):
            out.append(index)
    return out


def hung_on(joints, bodies, ball):
    """Dynamic bodies hung on ``ball`` through joints (src -> dest, any depth) and those joints."""
    by_src = {}
    for index, (src, _dest) in enumerate(joints):
        by_src.setdefault(src, []).append(index)
    found, links, stack, seen = [], [], [ball], {ball}
    while stack:
        current = stack.pop()
        for index in by_src.get(current, []):
            dest = joints[index][1]
            if dest is None or dest in seen or bodies[dest] == 0:
                continue
            seen.add(dest)
            found.append(dest)
            links.append(index)
            stack.append(dest)
    return found, links


# -- a finished PMX (mmd_tools' pmx module, plain Python) ---------------------------------------------
def load_pmx_module(explicit=None):
    if not explicit:
        try:
            from mmd_tools.core import pmx           # inside Blender
            return pmx
        except ImportError:
            pass
        roots = [os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")]
        for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
            hits = sorted(glob.glob(os.path.join(roots[0], pattern)))
            if hits:
                explicit = hits[0]
                break
        else:
            raise SystemExit("mmd_tools' core/pmx/__init__.py not found; pass --pmx-module")
    spec = importlib.util.spec_from_file_location("mmd_pmx", explicit)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _index(value):
    return None if value is None or value < 0 else value


def tune_model(model, params, hanging_only=False):
    """Re-size every breast joint of a loaded PMX model in place; returns one report line per breast."""
    pairs = [(_index(j.src_rigid), _index(j.dest_rigid)) for j in model.joints]
    modes = [r.mode for r in model.rigids]
    bone = (lambda i: model.bones[model.rigids[i].bone].name if _index(model.rigids[i].bone) is not None else "")
    report, scaled_bodies, scaled_joints = [], set(), set()
    for index in breast_joints(pairs, modes, bone, params["bones"]):
        joint = model.joints[index]
        ball = pairs[index][1]
        extra, links = hung_on(pairs, modes, ball)
        for i in extra:
            if i not in scaled_bodies:
                model.rigids[i].mass *= params["hanging_scale"]
                scaled_bodies.add(i)
        for i in links:
            if i not in scaled_joints:
                hung = model.joints[i]
                hung.spring_constant = [v * params["hanging_scale"] for v in hung.spring_constant]
                hung.spring_rotation_constant = [v * params["hanging_scale"] for v in hung.spring_rotation_constant]
                scaled_joints.add(i)
        frame = joint_frame(*joint.rotation)
        down = to_frame(frame, (0.0, -1.0, 0.0))
        bodies = []
        for i in [ball] + extra:
            r = model.rigids[i]
            arm = to_frame(frame, [r.location[k] - joint.location[k] for k in range(3)])
            bodies.append((r.mass, arm, own_inertia(r.type, r.size, r.mass)))
        body = model.rigids[ball]
        line = {"joint": joint.name, "bone": bone(ball), "hung_bodies": len(extra)}
        if hanging_only:
            line["kept"] = {"springs": tuple(joint.spring_rotation_constant),
                            "limits_deg": tuple(round(math.degrees(v), 1) for v in joint.maximum_rotation)}
        else:
            sized = size_joint(bodies, down, params)
            line.update(sized)
            limits = limits_rad(params)
            joint.maximum_rotation = list(limits)
            joint.minimum_rotation = [-v for v in limits]
            joint.spring_rotation_constant = list(sized["springs"])
            body.velocity_attenuation = params["lin_damp"]
            body.rotation_attenuation = params["ang_damp"]
            line["limits_deg"] = tuple(params[a + "_limit"] for a in AXES)
            line["damping"] = (params["lin_damp"], params["ang_damp"])
        report.append(line)
    return report


def tune_file(src, dst, params, hanging_only=False, dry_run=False, force=False, pmx_module=None):
    pmx = load_pmx_module(pmx_module)
    model = pmx.load(src)
    if MARK in (model.comment or "") and not force:
        raise SystemExit("%s is tuned already (its comment says so); --force tunes it again" % src)
    report = tune_model(model, params, hanging_only)
    if not report:
        raise SystemExit("no joint hangs a dynamic breast body from a static one (--bones %r)" % params["bones"])
    if dry_run:
        return report
    if os.path.abspath(dst) == os.path.abspath(src):
        raise SystemExit("refusing to overwrite the input; write a new file")
    # the pmx module makes texture paths absolute on load and relative to the new file on save: a copy written
    # elsewhere points back at the original's textures\ (keep the old relative path when textures\ was copied too)
    src_dir, dst_dir = os.path.dirname(os.path.abspath(src)), os.path.dirname(os.path.abspath(dst))
    for texture in model.textures:
        local = os.path.join(dst_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    note = MARK + (" - only the bodies hung on the breasts lightened" if hanging_only else "")
    model.comment = ((model.comment or "").rstrip() + "\r\n" + note).lstrip()
    model.comment_e = ((model.comment_e or "").rstrip() + "\r\n" + note).lstrip()
    pmx.save(dst, model, add_uv_count=model.header.additional_uvs)
    return report


# -- the mmd_tools objects in Blender (export_pmx.py) -------------------------------------------------
def tune_scene(scene, params, scale=12.5, hanging_only=False):
    """The same on an mmd_tools model before export: rigid bodies / joints as objects, Blender axes (x, y, z) =
    PMX (x, z, y) / scale, so a joint's PMX pitch / yaw / twist are its Blender x / z / y."""
    from mathutils import Vector

    rigids = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.rigid_body]
    joints = [o for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT" and o.rigid_body_constraint]
    where = {o: i for i, o in enumerate(rigids)}
    pairs = [(where.get(j.rigid_body_constraint.object1), where.get(j.rigid_body_constraint.object2)) for j in joints]
    modes = [int(o.mmd_rigid.type) for o in rigids]

    def pmx_point(obj):
        return Vector(obj.matrix_world.translation).xzy * scale

    def pmx_size(obj):
        size = Vector(obj.mmd_rigid.size) * (sum(obj.matrix_world.to_scale()) / 3) * scale
        shape = {"SPHERE": 0, "BOX": 1, "CAPSULE": 2}[obj.mmd_rigid.shape]
        return shape, (size.xzy if shape == 1 else size)

    report, scaled_bodies, scaled_joints = [], set(), set()
    for index in breast_joints(pairs, modes, lambda i: rigids[i].mmd_rigid.bone, params["bones"]):
        joint = joints[index]
        ball = pairs[index][1]
        extra, links = hung_on(pairs, modes, ball)
        for i in extra:
            if i not in scaled_bodies:
                rigids[i].rigid_body.mass *= params["hanging_scale"]
                scaled_bodies.add(i)
        for i in links:
            if i not in scaled_joints:
                mj = joints[i].mmd_joint
                mj.spring_linear = tuple(v * params["hanging_scale"] for v in mj.spring_linear)
                mj.spring_angular = tuple(v * params["hanging_scale"] for v in mj.spring_angular)
                scaled_joints.add(i)
        rotation = Vector(joint.matrix_world.to_euler("YXZ")).xzy * -1
        frame = joint_frame(*rotation)
        down = to_frame(frame, (0.0, -1.0, 0.0))
        origin = pmx_point(joint)
        bodies = []
        for i in [ball] + extra:
            obj = rigids[i]
            shape, size = pmx_size(obj)
            arm = to_frame(frame, tuple(pmx_point(obj) - origin))
            bodies.append((obj.rigid_body.mass, arm, own_inertia(shape, size, obj.rigid_body.mass)))
        line = {"joint": joint.mmd_joint.name_j or joint.name, "bone": rigids[ball].mmd_rigid.bone,
                "hung_bodies": len(extra)}
        if not hanging_only:
            sized = size_joint(bodies, down, params)
            line.update(sized)
            pitch, yaw, twist = sized["springs"]
            joint.mmd_joint.spring_angular = (pitch, twist, yaw)         # Blender order x, y, z
            rbc = joint.rigid_body_constraint
            for axis, name in (("x", "pitch"), ("y", "twist"), ("z", "yaw")):
                limit = math.radians(params[name + "_limit"])
                setattr(rbc, "limit_ang_%s_lower" % axis, -limit)
                setattr(rbc, "limit_ang_%s_upper" % axis, limit)
            body = rigids[ball].rigid_body
            body.linear_damping = params["lin_damp"]
            body.angular_damping = params["ang_damp"]
            line["limits_deg"] = tuple(params[a + "_limit"] for a in AXES)
            line["damping"] = (params["lin_damp"], params["ang_damp"])
        report.append(line)
    return report


def describe(line):
    if "springs" not in line:
        return "%s (%s): %d bodies hung on it lightened, joint kept %s" % (
            line["joint"], line["bone"], line["hung_bodies"], line.get("kept"))
    return ("%s (%s), %d bodies hung on it: gravity torque pitch/yaw/twist %s, gravity stiffness %s -> springs %s, "
            "rest %s deg, swing %s Hz, limits +-%s deg, damping %s" % (
                line["joint"], line["bone"], line["hung_bodies"], line["torque"], line["gravity_stiffness"],
                line["springs"], line["rest_deg"], line["hz"], line["limits_deg"], line["damping"]))


def parse_overrides(text):
    """'sag=10,pitch_limit=20' -> {"sag": 10.0, "pitch_limit": 20.0} (keys of DEFAULTS)."""
    out = {}
    for item in filter(None, (part.strip() for part in (text or "").split(","))):
        key, _, value = item.partition("=")
        key = key.strip().replace("-", "_")
        if key not in DEFAULTS:
            raise SystemExit("unknown bust setting %r (known: %s)" % (key, ", ".join(DEFAULTS)))
        out[key] = value.strip() if key == "bones" else float(value)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output", help="the new PMX ('-' with --dry-run)")
    for key, value in DEFAULTS.items():
        kind = str if key == "bones" else float
        ap.add_argument("--" + key.replace("_", "-"), type=kind, default=value, help="default %(default)s")
    ap.add_argument("--hanging-only", action="store_true",
                    help="only scale the bodies hung on the breasts; the breast joint keeps its values")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="tune a PMX that was tuned before")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    args = ap.parse_args(argv)
    params = {key: getattr(args, key) for key in DEFAULTS}
    report = tune_file(args.input, args.output, params, args.hanging_only, args.dry_run, args.force,
                       args.pmx_module)
    for line in report:
        print(describe(line))
    print("dry run, nothing written" if args.dry_run else "wrote %s" % args.output)


if __name__ == "__main__":
    sys.exit(main())
