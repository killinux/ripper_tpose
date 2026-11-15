# Skyrim SE outfit NIFs (BodySlide ShapeData / meshes) -> one PMX with MMD-named bones, via PyNifly's pyn library
# (plain CPython, NiflyDLL.dll).  Skyrim: Z up, +Y forward, left = -X, ~1.33 cm per unit; scaled so the hip joint
# (NPC L Thigh) and ankle (NPC L Foot) heights land on the target's.  python nif_to_pmx.py --out X.pmx --tex PNGDIR
#   [--hip-y 99.3 --ankle-y 16] [--skip-shape regex] <a.nif> <b.nif> ...
import argparse
import os
import re
import shutil
import sys

import numpy as np

NIFLY = r"E:\tools\mod_importers\io_scene_nifly"
sys.path.insert(0, NIFLY)
from pyn import pynifly  # noqa: E402

pynifly.NifFile.Load(os.path.join(NIFLY, "NiflyDLL.dll"))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pmxlib as L  # noqa: E402

pmx = L.pmx
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--tex", required=True)
ap.add_argument("--hip-y", type=float, default=99.3)
ap.add_argument("--ankle-y", type=float, default=16.0)
ap.add_argument("--skip-shape", default="")
ap.add_argument("--name", default="Skyrim outfit")
a = ap.parse_args()

NPC = {"NPC Root [Root]": "全ての親", "NPC COM [COM ]": "センター", "NPC Pelvis [Pelv]": "下半身", "NPC Spine [Spn0]": "上半身",
       "NPC Spine1 [Spn1]": "上半身2", "NPC Spine2 [Spn2]": "上半身3", "NPC Neck [Neck]": "首", "NPC Head [Head]": "頭",
       "NPC L Clavicle [LClv]": "左肩", "NPC L UpperArm [LUar]": "左腕", "NPC L Forearm [LLar]": "左ひじ", "NPC L Hand [LHnd]": "左手首",
       "NPC R Clavicle [RClv]": "右肩", "NPC R UpperArm [RUar]": "右腕", "NPC R Forearm [RLar]": "右ひじ", "NPC R Hand [RHnd]": "右手首",
       "NPC L UpperarmTwist1 [LUt1]": "左腕捩", "NPC L ForearmTwist1 [LLt1]": "左手捩",
       "NPC R UpperarmTwist1 [RUt1]": "右腕捩", "NPC R ForearmTwist1 [RLt1]": "右手捩",
       "NPC L Thigh [LThg]": "左足", "NPC L Calf [LClf]": "左ひざ", "NPC L Foot [Lft ]": "左足首", "NPC L Toe0 [LToe]": "左つま先",
       "NPC R Thigh [RThg]": "右足", "NPC R Calf [RClf]": "右ひざ", "NPC R Foot [Rft ]": "右足首", "NPC R Toe0 [RToe]": "右つま先",
       "NPC L Finger00 [LF00]": "左親指０", "NPC L Finger01 [LF01]": "左親指１", "NPC L Finger02 [LF02]": "左親指２",
       "NPC L Finger10 [LF10]": "左人指１", "NPC L Finger11 [LF11]": "左人指２", "NPC L Finger12 [LF12]": "左人指３",
       "NPC L Finger20 [LF20]": "左中指１", "NPC L Finger21 [LF21]": "左中指２", "NPC L Finger22 [LF22]": "左中指３",
       "NPC L Finger30 [LF30]": "左薬指１", "NPC L Finger31 [LF31]": "左薬指２", "NPC L Finger32 [LF32]": "左薬指３",
       "NPC L Finger40 [LF40]": "左小指１", "NPC L Finger41 [LF41]": "左小指２", "NPC L Finger42 [LF42]": "左小指３",
       "NPC R Finger00 [RF00]": "右親指０", "NPC R Finger01 [RF01]": "右親指１", "NPC R Finger02 [RF02]": "右親指２",
       "NPC R Finger10 [RF10]": "右人指１", "NPC R Finger11 [RF11]": "右人指２", "NPC R Finger12 [RF12]": "右人指３",
       "NPC R Finger20 [RF20]": "右中指１", "NPC R Finger21 [RF21]": "右中指２", "NPC R Finger22 [RF22]": "右中指３",
       "NPC R Finger30 [RF30]": "右薬指１", "NPC R Finger31 [RF31]": "右薬指２", "NPC R Finger32 [RF32]": "右薬指３",
       "NPC R Finger40 [RF40]": "右小指１", "NPC R Finger41 [RF41]": "右小指２", "NPC R Finger42 [RF42]": "右小指３",
       "L Breast01": "左胸", "R Breast01": "右胸"}
# parents for the MMD-named bones we create (the ShapeData nifs flatten the tree under Scene Root)
PARENT = {"センター": "全ての親", "下半身": "センター", "上半身": "センター", "上半身2": "上半身", "上半身3": "上半身2", "首": "上半身3",
          "頭": "首", "左肩": "上半身3", "左腕": "左肩", "左腕捩": "左腕", "左ひじ": "左腕", "左手捩": "左ひじ", "左手首": "左ひじ",
          "右肩": "上半身3", "右腕": "右肩", "右腕捩": "右腕", "右ひじ": "右腕", "右手捩": "右ひじ", "右手首": "右ひじ",
          "左足": "下半身", "左ひざ": "左足", "左足首": "左ひざ", "左つま先": "左足首", "右足": "下半身", "右ひざ": "右足",
          "右足首": "右ひざ", "右つま先": "右足首", "左胸": "上半身3", "右胸": "上半身3"}
for side, s_ in (("左", "L"), ("右", "R")):
    for f, n in (("親指", 0), ("人指", 1), ("中指", 2), ("薬指", 3), ("小指", 4)):
        names = ["%s%s０" % (side, f), "%s%s１" % (side, f), "%s%s２" % (side, f)] if f == "親指" else \
                ["%s%s１" % (side, f), "%s%s２" % (side, f), "%s%s３" % (side, f)]
        prev = side + "手首"
        for nm in names:
            PARENT[nm] = prev
            prev = nm

nifs = []
for f in a.files:
    n = pynifly.NifFile(f)
    nifs.append((f, n))
# skeleton: union of node globals (Skyrim units)
node_pos = {}
for f, n in nifs:
    for name, node in n.nodes.items():
        if name in node_pos or name == "Scene Root":
            continue
        try:
            t = node.global_transform.translation
        except Exception:
            t = node.transform.translation
        node_pos[name] = np.array([t[0], t[1], t[2]], float)
hip = node_pos.get("NPC L Thigh [LThg]")
ank = node_pos.get("NPC L Foot [Lft ]")
if hip is None or ank is None:
    raise SystemExit("need NPC L Thigh and NPC L Foot nodes for the scale (give a legs/boots nif first)")
s = (a.hip_y - a.ankle_y) / (hip[2] - ank[2])
y0 = a.ankle_y - ank[2] * s
print("scale %.4f y0 %.1f  (skyrim hip z %.2f ankle z %.2f)" % (s, y0, hip[2], ank[2]))


def xf(p):                                        # skyrim (x right?, y forward, z up), left = -x  ->  PMX
    return np.array([-p[0] * s, p[2] * s + y0, -p[1] * s])


M = pmx.Model()
M.name = M.name_e = a.name
M.comment = "converted from Skyrim SE NIF by nif_to_pmx.py (PyNifly)\r\n" + "\r\n".join(os.path.basename(f) for f in a.files)
bone_index = {}


def add_bone(mmd_name, pos_pmx, parent_name):
    if mmd_name in bone_index:
        return bone_index[mmd_name]
    if parent_name and parent_name not in bone_index:
        # parent position: known node or the child's position
        pp = None
        for nname, mm in NPC.items():
            if mm == parent_name and nname in node_pos:
                pp = xf(node_pos[nname])
        if pp is None:
            pp = pos_pmx
        add_bone(parent_name, pp, PARENT.get(parent_name))
    b = pmx.Bone()
    b.name = b.name_e = mmd_name
    b.location = [float(x) for x in np.asarray(pos_pmx) / L.UNIT_CM]
    b.parent = bone_index[parent_name] if parent_name else -1
    M.bones.append(b)
    bone_index[mmd_name] = len(M.bones) - 1
    return bone_index[mmd_name]


add_bone("全ての親", np.array([0.0, 0.0, 0.0]), None)
add_bone("センター", xf(node_pos.get("NPC COM [COM ]", hip * np.array([0, 1, 1]) * 0.6)) if "NPC COM [COM ]" in node_pos else np.array([0.0, 43.0, 0.0]), "全ての親")
for nname in sorted(node_pos):
    mmd = NPC.get(nname)
    if mmd:
        add_bone(mmd, xf(node_pos[nname]), PARENT.get(mmd, "センター"))


def sk_name(nname):
    return "sk_" + re.sub(r"[\[\]\s]", "", nname)[:14]


# other nodes (twist / breast / butt helpers, the outfit's SMP chains): the flattened ShapeData tree does not say
# whose child they are.  Until 11-14 they all hung on センター, which another model keeps elsewhere (ROE a08: 56 cm
# lower), so an outfit moved by bone names dropped every vertex weighted to them.  Now: the previous node of a numbered
# chain (cocoa03 -> cocoa02), else the named deform bone whose segment passes nearest.
used_nodes = set()                    # nodes some shape is skinned to (the rest: shape / collision / SMP helper nodes)
for f_, n_ in nifs:
    for sh_ in n_.shapes:
        try:
            used_nodes.update(sh_.bone_weights.keys())
        except Exception:
            pass
named_pos = {mmd: np.array(M.bones[i].location) * L.UNIT_CM for mmd, i in bone_index.items()}
segs = [(par, named_pos[par], named_pos[ch]) for ch, par in PARENT.items()
        if ch in bone_index and par in bone_index and par not in ("全ての親", "センター")]
segs += [(mmd, p, p) for mmd, p in named_pos.items() if mmd not in ("全ての親", "センター")]


def seg_owner(p):
    best, bd = "下半身", 1e9
    for owner, a_, b_ in segs:
        ab = b_ - a_
        t = float(np.clip(np.dot(p - a_, ab) / np.dot(ab, ab), 0.0, 1.0)) if ab.any() else 0.0
        d = float(np.linalg.norm(a_ + t * ab - p))
        if d < bd:
            best, bd = owner, d
    return best


NUM = re.compile(r"^(.*?)(\d+)(\D*)$")
unknown_set = {n for n in node_pos if n not in NPC}


def chain_parent(nname):
    m = NUM.match(nname)
    if not m or int(m.group(2)) == 0:
        return None
    prev = "%s%0*d%s" % (m.group(1), len(m.group(2)), int(m.group(2)) - 1, m.group(3))
    return prev if prev in unknown_set else None


def chain_depth(nname):
    d, c = 0, chain_parent(nname)
    while c is not None and d < 64:
        d, c = d + 1, chain_parent(c)
    return d


unknown = set()
for nname in unknown_set & used_nodes:  # a skinned node and the numbered chain above it
    while nname is not None and nname not in unknown:
        unknown.add(nname)
        nname = chain_parent(nname)
for nname in sorted(unknown, key=lambda n: (chain_depth(n), n)):
    cp = chain_parent(nname)
    add_bone(sk_name(nname), xf(node_pos[nname]), sk_name(cp) if cp else seg_owner(xf(node_pos[nname])))
print("bones:", len(M.bones))

out_dir = os.path.dirname(os.path.abspath(a.out))
os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
skip = re.compile(a.skip_shape) if a.skip_shape else None
total_faces = 0
for f, n in nifs:
    stem = re.sub(r"[^\w\-]+", "_", os.path.splitext(os.path.basename(f))[0].replace("CBBE SE - [COCO] Mulan ", "")).strip("_")
    for sh in n.shapes:
        if skip and skip.search(sh.name):
            print("  skip", stem, sh.name)
            continue
        V = np.array(sh.verts, float)
        N = np.array(sh.normals, float) if len(sh.normals) == len(V) else None
        UV = np.array(sh.uvs, float) if len(sh.uvs) == len(V) else np.zeros((len(V), 2))
        # shape transform (usually identity for skinned shapes)
        try:
            st = sh.transform
            off = np.array([st.translation[0], st.translation[1], st.translation[2]], float)
        except Exception:
            off = np.zeros(3)
        wv = [[] for _ in range(len(V))]
        bw_all = sh.bone_weights
        for bname, lst in bw_all.items():
            mmd = NPC.get(bname, "sk_" + re.sub(r"[\[\]\s]", "", bname)[:14])
            if mmd not in bone_index:
                add_bone(mmd, xf(node_pos[bname]) if bname in node_pos else np.array([0.0, 100.0, 0.0]), "センター")
            bi = bone_index[mmd]
            for vi, w in lst:
                if w > 0:
                    wv[vi].append((bi, float(w)))
        base = len(M.vertices)
        for i in range(len(V)):
            v = pmx.Vertex()
            v.co = [float(x) for x in xf(V[i] + off) / L.UNIT_CM]
            if N is not None:
                nn = N[i]
                v.normal = [float(-nn[0]), float(nn[2]), float(-nn[1])]
            else:
                v.normal = [0.0, 1.0, 0.0]
            v.uv = [float(UV[i][0]), float(UV[i][1])]
            v.additional_uvs = []
            ws = sorted(wv[i], key=lambda t: -t[1])[:4]
            tot = sum(w for _, w in ws) or 1.0
            ws = [(b, w / tot) for b, w in ws]
            bw = pmx.BoneWeight()
            if len(ws) == 0:
                bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF1, [bone_index.get("下半身", bone_index["センター"])], []
            elif len(ws) == 1:
                bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF1, [ws[0][0]], []
            elif len(ws) == 2:
                bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF2, [ws[0][0], ws[1][0]], [ws[0][1]]
            else:
                while len(ws) < 4:
                    ws.append((ws[0][0], 0.0))
                bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF4, [b for b, _ in ws], [w for _, w in ws]
            v.weight = bw
            v.edge_scale = 1.0
            M.vertices.append(v)
        faces = []
        for tri in sh.tris:
            i0, i1, i2 = (base + int(t) for t in tri)
            p0, p1, p2 = (np.array(M.vertices[t].co) for t in (i0, i1, i2))
            gn = np.cross(p1 - p0, p2 - p0)
            vn = np.array(M.vertices[i0].normal) + np.array(M.vertices[i1].normal) + np.array(M.vertices[i2].normal)
            faces.append([i0, i1, i2] if np.dot(gn, vn) <= 0 else [i0, i2, i1])
        # diffuse texture
        texs = list(sh.textures.values()) if hasattr(sh.textures, "values") else list(sh.textures)
        diffuse = next((t for t in texs if t and not re.search(r"_n\.dds$|_m\.dds$|_e\.dds$|_s\.dds$|cubemap", t, re.I)), None)
        ti = -1
        chosen = None
        if diffuse:
            png = os.path.splitext(os.path.basename(diffuse))[0] + ".png"
            src = os.path.join(a.tex, png)
            if os.path.isfile(src):
                dst = os.path.join(out_dir, "textures", png)
                if not os.path.isfile(dst):
                    shutil.copyfile(src, dst)
                ti = L.add_texture(M, os.path.abspath(dst))
                chosen = png
        mat_name = "%s_%s" % (stem, re.sub(r"[^\w\-]+", "_", sh.name))[:60]
        L.new_material(M, mat_name, mat_name, ti, faces, diffuse=(1, 1, 1, 1), specular=(0.3, 0.3, 0.3), shininess=10,
                       ambient=(0.5, 0.5, 0.5), edge=False, toon=0, comment="skyrim %s / %s" % (stem, sh.name))
        total_faces += len(faces)
        print("  %-26s shape %-14s verts %5d faces %5d bones %2d tex %s" % (stem, sh.name, len(V), len(faces), len(bw_all), chosen))
print("bone tails:", L.connect_tails(M))
pmx.save(a.out, M, add_uv_count=0)
print("wrote", a.out, "vertices", len(M.vertices), "faces", total_faces, "materials", len(M.materials), "bones", len(M.bones))
print("NIF_PMX_DONE")
