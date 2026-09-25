# -*- coding: utf-8 -*-
"""FF7 Remake / Rebirth mods -> Blender, one .blend per mod file, plus gallery entries.

Reads what nexus_mod_batch.py collected (D:/ff7_mods/collected.json: every downloaded archive
unpacked under .../x/), finds the containers inside and exports every skeletal mesh the mod
ships, textured with the mod's own textures on top of the game's.

Remake (UE4.18 .pak, Remake UE Viewer build):
  * the mod is mounted ALONE (hard link in <work>/mount): with the whole Paks folder the
    base game can win over the mod (docs/ff7remake-mod-manual-export.md);
  * "umodel -list *" names every package with its classes -> SkeletalMesh / Texture2D / MI;
  * textures + materials: "-export -png -nomesh" over the whole mod;
  * mesh: "-export" to ActorX; when this UE Viewer build rejects a mod mesh (LOD assertion)
    the raw package is saved (-save) and FF7R-mesh-importer turns it into glTF;
  * validate_ff7remake_model.py --overlay-root: the mod textures/.mat win over the base
    export in D:/ff7remake_exports/player (materials the mod does not ship come from there).
Rebirth (UE4.26 IoStore): ff7rb_cli_export.py --mod (hard-link staging, mod in ~mods) and the
FF7RB Blender worker, like the official exports.

  python ff7_mod_export.py remake            # every collected Remake archive
  python ff7_mod_export.py rebirth
  python ff7_mod_export.py remake --only 3326 --force
  python ff7_mod_export.py register --game remake --blend X.blend --report X.json ...
Outputs: D:/ff7remake_exports/mods/<modId>_<slug>/<fileId>_<slug>/ and
D:/ff7rebirth_exports/mods/...; gallery entries in <root>/gallery_mods.json.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UMODEL = "E:/tools/umodel_ff7remake/umodel_FFVII_intergrade_v8.exe"
BLENDER = "D:/Program Files/blender-3.6.15-windows-x64/blender.exe"
MESH_IMPORTER = "E:/tools/FF7R-mesh-importer/src/main.py"
COLLECTED = "D:/ff7_mods/collected.json"
SELECTION = "D:/ff7_mods/selection.json"
ROOTS = {"remake": "D:/ff7remake_exports/mods", "rebirth": "D:/ff7rebirth_exports/mods"}
DOMAINS = {"remake": "finalfantasy7remake", "rebirth": "finalfantasy7rebirth"}
REMAKE_BASE = "D:/ff7remake_exports/player/GameContents"
HELPER_SUFFIX = re.compile("(_(Skeleton|PhysicsAsset|BNM|KDI|vfx|Rig|Phy)|condition)$", re.IGNORECASE)   # Reika ships "Reika_FinalcompletCOndition"


def run(cmd, timeout=3600, env=None, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env, cwd=cwd)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def slug(text, limit=48):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:limit].rstrip("_") or "x"


def link_or_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def load_json(path, default):
    if os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def register(game, entry):
    """Insert/replace one card in <root>/gallery_mods.json (keyed by label)."""
    path = os.path.join(ROOTS[game], "gallery_mods.json")
    data = load_json(path, {"results": []})
    data["results"] = [e for e in data["results"] if e.get("label") != entry["label"]] + [entry]
    data["results"].sort(key=lambda e: e["label"])
    save_json(path, data)
    return path


def mod_meta(sel, mod_id, file_id):
    for m in sel.get("selected", []):
        if m["modId"] == mod_id:
            f = next((x for x in m["files"] if int(x["fileId"]) == int(file_id)), {})
            return {"name": m["name"], "modId": mod_id, "fileId": int(file_id), "file": f.get("name", ""),
                    "author": (m.get("uploader") or {}).get("name", ""), "adult": bool(m.get("adultContent")),
                    "url": "https://www.nexusmods.com/%s/mods/%d" % (m["game"]["domainName"], mod_id)}
    return {"name": "mod %d" % mod_id, "modId": mod_id, "fileId": int(file_id)}


# ------------------------------------------------------------------ Remake
def umodel_list(mount):
    """{package: [classes]} from "umodel -list *" (a /path line, then one line per export)."""
    _rc, out = run([UMODEL, "-list", "-game=ue4.18", "-path=" + mount, "*"], timeout=900)
    pkgs, cur = {}, None
    for line in out.splitlines():
        t = line.strip()
        if t.startswith("/") and t.lower().endswith(".uasset"):
            cur = t.lstrip("/")
            pkgs[cur] = []
        elif cur and t:
            parts = t.split()
            if len(parts) >= 5 and parts[0].isdigit():
                pkgs[cur].append(parts[3])
    return pkgs


def material_params(mount, pkgs):
    """{material instance: {parameter: texture}} from "umodel -dump" of every MI the mod ships.
    The .mat files UE Viewer writes list textures without parameter names, so a mask bound
    to DetailOpacity (967: MarineCharm_A, the emissive-detail mask of an OPAQUE shader)
    looked like a coverage mask and cut the whole suit full of holes."""
    out = {}
    for pkg, classes in sorted(pkgs.items()):
        if "MaterialInstanceConstant" not in classes:
            continue
        _rc, dump = run([UMODEL, "-dump", "-game=ue4.18", "-path=" + mount, pkg], timeout=300)
        name, param, table = os.path.splitext(os.path.basename(pkg))[0], None, {}
        for line in dump.splitlines():
            t = line.strip()
            if t.startswith("ParameterInfo = { Name="):
                param = t[len("ParameterInfo = { Name="):].rstrip("} ").strip()
            elif t.startswith("ParameterValue = Texture") and param:
                ref = t.split(chr(39))[1] if chr(39) in t else ""
                table[param] = ref.rsplit(".", 1)[-1] if ref else ""
                param = None
        out[name] = table
    return out


def remake_targets(pkgs):
    """Skeletal meshes the mod ships; for texture-only mods, the base meshes of the folders it retextures."""
    meshes = [p for p, cls in pkgs.items()
              if "SkeletalMesh" in cls and not HELPER_SUFFIX.search(os.path.splitext(os.path.basename(p))[0])]
    if meshes:
        return [(p, None) for p in sorted(meshes)]
    out = []
    for folder in sorted({p.split("/")[-3] for p, cls in pkgs.items() if "Texture2D" in cls and "/Texture/" in p}):
        base = glob.glob(os.path.join(REMAKE_BASE, "Character", "*", folder, "Model", "*.psk*"))
        if base:
            code = os.path.splitext(os.path.basename(base[0]))[0]
            out.append(("End/Content/GameContents/Character/Player/%s/Model/%s.uasset" % (folder, code), base[0]))
    return out


def remake_mesh(work, mount, assets, pkg, base_model, meta, force):
    parts = pkg.split("/")
    folder, code = parts[-3], os.path.splitext(parts[-1])[0]
    label = "mod%d_%s_%s" % (meta["modId"], code, slug(meta.get("file") or str(meta["fileId"]), 40))
    out_blend = os.path.join(work, label + ".blend")
    if os.path.isfile(out_blend) and not force:
        return {"label": label, "status": "SKIP", "blend": out_blend}
    model, route, note = base_model, "base mesh + mod textures", ""
    if not model:
        mesh_out = os.path.join(work, "mesh")
        rc, log = run([UMODEL, "-export", "-png", "-game=ue4.18", "-path=" + mount, "-out=" + mesh_out, pkg])
        found = glob.glob(os.path.join(mesh_out, "**", code + ".psk*"), recursive=True)
        if rc == 0 and found:
            model, route = found[0], "UE Viewer ActorX"
        else:
            note = next((l.strip() for l in log.splitlines() if "assert" in l.lower() or "error" in l.lower()), "")
            raw = os.path.join(work, "raw")
            run([UMODEL, "-save", "-game=ue4.18", "-path=" + mount, "-out=" + raw, pkg])
            uexp = glob.glob(os.path.join(raw, "**", code + ".uexp"), recursive=True)
            if not uexp:
                return {"label": label, "status": "FAIL", "error": "UE Viewer could not save " + pkg, "note": note}
            gl_root = os.path.join(work, "gltf")
            # the importer writes log/<time>.txt into the current directory: keep it in the work dir
            rc3, log3 = run([sys.executable, MESH_IMPORTER, uexp[0], gl_root, "--mode=export"], cwd=work)
            gltf = glob.glob(os.path.join(gl_root, "**", code + ".gltf"), recursive=True)
            if not gltf or not os.path.isfile(os.path.splitext(gltf[0])[0] + ".bin"):
                return {"label": label, "status": "FAIL", "error": "glTF conversion failed", "log": log3[-800:]}
            model, route = gltf[0], "FF7R-mesh-importer glTF"
    base_dirs = glob.glob(os.path.join(REMAKE_BASE, "Character", "*", folder))
    material_dir = os.path.join(base_dirs[0], "Material") if base_dirs else ""
    if not material_dir or not os.path.isdir(material_dir):
        mats = glob.glob(os.path.join(assets, "**", "Material"), recursive=True)
        material_dir = mats[0] if mats else assets
    report = os.path.join(work, label + ".json")
    preview = os.path.join(work, label + "_preview.png")
    rc, log = run([BLENDER, "--background", "--python", os.path.join(HERE, "enable_psk_addon.py"),
                   "--python", os.path.join(HERE, "validate_ff7remake_model.py"), "--",
                   "--model", model, "--asset-root", REMAKE_BASE, "--overlay-root", assets,
                   "--material-dir", material_dir, "--output", out_blend, "--report", report,
                   "--render", preview, "--material-params", os.path.join(assets, "material_params.json")])
    with open(os.path.join(work, label + ".log"), "w", encoding="utf-8") as fh:
        fh.write(log)
    if not os.path.isfile(out_blend):
        return {"label": label, "status": "FAIL", "error": "Blender wrote no .blend", "log": log[-1200:]}
    rep = load_json(report, {})
    mats = rep.get("materials") or []
    missing = rep.get("missing_preview_textures") or []
    entry = {"label": label, "code": code, "char": (folder.split("_") + ["", "", ""])[2],
             "variant": meta.get("file") or "", "blend": out_blend, "preview": preview,
             "meshes": rep.get("meshes", 0), "vertices": rep.get("vertices", 0), "polygons": rep.get("polygons", 0),
             "bones": rep.get("bones", 0), "materials": len(mats),
             "alphaMaterials": sum(1 for m in mats if m.get("alpha")),
             "warnings": (["缺贴图 %d：%s" % (len(missing), "; ".join("%s/%s" % (m.get("material"), m.get("kind"))
                                                                   for m in missing[:4]))] if missing else [])
                         + (["UE Viewer 读不了这个 mod 网格（%s），走 glTF" % note] if note else []),
             "route": route, "mod": meta, "package": pkg}
    register("remake", entry)
    return dict(entry, status="PASS")


def remake_file(key, st, sel, force, extra=()):
    """extra: [(fileId, collected entry)] mounted together with this file (an add-on such as
    1707's Hair and Makeup on top of the suit it was made for)."""
    x = os.path.join(st["dir"], "x")
    paks = glob.glob(os.path.join(x, "**", "*.pak"), recursive=True)
    meta = mod_meta(sel, st["modId"], key)
    for k2, st2 in extra:
        paks += glob.glob(os.path.join(st2["dir"], "x", "**", "*.pak"), recursive=True)
        meta = dict(meta, file="%s + %s" % (meta.get("file") or key, mod_meta(sel, st2["modId"], k2).get("file") or k2),
                    fileId="%s+%s" % (meta["fileId"], k2))
    if not paks:
        return [{"label": "file %s" % key, "status": "NO_PAK"}]
    work = os.path.join(ROOTS["remake"], "%d_%s" % (st["modId"], slug(meta["name"])),
                        "%s_%s" % ("+".join([key] + [k for k, _ in extra]), slug(meta.get("file") or key)))
    mount = os.path.join(work, "mount")
    for p in paks:                                # the mod alone: the base game cannot win
        link_or_copy(p, os.path.join(mount, os.path.basename(p)))
    pkgs = umodel_list(mount)
    save_json(os.path.join(work, "packages.json"), pkgs)
    assets = os.path.join(work, "mod_assets")
    if force or not os.path.isdir(assets):
        run([UMODEL, "-export", "-png", "-nomesh", "-noanim", "-game=ue4.18", "-path=" + mount,
             "-out=" + assets, "*"])
    params = material_params(mount, pkgs)
    save_json(os.path.join(assets, "material_params.json"), params)
    targets = remake_targets(pkgs)
    if not targets:
        return [{"label": "file %s" % key, "status": "NO_MODEL", "packages": len(pkgs)}]
    return [remake_mesh(work, mount, assets, pkg, base, meta, force) for pkg, base in targets]


# ------------------------------------------------------------------ Rebirth
def rebirth_file(key, st, sel, force):
    x = os.path.join(st["dir"], "x")
    meta = mod_meta(sel, st["modId"], key)
    if not glob.glob(os.path.join(x, "**", "*.utoc"), recursive=True):
        return [{"label": "file %s" % key, "status": "NO_CONTAINER"}]
    work = os.path.join(ROOTS["rebirth"], "%d_%s" % (st["modId"], slug(meta["name"])),
                        "%s_%s" % (key, slug(meta.get("file") or key)))
    cli = [sys.executable, os.path.join(HERE, "ff7rb_cli_export.py")]
    _rc, listing = run(cli + ["--out", work, "--mod", x, "--list"], timeout=1800)
    pkgs = sorted({l.strip() for l in listing.splitlines() if l.strip().lower().endswith(".uasset")})
    save_json(os.path.join(work, "packages.json"), pkgs)
    if not pkgs:
        return [{"label": "file %s" % key, "status": "NO_PACKAGES"}]
    # export every package of the mod against the staged game: a DRESSCODE plugin keeps its
    # meshes outside Model/ (End/Mods/<Plugin>/Content/MetaData/fullsuit), so let the export
    # tell which packages are skeletal meshes
    export = os.path.join(work, "export")
    args = cli + ["--out", export, "--mod", x]
    for p in pkgs:
        args += ["--package", p]
    rc, log = run(args, timeout=3600)
    with open(os.path.join(work, "cli_export.log"), "w", encoding="utf-8") as fh:
        fh.write(log)
    found_models = sorted(glob.glob(os.path.join(export, "**", "*.psk"), recursive=True)
                          + glob.glob(os.path.join(export, "**", "*.pskx"), recursive=True))
    meshes = []
    for path in found_models:
        rel = os.path.splitext(os.path.relpath(path, export).replace(os.sep, "/"))[0]
        if "_raw_materials" in rel:
            continue
        pkg = rel + ".uasset" if rel.startswith("End/") else             "End/Mods/%s/Content/%s.uasset" % (rel.split("/")[0], rel.split("/", 1)[1])   # plugin: object path
        code = os.path.basename(rel)
        if pkg in pkgs and not HELPER_SUFFIX.search(code):   # the mod own meshes, no _Condition helpers
            meshes.append((pkg, path))
    if not meshes:
        return [{"label": "file %s" % key, "status": "NO_MODEL", "packages": len(pkgs), "log": log[-800:]}]
    results = []
    for pkg, model_path in meshes:
        code = os.path.splitext(os.path.basename(pkg))[0]
        rel = os.path.dirname(pkg)
        label = "mod%d_%s_%s" % (meta["modId"], code, slug(meta.get("file") or key, 40))
        found = [model_path]
        if "/Character/" in pkg and rel.endswith("/Model"):
            variant_root = os.path.dirname(os.path.dirname(model_path))   # .../Character/Player/<variant>
        else:
            # plugin mod: meshes/materials land at <export>/<Plugin>/<folder>/ (object path), so the
            # variant root is <export>/<Plugin> and the worker's <variant_root>/../.. index spans the
            # whole work dir, i.e. also the base-game textures the plugin references
            variant_root = os.path.join(export, pkg.split("/")[2]) if pkg.startswith("End/Mods/") else os.path.join(export, "End")
        out_blend = os.path.join(work, label + ".blend")
        if os.path.isfile(out_blend) and not force:
            results.append({"label": label, "status": "SKIP", "blend": out_blend})
            continue
        env = dict(os.environ)
        if pkg.startswith("End/Mods/"):           # plugin mesh: base-game materials exported next to it
            env["FF7RB_EXTRA_ROOTS"] = os.path.join(export, "End", "Content", "Character")
        rc, blog = run([BLENDER, "--background", "--python", os.path.join(HERE, "export_ff7rb_model_blender.py"),
                        "--", found[0], variant_root, out_blend, os.path.join(HERE, "ff7rebirth_tools.py"),
                        "export", "blend"], env=env)
        with open(os.path.join(work, label + ".log"), "w", encoding="utf-8") as fh:
            fh.write(blog)
        line = next((l for l in reversed(blog.splitlines()) if l.startswith("FF7RB_EXPORT=")), "")
        payload = json.loads(line[len("FF7RB_EXPORT="):]) if line else {}
        if payload.get("status") != "PASS" or not os.path.isfile(out_blend):
            results.append({"label": label, "status": "FAIL", "error": payload.get("error") or "no result marker"})
            continue
        run([BLENDER, "--background", "--python", os.path.join(HERE, "html", "render_blend_preview.py"),
             "--", out_blend, "--force"])
        folder = rel.split("/")[-2] if rel.endswith("/Model") else (pkg.split("/")[2] if pkg.startswith("End/Mods/") else code)
        char = (folder.split("_") + ["", "", ""])[2] if re.match("^PC[0-9]{4}_", folder) else next(
            (w for w in ("Tifa", "Aerith", "Yuffie", "Reika", "Cloud", "Barret") if w.lower() in meta["name"].lower()),
            folder)
        variant = meta.get("file") or ""
        if pkg.startswith("End/Mods/"):           # one plugin file ships several outfits: name the mesh
            variant = "%s · %s" % (code, variant)
        entry = {"label": label, "code": code, "char": char,
                 "variant": variant, "blend": out_blend,
                 "preview": os.path.splitext(out_blend)[0] + "_preview.png",
                 "meshes": payload.get("meshes", 0), "vertices": payload.get("vertices", 0),
                 "polygons": payload.get("polygons", 0), "bones": payload.get("bones", 0),
                 "materials": payload.get("materials", 0), "alphaMaterials": 0,
                 "warnings": (["缺底色贴图：%s" % "; ".join(map(str, payload["missing_base"][:4]))]
                              if payload.get("missing_base") else []),
                 "route": "CUE4Parse CLI", "mod": meta, "package": pkg}
        register("rebirth", entry)
        results.append(dict(entry, status="PASS"))
    return results


# ------------------------------------------------------------------ main
def cmd_register(a):
    """Add an already-built mod .blend (e.g. an older manual export) to the gallery."""
    rep = load_json(a.report, {}) if a.report else {}
    entry = {"label": a.label, "code": a.code, "char": a.char, "variant": a.variant,
             "blend": os.path.abspath(a.blend), "preview": os.path.abspath(a.preview) if a.preview else "",
             "meshes": rep.get("meshes", a.meshes), "vertices": rep.get("vertices", a.vertices),
             "polygons": rep.get("polygons", a.polygons), "bones": rep.get("bones", a.bones),
             "materials": a.materials, "alphaMaterials": 0, "warnings": [], "route": a.route,
             "mod": {"name": a.name, "file": a.file, "url": a.url, "author": a.author}}
    print("registered in", register(a.game, entry))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("remake", "rebirth", "register"))
    ap.add_argument("--only", nargs="*", default=[], help="file ids to (re)do")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--combine", action="append", default=[],
                    help="remake: A+B mounts file B (an add-on) together with file A, e.g. 5649+5651")
    ap.add_argument("--collected", default=COLLECTED)
    ap.add_argument("--selection", default=SELECTION)
    for opt in ("game", "blend", "preview", "report", "label", "code", "char", "variant",
                "name", "file", "url", "author", "route"):
        ap.add_argument("--" + opt, default="")
    for opt in ("meshes", "vertices", "polygons", "bones", "materials"):
        ap.add_argument("--" + opt, type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "register":
        return cmd_register(a)
    collected = load_json(a.collected, {})
    sel = load_json(a.selection, {})
    todo = [(k, st) for k, st in sorted(collected.items())
            if st.get("status") == "ok" and st.get("game") == DOMAINS[a.cmd] and (not a.only or k in a.only)]
    results = []
    if a.combine:                                  # only the requested combinations
        todo = []
        for spec in a.combine:
            first, *rest = spec.split("+")
            todo.append((first, collected[first], [(k, collected[k]) for k in rest]))
    else:
        todo = [(k, st, []) for k, st in todo]
    for key, st, extra in todo:
        t0 = time.time()
        rs = remake_file(key, st, sel, a.force, extra) if a.cmd == "remake" else rebirth_file(key, st, sel, a.force)
        for r in rs:
            print("%-5s %-60s %s %s" % (r.get("status"), r.get("label"), r.get("route", ""),
                                        r.get("error", "")), flush=True)
        print("   file %s: %.0f s" % (key, time.time() - t0), flush=True)
        results += rs
    ok = sum(1 for r in results if r.get("status") in ("PASS", "SKIP"))
    print("FF7_MOD_EXPORT=" + json.dumps({"game": a.cmd, "files": len(todo), "models": len(results), "ok": ok}))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
