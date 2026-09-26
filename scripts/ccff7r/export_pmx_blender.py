# -*- coding: utf-8 -*-
"""CCFF7R .blend -> MMD .pmx, inside Blender 3.6 (headless).

The FF7 Remake / Rebirth chain (scripts/final/export_ff7_pmx_blender.py -> the Stellar Blade /
Rise of Eros workers: mmd_tools writes the PMX, Convert_to_MMD5 builds the MMD skeleton and body
colliders, mmd_cloth_physics the hair / skirt chains, blender2xps bakes node colours into one
texture per material).  This file only adds what the Crisis Core rig needs:

  * slots from the HumanIK names: Hips / Spine / Spine1 / Neck / Head, LeftShoulder / LeftArm /
    LeftForeArm / LeftHand, LeftUpLeg / LeftLeg / LeftFoot / LeftToeBase, LeftHandThumb1..3 ...,
    eyes hi_eye_L / hi_eye_R;
  * town / village NPCs have no Neck (Head hangs on Spine1), no fingers and no toes: a skinless
    Neck is inserted between Spine1 and Head (MMD needs the joint; the skin stays on Spine1 /
    Head as in the game);
  * the face rig (everything under hi_face except the eyes: lids, brows, lips, chin, tongue)
    is merged into Head - no face morphs yet, and the add-on would hand that skin to the eyes;
  * Tifa's breast chain L_bustB -> L_bustA becomes one bone (A merged into B) carrying the
    Eve-style bust physics; the other models have no breast bones;
  * bone names the cloth classifier would not recognise are spelt out: *_skt* -> *_skirt*,
    ribon -> ribbon, mant -> mantle, Cloth -> Cloak (Minerva); Roll / Sub arm and leg helpers
    are limb helpers, never cloth;
  * the <id>_weapon object (lying at the feet in the bind pose) is left out unless --keep-weapon;
  * centimetres -> metres; the PSK import already faces -Y.

  blender -b X.blend --python export_pmx_blender.py -- --out <dir> [--name N] [--model-name M]
          [--comment C] [--keep-weapon]
Prints CCFF7R_PMX={json}.  Writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FF7_SCRIPT = os.path.join(REPO, "scripts", "final", "export_ff7_pmx_blender.py")
EYES = ("hi_eye_L", "hi_eye_R")
RENAMES = ((re.compile(r"skt", re.I), "skirt", "skirt"), (re.compile(r"ribon", re.I), "ribbon", "ribbon"),
           (re.compile(r"mant(?!le)", re.I), "mantle", None), (re.compile(r"cloth", re.I), "Cloak", None))
LIMB_HELPERS = r"|roll\d*$|sub$"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ff7 = load(FF7_SCRIPT, "ff7_pmx")        # unpack / repack / merge_bones / pick; loads the SB module
sb = ff7.sb
sb.BUST["bones"] = (("左胸", "L_bustB"), ("右胸", "R_bustB"))


def rename_cloth_bones(arm, meshes):
    """Spell out abbreviations so Convert_to_MMD5 / mmd_cloth_physics see skirts, ribbons, capes."""
    done = []
    for bone in list(arm.data.bones):
        old = new = bone.name
        for rx, word, unless in RENAMES:
            if rx.search(new) and not (unless and unless in new.lower()):
                new = rx.sub(word, new)
        if new == old or new in arm.data.bones:
            continue
        bone.name = new                       # renames the vertex groups of the skinned meshes too
        for m in meshes:
            vg = m.vertex_groups.get(old)
            if vg is not None and m.vertex_groups.get(new) is None:
                vg.name = new
        done.append("%s -> %s" % (old, new))
    return done


def add_neck(arm):
    """NPC rigs hang Head straight on Spine1.  Insert a skinless Neck from just above the
    shoulders to the head pivot so the MMD skeleton has its 首 joint."""
    bones = arm.data.bones
    if "Neck" in bones or "Head" not in bones:
        return None
    head = bones["Head"]
    shoulders = [bones[n].head_local.z for n in ("LeftShoulder", "RightShoulder") if n in bones]
    top = head.head_local.copy()
    parent = head.parent
    z0 = (sum(shoulders) / len(shoulders)) if shoulders else (parent.head_local.z if parent else top.z - 8.0)
    base = top.copy()
    base.z = z0 + (top.z - z0) * 0.25
    if parent is not None:                    # follow the spine's lean between Spine1 and the head
        t = (base.z - parent.head_local.z) / max(1e-6, top.z - parent.head_local.z)
        base.y = parent.head_local.y + (top.y - parent.head_local.y) * t
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    neck = eb.new("Neck")
    neck.head = base
    neck.tail = eb["Head"].head.copy()
    if (neck.tail - neck.head).length < 1e-3:
        neck.tail = neck.head + Vector((0.0, 0.0, 2.0))
    neck.parent = eb["Head"].parent
    eb["Head"].parent = neck
    eb["Head"].use_connect = False
    neck.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return "Neck %.1f -> %.1f" % (base.z, top.z)


def face_bones(arm):
    root = arm.data.bones.get("hi_face")
    out = []
    if root is None:
        return out
    stack = list(root.children)
    while stack:
        b = stack.pop()
        if b.name in EYES:
            continue
        out.append(b.name)
        stack.extend(b.children)
    out.append(root.name)
    return out


def resolve_slots(arm):
    bones = arm.data.bones
    pick = ff7.pick
    slots = {
        "all_parents_bone": pick(bones, "root", "Reference"),
        "center_bone": "",
        "lower_body_bone": pick(bones, "Hips"),
        "upper_body_bone": pick(bones, "Spine"),
        "upper_body2_bone": pick(bones, "Spine1"),
        "upper_body3_bone": pick(bones, "Spine2"),
        "neck_bone": pick(bones, "Neck"),
        "head_bone": pick(bones, "Head"),
    }
    for side, word, s in (("left", "Left", "L"), ("right", "Right", "R")):
        slots.update({
            "%s_eye_bone" % side: pick(bones, "hi_eye_" + s),
            "%s_chest_bone" % side: pick(bones, s + "_bustB"),
            "%s_shoulder_bone" % side: pick(bones, word + "Shoulder"),
            "%s_upper_arm_bone" % side: pick(bones, word + "Arm"),
            "%s_lower_arm_bone" % side: pick(bones, word + "ForeArm"),
            "%s_hand_bone" % side: pick(bones, word + "Hand"),
            "%s_thigh_bone" % side: pick(bones, word + "UpLeg"),
            "%s_calf_bone" % side: pick(bones, word + "Leg"),
            "%s_foot_bone" % side: pick(bones, word + "Foot"),
            "%s_toe_bone" % side: pick(bones, word + "ToeBase"),
        })
        for finger, game in (("thumb", "Thumb"), ("index", "Index"), ("middle", "Middle"), ("ring", "Ring"),
                             ("pinky", "Pinky")):
            segments = ("0", "1", "2") if finger == "thumb" else ("1", "2", "3")
            for seg, n in zip(segments, "123"):
                slots["%s_%s_%s" % (side, finger, seg)] = pick(bones, "%sHand%s%s" % (word, game, n))
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


def prepare(arm, meshes):
    """Renames, neck, face / bust merges, skinless helpers off, centimetres -> metres."""
    height_cm = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    stats = {"height_cm": round(height_cm, 2)}
    stats["renamed"] = rename_cloth_bones(arm, meshes)
    stats["dropped_far_bones"] = len(sb.drop_far_sockets(arm, meshes))
    stats["added_neck"] = add_neck(arm)
    stats["merged_face_bones"] = len(ff7.merge_bones(arm, meshes, face_bones(arm), "Head"))
    bust = []
    for s in ("L", "R"):
        if s + "_bustA" in arm.data.bones and s + "_bustB" in arm.data.bones:
            bust += ff7.merge_bones(arm, meshes, [s + "_bustA"], s + "_bustB")
    stats["merged_bust"] = bust
    slots, missing = resolve_slots(arm)
    weighted = sb.weighted_bones(meshes)
    keep = {v for v in slots.values() if v}
    off = [b.name for b in arm.data.bones if b.use_deform and b.name not in weighted and b.name not in keep]
    for name in off:
        arm.data.bones[name].use_deform = False        # only decides who may inherit weight
    stats["undeformed_skinless"] = len(off)
    s = 0.01 if height_cm > 20.0 else 1.0
    arm.scale = tuple(x * s for x in arm.scale)
    bpy.context.view_layer.update()
    return slots, missing, stats


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--keep-weapon", action="store_true")
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath, "weapons_left_out": []}
    for obj in list(scene.objects):
        if obj.type == "MESH" and (obj.hide_render or (obj.name.endswith("_weapon") and not args.keep_weapon)):
            if obj.name.endswith("_weapon"):
                report["weapons_left_out"].append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]

    if os.path.isdir(out_dir):                      # a generated folder: start clean
        shutil.rmtree(out_dir)
    unpack_dir = tempfile.mkdtemp(prefix="ccff7r_pmx_images_")
    report["unpacked_images"] = ff7.unpack_images_to(unpack_dir)
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    slots, missing_optional, stats = prepare(arm, meshes)
    report["missing_optional_slots"] = missing_optional
    report.update(stats)

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
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    try:                                             # Roll / Sub bones are limb helpers, never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        if LIMB_HELPERS not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + LIMB_HELPERS, re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(conv)
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

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or ("Converted from CRISIS CORE -FINAL FANTASY VII- REUNION by ripper_tpose "
                               "(scripts/ccff7r). Personal use only.")
    text = bpy.data.texts.new(name + "_comment")
    text.from_string(comment.replace(chr(92) + "n", "\n"))
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
    report["repacked_images"] = ff7.repack_images_from(unpack_dir)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    shutil.rmtree(unpack_dir, ignore_errors=True)
    print("CCFF7R_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
