"""Videos for the VMDs export_roe_motions.py wrote: per clip a compare video (game vs PMX + VMD, no physics) and a
physics preview (textured, MMD-like physics, camera fitted to the whole motion), joined per group with labels.

  python render_roe_motion_videos.py a08                  every VMD in the a08 motion folder
  python render_roe_motion_videos.py a08 --clips skill_01 one clip (its part videos; the joined ones are rebuilt
                                                          from whatever parts exist)
  options: --stem  --pmx  --out  (as for export_roe_motions.py)  --fbx <game fbx>
           --what compare | physics | both (default)    --keep-blend (keep the physics scenes, ~30 MB each)

Writes, inside the motion folder <out>:
  对照_游戏原版vsPMX_展示动作<n>段.mp4 / preview_展示动作<n>段_MMD物理.mp4             showcase clips
  battle\\对照_游戏原版vsPMX_战斗动作<n>段.mp4 / battle\\preview_战斗动作<n>段_MMD物理.mp4   battle clips
  _clips\\videos\\compare_<clip>.mp4, physics_<clip>.mp4                                    one clip each

The compare video needs the decoded clip (_clips\\<clip>.json, written by export_roe_motions.py) and the game FBX
(D:\\roe_exports\\<id>\\...\\pc_<id>_hd.fbx); the physics preview only needs the PMX and the VMD and goes through the
repo's render_pmx_dance.py, then roe_refit_camera.py.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roe_motion_common import (BLENDER, FFMPEG, GROUPS, HERE, LABELS, clip_sort_key, default_out,  # noqa: E402
                               find_pmx, game_fbx, grep, run)

FONT = "C\\:/Windows/Fonts/msyh.ttc"


def join(parts, size, dst):
    """Concatenate (path, clip) parts, scaled into one frame size, each labelled with its clip."""
    inputs, filters = [], []
    w, h = size
    for k, (path, clip) in enumerate(parts):
        inputs += ["-i", path]
        title = LABELS.get(clip, clip)
        filters.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=0x53545c,"
            "setsar=1,fps=30,drawtext=fontfile='%s':text='%d/%d  %s  %s':fontcolor=white:fontsize=%d:"
            "box=1:boxcolor=black@0.45:boxborderw=8:x=16:y=h-th-24[v%d]"
            % (k, w, h, w, h, FONT, k + 1, len(parts), title, clip, max(22, h // 30), k))
    filters.append("".join("[v%d]" % k for k in range(len(parts))) + "concat=n=%d:v=1:a=0[out]" % len(parts))
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", dst], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--stem")
    ap.add_argument("--pmx")
    ap.add_argument("--out")
    ap.add_argument("--fbx")
    ap.add_argument("--clips")
    ap.add_argument("--what", default="both", choices=["compare", "physics", "both"])
    ap.add_argument("--keep-blend", action="store_true")
    args = ap.parse_args()
    stem = args.stem or "pc_%s_hd" % args.id
    pmx, character = (args.pmx, None) if args.pmx else find_pmx(stem)
    if not pmx or not os.path.isfile(pmx):
        sys.exit("PMX not found for %s (pass --pmx)" % stem)
    out = args.out or default_out(stem, character or os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(pmx)))))
    work = os.path.join(out, "_clips")
    vids = os.path.join(work, "videos")
    os.makedirs(vids, exist_ok=True)
    fbx = args.fbx or game_fbx(args.id)
    wanted = set(args.clips.split(",")) if args.clips else None
    found = []                                   # (group, clip, vmd)
    for group, folder in (("showcase", out), ("battle", os.path.join(out, "battle"))):
        for vmd in sorted(glob.glob(os.path.join(folder, stem + "_*.vmd"))):
            clip = os.path.basename(vmd)[len(stem) + 1:-4]
            found.append((group, clip, vmd))
    if not found:
        sys.exit("no %s_*.vmd in %s - run export_roe_motions.py first" % (stem, out))
    t0 = time.time()
    for group, clip, vmd in sorted(found, key=lambda x: (x[0] != "showcase", clip_sort_key(x[1]))):
        if wanted and clip not in wanted:
            continue
        if args.what in ("compare", "both"):
            js = os.path.join(work, clip + ".json")
            if not os.path.isfile(js) or not fbx:
                print("compare %-10s skipped: %s" % (clip, "no decoded clip (run export_roe_motions.py)" if not os.path.isfile(js)
                                                     else "no game FBX (pass --fbx)"))
            else:
                lf = os.path.join(vids, "compare_%s.log" % clip)
                code = run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "roe_vmd_compare.py"), "--",
                            js, pmx, vmd, fbx, os.path.join(vids, "compare_%s.mp4" % clip)], lf)
                print("compare %-10s exit %d  (%d s)" % (clip, code, time.time() - t0), flush=True)
        if args.what in ("physics", "both"):
            mp4 = os.path.join(vids, "physics_%s.mp4" % clip)
            blend = mp4[:-4] + ".blend"
            lf = os.path.join(vids, "physics_%s.log" % clip)
            code = run([BLENDER, "-b", "--python", os.path.join(HERE, "render_pmx_dance.py"), "--", pmx, vmd, "-", mp4,
                        "0", "full", "mmd"], lf)
            if os.path.isfile(blend):
                code = run([BLENDER, "-b", blend, "--python", os.path.join(HERE, "roe_refit_camera.py"), "--", mp4],
                           os.path.join(vids, "refit_%s.log" % clip))
                if not args.keep_blend:
                    os.remove(blend)
            physics = grep(lf, "physics: ")
            print("physics %-10s exit %d  (%d s)  %s" % (clip, code, time.time() - t0, physics[-1].strip() if physics else ""),
                  flush=True)
    for group in ("showcase", "battle"):
        clips = sorted({c for g, c, _v in found if g == group}, key=clip_sort_key)
        if not clips:
            continue
        folder = out if group == "showcase" else os.path.join(out, "battle")
        for prefix, size, name in (("compare", (1280, 720), "对照_游戏原版vsPMX_%s%d段.mp4"),
                                   ("physics", (720, 1080), "preview_%s%d段_MMD物理.mp4")):
            parts = [(os.path.join(vids, "%s_%s.mp4" % (prefix, c)), c) for c in clips]
            parts = [p for p in parts if os.path.isfile(p[0])]
            if parts:
                dst = os.path.join(folder, name % (GROUPS[group], len(parts)))
                join(parts, size, dst)
                print("joined", dst)
    print("done in %d s" % (time.time() - t0))


if __name__ == "__main__":
    main()
