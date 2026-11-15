# -*- coding: utf-8 -*-
"""Unreal Engine mannequin-style skeletons (Marvel Rivals and other UE4 / UE5 games) -> 3ds Max Biped.

  root, pelvis, spine_01 .. spine_05, neck_01 (.. neck_02), head, clavicle_l, upperarm_l, lowerarm_l, hand_l,
  thumb_01_l .. 03, index / middle / ring / pinky _01 .. _03 (+ *_metacarpal_l), thigh_l, calf_l, foot_l, ball_l,
  twist helpers upperarm_twist_01_l, lowerarm_twist_01_l, thigh_twist_01_l, calf_twist_01_l (01 .. 03)
Marvel Rivals adds corrective joints (L_Wrist_Fix_1_Jnt, L_Shoulder_Fix_*, L_Elbow_Fix_*, L_Trapezius), weapon /
socket / FX bones and *_end leaf markers.  Three to five spine bones are spread over Spine, Spine1, Spine2 (the first,
the middle and the last); the ones in between stay as helpers and are merged into their parent by the chain.
Breasts: the first pair of bones whose name says breast / bust / boob / chest_l|r becomes Bip001 L / R Pectoral.
"""
import re

NAME = "ue_mannequin"
BUST = (("左胸", "Bip001 L Pectoral"), ("右胸", "Bip001 R Pectoral"))
LIMB_HELPER = (r"|uparmtwist\d*$|foretwist\d*$|thightwist\d*$|calftwist\d*$|_fix_\d+_jnt$|trapezius$|metacarpal"
               r"|^weapon|socket|^fx_")
EYE_MATERIAL = r"(^|_)eyes?(_\d+)?(_c)?$|eyeball|(^|_)iris"
HAIR_MATERIAL = r"hair"
COMMENT = "Converted from a game mod by ripper_tpose (scripts/marvelrivals). Personal use only; credit the mod's author."
BREAST_RE = re.compile(r"(breast|bust|boob|chest)[_ ]?([lr])$|^([lr])[_ ]?(breast|bust|boob|chest)", re.IGNORECASE)


def spine_map(names):
    spines = sorted((n for n in names if re.fullmatch(r"spine_0\d", n)), key=lambda n: int(n[-2:]))
    if not spines:
        return {}
    if len(spines) == 1:
        return {spines[0]: "Bip001 Spine"}
    if len(spines) == 2:
        return {spines[0]: "Bip001 Spine", spines[1]: "Bip001 Spine2"}
    return {spines[0]: "Bip001 Spine", spines[len(spines) // 2]: "Bip001 Spine1", spines[-1]: "Bip001 Spine2"}


def build_map(names):
    m = {"root": "Bip001", "pelvis": "Bip001 Pelvis", "neck_01": "Bip001 Neck", "head": "Bip001 Head"}
    m.update(spine_map(names))
    for s, S in (("l", "L"), ("r", "R")):
        m.update({
            "clavicle_%s" % s: "Bip001 %s Clavicle" % S,
            "upperarm_%s" % s: "Bip001 %s UpperArm" % S,
            "lowerarm_%s" % s: "Bip001 %s Forearm" % S,
            "hand_%s" % s: "Bip001 %s Hand" % S,
            "thigh_%s" % s: "Bip001 %s Thigh" % S,
            "calf_%s" % s: "Bip001 %s Calf" % S,
            "foot_%s" % s: "Bip001 %s Foot" % S,
            "ball_%s" % s: "Bip001 %s Toe0" % S,
        })
        for game, d in (("thumb", "0"), ("index", "1"), ("middle", "2"), ("ring", "3"), ("pinky", "4")):
            for seg, suffix in (("01", ""), ("02", "1"), ("03", "2")):
                m["%s_%s_%s" % (game, seg, s)] = "Bip001 %s Finger%s%s" % (S, d, suffix)
        for game, biped in (("upperarm", "UpArmTwist"), ("lowerarm", "ForeTwist"), ("thigh", "ThighTwist"),
                            ("calf", "CalfTwist")):
            for k in (1, 2, 3):
                m["%s_twist_0%d_%s" % (game, k, s)] = "Bip001 %s %s%s" % (S, biped, "" if k == 1 else k - 1)
    for n in names:
        b = BREAST_RE.search(n)
        if b:
            side = (b.group(2) or b.group(3)).upper()
            target = "Bip001 %s Pectoral" % side
            if target not in m.values():
                m[n] = target
    return {k: v for k, v in m.items() if k in names}


def to_biped(arm, meshes):
    import rigtools as rt
    if "Bip001 Pelvis" in arm.data.bones:
        return {"already": True}
    names = {b.name for b in arm.data.bones}
    mapping = build_map(names)
    missing = [k for k in ("pelvis", "thigh_l", "thigh_r", "upperarm_l", "upperarm_r", "head") if k not in mapping]
    out = {"missing": missing}
    out["dropped"] = len(rt.drop_unweighted(arm, meshes, keep=set(mapping)))
    out["renamed"] = rt.rename_bones(arm, meshes, mapping)
    return out
