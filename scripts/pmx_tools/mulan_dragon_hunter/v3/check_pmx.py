# Structural check of a built PMX: indices in range, weights normalised, no degenerate normals, texture files there,
# material face counts add up, morph offsets point at real materials.
#   python check_pmx.py <pmx>
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2"))
import pmxlib as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
M = L.load(os.path.abspath(sys.argv[1]))
nv, nb, nm = len(M.vertices), len(M.bones), len(M.materials)
problems = []
F = np.array(M.faces, int)
if F.min() < 0 or F.max() >= nv:
    problems.append("face index out of range")
if sum(m.vertex_count for m in M.materials) != len(M.faces) * 3:
    problems.append("material face counts %d != faces %d" % (sum(m.vertex_count for m in M.materials) // 3, len(M.faces)))
bad_w = bad_b = bad_n = nan = 0
types = {}
for v in M.vertices:
    ws = L.oc.weights_of(L.pmx, v)
    types[v.weight.type] = types.get(v.weight.type, 0) + 1
    if not ws or abs(sum(x for _b, x in ws) - 1.0) > 1e-3:
        bad_w += 1
    if any(b < 0 or b >= nb for b, _x in ws):
        bad_b += 1
    n = np.array(v.normal, float)
    if not np.isfinite(n).all() or not np.isfinite(np.array(v.co, float)).all():
        nan += 1
    elif abs(np.linalg.norm(n) - 1.0) > 0.05:
        bad_n += 1
for label, k in (("vertices with weights not summing to 1", bad_w), ("vertices with a bone index out of range", bad_b),
                 ("vertices with a non-unit normal", bad_n), ("vertices with NaN", nan)):
    if k:
        problems.append("%d %s" % (k, label))
missing = [t.path for t in M.textures if not os.path.isfile(t.path)]
if missing:
    problems.append("missing textures: %s" % missing)
for m in M.materials:
    for idx, what in ((m.texture, "texture"), (m.sphere_texture, "sphere")):
        if idx >= len(M.textures):
            problems.append("material %s: %s index %d out of range" % (m.name, what, idx))
for mo in M.morphs:
    if isinstance(mo, L.pmx.MaterialMorph):
        for o in mo.offsets:
            if o.index is not None and (o.index < -1 or o.index >= nm):
                problems.append("morph %s: material %s out of range" % (mo.name, o.index))
used = np.zeros(nv, bool)
used[F.ravel()] = True
P = np.array([v.co for v in M.vertices]) * L.UNIT_CM
print("vertices %d (unused %d)  faces %d  bones %d  materials %d  morphs %d  rigids %d  joints %d" % (
    nv, int((~used).sum()), len(M.faces), nb, nm, len(M.morphs), len(M.rigids), len(M.joints)))
print("weight types:", types)
print("bbox cm:", P[used].min(0).round(1), P[used].max(0).round(1))
print("double sided:", [m.name for m in M.materials if m.is_double_sided and m.name.startswith("v11_")])
print("PROBLEMS:" if problems else "OK: no problems")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
