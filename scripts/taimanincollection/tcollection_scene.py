"""Read one Taimanin Collection prefab (or scene) out of data.unity3d into the scene folder build_blend.py takes
(scene.json + parts/*.npz + textures/*.png - the format of ../taimaninsquad/tsquad_scene.py).

The character is built the way Action Taimanin builds its own, so the reading is ../actiontaimanin's Scene: the
face prefab on face bones, the story clips made into shape keys, Dynamic Bone, Toony Colors Pro 2 hints.  What
this file adds is what a PLAYER BUILD does differently from that game's bundles:

* no type trees: a script component is told by the MonoScript its raw header points to, and the two classes a
  model needs are read with the layouts of dynamic_bone_types.json (tcollection_common.Component);
* the face clips are loose objects named like Action Taimanin's files (Game.container hands them over under the
  paths that game has);
* everything that is not a character is a rigid prop: nothing "waits at the origin for an animation", so no part
  is parked;
* a scene of the build (the bike race) has several roots: they are walked under one made-up root;
* materials that lost their shader and every property in the build (the two leftover city sets) get their
  pictures back BY NAME - mat_x takes tex_x, tex_x_lm (light map) and tex_x_e (glow) when such textures exist.
  That is a guess, marked "guessed" in the material record.
"""
from __future__ import annotations

import os

import numpy as np

import tcollection_common as tcc                        # (first: it puts the two other games' folders on the path)
import ataimanin_scene as asc  # noqa: E402
import tsquad_scene as ts  # noqa: E402
from tcollection_common import tc  # noqa: E402

SCENE_ROOT = -1                                         # node id of the made-up root of a scene
INTERFACE = ("RectTransform",)                          # a root of these is the interface, not the world
# the texture slots of this game's own background shaders, as the material builder reads them
BASE_SLOTS = ("_MainTex", "_diffuse_tex", "_diffuse_map")
LIGHT_SLOTS = ("_light_tex", "_LightMap")
GLOW_SLOTS = ("_glow_tex", "_Emission")
TINTS = ("_diffuse_color", "_MainTex_color", "_Color", "_TintColor")
POWERS = ("_diffuse_power", "_MainTex_power")
GLOW_COLORS = ("_glow_color", "_Emission_color")
GLOW_POWERS = ("_glow_velue", "_glow_value", "_Emission_power")
GUESSES = (("_MainTex", ""), ("_LightMap", "_lm"), ("_Emission", "_e"))
FLOAT_FORMATS = {17: ("<f2", 2), 20: ("<f4", 4)}       # TextureFormat RGBAHalf / RGBAFloat: (numpy type, bytes)


def family(shader: str) -> str:
    """Which builder a material goes to: Action Taimanin's families, plus this game's background shaders."""
    kind = asc.family(shader)
    if kind != "other":
        return kind
    if shader.startswith(("Curved/", "eTOYLab/bg_", "etoylab_background/", "Mobile/Unlit", "Unlit/",
                          "Legacy Shaders/", "Standard")) or not shader:
        return "background"
    return "other"


def background_hints(spec: dict) -> dict:
    """What tco_materials.build_background needs, whatever the shader calls its slots: the colour picture and its
    tint, the light map (a second picture multiplied on, when it is not the colour picture itself), the glow
    picture with its colour and strength.

    A Unity material keeps the values of every shader it was ever given, so only the properties its present
    shader DECLARES count (spec["declared"]; Curved/Curved_BG declares _glow_velue - the typing slip is the real
    name - while the materials also carry a dead _glow_value).  A material without a shader has no such list:
    whatever it holds is taken."""
    tex, floats, colors = spec.get("textures", {}), spec.get("floats", {}), spec.get("colors", {})
    declared = set(spec.get("declared") or [])

    def first(names, table):
        return next((n for n in names if n in table and (not declared or n in declared)), None)

    base, light, glow = first(BASE_SLOTS, tex), first(LIGHT_SLOTS, tex), first(GLOW_SLOTS, tex)
    out = {"family": "background", "base_slot": base, "light_slot": None, "glow_slot": None}
    if base:
        out["base_map"] = tex[base]["file"]
    tint = colors.get(first(TINTS, colors) or "", [1.0, 1.0, 1.0, 1.0])
    power = floats.get(first(POWERS, floats) or "", 1.0)
    out["tint"] = [round(float(c) * (power if i < 3 else 1.0), 4) for i, c in enumerate(tint)]
    if light and (not base or tex[light]["file"] != tex[base]["file"]):
        out["light_slot"] = light
    if glow and (not base or tex[glow]["file"] != tex[base]["file"]):
        colour = colors.get(first(GLOW_COLORS, colors) or "", [1.0, 1.0, 1.0, 1.0])
        strength = floats.get(first(GLOW_POWERS, floats) or "", 1.0)
        if strength > 0.0:
            out["glow_slot"], out["glow_color"], out["glow_strength"] = glow, [float(c) for c in colour[:3]], float(strength)
    return out


def float_image(width: int, height: int, fmt: int, data: bytes):
    """A PIL picture of an RGBAHalf (17) / RGBAFloat (20) texture's first level, cut off at 1; None when the
    data is too short.  Unity keeps the rows bottom-up."""
    from PIL import Image

    kind, size = FLOAT_FORMATS[fmt]
    count = width * height * 4
    if len(data) < count * size:
        return None
    values = np.frombuffer(data, dtype=kind, count=count).reshape(height, width, 4).astype(np.float32)
    rgb = np.clip(np.nan_to_num(values[::-1, :, :3]), 0.0, 1.0)
    return Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")


def light_map_uv(parts: list[dict], materials: dict) -> None:
    """Say on which UV set each light map lies (hints["light_uv"], a build_blend.py layer name): the second
    one when every part that wears the material has one - a light map is unwrapped apart from the tiling
    colour picture - else the first."""
    for part in parts:
        second = "uv1" in part.get("uv_sets", [])
        for key in part["materials"]:
            hints = (materials.get(key) or {}).get("hints") or {}
            if hints.get("light_slot"):
                hints["light_uv"] = "UV1" if second and hints.get("light_uv", "UV1") == "UV1" else "UVMap"


class Scene(asc.Scene):
    """ataimanin_scene.Scene on a player build."""

    def __init__(self, loader, out_dir: str, character: bool = True):
        super().__init__(loader, out_dir)
        self.character = character
        self.borrowed: dict[str, list] = {}             # part -> the materials it wears elsewhere in the game
        self._mesh = None                               # the mesh of the part being read (for _part_materials)

    # a component is wrapped so that its script class and (Dynamic Bone) its fields can be read
    def _components(self, go):
        return [self.loader.component(reader) for reader in super()._components(go)]

    def _read_transform(self, tr_reader):
        tr = tr_reader.read()
        go = self.loader.read(tr.m_GameObject)
        comps = self._components(go)
        p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
        local = ts.trs_matrix((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))
        types = [c.type.name for c in comps]
        monos = [c.script for c in comps if c.type.name == "MonoBehaviour"]
        return tr, go, comps, local, types, monos

    def walk_roots(self, roots: list, name: str) -> int:
        """Several root GameObjects (a scene) under one made-up root; returns its node id."""
        self._add_node(SCENE_ROOT, name, None, np.eye(4), np.eye(4), True, [], [], [])
        for go_reader in roots:
            transform = next((c for c in self._components(go_reader.read())
                              if c.type.name in ("Transform",) + INTERFACE), None)
            if transform is None or transform.type.name in INTERFACE:
                continue
            stack = [(transform, SCENE_ROOT, np.eye(4), True)]
            while stack:
                tr_reader, parent, parent_world, parent_active = stack.pop()
                tr, go, comps, local, types, monos = self._read_transform(tr_reader)
                world = parent_world @ local
                active = parent_active and bool(go.m_IsActive)
                self._add_node(tr_reader.path_id, go.m_Name, parent, local, world, active, types, monos, comps)
                for child in reversed(tr.m_Children):
                    reader = self.loader.deref(child)
                    if reader is not None:
                        stack.append((reader, tr_reader.path_id, world, active))
        return SCENE_ROOT

    def _parked(self, nid, lo, hi) -> bool:
        return False if not self.character else super()._parked(nid, lo, hi)

    def choose_bones(self, root_id: int, skinned: set[int]):
        """A prefab that is one mesh on its root (a track piece, a coin) has no transform below the root to
        become a bone: the root itself is the bone then - an XPS or PMX model needs one to hang the mesh on."""
        keep = super().choose_bones(root_id, skinned)
        if not keep:
            self.nodes[root_id]["bone"] = self.nodes[root_id]["name"]
            keep.add(root_id)
        return keep

    def texture(self, pptr, prop: str):
        """Half-float and float pictures (the leftover sets' light maps) are decoded here: UnityPy 1.25 fails on
        them.  They hold light above 1; a PNG cannot, so it is cut off at 1."""
        reader = self.loader.deref(pptr)
        if reader is not None and reader.type.name == "Texture2D":
            key = (reader.assets_file.name, reader.path_id, prop in ts.NORMAL_PROPS)
            if key not in self._tex_files:
                tex = reader.read()
                image = float_image(tex.m_Width, tex.m_Height, int(tex.m_TextureFormat), tex.get_image_data()) \
                    if int(tex.m_TextureFormat) in FLOAT_FORMATS else None
                if image is not None:
                    name, n = ts.safe_name(tex.m_Name), 1
                    while name.lower() in self._tex_names:
                        n += 1
                        name = "%s_%d" % (ts.safe_name(tex.m_Name), n)
                    self._tex_names.add(name.lower())
                    os.makedirs(os.path.join(self.out_dir, "textures"), exist_ok=True)
                    image.save(os.path.join(self.out_dir, "textures", name + ".png"))
                    self._tex_files[key] = name + ".png"
        return super().texture(pptr, prop)

    # a raw model import wears Unity's default material: it is dressed as the game dresses the same mesh
    def _skinned_part(self, nid, renderer, bones):
        self._mesh = (self.nodes[nid]["name"], self.loader.deref(renderer.m_Mesh))
        super()._skinned_part(nid, renderer, bones)

    def _rigid_part(self, nid, renderer, mesh_filter):
        self._mesh = (self.nodes[nid]["name"], self.loader.deref(mesh_filter.m_Mesh))
        super()._rigid_part(nid, renderer, mesh_filter)

    def _part_materials(self, renderer):
        slots = list(renderer.m_Materials)
        name, mesh = self._mesh or ("", None)
        if mesh is not None and slots and all(self.loader.is_default_material(m) for m in slots):
            worn = self.loader.mesh_materials().get((mesh.assets_file.name, mesh.path_id))
            if worn:
                slots = [worn[min(i, len(worn) - 1)] for i in range(len(slots))]
                self.borrowed[name] = [self.loader.deref(m).peek_name() for m in slots]
        return [self.material(m) for m in slots]

    def material(self, pptr):
        name = ts.Scene.material(self, pptr)               # (not Action Taimanin's: its hints come below)
        if name is None or "hints" in self.materials[name]:
            return name
        spec = self.materials[name]
        shader = self.loader.read(self.loader.read(pptr).m_Shader)
        props = getattr(getattr(getattr(shader, "m_ParsedForm", None), "m_PropInfo", None), "m_Props", None) or []
        spec["declared"] = [p.m_Name for p in props]
        if not spec["shader"] and not spec["textures"]:    # stripped in the build: the pictures by their names
            for slot, tail in GUESSES:
                found = self.loader.named("Texture2D").get("tex_" + spec["name"][4:] + tail) \
                    if spec["name"].startswith("mat_") else None
                png = self.texture(found[0], slot) if found else None
                if png:
                    spec["textures"][slot] = {"file": png, "scale": [1.0, 1.0], "offset": [0.0, 0.0]}
                    spec["guessed"] = True
            spec["stripped"] = not spec["textures"]          # ... and no picture is named after it: left plain
        kind = family(spec["shader"])
        if kind == "background":
            spec["hints"] = background_hints(spec)
        else:
            spec["hints"] = asc.hints(spec)
            spec["hints"]["family"] = kind
        return name


def extract(model: dict, out_dir: str, game: tcc.Game | None = None, include_inactive: bool = False,
            expressions: bool = True) -> dict:
    """Write scene.json + parts + textures of one model into out_dir; returns the scene dict."""
    game = game or tcc.Game()
    character = model["category"] == "character"
    scene = Scene(game, out_dir, character)
    if model["key"].startswith(tcc.SCENE_PREFIX):
        root_id = scene.walk_roots(game.scene_roots(model["key"][len(tcc.SCENE_PREFIX):]), model["name"])
    else:
        prefab = game.prefabs().get(model["key"])
        if prefab is None:
            raise RuntimeError("prefab %s not found in %s" % (model["key"], tcc.DATA_FILE))
        root_id = scene.walk(prefab)
    emotes = scene.add_renderers(root_id, include_inactive)
    light_map_uv(scene.parts, scene.materials)
    made, sources = scene.add_expressions(root_id, [model.get("character")]) if character and expressions else ([], {})
    scene.read_cloth(root_id)
    meta = {"id": model["id"], "name": model["name"], "group": model["group"], "category": model["category"],
            "prefab": model["key"], "bundle": os.path.basename(tcc.DATA_FILE), "game": tcc.GAME,
            "color_space": "gamma", "colliders": scene.colliders, "body_bones": asc.BODY_BONES,
            "emote_parts": emotes, "expressions": made, "morph_sources": sources,
            "guessed_materials": sorted(k for k, m in scene.materials.items() if m.get("guessed")),
            "plain_materials": sorted(k for k, m in scene.materials.items() if m.get("stripped")),
            "borrowed_materials": scene.borrowed}
    data = scene.to_json(root_id, meta)
    tc.save_json(os.path.join(out_dir, "scene.json"), data)
    return data


def details(model: dict, game: tcc.Game) -> dict:
    """What list_models.py --details shows: counts read from the prefab without decoding any geometry."""
    scene = Scene(game, "", model["category"] == "character")
    if model["key"].startswith(tcc.SCENE_PREFIX):
        root_id = scene.walk_roots(game.scene_roots(model["key"][len(tcc.SCENE_PREFIX):]), model["name"])
    else:
        root_id = scene.walk(game.prefabs()[model["key"]])
    info = {"parts": 0, "vertices": 0, "triangles": 0, "bones": 0, "face_bones": 0, "materials": 0,
            "default_materials": 0, "stripped_materials": 0, "shaders": [], "dynamic_bones": 0}
    materials, bones, shaders = {}, set(), set()
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
        info["parts"] += 1
        info["vertices"] += count
        info["triangles"] += sum(sm["indexCount"] for i, sm in enumerate(tt["m_SubMeshes"])
                                 if sm["topology"] == 0 and i < slots) // 3
        for m in renderer.m_Materials:
            key = (m.m_FileID, m.m_PathID)
            if key in materials:
                continue
            if game.is_default_material(m):                # nothing, or the Default-Material of a raw import
                materials[key] = "default"
                continue
            mat = game.read(m)
            shader = game.read(mat.m_Shader)
            name = getattr(getattr(shader, "m_ParsedForm", None), "m_Name", "") or ""
            materials[key] = "stripped" if not name and not any(
                env.m_Texture.m_PathID for _k, env in mat.m_SavedProperties.m_TexEnvs) else family(name)
            shaders.add(materials[key])
    names = [scene.nodes[b]["name"] for b in bones if b in scene.nodes]
    info["materials"] = len(materials)
    info["default_materials"] = sum(1 for v in materials.values() if v == "default")
    info["stripped_materials"] = sum(1 for v in materials.values() if v == "stripped")
    info["shaders"] = sorted(shaders)
    info["bones"] = len(bones)
    info["face_bones"] = sum(1 for n in names if asc.re.match(asc.BODY_BONES, n))
    info["biped"] = any(n.endswith(" Pelvis") for n in names)
    return info


if __name__ == "__main__":                             # python tcollection_scene.py <id> <out dir>: the scene only
    import sys

    target = tcc.find_models(tcc.discover_models(), [sys.argv[1]])[0]
    result = extract(target, sys.argv[2])
    print("%s: %d parts, %d bones, %d materials, cloth %s, breast bones %s, warnings %s" % (
        target["id"], len(result["parts"]), len(result["nodes"]), len(result["materials"]),
        [c["name"] + ":" + "+".join(c["root_bones"]) for c in result["cloth"]], result["breast_bones"],
        result["warnings"]))
    for item in result["expressions"]:
        print("  shape %-16s %-40s bones move %5.1f mm, %5d vertices up to %5.1f mm" % (
            item["name"], item["source"], item["bone_travel_mm"], item["vertices"], item["max_mm"]))
    print("  converter roles:", result["morph_sources"])
    for part in result["parts"]:
        print("  %-28s %-6s verts %6d tris %6d bones %3d materials %s" % (
            part["name"], part["role"], part["vertices"], part["triangles"], len(part["bones"]), part["materials"]))
    for name, mat in result["materials"].items():
        print("  material %-26s %-58s %s %s" % (name, mat["shader"] or "(no shader)", mat["hints"].get("family"),
                                                {k: v["file"] for k, v in mat["textures"].items()}))
