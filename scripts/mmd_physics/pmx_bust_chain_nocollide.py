"""Chains hung on a breast body collide with nothing again (collision mask 0), as in the archived PMX.

Why (g05, 10-18): cloth_collision_pmx.py gave every dynamic body except the breasts the collisions it can take, so
the chest ribbons (Riband_L/R_01..03, jointed to Bip001 chest_L02 / R02) started colliding with the arms and torso.
In the gesture dance the hands pass in front of the chest, hit the ribbons, and the ribbons yank the breasts: the
fitted body poked out of the chest pieces in spikes (60 vertices, 11 mm) even after pmx_body_follows_cups.py.
Tried and rejected: letting them collide with the legs only - in 八方来才 the light bustB pendant still went through
the raised thigh (the archived PMX does that too) and the other cloth got worse.  Only chains whose joint chain ends on
a SWINGING breast body (mode 1 / 2) change; a chain on a bone-following chest body is left alone.
    python pmx_bust_chain_nocollide.py in.pmx out.pmx [--bust REGEX]   (default: cloth_collision_pmx's breast names)"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_collision_pmx as cc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--bust", default=cc.DEFAULTS["bust"], help="regex of the breast bodies' bones (case-insensitive)")
args = ap.parse_args()
pmx = cc.load_pmx_module(cc.find_pmx_module())
m = pmx.load(args.src)
names = [b.name for b in m.bones]
bust_re = re.compile(args.bust, re.I)
bust = {i for i, r in enumerate(m.rigids) if r.mode in (1, 2) and r.bone is not None and r.bone >= 0
        and (bust_re.search(names[r.bone]) or bust_re.search(r.name))}
hung = {}                                          # dynamic body -> the body its chain joint hangs it on
for j in m.joints:
    if j.dest_rigid is not None and j.dest_rigid >= 0 and j.src_rigid is not None and j.src_rigid >= 0:
        hung.setdefault(j.dest_rigid, j.src_rigid)
changed = []
for i, r in enumerate(m.rigids):
    if r.mode == 0 or i in bust:
        continue
    k, seen = i, set()
    while k in hung and k not in seen:              # up the chain to the first body that is not dynamic
        seen.add(k)
        k = hung[k]
        if k in bust:
            break
    if k in bust:
        changed.append("%s (group %d, mask %d -> 0)" % (r.name, r.collision_group_number, r.collision_group_mask))
        r.collision_group_mask = 0
for line in changed:
    print("  " + line)
pmx.save(args.out, m, add_uv_count=m.header.additional_uvs)
print("%d bodies hung on the breasts collide with nothing; wrote %s" % (len(changed), args.out))
