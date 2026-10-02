"""Vindictus XPS -> MMD PMX with expressions, bust physics and hair physics (Blender 3.6, background).

    blender -b --python export_pmx.py -- --xps <model.xps> --dna <face.dna> --out <dir>
            [--name Fiona_BaseBody] [--model-name Fiona] [--no-physics] [--no-morphs]
    blender -b --python export_pmx.py -- --blend <build_blend.py output .blend> --dna <face.dna> --out <dir>
            [--max-texture 4096] [--ao 1.0] [--keep-xps] ...

``--blend`` is the full-resolution route: the colour of every material is baked at the size of the
material's own maps (outfits 4096, Blender2XPS stops at 2048) with the ARM map's ambient occlusion
multiplied in - a PMX material has one colour map and no normal / roughness / AO input, as ROE's HQ
PMX (albedo x tint x AO) - and Masked alpha baked as a 0 / 1 cut-out, then written as an intermediate
XPS by Blender2XPS and converted as below (see xps_from_blend for what the plain XPS route got wrong).

Two body rigs come in (RIGS): Fiona_BaseBody's 3ds Max Biped body and the UE5 body of the outfits
(PCF_*) and the default set; the slots, the bust bones and the body-bone pattern follow the rig.

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
   On the UE body the template sits on ``breast_physics_01`` / ``_02``; the skin hangs on 02 and the
   soft-tissue bones under it (1.0 summed at the centre), which all swing with 02.  Skirts hang
   from 下半身 and their chains are joined into one ring (see merge_garments).
4. PMX at scale 12.5 with textures, the ROE grant-order check, the converted .blend and a
   JSON report next to it.
"""
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import sys
from collections import defaultdict

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

# Convert to MMD 5 identifies roles by topology + geometry; on a Vindictus XPS (MetaHuman face, names
# mapped by Blender2XPS) a few come out wrong - see the tutorial 6.10 - and the fix depends on the body:
# - "biped": Fiona_BaseBody, the old 3ds Max Biped body (Bip001_*);
# - "ue": the outfits (PCF_*) and the default set, the UE5 body.  Its pelvis ("root hips" after
#   Blender2XPS) carries the hip skin.  Identified as センター (the automatic result) the conversion drops
#   those weights - センター and 下半身 both end with none and the hips stop following 下半身 - so it is
#   made 下半身 and the plugin adds a weightless センター (PCF_005: 1207 weight on 3235 verts moved).
# ``bust``: (static base, swinging bone) per side.  The UE body's breast is breast_l -> breast_physics_01
# -> 02 -> 03 -> ... plus a fan of soft-tissue bones under 02 and 03; the skin hangs on 02 and everything
# below it (summed per vertex: 1.0 at the centre), so swinging 02 moves the whole breast.
# ``body_regex``: bones mmd_cloth_physics must not take for cloth - FACIAL_* is face skin (the hairline
# joints are named *Hair*), breast_* the bust above, *toe_## the UE toes (they came out as "ribbons").
RIGS = {
    "biped": {
        "slots": {"center_bone": "", "lower_body_bone": "Bip001_Pelvis", "head_bone": "head neck upper",
                  "left_eye_bone": "head eyeball left", "right_eye_bone": "head eyeball right"},
        "bust": (("Bip001_L_bust_1", "Bip001_L_bust_2"), ("Bip001_R_bust_1", "Bip001_R_bust_2")),
        "body_regex": r"^(Bip0\d\d|FACIAL_)",
    },
    "ue": {
        "slots": {"center_bone": "", "lower_body_bone": "root hips", "head_bone": "head neck upper",
                  "left_eye_bone": "head eyeball left", "right_eye_bone": "head eyeball right"},
        "bust": (("breast_physics_01_l", "breast_physics_02_l"), ("breast_physics_01_r", "breast_physics_02_r")),
        "body_regex": r"^(FACIAL_|breast_|[a-z]+toe_\d)",
        "into_parent": r"^unused_calf_twist",       # see merge_into_parent
    },
}
SLOT_FIX = RIGS["biped"]["slots"]
# mmd_cloth_physics groups chains by a name stem whose side tokens are upper case (Skirt_L_01); the UE
# outfits name them Outfit005_skirt_a_01_l, so every skirt chain came out a garment of its own.  Chains
# whose root matches one of these (group 1 = the garment) and that share an anchor are joined again.
GARMENT_MERGE = (r"^(.*_skirt)_[a-z]_\d+_[lr]$",)
# MMD skirts hang from 下半身; the UE outfits hang theirs from spine_02 (上半身2), so a bow tipped the
# whole skirt with the chest.  Roots matching this are re-parented to 下半身 before the physics.
SKIRT_ROOT = r"_skirt_root$"
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
    "boost_to": 0.75, "limit_deg": 10.0, "spring": 450.0, "mass": 1.0, "lin_damp": 0.5, "ang_damp": 0.5,
    "friction": 0.5, "group": 15, "radius": (0.03, 0.06), "base_radius": 0.024, "centre_weight": 0.3,
}
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


# -- 0. --blend: full-size colour maps through an intermediate XPS -------------------------------
def principled(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    return next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def multiply_ao(material, strength=1.0):
    """Base Color x the ambient occlusion (R) of the ARM / ORM map that feeds Roughness (``strength`` 1 =
    fully, as ROE's HQ PMX).  build_blend.py wires G (roughness) and B (metallic) only - Principled has no
    AO input - so the .blend never shows it."""
    tree = material.node_tree
    bsdf = principled(material)
    if bsdf is None or strength <= 0.0 or not bsdf.inputs["Roughness"].is_linked:
        return False
    node = bsdf.inputs["Roughness"].links[0].from_node
    while node.type == "MAP_RANGE" and node.inputs["Value"].is_linked:
        node = node.inputs["Value"].links[0].from_node
    if node.type != "SEPRGB":
        return False
    base = bsdf.inputs["Base Color"]
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = min(strength, 1.0)
    if base.is_linked:
        tree.links.new(base.links[0].from_socket, mix.inputs["Color1"])
    else:
        mix.inputs["Color1"].default_value = base.default_value
    tree.links.new(node.outputs["R"], mix.inputs["Color2"])
    tree.links.new(mix.outputs["Color"], base)
    return True


def cutout_alpha(material):
    """MMD blends with whatever alpha the texture has.  A Masked (CLIP) material's alpha is a cut-out -
    opaque from the threshold up, as in the game and the .blend - but its in-between values came through
    as real transparency: 74% of PCF_005's skirt texels lie between 1/3 and 0.99 and the skirt went
    see-through grey.  CLIP alpha is baked as 0 / 1 at the material's threshold, OPAQUE as 1; hair, lashes
    and the eye shells (HASHED / BLEND) keep theirs."""
    bsdf = principled(material)
    if bsdf is None:
        return ""
    tree, alpha = material.node_tree, bsdf.inputs["Alpha"]
    if material.blend_method == "OPAQUE":
        for link in list(alpha.links):
            tree.links.remove(link)
        alpha.default_value = 1.0
        return "opaque"
    if material.blend_method == "CLIP" and alpha.is_linked:
        cut = tree.nodes.new("ShaderNodeMath")
        cut.operation = "GREATER_THAN"
        cut.inputs[1].default_value = material.alpha_threshold
        tree.links.new(alpha.links[0].from_socket, cut.inputs[0])
        tree.links.new(cut.outputs["Value"], alpha)
        return "cutout"
    return ""


def split_shared_materials():
    """Blender2XPS bakes a material once per object but names the result after the material, so the
    second object's bake overwrites the first one's (PCF_005: MI_PCF_Lower01 is on the Foot and the
    Onepiece - the PMX legs kept 4.7% of their texels and vanished).  Every further object gets its own
    copy, <material>_<object>."""
    users = defaultdict(list)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.visible_get():
            for slot in obj.material_slots:
                if slot.material is not None and obj not in users[slot.material.name]:
                    users[slot.material.name].append(obj)
    copies = []
    for name, objs in users.items():
        for obj in objs[1:]:
            copy = bpy.data.materials[name].copy()
            copy.name = "%s_%s" % (name, obj.name.rsplit("_", 1)[-1])
            for slot in obj.material_slots:
                if slot.material is not None and slot.material.name == name:
                    slot.material = copy
            copies.append(copy.name)
    return copies


def xps_from_blend(blend, xps, max_size, ao_strength=1.0):
    """A build_blend.py .blend -> an XPS whose colour maps are baked at the size of each material's own
    maps (up to ``max_size``) with AO multiplied in.  Every material is baked (bake mode ALL): in AUTO
    Blender2XPS keeps a texture as it is when only "mild" nodes sit in front of it - hue / saturation /
    value and tints within 0.1 of white - and so dropped the face's and the hands' Basecolor Brightness
    (0.93, 0.90) and tint while the body skin, tinted a little more, was baked: three skin tones.  Its
    2048 bake cap is lifted for this run.  Settings otherwise as its batch tool
    (tools/batch_export_blends.py, scale 0.01: the .blend is in centimetres)."""
    from blender2xps import export_xps
    from blender2xps import materials as b2x_materials

    bpy.ops.wm.open_mainfile(filepath=blend, load_ui=False)
    # Cycles hands out an image's colour premultiplied by its alpha unless the image's Alpha output is
    # wired into the shader.  The .blend wires it to Principled Alpha, but the bake takes Base Color alone,
    # so every colour came out multiplied by the opacity mask: PCF_005's skirt (alpha 0.4-0.6, a Masked
    # material, opaque in the game) baked at 0.49 instead of 0.78 and the PMX skirt was grey.  The game
    # packs opacity into the alpha of its colour maps - channel packed, nothing to premultiply.
    packed = [img.name for img in bpy.data.images if img.users and img.alpha_mode in ("STRAIGHT", "PREMUL")]
    for name in packed:
        bpy.data.images[name].alpha_mode = "CHANNEL_PACKED"
    shared = split_shared_materials()
    used = sorted({s.material.name for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()
                   for s in o.material_slots if s.material is not None})
    ao = [n for n in used if multiply_ao(bpy.data.materials[n], ao_strength)]
    alpha = {n: kind for n in used for kind in (cutout_alpha(bpy.data.materials[n]),) if kind}
    log("AO x%.2f into %d materials (%s); per-object copies %s; alpha %s"
        % (ao_strength, len(ao), ", ".join(ao), shared, alpha))
    bake_size_for = b2x_materials.bake_size_for
    b2x_materials.bake_size_for = lambda mat, requested=0, cap=2048: bake_size_for(mat, requested, max_size)
    try:
        settings = export_xps.Settings(filepath=xps, fmt="AUTO", scope="VISIBLE", scale=0.01, bake_mode="ALL",
                                       bake_size=0, hide_facial_bones=False, bone_naming="XPS", max_weights=4,
                                       auto_facing=True)
        result = export_xps.export_model(bpy.context, settings)
    finally:
        b2x_materials.bake_size_for = bake_size_for
    if result.errors:
        raise RuntimeError("Blender2XPS: " + "; ".join(result.errors))
    log("intermediate XPS %s: %d bones, %d meshes" % (xps, result.bone_count, result.mesh_count))
    return {"blend": blend, "ao_materials": ao, "ao_strength": ao_strength, "material_copies": shared,
            "alpha": alpha, "channel_packed_images": len(packed), "max_texture": max_size,
            "warnings": result.warnings}


def relink_textures(out_dir, work):
    """Point the converted .blend at the PMX's texture copies (<out>/textures) before the intermediate
    XPS folder goes; images only the XPS used (normal maps ...) are dropped."""
    tex = os.path.join(out_dir, "textures")
    work = os.path.normcase(os.path.abspath(work))
    relinked = dropped = 0
    for image in list(bpy.data.images):
        path = os.path.abspath(bpy.path.abspath(image.filepath)) if image.filepath else ""
        if not os.path.normcase(path).startswith(work):
            continue
        copy = os.path.join(tex, os.path.basename(path))
        if os.path.isfile(copy):
            image.filepath = copy
            relinked += 1
        else:
            bpy.data.images.remove(image)
            dropped += 1
    return {"relinked": relinked, "dropped": dropped}


# -- 1. import + convert -----------------------------------------------------------------------
def rig_kind(arm):
    return "biped" if "Bip001_Pelvis" in arm.data.bones else "ue"


def merge_into_parent(arm, pattern):
    """Weights of the bones matching ``pattern`` move to their first ancestor that does not match.
    Convert to MMD 5 hands a UE calf twist bone's weights to the nearest MMD bone.  calf_twist_01 sits a
    third of the way up from the ankle, so the lower half of the shin went to 足首D and folded with the
    foot: in a dance on high heels PCF_005's shins broke halfway down (XPS calf_twist_01 378 -> 足首D).
    The twist bones are children of the calf; their skin belongs to ひざ."""
    rx = re.compile(pattern)
    bones = arm.data.bones
    moved = defaultdict(float)
    for mesh in (o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == arm):
        for group in [g for g in mesh.vertex_groups if rx.search(g.name) and g.name in bones]:
            target = bones[group.name].parent
            while target is not None and rx.search(target.name):
                target = target.parent
            if target is None:
                continue
            dest = mesh.vertex_groups.get(target.name) or mesh.vertex_groups.new(name=target.name)
            for v in mesh.data.vertices:
                w = next((g.weight for g in v.groups if g.group == group.index), 0.0)
                if w > 0.0:
                    dest.add([v.index], w, "ADD")
                    moved["%s -> %s" % (group.name, target.name)] += w
            mesh.vertex_groups.remove(group)
    log("weights moved to the parent bone: %s" % ", ".join("%s %.0f" % kv for kv in sorted(moved.items())))
    return {k: round(v, 1) for k, v in sorted(moved.items())}


def import_and_convert(xps):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.orphans_purge(do_recursive=True)              # the source .blend of --blend
    bpy.ops.xps_tools.import_model(filepath=xps)          # XNALaraMesh defaults, as in the GUI
    arm = live_armature()
    kind = rig_kind(arm)
    log("body rig: %s" % kind)
    if RIGS[kind].get("into_parent"):
        merge_into_parent(arm, RIGS[kind]["into_parent"])
    arm.scale = (1.0, 1.0, 1.0)                            # the 214-unit trap (tutorial 6.10 step 2)
    activate(arm)
    bpy.ops.object.auto_identify_skeleton()
    scene = bpy.context.scene
    for prop, bone in RIGS[kind]["slots"].items():
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
    return root, arm, kind


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
def swing_set(bones, name):
    """The swinging bone and everything below it (the UE breast's soft-tissue bones move with it)."""
    out, stack = set(), [bones[name]]
    while stack:
        bone = stack.pop()
        out.add(bone.name)
        stack.extend(bone.children)
    return out


def swing_weights(mesh, names):
    """(vertex, [(group index, weight)]) of the vertices that ``names`` move."""
    idx = {g.index for g in mesh.vertex_groups if g.name in names}
    if not idx:
        return
    for v in mesh.data.vertices:
        own = [(g.group, g.weight) for g in v.groups if g.group in idx and g.weight > 0.0]
        if own:
            yield v, own


def boost_bust_weights(meshes, swing_sets, target):
    """Scale each breast's swing weights (per vertex, summed over the swinging bone and its children) so
    their peak is ``target``; the added weight comes out of the vertex's other bones in proportion, so
    every vertex still sums to what it did.  Fiona_BaseBody's bust_2 peaks at 0.24 and is boosted; the UE
    body's breast_physics_02 already reaches 1.0 and is left alone."""
    every = set().union(*swing_sets) if swing_sets else set()
    peak = 0.0
    for names in swing_sets:
        for mesh in meshes:
            for _v, own in swing_weights(mesh, names):
                peak = max(peak, sum(w for _g, w in own))
    if peak <= 0.0 or peak >= target:
        return {"peak_before": round(peak, 3), "factor": 1.0, "vertices": 0}
    factor = target / peak
    # The gain grows with the weight itself: the peak gets the full factor, the rim (30% of the peak)
    # only ~1.2x.  A flat factor steepened the rim 3x and the upper breast creased when it swung.
    gain = lambda w: 1.0 + (factor - 1.0) * (w / peak) ** 2  # noqa: E731
    changed = 0
    for names in swing_sets:
        for mesh in meshes:
            groups = {g.index: g for g in mesh.vertex_groups}
            skip = {g.index for g in mesh.vertex_groups if g.name in every}
            for v, own in list(swing_weights(mesh, names)):
                total = sum(w for _g, w in own)
                others = [(g.group, g.weight) for g in v.groups if g.group not in skip and g.weight > 0.0]
                pool = sum(w for _g, w in others)
                take = min(min(total * gain(total), 1.0) - total, pool)
                if take <= 0.0:
                    continue
                for oi, ow in others:
                    groups[oi].add([v.index], ow - take * ow / pool, "REPLACE")
                for gi, w in own:
                    groups[gi].add([v.index], w + take * w / total, "REPLACE")
                changed += 1
    return {"peak_before": round(peak, 3), "factor": round(factor, 3), "vertices": changed}


def add_bust_physics(root, arm, meshes, sides):
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
    for base_name, swing_name in sides:
        base, swing = bones.get(base_name), bones.get(swing_name)
        if base is None or swing is None or swing_name in rigids:
            report.append("%s: missing or already built" % swing_name)
            continue
        moved = swing_set(bones, swing_name)
        points, weights = [], []
        for mesh in meshes:
            for v, own in swing_weights(mesh, moved):
                w = sum(x for _g, x in own)
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
        report.append("%s swings on %s: sphere r %.1f cm, %.1f cm in front of the pivot, %d verts (%d bones)"
                      % (swing_name, base_name, radius * 100, (centre - swing.head_local).length * 100, len(points),
                         len(moved)))
    return report


def hang_skirts(arm):
    """Skirt roots (SKIRT_ROOT) that hang from a chest bone move to 下半身, keeping their place."""
    bones = arm.data.bones
    names = [b.name for b in bones if re.search(SKIRT_ROOT, b.name, re.IGNORECASE) and b.parent is not None
             and b.parent.name != "下半身"]
    if not names or "下半身" not in bones:
        return []
    activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    moved = []
    for name in names:
        moved.append("%s: %s -> 下半身" % (name, edit[name].parent.name))
        edit[name].use_connect = False
        edit[name].parent = edit["下半身"]
    bpy.ops.object.mode_set(mode="OBJECT")
    log("skirt roots: " + "; ".join(moved))
    return moved


def merge_garments(arm, garments, meshes):
    """Join the garments whose chain roots match GARMENT_MERGE and share an anchor (see there): a skirt
    of separate strands has no joints between neighbouring chains and the panels swing apart; joined,
    mmd_cloth_physics classifies it again (a ring when the chains go round the anchor) and links
    neighbours row by row."""
    from mmd_cloth_physics import analyze

    unit = analyze.unit_scale(meshes)
    patterns = [re.compile(p) for p in GARMENT_MERGE]
    groups, out = defaultdict(list), []
    for garment in garments:
        first = garment.chains[0][0] if garment.chains else ""
        match = next((m for m in (p.match(first) for p in patterns) if m), None)
        if match is None:
            out.append(garment)
        else:
            groups[(match.group(1), garment.anchor)].append(garment)
    for (stem, anchor), items in sorted(groups.items()):
        if len(items) == 1:
            out.extend(items)
            continue
        merged = analyze.Garment("%s@%s" % (stem, anchor), stem, anchor)
        merged.center = items[0].center
        for item in items:
            merged.chains.extend(item.chains)
            for name in item.bones:
                if name not in merged.rows:
                    merged.rows[name] = item.rows[name]
                    merged.bones.append(name)
        merged.bones.sort(key=lambda n: merged.rows[n])
        analyze.classify(arm, merged, unit)
        merged.preset = analyze.guess_preset(merged)
        log("cloth: %d chains of %s joined into one %s (preset %s, %d lattice pairs)"
            % (len(merged.chains), stem, merged.kind, merged.preset, len(merged.pairs)))
        out.append(merged)
    return out


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


def add_physics(root, arm, meshes, roe, rig):
    out = {}
    bones = arm.data.bones
    activate(arm)
    out["body"] = "ok" if bpy.ops.object.add_body_rigids() == {"FINISHED"} else "cancelled"
    sides = [(base, swing) for base, swing in rig["bust"] if base in bones and swing in bones]
    out["bust_weights"] = boost_bust_weights(meshes, [swing_set(bones, s) for _b, s in sides], BUST["boost_to"])
    out["bust"] = add_bust_physics(root, arm, meshes, sides)
    out["skirt_roots"] = hang_skirts(arm)
    from mmd_cloth_physics import api as cloth_api

    garments = merge_garments(arm, cloth_api.analyze_model(root, rig["body_regex"], r"\bProp\d*$", True), meshes)
    hair = [g for g in garments if g.preset == "hair"]
    for garment in hair:
        garment.preset = HAIR_PRESET
    report = cloth_api.setup(root, garments=garments, log=lambda line: log("cloth: " + line))
    hair_names = {g.name for g in hair}
    out["cloth"] = {"garments": len(report["garments"]), "rigid_bodies": report["rigid_bodies"],
                    "joints": report["joints"],
                    "not_hair": [g for g in report["garments"] if g["name"] not in hair_names]}
    out["hair"] = {"garments": len(hair)}
    out["hair"]["scalp_anchored"], out["hair"]["swinging"] = anchor_scalp_hair(arm, hair)
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
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--xps")
    source.add_argument("--blend", help="a build_blend.py .blend: full-size colour maps through an intermediate XPS")
    ap.add_argument("--max-texture", type=int, default=4096, help="--blend: largest baked colour map")
    ap.add_argument("--ao", type=float, default=1.0, help="--blend: how much of the ARM ambient occlusion to multiply in")
    ap.add_argument("--keep-xps", action="store_true", help="--blend: keep the intermediate XPS in <out>/<name>/_xps")
    ap.add_argument("--dna", default="", help="face DNA from metahuman_dna.py extract (no expressions without it)")
    ap.add_argument("--out", required=True, help="the PMX goes to <out>/<name>/<name>.pmx")
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="")
    ap.add_argument("--no-physics", action="store_true")
    ap.add_argument("--no-morphs", action="store_true")
    args = ap.parse_args(argv)
    name = args.name or os.path.splitext(os.path.basename(args.xps or args.blend))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".pmx")
    for module in ("mmd_tools", "XNALaraMesh-master", "Convert_to_MMD5"):
        addon_utils.enable(module, default_set=False)
    roe = load_worker()

    report = {"name": name, "pmx": path}
    xps, work = args.xps, None
    if args.blend:
        work = os.path.join(out_dir, "_xps")
        xps = os.path.join(work, name + ".xps")
        report["hd"] = xps_from_blend(os.path.abspath(args.blend), xps, args.max_texture, args.ao)
    report["xps"] = xps
    root, arm, kind = import_and_convert(xps)
    report["rig"] = kind
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == arm]
    report["both_eyes_bone"] = roe.add_both_eyes_bone(arm)
    activate(arm)
    bpy.ops.object.create_bone_group()                     # 両目 into the add-on's display frames
    if args.dna and not args.no_morphs:
        face = metahuman_dna.DnaFace(open(args.dna, "rb").read())
        report["expressions"] = build_face_morphs(root, arm, face)
    if not args.no_physics:
        report["physics"] = add_physics(root, arm, meshes, roe, RIGS[kind])
    comment = ("Vindictus: Defying Fate (2024 pre-alpha) %s. XPS -> Convert to MMD 5 -> ripper_tpose "
               "scripts/vindictus/export_pmx.py; expressions evaluated from the face's MetaHuman DNA." % name)
    export(root, path, args.model_name or name, comment)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bones"] = len(arm.data.bones)
    report["bytes"] = os.path.getsize(path)
    if work:
        report["converted_blend_images"] = relink_textures(out_dir, work)
    converted = os.path.join(out_dir, name + "_converted.blend")
    bpy.ops.wm.save_as_mainfile(filepath=converted)
    if work:
        # saved where it lives now, so "//textures/..." resolves next to it wherever the folder is copied
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_mainfile()
        if os.path.isfile(converted + "1"):
            os.remove(converted + "1")             # the backup the second save leaves
        if not args.keep_xps:
            shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(out_dir, name + ".pmx.report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    print("VINDICTUS_PMX_REPORT=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
