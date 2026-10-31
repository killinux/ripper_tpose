# -*- coding: utf-8 -*-
"""Inside Blender (the PMX exporters import it): make a written PMX's texture alpha say what the source drew.

MMD multiplies every texture's alpha into its material, so:

  * a texture that only OPAQUE source materials use gets alpha 1 - game textures keep spec / SSS / AO masks in
    alpha, and a PMX written with them has see-through faces and bodies (memory note "texture alpha = masks";
    Taimanin's fill_opaque_alpha in scripts/stellarblade/export_pmx_blender.py follows the same rule);
  * a texture that only alpha-CLIPPED source materials use gets its alpha remapped to the cut the game makes: 0 below
    clip - softness, 1 above clip + softness, a ramp between (soft edges).  Stellar Blade Raven's long hair: alpha
    median 0.25 against a clip of 0.333, so MMD drew it thin and see-through;
  * textures that blended materials use (hair cards drawn hashed, tights, shells) are left alone, and so is any
    texture shared with one.

Filling an opaque texture would also hide an EMPTY bake (texels the bake never wrote are alpha 0; filled they draw
black - Taimanin's NARAKA Matari, 10-31), so before the fill the share of each opaque material's triangles whose
texture alpha at the centroid is below 0.5 is measured and reported as "holes" when it is above HOLE_REPORT.

Only files inside the PMX's own folder are changed (mmd_tools' export copies the textures there).

    clip, opaque = source_alpha_modes()          # before the conversion touches the materials
    ... export the PMX ...
    lines = fix_texture_alpha(pmx_path, clip, opaque)
"""
import os
import re

import bpy
import numpy as np

CLIP_SOFTNESS = 0.05
HOLE_REPORT = 0.02


def source_alpha_modes():
    """({material: clip threshold} of the CLIP materials, {names of the OPAQUE ones}) of the open file."""
    clip = {m.name: round(m.alpha_threshold, 4) for m in bpy.data.materials if m.blend_method == "CLIP"}
    opaque = {m.name for m in bpy.data.materials if m.blend_method == "OPAQUE"}
    return clip, opaque


def fix_texture_alpha(pmx_path, clip, opaque, softness=CLIP_SOFTNESS):
    """Apply the rules above to the textures of ``pmx_path``.  A material named <source>_gloss (the Stellar Blade
    glossy split) counts as its source.  Returns one line per file changed."""
    from mmd_tools.core import pmx as pmx_file
    model = pmx_file.load(pmx_path)
    folder = os.path.normcase(os.path.dirname(os.path.abspath(pmx_path)))
    users, tris = {}, {}
    uv = np.array([v.uv for v in model.vertices], dtype=np.float64)
    faces = np.array(model.faces, dtype=np.int64).reshape(-1, 3)
    start = 0
    for mat in model.materials:
        count = mat.vertex_count // 3
        if mat.texture is not None and mat.texture >= 0:
            users.setdefault(mat.texture, []).append(mat.name)
            tris.setdefault(mat.texture, []).append((mat.name, uv[faces[start:start + count]].mean(axis=1)))
        start += count
    done = []
    for index, names in sorted(users.items()):
        bases = [re.sub(r"_gloss$", "", n) for n in names]
        thresholds = [clip.get(b) for b in bases]
        solid = all(b in opaque for b in bases)
        if any(t is None for t in thresholds) and not solid:
            continue                                 # drawn by a blended material too
        path = model.textures[index].path
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(pmx_path), path)
        if not os.path.normcase(os.path.abspath(path)).startswith(folder) or not os.path.isfile(path):
            continue
        image = bpy.data.images.load(path, check_existing=False)
        try:
            if image.channels < 4:
                continue
            px = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(px)
            alpha = px[3::4]
            if solid:
                if float(alpha.min()) >= 1.0:
                    continue
                line = "%s: opaque (%s), alpha min %.2f -> 1" % (os.path.basename(path), ", ".join(names),
                                                                 float(alpha.min()))
                w, h = image.size
                grid = alpha.reshape(h, w)                   # Blender rows run bottom-up, PMX v top-down
                for mat_name, centres in tris.get(index, []):
                    x = np.floor((centres[:, 0] % 1.0) * w).astype(int).clip(0, w - 1)
                    y = np.floor((1.0 - centres[:, 1] % 1.0) * h).astype(int).clip(0, h - 1)
                    holes = float((grid[y, x] < 0.5).mean()) if len(centres) else 0.0
                    if holes > HOLE_REPORT:
                        line += "; HOLES %s %.0f%% of triangles (an empty bake?)" % (mat_name, 100 * holes)
                px[3::4] = 1.0
            else:
                cut = min(thresholds)
                before = float(np.median(alpha[alpha > 0.02])) if np.any(alpha > 0.02) else 0.0
                line = "%s: clip %.3f (%s), alpha median %.2f -> cut" % (os.path.basename(path), cut,
                                                                          ", ".join(names), before)
                px[3::4] = np.clip((alpha - (cut - softness)) / (2.0 * softness), 0.0, 1.0)
            image.pixels.foreach_set(px)
            image.filepath_raw = path
            image.file_format = "PNG"
            image.save()
            done.append(line)
        finally:
            bpy.data.images.remove(image)
    return done
