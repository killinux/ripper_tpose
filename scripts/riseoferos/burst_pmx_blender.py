"""爆衣 PMX from a PMX, through the 爆衣 add-on's MMD code (scripts/blender_addons/clothes_burst: mmd.py,
shards.py, vmd.py) - the same code the add-on's panel runs by hand: the PMX imported with mmd_tools, the outfit (the
materials 衣服非表示_材質 hides - a full version from complete_nude.py has that morph - or --outfit) given the burst,
the model exported again with mmd_tools.

  碎片飞散 (default)  the outfit's fragment copy + 爆衣 / 爆衣落下 / 爆衣碎片_材質
  直接消失 (--style VANISH)  only 衣服非表示_材質; the VMD fades the outfit out in --vanish-frames
With 裸体形状 on the body (a full version) the body is also put in twice - dressed and nude - and 裸体形状 becomes the
material morph that swaps them (--no-swap keeps the one body with its vertex morph).  The nude copy's normals come
from the nude version's PMX (--nude-pmx; by default <...>_nude/<...>_nude.pmx beside a <...>_full/<...>_full.pmx),
else from Blender's turned custom normals (a08: 94 vertices at the nails more than 5 degrees off).

  blender -b --factory-startup --python burst_pmx_blender.py -- <in.pmx> <out.pmx>
      [--style SHARDS|VANISH] [--no-swap] [--nude-pmx <pmx>|none] [--outfit mat1,mat2] [--size 0.1] [--seed 1]
      [--vmd <out.vmd> [--start 120] [--slow 1.0] [--vanish-frames 1] [--merge <motion.vmd>]]
Prints ROE_BURST_PMX=<json>.
"""
import argparse
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "blender_addons")))
from clothes_burst import mmd as cb_mmd  # noqa: E402
from clothes_burst import vmd as cb_vmd  # noqa: E402

SCALE = 0.08          # PMX units -> metres on import, x 12.5 back on export (the batch's own scale)


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("pmx")
    ap.add_argument("out")
    ap.add_argument("--style", choices=("SHARDS", "VANISH"), default="SHARDS")
    ap.add_argument("--no-swap", action="store_true")
    ap.add_argument("--nude-pmx", default="")
    ap.add_argument("--outfit", default="")
    ap.add_argument("--size", type=float, default=cb_mmd.DEFAULTS["size"])
    ap.add_argument("--seed", type=int, default=cb_mmd.DEFAULTS["seed"])
    ap.add_argument("--vmd", default="")
    ap.add_argument("--start", type=int, default=cb_vmd.DEFAULTS["start"])
    ap.add_argument("--slow", type=float, default=cb_vmd.DEFAULTS["slow"])
    ap.add_argument("--vanish-frames", type=int, default=cb_vmd.DEFAULTS["vanish_frames"])
    ap.add_argument("--merge", default="")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def main():
    a = args()
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mmd_tools.import_model(filepath=os.path.abspath(a.pmx), scale=SCALE,
                                   types={"MESH", "ARMATURE", "PHYSICS", "DISPLAY", "MORPHS"},
                                   clean_model=False, rename_bones=False, log_level="ERROR")
    root = next(o for o in bpy.data.objects if o.mmd_type == "ROOT")
    outfit = [n for n in a.outfit.split(",") if n] or cb_mmd.outfit_from_morph(root)
    if not outfit:
        raise SystemExit("no outfit: the PMX has no 衣服非表示_材質 morph - name the materials with --outfit")
    cb_mmd.set_outfit(root, outfit)
    nude = a.nude_pmx
    if not nude:
        folder, name = os.path.split(os.path.abspath(a.pmx))
        guess = os.path.join(os.path.dirname(folder), os.path.basename(folder).replace("_full", "_nude"),
                             name.replace("_full", "_nude"))
        nude = guess if "_full" in name and os.path.isfile(guess) else ""
    opts = dict(style=a.style, swap=not a.no_swap, size=a.size, seed=a.seed, scale=SCALE,
                nude_pmx="" if nude == "none" else nude)
    report = cb_mmd.make(root, outfit, opts)
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    bpy.ops.mmd_tools.export_pmx(filepath=out, scale=1.0 / SCALE, copy_textures=True, log_level="ERROR")
    report.update(pmx=out, outfit=outfit, opts=opts)
    if a.vmd:
        timing = dict(start=a.start, slow=a.slow, style=a.style, vanish_frames=a.vanish_frames)
        report["vmd"] = cb_mmd.export_vmd(os.path.abspath(a.vmd), timing, a.merge, os.path.basename(out)[:-4])
    print("ROE_BURST_PMX=" + json.dumps(report, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
