# -*- coding: utf-8 -*-
"""Pick the parts of a PMX model: drop materials together with everything that only served them.

Deleting a material in PMXEditor, or its faces in Blender, removes faces and vertices only: the piece's bones, rigid
bodies and joints stay (an invisible skirt keeps swinging and can push other rigid bodies), and so do its morph
entries.  remove_parts() drops a set of materials with
  - their vertices (unless a kept face uses them),
  - the bones only those vertices were weighted to, the weightless bones under them (chain tips) and the weightless
    bones all of whose children go (chain roots) - never an MMD standard bone, and not when something kept needs
    one: a kept bone's parent, IK target / link or grant parent, or a body that kept physics hangs from,
  - the rigid bodies on those bones and every joint touching one,
  - their entries in vertex / UV / bone / material / group morphs; morphs left empty go, display frames follow,
  - the textures that only the removed materials used,
and keeps body swaps working.  A swap is a material morph that both hides materials (multiply alpha by 0) and shows
others (add alpha), like ROE full's 裸体形状 (fitted body out, nude copy in): when every material it hides is removed,
what it shows becomes visible by default; when everything it shows is removed, it stops hiding.

Runs in Blender (mmd_tools' pmx module) or a plain Python (the module core.pmx_module() finds).
"""
import copy
import os
import re
import shutil
from collections import Counter, defaultdict

try:
    from . import core
except ImportError:                     # plain Python / cli: this folder is on sys.path
    import core

PICK_SUFFIX = "_挑零件"
# MMD standard / semi-standard bones never go, even when only the removed parts were weighted to them (an outfit's
# sleeves may be the only user of 手捩1-3): VMD motions, PMXEditor plugins and the next outfit transfer expect them.
STANDARD_BONE = re.compile(
    r"^(全ての親|操作中心|センター|グルーブ|腰|上半身[23]?|下半身|首|頭|両目|腰キャンセル[左右]|"
    r"[左右](目|肩P?|肩C|腕|腕捩[123]?|ひじ|手捩[123]?|手首|ダミー|親指[０-２0-2]|[人中薬小]指[１-３1-3]|"
    r"足|ひざ|足首|つま先|足[ＩI][ＫK]親?|つま先[ＩI][ＫK]|足D|ひざD|足首D|足先EX))$")


def _ix(i):
    return -1 if i is None else int(i)


def _is_hide(o):
    """multiplies the diffuse alpha by 0"""
    return o.offset_type == 0 and len(o.diffuse_offset) == 4 and abs(o.diffuse_offset[3]) < 1e-6


def _is_show(o):
    """adds to the diffuse alpha"""
    return o.offset_type == 1 and len(o.diffuse_offset) == 4 and o.diffuse_offset[3] > 1e-6


def _needs(b):
    """The bones a bone cannot do without: parent, IK target and links, grant parent."""
    out = [_ix(b.parent)]
    if b.isIK:
        out.append(_ix(b.target))
        out += [_ix(link.target) for link in b.ik_links]
    if b.additionalTransform is not None and (b.hasAdditionalRotate or b.hasAdditionalLocation):
        out.append(_ix(b.additionalTransform[0]))
    return [i for i in out if i >= 0]


def _textures_of(mt):
    out = [mt.texture, mt.sphere_texture]
    if not mt.is_shared_toon_texture:
        out.append(mt.toon_texture)
    return {t for t in out if t is not None and t >= 0}


def _apply_add(mt, o):
    """Make an ADD material morph offset part of the material itself (a swap's shown body becomes the visible one)."""
    def add(base, off, n):
        base, off = list(base), list(off)
        if len(base) != n or len(off) != n:
            return base
        return [min(1.0, max(0.0, a + b)) for a, b in zip(base, off)]
    mt.diffuse = add(mt.diffuse, o.diffuse_offset, 4)
    mt.specular = add(mt.specular, o.specular_offset, 3)
    mt.ambient = add(mt.ambient, o.ambient_offset, 3)
    mt.edge_color = add(mt.edge_color, o.edge_color_offset, 4)
    mt.shininess = float(mt.shininess) + float(o.shininess_offset or 0.0)
    if isinstance(o.edge_size_offset, (int, float)):
        mt.edge_size = float(mt.edge_size) + float(o.edge_size_offset)


def plan(M, pmx, remove, bones=True):
    """What removing the materials named in `remove` takes along, without changing M.
    Returns (material indices, vertex indices, bone indices, rigid body indices) that go."""
    names = [mt.name for mt in M.materials]
    want = set(remove)
    unknown = sorted(want - set(names))
    if unknown:
        raise ValueError("模型里没有这些材质: %s" % ", ".join(unknown))
    rm_mi = {i for i, n in enumerate(names) if n in want}
    if not rm_mi:
        raise ValueError("没有要删的零件")
    if len(rm_mi) == len(names):
        raise ValueError("不能把所有材质都删掉")
    mft = core.material_faces(M)
    used = {v for mi in range(len(names)) if mi not in rm_mi for f in mft[mi] for v in M.faces[f]}
    gone_v = {v for mi in rm_mi for f in mft[mi] for v in M.faces[f]} - used

    gone_b = set()
    if bones:
        had, left = Counter(), Counter()
        for v, vert in enumerate(M.vertices):
            for b, x in core.weights_of(pmx, vert):
                had[b] += x
                if v not in gone_v:
                    left[b] += x
        children = defaultdict(list)
        for i, b in enumerate(M.bones):
            if _ix(b.parent) >= 0:
                children[_ix(b.parent)].append(i)
        gone_b = {b for b in had if had[b] > 0 and left[b] <= 0}
        stack = list(gone_b)                                   # weightless bones hanging under them: chain tips
        while stack:
            for c in children[stack.pop()]:
                if c not in gone_b and had[c] <= 0:
                    gone_b.add(c)
                    stack.append(c)
        changed = True                                         # weightless bones whose children all go: chain roots
        while changed:
            changed = False
            for i in range(len(M.bones)):
                if i not in gone_b and had[i] <= 0 and children[i] and all(c in gone_b for c in children[i]):
                    gone_b.add(i)
                    changed = True
        gone_b = {b for b in gone_b if not STANDARD_BONE.match(M.bones[b].name)}
        changed = True                                         # ... unless something kept needs them
        while changed:
            changed = False
            for i, b in enumerate(M.bones):
                if i not in gone_b:
                    for n in _needs(b):
                        if n in gone_b:
                            gone_b.discard(n)
                            changed = True
            for b in _anchors(M, gone_b):
                gone_b.discard(b)
                changed = True
    gone_r = {i for i, r in enumerate(M.rigids) if _ix(r.bone) >= 0 and _ix(r.bone) in gone_b}
    return rm_mi, gone_v, gone_b, gone_r


def _anchors(M, gone_b):
    """Bones of rigid bodies about to go that kept physics hangs from: a kept dynamic body that was joined to a
    bone-following (static) body before, and would no longer be, keeps the going bodies on its shortest way back."""
    nr = len(M.rigids)
    adj = defaultdict(set)
    for j in M.joints:
        a, c = _ix(j.src_rigid), _ix(j.dest_rigid)
        if 0 <= a < nr and 0 <= c < nr:
            adj[a].add(c)
            adj[c].add(a)
    kept = [_ix(r.bone) < 0 or _ix(r.bone) not in gone_b for r in M.rigids]

    def reach(starts, allowed):
        seen, stack = set(starts), list(starts)
        while stack:
            for c in adj[stack.pop()]:
                if c not in seen and allowed(c):
                    seen.add(c)
                    stack.append(c)
        return seen
    statics = [i for i, r in enumerate(M.rigids) if r.mode == 0]
    held_before = reach(statics, lambda c: True)
    held_after = reach([i for i in statics if kept[i]], lambda c: kept[c])
    floating = [i for i in range(nr) if kept[i] and M.rigids[i].mode != 0 and i in held_before
                and i not in held_after]
    out = set()
    for start in floating:
        prev, queue, found = {start: None}, [start], None     # shortest way to a held kept body or any static one
        while queue and found is None:
            nxt = []
            for a in queue:
                for c in adj[a]:
                    if c not in prev:
                        prev[c] = a
                        if c in held_after or M.rigids[c].mode == 0:
                            found = c
                            break
                        nxt.append(c)
                if found is not None:
                    break
            queue = nxt
        k = found
        while k is not None:
            if not kept[k]:
                out.add(_ix(M.rigids[k].bone))
            k = prev[k]
    return out


def remove_parts(M, pmx, remove, bones=True, empty_morphs=True, log=print):
    """Remove the materials named in `remove` from the loaded model M (in place) with everything that only served
    them (module docstring).  bones=False keeps every bone, rigid body and joint; empty_morphs=False keeps morphs
    that lose all their entries.  Returns a report dict."""
    rm_mi, gone_v, gone_b, gone_r = plan(M, pmx, remove, bones)
    counts0 = {"vertices": len(M.vertices), "materials": len(M.materials), "bones": len(M.bones),
               "morphs": len(M.morphs), "rigids": len(M.rigids), "joints": len(M.joints),
               "textures": len(M.textures), "frames": len(M.display)}
    report = {"removed_materials": [M.materials[i].name for i in sorted(rm_mi)], "swaps": []}
    tex_used_before = set()
    for mt in M.materials:
        tex_used_before |= _textures_of(mt)

    # -- body swaps, before anything is renumbered -------------------------------------------------------------------
    for mo in M.morphs:
        if not isinstance(mo, pmx.MaterialMorph):
            continue
        hides = [o for o in mo.offsets if o.index >= 0 and _is_hide(o)]
        shows = [o for o in mo.offsets if o.index >= 0 and _is_show(o)]
        if not hides or not shows:
            continue
        if all(o.index in rm_mi for o in hides) and any(o.index not in rm_mi for o in shows):
            shown = []
            for o in shows:
                if o.index not in rm_mi:
                    _apply_add(M.materials[o.index], o)
                    shown.append(M.materials[o.index].name)
            mo.offsets = [o for o in mo.offsets if not (o.index >= 0 and _is_show(o))]
            report["swaps"].append("「%s」藏的 %s 删了，%s 改成默认显示" % (
                mo.name, "、".join(M.materials[o.index].name for o in hides), "、".join(shown)))
        elif all(o.index in rm_mi for o in shows) and any(o.index not in rm_mi for o in hides):
            kept = [M.materials[o.index].name for o in hides if o.index not in rm_mi]
            mo.offsets = [o for o in mo.offsets if not (o.index >= 0 and _is_hide(o))]
            report["swaps"].append("「%s」换上的 %s 删了，不再藏 %s" % (
                mo.name, "、".join(M.materials[o.index].name for o in shows), "、".join(kept)))
    for line in report["swaps"]:
        log("swap: " + line)

    # -- vertices, faces, materials ----------------------------------------------------------------------------------
    mft = core.material_faces(M)
    keep_faces = [f for mi in range(len(M.materials)) if mi not in rm_mi for f in mft[mi]]
    keep_v = [v for v in range(len(M.vertices)) if v not in gone_v]
    vmap = {v: k for k, v in enumerate(keep_v)}
    keep_b = [i for i in range(len(M.bones)) if i not in gone_b]
    bmap = {b: k for k, b in enumerate(keep_b)}
    for v in keep_v:
        w = M.vertices[v].weight
        main = next((b for b in w.bones if _ix(b) >= 0 and b in bmap), keep_b[0])
        w.bones = [b if _ix(b) < 0 else bmap[b] if b in bmap else bmap[main]                # zero-weight padding
                   for b in w.bones]
    M.vertices = [M.vertices[v] for v in keep_v]
    M.faces = [tuple(vmap[v] for v in M.faces[f]) for f in keep_faces]
    mat_map = {}
    kept_mats = []
    for mi, mt in enumerate(M.materials):
        if mi not in rm_mi:
            mat_map[mi] = len(kept_mats)
            kept_mats.append(mt)
    M.materials = kept_mats

    # -- bones ---------------------------------------------------------------------------------------------------------
    report["removed_bones"] = [M.bones[i].name for i in sorted(gone_b)]
    loc = [list(b.location) for b in M.bones]
    for i in keep_b:
        b = M.bones[i]
        if _ix(b.parent) >= 0:
            b.parent = bmap[b.parent]
        if isinstance(b.displayConnection, int) and b.displayConnection >= 0:
            t = b.displayConnection
            b.displayConnection = bmap[t] if t in bmap else [loc[t][k] - loc[i][k] for k in range(3)]
        if b.isIK:
            b.target = bmap[b.target]
            for link in b.ik_links:
                link.target = bmap[link.target]
        if b.additionalTransform is not None and _ix(b.additionalTransform[0]) >= 0:
            t, ratio = b.additionalTransform
            b.additionalTransform = (bmap[t], ratio)
    M.bones = [M.bones[i] for i in keep_b]

    # -- physics -------------------------------------------------------------------------------------------------------
    keep_r = [i for i in range(len(M.rigids)) if i not in gone_r]
    rmap = {r: k for k, r in enumerate(keep_r)}
    report["removed_rigids"] = [M.rigids[i].name for i in sorted(gone_r)]
    report["removed_joints"] = [j.name for j in M.joints
                                if _ix(j.src_rigid) not in rmap or _ix(j.dest_rigid) not in rmap]
    M.joints = [j for j in M.joints if _ix(j.src_rigid) in rmap and _ix(j.dest_rigid) in rmap]
    for j in M.joints:
        j.src_rigid, j.dest_rigid = rmap[j.src_rigid], rmap[j.dest_rigid]
    M.rigids = [M.rigids[i] for i in keep_r]
    for r in M.rigids:
        if _ix(r.bone) >= 0:
            r.bone = bmap[r.bone]

    # -- morphs: entries on what went go; morphs left empty go (groups in cascade) ------------------------------------
    emptied = set()
    for i, mo in enumerate(M.morphs):
        n0 = len(mo.offsets)
        if isinstance(mo, (pmx.VertexMorph, pmx.UVMorph)):
            mo.offsets = [o for o in mo.offsets if o.index in vmap]
            for o in mo.offsets:
                o.index = vmap[o.index]
        elif isinstance(mo, pmx.MaterialMorph):
            mo.offsets = [o for o in mo.offsets if o.index < 0 or o.index in mat_map]
            for o in mo.offsets:
                if o.index >= 0:
                    o.index = mat_map[o.index]
        elif isinstance(mo, pmx.BoneMorph):
            mo.offsets = [o for o in mo.offsets if o.index in bmap]
            for o in mo.offsets:
                o.index = bmap[o.index]
        if n0 and not mo.offsets:
            emptied.add(i)
    drop_m = set()
    if empty_morphs:
        drop_m = set(emptied)
        changed = True
        while changed:
            changed = False
            for i, mo in enumerate(M.morphs):
                if isinstance(mo, pmx.GroupMorph) and i not in drop_m and mo.offsets and \
                        all(o.morph in drop_m for o in mo.offsets):
                    drop_m.add(i)
                    changed = True
    keep_m = [i for i in range(len(M.morphs)) if i not in drop_m]
    mmap = {m: k for k, m in enumerate(keep_m)}
    report["removed_morphs"] = [M.morphs[i].name for i in sorted(drop_m)]
    for i in keep_m:
        mo = M.morphs[i]
        if isinstance(mo, pmx.GroupMorph):
            mo.offsets = [o for o in mo.offsets if o.morph in mmap]
            for o in mo.offsets:
                o.morph = mmap[o.morph]
    M.morphs = [M.morphs[i] for i in keep_m]

    # -- display frames -------------------------------------------------------------------------------------------------
    frames, report["removed_frames"] = [], []
    for fr in M.display:
        n0 = len(fr.data)
        fr.data = [(k, bmap[i] if k == 0 else mmap[i]) for k, i in fr.data
                   if (k == 0 and i in bmap) or (k == 1 and i in mmap)]
        if fr.isSpecial or fr.data or not n0:
            frames.append(fr)
        else:
            report["removed_frames"].append(fr.name)
    M.display = frames

    # -- textures only the removed materials used ---------------------------------------------------------------------
    tex_used_after = set()
    for mt in M.materials:
        tex_used_after |= _textures_of(mt)
    keep_t = [t for t in range(len(M.textures)) if t in tex_used_after or t not in tex_used_before]
    tmap = {t: k for k, t in enumerate(keep_t)}
    report["removed_textures"] = [os.path.basename(M.textures[t].path) for t in range(len(M.textures))
                                  if t not in tmap]
    for mt in M.materials:
        if mt.texture is not None and mt.texture >= 0:
            mt.texture = tmap[mt.texture]
        if mt.sphere_texture is not None and mt.sphere_texture >= 0:
            mt.sphere_texture = tmap[mt.sphere_texture]
        if not mt.is_shared_toon_texture and mt.toon_texture is not None and mt.toon_texture >= 0:
            mt.toon_texture = tmap[mt.toon_texture]
    M.textures = [M.textures[t] for t in keep_t]

    counts1 = {"vertices": len(M.vertices), "materials": len(M.materials), "bones": len(M.bones),
               "morphs": len(M.morphs), "rigids": len(M.rigids), "joints": len(M.joints),
               "textures": len(M.textures), "frames": len(M.display)}
    report["before"], report["after"] = counts0, counts1
    log("removed: %s" % ", ".join("%s %d -> %d" % (k, counts0[k], counts1[k]) for k in counts0))
    for key, label in (("removed_bones", "bones"), ("removed_rigids", "rigid bodies"), ("removed_joints", "joints"),
                       ("removed_morphs", "morphs"), ("removed_frames", "display frames"),
                       ("removed_textures", "textures")):
        if report[key]:
            names = report[key]
            log("  %s: %s%s" % (label, ", ".join(names[:12]), " ... (%d)" % len(names) if len(names) > 12 else ""))
    return report


def check(M, pmx):
    """Every index in the model points at something that exists; returns the problems found."""
    nv, nb, nm, nmo, nr, nt = (len(M.vertices), len(M.bones), len(M.materials), len(M.morphs), len(M.rigids),
                               len(M.textures))
    bad = []
    if sum(mt.vertex_count for mt in M.materials) != 3 * len(M.faces):
        bad.append("material vertex counts != faces")
    if any(not (0 <= v < nv) for f in M.faces for v in f):
        bad.append("face -> vertex")
    if any(not (-1 <= _ix(b) < nb) for vert in M.vertices for b in vert.weight.bones):
        bad.append("weight -> bone")
    for i, b in enumerate(M.bones):
        refs = _needs(b)
        if isinstance(b.displayConnection, int) and b.displayConnection >= 0:
            refs.append(b.displayConnection)
        if any(r >= nb for r in refs):
            bad.append("bone %s -> bone" % b.name)
    for mt in M.materials:
        if any(t >= nt for t in _textures_of(mt)):
            bad.append("material %s -> texture" % mt.name)
    for mo in M.morphs:
        for o in mo.offsets:
            if isinstance(mo, (pmx.VertexMorph, pmx.UVMorph)) and not (0 <= o.index < nv) or \
                    isinstance(mo, pmx.MaterialMorph) and not (-1 <= o.index < nm) or \
                    isinstance(mo, pmx.BoneMorph) and not (0 <= o.index < nb) or \
                    isinstance(mo, pmx.GroupMorph) and not (0 <= o.morph < nmo):
                bad.append("morph %s -> out of range" % mo.name)
                break
    for fr in M.display:
        if any((k == 0 and not (0 <= i < nb)) or (k == 1 and not (0 <= i < nmo)) for k, i in fr.data):
            bad.append("frame %s -> out of range" % fr.name)
    if any(_ix(r.bone) >= nb for r in M.rigids):
        bad.append("rigid -> bone")
    if any(not (0 <= _ix(j.src_rigid) < nr and 0 <= _ix(j.dest_rigid) < nr) for j in M.joints):
        bad.append("joint -> rigid")
    return bad


def _label(M, pmx, faces):
    """The bone a group of faces mostly hangs on, as a short part name (chain numbers and _Dummy dropped)."""
    acc = defaultdict(float)
    for f in faces:
        for v in M.faces[f]:
            for b, w in core.weights_of(pmx, M.vertices[v]):
                acc[b] += w
    if not acc:
        return "part"
    name = M.bones[max(acc, key=acc.get)].name
    short = re.sub(r"[_\s]?\d+$", "", re.sub(r"_Dummy$", "", name))
    return short or name


def split_material(M, pmx, name, mode="bone", min_piece=100, log=print):
    """Cut one material into parts, in place: "bone" = the connected pieces grouped by the bone they mostly hang on,
    "island" = every connected piece of at least min_piece vertices on its own, the smaller ones together by bone.
    The parts are copies of the material (<name>_<bone>), its faces regrouped; vertices do not move, so vertex morphs
    stay valid; material morph entries on it are copied to every part (衣服非表示 still hides all of it).
    Returns the part names ([] when it stays in one piece)."""
    names = [mt.name for mt in M.materials]
    if name not in names:
        raise ValueError("模型里没有这个材质: %s" % name)
    mi = names.index(name)
    mft = core.material_faces(M)
    groups = core.islands(M.faces, mft[mi])
    pieces = []
    if mode == "bone":
        by = defaultdict(list)
        for g in groups:
            by[_label(M, pmx, g)].extend(g)
        pieces = [(lab, sorted(by[lab])) for lab in sorted(by, key=lambda k: -len(by[k]))]
    elif mode == "island":
        big = [g for g in groups if len({v for f in g for v in M.faces[f]}) >= min_piece]
        small = defaultdict(list)
        for g in groups:
            if len({v for f in g for v in M.faces[f]}) < min_piece:
                small[_label(M, pmx, g)].extend(g)
        seen = defaultdict(int)
        for g in sorted(big, key=lambda g: -len(g)):
            lab = _label(M, pmx, g)
            seen[lab] += 1
            pieces.append((lab if seen[lab] == 1 else "%s_%d" % (lab, seen[lab]), sorted(g)))
        pieces += [("%s_小件" % lab, sorted(small[lab])) for lab in sorted(small, key=lambda k: -len(small[k]))]
    else:
        raise ValueError("mode: bone / island")
    if len(pieces) < 2:
        log("%s: one piece, left as it is" % name)
        return []
    taken = set(names)
    new_mats, part_names = [], []
    for lab, faces in pieces:
        mt = copy.deepcopy(M.materials[mi])
        base = "%s_%s" % (name, lab)
        nm, k = base, 2
        while nm in taken:
            nm, k = "%s_%d" % (base, k), k + 1
        taken.add(nm)
        mt.name = mt.name_e = nm
        mt.vertex_count = 3 * len(faces)
        new_mats.append(mt)
        part_names.append(nm)
    order = [f for i in range(len(M.materials)) for f in (
        [f for _lab, fs in pieces for f in fs] if i == mi else mft[i])]
    M.faces = [M.faces[f] for f in order]
    M.materials = M.materials[:mi] + new_mats + M.materials[mi + 1:]
    shift = len(new_mats) - 1
    for mo in M.morphs:
        if isinstance(mo, pmx.MaterialMorph):
            offs = []
            for o in mo.offsets:
                if o.index == mi:
                    for k in range(len(new_mats)):
                        c = copy.deepcopy(o)
                        c.index = mi + k
                        offs.append(c)
                else:
                    if o.index > mi:
                        o.index += shift
                    offs.append(o)
            mo.offsets = offs
    log("%s -> %d parts: %s" % (name, len(part_names), ", ".join(
        "%s (%d faces)" % (n, len(fs)) for n, (_l, fs) in zip(part_names, pieces))))
    return part_names


def default_out(src, suffix=PICK_SUFFIX):
    """<model>_挑零件.pmx next to the model; _挑零件2, 3 ... when taken."""
    stem, folder = os.path.splitext(os.path.basename(src))[0], os.path.dirname(os.path.abspath(src))
    k = 1
    while True:
        out = os.path.join(folder, "%s%s%s.pmx" % (stem, suffix, "" if k == 1 else k))
        if not os.path.exists(out):
            return out
        k += 1


def split_parts(src, out=None, names=(), mode="bone", min_piece=100, log=print):
    """Write a copy of the PMX `src` with the materials in `names` cut into parts (split_material).
    out=None: <model>_拆开.pmx next to it.  Returns {"out", "parts": {material: [part names]}}."""
    pmx = core.pmx_module()
    M = pmx.load(src)
    source_name = M.name
    parts = {n: split_material(M, pmx, n, mode, min_piece, log) for n in names}
    if not any(parts.values()):
        raise ValueError("选的零件都是一整块，没有可拆的")
    bad = check(M, pmx)
    if bad:
        raise RuntimeError("拆完索引不对（没写文件）: %s" % "; ".join(bad[:5]))
    out = out or default_out(src, "_拆开")
    if os.path.exists(out):
        raise ValueError("输出已存在，不覆盖: %s" % out)
    if os.path.normcase(os.path.dirname(os.path.abspath(out))) != os.path.normcase(os.path.dirname(os.path.abspath(src))):
        raise ValueError("拆开的模型要和原模型放在同一个文件夹（贴图按相对路径找）")
    M.name = M.name_e = os.path.splitext(os.path.basename(out))[0]
    pmx.save(out, M, add_uv_count=M.header.additional_uvs)
    back = pmx.load(out)
    report = {"out": out, "source_name": source_name, "parts": parts, "problems": check(back, pmx)}
    log("wrote %s: %d materials" % (out, len(back.materials)))
    return report


def pick_parts(src, out=None, remove=(), keep=None, bones=True, empty_morphs=True, dry_run=False, log=print):
    """Write a copy of the PMX `src` without the materials in `remove` (or without every material not in `keep`)
    and everything that only served them.  out=None: <model>_挑零件.pmx next to it.  A folder other than the
    model's gets the textures copied into its textures\\.  dry_run: only report what would go.  Returns the report."""
    pmx = core.pmx_module()
    M = pmx.load(src)
    source_name = M.name
    names = [mt.name for mt in M.materials]
    if keep is not None:
        unknown = sorted(set(keep) - set(names))
        if unknown:
            raise ValueError("模型里没有这些材质: %s" % ", ".join(unknown))
        remove = [n for n in names if n not in set(keep)]
    if dry_run:
        rm_mi, gone_v, gone_b, gone_r = plan(M, pmx, remove, bones)
        rmap = {r for r in range(len(M.rigids)) if r not in gone_r}
        report = {"removed_materials": [names[i] for i in sorted(rm_mi)], "vertices": len(gone_v),
                  "removed_bones": [M.bones[i].name for i in sorted(gone_b)],
                  "removed_rigids": [M.rigids[i].name for i in sorted(gone_r)],
                  "removed_joints": [j.name for j in M.joints
                                     if _ix(j.src_rigid) not in rmap or _ix(j.dest_rigid) not in rmap]}
        log("would remove %d materials, %d vertices, %d bones, %d rigid bodies, %d joints" % (
            len(rm_mi), len(gone_v), len(gone_b), len(gone_r), len(report["removed_joints"])))
        return report
    out = out or default_out(src)
    if os.path.exists(out):
        raise ValueError("输出已存在，不覆盖: %s" % out)
    report = remove_parts(M, pmx, remove, bones=bones, empty_morphs=empty_morphs, log=log)
    bad = check(M, pmx)
    if bad:
        raise RuntimeError("删完索引不对（没写文件）: %s" % "; ".join(bad[:5]))
    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)
    if os.path.normcase(out_dir) != os.path.normcase(os.path.dirname(os.path.abspath(src))):
        tex_dir = os.path.join(out_dir, "textures")
        os.makedirs(tex_dir, exist_ok=True)
        for t in M.textures:
            if os.path.isfile(t.path):
                dst = os.path.join(tex_dir, os.path.basename(t.path))
                if not os.path.exists(dst):
                    shutil.copyfile(t.path, dst)
                t.path = dst
    M.name = M.name_e = os.path.splitext(os.path.basename(out))[0]
    gone = report["removed_materials"]
    M.comment = (M.comment or "").rstrip() + "\r\nparts removed by pmx_outfit_transfer: %s%s" % (
        ", ".join(gone[:20]), " ... (%d)" % len(gone) if len(gone) > 20 else "")
    pmx.save(out, M, add_uv_count=M.header.additional_uvs)
    back = pmx.load(out)
    bad = check(back, pmx)
    missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
    report.update({"out": out, "source_name": source_name, "problems": bad, "textures_missing": missing})
    log("wrote %s: %d vertices, %d materials, %d bones, %d rigids, %d joints, %d morphs%s%s" % (
        out, len(back.vertices), len(back.materials), len(back.bones), len(back.rigids), len(back.joints),
        len(back.morphs), "; problems: %s" % bad if bad else "", "; textures missing: %s" % missing if missing else ""))
    return report
