"""Stage + export every variant of a multi-variant replacer mod with UE Viewer (PSK + PNG) and CUE4Parse (mesh JSON),
then group the variants by geometry and material slots.

    python -I -X utf8 export_variants.py CrimsonWingsBBB [--jobs 4]

Per variant (one .utoc/.ucas/.pak triple):
  D:\\stellarblade_exports\\mods\\<mod>\\staging\\<label>\\  hardlinks of the triple + the game's global.utoc/ucas
  D:\\stellarblade_exports\\umodel_mod_exports\\<mod>\\<label>\\  UE Viewer output
  D:\\stellarblade_exports\\mods\\<mod>\\json\\<label>\\  CUE4Parse JSON of the skeletal mesh
Writes D:\\stellarblade_exports\\mods\\<mod>\\variants.json.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

WORK = Path(r"D:\stellarblade_exports\mods")
UOUT = Path(r"D:\stellarblade_exports\umodel_mod_exports")
GAME_PAKS = Path(r"D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks")
UMODEL = r"E:\tools\umodel_stellarblade\umodel_stellar_blade_v6.exe"
CUE = r"E:\tools\cue4parse_cli\cue4parse.exe"
USMAP = r"E:\game_export\StellarBlade\_meta\mappings\StellarBlade_1.1.0.usmap"


def label_for(rel):
    """folder path + stem -> a short unique label"""
    parts = rel.replace("\\", "/").split("/")
    stem = re.sub(r"^(Romaera_CW_|Addon_)", "", parts[-1].rsplit(".", 1)[0])
    stem = re.sub(r"_1566_P$|_P$", "", stem)
    folders = [p for p in parts[:-1] if p]
    keep = []
    for f in folders:
        f = re.sub(r"Crimson Wings |BBB AIO Replacement|Replacement|_AIO|Original Panty&NoPanty", "", f).strip(" _")
        f = re.sub(r"[^A-Za-z0-9]+", "", f)
        if f and f.lower() not in stem.lower():
            keep.append(f)
    return "_".join(keep + [stem])[:80]


def psk_info(path):
    """counts + a geometry hash (points) + material names of a UE Viewer PSK"""
    data = path.read_bytes()
    off, info, mats = 0, {}, []
    pts = b""
    while off + 32 <= len(data):
        cid = data[off:off + 20].split(b"\0")[0].decode("ascii", "replace")
        size, count = struct.unpack_from("<ii", data, off + 24)
        body = data[off + 32: off + 32 + size * count]
        info[cid] = count
        if cid.startswith("PNTS"):
            pts = body
        elif cid.startswith("MATT"):
            for i in range(count):
                mats.append(body[i * size: i * size + 64].split(b"\0")[0].decode("latin-1"))
        off += 32 + size * count
    return {"points": info.get("PNTS0000", 0), "wedges": info.get("VTXW0000", 0) or info.get("VTXW3200", 0),
            "faces": info.get("FACE0000", 0) or info.get("FACE3200", 0), "bones": info.get("REFSKELT", 0),
            "geo": hashlib.md5(pts).hexdigest()[:12], "psk_materials": mats}


def one(mod, rel, utoc):
    label = label_for(rel)
    st = WORK / mod / "staging" / label
    st.mkdir(parents=True, exist_ok=True)
    for ext in (".utoc", ".ucas", ".pak"):
        src = utoc.with_suffix(ext)
        dst = st / src.name
        if src.exists() and not dst.exists():
            os.link(src, dst)
    for g in ("global.utoc", "global.ucas"):
        if not (st / g).exists():
            os.link(GAME_PAKS / g, st / g)
    out = UOUT / mod / label
    if not any(out.rglob("*.psk*")) if out.exists() else True:
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "_umodel.log", "wb") as log:
            subprocess.run([UMODEL, "-export", "-path=" + str(st), "-game=ue4.26", "-noanim", "-psk", "-png",
                            "-out=" + str(out), "*"], stdout=log, stderr=subprocess.STDOUT)
    js = WORK / mod / "json" / label
    if not js.exists() or not any(js.rglob("*.json")):
        js.mkdir(parents=True, exist_ok=True)
        with open(js / "_cue.log", "wb") as log:
            subprocess.run([CUE, "-i", str(st), "-g", "GAME_UE4_26", "-m", USMAP, "-f", "json", "-y", "-o", str(js),
                            "-p", "*.uasset"], stdout=log, stderr=subprocess.STDOUT)
    psks = sorted(out.rglob("*.psk*"))
    rec = {"label": label, "rel": rel, "psk": [str(p) for p in psks]}
    if psks:
        rec.update(psk_info(psks[0]))
    slots = []
    for j in sorted(js.rglob("*.json")):
        try:
            doc = json.load(open(j, encoding="utf-8"))
        except ValueError:
            continue
        for exp in doc if isinstance(doc, list) else [doc]:
            if exp.get("Type") != "SkeletalMesh":
                continue
            rec["mesh_json"] = str(j)
            for m in exp.get("SkeletalMaterials") or exp.get("Materials") or []:
                mi = (m.get("MaterialInterface") or {}).get("ObjectPath", "") if isinstance(m, dict) else ""
                slots.append([m.get("MaterialSlotName", ""), mi.split(".")[0].rsplit("/", 1)[-1], mi])
    rec["slots"] = slots
    return rec


def main(mod, jobs):
    un = WORK / mod / "unzipped"
    utocs = sorted(un.rglob("*.utoc"))
    recs = []
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = [ex.submit(one, mod, str(u.relative_to(un)), u) for u in utocs]
        for f in futs:
            recs.append(f.result())
    labels = [r["label"] for r in recs]
    assert len(set(labels)) == len(labels), "label clash: %r" % labels
    json.dump(recs, open(WORK / mod / "variants.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    groups = {}
    for r in recs:
        groups.setdefault(r.get("geo"), []).append(r)
    print("%s: %d variants, %d distinct geometries" % (mod, len(recs), len(groups)))
    for g, rs in groups.items():
        r0 = rs[0]
        print("  geo %s  points %s faces %s bones %s  slots %d" % (g, r0.get("points"), r0.get("faces"), r0.get("bones"),
                                                                  len(r0.get("slots") or [])))
        for r in rs:
            print("     %-60s %s" % (r["label"], ",".join(s[1] for s in r.get("slots") or [])[:200]))


if __name__ == "__main__":
    a = sys.argv[1:]
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 4
    main(a[0], jobs)
