#!/usr/bin/env python3
"""DOA5LR physics data -> JSON (TMC custom params + ACSCLS cloth/hair/strings + PHYD).

What it reads (all little-endian, stdlib only):
  * TMC (model) blocks: NodeLay (names), HieLay (parent + local bind matrix),
    GlblMtx (global bind matrix), cpf/nodecp (per-node custom params, keys are
    FNV-1 32-bit hashes), ACSCLS (accessory cloth: chains, grids, hair, mixer,
    colliders).
  * PHYD ("PHYD0.8", nested "1PDS" chunks root / Cols / Phys): best effort,
    rigid-body shapes per bone (SPHE / BOX) - NOT the cloth colliders.
  * optional --exe game.exe: copies the bust preset tables that sit next to the
    OPT_Breast_* name table in .data (plain data; .text is not touched).

Usage:
  python tmc_physics.py <file|dir> [...] [-o OUTDIR] [--exe game.exe]

  Files: *.TMC and *.PHYD (extract them first with extract_lnk.py). With a
  directory every .TMC/.PHYD inside is processed. Collider references are
  resolved across all files of one run (a hair lists colliders that live in
  the costume), so pass costume + hair (+ face) together.
  Default OUTDIR: <input dir>/../physics when the input dir is called tmc_src,
  otherwise ./physics.

Every number is written raw; names ending in '?' are guesses. The meaning of
each field and how sure we are is in the "notes" of each JSON and in
docs (findings): verified / likely / guess.
"""

import argparse
import glob
import json
import math
import os
import struct
import sys

MARK = 0x01010000
FNV_PRIME = 0x01000193
FNV_BASIS = 0x811C9DC5

# Custom-parameter keys (strings found in game.exe, plus resolved variants).
KNOWN_KEYS = """
ASSIST_BONE_PERCENT ASSIST_BONE_TYPE ASSIST_BONE_BASE_NODE ASSIST_BONE_SUB_NODE
ASSIST_BONE_BASE_NODE_NAME ASSIST_BONE_SUB_NODE_NAME ASSIST_BONE_TWSIT_SCL
ASSIST_BONE_TWSIT_SCL_X ASSIST_BONE_TWSIT_SCL_Y ASSIST_BONE_TWSIT_SCL_Z
ASSIST_BONE_TRANS_USE ASSIST_BONE_TRANS_PERCENT
BUST_VIBRATION BUST_VIBRATION_ BUST_SWING_PRESET BUST_HENKEI_PRESET BUST_PRESS_ENABLE
HAT_HAIR_CHANGE REFLECT_TEX_TARGET_NODE REFLECT_POSTURE EQUIP_DISP_STATUS GLASSES_NODE
SKIRT_GRAVITY ALWAYS_HABIT UNDERWEAR_DISP_STATUS COS_BREAK_DISP_TYPE
LONGRANGE_WEAPON_TEXTURE_NODE SKIN_SWEAT WET_MATERIAL WET_CLOTH STAIN_LAYER_MATERIAL
HAIR_SHADER UNIFIED_DRAW_DISABLE BUMPWAVE_MATERIAL BUMPWAVE_HEIGHTMAP_MATERIAL
REFLECT_MATERIAL GLASS_REF_MATERIAL ALPHA_REF_DEPTH_ONLY DROP_SWEAT_SPECULAR
DROP_SWEAT_SHADOW SSAO_DISABLE COLLIDE WIND
""".split()

# ACSCLS group tags (third field of the object table), FNV-1 of these names.
KNOWN_TAGS = ["AcsCloth", "AcsString", "AcsHair", "AcsMixer", "AcsHatOnly", "AcsNoHatOnly",
              "AcsCloth1", "AcsString1"]

OBJECT_KINDS = {
    0: ("cloth_grid", "particle grid: structural + shear + bend springs, triangles; e.g. skirts"),
    1: ("string_chain", "particle chain(s) with stretch + bend springs; strings, ribbons, sashes"),
    2: ("mixer", "no simulation particles: 7 baked pose sets (rest + 6 directions) blended at runtime; e.g. bangs"),
    3: ("hair_chain", "particle chain like type 1, used for hair strands"),
    4: ("cloth_grid_variant", "same block layout as type 0; rare (limb-attached cloth: sleeves, collar, obi)"),
    5: ("string_chain_variant", "same block layout as type 1; rare (wrist/ankle cuffs, ribbons)"),
}

COLLIDER_SHAPES = {
    0: ("box?", "size = half extents (the 1 x 0.5 x 1 floor box on OPT_acs_ground has its top face at y=0)"),
    1: ("capsule?", "size = (radius, half length, radius-ish), axis = local Y"),
    2: ("ellipsoid?", "size = three semi-axes"),
}

BREAST_BONES = ["OPT_Breast_%s_%s" % (s, p) for s in ("Left", "Right") for p in ("base", "tip")] + \
               ["OPT_Breast_%s%d" % (s, i) for s in ("Left", "Right") for i in range(1, 6)]


def fnv1(s):
    h = FNV_BASIS
    for c in s:
        h = ((h * FNV_PRIME) & 0xFFFFFFFF) ^ c
    return h


KEY_BY_HASH = {fnv1(k.encode()): k for k in KNOWN_KEYS}
TAG_BY_HASH = {fnv1(k.encode()): k for k in KNOWN_TAGS}
TAG_BY_HASH[FNV_BASIS] = ""


def r6(x):
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return str(x)
        return round(x, 6)
    if isinstance(x, (list, tuple)):
        return [r6(v) for v in x]
    return x


def hx(v):
    return "0x%08X" % v


# ---------------------------------------------------------------- TMC blocks

class Tmc:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.d = f.read()
        if self.d[:3] != b"TMC":
            raise ValueError("not a TMC file: %s" % path)
        top = self.blk(0)
        self.top = [self.blk(o) if o else None for o in self.offs(top)]
        self.by_name = {b["name"]: b for b in self.top if b}

    def u32(self, p):
        return struct.unpack_from("<I", self.d, p)[0]

    def blk(self, p):
        d = self.d
        if p < 0 or p + 0x30 > len(d) or self.u32(p + 8) != MARK:
            return None
        _, hsize, size, c1, c2, c3, o1, o2, o3, _ = struct.unpack_from("<10I", d, p + 8)
        return dict(p=p, name=d[p:p + 8].split(b"\0")[0].decode("ascii", "replace"),
                    hsize=hsize, size=size, c1=c1, c2=c2, c3=c3, o1=o1, o2=o2, o3=o3)

    def offs(self, b):
        if not b or not b["c1"] or not b["o1"]:
            return []
        return list(struct.unpack_from("<%dI" % b["c1"], self.d, b["p"] + b["o1"]))

    def cstr(self, p):
        e = self.d.index(b"\0", p)
        return self.d[p:e].decode("ascii", "replace")

    # nodes -------------------------------------------------------------
    def nodes(self):
        d = self.d
        nl, hl, gm = self.by_name.get("NodeLay"), self.by_name.get("HieLay"), self.by_name.get("GlblMtx")
        names = [self.cstr(nl["p"] + o + 0x40) for o in self.offs(nl)]
        out = []
        hoffs = self.offs(hl)
        goffs = self.offs(gm) if gm else []
        for i, n in enumerate(names):
            hb = hl["p"] + hoffs[i]
            local = struct.unpack_from("<16f", d, hb)
            parent, nch, level, _ = struct.unpack_from("<i3I", d, hb + 0x40)
            glob_m = struct.unpack_from("<16f", d, gm["p"] + goffs[i]) if goffs else None
            out.append(dict(index=i, name=n, parent=parent, level=level, local=local, glob=glob_m))
        for nd in out:
            nd["parent_name"] = out[nd["parent"]]["name"] if 0 <= nd["parent"] < len(out) else None
        return out

    # custom params -----------------------------------------------------
    def customp(self, p):
        b = self.blk(p)
        res = []
        for i in range(b["c1"]):
            voff = self.u32(p + b["o1"] + 4 * i)
            khash, _kidx = struct.unpack_from("<II", self.d, p + b["o3"] + 8 * i)
            vtype = self.u32(p + voff)
            raw = self.d[p + voff + 4:p + voff + 16]
            if vtype == 0:
                val = bool(raw[0])
            elif vtype == 1:
                val = struct.unpack_from("<i", raw)[0]
            elif vtype == 2:
                val = struct.unpack_from("<f", raw)[0]
            elif vtype == 3:
                val = self.cstr(p + voff + 4)
            else:
                val = raw.hex()
            res.append(dict(key=KEY_BY_HASH.get(khash, hx(khash)), key_hash=hx(khash), type=vtype, value=r6(val)))
        return res

    def node_params(self):
        cpf = self.by_name.get("cpf")
        if not cpf:
            return {}
        so = self.offs(cpf)
        if not so or not so[0]:
            return {}
        nodecp = self.blk(cpf["p"] + so[0])
        out = {}
        for i, o in enumerate(self.offs(nodecp)):
            if o:
                out[i] = self.customp(nodecp["p"] + o)
        return out


# ---------------------------------------------------------------- ACSCLS

def u16_list(t, p):
    b = t.blk(p)
    if not b:
        return None
    return list(struct.unpack_from("<%dH" % b["c1"], t.d, p + b["o1"])) if b["c1"] else []


def list_set(t, p):
    b = t.blk(p)
    if not b:
        return None
    return [u16_list(t, p + o) if o else [] for o in t.offs(b)]


def u32_list(t, p):
    b = t.blk(p)
    return list(struct.unpack_from("<%dI" % b["c1"], t.d, p + b["o1"])) if b and b["c1"] else []


def parse_particles(t, p):
    b = t.blk(p)
    d = t.d
    recs = []
    for i in range(b["c1"]):
        r = p + b["o1"] + i * 160
        m = struct.unpack_from("<16f", d, r)
        v = [struct.unpack_from("<4f", d, r + 0x40 + 16 * k) for k in range(4)]
        e, f = struct.unpack_from("<2f", d, r + 0x80)
        node, = struct.unpack_from("<I", d, r + 0x88)
        local, parent = struct.unpack_from("<2H", d, r + 0x8C)
        slot, = struct.unpack_from("<I", d, r + 0x90)
        tail = struct.unpack_from("<3I", d, r + 0x94)
        recs.append(dict(mtx=m, v=v, e=e, f=f, node=node, local=local, parent=parent, slot=slot, tail=tail))
    lists = list_set(t, p + b["o3"]) if b["o3"] else None
    return recs, lists


def parse_springs(t, p):
    b = t.blk(p)
    d = t.d
    recs = []
    for i in range(b["c1"]):
        r = p + b["o1"] + i * 96
        v = [struct.unpack_from("<4f", d, r + 16 * k) for k in range(5)]
        pa, pb, la, lb = struct.unpack_from("<4H", d, r + 0x50)
        tail = struct.unpack_from("<2I", d, r + 0x58)
        recs.append(dict(v=v, a=pa, b=pb, la=la, lb=lb, tail=tail))
    lists = list_set(t, p + b["o3"]) if b["o3"] else None
    return recs, lists


def parse_tris(t, p):
    b = t.blk(p)
    v = struct.unpack_from("<%dH" % (3 * b["c1"]), t.d, p + b["o1"])
    return [list(v[i:i + 3]) for i in range(0, len(v), 3)]


def parse_frames(t, p):
    """Type-0 sub-block 5: one 96-byte record per particle (rest frame + 2 weights + ids)."""
    b = t.blk(p)
    d = t.d
    recs = []
    inner = t.blk(p + 0x30)
    inner_vals = list(struct.unpack_from("<12I", d, p + 0x60)) if inner else None
    for i in range(b["c1"]):
        r = p + b["o1"] + i * 96
        m = struct.unpack_from("<16f", d, r)
        w0, w1 = struct.unpack_from("<2f", d, r + 64)
        ints = struct.unpack_from("<6I", d, r + 72)
        recs.append(dict(frame=r6(list(m)), weights=r6([w0, w1]), ints=list(ints)))
    return dict(records=recs, header_ints=inner_vals)


def parse_pose_set(t, p):
    b = t.blk(p)
    d = t.d
    recs = []
    for i in range(b["c1"]):
        r = p + b["o1"] + i * 64
        rot = struct.unpack_from("<3f", d, r)
        scl = struct.unpack_from("<3f", d, r + 16)
        pos = struct.unpack_from("<3f", d, r + 32)
        i0, i1 = struct.unpack_from("<2I", d, r + 48)
        recs.append(dict(id=i0, id2=i1, rot_euler=r6(list(rot)), scale=r6(list(scl)), pos=r6(list(pos))))
    return recs


def mat_mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def spring_classes(parts, springs):
    par = [q["parent"] for q in parts]
    roots = set(i for i in range(len(parts)) if par[i] == i)
    if 0 not in roots and parts:
        roots.add(0)
    depth = []
    for i in range(len(parts)):
        j, dd, g = i, 0, 0
        while j not in roots and g < 4096:
            j = par[j]
            dd += 1
            g += 1
        depth.append(dd)

    def is_anc(a, b, n):
        j = b
        for _ in range(n):
            if j in roots:
                return False
            j = par[j]
        return j == a

    out = []
    for s in springs:
        a, b = s["a"], s["b"]
        if is_anc(a, b, 1) or is_anc(b, a, 1):
            c = "structural"          # parent - child
        elif is_anc(a, b, 2) or is_anc(b, a, 2):
            c = "bend"                # grandparent - grandchild (skip one)
        elif depth[a] == depth[b]:
            c = "horizontal"          # same row of a grid (ring links + skip-one ring links)
        elif abs(depth[a] - depth[b]) == 1:
            c = "shear"               # neighbouring rows, not parent/child
        else:
            c = "long_range"
        out.append(c)
    return out, depth, sorted(roots)


def parse_object(t, p, otype, tag_hash, table_node, nodes):
    b = t.blk(p)
    d = t.d
    hdr_end = b["o1"]
    nvec = (hdr_end - 0x30) // 16 - 1
    vecs = [list(struct.unpack_from("<4f", d, p + 0x30 + 16 * i)) for i in range(nvec)]
    tail = struct.unpack_from("<4I", d, p + hdr_end - 16)
    so = t.offs(b)
    nm = lambda i: nodes[i]["name"] if 0 <= i < len(nodes) else None
    kind, kind_note = OBJECT_KINDS.get(otype, ("unknown", ""))
    obj = dict(type=otype, kind=kind, kind_note=kind_note,
               group_tag=TAG_BY_HASH.get(tag_hash), group_tag_hash=hx(tag_hash),
               node=table_node, node_name=nm(table_node), block_offset=hx(p),
               header_raw=r6(vecs), header_tail_raw=list(tail))
    if otype == 2:
        # mixer: header = 7 single-value params (stored as splatted vec4), tail = (node, first slot, 0, 0)
        obj["params_raw"] = r6([v[0] for v in vecs])
        obj["params"] = {"m%d?" % i: r6(v[0]) for i, v in enumerate(vecs)}
        obj["first_slot"] = tail[1]
        children = [n["index"] for n in nodes if n["parent"] == table_node]
        sets = []
        for k, o in enumerate(so):
            if not o:
                sets.append(None)
                continue
            recs = parse_pose_set(t, p + o)
            for rr in recs:
                ni = children[rr["id"]] if rr["id"] < len(children) else None
                rr["node_guess"] = nm(ni) if ni is not None else None
            sets.append(recs)
        obj["pose_sets"] = sets
        obj["pose_set_labels?"] = ["rest", "+X", "-X", "+Y", "-Y", "+Z", "-Z"]
        return obj

    flags = tail[1]
    obj.update(dict(
        anchor=r6(vecs[0][:3]),
        reach=r6(vecs[1][0]),
        params_raw=dict(p2=r6(vecs[2][0]), p3=r6(vecs[3][0]), p4=r6(vecs[4][0]), p5=r6(vecs[5][0])),
        params_guess={"gravity_scale?": r6(vecs[2][0]), "unknown_p3 (1.0 typical; inertia/follow scale?)": r6(vecs[3][0]),
                      "unknown_p4 (0..1 typical; shape keeping?)": r6(vecs[4][0]),
                      "damping?": r6(vecs[5][0])},
        flags_raw=hx(flags), flag_lo=flags & 0xFFFF, columns=flags >> 16,
        first_slot=tail[2]))
    roles = {0: "particles", 1: "springs", 2: "colliders", 3: "colliders2"} if otype in (1, 3, 5) else \
            {0: "particles", 1: "springs", 2: "triangles", 3: "colliders", 4: "colliders2", 5: "frames"}
    obj["sub_blocks"] = [roles.get(i, "sub%d" % i) if o else None for i, o in enumerate(so)]
    parts = springs = None
    for i, o in enumerate(so):
        if not o:
            continue
        q = p + o
        role = roles.get(i, "sub%d" % i)
        if role == "particles":
            parts, plists = parse_particles(t, q)
            obj["particle_lists"] = plists
        elif role == "springs":
            springs, slists = parse_springs(t, q)
            obj["spring_lists"] = slists
        elif role == "triangles":
            obj["triangles"] = parse_tris(t, q)
        elif role in ("colliders", "colliders2"):
            obj[role] = [hx(h) for h in u32_list(t, q)]
        elif role == "frames":
            obj["frames"] = parse_frames(t, q)
        else:
            sb = t.blk(q)
            obj.setdefault("unknown_sub_blocks", []).append(dict(index=i, hex=d[q:q + sb["size"]].hex()))
    if parts is not None:
        classes, depth, roots = spring_classes(parts, springs or [])
        obj["root_particles"] = roots
        # bind-pose positions in the object frame by chaining the particle rest matrices
        G = [None] * len(parts)
        for i in range(len(parts)):
            stack, j, g = [], i, 0
            while G[j] is None and j not in roots and g < 4096:
                stack.append(j)
                j = parts[j]["parent"]
                g += 1
            if G[j] is None:
                G[j] = list(parts[j]["mtx"])
            for k in reversed(stack):
                G[k] = mat_mul(parts[k]["mtx"], G[parts[k]["parent"]])
        plist = []
        for i, q in enumerate(parts):
            plist.append(dict(
                index=i, node=q["node"], node_name=nm(q["node"]), parent=q["parent"], depth=depth[i],
                rest_offset=r6(list(q["mtx"][12:15])), rest_rotation_rows=r6([list(q["mtx"][0:3]), list(q["mtx"][4:7]), list(q["mtx"][8:11])]),
                chain_pos=r6(G[i][12:15]) if G[i] else None,
                a=r6(q["v"][0][0]), b=r6(q["v"][1][0]), c=r6(q["v"][2][0]), d=r6(q["v"][3][0]), e=r6(q["e"]),
                f_equals_e=abs(q["e"] - q["f"]) < 1e-7, local_node_id=q["local"], slot=q["slot"]))
        obj["particles"] = plist
        slist = []
        counts = {}
        for i, s in enumerate(springs or []):
            c = classes[i]
            counts[c] = counts.get(c, 0) + 1
            slist.append(dict(index=i, a=s["a"], b=s["b"], cls=c, rest_length=r6(s["v"][0][0]),
                              share_a=r6(s["v"][1][0]), share_b=r6(s["v"][2][0]),
                              k1=r6(s["v"][3][0]), k2=r6(s["v"][4][0])))
        obj["springs"] = slist
        obj["spring_class_counts"] = counts
        obj["counts"] = dict(particles=len(parts), springs=len(slist), triangles=len(obj.get("triangles", [])),
                             roots=len(roots))
    return obj


def parse_acscls(t, nodes):
    b = t.by_name.get("ACSCLS")
    if not b:
        return None
    d = t.d
    base = b["p"]
    so = t.offs(b)
    nm = lambda i: nodes[i]["name"] if 0 <= i < len(nodes) else None
    res = dict(block_offset=hx(base), version=t.u32(base + 0x30), objects=[], colliders=[])
    ob = t.blk(base + so[0]) if len(so) > 0 and so[0] else None
    tbl = t.blk(ob["p"] + 0x30) if ob else None
    table = [struct.unpack_from("<3I", d, tbl["p"] + tbl["o1"] + 12 * i) for i in range(tbl["c1"])] if tbl else []
    for i, o in enumerate(t.offs(ob) if ob else []):
        otype, node, tag = table[i]
        obj = parse_object(t, ob["p"] + o, otype, tag, node, nodes)
        obj["index"] = i
        res["objects"].append(obj)
    cb = t.blk(base + so[1]) if len(so) > 1 and so[1] else None
    if cb and cb["c1"]:
        ctbl = t.blk(cb["p"] + 0x30)
        entries = [struct.unpack_from("<3I", d, ctbl["p"] + ctbl["o1"] + 12 * i) for i in range(ctbl["c1"])]
        for i, o in enumerate(t.offs(cb)):
            r = cb["p"] + o
            rot = struct.unpack_from("<3f", d, r)
            size = struct.unpack_from("<3f", d, r + 16)
            ctr = struct.unpack_from("<3f", d, r + 32)
            node, h = struct.unpack_from("<2I", d, r + 48)
            ctype = entries[i][0]
            shape, note = COLLIDER_SHAPES.get(ctype, ("unknown", ""))
            res["colliders"].append(dict(index=i, name_hash=hx(h), type=ctype, shape=shape,
                                         node=node, node_name=nm(node), rotation_euler_xyz_rad=r6(list(rot)),
                                         size=r6(list(size)), center=r6(list(ctr))))
    res["slot_nodes"] = [dict(node=n, name=nm(n)) for n in (u32_list(t, base + so[2]) if len(so) > 2 and so[2] else [])]
    res["driven_nodes"] = [dict(node=n, name=nm(n)) for n in (u32_list(t, base + so[3]) if len(so) > 3 and so[3] else [])]
    return res


# ---------------------------------------------------------------- PHYD (best effort)

def parse_phyd(path):
    with open(path, "rb") as f:
        d = f.read()
    if d[:7] != b"PHYD0.8":
        raise ValueError("not a PHYD file: %s" % path)
    u = lambda p: struct.unpack_from("<I", d, p)[0]
    out = dict(format="PHYD0.8 (nested 1PDS chunks; schema-driven serialisation, partly decoded)", chunks=[])
    root_size = u(12)
    root_hdr = list(struct.unpack_from("<8I", d, 16))
    out["root_header"] = root_hdr
    # root data: a few offsets (string index, string blob, chunk offsets ...; the count varies)
    data_off = root_hdr[5]
    root_words = list(struct.unpack_from("<6I", d, data_off))
    out["root_words"] = root_words
    # bone-name strings: length-prefixed, zero-terminated, stored before the first nested chunk
    first_chunk = d.find(b"1PDS", 12)
    limit = first_chunk - 8 if first_chunk > 0 else len(d)
    names = []
    q = data_off
    while q < limit:
        n = d[q]
        if 3 <= n <= 64 and q + 2 + n <= limit and d[q + 1 + n] == 0 and \
                all(48 <= c < 123 for c in d[q + 1:q + 1 + n]):
            names.append(d[q + 1:q + 1 + n].decode("ascii"))
            q += n + 2
        else:
            q += 1
    out["names"] = names
    # nested chunks: 8-byte name + "1PDS" + size (size counted from the name)
    p = 8
    found = []
    while True:
        p = d.find(b"1PDS", p + 4)
        if p < 0:
            break
        if p - 8 < 0:
            continue
        name = d[p - 8:p].split(b"\0")[0]
        if not name or not all(32 <= c < 127 for c in name):
            continue
        found.append((name.decode(), p - 8))
    for name, cp in found:
        size = u(cp + 12)
        hdr = list(struct.unpack_from("<8I", d, cp + 16))
        ntypes, ttab, doff, pool = hdr[0], hdr[4], hdr[5], hdr[6]
        types = [list(struct.unpack_from("<4I", d, cp + ttab + 16 * i)) for i in range(ntypes)]
        end = cp + (pool if pool else size)
        words = []
        for a in range(cp + doff, min(end, cp + size), 4):
            words.append(u(a))
        ch = dict(name=name, offset=hx(cp), size=size, header=hdr, types=[[hx(x) for x in ty] for ty in types])
        if name == "Cols":
            shapes = []
            i = 0
            while i < len(words):
                tag = struct.pack("<I", words[i])[::-1].strip(b"\0")
                if tag in (b"SPHE", b"BOX", b"CAPS", b"CAPL", b"CYL"):
                    refs = []
                    j = i + 1
                    while j < len(words) and pool and pool <= words[j] < size and (words[j] - pool) % 4 == 0:
                        v = struct.unpack_from("<3f", d, cp + words[j])
                        refs.append(dict(ptr=hx(words[j]), vec3=r6(list(v))))
                        j += 1
                    pre = words[max(0, i - 4):i]
                    shapes.append(dict(tag=tag.decode(), word_index=i, refs=refs,
                                       pre_words=[r6(struct.unpack("<f", struct.pack("<I", w))[0]) if 0x30000000 < w < 0x50000000 else w for w in pre]))
                    i = j
                else:
                    i += 1
            ch["shapes"] = shapes
            if pool:
                ch["vec3_pool"] = [r6(list(struct.unpack_from("<3f", d, cp + a))) for a in range(pool, size - 11, 12)]
        elif name == "Phys":
            ch["values"] = [r6(struct.unpack("<f", struct.pack("<I", w))[0]) if w > 0xFFFF else w for w in words]
        out["chunks"].append(ch)
    out["notes"] = [
        "Root chunk lists the bone names the bodies attach to; 'Cols' holds tagged shapes (SPHE / BOX) whose fields "
        "point (offsets from the chunk start) into a vec3 pool; 'Phys' holds per-body scalars.",
        "Character PHYD: 16 MOT bones, 4 SPHE + 12 BOX, Phys = 16 x (1, 0.5, 1, 1). Per-costume PHYD (e.g. "
        "KASUMI_COS_004): one BOX on WGT_headdress, Phys = (1, 0.75, 1, 0, 1, 1.5, 1, 0.1).",
        "Likely a rigid-body description (body vs stage props; knock-off accessories). The cloth / hair colliders "
        "are in the TMC ACSCLS block, not here.",
    ]
    return out


# ---------------------------------------------------------------- game.exe bust tables

def find_bust_tables(exe_path):
    with open(exe_path, "rb") as f:
        d = f.read()
    # locate "OPT_Breast_Right_base" string, then the pointer table that references the 12 names
    ib = 0x400000
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = pe + 24
    ib = struct.unpack_from("<I", d, opt + 28)[0]
    sec_tab = opt + struct.unpack_from("<H", d, pe + 20)[0]
    secs = []
    for i in range(nsec):
        s = sec_tab + 40 * i
        name = d[s:s + 8].split(b"\0")[0].decode("ascii", "replace")
        vsize, va, rsize, raw = struct.unpack_from("<4I", d, s + 8)
        secs.append((name, va, vsize, raw, rsize))

    def off2va(o):
        for n, va, vs, raw, rs in secs:
            if raw <= o < raw + rs:
                return ib + va + (o - raw)
        return None

    s = d.find(b"OPT_Breast_Right_base\0")
    if s < 0:
        return dict(error="OPT_Breast_Right_base not found")
    va = off2va(s)
    ptab = d.find(struct.pack("<I", va))
    if ptab < 0:
        return dict(error="pointer table not found")

    def fl(o, n):
        return r6(list(struct.unpack_from("<%df" % n, d, o)))

    # layout measured on the Steam build (game.exe 17,260,664 bytes, 2024-09-01); offsets relative to the pointer table
    lay = dict(pre=(-0x8B4, 24, 1), R=(-0x854, 17, 5), T=(-0x700, 17, 5), H=(-0x5AC, 19, 4),
               P=(-0x47C, 23, 4), Q=(-0x30C, 23, 4), tail_header=(-0x1A4, 4, 1), tail=(-0x194, 5, 20))
    out = dict(exe=os.path.basename(exe_path), exe_size=len(d), pointer_table_file_offset=hx(ptab),
               pointer_table_va=hx(off2va(ptab)), tables={})
    for k, (rel, n, cnt) in lay.items():
        base = ptab + rel
        out["tables"][k] = dict(file_offset=hx(base), va=hx(off2va(base)), record_floats=n,
                                records=[fl(base + 4 * n * i, n) for i in range(cnt)])
    T = out["tables"]
    ok = (T["R"]["records"][0][0] == 2.5 and T["T"]["records"][0][0] == 12.0 and
          T["H"]["records"][3][18] == 32.0 and T["tail_header"]["records"][0] == [1.0, 1.0, 45.0, 10.0])
    out["layout_validated"] = ok
    if not ok:
        out["raw_dump_before_pointer_table"] = fl(ptab - 0x900, 0x900 // 4)
    out["notes"] = [
        "Plain .data next to the 12 OPT_Breast_* name pointers. Exact field meanings unknown (code is in the "
        "encrypted .text). Counts match the per-costume presets: R and T have 5 records = BUST_SWING_PRESET 0-4; "
        "H, P and Q have 4 records = BUST_HENKEI_PRESET 0-3, and record 3 has all offsets zero (Marie Rose, the only "
        "character with HENKEI 3).",
        "R/T record = 9 scalars + 4 + 4 values; the last 8 look like 4 (frequency?, amplitude?) pairs (R4 switches "
        "pairs 3-4 off). H record = 6 vec3 (6 bones? tip + 5 ring bones) + an angle-like value (35/32). "
        "P/Q record = 4 scalars + 17 small signed offsets + (1, 1).",
        "tail = header (1, 1, 45, 10) + 20 records (sx, sy, sz, a, b); contains a 0 record and a 1.0/1.25/1.5/1.75 "
        "ladder (a, b scale with s), a guess for the Off / Natural / DOA / OMG option scaling.",
    ]
    return out


# ---------------------------------------------------------------- per-file assembly

PARTICLE_NOTES = {
    "rest_offset": "verified: translation of the particle rest matrix (relative to its parent particle); its length equals the parent spring rest length (40,333 of 40,341 checked)",
    "chain_pos": "rest positions obtained by chaining the rest matrices from the root particle (object frame)",
    "a,b,c,d,e": "per-particle scalars (a-d stored as splatted vec4; e is stored twice, equal in all 47,919 particles). Unknown. Hair: b ramps 1,1,1,0.5,0.. and e ramps 1,0.5,0.2,0.1,0.. from the root (guess: follow-animation / pin weights)",
}
SPRING_NOTES = {
    "rest_length": "verified (see particles)",
    "share_a/share_b": "verified sum = 1 for every spring; likely the inverse-mass split of the position correction",
    "k1/k2": "likely stiffness; structural 5-20, bend 1; shear springs have k1 > k2 (5 / 3) -> stretch vs compression stiffness?",
    "cls": "computed here from the particle tree: structural (parent-child), bend (skip one), horizontal (same grid row), shear (neighbouring rows)",
}


def build_tmc_json(path):
    t = Tmc(path)
    nodes = t.nodes()
    params = t.node_params()
    acs = parse_acscls(t, nodes)

    roles = {}
    for nd in nodes:
        n = nd["name"]
        if n in BREAST_BONES:
            roles[nd["index"]] = "breast"
    if acs:
        for o in acs["objects"]:
            roles.setdefault(o["node"], "acs_object_node")
            for q in o.get("particles", []):
                roles[q["node"]] = "acs_particle"
            index_by_name = {nd["name"]: nd["index"] for nd in nodes}
            for ps in o.get("pose_sets") or []:
                for rr in ps or []:
                    if rr.get("node_guess") in index_by_name:
                        roles[index_by_name[rr["node_guess"]]] = "acs_mixer_bone"
        for dn in acs["driven_nodes"]:
            roles.setdefault(dn["node"], "acs_driven")
        for c in acs["colliders"]:
            roles.setdefault(c["node"], "collider_parent")
    for i in params:
        roles.setdefault(i, "has_custom_params")

    def node_json(nd):
        g = nd["glob"]
        return dict(index=nd["index"], name=nd["name"], parent=nd["parent"], parent_name=nd["parent_name"],
                    role=roles.get(nd["index"], "other"),
                    local_matrix=r6(list(nd["local"])), global_matrix=r6(list(g)) if g else None,
                    global_position=r6(list(g[12:15])) if g else None)

    custom = {}
    for i, plist in params.items():
        custom[nodes[i]["name"] if i < len(nodes) else str(i)] = {pp["key"]: pp["value"] for pp in plist}

    # breast summary
    chest = custom.get("MOT02_Chest", {})
    breast = None
    present = [n for n in BREAST_BONES if any(nd["name"] == n for nd in nodes)]
    if present:
        breast = dict(
            bones=present,
            swing_preset=chest.get("BUST_SWING_PRESET"), henkei_preset=chest.get("BUST_HENKEI_PRESET"),
            press_enable=chest.get("BUST_PRESS_ENABLE"),
            vibration={n: custom.get(n, {}).get("BUST_VIBRATION", custom.get(n, {}).get("BUST_VIBRATION_"))
                       for n in present if n[-1].isdigit()},
            notes=["Breasts are not in ACSCLS and not in PHYD: 14 skinned bones per model (base -> tip -> 5 ring bones "
                   "on the upper half), moved procedurally by code; the bone names are hard-coded in game.exe.",
                   "Per costume: BUST_SWING_PRESET (0-4) and BUST_HENKEI_PRESET (0-3) on MOT02_Chest, optional "
                   "BUST_PRESS_ENABLE; per ring bone: BUST_VIBRATION (0-0.8). Preset tables: run with --exe."])

    out = dict(source=os.path.basename(path), format="doa5lr-tmc-physics/1",
               counts=dict(nodes=len(nodes), custom_param_nodes=len(params)),
               breast=breast, custom_params=custom, acscls=acs,
               nodes=[node_json(nd) for nd in nodes if roles.get(nd["index"]) or nd["name"].startswith("MOT")],
               notes=dict(particles=PARTICLE_NOTES, springs=SPRING_NOTES,
                          object_header="anchor = root particle position (or centroid of the root row for grids) in the "
                                        "object node frame (94% verified); reach = largest bind-pose distance from the root "
                                        "particle (96% of single-root chains verified); p2..p5 guesses: gravity scale / ? / ? / damping",
                          flags="flag_lo is 1 or 10 for every object (solver iterations?); columns = number of root (pinned) "
                                "particles = grid columns (94% of objects match)",
                          colliders="name_hash = FNV-1 of a collider name (unresolved names; FNV-1('') = 0x811C9DC5 occurs). "
                                    "Objects list colliders by hash (sorted) and may reference colliders defined in another "
                                    "part (hair -> costume); 'colliders2' is a second list that usually holds the floor "
                                    "(0x885D4722, box on OPT_acs_ground) and head/hair shapes.",
                          lists="spring_lists[1] = parent spring of every non-root particle (84%); either particle_lists[0] "
                                "(= non-root particles) or spring_lists[0] is filled"))
    if acs:
        out["counts"].update(acs_objects=len(acs["objects"]), acs_colliders=len(acs["colliders"]),
                             particles=sum(len(o.get("particles", [])) for o in acs["objects"]),
                             springs=sum(len(o.get("springs", [])) for o in acs["objects"]))
    return out


def resolve_colliders(results):
    """Annotate collider references with the file / shape that defines them."""
    defs = {}
    for name, js in results.items():
        acs = js.get("acscls") if isinstance(js, dict) else None
        if not acs:
            continue
        for c in acs["colliders"]:
            defs.setdefault(c["name_hash"], []).append(dict(file=name, type=c["type"], shape=c["shape"],
                                                            node_name=c["node_name"], size=c["size"]))
    for name, js in results.items():
        acs = js.get("acscls") if isinstance(js, dict) else None
        if not acs:
            continue
        for o in acs["objects"]:
            for key in ("colliders", "colliders2"):
                if key in o:
                    o[key + "_resolved"] = [dict(hash=h, defined_in=defs.get(h, [])) for h in o[key]]


def summarize(name, js):
    lines = []
    if "acscls" in js:
        c = js["counts"]
        lines.append("%s: %d nodes, %d custom-param nodes, ACSCLS objects %s, colliders %s, particles %s, springs %s" % (
            name, c["nodes"], c["custom_param_nodes"], c.get("acs_objects", 0), c.get("acs_colliders", 0),
            c.get("particles", 0), c.get("springs", 0)))
        if js.get("breast"):
            b = js["breast"]
            lines.append("    bust: swing=%s henkei=%s press=%s vibration=%s" % (
                b["swing_preset"], b["henkei_preset"], b["press_enable"],
                {k.replace("OPT_Breast_", ""): v for k, v in b["vibration"].items() if v is not None}))
        if js["acscls"]:
            for o in js["acscls"]["objects"]:
                cnt = o.get("counts", {})
                lines.append("    obj %-2d %-20s %-12s tag=%-12s particles=%-4s springs=%-4s %s" % (
                    o["index"], o["node_name"], o["kind"], o["group_tag"] if o["group_tag"] is not None else o["group_tag_hash"],
                    cnt.get("particles", "-"), cnt.get("springs", "-"),
                    ("classes=%s" % o.get("spring_class_counts")) if o.get("spring_class_counts") else
                    ("pose_sets=%d" % len(o.get("pose_sets", [])) if o["type"] == 2 else "")))
            for c in js["acscls"]["colliders"]:
                lines.append("    collider %-2d %s %-10s on %-20s size=%s center=%s rot=%s" % (
                    c["index"], c["name_hash"], c["shape"], c["node_name"], c["size"], c["center"], c["rotation_euler_xyz_rad"]))
    elif "chunks" in js:
        lines.append("%s: PHYD names=%s chunks=%s" % (name, js["names"], [c["name"] for c in js["chunks"]]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help=".TMC / .PHYD files or directories")
    ap.add_argument("-o", "--out", help="output directory for the JSON files")
    ap.add_argument("--exe", help="game.exe: also write doa5lr_bust_tables.json (read only)")
    ap.add_argument("-q", "--quiet", action="store_true", help="no per-file summary")
    args = ap.parse_args()

    files = []
    for x in args.inputs:
        if os.path.isdir(x):
            files += sorted(glob.glob(os.path.join(x, "*.TMC")) + glob.glob(os.path.join(x, "*.tmc")) +
                            glob.glob(os.path.join(x, "*.PHYD")) + glob.glob(os.path.join(x, "*.phyd")))
        else:
            files.append(x)
    files = sorted(set(os.path.abspath(f) for f in files))
    if not files:
        ap.error("no .TMC / .PHYD input")
    out_dir = args.out
    if not out_dir:
        first_dir = os.path.dirname(files[0])
        if os.path.basename(first_dir).lower() == "tmc_src":
            out_dir = os.path.join(os.path.dirname(first_dir), "physics")
        else:
            out_dir = os.path.join(os.getcwd(), "physics")
    os.makedirs(out_dir, exist_ok=True)

    results = {}
    for f in files:
        name = os.path.basename(f)
        try:
            if name.upper().endswith(".PHYD"):
                results[name] = parse_phyd(f)
            else:
                results[name] = build_tmc_json(f)
        except Exception as e:  # keep going, report at the end
            results[name] = dict(error=repr(e))
            print("failed: %s: %r" % (name, e), file=sys.stderr)
    resolve_colliders(results)

    for name, js in results.items():
        stem = os.path.splitext(name)[0] + ("_phyd" if name.upper().endswith(".PHYD") else "")
        path = os.path.join(out_dir, stem + ".physics.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(js, fh, indent=1, ensure_ascii=False)
        if not args.quiet and "error" not in js:
            print(summarize(name, js))
    if args.exe:
        tab = find_bust_tables(args.exe)
        with open(os.path.join(out_dir, "doa5lr_bust_tables.json"), "w", encoding="utf-8") as fh:
            json.dump(tab, fh, indent=1)
        print("bust tables: validated=%s -> %s" % (tab.get("layout_validated"), os.path.join(out_dir, "doa5lr_bust_tables.json")))
    print("wrote %d file(s) -> %s" % (len(results), out_dir))


if __name__ == "__main__":
    main()
