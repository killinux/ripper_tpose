"""The 衣服非表示 switch for a PMX that carries an outfit and, underneath, a whole nude body as materials of its own -
the structure the 爆衣 add-on (scripts/blender_addons/clothes_burst) and burst_pmx_blender.py work on: they then only
add the fragments, and MMD can strip the model with one slider.

What it sets (the same design as the ROE full versions, scripts/riseoferos/pmx_two_bodies.py):
  - the nude body's materials: alpha 0 in the file (and edge alpha 0) - invisible while dressed;
  - 衣服非表示_材質 (material morph): the outfit's alpha x 0;
  - 裸体形状 (material morph): the outfit's own skin pieces (--skin) alpha x 0, the nude body's alpha added back -
    the body is swapped, so nothing of the dressed model's partial skin z-fights the nude body;
  - 衣服非表示 (group): both, one slider undresses;
  - the three morphs go into the 表情 display frame.
The nude body must already be in the file (put in before the PMX export, e.g. scripts/stellarblade: a second body mesh
on the same armature).  A PMX that has 衣服非表示_材質 or 裸体形状 already is left alone ("already").

  python pmx_nude_switch.py <in.pmx> --outfit <names> --nude <names> [--skin <names>] [--out <pmx>]
                            [--pmx-module <mmd_tools/core/pmx/__init__.py>]

<names> = material names, comma separated, shell-style wildcards allowed (MI_P_EVE_09_Metal*); each must match.
Written next to the input by default (<stem>_switch.pmx); --out in another folder copies the textures it uses there.
Needs only Python and mmd_tools' stand-alone PMX module (no Blender, no numpy).  Prints PMX_NUDE_SWITCH=<json>.
"""
import argparse
import fnmatch
import glob
import importlib.util
import json
import logging
import os
import shutil
import sys

BODY = "裸体形状"
OUTFIT = "衣服非表示_材質"
GROUP = "衣服非表示"
OTHER = 4           # morph panel: その他


def pmx_module(path=None):
    """mmd_tools' stand-alone PMX reader / writer (core/pmx/__init__.py), loaded without Blender."""
    if not path:
        root = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
        for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits:
                path = hits[0]
                break
    if not path or not os.path.isfile(path):
        raise SystemExit("mmd_tools' core/pmx/__init__.py not found; pass --pmx-module")
    spec = importlib.util.spec_from_file_location("mmd_tools_pmx", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    logging.getLogger().setLevel(logging.WARNING)
    return mod


def pick(model, patterns, what):
    """Material indices matching the comma separated names / wildcards; every pattern must match something."""
    names = [m.name for m in model.materials]
    out = []
    for pat in [p.strip() for p in (patterns or "").split(",") if p.strip()]:
        hit = [k for k, n in enumerate(names) if fnmatch.fnmatchcase(n, pat)]
        if not hit:
            raise SystemExit("%s: no material matches %r (materials: %s)" % (what, pat, ", ".join(names)))
        out += [k for k in hit if k not in out]
    return out


def _offset(pmx, index, mode, alpha=0.0, edge=0.0):
    o = pmx.MaterialMorphOffset()
    o.index, o.offset_type = index, mode
    if mode == 0:       # multiply: alpha x 0, the rest x 1
        o.diffuse_offset, o.specular_offset, o.shininess_offset = [1.0, 1.0, 1.0, 0.0], [1.0] * 3, 1.0
        o.ambient_offset, o.edge_color_offset, o.edge_size_offset = [1.0] * 3, [1.0, 1.0, 1.0, 0.0], 1.0
        o.texture_factor = o.sphere_texture_factor = o.toon_texture_factor = [1.0] * 4
    else:               # add: the alpha the file took away, back
        o.diffuse_offset, o.specular_offset, o.shininess_offset = [0.0, 0.0, 0.0, alpha], [0.0] * 3, 0.0
        o.ambient_offset, o.edge_color_offset, o.edge_size_offset = [0.0] * 3, [0.0, 0.0, 0.0, edge], 0.0
        o.texture_factor = o.sphere_texture_factor = o.toon_texture_factor = [0.0] * 4
    return o


def add_switch(pmx, model, outfit, nude, skin=()):
    """Switch morphs on model (in place).  outfit / nude / skin = material indices.  Returns a report."""
    names = {m.name for m in model.morphs}
    if OUTFIT in names or BODY in names:
        return {"status": "already"}
    clash = (set(outfit) & set(nude)) | (set(outfit) & set(skin)) | (set(nude) & set(skin))
    if clash:
        return {"status": "a material is in two lists: %s" % sorted(model.materials[k].name for k in clash)}
    if not outfit or not nude:
        return {"status": "needs --outfit and --nude"}
    mats = model.materials
    alpha = {k: float(mats[k].diffuse[3]) for k in nude}
    edge = {k: float(mats[k].edge_color[3]) for k in nude}
    for k in nude:
        mats[k].diffuse = list(mats[k].diffuse[:3]) + [0.0]
        mats[k].edge_color = list(mats[k].edge_color[:3]) + [0.0]
    hide = pmx.MaterialMorph(OUTFIT, "Outfit hide (material)", OTHER)
    hide.offsets = [_offset(pmx, k, 0) for k in outfit]
    swap = pmx.MaterialMorph(BODY, "Nude body", OTHER)
    swap.offsets = [_offset(pmx, k, 0) for k in skin] + [_offset(pmx, k, 1, alpha[k], edge[k]) for k in nude]
    first = len(model.morphs)
    model.morphs += [hide, swap]
    group = pmx.GroupMorph(GROUP, "Outfit hide", OTHER)
    for i in (first, first + 1):
        o = pmx.GroupMorphOffset()
        o.morph, o.factor = i, 1.0
        group.offsets.append(o)
    model.morphs.append(group)
    frame = next((d for d in model.display if d.isSpecial and d.name in ("表情", "Exp")), None) or \
        next((d for d in model.display if d.name in ("表情", "Exp")), None)
    if frame is not None:
        frame.data += [(1, i) for i in (first + 2, first, first + 1)]
    return {"status": "ok", "outfit": [mats[k].name for k in outfit], "nude": [mats[k].name for k in nude],
            "skin": [mats[k].name for k in skin], "morphs": [OUTFIT, BODY, GROUP],
            "display_frame": frame.name if frame is not None else None}


def save(pmx, model, src, out):
    """Write model to out.  Texture paths are written relative to out's folder, so every texture outside that folder
    (the source PMX's when out is elsewhere - on another drive the path would be written absolute - or another PMX's
    copied in) is copied under it first; a different file of the same name gets a _2, _3 ... name.  Read back."""
    out = os.path.abspath(out)
    folder = os.path.dirname(out)
    src_dir = os.path.dirname(os.path.abspath(src))
    os.makedirs(folder, exist_ok=True)
    copied = 0
    def rel_to(path, start):
        try:
            return os.path.relpath(path, start)
        except ValueError:                            # another drive
            return None

    for tex in model.textures:
        path = tex.path if os.path.isabs(tex.path) else os.path.join(src_dir, tex.path)
        inside = rel_to(path, folder)
        if not os.path.isfile(path) or (inside is not None and not inside.startswith("..")):
            continue                                  # missing, or under the output folder already
        rel = rel_to(path, src_dir)
        if rel is None or rel.startswith("..") or os.path.isabs(rel):
            rel = os.path.join("textures", os.path.basename(path))
        dest = os.path.join(folder, rel)
        stem, ext = os.path.splitext(dest)
        n = 2
        while os.path.isfile(dest) and os.path.getsize(dest) != os.path.getsize(path):
            dest = "%s_%d%s" % (stem, n, ext)
            n += 1
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.isfile(dest):
            shutil.copy2(path, dest)
            copied += 1
        tex.path = dest
    tmp = out[:-4] + ".switch.tmp.pmx"
    pmx.save(tmp, model, add_uv_count=getattr(model.header, "additional_uvs", 0))
    check = pmx.load(tmp)
    if len(check.materials) != len(model.materials) or len(check.morphs) != len(model.morphs):
        os.remove(tmp)
        raise SystemExit("written file did not read back right")
    os.replace(tmp, out)
    return copied


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pmx")
    ap.add_argument("--outfit", required=True, help="materials 衣服非表示 hides")
    ap.add_argument("--nude", required=True, help="materials of the nude body (alpha 0 until 裸体形状)")
    ap.add_argument("--skin", default="", help="the outfit's own skin pieces, hidden when the nude body shows")
    ap.add_argument("--out", default="")
    ap.add_argument("--pmx-module", default="")
    a = ap.parse_args()
    pmx = pmx_module(a.pmx_module)
    model = pmx.load(a.pmx)
    report = add_switch(pmx, model, pick(model, a.outfit, "--outfit"), pick(model, a.nude, "--nude"),
                        pick(model, a.skin, "--skin"))
    report["pmx"] = os.path.abspath(a.pmx)
    if report["status"] == "ok":
        out = a.out or a.pmx[:-4] + "_switch.pmx"
        report["textures_copied"] = save(pmx, model, a.pmx, out)
        report["written"] = os.path.abspath(out)
    print("PMX_NUDE_SWITCH=" + json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] in ("ok", "already") else 1


if __name__ == "__main__":
    sys.exit(main())
