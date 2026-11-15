# Set material flags on a PMX in place: double-sided (thin crystal cards / one-sided plates seen from behind) and the
# toon (shared toon index) for materials matching a regex.
#   python mat_flags.py <pmx> [--double regex] [--toon regex --toon-index 1]
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pmx")
ap.add_argument("--double", default="")
ap.add_argument("--toon", default="")
ap.add_argument("--toon-index", type=int, default=1)
a = ap.parse_args()
M = L.load(os.path.abspath(a.pmx))
nd = nt = 0
for m in M.materials:
    if a.double and re.search(a.double, m.name):
        m.is_double_sided = True
        nd += 1
    if a.toon and re.search(a.toon, m.name):
        m.is_shared_toon_texture, m.toon_texture = True, a.toon_index
        nt += 1
L.save(M, os.path.abspath(a.pmx))
print("double-sided", nd, "toon", nt)
