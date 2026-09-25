"""Bake HoneySelect 2 prefabs out of the asset bundles into one Unity-space scene.

A scene is what `build_blend.py` turns into a .blend: a node tree (the union skeleton), mesh
parts whose vertices are already skinned to that skeleton's rest pose, and materials whose
textures are decoded to PNG.  Placement follows the game (ChaControl):

* the body prefab (`p_cf_body_00` / `p_cm_body_00`) sits at the origin;
* the head skeleton `p_cf_head_bone` and the head mesh prefab hang under `cf_J_Head_s`;
* clothes are re-bound onto the body bones **by name** (their own bone copies are dropped);
* hair hangs under `N_hair_Root` (head), accessories under their `Parent` / card `parentKey` node.

Every skinned vertex is baked as sum_i w_i * (World_i x BindPose_i) * v with World_i taken
from the *target* skeleton, i.e. exactly what Unity draws in the prefab pose.
"""
import os

import numpy as np
import UnityPy
from UnityPy.files.SerializedFile import SerializedFile
from UnityPy.helpers.MeshHelper import MeshHandler

import hs2_data

HIDE_RENDERERS = ("o_hit_", "o_silhouette", "o_shadowcaster")
SKELETON_TAGS = ("body", "headbone")  # node sets later instances may merge into by name


def _mat4(b):
    return np.array([[b.e00, b.e01, b.e02, b.e03], [b.e10, b.e11, b.e12, b.e13],
                     [b.e20, b.e21, b.e22, b.e23], [b.e30, b.e31, b.e32, b.e33]], dtype=np.float64)


def trs_matrix(pos, rot, scale):
    x, y, z, w = rot
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.asarray(scale, dtype=np.float64)
    m[:3, 3] = pos
    return m


def euler_quat(deg):
    """Unity Euler (degrees, applied Z then X then Y) -> quaternion (x, y, z, w)."""
    rx, ry, rz = (np.radians(a) * 0.5 for a in deg)
    qx = np.array([np.sin(rx), 0, 0, np.cos(rx)])
    qy = np.array([0, np.sin(ry), 0, np.cos(ry)])
    qz = np.array([0, 0, np.sin(rz), np.cos(rz)])

    def mul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                         aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])
    return mul(mul(qy, qx), qz)


def _local(t):
    p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
    return trs_matrix((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))


def _oid(obj):
    return obj.object_reader.path_id


def _pid(pptr):
    return getattr(pptr, "path_id", 0) or getattr(pptr, "m_PathID", 0)


def _safe_read(pptr):
    if pptr is None or not _pid(pptr):
        return None
    try:
        return pptr.read()
    except Exception:  # noqa: BLE001 - unresolved cross-bundle refs are simply absent
        return None


def _color(c):
    return [float(c.r), float(c.g), float(c.b), float(c.a)] if hasattr(c, "r") else \
        [float(c["r"]), float(c["g"]), float(c["b"]), float(c["a"])]


# Unity's built-in meshes live in "unity default resources", not in any bundle; a few
# accessories use them (the clown nose is a Sphere).  path_id -> generator.
BUILTIN_MESHES = {10202: "Cube", 10206: "Cylinder", 10207: "Sphere", 10208: "Capsule", 10209: "Plane", 10210: "Quad"}


def _faces_outward(verts, normals, tris):
    """Order each triangle so cross(b-a, c-a) follows the normal (Unity's index order)."""
    tris = np.asarray(tris, dtype=np.int64)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    flip = (np.cross(b - a, c - a) * (normals[tris[:, 0]] + normals[tris[:, 1]] + normals[tris[:, 2]])).sum(1) < 0
    tris[flip] = tris[flip][:, [0, 2, 1]]
    return tris


def builtin_mesh(kind, seg=24, rings=16):
    """(vertices, normals, uv0, triangles) of a Unity primitive in its own units."""
    if kind in ("Sphere", "Capsule"):
        half = 0.5 if kind == "Capsule" else 0.0  # capsule: 2 tall, hemispheres r 0.5
        verts, uvs = [], []
        for i in range(rings + 1):
            th = np.pi * i / rings
            for j in range(seg + 1):
                ph = 2 * np.pi * j / seg
                x, y, z = np.sin(th) * np.cos(ph), np.cos(th), np.sin(th) * np.sin(ph)
                verts.append((x * 0.5, y * 0.5 + (half if y >= 0 else -half), z * 0.5))
                uvs.append((j / seg, 1 - i / rings))
        v = np.array(verts, dtype=np.float64)
        n = v.copy()
        n[:, 1] -= np.clip(n[:, 1], -half, half)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        tris = []
        for i in range(rings):
            for j in range(seg):
                a, b = i * (seg + 1) + j, (i + 1) * (seg + 1) + j
                tris += [(a, b, a + 1), (a + 1, b, b + 1)]
        return v, n, np.array(uvs, dtype=np.float32), _faces_outward(v, n, tris)
    if kind == "Cylinder":
        verts, norms, uvs, tris = [], [], [], []
        for j in range(seg + 1):
            ph = 2 * np.pi * j / seg
            x, z = np.cos(ph) * 0.5, np.sin(ph) * 0.5
            for y in (-1.0, 1.0):
                verts.append((x, y, z))
                norms.append((x * 2, 0, z * 2))
                uvs.append((j / seg, (y + 1) / 2))
        for j in range(seg):
            a = j * 2
            tris += [(a, a + 1, a + 2), (a + 1, a + 3, a + 2)]
        for y in (-1.0, 1.0):
            c = len(verts)
            verts.append((0, y, 0))
            norms.append((0, y, 0))
            uvs.append((0.5, 0.5))
            for j in range(seg + 1):
                ph = 2 * np.pi * j / seg
                verts.append((np.cos(ph) * 0.5, y, np.sin(ph) * 0.5))
                norms.append((0, y, 0))
                uvs.append((0.5 + np.cos(ph) * 0.5, 0.5 + np.sin(ph) * 0.5))
            for j in range(seg):
                tris.append((c, c + 1 + j, c + 2 + j))
        v, n = np.array(verts, dtype=np.float64), np.array(norms, dtype=np.float64)
        return v, n, np.array(uvs, dtype=np.float32), _faces_outward(v, n, tris)
    if kind in ("Plane", "Quad"):
        size = 10.0 if kind == "Plane" else 1.0
        g = np.linspace(-size / 2, size / 2, 11 if kind == "Plane" else 2)
        verts, uvs = [], []
        for zi, zz in enumerate(g):
            for xi, xx in enumerate(g):
                verts.append((xx, 0.0, zz) if kind == "Plane" else (xx, zz, 0.0))
                uvs.append((xi / (len(g) - 1), zi / (len(g) - 1)))
        v = np.array(verts, dtype=np.float64)
        n = np.tile([0.0, 1.0, 0.0] if kind == "Plane" else [0.0, 0.0, -1.0], (len(v), 1))
        k = len(g)
        tris = []
        for zi in range(k - 1):
            for xi in range(k - 1):
                a = zi * k + xi
                tris += [(a, a + k, a + 1), (a + 1, a + k, a + k + 1)]
        return v, n, np.array(uvs, dtype=np.float32), _faces_outward(v, n, tris)
    # Cube: 6 faces x 4 vertices
    verts, norms, uvs, tris = [], [], [], []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            nrm = np.zeros(3)
            nrm[axis] = sign
            u, w = [i for i in range(3) if i != axis]
            base = len(verts)
            for cu, cw in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = np.zeros(3)
                p[axis], p[u], p[w] = sign * 0.5, cu * 0.5, cw * 0.5
                verts.append(p)
                norms.append(nrm)
                uvs.append(((cu + 1) / 2, (cw + 1) / 2))
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    v, n = np.array(verts, dtype=np.float64), np.array(norms, dtype=np.float64)
    return v, n, np.array(uvs, dtype=np.float32), _faces_outward(v, n, tris)


class Bundles:
    """One UnityPy Environment holding every bundle a scene needs (+ manifest dependencies)."""

    def __init__(self, root, deps):
        self.root, self.deps = root, deps
        self.env = UnityPy.Environment()
        self.files = {}
        self._prefabs = {}

    def load(self, rel):
        rel = rel.replace("\\", "/")
        if rel in self.files:
            return self.files[rel]
        self.files[rel] = []
        for dep in self.deps.get(rel, []):
            self.load(dep)
        path = hs2_data.abdata_path(self.root, rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        bundle = self.env.load_file(path)
        self.files[rel] = [f for f in bundle.files.values() if isinstance(f, SerializedFile)]
        return self.files[rel]

    def prefab(self, rel, name):
        """Root Transform of prefab `name` in bundle `rel` (container lookup, scan fallback)."""
        key = (rel, name.lower())
        if key in self._prefabs:
            return self._prefabs[key]
        found = None
        for sf in self.load(rel):
            for obj in sf.objects.values():
                if obj.type.name != "AssetBundle":
                    continue
                for path, info in obj.read().m_Container:
                    base = path.rsplit("/", 1)[-1]
                    if base.lower() in (name.lower() + ".prefab", name.lower()):
                        go = _safe_read(info.asset)
                        if go is not None and type(go).__name__ == "GameObject":
                            found = _transform_of(go)
                            break
        if found is None:  # prefab not in the container (rare): scan root transforms
            for sf in self.load(rel):
                for obj in sf.objects.values():
                    if obj.type.name != "GameObject":
                        continue
                    go = obj.read()
                    if go.m_Name == name:
                        t = _transform_of(go)
                        if t is not None and not _pid(t.m_Father):
                            found = t
                            break
        self._prefabs[key] = found
        return found

    def texture(self, rel, name):
        """Texture2D `name` from bundle `rel` (for list-driven skin/makeup textures)."""
        for sf in self.load(rel):
            for obj in sf.objects.values():
                if obj.type.name == "Texture2D":
                    tex = obj.read()
                    if tex.m_Name == name:
                        return tex
        return None


def _transform_of(go):
    for comp in go.m_Components:
        pptr = getattr(comp, "component", comp)
        obj = _safe_read(pptr)
        if obj is not None and type(obj).__name__ in ("Transform", "RectTransform"):
            return obj
    return None


def _components(go):
    out = []
    for comp in go.m_Components:
        obj = _safe_read(getattr(comp, "component", comp))
        if obj is not None:
            out.append(obj)
    return out


def _monobehaviour_tree(go, script_names):
    for comp in go.m_Components:
        pptr = getattr(comp, "component", comp)
        try:
            reader = pptr.deref()
        except Exception:  # noqa: BLE001
            continue
        if reader.type.name != "MonoBehaviour":
            continue
        try:
            mb = reader.read()
            script = _safe_read(mb.m_Script)
            cls = getattr(script, "m_ClassName", "") if script is not None else ""
            if cls in script_names:
                return cls, reader.read_typetree()
        except Exception:  # noqa: BLE001
            continue
    return None, None


class Scene:
    """Union skeleton + baked parts + materials, all in Unity space (10 units = 1 m)."""

    def __init__(self, bundles, tex_dir):
        self.b = bundles
        self.tex_dir = tex_dir
        self.nodes = {}        # name -> {"parent": name|None, "world": 4x4, "tag": str}
        self.order = []
        self.parts = []
        self.materials = {}
        self.textures = {}     # (file, path_id) -> png basename
        self.warnings = []

    # ------------------------------------------------------------ nodes

    def _new_name(self, name, tag):
        if name not in self.nodes:
            return name
        i = 1
        while "%s.%s%s" % (name, tag, "" if i == 1 else i) in self.nodes:
            i += 1
        return "%s.%s%s" % (name, tag, "" if i == 1 else i)

    def _add_node(self, name, parent, world, tag):
        self.nodes[name] = {"parent": parent, "world": world, "tag": tag}
        self.order.append(name)

    def node_world(self, name):
        return self.nodes[name]["world"]

    # ------------------------------------------------------------ instances

    def place(self, root_t, tag, anchor=None, merge=False, local_override=None, hide_paths=()):
        """Instantiate the prefab rooted at `root_t` under node `anchor`.

        merge=True re-binds every transform whose name already exists in the body/head
        skeleton onto that node (clothes, the head mesh).  Returns {path_id: node name} and
        the renderers found [(GameObject, renderer, node name, hidden?)].
        """
        anchor_world = self.node_world(anchor) if anchor else np.eye(4)
        mapping, renderers = {}, []
        hide_ids = set(hide_paths)
        stack = [(root_t, anchor, anchor_world, True, False)]
        while stack:
            t, parent, parent_world, active, hidden = stack.pop()
            go = t.m_GameObject.read()
            local = _local(t)
            if local_override and go.m_Name in local_override:
                local = local_override[go.m_Name](local)
            world = parent_world @ local
            name = go.m_Name
            existing = self.nodes.get(name)
            if merge and existing is not None and existing["tag"] in SKELETON_TAGS:
                node = name
            else:
                node = self._new_name(name, tag)
                self._add_node(node, parent, world, tag)
            mapping[_oid(t)] = node
            # prefab roots are often saved inactive and switched on after Instantiate
            active = active and (bool(go.m_IsActive) or t is root_t)
            hidden = hidden or _pid(t.m_GameObject) in hide_ids
            for comp in _components(go):
                kind = type(comp).__name__
                if kind in ("SkinnedMeshRenderer", "MeshRenderer"):
                    renderers.append((go, comp, node, not active or hidden))
            for child in t.m_Children:
                ct = _safe_read(child)
                if ct is not None:
                    stack.append((ct, node, self.node_world(node), active, hidden))
        return mapping, renderers

    # ------------------------------------------------------------ meshes

    def add_renderers(self, renderers, mapping, source, role_of, colors=None, skip=()):
        for go, rend, node, hidden in renderers:
            low = go.m_Name.lower()
            if hidden or low.startswith(HIDE_RENDERERS) or go.m_Name in skip:
                continue
            if not getattr(rend, "m_Enabled", True):
                continue
            try:
                part = self._bake(go, rend, node, mapping, source, role_of(go.m_Name), colors or {})
            except Exception as exc:  # noqa: BLE001 - keep the rest of the character
                self.warnings.append("%s/%s: %s" % (source, go.m_Name, exc))
                continue
            if part is not None:
                self.parts.append(part)

    def _bake(self, go, rend, node, mapping, source, role, colors):
        skinned = type(rend).__name__ == "SkinnedMeshRenderer"
        if skinned:
            mesh_pptr = rend.m_Mesh
        else:
            mf = next((c for c in _components(go) if type(c).__name__ == "MeshFilter"), None)
            mesh_pptr = mf.m_Mesh if mf is not None else None
        mesh = _safe_read(mesh_pptr)
        builtin = None
        if mesh is None:
            builtin = BUILTIN_MESHES.get(_pid(mesh_pptr)) if mesh_pptr is not None else None
            if builtin is None:
                if mesh_pptr is not None and _pid(mesh_pptr):
                    self.warnings.append("%s/%s: mesh %d not resolvable" % (source, go.m_Name, _pid(mesh_pptr)))
                return None
        if builtin:
            verts, normals, uv0, tris = builtin_mesh(builtin)
            n = len(verts)
            uv1 = uv2 = None
            index = tris.ravel()
            submeshes = [[0, len(index), 0]]
            skinned = False
        else:
            h = MeshHandler(mesh)
            h.process()
            verts = np.asarray(h.m_Vertices, dtype=np.float64)[:, :3]
            n = len(verts)
            if n == 0:
                return None
            normals = np.asarray(h.m_Normals, dtype=np.float64)[:, :3] if h.m_Normals else None
            uv0 = np.asarray(h.m_UV0, dtype=np.float32)[:, :2] if h.m_UV0 else None
            uv1 = np.asarray(h.m_UV1, dtype=np.float32)[:, :2] if getattr(h, "m_UV1", None) else None
            uv2 = np.asarray(h.m_UV2, dtype=np.float32)[:, :2] if getattr(h, "m_UV2", None) else None
            index = np.asarray(h.m_IndexBuffer, dtype=np.int64)
            stride = 2 if getattr(h, "m_Use16BitIndices", True) else 4
            submeshes = []
            for sm in mesh.m_SubMeshes:
                first = int(sm.firstByte) // stride
                submeshes.append([first, int(sm.indexCount), int(getattr(sm, "topology", 0))])

        bones, weights_arr, index_arr = [], None, None
        if skinned and rend.m_Bones:
            mats = []
            for i, pptr in enumerate(rend.m_Bones):
                bt = _safe_read(pptr)
                bnode = mapping.get(_oid(bt)) if bt is not None else None
                if bnode is None and bt is not None:
                    bnode = bt.m_GameObject.read().m_Name
                    if bnode not in self.nodes:
                        bnode = None
                if bnode is None or i >= len(mesh.m_BindPose):
                    bones.append(node)
                    mats.append(self.node_world(node))
                    continue
                bones.append(bnode)
                mats.append(self.node_world(bnode) @ _mat4(mesh.m_BindPose[i]))
            mats = np.asarray(mats)
            index_arr = np.asarray(h.m_BoneIndices, dtype=np.int64).reshape(n, -1)
            if h.m_BoneWeights:
                weights_arr = np.asarray(h.m_BoneWeights, dtype=np.float64).reshape(n, -1)
            else:
                weights_arr = np.ones(index_arr.shape, dtype=np.float64)
            index_arr = np.clip(index_arr, 0, len(mats) - 1)
            blend = np.einsum("nk,nkij->nij", weights_arr, mats[index_arr])
            wsum = weights_arr.sum(axis=1)
            blend[wsum < 1e-6] = self.node_world(node)
        else:
            blend = np.broadcast_to(self.node_world(node), (n, 4, 4))
            bones = [node]
            index_arr = np.zeros((n, 1), dtype=np.int64)
            weights_arr = np.ones((n, 1), dtype=np.float64)
        lin = blend[:, :3, :3]
        baked = np.einsum("nij,nj->ni", lin, verts) + blend[:, :3, 3]
        arrays = {"vertices": baked.astype(np.float32), "indices": index.astype(np.int32),
                  "bone_indices": index_arr.astype(np.int32), "bone_weights": weights_arr.astype(np.float32)}
        if normals is not None and len(normals) == n:
            nb = np.einsum("nij,nj->ni", np.linalg.inv(lin).transpose(0, 2, 1), normals)
            nb /= np.maximum(np.linalg.norm(nb, axis=1, keepdims=True), 1e-12)
            arrays["normals"] = nb.astype(np.float32)
        if uv0 is not None and len(uv0) == n:
            arrays["uv0"] = uv0
        if uv1 is not None and len(uv1) == n:
            arrays["uv1"] = uv1
        if uv2 is not None and len(uv2) == n:
            arrays["uv2"] = uv2
        shape_names = []
        shapes = getattr(mesh, "m_Shapes", None) if mesh is not None else None
        if shapes is not None and shapes.channels:
            for ci, ch in enumerate(shapes.channels):
                frame = shapes.shapes[ch.frameIndex + ch.frameCount - 1]
                sv = shapes.vertices[frame.firstVertex:frame.firstVertex + frame.vertexCount]
                if not sv:
                    continue
                idx = np.array([v.index for v in sv], dtype=np.int64)
                delta = np.array([[v.vertex.x, v.vertex.y, v.vertex.z] for v in sv], dtype=np.float64)
                keep = idx < n
                idx, delta = idx[keep], delta[keep]
                delta = np.einsum("nij,nj->ni", lin[idx], delta)
                arrays["shape%d_idx" % len(shape_names)] = idx.astype(np.int32)
                arrays["shape%d_delta" % len(shape_names)] = delta.astype(np.float32)
                shape_names.append(ch.name.split(".", 1)[-1] if "." in ch.name else ch.name)

        mat_names = []
        for i, mpptr in enumerate(rend.m_Materials):
            if i >= max(len(submeshes), 1):
                break  # extra materials are overlay passes (wet/liquid) - skip
            mat = _safe_read(mpptr)
            mat_names.append(self.add_material(mat, role, colors, source) if mat is not None else None)
        return {"name": go.m_Name, "source": source, "role": role, "node": node,
                "skinned": bool(skinned), "bones": bones, "submeshes": submeshes,
                "materials": mat_names, "shape_keys": shape_names, "arrays": arrays}

    # ------------------------------------------------------------ materials

    def save_texture(self, tex, slot=""):
        if tex is None:
            return None
        key = (getattr(tex.assets_file, "name", ""), tex.object_reader.path_id if hasattr(tex, "object_reader") else id(tex))
        if key in self.textures:
            return self.textures[key]
        try:
            img = tex.image
        except Exception as exc:  # noqa: BLE001
            self.warnings.append("texture %s: %s" % (tex.m_Name, exc))
            self.textures[key] = None
            return None
        if img is None or img.size[0] == 0:
            self.textures[key] = None
            return None
        is_normal = slot.lower().startswith("_bumpmap") or tex.m_Name.lower().endswith(("_n", "_nml", "_normal"))
        if is_normal:
            img = unpack_normal(img, getattr(tex.m_TextureFormat, "name", str(tex.m_TextureFormat)))
        base = tex.m_Name
        name = base + ".png"
        i = 1
        used = set(v for v in self.textures.values() if v)
        while name in used:
            i += 1
            name = "%s_%d.png" % (base, i)
        os.makedirs(self.tex_dir, exist_ok=True)
        img.save(os.path.join(self.tex_dir, name))
        self.textures[key] = name
        return name

    def add_material(self, mat, role, colors, source):
        name = mat.m_Name
        key = name if name not in self.materials or self.materials[name].get("source") == source else "%s.%s" % (name, source)
        if key in self.materials:
            return key
        shader = _safe_read(mat.m_Shader)
        props = mat.m_SavedProperties
        textures, tex_st = {}, {}
        for slot, env in props.m_TexEnvs:
            tex = _safe_read(env.m_Texture)
            if tex is None or type(tex).__name__ != "Texture2D":
                continue
            png = self.save_texture(tex, slot)
            if png:
                textures[slot] = png
                sc, off = env.m_Scale, env.m_Offset
                tex_st[slot] = [float(sc.x), float(sc.y), float(off.x), float(off.y)]
        mcolors = {k: _color(v) for k, v in props.m_Colors}
        floats = {k: float(v) for k, v in props.m_Floats}
        self.materials[key] = {
            "name": name, "source": source, "role": role,
            "shader": getattr(shader, "m_Name", "") if shader is not None else "",
            "textures": textures, "tex_st": tex_st, "colors": mcolors, "floats": floats,
            "override": dict(colors),
        }
        return key

    # ------------------------------------------------------------ output

    def used_nodes(self):
        used = set()
        for part in self.parts:
            used.update(part["bones"])
            used.add(part["node"])
        out = set()
        for name in used:
            while name is not None and name not in out:
                out.add(name)
                name = self.nodes[name]["parent"]
        return [n for n in self.order if n in out]

    def write(self, out_dir, meta):
        import json

        os.makedirs(os.path.join(out_dir, "parts"), exist_ok=True)
        nodes = self.used_nodes()
        parts = []
        for i, part in enumerate(self.parts):
            fname = "%03d_%s.npz" % (i, "".join(c if c.isalnum() or c in "_-." else "_" for c in part["name"]))
            np.savez_compressed(os.path.join(out_dir, "parts", fname), **part["arrays"])
            entry = {k: v for k, v in part.items() if k != "arrays"}
            entry["npz"] = "parts/" + fname
            entry["verts"] = int(len(part["arrays"]["vertices"]))
            parts.append(entry)
        scene = dict(meta)
        scene.update({
            "unit_scale": 0.1,
            "nodes": [{"name": n, "parent": self.nodes[n]["parent"],
                       "world": np.round(self.nodes[n]["world"], 7).tolist()} for n in nodes],
            "parts": parts, "materials": self.materials, "warnings": self.warnings,
        })
        with open(os.path.join(out_dir, "scene.json"), "w", encoding="utf-8") as f:
            json.dump(scene, f, ensure_ascii=False, indent=1)
        return scene


def unpack_normal(img, fmt):
    """Unity stores tangent-space normals as DXT5nm (x in A, y in G) or BC5 (x R, y G)."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    if "BC5" in fmt:
        x, y = r, g
    elif a.std() > 0.02 and (r.min() > 0.9 or abs(r.mean() - 1.0) < 0.05):
        x, y = a, g
    elif b.mean() > 0.7:  # already a plain RGB normal map
        return img.convert("RGB")
    else:
        x, y = a if a.std() > 0.02 else r, g
    nx, ny = x * 2 - 1, y * 2 - 1
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    out = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], axis=-1)
    from PIL import Image
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGB")


def clothes_hidden_paths(root_t, state="full"):
    """GameObject path ids to hide for a clothes prefab: its 'half' (or 'full') state objects."""
    go = root_t.m_GameObject.read()
    cls, tree = _monobehaviour_tree(go, ("CmpClothes",))
    if tree is None:
        return set(), {}
    hide = set()
    pairs = [("objTopDef", "objTopHalf"), ("objBotDef", "objBotHalf")]
    for full, half in pairs:
        pick = tree.get(half if state == "full" else full) or {}
        pid = pick.get("m_PathID", 0)
        if pid:
            hide.add(pid)
    defaults = {}
    for i in (1, 2, 3, 4):
        c = tree.get("defMainColor0%d" % i)
        if c:
            defaults["color%d" % i] = _color(c)
        if "defGloss0%d" % i in tree:
            defaults["gloss%d" % i] = float(tree["defGloss0%d" % i])
        if "defMetallic0%d" % i in tree:
            defaults["metallic%d" % i] = float(tree["defMetallic0%d" % i])
    return hide, defaults


def component_defaults(root_t, script_names):
    """Default colours an accessory / hair component carries (defColor01.., acsDefColor..)."""
    go = root_t.m_GameObject.read()
    cls, tree = _monobehaviour_tree(go, script_names)
    out = {}
    if not tree:
        return out
    for key, value in tree.items():
        if isinstance(value, dict) and set(value) >= {"r", "g", "b", "a"} and key.lower().startswith(("def", "acsdef")):
            out[key] = _color(value)
    return out
