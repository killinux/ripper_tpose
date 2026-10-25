"""Rise of Eros: the gacha intro girl (pc_gacha01, the model of the gacha's butt-poke opening) as .blend + PMX.

    python export_gacha_model.py                       # all steps -> E:\\game_export\\RiseOfEros\\_抽奖模型
    python export_gacha_model.py --video               # + the PMX dancing the default test motion (手势舞)
    python export_gacha_model.py --out D:\\x --steps blend,pmx    # again from the work folder's FBX / material cache
    python export_gacha_model.py --dry-run             # print the commands only

Steps (--steps, default extract,hq,blend,pmx):
  extract  the bundles below -> <work>\\stage (newest of the install dir / the download cache); AssetStudioModCLI writes
           the FBX (bind pose, no animation, x100, sceneHierarchy - extract_character.ps1's arguments) and every
           texture as PNG -> <work>\\export
  hq       the game's 12 materials of the model -> <work>\\hq_cache\\j_gacha01.json + decoded textures + the XPS / PMX
           maps (hq_material_data.py with its bundle choice replaced by the list below: the model draws from four
           characters' bundles, which its id-based choice cannot find)
  blend    blender: build_gacha_blender.py -> <work>\\out\\pc_gacha01_nk.blend + _preview.png (game materials)
  pmx      blender: export_suit_pmx_blender.py on that .blend -> <work>\\out\\pmx\\pc_gacha01_nk.pmx + textures\\ (the
           batch's Convert_to_MMD5 conversion, 58 vertex morphs, bust / hair physics, 衣服非表示 over the swimsuit)
  video    (--video) blender: render_pmx_dance.py -> <work>\\out\\pc_gacha01_nk_手势舞.mp4
Then everything made is copied to --out (same names: a re-run replaces the files there).  Prints
ROE_GACHA_EXPORT={json}.  Needs: system Python with UnityPy + Pillow, Blender 3.6 with mmd_tools + Convert_to_MMD5.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROE = os.path.dirname(HERE)
GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles"
DOWNLOADS = os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "Pinkcore", "Rise of Eros", "AssetBundles")
CLI = r"E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
OUT = r"E:\game_export\RiseOfEros\_抽奖模型"
VMD = r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd"
WAV = r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\meeynara手势舞2026.2.14.WAV"
STEM = "pc_gacha01_nk"
CID = "j_gacha01"

# What the game's gacha scene draws (the renderers of scene_meta3d_gachaintro.ab, read 2026-10-25 with
# inspect_bundle_renderers.py): the model and the game's material assignment of it ...
MODEL = ["chara_bare_pc_gacha01_nk_tutorial.ab",   # Miri's e01 body mesh, Keleira's k01 hair, necklace, swimsuit
         "gacha_video_prefab_pc_gacha01.ab"]       # the same meshes with the game's materials on the renderers
# ... and the materials / textures: its own (hair, swimsuit, necklace), Lynn's body and head, the d head (Lynn's
# brow and iris textures), the k head (the hair albedo), the shared skin / eye / tooth / hair maps
MATS = ["chara_mat_bare_pc_gacha01_nk_tutorial.ab", "chara_mat_bare_pc_j01_nk_tutorial.ab",
        "chara_mat_bare_pc_j_common_head_tutorial.ab", "chara_mat_bare_common_prelude.ab"]
TEXS = ["chara_tex_bare_pc_gacha01_nk_tutorial.ab", "chara_tex_bare_pc_j01_nk_tutorial.ab",
        "chara_tex_bare_pc_j_common_head_tutorial.ab", "chara_tex_bare_pc_d_common_head_tutorial.ab",
        "chara_tex_bare_pc_k_common_head_tutorial.ab", "chara_tex_bare_common_prelude.ab"]
PLACEHOLDERS = ["chara_mat_bare__system_prelude.ab"]   # the bundle's default_material_bare (AssetStudio resolves it)
STEPS = ("extract", "hq", "blend", "pmx", "video")


def newest(name):
    found = [p for p in (os.path.join(DOWNLOADS, name), os.path.join(GAME, name)) if os.path.isfile(p)]
    if not found:
        raise SystemExit("bundle not found in the install dir or the download cache: %s" % name)
    return max(found, key=os.path.getmtime)


def run(cmd, log_path, dry):
    print(">", subprocess.list2cmdline(cmd))
    if dry:
        return ""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace")
        log.write(proc.stdout)
    if proc.returncode:
        raise SystemExit("failed (%d), see %s" % (proc.returncode, log_path))
    return proc.stdout


def marker(text, prefix, log_path):
    line = next((l for l in reversed(text.splitlines()) if l.startswith(prefix)), "")
    if not line:
        raise SystemExit("no %s line - see %s" % (prefix, log_path))
    return json.loads(line[len(prefix):])


def step_extract(work, args, report):
    stage, export = os.path.join(work, "stage"), os.path.join(work, "export")
    for d in (stage, export):
        if os.path.isdir(d) and not args.dry_run:
            shutil.rmtree(d)
    os.makedirs(stage, exist_ok=True)
    copied = []
    for name in MODEL + MATS + TEXS + PLACEHOLDERS:
        src = newest(name)
        if not args.dry_run:
            shutil.copy2(src, stage)
        copied.append(src)
    report["bundles"] = copied
    run([args.cli, stage, "-m", "splitObjects", "--fbx-animation", "skip", "--fbx-scale-factor", "100",
         "-g", "sceneHierarchy", "-o", export, "--log-level", "warning"], os.path.join(work, "extract_fbx.log"),
        args.dry_run)
    run([args.cli, stage, "-m", "export", "-t", "tex2d", "--image-format", "png", "-g", "none",
         "-o", os.path.join(export, "_textures"), "--log-level", "warning"], os.path.join(work, "extract_tex.log"),
        args.dry_run)
    if not args.dry_run:
        # the pants' second copy fails in AssetStudio (a texture path under "<root> (1)"); the first copy is the one
        # build_gacha_blender.py reads
        fbx = [os.path.relpath(os.path.join(r, f), export) for r, _d, fs in os.walk(export) for f in fs
               if f.endswith(".fbx")]
        report["fbx"] = sorted(fbx)
        report["textures"] = len(os.listdir(os.path.join(export, "_textures")))


def step_hq(work, args, report):
    cache = os.path.join(work, "hq_cache")
    if args.dry_run:
        print("> hq_material_data.py %s --out %s --all (bundles: %s)" % (CID, cache, ", ".join(MATS + TEXS)))
        return
    sys.path.insert(0, ROE)
    import hq_material_data as H

    def select_bundles(cid, bundles, albedos=(), pieces=(), deps=None):
        missing = [n for n in MATS + TEXS if n not in bundles]
        if missing:
            raise SystemExit("bundles not found: %s" % missing)
        return list(MATS), sorted(TEXS)

    H.select_bundles = select_bundles
    os.makedirs(cache, exist_ok=True)
    argv = sys.argv
    sys.argv = ["hq_material_data.py", CID, "--out", cache, "--all"]
    try:
        H.main()
    finally:
        sys.argv = argv
    with open(os.path.join(cache, CID + ".json"), encoding="utf-8") as fh:
        data = json.load(fh)
    report["hq"] = {"materials": sorted(data["materials"]), "missing": data["missing"],
                    "export_errors": data["export_errors"]}


def step_blend(work, args, report):
    out = os.path.join(work, "out", STEM + ".blend")
    log = os.path.join(work, "blend.log")
    text = run([args.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_gacha_blender.py"),
                "--", "build", work, os.path.join(work, "hq_cache"), out], log, args.dry_run)
    if not args.dry_run:
        report["blend"] = marker(text, "GACHA_BUILD=", log)


def step_pmx(work, args, report):
    pmx = os.path.join(work, "out", "pmx", STEM + ".pmx")
    if os.path.isdir(os.path.dirname(pmx)) and not args.dry_run:
        shutil.rmtree(os.path.dirname(pmx))
    os.makedirs(os.path.dirname(pmx), exist_ok=True)
    log = os.path.join(work, "pmx.log")
    text = run([args.blender, "-b", "--factory-startup", os.path.join(work, "out", STEM + ".blend"),
                "--python", os.path.join(ROE, "export_suit_pmx_blender.py"), "--", pmx], log, args.dry_run)
    if not args.dry_run:
        report["pmx"] = marker(text, "ROE_SUIT_PMX=", log)


def step_video(work, args, report):
    mp4 = os.path.join(work, "out", STEM + "_手势舞.mp4")
    log = os.path.join(work, "video.log")
    run([args.blender, "-b", "--factory-startup", "--python", os.path.join(ROE, "render_pmx_dance.py"), "--",
         os.path.join(work, "out", "pmx", STEM + ".pmx"), args.vmd, args.wav, mp4, "0", "full", "mmd"], log,
        args.dry_run)
    report["video"] = mp4


def copy_out(work, args, report):
    src = os.path.join(work, "out")
    os.makedirs(os.path.join(args.out, "pmx"), exist_ok=True)
    copied = []
    for name in (STEM + ".blend", STEM + "_preview.png", STEM + "_手势舞.mp4"):
        if os.path.isfile(os.path.join(src, name)):
            shutil.copy2(os.path.join(src, name), args.out)
            copied.append(name)
    pmx_dir = os.path.join(src, "pmx")
    if os.path.isdir(pmx_dir):
        dst = os.path.join(args.out, "pmx")
        for name in os.listdir(pmx_dir):
            s = os.path.join(pmx_dir, name)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(dst, name), dirs_exist_ok=True)
            else:
                shutil.copy2(s, dst)
            copied.append("pmx\\" + name)
    report["copied_to"] = args.out
    report["copied"] = copied


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT, help="where the results go (default %(default)s)")
    ap.add_argument("--work", default=os.path.join(tempfile.gettempdir(), "roe_gacha01"),
                    help="work folder: staged bundles, FBX, material cache, logs (default %(default)s)")
    ap.add_argument("--steps", default="extract,hq,blend,pmx", help="comma separated, from %s" % ",".join(STEPS))
    ap.add_argument("--video", action="store_true", help="also the dance preview (adds the video step)")
    ap.add_argument("--vmd", default=VMD)
    ap.add_argument("--wav", default=WAV)
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--cli", default=CLI, help="AssetStudioModCLI.exe")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()] + (["video"] if args.video else [])
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise SystemExit("unknown step(s): %s" % ", ".join(sorted(unknown)))
    os.makedirs(args.work, exist_ok=True)
    report = {"work": args.work, "steps": steps}
    t0 = time.time()
    for step in STEPS:
        if step in steps:
            print("== %s" % step)
            globals()["step_" + step](args.work, args, report)
    if not args.dry_run:
        copy_out(args.work, args, report)
    report["seconds"] = round(time.time() - t0, 1)
    print("ROE_GACHA_EXPORT=" + json.dumps(report, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
