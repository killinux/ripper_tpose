"""Point the fixed axes of the twist bones (腕捩 / 手捩) along the arm again, in an existing PMX.

Convert_to_MMD5 (convert/semistandard.py, _fix_twist_axis) stores the axis as Blender (x, z, -y), but mmd_tools
keeps ``mmd_bone.fixed_axis`` as Blender (x, z, y) - the PMX frame - so every exported twist axis has its front /
back component reversed: Vindictus Fiona's 腕捩 and 手捩 point 3.2 deg off the arm, more on a model whose arms come
forward in the rest pose.  MMD plays a VMD's rotations as they are, so a dance hardly shows it; posing the twist by
hand in MMD turns the arm about the wrong line.  This sets each axis to the joint line (腕 -> ひじ, ひじ -> 手首).
The add-on writes (x, z, y) since its build of 2026-10-06 evening ("twist-axis+inner-colliders"): models converted
after that need no fix; PMX exported before still do.

    python pmx_twist_axes.py in.pmx out.pmx
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pmx_nude_switch import pmx_module  # noqa: E402

LINES = (("腕捩", "腕", "ひじ"), ("手捩", "ひじ", "手首"))


def fix(model):
    idx = {b.name: i for i, b in enumerate(model.bones)}
    out = []
    for side in ("左", "右"):
        for twist, a, b in LINES:
            if not all(side + n in idx for n in (twist, a, b)):
                continue
            bone = model.bones[idx[side + twist]]
            if bone.axis is None or not any(bone.axis):
                continue
            line = np.array(model.bones[idx[side + b]].location) - np.array(model.bones[idx[side + a]].location)
            line /= np.linalg.norm(line)
            old = np.array(bone.axis, float)
            angle = math.degrees(math.acos(min(1.0, abs(old @ line) / np.linalg.norm(old))))
            bone.axis = [float(x) for x in line]
            out.append((side + twist, angle))
    return out


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1:]
    if os.path.abspath(src) == os.path.abspath(dst):
        raise SystemExit("refusing to overwrite the input; write a new file")
    pmx = pmx_module()
    model = pmx.load(src)
    for name, angle in fix(model):
        print("%s: axis was %.2f deg off the joint line - now along it" % (name, angle))
    src_dir, out_dir = os.path.dirname(os.path.abspath(src)), os.path.dirname(os.path.abspath(dst))
    for texture in model.textures:
        local = os.path.join(out_dir, os.path.relpath(texture.path, src_dir))
        if os.path.exists(local):
            texture.path = local
    pmx.save(dst, model, add_uv_count=model.header.additional_uvs)
    print("wrote", dst)


if __name__ == "__main__":
    main()
