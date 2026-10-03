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
# the shape names Taimanin Squad's PMX converter knows the roles of (export_pmx_blender.SOURCES)
SHAPE_NAMES = {"surprise": "surprised_face"}
BLINK, TALK = "closed_eyes", "mouth_talk_a"
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

        Returns (what was made, {converter role: [shape names]})."""
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

        bone_node = {n["bone"]: nid for nid, n in self.nodes.items() if "bone" in n}
        made = []
        for part in self.parts:
            ids = [bone_node.get(b) for b in part["bones"]]
            if not any(i in rest and i != root["id"] for i in ids):
                continue
            path = os.path.join(self.out_dir, part["npz"])
            arrays = dict(np.load(path))
            first = len(part["shape_keys"])
            inverse = [np.linalg.inv(self.nodes[i]["world"]) if i in rest else None for i in ids]
            for name, source, new, old in shapes:
                change = np.zeros((len(ids), 4, 4))
                for k, i in enumerate(ids):
                    if i in rest:
                        change[k] = (new[i] - old[i]) @ inverse[k]
                delta = skin_deltas(arrays["vertices"], arrays["bone_indices"], arrays["bone_weights"], change)
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
        return made, {role: found for role, found in sources.items() if found}

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
