# -*- coding: utf-8 -*-
"""FF7 Remake / Rebirth character .blend -> MMD .pmx, all inside Blender 3.6 (headless).

The same chain as the Stellar Blade Eve PMX (scripts/stellarblade/export_pmx_blender.py),
which itself reuses the ROE PMX worker: mmd_tools writes the PMX, Convert_to_MMD5 builds the
MMD skeleton and body colliders, mmd_cloth_physics the hair / skirt chains, blender2xps bakes
node colours into one texture per material.  Everything is imported from those two scripts;
this file only adds what the Square Enix rig needs:

  * slots from the SE bone names: C_Hip_a, C_Spine_a..d, C_Neck_a, C_Head_a, L_Shoulder_a,
    L_UpperArm_a, L_Forearm_a, L_Hand_a, L_UpperLeg_a, L_Foreleg_a, L_Foot_a, L_Toe_a,
    L_Thumb_a..c / L_Index_a..c ...; eyes L_Eye / R_Eye (so the gaze works); chest
    L/R_Breast_a_Phy with the Eve bust physics;
  * four spine bones for three MMD slots: C_Spine_c is merged into C_Spine_b, giving
    upper body / upper body 2 / upper body 3 = C_Spine_a / b / d;
  * the face rig (every bone under C_FaceBase_a / C_FaceBase_b except the eyes) is merged
    into the head: the add-on classifier would hand that skin to the nearest bone head - the
    eye bones - so the lids would follow the gaze.  With --face-data the game's expressions
    are baked into shape keys first (the FF7 Face Morphs add-on, scripts/blender_addons/
    ff7_face_morphs), so the PMX gets real vertex morphs (まばたき, あいうえお, 眉 ... + the
    game's whole-face poses);
  * the PSK / glTF import faces +X in centimetres: turned to face -Y, scaled to metres.

  blender -b X.blend --python export_ff7_pmx_blender.py -- --out <dir> [--name N]
          [--model-name M] [--comment C] [--skirt-to-legs] [--face-data <face json>
          [--face-categories EYE,EYEBROW,MOUTH,OTHER] [--face-strength EYEBROW=1.5 ...]]
Prints FF7_PMX_REPORT={json}.  Writes <out>/<name>/<name>.pmx + textures/ + _converted.blend.
"""
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SB_SCRIPT = os.path.join(REPO, "scripts", "stellarblade", "export_pmx_blender.py")
FACE_ROOTS = ("C_FaceBase_a", "C_FaceBase_b")
KEEP_UNDER_FACE = re.compile("(^[LR]_Eye$)|hair|_phy$", re.IGNORECASE)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = load(SB_SCRIPT, "sb_pmx")
sys.path.insert(0, os.path.join(REPO, "scripts", "blender_addons"))
from ff7_face_morphs import core as face_morphs  # noqa: E402  (the FF7 Face Morphs add-on: same code by hand)
sb.BUST["bones"] = (("左胸", "L_Breast_a_Phy"), ("右胸", "R_Breast_a_Phy"))
sb.EYE_MAT_RE = re.compile("(^|_)eye($|_)|ojos|eyeball", re.IGNORECASE)


def unpack_images_to(folder):
    """Packed images -> files in <folder>, image.filepath pointed there (the source blend is not saved).
    mmd_tools' PMX export copies texture FILES; blends archived to E:/game_export keep their images
    packed, and exporting straight from there gave a PMX folder holding only the freshly baked maps
    (magenta face in MMD)."""
    used, done = set(), 0
    for image in bpy.data.images:
        if image.source != "FILE" or not image.packed_file:
            continue
        stem, ext = os.path.splitext(os.path.basename(bpy.path.abspath(image.filepath)) or image.name)
        ext = ext or ".png"
        name, n = stem + ext, 1
        while name.lower() in used:
            n += 1
            name = "%s_%d%s" % (stem, n, ext)
        used.add(name.lower())
        path = os.path.join(folder, name)
        with open(path, "wb") as fh:
            fh.write(bytes(image.packed_file.data))
        image.filepath = path
        image.unpack(method="REMOVE")
        done += 1
    return done


def repack_images_from(folder):
    """Pack every image still read from <folder> so the saved _converted.blend stays standalone."""
    root, done = os.path.normcase(os.path.abspath(folder)), 0
    for image in bpy.data.images:
        if image.source == "FILE" and not image.packed_file and image.filepath:
            path = os.path.normcase(os.path.abspath(bpy.path.abspath(image.filepath)))
            if path.startswith(root) and os.path.isfile(path):
                image.pack()
                done += 1
    return done


def pick(bones, *names):
    return next((n for n in names if n and n in bones), "")


def resolve_ff7_slots(arm):
    """Convert_to_MMD5 slots (same keys as the ROE resolver) from the SE naming."""
    bones = arm.data.bones
    slots = {
        "all_parents_bone": pick(bones, "Trans", "Root", "root"),
        "center_bone": "",
        "lower_body_bone": pick(bones, "C_Hip_a"),
        "upper_body_bone": pick(bones, "C_Spine_a"),
        "upper_body2_bone": pick(bones, "C_Spine_b"),
        "upper_body3_bone": pick(bones, "C_Spine_d", "C_Spine_c"),
        "neck_bone": pick(bones, "C_Neck_a"),
        "head_bone": pick(bones, "C_Head_a"),
    }
    for side, s in (("left", "L"), ("right", "R")):
        slots.update({
            "%s_eye_bone" % side: pick(bones, s + "_Eye", s + "_Eyeball"),
            "%s_chest_bone" % side: pick(bones, s + "_Breast_a_Phy"),
            "%s_shoulder_bone" % side: pick(bones, s + "_Shoulder_a"),
            "%s_upper_arm_bone" % side: pick(bones, s + "_UpperArm_a"),
            "%s_lower_arm_bone" % side: pick(bones, s + "_Forearm_a", s + "_ForeArm_a"),
            "%s_hand_bone" % side: pick(bones, s + "_Hand_a"),
            "%s_thigh_bone" % side: pick(bones, s + "_UpperLeg_a"),
            "%s_calf_bone" % side: pick(bones, s + "_Foreleg_a"),
            "%s_foot_bone" % side: pick(bones, s + "_Foot_a"),
            "%s_toe_bone" % side: pick(bones, s + "_Toe_a"),
        })
        for finger in ("thumb", "index", "middle", "ring", "pinky"):
            segments = ("0", "1", "2") if finger == "thumb" else ("1", "2", "3")
            for seg, letter in zip(segments, "abc"):
                slots["%s_%s_%s" % (side, finger, seg)] = pick(
                    bones, "%s_%s_%s" % (s, finger.capitalize(), letter),
                    "%s_%s_%s" % (s, "Little" if finger == "pinky" else finger.capitalize(), letter))
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


def merge_bones(arm, meshes, names, into):
    """Give each bone's skin to `into`, hang its children on its parent, delete it."""
    names = [n for n in names if n in arm.data.bones and n != into]
    if not names:
        return []
    for m in meshes:
        dst = m.vertex_groups.get(into) or m.vertex_groups.new(name=into)
        for name in names:
            src = m.vertex_groups.get(name)
            if src is None:
                continue
            for v in m.data.vertices:
                for g in v.groups:
                    if g.group == src.index and g.weight > 0.0:
                        dst.add([v.index], g.weight, "ADD")
            m.vertex_groups.remove(src)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    doomed = set(names)
    for name in names:
        bone = eb.get(name)
        parent = bone.parent
        while parent is not None and parent.name in doomed:
            parent = parent.parent
        for child in list(bone.children):
            if child.name not in doomed:
                child.parent = parent
    for name in names:
        eb.remove(eb[name])
    bpy.ops.object.mode_set(mode="OBJECT")
    return names


def face_rig(arm):
    out = []
    for root in FACE_ROOTS:
        bone = arm.data.bones.get(root)
        if bone is None:
            continue
        stack = [bone]
        while stack:
            b = stack.pop()
            if KEEP_UNDER_FACE.search(b.name):
                continue                           # eyes stay; hair / physics chains keep their subtree
            out.append(b.name)
            stack.extend(b.children)
    return out


def relocate_bust_pivots(arm, meshes, slots, depth):
    """SE hangs BOTH breast physics bones (L/R_Breast_Spo -> L/R_Breast_a_Phy) on one point
    12 cm behind the spine - the game's own jiggle solver copes with that lever, MMD rigid
    bodies do not (a 28 cm pendulum).  Each side's pivot moves to `depth` behind its own
    skin centroid, horizontally towards the spine.  Rest shape unchanged (rest-only edit)."""
    spine = arm.data.bones.get(slots["upper_body3_bone"]) or arm.data.bones.get(slots["upper_body_bone"])
    inv = arm.matrix_world.inverted()
    plans = []
    for side in ("left", "right"):
        bone = arm.data.bones.get(slots["%s_chest_bone" % side])
        if bone is None:
            continue
        pts, ws = [], []
        for m in meshes:
            vg = m.vertex_groups.get(bone.name)
            if vg is None:
                continue
            for v in m.data.vertices:
                for g in v.groups:
                    if g.group == vg.index and g.weight >= 0.3:
                        pts.append(m.matrix_world @ v.co)
                        ws.append(g.weight)
        if not pts or spine is None:
            continue
        centre = sum((p * w for p, w in zip(pts, ws)), Vector()) / sum(ws)
        back = (arm.matrix_world @ spine.head_local) - centre
        back.z = 0.0
        if back.length < 1e-6:
            continue
        pivot = centre + back.normalized() * depth
        plans.append((bone.name, inv @ pivot, inv @ centre))
    if not plans:
        return []
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    out = []
    for name, pivot, centre in plans:
        bone = eb[name]
        old = bone.head.copy()
        chain = [bone]
        parent = bone.parent                     # the skinless *_Breast_Spo sitting on the same point
        if parent is not None and (parent.head - old).length < 1e-3:
            chain.append(parent)
        for b in chain:
            b.head = pivot
            b.tail = pivot + (centre - pivot) * 0.5
        out.append("%s: pivot moved %.1f" % (name, (pivot - old).length))
    bpy.ops.object.mode_set(mode="OBJECT")
    return out


def _seg_dist(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def skirt_to_legs(arm, meshes, slots):
    """--skirt-to-legs: skin a mod weighted to the base outfit's skirt chains goes to the
    nearest thigh.  TheWolfster's GANTZ suits (Remake 1707, Rebirth 817) hang the lower
    thigh guards on Tifa's skirt bones (C_SkirtA_b / L_SkirtB_b / R_SkirtA_b) so the game's
    skirt solver sways them; in MMD those chains hang off the lower body without physics
    and the guards stayed behind whenever a leg lifted.  Off by default: on a real skirt
    the same weights must stay on the skirt (its front hem sits between the legs too)."""
    legs = []
    for side in ("left", "right"):
        thigh = arm.data.bones.get(slots["%s_thigh_bone" % side])
        calf = arm.data.bones.get(slots["%s_calf_bone" % side])
        if thigh is not None and calf is not None:
            legs.append((thigh.name, arm.matrix_world @ thigh.head_local, arm.matrix_world @ calf.head_local))
    moved = {}
    if len(legs) != 2:
        return moved
    for m in meshes:
        skirt = [vg for vg in m.vertex_groups if re.search("skirt", vg.name, re.IGNORECASE)]
        if not skirt:
            continue
        index = {vg.index for vg in skirt}
        dst = {name: m.vertex_groups.get(name) or m.vertex_groups.new(name=name) for name, _a, _b in legs}
        for v in m.data.vertices:
            w = sum(g.weight for g in v.groups if g.group in index)
            if w <= 0.0:
                continue
            p = m.matrix_world @ v.co
            name = min(legs, key=lambda leg: _seg_dist(p, leg[1], leg[2]))[0]
            dst[name].add([v.index], w, "ADD")
            moved[name] = moved.get(name, 0) + 1
        for vg in skirt:
            m.vertex_groups.remove(vg)
    return moved


def prepare_ff7(arm, meshes, slots, skirt_legs=False):
    """Merges, skinless helpers off, face -Y, centimetres -> metres.  Returns stats."""
    height_cm = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    dropped = sb.drop_far_sockets(arm, meshes)
    spine = merge_bones(arm, meshes, ["C_Spine_c"], "C_Spine_b") if slots["upper_body3_bone"] == "C_Spine_d" else []
    face = merge_bones(arm, meshes, face_rig(arm), slots["head_bone"])
    skirt = skirt_to_legs(arm, meshes, slots) if skirt_legs else {}
    bust = relocate_bust_pivots(arm, meshes, slots, 8.0 if height_cm > 20.0 else 0.08)
    weighted = sb.weighted_bones(meshes)
    keep = {v for v in slots.values() if v}
    off = [b.name for b in arm.data.bones if b.use_deform and b.name not in weighted and b.name not in keep]
    for name in off:
        arm.data.bones[name].use_deform = False    # only decides who may inherit weight
    bones = arm.data.bones
    d = Vector((0.0, 0.0, 0.0))
    for side in ("left", "right"):
        foot, toe = bones.get(slots["%s_foot_bone" % side]), bones.get(slots["%s_toe_bone" % side])
        if foot is None or toe is None:
            raise RuntimeError("no %s foot / toe bone to find the front" % side)
        d += (arm.matrix_world.to_3x3() @ (toe.head_local - foot.head_local)).normalized()
    turn = math.atan2(-1.0, 0.0) - math.atan2(d.y, d.x)
    turn = math.atan2(math.sin(turn), math.cos(turn))
    arm.matrix_world = Matrix.Rotation(turn, 4, "Z") @ arm.matrix_world
    s = 0.01 if height_cm > 20.0 else 1.0          # PSK / patched glTF import: centimetres
    arm.scale = tuple(x * s for x in arm.scale)
    bpy.context.view_layer.update()
    return {"height_cm": round(height_cm, 2), "turned_deg": round(math.degrees(turn), 1),
            "dropped_far_bones": len(dropped), "merged_spine": spine, "merged_face_bones": len(face),
            "bust_pivots": bust, "skirt_to_legs": skirt,
            "undeformed_skinless": len(off)}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--skirt-to-legs", action="store_true",
                    help="skin on the base outfit's skirt bones follows the nearest thigh (tight suits)")
    ap.add_argument("--face-data", default="",
                    help="face-data JSON (ff7_face_data.py): the game's expressions as MMD vertex morphs")
    ap.add_argument("--face-categories", default="EYE,EYEBROW,MOUTH,OTHER",
                    help="expression panels to build with --face-data")
    ap.add_argument("--face-strength", action="append", default=[], metavar="PANEL=FACTOR",
                    help="scale one panel's expressions, e.g. EYEBROW=1.5 (repeatable)")
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    for obj in list(scene.objects):
        if obj.type == "MESH" and obj.hide_render:
            bpy.data.objects.remove(obj, do_unlink=True)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]

    report = {"name": name, "pmx": path, "source": bpy.data.filepath}
    if os.path.isdir(out_dir):                      # a generated folder: start clean
        shutil.rmtree(out_dir)
    unpack_dir = tempfile.mkdtemp(prefix="ff7_pmx_images_")
    report["unpacked_images"] = unpack_images_to(unpack_dir)
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    slots, missing_optional = resolve_ff7_slots(arm)
    report["missing_optional_slots"] = missing_optional
    face_made, face_stash = [], {}
    if args.face_data:                              # while the face bones still exist
        strengths = {}
        for item in args.face_strength:
            panel, _sep, value = item.partition("=")
            strengths[panel.strip().upper()] = float(value)
        panels = tuple(c.strip().upper() for c in args.face_categories.split(",") if c.strip())
        # keys left in the .blend by an earlier build (the add-on panel) would be exported too: the PMX
        # gets exactly the panels / strengths asked for here
        report["face_morphs_cleared"] = face_morphs.clear(meshes)
        try:
            face_made = face_morphs.build_shape_keys(arm, meshes, face_morphs.load_face_data(args.face_data),
                                                     categories=panels, strengths=strengths)
        except Exception as exc:                    # no FF7 face rig etc.: a PMX without expressions, reported
            report["face_morph_error"] = str(exc)
        report["face_morph_vertices"] = {m[0]: m[3] for m in face_made}   # "face_morphs" = the ROE add-on's
    report.update(prepare_ff7(arm, meshes, slots, args.skirt_to_legs))

    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    os.makedirs(out_dir, exist_ok=True)
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    if missing_required:
        raise RuntimeError("rig lacks joints the MMD conversion needs: %s" % ", ".join(missing_required))
    roe.bake_rig_transforms(arm, meshes)
    report["premerged_helpers"] = sb.premerge_spine_helpers(arm, meshes, slots)
    before = roe.edge_lengths(meshes)
    report["height_m"] = round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)
    helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
    report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
    if face_made:                                   # the pose bakes below skip meshes with shape keys
        face_stash = face_morphs.stash(meshes)
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    try:                                           # SE support bones (*_Spo) are muscle helpers, never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        if "_spo" not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + "|_spo$", re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, stats = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(stats)
    if face_stash:
        report["face_morphs_restored"] = face_morphs.restore(meshes)
    report["stray_recipients"] = sorted((sb.weighted_bones(meshes) - weighted_before) & names_before)
    slot_names = {v for v in slots.values() if v}
    report["retired_helpers"] = sorted(weighted_before - sb.weighted_bones(meshes) - slot_names)
    report["anchored_hub_roots"] = sb.anchor_hub_roots(arm)
    report["released_rest_overlaps"] = sb.release_rest_overlaps()
    report["bust_physics"] = sb.add_breast_physics(root, arm, meshes)
    report["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    report["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = sb.fix_pmx_materials(meshes, baked, os.path.join(out_dir, "textures"))
    if face_made:
        report["vertex_morphs"] = face_morphs.register_morphs(root, meshes)

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or "Converted from FINAL FANTASY VII by ripper_tpose (scripts/final)."
    text = bpy.data.texts.new(name + "_comment")
    text.from_string(comment.replace(chr(92) + "n", "\n"))   # a literal backslash-n on the command line
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
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bytes"] = os.path.getsize(path)
    report["repacked_images"] = repack_images_from(unpack_dir)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    shutil.rmtree(unpack_dir, ignore_errors=True)
    print("FF7_PMX_REPORT=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
