"""Shared by the Taimanin Collection scripts: where things are, the game's data file, the model list.

Taimanin Collection (eTOYLab, Unity 2018.4.36f1, IL2CPP, built-in render pipeline, gamma colour space) is a 2D
card game: its 843 cards are encrypted pictures under ``Data/Res``.  The 3D it has is in the player data itself,
``TaimaninCollection_Data/data.unity3d`` - one plain UnityFS file (360 MB) holding the three scenes and
``resources.assets``:

* Asagi, the way Action Taimanin builds her (the same studio's engine code): ``prf_asagi_costume_1`` = body +
  hair on a 3ds Max Biped, the face a prefab of its own on about 28 face bones, Dynamic Bone on hair and breasts,
  Toony Colors Pro 2 materials;
* what the bike mini-game shows: a rigged motorcycle, a drop ship, the bridge track with its barricades, coins,
  boosters, a truck, the night sky dome, and the track pieces the level is put together from;
* leftovers of Action Taimanin that this game never shows: two city sets whose materials lost their shader and
  every property in the build, and about 190 raw model imports with Unity's default material.

A player build carries NO type trees.  UnityPy brings its own for the engine's classes; for the two script
classes a model needs (DynamicBone, DynamicBoneCollider) the field layout is in dynamic_bone_types.json - taken
from Action Taimanin's bundles, which do carry type trees, and checked to read every such component of this
game to its last byte.

The Blender-side and format code is Taimanin Squad's and the scene reading Action Taimanin's
(``../taimaninsquad``, ``../actiontaimanin``), reused module by module; this file only adds what differs.
Paths: TCOLLECTION_GAME_DIR, TCOLLECTION_EXPORT_ROOT, TSQUAD_BLENDER.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SQUAD_DIR = os.path.join(os.path.dirname(HERE), "taimaninsquad")
ACTION_DIR = os.path.join(os.path.dirname(HERE), "actiontaimanin")
for folder in (ACTION_DIR, SQUAD_DIR):
    if folder not in sys.path:
        sys.path.insert(1, folder)
import tsquad_common as tc  # noqa: E402 - Blender path, json helpers, the export ledger, the breast settings

GAME = "Taimanin Collection"
GAME_DIR = os.environ.get("TCOLLECTION_GAME_DIR", r"E:\SteamLibrary\steamapps\common\Taimanin Collection")
DATA_FILE = os.path.join(GAME_DIR, "TaimaninCollection_Data", "data.unity3d")
EXPORT_ROOT = os.environ.get("TCOLLECTION_EXPORT_ROOT", r"E:\game_export\TaimaninCollection")
TYPES_FILE = os.path.join(HERE, "dynamic_bone_types.json")
RESOURCES = "resources.assets"
SCENE_PREFIX = "scene:"                                 # a model key that is a scene of the build, not a prefab

CATEGORY_ORDER = ("character", "vehicle", "prop", "level", "scene", "set", "unit", "part", "effect", "director", "raw")
CATEGORY_ZH = {"character": "角色", "vehicle": "载具（带骨架）", "prop": "摩托小游戏的道具和场景件",
               "level": "摩托小游戏的赛道段", "scene": "游戏场景", "set": "布景（Action Taimanin 的残留，材质被剥掉）",
               "unit": "游戏里生成的单位（同一个角色模型 + 相机）", "part": "角色的零件", "effect": "特效",
               "director": "过场演出",
               "raw": "原始模型（残留，只有默认材质）"}
# where a prefab lies under Resources/ says what it is: (pattern on the path, category), the first that fits
RULES = (
    (r"^ui/", ""),                                                          # the interface: not a model
    (r"^unit_art/model/[^/]+/prf_", "character"),
    (r"^unit/", "unit"),
    (r"^unit_art/model/", "part"),
    (r"^background/art/movie/[^/]*_rig$", "vehicle"),
    (r"^bike/level/prf_race_trackobject", "level"),
    (r"^bike/(background|skybox)/prf_", "prop"),
    (r"^background/art/movie/(asagi_select|in_game_movie)/prf_", "set"),
    (r"^(bike/)?director/", "director"),
    (r"^(bike/)?effect/", "effect"),
    (r"", "raw"),
)
GROUPS = {"vehicle": "Vehicles", "prop": "Props", "level": "Levels", "scene": "Scenes", "set": "Sets",
          "effect": "Effects", "director": "Directors", "raw": "Raw"}
CHARACTER = re.compile(r"^unit_art/model/([^/]+)/|^unit/([^/_]+)")
LIST_VERSION = 2                                        # of RULES / the counting: an older models.json is made again


def log(msg: str) -> None:
    print("[tcollection] " + msg, flush=True)


def check_game() -> None:
    if not os.path.isfile(DATA_FILE):
        raise SystemExit("data file not found: %s\nset TCOLLECTION_GAME_DIR to the game folder" % DATA_FILE)


def check_tools() -> None:
    check_game()
    if not os.path.isfile(tc.BLENDER):
        raise SystemExit("Blender not found: %s (set TSQUAD_BLENDER)" % tc.BLENDER)


# ---------------------------------------------------------------- script components without type trees
def type_nodes(path: str = TYPES_FILE) -> dict:
    """{script class: UnityPy type tree node} from dynamic_bone_types.json ({class: [[level, type, name, byte
    size, meta flag, version, type flags], ...]})."""
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    with open(path, encoding="utf-8") as fh:
        layouts = json.load(fh)
    return {cls: TypeTreeNode.from_list([
        {"m_Level": level, "m_Type": kind, "m_Name": name, "m_ByteSize": size, "m_MetaFlag": meta,
         "m_Version": version, "m_TypeFlags": flags}
        for level, kind, name, size, meta, version, flags in rows])
        for cls, rows in layouts.items() if not cls.startswith("_")}


def script_reference(raw: bytes) -> tuple[int, int]:
    """(file id, path id) of the MonoScript a MonoBehaviour is an instance of.  Its data starts, whatever the
    script: m_GameObject (int32 file, int64 path), m_Enabled (1 byte, aligned to 4), m_Script (int32, int64)."""
    if len(raw) < 28:
        return 0, 0
    return struct.unpack_from("<iq", raw, 16)


class Component:
    """A MonoBehaviour reader that knows its script's class and, for the classes of dynamic_bone_types.json,
    reads itself: stands in for the UnityPy reader in tsquad_scene / ataimanin_scene."""

    def __init__(self, reader, script: str, node=None):
        self._reader, self.script, self._node = reader, script, node

    def __getattr__(self, name):
        return getattr(self._reader, name)

    def read_typetree(self, *args, **kwargs):
        if self._node is None:
            raise ValueError("no type tree for the script %s" % (self.script or "?"))
        return self._reader.read_typetree(self._node)


class Game:
    """The game's data file in one UnityPy environment, read whole (about 15 seconds).

    deref / read / container have the shape tsquad_scene.Scene and ataimanin_scene expect of their loader."""

    def __init__(self, path: str = DATA_FILE):
        import UnityPy

        self.path = path
        self.env = UnityPy.load(path)
        bundle = next(iter(self.env.files.values()))
        self.files = {name: sf for name, sf in bundle.files.items() if hasattr(sf, "objects")}
        self._scripts: dict | None = None
        self._types: dict | None = None
        self._resources: list | None = None
        self._named: dict = {}

    # ---- references
    def deref(self, pptr):
        """ObjectReader behind a PPtr (or the reader itself when handed one); None if absent."""
        if pptr is None:
            return None
        if hasattr(pptr, "get_raw_data"):                  # an ObjectReader (or a Component around one)
            return pptr
        if not getattr(pptr, "m_PathID", 0):
            return None
        try:
            return pptr.deref()
        except (FileNotFoundError, KeyError, ValueError):   # Unity's built-in resources are not in the file
            return None

    def read(self, pptr):
        reader = self.deref(pptr)
        return reader.read() if reader is not None else None

    # ---- scripts
    def script_class(self, reader) -> str:
        """Class name of the script behind a MonoBehaviour, from the raw header (there is no type tree)."""
        if self._scripts is None:
            self._scripts = {}
            for name, sf in self.files.items():
                for obj in sf.objects.values():
                    if obj.type.name == "MonoScript":
                        self._scripts[(name, obj.path_id)] = obj.read().m_ClassName
        file_id, path_id = script_reference(reader.get_raw_data())
        sf = reader.assets_file
        target = sf.name
        if file_id:
            if file_id - 1 >= len(sf.externals):
                return ""
            target = os.path.basename(sf.externals[file_id - 1].path.replace("\\", "/"))
        return self._scripts.get((target, path_id), "")

    def component(self, reader):
        """A component reader as the scene code wants it: MonoBehaviours wrapped (Component)."""
        if reader.type.name != "MonoBehaviour":
            return reader
        if self._types is None:
            self._types = type_nodes()
        script = self.script_class(reader)
        return Component(reader, script, self._types.get(script))

    # ---- what is in the file
    def resources(self) -> list[tuple[str, object]]:
        """[(path under Resources/, ObjectReader)] - the ResourceManager's table."""
        if self._resources is None:
            self._resources = []
            manager = next((o for sf in self.files.values() for o in sf.objects.values()
                            if o.type.name == "ResourceManager"), None)
            for path, pptr in (manager.read().m_Container if manager is not None else []):
                reader = self.deref(pptr)
                if reader is not None:
                    self._resources.append((path, reader))
        return self._resources

    def prefabs(self) -> dict[str, object]:
        """{path under Resources/: GameObject reader} of the prefab roots."""
        return {path: reader for path, reader in self.resources() if reader.type.name == "GameObject"}

    def named(self, kind: str) -> dict[str, list]:
        """{object name: [readers]} of every object of one class in resources.assets (Texture2D, AnimationClip)."""
        if kind not in self._named:
            table: dict[str, list] = {}
            for obj in self.files[RESOURCES].objects.values():
                if obj.type.name == kind:
                    table.setdefault(obj.peek_name() or "", []).append(obj)
            self._named[kind] = table
        return self._named[kind]

    def is_default_material(self, pptr) -> bool:
        """True for a material slot that says nothing: empty, Unity's built-in default (not in the file), or
        the ``Default-Material`` a raw model import was left with."""
        reader = self.deref(pptr)
        return reader is None or reader.type.name != "Material" or (reader.peek_name() or "") == "Default-Material"

    def mesh_materials(self) -> dict:
        """{(file, mesh path id): [material PPtr per slot]} - how each mesh is dressed where the game really
        draws it.  The raw model imports under Resources/ carry Unity's default material; the same mesh sits,
        with its real materials, in the prefab or the cutscene that shows it (the drop ship: only in
        drt_race_start_asagi)."""
        if "mesh_materials" not in self._named:
            table: dict = {}
            for sf in self.files.values():
                filters = {}
                for obj in sf.objects.values():
                    if obj.type.name == "MeshFilter":
                        data = obj.read()
                        filters[data.m_GameObject.m_PathID] = data.m_Mesh
                for obj in sf.objects.values():
                    if obj.type.name not in ("SkinnedMeshRenderer", "MeshRenderer"):
                        continue
                    renderer = obj.read()
                    mesh = renderer.m_Mesh if obj.type.name == "SkinnedMeshRenderer" \
                        else filters.get(renderer.m_GameObject.m_PathID)
                    target = self.deref(mesh)
                    slots = list(renderer.m_Materials)
                    if target is None or not slots or any(self.is_default_material(m) for m in slots):
                        continue
                    table.setdefault((target.assets_file.name, target.path_id), slots)
            self._named["mesh_materials"] = table
        return self._named["mesh_materials"]

    def container(self, name: str) -> dict:
        """What ataimanin_scene.story_clips asks Action Taimanin's bundle ``animation_char`` for: the face and
        mouth clips by a path.  Here they are loose clips in resources.assets, named like there.

        Seven face clips and two mouth clips exist TWICE under one name.  The file holds two sets one after the
        other: an older one (7 faces; mouths only for angry / angry_02 / idle, as 2-second talking loops) and
        the set Action Taimanin has (7 faces, 7 mouths, each mouth a single pose).  story_clips takes the first
        clip of a name that fits the rig, so the later object comes first here; the other one follows in a
        folder of its own."""
        if name != "animation_char":
            return {}
        out = {}
        for clip, readers in sorted(self.named("AnimationClip").items()):
            match = re.match(r"^ani_(face|mouth)_(.+?)_story_", clip)
            if match is None:
                continue
            for n, reader in enumerate(sorted(readers, key=lambda r: -r.path_id)):
                out["animation_char/%s%s/ani_story/%s.anim" % (match.group(2), "_older%d" % n if n else "", clip)] = reader
        return out

    def scenes(self) -> list[tuple[str, str]]:
        """[(serialized file, scene name)] - the build's scenes: level<N> is the N-th of the build settings."""
        manager = next((o for sf in self.files.values() for o in sf.objects.values()
                        if o.type.name == "BuildSettings"), None)
        names = list(manager.read_typetree().get("scenes") or []) if manager is not None else []
        out = []
        for index, path in enumerate(names):
            if "level%d" % index in self.files:
                out.append(("level%d" % index, os.path.splitext(os.path.basename(path))[0]))
        return out

    def scene_roots(self, key: str) -> list:
        """The root GameObject readers of a scene, in file order (the interface roots left out).  `key` is
        ``level2`` (every root) or ``level2/BikeObj`` (the root of that name)."""
        level, _slash, wanted = key.partition("/")
        out = []
        for obj in self.files[level].objects.values():
            if obj.type.name != "Transform":
                continue
            tr = obj.read()
            if not tr.m_Father.m_PathID:
                reader = self.deref(tr.m_GameObject)
                if reader is not None and (not wanted or reader.peek_name() == wanted):
                    out.append(reader)
        return out


# ---------------------------------------------------------------- the model list
def title(text: str) -> str:
    return "_".join(w.capitalize() for w in text.split("_"))


def category_of(path: str) -> str:
    low = path.lower()
    return next(category for pattern, category in RULES if re.search(pattern, low))


def model_from_path(path: str, taken=()) -> dict | None:
    """One model record from a prefab's path under Resources/ (None: an interface prefab).  The id is the
    prefab's own name; where two prefabs share it, the folder is put in front."""
    category = category_of(path)
    if not category:
        return None
    name = path.rsplit("/", 1)[-1].lower()
    model_id = name if name not in taken else "%s_%s" % (path.rsplit("/", 2)[-2].lower(), name)
    model = {"id": model_id, "key": path, "category": category, "folder": path.rsplit("/", 1)[0], "name": name}
    match = CHARACTER.match(path.lower())
    if category in ("character", "unit", "part") and match:
        model["character"] = match.group(1) or match.group(2)
        model["group"] = title(model["character"])
    else:
        model["character"] = ""
        model["group"] = GROUPS.get(category, title(category))
    return model


def signature() -> list:
    """What the cached model list was made from: the data file, and the version of the rules above."""
    return [os.path.getsize(DATA_FILE), int(os.path.getmtime(DATA_FILE)), LIST_VERSION]


def renderer_counts(game: Game, go_reader) -> dict:
    """{"skinned", "rigid", "particles", "nodes"} below a prefab root - without decoding anything.  Only what
    would be drawn counts: a renderer that is enabled, on an active object, with a mesh."""
    counts = {"skinned": 0, "rigid": 0, "particles": 0, "nodes": 0}
    stack = [(go_reader, True)]
    while stack:
        reader, active = stack.pop()
        go = reader.read()
        active = active and bool(go.m_IsActive)
        counts["nodes"] += 1
        by_type = {}
        for comp in go.m_Components:
            found = game.deref(getattr(comp, "component", comp))
            if found is not None:
                by_type[found.type.name] = found
        if active and "SkinnedMeshRenderer" in by_type:
            renderer = by_type["SkinnedMeshRenderer"].read()
            counts["skinned"] += bool(renderer.m_Enabled and renderer.m_Mesh.m_PathID)
        elif active and "MeshRenderer" in by_type and "MeshFilter" in by_type:
            counts["rigid"] += bool(by_type["MeshRenderer"].read().m_Enabled
                                    and by_type["MeshFilter"].read().m_Mesh.m_PathID)
        counts["particles"] += "ParticleSystem" in by_type
        transform = by_type.get("Transform") or by_type.get("RectTransform")
        if transform is not None:
            for child in transform.read().m_Children:
                tr = game.read(child)
                found = game.deref(tr.m_GameObject) if tr is not None else None
                if found is not None:
                    stack.append((found, active))
    return counts


def scene_models(level: str, name: str, roots: list[tuple[str, dict]]) -> list[dict]:
    """The models a scene of the build gives: the scene as a whole, and - when more than one of its roots draws
    something - each of those roots by itself (the bike of the race scene stands in it complete, wheels on;
    under Resources/ it is three separate rigs).  `roots`: [(root name, renderer_counts)]."""
    drawn = [(root, counts) for root, counts in roots if counts["skinned"] or counts["rigid"]]
    if not drawn:
        return []
    total = {key: sum(counts[key] for _root, counts in drawn) for key in drawn[0][1]}
    base = {"category": "scene", "folder": "Assets/Scenes", "character": "", "group": GROUPS["scene"]}
    out = [dict(base, **total, id="scene_" + name.lower(), key=SCENE_PREFIX + level, name=name)]
    if len(drawn) > 1:
        for root, counts in drawn:
            out.append(dict(base, **counts, id="scene_%s_%s" % (name.lower(), re.sub(r"\W+", "_", root.lower())),
                            key="%s%s/%s" % (SCENE_PREFIX, level, root), name="%s / %s" % (name, root)))
    return out


def discover_models(root: str = EXPORT_ROOT, game: Game | None = None, refresh: bool = False) -> list[dict]:
    """Every prefab under Resources/ that draws a mesh, and the scenes that do - cached in
    <root>/_meta/models.json until the data file changes."""
    cache = os.path.join(tc.meta_dir(root), "models.json")
    data = None
    if not refresh and os.path.isfile(cache):
        try:
            data = tc.load_json(cache)
        except (OSError, ValueError):
            data = None
        if data and data.get("signature") != signature():
            data = None
    if data is None:
        game = game or Game()
        models, taken = [], set()
        for path, reader in sorted(game.prefabs().items()):
            model = model_from_path(path, taken)
            if model is None:
                continue
            counts = renderer_counts(game, reader)
            if not counts["skinned"] and not counts["rigid"]:
                continue                                   # particles, sounds, a camera rig: nothing to export
            model.update(counts)
            taken.add(model["name"])
            models.append(model)
        for level, name in game.scenes():
            models.extend(scene_models(level, name, [(reader.peek_name(), renderer_counts(game, reader))
                                                     for reader in game.scene_roots(level)]))
        data = {"signature": signature(), "models": models}
        tc.save_json(cache, data)
    models = data["models"]
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    models.sort(key=lambda m: (order.get(m["category"], 99), m["group"].lower(), m["id"]))
    for model in models:
        model["exported"] = tc.exported_formats(model, root)
    return models


def find_models(models: list[dict], patterns: list[str]) -> list[dict]:
    """ids, character names (every model of that character) or wildcards; order of first match kept."""
    out, missing = [], []
    for pat in patterns:
        p = pat.lower()
        hits = [m for m in models if m["id"] == p]
        if not hits:
            hits = [m for m in models if m.get("character") == p]
        if not hits:
            hits = [m for m in models if fnmatch.fnmatch(m["id"], p)]
        if not hits and not any(c in p for c in "*?["):
            hits = [m for m in models if p in m["id"]]
        if not hits:
            missing.append(pat)
        for m in hits:
            if m not in out:
                out.append(m)
    if missing:
        raise SystemExit("no model matches: %s  (python list_models.py shows them)" % ", ".join(missing))
    return out
