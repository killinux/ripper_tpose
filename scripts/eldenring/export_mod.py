# -*- coding: utf-8 -*-
"""ELDEN RING character mod -> .blend with the game's full-size materials, XPS and PMX, in one command.

    python export_mod.py <mod .zip | .rar | .7z | unpacked mod folder> [--name N] [--character C]
           [--tint MATERIAL=#RRGGBB ...] [--variant LABEL=REGEX ...] [--set LABEL=PARTS ...] [--only-set L1,L2]
           [--no-xps] [--no-pmx] [--no-preview] [--skip-done]
           [--out-root D:\\eldenring_exports] [--blender <blender 3.6 exe>]

Steps (each one its own script, runnable alone):
  1. unpack_mod.py         parts/*.partsbnd.dcx -> work/<name>/ (model.json + model.npz + textures/)
  2. build_blend.py        -> blend/<name>/<name>.blend (+ textures/, preview strip)
  3. export_xps_blender.py -> xps/<name>/<name>.xps              (and xps/<name>_<LABEL>/ per --variant)
  4. export_pmx_blender.py -> pmx/<name>/<name>.pmx              (and pmx/<name>_<LABEL>/ per --variant)
  5. scripts/stellarblade/preview_pmx_blender.py: each PMX imported back with physics, a dance played, rendered
A --variant leaves out the mesh objects (= FLVER material names) its regex matches, e.g. a hardsuit.
A --set makes one model from some of the mod's parts (PARTS = comma list of part ids or wildcards, *_1500): mods
that ship several outfits as several armour ids (Tifa Gantz: one id per set).  Every set runs steps 1-5.
Known mods (PRESETS, by the Nexus mod id in the file name - "<name> <id> <ver> <time> <rnd>.zip" or the older
"<name>-<id>-<ver>-<time>.rar") fill in name / character / tints / variants / sets, and a label per download
(file_labels: a word in the file name -> a name part, e.g. the suit colour).
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
    # 4684 "Tifa Gantz (nude jiggle physics 9 sets)" by shintheweapon / 兵器君 (2024-03-08): three downloads = three
    # suit colours, each with three sets on three armour ids (the helm of each carries its own hair colour);
    # sets told apart by their meshes: 1500 high-cut suit + thigh bands, 1810 full bodysuit, 2110 nude + gauntlets
    "4684": {
        "name": "mod4684_Tifa_Gantz", "character": "Tifa", "model_name": "Tifa Gantz",
        "comment": "ELDEN RING mod 'Tifa Gantz (nude jiggle physics 9 sets)' by shintheweapon / 兵器君 "
                   "(nexusmods.com/eldenring/mods/4684); models: mokujinhornywood, dddkhakha1. Converted by ripper_tpose "
                   "scripts/eldenring. Personal use only; credit the authors.",
        "file_labels": {"Black": "黑", "Metallic": "金属", "White": "白"},
        "sets": {"比基尼": "*_1500", "全覆盖": "*_1810", "裸体": "*_2110"},
    },
    # 1196 "DOA Naotora Gantz set" by az3163693 (2022-05-18), replaces the Eccentric set (1460); models: Shuubaru
    "1196": {
        "name": "mod1196_Naotora_Gantz", "character": "Naotora", "model_name": "Naotora Gantz",
        "comment": "ELDEN RING mod 'DOA Naotora Gantz set' by az3163693 (nexusmods.com/eldenring/mods/1196); "
                   "models: Shuubaru. Converted by ripper_tpose scripts/eldenring. Personal use only; credit the authors.",
    },
    # SEKIRO (same FromSoft formats; FLVER 0x2001A / 0x20014, MTD materials whose textures the FLVER lists itself).
    # 1838 "Tifa Gantz (jiggle and hair physics weapon included)" by shintheweapon / 兵器君 (2024-03-24): three
    # downloads = three colours; costumes 9000 (Wolf's original memory: full suit), 9120 (bikini), 9130 (nude) - told
    # apart by their meshes; wp_a_0300 = Kusabimaru with the glowing blade, in every set
    "1838": {
        "game": "sekiro", "out_root": r"D:\sekiro_exports",
        "name": "mod1838_Tifa_Gantz", "character": "Tifa", "model_name": "Tifa Gantz",
        "comment": "SEKIRO mod 'Tifa Gantz (jiggle and hair physics weapon included)' by shintheweapon / 兵器君 "
                   "(nexusmods.com/sekiro/mods/1838); models: mokujinhornywood, dddkhakha1, lezisell. Converted by "
                   "ripper_tpose scripts/eldenring. Personal use only; credit the authors.",
        "file_labels": {"Black": "黑", "Metallic": "金属", "White": "白"},
        "sets": {"全覆盖": "*_9000,wp_*", "比基尼": "*_9120,wp_*", "裸体": "*_9130,wp_*"},
    },
}


def run(cmd, tag, log_path):
    t = time.time()
    with open(log_path, "a", encoding="utf-8") as log:
        log.write("\n$ %s\n" % " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.write(p.stdout[-200000:])
        log.write(p.stderr[-50000:])
    line = next((l[l.index(tag + "="):] for l in reversed(p.stdout.splitlines()) if tag + "=" in l), None)
    if line is None:
        raise RuntimeError("%s failed (no %s line); see %s" % (os.path.basename(cmd[-1] if cmd else "?"), tag, log_path))
    res = json.loads(line[len(tag) + 1:])
    res["_seconds"] = round(time.time() - t, 1)
    return res


def mod_id(path):
    b = os.path.basename(path)
    m = re.search(r"\s(\d{2,6})\s\d", b)                      # "<name> <modid> <version> <time> <rnd>.zip"
    if not m:
        m = re.match(r"^.*?-(\d{2,6})-.+-\d{9,11}\.\w+$", b)   # "<name>-<modid>-<version>-<time>.rar"
    return m.group(1) if m else None


def file_label(path, labels):
    b = os.path.basename(path)
    return next((v for k, v in labels.items() if re.search(r"(^|[^A-Za-z])%s([^A-Za-z]|$)" % re.escape(k), b)), "")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mod")
    ap.add_argument("--name", default="")
    ap.add_argument("--character", default="")
    ap.add_argument("--model-name", default="")
    ap.add_argument("--comment", default="")
    ap.add_argument("--tint", action="append", default=[], metavar="MATERIAL=#RRGGBB")
    ap.add_argument("--variant", action="append", default=[], metavar="LABEL=REGEX")
    ap.add_argument("--set", action="append", default=[], metavar="LABEL=PARTS",
                    help="one model from these parts (ids or wildcards, comma separated); repeatable")
    ap.add_argument("--only-set", default="", help="comma list of set labels to export (default all)")
    ap.add_argument("--label", default=None, help="name part for this download (default: the preset's file_labels)")
    ap.add_argument("--no-preset", action="store_true")
    ap.add_argument("--no-xps", action="store_true")
    ap.add_argument("--no-pmx", action="store_true")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--skip-done", action="store_true", help="skip a model whose logs/<name>_summary.json is complete")
    ap.add_argument("--from-step", choices=("unpack", "xps", "pmx"), default="unpack",
                    help="xps / pmx: keep the existing work folder and .blend, redo from that step (after a fix in "
                         "the XPS / PMX steps)")
    ap.add_argument("--out-root", default=None,
                    help=r"default D:\eldenring_exports (a preset may set its own: Sekiro D:\sekiro_exports)")
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--vmd", default=TEST_VMD)
    args = ap.parse_args(argv)

    preset = {} if args.no_preset else PRESETS.get(mod_id(args.mod) or "", {})
    args.out_root = args.out_root or preset.get("out_root") or r"D:\eldenring_exports"
    base = args.name or preset.get("name") or "mod_" + re.sub(r"\W+", "_", os.path.splitext(os.path.basename(args.mod))[0])
    label = args.label if args.label is not None else file_label(args.mod, preset.get("file_labels", {}))
    tints = dict(preset.get("tint", {}))
    tints.update(dict(t.split("=", 1) for t in args.tint))
    variants = dict(preset.get("variants", {}))
    variants.update(dict(v.split("=", 1) for v in args.variant))
    sets = dict(preset.get("sets", {}))
    sets.update(dict(s.split("=", 1) for s in args.set))
    only = {s.strip() for s in args.only_set.split(",") if s.strip()}
    jobs = [(k, v) for k, v in sets.items() if not only or k in only] if sets else [("", "")]
    results = []
    for set_label, parts in jobs:
        name = "_".join(x for x in (base, label, set_label) if x)
        title = " ".join(x for x in (args.model_name or preset.get("model_name") or base, label, set_label) if x)
        results.append(export_one(args, preset, name, title, parts, tints, variants))
    print("ER_EXPORT=" + json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False), flush=True)


def export_one(args, preset, name, model_name, parts, tints, variants):
    root = args.out_root
    work = os.path.join(root, "work", name)
    blend_dir = os.path.join(root, "blend", name)
    blend = os.path.join(blend_dir, name + ".blend")
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    log = os.path.join(root, "logs", name + ".log")
    summary_path = os.path.join(root, "logs", name + "_summary.json")
    old = {}
    if os.path.isfile(summary_path):
        with open(summary_path, encoding="utf-8") as fh:
            old = json.load(fh)
    if args.skip_done and args.from_step == "unpack" and old.get("complete"):
        print("skip %s (done)" % name, flush=True)
        return old
    redo = args.from_step != "unpack"
    if redo and not os.path.isfile(blend):
        raise RuntimeError("--from-step %s needs %s" % (args.from_step, blend))
    if os.path.exists(log) and not redo:
        os.remove(log)
    summary = {"mod": os.path.abspath(args.mod), "name": name, "preset": mod_id(args.mod) if preset else None,
               "parts": parts, "tints": tints, "variants": variants, "log": log}
    if redo:
        summary.update({k: v for k, v in old.items() if k in ("unpack", "blend") or
                        (args.from_step == "pmx" and k.startswith("xps"))})
        summary["redone_from"] = args.from_step
    else:
        cmd = [sys.executable, os.path.join(HERE, "unpack_mod.py"), args.mod, "--out", work]
        if parts:
            cmd += ["--parts", parts]
        for k, v in tints.items():
            cmd += ["--tint", "%s=%s" % (k, v)]
        summary["unpack"] = run(cmd, "ER_UNPACK", log)
        summary["blend"] = run([args.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"),
                                "--", "--work", work, "--out", blend, "--preview", os.path.join(blend_dir, "preview")],
                               "ER_BLEND", log)
        strip_previews(blend_dir)
    jobs = [("", "")] + sorted(variants.items())
    comment = args.comment or preset.get("comment", "")
    for label, rx in jobs:
        out_name = name + ("_" + label if label else "")
        if not args.no_xps and args.from_step != "pmx":
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
    summary["complete"] = True
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("ER_MODEL=" + json.dumps({"name": name, "seconds": round(sum(v.get("_seconds", 0) for v in summary.values()
                                                                       if isinstance(v, dict)), 1)}, ensure_ascii=False), flush=True)
    return summary


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
