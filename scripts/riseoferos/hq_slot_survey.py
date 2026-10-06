"""Which slots of the exported ROE models would get another game material under the current rules - read only.

hq_materials_blender.py picks each slot's game material (colour-texture match, then source_material(): the FBX's stored
material where the match went wrong, glass, cross-character textures through the game's Manifest.ab).  After a rule or
data change this lists what a re-export would change, without exporting anything:

    python hq_slot_survey.py                       # every main model, suit and nude base on D: (h / i suits + nude left out)
    python hq_slot_survey.py b04 pc_a01_marry      # just these (main key / stem, suit pc_<id>_<suit>, nude pc_<id>_nk_bs)
    python hq_slot_survey.py --family e,f --json out.json

Runs one Blender in the background that opens each .blend (nothing is saved), then prints per model the slots whose
material would change (CHG: another game material, NEW: a slot the add-on kept gets one) with the role it gets
(pbr / skin / hair / glass / flat, "XPS alpha" = alpha render group) and, separately, how many head slots still miss the
10-02 lashes / brows / iris conversion.  Changes that are only a name (<material>@<suit>, __UVMap copies) and picks
whose role is None (the slot keeps the add-on material anyway) are left out.  The material caches must be current
(run hq_material_data.py <id> --out D:\\roe_exports\\_hq_materials first after a data-script change; the exports do it
themselves).
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = r"D:\roe_exports\_hq_materials"


def worker(out_path, blends):
    """Inside Blender: one row per used slot of every blend -> out_path (resumes a partial file)."""
    import bpy
    sys.path.insert(0, HERE)
    import hq_materials_blender as hq
    result = json.load(open(out_path, encoding="utf-8")) if os.path.isfile(out_path) else {}
    datas = {}
    for path in blends:
        if path in result:
            continue
        try:
            bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
        except Exception as exc:
            result[path] = {"error": str(exc)}
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        cid = re.match(r"pc_([a-z]\d+)", stem).group(1)
        if cid not in datas:
            p = os.path.join(CACHE, cid + ".json")
            datas[cid] = json.load(open(p, encoding="utf-8"))["materials"] if os.path.isfile(p) else {}
        mats = datas[cid]
        suit = re.match(r"pc_%s_(.+)$" % cid, stem.lower())
        suit = suit.group(1) if suit else None
        rows = []
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            sources = hq.slot_sources(obj)
            counts = {}
            for poly in obj.data.polygons:
                counts[poly.material_index] = counts.get(poly.material_index, 0) + 1
            for index, slot in enumerate(obj.material_slots):
                mat = slot.material
                if mat is None or not counts.get(index):
                    continue
                cur = re.sub(r"\.\d{3}$", "", mat.name)
                source = sources.get(index, "")
                albedo = hq.slot_albedo(mat)
                picked = hq.pick_material(mats, albedo, source, cur, suit)
                new = hq.source_material(mats, picked, source, cur)
                row = {"object": obj.name, "slot": index, "faces": counts[index], "current": cur, "source": source,
                       "albedo": albedo, "picked": picked, "new": new}
                if cur in hq.STROKE_SLOTS + hq.EYE_SLOTS:
                    kind = "eye" if cur in hq.EYE_SLOTS else "stroke"
                    game = hq.pick_eye(mats, albedo, source, suit, cid) if kind == "eye" else picked
                    row["head"] = {"kind": kind, "game": game, "done": bool(mat.get("roe_hq_stroke") or mat.get("roe_hq_iris")),
                                   "ok": bool(game and (kind == "eye" or "_BaseMap" in mats.get(game, {}).get("textures", {})))}
                if new and new in mats:
                    row["role"] = hq.role_of(mats[new]) or hq.flat_kind(mats[new])
                    row["xps_alpha"] = hq.xps_alpha(mats[new])
                rows.append(row)
        result[path] = rows
        print("SURVEY %s %d" % (stem, len(rows)), flush=True)
        json.dump(result, open(out_path, "w", encoding="utf-8"), indent=0, ensure_ascii=False)


def summarize(result):
    """{stem: [change rows]}, {stem: [head slots still to convert]} - name-only changes and role-None picks left out."""
    caches, changes, heads = {}, {}, {}

    def mats(cid):
        if cid not in caches:
            p = os.path.join(CACHE, cid + ".json")
            caches[cid] = json.load(open(p, encoding="utf-8"))["materials"] if os.path.isfile(p) else {}
        return caches[cid]

    def look(m, name):
        d = m.get(name, {})
        return (d.get("textures", {}).get("_BaseMap", {}).get("texture", "").lower(), d.get("colors", {}).get("_BaseColor"))

    for path, rows in sorted(result.items()):
        stem = os.path.basename(path)[:-6]
        if isinstance(rows, dict):
            changes.setdefault(stem, []).append({"error": rows.get("error")})
            continue
        m = mats(re.match(r"pc_([a-z]\d+)", stem).group(1))
        for r in rows:
            if r.get("head"):
                if r["head"]["ok"] and not r["head"]["done"]:
                    heads.setdefault(stem, []).append("%s %s[%d]" % (r["head"]["kind"], r["object"], r["slot"]))
                continue
            new, cur = r["new"], r["current"]
            if not new or not r.get("role"):
                continue
            if cur.startswith("HQ_"):
                old = re.sub(r"__UVMap$", "", cur[3:])
                if old == new or old.split("@")[0] == new.split("@")[0] or look(m, old) == look(m, new):
                    continue
                kind = "CHG"
            else:
                old, kind = cur, "NEW"
            changes.setdefault(stem, []).append(dict(r, kind=kind, old=old))
    return changes, heads


def main():
    if "--worker" in sys.argv:              # inside Blender
        argv = sys.argv[sys.argv.index("--worker") + 1:]
        blends = [l.strip() for l in open(argv[1], encoding="utf-8") if l.strip()]
        worker(argv[0], blends)
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="main key / stem, pc_<id>_<suit>, pc_<id>_nk_bs (default: all)")
    ap.add_argument("--family", default="", help="only these family letters, e.g. e,f")
    ap.add_argument("--with-hi", action="store_true", help="also the h / i suits and nude bases (left out by default)")
    ap.add_argument("--json", help="write the raw rows + the summary here")
    ap.add_argument("--exports", default=r"D:\roe_exports")
    ap.add_argument("--blender", default=r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
    args = ap.parse_args()
    sys.path.insert(0, HERE)
    import export_hq
    cat = export_hq.catalogue(args.exports)
    families = {x.strip().lower() for x in args.family.split(",") if x.strip()}
    blends = []
    for stem, (kind, info) in sorted(cat.items()):
        if args.names and not any(export_hq.resolve(n, cat) == stem for n in args.names):
            continue
        fam = info["cid"][0]
        if families and fam not in families:
            continue
        if kind in ("suit", "nude") and fam in "hi" and not args.with_hi and not args.names:
            continue
        if os.path.isfile(info["blend"]):
            blends.append(info["blend"])
    if not blends:
        sys.exit("no .blend matched")
    work = os.path.join(args.exports, "_hq_runs", "_slot_survey")
    os.makedirs(work, exist_ok=True)
    rows_path, list_path = os.path.join(work, "rows.json"), os.path.join(work, "blends.txt")
    if os.path.isfile(rows_path):
        os.remove(rows_path)
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(blends))
    print("surveying %d .blend files (read only) ..." % len(blends), flush=True)
    run = subprocess.run([args.blender, "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--",
                          "--worker", rows_path, list_path], capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if not os.path.isfile(rows_path):
        sys.exit("survey failed:\n" + (run.stderr or run.stdout)[-2000:])
    result = json.load(open(rows_path, encoding="utf-8"))
    changes, heads = summarize(result)
    print("\n%d of %d files would change material:" % (len(changes), len(result)))
    for stem, rows in changes.items():
        for r in rows:
            if "error" in r:
                print("  %-24s ERROR %s" % (stem, r["error"]))
                continue
            print("  %-24s %s %-26s [%d] %6d faces  %s -> %s (%s%s)" % (
                stem, r["kind"], r["object"], r["slot"], r["faces"], r["old"], r["new"], r["role"],
                ", XPS alpha" if r.get("xps_alpha") else ""))
    print("\nhead slots still without the 10-02 lashes / brows / iris look: %d in %d files"
          % (sum(len(v) for v in heads.values()), len(heads)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": result, "changes": changes, "heads": heads}, fh, ensure_ascii=False, indent=1)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
