# -*- coding: utf-8 -*-
"""source + recipe set -> MMD bone morphs and/or shape keys (MMD vertex morphs, ARKit 52).

Outputs of the MMD set:
  BONE    every expression an mmd_tools bone morph (needs a pose source and an mmd_tools model)
  VERTEX  every expression a shape key = PMX vertex morph (any source; registered in the model's
          morph panels when it is an mmd_tools model, else just keys - convert later)
  AUTO    per expression: a bone morph when a 4-weight PMX shows it within ``threshold_mm`` of the
          real rig, otherwise a vertex morph (pose source + mmd_tools model)
The ARKit set always writes shape keys (that is what Faceit and face trackers drive).

One name, one kind: writing a bone morph removes shape keys of the same name and vice versa
(``replace``), otherwise MMD would apply both and the face would move twice.
"""
import json

import numpy as np

from . import bake, mmd, recipes

TAG = "expression_kit"        # mesh: JSON {set: [shape keys made]}; root: JSON {"BONE": [bone morphs made]}


def tags(obj):
    try:
        return json.loads(obj.get(TAG, "{}"))
    except (TypeError, ValueError):
        return {}


def _add_tags(obj, key, names_):
    t = tags(obj)
    have = t.get(key, [])
    t[key] = have + [n for n in names_ if n not in have]
    obj[TAG] = json.dumps(t, ensure_ascii=False)


def _drop_tags(obj, key, names_):
    t = tags(obj)
    if key in t:
        t[key] = [n for n in t[key] if n not in set(names_)]
        obj[TAG] = json.dumps(t, ensure_ascii=False)


def made_keys(meshes, set_key=None):
    out = []
    for m in meshes:
        for k, names_ in tags(m).items():
            if set_key in (None, k):
                out += [n for n in names_ if n not in out]
    return out


def made_bone_morphs(root):
    return list(tags(root).get("BONE", [])) if root is not None else []


def _remove_keys(meshes, names_):
    removed = []
    wanted = set(names_)
    for m in meshes:
        if not m.data.shape_keys:
            continue
        for name in [kb.name for kb in m.data.shape_keys.key_blocks][1:]:     # by name: removal
            if name in wanted:                                                # invalidates refs
                m.shape_key_remove(m.data.shape_keys.key_blocks[name])
                removed.append(name)
        for set_key in list(tags(m)):
            _drop_tags(m, set_key, wanted)
        if m.data.shape_keys and len(m.data.shape_keys.key_blocks) == 1:     # only Basis left
            m.shape_key_clear()
    return sorted(set(removed))


def _foreign(meshes, root, name, set_key, writing):
    """``name`` already exists and was not made here - with replace off it is left alone."""
    for m in meshes:
        if m.data.shape_keys and name in m.data.shape_keys.key_blocks and name not in tags(m).get(set_key, []):
            return True
    return (writing == "bone" or set_key == recipes.MMD) and root is not None and \
        root.mmd_root.bone_morphs.find(name) >= 0 and name not in made_bone_morphs(root)


def _write_key(mesh, name, base, delta, eps):
    delta = delta.copy()
    delta[np.linalg.norm(delta, axis=1) < eps] = 0.0
    if not delta.any():
        return 0
    if mesh.data.shape_keys is None:
        mesh.shape_key_add(name="Basis", from_mix=False)
    blocks = mesh.data.shape_keys.key_blocks
    key = blocks.get(name) or mesh.shape_key_add(name=name, from_mix=False)
    key.relative_key = mesh.data.shape_keys.reference_key
    key.data.foreach_set("co", (base + delta).ravel())
    key.slider_min, key.slider_max, key.value = 0.0, 1.0, 0.0
    return int(np.count_nonzero(np.any(delta != 0.0, axis=1)))


def plan(source, targets):
    """[(target, components, against)] this source can make, and [(name, reason)] it cannot."""
    doable, skipped = [], []
    for t in targets:
        comps = source.recipe(t)
        if comps is None:
            skipped.append((t["name"], source.why_not(t)))
        else:
            doable.append((t, comps, source.against(t)))
    return doable, skipped


def build(arm, meshes, root, source, set_key, targets, output="VERTEX", strengths=None, replace=True,
          threshold_mm=0.3, log=print):
    strengths = strengths or {}
    report = {"set": set_key, "source": source.key, "output": output, "bone": [], "vertex": [], "skipped": [],
              "removed": [], "errors_mm": {}, "disconnected": 0}
    if set_key == recipes.ARKIT:
        output = "VERTEX"
        if source.key == "SHAPES":
            report["note"] = "the model already has these ARKit keys - register them with Faceit instead"
            return report
    if output in ("BONE", "AUTO"):
        if root is None:
            raise ValueError("bone morphs need an mmd_tools model: convert it first (Convert to MMD / mmd_tools)")
        if source.form != "pose":
            raise ValueError("%s has no bone movement - use vertex morphs" % source.key)
    doable, report["skipped"] = plan(source, targets)
    if not replace:
        keep = []
        for t, comps, against in doable:
            if _foreign(meshes, root, t["name"], set_key, "bone" if output == "BONE" else "vertex"):
                report["skipped"].append((t["name"], "exists (not made here; replace is off)"))
            else:
                keep.append((t, comps, against))
        doable = keep
    if not doable:
        return report
    unit = bake.mm_per_unit(arm)
    eps = 0.005 / unit                                     # offsets below 0.005 mm are rounding noise

    poses, against_poses = {}, {}
    if source.form == "pose":
        for t, comps, against in doable:
            s = strengths.get(t["category"], 1.0)
            poses[t["name"]] = source.pose(comps, s)
            if against:
                against_poses[t["name"]] = source.pose(against, s)
        moving = {b for p in list(poses.values()) + list(against_poses.values())
                  for b, value in p.items() if value[0].length > 1e-9}
        report["disconnected"] = bake.disconnect(arm, moving)

    with mmd.SliderState(root):
        if output == "BONE":
            for t, _comps, _a in doable:
                pose = poses[t["name"]]
                if not pose:
                    report["skipped"].append((t["name"], "moves nothing"))
                    continue
                if _scales(pose):
                    report["skipped"].append((t["name"], "scales bones - a PMX bone morph cannot, use vertex / auto"))
                    continue
                report["removed"] += _clear_other_kind(meshes, root, t["name"], "bone", replace)
                mmd.write_bone_morph(root, t["name"], t["name_e"], t["category"], pose)
                report["bone"].append(t["name"])
        elif source.form == "shape":
            for t, comps, _a in doable:
                deltas = source.shapes(comps, strengths.get(t["category"], 1.0))
                moved = 0
                for m in source.meshes:
                    if m.name in deltas:
                        moved += _write_key(m, t["name"], bake.basis_coords(m), deltas[m.name], eps)
                if not moved:
                    report["skipped"].append((t["name"], "moves nothing"))
                    continue
                if set_key == recipes.MMD:
                    report["removed"] += _clear_other_kind(meshes, root, t["name"], "vertex", replace)
                for m in source.meshes:
                    if m.data.shape_keys and t["name"] in m.data.shape_keys.key_blocks:
                        _add_tags(m, set_key, [t["name"]])
                report["vertex"].append(t["name"])
                log("  %-12s %6d verts" % (t["name"], moved))
        else:
            _bake_poses(arm, meshes, root, source, set_key, doable, poses, against_poses, output, replace,
                        threshold_mm, unit, eps, report, log)
        if set_key == recipes.ARKIT and root is not None and report["vertex"]:
            # listed after the MMD morphs as 'other' - unlisted keys would head the PMX morph list
            mmd.register_vertex_morphs(root, [(n, n, "OTHER") for n in report["vertex"]], at_top=False)
        if set_key == recipes.MMD and root is not None:
            by_name = {t["name"]: t for t, _c, _a in doable}
            if report["vertex"]:
                mmd.register_vertex_morphs(root, [(n, by_name[n]["name_e"], by_name[n]["category"])
                                                  for n in report["vertex"]])
            if report["bone"]:
                _add_tags(root, "BONE", report["bone"])
            if report["bone"] or report["vertex"] or report["removed"]:
                try:
                    mmd.refresh_facial_frame(root)
                except Exception as exc:            # cosmetic; the morphs are in
                    log("facial display frame: %s" % exc)
    return report


def _scales(pose):
    return any(len(value) > 2 for value in pose.values())


def _clear_other_kind(meshes, root, name, writing, replace):
    """Before writing a bone morph remove same-named shape keys, before a shape key the bone morph."""
    removed = []
    if writing == "bone":
        clash = [m for m in meshes if m.data.shape_keys and name in m.data.shape_keys.key_blocks]
        if clash and replace:
            removed += ["%s (shape key)" % n for n in _remove_keys(clash, [name])]
            if root is not None:
                mmd.remove_vertex_morph_entries(root, [name])
    elif root is not None and root.mmd_root.bone_morphs.find(name) >= 0 and replace:
        removed += ["%s (bone morph)" % n for n in mmd.remove_bone_morphs(root, [name])]
        _drop_tags(root, "BONE", [name])
    return removed


def _bake_poses(arm, meshes, root, source, set_key, doable, poses, against_poses, output, replace,
                threshold_mm, unit, eps, report, log):
    targets_meshes = bake.skinned_meshes(arm, meshes, source.face_bones())
    if not targets_meshes:
        raise ValueError("no mesh of %s is weighted to the bones this source moves" % arm.name)
    models = [bake.WeightModel(arm, m) for m in targets_meshes] if output == "AUTO" else []
    with bake.RestState(arm, targets_meshes) as state:
        rest = {m.name: bake.coords(m) for m in targets_meshes}
        base = {m.name: bake.basis_coords(m) for m in targets_meshes}
        for m in targets_meshes:
            if len(rest[m.name]) != len(base[m.name]):
                raise ValueError("%s: a modifier changes the vertex count - can't bake" % m.name)
        for t, _comps, _a in doable:
            name = t["name"]
            pose = poses[name]
            if not pose:
                report["skipped"].append((name, "moves nothing"))
                continue
            state.set_pose(pose)
            posed = {m.name: bake.coords(m) for m in targets_meshes}
            if output == "AUTO":
                err = max((wm.error() for wm in models), default=0.0) * unit
                report["errors_mm"][name] = round(err, 3)
                if err <= threshold_mm and not _scales(pose):
                    report["removed"] += _clear_other_kind(meshes, root, name, "bone", replace)
                    mmd.write_bone_morph(root, name, t["name_e"], t["category"], pose)
                    report["bone"].append(name)
                    log("  %-12s bone morph  (PMX error %.2f mm)" % (name, err))
                    continue
            ref = rest
            if name in against_poses:
                state.set_pose(against_poses[name])
                ref = {m.name: bake.coords(m) for m in targets_meshes}
            moved = 0
            for m in targets_meshes:
                moved += _write_key(m, name, base[m.name], posed[m.name] - ref[m.name], eps)
            if not moved:
                report["skipped"].append((name, "moves nothing"))
                continue
            if set_key == recipes.MMD:
                report["removed"] += _clear_other_kind(meshes, root, name, "vertex", replace)
            for m in targets_meshes:
                if m.data.shape_keys and name in m.data.shape_keys.key_blocks:
                    _add_tags(m, set_key, [name])
            report["vertex"].append(name)
            log("  %-12s %6d verts%s" % (name, moved, ("  (PMX error %.2f mm)" % report["errors_mm"][name])
                                         if name in report["errors_mm"] else ""))


def estimate(arm, meshes, source, targets, strengths=None):
    """{name: largest PMX (4-weight) error in mm} of each expression as a bone morph - nothing written."""
    strengths = strengths or {}
    doable, _skipped = plan(source, targets)
    targets_meshes = bake.skinned_meshes(arm, meshes, source.face_bones())
    models = [bake.WeightModel(arm, m) for m in targets_meshes]
    unit = bake.mm_per_unit(arm)
    out = {"max_influences": max((wm.max_influences for wm in models), default=0),
           "over4_vertices": int(sum(len(wm.over4) for wm in models)), "errors_mm": {}, "scaled": []}
    with bake.RestState(arm, targets_meshes) as state:
        for t, comps, _a in doable:
            pose = source.pose(comps, strengths.get(t["category"], 1.0))
            if _scales(pose):                       # no bone morph possible at all
                out["scaled"].append(t["name"])
                continue
            if out["over4_vertices"]:
                state.set_pose(pose)
                out["errors_mm"][t["name"]] = round(max(wm.error() for wm in models) * unit, 3)
    return out


def clear(meshes, root, set_key):
    """Remove what this add-on made for a set (never anything else)."""
    names_ = made_keys(meshes, set_key)
    removed = _remove_keys(meshes, names_) if names_ else []
    bones = []
    if root is not None:
        with mmd.SliderState(root):
            if set_key == recipes.MMD:
                bones = mmd.remove_bone_morphs(root, made_bone_morphs(root))
                _drop_tags(root, "BONE", bones)
            mmd.remove_vertex_morph_entries(root, removed)
            try:
                mmd.refresh_facial_frame(root)
            except Exception:
                pass
    return {"shape_keys": removed, "bone_morphs": bones}


def preview(arm, meshes, root, name, weight=1.0):
    """Show one expression (bone morph pose or shape key value); everything else we made at 0."""
    reset(arm, meshes, root)
    if root is not None and name in made_bone_morphs(root):
        mmd.pose_bone_morph(root, arm, name, weight)
        return "bone"
    for m in meshes:
        if m.data.shape_keys and name in m.data.shape_keys.key_blocks:
            m.data.shape_keys.key_blocks[name].value = weight
    return "shape"


def reset(arm, meshes, root):
    if root is not None:
        from mathutils import Matrix
        for b in mmd.morph_bones(root):
            pb = arm.pose.bones.get(b)
            if pb is not None:
                pb.matrix_basis = Matrix()
    mine = set(made_keys(meshes))
    for m in meshes:
        if m.data.shape_keys:
            for kb in m.data.shape_keys.key_blocks:
                if kb.name in mine:
                    kb.value = 0.0
