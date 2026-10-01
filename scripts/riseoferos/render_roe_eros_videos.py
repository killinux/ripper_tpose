"""Videos for the H scenes export_roe_eros.py wrote: per part a compare video (both actors as in the game vs both
PMX playing their VMDs, no physics) and a physics preview (textured, MMD-like physics), joined per scene.

  python render_roe_eros_videos.py g04                     every scene folder of the outfit (g04: eros07)
  python render_roe_eros_videos.py a08 --clips eros15_p1   one part (the joined videos are rebuilt from the parts)
  options: --out <dir> (as for export_roe_eros.py)  --what compare | physics | both  --keep-blend

Writes, inside each scene folder <out>\\<scene>:
  对照_游戏原版vsPMX_<scene>_<n>段.mp4 / preview_<scene>_<n>段_MMD物理.mp4    the parts in order, labelled
  _clips\\videos\\compare_<part>.mp4, physics_<part>.mp4                     one part each
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_roe_eros import part_key  # noqa: E402
from render_roe_motion_videos import FONT  # noqa: E402
from roe_motion_common import BLENDER, FFMPEG, HERE, body_fbx, default_out, find_pmx, run  # noqa: E402


def part_label(part):
    m = re.match(r"eros\d+_([pt])(\d+)(?:_(in|out))?$", part)
    if not m:
        return part
    if m.group(1) == "p":
        return "阶段 %s" % m.group(2)
    return "过渡 %s%s" % (m.group(2), {"in": " 进", "out": " 出", None: ""}[m.group(3)])


def join(parts, size, dst):
    inputs, filters = [], []
    w, h = size
    for k, (path, part) in enumerate(parts):
        inputs += ["-i", path]
        filters.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=0x53545c,"
            "setsar=1,fps=30,drawtext=fontfile='%s':text='%d/%d  %s  %s':fontcolor=white:fontsize=%d:"
            "box=1:boxcolor=black@0.45:boxborderw=8:x=16:y=h-th-24[v%d]"
            % (k, w, h, w, h, FONT, k + 1, len(parts), part_label(part), part, max(22, h // 30), k))
    filters.append("".join("[v%d]" % k for k in range(len(parts))) + "concat=n=%d:v=1:a=0[out]" % len(parts))
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", dst], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--out")
    ap.add_argument("--clips")
    ap.add_argument("--what", default="both", choices=["compare", "physics", "both"])
    ap.add_argument("--keep-blend", action="store_true")
    args = ap.parse_args()
    _pmx, character = find_pmx("pc_%s_hd" % args.id)
    base = args.out or default_out("pc_%s_hd" % args.id, character or "Luf")
    scenes = sorted(d for d in glob.glob(os.path.join(base, "eros*")) if os.path.isdir(d))
    if not scenes:
        sys.exit("no eros* scene folder in %s - run export_roe_eros.py first" % base)
    wanted = set(args.clips.split(",")) if args.clips else None
    t0 = time.time()
    for folder in scenes:
        scene = os.path.basename(folder)
        work = os.path.join(folder, "_clips")
        vids = os.path.join(work, "videos")
        os.makedirs(vids, exist_ok=True)
        parts = sorted({os.path.basename(p)[:-len(".f.json")] for p in glob.glob(os.path.join(work, "*.f.json"))},
                       key=part_key)
        summary = open(os.path.join(work, "export_summary.txt"), encoding="utf-8").read()
        her_pmx = re.search(r"her PMX (.+)", summary).group(1).strip()
        his_pmx = re.search(r"his PMX (.+)", summary).group(1).strip()
        bodies = [os.path.basename(os.path.dirname(her_pmx)).replace("_bs", ""), "pc_a00_nk"]
        fbx = [body_fbx(b) for b in bodies]
        for part in parts:
            if wanted and part not in wanted:
                continue
            actors = []
            for a, pmx, f in zip("fm", (her_pmx, his_pmx), fbx):
                vmd = os.path.join(folder, "%s_%s.vmd" % (os.path.splitext(os.path.basename(pmx))[0], part))
                js = os.path.join(work, "%s.%s.json" % (part, a))
                if os.path.isfile(vmd) and os.path.isfile(js):
                    actors.append((js, pmx, vmd, f))
            if not actors:
                continue
            if args.what in ("compare", "both"):
                if all(a[3] for a in actors):
                    cmd = [BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "roe_vmd_compare.py"), "--"]
                    for act in actors:
                        cmd += list(act)
                    cmd += [os.path.join(vids, "compare_%s.mp4" % part), "--gap", "1.1"]
                    code = run(cmd, os.path.join(vids, "compare_%s.log" % part))
                    print("compare %-14s exit %d  (%d s)" % (part, code, time.time() - t0), flush=True)
                else:
                    print("compare %-14s skipped: no game FBX for %s" % (part, bodies), flush=True)
            if args.what in ("physics", "both"):
                mp4 = os.path.join(vids, "physics_%s.mp4" % part)
                cmd = [BLENDER, "-b", "--python", os.path.join(HERE, "roe_eros_preview.py"), "--", mp4]
                for _js, pmx, vmd, _f in actors:
                    cmd += [pmx, vmd]
                code = run(cmd, os.path.join(vids, "physics_%s.log" % part))
                blend = mp4[:-4] + ".blend"
                if os.path.isfile(blend) and not args.keep_blend:
                    os.remove(blend)
                print("physics %-14s exit %d  (%d s)" % (part, code, time.time() - t0), flush=True)
        for prefix, name in (("compare", "对照_游戏原版vsPMX_%s_%d段.mp4"), ("physics", "preview_%s_%d段_MMD物理.mp4")):
            got = [(os.path.join(vids, "%s_%s.mp4" % (prefix, p)), p) for p in parts]
            got = [g for g in got if os.path.isfile(g[0])]
            if got:
                dst = os.path.join(folder, name % (scene, len(got)))
                join(got, (1280, 720), dst)
                print("joined", dst)
    print("done in %d s" % (time.time() - t0))


if __name__ == "__main__":
    main()
