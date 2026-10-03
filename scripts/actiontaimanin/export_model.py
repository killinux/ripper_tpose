"""Export Action Taimanin models to toon-shaded, rigged .blend files (+ XPS, + MMD PMX).

    python export_model.py asagi_costume_1_f              # one model (ids from list_models.py)
    python export_model.py asagi                          # every model of that character (figures, game, lobby)
    python export_model.py "asagi_costume_*_f" --xps --pmx   # wildcards; + XPS and MMD PMX next to the .blend
    python export_model.py asagi_costume_1_f --views      # + 5 body and 4 face angles into _work/views/<id>
    python export_model.py --category figure --jobs 4     # a whole category, 4 at a time

Per model:
  1. ataimanin_scene.py reads the unit prefab from the ``unit`` bundle and what it draws from ``model_char``
     (UnityPy, the bundles read block by block): skeleton, renderers baked to the prefab pose, materials with
     every property, textures as PNG -> <export-root>/_work/scenes/<id>/ (removed after a good build unless
     --keep-work);
  2. Blender 3.6 runs Taimanin Squad's build_blend.py with this game's materials (atm_materials.py: Toony
     Colors Pro 2 and Unity-Chan Toon Shader 2 in gamma space, parts colours, outline hull), renders a
     full-body and a face preview, packs the images and saves
         <export-root>/<Character>/blend/<id>/<id>.blend   (+ <id>_preview.png, <id>_face.png);
  3. --xps / --pmx / --turntable: Taimanin Squad's converters on that .blend (Blender2XPS; mmd_tools +
     Convert_to_MMD5 + mmd_cloth_physics) -> <Character>/xps/<id>/, <Character>/pmx/<id>/ with their check
     pictures.  An existing .blend is reused (only converted) unless --force.

A summary of every run is kept in <export-root>/_meta/exports.json (written model by model, so a batch
can be stopped and started again: what is already there is skipped).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ataimanin_common as ac  # noqa: E402
from ataimanin_common import tc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MATERIALS = os.path.join(HERE, "atm_materials.py")
log = ac.log


def squad_module(name: str):
    """A Taimanin Squad script as a module (its export_model.py has this file's name)."""
    spec = importlib.util.spec_from_file_location("squad_" + name, os.path.join(ac.SQUAD_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


squad = squad_module("export_model")
KEEP = squad.KEEP + ("category", "dynamic_bones", "expression_shapes")


def bust_settings(model: dict, a):
    """The PMX breast settings: Dynamic Bone has no travel limit to take over, so --bust on the defaults,
    fitted to the size of the breasts in Blender (tsquad_blender.spring_bust)."""
    return tc.bust_for_unit(tc.parse_bust(a.bust), None, a.bust), None


def export_one(model: dict, a, game: ac.Game) -> dict:
    import ataimanin_scene as asc

    t0 = time.time()
    model_id = model["id"]
    logs = os.path.join(tc.work_dir(a.export_root), "logs")
    blend = os.path.join(tc.model_dir(model, a.export_root, "blend"), model_id + ".blend")
    if os.path.isfile(blend) and not a.force:
        if a.xps or a.pmx or a.turntable:
            log("%s: reusing %s" % (model_id, blend))
            return squad.convert(model, blend, a, {"id": model_id, "blend": blend, "reused_blend": True},
                                 game=ac.GAME, bust_reader=bust_settings)
        log("%s: already exported (%s) - --force to redo" % (model_id, blend))
        return {"id": model_id, "skipped": True, "blend": blend}

    scene_dir = os.path.join(tc.work_dir(a.export_root), "scenes", model_id)
    if os.path.isdir(scene_dir):
        shutil.rmtree(scene_dir)
    log("%s: reading %s" % (model_id, model["key"]))
    scene = asc.extract_unit(model, scene_dir, game, include_inactive=a.inactive, expressions=not a.no_expressions)
    if scene.get("expressions"):
        log("%s: %d expression shapes (the game's clips + lip / gaze recipes): %s" % (
            model_id, len(scene["expressions"]), " ".join(e["name"] for e in scene["expressions"])))
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    log("%s: building %s (%d parts, %d bones, %d materials)" % (
        model_id, blend, len(scene["parts"]), len(scene["nodes"]), len(scene["materials"])))
    cmd = ["--background", "--factory-startup", "--python", squad.BUILD_SCRIPT, "--",
           "--scene", os.path.join(scene_dir, "scene.json"), "--out", blend, "--materials", MATERIALS]
    if a.no_preview:
        cmd.append("--no-preview")
    if a.no_outline:
        cmd.append("--no-outline")
    if a.no_weld:
        cmd.append("--no-weld")
    if a.views:
        cmd += ["--views", os.path.join(tc.work_dir(a.export_root), "views", model_id)]
    tiles = os.path.join(tc.work_dir(a.export_root), "tiles", model_id)
    shutil.rmtree(tiles, ignore_errors=True)
    if not a.no_preview:
        cmd += ["--tiles", tiles]
    log_path = os.path.join(logs, model_id + ".blender.log")
    report, code = squad.run_blender(cmd, "TSQ_REPORT=", log_path)
    if code != 0 or report is None or not os.path.isfile(blend):
        raise RuntimeError("Blender failed for %s (exit %d), log: %s" % (model_id, code, log_path))
    sheet = squad.expression_sheet(tiles, os.path.join(os.path.dirname(blend), model_id + "_expressions.png"))
    if sheet:
        report["expressions"] = sheet
    shutil.rmtree(tiles, ignore_errors=True)
    report["expression_shapes"] = [e["name"] for e in scene.get("expressions") or []]
    report["seconds"] = round(time.time() - t0, 1)
    report["name"] = model["name"]
    report["category"] = model["category"]
    report["dynamic_bones"] = [{"name": c["name"], "roots": c["root_bones"]} for c in scene.get("cloth", [])]
    if not a.keep_work:
        shutil.rmtree(scene_dir, ignore_errors=True)
    return squad.convert(model, blend, a, report, game=ac.GAME, bust_reader=bust_settings)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="*", help="ids or character names from list_models.py, wildcards ok")
    ap.add_argument("--category", choices=ac.CATEGORY_ORDER, action="append")
    ap.add_argument("--all", action="store_true", help="every model")
    ap.add_argument("--jobs", type=int, default=1, metavar="N", help="run N models at a time (N processes)")
    ap.add_argument("--shard", metavar="K/N", help="only every N-th model of the list, starting at the K-th "
                    "(what --jobs gives its workers)")
    ap.add_argument("--force", action="store_true", help="re-export even if the output exists")
    ap.add_argument("--reconvert", action="store_true",
                    help="redo the --xps / --pmx asked for from the .blend that is there")
    ap.add_argument("--repreview", action="store_true",
                    help="render the check pictures of the XPS / PMX that are there again (with --xps / --pmx)")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--views", action="store_true", help="also render 5 body + 4 face angles into _work/views/<id>")
    ap.add_argument("--turntable", action="store_true", help="also render <id>_turntable.mp4 next to the .blend")
    ap.add_argument("--xps", action="store_true", help="also write <Character>/xps/<id>/<id>.xps (Blender2XPS)")
    ap.add_argument("--no-xps-preview", action="store_true", help="skip the read-back render of the XPS")
    ap.add_argument("--xps-unlit", action="store_true", help="XPS: shadeless render groups (the flat game colours)")
    ap.add_argument("--pmx", action="store_true", help="also write <Character>/pmx/<id>/<id>.pmx (+ MMD previews)")
    ap.add_argument("--no-pmx-preview", action="store_true", help="skip the dance / morph preview renders of the PMX")
    ap.add_argument("--bust", default="", metavar="KEY=VALUE,...",
                    help="PMX breast physics, e.g. amount=1.3 (the settings and their defaults: "
                         "taimaninsquad/tsquad_common.BUST; fitted to the size of the breasts)")
    ap.add_argument("--keep-weapon", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-expressions", action="store_true",
                    help="without the shape keys made from the game's expression clips")
    ap.add_argument("--no-outline", action="store_true", help=".blend without the inverted-hull outline")
    ap.add_argument("--no-weld", action="store_true", help="keep Unity's split vertices (no UV-seam welding)")
    ap.add_argument("--inactive", action="store_true", help="also take renderers on inactive GameObjects")
    ap.add_argument("--keep-work", action="store_true", help="keep _work/scenes/<id> (scene.json, parts, PNG textures)")
    ap.add_argument("--export-root", default=ac.EXPORT_ROOT)
    a = ap.parse_args()
    if not (a.models or a.category or a.all):
        ap.error("name at least one model (python list_models.py shows them), --category or --all")
    tc.parse_bust(a.bust)                               # a misspelt setting stops here, not in every model's log

    ac.check_tools()
    game = ac.Game()
    models = ac.discover_models(a.export_root, game)
    chosen = list(models) if a.all else []
    if a.category:
        chosen += [m for m in models if m["category"] in a.category and m not in chosen]
    if a.models:
        chosen += [m for m in ac.find_models(models, a.models) if m not in chosen]
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        chosen = chosen[k - 1::n]
    elif a.jobs > 1 and len(chosen) > 1:
        jobs = min(a.jobs, len(chosen))
        log("%d models, %d at a time" % (len(chosen), jobs))
        return squad.run_workers(jobs, os.path.abspath(__file__))

    reports, failed = [], []
    for i, model in enumerate(chosen, 1):
        log("(%d/%d) %s  %s" % (i, len(chosen), model["id"], model["name"]))
        try:
            rep = export_one(model, a, game)
        except Exception as exc:  # noqa: BLE001 - keep going through a batch
            log("FAILED %s: %s" % (model["id"], exc))
            failed.append((model["id"], str(exc)))
            continue
        reports.append(rep)
        if rep.get("skipped"):
            continue
        tc.record_export(a.export_root, [{k: rep.get(k) for k in KEEP}])   # now: a batch may be stopped half way
        if not rep.get("reused_blend"):
            log("%s: %s  (%d verts, %d faces, %d bones, %d materials, %d shape keys, %.0f s)" % (
                rep["id"], rep.get("blend"), rep.get("vertices", 0), rep.get("faces", 0), rep.get("bones", 0),
                len(rep.get("materials_built", {})), rep.get("shape_keys", 0), rep["seconds"]))
        for key in ("turntable", "xps", "pmx"):
            if rep.get(key):
                log("  %s %s" % (key.upper(), rep[key]))
        pr = rep.get("pmx_report") or {}
        if pr.get("plain_rig"):
            log("  PMX: not a human figure - %s" % pr["plain_rig"])
        if pr:
            d = pr.get("distortion") or {}
            log("  PMX: %s bones, %s rigid bodies, torn %s, stretched %s, grant violations %d, bust %s, morphs %s" % (
                pr.get("bones"), pr.get("rigid_bodies"), d.get("torn"), d.get("stretched"),
                len(pr.get("grant_order_violations") or []), len(pr.get("bust_physics") or []),
                len(pr.get("vertex_morphs") or [])))
        for fit in (pr.get("bust_springs") or [])[:1]:
            log("  PMX breasts: size %s cm -> factor %s: travel %s cm, %s Hz, sag %s cm" % (
                fit.get("size_cm"), fit.get("factor"), fit.get("travel_cm"), fit.get("hz"), fit.get("sag_cm")))
        for w in rep.get("warnings", []):
            log("  ! " + w)
        if rep.get("missing_textures"):
            log("  ! missing textures: %s" % ", ".join(rep["missing_textures"]))
        if rep.get("convert_failed"):
            failed.append((rep["id"], "%s conversion failed (see the warnings above)" % "/".join(rep["convert_failed"])))
    done = [r for r in reports if not r.get("skipped")]
    log("done: %d built, %d skipped, %d failed" % (len(done), len(reports) - len(done), len(failed)))
    for mid, err in failed:
        log("  failed %s: %s" % (mid, err.splitlines()[0] if err else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
