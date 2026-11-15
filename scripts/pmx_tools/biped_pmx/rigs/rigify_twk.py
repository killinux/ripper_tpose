# -*- coding: utf-8 -*-
"""Rigify-style deform chains made of tweak bones (seen on the HS2 studio port "[Fouetty] Venom Marvel Rivals")
-> 3ds Max Biped:

  <root> -> pelvis.twk -> spine.twk -> spine-1.twk -> chest.twk -> chest-1.twk -> neck.twk -> neck-1.twk -> head
  chest-1.twk -> clavicle.L -> upper_arm.bend.twk.L -> upper_arm.twist.twk.L -> forearm.bend.twk.L
              -> forearm.twist.twk.L -> hand.twk.L -> palm_*.L -> f_index.01.L .. / thumb.01.L ..
  pelvis.twk -> thigh.bend.twk.L -> thigh.twist.twk.L -> shin.bend.twk.L -> shin.twist.twk.L -> foot.twk.L -> toe.L
The twist bones sit IN the chain here (upper arm -> twist -> forearm); they are named as Biped twist helpers and the
chain keeps working because the conversion places the MMD bones by slot.  Unskinned DEF-* / control bones are dropped;
tongue and anatomy chains are marked as helpers (never cloth).
"""
NAME = "rigify_twk"
BUST = (("左胸", "Bip001 L Pectoral"), ("右胸", "Bip001 R Pectoral"))
LIMB_HELPER = (r"|uparmtwist\d*$|foretwist\d*$|thightwist\d*$|calftwist\d*$|^palm_|tongue|teeth|pelvis2|anus|rectum"
               r"|scrotum|testicle|shaft|crease|^root\.1$|spine-1\.twk$|neck-1\.twk$")
EYE_MATERIAL = None
HAIR_MATERIAL = r"hair"
COMMENT = "Converted from a HoneySelect 2 studio item mod by ripper_tpose. Personal use only; credit the mod's author."


def build_map(names):
    m = {"pelvis.twk": "Bip001 Pelvis", "spine.twk": "Bip001 Spine", "chest.twk": "Bip001 Spine1",
         "chest-1.twk": "Bip001 Spine2", "neck.twk": "Bip001 Neck", "head": "Bip001 Head"}
    roots = [n for n in names if n.endswith(" FK") or n in ("root", "Root")]
    if roots:
        m[roots[0]] = "Bip001"
    for S in ("L", "R"):
        m.update({
            "clavicle.%s" % S: "Bip001 %s Clavicle" % S,
            "upper_arm.bend.twk.%s" % S: "Bip001 %s UpperArm" % S,
            "upper_arm.twist.twk.%s" % S: "Bip001 %s UpArmTwist" % S,
            "forearm.bend.twk.%s" % S: "Bip001 %s Forearm" % S,
            "forearm.twist.twk.%s" % S: "Bip001 %s ForeTwist" % S,
            "hand.twk.%s" % S: "Bip001 %s Hand" % S,
            "thigh.bend.twk.%s" % S: "Bip001 %s Thigh" % S,
            "thigh.twist.twk.%s" % S: "Bip001 %s ThighTwist" % S,
            "shin.bend.twk.%s" % S: "Bip001 %s Calf" % S,
            "shin.twist.twk.%s" % S: "Bip001 %s CalfTwist" % S,
            "foot.twk.%s" % S: "Bip001 %s Foot" % S,
            "toe.%s" % S: "Bip001 %s Toe0" % S,
        })
        for game, d in (("thumb", "0"), ("f_index", "1"), ("f_middle", "2"), ("f_ring", "3"), ("f_pinky", "4")):
            for seg, suffix in (("01", ""), ("02", "1"), ("03", "2")):
                m["%s.%s.%s" % (game, seg, S)] = "Bip001 %s Finger%s%s" % (S, d, suffix)
    return {k: v for k, v in m.items() if k in names}


def to_biped(arm, meshes):
    import rigtools as rt
    if "Bip001 Pelvis" in arm.data.bones:
        return {"already": True}
    names = {b.name for b in arm.data.bones}
    mapping = build_map(names)
    out = {"missing": [k for k in ("pelvis.twk", "thigh.bend.twk.L", "upper_arm.bend.twk.L", "head") if k not in names]}
    out["dropped"] = len(rt.drop_unweighted(arm, meshes, keep=set(mapping)))
    out["renamed"] = rt.rename_bones(arm, meshes, mapping)
    return out
