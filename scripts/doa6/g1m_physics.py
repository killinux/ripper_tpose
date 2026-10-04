#!/usr/bin/env python3
"""DOA6 .g1m physics -> one JSON per model part, for a Unity re-implementation.

Reads a DOA6 model part (KAS_COS_001.g1m, KAS_HAIR_001.g1m, ...) plus its sibling files
(.oid bone-name hashes, .swg swing bones, .rigbin, .grp) and writes everything the game
uses to animate it physically:

  skeleton      G1MS bones: global id, name, parent, local TRS, model-space rest TRS
  colliders     COLL: collider groups (each cloth / chain / soft body names the groups it uses)
  cloth         NUNO1 + NUNO3 + NUNV1 (three parameter sets over the SAME control-point grid):
                grid (left/right/up/down links, rest lengths), the two skinned top rows,
                parameters, extra distance constraints, collision groups, driven meshes
  chains        NUNO4: bone chains (ponytail strands, ribbons) that drive real skeleton bones
  soft_bodies   SOFT 0x80001: lattice soft bodies (breasts, buttocks): nodes on a 3D grid,
                node skinning, closed hull triangles, parameters
  soft_attachments  SOFT 0x80002: bones that are placed by soft-body nodes (8-node trilinear)
  swing_bones   <part>.swg: per-bone swing parameters (small hair strands)
  meshes        G1MG mesh -> driver: type 1 = cloth surface rebuilt from 4x4 control points,
                type 2 = ordinary skinning on physics bones, type 4 = soft-body lattice (FFD)

Conventions (verified on Kasumi's files; parameter names marked guess/likely are hypotheses, raw values are kept):
  units cm; G1M model space: +Y up, character faces +Z, +X = character's left (right-handed);
  quaternions (x, y, z, w); bone transforms are parent * local; "model" = rest pose;
  bone ids are GLOBAL ids (what .g1a/.g2a clips and .oid use); "local" joint indices are
  per-file G1MS order and are only given for reference.

Usage:
  python g1m_physics.py <part.g1m> [<part2.g1m> ...] [-o OUTDIR] [--no-vertices] [--oid-table Oid.h]
"""

import argparse
import json
import math
import os
import re
import struct
import sys
from collections import Counter

FORMAT_VERSION = 1

# --------------------------------------------------------------------------------------------
# bone names: .oid files hold a hash per global id; hash(s) = sum(c_k * 31^(k+1)) mod 2^32
# --------------------------------------------------------------------------------------------
# Standard DOA6 bone names (body, fingers, twist/helper bones). Hash -> name is computed at run
# time. Names marked "cracked" were recovered here by matching hashes of consistent L/R families.
STANDARD_BONE_NAMES = """
root SK_Skeleton SK_Hips SK_Spine01 SK_Spine02 SK_Neck SK_Head
SK_L_UpLeg SK_R_UpLeg SK_L_Leg SK_R_Leg SK_L_Foot SK_R_Foot SK_L_Toes SK_R_Toes
SK_L_Shoulder SK_R_Shoulder SK_L_Arm SK_R_Arm SK_L_ForeArm SK_R_ForeArm SK_L_Hand SK_R_Hand
SK_L_Weapon SK_R_Weapon SK_L_PinkySide SK_R_PinkySide
SK_L_Thumb01 SK_L_Thumb02 SK_L_Thumb03 SK_R_Thumb01 SK_R_Thumb02 SK_R_Thumb03
SK_L_Index01 SK_L_Index02 SK_L_Index03 SK_R_Index01 SK_R_Index02 SK_R_Index03
SK_L_Middle01 SK_L_Middle02 SK_L_Middle03 SK_R_Middle01 SK_R_Middle02 SK_R_Middle03
SK_L_Ring01 SK_L_Ring02 SK_L_Ring03 SK_R_Ring01 SK_R_Ring02 SK_R_Ring03
SK_L_Pinky01 SK_L_Pinky02 SK_L_Pinky03 SK_R_Pinky01 SK_R_Pinky02 SK_R_Pinky03
RF_L_Arm_00 RF_R_Arm_00 RF_L_Arm_01 RF_R_Arm_01 RF_L_Arm_02 RF_R_Arm_02
RF_L_Elbow_00 RF_R_Elbow_00 RF_L_ForeArm_00 RF_R_ForeArm_00 RF_L_ForeArm_01 RF_R_ForeArm_01
RF_L_UpLeg_00 RF_R_UpLeg_00 RF_L_UpLeg_01 RF_R_UpLeg_01 RF_L_UpLeg_02 RF_R_UpLeg_02
RF_L_Knee_00 RF_R_Knee_00 RF_L_Leg_00 RF_R_Leg_00
RF_L_HipBack RF_R_HipBack RF_L_HipOutSide RF_R_HipOutSide RF_L_HipInSide RF_R_HipInSide
RF_L_HipsBack RF_R_HipsBack RF_L_HipsOutSide RF_R_HipsOutSide RF_L_HipsFront RF_R_HipsFront
RF_L_ForeArmNoTwist RF_R_ForeArmNoTwist RF_L_HandNoTwist RF_R_HandNoTwist
RF_L_ElbowNoTwist RF_R_ElbowNoTwist RF_L_LegNoTwist RF_R_LegNoTwist RF_L_KneeNoTwist RF_R_KneeNoTwist
RF_L_ArmNoTwist RF_R_ArmNoTwist RF_L_UpLegNoTwist RF_R_UpLegNoTwist
SK_INI_L_FootAdjust SK_INI_R_FootAdjust SK_INI_L_ToesAdjust SK_INI_R_ToesAdjust
RF_L_FootAdjust RF_R_FootAdjust RF_L_ToesAdjust RF_R_ToesAdjust
SK_INI_L_ShoulderArmor SK_INI_R_ShoulderArmor RF_L_ShoulderArmor RF_R_ShoulderArmor
RF_B_Collar RF_L_Collar RF_R_Collar SK_INI_B_Collar SK_INI_L_Collar SK_INI_R_Collar
SK_L_Sleeve SK_R_Sleeve RF_L_ShoulderBlade RF_R_ShoulderBlade RF_L_SideChest RF_R_SideChest
INI_L_ChestAssist INI_R_ChestAssist RF_L_ChestAssist RF_R_ChestAssist
F_Face F_Head_UP F_Head_Down F_Head_Back F_Assist F_Chin
""".split()

OID_H_DEFAULT = r"E:\tools\doa6\project_g1m\Project-G1M-main\Source\Public\Oid.h"


def name_hash(s):
    h, p = 0, 31
    for c in s.encode("latin1"):
        h = (h + c * p) & 0xFFFFFFFF
        p = (p * 31) & 0xFFFFFFFF
    return h


def load_name_table(oid_h_path):
    table = {name_hash(n): n for n in STANDARD_BONE_NAMES}
    if oid_h_path and os.path.isfile(oid_h_path):
        src = open(oid_h_path, encoding="utf-8", errors="replace").read()
        for hx, n in re.findall(r'\{\s*0x([0-9A-Fa-f]+)\s*,\s*"([^"]+)"\s*\}', src):
            if int(hx, 16) == name_hash(n):          # keep only entries that match the DOA6 hash
                table.setdefault(int(hx, 16), n)
    return table


def read_oid(path):
    """DOA6 .oid (type 2 'hashed'): u32 max_id, then (u32 global_id, u32 name_hash, u32 0) ..."""
    if not os.path.isfile(path):
        return {}
    b = open(path, "rb").read()
    if len(b) < 16 or struct.unpack_from("<I", b, 12)[0] != 0:
        return {}
    last = struct.unpack_from("<I", b, 0)[0]
    out, o = {}, 4
    while o + 12 <= len(b):
        gid, h, _z = struct.unpack_from("<3I", b, o)
        out[gid] = h
        o += 12
        if gid == last:
            break
    return out


# --------------------------------------------------------------------------------------------
# small math helpers (quaternions are (x, y, z, w))
# --------------------------------------------------------------------------------------------
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def to_model(bone, p):
    q, t = bone
    return vadd(t, qrot(q, p))


def to_local(bone, p):
    q, t = bone
    return qrot(qconj(q), vsub(p, t))


def mat_rows_to_quat(r0, r1, r2):
    """Quaternion of the rotation whose matrix COLUMNS are r0, r1, r2 (i.e. local axes given as rows)."""
    m00, m10, m20 = r0
    m01, m11, m21 = r1
    m02, m12, m22 = r2
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        w, x, y, z = (m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        w, x, y, z = (m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        w, x, y, z = (m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    return (x / n, y / n, z / n, w / n)


def r(v, nd=4):
    """round a number or a sequence for compact JSON"""
    if isinstance(v, (list, tuple)):
        return [r(x, nd) for x in v]
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
        x = round(v, nd)
        return 0.0 if x == 0 else x
    return v


def f32(u):
    return struct.unpack("<f", struct.pack("<I", u))[0]


def raw_value(u):
    """a 32-bit parameter word as the most plausible value: small ints / flag bytes stay ints."""
    if u == 0:
        return 0
    if u < 0x00800000:                           # tiny -> it is an integer, not a denormal float
        return {"int": u}
    e = (u >> 23) & 0xFF
    if e < 0x60 or e > 0xA0:                     # implausible float magnitude -> packed bytes
        return {"bytes": list(struct.pack("<I", u))}
    return round(f32(u), 6)


# --------------------------------------------------------------------------------------------
# G1M container + chunks
# --------------------------------------------------------------------------------------------
CHUNK_NAMES = {b"FM1G": "G1MF", b"SM1G": "G1MS", b"MM1G": "G1MM", b"GM1G": "G1MG", b"LLOC": "COLL",
               b"RIAH": "HAIR", b"ONUN": "NUNO", b"VNUN": "NUNV", b"SNUN": "NUNS", b"TFOS": "SOFT",
               b"RTXE": "EXTR"}


def ver_str(v):
    return struct.pack("<I", v)[::-1].decode("latin1")


def g1m_chunks(buf):
    if buf[:4] != b"_M1G":
        raise ValueError("not a G1M file")
    first, _res, count = struct.unpack_from("<III", buf, 12)
    off, out = first, {}
    for _ in range(count):
        magic, ver, size = struct.unpack_from("<4sII", buf, off)
        out.setdefault(CHUNK_NAMES.get(magic, magic.decode("latin1")), (off, size, ver))
        off += size
    return out


def u32s(buf, off, n):
    return list(struct.unpack_from("<%dI" % n, buf, off)) if n else []


def parse_g1ms(buf, off):
    joff, unk1, jcount, jicount, layer, _pad = struct.unpack_from("<IIHHHH", buf, off + 12)
    gl = struct.unpack_from("<%dH" % jicount, buf, off + 28)
    l2g = {loc: g for g, loc in enumerate(gl) if loc != 0xFFFF}
    joints = []
    for i in range(jcount):
        sx, sy, sz, parent, qx, qy, qz, qw, px, py, pz, w = struct.unpack_from("<3fI4f3ff", buf, off + joff + 48 * i)
        joints.append(dict(local=i, id=l2g.get(i, -1), parent_raw=parent, scale=(sx, sy, sz), rot=(qx, qy, qz, qw), pos=(px, py, pz)))
    model = [None] * jcount

    def get(i, depth=0):
        if model[i] is None:
            j = joints[i]
            par = j["parent_raw"]
            if par == 0xFFFFFFFF or depth > jcount:
                model[i] = (j["rot"], j["pos"])
            else:
                pq, pp = get(par & 0x7FFFFFFF, depth + 1)
                model[i] = (qmul(pq, j["rot"]), vadd(pp, qrot(pq, j["pos"])))
        return model[i]

    for i in range(jcount):
        get(i)
    return dict(layer=layer, unk1=unk1, joints=joints, l2g=l2g, g2l={g: l for l, g in l2g.items()}, model=model)


# ---- G1MG ----------------------------------------------------------------------------------
DT_FMT = {0: "<f", 1: "<2f", 2: "<3f", 3: "<4f", 5: "<4B", 7: "<4H", 9: "<4I", 0xA: "<2e", 0xB: "<4e", 0xD: "<4B"}
SEM_POSITION, SEM_WEIGHT, SEM_INDEX, SEM_NORMAL, SEM_PSIZE, SEM_UV, SEM_TANGENT, SEM_BINORMAL = 0, 1, 2, 3, 4, 5, 6, 7
SEM_COLOR, SEM_FOG, SEM_SAMPLE = 10, 11, 13


def parse_g1mg(buf, off, ver):
    o = off + 12
    nsec = struct.unpack_from("<I", buf, o + 32)[0]
    o += 36
    G = dict(vbufs=[], layouts=[], palettes=[], ibufs=[], submeshes=[], groups=[])
    for _ in range(nsec):
        magic, ssize, cnt = struct.unpack_from("<3I", buf, o)
        p = o + 12
        if magic == 0x10004:
            for _ in range(cnt):
                _u1, stride, count = struct.unpack_from("<3I", buf, p)
                data = p + 12 + (4 if ver > 0x30303430 else 0)
                G["vbufs"].append(dict(stride=stride, count=count, off=data))
                p = data + stride * count
        elif magic == 0x10005:
            for _ in range(cnt):
                n = struct.unpack_from("<I", buf, p)[0]
                refs = u32s(buf, p + 4, n)
                p += 4 + 4 * n
                na = struct.unpack_from("<I", buf, p)[0]
                p += 4
                attrs = []
                for _ in range(na):
                    bid, aoff, dt, _x, sem, layer = struct.unpack_from("<HHBBBB", buf, p)
                    p += 8
                    attrs.append(dict(buf=refs[bid], off=aoff, dt=dt, sem=sem, layer=layer))
                G["layouts"].append(attrs)
        elif magic == 0x10006:
            for _ in range(cnt):
                n = struct.unpack_from("<I", buf, p)[0]
                G["palettes"].append([struct.unpack_from("<3I", buf, p + 4 + 12 * k) for k in range(n)])
                p += 4 + 12 * n
        elif magic == 0x10007:
            for _ in range(cnt):
                count, dtype = struct.unpack_from("<2I", buf, p)
                p += 12 if ver > 0x30303430 else 8
                w = {8: 1, 0x10: 2, 0x20: 4}[dtype]
                G["ibufs"].append(dict(count=count, w=w, off=p))
                p = (p + count * w + 3) & ~3
        elif magic == 0x10008:
            for i in range(cnt):
                v = struct.unpack_from("<14I", buf, p + 56 * i)
                G["submeshes"].append(dict(vb=v[1], palette=v[2], material=v[6], ib=v[7], prim=v[9],
                                           vb_off=v[10], vcount=v[11], ib_off=v[12], icount=v[13]))
        elif magic == 0x10009:
            for _ in range(cnt):
                if ver > 0x30303330:
                    lod, grp, gidx, c1, c2 = struct.unpack_from("<5I", buf, p)
                    p += 36 if ver > 0x30303430 else 20
                else:
                    lod, c1, c2 = struct.unpack_from("<3I", buf, p)
                    grp = gidx = 0
                    p += 12
                meshes = []
                for _ in range(c1 + c2):
                    name = buf[p:p + 16].split(b"\x00")[0].decode("latin1")
                    mtype, _mpad, ext, nidx = struct.unpack_from("<HHII", buf, p + 16)
                    p += 28
                    idx = u32s(buf, p, nidx)
                    p += 4 * nidx if nidx else 4
                    meshes.append(dict(name=name, type=mtype, external=ext, submeshes=idx))
                G["groups"].append(dict(lod=lod, group=grp, gidx=gidx, meshes=meshes))
        o += ssize
    return G


def read_attr(buf, G, sm, sem, layer=None, int_only=False):
    for a in G["layouts"][sm["vb"]]:
        if a["sem"] != sem or (layer is not None and a["layer"] != layer):
            continue
        if int_only and a["dt"] not in (5, 7, 9):
            continue
        fmt = DT_FMT.get(a["dt"])
        if fmt is None:
            return None
        vb = G["vbufs"][a["buf"]]
        base = vb["off"] + a["off"] + vb["stride"] * sm["vb_off"]
        return [struct.unpack_from(fmt, buf, base + vb["stride"] * i) for i in range(sm["vcount"])]
    return None


def read_triangles(buf, G, sm):
    ib = G["ibufs"][sm["ib"]]
    fmt = {1: "B", 2: "H", 4: "I"}[ib["w"]]
    idx = struct.unpack_from("<%d%s" % (sm["icount"], fmt), buf, ib["off"] + ib["w"] * sm["ib_off"])
    idx = [i - sm["vb_off"] for i in idx]
    if sm["prim"] == 4:                          # strip -> list
        tris = []
        for k in range(len(idx) - 2):
            a, b, c = idx[k], idx[k + 1], idx[k + 2]
            if a == b or b == c or a == c:
                continue
            tris += [a, b, c] if k % 2 == 0 else [b, a, c]
        return tris
    return list(idx)


# ---- NUNO / NUNV (cloth grids and bone chains) ----------------------------------------------
def parse_nuno(buf, off, ver):
    o = off + 12
    nsec = struct.unpack_from("<I", buf, o)[0]
    o += 4
    out = {"NUNO1": [], "NUNO3": [], "NUNO4": [], "skipped": []}
    for _ in range(nsec):
        magic, ssize, cnt = struct.unpack_from("<3I", buf, o)
        end = o + ssize
        p = o + 12
        if magic == 0x30001:
            for _ in range(cnt):
                parent, n, n_skin, s1, s2, s3 = struct.unpack_from("<6I", buf, p)
                p += 24
                plen = 0x3C + (0x10 if ver > 0x30303233 else 0) + (0x10 if ver >= 0x30303235 else 0)
                prm = u32s(buf, p, plen // 4)
                p += plen
                cps = [struct.unpack_from("<4f", buf, p + 16 * k) for k in range(n)]
                p += 16 * n
                links = [struct.unpack_from("<4i2f", buf, p + 24 * k) for k in range(n)]
                p += 24 * n
                skin = [struct.unpack_from("<8fI4B2I", buf, p + 48 * k) for k in range(n_skin)]
                p += 48 * n_skin
                fixed = u32s(buf, p, s1)
                p += 4 * s1
                rows = u32s(buf, p, s2)
                p += 4 * s2
                cg = u32s(buf, p, s3)
                p += 4 * s3
                out["NUNO1"].append(dict(parent=parent, params=prm, cps=cps, links=links, skin=skin, fixed=fixed, row_starts=rows, coll_groups=cg))
        elif magic == 0x30003:
            for _ in range(cnt):
                parent, n, n_skin, s1, pal_id, s2, s3, s4 = struct.unpack_from("<8I", buf, p)
                p += 32
                if ver < 0x30303330:
                    plen = 0xA8 + (0x10 if ver >= 0x30303235 else 0)
                    prm = u32s(buf, p, plen // 4)
                    p += plen
                else:
                    t = struct.unpack_from("<I", buf, p + 8)[0]
                    prm = u32s(buf, p + 8, t // 4)
                    p += 8 + t
                cps = [struct.unpack_from("<4f", buf, p + 16 * k) for k in range(n)]
                p += 16 * n
                links = [struct.unpack_from("<4i2f", buf, p + 24 * k) for k in range(n)]
                p += 24 * n
                skin = [struct.unpack_from("<8fI4B2I", buf, p + 48 * k) for k in range(n_skin)]
                p += 48 * n_skin
                cg = u32s(buf, p, s1)
                p += 4 * s1
                ranges = [struct.unpack_from("<2I", buf, p + 8 * k) for k in range(s2)]
                p += 8 * s2
                extra = [struct.unpack_from("<2If", buf, p + 12 * k) for k in range(s3)]
                p += 12 * s3
                extra4 = [struct.unpack_from("<2I", buf, p + 8 * k) for k in range(s4)]
                p += 8 * s4
                out["NUNO3"].append(dict(parent=parent, palette=pal_id, params=prm, cps=cps, links=links, skin=skin, coll_groups=cg,
                                         sim_ranges=ranges, extra_constraints=extra, extra4=extra4))
        elif magic == 0x30004:
            for _ in range(cnt):
                parent, nb, nrot, s1, nmap = struct.unpack_from("<5I", buf, p)
                p += 20
                prm = u32s(buf, p, 17)
                p += 68
                rots = [struct.unpack_from("<9f", buf, p + 36 * k) for k in range(nrot)]
                p += 36 * nrot
                recs = [struct.unpack_from("<4fIff", buf, p + 28 * k) for k in range(nb)]
                p += 28 * nb
                cg = u32s(buf, p, s1)
                p += 4 * s1
                maps = [struct.unpack_from("<2I", buf, p + 8 * k) for k in range(nmap)]
                p += 8 * nmap
                out["NUNO4"].append(dict(parent=parent, params=prm, rots=rots, recs=recs, coll_groups=cg, maps=maps))
        else:
            out["skipped"].append(dict(magic="0x%08x" % magic, count=cnt, size=ssize))
            p = end
        if p != end:
            raise ValueError("NUNO section 0x%x parsed to %d, expected %d" % (magic, p, end))
        o = end
    return out


def parse_nunv(buf, off, ver):
    o = off + 12
    nsec = struct.unpack_from("<I", buf, o)[0]
    o += 4
    out, skipped = [], []
    for _ in range(nsec):
        magic, ssize, cnt = struct.unpack_from("<3I", buf, o)
        end = o + ssize
        p = o + 12
        if magic == 0x50001:
            for _ in range(cnt):
                parent, n, n_skin, s1 = struct.unpack_from("<4I", buf, p)
                p += 16
                plen = 0x54 + (0x10 if ver >= 0x30303131 else 0)
                prm = u32s(buf, p, plen // 4)
                p += plen
                cps = [struct.unpack_from("<4f", buf, p + 16 * k) for k in range(n)]
                p += 16 * n
                links = [struct.unpack_from("<4i2f", buf, p + 24 * k) for k in range(n)]
                p += 24 * n
                skin = [struct.unpack_from("<8fI4B2I", buf, p + 48 * k) for k in range(n_skin)]
                p += 48 * n_skin
                cg = u32s(buf, p, s1)
                p += 4 * s1
                out.append(dict(parent=parent, params=prm, cps=cps, links=links, skin=skin, coll_groups=cg))
            if p != end:
                raise ValueError("NUNV section parsed to %d, expected %d" % (p, end))
        else:
            skipped.append(dict(magic="0x%08x" % magic, count=cnt, size=ssize))
        o = end
    return out, skipped


# ---- SOFT (lattice soft bodies) ---------------------------------------------------------------
def parse_soft(buf, off, ver):
    o = off + 12
    nsec = struct.unpack_from("<I", buf, o)[0]
    o += 4
    bodies, attach, skipped = [], [], []
    for _ in range(nsec):
        magic, size = struct.unpack_from("<2I", buf, o)
        end = o + size
        if magic == 0x80001:
            cnt = struct.unpack_from("<I", buf, o + 8)[0]
            p = o + 12
            for _ in range(cnt):
                h = u32s(buf, p, 13)
                p += 52
                hf = u32s(buf, p, 24)
                p += 96
                n, nbones, ntri, ncg = h[1], h[4], h[6], h[8]
                nodes = []
                for _ in range(n):
                    nid = struct.unpack_from("<I", buf, p)[0]
                    pos = struct.unpack_from("<3f", buf, p + 4)
                    nrm = struct.unpack_from("<3f", buf, p + 16)
                    flags, cell, ninf = struct.unpack_from("<3I", buf, p + 28)
                    p += 40
                    pairs = [struct.unpack_from("<If", buf, p + 8 * i) for i in range(ninf + 1)]
                    p += 8 * (ninf + 1)
                    extra = struct.unpack_from("<3f3I", buf, p)
                    p += 24
                    nodes.append(dict(id=nid, pos=pos, nrm=nrm, flags=flags, cell=cell, pairs=pairs, extra=extra))
                bones = u32s(buf, p, nbones)
                p += 4 * nbones
                order = u32s(buf, p, n)
                p += 4 * n
                cg = u32s(buf, p, ncg)
                p += 4 * ncg
                tris = [struct.unpack_from("<3I", buf, p + 12 * i) for i in range(ntri)]
                p += 12 * ntri
                pver, tail_bytes = struct.unpack_from("<2I", buf, p)
                tail = u32s(buf, p + 8, (tail_bytes - 8) // 4)
                p += tail_bytes
                bodies.append(dict(h=h, hf=hf, nodes=nodes, bones=bones, order=order, coll_groups=cg, tris=tris, param_version=pver, tail=tail))
            if p != end:
                raise ValueError("SOFT 0x80001 parsed to %d, expected %d" % (p, end))
        elif magic == 0x80002:
            p = o + 8
            cnt = struct.unpack_from("<I", buf, p)[0]
            p += 4
            for _ in range(cnt):
                bone = struct.unpack_from("<I", buf, p)[0]
                vec = struct.unpack_from("<3f", buf, p + 4)
                nb = struct.unpack_from("<I", buf, p + 16)[0]
                p += 20
                refs = []
                for _ in range(nb):
                    body, w = struct.unpack_from("<If", buf, p)
                    refs.append(dict(body=body, weight=w, nodes=struct.unpack_from("<8I", buf, p + 8), weights=struct.unpack_from("<8f", buf, p + 40)))
                    p += 72
                attach.append(dict(bone=bone, vec=vec, refs=refs))
            if p != end:
                raise ValueError("SOFT 0x80002 parsed to %d, expected %d" % (p, end))
        else:
            skipped.append(dict(magic="0x%08x" % magic, size=size))
        o = end
    return bodies, attach, skipped


# ---- COLL (colliders) ---------------------------------------------------------------------------
def parse_coll(buf, off, ver):
    o = off + 12
    nsec = struct.unpack_from("<I", buf, o)[0]
    o += 4
    groups = []
    for _ in range(nsec):
        magic, ssize, ngroups = struct.unpack_from("<3I", buf, o)
        end = o + ssize
        p = o + 12
        if magic == 0x20001:
            for _ in range(ngroups):
                flag, cnt = struct.unpack_from("<2I", buf, p)
                p += 8
                cols = []
                for _ in range(cnt):
                    typ, bone, bone2, z = struct.unpack_from("<4I", buf, p)
                    cols.append(dict(type=typ, bone=bone, bone2=bone2, z=z, size=struct.unpack_from("<4f", buf, p + 16),
                                     m=struct.unpack_from("<16f", buf, p + 32), tail=buf[p + 96:p + 112]))
                    p += 112
                groups.append(dict(flag=flag, cols=cols))
            if p != end:
                raise ValueError("COLL parsed to %d, expected %d" % (p, end))
        o = end
    return groups


# ---- sibling files -------------------------------------------------------------------------------
def parse_swg(path):
    b = open(path, "rb").read()
    magic, hsize, n = struct.unpack_from("<4sII", b, 0)
    if magic != b"SWGQ":
        raise ValueError("not a SWGQ file")
    preset = b[12:20].split(b"\0")[0].decode("latin1") if hsize >= 20 else ""
    hdr_tail = u32s(b, 20, (hsize - 20) // 4) if hsize > 20 else []
    entries = []
    for i in range(n):
        o = hsize + 72 * i
        if o + 72 > len(b):
            break
        group, bone = struct.unpack_from("<HH", b, o)
        vals = u32s(b, o + 4, 15)
        entries.append(dict(group=group, bone=bone, vals=vals, tail=list(b[o + 64:o + 72])))
    return dict(header_size=hsize, preset=preset, header_words=hdr_tail, entries=entries, size_ok=(len(b) == hsize + 72 * n))


def parse_rigbin(path):
    b = open(path, "rb").read()
    magic, ver, size, h = struct.unpack_from("<4sIII", b, 0)
    return dict(magic=magic[::-1].decode("latin1"), version=ver, size=size, hash="0x%08x" % h,
                values=[raw_value(v) for v in u32s(b, 16, (len(b) - 16) // 4)])


def parse_grp(path):
    b = open(path, "rb").read()
    return dict(words=["0x%08x" % v if v > 0xFFFF else v for v in u32s(b, 0, len(b) // 4)])


# --------------------------------------------------------------------------------------------
# parameter name guesses (confidence: verified / likely / guess). Raw values are always kept.
# --------------------------------------------------------------------------------------------
NUNO1_NAMES = {0: ("mean_rest_len_horizontal", "verified"), 1: ("mean_rest_len_vertical", "verified"),
               2: ("joint_palette_index", "verified"), 11: ("sim_rate_hz", "likely"), 14: ("time_step_s", "likely")}
NUNV1_NAMES = {0: ("joint_palette_index", "verified"), 15: ("sim_rate_hz", "likely"), 17: ("time_step_s", "likely")}
NUNO3_NAMES = {4: ("gravity_scale_or_mass", "guess"), 5: ("air_drag", "guess"),
               6: ("stiffness_a (0.05..1)", "guess"), 7: ("stiffness_b (0.05..1)", "guess"),
               8: ("stiffness_c (0.05..1)", "guess"), 9: ("stiffness_d (0.05..1)", "guess"),
               12: ("friction", "guess"), 13: ("flags", "guess"), 14: ("flag_bytes", "guess"),
               15: ("spring_k_1", "guess"), 16: ("spring_damping_1 (=k/5)", "guess"),
               18: ("spring_k_2", "guess"), 19: ("spring_damping_2 (=k/5)", "guess"),
               20: ("spring_k_3", "guess"), 21: ("spring_damping_3 (=k/5)", "guess"),
               22: ("velocity_keep_a", "guess"), 23: ("velocity_keep_b", "guess"),
               31: ("collision_penalty_k", "guess"), 32: ("collision_penalty_damping (=k/5)", "guess"),
               36: ("particle_collision_radius_cm", "guess"), 37: ("iteration_counts (bytes)", "guess")}
NUNO4_NAMES = {0: ("gravity_scale_or_mass", "guess"), 1: ("flag_bytes", "guess"), 2: ("damping_a", "guess"),
               3: ("damping_b_or_shape_keep", "guess"), 4: ("stiffness_a", "guess"), 5: ("stiffness_b", "guess"),
               6: ("stiffness_c", "guess"), 7: ("iterations", "guess"), 8: ("restore_to_rest", "guess"),
               9: ("friction", "guess")}
SOFT_HEADER_NAMES = {0: ("pairA_scale", "guess"), 1: ("pairA_coef", "guess"), 2: ("pairB_scale", "guess"),
                     3: ("pairB_coef", "guess"), 4: ("pairC_scale", "guess"), 5: ("pairC_coef", "guess"),
                     6: ("pairD_scale", "guess"), 7: ("pairD_coef", "guess"),
                     8: ("per_axis_x", "guess"), 9: ("per_axis_y", "guess"), 10: ("per_axis_z", "guess"),
                     11: ("damping", "guess"), 12: ("stiffness", "guess"), 13: ("scale", "guess"), 14: ("flag", "guess"),
                     19: ("axis_x (unit vector)", "verified unit vector, meaning guess"), 20: ("axis_y", "guess"),
                     21: ("axis_z", "guess"), 22: ("gravity (default -9.8)", "likely"), 23: ("const 0.3", "guess")}
SWG_NAMES = {0: ("limit_deg_a (+X?)", "likely"), 1: ("limit_deg_b (-X?)", "likely"), 2: ("limit_deg_c (+Z?)", "likely"),
             3: ("limit_deg_d (-Z?)", "likely"), 10: ("phase_or_order (small int)", "guess"),
             13: ("damping (0.8 typical)", "guess"), 14: ("stiffness_or_speed (10 typical)", "guess")}
COLLIDER_TYPES = {0: "ellipsoid_or_box? (3 sizes)", 2: "box_or_ellipsoid? (3 sizes)",
                  5: "capsule along local Y (a=radius, b=half-length, c=see notes)", 6: "ellipsoid / sphere (radii a,b,c)"}


def named_params(words, names):
    out = []
    for i, w in enumerate(words):
        d = dict(i=i, value=raw_value(w))
        if i in names:
            d["name"], d["confidence"] = names[i]
        out.append(d)
    return out


# --------------------------------------------------------------------------------------------
# build the JSON
# --------------------------------------------------------------------------------------------
def grid_shape(links):
    n = len(links)
    row = [0] * n
    for i in range(n):
        j, k = i, 0
        while links[j][2] >= 0 and k <= n:
            j = links[j][2]
            k += 1
        row[i] = k
    nrows = max(row) + 1 if n else 0
    cols = sum(1 for x in row if x == 0)
    ring = bool(n) and all(links[i][0] >= 0 for i in range(n) if row[i] == 0)
    return cols, nrows, row, ring


class Part:
    def __init__(self, g1m_path, names_table, keep_vertices=True):
        self.path = g1m_path
        self.base = os.path.splitext(g1m_path)[0]
        self.buf = open(g1m_path, "rb").read()
        self.ch = g1m_chunks(self.buf)
        self.names_table = names_table
        self.keep_vertices = keep_vertices
        self.oid = read_oid(self.base + ".oid")
        off, _s, _v = self.ch["G1MS"]
        self.skel = parse_g1ms(self.buf, off)
        self.checks = {}

    # -- bones
    def bname(self, gid):
        h = self.oid.get(gid)
        if h is None:
            return None
        return self.names_table.get(h, "hash_0x%08x" % h)

    def bref(self, gid):
        return dict(id=gid, name=self.bname(gid))

    def bone_model(self, gid):
        loc = self.skel["g2l"].get(gid)
        return self.skel["model"][loc] if loc is not None else None

    def local_to_global(self, loc):
        return self.skel["l2g"].get(loc & 0x7FFFFFFF, -1)

    def skeleton_json(self):
        out = []
        for j in self.skel["joints"]:
            par = j["parent_raw"]
            parent_id = -1 if par == 0xFFFFFFFF else self.local_to_global(par)
            q, p = self.skel["model"][j["local"]]
            out.append(dict(local=j["local"], id=j["id"], name=self.bname(j["id"]), parent_id=parent_id,
                            local_pos=r(j["pos"]), local_rot=r(j["rot"], 6), local_scale=r(j["scale"]),
                            model_pos=r(p), model_rot=r(q, 6)))
        return out

    # -- meshes
    def g1mg(self):
        if not hasattr(self, "_g1mg"):
            off, _s, ver = self.ch["G1MG"]
            self._g1mg = parse_g1mg(self.buf, off, ver)
        return self._g1mg

    def lod0_meshes(self):
        G = self.g1mg()
        groups = [g for g in G["groups"] if g["lod"] == 0] or G["groups"][:1]
        out = []
        for g in groups:
            for k, m in enumerate(g["meshes"]):
                out.append(dict(m, group=g["group"], group_index=k))
        return out

    def palette_bones(self, pal_index, ids_are_global=False):
        pal = self.g1mg()["palettes"][pal_index]
        if ids_are_global:
            return [e[2] for e in pal]
        return [self.local_to_global(e[2]) for e in pal]

    def run(self):
        J = dict(format="doa6_g1m_physics", version=FORMAT_VERSION, source=os.path.basename(self.path),
                 units="cm",
                 axes="G1M model space, right-handed: +Y up, character faces +Z, +X = character's left. Rest pose. Quaternions (x,y,z,w).",
                 chunks={k: dict(version=ver_str(v), size=s) for k, (o, s, v) in self.ch.items()},
                 skeleton=self.skeleton_json())
        groups = []
        if "COLL" in self.ch:
            off, _s, ver = self.ch["COLL"]
            groups = parse_coll(self.buf, off, ver)
        self.coll_users = {}
        cloth = self.build_cloth()
        chains = self.build_chains()
        soft, attach, soft_skipped = self.build_soft()
        J["colliders"] = self.build_colliders(groups)
        J["cloth"] = cloth
        J["chains"] = chains
        J["soft_bodies"] = soft
        J["soft_attachments"] = attach
        J["swing_bones"] = self.build_swing()
        J["meshes"] = self.build_meshes(cloth, chains, soft)
        side = {}
        if os.path.isfile(self.base + ".rigbin"):
            side["rigbin"] = parse_rigbin(self.base + ".rigbin")
        if os.path.isfile(self.base + ".grp"):
            side["grp"] = parse_grp(self.base + ".grp")
        J["side_files"] = side
        J["summary"] = dict(bones=len(J["skeleton"]), collider_groups=len(J["colliders"]["groups"]),
                            colliders=sum(len(g["colliders"]) for g in J["colliders"]["groups"]),
                            cloth=[dict(index=c["index"], parent=c["parent"]["id"], grid="%dx%d%s" % (c["cols"], c["rows"], " ring" if c["ring"] else ""))
                                   for c in cloth],
                            chains=[dict(index=c["index"], parent=c["parent"]["id"], points=c["n"]) for c in chains],
                            soft_bodies=[dict(index=s["index"], parent=s["parent"]["id"], nodes=s["n"]) for s in soft],
                            swing_bones=len(J["swing_bones"]["entries"]) if J["swing_bones"] else 0,
                            physics_meshes=Counter(m["type_name"] for m in J["meshes"] if m["type"] != 0))
        skipped = []
        if getattr(self, "nuno_skipped", None):
            skipped += self.nuno_skipped
        skipped += soft_skipped
        J["skipped_sections"] = skipped
        J["checks"] = self.checks
        return J

    # -- colliders
    def build_colliders(self, groups):
        out = []
        for gi, g in enumerate(groups):
            cols = []
            for c in g["cols"]:
                m = c["m"]
                r0, r1, r2, t = m[0:3], m[4:7], m[8:11], m[12:15]
                rot = mat_rows_to_quat(r0, r1, r2)
                d = dict(type=c["type"], shape=COLLIDER_TYPES.get(c["type"], "unknown"), bone=self.bref(c["bone"]),
                         size_abc=r(list(c["size"][:3])), local_pos=r(t), local_rot=r(rot, 6),
                         local_axes_rows=r([list(r0), list(r1), list(r2)], 6),
                         flag_bytes=list(c["tail"][:4]))
                if c["bone2"] != 0xFFFFFFFF:
                    d["bone2"] = self.bref(c["bone2"])
                bm = self.bone_model(c["bone"])
                if bm:
                    d["model_pos"] = r(to_model(bm, t))
                    d["model_axis_y"] = r(qrot(bm[0], tuple(r1)), 6)
                    d["model_rot"] = r(qmul(bm[0], rot), 6)
                cols.append(d)
            users = self.coll_users.get(gi, [])
            d = dict(index=gi, flag=g["flag"], used_by=users, colliders=cols)
            if not users and gi == 0 and "_COS_" in os.path.basename(self.path).upper():
                d["note"] = ("not referenced by this costume. In 86 of 87 surveyed DOA6 costumes group 0 is unused by the costume "
                             "itself while HAIR parts reference group 0: most likely the body colliders for the hair's chains/cloth "
                             "(merge with the HAIR part's group 0) - likely, not proven")
            out.append(d)
        return dict(groups=out, notes=[
            "Each cloth / chain / soft body lists the collider groups it collides with (its collision_groups).",
            "local_pos/local_rot: collider frame in its bone's space. local_axes_rows: collider X/Y/Z axes in bone space "
            "(stored matrix is row-vector style: p_bone = p_collider * R + t).",
            "type 5 (most): capsule along the collider's local Y: a = radius (likely), b = half-length of the segment (likely); "
            "c = 50.0 in most cloth groups and ~= a or a different radius in soft-body groups: meaning not resolved "
            "(second radius of an elliptic/tapered capsule? 50 = default/unused?).",
            "type 6: ellipsoid (radii a,b,c along local X,Y,Z; a=b=c -> sphere) (likely). types 0/2 are rare (unresolved).",
            "flag_bytes [0xff,0,0xff,0] appear on groups used by cloth/chains, [0,0,0xff,0] on soft-body groups (meaning unknown)."])

    # -- cloth (NUNO1 / NUNO3 / NUNV1)
    def build_cloth(self):
        if "NUNO" not in self.ch:
            self.nuno = {"NUNO1": [], "NUNO3": [], "NUNO4": [], "skipped": []}
        else:
            off, _s, ver = self.ch["NUNO"]
            self.nuno = parse_nuno(self.buf, off, ver)
        self.nuno_skipped = self.nuno["skipped"]
        nunv = []
        if "NUNV" in self.ch:
            off, _s, ver = self.ch["NUNV"]
            nunv, sk = parse_nunv(self.buf, off, ver)
            self.nuno_skipped = self.nuno_skipped + sk
        n1, n3 = self.nuno["NUNO1"], self.nuno["NUNO3"]
        count = max(len(n1), len(n3), len(nunv))
        out = []
        for i in range(count):
            e1 = n1[i] if i < len(n1) else None
            e3 = n3[i] if i < len(n3) else None
            ev = nunv[i] if i < len(nunv) else None
            base = e3 or e1 or ev
            parent = base["parent"] & 0x7FFFFFFF
            cps, links = base["cps"], base["links"]
            same = all(e is None or (len(e["cps"]) == len(cps) and e["parent"] == base["parent"]) for e in (e1, e3, ev))
            cols, nrows, rowof, ring = grid_shape(links)
            bm = self.bone_model(parent)
            pal_id = e3["palette"] if e3 else (e1["params"][2] if e1 else ev["params"][0])
            pal_bones = self.palette_bones(pal_id, ids_are_global=True) if pal_id < len(self.g1mg()["palettes"]) else []
            cp_json = []
            for k, (c, l) in enumerate(zip(cps, links)):
                d = dict(i=k, row=rowof[k], local_pos=r(c[:3]), w=r(c[3]), left=l[0], right=l[1], up=l[2], down=l[3],
                         rest_right=r(l[4]), rest_down=r(l[5]))
                if bm:
                    d["model_pos"] = r(to_model(bm, c[:3]))
                cp_json.append(d)
            skin = []
            for k, s in enumerate(base["skin"]):
                nrm, w, cnt, idx = s[0:3], s[4:8], s[8], s[9:13]
                bones = [pal_bones[j] if j < len(pal_bones) else None for j in idx[:max(cnt, 1)]]
                skin.append(dict(cp=k, rest_normal=r(nrm, 6), bones=[self.bref(b) if b is not None else None for b in bones],
                                 weights=r(list(w[:max(cnt, 1)]), 5), palette_slots=list(idx[:max(cnt, 1)])))
            colls = sorted(set((e3 or {}).get("coll_groups", []) + (e1 or {}).get("coll_groups", []) + (ev or {}).get("coll_groups", [])))
            for g in colls:
                self.coll_users.setdefault(g, []).append("cloth[%d]" % i)
            d = dict(index=i, parent=self.bref(parent), n=len(cps), cols=cols, rows=nrows, ring=ring,
                     entries_consistent=same,
                     present_in=[k for k, e in (("NUNO1", e1), ("NUNO3", e3), ("NUNV1", ev)) if e is not None],
                     joint_palette=dict(index=pal_id, bones=[self.bref(b) for b in pal_bones]),
                     collision_groups=colls,
                     skinned_cps=len(base["skin"]),
                     notes=["control_points[].local_pos is in the parent bone's space; links: left/right/up/down CP index (-1 = none, "
                            "up = -1 means attached to the bone); rest_right / rest_down = rest distance to the right / down neighbour.",
                            "the first skinned_cps CPs (= 2 rows) are kinematic: skin[] gives their bones (global ids) and weights; "
                            "the rest are simulated (NUNO3 sim_ranges = [first, last] simulated CP)."],
                     control_points=cp_json, skin=skin)
            if e1:
                d["nuno1"] = dict(fixed_cps=e1["fixed"], row_starts=e1["row_starts"], collision_groups=e1["coll_groups"],
                                  params=named_params(e1["params"], NUNO1_NAMES))
            if e3:
                d["nuno3"] = dict(sim_ranges=[list(x) for x in e3["sim_ranges"]], collision_groups=e3["coll_groups"],
                                  extra_constraints=[dict(a=a, b=b, rest=r(L)) for a, b, L in e3["extra_constraints"]],
                                  extra4=[list(x) for x in e3["extra4"]],
                                  params=named_params(e3["params"], NUNO3_NAMES))
            if ev:
                d["nunv1"] = dict(collision_groups=ev["coll_groups"], params=named_params(ev["params"], NUNV1_NAMES))
            out.append(d)
        return out

    # -- chains (NUNO4)
    def build_chains(self):
        out = []
        for i, e in enumerate(self.nuno.get("NUNO4", [])):
            parent = e["parent"] & 0x7FFFFFFF
            bm = self.bone_model(parent)
            rmap = dict(e["maps"])
            recs = []
            for k, (x, y, z, w, flag, t, seg) in enumerate(e["recs"]):
                jl = rmap.get(k)
                gid = self.local_to_global(jl) if jl is not None else None
                d = dict(i=k, model_pos=r((x, y, z)), w=r(w), anchored=bool(flag & 0x80000000), flag="0x%08x" % flag,
                         t=r(t, 5), rest_len=r(seg), bone=self.bref(gid) if gid is not None else None)
                if bm:
                    d["local_pos"] = r(to_local(bm, (x, y, z)))
                recs.append(d)
            rots = []
            for R in e["rots"]:
                rots.append(dict(rows=r([list(R[0:3]), list(R[3:6]), list(R[6:9])], 6), quat=r(mat_rows_to_quat(R[0:3], R[3:6], R[6:9]), 6)))
            for g in e["coll_groups"]:
                self.coll_users.setdefault(g, []).append("chains[%d]" % i)
            # check: records sit on the mapped skeleton joints
            err = 0.0
            for k, jl in e["maps"]:
                p = self.skel["model"][jl][1]
                err = max(err, vlen(vsub(p, e["recs"][k][0:3])))
            self.checks.setdefault("chain_record_vs_joint_max_err_cm", 0.0)
            self.checks["chain_record_vs_joint_max_err_cm"] = r(max(self.checks["chain_record_vs_joint_max_err_cm"], err), 6)
            out.append(dict(index=i, parent=self.bref(parent), n=len(recs), collision_groups=e["coll_groups"],
                            root_rest_rotation=rots, params=named_params(e["params"], NUNO4_NAMES), points=recs,
                            notes=["points are the rest positions (model space) of real skeleton bones (bone); point 0 is anchored "
                                   "to the parent bone (flag 0x80000000) and moves with it.",
                                   "t = arc-length fraction along the chain, rest_len = distance to the previous point (verified).",
                                   "root_rest_rotation = model-space rest rotation of the first chain bone (rows = its local axes; "
                                   "verified). Every chain bone's local +X points at the next point (verified)."]))
        return out

    # -- soft bodies
    def build_soft(self):
        if "SOFT" not in self.ch:
            return [], [], []
        off, _s, ver = self.ch["SOFT"]
        bodies, attach, skipped = parse_soft(self.buf, off, ver)
        out = []
        for bi, b in enumerate(bodies):
            h = b["h"]
            parent_gid = self.local_to_global(h[7])
            bm = self.bone_model(parent_gid)
            bones = [self.local_to_global(x) for x in b["bones"]]
            n = len(b["nodes"])
            nparams = len(b["tail"]) - 2 * n
            params = b["tail"][:nparams]
            arr = b["tail"][nparams:]
            node_json = []
            cells = []
            for nd in b["nodes"]:
                c = nd["cell"]
                cell = (c & 1023, (c >> 10) & 1023, (c >> 20) & 1023)
                cells.append(cell)
                skin = [dict(bone=self.bref(bones[j]) if j < len(bones) else None, slot=j, weight=r(w, 5)) for j, w in nd["pairs"][:-1]]
                selfid, selfw = nd["pairs"][-1]
                d = dict(id=nd["id"], model_pos=r(nd["pos"]), normal=r(nd["nrm"], 5), cell=list(cell),
                         flags=nd["flags"], surface=bool(nd["flags"] & 0x40), interior=bool(nd["flags"] & 0x20),
                         skin=skin, w_self=r(selfw, 5), extra3=r(list(nd["extra"][:3]), 6))
                if selfid != nd["id"]:
                    d["self_pair_id"] = selfid
                if any(nd["extra"][3:]):
                    d["extra_ints"] = list(nd["extra"][3:])
                if bm:
                    d["local_pos"] = r(to_local(bm, nd["pos"]))
                if c >> 30:
                    d["cell_top_bits"] = c >> 30
                node_json.append(d)
            # node links are not stored: the lattice cell coordinates imply them. Give the 6 axis neighbours
            # (structural springs) for convenience; face (12) and body (8) diagonals follow the same way.
            by_cell = {cell: nd["id"] for cell, nd in zip(cells, b["nodes"])}
            for cell, d in zip(cells, node_json):
                d["n6"] = [by_cell.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), -1)
                           for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
            lattice = self.fit_lattice(cells, [nd["pos"] for nd in b["nodes"]])
            lattice["note"] = ("node model_pos = origin + cell.x*axis_x + cell.y*axis_y + cell.z*axis_z (exact). "
                               "n6 = neighbour ids in +x,-x,+y,-y,+z,-z (-1 = none). cell is packed 10:10:10 in the file.")
            vol = 0.0
            P = [nd["pos"] for nd in b["nodes"]]
            for a, bb, cc in b["tris"]:
                vol += vdot(P[a], vcross(P[bb], P[cc])) / 6.0
            edges = Counter()
            for a, bb, cc in b["tris"]:
                for e2 in ((a, bb), (bb, cc), (cc, a)):
                    edges[tuple(sorted(e2))] += 1
            closed = all(v == 2 for v in edges.values())
            for g in b["coll_groups"]:
                self.coll_users.setdefault(g, []).append("soft_bodies[%d]" % bi)
            out.append(dict(index=bi, body_id=h[0], parent=self.bref(parent_gid), parent_local=h[7], n=n,
                            header_words=h, header_params=named_params(b["hf"], SOFT_HEADER_NAMES),
                            skin_bones=[self.bref(x) for x in bones], collision_groups=[int(x) for x in b["coll_groups"]],
                            node_order=b["order"] if b["order"] != list(range(n)) else "identity",
                            lattice=lattice,
                            hull=dict(triangles=[list(t) for t in b["tris"]], closed=closed, signed_volume_cm3=r(vol, 2),
                                      note="closed, consistently wound hull over surface nodes (negative volume = inward winding)"),
                            param_block_version=b["param_version"],
                            notes=["nodes[].model_pos: rest position in model space (local_pos: in the parent bone's space).",
                                   "nodes[].skin: bones (global ids) and weights that carry the node's target position.",
                                   "flags: 0x40 surface node, 0x20 interior node, 0x10 rare (verified from lattice position); "
                                   "0x02 always set; 0x01 set on the chest-wall layer of breast bodies (pinned? guess); "
                                   "bodies whose nodes all carry 0x80|0x01 (buttocks/hips) are a second body class (guess).",
                                   "w_self (last pair of the node record, 0.1..1): per-node weight, meaning unresolved "
                                   "(simulation share vs. skinned target? guess).",
                                   "extra3: per-node vector that always points along ~(0.55,0.72,0.41): effectively one painted "
                                   "scalar per node (meaning unresolved).",
                                   "params: parameter block of version param_block_version (v6 = 58 words, v7 59, v8 60, v9 61, "
                                   "v10 63); per_node_arrays: two per-node float arrays (all 1.0 for Kasumi).",
                                   "hull: closed triangle hull over surface nodes -> volume preservation and/or collision (likely)."],
                            params=[raw_value(v) for v in params],
                            per_node_arrays=[[r(f32(v), 5) for v in arr[k * n:(k + 1) * n]] for k in range(len(arr) // n)] if n else [],
                            nodes=node_json))
        att = []
        for a in attach:
            gid = self.local_to_global(a["bone"])
            att.append(dict(bone=self.bref(gid), bone_local=a["bone"], vec=r(list(a["vec"]), 6),
                            refs=[dict(body=x["body"], weight=r(x["weight"], 5), nodes=list(x["nodes"]), node_weights=r(list(x["weights"]), 6))
                                  for x in a["refs"]]))
        return out, att, skipped

    def fit_lattice(self, cells, pos):
        """least-squares affine fit pos = origin + x*ax + y*ay + z*az (pure python 4x4 normal equations)"""
        rows = [(c[0], c[1], c[2], 1.0) for c in cells]
        ata = [[sum(a[i] * a[j] for a in rows) for j in range(4)] for i in range(4)]
        sol = []
        for dim in range(3):
            atb = [sum(a[i] * p[dim] for a, p in zip(rows, pos)) for i in range(4)]
            sol.append(solve4(ata, atb))
        ax = tuple(sol[d][0] for d in range(3))
        ay = tuple(sol[d][1] for d in range(3))
        az = tuple(sol[d][2] for d in range(3))
        org = tuple(sol[d][3] for d in range(3))
        err = 0.0
        for c, p in zip(cells, pos):
            q = vadd(vadd(vadd(org, vscale(ax, c[0])), vscale(ay, c[1])), vscale(az, c[2]))
            err = max(err, vlen(vsub(q, p)))
        self.checks["soft_lattice_fit_max_err_cm"] = r(max(self.checks.get("soft_lattice_fit_max_err_cm", 0.0), err), 6)
        return dict(origin=r(org), axis_x=r(ax, 5), axis_y=r(ay, 5), axis_z=r(az, 5), max_fit_error=r(err, 6),
                    cell_min=[min(c[k] for c in cells) for k in range(3)], cell_max=[max(c[k] for c in cells) for k in range(3)])

    # -- swing bones
    def build_swing(self):
        path = self.base + ".swg"
        if not os.path.isfile(path):
            return None
        s = parse_swg(path)
        ents = []
        for e in s["entries"]:
            bm = self.bone_model(e["bone"])
            loc = self.skel["g2l"].get(e["bone"])
            parent_id = None
            if loc is not None:
                par = self.skel["joints"][loc]["parent_raw"]
                parent_id = -1 if par == 0xFFFFFFFF else self.local_to_global(par)
            ents.append(dict(group=e["group"], bone=self.bref(e["bone"]), parent_id=parent_id,
                             model_pos=r(bm[1]) if bm else None,
                             params=named_params(e["vals"], SWG_NAMES), tail_bytes=e["tail"]))
        return dict(file=os.path.basename(path), preset=s["preset"], header_size=s["header_size"],
                    header_words=[raw_value(v) for v in s["header_words"]], size_ok=s["size_ok"], entries=ents,
                    notes=["72-byte entries: u16 group, u16 bone (global id), 15 x 32-bit params, 8 bytes.",
                           "params 0..3 look like angle limits in degrees (0..90, often a/b asymmetric and c==d); "
                           "group is shared by the bones of one strand; others unresolved (see findings)."])

    # -- meshes
    def build_meshes(self, cloth, chains, soft):
        G = self.g1mg()
        chain_bones = {}
        for c in chains:
            for p in c["points"]:
                if p["bone"]:
                    chain_bones[p["bone"]["id"]] = c["index"]
        swing = set()
        sw = self.build_swing()
        if sw:
            swing = {e["bone"]["id"] for e in sw["entries"]}
        out = []
        nuno3 = self.nuno.get("NUNO3", [])
        nuno1 = self.nuno.get("NUNO1", [])
        bodies = soft
        worst_cos, worst_soft = 1.0, 0.0
        for mi, m in enumerate(self.lod0_meshes()):
            for smi in m["submeshes"]:
                sm = G["submeshes"][smi]
                d = dict(mesh_index=mi, name=m["name"], type=m["type"],
                         type_name={0: "skinned", 1: "cloth_surface", 2: "skinned_on_physics_bones", 4: "soft_body"}.get(m["type"], "unknown"),
                         external=(m["external"] if m["external"] != 0xFFFFFFFF else -1), submesh=smi,
                         group=m["group"], vertex_count=sm["vcount"], material=sm["material"])
                if m["type"] == 0:
                    out.append(d)
                    continue
                pal = self.palette_bones(sm["palette"])
                if m["type"] == 1:
                    ci = m["external"] - 20000 if m["external"] >= 20000 else m["external"] % 10000
                    src = nuno3 if m["external"] >= 20000 else nuno1
                    d["driver"] = dict(kind="cloth", cloth_index=ci)
                    if 0 <= ci < len(src):
                        e = src[ci]
                        bm = self.bone_model(e["parent"] & 0x7FFFFFFF)
                        data, cos = self.cloth_vertices(sm, e["cps"], pal, bm)
                        worst_cos = min(worst_cos, cos)
                        d.update(data)
                elif m["type"] == 2:
                    phys = sorted(set(x[1] for x in G["palettes"][sm["palette"]]))
                    used_chains = sorted(set(chain_bones[b] for b in pal if b in chain_bones))
                    d["driver"] = dict(kind="skinning", palette_bones=[self.bref(b) for b in pal], chains=used_chains,
                                       swing_bones=sorted(b for b in pal if b in swing),
                                       palette_physics_index=phys,
                                       note="ordinary linear-blend skinning; the bones are moved by chains / swing bones"
                                            if phys == [0] else "palette has physics indices: vertices may be in physics-joint space")
                elif m["type"] == 4:
                    d["driver"] = dict(kind="soft_body", body_index=m["external"])
                    if m["external"] < len(bodies):
                        data, err = self.soft_vertices(sm, bodies[m["external"]], pal)
                        worst_soft = max(worst_soft, err)
                        d.update(data)
                out.append(d)
        if any(m["type"] == 1 for m in self.lod0_meshes()):
            self.checks["cloth_normals_min_mean_abs_cos"] = r(worst_cos, 4)
        if any(m["type"] == 4 for m in self.lod0_meshes()):
            self.checks["soft_vertex_interp_max_err_cm"] = r(worst_soft, 5)
        return out

    def cloth_vertices(self, sm, cps, pal, bm):
        buf, G = self.buf, self.g1mg()
        wh = read_attr(buf, G, sm, SEM_POSITION, 0)
        wv = read_attr(buf, G, sm, SEM_WEIGHT, 0)
        dwh = read_attr(buf, G, sm, SEM_BINORMAL, 0)
        dwv = read_attr(buf, G, sm, SEM_COLOR, 1)
        rows = [read_attr(buf, G, sm, SEM_INDEX, 0), read_attr(buf, G, sm, SEM_PSIZE, None, True),
                read_attr(buf, G, sm, SEM_FOG, None, True), read_attr(buf, G, sm, SEM_UV, None, True)]
        nrm = read_attr(buf, G, sm, SEM_NORMAL, 0)
        tan = read_attr(buf, G, sm, SEM_TANGENT, 0)
        uv = read_attr(buf, G, sm, SEM_UV, 0)
        P = [c[:3] for c in cps]
        n = sm["vcount"]
        cl = dict(index=[], cp=[], w_h=[], w_v=[], dw_h=[], dw_v=[], depth=[], normal_coef=[], tangent_coef=[])
        sk = dict(index=[], local_pos=[], bones=[], weights=[])
        rest = [None] * n
        geo_n = [None] * n
        for i in range(n):
            if not any(dwh[i]) and not any(dwv[i]):
                pl = wh[i][:3]
                rest[i] = to_model(bm, pl) if bm else pl
                sk["index"].append(i)
                sk["local_pos"] += r(list(pl))
                if any(rows[0][i][k] % 3 for k in range(4)):
                    self.checks["joint_index_not_multiple_of_3"] = self.checks.get("joint_index_not_multiple_of_3", 0) + 1
                ids = [rows[0][i][k] // 3 for k in range(4)]
                sk["bones"] += [pal[j] if j < len(pal) else -1 for j in ids]
                sk["weights"] += r(list(wv[i]), 5)
                continue
            u = [tuple(sum(wh[i][j] * P[rows[k][i][j]][a] for j in range(4)) for a in range(3)) for k in range(4)]
            v = [tuple(sum(dwh[i][j] * P[rows[k][i][j]][a] for j in range(4)) for a in range(3)) for k in range(4)]
            a_ = tuple(sum(wv[i][k] * u[k][x] for k in range(4)) for x in range(3))
            b_ = tuple(sum(dwv[i][k] * u[k][x] for k in range(4)) for x in range(3))
            c_ = tuple(sum(wv[i][k] * v[k][x] for k in range(4)) for x in range(3))
            dd = vcross(b_, c_)
            pl = vadd(a_, vscale(dd, nrm[i][3]))
            rest[i] = to_model(bm, pl) if bm else pl
            nn = vadd(vadd(vscale(c_, nrm[i][0]), vscale(b_, nrm[i][1])), vscale(dd, nrm[i][2]))
            geo_n[i] = vscale(nn, 1.0 / (vlen(nn) or 1.0))
            cl["index"].append(i)
            cl["cp"] += [rows[k][i][j] for k in range(4) for j in range(4)]
            cl["w_h"] += r(list(wh[i]), 6)
            cl["w_v"] += r(list(wv[i]), 6)
            cl["dw_h"] += r(list(dwh[i]), 6)
            cl["dw_v"] += r(list(dwv[i]), 6)
            cl["depth"].append(r(nrm[i][3], 6))
            cl["normal_coef"] += r(list(nrm[i][:3]), 5)
            cl["tangent_coef"] += r(list(tan[i]), 5) if tan else []
        tris = read_triangles(buf, G, sm)
        # check: stored normals vs geometric normals of the rebuilt surface (cloth vertices only)
        acc = [(0.0, 0.0, 0.0)] * n
        for t in range(0, len(tris) - 2, 3):
            a, b, c = tris[t], tris[t + 1], tris[t + 2]
            fn = vcross(vsub(rest[b], rest[a]), vsub(rest[c], rest[a]))
            for x in (a, b, c):
                acc[x] = vadd(acc[x], fn)
        cs = []
        for i in range(n):
            if geo_n[i] is not None and vlen(acc[i]) > 0:
                q = to_local(bm, vadd(bm[1], acc[i])) if bm else acc[i]
                cs.append(abs(vdot(geo_n[i], vscale(q, 1.0 / vlen(q)))))
        mean_cos = sum(cs) / len(cs) if cs else 1.0
        data = dict(rebuild=dict(
            formula="u_k = sum_j w_h[j]*CP[cp[k][j]], v_k = sum_j dw_h[j]*CP[cp[k][j]] (k = 4 rows, j = 4 columns); "
                    "a = sum_k w_v[k]*u_k; b = sum_k dw_v[k]*u_k; c = sum_k w_v[k]*v_k; d = cross(b, c) (NOT normalized); "
                    "position = a + d*depth; normal = normalize(c*n.x + b*n.y + d*n.z); same for the tangent (w = handedness). "
                    "CPs and results are in the cloth parent bone's space.",
            cloth_vertices=len(cl["index"]), skinned_vertices=len(sk["index"]), normal_check_mean_abs_cos=r(mean_cos, 4)))
        if self.keep_vertices:
            data["cloth_vertices"] = cl
            data["skinned_vertices"] = dict(sk, note="rigid part of the cloth mesh (e.g. waistband): local_pos is in the cloth "
                                                     "parent bone's space, bones are global ids (palette index = JointIndex/3)")
            data["rest_model_pos"] = r([list(p) for p in rest])
            data["uv"] = r([list(x) for x in uv], 5) if uv else None
            data["triangles"] = tris
        return data, mean_cos

    def soft_vertices(self, sm, body, pal):
        buf, G = self.buf, self.g1mg()
        pos = read_attr(buf, G, sm, SEM_POSITION, 0)
        ids1 = read_attr(buf, G, sm, SEM_PSIZE, 0)
        ids2 = read_attr(buf, G, sm, SEM_FOG, 0)
        w1 = read_attr(buf, G, sm, SEM_UV, 8)
        w2 = read_attr(buf, G, sm, SEM_UV, 9)
        blend = read_attr(buf, G, sm, SEM_SAMPLE, 0)
        jw = read_attr(buf, G, sm, SEM_WEIGHT, 0)
        ji = read_attr(buf, G, sm, SEM_INDEX, 0)
        uv = read_attr(buf, G, sm, SEM_UV, 0)
        node_pos = {nd["id"]: nd["model_pos"] for nd in body["nodes"]}
        err = 0.0
        out = dict(node_ids=[], node_w=[], blend=[], bones=[], bone_w=[])
        for i in range(sm["vcount"]):
            ids = list(ids1[i]) + list(ids2[i])
            w = list(w1[i]) + list(w2[i])
            p, wsum = (0.0, 0.0, 0.0), 0.0
            for k in range(8):
                if ids[k] == 0xFFFFFFFF or ids[k] not in node_pos:
                    if w[k]:
                        self.checks["soft_vertex_missing_node_weight"] = r(self.checks.get("soft_vertex_missing_node_weight", 0.0) + w[k], 4)
                    ids[k] = -1
                    continue
                if w[k]:
                    p = vadd(p, vscale(tuple(node_pos[ids[k]]), w[k]))
                    wsum += w[k]
            if wsum > 0.5:
                err = max(err, vlen(vsub(vscale(p, 1.0 / wsum), pos[i][:3])))
            out["node_ids"] += ids
            out["node_w"] += r(w, 6)
            out["blend"].append(r(blend[i][0], 5) if blend else None)
            if any(x % 3 for x in ji[i]):
                self.checks["joint_index_not_multiple_of_3"] = self.checks.get("joint_index_not_multiple_of_3", 0) + 1
            out["bones"] += [pal[x // 3] if x // 3 < len(pal) else -1 for x in ji[i]]
            out["bone_w"] += r([float(x) for x in jw[i]], 5)
        data = dict(rebuild=dict(
            formula="soft position = sum_k node_w[k] * node_pos[node_ids[k]] (8 nodes = one lattice cell, trilinear/FFD); "
                    "bone skinning (bones/bone_w, global ids) gives the rigid position; "
                    "blend (Sample0) is 0 at the front of the breast and 1 near the body edge: likely "
                    "final = lerp(soft, skinned, blend) (guess)",
            interpolation_max_err_cm=r(err, 5)))
        if self.keep_vertices:
            data["soft_vertices"] = out
            data["rest_model_pos"] = r([list(p[:3]) for p in pos])
            data["uv"] = r([list(x) for x in uv], 5) if uv else None
            data["triangles"] = read_triangles(buf, G, sm)
        return data, err


def solve4(a, b):
    m = [list(row) + [bb] for row, bb in zip(a, b)]
    for c in range(4):
        piv = max(range(c, 4), key=lambda k: abs(m[k][c]))
        m[c], m[piv] = m[piv], m[c]
        if abs(m[c][c]) < 1e-12:
            return [0.0] * 4
        for k in range(4):
            if k != c:
                f = m[k][c] / m[c][c]
                for j in range(c, 5):
                    m[k][j] -= f * m[c][j]
    return [m[k][4] / m[k][k] for k in range(4)]


def summarize(J):
    lines = ["%s: %d bones" % (J["source"], len(J["skeleton"]))]
    for g in J["colliders"]["groups"]:
        lines.append("  collider group %d: %d colliders %s, used by %s" % (
            g["index"], len(g["colliders"]), dict(Counter(c["type"] for c in g["colliders"])), g["used_by"] or "-"))
    for c in J["cloth"]:
        lines.append("  cloth %d: parent %s (%s) %d CPs = %d cols x %d rows%s, skinned CPs %d, collides with %s" % (
            c["index"], c["parent"]["id"], c["parent"]["name"], c["n"], c["cols"], c["rows"], " ring" if c["ring"] else "",
            c["skinned_cps"], c["collision_groups"]))
    for c in J["chains"]:
        lines.append("  chain %d: parent %s (%s) %d points, bones %s..%s, collides with %s" % (
            c["index"], c["parent"]["id"], c["parent"]["name"], c["n"],
            c["points"][0]["bone"]["id"] if c["points"][0]["bone"] else "-", c["points"][-1]["bone"]["id"] if c["points"][-1]["bone"] else "-",
            c["collision_groups"]))
    for s in J["soft_bodies"]:
        lines.append("  soft body %d: parent %s (%s) %d nodes, lattice %s..%s, hull %d tris (closed %s, %.0f cm3), collides with %s" % (
            s["index"], s["parent"]["id"], s["parent"]["name"], s["n"], s["lattice"]["cell_min"], s["lattice"]["cell_max"],
            len(s["hull"]["triangles"]), s["hull"]["closed"], -s["hull"]["signed_volume_cm3"], s["collision_groups"]))
    for a in J["soft_attachments"]:
        lines.append("  soft attachment: bone %s follows %s" % (a["bone"]["id"], [(x["body"], x["weight"]) for x in a["refs"]]))
    if J["swing_bones"]:
        lines.append("  swing bones: %s" % [e["bone"]["id"] for e in J["swing_bones"]["entries"]])
    for m in J["meshes"]:
        if m["type"] != 0:
            lines.append("  mesh %s type %d (%s) submesh %d: %d verts, driver %s" % (
                m["name"], m["type"], m["type_name"], m["submesh"], m["vertex_count"],
                {k: v for k, v in m.get("driver", {}).items() if k in ("kind", "cloth_index", "body_index", "chains")}))
    lines.append("  checks: %s" % J["checks"])
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("g1m", nargs="+")
    ap.add_argument("-o", "--out-dir", default=None, help="output folder (default: next to the .g1m)")
    ap.add_argument("--no-vertices", action="store_true", help="leave out per-vertex data of cloth / soft meshes")
    ap.add_argument("--oid-table", default=OID_H_DEFAULT, help="Project G1M Oid.h for extra bone names (optional)")
    ap.add_argument("--indent", type=int, default=None)
    args = ap.parse_args()
    names = load_name_table(args.oid_table)
    for path in args.g1m:
        part = Part(path, names, keep_vertices=not args.no_vertices)
        J = part.run()
        out_dir = args.out_dir or os.path.dirname(os.path.abspath(path))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(J, f, indent=args.indent, separators=None if args.indent else (",", ":"))
        print(summarize(J))
        print("  -> %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    sys.exit(main())
