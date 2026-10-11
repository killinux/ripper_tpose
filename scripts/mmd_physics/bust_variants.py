r"""The six breast-physics settings of 10-06 (docs/clothes-burst-guide.md 8.11) on any PMX with MMD breast bodies, each
as a PMX for MMD and as a .blend that plays it in Blender: the default test dance, MMD-like joints, physics baked -
open the .blend and press play.

    python bust_variants.py <in.pmx> <out dir> [--only 1,2,6] [--video] [--vmd ... --wav ...] [--blender ...]

<out dir> gets:
  textures\                            the PMX's textures, copied once, so the folder stands alone
  1_现在.pmx                            the PMX as it is (its texture paths now point at the copy)
  2_乳奶模板.pmx ... 6_普通物理.pmx       scripts/mmd_physics/tune_bust_pmx.py with that setting; --hanging-scale 1, so what
                                       hangs on a breast keeps its mass and springs
  <name>.blend                         bust_scene_blender.py on that PMX: chest camera in the viewport, music, baked
  --video: <name>.mp4 + 0_六种并排.mp4   chest close-ups rendered from those scenes, 3 x 2 side by side

The settings (spring pitch / yaw / twist, limits in degrees, damping, mass of the breast body):
  1 现在         whatever the PMX carries (springs sized by gravity: the Vindictus PMX sag 6-7 degrees at rest,
                 ROE's _bustB 15)
  2 乳奶模板      no springs, +-10 / 10 / 10, damping 0.5, mass 1 (89 % of the MMD models on this machine)
  3 PmxTailor胸大 251.5 each, +-13.5 / 13.5 / 27.4, damping 0.9999, mass 6.2
  4 Q弹          150 each, +-15, damping 0.3, mass 1
  5 夸张          60 each, +-25, damping 0.2, mass 1.5
  6 普通物理      springs for a 1-degree sag, +-4 / 4 / 2, damping 0.5: the near-rigid look of Blender's own joints
                 (the 10-06 reference video), made a PMX on 10-11
Needs Python, the pmx module inside mmd_tools, Blender 3.6 with mmd_tools, ffmpeg for --video.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tune_bust_pmx import find_pmx_module, load_pmx_module  # noqa: E402

BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
DANCE = r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画"
VMD = os.path.join(DANCE, "适配瓦雷莎.vmd")
WAV = os.path.join(DANCE, "meeynara手势舞2026.2.14.WAV")
VARIANTS = [
    ("1_现在", "1 现在：按重力定弹簧", None),
    ("2_乳奶模板", "2 乳奶模板：无弹簧 ±10°",
     "--spring-pitch 0 --spring-yaw 0 --spring-twist 0 --pitch-limit 10 --yaw-limit 10 --twist-limit 10 "
     "--lin-damp 0.5 --ang-damp 0.5 --mass 1"),
    ("3_PmxTailor胸大", "3 PmxTailor 胸(大)",
     "--spring-pitch 251.5 --spring-yaw 251.5 --spring-twist 251.5 --pitch-limit 13.5 --yaw-limit 13.5 "
     "--twist-limit 27.4 --lin-damp 0.9999 --ang-damp 0.9999 --mass 6.2"),
    ("4_Q弹", "4 Q弹",
     "--spring-pitch 150 --spring-yaw 150 --spring-twist 150 --pitch-limit 15 --yaw-limit 15 --twist-limit 15 "
     "--lin-damp 0.3 --ang-damp 0.3 --mass 1"),
    ("5_夸张", "5 夸张",
     "--spring-pitch 60 --spring-yaw 60 --spring-twist 60 --pitch-limit 25 --yaw-limit 25 --twist-limit 25 "
     "--lin-damp 0.2 --ang-damp 0.2 --mass 1.5"),
    ("6_普通物理", "6 普通物理：几乎不晃",
     "--sag 1 --twist-sag 0.5 --pitch-limit 4 --yaw-limit 4 --twist-limit 2 --lin-damp 0.5 --ang-damp 0.5"),
]


def copy_base(pmx, src, out_dir, dst):
    """The PMX saved into out_dir with every texture copied beside it (same layout under out_dir; a texture outside
    the PMX's folder goes to textures\\_ext\\), so the folder stands alone.  Returns (copied, missing)."""
    model = pmx.load(src)
    src_dir = os.path.dirname(os.path.abspath(src))
    copied, missing = 0, []
    for tex in model.textures:
        path = tex.path                     # the pmx module made it absolute
        rel = os.path.relpath(path, src_dir)
        if rel.startswith(".."):
            rel = os.path.join("textures", "_ext", os.path.basename(path))
        new = os.path.join(out_dir, rel)
        if os.path.isfile(path):
            os.makedirs(os.path.dirname(new), exist_ok=True)
            if not os.path.isfile(new) or os.path.getsize(new) != os.path.getsize(path):
                shutil.copy2(path, new)
            copied += 1
        else:
            missing.append(path)
        tex.path = new
    pmx.save(dst, model, add_uv_count=model.header.additional_uvs)
    return copied, missing


def grid(out_dir, names, labels, file_name="0_六种并排.mp4"):
    """The chest videos side by side with labels (3 across from five on, else 2), audio from the first."""
    font = "C\\:/Windows/Fonts/msyhbd.ttc"
    cols = 3 if len(names) >= 5 else min(2, len(names))
    inputs, filters = [], ""
    for k, (name, label) in enumerate(zip(names, labels)):
        inputs += ["-i", os.path.join(out_dir, name + ".mp4")]
        filters += ("[%d:v]scale=720:720,drawtext=fontfile='%s':text='%s':fontsize=30:fontcolor=white:borderw=3:"
                    "bordercolor=black@0.7:x=(w-text_w)/2:y=20[v%d];" % (k, font, label, k))
    layout = "|".join("%d_%d" % ((k % cols) * 720, (k // cols) * 720) for k in range(len(names)))
    stack = "".join("[v%d]" % k for k in range(len(names)))
    out = os.path.join(out_dir, file_name)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y"] + inputs + [
        "-filter_complex", "%s%sxstack=inputs=%d:layout=%s:fill=black[v]" % (filters, stack, len(names), layout),
        "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-c:a", "aac",
        "-shortest", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pmx")
    ap.add_argument("out_dir")
    ap.add_argument("--only", default="", help="comma separated numbers of the settings to make (default all six; "
                                               "'none' = only the --add ones)")
    ap.add_argument("--add", action="append", default=[], metavar="NAME=SETTINGS",
                    help='an own setting, tune_bust_pmx.py arguments, repeatable: "2_乳奶模板_20度=--spring-pitch 0 '
                         '--spring-yaw 0 --spring-twist 0 --pitch-limit 20 --yaw-limit 20 --twist-limit 20"')
    ap.add_argument("--grid-also", default="", help="comma separated names whose .mp4 is already in <out dir>: put "
                                                    "first in the side-by-side video, not made again")
    ap.add_argument("--grid-name", default=None, help="side-by-side file (default 0_六种并排.mp4 / 0_对比.mp4)")
    ap.add_argument("--video", action="store_true", help="also render the chest close-ups and the 3 x 2 grid")
    ap.add_argument("--no-blend", action="store_true", help="PMX only")
    ap.add_argument("--vmd", default=VMD)
    ap.add_argument("--wav", default=WAV, help="music for the scenes ('-' for none)")
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--pmx-module", default=None)
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    pmx = load_pmx_module(find_pmx_module(args.pmx_module))
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    chosen = [v for v in VARIANTS if not wanted or v[0].split("_")[0] in wanted]
    for item in args.add:
        name, _, setting = item.partition("=")
        if not setting.strip():
            raise SystemExit("--add needs NAME=SETTINGS: %r" % item)
        chosen.append((name.strip(), name.strip().replace("_", " "), setting.strip()))
    base = os.path.join(out_dir, VARIANTS[0][0] + ".pmx")
    copied, missing = copy_base(pmx, args.pmx, out_dir, base)
    print("1_现在.pmx: %d textures copied, %d missing %s" % (copied, len(missing), missing[:3]), flush=True)
    tune = os.path.join(HERE, "tune_bust_pmx.py")
    for name, label, setting in chosen:
        pmx_out = os.path.join(out_dir, name + ".pmx")
        if setting:
            r = subprocess.run([sys.executable, tune, base, pmx_out, "--hanging-scale", "1"] + setting.split(),
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode:
                raise SystemExit("tune_bust_pmx failed for %s:\n%s%s" % (name, r.stdout, r.stderr))
            print("%s.pmx: %s" % (name, " ".join(l.strip() for l in r.stdout.splitlines()
                                                 if l.lstrip().startswith(("springs", "limits")))[:220]), flush=True)
        if args.no_blend:
            continue
        cmd = [args.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "bust_scene_blender.py"),
               "--", pmx_out, args.vmd, args.wav, os.path.join(out_dir, name + ".blend")]
        if args.video:
            cmd += ["--video", os.path.join(out_dir, name + ".mp4")]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = next((l for l in r.stdout.splitlines() if l.startswith("BUST_SCENE=")), "")
        if r.returncode or not line:
            raise SystemExit("bust_scene_blender failed for %s (exit %d):\n%s" % (name, r.returncode,
                                                                                  (r.stdout + r.stderr)[-2000:]))
        print("%s.blend: %s" % (name, line.split(", ", 1)[1]), flush=True)
    if args.video and not args.no_blend:
        also = [s.strip() for s in args.grid_also.split(",") if s.strip()]
        labels = {v[0]: v[1] for v in VARIANTS + chosen}
        names = also + [v[0] for v in chosen if v[0] not in also]
        missing = [n for n in names if not os.path.isfile(os.path.join(out_dir, n + ".mp4"))]
        if missing:
            raise SystemExit("no video for %s" % ", ".join(missing))
        if len(names) > 1:
            six = names == [v[0] for v in VARIANTS]
            print("grid:", grid(out_dir, names, [labels.get(n, n.replace("_", " ")) for n in names],
                                args.grid_name or ("0_六种并排.mp4" if six else "0_对比.mp4")))


if __name__ == "__main__":
    main()
