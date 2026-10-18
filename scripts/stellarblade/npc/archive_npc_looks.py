r"""Archive the built looks (build_npc_looks.py) to E:\game_export\StellarBlade\<char>\blend\<look>\ and list them in
the SB gallery.

    python archive_npc_looks.py [--only Raven,Lily_01] [--no-gallery]

Per look: scripts/archive/blend_package.py makes the .blend self-contained (every texture copied into textures\ and
linked relatively, the saved file reopened and checked), then the previews, package.json (parts, slots, stats) and a
README.txt go next to it. The archive manifest (_meta\stellarblade_models_manifest.json) gets one entry per look
(label NPC_<look>, kind "npc", or "nude" for a nude body; an existing entry of that label is replaced), and
scripts\stellarblade\html\make_gallery.py regenerates the page from it."""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
PACKAGE = os.path.join(REPO, "scripts", "archive", "blend_package.py")
GALLERY = os.path.join(REPO, "scripts", "stellarblade", "html", "make_gallery.py")
PREVIEWS = ("preview.png", "preview_back.png", "preview_face.png", "preview_nude.png", "preview_nude_back.png")


def readme(look, report, files):
    kind = {"nude": "裸体 / nude body"}.get(look.get("kind"), "其他角色 / other character")
    lines = [
        "Stellar Blade - %s (%s)" % (look["char"], look["label"]),
        "=" * 60,
        "",
        "造型 / Look    : %s" % look["name"],
        "说明 / Variant : %s" % (look.get("variant") or "-"),
        "类型 / Kind    : %s" % kind,
        "游戏包 / Packages:",
    ] + ["  SB/Content/%s" % p for p in look["parts"]] + [
        "",
        "这个文件夹是独立的：.blend 里的贴图全部用 //textures/ 相对路径引用，整个文件夹拷到别的电脑直接打开。",
        "This folder is self-contained: every texture is linked relatively from textures\\.",
        "",
        "文件 / Files",
        "  %s.blend   Blender 3.6.15 保存 / saved with Blender 3.6.15" % look["name"],
        "  textures\\    %d 张 PNG（游戏原图），材质里已接好 / game textures, wired in the materials" % files,
        "  preview*.png  正面 / 背面 / 头部；preview_nude*.png = 藏起衣服和头发后剩下的（看衣服下面有没有身体）",
        "                front / back / head; preview_nude* = what is left with clothes and hair hidden",
        "  package.json  游戏包、每个材质槽（主材质、类别、贴图）、网格统计 / packages, slots, stats",
        "",
        "模型 / Model",
        "  顶点 / vertices : %d" % report["vertices"],
        "  面 / polygons   : %d" % report["polygons"],
        "  骨骼 / bones    : %d（游戏骨架 Bip001；脸、头发是另外的骨架，挂在身体骨架下面，静止姿势已对齐）" % report["bones"],
        "  单位 / units    : 厘米，身高约 %d；Blender 里显示成 %d m 是正常的" % (report["height_cm"], report["height_cm"]),
        "",
        "材质 / Materials",
        "  预览版：Principled BSDF + 游戏的颜色图 / 法线图；头发按游戏的发根、发梢颜色上色，按发片贴图裁剪；",
        "  眼睛用游戏的虹膜 / 眼白网络和这个角色自己的参数；眼睛水膜、眼影壳、泪线、牙齿遮挡这类叠加层隐藏。",
        "  Preview materials: Principled BSDF with the game's colour / normal maps; hair coloured from its root / tip",
        "  colours and cut out by its cards' map; eyes from the game's iris network with this character's own values.",
        "",
        "导出：scripts/stellarblade/npc（ripper_tpose），%s" % datetime.date.today().isoformat(),
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\stellarblade_npc")
    ap.add_argument("--dest", default=r"E:\game_export\StellarBlade")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-gallery", action="store_true")
    o = ap.parse_args()
    looks = json.load(open(os.path.join(HERE, "npc_looks.json"), encoding="utf-8"))["looks"]
    only = {s for s in o.only.split(",") if s}
    looks = [l for l in looks if (not only or l["name"] in only)
             and os.path.exists(os.path.join(o.root, "looks", l["name"], l["name"] + ".blend"))]
    jobs = []
    for l in looks:
        src_dir = os.path.join(o.root, "looks", l["name"])
        dst_dir = os.path.join(o.dest, l["char"], "blend", l["name"])
        jobs.append({"src": os.path.join(src_dir, l["name"] + ".blend"), "dest": os.path.join(dst_dir, l["name"] + ".blend"),
                     "product_src": src_dir, "product_dest": dst_dir})
    tmp = tempfile.mkdtemp(prefix="sb_npc_archive_")
    jobs_path, result_path = os.path.join(tmp, "jobs.json"), os.path.join(tmp, "result.json")
    json.dump(jobs, open(jobs_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", PACKAGE, "--", jobs_path, result_path],
                   capture_output=True, text=True, errors="replace")
    result = json.load(open(result_path, encoding="utf-8"))
    manifest_path = os.path.join(o.dest, "_meta", "stellarblade_models_manifest.json")
    manifest = json.load(open(manifest_path, encoding="utf-8-sig"))
    for l, job in zip(looks, jobs):
        r = result.get(job["dest"], {"problems": ["blend_package.py wrote nothing"]})
        src_dir, dst_dir = job["product_src"], job["product_dest"]
        report = json.load(open(os.path.join(src_dir, "report.json"), encoding="utf-8"))
        for f in PREVIEWS:
            if os.path.exists(os.path.join(src_dir, f)):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(dst_dir, f))
        textures = sorted(os.path.relpath(t, dst_dir).replace("\\", "/") for _, t in r.get("copied", []))
        package = dict(l, report=report, textures=textures, missing=r.get("missing", []), problems=r.get("problems", []),
                       blend=os.path.basename(job["dest"]), blend_bytes=os.path.getsize(job["dest"]) if os.path.exists(job["dest"]) else 0)
        json.dump(package, open(os.path.join(dst_dir, "package.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(os.path.join(dst_dir, "README.txt"), "w", encoding="utf-8-sig").write(readme(l, report, len(textures)))
        warnings = list(l.get("warnings", [])) + ["打包: %s" % p for p in r.get("problems", [])]
        warnings += ["源文件缺贴图: %s" % m for m in r.get("missing", [])]
        label = "NPC_" + l["name"]
        entry = {
            "label": label, "package": l["parts"][0].rsplit("/", 1)[1],
            "name": "%s %s" % (l["label"], l.get("variant") or ""), "group": l["char"],
            "kind": l.get("kind", "npc"), "blend": job["dest"], "preview": os.path.join(dst_dir, "preview.png"),
            "packageDir": dst_dir, "facePreview": os.path.join(dst_dir, "preview_face.png"),
            "blendSize": package["blend_bytes"], "meshes": len(l["parts"]), "vertices": report["vertices"],
            "polygons": report["polygons"], "bones": report["bones"], "armatures": len(l["parts"]),
            "materials": sum(1 for m in report["materials"] if m["kind"] != "hidden"), "morphs": 0,
            "xps": "", "pmx": "", "pmxPreviews": [], "warnings": warnings,
        }   # no "hq": the gallery reads it as the HQ build (badge 高清材质); these are the preview-material builds
        manifest["results"] = [e for e in manifest["results"] if e.get("label") != label] + [entry]
        print("%-16s -> %s  textures %d  missing %d  problems %d" % (l["name"], dst_dir, len(textures),
                                                                      len(r.get("missing", [])), len(r.get("problems", []))))
    shutil.copy2(manifest_path, manifest_path + ".bak_npc")
    with open(manifest_path + ".part", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(manifest_path + ".part", manifest_path)
    if not o.no_gallery:
        subprocess.run([sys.executable, GALLERY], check=False)


if __name__ == "__main__":
    main()
