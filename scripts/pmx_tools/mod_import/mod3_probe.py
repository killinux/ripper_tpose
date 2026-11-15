# Run under Blender's Python (needs mathutils):  blender -b --python mod3_probe.py -- <file.mod3>
import os
import sys

import numpy as np

R = r"E:\tools\mod_importers\mod3_src\Mod3-MHW-Importer-master"
for sub in ("mod3", "common", "mrl3"):
    sys.path.insert(0, os.path.join(R, sub))
import FileLike as FL  # noqa: E402
import Mod3  # noqa: E402
from mathutils import Matrix  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
p = argv[0]
model = Mod3.Mod3()
model.marshall(FL.FileLike(open(p, "rb").read()))
model.filterLOD()
arm = model.prepareArmature()
print("bones", len(arm))
b0 = arm[0]
print("bone keys", list(b0.keys()))
print("custom", b0["CustomProperties"])


def lmat(bone):
    return Matrix([[bone["LMatCol%d" % c][r] for c in range(4)] for r in range(4)])


world = {}


def world_of(i):
    if i in world:
        return world[i]
    b = arm[i]
    m = lmat(b)
    pid = b["parentId"]
    world[i] = m if pid == 255 or pid >= len(arm) else world_of(pid) @ m
    return world[i]


for i, b in enumerate(arm):
    w = world_of(i)
    t = w.to_translation()
    print("bone %3d parent %3d func %3d pos (%7.2f %7.2f %7.2f) %s" % (i, b["parentId"], b["CustomProperties"].get("boneFunction", -1), t.x, t.y, t.z,
                                                                   {k: v for k, v in b["CustomProperties"].items() if k != "boneFunction"}))
print("materials", model.Materials)
meshes = model.prepareMeshparts(weightSplit=False)
print("mesh parts", len(meshes))
for m in meshes:
    V = np.array(m["vertices"])
    W = m["weightGroups"]
    print(" mat %-26s lod %s block %-14s verts %5d faces %5d uvs %d wgroups %d keys %s bbox %s %s" % (
        m["properties"]["material"], m["properties"].get("lod"), m["properties"]["blockLabel"], len(V), len(m["faces"]),
        len(m["uvs"]), len(W), sorted(W.keys())[:10], V.min(0).round(1), V.max(0).round(1)))
print("PROBE_DONE")
