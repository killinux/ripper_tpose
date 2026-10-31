# -*- coding: utf-8 -*-
"""AION2 .blend (build_blend.py) -> MMD .pmx, inside Blender 3.6 (headless).

The Crisis Core / FF7 / Stellar Blade chain (scripts/ccff7r/export_pmx_blender.py ->
scripts/final/export_ff7_pmx_blender.py -> scripts/stellarblade/export_pmx_blender.py -> the Rise of Eros
worker): mmd_tools writes the PMX, Convert_to_MMD5 builds the MMD skeleton and the body colliders,
mmd_cloth_physics the hair / skirt / sleeve / cape chains, blender2xps decides which texture is the colour.
AION2 characters are 3ds Max Biped rigs like Rise of Eros, so the ROE resolver finds the joints; this file only
adds what the AION2 rigs need:

  * hyphenated Biped names (``Bip001-L-Clavicle``) -> spaces, the spelling the resolver and Convert_to_MMD5 read;
  * eyes: ``b_L_Eye_0`` / ``b_R_Eye_0`` (player and NPC rig) or ``Bone_eye_L`` / ``Bone_eye_R`` (cutscene rig),
    so VMD gaze keys move them;
  * the face rig - ``Face_Root``'s ~120 ``b_*`` joints (brows, lids, lips, cheeks, teeth), the ``Helmet``
    sockets and the cutscene rig's lids (``Bone_eye_L_upper`` ...) - is merged into the head after the expressions
    are taken from it (below): the add-on would hand that skin to the eyes;
  * breasts: ``b_L_Breast_Base`` + ``b_L_Breast_001`` become one bone a side (``L_Chest`` on the cutscene rig)
    carrying the Eve-style bust physics;
  * the muscle helpers (``L_Bipceps``, ``L_Triceps``, ``L_Deltoid``, ``L_Trapezius``, ``L_Lat``,
    ``L_Quadriceps``, ``L_CalfMuscle``, ``L_Wrist_*``, ``L_Ankle_Fwd``, ``L_Butt`` / ``L_Butt_Jiggle``,
    ``Pelvis_Width``, ``Stomach``) are limb helpers, never cloth: two of them in a row (Butt -> Butt_Jiggle)
    would otherwise pass the garment test and swing;
  * chain names the cloth classifiers would not recognise are spelt out: everything under ``Skirt_Root``
    (``S_002_B_L_001``, Leda's ``P_001_F_001``) -> ``Skirt_*``, the hanging sleeves ``LinkFore_*`` ->
    ``Sleeve_*``, so mmd_cloth_physics picks the skirt / sleeve presets;
  * centimetres -> metres; build_blend.py already faces -Y;
  * MMD draws one colour map, without the normal / ORM maps the game shades with: a garment gets its normal map's
    relief multiplied into the colour (Yustiel's dress is one flat colour - its embroidery, ornaments and folds
    are all in the normal map) and garments, skin and faces the ORM's ambient occlusion (bake_pmx_textures;
    ``--relief 0`` / ``--no-ao`` leave them out);
  * expressions are VERTEX morphs from the game's own ARKit poses (facs_morphs.py, the pose asset extracted by
    face_data.py): one shape key per pose while the face bones still exist, kept aside while the conversion
    poses the arms (its pose bakes skip meshes with shape keys) and put back after, then the standard MMD set
    (まばたき, あいうえお, 笑い, ウィンク, 眉 ...) mixed from them with the Stellar Blade recipes, and the 52 ARKit
    shapes themselves under 'other'.  The recipes' ``TeethLowerDown`` is left out: the lower teeth ride
    ``b_C_TeethLower_0``, which jawOpen already turns.

  * hair skinned only to the body (Yustiel: no hair bones) gets generated chains first (hair_chains.py), so it
    swings like the others (``--hair-chains off`` leaves it on the body);
  * ``--albedo-dir`` swaps the .blend's colour maps for same-named files from a folder - AI-upscaled copies
    (E:\\tools\\upscale\\esrgan.py, 4x-UltraSharp): the game's own maximum is 1024 for NPC outfits.

  blender -b <id>.blend --python export_pmx_blender.py -- --out <dir> [--name N] [--model-name M]
          [--comment C] [--facs <pose asset json> | --facs none] [--head-psk <head part .psk>]
          [--game-faces <json> | none] [--relief 0.6] [--no-ao] [--hair-chains auto|off] [--albedo-dir <dir>]
Prints AION2_PMX={json}.  Writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend.
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
FF7_SCRIPT = os.path.join(REPO, "scripts", "final", "export_ff7_pmx_blender.py")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "pmx_tools"))
import facs_morphs  # noqa: E402
import hair_chains  # noqa: E402
from texture_alpha_blender import fix_texture_alpha, source_alpha_modes  # noqa: E402

RELIEF = 0.6            # how much a garment's normal-map slopes darken its colour (0 = off)
RELIEF_POWER = 2.0
# bake_materials.py already darkens the colour maps by part of the ORM's AO: albedo x (k + (1 - k) x AO), k per kind
# (bake_armor 0.55, bake_skin_or_face 0.65) - the PMX textures add the rest, so they carry the full AO once
BAKED_AO_KEEP = {"armor": 0.55, "phantom": 0.55, "skin": 0.65, "face": 0.65}
GARMENT_KINDS = ("armor", "phantom")
AO_MIN_MEDIAN = 0.25    # an AO channel darker than this at its median is an unused channel, not occlusion
LEGS_INSIDE = "leave"   # mmd_cloth_physics default; "collide": skirt fronts lying on the thighs still hit them
DEFAULT_FACS = r"E:\aion2_exports\_meta\face\GF_Head_006_FACS_PA.json"
DEFAULT_GAME_FACES = r"E:\aion2_exports\_meta\face\GF_CineFacial_PoseAsset_01.json"

FACE_ROOTS = ("Face_Root", "Helmet")
FACE_EXTRA = re.compile(r"^Bone_eye_[LR]_(upper|under)$")       # the cutscene rig's lids, straight under the head
WEAPON_RE = re.compile(r"(^|_)weapon", re.IGNORECASE)
PET_RE = re.compile(r"^(Bip(?!001)\d{3})\b")                    # Bip002-... = a second Biped rig (a pet)
HEAD_HEIGHT_CM = 166.9      # Yustiel's head joint; a model whose head is above 2 m is scaled to this (Siel 272.6)
EYES = {"left": ("b_L_Eye_0", "Bone_eye_L"), "right": ("b_R_Eye_0", "Bone_eye_R")}
# (the bone that stays, the bones merged into it)
BREASTS = {"left": (("b_L_Breast_Base", ("b_L_Breast_001",)), ("L_Chest", ())),
           "right": (("b_R_Breast_Base", ("b_R_Breast_001",)), ("R_Chest", ()))}
MUSCLE_HELPERS = (r"bipceps|biceps|triceps|deltoid|trapezius|quadriceps|calfmuscle|butt|jiggle|pelvis_width"
                  r"|stomach|^[lr]_lat$|_fwd$|wrist")
# (subtree root or name regex, prefix).  "cloth" is not on Convert_to_MMD5's word list: Siel's shawl behind her back
# (B_hand_cloth01-04, under Spine on the midline) was merged into the spine as a helper and tore 13 edges when the
# arms came down
CLOTH_RENAMES = (("Skirt_Root", "Skirt_"), ("^LinkFore_", "Sleeve_"), ("(?i)cloth", "Drape_"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ff7 = load(FF7_SCRIPT, "ff7_pmx")        # merge_bones / pick; loads the SB module
sb = ff7.sb
sb.EYE_MAT_RE = re.compile(r"_Eye[LR]?(\.\d+)?$", re.IGNORECASE)   # MI_<id>_Eye (Snotra: _EyeL / _EyeR), not _Eye_AO
sb.SKIN_HELPER_RE = re.compile(r"^[LR]_(UpperArmTwist|ForearmTwist|Bipceps|Triceps|Deltoid|Elbow|ThighTwist"
                               r"|CalfTwist|Knee|Quadriceps|CalfMuscle)")


def rename_biped(arm, meshes):
    """Bip001-L-Clavicle -> Bip001 L Clavicle (Blender renames the vertex groups with the bones)."""
    renamed = 0
    for bone in arm.data.bones:
        if bone.name.startswith("Bip001-"):
            bone.name = bone.name.replace("-", " ")
            renamed += 1
    stale = [vg.name for m in meshes for vg in m.vertex_groups if vg.name.startswith("Bip001-")]
    if stale:
        raise RuntimeError("vertex groups did not follow the bone rename: %s" % stale[:5])
    return renamed


def rename_cloth_bones(arm, meshes):
    """Prefix chain bones so Convert_to_MMD5's word list and mmd_cloth_physics' presets see what they are."""
    bones = arm.data.bones
    plan = {}
    for anchor, prefix in CLOTH_RENAMES:
        if anchor in bones:                    # a subtree: every bone below the root
            stack = list(bones[anchor].children)
            while stack:
                b = stack.pop()
                plan.setdefault(b.name, prefix)
                stack.extend(b.children)
        else:
            rx = re.compile(anchor)
            for b in bones:
                if rx.search(b.name):
                    plan.setdefault(b.name, prefix)
    done = []
    for old, prefix in sorted(plan.items()):
        new = prefix + old
        if old.lower().startswith(prefix.lower()) or new in bones:
            continue
        bones[old].name = new
        for m in meshes:
            vg = m.vertex_groups.get(old)
            if vg is not None and m.vertex_groups.get(new) is None:
                vg.name = new
        done.append("%s -> %s" % (old, new))
    return done


def drop_weapons(arm, meshes):
    """The skin of weapon bones hanging straight off the root (Siel's orb on ``weapon_ctrl``, 3.4 m in front of her
    in the cut-scene's bind pose) is deleted, like the other exporters' weapons; the bone, skinless now, goes with
    drop_far_sockets.  Returns the bone names."""
    import bmesh
    names = {b.name for b in arm.data.bones if WEAPON_RE.search(b.name) and
             (b.parent is None or b.parent.parent is None)}
    if not names:
        return []
    for m in meshes:
        idx = {vg.index for vg in m.vertex_groups if vg.name in names}
        if not idx:
            continue
        doomed = {v.index for v in m.data.vertices
                  if sum(g.weight for g in v.groups if g.group in idx) >= 0.5}
        if not doomed:
            continue
        bm = bmesh.new()
        bm.from_mesh(m.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context="VERTS")
        bm.to_mesh(m.data)
        bm.free()
    return sorted(names)


def merge_pets(arm, meshes):
    """A second Biped rig (Urd's squirrel: Bip002-*, on her right shoulder) becomes one bone: without it the cloth
    add-on took the creature's 30-odd bones for a coat and swung it.  Returns "root <- n bones" lines."""
    groups = {}
    for b in arm.data.bones:
        m = PET_RE.match(b.name)
        if m:
            groups.setdefault(m.group(1), []).append(b.name)
    out = []
    for prefix, names in sorted(groups.items()):
        inside = set(names)
        roots = [n for n in names if arm.data.bones[n].parent is None or arm.data.bones[n].parent.name not in inside]
        keep = roots[0]
        # descendants of the rig that are not Bip00N-named (props, tails) go along
        stack = [arm.data.bones[r] for r in roots]
        while stack:
            b = stack.pop()
            inside.add(b.name)
            stack.extend(b.children)
        merged = ff7.merge_bones(arm, meshes, sorted(inside - {keep}), keep)
        out.append("%s <- %d bones" % (keep, len(merged)))
    return out


def face_bones(arm, keep):
    out = [b.name for b in arm.data.bones if FACE_EXTRA.match(b.name)]
    for root in FACE_ROOTS:
        bone = arm.data.bones.get(root)
        if bone is None:
            continue
        stack = [bone]
        while stack:
            b = stack.pop()
            if b.name in keep:
                continue
            out.append(b.name)
            stack.extend(b.children)
    return out


def resolve_slots(arm, roe):
    slots, missing = roe.resolve_roe_slots(arm)
    bones = arm.data.bones
    for side in ("left", "right"):
        eye = ff7.pick(bones, *EYES[side])
        if eye:
            slots["%s_eye_bone" % side] = eye
        chest = next((keep for keep, _merge in BREASTS[side] if keep in bones), "")
        if chest:
            slots["%s_chest_bone" % side] = chest
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


def prepare(arm, meshes, roe, hair_mode="auto", keep_weapon=False):
    """Renames, weapons / pets, face / bust merges, hair chains, skinless helpers off, centimetres -> metres."""
    height_cm = max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box)
    stats = {"height_cm": round(height_cm, 2)}
    stats["weapons_left_out"] = [] if keep_weapon else drop_weapons(arm, meshes)
    stats["renamed_biped"] = rename_biped(arm, meshes)
    stats["merged_pets"] = merge_pets(arm, meshes)
    stats["renamed_cloth"] = rename_cloth_bones(arm, meshes)
    stats["dropped_far_bones"] = len(sb.drop_far_sockets(arm, meshes))
    eyes = {n for pair in EYES.values() for n in pair}
    head = "Bip001 Head"
    stats["merged_face_bones"] = len(ff7.merge_bones(arm, meshes, face_bones(arm, eyes), head))
    stats["hair_chains"] = []
    if hair_mode != "off":                        # hair skinned to the body only (Yustiel): chains for physics
        for m in meshes:
            hairy = any(s.material and "hair" in s.material.name.lower() for s in m.material_slots)
            if hairy and hair_chains.needs_chains(arm, m):
                stats["hair_chains"].append(dict(hair_chains.rig(arm, m, head), mesh=m.name))
    bust = []
    for side in ("left", "right"):
        for keep, merge in BREASTS[side]:
            if keep in arm.data.bones:
                bust += ff7.merge_bones(arm, meshes, list(merge), keep)
                break
    stats["merged_bust"] = bust
    slots, missing = resolve_slots(arm, roe)
    weighted = sb.weighted_bones(meshes)
    keep = {v for v in slots.values() if v}
    off = [b.name for b in arm.data.bones if b.use_deform and b.name not in weighted and b.name not in keep]
    for name in off:
        arm.data.bones[name].use_deform = False        # only decides who may inherit weight
    stats["undeformed_skinless"] = len(off)
    front = sum(((arm.matrix_world.to_3x3() @ (arm.data.bones[slots["%s_toe_bone" % s]].head_local
                                              - arm.data.bones[slots["%s_foot_bone" % s]].head_local)).normalized()
                 for s in ("left", "right") if slots["%s_toe_bone" % s] and slots["%s_foot_bone" % s]), Vector())
    front.z = 0.0                                      # the toes also point down
    if front.length > 1e-6 and front.normalized().y > -0.9:
        raise RuntimeError("the model does not face -Y (toes point %s)" % tuple(round(x, 2) for x in front))
    s = 0.01 if height_cm > 20.0 else 1.0
    head = arm.data.bones.get(slots["head_bone"])
    head_z = (arm.matrix_world @ head.head_local).z if head is not None else 0.0
    if s == 0.01 and head_z > 200.0:                 # a giant (Siel in her cut-scene): human size for MMD motions
        stats["rescaled"] = "head at %.2f m -> %.2f m (x%.3f)" % (head_z / 100.0, HEAD_HEIGHT_CM / 100.0,
                                                                  HEAD_HEIGHT_CM / head_z)
        s *= HEAD_HEIGHT_CM / head_z
    arm.scale = tuple(x * s for x in arm.scale)
    bpy.context.view_layer.update()
    return slots, missing, stats


def head_psk(blend_path, given=""):
    """The head part's PSK: --head-psk, else spec.json beside the .blend (part 'Head', else the first part whose
    skeleton has the face rig)."""
    if given:
        return given
    spec_path = os.path.join(os.path.dirname(blend_path), "spec.json")
    if not os.path.isfile(spec_path):
        return ""
    parts = json.load(open(spec_path, encoding="utf-8")).get("parts", [])
    parts = sorted(parts, key=lambda p: p.get("name") != "Head")
    for part in parts:
        psk = part.get("psk", "")
        if os.path.isfile(psk) and any(n == facs_morphs.FACE_ROOT for n, _p, _q, _t in
                                       facs_morphs.read_psk_skeleton(psk)):
            return psk
    return ""


def add_face_morphs(root, meshes, game_faces=""):
    """The MMD expression set mixed from the ARKit keys (Stellar Blade's recipes), then the game's own cutscene
    faces (add_game_faces), then the raw ARKit keys under 'other'.  Returns (made, skipped, game faces)."""
    keyed = sorted((m for m in meshes if m.data.shape_keys and len(m.data.shape_keys.key_blocks) > 1),
                   key=lambda m: -len(m.data.shape_keys.key_blocks))
    if not keyed:
        return [], [], []
    head = keyed[0]
    keys = head.data.shape_keys.key_blocks
    recipes = sb.RECIPES
    sb.RECIPES = [(n, e, c, {k: v for k, v in mix.items() if k in keys or k != "TeethLowerDown"})
                  for n, e, c, mix in recipes]
    try:
        made, skipped = sb.add_arkit_morphs(root, head)
    finally:
        sb.RECIPES = recipes
    game = game_face_mixes(game_faces)
    faces = add_game_faces(root, head, game, len(made))
    # every other mesh the face bones move (hair and headbands skinned to the forehead / temples: Leda's GF_Hair_402,
    # Hadar's headband) gets the same mixes from its own ARKit keys - same names, so the PMX morph moves them too
    # (a key a mesh lacks = the pose did not move it); the head's registration and order stay
    mixes = [(n, mix) for n, _e, _c, mix in recipes if n in made] + [(n, mix) for n, mix in game if n in faces]
    for mesh in keyed[1:]:
        mix_keys(mesh, mixes)
    return made, skipped, faces


def mix_keys(mesh, mixes):
    """Shape keys mixed from a mesh's own ARKit keys; the keys it lacks count as 0.  Returns the names made."""
    keys = mesh.data.shape_keys.key_blocks
    for kb in keys:
        kb.value = 0.0
    made = []
    for name, mix in mixes:
        mix = {k: v for k, v in mix.items() if k in keys and abs(v) > 1e-4}
        if not mix or name in keys:
            continue
        for k, v in mix.items():
            keys[k].value = v
        new = mesh.shape_key_add(name=name, from_mix=True)
        new.value = 0.0
        for k in mix:
            keys[k].value = 0.0
        made.append(name)
    return made


def game_face_mixes(path):
    """The game's cutscene expressions (GF_CineFacial_PoseAsset_01: Face_Angry, Face_Smile, Face_Surprise,
    Face_Sad, Face_serious, Mouth_A / E / W / EA / O / eop) are weights of the same ARKit curves, made by the
    game's animators: [(name, {curve: weight})].  Pose_9 .. Pose_19 (copies of Face_serious) are left out."""
    if not path or not os.path.isfile(path):
        return []
    doc = json.load(open(path, encoding="utf-8-sig"))
    pc = next(o for o in doc if o.get("Type") == "PoseAsset")["Properties"]["PoseContainer"]
    curves = [c["Name"]["DisplayName"] for c in pc.get("Curves", [])]
    return [(p["DisplayName"], dict(zip(curves, pose.get("CurveData", []))))
            for p, pose in zip(pc["PoseNames"], pc["Poses"]) if not re.match(r"^Pose_\d+$", p["DisplayName"])]


def add_game_faces(root, head, mixes, after):
    """Each game expression becomes one more vertex morph mixed from the ARKit keys, panel 'other', listed right after
    the MMD set; curves without a key (Cage_Face_jawOpen) are skipped."""
    made = mix_keys(head, mixes)
    mmd = root.mmd_root
    have = {m.name for m in mmd.vertex_morphs}
    for name in made:
        if name not in have:
            item = mmd.vertex_morphs.add()
            item.name, item.name_e, item.category = name, name, "OTHER"
    for i, name in enumerate(made):
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(name), after + i)
    if made:
        from mmd_tools.operators.display_item import DisplayItemQuickSetup
        mmd.display_item_frames["表情"].data.clear()
        DisplayItemQuickSetup.load_facial_items(mmd)
    return made


def swap_colour_maps(meshes, folder):
    """--albedo-dir: every image node whose file has a namesake in `folder` (AI-upscaled copies of the .blend's
    textures\\*_albedo.png, E:\\tools\\upscale\\esrgan.py) reads that file instead.  Returns the files swapped."""
    done = set()
    for m in meshes:
        for slot in m.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            for n in mat.node_tree.nodes:
                if n.type != "TEX_IMAGE" or n.image is None:
                    continue
                src = os.path.join(folder, os.path.basename(bpy.path.abspath(n.image.filepath)))
                if os.path.isfile(src):
                    img = bpy.data.images.load(src, check_existing=True)
                    img.colorspace_settings.name = n.image.colorspace_settings.name
                    n.image = img
                    done.add(os.path.basename(src))
    return sorted(done)


def material_maps(meshes, blend_path):
    """Before the conversion: each material's albedo / normal / ORM images (build_blend.py's nodes) and its kind
    (materials.json beside the .blend)."""
    kinds = {}
    path = os.path.join(os.path.dirname(blend_path), "materials.json")
    if os.path.isfile(path):
        kinds = {k: v.get("kind") for k, v in json.load(open(path, encoding="utf-8")).items() if isinstance(v, dict)}
    out = {}
    for m in meshes:
        for slot in m.material_slots:
            mat = slot.material
            if mat is None or mat.name in out or not mat.use_nodes:
                continue
            maps = {"kind": kinds.get(mat.name) or kinds.get(re.sub(r"\.\d+$", "", mat.name)) or ""}
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image is not None:
                    low = n.image.name.lower()
                    if "_orm" in low:
                        maps["orm"] = n.image
                    elif re.search(r"_n\.(png|tga|jpg)$", low):
                        maps["normal"] = n.image
            bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            link = next((l for l in mat.node_tree.links if bsdf and l.to_socket == bsdf.inputs["Base Color"]), None)
            if link is not None and link.from_node.type == "TEX_IMAGE":
                maps["albedo"] = link.from_node.image
            out[mat.name] = maps
    return out


def _pixels(image, w, h):
    """RGBA floats (h, w, 4) of an image at w x h, as stored (sRGB colour maps stay sRGB)."""
    src = image
    if tuple(image.size) != (w, h):
        src = image.copy()
        src.scale(w, h)
    a = np.empty(w * h * 4, np.float32)
    src.pixels.foreach_get(a)
    if src is not image:
        bpy.data.images.remove(src)
    return a.reshape(h, w, 4)


def bake_pmx_textures(maps, tex_dir, relief=RELIEF, power=RELIEF_POWER):
    """MMD reads one colour map and no normal / AO map, so what the game draws with them goes into the colour:
    garments (kinds armor / phantom) x the normal map's relief - 1 - relief * (1 - nz^power), nz the normal's
    height part, which darkens the slopes of embroidery, ornaments and folds (Yustiel's dress is one flat colour,
    its whole pattern is in the normal map) - and garments, skin and faces x the rest of the ORM map's ambient
    occlusion (BAKED_AO_KEEP), so the PMX colour carries the AO exactly once.  The colour maps keep the game's
    resolution (AION2's own maximum: NPC outfits 1024, the shared body / faces 2048, measured in the packages'
    texture headers).  Writes <material>_pmx.png and makes it the PMX texture.  Returns {material: what was
    multiplied in}."""
    from mmd_tools.core.material import FnMaterial
    report = {}
    os.makedirs(tex_dir, exist_ok=True)
    for name, m in sorted(maps.items()):
        mat, albedo = bpy.data.materials.get(name), m.get("albedo")
        if mat is None or albedo is None or mat.mmd_material.alpha <= 0.0:
            continue
        use_relief = relief > 0.0 and m.get("normal") is not None and m["kind"] in GARMENT_KINDS
        use_ao = m.get("orm") is not None and m["kind"] in BAKED_AO_KEEP
        if not (use_relief or use_ao):
            continue
        sizes = [tuple(albedo.size)] + [tuple(m[k].size) for k, on in (("normal", use_relief), ("orm", use_ao)) if on]
        w, h = max(s[0] for s in sizes), max(s[1] for s in sizes)
        factor = np.ones((h, w), np.float32)
        if use_relief:
            n = _pixels(m["normal"], w, h)
            nx, ny = n[..., 0] * 2.0 - 1.0, n[..., 1] * 2.0 - 1.0
            factor *= 1.0 - relief * (1.0 - np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0)) ** power)
        ao_note = ""
        if use_ao:                                    # the part of the AO the colour map does not have yet
            ao = _pixels(m["orm"], w, h)[..., 0]
            if float(np.median(ao)) < AO_MIN_MEDIAN:
                # not an AO map: an unused channel (Snotra's metal face ornament: median 0, the ornament went black)
                use_ao, ao_note = False, " (ao channel unused, median %.2f)" % float(np.median(ao))
            else:
                keep = BAKED_AO_KEEP[m["kind"]]
                factor *= np.clip(ao / np.maximum(keep + (1.0 - keep) * ao, 1e-3), 0.0, 1.0)
        if float(factor.min()) > 0.995:
            continue                                  # constant AO 1, no relief: the colour map as it is
        rgba = _pixels(albedo, w, h)
        rgba[..., :3] *= factor[..., None]
        path = os.path.join(tex_dir, re.sub(r"[^\w.-]", "_", name) + "_pmx.png")
        out = bpy.data.images.new(name + "_pmx", w, h, alpha=True)
        out.pixels.foreach_set(rgba.ravel())
        out.filepath_raw, out.file_format = path, "PNG"
        out.save()
        FnMaterial(mat).create_texture(path)
        report[name] = "%dx%d%s%s (mean x%.2f)%s" % (w, h, " relief" if use_relief else "", " ao" if use_ao else "",
                                                     float(factor.mean()), ao_note)
    return report


def fit_colliders(pmx_path, maps, meshes):
    """The body colliders refitted inside the legs / body as they look (scripts/mmd_physics/cloth_collision_pmx.py,
    plain Python, rewrites the PMX's rigid bodies only): skin and face materials, plus the materials of the part
    named *_Pants (the leg's surface where leggings cover it) and *_Boots for the shins.  Convert_to_MMD5 measures
    its colliders on the dressed mesh and mmd_cloth_physics leaves cloth that starts inside a collider free of that
    collider class: Hadar's open skirt front lay on thighs it never hit, and once she stood wide the thighs went
    through both panels.  With the fit (thigh halves) it stays in front.  A model whose skin shares one material with
    the clothes (Siel) is left as it is.  Returns the tool's summary lines or a reason."""
    skin = {n for n, m in maps.items() if m["kind"] in ("skin", "face") or re.search(r"BaseBody|_Skin\b", n)}
    legs, boots = set(), set()
    for m in meshes:                              # the leggings' own material only: a Pants part may carry a piece
        names = {s.material.name for s in m.material_slots if s.material}      # of the dress (Yustiel, Urd's robe)
        if m.name.endswith("_Pants"):
            legs |= {n for n in names if re.search(r"pants", n, re.IGNORECASE)}
        elif m.name.endswith("_Boots"):
            boots |= {n for n in names if re.search(r"boots", n, re.IGNORECASE)}
    skin_list = sorted(skin | (legs - boots))
    if not skin:
        return ["skipped: no skin material of its own"]
    tool = os.path.join(REPO, "scripts", "mmd_physics", "cloth_collision_pmx.py")
    tmp = pmx_path + ".fit.pmx"
    cmd = [sys.executable, tool, pmx_path, tmp, "--skin", ",".join(skin_list), "--thigh-halves"]
    if boots:
        cmd += ["--shins-from", ",".join(sorted(boots))]
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.isfile(tmp):
        return ["failed (%d): %s" % (r.returncode, (r.stderr or r.stdout)[-600:])]
    os.replace(tmp, pmx_path)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return ["skin: " + ", ".join(skin_list), "shins: " + ", ".join(sorted(boots))] + \
        [l for l in lines if "dynamic" in l or "thinned" in l or "colliders" in l][:12]


def limb_helpers_never_cloth(roe):
    """The AION2 muscle helpers join the limb-helper names of the ROE worker and of mmd_cloth_physics."""
    extra = "|" + MUSCLE_HELPERS
    if MUSCLE_HELPERS not in roe.LIMB_HELPER_NAME.pattern:
        roe.LIMB_HELPER_NAME = re.compile(roe.LIMB_HELPER_NAME.pattern + extra, re.IGNORECASE)
    try:
        import mmd_cloth_physics.analyze as cloth_analyze
        if MUSCLE_HELPERS not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + extra, re.IGNORECASE)
    except ImportError:
        pass


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--facs", default=DEFAULT_FACS,
                    help="the game's ARKit pose asset (face_data.py) for the expressions; 'none' = no expressions")
    ap.add_argument("--head-psk", default="", help="the head part's PSK (default: from spec.json beside the .blend)")
    ap.add_argument("--game-faces", default=DEFAULT_GAME_FACES,
                    help="the game's cutscene expressions as ARKit mixes (face_data.py); 'none' = leave them out")
    ap.add_argument("--relief", type=float, default=RELIEF,
                    help="garments: how much the normal map's slopes darken the colour map (0 = plain colour)")
    ap.add_argument("--no-ao", action="store_true", help="leave the ORM maps' ambient occlusion out of the colours")
    ap.add_argument("--hair-chains", choices=("auto", "off"), default="auto",
                    help="auto: hair skinned only to Biped bones (no hair bones, Yustiel) gets generated chains")
    ap.add_argument("--albedo-dir", default="",
                    help="colour maps to use instead of the .blend's (same file names), e.g. AI-upscaled copies")
    ap.add_argument("--keep-weapon", action="store_true",
                    help="keep the skin of weapon bones hanging off the root (Siel's orb)")
    ap.add_argument("--legs-inside", choices=("leave", "collide"), default=LEGS_INSIDE,
                    help="mmd_cloth_physics' legs_inside: cloth that starts inside a leg collider hits the legs anyway")
    ap.add_argument("--no-collider-fit", action="store_true",
                    help="keep Convert_to_MMD5's body colliders (no cloth_collision_pmx.py refit after the write)")
    args = ap.parse_args(argv)
    clip, opaque = source_alpha_modes()            # before anything touches the materials

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath}
    for obj in list(scene.objects):
        if obj.type in ("CAMERA", "LIGHT") or (obj.type == "MESH" and obj.hide_render):
            bpy.data.objects.remove(obj, do_unlink=True)
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]

    # a generated folder: the PMX, its textures and the converted scene are replaced; whatever else lies beside
    # them (preview videos, sheets) stays, and a folder another program has open (Explorer, a player) is no error
    for old in (path, os.path.join(out_dir, name + "_converted.blend")):
        if os.path.isfile(old):
            os.remove(old)
    shutil.rmtree(os.path.join(out_dir, "textures"), ignore_errors=True)
    if args.albedo_dir:
        report["albedo_dir"] = {"folder": args.albedo_dir, "swapped": swap_colour_maps(meshes, args.albedo_dir)}
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))
    maps = material_maps(meshes, bpy.data.filepath)     # before the conversion rebuilds the node trees
    if args.no_ao:
        for m in maps.values():
            m.pop("orm", None)
    if args.facs.lower() == "none":
        report["facs"] = "off (--facs none)"
    elif facs_morphs.FACE_ROOT not in arm.data.bones:
        report["facs"] = "no %s in the rig" % facs_morphs.FACE_ROOT
    else:                                          # while the face bones still exist
        psk = head_psk(bpy.data.filepath, args.head_psk)
        if not os.path.isfile(args.facs):
            report["facs"] = "pose asset missing: %s (run face_data.py)" % args.facs
        elif not psk:
            report["facs"] = "no head PSK with the face rig (spec.json / --head-psk)"
        else:
            report["facs"] = facs_morphs.build_shape_keys(arm, meshes, psk, args.facs)
            report["facs"]["pose_asset"] = args.facs
    slots, missing_optional, stats = prepare(arm, meshes, roe, args.hair_chains, args.keep_weapon)
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
    limb_helpers_never_cloth(roe)
    helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
    report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
    stash = ff7.face_morphs.stash(meshes)          # the pose bakes below skip meshes with shape keys
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    # collider_fixes: chains found by shape (sleeves under the forearm) stop the body colliders' measurement,
    # and bodies starting inside a collider stop colliding with it
    import mmd_cloth_physics.api as cloth_api
    cloth_setup = cloth_api.setup
    if args.legs_inside != "leave":                # the worker calls api.setup without it: hand the option in
        def setup_with_legs(*a, **kw):
            kw.setdefault("legs_inside", args.legs_inside)
            return cloth_setup(*a, **kw)
        cloth_api.setup = setup_with_legs
    try:
        root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before,
                                            collider_fixes=True)
    finally:
        cloth_api.setup = cloth_setup
    report["legs_inside"] = args.legs_inside
    report.update(conv)
    if stash:
        report["face_keys_restored"] = ff7.face_morphs.restore(meshes)
    report["stray_recipients"] = sorted((sb.weighted_bones(meshes) - weighted_before) & names_before)
    slot_names = {v for v in slots.values() if v}
    report["retired_helpers"] = sorted(weighted_before - sb.weighted_bones(meshes) - slot_names)
    report["anchored_hub_roots"] = sb.anchor_hub_roots(arm)
    report["anchored_skin_helpers"] = sb.anchor_skin_helpers(arm, meshes)
    sb.BUST["bones"] = tuple((mmd, slots["%s_chest_bone" % side])
                             for mmd, side in (("左胸", "left"), ("右胸", "right")) if slots["%s_chest_bone" % side])
    report["bust_physics"] = sb.add_breast_physics(root, arm, meshes)
    report["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    report["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = sb.fix_pmx_materials(meshes, baked, os.path.join(out_dir, "textures"))
    report["pmx_textures"] = bake_pmx_textures(maps, os.path.join(out_dir, "textures"), args.relief)
    report["vertex_morphs"], report["morphs_skipped"], report["game_faces"] = add_face_morphs(
        root, meshes, "" if args.game_faces.lower() == "none" else args.game_faces)

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or "Converted from AION2 (NCSOFT) by ripper_tpose (scripts/aion2). Personal use only."
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
    # MMD multiplies texture alpha in: opaque materials' textures -> 1, clipped ones cut where the game cuts
    report["texture_alpha"] = fix_texture_alpha(path, clip, opaque)
    if not args.no_collider_fit:                   # after the write: the tool edits the PMX's rigid bodies
        report["collider_fit"] = fit_colliders(path, maps, meshes)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bytes"] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    with open(os.path.join(out_dir, name + "_report.json"), "w", encoding="utf-8") as fh:   # the gallery reads it
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    print("AION2_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
