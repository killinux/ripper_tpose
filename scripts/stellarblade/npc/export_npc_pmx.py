# -*- coding: utf-8 -*-
"""Stellar Blade NPC look (.blend from build_npc_looks.py / hq_npc_looks.py) -> MMD-ready PMX, through
../export_pmx_blender.py run unchanged (imported as a module, its main() called with this command line).

What an NPC look has that an Eve .blend has not:

  * the face and the hair come with their own armatures, parented to the body's with the rest poses aligned and the
    same Bip001 names (build_npc_blend.py); the exporter takes ONE armature, so they are merged into the body's first:
    shared bones by name (the skinned ones checked to REST_TOLERANCE), bones only the face / hair rig has are copied
    when some skin hangs on them (with the ancestors the body lacks), every mesh is re-bound, the extra armatures
    removed;
  * the faces are Stellar Blade's own facial rig - jaw_open, upLid_down_L, lipCorner_pull ... 180 shapes - not
    ARKit, so the exporter's ARKit RECIPES find nothing; NPC_RECIPES mixes the same MMD set from these names and is
    swapped in when the head has them.  _L / _left is the character's left (Raven: upLid_down_L moves the eye on
    the side the left foot is on).  The jaw_open shape carries the lower teeth itself;
  * the hair chains are HBN_* / HBn_* (HBn_Root = the scalp): mmd_cloth_physics lets a chain under the head swing
    only when its name says hair, so they are renamed Hair_* (Raven's long hair stood still in the first try);
  * a cloth chain hung off a UE body helper - a twist bone or a muscle / joint corrective with the body's own skin on
    it (Raven's thigh strap Ab_RV_ACC_R01 under Ab-R-Thigh-Tw1, Scarlet's skirt panels under the thigh muscles
    Ab-L/R-Venter2) - made mmd_cloth_physics take the helper as the chain's first swinging link (its limb-helper
    pattern knows "twist", not "-Tw1" or "Venter"), and the thigh swung with the skirt; such a chain is hung on the
    first ancestor that is no helper (the limb bone) instead (BODY_HELPER);
  * alpha-clipped materials (the game's masked hair: drawn where alpha >= its clip value, 0.333 for Raven's long
    hair) went into the PMX with the texture's raw alpha - median 0.25 there - and MMD blends alpha, so the hair
    came out thin and see-through.  After the write, a texture only clipped materials use gets its alpha remapped
    to the game's cut (0 below clip - 0.05, 1 above clip + 0.05, a ramp between: soft edges);
    a texture only OPAQUE materials use gets alpha 1 (MMD multiplies texture alpha in; a mask kept there would make
    the part see-through - memory note "texture alpha = masks"); both in ../../pmx_tools/texture_alpha_blender.py;
  * face shapes on more than one mesh: every such mesh gets the MMD mixes under the same names, so one PMX morph moves
    them together; an ARKit head without MetaHuman's TeethLowerDown (Lily) gets the recipes without it, as in
    scripts/firstdescendant (jawOpen carries the teeth), else あいうえお were skipped;
  * toes spelt as helpers (Rael: Ab-L-Toe0 under Bip001-L-Foot) get the Biped name - the exporter finds the front
    by Bip001 Foot -> Toe0;
  * a mesh that only repeats part of another is left out (Lily's look holds her full mesh AND its separate face - the
    same head twice);
  * --collider-skin: the body colliders are measured on the dressed mesh, so hair lying on the chest starts inside
    the upper-body collider and mmd_cloth_physics lets it ignore that collider - Raven's front hair sank into her
    chest in a dance.  ../../mmd_physics/cloth_collision_pmx.py refits the colliders inside the given materials
    (skin, face, a skin-tight suit; wildcards) with thigh halves, and every hair / cloth body collides again.

blender -b --factory-startup <look>_HQ.blend --python export_npc_pmx.py -- --out <dir> --name <stem>
    [--collider-skin "*BaseBody*,*Suit01*,*_Head"] [--hq-materials <look folder>/hq_materials.json]
    [any other option of ../export_pmx_blender.py]
Prints NPC_MERGE={json} before the exporter's SB_PMX_REPORT={json}, then NPC_ALPHA= and NPC_COLLIDERS=.
"""
import argparse
import importlib.util
import json
import os
import re
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
EXPORTER = os.path.join(os.path.dirname(HERE), "export_pmx_blender.py")
FITTER = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mmd_physics", "cloth_collision_pmx.py")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "pmx_tools"))
from texture_alpha_blender import fix_texture_alpha, source_alpha_modes  # noqa: E402
REST_TOLERANCE = 0.5                    # cm (UE units): a skinned shared bone may sit this far off - the pivot moves
                                        # by that much; Citizen_08's eyelid helpers are 0.25 cm off, its head 0
NPC_FACE_KEYS = ("jaw_open", "upLid_down_L", "upLid_down_R")
HAIR_BONE = re.compile(r"^HB[Nn]_(?!Root$)")
# UE body helpers that carry the body's own skin: twist bones and the muscle / joint correctives
BODY_HELPER = re.compile(r"^(?:Ab|Dm)-(?:[LR]-)?(?:(?:Forearm|UpperArm|Calf|Thigh)-Tw|Venter|Becep|Bicep|Tricep|"
                         r"Deltoid|Elbow|Side|Shoulder|Trape|Pectro|Knee|Ankle|Hip|Brochi|NeckSub)", re.IGNORECASE)

# The exporter's RECIPES with Stellar Blade's facial names (same categories, MMD names and weights where a shape
# has a counterpart; ワ / ん added).  Weights were checked on Raven's morph sheet.
NPC_RECIPES = [
    # --- eyes
    ("まばたき", "blink", "EYE", {"upLid_down_L": 1.0, "upLid_down_R": 1.0}),
    ("笑い", "smile", "EYE", {"upLid_down_L": 0.7, "upLid_down_R": 0.7, "squint_lower_left": 0.6,
                             "squint_lower_right": 0.6, "squint_left": 0.3, "squint_right": 0.3}),
    ("ウィンク", "wink", "EYE", {"upLid_down_L": 1.0, "squint_lower_left": 0.4, "squint_left": 0.3}),
    ("ウィンク右", "wink_R", "EYE", {"upLid_down_R": 1.0, "squint_lower_right": 0.4, "squint_right": 0.3}),
    ("ウィンク２", "wink2", "EYE", {"upLid_down_L": 1.0}),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", {"upLid_down_R": 1.0}),
    ("びっくり", "surprised", "EYE", {"upLid_up_L": 1.0, "upLid_up_R": 1.0, "loLid_down_L": 0.5, "loLid_down_R": 0.5}),
    ("じと目", "jito-eye", "EYE", {"upLid_down_L": 0.45, "upLid_down_R": 0.45}),
    ("はぅ", "close><", "EYE", {"upLid_down_L": 1.0, "upLid_down_R": 1.0, "squint_left": 0.6, "squint_right": 0.6,
                               "squint_lower_left": 0.6, "squint_lower_right": 0.6}),
    # --- brows
    ("真面目", "serious", "EYEBROW", {"brow_down_left": 0.35, "brow_down_right": 0.35}),
    ("困る", "trouble", "EYEBROW", {"innerBrow_up": 1.0, "brow_furrow": 0.3}),
    ("にこり", "cheerful", "EYEBROW", {"outerBrow_up_left": 0.6, "outerBrow_up_right": 0.6}),
    ("怒り", "anger", "EYEBROW", {"brow_down_left": 1.0, "brow_down_right": 1.0, "brow_furrow": 0.6}),
    ("上", "brow_up", "EYEBROW", {"brow_up_left": 1.0, "brow_up_right": 1.0}),
    ("下", "brow_down", "EYEBROW", {"brow_down_left": 0.6, "brow_down_right": 0.6}),
    # --- mouth
    ("あ", "a", "MOUTH", {"jaw_open": 0.6, "lowerLip_down": 0.3, "upperLip_up": 0.2}),
    ("い", "i", "MOUTH", {"lip_stretch": 0.8, "upperLip_up": 0.3, "lowerLip_down": 0.3, "jaw_open": 0.08}),
    ("う", "u", "MOUTH", {"lip_pucker": 1.0, "lowerLip_funnel": 0.3, "upperLip_funnel": 0.3, "jaw_open": 0.05}),
    ("え", "e", "MOUTH", {"jaw_open": 0.3, "lip_stretch": 0.5, "lowerLip_down": 0.3}),
    ("お", "o", "MOUTH", {"jaw_open": 0.45, "lowerLip_funnel": 0.8, "upperLip_funnel": 0.8, "lip_pucker": 0.3}),
    ("にやり", "grin", "MOUTH", {"lipCorner_pull": 1.0}),
    ("にっこり", "smile_mouth", "MOUTH", {"lipCorner_pull": 0.6}),
    ("∧", "mouth_∧", "MOUTH", {"lipCorner_down": 1.0}),
    ("口角上げ", "mouth_corner_up", "MOUTH", {"lipCorner_pull": 0.45}),
    ("口角下げ", "mouth_corner_down", "MOUTH", {"lipCorner_down": 0.6}),
    ("口横広げ", "mouth_wide", "MOUTH", {"lip_stretch": 0.6}),
    ("ワ", "wa", "MOUTH", {"jaw_open": 0.5, "lip_stretch": 0.5, "lipCorner_pull": 0.5, "upperLip_up": 0.3}),
    ("ん", "n", "MOUTH", {"lip_stretch": 0.2, "lip_pucker": 0.15}),
]


def weighted_groups(meshes):
    names = set()
    for m in meshes:
        index = {g.index: g.name for g in m.vertex_groups}
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > 0.0:
                    names.add(index[g.group])
    return names


def merge_armatures(scene):
    """The face / hair armatures into the body's (the one without a parent).  Returns a report."""
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    if len(arms) < 2:
        return {}
    main = next((a for a in arms if a.parent is None), arms[0])
    extras = [a for a in arms if a is not main]
    meshes_of = {a.name: [m for m in scene.objects if m.type == "MESH" and m.find_armature() is a] for a in extras}
    report = {"into": main.name, "merged": {}}
    plan = {}
    for a in extras:
        # only the shared bones its meshes are skinned to must line up: Scarlet's face rig has the pelvis and rope
        # sockets 1.1 cm off the body's, its head and neck 0.004 cm
        skinned = weighted_groups(meshes_of[a.name])
        worst = any_gap = 0.0
        for b in a.data.bones:
            mb = main.data.bones.get(b.name)
            if mb is not None:
                gap = ((a.matrix_world @ b.head_local) - (main.matrix_world @ mb.head_local)).length
                any_gap = max(any_gap, gap)
                if b.name in skinned:
                    worst = max(worst, gap)
        if worst > REST_TOLERANCE:
            raise RuntimeError("%s: rest pose of its skinned bones differs from %s's by %.4f"
                               % (a.name, main.name, worst))
        need = set()
        for name in weighted_groups(meshes_of[a.name]):
            b = a.data.bones.get(name)
            while b is not None and b.name not in main.data.bones:
                need.add(b.name)
                b = b.parent
        for n in sorted(need, key=lambda n: len(a.data.bones[n].parent_recursive)):
            b = a.data.bones[n]
            rec = (a.matrix_world @ b.head_local, a.matrix_world @ b.tail_local,
                   (a.matrix_world @ b.matrix_local).to_3x3() @ Vector((0.0, 0.0, 1.0)),
                   b.parent.name if b.parent else None, b.use_deform, len(b.parent_recursive))
            if n in plan and (plan[n][0] - rec[0]).length > REST_TOLERANCE:
                raise RuntimeError("bone %s differs between the extra armatures" % n)
            plan.setdefault(n, rec)
        own = [b.name for b in a.data.bones if b.name not in main.data.bones]
        report["merged"][a.name] = {"meshes": [m.name for m in meshes_of[a.name]], "shared_gap": round(worst, 4),
                                    "unskinned_shared_gap": round(any_gap, 4),
                                    "copied": sorted(need), "left_out_unweighted": len(own) - len(need)}
    if plan:
        bpy.context.view_layer.objects.active = main
        for o in scene.objects:
            o.select_set(o is main)
        bpy.ops.object.mode_set(mode="EDIT")
        edit = main.data.edit_bones
        inv = main.matrix_world.inverted()
        for n, (head, tail, z_axis, parent, deform, _depth) in sorted(plan.items(), key=lambda kv: kv[1][5]):
            e = edit.new(n)
            e.head, e.tail = inv @ head, inv @ tail
            e.align_roll(inv.to_3x3() @ z_axis)
            e.parent = edit.get(parent) if parent else None
            e.use_deform = deform
        bpy.ops.object.mode_set(mode="OBJECT")
    for a in extras:
        for m in meshes_of[a.name]:
            for mod in m.modifiers:
                if mod.type == "ARMATURE" and mod.object is a:
                    mod.object = main
        for child in list(a.children):
            world = child.matrix_world.copy()
            child.parent = main
            child.matrix_world = world
        bpy.data.objects.remove(a, do_unlink=True)
    bones = set(main.data.bones.keys())
    meshes = [m for m in scene.objects if m.type == "MESH" and m.find_armature() is main]
    report["unbound_weighted_groups"] = sorted(weighted_groups(meshes) - bones)
    bpy.context.view_layer.update()
    return report


def drop_duplicate_meshes(scene, tolerance=0.05, share=0.95):
    """A mesh that only repeats part of another - its materials all on the other mesh, its vertices on the other's
    (within ``tolerance`` cm) - is left out: Lily's look holds the full CH_NPC_01_Lilly (body + head) AND the separate
    CH_NPC_01_Face, the same head twice (8580 head vertices each), which flickers in MMD.  Returns 'dropped <- kept'."""
    from mathutils import kdtree
    meshes = sorted([o for o in scene.objects if o.type == "MESH" and not o.hide_render],
                    key=lambda o: -len(o.data.vertices))
    dropped = []
    for i, big in enumerate(meshes):
        if big.name in {d[0] for d in dropped}:
            continue
        mats = {s.material.name for s in big.material_slots if s.material}
        tree = None
        for small in meshes[i + 1:]:
            if small.name in {d[0] for d in dropped}:
                continue
            small_mats = {s.material.name for s in small.material_slots if s.material}
            if not small_mats or not small_mats <= mats:
                continue
            if tree is None:
                tree = kdtree.KDTree(len(big.data.vertices))
                for v in big.data.vertices:
                    tree.insert(big.matrix_world @ v.co, v.index)
                tree.balance()
            near = sum(1 for v in small.data.vertices if tree.find(small.matrix_world @ v.co)[2] <= tolerance)
            if near >= share * len(small.data.vertices):
                dropped.append((small.name, big.name))
    for name, _big in dropped:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    return ["%s <- %s" % d for d in dropped]


def name_biped_toes(arm):
    """Ab-L-Toe0 under Bip001-L-Foot -> Bip001-L-Toe0: Rael's rig spells her toes as helpers, and the exporter finds
    the model's front (and the ROE resolver the toe slot) by the Biped name.  Returns the renamed bones."""
    renamed = []
    for side in ("L", "R"):
        foot = arm.data.bones.get("Bip001-%s-Foot" % side)
        if foot is None or arm.data.bones.get("Bip001-%s-Toe0" % side) is not None:
            continue
        toe = next((c for c in foot.children if c.name == "Ab-%s-Toe0" % side), None)
        if toe is not None:
            toe.name = "Bip001-%s-Toe0" % side             # vertex groups follow
            renamed.append(toe.name)
    return renamed


def name_hair_chains(arm):
    """HBN_LMA01 -> Hair_LMA01 (vertex groups follow the bone rename); HBn_Root stays."""
    renamed = []
    for b in arm.data.bones:
        if HAIR_BONE.match(b.name):
            b.name = "Hair_" + b.name[4:]
            renamed.append(b.name)
    return renamed


def rehang_off_body_helpers(arm):
    """Children of a body helper that are not body helpers themselves -> the first ancestor that is no helper."""
    moves = []
    for b in arm.data.bones:
        if b.parent is None or not BODY_HELPER.match(b.parent.name) or BODY_HELPER.match(b.name):
            continue
        anchor = b.parent
        while anchor is not None and BODY_HELPER.match(anchor.name):
            anchor = anchor.parent
        if anchor is not None:
            moves.append((b.name, anchor.name))
    if moves:
        bpy.context.view_layer.objects.active = arm
        for o in bpy.context.scene.objects:
            o.select_set(o is arm)
        bpy.ops.object.mode_set(mode="EDIT")
        edit = arm.data.edit_bones
        for child, parent in moves:
            edit[child].use_connect = False
            edit[child].parent = edit[parent]
        bpy.ops.object.mode_set(mode="OBJECT")
    return ["%s -> %s" % m for m in moves]


def fit_colliders(pmx_path, skin):
    """cloth_collision_pmx.py on the written PMX (plain Python: Blender's own interpreter has numpy).  Returns the
    tool's summary lines."""
    import subprocess
    tmp = pmx_path + ".fit.pmx"
    r = subprocess.run([sys.executable, FITTER, pmx_path, tmp, "--skin", skin, "--thigh-halves"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.isfile(tmp):
        if os.path.isfile(tmp):
            os.remove(tmp)
        return ["failed (%d): %s" % (r.returncode, (r.stderr or r.stdout)[-600:])]
    os.replace(tmp, pmx_path)
    keep = ("skin:", "rigid bodies", "dynamic bodies collide", "collision groups", "colliders ", "dynamic hitting")
    return [l.strip() for l in r.stdout.splitlines() if l.strip().startswith(keep) or "dynamic bodies" in l][:16]


def mixes_on_every_keyed_mesh(sb, original):
    """The exporter mixes its recipes on ONE head mesh.  Lily's face shapes sit on two meshes (the head and the
    eyes / brows / lashes, 52 ARKit keys each), so the second one gets the same mixes under the same names - mmd_tools
    writes same-named keys of all meshes as one PMX morph, and a blink then closes lids and lashes together."""
    def wrapped(root, head):
        made, skipped = original(root, head)
        for mesh in [o for o in bpy.context.scene.objects if o.type == "MESH" and o is not head
                     and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40]:
            keys = mesh.data.shape_keys.key_blocks
            for kb in keys:
                kb.value = 0.0
            for name, _name_e, _category, mix in sb.RECIPES:
                present = {k: v for k, v in mix.items() if k in keys}
                if name not in made or name in keys or not present:
                    continue
                for k, v in present.items():
                    keys[k].value = v
                new = mesh.shape_key_add(name=name, from_mix=True)
                new.value = 0.0
                for k in present:
                    keys[k].value = 0.0
        return made, skipped
    return wrapped


def main():
    scene = bpy.context.scene
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--collider-skin", default="")
    known, _rest = ap.parse_known_args(argv)
    if "--collider-skin" in sys.argv:                # the exporter's own parser must not see this one
        i = sys.argv.index("--collider-skin")
        del sys.argv[i:i + 2]
    clip, opaque = source_alpha_modes()
    duplicates = drop_duplicate_meshes(scene)
    merge = merge_armatures(scene)
    merge["dropped_duplicate_meshes"] = duplicates
    if merge.get("unbound_weighted_groups"):
        raise RuntimeError("skin on groups no bone carries after the merge: %s" % merge["unbound_weighted_groups"][:8])
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    merge["toes_renamed"] = name_biped_toes(arm)
    merge["hair_bones_renamed"] = len(name_hair_chains(arm))
    merge["rehung_off_body_helpers"] = rehang_off_body_helpers(arm)
    spec = importlib.util.spec_from_file_location("sb_export_pmx", EXPORTER)
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    sb.add_arkit_morphs = mixes_on_every_keyed_mesh(sb, sb.add_arkit_morphs)
    head = next((m for m in scene.objects if m.type == "MESH" and m.data.shape_keys
                 and len(m.data.shape_keys.key_blocks) > 40), None)
    keys = head.data.shape_keys.key_blocks if head else {}
    if all(k in keys for k in NPC_FACE_KEYS):
        sb.RECIPES = NPC_RECIPES
        merge["face_recipes"] = "stellar blade facial rig (%d shapes)" % (len(keys) - 1)
    else:
        merge["face_recipes"] = "ARKit (the exporter's own)" if head else "no face shapes"
        if head is not None and "TeethLowerDown" not in keys:
            # MetaHuman's extra key; Lily's ARKit set lacks it and the recipes skipped あいうえお - jawOpen carries
            # the lower teeth there (the same as scripts/firstdescendant)
            sb.RECIPES = [(n, e, c, {k: v for k, v in mix.items() if k != "TeethLowerDown"})
                          for n, e, c, mix in sb.RECIPES]
            merge["face_recipes"] += ", TeethLowerDown dropped"
    print("NPC_MERGE=" + json.dumps(merge, ensure_ascii=False), flush=True)
    name = known.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    sb.main()
    pmx_path = os.path.join(os.path.abspath(known.out), name, name + ".pmx")
    print("NPC_ALPHA=" + json.dumps(fix_texture_alpha(pmx_path, clip, opaque), ensure_ascii=False), flush=True)
    if known.collider_skin:
        print("NPC_COLLIDERS=" + json.dumps(fit_colliders(pmx_path, known.collider_skin), ensure_ascii=False),
              flush=True)


if __name__ == "__main__":
    main()
