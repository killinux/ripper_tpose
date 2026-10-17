"""The game's shoulder correctives in a finished Vindictus PMX: helper bones that slide the shoulder's flesh.

Why: the MetaHuman body keeps the shoulder in shape with corrective joints driven at runtime by the PoseDriver nodes
of ABP_PCF_Corrective from the pose assets BaseBody_PCF/Poses/pcf_upperarm_l/r_pose (11 arm directions) and
pcf_clavicle_l/r_pose (shoulder forward / back / down / up): upperarm_correctiveRoot turns half the arm's turn,
upperarm_out / fwd / bck / in slide on it (fwd 16 cm with the arm forward and up), clavicle_out / scap / pec and
spine_04_latissimus move with the clavicle (scap 12 cm with the shoulder pulled back).  export_pmx.py folds them into
腕 / 肩 / 上半身5 (MMD cannot drive them), so the shoulder is plain skinning on the game's own weights (since
2026-10-11 without the converter's armpit smoothing): 4-7 cm off the game's shape with the arm forward or raised.

What: per side three hidden bones, children of 肩C (腕's parent), that MMD and mmd_tools both drive with plain
回転付与 (rotation grant) from 腕 - 0.63 of its turn about a point 150 cm out along the arm line, 0.70 about one 60 cm
inside the body, 0.30 about one 12 cm out.  A vertex sharing in the far ones slides along with the arm's swing, a
little behind or ahead of it, the way the game's correctives slide the flesh (two far pivots on opposite sides
nearly cancel at small angles and add up at large ones).  Every vertex within ZONE of the shoulder joint that the
game skins to the clavicle or upper arm (and to nothing below the elbow) gets new weights: its body share stays
(what follows the chest), the rest is shared between 肩, 腕 (each keeping its own bones' split - 腕捩1-3, the elbow
helpers) and the helpers, at most 4 bones (body bones no motion turns apart - 上半身4-5 under 上半身3, 首1 under
首 - count as one and are merged onto one when needed), fitted so linear skinning reproduces the game at its
corrective poses, weighted by how often dance motions come near each (the arm hanging forward or back, reaching
forward count most); 腕 twisted about its own line must move the shoulder as before.  Each vertex's weights are
pulled a little towards its neighbours' (outside the zone: their old weights).  Rest positions do not change.

Choices (PCF_005, 2026-10-17): pivots on the arm line, because a twist of 腕 about its own line
then turns a helper exactly like the arm - pivots off the line fitted the game a little closer but swung the
shoulder 2-3 cm out of place when the arm twisted.  No 肩 helper by default ("clav:ratio:offset" adds one): the best
one (0.59 of 肩 about a point 24 cm in front of it) halves the error with the shoulder pulled back (4.0 -> 1.9 cm)
but folds the back over the shoulder blade when the shoulder goes forward.  Old weights below PRUNE are dropped
first (the elbow tool's 0.00x on ひじ補1/2 took the slots the helpers need, and a vertex with none next to one on
helpers alone creased when the arm went up).  Ratios below 1 are Euler-scaled by mmd_tools (MMD slerps): on the
game poses Blender and MMD differ by at most 0.1 cm, on the 244 keys of 最佳男主角 by 1.2 cm at most (the arm
110 deg up with twist), 0.004 cm on average - Blender itself matches the tool's model of it to 0.0001 cm.

PCF_005, against the game (left zone, max / mean cm): arm horizontal 1.99 / 0.20 -> 1.80 / 0.14, raised 55 deg
4.16 / 0.39 -> 3.09 / 0.22, forward and up 7.08 / 0.55 -> 2.68 / 0.22, forward 5.80 / 0.46 -> 2.38 / 0.19, hanging
forward 1.85 / 0.12 -> 1.36 / 0.11, back 1.87 / 0.15 the same; the lower arm poses within 0.25 cm of before; the
clavicle poses as before (pulled back 4.0, raised 3.1); 腕 twisted 90 deg 2.0 cm from before.  Fiona (armour):
forward and up 7.29 / 1.26 -> 2.91 / 0.53, forward 5.92 / 1.03 -> 2.53 / 0.43.

    python pmx_shoulder.py <id>.pmx <out>.pmx --xps <id>.xps          # the XPS export_pmx.py was given
    python pmx_shoulder.py ... --report r.json --helpers "arm:0.63:150,arm:0.70:-60,arm:0.30:12,clav:0.59:-20/0/-12.5"

Run it last (after pmx_elbow.py).  Arms raised before the conversion (export_pmx.py --arm-angle) are recognised like
in pmx_elbow.py.  Write <out> next to <id>.pmx (texture paths).  A PMX that already has the comment line (MARK) is
refused.  The game data (skeleton + pose assets, CUE4Parse JSON) is not in the repo: --game-data, default
E:\\game_export\\Vindictus\\_meta\\elbow (how to export it: README.md, 手臂权重 / 肩部).  Needs numpy and the
XNALaraMesh add-on's XPS reader; plain Python, ~20 s.
"""
import argparse
import itertools
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)
import pmx_elbow as pe  # noqa: E402

GAME_DATA = pe.GAME_DATA
POSE_ASSETS = {"upperarm": "pcf_upperarm_%s_pose.json", "clavicle": "pcf_clavicle_%s_pose.json"}
MARK = "shoulder: the game's shoulder correctives as helper bones"
# kind:ratio:offset - offset cm along the arm line from 腕's head (+ = out towards the elbow), or x/y/z cm from the
# head (x = towards the model's own side); found by Nelder-Mead on PCF_005's fit (2026-10-17, scratch b_opt3.py)
DEFAULT_HELPERS = "arm:0.63:150,arm:0.70:-60,arm:0.30:12"
ZONE = 2.2                       # PMX units (17.6 cm) from the shoulder joint; the correctives act within ~15 cm
TWISTS = (45.0, -45.0, 90.0, -90.0)
TWIST_WEIGHT = 1.0
WEIGHT_SMOOTH = 1.0              # pull towards the neighbours' weights (PCF_005, creases = the posed mesh's local bend
                                 # against the game's, max cm, plain PMX 1.79 / 1.54 / 1.43 at forward-up / 55 up /
                                 # forward: 0 -> 1.28 / 1.52 / 1.03 ... 1 the same, 3 -> 1.34 / 1.69 / 1.06,
                                 # 10 -> 1.52 / 1.70 / 1.20; the game error the same)
WEIGHT_SMOOTH_ITER = 8
PRUNE = 0.02                     # the zone's old weights below this are dropped first (the elbow tool leaves 0.00x
                                 # on ひじ補1/2 high up the arm: they took the slots helpers need, and a vertex that
                                 # could take none next to one on helpers alone creased when the arm went up)
JUNK_TRACKS = ("calf_", "index_01_half_")     # in every pose of these assets, nothing to do with the shoulder
C_UE = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])     # UE axes -> PMX axes
# how often dance motions come near each game arm direction (degrees below the horizontal, forward; left side):
# 最佳男主角 / 手势舞 / 永劫无间摇香 / superstar / 姑娘别哭泣 keys mostly hang the arm forward or back (P3, P1, P7,
# P9, P6), reach forward (P11) and pull the shoulder back (clavicle back); raised arms are rarer
ARM_WEIGHTS = (((39.2, -60.0), 3.0), ((-0.1, -1.7), 1.0), ((85.5, 86.7), 3.0), ((-30.0, -4.2), 1.0),
               ((-20.6, 79.5), 1.0), ((64.5, 7.8), 2.0), ((50.1, 28.2), 2.0), ((39.7, 2.1), 3.0),
               ((54.7, -12.7), 2.0), ((-54.9, -8.0), 1.0), ((-4.5, 88.3), 2.0))
CLAVICLE_BACK_WEIGHT = 3.0       # the shoulder pulled back (the other clavicle poses 1)
# bones MMD motions key (standard + semi-standard); a body bone outside these, without physics, grant, IK or bone
# morph turns with its parent in every motion (the converter's 上半身4-5 and 首1, the face rig's neck joints: in
# 2026-10 none of the user's 535 VMDs turns them - 244 key 上半身3, all at 0 deg), so the 4-bone limit counts it with it
KEYED = {"全ての親", "センター", "グルーブ", "腰", "上半身", "上半身1", "上半身2", "上半身3", "下半身", "首", "頭", "両目",
         "左目", "右目"} | {s + n for s in ("左", "右") for n in (
             "肩P", "肩", "肩C", "腕", "腕捩", "ひじ", "手捩", "手首", "ダミー", "親指０", "親指１", "親指２", "人指１", "人指２",
             "人指３", "中指１", "中指２", "中指３", "薬指１", "薬指２", "薬指３", "小指１", "小指２", "小指３", "足", "ひざ", "足首",
             "足先EX", "足ＩＫ", "つま先ＩＫ", "足D", "ひざD", "足首D", "腰キャンセル")}


def parse_helpers(spec):
    """kind:ratio:offset - offset in cm along the arm / clavicle line, or x/y/z cm from 腕's / 肩's head (x towards
    the model's own side: mirrored for the right)"""
    out = []
    for part in spec.split(","):
        kind, ratio, offset = part.split(":")
        if kind not in ("arm", "clav"):
            raise SystemExit("helper kind must be arm or clav: " + part)
        off = tuple(float(v) for v in offset.split("/"))
        if len(off) not in (1, 3):
            raise SystemExit("offset must be one number or x/y/z: " + part)
        out.append((kind, float(ratio), off if len(off) == 3 else off[0]))
    return out


def rpow(R, r):
    """R to the power r (the same axis, r times the angle) - MMD's slerp grant"""
    c = np.clip((np.trace(R) - 1) / 2, -1, 1)
    th = math.acos(c)
    if th < 1e-9:
        return np.eye(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(v)
    if n < 1e-9:
        w, V = np.linalg.eigh((R + R.T) / 2)
        a = V[:, np.argmax(w)]
    else:
        a = v / n
    return pe.rotation(a, th * r)


# -- mmd_tools' grant (Blender): Euler XYZ channels of the source's local rotation scaled ------------------------------
P_SWAP = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])     # PMX <-> Blender axes


def blender_frame(model, bone):
    """the Blender bone frame (columns X, Y, Z, Blender axes) mmd_tools gives 腕 / 肩 (update_auto_bone_roll), which
    pe.add_helper copies onto the helpers"""
    tail, ax, az = pe.source_frame(model, bone)
    y = P_SWAP @ np.array(ax)
    x = P_SWAP @ np.array(az)
    z = np.cross(x, y)
    z -= (z @ y) * y
    z /= np.linalg.norm(z)
    return np.stack([np.cross(y, z), y, z], axis=1)


def _eul_xyz(M):
    cy = math.hypot(M[0, 0], M[1, 0])
    if cy > 16 * 1.19e-7:
        e1 = (math.atan2(M[2, 1], M[2, 2]), math.atan2(-M[2, 0], cy), math.atan2(M[1, 0], M[0, 0]))
        e2 = (math.atan2(-M[2, 1], -M[2, 2]), math.atan2(-M[2, 0], -cy), math.atan2(-M[1, 0], -M[0, 0]))
        return e1 if sum(map(abs, e1)) <= sum(map(abs, e2)) else e2
    return (math.atan2(-M[1, 2], M[1, 1]), math.atan2(-M[2, 0], cy), 0.0)


def euler_grant(L, r, frame):
    a, b, c = (r * v for v in _eul_xyz(frame.T @ (P_SWAP @ L @ P_SWAP) @ frame))
    E = pe.rotation((0, 0, 1), c) @ pe.rotation((0, 1, 0), b) @ pe.rotation((1, 0, 0), a)
    return P_SWAP @ (frame @ E @ frame.T) @ P_SWAP


# -- the game ---------------------------------------------------------------------------------------------------------
def pose_asset(data_dir, name):
    """{pose: {track: (q, t, s)}} of a PoseAsset JSON (CUE4Parse)"""
    pc = pe._json(os.path.join(data_dir, name))[0]["Properties"]["PoseContainer"]
    names = [p["DisplayName"] for p in pc["PoseNames"]]
    poses = {n: {} for n in names}
    for t, infl in enumerate(pc["TrackPoseInfluenceIndices"]):
        for i in infl["Influences"]:
            tr = pc["Poses"][i["PoseIndex"]]["LocalSpacePose"][i["BoneTransformIndex"]]
            r, p, s = tr["Rotation"], tr["Translation"], tr["Scale3D"]
            poses[names[i["PoseIndex"]]][pc["Tracks"][t]] = ((r["X"], r["Y"], r["Z"], r["W"]), (p["X"], p["Y"], p["Z"]),
                                                              (s["X"], s["Y"], s["Z"]))
    return poses


def world_rot(G, i):
    R = G[i][:3, :3]
    return C_UE @ (R / np.linalg.norm(R, axis=0)) @ C_UE.T


def arm_direction(game, G, side):
    """degrees below the horizontal and forward (PMX: the model faces -z) of the upper arm"""
    a = pe.ue_to_pmx(G[game.index["lowerarm_" + side]][:3, 3]) - pe.ue_to_pmx(G[game.index["upperarm_" + side]][:3, 3])
    a /= np.linalg.norm(a)
    return math.degrees(math.asin(-a[1])), math.degrees(math.atan2(-a[2], abs(a[0])))


def rigid_reps(model):
    """each bone's representative: itself, or for a bone that cannot turn on its own (see KEYED) the nearest
    ancestor that can - bones sharing one move as one in every motion"""
    dyn = {r.bone for r in model.rigids if r.mode != 0}
    ik = set()
    for i, b in enumerate(model.bones):
        if b.isIK:
            ik.update([i, b.target] + [link.target for link in b.ik_links])
    morph = {o.index for mo in model.morphs for o in mo.offsets if type(o).__name__ == "BoneMorphOffset"}

    def active(i):
        b = model.bones[i]
        return (b.name in KEYED or i in dyn or i in ik or i in morph or b.hasAdditionalRotate
                or b.hasAdditionalLocation or b.parent is None or b.parent < 0)
    rep = np.arange(len(model.bones))
    for i in range(len(model.bones)):
        j = i
        while not active(j):
            j = model.bones[j].parent
        rep[i] = j
    return rep


def arm_weight(below, fwd):
    def gap(d):
        return math.hypot(d[0][0] - below, d[0][1] - fwd)
    return min(ARM_WEIGHTS, key=gap)[1]


# -- one side ---------------------------------------------------------------------------------------------------------
class Side:
    """the zone, its targets at the game's poses and the candidate bones' positions"""

    def __init__(self, model, xps, game, raise_, mesh_of, vert_of, side, data_dir, log=print):
        self.side, self.jp = side, {"l": "左", "r": "右"}[side]
        names = [b.name for b in model.bones]
        jp = self.jp
        self.i_arm, self.i_clav = names.index(jp + "腕"), names.index(jp + "肩")
        self.J = np.array(model.bones[self.i_arm].location, dtype=float)
        self.S = np.array(model.bones[self.i_clav].location, dtype=float)
        el = np.array(model.bones[names.index(jp + "ひじ")].location, dtype=float) - self.J
        self.u = el / np.linalg.norm(el)
        self.cl = (self.J - self.S) / np.linalg.norm(self.J - self.S)
        self.F_arm, self.F_clav = blender_frame(model, self.i_arm), blender_frame(model, self.i_clav)
        # roles of the PMX bones: 0 body, 1 the 肩 subtree without the arm, 2 the 腕 subtree
        arm = pe.subtree(model, self.i_arm)
        self.role = np.zeros(len(names) + 1, dtype=int)
        for b in pe.subtree(model, self.i_clav) - arm:
            self.role[b] = 1
        for b in arm:
            self.role[b] = 2
        # the zone: the game skins it to this clavicle / upper arm (or their correctives), nothing below the elbow
        below = set()
        root = game.index["lowerarm_" + side]
        for i in range(len(game.parents)):
            j = i
            while j >= 0:
                if j == root:
                    below.add(i)
                    break
                j = game.parents[j]
        shoulder = pe.ue_to_pmx(game.G_bind[game.index["upperarm_" + side]][:3, 3])
        if np.linalg.norm(shoulder - self.J) > 0.01:
            raise SystemExit("%s腕 is not at the game's shoulder" % jp)
        ok = np.zeros(len(mesh_of), dtype=bool)
        for k in np.unique(mesh_of[mesh_of >= 0]):
            m = xps["meshes"][k]
            sel = np.where(mesh_of == k)[0]
            ue = game.xps_ue[m["bones"][vert_of[sel]]]
            w = m["weights"][vert_of[sel]]
            arm_w = np.zeros(len(sel))
            low = np.zeros(len(sel))
            for j in range(4):
                nm = [game.names[x] if x >= 0 else "" for x in ue[:, j]]
                arm_w += w[:, j] * np.array([("clavicle_" + side in n or "upperarm_" + side in n
                                              or n == "spine_04_latissimus_" + side) for n in nm])
                low += w[:, j] * np.isin(ue[:, j], list(below))
            near = np.linalg.norm(pe.xps_to_pmx(m["co"][vert_of[sel]]) - shoulder, axis=1) < ZONE
            ok[sel] = (arm_w > 0) & (low == 0) & near
        self.zone = np.where(ok)[0]
        self.P = np.array([model.vertices[i].co for i in self.zone], dtype=float)
        # the arm raise (the PMX rest against the game's bind)
        self.rest = pe.rotation(*raise_.sides[side][1:3]) if side in raise_.sides else np.eye(3)
        # the game's poses
        self.poses = []
        G0 = game.G_bind
        iu, ic = game.index["upperarm_" + side], game.index["clavicle_" + side]
        for asset, fname in POSE_ASSETS.items():
            P = pose_asset(data_dir, fname % side)
            for pn, tracks in P.items():
                driver = ("upperarm_" if asset == "upperarm" else "clavicle_") + side
                if driver not in tracks:
                    continue
                tracks = {t: v for t, v in tracks.items() if not t.startswith(JUNK_TRACKS) and t in game.index}
                K = game.skin_mats(tracks)
                G = game.fk([pe.trs(*tracks[n]) if n in tracks else game.bind_local[i]
                             for i, n in enumerate(game.names)])
                target = np.zeros_like(self.P)
                for k in np.unique(mesh_of[self.zone]):
                    rows = np.where(mesh_of[self.zone] == k)[0]
                    target[rows] = game.deform(k, K)[vert_of[self.zone][rows]]
                if asset == "upperarm":
                    D = world_rot(G, iu) @ world_rot(G0, iu).T
                    clavR, armL = np.eye(3), D @ self.rest.T
                    below_deg, fwd = arm_direction(game, G, side)
                    weight = arm_weight(below_deg, fwd)
                else:
                    D = world_rot(G, ic) @ world_rot(G0, ic).T
                    clavR, armL = D, D.T @ (world_rot(G, iu) @ world_rot(G0, iu).T) @ self.rest.T
                    back = (D @ (self.J - self.S))[2] - (self.J - self.S)[2]
                    weight = CLAVICLE_BACK_WEIGHT if back * 8 > 2.0 else 1.0
                    below_deg, fwd = 0.0, 0.0
                self.poses.append({"asset": asset, "name": pn, "target": target, "clavR": clavR, "armL": armL,
                                   "weight": weight, "dir": (below_deg, fwd)})
        log("%s: zone %d vertices; %d game poses" % (jp, len(self.zone), len(self.poses)))

    # where each kind of bone puts the zone in a pose (clavR: 肩's turn, armL: 腕's)
    def clav(self, p, X):
        return self.S + (X - self.S) @ p["clavR"].T

    def arm(self, p, X):
        return self.clav(p, self.J + (X - self.J) @ p["armL"].T)

    def helper(self, p, X, kind, ratio, Q, blender=False):
        if kind == "arm":
            R = euler_grant(p["armL"], ratio, self.F_arm) if blender else rpow(p["armL"], ratio)
            return self.clav(p, Q + (X - Q) @ R.T)
        R = euler_grant(p["clavR"], ratio, self.F_clav) if blender else rpow(p["clavR"], ratio)
        return Q + (X - Q) @ R.T

    def pivot(self, kind, offset_cm):
        base = self.J if kind == "arm" else self.S
        if isinstance(offset_cm, tuple):
            x, y, z = offset_cm
            return base + np.array([x if self.side == "l" else -x, y, z]) / 8.0
        return base + (self.u if kind == "arm" else self.cl) * offset_cm / 8.0


def solve_weights(X, T, costs, limit, prior=None, lam=0.0):
    """per vertex: min sum_k |sum_b w_b X[k,b] - T[k]|^2 (+ lam |w - prior|^2, lam per vertex or one), w >= 0,
    sum w = 1, the bones of the used candidates (costs) within the vertex's limit; every subset solved, the best
    feasible one kept"""
    K, B, N, _ = X.shape
    A = X.transpose(2, 0, 3, 1).reshape(N, K * 3, B)
    y = T.transpose(1, 0, 2).reshape(N, K * 3)
    if prior is not None:
        root = np.sqrt(np.broadcast_to(np.asarray(lam, dtype=float), (N,)))
        A = np.concatenate([A, root[:, None, None] * np.eye(B)[None]], axis=1)
        y = np.concatenate([y, root[:, None] * prior], axis=1)
    best_w = np.zeros((N, B))
    best_e = np.full(N, np.inf)
    for r in range(1, min(B, int(limit.max())) + 1):
        for s in itertools.combinations(range(B), r):
            s = list(s)
            fits = costs[:, s].sum(1) <= limit
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
    return best_w, np.isfinite(best_e)


# -- the fit ------------------------------------------------------------------------------------------------------------
def zone_neighbours(model, bi, bw, sd, nb):
    """a function giving each zone vertex the mean of its neighbours' weights in the zone's 肩 / 腕 / helper space
    (UV-seam copies merged; each neighbour counted by its non-body share) - neighbours outside the zone with their
    own (old) weights, so the zone's edge does not break"""
    co = np.array([v.co for v in model.vertices], dtype=float)
    z = sd.zone
    rep, e, m, in_zone, count = pe._merged_mesh(co, model.faces, z)
    role_all = sd.role[np.where(bi >= 0, bi, nb)]
    W_all = np.zeros((len(co), 3))
    for j in range(4):
        W_all[np.arange(len(co)), role_all[:, j]] += np.where(bi[:, j] >= 0, bw[:, j], 0.0)
    W_all /= np.maximum(W_all.sum(1, keepdims=True), 1e-12)
    old_m = np.zeros((m, 3))
    np.add.at(old_m, rep, W_all)
    old_m /= np.bincount(rep, minlength=m)[:, None]
    edges = e[in_zone[e[:, 0]] | in_zone[e[:, 1]]]

    def neighbour_mean(W_sub_rest):
        """W_sub_rest: (zone, 2 + helpers), the zone's non-body weights (not normalised)"""
        val = np.zeros((m, W_sub_rest.shape[1]))
        val[:, :2] = old_m[:, 1:]
        zsum = np.zeros_like(val)
        np.add.at(zsum, rep[z], W_sub_rest)
        val[in_zone] = zsum[in_zone] / count[in_zone, None]
        acc = np.zeros_like(val)
        np.add.at(acc, edges[:, 0], val[edges[:, 1]])
        np.add.at(acc, edges[:, 1], val[edges[:, 0]])
        out = acc[rep[z]]
        tot = out.sum(1, keepdims=True)
        own = W_sub_rest / np.maximum(W_sub_rest.sum(1, keepdims=True), 1e-12)
        return np.where(tot > 1e-9, out / np.maximum(tot, 1e-12), own)
    return neighbour_mean


def fit_side(sd, model, bi, bw, helpers, reps, weight_smooth=None, log=print):
    """weights (n, 3 + helpers) of the zone: body (kept), 肩, 腕, helpers; and the report numbers"""
    weight_smooth = WEIGHT_SMOOTH if weight_smooth is None else weight_smooth
    z = sd.zone
    nb = len(model.bones)
    role = sd.role[np.where(bi[z] >= 0, bi[z], nb)]
    W_old = np.zeros((len(z), 3))
    costs = np.zeros((len(z), 3), dtype=np.int64)
    for j in range(4):
        used = (bi[z, j] >= 0) & (bw[z, j] > 0)
        np.add.at(W_old, (np.arange(len(z))[used], role[used, j]), bw[z, j][used])
        np.add.at(costs, (np.arange(len(z))[used], role[used, j]), 1)
    W_old /= W_old.sum(1, keepdims=True)
    for row, i in enumerate(z):                          # body bones that move as one count as one
        costs[row, 0] = len({reps[b] for b, w in zip(bi[i], bw[i]) if b >= 0 and w > 0 and sd.role[b] == 0})
    hs = [(kind, ratio, sd.pivot(kind, off)) for kind, ratio, off in helpers]
    twists = [{"asset": "twist", "name": "%+.0f" % deg, "clavR": np.eye(3), "armL": pe.rotation(sd.u, math.radians(deg)),
               "weight": TWIST_WEIGHT} for deg in TWISTS]
    poses = sd.poses + twists

    def candidates(blender=False):
        out = []
        for p in poses:
            row = [sd.P, sd.clav(p, sd.P), sd.arm(p, sd.P)]
            row += [sd.helper(p, sd.P, kind, ratio, Q, blender) for kind, ratio, Q in hs]
            out.append(row)
        return np.array(out)

    X = candidates()
    T = np.array([p["target"] for p in sd.poses]
                 + [np.einsum("bni,nb->ni", X[len(sd.poses) + i, :3], W_old) for i in range(len(twists))])
    sw = np.sqrt(np.array([p["weight"] for p in poses]))
    wb = W_old[:, 0]
    rest = np.maximum(1 - wb, 1e-9)
    Y = (T - wb[None, :, None] * X[:, 0]) / rest[None, :, None]
    Xs = X[:, 1:] * sw[:, None, None, None]
    Ys = Y * sw[:, None, None]
    sub_costs = np.concatenate([np.maximum(costs[:, 1:], 1), np.ones((len(z), len(hs)), dtype=np.int64)], axis=1)
    limit = 4 - np.where(wb > 1e-6, costs[:, 0], 0)
    # each vertex pulled towards its neighbours' weights - neighbours outside the zone with their old weights, so the
    # zone's edge does not break (a fade to the old weights at the edge loses the correction: a third of the game's
    # biggest moves lie within 4 cm of it)
    neighbour_mean = zone_neighbours(model, bi, bw, sd, nb)
    Ws, ok = solve_weights(Xs, Ys, sub_costs, limit)
    for _step in range(WEIGHT_SMOOTH_ITER if weight_smooth > 0 else 0):
        Ws, ok = solve_weights(Xs, Ys, sub_costs, limit, prior=neighbour_mean(rest[:, None] * Ws), lam=weight_smooth)
    keep = (wb > 1 - 1e-6) | ~ok                        # all body, or no subset fits: the old weights stay
    W = np.concatenate([wb[:, None], rest[:, None] * Ws], axis=1)
    W[keep] = 0
    W[keep, :3] = W_old[keep]
    # report: against the game (and the twist targets), before / after, MMD and Blender
    before = np.linalg.norm(np.einsum("kbni,nb->kni", X[:, :3], W_old) - T, axis=2) * 8
    after = np.linalg.norm(np.einsum("kbni,nb->kni", X, W) - T, axis=2) * 8
    after_b = np.linalg.norm(np.einsum("kbni,nb->kni", candidates(True), W) - T, axis=2) * 8
    rows = []
    for k, p in enumerate(poses):
        rows.append({"asset": p["asset"], "pose": p["name"], "weight": p["weight"],
                     "dir_below_fwd": [round(v, 1) for v in p.get("dir", (0.0, 0.0))],
                     "before_cm": [round(float(before[k].max()), 2), round(float(before[k].mean()), 3)],
                     "after_cm": [round(float(after[k].max()), 2), round(float(after[k].mean()), 3)],
                     "after_blender_cm": [round(float(after_b[k].max()), 2), round(float(after_b[k].mean()), 3)]})
    game = slice(0, len(sd.poses))
    log("%s: %d vertices (%d kept); against the game max %.2f -> %.2f cm, mean %.3f -> %.3f (Blender %.2f / %.3f); "
        "arm twisted 90: %.2f cm from before" % (
            sd.jp, len(z), keep.sum(), before[game].max(), after[game].max(), before[game].mean(), after[game].mean(),
            after_b[game].max(), after_b[game].mean(), after[len(sd.poses):].max()))
    cost = float((sw[:, None] ** 2 * after ** 2).sum() / (sw ** 2).sum() / after.shape[1])
    return W, W_old, hs, {"zone": int(len(z)), "kept": int(keep.sum()), "poses": rows, "cost_cm2": cost,
                          "before_cm_max": round(float(before[game].max()), 2),
                          "after_cm_max": round(float(after[game].max()), 2),
                          "before_cm_mean": round(float(before[game].mean()), 3),
                          "after_cm_mean": round(float(after[game].mean()), 3)}


# -- writing ------------------------------------------------------------------------------------------------------------
def shoulder(model, pmx, xps, helpers=DEFAULT_HELPERS, data_dir=GAME_DATA, log=print, weight_smooth=None):
    """the work on a loaded model, in place; returns the report"""
    cfg = parse_helpers(helpers)
    game = pe.Game(xps, data_dir)
    raise_ = pe.ArmRaise(model, xps, game)
    fingers = pe.fingers_straight(model)
    mesh_of, vert_of, _dist = pe.match_vertices(model, xps, raise_, fingers)
    ok = mesh_of >= 0
    report = {"helpers": helpers, "vertices": len(model.vertices), "matched": int(ok.sum()),
              "arms_raised_deg": {s: round(raise_.degrees(s), 2) for s in "lr"}, "sides": {}}
    log("matched %d / %d vertices to the XPS; arms raised from the game's by %.1f / %.1f deg" % (
        ok.sum(), len(ok), raise_.degrees("l"), raise_.degrees("r")))
    bi, bw, _sdef = pe.pmx_weights(model, pmx)
    bw = np.where(bw < PRUNE, 0.0, bw)                  # pruned everywhere it is read; only the zones are written
    bw /= np.maximum(bw.sum(1, keepdims=True), 1e-12)
    nb = len(model.bones)
    reps = rigid_reps(model)
    for side, tag in (("l", "L"), ("r", "R")):
        sd = Side(model, xps, game, raise_, mesh_of, vert_of, side, data_dir, log)
        W, W_old, hs, rep = fit_side(sd, model, bi, bw, cfg, reps, weight_smooth, log)
        hb = []
        counts = {"arm": 0, "clav": 0}
        for kind, ratio, Q in hs:
            counts[kind] += 1
            if "%s%s補%d" % (sd.jp, "腕" if kind == "arm" else "肩", counts[kind]) in [b.name for b in model.bones]:
                raise SystemExit("bone %s%s補%d exists already" % (sd.jp, "腕" if kind == "arm" else "肩", counts[kind]))
            src = sd.i_arm if kind == "arm" else sd.i_clav
            hb.append(pe.add_helper(model, pmx, "%s%s補%d" % (sd.jp, "腕" if kind == "arm" else "肩", counts[kind]),
                                    "%s helper%d_%s" % ("arm" if kind == "arm" else "shoulder", counts[kind], tag),
                                    Q, model.bones[src].parent, src, ratio))
        lead = {1: sd.i_clav, 2: sd.i_arm}
        merges = 0
        for row, i in enumerate(sd.zone):
            olds = [(int(b), float(w)) for b, w in zip(bi[i], bw[i]) if b >= 0 and w > 0]
            entries = [(b, w) for b, w in olds if sd.role[b] == 0]
            for r in (1, 2):
                group = [(b, w) for b, w in olds if sd.role[b] == r]
                total = sum(w for _b, w in group)
                if W[row, r] <= 1e-6:
                    continue
                if total > 0:
                    entries += [(b, W[row, r] * w / total) for b, w in group]
                else:
                    entries.append((lead[r], W[row, r]))
            entries += [(b, W[row, 3 + j]) for j, b in enumerate(hb)]
            entries = [(b, w) for b, w in entries if w > 1e-5]
            if len(entries) > 4:                         # body bones that move as one: onto the heaviest of them
                merged = {}
                for b, w in entries:
                    key = ("body", reps[b]) if b < nb and sd.role[b] == 0 else ("own", b)
                    merged.setdefault(key, []).append((b, w))
                entries = [(max(group, key=lambda e: e[1])[0], sum(w for _b, w in group)) for group in merged.values()]
                merges += 1
            pe.set_weight(model.vertices[i], entries, pmx)
        moved = (np.abs(W[:, :3] - W_old).sum(1) + W[:, 3:].sum(1)) / 2
        rep.update({"helper_bones": [model.bones[b].name for b in hb],
                    "helper_weight_max": [round(float(x), 3) for x in W[:, 3:].max(0)],
                    "helper_vertices": [int((W[:, 3 + j] > 0.01).sum()) for j in range(len(hb))],
                    "weight_moved_mean": round(float(moved.mean()), 4), "body_bones_merged": merges})
        report["sides"][side] = rep
    if len(model.bones) - nb != 2 * len(cfg):
        raise SystemExit("helper count mismatch")
    lines = (model.comment or "").replace("\r\n", "\n").split("\n")
    lines.append("%s (%s; pcf_upperarm / pcf_clavicle poses, %d + %d vertices, scripts/vindictus/pmx_shoulder.py)" % (
        MARK, helpers, report["sides"]["l"]["zone"], report["sides"]["r"]["zone"]))
    model.comment = "\r\n".join(lines)
    return report


def shoulder_file(pmx_in, pmx_out, xps_path, helpers=DEFAULT_HELPERS, data_dir=GAME_DATA, log=print,
                  weight_smooth=None):
    pmx = bust_physics.load_pmx_module()
    model = pmx.load(pmx_in)
    if MARK in (model.comment or ""):
        raise SystemExit("already done: " + pmx_in)
    report = shoulder(model, pmx, pe.read_xps(xps_path), helpers, data_dir, log, weight_smooth)
    tmp = pmx_out + ".shoulder.tmp"
    pmx.save(tmp, model)
    os.replace(tmp, pmx_out)
    report.update({"pmx": pmx_in, "out": pmx_out, "xps": xps_path})
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pmx_in")
    ap.add_argument("pmx_out")
    ap.add_argument("--xps", required=True, help="the XPS export_pmx.py made this PMX from")
    ap.add_argument("--helpers", default=DEFAULT_HELPERS, help="kind:ratio:offset,... (default %(default)s)")
    ap.add_argument("--game-data", default=GAME_DATA)
    ap.add_argument("--weight-smooth", type=float, default=None,
                    help="pull towards the neighbours' weights (default %s)" % WEIGHT_SMOOTH)
    ap.add_argument("--report")
    args = ap.parse_args()
    t0 = time.time()
    report = shoulder_file(args.pmx_in, args.pmx_out, args.xps, args.helpers, args.game_data,
                           weight_smooth=args.weight_smooth)
    report["seconds"] = round(time.time() - t0, 1)
    print("wrote %s (%.0f s)" % (args.pmx_out, time.time() - t0))
    if args.report:
        json.dump(report, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
