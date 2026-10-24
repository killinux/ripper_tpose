"""Stellar Blade outfit materials as the game has them: read the outfit's material instances (CUE4Parse JSON of
MA_CH_Standard_Ver03 instances) and write

  <out>/materials.json      per material: its maps (base colour, ORM, normal, masks, emissive, pattern normal) and
                            the parameters that matter outside the engine - what hq_materials_blender.py wires
  <out>/<map>_pmx.png       per material, the colour MMD gets (one texture per material): base colour x AO (ORM red,
                            in linear light) plus the emissive colour where the emissive mask is lit - full size

The archived outfit .blend (validate_eve.py / package_outfits.py) wires the base colour only; its textures\\extra\\
holds the outfit's own _N / _ORM / _M / _E maps unwired.  This reads which map is which from the game instead of
guessing from file names.

    python hq_materials.py --mi-json <dir with MI_*.json> --textures <outfit textures dir> --out <dir>
        [--pattern Knitted_N=<png>]          # shared pattern normals the instances name (not in the outfit folder)

Plain Python (numpy + Pillow).  The JSON comes from CUE4Parse.CLI:
    cue4parse.exe -i <SB\\Content\\Paks> -g GAME_UE4_26 -m StellarBlade_1.1.0.usmap -f json -o <dir>
        -p "SB/Content/DLC_2/Art/Character/PC/<package>/Mat/*"

An instance of the eye material (parent M_EyeRefractive) in the folder is not an outfit material: its values and
textures go to materials.json "eyes" (by instance name) and "eye" (the in-game one, not a cinematic _Cin / special
_subiris / _Die variant) - eye_material.py: iris size, tint, brightness, the instance's own iris / sclera textures
(found under --textures, else --eye-textures: the game's shared eye textures, which an instance that sets no
IrisColor / ScleraColor uses).  hq_materials_blender.py and export_pmx_blender.py --hq-materials rebuild the eye from
it; without one they use Eve's (CH_P_EVE_Head's MI_EyeRefractive1).  Other characters keep their eye instance in
their head / face folder (e.g. NPC/CH_NPC_01/Materials/MI_CH_NPC_Lilly_Eyes): export its JSON into --mi-json too.
"""
import argparse
import glob
import json
import os

import numpy as np
from PIL import Image

import eye_material

Image.MAX_IMAGE_PIXELS = None
CHANNELS = "RGBA"


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def channel_of(vec):
    """a mask-channel selector vector (R G B A weights, one of them 1) -> 'R' / 'G' / ..."""
    if not vec:
        return None
    vals = [vec.get(k, 0.0) for k in "RGBA"]
    return CHANNELS[int(np.argmax(vals))] if max(vals) > 0.5 else None


def read_instance(path):
    """{name, parent, scalars, vectors, textures, switches, blend} of one material instance JSON"""
    for e in json.load(open(path, encoding="utf-8-sig")):
        if not e.get("Type", "").startswith("MaterialInstance"):
            continue
        p = e["Properties"]
        return {
            "name": e["Name"],
            "parent": ((p.get("Parent") or {}).get("ObjectPath") or "").split("/")[-1].split(".")[0],
            "scalars": {s["ParameterInfo"]["Name"]: s["ParameterValue"] for s in p.get("ScalarParameterValues", [])},
            "vectors": {s["ParameterInfo"]["Name"]: s["ParameterValue"] for s in p.get("VectorParameterValues", [])},
            "textures": {s["ParameterInfo"]["Name"]: s["ParameterValue"]["ObjectPath"].split("/")[-1].split(".")[0]
                         for s in p.get("TextureParameterValues", [])},
            "switches": {s["ParameterInfo"]["Name"]: s["Value"]
                         for s in (p.get("StaticParameters") or {}).get("StaticSwitchParameters", [])},
            "blend": (p.get("BasePropertyOverrides") or {}).get("BlendMode", "EBlendMode::BLEND_Opaque").split("::")[-1],
        }
    return None


def find_texture(name, roots):
    for root in roots:
        for sub in ("", "extra"):
            path = os.path.join(root, sub, name + ".png")
            if os.path.isfile(path):
                return os.path.abspath(path)
    return None


# MA_CH_Standard_Ver03 defaults for what the instances leave out (its CachedExpressionData)
DEFAULTS = {"Metallic": 1.0, "Roughness Min": 0.0, "Roughness Max": 1.0, "ClearCoatRoughness Min": 0.0,
            "Fuzz_01_INTENSITY": 0.0, "EmissivePower": 0.0, "Pattern01_Tiling": 8.0, "Pattern01_NormalIntensity": 0.0,
            "Pattern01_RoughnessIntencity": 0.0}


def describe(mi, roots, patterns):
    s = dict(DEFAULTS)
    s.update(mi["scalars"])
    t, v = mi["textures"], mi["vectors"]
    tex = {}
    for key, param in (("base", "Basecolor"), ("orm", "ORM"), ("normal", "Baked NormalMap"), ("emissive", "Emissive"),
                       ("fuzz_mask", "FuzzMask"), ("layer_mask", "MaterialLayerMask"),
                       ("shading_mask", "ShadingModelMask"), ("pattern_normal", "Pattern01_Normal")):
        name = t.get(param)
        if not name or name in ("FlatNormal",):
            continue
        tex[key] = patterns.get(name) or find_texture(name, roots)
        if tex[key] is None:
            tex[key] = "MISSING:" + name
    d = {"name": mi["name"], "parent": mi["parent"], "blend": mi["blend"], "textures": tex,
         "metallic": s["Metallic"], "roughness_min": s["Roughness Min"], "roughness_max": s["Roughness Max"]}
    if mi["switches"].get("UesFuzzLayer") and "fuzz_mask" in tex:
        col = v.get("FUZZ_01_COLOR", {"R": 1, "G": 1, "B": 1})
        d["fuzz"] = {"channel": channel_of(v.get("Fuzz_01_CH")) or "R", "intensity": s["Fuzz_01_INTENSITY"],
                     "color": [col["R"], col["G"], col["B"]]}
    if mi["switches"].get("Ues_ML_MetallicClearCoat(Clearcoat)") and "layer_mask" in tex:
        d["clearcoat"] = {"channel": channel_of(v.get("Shading_ClearCoat_CH") or v.get("ML_MetallicClearCoat_CH")) or "R",
                          "roughness": s["ClearCoatRoughness Min"]}
    col = v.get("EmissiveColor") or {"R": 0.0, "G": 0.0, "B": 0.0}
    if "emissive" in tex and s["EmissivePower"] > 0 and max(col["R"], col["G"], col["B"]) > 0:
        # the master lights ONE channel of the map (Emissive_CH, red by default in Ver03 / Cloth_Ver02) x EmissiveColor x
        # EmissivePower; with the master's defaults (power 0, black) nothing glows in the game
        d["emissive"] = {"channel": channel_of(v.get("Emissive_CH")) or "R", "color": [col["R"], col["G"], col["B"]],
                         "power": s["EmissivePower"]}
    if "pattern_normal" in tex and s["Pattern01_NormalIntensity"] > 0:
        d["pattern"] = {"tiling": s["Pattern01_Tiling"], "normal_intensity": s["Pattern01_NormalIntensity"],
                        "roughness_intensity": s["Pattern01_RoughnessIntencity"]}
    return d


def load(path, mode):
    im = Image.open(path)
    return np.asarray(im.convert(mode), dtype=np.float32) / 255.0


def pmx_colour(d, out_dir):
    """base colour x AO (+ emissive), linear light, full size; alpha kept for masked materials"""
    tex = d["textures"]
    base_path = tex.get("base")
    if not base_path or base_path.startswith("MISSING"):
        return None
    rgba = load(base_path, "RGBA")
    lin = srgb_to_linear(rgba[..., :3])
    report = {"size": rgba.shape[1]}
    orm = tex.get("orm")
    if orm and not orm.startswith("MISSING"):
        ao = load(orm, "RGB")[..., 0]
        if ao.shape != lin.shape[:2]:
            ao = np.asarray(Image.fromarray((ao * 255).astype(np.uint8)).resize(lin.shape[1::-1], Image.BILINEAR),
                            dtype=np.float32) / 255.0
        lin = lin * ao[..., None]
        report["ao_mean"] = round(float(ao.mean()), 3)
    em = tex.get("emissive")
    if em and not em.startswith("MISSING") and "emissive" in d:
        mask = load(em, "RGBA")[..., CHANNELS.index(d["emissive"].get("channel", "R"))]
        if mask.shape != lin.shape[:2]:
            mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(lin.shape[1::-1], Image.BILINEAR),
                              dtype=np.float32) / 255.0
        col = np.array(d["emissive"]["color"], dtype=np.float32)
        lin = lin + mask[..., None] * col[None, None, :]       # MMD has no glow: the lit part at full colour
        report["emissive_px"] = int((mask > 0.1).sum())
    out = np.concatenate([linear_to_srgb(lin), rgba[..., 3:]], axis=2)
    path = os.path.join(out_dir, os.path.splitext(os.path.basename(base_path))[0] + "_pmx.png")
    keep_alpha = d["blend"] in ("BLEND_Masked", "BLEND_Translucent") or rgba[..., 3].min() < 0.99
    img = Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")
    (img if keep_alpha else img.convert("RGB")).save(path, optimize=False)
    report["file"] = path
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mi-json", required=True, help="folder with the outfit's MI_*.json (searched recursively)")
    ap.add_argument("--textures", required=True, action="append", help="texture folder(s) (and their extra\\)")
    ap.add_argument("--pattern", action="append", default=[], help="NAME=png for shared pattern normals")
    ap.add_argument("--eye-textures", action="append", default=[],
                    help="folder(s) with the game's shared eye textures, searched after --textures for the eye "
                         "instance's (default: %s)" % eye_material.SHARED_TEXTURES)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eye_roots = args.textures + (args.eye_textures or [eye_material.SHARED_TEXTURES])
    os.makedirs(args.out, exist_ok=True)
    patterns = dict(p.split("=", 1) for p in args.pattern)
    patterns = {k: os.path.abspath(v) for k, v in patterns.items()}
    mats, eyes = {}, []
    for path in sorted(glob.glob(os.path.join(args.mi_json, "**", "MI_*.json"), recursive=True)):
        mi = read_instance(path)
        if mi is None:
            continue
        eye = eye_material.eye_from_instance(mi["name"], mi["parent"], mi["scalars"], mi["vectors"], mi["textures"])
        if eye is not None:
            eye["file"] = os.path.abspath(path)
            eye["textures"] = {k: eye_material.find_texture_file(name, eye_roots) or "MISSING:" + name
                               for k, name in eye["textures"].items()}
            eyes.append(eye)
            print("%-28s %s: eye, %s; %s" % (mi["name"], mi["parent"], eye_material.describe(eye["params"]),
                                             ", ".join(os.path.basename(v) for v in eye["textures"].values())))
            continue
        d = describe(mi, args.textures, patterns)
        d["pmx"] = pmx_colour(d, args.out)
        mats[mi["name"]] = d
        print("%-28s %s: %s%s" % (mi["name"], mi["parent"], ", ".join(sorted(d["textures"])),
                                  "" if d["pmx"] is None else " -> %s" % os.path.basename(d["pmx"]["file"])))
    doc = {"materials": mats}
    if eyes:
        # the in-game one: not a cinematic (_Cin), special (_subiris) or dead (_Die) variant
        plain = [e for e in eyes if not any(t in e["material"].lower() for t in ("_cin", "_subiris", "_die"))]
        doc["eye"] = (plain or eyes)[0]
        doc["eyes"] = {e["material"]: e for e in eyes}
    json.dump(doc, open(os.path.join(args.out, "materials.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", os.path.join(args.out, "materials.json"), "(eye: %s)" % (doc["eye"]["material"] if eyes else
                                                                           "none - Eve's values"))


if __name__ == "__main__":
    main()
