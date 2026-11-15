# -*- coding: utf-8 -*-
"""The First Descendant .blend -> MMD .pmx, inside Blender 3.6 (headless).

The Stellar Blade chain (scripts/stellarblade/export_pmx_blender.py -> the Rise of Eros worker:
Convert_to_MMD5 builds the MMD skeleton and body colliders, mmd_cloth_physics the hair / skirt
chains, the ARKit shapes are mixed into the standard MMD expressions, blender2xps bakes node
colours into one texture per material, mmd_tools writes the PMX at 12.5).  TFD's descendants are
3ds Max Biped rigs spelt with hyphens like Eve's, so this file only adds what the TFD rig needs:

  * eyes: the eyeballs ride Bn_FEye_L / Bn_FEye_R (or their child Bn_FEye_L1 / _R1 - whichever
    carries the eyeball skin) -> the eye slots, 左目 / 右目 + 両目;  a rig without them gets Eve's
    eye bones from the eye material (``*_Eyes_MI``);
  * breasts: Bn_Shape_Chest_L / _R -> the chest slots (左胸 / 右胸) and Eve's sphere physics;
  * the whole descendant is ONE mesh carrying the 52 ARKit shapes, and Convert_to_MMD5's A-pose
    bake leaves out meshes with shape keys (the arms would stay where they are while the skeleton
    goes down): ROE's keep_shape_keys_in_rest_bakes (scripts/riseoferos/export_suit_pmx_blender.py)
    bakes it with its keys;
  * the ARKit set has no MetaHuman ``TeethLowerDown``: the teeth are part of the mesh and jawOpen
    moves them, so the recipes drop that key instead of skipping あ / い / う / え / お;
  * bone helpers that are not cloth: Bn_Shape_* (the game's pose-driven correctives), Bn_Twist_*,
    Bn_Pos_*, the Pt_* armour pointers, sockets / weapon and accessory hang points;
  * a mesh parented to a bone (helmets hang on Bn_Socket_Head) becomes skinned to that bone, and
    meshes that are not the character (the preview scene's cube) are left out;
  * centimetres -> metres; the rig is turned to face -Y by its feet if it does not already.

  blender -b X.blend --python export_pmx_blender.py -- --out <dir> [--name N] [--model-name M]
          [--comment C]
Prints TFD_PMX={json}.  Writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend.
"""
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SB_SCRIPT = os.path.join(REPO, "scripts", "stellarblade", "export_pmx_blender.py")
SUIT_SCRIPT = os.path.join(REPO, "scripts", "riseoferos", "export_suit_pmx_blender.py")
EYE_BONES = (("left", "Bn_FEye_L"), ("right", "Bn_FEye_R"))
CHEST_BONES = (("left", "Bn_Shape_Chest_L"), ("right", "Bn_Shape_Chest_R"))
# never cloth: correctives, twist / position helpers, armour pointers, attach points
NOT_CLOTH = r"|^Bn_Shape_|^Bn_Twist_|^Bn_Pos_|^Pt_|^Bn_Socket_|^Bn_Weapon_|^Bn_Acc_Hang"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = load(SB_SCRIPT, "sb_pmx")
sb.BUST["bones"] = (("左胸", "Bn_Shape_Chest_L"), ("右胸", "Bn_Shape_Chest_R"))
sb.EYE_MAT_RE = re.compile(sb.EYE_MAT_RE.pattern + r"|(^|_)Eyes(_MI)?$", re.IGNORECASE)
sb.RECIPES = [(n, e, c, {k: v for k, v in mix.items() if k != "TeethLowerDown"}) for n, e, c, mix in sb.RECIPES]


def character_meshes(arm):
    """Meshes deformed by (or hanging on) the rig; anything else in the file is scenery."""
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        rigged = any(m.type == "ARMATURE" and m.object == arm for m in obj.modifiers)
        if rigged or (obj.parent == arm):
            out.append(obj)
    return out


def skin_bone_parented(arm, meshes):
    """A rigid piece parented to a bone (a helmet on Bn_Socket_Head) -> skinned 100 % to that bone, so the
    conversion carries it like any other part.  Returns 'mesh -> bone' lines."""
    done = []
    for obj in meshes:
        if obj.parent != arm or obj.parent_type != "BONE" or not obj.parent_bone:
            continue
        bone = obj.parent_bone
        world = obj.matrix_world.copy()
        obj.parent_type = "OBJECT"
        obj.parent_bone = ""
        obj.matrix_world = world
        group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
        group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        if not any(m.type == "ARMATURE" and m.object == arm for m in obj.modifiers):
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = arm
        arm.data.bones[bone].use_deform = True
        done.append("%s -> %s (%d verts)" % (obj.name, bone, len(obj.data.vertices)))
    return done


def eye_material_vertices(mesh):
    slots = [i for i, sl in enumerate(mesh.material_slots) if sl.material and sb.is_eye_material(sl.material.name)]
    verts = set()
    for poly in mesh.data.polygons:
        if poly.material_index in slots:
            verts.update(poly.vertices)
    return verts


def pick_eye_bones(arm, meshes):
    """The Bn_FEye_* bone of each side that carries most of the eyeball skin -> {side: bone}."""
    totals = {}
    for mesh in meshes:
        verts = eye_material_vertices(mesh)
        if not verts:
            continue
        names = {vg.index: vg.name for vg in mesh.vertex_groups}
        for i in verts:
            for g in mesh.data.vertices[i].groups:
                name = names.get(g.group, "")
                if name.startswith("Bn_FEye_") and g.weight > 0.0:
                    totals[name] = totals.get(name, 0.0) + g.weight
    picked = {}
    for side, stem in EYE_BONES:
        best = max((n for n in totals if n.startswith(stem)), key=lambda n: totals[n], default="")
        if best:
            picked[side] = best
    return picked, {k: round(v, 1) for k, v in totals.items()}


def face_front(arm):
    """Turn about Z so the feet point along -Y (MMD's front)."""
    bones = arm.data.bones
    d = Vector((0.0, 0.0, 0.0))
    for side in ("L", "R"):
        foot, toe = bones.get("Bip001 %s Foot" % side), bones.get("Bip001 %s Toe0" % side)
        if foot is None or toe is None:
            raise RuntimeError("no Bip001 %s Foot / Toe0 to find the front" % side)
        d += (arm.matrix_world.to_3x3() @ (toe.head_local - foot.head_local)).normalized()
    turn = math.atan2(-1.0, 0.0) - math.atan2(d.y, d.x)
    turn = math.atan2(math.sin(turn), math.cos(turn))
    if abs(math.degrees(turn)) > 1.0:
        arm.matrix_world = Matrix.Rotation(turn, 4, "Z") @ arm.matrix_world
    return round(math.degrees(turn), 1)


def skinned_helpers(arm, meshes, limit=80):
    """Diagnostic: non-Biped bones that carry skin - name, parent, vertices, weight sum."""
    count, total = {}, {}
    for m in meshes:
        names = {vg.index: vg.name for vg in m.vertex_groups}
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > 1e-4:
                    n = names.get(g.group, "")
                    count[n] = count.get(n, 0) + 1
                    total[n] = total.get(n, 0.0) + g.weight
    rows = []
    for name in sorted(total, key=lambda n: -total[n]):
        bone = arm.data.bones.get(name)
        if bone is None or name.startswith("Bip001"):
            continue
        rows.append("%s <- %s: %d v / %.0f" % (name, bone.parent.name if bone.parent else "-", count[name], total[name]))
    return rows[:limit]


def prepare(arm, meshes):
    stats = {"socket_meshes": skin_bone_parented(arm, meshes)}
    renamed = 0
    for bone in arm.data.bones:
        if bone.name.startswith("Bip001-"):
            bone.name = bone.name.replace("-", " ")     # Blender renames the vertex groups too
            renamed += 1
    stats["renamed_bones"] = renamed
    left = [vg.name for m in meshes for vg in m.vertex_groups if vg.name.startswith("Bip001-")]
    if left:
        raise RuntimeError("vertex groups did not follow the bone rename: %s" % left[:5])
    height = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    stats["height_source_units"] = round(height, 2)
    stats["dropped_far_bones"] = len(sb.drop_far_sockets(arm, meshes))
    eyes, eye_weights = pick_eye_bones(arm, meshes)
    stats["eye_bone_skin"] = eye_weights
    if len(eyes) < 2:
        stats["made_eye_bones"] = sb.add_eye_bones(arm, meshes)
        eyes = {side: "Bip001 %s Eye" % s for side, s in (("left", "L"), ("right", "R"))
                if "Bip001 %s Eye" % s in arm.data.bones}
    stats["eyes"] = eyes
    stats["skinned_helpers"] = skinned_helpers(arm, meshes)
    stats["undeformed_sockets"] = sb.undeform_sockets(arm, meshes)
    reparented = []
    for m in meshes:                                     # the turn / scale below ride the rig: children follow
        if m.parent != arm:
            world = m.matrix_world.copy()
            m.parent = arm
            m.matrix_world = world
            reparented.append(m.name)
    stats["reparented_meshes"] = reparented
    stats["turned_deg"] = face_front(arm)
    s = 0.01 if height > 20.0 else 1.0                   # UE centimetres
    arm.scale = tuple(x * s for x in arm.scale)
    bpy.context.view_layer.update()
    return eyes, stats


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    suit = load(SUIT_SCRIPT, "roe_suit_pmx")
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath}

    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = character_meshes(arm)
    left_out = [o.name for o in scene.objects if o.type == "MESH" and o not in meshes]
    for obj_name in left_out:
        bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
    report["left_out"] = left_out
    head = next((m for m in meshes if m.data.shape_keys and len(m.data.shape_keys.key_blocks) > 40), None)
    report["shape_keys"] = len(head.data.shape_keys.key_blocks) - 1 if head else 0

    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    meshes, report["joined_meshes"] = sb.join_meshes_sharing_materials(meshes)
    report["uv_tiles_wrapped"] = sb.wrap_uv_tiles(meshes)
    opaque = sb.opaque_materials(meshes)
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    eyes, stats = prepare(arm, meshes)
    report.update(stats)

    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    suit.keep_shape_keys_in_rest_bakes()             # the one mesh has the ARKit keys: bake it into the A-pose too
    os.makedirs(out_dir, exist_ok=True)
    slots, missing = roe.resolve_roe_slots(arm)
    for side, bone in eyes.items():
        slots["%s_eye_bone" % side] = bone
    for side, bone in CHEST_BONES:
        if not slots.get("%s_chest_bone" % side) and bone in arm.data.bones:
            slots["%s_chest_bone" % side] = bone
    missing_optional = [m for m in missing if not slots.get(m)]
    report["missing_optional_slots"] = missing_optional
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
    try:                                             # helpers are never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        if NOT_CLOTH not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + NOT_CLOTH, re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(conv)
    # a skinless source bone that carries skin now was handed someone else's weight by the conversion
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
    if head is not None:
        report["vertex_morphs"], report["morphs_skipped"] = sb.add_arkit_morphs(root, head)

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or ("Converted from The First Descendant by ripper_tpose (scripts/firstdescendant). "
                               "Personal use only.")
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
    holes = sb.transparent_at_faces(path)                # before the fill hides them
    report["opaque_holes"] = {m: v for m, v in holes.items() if m in opaque and v > 0.005}
    report["opaque_textures"] = sb.fill_opaque_alpha(path, opaque)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bytes"] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    with open(os.path.join(out_dir, name + ".report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    print("TFD_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
