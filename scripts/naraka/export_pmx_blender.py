# -*- coding: utf-8 -*-
"""NARAKA: BLADEPOINT archive .blend (export_model.py / batch_export.py) -> MMD .pmx, inside Blender 3.6 (headless).

The Stellar Blade chain (scripts/stellarblade/export_pmx_blender.py -> the Rise of Eros worker:
Convert_to_MMD5 builds the MMD skeleton and body colliders, mmd_cloth_physics the hair / skirt
chains, ARKit shapes are mixed into the standard MMD expressions, blender2xps bakes node colours
into one texture per material, mmd_tools writes the PMX at 12.5), as in
scripts/firstdescendant/export_pmx_blender.py.  NARAKA's heroes are 3ds Max Bipeds spelt
``gMan <part>`` under Unity's ``MotionRoot``; this file adds what that rig needs:

  * names: ``gMan `` -> ``Bip001 ``, ``MotionRoot`` -> ``Bip001`` (the all-parents bone);
  * the game's runtime nodes (hit / environment colliders, weapon, aim, camera and lock points,
    ``body_dummy``, ``UpAnchor``) carry no skin -> deleted with their skinless subtrees;
  * eyes: ``Face_L_Yanqiu`` / ``Face_R_Yanqiu`` -> 左目 / 右目 + 両目; their ``Face_*_YanZ`` sockets
    are dropped and the lid / eyeball bones hang on the head;
  * breasts: ``L_breast`` / ``R_breast`` -> 左胸 / 右胸 + Eve's sphere physics;
  * expressions: the battle face (``ch_f_face_battle``, shared by every heroine) has no shape keys
    and no mouth or brow bones - only the lids: ``Face_*_Shangyanpi01`` (upper) and
    ``Face_*_Xiayanpi`` (lower), both pivoting at the eye centre.  Turning them about the eye's
    side axis gives ARKit-named eye shapes (eyeBlink / eyeWide / eyeSquint per side, the angles
    measured from the lid margins), which the Stellar Blade recipes mix into まばたき, ウィンク,
    笑い, びっくり, じと目, はぅ ...  No mouth or brow morphs.  The eyelashes ride the lids, so
    they are joined into the face mesh first (one mesh carries the keys);
  * hanging chains stay chains: the add-on retires midline bones under the spine whose names it
    does not know as cloth / hair, and NARAKA names its chains in pinyin (belt_, piaodai_, daizi_,
    M_ribbon_ ...) - see keep_chains_whole();
  * eyelashes get the game's lash colour (the archive .blend shows the white strands of _MainTex),
    see colour_eyelashes(); textures only opaque materials use get alpha 1 (sb.fill_opaque_alpha).

  blender -b X.blend --factory-startup --python export_pmx_blender.py -- --out <dir> [--name N]
          [--model-name M] [--comment C]
Prints NARAKA_PMX={json}.  Writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend
+ <name>.report.json.
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
PREFIX = "gMan "
ROOT = "MotionRoot"
EYE_BONES = {"left": "Face_L_Yanqiu", "right": "Face_R_Yanqiu"}
EYE_SOCKET = re.compile(r"^Face_[LR]_YanZ$")
UPPER_LID = "Face_%s_Shangyanpi01"
LOWER_LID = "Face_%s_Xiayanpi"
CHEST_BONES = (("left", "L_breast"), ("right", "R_breast"))
# lid turns as fractions of the open eye's angle (upper margin -> lower margin, seen from the pivot);
# + closes (upper lid down / lower lid up).  Blink: the lids meet a quarter of the way up, plus a
# hair of overlap so no slit is left.
EYE_SHAPES = {
    "eyeBlink": (0.75, 0.25),
    "eyeWide": (-0.3, -0.05),
    "eyeSquint": (0.1, 0.35),
}
BLINK_OVERLAP_DEG = 0.5
FACE_MESH, LASH_MESH = "face", "eyelash"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Lids that only turn about one axis cross each other when a mix closes them by more than the open
# angle (Eve's はぅ = blink 1 + squint 1 would push the lower lid 45 % past the upper one), so the
# mixes that add squint to a blink get less of it here.
RECIPE_MIX = {
    "笑い": {"eyeBlinkLeft": 0.6, "eyeBlinkRight": 0.6, "eyeSquintLeft": 1.0, "eyeSquintRight": 1.0},
    "ウィンク": {"eyeBlinkLeft": 1.0, "eyeSquintLeft": 0.2},
    "ウィンク右": {"eyeBlinkRight": 1.0, "eyeSquintRight": 0.2},
    "はぅ": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0, "eyeSquintLeft": 0.3, "eyeSquintRight": 0.3},
}

sb = load(SB_SCRIPT, "sb_pmx")
sb.BUST["bones"] = (("左胸", "L_breast"), ("右胸", "R_breast"))
sb.EYE_MAT_RE = re.compile(sb.EYE_MAT_RE.pattern + r"|(^|_)Eye$", re.IGNORECASE)      # female_Eye, not _Eyeslash
sb.RECIPES = [(n, e, c, RECIPE_MIX.get(n, mix)) for n, e, c, mix in sb.RECIPES]


def character_meshes(arm):
    """Meshes deformed by the rig; anything else in the file is scenery."""
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render
            and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def colour_eyelashes(meshes, scene_json):
    """NARAKA's eyelash shader (LX22_Standard_Charactor_Eyelash) paints the lash strands with _EyelashColorL / R
    (black on the battle face; the character creator can change it) where its _SpecGlossMap red channel marks a
    lash - in _MainTex the strands are pure white.  The archive .blend wires _MainTex as the colour, so the lashes
    came out white (the eye-socket ring under them, red channel ~0.08, keeps its own colour).  The lash colour is
    mixed in by that mask before the bake.  Returns {material: 'r g b'}."""
    if not os.path.isfile(scene_json):
        return {}
    with open(scene_json, encoding="utf-8") as fh:
        doc = json.load(fh)
    done = {}
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            info = doc.get("materials", {}).get(mat.name if mat else "")
            if not info or "Eyelash" not in info.get("shader", "") or mat.name in done or not mat.use_nodes:
                continue
            colours = info.get("colors", {})
            left = colours.get("_EyelashColorL", colours.get("_EyelashColorR"))
            if left is None:
                continue
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            files = {n.image.name: n for n in nodes if n.type == "TEX_IMAGE" and n.image}
            mask = files.get(info.get("textures", {}).get("_SpecGlossMap", ""))
            bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
            if mask is None or bsdf is None or not bsdf.inputs["Base Color"].is_linked:
                continue
            source = bsdf.inputs["Base Color"].links[0].from_socket
            split = nodes.new("ShaderNodeSeparateRGB")
            mix = nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MIX"
            mix.inputs["Color2"].default_value = tuple(_linear(c) for c in left[:3]) + (1.0,)
            links.new(mask.outputs["Color"], split.inputs["Image"])
            links.new(split.outputs["R"], mix.inputs["Fac"])
            links.new(source, mix.inputs["Color1"])
            links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
            right = colours.get("_EyelashColorR", left)
            done[mat.name] = " ".join("%.3f" % c for c in left[:3]) + ("" if right[:3] == left[:3] else " (R differs, L used)")
    return done


def drop_runtime_nodes(arm, meshes):
    """Delete bones that carry no skin and have none below them (the game's colliders, weapon /
    aim / camera points, separate roots), keeping the Biped and the face bones.  Returns the names."""
    weighted = sb.weighted_bones(meshes)

    def clean(bone):
        return bone.name not in weighted and all(clean(c) for c in bone.children)

    doomed = [b.name for b in arm.data.bones if clean(b)
              and not b.name.startswith((PREFIX, "Face_")) and b.name != ROOT]
    if doomed:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm.data.edit_bones
        for name in doomed:
            if name in eb:
                eb.remove(eb[name])
        bpy.ops.object.mode_set(mode="OBJECT")
    return sorted(doomed)


def drop_eye_sockets(arm):
    """Face_*_YanZ (skinless, on the eye centre) -> its lid and eyeball bones hang on its parent."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    dropped = []
    for bone in [b for b in eb if EYE_SOCKET.match(b.name)]:
        for child in list(bone.children):
            child.use_connect = False
            child.parent = bone.parent
        dropped.append(bone.name)
        eb.remove(bone)
    bpy.ops.object.mode_set(mode="OBJECT")
    return dropped


def join_lashes(meshes, face):
    """The eyelashes ride the lid bones: join them into the face so one mesh carries the eye keys.
    Returns the mesh list without the eyelash object."""
    lash = next((m for m in meshes if m.name == LASH_MESH), None)
    names = [m.name for m in meshes if m is not lash]
    if lash is not None:
        bpy.ops.object.select_all(action="DESELECT")
        lash.select_set(True)
        face.select_set(True)
        bpy.context.view_layer.objects.active = face
        bpy.ops.object.join()
    return [bpy.data.objects[n] for n in names]


def _lid_margin(face, group, centre, left, up, fwd, lowest):
    """The lid margin point straight in front of the pupil: of the vertices this lid bone owns
    (weight > 0.5) within 3 mm of the eye centre sideways, the lowest (upper lid) or the highest
    (lower lid) seen from the pivot.  Returns its elevation angle (radians)."""
    vg = face.vertex_groups.get(group)
    if vg is None:
        raise RuntimeError("face mesh has no '%s' group" % group)
    best = None
    for v in face.data.vertices:
        w = next((g.weight for g in v.groups if g.group == vg.index), 0.0)
        if w <= 0.5:
            continue
        d = face.matrix_world @ v.co - centre
        if abs(d.dot(left)) > 0.003 or d.dot(fwd) <= 0.0:
            continue
        a = math.atan2(d.dot(up), d.dot(fwd))
        if best is None or (a < best if lowest else a > best):
            best = a
    if best is None:
        raise RuntimeError("no margin vertices for '%s'" % group)
    return best


def measure_lids(arm, face):
    """Per side (ARKit Left = the character's left = the L bones): lid bones, pivot, side axis and the
    open eye's angle between the margins.  Read on the face alone - lash cards hang below the margin."""
    bones = arm.data.bones
    mw = arm.matrix_world
    eye_l, eye_r = (mw @ bones[EYE_BONES[s]].head_local for s in ("left", "right"))
    left = (eye_l - eye_r).normalized()
    up = Vector((0.0, 0.0, 1.0))
    fwd = left.cross(up).normalized()                  # left x up = forward (right-handed)
    sides, report = {}, {}
    for side, s in (("Left", "L"), ("Right", "R")):
        upper, lower = UPPER_LID % s, LOWER_LID % s
        centre = mw @ bones[upper].head_local
        a_up = _lid_margin(face, upper, centre, left, up, fwd, lowest=True)
        a_lo = _lid_margin(face, lower, centre, left, up, fwd, lowest=False)
        gap = a_up - a_lo
        sides[side] = (upper, lower, centre, gap)
        report[side] = {"open_deg": round(math.degrees(gap), 1),
                        "upper_margin_deg": round(math.degrees(a_up), 1),
                        "lower_margin_deg": round(math.degrees(a_lo), 1)}
    return sides, left, report


def make_eye_shapes(arm, face, sides, left):
    """eyeBlink / eyeWide / eyeSquint Left + Right on the face mesh: the lid bones turned about the
    eye's side axis through their pivot (rest = bind pose), the deformed mesh stored as a key."""
    mw = arm.matrix_world
    report = {}
    if face.data.shape_keys is None:
        face.shape_key_add(name="Basis", from_mix=False)
    basis = [v.co.copy() for v in face.data.vertices]
    inv = mw.inverted()
    axis_arm = (inv.to_3x3() @ left).normalized()
    made = []
    for stem, (k_up, k_lo) in EYE_SHAPES.items():
        for side, (upper, lower, centre, gap) in sides.items():
            extra = math.radians(BLINK_OVERLAP_DEG) if stem == "eyeBlink" else 0.0
            turns = {upper: k_up * gap + extra, lower: -(k_lo * gap + extra)}
            c = inv @ centre
            for name, angle in turns.items():
                pb = arm.pose.bones[name]
                pb.matrix_basis = Matrix.Identity(4)
                pb.matrix = (Matrix.Translation(c) @ Matrix.Rotation(angle, 4, axis_arm)
                             @ Matrix.Translation(-c) @ pb.bone.matrix_local)
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            ev = face.evaluated_get(dg)
            coords = [v.co.copy() for v in ev.to_mesh().vertices]
            ev.to_mesh_clear()
            key = face.shape_key_add(name=stem + side, from_mix=False)
            moved = 0
            for i, co in enumerate(coords):
                if (co - basis[i]).length > 1e-5:
                    key.data[i].co = co
                    moved += 1
                else:
                    key.data[i].co = basis[i]
            for name in turns:
                arm.pose.bones[name].matrix_basis = Matrix.Identity(4)
            bpy.context.view_layer.update()
            made.append("%s%s: upper %+.1f deg, lower %+.1f deg, %d verts"
                        % (stem, side, math.degrees(turns[upper]), math.degrees(turns[lower]), moved))
    for kb in face.data.shape_keys.key_blocks:
        kb.value = 0.0
    report["shapes"] = made
    return report


def keep_chains_whole():
    """Convert_to_MMD5's classifier calls a bone under a spine bone and on the midline 'merge' (a spine
    segment) and retires it into the nearest bone unless CLOTH_RE / HAIR_RE / BREAST_RE knows its name;
    the Stellar Blade premerge follows the same verdict.  NARAKA's hanging chains have pinyin names the
    add-on does not know (belt_, piaodai_, daizi_, M_ribbon_ ... in 495 outfits): Viper Ning's front sash
    (belt_01-04, under Spine1) went into 上半身2 and lost its physics.  Here a bone that heads a chain
    (has child bones) or hangs in one (its parent is not a mapped bone) is 'other' (kept) instead."""
    import importlib
    hc = importlib.import_module("Convert_to_MMD5.helper_classifier")
    original = getattr(hc.classify_helpers, "naraka_original", hc.classify_helpers)

    def classify(armature_data, skeleton_map):
        result = original(armature_data, skeleton_map)
        for name, kind in list(result.items()):
            if kind != "merge":
                continue
            bone = armature_data.bones[name]
            parent_kind = result.get(bone.parent.name) if bone.parent else None
            if bone.children or parent_kind not in ("mapped", None):
                result[name] = "other"
        return result

    classify.naraka_original = original
    for module in ("Convert_to_MMD5.helper_classifier", "Convert_to_MMD5.convert.identify",
                   "Convert_to_MMD5.convert.weights.transfer"):
        importlib.import_module(module).classify_helpers = classify


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


def prepare(arm, meshes):
    face = next((m for m in meshes if m.name == FACE_MESH), None)
    if face is None:
        raise RuntimeError("no '%s' mesh (NARAKA battle face) in the file" % FACE_MESH)
    stats = {"dropped_bones": drop_runtime_nodes(arm, meshes), "dropped_eye_sockets": drop_eye_sockets(arm)}
    sides, left, stats["eye_lids"] = measure_lids(arm, face)
    meshes = join_lashes(meshes, face)
    stats["eye_shapes"] = make_eye_shapes(arm, face, sides, left)
    renamed = 0
    for bone in arm.data.bones:
        if bone.name.startswith(PREFIX):
            bone.name = "Bip001 " + bone.name[len(PREFIX):]     # Blender renames the vertex groups too
            renamed += 1
    arm.data.bones[ROOT].name = "Bip001"
    stats["renamed_bones"] = renamed + 1
    left = [vg.name for m in meshes for vg in m.vertex_groups if vg.name.startswith(PREFIX)]
    if left:
        raise RuntimeError("vertex groups did not follow the bone rename: %s" % left[:5])
    height = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    stats["height_source_units"] = round(height, 3)
    stats["undeformed_sockets"] = sb.undeform_sockets(arm, meshes)
    stats["turned_deg"] = face_front(arm)
    if height > 20.0:                                          # centimetres (the archive is in metres)
        arm.scale = tuple(x * 0.01 for x in arm.scale)
    bpy.context.view_layer.update()
    return face, meshes, stats


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

    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    meshes, report["joined_meshes"] = sb.join_meshes_sharing_materials(meshes)
    report["uv_tiles_wrapped"] = sb.wrap_uv_tiles(meshes)
    opaque = sb.opaque_materials(meshes)
    report["eyelash_colour"] = colour_eyelashes(meshes, os.path.join(os.path.dirname(bpy.data.filepath), "scene.json"))
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    face, meshes, stats = prepare(arm, meshes)
    report.update(stats)

    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    suit.keep_shape_keys_in_rest_bakes()             # the face carries the eye keys: bake it into the A-pose too
    keep_chains_whole()
    os.makedirs(out_dir, exist_ok=True)
    slots, missing = roe.resolve_roe_slots(arm)
    for side, bone in EYE_BONES.items():
        if bone in arm.data.bones:
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
    report["vertex_morphs"], report["morphs_skipped"] = sb.add_arkit_morphs(root, face)

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or ("Converted from NARAKA: BLADEPOINT by ripper_tpose (scripts/naraka). "
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
    print("NARAKA_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
