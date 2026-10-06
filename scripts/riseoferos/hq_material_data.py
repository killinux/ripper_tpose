"""The game's own material definitions + the textures they use, for one ROE character.

The FBX route (AssetStudio) gives exact geometry, but the Blender materials only got the albedo.
This reads the material bundles directly with UnityPy (system Python, not Blender) and writes into a
cache shared by all characters:

  <cache>/<id>.json         every Material found for <id>: shader keywords, texture slots (+ tiling),
                            floats, colours, source bundle; the face override (see below)
  <cache>/textures/*.png    the textures of the selected materials, decoded from the bundles (mip 0,
                            lossless).  Normal maps are Unity DXT5nm (R=1, G=B=Y, A=X); each is also
                            written as a standard tangent-space RGB map <name>__nrm.png (Z rebuilt)
  <cache>/export/*.png      per lit material, for the formats that cannot run a node tree: XPS diffuse
                            (albedo x _BaseColor), lightmap (AO), bump (green flipped: XPS default
                            tangent space; flat when none), specular (sqrt smoothness); PMX diffuse (albedo x
                            _BaseColor x AO); see-through: alpha x _BaseColor alpha, premultiplied glass at
                            least --glass-alpha (neither format draws its reflections)

Bundles (install dir + runtime cache, newest copy wins): every chara_mat_* whose name has pc_<id>,
pc_<family>_common, or is a shared bare / armor / system bundle (families name their head bundles
differently: pc_a_common_head_tutorial, pc_g_common_head_prelude ...), plus the paired chara_tex_*
bundles and the shared texture bundles (hair normal / strand occlusion, skin detail normal, eyes ...),
plus every chara_tex_* bundle the game's Manifest.ab lists as a dependency of those material bundles: 32
materials draw another character's texture (k06's hair = k04's albedo, e06's = the d family's, the i family's
head = the h family's iris / eyebrow), and read by name alone those slots came out empty.
Glass and glowing parts have no colour texture (Unity's white default: the colour is _BaseColor): flat_kind()
"glass" / "flat", with 8 x 8 export maps.
The outfit suits (export_suits.py: pc_a01_fm, pc_j01_prouniform ...) add their component bundles:
accessory_components_pc_<id>_suit_* (materials) + chara_tex_components_pc_<id>_suit_* (textures), and the
shared fm pieces' accessory_components_common_* / chara_tex_components_common_*.  The other shared pieces
(fm rings, arm / leg hair, ears) sit in accessory_<hash>_common_<piece> bundles, found from an albedo
Common_<Piece>_rgbx_Albedo; <id>.json "pieces" keeps the ones looked up, so a later run for another
suit of the character still reads their bundles.
Materials are selected by name (--materials) or by the albedo they use (--albedos); only their
textures are decoded.  When two bundles define the same material name (HD and LD heads), the one
with the bigger textures wins; a suit's own definition is also kept as <name>@<suit> (two suits can
name a piece alike: g01 sleepwear / yoga Rouffe_Underwear_obj001).  Names do not identify textures
either (the g01 HD outfit's MGAC is called pc_g01_nk_body_rgbx_MGAC, like the nude body's own): a slot
records the object it points at ("source"), and when one name covers different data the material
gets its own copy, <stem>__<md5 8>_rgbx_<type>, through "overrides".  <id>.json accumulates: a later
run adds its selection to what an earlier one (the outfit, a suit, the nude base) already decoded.

Face override: the runtime head bundle can carry the outfit's own face albedo pc_<id>_hd_face
(Inase a01: same face, light scalp for her silver hair; the shared pc_<f>_nk_face has a dark one);
it replaces the face material's _BaseMap for that id.

  python hq_material_data.py g05 --out D:/roe_exports/_hq_materials --albedos pc_g05_hd_body1_rgbx_Albedo,...
Prints ROE_HQ_DATA={json}.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time

import numpy as np
import UnityPy
from PIL import Image

GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles"
CACHE = os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "Pinkcore", "Rise of Eros", "AssetBundles")
NORMAL_SLOTS = {"_BumpMap", "_DetailNormalMap", "_EyeBumpMap"}
SHARED_MAT = ("chara_mat_bare_common", "chara_mat_armor_common", "chara_mat_armor__system")
SHARED_TEX = ("chara_tex_bare_common", "chara_tex_armor_common", "chara_tex_armor__system")
MANIFEST = "Manifest.ab"          # the game's bundle list with each bundle's dependencies
# least alpha of premultiplied glass in the XPS / PMX textures: env ROE_GLASS_ALPHA (the exports pick it up too) or
# --glass-alpha; a change rebuilds the affected maps by itself (export_signatures)
GLASS_ALPHA = float(os.environ.get("ROE_GLASS_ALPHA", "0.25"))


def _items(x):
    return x.items() if isinstance(x, dict) else x


def _read(pptr):
    try:
        return pptr.read() if pptr is not None and getattr(pptr, "path_id", 0) else None
    except Exception:
        return None


def inventory(roots):
    """{bundle file name: newest path} across the install dir and the runtime cache."""
    found = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            if name.endswith(".ab"):
                path = os.path.join(root, name)
                if name not in found or os.path.getmtime(path) > os.path.getmtime(found[name]):
                    found[name] = path
    return found


def shared_pieces(albedos):
    """The shared accessory pieces a set of albedos names: Common_<Piece>_rgbx_Albedo -> <piece>."""
    return {m.group(1) for m in (re.match(r"common_(.+?)_rgbx_albedo$", a.lower()) for a in albedos) if m}


def manifest_deps(bundles):
    """{bundle (no .ab): [the bundles it depends on]} from the game's Manifest.ab (a MonoBehaviour m_Keys / m_Values).
    A material can point at another character's texture bundle: k06's hair draws k04's hair albedo, e06's the d
    family's, the i family's head the h family's iris - 32 such links; read by name only, those slots came out empty."""
    path = bundles.get(MANIFEST)
    if not path:
        return {}
    try:
        env = UnityPy.load(path)
        for obj in env.objects:
            if obj.type.name == "MonoBehaviour":
                tree = obj.read_typetree()
                if "m_Keys" in tree and "m_Values" in tree:
                    return {k: list(v.get("m_Dependencies") or ()) for k, v in zip(tree["m_Keys"], tree["m_Values"])}
    except Exception as exc:              # no manifest: the name rule alone, as before
        print("manifest unreadable: %s" % exc, file=sys.stderr)
    return {}


def select_bundles(cid, bundles, albedos=(), pieces=(), deps=None):
    fam = cid[0]
    mats = sorted(n for n in bundles if n.startswith("chara_mat_") and (
        "pc_%s" % cid in n or "pc_%s_common" % fam in n or n.startswith(SHARED_MAT)))
    texs = {"chara_tex_" + n[len("chara_mat_"):] for n in mats} & set(bundles)
    texs |= {n for n in bundles if n.startswith(SHARED_TEX) or n.startswith("chara_tex_bare_pc_%s_common" % fam)}
    # the suits' pieces: accessory_components_pc_<id>_suit_<suit> + the shared fm pieces (horns, cuffs ...)
    mats += sorted(n for n in bundles if n.startswith(("accessory_components_pc_%s_suit_" % cid,
                                                       "accessory_components_common_")))
    texs |= {n for n in bundles if n.startswith(("chara_tex_components_pc_%s_suit_" % cid,
                                                 "chara_tex_components_common_"))}
    # shared accessory pieces (the fm rings, arm / leg hair): accessory_<hash>_common_<piece>.ab +
    # chara_tex_<hash>_common_<piece>.ab, too many to load them all - found from the piece's albedo name
    # Common_<Piece>_rgbx_Albedo (+ `pieces`, the ones earlier runs looked up)
    pieces = shared_pieces(albedos) | set(pieces)
    # the fm set shares textures across pieces (the arm hair albedo sits in ..._common_fmmleghair_obj001):
    # any fm piece reads all of it, a handful of small bundles (as suit_bundle.bundle_paths does)
    fm = any(p.startswith("fm") for p in pieces)
    for name in bundles:
        m = re.match(r"(accessory|chara_tex)_[0-9a-f]{8}_common_(.+)\.ab$", name)
        if m and (m.group(2) in pieces or (fm and m.group(2).startswith("fm"))):
            if m.group(1) == "accessory":
                mats.append(name)
            else:
                texs.add(name)
    # + the texture bundles the game's manifest lists for those material bundles (another character's, too)
    for name in mats:
        for dep in (deps or {}).get(name[:-3] if name.endswith(".ab") else name, ()):
            if dep.startswith("chara_tex_") and dep + ".ab" in bundles:
                texs.add(dep + ".ab")
    return mats, sorted(texs)


def to_standard_normal(img):
    """Unity DXT5nm (x in A, y in G) -> RGB tangent-space normal with Z rebuilt; an RGB map (R not a
    constant 1) is returned as is."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    if arr[..., 0].mean() < 0.98:
        return img.convert("RGB"), False
    x = arr[..., 3] * 2.0 - 1.0
    y = arr[..., 1] * 2.0 - 1.0
    z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
    rgb = np.stack([x, y, z], axis=-1) * 0.5 + 0.5
    return Image.fromarray(np.clip(np.rint(rgb * 255.0), 0, 255).astype(np.uint8), "RGB"), True


def save_png(img, path):
    """Atomic write; parallel lanes may decode the same shared texture at the same time."""
    tmp = "%s.%d.tmp.png" % (path, os.getpid())
    img.save(tmp)
    try:
        os.replace(tmp, path)
    except PermissionError:          # another process holds the finished file open: it is identical
        os.remove(tmp)


def role_of(mdef):
    """Same rule as hq_materials_blender.role_of: hair / pbr / skin, or None (kept as the add-on made it)."""
    tex, kw = mdef["textures"], set(mdef["keywords"])
    if "_ShiftNoiseMap" in tex or "HAIR_AM" in kw:
        return "hair"
    if "_IrisAlbedoTex" in tex or "_BaseMap" not in tex:
        return None
    if "_BumpMap" in tex or "_MetallicGlossMap" in tex or "DIRECT_SPECULAR" in kw:     # + the lit shader, albedo only
        skin = "_SkinLutMap" in tex or mdef["floats"].get("_EanbleTranslucency", 0.0) > 0.0   # sic
        return "skin" if skin else "pbr"
    return None


EYE_TEXTURES = ("_IrisAlbedoTex", "_ScleraAlbedoTex", "_EyeBumpMap")


def flat_kind(mdef):
    """Same rule as hq_materials_blender.flat_kind: a lit material with no colour texture (the shader samples
    Unity's white default, so _BaseColor is the colour): "glass" when see-through (lenses, glass, tears), "flat"
    when opaque (glowing parts).  None for textured materials, hair and eyes."""
    tex, kw = mdef["textures"], set(mdef["keywords"])
    if "_BaseMap" in tex or "_BaseColor" not in mdef["colors"]:
        return None
    if "_ShiftNoiseMap" in tex or "HAIR_AM" in kw or any(k in tex for k in EYE_TEXTURES):
        return None
    return "glass" if mdef["floats"].get("_Surface", 0.0) > 0.0 else "flat"


def premultiplied(mdef):
    """See-through with premultiplied alpha: the diffuse x alpha, the reflections kept whole (URP Lit
    _ALPHAPREMULTIPLY_ON) - glass with _BaseColor alpha 0 shows only its reflections."""
    fl, kw = mdef["floats"], set(mdef["keywords"])
    return fl.get("_Surface", 0.0) > 0.0 and (fl.get("_EnablePremultiplyAlpha", 0.0) > 0.0 or "_ALPHAPREMULTIPLY_ON" in kw)


def emission_colour(mdef):
    """The glow colour scaled into 0..1 (sRGB) for the formats without emission, or None."""
    col, fl = mdef["colors"], mdef["floats"]
    em = col.get("_EmissionColor", [0.0, 0.0, 0.0, 1.0])[:3]
    if fl.get("_EnableEmission", 0.0) <= 0.0 or max(em) <= 1e-4:
        return None
    top = max(em)
    return [c / top if top > 1.0 else c for c in em]


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1.0 / 2.4) - 0.055)


def safe_name(name):
    return "".join(c if c.isalnum() or c in "-." else "_" for c in name)


def export_signature(mdef, sources, glass_alpha):
    """What export_maps makes a material's maps of: its textures, the alpha factor, a flat material's colour."""
    base = mdef["colors"].get("_BaseColor", [1, 1, 1, 1])
    role = role_of(mdef)
    factor = 1.0
    if mdef["floats"].get("_Surface", 0.0) > 0.0 and role != "hair" and len(base) > 3 and base[3] < 1.0:
        factor = round(max(float(base[3]), glass_alpha if premultiplied(mdef) else 0.0), 4)
    kind = None if role else flat_kind(mdef)
    if kind:
        return json.dumps([sorted(sources), factor, kind, [round(c, 4) for c in (emission_colour(mdef) or base[:3])]])
    return json.dumps([sorted(sources), factor])


def export_maps(out_dir, mname, mdef, override, force=False, glass_alpha=None):
    """Textures for the formats that cannot run the Blender node tree (paths relative to out_dir):
      xps: diffuse = albedo x _BaseColor (alpha kept), lightmap = the AO the .blend uses, bump = the
           normal map with green flipped (XPS default tangent space inverts Y), specular = sqrt(smoothness)
           (XPS Tools reads roughness = 1 - spec^2), hair: flat 0.35
      pmx: diffuse = albedo x _BaseColor x AO (MMD has no normal / metal / AO input)
    A see-through material's alpha also takes _BaseColor's alpha; premultiplied glass (alpha 0: only its reflections
    show in the game) keeps at least glass_alpha, as neither format draws reflections.  A material with no colour
    texture (flat_kind: lenses, glass, glowing parts) gets 8 x 8 maps of its colour (a glowing part: its glow's)."""
    glass_alpha = GLASS_ALPHA if glass_alpha is None else glass_alpha
    role = role_of(mdef)
    kind = None if role else flat_kind(mdef)
    if role is None and kind is None:
        return None
    tex, fl, col = mdef["textures"], mdef["floats"], mdef["colors"]
    stem = safe_name(mname)
    # render group 24 / 25 takes four maps: a material without a normal map gets a flat one (not missing.png)
    rel = {"diffuse": "export/%s__xps_diffuse.png" % stem, "lightmap": "export/%s__xps_light.png" % stem,
           "bump": "export/%s__xps_bump.png" % stem, "specular": "export/%s__xps_spec.png" % stem,
           "pmx": "export/%s__pmx_diffuse.png" % stem}
    paths = {k: os.path.join(out_dir, v) for k, v in rel.items()}
    if not force and all(os.path.isfile(p) for p in paths.values()):
        return rel
    os.makedirs(os.path.join(out_dir, "export"), exist_ok=True)
    base = col.get("_BaseColor", [1, 1, 1, 1])
    if kind:
        albedo = np.ones((8, 8, 4), dtype=np.float32)
        albedo[..., :3] = np.clip(np.asarray(emission_colour(mdef) or base[:3], dtype=np.float32), 0.0, 1.0)
        tint = np.ones(3, dtype=np.float32)
    else:
        albedo_name = override.get("_BaseMap", tex["_BaseMap"]["texture"])
        albedo = np.asarray(Image.open(os.path.join(out_dir, "textures", albedo_name + ".png")).convert("RGBA"),
                            dtype=np.float32) / 255.0
        tint = srgb_to_linear(np.asarray(base[:3], dtype=np.float32))
    rgb = srgb_to_linear(albedo[..., :3]) * tint
    alpha = albedo[..., 3:4]
    if fl.get("_Surface", 0.0) > 0.0 and role != "hair" and len(base) > 3 and base[3] < 1.0:
        alpha = alpha * max(float(base[3]), glass_alpha if premultiplied(mdef) else 0.0)
    occ_slot = "_OcclusionMaskMap" if role == "hair" else "_MetallicGlossMap"
    mask = None
    if occ_slot in tex:
        mask = np.asarray(Image.open(os.path.join(out_dir, "textures", override.get(occ_slot, tex[occ_slot]["texture"])
                                                  + ".png")).convert("RGBA"), dtype=np.float32) / 255.0
    strength = fl.get("_OcclusionStrength", 1.0)
    if mask is not None:
        ao = 1.0 - strength + strength * mask[..., 0 if role == "hair" else 2]
    else:
        ao = np.ones(albedo.shape[:2], dtype=np.float32)

    def save(key, arr, mode):
        save_png(Image.fromarray(np.clip(np.rint(arr * 255.0), 0, 255).astype(np.uint8), mode), paths[key])

    save("diffuse", np.concatenate([linear_to_srgb(rgb), alpha], axis=-1), "RGBA")
    save("lightmap", np.repeat(ao[..., None], 3, axis=-1), "RGB")
    if ao.shape != albedo.shape[:2]:
        ao_full = np.asarray(Image.fromarray(np.clip(np.rint(ao * 255.0), 0, 255).astype(np.uint8), "L")
                             .resize((albedo.shape[1], albedo.shape[0]), Image.BILINEAR), dtype=np.float32) / 255.0
    else:
        ao_full = ao
    save("pmx", np.concatenate([linear_to_srgb(rgb * ao_full[..., None]), alpha], axis=-1), "RGBA")
    if "_BumpMap" in tex:
        nrm = np.asarray(Image.open(os.path.join(out_dir, "textures", override.get("_BumpMap", tex["_BumpMap"]["texture"])
                                                 + "__nrm.png")).convert("RGB"), dtype=np.float32) / 255.0
        nrm[..., 1] = 1.0 - nrm[..., 1]
        save("bump", nrm, "RGB")
    else:
        save("bump", np.tile(np.array([0.5, 0.5, 1.0], dtype=np.float32), (8, 8, 1)), "RGB")
    if kind and mask is None:
        spec = np.full((8, 8), np.sqrt(np.clip(fl.get("_Smoothness", 0.5), 0.0, 1.0)), dtype=np.float32)
    elif role == "hair" or mask is None:
        spec = np.full((8, 8), 0.35, dtype=np.float32)
    else:
        spec = np.sqrt(np.clip(mask[..., 1] * fl.get("_Smoothness", 1.0), 0.0, 1.0))
    save("specular", np.repeat(spec[..., None], 3, axis=-1), "RGB")
    return rel


def _source(obj):
    """[serialized file, path id] of a read object: two different textures can share a name."""
    reader = getattr(obj, "object_reader", None)
    return [reader.assets_file.name.lower(), int(reader.path_id)] if reader is not None else None


def texture_digest(obj):
    """md5 of a Texture2D's stored data (in the object or its .resS stream), without decoding it."""
    tex = obj.read()
    data = getattr(tex, "image_data", b"") or b""
    stream = getattr(tex, "m_StreamData", None)
    if not data and stream is not None and stream.path:
        from UnityPy.helpers.ResourceReader import get_resource_data
        data = get_resource_data(stream.path, obj.assets_file, stream.offset, stream.size)
    return hashlib.md5(data).hexdigest()


def unique_texture_name(name, digest):
    """pc_g01_nk_body_rgbx_MGAC -> pc_g01_nk_body__9cf04c98_rgbx_MGAC (the type suffix stays last)."""
    m = re.match(r"(.+?)(_rgbx_\w+)$", name)
    return "%s__%s%s" % (m.group(1), digest[:8], m.group(2)) if m else "%s__%s" % (name, digest[:8])


def material_def(m, bundle):
    props = m.m_SavedProperties
    slots = {}
    for key, value in _items(props.m_TexEnvs):
        tex = _read(value.m_Texture)
        if tex is not None:
            slots[key] = {"texture": tex.m_Name, "scale": [float(value.m_Scale.x), float(value.m_Scale.y)],
                          "offset": [float(value.m_Offset.x), float(value.m_Offset.y)],
                          "size": [int(tex.m_Width), int(tex.m_Height)], "source": _source(tex)}
    return {"bundle": bundle,
            "keywords": list(getattr(m, "m_ValidKeywords", None) or getattr(m, "m_ShaderKeywords", None) or []),
            "textures": slots,
            "floats": {k: float(v) for k, v in _items(props.m_Floats)},
            "colors": {k: [float(c.r), float(c.g), float(c.b), float(c.a)] for k, c in _items(props.m_Colors)}}


def texel_count(mdef):
    return sum(s["size"][0] * s["size"][1] for s in mdef["textures"].values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cid", help="character id, e.g. a01 / g05 (an outfit a08_outfit1 uses a08)")
    ap.add_argument("--out", required=True, help="cache dir shared by all characters")
    ap.add_argument("--materials", default="", help="game material names to decode (comma separated)")
    ap.add_argument("--albedos", default="", help="albedo texture names; the materials using them are decoded")
    ap.add_argument("--all", action="store_true", help="decode every material found for the id")
    ap.add_argument("--force-exports", action="store_true",
                    help="rebuild the XPS / PMX export textures even when they exist")
    ap.add_argument("--glass-alpha", type=float, default=GLASS_ALPHA,
                    help="least alpha of premultiplied glass in the XPS / PMX textures (default %(default)s, env "
                         "ROE_GLASS_ALPHA - set that one for the exports, which run this script themselves)")
    ap.add_argument("--game", default=GAME)
    args = ap.parse_args()
    t0 = time.time()
    cid = re.match(r"[a-z]\d+|[a-z]_[a-z]+\d+", args.cid.lower()).group(0)
    fam = cid[0]
    bundles = inventory([args.game, CACHE])
    out_json = os.path.join(args.out, "%s.json" % cid)
    prev = {}
    if os.path.isfile(out_json):        # keep what earlier runs (the outfit, a suit, the nude base) decoded
        try:
            with open(out_json, encoding="utf-8") as fh:
                prev = json.load(fh)
        except (OSError, ValueError):
            prev = {}
    # the shared pieces stay in the cache once looked up: a later run for another suit of the character
    # (no Common_* albedos) must not drop the fm suit's ring / arm-hair definitions
    pieces = shared_pieces(s for s in args.albedos.split(",") if s) | set(prev.get("pieces", []))
    mat_names, tex_names = select_bundles(cid, bundles, (), pieces, manifest_deps(bundles))
    if not mat_names:
        sys.exit("no material bundles for %s" % cid)
    env = UnityPy.load(*[bundles[n] for n in mat_names + tex_names])

    # every Material of the selected bundles; a name defined twice keeps the one with bigger textures
    found, objects = {}, {}
    for path, bundle in env.files.items():
        base = os.path.basename(path)
        if not base.startswith(("chara_mat_", "accessory_")):
            continue
        for sf in getattr(bundle, "files", {}).values():
            for obj in getattr(sf, "objects", {}).values():
                if obj.type.name != "Material":
                    continue
                m = obj.read()
                mdef = material_def(m, base)
                old = found.get(m.m_Name)
                if old is None or texel_count(mdef) > texel_count(old):
                    found[m.m_Name], objects[m.m_Name] = mdef, m
                # two suits can name a piece alike with their own textures (g01 sleepwear / yoga
                # Rouffe_Underwear_obj001): each suit's own definition also as <name>@<suit>
                suit = re.match(r"accessory_components_pc_[a-z]\d+_suit_(.+)\.ab$", base)
                if suit:
                    found["%s@%s" % (m.m_Name, suit.group(1))] = mdef
    textures, same_name, by_source = {}, collections.defaultdict(list), {}
    for obj in env.objects:
        if obj.type.name == "Texture2D":
            try:
                name = obj.peek_name()          # the name only, not the pixel data
            except Exception:
                name = obj.read().m_Name
            textures.setdefault(name, obj)
            # grouped case-insensitively: the cache is a Windows folder, where k01 combat's
            # Clara_Eyemask_obj001_rgbx_Albedo and 2025xmas's Clara_EyeMask_... are ONE file -
            # whichever run came first gave the other suit its eye mask (black instead of teal)
            same_name[name.lower()].append(obj)
            by_source[(obj.assets_file.name.lower(), int(obj.path_id))] = obj

    overrides = {}
    face_tex = "pc_%s_hd_face_rgbx_albedo" % cid
    for name in textures:
        if name.lower() == face_tex:
            for mname in found:
                if re.fullmatch(r"pc_%s_nk_face" % fam, mname):
                    overrides[mname] = {"_BaseMap": name}

    wanted_mats = {s for s in args.materials.split(",") if s}
    wanted_alb = {s.lower() for s in args.albedos.split(",") if s}
    selected = [n for n, d in found.items() if args.all or n in wanted_mats or
                d["textures"].get("_BaseMap", {}).get("texture", "").lower() in wanted_alb]

    # a name shared by different textures (the g01 HD outfit's MGAC is called pc_g01_nk_body_rgbx_MGAC like
    # the nude body's own; HD / LD copies; two suits' pieces): a material gets the object its slot points
    # at, decoded as unique_texture_name() and set through overrides (identical copies keep the name).
    # Every material, not only the selected ones: a later build reads the overrides without a re-run
    digests = {}

    def digest(obj):
        key = (obj.assets_file.name.lower(), int(obj.path_id))
        if key not in digests:
            digests[key] = texture_digest(obj)
        return digests[key]

    for n in found:
        for key, slot in found[n]["textures"].items():
            objs = same_name.get(slot["texture"].lower(), [])
            ref = by_source.get(tuple(slot.get("source") or ()))
            if len(objs) < 2 or ref is None or key in overrides.get(n, {}):
                continue
            if len({digest(o) for o in objs}) > 1:
                uname = unique_texture_name(slot["texture"], digest(ref))
                overrides.setdefault(n, {})[key] = uname
                textures[uname] = ref

    tex_dir = os.path.join(args.out, "textures")
    os.makedirs(tex_dir, exist_ok=True)
    decoded, reused, missing = [], 0, []
    tex_info = {}
    need = {}
    for n in selected:
        override = overrides.get(n, {})
        for key, slot in found[n]["textures"].items():
            tname = override.get(key, slot["texture"])
            normal = key in NORMAL_SLOTS or slot["texture"].endswith("_Normal")
            need[tname] = need.get(tname, False) or normal
        for key, tname in override.items():
            need.setdefault(tname, False)
    for tname, normal in sorted(need.items()):
        obj = textures.get(tname)
        if obj is None:
            missing.append(tname)
            continue
        entry = {"file": "textures/%s.png" % tname}
        path = os.path.join(args.out, entry["file"])
        if normal:
            entry["normal_file"] = "textures/%s__nrm.png" % tname
        nrm_path = os.path.join(args.out, entry.get("normal_file", entry["file"]))
        if os.path.isfile(path) and os.path.isfile(nrm_path):
            reused += 1
        else:
            tex = obj.read()
            img = tex.image
            save_png(img, path)
            if normal:
                rgb, _converted = to_standard_normal(img)
                save_png(rgb, nrm_path)
            decoded.append(tname)
        tex_info[tname] = entry

    exports, export_errors, signatures = {}, {}, {}
    fresh = set(decoded)
    for n in selected:
        sources = {s["texture"] for s in found[n]["textures"].values()} | set(overrides.get(n, {}).values())
        # what the maps are made of: rebuilt when that changes (a slot the manifest resolved, the alpha rule);
        # maps from before the signatures count as made with the alpha factor 1
        signatures[n] = export_signature(found[n], sources, args.glass_alpha)
        made = prev.get("export_signatures", {}).get(n, json.dumps([sorted(sources), 1.0]))
        try:
            maps = export_maps(args.out, n, found[n], overrides.get(n, {}),
                               force=args.force_exports or bool(sources & fresh) or made != signatures[n],
                               glass_alpha=args.glass_alpha)
        except Exception as exc:          # a missing source texture: the material keeps albedo-only exports
            export_errors[n] = str(exc)
            signatures.pop(n)
            continue
        if maps:
            exports[n] = maps

    data = {"schema": 5,                 # 2: the suits' component bundles; 3: + shared accessory pieces by albedo;
            # 4: + texture sources, same-name textures told apart, <material>@<suit>; 5: + the manifest's texture
            # bundles (another character's textures), texture-less glass / glowing parts, export signatures
            "character": cid, "family": fam, "bundles": mat_names + tex_names, "materials": found,
            "selected": sorted(selected), "textures": tex_info, "overrides": overrides, "missing": missing,
            "exports": exports, "export_errors": export_errors, "export_signatures": signatures,
            "pieces": sorted(pieces)}    # Common_<piece> albedos looked up (hq_materials_blender.load_data)
    os.makedirs(args.out, exist_ok=True)
    for key in ("textures", "exports", "export_signatures"):
        for name, value in prev.get(key, {}).items():
            data[key].setdefault(name, value)
    data["selected"] = sorted(set(selected) | (set(prev.get("selected", [])) & set(found)))
    tmp = out_json + ".%d.part" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)
    print("ROE_HQ_DATA=" + json.dumps({"json": out_json, "materials": len(found), "selected": sorted(selected),
                                       "decoded": len(decoded), "reused": reused, "missing": missing,
                                       "overrides": overrides, "seconds": round(time.time() - t0, 1)},
                                      ensure_ascii=True))


if __name__ == "__main__":
    main()
