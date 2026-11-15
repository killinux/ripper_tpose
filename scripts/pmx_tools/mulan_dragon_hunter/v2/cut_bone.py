# Drop the faces of a material that hang on given bones (2 of the 3 corners' heaviest bone in the list), e.g. the
# Velkhana crown's two dangling earrings (on its side cloth bones) while the tiara (on 頭) stays.
#   python cut_bone.py <in.pmx> <out.pmx> <material> --bones "mhw_f_helm08_f153,Accessories_ear"
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("material")
ap.add_argument("--bones", required=True)
a = ap.parse_args()
M = L.load(os.path.abspath(a.src))
names = {n.strip() for n in a.bones.split(",") if n.strip()}
drop_bones = {i for i, b in enumerate(M.bones) if b.name in names}
missing = names - {M.bones[i].name for i in drop_bones}
if missing:
    raise SystemExit("bones not found: %s" % ", ".join(sorted(missing)))
mi = L.mat_index(M, a.material)
spans = L.mat_faces(M)
s, n = spans[mi]
keep, dropped = [], 0
for f in M.faces[s:s + n]:
    hits = sum(1 for v in f if L.dominant_bone(M, v) in drop_bones)
    if hits >= 2:
        dropped += 1
    else:
        keep.append(f)
M.faces[s:s + n] = keep
M.materials[mi].vertex_count = len(keep) * 3
L.save(M, os.path.abspath(a.dst))
print("material %s: %d faces dropped, %d kept" % (a.material, dropped, len(keep)))
