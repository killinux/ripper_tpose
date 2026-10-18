"""Rise of Eros PMX: the eye texture re-baked from the game's own eyeball shader, for MMD.

Why (2026-10-18, g05 "瞳孔修正"): the PMX eye (eye_portable) is one image baked from a flat sclera colour and the iris
pasted 1:1, so the pupil is 11 % of the iris; the game composes the eyeball from five textures every frame and draws
the pupil ~27-29 %, with a limbal ring, sclera veins / shading and the iris tint.  MMD cannot run that shader, so this
evaluates it head-on in the eyeball's UV square (the same formula as the ROE add-on's 2.6 button, roe_eye_blender.build,
with the cornea parallax at 0 and no lighting; the eyelid occlusion map stays - it lives on the eyeball UV in the game
too) and writes it as a texture the PMX's eye material points at.  In UV space the result equals a Cycles bake of the
2.6 network's base colour.

    python pmx_game_eye.py in.pmx out.pmx [--pupil 0] [--size 1024] [--cid g05] [--cache <hq cache>]

The texture goes to <out folder>\\textures\\<stem>_eye_game.png; out.pmx = in.pmx with eye_portable pointing at it,
nothing else changed.  Never writes over an existing file.  Needs the game's eye textures in the HQ material cache
(hq_cache.py); a family's iris missing there is fetched by the ROE add-on's 2.6 button or hq_material_data.py.
Plain Python + numpy + Pillow + the pmx module inside mmd_tools (no Blender).
"""
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mmd_physics"))
import cloth_collision_pmx as cc  # noqa: E402  (pmx module loader)
import hq_cache  # noqa: E402


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def load(path, color=True):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    return srgb_to_lin(a) if color else a


def sample(img, u, v):
    """Bilinear, clamp to edge (Blender's EXTEND); u, v in Blender UV (v up)."""
    h, w = img.shape[:2]
    x = np.clip(u * w - 0.5, 0, w - 1)
    y = np.clip((1.0 - v) * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bot = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return top * (1 - fy) + bot * fy


def smooth(v, lo, hi):
    t = np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def pick_eye_material(materials, cid, suit=None):
    """As roe_eye_blender.pick_eye_material: the character's own eye, a suit's, the family's pc_<x>_nk_eyes; never
    the low-detail battle eye (_ld_)."""
    eyes = [n for n, d in materials.items() if "_IrisAlbedoTex" in d.get("textures", {})]
    if not eyes:
        return None
    fam = cid[0]

    def score(n):
        low = n.lower()
        return ("_ld_" in low, not (suit and low.endswith("@" + suit)), ("pc_%s_" % cid) not in low,
                ("pc_%s_" % fam) not in low, "@" in low, len(n), n)
    return sorted(eyes, key=score)[0]


def game_eye(mdef, cache, size, pupil=0.0):
    """The game eyeball's base colour, head-on, as an sRGB uint8 image (size x size) over the eyeball UV square."""
    f, c, t = mdef.get("floats", {}), mdef.get("colors", {}), mdef["textures"]
    tex = lambda key: os.path.join(cache, "textures", t[key]["texture"] + ".png")  # noqa: E731
    for key in ("_IrisAlbedoTex", "_IrisMaskTex", "_ScleraAlbedoTex", "_EyeOcclusionMap"):
        if not os.path.isfile(tex(key)):
            raise SystemExit("missing game texture %s - click the ROE add-on's 2.6 button once on this family, or "
                             "run hq_material_data.py" % tex(key))
    u, v = np.meshgrid((np.arange(size) + 0.5) / size, 1.0 - (np.arange(size) + 0.5) / size)
    px, py = u - 0.5, v - 0.5
    pivot = f.get("_LimbusPivot", 0.3) * 0.5
    pivot2 = pivot * pivot
    width = f.get("_LimbusPivotWidth", 0.5) * 0.01
    fade = f.get("_LimbusFadeRatio", 1.0)
    d2 = (px * px + py * py) * fade + pivot2 * (1.0 - fade)
    in_start = (pivot2 - 0.0001 - width) * (1.0 - f.get("_LimbusSizeIris", 1.0))
    s_scl = f.get("_LimbusSizeSclera", 1.0)
    out_end = (pivot2 + width + 0.0001) * (1.0 - s_scl) + 0.25 * s_scl
    ring = np.clip(smooth(d2, in_start, pivot2 - width) + smooth(d2, out_end, pivot2 + width) - 1.0, 0, 1)[..., None]
    sinv = f.get("_IrisLimbusScaleInv", 1.0)
    iris_w = np.clip(sample(load(tex("_IrisMaskTex"), False), px * sinv + 0.5, py * sinv + 0.5)[..., :1], 0, 1)
    zoom = (f.get("_PupilMinSizeInv", 1.0) + (f.get("_PupilMaxSizeInv", 0.4) - f.get("_PupilMinSizeInv", 1.0)) * pupil) * sinv
    iris = sample(load(tex("_IrisAlbedoTex")), px * zoom + 0.5, py * zoom + 0.5)
    ic = c.get("_IrisColor", [1, 1, 1, 1])
    iris = iris * (1 - ic[3]) + iris * srgb_to_lin(np.array(ic[:3])) * ic[3]
    ssz = f.get("_ScleraSizeInv", 1.0)
    scl = sample(load(tex("_ScleraAlbedoTex")), px * ssz + 0.5, py * ssz + 0.5)
    sc = c.get("_ScleraColor", [1, 1, 1, 1])
    scl = scl * (1 - sc[3]) + scl * srgb_to_lin(np.array(sc[:3])) * sc[3]
    albedo = scl * (1 - iris_w) + iris * iris_w
    albedo = albedo * (1 - ring) + srgb_to_lin(np.array(c.get("_LimbusColor", [0.2, 0, 0, 1])[:3])) * ring
    occ = sample(load(tex("_EyeOcclusionMap"), False), u, v)[..., :1]
    amt = f.get("_ScleraOcclusionAmt", 0.0) * (1 - iris_w) + f.get("_IrisOcclusionAmt", 0.0) * iris_w
    return (lin_to_srgb(albedo * (1 - occ * amt)) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--pupil", type=float, default=0.0, help="0 = the size of the game's showcase videos (default)")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--cid", default="", help="character id (default: from the file name, pc_<cid>_...)")
    ap.add_argument("--cache", default="", help="HQ material cache (default: hq_cache.default_cache())")
    args = ap.parse_args()
    stem = os.path.splitext(os.path.basename(args.src))[0]
    cid = args.cid or (re.match(r"pc_([a-z]\d+)", stem.lower()) or [None, None])[1]
    if not cid:
        raise SystemExit("cannot tell the character id from %r - pass --cid" % stem)
    cache = args.cache or hq_cache.default_cache()
    data = json.load(open(os.path.join(cache, cid + ".json"), encoding="utf-8"))
    suit = re.match(r"pc_%s_(.+?)_hd" % cid, stem.lower())
    game = pick_eye_material(data["materials"], cid, suit.group(1) if suit else None)
    if game is None:
        raise SystemExit("no game eye material for %s in %s.json" % (cid, cid))
    out_dir = os.path.dirname(os.path.abspath(args.out))
    png = os.path.join(out_dir, "textures", re.sub(r"_(bustB|full|nude).*$", "", stem) + "_eye_game.png")
    for p in (args.out,):
        if os.path.exists(p):
            raise SystemExit("refusing to overwrite %s" % p)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    if not os.path.exists(png):
        Image.fromarray(game_eye(data["materials"][game], cache, args.size, args.pupil)).save(png)
    pmx = cc.load_pmx_module(cc.find_pmx_module())
    m = pmx.load(args.src)
    eyes = [mt for mt in m.materials if mt.name.startswith("eye_portable")]
    if len(eyes) != 1:
        raise SystemExit("expected one eye_portable material, found %d" % len(eyes))
    ti = eyes[0].texture
    if [mt.name for mt in m.materials if mt.texture == ti] == [eyes[0].name]:
        m.textures[ti].path = png
    else:
        t = pmx.Texture()
        t.path = png
        m.textures.append(t)
        eyes[0].texture = len(m.textures) - 1
    pmx.save(args.out, m, add_uv_count=m.header.additional_uvs)
    back = pmx.load(args.out)
    missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
    print("eye material %s (%s): %s; wrote %s (textures missing: %d)" % (
        game, cid, os.path.basename(png), args.out, len(missing)))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
