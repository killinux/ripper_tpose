# -*- coding: utf-8 -*-
"""Bone chains for hair that has none, so the PMX can give it physics (Blender, before the MMD conversion).

Some AION2 NPCs ship their long hair without hair bones: Yustiel's 31,000-vertex hair is skinned to the head, and its
long part to Spine..Spine2, the pelvis and the clavicles (the game moves it with the body, maybe a cloth simulation
on top, which a PSK does not carry).  In MMD that hair follows the torso and never swings.  Player hairstyles and
Leda / Siel have Hair_* chains of their own and are left alone.

rig() lays N strands x M segments over the hanging part, under the head bone:
  - the hanging part = the weight the hair has on body bones other than the head and the neck (the game's own split:
    the scalp stays on the head);
  - strands are spread evenly by azimuth around the head (0 = straight back) over the width the long hair covers
    below the shoulders (Yustiel: -55..55 degrees, 7 strands); each strand's joints are the centroids of its hair at
    evenly spaced heights from the nape to its tip (about SEGMENT_CM apart), smoothed;
  - every hanging vertex gives its body weight to the two nearest strands (linear in azimuth) x the two nearest
    segments (linear between the bones' middles); the head weight stays; short hair lying on the shoulders
    (beyond FADE_DEG) keeps its clavicle weight, with a smooth hand-over in between;
  - at most 4 bones per vertex (PMX), the smallest dropped and the rest scaled back to the same total.
The bones are named Hair_Gen_<strand>_<nn> (strands A.. from her right to her left), so Convert_to_MMD5 keeps them
and mmd_cloth_physics gives them its hair preset.
"""
import math
import re

import bpy
import numpy as np
from mathutils import Vector

SEGMENT_CM = 8.0
STRANDS = 7
FADE_DEG = (55.0, 75.0)          # full chain weight inside, the original weights outside
KEEP = re.compile(r"(^|\s|-)(Head|Neck)$|^Face_Root$|^b_[LRC]_", re.IGNORECASE)
BIPED = re.compile(r"^Bip\d+[ -]")


def needs_chains(arm, mesh):
    """True when every bone the mesh is skinned to is a Biped bone (no hair / cloth chain of its own)."""
    names = {vg.index: vg.name for vg in mesh.vertex_groups}
    used = set()
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                used.add(names.get(g.group, ""))
    return bool(used) and all(BIPED.match(n) for n in used if n in arm.data.bones)


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def rig(arm, mesh, head_name, strands=STRANDS, segment=SEGMENT_CM, fade=FADE_DEG, prefix="Hair_Gen", log=print):
    """Build the chains and move the hanging weight onto them.  Units = the armature's (AION2 .blend: cm).
    Returns a report dict."""
    bones = arm.data.bones
    head_bone = bones[head_name]
    to_world = arm.matrix_world
    hp = to_world @ head_bone.head_local
    groups = {vg.index: vg.name for vg in mesh.vertex_groups}
    n = len(mesh.data.vertices)
    co = np.empty(n * 3)
    mesh.data.vertices.foreach_get("co", co)
    mw = np.array(mesh.matrix_world)
    co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    weights = [{groups[g.group]: g.weight for g in v.groups if g.weight > 0.0} for v in mesh.data.vertices]
    body = np.array([sum(w for k, w in d.items() if not KEEP.search(k)) for d in weights])
    az = np.degrees(np.arctan2(co[:, 0] - hp.x, co[:, 1] - hp.y))      # 0 = back (+Y), + = her left (+X)
    hanging = body > 0.01
    if hanging.sum() < 50:
        return {"skipped": "no hair weighted to the body"}
    # the width of the long hair: azimuths of the hanging hair well below the clavicles
    clav_z = max((to_world @ b.head_local).z for b in bones if re.search(r"Clavicle$", b.name)) \
        if any(re.search(r"Clavicle$", b.name) for b in bones) else hp.z - 12.0
    long_hair = hanging & (co[:, 2] < clav_z - 5.0)
    if long_hair.sum() < 50:
        return {"skipped": "the hair does not hang below the shoulders"}
    lo, hi = np.percentile(az[long_hair], [3, 97])
    lo, hi = max(lo, -fade[0]), min(hi, fade[0])
    centres = np.linspace(lo, hi, strands)
    spacing = (hi - lo) / max(1, strands - 1)
    share = 1.0 - _smoothstep(fade[0], fade[1], np.abs(az))            # 1 inside, 0 on the shoulders
    chain_w = body * share

    # joints per strand
    plans = []
    for s, theta in enumerate(centres):
        near = hanging & (np.abs(az - theta) < spacing) & (share > 0.5)
        if near.sum() < 20:
            continue
        z = co[near, 2]
        z_top = min(float(np.percentile(z, 99)), hp.z - 1.0)
        z_bot = float(np.percentile(z, 1))
        length = z_top - z_bot
        if length < segment:
            continue
        m = max(2, int(round(length / segment)))
        joints = []
        band = length / m * 0.75
        g = np.exp(-0.5 * ((az[near] - theta) / (spacing * 0.6)) ** 2)
        for k in range(m + 1):
            zk = z_top - length * k / m
            sel = np.abs(z - zk) < band
            if sel.sum() < 5:
                sel = np.abs(z - zk) < band * 2
            w = g[sel]
            p = (co[near][sel] * w[:, None]).sum(0) / max(w.sum(), 1e-9) if sel.any() else None
            joints.append(np.array([p[0], p[1], zk]) if p is not None else None)
        for k in range(len(joints)):                    # holes: carry the previous direction on
            if joints[k] is None:
                joints[k] = joints[k - 1] + (joints[k - 1] - joints[k - 2]) if k >= 2 else np.array([hp.x, hp.y, z_top])
        js = np.array(joints)
        for _ in range(2):                              # smooth the interior joints
            js[1:-1] = 0.25 * js[:-2] + 0.5 * js[1:-1] + 0.25 * js[2:]
        plans.append((s, theta, js))
    if not plans:
        return {"skipped": "no strand had enough hair"}

    letters = "ABCDEFGHIJKLMNOP"
    to_arm = to_world.inverted()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    names = []                                          # per plan: bone names top -> tip
    for s, _theta, js in plans:
        parent = eb[head_name]
        chain = []
        for k in range(len(js) - 1):
            name = "%s_%s_%02d" % (prefix, letters[s], k + 1)
            b = eb.new(name)
            b.head = to_arm @ Vector(js[k])
            b.tail = to_arm @ Vector(js[k + 1])
            b.parent = parent
            b.use_connect = k > 0
            b.use_deform = True
            parent = b
            chain.append(name)
        names.append(chain)
    bpy.ops.object.mode_set(mode="OBJECT")

    # weights: two strands (azimuth) x two segments (height)
    thetas = np.array([p[1] for p in plans])
    mids = [0.5 * (js[:-1, 2] + js[1:, 2]) for _s, _t, js in plans]      # each bone's middle height
    for name in {nm for chain in names for nm in chain}:
        if mesh.vertex_groups.get(name) is None:
            mesh.vertex_groups.new(name=name)
    vg = {g.name: g for g in mesh.vertex_groups}
    moved = 0
    for i in np.nonzero(chain_w > 1e-4)[0]:
        d = weights[i]
        wc = chain_w[i]
        keep_body = 1.0 - share[i]
        new = {k: (w if KEEP.search(k) else w * keep_body) for k, w in d.items()}
        t = np.interp(az[i], thetas, np.arange(len(thetas)))
        s0 = int(math.floor(t))
        s1 = min(s0 + 1, len(thetas) - 1)
        f = t - s0
        for sidx, ws in ((s0, 1.0 - f), (s1, f)):
            if ws <= 1e-4:
                continue
            m = mids[sidx]
            # heights go down the chain: np.interp needs increasing x
            u = np.interp(-co[i, 2], -m, np.arange(len(m)))
            k0 = int(math.floor(u))
            k1 = min(k0 + 1, len(m) - 1)
            g = u - k0
            for kidx, wk in ((k0, 1.0 - g), (k1, g)):
                if wk > 1e-4:
                    bn = names[sidx][kidx]
                    new[bn] = new.get(bn, 0.0) + wc * ws * wk
        total = sum(d.values())
        items = sorted(new.items(), key=lambda kv: -kv[1])[:4]
        scale = total / max(sum(w for _k, w in items), 1e-9)
        for k in d:
            vg[k].remove([int(i)])
        for k, w in items:
            if w * scale > 1e-5:
                vg[k].add([int(i)], w * scale, "REPLACE")
        moved += 1
    report = {"strands": len(plans), "segments": [len(c) for c in names], "azimuth_deg": [round(lo, 1), round(hi, 1)],
              "vertices": int(moved), "bones": [c[0] + ".." + c[-1][-2:] for c in names]}
    log("[aion2 hair] %s: %d strands x %s segments, %d vertices moved onto them"
        % (mesh.name, len(plans), report["segments"], moved))
    return report
