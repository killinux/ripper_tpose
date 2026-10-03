"""Export Taimanin Squad units to toon-shaded, rigged .blend files (+ XPS, + MMD PMX).

    python export_model.py 24_kirara                 # one model (ids from list_models.py)
    python export_model.py kirara asagi 7            # names (every model of that character) / unit numbers
    python export_model.py --category character      # a whole category
    python export_model.py --female --xps --pmx --turntable --jobs 4   # every female figure, 4 at a time
    python export_model.py 24_kirara --xps --pmx     # + XPS and MMD PMX next to the .blend
    python export_model.py 24_kirara --views         # + 5 body and 4 face angles into _work/views/<id>
    python export_model.py 24_kirara --turntable     # + <id>_turntable.mp4 (one turn, then a light sweep on the face)
    python export_model.py 24_kirara --weapons       # + the weapons the game hangs on the unit (see below)
    python export_model.py --all --preview-only      # only preview images into _work/previews (surveys)

Per model:
  1. tsquad_scene.py reads the unit prefab from the art bundle (UnityPy): skeleton, renderers baked to
     the prefab pose, blend shapes, materials with every property of the game's toon shader, textures
     as PNG -> <export-root>/_work/scenes/<id>/ (removed after a good build unless --keep-work).
     The weapon prefabs of the unit's other bundle that are parts of the BODY come along by themselves
     (Natsume's left arm, Saika's legs: the game keeps them in the weapon slot); --weapons also takes
     the real weapons, where the prefab pose has them (many wait at the origin for an animation: those
     stay hidden in the .blend and out of the XPS / PMX unless --keep-weapon); --weapon-grade 1 / 2 =
     the upgraded looks;
  2. Blender 3.6 (build_blend.py) builds the armature, welds the UV-seam splits, rebuilds the toon
     shader (shade map, mask map, MatCap, SDF face shadow, rim, outline hull), renders a full-body and a
     face preview, packs the images and saves
         <export-root>/<Character>/blend/<id>/<id>.blend   (+ <id>_preview.png, <id>_face.png)
     so every model folder opens on its own (the E:\\game_export convention);
  3. --xps: export_xps_blender.py (Blender2XPS) -> <Character>/xps/<id>/<id>.xps;
     --pmx: export_pmx_blender.py (mmd_tools + Convert_to_MMD5 + mmd_cloth_physics, the chain the other
     games use) -> <Character>/pmx/<id>/<id>.pmx, then scripts/stellarblade/preview_pmx_blender.py
     renders preview / gaze / dance next to it.  An existing .blend is reused (only converted) unless
     --force.

A summary of every run is kept in <export-root>/_meta/exports.json (written model by model, so a
batch can be stopped and started again: what is already there is skipped).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_SCRIPT = os.path.join(HERE, "build_blend.py")
XPS_SCRIPT = os.path.join(HERE, "export_xps_blender.py")
PMX_SCRIPT = os.path.join(HERE, "export_pmx_blender.py")
XPS_PREVIEW = os.path.join(HERE, "preview_xps_blender.py")
TURNTABLE = os.path.join(HERE, "render_turntable.py")
PMX_MORPHS = os.path.join(HERE, "preview_pmx_morphs.py")
PMX_PREVIEW = os.path.join(os.path.dirname(HERE), "stellarblade", "preview_pmx_blender.py")
KEEP = ("id", "name", "blend", "preview", "face", "expressions", "vertices", "faces", "bones", "shape_keys",
        "materials_built", "warnings", "seconds", "size_m", "turntable", "xps", "xps_stats", "xps_preview", "pmx",
        "pmx_report", "pmx_preview", "pmx_morph_sheet", "skipped", "weapon_prefabs")
log = tc.log


def run_blender(args: list[str], marker: str, log_path: str, timeout: int = 3600) -> tuple[dict | None, int]:
    """Run Blender, keep its log, return the JSON after `marker` on the last matching line."""
    r = subprocess.run([tc.BLENDER] + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""))
    line = next((ln for ln in reversed((r.stdout or "").splitlines()) if ln.startswith(marker)), "")
    return (json.loads(line[len(marker):]) if line else None), r.returncode


def label_font(size: int = 15):
    """A font that can write the MMD morph names (kana / kanji); None when Windows has none of them."""
    from PIL import ImageFont

    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("meiryo.ttc", "YuGothM.ttc", "msgothic.ttc", "msyh.ttc"):
        try:
            return ImageFont.truetype(os.path.join(fonts, name), size)
        except OSError:
            continue
    return None


def tile_sheet(tiles: list[tuple[str, str]], out_path: str, columns: int = 6, size: int = 300) -> str | None:
    """Join (png path, label) pairs into one labelled picture."""
    if len(tiles) < 2:
        return None
    from PIL import Image, ImageDraw

    label = 22
    font = label_font()
    columns = min(columns, len(tiles))
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * size, rows * (size + label)), (32, 32, 36))
    draw = ImageDraw.Draw(sheet)
    for i, (path, text) in enumerate(tiles):
        tile = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
        x, y = (i % columns) * size, (i // columns) * (size + label)
        sheet.paste(tile, (x, y + label))
        if font is None:                               # the default font is Latin-1 only
            text = text.encode("ascii", "ignore").decode().strip() or "?"
        draw.text((x + 5, y + 2), text, fill=(235, 235, 160), font=font)
    sheet.save(out_path)
    return out_path


def expression_sheet(tiles_dir: str, out_path: str, columns: int = 6) -> str | None:
    """Tile the per-shape-key face renders (build_blend.py --tiles) into one labelled picture."""
    if not os.path.isdir(tiles_dir):
        return None
    files = sorted(f for f in os.listdir(tiles_dir) if f.lower().endswith(".png"))
    return tile_sheet([(os.path.join(tiles_dir, f), os.path.splitext(f)[0].split("_", 1)[1]) for f in files],
                      out_path, columns)


def pmx_morph_sheet(model_id: str, pmx: str, a, logs: str) -> dict | None:
    """preview_morphs.png next to the PMX: one labelled tile per MMD morph, read back from the file."""
    tiles = os.path.join(tc.work_dir(a.export_root), "tiles", model_id + "_pmx")
    shutil.rmtree(tiles, ignore_errors=True)
    rep, _code = run_blender(["-b", "--python", PMX_MORPHS, "--", "--pmx", pmx, "--tiles", tiles, "--all"],
                             "PMX_MORPHS=", os.path.join(logs, model_id + ".pmx_morphs.log"))
    out = None
    if rep and rep.get("tiles"):
        pairs = [(t["file"], ("%s  %s" % (t["name"], t["name_e"])).strip() if t["name"] != t["name_e"] else t["name"])
                 for t in rep["tiles"]]
        sheet = tile_sheet(pairs, os.path.join(os.path.dirname(pmx), "preview_morphs.png"))
        out = {"sheet": sheet, "morphs": len(pairs) - 1}
    shutil.rmtree(tiles, ignore_errors=True)
    return out


def pmx_previews(model_id: str, pmx: str, a, logs: str, report: dict) -> None:
    """The check pictures next to a PMX: preview.png / preview_dance.png (read back, a dance with physics -
    lit the way MMD shows a toon model, a material comes out as its texture, and simulated the way MMD
    runs the joints, not the stiffer way mmd_tools leaves them) and preview_morphs.png."""
    if os.path.isfile(PMX_PREVIEW):
        prev, _code = run_blender(["-b", "--python", PMX_PREVIEW, "--", "--pmx", pmx, "--look", "mmd",
                                   "--physics", "mmd"],
                                  "PMX_PREVIEW=", os.path.join(logs, model_id + ".pmx_preview.log"))
        if prev:
            report["pmx_preview"] = {k: prev.get(k) for k in ("rest_drop_test", "max_rigid_body_distance_from_hips_m")}
    sheet = pmx_morph_sheet(model_id, pmx, a, logs)    # after the dance preview: this one replaces its morph sheet
    if sheet:
        report["pmx_morph_sheet"] = sheet["sheet"]


def xps_preview(model_id: str, xps: str, logs: str, report: dict) -> None:
    """<id>_xps_preview.png: the XPS read back with the XNALaraMesh importer and posed."""
    prev, _code = run_blender(["-b", "--python", XPS_PREVIEW, "--", "--xps", xps], "XPS_PREVIEW=",
                              os.path.join(logs, model_id + ".xps_preview.log"))
    if prev:
        report["xps_preview"] = prev.get("preview")


def export_one(model: dict, a) -> dict:
    import tsquad_scene as ts

    t0 = time.time()
    model_id = model["id"]
    logs = os.path.join(tc.work_dir(a.export_root), "logs")
    out_dir = os.path.join(tc.work_dir(a.export_root), "previews") if a.preview_only \
        else tc.model_dir(model, a.export_root, "blend")
    blend = os.path.join(out_dir, model_id + ".blend")
    if os.path.isfile(blend) and not a.force and not a.preview_only:
        if a.xps or a.pmx or a.turntable:
            log("%s: reusing %s" % (model_id, blend))
            return convert(model, blend, a, {"id": model_id, "blend": blend, "reused_blend": True})
        log("%s: already exported (%s) - --force to redo" % (model_id, blend))
        return {"id": model_id, "skipped": True, "blend": blend}

    scene_dir = os.path.join(tc.work_dir(a.export_root), "scenes", model_id)
    if os.path.isdir(scene_dir):
        shutil.rmtree(scene_dir)
    log("%s: reading %s from %s" % (model_id, model["key"], model["bundle"]))
    scene = ts.extract_unit(model, scene_dir, a.export_root, include_inactive=a.inactive,
                            weapons="none" if a.no_weapon_prefabs else "all" if a.weapons else "limbs",
                            weapon_grade=a.weapon_grade)
    for w in scene.get("weapon_prefabs") or []:
        log("%s: + %s on %s (%s)" % (model_id, w["name"], w["bone"],
                                     "a part of the body" if w["kind"] == "limb" else "weapon"))
    os.makedirs(out_dir, exist_ok=True)
    log("%s: building %s (%d parts, %d bones, %d materials)" % (
        model_id, blend, len(scene["parts"]), len(scene["nodes"]), len(scene["materials"])))
    cmd = ["--background", "--factory-startup", "--python", BUILD_SCRIPT, "--",
           "--scene", os.path.join(scene_dir, "scene.json"), "--out", blend]
    if a.no_preview and not a.preview_only:
        cmd.append("--no-preview")
    if a.preview_only:
        cmd.append("--no-save")
    if a.no_outline:
        cmd.append("--no-outline")
    if a.no_weld:
        cmd.append("--no-weld")
    if a.views:
        cmd += ["--views", os.path.join(tc.work_dir(a.export_root), "views", model_id)]
    tiles = os.path.join(tc.work_dir(a.export_root), "tiles", model_id)
    shutil.rmtree(tiles, ignore_errors=True)
    if not a.no_preview and not a.preview_only:
        cmd += ["--tiles", tiles]
    log_path = os.path.join(logs, model_id + ".blender.log")
    report, code = run_blender(cmd, "TSQ_REPORT=", log_path)
    if code != 0 or report is None or (not a.preview_only and not os.path.isfile(blend)):
        raise RuntimeError("Blender failed for %s (exit %d), log: %s" % (model_id, code, log_path))
    sheet = expression_sheet(tiles, os.path.join(out_dir, model_id + "_expressions.png"))
    if sheet:
        report["expressions"] = sheet
    shutil.rmtree(tiles, ignore_errors=True)
    report["seconds"] = round(time.time() - t0, 1)
    report["name"] = model["name"]
    report["cloth_groups"] = [c["name"] for c in scene.get("cloth", [])]
    report["weapon_prefabs"] = [{k: w.get(k) for k in ("name", "kind", "bone", "parts")}
                                for w in scene.get("weapon_prefabs") or []]
    if not a.keep_work:
        shutil.rmtree(scene_dir, ignore_errors=True)
    if a.preview_only:
        report["preview_only"] = True
        return report
    return convert(model, blend, a, report)


_LOADERS: dict = {}
_LOADER_LOCK = threading.Lock()                        # dance_video.py --jobs asks from several threads


def bust_settings(model: dict, a) -> tuple[dict, dict | None]:
    """(the breast physics settings for this unit, its Bone Spring values or None): --bust put into the
    defaults, and how far the game lets this unit's breasts travel as cap_cm (tsquad_common.bust_for_unit).
    Blender then fits them to the size of the breasts (tsquad_blender.spring_bust)."""
    import tsquad_scene as ts

    base = tc.parse_bust(a.bust)
    spring = None
    if base["style"] == "spring" and base["game"] >= 0.5:
        try:
            with _LOADER_LOCK:
                if a.export_root not in _LOADERS:
                    _LOADERS[a.export_root] = ts.Loader(a.export_root)
                spring = ts.breast_spring(model, _LOADERS[a.export_root])
        except Exception as exc:  # noqa: BLE001 - the defaults are a usable answer
            log("%s: the game's breast settings could not be read (%s) - no travel limit from the game" % (model["id"], exc))
    return tc.bust_for_unit(base, spring, a.bust), spring


def convert(model: dict, blend: str, a, report: dict) -> dict:
    """--turntable / --xps / --pmx from the finished .blend into <Character>/blend|xps|pmx/<id>/."""
    model_id = model["id"]
    logs = os.path.join(tc.work_dir(a.export_root), "logs")
    title = "%s (%s)" % (model["name"], model_id)
    if a.turntable:
        video = os.path.join(os.path.dirname(blend), model_id + "_turntable.mp4")
        if os.path.isfile(video) and not a.force:
            report["turntable"] = video
        else:
            log("%s: turntable video ..." % model_id)
            rep, _code = run_blender(["-b", blend, "--python", TURNTABLE, "--", "--out", video],
                                     "TSQ_TURNTABLE=", os.path.join(logs, model_id + ".turntable.log"))
            if rep and os.path.isfile(video):
                report["turntable"] = video
            else:
                report.setdefault("warnings", []).append("turntable failed, log: %s"
                                                         % os.path.join(logs, model_id + ".turntable.log"))
    if a.xps:
        xps_root = os.path.join(a.export_root, model["group"], "xps")
        xps = os.path.join(xps_root, model_id, model_id + ".xps")
        if os.path.isfile(xps) and not (a.force or a.reconvert):
            report["xps"] = xps
            if a.repreview:
                log("%s: XPS check picture ..." % model_id)
                xps_preview(model_id, xps, logs, report)
        else:
            log("%s: XPS ..." % model_id)
            if os.path.isdir(os.path.dirname(xps)):    # a generated folder: start clean, no stale textures
                shutil.rmtree(os.path.dirname(xps))
            cmd = ["-b", blend, "--python", XPS_SCRIPT, "--", "--out", xps_root]
            if a.xps_unlit:
                cmd.append("--unlit")
            if a.keep_weapon:
                cmd.append("--keep-weapon")
            rep, _code = run_blender(cmd, "TSQ_XPS=", os.path.join(logs, model_id + ".xps.log"))
            if not rep or not rep.get("ok"):
                report.setdefault("warnings", []).append("XPS failed: %s" % ((rep or {}).get("errors") or "see the log"))
                report.setdefault("convert_failed", []).append("xps")
            else:
                report["xps"] = rep["path"]
                report["xps_stats"] = rep.get("stats")
                if not a.no_xps_preview:               # read it back with the XNALaraMesh importer, pose it
                    xps_preview(model_id, rep["path"], logs, report)
    if a.pmx:
        pmx_root = os.path.join(a.export_root, model["group"], "pmx")
        pmx = os.path.join(pmx_root, model_id, model_id + ".pmx")
        if os.path.isfile(pmx) and not (a.force or a.reconvert):
            report["pmx"] = pmx
            if a.repreview:
                log("%s: PMX check pictures ..." % model_id)
                pmx_previews(model_id, pmx, a, logs, report)
        else:
            log("%s: PMX ..." % model_id)
            comment = ("%s - Taimanin Squad (%s)\\nConverted by ripper_tpose "
                       "(scripts/taimaninsquad/export_pmx_blender.py). Personal use only." % (title, model["key"]))
            bust, spring = bust_settings(model, a)
            rep, _code = run_blender(["-b", blend, "--python", PMX_SCRIPT, "--", "--out", pmx_root,
                                      "--model-name", title[:60], "--comment", comment,
                                      "--bust", tc.bust_text(bust)]
                                     + (["--keep-weapon"] if a.keep_weapon else []),
                                     "TSQ_PMX=", os.path.join(logs, model_id + ".pmx.log"))
            if not rep or not os.path.isfile(pmx):
                report.setdefault("warnings", []).append("PMX failed, log: %s" % os.path.join(logs, model_id + ".pmx.log"))
                report.setdefault("convert_failed", []).append("pmx")
            else:
                report["pmx"] = pmx
                report["pmx_report"] = {k: rep.get(k) for k in (
                    "height_m", "bones", "rigid_bodies", "joints", "distortion", "weight_holes",
                    "grant_order_violations", "bust_physics", "vertex_morphs", "missing_optional_slots",
                    "plain_rig", "bust_style", "bust_springs")}
                report["pmx_report"]["morphs_made"] = (rep.get("morphs") or {}).get("made")
                report["pmx_report"]["morphs_skipped"] = (rep.get("morphs") or {}).get("skipped")
                if rep.get("bust_springs"):            # what the breasts were given, and from which game values
                    report["pmx_report"]["bust_settings"] = {k: bust[k] for k in tc.BUST if k != "style"}
                    report["pmx_report"]["bust_game"] = spring
                if not a.no_pmx_preview:
                    pmx_previews(model_id, pmx, a, logs, report)
    return report


def run_workers(jobs: int) -> int:
    """--jobs: this same command line in `jobs` processes, worker k taking every jobs-th model of the list."""
    args, skip = [], False
    for arg in sys.argv[1:]:
        if skip:
            skip = False
        elif arg == "--jobs":
            skip = True
        elif not arg.startswith("--jobs="):
            args.append(arg)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__)] + args + ["--shard", "%d/%d" % (k, jobs)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace", env=env) for k in range(1, jobs + 1)]

    def pump(k, proc):
        for line in proc.stdout:
            print("%d| %s" % (k, line.rstrip("\n")), flush=True)

    threads = [threading.Thread(target=pump, args=(k, p), daemon=True) for k, p in enumerate(procs, 1)]
    for t in threads:
        t.start()
    try:
        codes = [p.wait() for p in procs]
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        raise
    for t in threads:
        t.join()
    return max(codes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="*", help="ids / unit numbers / names from list_models.py, wildcards ok")
    ap.add_argument("--category", choices=tc.CATEGORY_ORDER, action="append")
    ap.add_argument("--female", action="store_true",
                    help="every female figure (list_models.py --female: breast bones, plus a few picked by eye)")
    ap.add_argument("--all", action="store_true", help="every model (252)")
    ap.add_argument("--jobs", type=int, default=1, metavar="N",
                    help="run N models at a time (N processes; a model takes about 2 minutes with everything)")
    ap.add_argument("--shard", metavar="K/N", help="only every N-th model of the list, starting at the K-th "
                    "(what --jobs gives its workers; also for running the parts in separate terminals)")
    ap.add_argument("--force", action="store_true", help="re-export even if the output exists")
    ap.add_argument("--reconvert", action="store_true",
                    help="redo the --xps / --pmx asked for from the .blend that is there (the .blend and the "
                         "turntable are kept; --force redoes those too)")
    ap.add_argument("--repreview", action="store_true",
                    help="render the check pictures of the XPS / PMX that are there again (with --xps / --pmx)")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--views", action="store_true", help="also render 5 body + 4 face angles into _work/views/<id>")
    ap.add_argument("--preview-only", action="store_true",
                    help="only render <id>_preview.png / _face.png into _work/previews, no .blend (for surveys)")
    ap.add_argument("--turntable", action="store_true",
                    help="also render <id>_turntable.mp4 next to the .blend (one turn + a light sweep on the face)")
    ap.add_argument("--xps", action="store_true", help="also write <Character>/xps/<id>/<id>.xps (Blender2XPS)")
    ap.add_argument("--no-xps-preview", action="store_true", help="skip the read-back render of the XPS")
    ap.add_argument("--xps-unlit", action="store_true", help="XPS: shadeless render groups (the flat game colours)")
    ap.add_argument("--pmx", action="store_true", help="also write <Character>/pmx/<id>/<id>.pmx (+ MMD previews)")
    ap.add_argument("--no-pmx-preview", action="store_true", help="skip the dance / morph preview renders of the PMX")
    ap.add_argument("--bust", default="", metavar="KEY=VALUE,...",
                    help="PMX breast physics, e.g. bounce_hz=3,ratio=0.2 or amount=1.3 (the settings and their "
                         "defaults: tsquad_common.BUST - the values as tuned on Asagi; each unit gets them fitted to "
                         "the size of its breasts and to the travel the game allows it; size_cm=0,game=0 gives "
                         "everyone the same; style=swing = the pivot template of before 2026-10-02)")
    ap.add_argument("--weapons", action="store_true",
                    help="also hang the unit's real weapons on it (swords, guns, crowns, tentacles: the weapon "
                         "prefabs of its other bundle), where the prefab pose has them; the body parts the game "
                         "keeps as weapons (Natsume's arm, Saika's legs) are taken without asking")
    ap.add_argument("--weapon-grade", type=int, default=0, choices=(0, 1, 2),
                    help="which look of the weapon prefabs: 0 = the first (default), 1 / 2 = the upgraded ones")
    ap.add_argument("--no-weapon-prefabs", action="store_true",
                    help="the unit prefab alone, no weapon prefab at all (not even the arms and legs)")
    ap.add_argument("--keep-weapon", action="store_true",
                    help="XPS / PMX: also take the weapons that are parked at the origin in the prefab pose")
    ap.add_argument("--no-outline", action="store_true", help=".blend without the inverted-hull outline")
    ap.add_argument("--no-weld", action="store_true", help="keep Unity's split vertices (no UV-seam welding)")
    ap.add_argument("--inactive", action="store_true", help="also take renderers on inactive GameObjects")
    ap.add_argument("--keep-work", action="store_true", help="keep _work/scenes/<id> (scene.json, parts, PNG textures)")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    if not (a.models or a.category or a.female or a.all):
        ap.error("name at least one model (python list_models.py shows them), --category, --female or --all")
    tc.parse_bust(a.bust)                               # a misspelt setting stops here, not in every model's log

    tc.check_tools(need_blender=True)
    models = tc.discover_models(tc.catalog_assets(a.export_root), a.export_root)
    chosen = list(models) if a.all else []
    if a.category:
        chosen += [m for m in models if m["category"] in a.category and m not in chosen]
    if a.female:
        import list_models

        list_models.add_details(models, a.export_root)
        chosen += [m for m in models if tc.is_female(m) and m not in chosen]
    if a.models:
        chosen += [m for m in tc.find_models(models, a.models) if m not in chosen]
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        chosen = chosen[k - 1::n]
    elif a.jobs > 1 and len(chosen) > 1:
        jobs = min(a.jobs, len(chosen))
        log("%d models, %d at a time" % (len(chosen), jobs))
        return run_workers(jobs)

    reports, failed = [], []
    for i, model in enumerate(chosen, 1):
        log("(%d/%d) %s  %s" % (i, len(chosen), model["id"], model["name"]))
        try:
            rep = export_one(model, a)
        except Exception as exc:  # noqa: BLE001 - keep going through a batch
            log("FAILED %s: %s" % (model["id"], exc))
            failed.append((model["id"], str(exc)))
            continue
        reports.append(rep)
        if rep.get("skipped"):
            continue
        if not rep.get("preview_only"):                # now, not at the end: a batch may be stopped half way
            tc.record_export(a.export_root, [{k: rep.get(k) for k in KEEP}])
        if not rep.get("reused_blend"):
            log("%s: %s  (%d verts, %d faces, %d bones, %d materials, %d shape keys, %.0f s)" % (
                rep["id"], rep.get("blend") or rep.get("preview"), rep.get("vertices", 0), rep.get("faces", 0),
                rep.get("bones", 0), len(rep.get("materials_built", {})), rep.get("shape_keys", 0), rep["seconds"]))
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
            log("  PMX breasts: size %s cm, the game allows %s cm -> factor %s: travel %s cm, %s Hz, sag %s cm" % (
                fit.get("size_cm"), fit.get("cap_cm") or "any", fit.get("factor"), fit.get("travel_cm"),
                fit.get("hz"), fit.get("sag_cm")))
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
