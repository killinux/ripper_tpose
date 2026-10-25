"""Bake AION2 character materials into plain PBR textures (system Python: numpy + Pillow).

AION2's character shaders build the final look at run time, so UE Viewer's textures alone render
grey or wrong:

  armor  (parent chain CM_Armor*)   BaseColor is a GREY detail map; the colours come from the dye system:
         the Cstm mask's R/G/B/A channels each pick a region and multiply it by CustomMask<ch>_Color
         (Use_ColorCustom, CustomMask<ch>_Use > 0, strength CustomMask<ch>_Value).  ARM = AO / roughness /
         metallic; metal and roughness offsets per mask channel (Detail<ch>_MetalicUse / _Metalic /
         _RoughOffset); SE.G = emissive mask x EmissiveDay_intensity (coloured by the dye when
         Use_EmissiveColorCustom); BaseColor alpha = opacity (the *_DO maps).
  skin   (CM_Body_Cstm)    BaseColor skin + ARS(C) = AO / roughness / specular.
  face   (CM_Head_Cstm)    the shared GF_Head_D/GM_Head_D skin + per-head normal map; eyebrows are
         painted at run time from the Cstm_EyeBrow texture array (slice EyeBrow_NUMBER, B = strands,
         A = pencil) - placed here by BROW_BOX and mirrored.  Eye shadow / liner / lip layers are NOT
         baked yet (the base texture already carries lip and cheek colour).
  eye    (CM_Eye)          procedural iris: IrisColor_Mid / IrisColor_Edge over the iris mask, Pupil_Color pupil,
                           sclera; iris radius grows with Iris_Scale (IRIS_UV_PER_SCALE).
  eye_ao (CM_EyeAO_Cstm)   the shell in front of the eyes: lashes (EyelashAO G = upper, B = lower) and the
         corner shadow (R) -> black with alpha.
  tear   (CM_EyeAO_Trans)  tear line - left transparent.
  hair   (CM_HairCard*)    hair cards: RootColor/MidColor/TipColor x DIRO.R strand brightness, DIRO.A = alpha
         boosted by OpacityFar; cards use the atlas' top half, the scalp cap the bottom half (UV v halved -
         build_blend.py rewrites the hair UVs).  Many hairstyles' slots come out of UE Viewer as "material_0":
         export_model.py maps them to the MI_<mesh> next to the mesh.

Output: <out>/textures/<material>_albedo.png (RGBA when it has alpha), _orm.png (R AO, G roughness,
B metallic), _emission.png; normal maps are used as they are (DirectX: green flipped in Blender);
<out>/materials.json describes each material for build_blend.py.

    python bake_materials.py --umodel E:\\aion2_exports\\umodel_exports --out <dir> MI_GF_Angel_01_Body_LT ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image

IMAGE_EXTS = (".png", ".tga", ".hdr", ".dds")
MASK_CLIP = 0.33

# Eyebrow placement on the shared head UV (u right, v down, as in the image), right half of the face; the
# left one is mirrored about u = 0.5.  The brow texture (512 x 256) maps onto this box.  Measured on
# GF_Head_D: the right eye's lash line sits at u 0.61-0.65, v 0.374; the brow strands fill u 0.18-0.68,
# v 0.36-0.62 of the brow texture.  Tunable: --brow-box u0,v0,u1,v1.
BROW_BOX = (0.503, 0.281, 0.794, 0.388)


# ---------------------------------------------------------------- props
_PARAM_RE = re.compile(r"ParameterInfo = \{ Name=(?P<name>[^}]*?) \}\s*ParameterValue = (?P<value>[^\n]*)")
_REF_RE = re.compile(r"'(?P<path>/[^'.]+)\.[^']*'")
_VEC_RE = re.compile(r"R=(?P<r>[-\d.e]+), G=(?P<g>[-\d.e]+), B=(?P<b>[-\d.e]+), A=(?P<a>[-\d.e]+)")


def ref_to_rel(ref: str) -> str:
    """'/AION2/Content/Material/Chr/CM_Armor.CM_Armor' -> 'Material/Chr/CM_Armor'"""
    m = _REF_RE.search(ref)
    path = m.group("path") if m else ref
    for prefix in ("/AION2/Content/", "/Game/", "/AION2/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path.lstrip("/")


class Props:
    """One material instance's parameters, merged over its parent chain (child wins)."""

    def __init__(self, root: str, rel: str):
        self.root = root
        self.chain = []          # [rel paths], self first
        self.scalars, self.textures, self.vectors = {}, {}, {}
        self.blend_mode, self.two_sided = None, None
        seen = set()
        cur = rel
        while cur and cur not in seen:
            seen.add(cur)
            path = os.path.join(root, cur + ".props.txt")
            if not os.path.isfile(path):
                self.chain.append(cur + " (not exported)")
                break
            self.chain.append(cur)
            text = open(path, encoding="utf-8", errors="replace").read()
            for m in _PARAM_RE.finditer(text):
                name, value = m.group("name").strip(), m.group("value").strip()
                if value.startswith(("Texture", "TextureCube")):
                    self.textures.setdefault(name, ref_to_rel(value))
                elif value.startswith("{") and "R=" in value:
                    v = _VEC_RE.search(value)
                    if v:
                        self.vectors.setdefault(name, tuple(float(v.group(k)) for k in "rgba"))
                else:
                    try:
                        self.scalars.setdefault(name, float(value))
                    except ValueError:
                        pass
            bm = re.search(r"bOverride_BlendMode = (true|false)\s*\n\s*BlendMode = (\w+)", text)
            if bm and self.blend_mode is None and (bm.group(1) == "true" or cur == self.chain[-1] and "Material3" in text):
                self.blend_mode = bm.group(2)
            if self.blend_mode is None and not text.startswith("Parent"):
                bm2 = re.search(r"^BlendMode = (\w+)", text, re.M)
                if bm2:
                    self.blend_mode = bm2.group(1)
            ts = re.search(r"bOverride_TwoSided = (true|false)\s*\n\s*TwoSided = (true|false)", text)
            if ts and self.two_sided is None and ts.group(1) == "true":
                self.two_sided = ts.group(2) == "true"
            if self.two_sided is None and not text.startswith("Parent"):
                ts2 = re.search(r"^TwoSided = (true|false)", text, re.M)
                if ts2:
                    self.two_sided = ts2.group(1) == "true"
            pm = re.search(r"^Parent = (.+)$", text, re.M)
            cur = ref_to_rel(pm.group(1)) if pm and "None" not in pm.group(1) else None

    def s(self, name, default=0.0):
        return self.scalars.get(name, default)

    def v(self, name, default=(1.0, 1.0, 1.0, 1.0)):
        return self.vectors.get(name, default)

    def kind(self) -> str:
        names = " ".join(os.path.basename(c).lower() for c in self.chain)
        if "cm_armor" in names or "cmm_armor" in names:
            return "armor"
        if "cm_body" in names or "cmm_body" in names:
            return "skin"
        if "cm_head" in names or "cmm_head" in names:
            return "face"
        if "cm_eyeao_trans" in names:
            return "tear"
        if "cm_eyeao" in names:
            return "eye_ao"
        if "cm_eye" in names:
            return "eye"
        if "cm_hair" in names or "haircard" in names:
            return "hair"
        return "generic"


# ---------------------------------------------------------------- images
def find_texture(root: str, rel: str, slice_index: int | None = None) -> str | None:
    base = os.path.join(root, rel)
    if slice_index is not None:
        base = "%s_%02d" % (base, slice_index)
    for ext in IMAGE_EXTS:
        if os.path.isfile(base + ext):
            return base + ext
    return None


def load(path: str, size=None) -> np.ndarray:
    im = Image.open(path)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    if size and im.size != size:
        im = im.resize(size, Image.BILINEAR)
    return np.asarray(im).astype(np.float32) / 255.0


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def save(arr: np.ndarray, path: str):
    arr = np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGBA" if arr.shape[2] == 4 else "RGB").save(path, optimize=False)


# ---------------------------------------------------------------- bakers
def bake_armor(name, p: Props, root, tex_dir, entry):
    path = find_texture(root, p.textures.get("BaseColor", ""))
    if not path:
        entry["warnings"].append("no BaseColor texture")
        return
    d = load(path)
    h, w = d.shape[:2]
    lin = srgb_to_lin(d[..., :3])
    alpha = d[..., 3] if d.shape[2] == 4 else None
    mpath = find_texture(root, p.textures.get("Cstm", ""))
    mask = load(mpath, (w, h)) if mpath else None
    tint = np.ones_like(lin)
    used = []
    if p.s("Use_ColorCustom") > 0 and mask is not None:
        for i, ch in enumerate("RGBA"):
            if i >= mask.shape[2] or p.s("CustomMask%s_Use" % ch) <= 0:
                continue
            col = np.array(p.v("CustomMask%s_Color" % ch)[:3], np.float32)
            m = mask[..., i:i + 1] * p.s("CustomMask%s_Value" % ch, 1.0)
            tint = tint * (1.0 - m) + col * m
            used.append(ch)
    dyed = lin * tint
    apath = find_texture(root, p.textures.get("ARM", ""))
    if apath:
        arm = load(apath, (w, h))
        ao, rough, metal = arm[..., 0], arm[..., 1], arm[..., 2]
    else:
        ao, rough, metal = np.ones((h, w), np.float32), np.full((h, w), 0.6, np.float32), np.zeros((h, w), np.float32)
    if mask is not None:
        for i, ch in enumerate("RGBA"):
            if i >= mask.shape[2] or p.s("Detail%s_USE" % ch) <= 0:
                continue
            m = mask[..., i]
            if p.s("Detail%s_MetalicUse" % ch) > 0:
                metal = np.maximum(metal, m * p.s("Detail%s_Metalic" % ch))
            rough = rough + m * p.s("Detail%s_RoughOffset" % ch)
    rough = np.clip(rough + p.s("Roughness_Add"), 0.04, 1.0)
    albedo = lin_to_srgb(dyed * (0.55 + 0.45 * ao[..., None]))
    if alpha is not None and alpha.min() < 0.5:
        albedo = np.concatenate([albedo, alpha[..., None]], axis=2)
        entry["alpha"] = "clip"
    out = os.path.join(tex_dir, name + "_albedo.png")
    save(albedo, out)
    entry["albedo"] = out
    orm = os.path.join(tex_dir, name + "_orm.png")
    save(np.stack([ao, rough, metal], axis=2), orm)
    entry["orm"] = orm
    spath = find_texture(root, p.textures.get("SE", ""))
    if spath and p.s("EmissiveDay_intensity") > 0:
        se = load(spath, (w, h))[..., 1]
        if se.max() > 0.02:
            col = dyed if p.s("Use_EmissiveColorCustom") > 0 else np.ones_like(dyed)
            emis = os.path.join(tex_dir, name + "_emission.png")
            save(lin_to_srgb(np.clip(col * se[..., None] * 2.0, 0, 1)), emis)
            entry["emission"] = emis
            entry["emission_strength"] = round(p.s("EmissiveDay_intensity") * p.s("EmissiveDay_Power", 1.0), 3)
    entry["dye_channels"] = used


def bake_skin_or_face(name, p: Props, root, tex_dir, entry, face=False):
    path = find_texture(root, p.textures.get("BaseColor", ""))
    if not path:
        entry["warnings"].append("no BaseColor texture")
        return
    d = load(path)
    h, w = d.shape[:2]
    srgb = d[..., :3].copy()
    apath = find_texture(root, p.textures.get("ARS", ""))
    ars = load(apath, (w, h)) if apath else None
    if face:
        srgb = paint_brows(srgb, p, root, entry)
    lin = srgb_to_lin(srgb)
    if ars is not None:
        lin = lin * (0.65 + 0.35 * ars[..., 0:1])
    out = os.path.join(tex_dir, name + "_albedo.png")
    save(lin_to_srgb(lin), out)
    entry["albedo"] = out
    if ars is not None:
        orm = os.path.join(tex_dir, name + "_orm.png")
        save(np.stack([ars[..., 0], np.clip(ars[..., 1], 0.3, 1.0), np.zeros((h, w), np.float32)], axis=2), orm)
        entry["orm"] = orm
    entry["subsurface"] = 0.08


def paint_brows(srgb, p: Props, root, entry):
    if p.s("Use_EyeBrow", 1) <= 0:
        # NPC faces with a texture of their own (Leda: NPC_Leda_01_Head_D) switch the brow layer off - the brows are
        # in that texture; the inherited EyeBrow_NUMBER (5 from MI_GF_Head_007) must not paint a second pair
        entry["eyebrow"] = "off (Use_EyeBrow 0)"
        return srgb
    rel = None
    for key in p.textures:
        if "eyebrow" in key.lower():
            rel = p.textures[key]
    # the array is a material-function input, not an instance parameter: find it by name next to the head
    if rel is None:
        for cand in ("Character/Player/Customize/Cstm_EyeBrow_T2A",):
            if find_texture(root, cand, 0):
                rel = cand
    index = int(p.s("EyeBrow_NUMBER", 0))
    path = find_texture(root, rel, index) if rel else None
    if path is None and rel:
        path = find_texture(root, rel)              # EyeBrow_NUMBER_Texture: one brow texture, not an array
    if not path:
        entry["warnings"].append("eyebrow texture slice %d not found" % index)
        return srgb
    brow = load(path)
    h, w = srgb.shape[:2]
    u0, v0, u1, v1 = BROW_BOX
    x0, x1, y0, y1 = int(u0 * w), int(u1 * w), int(v0 * h), int(v1 * h)
    patch = np.asarray(Image.fromarray((brow * 255).astype(np.uint8), "RGBA").resize((x1 - x0, y1 - y0), Image.BILINEAR)).astype(np.float32) / 255
    hair = patch[..., 2:3] * p.s("EyeBrowHair_intensity", 0.8)
    pencil = patch[..., 3:4] * p.s("EyeBrowPencil_Intensity", 0.5)
    hair_col = lin_to_srgb(np.array(p.v("EyeBrowHair_Color", (0.08, 0.03, 0.02, 1))[:3], np.float32))
    pencil_col = lin_to_srgb(np.array(p.v("EyeBrowPencil_Color", (0.1, 0.04, 0.03, 1))[:3], np.float32))
    for side in ("right", "left"):
        if side == "right":
            region = srgb[y0:y1, x0:x1]
            hp, pp = hair, pencil
        else:
            lx0, lx1 = w - x1, w - x0
            region = srgb[y0:y1, lx0:lx1]
            hp, pp = hair[:, ::-1], pencil[:, ::-1]
        region[:] = region * (1 - pp) + pencil_col * pp
        region[:] = region * (1 - hp) + hair_col * hp
    entry["eyebrow"] = "slice %d at %s" % (index, ",".join("%.3f" % x for x in BROW_BOX))
    return srgb


# Iris_Scale GROWS the iris: the iris disc on the eyeball UV has radius IRIS_UV_PER_SCALE * Iris_Scale.  Values seen:
# MI_Head_Eye (the default) 0.7, GF_Head_001 1.75, GF_Head_002 0.98, NPC Yustiel 0.8.  Until 10-25 the UV was scaled BY
# Iris_Scale (radius 0.47 / scale): only GF_Head_001 looked right, every smaller value gave an iris wider than the eyelid
# opening (ray tests on the head meshes: the visible eyeball spans |uv| <= ~0.25 across and ~0.1 up / down, the same
# eyeball UV layout on player and NPC heads) - Yustiel's eyes rendered as one black pupil.  The constant keeps
# GF_Head_001 as it was (0.47 / 1.75 at 1.75); the default 0.7 now gives a radius of 0.107.
IRIS_UV_PER_SCALE = 0.47 / 1.75 / 1.75
PUPIL_OF_IRIS = 0.33                            # pupil radius / iris radius (Pupil_Size / Pupil_Scale not decoded)


def bake_eye(name, p: Props, root, tex_dir, entry, size=1024):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx + 0.5) / size - 0.5
    v = (yy + 0.5) / size - 0.5
    r = np.sqrt(u * u + v * v)
    iris_r = IRIS_UV_PER_SCALE * p.s("Iris_Scale", 0.7)
    tex_scale = 0.47 / iris_r                  # the iris maps' disc (0.47 of the texture) onto that circle
    mid = np.array(p.v("IrisColor_Mid", (0.11, 0.16, 0.18, 1))[:3], np.float32)
    edge = np.array(p.v("IrisColor_Edge", (0.05, 0.08, 0.10, 1))[:3], np.float32)
    t = np.clip(r / iris_r, 0, 1)
    iris = mid * (1 - t[..., None] ** 2) + edge * (t[..., None] ** 2)
    mpath = find_texture(root, p.textures.get("IrisMasks", "Character/Player/Common/Iris_02_M"))
    if mpath:
        m = load(mpath)
        ms = m.shape[0]
        tu = np.clip((u * tex_scale + 0.5) * ms, 0, ms - 1).astype(int)
        tv = np.clip((v * tex_scale + 0.5) * ms, 0, ms - 1).astype(int)
        fib = m[tv, tu, 1]
        iris = iris * (0.55 + 0.9 * fib[..., None])
    pupil_r = iris_r * PUPIL_OF_IRIS
    pupil = np.clip((r - pupil_r) / (iris_r * 0.08), 0, 1)[..., None]
    pupil_col = np.array(p.v("Pupil_Color", (0, 0, 0, 1))[:3], np.float32)   # Yustiel: dark grey, not black
    iris = iris * pupil + pupil_col * (1 - pupil)
    limbus = np.clip((r - iris_r * 0.92) / (iris_r * 0.12), 0, 1)[..., None]
    sclera = srgb_to_lin(np.array([0.86, 0.84, 0.83], np.float32)) * np.array(p.v("Sclera_Color", (1, 1, 1, 1))[:3], np.float32)
    lin = iris * (1 - limbus) + sclera * limbus
    out = os.path.join(tex_dir, name + "_albedo.png")
    save(lin_to_srgb(lin), out)
    entry["albedo"] = out
    entry["roughness"] = 0.08
    entry["iris_uv_radius"] = round(float(iris_r), 4)


def bake_eye_ao(name, p: Props, root, tex_dir, entry):
    path = find_texture(root, p.textures.get("EyelashAO", ""))
    if not path:
        entry["alpha"] = "hide"
        return
    m = load(path)
    lashes = np.maximum(m[..., 1] * p.s("EyelashUpper_intensity", 0.7) * 1.3, m[..., 2] * p.s("EyelashLower_intensity", 0.7) * 1.3)
    shade = m[..., 0] * p.s("EyeAO_intensity", 0.4)
    alpha = np.clip(np.maximum(np.clip(lashes, 0, 1), shade), 0, 1)
    rgb = np.zeros(m.shape[:2] + (3,), np.float32) + 0.02
    out = os.path.join(tex_dir, name + "_albedo.png")
    save(np.concatenate([rgb, alpha[..., None]], axis=2), out)
    entry["albedo"] = out
    entry["alpha"] = "blend"
    entry["roughness"] = 0.8


def bake_hair(name, p: Props, root, tex_dir, entry):
    path = find_texture(root, p.textures.get("DIRO", ""))
    if not path:
        entry["warnings"].append("no DIRO texture")
        return
    d = load(path)
    col = np.array(p.v("MidColor", p.v("RootColor", (0.05, 0.03, 0.02, 1)))[:3], np.float32)
    shade = (0.35 + 1.1 * d[..., 0:1])
    lin = col * shade
    alpha = d[..., 3:4] if d.shape[2] == 4 else np.ones(d.shape[:2] + (1,), np.float32)
    # the shader boosts the strand opacity (OpacityFar x, OpacityPowFar ^); the raw alpha clipped at 1/3 left the
    # scalp showing through GF_Hair_001 (measured 10-25)
    alpha = np.clip(alpha * p.s("OpacityFar", 2.0), 0.0, 1.0) ** p.s("OpacityPowFar", 1.0)
    out = os.path.join(tex_dir, name + "_albedo.png")
    save(np.concatenate([lin_to_srgb(lin), alpha], axis=2), out)
    entry["albedo"] = out
    entry["alpha"] = "hashed"
    entry["roughness"] = 0.45
    entry["hair_colors"] = {k: [round(x, 4) for x in p.v(k)[:3]] for k in ("RootColor", "MidColor", "TipColor")}
    # Every hair atlas (T_Hair_0x_DIRO) holds the cards in its top half and a scalp cap in the bottom half.  The
    # cards' UVs span the FULL height (v 0..1) and cap polygons (CM_HairCardCap hairs) run v -1..0: both shaders
    # halve v.  build_blend.py rewrites the UVs (v' = 0.5 + 0.5 v) so the model also works in tools without that
    # shader.  Without it a card's lower half samples the cap blob: opaque dark blocks on GF_Hair_203 / 208 / 412
    # (10-25; GF_Hair_110 only got away with it because its cards' lower halves fall on transparent texels).
    entry["uv_half_atlas"] = True


def bake_generic(name, p: Props, root, tex_dir, entry):
    for key in ("BaseColor", "Diffuse", "Base Color", "Albedo"):
        path = find_texture(root, p.textures.get(key, ""))
        if path:
            entry["albedo_raw"] = path
            return
    entry["warnings"].append("no colour texture (generic kind)")


BAKERS = {"armor": bake_armor, "skin": lambda n, p, r, t, e: bake_skin_or_face(n, p, r, t, e, False),
          "face": lambda n, p, r, t, e: bake_skin_or_face(n, p, r, t, e, True), "eye": bake_eye,
          "eye_ao": bake_eye_ao, "hair": bake_hair, "generic": bake_generic}


def index_materials(root: str) -> dict:
    """material name -> rel path (a .mat file marks a material; a mesh has only .props.txt)"""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".mat"):
                rel = os.path.relpath(os.path.join(dirpath, f[:-4]), root).replace("\\", "/")
                out.setdefault(f[:-4], rel)
    return out


def bake(root: str, out_dir: str, names: list, rels: dict | None = None) -> dict:
    """rels: material name -> rel path for names the export root holds more than once (MI_GF_Hair is in every
    hairstyle folder) or that export_model.py renamed (MI_GF_Hair__GF_Hair_402); the rest are found by name."""
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)
    index = index_materials(root)
    result = {}
    for name in names:
        entry = {"kind": "missing", "warnings": []}
        rel = (rels or {}).get(name)
        if rel is None or not os.path.isfile(os.path.join(root, rel.replace("/", os.sep) + ".mat")):
            rel = index.get(name)
        if rel is None:
            entry["warnings"].append("material not exported by UE Viewer")
            result[name] = entry
            continue
        p = Props(root, rel)
        entry["kind"] = p.kind()
        entry["chain"] = [os.path.basename(c) for c in p.chain]
        entry["blend_mode"] = p.blend_mode
        entry["two_sided"] = bool(p.two_sided)
        npath = find_texture(root, p.textures.get("NormalBase", p.textures.get("Normal", "")))
        if npath and entry["kind"] not in ("eye", "eye_ao", "tear"):
            entry["normal"] = npath
        if entry["kind"] == "tear":
            entry["alpha"] = "hide"
        else:
            try:
                BAKERS[entry["kind"]](name, p, root, tex_dir, entry)
            except Exception as exc:  # noqa: BLE001
                entry["warnings"].append("bake failed: %r" % exc)
        result[name] = entry
        print("  %-28s %-8s %s" % (name, entry["kind"], "; ".join(entry["warnings"]) or "ok"), flush=True)
    with open(os.path.join(out_dir, "materials.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    return result


def main():
    global BROW_BOX
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--umodel", required=True, help="UE Viewer export root (…\\umodel_exports)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--brow-box", help="u0,v0,u1,v1 of the right eyebrow on the head texture (default %s)" %
                    ",".join(str(x) for x in BROW_BOX))
    ap.add_argument("materials", nargs="+")
    args = ap.parse_args()
    if args.brow_box:
        BROW_BOX = tuple(float(x) for x in args.brow_box.split(","))
    bake(args.umodel, args.out, args.materials)
    return 0


if __name__ == "__main__":
    sys.exit(main())
