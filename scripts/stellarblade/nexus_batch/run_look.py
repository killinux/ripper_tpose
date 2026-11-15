"""Run the export steps for one look of looks.py (each step logged, skipped when done unless --redo).

    python -I -X utf8 run_look.py <label> [--steps stage,umodel,cue,swap,fill,texfix,xps,pmx,preview] [--redo swap,...]

stage   : hardlinks of the look's .pak/.utoc/.ucas folders + the game's global.utoc/ucas
          -> D:\\stellarblade_exports\\mods\\<mod>\\staging\\<key>\\  (key shared by looks with the same files)
umodel  : UE Viewer (mod files only) -> D:\\stellarblade_exports\\umodel_mod_exports\\<mod>\\<key>\\
cue     : CUE4Parse of the look's mesh with the game's Paks beside it (the mod's files at the folder's ROOT: a
          replacer at the game's own path is read as the mod's, in a subfolder after "game" it is not) -> every slot's
          instance, its parent chain and flattened maps (hq_mod_outfits.read_game / flatten) -> slots.json (also in the
          shape swap_mod_mesh.py's --mesh-json reads)
swap    : swap_mod_mesh.py into the archived base package -> D:\\stellarblade_exports\\packages\\<label>\\
fill    : fill_materials.py: slots swap left empty get their nearest ancestor's game material (this .blend or any
          archived one, material_index.json) or one built from the game's maps; CNS default texture options; CNS
          toggles that are off by default remove their faces
texfix  : the mod's textures that replace game textures of the same name copied over the package's copies
xps / pmx / preview : blender2xps, export_pmx_blender.py, preview_pmx_blender.py --dance-views front,back
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from looks import BY_LABEL, LOOKS, MODS  # noqa: E402

SB = r"E:\code\othercode\ripper_tpose\scripts\stellarblade"
sys.path.insert(0, SB)
import hq_mod_outfits as hq  # noqa: E402

WORK = Path(r"D:\stellarblade_exports\mods")
UOUT = Path(r"D:\stellarblade_exports\umodel_mod_exports")
PACKAGES = Path(r"D:\stellarblade_exports\packages")
XPS_OUT = Path(r"D:\stellarblade_exports\xps")
PMX_OUT = Path(r"D:\stellarblade_exports\pmx")
ARCH_EVE = Path(r"E:\game_export\StellarBlade\Eve\blend")
GAME_PAKS = r"D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks"
UMODEL = r"E:\tools\umodel_stellarblade\umodel_stellar_blade_v6.exe"
CUE = r"E:\tools\cue4parse_cli\cue4parse.exe"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
B2X = r"E:\code\othercode\blender2xps\tools\batch_export_blends.py"
MATERIAL_INDEX = r"E:\game_export\StellarBlade\_meta\material_index.json"   # material_index.py writes it
ALL_STEPS = ["stage", "umodel", "cue", "swap", "fill", "texfix", "xps", "pmx", "preview"]
BASE_KEYS = ("basecolor", "base color", "diffuse", "albedo", "basecolour", "base_color")
NORMAL_KEYS = ("baked normalmap", "normal", "basenormal", "normalmap", "normal map")
ORM_KEYS = ("orm", "arm")
HIDE_RE = re.compile(r"^(M_|MI_|MA_)?(Hide|Hidden|Invisible)(_.*)?$", re.I)


class StepError(RuntimeError):
    pass


def run(cmd, log, timeout=3600):
    t = time.time()
    with open(log, "wb") as fh:
        p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    return p.returncode, time.time() - t


def stage_key(stage):
    if len(stage) == 1 and stage[0][1] in (".", "") and len(stage[0]) == 2:
        return "main"
    s = "|".join("/".join(x) for x in stage)
    tail = re.sub(r"[^A-Za-z0-9]+", "_", stage[-1][-1].split("/")[-1])[-40:].strip("_") or "main"
    return "%s_%s" % (tail, hashlib.md5(s.encode()).hexdigest()[:6])


def triple_files(entry):
    mod, sub = entry[0], entry[1]
    stem = entry[2] if len(entry) > 2 else None
    d = WORK / mod / "unzipped" / sub
    return [f for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in (".pak", ".utoc", ".ucas")
            and (stem is None or f.stem == stem)]


def link_into(dst_dir, files):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        d = dst_dir / f.name
        if not d.exists():
            os.link(f, d)


def patch_name(f):
    """<stem>_P.<ext>: CUE4Parse mounts the containers in parallel and, between two holding the same package path,
    keeps the one with the higher read order - "_P" (a patch) ranks above the game's pakchunks; with equal orders
    the winner is random (11-15: Revealing Crimson Wings' CH_P_EVE_39 read as the game's own mesh in 2 runs of 3)"""
    return f.name if f.stem.lower().endswith("_p") else f.stem + "_P" + f.suffix


class GamePaks:
    """<dir>\\ with the look's files at its root (named as patches, patch_name()) and a junction "game" -> the
    game's Paks; the junction (only the junction) is removed on exit"""

    def __init__(self, d, stage):
        self.d, self.stage = Path(d), stage

    def __enter__(self):
        if self.d.exists():
            self.close()
            shutil.rmtree(self.d)
        self.d.mkdir(parents=True)
        for f in [f for e in self.stage for f in triple_files(e)]:
            os.link(f, self.d / patch_name(f))
        self.link = self.d / "game"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(self.link), GAME_PAKS], capture_output=True)
        return str(self.d)

    def close(self):
        lnk = self.d / "game"
        if os.path.lexists(lnk):
            os.rmdir(lnk)

    def __exit__(self, *exc):
        self.close()


def find_psk(out_dir, mesh_path):
    """the PSK UE Viewer wrote for the mesh: its file name, the deepest matching folder tail wins"""
    name = mesh_path.rsplit("/", 1)[-1]
    tail = [p.lower() for p in mesh_path.split("/")[2:-1]]          # drop "<mount>/Content"
    best, score = None, -1
    for p in out_dir.rglob(name + ".psk*"):
        parts = [x.lower() for x in p.relative_to(out_dir).parts[:-1]]
        s = 0
        while s < min(len(parts), len(tail)) and parts[-1 - s] == tail[-1 - s]:
            s += 1
        if s > score:
            best, score = p, s
    return best


def psk_counts(path):
    """counts, material names and faces per material of a UE Viewer PSK"""
    import struct
    from collections import Counter
    data = path.read_bytes()
    off, info, mats, per = 0, {}, [], Counter()
    while off + 32 <= len(data):
        cid = data[off:off + 20].split(b"\0")[0].decode("ascii", "replace")
        size, count = struct.unpack_from("<ii", data, off + 24)
        body = data[off + 32: off + 32 + size * count]
        if cid.startswith("MATT"):
            mats = [body[i * size: i * size + 64].split(b"\0")[0].decode("latin-1") for i in range(count)]
        elif cid.startswith("FACE"):
            mi_off = 12 if cid.startswith("FACE3200") else 6        # 3 wedge indices (uint32 / uint16), then MatIndex
            per = Counter(body[i * size + mi_off] for i in range(count))
        info[cid[:4]] = count
        off += 32 + size * count
    return {"points": info.get("PNTS", 0), "faces": info.get("FACE", 0), "materials": mats,
            "faces_per_material": [per.get(i, 0) for i in range(len(mats))]}


def lenient_json(path):
    raw = open(path, encoding="utf-8-sig").read()
    return json.loads(re.sub(r",\s*([\]}])", r"\1", raw))


def cns_defaults(lk):
    """the CNS registration of this look's mesh: default texture options, materials hidden by default"""
    mesh_name = lk["mesh"].rsplit("/", 1)[-1].lower()
    tail = "/".join(lk["mesh"].split("/")[2:]).lower()
    out = {"overrides": [], "hide": [], "parameters": [], "fit": None}
    for j in (WORK / lk["mod"] / "unzipped").rglob("*.dekcns.json"):
        doc = lenient_json(j)
        for fit in doc if isinstance(doc, list) else [doc]:
            paths = list(fit.get("OutfitPaths") or [])
            datas = fit.get("OutfitDatas") or []
            paths += [d.get("Mesh") or "" for d in datas]
            k = next((i for i, p in enumerate(paths) if p.split(".")[0].lower().endswith("/" + tail.split("/", 1)[-1])
                      or p.split(".")[0].rsplit("/", 1)[-1].lower() == mesh_name and tail.split("/")[0] in p.lower()),
                     None)
            if k is None:
                k = next((i for i, p in enumerate(paths) if p.split(".")[0].rsplit("/", 1)[-1].lower() == mesh_name),
                         None)
            if k is None:
                continue
            out["fit"] = fit.get("UniqueFitID")
            data = datas[k - len(fit.get("OutfitPaths") or [])] if datas and k >= len(fit.get("OutfitPaths") or []) else {}
            out["hide"] += list(data.get("HiddenMats") or [])
            out["parameters"] = data.get("Parameters") or []
            if data.get("Materials"):
                out["material_overrides"] = data["Materials"]
            ut = fit.get("UserConfigs") or {}
            for t in ut.get("MaterialToggles") or []:
                if t.get("Value") is False:
                    out["hide"].append(t["MaterialIndex"])
            for t in ut.get("TextureOptions") or []:
                v = t.get("Value", 0) or 0
                texs = t.get("Textures") or []
                if 0 <= v < len(texs) and texs[v]:
                    out["overrides"].append({"index": t.get("MaterialIndex", 0), "param": t.get("ParamName"),
                                             "texture": texs[v], "option": (t.get("OptionNames") or [""] * (v + 1))[v],
                                             "name": t.get("DisplayName")})
            return out
    return out


def pick(textures, keys):
    for k, v in textures.items():
        if k.lower() in keys:
            return v
    return None


def main():
    a = sys.argv[1:]
    lk = BY_LABEL[a[0]]
    steps = a[a.index("--steps") + 1].split(",") if "--steps" in a else ALL_STEPS
    redo = set(a[a.index("--redo") + 1].split(",")) if "--redo" in a else set()
    mod, label = lk["mod"], lk["label"]
    meta = MODS[mod]
    key = stage_key(lk["stage"])
    staging = WORK / mod / "staging" / key
    uout = UOUT / mod / key
    lw = WORK / mod / "looks" / label
    lw.mkdir(parents=True, exist_ok=True)
    status_path = lw / "status.json"
    status = json.load(open(status_path, encoding="utf-8")) if status_path.exists() else {}

    def save():
        json.dump(status, open(status_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    pkg = PACKAGES / label
    blend = pkg / (label + ".blend")
    for step in steps:
        if step in status and step not in redo:
            continue
        t0 = time.time()
        if step == "stage":
            files = [f for e in lk["stage"] for f in triple_files(e)]
            if not files:
                raise StepError("no .pak/.utoc/.ucas for %s" % lk["stage"])
            link_into(staging, files)
            link_into(staging, [Path(GAME_PAKS) / "global.utoc", Path(GAME_PAKS) / "global.ucas"])
            status[step] = {"files": [f.name for f in files], "key": key}
        elif step == "umodel":
            marker = uout / "_umodel_done.txt"
            if not marker.exists() or step in redo:
                uout.mkdir(parents=True, exist_ok=True)
                rc, dt = run([UMODEL, "-export", "-path=" + str(staging), "-game=ue4.26", "-noanim", "-psk", "-png",
                              "-out=" + str(uout), "*"], uout / "_umodel.log")
                marker.write_text("rc %s in %.0f s\n" % (rc, dt))
            psk = find_psk(uout, lk["mesh"])
            if psk is None:
                raise StepError("UE Viewer wrote no PSK for %s (see %s)" % (lk["mesh"], uout / "_umodel.log"))
            status[step] = dict(psk=str(psk), **psk_counts(psk))
        elif step == "cue":
            cd = WORK / mod / "cue" / label
            jdir = cd / "json"
            shutil.rmtree(jdir, ignore_errors=True)
            try:
                with GamePaks(cd / "paks", lk["stage"]) as paks:
                    mats = hq.read_game([lk["mesh"] + ".uasset"], str(jdir), paks, any_mount=True)
            except SystemExit as e:
                raise StepError("CUE4Parse: %s" % str(e)[-600:])
            mesh = mats.get(lk["mesh"].rsplit("/", 1)[-1])
            if mesh is None or mesh.get("Type") != "SkeletalMesh":
                raise StepError("CUE4Parse wrote no SkeletalMesh for %s" % lk["mesh"])
            psk_mats = status["umodel"]["materials"]
            if "faces_per_material" not in status["umodel"]:
                status["umodel"].update(psk_counts(Path(status["umodel"]["psk"])))
            psk_faces = status["umodel"]["faces_per_material"]
            # UE Viewer writes one PSK material per LOD0 SECTION, in section order: a slot no section uses is left
            # out (the Nikke Plus jacketless mesh's MI_Basebody_V02_F2, the nude bodies' empty heels / pubic-hair
            # slots), a slot two sections use comes twice, a disabled section is there too (Crimson Wings OP: UV2 in
            # sections 1 and 3, a 1766-triangle proxy section the game does not draw) - checked by triangle counts
            sections = (mesh.get("LODModels") or [{}])[0].get("Sections") or []
            if len(sections) != len(psk_mats) or [s.get("NumTriangles", 0) for s in sections] != psk_faces:
                raise StepError("PSK materials %s (faces %s) do not match the mesh's sections %s (triangles %s): the "
                                "game's own mesh, not the mod's?" % (psk_mats, psk_faces,
                                                                     [s.get("MaterialIndex") for s in sections],
                                                                     [s.get("NumTriangles") for s in sections]))
            all_slots = mesh.get("SkeletalMaterials") or []
            order = [s.get("MaterialIndex", 0) for s in sections]
            slots = []
            for i, j in enumerate(order):
                m = all_slots[j]
                mat = m.get("Material") or {}
                path = mat.get("ObjectPath") or ""
                mi = hq.quoted(mat.get("ObjectName", "")) if mat else ""
                psk_name = psk_mats[i]
                use = mi or (psk_name if psk_name and not re.match(r"material_?\d+$", psk_name, re.I) else "") \
                    or m.get("MaterialSlotName") or "slot%d" % i
                chain, textures, blendmode, vectors, scalars = [], {}, None, {}, {}
                if mi:
                    staged, note = hq.flatten(mi, mats)
                    chain = note.get("chain", [])
                    blendmode = note.get("blend")
                    if staged:
                        pr = staged[0]["Properties"]
                        textures = {t["ParameterInfo"]["Name"]: t["ParameterValue"]["ObjectPath"]
                                    for t in pr["TextureParameterValues"]}
                        vectors = {t["ParameterInfo"]["Name"]: t["ParameterValue"] for t in pr["VectorParameterValues"]}
                        scalars = {t["ParameterInfo"]["Name"]: t["ParameterValue"] for t in pr["ScalarParameterValues"]}
                slots.append({"index": i, "mesh_index": j, "MaterialSlotName": m.get("MaterialSlotName"),
                              "disabled": bool(sections[i].get("bDisabled")),
                              "resolved": path or None, "psk": psk_name, "use": use, "chain": chain,
                              "textures": textures, "blend": blendmode, "vectors": vectors, "scalars": scalars,
                              "MaterialInterface": {"ObjectName": "MaterialInstanceConstant'%s'" % use}})
            json.dump(slots, open(lw / "slots.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            status[step] = {"slots": [(s["MaterialSlotName"], s["use"], bool(s["resolved"]), len(s["chain"]))
                                      for s in slots],
                            "undrawn_slots": [all_slots[j].get("MaterialSlotName") for j in range(len(all_slots))
                                              if j not in order],
                            "skeleton": ((mesh.get("Properties") or {}).get("Skeleton") or {}).get("ObjectName")}
        elif step == "swap":
            base = ARCH_EVE / lk["base"]
            cmd = [BLENDER, "-b", "--factory-startup", "--python", os.path.join(SB, "swap_mod_mesh.py"), "--",
                   "--base", str(base), "--psk", status["umodel"]["psk"], "--tex-root", str(uout),
                   "--mesh-json", str(lw / "slots.json"), "--out", str(PACKAGES), "--label", label,
                   "--title", lk["title"]]
            for extra in lk.get("material_from", []):
                cmd += ["--material-from", extra]
            rc, dt = run(cmd, lw / "swap.log", timeout=1800)
            text = open(lw / "swap.log", encoding="utf-8", errors="replace").read()
            if "SB_MOD_SWAP=" not in text:
                raise StepError("swap failed rc %s (see %s)" % (rc, lw / "swap.log"))
            rep = json.loads(text.split("SB_MOD_SWAP=", 1)[1].splitlines()[0])
            status[step] = {"bone_fit": rep.get("bone_fit"), "slots": rep.get("slots"),
                            "missing_textures": rep.get("missing_textures", []), "height_cm": rep.get("height_cm"),
                            "seconds": round(dt)}
            for later in ("fill", "texfix", "xps", "pmx", "preview"):
                status.pop(later, None)                    # a new package: the later steps must run again
        elif step == "fill":
            slots = json.load(open(lw / "slots.json", encoding="utf-8"))
            index = json.load(open(MATERIAL_INDEX, encoding="utf-8"))
            sw = status["swap"]["slots"] or {}
            cns = cns_defaults(lk)
            mod_png = {}
            for p in uout.rglob("*.png"):
                mod_png.setdefault(p.stem.lower(), str(p))
            wanted, fetch = {}, {}

            def png_for(object_path):
                n = object_path.split(".")[0].rsplit("/", 1)[-1]
                if n.lower() in mod_png:
                    return mod_png[n.lower()]
                fetch[n] = object_path
                return n                                        # resolved after the fetch
            spec_slots, hidden_by_mod = [], []
            for s in slots:
                src = (sw.get(s["use"]) or {}).get("source", "")
                need = src in ("as imported", "none", "")
                if s.get("disabled") or any(HIDE_RE.match(x) for x in s["chain"][1:]):
                    # the mod points the slot at an invisible material (YoRHa Ceremonial's arms / legs / hands skin
                    # under gloves and stockings, its pubic hair: parent "Hide") - not drawn in the game
                    hidden_by_mod.append(s["index"])
                    continue
                rec = {"index": s["index"], "name": s["use"], "need": need, "ancestors": s["chain"][1:],
                       "sources": {x: index[x] for x in s["chain"][1:] if x in index}, "textures": {},
                       "vectors": s.get("vectors", {}), "scalars": s.get("scalars", {}), "blend": s.get("blend")}
                if need and not rec["sources"]:
                    t = s["textures"]
                    for k, keys in (("base", BASE_KEYS), ("normal", NORMAL_KEYS), ("orm", ORM_KEYS)):
                        op = pick(t, keys)
                        if op:
                            rec["textures"][k] = png_for(op)
                    rec["textures"]["alpha_masked"] = (s.get("blend") or "").endswith(("Masked", "Translucent"))
                spec_slots.append(rec)
            # CNS numbers the mesh's material slots; the Blender object has only the drawn ones (slots.json)
            to_blender = {}
            for s in slots:
                to_blender.setdefault(s.get("mesh_index", s["index"]), []).append(s["index"])
            cns["hide"] = [i for j in cns["hide"] for i in to_blender.get(j, [])]
            overrides = []
            for o in cns["overrides"]:
                for i in to_blender.get(o["index"], []):
                    overrides.append({"index": i, "param": o["param"], "png": png_for(o["texture"]),
                                      "texture": o["texture"], "option": o["option"], "name": o["name"]})
            got = {}
            if fetch:
                fdir = lw / "fill_tex"
                fdir.mkdir(exist_ok=True)
                with GamePaks(WORK / mod / "cue" / label / "paks", lk["stage"]) as paks:
                    for n, op in fetch.items():
                        try:
                            hq.cue4parse([hq.package_glob(op, True)[:-2] + ".uasset"], str(fdir), paks, fmt="png")
                        except SystemExit:
                            pass
                        hits = list(fdir.rglob(n + ".png"))
                        if hits:
                            got[n] = str(hits[0])
            for rec in spec_slots:
                for k in ("base", "normal", "orm"):
                    v = rec["textures"].get(k)
                    if v and not os.path.isfile(v):
                        rec["textures"][k] = got.get(v)
            overrides = [dict(o, png=got.get(o["png"], o["png"])) for o in overrides]
            missing_tex = [o["png"] for o in overrides if not os.path.isfile(o["png"])]
            overrides = [o for o in overrides if os.path.isfile(o["png"])]
            spec = {"object": "Eve_Body_Mesh_01", "slots": spec_slots, "overrides": overrides,
                    "hide": sorted(set(cns["hide"]) | set(hidden_by_mod)), "hidden_by_mod": hidden_by_mod,
                    "mesh_index": {s["index"]: s.get("mesh_index", s["index"]) for s in slots}}
            json.dump(spec, open(lw / "fill.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            rc, dt = run([BLENDER, "-b", "--factory-startup", str(blend), "--python",
                          os.path.join(HERE, "fill_materials.py"), "--", str(lw / "fill.json")], lw / "fill.log")
            text = open(lw / "fill.log", encoding="utf-8", errors="replace").read()
            if "SB_FILL=" not in text:
                raise StepError("fill failed rc %s (see %s)" % (rc, lw / "fill.log"))
            rep = json.loads(text.split("SB_FILL=", 1)[1].splitlines()[0])
            status[step] = dict(rep, cns_fit=cns["fit"], cns_parameters=cns["parameters"],
                                cns_material_overrides=cns.get("material_overrides"), textures_not_found=missing_tex,
                                seconds=round(dt))
        elif step == "texfix":
            mod_png = {}
            for p in uout.rglob("*.png"):
                mod_png.setdefault(p.stem.lower(), p)
            replaced = []
            for p in (pkg / "textures").rglob("*.png"):
                if "mod" in [x.lower() for x in p.relative_to(pkg / "textures").parts[:-1]]:
                    continue
                src = mod_png.get(p.stem.lower())
                if src is not None and (os.path.getsize(src) != os.path.getsize(p)
                                        or open(src, "rb").read() != open(p, "rb").read()):
                    shutil.copy2(src, p)
                    replaced.append(str(p.relative_to(pkg)))
            status[step] = {"replaced": replaced}
        elif step == "xps":
            rc, dt = run([BLENDER, "-b", "--factory-startup", "--python", B2X, "--", "--out", str(XPS_OUT),
                          "--scale", "0.01", "--bake", "AUTO", str(blend)], lw / "xps.log", timeout=3600)
            xps = XPS_OUT / label / (label + ".xps")
            if not xps.exists():
                raise StepError("no XPS (rc %s, see %s)" % (rc, lw / "xps.log"))
            status[step] = {"xps": str(xps), "bytes": xps.stat().st_size, "seconds": round(dt)}
        elif step == "pmx":
            comment = ("Stellar Blade mod '%s' by %s (nexusmods.com/stellarblade/mods/%d), file '%s'; converted by "
                       "ripper_tpose scripts/stellarblade. Personal use only; credit the mod author."
                       % (meta["title"], meta["author"], meta["nexus"], meta["file"]))
            (PMX_OUT / "_logs").mkdir(parents=True, exist_ok=True)
            plog = PMX_OUT / "_logs" / (label + ".log")
            cmd = [BLENDER, "-b", str(blend), "--python", os.path.join(SB, "export_pmx_blender.py"), "--",
                   "--out", str(PMX_OUT), "--model-name", "Eve " + lk["title"], "--comment", comment]
            cmd += lk.get("pmx_args", [])
            rc, dt = run(cmd, plog, timeout=3600)
            text = open(plog, encoding="utf-8", errors="replace").read()
            if "SB_PMX_REPORT=" not in text:
                raise StepError("PMX failed rc %s (see %s)" % (rc, plog))
            rep = json.loads(text.split("SB_PMX_REPORT=", 1)[1].splitlines()[0])
            status[step] = {"pmx": str(PMX_OUT / label / (label + ".pmx")), "seconds": round(dt),
                            "report": {k: rep.get(k) for k in ("bones", "rigid_bodies", "joints", "vertex_morphs",
                                                               "torn", "holes", "stray_recipients", "height")
                                       if k in rep}}
        elif step == "preview":
            plog = PMX_OUT / "_logs" / (label + "_preview.log")
            rc, dt = run([BLENDER, "-b", "--python", os.path.join(SB, "preview_pmx_blender.py"), "--",
                          "--pmx", status["pmx"]["pmx"], "--dance-views", "front,back"], plog, timeout=3600)
            text = open(plog, encoding="utf-8", errors="replace").read()
            if "PMX_PREVIEW=" not in text:
                raise StepError("preview failed rc %s (see %s)" % (rc, plog))
            rep = json.loads(text.split("PMX_PREVIEW=", 1)[1].splitlines()[0])
            status[step] = {"seconds": round(dt), "report": rep}
        else:
            raise StepError("unknown step " + step)
        status.setdefault("times", {})[step] = round(time.time() - t0)
        save()
        print("[%s] %s done (%.0f s)" % (label, step, time.time() - t0), flush=True)
    save()


if __name__ == "__main__":
    try:
        main()
    except StepError as e:
        print("STEP_ERROR " + str(e), flush=True)
        sys.exit(2)
