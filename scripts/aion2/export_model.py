"""Export one AION2 model to a textured .blend: UE Viewer -> bake_materials.py -> Blender build_blend.py.

    python export_model.py GF_Angel_01                         # a female costume, default head + hair
    python export_model.py GF_Angel_01 --hair GF_Hair_010      # another hairstyle (output folder gets a suffix)
    python export_model.py GF_0001_T04 --head GF_Head_006
    python export_model.py NPC_F_Daeva_04                      # any model id from list_models.py
    python export_model.py GF_Angel_01 --force                 # re-export the PSKs / textures from the game
    python export_model.py GF_Nude --hair GF_Hair_308          # the nude body (nude_survey.py --write first; nude_body.py)

Steps:
  1. list_models.resolve(): the model's parts (sets get the base body where they have no Body / Pants
     part, plus a head and a hairstyle);
  2. UE Viewer (spiritovod's UE5 build, -game=ue5.3) exports each part package - PSK + the materials'
     .mat / .props.txt + PNG textures - into <export-root>\\umodel_exports (skipped when the PSK exists);
  3. the PSKs' material slot names -> bake_materials.bake() -> <out>\\textures + materials.json;
  4. Blender 3.6 build_blend.py -> <out>\\<id>.blend + preview.png / preview_back.png / preview_face.png.

<out> = <export-root>\\blend\\<id>[__<head>][__<hair>][__<variant>].  build.log keeps the AION2_REPORT line.
The AES key comes from --key-file / AION2_AES_KEY (see aion2_pak.py); it is passed to UE Viewer as a file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aion2_pak as pak  # noqa: E402
import bake_materials  # noqa: E402
import list_models as lm  # noqa: E402

DEFAULT_UMODEL = r"E:\tools\umodel_specific\materials\umodel_materials_ue5.exe"
DEFAULT_BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"


def psk_materials(path: str) -> list:
    """Material names of a PSK / PSKX (MATT0000 chunk: 64-byte name + 6 int32 per entry)."""
    names = []
    with open(path, "rb") as fh:
        while True:
            head = fh.read(32)
            if len(head) < 32:
                break
            cid = head[:20].split(b"\0")[0].decode("ascii", "replace")
            _flags, size, count = struct.unpack_from("<iii", head, 20)
            data = fh.read(size * count)
            if cid.startswith("MATT"):
                for i in range(count):
                    names.append(data[i * size:i * size + 64].split(b"\0")[0].decode("utf-8", "replace"))
                break
    return names


def umodel_export(umodel: str, game_root: str, key_file: str, out_root: str, package: str, log) -> bool:
    cmd = [umodel, "-game=ue5.3", "-path=" + pak.paks_dir(game_root), "-aes=@" + key_file, "-export", "-png",
           "-out=" + out_root, package]
    with tempfile.TemporaryDirectory() as cwd:             # UE Viewer drops UmodelSaved\ etc. into its cwd
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")
    lines = (r.stdout + r.stderr).splitlines()
    exported = [ln for ln in lines if ln.startswith("Exported")]
    errors = [ln for ln in lines if "rror" in ln or "WARNING: unable" in ln]
    log("  umodel %s: %s%s" % (package, exported[-1] if exported else "nothing exported",
                              (" | " + errors[0]) if errors else ""))
    return bool(exported)


GENERIC_SLOT_RE = re.compile(r"^material_\d+$")
HAIR_ID_RE = re.compile(r"^(GF|GM)_Hair_\d+$")
NUDE_RE = re.compile(r"^(GF|GM)_Nude$")


def nude_parts(models: dict, mid: str, export_root: str, head=None, hair=None) -> dict:
    """<G>_Nude: the skin of the costume parts nude_survey.py picked (in coverage order) + a head and a hairstyle.
    build_blend.py keeps only their <G>_BaseBody skin slot, drops what an earlier part already covers, welds
    them and closes the openings - AION2 has no nude body of its own (see nude_survey.py)."""
    g = mid[:2]
    recipe_path = os.path.join(export_root, "_meta", "aion2_nude_%s.json" % g)
    if not os.path.isfile(recipe_path):
        raise SystemExit("no nude recipe yet: run  python nude_survey.py --gender %s --write  (after the costume "
                         "Body / Pants parts are exported, see README)" % g)
    recipe = json.load(open(recipe_path, encoding="utf-8"))
    res = {"id": mid, "kind": "nude", "gender": g, "folder": "", "parts": [],
           "notes": ["skin from %s, openings %s cm capped" % (
               " + ".join(p["stem"] for p in recipe["parts"]), ", ".join("%.0f" % o for o in recipe.get("openings_cm", [])))]}
    for i, rp in enumerate(recipe["parts"]):
        path = lm.CONTENT + rp["psk_rel"][:-len(".psk")] + ".uasset"
        res["parts"].append({"name": "Skin%d" % i, "path": path, "package": lm.pkg(path),
                             "skin_only": recipe["skin_material"], "role": rp.get("role", "upper"),
                             "waist_z": recipe.get("waist_z", 120.0), "torso_x": recipe.get("torso_x", 22.0)})
    for name, wanted in (("Head", head or lm.DEFAULT_HEAD[g]), ("Hair", hair or lm.DEFAULT_HAIR[g])):
        if wanted not in models:
            raise KeyError("%s %s" % (name.lower(), wanted))
        p = models[wanted]["parts"][0]
        res["parts"].append({"name": name, "path": p, "package": lm.pkg(p)})
    res["head"], res["hair"] = head or lm.DEFAULT_HEAD[g], hair or lm.DEFAULT_HAIR[g]
    # the shop mannequin (a closed nude body, other topology) shapes the caps over what no costume shows; the
    # other costumes' skin near the openings (nude_survey.py) shapes the rest
    res["guide"] = [lm.CONTENT + "Character/ETC/Mannequin/%s/%s_Mannequin_%s.uasset" % (g, g, s) for s in ("Body", "Pants")]
    res["skin_guide"] = os.path.join(export_root, "_meta", recipe["guide"]) if recipe.get("guide") else None
    res["skin_material"] = recipe["skin_material"]
    return res


def helmet_rules(game, classes: dict, res: dict) -> dict:
    """What the set's helmet does to the hair, read from its AionEquipPartsSettingData (EPS_<set>_Helmet).

    The EPS properties are unversioned (no usmap), but its name map is enough: a full helmet names the
    hairstyle worn under it (GF_0001_T04 and the swimsuit cap -> GF_Hair_009, a tight scalp cut) and/or a
    <part>_Clip static mesh - a single quad: the hair on the head-top side of that plane is cut away
    (GF_0010_T05).  Halos, hair bands, Santa hats name neither and leave the hair alone."""
    helmet = next((p for p in res["parts"] if p["name"] == "Helmet"), None)
    if helmet is None:
        return {}
    folder = os.path.dirname(helmet["path"])
    eps = [p for p, c in classes.items() if c == "AionEquipPartsSettingData" and os.path.dirname(p) == folder
           and lm.stem(p).lower().endswith("_helmet")]
    if not eps:
        return {}
    names = game.header(eps[0])["names"]
    out = {"eps": eps[0]}
    hair = [n for n in names if HAIR_ID_RE.match(n)]
    if hair:
        out["hair"] = hair[0]
    clip = [n for n in names if n.startswith("/Game/") and n.endswith("_Clip")]
    if clip:
        out["clip"] = "AION2/Content/" + clip[0][len("/Game/"):] + ".uasset"
    return out


def material_imports(game, classes: dict, path: str) -> list:
    """The material instances a mesh package imports (its zen header's imported packages), as index paths in import
    order: the materials of its slots, also of the ones UE Viewer leaves as 'material_N'."""
    try:
        imported = game.header(path).get("imported_packages", [])
    except KeyError:
        return []
    if not _MI_FOLDERS:
        for p, c in classes.items():
            if c == "MaterialInstanceConstant":
                _MI_FOLDERS.setdefault(os.path.dirname(p), []).append(p)
    out = []
    for imp in imported:
        if not imp.startswith("/Game/"):
            continue
        ip = lm.CONTENT + imp[len("/Game/"):] + ".uasset"
        if classes.get(ip) in ("MaterialInstanceConstant", "Material"):
            out.append(ip)
            continue
        # a package stored under another file name than the one it is imported by: NPC_Leda_01_Hair imports
        # GF_Hair_402/Materials/MI_GF_Hair, the container has GF_Hair_402/Materials/MI_GF_Hair_402.uasset
        here = _MI_FOLDERS.get(os.path.dirname(ip), [])
        stem = lm.stem(ip).lower()
        cand = [p for p in here if lm.stem(p).lower().startswith(stem)] or (here if len(here) == 1 else [])
        if len(cand) == 1:
            out.append(cand[0])
    return out


_MI_FOLDERS = {}
_MI_STEMS = Counter()


def material_name(classes: dict, mi: str) -> str:
    """Blender / materials.json name of a material instance: its stem, plus its folder when the stem is not unique
    (every NPC-used hairstyle has its own MI_GF_Hair: GF_Hair_402/Materials/MI_GF_Hair -> MI_GF_Hair__GF_Hair_402)."""
    if not _MI_STEMS:
        _MI_STEMS.update(lm.stem(p).lower() for p, c in classes.items() if c == "MaterialInstanceConstant")
    name = lm.stem(mi)
    if _MI_STEMS[name.lower()] > 1:
        folder = os.path.dirname(mi)
        if os.path.basename(folder) == "Materials":
            folder = os.path.dirname(folder)
        name += "__" + os.path.basename(folder)
    return name


def map_generic_slots(part: dict, classes: dict, umodel_root: str, export, log, game=None) -> tuple:
    """(slot -> material name, material name -> rel path) for one part.

    UE Viewer names a slot 'material_N' when it cannot resolve the mesh's material reference (many hairstyles,
    e.g. GF_Hair_303, whose package was saved under another name).  The mesh's own imports name the package: an NPC
    wearing a player hairstyle imports e.g. GF_Hair_402/Materials/MI_GF_Hair (NPC_Leda_01_Hair; the folder guess below
    gave it the dress material).  Without an import the material instance is looked for next to the mesh:
    <folder>/Materials/MI_<mesh>.uasset (or the only non-test MI there).  The rel paths let bake_materials pick the
    right one of several same-named instances."""
    slots = psk_materials(part["psk"])
    generic = sorted(n for n in slots if GENERIC_SLOT_RE.match(n))
    imports = material_imports(game, classes, part["path"]) if game is not None else []
    rels = {}
    for n in slots:
        hit = [ip for ip in imports if lm.stem(ip) == n]
        if hit:
            rels[n] = hit[0][len(lm.CONTENT):-len(".uasset")]
    if not generic:
        return {}, rels
    named = set(slots) - set(generic)
    folder = os.path.dirname(part["path"])
    mis = sorted(p for p, c in classes.items() if c == "MaterialInstanceConstant"
                 and (os.path.dirname(p) == folder or os.path.dirname(p) == folder + "/Materials"))
    want = "mi_" + lm.stem(part["path"]).lower()
    ranked = [p for p in imports if lm.stem(p) not in named]
    source = "the mesh's imports" if ranked else "the mesh's folder"
    for p in [p for p in mis if lm.stem(p).lower() == want] + \
             [p for p in mis if lm.stem(p).lower() != want and "test" not in lm.stem(p).lower()]:
        if p not in ranked:
            ranked.append(p)
    mapping = {}
    for slot, mi in zip(generic, ranked):
        name = material_name(classes, mi)
        rel = mi[len(lm.CONTENT):-len(".uasset")]
        if not os.path.isfile(os.path.join(umodel_root, rel.replace("/", os.sep) + ".mat")):
            export(lm.pkg(mi))
        mapping[slot] = name
        rels[name] = rel
    if len(generic) > len(ranked) or len(generic) > 1:
        log("  note: %s has %d unresolved slots, %d candidate material instances - mapped %s" % (
            part["name"], len(generic), len(ranked), mapping))
    else:
        log("  %s: slot %s -> %s (from %s)" % (part["name"], generic[0], mapping.get(generic[0]), source))
    return mapping, rels


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--head", help="head for a wearable set (default <G>_Head_001)")
    ap.add_argument("--hair", help="hairstyle for a wearable set (default <G>_Hair_001)")
    ap.add_argument("--variant", default="A", help="letter of the alternative parts to use (Body_A / Body_B ...)")
    ap.add_argument("--game-root", default=pak.DEFAULT_GAME_ROOT)
    ap.add_argument("--key-file", default=pak.DEFAULT_KEY_FILE)
    ap.add_argument("--oodle", default=pak.DEFAULT_OODLE)
    ap.add_argument("--export-root", default=lm.DEFAULT_EXPORT_ROOT)
    ap.add_argument("--umodel", default=DEFAULT_UMODEL)
    ap.add_argument("--blender", default=DEFAULT_BLENDER)
    ap.add_argument("--keep-hair", action="store_true",
                    help="ignore what the helmet's settings say about the hair (swap / cut plane)")
    ap.add_argument("--force", action="store_true", help="re-export PSKs and textures even when they exist")
    ap.add_argument("--no-blend", action="store_true", help="stop after the UE Viewer export + bake")
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    key = pak.read_key(key_file=args.key_file)
    tmp_key = None
    key_file = args.key_file
    if not (key_file and os.path.isfile(key_file)):          # key from the environment: hand UE Viewer a temp file
        fd, tmp_key = tempfile.mkstemp(suffix=".txt")
        os.write(fd, ("0x" + key.hex().upper()).encode())
        os.close(fd)
        key_file = tmp_key
    try:
        game = pak.Game(args.game_root, key, args.oodle)
        classes = lm.load_classes(game, os.path.join(args.export_root, "_meta", "aion2_classes.json"))
        if classes is None:
            raise SystemExit("no class cache yet: run  python list_models.py --scan  first")
        models = lm.build_models(classes)
        try:
            if NUDE_RE.match(args.model):
                res = nude_parts(models, args.model, args.export_root, args.head, args.hair)
            else:
                res = lm.resolve(models, args.model, args.head, args.hair, args.variant)
        except KeyError as e:
            raise SystemExit("unknown model or part %s - see python list_models.py --kind ..." % e)
        rules = {} if args.keep_hair else helmet_rules(game, classes, res)
        if rules.get("hair") and rules["hair"] in models:
            hp = models[rules["hair"]]["parts"][0]
            for p in res["parts"]:
                if p["name"] == "Hair" and p["path"] != hp:
                    res["notes"].append("helmet: hair %s -> %s (named in %s)" % (
                        lm.stem(p["path"]), rules["hair"], lm.stem(rules["eps"])))
                    p.update({"path": hp, "package": lm.pkg(hp)})
        if rules.get("clip") and rules["clip"] in game.index:
            res["notes"].append("helmet: hair cut by the plane %s" % lm.stem(rules["clip"]))

        suffix = ""
        g = res.get("gender")
        if res.get("head") and res["head"] != lm.DEFAULT_HEAD.get(g):
            suffix += "__" + res["head"].replace(g + "_", "")
        if res.get("hair") and res["hair"] != lm.DEFAULT_HAIR.get(g):
            suffix += "__" + res["hair"].replace(g + "_", "")
        if args.variant != "A":
            suffix += "__" + args.variant
        out_id = args.model + suffix
        out_dir = os.path.join(args.export_root, "blend", out_id)
        os.makedirs(out_dir, exist_ok=True)
        log_lines = []

        def log(msg):
            print(msg, flush=True)
            log_lines.append(msg)

        log("%s (%s %s): %d parts" % (out_id, res["kind"], g or "-", len(res["parts"])))
        for n in res["notes"]:
            log("  note: " + n)
        umodel_root = os.path.join(args.export_root, "umodel_exports")
        t0 = time.time()
        parts = []
        material_rels = {}                    # material name -> rel path (same-named instances, see map_generic_slots)
        for part in res["parts"]:
            rel = part["path"][len(lm.CONTENT):-len(".uasset")]
            psk = None
            for ext in (".psk", ".pskx"):
                cand = os.path.join(umodel_root, rel.replace("/", os.sep) + ext)
                if os.path.isfile(cand):
                    psk = cand
            if psk is None or args.force:
                umodel_export(args.umodel, args.game_root, key_file, umodel_root, part["package"], log)
                for ext in (".psk", ".pskx"):
                    cand = os.path.join(umodel_root, rel.replace("/", os.sep) + ext)
                    if os.path.isfile(cand):
                        psk = cand
            if psk is None:
                log("  MISSING PSK for %s (%s)" % (part["name"], part["package"]))
                continue
            entry = {"name": part["name"], "psk": psk, "package": part["package"], "path": part["path"]}
            if part.get("skin_only"):
                for k in ("skin_only", "role", "waist_z", "torso_x"):
                    entry[k] = part[k]
            entry["material_map"], rels = map_generic_slots(
                entry, classes, umodel_root,
                lambda p: umodel_export(args.umodel, args.game_root, key_file, umodel_root, p, log), log, game)
            material_rels.update(rels)
            parts.append(entry)
        guide = []
        for gp in res.get("guide", []):
            if gp not in game.index:
                continue
            rel = gp[len(lm.CONTENT):-len(".uasset")]
            cand = os.path.join(umodel_root, rel.replace("/", os.sep) + ".psk")
            if not os.path.isfile(cand) or args.force:
                umodel_export(args.umodel, args.game_root, key_file, umodel_root, lm.pkg(gp), log)
            if os.path.isfile(cand):
                guide.append(cand)
        hair_clip = None
        if rules.get("clip") and rules["clip"] in game.index:
            rel = rules["clip"][len(lm.CONTENT):-len(".uasset")]
            cand = os.path.join(umodel_root, rel.replace("/", os.sep) + ".pskx")
            if not os.path.isfile(cand) or args.force:
                umodel_export(args.umodel, args.game_root, key_file, umodel_root, lm.pkg(rules["clip"]), log)
            if os.path.isfile(cand):
                hair_clip = cand
        log("UE Viewer: %d/%d parts in %.0f s" % (len(parts), len(res["parts"]), time.time() - t0))

        names = []
        for part in parts:
            for n in psk_materials(part["psk"]):
                n = part["material_map"].get(n, n)
                if part.get("skin_only") and n != part["skin_only"]:
                    continue                                   # the garment of a skin donor is dropped anyway
                if n not in names:
                    names.append(n)
        log("baking %d materials" % len(names))
        mats = bake_materials.bake(umodel_root, out_dir, names, material_rels)
        bad = {n: e["warnings"] for n, e in mats.items() if e["warnings"]}
        for n, w in bad.items():
            log("  material %s: %s" % (n, "; ".join(w)))

        spec = {"id": out_id, "model": args.model, "kind": res["kind"], "gender": g, "out_dir": out_dir,
                "parts": parts, "materials": os.path.join(out_dir, "materials.json"),
                "head": res.get("head"), "hair": res.get("hair"), "notes": res["notes"], "hair_clip": hair_clip,
                "nude_guide": guide, "nude_skin_guide": res.get("skin_guide"), "nude_skin_material": res.get("skin_material")}
        spec_path = os.path.join(out_dir, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=1, ensure_ascii=False)
        if args.no_blend:
            log("spec written: " + spec_path)
            return 0

        cmd = [args.blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"), "--",
               "--spec", spec_path] + (["--no-preview"] if args.no_preview else [])
        t1 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        report = None
        for line in (r.stdout or "").splitlines():
            if line.startswith("[aion2]"):
                log(line)
            if line.startswith("AION2_REPORT="):
                report = json.loads(line[len("AION2_REPORT="):])
        if report is None:
            log("Blender failed (rc %d):\n%s" % (r.returncode, "\n".join((r.stdout + r.stderr).splitlines()[-25:])))
        else:
            log("Blender: %.0f s, %d warnings" % (time.time() - t1, len(report["warnings"])))
            for w in report["warnings"]:
                log("  warning: " + w)
            log_lines.append("AION2_REPORT=" + json.dumps(report, ensure_ascii=False))
        with open(os.path.join(out_dir, "build.log"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(log_lines) + "\n")
        if report:
            print("done: %s" % os.path.join(out_dir, out_id + ".blend"))
        return 0 if report else 1
    finally:
        if tmp_key:
            os.remove(tmp_key)


if __name__ == "__main__":
    sys.exit(main())
