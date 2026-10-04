"""Read one Action Taimanin unit prefab out of the bundles into the scene folder build_blend.py takes
(scene.json + parts/*.npz + textures/*.png - the format of ../taimaninsquad/tsquad_scene.py, whose Scene
does the walking, the mesh decoding and the baking; this file adds what this game does differently).

What the game data looks like (measured on asagi_costume_1_f, see the README):

* a figure prefab is ``<name>_F`` (FigureUnit) > ``prf_<char>_costume_<n>`` (Animator, CostumeBody,
  DynamicBone x n) > ``charbody`` + ``charhair`` renderers and the skeleton ``root/Bip001/...`` - a 3ds Max
  Biped again, with unnamed extras (``Bone005`` / ``Bone006`` are Asagi's breasts);
* the face is a prefab of its own under ``Bip001 Head/Socket_head``: ``fbx_<char>_face`` with ``charface``
  skinned to about 28 FACE BONES (eyeballs, lids, brows, lips, teeth, tongue) - there are no blend shapes,
  expressions are animation clips on those bones.  ``fbx_<char>_face_none`` (inactive) is a spare face
  without the rig, ``emotion_shy`` (inactive) a blush card;
* a few bones are NOT on the bind pose in the prefab (Asagi's ``Bone_hair00`` / ``Bone_hair06``, the two
  thin side locks: 26 degrees off).  The prefab pose is the look - baked on the bind pose the locks stick out
  sideways instead of lying along the hair (both were rendered and compared); so, as for Squad, what is
  baked is what Unity draws before any animation;
* cloth is Dynamic Bone (the Unity asset): one component per chain with damping / elasticity / stiffness /
  inert, spheres and capsules as colliders.  The breasts are single-bone chains with an end offset;
* materials are Toony Colors Pro 2 (``eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline ...``, 84 % of
  the character materials) or Unity-Chan Toon Shader 2 (``UnityChanToonShader/Mobile/Toon_ShadingGradeMap``,
  the newer costumes), both with the studio's "parts colour" recolouring; eyes are a Shader Forge unlit
  shader.  The game renders in GAMMA space (Squad: linear).
"""
from __future__ import annotations

import os
import re

import numpy as np

import ataimanin_anim as aa
import ataimanin_common as ac
import tsquad_scene as ts
from ataimanin_common import tc

EMOTION = re.compile(r"^emotion_", re.IGNORECASE)      # blush / sweat cards the game switches on
FACE_ROOT = re.compile(r"^fbx_(?P<who>.+?)_face$")     # the face prefab: its Animator plays the expression clips
STORY_CLIP = re.compile(r"/ani_story/ani_(?P<kind>face|mouth)_(?P<who>.+?)_story_(?P<name>[a-z]+?)_?(?P<n>\d*)\.anim$")
LID = re.compile(r"_Eye_[LR]_Shape|_Eye_Top", re.IGNORECASE)        # the bones a blink moves
BROW = re.compile(r"Eyebrow", re.IGNORECASE)
LIP = re.compile(r"_Lip_(UL|UR|DL|DR|U|D|L|R)$", re.IGNORECASE)
EYEBALL = re.compile(r"Eyeball_([LR])$", re.IGNORECASE)
EYE_SIDE = re.compile(r"_Eye_([LR])_", re.IGNORECASE)
UPPER_LID = re.compile(r"_Shape_U_", re.IGNORECASE)
# the shape names Taimanin Squad's PMX converter knows the roles of (export_pmx_blender.SOURCES)
SHAPE_NAMES = {"surprise": "surprised_face"}
BLINK, TALK = "closed_eyes", "mouth_talk_a"
# one region of a story face, cut by bone group: (clip, region, bones) -> shape "<clip>_<region>".  The MMD
# morphs that are one region of a face (the brows of the angry face, the lids of the smile) come from these -
# on this face the brows sit at the height of the upper lashes, a cut by height cannot part them.
CUTS = (("smile", "eyes", LID), ("surprise", "eyes", LID), ("smile", "brows", BROW), ("angry", "brows", BROW),
        ("serious", "brows", BROW), ("panic", "brows", BROW))
# Mouth shapes the game has no clip for (its only mouths are the frown of the serious faces and the open
# talking mouths), posed here on the eight lip bones: (outward, up, forward) in millimetres per bone group, for
# a mouth 28 mm wide (scaled to the mouth).  NOT game data - a recipe, tuned by eye on Asagi.
LIP_GROUP = {"L": "corner", "R": "corner", "UL": "upper_side", "UR": "upper_side", "DL": "lower_side",
             "DR": "lower_side", "U": "upper", "D": "lower"}
MOUTH_WIDTH = 0.028
MOUTH_POSES = {
    "mouth_smile": {"corner": (1.2, 2.4, -0.4), "upper_side": (0.3, 0.5, 0.0), "lower_side": (0.4, 1.0, 0.0),
                    "lower": (0.0, 0.3, 0.0)},
    "mouth_frown": {"corner": (0.4, -2.2, 0.0), "upper_side": (0.0, -0.8, 0.0), "lower_side": (0.0, -0.5, 0.0)},
    "mouth_wide": {"corner": (2.4, 0.0, -0.8), "upper_side": (0.9, 0.0, 0.0), "lower_side": (0.9, 0.0, 0.0)},
    "mouth_narrow": {"corner": (-3.2, 0.0, 1.0), "upper_side": (-1.3, 0.2, 1.2), "lower_side": (-1.3, -0.2, 1.2),
                     "upper": (0.0, 0.3, 0.9), "lower": (0.0, -0.3, 0.9)},
}
# Looks, by turning the eyeball bones about their heads: shape -> (direction, degrees).  The game's own
# sideways look (the panic face) is 9 degrees; left / right are as seen from the front (screen left / right),
# which is how Taimanin Squad's own left_eyes / right_eyes shapes go.
GAZE = {"up_eyes": ("up", 5.0), "down_eyes": ("down", 5.0), "left_eyes": ("left", 9.0), "right_eyes": ("right", 9.0)}
SMILE_CLOSES = 0.7                                     # of the eye's opening: the smile's eyes are shut ("^ ^")
FACE = re.compile(r"face", re.IGNORECASE)
HAIR = re.compile(r"hair", re.IGNORECASE)
SPINE = re.compile(r"^Bip\d+ Spine\d*$")
BUST_NAME = re.compile(r"bust|breast|mune|oppai|boob", re.IGNORECASE)
MORE_NORMALS = ("_NormalMapForMatCap",)
# face bones and other skinned bones that are the body itself, not something that swings (for the PMX
# converter: mmd_cloth_physics takes every other chain of skinned bones for a garment)
BODY_BONES = r"^(root_face|Bone_face|Bone_Face_|Bone_Eye|Bone_Teeth|Bone_Tongue|Bone_Jaw|fbx_)"


def family(shader: str) -> str:
    if shader.startswith("eTOYLab/Toony Colors Pro 2"):
        return "tcp2"
    if shader.startswith("UnityChanToonShader"):
        return "uts2"
    if shader.startswith("Shader Forge/eye"):
        return "eye"
    if "Particles" in shader:
        return "particle"
    return "other"


def _rgb(colors: dict, key: str, default=(1.0, 1.0, 1.0, 1.0)) -> list[float]:
    return [float(v) for v in (colors.get(key) or default)]


def hints(spec: dict) -> dict:
    """What a format converter needs of a material, whatever the shader: the colour picture, how much
    darker the shadow side is (display values, per channel), the sphere map, the outline.

    tcp2:  shadow = lerp(1, _SColor.rgb, _SColor.a)             (the highlight colour is white in this build)
    uts2:  shadow = _1st_ShadeColor / _BaseColor                (the base map is its own 1st shade map)
           matcap = _MatCap_Sampler x _MatCapColor, masked by _Set_MatcapMask.g, added or multiplied
    outline widths in millimetres: tcp2 moves a vertex _Outline x 0.01 along the normal, uts2
    _Outline_Width x 0.001."""
    shader, kind = spec.get("shader", ""), family(spec.get("shader", ""))
    tex, floats, colors = spec.get("textures", {}), spec.get("floats", {}), spec.get("colors", {})
    out = {"family": kind}
    base = tex.get("_MainTex") or tex.get("_diffuse_map") or tex.get("_Main_Tex")
    if base:
        out["base_map"] = base["file"]
    if kind == "tcp2":
        s = _rgb(colors, "_SColor", (0.195, 0.195, 0.195, 1.0))
        out["shade"] = [round(1.0 + (c - 1.0) * s[3], 4) for c in s[:3]]
        if "Outline" in shader.rsplit("/", 1)[-1] and floats.get("_Outline", 1.0) > 0.0:
            c = _rgb(colors, "_OutlineColor", (0.2, 0.2, 0.2, 1.0))
            out["outline"] = {"width_mm": round(floats.get("_Outline", 1.0) * 10.0, 3), "color": c[:3],
                              "alpha": c[3] if "OutlineBlending" in shader else 1.0}
    elif kind == "uts2":
        base_c, shade_c = _rgb(colors, "_BaseColor"), _rgb(colors, "_1st_ShadeColor")
        if floats.get("_Use_BaseAs1st", 0.0) >= 0.5 or "_1st_ShadeMap" not in tex:
            out["shade"] = [round(min(1.0, s / max(b, 1e-3)), 4) for s, b in zip(shade_c[:3], base_c[:3])]
        if floats.get("_MatCap", 0.0) >= 0.5 and tex.get("_MatCap_Sampler"):
            mask = tex.get("_Set_MatcapMask")
            out["sphere"] = {"file": tex["_MatCap_Sampler"]["file"], "color": _rgb(colors, "_MatCapColor")[:3],
                             "mask": {"file": mask["file"], "channel": 1} if mask else None,
                             "level": floats.get("_Tweak_MatcapMaskLevel", 0.0),
                             "mode": "add" if floats.get("_Is_BlendAddToMatCap", 1.0) >= 0.5 else "multiply"}
        tail = shader.lower()
        if "without_outline" not in tail and "nooutline" not in tail and floats.get("_Outline_Width", 0.0) > 0.0:
            out["outline"] = {"width_mm": round(floats["_Outline_Width"], 3), "color": _rgb(colors, "_Outline_Color")[:3],
                              "alpha": 1.0, "blend_base": floats.get("_Is_BlendBaseColor", 0.0) >= 0.5}
    return out


def breast_pair(candidates: list[dict], forward: float = 1.0) -> list[str]:
    """The two breast bones among the Dynamic Bone roots: [{"bone", "parent", "pos" (world x, y, z),
    "leaf"}].  Named ones first (bust / breast / mune); else the mirrored pair of single-bone chains that
    hangs on a spine bone in front of it (Asagi: Bone005 / Bone006).  `forward`: +1 when the character
    faces +Z."""
    named = [c["bone"] for c in candidates if BUST_NAME.search(c["bone"])]
    if len(named) >= 2:
        return named[:2]
    pool = [c for c in candidates if c.get("leaf") and SPINE.match(c.get("parent") or "")]
    best, best_gap = [], None
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if a["parent"] != b["parent"]:
                continue
            ax, ay, az = a["pos"]
            bx, by, bz = b["pos"]
            px, _py, pz = a.get("parent_pos", (0.0, 0.0, 0.0))
            mirrored = abs((ax - px) + (bx - px)) < 0.02 and abs(ax - bx) > 0.04 and abs(ay - by) < 0.02
            in_front = (az - pz) * forward > 0.03 and (bz - pz) * forward > 0.03
            if mirrored and in_front:
                gap = abs(ax - bx)
                if best_gap is None or gap < best_gap:
                    best, best_gap = [a["bone"], b["bone"]], gap
    return best


def story_clips(game, names, known: set[int]) -> dict:
    """{"face": {label: Clip}, "mouth": {label: Clip}} - the story expression clips of a character.

    ``animation_char/<char>/ani_story/ani_face_<char>_story_<name>_01.anim`` holds the face of one expression
    (idle, smile, angry, panic, serious, shy, surprise; the idle one blinks after a second),
    ``ani_mouth_<char>_story_<name>_01.anim`` is a single pose: the mouth open, for talking with that face.
    `names`: how the character may be called; `known`: the path hashes of the face rig - a clip most of whose
    curves address other paths belongs to another rig and is left out."""
    out = {"face": {}, "mouth": {}}
    wanted = {n for n in names if n}
    for key, pptr in sorted(game.container("animation_char").items()):
        match = STORY_CLIP.search(key)
        if match is None or "/cinematic/" in key or match.group("who") not in wanted:
            continue
        label = match.group("name") + ("_" + match.group("n") if match.group("n") not in ("", "1", "01") else "")
        reader = game.deref(pptr)
        if reader is None or label in out[match.group("kind")]:
            continue
        clip = aa.Clip(reader.read_typetree())
        bound = [b for b in clip.bindings if b[1] != "float"]
        if bound and sum(1 for b in bound if b[0] in known) >= 0.8 * len(bound):
            out[match.group("kind")][label] = clip
    return out


def posed_local(rest: np.ndarray, keyed: dict) -> np.ndarray:
    """A bone's local matrix with the clip's position / rotation / scale put in place of the rest values."""
    scale = np.linalg.norm(rest[:3, :3], axis=0)
    if "position" not in keyed and "rotation" not in keyed and "scale" not in keyed:
        return rest
    out = np.eye(4)
    if "rotation" in keyed:
        out = ts.trs_matrix((0.0, 0.0, 0.0), keyed["rotation"], (1.0, 1.0, 1.0))
    else:
        out[:3, :3] = rest[:3, :3] / np.maximum(scale, 1e-12)
    out[:3, :3] = out[:3, :3] * np.asarray(keyed.get("scale", scale), dtype=np.float64)
    out[:3, 3] = keyed.get("position", rest[:3, 3])
    return out


def skin_deltas(vertices, bone_indices, bone_weights, changes: np.ndarray) -> np.ndarray:
    """Per-vertex move when bone i's world matrix changes by changes[i] = New_i x Rest_i^-1 - I (zero for
    a bone that stays).  Linear blend skinning on vertices already in the rest pose."""
    w = bone_weights.astype(np.float64)
    total = w.sum(axis=1, keepdims=True)
    w = np.where(total > 1e-8, w / np.maximum(total, 1e-8), 0.0)
    homogeneous = np.concatenate([vertices.astype(np.float64), np.ones((len(vertices), 1))], axis=1)
    return np.einsum("nk,nkij,nj->ni", w, changes[bone_indices], homogeneous)[:, :3]


def rotation_about(point, axis, degrees: float) -> np.ndarray:
    """4x4 turn of `degrees` about the line through `point` along `axis`."""
    k = np.asarray(axis, dtype=np.float64)
    k = k / max(float(np.linalg.norm(k)), 1e-12)
    a = np.radians(degrees)
    cross = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    out = np.eye(4)
    out[:3, :3] = np.eye(3) * np.cos(a) + np.sin(a) * cross + (1.0 - np.cos(a)) * np.outer(k, k)
    p = np.asarray(point, dtype=np.float64)
    out[:3, 3] = p - out[:3, :3] @ p
    return out


def look_turn(head, forward: float, direction, degrees: float) -> np.ndarray:
    """The turn about an eyeball bone's head that carries the front of the eye (the character faces
    `forward` x Z) towards `direction` (a unit vector across the view axis)."""
    return rotation_about(head, np.cross((0.0, 0.0, forward), direction), degrees)


def mouth_moves(lips: dict, pose: dict, forward: float) -> dict:
    """{lip bone suffix: world move (m)} of one MOUTH_POSES entry.  `lips`: {suffix (L, UR, D ...): rest
    position}; outward is away from the mouth's centre plane, amounts scale with the mouth's width."""
    centre = [lips[s][0] for s in ("U", "D") if s in lips] or [p[0] for p in lips.values()]
    cx = float(np.mean(centre))
    corners = [abs(lips[s][0] - cx) for s in ("L", "R") if s in lips]
    scale = (2.0 * float(np.mean(corners)) / MOUTH_WIDTH) if corners else 1.0
    out = {}
    for suffix, position in lips.items():
        amount = pose.get(LIP_GROUP.get(suffix.upper(), ""))
        if amount is None:
            continue
        side = 0.0 if abs(position[0] - cx) < 1e-4 else (1.0 if position[0] > cx else -1.0)
        out[suffix] = np.array([side * amount[0], amount[1], forward * amount[2]]) * 0.001 * scale
    return out


def lid_gap(x, y, upper, lower, bins: int = 6) -> float:
    """Mean opening of an eye (m): over `bins` columns across the eye, the lower edge of the upper lid minus
    the upper edge of the lower lid (0 where they meet or overlap).  x, y: vertex coordinates (y up);
    upper / lower: the vertices the upper / lower lid bones hold."""
    if not upper.any() or not lower.any():
        return 0.0
    edges = np.linspace(float(x[lower].min()), float(x[lower].max()), bins + 1)
    gaps = []
    for a, b in zip(edges[:-1], edges[1:]):
        u, low = upper & (x >= a) & (x <= b), lower & (x >= a) & (x <= b)
        if u.any() and low.any():
            gaps.append(max(0.0, float(y[u].min() - y[low].max())))
    return float(np.mean(gaps)) if gaps else 0.0


def eye_closure(vertices, bone_indices, bone_weights, bones, delta) -> dict:
    """{side: the part of the eye's opening the vertex move `delta` closes, 0..1}, measured on the lids
    themselves (lid_gap) - the lid bones turn as well as move, and a "^ ^" smile closes the eye from below,
    so neither the bones' travel nor a comparison with the blink tells."""
    out = {}
    w = bone_weights.astype(np.float64)
    for side in ("L", "R"):
        def held(upper):
            idx = [k for k, b in enumerate(bones) if LID.search(b) and bool(UPPER_LID.search(b)) == upper
                   and (EYE_SIDE.search(b) or [None, ""])[1].upper() == side]
            return (w * np.isin(bone_indices, idx)).sum(axis=1) > 0.3

        upper, lower = held(True), held(False)
        rest = lid_gap(vertices[:, 0], vertices[:, 1], upper, lower)
        if rest > 1e-4:
            posed = vertices + delta
            out[side] = 1.0 - lid_gap(posed[:, 0], posed[:, 1], upper, lower) / rest
    return out


def by_side(nodes: list[tuple], pattern, skinned: set) -> dict:
    """{what the pattern's first group says, upper case: node id} of the nodes [(id, name, bone name)] the
    pattern fits.  Where several fit one side, the one that carries skin: a face rig can hold a helper named
    alike next to the bone (Taimanin Collection: ``Point_Eyeball_L`` beside ``Bone_Eyeball_L``)."""
    out, holds = {}, {}
    for nid, name, bone in nodes:
        found = pattern.search(name)
        if found is None:
            continue
        side = found.group(1).upper()
        if side not in out or (bone in skinned and not holds[side]):
            out[side], holds[side] = nid, bone in skinned
    return out


def morph_recipes(have, smile_closes: bool) -> tuple[list, list]:
    """(recipes, shapes to leave out of the PMX's own-name list) for export_pmx_blender: MMD morph name,
    English name, panel, [(shape, strength, region)] - which of the shapes made here each standard morph is.
    A recipe is only given when all its shapes exist; the converter's defaults stand for the rest."""
    wanted = [
        ("笑い", "smile", "EYE", [("smile_eyes", 1.0, "all")], smile_closes),
        ("ウィンク", "wink", "EYE", [("smile_eyes", 1.0, "L")], smile_closes and BLINK in have),
        ("ウィンク右", "wink_R", "EYE", [("smile_eyes", 1.0, "R")], smile_closes and BLINK in have),
        ("びっくり", "surprised", "EYE", [("surprise_eyes", 1.0, "all")], True),
        ("い", "i", "MOUTH", [(TALK, 0.3, "all"), ("mouth_wide", 1.0, "all")], True),
        ("う", "u", "MOUTH", [(TALK, 0.25, "all"), ("mouth_narrow", 1.0, "all")], True),
        ("え", "e", "MOUTH", [(TALK, 0.55, "all"), ("mouth_wide", 0.6, "all")], True),
        ("お", "o", "MOUTH", [(TALK, 0.8, "all"), ("mouth_narrow", 0.75, "all")], True),
        ("にっこり", "smile_mouth", "MOUTH", [("mouth_smile", 1.0, "all")], True),
        ("口角下げ", "mouth_corner_down", "MOUTH", [("mouth_frown", 1.0, "all")], True),
        ("困る", "trouble", "EYEBROW", [("panic_brows", 1.0, "all")], True),
        ("怒り", "anger", "EYEBROW", [("angry_brows", 1.0, "all")], True),
        ("真面目", "serious", "EYEBROW", [("serious_brows", 1.0, "all")], True),
        ("にこり", "cheerful", "EYEBROW", [("smile_brows", 1.0, "all")], True),
    ]
    recipes = [[jp, en, panel, [list(p) for p in parts]] for jp, en, panel, parts, ok in wanted
               if ok and all(p[0] in have for p in parts)]
    helpers = ["%s_%s" % (label, region) for label, region, _bones in CUTS] + list(MOUTH_POSES) + list(GAZE)
    return recipes, [name for name in helpers if name in have]


class Scene(ts.Scene):
    """tsquad_scene.Scene with this game's parts, materials and Dynamic Bone."""

    def __init__(self, loader, out_dir: str):
        super().__init__(loader, out_dir)
        self.colliders: list[dict] = []

    # an inactive transform that carries no skin is a spare (the face without a rig, lights): not a bone
    def _is_helper(self, node) -> bool:
        return (not node["active"]) or super()._is_helper(node)

    def texture(self, pptr, prop: str):
        return super().texture(pptr, "_NormalMap" if prop in MORE_NORMALS else prop)

    def material(self, pptr):
        name = super().material(pptr)
        if name is not None and "hints" not in self.materials[name]:
            self.materials[name]["hints"] = hints(self.materials[name])
        return name

    def add_renderers(self, root_id: int, include_inactive: bool = False):
        woken = []
        for nid, node in self.nodes.items():
            parent = self.nodes.get(node["parent"]) if node["parent"] is not None else None
            if EMOTION.search(node["name"]) and not node["active"] and parent is not None and parent["active"]:
                node["active"] = True                  # baked like the rest, kept hidden (role "emote")
                woken.append(node["name"])
        super().add_renderers(root_id, include_inactive)
        for part in self.parts:
            if EMOTION.search(part["mesh"]) or EMOTION.search(part["name"]):
                part["role"], part["active"] = "emote", False
            elif part["role"] == "body" and FACE.search(part["name"]):
                part["role"] = "face"
            elif part["role"] == "body" and HAIR.search(part["name"]):
                part["role"] = "hair"
        return woken

    def read_cloth(self, root_id: int):
        """Dynamic Bone chains and colliders (kept in the scene as physics hints); the breast pair becomes
        the group "Breast" the Squad code looks for."""
        owner = {}
        for nid, node in self.nodes.items():
            for comp in node["components"]:
                owner[comp.path_id] = nid
        chains = []
        for nid in self._ordered(root_id):
            node = self.nodes[nid]
            for comp, cls in zip([c for c in node["components"] if c.type.name == "MonoBehaviour"], node["monos"]):
                if cls not in ("DynamicBone", "DynamicBoneCollider"):
                    continue
                try:
                    data = comp.read_typetree()
                except Exception:  # noqa: BLE001
                    continue
                if cls == "DynamicBoneCollider":
                    c = data.get("m_Center") or {}
                    self.colliders.append({
                        "bone": node.get("bone") or node["name"], "direction": data.get("m_Direction"),
                        "bound": data.get("m_Bound"), "radius": data.get("m_Radius"), "height": data.get("m_Height"),
                        "center": [c.get("x", 0.0), c.get("y", 0.0), c.get("z", 0.0)]})
                    continue
                ref = data.get("m_Root") or {}
                target = self.nodes.get(self._nid(node, ref.get("m_FileID"), ref.get("m_PathID")))
                if target is None:
                    continue

                def vec(key):
                    v = data.get(key) or {}
                    return [round(v.get("x", 0.0), 5), round(v.get("y", 0.0), 5), round(v.get("z", 0.0), 5)]

                hit = [self.nodes[owner[c["m_PathID"]]] for c in data.get("m_Colliders") or []
                       if not c.get("m_FileID") and c.get("m_PathID") in owner]
                parent = self.nodes.get(target["parent"]) if target["parent"] is not None else None
                chains.append({
                    "name": "DynamicBone", "kind": "dynamic_bone", "root_bones": [target.get("bone") or target["name"]],
                    "damping": data.get("m_Damping"), "elasticity": data.get("m_Elasticity"),
                    "stiffness": data.get("m_Stiffness"), "inert": data.get("m_Inert"), "radius": data.get("m_Radius"),
                    "end_length": data.get("m_EndLength"), "end_offset": vec("m_EndOffset"),
                    "gravity": vec("m_Gravity"), "force": vec("m_Force"), "freeze_axis": data.get("m_FreezeAxis"),
                    "colliders": [n.get("bone") or n["name"] for n in hit],
                    "_leaf": not any("bone" in self.nodes[c] for c in target["children"]),
                    "_parent": (parent.get("bone") or parent["name"]) if parent else "",
                    "_pos": target["world"][:3, 3].tolist(),
                    "_parent_pos": parent["world"][:3, 3].tolist() if parent else [0.0, 0.0, 0.0]})
        pair = breast_pair([{"bone": c["root_bones"][0], "parent": c["_parent"], "pos": c["_pos"],
                             "parent_pos": c["_parent_pos"], "leaf": c["_leaf"]} for c in chains], self.forward())
        for chain in chains:
            if chain["root_bones"][0] in pair:
                chain["name"] = "Breast"
            for key in [k for k in chain if k.startswith("_")]:
                del chain[key]
        breasts = [c for c in chains if c["name"] == "Breast"]
        if len(breasts) == 2:                          # one group with both roots, as tsquad_scene.breast_bones reads it
            breasts[0]["root_bones"] = [breasts[0]["root_bones"][0], breasts[1]["root_bones"][0]]
            chains.remove(breasts[1])
            chains.insert(0, chains.pop(chains.index(breasts[0])))
        self.cloth.extend(chains)

    # ------------------------------------------------------------ expressions
    def add_expressions(self, root_id: int, names) -> tuple[list[dict], dict]:
        """The game's facial expressions as blend shapes of the parts the face bones move.

        The face has no blend shapes: its expressions are animation clips on about 28 bones (story_clips).
        Each pose is skinned here and stored as the vertex moves it makes - from then on the model has
        ordinary shape keys, in the .blend and (cut into the MMD set by Squad's converter) in the PMX:

            closed_eyes          the lids of the idle clip where they are furthest from rest (its blink)
            <name>_face          the face of every other story clip at its start (smile_face, angry_face ...)
            mouth_talk_a         the talking mouth of the idle face, as a move from that face
            <name>_talk          the talking mouth of another expression, as a move from that expression
            <name>_eyes / _brows one region of a story face, cut by bone group (CUTS)
            mouth_smile / _frown / _wide / _narrow     lip bones posed by recipe (MOUTH_POSES) - not game data
            up_eyes / down_eyes / left_eyes / right_eyes   the eyeball bones turned (GAZE) - not game data

        Returns (what was made, what the PMX converter is told: {role: [shape names]} + "recipes" (which shape
        each MMD morph is, morph_recipes) + "drop" (helper shapes it leaves out of the PMX's own-name list))."""
        root = next((self.nodes[i] for i in self._ordered(root_id)
                     if self.nodes[i]["active"] and "Animator" in self.nodes[i]["types"]
                     and FACE_ROOT.match(self.nodes[i]["name"])), None)
        if root is None:
            return [], {}
        paths, order, stack = {}, [], [(root["id"], "")]
        while stack:
            nid, prefix = stack.pop()
            for child in self.nodes[nid]["children"]:
                path = prefix + self.nodes[child]["name"]
                paths[aa.path_hash(path)] = child
                order.append(child)
                stack.append((child, path + "/"))
        clips = story_clips(self.loader, list(names) + [FACE_ROOT.match(root["name"]).group("who")], set(paths))
        if not clips["face"] and not clips["mouth"]:
            return [], {}

        def pose(sample, only=None):
            return {paths[h]: keyed for h, keyed in sample.items()
                    if h in paths and (only is None or only.search(self.nodes[paths[h]]["name"]))}

        def worlds(*poses):
            """World matrices of the face rig with the poses applied one over the other."""
            keyed = {}
            for p in poses:
                for nid, values in p.items():
                    keyed.setdefault(nid, {}).update(values)
            out = {root["id"]: root["world"]}
            for nid in order:                          # parents come before their children
                node = self.nodes[nid]
                out[nid] = out[node["parent"]] @ posed_local(node["local"], keyed.get(nid, {}))
            return out

        def travel(world):
            return max((float(np.linalg.norm(world[n][:3, 3] - self.nodes[n]["world"][:3, 3])) for n in order), default=0.0)

        rest = worlds()
        shapes = []                                    # (shape name, source text, worlds, worlds it starts from)
        faces = {}
        for label, clip in clips["face"].items():
            start = pose(clip.sample(clip.start))
            if label == "idle":
                times = clip.times()
                lids = [h for h, n in paths.items() if LID.search(self.nodes[n]["name"])]
                first = clip.sample(clip.start)
                moved = [sum(float(np.linalg.norm(np.subtract(s[h]["position"], first[h]["position"])))
                             for h in lids if h in s and "position" in s[h] and h in first)
                         for s in (clip.sample(t) for t in times)]
                if moved and max(moved) > 0.002:
                    t = times[int(np.argmax(moved))]
                    shapes.append((BLINK, "%s at %.2f s" % (clip.name, t), worlds(pose(clip.sample(t), LID)), rest))
                faces[label] = start
                continue
            faces[label] = start
            shapes.append((SHAPE_NAMES.get(label, label + "_face"), clip.name, worlds(start), rest))
        for label, clip in clips["mouth"].items():
            base = faces.get(label, {})
            shapes.append((TALK if label == "idle" else label + "_talk", clip.name,
                           worlds(base, pose(clip.sample(clip.start))), worlds(base)))
        for label, region, bones in CUTS:              # one region of a story face, cut by bone group
            if label != "idle" and label in clips["face"]:
                cut = worlds({n: v for n, v in faces[label].items() if bones.search(self.nodes[n]["name"])})
                if travel(cut) > 3e-4:
                    shapes.append(("%s_%s" % (label, region),
                                   "%s, the %s bones only" % (clips["face"][label].name, region), cut, rest))

        def shifted(moves):
            """World matrices with `moves` ({bone: 4x4 world transform}) applied to those bones and all
            below them."""
            out, applied = {root["id"]: root["world"]}, {}
            for nid in order:
                applied[nid] = moves[nid] if nid in moves else applied.get(self.nodes[nid]["parent"])
                out[nid] = rest[nid] if applied[nid] is None else applied[nid] @ rest[nid]
            return out

        forward = self.forward()
        skinned = {b for part in self.parts for b in part["bones"]}
        rig = [(n, self.nodes[n]["name"], self.nodes[n].get("bone")) for n in order]
        lips = by_side(rig, LIP, skinned)
        if {"L", "R"} <= set(lips):                    # the mouths the game has no clip for (MOUTH_POSES)
            at = {suffix: rest[n][:3, 3] for suffix, n in lips.items()}
            for name, table in MOUTH_POSES.items():
                moves = {}
                for suffix, move in mouth_moves(at, table, forward).items():
                    moves[lips[suffix]] = np.eye(4)
                    moves[lips[suffix]][:3, 3] = move
                shapes.append((name, "lip bones posed by recipe (not game data)", shifted(moves), rest))
        eyes = by_side(rig, EYEBALL, skinned)
        if {"L", "R"} <= set(eyes):                    # looks: the eyeballs turned about their bones (GAZE)
            left = 1.0 if rest[eyes["L"]][0, 3] > rest[eyes["R"]][0, 3] else -1.0
            # left / right as seen from the front, like Squad's own left_eyes (it moves towards the character's right)
            towards = {"up": (0.0, 1.0, 0.0), "down": (0.0, -1.0, 0.0), "left": (-left, 0.0, 0.0), "right": (left, 0.0, 0.0)}
            for name, (direction, degrees) in GAZE.items():
                shapes.append((name, "eyeball bones turned %g degrees %s (not game data)" % (degrees, direction),
                               shifted({n: look_turn(rest[n][:3, 3], forward, towards[direction], degrees)
                                        for n in eyes.values()}), rest))

        bone_node = {n["bone"]: nid for nid, n in self.nodes.items() if "bone" in n}
        made, closed = [], {}                          # closed: {shape: {side: part of the eye's opening it closes}}
        for part in self.parts:
            ids = [bone_node.get(b) for b in part["bones"]]
            if not any(i in rest and i != root["id"] for i in ids):
                continue
            path = os.path.join(self.out_dir, part["npz"])
            arrays = dict(np.load(path))
            first = len(part["shape_keys"])
            inverse = [np.linalg.inv(self.nodes[i]["world"]) if i in rest else None for i in ids]
            moves = []
            for name, source, new, old in shapes:
                change = np.zeros((len(ids), 4, 4))
                for k, i in enumerate(ids):
                    if i in rest:
                        change[k] = (new[i] - old[i]) @ inverse[k]
                moves.append(skin_deltas(arrays["vertices"], arrays["bone_indices"], arrays["bone_weights"], change))
            if not any(float(np.abs(delta).max(initial=0.0)) > 1e-6 for delta in moves):
                continue                               # held by the face rig, moved by nothing (the blush card)
            for (name, source, new, old), delta in zip(shapes, moves):
                if name in (BLINK, "smile_eyes"):
                    closure = eye_closure(arrays["vertices"], arrays["bone_indices"], arrays["bone_weights"],
                                          part["bones"], delta)
                    if closure:
                        closed[name] = closure
                keep = np.linalg.norm(delta, axis=1) > 1e-6
                index = len(part["shape_keys"])
                arrays["shape%d_idx" % index] = np.nonzero(keep)[0].astype(np.int32)
                arrays["shape%d_delta" % index] = delta[keep].astype(np.float32)
                part["shape_keys"].append(name)
                if part is self.parts[0] or not any(m["name"] == name for m in made):
                    made.append({"name": name, "source": source, "bone_travel_mm": round(travel(new) * 1000.0, 1),
                                 "vertices": int(keep.sum()),
                                 "max_mm": round(float(np.linalg.norm(delta, axis=1).max()) * 1000.0, 1) if len(delta) else 0.0})
                else:
                    entry = next(m for m in made if m["name"] == name)
                    entry["vertices"] += int(keep.sum())
            if len(part["shape_keys"]) > first:
                np.savez_compressed(path, **arrays)
        have = {m["name"] for m in made}
        sources = {role: [n for n in wanted if n in have] for role, wanted in (
            ("blink", [BLINK]), ("talk_a", [TALK]), ("shout", [TALK]), ("smile", ["smile_face"]),
            ("angry", ["angry_face"]), ("yell", ["angry_face"]), ("debuff", ["panic_face"]))}
        sources = {role: found for role, found in sources.items() if found}
        smile = closed.get("smile_eyes", {})
        smile_closes = len(smile) == 2 and min(smile.values()) >= SMILE_CLOSES
        sources["recipes"], sources["drop"] = morph_recipes(have, smile_closes)
        sources["eyes_closed_by"] = {name: {side: round(v, 3) for side, v in sides.items()} for name, sides in closed.items()}
        return made, sources

    def forward(self) -> float:
        """+1 when the character faces +Z in the prefab (toes ahead of the feet), else -1."""
        named = {n["name"]: n for n in self.nodes.values()}
        for side in ("L", "R"):
            foot, toe = named.get("Bip001 %s Foot" % side), named.get("Bip001 %s Toe0" % side)
            if foot is not None and toe is not None:
                gap = float(toe["world"][2, 3] - foot["world"][2, 3])
                if abs(gap) > 1e-3:
                    return 1.0 if gap > 0 else -1.0
        return 1.0


def extract_unit(model: dict, out_dir: str, game: ac.Game | None = None, include_inactive: bool = False,
                 expressions: bool = True) -> dict:
    """Write scene.json + parts + textures of one model into out_dir; returns the scene dict."""
    game = game or ac.Game()
    pptr = game.container(model["bundle"]).get(model["key"])
    prefab = game.deref(pptr)
    if prefab is None or prefab.type.name != "GameObject":
        raise RuntimeError("prefab %s not found in the %s bundle" % (model["key"], model["bundle"]))
    scene = Scene(game, out_dir)
    root_id = scene.walk(prefab)
    emotes = scene.add_renderers(root_id, include_inactive)
    expressions, sources = scene.add_expressions(root_id, [model.get("character")]) if expressions else ([], {})
    scene.read_cloth(root_id)
    meta = {"id": model["id"], "name": model["name"], "group": model["group"], "category": model["category"],
            "prefab": model["key"], "bundle": model["bundle"], "game": ac.GAME, "color_space": "gamma",
            "colliders": scene.colliders, "body_bones": BODY_BONES, "emote_parts": emotes,
            "expressions": expressions, "morph_sources": sources}
    data = scene.to_json(root_id, meta)
    tc.save_json(os.path.join(out_dir, "scene.json"), data)
    return data


def unit_details(model: dict, game: ac.Game) -> dict:
    """What list_models.py --details shows: counts read from the prefab without decoding any geometry."""
    prefab = game.deref(game.container(model["bundle"]).get(model["key"]))
    if prefab is None:
        return {"error": "prefab not found"}
    scene = Scene(game, "")
    root_id = scene.walk(prefab)
    info = {"parts": [], "vertices": 0, "triangles": 0, "materials": 0, "shaders": [], "dynamic_bones": 0}
    materials, bones, shaders = set(), set(), set()
    for nid in scene._ordered(root_id):
        node = scene.nodes[nid]
        info["dynamic_bones"] += sum(1 for m in node["monos"] if m == "DynamicBone")
        if not node["active"]:
            continue
        by_type = {c.type.name: c for c in node["components"]}
        if "SkinnedMeshRenderer" in by_type:
            renderer = by_type["SkinnedMeshRenderer"].read()
            mesh_ptr = renderer.m_Mesh
            bones.update(b.m_PathID for b in renderer.m_Bones if not b.m_FileID)
        elif "MeshRenderer" in by_type and "MeshFilter" in by_type:
            renderer = by_type["MeshRenderer"].read()
            mesh_ptr = by_type["MeshFilter"].read().m_Mesh
        else:
            continue
        reader = game.deref(mesh_ptr) if renderer.m_Enabled else None
        if reader is None:
            continue
        tt = reader.read_typetree()
        count = tt["m_VertexData"]["m_VertexCount"] or \
            ((tt.get("m_CompressedMesh") or {}).get("m_Vertices") or {}).get("m_NumItems", 0) // 3
        slots = len(renderer.m_Materials)
        info["parts"].append(node["name"])
        info["vertices"] += count
        info["triangles"] += sum(sm["indexCount"] for i, sm in enumerate(tt["m_SubMeshes"])
                                 if sm["topology"] == 0 and i < slots) // 3
        for m in renderer.m_Materials:
            if not m.m_PathID or (m.m_FileID, m.m_PathID) in materials:
                continue
            materials.add((m.m_FileID, m.m_PathID))
            mat = game.read(m)
            shader = game.read(mat.m_Shader) if mat is not None else None
            parsed = getattr(shader, "m_ParsedForm", None)
            shaders.add(family(getattr(parsed, "m_Name", "") or ""))
    names = [scene.nodes[b]["name"] for b in bones if b in scene.nodes]
    info["materials"] = len(materials)
    info["shaders"] = sorted(shaders)
    info["bones"] = len(bones)
    info["face_bones"] = sum(1 for n in names if re.match(BODY_BONES, n))
    info["biped"] = any(n.endswith(" Pelvis") for n in names)
    return info


if __name__ == "__main__":                             # python ataimanin_scene.py <id> <out dir>: the scene only
    import sys

    models = ac.discover_models()
    target = ac.find_models(models, [sys.argv[1]])[0]
    result = extract_unit(target, sys.argv[2])
    print("%s: %d parts, %d bones, %d materials, cloth %s, breast bones %s, warnings %s" % (
        target["id"], len(result["parts"]), len(result["nodes"]), len(result["materials"]),
        [c["name"] + ":" + "+".join(c["root_bones"]) for c in result["cloth"]], result["breast_bones"],
        result["warnings"]))
    for item in result["expressions"]:
        print("  shape %-16s %-40s bones move %5.1f mm, %5d vertices up to %5.1f mm" % (
            item["name"], item["source"], item["bone_travel_mm"], item["vertices"], item["max_mm"]))
    print("  converter roles:", result["morph_sources"])
    for part in result["parts"]:
        print("  %-22s %-6s verts %6d tris %6d bones %3d materials %s" % (
            part["name"], part["role"], part["vertices"], part["triangles"], len(part["bones"]), part["materials"]))
