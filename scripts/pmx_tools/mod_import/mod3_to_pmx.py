# Monster Hunter World player equipment (.mod3 + .mrl3 + converted .png textures) -> one PMX with an MMD-named skeleton.
# Runs under Blender's Python (the mod3 parser needs mathutils):
#   blender -b --factory-startup --python mod3_to_pmx.py -- --out <out.pmx> --tex <png dir> [--skip-mat Ch_Skin]
#            [--shoulder-y 141.1 --ankle-y 16] <a.mod3> <b.mod3> ...
# Bones are named by the MHW "bone function" (player skeleton), laid out as a standard MMD tree (2026-11-14):
#   0 root -> 全ての親 (moved to the floor), a new センター (no weights), 13 hips (legs hang on it) -> 下半身,
#   1 spine root -> 上半身 (beside 下半身 under センター), 2 chest (clavicles hang on it) -> 上半身2, 3 neck base -> 首,
#   4 -> 頭; 5-8 left shoulder/arm/elbow/wrist, 9-12 right, 81 / 83 forearm twist -> 左手捩 / 右手捩, 14-17 / 18-21
#   legs, 31-46 / 48-63 fingers; others keep "mhw_fNNN".  Helper bones sitting on a joint (root twists, deltoid /
#   elbow / knee / ankle / hip helpers, 0 itself) hand their weights to the MMD bone of that joint (WEIGHT_REMAP), so
#   nothing is weighted to a control bone.  (Until 11-14 13 was named センター, 2 上半身, 3 上半身2, 4 首: a garment
#   moved to another PMX by bone names then dropped to that model's センター and its chest / crown sat 5-27 cm low.)
# MHW is Y up, Z forward, left = +X, roughly cm with the pelvis at the origin: scaled so the shoulder / ankle heights
# land on the target's, Z flipped (PMX faces -Z), faces re-wound from the vertex normals.
import argparse
import os
import re
import shutil
import sys

import numpy as np

R = r"E:\tools\mod_importers\mod3_src\Mod3-MHW-Importer-master"
for sub in ("mod3", "common", "mrl3"):
    sys.path.insert(0, os.path.join(R, sub))
import FileLike as FL  # noqa: E402
import Mod3  # noqa: E402
import Mrl3  # noqa: E402
from mathutils import Matrix  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pmxlib as L  # noqa: E402

pmx = L.pmx
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--tex", required=True, help="folder with the converted .png textures")
ap.add_argument("--skip-mat", default="Ch_Skin")
ap.add_argument("--shoulder-y", type=float, default=141.1, help="target: height of the shoulder joint (cm)")
ap.add_argument("--ankle-y", type=float, default=16.0, help="target: height of the ankle joint (cm)")
ap.add_argument("--name", default="MHW equipment")
a = ap.parse_args(argv)

FUNC_NAMES = {0: "全ての親", 13: "下半身", 1: "上半身", 2: "上半身2", 3: "首", 4: "頭", "center": "センター",
              5: "左肩", 6: "左腕", 7: "左ひじ", 8: "左手首", 9: "右肩", 10: "右腕", 11: "右ひじ", 12: "右手首",
              81: "左手捩", 83: "右手捩",
              14: "左足", 15: "左ひざ", 16: "左足首", 17: "左つま先", 18: "右足", 19: "右ひざ", 20: "右足首", 21: "右つま先",
              31: "左親指０", 32: "左親指１", 33: "左親指２", 34: "左人指１", 35: "左人指２", 36: "左人指３",
              37: "左中指１", 38: "左中指２", 39: "左中指３", 41: "左薬指１", 42: "左薬指２", 43: "左薬指３",
              44: "左小指１", 45: "左小指２", 46: "左小指３",
              48: "右親指０", 49: "右親指１", 50: "右親指２", 51: "右人指１", 52: "右人指２", 53: "右人指３",
              54: "右中指１", 55: "右中指２", 56: "右中指３", 58: "右薬指１", 59: "右薬指２", 60: "右薬指３",
              61: "右小指１", 62: "右小指２", 63: "右小指３"}


def lmat(bone):
    return Matrix([[bone["LMatCol%d" % c][r] for c in range(4)] for r in range(4)])


def world_positions(arm):
    world = {}

    def w(i):
        if i in world:
            return world[i]
        b = arm[i]
        m = lmat(b)
        pid = b["parentId"]
        world[i] = m if pid == 255 or pid >= len(arm) else w(pid) @ m
        return world[i]

    return [np.array(w(i).to_translation()) for i in range(len(arm))]


# --- pass 1: skeleton (union over files, by bone function)
models = []
for f in a.files:
    m = Mod3.Mod3()
    m.marshall(FL.FileLike(open(f, "rb").read()))
    m.filterLOD()
    models.append((f, m))
func_pos, func_parent = {}, {}


def key_of(stem, fn):
    """standard player bones (< 100) are shared between the equipment files; each file's own cloth / helper bones
    (>= 100, the ids are reused by every piece for different chains) stay private"""
    return fn if fn < 100 else (stem, fn)


file_keys = {}
for f, m in models:
    stem = os.path.splitext(os.path.basename(f))[0]
    arm = m.prepareArmature()
    pos = world_positions(arm)
    keys = []
    for i, b in enumerate(arm):
        fn = b["CustomProperties"]["boneFunction"]
        k = key_of(stem, fn)
        keys.append(k)
        if k in func_pos:
            continue
        func_pos[k] = pos[i]
        pid = b["parentId"]
        func_parent[k] = key_of(stem, arm[pid]["CustomProperties"]["boneFunction"]) if pid != 255 and pid < len(arm) else None
    file_keys[stem] = keys
print("skeleton bones:", len(func_pos), "unnamed standard:", sorted(k for k in func_pos if isinstance(k, int) and k not in FUNC_NAMES))
# scale from the shoulder (func 6) and ankle (func 16) heights
ys, ya = func_pos[6][1], func_pos[16][1]
s = (a.shoulder_y - a.ankle_y) / (ys - ya)
y0 = a.ankle_y - ya * s
print("scale %.4f, y offset %.1f (MHW shoulder y %.1f ankle y %.1f)" % (s, y0, ys, ya))


def xf(p):
    return np.array([p[0] * s, p[1] * s + y0, -p[2] * s])


# --- MMD layout (see the header).  Helpers on a joint give their weights to that joint's MMD bone; the ones >= 100
# (per-file keys) are spine / root helpers every piece carries.
WEIGHT_REMAP = {0: 13, 30: 8, 47: 12, 64: 13, 66: 13, 67: 13, 69: 13, 70: 6, 72: 10, 71: 7, 73: 11, 80: 6, 82: 10,
                74: 14, 76: 18, 75: 15, 77: 19, 84: 16, 85: 20}
ANYFILE_REMAP = {247: 2, 248: 2, 249: 13, 250: 13, 251: 13, 252: 13, 253: 13}


def remap_key(k):
    to = ANYFILE_REMAP.get(k[1]) if isinstance(k, tuple) else WEIGHT_REMAP.get(k)
    return to if to is not None and to in func_pos else k


pmx_pos = {k: xf(p) for k, p in func_pos.items()}
if 0 in func_pos:
    pmx_pos[0] = np.zeros(3)                                     # 全ての親 on the floor
if 13 in func_pos:
    for k, p in list(func_parent.items()):                       # nothing but センター hangs on 全ての親
        if p == 0 and k != 13:
            func_parent[k] = 13
    func_pos["center"] = func_pos[13]
    pmx_pos["center"] = np.array([0.0, 0.41 * pmx_pos[13][1], 0.0])
    func_parent["center"] = 0 if 0 in func_pos else None
    func_parent[13] = "center"
    if 1 in func_pos:
        func_parent[1] = "center"                                # 上半身 beside 下半身, not under it

M = pmx.Model()
M.name = M.name_e = a.name
M.comment = "converted from Monster Hunter World mod3 by mod3_to_pmx.py\r\n" + "\r\n".join(os.path.basename(f) for f in a.files)
M.header = None
# bones in parent-first order
order = []
seen = set()


def add_order(fn):
    if fn in seen:
        return
    p = func_parent.get(fn)
    if p is not None and p in func_pos:
        add_order(p)
    seen.add(fn)
    order.append(fn)


def sort_key(k):
    if isinstance(k, str):
        return (0, 1, 1, -1 if k == "center" else 999, "")
    if isinstance(k, int):
        return (0, k != 0, k != 13, k, "")
    return (1, 0, 0, k[1], k[0])


for fn in sorted(func_pos, key=sort_key):
    add_order(fn)
bone_index = {}
for fn in order:
    b = pmx.Bone()
    if isinstance(fn, str):
        b.name = FUNC_NAMES[fn]
    else:
        b.name = FUNC_NAMES.get(fn, "mhw_f%03d" % fn) if isinstance(fn, int) else "mhw_%s_f%03d" % (fn[0][:8], fn[1])
    b.name_e = b.name
    b.location = [float(x) for x in pmx_pos[fn] / L.UNIT_CM]
    p = func_parent.get(fn)
    b.parent = bone_index[p] if p is not None and p in bone_index else -1
    M.bones.append(b)
    bone_index[fn] = len(M.bones) - 1
print("bones written:", len(M.bones))

# --- pass 2: meshes
tex_dir = a.tex
out_dir = os.path.dirname(os.path.abspath(a.out))
os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
skip = re.compile(a.skip_mat) if a.skip_mat else None
n_faces_total = 0
for f, m in models:
    arm = m.prepareArmature()
    fn_of = [b["CustomProperties"]["boneFunction"] for b in arm]
    stem = os.path.splitext(os.path.basename(f))[0]
    mrl = None
    mrl_path = os.path.splitext(f)[0] + ".mrl3"
    if os.path.isfile(mrl_path):
        try:
            mrl = Mrl3.MRL3()
            mrl.marshall(open(mrl_path, "rb"))
        except Exception as e:
            print("mrl3 failed for", stem, e)
            mrl = None
    parts = m.prepareMeshparts(weightSplit=False)
    for k, part in enumerate(parts):
        mat = part["properties"]["material"].split("\\x00")[0].split("\x00")[0]
        mat = re.sub(r"[^\w\-]", "", mat)
        if skip and skip.search(mat):
            print("  skip", stem, mat)
            continue
        V = np.array(part["vertices"], float)
        N = np.array(part["normals"], float) if part.get("normals") is not None and len(part["normals"]) == len(V) else None
        UV = np.array(part["uvs"][0], float) if part["uvs"] else np.zeros((len(V), 2))
        # weights per vertex
        wv = [[] for _ in range(len(V))]
        keys = file_keys[stem]
        for gix, group in part["weightGroups"].items():
            bk = remap_key(keys[gix]) if gix < len(keys) else None
            if bk is None or bk not in bone_index:
                continue
            bi = bone_index[bk]
            for vi, w in group:
                wv[vi].append((bi, float(w)))
        base = len(M.vertices)
        for i in range(len(V)):
            v = pmx.Vertex()
            v.co = [float(x) for x in xf(V[i]) / L.UNIT_CM]
            if N is not None:
                n = N[i]
                v.normal = [float(n[0]), float(n[1]), float(-n[2])]
            else:
                v.normal = [0.0, 1.0, 0.0]
            v.uv = [float(UV[i][0]), float(UV[i][1])]
            v.additional_uvs = []
            merged = {}
            for bi_, w_ in wv[i]:                       # remapped helpers can land on a bone the vertex already has
                merged[bi_] = merged.get(bi_, 0.0) + w_
            ws = sorted(((b_, w_) for b_, w_ in merged.items() if w_ > 0), key=lambda t: -t[1])[:4]
            tot = sum(w for _, w in ws) or 1.0
            ws = [(b, w / tot) for b, w in ws]
            bw = pmx.BoneWeight()
            if len(ws) == 0:
                bw.type, bw.bones, bw.weights = pmx.BoneWeight.BDEF1, [bone_index.get(13, 0)], []
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
        for tri in part["faces"]:
            if len(tri) != 3:
                continue
            i0, i1, i2 = (base + t for t in tri)
            p0, p1, p2 = (np.array(M.vertices[t].co) for t in (i0, i1, i2))
            gn = np.cross(p1 - p0, p2 - p0)
            vn = np.array(M.vertices[i0].normal) + np.array(M.vertices[i1].normal) + np.array(M.vertices[i2].normal)
            # PMX stores clockwise-from-the-front: cross(v1-v0, v2-v0) points AGAINST the vertex normal
            faces.append([i0, i1, i2] if np.dot(gn, vn) <= 0 else [i0, i2, i1])
        # texture: mrl3 albedo of this material, else <stem>_BM.png
        tex_name = None
        if mrl is not None:
            try:
                tp = mrl[part["properties"]["material"].split("\x00")[0]]
                if tp:
                    tex_name = os.path.basename(str(tp)) + ".png"
            except Exception:
                tex_name = None
        cands = ([tex_name] if tex_name else []) + [stem + "_BM.png", stem[:-4] + "0010_BML.png", stem + "_BML.png"]
        chosen = next((c for c in cands if c and os.path.isfile(os.path.join(tex_dir, c))), None)
        if chosen is None:
            print("  no texture for", stem, mat, "tried", cands[:2])
            ti = -1
        else:
            dst = os.path.join(out_dir, "textures", chosen)
            if not os.path.isfile(dst):
                shutil.copyfile(os.path.join(tex_dir, chosen), dst)
            ti = L.add_texture(M, os.path.abspath(dst))
        L.new_material(M, "%s_%s_%d" % (stem, mat, k), "%s_%s_%d" % (stem, mat, k), ti, faces, diffuse=(1, 1, 1, 1),
                       specular=(0.3, 0.3, 0.3), shininess=10, ambient=(0.5, 0.5, 0.5), edge=False, toon=0,
                       comment="mhw %s material %s block %s" % (stem, mat, part["properties"].get("blockLabel")))
        n_faces_total += len(faces)
        print("  part %-22s mat %-24s verts %5d faces %5d tex %s" % (stem, mat, len(V), len(faces), chosen))
M.textures = M.textures or []
# the pmx module needs a header: build via save's defaults
try:
    M.header = pmx.Header(M)
except Exception:
    pass
print("bone tails:", L.connect_tails(M))
pmx.save(a.out, M, add_uv_count=0)
print("wrote", a.out, "vertices", len(M.vertices), "faces", n_faces_total, "materials", len(M.materials), "bones", len(M.bones))
print("MOD3_PMX_DONE")
