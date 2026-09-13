"""The MMD standard expression set as recipes over face-bone roles.

An action is ``(role, kind, amount)``:

``pitch`` deg   rotate about the lateral axis; positive = the front of the
                bone goes DOWN (a lid closes, the jaw opens, a tongue tip dips)
``roll``  deg   rotate about the front axis; positive = the OUTER end goes UP
                (mirrored per side)
``yaw``   deg   rotate about the vertical axis; positive = the front end swings
                OUTWARD (for a central bone: toward the character's left, +X)
``move``  (out, fwd, up)   translation in eye spacings; ``out`` is away from the
                midline (mirrored per side), ``fwd`` toward the face

Angles below were calibrated on ROE heads by rendering sweeps: the upper lid
closes at 33 deg with the pivot at the eyeball centre, the jaw reads as あ at
18 deg.  Actions on roles a model lacks are skipped; a morph with nothing left
is not created.
"""
BLINK_DEG = 33.0      # upper lid, closed
LOWER_SHARE = 0.45    # the lower lid's share of a blink (it rises)
JAW_DEG = 18.0        # あ

EYES, BROWS, MOUTH, TONGUE = "eyes", "brows", "mouth", "tongue"


def scale_group(role):
    """Which user multiplier an action on this role obeys."""
    if role.startswith(("upper_lid", "lower_lid", "eye")):
        return EYES
    if role.startswith("brow"):
        return BROWS
    if role.startswith("tongue"):
        return TONGUE
    return MOUTH


# -- helpers ------------------------------------------------------------------
def lids(sides, upper, lower):
    """upper/lower as fractions of a blink (lower 1.0 = the lid's blink share)."""
    acts = []
    for side in sides:
        if upper:
            acts.append(("upper_lid_%s" % side, "pitch", upper * BLINK_DEG))
        if lower:
            acts.append(("lower_lid_%s" % side, "pitch", -lower * BLINK_DEG * LOWER_SHARE))
    return acts


def lid_roll(sides, degrees):
    return [("upper_lid_%s" % side, "roll", degrees) for side in sides]


def brows(inner=None, centre=None, outer=None, root=None, tilt=0.0):
    """Segment moves for rigs with three brow bones per side; ``tilt`` (roll of
    the root, outer end up) only applies to rigs whose brow is a single bone."""
    acts = []
    for side in "LR":
        for segment, amount in (("inner", inner), ("centre", centre), ("outer", outer)):
            if amount:
                acts.append(("brow_%s_%s" % (side, segment), "move", amount))
        if root:
            acts.append(("brow_%s" % side, "move", root))
        if tilt:
            acts.append(("brow_%s_tilt" % side, "roll", tilt))
    return acts


def jaw(degrees):
    return [("chin", "pitch", degrees)]


def corners(out=0.0, up=0.0, fwd=0.0, sides="LR"):
    return [("corner_%s" % side, "move", (out, fwd, up)) for side in sides]


def lip(role, out=0.0, fwd=0.0, up=0.0):
    return [(role, "move", (out, fwd, up))]


def tongue(fwd=0.0, down=0.0, pitch=0.0, yaw=0.0, curl=0.0):
    acts = []
    if fwd or down:
        acts.append(("tongue_0", "move", (0.0, fwd, -down)))
    if pitch:
        acts.append(("tongue_0", "pitch", pitch))
    if yaw:
        acts.append(("tongue_0", "yaw", yaw))
    if curl:
        acts.append(("tongue_1", "pitch", curl))
        acts.append(("tongue_2", "pitch", curl * 0.7))
    return acts


def teeth(which, back, up):
    return [("teeth_%s" % which, "move", (0.0, -back, up))]


def morph(name, name_e, category, actions):
    return {"name": name, "name_e": name_e, "category": category, "actions": actions}


# -- the set -------------------------------------------------------------------
SMILE = lids("LR", 0.35, 2.2)            # lower lid up, upper down a little: ^ ^
# Calibrated by measuring the evaluated mesh, not by eye: the tongue tip sits
# 4-8 mm BEHIND the lip surface at rest, so a rotation alone can only push it
# through the chin (which is what a jaw-8/pitch-18 first attempt did).  It has
# to be carried forward bodily.  fwd 0.45 puts the tip ~14 mm past the lower
# lip with the jaw open 16 deg; the curl then lets it droop over the lip.
PERO = jaw(16.0) + tongue(fwd=0.45, down=0.08, pitch=6.0, curl=6.0)
OMEGA = (corners(out=-0.10, up=0.06) + lip("upper_lip_C", fwd=0.03, up=-0.03)
         + lip("lower_lip_C", fwd=0.03, up=0.02))

MORPHS = [
    # 眉
    morph("真面目", "serious", "EYEBROW",
          brows(inner=(-0.02, 0.0, -0.04), centre=(0.0, 0.0, -0.01), outer=(0.0, 0.0, 0.02), tilt=5.0)),
    morph("困る", "troubled", "EYEBROW",
          brows(inner=(-0.02, 0.0, 0.09), centre=(0.0, 0.0, 0.03), outer=(0.0, 0.0, -0.05),
                root=(0.0, 0.0, 0.02), tilt=-12.0)),
    morph("にこり", "smile_brow", "EYEBROW",
          brows(inner=(0.0, 0.0, 0.02), centre=(0.0, 0.0, 0.05), outer=(0.0, 0.0, 0.03),
                root=(0.0, 0.0, 0.03))),
    morph("怒り", "anger", "EYEBROW",
          brows(inner=(-0.05, 0.0, -0.09), centre=(0.0, 0.0, -0.03), outer=(0.0, 0.0, 0.05),
                root=(0.0, 0.0, -0.01), tilt=14.0)),
    morph("上", "brow_up", "EYEBROW", brows(root=(0.0, 0.0, 0.10))),
    morph("下", "brow_down", "EYEBROW", brows(root=(0.0, 0.0, -0.08))),
    # 目
    morph("まばたき", "blink", "EYE", lids("LR", 1.0, 1.0)),
    morph("笑い", "smile", "EYE", SMILE),
    morph("ウィンク", "wink", "EYE", lids("L", 1.0, 1.0)),
    morph("ウィンク右", "wink_right", "EYE", lids("R", 1.0, 1.0)),
    morph("ウィンク２", "wink2", "EYE", lids("L", 0.45, 2.2)),
    morph("ｳｨﾝｸ２右", "wink2_right", "EYE", lids("R", 0.45, 2.2)),
    morph("なごみ", "calm", "EYE", lids("LR", 0.5, 0.5)),
    morph("はぅ", "hau", "EYE", lids("LR", 1.05, 1.3)),
    morph("びっくり", "surprised", "EYE", lids("LR", -0.25, -0.4)),
    morph("じと目", "jito", "EYE", lids("LR", 0.55, 0.0)),
    morph("キリッ", "kiri", "EYE", lid_roll("LR", 10.0) + lids("LR", 0.12, 0.2)),
    # 口
    morph("あ", "a", "MOUTH", jaw(JAW_DEG)),
    morph("い", "i", "MOUTH", jaw(6.0) + corners(out=0.22)),
    morph("う", "u", "MOUTH", jaw(7.0) + corners(out=-0.18, fwd=0.04)),
    morph("え", "e", "MOUTH", jaw(12.0) + corners(out=0.10)),
    morph("お", "o", "MOUTH", jaw(13.0) + corners(out=-0.12, fwd=0.03)),
    morph("▲", "triangle", "MOUTH", jaw(7.0) + corners(out=-0.12, up=-0.04)),
    morph("∧", "frown", "MOUTH", corners(out=-0.04, up=-0.07) + lip("lower_lip_C", up=0.02)),
    morph("ω", "omega", "MOUTH", OMEGA),
    morph("ω□", "omega_open", "MOUTH", OMEGA + jaw(6.0)),
    morph("にやり", "grin", "MOUTH", corners(out=0.08, up=0.07)),
    morph("にやり２", "grin2", "MOUTH", corners(out=0.08, up=0.09, sides="L")),
    morph("ぺろっ", "tongue_out", "MOUTH", PERO),
    morph("てへぺろ", "tehepero", "MOUTH", PERO + tongue(yaw=25.0) + lids("L", 1.0, 1.0)),
    morph("てへぺろ２", "tehepero2", "MOUTH", PERO + tongue(yaw=-25.0) + lids("R", 1.0, 1.0)),
    morph("口角上げ", "corner_up", "MOUTH", corners(up=0.08)),
    morph("口角下げ", "corner_down", "MOUTH", corners(up=-0.08)),
    morph("口横広げ", "mouth_wide", "MOUTH", corners(out=0.25)),
    morph("歯無し上", "no_upper_teeth", "MOUTH", teeth("up", back=0.20, up=0.18)),
    morph("歯無し下", "no_lower_teeth", "MOUTH", teeth("dw", back=0.20, up=-0.18)),
]

NAMES = [m["name"] for m in MORPHS]
CATEGORIES = ("EYEBROW", "EYE", "MOUTH")
