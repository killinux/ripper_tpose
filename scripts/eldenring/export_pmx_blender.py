# -*- coding: utf-8 -*-
"""Elden Ring mod .blend (build_blend.py) -> MMD .pmx, inside Blender 3.6 (headless).

The repo's Biped chain (Stellar Blade's export_pmx_blender.py on the Rise of Eros worker: mmd_tools writes the PMX,
Convert_to_MMD5 builds the MMD skeleton, IK and body colliders, mmd_cloth_physics the hair / cloth chains,
blender2xps bakes node colours into one texture per material).  What this file adds for Elden Ring:
  * FromSoftware's bone names -> 3ds Max Biped names (rig.py; the skeleton is a Max Biped without the prefix);
  * eye bones (左目 / 右目) at each eyeball's sphere centre - the game turns no eye bones (the eyes ride Head);
  * the breasts hang on L_ / R_Pectoral (with Spine2): those become 左胸 / 右胸 with a dynamic sphere and a spring
    joint each (Stellar Blade's BUST set-up);
  * hair the game moves with its Havok cloth (the _c.hkx a PMX cannot carry) is skinned to the head and the chest
    only: chains are generated over its hanging part (scripts/aion2/hair_chains.py) so it swings (--hair-chains off);
  * --leave-out REGEX drops mesh objects (named after the FLVER materials) first, e.g. a hardsuit for a slim variant.
  blender -b <name>.blend --python export_pmx_blender.py -- --out <dir> [--name N] [--model-name M] [--comment C]
          [--leave-out REGEX] [--hair-chains auto|off]
Prints ER_PMX={json}.  Writes <out>/<name>.pmx + textures/ + <name>_converted.blend.
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
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import rig  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = load(os.path.join(REPO, "scripts", "stellarblade", "export_pmx_blender.py"), "sb_pmx")
hair_chains = load(os.path.join(REPO, "scripts", "aion2", "hair_chains.py"), "aion2_hair_chains")
sb.BUST["bones"] = rig.BUST
sb.BUST["min_weight"] = 0.2           # the breast skin is half Spine2, half Pectoral
sb.is_eye_material = lambda name: bool(rig.EYE_MATERIAL.search(name))


def fix_eye_pivots(arm, meshes):
    """Eye bone -> the least-squares sphere centre of the vertices it carries (from scripts/vindictusna): add_eye_bones
    puts the pivot at back-most point + radius, which lands on the cornea when the eyeball is a front cap."""
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


def long_hair_side(arm, mesh, head_name="Bip001 Head"):
    """'front' / 'back': where the hair hanging below the shoulders is (median azimuth, 0 = her back)."""
    hp = arm.matrix_world @ arm.data.bones[head_name].head_local
    names = {g.index: g.name for g in mesh.vertex_groups}
    az = []
    for v in mesh.data.vertices:
        if sum(g.weight for g in v.groups if not hair_chains.KEEP.search(names.get(g.group, ""))) <= 0.01:
            continue
        p = mesh.matrix_world @ v.co
        if p.z < hp.z - 0.20:
            az.append(np.degrees(np.arctan2(p.x - hp.x, p.y - hp.y)))
    if not az:
        return None
    a = np.radians(np.array(az))
    mean = np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean()))
    return "front" if abs(mean) > 90 else "back"


def add_hair_chains(arm, meshes, mode):
    """Chains for hair skinned to the body only (scripts/aion2/hair_chains.py).  That generator works in centimetres
    and spreads its strands around her BACK; it runs here with the armature scaled x100 and, when the long hair
    hangs in front (Reika: over the chest, short at the back), turned 180 degrees about Z, then both are undone."""
    if mode == "off":
        return []
    out = []
    hairy = [m for m in meshes if any(s.material and re.search(r"hair", s.material.name, re.I) for s in m.material_slots)]
    hairy = [m for m in hairy if hair_chains.needs_chains(arm, m)]
    for m in hairy:
        side = long_hair_side(arm, m)
        if side is None:
            out.append({"mesh": m.name, "skipped": "no hair hangs below the shoulders"})
            continue
        arm.scale = (100.0, 100.0, 100.0)
        arm.rotation_euler = (0.0, 0.0, np.pi if side == "front" else 0.0)
        bpy.context.view_layer.update()
        try:
            out.append(dict(hair_chains.rig(arm, m, "Bip001 Head", prefix="Hair_Front" if side == "front" else "Hair_Gen"),
                            mesh=m.name, side=side))
        finally:
            arm.scale = (1.0, 1.0, 1.0)
            arm.rotation_euler = (0.0, 0.0, 0.0)
            bpy.context.view_layer.update()
    return out


def prepare(arm, meshes, hair_mode):
    stats = {"height_m": round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)}
    stats["rig"] = rig.to_biped(arm, meshes)
    stats["dropped_far_bones"] = len(sb.drop_far_sockets(arm, meshes))
    stats["hair_chains"] = add_hair_chains(arm, meshes, hair_mode)
    stats["eye_bones"] = sb.add_eye_bones(arm, meshes)
    stats["eye_pivots"] = fix_eye_pivots(arm, meshes)
    stats["undeformed_sockets"] = sb.undeform_sockets(arm, meshes)
    return stats


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--leave-out", default="", help="regex of mesh objects (FLVER material names) to drop")
    ap.add_argument("--hair-chains", choices=("auto", "off"), default="auto")
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.abspath(args.out)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath}
    report["left_out"] = rig.leave_out(scene, args.leave_out)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]

    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    mask_alpha = mask_alpha_images(meshes)           # before the conversion gives every material the MMD shader
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    report.update(prepare(arm, meshes, args.hair_chains))

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
        if rig.LIMB_HELPER not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + rig.LIMB_HELPER, re.IGNORECASE)
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
    comment = args.comment or ("Converted from an ELDEN RING mod by ripper_tpose (scripts/eldenring). "
                               "Personal use only; credit the mod's author.")
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
    print("ER_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
