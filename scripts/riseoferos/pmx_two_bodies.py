"""The body put into a full PMX twice - dressed and nude - in the file itself (the user's pick, 2026-10-05:
"普通full版用两个身体").

Why: a full version's body is fitted inside the outfit, and the vertex morph 裸体形状 takes it back to its own shape
when 衣服非表示 hides the outfit.  MMD keeps the file's normals under a vertex morph, so the nude state was lit with
the fitted shape's normals (dented breasts, black nail notches).  Two bodies: the dressed one as it is, and a nude
copy - the nude shape's positions, the nude version's normals - shown instead of it by 裸体形状, which becomes a
material morph (dressed body alpha x 0, nude copy alpha added back).  Right in MMD and in Blender.  The same design
as the 爆衣 add-on's 换成完整身体 (scripts/blender_addons/clothes_burst/mmd.py), done here on the PMX data so that
every other byte of the file stays as it was (an mmd_tools import / export round trip moved a few things: one toe
normal flipped, bone tails, morph offsets under 0.08 mm, two rigid bodies' rotations).

What changes:
  - per body material (not outfit - the materials 衣服非表示_材質 hides - and moved by 裸体形状; the face material
    too when the neck is in it): its faces copied, right after it, as material <name>_nude (alpha 0 in the file,
    edge alpha 0); the copies' vertices appended at the end with the nude positions (rest + 裸体形状), the nude PMX's
    normals (same place and UV; the rest smooth normals of the nude shape), the source's UV / weights / edge scale;
  - every vertex / UV morph gets the source vertices' offsets on the copies (expressions work on the copy), every
    material morph the source materials' entries on the copies (the material indices after an insert shift);
  - 裸体形状: same index, name and panel, now a material morph - group morphs (衣服非表示) and the 表情 frame keep
    pointing at it.
A PMX whose 裸体形状 is a material morph already is left alone ("already").

  python pmx_two_bodies.py <full.pmx or folder> [...] [--nude <nude.pmx>] [--out <pmx>]
                           [--backup <dir> --base <dir>] [--dry-run] [--pmx-module <mmd_tools/core/pmx/__init__.py>]

  --nude     the nude version's PMX (normals); default: <...>_nude\\<...>_nude.pmx beside <...>_full\\<...>_full.pmx
             (also for <...>_full_bustB.pmx); none = smooth normals of the nude shape
  --out      write here instead of over the input (one input only)
  --backup   copy each original to <dir>\\<its path relative to --base> before it is replaced
A folder is searched for *_full.pmx and *_full_bustB.pmx.  Needs Python + numpy + mmd_tools' stand-alone PMX module
(no Blender).  Saving through that module is byte-exact when written into the PMX's own folder (texture paths are
written relative to it), so the file is written there under a temporary name and then moved over the original.
Prints one line per file and PMX_TWO_BODIES=<json> at the end.
"""
import argparse
import copy
import glob
import importlib.util
import json
import logging
import os
import shutil
import sys
import time

import numpy as np

BODY = "裸体形状"
OUTFIT = "衣服非表示_材質"
SUFFIX = "_nude"
PLACE = 2.5e-3      # PMX units (x0.08 = 0.2 mm): nude copy vertex vs nude PMX vertex
PLACE_WIDE = 2.5e-2  # second pass for the rest (2 mm; m02's shoulder: the full's own shape 0.2-1.4 mm off the nude's)
UV = 1e-3


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


def nude_guess(path):
    folder, name = os.path.split(os.path.abspath(path))
    if "_full" not in name:
        return ""
    stem = name.replace("_full_bustB.pmx", "_full.pmx").replace("_full", "_nude")
    guess = os.path.join(os.path.dirname(folder), os.path.basename(folder).replace("_full", "_nude"), stem)
    return guess if os.path.isfile(guess) else ""


def smooth_normals(co, faces):
    """Angle-weighted smooth normal per vertex of the triangles faces over positions co, vertices at the same place
    welded (the mesh is split along UV seams)."""
    _, ids = np.unique(np.round(co / 1e-5).astype(np.int64), axis=0, return_inverse=True)
    ids = ids.ravel()
    tri = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    p = co[tri]
    face = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    face /= np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-20)
    acc = np.zeros((ids.max() + 1, 3))
    for k in range(3):
        u, v = p[:, (k + 1) % 3] - p[:, k], p[:, (k + 2) % 3] - p[:, k]
        cos = (u * v).sum(1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-20)
        np.add.at(acc, ids[tri[:, k]], face * np.arccos(np.clip(cos, -1.0, 1.0))[:, None])
    out = acc[ids]
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-20)


def nude_normals(co, uv, nude):
    """Per copy vertex (nude position co, uv): the normal of the nearest nude PMX vertex with the same UV within
    PLACE, then for the rest within PLACE_WIDE.  Returns the normals, NaN rows where none matched."""
    out = np.full((len(co), 3), np.nan)
    if nude is None:
        return out
    nco = np.array([v.co for v in nude.vertices], dtype=np.float64)
    nuv = np.array([v.uv for v in nude.vertices], dtype=np.float64)
    nno = np.array([v.normal for v in nude.vertices], dtype=np.float64)
    near = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)]
    for tol in (PLACE, PLACE_WIDE):
        todo = np.nonzero(np.isnan(out[:, 0]))[0]
        if not len(todo):
            break
        cells = {}
        for j, key in enumerate(map(tuple, np.floor(nco / tol).astype(np.int64))):
            cells.setdefault(key, []).append(j)
        for i in todo:
            c, u = co[i], uv[i]
            x, y, z = np.floor(c / tol).astype(np.int64)
            best, bd = -1, tol
            for dx, dy, dz in near:
                for j in cells.get((x + dx, y + dy, z + dz), ()):
                    if abs(nuv[j, 0] - u[0]) > UV or abs(nuv[j, 1] - u[1]) > UV:
                        continue
                    d = float(np.linalg.norm(nco[j] - c))
                    if d <= bd:
                        best, bd = j, d
            if best >= 0:
                out[i] = nno[best]
    return out


def convert(pmx, model, nude):
    """Two bodies in model (in place).  Returns a report; report["status"] is "ok", "already" or an error."""
    names = [m.name for m in model.morphs]
    if BODY not in names:
        return {"status": "no %s morph" % BODY}
    body_i = names.index(BODY)
    body = model.morphs[body_i]
    if isinstance(body, pmx.MaterialMorph):
        return {"status": "already"}
    if not isinstance(body, pmx.VertexMorph):
        return {"status": "%s is a %s" % (BODY, type(body).__name__)}
    outfit_morph = next((m for m in model.morphs if m.name == OUTFIT and isinstance(m, pmx.MaterialMorph)), None)
    if outfit_morph is None:
        return {"status": "no %s morph" % OUTFIT}
    outfit = {o.index for o in outfit_morph.offsets if o.offset_type == 0 and o.diffuse_offset[3] < 1e-6}
    moved = {o.index: np.array(o.offset, dtype=np.float64) for o in body.offsets}
    starts, s = [], 0
    for mat in model.materials:
        starts.append(s)
        s += mat.vertex_count // 3
    faces = model.faces
    slots = [k for k, mat in enumerate(model.materials) if k not in outfit and any(
        v in moved for f in faces[starts[k]:starts[k] + mat.vertex_count // 3] for v in f)]
    if not slots:
        return {"status": "%s moves no body material" % BODY}

    # the copies: per body material its faces' vertices, appended at the end
    n_old = len(model.vertices)
    sources, copy_faces, per_slot = [], {}, {}
    for k in slots:
        local = {}
        new_f = []
        for f in faces[starts[k]:starts[k] + model.materials[k].vertex_count // 3]:
            tri = []
            for v in f:
                if v not in local:
                    local[v] = n_old + len(sources)
                    sources.append(v)
                tri.append(local[v])
            new_f.append(tuple(tri))
        copy_faces[k] = new_f
        per_slot[k] = local
    src = np.array(sources, dtype=np.int64)
    rest = np.array([model.vertices[v].co for v in sources], dtype=np.float64)
    shift = np.array([moved.get(v, np.zeros(3)) for v in sources])
    nude_co = rest + shift
    uv = np.array([model.vertices[v].uv for v in sources], dtype=np.float64)
    normals = nude_normals(nude_co, uv, nude)
    matched = int((~np.isnan(normals[:, 0])).sum())
    if matched < len(sources):
        all_faces = np.array([t for k in slots for t in copy_faces[k]], dtype=np.int64) - n_old
        smooth = smooth_normals(nude_co, all_faces)
        miss = np.isnan(normals[:, 0])
        normals[miss] = smooth[miss]
    for i, v in enumerate(sources):
        vert = copy.deepcopy(model.vertices[v])
        vert.co = [float(x) for x in nude_co[i]]
        vert.normal = [float(x) for x in normals[i] / max(np.linalg.norm(normals[i]), 1e-20)]
        model.vertices.append(vert)

    # materials and faces: each copy right after its source (draw order: the body before hair, lashes ...)
    new_mats, new_faces, remap, copy_of = [], [], {}, {}
    for k, mat in enumerate(model.materials):
        remap[k] = len(new_mats)
        new_mats.append(mat)
        new_faces.extend(faces[starts[k]:starts[k] + mat.vertex_count // 3])
        if k in copy_faces:
            dup = copy.deepcopy(mat)
            dup.name = mat.name + SUFFIX
            dup.name_e = (mat.name_e + SUFFIX) if mat.name_e else ""
            dup.diffuse = list(mat.diffuse[:3]) + [0.0]
            dup.edge_color = list(mat.edge_color[:3]) + [0.0]
            dup.vertex_count = len(copy_faces[k]) * 3
            copy_of[k] = len(new_mats)
            new_mats.append(dup)
            new_faces.extend(copy_faces[k])
    alpha = {k: float(model.materials[k].diffuse[3]) for k in slots}
    edge = {k: float(model.materials[k].edge_color[3]) for k in slots}
    model.materials, model.faces = new_mats, new_faces

    # morphs: offsets / entries onto the copies, material indices shifted, 裸体形状 -> the swap
    copies_of_vertex = {}
    for k in slots:
        for v, c in per_slot[k].items():
            copies_of_vertex.setdefault(v, []).append(c)
    added = {"vertex": 0, "uv": 0, "material": 0}
    for i, m in enumerate(model.morphs):
        if i == body_i:
            continue
        if isinstance(m, (pmx.VertexMorph, pmx.UVMorph)):
            extra = []
            for o in m.offsets:
                for c in copies_of_vertex.get(o.index, ()):
                    dup = copy.copy(o)
                    dup.index = c
                    extra.append(dup)
            m.offsets.extend(extra)
            added["vertex" if isinstance(m, pmx.VertexMorph) else "uv"] += len(extra)
        elif isinstance(m, pmx.MaterialMorph):
            extra = []
            for o in m.offsets:
                old = o.index
                if old >= 0:
                    o.index = remap[old]
                    if old in copy_of:
                        dup = copy.copy(o)
                        dup.index = copy_of[old]
                        extra.append(dup)
            m.offsets.extend(extra)
            added["material"] += len(extra)
    swap = pmx.MaterialMorph(body.name, body.name_e, body.category)
    for k in slots:
        for target, mode in ((remap[k], 0), (copy_of[k], 1)):
            o = pmx.MaterialMorphOffset()
            o.index, o.offset_type = target, mode
            if mode == 0:       # dressed body: alpha x 0, the rest x 1
                o.diffuse_offset, o.specular_offset, o.shininess_offset = [1.0, 1.0, 1.0, 0.0], [1.0] * 3, 1.0
                o.ambient_offset, o.edge_color_offset, o.edge_size_offset = [1.0] * 3, [1.0, 1.0, 1.0, 0.0], 1.0
                o.texture_factor = o.sphere_texture_factor = o.toon_texture_factor = [1.0] * 4
            else:               # nude copy: the alpha the file took away, added back
                o.diffuse_offset, o.specular_offset, o.shininess_offset = [0.0, 0.0, 0.0, alpha[k]], [0.0] * 3, 0.0
                o.ambient_offset, o.edge_color_offset, o.edge_size_offset = [0.0] * 3, [0.0, 0.0, 0.0, edge[k]], 0.0
                o.texture_factor = o.sphere_texture_factor = o.toon_texture_factor = [0.0] * 4
            swap.offsets.append(o)
    model.morphs[body_i] = swap
    return {"status": "ok", "body_materials": [model.materials[remap[k]].name for k in slots],
            "copied_vertices": len(sources), "copied_faces": sum(len(f) for f in copy_faces.values()),
            "moved_by_body_morph": len(moved), "nude_normals": matched, "smooth_normals": len(sources) - matched,
            "offsets_added": added, "vertices": len(model.vertices), "materials": len(model.materials)}


def two_bodies(pmx, path, nude_path, out, backup, base, dry, nude_cache):
    model = pmx.load(path)
    nude = None
    if nude_path:
        if nude_path not in nude_cache:
            nude_cache.clear()
            nude_cache[nude_path] = pmx.load(nude_path)
        nude = nude_cache[nude_path]
    report = convert(pmx, model, nude)
    report.update(pmx=path, nude=nude_path or None)
    if report["status"] != "ok" or dry:
        return report
    target = os.path.abspath(out or path)
    tmp = os.path.join(os.path.dirname(target), os.path.basename(target)[:-4] + ".two_bodies.tmp.pmx")
    pmx.save(tmp, model, add_uv_count=getattr(model.header, "additional_uvs", 0))
    check = pmx.load(tmp)
    morph = next(m for m in check.morphs if m.name == BODY)
    if not isinstance(morph, pmx.MaterialMorph) or len(check.vertices) != report["vertices"] \
            or len(check.materials) != report["materials"]:
        os.remove(tmp)
        report["status"] = "written file did not read back right - original kept"
        return report
    if backup and os.path.isfile(target):
        dest = os.path.join(backup, os.path.relpath(target, base) if base else os.path.basename(target))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.isfile(dest):
            shutil.copy2(target, dest)
        report["backup"] = dest
    os.replace(tmp, target)
    report["written"] = target
    note_in_report(target, report)
    return report


def note_in_report(target, report):
    """The conversion recorded as "two_bodies" in the export report beside the PMX (<stem>.report.json, one per
    folder: the bust B file shares its full version's)."""
    stem = os.path.basename(target)[:-4]
    path = os.path.join(os.path.dirname(target), (stem[:-6] if stem.endswith("_bustB") else stem) + ".report.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except ValueError:
        return
    keys = ("body_materials", "copied_vertices", "copied_faces", "nude_normals", "smooth_normals", "nude")
    entry = dict(data.get("two_bodies") or {}, **{k: report.get(k) for k in keys})
    entry.setdefault("files", [])
    if os.path.basename(target) not in entry["files"]:
        entry["files"].append(os.path.basename(target))
    entry["date"] = time.strftime("%Y-%m-%d")
    data["two_bodies"] = entry
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def pmx_files(paths):
    """Inputs in order, a folder's full + bust B files next to each other (they share the nude PMX: read once)."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "**", "*_full.pmx"), recursive=True)
                          + glob.glob(os.path.join(p, "**", "*_full_bustB.pmx"), recursive=True))
        else:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--nude", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--backup", default="")
    ap.add_argument("--base", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pmx-module", default="")
    a = ap.parse_args()
    files = pmx_files(a.paths)
    if a.out and len(files) != 1:
        ap.error("--out takes one input file")
    pmx = pmx_module(a.pmx_module)
    results, cache = [], {}
    for path in files:
        nude = "" if a.nude == "none" else (a.nude or nude_guess(path))
        try:
            rep = two_bodies(pmx, path, nude, a.out, a.backup, a.base, a.dry_run, cache)
        except Exception as exc:                # one bad file must not stop a batch
            rep = {"pmx": path, "status": "error: %s" % exc}
        results.append(rep)
        print("%-8s %s  %s" % (rep["status"] if len(rep["status"]) < 9 else "FAILED", os.path.basename(path),
                               "" if rep["status"] in ("ok", "already") else rep["status"]), flush=True)
    counts = {}
    for r in results:
        counts[r["status"] if r["status"] in ("ok", "already") else "other"] = counts.get(
            r["status"] if r["status"] in ("ok", "already") else "other", 0) + 1
    print("PMX_TWO_BODIES=" + json.dumps({"counts": counts, "results": results}, ensure_ascii=True))
    return 0 if not counts.get("other") else 1


if __name__ == "__main__":
    sys.exit(main())
