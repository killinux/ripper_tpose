"""Add an outfit's battle weapon to its PMX (Rise of Eros).

The HD prefab our PMX is built from has no weapon in some outfits: a08's sword is shown only in battle, where the
battle (LD) prefab carries it as skinned meshes - wp_a08_l, the left half of the sword with its chain (bones
Point007_L, chain01-04) and wp_a08_r, the right half (Point007_R).  The HD bundle's own wp_a08 is a loose static
copy at the origin.  The HD skeleton has the weapon bones too, the battle clips animate them (the two halves part
and close in the skills), the showcase clips leave them alone (no weapon in the showcase).

This appends to the PMX in its binary form; every byte that was there stays where it was, so existing indices
(morph offsets, rigid bodies, IK) keep pointing at the same things:
  bones     the meshes' bones plus the ancestors that link them (Point007_L > chain_ALL > chain02 ...); the first
            ancestor the PMX has, else 全ての親 (their game parent, Root, has no PMX bone), is the parent.  Heads at
            the HD skeleton's rest, the pose make_roe_vmd.py measures motion from
  vertices  the battle meshes skinned at that rest (rest world x bind pose), game -> PMX by the similarity fitted
            on the bones both have (hair, skirt, knees ...: not the arms, which the exporter swung down to an
            A-pose); faces wound like the PMX's own
  material  one per renderer, settings copied from the body's; texture = the HD weapon material's PMX diffuse
            from hq_material_data.py (albedo x _BaseColor x AO, as for the body), copied into textures\\
  morph     武器非表示 folds the weapon away; its English name lists the weapon's root bones ("hide weapon:
            Point007_L,Point007_R"), and export_roe_motions.py keys it 1 in the clips that leave all of them alone
  frame     a 武器 display frame with the new bones

  python pmx_add_weapon.py a08                        the archive PMX, its _bustB sibling, the D:\\roe_exports source
  python pmx_add_weapon.py a08 --pmx X.pmx --out Y.pmx    one file (a test copy)
  options: --albedo <texture name> (default <weapon>_rgbx_Albedo, e.g. wp_a08_rgbx_Albedo)   --dry-run
A PMX that already has the weapon morph is left alone.  Originals go to <archive>\\_meta\\pmx_old\\weapon_<date>\\.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import struct
import subprocess
import sys

import numpy as np
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decode_roe_clip as dec  # noqa: E402
import pmx_add_scale_morph as psm  # noqa: E402
from roe_motion_common import ARCHIVE, ROE_EXPORTS, bundles, find_pmx, pmx_copies  # noqa: E402

HQ_CACHE = os.path.join(ROE_EXPORTS, "_hq_materials")
MORPH = "武器非表示"
MORPH_TAG = "hide weapon: "
FRAME, FRAME_E = "武器", "Weapon"


# ---------------------------------------------------------------- game side

def quat_matrix(x, y, z, w):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def trs(pos, rot, scale):
    m = np.eye(4)
    m[:3, :3] = quat_matrix(*rot) * np.asarray(scale, dtype=float)[None, :]
    m[:3, 3] = pos
    return m


def rest_worlds(skeleton):
    """Unity world matrix of every transform at its rest; a skinned bone at its bind pose (renderer world x
    inverse bindpose), which is what our FBX / PMX rest and make_roe_vmd.py's rest_world() are."""
    rest = []
    for b in skeleton:
        m = trs(b["pos"], b["rot"], b["scale"])
        rest.append(m if b["parent"] < 0 else rest[b["parent"]] @ m)
    out = []
    for i, b in enumerate(skeleton):
        bind = b.get("bind")
        out.append(rest[i] if bind is None else rest[bind["renderer"]] @ np.linalg.inv(np.array(bind["inv"])))
    return out


def weapon_renderers(env):
    """The skinned weapons (renderers named wp_*) of a prefab bundle: name, mesh vertices / normals / uv0,
    triangles, per-vertex [(bone slot, weight)], bone names and bind poses."""
    out = []
    for obj in env.objects:
        if obj.type.name != "SkinnedMeshRenderer":
            continue
        smr = obj.read()
        go = smr.m_GameObject.read()
        if not go.m_Name.lower().startswith("wp_") or not smr.m_Mesh.path_id:
            continue
        mesh = smr.m_Mesh.read()
        h = MeshHandler(mesh)
        h.process()
        n = len(h.m_Vertices)
        bones = [b.read().m_GameObject.read().m_Name for b in smr.m_Bones]
        binds = [np.array([[getattr(m, "e%d%d" % (r, c)) for c in range(4)] for r in range(4)])
                 for m in mesh.m_BindPose]
        index = h.m_BoneIndices or [(0,)] * n
        # BlendIndices without BlendWeight (wp_a08_r): one bone per vertex, weight 1
        weight = h.m_BoneWeights or [(1.0,) + (0.0,) * (len(ix) - 1) for ix in index]
        skin = []
        for ix, ws in zip(index, weight):
            acc = {}
            for i, w in zip(ix, ws):
                if w > 0:
                    acc[i] = acc.get(i, 0.0) + w
            total = sum(acc.values())
            skin.append(sorted(((i, w / total) for i, w in acc.items()), key=lambda p: -p[1])[:4])
        tris = [tuple(t) for sub in h.get_triangles() for t in sub]
        out.append({"name": go.m_Name, "v": np.array(h.m_Vertices, dtype=float),
                    "n": np.array(h.m_Normals, dtype=float), "uv": np.array(h.m_UV0, dtype=float)[:, :2],
                    "tris": tris, "bones": bones, "binds": binds, "skin": skin})
    return sorted(out, key=lambda r: r["name"])


def skin_at_rest(r, world_of):
    """World positions and normals of a renderer's vertices with its bones at their rest."""
    mats = [world_of[b] @ bp for b, bp in zip(r["bones"], r["binds"])]
    V = np.zeros_like(r["v"])
    N = np.zeros_like(r["n"])
    for i, pairs in enumerate(r["skin"]):
        for slot, w in pairs:
            M = mats[slot]
            V[i] += w * (M[:3, :3] @ r["v"][i] + M[:3, 3])
            N[i] += w * (M[:3, :3] @ r["n"][i])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return V, N


# ---------------------------------------------------------------- PMX layout

def layout(data):
    """Offsets of every section of a PMX 2.0 and the tables the weapon needs; walks to the last byte."""
    r = psm.Reader(data)
    assert data[:4] == b"PMX ", "not a PMX file"
    r.skip(4)
    version = r.take("f")
    n_glob = r.take("B")
    g = list(struct.unpack_from("<%dB" % n_glob, data, r.p))
    r.skip(n_glob)
    enc, add_uv, vsz, tsz, msz, bsz, mosz, rsz = g[:8]
    E = "utf-16-le" if enc == 0 else "utf-8"
    for _ in range(4):
        r.text()
    L = {"version": version, "glob": g, "enc": E, "add_uv": add_uv, "vsz": vsz, "tsz": tsz, "msz": msz, "bsz": bsz,
         "mosz": mosz, "rsz": rsz}
    bfmt, tfmt = psm.index_fmt(bsz), psm.index_fmt(tsz)
    L["v_at"] = r.p
    nv = r.take("i")
    pos, nrm = np.zeros((nv, 3)), np.zeros((nv, 3))
    for i in range(nv):
        pos[i] = r.take("3f")
        nrm[i] = r.take("3f")
        r.skip(8 + 16 * add_uv)
        kind = r.take("B")
        r.skip({0: bsz, 1: 2 * bsz + 4, 2: 4 * bsz + 16, 3: 2 * bsz + 4 + 36, 4: 4 * bsz + 16}[kind] + 4)
    L.update(nv=nv, v_end=r.p, pos=pos, nrm=nrm)
    L["f_at"] = r.p
    nf = r.take("i")
    ffmt = psm.index_fmt(vsz, True)
    L["faces"] = np.array(struct.unpack_from("<%d%s" % (nf, ffmt), data, r.p)).reshape(-1, 3)
    r.skip(nf * vsz)
    L.update(nf=nf, f_end=r.p, t_at=r.p)
    L["textures"] = [r.text().decode(E) for _ in range(r.take("i"))]
    L.update(t_end=r.p, m_at=r.p)
    mats = []
    for _ in range(r.take("i")):
        start = r.p
        name = r.text().decode(E)
        r.text()
        diffuse, specular, power, ambient = r.take("4f"), r.take("3f"), r.take("f"), r.take("3f")
        flags = r.take("B")
        edge, edge_size = r.take("4f"), r.take("f")
        tex, sphere = r.take(tfmt), r.take(tfmt)
        sphere_mode, shared = r.take("B"), r.take("B")
        toon = r.take("B") if shared else r.take(tfmt)
        memo = r.text()
        faces = r.take("i")
        mats.append({"name": name, "diffuse": diffuse, "specular": specular, "power": power, "ambient": ambient,
                     "flags": flags, "edge": edge, "edge_size": edge_size, "tex": tex, "sphere": sphere,
                     "sphere_mode": sphere_mode, "shared": shared, "toon": toon, "faces": faces,
                     "bytes": data[start:r.p]})
    L.update(materials=mats, m_end=r.p, b_at=r.p)
    bones = []
    for _ in range(r.take("i")):
        name, name_e = r.text().decode(E), r.text().decode(E)
        head = r.take("3f")
        parent = r.take(bfmt)
        r.skip(4)
        flags = r.take("H")
        r.skip(bsz if flags & 0x0001 else 12)
        if flags & 0x0300:
            r.skip(bsz + 4)
        if flags & 0x0400:
            r.skip(12)
        if flags & 0x0800:
            r.skip(24)
        if flags & 0x2000:
            r.skip(4)
        if flags & 0x0020:
            r.skip(bsz + 8)
            for _ in range(r.take("i")):
                r.skip(bsz)
                if r.take("B"):
                    r.skip(24)
        bones.append({"name": name, "name_e": name_e, "head": head, "parent": parent})
    L.update(bones=bones, b_end=r.p)
    # morphs, frames, rigid bodies, joints: only walked, to prove the file ends where it should
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(1)
        kind = r.take("B")
        count = r.take("i")
        size = {0: mosz + 4, 1: vsz + 12, 2: bsz + 28, 3: vsz + 16, 4: vsz + 16, 5: vsz + 16, 6: vsz + 16,
                7: vsz + 16, 8: msz + 1 + 112, 9: mosz + 4, 10: rsz + 1 + 24}[kind]
        r.skip(count * size)
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(1)
        for _ in range(r.take("i")):
            t = r.take("B")
            r.skip(mosz if t == 1 else bsz)
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(bsz + 61)
    for _ in range(r.take("i")):
        r.text(), r.text()
        r.skip(1 + 2 * rsz + 96)
    if version >= 2.1:
        raise ValueError("PMX 2.1 (soft bodies) is not handled")
    assert r.p == len(data), "PMX walk ended at %d of %d bytes" % (r.p, len(data))
    return L


def text(s, enc):
    b = s.encode(enc)
    return struct.pack("<i", len(b)) + b


def winding_sign(pos, nrm, faces, sample=4000):
    """+1 when a face's (b - a) x (c - a) points along its vertices' normals, -1 when against."""
    f = faces[:: max(1, len(faces) // sample)]
    a, b, c = pos[f[:, 0]], pos[f[:, 1]], pos[f[:, 2]]
    geo = np.cross(b - a, c - a)
    dots = np.einsum("ij,ij->i", geo, nrm[f[:, 0]] + nrm[f[:, 1]] + nrm[f[:, 2]])
    return 1 if (dots > 0).sum() >= (dots < 0).sum() else -1


def fit_similarity(P, Q):
    """s, R, t with Q ~ s R P + t (rows are points), R a proper rotation (Umeyama)."""
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(B.T @ A)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt)) or 1.0])
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / (A ** 2).sum())
    return s, R, mq - s * R @ mp


def game_to_pmx(L, skeleton, world, log):
    """The similarity taking Unity world space to the PMX, fitted on the bones both have (by game name: a PMX
    bone's English name holds it when the exporter shortened the Japanese one).  The arms are left out: the
    exporter swung them down to an A-pose."""
    names = [b["name"] for b in skeleton]
    index = {n: i for i, n in enumerate(names)}

    def under_arm(i):
        while i >= 0:
            if re.search(r"(Clavicle|UpperArm)$", names[i]):
                return True
            i = skeleton[i]["parent"]
        return False

    P, Q, used = [], [], []
    for b in L["bones"]:
        gname = b["name_e"] or b["name"]
        i = index.get(gname)
        if i is None or under_arm(i):
            continue
        P.append(world[i][:3, 3])
        Q.append(b["head"])
        used.append(gname)
    P, Q = np.array(P), np.array(Q)
    if len(P) < 6:
        raise ValueError("only %d bones shared by the game skeleton and the PMX" % len(P))
    keep = np.ones(len(P), bool)
    for _ in range(3):
        s, R, t = fit_similarity(P[keep], Q[keep])
        res = np.linalg.norm(P @ (s * R).T + t - Q, axis=1)
        keep = res < max(0.05, 4 * np.median(res[keep]))
    s, R, t = fit_similarity(P[keep], Q[keep])
    res = np.linalg.norm(P @ (s * R).T + t - Q, axis=1)
    log("game -> PMX: scale %.4f, rotation %s, offset %s; %d of %d shared bones, residual mean %.4f max %.4f PMX units"
        % (s, np.round(R, 3).tolist(), np.round(t, 4).tolist(), keep.sum(), len(P), res[keep].mean(), res[keep].max()))
    dropped = [u for u, k in zip(used, keep) if not k]
    if dropped:
        log("   left out (moved by the exporter): %s" % ", ".join(dropped[:12]))
    return s, R, t


# ---------------------------------------------------------------- the weapon in PMX terms

def build_weapon(L, skeleton, renderers, log):
    """New bones / vertices / faces / per-renderer face counts in PMX terms."""
    world = rest_worlds(skeleton)
    s, R, t = game_to_pmx(L, skeleton, world, log)
    names = [b["name"] for b in skeleton]
    index = {n: i for i, n in enumerate(names)}
    have = {}
    for k, b in enumerate(L["bones"]):
        have.setdefault(b["name_e"] or b["name"], k)
        have.setdefault(b["name"], k)
    world_of = {n: world[i] for n, i in index.items()}
    missing = sorted({b for r in renderers for b in r["bones"] if b not in index})
    if missing:
        raise ValueError("weapon bones not in the HD skeleton: %s" % missing)

    # the bones to add: every weapon bone and its ancestors up to one the PMX has (or the prefab's Root)
    new, parent_of = [], {}
    for r in renderers:
        for b in r["bones"]:
            chain = []
            i = index[b]
            while i >= 0 and names[i] not in have and skeleton[i]["parent"] >= 0 and names[i] != "Root":
                chain.append(i)
                i = skeleton[i]["parent"]
            for j in chain:
                if names[j] not in parent_of:
                    p = skeleton[j]["parent"]
                    parent_of[names[j]] = names[p] if names[p] in have or p in chain else None
            new.extend(names[j] for j in chain if names[j] not in new)

    def depth(n):
        d, i = 0, index[n]
        while skeleton[i]["parent"] >= 0:
            d, i = d + 1, skeleton[i]["parent"]
        return d
    new.sort(key=lambda n: (depth(n), index[n]))
    base = len(L["bones"])
    pmx_index = dict(have)
    pmx_index.update({n: base + k for k, n in enumerate(new)})

    def to_pmx(p):
        return s * (R @ p) + t
    heads = {n: to_pmx(world_of[n][:3, 3]) for n in new}

    verts, faces, counts, owned = [], [], [], {n: [] for n in new}
    flip = None
    for r in renderers:
        V, N = skin_at_rest(r, world_of)
        P = V @ (s * R).T + t
        Nn = N @ R.T
        first = L["nv"] + len(verts)
        for i in range(len(P)):
            w = [(pmx_index[r["bones"][slot]], wt) for slot, wt in r["skin"][i]]
            verts.append((P[i], Nn[i], (r["uv"][i, 0], 1.0 - r["uv"][i, 1]), w))
            main_bone = r["bones"][r["skin"][i][0][0]]
            if main_bone in owned:
                owned[main_bone].append(P[i])
        tri = np.array(r["tris"], dtype=np.int64)
        if flip is None:
            mine = winding_sign(P, Nn, tri)
            flip = mine != winding_sign(L["pos"], L["nrm"], L["faces"])
        if flip:
            tri = tri[:, [0, 2, 1]]
        faces.extend((tri + first).tolist())
        counts.append((r["name"], len(tri) * 3))
        log("   %s: %d vertices, %d triangles, bones %s" % (r["name"], len(P), len(tri), ", ".join(r["bones"])))
    log("   faces %s to match the PMX's winding" % ("flipped" if flip else "kept"))

    bones = []
    for n in new:
        parent = parent_of[n]
        kids = [m for m in new if parent_of[m] == n]
        if len(kids) == 1:
            tail = ("bone", pmx_index[kids[0]])
        elif owned[n]:                       # towards its farthest vertex: the blade
            pts = np.array(owned[n])
            tail = ("offset", (pts[np.argmax(np.linalg.norm(pts - heads[n], axis=1))] - heads[n]) * 0.9)
        elif parent in heads:                # the end of a chain: one more link
            tail = ("offset", heads[n] - heads[parent])
        else:
            tail = ("offset", np.array([0.0, 1.0, 0.0]))
        bones.append({"name": n, "head": heads[n], "parent": pmx_index[parent] if parent else 0, "tail": tail})
    roots = [n for n in new if parent_of[n] is None]
    return {"bones": bones, "verts": verts, "faces": faces, "counts": counts, "roots": roots, "heads": heads,
            "pmx_index": pmx_index, "first_vertex": L["nv"], "transform": (s, R, t)}


def appended(data, L, W, texture_rel, model_mat):
    """The PMX bytes with the weapon's vertices, faces, texture, materials and bones appended."""
    E, bsz, vsz, tsz = L["enc"], L["bsz"], L["vsz"], L["tsz"]
    limits = {1: 127, 2: 32767, 4: 2 ** 31 - 1}
    if L["nv"] + len(W["verts"]) > {1: 255, 2: 65535, 4: 2 ** 31 - 1}[vsz]:
        raise ValueError("vertex index size %d cannot hold %d vertices" % (vsz, L["nv"] + len(W["verts"])))
    if len(L["bones"]) + len(W["bones"]) > limits[bsz]:
        raise ValueError("bone index size %d cannot hold more bones" % bsz)
    if len(L["textures"]) + 1 > limits[tsz] or len(L["materials"]) + len(W["counts"]) > limits[L["msz"]]:
        raise ValueError("texture / material index size too small")
    bfmt, tfmt, ffmt = psm.index_fmt(bsz), psm.index_fmt(tsz), psm.index_fmt(vsz, True)
    vb = bytearray()
    for p, n, uv, w in W["verts"]:
        vb += struct.pack("<3f3f2f", *p, *n, *uv)
        vb += b"\0" * (16 * L["add_uv"])
        if len(w) == 1:
            vb += struct.pack("<B" + bfmt, 0, w[0][0])
        elif len(w) == 2:
            vb += struct.pack("<B2" + bfmt + "f", 1, w[0][0], w[1][0], w[0][1])
        else:
            w = (w + [(0, 0.0)] * 4)[:4]
            vb += struct.pack("<B4" + bfmt + "4f", 2, *[b for b, _x in w], *[x for _b, x in w])
        vb += struct.pack("<f", 1.0)
    fb = struct.pack("<%d%s" % (3 * len(W["faces"]), ffmt), *[i for f in W["faces"] for i in f])
    tex_index = len(L["textures"])
    tb = text(texture_rel, E)
    mb = bytearray()
    for name, count in W["counts"]:
        m = model_mat
        mb += text(name, E) + text("", E)
        mb += struct.pack("<4f3ff3fB4ff", *m["diffuse"], *m["specular"], m["power"], *m["ambient"], m["flags"],
                          *m["edge"], m["edge_size"])
        mb += struct.pack("<" + tfmt + tfmt + "BB", tex_index, -1, 0, m["shared"])
        mb += struct.pack("<B", m["toon"]) if m["shared"] else struct.pack("<" + tfmt, m["toon"])
        mb += text("", E) + struct.pack("<i", count)
    bb = bytearray()
    for b in W["bones"]:
        flags = 0x001E | (0x0001 if b["tail"][0] == "bone" else 0)
        bb += text(b["name"], E) + text("", E) + struct.pack("<3f" + bfmt + "iH", *b["head"], b["parent"], 0, flags)
        bb += struct.pack("<" + bfmt, b["tail"][1]) if b["tail"][0] == "bone" else struct.pack("<3f", *b["tail"][1])
    out = bytearray(data[:L["v_at"]])
    out += struct.pack("<i", L["nv"] + len(W["verts"])) + data[L["v_at"] + 4:L["v_end"]] + vb
    out += struct.pack("<i", L["nf"] + 3 * len(W["faces"])) + data[L["f_at"] + 4:L["f_end"]] + fb
    out += struct.pack("<i", len(L["textures"]) + 1) + data[L["t_at"] + 4:L["t_end"]] + tb
    out += struct.pack("<i", len(L["materials"]) + len(W["counts"])) + data[L["m_at"] + 4:L["m_end"]] + mb
    out += struct.pack("<i", len(L["bones"]) + len(W["bones"])) + data[L["b_at"] + 4:L["b_end"]] + bb
    out += data[L["b_end"]:]
    return bytes(out)


def add_bone_frame(data, name, name_e, bone_indices):
    """One more display frame listing ``bone_indices``."""
    info = psm.parse(data)
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    at, end = info["frames_at"], info["frames_end"]
    n = struct.unpack_from("<i", data, at)[0]
    bfmt = psm.index_fmt(info["bsz"])
    frame = text(name, enc) + text(name_e, enc) + struct.pack("<Bi", 0, len(bone_indices))
    frame += b"".join(struct.pack("<B" + bfmt, 0, i) for i in bone_indices)
    return data[:at] + struct.pack("<i", n + 1) + data[at + 4:end] + frame + data[end:]


def with_weapon(data, skeleton, renderers, texture_rel, log):
    L = layout(data)
    W = build_weapon(L, skeleton, renderers, log)
    body = next((m for m in L["materials"] if "body" in m["name"]), L["materials"][0])
    out = appended(data, L, W, texture_rel, body)
    # 武器非表示: every weapon vertex onto its bones' heads
    heads_pmx = {W["pmx_index"][n]: h for n, h in W["heads"].items()}
    offsets = []
    for k, (p, _n, _uv, w) in enumerate(W["verts"]):
        d = np.zeros(3)
        for b, x in w:
            d += x * (heads_pmx.get(b, p) - p)
        offsets.append((W["first_vertex"] + k, tuple(d)))
    info = psm.parse(out)
    out, mi, in_face = psm.append_vertex_morph(out, info, MORPH, offsets, MORPH_TAG + ",".join(W["roots"]))
    first = len(L["bones"])
    out = add_bone_frame(out, FRAME, FRAME_E, list(range(first, first + len(W["bones"]))))
    L2 = layout(out)
    assert L2["nv"] == L["nv"] + len(W["verts"]) and len(L2["bones"]) == len(L["bones"]) + len(W["bones"])
    log("   + %d bones (%s), %d vertices, %d triangles, %d material(s), morph %s (index %d%s), frame %s"
        % (len(W["bones"]), ", ".join(b["name"] for b in W["bones"]), len(W["verts"]), len(W["faces"]),
           len(W["counts"]), MORPH, mi, ", in 表情" if in_face else "", FRAME))
    return out


# ---------------------------------------------------------------- texture

def weapon_texture(cid, albedo, log):
    """The PMX diffuse of the material whose albedo is ``albedo`` (hq_material_data.py, shared cache):
    (path of <material>__pmx_diffuse.png, material name)."""
    cmd = [sys.executable, os.path.join(HERE, "hq_material_data.py"), cid, "--out", HQ_CACHE, "--albedos", albedo]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    data = json.load(open(os.path.join(HQ_CACHE, "%s.json" % cid), encoding="utf-8"))
    for name, mdef in data["materials"].items():
        if mdef["textures"].get("_BaseMap", {}).get("texture", "").lower() == albedo.lower() and \
                name in data.get("exports", {}):
            path = os.path.join(HQ_CACHE, data["exports"][name]["pmx"])
            if os.path.isfile(path):
                log("texture: %s (material %s, %s)" % (path, name, mdef["bundle"]))
                return path, name
    raise SystemExit("no PMX diffuse for albedo %s (hq_material_data.py exit %d)\n%s"
                     % (albedo, res.returncode, (res.stdout + res.stderr)[-1500:]))


# ---------------------------------------------------------------- main

def has_weapon(path):
    info = psm.parse(open(path, "rb").read())
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    return MORPH in {n.decode(enc) for n in info["morph_names"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="outfit id, e.g. a08")
    ap.add_argument("--stem", help="model stem (default pc_<id>_hd)")
    ap.add_argument("--pmx", help="one PMX to change (default: the archive's, its _bustB, the D: source)")
    ap.add_argument("--out", help="with --pmx: write here instead of in place")
    ap.add_argument("--albedo", help="the weapon material's albedo (default <weapon>_rgbx_Albedo)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stem = args.stem or "pc_%s_hd" % args.id

    def log(line):
        print(line, flush=True)

    found = bundles(args.id)
    if not found["showcase"] or not found["battle"]:
        sys.exit("need both bundles of %s: %s" % (args.id, found))
    skeleton = dec.read_skeleton(UnityPy.load(found["showcase"]))
    renderers = weapon_renderers(UnityPy.load(found["battle"]))
    if not renderers:
        sys.exit("no skinned wp_* renderer in %s" % found["battle"])
    log("weapon renderers in %s: %s" % (os.path.basename(found["battle"]), ", ".join(r["name"] for r in renderers)))
    prefix = os.path.commonprefix([r["name"] for r in renderers]).rstrip("_")
    albedo = args.albedo or "%s_rgbx_Albedo" % prefix
    tex_src, mat_name = weapon_texture(args.id, albedo, log)
    tex_rel = "textures\\%s" % os.path.basename(tex_src)

    if args.pmx:
        targets = [(args.pmx, args.out or args.pmx)]
    else:
        pmx, _character = find_pmx(stem)
        if not pmx:
            sys.exit("no archive PMX for %s (pass --pmx)" % stem)
        targets = [(p, p) for p in pmx_copies(pmx)]
    stamp = datetime.date.today().strftime("%Y%m%d")
    for src, dst in targets:
        log("PMX %s" % src)
        if has_weapon(src):
            log("   already has %s - left alone" % MORPH)
            continue
        data = open(src, "rb").read()
        out = with_weapon(data, skeleton, renderers, tex_rel, log)
        if args.dry_run:
            continue
        tex_dir = os.path.join(os.path.dirname(dst), "textures")
        os.makedirs(tex_dir, exist_ok=True)
        shutil.copyfile(tex_src, os.path.join(tex_dir, os.path.basename(tex_src)))
        if os.path.abspath(dst) == os.path.abspath(src):
            norm = os.path.normcase(os.path.abspath(src))
            if norm.startswith(os.path.normcase(os.path.abspath(ARCHIVE)) + os.sep):
                rel = os.path.relpath(src, ARCHIVE)
            else:
                rel = os.path.join("_roe_exports", os.path.relpath(src, ROE_EXPORTS))
            backup = os.path.join(ARCHIVE, "_meta", "pmx_old", "weapon_%s" % stamp, rel)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            if not os.path.exists(backup):
                shutil.copy2(src, backup)
            log("   original kept in %s" % backup)
        tmp = dst + ".weapon.tmp"
        open(tmp, "wb").write(out)
        os.replace(tmp, dst)
        log("   written %s (%d -> %d bytes), texture %s" % (dst, len(data), len(out), tex_rel))


if __name__ == "__main__":
    main()
