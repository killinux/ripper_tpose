"""Read one Taimanin Squad unit prefab out of the bundles into a Unity-space scene on disk.

    scene.json            nodes (the skeleton, world matrices), parts, materials, cloth groups
    parts/<name>.npz      vertices already skinned to the prefab pose, normals, UVs, weights,
                          triangles per sub-mesh, blend shapes as sparse deltas
    textures/<name>.png   every texture the materials use (normal maps unpacked to RGB)

build_blend.py turns that into the .blend.  Nothing here needs Blender; UnityPy + numpy only.

What the game data looks like (measured on 24_Kirara, see the README):

* the unit prefab ``prf_<n>`` holds the renderers (``costume_<n>``, ``hair_<n>``, ``face_<n>``,
  ``face_<n>_out``, ``face_<n>_mouth_in``) next to the skeleton ``Root/Bip001/...`` - a 3ds Max
  Biped (``Bip001 L UpperArm``), ``Bip001_B_*`` twist / joint helpers and ``Bone_*`` chains for
  hair, skirt, ribbons and the bust, simulated by Magica Cloth 2 (bone cloth);
* every skinned vertex is baked as  sum_i w_i * (World_i x BindPose_i) * v  with World_i from
  the prefab, i.e. what Unity draws before any animation; blend-shape deltas and normals go
  through the same per-vertex matrix;
* materials are ``Squad/SquadToon`` (the game's own toon shader): ``_BaseMap`` (tex_d),
  ``_InShadowMap`` (tex_s, the colour in shadow), ``_MaskMap`` (tex_m), ``_MatCapMap``,
  ``_SDFShadowMap`` (tex_on, the face shadow threshold), outline width / colour;
* the unit prefab is not always the whole character: what the game calls weapons are prefabs of their
  own in the unit's other bundle (``<n>_<Name>/Weapon/Prefab/prf_weapon_<n>_<grade>_<slot>``) that an
  ``AttachObject`` component hangs on a bone at run time - and for some units the "weapon" is an arm
  or a pair of legs (20_Natsume, 82_Tsuru, 71_SnakeLady, 47_Saika ...).  Scene.add_weapons hangs
  them on here.
"""
from __future__ import annotations

import os
import re

import numpy as np
import UnityPy
from UnityPy.classes import PPtr

import tsquad_common as tc

# VertexFormat (2019+) -> (numpy dtype, normaliser)
FORMATS = {
    0: (np.float32, None), 1: (np.float16, None),
    2: (np.uint8, 255.0), 3: (np.int8, 127.0),
    4: (np.uint16, 65535.0), 5: (np.int16, 32767.0),
    6: (np.uint8, None), 7: (np.int8, None),
    8: (np.uint16, None), 9: (np.int16, None),
    10: (np.uint32, None), 11: (np.int32, None),
}
CHANNELS = {0: "vertices", 1: "normals", 2: "tangents", 3: "colors", 12: "weights", 13: "bone_indices"}
for _i in range(8):
    CHANNELS[4 + _i] = "uv%d" % _i
NORMAL_PROPS = ("_BumpMap", "_BakedNormal", "_BumpBlendMap", "_NormalMap")
# components that make a transform a physics / effect helper, not a bone
HELPER_COMPONENTS = ("MagicaCloth", "MagicaCapsuleCollider", "MagicaSphereCollider", "MagicaPlaneCollider",
                     "ParticleSystem", "ParticleSystemRenderer", "MeshRenderer", "MeshFilter", "TrailRenderer",
                     "LineRenderer", "Light", "Camera", "Projector")


def _bytes(value) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return bytes(bytearray(value))


def trs_matrix(pos, rot, scale) -> np.ndarray:
    x, y, z, w = rot
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.asarray(scale, dtype=np.float64)
    m[:3, 3] = pos
    return m


def safe_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("_") or "x"


# ---------------------------------------------------------------- bundles
class Loader:
    """One UnityPy environment; bundles are added when something in them is needed."""

    def __init__(self, root: str = tc.EXPORT_ROOT):
        self.env = UnityPy.Environment()
        self.cabs = tc.cab_index(root)
        self.bundles: dict[str, object] = {}

    def load(self, bundle: str):
        if bundle not in self.bundles:
            path = os.path.join(tc.BUNDLE_DIR, bundle)
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            self.bundles[bundle] = self.env.load_file(path)
        return self.bundles[bundle]

    def serialized_files(self, bundle: str):
        return [f for f in self.load(bundle).files.values() if hasattr(f, "objects")]

    def container_object(self, bundle: str, guid: str, type_name: str = "GameObject"):
        """The object a catalog GUID names inside its bundle (the bundle container is keyed by GUID)."""
        for sf in self.serialized_files(bundle):
            for obj in sf.objects.values():
                if obj.type.name != "AssetBundle":
                    continue
                for key, info in obj.read().m_Container:
                    if key != guid:
                        continue
                    reader = self.deref(info.asset)
                    if reader is not None and reader.type.name == type_name:
                        return reader
        return None

    def deref(self, pptr):
        """ObjectReader behind a PPtr, loading the bundle an external file lives in; None if absent."""
        if pptr is None or not getattr(pptr, "m_PathID", 0):
            return None
        if pptr.m_FileID:
            sf = pptr.assetsfile
            if sf is None or pptr.m_FileID - 1 >= len(sf.externals):
                return None
            cab = sf.externals[pptr.m_FileID - 1].path.replace("\\", "/").rsplit("/", 1)[-1].lower()
            bundle = self.cabs.get(cab)
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


def pptr_of(tree: dict, assets_file) -> PPtr:
    return PPtr(m_FileID=tree.get("m_FileID", 0), m_PathID=tree.get("m_PathID", 0), assetsfile=assets_file)


# ---------------------------------------------------------------- meshes
def decode_mesh(reader) -> dict:
    """Unity 2022 Mesh object -> numpy arrays (vertex streams decoded from m_VertexData)."""
    tt = reader.read_typetree()
    vd = tt["m_VertexData"]
    count = vd["m_VertexCount"]
    packed = ((tt.get("m_CompressedMesh") or {}).get("m_Vertices") or {}).get("m_NumItems", 0)
    if not count and packed:
        return decode_compressed_mesh(reader, tt)
    data = _bytes(vd.get("m_DataSize") or b"")
    stream = tt.get("m_StreamData") or {}
    if not data and stream.get("size"):
        from UnityPy.helpers.ResourceReader import get_resource_data
        data = bytes(get_resource_data(stream["path"], reader.assets_file, stream["offset"], stream["size"]))
    out = {"name": tt.get("m_Name", ""), "vertex_count": count}
    channels = vd["m_Channels"]
    strides: dict[int, int] = {}
    for ch in channels:
        dim = ch["dimension"] & 0xF
        if dim:
            size = np.dtype(FORMATS[ch["format"]][0]).itemsize * dim
            strides[ch["stream"]] = max(strides.get(ch["stream"], 0), ch["offset"] + size)
    starts, pos = {}, 0
    for s in sorted(strides):
        starts[s] = pos
        pos = (pos + strides[s] * count + 15) & ~15
    for i, ch in enumerate(channels):
        dim = ch["dimension"] & 0xF
        if not dim or not count:
            continue
        dtype, norm = FORMATS[ch["format"]]
        itemsize = np.dtype(dtype).itemsize
        stride = strides[ch["stream"]]
        buf = np.frombuffer(data, dtype=np.uint8, count=stride * count, offset=starts[ch["stream"]])
        buf = buf.reshape(count, stride)[:, ch["offset"]:ch["offset"] + itemsize * dim]
        arr = np.ascontiguousarray(buf).view(dtype).reshape(count, dim)
        if norm:
            arr = arr.astype(np.float32) / norm
        out[CHANNELS.get(i, "ch%d" % i)] = arr
    wide = tt.get("m_IndexFormat") == 1
    indices = np.frombuffer(_bytes(tt["m_IndexBuffer"]), dtype=np.uint32 if wide else np.uint16).astype(np.int64)
    isz = 4 if wide else 2
    out["submeshes"] = []
    for sm in tt["m_SubMeshes"]:
        first = sm["firstByte"] // isz
        indices[first:first + sm["indexCount"]] += sm.get("baseVertex", 0)
        out["submeshes"].append((int(first), int(sm["indexCount"]), int(sm["topology"])))
    out["indices"] = indices
    bp = tt.get("m_BindPose") or []
    out["bindposes"] = np.array([[[m["e%d%d" % (r, c)] for c in range(4)] for r in range(4)] for m in bp],
                                dtype=np.float64).reshape(-1, 4, 4)
    out["shapes"] = decode_shapes(tt.get("m_Shapes") or {})
    return out


def decode_compressed_mesh(reader, tt: dict) -> dict:
    """Meshes saved with Mesh Compression (most monsters): the vertex streams are empty and the
    data sits bit-packed in m_CompressedMesh.  UnityPy's MeshHandler unpacks it."""
    from UnityPy.helpers.MeshHelper import MeshHandler

    handler = MeshHandler(reader.read())
    handler.process()
    verts = np.asarray(handler.m_Vertices, dtype=np.float32).reshape(-1, 3)
    count = len(verts)
    out = {"name": tt.get("m_Name", ""), "vertex_count": count, "vertices": verts}
    for attr, key, dim in (("m_Normals", "normals", 3), ("m_Colors", "colors", 4),
                           ("m_BoneWeights", "weights", 4), ("m_BoneIndices", "bone_indices", 4)):
        value = getattr(handler, attr, None)
        if value is not None and len(value) == count:
            arr = np.asarray(value, dtype=np.float32).reshape(count, -1)[:, :dim]
            out[key] = arr.astype(np.int64) if key == "bone_indices" else arr
    for i in range(8):
        value = getattr(handler, "m_UV%d" % i, None)
        if value is not None and len(value) == count:
            out["uv%d" % i] = np.asarray(value, dtype=np.float32).reshape(count, -1)
    indices = np.asarray(handler.m_IndexBuffer, dtype=np.int64)
    isz = 2 if getattr(handler, "m_Use16BitIndices", True) else 4
    out["submeshes"] = []
    for sm in tt["m_SubMeshes"]:
        first = sm["firstByte"] // isz
        indices[first:first + sm["indexCount"]] += sm.get("baseVertex", 0)
        out["submeshes"].append((int(first), int(sm["indexCount"]), int(sm["topology"])))
    out["indices"] = indices
    bp = tt.get("m_BindPose") or []
    out["bindposes"] = np.array([[[m["e%d%d" % (r, c)] for c in range(4)] for r in range(4)] for m in bp],
                                dtype=np.float64).reshape(-1, 4, 4)
    out["shapes"] = decode_shapes(tt.get("m_Shapes") or {})
    out["compressed"] = True
    return out


def decode_shapes(shapes: dict) -> list[dict]:
    """[{"name", "indices" (k,), "delta" (k,3), "normal" (k,3) or None}] - the last frame of each channel."""
    channels = shapes.get("channels") or []
    if not channels:
        return []
    verts = shapes.get("vertices") or []
    index = np.fromiter((v["index"] for v in verts), dtype=np.int64, count=len(verts))
    delta = np.array([(v["vertex"]["x"], v["vertex"]["y"], v["vertex"]["z"]) for v in verts],
                     dtype=np.float32).reshape(-1, 3)
    normal = np.array([(v["normal"]["x"], v["normal"]["y"], v["normal"]["z"]) for v in verts],
                      dtype=np.float32).reshape(-1, 3)
    frames = shapes.get("shapes") or []
    weights = shapes.get("fullWeights") or []
    out = []
    for ch in channels:
        if not ch["frameCount"]:
            continue
        fi = ch["frameIndex"] + ch["frameCount"] - 1
        fr = frames[fi]
        a, b = fr["firstVertex"], fr["firstVertex"] + fr["vertexCount"]
        name = re.sub(r"[\x00-\x1f\x7f]", "", ch["name"])      # 16_Asuka Black: "difficult_eye\x1f_L"
        out.append({"name": name, "indices": index[a:b], "delta": delta[a:b],
                    "normal": normal[a:b] if fr.get("hasNormals") else None,
                    "full_weight": float(weights[fi]) if fi < len(weights) else 100.0})
    return out


def skin_matrices(mesh: dict, bone_matrices: np.ndarray) -> np.ndarray:
    """Per-vertex blended 4x4: sum_k w_k * (World_bone x BindPose_bone).  A mesh without bone indices
    is rigid: every vertex rides the first matrix (its transform's world matrix)."""
    n = mesh["vertex_count"]
    if not len(bone_matrices):
        return np.tile(np.eye(4), (n, 1, 1))
    idx = mesh.get("bone_indices")
    if idx is None:
        return np.tile(np.asarray(bone_matrices[0], dtype=np.float64), (n, 1, 1))
    idx = np.clip(idx.astype(np.int64), 0, len(bone_matrices) - 1)
    w = mesh.get("weights")
    if w is None:
        w = np.zeros(idx.shape, dtype=np.float64)
        w[:, 0] = 1.0
    w = w.astype(np.float64)
    total = w.sum(axis=1, keepdims=True)
    w = np.where(total > 1e-8, w / np.maximum(total, 1e-8), np.eye(1, w.shape[1]))
    return np.einsum("nk,nkij->nij", w, bone_matrices[idx])


def drop_undrawn(mesh: dict, slots: int) -> int:
    """Unity draws sub-mesh i with the renderer's material slot i, and a sub-mesh beyond the last slot not
    at all.  Artists use that to switch pieces off: the white "glare" lenses of 257_Shizuru's glasses, the
    full-size horns under 125_Sokushitsuki's hat, spare mouth pieces - 11 units.  Removes those sub-meshes
    and the vertices only they use (in place); returns the number of triangles removed."""
    subs = mesh["submeshes"]
    extra = [s for i, s in enumerate(subs) if i >= slots]
    if not extra:
        return 0
    kept = [s for i, s in enumerate(subs) if i < slots]
    n = mesh["vertex_count"]
    idx = mesh["indices"]
    used = np.zeros(n, dtype=bool)
    for first, count, _topo in kept:
        ref = idx[first:first + count]
        used[ref[(ref >= 0) & (ref < n)]] = True
    left = int(used.sum())
    remap = np.cumsum(used) - 1
    new_idx = idx.copy()
    for first, count, _topo in kept:
        ref = idx[first:first + count]
        good = (ref >= 0) & (ref < n)
        new_idx[first:first + count] = np.where(good, remap[np.clip(ref, 0, n - 1)], left)   # bad stays out of range
    for key, value in list(mesh.items()):
        if isinstance(value, np.ndarray) and key not in ("indices", "bindposes") and len(value) == n:
            mesh[key] = value[used]
    for shape in mesh.get("shapes") or []:
        sel = shape["indices"]
        good = (sel >= 0) & (sel < n)
        good[good] = used[sel[good]]
        shape["indices"] = remap[sel[good]]
        shape["delta"] = shape["delta"][good]
        if shape.get("normal") is not None:
            shape["normal"] = shape["normal"][good]
    mesh["submeshes"], mesh["indices"], mesh["vertex_count"] = kept, new_idx, left
    return sum(count for _first, count, topo in extra if topo == 0) // 3


# ---------------------------------------------------------------- scene
class Scene:
    def __init__(self, loader: Loader, out_dir: str):
        self.loader = loader
        self.out_dir = out_dir
        self.nodes: dict[int, dict] = {}       # transform path id -> node
        self.parts: list[dict] = []
        self.materials: dict[str, dict] = {}
        self.cloth: list[dict] = []
        self.aliases: dict[str, str] = {}      # limb alias bone -> the Biped bone that takes its skin
        self.undrawn: list[dict] = []          # sub-meshes the game does not draw (no material slot)
        self.alias: dict = {}                  # (weapon prefab, transform id) -> the unit node that Ref_ bone stands for
        self.weapons: list[dict] = []          # weapon prefabs hung on the unit (add_weapons)
        self.weapons_left: list[dict] = []     # ... and the ones left out, with the reason
        self.warnings: list[str] = []
        self._mat_keys: dict[tuple, str] = {}
        self._tex_files: dict[tuple, str] = {}
        self._tex_names: set[str] = set()

    # ------------------------------------------------------------ hierarchy
    def _components(self, go):
        out = []
        for comp in go.m_Components:
            reader = self.loader.deref(getattr(comp, "component", comp))
            if reader is not None:
                out.append(reader)
        return out

    def _read_transform(self, tr_reader):
        """(Transform, GameObject, component readers, local matrix, component types, script class names)."""
        tr = tr_reader.read()
        go = self.loader.read(tr.m_GameObject)
        comps = self._components(go)
        p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
        local = trs_matrix((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))
        types, monos = [], []
        for c in comps:
            types.append(c.type.name)
            if c.type.name == "MonoBehaviour":
                try:
                    script = self.loader.read(c.read().m_Script)
                    monos.append(getattr(script, "m_ClassName", "") or "")
                except Exception:  # noqa: BLE001 - a script we cannot resolve is just unnamed
                    monos.append("")
        return tr, go, comps, local, types, monos

    def _add_node(self, nid, name, parent, local, world, active, types, monos, comps, weapon=None):
        self.nodes[nid] = {"id": nid, "name": name, "parent": parent, "local": local, "world": world,
                           "active": active, "types": types, "monos": monos, "components": comps, "children": []}
        if weapon:
            self.nodes[nid]["weapon"] = weapon
        if parent is not None:
            self.nodes[parent]["children"].append(nid)

    def walk(self, root_go_reader):
        """Read every transform under the prefab root; returns the root node id."""
        root_go = root_go_reader.read()
        root_tr = next(c for c in self._components(root_go) if c.type.name == "Transform")
        stack = [(root_tr, None, np.eye(4), True)]
        root_id = root_tr.path_id
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
        return root_id

    # ------------------------------------------------------------ weapon prefabs
    def attach_prefab(self, prefab_reader, tag: str, names: dict):
        """Hang a weapon prefab on the unit the way the game's AttachObject component does at run time:
        under the unit transform ``kBoneName``, its own transform reset when ``kInitTrans`` is set.

        A transform called ``Ref_<bone>`` is the prefab's stand-in for the unit's bone of that name (the
        animation clips key both with the same curves): no node is made for it, whatever is skinned to it
        is skinned to the unit's bone, and its children hang from the unit's bone.  So is a transform that
        has a unit bone's very name and lies exactly on it.  Everything else becomes a node of its own
        ("weapon": tag) under the unit skeleton.  `names`: {unit transform name: node id}.
        Returns {"root", "bone", "data"}, or a string saying why the prefab was not attached."""
        root_go = prefab_reader.read()
        root_tr = next(c for c in self._components(root_go) if c.type.name == "Transform")
        tr, go, comps, local, types, monos = self._read_transform(root_tr)
        data = None
        for comp, cls in zip([c for c in comps if c.type.name == "MonoBehaviour"], monos):
            if cls == "AttachObject":
                try:
                    data = comp.read_typetree()
                except Exception:  # noqa: BLE001
                    data = None
        if data is None:
            return "no AttachObject component"
        target = names.get(data.get("kBoneName"))
        if target is None:
            return "the unit has no transform called %r" % data.get("kBoneName")
        base = self.nodes[target]
        reset = bool(data.get("kInitTrans", 1))
        root_id = (tag, root_tr.path_id)
        world = base["world"] if reset else base["world"] @ local
        active = base["active"] and bool(go.m_IsActive)
        self._add_node(root_id, go.m_Name, target, np.eye(4) if reset else local, world, active, types, monos, comps, tag)
        stack = [(child, root_id, world, active) for child in reversed(tr.m_Children)]
        while stack:
            pptr, parent, parent_world, parent_active = stack.pop()
            tr_reader = self.loader.deref(pptr)
            if tr_reader is None:
                continue
            tr, go, comps, local, types, monos = self._read_transform(tr_reader)
            world = parent_world @ local
            active = parent_active and bool(go.m_IsActive)
            key = (tag, tr_reader.path_id)
            ref = go.m_Name.startswith(REF_PREFIX)
            twin = names.get(go.m_Name[len(REF_PREFIX):] if ref else go.m_Name)
            if twin is not None and (ref or np.allclose(world, self.nodes[twin]["world"], atol=2e-3)):
                self.alias[key] = twin
                parent, world = twin, self.nodes[twin]["world"]
            else:
                self._add_node(key, go.m_Name, parent, local, world, active, types, monos, comps, tag)
                parent = key
            stack.extend((child, parent, world, active) for child in reversed(tr.m_Children))
        return {"root": root_id, "bone": data.get("kBoneName"), "data": data}

    def _weapon_renderers(self, tag: str):
        """[(node, kind, bone node ids)] of the renderers a weapon prefab draws (active, enabled, with a mesh)."""
        out = []
        for node in self.nodes.values():
            if node.get("weapon") != tag or not node["active"]:
                continue
            by_type = {c.type.name: c for c in node["components"]}
            if "SkinnedMeshRenderer" in by_type:
                r = by_type["SkinnedMeshRenderer"].read()
                if r.m_Enabled and r.m_Mesh.m_PathID:
                    out.append((node, "skinned", [self._nid(node, b.m_FileID, b.m_PathID) for b in r.m_Bones]))
            elif "MeshRenderer" in by_type and "MeshFilter" in by_type:
                r = by_type["MeshRenderer"].read()
                if r.m_Enabled and by_type["MeshFilter"].read().m_Mesh.m_PathID:
                    out.append((node, "rigid", []))
        return out

    def _detach(self, tag: str):
        for nid in [n for n, node in self.nodes.items() if node.get("weapon") == tag]:
            parent = self.nodes[nid]["parent"]
            if parent in self.nodes and nid in self.nodes[parent]["children"]:
                self.nodes[parent]["children"].remove(nid)
            del self.nodes[nid]
        self.alias = {k: v for k, v in self.alias.items() if k[0] != tag}

    def add_weapons(self, root_id, weapons: list[dict], mode: str = "limbs"):
        """Hang the unit's weapon prefabs (tsquad_common.pick_weapons) on the skeleton read by walk().

        The game keeps more than swords in its weapon slots.  Natsume's left arm, Tsuru's right forearm,
        Snake Lady's arms and Saika's legs are weapon prefabs: skinned meshes whose every bone is a
        ``Ref_`` stand-in for a bone of the unit, so they deform with the unit's own skeleton - a "limb".
        Without them the unit prefab has a stump.  mode "limbs" (the default) attaches those only; "all"
        also the real weapons (kind "weapon": own bones or rigid, under the hand bone, on the back, on
        the head ...) where the prefab pose puts them; "none" nothing."""
        if mode == "none" or not weapons:
            return
        names: dict = {}
        for nid in self._ordered(root_id):
            names.setdefault(self.nodes[nid]["name"], nid)
        for w in weapons:
            row = {"name": w["name"], "grade": w["grade"], "slot": w["slot"]}
            reader = self.loader.container_object(w["bundle"], w["guid"])
            info = self.attach_prefab(reader, w["name"], names) if reader is not None else "prefab not found"
            if isinstance(info, str):
                self.weapons_left.append(dict(row, reason=info))
                continue
            row["bone"] = info["bone"]
            drawn = self._weapon_renderers(w["name"])
            limb = bool(drawn) and all(kind == "skinned" and bones and all(
                b in self.nodes and not self.nodes[b].get("weapon") for b in bones) for _n, kind, bones in drawn)
            row["kind"] = "limb" if limb else "weapon"
            if not drawn:
                self._detach(w["name"])
                self.weapons_left.append(dict(row, reason="nothing to draw (its renderers are switched off)"))
            elif mode != "all" and not limb:
                self._detach(w["name"])
                self.weapons_left.append(dict(row, reason="a weapon, not a part of the body (--weapons takes it)"))
            else:
                self.weapons.append(row)

    def _nid(self, node, file_id, path_id):
        """Node id of a transform a component on `node` points to (None: another file, or nothing)."""
        if file_id or not path_id:
            return None
        tag = node.get("weapon")
        key = path_id if tag is None else (tag, path_id)
        return self.alias.get(key, key)

    def _is_helper(self, node) -> bool:
        return any(t in HELPER_COMPONENTS for t in node["types"]) or any(m in HELPER_COMPONENTS for m in node["monos"])

    def choose_bones(self, root_id: int, skinned: set[int]):
        """Mark the transforms that become armature bones: every skinned bone with its ancestors,
        plus the plain transforms under the skeleton tops (sockets, chain ends)."""
        keep = set()
        for nid in skinned:
            cur = nid
            while cur is not None and cur != root_id and cur not in keep:
                keep.add(cur)
                cur = self.nodes[cur]["parent"]
        tops = [c for c in self.nodes[root_id]["children"] if c in keep]
        renderer_types = ("SkinnedMeshRenderer", "MeshRenderer")
        for top in tops:
            stack = [top]
            while stack:
                nid = stack.pop()
                node = self.nodes[nid]
                if nid not in keep:
                    # (of a weapon prefab only what carries skin becomes a bone, not its spare transforms)
                    if node.get("weapon") or self._is_helper(node) or any(t in renderer_types for t in node["types"]):
                        continue                       # its subtree is helper stuff too
                    keep.add(nid)
                stack.extend(node["children"])
        names: dict[str, int] = {}
        for nid in self._ordered(root_id):
            if nid not in keep:
                continue
            node = self.nodes[nid]
            name, n = node["name"], 1
            while name in names:
                n += 1
                name = "%s.%03d" % (node["name"], n)
            names[name] = nid
            node["bone"] = name
        return keep

    def limb_aliases(self) -> dict[str, str]:
        """{alias bone: Biped bone} for the second leg / arm chain of the early characters.

        Asagi, Shiranui, Asuka and Oboro do not skin their legs to the Biped: ``Bone_L_Thigh >
        Bone_L_Knee_end > Bone_L_Calf`` hangs under ``Bip001 L Thigh`` and carries the whole thigh and
        shin.  Every game animation keys that chain to lie on the Biped leg; outside the game nothing
        does, and a shin skinned to ``Bone_L_Calf`` stays in line with the thigh when ``Bip001 L Calf``
        bends (the foot left the leg in the XPS pose test and the MMD dance).  The chains coincide in
        the prefab pose, so the skin is handed to the Biped bone and the alias stays as an empty bone."""
        bones = {n["bone"]: n for n in self.nodes.values() if "bone" in n}
        if not bones:
            return {}
        top = max(float(n["world"][1, 3]) for n in bones.values())
        reach = 0.03 * max(1.0, top / 1.6)
        lower = {name.lower(): name for name in bones}
        out = {}
        for name, node in bones.items():
            match = LIMB_ALIAS.match(name)
            if match is None:
                continue
            biped = lower.get(("bip001 %s %s" % (match.group(1), match.group(2))).lower())
            if biped is None or biped == name:
                continue
            gap = float(np.linalg.norm(node["world"][:3, 3] - bones[biped]["world"][:3, 3]))
            if gap <= reach:
                out[name] = biped
        return out

    def _ordered(self, root_id: int):
        out, stack = [], [root_id]
        while stack:
            nid = stack.pop()
            out.append(nid)
            stack.extend(reversed(self.nodes[nid]["children"]))
        return out

    def bone_ancestor(self, nid):
        cur = nid
        while cur is not None:
            if "bone" in self.nodes[cur]:
                return self.nodes[cur]["bone"]
            cur = self.nodes[cur]["parent"]
        return None

    # ------------------------------------------------------------ textures / materials
    def texture(self, pptr, prop: str):
        reader = self.loader.deref(pptr)
        if reader is None or reader.type.name != "Texture2D":
            return None
        key = (reader.assets_file.name, reader.path_id, prop in NORMAL_PROPS)
        if key in self._tex_files:
            return self._tex_files[key]
        tex = reader.read()
        name, n = safe_name(tex.m_Name), 1
        while name.lower() in self._tex_names:
            n += 1
            name = "%s_%d" % (safe_name(tex.m_Name), n)
        self._tex_names.add(name.lower())
        try:
            image = tex.image
        except Exception as exc:  # noqa: BLE001 - a texture format the decoder lacks
            self.warnings.append("texture %s not decoded: %s" % (tex.m_Name, exc))
            self._tex_files[key] = None
            return None
        if prop in NORMAL_PROPS:
            image = unpack_normal(image)
        tex_dir = os.path.join(self.out_dir, "textures")
        os.makedirs(tex_dir, exist_ok=True)
        image.save(os.path.join(tex_dir, name + ".png"))
        self._tex_files[key] = name + ".png"
        return self._tex_files[key]

    def material(self, pptr):
        reader = self.loader.deref(pptr)
        if reader is None or reader.type.name != "Material":
            return None
        key = (reader.assets_file.name, reader.path_id)
        if key in self._mat_keys:
            return self._mat_keys[key]
        mat = reader.read()
        name, n = mat.m_Name or "material", 1
        while name in self.materials:
            n += 1
            name = "%s.%03d" % (mat.m_Name, n)
        self._mat_keys[key] = name
        shader = self.loader.read(mat.m_Shader)
        parsed = getattr(shader, "m_ParsedForm", None)
        shader_name = getattr(parsed, "m_Name", None) or getattr(shader, "m_Name", "") or ""
        props = mat.m_SavedProperties
        textures = {}
        for prop, env in props.m_TexEnvs:
            png = self.texture(env.m_Texture, prop)
            if png:
                textures[prop] = {"file": png, "scale": [env.m_Scale.x, env.m_Scale.y],
                                  "offset": [env.m_Offset.x, env.m_Offset.y]}
        tags = getattr(mat, "stringTagMap", None) or []
        self.materials[name] = {
            "name": mat.m_Name, "shader": shader_name, "textures": textures,
            "floats": {k: float(v) for k, v in props.m_Floats},
            "ints": {k: int(v) for k, v in (getattr(props, "m_Ints", None) or [])},
            "colors": {k: [float(v.r), float(v.g), float(v.b), float(v.a)] for k, v in props.m_Colors},
            "keywords": sorted(list(getattr(mat, "m_ValidKeywords", None) or [])),
            "render_queue": int(getattr(mat, "m_CustomRenderQueue", -1)),
            "tags": {k: v for k, v in tags},
            "disabled_passes": list(getattr(mat, "disabledShaderPasses", None) or []),
        }
        return name

    # ------------------------------------------------------------ renderers
    def add_renderers(self, root_id: int, include_inactive: bool = False):
        """Find the renderers, pick the bones, bake and write each part."""
        skinned_parts, rigid_parts, skinned_bones = [], [], set()
        for nid in self._ordered(root_id):
            node = self.nodes[nid]
            if not node["active"] and not include_inactive and not EMOTE_NAME.search(node["name"]):
                continue                               # (the em_* cards are kept, hidden: see part_role)
            by_type = {c.type.name: c for c in node["components"]}
            if "SkinnedMeshRenderer" in by_type:
                r = by_type["SkinnedMeshRenderer"].read()
                if not r.m_Enabled or not r.m_Mesh.m_PathID:
                    continue
                bones = [self._nid(node, b.m_FileID, b.m_PathID) for b in r.m_Bones]
                skinned_bones.update(b for b in bones if b in self.nodes)
                skinned_parts.append((nid, r, bones))
            elif "MeshRenderer" in by_type and "MeshFilter" in by_type:
                r = by_type["MeshRenderer"].read()
                mf = by_type["MeshFilter"].read()
                if r.m_Enabled and mf.m_Mesh.m_PathID:
                    rigid_parts.append((nid, r, mf))
        if not skinned_parts and not rigid_parts:
            raise RuntimeError("the prefab has no enabled renderer")
        if not skinned_bones:                          # a prop without a skeleton: its own transforms are the bones
            skinned_bones = {nid for nid, _r, _mf in rigid_parts}
        self.choose_bones(root_id, skinned_bones)
        self.aliases = self.limb_aliases()
        for nid, r, bones in skinned_parts:
            self._skinned_part(nid, r, bones)
        for nid, r, mf in rigid_parts:
            self._rigid_part(nid, r, mf)

    def _part_materials(self, renderer):
        keys = []
        for pptr in renderer.m_Materials:
            keys.append(self.material(pptr))
        return keys

    def _skinned_part(self, nid, renderer, bones):
        node = self.nodes[nid]
        reader = self.loader.deref(renderer.m_Mesh)
        if reader is None:
            self.warnings.append("%s: mesh not found" % node["name"])
            return
        mesh = decode_mesh(reader)
        if not mesh["vertex_count"] or "vertices" not in mesh:
            self.warnings.append("%s: empty mesh" % node["name"])
            return
        names, mats = [], []
        binds = mesh["bindposes"]
        for i, pid in enumerate(bones):
            bnode = self.nodes.get(pid) if pid is not None else None
            if bnode is None or i >= len(binds):
                names.append(self.bone_ancestor(nid) or "")
                mats.append(node["world"])
                continue
            name = bnode.get("bone") or self.bone_ancestor(pid) or ""
            names.append(self.aliases.get(name, name))     # baked with its own bone, driven by the Biped one
            mats.append(bnode["world"] @ binds[i])
        if not mats:                                   # no bones: rides its own transform
            names = [self.bone_ancestor(nid) or ""]
            mats = [node["world"]]
            mesh.pop("bone_indices", None)
            mesh.pop("weights", None)
        # the expression the prefab starts with (0 - 100 per shape): 125_Sokushitsuki's horns are "small"
        mesh["shape_defaults"] = [float(w) for w in (getattr(renderer, "m_BlendShapeWeights", None) or [])]
        self._write_part(node, mesh, np.array(mats), names, self._part_materials(renderer), True)

    def _rigid_part(self, nid, renderer, mesh_filter):
        node = self.nodes[nid]
        reader = self.loader.deref(mesh_filter.m_Mesh)
        if reader is None:                             # a Unity built-in primitive
            return
        mesh = decode_mesh(reader)
        if not mesh["vertex_count"] or "vertices" not in mesh:
            return
        mesh.pop("bone_indices", None)
        mesh.pop("weights", None)
        self._write_part(node, mesh, np.array([node["world"]]), [self.bone_ancestor(nid) or ""],
                         self._part_materials(renderer), False)

    def _parked(self, nid, lo, hi) -> bool:
        """True when a rigid mesh is not on the body in the prefab pose.  The game leaves many weapon
        bones at the origin (some under the floor) until an animation moves them into the hand, and a
        few weapons hang outside the skeleton altogether.  On the body = the bounding box [lo, hi]
        comes close to a hand, or to the Biped bone the mesh hangs from (a sheath on the hip, a blade
        on the forearm)."""
        chain, cur = [], self.nodes[nid]["parent"]
        while cur is not None:
            chain.append(self.nodes[cur])
            cur = self.nodes[cur]["parent"]
        if not any("bone" in n for n in chain):
            return True                                # nothing in the armature could carry it
        anchors = [n for n in self.nodes.values() if HAND_NAME.search(n["name"])]
        hang = next((n for n in chain if BIPED_BONE.search(n["name"])), None)
        if hang is not None:
            anchors.append(hang)
        if not anchors:
            return False                               # not a Biped: no way to tell, keep it
        top = max(float(n["world"][1, 3]) for n in self.nodes.values() if "bone" in n)
        return box_gap(lo, hi, [n["world"][:3, 3] for n in anchors]) > CARRY_REACH * max(top, 0.5)

    def _write_part(self, node, mesh, matrices, bone_names, materials, skinned):
        dropped = drop_undrawn(mesh, len(materials))
        if dropped:
            self.undrawn.append({"part": node["name"], "triangles": dropped})
        if not mesh["vertex_count"] or not mesh["submeshes"]:
            return                                     # a renderer without a material slot draws nothing
        n = mesh["vertex_count"]
        blend = skin_matrices(mesh, matrices)
        rot = blend[:, :3, :3]
        # positions and normals are float3 in most meshes, float4 in a few (the fourth is padding)
        verts = np.einsum("nij,nj->ni", rot, mesh["vertices"][:, :3].astype(np.float64)) + blend[:, :3, 3]
        arrays = {"vertices": verts.astype(np.float32), "indices": mesh["indices"].astype(np.int32)}
        if "normals" in mesh and mesh["normals"].shape[1] >= 3:
            nrm = np.einsum("nij,nj->ni", rot, mesh["normals"][:, :3].astype(np.float64))
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            arrays["normals"] = nrm.astype(np.float32)
        for i in range(8):
            if "uv%d" % i in mesh:
                arrays["uv%d" % i] = mesh["uv%d" % i][:, :2].astype(np.float32)
        if "colors" in mesh:
            arrays["colors"] = mesh["colors"].astype(np.float32)
        idx = mesh.get("bone_indices")
        if idx is None:
            idx = np.zeros((n, 1), dtype=np.int32)
            w = np.ones((n, 1), dtype=np.float32)
        else:
            w = mesh.get("weights")
            if w is None:
                w = np.zeros(idx.shape, dtype=np.float32)
                w[:, 0] = 1.0
        arrays["bone_indices"] = np.clip(idx, 0, max(0, len(bone_names) - 1)).astype(np.int32)
        arrays["bone_weights"] = w.astype(np.float32)
        shape_names, shape_defaults = [], {}
        defaults = mesh.get("shape_defaults") or []
        for si, shape in enumerate(mesh["shapes"]):
            sel = shape["indices"]
            good = sel < n
            sel = sel[good]
            delta = np.einsum("nij,nj->ni", rot[sel], shape["delta"][good].astype(np.float64))
            keep = np.linalg.norm(delta, axis=1) > 1e-7
            arrays["shape%d_idx" % si] = sel[keep].astype(np.int32)
            arrays["shape%d_delta" % si] = delta[keep].astype(np.float32)
            shape_names.append(shape["name"])
            if si < len(defaults) and abs(defaults[si]) > 1e-3:
                shape_defaults[shape["name"]] = round(defaults[si] / (shape.get("full_weight") or 100.0), 4)
        name, k = safe_name(node["name"]), 1
        used = {p["name"] for p in self.parts}
        while name in used:
            k += 1
            name = "%s_%d" % (safe_name(node["name"]), k)
        parts_dir = os.path.join(self.out_dir, "parts")
        os.makedirs(parts_dir, exist_ok=True)
        np.savez_compressed(os.path.join(parts_dir, name + ".npz"), **arrays)
        tris = sum(c for _f, c, topo in mesh["submeshes"] if topo == 0) // 3
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        weapon = next((w for w in self.weapons if w["name"] == node.get("weapon")), None)
        if weapon is not None and weapon["kind"] != "limb":    # a real weapon out of its prefab, skinned or not
            role = "weapon_parked" if self._parked(node["id"], lo, hi) else "weapon"
        else:
            role = part_role(node["name"], bone_names, skinned, (not skinned) and self._parked(node["id"], lo, hi))
        if weapon is not None:
            weapon.setdefault("parts", []).append(name)
        self.parts.append({
            "name": name, "mesh": mesh["name"], "npz": "parts/%s.npz" % name, "skinned": skinned,
            "role": role, "weapon": node.get("weapon") or "",
            "node": self.bone_ancestor(node["id"]) or "", "bones": bone_names, "materials": materials,
            "submeshes": [list(s) for s in mesh["submeshes"]], "shape_keys": shape_names,
            "shape_defaults": shape_defaults,
            "vertices": int(n), "triangles": int(tris), "uv_sets": [k for k in arrays if k.startswith("uv")],
            "bounds": [lo.tolist(), hi.tolist()], "active": bool(node["active"]),
        })

    # ------------------------------------------------------------ Magica Cloth (documentation / physics hints)
    def read_cloth(self, root_id: int):
        for nid in self._ordered(root_id):
            node = self.nodes[nid]
            for comp, cls in zip([c for c in node["components"] if c.type.name == "MonoBehaviour"], node["monos"]):
                if cls != "MagicaCloth":
                    continue
                try:
                    data = comp.read_typetree().get("serializeData") or {}
                except Exception:  # noqa: BLE001
                    continue
                roots = []
                for ref in data.get("rootBones") or []:
                    target = self.nodes.get(self._nid(node, ref.get("m_FileID"), ref.get("m_PathID")))
                    if target is not None:
                        roots.append(target.get("bone") or target["name"])
                spring = data.get("springConstraint") or {}
                self.cloth.append({
                    "name": node["name"], "cloth_type": data.get("clothType"), "root_bones": roots,
                    "gravity": data.get("gravity"), "damping": (data.get("damping") or {}).get("value"),
                    "radius": (data.get("radius") or {}).get("value"),
                    "connection_mode": data.get("connectionMode"),
                    "blend_weight": data.get("blendWeight"),
                    # Bone Spring (cloth type 10, the breasts): the bone slides up to limit_distance metres
                    # and each step pulls it back by spring_power of that
                    "use_spring": bool(spring.get("useSpring")), "spring_power": spring.get("springPower"),
                    "limit_distance": spring.get("limitDistance"),
                })

    # ------------------------------------------------------------ output
    def to_json(self, root_id: int, meta: dict) -> dict:
        nodes, moved = [], {}
        bones = {n["bone"] for n in self.nodes.values() if "bone" in n}
        for nid in self._ordered(root_id):
            node = self.nodes[nid]
            if "bone" not in node:
                continue
            chain, parent = [], node["parent"]
            while parent is not None:
                if "bone" in self.nodes[parent]:
                    chain.append(self.nodes[parent]["bone"])
                parent = self.nodes[parent]["parent"]
            owner = twist_owner(node["bone"], chain, bones)
            if owner:
                moved[node["bone"]] = owner
            nodes.append({"name": node["bone"], "parent": owner or (chain[0] if chain else None),
                          "world": node["world"].tolist()})
        weighted = set()
        for part in self.parts:
            weighted.update(b for b in part["bones"] if b)
        scene = dict(meta)
        scene.update({
            "unit_scale": 1.0, "nodes": nodes, "parts": self.parts, "materials": self.materials,
            "cloth": self.cloth, "skinned_bones": sorted(weighted), "warnings": self.warnings,
            "limb_aliases": self.aliases, "reparented_twist_links": moved,
            "undrawn_submeshes": self.undrawn,
            "weapon_prefabs": self.weapons, "weapon_prefabs_left_out": self.weapons_left,
            "breast_bones": breast_bones(self.cloth, sorted(weighted)),
        })
        return scene


REF_PREFIX = "Ref_"                                    # weapon prefabs: Ref_<bone> stands for the unit's <bone>
WEAPON_NAME = re.compile(r"weapon|(^|_)wp(_|$)|prop", re.IGNORECASE)
EMOTE_NAME = re.compile(r"^em_", re.IGNORECASE)
EFFECT_NAME = re.compile(r"effectrender", re.IGNORECASE)   # costume_10_EffectRender, B_16_EffectRenderMesh_1
FACE_NAME = re.compile(r"(^|_)face(_|$)")              # face_24, face_24_mouth_in, asuka_face (16_Asuka Black)
LIMB_ALIAS = re.compile(r"^Bone_?([LR])_?(Thigh|Calf|UpperArm|Forearm)$", re.IGNORECASE)
TWIST_LINK = re.compile(r"^(Bip\d+) ([LR])\s?(Thigh|Calf|UpArm|UpperArm|Fore|ForeArm)Twist\d*$", re.IGNORECASE)
TWIST_OWNER = {"thigh": "Thigh", "calf": "Calf", "uparm": "UpperArm", "upperarm": "UpperArm",
               "fore": "Forearm", "forearm": "Forearm"}


def twist_owner(name: str, ancestors: list[str], bones) -> str | None:
    """The limb bone a Biped twist link belongs under, when it is not under it already.

    3ds Max hangs ``Bip001 LThighTwist`` next to the thigh, not under it, and animates it; 13_Shiranui
    skins most of her thighs to it.  As a sibling it stays behind when the thigh is posed in Blender or
    XPS, so the exported skeleton puts it under ``Bip001 L Thigh`` (the rest pose does not change)."""
    match = TWIST_LINK.match(name)
    if match is None:
        return None
    owner = "%s %s %s" % (match.group(1), match.group(2).upper(), TWIST_OWNER[match.group(3).lower()])
    return owner if owner in bones and owner not in ancestors else None


HAND_NAME = re.compile(r"^Bip\d+ [LR] Hand$")
BIPED_BONE = re.compile(r"^Bip\d+ \S")                 # a Biped body bone ("Bip001 L Calf"), not the root "Bip001"
CARRY_REACH = 0.15                                     # x the height of the skeleton: measured gaps are < 0.12 (carried) and > 0.3 (parked)


def box_gap(lo, hi, points) -> float:
    """The smallest distance from any of the points to the box [lo, hi] (0 when one is inside)."""
    lo, hi = np.asarray(lo, dtype=np.float64), np.asarray(hi, dtype=np.float64)
    return min((float(np.linalg.norm(np.maximum(np.maximum(lo - p, p - hi), 0.0)))
                for p in np.asarray(points, dtype=np.float64).reshape(-1, 3)), default=float("inf"))


def part_role(name: str, bone_names: list[str], skinned: bool, parked: bool = False) -> str:
    """face / hair / body by the game's own part names.  "effect" = an ...EffectRender renderer: the body
    drawn a second time with an additive glow shader (7 units), which would cover the real one.  Rigid
    meshes: "emote" = the em_* cards on the head (tears, sweat drop, anger mark) the game switches on
    with an expression; "weapon" = a mesh on a weapon / prop bone, "weapon_parked" when it is not on the
    body in the prefab pose (Scene._parked: the orcs' clubs stand at the origin until an animation
    moves them into the hand)."""
    low = name.lower()
    if EFFECT_NAME.search(name):
        return "effect"
    if not skinned:
        if EMOTE_NAME.search(name):
            return "emote"
        if WEAPON_NAME.search(name) or any(WEAPON_NAME.search(b or "") for b in bone_names):
            return "weapon_parked" if parked else "weapon"
    if FACE_NAME.search(low):
        return "face"
    if low.startswith("hair"):
        return "hair"
    return "body"


def unpack_normal(image):
    """Unity stores tangent normals as (1, y, *, x) (DXT5nm style) or plain RGB; write RGB with z rebuilt."""
    from PIL import Image

    arr = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    x = arr[..., 0] * arr[..., 3]                      # UnpackNormalmapRGorAG: x = r * a
    y = arr[..., 1]
    nx, ny = x * 2.0 - 1.0, y * 2.0 - 1.0
    nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
    out = np.stack([x, y, nz * 0.5 + 0.5], axis=-1)
    return Image.fromarray(np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


BUST_BONE = re.compile(r"bust|breast", re.IGNORECASE)


def breast_bones(cloth: list[dict], bone_names) -> list[str]:
    """The breast bones: the roots of the Magica Cloth group called "Breast" (they are ``Bone_L_Bust``,
    ``Bone_LBreast`` or the Biped extras ``Bip001 Xtra01`` / ``Xtra01Opp`` depending on the rig), else
    any bone named bust / breast."""
    for group in cloth:
        if BUST_BONE.search(group.get("name") or "") and group.get("root_bones"):
            return list(group["root_bones"])
    return [n for n in bone_names if BUST_BONE.search(n)]


BONE_SPRING = 10                                       # MagicaCloth2 ClothType.BoneSpring


def breast_spring(model: dict, loader: Loader | None = None, root: str = tc.EXPORT_ROOT) -> dict | None:
    """The Bone Spring settings of the unit's breasts - {"spring_power", "limit_distance", "damping",
    "blend_weight"} of its Magica Cloth group "Breast" - or None when it has no such spring.  Only the
    prefab's components are read (no geometry), about a tenth of a second."""
    loader = loader or Loader(root)
    prefab = loader.container_object(model["bundle"], model["guid"])
    if prefab is None:
        return None
    scene = Scene(loader, "")
    scene.read_cloth(scene.walk(prefab))
    for group in scene.cloth:
        if BUST_BONE.search(group.get("name") or "") and group.get("cloth_type") == BONE_SPRING \
                and group.get("use_spring") and group.get("spring_power") and group.get("limit_distance"):
            return {"spring_power": round(float(group["spring_power"]), 4),
                    "limit_distance": round(float(group["limit_distance"]), 4),
                    "damping": round(float(group.get("damping") or 0.0), 4),
                    "blend_weight": round(float(group.get("blend_weight") or 1.0), 4)}
    return None


def unit_details(model: dict, loader: Loader | None = None, root: str = tc.EXPORT_ROOT) -> dict:
    """What list_models.py --details shows: counts read from the prefab without decoding any geometry."""
    loader = loader or Loader(root)
    prefab = loader.container_object(model["bundle"], model["guid"])
    if prefab is None:
        return {"error": "prefab not found"}
    scene = Scene(loader, "")
    root_id = scene.walk(prefab)
    info = {"parts": [], "vertices": 0, "triangles": 0, "shape_keys": 0, "materials": 0, "cloth_groups": 0,
            "weapons": 0}
    materials, bones = set(), set()
    for nid in scene._ordered(root_id):
        node = scene.nodes[nid]
        if not node["active"]:
            continue
        by_type = {c.type.name: c for c in node["components"]}
        mesh_ptr = renderer = None
        if "SkinnedMeshRenderer" in by_type:
            renderer = by_type["SkinnedMeshRenderer"].read()
            mesh_ptr = renderer.m_Mesh
            bones.update(b.m_PathID for b in renderer.m_Bones if not b.m_FileID)
        elif "MeshRenderer" in by_type and "MeshFilter" in by_type:
            renderer = by_type["MeshRenderer"].read()
            mesh_ptr = by_type["MeshFilter"].read().m_Mesh
            info["weapons"] += 1 if WEAPON_NAME.search(node["name"]) else 0
        info["cloth_groups"] += sum(1 for m in node["monos"] if m == "MagicaCloth")
        if node["parent"] is None:
            for comp, cls in zip([c for c in node["components"] if c.type.name == "MonoBehaviour"], node["monos"]):
                if cls == "UnitCustomInfo":
                    try:
                        info["height_m"] = round(float(comp.read_typetree().get("Height", 0.0)), 2)
                    except Exception:  # noqa: BLE001
                        pass
        if renderer is None or not renderer.m_Enabled:
            continue
        reader = loader.deref(mesh_ptr)
        if reader is None:
            continue
        tt = reader.read_typetree()
        count = tt["m_VertexData"]["m_VertexCount"] or \
            ((tt.get("m_CompressedMesh") or {}).get("m_Vertices") or {}).get("m_NumItems", 0) // 3
        slots = len(renderer.m_Materials)               # sub-meshes beyond the material slots are not drawn
        tris = sum(sm["indexCount"] for i, sm in enumerate(tt["m_SubMeshes"]) if sm["topology"] == 0 and i < slots) // 3
        shapes = len((tt.get("m_Shapes") or {}).get("channels") or [])
        info["parts"].append(node["name"])
        info["vertices"] += count
        info["triangles"] += tris
        info["shape_keys"] += shapes
        materials.update((m.m_FileID, m.m_PathID) for m in renderer.m_Materials if m.m_PathID)
    names = [scene.nodes[b]["name"] for b in bones if b in scene.nodes]
    info["materials"] = len(materials)
    info["bones"] = len(bones)
    scene.read_cloth(root_id)
    info["bust"] = bool(breast_bones(scene.cloth, names))
    info["biped"] = any(n.endswith(" Pelvis") for n in names)
    return info


def export_icons(models: list[dict], out_dir: str, root: str = tc.EXPORT_ROOT) -> dict[str, str]:
    """The game's own unit icons (Icon/Char/...) as PNG, one per model id; existing files are kept."""
    os.makedirs(out_dir, exist_ok=True)
    loader, done = None, {}
    for model in models:
        icon = model.get("icon")
        if not icon:
            continue
        path = os.path.join(out_dir, model["id"] + ".png")
        if not os.path.isfile(path):
            loader = loader or Loader(root)
            try:
                reader = loader.container_object(icon["bundle"], icon["guid"], "Texture2D")
                if reader is None:
                    continue
                reader.read().image.save(path)
            except Exception:  # noqa: BLE001 - an icon is decoration
                continue
        done[model["id"]] = path
    return done


def load_unit(scene: Scene, model: dict, include_inactive: bool = False, weapons: str = "limbs",
              weapon_grade: int = 0):
    """The unit prefab with its weapon prefabs hung on (Scene.add_weapons), every part baked; returns the
    root node id.  weapons: "limbs" (the body parts the game keeps as weapons), "all", "none"."""
    prefab = scene.loader.container_object(model["bundle"], model["guid"])
    if prefab is None:
        raise RuntimeError("prefab %s not found in %s" % (model["key"], model["bundle"]))
    root_id = scene.walk(prefab)
    scene.add_weapons(root_id, tc.pick_weapons(model.get("weapons") or [], weapon_grade), weapons)
    scene.add_renderers(root_id, include_inactive)
    scene.read_cloth(root_id)
    return root_id


def extract_unit(model: dict, out_dir: str, root: str = tc.EXPORT_ROOT, include_inactive: bool = False,
                 weapons: str = "limbs", weapon_grade: int = 0) -> dict:
    """Write scene.json + parts + textures of one model into out_dir; returns the scene dict."""
    scene = Scene(Loader(root), out_dir)
    root_id = load_unit(scene, model, include_inactive, weapons, weapon_grade)
    meta = {"id": model["id"], "name": model["name"], "group": model["group"], "category": model["category"],
            "prefab": model["key"], "bundle": model["bundle"], "game": "Taimanin Squad"}
    data = scene.to_json(root_id, meta)
    tc.save_json(os.path.join(out_dir, "scene.json"), data)
    return data
