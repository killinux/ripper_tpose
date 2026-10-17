"""The game's own elbow in a finished Vindictus PMX: its corrective joints become two helper bones per arm.

Why: the MetaHuman body keeps the elbow round with corrective joints (lowerarm_correctiveRoot at half the bend,
lowerarm_in / out / fwd / bck sliding up to 9 cm, bicep / tricep bulging), driven at runtime by the PoseDriver nodes
of ABP_PCF_Corrective from the pose assets BaseBody_PCF/Poses/pcf_lowerarm_l/r_pose (9 poses, the elbow bent 3.7 to
148.7 deg).  export_pmx.py folds those joints into the limb bones (MMD cannot drive them), so the elbow is plain
skinning: linear in Blender (mmd_tools without its SDEF driver - what you see after importing), SDEF in MMD.  Linear
skinning pinches the elbow into a V when it bends (6 cm off the game's shape at 149 deg on PCF_005) and wrings it
like a sweet wrapper when the motion twists the forearm through ひじ (MMD motions do: the gesture dance up to 87 deg,
the ring shrinks 29 %).  SDEF stays round but opens holes along the lace sleeve's edge, where the game weights the
sleeve and the skin under it differently.

What: per arm, two hidden bones that MMD and mmd_tools both drive with plain 回転付与 (rotation grant):
  左ひじ補1  ひじ's whole rotation (ratio 1) about a point 4 units (32 cm) up the arm line - a vertex sharing in it
             slides as the elbow bends, the way the game's correctives slide the flesh;
  左ひじ補2  half of ひじ's rotation about the elbow joint - the in-between step that keeps the ring round in a
             bend and in a twist.
Every vertex within ZONE of the elbow (sleeve layers included) gets new weights (upper arm, forearm, the helpers; at
most 4 bones) and a rest position, fitted so linear skinning reproduces the game: the XPS (the game's bind mesh and
weights) skinned with the pose asset's corrective transforms at all 9 angles; an elbow twist (ひじ about the arm line)
must not shrink the ring; an upper-arm twist (腕捩) must share out as before.  The old weights' upper-arm and forearm
parts keep their own twist bones (腕捩1-3 / 手捩1-3 shares), counted against the 4-bone limit; SDEF goes from these
vertices (BDEF now, the same in MMD and Blender).  Each vertex's weights are pulled towards its neighbours'
(WEIGHT_SMOOTH): fitted vertex by vertex alone, a thin line of crease vertices went wholly onto the hidden helpers
(1.0 next to 0.4), which in Blender's weight paint of ひじ - or of any bone you can pose - looks like a piece of the
elbow with no weight.  With the pull the helpers top out at 0.7 and every vertex keeps at least 0.3 on bones you
can pose, a band as broad and soft as the game's own corrective weights (at most 0.6), for the same fit.

Why these two: a far helper with a ratio below 1 matches the game a little closer (0.7 instead of 1.3 cm at 149 deg)
but mmd_tools grants by scaling Euler angles, not by MMD's slerp; with bend and twist together its rotation is
off by degrees and 32 cm of lever turn that into 2 cm lumps in Blender.  Ratio 1 copies the rotation exactly, and the
half-ratio helper turns about the joint itself, so Blender and MMD differ by at most 1.0 cm (mean 0.02 cm) in the
gesture dance's worst keys.  Both pivots lie on the arm line, so a twist through ひじ turns them exactly like the
forearm (no sweep); a bend in another plane turns their correction with it.

PCF_005 (2026-10-11, scratch elbow2\\, arms raised to 40 deg, weight pull 3): against the game's corrective elbow
at 89 / 117 / 149 deg, max 0.6 / 0.6 / 1.4 cm (linear skinning before: 2.8 / 4.4 / 6.1, SDEF: 2.2 / 3.4 / 4.6); ひじ
twist 90 deg shrinks the ring at most 14 % (was 29 %); 腕捩 80 deg moves the zone 0.07 cm on average from before (max 0.9), 手捩 80 deg max 0.14 cm; rest
positions move at most 0.7 cm (the game's own straight-arm shape); the gesture dance's elbow keys (up to 147 deg
with 84 deg twist) stay within 1.05 x of the plain bend's change.

    python pmx_elbow.py <id>.pmx <out>.pmx --xps <id>.xps          # the XPS export_pmx.py was given
    python pmx_elbow.py ... --report r.json --helpers "1:-4,0.5:0" --game-data <dir>

Arms raised before the conversion (export_pmx.py --arm-angle, limbs.raise_arms) are recognised from the PMX's upper
arm against the game skeleton; the matching, the game's shapes and the hinge are turned the same way.  Fingers
straightened before it (limbs.straighten_fingers) are recognised from 左人指１-３ lying on a line; the matching
straightens the XPS the same way.

Write <out> next to <id>.pmx: mmd_tools' writer makes texture paths relative to the output.  A PMX that already has
the comment line (MARK) is refused.  The game data (pose assets + skeleton, CUE4Parse JSON, ~1.4 MB) is not in the
repo: --game-data, default E:\\game_export\\Vindictus\\_meta\\elbow; how to export it is in README.md (手臂权重).
Needs numpy and the XNALaraMesh add-on's XPS reader (Blender 3.6 add-ons folder); runs in plain Python, ~30 s.
"""
import argparse
import importlib
import itertools
import json
import math
import os
import sys
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)

GAME_DATA = r"E:\game_export\Vindictus\_meta\elbow"
SKELETON = "SK_PCF_BaseBody01_Skeleton.json"
POSE_ASSET = "pcf_lowerarm_%s_pose.json"
XNALARA = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "3.6", "scripts", "addons",
                       "XNALaraMesh-master")
MARK = "elbow: the game's corrective elbow as helper bones"
DEFAULT_HELPERS = "1:-4,0.5:0"         # ratio:offset (PMX units along the arm line from the elbow, - = shoulder)
ZONE = 2.5                             # PMX units (20 cm): the game moves vertices non-rigidly up to 18.8 cm out
FADE_FROM = 2.0                        # rest-position changes fade out between 16 and 20 cm
ETWIST = (45.0, -45.0, 90.0, -90.0)    # ひじ turned about the arm line: the ring must not shrink
ETWIST_WEIGHT = 2.0
UTWIST = (60.0, -60.0)                 # 腕捩 turned: the upper arm shares it out as before
SMOOTH = True                          # the rest-position change smoothed over the mesh (3 x 0.5 Laplacian)
WEIGHT_SMOOTH = 3.0                    # pull towards the neighbours' weights (PMX units^2 per unit of weight^2):
                                       # PCF_005 0 / 1 / 3 / 10 -> mean off the game 0.114 / 0.115 / 0.117 /
                                       # 0.120 cm, largest weight step between neighbours 0.47 / 0.22 / 0.18 / 0.15
WEIGHT_SMOOTH_ITER = 8
CORRECTIVE_TRACKS = ("lowerarm_{s}", "lowerarm_correctiveRoot_{s}", "lowerarm_in_{s}", "lowerarm_out_{s}",
                     "lowerarm_fwd_{s}", "lowerarm_bck_{s}", "upperarm_bicep_{s}", "upperarm_tricep_{s}")
# Blender2XPS's names for the UE bones it renames (the rest keep their name or get an unused_ prefix)
XPS_TO_UE = {"root ground": "root", "root hips": "pelvis", "spine lower": "spine_01", "spine middle": "spine_03",
             "spine upper": "spine_05", "head neck lower": "neck_01", "head neck upper": "head"}
for _side, _s in (("left", "l"), ("right", "r")):
    XPS_TO_UE.update({"arm %s shoulder 1" % _side: "clavicle_" + _s, "arm %s shoulder 2" % _side: "upperarm_" + _s,
                      "arm %s elbow" % _side: "lowerarm_" + _s, "arm %s wrist" % _side: "hand_" + _s,
                      "leg %s thigh" % _side: "thigh_" + _s, "leg %s knee" % _side: "calf_" + _s,
                      "leg %s ankle" % _side: "foot_" + _s, "leg %s toes" % _side: "ball_" + _s})
    for _n, _f in (("1", "thumb"), ("2", "index"), ("3", "middle"), ("4", "ring"), ("5", "pinky")):
        for _j, _part in (("a", "01"), ("b", "02"), ("c", "03")):
            XPS_TO_UE["arm %s finger %s%s" % (_side, _n, _j)] = "%s_%s_%s" % (_f, _part, _s)
XPS_ARMS = (("arm left shoulder 2", "arm left elbow", "arm left wrist"),
            ("arm right shoulder 2", "arm right elbow", "arm right wrist"))
# limbs.XPS_FINGERS / HALF (limbs.py needs Blender): each finger from the knuckle out
XPS_FINGERS = tuple(
    chain for _side, _s in (("left", "l"), ("right", "r")) for chain in
    [("arm %s finger 1a" % _side, "arm %s finger 1b" % _side, "arm %s finger 1c" % _side)]
    + [("unused_%s_metacarpal_%s" % (_f, _s),) + tuple("arm %s finger %s%s" % (_side, _n, _j) for _j in "abc")
       for _n, _f in (("2", "index"), ("3", "middle"), ("4", "ring"), ("5", "pinky"))])
HALF = "_half_"


# -- small maths -----------------------------------------------------------------------------------------------------
def rotation(axis, angle):
    """3x3 rotation by angle (radians) about axis"""
    axis = np.asarray(axis, dtype=float)
    x, y, z = axis / np.linalg.norm(axis)
    c, s = math.cos(angle), math.sin(angle)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def rot_about(P, axis, deg, centre):
    return centre + (P - centre) @ rotation(axis, math.radians(deg)).T


def quat_matrix(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    s = 2.0 / n if n > 0 else 0.0
    return np.array([[1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
                     [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
                     [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)]])


def trs(q, t, s=(1.0, 1.0, 1.0)):
    m = np.eye(4)
    m[:3, :3] = quat_matrix(q) @ np.diag(s)
    m[:3, 3] = t
    return m


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def rotation_between(a, b):
    a = a / max(np.linalg.norm(a), 1e-12)
    b = b / max(np.linalg.norm(b), 1e-12)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9 or c <= -1 + 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1.0 + c)


# -- the game: skeleton, corrective poses, its skinning in PMX space ----------------------------------------------------
def ue_to_pmx(v):
    """UE centimetres -> the PMX export_pmx.py writes (x12.5 on the XPS metres, z flipped, centred like the PMX)"""
    return np.stack([v[..., 0] / 8.0, v[..., 2] / 8.0, -v[..., 1] / 8.0 - 0.3015], axis=-1)


def xps_to_ue(co):
    return np.stack([100 * co[:, 0], 100 * co[:, 2], 100 * co[:, 1]], axis=1)


def xps_to_pmx(co):
    return ue_to_pmx(xps_to_ue(co))


def _json(path):
    return json.load(open(path, encoding="utf-8-sig"))


class Game:
    """The UE reference skeleton and the corrective pose assets; skins XPS meshes (the game's bind mesh + weights)."""

    def __init__(self, xps, data_dir=GAME_DATA):
        sk = next(e for e in _json(os.path.join(data_dir, SKELETON)) if e["Type"] == "Skeleton")["ReferenceSkeleton"]
        self.names = [b["Name"] for b in sk["FinalRefBoneInfo"]]
        self.parents = [b["ParentIndex"] for b in sk["FinalRefBoneInfo"]]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.bind_local = []
        for tr in sk["FinalRefBonePose"]:
            r, p, s = tr["Rotation"], tr["Translation"], tr["Scale3D"]
            self.bind_local.append(trs((r["X"], r["Y"], r["Z"], r["W"]), (p["X"], p["Y"], p["Z"]),
                                       (s["X"], s["Y"], s["Z"])))
        self.G_bind = self.fk(self.bind_local)
        self.G_bind_inv = [np.linalg.inv(g) for g in self.G_bind]
        self.data_dir = data_dir
        self.xps = xps
        self.xps_ue = np.array([self.index.get(XPS_TO_UE.get(n, n[7:] if n.startswith("unused_") else n), -1)
                                for n, _p, _c in xps["bones"]])

    def fk(self, local):
        g = [None] * len(local)
        for i, p in enumerate(self.parents):
            g[i] = local[i] if p < 0 else g[p] @ local[i]
        return g

    def poses(self, s):
        """[(bend degrees, {track: (q, t, s)})] of pcf_lowerarm_<s>_pose, sorted by the bend"""
        pc = _json(os.path.join(self.data_dir, POSE_ASSET % s))[0]["Properties"]["PoseContainer"]
        names = [p["DisplayName"] for p in pc["PoseNames"]]
        tracks = pc["Tracks"]
        poses = {n: {} for n in names}
        for t, infl in enumerate(pc["TrackPoseInfluenceIndices"]):
            for i in infl["Influences"]:
                tr = pc["Poses"][i["PoseIndex"]]["LocalSpacePose"][i["BoneTransformIndex"]]
                r, p, sc = tr["Rotation"], tr["Translation"], tr["Scale3D"]
                poses[names[i["PoseIndex"]]][tracks[t]] = ((r["X"], r["Y"], r["Z"], r["W"]), (p["X"], p["Y"], p["Z"]),
                                                           (sc["X"], sc["Y"], sc["Z"]))
        out = []
        for n in names:
            if "lowerarm_" + s not in poses[n]:
                continue
            q = poses[n]["lowerarm_" + s][0]
            angle = math.degrees(2 * math.atan2(math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2), abs(q[3])))
            keep = {tr.format(s=s) for tr in CORRECTIVE_TRACKS}
            out.append((angle, {k: v for k, v in poses[n].items() if k in keep}))
        return sorted(out, key=lambda e: e[0])

    def skin_mats(self, overrides):
        local = list(self.bind_local)
        for name, tr in overrides.items():
            local[self.index[name]] = trs(*tr)
        return np.array([g @ gi for g, gi in zip(self.fk(local), self.G_bind_inv)])

    def deform(self, k, K):
        """XPS mesh k skinned with the UE skinning matrices K -> PMX space"""
        m = self.xps["meshes"][k]
        co = xps_to_ue(m["co"])
        hom = np.concatenate([co, np.ones((len(co), 1))], axis=1)
        ue = self.xps_ue[m["bones"]]
        out = np.zeros_like(co)
        total = np.zeros(len(co))
        for j in range(4):
            w = m["weights"][:, j]
            M = np.where((ue[:, j] >= 0)[:, None, None], K[np.maximum(ue[:, j], 0)], np.eye(4)[None])
            out += w[:, None] * np.einsum("nij,nj->ni", M, hom)[:, :3]
            total += w
        return ue_to_pmx(out / np.where(total > 0, total, 1)[:, None])

    def hinge(self, s):
        """the lowerarm's bend axis (its parent's local Z) and the elbow joint, PMX space"""
        a = self.G_bind[self.index["upperarm_" + s]][:3, :3] @ np.array([0.0, 0.0, 1.0])
        axis = np.array([a[0], a[2], -a[1]])
        return axis / np.linalg.norm(axis), ue_to_pmx(self.G_bind[self.index["lowerarm_" + s]][:3, 3])


# -- the XPS export_pmx.py started from ---------------------------------------------------------------------------------
def read_xps(path):
    """bones [(name, parent, co)], meshes [{name, co, uv, bones, weights}] - with XNALaraMesh's own binary reader
    (its ASCII reader imports mathutils, stubbed here)"""
    if "mathutils" not in sys.modules:
        stub = types.ModuleType("mathutils")
        stub.Vector = lambda v: tuple(v)
        sys.modules["mathutils"] = stub
    if "xnalara_reader" not in sys.modules:
        pkg = types.ModuleType("xnalara_reader")
        pkg.__path__ = [XNALARA]
        sys.modules["xnalara_reader"] = pkg
    stdout = sys.stdout
    sys.stdout = open(os.devnull, "w")                  # the reader prints every step
    try:
        data = importlib.import_module("xnalara_reader.read_bin_xps").readXpsModel(path)
    finally:
        sys.stdout.close()
        sys.stdout = stdout
    bones = [(b.name, b.parentId, tuple(b.co)) for b in data.bones]
    meshes = []
    for m in data.meshes:
        n = len(m.vertices)
        bi = np.zeros((n, 4), dtype=np.int64)
        bw = np.zeros((n, 4))
        for i, v in enumerate(m.vertices):
            for j, w in enumerate(v.boneWeights[:4]):
                bi[i, j], bw[i, j] = w.id, w.weight
        meshes.append({"name": m.name, "co": np.array([v.co for v in m.vertices], dtype=float),
                       "uv": np.array([v.uv[0] for v in m.vertices], dtype=float), "bones": bi, "weights": bw})
    return {"bones": bones, "meshes": meshes}


def _subtree_mask(kids, n, root):
    below = np.zeros(n, dtype=bool)
    stack = [root]
    while stack:
        b = stack.pop()
        below[b] = True
        stack.extend(kids.get(b, []))
    return below


def straightened(xps, fingers=False):
    """the XPS positions after export_pmx.py's limb steps before the arm raise: with `fingers`, limbs.straighten_fingers
    (joint by joint from the knuckle, each vertex by its share beyond the joint, the half bones' weight counting
    half), then limbs.straighten_forearms (each vertex turned about the elbow by its forearm share of the rest bend)"""
    names = [b[0] for b in xps["bones"]]
    parents = [b[1] for b in xps["bones"]]
    kids = {}
    for i, p in enumerate(parents):
        kids.setdefault(p, []).append(i)
    out = [m["co"].copy() for m in xps["meshes"]]
    bone_co = np.array([b[2] for b in xps["bones"]], dtype=float)
    for level in ((1, 2) if fingers else ()):
        turns = []
        for chain in XPS_FINGERS:
            if level + 1 >= len(chain) or any(n not in names for n in chain[level - 1:level + 2]):
                continue
            ib, ij, ia = (names.index(n) for n in chain[level - 1:level + 2])
            joint = bone_co[ij].copy()
            along = (joint - bone_co[ib]) / np.linalg.norm(joint - bone_co[ib])
            ahead = (bone_co[ia] - joint) / np.linalg.norm(bone_co[ia] - joint)
            angle = math.acos(np.clip(along @ ahead, -1, 1))
            if angle < math.radians(0.5):
                continue
            factor = _subtree_mask(kids, len(names), ij).astype(float)
            for h in kids.get(ij, []):
                if HALF in names[h]:
                    factor[_subtree_mask(kids, len(names), h)] = 0.5
            turns.append((joint, np.cross(ahead, along), angle, factor))
        for joint, axis, angle, factor in turns:
            for k, m in enumerate(xps["meshes"]):
                total = m["weights"].sum(1)
                share = (m["weights"] * factor[m["bones"]]).sum(1)
                for i in np.where(share > 0)[0]:
                    out[k][i] = joint + rotation(axis, angle * share[i] / total[i]) @ (out[k][i] - joint)
            sel = factor > 0
            bone_co[sel] = joint + (bone_co[sel] - joint) @ rotation(axis, angle).T
    plans = []
    for up, el, wr in XPS_ARMS:
        iu, ie, iw = names.index(up), names.index(el), names.index(wr)
        co = [np.array(xps["bones"][i][2]) for i in (iu, ie, iw)]
        upper = (co[1] - co[0]) / np.linalg.norm(co[1] - co[0])
        fore = (co[2] - co[1]) / np.linalg.norm(co[2] - co[1])
        below = np.zeros(len(names), dtype=bool)
        stack = [ie]
        while stack:
            b = stack.pop()
            below[b] = True
            stack.extend(kids.get(b, []))
        plans.append((co[1], np.cross(fore, upper), math.acos(np.clip(upper @ fore, -1, 1)), below))
    for k, m in enumerate(xps["meshes"]):
        co = out[k]
        for elbow, axis, angle, below in plans:
            total = m["weights"].sum(1)
            share = (m["weights"] * below[m["bones"]]).sum(1)
            for i in np.where(share > 0)[0]:
                co[i] = elbow + rotation(axis, angle * share[i] / total[i]) @ (co[i] - elbow)
    return out


def fingers_straight(model, max_deg=2.0):
    """were the fingers straightened before the conversion (limbs.straighten_fingers)?  The game binds the index
    finger's middle joint 11.7 deg bent; straightened, 左人指１-２-３ lie on a line"""
    idx = {b.name: i for i, b in enumerate(model.bones)}
    names = ("左人指１", "左人指２", "左人指３")
    if any(n not in idx for n in names):
        return False
    a, b, c = (np.array(model.bones[idx[n]].location, dtype=float) for n in names)
    u, v = (b - a) / np.linalg.norm(b - a), (c - b) / np.linalg.norm(c - b)
    return math.degrees(math.acos(np.clip(u @ v, -1, 1))) < max_deg


class ArmRaise:
    """How this PMX's arms were raised from the game's (limbs.raise_arms, export_pmx.py --arm-angle): per
    side the turn about the shoulder taking the game's upper arm onto the PMX's, and each XPS vertex's share of
    weight on the arm - apply() puts game-space positions where the raise put them."""

    def __init__(self, model, xps, game):
        names = [b.name for b in model.bones]
        xnames = [b[0] for b in xps["bones"]]
        kids = {}
        for i, (_n, p, _c) in enumerate(xps["bones"]):
            kids.setdefault(p, []).append(i)
        self.sides = {}
        for side, jp, (xup, _xel, _xwr) in zip("lr", ("左", "右"), XPS_ARMS):
            S0 = ue_to_pmx(game.G_bind[game.index["upperarm_" + side]][:3, 3])
            E0 = ue_to_pmx(game.G_bind[game.index["lowerarm_" + side]][:3, 3])
            S = np.array(model.bones[names.index(jp + "腕")].location, dtype=float)
            E = np.array(model.bones[names.index(jp + "ひじ")].location, dtype=float)
            if np.linalg.norm(S - S0) > 0.01:
                raise SystemExit("%s腕 is not at the game's shoulder (%.3f units off)" % (jp, np.linalg.norm(S - S0)))
            d0, d1 = (E0 - S0) / np.linalg.norm(E0 - S0), (E - S) / np.linalg.norm(E - S)
            angle = math.acos(float(np.clip(d0 @ d1, -1, 1)))
            if math.degrees(angle) < 0.05:
                continue
            axis = np.cross(d0, d1)
            axis /= np.linalg.norm(axis)
            below = np.zeros(len(xnames), dtype=bool)
            stack = [xnames.index(xup)]
            while stack:
                b = stack.pop()
                below[b] = True
                stack.extend(kids.get(b, []))
            shares = [(m["weights"] * below[m["bones"]]).sum(1) / np.maximum(m["weights"].sum(1), 1e-12)
                      for m in xps["meshes"]]
            self.sides[side] = (S, axis, angle, shares)

    def degrees(self, side):
        return math.degrees(self.sides[side][2]) if side in self.sides else 0.0

    def apply(self, k, P):
        """PMX-space positions of XPS mesh k, game pose -> raised"""
        P = np.array(P, dtype=float, copy=True)
        for S, axis, angle, shares in self.sides.values():
            s = np.round(shares[k], 6)
            for v in np.unique(s[s > 0]):
                sel = s == v
                P[sel] = S + (P[sel] - S) @ rotation(axis, angle * v).T
        return P

    def turn_point(self, side, p):
        if side not in self.sides:
            return np.array(p, dtype=float)
        S, axis, angle, _shares = self.sides[side]
        return S + rotation(axis, angle) @ (np.array(p, dtype=float) - S)

    def turn_vector(self, side, v):
        if side not in self.sides:
            return np.array(v, dtype=float)
        _S, axis, angle, _shares = self.sides[side]
        return rotation(axis, angle) @ np.array(v, dtype=float)


# -- the PMX ------------------------------------------------------------------------------------------------------------
def material_vertices(model):
    out, start = [], 0
    for mat in model.materials:
        n = mat.vertex_count // 3
        out.append((mat.name, np.unique(np.array(model.faces[start:start + n], dtype=np.int64).ravel())))
        start += n
    return out


def match_vertices(model, xps, raise_=None, fingers=False):
    """PMX vertex -> (XPS mesh, vertex): the same material and UV, the nearest straightened (and raised) position"""
    co = np.array([v.co for v in model.vertices], dtype=float)
    uv = np.array([v.uv for v in model.vertices], dtype=float)
    st = straightened(xps, fingers)
    names = [m["name"] for m in xps["meshes"]]
    mesh_of = np.full(len(co), -1)
    vert_of = np.full(len(co), -1)
    dist = np.full(len(co), np.inf)
    for mat_name, idx in material_vertices(model):
        if mat_name not in names:
            continue
        k = names.index(mat_name)
        xuv, xco = xps["meshes"][k]["uv"], xps_to_pmx(st[k])
        if raise_ is not None:
            xco = raise_.apply(k, xco)
        table = {}
        for j, key in enumerate(map(tuple, np.round(xuv * 1e6).astype(np.int64))):
            table.setdefault(key, []).append(j)
        for i, key in zip(idx, map(tuple, np.round(uv[idx] * 1e6).astype(np.int64))):
            c = table.get(key)
            if c:
                d = np.linalg.norm(xco[c] - co[i], axis=1)
                j = int(np.argmin(d))
                mesh_of[i], vert_of[i], dist[i] = k, c[j], d[j]
    return mesh_of, vert_of, dist


def pmx_weights(model, pmx):
    n = len(model.vertices)
    bi = np.full((n, 4), -1, dtype=np.int64)
    bw = np.zeros((n, 4))
    sdef = np.zeros(n, dtype=bool)
    for i, v in enumerate(model.vertices):
        w = v.weight
        if w.type == pmx.BoneWeight.BDEF1:
            bi[i, 0], bw[i, 0] = w.bones[0], 1.0
        elif w.type == pmx.BoneWeight.BDEF2:
            bi[i, :2], bw[i, :2] = w.bones[:2], (w.weights[0], 1 - w.weights[0])
        elif w.type == pmx.BoneWeight.BDEF4:
            bi[i], bw[i] = w.bones, w.weights
        elif w.type == pmx.BoneWeight.SDEF:
            bi[i, :2], bw[i, :2] = w.bones[:2], (w.weights.weight, 1 - w.weights.weight)
            sdef[i] = True
    bw[bi < 0] = 0
    return bi, bw, sdef


def subtree(model, root):
    kids = {}
    for i, b in enumerate(model.bones):
        kids.setdefault(b.parent, []).append(i)
    out, stack = set(), [root]
    while stack:
        b = stack.pop()
        out.add(b)
        stack.extend(kids.get(b, []))
    return out


def twist_ratios(model, twist_bone):
    """how much of a 腕捩 turn each bone takes: its subtree 1, the bones granted from it (腕捩1-3) their ratio"""
    r = np.zeros(len(model.bones))
    r[list(subtree(model, twist_bone))] = 1.0
    for i, b in enumerate(model.bones):
        if b.hasAdditionalRotate and b.additionalTransform and b.additionalTransform[0] == twist_bone:
            r[list(subtree(model, i))] = b.additionalTransform[1]
    return r


def turned(model, co, bi, bw, idx, bone, axis, deg):
    """vertices idx with `bone` turned deg about axis through its head (its subtree follows, bones granted from it
    turn their share about their own heads), linear skinning"""
    J = np.array(model.bones[bone].location)
    R = rotation(axis, math.radians(deg))
    X = {b: (R, J - R @ J) for b in subtree(model, bone)}
    for i, b in enumerate(model.bones):
        if b.hasAdditionalRotate and b.additionalTransform and b.additionalTransform[0] == bone and i not in X:
            Rh = rotation(axis, math.radians(deg * b.additionalTransform[1]))
            Q = np.array(b.location)
            for c in subtree(model, i):
                X[c] = (Rh, Q - Rh @ Q)
    ident = (np.eye(3), np.zeros(3))
    out = np.zeros((len(idx), 3))
    for j in range(4):
        Rs = np.stack([X.get(int(b), ident)[0] for b in bi[idx, j]])
        ts = np.stack([X.get(int(b), ident)[1] for b in bi[idx, j]])
        out += bw[idx, j:j + 1] * (np.einsum("nij,nj->ni", Rs, co[idx]) + ts)
    return out / np.maximum(bw[idx].sum(1, keepdims=True), 1e-12)


# -- the fit --------------------------------------------------------------------------------------------------------------
def candidates(P, pose, joint, helpers, ugroup):
    """(B, N, 3): where each candidate bone puts every vertex in one pose.  0 = upper arm (in an upper-arm twist each
    of the vertex's own old upper-arm bones turns by its ratio), 1 = forearm (ひじ), 2.. = helpers (ratio k of ひじ's
    turn about pivot Q; children of 腕捩, so a 腕捩 turn takes them whole)"""
    out = []
    if pose["kind"] in ("bend", "etwist"):
        a, d = pose["axis"], pose["deg"]
        out.append(P.copy())
        out.append(rot_about(P, a, d, joint))
        for k, Q in helpers:
            out.append(rot_about(P, a, d * k, Q))
    else:
        a, d, c = pose["axis"], pose["deg"], pose["centre"]
        ratios, shares = ugroup
        U = np.zeros_like(P)
        for g in range(ratios.shape[1]):
            for r in np.unique(ratios[:, g]):
                sel = (ratios[:, g] == r) & (shares[:, g] > 0)
                if sel.any():
                    U[sel] += shares[sel, g:g + 1] * rot_about(P[sel], a, d * r, c)
        out.append(U)
        out.append(rot_about(P, a, d, c))
        for _k, _Q in helpers:
            out.append(rot_about(P, a, d, c))
    return np.array(out)


def solve_weights(X, T, costs, max_bones=4, prior=None, lam=0.0):
    """per vertex: min sum_k |sum_b w_b X[k,b] - T[k]|^2 (+ lam |w - prior|^2), w >= 0, sum w = 1, the bones the
    used candidates take (costs) <= max_bones; every subset solved with the sum by substitution, the best feasible
    one kept"""
    K, B, N, _ = X.shape
    A = X.transpose(2, 0, 3, 1).reshape(N, K * 3, B)
    y = T.transpose(1, 0, 2).reshape(N, K * 3)
    if prior is not None and lam > 0:
        A = np.concatenate([A, np.broadcast_to(math.sqrt(lam) * np.eye(B), (N, B, B))], axis=1)
        y = np.concatenate([y, math.sqrt(lam) * prior], axis=1)
    best_w = np.zeros((N, B))
    best_e = np.full(N, np.inf)
    for r in range(1, max_bones + 1):
        for s in itertools.combinations(range(B), r):
            s = list(s)
            fits = costs[:, s].sum(1) <= max_bones
            if not fits.any():
                continue
            As = A[:, :, s]
            if len(s) == 1:
                w = np.ones((N, 1))
            else:
                base = As[:, :, -1]
                D = As[:, :, :-1] - base[:, :, None]
                DtD = np.einsum("nki,nkj->nij", D, D) + 1e-12 * np.eye(len(s) - 1)
                z = np.linalg.solve(DtD, np.einsum("nki,nk->ni", D, y - base)[..., None])[..., 0]
                w = np.concatenate([z, 1 - z.sum(1, keepdims=True)], axis=1)
            e = ((np.einsum("nkb,nb->nk", As, w) - y) ** 2).sum(1)
            better = fits & (w >= -1e-9).all(1) & (e < best_e)
            if better.any():
                best_e[better] = e[better]
                full = np.zeros((better.sum(), B))
                full[:, s] = np.clip(w[better], 0, None)
                best_w[better] = full / full.sum(1, keepdims=True)
    return best_w


def _etwist_targets(P, poses, T, joint, share):
    """each vertex turned by its own effective ratio: the target only asks the ring not to shrink"""
    for i, p in enumerate(poses):
        if p["kind"] == "etwist":
            for v in np.unique(np.round(share, 3)):
                sel = np.round(share, 3) == v
                T[i][sel] = rot_about(P[sel], p["axis"], p["deg"] * v, joint)


def fit(P, poses, targets, wts, joint, helpers, ugroup, costs, share0, rest_fade, rounds=3, smooth=None,
        neighbours=None, lam=0.0, iterations=None):
    """weights and rest positions in turn; the rest positions come from the bend / elbow-twist poses (one transform
    per bone), smoothed over the mesh (`smooth`, on the change) and damped by rest_fade towards the zone's border;
    with `neighbours` (the mean of the neighbours' weights) each vertex's weights are also pulled towards its
    neighbours' (lam, a few Jacobi steps), so the weights change over the mesh as smoothly as the game's"""
    iterations = WEIGHT_SMOOTH_ITER if iterations is None else iterations
    ks = np.array([0.0, 1.0] + [k for k, _Q in helpers])
    sw = np.sqrt(np.asarray(wts, dtype=float))
    share = share0.copy()
    T = targets.copy()
    Pc = P.copy()
    shared = [i for i, p in enumerate(poses) if p["kind"] in ("bend", "etwist")]
    for _round in range(rounds + 1):
        _etwist_targets(Pc, poses, T, joint, share)
        X = np.array([candidates(Pc, p, joint, helpers, ugroup) for p in poses])
        W = solve_weights(X * sw[:, None, None, None], T * sw[:, None, None], costs)
        if neighbours is not None and lam > 0:
            for _step in range(iterations):
                W = solve_weights(X * sw[:, None, None, None], T * sw[:, None, None], costs, prior=neighbours(W),
                                  lam=lam)
        share = np.clip(W @ ks, 0, 1)
        if _round == rounds:
            break
        R = np.zeros((len(shared), len(ks), 3, 3))
        t = np.zeros((len(shared), len(ks), 3))
        for kk, i in enumerate(shared):
            a, d = poses[i]["axis"], poses[i]["deg"]
            R[kk, 0] = np.eye(3)
            for b, (k, Q) in enumerate([(1.0, joint)] + list(helpers), start=1):
                M = rotation(a, math.radians(d * k))
                R[kk, b], t[kk, b] = M, Q - M @ Q
        wb = sw[shared]
        A = np.einsum("nb,kbij->nkij", W, R) * wb[None, :, None, None]
        rhs = (T[shared].transpose(1, 0, 2) - np.einsum("nb,kbi->nki", W, t)) * wb[None, :, None]
        Pn = np.linalg.solve(np.einsum("nkji,nkjl->nil", A, A), np.einsum("nkji,nkj->ni", A, rhs)[..., None])[..., 0]
        change = Pn - P if smooth is None else smooth(Pn - P)
        Pc = P + rest_fade[:, None] * change
    pred = np.einsum("kbni,nb->kni", X, W)
    return W, Pc, np.linalg.norm(pred - T, axis=2), share


def _merged_mesh(co, faces, zone):
    """vertices at one position (UV seams) as one: each vertex's merged index, the merged edges, how many merged
    vertices, which of them lie in the zone and how many zone vertices each one stands for"""
    _u, rep = np.unique(np.round(co, 6), axis=0, return_inverse=True)
    rep = rep.ravel()
    f = rep[np.asarray(faces, dtype=np.int64)]
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e = np.unique(np.sort(e[e[:, 0] != e[:, 1]], axis=1), axis=0)
    m = rep.max() + 1
    in_zone = np.zeros(m, dtype=bool)
    in_zone[rep[zone]] = True
    count = np.bincount(rep[zone], minlength=m).astype(float)
    return rep, e, m, in_zone, count


def neighbour_mean(co, faces, zone):
    """per zone vertex: the mean of its zone neighbours' values (seam copies merged first)"""
    rep, e, m, in_zone, count = _merged_mesh(co, faces, zone)
    e = e[in_zone[e[:, 0]] & in_zone[e[:, 1]]]
    deg = np.bincount(e.ravel(), minlength=m).astype(float)

    def mean(values):
        d = np.zeros((m, values.shape[1]))
        np.add.at(d, rep[zone], values)
        d[in_zone] /= count[in_zone, None]
        acc = np.zeros_like(d)
        np.add.at(acc, e[:, 0], d[e[:, 1]])
        np.add.at(acc, e[:, 1], d[e[:, 0]])
        out = np.where(deg[:, None] > 0, acc / np.maximum(deg, 1)[:, None], d)
        return out[rep[zone]]
    return mean


def mesh_smoother(co, faces, zone, iterations=3, lam=0.5):
    """smooth a per-vertex change of the zone over the mesh: vertices at one position (UV seams) count as one and
    end up with one value; neighbours outside the zone hold 0"""
    rep, e, m, in_zone, count = _merged_mesh(co, faces, zone)
    deg = np.bincount(e.ravel(), minlength=m).astype(float)

    def smooth(change):
        d = np.zeros((m, 3))
        np.add.at(d, rep[zone], change)
        d[in_zone] /= count[in_zone, None]
        for _ in range(iterations):
            acc = np.zeros((m, 3))
            np.add.at(acc, e[:, 0], d[e[:, 1]])
            np.add.at(acc, e[:, 1], d[e[:, 0]])
            mean = np.where(deg[:, None] > 0, acc / np.maximum(deg, 1)[:, None], d)
            d = np.where(in_zone[:, None], (1 - lam) * d + lam * mean, 0.0)
        return d[rep[zone]]
    return smooth


def shrink(P, W, joint, d0, helpers, deg=90.0):
    """1 - r'/r about the arm line under a pure ひじ twist of deg"""
    X = candidates(P, {"kind": "etwist", "axis": d0, "deg": deg}, joint, helpers, None)
    pred = np.einsum("bni,nb->ni", X, W)

    def radial(Y):
        v = Y - joint
        return np.linalg.norm(v - np.outer(v @ d0, d0), axis=1)
    r0, r1 = radial(P), radial(pred)
    out = np.zeros(len(P))
    m = r0 > 0.2
    out[m] = 1 - r1[m] / r0[m]
    return out


# -- writing ----------------------------------------------------------------------------------------------------------------
def source_frame(model, source):
    """the source bone's tail offset and the local axes mmd_tools gives it on import (core/bone.py
    update_auto_bone_roll, used for 左ひじ / 右ひじ), as a PMX localCoordinate pair"""
    b = model.bones[source]
    tail = b.displayConnection
    if isinstance(tail, int):
        tail = tuple(np.array(model.bones[tail].location) - np.array(b.location))
    tail = np.array(tail, dtype=float)
    p1 = np.array([b.location[0], b.location[2], b.location[1]])            # Blender axes
    p2 = p1 + np.array([tail[0], tail[2], tail[1]])
    xz = np.array([p2[0] - p1[0], p2[2] - p1[2]])
    theta = math.atan2(xz[1], xz[0])
    norm = np.linalg.norm(p2 - p1)
    p3 = p2 + np.array([-norm * math.sin(theta), 0.0, norm * math.cos(theta)])
    y = (p2 - p1) / norm
    x = np.cross(y, (p3 - p1) / np.linalg.norm(p3 - p1))
    return tuple(tail), (float(y[0]), float(y[2]), float(y[1])), (float(x[0]), float(x[2]), float(x[1]))


def add_helper(model, pmx, name, name_e, location, parent, source, ratio):
    """a hidden bone turning ratio x source (回転付与), oriented exactly like the source in mmd_tools: the same tail
    direction and, through ローカル軸, the same roll - mmd_tools then takes the source's rotation straight over (its
    grants scale Euler angles; with aligned bones a bend stays one channel and matches MMD's slerp)"""
    tail, ax, az = source_frame(model, source)
    b = pmx.Bone()
    b.name, b.name_e = name, name_e
    b.location = tuple(float(v) for v in location)
    b.parent = parent
    b.transform_order = model.bones[source].transform_order
    b.displayConnection = tuple(float(v) for v in tail)
    b.isRotatable, b.isMovable, b.visible, b.isControllable = True, False, False, False
    b.hasAdditionalRotate = True
    b.additionalTransform = (source, float(ratio))
    b.localCoordinate = pmx.Coordinate(ax, az)
    model.bones.append(b)
    return len(model.bones) - 1


def set_weight(v, entries, pmx):
    entries = [(b, w) for b, w in entries if w > 1e-5]
    total = sum(w for _b, w in entries)
    entries = sorted(((b, w / total) for b, w in entries), key=lambda e: -e[1])
    wt = pmx.BoneWeight()
    if len(entries) == 1:
        wt.type, wt.bones, wt.weights = pmx.BoneWeight.BDEF1, [entries[0][0]], []
    elif len(entries) == 2:
        wt.type, wt.bones, wt.weights = pmx.BoneWeight.BDEF2, [entries[0][0], entries[1][0]], [entries[0][1]]
    else:
        if len(entries) > 4:
            raise ValueError("%d bones" % len(entries))
        entries = (entries + [(-1, 0.0)] * 4)[:4]
        wt.type = pmx.BoneWeight.BDEF4
        wt.bones, wt.weights = [b for b, _w in entries], [w for _b, w in entries]
    v.weight = wt


def vertex_normals(co, faces):
    f = np.asarray(faces, dtype=np.int64)
    fn = np.cross(co[f[:, 1]] - co[f[:, 0]], co[f[:, 2]] - co[f[:, 0]])     # area weighted
    out = np.zeros_like(co)
    for j in range(3):
        np.add.at(out, f[:, j], fn)
    return out


def elbow(model, pmx, xps, helpers=DEFAULT_HELPERS, data_dir=GAME_DATA, log=print, weight_smooth=None):
    """the work on a loaded model, in place; returns the report"""
    cfg = [tuple(float(x) for x in part.split(":")) for part in helpers.split(",")]
    weight_smooth = WEIGHT_SMOOTH if weight_smooth is None else weight_smooth
    game = Game(xps, data_dir)
    raise_ = ArmRaise(model, xps, game)
    fingers = fingers_straight(model)
    mesh_of, vert_of, mdist = match_vertices(model, xps, raise_, fingers)
    ok = mesh_of >= 0
    report = {"helpers": helpers, "vertices": len(model.vertices), "matched": int(ok.sum()),
              "match_max_dist": float(mdist[ok].max()) if ok.any() else None, "sides": {},
              "arms_raised_deg": {s: round(raise_.degrees(s), 2) for s in "lr"}, "fingers_straight": fingers}
    log("matched %d / %d vertices to the XPS (max %.5f); arms raised from the game's by %.1f / %.1f deg; fingers %s" % (
        ok.sum(), len(ok), report["match_max_dist"] or -1, raise_.degrees("l"), raise_.degrees("r"),
        "straightened" if fingers else "as bound"))
    co = np.array([v.co for v in model.vertices], dtype=float)
    bi, bw, sdef = pmx_weights(model, pmx)
    names = [b.name for b in model.bones]
    new_co = co.copy()
    changed = []
    for side, jp, tag in (("l", "左", "L"), ("r", "右", "R")):
        el = names.index(jp + "ひじ")
        parent = model.bones[el].parent                              # 腕捩
        upper_root = names.index(jp + "腕")
        nb = len(model.bones)
        fore = np.zeros(nb, dtype=bool)
        fore[list(subtree(model, el))] = True
        arm = np.zeros(nb, dtype=bool)
        arm[list(subtree(model, upper_root))] = True
        axis, joint = game.hinge(side)
        axis, joint = raise_.turn_vector(side, axis), raise_.turn_point(side, joint)
        J = np.array(model.bones[el].location)
        if np.linalg.norm(J - joint) > 0.01:
            raise SystemExit("%sひじ is not at the game's elbow (%.3f units off)" % (jp, np.linalg.norm(J - joint)))
        e1 = J - np.array(model.bones[upper_root].location)
        e1 -= (e1 @ axis) * axis
        e1 /= np.linalg.norm(e1)
        dist = np.linalg.norm(co - J, axis=1)
        zone = np.where(((bw * arm[np.maximum(bi, 0)] * (bi >= 0)).sum(1) > 1e-6) & (dist < ZONE) & ok)[0]
        # the game at the pose asset's angles
        angles, bends = [], []
        for angle, over in game.poses(side):
            K = game.skin_mats(over)
            T = co[zone].copy()
            for k in range(len(xps["meshes"])):
                sel = np.where(mesh_of[zone] == k)[0]
                if len(sel):
                    T[sel] = raise_.apply(k, game.deform(k, K))[vert_of[zone][sel]]
            angles.append(angle)
            bends.append(T)
        # each vertex's old upper-arm bones (twist ratio, share); the bones each candidate takes
        ratio = twist_ratios(model, parent)
        ur, us = np.ones((len(zone), 4)), np.zeros((len(zone), 4))
        costs = np.ones((len(zone), 2 + len(cfg)), dtype=np.int64)
        for row, i in enumerate(zone):
            ups = [(int(b), w) for b, w in zip(bi[i], bw[i]) if b >= 0 and w > 0 and not fore[b]]
            fos = [(int(b), w) for b, w in zip(bi[i], bw[i]) if b >= 0 and w > 0 and fore[b]]
            costs[row, 0], costs[row, 1] = max(1, len(ups)), max(1, len(fos))
            total = sum(w for _b, w in ups)
            for g, (b, w) in enumerate(ups):
                ur[row, g], us[row, g] = ratio[b], w / total
            if not ups:
                us[row, 0] = 1.0
        tax = np.array(model.bones[parent].axis or e1, dtype=float)
        tax /= np.linalg.norm(tax)
        tc = np.array(model.bones[parent].location)
        poses = ([{"kind": "bend", "axis": axis, "deg": a} for a in angles]
                 + [{"kind": "etwist", "axis": e1, "deg": d} for d in ETWIST]
                 + [{"kind": "utwist", "axis": tax, "deg": d, "centre": tc} for d in UTWIST])
        targets = np.concatenate([np.array(bends), np.repeat(co[zone][None], len(ETWIST), 0),
                                  np.array([turned(model, co, bi, bw, zone, parent, tax, d) for d in UTWIST])])
        wts = [1.0] * len(angles) + [ETWIST_WEIGHT] * len(ETWIST) + [1.0] * len(UTWIST)
        share = (bw[zone] * fore[np.maximum(bi[zone], 0)] * (bi[zone] >= 0)).sum(1) / bw[zone].sum(1)
        hs = [(k, J + s * e1) for k, s in cfg]
        fade = 1.0 - smoothstep((dist[zone] - FADE_FROM) / (ZONE - FADE_FROM))
        W, Pc, err, _share = fit(co[zone], poses, targets, wts, J, hs, (ur, us), costs, share, fade,
                                 smooth=mesh_smoother(co, model.faces, zone) if SMOOTH else None,
                                 neighbours=neighbour_mean(co, model.faces, zone), lam=weight_smooth)
        # before / after, for the report
        before = np.array([turned(model, co, bi, bw, zone, el, axis, a) for a in angles])
        e_old = np.linalg.norm(before - np.array(bends), axis=2) * 8
        e_new = err[:len(angles)] * 8
        sh_new = shrink(Pc, W, J, e1, hs)
        sh_old = shrink(co[zone], np.stack([1 - share, share], axis=1), J, e1, [])
        # the bones and the weights
        hb = [add_helper(model, pmx, "%sひじ補%d" % (jp, j + 1), "elbow helper%d_%s" % (j + 1, tag), J + s * e1,
                         parent, el, k) for j, (k, s) in enumerate(cfg)]
        for row, i in enumerate(zone):
            olds = [(int(b), float(w)) for b, w in zip(bi[i], bw[i]) if b >= 0 and w > 0]
            up = [(b, w) for b, w in olds if not fore[b]] or [(parent, 1.0)]
            fo = [(b, w) for b, w in olds if fore[b]] or [(el, 1.0)]
            su, sf = sum(w for _b, w in up), sum(w for _b, w in fo)
            entries = [(b, W[row, 0] * w / su) for b, w in up] + [(b, W[row, 1] * w / sf) for b, w in fo] \
                + [(b, W[row, 2 + j]) for j, b in enumerate(hb)]
            set_weight(model.vertices[i], entries, pmx)
            new_co[i] = Pc[row]
        changed.extend(zone.tolist())
        moved = np.linalg.norm(Pc - co[zone], axis=1) * 8
        rep = {"zone": int(len(zone)), "angles": [round(a, 1) for a in angles],
               "before_cm_max_per_angle": [round(float(x), 2) for x in e_old.max(1)],
               "after_cm_max_per_angle": [round(float(x), 2) for x in e_new.max(1)],
               "before_cm_mean": float(e_old.mean()), "after_cm_mean": float(e_new.mean()),
               "twist90_shrink_before_max": float(sh_old.max()), "twist90_shrink_after_max": float(sh_new.max()),
               "rest_moved_cm_max": float(moved.max()), "sdef_dropped": int(sdef[zone].sum()),
               "helper_bones": [model.bones[b].name for b in hb]}
        report["sides"][side] = rep
        log("%s: %d vertices; against the game max %.2f -> %.2f cm (mean %.3f -> %.3f); elbow twist 90: ring shrinks "
            "%.0f %% -> %.0f %%; rest moved max %.2f cm; SDEF dropped %d" % (
                jp, len(zone), e_old.max(), e_new.max(), e_old.mean(), e_new.mean(), 100 * sh_old.max(),
                100 * sh_new.max(), moved.max(), sdef[zone].sum()))
    # positions and normals (each stored normal turned as its face normal turned)
    idx = np.array(sorted(set(changed)))
    n_old, n_new = vertex_normals(co, model.faces), vertex_normals(new_co, model.faces)
    for i in idx:
        v = model.vertices[i]
        v.co = tuple(float(x) for x in new_co[i])
        n = rotation_between(n_old[i], n_new[i]) @ np.array(v.normal, dtype=float)
        v.normal = tuple(float(x) for x in n / max(np.linalg.norm(n), 1e-12))
    lines = [line for line in (model.comment or "").replace("\r\n", "\n").split("\n")
             if not line.startswith("SDEF on the joint rings")]
    lines.append("%s (%s; pcf_lowerarm poses, %d vertices, scripts/vindictus/pmx_elbow.py)" % (MARK, helpers, len(idx)))
    model.comment = "\r\n".join(lines)
    report["vertices_changed"] = int(len(idx))
    return report


def elbow_file(pmx_in, pmx_out, xps_path, helpers=DEFAULT_HELPERS, data_dir=GAME_DATA, log=print,
               weight_smooth=None):
    pmx = bust_physics.load_pmx_module()
    model = pmx.load(pmx_in)
    if MARK in (model.comment or ""):
        raise SystemExit("already done: " + pmx_in)
    report = elbow(model, pmx, read_xps(xps_path), helpers, data_dir, log, weight_smooth)
    tmp = pmx_out + ".elbow.tmp"
    pmx.save(tmp, model)
    os.replace(tmp, pmx_out)
    report.update({"pmx": pmx_in, "out": pmx_out, "xps": xps_path})
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pmx_in")
    ap.add_argument("pmx_out")
    ap.add_argument("--xps", required=True, help="the XPS export_pmx.py made this PMX from")
    ap.add_argument("--helpers", default=DEFAULT_HELPERS, help="ratio:offset,... (default %(default)s)")
    ap.add_argument("--game-data", default=GAME_DATA)
    ap.add_argument("--weight-smooth", type=float, default=None,
                    help="pull towards the neighbours' weights (default %s)" % WEIGHT_SMOOTH)
    ap.add_argument("--report")
    args = ap.parse_args()
    t0 = time.time()
    report = elbow_file(args.pmx_in, args.pmx_out, args.xps, args.helpers, args.game_data,
                        weight_smooth=args.weight_smooth)
    report["seconds"] = round(time.time() - t0, 1)
    print("wrote %s (%.0f s)" % (args.pmx_out, time.time() - t0))
    if args.report:
        json.dump(report, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
