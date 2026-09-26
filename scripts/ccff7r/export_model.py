"""Export CRISIS CORE -FINAL FANTASY VII- REUNION models to textured, rigged .blend files.

    python export_model.py tifa                      # one model (ids from list_models.py)
    python export_model.py tifa aerith zack_s12      # several
    python export_model.py --category named          # the whole main cast
    python export_model.py Zack                      # a group: every zack_* model
    python export_model.py tifa --sw                 # the "_SW" twin (same mesh, *_Lite materials)
    python export_model.py tifa --xps --pmx          # + XPS and MMD PMX next to the .blend

Per model:
  1. CUE4Parse CLI -> ActorX .psk (skeleton + LODs, highest kept) + every texture its materials use as
     PNG, into <export-root>/_work/raw (a cache; the CLI's own material files are empty "{}");
  2. the mesh and its material instances as JSON (-f json) -> slot -> instance -> parent chain; the
     parameters are merged child-over-parent, so a value the instance leaves at its parent's default
     (MI_ch_Human_Skin's pore maps, MI_ch_Human_Mouth's teeth textures) is still found;
  3. each slot gets a family from the shared parent it derives from (MI_ch_Standard / EMStandard,
     Human_Skin / Human_Mouth, Hair, Eye2_ad, Eyelash, Glass, Gem) and the PNG paths of its textures;
  4. Blender 3.6 (build_blend.py) imports the PSK, builds the materials, renders a full-body and a face
     preview, packs the images into the .blend and saves
         <export-root>/<group>/blend/<id>/<id>.blend   (+ <id>_preview.png, <id>_face.png)
     so every model folder opens on its own (the E:\\game_export convention).
  5. --xps: export_xps_blender.py (Blender2XPS, x0.01) -> <group>/xps/<id>/<id>.xps;
     --pmx: export_pmx_blender.py (the FF7 / Stellar Blade MMD chain) -> <group>/pmx/<id>/<id>.pmx, then
     scripts/stellarblade/preview_pmx_blender.py renders preview / gaze / dance next to it.
     An existing .blend is reused (only converted) unless --force.

A summary of every run is kept in <export-root>/_meta/exports.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import ccff7r_common as cc

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_SCRIPT = os.path.join(HERE, "build_blend.py")
XPS_SCRIPT = os.path.join(HERE, "export_xps_blender.py")
PMX_SCRIPT = os.path.join(HERE, "export_pmx_blender.py")
PMX_PREVIEW = os.path.join(os.path.dirname(HERE), "stellarblade", "preview_pmx_blender.py")
BASE_MATERIALS = "/Game/Fair/00_Common/Materials/M/"   # root Materials: named in the chain, never dumped

# family -> the texture parameters build_blend.py reads (anything else is carried along, unused)
FAMILY_TEXTURES = {
    "standard": ("Tex_Color", "Tex_MultiMask", "Tex_BakedNormal", "Tex_2ndMultiMask"),
    "skin": ("AlbedMap", "MultiMaskMap", "BakedNormalMap", "PoreMask", "PoreSpec", "PoreNormal"),
    "hair": ("Tex_BaseColor", "Tex_Multi", "Tex_BakedNormal"),
    "eye": ("Tex_Colormap",),
    "eyelash": ("Tex_Color", "Tex_MultiMask"),
    "glass": ("Tex_Color", "Tex_MultiMask", "Tex_BakedNormal"),
    "gem": ("MM", "Normal"),
}


def log(msg: str) -> None:
    print("[ccff7r] " + msg, flush=True)


# ---------------------------------------------------------------- material instances
def mi_record(export: dict) -> dict:
    """The parameters one MaterialInstanceConstant sets itself."""
    pr = export.get("Properties") or {}
    rec = {"name": export.get("Name"), "textures": {}, "scalars": {}, "vectors": {}, "switches": {},
           "overrides": {}, "parent": (pr.get("Parent") or {}).get("ObjectPath")}
    for t in pr.get("TextureParameterValues") or []:
        rec["textures"][t["ParameterInfo"]["Name"]] = (t.get("ParameterValue") or {}).get("ObjectPath")
    for s in pr.get("ScalarParameterValues") or []:
        rec["scalars"][s["ParameterInfo"]["Name"]] = s.get("ParameterValue")
    for v in pr.get("VectorParameterValues") or []:
        val = v.get("ParameterValue") or {}
        rec["vectors"][v["ParameterInfo"]["Name"]] = [val.get(k, 0.0) for k in ("R", "G", "B", "A")]
    for s in ((pr.get("StaticParameters") or {}).get("StaticSwitchParameters") or []):
        rec["switches"][s["ParameterInfo"]["Name"]] = bool(s.get("Value"))
    bo = pr.get("BasePropertyOverrides") or {}
    for key in ("BlendMode", "ShadingModel", "TwoSided", "OpacityMaskClipValue", "UseMaskDisable"):
        if key in bo:
            rec["overrides"][key] = bo[key]
    if pr.get("bUseMaskDisable"):
        rec["overrides"]["UseMaskDisable"] = True
    return rec


def family_of(chain: list[str]) -> str:
    """Family from the SHARED materials in the chain (MI_ch_* / M_ch_*, lower-case "ch"); per-character
    instances are MI_CH_<name>_* and their names say nothing reliable (an "_eye" patch can be cloth)."""
    shared = [n for n in chain if n.startswith(("MI_ch_", "M_ch_", "MI_ob_", "M_ob_"))] or chain
    s = " ".join(n.lower() for n in shared)
    if "human_skin" in s or "human_mouth" in s:
        return "skin"
    if "eyelash" in s:
        return "eyelash"
    if "eye" in s:
        return "eye"
    if "hair" in s:
        return "hair"
    if "glass" in s:
        return "glass"
    if "gem" in s:
        return "gem"
    return "standard"


def merge_chain(records: list[dict]) -> dict:
    """records child-first -> one parameter set, the child's value winning."""
    merged = {"textures": {}, "scalars": {}, "vectors": {}, "switches": {}, "overrides": {}}
    for rec in reversed(records):
        for key in merged:
            merged[key].update({k: v for k, v in rec.get(key, {}).items() if v is not None})
    return merged


class MaterialResolver:
    def __init__(self, packages: set[str], props_root: str):
        self.packages = packages
        self.props = props_root
        self.cache: dict[str, dict | None] = {}

    def _path(self, object_path: str) -> str | None:
        pkg = cc.object_to_package(object_path)
        return cc.package_file(self.props, pkg, ".json") if pkg else None

    def prefetch(self, object_paths) -> None:
        """Dump every instance of the chains (one CLI run per chain depth)."""
        todo = set(p for p in object_paths if p)
        seen = set()
        while todo:
            need = []
            for obj in todo:
                pkg = cc.object_to_package(obj)
                if (pkg and pkg in self.packages and not obj.startswith(BASE_MATERIALS)
                        and not os.path.isfile(cc.package_file(self.props, pkg, ".json"))):
                    need.append(pkg)
            if need:
                cc.export_packages(need, self.props, fmt="json")
            seen |= todo
            nxt = set()
            for obj in todo:
                rec = self.record(obj)
                if rec and rec.get("parent") and rec["parent"] not in seen:
                    nxt.add(rec["parent"])
            todo = nxt

    def record(self, object_path: str) -> dict | None:
        if object_path in self.cache:
            return self.cache[object_path]
        rec = None
        path = self._path(object_path)
        if path and os.path.isfile(path):
            try:
                data = cc.load_json(path)
            except (OSError, ValueError):
                data = []
            want = cc.asset_name(object_path)
            for e in data if isinstance(data, list) else []:
                if e.get("Type") in ("MaterialInstanceConstant", "Material") and e.get("Name") == want:
                    rec = mi_record(e)
                    break
        self.cache[object_path] = rec
        return rec

    def resolve(self, object_path: str) -> dict:
        chain_names, records = [], []
        obj = object_path
        guard = 0
        while obj and guard < 16:
            guard += 1
            chain_names.append(cc.asset_name(obj))
            rec = self.record(obj)
            if rec is None:
                break
            records.append(rec)
            obj = rec.get("parent")
        merged = merge_chain(records)
        merged["chain"] = chain_names
        merged["family"] = family_of(chain_names)
        return merged


# ---------------------------------------------------------------- one model
def export_one(model: dict, a, packages: set[str], resolver: MaterialResolver) -> dict:
    t0 = time.time()
    raw = os.path.join(cc.work_dir(a.export_root), "raw")
    props = os.path.join(cc.work_dir(a.export_root), "props")
    mesh_pkg = model["sw_package"] if a.sw and model.get("sw_package") else model["package"]
    mesh_name = cc.asset_name(mesh_pkg)
    out_dir = cc.model_dir(model, a.export_root)
    model_id = model["id"] + ("_sw" if a.sw and model.get("sw_package") else "")
    if a.sw:
        out_dir = out_dir.rstrip("\\/") + "_sw"
    if a.preview_only:
        out_dir = os.path.join(cc.work_dir(a.export_root), "previews")
    blend = os.path.join(out_dir, model_id + ".blend")
    if os.path.isfile(blend) and not a.force and not a.preview_only:
        if a.xps or a.pmx:
            log("%s: reusing %s" % (model_id, blend))
            return convert(model, model_id, blend, a, {"id": model_id, "blend": blend, "reused_blend": True})
        log("%s: already exported (%s) - --force to redo" % (model_id, blend))
        return {"id": model_id, "skipped": True, "blend": blend}

    # 1. mesh + textures
    psk = cc.package_file(raw, mesh_pkg, ".psk")
    if a.force or not (os.path.isfile(psk) or os.path.isfile(psk + "x")):
        log("%s: exporting %s ..." % (model_id, mesh_pkg))
        cc.export_packages([mesh_pkg], raw)
    if not os.path.isfile(psk) and os.path.isfile(psk + "x"):
        psk += "x"
    if not os.path.isfile(psk):
        raise RuntimeError("no PSK written for %s" % mesh_pkg)

    # 2. mesh JSON -> slots
    mesh_json = cc.package_file(props, mesh_pkg, ".json")
    if a.force or not os.path.isfile(mesh_json):
        cc.export_packages([mesh_pkg], props, fmt="json")
    mesh = next(e for e in cc.load_json(mesh_json) if e.get("Type") == "SkeletalMesh")
    slots = []
    for i, sm in enumerate(mesh.get("SkeletalMaterials") or []):
        mat = (sm.get("Material") or {}).get("ObjectPath")
        slots.append({"slot": i, "slot_name": sm.get("MaterialSlotName"), "object": mat,
                      "material": cc.asset_name(mat) if mat else None})
    resolver.prefetch(s["object"] for s in slots)

    # 3. merged parameters + texture PNGs
    materials, missing_png = {}, set()
    for s in slots:
        if not s["object"] or s["material"] in materials:
            continue
        info = resolver.resolve(s["object"])
        tex_png = {}
        for param, obj in info["textures"].items():
            pkg = cc.object_to_package(obj)
            if not pkg:
                continue
            png = cc.package_file(raw, pkg, ".png")
            tex_png[param] = png
            if not os.path.isfile(png) and pkg in packages:
                missing_png.add(pkg)
        info["texture_files"] = tex_png
        materials[s["material"]] = info
    if missing_png:
        log("%s: exporting %d more textures" % (model_id, len(missing_png)))
        cc.export_packages(sorted(missing_png), raw)
    for info in materials.values():
        info["texture_files"] = {k: v for k, v in info["texture_files"].items() if os.path.isfile(v)}

    spec = {
        "id": model_id, "mesh": mesh_name, "package": mesh_pkg, "psk": psk, "out_dir": out_dir,
        "name_en": model["name_en"], "name_zh": model["name_zh"], "group": model["group"],
        "category": model["category"], "slots": slots, "materials": materials,
        "family_textures": FAMILY_TEXTURES, "preview": a.preview_only or not a.no_preview, "views": a.views,
        "views_dir": os.path.join(cc.work_dir(a.export_root), "views", model_id),
        "save": not a.preview_only,
    }
    spec_dir = os.path.join(cc.work_dir(a.export_root), "specs")
    os.makedirs(spec_dir, exist_ok=True)
    spec_path = os.path.join(spec_dir, model_id + ".json")
    with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)

    # 4. Blender
    os.makedirs(out_dir, exist_ok=True)
    log("%s: building %s" % (model_id, blend))
    cmd = [cc.BLENDER, "--background", "--factory-startup", "--python", BUILD_SCRIPT, "--", "--spec", spec_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    report = None
    for line in (r.stdout or "").splitlines():
        if line.startswith("CCFF7R_REPORT="):
            report = json.loads(line[len("CCFF7R_REPORT="):])
    log_path = os.path.join(spec_dir, model_id + ".blender.log")
    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""))
    if r.returncode != 0 or report is None or (not a.preview_only and not os.path.isfile(blend)):
        raise RuntimeError("Blender failed for %s (exit %d), log: %s" % (model_id, r.returncode, log_path))
    report["seconds"] = round(time.time() - t0, 1)
    report["spec"] = spec_path
    if a.preview_only:
        report["preview_only"] = True
        return report
    return convert(model, model_id, blend, a, report)


def run_blender(args: list[str], marker: str, log_path: str, timeout: int = 3600) -> dict | None:
    """Run Blender, keep its log, return the JSON after `marker` on the last matching line."""
    r = subprocess.run([cc.BLENDER] + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""))
    line = next((l for l in reversed((r.stdout or "").splitlines()) if l.startswith(marker)), "")
    return json.loads(line[len(marker):]) if line else None


def convert(model: dict, model_id: str, blend: str, a, report: dict) -> dict:
    """--xps / --pmx from the finished .blend into <group>/xps|pmx/<id>/."""
    spec_dir = os.path.join(cc.work_dir(a.export_root), "specs")
    os.makedirs(spec_dir, exist_ok=True)
    group_dir = os.path.join(a.export_root, model["group"])
    title = "%s (%s)" % (model["name_en"], model_id) if model["name_en"] != model_id else model_id
    if a.xps:
        xps = os.path.join(group_dir, "xps", model_id, model_id + ".xps")
        if os.path.isfile(xps) and not a.force:
            report["xps"] = xps
        else:
            log("%s: XPS ..." % model_id)
            rep = run_blender(["-b", blend, "--python", XPS_SCRIPT, "--", "--out", os.path.join(group_dir, "xps")],
                              "CCFF7R_XPS=", os.path.join(spec_dir, model_id + ".xps.log"))
            if not rep or not rep.get("ok"):
                report.setdefault("warnings", []).append("XPS failed: %s" % ((rep or {}).get("errors") or "see log"))
                report.setdefault("convert_failed", []).append("xps")
            else:
                report["xps"] = rep["path"]
                report["xps_stats"] = rep.get("stats")
    if a.pmx:
        pmx = os.path.join(group_dir, "pmx", model_id, model_id + ".pmx")
        if os.path.isfile(pmx) and not a.force:
            report["pmx"] = pmx
        else:
            log("%s: PMX ..." % model_id)
            comment = ("%s - CRISIS CORE -FINAL FANTASY VII- REUNION (%s)\\nConverted by ripper_tpose "
                       "(scripts/ccff7r/export_pmx_blender.py). Personal use only." % (title, model["mesh"]))
            rep = run_blender(["-b", blend, "--python", PMX_SCRIPT, "--", "--out", os.path.join(group_dir, "pmx"),
                               "--model-name", title[:60], "--comment", comment],
                              "CCFF7R_PMX=", os.path.join(spec_dir, model_id + ".pmx.log"))
            if not rep or not os.path.isfile(pmx):
                report.setdefault("warnings", []).append("PMX failed, log: %s" % os.path.join(spec_dir, model_id + ".pmx.log"))
                report.setdefault("convert_failed", []).append("pmx")
            else:
                report["pmx"] = pmx
                report["pmx_report"] = {k: rep.get(k) for k in (
                    "height_m", "bones", "rigid_bodies", "joints", "distortion", "weight_holes",
                    "grant_order_violations", "bust_physics", "added_neck", "missing_optional_slots")}
                prev = run_blender(["-b", "--python", PMX_PREVIEW, "--", "--pmx", pmx], "PMX_PREVIEW=",
                                   os.path.join(spec_dir, model_id + ".pmx_preview.log"))
                if prev:
                    report["pmx_preview"] = {k: prev.get(k) for k in ("rest_drop_test", "max_rigid_body_distance_from_hips_m")}
    return report


def record_runs(root: str, reports: list[dict]) -> None:
    """Merge this run into _meta/exports.json under a lock file (several batches may run in parallel)."""
    path = os.path.join(cc.meta_dir(root), "exports.json")
    os.makedirs(cc.meta_dir(root), exist_ok=True)
    lock = path + ".lock"
    fd = None
    for _ in range(300):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            time.sleep(0.2)
    try:
        _record_runs(path, reports)
    finally:
        if fd is not None:
            os.close(fd)
            os.remove(lock)


def _record_runs(path: str, reports: list[dict]) -> None:
    data = {}
    if os.path.isfile(path):
        try:
            data = cc.load_json(path)
        except (OSError, ValueError):
            data = {}
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for rep in reports:
        if rep.get("skipped") or rep.get("preview_only"):
            continue
        old = data.get(rep["id"], {}) if rep.get("reused_blend") else {}
        new = {k: rep.get(k) for k in ("blend", "preview", "face", "vertices", "faces", "bones", "materials_built",
                                       "warnings", "seconds", "xps", "xps_stats", "pmx", "pmx_report", "pmx_preview")
               if rep.get(k) is not None}
        data[rep["id"]] = {**old, "time": stamp, **new}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="ids / names / groups from list_models.py, wildcards ok")
    ap.add_argument("--category", choices=cc.CATEGORY_ORDER, action="append")
    ap.add_argument("--all", action="store_true", help="every model (266)")
    ap.add_argument("--sw", action="store_true", help="the _SW twin instead (same mesh, *_Lite materials)")
    ap.add_argument("--force", action="store_true", help="re-export even if the .blend exists")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--views", action="store_true", help="also render front/side/back/3-4 + close-ups to _work/views")
    ap.add_argument("--preview-only", action="store_true",
                    help="only render <id>_preview.png / _face.png into _work/previews, no .blend (for surveys)")
    ap.add_argument("--xps", action="store_true", help="also write <group>/xps/<id>/<id>.xps (Blender2XPS)")
    ap.add_argument("--pmx", action="store_true", help="also write <group>/pmx/<id>/<id>.pmx (+ MMD previews)")
    ap.add_argument("--export-root", default=cc.EXPORT_ROOT)
    a = ap.parse_args()
    if not (a.models or a.category or a.all):
        ap.error("name at least one model (python list_models.py shows them), --category or --all")

    cc.check_tools(need_blender=True)
    packages = cc.list_packages(a.export_root)
    models = cc.discover_models(packages, root=a.export_root)
    chosen = models if a.all else []
    if a.category:
        chosen += [m for m in models if m["category"] in a.category and m not in chosen]
    if a.models:
        chosen += [m for m in cc.find_models(models, a.models) if m not in chosen]
    resolver = MaterialResolver(set(packages), os.path.join(cc.work_dir(a.export_root), "props"))

    reports, failed = [], []
    for i, model in enumerate(chosen, 1):
        log("(%d/%d) %s  %s %s" % (i, len(chosen), model["id"], model["name_en"], model["name_zh"]))
        try:
            rep = export_one(model, a, set(packages), resolver)
        except Exception as exc:  # noqa: BLE001 - keep going through a batch
            log("FAILED %s: %s" % (model["id"], exc))
            failed.append((model["id"], str(exc)))
            continue
        reports.append(rep)
        if not rep.get("skipped"):
            if not rep.get("reused_blend"):
                log("%s: %s  (%d verts, %d bones, %d materials, %.0f s)" % (
                    rep["id"], rep.get("blend") or rep.get("preview"), rep.get("vertices", 0), rep.get("bones", 0),
                    len(rep.get("materials_built", {})), rep["seconds"]))
            for key in ("xps", "pmx"):
                if rep.get(key):
                    log("  %s %s" % (key.upper(), rep[key]))
            pr = rep.get("pmx_report") or {}
            if pr:
                d = pr.get("distortion") or {}
                log("  PMX: %s bones, %s rigid bodies, torn %s, stretched %s, grant violations %d, bust %s" % (
                    pr.get("bones"), pr.get("rigid_bodies"), d.get("torn"), d.get("stretched"),
                    len(pr.get("grant_order_violations") or []), len(pr.get("bust_physics") or [])))
            for w in rep.get("warnings", []):
                log("  ! " + w)
            if rep.get("convert_failed"):
                failed.append((rep["id"], "%s conversion failed (see the warnings above)" % "/".join(rep["convert_failed"])))
    record_runs(a.export_root, reports)
    done = [r for r in reports if not r.get("skipped")]
    log("done: %d built, %d skipped, %d failed" % (len(done), len(reports) - len(done), len(failed)))
    for mid, err in failed:
        log("  failed %s: %s" % (mid, err.splitlines()[0] if err else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
