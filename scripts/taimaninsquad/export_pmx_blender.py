# -*- coding: utf-8 -*-
"""Taimanin Squad .blend -> MMD .pmx, inside Blender 3.6 (headless).

The units are 3ds Max Biped rigs like Rise of Eros, so the Rise of Eros PMX worker
(scripts/riseoferos/export_character_model_blender.py) is reused function by function: slot
resolution, limb-helper planning, shoulder relax, the 37 degree A-pose, Convert_to_MMD5's
one-click conversion, 付与 grants, body colliders, bust physics, mmd_cloth_physics for the
hair / skirt / ribbon chains, the mmd_tools export at 12.5 and the grant-order check.

What is Taimanin Squad specific, done here around that sequence:

  * the toon .blend is taken apart first (tsquad_blender): outline hull off, every material
    back to its base map, shape-key drivers removed, the hidden emote cards and the weapons
    parked at the origin left out (weapons carried on the body stay, rigid on their bone);
  * breasts: the skinned bones are ``Bone_L_Bust`` / ``Bone_LBreast`` ... (one bone a side,
    simulated by Magica Cloth in the game) -> the chest slots, so they become 左胸 / 右胸 with
    the worker's rigid bodies.  The joints are then rebuilt as sliding springs
    (tsquad_blender.spring_bust): in the game the breast bone is a "Bone Spring" that slides up to
    5 cm around its place with gravity off; the worker's template - a pivot of +-10 degrees
    without a spring - is pressed onto its limit by gravity and shows no bounce at all in a dance
    (measured: 0.06 cm a frame against 0.37).  --bust key=value,... gives the values (export_model.py
    hands over the ones for this unit: tsquad_common.BUST scaled by the unit's own Bone Spring),
    --bust style=swing keeps the template;
  * expressions are real VERTEX morphs.  The game has whole-face blend shapes (closed_eyes,
    smile_face, shouted_face, sad_face, dissatisfied_face ..., eyes up / down / left / right)
    and no visemes, so the standard MMD set is cut out of them by region: the face is split
    into brows / eyes / mouth by height (measured on closed_eyes and the widest-open mouth
    shape) and into left / right at the middle -

        まばたき = closed_eyes            ウィンク２ / ｳｨﾝｸ２右 = its left / right half
        笑い / ウィンク / ウィンク右 = the eyes of the smile when it closes both of them ("^ ^",
            Asagi), else closed_eyes again (Kirara's smile is a wink)
        目上 目下 目左 目右 = the gaze shapes scaled to a look, not a roll: the iris travels 0.2 /
            0.25 of the eye height (at full weight the game shapes turn the eyes white)
        あ = mouth_talk_A, else the mouth of shouted_face;  い う え お mixed from what exists
        にっこり = smile, mouth           口角下げ = sad (else dissatisfied), mouth
        困る = sad (else debuff), brows   怒り = dissatisfied (else shouted), brows

    and every game shape is exported under its own name as well (panel その他);
  * materials get what MMD has for a toon look: the base map, a toon ramp whose shadow colour
    is the material's average tex_s / tex_d ratio, the MatCap as an additive sphere map, and
    the game's outline colour / width as the PMX edge.

  blender -b X.blend --python export_pmx_blender.py -- --out <dir> [--name N] [--model-name M]
          [--comment C] [--keep-weapon] [--bust key=value,...]
Prints TSQ_PMX={json}.  Writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend.
"""
import argparse
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import tempfile

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORKER = os.path.join(REPO, "scripts", "riseoferos", "export_character_model_blender.py")
for extra in (HERE, os.path.join(REPO, "scripts", "blender_addons"), os.path.join(REPO, "scripts", "riseoferos"),
              os.environ.get("BLENDER2XPS", os.path.join(os.path.dirname(os.path.dirname(REPO)), "blender2xps"))):
    if extra not in sys.path:
        sys.path.insert(0, extra)
import tsquad_blender as tb  # noqa: E402

BUST_BONE = re.compile(r"bust|breast", re.IGNORECASE)
BIPED_BONE = re.compile(r"^Bip\d+[ _]")                # Bip001 Spine2, Bip002_B_R Deltoid
# game shape -> the first spelling present wins (lower-case, see the survey in the README).  "a+b" is the
# sum of split shapes: two units keep eyes / mouth apart (138_Orcboss: closed_eyes_L / _R; 16_Asuka Black:
# close_eye_L, smile_eye_L, smile_mouth ...).  The orcs' closed_face is NOT a blink: it shuts the mouth too.
SOURCES = {
    "blink": ("closed_eyes", "closed_eye_face", "close_eyes", "closed_eyes_l+closed_eyes_r", "close_eye_l+close_eye_r"),
    "smile": ("smile_face", "smile_01_face", "smile01_face", "smile1_face", "smile_1_face",
              "smile_eye_l+smile_eye_r+smile_mouth"),
    "shout": ("shouted_face", "shouted_01_face", "shouted01_face", "shouted1_face", "surprised_face",
              "surprised_eye_l+surprised_eye_r+suprised_mouth"),
    "yell": ("shouted_face", "shouted_01_face", "shouted01_face", "shouted1_face"),    # angry brows, never the surprise
    "debuff": ("debuff_face", "debuff_01_face", "debuff1_face", "deburff_face"),
    "sad": ("sad_face", "sad_01_face", "sad1_face", "sorrow_face", "difficult_eye_l+difficult_eye_r+difficult_mouth"),
    "angry": ("dissatisfied_face", "dissatis_face", "dissatisfaction_face", "dissatisfied_01_face",
              "dissatisfied_1_face", "angry_face", "anger_eye_l+anger_eye_r+anger_mouth"),
    "talk_a": ("mouth_talk_a",), "talk_e": ("mouth_talk_e",), "talk_o": ("mouth_talk_o",),
    "up": ("up_eyes",), "down": ("down_eyes",), "left": ("left_eyes",), "right": ("right_eyes",),
}
# shape names tried before those, per role: the .blend's ``tsq_morph_sources`` (main() fills it; shapes made
# from Action Taimanin's expression clips)
MORE_SOURCES = {}
# (MMD name, English name, panel, [(source, strength, region)])
# region: "all", "L" / "R" (the character's left / right half), "eyes" (eye band and up), "mouth", "brows"
# strength ("fit", f): whatever makes the shape's largest travel f x the eye height (Face.fit)
RECIPES = [
    ("まばたき", "blink", "EYE", [("blink", 1.0, "all")]),
    ("笑い", "smile", "EYE", [("blink", 1.0, "all")]),
    ("ウィンク", "wink", "EYE", [("blink", 1.0, "L")]),
    ("ウィンク右", "wink_R", "EYE", [("blink", 1.0, "R")]),
    ("ウィンク２", "wink2", "EYE", [("blink", 1.0, "L")]),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", [("blink", 1.0, "R")]),
    ("あ", "a", "MOUTH", [("talk_a", 1.0, "all")]),
    ("い", "i", "MOUTH", [("talk_e", 0.45, "all"), ("smile", 0.55, "mouth")]),
    ("う", "u", "MOUTH", [("talk_o", 0.8, "all")]),
    ("え", "e", "MOUTH", [("talk_e", 1.0, "all")]),
    ("お", "o", "MOUTH", [("talk_o", 1.0, "all")]),
    ("にっこり", "smile_mouth", "MOUTH", [("smile", 1.0, "mouth")]),
    ("口角下げ", "mouth_corner_down", "MOUTH", [("sad", 1.0, "mouth")]),
    ("困る", "trouble", "EYEBROW", [("sad", 1.0, "brows")]),
    ("怒り", "anger", "EYEBROW", [("angry", 1.0, "brows")]),
    ("目上", "eyes_up", "EYE", [("up", ("fit", 0.20), "all")]),
    ("目下", "eyes_down", "EYE", [("down", ("fit", 0.20), "all")]),
    ("目左", "eyes_left", "EYE", [("left", ("fit", 0.25), "all")]),
    ("目右", "eyes_right", "EYE", [("right", ("fit", 0.25), "all")]),
]
# when the character's smile closes both eyes ("^ ^"), these come from it instead of closed_eyes
SMILE_EYES = {
    "笑い": [("smile", 1.0, "eyes")],
    "ウィンク": [("smile", 1.0, "eyes_L")],
    "ウィンク右": [("smile", 1.0, "eyes_R")],
}
# when the first recipe has no source: the vowels from the mouth of the shout and the smile (most units
# have no talk shapes); brows / mouth corners from the nearest other expression (47 units have no sad
# face, 30 no dissatisfied one - nearly all have debuff and shouted)
FALLBACKS = {                                          # MMD name: alternatives, the first with all its sources wins
    "口角下げ": [[("angry", 1.0, "mouth")]],
    "困る": [[("debuff", 1.0, "brows")]],
    "怒り": [[("yell", 1.0, "brows")]],
    "あ": [[("shout", 1.0, "mouth")]],
    "い": [[("shout", 0.25, "mouth"), ("smile", 0.6, "mouth")], [("shout", 0.3, "mouth")]],
    "う": [[("shout", 0.3, "mouth")]],
    "え": [[("shout", 0.5, "mouth"), ("smile", 0.35, "mouth")], [("shout", 0.5, "mouth")]],
    "お": [[("shout", 0.65, "mouth")]],
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- rig
def resolve_slots(roe, arm, meshes):
    """The worker's Biped table + the breast bones.  Which bones those are comes from the game: the
    roots of the Magica Cloth group "Breast" (build_blend.py keeps the list on the armature) - they are
    called Bone_L_Bust, Bone_LBreast or Bip001 Xtra01 / Xtra01Opp depending on the rig."""
    slots, missing = roe.resolve_roe_slots(arm)
    weighted = roe.weighted_bones(meshes)
    try:
        listed = json.loads(arm.get("tsq_breast_bones", "") or "[]")
    except ValueError:
        listed = []
    names = [n for n in listed if n in arm.data.bones] or [
        b.name for b in arm.data.bones
        if BUST_BONE.search(b.name) and not (b.parent is not None and BUST_BONE.search(b.parent.name))]
    # Left and right of THIS skeleton's middle, and the bones that hang on it before any other.
    # 58_YuphieSophie is two characters side by side in one unit (Bip001 and Bip002): measured from the
    # world's middle, both of Yuphie's breasts were "right" - her left one became 右胸 and the other got no
    # physics at all.  (b_13_Thursday's breasts hang on her second Biped and there are no others: kept.)
    main = (slots.get("lower_body_bone") or "").split(" ")[0]
    spine = arm.data.bones.get(slots.get("upper_body_bone") or slots.get("lower_body_bone") or "")
    middle = (arm.matrix_world @ spine.head_local).x if spine is not None else 0.0

    def on_main_skeleton(name):
        owner = arm.data.bones[name].parent
        while owner is not None and not BIPED_BONE.match(owner.name):
            owner = owner.parent
        return owner is None or not main or owner.name.split(" ")[0].split("_")[0] == main

    names = [n for n in names if n in weighted]
    names = [n for n in names if on_main_skeleton(n)] or names
    sides = {"left": None, "right": None}
    for name in names:
        x = (arm.matrix_world @ arm.data.bones[name].head_local).x
        side = "left" if x > middle else "right"       # +X is the character's left
        if sides[side] is None:
            sides[side] = name
    for side, name in sides.items():
        if name:
            slots["%s_chest_bone" % side] = name
    # eyeball bones of a face rigged with bones (Action Taimanin: Bone_Eyeball_L / _R; Squad has none)
    for side, key in (("L", "left_eye_bone"), ("R", "right_eye_bone")):
        if key in slots and not slots[key]:
            slots[key] = next((b.name for b in arm.data.bones
                               if EYE_BONE.search(b.name) and b.name.endswith("_" + side) and b.name in weighted), "")
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


EYE_BONE = re.compile(r"eye_?ball", re.IGNORECASE)


LIMB_ALIAS = re.compile(r"^Bone_?([LR])_?(Thigh|Calf|UpperArm|Forearm)$", re.IGNORECASE)
ALIAS_SLOT = {"thigh": "thigh_bone", "calf": "calf_bone", "upperarm": "upper_arm_bone", "forearm": "lower_arm_bone"}


def merge_limb_aliases(arm, meshes, slots, reach=0.03):
    """Hand the skin of ``Bone_L_Thigh`` / ``Bone_L_Calf`` ... to the Biped bone they lie on.

    Five early characters (Asagi, Shiranui, Asuka, Asuka Black, Oboro) do not skin the legs to the
    Biped: a second chain ``Bone_L_Thigh > Bone_L_Knee_end > Bone_L_Calf`` hangs under ``Bip001 L Thigh``
    and carries the whole thigh and shin; in the game its bones are keyed by every animation to lie on
    the Biped leg.  Nothing keys them in MMD: the shin would stay a rigid child of the thigh chain and
    never bend at the knee (Asagi's foot left her straight leg in the dance preview).  The two chains
    coincide in the bind pose, so the Biped bone can simply take the weights; the alias bone stays as
    an empty leaf.  Only a bone whose head is within 3 cm of that Biped bone's head is merged."""
    merged = []
    for bone in arm.data.bones:
        match = LIMB_ALIAS.match(bone.name)
        if match is None:
            continue
        side = "left" if match.group(1).upper() == "L" else "right"
        target = arm.data.bones.get(slots.get("%s_%s" % (side, ALIAS_SLOT[match.group(2).lower()])) or "")
        if target is None or target.name == bone.name or (bone.head_local - target.head_local).length > reach:
            continue
        count = 0
        for mesh in meshes:
            source = mesh.vertex_groups.get(bone.name)
            if source is None:
                continue
            dest = mesh.vertex_groups.get(target.name) or mesh.vertex_groups.new(name=target.name)
            for vertex in mesh.data.vertices:
                for item in vertex.groups:
                    if item.group == source.index and item.weight > 0.0:
                        dest.add([vertex.index], item.weight, "ADD")
                        count += 1
            mesh.vertex_groups.remove(source)
        if count:
            merged.append("%s -> %s (%d weights)" % (bone.name, target.name, count))
    return merged


# ---------------------------------------------------------------- expressions
def _coords(data):
    out = np.empty(len(data) * 3, dtype=np.float64)
    data.foreach_get("co", out)
    return out.reshape(-1, 3)


def smoothstep(lo, hi, x):
    t = np.clip((x - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def islands(mesh):
    """Connected-component label per vertex (union-find over the edges)."""
    parent = np.arange(len(mesh.vertices))
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", edges)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    roots = np.array([find(i) for i in range(len(parent))])
    _u, label = np.unique(roots, return_inverse=True)
    return label


class Face:
    """The meshes that carry shape keys, their rest coordinates and per-key deltas."""

    def __init__(self, meshes):
        self.meshes = [m for m in meshes if m.data.shape_keys and len(m.data.shape_keys.key_blocks) > 1]
        self.base, self.delta, self.overlay, self.island = {}, {}, {}, {}
        for m in self.meshes:
            keys = m.data.shape_keys.key_blocks
            base = _coords(keys[0].data)
            self.base[m.name] = (m.matrix_world.to_3x3(), np.array([m.matrix_world @ Vector(c) for c in base]), base)
            for kb in keys[1:]:
                self.delta[(m.name, kb.name.lower())] = _coords(kb.data) - base
            # the blush / gloom / tear cards (the unlit overlay material) hide inside the head and are
            # pushed out by whole-face shapes: they belong to those, not to a brow or mouth morph
            unlit = {i for i, slot in enumerate(m.material_slots)
                     if slot.material is not None and slot.material.get("tsq_kind") == "unlit"}
            hidden = np.zeros(len(base), dtype=bool)
            if unlit:
                shown = np.zeros(len(base), dtype=bool)
                for poly in m.data.polygons:
                    (hidden if poly.material_index in unlit else shown)[list(poly.vertices)] = True
                hidden &= ~shown
            self.overlay[m.name] = hidden
            self.island[m.name] = islands(m.data)
        self.names = sorted({k[1] for k in self.delta})
        for alternatives in SOURCES.values():          # the sums of split shapes, under their "a+b" name
            for name in alternatives:
                parts = name.split("+")
                if len(parts) < 2 or name in self.names or not all(p in self.names for p in parts):
                    continue
                for m in self.meshes:
                    found = [self.delta[(m.name, p)] for p in parts if (m.name, p) in self.delta]
                    if found:
                        self.delta[(m.name, name)] = np.sum(found, axis=0)
                self.names.append(name)
        self._cards, self._kept = {}, {}
        self.skin = None                               # (mesh name, vertex mask): the biggest connected piece
        for m in self.meshes:
            counts = np.bincount(self.island[m.name])
            if self.skin is None or counts.max() > self.skin[2]:
                self.skin = (m.name, self.island[m.name] == int(counts.argmax()), int(counts.max()))

    def depth(self, points, key_name=None):
        """How deep inside the head the world points lie (m): + = behind the facial skin along the view
        axis (the character faces -Y), against the four skin vertices nearest in the frontal plane.
        With key_name the skin is taken in that shape."""
        name, sel, _count = self.skin
        rot, world, _base = self.base[name]
        skin = world[sel]
        if key_name is not None and (name, key_name) in self.delta:
            skin = skin + self.delta[(name, key_name)][sel] @ np.array(rot).T
        out = np.empty(len(points))
        for i, p in enumerate(points):
            d2 = (skin[:, 0] - p[0]) ** 2 + (skin[:, 2] - p[2]) ** 2
            near = np.argpartition(d2, min(4, len(d2) - 1))[:4]
            w = 1.0 / (d2[near] + 1e-8)
            out[i] = p[1] - float((skin[near, 1] * w).sum() / w.sum())
        return out

    def cards(self, mesh_name, key_name, travel=0.008, hidden=0.008, shown=0.006):
        """Vertices of the pop-out cards of this shape: sweat drops, tears, anger marks - small pieces
        parked inside the head and flown to the surface by ONE whole-face expression.  A card travels as
        a whole (every vertex over 8 mm), starts hidden (over 8 mm behind the skin) and ends on the skin
        (within 6 mm, or 0.4 of the depth it started at).  Brows, the closed-mouth line (pulled in when
        the mouth opens) and the teeth travel as wholes too, but they start on the surface or stay
        inside: those are the face itself."""
        key = (mesh_name, key_name)
        if key not in self._cards:
            d = self.delta.get(key)
            label = self.island[mesh_name]
            out = np.zeros(len(label), dtype=bool)
            if d is not None and self.skin is not None:
                rot, world, _base = self.base[mesh_name]
                moved = d @ np.array(rot).T
                mag = np.linalg.norm(d, axis=1)
                least = np.full(label.max() + 1, np.inf)
                np.minimum.at(least, label, mag)
                for i in np.nonzero(least > travel)[0]:
                    sel = label == i
                    rest = world[sel].mean(axis=0)
                    dest = rest + moved[sel].mean(axis=0)
                    deep = self.depth([rest])[0]
                    if deep > hidden and self.depth([dest], key_name)[0] < max(shown, 0.4 * deep):
                        out |= sel
            self._cards[key] = out
        return self._cards[key]

    def kept_hidden(self, mesh_name, key_name, hidden=0.008):
        """Overlay pieces this shape moves WITHOUT showing them: parked inside the head, and still inside
        (over 8 mm behind the skin) where the shape puts them.  Hebiko's shout sends the "ε" mouth mark
        30 mm further in - it rests right behind the lips and would be seen through the open mouth.  A
        region cut from the shape has to take such pieces along, or the cut shows what the game hides."""
        key = (mesh_name, key_name)
        if key not in self._kept:
            d = self.delta.get(key)
            label, overlay = self.island[mesh_name], self.overlay[mesh_name]
            out = np.zeros(len(label), dtype=bool)
            if d is not None and self.skin is not None and overlay.any():
                rot, world, _base = self.base[mesh_name]
                moved = d @ np.array(rot).T
                mag = np.linalg.norm(d, axis=1)
                cards = self.cards(mesh_name, key_name)
                for i in np.unique(label[overlay]):
                    sel = label == i
                    if not overlay[sel].all() or cards[sel].any() or mag[sel].max() < 3e-4:
                        continue
                    rest = world[sel].mean(axis=0)
                    dest = rest + moved[sel].mean(axis=0)
                    if self.depth([rest])[0] > hidden and self.depth([dest], key_name)[0] > hidden:
                        out |= sel
            self._kept[key] = out
        return self._kept[key]

    def source(self, role):
        return next((n for n in MORE_SOURCES.get(role, ()) + SOURCES[role] if n in self.names), None)

    def measure(self):
        """Heights that split the face: bottom / top of the eyes (closed_eyes), the mouth (the widest
        opening shape).  None when the model has no blink shape."""
        blink = self.source("blink")
        if blink is None:
            return None
        zs, xs = [], []
        for m in self.meshes:
            d = self.delta.get((m.name, blink))
            if d is None:
                continue
            world = self.base[m.name][1]
            # not the cards a shape flies in from their parking place (Ingrid's closed_eyes: 61 mm)
            moved = (np.linalg.norm(d, axis=1) > 3e-4) & ~self.overlay[m.name] & ~self.cards(m.name, blink)
            zs.append(world[moved, 2])
            xs.append(world[moved, 0])
        zs, xs = np.concatenate(zs), np.concatenate(xs)
        if len(zs) < 8:
            return None
        eye_lo, eye_hi = float(np.percentile(zs, 2)), float(np.percentile(zs, 98))
        centre = float((np.percentile(xs, 2) + np.percentile(xs, 98)) * 0.5)
        mouth = None
        for role in ("talk_a", "shout", "smile", "sad"):
            name = self.source(role)
            if name is None:
                continue
            pts, wts = [], []
            for m in self.meshes:
                d = self.delta.get((m.name, name))
                if d is None:
                    continue
                world = self.base[m.name][1]
                mag = np.where(self.overlay[m.name] | self.cards(m.name, name), 0.0, np.linalg.norm(d, axis=1))
                low = world[:, 2] < eye_lo - 0.2 * (eye_hi - eye_lo)
                pts.append(world[low, 2])
                wts.append(mag[low])
            pts, wts = np.concatenate(pts), np.concatenate(wts)
            if wts.sum() > 1e-6:
                mouth = float((pts * wts).sum() / wts.sum())
                break
        if mouth is None:
            mouth = eye_lo - 2.2 * (eye_hi - eye_lo)
        return {"eye_lo": eye_lo, "eye_hi": eye_hi, "mouth": mouth, "centre": centre}

    def region(self, mesh_name, which, m, overlay=False):
        """Per-vertex weight 0..1 of a face region; 0 on the overlay cards unless `overlay`."""
        world = self.base[mesh_name][1]
        z, x = world[:, 2], world[:, 0]
        if which == "all" or m is None:
            return np.ones(len(z))
        gap = max(m["eye_lo"] - m["mouth"], 1e-3)
        eye_h = max(m["eye_hi"] - m["eye_lo"], 1e-3)
        upper = smoothstep(m["eye_lo"] - 0.45 * gap, m["eye_lo"] - 0.15 * gap, z)      # 1 above the cheeks
        brow = smoothstep(m["eye_hi"] + 0.05 * eye_h, m["eye_hi"] + 0.45 * eye_h, z)   # 1 above the upper lid
        left = smoothstep(m["centre"] - 0.004, m["centre"] + 0.004, x)                 # +X = the character's left
        weight = {"mouth": 1.0 - upper, "brows": brow, "eyes": upper, "L": left, "R": 1.0 - left,
                  "eyes_L": upper * left, "eyes_R": upper * (1.0 - left)}[which]
        return weight if overlay else np.where(self.overlay[mesh_name], 0.0, weight)

    def smile_closes_eyes(self, measure):
        """True when the smile shape closes BOTH eyes (Asagi's smile_01 is "^ ^"; Kirara's is a wink):
        each side's eye movement in the smile, projected on closed_eyes, is at least half of it."""
        smile, blink = self.source("smile"), self.source("blink")
        if not smile or not blink or measure is None:
            return False
        for side in ("L", "R"):
            num = den = 0.0
            for m in self.meshes:
                ds, db = self.delta.get((m.name, smile)), self.delta.get((m.name, blink))
                if ds is None or db is None:
                    continue
                w = self.region(m.name, side, measure)[:, None]
                num += float((ds * db * w).sum())
                den += float((db * db * w).sum())
            if den < 1e-12 or num / den < 0.5:
                return False
        return True

    def fit(self, name, fraction, measure):
        """The strength at which the shape's largest travel is `fraction` of the eye height.  The gaze
        shapes are rolls (24 - 28 mm, the iris leaves the eye); 0.2 of the eye height up / down and
        0.25 sideways is a clear look that keeps the iris in sight (measured on Kirara and Asagi)."""
        size = max((float(np.linalg.norm(d, axis=1).max()) for (_m, k), d in self.delta.items() if k == name),
                   default=0.0)
        if measure is None or size < 1e-6:
            return 0.2
        return min(1.0, fraction * (measure["eye_hi"] - measure["eye_lo"]) / size)

    def mix(self, parts, measure):
        """{mesh name: delta array} for a list of (source role, strength, region); None if a source is absent."""
        out, used = {}, False
        for role, strength, which in parts:
            name = self.source(role)
            if name is None:
                return None
            if isinstance(strength, tuple):
                strength = self.fit(name, strength[1], measure)
            for m in self.meshes:
                d = self.delta.get((m.name, name))
                if d is None:
                    continue
                w = self.region(m.name, which, measure)
                if which in ("mouth", "brows"):        # a cut-out region takes no pop-out cards along
                    w = np.where(self.cards(m.name, name), 0.0, w)
                kept = self.kept_hidden(m.name, name) if which != "all" and measure is not None else None
                if kept is not None and kept.any():    # ... but what the shape keeps out of sight goes with
                    raw = self.region(m.name, which, measure, overlay=True)     # the region it rests in,
                    label = self.island[m.name]                                 # each piece as a whole
                    for i in np.unique(label[kept]):
                        sel = label == i
                        w = np.where(sel, float(raw[sel].mean()), w)
                out[m.name] = out.get(m.name, 0.0) + d * (strength * w)[:, None]
                used = True
        return out if used else None


def build_morphs(root, meshes):
    """Add the standard MMD morphs as shape keys, register every key with mmd_tools.  Returns a report."""
    face = Face(meshes)
    report = {"game_shapes": face.names, "made": [], "skipped": []}
    if not face.meshes:
        return report
    measure = face.measure()
    report["regions"] = {k: round(v, 4) for k, v in (measure or {}).items()}
    made = []
    happy = face.smile_closes_eyes(measure)
    report["smile_closes_eyes"] = happy
    for jp, en, panel, parts in RECIPES:
        if happy and jp in SMILE_EYES:
            parts = SMILE_EYES[jp]
        deltas = face.mix(parts, measure) if (measure or all(p[2] == "all" for p in parts)) else None
        how = "game" if all(p[2] == "all" and p[1] == 1.0 for p in parts) else "cut from the game's"
        used_parts = parts
        if deltas is None and measure:
            for alternative in FALLBACKS.get(jp, []):
                deltas = face.mix(alternative, measure)
                if deltas is not None:
                    how, used_parts = "approximated", alternative
                    break
        if deltas is None:
            report["skipped"].append(jp)
            continue
        size = max(float(np.linalg.norm(d, axis=1).max()) for d in deltas.values())
        if size < 2e-4:
            report["skipped"].append(jp + " (empty)")
            continue
        for m in face.meshes:
            d = deltas.get(m.name)
            if d is None or float(np.abs(d).max()) < 1e-6:
                continue
            kb = m.shape_key_add(name=jp, from_mix=False)
            kb.data.foreach_set("co", (face.base[m.name][2] + d).ravel())
            kb.value = 0.0
        made.append((jp, en, panel))
        report["made"].append("%s (%s: %s, %.1f mm)" % (
            jp, how, " + ".join(face.source(p[0]) or "?" for p in used_parts), size * 1000.0))
    # the pop-out cards left out of the cut regions: "mesh/shape": vertices
    report["cards"] = {"%s/%s" % key: int(mask.sum()) for key, mask in face._cards.items() if mask.any()}
    # the hidden pieces that went along with a cut region (the shape moves them, they stay inside the head)
    report["kept_hidden"] = {"%s/%s" % key: int(mask.sum()) for key, mask in face._kept.items() if mask.any()}
    mmd = root.mmd_root
    have = {item.name for item in mmd.vertex_morphs}
    for jp, en, panel in made:
        if jp not in have:
            item = mmd.vertex_morphs.add()
            item.name = jp
        item = mmd.vertex_morphs[mmd.vertex_morphs.find(jp)]
        item.name_e, item.category = en, panel
    standard = {m[0] for m in made}
    for m in face.meshes:                              # the game's own shapes, under their own names
        for kb in m.data.shape_keys.key_blocks[1:]:
            if kb.name in standard or kb.name in have:
                continue
            item = mmd.vertex_morphs.add()
            item.name = item.name_e = kb.name
            item.category = "OTHER"
            have.add(kb.name)
    for target, (jp, _en, _panel) in enumerate(made):  # standard names first, in RECIPES order
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(jp), target)
    try:
        from mmd_tools.operators.display_item import DisplayItemQuickSetup
        if "表情" in mmd.display_item_frames:
            mmd.display_item_frames["表情"].data.clear()
        DisplayItemQuickSetup.load_facial_items(mmd)
    except Exception as exc:  # noqa: BLE001
        report["display_frame"] = "not rebuilt: %s" % exc
    report["vertex_morphs"] = [item.name for item in mmd.vertex_morphs]
    return report


# ---------------------------------------------------------------- materials
def shade_ratio(base_img, shade_img):
    """Average tex_s / tex_d over the texels that are drawn: the colour MMD's toon ramp multiplies in."""
    if base_img is None or shade_img is None:
        return None
    a, b = tb.image_pixels(base_img), tb.image_pixels(shade_img)
    if a.shape != b.shape:
        step_a = max(1, a.shape[0] // 256)
        step_b = max(1, b.shape[0] // 256)
        a, b = a[::step_a, ::step_a], b[::step_b, ::step_b]
        if a.shape != b.shape:
            return None
    mask = (a[..., 3] > 0.5) & (a[..., :3].max(axis=2) > 0.08)
    if mask.sum() < 16:
        return None
    lit, dark = a[..., :3][mask].mean(axis=0), b[..., :3][mask].mean(axis=0)
    return np.clip(dark / np.maximum(lit, 1e-4), 0.0, 1.0)


def toon_png(path, color):
    """A 32 x 32 MMD toon ramp: white above, the shadow colour below, a short blend between."""
    h = w = 32
    rows = np.ones((h, w, 4), dtype=np.float32)
    for y in range(h):                                 # row 0 is the BOTTOM of the image in Blender
        t = np.clip((y / (h - 1) - 0.42) / 0.16, 0.0, 1.0)
        rows[y, :, :3] = np.asarray(color) * (1.0 - t) + t
    return tb.save_png(path, rows)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def srgb_to_linear(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, None)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def mask_coverage(meshes, mat, image, channel=2):
    """Mean of one channel of a mask picture over the UVs of the faces that use `mat`: the share of the
    material the game's mask lets an effect onto (tex_m blue = MatCap).  1.0 without a mask."""
    if image is None:
        return 1.0
    px = tb.image_pixels(image)
    h, w = px.shape[:2]
    total, count = 0.0, 0
    for obj in meshes:
        me = obj.data
        index = {i for i, slot in enumerate(obj.material_slots) if slot.material == mat}
        if not index or not me.uv_layers:
            continue
        loops = [li for p in me.polygons if p.material_index in index for li in p.loop_indices]
        if not loops:
            continue
        uv = np.empty(len(me.loops) * 2)
        me.uv_layers[0].data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)[loops]
        u = np.clip((uv[:, 0] % 1.0) * w, 0, w - 1).astype(int)
        v = np.clip((uv[:, 1] % 1.0) * h, 0, h - 1).astype(int)
        total += float(px[v, u, channel].sum())
        count += len(loops)
    return total / count if count else 1.0


def setup_materials(meshes, tex_dir):
    """MMD values for every material from the game's record kept on it (tsq_spec)."""
    from mmd_tools.core.material import FnMaterial

    os.makedirs(tex_dir, exist_ok=True)
    images = {os.path.basename(bpy.path.abspath(i.filepath)).lower(): i for i in bpy.data.images if i.filepath}
    report = {"toon": [], "sphere": [], "edge": [], "hidden": []}
    done = set()
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name in done:
                continue
            done.add(mat.name)
            mm = mat.mmd_material
            spec = tb.material_spec(mat)
            floats, colors = spec.get("floats", {}), spec.get("colors", {})
            textures, kw = spec.get("textures", {}), set(spec.get("keywords", []))
            mm.diffuse_color = (1.0, 1.0, 1.0)
            mm.ambient_color = (0.6, 0.6, 0.6)
            if not any(textures.get(p) for p in ("_BaseMap", "_MainTex", "_MainTexture")):
                tint = colors.get("_BaseColor") or colors.get("_Color") or colors.get("_TintColor")
                if tint:                               # no picture: the colour is all there is (FX_Black)
                    mm.diffuse_color = tuple(max(0.0, min(1.0, float(c))) for c in tint[:3])
                    mm.ambient_color = tuple(0.6 * c for c in mm.diffuse_color)
            mm.specular_color = (0.0, 0.0, 0.0)
            mm.shininess = 5.0
            mm.is_double_sided = not mat.use_backface_culling
            width = float(mat.get("tsq_outline_width", 0.0) or 0.0)
            mm.enabled_toon_edge = width > 0.0
            if width > 0.0:
                c = list(mat.get("tsq_outline_color", (0.0, 0.0, 0.0)))
                mm.edge_color = (c[0], c[1], c[2], 1.0)
                mm.edge_weight = max(0.2, min(2.0, width * 0.5))   # _Outline_Width 2 (mm) = MMD edge 1.0
                report["edge"].append(mat.name)
            if mat.get("tsq_kind") == "unlit":                      # the hidden face overlays (blush, gloom)
                mm.enabled_self_shadow = mm.enabled_self_shadow_map = mm.enabled_drop_shadow = False
                mm.enabled_toon_edge = False
                continue
            if mat.get("tsq_kind") != "toon":
                continue

            def img(prop):
                info = textures.get(prop)
                return images.get(info["file"].lower()) if info else None

            # Colours here are DISPLAY values: Image.pixels of an 8-bit picture and the game's colour
            # properties are sRGB-encoded, and MMD multiplies / adds what it is given as it is.
            # "hints": the same facts worked out by the extraction for another game's shaders
            # (scripts/actiontaimanin/ataimanin_scene.hints) - the shadow tint, the sphere map and its mask.
            hints = spec.get("hints") or {}
            ratio = None
            if hints.get("shade"):
                ratio = np.clip(np.array(hints["shade"], dtype=float), 0.0, 1.0)
            elif "_SHADOWCOLOR" in kw:                 # two tinted steps of the albedo: use the first
                c = colors.get("_Shadow1Color")
                if c:
                    ratio = np.clip(np.array([float(c[0]), float(c[1]), float(c[2])]), 0.0, 1.0)
            else:
                ratio = shade_ratio(img("_BaseMap"), img("_InShadowMap"))
                if ratio is not None:                  # the shadow picture is not tinted, the base map is
                    base_tint = np.array((colors.get("_BaseColor") or [1.0, 1.0, 1.0])[:3], dtype=float)
                    ratio = np.clip(ratio / np.maximum(base_tint, 1e-3), 0.0, 1.0)
            if ratio is not None:
                path = toon_png(os.path.join(tex_dir, "toon_%s.png" % safe(mat.name)), ratio)
                mm.is_shared_toon_texture = False
                mm.toon_texture = path
                report["toon"].append("%s (%.2f %.2f %.2f)" % (mat.name, *ratio))
            sphere = hints.get("sphere")
            matcap = images.get(sphere["file"].lower()) if sphere else img("_MatCapMap")
            if sphere and matcap is not None:
                # a gamma-space shader: matcap x colour x mask.G (+ level) on display values as they are
                mask = sphere.get("mask") or {}
                cover = mask_coverage(meshes, mat, images.get(mask["file"].lower()) if mask else None,
                                      mask.get("channel", 1))
                cover = min(max(cover + float(sphere.get("level", 0.0)), 0.0), 1.0)
                px = tb.image_pixels(matcap).copy()
                px[..., :3] = np.clip(px[..., :3] * np.array(sphere["color"][:3], dtype=float) * cover, 0.0, 1.0)
                if sphere.get("mode") == "multiply":    # multiplied where the mask lets it: white elsewhere
                    px[..., :3] = 1.0 - cover + px[..., :3]
                px[..., 3] = 1.0
                path = tb.save_png(os.path.join(tex_dir, "sph_%s.png" % safe(mat.name)), px)
                FnMaterial(mat).create_sphere_texture(path)
                mm.sphere_texture_type = "1" if sphere.get("mode") == "multiply" else "2"
                report["sphere"].append("%s (x%.2f)" % (mat.name, cover))
            elif "_MATCAP" in kw and matcap is not None:
                px = tb.image_pixels(matcap).copy()
                tint = colors.get("_MatCapColor", [1, 1, 1, 1])
                lin = np.array([tb_srgb(tint[0]), tb_srgb(tint[1]), tb_srgb(tint[2])])
                # the shader adds matcap x _MatCapColor x mask.B in linear light: decode the picture,
                # scale by the colour and by how much of this material the mask covers, encode again
                cover = mask_coverage(meshes, mat, img("_MaskMap"))
                px[..., :3] = linear_to_srgb(srgb_to_linear(px[..., :3]) * lin * cover)
                px[..., 3] = 1.0
                path = tb.save_png(os.path.join(tex_dir, "sph_%s.png" % safe(mat.name)), px)
                FnMaterial(mat).create_sphere_texture(path)
                mm.sphere_texture_type = "2"            # additive, like the shader's "+ matcap"
                report["sphere"].append("%s (x%.2f)" % (mat.name, cover))
    return report


def tb_srgb(c):
    c = max(0.0, float(c))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def safe(text):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("_") or "x"


def teach_cloth_names():
    """mmd_cloth_physics picks a garment's preset from its bone names, and three units of this game spell
    the skirt ``Skrit`` (24_Kirara, 86_Robel, 248_Mari): no hint matched and the skirt panels were built
    as floppy "ribbons".  For this run only - the add-on's files are not touched - the misspelling counts
    as a skirt.  Returns a note for the report."""
    try:
        from mmd_cloth_physics import analyze
    except ImportError:
        return "mmd_cloth_physics is not installed"
    if not getattr(analyze, "_tsq_taught", False):
        analyze.NAME_HINTS = tuple((pattern + "|skrit|skrt" if preset == "skirt" else pattern, preset)
                                   for pattern, preset in analyze.NAME_HINTS)
        analyze._tsq_taught = True
    return "skrit = skirt"


def teach_dynamic_hair(arm):
    """The add-on leaves the bones under the head alone unless their name says hair (they could be the face).
    Action Taimanin's hair chains have no such name (``Bone136`` ... ``Bone141`` is Asagi's long hair) - but
    the game says which chains swing: the roots of its Dynamic Bone components, kept on the armature
    (``tsq_cloth``).  For this run those bones count as hair.  Returns their names."""
    try:
        from mmd_cloth_physics import analyze
        groups = json.loads(arm.get("tsq_cloth", "") or "[]")
    except (ImportError, ValueError):
        return []
    names = []
    for group in groups:
        if group.get("kind") != "dynamic_bone" or group.get("name") == "Breast":
            continue
        for root in group.get("root_bones") or []:
            bone = arm.data.bones.get(root)
            if bone is None or not any(re.search(r"\b(Head|Neck)\b", p.name) for p in bone.parent_recursive):
                continue
            names += [b.name for b in [bone] + list(bone.children_recursive)
                      if b.name not in names and not analyze.HAIR_NAME.search(b.name)]
    if names and not getattr(analyze, "_tsq_hair", False):
        pattern = analyze.NAME_HINTS[0][0] + "|" + "|".join(r"\b%s\b" % re.escape(n) for n in names)
        analyze.NAME_HINTS = ((pattern, analyze.NAME_HINTS[0][1]),) + tuple(analyze.NAME_HINTS[1:])
        analyze.HAIR_NAME = re.compile(pattern, re.IGNORECASE)
        analyze._tsq_hair = True
    return names


def every_biped_is_body(more=""):
    """58_YuphieSophie is two characters in one unit: a second 3ds Max Biped (``Bip002 ...``) stands next to
    the one the MMD skeleton is made of.  The worker tells mmd_cloth_physics that the body is ``^Bip001\\b``
    and that add-on takes every other chain of skinned bones for a garment - the whole second character
    became cloth and collapsed (5 m of drift in the rest test, 93 m in a dance).  For this run the body is
    every Biped, and what `more` matches (the .blend's ``tsq_body_bones``: Action Taimanin's face bones);
    the add-on's files are not touched.  Returns a note for the report."""
    try:
        from mmd_cloth_physics import api
    except ImportError:
        return "mmd_cloth_physics is not installed"
    if not getattr(api, "_tsq_bipeds", False):
        original = api.setup
        body = r"^Bip\d+\b" + ("|" + more if more else "")

        def setup(obj, *args, body_regex=None, **kwargs):
            if body_regex and re.match(r"\^Bip\d+", body_regex):
                body_regex = body
            return original(obj, *args, body_regex=body_regex, **kwargs)

        api.setup = setup
        api._tsq_bipeds = True
    return "every Biped is body" + (", and %s" % more if more else "")


def plain_mmd_model(arm):
    """An MMD model around a rig that is no human figure: mmd_tools' own conversion.  The standard MMD
    skeleton (IK legs, twist arms) needs two legs and two arms to map onto; without them the bones stay
    the game's, under the game's names, and nothing is simulated.  Returns the MMD root object."""
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    done = bpy.ops.mmd_tools.convert_to_mmd_model()
    root = arm.parent
    if done != {"FINISHED"} or root is None or getattr(root, "mmd_type", "") != "ROOT":
        raise RuntimeError("mmd_tools could not make an MMD model of the rig: %r" % (done,))
    return root


# ---------------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    ap.add_argument("--keep-weapon", action="store_true")
    ap.add_argument("--bust", default="", help="breast physics: key=value,... (tsquad_common.BUST), applied as given")
    args = ap.parse_args(argv)
    bust = tb.parse_bust(args.bust)

    roe = load(WORKER, "roe_char_worker")
    if "bust" not in inspect.signature(roe.convert_rig_to_mmd).parameters:
        # the breast bodies and the collider fixes are the worker's; spring_bust only turns its joints into springs
        raise SystemExit("the PMX worker %s has no breast physics (convert_rig_to_mmd takes no 'bust'): "
                         "this step needs the version of the worker that has it" % WORKER)
    from ff7_face_morphs import core as shape_keys     # stash / restore: generic, despite the name

    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath}

    arm, meshes, removed = tb.scene_parts(keep_weapon=args.keep_weapon)
    game = arm.get("tsq_game", "") or "Taimanin Squad"
    try:
        MORE_SOURCES.update({role: tuple(n.lower() for n in names)
                             for role, names in json.loads(arm.get("tsq_morph_sources", "") or "{}").items()
                             if role in SOURCES})
    except ValueError:
        pass
    report["weapons_left_out"] = removed
    report["outline_modifiers_removed"] = tb.strip_outline(meshes)
    report["shape_key_drivers_removed"] = tb.clear_shape_key_drivers(meshes)
    report["plain_materials"] = len(tb.plain_materials(meshes))
    if os.path.isdir(out_dir):                          # a generated folder: start clean
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    unpack_dir = tempfile.mkdtemp(prefix="tsq_pmx_images_")
    report["unpacked_images"] = tb.unpack_images_to(unpack_dir)

    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    slots, missing_optional = resolve_slots(roe, arm, meshes)
    report["missing_optional_slots"] = missing_optional
    report["chest_bones"] = [slots.get("left_chest_bone", ""), slots.get("right_chest_bone", "")]
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    report["merged_limb_aliases"] = merge_limb_aliases(arm, meshes, slots)
    weighted = roe.weighted_bones(meshes)
    keep = {v for v in slots.values() if v}
    off = [b.name for b in arm.data.bones if b.use_deform and b.name not in weighted and b.name not in keep]
    for bone_name in off:                               # sockets / chain ends: must not inherit weight
        arm.data.bones[bone_name].use_deform = False
    report["undeformed_skinless"] = len(off)

    before = roe.edge_lengths(meshes)
    try:
        roe.bake_rig_transforms(arm, meshes)
    except RuntimeError as exc:                         # its last line tests "taller than deep" - a boss in a
        if "Z-up" not in str(exc):                      # six-metre tentacle skirt is not; our .blend is Z-up
            raise                                       # by construction, and the baking itself is done by then
        report["z_up_check"] = "passed over (the rig is deeper than tall): %s" % exc
    report["height_m"] = round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)
    if missing_required:
        # no human figure - a snake or fish tail for legs (Kaliya, Wednesday), wings for arms (Harbinger)
        report["plain_rig"] = ("no standard MMD skeleton (the rig has no %s): the game's bones under their own "
                               "names, no IK, no physics" % ", ".join(missing_required))
        root = plain_mmd_model(arm)
        report.update({"bones": len(arm.data.bones), "rigid_bodies": 0, "joints": 0, "bust_physics": []})
    else:
        report["premerged_helpers"] = roe.premerge_spine_helpers(arm, meshes, slots)
        helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
        report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
        report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
        stash = shape_keys.stash(meshes)                # the pose bakes below skip meshes with shape keys
        report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
        skin_before = roe.snapshot_skin(arm, meshes)
        report["cloth_names"] = teach_cloth_names()
        report["dynamic_hair"] = teach_dynamic_hair(arm)
        report["cloth_body"] = every_biped_is_body(arm.get("tsq_body_bones", "") or "")
        root, stats = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before,
                                             bust=True, collider_fixes=True)
        report.update(stats)
        physics = stats.get("physics", {})
        report["rigid_bodies"] = physics.get("rigid_bodies")
        report["joints"] = physics.get("joints")
        report["bust_physics"] = physics.get("bust") or []
        report["bust_style"] = bust["style"]
        if bust["style"] == "spring" and report["bust_physics"]:
            # the worker's pivots -> sliding springs, like the game's Bone Spring (see the module text)
            report["bust_springs"] = tb.spring_bust(scene, bust)
        if stash:
            report["shape_keys_restored"] = shape_keys.restore(meshes)
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = setup_materials(meshes, os.path.join(out_dir, "textures"))
    morphs = build_morphs(root, meshes)
    report["morphs"] = morphs
    report["vertex_morphs"] = morphs.get("vertex_morphs", [])

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or "Converted from %s by ripper_tpose (scripts/taimaninsquad). Personal use only." % game
    text = bpy.data.texts.new(name + "_comment")
    text.from_string(comment.replace(chr(92) + "n", "\n"))
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
    try:
        report["short_bone_names"] = roe.shorten_bone_names(root)
    except Exception as exc:  # noqa: BLE001 - long names only cost VMD addressing of helper bones
        report["short_bone_names"] = "skipped: %s" % exc
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True, log_level="ERROR")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("PMX not written: %s" % path)
    try:
        report["grant_order_violations"] = roe.verify_grant_order(path)
    except Exception as exc:  # noqa: BLE001
        report["grant_order_violations"] = []
        report["grant_order_check"] = "skipped: %s" % exc
    report["bytes"] = os.path.getsize(path)
    report["repacked_images"] = tb.repack_images_from(unpack_dir)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    shutil.rmtree(unpack_dir, ignore_errors=True)
    print("TSQ_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
