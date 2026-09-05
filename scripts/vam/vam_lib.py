"""Virt-A-Mate (VaM) content library shared by the export scripts.

Everything here is plain Python 3 + numpy; nothing imports bpy.  It covers:

* the package index: ``AddonPackages/**/*.var`` (zip files) plus the loose
  ``Custom/`` and ``Saves/`` folders, with VaM's ``SELF:`` /
  ``Creator.Package.latest:/`` reference resolution;
* the catalog of exportable things: looks (Person atoms in scenes and
  appearance presets), clothing items (``.vam`` + ``.vaj`` + ``.vab``) and hair
  items (listed only, the strand format is not converted);
* binary readers for the ``.vab`` DAZMesh store and the ``.vmb`` morph deltas;
* readers for the AssetStudioModCLI text dumps of the game's own bundles
  (``a_per`` person meshes, ``f_mb``/``m_mb`` built-in morph banks, ``f_c``/``m_c``
  texture-group tables, ``DAZCharacter`` skin table);
* the cache that materialises those dumps once into ``.npz``/``.json``;
* the model bundle writer (``model.json`` + ``model.npz`` + ``_textures``)
  consumed by the Blender worker.

Formats were reverse-engineered from the shipped data (see
scripts/vam/README.md, section "格式说明"); every assumption is asserted at
parse time so a surprising file fails loudly instead of producing garbage.
"""

import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

import numpy as np

# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def lenient_json_loads(text):
    """VaM writes JSON with trailing commas; strip them before parsing."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    text = text.lstrip("\ufeff")
    return json.loads(_TRAILING_COMMA.sub(r"\1", text))


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes")


def hsv_to_rgb(h, s, v):
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def storable_color(entry, default=None):
    """VaM stores colours as {"h","s","v"} strings."""
    if not isinstance(entry, dict):
        return default
    return list(hsv_to_rgb(as_float(entry.get("h")), as_float(entry.get("s")),
                           as_float(entry.get("v"), 1.0)))


# --------------------------------------------------------------------------
# Keys / names
# --------------------------------------------------------------------------

_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')


def sanitize(text, limit=80):
    text = _UNSAFE.sub("_", str(text)).strip("_. ")
    text = re.sub(r"_+", "_", text)
    return text[:limit] or "item"


def make_key(*parts):
    return "~".join(sanitize(p) for p in parts if p not in (None, ""))


# --------------------------------------------------------------------------
# Packages
# --------------------------------------------------------------------------

_VAR_NAME = re.compile(r"^(?P<creator>[^.]+)\.(?P<name>.+?)(?:\.(?P<version>\d+))?$")


class Package:
    """One ``.var`` archive, or the loose game folders as the ``local`` package."""

    def __init__(self, path, local=False):
        self.path = path
        self.local = local
        if local:
            self.creator, self.name, self.version = "local", "local", 0
        else:
            stem = os.path.basename(path)[:-4]
            match = _VAR_NAME.match(stem)
            if match:
                self.creator = match.group("creator")
                self.name = match.group("name")
                self.version = int(match.group("version") or 0)
            else:
                self.creator, self.name, self.version = "unknown", stem, 0
        self._zip = None
        self._names = None
        self._lower = None
        self._meta = None

    @property
    def id(self):
        if self.local:
            return "local"
        return "%s.%s.%d" % (self.creator, self.name, self.version)

    @property
    def group(self):
        """Creator.Name without the version, the unit ``.latest`` refers to."""
        return ("%s.%s" % (self.creator, self.name)).lower()

    # -- members -----------------------------------------------------------

    def _open(self):
        if self._zip is None:
            self._zip = zipfile.ZipFile(self.path)
        return self._zip

    def names(self):
        if self._names is None:
            if self.local:
                found = []
                for sub in ("Custom", "Saves"):
                    root = os.path.join(self.path, sub)
                    for dirpath, _dirs, files in os.walk(root):
                        rel = os.path.relpath(dirpath, self.path).replace("\\", "/")
                        for name in files:
                            found.append(posixpath.join(rel, name))
                self._names = found
            else:
                self._names = [n for n in self._open().namelist()
                               if not n.endswith("/")]
            self._lower = {n.lower(): n for n in self._names}
        return self._names

    def find(self, member):
        """Case-insensitive member lookup; returns the real name or None."""
        self.names()
        member = member.replace("\\", "/").lstrip("/")
        return self._lower.get(member.lower())

    def read(self, member):
        real = self.find(member)
        if real is None:
            raise FileNotFoundError("%s: %s" % (self.id, member))
        if self.local:
            with open(os.path.join(self.path, real), "rb") as handle:
                return handle.read()
        return self._open().read(real)

    def size(self, member):
        real = self.find(member)
        if real is None:
            return None
        if self.local:
            return os.path.getsize(os.path.join(self.path, real))
        return self._open().getinfo(real).file_size

    def extract_to(self, member, dest_path):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        real = self.find(member)
        if real is None:
            raise FileNotFoundError("%s: %s" % (self.id, member))
        if self.local:
            shutil.copyfile(os.path.join(self.path, real), dest_path)
        else:
            with self._open().open(real) as src, open(dest_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        return dest_path

    def meta(self):
        if self._meta is None:
            self._meta = {}
            if not self.local and self.find("meta.json"):
                try:
                    self._meta = lenient_json_loads(self.read("meta.json"))
                except (ValueError, KeyError):
                    self._meta = {}
        return self._meta


class PackageIndex:
    """All packages of one VaM install plus reference resolution."""

    def __init__(self, game_root):
        self.game_root = game_root
        self.packages = []
        self.by_id = {}
        self.groups = {}
        addon = os.path.join(game_root, "AddonPackages")
        if os.path.isdir(addon):
            for dirpath, _dirs, files in os.walk(addon):
                for name in sorted(files):
                    if name.lower().endswith(".var"):
                        self._add(Package(os.path.join(dirpath, name)))
        self.local = Package(game_root, local=True)
        self.by_id["local"] = self.local

    def _add(self, package):
        # The same package can sit in two folders (user copies); keep the first.
        low = package.id.lower()
        if any(low == existing.lower() for existing in self.by_id):
            return
        self.packages.append(package)
        self.by_id[package.id] = package
        self.groups.setdefault(package.group, []).append(package)

    def latest(self, group):
        candidates = self.groups.get(group.lower())
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.version)

    def package_for(self, ref):
        """``Creator.Name.latest`` / ``Creator.Name.3`` -> Package or None."""
        low = ref.lower()
        if low == "self":
            return None
        if low.endswith(".latest"):
            return self.latest(low[:-len(".latest")])
        match = re.match(r"^(.*)\.(\d+)$", ref)
        if match:
            for pid, pkg in self.by_id.items():
                if pid.lower() == low:
                    return pkg
            return self.latest(match.group(1))
        return self.latest(ref)

    def resolve(self, url, current):
        """Resolve a VaM url to ``(package, member)`` or ``(None, None)``.

        ``current`` is the package the referencing file lives in (``SELF:``).
        Plain ``Custom/...`` paths are looked up in the current package first
        (creators frequently forget the ``SELF:`` prefix) and then locally.
        """
        if not url:
            return None, None
        url = str(url).replace("\\", "/")
        if ":/" in url:
            ref, member = url.split(":/", 1)
            if ref.upper() == "SELF":
                package = current
            else:
                package = self.package_for(ref)
            if package is None:
                return None, None
            real = package.find(member)
            return (package, real) if real else (None, None)
        member = url.lstrip("/")
        for package in (current, self.local):
            if package is None:
                continue
            real = package.find(member)
            if real:
                return package, real
        return None, None


def region_from_morph_path(member):
    low = member.lower()
    for token in ("female_genitalia", "male_genitalia", "female", "male"):
        if "/morphs/%s/" % token in low:
            return token
    return None


# --------------------------------------------------------------------------
# Catalog entries
# --------------------------------------------------------------------------

class Entry:
    def __init__(self, kind, key, package, member, display, **extra):
        self.kind = kind
        self.key = key
        self.package = package
        self.member = member
        self.display = display
        self.extra = extra

    def to_row(self):
        row = {"kind": self.kind, "key": self.key, "package": self.package.id,
               "member": self.member, "display": self.display}
        row.update(self.extra)
        return row


def person_storables(atom):
    return {s.get("id"): s for s in atom.get("storables", []) if isinstance(s, dict)}


def _person_summary(atom):
    storables = person_storables(atom)
    geometry = storables.get("geometry", {})
    textures = storables.get("textures", {})
    custom_tex = sum(1 for k, v in textures.items() if k.endswith("Url") and v)
    return {
        "character": geometry.get("character") or "",
        "morphs": len(geometry.get("morphs", []) or []),
        "clothing": sum(1 for c in geometry.get("clothing", []) or []
                        if as_bool(c.get("enabled"), True)),
        "hair": sum(1 for c in geometry.get("hair", []) or []
                    if as_bool(c.get("enabled"), True)),
        "skinTextures": custom_tex,
    }


class Catalog:
    """Enumerates looks, clothing and hair across the package index."""

    def __init__(self, index):
        self.index = index
        self._entries = None

    def entries(self, kinds=("look", "clothing", "hair")):
        if self._entries is None:
            self._entries = self._scan()
        return [e for e in self._entries if e.kind in kinds]

    def _scan(self):
        entries = []
        seen = set()

        def add(entry):
            base = entry.key
            counter = 2
            while entry.key.lower() in seen:
                entry.key = "%s~%d" % (base, counter)
                counter += 1
            seen.add(entry.key.lower())
            entries.append(entry)

        packages = list(self.index.packages) + [self.index.local]
        for package in packages:
            for member in package.names():
                low = member.lower()
                if low.startswith("saves/scene/") and low.endswith(".json"):
                    self._scan_scene(package, member, add)
                elif (low.startswith("custom/atom/person/appearance/")
                        and low.endswith(".vap")):
                    self._scan_preset(package, member, add)
                elif low.startswith("custom/clothing/") and low.endswith(".vam"):
                    self._scan_item(package, member, "clothing", add)
                elif low.startswith("custom/hair/") and low.endswith(".vam"):
                    self._scan_item(package, member, "hair", add)
        return entries

    def _scan_scene(self, package, member, add):
        try:
            data = lenient_json_loads(package.read(member))
        except (ValueError, KeyError, OSError):
            return
        atoms = data.get("atoms") if isinstance(data, dict) else None
        if not isinstance(atoms, list):
            return
        scene = posixpath.splitext(posixpath.basename(member))[0]
        for atom in atoms:
            if not isinstance(atom, dict) or atom.get("type") != "Person":
                continue
            summary = _person_summary(atom)
            person = atom.get("id") or "Person"
            add(Entry("look", make_key(package.id, scene, person), package, member,
                      "%s / %s" % (scene, person), source="scene", person=person,
                      **summary))

    def _scan_preset(self, package, member, add):
        try:
            data = lenient_json_loads(package.read(member))
        except (ValueError, KeyError, OSError):
            return
        if not isinstance(data, dict) or "storables" not in data:
            return
        summary = _person_summary(data)
        preset = posixpath.splitext(posixpath.basename(member))[0]
        add(Entry("look", make_key(package.id, preset), package, member, preset,
                  source="preset", person=None, **summary))

    def _scan_item(self, package, member, kind, add):
        base = member[:-4]
        vab = package.find(base + ".vab")
        try:
            meta = lenient_json_loads(package.read(member))
        except (ValueError, KeyError, OSError):
            meta = {}
        display = meta.get("displayName") or posixpath.basename(base)
        uid = meta.get("uid") or ("%s:%s" % (meta.get("creatorName", ""), display))
        exportable = False
        if vab is not None:
            try:
                head = package.read(vab)[:96]
                exportable = is_dazmesh_vab(head) or (kind == "hair"
                                                      and is_runtime_hair_vab(head))
            except (OSError, KeyError):
                exportable = False
        add(Entry(kind, make_key(package.id, display), package, member, display,
                  uid=uid, itemType=meta.get("itemType", ""),
                  creator=meta.get("creatorName", ""), hasMesh=vab is not None,
                  exportable=exportable))

    def by_uid(self, uid):
        """Clothing/hair entry whose ``.vam`` uid matches (``Creator:Name``)."""
        low = str(uid).lower()
        for entry in self.entries(("clothing", "hair")):
            if str(entry.extra.get("uid", "")).lower() == low:
                return entry
        return None

    def select(self, wanted, indices=(), kinds=("look", "clothing", "hair")):
        """Resolve ``--only`` names (exact key, else unique substring) and indices."""
        pool = self.entries(kinds)
        chosen = []
        unknown = []
        for want in wanted:
            low = want.lower()
            exact = [e for e in pool if e.key.lower() == low]
            if exact:
                chosen.extend(exact)
                continue
            partial = [e for e in pool
                       if low in e.key.lower() or low in e.display.lower()]
            if len(partial) == 1:
                chosen.extend(partial)
            elif not partial:
                unknown.append("%s (no match)" % want)
            else:
                unknown.append("%s (ambiguous: %s)" % (
                    want, ", ".join(e.key for e in partial[:6])))
        for number in indices:
            if 1 <= number <= len(pool):
                chosen.append(pool[number - 1])
            else:
                unknown.append("#%d (out of range 1..%d)" % (number, len(pool)))
        unique = []
        for entry in chosen:
            if entry not in unique:
                unique.append(entry)
        return unique, unknown


# --------------------------------------------------------------------------
# .vab (DynamicStore / DAZMesh) and .vmb
# --------------------------------------------------------------------------

class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def string(self):
        # .NET BinaryWriter: 7-bit encoded length + UTF-8 bytes.
        length = shift = 0
        while True:
            byte = self.data[self.pos]
            self.pos += 1
            length |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        value = self.data[self.pos:self.pos + length].decode("utf-8")
        self.pos += length
        return value

    def int32(self):
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def floats(self, count):
        arr = np.frombuffer(self.data, dtype="<f4", count=count, offset=self.pos)
        self.pos += 4 * count
        return arr

    def ints(self, count):
        arr = np.frombuffer(self.data, dtype="<i4", count=count, offset=self.pos)
        self.pos += 4 * count
        return arr


class DazMesh:
    """Polygon mesh with per-polygon material and a separate UV vertex set.

    ``poly_idx`` / ``uv_poly_idx`` are flat index arrays; ``poly_len`` gives the
    vertex count per polygon and ``poly_mat`` its material index.
    """

    def __init__(self, name, material_names, verts, poly_mat, poly_len, poly_idx,
                 uv_poly_idx, uvs, ids=()):
        self.name = name
        self.ids = list(ids)
        self.material_names = list(material_names)
        self.verts = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
        self.poly_mat = np.asarray(poly_mat, dtype=np.int32)
        self.poly_len = np.asarray(poly_len, dtype=np.int32)
        self.poly_idx = np.asarray(poly_idx, dtype=np.int32)
        self.uv_poly_idx = np.asarray(uv_poly_idx, dtype=np.int32)
        self.uvs = np.asarray(uvs, dtype=np.float32).reshape(-1, 2)

    @property
    def num_verts(self):
        return int(self.verts.shape[0])

    @property
    def num_polys(self):
        return int(self.poly_len.shape[0])


def is_dazmesh_vab(head):
    try:
        reader = _Reader(head)
        return (reader.string() == "DynamicStore" and reader.string() == "1.0"
                and reader.string() == "DAZMesh")
    except (IndexError, UnicodeDecodeError, struct.error):
        return False


def _read_poly_list(reader, count, limit):
    mats = np.empty(count, dtype=np.int32)
    lens = np.empty(count, dtype=np.int32)
    chunks = []
    for i in range(count):
        mat = reader.int32()
        size = reader.int32()
        if size not in (3, 4):
            raise ValueError("polygon %d has %d vertices" % (i, size))
        mats[i] = mat
        lens[i] = size
        chunks.append(reader.ints(size))
    idx = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int32)
    if idx.size and (idx.min() < 0 or idx.max() >= limit):
        raise ValueError("polygon index out of range (%d vertices)" % limit)
    return mats, lens, idx


def parse_dazmesh_vab(data):
    """Parse the DAZMesh section of a clothing ``.vab``.

    Layout (little-endian, strings are 7-bit-length prefixed UTF-8):
      "DynamicStore" "1.0" "DAZMesh" "1.0"
      name, nodeId, sceneNodeId, geometryId         (4 strings)
      int numVerts, Vector3[numVerts]
      int numMaterials, string[numMaterials]
      int numPolys, {int material, int count, int[count]}[numPolys]  base polys
      {int material, int count, int[count]}[numPolys]                UV polys
      int numUVVerts, Vector2[numUVVerts]
      int numMapped, {int uvVert, int baseVert}[numMapped]   (numUVVerts-numVerts)
      ... skin-wrap / simulation data (not needed for a static export)
    """
    reader = _Reader(data)
    magic = [reader.string() for _ in range(4)]
    if magic[0] != "DynamicStore" or magic[2] != "DAZMesh":
        raise ValueError("not a DAZMesh DynamicStore: %r" % (magic,))
    name = reader.string()
    ids = [reader.string() for _ in range(3)]
    num_verts = reader.int32()
    if not 0 < num_verts < 5_000_000:
        raise ValueError("implausible vertex count %d" % num_verts)
    verts = reader.floats(num_verts * 3).reshape(-1, 3)
    num_materials = reader.int32()
    if not 0 < num_materials < 1000:
        raise ValueError("implausible material count %d" % num_materials)
    materials = [reader.string() for _ in range(num_materials)]
    num_polys = reader.int32()
    if not 0 < num_polys < 20_000_000:
        raise ValueError("implausible polygon count %d" % num_polys)
    poly_mat, poly_len, poly_idx = _read_poly_list(reader, num_polys, num_verts)
    if poly_mat.max() >= num_materials:
        raise ValueError("polygon material index out of range")
    _uv_mat, uv_len, uv_idx = _read_poly_list(reader, num_polys, 1 << 30)
    if not np.array_equal(uv_len, poly_len):
        raise ValueError("UV polygon sizes differ from base polygon sizes")
    num_uv_verts = reader.int32()
    if not num_verts <= num_uv_verts < 8 * num_verts + 16:
        raise ValueError("implausible UV vertex count %d (verts %d)"
                         % (num_uv_verts, num_verts))
    if uv_idx.max() >= num_uv_verts:
        raise ValueError("UV polygon index out of range")
    uvs = reader.floats(num_uv_verts * 2).reshape(-1, 2)
    num_mapped = reader.int32()
    if num_mapped != num_uv_verts - num_verts:
        raise ValueError("UV map count %d != %d" % (num_mapped, num_uv_verts - num_verts))
    return DazMesh(name, materials, verts.copy(), poly_mat, poly_len, poly_idx,
                   uv_idx, uvs.copy(), ids)


HAIR_STORE = "RuntimeHairGeometryCreator"


def is_runtime_hair_vab(head):
    try:
        reader = _Reader(head)
        if reader.string() != "DynamicStore" or reader.string() != "1.0":
            return False
        reader.pos += 1                     # store-count byte (always 1)
        return reader.string() == HAIR_STORE
    except (IndexError, UnicodeDecodeError, struct.error):
        return False


class HairGuides:
    """VaM strand hair: one styled guide curve per scalp vertex.

    ``strands`` holds the guides that actually exist (VaM keeps a slot per
    scalp vertex; masked-out vertices have zero points).  Points are in metres
    in the same space as the base body, i.e. the unmorphed default figure.
    """

    def __init__(self, scalp, version, segments, segment_length, scalp_verts, mask,
                 roots, strands):
        self.scalp = scalp
        self.version = version
        self.segments = segments
        self.segment_length = segment_length
        self.scalp_verts = scalp_verts
        self.mask = mask
        self.roots = roots
        self.strands = strands

    @property
    def scalp_token(self):
        """'UdaneScalp' -> 'udane', the substring that names the scalp mesh."""
        return re.sub(r"scalp$", "", self.scalp.lower()).strip(" _-") or self.scalp.lower()


def parse_hair_vab(data):
    """Parse a ``RuntimeHairGeometryCreator`` DynamicStore (VaM sim hair).

    Layout:
      "DynamicStore" "1.0" byte 1 "RuntimeHairGeometryCreator" version scalpName
      int segments, float segmentLength, byte, int numScalpVerts, byte[num] mask
      int numScalpVerts, {int vertexIndex, int numPoints, Vector3[numPoints]}[num]
      ... style / rigidity data (not needed)
    """
    reader = _Reader(data)
    if reader.string() != "DynamicStore":
        raise ValueError("not a DynamicStore")
    reader.string()
    reader.pos += 1
    if reader.string() != HAIR_STORE:
        raise ValueError("not a RuntimeHairGeometryCreator store")
    version = reader.string()
    scalp = reader.string()
    segments = reader.int32()
    segment_length = struct.unpack_from("<f", data, reader.pos)[0]
    reader.pos += 4
    reader.pos += 1
    count = reader.int32()
    if not 0 < count < 200000 or not 0 < segments < 1000:
        raise ValueError("implausible hair header (%d scalp verts, %d segments)"
                         % (count, segments))
    mask = np.frombuffer(data, dtype=np.uint8, count=count, offset=reader.pos).copy()
    reader.pos += count
    if reader.int32() != count:
        raise ValueError("hair strand table count mismatch")
    roots, strands = [], []
    for k in range(count):
        index = reader.int32()
        points = reader.int32()
        if index != k or points < 0 or points > 4096:
            raise ValueError("hair strand %d malformed (index %d, %d points)"
                             % (k, index, points))
        if points:
            strands.append(reader.floats(points * 3).reshape(-1, 3).copy())
            roots.append(k)
        # zero-point slots carry no data
    return HairGuides(scalp, version, segments, segment_length, count, mask,
                      np.asarray(roots, dtype=np.int32), strands)


def drop_unstyled_guides(strands, segment_length, min_length=0.15, straightness=0.985,
                         hanging=-0.6):
    """Remove guides that are still VaM's initial straight line.

    A guide the creator never styled is a perfectly straight run along the
    scalp normal; in VaM the simulation drags it into the hair, in a static
    export it sticks out of the head like a wire.  Long hanging hair is also
    nearly straight, so a straight strand is only dropped when it does not
    point mostly down (tip-root y component above ``hanging`` x its length).
    """
    kept, dropped = [], 0
    for strand in strands:
        strand = np.asarray(strand, dtype=np.float32)
        if strand.shape[0] < 3:
            kept.append(strand)
            continue
        path = float(np.linalg.norm(np.diff(strand, axis=0), axis=1).sum())
        delta = strand[-1] - strand[0]
        span = float(np.linalg.norm(delta))
        straight = path >= min_length and span / max(path, 1e-9) >= straightness
        points_down = delta[1] / max(span, 1e-9) <= hanging
        if straight and not points_down:
            dropped += 1
            continue
        kept.append(strand)
    return kept, dropped


def hair_children(strands, count, spread, seed=0):
    """Fan each guide out into ``count`` strands (guide + offset copies).

    VaM multiplies guides at render time (hairMultiplier x curveDensity) with
    random spread; this cheap stand-in offsets copies within ``spread`` metres
    around the root, widening slightly toward the tip so clumps read as hair
    rather than as a comb of parallel wires.
    """
    rng = np.random.default_rng(seed)
    out = []
    for guide in strands:
        guide = np.asarray(guide, dtype=np.float32)
        out.append(guide)
        if count <= 1 or guide.shape[0] < 2:
            continue
        axis = guide[-1] - guide[0]
        norm = np.linalg.norm(axis)
        axis = axis / norm if norm > 1e-9 else np.asarray([0, 1, 0], np.float32)
        helper = np.asarray([1, 0, 0], np.float32) if abs(axis[0]) < 0.9 \
            else np.asarray([0, 0, 1], np.float32)
        u = np.cross(axis, helper)
        u /= max(np.linalg.norm(u), 1e-9)
        v = np.cross(axis, u)
        t = np.linspace(0.0, 1.0, guide.shape[0], dtype=np.float32)[:, None]
        widen = 0.6 + 0.8 * t
        for _ in range(count - 1):
            angle = rng.uniform(0, 2 * np.pi)
            radius = spread * np.sqrt(rng.uniform(0.05, 1.0))
            offset = (np.cos(angle) * u + np.sin(angle) * v) * radius
            out.append(guide + offset[None, :] * widen)
    return out


def parse_vmb(data):
    """``.vmb``: int32 count, then {int32 vertex, float x, y, z} records."""
    count = struct.unpack_from("<i", data, 0)[0]
    if len(data) != 4 + 16 * count:
        raise ValueError("vmb size %d does not match %d deltas" % (len(data), count))
    records = np.frombuffer(data, dtype=np.dtype([("v", "<i4"), ("d", "<f4", (3,))]),
                            count=count, offset=4)
    return records["v"].astype(np.int32), records["d"].astype(np.float32)


# --------------------------------------------------------------------------
# AssetStudio text dumps
# --------------------------------------------------------------------------

def _dump_header(path):
    """Top-level scalar fields of a MonoBehaviour dump (stops at the arrays)."""
    header = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("\t") and not line.startswith("\t\t"):
                stripped = line.strip()
                if " = " in stripped:
                    key, value = stripped.split(" = ", 1)
                    header[key.split()[-1]] = value.strip().strip('"')
                elif stripped.endswith(" _baseVertices") or stripped.endswith(" _morphs"):
                    break
    return header


def parse_dump_mesh(path):
    """Read a ``DAZMesh``/``DAZMergedMesh`` MonoBehaviour dump into a DazMesh.

    Uses ``_baseVertices``, ``_basePolyList`` (materialNum + vertices),
    ``_UVPolyList``, ``_OrigUV`` and ``_materialNames``.  Returns the mesh and
    the header fields (geometryId, counts) as a dict.
    """
    verts, uvs, materials = [], [], []
    lists = {"_basePolyList": ([], [], []), "_UVPolyList": ([], [], [])}
    header = {}
    section = None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("\t") and not line.startswith("\t\t"):
                stripped = line.strip()
                if " = " in stripped:
                    key, value = stripped.split(" = ", 1)
                    header[key.split()[-1]] = value.strip().strip('"')
                    section = None
                else:
                    section = stripped.split()[-1]
                continue
            if section is None:
                continue
            stripped = line.strip()
            if section == "_baseVertices":
                if stripped.startswith("float "):
                    verts.append(float(stripped[10:]))
            elif section == "_OrigUV":
                if stripped.startswith("float "):
                    uvs.append(float(stripped[10:]))
            elif section == "_materialNames":
                if stripped.startswith("string data = "):
                    materials.append(stripped[14:].strip('"'))
            elif section in lists:
                mats, lens, idx = lists[section]
                if stripped.startswith("int materialNum = "):
                    mats.append(int(stripped[18:]))
                    lens.append(0)
                elif stripped.startswith("int data = "):
                    idx.append(int(stripped[11:]))
                    lens[-1] += 1
    verts = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
    uvs = np.asarray(uvs, dtype=np.float32).reshape(-1, 2)
    base_mat, base_len, base_idx = (np.asarray(a, dtype=np.int32)
                                    for a in lists["_basePolyList"])
    _uv_mat, uv_len, uv_idx = (np.asarray(a, dtype=np.int32) for a in lists["_UVPolyList"])
    num_polys = int(header.get("_numBasePolygons", base_len.size))
    if base_len.size != num_polys or uv_len.size != num_polys:
        raise ValueError("%s: polygon count mismatch %d/%d/%d"
                         % (path, base_len.size, uv_len.size, num_polys))
    if not np.array_equal(base_len, uv_len):
        raise ValueError("%s: base/UV polygon sizes differ" % path)
    if base_idx.size and base_idx.max() >= verts.shape[0]:
        raise ValueError("%s: polygon index beyond vertex count" % path)
    if uv_idx.size and uv_idx.max() >= uvs.shape[0]:
        raise ValueError("%s: UV polygon index beyond UV count" % path)
    mesh = DazMesh(header.get("geometryId", ""), materials, verts, base_mat, base_len,
                   base_idx, uv_idx, uvs)
    if mesh.num_verts != int(header.get("_numBaseVertices", mesh.num_verts)):
        raise ValueError("%s: vertex count mismatch" % path)
    if len(materials) != int(header.get("_numMaterials", len(materials))):
        raise ValueError("%s: material count mismatch" % path)
    return mesh, header


def parse_dump_morph_bank(path):
    """Yield (info, indices, deltas) per morph in a ``DAZMorphSubBank`` dump."""
    info = None
    idx = []
    deltas = []
    # In the dump the flags (visible / disable / isPoseControl) precede the
    # morphName they belong to, so they are parked here until the name arrives.
    pending = {}

    def flush():
        if info is None:
            return None
        return (info, np.asarray(idx, dtype=np.int32),
                np.asarray(deltas, dtype=np.float32).reshape(-1, 3))

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("UInt8 isPoseControl = "):
                pending["isPoseControl"] = stripped[22:] == "1"
                continue
            if stripped.startswith("string morphName = "):
                done = flush()
                if done is not None:
                    yield done
                info = {"name": stripped[19:].strip('"'),
                        "isPoseControl": pending.get("isPoseControl", False)}
                pending = {}
                idx, deltas = [], []
            elif info is None:
                continue
            elif stripped.startswith("int vertex = "):
                idx.append(int(stripped[13:]))
            elif stripped.startswith("float x = ") or stripped.startswith("float y = ") \
                    or stripped.startswith("float z = "):
                deltas.append(float(stripped[10:]))
            elif stripped.startswith("string displayName = "):
                info["displayName"] = stripped[21:].strip('"')
            elif stripped.startswith("string region = "):
                info["region"] = stripped[16:].strip('"')
            elif stripped.startswith("string group = "):
                info["group"] = stripped[15:].strip('"')
            elif stripped.startswith("int numDeltas = "):
                info["numDeltas"] = int(stripped[16:])
    done = flush()
    if done is not None:
        yield done


def parse_dump_character(path):
    text = open(path, encoding="utf-8", errors="replace").read()

    def grab(key):
        match = re.search(r'\b%s = "?([^"\n]*)"?' % key, text)
        return match.group(1).strip() if match else ""

    return {
        "displayName": grab("displayName"),
        "bundle": grab("assetBundleName"),
        "asset": grab("assetName"),
        "isMale": grab("isMale") == "1",
        "uv": grab("UVname"),
    }


def parse_dump_texture_control(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    groups = {}
    for group in ("faceMaterialNums", "torsoMaterialNums", "limbMaterialNums",
                  "genitalMaterialNums"):
        match = re.search(r"vector %s\s*\n\s*Array Array\s*\n\s*int size = (\d+)"
                          r"((?:\s*\n\s*\[\d+\]\s*\n\s*int data = \d+)*)" % group, text)
        values = [int(v) for v in re.findall(r"int data = (\d+)", match.group(2))] \
            if match else []
        groups[group.replace("MaterialNums", "")] = values
    return groups


# --------------------------------------------------------------------------
# AssetStudioModCLI driver + cache
# --------------------------------------------------------------------------

def default_assetstudio():
    for candidate in (
        r"E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",
        r"E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI.exe",
    ):
        if os.path.isfile(candidate):
            return candidate
    return "AssetStudioModCLI.exe"


class AssetStudio:
    def __init__(self, exe, game_root):
        self.exe = exe
        self.game_root = game_root
        self.managed = os.path.join(game_root, "VaM_Data", "Managed")

    def bundle(self, name):
        path = os.path.join(self.game_root, "VaM_Data", "StreamingAssets", name)
        if not os.path.isfile(path):
            raise FileNotFoundError("bundle not found: %s" % path)
        return path

    def _run(self, args):
        cmd = [self.exe] + args + ["--log-level", "error"]
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            raise RuntimeError("AssetStudioModCLI failed (%d): %s\n%s"
                               % (completed.returncode, " ".join(cmd),
                                  completed.stdout[-2000:]))
        return completed.stdout

    def dump_monobehaviours(self, bundle_name, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        self._run([self.bundle(bundle_name), "-m", "dump", "-t", "monoBehaviour",
                   "-g", "none", "-f", "assetName_pathID", "-o", out_dir,
                   "--assembly-folder", self.managed])
        return out_dir

    def asset_names(self, bundle_name, asset_type="Texture2D"):
        with tempfile.TemporaryDirectory(prefix="vam_list_") as tmp:
            self._run([self.bundle(bundle_name), "-m", "info",
                       "--export-asset-list", "xml", "-o", tmp])
            xml_path = os.path.join(tmp, "assets.xml")
            if not os.path.isfile(xml_path):
                return []
            text = open(xml_path, encoding="utf-8", errors="replace").read()
        names = []
        for match in re.finditer(r"<Name>([^<]*)</Name>.*?<Type id=\"\d+\">(\w+)</Type>",
                                 text, re.S):
            if match.group(2) == asset_type:
                names.append(match.group(1))
        return names

    def export_textures(self, bundle_name, names, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        if not names:
            return []
        self._run([self.bundle(bundle_name), "-m", "export", "-t", "tex2d",
                   "-g", "none", "--image-format", "png",
                   "--filter-by-name", ",".join(names), "-o", out_dir])
        return [os.path.join(out_dir, n) for n in os.listdir(out_dir)]


TEXTURE_KIND_CODES = {"d": "diffuse", "m": "diffuse", "s": "specular",
                      "g": "gloss", "ss": "gloss", "n": "normal", "nm": "normal"}
TEXTURE_VARIANT = {"nude"}
_REGION_PATTERNS = (
    ("genitals", re.compile(r"genitalia|genitals?|gens|gen(?![a-z])")),
    ("mouth", re.compile(r"inmouth|mouth")),
    ("lashes", re.compile(r"lash(?:es)?")),
    ("eyes", re.compile(r"eyes?")),
    ("face", re.compile(r"face|head")),
    ("torso", re.compile(r"torso")),
    ("limbs", re.compile(r"limbs?")),
)


def classify_texture_name(name):
    """Map a skin-bundle texture name to (region, kind, rank); None if unusable.

    Names vary per creator ("V5BreeHeadM", "Kayla FaceD (B)", "faceBrowlessD",
    "Tina Face D Nude", "RyBelle_faceNM", "M5PhillipFace01S"), so this is a
    tolerant tokenizer: region word, then trailing letter groups decide the
    kind; digits and known neutral words only lower the rank.  Anything with
    an unknown letter group (B/BU/SI/SSS/TL/filled/...) is rejected.
    """
    low = name.lower()
    for region, pattern in _REGION_PATTERNS:
        match = pattern.search(low)
        if match:
            break
    else:
        return None
    tail = low[match.end():]
    # Neutral words are removed before tokenising: "g2f" would otherwise split
    # into g / 2 / f and the g be mistaken for a gloss code.
    tail = re.sub(r"g2[fm]|nipples|base", " ", tail)
    tokens = re.findall(r"[a-z]+|\d+", tail)
    kinds = []
    rank = 0
    for token in tokens:
        if token.isdigit():
            rank += 1
        elif token in TEXTURE_KIND_CODES:
            kinds.append(TEXTURE_KIND_CODES[token])
        elif token in TEXTURE_VARIANT:
            rank += 1
        else:
            return None
    if len(kinds) > 1:
        return None
    kind = kinds[0] if kinds else "diffuse"
    return region, kind, rank


def pick_default_textures(names):
    """{(region, kind): best texture name} from a skin bundle's texture list."""
    best = {}
    for name in names:
        classified = classify_texture_name(name)
        if classified is None:
            continue
        region, kind, rank = classified
        current = best.get((region, kind))
        if current is None or (rank, len(name)) < (current[0], len(current[1])):
            best[(region, kind)] = (rank, name)
    return {key: value[1] for key, value in best.items()}


class VamCache:
    """One-time materialisation of the game's own person data.

    Layout under ``cache_dir``:
      characters.json         DAZCharacter table (display name -> bundle, gender)
      base_female.npz/.json   merged female mesh + texture groups + graft offsets
      base_male.npz/.json
      morphs_female.npz/.json built-in morph bank
      morphs_male.npz/.json
      textures/<bundle>/      default skin textures exported on demand
    """

    GENDER_BUNDLES = {
        "female": {"mesh": "GenesisFemale-1:Genitalia-default", "bank": "f_mb",
                   "skin": "f_c"},
        "male": {"mesh": "Genesis2Male:Genesis2MaleGenitalia", "bank": "m_mb",
                 "skin": "m_c"},
    }

    def __init__(self, cache_dir, studio, log=print):
        self.dir = cache_dir
        self.studio = studio
        self.log = log
        os.makedirs(cache_dir, exist_ok=True)
        self._bases = {}
        self._morphs = {}

    # -- characters --------------------------------------------------------

    def characters(self):
        path = os.path.join(self.dir, "characters.json")
        if not os.path.isfile(path):
            self.prepare_person()
        return json.load(open(path, encoding="utf-8"))

    def character(self, display_name):
        table = self.characters()
        if display_name in table:
            return table[display_name]
        for name, info in table.items():
            if name.lower() == str(display_name).lower():
                return info
        return None

    def gender_of(self, display_name):
        info = self.character(display_name)
        if info is None:
            low = str(display_name).lower()
            return "male" if low.startswith(("male", "futa")) else "female"
        return "male" if info["isMale"] else "female"

    # -- meshes ------------------------------------------------------------

    def prepare_person(self):
        """Dump ``a_per`` once and store both merged meshes + character table."""
        log = self.log
        with tempfile.TemporaryDirectory(prefix="vam_a_per_") as tmp:
            log("  dumping a_per (person meshes, characters) ...")
            self.studio.dump_monobehaviours("a_per", tmp)
            files = os.listdir(tmp)
            characters = {}
            for name in files:
                if name.startswith("DAZCharacter @"):
                    info = parse_dump_character(os.path.join(tmp, name))
                    if info["displayName"]:
                        characters[info["displayName"]] = info
            with open(os.path.join(self.dir, "characters.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(characters, handle, ensure_ascii=False, indent=1, sort_keys=True)
            components = {}
            merged = {}
            scalps = []
            for name in files:
                if name.startswith("DAZMesh @"):
                    header = _dump_header(os.path.join(tmp, name))
                    components[header.get("geometryId", "")] = int(
                        header.get("_numBaseVertices", 0))
                    if int(header.get("_numBaseVertices", 0)) < 5000 \
                            and "genital" not in header.get("geometryId", "").lower():
                        scalps.append(os.path.join(tmp, name))
                elif name.startswith("DAZMergedMesh @"):
                    header = _dump_header(os.path.join(tmp, name))
                    merged[header.get("geometryId", "")] = os.path.join(tmp, name)
            self._save_scalps(scalps)
            for gender, spec in self.GENDER_BUNDLES.items():
                target = None
                for geometry_id, path in merged.items():
                    if geometry_id.startswith(spec["mesh"]):
                        target = path
                        break
                if target is None:
                    raise RuntimeError("merged %s mesh not found in a_per" % gender)
                log("  parsing %s merged mesh ..." % gender)
                mesh, header = parse_dump_mesh(target)
                parts = header["geometryId"].split(":")
                offsets = {}
                cursor = 0
                for part in parts:
                    count = components.get(part)
                    if count is None:
                        raise RuntimeError("component %s of %s not found" % (part, gender))
                    offsets[part] = [cursor, count]
                    cursor += count
                if cursor != mesh.num_verts:
                    raise RuntimeError("%s components sum to %d, merged has %d"
                                       % (gender, cursor, mesh.num_verts))
                groups = self._texture_groups(spec["skin"])
                self._save_base(gender, mesh, {
                    "geometryId": header["geometryId"],
                    "components": offsets,
                    "bodyComponent": parts[0],
                    "genitalComponent": parts[1] if len(parts) > 1 else None,
                    "textureGroups": groups,
                    "materialNames": mesh.material_names,
                })

    def _save_scalps(self, paths):
        """Hair scalp caps (Soleil/Udane/Krayon/Leyton/Omri/pubic): small
        DAZMesh objects whose only material is 'scalp'.  Strand hair files
        name their scalp, and the cap hides the skin between strands."""
        table = []
        seen = set()
        for path in paths:
            try:
                mesh, header = parse_dump_mesh(path)
            except ValueError:
                continue
            materials = [m.lower() for m in mesh.material_names]
            if not materials or any(m not in ("scalp", "default") for m in materials):
                continue
            key = (header.get("nodeId", ""), mesh.num_verts)
            if key in seen:
                continue
            seen.add(key)
            index = len(table)
            np.savez_compressed(os.path.join(self.dir, "scalp_%d.npz" % index),
                                verts=mesh.verts, poly_mat=mesh.poly_mat,
                                poly_len=mesh.poly_len, poly_idx=mesh.poly_idx,
                                uv_poly_idx=mesh.uv_poly_idx, uvs=mesh.uvs)
            table.append({"nodeId": header.get("nodeId", ""),
                          "geometryId": header.get("geometryId", ""),
                          "vertices": mesh.num_verts, "file": "scalp_%d.npz" % index,
                          "materialNames": mesh.material_names})
        with open(os.path.join(self.dir, "scalps.json"), "w", encoding="utf-8") as handle:
            json.dump(table, handle, ensure_ascii=False, indent=1)

    def scalp_mesh(self, token, vertex_count):
        """DazMesh of the scalp cap a strand-hair file refers to, or None."""
        path = os.path.join(self.dir, "scalps.json")
        if not os.path.isfile(path):
            self.prepare_person()
        table = json.load(open(path, encoding="utf-8"))
        token = token.lower()
        for entry in table:
            if entry["vertices"] == vertex_count and token in entry["nodeId"].lower():
                data = np.load(os.path.join(self.dir, entry["file"]))
                return DazMesh(entry["geometryId"], entry["materialNames"], data["verts"],
                               data["poly_mat"], data["poly_len"], data["poly_idx"],
                               data["uv_poly_idx"], data["uvs"])
        return None

    def _texture_groups(self, skin_bundle):
        with tempfile.TemporaryDirectory(prefix="vam_skin_") as tmp:
            self.log("  dumping %s (texture group table) ..." % skin_bundle)
            self.studio.dump_monobehaviours(skin_bundle, tmp)
            for name in os.listdir(tmp):
                if name.startswith("DAZCharacterTextureControl @"):
                    return parse_dump_texture_control(os.path.join(tmp, name))
        raise RuntimeError("no DAZCharacterTextureControl in %s" % skin_bundle)

    def _save_base(self, gender, mesh, meta):
        np.savez_compressed(os.path.join(self.dir, "base_%s.npz" % gender),
                            verts=mesh.verts, poly_mat=mesh.poly_mat,
                            poly_len=mesh.poly_len, poly_idx=mesh.poly_idx,
                            uv_poly_idx=mesh.uv_poly_idx, uvs=mesh.uvs)
        with open(os.path.join(self.dir, "base_%s.json" % gender), "w",
                  encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=1)

    def base(self, gender):
        """(DazMesh, meta) of the merged body+genitalia mesh for a gender."""
        if gender not in self._bases:
            npz_path = os.path.join(self.dir, "base_%s.npz" % gender)
            if not os.path.isfile(npz_path):
                self.prepare_person()
            data = np.load(npz_path)
            meta = json.load(open(os.path.join(self.dir, "base_%s.json" % gender),
                                  encoding="utf-8"))
            mesh = DazMesh(meta["geometryId"], meta["materialNames"], data["verts"],
                           data["poly_mat"], data["poly_len"], data["poly_idx"],
                           data["uv_poly_idx"], data["uvs"])
            self._bases[gender] = (mesh, meta)
        return self._bases[gender]

    # -- built-in morphs ---------------------------------------------------

    def prepare_morphs(self, gender):
        bank = self.GENDER_BUNDLES[gender]["bank"]
        log = self.log
        with tempfile.TemporaryDirectory(prefix="vam_%s_" % bank) as tmp:
            log("  dumping %s (built-in %s morphs) ..." % (bank, gender))
            self.studio.dump_monobehaviours(bank, tmp)
            index = {}
            all_idx, all_delta = [], []
            cursor = 0
            log("  parsing morph bank ...")
            for name in sorted(os.listdir(tmp)):
                if not name.startswith("DAZMorphSubBank @"):
                    continue
                for info, idx, delta in parse_dump_morph_bank(os.path.join(tmp, name)):
                    if idx.size != delta.shape[0]:
                        raise RuntimeError("morph %s: %d indices / %d deltas"
                                           % (info["name"], idx.size, delta.shape[0]))
                    key = info["name"]
                    if key in index:
                        continue
                    index[key] = {"start": cursor, "count": int(idx.size),
                                  "isPoseControl": bool(info.get("isPoseControl")),
                                  "region": info.get("region", ""),
                                  "group": info.get("group", ""),
                                  "displayName": info.get("displayName", key)}
                    all_idx.append(idx)
                    all_delta.append(delta)
                    cursor += int(idx.size)
            if not index:
                raise RuntimeError("no morphs parsed from %s" % bank)
            np.savez_compressed(os.path.join(self.dir, "morphs_%s.npz" % gender),
                                idx=np.concatenate(all_idx),
                                delta=np.concatenate(all_delta))
            with open(os.path.join(self.dir, "morphs_%s.json" % gender), "w",
                      encoding="utf-8") as handle:
                json.dump(index, handle, ensure_ascii=False, indent=0)

    def morph_bank(self, gender):
        if gender not in self._morphs:
            npz_path = os.path.join(self.dir, "morphs_%s.npz" % gender)
            if not os.path.isfile(npz_path):
                self.prepare_morphs(gender)
            data = np.load(npz_path)
            index = json.load(open(os.path.join(self.dir, "morphs_%s.json" % gender),
                                   encoding="utf-8"))
            # Scenes refer to built-in morphs by *display* name ("Shoulders
            # Shrug"), the bank keys them by internal name ("CTRLShouldersShrug").
            lower = {}
            for key, info in index.items():
                lower.setdefault(info.get("displayName", key).lower(), key)
            for key in index:
                lower.setdefault(key.lower(), key)
            self._morphs[gender] = (index, lower, data["idx"], data["delta"])
        return self._morphs[gender]

    def builtin_morph(self, gender, name):
        """(info, indices, deltas) of a built-in morph, or None."""
        index, lower, idx, delta = self.morph_bank(gender)
        key = name if name in index else lower.get(str(name).lower())
        if key is None:
            return None
        info = index[key]
        start, count = info["start"], info["count"]
        return info, idx[start:start + count], delta[start:start + count]


    # -- default skin textures ---------------------------------------------

    def skin_textures(self, bundle, fallback_bundle=None):
        """{(region, kind): png path} for a character skin bundle (``f_c`` ...).

        Slots the bundle lacks (Ren skins ship no mouth/eye textures) fall back
        to the shared eye bundle and then to ``fallback_bundle`` (``f_c``/``m_c``).
        """
        if not bundle:
            return {}
        out_dir = os.path.join(self.dir, "textures", bundle)
        index_path = os.path.join(out_dir, "index.json")
        if os.path.isfile(index_path):
            table = json.load(open(index_path, encoding="utf-8"))
            return {tuple(k.split("|")): v for k, v in table.items()}
        chosen = {}
        sources = [bundle + "_mat", "p_eye_mat"]
        if fallback_bundle and fallback_bundle != bundle:
            sources.append(fallback_bundle + "_mat")
        for source in sources:
            try:
                found = self.studio.asset_names(source)
            except (RuntimeError, FileNotFoundError):
                found = []
            for key, tex in pick_default_textures(found).items():
                chosen.setdefault(key, (source, tex))
        by_source = {}
        for key, (source, tex) in chosen.items():
            by_source.setdefault(source, set()).add(tex)
        os.makedirs(out_dir, exist_ok=True)
        for source, wanted in by_source.items():
            self.log("  exporting %d default textures from %s ..." % (len(wanted), source))
            self.studio.export_textures(source, sorted(wanted), out_dir)
        table = {}
        for key, (_source, tex) in chosen.items():
            path = os.path.join(out_dir, tex + ".png")
            if os.path.isfile(path):
                table["|".join(key)] = path
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump(table, handle, ensure_ascii=False, indent=1, sort_keys=True)
        return {tuple(k.split("|")): v for k, v in table.items()}



def is_pose_morph(info):
    """Pose morphs are skipped for a rest-pose export.

    VaM's own ``isPoseControl`` flag is unreliable for the built-in CTRL
    morphs ("Shoulders Shrug" has it off), so the bank group is consulted too.
    """
    if not info:
        return False
    if as_bool(info.get("isPoseControl")):
        return True
    group = str(info.get("group", "")).lower()
    region = str(info.get("region", "")).lower()
    return group.startswith("pose") or region.startswith("pose")


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

def to_blender(verts):
    """VaM/Unity metres (Y up, +Z forward, +X = character's right) -> Blender.

    Blender: Z up, the character faces -Y, its right hand at -X.  This is a
    mirror (det -1), so polygon winding must be reversed alongside.
    """
    verts = np.asarray(verts, dtype=np.float32)
    out = np.empty_like(verts)
    out[:, 0] = -verts[:, 0]
    out[:, 1] = -verts[:, 2]
    out[:, 2] = verts[:, 1]
    return out


def transfer_displacement(points, base_verts, displaced_verts, k=4, chunk=512):
    """Move ``points`` with the k nearest base vertices (inverse-distance weights).

    Used to carry a look's morphs onto clothing meshes, which VaM ships fitted
    to the unmorphed body.  Brute force in chunks; 40k x 23k fits comfortably.
    """
    points = np.asarray(points, dtype=np.float32)
    delta = np.asarray(displaced_verts, dtype=np.float64) - np.asarray(base_verts,
                                                                       dtype=np.float64)
    if not np.any(delta):
        return points.copy()
    out = np.empty_like(points)
    k = min(k, delta.shape[0])
    for start, block, dist in _squared_distances(points, base_verts, chunk):
        nearest = np.argpartition(dist, k - 1, axis=1)[:, :k]
        near_d = np.take_along_axis(dist, nearest, axis=1)
        # Inverse *squared* distance keeps the influence local (a vertex
        # sitting on the body follows that spot, not the far neighbours).
        weights = 1.0 / (np.maximum(near_d, 0.0) + 1e-8)
        weights /= weights.sum(axis=1, keepdims=True)
        out[start:start + block.shape[0]] = (
            block + np.einsum("ik,ikj->ij", weights, delta[nearest])).astype(np.float32)
    return out


def _squared_distances(points, base_verts, chunk=512):
    """Yield (start, block, squared distance matrix) in float64 chunks.

    float64 matters: with metre coordinates the expanded |a|^2-2ab+|b|^2 form
    loses ~0.3 mm in float32, more than the skin-layer tolerance.
    """
    points = np.asarray(points, dtype=np.float64)
    base = np.asarray(base_verts, dtype=np.float64)
    base_sq = np.einsum("ij,ij->i", base, base)
    for start in range(0, points.shape[0], chunk):
        block = points[start:start + chunk]
        dist = base_sq[None, :] - 2.0 * block @ base.T
        dist += np.einsum("ij,ij->i", block, block)[:, None]
        yield start, block, dist


def nearest_distance(points, base_verts, chunk=512):
    """Distance from each point to its nearest base vertex (brute force)."""
    out = np.empty(np.asarray(points).shape[0], dtype=np.float32)
    for start, block, dist in _squared_distances(points, base_verts, chunk):
        out[start:start + block.shape[0]] = np.sqrt(np.maximum(dist.min(axis=1), 0.0))
    return out


def vertex_normals(verts, poly_len, poly_idx):
    """Area-weighted vertex normals from the (original-winding) polygons."""
    verts = np.asarray(verts, dtype=np.float32)
    normals = np.zeros_like(verts)
    cursor = 0
    for size in poly_len.tolist():
        idx = poly_idx[cursor:cursor + size]
        cursor += size
        a, b, c = verts[idx[0]], verts[idx[1]], verts[idx[2]]
        normal = np.cross(b - a, c - a)
        if size == 4:
            normal = normal + np.cross(c - a, verts[idx[3]] - a)
        normals[idx] += normal
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(length, 1e-12)


def skin_layer_fraction(points, body_verts, tolerance=0.002):
    """Share of points lying within ``tolerance`` metres of the body surface.

    Makeup, tattoo, nail and eye shells are shipped as meshes wrapped a
    fraction of a millimetre over the skin; they need BLEND-mode materials and
    a small outward push, or EEVEE's depth prepass z-fights them into lace.
    """
    if points.shape[0] == 0:
        return 0.0
    distance = nearest_distance(points, body_verts)
    return float(np.mean(distance < tolerance))


def clean_polygons(poly_len, poly_idx, uv_poly_idx, poly_mat, keep_mask=None):
    """Drop degenerate polygons (repeated vertex) and reverse winding.

    Returns (faces, loop_uv_index, face_mat) with faces as a list of tuples in
    reversed order, matching the mirrored coordinate conversion.
    """
    faces, uv_loops, mats = [], [], []
    cursor = 0
    for i, size in enumerate(poly_len.tolist()):
        idx = poly_idx[cursor:cursor + size]
        uv_idx = uv_poly_idx[cursor:cursor + size]
        cursor += size
        if keep_mask is not None and not keep_mask[i]:
            continue
        if len(set(idx.tolist())) != size:
            continue
        faces.append(tuple(int(v) for v in idx[::-1]))
        uv_loops.extend(int(v) for v in uv_idx[::-1])
        mats.append(int(poly_mat[i]))
    return faces, np.asarray(uv_loops, dtype=np.int32), np.asarray(mats, dtype=np.int32)


# --------------------------------------------------------------------------
# Model bundle writer (consumed by export_vam_model_blender.py)
# --------------------------------------------------------------------------

def material_spec(name, **kw):
    spec = {"name": name, "diffuse": None, "normal": None, "specular": None,
            "gloss": None, "alpha": None, "decal": None, "color": None,
            "alphaAdjust": 0.0, "transparent": False, "glass": False,
            "layer": False, "hair": False, "backface": True, "roughness": 0.55}
    spec.update(kw)
    return spec


class ModelBundle:
    """Accumulates objects + textures and writes model.json / model.npz."""

    def __init__(self, out_dir, key, kind, display):
        self.out_dir = out_dir
        self.texture_dir = os.path.join(out_dir, "_textures")
        self.key = key
        self.kind = kind
        self.display = display
        self.objects = []
        self.arrays = {}
        self.notes = {}
        self._texture_names = {}
        os.makedirs(self.texture_dir, exist_ok=True)

    def _unique_name(self, stem, ext):
        name = "%s%s" % (stem, ext)
        counter = 2
        taken = {v.lower() for v in self._texture_names.values()}
        while name.lower() in taken:
            name = "%s_%d%s" % (stem, counter, ext)
            counter += 1
        return name

    def add_texture(self, package, member):
        """Copy a texture out of its package; returns the relative file name."""
        if package is None or member is None:
            return None
        marker = (package.id, member.lower())
        if marker in self._texture_names:
            return self._texture_names[marker]
        stem = sanitize(posixpath.splitext(posixpath.basename(member))[0], 60)
        ext = posixpath.splitext(member)[1].lower() or ".png"
        name = self._unique_name(stem, ext)
        package.extract_to(member, os.path.join(self.texture_dir, name))
        self._texture_names[marker] = name
        return name

    def add_texture_file(self, path):
        if not path or not os.path.isfile(path):
            return None
        marker = ("file", os.path.normcase(path))
        if marker in self._texture_names:
            return self._texture_names[marker]
        stem = sanitize(os.path.splitext(os.path.basename(path))[0], 60)
        ext = os.path.splitext(path)[1].lower()
        name = self._unique_name(stem, ext)
        shutil.copyfile(path, os.path.join(self.texture_dir, name))
        self._texture_names[marker] = name
        return name

    def add_object(self, name, verts_vam, faces, loop_uvs, face_mat, materials,
                   role="mesh"):
        index = len(self.objects)
        prefix = "o%d_" % index
        verts = to_blender(verts_vam)
        total = sum(len(f) for f in faces)
        flat = np.fromiter((v for f in faces for v in f), dtype=np.int32, count=total)
        self.arrays[prefix + "verts"] = verts
        self.arrays[prefix + "face_len"] = np.asarray([len(f) for f in faces], dtype=np.int32)
        self.arrays[prefix + "face_idx"] = flat
        self.arrays[prefix + "face_mat"] = np.asarray(face_mat, dtype=np.int32)
        self.arrays[prefix + "loop_uv"] = np.asarray(loop_uvs, dtype=np.float32).reshape(-1, 2)
        self.objects.append({"name": name, "prefix": prefix, "role": role,
                             "materials": materials, "faces": len(faces),
                             "vertices": int(verts.shape[0])})

    def add_curves(self, name, strands_vam, material, radius, role="hair"):
        """Polyline strands (VaM coords) -> one curve object with a bevel."""
        index = len(self.objects)
        prefix = "o%d_" % index
        lengths = np.asarray([len(s) for s in strands_vam], dtype=np.int32)
        points = np.concatenate([np.asarray(s, dtype=np.float32) for s in strands_vam]) \
            if strands_vam else np.zeros((0, 3), dtype=np.float32)
        self.arrays[prefix + "points"] = to_blender(points)
        self.arrays[prefix + "strand_len"] = lengths
        self.objects.append({"name": name, "prefix": prefix, "role": role, "curve": True,
                             "materials": [material], "strands": int(lengths.size),
                             "vertices": int(points.shape[0]), "radius": float(radius)})

    def write(self):
        np.savez_compressed(os.path.join(self.out_dir, "model.npz"), **self.arrays)
        payload = {"key": self.key, "kind": self.kind, "display": self.display,
                   "textureDir": "_textures", "objects": self.objects,
                   "notes": self.notes}
        path = os.path.join(self.out_dir, "model.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        return path
