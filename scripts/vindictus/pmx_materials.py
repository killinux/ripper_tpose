"""Specular and shininess of a Vindictus PMX's materials by what they are in the game - plain Python, in place.

Convert to MMD 5 gives every material specular (1, 1, 1) and shininess 11.9: skin, cloth, metal and hair all
shine alike.  In MMD that is a broad white highlight; in Blender mmd_tools mixes 2 % of a glossy BSDF coloured by
the specular and with roughness 1 / shininess (0.08: nearly a mirror) - the skin looks oiled.

Each material is classed from the game material it was baked from (build_blend.py's build.log report next to
the .blend: kind + textures) and, for outfit materials, the metallic channel (B of the ARM / ORM map) measured
only inside this material's own UV triangles:
  skin  (kind skin: body, face, hands)                 -> SKIN   specular 0.15, shininess 4
  cloth (outfit, metallic share < 0.2, or no ARM map)  -> CLOTH  0.15, 4
  mixed (metallic share 0.2 - 0.5: lace with gold ...) -> MIXED  0.5, 8
  metal (metallic share >= 0.5: armour, jewellery)     -> kept as it is (1.0, 11.9)
  eyes, hair, brows / lashes, teeth, unknown           -> kept
Chosen by the user from rendered comparisons (2026-10-05).  Fiona_BaseBody (another build) has no report: its
skin is recognised by its texture names.  A material shared by two meshes was split by export_pmx into
"<name>_<part>" copies: the suffix is stripped to find the game material.

    python pmx_materials.py <id>.pmx --blend-dir <build_blend folder of <id>> [--dry-run]

export_pmx.py runs tune_file() on the PMX it has written when it knows the .blend (``--no-tune-materials``
skips it).  The PMX module's round trip is byte-identical: only these two fields and a comment line change.
"""
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)

VALUES = {"skin": (0.15, 4.0), "cloth": (0.15, 4.0), "mixed": (0.5, 8.0)}     # metal / keep: unchanged
METAL, MIXED = 0.5, 0.2
MARK = "materials by game kind: skin / cloth specular 0.15 shininess 4, mixed 0.5 / 8, metal kept (pmx_materials.py)"


def game_materials(blend_dir):
    """{game material: {kind, textures}} from build_blend's report in <blend_dir>/build.log ({} if none)."""
    path = os.path.join(blend_dir, "build.log")
    if not os.path.isfile(path):
        return {}
    raw = open(path, "rb").read()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    m = re.search(r"VINDICTUS_REPORT=(\{.*\})", text)
    return json.loads(m.group(1)).get("materials", {}) if m else {}


def _coverage(triangles, size):
    img = Image.new("L", size, 0)
    draw = ImageDraw.Draw(img)
    for tri in triangles:
        draw.polygon([(u * size[0], v * size[1]) for u, v in tri], fill=255)
    return np.asarray(img) > 0


def classify(model, game, textures_dir):
    """[(material, class, info)] for every material of ``model``."""
    out = []
    start = 0
    for mat in model.materials:
        n = mat.vertex_count // 3
        tris = model.faces[start:start + n]
        start += n
        tex = os.path.basename(model.textures[mat.texture].path) if mat.texture is not None and mat.texture >= 0 else ""
        name = re.sub(r"_baked\.png$", "", tex, flags=re.I)
        while name not in game and re.search(r"_[A-Za-z]+$", name):
            name = name.rsplit("_", 1)[0]
        info = dict(game.get(name, {}), game=name if name in game else "", texture=tex)
        kind = info.get("kind")
        low = tex.lower()
        if kind is None:                         # no report (Fiona_BaseBody): its maps' names
            kind = "skin" if re.search(r"basebody|hand_foot|body05|handfoot05|face01__", low) else \
                "cloth" if "inner" in low else "?"
        if "teeth" in name.lower() or "teeth" in low:
            kind = "teeth"
        if kind in ("pbr", "layered"):
            arm = next((t for t in info.get("textures", []) if re.search(r"_(ARM|ORM|MRA|RMA)\.png$", t, re.I)), "")
            share = None
            if arm and os.path.isfile(os.path.join(textures_dir, arm)):
                image = Image.open(os.path.join(textures_dir, arm)).convert("RGB")
                cover = _coverage([[tuple(model.vertices[i].uv) for i in t] for t in tris], image.size)
                if cover.any():
                    share = float((np.asarray(image)[..., 2][cover] > 127).mean())
            info["metal_share"] = None if share is None else round(share, 3)
            klass = "cloth" if share is None or share < MIXED else "mixed" if share < METAL else "metal"
        elif kind == "skin":
            klass = "skin"
        elif kind == "cloth":
            klass = "cloth"
        else:
            klass = "keep"
        out.append((mat, klass, info))
    return out


def tune_file(pmx_path, blend_dir, dry_run=False, pmx_module=None):
    """Classify and set the materials of ``pmx_path`` in place; returns {material name: (class, spec, shininess)}."""
    pmx = bust_physics.load_pmx_module(pmx_module)
    model = pmx.load(pmx_path)
    classes = classify(model, game_materials(blend_dir), os.path.join(blend_dir, "textures"))
    report = {}
    for mat, klass, info in classes:
        if klass in VALUES:
            spec, shin = VALUES[klass]
            mat.specular = [spec, spec, spec]
            mat.shininess = shin
        report[mat.name] = (klass, round(mat.specular[0], 3), round(mat.shininess, 2), info.get("metal_share"))
    if dry_run:
        return report
    if MARK not in (model.comment or ""):
        model.comment = ((model.comment or "").rstrip() + "\r\n" + MARK).lstrip()
        model.comment_e = ((model.comment_e or "").rstrip() + "\r\n" + MARK).lstrip()
    temporary = pmx_path + ".mat.tmp"
    pmx.save(temporary, model, add_uv_count=model.header.additional_uvs)
    os.replace(temporary, pmx_path)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pmx")
    ap.add_argument("--blend-dir", required=True, help="build_blend.py's folder of the model (build.log + textures)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = tune_file(args.pmx, args.blend_dir, args.dry_run, args.pmx_module)
    for name, (klass, spec, shin, share) in report.items():
        print("%-6s spec %.2f shininess %5.1f %s %s" % (klass, spec, shin, "" if share is None else "metal %.2f" % share, name))
    print("dry run, nothing written" if args.dry_run else "wrote %s" % args.pmx)


if __name__ == "__main__":
    sys.exit(main())
