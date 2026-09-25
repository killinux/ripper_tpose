# -*- coding: utf-8 -*-
"""PMX (+ MMD preview renders) for every exported FF7 mod model, and XPS / PMX paths into
the gallery entries.

  python ff7_mod_pmx_batch.py remake  [--only mod1707] [--skirt-to-legs 817,1707]
  python ff7_mod_pmx_batch.py rebirth

For each card in <root>/gallery_mods.json whose label starts with "mod<id>_": runs
export_ff7_pmx_blender.py (-> <root>/pmx/<label>/<label>.pmx) and, when the PMX is new,
stellarblade/preview_pmx_blender.py (preview.png / _dance / _gaze next to it).  Then records
"pmx", "pmx_report" and "xps" (from <root>/xps/<label>/<label>.xps when present) in the card.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BLENDER = "D:/Program Files/blender-3.6.15-windows-x64/blender.exe"
ROOTS = {"remake": "D:/ff7remake_exports/mods", "rebirth": "D:/ff7rebirth_exports/mods"}
GAME_NAMES = {"remake": "FINAL FANTASY VII REMAKE INTERGRADE", "rebirth": "FINAL FANTASY VII REBIRTH"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", choices=sorted(ROOTS))
    ap.add_argument("--only", default="", help="label substring")
    ap.add_argument("--skirt-to-legs", default="817,1707", help="mod ids whose skirt-bone skin follows the thighs")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--exclude", default="_PC[0-9]{4}_[0-9]{2}_Hair_and_Makeup_Add_on$",
                    help="labels to leave out (default: 1707's add-on shown on the plain base outfits)")
    a = ap.parse_args()
    root = ROOTS[a.game]
    manifest_path = os.path.join(root, "gallery_mods.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    skirt_ids = {int(x) for x in a.skirt_to_legs.split(",") if x.strip()}
    for e in manifest["results"]:
        m = re.match("^mod([0-9]+)_", e["label"])
        if not m or (a.only and a.only not in e["label"]) or (a.exclude and re.search(a.exclude, e["label"])):
            continue
        mod = e.get("mod") or {}
        label = e["label"]
        pmx = os.path.join(root, "pmx", label, label + ".pmx")
        xps = os.path.join(root, "xps", label, label + ".xps")
        if os.path.isfile(xps):
            e["xps"] = xps
        if a.force or not os.path.isfile(pmx):
            t0 = time.time()
            comment = ("Mod: %s by %s (%s)" + chr(10) + "File: %s" + chr(10)
                       + "Converted from %s by ripper_tpose (scripts/final/export_ff7_pmx_blender.py). "
                       "Personal use only; credit the mod author.") % (
                mod.get("name", ""), mod.get("author", "?"), mod.get("url", ""), mod.get("file", ""),
                GAME_NAMES[a.game])
            cmd = [BLENDER, "-b", e["blend"], "--python", os.path.join(HERE, "export_ff7_pmx_blender.py"), "--",
                   "--out", os.path.join(root, "pmx"), "--name", label,
                   "--model-name", ("%s %s" % (e.get("char") or "", mod.get("file") or label)).strip()[:60],
                   "--comment", comment]
            if int(m.group(1)) in skirt_ids:
                cmd.append("--skirt-to-legs")
            log = run(cmd)
            line = next((l for l in reversed(log.splitlines()) if l.startswith("FF7_PMX_REPORT=")), "")
            if not line:
                print("FAIL", label, log[-600:], flush=True)
                continue
            rep = json.loads(line[len("FF7_PMX_REPORT="):])
            prev = run([BLENDER, "-b", "--python", os.path.join(REPO, "scripts", "stellarblade", "preview_pmx_blender.py"),
                        "--", "--pmx", pmx])
            pline = next((l for l in reversed(prev.splitlines()) if l.startswith("PMX_PREVIEW=")), "")
            prep = json.loads(pline[len("PMX_PREVIEW="):]) if pline else {}
            e["pmx_report"] = {k: rep.get(k) for k in ("height_m", "bones", "rigid_bodies", "joints", "distortion",
                                                      "stray_recipients", "grant_order_violations", "both_eyes_bone",
                                                      "skirt_to_legs", "bust_physics")}
            e["pmx_report"]["drop_test"] = prep.get("rest_drop_test")
            print("OK  ", label, "%.0f s" % (time.time() - t0), "torn", (rep.get("distortion") or {}).get("torn"),
                  "rigid", rep.get("rigid_bodies"), "drift", (prep.get("rest_drop_test") or {}).get("max_drift_cm"),
                  flush=True)
        if os.path.isfile(pmx):
            e["pmx"] = pmx
            e["pmx_preview"] = os.path.join(root, "pmx", label, "preview_dance.png")
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, manifest_path)


if __name__ == "__main__":
    sys.exit(main())
