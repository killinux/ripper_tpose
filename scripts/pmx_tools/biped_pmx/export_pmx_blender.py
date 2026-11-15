# -*- coding: utf-8 -*-
"""Any game's character .blend -> MMD .pmx through the repo's Biped chain, inside Blender 3.6 (headless).

The chain is the one Elden Ring / Stellar Blade / Rise of Eros use (Stellar Blade's export_pmx_blender.py on the Rise
of Eros worker: Convert_to_MMD5 builds the MMD skeleton, IK and body colliders, mmd_cloth_physics the hair / cloth
chains, blender2xps bakes node colours into one texture per material, mmd_tools writes the PMX at 12.5).  It reads
3ds Max Biped bone names; a rig map (rigs/<name>.py) turns the game's skeleton into one first:

    to_biped(arm, meshes) -> report      rename (vertex groups follow) and fix the tree (rigtools.py)
    BUST = (("左胸", <left bone>), ("右胸", <right bone>))   bones that get a jiggle sphere each
    LIMB_HELPER = r"|..."                 extra regex alternatives of bones that ride a limb (never cloth)
    EYE_MATERIAL = regex or None          materials that are eyeballs (eye bones 左目 / 右目); None = no eye bones
    HAIR_MATERIAL = regex                 hair materials (chains are generated for hair with no bones of its own)
    COMMENT = "..."                       default PMX comment

The scene must be in metres, Z up, the character facing -Y (the build scripts of scripts/marvelheroes etc. do that).

  blender -b <name>.blend --python export_pmx_blender.py -- --rig <mho|...> --out <dir> [--name N]
          [--model-name M] [--comment C] [--leave-out REGEX] [--hair-chains auto|off]
Prints BIPED_PMX={json}.  Writes <out>/<name>.pmx + textures/ + <name>_converted.blend.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rig(name):
    path = os.path.join(HERE, "rigs", name + ".py")
    if not os.path.isfile(path):
        raise SystemExit("unknown rig %r (no %s)" % (name, path))
    return load(path, "rig_" + name)


sb = load(os.path.join(REPO, "scripts", "stellarblade", "export_pmx_blender.py"), "sb_pmx")
limbs = load(os.path.join(REPO, "scripts", "vindictus", "limbs.py"), "vindictus_limbs")


def biped_finger_chains(arm):
    """Per finger, from the bone the finger is laid along out: the thumb along Finger0, the others along the
    wrist -> knuckle line (Hand), in Biped names."""
    chains = []
    for S in ("L", "R"):
        chains.append(tuple("Bip001 %s Finger0%s" % (S, j) for j in ("", "1", "2")))
        for d in "1234":
            chains.append(("Bip001 %s Hand" % S,) + tuple("Bip001 %s Finger%s%s" % (S, d, j) for j in ("", "1", "2")))
    names = arm.data.bones
    return [tuple(n.replace("Finger0", "Finger0") for n in c) for c in chains if all(n in names for n in c)]


def finger_curl_deg(arm, chains):
    """Mean bend (degrees) of the finger joints at rest."""
    import math
    b = arm.data.bones
    angles = []
    for c in chains:
        for i in range(1, len(c) - 1):
            a = (b[c[i]].head_local - b[c[i - 1]].head_local).normalized()
            o = (b[c[i + 1]].head_local - b[c[i]].head_local).normalized()
            angles.append(math.degrees(a.angle(o)))
    return sum(angles) / len(angles) if angles else 0.0
hair_chains = load(os.path.join(REPO, "scripts", "aion2", "hair_chains.py"), "aion2_hair_chains")


def leave_out(scene, pattern):
    """Delete mesh objects whose name matches pattern, and hidden ones.  Returns names."""
    rx = re.compile(pattern) if pattern else None
    gone = []
    for o in list(scene.objects):
        if o.type != "MESH":
            continue
        if o.hide_render or o.hide_get() or (rx and rx.search(o.name)):
            gone.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return gone


def fix_eye_pivots(arm, meshes):
    """Eye bone -> the least-squares sphere centre of the vertices it carries (add_eye_bones puts the pivot at the
    back-most point + radius, which lands on the cornea when the eyeball is a front cap)."""
    out = []
    for side in ("L", "R"):
        name = "Bip001 %s Eye" % side
        if name not in arm.data.bones:
            continue
        pts = []
        for m in meshes:
            vg = m.vertex_groups.get(name)
            if vg is None:
                continue
            for v in m.data.vertices:
                if any(g.group == vg.index and g.weight > 0.5 for g in v.groups):
                    pts.append(tuple(m.matrix_world @ v.co))
        if len(pts) < 20:
            continue
        P = np.array(pts)
        c = np.linalg.lstsq(np.c_[2 * P, np.ones(len(P))], (P ** 2).sum(1), rcond=None)[0]
        ctr, r = Vector(c[:3]), float(np.sqrt(c[3] + (c[:3] ** 2).sum()))
        if not 0.005 < r < 0.03:
            out.append("%s: sphere fit r %.1f mm - kept add_eye_bones' pivot" % (name, r * 1000))
            continue
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm.data.edit_bones[name]
        inv = arm.matrix_world.inverted()
        d = (eb.tail - eb.head).normalized()
        old = arm.matrix_world @ eb.head
        eb.head = inv @ ctr
        eb.tail = eb.head + d * max(r * 1.5, 0.01)
        bpy.ops.object.mode_set(mode="OBJECT")
        out.append("%s: pivot moved %.1f mm to the sphere centre (r %.1f mm)" % (name, (old - ctr).length * 1000, r * 1000))
    return out


def mask_alpha_images(meshes):
    """file names of images only OPAQUE materials use (a mask in alpha would make MMD draw them see-through)"""
    see, opaque = set(), set()
    for o in meshes:
        for s in o.material_slots:
            m = s.material
            if m is None or not m.use_nodes:
                continue
            names = {os.path.basename(bpy.path.abspath(n.image.filepath)).lower()
                     for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and n.image.filepath}
            (opaque if m.blend_method == "OPAQUE" else see).update(names)
    return opaque - see


def fill_mask_alpha(tex_dir, names):
    done = []
    for f in sorted(os.listdir(tex_dir)) if os.path.isdir(tex_dir) else []:
        if f.lower() not in names:
            continue
        im = bpy.data.images.load(os.path.join(tex_dir, f))
        if im.channels == 4:
            px = np.empty(len(im.pixels), dtype=np.float32)
            im.pixels.foreach_get(px)
            if px[3::4].min() < 1.0:
                px[3::4] = 1.0
                im.pixels.foreach_set(px)
                im.save()
                done.append(f)
        bpy.data.images.remove(im)
    return done


def add_hair_chains(arm, meshes, rig, mode):
    """Chains for hair skinned to the head only (scripts/aion2/hair_chains.py, which works in centimetres)."""
    if mode == "off" or not getattr(rig, "HAIR_MATERIAL", None):
        return []
    rx = re.compile(rig.HAIR_MATERIAL, re.IGNORECASE)
    out = []
    for m in meshes:
        if not any(s.material and rx.search(s.material.name) for s in m.material_slots):
            continue
        if not hair_chains.needs_chains(arm, m):
            continue
        arm.scale = (100.0, 100.0, 100.0)
        bpy.context.view_layer.update()
        try:
            out.append(dict(hair_chains.rig(arm, m, "Bip001 Head", prefix="Hair_Gen"), mesh=m.name))
        finally:
            arm.scale = (1.0, 1.0, 1.0)
            bpy.context.view_layer.update()
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--rig", required=True, help="rig map in rigs/ (mho, ...)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--leave-out", default="", help="regex of mesh objects to drop")
    ap.add_argument("--hair-chains", choices=("auto", "off"), default="auto")
    ap.add_argument("--straighten-fingers", choices=("auto", "on", "off"), default="auto",
                    help="lay curled fingers straight before the conversion (auto: when the mean joint bend > 15 deg)")
    args = ap.parse_args(argv)
    rig = load_rig(args.rig)
    sb.BUST["bones"] = rig.BUST
    sb.BUST["min_weight"] = 0.2
    eye_rx = re.compile(rig.EYE_MATERIAL, re.IGNORECASE) if getattr(rig, "EYE_MATERIAL", None) else None
    sb.is_eye_material = (lambda name: bool(eye_rx.search(name))) if eye_rx else (lambda name: False)

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.abspath(args.out)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath, "rig": args.rig}
    report["left_out"] = leave_out(scene, args.leave_out)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]

    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    mask_alpha = mask_alpha_images(meshes)           # before the conversion gives every material the MMD shader
    # faces in other UV tiles (UDIM-style 1..5 on the HS2 Venom, the mirrored half of Marvel Heroes' meshes) bake empty
    # and the material would be hidden as a "transparent shell": move them into 0..1 first (textures repeat)
    report["uv_tiles_wrapped"] = sb.wrap_uv_tiles(meshes)
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    report["height_m"] = round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)
    report["to_biped"] = rig.to_biped(arm, meshes)
    report["dropped_far_bones"] = len(sb.drop_far_sockets(arm, meshes))
    report["hair_chains"] = add_hair_chains(arm, meshes, rig, args.hair_chains)
    # MMD motions take straight fingers for rest; a rig bound with curled fingers (claws) bends them the wrong way
    # (the HS2 Venom's fingers flipped up into sticks).  Straightened joint by joint, skin turning by its weight share
    # (scripts/vindictus/limbs.py, the same as the Vindictus UE body).
    chains = biped_finger_chains(arm)
    curl = finger_curl_deg(arm, chains)
    report["finger_curl_deg"] = round(curl, 1)
    if args.straighten_fingers == "on" or (args.straighten_fingers == "auto" and curl > 15.0):
        report["straightened_fingers"] = limbs.straighten_fingers(arm, meshes, chains=chains)
    report["eye_bones"] = sb.add_eye_bones(arm, meshes) if eye_rx else "no eye material in this rig map"
    report["eye_pivots"] = fix_eye_pivots(arm, meshes)
    report["undeformed_sockets"] = sb.undeform_sockets(arm, meshes)

    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    slots, missing_optional = roe.resolve_roe_slots(arm)
    for (mmd_name, source_name), side in zip(sb.BUST["bones"], ("left", "right")):
        if source_name in arm.data.bones:
            slots["%s_chest_bone" % side] = source_name          # -> 左胸 / 右胸
            missing_optional = [m for m in missing_optional if m != "%s_chest_bone" % side]
    report["slots"] = {k: v for k, v in slots.items() if v}
    report["missing_optional_slots"] = missing_optional
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    if missing_required:
        raise RuntimeError("rig lacks joints the MMD conversion needs: %s" % ", ".join(missing_required))
    roe.bake_rig_transforms(arm, meshes)
    report["premerged_helpers"] = sb.premerge_spine_helpers(arm, meshes, slots)
    before = roe.edge_lengths(meshes)
    helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
    report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    try:                                             # twist helpers ride their limb, never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        extra = getattr(rig, "LIMB_HELPER", "")
        if extra and extra not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + extra, re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(conv)
    report["stray_recipients"] = sorted((sb.weighted_bones(meshes) - weighted_before) & names_before)
    slot_names = {v for v in slots.values() if v}
    report["retired_helpers"] = sorted(weighted_before - sb.weighted_bones(meshes) - slot_names)
    report["anchored_hub_roots"] = sb.anchor_hub_roots(arm)
    report["anchored_skin_helpers"] = sb.anchor_skin_helpers(arm, meshes)
    report["released_rest_overlaps"] = sb.release_rest_overlaps()
    report["bust_physics"] = sb.add_breast_physics(root, arm, meshes)
    report["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    report["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = sb.fix_pmx_materials(meshes, baked, os.path.join(out_dir, "textures"))

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or getattr(rig, "COMMENT", "Converted by ripper_tpose. Personal use only; credit the mod's author.")
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
    report["opaque_textures"] = fill_mask_alpha(os.path.join(out_dir, "textures"), mask_alpha)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bytes"] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    print("BIPED_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
