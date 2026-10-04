"""Export Taimanin Collection's 3D models to rigged .blend files with the game's materials (+ XPS, + MMD PMX).

    python export_model.py prf_asagi_costume_1 --xps --pmx --turntable   # Asagi: everything
    python export_model.py fbx_motorcycle_rig fbx_dropship_rig --xps     # the vehicles
    python export_model.py --category prop level scene                   # what the bike mini-game shows
    python export_model.py --game                                        # all of the above in one go
    python export_model.py prf_asagi_costume_1 --views                   # + 5 body and 4 face angles into _work/views/<id>

Per model:
  1. tcollection_scene.py reads the prefab (or the scene) from data.unity3d (UnityPy; the file is read whole,
     about 15 seconds): skeleton, renderers baked to the prefab pose, materials with every property, textures
     as PNG, Dynamic Bone chains, the face's story clips as shape keys -> <export-root>/_work/scenes/<id>/
     (removed after a good build unless --keep-work);
  2. Blender 3.6 runs Taimanin Squad's build_blend.py with this game's materials (tco_materials.py: Action
     Taimanin's Toony Colors Pro 2 for the character and the vehicles, a light-mapped unlit material for the
     scenery), renders the previews, packs the images and saves
         <export-root>/<Group>/blend/<id>/<id>.blend   (+ <id>_preview.png, <id>_face.png);
  3. --xps / --pmx / --turntable: Taimanin Squad's converters on that .blend -> <Group>/xps/<id>/,
     <Group>/pmx/<id>/ with their check pictures.  An existing .blend is reused (only converted) unless --force.

<Group> is the character's name (Asagi) or the kind of thing (Vehicles, Props, Levels, Scenes, Sets ...).
A summary of every run is kept in <export-root>/_meta/exports.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tcollection_common as tcc  # noqa: E402
from tcollection_common import tc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MATERIALS = os.path.join(HERE, "tco_materials.py")
GAME_SET = ("character", "vehicle", "prop", "level", "scene")     # --game: what the game itself shows
# where the preview of anything but a character looks from (Blender axes: a figure faces -Y, +Z is up):
# front, to its left, from above
PREVIEW_VIEW = "0.62,-0.66,0.42"
log = tcc.log


def squad_module(name: str):
    """A Taimanin Squad script as a module (its export_model.py has this file's name)."""
    spec = importlib.util.spec_from_file_location("squad_" + name, os.path.join(tcc.SQUAD_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


squad = squad_module("export_model")
KEEP = squad.KEEP + ("category", "dynamic_bones", "expression_shapes", "guessed_materials", "plain_materials",
                     "borrowed_materials")


def bust_settings(model: dict, a):
    """The PMX breast settings: Dynamic Bone has no travel limit to take over, so --bust on the defaults,
    fitted to the size of the breasts in Blender (tsquad_blender.spring_bust)."""
    return tc.bust_for_unit(tc.parse_bust(a.bust), None, a.bust), None


def converting(model: dict, a):
    """The options the format converters get for this model.  What is no character gets no turntable video and
    no dance / expression pictures of its PMX: those turn a figure and make it dance (a bridge does neither);
    its PMX is checked by the converter's own report, its XPS by the read-back picture."""
    if model["category"] == "character":
        return a
    options = argparse.Namespace(**vars(a))
    options.turntable, options.no_pmx_preview = False, True
    return options


def export_one(model: dict, a, game: tcc.Game) -> dict:
    import tcollection_scene as tcs

    t0 = time.time()
    model_id = model["id"]
    logs = os.path.join(tc.work_dir(a.export_root), "logs")
    blend = os.path.join(tc.model_dir(model, a.export_root, "blend"), model_id + ".blend")
    if os.path.isfile(blend) and not a.force:
        if a.xps or a.pmx or a.turntable:
            log("%s: reusing %s" % (model_id, blend))
            return squad.convert(model, blend, converting(model, a), {"id": model_id, "blend": blend, "reused_blend": True},
                                 game=tcc.GAME, bust_reader=bust_settings)
        log("%s: already exported (%s) - --force to redo" % (model_id, blend))
        return {"id": model_id, "skipped": True, "blend": blend}

    scene_dir = os.path.join(tc.work_dir(a.export_root), "scenes", model_id)
    if os.path.isdir(scene_dir):
        shutil.rmtree(scene_dir)
    log("%s: reading %s" % (model_id, model["key"]))
    scene = tcs.extract(model, scene_dir, game, include_inactive=a.inactive, expressions=not a.no_expressions)
    if scene.get("expressions"):
        log("%s: %d expression shapes (the game's clips + lip / gaze recipes): %s" % (
            model_id, len(scene["expressions"]), " ".join(e["name"] for e in scene["expressions"])))
    if scene.get("guessed_materials"):
        log("%s: %d material(s) lost their properties in the build - pictures taken by name: %s" % (
            model_id, len(scene["guessed_materials"]), ", ".join(scene["guessed_materials"])))
    if scene.get("plain_materials"):
        log("%s: %d material(s) lost their properties and no picture is named after them - left plain: %s" % (
            model_id, len(scene["plain_materials"]), ", ".join(scene["plain_materials"])))
    if scene.get("borrowed_materials"):
        worn = sorted({m for names in scene["borrowed_materials"].values() for m in names})
        log("%s: %d part(s) carry Unity's default material - dressed as the game dresses the same mesh: %s" % (
            model_id, len(scene["borrowed_materials"]), ", ".join(worn)))
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    log("%s: building %s (%d parts, %d bones, %d materials)" % (
        model_id, blend, len(scene["parts"]), len(scene["nodes"]), len(scene["materials"])))
    cmd = ["--background", "--factory-startup", "--python", squad.BUILD_SCRIPT, "--",
           "--scene", os.path.join(scene_dir, "scene.json"), "--out", blend, "--materials", MATERIALS]
    if a.no_preview:
        cmd.append("--no-preview")
    if model["category"] != "character":
        cmd += ["--preview-view", a.preview_view]
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
    report["guessed_materials"] = scene.get("guessed_materials") or []
    report["plain_materials"] = scene.get("plain_materials") or []
    report["borrowed_materials"] = scene.get("borrowed_materials") or {}
    report["seconds"] = round(time.time() - t0, 1)
    report["name"] = model["name"]
    report["category"] = model["category"]
    report["dynamic_bones"] = [{"name": c["name"], "roots": c["root_bones"]} for c in scene.get("cloth", [])]
    if not a.keep_work:
        shutil.rmtree(scene_dir, ignore_errors=True)
    return squad.convert(model, blend, converting(model, a), report, game=tcc.GAME, bust_reader=bust_settings)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="*", help="ids from list_models.py, wildcards ok")
    ap.add_argument("--category", choices=tcc.CATEGORY_ORDER, nargs="+", action="extend", default=[])
    ap.add_argument("--game", action="store_true",
                    help="what the game itself shows: %s (not the leftovers)" % ", ".join(GAME_SET))
    ap.add_argument("--all", action="store_true", help="every model, the leftovers too")
    ap.add_argument("--force", action="store_true", help="re-export even if the output exists")
    ap.add_argument("--reconvert", action="store_true",
                    help="redo the --xps / --pmx asked for from the .blend that is there")
    ap.add_argument("--repreview", action="store_true",
                    help="render the check pictures of the XPS / PMX that are there again (with --xps / --pmx)")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--preview-view", default=PREVIEW_VIEW, metavar="X,Y,Z",
                    help="where the preview of a vehicle / prop / set looks from, Blender axes (%(default)s: front, "
                         "to the left, from above); a character is always shown from the front")
    ap.add_argument("--views", action="store_true", help="also render 5 body + 4 face angles into _work/views/<id>")
    ap.add_argument("--turntable", action="store_true", help="also render <id>_turntable.mp4 next to the .blend")
    ap.add_argument("--xps", action="store_true", help="also write <Group>/xps/<id>/<id>.xps (Blender2XPS)")
    ap.add_argument("--no-xps-preview", action="store_true", help="skip the read-back render of the XPS")
    ap.add_argument("--xps-unlit", action="store_true", help="XPS: shadeless render groups (the flat game colours)")
    ap.add_argument("--pmx", action="store_true", help="also write <Group>/pmx/<id>/<id>.pmx (+ MMD previews)")
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
    ap.add_argument("--export-root", default=tcc.EXPORT_ROOT)
    a = ap.parse_args()
    if not (a.models or a.category or a.game or a.all):
        ap.error("name at least one model (python list_models.py shows them), --category, --game or --all")
    tc.parse_bust(a.bust)                               # a misspelt setting stops here, not in every model's log

    tcc.check_tools()
    game = tcc.Game()
    models = tcc.discover_models(a.export_root, game)
    wanted = set(a.category) | (set(GAME_SET) if a.game else set())
    chosen = list(models) if a.all else [m for m in models if m["category"] in wanted]
    if a.models:
        chosen += [m for m in tcc.find_models(models, a.models) if m not in chosen]

    reports, failed = [], []
    for i, model in enumerate(chosen, 1):
        log("(%d/%d) %s  %s" % (i, len(chosen), model["id"], tcc.CATEGORY_ZH.get(model["category"], model["category"])))
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
