"""Breast physics for a PMX whose breast bones the exporter did not recognise: rigid bodies and joints on the game's
own breast bones, laid out the way every other dressed Rise of Eros outfit has them, and those bones renamed 左胸 / 右胸.

Fourteen dressed ROE outfits name their breast bones in ways Convert_to_MMD5 does not know - Biped extras on Inase
a03-a06 (Xtra01Opp -> Xtra01Opp02 on the left, Bip001 Xtra01 -> Bip001 Xtra0102 on the right), "OPAI" (おっぱい) on
Kart b01-b06 and Misa c03-c06 (Bip001 OPAI_L -> Bip001 OPAI_L02 [-> _L03]).  So none became 左胸 / 右胸, the ROE
worker's add_bust_physics found nothing to hang a body on, and the breasts - skinned by the game to those bones -
move with the ribcage in any dance.  The weights are the game's and stay as they are; this adds what is missing:

    per side  a static anchor sphere (2.4 cm) on the breast's root bone, between its head and the next bone's;
              a swinging sphere on the next bone, at the weighted centre of the vertices it moves (weight >= 0.3),
              radius 0.8 x the 75th-percentile distance of those vertices, kept within 3-6 cm;
              a joint at that bone's head, +-10 degrees on every axis, no translation, no spring;
              mass 1, damping 0.5 / 0.5, friction 0.5, collision group 15 with mask 0 - the numbers of
              scripts/riseoferos/export_character_model_blender.py BUST / add_bust_physics (the user's MMD template).
    a breast of one bone swings itself, hung from the nearest body above it (the torso's).
    the root bones are renamed 左胸 / 右胸 (the English name keeps the game's name), as the exporter does for
    Bip001 Breast_L: MMD tools, the dance report and the bust tuning find them by that name.

The main file gets these template joints; <id>_bustB.pmx is the same file run through
scripts/mmd_physics/tune_bust_pmx.py with its defaults (springs sized for a 15-degree sag, +-25 / 20 / 5 degrees,
damping 0.95) - how every other outfit's _bustB.pmx was made.  Nothing else changes: vertices and weights, faces,
materials, morphs, the other bones / bodies / joints keep their order and values; the new bodies and joints go at
the end.  Needs only Python, numpy and the pmx module inside mmd_tools (no Blender).

    python pmx_add_bust.py --roe pc_b05_hd                      # -> <--out-dir>/pc_b05_hd/pc_b05_hd(_bustB).pmx
    python pmx_add_bust.py --roe pc_a03_hd pc_b05_hd --dry-run  # what it would do
    python pmx_add_bust.py in.pmx out.pmx [--left BONE --right BONE]
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = {
    "unit_cm": 8.0,          # one PMX unit in cm (ROE PMX are exported at scale 12.5)
    "anchor_radius": 2.4,    # cm, the static sphere on the root bone
    "radius": (3.0, 6.0),    # cm, the swinging sphere's radius is kept in here
    "radius_scale": 0.8,     # x the 75th-percentile distance of the moved vertices from their centre
    "min_weight": 0.3,       # vertices that count for the centre / radius
    "limit_deg": 10.0,       # joint rotation limit, every axis
    "mass": 1.0,
    "lin_damp": 0.5,
    "ang_damp": 0.5,
    "friction": 0.5,
    "group": 15,             # collision group (0-based, MMD's 16) ...
    "mask": 0,               # ... and the non-collision mask the exported ROE breast bodies carry
}
BREAST_NAME = re.compile(r"opai|oppai|xtra\d*|breast|bust|chest_?[lr]\b|乳|胸", re.IGNORECASE)
NEXT_NAME = re.compile(r"opai|oppai|xtra|breast|bust|chest|nipple|乳|胸", re.IGNORECASE)   # the root's breast child
HELPER = re.compile(r"^point_|^ac[ _]|_ac(_|\d|$)", re.IGNORECASE)    # Point_breast_UL, AC breast_UL, breas_ac_med_00
TORSO = ("上半身", "上半身1", "上半身2", "上半身3")
SIDE_NAMES = {1: "左胸", -1: "右胸"}          # MMD: left = +X (the model faces -Z)
ROE_ROOT = os.environ.get("ROE_ARCHIVE_ROOT", r"E:\game_export\RiseOfEros")
ROE_OUT = os.path.join(ROE_ROOT, "_videos", "_检查", "补胸骨")
BUST_SUFFIX = "_bustB"
TUNE = os.path.join(os.path.dirname(HERE), "mmd_physics", "tune_bust_pmx.py")
TUNE_BONES = r"胸|乳|chest|breast|bust|oppai|opai|xtra"     # tune_bust_pmx --bones: finds the swing bodies by bone


def pmx_module(path: str | None = None):
    """mmd_tools' stand-alone PMX reader / writer (core/pmx/__init__.py), loaded without Blender."""
    if not path:
        root = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
        for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                        "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits:
                path = hits[0]
                break
    if not path or not os.path.isfile(path):
        raise SystemExit("mmd_tools' core/pmx/__init__.py not found; pass --pmx-module")
    spec = importlib.util.spec_from_file_location("mmd_pmx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_weights(vertex) -> dict:
    """{bone index: weight} of a vertex (a bone listed twice is added up)."""
    w = vertex.weight
    if w.type == 0:
        pairs = [(w.bones[0], 1.0)]
    elif w.type in (1, 3):
        x = w.weights[0] if w.type == 1 else w.weights.weight
        pairs = [(w.bones[0], x), (w.bones[1], 1.0 - x)]
    else:
        pairs = list(zip(w.bones, w.weights))
    out = {}
    for bone, x in pairs:
        if bone is not None and bone >= 0 and x > 0:
            out[bone] = out.get(bone, 0.0) + x
    return out


def children(model) -> dict:
    out = {}
    for i, b in enumerate(model.bones):
        if b.parent is not None and b.parent >= 0:
            out.setdefault(b.parent, []).append(i)
    return out


def subtree(kids: dict, root: int, stop: set) -> list[int]:
    """root and every bone below it, not descending into bones in stop."""
    out, stack = [], [root]
    while stack:
        i = stack.pop()
        out.append(i)
        stack.extend(k for k in kids.get(i, []) if k not in stop)
    return out


def find_breasts(model, left: str | None = None, right: str | None = None) -> dict:
    """{side (+1 left / -1 right): (root bone, next bone or None)}: given by name, or the weighted bones under a torso
    bone whose name looks like a breast's (BREAST_NAME, Japanese or English name), one per side by x - not helpers or
    accessories (HELPER: Point_breast_UL, AC breast_UL), and 左胸 / 右胸 first where a model has them.  The next bone is
    the root's child that looks like a breast's (NEXT_NAME: Breast_L02, chest_L02, OPAI_L02, Xtra01Opp02) and carries
    weight; an unweighted one (g09's chest_R02) or an accessory chain hung on the breast does not count."""
    names = [b.name for b in model.bones]
    kids = children(model)
    weighted = set()
    for v in model.vertices:
        weighted.update(b for b, x in read_weights(v).items() if x > 0.01)
    found = {}
    if left or right:
        for side, name in ((1, left), (-1, right)):
            if name:
                if name not in names:
                    raise SystemExit("no bone %r" % name)
                found[side] = names.index(name)
    else:
        torso = {names.index(n) for n in TORSO if n in names}
        candidates = {}
        for i, b in enumerate(model.bones):
            if b.parent not in torso or not (BREAST_NAME.search(b.name) or BREAST_NAME.search(b.name_e or "")):
                continue
            if b.name not in SIDE_NAMES.values() and (HELPER.search(b.name) or HELPER.search(b.name_e or "")):
                continue
            if not weighted & set(subtree(kids, i, set())):
                continue
            candidates.setdefault(1 if b.location[0] > 0 else -1, []).append(i)
        for side, bones in candidates.items():
            canonical = [i for i in bones if names[i] == SIDE_NAMES[side]]
            if canonical:
                bones = canonical
            if len(bones) > 1:
                raise SystemExit("two breast bones on one side: %s (give --left / --right)"
                                 % ", ".join(names[i] for i in bones))
            found[side] = bones[0]
    out = {}
    for side, root in found.items():
        nxt = [k for k in kids.get(root, []) if (NEXT_NAME.search(names[k]) or NEXT_NAME.search(model.bones[k].name_e or ""))
               and weighted & set(subtree(kids, k, set()))]
        out[side] = (root, (nxt or [None])[0])
    return out


def moved_vertices(model, bones: set, min_weight: float) -> tuple[np.ndarray, np.ndarray]:
    pts, ws = [], []
    for v in model.vertices:
        w = sum(x for b, x in read_weights(v).items() if b in bones)
        if w >= min_weight:
            pts.append(v.co)
            ws.append(w)
    return np.array(pts, dtype=np.float64).reshape(-1, 3), np.array(ws, dtype=np.float64)


def sphere(pmx, name: str, bone: int, location, radius: float, mode: int, opts: dict):
    r = pmx.Rigid()
    r.name, r.name_e, r.bone = name, "", bone
    r.collision_group_number, r.collision_group_mask = opts["group"], opts["mask"]
    r.type, r.size = 0, [float(radius), 0.0, 0.0]
    r.location, r.rotation = [float(x) for x in location], [0.0, 0.0, 0.0]
    r.mass, r.velocity_attenuation, r.rotation_attenuation = opts["mass"], opts["lin_damp"], opts["ang_damp"]
    r.bounce, r.friction, r.mode = 0.0, opts["friction"], mode
    return r


def add_bust(pmx, model, opts: dict, left: str | None = None, right: str | None = None, rename: bool = True) -> dict:
    """Bodies + joints on the breast bones of model (changed in place); returns the report."""
    unit = opts["unit_cm"]
    names = [b.name for b in model.bones]
    kids = children(model)
    on_bone = {}
    for i, r in enumerate(model.rigids):
        if r.bone is not None:
            on_bone.setdefault(r.bone, i)
    breasts = find_breasts(model, left, right)
    if not breasts:
        raise SystemExit("no breast bones found (give --left / --right)")
    taken = [n for n in SIDE_NAMES.values() if n in names]
    report = {"sides": {}}
    limit = math.radians(opts["limit_deg"])
    for side in sorted(breasts, reverse=True):
        root, nxt = breasts[side]
        swing = nxt if nxt is not None else root
        label = SIDE_NAMES[side]
        line = {"root": names[root], "next": names[nxt] if nxt is not None else None}
        report["sides"][label] = line
        if swing in on_bone:
            line["skipped"] = "%s already has a rigid body (%s)" % (names[swing], model.rigids[on_bone[swing]].name)
            continue
        with_body = set(on_bone)
        moved = set(subtree(kids, swing, with_body))
        pts, ws = moved_vertices(model, moved, opts["min_weight"])
        if not len(pts):
            line["skipped"] = "no vertex follows %s by %.1f or more" % (names[swing], opts["min_weight"])
            continue
        centre = (pts * ws[:, None]).sum(0) / ws.sum()
        dist = np.sort(np.linalg.norm(pts - centre, axis=1))
        low, high = (x / unit for x in opts["radius"])
        radius = min(high, max(low, opts["radius_scale"] * float(dist[int(0.75 * (len(dist) - 1))])))
        if nxt is not None:
            anchor = on_bone.get(root)
            if anchor is None:
                head = np.array(model.bones[root].location) + np.array(model.bones[nxt].location)
                model.rigids.append(sphere(pmx, label, root, head * 0.5, opts["anchor_radius"] / unit, 0, opts))
                anchor = on_bone[root] = len(model.rigids) - 1
                line["anchor"] = "new static sphere %s" % label
            else:
                line["anchor"] = "its own body %s" % model.rigids[anchor].name
        else:
            holder = model.bones[root].parent
            while holder is not None and holder >= 0 and holder not in on_bone:
                holder = model.bones[holder].parent
            if holder is None or holder < 0:
                line["skipped"] = "no body above %s to hang it on" % names[root]
                continue
            anchor = on_bone[holder]
            line["anchor"] = "the body of %s (%s)" % (names[holder], model.rigids[anchor].name)
        model.rigids.append(sphere(pmx, names[swing], swing, centre, radius, 1, opts))
        on_bone[swing] = body = len(model.rigids) - 1
        j = pmx.Joint()
        j.name, j.name_e, j.mode = names[swing], "", 0
        j.src_rigid, j.dest_rigid = anchor, body
        j.location, j.rotation = [float(x) for x in model.bones[swing].location], [0.0, 0.0, 0.0]
        j.minimum_location, j.maximum_location = [0.0] * 3, [0.0] * 3
        j.minimum_rotation, j.maximum_rotation = [-limit] * 3, [limit] * 3
        j.spring_constant, j.spring_rotation_constant = [0.0] * 3, [0.0] * 3
        model.joints.append(j)
        line.update({"swing": names[swing], "sphere_cm": round(radius * unit, 2),
                     "centre_from_pivot_cm": round(float(np.linalg.norm(centre - np.array(model.bones[swing].location)))
                                                   * unit, 2), "vertices": int(len(pts))})
        if rename and label not in taken:
            bone = model.bones[root]
            bone.name_e = bone.name_e or bone.name
            line["renamed"] = "%s -> %s" % (bone.name, label)
            bone.name = label
            for r in model.rigids:
                if r.bone == root and r.name == names[root]:
                    r.name = label
    return report


def check(pmx, before_path: str, after_path: str) -> dict:
    """Re-read the written file: only names of the breast roots and the new bodies / joints may differ."""
    a, b = pmx.load(before_path), pmx.load(after_path)
    problems = []
    if a.faces != b.faces or len(a.vertices) != len(b.vertices):
        problems.append("mesh differs")
    for va, vb in zip(a.vertices, b.vertices):
        if (va.co, va.normal, va.uv) != (vb.co, vb.normal, vb.uv) or read_weights(va) != read_weights(vb):
            problems.append("vertices differ")
            break
    if [(m.name, m.vertex_count) for m in a.materials] != [(m.name, m.vertex_count) for m in b.materials]:
        problems.append("materials differ")
    if [m.name for m in a.morphs] != [m.name for m in b.morphs]:
        problems.append("morphs differ")
    if [(x.parent, x.location) for x in a.bones] != [(x.parent, x.location) for x in b.bones]:
        problems.append("bones differ")
    renamed = [(x.name, y.name) for x, y in zip(a.bones, b.bones) if x.name != y.name]
    if len(b.rigids) < len(a.rigids) or [r.name for r in a.rigids] != [r.name for r in b.rigids[:len(a.rigids)]]:
        problems.append("the old bodies changed")
    if [(j.name, j.src_rigid, j.dest_rigid) for j in a.joints] != \
            [(j.name, j.src_rigid, j.dest_rigid) for j in b.joints[:len(a.joints)]]:
        problems.append("the old joints changed")
    return {"ok": not problems, "problems": problems, "renamed": renamed,
            "bodies": "%d -> %d" % (len(a.rigids), len(b.rigids)), "joints": "%d -> %d" % (len(a.joints), len(b.joints))}


def tune(src: str, out: str, tune_script: str = TUNE) -> str:
    """<id>_bustB.pmx: the file through tune_bust_pmx.py with its defaults (as for every other outfit)."""
    if not os.path.isfile(tune_script):
        raise SystemExit("%s not found (--tune)" % tune_script)
    r = subprocess.run([sys.executable, tune_script, src, out, "--bones", TUNE_BONES], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("tune_bust_pmx failed:\n%s%s" % (r.stdout, r.stderr))
    return r.stdout.strip()


def build(pmx, src: str, out: str, opts: dict, dry_run: bool, left=None, right=None, rename=True,
          bust: bool = True, tune_script: str = TUNE) -> dict:
    model = pmx.load(src)
    report = add_bust(pmx, model, opts, left, right, rename)
    report["source"] = src
    if dry_run:
        return report
    if os.path.abspath(out) == os.path.abspath(src):
        raise SystemExit("refusing to overwrite %s; write a new file" % src)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # the pmx module reads texture paths as absolute and writes them relative to the new file: a copy in another
    # folder points back at the original's textures folder
    pmx.save(out, model, add_uv_count=model.header.additional_uvs)
    report["written"] = out
    report["check"] = check(pmx, src, out)
    if bust:
        stem, ext = os.path.splitext(out)
        report["bustB"] = {"written": stem + BUST_SUFFIX + ext,
                           "tune": tune(out, stem + BUST_SUFFIX + ext, tune_script)}
    return report


def roe_pmx(stem: str, root: str = ROE_ROOT) -> str:
    hits = glob.glob(os.path.join(root, "*", "pmx", stem, stem + ".pmx"))
    if not hits:
        raise SystemExit("no PMX for %s under %s" % (stem, root))
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="in.pmx out.pmx")
    ap.add_argument("--roe", nargs="+", default=[], help="ROE outfit ids (pc_b05_hd ...) from the archive")
    ap.add_argument("--out-dir", default=ROE_OUT, help="--roe: writes <out-dir>/<id>/<id>.pmx (+ _bustB) "
                                                       "(default %(default)s)")
    ap.add_argument("--roe-root", default=ROE_ROOT)
    ap.add_argument("--left", help="the left breast's root bone (default: found by name)")
    ap.add_argument("--right", help="the right breast's root bone")
    ap.add_argument("--keep-names", action="store_true", help="do not rename the roots 左胸 / 右胸")
    ap.add_argument("--no-bustb", action="store_true", help="only the template file, no _bustB")
    ap.add_argument("--tune", default=TUNE, help="tune_bust_pmx.py (default %(default)s)")
    for key in ("unit_cm", "anchor_radius", "radius_scale", "min_weight", "limit_deg", "mass", "lin_damp",
                "ang_damp", "friction"):
        ap.add_argument("--" + key.replace("_", "-"), type=float, default=DEFAULTS[key],
                        help="(default %(default)s)")
    ap.add_argument("--radius", default="%g,%g" % DEFAULTS["radius"], help="cm min,max (default %(default)s)")
    ap.add_argument("--group", type=int, default=DEFAULTS["group"], help="(default %(default)s)")
    ap.add_argument("--mask", type=int, default=DEFAULTS["mask"], help="(default %(default)s)")
    ap.add_argument("--pmx-module", help="path of mmd_tools/core/pmx/__init__.py")
    ap.add_argument("--report", help="write the reports as JSON here")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    opts = {k: getattr(a, k) for k in DEFAULTS if k != "radius"}
    opts["radius"] = tuple(float(x) for x in a.radius.split(","))
    pmx = pmx_module(a.pmx_module)
    jobs = []
    if a.files:
        if len(a.files) != 2:
            ap.error("give in.pmx out.pmx")
        jobs.append(tuple(a.files))
    for stem in a.roe:
        jobs.append((roe_pmx(stem, a.roe_root), os.path.join(a.out_dir, stem, stem + ".pmx")))
    if not jobs:
        ap.error("nothing to do: give in.pmx out.pmx or --roe ids")
    reports = {}
    for src, out in jobs:
        report = build(pmx, src, out, opts, a.dry_run, a.left, a.right, not a.keep_names, not a.no_bustb, a.tune)
        reports[src] = report
        print("%s -> %s" % (src, out if not a.dry_run else "(dry run)"))
        for label, line in report["sides"].items():
            print("   %s: %s" % (label, line))
        for key in ("check", "bustB"):
            if key in report:
                print("   %s: %s" % (key, report[key]))
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
