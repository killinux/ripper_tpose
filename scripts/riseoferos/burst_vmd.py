"""爆衣 keys as a VMD, from the command line - the 爆衣 add-on's own code (scripts/blender_addons/clothes_burst/vmd.py,
pure Python, no Blender needed), for a PMX made by the add-on or by burst_pmx_blender.py: a VMD with only these morph
keys (load it in MMD on top of any motion), or the keys added to a motion's VMD.

  python burst_vmd.py <out.vmd> [--start 120] [--slow 1.0] [--style SHARDS|VANISH] [--vanish-frames 1]
                      [--no-fade] [--merge <motion.vmd>] [--model <name>]

碎片飞散 (SHARDS): at --start the outfit is hidden (衣服非表示_材質) and its fragments shown (爆衣碎片_材質), they fly
off in 8 frames (爆衣), fall in 24 from frame 6 (爆衣落下) and fade out frames 26-40; the body is swapped in frames
0-2 (裸体形状).  直接消失 (VANISH): the outfit fades out in --vanish-frames, then the body is swapped.  Frames at 30 fps
x --slow.  --merge keeps everything in the motion (bones, its other morphs, camera ...) and replaces its keys of these
morphs.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender_addons",
                                                "clothes_burst")))
import vmd  # noqa: E402  (the add-on's vmd.py: no bpy in it)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--start", type=int, default=vmd.DEFAULTS["start"], help="frame where the outfit bursts")
    ap.add_argument("--slow", type=float, default=vmd.DEFAULTS["slow"], help="stretch the timing (1.5 = slower)")
    ap.add_argument("--style", choices=("SHARDS", "VANISH"), default="SHARDS")
    ap.add_argument("--vanish-frames", type=int, default=vmd.DEFAULTS["vanish_frames"])
    ap.add_argument("--no-fade", action="store_true", help="the fragments stay on the floor")
    ap.add_argument("--merge", help="a motion's VMD to add the keys to")
    ap.add_argument("--model", default="", help="model name written in a morph-only VMD")
    a = ap.parse_args()
    if a.start < 1:
        ap.error("--start must be at least 1 (the switch is keyed on the frame before)")
    fade_start = vmd.DEFAULTS["fade_start"]
    keys = vmd.burst_keys(start=a.start, slow=a.slow, shards=a.style == "SHARDS", vanish_frames=a.vanish_frames,
                          fade_start=fade_start, fade_end=fade_start if a.no_fade else vmd.DEFAULTS["fade_end"])
    if a.merge:
        dropped = vmd.merge(a.merge, a.out, keys)
        print("BURST_VMD=%s (merged into %s, %d keys added, %d replaced)" % (a.out, a.merge, len(keys), dropped))
    else:
        vmd.write_morph_vmd(a.out, keys, a.model)
        print("BURST_VMD=%s (%d morph keys from frame %d)" % (a.out, len(keys), a.start))


if __name__ == "__main__":
    sys.exit(main())
