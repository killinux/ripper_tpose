"""Marvel Heroes Omega mod / package -> Blender, without the game.

    python -I scripts\\marvelheroes\\export_upk.py <mod.zip | package.upk> --out <dir> [--name Gwenom]
           [--mesh <skeletal mesh>] [--scale 0.018] [--spec-scale 0.025] [--keep-dummy] [--no-preview]
    python -I scripts\\marvelheroes\\export_upk.py <mod.zip | package.upk> --list

Writes
    <out>\\blend\\<name>\\<name>.blend    model + armature + materials, textures\\ next to it (relative paths)
    <out>\\blend\\<name>\\preview.png     front / 3-4 / side / back + four head close-ups, preview\\ = single renders
    <out>\\psk\\<name>\\<name>.psk        the same mesh as an ActorX PSK (UE Viewer conventions), textures\\ PNG,
                                       materials.json (every material instance's parameters)
    <out>\\_meta\\                       report.json, the mod's manifest / string files and its icons as PNG

The .zip is read with zipfile into a fresh temporary folder (file names reduced to their base name) and deleted
afterwards; the package is only parsed as data.  See README.md for the format notes and the material mapping.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from upk import Package  # noqa: E402
import materials as mat_mod  # noqa: E402
import skelmesh  # noqa: E402
import textures as tex_mod  # noqa: E402
import write_psk  # noqa: E402

BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
TEXCONV = tex_mod.TEXCONV
KEEP_FROM_ZIP = (".upk", ".json", ".dds", ".txt")


def log(msg):
    print(msg, flush=True)


def unpack_zip(path, work):
    """Members with the extensions we use -> work/<base name>.  Returns the list of written files."""
    out = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            base = os.path.basename(info.filename.replace("\\", "/"))
            if not base or not base.lower().endswith(KEEP_FROM_ZIP) or base.startswith("."):
                continue
            dst = os.path.join(work, base)
            with z.open(info) as src, open(dst, "wb") as f:
                shutil.copyfileobj(src, f)
            out.append(dst)
    return out


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_") or "model"


def list_package(pkg):
    log("package %s: version %d/%d, %d exports" % (os.path.basename(pkg.path), pkg.ver, pkg.lic, pkg.export_count))
    for i in pkg.of_class("skeletalmesh"):
        log("  SkeletalMesh %-40s %8d bytes" % (pkg.obj_path(i + 1), pkg.exports[i]["size"]))
    for name, m in mat_mod.read_instances(pkg).items():
        log("  Material     %-40s %d textures" % (m["path"], len(m["textures"])))
    for i in pkg.of_class("texture2d"):
        t = tex_mod.read_texture(pkg, i)
        if not t["data"]:
            where = "(only in the game's %s.tfc cache)" % t["cache"]
        elif t["mip_width"] < t["width"]:
            where = "%dx%d inline, full %dx%d in the game's %s.tfc cache" % (
                t["mip_width"], t["mip_height"], t["width"], t["height"], t["cache"])
        else:
            where = "%dx%d inline" % (t["mip_width"], t["mip_height"])
        log("  Texture2D    %-40s %s %s" % (t["path"], t["format"], where))
    n_anim = len(pkg.of_class("animsequence"))
    if n_anim:
        log("  AnimSequence x %d (not converted)" % n_anim)


def contact_sheet(files, dst):
    try:
        from PIL import Image
    except ImportError:
        log("  (no Pillow: preview.png not made, single renders are in preview\\)")
        return None
    body = [Image.open(f).convert("RGB") for f in files[:4]]
    heads = [Image.open(f).convert("RGB") for f in files[4:8]]
    h1 = 900
    body = [im.resize((int(im.width * h1 / im.height), h1)) for im in body]
    w = sum(im.width for im in body)
    h2 = w // max(len(heads), 1)
    heads = [im.resize((h2, h2)) for im in heads]
    sheet = Image.new("RGB", (w, h1 + (h2 if heads else 0)), (40, 41, 45))
    x = 0
    for im in body:
        sheet.paste(im, (x, 0))
        x += im.width
    for i, im in enumerate(heads):
        sheet.paste(im, (i * h2, h1))
    sheet.save(dst)
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="mod .zip or a .upk package")
    ap.add_argument("--out", help="output folder, e.g. E:\\game_export\\MarvelHeroesOmega\\Gwenom")
    ap.add_argument("--name", help="model name (default: the mod's name, else the mesh name)")
    ap.add_argument("--mesh", help="skeletal mesh export name (default: the largest one)")
    ap.add_argument("--scale", type=float, default=0.018, help="game units -> metres (default 0.018: Gwenom 1.68 m)")
    ap.add_argument("--spec-scale", type=float, default=0.025, help="coloured specular = ... x specmult x this")
    ap.add_argument("--keep-dummy", action="store_true", help="keep one-triangle placeholder sections")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--list", action="store_true", help="only list meshes, materials and textures")
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--texconv", default=TEXCONV)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    work = tempfile.mkdtemp(prefix="mho_export_")
    try:
        manifest = {}
        if a.source.lower().endswith(".zip"):
            files = unpack_zip(a.source, work)
            upks = [f for f in files if f.lower().endswith(".upk")]
            for f in files:
                if os.path.basename(f).lower() == "manifest.json":
                    with open(f, encoding="utf-8-sig") as fh:
                        manifest = json.load(fh)
        else:
            files, upks = [], [a.source]
        if not upks:
            raise SystemExit("no .upk in " + a.source)
        pkgs = [Package(p) for p in upks]
        if a.list:
            for pkg in pkgs:
                list_package(pkg)
            return
        if not a.out:
            raise SystemExit("--out is required (or use --list)")
        # the package with the mesh asked for (or the biggest skeletal mesh of all packages)
        cands = [(pkg, i) for pkg in pkgs for i in pkg.of_class("skeletalmesh")
                 if not a.mesh or pkg.exports[i]["name"].lower() == a.mesh.lower()]
        if not cands:
            raise SystemExit("no skeletal mesh%s found" % (" called " + a.mesh if a.mesh else ""))
        pkg, idx = max(cands, key=lambda c: c[0].exports[c[1]]["size"])
        name = safe_name(a.name or manifest.get("Name", "").split(" - ")[0] or pkg.exports[idx]["name"])
        out = os.path.abspath(a.out)
        psk_dir = os.path.join(out, "psk", name)
        blend_dir = os.path.join(out, "blend", name)
        meta_dir = os.path.join(out, "_meta")
        for d in (psk_dir, blend_dir, meta_dir):
            os.makedirs(d, exist_ok=True)
        log("== %s: mesh %s -> %s" % (os.path.basename(pkg.path), pkg.obj_path(idx + 1), name))

        mesh = skelmesh.parse(pkg, idx, log=log)
        psk = write_psk.write_psk(mesh, os.path.join(psk_dir, name + ".psk"), keep_dummy=a.keep_dummy, log=log)
        mics = mat_mod.read_instances(pkg)
        # material slots the PSK kept (a dropped placeholder section's material is not exported)
        slot_names = {p.split(".")[-1] for p in mesh["materials"] if write_psk.material_name(p) in psk["materials"]}
        used = {k: v for k, v in mics.items() if k in slot_names}
        with open(os.path.join(psk_dir, "materials.json"), "w", encoding="utf-8") as f:
            json.dump(mics, f, indent=1, ensure_ascii=False, default=str)
        wanted = {v.split(".")[-1].lower() for m in used.values() for v in m["textures"].values()}
        log("textures (%d used by the mesh's materials):" % len(wanted))
        tex_dir = os.path.join(psk_dir, "textures")
        done = tex_mod.export_textures(pkg, tex_dir, a.texconv, only=wanted, log=log)
        for f in os.listdir(tex_dir):
            if f.lower().endswith(".dds"):
                os.remove(os.path.join(tex_dir, f))
        missing = sorted(wanted - {p.split(".")[-1].lower() for p in done})
        if missing:
            log("  textures not in the package (the game's .tfc caches hold them): " + ", ".join(missing))

        blend = os.path.join(blend_dir, name + ".blend")
        cmd = [a.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"), "--",
               "--psk", psk["psk"], "--textures", tex_dir, "--materials", os.path.join(psk_dir, "materials.json"),
               "--out", blend, "--name", name, "--scale", str(a.scale), "--spec-scale", str(a.spec_scale)]
        if not a.no_preview:
            cmd += ["--preview", os.path.join(blend_dir, "preview")]
        log("Blender: building %s" % blend)
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        built = None
        for line in res.stdout.splitlines():
            if line.startswith("[mho]"):
                log("  " + line[6:])
            if line.startswith("BUILD_DONE="):
                built = json.loads(line[len("BUILD_DONE="):])
        if res.returncode != 0 or built is None:
            log(res.stdout[-3000:])
            log(res.stderr[-3000:])
            raise SystemExit("Blender build failed (exit %d)" % res.returncode)
        sheet = None
        if built["previews"]:
            sheet = contact_sheet(built["previews"], os.path.join(blend_dir, "preview.png"))

        # metadata: the mod's own files (json as-is, icons as png) + a report
        for f in files:
            base = os.path.basename(f)
            if base.lower().endswith(".json") or base.lower().endswith(".txt"):
                shutil.copy2(f, os.path.join(meta_dir, base))
            elif base.lower().endswith(".dds") and os.path.isfile(a.texconv):
                subprocess.run([a.texconv, "-nologo", "-y", "-ft", "png", "-o", meta_dir, f], check=False,
                               stdout=subprocess.DEVNULL)
        report = {"source": os.path.abspath(a.source), "package": os.path.basename(pkg.path),
                  "package_version": "%d/%d" % (pkg.ver, pkg.lic), "mesh": pkg.obj_path(idx + 1), "name": name,
                  "mod": {k: manifest.get(k) for k in ("Name", "Author", "Version")} if manifest else None,
                  "bones": len(mesh["bones"]), "gpu_vertices": len(mesh["verts"]), "psk": psk,
                  "materials": {k: v["textures"] for k, v in used.items()}, "missing_textures": missing,
                  "scale": a.scale, "spec_scale": a.spec_scale, "blend": built, "preview": sheet,
                  "animsequences_not_converted": len(pkg.of_class("animsequence")), "notes": mesh["notes"]}
        with open(os.path.join(meta_dir, "report_%s.json" % name), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False, default=str)
        log("EXPORT_DONE=" + json.dumps({"blend": blend, "psk": psk["psk"], "preview": sheet,
                                         "height_m": built["height_m"], "faces": built["faces"],
                                         "bones": built["bones"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
