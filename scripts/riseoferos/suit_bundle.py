# -*- coding: utf-8 -*-
"""Read a Rise of Eros 'suit' straight from the asset bundles (no AssetStudio pass).

A suit (outfit variant) is the nude base body + a set of clothing component
meshes skinned to the shared skeleton.  ``suit_parts.py`` only lists the parts;
this module pulls everything the assembler needs out of the bundles with UnityPy:

* per part: the mesh (vertices / normals / UV0 / triangles / sub-meshes), the
  bone names + weights of a skinned part, the world placement of a static part
  (glasses, wreath, cat ears ...), and the renderer's materials with their
  texture NAMES (``_BaseMap`` albedo, ``_BumpMap`` normal, ``_MetallicGlossMap``);
* the textures themselves, decoded from the suit's ``chara_tex_components_*``
  bundle into PNGs;
* a dressed-state selection (which alternates / toys to leave out) that the
  assembler follows and that ``suit_overrides.json`` can correct per suit.

Why not the per-object FBX that ``extract_character.ps1`` produces?  AssetStudio
names the export after the GameObject, so same-named parts of different suits
overwrite each other (``Underwear_obj001`` ...), suits added by an update are not
in an old extraction at all (j01 ProUniform, b01 Wulin), and the FBX carry no
materials so every texture had to be guessed from the piece name.  The stub
bundle references the exact mesh and material by PPtr, so reading it directly is
both complete and unambiguous.

Coordinate frame: mesh data of skinned parts is stored in the same Z-up model
space as the base body (``pc_<id>_nk_body``); the Blender importer mirrors X, the
same mapping the FBX route ends up with (verified vertex-by-vertex on j01).  A
static part's mesh is local; its placement is the composed transform of the
same-named object in ``chara_components_pc_<id>.ab``, given in Unity's Y-up
world (the model is rotated -90 deg about X there), converted by the importer.

CLI:
    python suit_bundle.py --game <AssetBundles> --id j01 --suit prouniform --out <dir>
writes ``<dir>/suit.json``, ``<dir>/parts/<root>.npz`` and ``<dir>/textures/*.png``.
"""
import argparse
import glob
import json
import os
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
import UnityPy  # noqa: E402
from UnityPy.files import SerializedFile  # noqa: E402
from UnityPy.helpers.MeshHelper import MeshHandler  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES_PATH = os.path.join(HERE, "suit_overrides.json")

TEX_SLOTS = {"albedo": ("_BaseMap", "_MainTex"), "normal": ("_BumpMap",),
             "mgac": ("_MetallicGlossMap",)}
# adult toys and pure H-scene props that no dressed look includes
TOY_RE = re.compile(r"vibrator|dildo|plug|eggvib", re.IGNORECASE)
# a variant state of another piece in the same suit: "OpenVest" next to "CloseVest",
# "SleepwearPull" next to "Sleepwear", "StockingsBroken" next to "Stockings" ...
STATE_TOKENS = ("Open", "open", "Pull", "Broken", "Hole", "R18", "openbelow", "openup")
NIPPLE_RE = re.compile(r"nipple|patch|pastie", re.IGNORECASE)
# breast-area pieces that do not actually cover the chest
NOT_COVERING_RE = re.compile(r"rope|harness|knot|strap|necklace|scarf|tie$|collar|ribbon|wing|tassel", re.IGNORECASE)
TRANSPARENT_RE = re.compile(r"panties|stocking|fishnet|veil|lace|mesh|net$|sock|tights|garter|transparen", re.IGNORECASE)


def _read(pptr):
    try:
        return pptr.read()
    except Exception:
        return None


def _components(go):
    out = []
    for comp in go.m_Components:
        obj = _read(comp.component if hasattr(comp, "component") else comp)
        if obj is not None:
            out.append(obj)
    return out


def _transform(go):
    for obj in _components(go):
        if type(obj).__name__ in ("Transform", "RectTransform"):
            return obj
    return None


def _find_renderer(go, tr):
    """(GameObject, renderer) of the first Skinned/MeshRenderer under go."""
    for obj in _components(go):
        if type(obj).__name__ in ("SkinnedMeshRenderer", "MeshRenderer"):
            return go, obj
    for child in tr.m_Children:
        ctr = _read(child)
        cgo = _read(ctr.m_GameObject) if ctr is not None else None
        ctr2 = _transform(cgo) if cgo is not None else None
        if ctr2 is not None:
            found = _find_renderer(cgo, ctr2)
            if found:
                return found
    return None


def _go_name(transform):
    go = _read(transform.m_GameObject) if transform is not None else None
    return go.m_Name if go is not None else None


def _ancestors(transform):
    """Names of the transform's parents, nearest first."""
    out = []
    t = transform
    while t is not None and getattr(t.m_Father, "path_id", 0):
        t = _read(t.m_Father)
        if t is None:
            break
        out.append(_go_name(t))
    return out


def _quat_mul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def _quat_to_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _world_matrix(transform):
    """Composed local TRS chain of a Unity transform as a 4x4 (Unity world)."""
    chain = []
    t = transform
    while t is not None:
        p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
        chain.append(((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z)))
        t = _read(t.m_Father) if getattr(t.m_Father, "path_id", 0) else None
    world = np.eye(4)
    for pos, rot, scl in reversed(chain):
        local = np.eye(4)
        local[:3, :3] = _quat_to_matrix(rot) @ np.diag(scl)
        local[:3, 3] = pos
        world = world @ local
    return world


def load_skeleton(game, cid):
    """Rest (bind) matrix of every bone of the character's body, in the model frame, by name.

    Not the prefab's transforms -- those sit in whatever pose the bare bundle was
    saved in -- but the body mesh's bind poses: BindPose maps mesh space to bone
    space, so its inverse is the bone's matrix in the (Z-up) model frame."""
    path = os.path.join(game, "chara_bare_pc_%s_nk.ab" % cid)
    out = {}
    if not os.path.isfile(path):
        return out
    env = UnityPy.load(path)
    for obj in env.objects:
        if obj.type.name != "SkinnedMeshRenderer":
            continue
        renderer = obj.read()
        go = _read(renderer.m_GameObject)
        if go is None or not go.m_Name.lower().endswith("_nk_body"):
            continue
        mesh = _read(renderer.m_Mesh)
        if mesh is None:
            continue
        for i, pptr in enumerate(renderer.m_Bones):
            if i >= len(mesh.m_BindPose):
                break
            name = _go_name(_read(pptr))
            b = mesh.m_BindPose[i]
            bind = np.array([[b.e00, b.e01, b.e02, b.e03], [b.e10, b.e11, b.e12, b.e13],
                             [b.e20, b.e21, b.e22, b.e23], [b.e30, b.e31, b.e32, b.e33]], dtype=np.float64)
            if name and name not in out:
                try:
                    out[name] = np.linalg.inv(bind)
                except np.linalg.LinAlgError:
                    pass
        if out:
            break
    return out


# where the game hangs an accessory that has no body bone of its own, by Area
AREA_BONES = (
    (re.compile(r"hair|head|eyes|ears|nose|eye", re.I), "Bip001 Head"),
    (re.compile(r"neck", re.I), "Bip001 Neck"),
    (re.compile(r"nipple", re.I), "Nipple_{side}"),
    (re.compile(r"breast|wholebody|styling", re.I), "Bip001 Spine2"),
    (re.compile(r"belly|butt|panties|waist|lower", re.I), "Bip001 Pelvis"),
    (re.compile(r"arms|hand|wrist", re.I), "Bip001 {side} Hand"),
    (re.compile(r"feet|foot", re.I), "Bip001 {side} Foot"),
    (re.compile(r"legs|leg|calf|thigh", re.I), "Bip001 {side} Thigh"),
)


def attach_bone_for(root_name, area):
    side = "R" if re.search(r"(^|_)R(?=[A-Z_])|_R_obj|^Right", root_name) else "L"
    for pattern, bone in AREA_BONES:
        if pattern.search(area or ""):
            return bone.format(side=side)
    return "Bip001 Pelvis"


def _texture_names(material):
    """{slot: Texture2D object} for the albedo / normal / mgac slots of a material."""
    found = {}
    try:
        envs = material.m_SavedProperties.m_TexEnvs
        items = envs.items() if isinstance(envs, dict) else envs
    except Exception:
        return found
    for key, value in items:
        for slot, names in TEX_SLOTS.items():
            if key in names and slot not in found:
                tex = _read(value.m_Texture) if hasattr(value, "m_Texture") else None
                if tex is not None:
                    found[slot] = tex
    return found


def _base_color(material):
    """The material's _BaseColor / _Color as an RGBA list, or None."""
    try:
        colors = material.m_SavedProperties.m_Colors
        items = colors.items() if isinstance(colors, dict) else colors
    except Exception:
        return None
    for key, value in items:
        if key in ("_BaseColor", "_Color"):
            try:
                return [float(value.r), float(value.g), float(value.b), float(value.a)]
            except Exception:
                return None
    return None


def piece_of(renderer_name):
    """'lynn_Upper_BreastArea_OpenVest_obj001' -> ('OpenVest', 'BreastArea')."""
    stem = re.sub(r"_obj\d+(?: \(\d+\))?$", "", renderer_name)
    segs = stem.split("_")
    area = next((s for s in segs if s.endswith("Area") or s.endswith("Tattoo")), "")
    piece = segs[-1] if len(segs) > 1 else stem
    return piece, area


def stub_files(env, stub_path):
    want = os.path.normcase(os.path.abspath(stub_path))
    out = []
    for name, bundle in env.files.items():
        if os.path.normcase(os.path.abspath(name)) == want:
            for sf in bundle.files.values():
                if isinstance(sf, SerializedFile):
                    out.append(sf)
    return out


def bundle_paths(game, cid, suit):
    stub = os.path.join(game, "accessory_components_pc_%s_suit_%s.ab" % (cid, suit))
    extra = [os.path.join(game, "chara_components_pc_%s.ab" % cid),
             os.path.join(game, "chara_components_common.ab"),
             os.path.join(game, "chara_tex_components_pc_%s_suit_%s.ab" % (cid, suit))]
    if suit == "fm":
        # the demon-form ("fm") props come from the shared accessory pool: their
        # materials sit in one tiny accessory_components_common_common_<x>.ab each,
        # the textures in chara_tex_components_common_common_<x>.ab
        # (older props use the per-accessory scheme instead: accessory_<hash>_common_<x>.ab
        # for the material, chara_tex_<hash>_common_<x>.ab for the textures)
        extra += [os.path.join(game, f) for f in sorted(os.listdir(game))
                  if re.match(r"(chara_tex_components_common|accessory_components_common_common_"
                              r"|accessory_[0-9a-f]{8}_common_fm|chara_tex_[0-9a-f]{8}_common_fm)", f.lower())]
    return stub, [p for p in extra if os.path.isfile(p)]


def read_suit(game, cid, suit):
    """Every part of the suit with mesh arrays, bones, placement and materials."""
    stub, extra = bundle_paths(game, cid, suit)
    if not os.path.isfile(stub):
        raise FileNotFoundError(stub)
    env = UnityPy.load(stub, *extra)
    # index of every GameObject in the component bundles by name (static placement)
    comp_gos = {}
    for name, bundle in env.files.items():
        if os.path.basename(name).lower().startswith("chara_components"):
            for sf in bundle.files.values():
                if not isinstance(sf, SerializedFile):
                    continue
                for obj in sf.objects.values():
                    if obj.type.name == "GameObject":
                        go = obj.read()
                        comp_gos.setdefault(go.m_Name.lower(), go)
    skeleton = load_skeleton(game, cid)
    parts = []
    for sf in stub_files(env, stub):
        for obj in sf.objects.values():
            if obj.type.name != "GameObject":
                continue
            go = obj.read()
            tr = _transform(go)
            if tr is None or (tr.m_Father is not None and getattr(tr.m_Father, "path_id", 0)):
                continue                      # not a stub root
            found = _find_renderer(go, tr)
            if not found:
                continue
            rgo, renderer = found
            skinned = type(renderer).__name__ == "SkinnedMeshRenderer"
            if skinned:
                mesh = _read(renderer.m_Mesh)
            else:
                mf = next((c for c in _components(rgo) if type(c).__name__ == "MeshFilter"), None)
                mesh = _read(mf.m_Mesh) if mf is not None else None
            if mesh is None:
                parts.append({"root": go.m_Name, "renderer": rgo.m_Name, "error": "mesh PPtr unresolved"})
                continue
            handler = MeshHandler(mesh)
            handler.process()
            verts = np.asarray(handler.m_Vertices, dtype=np.float32)[:, :3]
            normals = np.asarray(handler.m_Normals, dtype=np.float32)[:, :3] if handler.m_Normals else None
            uv0 = np.asarray(handler.m_UV0, dtype=np.float32)[:, :2] if handler.m_UV0 else None
            indices = np.asarray(handler.m_IndexBuffer, dtype=np.int32)
            stride = 2 if getattr(handler, "m_Use16BitIndices", True) else 4
            submeshes = []
            for i, sm in enumerate(mesh.m_SubMeshes):
                first = int(sm.firstByte) // stride
                submeshes.append((first, int(sm.indexCount), i))
            part = {"root": go.m_Name, "renderer": rgo.m_Name, "mesh": mesh.m_Name,
                    "kind": "skinned" if skinned else "static", "verts": int(len(verts)),
                    "submeshes": submeshes}
            part["piece"], part["area"] = piece_of(rgo.m_Name)
            part["area_bone"] = attach_bone_for(go.m_Name, part["area"])
            arrays = {"vertices": verts, "indices": indices}
            if normals is not None and len(normals) == len(verts):
                arrays["normals"] = normals
            if uv0 is not None and len(uv0) == len(verts):
                arrays["uv0"] = uv0
            if skinned:
                bones, ancestors = [], {}
                for pptr in renderer.m_Bones:
                    t = _read(pptr)
                    name = _go_name(t) if t is not None else None
                    bones.append(name)
                    if t is not None and name:
                        ancestors[name] = _ancestors(t)
                part["bones"] = bones
                part["bone_ancestors"] = ancestors
                root_bone = _go_name(_read(renderer.m_RootBone)) if getattr(renderer.m_RootBone, "path_id", 0) else None
                part["root_bone"] = root_bone
                # where the mesh sits at bind time: BoneWorld * BindPose (identical for
                # every bone).  Most parts are authored Z-up with a -90 deg X renderer,
                # a few (c01 SwimBra) Y-up with an identity one -- this catches both.
                part["world_matrix"], part["placement_from"] = None, "none"
                for i, pptr in enumerate(renderer.m_Bones):
                    t = _read(pptr)
                    if t is None or i >= len(mesh.m_BindPose):
                        continue
                    b = mesh.m_BindPose[i]
                    bind = np.array([[b.e00, b.e01, b.e02, b.e03], [b.e10, b.e11, b.e12, b.e13],
                                     [b.e20, b.e21, b.e22, b.e23], [b.e30, b.e31, b.e32, b.e33]], dtype=np.float64)
                    part["world_matrix"] = (_world_matrix(t) @ bind).tolist()
                    part["placement_from"] = "bindpose"
                    break
                if part["world_matrix"] is None:
                    part["world_matrix"] = _world_matrix(tr).tolist()
                    part["placement_from"] = "stub"
                # an accessory rigged only to its own physics bones (hat, tail,
                # tassels, dangling earrings) is attached to a body bone at runtime by
                # its Area: offer that placement too (Unity world of the body bone in the
                # bare skeleton x mesh-in-root-bone-space) and let the importer pick
                if not any(a in skeleton for name in bones if name for a in [name] + ancestors.get(name, [])):
                    attach = attach_bone_for(go.m_Name, part["area"])
                    root_pptr = renderer.m_RootBone if getattr(renderer.m_RootBone, "path_id", 0) else (renderer.m_Bones[0] if renderer.m_Bones else None)
                    root_t = _read(root_pptr) if root_pptr is not None else None
                    if attach in skeleton and root_t is not None and part["placement_from"] == "bindpose":
                        rel = np.linalg.inv(_world_matrix(root_t)) @ np.array(part["world_matrix"])
                        part["attach_bone"] = attach
                        part["attach_matrix"] = (skeleton[attach] @ rel).tolist()
                indices = np.asarray(handler.m_BoneIndices, dtype=np.int32).reshape(len(verts), -1)
                if handler.m_BoneWeights:
                    weights = np.asarray(handler.m_BoneWeights, dtype=np.float32).reshape(len(verts), -1)
                else:
                    # one bone per vertex and no weight stream (nails, pauldrons, dangling earrings)
                    weights = np.ones(indices.shape, dtype=np.float32)
                arrays["bone_indices"] = indices
                arrays["bone_weights"] = weights
            else:
                placed = comp_gos.get(rgo.m_Name.lower()) or comp_gos.get(go.m_Name.lower())
                src = _transform(placed) if placed is not None else tr
                part["world_matrix"] = _world_matrix(src).tolist()
                part["placement_from"] = "components" if placed is not None else "stub"
                if placed is None:
                    # a bare stub prop (cow earrings): local mesh, no placement anywhere
                    # -> the game hangs it on the Area's bone; offer that reading
                    attach = attach_bone_for(go.m_Name, part["area"])
                    if attach in skeleton:
                        part["attach_bone"] = attach
                        part["attach_matrix"] = skeleton[attach].tolist()
            mats = []
            for pptr in renderer.m_Materials:
                material = _read(pptr)
                if material is None:
                    mats.append({"name": None, "textures": {}})
                    continue
                texs = _texture_names(material)
                mats.append({"name": material.m_Name,
                             "textures": {slot: tex.m_Name for slot, tex in texs.items()},
                             "color": _base_color(material),
                             "_tex_objects": texs})
            part["materials"] = mats
            part["_arrays"] = arrays
            parts.append(part)
    parts.sort(key=lambda p: p["root"].lower())
    return parts


# ---------------------------------------------------------------- dressed state
def select_dressed(parts, overrides=None):
    """Return {root: reason} of parts to leave out for the dressed look."""
    excluded = {}
    # the piece name comes from the renderer; when several roots share one renderer
    # (WeddingTights / WeddingTightsBroken use the same mesh with another material)
    # only the root name tells the states apart
    renderers = [p.get("renderer") for p in parts if "error" not in p]
    pieces = {}
    for p in parts:
        if "error" in p:
            continue
        shared = renderers.count(p.get("renderer")) > 1
        pieces[p["root"]] = re.sub(r"_obj\d+$", "", p["root"]) if shared else p.get("piece", p["root"])
    lower = {root: piece.lower() for root, piece in pieces.items()}

    def sibling_exists(root, candidate):
        cand = candidate.lower()
        return any(r != root and lower[r] == cand for r in lower)

    for root, piece in pieces.items():
        if TOY_RE.search(piece):
            excluded[root] = "toy"
            continue
        for token in STATE_TOKENS:
            if token in piece:
                stripped = piece.replace(token, "")
                swapped = piece.replace(token, "Close") if token.lower() == "open" else ""
                if stripped and (sibling_exists(root, stripped) or (swapped and sibling_exists(root, swapped))
                                 or sibling_exists(root, stripped.strip("_"))):
                    excluded[root] = "alternate state of %s" % (stripped if sibling_exists(root, stripped) else swapped)
                    break
    # nipple jewellery / pasties under a covering top
    covering = [p for p in parts if "error" not in p and p["root"] not in excluded
                and p.get("area", "").lower() == "breastarea"
                and not NOT_COVERING_RE.search(p["piece"]) and "open" not in p["piece"].lower()]
    if covering:
        for p in parts:
            if "error" in p or p["root"] in excluded:
                continue
            if p.get("area", "").lower() == "nipplearea" or NIPPLE_RE.search(p["piece"]):
                excluded[p["root"]] = "under %s" % covering[0]["piece"]
    if overrides:
        for root in overrides.get("include", []):
            excluded.pop(root, None)
        for root in overrides.get("exclude", []):
            if root in pieces:
                excluded[root] = "override"
    return excluded


def load_overrides(cid, suit):
    if not os.path.isfile(OVERRIDES_PATH):
        return {}
    with open(OVERRIDES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("%s:%s" % (cid, suit), {})


# ---------------------------------------------------------------- export
def export_suit(game, cid, suit, out_dir, base_fbx_root=None):
    parts = read_suit(game, cid, suit)
    os.makedirs(os.path.join(out_dir, "parts"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
    overrides = load_overrides(cid, suit)
    excluded = select_dressed(parts, overrides)
    manifest = {"id": cid, "suit": suit, "parts": [], "excluded": excluded, "overrides": overrides}
    written = {}
    for part in parts:
        entry = {k: v for k, v in part.items() if not k.startswith("_")}
        if "error" in part:
            manifest["parts"].append(entry)
            continue
        npz = os.path.join(out_dir, "parts", re.sub(r"[^A-Za-z0-9_.()-]", "_", part["root"]) + ".npz")
        np.savez_compressed(npz, **part["_arrays"])
        entry["npz"] = npz
        # a one-sided pool prop instanced as <x>_L and <x>_R: the _R root is the mirror image
        entry["mirrored"] = bool(re.search(r"_R_obj\d+$", part["root"], re.IGNORECASE)) and any(
            other is not part and other.get("renderer") == part["renderer"] for other in parts)
        entry["transparent"] = bool(TRANSPARENT_RE.search(part["piece"])
                                    or any(m.get("name") and "transparen" in m["name"].lower() for m in part["materials"]))
        for material in entry["materials"]:
            files = {}
            for slot, tex in part["materials"][entry["materials"].index(material)].get("_tex_objects", {}).items():
                name = re.sub(r"[^A-Za-z0-9_.-]", "_", tex.m_Name)
                path = os.path.join(out_dir, "textures", name + ".png")
                if name not in written:
                    if not os.path.isfile(path):
                        try:
                            tex.image.save(path)
                        except Exception as exc:  # noqa: BLE001
                            files[slot + "_error"] = str(exc)[:80]
                            continue
                    written[name] = path
                files[slot] = written.get(name, path)
            if "albedo" not in files and material.get("name") and base_fbx_root:
                # texture not in the suit's own bundle (j01 idol's hair buns live in the
                # hair set): fall back to the character's extracted texture folder by name
                pattern = os.path.join(base_fbx_root, "_textures", material["name"] + "*")
                for candidate in sorted(glob.glob(pattern)):
                    if re.search(r"_(albedo|abedo)", candidate, re.IGNORECASE) and candidate.lower().endswith(".png"):
                        files["albedo"] = candidate
                        break
            material["files"] = files
            material.pop("_tex_objects", None)
        manifest["parts"].append(entry)
    # base body: fm suits use the character's fm body when the game ships one
    manifest["base"] = "pc_%s_nk" % cid
    if suit == "fm" and base_fbx_root:
        fm = os.path.join(base_fbx_root, "pc_%s_fm_nk" % cid, "FBX_GameObjects", "pc_%s_fm_nk" % cid, "pc_%s_fm_nk.fbx" % cid)
        if os.path.isfile(fm):
            manifest["base"] = "pc_%s_fm_nk" % cid
    with open(os.path.join(out_dir, "suit.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help="AssetBundles directory")
    ap.add_argument("--id", required=True)
    ap.add_argument("--suit", required=True)
    ap.add_argument("--out", required=True, help="output dir (suit.json, parts/, textures/)")
    ap.add_argument("--fbx-root", default="", help="D:\\roe_exports\\<id> (to detect an fm base body)")
    args = ap.parse_args()
    manifest = export_suit(args.game, args.id, args.suit, args.out, args.fbx_root or None)
    for part in manifest["parts"]:
        state = "EXCLUDED(%s)" % manifest["excluded"][part["root"]] if part["root"] in manifest["excluded"] else "dressed"
        tex = ",".join(sorted(f for m in part.get("materials", []) for f in m.get("files", {}) if not f.endswith("_error")))
        print("%-44s %-8s %6s %-10s %s" % (part["root"][:44], part.get("kind", "?"), part.get("verts", "-"), state, tex))
    print("SUIT_JSON=%s" % os.path.join(args.out, "suit.json"))


if __name__ == "__main__":
    main()
