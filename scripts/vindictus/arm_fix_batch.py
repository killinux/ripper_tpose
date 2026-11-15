# -*- coding: utf-8 -*-
r"""Fiona outfits with the arm fixes, as side files next to the archive's PMX: <id>_手臂修正_肩部辅助骨.pmx.

Per outfit, the chain the PCF_005 / Fiona side files were made with (README "手臂角度" / "手指" / "肩部" / "肩部辅助骨"):
  1. export_pmx.py from the archived XPS (arms raised to 40 deg, fingers straightened, the converter's armpit
     smoothing skipped - its defaults) - Blender;
  2. scripts/mmd_physics/cloth_collision_pmx.py --colliders-from _爆衣插件/Fiona_full/Fiona_full.pmx;
  3. pmx_elbow.py (the game's corrective elbow as helper bones);
  4. pmx_shoulder.py (the game's shoulder correctives as helper bones).
Then the side file is compared with the archive's <id>.pmx: same vertices / faces / materials / textures (byte-identical
files), the 10 helper bones added and nothing removed, no vertex outside the arms moved more than 0.5 cm, morph
offsets the same to 0.5 cm, the same number of rigid bodies.  Joint counts and body placement may differ: the hair /
cloth physics is rebuilt by today's mmd_cloth_physics and Convert_to_MMD5 (see the README's 2026-10-31 notes).

    python arm_fix_batch.py <id> ... [--work DIR] [--stand] [--copy] [--force] [--accept-rigids ID,ID]

  --work           working folder (default %TEMP%\vindictus_arm_fix); <work>\<id>\ keeps logs, reports, check.json
  --stand          also run checks/physics_standing.py on the side file (Blender, one at a time); a model whose
                   physics blows up (> 50 cm) is not copied
  --copy           put the side file into E:\game_export\Vindictus\Fiona\pmx\<id>\ when every check passed and the
                   name is free (the archive's own files are never touched); md5 checked after the copy
  --force          redo steps whose output exists
  --accept-rigids  ids whose rigid body count may differ (reviewed by hand: PCF_010 gets the 7 static body
                   colliders the other outfits already had)
Not for Fiona_BaseBody / Shiningwill_legacy (Biped bodies, no arm fixes).  Prints ARM_FIX_DONE {json} at the end.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import bust_physics  # noqa: E402  (load_pmx_module)

BLENDER = os.environ.get("BLENDER", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
ARCHIVE = r"E:\game_export\Vindictus\Fiona"
DNA = r"E:\game_export\Vindictus\_meta\face\SK_Fiona_Face01.dna"
COLLIDERS = r"E:\game_export\Vindictus\_爆衣插件\Fiona_full\Fiona_full.pmx"
COLLISION = os.path.join(REPO, "scripts", "mmd_physics", "cloth_collision_pmx.py")
STANDING = os.path.join(HERE, "checks", "physics_standing.py")
SUFFIX = "_手臂修正_肩部辅助骨.pmx"
HELPERS = 10                         # ひじ補1/2 and 腕補1-3, both sides
UNIT_CM = 8.0                        # 1 PMX unit = 8 cm (mmd_tools scale 12.5)
NAMES = {"Fiona": "Fiona"}           # MMD model names; others are "Fiona <id>"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(args, log):
    t = time.time()
    with open(log, "w", encoding="utf-8") as fh:
        r = subprocess.run(args, stdout=fh, stderr=subprocess.STDOUT, cwd=HERE)
    if r.returncode:
        script = next((a for a in args[1:] if a.endswith(".py")), args[0])
        raise RuntimeError("step failed (%d): %s - see %s" % (r.returncode, os.path.basename(script), log))
    return round(time.time() - t, 1)


def weights(v):
    w = v.weight
    bs, ws = list(w.bones), w.weights
    if hasattr(ws, "weight"):                                        # SDEF
        ws = [ws.weight, 1 - ws.weight]
    elif isinstance(ws, (int, float)):
        ws = [ws]
    ws = list(ws)
    if len(bs) == 1:
        ws = [1.0]
    elif len(bs) == 2 and len(ws) == 1:
        ws = [ws[0], 1 - ws[0]]
    return [(b, x) for b, x in zip(bs, ws) if b is not None and b >= 0 and x > 1e-4]


def compare(pmx, base_path, side_path):
    """The archive's <id>.pmx vs the side file: what changed, and whether anything outside the arms did."""
    A, B = pmx.load(base_path), pmx.load(side_path)
    an, bn = [b.name for b in A.bones], [b.name for b in B.bones]
    res = {"counts": {k: [len(getattr(A, k)), len(getattr(B, k))]
                      for k in ("vertices", "faces", "materials", "bones", "morphs", "rigids", "joints", "textures")}}
    res["bones_added"] = [n for n in bn if n not in set(an)]
    res["bones_removed"] = [n for n in an if n not in set(bn)]
    rel = lambda m, p: [os.path.relpath(t.path, os.path.dirname(os.path.abspath(p))).lower() for t in m.textures]
    res["texture_table_same"] = rel(A, base_path) == rel(B, side_path)
    res["faces_same"] = [tuple(f) for f in A.faces] == [tuple(f) for f in B.faces]
    if len(A.vertices) != len(B.vertices):
        return res
    move = np.linalg.norm(np.array([v.co for v in A.vertices]) - np.array([v.co for v in B.vertices]), axis=1) * UNIT_CM
    kids = {}
    for i, b in enumerate(B.bones):
        if b.parent is not None and b.parent >= 0:
            kids.setdefault(b.parent, []).append(i)
    arm, todo = set(), [bn.index(r) for r in ("左肩P", "右肩P", "左肩", "右肩") if r in bn]
    while todo:
        i = todo.pop()
        if i not in arm:
            arm.add(i)
            todo.extend(kids.get(i, []))
    arm |= {bn.index(n) for n in res["bones_added"]}
    in_arm = np.array([any(b in arm for b, _ in weights(v)) for v in B.vertices])
    res["moved_cm"] = {"arm_max": round(float(move[in_arm].max()), 2) if in_arm.any() else 0.0,
                       "outside_max": round(float(move[~in_arm].max()), 4) if (~in_arm).any() else 0.0}
    old = {m.name: m for m in A.morphs}
    diff = 0.0
    for m in B.morphs:
        o = old.get(m.name)
        if o is None or type(m).__name__ != "VertexMorph":
            continue
        d = {x.index: np.array(x.offset) for x in o.offsets}
        for x in m.offsets:
            if x.index in d:
                diff = max(diff, float(np.linalg.norm(np.array(x.offset) - d[x.index])) * UNIT_CM)
    res["morph_offsets_max_diff_cm"] = round(diff, 4)
    return res


def textures_same(side_dir, archive_dir):
    a = os.path.join(archive_dir, "textures")
    b = os.path.join(side_dir, "textures")
    names = sorted(os.listdir(b)) if os.path.isdir(b) else []
    differ = [n for n in names if not os.path.isfile(os.path.join(a, n)) or md5(os.path.join(a, n)) != md5(os.path.join(b, n))]
    return len(names), differ


def problems_of(res, tex_differ, accept_rigids):
    out = []
    c = res["counts"]
    if tex_differ:
        out.append("textures differ from the archive's: %s" % tex_differ[:5])
    if c["vertices"][0] != c["vertices"][1] or not res["faces_same"] or c["materials"][0] != c["materials"][1]:
        out.append("geometry / materials differ")
    if not res["texture_table_same"]:
        out.append("texture table differs")
    if res["bones_removed"] or len(res["bones_added"]) != HELPERS:
        out.append("bones +%d -%d (expected +%d)" % (len(res["bones_added"]), len(res["bones_removed"]), HELPERS))
    if res.get("moved_cm", {}).get("outside_max", 99) > 0.5:
        out.append("vertices outside the arms moved %.2f cm" % res["moved_cm"]["outside_max"])
    if res.get("morph_offsets_max_diff_cm", 99) > 0.5:
        out.append("morph offsets differ %.2f cm" % res["morph_offsets_max_diff_cm"])
    if c["rigids"][0] != c["rigids"][1] and not accept_rigids:
        out.append("rigid body count %s" % c["rigids"])
    return out


def one(mid, args, pmx):
    xps = os.path.join(ARCHIVE, "xps", mid, mid + ".xps")
    base = os.path.join(ARCHIVE, "pmx", mid, mid + ".pmx")
    for need in (xps, base):
        if not os.path.isfile(need):
            raise RuntimeError("missing %s" % need)
    d = os.path.join(args.work, mid)
    os.makedirs(d, exist_ok=True)
    exported, coll = os.path.join(d, mid + ".pmx"), os.path.join(d, mid + "_c.pmx")
    elbow, side = os.path.join(d, mid + "_手臂修正.pmx"), os.path.join(d, mid + SUFFIX)
    row = {"id": mid, "times": {}}
    if args.force or not os.path.isfile(exported):
        row["times"]["export"] = run([BLENDER, "-b", "--python", os.path.join(HERE, "export_pmx.py"), "--", "--xps", xps,
                                      "--dna", DNA, "--out", args.work, "--model-name", NAMES.get(mid, "Fiona " + mid)],
                                     os.path.join(d, "export.log"))
    if args.force or not os.path.isfile(coll):
        row["times"]["collision"] = run([sys.executable, COLLISION, exported, coll, "--colliders-from", COLLIDERS],
                                        os.path.join(d, "collision.log"))
    if args.force or not os.path.isfile(elbow):
        row["times"]["elbow"] = run([sys.executable, os.path.join(HERE, "pmx_elbow.py"), coll, elbow, "--xps", xps,
                                     "--report", os.path.join(d, "elbow.json")], os.path.join(d, "elbow.log"))
    if args.force or not os.path.isfile(side):
        row["times"]["shoulder"] = run([sys.executable, os.path.join(HERE, "pmx_shoulder.py"), elbow, side, "--xps", xps,
                                        "--report", os.path.join(d, "shoulder.json")], os.path.join(d, "shoulder.log"))
    res = compare(pmx, base, side)
    n_tex, tex_differ = textures_same(d, os.path.dirname(base))
    row["check"] = res
    row["textures"] = {"files": n_tex, "differ": tex_differ}
    row["problems"] = problems_of(res, tex_differ, mid in args.accept_rigids)
    if args.stand:
        log = os.path.join(d, "standing.log")
        run([BLENDER, "-b", "--factory-startup", "--python", STANDING, "--", side], log)
        text = open(log, encoding="utf-8", errors="replace").read()
        found = re.search(r"^blown up \(> 50 cm\): (.*?) PHYS DONE", text, re.M)
        row["standing"] = {k: (re.search(r"^%s.*$" % k, text, re.M) or [""])[0] for k in ("hair:", "bust:", "skirt:")}
        if not found or found.group(1).strip() != "[]":
            row["problems"].append("standing physics: %s" % (found.group(1) if found else "no result"))
    if args.copy and not row["problems"]:
        dest = os.path.join(ARCHIVE, "pmx", mid, mid + SUFFIX)
        if os.path.exists(dest):
            row["copied"] = "kept (same file)" if md5(dest) == md5(side) else "NOT COPIED: a different file has the name"
        else:
            shutil.copyfile(side, dest + ".part")
            os.replace(dest + ".part", dest)
            row["copied"] = "ok" if md5(dest) == md5(side) else "MD5 MISMATCH"
    with open(os.path.join(d, "check.json"), "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=1)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--work", default=os.path.join(tempfile.gettempdir(), "vindictus_arm_fix"))
    ap.add_argument("--stand", action="store_true")
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--accept-rigids", default="")
    args = ap.parse_args()
    args.accept_rigids = {x for x in args.accept_rigids.split(",") if x}
    os.makedirs(args.work, exist_ok=True)
    pmx = bust_physics.load_pmx_module()
    done = {}
    for mid in args.ids:
        t = time.time()
        try:
            row = one(mid, args, pmx)
        except Exception as exc:                                 # keep going with the next outfit
            row = {"id": mid, "problems": ["%s: %s" % (type(exc).__name__, exc)]}
        done[mid] = row
        print("%-14s %4.0f s  %s%s" % (mid, time.time() - t, "; ".join(row["problems"]) or "ok",
                                      ("  [%s]" % row["copied"]) if row.get("copied") else ""), flush=True)
    print("ARM_FIX_DONE " + json.dumps({k: {"problems": v["problems"], "copied": v.get("copied")} for k, v in done.items()},
                                       ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
