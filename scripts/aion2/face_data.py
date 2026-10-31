"""AION2 face data for the PMX expressions: the game's FACS pose assets as CUE4Parse JSON.

    python face_data.py [--out E:\\aion2_exports\\_meta\\face] [--usmap E:\\tools\\aion2\\vdf53_patched.usmap]
                        [--asset GF_Head_006_FACS_PA ...] [--list]

AION2's packages are unversioned (no property tags), so CUE4Parse needs type mappings, and none exist for AION2:
they are dumped from the running game, which NCGuard protects - not done.  The engine classes a PoseAsset is made of
(PoseAsset, PoseDataContainer, PoseData, Transform ...) are stock UE 5.3, so the UE 5.3 mappings built for
Vindictus (TFD's 5.2 mappings + scripts/vindictus/levels/patch_usmap.py) read them: the 52 ARKit poses come out with
their bone tracks.  Copy that file to the --usmap path once.  The AES key is read like aion2_pak.py reads it (key
file or AION2_AES_KEY) and never printed.  Writes <out>/<asset>.json (the CUE4Parse CLI's own folder tree is
flattened) and prints the pose names.

Assets (default: all four):
  GF_Head_006_FACS_PA          female player head 006 - the default of export_pmx_blender.py
  GF_Head_023_FACS_PA          female player head 023
  GF_CineFacial_PoseAsset_01   female cutscene face
  GM_Head_004_FACS_Pose        male player head 004
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aion2_pak as pak  # noqa: E402

CLI = r"E:\tools\cue4parse_cli\cue4parse.exe"
DEFAULT_OUT = r"E:\aion2_exports\_meta\face"
DEFAULT_USMAP = r"E:\tools\aion2\vdf53_patched.usmap"
ASSETS = ("GF_Head_006_FACS_PA", "GF_Head_023_FACS_PA", "GF_CineFacial_PoseAsset_01", "GM_Head_004_FACS_Pose")


def run_cli(args, key):
    hexkey = "0x" + key.hex().upper()
    r = subprocess.run([CLI] + args[:2] + ["-k", hexkey] + args[2:], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    text = (r.stdout or "") + (r.stderr or "")
    for k in (hexkey, hexkey[2:], hexkey.lower(), hexkey[2:].lower()):
        text = text.replace(k, "<key>")
    return r.returncode, text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--usmap", default=DEFAULT_USMAP)
    ap.add_argument("--game-root", default=pak.DEFAULT_GAME_ROOT)
    ap.add_argument("--key-file", default=pak.DEFAULT_KEY_FILE)
    ap.add_argument("--asset", action="append", default=[], help="pose asset name (repeatable); default: all four")
    ap.add_argument("--list", action="store_true", help="only list the packages each name matches")
    args = ap.parse_args()
    if not os.path.isfile(CLI):
        raise SystemExit("CUE4Parse CLI not found: %s" % CLI)
    if not os.path.isfile(args.usmap):
        raise SystemExit("UE 5.3 type mappings not found: %s (see the docstring)" % args.usmap)
    key = pak.read_key(None, args.key_file)
    assets = args.asset or list(ASSETS)
    base = ["-i", pak.paks_dir(args.game_root), "-g", "GAME_UE5_3", "-m", args.usmap, "-y"]
    patterns = []
    for a in assets:
        patterns += ["-p", "*/%s.uasset" % a]
    if args.list:
        rc, text = run_cli(base + patterns + ["-l"], key)
        print(text)
        return
    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="aion2_face_")
    try:
        rc, text = run_cli(base + ["-o", tmp, "-f", "json"] + patterns, key)
        if rc != 0:
            raise SystemExit("CUE4Parse failed (%d):\n%s" % (rc, text[-3000:]))
        found = {os.path.splitext(os.path.basename(p))[0]: p
                 for p in glob.glob(os.path.join(tmp, "**", "*.json"), recursive=True)}
        for a in assets:
            src = found.get(a)
            if src is None:
                print("%-28s not found" % a)
                continue
            dst = os.path.join(args.out, a + ".json")
            shutil.copyfile(src, dst)
            doc = json.load(open(dst, encoding="utf-8-sig"))
            props = next((o for o in doc if o.get("Type") == "PoseAsset"), {}).get("Properties", {})
            names = [p["DisplayName"] for p in props.get("PoseContainer", {}).get("PoseNames", [])]
            print("%-28s %2d poses -> %s" % (a, len(names), dst))
            print("    " + ", ".join(names))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
