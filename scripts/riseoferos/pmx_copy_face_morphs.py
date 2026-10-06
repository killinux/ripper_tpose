"""Rise of Eros: give a PMX the face expressions of another PMX of the same family.

The seasonal family outfits (pc_a_swimsuit01, pc_b_halloween01, pc_e_xmas01 ...) come with a head but without the
32 face bones every numbered outfit has, so the exporter's expressions (bones posed, then baked to vertex morphs)
have nothing to pose and the PMX has none: the face stays still through a dance's blinks and lip sync.  Their head
is the family's own mesh - the same shape, a few vertices split differently - so the donor's vertex morphs carry
over: every vertex of a receiving face part takes the offsets of its counterpart in the donor's same part - the
vertex with the same texture coordinate close by, else the one on top of it that faces the same way, else the
nearest ones weighted by distance and facing (the brows, cut differently, also look at the forehead skin) - faded
to nothing for vertices more than --reach away from any donor vertex.

    python pmx_copy_face_morphs.py donor.pmx in.pmx out.pmx [--parts face,eye_portable,lash,brow,eye_overlay]
    python pmx_copy_face_morphs.py --family in.pmx out.pmx       # donor: the family's pc_<letter>01_hd on E:

Only vertex morphs that move a face part are copied, with their names, English names and panels; they go after
the receiver's own morphs and into its 表情 display frame.  A morph whose name the receiver already has is left
alone (--replace overwrites it).  Needs Python, numpy and the pmx module inside mmd_tools (no Blender).
Prints what it did; --dry-run writes nothing.
"""
import argparse
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "clothes_burst"))
from pmx_nude_switch import pmx_module  # noqa: E402

PARTS = ("face", "eye_portable", "lash", "brow", "eye_overlay")
# where a part looks for its donor vertices: the brows are cut differently from the family's (196 vs 154 vertices on
# Inase, up to 8 mm apart), the forehead skin under them moves the same way
SOURCES = {"brow": ("brow", "face")}
ARCHIVE = r"E:\game_export\RiseOfEros"
NAMES = {"a": "Inase", "b": "Kart", "c": "Misa", "d": "Erin", "e": "Miri", "f": "Rana", "g": "Luf", "h": "Fen",
         "i": "Sera", "j": "Lynn", "k": "Keleira", "l": "SFox", "m": "Amano"}   # = scripts/archive/games.py
NEAREST = 8
SNAP = 0.005            # PMX units (0.4 mm): a donor vertex this close is the same vertex
UV_TOL = 0.001          # same texture coordinate ...
UV_GAP = 0.06           # ... and within 4.8 mm: the same vertex, moved (Inase's seasonal teeth: 2.6 mm)


FACE = re.compile(r"(?:face|pc_[a-z]\d*(?:_fm)?_nk_face)(?:_nude)?")


def part_key(name):
    """The face part a material is: the main export calls the head 'face', complete_nude.py's versions
    'pc_a_nk_face' (and the full version's second copy 'pc_a_nk_face_nude')."""
    n = name.lower()
    if FACE.fullmatch(n):
        return "face"
    return n[:-5] if n.endswith("_nude") else n


def part_vertices(model):
    """{material name: sorted vertex indices its faces use}."""
    faces = np.array(model.faces).reshape(-1, 3)
    out, start = {}, 0
    for mat in model.materials:
        verts = np.unique(faces[start // 3:(start + mat.vertex_count) // 3])
        out.setdefault(mat.name, set()).update(verts.tolist())
        start += mat.vertex_count
    return {k: np.array(sorted(v)) for k, v in out.items()}


def nearest(points, ref, k):
    """(distances, indices) of the k nearest rows of ref for every row of points (brute force in chunks)."""
    k = min(k, len(ref))
    dist = np.empty((len(points), k))
    idx = np.empty((len(points), k), int)
    for i in range(0, len(points), 512):
        d2 = ((points[i:i + 512, None, :] - ref[None, :, :]) ** 2).sum(2)
        part = np.argpartition(d2, k - 1, axis=1)[:, :k]
        rows = np.arange(len(part))[:, None]
        order = np.argsort(d2[rows, part], axis=1)
        idx[i:i + 512] = part[rows, order]
        dist[i:i + 512] = np.sqrt(d2[rows, idx[i:i + 512]])
    return dist, idx


def uv_counterparts(ruv, rco, duv, dco, tol=UV_TOL, max_gap=UV_GAP):
    """Per receiving vertex: the donor vertex (local index) with the same texture coordinate within max_gap in
    space - the nearest such one - else -1."""
    out = np.full(len(ruv), -1)
    for i in range(0, len(ruv), 512):
        du = np.abs(ruv[i:i + 512, None, :] - duv[None, :, :]).max(2)
        d3 = np.sqrt(((rco[i:i + 512, None, :] - dco[None, :, :]) ** 2).sum(2))
        d3 = np.where((du < tol) & (d3 < max_gap), d3, np.inf)
        best = d3.argmin(1)
        ok = np.isfinite(d3[np.arange(len(best)), best])
        out[i:i + 512][ok] = best[ok]
    return out


def family_donor(path):
    """The family's numbered base outfit on E: (pc_a_swimsuit01_hd -> Inase\\pmx\\pc_a01_hd\\pc_a01_hd.pmx)."""
    m = re.match(r"pc_([a-z])", os.path.basename(path).lower())
    if not m:
        raise SystemExit("--family: cannot tell the family from %s" % os.path.basename(path))
    letter = m.group(1)
    donor = os.path.join(ARCHIVE, NAMES.get(letter, letter), "pmx", "pc_%s01_hd" % letter, "pc_%s01_hd.pmx" % letter)
    if not os.path.isfile(donor):
        raise SystemExit("--family: no donor at %s" % donor)
    return donor


def copy_morphs(donor, model, parts=PARTS, reach=0.25, replace=False):
    dparts = {}                                  # the donor's parts by key (its materials of one part merged)
    for name, verts in part_vertices(donor).items():
        key = part_key(name)
        dparts[key] = np.union1d(dparts[key], verts) if key in dparts else verts
    # every receiving material of a wanted part on its own (the full version has the head twice)
    rmats = [(name, part_key(name), verts) for name, verts in part_vertices(model).items()
             if part_key(name) in parts and part_key(name) in dparts]
    dco = np.array([v.co for v in donor.vertices], float)
    rco = np.array([v.co for v in model.vertices], float)
    dno = np.array([v.normal for v in donor.vertices], float)
    rno = np.array([v.normal for v in model.vertices], float)
    duv = np.array([v.uv for v in donor.vertices], float)
    ruv = np.array([v.uv for v in model.vertices], float)
    if not any(key == "face" for _name, key, _v in rmats):
        raise SystemExit("no face material in both models (donor parts: %s; receiver: %s)" % (
            ", ".join(sorted(dparts)), ", ".join(m.name for m in model.materials)))
    # per part: the receiving vertices, their donor neighbours (global indices) and weights, by three rules:
    # 1. the same vertex by its texture coordinate: Inase's seasonal head carries the teeth and tongue 2.6 mm off
    #    the family's (its 1,592 mouth vertices sit exactly that far from theirs, same UV) - by position alone an
    #    upper tooth would follow the lower ones;
    # 2. a donor vertex on top of it (within SNAP): a closed mouth puts the upper lip's edge on the lower lip's, so
    #    of those the one facing its own way, alone - blending them mixes a still lip with one the jaw carries;
    # 3. else the nearest donor vertices, by distance AND by facing alike.
    maps, report = [], {}
    for name, p, rv in rmats:
        dv = np.unique(np.concatenate([dparts[s] for s in SOURCES.get(p, (p,)) if s in dparts]))
        dist, idx = nearest(rco[rv], dco[dv], NEAREST)
        facing = np.clip(np.einsum("ij,ikj->ik", rno[rv], dno[dv][idx]), 0.0, 1.0)
        w = facing ** 4 / np.maximum(dist, 1e-6) ** 2
        blind = w.sum(1) < 1e-12                                        # nothing faces its way: distance only
        w[blind] = 1.0 / np.maximum(dist[blind], 1e-6) ** 2
        close = dist < np.maximum(SNAP, 3.0 * dist[:, :1])               # the donor vertices on top of it
        on_top = dist[:, 0] < SNAP
        pick = np.argmax(np.where(close, facing, -1.0), axis=1)
        w[on_top] = 0.0
        w[np.flatnonzero(on_top), pick[on_top]] = 1.0
        nb = dv[idx]
        own = dparts[p]                                                 # rule 1 only within the same part
        by_uv = uv_counterparts(ruv[rv], rco[rv], duv[own], dco[own])
        hit = by_uv >= 0
        nb[hit, 0] = own[by_uv[hit]]
        w[hit] = 0.0
        w[hit, 0] = 1.0
        w /= w.sum(1, keepdims=True)
        gap = np.where(hit, np.linalg.norm(rco[rv] - dco[nb[:, 0]], axis=1), dist[:, 0])
        fade = np.clip((reach - gap) / (0.5 * reach), 0.0, 1.0)         # 1 inside reach/2, 0 beyond reach
        maps.append((rv, nb, w * fade[:, None]))
        report[name] = {"vertices": int(len(rv)), "donor": int(len(dv)),
                     "median_mm": round(float(np.median(dist[:, 0])) * 80.0, 2),
                     "max_mm": round(float(dist[:, 0].max()) * 80.0, 2), "faded": int((fade < 1.0).sum()),
                     "by_uv": int(hit.sum()), "on_top": int((on_top & ~hit).sum()),
                     "on_top_by_facing": int((on_top & ~hit & (pick > 0)).sum())}
    donor_part = np.zeros(len(dco), bool)
    for p in {key for _name, key, _v in rmats}:
        donor_part[dparts[p]] = True
    have = {mo.name: i for i, mo in enumerate(model.morphs)}
    vertex_morph = type(next(mo for mo in donor.morphs if type(mo).__name__ == "VertexMorph"))
    offset_cls = type(next(mo for mo in donor.morphs if type(mo).__name__ == "VertexMorph").offsets[0])
    added, replaced, skipped = [], [], []
    for mo in donor.morphs:
        if type(mo).__name__ != "VertexMorph":
            continue
        dense = np.zeros((len(dco), 3))
        for o in mo.offsets:
            dense[o.index] = o.offset
        if not np.abs(dense[donor_part]).max(initial=0.0) > 1e-7:
            continue                                    # moves nothing of the face
        if mo.name in have and not replace:
            skipped.append(mo.name)
            continue
        out = vertex_morph(mo.name, mo.name_e, mo.category)
        for rv, nb, w in maps:
            vals = (dense[nb] * w[:, :, None]).sum(1)
            for vi, val in zip(rv, vals):
                if np.abs(val).max() > 1e-6:
                    o = offset_cls()
                    o.index = int(vi)
                    o.offset = [float(x) for x in val]
                    out.offsets.append(o)
        if mo.name in have:
            model.morphs[have[mo.name]] = out
            replaced.append(mo.name)
        else:
            model.morphs.append(out)
            have[mo.name] = len(model.morphs) - 1
            added.append(mo.name)
    frame = next((d for d in model.display if d.name == "表情"), None)
    if frame is None:
        frame = type(model.display[0])() if model.display else None
        if frame is not None:
            frame.name, frame.name_e, frame.isSpecial = "表情", "Exp", True
            model.display.insert(min(1, len(model.display)), frame)
    if frame is not None:
        listed = {i for t, i in frame.data if t == 1}
        frame.data += [(1, have[n]) for n in added if have[n] not in listed]
    return {"parts": report, "added": len(added), "replaced": len(replaced), "skipped_existing": skipped,
            "morphs": added + replaced}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", help="donor.pmx in.pmx out.pmx, or with --family: in.pmx out.pmx")
    ap.add_argument("--family", action="store_true", help="donor = the family's pc_<letter>01_hd.pmx on E:")
    ap.add_argument("--parts", default=",".join(PARTS))
    ap.add_argument("--reach", type=float, default=0.25, help="PMX units (1 = 8 cm): offsets fade out to here")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.family:
        if len(a.paths) != 2:
            raise SystemExit("--family takes in.pmx out.pmx")
        donor_path, (src, dst) = family_donor(a.paths[0]), a.paths
    else:
        if len(a.paths) != 3:
            raise SystemExit("give donor.pmx in.pmx out.pmx")
        donor_path, src, dst = a.paths
    pmx = pmx_module()
    donor, model = pmx.load(donor_path), pmx.load(src)
    result = copy_morphs(donor, model, [p.strip() for p in a.parts.split(",") if p.strip()], a.reach, a.replace)
    print("donor:", donor_path)
    for key, value in result.items():
        if key != "morphs":
            print("%s: %s" % (key, value))
    if a.dry_run:
        return
    src_dir, out_dir = os.path.dirname(os.path.abspath(src)), os.path.dirname(os.path.abspath(dst))
    for texture in model.textures:
        local = os.path.join(out_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    tmp = dst + ".part"
    pmx.save(tmp, model, add_uv_count=model.header.additional_uvs)
    os.replace(tmp, dst)
    print("wrote", dst)


if __name__ == "__main__":
    main()
