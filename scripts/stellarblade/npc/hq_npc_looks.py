r"""HQ .blend of every archived look with the SB HQ scripts, run unchanged: ../hq_materials.py (materials.json: maps
and values per material, eyes from each character's own M_EyeRefractive instance) -> ../hq_materials_blender.py
(ORM roughness / metallic / specular occlusion, the DirectX normal map, emission, clip; the game's eye network).

    python hq_npc_looks.py [--only Raven,Lily_01] [--lanes 3]

Per look (E:\game_export\StellarBlade\<char>\blend\<look>\):
  1. staging in <root>\hq\<look>\: hq_materials.py reads only files named MI_*.json, takes each instance's own
     parameters (no parent instance's nor the master's) and looks for maps in one flat folder - so every cloth / skin /
     eye instance the look uses is written there as MI_<name>.json with its parents' parameters merged in (UE's rule:
     the child's value wins; Parent = the master material) and the master's defaults for what none sets, and every
     map they name is hard-linked into tex\;
  2. hq_materials.py --mi-json mi --textures tex --out out;
  3. hq_materials_blender.py on the archived <look>.blend -> <look>_HQ.blend, its maps copied into textures\;
  4. render_look.py: hq_preview*.png, and 高清材质对比.jpg (preview vs HQ, body and head);
  5. the gallery manifest entry gets "hq" (the .blend and the comparison), the page is regenerated.
Hair, brows and lashes keep build_npc_blend.py's wiring (hq_materials.py describes MA_CH_Standard_Ver03-style
parameters: Basecolor / ORM / Baked NormalMap / Emissive)."""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SB = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SB))
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
KINDS = ("cloth", "body", "eye")         # hidden shells, hair, brows / lashes keep the preview wiring
# master defaults hq_materials.describe() reads (EmissivePower / EmissiveColor / Emissive_CH: it lights only the
# selected channel of "Emissive", and only with power > 0 and a colour - fixed there 10-18 after Iberis' stockings
# glowed orange-pink from her mask map, whose selected blue channel is empty)
MASTER_DEFAULTS = {"Metallic", "Roughness Min", "Roughness Max", "ClearCoatRoughness Min", "Fuzz_01_INTENSITY",
                   "EmissivePower", "Pattern01_Tiling", "Pattern01_NormalIntensity", "Pattern01_RoughnessIntencity",
                   "EmissiveColor", "Emissive_CH"}


def index_json(root):
    """material name -> its export (instances and masters) from the json folder"""
    out = {}
    for f in glob.glob(os.path.join(root, "json", "**", "*.json"), recursive=True):
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
        except ValueError:
            continue
        for e in data if isinstance(data, list) else []:
            if e.get("Type", "").startswith("MaterialInstance") or e.get("Type") == "Material":
                out.setdefault(e["Name"], e)
    return out


def quoted(ref):
    return ref.split("'")[1] if "'" in ref else ref


def flatten(name, mats):
    """the instance with its parent instances' parameters merged in (the child's value wins); None for a master"""
    e = mats.get(name)
    if e is None or not e.get("Type", "").startswith("MaterialInstance"):
        return None
    chain = [e]
    while True:
        par = quoted(((chain[-1].get("Properties") or {}).get("Parent") or {}).get("ObjectName", ""))
        nxt = mats.get(par)
        if nxt is None or len(chain) > 10:
            break
        chain.append(nxt)
        if not nxt.get("Type", "").startswith("MaterialInstance"):
            break
    master_ref = (chain[-1].get("Properties") or {}).get("Parent") if chain[-1].get("Type", "").startswith(
        "MaterialInstance") else {"ObjectName": "Material'%s'" % chain[-1]["Name"],
                                  "ObjectPath": chain[-1].get("Package", chain[-1]["Name"]) + "." + chain[-1]["Name"]}
    merged = {}
    for key in ("ScalarParameterValues", "VectorParameterValues", "TextureParameterValues"):
        by_name = {}
        for inst in reversed([c for c in chain if c.get("Type", "").startswith("MaterialInstance")]):
            for s in (inst.get("Properties") or {}).get(key) or []:
                if key == "TextureParameterValues" and not (s.get("ParameterValue") or {}).get("ObjectPath"):
                    continue          # an unset map (null): hq_materials.read_instance needs an ObjectPath
                by_name[s["ParameterInfo"]["Name"]] = s
        merged[key] = list(by_name.values())
    # what no instance sets comes from the master's own defaults (CachedExpressionData: names in ParameterInfos,
    # values in the same order), not from hq_materials.py's MA_CH_Standard_Ver03 DEFAULTS
    master = chain[-1] if chain[-1].get("Type") == "Material" else None
    if master is not None:
        params = ((master.get("Properties") or {}).get("CachedExpressionData") or {}).get("Parameters") or {}
        for key, entries, values in (("ScalarParameterValues", "RuntimeEntries", "ScalarValues"),
                                     ("VectorParameterValues", "RuntimeEntries[1]", "VectorValues")):
            names = [p.get("Name") for p in (params.get(entries) or {}).get("ParameterInfos") or []]
            have = {s["ParameterInfo"]["Name"] for s in merged[key]}
            for n, v in zip(names, params.get(values) or []):
                if n in MASTER_DEFAULTS and n not in have:
                    merged[key].append({"ParameterInfo": {"Name": n, "Association": "GlobalParameter", "Index": -1},
                                        "ParameterValue": v})
    switches = {}
    for inst in reversed([c for c in chain if c.get("Type", "").startswith("MaterialInstance")]):
        for s in ((inst.get("Properties") or {}).get("StaticParameters") or {}).get("StaticSwitchParameters") or []:
            switches[s["ParameterInfo"]["Name"]] = s
    props = dict(merged, Parent=master_ref, StaticParameters={"StaticSwitchParameters": list(switches.values())})
    for inst in chain:                                   # the nearest BlendMode override
        bpo = (inst.get("Properties") or {}).get("BasePropertyOverrides")
        if bpo and "BlendMode" in bpo:
            props["BasePropertyOverrides"] = {"BlendMode": bpo["BlendMode"]}
            break
    return [{"Type": e["Type"], "Name": e["Name"], "Properties": props}]


def link(src, dst):
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def stage(look, report, mats, pngs, root):
    base = os.path.join(root, "hq", look["name"])
    mi_dir, tex_dir = os.path.join(base, "mi"), os.path.join(base, "tex")
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(mi_dir)
    os.makedirs(tex_dir)
    staged, missing = [], []
    for m in report["materials"]:
        if m["kind"] not in KINDS:
            continue
        name = m["material"].split(".")[0]
        flat = flatten(name, mats)
        if flat is None:
            continue
        fname = name if name.startswith("MI_") else "MI_" + name     # hq_materials.py globs MI_*.json
        json.dump(flat, open(os.path.join(mi_dir, fname + ".json"), "w", encoding="utf-8"), indent=1)
        staged.append(name)
        for t in flat[0]["Properties"]["TextureParameterValues"]:
            tname = t["ParameterValue"]["ObjectPath"].split("/")[-1].split(".")[0]
            src = pngs.get(tname.lower())
            if src:
                link(src, os.path.join(tex_dir, tname + ".png"))
            elif not os.path.exists(os.path.join(tex_dir, tname + ".png")):
                missing.append(tname)
    return base, staged, sorted(set(missing))


def compare_sheet(dst_dir, out):
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24)
    H = 900
    tiles = []
    for f, title in (("preview.png", "预览版"), ("hq_preview.png", "高清版"), ("preview_face.png", "预览版"),
                     ("hq_preview_face.png", "高清版")):
        p = os.path.join(dst_dir, f)
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        im = im.resize((int(im.width * H / im.height), H))
        t = Image.new("RGB", (im.width, H + 40), (30, 30, 34))
        t.paste(im, (0, 40))
        ImageDraw.Draw(t).text((8, 4), title, fill=(255, 220, 160), font=font)
        tiles.append(t)
    sheet = Image.new("RGB", (sum(t.width for t in tiles), H + 40), (30, 30, 34))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    sheet.save(out, quality=88)


def run(look, o, mats, pngs):
    dst_dir = os.path.join(o.dest, look["char"], "blend", look["name"])
    blend = os.path.join(dst_dir, look["name"] + ".blend")
    hq_blend = os.path.join(dst_dir, look["name"] + "_HQ.blend")
    report = json.load(open(os.path.join(dst_dir, "package.json"), encoding="utf-8"))["report"]
    base, staged, missing = stage(look, report, mats, pngs, o.root)
    out_dir = os.path.join(base, "out")
    r1 = subprocess.run([sys.executable, os.path.join(SB, "hq_materials.py"), "--mi-json", os.path.join(base, "mi"),
                         "--textures", os.path.join(base, "tex"), "--out", out_dir],
                        capture_output=True, text=True, errors="replace")
    log = "== hq_materials.py\n" + r1.stdout + r1.stderr
    if r1.returncode != 0 or not os.path.exists(os.path.join(out_dir, "materials.json")):
        open(os.path.join(base, "hq.log"), "w", encoding="utf-8").write(log)
        return look["name"], "hq_materials.py FAILED (see %s)" % os.path.join(base, "hq.log")
    r2 = subprocess.run([BLENDER, "-b", "--factory-startup", blend, "--python", os.path.join(SB, "hq_materials_blender.py"),
                         "--", "--materials", os.path.join(out_dir, "materials.json"), "--save", hq_blend,
                         "--copy-textures", os.path.join(dst_dir, "textures")],
                        capture_output=True, text=True, errors="replace")
    log += "\n== hq_materials_blender.py\n" + r2.stdout[-20000:] + r2.stderr[-5000:]
    r3 = subprocess.run([BLENDER, "-b", "--factory-startup", hq_blend, "--python", os.path.join(HERE, "render_look.py"),
                         "--", os.path.join(dst_dir, "hq_preview")], capture_output=True, text=True, errors="replace")
    outside = [l.split("=", 1)[1] for l in r3.stdout.splitlines() if l.startswith("SB_NPC_OUTSIDE=")]
    log += "\n== render_look.py\n" + "\n".join(outside)
    open(os.path.join(base, "hq.log"), "w", encoding="utf-8").write(log)
    shutil.copy2(os.path.join(base, "hq.log"), os.path.join(dst_dir, "hq_log.txt"))
    shutil.copy2(os.path.join(out_dir, "materials.json"), os.path.join(dst_dir, "hq_materials.json"))
    compare_sheet(dst_dir, os.path.join(dst_dir, "高清材质对比.jpg"))
    eye_lines = [l.strip() for l in r2.stdout.splitlines() if "game eye of" in l]
    return look["name"], {"staged": staged, "missing_maps": missing, "eyes": eye_lines, "outside": outside,
                          "hq_blend": hq_blend if os.path.exists(hq_blend) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\stellarblade_npc")
    ap.add_argument("--dest", default=r"E:\game_export\StellarBlade")
    ap.add_argument("--only", default="")
    ap.add_argument("--lanes", type=int, default=3)
    ap.add_argument("--no-gallery", action="store_true")
    o = ap.parse_args()
    looks = json.load(open(os.path.join(HERE, "npc_looks.json"), encoding="utf-8"))["looks"]
    only = {s for s in o.only.split(",") if s}
    looks = [l for l in looks if not only or l["name"] in only]
    mats = index_json(o.root)
    pngs = {}
    for f in glob.glob(os.path.join(o.root, "raw", "**", "*.png"), recursive=True):
        pngs.setdefault(os.path.splitext(os.path.basename(f))[0].lower(), f)
    with ThreadPoolExecutor(o.lanes) as pool:
        results = list(pool.map(lambda l: run(l, o, mats, pngs), looks))
    manifest_path = os.path.join(o.dest, "_meta", "stellarblade_models_manifest.json")
    manifest = json.load(open(manifest_path, encoding="utf-8-sig"))
    for (name, r), look in zip(results, looks):
        print(name, json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r)
        if not isinstance(r, dict) or not r["hq_blend"]:
            continue
        dst_dir = os.path.dirname(r["hq_blend"])
        for e in manifest["results"]:
            if e.get("label") == "NPC_" + name:
                e["hq"] = [["高清 .blend（游戏完整材质）", r["hq_blend"]],
                           ["高清材质对比", os.path.join(dst_dir, "高清材质对比.jpg")]]
        pkg_path = os.path.join(dst_dir, "package.json")
        pkg = json.load(open(pkg_path, encoding="utf-8"))
        pkg["hq"] = {"blend": os.path.basename(r["hq_blend"]), "materials": "hq_materials.json", "staged": r["staged"],
                     "missing_maps": r["missing_maps"], "eyes": r["eyes"], "outside": r["outside"]}
        json.dump(pkg, open(pkg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        readme = os.path.join(dst_dir, "README.txt")
        text = open(readme, encoding="utf-8-sig").read()
        if "_HQ.blend" not in text:
            text += ("\n高清版 / HQ\n"
                     "  %s_HQ.blend   游戏完整材质：ORM（粗糙度、金属度、高光遮蔽）、DirectX 法线、自发光、裁剪，\n"
                     "                 眼睛用这个角色自己的眼睛参数（虹膜大小、色调、亮度）；头发、眉毛、睫毛同预览版\n"
                     "                 the game's full materials (ORM, DirectX normals, emission, clip, own eye values)\n"
                     "  hq_preview*.png  高清版的正面 / 背面 / 头部；高清材质对比.jpg = 预览版和高清版并排\n"
                     "  hq_materials.json / hq_log.txt  hq_materials.py 读出的每个材质的贴图和参数 / 运行记录\n"
                     "  做法：scripts/stellarblade/npc/hq_npc_looks.py（调用 ../hq_materials.py、../hq_materials_blender.py）\n"
                     % name)
            open(readme, "w", encoding="utf-8-sig").write(text)
    with open(manifest_path + ".part", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(manifest_path + ".part", manifest_path)
    if not o.no_gallery:
        subprocess.run([sys.executable, os.path.join(SB, "html", "make_gallery.py")], check=False)


if __name__ == "__main__":
    main()
