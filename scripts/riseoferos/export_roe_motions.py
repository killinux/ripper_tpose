"""Export a Rise of Eros outfit's own motions as VMD files for its PMX (MMD, or Blender with mmd_tools).

  python export_roe_motions.py a08                       every clip of pc_a08_hd (showcase + battle)
  python export_roe_motions.py a08 --list                the clips the game has for it
  python export_roe_motions.py a08 --clips skill_01,die  only these
  options: --stem pc_a08_outfit1_hd (another suit of the same outfit)   --pmx <file>   --out <dir>
           --no-scale-morphs (never touch the PMX; scaled props then keep their full size)

Reads (never writes) the game's bundles: chara_armor_pc_<id>_hd & ld_hd.ab holds the showcase clips
(idle_02, idle_ur01, react_01, react_02), chara_armor_pc_<id>_hd & ld_ld*.ab the battle clips (idle_01,
skill_01..03, hurt, die, rip).  The PMX is found in the archive, E:\\game_export\\RiseOfEros\\<character>\\pmx\\<stem>.
Writes to <out> = E:\\game_export\\RiseOfEros\\<character>\\vmd\\<stem>:
  <stem>_<clip>.vmd              showcase clips
  battle\\<stem>_<clip>.vmd       battle clips
  _clips\\<clip>.json             the decoded motion (render_roe_motion_videos.py renders from it)
  _clips\\export_summary.txt      per clip: frames, the round-trip check, morphs keyed

Steps: decode every clip onto the hd skeleton (decode_roe_clip.py) -> find bones the clip scales (roe_motion_scale.py;
MMD bones cannot scale, so a uniformly scaled group becomes a vertex morph added to the PMX, pmx_add_scale_morph.py,
and keyed frame by frame) -> one Blender run per clip (make_roe_vmd.py): retarget, write the VMD, re-import it with
mmd_tools and measure every joint against the game.  See README_motion.md beside this file.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import UnityPy  # noqa: E402

import decode_roe_clip as dec  # noqa: E402
import pmx_add_scale_morph as psm  # noqa: E402
from roe_motion_common import (BLENDER, GROUPS, HERE, bundles, clip_sort_key, default_out, find_pmx,  # noqa: E402
                               grep, pmx_copies, run, vmd_path)

SCALE_TOL = 0.03


def morph_name(bones, factor):
    """Name a scale morph.  The g04 fan's 扇子縮小 is kept for the fan; others get 縮小_/拡大_ + their first bone,
    and a trailing + when the morph covers more bones, cut to the 15 Shift-JIS bytes a VMD can name."""
    if any("fan" in b.lower() for b in bones):
        return "扇子縮小"
    name = ("縮小_" if factor < 1 else "拡大_") + bones[0]
    mark = "+" if len(bones) > 1 else ""
    while len((name + mark).encode("shift_jis", "replace")) > 15:
        name = name[:-1]
    return name + mark


def scale_classes(per_clip):
    """{clip: [bone groups the clip scales together]} -> the finest classes such that in every clip all bones of a
    class share one scale curve: {class (tuple): {clip: factors}}.  a00's five semen bones go to 0 together in most
    of a08's scene but grow one by one in eros15_p4, so they need a morph each there and everywhere."""
    bones = sorted({b for groups in per_clip.values() for bs, _f in groups for b in bs})
    classes = [bones] if bones else []
    for groups in per_clip.values():
        where = {b: k for k, (bs, _f) in enumerate(groups) for b in bs}
        refined = []
        for cls in classes:
            split = {}
            for b in cls:
                split.setdefault(where.get(b, -1), []).append(b)
            refined += list(split.values())
        classes = refined
    out = {}
    for cls in classes:
        out[tuple(cls)] = {clip: f for clip, groups in per_clip.items() for bs, f in groups if cls[0] in bs}
    return out


def pmx_morphs_and_bones(path):
    info = psm.parse(open(path, "rb").read())
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    return {n.decode(enc) for n in info["morph_names"]}, {n.decode(enc) for n, _p in info["bones"]}


def morph_bones(path):
    """{morph name: [bones it scales]} from the English names pmx_add_scale_morph.py writes ("scale 0: b1,b2");
    None for morphs that do not say (扇子縮小 from before 2026-10-01)."""
    info = psm.parse(open(path, "rb").read())
    enc = "utf-16-le" if info["enc"] == 0 else "utf-8"
    out = {}
    for n, e in zip(info["morph_names"], info["morph_names_e"]):
        e = e.decode(enc)
        out[n.decode(enc)] = e.split(": ", 1)[1].split(",") if e.startswith("scale ") and ": " in e else None
    return out


def ensure_scale_morph(pmx, name, factor, bones, log):
    """Add the morph to the PMX, its _bustB sibling and their D:\\roe_exports source (pmx_copies) unless it is there
    already; edits the files in place.  A same-named morph over other bones makes it pick another name; returns
    the name used."""
    have = morph_bones(pmx)
    base, k = name, 2
    while name in have and have[name] is not None and sorted(have[name]) != sorted(bones):
        name = base[:-2] + "~%d" % k if len(base.encode("shift_jis", "replace")) > 13 else base + "~%d" % k
        k += 1
    for path in pmx_copies(pmx):
        morphs, _bones = pmx_morphs_and_bones(path)
        if name in morphs:
            log("   PMX already has %s: %s" % (name, path))
            continue
        tmp = path + ".tmp"
        code = run([sys.executable, os.path.join(HERE, "pmx_add_scale_morph.py"), path, tmp, name, "%g" % factor]
                   + bones, tmp + ".log")
        if code != 0 or not os.path.isfile(tmp):
            log("   FAILED to add %s to %s (see %s)" % (name, path, tmp + ".log"))
            continue
        os.replace(tmp, path)
        os.remove(tmp + ".log")
        log("   PMX: added morph %s (%d bones x%g) -> %s" % (name, len(bones), factor, path))
    return name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="outfit id, e.g. a08 or g04")
    ap.add_argument("--stem", help="model stem (default pc_<id>_hd)")
    ap.add_argument("--pmx", help="target PMX (default: the archive's <stem>.pmx)")
    ap.add_argument("--out", help="output folder (default: <archive>\\<character>\\vmd\\<stem>)")
    ap.add_argument("--clips", help="comma separated clip names (default: all)")
    ap.add_argument("--list", action="store_true", help="only list the clips")
    ap.add_argument("--no-scale-morphs", action="store_true")
    args = ap.parse_args()
    stem = args.stem or "pc_%s_hd" % args.id
    found = bundles(args.id)
    if not found["showcase"]:
        sys.exit("no bundle chara_armor_pc_%s_hd & ld_hd.ab in the game folders" % args.id)
    envs = {"showcase": UnityPy.load(found["showcase"])}
    if found["battle"]:
        envs["battle"] = UnityPy.load(found["battle"])
    if args.list:
        for group, env in envs.items():
            print("%s (%s):" % (GROUPS[group], os.path.basename(found[group])))
            for name, seconds in dec.list_clips(env):
                print("   %-12s %.2f s" % (name, seconds))
        return
    pmx, character = (args.pmx, None) if args.pmx else find_pmx(stem)
    if not pmx or not os.path.isfile(pmx):
        sys.exit("PMX not found for %s (pass --pmx)" % stem)
    out = args.out or default_out(stem, character or os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(pmx)))))
    work = os.path.join(out, "_clips")
    os.makedirs(work, exist_ok=True)
    summary_path = os.path.join(work, "export_summary.txt")
    summary = open(summary_path, "w", encoding="utf-8")

    def log(line):
        print(line, flush=True)
        summary.write(line + "\n")
        summary.flush()

    t0 = time.time()
    log("ROE motions: %s  PMX %s" % (stem, pmx))
    log("   showcase bundle %s\n   battle bundle %s" % (found["showcase"], found["battle"]))
    wanted = set(args.clips.split(",")) if args.clips else None
    skeleton = dec.read_skeleton(envs["showcase"])        # the hd prefab, which our PMX was built from
    plan = []
    for group, env in envs.items():
        clips = dec.clips_in(env)
        for name, _seconds in sorted(dec.list_clips(env), key=lambda c: clip_sort_key(c[0])):
            if wanted and name not in wanted:
                continue
            if any(name == p[1] for p in plan):
                sys.exit("clip name %s appears in both bundles" % name)
            js = os.path.join(work, name + ".json")
            log("decode %-9s %s" % (group, dec.decode_clip(clips[name], skeleton, js)))
            plan.append((group, name, js))
    if not plan:
        sys.exit("no clip matched %s" % args.clips)

    # bones the clips scale -> vertex morphs
    morph_values = {name: {} for _g, name, _j in plan}
    report_path = os.path.join(work, "scale.json")
    run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "roe_motion_scale.py"), "--",
         report_path] + [js for _g, _n, js in plan], os.path.join(work, "scale.log"))
    report = json.load(open(report_path, encoding="utf-8"))
    per_clip_groups = {}
    for name, rec in report.items():
        for g in rec["groups"]:
            if not g["uniform"]:
                log("   %s: %s stretch unevenly (%.2f..%.2f) - a morph cannot copy that, left as is"
                    % (name, ",".join(g["bones"]), min(g["factors"]), max(g["factors"])))
                continue
            per_clip_groups.setdefault(name, []).append((g["bones"], g["factors"]))
    _morphs, pmx_bones = pmx_morphs_and_bones(pmx)
    for bones, per_clip in scale_classes(per_clip_groups).items():
        values = [v for f in per_clip.values() for v in f]
        factor = round(min(values) if min(values) < 1 - SCALE_TOL else max(values), 4)
        name = morph_name(list(bones), factor)
        missing = [b for b in bones if b not in pmx_bones]
        if missing or args.no_scale_morphs:
            log("   %s scaled x%.3f in %s - %s" % (",".join(bones), factor, ",".join(per_clip),
                                                   "not in the PMX: %s" % missing if missing else "left (--no-scale-morphs)"))
            continue
        log("scale: %s x%.3f in %s -> morph %s" % (",".join(bones), factor, ",".join(sorted(per_clip, key=clip_sort_key)), name))
        name = ensure_scale_morph(pmx, name, factor, list(bones), log)
        for clip in morph_values:
            curve = per_clip.get(clip)
            # morph weight w scales by 1 + w (factor - 1): exact for any factor, since the offsets are linear
            morph_values[clip][name] = [round((f - 1) / (factor - 1), 5) for f in curve] if curve else 0.0

    # one Blender run per clip
    for group, name, js in plan:
        vmd = vmd_path(out, stem, group, name)
        os.makedirs(os.path.dirname(vmd), exist_ok=True)
        cmd = [BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "make_roe_vmd.py"), "--", js, pmx, vmd]
        if morph_values[name]:
            spec = os.path.join(work, name + ".morphs.json")
            json.dump(morph_values[name], open(spec, "w", encoding="utf-8"), ensure_ascii=False)
            cmd += ["--morphs", spec]
        lf = os.path.join(work, name + ".log")
        code = run(cmd, lf)
        lines = grep(lf, "VMD written", "round trip", "morph keys", "Traceback", "Error: Python")
        log("vmd    %-9s %-10s exit %d  (%d s)" % (group, name, code, time.time() - t0))
        for line in lines:
            log("   " + line.strip()[:260])
    log("done: %d clips in %d s -> %s" % (len(plan), time.time() - t0, out))
    summary.close()
    shutil.copy(summary_path, os.path.join(out, "export_summary.txt"))


if __name__ == "__main__":
    main()
