# -*- coding: utf-8 -*-
"""The 52 ARKit blend shapes: names, how a MetaHuman makes each one, and how to recognise them
under other spellings on an existing model."""
import re

# Apple's order (ARFaceAnchor.BlendShapeLocation; Faceit's ARKIT table uses the same)
ARKIT_52 = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft", "eyeSquintLeft",
    "eyeWideLeft", "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight", "eyeLookUpRight",
    "eyeSquintRight", "eyeWideRight", "jawForward", "jawLeft", "jawRight", "jawOpen", "mouthClose", "mouthFunnel",
    "mouthPucker", "mouthRight", "mouthLeft", "mouthSmileLeft", "mouthSmileRight", "mouthFrownRight",
    "mouthFrownLeft", "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthPressLeft", "mouthPressRight",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight", "browDownLeft",
    "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft",
    "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
]


def _one(control, value=1.0):
    return {control: value}


def _quad(stem, value=1.0):
    return {stem + k: value for k in ("UL", "UR", "DL", "DR")}


def metahuman_recipes():
    """ARKit name -> (MetaHuman raw controls, controls the shape is measured against or None).

    The mix follows Epic's ARKit mapping for Live Link Face on a MetaHuman.  ARKit Left/Right and
    MetaHuman L/R both mean the character's own side.  mouthClose is the lips closing OVER an open
    jaw, so it is measured against jawOpen alone (added on top of jawOpen it closes the lips)."""
    out = {}
    for side, s in (("Left", "L"), ("Right", "R")):
        inward, outward = ("Right", "Left") if s == "L" else ("Left", "Right")
        out["eyeBlink" + side] = (_one("eyeBlink" + s), None)
        out["eyeLookDown" + side] = (_one("eyeLookDown" + s), None)
        out["eyeLookIn" + side] = (_one("eyeLook" + inward + s), None)
        out["eyeLookOut" + side] = (_one("eyeLook" + outward + s), None)
        out["eyeLookUp" + side] = (_one("eyeLookUp" + s), None)
        out["eyeSquint" + side] = (_one("eyeSquintInner" + s), None)
        out["eyeWide" + side] = (_one("eyeWiden" + s), None)
        out["mouthSmile" + side] = (_one("mouthCornerPull" + s), None)
        out["mouthFrown" + side] = (_one("mouthCornerDepress" + s), None)
        out["mouthDimple" + side] = (_one("mouthDimple" + s), None)
        out["mouthStretch" + side] = (_one("mouthStretch" + s), None)
        out["mouthPress" + side] = ({"mouthPressU" + s: 1.0, "mouthPressD" + s: 1.0}, None)
        out["mouthLowerDown" + side] = (_one("mouthLowerLipDepress" + s), None)
        out["mouthUpperUp" + side] = (_one("mouthUpperLipRaise" + s), None)
        out["browDown" + side] = ({"browDown" + s: 1.0, "browLateral" + s: 1.0}, None)
        out["browOuterUp" + side] = (_one("browRaiseOuter" + s), None)
        out["cheekSquint" + side] = (_one("eyeCheekRaise" + s), None)
        out["noseSneer" + side] = (_one("noseWrinkle" + s), None)
    out["jawForward"] = (_one("jawFwd"), None)
    out["jawLeft"] = (_one("jawLeft"), None)
    out["jawRight"] = (_one("jawRight"), None)
    out["jawOpen"] = (_one("jawOpen"), None)
    out["mouthClose"] = (dict({"jawOpen": 1.0}, **_quad("mouthLipsTogether")), {"jawOpen": 1.0})
    out["mouthFunnel"] = (_quad("mouthFunnel"), None)
    out["mouthPucker"] = (_quad("mouthLipsPurse"), None)
    out["mouthLeft"] = (_one("mouthLeft"), None)
    out["mouthRight"] = (_one("mouthRight"), None)
    out["mouthRollLower"] = ({"mouthLowerLipRollInL": 1.0, "mouthLowerLipRollInR": 1.0}, None)
    out["mouthRollUpper"] = ({"mouthUpperLipRollInL": 1.0, "mouthUpperLipRollInR": 1.0}, None)
    out["mouthShrugLower"] = ({"jawChinRaiseDL": 1.0, "jawChinRaiseDR": 1.0}, None)
    out["mouthShrugUpper"] = ({"jawChinRaiseUL": 1.0, "jawChinRaiseUR": 1.0}, None)
    out["browInnerUp"] = ({"browRaiseInL": 1.0, "browRaiseInR": 1.0}, None)
    out["cheekPuff"] = ({"mouthCheekBlowL": 1.0, "mouthCheekBlowR": 1.0}, None)
    out["tongueOut"] = (_one("tongueOut"), None)
    return out


# -- recognising ARKit shapes that already exist under another spelling --------------------------
def _norm(name):
    """'eyeBlink_L', 'EyeBlinkLeft', 'Face.eyeBlinkLeft', 'Eye_Blink_L', 'eyeBlink.L' -> 'eyeblinkleft'.
    A side is only read from a separate token (_L, .R, ' left') or a camel-case tail (...kLeft,
    ...kL), so words that merely end in l/r (mouthFunnel, mouthRollUpper) stay as they are."""
    n = name.split(".")[-1] if re.search(r"\.[A-Za-z]{3,}", name) else name     # 'Face.' style prefixes
    side = ""
    m = re.match(r"^(.*?)[\s_\-.]+(left|right|l|r)$", n, re.IGNORECASE)
    if m:
        n, side = m.group(1), m.group(2).lower()
    else:
        m = re.match(r"^(.*[a-z])(Left|Right|L|R)$", n)
        if m:
            n, side = m.group(1), m.group(2).lower()
    side = {"l": "left", "r": "right"}.get(side, side)
    return re.sub(r"[\s_\-.]", "", n).lower() + side


_KNOWN = {_norm(a): a for a in ARKIT_52}


def match_names(key_names):
    """{ARKit name: shape key name} for keys that are ARKit shapes under any common spelling.
    An exact ARKit name always wins over an alias."""
    out = {}
    for key in key_names:
        if key in ARKIT_52:
            out[key] = key
    for key in key_names:
        arkit = _KNOWN.get(_norm(key))
        if arkit and arkit not in out:
            out[arkit] = key
    return out
