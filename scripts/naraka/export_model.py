"""Export NARAKA: BLADEPOINT models to .blend (+ FBX) with preview renders.

    python export_model.py --outfit ch_f_ming_haikou_lv_s0          # outfit + its hair + default face
    python export_model.py --outfit ch_f_ming_haikou_lv_s0 --hair ch_f_hair_05
    python export_model.py --outfit ch_m_ming_haoxia_lv_s1 --no-hair --no-face
    python export_model.py --family ch_f_ming_haikou                  # every outfit of a family
    python export_model.py --all-outfits [--sex f]                    # all 834 (hours; batch_export.py runs it in parallel)
    python export_model.py --prefab mo_pve_a_bigstonewolf_01          # any prefab by name or asset path
    python export_model.py --group full_body                          # a whole list group

Common: --fbx, --keep-fx, --no-preview, --no-blend (scene.json + parts + textures only), --force,
--ui (use the *_ui copies), --no-html, --out D:\\naraka_exports, --blender <exe>.

Output: <out>\\outfits\\<name>\\<name>.blend, _preview/_side/_back/_face.png, scene.json,
parts\\*.npz, textures\\*.png, export.json; standalone prefabs go to <out>\\items\\<name>.
Mechanism and pitfalls: docs\\naraka-bladepoint-extraction.md.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import naraka_catalog  # noqa: E402
import naraka_env  # noqa: E402
import naraka_scene  # noqa: E402
from list_models import OUT, export_dir, write_html  # noqa: E402

BLENDER = os.environ.get("BLENDER", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")


def run_blender(blender, out_dir, name, fbx, preview):
    cmd = [blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "build_blend.py"), "--",
           "--scene", os.path.join(out_dir, "scene.json"), "--out", os.path.join(out_dir, name + ".blend")]
    if fbx:
        cmd.append("--fbx")
    if not preview:
        cmd.append("--no-preview")
    with open(os.path.join(out_dir, "build.log"), "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    report = None
    with open(os.path.join(out_dir, "build.log"), encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("NARAKA_REPORT="):
                report = json.loads(line[len("NARAKA_REPORT="):])
    if proc.returncode != 0 or report is None:
        raise RuntimeError("blender failed (see %s)" % os.path.join(out_dir, "build.log"))
    return report


def unresolved(scene):
    return sum(1 for line in scene.log if "unresolved" in line or "off by" in line)


def build_outfit(game, catalog, item, args):
    by_name = {i.name: i for i in catalog}
    sex = item.sex or "f"
    hair = None
    if args.hair and args.hair != "none":
        hair = by_name.get(args.hair)
        if hair is None:
            raise SystemExit("no hair prefab named %s" % args.hair)
    elif not args.no_hair:
        hair, how = naraka_catalog.hair_for(catalog, item)
        if hair is not None:
            print("  hair: %s (%s)" % (hair.name, how))
    out_dir = export_dir(item, args.out)
    scene = naraka_scene.Scene(item.name, out_dir)
    asm = naraka_scene.Assembler(game, scene, sex, keep_fx=args.keep_fx)
    asm.add_prefab(item.path, "outfit")
    if hair is not None:
        asm.add_prefab(hair.path, "hair")
    if not args.no_face and sex in asm.FACES:
        asm.add_prefab(asm.FACES[sex], "face")
    code, zh = naraka_catalog.hero_of(item.family)
    meta = {"outfit": item.path, "hair": hair.path if hair else None, "hero": code, "hero_zh": zh,
            "face": None if args.no_face else asm.FACES.get(sex), "skeleton": asm.skeleton,
            "family": item.family, "bundle": item.bundle}
    return scene, meta


def build_standalone(game, item, args):
    """Whole models (monsters, NPCs) bind to a separate dummy-body skeleton like the
    heroes do; weapons and props carry their own hierarchy."""
    out_dir = export_dir(item, args.out)
    scene = naraka_scene.Scene(item.name, out_dir)
    skel = naraka_scene.skeleton_for(game, item.name) if item.group != "weapon" else None
    if not skel and item.group != "weapon" and item.sex in naraka_scene.Assembler.SKELETONS:
        skel = naraka_scene.Assembler.SKELETONS[item.sex]      # human NPCs: the hero skeleton
    if skel and skel != item.path:
        asm = naraka_scene.Assembler(game, scene, skeleton=skel, keep_fx=args.keep_fx)
        asm.add_prefab(item.path, "outfit")
    else:
        asm = naraka_scene.Assembler(game, scene, skeleton="", keep_fx=args.keep_fx)
        asm.add_standalone(item.path)
    return scene, {"prefab": item.path, "group": item.group, "bundle": item.bundle, "skeleton": skel}


def export(game, catalog, item, args):
    out_dir = export_dir(item, args.out)
    blend = os.path.join(out_dir, item.name + ".blend")
    if os.path.isfile(blend) and not args.force:
        print("  skip (exists): %s" % blend)
        return "skipped"
    t0 = time.time()
    if item.group == "outfit":
        scene, meta = build_outfit(game, catalog, item, args)
    else:
        scene, meta = build_standalone(game, item, args)
    if not scene.parts:
        raise RuntimeError("no meshes in %s" % item.path)
    scene.write(meta)
    t1 = time.time()
    report = {}
    if not args.no_blend:
        report = run_blender(args.blender, out_dir, item.name, args.fbx, not args.no_preview)
    info = dict(meta, name=item.name, parts=len(scene.parts), nodes=len(scene.order),
                materials=len(scene.materials), textures=len([t for t in scene.textures.values() if t]),
                unresolved_bones=unresolved(scene), extract_s=round(t1 - t0, 1),
                blender_s=round(time.time() - t1, 1), blender=report, log=scene.log)
    with open(os.path.join(out_dir, "export.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print("  %d parts, %d bones, %d materials, unresolved %d, %.0fs + %.0fs -> %s" % (
        info["parts"], info["nodes"], info["materials"], info["unresolved_bones"],
        info["extract_s"], info["blender_s"], out_dir))
    return "ok"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outfit", action="append", default=[])
    ap.add_argument("--family")
    ap.add_argument("--all-outfits", action="store_true")
    ap.add_argument("--prefab", action="append", default=[])
    ap.add_argument("--group")
    ap.add_argument("--sex", choices=("f", "m"))
    ap.add_argument("--hair", help="hair prefab name, or 'none'")
    ap.add_argument("--no-hair", action="store_true")
    ap.add_argument("--no-face", action="store_true")
    ap.add_argument("--ui", action="store_true", help="allow *_ui copies in --family/--group")
    ap.add_argument("--keep-fx", action="store_true", help="keep fx_* effect meshes (trails, glows)")
    ap.add_argument("--fbx", action="store_true")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--no-blend", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-html", action="store_true", help="leave <out>\\_list\\index.html alone")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--game-data", default=naraka_env.STREAMING)
    ap.add_argument("--blender", default=BLENDER)
    args = ap.parse_args()

    game = naraka_env.Game(args.game_data)
    catalog = naraka_catalog.build(game.manifest)
    by_name = {i.name: i for i in catalog}
    by_path = {i.path: i for i in catalog}
    todo = []
    for name in args.outfit + args.prefab:
        item = by_path.get(name) or by_name.get(name)
        if item is None:
            raise SystemExit("unknown model: %s (see list_models.py)" % name)
        todo.append(item)
    ok_ui = lambda i: args.ui or not i.ui  # noqa: E731
    if args.family:
        todo += [i for i in catalog if i.family == args.family and i.group == "outfit" and ok_ui(i)]
    if args.all_outfits:
        todo += [i for i in catalog if i.group == "outfit" and ok_ui(i) and (not args.sex or i.sex == args.sex)]
    if args.group:
        todo += [i for i in catalog if i.group == args.group and ok_ui(i) and (not args.sex or i.sex == args.sex)]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        ap.print_help()
        return
    stats = {"ok": 0, "skipped": 0, "failed": 0}
    for n, item in enumerate(todo, 1):
        print("[%d/%d] %s (%s)" % (n, len(todo), item.name, item.group), flush=True)
        try:
            stats[export(game, catalog, item, args)] += 1
        except Exception as exc:
            stats["failed"] += 1
            print("  FAILED: %s" % exc)
            traceback.print_exc()
    if not args.no_html:
        write_html(os.path.join(args.out, "_list", "index.html"), [i for i in catalog if not i.ui], args.out)
    print("done: %(ok)d exported, %(skipped)d skipped, %(failed)d failed" % stats)


if __name__ == "__main__":
    main()
