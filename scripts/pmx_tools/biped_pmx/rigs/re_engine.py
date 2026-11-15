# -*- coding: utf-8 -*-
"""RE Engine player skeletons (Resident Evil 2 / 3 remakes, read by RE Mesh Editor, scripts/re_engine) -> 3ds Max Biped.

  root -> Null_Offset, COG -> {hips -> l_leg_femur -> l_leg_tibia -> l_leg_ankle -> l_leg_ball,
                               spine_0 -> spine_1 -> spine_2 -> neck_0 -> neck_1 -> head,
                               spine_2 -> l_arm_clavicle -> l_arm_humerus -> l_arm_radius -> l_arm_wrist}
  fingers l_hand_thumb_0..2, l_hand_index_0..2, l_hand_middle_0..2, l_hand_ring_0..3, l_hand_little_0..3 (ring /
  little _0 = metacarpal), twist helpers l_arm_humerus_twist_0_H .., l_leg_femur_twist_0_H .. (they carry most of the
  limb skin), muscle helpers *_muscle under *_muscleOffset nulls, ~100 face bones straight under head.
The hips become the hub (Pelvis -> Spine + thighs, as in a Biped), COG and Null_Offset are removed, the face bones are
merged into the head (no expressions are kept - the face stays as it is), the pectoral muscle helpers (l/r_pecA_muscle,
the only chest bones these rigs have) become the bust bones.
"""
import re

NAME = "re_engine"
BUST = (("左胸", "Bip001 L Pectoral"), ("右胸", "Bip001 R Pectoral"))
LIMB_HELPER = (r"|uparmtwist\d*$|foretwist\d*$|thightwist\d*$|calftwist\d*$|_muscle$|_twist_\d+_h$|_scapula_\d$"
               r"|weapon|holster|setprop|belt|bag\d|light_0|antenna")
EYE_MATERIAL = r"eyes?_in|iris"
HAIR_MATERIAL = r"(^|_)hair"
COMMENT = "Converted from a Resident Evil mod by ripper_tpose (scripts/re_engine). Personal use only; credit the mod's author."
FACE_KEEP = re.compile(r"^(neck|head)|hair|_eye(ball)?$", re.IGNORECASE)


def build_map(names):
    m = {"root": "Bip001", "hips": "Bip001 Pelvis", "spine_0": "Bip001 Spine", "spine_1": "Bip001 Spine1",
         "spine_2": "Bip001 Spine2", "neck_0": "Bip001 Neck", "head": "Bip001 Head"}
    for s, S in (("l", "L"), ("r", "R")):
        m.update({
            "%s_arm_clavicle" % s: "Bip001 %s Clavicle" % S,
            "%s_arm_humerus" % s: "Bip001 %s UpperArm" % S,
            "%s_arm_radius" % s: "Bip001 %s Forearm" % S,
            "%s_arm_wrist" % s: "Bip001 %s Hand" % S,
            "%s_leg_femur" % s: "Bip001 %s Thigh" % S,
            "%s_leg_tibia" % s: "Bip001 %s Calf" % S,
            "%s_leg_ankle" % s: "Bip001 %s Foot" % S,
            "%s_leg_ball" % s: "Bip001 %s Toe0" % S,
            "%s_pecA_muscle" % s: "Bip001 %s Pectoral" % S,
        })
        for game, d in (("thumb", "0"), ("index", "1"), ("middle", "2"), ("ring", "3"), ("little", "4")):
            segs = sorted((n for n in names if re.fullmatch(r"%s_hand_%s_\d" % (s, game), n)), key=lambda n: int(n[-1]))
            if len(segs) == 4:          # _0 is the metacarpal
                segs = segs[1:]
            for name, suffix in zip(segs, ("", "1", "2")):
                m[name] = "Bip001 %s Finger%s%s" % (S, d, suffix)
        for game, biped in (("arm_humerus", "UpArmTwist"), ("arm_radius", "ForeTwist"), ("leg_femur", "ThighTwist"),
                            ("leg_tibia", "CalfTwist")):
            for k in range(4):
                m["%s_%s_twist_%d_H" % (s, game, k)] = "Bip001 %s %s%s" % (S, biped, "" if k == 0 else k)
    return {k: v for k, v in m.items() if k in names}


def to_biped(arm, meshes):
    import rigtools as rt
    if "Bip001 Pelvis" in arm.data.bones:
        return {"already": True}
    names = {b.name for b in arm.data.bones}
    out = {}
    out["reparented"] = rt.reparent(arm, [("hips", "root"), ("spine_0", "hips")])
    out["collapsed"] = rt.collapse(arm, ["COG", "Null_Offset"])
    head = arm.data.bones.get("head")
    face = []
    if head is not None:
        stack = [c for c in head.children]
        while stack:
            b = stack.pop()
            if not FACE_KEEP.search(b.name):
                face.append(b.name)
            stack.extend(b.children)
    out["face_merged"] = rt.merge_into(arm, meshes, face, "head") if face else 0
    mapping = build_map({b.name for b in arm.data.bones})
    out["dropped"] = len(rt.drop_unweighted(arm, meshes, keep=set(mapping)))
    out["renamed"] = rt.rename_bones(arm, meshes, mapping)
    out["missing"] = [k for k in ("hips", "l_leg_femur", "r_leg_femur", "l_arm_humerus", "head") if k not in names]
    return out
