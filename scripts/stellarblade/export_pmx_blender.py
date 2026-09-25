# -*- coding: utf-8 -*-
"""Stellar Blade Eve .blend -> MMD-ready PMX.

Reuses the Rise of Eros PMX worker (scripts/riseoferos/export_character_model_blender.py)
function by function - one implementation, not a copy - because Eve is a 3ds Max Biped
rig too: slot resolution, limb-helper planning, shoulder relax, the 37 degree A-pose,
Convert_to_MMD5's one-click conversion, 付与 grants, body colliders, mmd_cloth_physics,
the tear gate, alpha-0 blank slots, the mmd_tools export at 12.5 and the grant-order check.

What is Eve-specific, done here before / after that sequence:

  * the Biped bones are spelt with hyphens (``Bip001-L-Clavicle``); the ROE resolver and
    Convert_to_MMD5 read the space form, so they are renamed (vertex groups follow);
  * the scene is in centimetres (UE); it is scaled to metres like an FBX/XPS import;
  * the PSK comes in facing +-X; MMD wants the model facing -Y in Blender (-Z in the PMX)
    and the A-pose lowers the arms about the front/back axis, so the rig is turned to face
    -Y first - where the toes point is the front (on the unturned rig the A-pose twisted
    the arms to 57 / 49 degrees instead of 37, and the model stood sideways in MMD);
  * UE socket / FX bones carry no skin and some sit metres away (a drone start point 6 m
    out, ``FX_GunFire_Rail_End`` 22 m below the floor); Convert_to_MMD5 reads a skeleton
    taller than 10 m as a centimetre rig and shrinks the whole model x0.1, so unweighted
    bone subtrees outside the body box are deleted first;
  * mmd_cloth_physics finds garments by shape, and a two-bone ``Dm-*-Point`` marker chain
    (UE rig helpers, not cloth) passes that test; rigid bodies on Dm- bones are removed;
  * hidden helper objects (build_standalone's physics proxy) are removed, not exported;
  * materials: mmd_tools keeps ONE texture per material and grabbed the wrong one wherever
    the colour is computed by nodes - both hair materials got the grey PonyTail_Alpha mask,
    the procedural iris came out black, the mouth interior (no texture) grey, and the
    translucent helper shells (eye occlusion, tear film, teeth shadow) were written opaque,
    ringing the eyes in white.  fix_pmx_materials() bakes the node-computed colour with
    blender2xps, gives shells alpha 0 and flat materials their own base colour, and sets MMD
    lighting values (diffuse 1, ambient 0.5, low specular - the defaults were diffuse 0.4 and
    specular 1.0: dark and oily);
  * the face is a MetaHuman-style head with the 52 ARKit blendshapes and no face bones,
    so expressions are real VERTEX morphs: the standard MMD set (まばたき, あいうえお,
    笑い, ウィンク, 眉 ...) is mixed from ARKit shapes (RECIPES below), and the ARKit
    shapes themselves are exported too, under 'other'.

blender -b <Eve_*.blend> --python export_pmx_blender.py -- --out <dir> [--name <stem>]
Prints SB_PMX_REPORT={json}.
"""
import argparse
import importlib.util
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORKER = os.path.join(REPO, "scripts", "riseoferos", "export_character_model_blender.py")
sys.path.insert(0, os.path.join(REPO, "scripts", "blender_addons"))     # mmd_cloth_physics etc.
# blender2xps (sibling repo) owns "which texture is the colour, what needs baking, what is a
# translucent helper shell" - the same answers the XPS export uses, so reuse them
B2X = os.environ.get("BLENDER2XPS", os.path.join(os.path.dirname(os.path.dirname(REPO)), "blender2xps"))
sys.path.insert(0, B2X)

# MMD morph = mix of ARKit shapes.  Categories: EYE / EYEBROW / MOUTH (PMX panel groups).
RECIPES = [
    # --- eyes
    ("まばたき", "blink", "EYE", {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0}),
    ("笑い", "smile", "EYE", {"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.8, "eyeSquintLeft": 0.5,
                             "eyeSquintRight": 0.5, "cheekSquintLeft": 0.5, "cheekSquintRight": 0.5}),
    ("ウィンク", "wink", "EYE", {"eyeBlinkLeft": 1.0, "eyeSquintLeft": 0.4, "cheekSquintLeft": 0.4}),
    ("ウィンク右", "wink_R", "EYE", {"eyeBlinkRight": 1.0, "eyeSquintRight": 0.4, "cheekSquintRight": 0.4}),
    ("ウィンク２", "wink2", "EYE", {"eyeBlinkLeft": 1.0}),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", {"eyeBlinkRight": 1.0}),
    ("びっくり", "surprised", "EYE", {"eyeWideLeft": 1.0, "eyeWideRight": 1.0}),
    ("じと目", "jito-eye", "EYE", {"eyeBlinkLeft": 0.45, "eyeBlinkRight": 0.45}),
    ("はぅ", "close><", "EYE", {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0, "eyeSquintLeft": 1.0,
                               "eyeSquintRight": 1.0, "cheekSquintLeft": 0.6, "cheekSquintRight": 0.6}),
    # --- brows
    ("真面目", "serious", "EYEBROW", {"browDownLeft": 0.35, "browDownRight": 0.35}),
    ("困る", "trouble", "EYEBROW", {"browInnerUp": 1.0}),
    ("にこり", "cheerful", "EYEBROW", {"browOuterUpLeft": 0.6, "browOuterUpRight": 0.6}),
    ("怒り", "anger", "EYEBROW", {"browDownLeft": 1.0, "browDownRight": 1.0}),
    ("上", "brow_up", "EYEBROW", {"browInnerUp": 0.6, "browOuterUpLeft": 0.8, "browOuterUpRight": 0.8}),
    ("下", "brow_down", "EYEBROW", {"browDownLeft": 0.6, "browDownRight": 0.6}),
    # --- mouth (the lower teeth ride the jaw only if their own shape is mixed in)
    ("あ", "a", "MOUTH", {"jawOpen": 0.6, "TeethLowerDown": 0.6, "mouthLowerDownLeft": 0.3,
                         "mouthLowerDownRight": 0.3, "mouthUpperUpLeft": 0.2, "mouthUpperUpRight": 0.2}),
    ("い", "i", "MOUTH", {"mouthStretchLeft": 0.8, "mouthStretchRight": 0.8, "mouthUpperUpLeft": 0.3,
                         "mouthUpperUpRight": 0.3, "mouthLowerDownLeft": 0.3, "mouthLowerDownRight": 0.3,
                         "jawOpen": 0.08, "TeethLowerDown": 0.08}),
    ("う", "u", "MOUTH", {"mouthPucker": 1.0, "mouthFunnel": 0.3, "jawOpen": 0.05, "TeethLowerDown": 0.05}),
    ("え", "e", "MOUTH", {"jawOpen": 0.3, "TeethLowerDown": 0.3, "mouthStretchLeft": 0.5,
                         "mouthStretchRight": 0.5, "mouthLowerDownLeft": 0.3, "mouthLowerDownRight": 0.3}),
    ("お", "o", "MOUTH", {"jawOpen": 0.45, "TeethLowerDown": 0.45, "mouthFunnel": 0.8, "mouthPucker": 0.3}),
    ("にやり", "grin", "MOUTH", {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0}),
    ("にっこり", "smile_mouth", "MOUTH", {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.6}),
    ("∧", "mouth_∧", "MOUTH", {"mouthFrownLeft": 1.0, "mouthFrownRight": 1.0}),
    ("口角上げ", "mouth_corner_up", "MOUTH", {"mouthSmileLeft": 0.45, "mouthSmileRight": 0.45}),
    ("口角下げ", "mouth_corner_down", "MOUTH", {"mouthFrownLeft": 0.6, "mouthFrownRight": 0.6}),
    ("口横広げ", "mouth_wide", "MOUTH", {"mouthStretchLeft": 0.6, "mouthStretchRight": 0.6}),
]


def load_worker():
    spec = importlib.util.spec_from_file_location("roe_char_worker", WORKER)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_eve(arm, meshes):
    """Hyphenated Biped names -> spaces, centimetres -> metres.  Returns stats."""
    renamed = 0
    for bone in arm.data.bones:
        if bone.name.startswith("Bip001-"):
            bone.name = bone.name.replace("-", " ")     # Blender renames the vertex groups too
            renamed += 1
    missing = [vg.name for m in meshes for vg in m.vertex_groups
               if vg.name.startswith("Bip001-")]
    if missing:
        raise RuntimeError("vertex groups did not follow the bone rename: %s" % missing[:5])
    height_cm = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    dropped = drop_far_sockets(arm, meshes)
    # face -Y: rotate about Z so the foot->toe direction points along -Y.  Both feet,
    # averaged: one foot alone is splayed outwards (~10 degrees on Eve's left foot)
    bones = arm.data.bones
    d = Vector((0.0, 0.0, 0.0))
    for side in ("L", "R"):
        foot, toe = bones.get("Bip001 %s Foot" % side), bones.get("Bip001 %s Toe0" % side)
        if foot is None or toe is None:
            raise RuntimeError("no Bip001 %s Foot / Toe0 to find the front" % side)
        d += (arm.matrix_world.to_3x3() @ (toe.head_local - foot.head_local)).normalized()
    turn = math.atan2(-1.0, 0.0) - math.atan2(d.y, d.x)
    turn = math.atan2(math.sin(turn), math.cos(turn))
    arm.matrix_world = Matrix.Rotation(turn, 4, "Z") @ arm.matrix_world
    arm.scale = (0.01, 0.01, 0.01)                   # bake_rig_transforms applies both
    bpy.context.view_layer.update()
    return {"renamed_bones": renamed, "height_cm": round(height_cm, 2),
            "turned_deg": round(math.degrees(turn), 1), "dropped_far_bones": dropped}


def drop_far_sockets(arm, meshes, margin=0.25):
    """Delete bone subtrees with no skin weight that reach outside the body box."""
    weighted = set()
    for m in meshes:
        names = {vg.index: vg.name for vg in m.vertex_groups}
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > 1e-4 and g.group in names:
                    weighted.add(names[g.group])
    pts = [m.matrix_world @ Vector(c) for m in meshes for c in m.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    pad = (hi - lo) * margin

    def outside(p):
        return any(p[i] < lo[i] - pad[i] or p[i] > hi[i] + pad[i] for i in range(3))

    def clean(bone):
        return bone.name not in weighted and all(clean(c) for c in bone.children)

    far = [b.name for b in arm.data.bones if clean(b)
           and (outside(arm.matrix_world @ b.head_local) or outside(arm.matrix_world @ b.tail_local))]
    if far:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm.data.edit_bones
        doomed = set()
        for name in far:
            stack = [eb[name]]
            while stack:
                b = stack.pop()
                doomed.add(b.name)
                stack.extend(b.children)
        for name in doomed:
            eb.remove(eb[name])
        bpy.ops.object.mode_set(mode="OBJECT")
        far = sorted(doomed)
    return far


def drop_marker_physics(prefix="Dm-"):
    """Remove rigid bodies (and their joints) that ended up on UE marker bones."""
    scene_objs = list(bpy.context.scene.objects)
    bodies = [o for o in scene_objs if getattr(o, "mmd_type", "") == "RIGID_BODY"
              and o.mmd_rigid.bone.startswith(prefix)]
    doomed = set(bodies)
    for j in scene_objs:
        if getattr(j, "mmd_type", "") == "JOINT" and j.rigid_body_constraint:
            c = j.rigid_body_constraint
            if c.object1 in doomed or c.object2 in doomed:
                doomed.add(j)
    names = sorted(o.mmd_rigid.bone for o in bodies)
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    return names


def _principled_color(mat):
    from blender2xps import materials as b2m
    node = b2m._find_principled(mat.node_tree) if mat.use_nodes and mat.node_tree else None
    if node is not None:
        c = node.inputs["Base Color"].default_value
        return (c[0], c[1], c[2])
    c = mat.diffuse_color
    return (c[0], c[1], c[2])


def bake_node_colours(meshes, tex_dir):
    """Bake every material whose colour is computed by nodes (hair root/tip mixes over a
    strand mask, the procedural iris ...) to a plain RGBA texture.

    Must run BEFORE the conversion: mmd_tools then adds its MMD shader group to every
    material, and blender2xps treats a material carrying that group as handled natively
    and bakes nothing.  Returns {material name: (png path, cut-out fraction)}."""
    from blender2xps import materials as b2m      # the add-on package (junction to the repo)

    os.makedirs(tex_dir, exist_ok=True)
    out, seen = {}, set()
    for obj in meshes:
        todo = []
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name in seen:
                continue
            seen.add(mat.name)
            if b2m.material_is_invisible(mat) or b2m.material_is_translucent_shell(mat):
                continue
            if b2m.material_wants_bake(mat):
                todo.append(mat)
        if not todo:
            continue
        baked = b2m.bake_object_materials(bpy.context, obj, todo)
        for mat in todo:
            tex = baked.get(mat.name)
            if tex is None:
                continue
            path = os.path.join(tex_dir, b2m._safe_filename(mat.name) + "_baked.png")
            if b2m.save_rgba_png(path, tex.width, tex.height, tex.rgba):
                out[mat.name] = (path, float((tex.rgba[:, 3] < 0.5).mean()), tex.width)
    return out


def fix_pmx_materials(meshes, baked):
    """Give every material what MMD needs: one colour texture that really is the colour,
    alpha 0 on helper shells, and MMD lighting values."""
    from blender2xps import materials as b2m
    from mmd_tools.core.material import FnMaterial

    report = {"baked": [], "shells": [], "flat": []}
    done = set()
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name in done:
                continue
            done.add(mat.name)
            mm = mat.mmd_material
            if b2m.material_is_invisible(mat) or b2m.material_is_translucent_shell(mat):
                mm.alpha = 0.0
                report["shells"].append(mat.name)
                continue
            mm.diffuse_color = (1.0, 1.0, 1.0)
            mm.ambient_color = (0.5, 0.5, 0.5)
            mm.specular_color = (0.12, 0.12, 0.12)
            mm.shininess = 12.0
            if mat.name in baked:
                path, cut, size = baked[mat.name]
                FnMaterial(mat).create_texture(path)
                if cut > 0.02:                        # strand cards: seen from both sides
                    mm.is_double_sided = True
                if "hair" in mat.name.lower():
                    mm.specular_color = (0.3, 0.3, 0.3)
                    mm.shininess = 30.0
                report["baked"].append("%s (%d px, %.0f%% cut)" % (mat.name, size, 100 * cut))
                continue
            tex = FnMaterial(mat).get_texture()
            if tex is None or getattr(tex, "image", None) is None:
                col = _principled_color(mat)
                mm.diffuse_color = col
                mm.ambient_color = tuple(c * 0.5 for c in col)
                report["flat"].append(mat.name)
    return report


def add_arkit_morphs(root, head):
    """Mix the ARKit shape keys into the standard MMD expression set (vertex morphs)."""
    keys = head.data.shape_keys.key_blocks
    for kb in keys:
        kb.value = 0.0
    made, skipped = [], []
    for name, name_e, category, mix in RECIPES:
        absent = [k for k in mix if k not in keys]
        if absent or name in keys:
            skipped.append((name, absent or "exists"))
            continue
        for k, v in mix.items():
            keys[k].value = v
        new = head.shape_key_add(name=name, from_mix=True)
        new.value = 0.0
        for k in mix:
            keys[k].value = 0.0
        made.append((name, name_e, category))
    mmd = root.mmd_root
    have = {m.name for m in mmd.vertex_morphs}
    for name, name_e, category in made:
        if name not in have:
            item = mmd.vertex_morphs.add()
            item.name, item.name_e, item.category = name, name_e, category
    for kb in list(keys)[1:]:                         # the ARKit shapes themselves, as 'other'
        if kb.name not in have and kb.name not in {m[0] for m in made}:
            item = mmd.vertex_morphs.add()
            item.name, item.name_e, item.category = kb.name, kb.name, "OTHER"
    # MMD's standard names first (in RECIPES order), then the raw ARKit shapes: the
    # conversion registered the ARKit keys before our mixes existed, so move ours up.
    # The exporter orders the PMX morph list by this collection too.
    for target, (name, _e, _c) in enumerate(made):
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(name), target)
    from mmd_tools.operators.display_item import DisplayItemQuickSetup
    mmd.display_item_frames["表情"].data.clear()     # else it keeps the old order
    DisplayItemQuickSetup.load_facial_items(mmd)
    return [m[0] for m in made], skipped


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    args = ap.parse_args(argv)

    roe = load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")

    for obj in list(scene.objects):                  # build_standalone's hidden proxy etc.
        if obj.type == "MESH" and obj.hide_render:
            bpy.data.objects.remove(obj, do_unlink=True)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]
    head = next((m for m in meshes if m.data.shape_keys and len(m.data.shape_keys.key_blocks) > 40), None)

    report = {"name": name, "pmx": path}
    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    baked = bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    report.update(prepare_eve(arm, meshes))

    # --- the ROE sequence (export_pmx), with the Eve morph step before the write
    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    os.makedirs(out_dir, exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)
    slots, missing_optional = roe.resolve_roe_slots(arm)
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    if missing_required:
        raise RuntimeError("rig lacks joints the MMD conversion needs: %s" % ", ".join(missing_required))
    roe.bake_rig_transforms(arm, meshes)
    # measured after the cm -> m bake (world geometry unchanged), so both sides share units
    before = roe.edge_lengths(meshes)
    report["height_m"] = round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)
    helper_plans, helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
    report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    root, stats = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(stats)
    report["dropped_marker_physics"] = drop_marker_physics()
    report["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    report["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = fix_pmx_materials(meshes, baked)
    if head is not None:
        report["vertex_morphs"], report["morphs_skipped"] = add_arkit_morphs(root, head)

    # otherwise MMD lists it as mmd_tools' default "New MMD Model"
    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or "Converted from Stellar Blade by ripper_tpose (scripts/stellarblade)."
    text = bpy.data.texts.new(name + "_comment")
    text.from_string(comment.replace(r"\n", "\n"))     # a literal \n on the command line = new line
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
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    print("SB_PMX_REPORT=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
