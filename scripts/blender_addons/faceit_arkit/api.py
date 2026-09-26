# -*- coding: utf-8 -*-
"""Script entry points (the panel's buttons call these too).

    import sys; sys.path.insert(0, "E:/code/othercode/ripper_tpose/scripts/blender_addons")
    from faceit_arkit import api
    api.analyze(obj, dna_path)                        # what the model has
    api.restore_weights(obj, "SK_Fiona_Face01.uasset.bin")   # optional: UE Viewer's 4-influence cut
    api.bake_arkit(obj, "SK_Fiona_Face01.dna")        # 52 ARKit shape keys from the MetaHuman DNA
    api.register_faceit(obj)                           # Faceit: objects, targets, head bone, Face Cap
"""
import collections
import os

import bpy

from . import arkit, bake, dna, faceit_link, ue_weights

_DNA_CACHE = {}


def load_dna(path):
    path = bpy.path.abspath(path)
    key = (path, os.path.getmtime(path))
    if key not in _DNA_CACHE:
        with open(path, "rb") as fh:
            _DNA_CACHE.clear()
            _DNA_CACHE[key] = dna.DnaFace(fh.read())
    return _DNA_CACHE[key]


def companion_package(dna_path):
    """<name>.uasset.bin next to <name>.dna, if the extractor wrote one."""
    if not dna_path:
        return ""
    stem = os.path.splitext(bpy.path.abspath(dna_path))[0]
    for cand in (stem + ".uasset.bin", stem + ".bin"):
        if os.path.isfile(cand):
            return cand
    return ""


def model(obj):
    """(armature, face meshes) for any object of the model."""
    arm = bake.find_armature(obj)
    if arm is None:
        raise ValueError("select an object of a rigged model (armature or a skinned mesh)")
    facial = [b.name for b in arm.data.bones if b.name.upper().startswith("FACIAL_")]
    meshes = bake.skinned_meshes(arm, facial) if facial else []
    if not meshes:            # no MetaHuman rig: the meshes that already carry ARKit keys
        meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() == arm
                  and o.data.shape_keys and arkit.match_names([k.name for k in o.data.shape_keys.key_blocks])]
    return arm, meshes


def analyze(obj, dna_path=""):
    arm, meshes = model(obj)
    info = {"armature": arm.name, "meshes": [m.name for m in meshes],
            "facial_bones": sum(1 for b in arm.data.bones if b.name.upper().startswith("FACIAL_"))}
    counts = collections.Counter()
    for m in meshes:
        for v in m.data.vertices:
            counts[sum(1 for g in v.groups if g.weight > 0.0)] += 1
    info["max_influences"] = max(counts) if counts else 0
    total = sum(counts.values()) or 1
    over4 = sum(n for k, n in counts.items() if k > 4)
    # UE Viewer's cut: most vertices at exactly 4, almost none above (a few edited ones may be)
    info["four_capped"] = info["facial_bones"] > 100 and counts.get(4, 0) / total > 0.5 and over4 / total < 0.05
    targets = faceit_link.arkit_targets(meshes)
    info["arkit_keys"] = len(targets)
    info["renamed_keys"] = sum(1 for k, v in targets.items() if k not in v)
    info["baked_by_addon"] = any(m.get(bake.TAG) for m in meshes)
    if dna_path:
        face = load_dna(dna_path)
        poser = bake.DnaPoser(face, arm)
        info["dna"] = {"file": os.path.basename(bpy.path.abspath(dna_path)), "joints": poser.fit["joints"],
                       "dna_joints": poser.fit["dna_joints"], "fit_mean_mm": round(poser.fit["mean_mm"], 2),
                       "fit_max_mm": round(poser.fit["max_mm"], 2), "blend_shape_channels": face.blend_shape_channels}
    state, _pkg = faceit_link.faceit_state()
    info["faceit"] = state
    if state == "enabled":
        registered, n = faceit_link.is_registered(bpy.context.scene, meshes)
        info["faceit_registered"], info["faceit_targets"] = registered, n
    info["head_bone"] = faceit_link.guess_head_bone(arm, meshes) if meshes else ""
    return info


def restore_weights(obj, package_path, force=False):
    arm, meshes = model(obj)
    with open(bpy.path.abspath(package_path), "rb") as fh:
        pkg = ue_weights.read_package(fh.read())
    reports = {}
    for m in meshes:
        try:
            reports[m.name] = ue_weights.restore(m, pkg, force=force)
        except ValueError as exc:            # a mesh of another package (hair, body) - not this one
            reports[m.name] = {"skipped": str(exc)}
    return {"package": {k: pkg[k] for k in ("sections", "max_influences", "total_influences", "per_vertex")},
            "meshes": reports}


def bake_arkit(obj, dna_path, names=None, log=print):
    arm, _meshes = model(obj)
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    face = load_dna(dna_path)
    return bake.bake(arm, face, names=names, dna_path=dna_path, log=log)


def clear_arkit(obj):
    _arm, meshes = model(obj)
    return bake.clear(meshes)


def register_faceit(obj, head_bone="", source="FACECAP", require_enabled=True):
    arm, meshes = model(obj)
    return faceit_link.register(bpy.context.scene, arm, meshes, head_bone=head_bone, source=source,
                                require_enabled=require_enabled)


def preview(obj, name, value=1.0):
    """Show one ARKit shape (all others to 0) on every face mesh."""
    _arm, meshes = model(obj)
    for m in meshes:
        if m.data.shape_keys is None:
            continue
        keys = m.data.shape_keys.key_blocks
        mapping = arkit.match_names([k.name for k in keys])
        for ark, key in mapping.items():
            keys[key].value = value if ark == name else 0.0


def reset(obj):
    preview(obj, "", 0.0)


def run_all(obj, dna_path, package_path="", head_bone="", source="FACECAP", log=print, require_enabled=True):
    out = {}
    package_path = package_path or companion_package(dna_path)
    if package_path:
        out["package"] = package_path
        out["weights"] = restore_weights(obj, package_path)
    out["bake"] = bake_arkit(obj, dna_path, log=log)
    state, _pkg = faceit_link.faceit_state()
    if state == "enabled" or (state == "disabled" and not require_enabled):
        out["faceit"] = register_faceit(obj, head_bone=head_bone, source=source, require_enabled=require_enabled)
    else:
        out["faceit"] = "Faceit %s - shape keys are ready, register them once Faceit is enabled" % state
    return out
