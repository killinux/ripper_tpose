"""Graft a garment from one PMX onto another: its mesh (whole connected pieces that ride the garment bones), the garment
bones, their rigid bodies and joints, the material(s) and textures.  Both models are MMD-converted rigs with standard
bone names (ROE exports); weights on bones the target lacks fall back to the nearest ancestor it has.

    python pmx_graft.py donor.pmx target.pmx out.pmx --bones "^Riband_M" [--min-weight 0.3]
        [--align 下半身] [--offset dx,dy,dz] [--material-name g05_skirt] [--hide-morph 衣服非表示_材質]
        [--skip-material "pc_g01_nk_body,..."] [--dry-run]

- garment bones: every donor bone matching --bones, plus the bones between them and the first ancestor the target
  has (a Dummy root), added after the target's bones, parented to the same-named target bone;
- the mesh: per donor material, the connected pieces (faces sharing vertices) holding a vertex with >= --min-weight
  on garment bones; each donor material becomes one new material "<--material-name>[_n]" with its texture copied
  into the output folder's textures\\;
- positions move by target(--align) - donor(--align) (+ --offset, PMX units); normals as they are;
- rigid bodies on garment bones and the joints between them come along; a joint to a donor body on a non-garment bone
  is re-hung on the target's body on the same-named bone;
- the new material(s) join the target's --hide-morph material morph (the full's outfit switch) like its outfit;
- the new bones go to the display frame "other" (or the last one).
Needs Python + numpy + mmd_tools' pmx module (as scripts/mmd_physics/cloth_collision_pmx.py).
"""
import argparse
import copy
import os
import re
import shutil
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_collision_pmx as cc  # noqa: E402


def material_faces(model):
    out, start = [], 0
    for mi, mt in enumerate(model.materials):
        n = mt.vertex_count // 3
        out.append(list(range(start // 3, start // 3 + n)))
        start += mt.vertex_count
    return out


def islands(faces, face_ids):
    """Connected pieces among face_ids (faces sharing a vertex)."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in face_ids:
        a, b, c = faces[f]
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    groups = defaultdict(list)
    for f in face_ids:
        groups[find(faces[f][0])].append(f)
    return list(groups.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("donor")
    ap.add_argument("target")
    ap.add_argument("out")
    ap.add_argument("--bones", required=True, help="regex of the garment's bones in the donor")
    ap.add_argument("--min-weight", type=float, default=0.3)
    ap.add_argument("--align", default="下半身")
    ap.add_argument("--offset", default="0,0,0")
    ap.add_argument("--material-name", default="graft")
    ap.add_argument("--hide-morph", default="衣服非表示_材質")
    ap.add_argument("--skip-material", default="", help="donor materials never taken (comma separated)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pmx = cc.load_pmx_module(cc.find_pmx_module())
    D, T = pmx.load(args.donor), pmx.load(args.target)
    dn = [b.name for b in D.bones]
    tn = {b.name: i for i, b in enumerate(T.bones)}
    pat = re.compile(args.bones)
    skip = {s.strip() for s in args.skip_material.split(",") if s.strip()}

    # garment bones: the matches and their ancestors up to the first bone the target has
    garment = set(i for i, n in enumerate(dn) if pat.search(n))
    for i in list(garment):
        p = D.bones[i].parent
        while p is not None and p >= 0 and dn[p] not in tn and p not in garment:
            garment.add(p)
            p = D.bones[p].parent
    garment = sorted(garment)                       # donor order: parents first in ROE exports
    clash = [dn[i] for i in garment if dn[i] in tn]
    if clash:
        raise SystemExit("target already has bones named %s" % clash[:5])

    def target_of(i):
        """donor bone -> target bone index (garment bones resolved later)"""
        while i is not None and i >= 0:
            if dn[i] in tn:
                return tn[dn[i]]
            i = D.bones[i].parent
        return tn.get("下半身", 0)

    shift = np.array(T.bones[tn[args.align]].location) - np.array(D.bones[dn.index(args.align)].location) \
        + np.array([float(x) for x in args.offset.split(",")])
    print("garment bones: %d (%s ...); shift %s" % (len(garment), ", ".join(dn[i] for i in garment[:6]),
                                                    np.round(shift * 8, 2).tolist()))

    # the mesh
    gset = set(garment)
    on_garment = np.zeros(len(D.vertices))
    for i, v in enumerate(D.vertices):
        on_garment[i] = sum(w for b, w in cc.weights_of(pmx, v) if b in gset)
    mfaces = material_faces(D)
    take = []                                       # (donor material index, [face ids])
    for mi, fids in enumerate(mfaces):
        if D.materials[mi].name in skip or not fids:
            continue
        hit = [f for f in fids if any(on_garment[v] >= args.min_weight for v in D.faces[f])]
        if not hit:
            continue
        pieces = [p for p in islands(D.faces, fids) if any(on_garment[v] >= args.min_weight for f in p for v in D.faces[f])]
        faces = sorted(f for p in pieces for f in p)
        verts = sorted({v for f in faces for v in D.faces[f]})
        ride = float(np.mean([on_garment[v] >= args.min_weight for v in verts]))
        print("  %-26s %d pieces, %d faces, %d vertices (%.0f%% on the garment bones)" % (
            D.materials[mi].name, len(pieces), len(faces), len(verts), ride * 100))
        take.append((mi, faces))
    if args.dry_run:
        return 0

    # bones
    bmap = {}
    for i in garment:
        bmap[i] = len(T.bones) + len(bmap)
    new_bones = []
    for i in garment:
        b = copy.deepcopy(D.bones[i])
        b.location = [float(x) for x in np.array(b.location) + shift]
        p = b.parent
        b.parent = bmap[p] if p in bmap else target_of(p)
        if isinstance(b.displayConnection, int):
            b.displayConnection = bmap.get(b.displayConnection, -1) if b.displayConnection >= 0 else -1
        if b.additionalTransform:
            t, v = b.additionalTransform
            b.additionalTransform = (bmap[t] if t in bmap else target_of(t), v)
        if b.isIK:
            raise SystemExit("IK bone in the garment: %s" % b.name)
        new_bones.append(b)
    T.bones.extend(new_bones)

    def map_bone(i):
        return bmap[i] if i in bmap else target_of(i)

    # vertices + faces + materials
    out_dir = os.path.dirname(os.path.abspath(args.out))
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)

    def place(src):
        """A real copy of src in the output's textures folder (never a link); a different file of the same name gets
        a suffix.  Returns the new path."""
        base, ext = os.path.splitext(os.path.basename(src))
        dst, k = os.path.join(tex_dir, base + ext), 1
        while os.path.exists(dst) and os.path.getsize(dst) != os.path.getsize(src):
            dst, k = os.path.join(tex_dir, "%s_%d%s" % (base, k, ext)), k + 1
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        return dst
    if os.path.normcase(out_dir) != os.path.normcase(os.path.dirname(os.path.abspath(args.target))):
        for t in T.textures:                       # the target's own textures: the output folder stands alone
            if os.path.isfile(t.path):
                t.path = place(t.path)
    tex_index = {}
    n_uv = T.header.additional_uvs
    new_mats = []
    for k, (mi, faces) in enumerate(take):
        vmap = {}
        for f in faces:
            for v in D.faces[f]:
                if v in vmap:
                    continue
                src = D.vertices[v]
                nv = copy.deepcopy(src)
                nv.co = [float(x) for x in np.array(src.co) + shift]
                w = nv.weight
                if isinstance(w.bones, (list, tuple)):
                    w.bones = [map_bone(b) if b is not None and b >= 0 else b for b in w.bones]
                if isinstance(w.weights, pmx.BoneWeightSDEF):
                    for attr in ("c", "r0", "r1"):
                        val = getattr(w.weights, attr, None)
                        if val is not None:
                            setattr(w.weights, attr, [float(x) for x in np.array(val) + shift])
                nv.additional_uvs = (list(nv.additional_uvs) + [[0.0, 0.0, 0.0, 0.0]] * n_uv)[:n_uv]
                vmap[v] = len(T.vertices)
                T.vertices.append(nv)
        for f in faces:
            T.faces.append(tuple(vmap[v] for v in D.faces[f]))
        mt = copy.deepcopy(D.materials[mi])
        mt.name = mt.name_e = args.material_name + ("" if len(take) == 1 else "_%d" % (k + 1))
        mt.vertex_count = 3 * len(faces)
        for attr in ("texture", "sphere_texture") + (() if mt.is_shared_toon_texture else ("toon_texture",)):
            ti = getattr(mt, attr)
            if ti is None or ti < 0:
                continue
            src = D.textures[ti].path
            if src not in tex_index:
                t = pmx.Texture()
                t.path = place(src)
                T.textures.append(t)
                tex_index[src] = len(T.textures) - 1
            setattr(mt, attr, tex_index[src])
        T.materials.append(mt)
        new_mats.append(len(T.materials) - 1)
        print("  material %s: %d faces, %d vertices, texture %s" % (mt.name, len(faces), len(vmap),
                                                                    os.path.basename(D.textures[D.materials[mi].texture].path)
                                                                    if D.materials[mi].texture >= 0 else "-"))

    # the full's outfit switch
    hide = next((mo for mo in T.morphs if mo.name == args.hide_morph), None)
    if hide is not None and hide.offsets:
        for mi in new_mats:
            o = copy.deepcopy(hide.offsets[0])
            o.index = mi
            hide.offsets.append(o)
        print("  %s now hides %d materials" % (hide.name, len(hide.offsets)))
    else:
        print("  no material morph %s in the target" % args.hide_morph)

    # display frame
    frame = next((d for d in T.display if d.name.lower() == "other"), T.display[-1])
    frame.data.extend((0, bmap[i]) for i in garment)

    # physics
    t_body = {}
    for i, r in enumerate(T.rigids):
        if r.bone is not None and r.bone >= 0:
            t_body.setdefault(T.bones[r.bone].name, i)
    rmap = {}
    for i, r in enumerate(D.rigids):
        if r.bone is not None and r.bone in bmap:
            nr = copy.deepcopy(r)
            nr.bone = bmap[r.bone]
            nr.location = [float(x) for x in np.array(r.location) + shift]
            rmap[i] = len(T.rigids)
            T.rigids.append(nr)
    joints = 0
    for j in D.joints:
        a, b = j.src_rigid, j.dest_rigid
        if a not in rmap and b not in rmap:
            continue

        def end(x):
            if x in rmap:
                return rmap[x]
            r = D.rigids[x]
            name = dn[r.bone] if r.bone is not None and r.bone >= 0 else ""
            tb = T.bones[target_of(r.bone)].name if r.bone is not None and r.bone >= 0 else ""
            for n in (name, tb):
                if n in t_body:
                    return t_body[n]
            raise SystemExit("joint %s: no target body for %s" % (j.name, r.name))
        nj = copy.deepcopy(j)
        nj.src_rigid, nj.dest_rigid = end(a), end(b)
        nj.location = [float(x) for x in np.array(j.location) + shift]
        T.joints.append(nj)
        joints += 1
    print("  physics: %d rigid bodies, %d joints" % (len(rmap), joints))
    pmx.save(args.out, T, add_uv_count=T.header.additional_uvs)
    back = pmx.load(args.out)
    missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
    print("wrote %s: %d vertices, %d materials, %d bones, %d rigids, %d joints; textures missing %d %s" % (
        args.out, len(back.vertices), len(back.materials), len(back.bones), len(back.rigids), len(back.joints),
        len(missing), missing[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
