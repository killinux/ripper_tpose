# -*- coding: utf-8 -*-
"""ELDEN RING character mod -> .blend with the game's full-size materials, XPS and PMX, in one command.

    python export_mod.py <mod.zip | unpacked mod folder> [--name N] [--character C]
           [--tint MATERIAL=#RRGGBB ...] [--variant LABEL=REGEX ...] [--no-xps] [--no-pmx] [--no-preview]
           [--out-root D:\\eldenring_exports] [--blender <blender 3.6 exe>]

Steps (each one its own script, runnable alone):
  1. unpack_mod.py         parts/*.partsbnd.dcx -> work/<name>/ (model.json + model.npz + textures/)
  2. build_blend.py        -> blend/<name>/<name>.blend (+ textures/, preview strip)
  3. export_xps_blender.py -> xps/<name>/<name>.xps              (and xps/<name>_<LABEL>/ per --variant)
  4. export_pmx_blender.py -> pmx/<name>/<name>.pmx              (and pmx/<name>_<LABEL>/ per --variant)
  5. scripts/stellarblade/preview_pmx_blender.py: each PMX imported back with physics, a dance played, rendered
A --variant leaves out the mesh objects (= FLVER material names) its regex matches, e.g. a hardsuit.
Known mods (PRESETS, by the Nexus mod id in the zip's name) fill in name / character / tints / variants.
Archive afterwards: python scripts\\archive\\archive_exports.py eldenring  (-> E:\\game_export\\EldenRing).
Prints ER_EXPORT={json}.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BLENDER = os.environ.get("BLENDER36", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
TEST_VMD = r"E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd"

PRESETS = {
    # Nexus mod id -> settings.  11065 "Reika Hardsuit - Gantz" by zlohort (Elden Ring Nexus, 2026-10-04)
    "11065": {
        "name": "mod11065_Reika_Hardsuit", "character": "Reika", "model_name": "Reika Hardsuit",
        "comment": "ELDEN RING mod 'Reika Hardsuit - Gantz' by zlohort (nexusmods.com/eldenring/mods/11065), "
                   "converted by ripper_tpose scripts/eldenring. Personal use only; credit the mod author.",
        # the fur / hair shader (c4720 'Beast') colours a near-black map copper in the game: measured from the
        # author's showcase GIFs (median of the hair pixels)
        "tint": {"Hair": "#a95e37"},
        # without the hardsuit: the giant arms + shoulder frame (am_m_1810), the hanging tubes, the katana
        "variants": {"无外骨骼": r"^(ARMS_[LR]|BASE(_[LR])?|TUBES_[ABC]|BLADE)$"},
    },
}


def run(cmd, tag, log_path):
    t = time.time()
    with open(log_path, "a", encoding="utf-8") as log:
        log.write("\n$ %s\n" % " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.write(p.stdout[-200000:])
        log.write(p.stderr[-50000:])
    line = next((l for l in reversed(p.stdout.splitlines()) if l.startswith(tag + "=")), None)
    if line is None:
        raise RuntimeError("%s failed (no %s line); see %s" % (os.path.basename(cmd[-1] if cmd else "?"), tag, log_path))
    res = json.loads(line[len(tag) + 1:])
    res["_seconds"] = round(time.time() - t, 1)
    return res


def mod_id(path):
    m = re.search(r"\s(\d{2,6})\s\d", os.path.basename(path))       # "<name> <modid> <version> <time> <rnd>.zip"
    return m.group(1) if m else None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mod")
    ap.add_argument("--name", default="")
    ap.add_argument("--character", default="")
    ap.add_argument("--model-name", default="")
    ap.add_argument("--comment", default="")
    ap.add_argument("--tint", action="append", default=[], metavar="MATERIAL=#RRGGBB")
    ap.add_argument("--variant", action="append", default=[], metavar="LABEL=REGEX")
    ap.add_argument("--no-preset", action="store_true")
    ap.add_argument("--no-xps", action="store_true")
    ap.add_argument("--no-pmx", action="store_true")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--out-root", default=r"D:\eldenring_exports")
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--vmd", default=TEST_VMD)
    args = ap.parse_args(argv)

    preset = {} if args.no_preset else PRESETS.get(mod_id(args.mod) or "", {})
    name = args.name or preset.get("name") or "mod_" + re.sub(r"\W+", "_", os.path.splitext(os.path.basename(args.mod))[0])
    tints = dict(preset.get("tint", {}))
    tints.update(dict(t.split("=", 1) for t in args.tint))
    variants = dict(preset.get("variants", {}))
    variants.update(dict(v.split("=", 1) for v in args.variant))
    root = args.out_root
    work = os.path.join(root, "work", name)
    blend_dir = os.path.join(root, "blend", name)
    blend = os.path.join(blend_dir, name + ".blend")
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    log = os.path.join(root, "logs", name + ".log")
    if os.path.exists(log):
        os.remove(log)
    summary = {"mod": os.path.abspath(args.mod), "name": name, "preset": mod_id(args.mod) if preset else None,
               "tints": tints, "variants": variants, "log": log}

    cmd = [sys.executable, os.path.join(HERE, "unpack_mod.py"), args.mod, "--out", work]
    for k, v in tints.items():
        cmd += ["--tint", "%s=%s" % (k, v)]
    summary["unpack"] = run(cmd, "ER_UNPACK", log)
    summary["blend"] = run([args.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"),
                            "--", "--work", work, "--out", blend, "--preview", os.path.join(blend_dir, "preview")],
                           "ER_BLEND", log)
    strip_previews(blend_dir)
    jobs = [("", "")] + sorted(variants.items())
    model_name = args.model_name or preset.get("model_name") or name
    comment = args.comment or preset.get("comment", "")
    for label, rx in jobs:
        out_name = name + ("_" + label if label else "")
        if not args.no_xps:
            summary["xps" + ("_" + label if label else "")] = run(
                [args.blender, "-b", blend, "--factory-startup", "--python", os.path.join(HERE, "export_xps_blender.py"),
                 "--", "--out", os.path.join(root, "xps", out_name), "--name", out_name] +
                (["--leave-out", rx] if rx else []), "ER_XPS", log)
        if not args.no_pmx:
            pmx_dir = os.path.join(root, "pmx", out_name)
            cmd = [args.blender, "-b", blend, "--factory-startup", "--python",
                   os.path.join(HERE, "export_pmx_blender.py"), "--", "--out", pmx_dir, "--name", out_name,
                   "--model-name", model_name + (" " + label if label else "")]
            if comment:
                cmd += ["--comment", comment]
            if rx:
                cmd += ["--leave-out", rx]
            summary["pmx" + ("_" + label if label else "")] = brief_pmx(run(cmd, "ER_PMX", log))
            if not args.no_preview:
                summary["preview" + ("_" + label if label else "")] = run(
                    [args.blender, "-b", "--python", os.path.join(REPO, "scripts", "stellarblade", "preview_pmx_blender.py"),
                     "--", "--pmx", os.path.join(pmx_dir, out_name + ".pmx"), "--vmd", args.vmd], "PMX_PREVIEW", log)
    with open(os.path.join(root, "logs", name + "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("ER_EXPORT=" + json.dumps(summary, ensure_ascii=False), flush=True)


def brief_pmx(r):
    keep = ("pmx", "left_out", "height_m", "hair_chains", "eye_bones", "bust_physics", "bones", "rigid_bodies",
            "joints", "distortion", "stray_recipients", "grant_order_violations", "bytes", "_seconds")
    return {k: r.get(k) for k in keep if k in r}


def strip_previews(folder):
    """preview.0/1/2.png -> one preview.png strip (front / side / back)."""
    try:
        from PIL import Image
    except ImportError:
        return
    parts = [os.path.join(folder, "preview.%d.png" % k) for k in range(3)]
    if not all(os.path.exists(p) for p in parts):
        return
    ims = [Image.open(p).convert("RGB") for p in parts]
    strip = Image.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)), (128, 128, 128))
    x = 0
    for im in ims:
        strip.paste(im, (x, 0))
        x += im.width
    strip.save(os.path.join(folder, "preview.png"))
    for p in parts:
        os.remove(p)


if __name__ == "__main__":
    main(sys.argv[1:])
