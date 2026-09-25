"""Assemble NARAKA character parts onto one skeleton and write scene.json.

A character in the game is several prefabs instantiated under one actor:
the outfit (actor_visual_part/<family>/<family>_lv_<skin>.prefab), its hair
(<family>_hair_lv_<skin>.prefab), the face (face/ch_f_face_battle.prefab) and
the skeleton they are bound to at runtime (ch_dummy_body/ch_f_dummy_body.prefab).

How the parts find their bones:
- outfit / hair SkinnedMeshRenderers carry no bone references; their meshes
  list m_BoneNameHashes = CRC32 of the bone's transform path below the actor
  root ("MotionRoot/gMan Pelvis/gMan Spine/...");
- bones the skeleton lacks (breasts, skirt, hair and cloth chains) ship inside
  the outfit prefab as loose children; the game re-parents them, so their
  parent is recovered by finding the skeleton path P with crc32(P/name) in the
  mesh hashes;
- the face renderers do reference bones (by object), and their meshes are
  built at runtime from *_data.asset (AvatarFaceMeshData: positions, normals,
  UVs, indices, bind poses, skin weights).

Rest pose = the meshes' bind pose: every bone's rest world matrix is
renderer_world @ inverse(bindpose), which agrees across all meshes to float
precision and with ch_f_dummy_body to a few micrometres; bones no mesh uses
take the skeleton prefab's local transform.  Vertices therefore only need the
renderer's world matrix.  Units: Unity metres, Y up.
"""
import json
import os
import re
import zlib

import numpy as np

import naraka_mesh

LOD_SUFFIX = re.compile(r"_L\d+$")


# ---------------------------------------------------------------- transforms
def trs(t):
    p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
    x, y, z, w = q.x, q.y, q.z, q.w
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array([s.x, s.y, s.z])
    m[:3, 3] = [p.x, p.y, p.z]
    return m


def components(go):
    return [c.component for c in go.m_Component]


def transform_of(go):
    for c in components(go):
        if c.type.name in ("Transform", "RectTransform"):
            return c.read()
    raise ValueError("no transform on " + go.m_Name)


def children(go):
    for ch in transform_of(go).m_Children:
        t = ch.read()
        yield t, t.m_GameObject.read()


def script_name(mb):
    try:
        return mb.m_Script.read().m_ClassName
    except Exception:
        return ""


# ---------------------------------------------------------------- textures
def _normal_rg(img):
    """BC5 normal maps decode to RG(+B=0): rebuild B so Blender reads a normal."""
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    if a[..., 2].max() > 0.01:
        return img
    x, y = a[..., 0] * 2 - 1, a[..., 1] * 2 - 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    a[..., 2] = z * 0.5 + 0.5
    from PIL import Image
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGB")


class Scene:
    def __init__(self, name, out_dir):
        self.name = name
        self.out_dir = out_dir
        self.nodes = {}          # path -> {"parent", "local", "world" (rest), "bind" bool}
        self.order = []
        self.hash_to_path = {}
        self.tid = {}            # Transform path_id -> node path (standalone prefabs)
        self.hair_colors = {}    # material name -> sRGB hair colour (hair_custom_data)
        self.parts = []
        self.materials = {}
        self.textures = {}       # texture name -> png file name
        self.log = []
        os.makedirs(os.path.join(out_dir, "parts"), exist_ok=True)
        os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)

    # ------------------------------------------------------------ nodes
    def add_node(self, path, local, parent):
        if path in self.nodes:
            return
        pw = self.nodes[parent]["world"] if parent in self.nodes else np.eye(4)
        self.nodes[path] = {"parent": parent, "local": local, "world": pw @ local, "bind": False}
        self.order.append(path)
        self.hash_to_path[zlib.crc32(path.encode("utf-8"))] = path

    def add_hierarchy(self, go, prefix="", parent_world=None, skip=None):
        """Every transform below go, keyed by path (go itself is the root)."""
        for t, cgo in children(go):
            if skip and skip(cgo):
                continue
            path = prefix + cgo.m_Name
            self.add_node(path, trs(t), prefix[:-1] if prefix else None)
            self.tid[t.object_reader.path_id if hasattr(t, "object_reader") else id(t)] = path
            self.add_hierarchy(cgo, path + "/", skip=skip)

    def set_bind(self, path, world):
        node = self.nodes[path]
        if node["bind"]:
            return
        node["world"] = world
        node["bind"] = True

    def refresh(self):
        """Re-derive the rest world of bind-less nodes from their parents."""
        for path in self.order:
            node = self.nodes[path]
            if node["bind"]:
                continue
            parent = self.nodes.get(node["parent"])
            node["world"] = (parent["world"] if parent else np.eye(4)) @ node["local"]

    def by_name(self, name):
        for path in self.order:
            if path.rsplit("/", 1)[-1] == name:
                return path
        return None

    # ------------------------------------------------------------ textures / materials
    def texture(self, ptr, kind):
        if ptr is None or ptr.m_PathID == 0:
            return None
        tex = ptr.read()
        name = tex.m_Name
        if name in self.textures:
            return self.textures[name]
        png = re.sub(r"[^\w.-]", "_", name) + ".png"
        path = os.path.join(self.out_dir, "textures", png)
        if not os.path.isfile(path):
            try:
                img = tex.image
            except Exception as exc:
                self.log.append("texture %s: %s" % (name, exc))
                self.textures[name] = None
                return None
            if kind == "normal":
                img = _normal_rg(img)
            img.save(path)
        self.textures[name] = png
        return png

    def material(self, ptr, role):
        if ptr is None or ptr.m_PathID == 0:
            return None
        mat = ptr.read()
        key = mat.m_Name
        if key in self.materials:
            return key
        props = mat.m_SavedProperties
        shader = ""
        try:
            sh = mat.m_Shader.read()
            shader = sh.m_ParsedForm.m_Name
        except Exception:
            pass
        kinds = {"_BumpMap": "normal", "_NormalBentMap": "normal"}
        textures, st = {}, {}
        for slot, env in props.m_TexEnvs:
            png = self.texture(env.m_Texture, kinds.get(slot, "color"))
            if png:
                textures[slot] = png
                st[slot] = [env.m_Scale.x, env.m_Scale.y, env.m_Offset.x, env.m_Offset.y]
        self.materials[key] = {
            "shader": shader,
            "role": role,
            "textures": textures,
            "tex_st": st,
            "colors": {k: [v.r, v.g, v.b, v.a] for k, v in props.m_Colors},
            "floats": {k: float(v) for k, v in props.m_Floats},
            "keywords": mat.m_ShaderKeywords if isinstance(mat.m_ShaderKeywords, str) else " ".join(mat.m_ShaderKeywords or []),
        }
        if "_IrisDiffuseTex" in textures and "_MainTex" in textures:
            png = self._bake_eye(key, textures, self.materials[key]["colors"], self.materials[key]["floats"])
            if png:
                textures["_MainTex"] = png
        if "_EyeBrowDecalTex" in textures and "_MainTex" in textures:
            png = self._bake_brows(key, textures, self.materials[key]["colors"])
            if png:
                textures["_MainTex"] = png
        if "_MainSHMap" in textures:
            # LX22 hair: _MainTex is a strand-ID map (A = strand coverage) and
            # _MainSHMap signed lighting data; the colour is the hairstyle's
            # hair_custom_data BaseColorA (Assembler.hair_colors fills it in)
            self.materials[key]["hair_color"] = self.hair_colors.get(key, [0.2, 0.165, 0.165, 1.0])
        return key

    # ------------------------------------------------------------ shader bakes
    def _img(self, png):
        from PIL import Image
        return np.asarray(Image.open(os.path.join(self.out_dir, "textures", png)).convert("RGBA")).astype(np.float32) / 255.0

    def _save(self, arr, png):
        from PIL import Image
        Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(
            os.path.join(self.out_dir, "textures", png))
        return png

    def _bake_eye(self, key, tex, colors, floats):
        """LX22 eye: the sclera texture fills the eye's UV disc (centre 0.5, 0.5); the
        shader draws the iris (_IrisDiffuseTex, grey, tinted by _IrisColor) inside
        radius _IrisDail and darkens the pupil (_PupilDail of the iris)."""
        sclera, iris = self._img(tex["_MainTex"]), self._img(tex["_IrisDiffuseTex"])
        h, w = sclera.shape[:2]
        r_iris = float(floats.get("_IrisDail", 0.24))
        tint = np.array((colors.get("_IrisColor") or [0.4, 0.3, 0.2, 1])[:3], np.float32)
        v, u = np.mgrid[0:h, 0:w].astype(np.float32)
        u, v = (u + 0.5) / w - 0.5, 0.5 - (v + 0.5) / h
        d = np.sqrt(u * u + v * v)
        iu = np.clip(((u / (2 * r_iris)) + 0.5) * iris.shape[1], 0, iris.shape[1] - 1).astype(int)
        iv = np.clip((0.5 - (v / (2 * r_iris))) * iris.shape[0], 0, iris.shape[0] - 1).astype(int)
        ic = iris[iv, iu, :3] * tint / 0.45
        mask = np.clip((r_iris - d) / (0.08 * r_iris), 0, 1)[..., None]
        out = sclera.copy()
        out[..., :3] = sclera[..., :3] * (1 - mask) + ic * mask
        return self._save(out, re.sub(r"[^\w.-]", "_", key) + "_eye_composite.png")

    def _bake_brows(self, key, tex, colors):
        """LX22 custom face: eyebrows are a decal (_EyeBrowDecalTex, R = coverage)
        placed in face UV space by _EyeBrowDecalTransform (u, v, width, height) and
        mirrored to the other half (face UV is symmetric about u = 0.5)."""
        face, brow = self._img(tex["_MainTex"]), self._img(tex["_EyeBrowDecalTex"])
        t = colors.get("_EyeBrowDecalTransform")
        if not t or t[2] <= 0:
            return None
        col = np.array((colors.get("_EyebrowTargetColorL") or [0.05, 0.04, 0.03, 1])[:3], np.float32)
        col = np.maximum(col, 0.04)
        h, w = face.shape[:2]
        out = face.copy()
        from PIL import Image
        bw, bh = max(1, int(round(t[2] * w))), max(1, int(round(t[3] * h)))
        cov = np.asarray(Image.fromarray((brow[..., 0] * 255).astype(np.uint8)).resize((bw, bh), Image.BILINEAR)).astype(np.float32) / 255.0
        for mirror in (False, True):
            c = cov[:, ::-1] if mirror else cov
            u0 = (1.0 - t[0] - t[2]) if mirror else t[0]
            x0 = int(round(u0 * w))
            y0 = int(round((1.0 - t[1] - t[3]) * h))
            x1, y1 = min(w, x0 + bw), min(h, y0 + bh)
            if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                continue
            a = c[:y1 - y0, :x1 - x0, None] * 0.9
            out[y0:y1, x0:x1, :3] = out[y0:y1, x0:x1, :3] * (1 - a) + col * a
        return self._save(out, re.sub(r"[^\w.-]", "_", key) + "_brows.png")

    # ------------------------------------------------------------ parts
    def add_part(self, name, source, role, world, mesh, bones, materials, extra_weights=None):
        """mesh = naraka_mesh.decode() dict; bones = node path per bone index."""
        verts = mesh["vertices"].astype(np.float64)
        verts = verts @ world[:3, :3].T + world[:3, 3]
        rot = world[:3, :3] / np.linalg.norm(world[:3, :3], axis=0, keepdims=True)
        data = {"vertices": verts.astype(np.float32), "indices": mesh["indices"].astype(np.int32)}
        if "normals" in mesh:
            n = mesh["normals"][:, :3].astype(np.float64) @ rot.T
            data["normals"] = (n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)).astype(np.float32)
        for k in ("uv0", "uv1", "uv2", "colors"):
            if k in mesh:
                data[k] = mesh[k].astype(np.float32)
        if "weights" in mesh and "bone_indices" in mesh:
            data["bone_weights"] = mesh["weights"].astype(np.float32)
            data["bone_indices"] = mesh["bone_indices"].astype(np.int32)
        else:
            data["bone_weights"] = np.ones((len(verts), 1), np.float32)
            data["bone_indices"] = np.zeros((len(verts), 1), np.int32)
        safe = re.sub(r"[^\w.-]", "_", "%02d_%s" % (len(self.parts), name))
        np.savez_compressed(os.path.join(self.out_dir, "parts", safe + ".npz"), **data)
        self.parts.append({
            "name": name, "source": source, "role": role, "npz": "parts/%s.npz" % safe,
            "bones": bones, "materials": materials,
            "submeshes": [list(s) for s in mesh["submeshes"]],
        })

    def write(self, meta=None):
        self.refresh()
        doc = {
            "name": self.name,
            "unit_scale": 1.0,
            "nodes": [{"name": p, "parent": self.nodes[p]["parent"], "world": self.nodes[p]["world"].tolist()}
                      for p in self.order],
            "parts": self.parts,
            "materials": self.materials,
            "meta": meta or {},
            "log": self.log,
        }
        with open(os.path.join(self.out_dir, "scene.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        return doc


# ---------------------------------------------------------------- roles
def skip_renderer(scene, go, r):
    """Renderers the game does not draw: disabled ones and material-less proxies
    (the *_sim meshes that cloth simulation drives)."""
    mats = [m for m in (r.m_Materials or []) if m and m.m_PathID]
    enabled = getattr(r, "m_Enabled", 1)
    if not enabled or not mats:
        scene.log.append("skipped %s renderer %s" % ("disabled" if not enabled else "material-less", go.m_Name))
        return True
    return False


def skeleton_for(game, name):
    """The runtime skeleton a whole-body prefab is bound to: the matching
    ch_dummy_body/<name>_dummy_body.prefab (trailing _NN / _suffix dropped one
    at a time), else art/characters/_common/avatar/<name>_skeleton.fbx."""
    parts = name.split("_")
    while len(parts) > 1:
        stem = "_".join(parts)
        for cand in ("assets/res/prefab/actor_visual_part/ch_dummy_body/%s_dummy_body.prefab" % stem,
                     "assets/art/characters/_common/avatar/%s_skeleton.fbx" % stem):
            if cand in game.asset_bundle:
                return cand
        parts = parts[:-1]
    return None


def role_of(part_name, shader, prefab_kind):
    s = shader.lower()
    n = part_name.lower()
    if prefab_kind == "face":
        if n.startswith("eyelash"):
            return "eyelash"
        if n.startswith("eye"):
            return "eye"
        return "skin_head"
    if "skin" in s:
        return "skin_body"
    if "hair" in s:
        return "hair"
    return "clothes"


class Assembler:
    """Parts -> Scene.  sex 'f' or 'm' picks the skeleton prefab."""

    SKELETONS = {
        "f": "assets/res/prefab/actor_visual_part/ch_dummy_body/ch_f_dummy_body.prefab",
        "m": "assets/res/prefab/actor_visual_part/ch_dummy_body/ch_m_dummy_body.prefab",
    }
    FACES = {
        "f": "assets/res/prefab/actor_visual_part/face/ch_f_face_battle.prefab",
        "m": "assets/res/prefab/actor_visual_part/face/ch_m_face_battle.prefab",
    }

    def __init__(self, game, scene, sex="f", skeleton=None, lod=0, keep_fx=False):
        self.game = game
        self.keep_fx = keep_fx
        self.scene = scene
        self.lod = lod
        self.skeleton = skeleton if skeleton is not None else self.SKELETONS.get(sex)
        if not self.skeleton:
            return
        root = game.asset(self.skeleton).read()
        scene.add_hierarchy(root, skip=lambda go: any(c.type.name in ("SkinnedMeshRenderer", "MeshRenderer")
                                                      for c in components(go)))
        scene.log.append("skeleton %s: %d nodes" % (self.skeleton, len(scene.order)))

    # --- helpers
    def _lod0(self, root_go):
        """PathIDs of the renderers the prefab's ActorBodyVisualCell lists for LOD 0."""
        for c in components(root_go):
            if c.type.name != "MonoBehaviour":
                continue
            mb = c.read()
            if script_name(mb) != "ActorBodyVisualCell":
                continue
            tt = c.read_typetree()
            key = "lod%dRendererAssistants" % self.lod
            assists = tt.get(key) or []
            if not assists:
                return None
            ids = set()
            for a in assists:
                try:
                    obj = resolve(self.game, c, a)
                    ids.add(obj.read_typetree()["_renderer"]["m_PathID"])
                except Exception:
                    pass
            return ids or None
        return None

    def _attach_loose(self, go, hashes, binds=(), final=True):
        """Loose bone subtrees of an outfit prefab: find their skeleton parent by
        path hash; failing that (hair/face runtime meshes have no hashes) by the
        parent under which the most subtree bones land exactly on a bind pose."""
        names = []

        def walk(g, rel):
            for t, c in children(g):
                names.append((rel + c.m_Name, t, c))
                walk(c, rel + c.m_Name + "/")
        walk(go, "")
        skel_paths = list(self.scene.order)
        parent_of_top = None
        for rel in [go.m_Name] + [go.m_Name + "/" + r for r, _, _ in names]:
            for p in skel_paths:
                if zlib.crc32((p + "/" + rel).encode("utf-8")) in hashes:
                    parent_of_top = p
                    break
            if parent_of_top:
                break
        locs = None
        if parent_of_top is None and len(binds):
            # the subtree root's POSITION: ribbon/belt chains are often saved with
            # their rotations off the bind pose, but the root still sits where its
            # parent puts it.  (Skipped for zero offsets, which would sit on any bone.)
            locs = self._subtree_locals(go)
            if np.linalg.norm(locs[0][:3, 3]) > 1e-3:
                bind_pos = binds[:, :3, 3]
                cands = []
                for p in skel_paths:
                    top = (self.scene.nodes[p]["world"] @ locs[0])[:3, 3]
                    if np.linalg.norm(bind_pos - top, axis=1).min() < 1e-3:
                        cands.append((p.count("/"), p))
                if cands:
                    parent_of_top = min(cands)[1]
        if parent_of_top is None and len(binds):
            # most subtree bones landing on a bind pose wins; exact first, then with
            # growing tolerance - some prefabs saved their ribbon/belt chains a few
            # cm off the bind pose (drift grows along the chain)
            locs = locs or self._subtree_locals(go)
            errs = {}
            for p in skel_paths:
                pw = self.scene.nodes[p]["world"]
                errs[p] = [float(np.abs(binds - (pw @ m)).max(axis=(1, 2)).min()) for m in locs]
            # loose tolerances only in the last round, after every exact match
            # (possibly another loose chain - the real parent) is in place
            for tol in ((1e-3, 1e-2, 5e-2) if final else (1e-3,)):
                best = (0, 0, None)
                for p, e in errs.items():
                    hit = sum(1 for x in e if x < tol)
                    key = (hit, -p.count("/"))
                    if hit and key > best[:2]:
                        best = (hit, -p.count("/"), p)
                if best[2] is not None:
                    parent_of_top = best[2]
                    if tol > 1e-3:
                        self.scene.log.append("%s: parent found at %.0f mm tolerance" % (go.m_Name, tol * 1000))
                    break
        if parent_of_top is None and not final:
            return None
        base = (parent_of_top + "/") if parent_of_top else ""
        top_t = transform_of(go)
        self.scene.add_node(base + go.m_Name, trs(top_t), parent_of_top)
        for rel, t, c in names:
            path = base + go.m_Name + "/" + rel
            parent = path.rsplit("/", 1)[0]
            self.scene.add_node(path, trs(t), parent)
        return parent_of_top

    @staticmethod
    def _subtree_locals(go):
        """Matrices of go and its descendants relative to go's parent."""
        out = []

        def walk(g, m):
            out.append(m)
            for t, c in children(g):
                walk(c, m @ trs(t))
        walk(go, trs(transform_of(go)))
        return out

    # --- prefabs
    def load_hair_colors(self, asset_path):
        """character/hair_custom_data/<prefab>/hair_custom_data_01.asset holds each
        hair material's default BaseColorA - the colour the game shows (checked
        against the item icons: red, blonde and black styles all match)."""
        name = asset_path.rsplit("/", 1)[-1][:-7]
        path = "assets/res/character/hair_custom_data/%s/hair_custom_data_01.asset" % name
        if path not in self.game.asset_bundle:
            return
        try:
            tt = self.game.objects(path)[0].read_typetree()
        except Exception as exc:
            self.scene.log.append("hair colours %s: %s" % (name, exc))
            return
        for e in tt.get("serializedCustomHairData") or []:
            c = e.get("BaseColorA")
            if c:
                self.scene.hair_colors[e["materialName"]] = [c["r"], c["g"], c["b"], 1.0]

    def add_prefab(self, asset_path, kind="outfit"):
        """kind: outfit | hair | face | item (anything with (Skinned)MeshRenderers)."""
        self.load_hair_colors(asset_path)
        root = self.game.asset(asset_path).read()
        lod0 = self._lod0(root)
        renderers, loose = [], []
        for t, go in children(root):
            comps = components(go)
            types = [c.type.name for c in comps]
            if "SkinnedMeshRenderer" in types or "MeshRenderer" in types:
                if go.m_Name.lower().startswith("fx_") and not self.keep_fx:
                    self.scene.log.append("skipped effect mesh %s" % go.m_Name)
                    continue
                renderers.append((t, go, comps))
            elif go.m_Name not in ("MotionRoot", "body_dummy"):     # the prefab's own skeleton stub
                loose.append(go)
        if kind == "face":
            self._face_bones(root)
        # hashes the outfit's meshes ask for
        meshes = []
        for t, go, comps in renderers:
            for c in comps:
                if c.type.name == "SkinnedMeshRenderer":
                    smr = c.read()
                    if lod0 is not None and c.path_id not in lod0:
                        continue
                    if lod0 is None and LOD_SUFFIX.search(go.m_Name):
                        continue
                    meshes.append((t, go, smr, c))
                elif c.type.name == "MeshRenderer":
                    if LOD_SUFFIX.search(go.m_Name):
                        continue
                    meshes.append((t, go, c.read(), c))
        hashes = set()
        decoded = {}
        binds = []
        for t, go, r, c in meshes:
            mesh = self._mesh(go, r, root)
            decoded[c.path_id] = mesh
            if mesh:
                hashes.update(mesh.get("bone_hashes") or [])
                if not mesh.get("bone_hashes") and not getattr(r, "m_Bones", None):
                    binds += [trs(t) @ np.linalg.inv(bp) for bp in mesh["bindposes"]]
        binds = np.array(binds) if binds else np.zeros((0, 4, 4))
        # loose bones may hang under other loose bones (earrings on a hair chain):
        # attach what can be placed, then retry the rest against the grown tree
        pending = list(loose)
        for final in (False, False, True):
            left = []
            for go in pending:
                parent = self._attach_loose(go, hashes, binds, final=final)
                if parent is None and not final:
                    left.append(go)
                    continue
                self.scene.log.append("%s: loose %s under %s" % (os.path.basename(asset_path), go.m_Name, parent))
            self.scene.refresh()
            pending = left
            if not pending:
                break
        self.scene.refresh()
        added = 0
        for t, go, r, c in meshes:
            mesh = decoded[c.path_id]
            if not mesh or skip_renderer(self.scene, go, r):
                continue
            world = trs(t)            # renderer objects sit directly under the prefab root
            bones = self._bones(go, r, mesh, world)
            mats = []
            for i, mp in enumerate(r.m_Materials):
                mat = mp.read() if mp and mp.m_PathID else None
                shader = ""
                if mat is not None:
                    try:
                        shader = mat.m_Shader.read().m_ParsedForm.m_Name
                    except Exception:
                        pass
                mats.append(self.scene.material(mp, role_of(go.m_Name, shader, kind)))
            role = role_of(go.m_Name, "", kind) if kind == "face" else (
                self.scene.materials.get(mats[0], {}).get("role", "clothes") if mats and mats[0] else "clothes")
            self.scene.add_part(go.m_Name, asset_path, role, world, mesh, bones, mats)
            added += 1
        self.scene.refresh()
        self.scene.log.append("%s: %d parts" % (asset_path, added))
        return added

    def add_standalone(self, asset_path):
        """A self-contained prefab (monster, NPC, weapon, prop): its own transform
        hierarchy is the skeleton; renderers may sit at any depth."""
        root = self.game.asset(asset_path).read()
        lod0 = self._lod0(root)
        base = len(self.scene.order)
        self.scene.add_hierarchy(root)
        added = 0
        found = []

        def walk(go, path):
            for t, c in children(go):
                p = (path + "/" if path else "") + c.m_Name
                for comp in components(c):
                    if comp.type.name not in ("SkinnedMeshRenderer", "MeshRenderer"):
                        continue
                    if c.m_Name.lower().startswith("fx_") and not self.keep_fx:
                        continue
                    if lod0 is not None and comp.type.name == "SkinnedMeshRenderer" and comp.path_id not in lod0:
                        continue
                    if lod0 is None and LOD_SUFFIX.search(c.m_Name):
                        continue
                    found.append((p, c, comp.read()))
                walk(c, p)
        walk(root, "")
        for path, go, r in found:
            if skip_renderer(self.scene, go, r):
                continue
            mesh = self._mesh(go, r, root)
            if not mesh:
                continue
            world = self.scene.nodes[path]["world"]
            bones = self._bones(go, r, mesh, world)
            if bones == [None]:
                bones = [path]
            mats = []
            for mp in r.m_Materials:
                shader = ""
                try:
                    shader = mp.read().m_Shader.read().m_ParsedForm.m_Name
                except Exception:
                    pass
                mats.append(self.scene.material(mp, role_of(go.m_Name, shader, "item")))
            role = self.scene.materials.get(mats[0], {}).get("role", "clothes") if mats and mats[0] else "clothes"
            self.scene.add_part(go.m_Name, asset_path, role, world, mesh, bones, mats)
            added += 1
        self.scene.refresh()
        self.scene.log.append("%s: %d parts, %d nodes" % (asset_path, added, len(self.scene.order) - base))
        return added

    def _mesh(self, go, r, root):
        if hasattr(r, "m_Mesh"):          # SkinnedMeshRenderer
            if r.m_Mesh and r.m_Mesh.m_PathID:
                return naraka_mesh.decode(r.m_Mesh.deref().read_typetree())
            return self._runtime_mesh(go, root)
        for c in components(go):          # MeshRenderer -> MeshFilter
            if c.type.name == "MeshFilter":
                mf = c.read()
                if mf.m_Mesh and mf.m_Mesh.m_PathID:
                    return naraka_mesh.decode(mf.m_Mesh.deref().read_typetree())
        return None

    # --- face: runtime meshes from AvatarFaceData
    def _face_bones(self, root):
        """Face_* bones (eyelids, eyeballs) live under the face prefab's own short
        MotionRoot/gMan Pelvis/gMan Neck/gMan Head chain; hang them on the real head."""
        head = self.scene.by_name("gMan Head")

        def walk(go, parent_path):
            for t, c in children(go):
                if c.m_Name.startswith("gMan "):
                    walk(c, self.scene.by_name(c.m_Name) or parent_path)
                elif c.m_Name.startswith("Face_"):
                    path = parent_path + "/" + c.m_Name
                    self.scene.add_node(path, trs(t), parent_path)
                    walk(c, path)
                elif c.m_Name == "MotionRoot":
                    walk(c, self.scene.by_name("MotionRoot") or parent_path)
        walk(root, head)

    def _runtime_mesh(self, go, root):
        """Hair and face renderers ship without a Mesh; their LXRendererAssistant
        points at an AvatarFaceMeshData (m_VertexData list, m_Indices, ...)."""
        for c in components(go):
            if c.type.name != "MonoBehaviour":
                continue
            tt = c.read_typetree()
            ref = tt.get("avatarMeshAsset")
            if ref and ref.get("m_PathID"):
                md = resolve(self.game, c, ref)
                if md is not None:
                    return _face_mesh(md.read_typetree())
        self.scene.log.append("%s: no mesh" % go.m_Name)
        return None

    # --- bones of one renderer
    def _bones(self, go, r, mesh, world):
        bones = []
        binds = mesh.get("bindposes")
        refs = list(getattr(r, "m_Bones", None) or [])
        if refs:                      # explicit bone objects (face)
            for i, ref in enumerate(refs):
                path = self.scene.tid.get(ref.m_PathID)
                if path is None:
                    path = self.scene.by_name(ref.read().m_GameObject.read().m_Name)
                bones.append(path)
                if path and binds is not None and i < len(binds):
                    self.scene.set_bind(path, world @ np.linalg.inv(binds[i]))
            return bones
        hashes = mesh.get("bone_hashes") or []
        for i, h in enumerate(hashes):
            path = self.scene.hash_to_path.get(h)
            if path is None:
                self.scene.log.append("%s: bone hash %d unresolved" % (go.m_Name, h))
            bones.append(path)
            if path and binds is not None and i < len(binds):
                self.scene.set_bind(path, world @ np.linalg.inv(binds[i]))
        if not hashes and binds is not None and len(binds):
            # runtime (hair) mesh: no names, no hashes - the bind pose says which bone.
            # Matched top-down by POSITION: once a bone's rest is snapped to its bind
            # pose its children follow it, so chains whose rotations were saved off
            # the bind pose (ribbons, belts) still line up link by link.
            targets = [world @ np.linalg.inv(bp) for bp in binds]
            found = [None] * len(targets)
            for _ in range(64):
                self.scene.refresh()
                paths = list(self.scene.order)
                worlds = np.array([self.scene.nodes[p]["world"] for p in paths])
                depth = [p.count("/") for p in paths]
                progress = False
                for i, target in enumerate(targets):
                    if found[i] is not None:
                        continue
                    near = np.nonzero(np.linalg.norm(worlds[:, :3, 3] - target[:3, 3], axis=1) < 1e-3)[0]
                    if not len(near):
                        continue
                    err = np.abs(worlds[near] - target).max(axis=(1, 2))
                    # ties (a collider node sitting exactly on its bone): the shallower path
                    k = min(range(len(near)), key=lambda n: (round(float(err[n]), 3), depth[near[n]], near[n]))
                    found[i] = paths[near[k]]
                    if err[k] > 1e-3 and not self.scene.nodes[found[i]]["bind"]:
                        self.scene.set_bind(found[i], target)
                        self.scene.log.append("%s: rest of %s rotated onto its bind pose (%.3f)" % (
                            go.m_Name, found[i].rsplit("/", 1)[-1], err[k]))
                    progress = True
                if not progress:
                    break
            self.scene.refresh()
            paths = list(self.scene.order)
            worlds = np.array([self.scene.nodes[p]["world"] for p in paths])
            depth = [p.count("/") for p in paths]
            for i, target in enumerate(targets):
                if found[i] is None:
                    err = np.abs(worlds - target).max(axis=(1, 2))
                    j = min(range(len(paths)), key=lambda k: (round(float(err[k]), 3), depth[k], k))
                    found[i] = paths[j]
                    self.scene.log.append("%s: bind %d nearest %s off by %.3f" % (go.m_Name, i, paths[j], err[j]))
            return found
        if not hashes:               # static mesh: rides its own node or the root
            bones = [None]
        return bones


def resolve(game, owner, ptr):
    """A typetree {m_FileID, m_PathID} seen from `owner` (PPtr or object reader)."""
    if not ptr or not ptr.get("m_PathID"):
        return None
    sf = getattr(owner, "assets_file", None) or getattr(owner, "assetsfile", None)
    if ptr.get("m_FileID", 0) == 0:
        return sf.objects.get(ptr["m_PathID"])
    ext = sf.externals[ptr["m_FileID"] - 1]
    name = ext.path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for key, f in game.env.files.items():
        if key.lower() == name and hasattr(f, "objects"):
            return f.objects.get(ptr["m_PathID"])
    return None


def _face_mesh(mt):
    """AvatarFaceMeshData (typetree dict) -> naraka_mesh-style dict."""
    vd = mt["m_VertexData"]
    out = {"name": mt.get("m_MeshName", "")}
    out["vertices"] = np.array([[v["position"]["x"], v["position"]["y"], v["position"]["z"]] for v in vd], np.float32)
    if vd and "normal" in vd[0]:
        out["normals"] = np.array([[v["normal"]["x"], v["normal"]["y"], v["normal"]["z"]] for v in vd], np.float32)
    if mt.get("m_UVData"):
        out["uv0"] = np.array([[u["x"], u["y"]] for u in mt["m_UVData"]], np.float32)
    elif mt.get("m_HairUVSetData"):
        out["uv0"] = np.array([[u["uv0"]["x"], u["uv0"]["y"]] for u in mt["m_HairUVSetData"]], np.float32)
        out["uv1"] = np.array([[u["uv1"]["x"], u["uv1"]["y"]] for u in mt["m_HairUVSetData"]], np.float32)
    if mt.get("m_VertexColorData"):
        rgba = np.array([c["rgba"] for c in mt["m_VertexColorData"]], np.uint32)
        out["colors"] = np.stack([(rgba >> s) & 255 for s in (0, 8, 16, 24)], 1).astype(np.float32) / 255.0
    idx = np.array(mt["m_Indices"], np.int64)
    out["indices"] = idx
    out["submeshes"] = [(0, len(idx), 0)]
    skin = mt.get("m_AnimSkinData") or []
    if skin:
        out["weights"] = np.array([[s["boneWeight"][k] for k in "xyzw"] for s in skin], np.float32)
        out["bone_indices"] = np.array([[s["boneIndex"][k] for k in "xyzw"] for s in skin], np.int32)
    bp = mt.get("m_BindPoses") or []
    out["bindposes"] = np.array([[[m["e%d%d" % (r, c)] for c in range(4)] for r in range(4)] for m in bp],
                                np.float64).reshape(-1, 4, 4)
    out["bone_hashes"] = []
    return out
