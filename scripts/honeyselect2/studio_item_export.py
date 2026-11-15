"""HoneySelect 2 Studio item zipmod (e.g. a ported character like "[Fouetty] Venom Marvel Rivals") -> HD .blend
(+ PMX / XPS when a rig map fits), without the game.

    python -I scripts\\honeyselect2\\studio_item_export.py <x.zipmod> [--out-root E:\\game_export\\HoneySelect2]
           [--character Venom] [--name Label] [--rig rigify] [--formats blend,pmx,xps]

* The zipmod (a zip) is unpacked to a new work folder; abdata\\studio\\info\\*\\ItemList_*.csv names each item's bundle
  and prefab (columns Bundle / Object).
* AssetStudioModCLI (E:\\tools\\AssetStudioModCLI_net472) exports the prefab with -m splitObjects -> FBX (skinned).
* UnityPy reads every material of the bundle: texture slots (_MainTex, _BumpMap, _MetallicGlossMap ...) -> PNG per
  texture path id (two textures may share a name), so the spec names each slot's own image.
* scripts\\marvelrivals\\build_blend.py builds the materials (texture-name suffixes _D / _N / _ORM decide the role
  when the slot name does not; normal maps called *OpenGL* are not flipped).  HS2 units are 0.1 m: the FBX comes in at
  x0.01 and is scaled x10 more.
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ASSETSTUDIO = r"E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
WORK_ROOT = r"D:\hs2_studio_work"


def log(msg):
    print(msg, flush=True)


def safe(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")


def unpack(zp, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name.startswith("/") or ".." in name.split("/"):
                continue
            t = os.path.join(dst, *name.split("/"))
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with z.open(info) as a, open(t, "wb") as b:
                shutil.copyfileobj(a, b)


def items(root):
    out = []
    for f in glob.glob(os.path.join(root, "abdata", "studio", "info", "**", "ItemList_*.csv"), recursive=True):
        with open(f, encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        head = rows[0]
        for r in rows[1:]:
            d = dict(zip(head, r))
            if d.get("Bundle") and d.get("Object"):
                out.append({"name": d.get("Name") or d["Object"], "bundle": d["Bundle"], "object": d["Object"]})
    return out


def material_spec(bundle, tex_dir):
    """{material name: {"textures": {slot: png}}} with every texture written once per path id."""
    import UnityPy
    env = UnityPy.load(bundle)
    os.makedirs(tex_dir, exist_ok=True)
    written = {}
    spec = {}
    for o in env.objects:
        if o.type.name != "Material":
            continue
        m = o.read()
        slots = {}
        for name, env_ in m.m_SavedProperties.m_TexEnvs:
            if not env_.m_Texture.path_id:
                continue
            pid = env_.m_Texture.path_id
            if pid not in written:
                tex = env_.m_Texture.read()
                path = os.path.join(tex_dir, "%s_%d.png" % (safe(tex.m_Name), pid & 0xFFFFFFFF))
                tex.image.save(path)
                written[pid] = path
            slots[name] = written[pid]
        spec[m.m_Name] = {"textures": slots}
    return spec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zipmod")
    ap.add_argument("--out-root", default=r"E:\game_export\HoneySelect2")
    ap.add_argument("--character")
    ap.add_argument("--name")
    ap.add_argument("--rig", default="")
    ap.add_argument("--formats", default="blend")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    stem = os.path.splitext(os.path.basename(a.zipmod))[0]
    work = os.path.join(WORK_ROOT, safe(stem))
    src = os.path.join(work, "unpacked")
    unpack(a.zipmod, src)
    its = items(src)
    if not its:
        raise SystemExit("no studio ItemList_*.csv with Bundle / Object in " + a.zipmod)
    for it in its:
        label = safe(a.name or it["name"])
        bundle = os.path.join(src, "abdata", *it["bundle"].split("/"))
        log("%s: %s / %s" % (label, it["bundle"], it["object"]))
        fbx_dir = os.path.join(work, label, "fbx")
        subprocess.run([ASSETSTUDIO, bundle, "-m", "splitObjects", "-o", fbx_dir, "--fbx-scale-factor", "1", "-r"],
                       stdout=subprocess.DEVNULL)
        fbxs = glob.glob(os.path.join(fbx_dir, "**", "*.fbx"), recursive=True)
        fbx = next((f for f in fbxs if os.path.splitext(os.path.basename(f))[0] == it["object"]), fbxs[0] if fbxs else None)
        if not fbx:
            log("  AssetStudio wrote no FBX")
            continue
        mats = material_spec(bundle, os.path.join(work, label, "tex"))
        spec = {"name": label, "fbx": fbx, "scale": 10.0, "materials": mats}
        spec_path = os.path.join(work, label, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=1, ensure_ascii=False)
        char = a.character or label
        blend_dir = os.path.join(a.out_root, char, "blend", label)
        blend = os.path.join(blend_dir, label + ".blend")
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python",
                            os.path.join(REPO, "scripts", "marvelrivals", "build_blend.py"), "--", "--spec", spec_path,
                            "--out", blend, "--preview", os.path.join(blend_dir, "preview")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            if line.startswith("[mr]"):
                log("    " + line[5:])
        m = re.search(r"BUILD_DONE=(\{.*\})", r.stdout)
        if not m:
            log((r.stdout + r.stderr)[-2500:])
            continue
        built = json.loads(m.group(1))
        sys.path.insert(0, os.path.join(REPO, "scripts", "re_engine"))
        from export_mod import contact_sheet  # noqa: E402
        if built["previews"]:
            contact_sheet(built["previews"], os.path.join(blend_dir, "preview.png"))
        rep = {"label": label, "zipmod": os.path.abspath(a.zipmod), "item": it, "built": built}
        biped = os.path.join(REPO, "scripts", "pmx_tools", "biped_pmx")
        if a.rig and "pmx" in a.formats:
            o = subprocess.run([BLENDER, "-b", blend, "--python", os.path.join(biped, "export_pmx_blender.py"), "--",
                                "--rig", a.rig, "--out", os.path.join(a.out_root, char, "pmx", label), "--name", label],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            mm = re.search(r"BIPED_PMX=(\{.*\})", o.stdout)
            rep["pmx"] = json.loads(mm.group(1)) if mm else {"error": (o.stdout + o.stderr)[-2000:]}
            log("  PMX: %s" % (rep["pmx"].get("pmx") or rep["pmx"].get("error", "")[-500:]))
        if a.rig and "xps" in a.formats:
            o = subprocess.run([BLENDER, "-b", blend, "--factory-startup", "--python",
                                os.path.join(biped, "export_xps_blender.py"), "--", "--rig", a.rig, "--out",
                                os.path.join(a.out_root, char, "xps", label), "--name", label],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            mm = re.search(r"BIPED_XPS=(\{.*\})", o.stdout)
            rep["xps"] = json.loads(mm.group(1)) if mm else {"error": (o.stdout + o.stderr)[-2000:]}
            log("  XPS: %s" % (rep["xps"].get("path") or rep["xps"].get("error", "")[-500:]))
        with open(os.path.join(work, label, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1, ensure_ascii=False, default=str)
        log("HS2_STUDIO_DONE=" + json.dumps({"blend": blend, "height_m": built.get("height_m")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
