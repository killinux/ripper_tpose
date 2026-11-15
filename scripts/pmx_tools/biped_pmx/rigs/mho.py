# -*- coding: utf-8 -*-
"""Marvel Heroes Omega player skeleton (g_* bones, scripts/marvelheroes) -> 3ds Max Biped.

The game's tree is not a Biped one:
  root -> g_spine01_offset -> g_spine01 -> {g_pelvis, g_spine02_offset -> g_spine02 -> g_spine03_offset -> g_spine03}
  root -> g_l_hip_offset -> g_l_hip -> g_l_knee -> g_l_ankle -> g_l_ball           (legs hang from the ROOT)
  g_spine03 -> g_breast (one bone for both breasts), g_l_clavical -> g_l_shoulder -> g_l_elbow -> g_l_wrist
plus unskinned IK effectors, attach points, hair / eye / jaw bones the costume does not use.  So: the hips become the
hub (Pelvis -> Spine and both thighs), the *_offset nulls are removed, unskinned leaves are dropped, g_breast is split
into Bip001 L / R Pectoral by side, then everything is renamed.
"""
NAME = "mho"
MAP = {
    "root": "Bip001",
    "g_pelvis": "Bip001 Pelvis",
    "g_spine01": "Bip001 Spine",
    "g_spine02": "Bip001 Spine1",
    "g_spine03": "Bip001 Spine2",
    "g_neck": "Bip001 Neck",
    "g_head": "Bip001 Head",
}
for _s, _S in (("l", "L"), ("r", "R")):
    MAP.update({
        "g_%s_clavical" % _s: "Bip001 %s Clavicle" % _S,
        "g_%s_shoulder" % _s: "Bip001 %s UpperArm" % _S,
        "g_%s_biceptwist" % _s: "Bip001 %s UpArmTwist" % _S,
        "g_%s_uprarm" % _s: "Bip001 %s UpArmTwist1" % _S,
        "g_%s_elbow" % _s: "Bip001 %s Forearm" % _S,
        "g_%s_forarm" % _s: "Bip001 %s ForeTwist" % _S,
        "g_%s_lwrarm" % _s: "Bip001 %s ForeTwist1" % _S,
        "g_%s_wrist" % _s: "Bip001 %s Hand" % _S,
        "g_%s_hip" % _s: "Bip001 %s Thigh" % _S,
        "g_%s_thightwist" % _s: "Bip001 %s ThighTwist" % _S,
        "g_%s_uprleg" % _s: "Bip001 %s ThighTwist1" % _S,
        "g_%s_knee" % _s: "Bip001 %s Calf" % _S,
        "g_%s_lwrlegmid" % _s: "Bip001 %s CalfTwist" % _S,
        "g_%s_lwrlegend" % _s: "Bip001 %s CalfTwist1" % _S,
        "g_%s_ankle" % _s: "Bip001 %s Foot" % _S,
        "g_%s_ball" % _s: "Bip001 %s Toe0" % _S,
    })
    # Biped digits: 0 thumb, 1 index, 2 middle ("birdy" in this rig), 3 ring, 4 pinky; segments Finger<d>, <d>1, <d>2
    for _game, _d in (("thumb", "0"), ("index", "1"), ("birdy", "2"), ("ring", "3"), ("pinky", "4")):
        for _seg, _suffix in (("1", ""), ("2", "1"), ("3", "2")):
            MAP["g_%s_%s%s" % (_s, _game, _seg)] = "Bip001 %s Finger%s%s" % (_S, _d, _suffix)

BUST = (("左胸", "Bip001 L Pectoral"), ("右胸", "Bip001 R Pectoral"))
LIMB_HELPER = r"|uparmtwist\d*$|foretwist\d*$|thightwist\d*$|calftwist\d*$|_scapula$"
EYE_MATERIAL = None          # the symbiote mask's lenses are part of the head, not eyeballs
HAIR_MATERIAL = r"hair"
COMMENT = "Converted from a Marvel Heroes Omega mod by ripper_tpose (scripts/marvelheroes). Personal use only; credit the mod's author."


def to_biped(arm, meshes):
    import rigtools as rt
    if "Bip001 Pelvis" in arm.data.bones:
        return {"already": True}
    out = {}
    out["reparented"] = rt.reparent(arm, [("g_pelvis", "root"), ("g_spine01", "g_pelvis"),
                                          ("g_l_hip", "g_pelvis"), ("g_r_hip", "g_pelvis"),
                                          ("g_spine02", "g_spine01"), ("g_spine03", "g_spine02")])
    out["collapsed"] = rt.collapse(arm, ["g_spine01_offset", "g_spine02_offset", "g_spine03_offset",
                                         "g_l_hip_offset", "g_r_hip_offset"])
    out["dropped"] = rt.drop_unweighted(arm, meshes, keep=set(MAP) | {"g_breast"})
    out["bust"] = rt.split_bone_by_side(arm, meshes, "g_breast", "g_l_pectoral", "g_r_pectoral", parent="g_spine03")
    MAP.update({"g_l_pectoral": "Bip001 L Pectoral", "g_r_pectoral": "Bip001 R Pectoral"})
    out["renamed"] = rt.rename_bones(arm, meshes, MAP)
    return out
