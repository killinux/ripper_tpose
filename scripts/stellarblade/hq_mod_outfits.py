r"""HQ .blend of the archived Nexus-mod outfits worn by Eve (Gantz Reika A / B, Vindictus Fiona, Vindictus Demon Maiden,
and the nude body of EveOriginalProportions), so the stellarblade_game_materials add-on finds every material of their PMX.  The mod's own
material instances are read with CUE4Parse together with their game parents and masters, flattened, and handed to
the SB HQ scripts unchanged: ../hq_materials.py (materials.json) -> ../hq_materials_blender.py on the archived outfit
.blend -> <label>_HQ.blend.

    python hq_mod_outfits.py [--only Mod_GantzReika_B] [--paks "<StellarBlade>\SB\Content\Paks"]

A mod installed in the game's Paks\~mods is read from there.  One that is not installed (the nude body: it replaces
the inner suit, so it is kept out of the game) is read from its download archive: the variant's .pak / .utoc / .ucas
unpacked into a scratch folder next to a junction to the game's Paks, so its instances still find their game parents.

Per outfit (E:\game_export\StellarBlade\<char>\blend\<package>\<label>.blend), data in _meta\hq_materials\<package>\:
  1. mi_json\: CUE4Parse JSON of the mod folder, then of every parent up to the master;
  2. staged\MI_<name>.json: each instance the outfit's mesh uses, flattened - UE's rule: the child's value wins, the
     master's defaults (its CachedExpressionData) for what no instance sets; parameter names are FNames, which UE
     compares without case (Vindictus Fiona's shoes set "BaseColor" over their parent's "Basecolor": one parameter,
     kept under the master side's spelling).  One translation hq_materials.py has no
     rule for: the GlowEmissive layer (static switch UseGlowEmissive; the Planet Diving Suit master MA_CH_P_EVE_09,
     which the Gantz Reika suits inherit through MI_P_EVE_09_Metal02_Layered) lights the ML_GlowEmissive_CH channel of
     the Emissive map in ML_GlowEm_EyeCoreHDRTint - written as Emissive_CH / EmissiveColor (HDR, kept as is) /
     EmissivePower 1 (only switches the wiring on).  The layer's fresnel / boost terms are not reproduced;
  3. ../hq_materials.py --mi-json staged --textures <outfit folder>\textures --out <data dir>; then normals.json: the
     green direction of every normal map the outfit wires, by an integrability test (normal_convention(): a map made
     from a height field has no curl only when read its own way).  UE's maps are DirectX; one that is clearly the
     OpenGL way (Vindictus Fiona's dress PCF_005_Onepiece_N - flipped by the mod, the Vindictus original and the
     outfit's other maps are DirectX - so the game lights its relief upside down) is read the OpenGL way in step 5;
  4. ../hq_materials_blender.py on the archived .blend -> <label>_HQ.blend next to it (the eye rebuilt from the
     game's values on the way, as in every HQ .blend);
  5. this script inside Blender (--post):
     - skin instances (masters MA_Skin*: BaseColor / BaseNormal / "ORSS Mask" = R occlusion, G roughness, B specular,
       A subsurface; hq_materials.py reads none of these names) are wired here: roughness = G between MinRoughness and
       MaxRoughness, specular = B x BaseSpecularValue, the DirectX normal x NormalStrength; the subsurface settings
       are the head material's, so the body skin meets the face (whose archive network stays) without a seam -
       skin.json lists what was read.  A skin whose ORSS mask is not among the outfit's textures keeps its parent's;
       layout_kept() correlates the skin's normal map with the parent's.  A body on the parent's UV layout (Vindictus
       Demon Maiden: Eve's BaseBody V02_F1 repainted, r 0.92) gets the parent's mask itself, copied to
       textures\extra; one on another layout (Vindictus Fiona: Eve's CH_P_EVE_BB_V01_ORSS on Fiona's UVs, r about 0)
       would have Eve's creases land at random, so the mask's means become constants (orss_mean(); both game
       textures exported once to <data>\orss\).  An opaque master's skin is made opaque where the archive had wired
       the base colour's alpha (Fiona's skin textures carry UV coverage there);
     - normal maps normals.json calls OpenGL get their green unpack turned (flip_green());
     - nodes the new wiring left with no path to the output are dropped (the archive had guessed ORM / normal /
       emission from file names).
A material is looked up by the instance's name, then as <name>_mod: swap_mod_mesh.py packages (a CNS outfit such as
Vindictus Demon Maiden, its own mesh in a copy of a game outfit's package) name the materials built from the mod's maps
so, and their PMX carries the same names.
More outfits come from the registry _meta\hq_materials\mod_outfits.json (2026-11-15: 48 looks of 12 mods; REGISTRY):
their variant's files are hardlinked from the archived mod sources and named as patches (a replacer at the game's own
path otherwise loses to the game's package at random), the mesh's slots may name the game's own instances (read too),
the textures the archived package lacks are exported into textures\extra (fetch_textures()), and a CNS outfit's default
texture options replace the flattened chain's (apply_overrides()).
The archived .blend is only read (fetched maps are added to its textures\extra).  The add-on picks the HQ .blend that holds most of a PMX's materials (per layer for
a pmx_layers.py model), so the Reika and Vindictus Fiona PMX take every material from their own HQ .blend and the
nude layer from the nude's; the Cooling Suit and the other Eve PMX keep theirs (a tie goes to the first folder in
name order: Eve before Fiona).
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
ARCHIVE = r"E:\game_export\StellarBlade"
DATA = os.path.join(ARCHIVE, "_meta", "hq_materials")
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
CUE4PARSE = r"E:\tools\cue4parse_cli\cue4parse.exe"
PAKS = r"D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks"
USMAP = os.path.join(ARCHIVE, "_meta", "mappings", "StellarBlade_1.1.0.usmap")
# Windows' own bsdtar reads .rar (RAR5) too; a GNU tar first in PATH (Git Bash) takes "E:" for a remote host
TAR = r"C:\Windows\System32\tar.exe" if os.path.isfile(r"C:\Windows\System32\tar.exe") else shutil.which("tar")
HEAD = "MI_EVE_Head_V02"          # Eve's face material in every outfit .blend: the skin's subsurface comes from it
MOD_SOURCES = os.path.join(ARCHIVE, "_meta", "mod_sources")
# more outfits, one JSON entry per package folder (2026-11-15: the 48 looks of 12 mods - Nikke Plus, Cake Unveiled,
# Crimson Wings BBB / OP, ...): same keys as OUTFITS plus "files" (groups of the variant's .pak / .utoc / .ucas under
# MOD_SOURCES, each group hardlinked into its own folder next to the game's Paks) and "any_mount" (the mod's packages
# sit under any mount name - SB_CNS/Content, CNS_CWings/Content ... - so /Game/<path> is looked up as */Content/<path>)
REGISTRY = os.path.join(DATA, "mod_outfits.json")
# package folder -> character, the mod's content folder, the outfit's skeletal mesh (its material slots); "packages":
# what to read first when the folder is the game's own (default: the whole folder); "slots": only these (the barefoot
# variant's mesh keeps empty heels / pubic-hair slots); "archive" + "member": a mod that is not installed, read from
# the folder of its download archive holding the variant's .pak / .utoc / .ucas
OUTFITS = {
    "Mod_GantzReika_A": {"character": "Reika", "mod": "SB/Content/OutfitMods/GantzReika", "mesh": "GantzReika_A"},
    "Mod_GantzReika_B": {"character": "Reika", "mod": "SB/Content/OutfitMods/GantzReika", "mesh": "GantzReika_B"},
    # Nexus 1145 "Vindictus Fiona": mounted at test/Content (an io store mod's mount name is free); its mesh replaces
    # the Planet Diving Suit 7th (CH_P_EVE_09) and its instances sit in the 09 / 16 / 21 folders; .uasset only, as for
    # the nude below (a texture's .ubulk exported in parallel to the same JSON)
    "Mod_VindictusFiona": {"character": "Fiona", "mod": "test/Content", "packages": ["test/Content/*.uasset"],
                           "mesh": "CH_P_EVE_09"},
    # Nexus 1807 "Vindictus - Demon Maiden" (AlomX), a CNS outfit: its own mesh on the CH_P_EVE_01 skeleton, not
    # installed - read from the copy of its zip (the files at the zip's root) kept with the archive's mod sources
    "Mod_VindictusDemonMaiden": {
        "character": "Eve", "mod": "SB/Content/OutfitMods/VindictusDemonMaidenOutfit",
        "packages": ["SB/Content/OutfitMods/VindictusDemonMaidenOutfit/*.uasset"], "mesh": "CH_P_EVE_DemonMaiden",
        "archive": ARCHIVE + r"\_meta\mod_sources\DemonMaiden\Vindictus - DemonMaiden - Outfit-1807-1-0-1754919465.zip"},
    "Nude_Barefoot": {"character": "Eve", "mod": "SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit",
                      # .uasset, not .*: the game's own .ubulk of the mesh would be exported to the same JSON in
                      # parallel (CUE4Parse crashes on the locked file)
                      "packages": ["SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit/SkinEve.uasset",
                                   "SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit/CH_P_EVE_InnerSuit.uasset"],
                      "mesh": "CH_P_EVE_InnerSuit", "slots": ["SkinEve"],
                      "archive": r"E:\tools\setup\mods\EveOriginalProportions-30-2-1-1750283806.rar",
                      "member": "Barefoot"},
}


def log(msg):
    print("[hq_mod_outfits] " + msg, flush=True)


# --- reading the game ------------------------------------------------------------------------------------------------
def quoted(ref):
    return ref.split("'")[1] if "'" in ref else ref


def parent_of(export):
    return quoted(((export.get("Properties") or {}).get("Parent") or {}).get("ObjectName", ""))


def package_glob(object_path, any_mount=False):
    """/Game/Art/X/MI_Y.0 -> SB/Content/Art/X/MI_Y.* (CUE4Parse wants a wildcard for a single package); any_mount:
    */Content/Art/X/MI_Y.* - a mod mounted under its own name keeps its packages at /Game/<path> for the game"""
    path = object_path.split(".")[0]
    if path.startswith("/Game/"):
        path = ("*/Content/" if any_mount else "SB/Content/") + path[len("/Game/"):]
    return path + ".*"


def cue4parse(patterns, out_dir, paks, fmt="json"):
    cmd = [CUE4PARSE, "-i", paks, "-g", "GAME_UE4_26", "-m", USMAP, "-f", fmt, "-y", "-o", out_dir]
    for p in patterns:
        cmd += ["-p", p]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("cue4parse failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])


def mod_paks(entry, paks, work):
    """the Paks folder CUE4Parse reads for this outfit: the game's own (an installed mod sits in its ~mods), or for a
    mod that is not installed a folder in `work` with the variant's files from its archive and a junction to the
    game's Paks (the mod's instances name game parents).  Without a "member" the mod's files sit at the archive's root
    (Vindictus Demon Maiden's zip) and are unpacked into <work>/Paks/mod.  Returns (folder, junction or None)."""
    if entry.get("files"):
        # the variant's own files (archived mod sources), each group in its own folder: a pack's other variants
        # (another Crimson Wings mesh at the same path, an add-on that hides parts) stay out
        folder = os.path.join(work, "Paks")
        for k, group in enumerate(entry["files"]):
            sub = os.path.join(folder, "m%d" % k)
            os.makedirs(sub)
            for f in group:
                src = f if os.path.isabs(f) else os.path.join(MOD_SOURCES, f)
                stem, ext = os.path.splitext(os.path.basename(src))
                # named as a patch: CUE4Parse mounts in parallel and keeps the higher read order between two
                # containers holding the same package path ("_P" ranks above the game's pakchunks; with equal
                # orders the winner is random - a replacer such as Revealing Crimson Wings' CH_P_EVE_39 came out
                # as the game's own mesh in 2 runs of 3)
                name = stem + ext if stem.lower().endswith("_p") else stem + "_P" + ext
                os.link(src, os.path.join(sub, name))      # the work folder sits on the sources' drive
        link = os.path.join(folder, "game")
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, paks], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit("mklink /J failed: " + r.stdout + r.stderr)
        return folder, link
    if not entry.get("archive"):
        return paks, None
    folder = os.path.join(work, "Paks")
    member = entry.get("member")
    sub = os.path.join(folder, member or "mod")
    os.makedirs(folder)
    if not member:
        os.makedirs(sub)
    r = subprocess.run([TAR, "-xf", entry["archive"], "-C"] + ([folder, member] if member else [sub]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    found = glob.glob(os.path.join(sub, "*.utoc")) + glob.glob(os.path.join(sub, "*.pak"))
    if r.returncode != 0 or not found:
        raise SystemExit("could not unpack %s from %s:\n%s" % (member or "the mod's files", entry["archive"],
                                                               r.stdout + r.stderr))
    link = os.path.join(folder, "game")
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, paks], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise SystemExit("mklink /J failed: " + r.stdout + r.stderr)
    return folder, link


def index_json(root):
    """name -> export, for every material instance, material and skeletal mesh under root"""
    out = {}
    for f in glob.glob(os.path.join(root, "**", "*.json"), recursive=True):
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
        except ValueError:
            continue
        for e in data if isinstance(data, list) else []:
            t = e.get("Type", "")
            if t.startswith("MaterialInstance") or t in ("Material", "SkeletalMesh"):
                out.setdefault(e["Name"], e)
    return out


def read_game(patterns, json_dir, paks, any_mount=False):
    """the mod's packages' JSON plus every parent instance / master they name; any_mount: also the instances the
    skeletal mesh names that are not the mod's (a replacer keeps the game's own, e.g. Crimson Wings' UV1 / UV2)"""
    cue4parse(patterns, json_dir, paks)
    asked = set()
    for _level in range(8):
        mats = index_json(json_dir)
        refs = []
        for e in mats.values():
            t = e.get("Type", "")
            if t.startswith("MaterialInstance"):
                p = (e.get("Properties") or {}).get("Parent") or {}
                refs.append((quoted(p.get("ObjectName", "")), p.get("ObjectPath", "")))
            elif t == "SkeletalMesh" and any_mount:
                for s in e.get("SkeletalMaterials") or []:
                    m = s.get("Material") or {}
                    refs.append((quoted(m.get("ObjectName", "")), m.get("ObjectPath", "")))
        wanted = []
        for name, ref in refs:
            if ref and name not in mats and ref not in asked:
                asked.add(ref)
                wanted.append(package_glob(ref, any_mount))
        if not wanted:
            return mats
        cue4parse(wanted, json_dir, paks)
    return index_json(json_dir)


def fetch_textures(staged_list, tex_dir, paks, any_mount):
    """textures the flattened instances name that the outfit folder lacks (a replacer's game instances whose maps the
    archived package never exported, a mod map no slot of swap_mod_mesh.py used) -> PNG in textures\\extra.  One
    CUE4Parse call per texture, .uasset only (its .ubulk in parallel would write the same file); a texture CUE4Parse
    cannot find is listed, not fatal.  Returns (fetched, not found)."""
    have = set()
    for sub in ("", "extra", "mod"):
        d = os.path.join(tex_dir, sub)
        if os.path.isdir(d):
            have |= {os.path.splitext(f)[0].lower() for f in os.listdir(d) if f.lower().endswith(".png")}
    want = {}
    for staged in staged_list:
        for t in staged[0]["Properties"]["TextureParameterValues"]:
            n = texture_name(t["ParameterValue"])
            if n.lower() not in have:
                want.setdefault(n, t["ParameterValue"]["ObjectPath"])
    got, missing = [], []
    if not want:
        return got, missing
    extra = os.path.join(tex_dir, "extra")
    os.makedirs(extra, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="hq_tex_")
    try:
        for n, op in sorted(want.items()):
            try:
                cue4parse([package_glob(op, any_mount)[:-2] + ".uasset"], tmp, paks, fmt="png")
            except SystemExit:
                pass
            hits = glob.glob(os.path.join(tmp, "**", n + ".png"), recursive=True)
            if hits:
                shutil.copy2(hits[0], os.path.join(extra, n + ".png"))
                got.append(n)
            else:
                missing.append(n)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return got, missing


def master_defaults(master):
    """{"scalars", "vectors"} a master material gives what no instance sets (CachedExpressionData: names in
    ParameterInfos, values in the same order)"""
    params = ((master.get("Properties") or {}).get("CachedExpressionData") or {}).get("Parameters") or {}
    out = {"scalars": {}, "vectors": {}}
    for kind, entries, values in (("scalars", "RuntimeEntries", "ScalarValues"),
                                  ("vectors", "RuntimeEntries[1]", "VectorValues")):
        names = [p.get("Name") for p in (params.get(entries) or {}).get("ParameterInfos") or []]
        for n, v in zip(names, params.get(values) or []):
            out[kind][n] = v
    return out


def flatten(name, mats):
    """(staged CUE4Parse-style export, notes) of one instance with its parents' and master's values merged in"""
    chain, e = [], mats.get(name)
    while e is not None and len(chain) < 10:
        chain.append(e)
        if not e.get("Type", "").startswith("MaterialInstance"):
            break
        e = mats.get(parent_of(e))
    insts = [c for c in chain if c.get("Type", "").startswith("MaterialInstance")]
    master = chain[-1] if chain and chain[-1].get("Type") == "Material" else None
    if not insts:
        return None, {}
    defaults = master_defaults(master) if master is not None else {"scalars": {}, "vectors": {}}
    scalars, vectors, textures, switches, overrides = {}, {}, {}, {}, {}
    spelling = {}

    def put(store, name, value):
        # parameter names are FNames, which UE compares without case: the Vindictus Fiona shoes set "BaseColor"
        # over their parent's "Basecolor" - one parameter, kept under the master side's spelling
        store[spelling.setdefault((id(store), name.lower()), name)] = value

    for k, v in defaults["scalars"].items():
        put(scalars, k, v)
    for k, v in defaults["vectors"].items():
        put(vectors, k, v)
    for inst in reversed(insts):                           # master side first: the child's value wins
        p = inst.get("Properties") or {}
        for s in p.get("ScalarParameterValues") or []:
            put(scalars, s["ParameterInfo"]["Name"], s["ParameterValue"])
        for s in p.get("VectorParameterValues") or []:
            put(vectors, s["ParameterInfo"]["Name"], s["ParameterValue"])
        for s in p.get("TextureParameterValues") or []:
            if (s.get("ParameterValue") or {}).get("ObjectPath"):
                put(textures, s["ParameterInfo"]["Name"], s["ParameterValue"])
        for s in (p.get("StaticParameters") or {}).get("StaticSwitchParameters") or []:
            put(switches, s["ParameterInfo"]["Name"], s["Value"])
        overrides.update(p.get("BasePropertyOverrides") or {})
    master_name = master["Name"] if master is not None else parent_of(insts[-1])
    notes = {"chain": [c["Name"] for c in chain], "master": master_name,
             "blend": (overrides.get("BlendMode") or ((master or {}).get("Properties") or {}).get("BlendMode")
                       or "EBlendMode::BLEND_Opaque").split("::")[-1]}

    def rgb(v):
        return max(v.get("R", 0.0), v.get("G", 0.0), v.get("B", 0.0)) if isinstance(v, dict) else 0.0

    standard_on = scalars.get("EmissivePower", 0.0) > 0 and rgb(vectors.get("EmissiveColor")) > 0
    if switches.get("UseGlowEmissive") and "Emissive" in textures and not standard_on \
            and rgb(vectors.get("ML_GlowEm_EyeCoreHDRTint")) > 0:
        vectors["EmissiveColor"] = vectors["ML_GlowEm_EyeCoreHDRTint"]
        vectors["Emissive_CH"] = vectors.get("ML_GlowEmissive_CH") or {"R": 1.0, "G": 0.0, "B": 0.0, "A": 0.0}
        scalars["EmissivePower"] = 1.0
        notes["glow"] = {"color": vectors["EmissiveColor"], "channel": vectors["Emissive_CH"]}
    if master_name.startswith("MA_Skin"):
        notes["skin"] = True

    def info(n):
        return {"Name": n, "Association": "EMaterialParameterAssociation::GlobalParameter", "Index": -1}

    props = {
        "Parent": {"ObjectName": "Material'%s'" % master_name,
                   "ObjectPath": (master or {}).get("Package", "/Game/" + master_name) + "." + master_name},
        "ScalarParameterValues": [{"ParameterInfo": info(k), "ParameterValue": v} for k, v in sorted(scalars.items())],
        "VectorParameterValues": [{"ParameterInfo": info(k), "ParameterValue": v} for k, v in sorted(vectors.items())],
        "TextureParameterValues": [{"ParameterInfo": info(k), "ParameterValue": v} for k, v in sorted(textures.items())],
        "StaticParameters": {"StaticSwitchParameters": [{"ParameterInfo": info(k), "Value": v}
                                                        for k, v in sorted(switches.items())]},
        "BasePropertyOverrides": overrides,
    }
    return [{"Type": insts[0]["Type"], "Name": name, "Properties": props}], notes


def texture_name(value):
    return value["ObjectPath"].split("/")[-1].split(".")[0]


def apply_overrides(staged, overrides, note):
    """a CNS outfit's default texture options ({parameter: /Game/... texture}, the .dekcns.json TextureOptions at
    their Value): CNS sets them on the slot's material at run time, so they win over the flattened chain"""
    tex = staged[0]["Properties"]["TextureParameterValues"]
    for param, path in overrides.items():
        obj = {"ObjectName": "Texture2D'%s'" % path.split(".")[-1], "ObjectPath": path.split(".")[0] + ".0"}
        hit = next((t for t in tex if t["ParameterInfo"]["Name"].lower() == param.lower()), None)
        if hit is not None:
            hit["ParameterValue"] = obj
        else:
            tex.append({"ParameterInfo": {"Name": param, "Association": "EMaterialParameterAssociation::GlobalParameter",
                                          "Index": -1}, "ParameterValue": obj})
    note["cns_textures"] = overrides


def skin_record(staged, tex_dir):
    """what --post wires for a skin instance (flattened values; maps as files in the outfit's textures)"""
    p = staged[0]["Properties"]
    s = {x["ParameterInfo"]["Name"]: x["ParameterValue"] for x in p["ScalarParameterValues"]}
    t = {x["ParameterInfo"]["Name"]: texture_name(x["ParameterValue"]) for x in p["TextureParameterValues"]}

    def find(key):
        name = t.get(key)
        if not name:
            return None
        for sub in ("", "extra", "mod"):            # mod\: the mod's own maps, as swap_mod_mesh.py copies them
            path = os.path.join(tex_dir, sub, name + ".png")
            if os.path.isfile(path):
                return path
        return "MISSING:" + name

    objects = {x["ParameterInfo"]["Name"]: x["ParameterValue"]["ObjectPath"] for x in p["TextureParameterValues"]}
    return {"base": find("BaseColor"), "normal": find("BaseNormal"), "orss": find("ORSS Mask"),
            "orss_object": objects.get("ORSS Mask"),
            "roughness_min": s.get("MinRoughness", 0.2), "roughness_max": s.get("MaxRoughness", 1.0),
            "specular": s.get("BaseSpecularValue", 0.4), "normal_strength": s.get("NormalStrength", 1.0),
            "not_wired": {k: t[k] for k in t if k not in ("BaseColor", "BaseNormal", "ORSS Mask")},
            "values": {k: s[k] for k in ("BaseSSS", "GlobalRoughness", "FresnelRoughness", "Detail Tiling",
                                         "Detail Strength") if k in s}}


def orss_mean(object_path, data, paks):
    """[R, G, B, A] means (0-1) of a game texture over its drawn texels (any RGB above 2/255: the UV islands, not the
    black padding).  A mod skin that keeps its parent's ORSS mask gets a mask painted for ANOTHER body's UV layout
    (Vindictus Fiona's skin inherits Eve's CH_P_EVE_BB_V01_ORSS, laid out for Eve's body): wired the way the game does
    it, Eve's creases, nipples and black gaps would land at random on the new body, so --post sets the means as
    constants.  The texture is exported once into <data>\\orss\\."""
    import numpy as np
    from PIL import Image
    out = os.path.join(data, "orss")
    os.makedirs(out, exist_ok=True)
    path = object_path.split(".")[0]
    if path.startswith("/Game/"):
        path = "SB/Content/" + path[len("/Game/"):]
    name = os.path.basename(path)
    hits = glob.glob(os.path.join(out, "**", name + ".png"), recursive=True)
    if not hits:
        cue4parse([path + ".uasset"], out, paks, fmt="png")        # .uasset: not its .ubulk in parallel
        hits = glob.glob(os.path.join(out, "**", name + ".png"), recursive=True)
    if not hits:
        return None, None
    Image.MAX_IMAGE_PIXELS = None
    a = np.asarray(Image.open(hits[0]).convert("RGBA"), dtype=np.float32) / 255.0
    drawn = a[..., :3].max(-1) > 2.0 / 255.0
    return [round(float(x), 4) for x in a[drawn].mean(0)], hits[0]


LAYOUT_R = 0.5          # the mod's skin normal map against its parent's: same UV layout above this correlation


def layout_kept(normal_png, parent_normal_object, data, paks):
    """Correlation (-1..1) of the mod skin's BaseNormal with its parent's, both shrunk to 256 px (x / y slopes): a
    body that keeps its parent's UV layout keeps its relief where the parent has it, so the parent's ORSS mask fits it.
    Measured: Vindictus Demon Maiden (Eve's BaseBody V02_F1 repainted, CH_EVE_BaseBody_V02_F1_N_Rav against the game's
    _N) 0.92; Vindictus Fiona's four skins (Fiona's own body against Eve's) -0.01 to 0.01.  The parent's map is
    exported into <data>\\orss\\ next to the mask.  None when a map is missing."""
    import numpy as np
    from PIL import Image
    if not normal_png or not os.path.isfile(normal_png) or not parent_normal_object:
        return None
    out = os.path.join(data, "orss")
    path = package_glob(parent_normal_object)[:-2]
    name = os.path.basename(path)
    hits = glob.glob(os.path.join(out, "**", name + ".png"), recursive=True)
    if not hits:
        cue4parse([path + ".uasset"], out, paks, fmt="png")
        hits = glob.glob(os.path.join(out, "**", name + ".png"), recursive=True)
    if not hits:
        return None
    Image.MAX_IMAGE_PIXELS = None

    def slopes(p):
        a = np.asarray(Image.open(p).convert("RGB").resize((256, 256), Image.BOX), dtype=np.float32) / 255.0
        v = (a[..., :2] - 0.5).reshape(-1)
        return v - v.mean()
    a, b = slopes(normal_png), slopes(hits[0])
    return round(float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12)), 3)


def parent_texture(chain, mats, param):
    """the object path of a texture parameter as the first instance above the mod's sets it (None if none does)"""
    for name in chain[1:]:
        props = (mats.get(name) or {}).get("Properties") or {}
        for t in props.get("TextureParameterValues") or []:
            if t["ParameterInfo"]["Name"].lower() == param.lower() and t.get("ParameterValue"):
                return t["ParameterValue"]["ObjectPath"]
    return None


GREEN_RATIO = 1.4       # OpenGL only when its curl is this many times smaller than DirectX's


def normal_convention(path, size=2048):
    """("DirectX" | "OpenGL", {convention: curl}) of a tangent-space normal map.  A map made from a height field is
    integrable - its gradient field has no curl - only when read with its own green direction.  UE's maps are DirectX,
    and so is every map the SB HQ wiring unpacks; a mod can ship one the other way (Vindictus Fiona's dress
    PCF_005_Onepiece_N: green flipped against the Vindictus original and the outfit's three other maps, so the game
    lights its relief upside down).  Texture space: column ~ u, row ~ 1 - v, n ~ (-dh/du, -dh/dv, 1); measured inside
    the islands (away from their borders) where the map has detail."""
    import numpy as np
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path).convert("RGB")
    if im.size != (size, size):
        im = im.resize((size, size), Image.BILINEAR)
    a = np.asarray(im, dtype=np.float64) / 255.0
    nx, g, nz = a[..., 0] * 2 - 1, a[..., 1] * 2 - 1, a[..., 2] * 2 - 1
    valid = nz > 0.35
    inner = valid.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            inner &= np.roll(np.roll(valid, dy, 0), dx, 1)
    nz = np.where(valid, nz, 1.0)
    fc = -nx / nz
    d_fc_dr = (np.roll(fc, -1, 0) - np.roll(fc, 1, 0)) / 2
    d_g_dc = (np.roll(g / nz, -1, 1) - np.roll(g / nz, 1, 1)) / 2
    detail = (np.abs(d_fc_dr) + np.abs(d_g_dc))[inner]
    if not detail.size:
        return "DirectX", {}
    keep = detail > np.percentile(detail, 50)
    curls = {}
    for name, sign in (("OpenGL", 1.0), ("DirectX", -1.0)):          # dh/dr = +g/nz (OpenGL), -g/nz (DirectX)
        curls[name] = round(float(np.abs(d_fc_dr - sign * d_g_dc)[inner][keep].mean()), 5)
    return ("OpenGL" if curls["OpenGL"] * GREEN_RATIO < curls["DirectX"] else "DirectX"), curls


def run_outfit(package, args):
    entry = OUTFITS[package]
    mod_dir, mesh_name = entry["mod"], entry["mesh"]
    folder = os.path.join(ARCHIVE, entry["character"], "blend", package)
    blends = [f for f in os.listdir(folder) if f.endswith(".blend") and not f.endswith("_HQ.blend")]
    if len(blends) != 1:
        raise SystemExit("%s: expected one archived .blend, found %s" % (folder, blends))
    blend = os.path.join(folder, blends[0])
    label = os.path.splitext(blends[0])[0]
    hq_blend = os.path.join(folder, label + "_HQ.blend")
    data = os.path.join(DATA, package)
    json_dir, staged_dir = os.path.join(data, "mi_json"), os.path.join(data, "staged")
    shutil.rmtree(staged_dir, ignore_errors=True)
    os.makedirs(staged_dir)
    any_mount = bool(entry.get("any_mount"))
    tex_dir = os.path.join(folder, "textures")
    work_root = None
    if entry.get("files"):              # hardlinks of the archived mod sources: the work folder on their drive
        work_root = os.path.join(DATA, "_work")
        os.makedirs(work_root, exist_ok=True)
    work = tempfile.mkdtemp(prefix="hq_mod_", dir=work_root)
    flat = {}
    try:
        paks, _link = mod_paks(entry, args.paks, work)
        mats = read_game(entry.get("packages") or [mod_dir + "/*"], json_dir, paks, any_mount)
        mesh = mats.get(mesh_name)
        if mesh is None:
            raise SystemExit("%s: skeletal mesh %s not in the mod's JSON" % (package, mesh_name))
        used = []
        for slot in mesh.get("SkeletalMaterials") or []:
            name = quoted((slot.get("Material") or {}).get("ObjectName", ""))
            if name and name not in used and (not entry.get("slots") or name in entry["slots"]):
                used.append(name)
        for name in used:
            flat[name] = flatten(name, mats)
            if flat[name][0] is not None and name in (entry.get("overrides") or {}):
                apply_overrides(flat[name][0], entry["overrides"][name], flat[name][1])
        # one instance on two slots with different CNS options: the .blend has a copy per extra slot
        # (<material>__slot<n>), flattened from the same instance under that name with its own options
        for mname, sm in (entry.get("slot_materials") or {}).items():
            staged, note = flatten(sm["instance"], mats)
            if staged is None:
                continue
            staged = json.loads(json.dumps(staged))
            staged[0]["Name"] = mname
            note = dict(note, slot_copy_of=sm["instance"])
            apply_overrides(staged, sm.get("overrides") or {}, note)
            flat[mname] = (staged, note)
            used.append(mname)
        if any_mount:
            got, missing = fetch_textures([s for s, _n in flat.values() if s is not None], tex_dir, paks, True)
            if got or missing:
                log("%s textures from the game / mod into textures\\extra: %d%s" % (
                    package, len(got), ("; not found: " + ", ".join(missing)) if missing else ""))
    finally:
        link = os.path.join(work, "Paks", "game")
        if os.path.lexists(link):
            os.rmdir(link)                          # the junction only - never the game's Paks it points to
        shutil.rmtree(work, ignore_errors=True)
    notes, skins = {}, {}
    for name in used:
        staged, note = flat[name]
        if staged is None:
            notes[name] = {"error": "not a material instance in the JSON"}
            continue
        notes[name] = note
        if note.get("skin"):
            skins[name] = skin_record(staged, tex_dir)
            skins[name]["chain"] = note["chain"]
            skins[name]["blend"] = note["blend"]
            obj = skins[name].get("orss_object")
            if obj and (skins[name]["orss"] or "").startswith("MISSING:"):
                skins[name]["orss_mean"], png = orss_mean(obj, data, args.paks)
                r = layout_kept(skins[name]["normal"], parent_texture(note["chain"], mats, "BaseNormal"), data,
                                args.paks)
                skins[name]["layout_r"] = r
                if png and r is not None and r >= LAYOUT_R:
                    skins[name]["orss_parent"] = png      # same body: --post wires the parent's mask itself
                log("%s %-12s parent's ORSS mask: normal correlation with the parent %s -> %s" % (
                    package, name, r, "the mask itself" if skins[name].get("orss_parent") else "its means"))
            continue
        fname = name if name.startswith("MI_") else "MI_" + name        # hq_materials.py globs MI_*.json
        json.dump(staged, open(os.path.join(staged_dir, fname + ".json"), "w", encoding="utf-8"), indent=1)
    json.dump(skins, open(os.path.join(data, "skin.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(notes, open(os.path.join(data, "chains.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for name, note in notes.items():
        log("%s %-12s %s%s%s" % (package, name, " -> ".join(note.get("chain", [])), "  [glow]" if "glow" in note else "",
                                 "  [skin]" if note.get("skin") else ""))
    text = []
    tex_args = ["--textures", tex_dir]
    if os.path.isdir(os.path.join(tex_dir, "mod")):      # a swap_mod_mesh.py package keeps the mod's maps there
        tex_args += ["--textures", os.path.join(tex_dir, "mod")]
    r1 = subprocess.run([sys.executable, os.path.join(HERE, "hq_materials.py"), "--mi-json", staged_dir] + tex_args +
                        ["--out", data], capture_output=True, text=True, encoding="utf-8", errors="replace")
    text.append("== hq_materials.py\n" + r1.stdout + r1.stderr)
    if r1.returncode != 0:
        raise SystemExit("hq_materials.py failed:\n" + text[-1])
    doc = json.load(open(os.path.join(data, "materials.json"), encoding="utf-8"))
    normals, tested = {}, {}
    for name, path in [(n, (d.get("textures") or {}).get("normal")) for n, d in doc["materials"].items()] + \
            [(n, d.get("normal")) for n, d in skins.items()]:
        if not path or path.startswith("MISSING") or not os.path.isfile(path):
            continue
        if path not in tested:
            tested[path] = normal_convention(path)
        conv, curls = tested[path]
        normals[name] = {"texture": path, "convention": conv, "curl": curls}
        if conv == "OpenGL":
            log("%s %-12s %s: green the OpenGL way (curl %.4f, DirectX %.4f) -> unpacked so" % (
                package, name, os.path.basename(path), curls["OpenGL"], curls["DirectX"]))
    json.dump(normals, open(os.path.join(data, "normals.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r2 = subprocess.run([BLENDER, "-b", "--factory-startup", blend, "--python",
                         os.path.join(HERE, "hq_materials_blender.py"), "--", "--materials",
                         os.path.join(data, "materials.json"), "--save", hq_blend],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    text.append("== hq_materials_blender.py\n" + r2.stdout[-20000:] + r2.stderr[-5000:])
    if r2.returncode != 0 or "SB_HQ_MATERIALS=" not in r2.stdout:
        raise SystemExit("hq_materials_blender.py failed:\n" + text[-1])
    r3 = subprocess.run([BLENDER, "-b", "--factory-startup", hq_blend, "--python", os.path.abspath(__file__), "--",
                         "--post", data], capture_output=True, text=True, encoding="utf-8", errors="replace")
    text.append("== hq_mod_outfits.py --post\n" + r3.stdout[-20000:] + r3.stderr[-5000:])
    if r3.returncode != 0 or "SB_MOD_POST=" not in r3.stdout:
        raise SystemExit("--post failed:\n" + text[-1])
    open(os.path.join(data, "hq_log.txt"), "w", encoding="utf-8").write("\n".join(text))
    post = json.loads(r3.stdout.split("SB_MOD_POST=", 1)[1].splitlines()[0])
    log("%s -> %s" % (package, hq_blend))
    for k, v in sorted(post["materials"].items()):
        log("    %-28s %s" % (k, v))
    return hq_blend


# --- inside Blender: skin wiring + pruning --------------------------------------------------------------------------------
def prune(mat):
    """drop the nodes that feed no output"""
    tree = mat.node_tree
    live, stack = set(), [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"]
    while stack:
        n = stack.pop()
        if n.name in live:
            continue
        live.add(n.name)
        for sock in n.inputs:
            for link in sock.links:
                stack.append(link.from_node)
    dead = [n for n in tree.nodes if n.name not in live and n.type != "FRAME"]
    for n in dead:
        tree.nodes.remove(n)
    return len(dead)


def wire_skin(mat, d, head):
    import hq_materials_blender as hb
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    p = hb.principled(mat)
    if p is None:
        return "no Principled BSDF"
    for sock in ("Roughness", "Specular", "Normal", "Metallic", "Subsurface"):
        for link in list(p.inputs[sock].links):
            links.remove(link)
    done = []
    x0, y = p.location.x - 1500, p.location.y
    orss = d["orss"] if d["orss"] and not d["orss"].startswith("MISSING") else None
    copy_to = None
    if orss is None and d.get("orss_parent") and os.path.isfile(d["orss_parent"]):
        import bpy
        orss = d["orss_parent"]         # the parent's mask on the parent's own UV layout (layout_kept())
        # copied next to the outfit's other maps: the .blend folder stays self-contained
        copy_to = os.path.join(os.path.dirname(bpy.data.filepath), "textures", "extra")
        done.append("parent's ORSS %s (same UV layout: normal r=%s)" % (os.path.basename(orss), d.get("layout_r")))
    if orss:
        n = nodes.new("ShaderNodeTexImage")
        n.image = hb.image(orss, True, copy_to)
        n.location = (x0, y - 300)
        sep = nodes.new("ShaderNodeSeparateRGB")
        sep.location = (x0 + 300, y - 300)
        links.new(n.outputs["Color"], sep.inputs["Image"])
        rng = nodes.new("ShaderNodeMapRange")
        rng.location = (x0 + 500, y - 260)
        rng.inputs["To Min"].default_value = d["roughness_min"]
        rng.inputs["To Max"].default_value = d["roughness_max"]
        links.new(sep.outputs["G"], rng.inputs["Value"])
        links.new(rng.outputs["Result"], p.inputs["Roughness"])
        spec = nodes.new("ShaderNodeMath")
        spec.operation = "MULTIPLY"
        spec.use_clamp = True
        spec.location = (x0 + 500, y - 460)
        spec.inputs[1].default_value = d["specular"]
        links.new(sep.outputs["B"], spec.inputs[0])
        links.new(spec.outputs[0], p.inputs["Specular"])
        done.append("orss (roughness %.3f-%.3f, specular x%g)" % (d["roughness_min"], d["roughness_max"], d["specular"]))
    elif d.get("orss_mean"):
        # the mask belongs to another UV layout (orss_mean()): its means, through the same ranges
        g, b = d["orss_mean"][1], d["orss_mean"][2]
        rough = max(0.0, min(1.0, d["roughness_min"] + g * (d["roughness_max"] - d["roughness_min"])))
        spec = max(0.0, min(1.0, b * d["specular"]))
        p.inputs["Roughness"].default_value = rough
        p.inputs["Specular"].default_value = spec
        done.append("orss of another UV layout -> constants (roughness %.3f, specular %.3f)" % (rough, spec))
    p.inputs["Metallic"].default_value = 0.0
    if d.get("blend", "BLEND_Opaque") == "BLEND_Opaque" and (p.inputs["Alpha"].is_linked or mat.blend_method != "OPAQUE"):
        # opaque in the game: the archive wired the base colour's alpha (Vindictus Fiona's T_PCF_Hand01_D /
        # T_PCF_Lower01_D: UV coverage, 0 only in the padding) and blended the skin with hashed alpha
        for link in list(p.inputs["Alpha"].links):
            links.remove(link)
        p.inputs["Alpha"].default_value = 1.0
        mat.blend_method = "OPAQUE"
        mat.shadow_method = "OPAQUE"
        done.append("opaque as its master")
    if d["normal"] and not d["normal"].startswith("MISSING"):
        n = nodes.new("ShaderNodeTexImage")
        n.image = hb.image(d["normal"], True)
        n.location = (x0, y - 900)
        v = hb.unpack_normal(nodes, links, n, x0 + 300)
        nrm = nodes.new("ShaderNodeVectorMath")
        nrm.operation = "NORMALIZE"
        nrm.location = (x0 + 700, y - 900)
        links.new(v, nrm.inputs[0])
        col = nodes.new("ShaderNodeVectorMath")
        col.operation = "MULTIPLY_ADD"
        col.location = (x0 + 880, y - 900)
        links.new(nrm.outputs["Vector"], col.inputs[0])
        col.inputs[1].default_value = (0.5, 0.5, 0.5)
        col.inputs[2].default_value = (0.5, 0.5, 0.5)
        nm = nodes.new("ShaderNodeNormalMap")
        nm.location = (x0 + 1060, y - 900)
        nm.inputs["Strength"].default_value = d["normal_strength"]
        links.new(col.outputs["Vector"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], p.inputs["Normal"])
        done.append("normal")
    hp = hb.principled(head) if head is not None else None
    if hp is not None:
        p.subsurface_method = hp.subsurface_method
        for sock in ("Subsurface", "Subsurface Radius", "Subsurface Color", "Subsurface IOR", "Subsurface Anisotropy"):
            if sock in hp.inputs and sock in p.inputs and not hp.inputs[sock].is_linked:
                p.inputs[sock].default_value = hp.inputs[sock].default_value
        done.append("subsurface as %s (%.3f)" % (head.name, hp.inputs["Subsurface"].default_value))
    mat["sb_hq_materials"] = ", ".join(done)
    return ", ".join(done)


def flip_green(mat, image_name):
    """read the normal map image_name with OpenGL green: the unpack (hq_materials_blender.unpack_normal) is SeparateRGB
    -> MULTIPLY_ADD per channel, green x-2 +1 for DirectX; x2 -1 reads it the other way.  Returns the nodes turned."""
    import bpy
    turned = 0
    for n in mat.node_tree.nodes:
        img = getattr(n, "image", None)
        if n.type != "TEX_IMAGE" or img is None or image_name.lower() not in (
                img.name.lower(), os.path.basename(bpy.path.abspath(img.filepath)).lower()):
            continue
        for link in n.outputs["Color"].links:
            if link.to_node.type != "SEPRGB":
                continue
            for l2 in link.to_node.outputs["G"].links:
                m = l2.to_node
                if m.type == "MATH" and m.operation == "MULTIPLY_ADD" and m.inputs[1].default_value < 0:
                    m.inputs[1].default_value, m.inputs[2].default_value = 2.0, -1.0
                    turned += 1
    return turned


def post(data):
    import bpy
    sys.path.insert(0, HERE)
    doc = json.load(open(os.path.join(data, "materials.json"), encoding="utf-8"))
    skins = json.load(open(os.path.join(data, "skin.json"), encoding="utf-8"))
    path = os.path.join(data, "normals.json")
    normals = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else {}
    head = bpy.data.materials.get(HEAD)

    def material(name):
        """the instance's material: its name, or <name>_mod (swap_mod_mesh.py's packages, as in hq_materials_blender)"""
        for n in (name, name + "_mod"):
            mat = bpy.data.materials.get(n)
            if mat is not None and mat.use_nodes:
                return mat
        return None

    report = {}
    for name, d in skins.items():
        mat = material(name)
        report[name] = wire_skin(mat, d, head) if mat is not None else "not in this .blend"
    for name, r in normals.items():
        mat = material(name)
        if r.get("convention") != "OpenGL" or mat is None:
            continue
        note = "normal map read with OpenGL green (%d node)" % flip_green(mat, os.path.basename(r["texture"]))
        mat["sb_hq_materials"] = ", ".join(x for x in (mat.get("sb_hq_materials", ""), note) if x)
        if name in report:
            report[name] += ", " + note
    for name in list(doc["materials"]) + list(skins):
        mat = material(name)
        if mat is not None:
            dropped = prune(mat)
            report[name] = (report.get(name) or mat.get("sb_hq_materials", "")) + "; %d unused nodes dropped" % dropped
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    print("SB_MOD_POST=" + json.dumps({"saved": bpy.data.filepath, "materials": report}, ensure_ascii=False),
          flush=True)


def main():
    if "--" in sys.argv and "--post" in sys.argv[sys.argv.index("--") + 1:]:
        argv = sys.argv[sys.argv.index("--") + 1:]
        post(argv[argv.index("--post") + 1])
        return
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="", help="comma-separated package folders (default: all of %s)" % ", ".join(OUTFITS))
    ap.add_argument("--paks", default=PAKS, help="the game's Paks folder with the mods in ~mods")
    args = ap.parse_args()
    if os.path.isfile(REGISTRY):
        for k, v in json.load(open(REGISTRY, encoding="utf-8")).items():
            OUTFITS.setdefault(k, v)
    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(OUTFITS)
    for package in wanted:
        run_outfit(package, args)


if __name__ == "__main__":
    main()
