"""Vindictus XPS -> MMD PMX with expressions, bust physics and hair physics (Blender 3.6, background).

    blender -b --python export_pmx.py -- --xps <model.xps> --dna <face.dna> --out <dir>
            [--name Fiona_BaseBody] [--model-name Fiona] [--no-physics] [--no-morphs]

The conversion is the hand route of docs/vindictus-fiona-manual-export.md 6.10 (XNALaraMesh
import -> Convert to MMD 5 with four slots corrected -> one-click with auto-identify off), then:

1. 両目 - the ROE worker's add_both_eyes_bone (grant rate 1, eyes on transform layer 1).
2. Expressions - the face is a MetaHuman: no shape keys, ~630 FACIAL_* joints moved by RigLogic
   from 269 raw controls.  metahuman_dna.DnaFace evaluates the face's own DNA (extracted from
   the game by ``metahuman_dna.py extract``) for each MMD morph's control mix (RECIPES), and
   every joint's rest -> posed world motion becomes a bone-morph offset on the rig.  The DNA's
   neutral skeleton is fitted to the rig first (similarity transform; Fiona: 0.38 mm mean).
3. Physics - Convert to MMD 5's body colliders; the bust laid out as in the user's MMD template
   (static body on ``Bip001_*_bust_1``, dynamic sphere on ``Bip001_*_bust_2``, joint +-10 deg,
   a group that collides with nothing) plus an angular spring (see BUST); hair chains by mmd_cloth_physics with the
   ``FACIAL_*`` joints counted as body (the MetaHuman hairline joints are named ``*Hair*`` and
   are face skin, not hair); then bodies that start inside a collider stop colliding with it.
   The game weights the breast skin to ``bust_2`` at 0.24 at most - a swinging body would move
   the skin by millimetres - so those weights are scaled up to 0.75 at the peak (the extra comes
   from the vertex's other bones, the T-shirt gets the same factor as the skin under it).
4. PMX at scale 12.5 with textures, the ROE grant-order check, the converted .blend and a
   JSON report next to it.
"""
import argparse
import importlib.util
import json
import math
import os
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "blender_addons"))      # mmd_cloth_physics
import metahuman_dna  # noqa: E402

WORKER = os.path.join(REPO, "scripts", "riseoferos", "export_character_model_blender.py")

# Convert to MMD 5 identifies roles by topology + geometry; on a Vindictus XPS (Biped body,
# MetaHuman face, names mapped by Blender2XPS) these four come out wrong - see the tutorial 6.10.
SLOT_FIX = {"center_bone": "", "lower_body_bone": "Bip001_Pelvis", "head_bone": "head neck upper",
            "left_eye_bone": "head eyeball left", "right_eye_bone": "head eyeball right"}
# Blender2XPS renames (report "改名的骨骼") that the facial joints went through, then Convert to MMD 5
XPS_NAMES = {"FACIAL_L_Eye": "head eyeball left", "FACIAL_R_Eye": "head eyeball right", "FACIAL_C_Jaw": "head jaw"}
MMD_NAMES = {"head eyeball left": "左目", "head eyeball right": "右目"}

PURSE = ("mouthLipsPurseUL", "mouthLipsPurseUR", "mouthLipsPurseDL", "mouthLipsPurseDR")
FUNNEL = ("mouthFunnelUL", "mouthFunnelUR", "mouthFunnelDL", "mouthFunnelDR")


def both(stem, value):
    return {stem + "L": value, stem + "R": value}


def mix(*parts):
    out = {}
    for part in parts:
        out.update(part)
    return out


# The standard MMD set (the same names and mixes as the Stellar Blade Fiona, ARKit -> MetaHuman
# raw controls).  Categories are the PMX expression panels.
RECIPES = [
    ("まばたき", "blink", "EYE", both("eyeBlink", 1.0)),
    ("笑い", "smile", "EYE", mix(both("eyeBlink", 0.85), both("eyeSquintInner", 0.5), both("eyeCheekRaise", 0.6))),
    ("ウィンク", "wink", "EYE", {"eyeBlinkL": 1.0, "eyeSquintInnerL": 0.4, "eyeCheekRaiseL": 0.4}),
    ("ウィンク右", "wink_R", "EYE", {"eyeBlinkR": 1.0, "eyeSquintInnerR": 0.4, "eyeCheekRaiseR": 0.4}),
    ("ウィンク２", "wink2", "EYE", {"eyeBlinkL": 1.0}),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", {"eyeBlinkR": 1.0}),
    ("びっくり", "surprised", "EYE", mix(both("eyeWiden", 1.0), both("eyeUpperLidUp", 0.5))),
    ("じと目", "jito-eye", "EYE", both("eyeBlink", 0.45)),
    ("はぅ", "close><", "EYE", mix(both("eyeBlink", 1.0), both("eyeSquintInner", 1.0), both("eyeCheekRaise", 0.6))),
    ("真面目", "serious", "EYEBROW", both("browDown", 0.35)),
    ("困る", "trouble", "EYEBROW", both("browRaiseIn", 1.0)),
    ("にこり", "cheerful", "EYEBROW", both("browRaiseOuter", 0.6)),
    ("怒り", "anger", "EYEBROW", mix(both("browDown", 1.0), both("browLateral", 0.6))),
    ("上", "brow_up", "EYEBROW", mix(both("browRaiseIn", 0.6), both("browRaiseOuter", 0.8))),
    ("下", "brow_down", "EYEBROW", both("browDown", 0.6)),
    ("あ", "a", "MOUTH", mix({"jawOpen": 0.6}, both("mouthLowerLipDepress", 0.3), both("mouthUpperLipRaise", 0.2))),
    ("い", "i", "MOUTH", mix({"jawOpen": 0.08}, both("mouthStretch", 0.8), both("mouthUpperLipRaise", 0.3),
                              both("mouthLowerLipDepress", 0.3))),
    ("う", "u", "MOUTH", mix({"jawOpen": 0.05}, {k: 1.0 for k in PURSE}, {k: 0.3 for k in FUNNEL})),
    ("え", "e", "MOUTH", mix({"jawOpen": 0.3}, both("mouthStretch", 0.5), both("mouthLowerLipDepress", 0.3))),
    ("お", "o", "MOUTH", mix({"jawOpen": 0.45}, {k: 0.8 for k in FUNNEL}, {k: 0.3 for k in PURSE})),
    # full mouthCornerPull bunches the cheeks into lumps (no corrective shapes on a bone-only face)
    ("にやり", "grin", "MOUTH", both("mouthCornerPull", 0.8)),
    ("にっこり", "smile_mouth", "MOUTH", both("mouthCornerPull", 0.6)),
    ("∧", "mouth_∧", "MOUTH", both("mouthCornerDepress", 1.0)),
    ("口角上げ", "mouth_corner_up", "MOUTH", both("mouthCornerPull", 0.45)),
    ("口角下げ", "mouth_corner_down", "MOUTH", both("mouthCornerDepress", 0.6)),
    ("口横広げ", "mouth_wide", "MOUTH", both("mouthStretch", 0.6)),
]

# The user's template has no joint spring, so gravity parks the breast on its 10 deg limit.  With
# Vindictus' weights that showed: standing, both breasts sat visibly lower than modelled and the right
# one creased along the upper edge where bust_2's weight falls off (dance frames 80 / 360).  An angular
# spring holds the modelled shape and the breast bounces around it.  Size it in MMD units (1 unit ~ 8 cm,
# gravity 9.8 units/s^2): the sphere hangs ~1.56 units in front of the pivot, so gravity torque is
# ~15 and a spring of 450 leaves ~2 deg of rest sag and bounces at ~2 Hz.  The Stellar Blade Fiona's 120
# looks right in a metre-scale Blender preview but sags ~10 deg at MMD scale (measured by importing at 1.0).
BUST = {
    "sides": (("Bip001_L_bust_1", "Bip001_L_bust_2"), ("Bip001_R_bust_1", "Bip001_R_bust_2")),
    "boost_to": 0.75, "limit_deg": 10.0, "spring": 450.0, "mass": 1.0, "lin_damp": 0.5, "ang_damp": 0.5,
    "friction": 0.5, "group": 15, "radius": (0.03, 0.06), "base_radius": 0.024, "centre_weight": 0.3,
}
HAIR_BODY_REGEX = r"^(Bip0\d\d|FACIAL_)"
# Fiona's hair is a sculpted bob.  mmd_cloth_physics' "hair" preset (+-10 deg per joint, no spring,
# root row simulated) is made for hair that hangs; on the bob the front and side strands fell over
# the face within a second of standing still (tips moved 24 cm).  "ornament" keeps the shape with
# springs and lets it jiggle.
HAIR_PRESET = os.environ.get("VINDICTUS_HAIR_PRESET", "ornament")
HAIR_FREE_BELOW_EYES = 0.03          # metres: hair below this line under the eyes swings (see anchor_scalp_hair)


def log(msg):
    print("[vindictus pmx] " + msg, flush=True)


def load_worker():
    spec = importlib.util.spec_from_file_location("roe_char_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def activate(obj):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def live_armature():
    return next(o for o in bpy.context.scene.objects
                if o.type == "ARMATURE" and "backup" not in o.name.lower() and not o.name.startswith("."))


# -- 1. import + convert -----------------------------------------------------------------------
def import_and_convert(xps):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.xps_tools.import_model(filepath=xps)          # XNALaraMesh defaults, as in the GUI
    arm = live_armature()
    arm.scale = (1.0, 1.0, 1.0)                            # the 214-unit trap (tutorial 6.10 step 2)
    activate(arm)
    bpy.ops.object.auto_identify_skeleton()
    scene = bpy.context.scene
    for prop, bone in SLOT_FIX.items():
        if bone == "" or bone in arm.data.bones:
            setattr(scene, prop, bone)
    if bpy.ops.object.one_click_convert(auto_identify=False, minimal=False) != {"FINISHED"}:
        raise RuntimeError("Convert to MMD 5 one-click conversion failed")
    arm = live_armature()
    root = arm
    while root.parent is not None:
        root = root.parent
    if getattr(root, "mmd_type", "") != "ROOT":
        raise RuntimeError("no mmd root after the conversion")
    return root, arm


# -- 2. expressions from the DNA ---------------------------------------------------------------
def build_face_morphs(root, arm, face):
    bones = arm.data.bones
    joints = {}
    for j, name in enumerate(face.joints):
        if not name.startswith("FACIAL_"):
            continue
        target = XPS_NAMES.get(name, name)
        target = MMD_NAMES.get(target, target)
        if target not in bones:
            target = "unused_" + target
        if target in bones:
            joints[j] = target
    index = sorted(joints)
    src = face.rest[index, :3, 3]
    dst = np.array([list(bones[joints[j]].head_local) for j in index])
    scale, rot, shift, err = metahuman_dna.fit_similarity(src, dst)
    fit = {"joints": len(index), "scale": round(float(scale), 6), "mean_mm": round(float(err.mean()) * 1000, 2),
           "max_mm": round(float(err.max()) * 1000, 2)}
    log("DNA fitted to %(joints)d joints: scale %(scale)s, error mean %(mean_mm)s mm, max %(max_mm)s mm" % fit)

    # translated joints must not be connected to their parent's tail
    activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for j in index:
        arm.data.edit_bones[joints[j]].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")

    rest = {joints[j]: bones[joints[j]].matrix_local.copy() for j in index}
    mmd_root = root.mmd_root
    made = []
    for name, name_e, category, controls in RECIPES:
        posed = face.posed(controls)
        want = {}
        for j in index:
            delta_rot = posed[j][:3, :3] @ face.rest[j][:3, :3].T
            move = scale * (rot @ (posed[j][:3, 3] - face.rest[j][:3, 3]))
            spin = Matrix((rot @ delta_rot @ rot.T).tolist()).to_4x4()
            head = bones[joints[j]].head_local
            want[joints[j]] = (Matrix.Translation(head + Vector(move.tolist())) @ spin
                               @ Matrix.Translation(-head) @ rest[joints[j]])
        items = []
        for bone_name, posed_matrix in want.items():
            bone = bones[bone_name]
            if bone.parent is not None:
                parent_pose = want.get(bone.parent.name, bone.parent.matrix_local)
                basis = ((bone.parent.matrix_local.inverted() @ bone.matrix_local).inverted()
                         @ parent_pose.inverted() @ posed_matrix)
            else:
                basis = bone.matrix_local.inverted() @ posed_matrix
            loc, quat, _scale = basis.decompose()
            if loc.length > 1e-5 or quat.angle > math.radians(0.02):
                items.append((bone_name, loc, quat))
        if not items:
            log("morph %s moves nothing - skipped" % name)
            continue
        morph = mmd_root.bone_morphs.add()
        morph.name, morph.name_e, morph.category = name, name_e, category
        for bone_name, loc, quat in items:
            item = morph.data.add()
            item.bone, item.location, item.rotation = bone_name, loc, quat
        made.append({"name": name, "bones": len(items),
                     "max_move_mm": round(max(loc.length for _b, loc, _q in items) * 1000, 1)})
    from mmd_tools.operators.display_item import DisplayItemQuickSetup

    frames = mmd_root.display_item_frames
    if "表情" in frames:
        frames["表情"].data.clear()
    DisplayItemQuickSetup.load_facial_items(mmd_root)
    log("expressions: %d bone morphs (%s)" % (len(made), " ".join(m["name"] for m in made)))
    return {"fit": fit, "morphs": made}


# -- 3. physics ---------------------------------------------------------------------------------
def boost_bust_weights(meshes, swing_names, target):
    """Scale the swing bones' weights so their peak is ``target``; the added weight comes out of
    the vertex's other bones in proportion, so every vertex still sums to what it did."""
    peak = 0.0
    for mesh in meshes:
        idx = {g.index for g in mesh.vertex_groups if g.name in swing_names}
        for v in mesh.data.vertices:
            for g in v.groups:
                if g.group in idx:
                    peak = max(peak, g.weight)
    if peak <= 0.0 or peak >= target:
        return {"peak_before": round(peak, 3), "factor": 1.0, "vertices": 0}
    factor = target / peak
    # The gain grows with the weight itself: the peak gets the full factor, the rim (30% of the peak)
    # only ~1.2x.  A flat factor steepened the rim 3x and the upper breast creased when it swung.
    gain = lambda w: 1.0 + (factor - 1.0) * (w / peak) ** 2  # noqa: E731
    changed = 0
    for mesh in meshes:
        groups = {g.index: g for g in mesh.vertex_groups}
        swing = {g.index for g in mesh.vertex_groups if g.name in swing_names}
        if not swing:
            continue
        for v in mesh.data.vertices:
            own = [(g.group, g.weight) for g in v.groups if g.group in swing and g.weight > 0.0]
            if not own:
                continue
            others = [(g.group, g.weight) for g in v.groups if g.group not in swing and g.weight > 0.0]
            pool = sum(w for _g, w in others)
            for gi, w in own:
                extra = min(w * gain(w), 1.0) - w
                take = min(extra, pool)
                if take <= 0.0:
                    continue
                for oi, ow in others:
                    groups[oi].add([v.index], ow - take * ow / pool, "REPLACE")
                others = [(oi, ow - take * ow / pool) for oi, ow in others]
                pool -= take
                groups[gi].add([v.index], w + take, "REPLACE")
            changed += 1
    return {"peak_before": round(peak, 3), "factor": round(factor, 3), "vertices": changed}


def add_bust_physics(root, arm, meshes):
    """The user's MMD template (标准骨骼与刚体.pmx 乳奶1/乳奶2, as ROE's add_bust_physics)."""
    from mmd_tools.core.model import Model

    model = Model(root)
    rigids = {o.mmd_rigid.bone: o for o in bpy.context.scene.objects
              if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.bone}
    bones = arm.data.bones
    limit = math.radians(BUST["limit_deg"])
    nothing = [True] * 16
    common = dict(collision_group_number=BUST["group"], collision_group_mask=nothing, mass=BUST["mass"],
                  friction=BUST["friction"], linear_damping=BUST["lin_damp"], angular_damping=BUST["ang_damp"],
                  bounce=0.0)
    report = []
    for base_name, swing_name in BUST["sides"]:
        base, swing = bones.get(base_name), bones.get(swing_name)
        if base is None or swing is None or swing_name in rigids:
            report.append("%s: missing or already built" % swing_name)
            continue
        points, weights = [], []
        for mesh in meshes:
            group = mesh.vertex_groups.get(swing_name)
            if group is None:
                continue
            for v in mesh.data.vertices:
                w = next((g.weight for g in v.groups if g.group == group.index), 0.0)
                if w >= BUST["centre_weight"]:
                    points.append(mesh.matrix_world @ v.co)
                    weights.append(w)
        if not points:
            report.append("%s: no skin" % swing_name)
            continue
        centre = sum((p * w for p, w in zip(points, weights)), Vector()) / sum(weights)
        spread = sorted((p - centre).length for p in points)
        low, high = BUST["radius"]
        radius = min(high, max(low, 0.8 * spread[int(0.75 * (len(spread) - 1))]))
        anchor = rigids.get(base_name) or model.createRigidBody(
            shape_type=0, location=(base.head_local + swing.head_local) * 0.5, rotation=(0.0, 0.0, 0.0),
            size=(BUST["base_radius"], 0.0, 0.0), dynamics_type=0, name=base_name, bone=base_name, **common)
        rigids[base_name] = anchor
        body = model.createRigidBody(shape_type=0, location=centre, rotation=(0.0, 0.0, 0.0),
                                     size=(radius, 0.0, 0.0), dynamics_type=1, name=swing_name,
                                     bone=swing_name, **common)
        rigids[swing_name] = body
        model.createJoint(name=swing_name, location=swing.head_local.copy(), rotation=(0.0, 0.0, 0.0),
                          rigid_a=anchor, rigid_b=body, maximum_location=(0.0, 0.0, 0.0),
                          minimum_location=(0.0, 0.0, 0.0), maximum_rotation=(limit,) * 3,
                          minimum_rotation=(-limit,) * 3, spring_linear=(0.0, 0.0, 0.0),
                          spring_angular=(BUST["spring"],) * 3)
        report.append("%s swings on %s: sphere r %.1f cm, %.1f cm in front of the pivot, %d verts"
                      % (swing_name, base_name, radius * 100, (centre - swing.head_local).length * 100, len(points)))
    return report


def anchor_scalp_hair(arm, garments, below_eyes=HAIR_FREE_BELOW_EYES):
    """Bones of a hair chain that still lie on the head follow the head bone (rigid body mode 0).

    Fiona's bob parts at the front of the crown and its longest strands (``Fiona_hair_d_*``,
    8-9 bones, 20-27 cm) sweep over the top of the head to the side, ending around the eyes.
    Simulated from the root, the whole strand slid off the skull and hung over the face within a
    second (tips 10-14 cm down and forward at MMD scale, with either preset); the head collider
    cannot stop it - Convert to MMD 5 sizes it from the face, a 7 cm sphere at jaw height.  So a
    chain is anchored from its root while each bone's tail is still above ear level (``below_eyes``
    under the eyes) and simulated from the first bone that reaches below it, down to the tip.
    Returns (anchored bodies, swinging bodies)."""
    bones = arm.data.bones
    line = (bones["左目"].head_local.z + bones["右目"].head_local.z) / 2 - below_eyes
    bodies = {o.mmd_rigid.bone: o for o in bpy.context.scene.objects
              if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.bone}
    anchored = swinging = 0
    for garment in garments:
        for chain in garment.chains:
            on_head = True
            for name in chain:
                body = bodies.get(name)
                if body is None:
                    continue
                if on_head and bones[name].tail_local.z > line:
                    body.mmd_rigid.type = "0"
                    anchored += 1
                else:
                    on_head = False
                    swinging += 1
    log("hair: %d bodies follow the head (tail above z %.3f), %d swing" % (anchored, line, swinging))
    return anchored, swinging


def add_physics(root, arm, meshes, roe):
    out = {}
    activate(arm)
    out["body"] = "ok" if bpy.ops.object.add_body_rigids() == {"FINISHED"} else "cancelled"
    out["bust_weights"] = boost_bust_weights(meshes, {s for _b, s in BUST["sides"]}, BUST["boost_to"])
    out["bust"] = add_bust_physics(root, arm, meshes)
    from mmd_cloth_physics import api as cloth_api

    garments = cloth_api.analyze_model(root, HAIR_BODY_REGEX, r"\bProp\d*$", True)
    for garment in garments:
        if garment.preset == "hair":
            garment.preset = HAIR_PRESET
    report = cloth_api.setup(root, garments=garments, log=lambda line: log("cloth: " + line))
    out["hair"] = {"garments": len(report["garments"]), "rigid_bodies": report["rigid_bodies"],
                   "joints": report["joints"]}
    out["hair"]["scalp_anchored"], out["hair"]["swinging"] = anchor_scalp_hair(arm, garments)
    out["released_overlaps"] = roe.release_rest_overlaps()
    scene = bpy.context.scene
    out["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    out["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    return out


# -- 4. export ----------------------------------------------------------------------------------
def export(root, path, model_name, comment):
    root.mmd_root.name = root.mmd_root.name_e = model_name
    root.name = model_name
    text = bpy.data.texts.new(model_name + "_comment")
    text.from_string(comment)
    root.mmd_root.comment_text = root.mmd_root.comment_e_text = text.name
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    stack = [root]
    while stack:
        obj = stack.pop()
        try:
            obj.hide_set(False)
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass
        stack.extend(obj.children)
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True, log_level="ERROR")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("PMX not written: %s" % path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--xps", required=True)
    ap.add_argument("--dna", default="", help="face DNA from metahuman_dna.py extract (no expressions without it)")
    ap.add_argument("--out", required=True, help="the PMX goes to <out>/<name>/<name>.pmx")
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="")
    ap.add_argument("--no-physics", action="store_true")
    ap.add_argument("--no-morphs", action="store_true")
    args = ap.parse_args(argv)
    name = args.name or os.path.splitext(os.path.basename(args.xps))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".pmx")
    for module in ("mmd_tools", "XNALaraMesh-master", "Convert_to_MMD5"):
        addon_utils.enable(module, default_set=False)
    roe = load_worker()

    report = {"name": name, "xps": args.xps, "pmx": path}
    root, arm = import_and_convert(args.xps)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == arm]
    report["both_eyes_bone"] = roe.add_both_eyes_bone(arm)
    activate(arm)
    bpy.ops.object.create_bone_group()                     # 両目 into the add-on's display frames
    if args.dna and not args.no_morphs:
        face = metahuman_dna.DnaFace(open(args.dna, "rb").read())
        report["expressions"] = build_face_morphs(root, arm, face)
    if not args.no_physics:
        report["physics"] = add_physics(root, arm, meshes, roe)
    comment = ("Vindictus: Defying Fate (2024 pre-alpha) %s. XPS -> Convert to MMD 5 -> ripper_tpose "
               "scripts/vindictus/export_pmx.py; expressions evaluated from the face's MetaHuman DNA." % name)
    export(root, path, args.model_name or name, comment)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bones"] = len(arm.data.bones)
    report["bytes"] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    with open(os.path.join(out_dir, name + ".pmx.report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    print("VINDICTUS_PMX_REPORT=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
