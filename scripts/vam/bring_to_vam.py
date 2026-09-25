"""Bring a skinned game character into VaM as real clothing / hair items + an appearance preset.

    blender -b <character.blend> --factory-startup -P blender_dump_skinned.py -- <work>\\_src [--bake <eye material>]
    python bring_to_vam.py --profile fiona_df [--install] [--no-thumbs]

Unlike ``import_to_vam.ps1`` (which writes .duf files for VaM's in-game creator), this writes the
items VaM stores itself -- ``.vam`` / ``.vaj`` / ``.vab`` via ``vam_items`` -- so they show up in the
clothing and hair lists straight away, plus a ``Preset_<name>.vap`` appearance preset that puts
them all on a person.

How the character is fitted to VaM's Genesis 2 female:

1. **Skeleton retarget.**  Every deforming bone of the source rig is mapped to a G2F joint
   (spine chains by arc length); each mapped bone gets an affine map that carries its segment
   (joint -> child joint) onto the G2F segment: rotation, scale along the bone, a girth factor
   across it.  Unmapped helper / twist / corrective bones follow their nearest mapped ancestor.
   The meshes are then linear-blend-skinned with their own weights through those maps, which
   poses A-pose arms into VaM's T-pose and stretches each limb to G2F's proportions without
   tearing at the joints.
2. **Face** (profiles with a ``face`` entry, ``face_fit.py``).  G2F's head is fitted to the
   source face -- landmarks, a similarity (VaM keeps its head size), a thin-plate spline and a
   surface pull -- and written as the head morph ``<name> Head`` (eye bone centres move with the
   eyeballs).  The source face texture is baked into G2F's face UVs (the base character's own
   texture takes over at the seams and where the source painted hair on the scalp), the eyebrow
   cards are painted in, and the source iris goes into the base character's eye texture.  The
   head bone of the retarget uses the same similarity, so the hair sits on the fitted head.
   Without a face entry the head is a scaled ICP of the source scalp onto G2F's.
3. **Rest body.**  VaM draws the body under clothes.  Instead of pushing garments out of the skin
   (which dents rigid plates), G2F -- with the head morph on -- is pulled in wherever a garment
   comes too close; that shape is the ``<name> Body`` morph and every item is wrapped against it.
4. **Wrap + write.**  ``vam_items.compute_wrap`` stores every vertex against its closest skin
   triangle the way VaM's creator does; textures are converted (DirectX normals -> OpenGL, ORM ->
   gloss / specular maps, hair colour baked from the root-tip ramp).  The preset puts the items,
   both morphs, the face / eye textures and the lash colour on the base character.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import face_fit as ff  # noqa: E402
import vam_items as vi  # noqa: E402
import vam_lib as vl  # noqa: E402

VAM_ROOT = r"E:\tools\vam\vam1.22\vam1.22\1.22"
CACHE = r"D:\vam_exports\_cache"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"

PROFILES = {
    "fiona_df": {
        "name": "Fiona DF",
        "creator": "VindictusDF",
        "work": r"D:\vam_imports\FionaDF",
        "unit": 0.01,                      # source centimetres
        "character": "Evey",               # VaM skin the preset uses (closest to Fiona's face)
        "rig": "ue5",
        "shoe_object": "Fiona_Foot",       # forefoot mapped ball -> shoe tip
        "items": [
            {"display": "Fiona DF Armor Top", "object": "Fiona_Upper", "exclude": ["MI_PCF_Upper01"],
             "tags": "top,armor,torso,arms", "clearance": 0.004},
            {"display": "Fiona DF Armor Bottom", "object": "Fiona_Lower", "exclude": ["MI_PCF_Lower01"],
             "tags": "bottom,armor,hip,legs", "clearance": 0.004, "disable_anatomy": True},
            {"display": "Fiona DF Gauntlets", "object": "Fiona_Hand", "tags": "gloves,armor,hands,arms",
             "clearance": 0.003},
            {"display": "Fiona DF Boots", "object": "Fiona_Foot", "tags": "shoes,boots,armor,feet,legs",
             "clearance": 0.003},
            {"display": "Fiona DF Hair", "object": "Fiona_Hair", "type": "HairFemale", "tags": "hair,long",
             "clearance": 0.001, "hair": True},
        ],
        "face": {
            "object": "Fiona_Face",
            "skin": "MI_Fiona_Face01_",
            "eyes": "MI_Fiona_Face01_EyeBall",           # dump with --bake MI_Fiona_Face01_EyeBall
            "brows": "MI_Fona_Face01_Eyebrow",           # hair cards on the skin: painted into the face
            "lashes_hsv": (0.08, 0.45, 0.32),             # VaM's own lashes, tinted brown
            "texture_size": 2048,
        },
    },
}


# ----------------------------------------------------------------------------- source

def to_vam(points, unit):
    """Blender (x, y, z) -> VaM (-x, z, -y) * unit: Z-up right-handed -> Unity Y-up; a mirror, so
    polygon order stays as authored and comes out clockwise-from-outside like VaM's own meshes."""
    p = np.asarray(points, dtype=np.float64) * unit
    return np.stack([-p[..., 0], p[..., 2], -p[..., 1]], axis=-1)


class Source:
    def __init__(self, dump_dir, unit):
        self.meta = json.load(open(os.path.join(dump_dir, "src.json"), encoding="utf-8"))
        self.npz = np.load(os.path.join(dump_dir, "src.npz"))
        self.unit = unit
        arm = self.meta["armature"]
        self.bones = arm["bones"]
        self.parents = arm["parents"]
        self.index = {n: i for i, n in enumerate(self.bones)}
        self.heads = to_vam(self.npz["bone_head"], unit)
        self.objects = {o["name"]: o for o in self.meta["objects"]}

    def head(self, bone):
        return self.heads[self.index[bone]]

    def obj(self, name):
        o = self.objects[name]
        k = o["key"]
        d = {"meta": o, "verts": to_vam(self.npz[k + "_verts"], self.unit)}
        for f in ("loop_vert", "loop_start", "loop_total", "mat", "uv", "w_vert", "w_group", "w_weight"):
            d[f] = self.npz[k + "_" + f]
        return d


# ----------------------------------------------------------------------------- G2F

class G2F:
    def __init__(self, cache=CACHE):
        self.cache_npz = os.path.join(cache, "base_female.npz")
        base = np.load(self.cache_npz)
        self.verts = base["verts"].astype(np.float64)
        self.poly_len = base["poly_len"]
        self.poly_idx = base["poly_idx"]
        self.poly_mat = base["poly_mat"]
        self.meta = json.load(open(os.path.join(cache, "base_female.json"), encoding="utf-8"))
        self.normals = vl.outward_normals(self.verts.astype(np.float32), self.poly_len, self.poly_idx).astype(np.float64)
        bones = json.load(open(os.path.join(cache, "bones.json"), encoding="utf-8"))
        self.joints = {k: np.array(v["female"], dtype=np.float64) for k, v in bones.items()}

    def j(self, name):
        return self.joints[name]


# ----------------------------------------------------------------------------- retarget

UE5_LIMBS = {
    "clavicle": "Collar", "upperarm": "Shldr", "lowerarm": "ForeArm", "hand": "Hand",
    "thigh": "Thigh", "calf": "Shin", "foot": "Foot", "ball": "Toe",
}
UE5_FINGERS = {"thumb": "Thumb", "index": "Index", "middle": "Mid", "ring": "Ring", "pinky": "Pinky"}
UE5_SPINE = ["pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01"]
G2F_SPINE = ["hip", "abdomen2", "chest", "neck"]


def _polyline_point(points, t):
    """Point at arc-length fraction t of a polyline."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = seg.sum()
    target = t * total
    acc = 0.0
    for i, s in enumerate(seg):
        if acc + s >= target or i == len(seg) - 1:
            f = 0.0 if s <= 0 else (target - acc) / s
            return points[i] + (points[i + 1] - points[i]) * min(max(f, 0.0), 1.0)
        acc += s
    return points[-1]


def ue5_joint_targets(src, g2f):
    """Target G2F position of every mapped UE5 joint, and each mapped bone's primary child joint."""
    tgt, child = {}, {}
    # spine by arc length
    fs = np.array([src.head(b) for b in UE5_SPINE])
    gs = np.array([g2f.j(b) for b in G2F_SPINE])
    seg = np.linalg.norm(np.diff(fs, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    for b, t in zip(UE5_SPINE, cum):
        tgt[b] = _polyline_point(gs, t)
    for a, b in zip(UE5_SPINE[:-1], UE5_SPINE[1:]):
        child[a] = b
    # neck_01 -> neck_02 -> head
    tgt["head"] = g2f.j("head")
    n1, n2, hd = src.head("neck_01"), src.head("neck_02"), src.head("head")
    frac = np.linalg.norm(n2 - n1) / max(np.linalg.norm(n2 - n1) + np.linalg.norm(hd - n2), 1e-9)
    tgt["neck_02"] = g2f.j("neck") + (g2f.j("head") - g2f.j("neck")) * frac
    child["neck_01"] = "neck_02"
    child["neck_02"] = "head"
    for side, S in (("l", "l"), ("r", "r")):
        for ue, dz in UE5_LIMBS.items():
            tgt["%s_%s" % (ue, side)] = g2f.j(S + dz)
        for a, b in (("clavicle", "upperarm"), ("upperarm", "lowerarm"), ("lowerarm", "hand"),
                     ("thigh", "calf"), ("calf", "foot"), ("foot", "ball")):
            child["%s_%s" % (a, side)] = "%s_%s" % (b, side)
        hand_f, hand_g = src.head("hand_" + side), g2f.j(S + "Hand")
        for ue, dz in UE5_FINGERS.items():
            for k in (1, 2, 3):
                tgt["%s_%02d_%s" % (ue, k, side)] = g2f.j("%s%s%d" % (S, dz, k))
            child["%s_01_%s" % (ue, side)] = "%s_02_%s" % (ue, side)
            child["%s_02_%s" % (ue, side)] = "%s_03_%s" % (ue, side)
            meta = "%s_metacarpal_%s" % (ue, side)
            if meta in src.index:
                base_f = src.head("%s_01_%s" % (ue, side))
                base_g = tgt["%s_01_%s" % (ue, side)]
                m = src.head(meta)
                f = np.dot(m - hand_f, base_f - hand_f) / max(np.dot(base_f - hand_f, base_f - hand_f), 1e-12)
                tgt[meta] = hand_g + (base_g - hand_g) * min(max(f, 0.0), 1.0)
                child[meta] = "%s_01_%s" % (ue, side)
        child["hand_" + side] = "middle_01_" + side
    child["pelvis"] = "spine_01"
    return tgt, child


def rotation_between(u, v):
    u = u / np.linalg.norm(u)
    v = v / np.linalg.norm(v)
    c = float(np.dot(u, v))
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:
        axis = np.cross(u, [1.0, 0, 0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(u, [0, 1.0, 0])
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    ax = np.cross(u, v)
    k = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + k + k @ k * (1.0 / (1.0 + c))


def segment_map(h_f, t_f, h_g, t_g, girth=1.0):
    """4x4 affine: h_f -> h_g, t_f -> t_g, scale along the segment, ``girth`` across it."""
    u = t_f - h_f
    lf = np.linalg.norm(u)
    lg = np.linalg.norm(t_g - h_g)
    R = rotation_between(u, t_g - h_g)
    un = u / lf
    S = girth * np.eye(3) + (lg / lf - girth) * np.outer(un, un)
    M = np.eye(4)
    M[:3, :3] = R @ S
    M[:3, 3] = h_g - R @ S @ h_f
    return M


def scaled_icp(src_pts, dst_pts, iters=30, trim=0.8):
    """Uniform scale + translation (no rotation) moving src_pts onto dst_pts' surface samples."""
    s, t = 1.0, dst_pts.mean(0) - src_pts.mean(0)
    for _ in range(iters):
        cur = src_pts * s + t
        idx = vl_nearest(cur, dst_pts)
        d = np.linalg.norm(dst_pts[idx] - cur, axis=1)
        keep = d <= np.quantile(d, trim)
        a, b = src_pts[keep], dst_pts[idx][keep]
        am, bm = a.mean(0), b.mean(0)
        s = float(np.sum((a - am) * (b - bm)) / max(np.sum((a - am) ** 2), 1e-12))
        t = bm - s * am
    return s, t


def vl_nearest(points, targets, chunk=1024):
    out = np.empty(len(points), dtype=np.int64)
    t2 = np.einsum("ij,ij->i", targets, targets)
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk]
        d = t2[None, :] - 2 * p @ targets.T
        out[s:s + chunk] = np.argmin(d, axis=1)
    return out


class Retarget:
    def __init__(self, src, g2f, head_fit=None, head_similarity=None, toe_tips=None, log=print):
        self.src, self.g2f = src, g2f
        tgt, child = ue5_joint_targets(src, g2f)
        self.targets = tgt
        mats = {}
        for bone, ch in child.items():
            if bone in src.index and ch in src.index:
                mats[bone] = segment_map(src.head(bone), src.head(ch), tgt[bone], tgt[ch])
        # The spine only moves.  The two rigs place their spine joints differently (UE's
        # spine_05 -> neck_01 leans back 37 deg, G2F's chest -> neck is upright), so aligning the
        # segments would rotate the whole chest and swing everything hanging off it (the scarf
        # tails went out behind her); the torso lengths agree anyway (0.480 vs 0.477 m).
        for bone in UE5_SPINE + ["neck_02"]:
            if bone in src.index:
                M = np.eye(4)
                M[:3, 3] = tgt[bone] - src.head(bone)
                mats[bone] = M
        # leaves: fingertips reuse their parent's linear part, pinned at their own joint
        for side in ("l", "r"):
            for ue in UE5_FINGERS:
                leaf, par = "%s_03_%s" % (ue, side), "%s_02_%s" % (ue, side)
                if leaf in src.index and par in mats:
                    mats[leaf] = self._pinned(mats[par], src.head(leaf), tgt[leaf])
            leaf, par = "ball_" + side, "foot_" + side
            if toe_tips and side in toe_tips:
                # forefoot: ball -> tip of the shoe onto G2F's toe joint -> toe tip, so a boot made
                # for a raised heel still closes over VaM's flat toes
                f_tip, g_tip = toe_tips[side]
                mats[leaf] = segment_map(src.head(leaf), f_tip, tgt[leaf], g_tip)
            else:
                mats[leaf] = self._pinned(mats[par], src.head(leaf), tgt[leaf])
        # head: the face fit's similarity (the head morph gives G2F the source face at VaM's head
        # size, so the hair must follow the same map) -- or, without a face fit, a scaled ICP of the
        # scalp onto G2F's (hair must sit on VaM's smaller head)
        if head_similarity is not None:
            s, R, t = head_similarity
            M = np.eye(4)
            M[:3, :3] = s * np.asarray(R)
            M[:3, 3] = t
            mats["head"] = M
        elif head_fit is not None:
            s, t = head_fit
            M = np.eye(4)
            M[:3, :3] *= s
            M[:3, 3] = t
            mats["head"] = M
            log("  head fit: scale %.3f, translation %s" % (s, np.round(t, 4)))
        mats["root"] = np.eye(4)
        mats["root"][:3, 3] = tgt["pelvis"] - src.head("pelvis")
        self.mats = mats
        # every bone -> nearest mapped ancestor
        self.bone_map = []
        for i, b in enumerate(src.bones):
            cur = b
            while cur is not None and cur not in mats:
                cur = src.parents[src.index[cur]]
            self.bone_map.append(cur or "root")

    @staticmethod
    def _pinned(parent_M, h_f, h_g):
        M = parent_M.copy()
        M[:3, 3] = h_g - M[:3, :3] @ h_f
        return M

    def deform(self, verts, groups, w_vert, w_group, w_weight):
        """Linear blend of the per-bone maps with the object's own weights."""
        n = len(verts)
        names = [self.bone_map[self.src.index[g]] if g in self.src.index else "root" for g in groups]
        M = np.array([self.mats[m] for m in names])            # per group
        acc = np.zeros((n, 3))
        wsum = np.zeros(n)
        vh = np.concatenate([verts, np.ones((n, 1))], axis=1)
        gm = np.asarray(w_group)
        vv = np.asarray(w_vert)
        ww = np.asarray(w_weight, dtype=np.float64)
        pts = np.einsum("kij,kj->ki", M[gm][:, :3, :], vh[vv])
        np.add.at(acc, vv, pts * ww[:, None])
        np.add.at(wsum, vv, ww)
        out = acc / np.maximum(wsum, 1e-12)[:, None]
        lone = wsum < 1e-9
        if lone.any():
            R = self.mats["root"]
            out[lone] = verts[lone] @ R[:3, :3].T + R[:3, 3]
        return out


# ----------------------------------------------------------------------------- mesh pieces

def select_polys(obj, exclude_names):
    mats = obj["meta"]["materials"]
    keep_mat = np.array([m not in exclude_names for m in mats]) if mats else np.array([True])
    pm = obj["mat"]
    keep = keep_mat[np.clip(pm, 0, len(keep_mat) - 1)]
    return keep


def build_piece(obj, verts_vam, keep_polys):
    """Compact the kept polygons: base polys (tri/quad; n-gons fanned), loop UVs, material ids."""
    ls, lt, lv, uv, pm = obj["loop_start"], obj["loop_total"], obj["loop_vert"], obj["uv"], obj["mat"]
    polys, loops, mats = [], [], []
    for p in np.nonzero(keep_polys)[0].tolist():
        s, n = int(ls[p]), int(lt[p])
        vids = lv[s:s + n].tolist()
        lids = list(range(s, s + n))
        if n in (3, 4):
            polys.append(vids)
            loops.append(lids)
            mats.append(int(pm[p]))
        else:
            for k in range(1, n - 1):
                polys.append([vids[0], vids[k], vids[k + 1]])
                loops.append([lids[0], lids[k], lids[k + 1]])
                mats.append(int(pm[p]))
    used = np.unique(np.concatenate([np.array(p) for p in polys]))
    remap = -np.ones(len(verts_vam), dtype=np.int64)
    remap[used] = np.arange(len(used))
    poly_len = np.array([len(p) for p in polys], dtype=np.int32)
    poly_idx = np.concatenate([remap[np.array(p)] for p in polys]).astype(np.int32)
    loop_uv = np.concatenate([uv[np.array(l)] for l in loops]).astype(np.float32)
    # material ids compacted to the ones actually used
    used_mats = sorted(set(mats))
    mat_remap = {m: i for i, m in enumerate(used_mats)}
    poly_mat = np.array([mat_remap[m] for m in mats], dtype=np.int32)
    return {"verts": verts_vam[used], "orig_index": used, "poly_len": poly_len, "poly_idx": poly_idx,
            "loop_uv": loop_uv, "poly_mat": poly_mat, "src_mats": used_mats}


# ----------------------------------------------------------------------------- textures

def _img(path):
    return Image.open(path)


def material_textures(src_meta, mat_name):
    entry = src_meta["materials"].get(mat_name) or {}
    found = {}
    for im in entry.get("images", []):
        low = (im.get("image") or im.get("label") or "").lower()
        path = im.get("path")
        if not path or not os.path.isfile(path):
            continue
        for key, tokens in (("D", ("_d.", "_bc.", "_basecolor")), ("N", ("_n.", "_na.", "_normal")),
                            ("ORM", ("_orm.", "_arm.")), ("ODI", ("_odi.",)), ("FR", ("_fr.",))):
            if any(t in low for t in tokens) and key not in found:
                found[key] = path
    return found, entry


def convert_material(tex, entry, out_dir, stem, hair=False, max_size=2048):
    """Write VaM-ready textures for one material; returns (texture map, material params)."""
    textures, params = {}, {}
    # the diffuse alpha only means something where the source material used it
    alpha_mode = entry.get("blend_method", "OPAQUE")
    uses_alpha = any("Alpha@" in link for im in entry.get("images", []) for link in im.get("links", []))
    if not uses_alpha:
        alpha_mode = "OPAQUE"

    def save(img, name, mode="RGB"):
        img = img.convert(mode)
        if max(img.size) > max_size:
            img = img.resize((max_size, max_size), Image.LANCZOS)
        path = os.path.join(out_dir, name)
        img.save(path)
        return name

    if hair:
        ramp = (entry.get("ramps") or [[]])[0]
        stops = sorted([(float(p), np.array(c[:3], dtype=np.float64)) for p, c in ramp]) or \
            [(0.0, np.array([0.2, 0.14, 0.09])), (1.0, np.array([0.19, 0.13, 0.1]))]
        fr = np.asarray(_img(tex["FR"]).convert("RGB"), dtype=np.float64)[..., 2] / 255.0 if "FR" in tex else None
        odi = np.asarray(_img(tex["ODI"]).convert("RGB"), dtype=np.float64) / 255.0 if "ODI" in tex else None
        size = (fr if fr is not None else odi[..., 0]).shape
        fac = fr if fr is not None else np.full(size, 0.5)
        pos = np.array([p for p, _ in stops])
        cols = np.array([c for _, c in stops])
        lin = np.stack([np.interp(fac, pos, cols[:, k]) for k in range(3)], axis=-1)   # linear colour
        srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)
        # a little strand shading from the ODI depth/id channels keeps the cards from looking flat
        if odi is not None:
            shade = 0.9 + 0.1 * odi[..., 1]
            srgb = srgb * shade[..., None]
            alpha = odi[..., 0]
        else:
            alpha = np.ones(size)
        rgba = np.concatenate([np.clip(srgb, 0, 1), alpha[..., None]], axis=-1)
        textures["customTexture_MainTex"] = save(Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA"), stem + "_D.png", "RGBA")
        textures["customTexture_AlphaTex"] = save(Image.fromarray((alpha * 255 + 0.5).astype(np.uint8), "L"), stem + "_A.png", "L")
        params.update({"Specular Intensity": 0.6, "Gloss": 4.5, "Specular Fresnel": 0.5, "renderQueue": 2450,
                       "Diffuse Bumpiness": 0, "Specular Bumpiness": 0})
        return textures, params

    if "D" in tex:
        d = _img(tex["D"])
        rgb = np.asarray(d.convert("RGB"), dtype=np.float64) / 255.0
        if "ORM" in tex:
            orm = np.asarray(_img(tex["ORM"]).convert("RGB").resize(d.size, Image.BILINEAR), dtype=np.float64) / 255.0
            ao, rough, metal = orm[..., 0], orm[..., 1], orm[..., 2]
            # metal-workflow -> VaM's diffuse/specular: metals keep less diffuse, their colour moves
            # into the specular map; AO darkens the diffuse
            # VaM has no environment reflections, so a metal that gives its albedo away to the
            # specular map renders black: keep most of the albedo (silver stays silver)
            diff = rgb * (1.0 - 0.35 * metal[..., None]) * (0.6 + 0.4 * ao[..., None])
            spec = (0.25 + 0.75 * metal)[..., None] * (1 - metal[..., None] + metal[..., None] * rgb)
            gloss = np.clip(1.0 - rough, 0, 1)
            textures["customTexture_SpecTex"] = save(Image.fromarray((np.clip(spec, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB"), stem + "_S.png")
            textures["customTexture_GlossTex"] = save(Image.fromarray((gloss * 255 + 0.5).astype(np.uint8), "L"), stem + "_G.png", "L")
            params.update({"Specular Intensity": 2.0, "Gloss": 7.0, "Specular Fresnel": 0.4})
        else:
            diff = rgb
            params.update({"Specular Intensity": 0.8, "Gloss": 4.0})
        textures["customTexture_MainTex"] = save(Image.fromarray((np.clip(diff, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB"), stem + "_D.png")
        if d.mode == "RGBA" and alpha_mode in ("CLIP", "HASHED", "BLEND"):
            a = np.asarray(d, dtype=np.uint8)[..., 3]
            if alpha_mode == "CLIP":
                a = np.where(a >= 128, 255, 0).astype(np.uint8)      # alpha test, not blending
            if a.min() < 250:
                textures["customTexture_AlphaTex"] = save(Image.fromarray(a, "L"), stem + "_A.png", "L")
    if "N" in tex:
        n = np.asarray(_img(tex["N"]).convert("RGB"), dtype=np.uint8).copy()
        n[..., 1] = 255 - n[..., 1]                  # UE (DirectX) -> Unity (OpenGL)
        textures["customTexture_BumpMap"] = save(Image.fromarray(n, "RGB"), stem + "_N.png")
    return textures, params


# ----------------------------------------------------------------------------- items

def safe(text):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in text).strip()


def mesh_edges(poly_len, poly_idx, count):
    """Both directions of every polygon edge, and the vertex degrees."""
    poly_len = np.asarray(poly_len)
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    a_list, b_list = [], []
    for n in (3, 4):
        sel = np.nonzero(poly_len == n)[0]
        if not len(sel):
            continue
        q = np.asarray(poly_idx)[starts[sel][:, None] + np.arange(n)[None, :]]
        a_list.append(q.ravel())
        b_list.append(np.roll(q, -1, axis=1).ravel())
    a = np.concatenate(a_list).astype(np.int64)
    b = np.concatenate(b_list).astype(np.int64)
    ea, eb = np.concatenate([a, b]), np.concatenate([b, a])
    return ea, eb, np.bincount(ea, minlength=count).astype(np.float64)


def signed_distance(points, verts, hint_normals, tris):
    """Signed distance of points to a skin (closest triangle, outward positive) + that triangle."""
    idx = vi.closest_triangles(points, tris, verts)
    tv = tris[idx]
    a, n, _t1, _t2 = vi.wrap_frames(tv, verts, hint_normals)
    d2 = vi._point_triangle_distance2(points, a, verts[tv[:, 1]], verts[tv[:, 2]])
    plane = np.einsum("ij,ij->i", points - a, n)
    return np.where(plane >= 0, 1.0, -1.0) * np.sqrt(d2), tv


# How far each part of the G2F body may be pulled in for the rest shape.  Thin parts get little
# room: shrinking a finger or a toe past its own thickness turns its triangles inside out, the
# signed distances flip and the fit runs away (it did, to the 7 cm cap everywhere).
G2F_SEGMENTS = [
    # (name, from joint, to joint, cap in metres, share of the local radius)
    ("head", "head", None, 0.020, 0.45), ("neck", "neck", "head", 0.030, 0.45),
    ("chest", "chest", "neck", 0.100, 0.60), ("belly", "abdomen2", "chest", 0.060, 0.60),
    ("hips", "hip", "abdomen2", 0.060, 0.60),
] + [(n + s, s + a, s + b if b else None, cap, frac) for s in ("l", "r") for n, a, b, cap, frac in (
    ("thigh", "Thigh", "Shin", 0.040, 0.45), ("shin", "Shin", "Foot", 0.030, 0.45),
    ("foot", "Foot", "Toe", 0.012, 0.40), ("toes", "Toe", None, 0.005, 0.40),
    ("collar", "Collar", "Shldr", 0.030, 0.45), ("upperarm", "Shldr", "ForeArm", 0.030, 0.45),
    ("forearm", "ForeArm", "Hand", 0.020, 0.45), ("hand", "Hand", "Mid1", 0.006, 0.40),
    ("thumb", "Thumb1", "Thumb3", 0.003, 0.35), ("index", "Index1", "Index3", 0.003, 0.35),
    ("middle", "Mid1", "Mid3", 0.003, 0.35), ("ring", "Ring1", "Ring3", 0.003, 0.35),
    ("pinky", "Pinky1", "Pinky3", 0.003, 0.35))]


# Skin material -> (cap, share of the radius, body segments whose axis gives that radius).
# Classifying by the nearest segment put the top of the breasts on the collar-bone axis (3 cm
# cap) and the breastplate stayed pierced; the skin materials say which part a vertex is on.
G2F_MATERIAL_CLASSES = [
    (("Torso", "Nipples"), 0.100, 0.60, ("hips", "belly", "chest")),
    (("Hips", "defaultMat", "Hidden"), 0.060, 0.60, ("hips", "belly", "thighl", "thighr")),
    (("Neck",), 0.030, 0.45, ("neck", "chest")),
    (("Head", "Face", "Lips", "Nostrils"), 0.020, 0.45, ("head", "neck")),
    # hair crossing an ear is normal; an ear pulled in 2 cm under it crumples (135 triangles
    # turned over) and shows
    (("Ears",), 0.003, 0.20, ("head",)),
    (("Shoulders",), 0.030, 0.45, ("collarl", "collarr", "upperarml", "upperarmr")),
    (("Forearms",), 0.020, 0.45, ("forearml", "forearmr", "upperarml", "upperarmr")),
    (("Hands",), 0.006, 0.40, tuple("%s%s" % (n, s) for s in "lr" for n in ("hand", "thumb", "index", "middle", "ring", "pinky"))),
    (("Fingernails",), 0.002, 0.30, tuple("%s%s" % (n, s) for s in "lr" for n in ("thumb", "index", "middle", "ring", "pinky"))),
    (("Legs",), 0.040, 0.45, ("thighl", "thighr", "shinl", "shinr")),
    (("Feet",), 0.012, 0.40, ("footl", "footr", "toesl", "toesr", "shinl", "shinr")),
    (("Toenails",), 0.004, 0.30, ("toesl", "toesr")),
]


# body skin that must also clear the garments from its own side (see rest_body)
SKIN_SIDE_MATERIALS = ("Torso", "Nipples", "Hips", "Neck", "Shoulders", "Legs", "Forearms")


def g2f_shrink_caps(g2f):
    """Per skin vertex: how far it may be pulled in -- its body part's cap, and never more than a
    share of its distance from that part's bone axis (an ankle 3 cm thick must not be shrunk
    3 cm: its triangles turn inside out and the wrap frames with them).  Eyes, teeth, mouth,
    lashes: nothing."""
    pts = g2f.verts
    segs = {}
    for name, a, b, _c, _f in G2F_SEGMENTS:
        pa = g2f.j(a)
        pb = g2f.j(b) if b else (pa + (pa - g2f.j(g2f_parent(a))) * 0.6 if g2f_parent(a) else pa)
        segs[name] = (pa, pb)

    def radius(names, idx):
        best = np.full(len(idx), np.inf)
        p = pts[idx]
        for n in names:
            pa, pb = segs[n]
            ab = pb - pa
            t = np.clip(((p - pa) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            best = np.minimum(best, np.linalg.norm(p - (pa + t[:, None] * ab), axis=1))
        return best

    names = g2f.meta["materialNames"]
    starts = np.concatenate([[0], np.cumsum(g2f.poly_len)[:-1]])
    cap = np.full(len(pts), np.inf)
    for mats, c, frac, seg_names in G2F_MATERIAL_CLASSES:
        ids = [names.index(m) for m in mats if m in names]
        polys = np.nonzero(np.isin(g2f.poly_mat, ids))[0]
        if not len(polys):
            continue
        vids = np.unique(np.concatenate([g2f.poly_idx[starts[p]:starts[p] + g2f.poly_len[p]] for p in polys]))
        cap[vids] = np.minimum(cap[vids], np.minimum(c, frac * radius(seg_names, vids)))
    cap[~np.isfinite(cap)] = 0.0
    cap[21556:] = 0.0          # the genital graft: a female body morph cannot move it
    return cap


def g2f_parent(joint):
    return {"head": "neck", "lToe": "lFoot", "rToe": "rFoot"}.get(joint)


def rest_body(g2f, pieces, start=None, log=print, rounds=10, smooth=20, damping=0.5):
    """The G2F body the items are wrapped against: the base shape pulled inward, smoothly, wherever a
    garment comes closer to it than that garment's clearance.

    VaM rebuilds every garment vertex at its stored offset from its skin triangle on the body it is
    worn on.  Measuring the offsets against a body shrunk to clear the garment means that on the
    real (bigger-chested, wider-hipped) G2F the garment is pushed out by exactly the difference --
    a smooth field over the body -- instead of cutting into it, and the garment itself is never
    bent here.  (Pushing the garment's own vertices out instead dented rigid plates, still let the
    skin show through big triangles and flared the skirt plates.)  ``start`` is the shape it is
    pulled in from (G2F with the head morph on); the returned shape minus ``start`` is the body
    morph.
    """
    base = g2f.verts if start is None else start
    normals = g2f.normals if start is None else \
        vl.outward_normals(base.astype(np.float32), g2f.poly_len, g2f.poly_idx).astype(np.float64)
    tris = vi.vam_triangles(g2f.poly_len, g2f.poly_idx, g2f.poly_mat)
    ea, eb, deg = mesh_edges(g2f.poly_len, g2f.poly_idx, len(base))
    cap = g2f_shrink_caps(g2f)
    # The skin moves in along a smoothed normal field (~5 cm), not its own normals, which point
    # sideways on the flanks of a small bump: along the smoothed field a bump moves back whole.
    direction = normals.copy()
    for _ in range(40):
        acc = np.zeros_like(direction)
        np.add.at(acc, ea, direction[eb])
        direction = 0.5 * direction + 0.5 * acc / np.maximum(deg, 1)[:, None]
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    pts = np.concatenate([np.concatenate([p["verts"], p["samples"]]) for p in pieces])
    clear = np.concatenate([np.full(len(p["verts"]) + len(p["samples"]), p["clearance"]) for p in pieces])
    # Skin side.  A garment point only pushes the skin triangle it is anchored to, so a small
    # bump beside that triangle got nothing but the smoothing's spill-over: the areola next to
    # the (65 mm pulled-in) nipple tip moved 15 mm and stayed 17 mm in front of the breastplate.
    # So every body-skin vertex must also lie its clearance behind the nearest solid garment
    # point (along the smoothed normal) -- on the big, smooth parts only: hands and feet have
    # mm-sized caps and folds of their own (the rule turned 4x as many foot triangles over), and
    # the garment side already fits them.  Not against hair (thin, see-through, its roots sit in
    # the scalp on purpose) and not for the face / head skin (the head morph owns that).
    solid = [p for p in pieces if not p["spec"].get("hair")]
    gpts = np.concatenate([np.concatenate([p["verts"], p["samples"]]) for p in solid])
    gclear = np.concatenate([np.full(len(p["verts"]) + len(p["samples"]), p["clearance"]) for p in solid])
    ggrid = vi._Grid(gpts, np.zeros((0, 3), dtype=np.int64), 0.02)
    names = g2f.meta["materialNames"]
    side_ids = [names.index(m) for m in SKIN_SIDE_MATERIALS if m in names]
    other_ids = [i for i in range(len(names)) if i not in side_ids]
    starts = np.concatenate([[0], np.cumsum(g2f.poly_len)[:-1]])

    def verts_of(ids):
        return np.unique(np.concatenate([g2f.poly_idx[st:st + n] for st, n, m in
                                         zip(starts, g2f.poly_len, g2f.poly_mat) if m in ids]))

    # vertices on a seam with an excluded part (wrist, ankle, jaw line) stay with that part
    skin_ids = np.setdiff1d(np.intersect1d(verts_of(side_ids), np.nonzero(cap > 0)[0]), verts_of(other_ids))
    # the body only moves inward, so points already clear of the base body stay clear
    dist, tv = signed_distance(pts, base, normals, tris)
    live = dist < clear + 2e-4
    pts, clear, tv = pts[live], clear[live], tv[live]
    # every point stays anchored to the skin it covers on the BASE body: re-picking the closest
    # triangle on the shrinking body let a breastplate point hop from the (deeply pulled-in)
    # breast apex to the barely moved slope above it, and the apex kept poking through
    shrink = np.zeros(len(base))
    for rnd in range(rounds):
        cur = base - direction * shrink[:, None]
        a, n, _t1, _t2 = vi.wrap_frames(tv, cur, normals)
        dist = np.einsum("ij,ij->i", pts - a, n)
        need = clear - dist
        bad = need > 2e-4
        near = ggrid.near_vertices(cur[skin_ids], k=1)[:, 0]
        has = near >= 0
        sk, gq = skin_ids[has], near[has]
        close = np.linalg.norm(gpts[gq] - cur[sk], axis=1) < 0.03
        sk, gq = sk[close], gq[close]
        depth = np.einsum("ij,ij->i", gpts[gq] - cur[sk], direction[sk])
        need_s = gclear[gq] - depth
        bad_s = need_s > 2e-4
        log("    rest body round %d: %d garment points too close (worst %.1f mm), %d skin vertices not behind the garment (worst %.1f mm)"
            % (rnd + 1, int(bad.sum()), 1000 * float(need.max()) if len(need) else 0.0,
               int(bad_s.sum()), 1000 * float(need_s.max()) if len(need_s) else 0.0))
        if not bad.any() and not bad_s.any():
            break
        req = np.zeros(len(base))
        np.maximum.at(req, tv[bad].ravel(), np.repeat(need[bad] + 2e-4, 3))
        np.maximum.at(req, sk[bad_s], need_s[bad_s] + 2e-4)
        req = np.minimum(req, np.maximum(cap - shrink, 0))
        add = req.copy()
        for _ in range(smooth):
            acc = np.zeros(len(base))
            np.add.at(acc, ea, add[eb])
            add = np.maximum(damping * acc / np.maximum(deg, 1) + (1 - damping) * add, req)
        new = np.minimum(shrink + add, cap)
        if np.max(new - shrink) < 1e-5:
            log("    rest body: the rest are beyond the per-part caps")
            break
        shrink = new
    log("    rest body: %d skin vertices pulled in (p95 %.1f mm, max %.1f mm)"
        % (int(np.sum(shrink > 1e-4)), 1000 * float(np.percentile(shrink[shrink > 1e-4], 95)) if np.any(shrink > 1e-4) else 0,
           1000 * float(shrink.max())))
    return base - direction * shrink[:, None], shrink


def prepare_piece(spec, src, rt):
    obj = src.obj(spec["object"])
    keep = select_polys(obj, set(spec.get("exclude", [])))
    moved = rt.deform(obj["verts"], obj["meta"]["groups"], obj["w_vert"], obj["w_group"], obj["w_weight"])
    piece = build_piece(obj, moved, keep)
    piece["obj"] = obj
    piece["spec"] = spec
    piece["clearance"] = float(spec.get("clearance", 0.003))
    piece["samples"] = triangle_samples(piece["verts"], piece["poly_len"], piece["poly_idx"])
    return piece


def triangle_samples(verts, poly_len, poly_idx, small=0.006, large=0.015):
    """Points inside the garment's bigger triangles.  A flat plate spanning a curved body can
    have every vertex clear of the skin while the skin still pokes through the middle of the
    triangle (the breastplate did), so the rest body is fitted against these too."""
    poly_len = np.asarray(poly_len)
    starts = np.concatenate([[0], np.cumsum(poly_len)[:-1]])
    tris = []
    for n in (3, 4):
        sel = np.nonzero(poly_len == n)[0]
        q = np.asarray(poly_idx)[starts[sel][:, None] + np.arange(n)[None, :]]
        tris.append(q[:, [0, 1, 2]])
        if n == 4:
            tris.append(q[:, [0, 2, 3]])
    tris = np.concatenate(tris)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    edge = np.max([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], axis=0)
    out = [(a + b + c)[edge > small] / 3.0]
    big = edge > large
    for w in ((0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
        out.append((a * w[0] + b * w[1] + c * w[2])[big])
    return np.concatenate(out)


def build_item(profile, piece, rest_verts, src, g2f, out_root, anchor=None, log=print):
    spec, obj = piece["spec"], piece["obj"]
    hair = spec.get("hair", False)
    verts = piece["verts"]
    normals = vl.outward_normals(verts.astype(np.float32), piece["poly_len"], piece["poly_idx"]).astype(np.float64)
    uvs, uv_poly_idx, mapped, uv_to_base = vi.split_uv_vertices(len(verts), piece["poly_len"], piece["poly_idx"], piece["loop_uv"])
    # The records are measured against the rest body -- the G2F shape the "<name> Body" morph
    # produces -- anchored to the skin each vertex covers on the base body.  With the morph on
    # (the preset sets it), VaM rebuilds the item exactly as authored; with it off, VaM's own
    # wrap pushes the item out over the bigger base body.  ``anchor`` is the shape the rest body
    # was pulled in from (base + head morph).  The frames are measured with the rest body's own
    # normals (VaM orients them on the body as it is), on triangles whose orientation no morph
    # state here can flip.
    start = g2f.verts if anchor is None else anchor
    tris = vi.vam_triangles(g2f.poly_len, g2f.poly_idx, g2f.poly_mat)
    usable = vi.stable_triangles(tris, [g2f.verts, start, rest_verts], g2f.poly_len, g2f.poly_idx)
    rest_normals = vl.outward_normals(rest_verts.astype(np.float32), g2f.poly_len, g2f.poly_idx).astype(np.float64)
    tri, tv, coeffs, ncoeffs = vi.compute_wrap(verts, normals, rest_verts, g2f.poly_len, g2f.poly_idx,
                                               g2f.poly_mat, rest_normals, anchor_verts=start, usable=usable)
    records = vi.pack_records(tri[uv_to_base], tv[uv_to_base], coeffs[uv_to_base], ncoeffs[uv_to_base])
    placed = verts
    rebuilt = vl.wrap_to_body(tv, coeffs, rest_verts, rest_normals)
    rebuild_mm = np.linalg.norm(rebuilt - verts, axis=1) * 1000         # must be ~0 (float32)
    on_base = vl.wrap_to_body(tv, coeffs, g2f.verts, g2f.normals)
    moved_mm = np.linalg.norm(on_base - verts, axis=1) * 1000          # morph off
    a, n, _t1, _t2 = vi.wrap_frames(tv, rest_verts, rest_normals)
    after = np.einsum("ij,ij->i", verts - a, n)                         # clearance on the rest body
    display = spec["display"]
    item_type = spec.get("type", "ClothingFemale")
    kind_dir = "Hair" if item_type.startswith("Hair") else "Clothing"
    out_dir = os.path.join(out_root, "Custom", kind_dir, "Female", profile["creator"], display)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    mat_names = [safe(obj["meta"]["materials"][m] or "mat%d" % m) for m in piece["src_mats"]]
    groups, params = [], {}
    for i, (name, src_mat) in enumerate(zip(mat_names, piece["src_mats"])):
        tex, entry = material_textures(src.meta, obj["meta"]["materials"][src_mat])
        textures, p = convert_material(tex, entry, out_dir, safe(display).replace(" ", "_") + "_" + name, hair=hair)
        groups.append((name, [i]))
        params[name] = dict(textures=textures, **p)
    mesh = {"name": safe(display), "ids": [safe(display) + "-2", safe(display) + "-1", safe(display) + "-3"],
            "verts": placed.astype(np.float32), "materials": mat_names, "poly_mat": piece["poly_mat"],
            "poly_len": piece["poly_len"], "poly_idx": piece["poly_idx"], "uv_poly_idx": uv_poly_idx,
            "uvs": uvs, "mapped": mapped}
    info = vi.write_item(out_dir, profile["creator"], display, item_type, mesh, records, groups, params,
                         tags=spec.get("tags", ""), disable_anatomy=spec.get("disable_anatomy", False))
    stats = {"display": display, "verts": int(len(verts)), "polys": int(len(piece["poly_len"])),
             "uv_verts": int(len(uvs)), "materials": mat_names, "dir": out_dir,
             "rebuild_max_mm": float(rebuild_mm.max()),
             "moved_share": float(np.mean(moved_mm > 0.5)), "moved_p95_mm": float(np.percentile(moved_mm, 95)),
             "moved_max_mm": float(moved_mm.max()), "inside_on_base": int(np.sum(after < 0)),
             "wrap_coeff_p50": float(np.median(np.abs(coeffs[:, 1:3]).max(axis=1))), **info}
    log("  %-24s %6d verts %6d polys  inside the morphed body: %d  rebuild max %.4f mm  (morph off: moved p95 %.1f mm)"
        % (display, stats["verts"], stats["polys"], stats["inside_on_base"], stats["rebuild_max_mm"],
           stats["moved_p95_mm"]))
    return stats


def head_fit(src, g2f, face_object="Fiona_Face", skin_material="MI_Fiona_Face01_"):
    """Scale + translation carrying the source skull onto G2F's (above the brows)."""
    obj = src.obj(face_object)
    mats = obj["meta"]["materials"]
    skin = mats.index(skin_material)
    polys = np.nonzero(obj["mat"] == skin)[0]
    ls, lt, lv = obj["loop_start"], obj["loop_total"], obj["loop_vert"]
    vids = np.unique(np.concatenate([lv[ls[p]:ls[p] + lt[p]] for p in polys]))
    pts = obj["verts"][vids]
    eye_f = src.head("head")[1] + 0.07          # a bit above the eyes
    eye_g = g2f.j("lEye")[1] + 0.015
    sp = pts[pts[:, 1] > eye_f]
    gp = g2f.verts[:21556][g2f.verts[:21556, 1] > eye_g]
    s, t = scaled_icp(sp, gp)
    return s, t


def toe_tips(src, g2f, shoe_object, margin=0.012):
    """Per side: (front tip of the source shoe near the sole, G2F's toe tip pushed out by the
    toe-cap thickness).  The forefoot is mapped along ball -> tip (see Retarget)."""
    shoe = src.obj(shoe_object)["verts"]
    out = {}
    for side, sign in (("l", -1.0), ("r", 1.0)):
        s = shoe[(shoe[:, 0] * sign) > 0.02]
        low = s[s[:, 1] < s[:, 1].min() + 0.05]
        f_tip = low[np.argmax(low[:, 2])]
        body = g2f.verts[:21556]
        foot = body[((body[:, 0] * sign) > 0.03) & (body[:, 1] < 0.05)]
        g = foot[np.argmax(foot[:, 2])].copy()
        g[2] += margin
        out[side] = (f_tip, g)
    return out


def character_textures(character):
    """{"region|kind": png} of a VaM character's default skin (``_cache/textures/<bundle>``,
    exported from the game bundles on first use)."""
    cache = vl.VamCache(CACHE, vl.AssetStudio(vl.default_assetstudio(), VAM_ROOT))
    chars = cache.characters()
    info = chars.get(character)
    if info is None:
        raise SystemExit("unknown VaM character %r (have: %s)" % (character, ", ".join(sorted(chars))))
    table = cache.skin_textures(info["bundle"], "m_c" if info.get("isMale") else "f_c")
    out = {"|".join(k): v for k, v in table.items()}
    out["index"] = os.path.join(CACHE, "textures", info["bundle"], "index.json")
    return out


def build_face(profile, src, g2f, out_root, log=print):
    """Head morph + face texture + iris texture for a profile's ``face`` entry.

    Returns the head deltas, the source -> G2F similarity (for the hair), the morph files and
    the preset storables (textures, irises, lashes)."""
    face = profile["face"]
    log("  face: fitting G2F's head to %s ..." % face["object"])
    fitted, (s, R, t), report = ff.fit_head(g2f, src, face["object"], face["skin"], face["eyes"],
                                            log=log)
    delta = fitted - g2f.verts
    base_tex = character_textures(profile["character"])
    tex_dir = os.path.join(out_root, "Custom", "Atom", "Person", "Textures", profile["creator"], profile["name"])
    os.makedirs(tex_dir, exist_ok=True)
    obj = src.obj(face["object"])
    src_g2f = obj["verts"] @ np.asarray(R).T * s + t
    size = int(face.get("texture_size", 2048))
    skin_tex, _entry = material_textures(src.meta, face["skin"])
    log("  face: baking %s onto G2F's face UVs (%d px) ..." % (os.path.basename(skin_tex["D"]), size))
    img, mask, pos = ff.bake_face_texture(fitted, g2f, ("Face", "Lips", "Nostrils"), src_g2f, obj, face["skin"],
                                          skin_tex["D"], size=size, log=log)
    ref = np.asarray(Image.open(base_tex["face|diffuse"]).convert("RGB").resize((size, size), Image.LANCZOS),
                     dtype=np.float64)
    glm, _ = ff.g2f_landmarks(fitted, g2f.poly_len, g2f.poly_idx, g2f.poly_mat, g2f.meta["materialNames"])
    eye_y = 0.5 * (glm["eye_l"][1] + glm["eye_r"][1])
    eye_x = 0.5 * (abs(glm["eye_out_l"][0]) + abs(glm["eye_out_r"][0]))
    # painted-on hair base at the hairline -> the base character's skin (hair gaps show scalp)
    img, paint = ff.replace_dark_paint(img, mask, pos, ref, above_y=eye_y + 0.012, lateral_x=eye_x + 0.008,
                                       below_y=eye_y - 0.035)
    log("    scalp paint replaced on %.1f%% of the face texture" % (100 * float(np.mean(paint > 0.5))))
    # the face meets the base character's torso texture (neck, ears, scalp) at the UV seams
    img, _w = ff.match_to_reference(img, mask, ref, band=int(0.05 * size), blur=max(2, int(0.008 * size)),
                                    strength_inside=0.3)
    if face.get("brows"):
        brow_tex, brow_entry = material_textures(src.meta, face["brows"])
        colour = brow_entry.get("bsdf", {}).get("Base Color", [0.05, 0.03, 0.02, 1])[:3]
        img, _cover = ff.bake_strands(img, fitted, g2f, ("Face",), src_g2f, obj, face["brows"], brow_tex["ODI"],
                                      ff.linear_to_srgb(colour) * 255, size, log=log)
    img, _m = ff.dilate(img, mask, 24)
    face_png = os.path.join(tex_dir, "%s Face D.png" % profile["name"])
    Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).save(face_png)
    rel = lambda p: os.path.relpath(p, out_root).replace("\\", "/")  # noqa: E731
    storables = [{"id": "textures", "faceDiffuseUrl": rel(face_png)}]
    eye_bake = src.meta["materials"].get(face["eyes"], {}).get("baked_base_color")
    if eye_bake and os.path.isfile(eye_bake) and base_tex.get("eyes|diffuse"):
        eyes_png = ff.transplant_iris(base_tex["eyes|diffuse"], eye_bake,
                                      os.path.join(tex_dir, "%s Eyes D.png" % profile["name"]), log=log)
        storables.append({"id": "irises", "customTexture_MainTex": rel(eyes_png),
                          "Diffuse Color": {"h": "0", "s": "0", "v": "1"}})
    else:
        log("    no baked eye texture (dump with --bake %s): VaM's default irises stay" % face["eyes"])
    if face.get("lashes_hsv"):
        h, sat, v = face["lashes_hsv"]
        storables.append({"id": "FemaleEyelashes", "Diffuse Color": {"h": str(h), "s": str(sat), "v": str(v)}})
    return {"delta": delta, "similarity": (s, R, t), "report": report, "storables": storables,
            "formulas": ff.eye_formulas(report["eye_shift"]), "face_png": face_png,
            "eyes_png": os.path.join(tex_dir, "%s Eyes D.png" % profile["name"]), "skin_index": base_tex["index"]}


def verify_items(items, morph_files, g2f, log=print):
    """Rebuild every written item from its own .vab on G2F + the written .vmb morphs, the way VaM
    does (frame normals oriented on that body), and compare with the vertices stored in the
    .vab: all should sit at VaM's surfaceOffset (0.3 mm) from where they were authored."""
    body = g2f.verts.copy()
    for path in morph_files:
        idx, delta = vl.parse_vmb(open(path, "rb").read())
        body[idx] += delta
    normals = vl.outward_normals(body.astype(np.float32), g2f.poly_len, g2f.poly_idx)
    worst = 0.0
    for it in items:
        stem = os.path.splitext(it["vam"])[0]
        vaj = vl.lenient_json_loads(open(stem + ".vaj", encoding="utf-8").read())
        mesh = vl.parse_dazmesh_vab(open(stem + ".vab", "rb").read())
        tris, coeffs = mesh.wrap
        offset = vl.wrap_surface_offset(vaj)
        placed = vl.wrap_to_body(tris, coeffs, body, normals, offset)
        err = np.linalg.norm(placed - np.asarray(mesh.verts, dtype=np.float64), axis=1) - offset
        err = np.abs(err) * 1000
        it["verify_max_mm"] = float(err.max())
        worst = max(worst, float(err.max()))
        log("  verify %-24s rebuilt on base + morphs: max %.3f mm off (beyond the %.1f mm surface offset)"
            % (it["display"], err.max(), offset * 1000))
    if worst > 1.0:
        log("  WARNING: an item does not rebuild where it was authored")
    return worst


def render_thumbnails(work, items, preset, morph_files, face=None, blender=BLENDER, log=print):
    """Blender preview of the result the way VaM rebuilds it (items from their .vab wraps, the
    morphs, the preset's face / eye textures): <work>/_preview/*.png, every item's <item>.jpg
    (VaM's browser thumbnail) and the preset's .jpg."""
    listing = os.path.join(work, "_items.txt")
    with open(listing, "w", encoding="utf-8") as f:
        f.write("\n".join(it["vam"] for it in items))
    cmd = [blender, "-b", "--factory-startup", "-P",
           os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_preview_items.py"), "--",
           "--out", os.path.join(work, "_preview"), "--thumbs", "--closeups", "--list", listing]
    for m in morph_files:
        cmd += ["--morph", m]
    if face:
        cmd += ["--skin", face["skin_index"], "--face", face["face_png"], "--face-closeups"]
        if os.path.isfile(face["eyes_png"]):
            cmd += ["--irises", face["eyes_png"]]
    log("  rendering previews and thumbnails in Blender ...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "PREVIEW_DONE" not in res.stdout:
        log(res.stdout[-3000:] + res.stderr[-3000:])
        raise SystemExit("Blender preview failed")
    for it in items:
        png = os.path.splitext(it["vam"])[0] + "_thumb.png"
        if os.path.isfile(png):
            Image.open(png).convert("RGB").save(os.path.splitext(it["vam"])[0] + ".jpg", quality=90)
            os.remove(png)
    head = os.path.join(work, "_preview", "preview_head.png")
    if os.path.isfile(head):
        Image.open(head).convert("RGB").resize((512, 512), Image.LANCZOS).save(
            os.path.splitext(preset)[0] + ".jpg", quality=90)
    log("  previews: %s" % os.path.join(work, "_preview"))


def write_preset(profile, items, out_root, morphs=(), storables=()):
    path = os.path.join(out_root, "Custom", "Atom", "Person", "Appearance", profile["creator"],
                        "Preset_%s.vap" % profile["name"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    clothing = [{"id": "Tank Top", "enabled": "false"}, {"id": "Shorts", "enabled": "false"}]
    hair = [{"id": "SimV2 Hair", "enabled": "false"}]
    for it in items:
        rel = os.path.relpath(it["vam"], out_root).replace("\\", "/")
        entry = {"id": rel, "internalId": it["uid"], "enabled": "true"}
        (hair if "/Hair/" in rel else clothing).append(entry)
    geometry = {"id": "geometry", "useAdvancedColliders": "true", "useAuxBreastColliders": "true",
                "disableAnatomy": "false", "useMaleMorphsOnFemale": "false", "useFemaleMorphsOnMale": "false",
                "character": profile["character"], "clothing": clothing, "hair": hair, "morphs": list(morphs)}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"setUnlistedParamsToDefault": "true", "storables": [geometry] + list(storables)}, f,
                  ensure_ascii=False, indent=3)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="fiona_df", choices=sorted(PROFILES))
    ap.add_argument("--install", action="store_true", help="also copy into the VaM folder")
    ap.add_argument("--vam", default=VAM_ROOT)
    ap.add_argument("--no-thumbs", action="store_true", help="skip the Blender preview / thumbnails")
    ap.add_argument("--blender", default=BLENDER)
    args = ap.parse_args()
    profile = PROFILES[args.profile]
    work = profile["work"]
    src = Source(os.path.join(work, "_src"), profile["unit"])
    g2f = G2F()
    print("fitting %s onto G2F ..." % profile["name"])
    out_root = os.path.join(work, "vam")
    morph_dir = os.path.join(out_root, "Custom", "Atom", "Person", "Morphs", "female", profile["creator"])
    if os.path.isdir(morph_dir):
        shutil.rmtree(morph_dir)
    morphs, storables = [], []
    start = g2f.verts
    face = None
    if profile.get("face"):
        face = build_face(profile, src, g2f, out_root)
        start = g2f.verts + face["delta"]
        head_name = profile["name"] + " Head"
        head = vi.write_morph(morph_dir, head_name, face["delta"], group=profile["creator"],
                              region=profile["creator"], formulas=face["formulas"])
        print("  morph %s: %d vertices moved" % (head_name, head["deltas"]))
        morphs.append({"uid": os.path.relpath(head["vmi"], out_root).replace("\\", "/"), "name": head_name, "value": "1"})
        storables += face["storables"]
    shoe = profile.get("shoe_object")
    rt = Retarget(src, g2f, head_fit=None if face else head_fit(src, g2f),
                  head_similarity=face["similarity"] if face else None,
                  toe_tips=toe_tips(src, g2f, shoe) if shoe else None)
    pieces = [prepare_piece(spec, src, rt) for spec in profile["items"]]
    print("  rest body (G2F pulled in where the items come too close) ...")
    rest, shrink = rest_body(g2f, pieces, start=start)
    np.save(os.path.join(work, "rest_shrink.npy"), shrink)
    body_name = profile["name"] + " Body"
    morph = vi.write_morph(morph_dir, body_name, rest - start, group=profile["creator"],
                           region=profile["creator"])
    print("  morph %s: %d vertices moved" % (body_name, morph["deltas"]))
    items = [build_item(profile, piece, rest, src, g2f, out_root, anchor=start) for piece in pieces]
    morphs.insert(0, {"uid": os.path.relpath(morph["vmi"], out_root).replace("\\", "/"), "name": body_name, "value": "1"})
    preset = write_preset(profile, items, out_root, morphs=morphs, storables=storables)
    vmbs = [os.path.join(out_root, m["uid"][:-4] + ".vmb") for m in morphs]
    verify_items(items, vmbs, g2f)
    if not args.no_thumbs:
        render_thumbnails(work, items, preset, vmbs, face, blender=args.blender)
    with open(os.path.join(work, "items.json"), "w", encoding="utf-8") as f:
        json.dump({"items": items, "preset": preset}, f, ensure_ascii=False, indent=1)
    print("preset:", preset)
    if args.install:
        for sub in ("Custom",):
            for dirpath, _d, files in os.walk(os.path.join(out_root, sub)):
                rel = os.path.relpath(dirpath, out_root)
                dst = os.path.join(args.vam, rel)
                os.makedirs(dst, exist_ok=True)
                for fn in files:
                    shutil.copy2(os.path.join(dirpath, fn), os.path.join(dst, fn))
        print("installed into", args.vam)
    return 0


if __name__ == "__main__":
    sys.exit(main())
