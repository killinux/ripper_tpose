"""List and export Virt-A-Mate looks and clothing to .blend (+ preview PNG).

Python side of ``export_vam_models.ps1``.  Sub-commands:

  list     enumerate looks (Person atoms in scenes, appearance presets),
           clothing items and hair items across AddonPackages + Custom
  export   assemble the selected items (morphed body + skin textures +
           clothing, or a single clothing item), then run Blender headless
           to build materials, pack textures, render a preview and save
  prepare  build the cache (base meshes, character table, built-in morphs)
           up front instead of on first use

Usage examples:
  python export_vam_models.py list
  python export_vam_models.py list --kind clothing --filter cheongsam
  python export_vam_models.py export --only VAMSOY.Angela.1~Angela~Person
  python export_vam_models.py export --index 3 5 --format blend,glb --no-preview

Everything the Blender worker needs is written to
``<out>/<kind>/<key>/model.json`` + ``model.npz`` + ``_textures/`` first, so a
failed Blender run can be re-driven by hand.
"""

import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vam_lib as vl  # noqa: E402

RESULT_MARKER = re.compile(r"VAM_EXPORT=(\{.*?\})\s*(?:\n|$)", re.S)
DEFAULT_GAME_ROOT = r"E:\tools\vam\vam1.22\vam1.22\1.22"
DEFAULT_OUT_ROOT = r"D:\vam_exports"
DEFAULT_BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"

SKIN_REGIONS = ("face", "torso", "limbs", "genitals")
SKIN_KINDS = {"Diffuse": "diffuse", "Specular": "specular", "Gloss": "gloss",
              "Normal": "normal", "Decal": "decal"}
EYE_MATERIALS = {"Irises": "irises", "Sclera": "sclera", "Pupils": "pupils",
                 "Lacrimals": "lacrimals"}
GLASS_MATERIALS = ("Cornea", "EyeReflection", "Tear")
MOUTH_MATERIALS = {"Teeth": "teeth", "Gums": "mouth", "Tongue": "tongue",
                   "InnerMouth": "mouth"}
TEXTURE_KEYS = {"customTexture_MainTex": "diffuse", "customTexture_BumpMap": "normal",
                "customTexture_SpecTex": "specular", "customTexture_GlossTex": "gloss",
                "customTexture_AlphaTex": "alpha", "customTexture_DecalTex": "decal"}


class Context:
    def __init__(self, args):
        self.game_root = args.game_root
        self.out_root = args.out
        self.index = vl.PackageIndex(args.game_root)
        self.catalog = vl.Catalog(self.index)
        studio = vl.AssetStudio(args.assetstudio, args.game_root)
        self.cache = vl.VamCache(os.path.join(args.out, "_cache"), studio, log=log)


def log(message):
    print(message, flush=True)


# --------------------------------------------------------------------------
# Texture helpers
# --------------------------------------------------------------------------

def image_has_alpha(path, size_limit=48 * 1024 * 1024):
    """True when a PNG/TGA actually carries non-opaque pixels (PIL optional)."""
    try:
        from PIL import Image
    except ImportError:
        return path.lower().endswith((".png", ".tga"))
    try:
        if os.path.getsize(path) > size_limit:
            return False
        with Image.open(path) as image:
            if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
                return False
            alpha = image.convert("RGBA").getchannel("A")
            low, _high = alpha.getextrema()
            return low < 250
    except (OSError, ValueError):
        return False


EMPTY_URLS = ("", "null", "none")


def resolve_item_texture(ctx, url, package, item_dir):
    """Clothing texture urls: SELF:/, Pkg:/, ./relative, bare name, Custom/..."""
    if not url or str(url).strip().lower() in EMPTY_URLS:
        return None, None
    url = str(url).replace("\\", "/")
    if ":/" in url:
        return ctx.index.resolve(url, package)
    if url.startswith("./") or "/" not in url:
        member = posixpath.normpath(posixpath.join(item_dir, url))
        real = package.find(member)
        if real:
            return package, real
    return ctx.index.resolve(url, package)


# --------------------------------------------------------------------------
# Clothing
# --------------------------------------------------------------------------

def load_item(ctx, package, vam_member):
    """(DazMesh, vaj dict, item_dir) for a clothing ``.vam`` member."""
    base = vam_member[:-4]
    vab = package.find(base + ".vab")
    if vab is None:
        raise FileNotFoundError("no .vab beside %s" % vam_member)
    mesh = vl.parse_dazmesh_vab(package.read(vab))
    vaj_member = package.find(base + ".vaj")
    vaj = vl.lenient_json_loads(package.read(vaj_member)) if vaj_member else {}
    return mesh, vaj, posixpath.dirname(vam_member)


def _material_storables(vaj):
    return {s["id"]: s for s in vaj.get("storables", [])
            if isinstance(s, dict) and "Material" in str(s.get("id", ""))}


def _storable_for_material(storables, index, mat_name):
    for sid, storable in storables.items():
        if sid.endswith("Material" + mat_name):
            return storable
    combined = []
    for sid, storable in storables.items():
        match = re.search(r"MaterialCombined(\d*)$", sid)
        if match:
            combined.append((int(match.group(1) or 0), storable))
    combined.sort(key=lambda pair: pair[0])
    if combined:
        if len(combined) == 1:
            return combined[0][1]
        if index < len(combined):
            return combined[index][1]
    return next(iter(storables.values()), {})


def clothing_materials(ctx, mesh, vaj, package, item_dir, bundle, overrides=None,
                       missing=None):
    """Material specs for a clothing mesh; ``overrides`` are scene storables."""
    storables = _material_storables(vaj)
    overrides = overrides or {}
    specs = []
    hidden = []
    for index, mat_name in enumerate(mesh.material_names):
        storable = dict(_storable_for_material(storables, index, mat_name))
        for sid, scene_storable in overrides.items():
            if sid in storables or (storable.get("id") and sid == storable.get("id")):
                storable.update(scene_storable)
        spec = vl.material_spec(mat_name)
        for key, role in TEXTURE_KEYS.items():
            url = storable.get(key)
            if not url or str(url).strip().lower() in EMPTY_URLS:
                continue
            tex_pkg, member = resolve_item_texture(ctx, url, package, item_dir)
            if member is None:
                if missing is not None:
                    missing.append("%s: %s" % (mat_name, url))
                continue
            spec[role] = bundle.add_texture(tex_pkg, member)
        spec["color"] = vl.storable_color(storable.get("Diffuse Color"))
        spec["alphaAdjust"] = vl.as_float(storable.get("Alpha Adjust"), 0.0)
        spec["transparent"] = bool(spec["alpha"]) or spec["alphaAdjust"] < -0.01
        if not spec["alpha"] and spec["diffuse"]:
            diffuse_path = os.path.join(bundle.texture_dir, spec["diffuse"])
            if image_has_alpha(diffuse_path):
                spec["transparent"] = True
        if vl.as_bool(storable.get("hideMaterial")):
            hidden.append(index)
        specs.append(spec)
    return specs, hidden


SKIN_LAYER_MIN_FRACTION = 0.6
SKIN_LAYER_PUSH = 0.0004      # metres, keeps a wrapped shell just off the skin


def mark_skin_layer(mesh, specs, body_verts, verts):
    """Detect shells wrapped onto the skin; returns (verts, is_layer)."""
    fraction = vl.skin_layer_fraction(verts, body_verts)
    if fraction < SKIN_LAYER_MIN_FRACTION:
        return verts, False
    normals = vl.vertex_normals(verts, mesh.poly_len, mesh.poly_idx)
    for spec in specs:
        spec["layer"] = True
    return verts + normals * SKIN_LAYER_PUSH, True


def add_clothing_object(ctx, bundle, name, mesh, specs, hidden, verts=None):
    keep = None
    if hidden:
        keep = ~np.isin(mesh.poly_mat, np.asarray(hidden, dtype=np.int32))
    faces, loop_uv_idx, face_mat = vl.clean_polygons(mesh.poly_len, mesh.poly_idx,
                                                     mesh.uv_poly_idx, mesh.poly_mat, keep)
    bundle.add_object(name, mesh.verts if verts is None else verts, faces,
                      mesh.uvs[loop_uv_idx], face_mat, specs, role="clothing")


# ------------------------------------------------------------------------
# Hair
# ------------------------------------------------------------------------

HAIR_CHILDREN_MAX = 8
HAIR_RADIUS_MIN, HAIR_RADIUS_MAX = 0.0005, 0.0012


def hair_sim_storable(vaj, overrides):
    """The '<uid>Sim' storable (colours, width, multiplier) with scene overrides."""
    storable = {}
    for s in vaj.get("storables", []):
        if str(s.get("id", "")).endswith("Sim"):
            storable = dict(s)
            break
    for sid, scene_storable in (overrides or {}).items():
        if storable.get("id") and sid == storable.get("id"):
            storable.update(scene_storable)
    return storable


def hair_material(name, sim):
    root = vl.storable_color(sim.get("rootColor")) or [0.05, 0.03, 0.02]
    tip = vl.storable_color(sim.get("tipColor")) or root
    color = [(r + t) * 0.5 for r, t in zip(root, tip)]
    return vl.material_spec(name, color=color, roughness=0.45, hair=True, _quiet=True)


def scalp_material(vaj, overrides, uid):
    for sid, s in list(_material_storables(vaj).items()) + list((overrides or {}).items()):
        if "Scalp" in sid and "Material" in sid:
            color = vl.storable_color(s.get("Diffuse Color"))
            if color is not None:
                return vl.material_spec("Scalp", color=color, roughness=0.6, layer=True)
    return vl.material_spec("Scalp", color=[0.06, 0.04, 0.03], roughness=0.6, layer=True)


def add_hair_item(ctx, bundle, package, vam_member, name, overrides, base_verts,
                  morphed_verts, missing):
    """Strand hair -> curves (+ scalp cap); mesh hair -> clothing-style object.

    Returns a short description for the notes.
    """
    base = vam_member[:-4]
    vab = package.find(base + ".vab")
    if vab is None:
        raise FileNotFoundError("no .vab beside %s" % vam_member)
    data = package.read(vab)
    vaj_member = package.find(base + ".vaj")
    vaj = vl.lenient_json_loads(package.read(vaj_member)) if vaj_member else {}
    item_dir = posixpath.dirname(vam_member)
    if vl.is_dazmesh_vab(data[:64]):
        mesh = vl.parse_dazmesh_vab(data)
        specs, hidden = clothing_materials(ctx, mesh, vaj, package, item_dir, bundle,
                                           overrides=overrides, missing=missing)
        verts = mesh.verts
        if morphed_verts is not None:
            verts = vl.transfer_displacement(mesh.verts, base_verts, morphed_verts)
            verts, _layer = mark_skin_layer(mesh, specs, morphed_verts, verts)
        add_clothing_object(ctx, bundle, name, mesh, specs, hidden, verts)
        return "%s (mesh)" % name
    guides = vl.parse_hair_vab(data)
    sim = hair_sim_storable(vaj, overrides)
    children = max(1, min(HAIR_CHILDREN_MAX, int(vl.as_float(sim.get("hairMultiplier"), 4))))
    spread = guides.segment_length * 0.45
    strands, dropped = vl.drop_unstyled_guides(guides.strands, guides.segment_length)
    if morphed_verts is not None and strands:
        lengths = [len(s) for s in strands]
        moved = vl.transfer_displacement(np.concatenate(strands), base_verts, morphed_verts)
        strands, cursor = [], 0
        for length in lengths:
            strands.append(moved[cursor:cursor + length])
            cursor += length
    fanned = vl.hair_children(strands, children, spread, seed=len(name))
    width = vl.as_float(sim.get("width"), 0.0002)
    radius = min(HAIR_RADIUS_MAX, max(HAIR_RADIUS_MIN, width * 4.0))
    bundle.add_curves(name, fanned, hair_material(name, sim), radius)
    scalp = ctx.cache.scalp_mesh(guides.scalp_token, guides.scalp_verts)
    if scalp is not None:
        verts = scalp.verts
        if morphed_verts is not None:
            verts = vl.transfer_displacement(scalp.verts, base_verts, morphed_verts)
        normals = vl.vertex_normals(verts, scalp.poly_len, scalp.poly_idx)
        verts = verts + normals * SKIN_LAYER_PUSH
        faces, loop_uv_idx, face_mat = vl.clean_polygons(
            scalp.poly_len, scalp.poly_idx, scalp.uv_poly_idx, scalp.poly_mat)
        specs = [dict(scalp_material(vaj, overrides, name), _quiet=True)
                 for _ in scalp.material_names]
        bundle.add_object(name + " scalp", verts, faces, scalp.uvs[loop_uv_idx], face_mat,
                          specs, role="scalp")
    return "%s (%d guides x%d%s%s)" % (
        name, len(strands), children,
        ", %d unstyled dropped" % dropped if dropped else "",
        "" if scalp is not None else ", no scalp cap")


def build_hair_bundle(ctx, entry, out_dir):
    bundle = vl.ModelBundle(out_dir, entry.key, "hair", entry.display)
    missing = []
    info = add_hair_item(ctx, bundle, entry.package, entry.member, entry.display, None,
                         None, None, missing)
    bundle.notes.update({"package": entry.package.id, "uid": entry.extra.get("uid"),
                         "hair": [info], "missingTextures": missing})
    return bundle.write(), bundle.notes


def build_clothing_bundle(ctx, entry, out_dir):
    bundle = vl.ModelBundle(out_dir, entry.key, "clothing", entry.display)
    mesh, vaj, item_dir = load_item(ctx, entry.package, entry.member)
    missing = []
    specs, hidden = clothing_materials(ctx, mesh, vaj, entry.package, item_dir, bundle,
                                       missing=missing)
    add_clothing_object(ctx, bundle, entry.display, mesh, specs, hidden)
    bundle.notes.update({
        "package": entry.package.id, "uid": entry.extra.get("uid"),
        "itemType": entry.extra.get("itemType"), "vertices": mesh.num_verts,
        "polygons": mesh.num_polys, "materials": mesh.material_names,
        "missingTextures": missing,
    })
    return bundle.write(), bundle.notes


# --------------------------------------------------------------------------
# Looks
# --------------------------------------------------------------------------

def load_person(entry):
    data = vl.lenient_json_loads(entry.package.read(entry.member))
    if entry.extra.get("source") == "scene":
        for atom in data.get("atoms", []):
            if atom.get("type") == "Person" and atom.get("id") == entry.extra.get("person"):
                return atom
        raise KeyError("person %s not found in %s" % (entry.extra.get("person"),
                                                      entry.member))
    return data


def apply_morphs(ctx, verts, morphs, gender, base_meta, package, include_pose):
    parts = base_meta["geometryId"].split(":")
    components = base_meta["components"]
    body_off, body_n = components[parts[0]]
    genital = components[parts[1]] if len(parts) > 1 else None
    report = {"applied": 0, "skippedPose": 0, "skippedZero": 0, "missing": [],
              "wrongGender": 0, "names": []}
    for morph in morphs or []:
        value = vl.as_float(morph.get("value"), 0.0)
        if abs(value) < 1e-6:
            report["skippedZero"] += 1
            continue
        uid = morph.get("uid") or morph.get("name") or ""
        offset, limit = body_off, body_n
        if ":/" in uid:
            pkg, member = ctx.index.resolve(uid, package)
            vmb = pkg.find(member[:-4] + ".vmb") if member else None
            if member is None or vmb is None:
                report["missing"].append(uid)
                continue
            try:
                info = vl.lenient_json_loads(pkg.read(member))
            except ValueError:
                info = {}
            if vl.is_pose_morph(info) and not include_pose:
                report["skippedPose"] += 1
                continue
            region = vl.region_from_morph_path(member) or gender
            if not region.startswith(gender):
                report["wrongGender"] += 1
                continue
            if region.endswith("genitalia"):
                if genital is None:
                    continue
                offset, limit = genital
            idx, delta = vl.parse_vmb(pkg.read(vmb))
            name = info.get("displayName") or morph.get("name") or uid
        else:
            hit = ctx.cache.builtin_morph(gender, uid)
            if hit is None:
                report["missing"].append(uid)
                continue
            info, idx, delta = hit
            if vl.is_pose_morph(info) and not include_pose:
                report["skippedPose"] += 1
                continue
            if "genital" in (info.get("region", "") + info.get("group", "")).lower():
                if genital is None:
                    continue
                offset, limit = genital
            name = uid
        mask = (idx >= 0) & (idx < limit)
        if not np.any(mask):
            continue
        np.add.at(verts, offset + idx[mask], value * delta[mask])
        report["applied"] += 1
        report["names"].append("%s=%.3g" % (name, value))
    return report


def skin_texture_table(ctx, bundle, package, textures_storable, defaults, missing):
    """{region: {kind: file}} from the look's texture urls, then skin defaults."""
    table = {region: {} for region in SKIN_REGIONS}
    used_defaults = []
    for region in SKIN_REGIONS:
        for kind_key, kind in SKIN_KINDS.items():
            url = textures_storable.get("%s%sUrl" % (region, kind_key))
            if url and str(url).strip().lower() not in EMPTY_URLS:
                pkg, member = ctx.index.resolve(url, package)
                if member is None:
                    missing.append("%s %s: %s" % (region, kind, url))
                else:
                    table[region][kind] = bundle.add_texture(pkg, member)
                    continue
            if kind == "decal":
                continue
            default = defaults.get((region, kind))
            if default:
                table[region][kind] = bundle.add_texture_file(default)
                used_defaults.append("%s.%s" % (region, kind))
    return table, used_defaults


def body_materials(ctx, bundle, base_mesh, base_meta, storables, package, defaults,
                   skin_color, missing):
    groups = base_meta.get("textureGroups", {})
    region_of = {}
    for group, region in (("face", "face"), ("torso", "torso"), ("limb", "limbs"),
                          ("genital", "genitals")):
        for index in groups.get(group, []):
            region_of[index] = region
    table, used_defaults = skin_texture_table(ctx, bundle, package,
                                              storables.get("textures", {}), defaults,
                                              missing)

    def override_texture(storable_id, key="customTexture_MainTex"):
        storable = storables.get(storable_id, {})
        url = storable.get(key)
        if not url or str(url).strip().lower() in EMPTY_URLS:
            return None
        pkg, member = ctx.index.resolve(url, package)
        if member is None:
            missing.append("%s: %s" % (storable_id, url))
            return None
        return bundle.add_texture(pkg, member)

    default_eyes = defaults.get(("eyes", "diffuse"))
    default_lashes = defaults.get(("lashes", "diffuse"))
    specs = []
    hidden = []
    for index, name in enumerate(base_mesh.material_names):
        spec = vl.material_spec(name)
        if name == "Hidden":
            hidden.append(index)
        elif index in region_of:
            region = region_of[index]
            spec.update(table.get(region, {}))
            spec["color"] = skin_color
            spec["region"] = region
            spec["roughness"] = 0.5
        elif name in EYE_MATERIALS:
            texture = override_texture(EYE_MATERIALS[name])
            if texture is None and default_eyes:
                texture = bundle.add_texture_file(default_eyes)
            spec["diffuse"] = texture
            spec["region"] = "eyes"
            spec["roughness"] = 0.35
            if name == "Lacrimals":
                spec["color"] = [0.75, 0.55, 0.55]
        elif name in GLASS_MATERIALS:
            spec["glass"] = True
            spec["transparent"] = True
            spec["region"] = "eyes"
        elif name == "Eyelashes":
            for sid in ("FemaleEyelashes", "MaleEyelashes"):
                texture = override_texture(sid)
                if texture:
                    spec["diffuse"] = texture
                    break
            if spec["diffuse"] is None and default_lashes:
                spec["diffuse"] = bundle.add_texture_file(default_lashes)
            spec["color"] = [0.05, 0.04, 0.04]
            spec["transparent"] = True
            spec["region"] = "lashes"
        elif name in MOUTH_MATERIALS:
            texture = override_texture(MOUTH_MATERIALS[name])
            if texture is None and defaults.get(("mouth", "diffuse")):
                texture = bundle.add_texture_file(defaults[("mouth", "diffuse")])
            spec["diffuse"] = texture
            if texture is None:
                spec["color"] = [0.85, 0.83, 0.8] if name == "Teeth" else [0.6, 0.25, 0.28]
            spec["region"] = "mouth"
            spec["roughness"] = 0.3
        else:
            region = "genitals" if "anus" in name.lower() else "torso"
            spec.update(table.get(region, {}))
            spec["color"] = skin_color
            spec["region"] = region
        specs.append(spec)
    return specs, hidden, table, used_defaults


def build_look_bundle(ctx, entry, out_dir, include_pose=False, include_clothing=True,
                      include_hair=True):
    bundle = vl.ModelBundle(out_dir, entry.key, "look", entry.display)
    atom = load_person(entry)
    storables = vl.person_storables(atom)
    geometry = storables.get("geometry", {})
    character = geometry.get("character") or "Female Custom"
    gender = ctx.cache.gender_of(character)
    info = ctx.cache.character(character) or {}
    base_mesh, base_meta = ctx.cache.base(gender)
    missing = []

    verts = base_mesh.verts.copy()
    morph_report = apply_morphs(ctx, verts, geometry.get("morphs", []), gender, base_meta,
                                entry.package, include_pose)

    try:
        custom_bundle = "m_c" if gender == "male" else "f_c"
        defaults = ctx.cache.skin_textures(info.get("bundle") or custom_bundle,
                                           fallback_bundle=custom_bundle)
    except (RuntimeError, FileNotFoundError) as exc:
        log("  default skin textures unavailable: %s" % exc)
        defaults = {}
    skin_color = vl.storable_color(storables.get("skin", {}).get("Skin Color"))
    specs, hidden, table, used_defaults = body_materials(
        ctx, bundle, base_mesh, base_meta, storables, entry.package, defaults, skin_color,
        missing)
    keep = ~np.isin(base_mesh.poly_mat, np.asarray(hidden, dtype=np.int32)) if hidden else None
    faces, loop_uv_idx, face_mat = vl.clean_polygons(
        base_mesh.poly_len, base_mesh.poly_idx, base_mesh.uv_poly_idx, base_mesh.poly_mat,
        keep)
    bundle.add_object("Body", verts, faces, base_mesh.uvs[loop_uv_idx], face_mat, specs,
                      role="body")

    clothing_done, clothing_missing = [], []
    if include_clothing:
        for item in geometry.get("clothing", []) or []:
            if not vl.as_bool(item.get("enabled"), True):
                continue
            uid = item.get("id") or ""
            pkg, member = ctx.index.resolve(uid, entry.package)
            if member is None:
                found = ctx.catalog.by_uid(item.get("internalId") or "")
                if found is not None and found.kind == "clothing":
                    pkg, member = found.package, found.member
            if member is None or not member.lower().endswith(".vam"):
                clothing_missing.append(item.get("internalId") or uid)
                continue
            try:
                mesh, vaj, item_dir = load_item(ctx, pkg, member)
            except (ValueError, FileNotFoundError, KeyError) as exc:
                clothing_missing.append("%s (%s)" % (item.get("internalId") or uid, exc))
                continue
            item_missing = []
            item_specs, item_hidden = clothing_materials(
                ctx, mesh, vaj, pkg, item_dir, bundle, overrides=storables,
                missing=item_missing)
            missing.extend(item_missing)
            fitted = vl.transfer_displacement(mesh.verts, base_mesh.verts, verts)
            fitted, is_layer = mark_skin_layer(mesh, item_specs, verts, fitted)
            name = item.get("internalId") or mesh.name
            add_clothing_object(ctx, bundle, name, mesh, item_specs, item_hidden, fitted)
            clothing_done.append(name + (" (skin layer)" if is_layer else ""))

    hair_done, hair_missing = [], []
    for item in geometry.get("hair", []) or []:
        if not vl.as_bool(item.get("enabled"), True):
            continue
        label = item.get("internalId") or item.get("id") or "hair"
        if not include_hair:
            hair_missing.append("%s (skipped: --no-hair)" % label)
            continue
        uid = item.get("id") or ""
        pkg, member = ctx.index.resolve(uid, entry.package)
        if member is None:
            found = ctx.catalog.by_uid(item.get("internalId") or "")
            if found is not None and found.kind == "hair":
                pkg, member = found.package, found.member
        if member is None or not member.lower().endswith(".vam"):
            hair_missing.append(label)
            continue
        try:
            hair_done.append(add_hair_item(ctx, bundle, pkg, member, label, storables,
                                           base_mesh.verts, verts, missing))
        except (ValueError, FileNotFoundError, KeyError) as exc:
            hair_missing.append("%s (%s)" % (label, exc))
    bundle.notes.update({
        "package": entry.package.id, "source": entry.member,
        "person": entry.extra.get("person"), "character": character, "gender": gender,
        "skinBundle": info.get("bundle"), "morphs": morph_report,
        "skinTextures": table, "defaultTexturesUsed": used_defaults,
        "clothing": clothing_done, "clothingMissing": clothing_missing,
        "hair": hair_done, "hairMissing": hair_missing, "missingTextures": missing,
    })
    return bundle.write(), bundle.notes


# --------------------------------------------------------------------------
# Blender driver
# --------------------------------------------------------------------------

def run_blender(blender, worker, model_dir, out_blend, mode, formats, preview):
    cmd = [blender, "--background", "--python", worker, "--", model_dir, out_blend,
           mode, ",".join(formats), "1" if preview else "0"]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    match = RESULT_MARKER.search(completed.stdout or "")
    if not match:
        tail = "\n".join((completed.stdout or "").splitlines()[-15:])
        return {"status": "FAIL", "error": "Blender produced no result marker",
                "log": tail}
    return json.loads(match.group(1))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_list(ctx, args):
    kinds = kind_filter(args.kind)
    rows = ctx.catalog.entries(kinds)
    if args.filter:
        low = args.filter.lower()
        rows = [e for e in rows if low in e.key.lower() or low in e.display.lower()]
    all_entries = ctx.catalog.entries(("look", "clothing", "hair"))
    numbering = {id(e): i + 1 for i, e in enumerate(all_entries)}
    if args.json:
        payload = [dict(index=numbering[id(e)], **e.to_row()) for e in rows]
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        log("wrote %s (%d entries)" % (args.json, len(payload)))
        return 0
    looks = [e for e in rows if e.kind == "look"]
    clothing = [e for e in rows if e.kind == "clothing"]
    hair = [e for e in rows if e.kind == "hair"]
    if looks:
        log("Looks (%d) - Person atoms in scenes / appearance presets:" % len(looks))
        log("  %5s  %-58s %-14s %6s %5s %4s %4s  %s" % (
            "#", "key", "character", "morphs", "cloth", "hair", "tex", "display"))
        for entry in looks:
            x = entry.extra
            log("  %5d  %-58s %-14s %6d %5d %4d %4d  %s" % (
                numbering[id(entry)], entry.key[:58], (x.get("character") or "")[:14],
                x.get("morphs", 0), x.get("clothing", 0), x.get("hair", 0),
                x.get("skinTextures", 0), entry.display))
    if clothing:
        exportable = sum(1 for e in clothing if e.extra.get("exportable"))
        log("")
        log("Clothing (%d, %d with mesh):" % (len(clothing), exportable))
        log("  %5s  %-58s %-14s %-4s %s" % ("#", "key", "type", "mesh", "display"))
        for entry in clothing:
            x = entry.extra
            log("  %5d  %-58s %-14s %-4s %s" % (
                numbering[id(entry)], entry.key[:58],
                (x.get("itemType") or "").replace("Clothing", "")[:14],
                "yes" if x.get("exportable") else "-", entry.display))
    if hair:
        log("")
        exportable = sum(1 for e in hair if e.extra.get("exportable"))
        log("Hair (%d, %d with strand/mesh data) - guides fanned out into curves:"
            % (len(hair), exportable))
        for entry in hair:
            log("  %5d  %-58s %-4s %s" % (numbering[id(entry)], entry.key[:58],
                                          "yes" if entry.extra.get("exportable") else "-",
                                          entry.display))
    log("")
    log("Select with --only <key or unique substring> or --index <#>.")
    return 0


def kind_filter(kind):
    if kind in (None, "all"):
        return ("look", "clothing", "hair")
    return (kind,)


def cmd_prepare(ctx, args):
    start = time.time()
    log("Preparing VaM cache in %s" % ctx.cache.dir)
    ctx.cache.prepare_person()
    for gender in ("female", "male"):
        ctx.cache.prepare_morphs(gender)
    log("done in %.0fs" % (time.time() - start))
    return 0


def cmd_export(ctx, args):
    kinds = kind_filter(args.kind)
    if args.all:
        entries = [e for e in ctx.catalog.entries(kinds)
                   if e.kind == "look" or e.extra.get("exportable")]
        unknown = []
    else:
        entries, unknown = ctx.catalog.select(args.only or [], args.index or [], kinds)
    if unknown:
        for item in unknown:
            log("unknown selection: %s" % item)
        return 2
    if not entries:
        log("nothing selected; use --only, --index or --all")
        return 2
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "export_vam_model_blender.py")
    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()] or ["blend"]
    results = []
    for number, entry in enumerate(entries, 1):
        log("")
        log("[%d/%d] %s: %s" % (number, len(entries), entry.key, entry.display))
        if entry.kind in ("clothing", "hair") and not entry.extra.get("exportable"):
            log("  NOMESH: no usable .vab beside the .vam")
            results.append({"model": entry.key, "kind": entry.kind, "status": "NOMESH",
                            "reason": "no .vab mesh/strand data"})
            continue
        model_dir = os.path.join(ctx.out_root, entry.kind + "s", entry.key)
        blend_dir = os.path.join(model_dir, "blend")
        out_blend = os.path.join(blend_dir, entry.key + ".blend")
        preview = os.path.join(blend_dir, entry.key + "_preview.png")
        if (not args.force and not args.validate and os.path.isfile(out_blend)
                and (args.no_preview or os.path.isfile(preview))):
            log("  exists, skipped (use --force)")
            results.append({"model": entry.key, "kind": entry.kind, "status": "SKIP",
                            "output": out_blend, "preview": preview,
                            "reason": "output already exists"})
            continue
        started = time.time()
        try:
            if entry.kind == "look":
                _path, notes = build_look_bundle(ctx, entry, model_dir,
                                                 include_pose=args.include_pose_morphs,
                                                 include_clothing=not args.no_clothing,
                                                 include_hair=not args.no_hair)
            elif entry.kind == "hair":
                _path, notes = build_hair_bundle(ctx, entry, model_dir)
            else:
                _path, notes = build_clothing_bundle(ctx, entry, model_dir)
        except Exception as exc:  # noqa: BLE001 - report and continue
            log("  FAIL (assemble): %s" % exc)
            results.append({"model": entry.key, "kind": entry.kind, "status": "FAIL",
                            "error": "assemble: %s" % exc,
                            "traceback": traceback.format_exc()})
            continue
        describe_notes(entry, notes)
        payload = run_blender(args.blender, worker, model_dir, out_blend,
                              "validate" if args.validate else "export", formats,
                              not args.no_preview)
        record = {"model": entry.key, "kind": entry.kind, "display": entry.display,
                  "source": "%s:/%s" % (entry.package.id, entry.member),
                  "modelDir": model_dir, "notes": notes,
                  "seconds": round(time.time() - started, 1)}
        record.update(payload)
        results.append(record)
        if payload.get("status") == "PASS":
            log("  PASS: %s objects / %s materials / %s textures packed / %s strands (%.1fs)" % (
                payload.get("objects"), payload.get("materials"),
                payload.get("packed_images"), payload.get("strands", 0), record["seconds"]))
            if payload.get("untextured_slots"):
                log("    untextured: %s" % "; ".join(payload["untextured_slots"]))
            if not args.validate:
                log("    BLEND: %s" % payload.get("output"))
                if payload.get("preview"):
                    log("    PREVIEW: %s" % payload.get("preview"))
        else:
            log("  FAIL: %s" % payload.get("error"))
            if payload.get("log"):
                log(payload["log"])
    write_manifest(ctx, args, results)
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    passed = sum(1 for r in results if r.get("status") == "PASS")
    skipped = sum(1 for r in results if r.get("status") == "SKIP")
    nomesh = sum(1 for r in results if r.get("status") == "NOMESH")
    log("")
    log("Complete: PASS=%d FAIL=%d SKIP=%d NOMESH=%d" % (passed, failed, skipped, nomesh))
    return 1 if failed else 0


def describe_notes(entry, notes):
    if entry.kind == "look":
        morphs = notes.get("morphs", {})
        log("  character %s (%s), morphs applied %d, pose skipped %d, missing %d" % (
            notes.get("character"), notes.get("gender"), morphs.get("applied", 0),
            morphs.get("skippedPose", 0), len(morphs.get("missing", []))))
        if morphs.get("missing"):
            log("    missing morphs: %s" % ", ".join(morphs["missing"][:6]))
        if notes.get("clothing"):
            log("  clothing: %s" % ", ".join(notes["clothing"]))
        if notes.get("clothingMissing"):
            log("    clothing not found (dependency missing?): %s"
                % ", ".join(notes["clothingMissing"]))
        if notes.get("hair"):
            log("  hair: %s" % ", ".join(notes["hair"]))
        if notes.get("hairMissing"):
            log("    hair not found: %s" % ", ".join(str(h) for h in notes["hairMissing"]))
        if notes.get("defaultTexturesUsed"):
            log("  default skin textures used for: %s"
                % ", ".join(notes["defaultTexturesUsed"]))
    elif entry.kind == "hair":
        log("  hair: %s" % ", ".join(notes.get("hair", [])))
    else:
        log("  %d vertices, %d polygons, materials: %s" % (
            notes.get("vertices", 0), notes.get("polygons", 0),
            ", ".join(notes.get("materials", []))))
    if notes.get("missingTextures"):
        log("    missing textures: %s" % "; ".join(notes["missingTextures"][:6]))


def write_manifest(ctx, args, results):
    name = "vam_models_manifest.validate.json" if args.validate else "vam_models_manifest.json"
    path = args.manifest or os.path.join(ctx.out_root, name)
    merged = list(results)
    if not args.validate and not args.all and os.path.isfile(path):
        try:
            previous = json.load(open(path, encoding="utf-8"))
            updated = {r["model"] for r in results}
            merged = [r for r in previous.get("results", []) if r.get("model") not in updated]
            merged.extend(results)
            merged.sort(key=lambda r: (r.get("kind", ""), r.get("model", "")))
        except (OSError, ValueError) as exc:
            log("  existing manifest could not be merged: %s" % exc)
    manifest = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "gameRoot": ctx.game_root, "outRoot": ctx.out_root,
                "validateOnly": bool(args.validate), "results": merged}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
    log("Manifest: %s" % path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", default=DEFAULT_GAME_ROOT)
    parser.add_argument("--out", default=DEFAULT_OUT_ROOT)
    parser.add_argument("--assetstudio", default=vl.default_assetstudio())
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--kind", choices=("look", "clothing", "hair", "all"), default="all")
    p_list.add_argument("--filter")
    p_list.add_argument("--json")

    p_prepare = sub.add_parser("prepare")

    p_export = sub.add_parser("export")
    p_export.add_argument("--only", nargs="*")
    p_export.add_argument("--index", nargs="*", type=int)
    p_export.add_argument("--all", action="store_true")
    p_export.add_argument("--kind", choices=("look", "clothing", "hair", "all"),
                          default="all")
    p_export.add_argument("--format", default="blend")
    p_export.add_argument("--blender", default=DEFAULT_BLENDER)
    p_export.add_argument("--no-preview", action="store_true")
    p_export.add_argument("--force", action="store_true")
    p_export.add_argument("--validate", action="store_true")
    p_export.add_argument("--include-pose-morphs", action="store_true")
    p_export.add_argument("--no-clothing", action="store_true")
    p_export.add_argument("--no-hair", action="store_true")
    p_export.add_argument("--manifest")

    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if not os.path.isdir(args.game_root):
        parser.error("game root not found: %s" % args.game_root)
    ctx = Context(args)
    if args.command == "list":
        return cmd_list(ctx, args)
    if args.command == "prepare":
        return cmd_prepare(ctx, args)
    if not os.path.isfile(args.blender):
        parser.error("Blender not found: %s" % args.blender)
    return cmd_export(ctx, args)


if __name__ == "__main__":
    sys.exit(main())
