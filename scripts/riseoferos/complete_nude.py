"""Rise of Eros: a dressed model with its whole body - the skin the game deleted under the outfit filled in from
the family nude base.  Makes two versions, each as .blend + XPS + PMX (+ bust B), and can copy them to E: with the
gallery:
  <stem>_nude   outfit removed
  <stem>_full   outfit kept over the whole body: in XPS the outfit meshes are optional items (+outfit|..., XNALara /
                XPS can hide them), in PMX the morph 衣服非表示 hides them; the .blend is what the clothes burst
                add-on works on

    python complete_nude.py a08                        # pc_a08_hd -> pc_a08_hd_nude + pc_a08_hd_full
    python complete_nude.py a08 g04 --archive          # ... then to E: + gallery
    python complete_nude.py a08 --archive-only         # no export: copy what is on D: to E: + gallery
    python complete_nude.py g04 --variants nude --formats blend,pmx
    python complete_nude.py pc_c05_hd --nude pc_c01_nk_bs --dry-run

Names: a main model's key (a08, a08_outfit1) or stem (pc_a08_hd), as in export_hq.py.  The nude base is the
family's pc_<letter>01_nk_bs (a08 -> pc_a01_nk_bs, g04 -> pc_g01_nk_bs) unless --nude names another one in
nude_materials\\ (a demon form: pc_<letter>01_fm_nk_bs).

Per version: complete_nude_body_blender.py (the body; how and why: docs/roe-complete-nude.md) -> the battle weapon
the HD model lacks (--weapon auto: weapon_dump.py + add_weapon_blender.py, a08's greatsword; a model that has its
own wp_* mesh keeps it) -> preview -> export_suit_xps_blender.py -> export_suit_pmx_blender.py -> PMX patches
(PMX_PATCHES: the weapon via pmx_add_weapon.py, g04's 扇子縮小 morph) -> tune_bust_pmx.py bust B.
Outputs on D:, beside the model's own:
  <id>\\blend\\<stem>_<version>.blend + _preview.png
  <id>\\blend\\xps\\<stem>_<version>\\<stem>_<version>.mesh (+ textures)
  <id>\\blend\\pmx\\<stem>_<version>\\<stem>_<version>.pmx + _bustB.pmx (+ textures\\)
Logs and result: D:\\roe_exports\\_hq_runs\\<stem>_nude\\.  Prints ROE_COMPLETE=<json>.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_hq as hq  # noqa: E402

VARIANTS = ("nude", "full")
# PMX patches other scripts make on the main model, done again on the completed versions: {key: [argv, ...]};
# {pmx} is the PMX, {cid} the outfit id.  The weapon one runs only when the version got an added weapon.
PMX_PATCHES = {
    "g04": [["pmx_add_scale_morph.py", "{pmx}", "{pmx}", "扇子縮小", "0.15", "fan_01", "Left_fan_01", "Left_fan_02",
             "Left_fan_03", "Right_fan_01", "Right_fan_02", "Right_fan_03"]],
}
# written beside the PMX, then moved over it: in place, pmx_add_weapon.py keeps the original in E:\_meta\pmx_old
WEAPON_PATCH = ["pmx_add_weapon.py", "{cid}", "--pmx", "{pmx}", "--out", "{tmp}"]


def nude_base(cid, name, exports):
    stem = name or "pc_%s01_nk_bs" % cid[0]
    stem = stem[:-6] if stem.endswith(".blend") else stem
    return stem, os.path.join(exports, "nude_materials", stem + ".blend")


def weapon_dump(cid, args, logs):
    """The battle weapon's dump (weapon_dump.py), or None when the outfit has none / it cannot be read."""
    out = os.path.join(logs, "weapon.json")
    code, text = hq.run([sys.executable, os.path.join(HERE, "weapon_dump.py"), cid, "--out", out],
                        os.path.join(logs, "weapon_dump.log"), args.dry_run)
    if args.dry_run:
        return out
    return out if code == 0 and os.path.isfile(out) else None


def run_patch(argv, values, logs, name, dry):
    """One PMX patch script; a patch that writes {tmp} has it moved over the PMX afterwards."""
    cmd = [sys.executable, os.path.join(HERE, argv[0])] + [a.format(**values) for a in argv[1:]]
    code, text = hq.run(cmd, os.path.join(logs, name + ".log"), dry)
    if code == 0 and not dry and os.path.isfile(values["tmp"]):
        os.replace(values["tmp"], values["pmx"])
    return "ok" if code == 0 else "FAILED (exit %d)" % code


def one_version(stem, variant, info, base_blend, args, logs, dump, result):
    """Build, weapon, preview, XPS, PMX + patches + bust B of one version; False on a failed step."""
    cid = info["cid"]
    name = "%s_%s" % (stem, variant)
    blend = os.path.join(args.exports, cid, "blend", name + ".blend")
    res = result.setdefault(variant, {})
    if "blend" in args.formats:
        code, data = hq.blender_step(args, info["blend"], "complete_nude_body_blender.py",
                                     ["--nude", base_blend, "--variant", variant, "--out", blend,
                                      "--report", os.path.join(logs, "complete_%s.json" % variant)],
                                     os.path.join(logs, "complete_%s.log" % variant), "ROE_COMPLETE_NUDE")
        if not args.dry_run:
            if code != 0 or data is None:
                res["error"] = "body step failed (exit %d), see %s" % (code, logs)
                return False
            res.update({k: data.get(k) for k in ("body", "weights", "fit", "outfit", "weapons", "aliases")})
        # the model's own weapon (g04's fan) or one added earlier (inherited from its .blend) stays as it is
        has_weapon = bool((data or {}).get("weapons")) and not args.dry_run
        if dump and (args.weapon == "yes" or not has_weapon):
            code, wdata = hq.blender_step(args, blend, "add_weapon_blender.py", ["--dump", dump],
                                          os.path.join(logs, "weapon_%s.log" % variant), "ROE_ADD_WEAPON")
            res["added_weapon"] = "dry" if args.dry_run else (wdata or "FAILED (exit %d)" % code)
        preview = os.path.splitext(blend)[0] + "_preview.png"
        if os.path.isfile(preview) and not args.dry_run:
            os.remove(preview)                      # a fresh one: the weapon / outfit may have changed
        hq.ensure_preview(name, {"blend": blend}, args, logs, res)
    if "xps" in args.formats:
        mesh = os.path.join(args.exports, cid, "blend", "xps", name, name + ".mesh")
        folder = os.path.dirname(mesh)
        if os.path.isdir(folder) and not args.dry_run:      # no textures left from an older export
            for f in os.listdir(folder):
                if f.lower().endswith((".mesh", ".png", ".json")):
                    os.remove(os.path.join(folder, f))
        code, data = hq.blender_step(args, blend, "export_suit_xps_blender.py", [mesh],
                                     os.path.join(logs, "xps_%s.log" % variant), "ROE_SUIT_XPS")
        if not args.dry_run:
            if code != 0 or data is None:
                res["xps"] = "FAILED (exit %d)" % code
                return False
            res["xps"] = {k: data.get(k) for k in ("meshes", "optional", "missing_textures", "unweighted_vertices")}
            if data.get("missing_textures") or data.get("unweighted_vertices"):
                return False
    if "pmx" in args.formats:
        pmx = os.path.join(args.exports, cid, "blend", "pmx", name, name + ".pmx")
        code, data = hq.blender_step(args, blend, "export_suit_pmx_blender.py", [pmx],
                                     os.path.join(logs, "pmx_%s.log" % variant), "ROE_SUIT_PMX")
        if not args.dry_run:
            if code != 0 or data is None:
                res["pmx"] = "FAILED (exit %d)" % code
                return False
            res["pmx"] = {"torn": data.get("torn"), "morphs": data.get("face_morphs"),
                          "morph_kind": data.get("morph_kind"), "vertex_morph_bake": data.get("vertex_morph_bake"),
                          "bust": (data.get("physics") or {}).get("bust"),
                          "grant_order_violations": data.get("grant_order_violations"),
                          "outfit_morph": (data.get("prep") or {}).get("outfit_morph")}
        values = {"pmx": pmx, "cid": cid, "tmp": pmx[:-4] + ".patch.tmp.pmx"}
        patches = []
        # the PMX export leaves an added weapon out: pmx_add_weapon.py appends it with its hide morph
        if args.dry_run and dump or (data or {}).get("prep", {}).get("left_out_weapon"):
            patches.append(("weapon", WEAPON_PATCH))
        for k, argv in enumerate(PMX_PATCHES.get(info.get("key", ""), [])):
            patches.append(("patch%d" % k, argv))
        for label, argv in patches:
            res.setdefault("pmx_patches", {})[label] = run_patch(argv, values, logs, "%s_%s" % (label, variant),
                                                                 args.dry_run)
        bust_log = os.path.join(logs, "bustB_%s" % variant)
        res["bustB"] = hq.bust_b(pmx, bust_log, args.dry_run, args.exports)
    return True


def complete_one(stem, info, args):
    logs = os.path.join(args.exports, "_hq_runs", stem + "_nude")
    base, base_blend = nude_base(info["cid"], args.nude, args.exports)
    result = {"stem": stem, "nude_base": base, "variants": args.variants, "formats": args.formats}
    if not args.dry_run and not os.path.isfile(base_blend):
        result.update(ok=False, error="no nude base " + base_blend)
        return result
    dump = weapon_dump(info["cid"], args, logs) if args.weapon != "no" and "blend" in args.formats else None
    result["weapon_dump"] = bool(dump)
    for variant in args.variants:
        if not one_version(stem, variant, info, base_blend, args, logs, dump, result):
            result["ok"] = False
            return result
    result["ok"] = True
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="main model key (a08) or stem (pc_a08_hd)")
    ap.add_argument("--nude", default="", help="nude base stem in nude_materials (default pc_<letter>01_nk_bs)")
    ap.add_argument("--variants", default=",".join(VARIANTS), help="nude,full (default both)")
    ap.add_argument("--formats", default=",".join(hq.FORMATS), help="blend,pmx,xps (default all three)")
    ap.add_argument("--weapon", choices=("auto", "yes", "no"), default="auto",
                    help="auto: add the battle weapon when the model has no wp_* mesh of its own")
    ap.add_argument("--pmx-morphs", choices=("vertex", "bone"), default=None,
                    help="PMX expressions as vertex morphs (default) or bone morphs (env ROE_PMX_MORPHS)")
    ap.add_argument("--archive", action="store_true", help="afterwards: gallery + copy these models to E:")
    ap.add_argument("--archive-only", action="store_true", help="no export: gallery + copy what is on D: to E:")
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    ap.add_argument("--exports", default=hq.EXPORTS)
    ap.add_argument("--archive-root", default=hq.ARCHIVE)
    ap.add_argument("--blender", default=hq.BLENDER)
    args = ap.parse_args()
    args.variants = [v for v in VARIANTS if v in args.variants.split(",")]
    args.formats = [f for f in hq.FORMATS if f in args.formats.split(",")]
    if args.pmx_morphs:
        os.environ["ROE_PMX_MORPHS"] = args.pmx_morphs       # every Blender run below inherits it
    cat = hq.catalogue(args.exports)
    results, stems = [], []
    for name in args.names:
        stem = hq.resolve(name, cat)
        if not stem or cat[stem][0] != "main":
            sys.exit("not a dressed main model: %s  (python export_hq.py --list shows the names)" % name)
        print("== %s -> %s" % (stem, ", ".join("%s_%s" % (stem, v) for v in args.variants)), flush=True)
        t0 = time.time()
        if args.archive_only:
            args.archive = True
            result = {"stem": stem, "ok": True, "archive_only": True}
        else:
            result = complete_one(stem, cat[stem][1], args)
        result["seconds"] = round(time.time() - t0)
        result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if not args.dry_run and not args.archive_only:
            logs = os.path.join(args.exports, "_hq_runs", stem + "_nude")
            os.makedirs(logs, exist_ok=True)
            earlier = hq.load_json(os.path.join(logs, "result.json"), {})
            for variant in VARIANTS:                 # a run of one version / format keeps the other's results
                if variant not in result and variant in earlier:
                    result[variant] = earlier[variant]
                elif variant in result and variant in earlier and len(args.formats) < len(hq.FORMATS):
                    kept = {k: v for k, v in earlier[variant].items() if k != "error"}    # an old run's failure
                    result[variant] = dict(kept, **result[variant])
            with open(os.path.join(logs, "result.json"), "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=1, default=str)
        print("   -> %s" % json.dumps({k: v for k, v in result.items() if k != "stem"}, ensure_ascii=False,
                                       default=str), flush=True)
        results.append(result)
        if result.get("ok"):
            for variant in args.variants:
                done = "%s_%s" % (stem, variant)
                stems.append(done)
                cat[done] = ("nude", {"cid": cat[stem][1]["cid"],
                                      "blend": os.path.join(args.exports, cat[stem][1]["cid"], "blend", done + ".blend")})
    summary = {"models": results, "failed": [r["stem"] for r in results if not r.get("ok")]}
    if args.archive and stems:
        print("== archive %s" % ", ".join(stems), flush=True)
        summary["archive"] = hq.archive(stems, cat, args)
        print("   -> %s" % json.dumps(summary["archive"], ensure_ascii=False))
    print("ROE_COMPLETE=" + json.dumps(summary, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
