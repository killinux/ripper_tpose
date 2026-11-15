"""Resident Evil (RE Engine) Nexus character mod -> HD .blend + PMX + XPS, without the game.

    python -I scripts\\re_engine\\export_mod.py <mod .zip / folder> --game ResidentEvil3 --character Jill
           [--name Label] [--out-root E:\\game_export] [--colour MATERIAL_OR_MASTER=r,g,b ...] [--formats blend,pmx,xps]

* The mod's meshes are the *.mesh.<version> files in a ...\\mesh\\ folder under natives\\ (other folders inside a mod
  are usually the author's leftovers and are skipped); per name only the highest version.  The mesh whose name is
  its character folder (pl2000\\mesh\\pl2000.mesh) goes first and brings the armature; the others merge into it.
* Blender 4.5 + RE Mesh Editor (E:\\tools\\re_mesh_editor, loaded for that session only) imports them and converts the
  mod's .tex files; import_re_mesh.py writes an FBX + every material's texture bindings.
* texconv turns the converted .dds into PNG; build_blend.py (Blender 3.6) rebuilds the materials (see its docstring).
  Textures the mod does not bring (they are in the game's paks) leave their material in a flat colour - hair masters
  default to dark brown; --colour overrides by material or master name.
* scripts\\pmx_tools\\biped_pmx (rig re_engine) -> PMX and XPS.
Outputs <out-root>\\<game>\\<character>\\{blend,pmx,xps}\\<label>\\ and <work>\\report.json.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BLENDER45 = r"D:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
BLENDER36 = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
RE_SCRIPTS = r"E:\tools\re_mesh_editor\scripts"
TEXCONV = r"E:\tools\directxtex\texconv.exe"
SEVEN_ZIP = r"E:\tools\7zip\7z.exe"
WORK_ROOT = r"D:\re_engine_work"
DEFAULT_COLOURS = {"hair": (0.23, 0.15, 0.10)}


def log(msg):
    print(msg, flush=True)


def safe(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")


def unpack(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(dst, os.path.basename(src.rstrip("\\/"))))
    elif src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if info.is_dir() or name.startswith("/") or ".." in name.split("/"):
                    continue
                t = os.path.join(dst, *name.split("/"))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with z.open(info) as a, open(t, "wb") as b:
                    shutil.copyfileobj(a, b)
    else:
        subprocess.run([SEVEN_ZIP, "x", "-y", "-o" + dst, src], check=True, stdout=subprocess.DEVNULL)


def find_meshes(root):
    best = {}
    for dp, _dirs, files in os.walk(root):
        if os.path.basename(dp).lower() != "mesh" or "natives" not in dp.lower():
            continue
        for f in files:
            m = re.match(r"^(.+)\.mesh\.(\d+)$", f, re.I)
            if not m:
                continue
            key = (dp.lower(), m.group(1).lower())
            if key not in best or int(m.group(2)) > best[key][0]:
                best[key] = (int(m.group(2)), os.path.join(dp, f))
    paths = [p for _v, p in best.values()]

    def order(p):
        stem = os.path.basename(p).split(".")[0].lower()
        owner = os.path.basename(os.path.dirname(os.path.dirname(p))).lower()
        return (0 if stem == owner else 1, p.lower())
    return sorted(paths, key=order)


def contact_sheet(files, dst):
    """front / 3-4 / side / back on top, four head close-ups below (Pillow; skipped without it)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    body = [Image.open(f).convert("RGB") for f in files[:4]]
    heads = [Image.open(f).convert("RGB") for f in files[4:8]]
    h1 = 900
    body = [im.resize((int(im.width * h1 / im.height), h1)) for im in body]
    w = sum(im.width for im in body)
    h2 = w // max(len(heads), 1)
    sheet = Image.new("RGB", (w, h1 + (h2 if heads else 0)), (40, 41, 45))
    x = 0
    for im in body:
        sheet.paste(im, (x, 0))
        x += im.width
    for i, im in enumerate(heads):
        sheet.paste(im.resize((h2, h2)), (i * h2, h1))
    sheet.save(dst)
    return dst


def run(cmd, env=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--game", required=True)
    ap.add_argument("--character", required=True)
    ap.add_argument("--name")
    ap.add_argument("--out-root", default=r"E:\game_export")
    ap.add_argument("--colour", action="append", default=[])
    ap.add_argument("--formats", default="blend,pmx,xps")
    ap.add_argument("--no-preview", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = os.path.splitext(os.path.basename(a.source.rstrip("\\/")))[0]
    m = re.match(r"^(.*?) (\d+) [\w.]+ \d{4}-\d\d-\d\dT", base) or re.match(r"^(.*?)-(\d+)(?:-\w+)*-\d{9,11}$", base)
    label = safe(a.name or (("%s_%s" % (m.group(1), m.group(2))) if m else base))
    work = os.path.join(WORK_ROOT, label)
    src = os.path.join(work, "unpacked")
    unpack(a.source, src)
    roots = sorted({os.path.dirname(dp) for dp, dirs, _f in os.walk(src) if os.path.basename(dp).lower() == "natives"})
    if not roots:
        raise SystemExit("no natives folder in " + a.source)
    names = [os.path.basename(r) for r in roots]
    common = os.path.commonprefix(names) if len(names) > 1 else ""
    for r in roots:
        tail = safe(os.path.basename(r)[len(common):]) if len(roots) > 1 else ""
        export_variant(a, label + ("_" + tail if tail else ""), r, os.path.join(work, tail or "main"))


def export_variant(a, label, src, work):
    os.makedirs(work, exist_ok=True)
    meshes = find_meshes(src)
    if not meshes:
        raise SystemExit("no natives\\...\\mesh\\*.mesh.* in " + a.source)
    log("%s: %d mesh file(s): %s" % (label, len(meshes), ", ".join(os.path.relpath(p, src) for p in meshes)))
    fbx, mjson = os.path.join(work, label + ".fbx"), os.path.join(work, label + "_materials.json")
    cmd = [BLENDER45, "-b", "--python", os.path.join(HERE, "import_re_mesh.py"), "--", "--out-fbx", fbx,
           "--out-json", mjson]
    for p in meshes:
        cmd += ["--mesh", p]
    out = run(cmd, env=dict(os.environ, BLENDER_USER_SCRIPTS=RE_SCRIPTS))
    if "RE_IMPORT_DONE=" not in out:
        log(out[-3000:])
        raise SystemExit("RE Mesh Editor import failed")
    with open(mjson, encoding="utf-8") as fh:
        info = json.load(fh)
    log("  imported: %d objects (dropped %d placeholder submeshes), %d materials" % (
        len(info["objects"]), len(info["dropped"]), len(info["materials"])))
    tex = os.path.join(work, "textures")
    os.makedirs(tex, exist_ok=True)
    dds = sorted({b["dds"] for mat in info["materials"].values() for b in mat["textures"].values() if b.get("dds")})
    for f in dds:
        subprocess.run([TEXCONV, "-nologo", "-y", "-ft", "png", "-o", tex, f], stdout=subprocess.DEVNULL)
    log("  %d textures converted" % len(dds))
    colours = dict(DEFAULT_COLOURS)
    for c in a.colour:
        k, v = c.split("=", 1)
        colours[k.lower()] = tuple(float(x) for x in v.split(","))
    root = os.path.join(a.out_root, a.game, a.character)
    blend_dir = os.path.join(root, "blend", label)
    blend = os.path.join(blend_dir, label + ".blend")
    cmd = [BLENDER36, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"), "--", "--fbx", fbx,
           "--json", mjson, "--textures", tex, "--out", blend, "--name", label]
    for k, v in colours.items():
        cmd += ["--colour", "%s=%s" % (k, ",".join(str(x) for x in v))]
    if not a.no_preview:
        cmd += ["--preview", os.path.join(blend_dir, "preview")]
    out = run(cmd)
    for line in out.splitlines():
        if line.startswith("[re]"):
            log("    " + line[5:])
    mm = re.search(r"BUILD_DONE=(\{.*\})", out)
    if not mm:
        log(out[-3000:])
        raise SystemExit("Blender build failed")
    built = json.loads(mm.group(1))
    if built["previews"]:
        contact_sheet(built["previews"], os.path.join(blend_dir, "preview.png"))
    rep = {"label": label, "source": os.path.abspath(a.source), "meshes": meshes, "import": info, "built": built}
    biped = os.path.join(REPO, "scripts", "pmx_tools", "biped_pmx")
    if "pmx" in a.formats:
        o = run([BLENDER36, "-b", blend, "--python", os.path.join(biped, "export_pmx_blender.py"), "--", "--rig",
                 "re_engine", "--out", os.path.join(root, "pmx", label), "--name", label, "--model-name", label])
        mm = re.search(r"BIPED_PMX=(\{.*\})", o)
        rep["pmx"] = json.loads(mm.group(1)) if mm else {"error": o[-2000:]}
        log("  PMX: %s" % (rep["pmx"].get("pmx") or rep["pmx"].get("error", "")[-600:]))
    if "xps" in a.formats:
        o = run([BLENDER36, "-b", blend, "--factory-startup", "--python", os.path.join(biped, "export_xps_blender.py"),
                 "--", "--rig", "re_engine", "--out", os.path.join(root, "xps", label), "--name", label])
        mm = re.search(r"BIPED_XPS=(\{.*\})", o)
        rep["xps"] = json.loads(mm.group(1)) if mm else {"error": o[-2000:]}
        log("  XPS: %s" % (rep["xps"].get("path") or rep["xps"].get("error", "")[-600:]))
    with open(os.path.join(work, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False, default=str)
    log("RE_EXPORT_DONE=" + json.dumps({"blend": blend, "flat": built.get("flat_materials"),
                                         "height_m": built.get("height_m")}, ensure_ascii=False))




if __name__ == "__main__":
    main()
