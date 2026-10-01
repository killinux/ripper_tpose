"""Export a Rise of Eros outfit's H scene - both actors - as VMD files for the nude body PMX and the man's PMX.

  python export_roe_eros.py g04                 the outfit's scene (g04: eros07, five parts p1..p5)
  python export_roe_eros.py a08 --list          scenes and parts in the outfit's bundle
  python export_roe_eros.py g01 --scenes eros02 --clips eros02_p1,eros02_p2
  options: --out <dir>  --female-pmx <file>  --male-pmx <file>
           --no-morphs (never touch a PMX: no scene shapes, no hidden semen mesh)

Reads the game's bundles (never writes them):
  chara_bare_pc_<id>_nk.ab        the scene: every part (erosNN_p1 ..., transitions erosNN_t1_in ...) twice - the
                                  woman's clip (~650 curves) and the man's (~190), each for its own skeleton - plus
                                  pc_<body>@<part> (her blend-shape weights)
  chara_bare_pc_<body>*.ab        her body prefab with its bind poses (g01: _prelude, a01: _tutorial)
  chara_bare_pc_a00_nk*.ab        his (pc_a00_nk)
  bare_blend_shape_pc_<id>_nk.ab  the scene's blend shapes (roe_blendshapes.py)
PMX (archive): <character>\\pmx\\pc_<body>_bs\\pc_<body>_bs.pmx (the nude base; pc_<body> also works) and
Inase\\pmx\\pc_a00_nk\\pc_a00_nk.pmx.  Both prefabs sit at the scene origin in the game, so load both PMX at the
origin and give each its own VMD; the parts line up with each other.
Writes to <out> = <archive>\\<character>\\vmd\\pc_<id>_hd\\<scene>:
  <her pmx stem>_<part>.vmd, pc_a00_nk_<part>.vmd    one pair per part
  _clips\\<part>.f.json / <part>.m.json (decoded motions), logs, export_summary.txt
The PMX files get vertex morphs (edited in place, _bustB copies too): the scene's shapes on her (E07_Pussy_Open ...,
keyed from her blend-shape clips) and, on him, 縮小_liquid011, which hides the semen mesh the game keeps at scale 0.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import UnityPy  # noqa: E402

import decode_roe_clip as dec  # noqa: E402
import roe_blendshapes as rbs  # noqa: E402
from export_roe_motions import (SCALE_TOL, ensure_scale_morph, morph_name, pmx_morphs_and_bones,  # noqa: E402
                                scale_classes)
from roe_motion_common import (BLENDER, HERE, default_out, find_bundle, find_bundles, find_pmx, grep,  # noqa: E402
                               pmx_copies, run)

MALE = "pc_a00_nk"


def part_key(name):
    """eros07_p2 < eros07_p10 < eros07_t1_in < eros07_t1_out"""
    m = re.match(r"eros\d+_([pt])(\d+)(?:_(in|out))?$", name)
    if not m:
        return (2, 0, 0, name)
    return (0 if m.group(1) == "p" else 1, int(m.group(2)), {"in": 0, None: 0, "out": 1}[m.group(3)], name)


def scenes_in(env):
    """{scene: {"parts": [...], "body": "pc_g01_nk", "male": "pc_a00_nk"}} from the clip names and the skeleton
    copies the bundle carries (pc_g01_nk_bone@eros07_p1, pc_a00_nk_g01@eros07_p1)."""
    names = {o.peek_name() for o in env.objects if o.type.name == "AnimationClip"}
    roots = set()
    for o in env.objects:
        if o.type.name == "GameObject":
            n = o.peek_name()
            if "@eros" in n:
                roots.add(n)
    out = {}
    for name in names:
        m = re.match(r"(eros\d+)_[pt]\d", name)
        if m and "@" not in name:
            out.setdefault(m.group(1), {"parts": [], "body": None, "male": None})["parts"].append(name)
    for scene, rec in out.items():
        rec["parts"].sort(key=part_key)
        for r in roots:
            m = re.match(r"(pc_[a-z]\d+(?:_fm)?_nk)_bone@%s_" % scene, r)
            if m:
                rec["body"] = m.group(1)
            m = re.match(r"(pc_a00_nk)_[a-z]\d+@%s_" % scene, r)
            if m:
                rec["male"] = m.group(1)
    return out


def body_skeleton(body, log):
    """(bundle, bones) of the prefab whose Animator sits on GameObject ``body`` and that has the most bind poses."""
    best = None
    for path in sorted(find_bundles("chara_bare_%s*.ab" % body)):
        try:
            bones = dec.read_skeleton(UnityPy.load(path), body)
        except (SystemExit, StopIteration, ValueError, KeyError):
            continue
        n = sum(1 for b in bones if "bind" in b)
        if n and (best is None or n > best[0]):
            best = (n, path, bones)
    if best is None:
        raise SystemExit("no bundle with a skinned %s prefab" % body)
    log("   skeleton %s: %s (%d bones, %d with a bind pose)" % (body, os.path.basename(best[1]), len(best[2]), best[0]))
    return best[1], best[2]


def nude_pmx(body):
    """The archive's PMX of the nude base: pc_g01_nk_bs (nude-model route), else pc_g01_nk."""
    for stem in (body + "_bs", body):
        path, character = find_pmx(stem)
        if path:
            return path, character
    return None, None


def scale_morphs(actor, jsons, pmx, work, no_morphs, log):
    """Bones the actor's clips scale -> vertex morphs on its PMX; returns {part: {morph: value or [per frame]}}."""
    report_path = os.path.join(work, "scale.%s.json" % actor)
    run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "roe_motion_scale.py"), "--",
         report_path] + list(jsons.values()), os.path.join(work, "scale.%s.log" % actor))
    report = json.load(open(report_path, encoding="utf-8"))
    key_to_part = {os.path.splitext(os.path.basename(js))[0]: part for part, js in jsons.items()}
    per_part_groups = {}
    for key, rec in report.items():
        for g in rec["groups"]:
            if not g["uniform"]:
                log("   %s %s: %s stretch unevenly (%.2f..%.2f) - left as is"
                    % (actor, key_to_part[key], ",".join(g["bones"][:3]), min(g["factors"]), max(g["factors"])))
                continue
            per_part_groups.setdefault(key_to_part[key], []).append((g["bones"], g["factors"]))
    values = {part: {} for part in jsons}
    _m, pmx_bones = pmx_morphs_and_bones(pmx)
    for bones, per_part in scale_classes(per_part_groups).items():
        flat = [v for f in per_part.values() for v in f]
        factor = round(min(flat) if min(flat) < 1 - SCALE_TOL else max(flat), 4)
        if abs(factor - 1.0) < 1e-6:
            continue
        name = morph_name(list(bones), factor)
        missing = [b for b in bones if b not in pmx_bones]
        if missing or no_morphs:
            log("   %s: %s scaled x%.3f - %s" % (actor, ",".join(bones[:4]), factor,
                                                 "not in the PMX: %s" % missing[:4] if missing else "left (--no-morphs)"))
            continue
        log("   %s: %s x%.3f in %d parts -> morph %s" % (actor, ",".join(bones[:4]) + ("..." if len(bones) > 4 else ""),
                                                        factor, len(per_part), name))
        name = ensure_scale_morph(pmx, name, factor, list(bones), log)
        for part in values:
            curve = per_part.get(part)
            values[part][name] = [round((f - 1) / (factor - 1), 5) for f in curve] if curve else 0.0
    return values


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="outfit id whose scene to export, e.g. g04 or a08 (g01 / a01 hold the base scenes)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scenes", help="comma separated, e.g. eros07 (default: every scene in the bundle)")
    ap.add_argument("--clips", help="comma separated parts, e.g. eros07_p1,eros07_p4 (default: all)")
    ap.add_argument("--out", help="output folder for the scene folders (default: <archive>\\<character>\\vmd\\pc_<id>_hd)")
    ap.add_argument("--female-pmx")
    ap.add_argument("--male-pmx")
    ap.add_argument("--no-morphs", action="store_true")
    args = ap.parse_args()
    scene_bundle = find_bundle("chara_bare_pc_%s_nk.ab" % args.id)
    if not scene_bundle:
        sys.exit("no chara_bare_pc_%s_nk.ab: this outfit has no H scene in the game files" % args.id)
    env = UnityPy.load(scene_bundle)
    scenes = scenes_in(env)
    if args.list or not scenes:
        print("%s:" % os.path.basename(scene_bundle))
        for scene, rec in sorted(scenes.items()):
            print("   %s  her %s, him %s: %s" % (scene, rec["body"], rec["male"], ", ".join(rec["parts"])))
        if not scenes:
            print("   no H scene clips")
        return
    if args.scenes:
        scenes = {s: r for s, r in scenes.items() if s in args.scenes.split(",")}
    wanted = set(args.clips.split(",")) if args.clips else None
    outfit_pmx, outfit_character = find_pmx("pc_%s_hd" % args.id)
    shape_bundle = find_bundle("bare_blend_shape_pc_%s_nk.ab" % args.id)
    shapes = rbs.bundle_shapes(shape_bundle) if shape_bundle and not args.no_morphs else {}
    t0 = time.time()
    for scene, rec in sorted(scenes.items()):
        body, male = rec["body"], rec["male"] or MALE
        f_pmx, f_char = (args.female_pmx, None) if args.female_pmx else nude_pmx(body)
        m_pmx, _m_char = (args.male_pmx, None) if args.male_pmx else find_pmx(male)
        if not f_pmx or not m_pmx:
            sys.exit("PMX missing: %s -> %s, %s -> %s (pass --female-pmx / --male-pmx)" % (body, f_pmx, male, m_pmx))
        character = outfit_character or f_char or "Luf"
        base = args.out or default_out("pc_%s_hd" % args.id, character)
        out = os.path.join(base, scene)
        work = os.path.join(out, "_clips")
        os.makedirs(work, exist_ok=True)
        summary_path = os.path.join(work, "export_summary.txt")
        summary = open(summary_path, "w", encoding="utf-8")

        def log(line):
            print(line, flush=True)
            summary.write(line + "\n")
            summary.flush()

        log("ROE H scene %s of %s (%s)" % (scene, args.id, os.path.basename(scene_bundle)))
        log("   her PMX %s\n   his PMX %s" % (f_pmx, m_pmx))
        parts = [p for p in rec["parts"] if not wanted or p in wanted]
        actors = {"f": (body, f_pmx), "m": (male, m_pmx)}
        found = {a: body_skeleton(stem, log) for a, (stem, _p) in actors.items()}
        skeletons = {a: bones for a, (_bundle, bones) in found.items()}
        jsons = {"f": {}, "m": {}}
        frames = {}
        for part in parts:
            clips = dec.named_clips(env, part)
            for a, bones in skeletons.items():
                clip = dec.pick_clip(clips, bones)
                hits = dec.binding_hits(clip, bones)
                if hits < 20:
                    log("decode %s %-14s no clip of that name binds to %s (%d hits) - skipped" % (a, part, actors[a][0], hits))
                    continue
                js = os.path.join(work, "%s.%s.json" % (part, a))
                log("decode %s %s" % (a, dec.decode_clip(clip, bones, js)))
                jsons[a][part] = js
                frames[part] = len(json.load(open(js, encoding="utf-8"))["frames"])
        morphs = {a: {p: {} for p in jsons[a]} for a in jsons}
        if not args.no_morphs:
            for a in actors:
                if jsons[a]:
                    for part, vals in scale_morphs(actors[a][0], jsons[a], actors[a][1], work, False, log).items():
                        morphs[a][part].update(vals)
        # her scene shapes: TextAsset E07 belongs to eros07
        tag = "E" + scene[len("eros"):]
        mesh_shapes = shapes.get(tag, {})
        if mesh_shapes and jsons["f"]:
            model_env = UnityPy.load(found["f"][0])
            info = rbs.psm.parse(open(f_pmx, "rb").read())
            names = {}
            for mesh, srec in mesh_shapes.items():
                gv, guv = rbs.game_mesh(model_env, mesh)
                built = rbs.pmx_morphs(gv, guv, info, srec["shapes"], log=log)
                for target in pmx_copies(f_pmx):
                    got = rbs.add_morphs(target, built, log=log)
                    if target == f_pmx:
                        names.update(got)
            for part in jsons["f"]:
                bs = dec.named_clips(env, "%s@%s" % (body, part))
                if bs:
                    curves = dec.blendshape_curves(bs[0])
                    morphs["f"][part].update(rbs.clip_weights(curves, names, frames[part]))
            log("   her scene shapes: %s" % ", ".join("%s=%s" % kv for kv in sorted(names.items())))
        # one Blender run per actor and part
        for part in parts:
            for a, (stem, pmx) in actors.items():
                js = jsons[a].get(part)
                if not js:
                    continue
                pmx_stem = os.path.splitext(os.path.basename(pmx))[0]
                vmd = os.path.join(out, "%s_%s.vmd" % (pmx_stem, part))
                cmd = [BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "make_roe_vmd.py"), "--",
                       js, pmx, vmd]
                if morphs[a].get(part):
                    spec = os.path.join(work, "%s.%s.morphs.json" % (part, a))
                    json.dump(morphs[a][part], open(spec, "w", encoding="utf-8"), ensure_ascii=False)
                    cmd += ["--morphs", spec]
                lf = os.path.join(work, "%s.%s.log" % (part, a))
                code = run(cmd, lf)
                log("vmd %s %-14s exit %d  (%d s)" % (a, part, code, time.time() - t0))
                for line in grep(lf, "VMD written", "round trip", "morph keys", "Traceback", "Error: Python"):
                    log("   " + line.strip()[:260])
        log("done: %s, %d parts in %d s -> %s" % (scene, len(parts), time.time() - t0, out))
        summary.close()
        shutil.copy(summary_path, os.path.join(out, "export_summary.txt"))


if __name__ == "__main__":
    main()
