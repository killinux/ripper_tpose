r"""HQ .blend of the archived Nexus-mod outfits worn by Eve (Gantz Reika A / B, and the nude body of
EveOriginalProportions), so the stellarblade_game_materials add-on finds every material of their PMX.  The mod's own
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
     master's defaults (its CachedExpressionData) for what no instance sets.  One translation hq_materials.py has no
     rule for: the GlowEmissive layer (static switch UseGlowEmissive; the Planet Diving Suit master MA_CH_P_EVE_09,
     which the Gantz Reika suits inherit through MI_P_EVE_09_Metal02_Layered) lights the ML_GlowEmissive_CH channel of
     the Emissive map in ML_GlowEm_EyeCoreHDRTint - written as Emissive_CH / EmissiveColor (HDR, kept as is) /
     EmissivePower 1 (only switches the wiring on).  The layer's fresnel / boost terms are not reproduced;
  3. ../hq_materials.py --mi-json staged --textures <outfit folder>\textures --out <data dir>;
  4. ../hq_materials_blender.py on the archived .blend -> <label>_HQ.blend next to it (the eye rebuilt from the
     game's values on the way, as in every HQ .blend);
  5. this script inside Blender (--post):
     - skin instances (masters MA_Skin*: BaseColor / BaseNormal / "ORSS Mask" = R occlusion, G roughness, B specular,
       A subsurface; hq_materials.py reads none of these names) are wired here: roughness = G between MinRoughness and
       MaxRoughness, specular = B x BaseSpecularValue, the DirectX normal x NormalStrength; the subsurface settings
       are the head material's, so the body skin meets the face (whose archive network stays) without a seam -
       skin.json lists what was read;
     - nodes the new wiring left with no path to the output are dropped (the archive had guessed ORM / normal /
       emission from file names).
The archived .blend is only read.  The add-on picks the HQ .blend that holds most of a PMX's materials (per layer for
a pmx_layers.py model), so the Reika PMX take every material from their own HQ .blend and the nude layer from the
nude's; the Cooling Suit and the other Eve PMX keep theirs.
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
# package folder -> character, the mod's content folder, the outfit's skeletal mesh (its material slots); "packages":
# what to read first when the folder is the game's own (default: the whole folder); "slots": only these (the barefoot
# variant's mesh keeps empty heels / pubic-hair slots); "archive" + "member": a mod that is not installed, read from
# the folder of its download archive holding the variant's .pak / .utoc / .ucas
OUTFITS = {
    "Mod_GantzReika_A": {"character": "Reika", "mod": "SB/Content/OutfitMods/GantzReika", "mesh": "GantzReika_A"},
    "Mod_GantzReika_B": {"character": "Reika", "mod": "SB/Content/OutfitMods/GantzReika", "mesh": "GantzReika_B"},
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


def package_glob(object_path):
    """/Game/Art/X/MI_Y.0 -> SB/Content/Art/X/MI_Y.* (CUE4Parse wants a wildcard for a single package)"""
    path = object_path.split(".")[0]
    if path.startswith("/Game/"):
        path = "SB/Content/" + path[len("/Game/"):]
    return path + ".*"


def cue4parse(patterns, out_dir, paks):
    cmd = [CUE4PARSE, "-i", paks, "-g", "GAME_UE4_26", "-m", USMAP, "-f", "json", "-y", "-o", out_dir]
    for p in patterns:
        cmd += ["-p", p]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("cue4parse failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])


def mod_paks(entry, paks, work):
    """the Paks folder CUE4Parse reads for this outfit: the game's own (an installed mod sits in its ~mods), or for a
    mod that is not installed a folder in `work` with the variant's files from its archive and a junction to the
    game's Paks (the mod's instances name game parents).  Returns (folder, junction or None)."""
    if not entry.get("archive"):
        return paks, None
    folder = os.path.join(work, "Paks")
    os.makedirs(folder)
    r = subprocess.run([TAR, "-xf", entry["archive"], "-C", folder, entry["member"]], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    found = glob.glob(os.path.join(folder, entry["member"], "*.utoc")) + \
        glob.glob(os.path.join(folder, entry["member"], "*.pak"))
    if r.returncode != 0 or not found:
        raise SystemExit("could not unpack %s from %s:\n%s" % (entry["member"], entry["archive"], r.stdout + r.stderr))
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


def read_game(patterns, json_dir, paks):
    """the mod's packages' JSON plus every parent instance / master they name"""
    cue4parse(patterns, json_dir, paks)
    asked = set()
    for _level in range(8):
        mats = index_json(json_dir)
        wanted = []
        for e in mats.values():
            if not e.get("Type", "").startswith("MaterialInstance"):
                continue
            ref = ((e.get("Properties") or {}).get("Parent") or {}).get("ObjectPath", "")
            if ref and quoted(((e.get("Properties") or {}).get("Parent") or {}).get("ObjectName", "")) not in mats \
                    and ref not in asked:
                asked.add(ref)
                wanted.append(package_glob(ref))
        if not wanted:
            return mats
        cue4parse(wanted, json_dir, paks)
    return index_json(json_dir)


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
    scalars, vectors = dict(defaults["scalars"]), dict(defaults["vectors"])
    textures, switches, overrides = {}, {}, {}
    for inst in reversed(insts):                           # master side first: the child's value wins
        p = inst.get("Properties") or {}
        for s in p.get("ScalarParameterValues") or []:
            scalars[s["ParameterInfo"]["Name"]] = s["ParameterValue"]
        for s in p.get("VectorParameterValues") or []:
            vectors[s["ParameterInfo"]["Name"]] = s["ParameterValue"]
        for s in p.get("TextureParameterValues") or []:
            if (s.get("ParameterValue") or {}).get("ObjectPath"):
                textures[s["ParameterInfo"]["Name"]] = s["ParameterValue"]
        for s in (p.get("StaticParameters") or {}).get("StaticSwitchParameters") or []:
            switches[s["ParameterInfo"]["Name"]] = s["Value"]
        overrides.update(p.get("BasePropertyOverrides") or {})
    master_name = master["Name"] if master is not None else parent_of(insts[-1])
    notes = {"chain": [c["Name"] for c in chain], "master": master_name}

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


def skin_record(staged, tex_dir):
    """what --post wires for a skin instance (flattened values; maps as files in the outfit's textures)"""
    p = staged[0]["Properties"]
    s = {x["ParameterInfo"]["Name"]: x["ParameterValue"] for x in p["ScalarParameterValues"]}
    t = {x["ParameterInfo"]["Name"]: texture_name(x["ParameterValue"]) for x in p["TextureParameterValues"]}

    def find(key):
        name = t.get(key)
        if not name:
            return None
        for sub in ("", "extra"):
            path = os.path.join(tex_dir, sub, name + ".png")
            if os.path.isfile(path):
                return path
        return "MISSING:" + name

    return {"base": find("BaseColor"), "normal": find("BaseNormal"), "orss": find("ORSS Mask"),
            "roughness_min": s.get("MinRoughness", 0.2), "roughness_max": s.get("MaxRoughness", 1.0),
            "specular": s.get("BaseSpecularValue", 0.4), "normal_strength": s.get("NormalStrength", 1.0),
            "not_wired": {k: t[k] for k in t if k not in ("BaseColor", "BaseNormal", "ORSS Mask")},
            "values": {k: s[k] for k in ("BaseSSS", "GlobalRoughness", "FresnelRoughness", "Detail Tiling",
                                         "Detail Strength") if k in s}}


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
    work = tempfile.mkdtemp(prefix="hq_mod_")
    try:
        paks, _link = mod_paks(entry, args.paks, work)
        mats = read_game(entry.get("packages") or [mod_dir + "/*"], json_dir, paks)
    finally:
        link = os.path.join(work, "Paks", "game")
        if os.path.lexists(link):
            os.rmdir(link)                          # the junction only - never the game's Paks it points to
        shutil.rmtree(work, ignore_errors=True)
    mesh = mats.get(mesh_name)
    if mesh is None:
        raise SystemExit("%s: skeletal mesh %s not in the mod's JSON" % (package, mesh_name))
    used = []
    for slot in mesh.get("SkeletalMaterials") or []:
        name = quoted((slot.get("Material") or {}).get("ObjectName", ""))
        if name and name not in used and (not entry.get("slots") or name in entry["slots"]):
            used.append(name)
    tex_dir = os.path.join(folder, "textures")
    notes, skins = {}, {}
    for name in used:
        staged, note = flatten(name, mats)
        if staged is None:
            notes[name] = {"error": "not a material instance in the JSON"}
            continue
        notes[name] = note
        if note.get("skin"):
            skins[name] = skin_record(staged, tex_dir)
            skins[name]["chain"] = note["chain"]
            continue
        fname = name if name.startswith("MI_") else "MI_" + name        # hq_materials.py globs MI_*.json
        json.dump(staged, open(os.path.join(staged_dir, fname + ".json"), "w", encoding="utf-8"), indent=1)
    json.dump(skins, open(os.path.join(data, "skin.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(notes, open(os.path.join(data, "chains.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for name, note in notes.items():
        log("%s %-12s %s%s%s" % (package, name, " -> ".join(note.get("chain", [])), "  [glow]" if "glow" in note else "",
                                 "  [skin]" if note.get("skin") else ""))
    text = []
    r1 = subprocess.run([sys.executable, os.path.join(HERE, "hq_materials.py"), "--mi-json", staged_dir,
                         "--textures", tex_dir, "--out", data], capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    text.append("== hq_materials.py\n" + r1.stdout + r1.stderr)
    if r1.returncode != 0:
        raise SystemExit("hq_materials.py failed:\n" + text[-1])
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
    if d["orss"] and not d["orss"].startswith("MISSING"):
        n = nodes.new("ShaderNodeTexImage")
        n.image = hb.image(d["orss"], True)
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
    p.inputs["Metallic"].default_value = 0.0
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


def post(data):
    import bpy
    sys.path.insert(0, HERE)
    doc = json.load(open(os.path.join(data, "materials.json"), encoding="utf-8"))
    skins = json.load(open(os.path.join(data, "skin.json"), encoding="utf-8"))
    head = bpy.data.materials.get(HEAD)
    report = {}
    for name, d in skins.items():
        mat = bpy.data.materials.get(name)
        report[name] = wire_skin(mat, d, head) if mat is not None and mat.use_nodes else "not in this .blend"
    for name in list(doc["materials"]) + list(skins):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.use_nodes:
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
    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(OUTFITS)
    for package in wanted:
        run_outfit(package, args)


if __name__ == "__main__":
    main()
