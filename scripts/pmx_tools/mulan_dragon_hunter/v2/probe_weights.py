# For each material matching a substring: which bones carry its weights (share of total weight), with the bone's
# position (cm) and parent.  python probe_weights.py model.pmx substring [top]
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

M = L.load(sys.argv[1])
sub = sys.argv[2]
top = int(sys.argv[3]) if len(sys.argv) > 3 else 12
U = L.UNIT_CM
for i, m in enumerate(M.materials):
    if sub not in m.name:
        continue
    acc = collections.Counter()
    for v in L.mat_vertices(M, i):
        for b, w in L.weights_of(M, v):
            if w > 0:
                acc[b] += w
    tot = sum(acc.values())
    print("== %d %s  (%d bones)" % (i, m.name, len(acc)))
    for b, w in acc.most_common(top):
        bo = M.bones[b]
        par = M.bones[bo.parent].name if bo.parent is not None and bo.parent >= 0 else "-"
        p = np.array(bo.location) * U
        print("   %5.1f%%  %-28s (%6.1f %6.1f %6.1f)  parent %s" % (100 * w / tot, bo.name, p[0], p[1], p[2], par))
