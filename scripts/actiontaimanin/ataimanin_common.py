"""Shared by the Action Taimanin scripts: where things are, the game's bundles, the model list.

Action Taimanin (GREMORY, Unity 2022.3.62f2, IL2CPP, built-in render pipeline, gamma colour space) packs
everything into 39 big classic AssetBundles under ``ActionTaimanin_Data/StreamingAssets/AssetBundles/pc``
(``model_char`` alone is 1 GB / 2 GB unpacked), one serialized file + one ``.resS`` each.  Three of them
(``game``, ``string``, ``system``: the data tables) are encrypted; nothing a model needs is.

* ``unit``        1392 prefabs: ``unit/figure/<char>_costume_<n>_f`` (a character in one costume, put
                  together: body + hair + face), ``unit/character/<char>_g|_l``, ``unit/monster/..``,
                  ``unit/npc/..``, ``unit/weapon/..``.  This is the model list.
* ``model_char``  what those prefabs draw: per character ``body_<char>/`` (face, hair per costume) and
                  ``costume_<char>_<n>[_aos|_wos]/`` (the body in that costume), meshes + materials + textures.
* ``model_monster`` / ``model_npc`` / ``model_weapon`` / ``shader``: the same for the rest.

The bundles are LZ4HC in 128 KB blocks, so a part of one can be read without unpacking the rest: Bundle
reads the block table and unpacks only the blocks a request covers.  Game puts the serialized files into
one UnityPy environment and hands UnityPy the ``.resS`` data (meshes, textures) through the same lazy reader.

The Blender-side and format code is Taimanin Squad's (``../taimaninsquad``), reused module by module; this
file only adds what differs.  Paths: ATAIMANIN_GAME_DIR, ATAIMANIN_EXPORT_ROOT, TSQUAD_BLENDER.
"""
from __future__ import annotations

import bisect
import fnmatch
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SQUAD_DIR = os.path.join(os.path.dirname(HERE), "taimaninsquad")
if SQUAD_DIR not in sys.path:
    sys.path.insert(1, SQUAD_DIR)
import tsquad_common as tc  # noqa: E402 - Blender path, json helpers, the export ledger, the breast settings

GAME = "Action Taimanin"
GAME_DIR = os.environ.get("ATAIMANIN_GAME_DIR", r"E:\SteamLibrary\steamapps\common\Action Taimanin")
DATA_DIR = os.path.join(GAME_DIR, "ActionTaimanin_Data")
BUNDLE_DIR = os.path.join(DATA_DIR, "StreamingAssets", "AssetBundles", "pc")
EXPORT_ROOT = os.environ.get("ATAIMANIN_EXPORT_ROOT", r"E:\game_export\ActionTaimanin")
CONTAINER_ROOT = "assets/resources.assetbundle/"
UNIT_BUNDLE = "unit"
BLOCK_CACHE = 96                                        # unpacked 128 KB blocks kept per bundle

CATEGORY_ORDER = ("figure", "character", "monster", "npc", "weapon")
CATEGORY_ZH = {"figure": "角色（按服装，展示用）", "character": "角色（战斗 / 大厅用）", "monster": "怪物 / 敌人",
               "npc": "NPC / 物件", "weapon": "武器"}
PREFAB = re.compile(r"^unit/(character|figure|monster|npc|weapon)/([^/]+)/([^/]+)\.prefab$")
COSTUME = re.compile(r"^(?P<char>.+?)_costume_(?P<n>\d+)(?P<rest>(?:_[a-z0-9]+)*)_f$")


def log(msg: str) -> None:
    print("[ataimanin] " + msg, flush=True)


def check_game() -> None:
    if not os.path.isfile(os.path.join(BUNDLE_DIR, UNIT_BUNDLE)):
        raise SystemExit("bundle not found: %s\nset ATAIMANIN_GAME_DIR to the game folder"
                         % os.path.join(BUNDLE_DIR, UNIT_BUNDLE))


def check_tools() -> None:
    check_game()
    if not os.path.isfile(tc.BLENDER):
        raise SystemExit("Blender not found: %s (set TSQUAD_BLENDER)" % tc.BLENDER)


# ---------------------------------------------------------------- bundles
def _cstr(handle) -> str:
    out = bytearray()
    while True:
        c = handle.read(1)
        if c in (b"", b"\0"):
            return out.decode("utf-8", "replace")
        out += c


def parse_block_info(info: bytes, data_start: int):
    """(blocks [(unpacked size, packed size, compression)], unpacked offsets, file offsets, nodes
    {name: (offset, size)}) from a UnityFS "blocks and directory" record."""
    pos = 16
    count = struct.unpack_from(">I", info, pos)[0]
    pos += 4
    blocks, ustart, cstart = [], [], []
    u, c = 0, data_start
    for _ in range(count):
        usize, csize, flags = struct.unpack_from(">IIH", info, pos)
        pos += 10
        blocks.append((usize, csize, flags & 0x3F))
        ustart.append(u)
        cstart.append(c)
        u += usize
        c += csize
    count = struct.unpack_from(">I", info, pos)[0]
    pos += 4
    nodes = {}
    for _ in range(count):
        offset, size, _flags = struct.unpack_from(">qqI", info, pos)
        pos += 20
        end = info.index(b"\0", pos)
        nodes[info[pos:end].decode("utf-8", "replace")] = (offset, size)
        pos = end + 1
    return blocks, ustart, cstart, nodes


class Bundle:
    """A UnityFS file read lazily: the block table at open, a block when a request needs it."""

    def __init__(self, path: str):
        import lz4.block

        self._lz4 = lz4.block
        self.path = path
        self.handle = open(path, "rb")
        f = self.handle
        if _cstr(f) != "UnityFS":
            f.close()
            raise ValueError("not a UnityFS bundle (encrypted?): %s" % path)
        version = struct.unpack(">I", f.read(4))[0]
        _cstr(f)
        self.engine = _cstr(f)
        _total, csize, usize, flags = struct.unpack(">qIII", f.read(20))
        if flags & 0x80:
            raise ValueError("block table at the end of the file is not supported: %s" % path)
        if version >= 7:
            f.seek((f.tell() + 15) // 16 * 16)
        raw = f.read(csize)
        start = f.tell()
        if flags & 0x200:                              # 2022: the data is aligned too
            start = (start + 15) // 16 * 16
        info = self._unpack(raw, usize, flags & 0x3F)
        self.blocks, self.ustart, self.cstart, self.nodes = parse_block_info(info, start)
        self._cache: dict[int, bytes] = {}

    def _unpack(self, raw: bytes, size: int, compression: int) -> bytes:
        if compression in (2, 3):
            return self._lz4.decompress(raw, uncompressed_size=size)
        if compression == 0:
            return raw
        raise ValueError("compression %d is not supported: %s" % (compression, self.path))

    def _block(self, index: int) -> bytes:
        hit = self._cache.get(index)
        if hit is None:
            usize, csize, compression = self.blocks[index]
            self.handle.seek(self.cstart[index])
            hit = self._unpack(self.handle.read(csize), usize, compression)
            if len(self._cache) >= BLOCK_CACHE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[index] = hit
        return hit

    def read(self, offset: int, size: int) -> bytes:
        """`size` bytes of the unpacked data stream from `offset`."""
        index = bisect.bisect_right(self.ustart, offset) - 1
        skip = offset - self.ustart[index]
        out, need = [], size
        while need > 0 and index < len(self.blocks):
            usize, csize, compression = self.blocks[index]
            if compression == 0 and usize > (4 << 20):  # a stored block the size of the file (movie): read in place
                self.handle.seek(self.cstart[index] + skip)
                piece = self.handle.read(min(need, usize - skip))
            else:
                piece = self._block(index)[skip:skip + need]
            out.append(piece)
            need -= len(piece)
            skip = 0
            index += 1
        return b"".join(out)

    def close(self) -> None:
        self.handle.close()


class LazyNode:
    """A ``.resS`` / ``.resource`` node as UnityPy's get_resource_data wants a registered cab: a position
    and read_bytes."""

    def __init__(self, bundle: Bundle, offset: int, size: int):
        self.bundle, self.offset, self.size, self.Position = bundle, offset, size, 0

    def read_bytes(self, size: int) -> bytes:
        data = self.bundle.read(self.offset + self.Position, size)
        self.Position += size
        return data


def bundle_names() -> list[str]:
    return sorted(n for n in os.listdir(BUNDLE_DIR) if os.path.isfile(os.path.join(BUNDLE_DIR, n)))


class Game:
    """One UnityPy environment over the game's bundles; a bundle is opened when something in it is needed.

    deref / read have the shape tsquad_scene.Scene expects of its loader."""

    def __init__(self):
        import UnityPy

        self.env = UnityPy.Environment()
        self.bundles: dict[str, Bundle] = {}
        self.files: dict[str, list] = {}               # bundle -> its serialized files
        self._cabs: dict[str, str] | None = None

    def cab_index(self) -> dict[str, str]:
        """{serialized file name (lower): bundle} - which bundle an external reference lives in."""
        if self._cabs is None:
            self._cabs = {}
            for name in bundle_names():
                try:
                    bundle = self.bundles.get(name) or Bundle(os.path.join(BUNDLE_DIR, name))
                except ValueError:                     # the three encrypted table bundles
                    continue
                for node in bundle.nodes:
                    self._cabs[node.lower()] = name
                if name not in self.bundles:
                    bundle.close()
        return self._cabs

    def load(self, name: str) -> list:
        if name not in self.files:
            bundle = Bundle(os.path.join(BUNDLE_DIR, name))
            self.bundles[name] = bundle
            files = []
            for node, (offset, size) in bundle.nodes.items():
                if node.endswith((".resS", ".resource")):
                    self.env.register_cab(node, LazyNode(bundle, offset, size))
                    continue
                sf = self.env.load_file(bundle.read(offset, size), name=node)
                self.env.files[node] = sf
                self.env.register_cab(node, sf)
                files.append(sf)
            self.files[name] = files
        return self.files[name]

    def container(self, name: str) -> dict:
        """{asset path below assets/resources.assetbundle/: PPtr} of a bundle."""
        out = {}
        for sf in self.load(name):
            for key, pptr in sf.container.items():
                out[key[len(CONTAINER_ROOT):] if key.startswith(CONTAINER_ROOT) else key] = pptr
        return out

    def deref(self, pptr):
        """ObjectReader behind a PPtr (the bundle of another file is opened on the way); None if absent."""
        if pptr is None or not getattr(pptr, "m_PathID", 0):
            return None
        if pptr.m_FileID:
            sf = pptr.assetsfile
            if sf is None or pptr.m_FileID - 1 >= len(sf.externals):
                return None
            cab = sf.externals[pptr.m_FileID - 1].path.replace("\\", "/").rsplit("/", 1)[-1].lower()
            bundle = self.cab_index().get(cab)
            if bundle is None:                         # unity default resources / built-in extra
                return None
            self.load(bundle)
        try:
            return pptr.deref()
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def read(self, pptr):
        reader = self.deref(pptr)
        return reader.read() if reader is not None else None


# ---------------------------------------------------------------- the model list
def title(text: str) -> str:
    return "_".join(w.capitalize() for w in text.split("_"))


def model_from_key(key: str, characters=()) -> dict | None:
    """One model record from a prefab's container path (None: not a unit prefab).

    ``unit/figure/asagi_costume_1_f/asagi_costume_1_f.prefab`` -> id ``asagi_costume_1_f``, group ``Asagi``,
    costume 1.  A figure without a costume number (``astaroth_rabbit_f``) and the other categories keep
    their prefab name; the group is the playable character the name starts with, else the name itself."""
    match = PREFAB.match(key)
    if match is None:
        return None
    category, folder, name = match.groups()
    model = {"id": name, "key": key, "category": category, "folder": folder, "bundle": UNIT_BUNDLE,
             "costume": None, "variant": ""}
    base = name
    costume = COSTUME.match(name)
    if category == "figure" and costume:
        base = costume.group("char")
        model["costume"] = int(costume.group("n"))
        model["variant"] = costume.group("rest").strip("_")
    elif category in ("figure", "character") and re.search(r"_[fgl]$", name):
        base = name[:-2]
        model["variant"] = {"f": "figure", "g": "game", "l": "lobby"}[name[-1]]
    owner = next((c for c in sorted(characters, key=len, reverse=True)
                  if base == c or base.startswith(c + "_")), None)
    if category in ("figure", "character") and owner:
        model["character"] = owner
        model["group"] = title(owner)
    else:
        model["character"] = ""
        model["group"] = title(base)
    model["name"] = title(base) if model["costume"] is None else "%s costume %d" % (title(base), model["costume"])
    return model


def signature() -> list:
    path = os.path.join(BUNDLE_DIR, UNIT_BUNDLE)
    return [os.path.getsize(path), int(os.path.getmtime(path))]


def discover_models(root: str = EXPORT_ROOT, game: Game | None = None, refresh: bool = False) -> list[dict]:
    """Every unit prefab of the game, cached in <root>/_meta/models.json until the unit bundle changes."""
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
        keys = sorted(k for k in game.container(UNIT_BUNDLE) if k.endswith(".prefab"))
        characters = sorted({m.group(2)[:-2] for m in map(PREFAB.match, keys)
                             if m and m.group(1) == "character" and re.search(r"_[gl]$", m.group(2))})
        models = [m for m in (model_from_key(k, characters) for k in keys) if m]
        data = {"signature": signature(), "characters": characters, "models": models}
        tc.save_json(cache, data)
    models = data["models"]
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    models.sort(key=lambda m: (order.get(m["category"], 9), m["group"].lower(), m["costume"] or 0, m["id"]))
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
            hits = [m for m in models if m["group"].lower() == p or m.get("character") == p]
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
