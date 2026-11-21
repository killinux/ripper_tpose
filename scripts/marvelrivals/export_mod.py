"""Marvel Rivals Nexus mod (.zip / .rar / folder of *_P.pak / .utoc / .ucas) -> HD .blend + PMX + XPS.

    python -I scripts\\marvelrivals\\export_mod.py <mod archive or folder> [--name Label] [--out-root E:\\game_export\\MarvelRivals]
           [--variant REGEX] [--overlay REGEX] [--mesh lobby|game] [--formats blend,pmx,xps] [--no-preview] [--list]
           [--usmap FILE]

A variant without a skeletal mesh that replaces a game skin's textures (a recolour) is exported on that skin's own
mesh from the installed game; --overlay stages such a variant on top of the mod's mesh variants instead.

What it needs:
  * the CUE4Parse CLI (E:\\tools\\cue4parse_cli_ff7\\cue4parse.exe), the game's mappings (.usmap) and AES key
    (E:\\tools\\marvelrivals\\_mappings, _keys - public, see E:\\tools\\marvelrivals\\README.txt);
  * the game's global.utoc / .ucas (script objects - no IoStore package loads without them) and, for everything the
    mod does not bring itself (base materials, textures of the skin it edits), the installed game: the Steam
    libraries are searched for MarvelRivals; while Steam is still downloading, global.* is taken from the download
    folder (read only) and missing materials come out flat grey (listed in the report).

Per variant folder of the mod (Cape on / Cape off, sizes ...): a stage folder of hard links (game containers) + the mod
files (a container whose header says encrypted while its index is plain gets repaired on the copy, fix_utoc.py), then
  1. the mod's package list -> its skeletal meshes (the _Lobby mesh by default: the hero-gallery one, more detail);
  2. mesh -> .psk + JSON (material slots), each slot's material instance and its parents -> JSON, every texture they
     name -> PNG;
  3. build_blend.py (Blender 3.6) -> <out-root>\\<Hero>\\blend\\<label>\\<label>.blend + preview.png;
  4. scripts\\pmx_tools\\biped_pmx (rig ue_mannequin) -> pmx\\<label>\\ and xps\\<label>\\.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import fix_utoc  # noqa: E402

CLI = r"E:\tools\cue4parse_cli_ff7\cue4parse.exe"
TOOLS = r"E:\tools\marvelrivals"
# Mappings, newest first.  SkinStudio 1.0.6 (Nexus #13477 Variant Skin Studio, its app\blender\Marvel.usmap of
# 2026-09-24) also reads the current game's own material instances and textures; the public season-1 file only reads
# what mods cooked with it (README 坑 2).  --usmap picks another one.
USMAPS = ["SkinStudio_1.0.6-Marvel.usmap", "S1_1_release-Marvel.usmap"]
USMAP = next((os.path.join(TOOLS, "_mappings", n) for n in USMAPS
              if os.path.isfile(os.path.join(TOOLS, "_mappings", n))), os.path.join(TOOLS, "_mappings", USMAPS[-1]))
# A mod's own assets were cooked by the game build of their day; what does not deserialise with USMAP (an empty JSON,
# no .psk, no PNG) is tried again with these older mappings (--usmap-old; "none" turns it off).
USMAP_OLD = os.path.join(TOOLS, "_mappings", USMAPS[-1])
KEY_FILE = os.path.join(TOOLS, "_keys", "marvelrivals_aes.txt")
SEVEN_ZIP = r"E:\tools\7zip\7z.exe"
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
WORK_ROOT = r"D:\marvelrivals_work"
OUT_ROOT = r"E:\game_export\MarvelRivals"
STEAM_LIBS = [r"E:\SteamLibrary", r"D:\Program Files (x86)\Steam", r"D:\SteamLibrary", r"C:\Program Files (x86)\Steam"]
PAKS_REL = os.path.join("MarvelGame", "Marvel", "Content", "Paks")
HEROES = {"1011": "Hulk", "1014": "Punisher", "1015": "Storm", "1016": "Loki", "1017": "HumanTorch",
          "1018": "DoctorStrange", "1020": "Mantis", "1021": "Hawkeye", "1022": "CaptainAmerica", "1023": "Rocket",
          "1024": "Hela", "1025": "CloakDagger", "1026": "BlackPanther", "1027": "Groot", "1029": "Magik",
          "1030": "MoonKnight", "1031": "LunaSnow", "1032": "SquirrelGirl", "1033": "BlackWidow", "1034": "IronMan",
          "1035": "Venom", "1036": "SpiderMan", "1037": "Magneto", "1038": "ScarletWitch", "1039": "Thor",
          "1040": "MisterFantastic", "1041": "WinterSoldier", "1042": "PeniParker", "1043": "StarLord",
          "1045": "Namor", "1046": "AdamWarlock", "1047": "JeffTheLandShark", "1048": "Psylocke", "1049": "Wolverine",
          "1050": "InvisibleWoman", "1051": "TheThing", "1052": "IronFist", "1053": "EmmaFrost"}


def log(msg):
    print(msg, flush=True)


def key():
    k = os.environ.get("MARVELRIVALS_AES_KEY")
    if k:
        return k.strip()
    with open(KEY_FILE, encoding="utf-8") as f:
        return f.read().strip()


def game_paks():
    """(installed Paks folder or None, folder holding global.utoc or None)."""
    for lib in STEAM_LIBS:
        p = os.path.join(lib, "steamapps", "common", "MarvelRivals", PAKS_REL)
        if os.path.isfile(os.path.join(p, "global.utoc")) and len(glob.glob(os.path.join(p, "*.utoc"))) > 10:
            return p, p
    for lib in STEAM_LIBS:
        p = os.path.join(lib, "steamapps", "downloading", "2767030", PAKS_REL)
        if os.path.isfile(os.path.join(p, "global.utoc")):
            return None, p
    return None, None


def safe(s):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")


def nexus_name(base):
    """(mod name, mod id) from a Nexus download name: new style 'Name 10647 1.0 2026-07-09T23-12Z xxxx', old style
    'Name-3899-1-1754417247' (id, version parts, unix time)."""
    m = re.match(r"^(.*?) (\d+) [\w.]+ \d{4}-\d\d-\d\dT", base)
    if m:
        return m.group(1).strip(" -"), m.group(2)
    m = re.match(r"^(.*?)-(\d+)(?:-[\w]+)*-\d{9,11}$", base)
    if m:
        return m.group(1).strip(" -"), m.group(2)
    return base, None


def unpack(src, dst):
    os.makedirs(dst, exist_ok=True)
    if os.path.isdir(src):
        for f in glob.glob(os.path.join(src, "**", "*"), recursive=True):
            if os.path.isfile(f):
                t = os.path.join(dst, os.path.relpath(f, src))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(f, t)
    elif src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if info.is_dir() or name.startswith("/") or ".." in name.split("/"):
                    continue
                t = os.path.join(dst, *name.split("/"))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with z.open(info) as a, open(t, "wb") as b:
                    shutil.copyfileobj(a, b)
    else:
        subprocess.run([SEVEN_ZIP, "x", "-y", "-o" + dst, src], check=True, stdout=subprocess.DEVNULL)


def variants(root):
    """Folders holding a mod container set (*.utoc + .ucas + .pak)."""
    out = sorted({os.path.dirname(f) for f in glob.glob(os.path.join(root, "**", "*.utoc"), recursive=True)})
    return out


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def stage(variant_dir, stage_dir, paks, global_dir, aes, overlays=()):
    """Game containers (hard links) + the variant's containers as zzmod_* (mounted after the game, so they win) +
    --overlay variants' containers as zzzz_overlay_* (mounted last: a recolour on top of the variant's mesh)."""
    if os.path.isdir(stage_dir):
        shutil.rmtree(stage_dir)
    os.makedirs(stage_dir)
    fixed = []
    if paks:
        for f in os.listdir(paks):
            if f.lower().endswith((".pak", ".utoc", ".ucas", ".sig")):
                link_or_copy(os.path.join(paks, f), os.path.join(stage_dir, f))
    elif global_dir:
        for f in ("global.utoc", "global.ucas"):
            shutil.copy2(os.path.join(global_dir, f), os.path.join(stage_dir, f))
    for prefix, folder in [("zzmod_", variant_dir)] + [("zzzz_overlay%d_" % i, o) for i, o in enumerate(overlays)]:
        for f in os.listdir(folder):
            src = os.path.join(folder, f)
            if not os.path.isfile(src) or not f.lower().endswith((".pak", ".utoc", ".ucas")):
                continue
            dst = os.path.join(stage_dir, prefix + f)
            if f.lower().endswith(".utoc"):
                with open(src, "rb") as fh:
                    data = fh.read()
                new = fix_utoc.fix(data, aes)
                with open(dst, "wb") as fh:
                    fh.write(new if new is not None else data)
                if new is not None:
                    fixed.append(f)
            else:
                shutil.copy2(src, dst)
    return fixed


def cli(stage_dir, patterns, out_dir, fmt=None, listing=False, usmap=None):
    cmd = [CLI, "-i", stage_dir, "-g", "GAME_MarvelRivals", "-m", usmap or USMAP, "-k", key(), "-y"]
    if out_dir:
        cmd += ["-o", out_dir]
    for p in patterns:
        cmd += ["-p", p]
    if fmt:
        cmd += ["-f", fmt]
    if listing:
        cmd += ["-l"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.stdout + res.stderr


def mod_packages(variant_dir, global_dir, work):
    """The mod's own package paths (listing with only the global container beside it)."""
    tmp = os.path.join(work, "_list")
    stage(variant_dir, tmp, None, global_dir, key())
    out = cli(tmp, ["*"], None, listing=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return [l.strip() for l in out.splitlines() if l.strip().lower().endswith((".uasset", ".ubulk", ".umap"))]


def obj_to_package(obj_path):
    """/Game/Marvel/Characters/X/MI_A.0 -> Marvel/Content/Marvel/Characters/X/MI_A.uasset"""
    p = obj_path.split(".")[0]
    if p.startswith("/Game/"):
        p = "Marvel/Content/" + p[len("/Game/"):]
    return p.lstrip("/") + ".uasset"


def read_json(out_dir, package):
    path = os.path.join(out_dir, *package[:-len(".uasset")].split("/")) + ".json"
    if not os.path.isfile(path):
        # the CLI keeps the case of the container's path
        cands = glob.glob(os.path.join(out_dir, "**", os.path.basename(path)), recursive=True)
        path = cands[0] if cands else path
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def mat_object(data):
    """The MaterialInstance / Material object of a CUE4Parse JSON export, or None ('{}' = it did not deserialise)."""
    if not isinstance(data, list):
        return None
    return next((o for o in data if isinstance(o, dict) and (str(o.get("Type", "")).startswith("MaterialInstance")
                                                             or o.get("Type") == "Material")), None)


def export_material_jsons(stage_dir, out_dir, mi_paths, old_read=None, real=lambda pkg: pkg):
    """JSON of every material instance and all their parents, one CLI call per generation (each call mounts the
    whole game, so they are batched).  A package that comes out empty with the current mappings is exported again with
    the older ones (USMAP_OLD): mods are cooked by the game build of their day - #5032's own MI_1036001_Head_Inst gave
    '{}' with the 2026-09 mappings and its slot fell back to Spider-Man's head textures by name.  Those go into
    old_read."""
    done, todo = set(), {p for p in mi_paths if p}
    for _ in range(8):
        todo -= done
        if not todo:
            break
        cli(stage_dir, sorted(real(obj_to_package(p)) for p in todo), out_dir, fmt="json")
        empty = sorted(p for p in todo if mat_object(read_json(out_dir, obj_to_package(p))) is None)
        if empty and USMAP_OLD and os.path.normcase(USMAP_OLD) != os.path.normcase(USMAP):
            cli(stage_dir, [real(obj_to_package(p)) for p in empty], out_dir, fmt="json", usmap=USMAP_OLD)
            for p in empty:
                if mat_object(read_json(out_dir, obj_to_package(p))) is not None and old_read is not None:
                    old_read.add(p)
        done |= todo
        nxt = set()
        for p in todo:
            data = read_json(out_dir, obj_to_package(p)) or []
            obj = next((o for o in data if isinstance(o, dict)
                        and str(o.get("Type", "")).startswith("MaterialInstance")), None)
            parent = (obj or {}).get("Properties", {}).get("Parent") or {}
            if parent.get("ObjectPath"):
                nxt.add(parent["ObjectPath"])
        todo = nxt


def material_chain(out_dir, mi_obj_path, depth=0):
    """Texture / scalar / vector parameters of a material instance, the child overriding its parents (JSON already
    exported by export_material_jsons)."""
    pkg = obj_to_package(mi_obj_path)
    obj = mat_object(read_json(out_dir, pkg))
    res = {"textures": {}, "scalars": {}, "vectors": {}, "chain": [mi_obj_path], "found": obj is not None}
    if obj is None:
        return res
    props = obj.get("Properties", {})
    parent = props.get("Parent")
    if parent and parent.get("ObjectPath") and depth < 8:
        sub = material_chain(out_dir, parent["ObjectPath"], depth + 1)
        for k in ("textures", "scalars", "vectors"):
            res[k].update(sub[k])
        res["chain"] += sub["chain"]
        for k in ("blend_mode", "clip", "two_sided"):
            if k in sub:
                res[k] = sub[k]
    for t in props.get("TextureParameterValues", []):
        v = t.get("ParameterValue")
        pname = t["ParameterInfo"]["Name"]
        if v and v.get("ObjectPath"):
            res["textures"][pname] = v["ObjectPath"]
        elif pname in res["textures"]:
            # the child sets the slot to None = switches the parent's map off (#7406 JinxyInvisible: Emissive /
            # SpecularTexture None over Spider-Man's head instance - kept, Spider-Man's emissive lit Sue's skin pale)
            del res["textures"][pname]
    for t in props.get("ScalarParameterValues", []):
        res["scalars"][t["ParameterInfo"]["Name"]] = t.get("ParameterValue")
    for t in props.get("VectorParameterValues", []):
        res["vectors"][t["ParameterInfo"]["Name"]] = t.get("ParameterValue")
    bo = props.get("BasePropertyOverrides") or {}
    if "BlendMode" in bo:
        res["blend_mode"] = bo["BlendMode"]
    if "OpacityMaskClipValue" in bo:
        res["clip"] = bo["OpacityMaskClipValue"]
    if bo.get("TwoSided"):
        res["two_sided"] = True
    if obj.get("Type") == "Material":
        res["blend_mode"] = res.get("blend_mode") or props.get("BlendMode", "")
        res["two_sided"] = res.get("two_sided") or bool(props.get("TwoSided"))
    return res


SUFFIX_PARAM = {"D": "BaseColor", "BC": "BaseColor", "N": "Normal", "ORM": "ORM", "S": "SpecularTexture",
                "E": "Emissive", "EM": "Emissive"}


def skin_folder(obj_path):
    """/Game/Marvel/Characters/1035/1035001/Materials/Lobby/MI_X.0 -> Marvel/Content/Marvel/Characters/1035/1035001"""
    m = re.match(r"^/Game/(Marvel/Characters/\d{4}/[^/]+)/", obj_path or "")
    return "Marvel/Content/" + m.group(1) if m else None


def guess_textures(mi_obj_path, listing):
    """Texture parameters by name when the instance's own properties did not come through (the public mappings are
    from season 1; the game's own instances are cooked by later builds and their parameter arrays are lost):
    MI_1035001_Body -> T_1035001_Body_D / _N / _ORM / _S in the same skin folder."""
    name = mi_obj_path.split("/")[-1].split(".")[0]
    part = re.sub(r"^MI_", "", name)
    part = re.sub(r"_(C|Inst|Lobby)$", "", part)
    out = {}
    for pkg in listing:
        stem = pkg.split("/")[-1][:-len(".uasset")]
        m = re.match(r"^T_%s_([A-Za-z]+)$" % re.escape(part), stem, re.I)
        if m and m.group(1).upper() in SUFFIX_PARAM:
            param = SUFFIX_PARAM[m.group(1).upper()]
            out.setdefault(param, "/Game/" + pkg[len("Marvel/Content/"):-len(".uasset")] + "." + stem)
    return out


def find_extra_texture(obj_path, dirs):
    """A game texture that CUE4Parse could not decode, found by name in folders of textures got elsewhere (--extra-
    textures: e.g. another mod that ships the game's own maps, like the HS2 port of Venom with T_1035001_Head_D/N/ORM).
    File stems may carry a numeric path-id suffix (UnityPy / AssetStudio exports: T_1035001_Head_D_3133077305.png)."""
    want = obj_path.split("/")[-1].split(".")[0].lower()
    for d in dirs or ():
        for f in sorted(glob.glob(os.path.join(d, "**", "*.*"), recursive=True)):
            stem, ext = os.path.splitext(os.path.basename(f))
            if ext.lower() in (".png", ".tga", ".jpg", ".jpeg") and re.sub(r"_\d{5,}$", "", stem).lower() == want:
                return f
    return None


def flat_colour(names, rules):
    """--colour REGEX=r,g,b[,roughness] (sRGB 0-1): the stand-in colour for a material that still has no colour map."""
    for rule in rules or ():
        pat, _, vals = rule.rpartition("=")
        if pat and any(n and re.search(pat, n, re.I) for n in names):
            v = [float(x) for x in vals.split(",")]
            return v[:3] + [v[3] if len(v) > 3 else 0.5]
    return None


def is_mesh(p):
    return bool(re.search(r"/SK_[^/]+\.uasset$", p, re.I)) and not re.search(
        r"skeleton|animbp|anim_?blueprint|physics", p, re.I)


def texture_skins(pkgs):
    """(hero id, skin id) of the game skins whose textures a texture-only mod replaces:
    .../Characters/1015/1015503/Texture/T_1015503_Body_D.uasset -> ("1015", "1015503")"""
    out = []
    for p in pkgs:
        m = re.search(r"/Characters/(\d{4})/(\d{7})/[^/]+/T_[^/]+\.uasset$", p, re.I)
        if m and m.groups() not in out:
            out.append(m.groups())
    return out


def export_variant(label, variant_dir, args, paks, global_dir, work, overlays=()):
    """overlays: [(folder of containers, tag)] staged on top of the variant (--overlay / --overlay-mod)."""
    tags = [t for _, t in overlays]
    overlays = [d for d, _ in overlays]
    pkgs = mod_packages(variant_dir, global_dir, work)
    meshes = [p for p in pkgs if is_mesh(p)]
    stage_dir = os.path.join(work, "stage")
    fixed, game_mesh = None, None
    if not meshes:
        # A recolour of a game skin (#6269 Stormy, #4249's _Anti-Venom): that skin's own mesh comes from the installed
        # game, and the mod's textures replace the game's through the stage order.
        skins = texture_skins(pkgs)
        if not (skins and paks):
            return {"label": label, "skipped": "no skeletal mesh and no game skin textures in this variant "
                                               "(physics only, or the game is not installed)", "packages": len(pkgs)}
        hero_id, skin_id = skins[0]
        fixed = stage(variant_dir, stage_dir, paks, global_dir, key(), overlays)
        out = cli(stage_dir, ["Marvel/Content/Marvel/Characters/%s/%s/Meshes/*" % (hero_id, skin_id)], None,
                  listing=True)
        meshes = [l.strip() for l in out.splitlines() if is_mesh(l.strip())]
        if not meshes:
            return {"label": label, "skipped": "texture-only variant, but the game has no mesh for skin %s" % skin_id}
        game_mesh = "texture-only mod: the game's own mesh of skin %s with the mod's textures" % skin_id
    lobby = [p for p in meshes if re.search(r"_lobby\.uasset$", p, re.I)]
    game = [p for p in meshes if p not in lobby]
    mesh = (lobby or game)[0] if args.mesh == "lobby" else (game or lobby)[0]
    hero_id = (re.search(r"/Characters/(\d{4})/", mesh) or re.search(r"(\d{4})", mesh)).group(1)
    hero = HEROES.get(hero_id, "Hero" + hero_id)
    if fixed is None:
        fixed = stage(variant_dir, stage_dir, paks, global_dir, key(), overlays)
    exp = os.path.join(work, "export")
    if os.path.isdir(exp):            # a PNG left by an earlier run must not stand in for one this run fails to export
        shutil.rmtree(exp)
    log("  %s: mesh %s (%s), %s%s%s" % (label, mesh, hero, "game installed" if paks else "mod + global only",
                                         " - " + game_mesh if game_mesh else "",
                                         " + overlay " + ", ".join(tags) if tags else ""))
    cli(stage_dir, [mesh], exp)                       # .psk/.pskx (+ textures it names when they resolve)
    cli(stage_dir, [mesh], exp, fmt="json")
    mj = read_json(exp, mesh) or []
    sk = next((o for o in mj if o.get("Type") == "SkeletalMesh"), {})
    psks = glob.glob(os.path.join(exp, "**", os.path.splitext(os.path.basename(mesh))[0] + ".psk*"), recursive=True)
    if not psks and USMAP_OLD and os.path.normcase(USMAP_OLD) != os.path.normcase(USMAP):
        cli(stage_dir, [mesh], exp, usmap=USMAP_OLD)            # a mod mesh cooked by an older game build
        cli(stage_dir, [mesh], exp, fmt="json", usmap=USMAP_OLD)
        mj = read_json(exp, mesh) or []
        sk = next((o for o in mj if isinstance(o, dict) and o.get("Type") == "SkeletalMesh"), {})
        psks = glob.glob(os.path.join(exp, "**", os.path.splitext(os.path.basename(mesh))[0] + ".psk*"),
                         recursive=True)
        if psks:
            log("    mesh read with the older mappings")
    if not psks:
        why = "mesh export failed"
        if sk and not sk.get("LODModels"):
            # 2026-11-21, the game's own SK_1015_1015503_Lobby with the 09-24 mappings: only "Skeleton" parses, no LODs
            # - the game's skeletal meshes are cooked by a newer build than the mappings (mods' meshes still read)
            why += (": the SkeletalMesh does not deserialise with these mappings (0 LODs; newer than the usmap) - "
                    "for a texture-only mod use --overlay-mod on a mod mesh of the same skin")
        return {"label": label, "error": why, "mesh": mesh, "game_mesh": game_mesh}
    mats, tex_pkgs = {}, set()
    slots = sk.get("SkeletalMaterials", [])
    # The CLI matches package paths case-sensitively, and some mods pack under "marvel/Content/..." (#5032): an object
    # path's package is asked for in the case the mod (or an overlay) really has it, else its own '{}' comes back.
    case = {}
    for d in overlays:
        case.update({p.lower(): p for p in mod_packages(d, global_dir, os.path.join(work, "_lo"))})
    case.update({p.lower(): p for p in pkgs})

    def real(pkg):
        return case.get(pkg.lower(), pkg)

    old_read = set()
    export_material_jsons(stage_dir, exp, [(s.get("Material") or {}).get("ObjectPath") for s in slots], old_read,
                          real)
    listings = {}
    for slot in slots:
        name = slot.get("MaterialSlotName") or "slot"
        mi = (slot.get("Material") or {}).get("ObjectPath")
        info = material_chain(exp, mi) if mi else {"textures": {}, "found": False, "chain": []}
        if mi in old_read:
            info["old_mappings"] = True
        folder = skin_folder(mi)
        # guessing by name only when NO texture parameter came through: added to a readable instance it would put
        # the game skin's maps on a mod's own UV layout
        if mi and folder and not info["textures"]:
            if folder not in listings:
                out = cli(stage_dir, [folder + "/*"], None, listing=True)
                listings[folder] = [l.strip() for l in out.splitlines() if l.strip().lower().endswith(".uasset")]
            guessed = guess_textures(mi, listings[folder])
            info["guessed"] = sorted(k for k in guessed if k not in info["textures"])
            for k, v in guessed.items():
                info["textures"].setdefault(k, v)
        mi_name = mi.split("/")[-1].split(".")[0] if mi else name
        mats[mi_name] = info
        mats.setdefault(name, info)
        for t in info["textures"].values():
            tex_pkgs.add(obj_to_package(t))
    def png_of(pkg):
        p = os.path.join(exp, *pkg[:-len(".uasset")].split("/")) + ".png"
        if not os.path.isfile(p):
            c = glob.glob(os.path.join(exp, "**", os.path.basename(p)), recursive=True)
            p = c[0] if c else p
        return p

    if tex_pkgs:
        cli(stage_dir, sorted(real(p) for p in tex_pkgs), exp, fmt="png")
        missing = sorted(real(p) for p in tex_pkgs if not os.path.isfile(png_of(p)))
        if missing and USMAP_OLD and os.path.normcase(USMAP_OLD) != os.path.normcase(USMAP):
            cli(stage_dir, missing, exp, fmt="png", usmap=USMAP_OLD)
    names_of = {}                     # mats holds each info under its instance name AND its slot name: resolve once
    for k, v in mats.items():
        names_of.setdefault(id(v), (v, []))[1].append(k)
    for info, names in names_of.values():
        resolved, extra = {}, {}
        for param, t in info["textures"].items():
            png = png_of(obj_to_package(t))
            if not os.path.isfile(png):
                # not decodable from the game (old mappings): the same texture from another source, by name
                f = find_extra_texture(t, args.extra_textures)
                if f:
                    png = f
                    extra[param] = f
            if os.path.isfile(png):
                resolved[param] = png
        info["textures"] = resolved
        if extra:
            info["from_extra"] = extra
        has_colour = any(re.search(r"base_?colou?r|diffuse|albedo", p, re.I) for p in resolved)
        if not has_colour:
            flat = flat_colour(names, args.colour)
            if flat:
                info["flat"] = flat
    # a re-export replaces the whole set: files an earlier run wrote (another texture naming, the stand-in maps, the
    # XPS exporter's leftovers - it does not empty its folder) must not stay beside the new ones
    for fmt in ("blend", "pmx", "xps"):
        old = os.path.join(args.out_root, hero, fmt, label)
        if os.path.isdir(old):
            shutil.rmtree(old)
            log("    replaced the earlier %s\\%s" % (fmt, label))
    blend_dir = os.path.join(args.out_root, hero, "blend", label)
    os.makedirs(blend_dir, exist_ok=True)
    spec = {"name": label, "psk": psks[0], "scale": 0.01, "materials": mats}
    spec_path = os.path.join(work, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=1, ensure_ascii=False)
    blend = os.path.join(blend_dir, label + ".blend")
    cmd = [BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "build_blend.py"), "--",
           "--spec", spec_path, "--out", blend]
    if not args.no_preview:
        cmd += ["--preview", os.path.join(blend_dir, "preview")]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    built = None
    for line in res.stdout.splitlines():
        if line.startswith("[mr]"):
            log("    " + line[5:])
        if line.startswith("BUILD_DONE="):
            built = json.loads(line[len("BUILD_DONE="):])
    if built is None:
        log(res.stdout[-2000:] + res.stderr[-2000:])
        return {"label": label, "error": "blender build failed"}
    if built["previews"]:
        contact_sheet(built["previews"], os.path.join(blend_dir, "preview.png"))
    rep = {"label": label, "hero": hero, "mesh": mesh, "other_meshes": [m for m in meshes if m != mesh],
           "game_mesh": game_mesh, "overlays": tags,
           "fixed_containers": fixed, "game_installed": bool(paks), "blend": blend, "built": built,
           "materials": {k: {"chain": v.get("chain"), "found": v.get("found"), "textures": sorted(v["textures"]),
                             "from_extra": v.get("from_extra", {}), "flat": v.get("flat"),
                             "guessed": v.get("guessed", []), "old_mappings": v.get("old_mappings", False)}
                         for k, v in mats.items()}}
    formats = args.formats.split(",")
    biped = os.path.join(REPO, "scripts", "pmx_tools", "biped_pmx")
    if "pmx" in formats:
        out = os.path.join(args.out_root, hero, "pmx", label)
        r = subprocess.run([BLENDER, "-b", blend, "--python", os.path.join(biped, "export_pmx_blender.py"), "--",
                            "--rig", "ue_mannequin", "--out", out, "--name", label, "--model-name", label],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"BIPED_PMX=(\{.*\})", r.stdout)
        rep["pmx"] = json.loads(m.group(1)) if m else {"error": (r.stdout + r.stderr)[-1500:]}
        log("    PMX: %s" % (rep["pmx"].get("pmx") or rep["pmx"].get("error", "")[:300]))
    if "xps" in formats:
        out = os.path.join(args.out_root, hero, "xps", label)
        r = subprocess.run([BLENDER, "-b", blend, "--factory-startup", "--python",
                            os.path.join(biped, "export_xps_blender.py"), "--", "--rig", "ue_mannequin", "--out", out,
                            "--name", label], capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"BIPED_XPS=(\{.*\})", r.stdout)
        rep["xps"] = json.loads(m.group(1)) if m else {"error": (r.stdout + r.stderr)[-1500:]}
        log("    XPS: %s" % (rep["xps"].get("path") or rep["xps"].get("error", "")[:300]))
    return rep


def contact_sheet(files, dst):
    try:
        from PIL import Image
    except ImportError:
        return None
    body = [Image.open(f).convert("RGB") for f in files[:4]]
    heads = [Image.open(f).convert("RGB") for f in files[4:8]]
    h1 = 900
    body = [im.resize((int(im.width * h1 / im.height), h1)) for im in body]
    w = sum(im.width for im in body)
    h2 = w // max(len(heads), 1)
    heads = [im.resize((h2, h2)) for im in heads]
    sheet = Image.new("RGB", (w, h1 + (h2 if heads else 0)), (40, 41, 45))
    x = 0
    for im in body:
        sheet.paste(im, (x, 0))
        x += im.width
    for i, im in enumerate(heads):
        sheet.paste(im, (i * h2, h1))
    sheet.save(dst)
    return dst


def main():
    global USMAP, USMAP_OLD           # cli() reads them; --usmap / --usmap-old override the defaults
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--name", help="label prefix (default: from the archive name)")
    ap.add_argument("--out-root", default=OUT_ROOT)
    ap.add_argument("--variant", help="regex: only variant folders whose path matches")
    ap.add_argument("--mesh", choices=("lobby", "game"), default="lobby")
    ap.add_argument("--formats", default="blend,pmx,xps")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--extra-textures", action="append", default=[], metavar="DIR",
                    help="folder of game textures got elsewhere, searched by name for maps the game cannot give "
                         "(old mappings); repeatable")
    ap.add_argument("--colour", action="append", default=[], metavar="REGEX=r,g,b[,roughness]",
                    help="stand-in sRGB colour (0-1) for materials matching REGEX that still have no colour map; "
                         "repeatable")
    ap.add_argument("--usmap", default=USMAP, help="mappings file (default: the newest one in %s)" %
                    os.path.join(TOOLS, "_mappings"))
    ap.add_argument("--overlay", action="append", default=[], metavar="REGEX",
                    help="variant folders (texture-only recolours) staged ON TOP of every exported variant; they are "
                         "not exported on their own, the label gets their folder name; repeatable")
    ap.add_argument("--overlay-mod", action="append", default=[], metavar="ARCHIVE",
                    help="another mod (.zip / .rar / folder) whose containers are staged on top of every exported "
                         "variant - a texture-only recolour of the same skin; the label gets its name + id; repeatable")
    ap.add_argument("--usmap-old", default=USMAP_OLD,
                    help="older mappings tried again for what does not deserialise with --usmap (mods cooked by an "
                         "older game build); 'none' = off")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    USMAP = args.usmap
    USMAP_OLD = None if args.usmap_old.lower() == "none" or not os.path.isfile(args.usmap_old) else args.usmap_old
    log("mappings: %s (retry with %s)" % (USMAP, USMAP_OLD))
    paks, global_dir = game_paks()
    if not global_dir:
        raise SystemExit("Marvel Rivals' global.utoc not found (install the game, or let Steam start downloading it)")
    base = os.path.splitext(os.path.basename(args.source.rstrip("\\/")))[0]
    name, mod_id = nexus_name(base)
    prefix = safe(args.name or name)
    # hard links into the stage need the same drive as the game
    work_root = os.path.join(os.path.splitdrive(paks)[0] + os.sep, "marvelrivals_work") if paks else WORK_ROOT
    work = os.path.join(work_root, safe(base)[:60])
    src_dir = os.path.join(work, "unpacked")
    if os.path.isdir(src_dir):
        shutil.rmtree(src_dir)
    unpack(args.source, src_dir)
    all_vs = variants(src_dir)
    rels = {v: os.path.relpath(v, src_dir) for v in all_vs}
    # a top folder every variant shares ("Thicc Storm (Symbiote Storm)\Default\M", "...\No Cape\XL") says nothing:
    # labels drop it -> Thicc_Storm_Symbiote_Storm_4249_Default_M
    parts = [r.split(os.sep) for r in rels.values() if r not in (".", "")]
    common = 0
    if len(parts) > 1:
        while all(len(p) > common + 1 and p[common] == parts[0][common] for p in parts):
            common += 1
    own = [v for v in all_vs if any(re.search(o, rels[v], re.I) for o in args.overlay)]
    overlays = [(v, safe(os.path.basename(v))) for v in own]
    for i, path in enumerate(args.overlay_mod):
        # another mod's recolour (#6269 Stormy) on this mod's meshes of the same skin
        obase = os.path.splitext(os.path.basename(path.rstrip("\\/")))[0]
        oname, oid = nexus_name(obase)
        odir = os.path.join(work, "_overlay%d" % i)
        if os.path.isdir(odir):
            shutil.rmtree(odir)
        unpack(path, odir)
        overlays += [(v, safe(oname) + ("_" + oid if oid else "")) for v in variants(odir)]
    vs = [v for v in all_vs if v not in own]
    if args.variant:
        vs = [v for v in vs if re.search(args.variant, rels[v], re.I)]

    def label_of(v):
        rel = os.sep.join(rels[v].split(os.sep)[common:]) if rels[v] not in (".", "") else ""
        tail = "_" + safe(rel.replace(os.sep, "_")) if rel else ""
        tail += "".join("_" + t for t in dict.fromkeys(t for _, t in overlays))
        return prefix + (("_" + mod_id) if mod_id else "") + re.sub(r"_{2,}", "_", tail)

    log("%s: %d variant(s)%s; game %s" % (base, len(vs), " + overlay " + ", ".join(t for _, t in overlays)
                                          if overlays else "",
                                          "installed at " + paks if paks else "NOT installed (mod + global only)"))
    if args.list:
        for v in vs:
            log("  [%s] -> %s" % (rels[v], label_of(v)))
            for p in mod_packages(v, global_dir, os.path.join(work, "_l")):
                log("     " + p)
        return
    reports = []
    for v in vs:
        sub = (safe(rels[v]) or "root") + "".join("+" + t for t in dict.fromkeys(t for _, t in overlays))
        reports.append(export_variant(label_of(v), v, args, paks, global_dir, os.path.join(work, sub), overlays))
    with open(os.path.join(work, "report.json"), "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=1, ensure_ascii=False, default=str)
    log("MR_EXPORT_DONE=" + json.dumps([{k: r.get(k) for k in ("label", "hero", "blend", "skipped", "error")}
                                         for r in reports], ensure_ascii=False))


if __name__ == "__main__":
    main()
