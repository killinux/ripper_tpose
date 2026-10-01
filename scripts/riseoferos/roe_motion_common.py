"""Paths, names and helpers shared by export_roe_motions.py and render_roe_motion_videos.py.

Every path can be overridden with an environment variable (ROE_BLENDER, ROE_FFMPEG, ROE_GAME, ROE_ARCHIVE,
ROE_EXPORTS) or the scripts' own --pmx / --out / --fbx options.
"""
import fnmatch
import os
import re
import subprocess

BLENDER = os.environ.get("ROE_BLENDER", r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe")
FFMPEG = os.environ.get("ROE_FFMPEG", r"D:\Program Files\ffmpeg\bin\ffmpeg.exe")
GAME_ROOT = os.environ.get("ROE_GAME", r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros")
BUNDLE_DIRS = [os.path.join(GAME_ROOT, "RiseOfEros_Data", "StreamingAssets", "AssetBundles"),
               os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "Pinkcore", "Rise of Eros", "AssetBundles")]
ARCHIVE = os.environ.get("ROE_ARCHIVE", r"E:\game_export\RiseOfEros")
ROE_EXPORTS = os.environ.get("ROE_EXPORTS", r"D:\roe_exports")
HERE = os.path.dirname(os.path.abspath(__file__))

# clip -> label used in the joined videos; the order is the order inside each joined video
LABELS = {
    "idle_ur01": "UR 待机", "idle_02": "待机 2", "react_01": "互动 1", "react_02": "互动 2",
    "idle_01": "战斗待机", "skill_01": "技能 1", "skill_02": "技能 2", "skill_03": "技能 3",
    "hurt": "受击", "die": "倒下", "rip": "破衣（倒地）",
}
ORDER = list(LABELS)
GROUPS = {"showcase": "展示动作", "battle": "战斗动作"}


def clip_sort_key(name):
    return (ORDER.index(name) if name in ORDER else len(ORDER), name)


def find_bundles(pattern):
    """Every bundle whose file name matches `pattern` (fnmatch) in the install dir or the download cache."""
    hits = []
    for root in BUNDLE_DIRS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    hits.append(os.path.join(dirpath, f))
    return hits


def find_bundle(pattern):
    """Newest bundle whose file name matches `pattern` (fnmatch) in the install dir or the download cache."""
    hits = find_bundles(pattern)
    return max(hits, key=os.path.getmtime) if hits else None


def bundles(cid):
    """{"showcase": hd bundle, "battle": ld bundle} of outfit `cid` (a08, g04 ...); the hd one also gives the
    skeleton every clip is decoded onto (the PMX is built from the hd prefab)."""
    return {"showcase": find_bundle("chara_armor_pc_%s_hd & ld_hd.ab" % cid),
            "battle": find_bundle("chara_armor_pc_%s_hd & ld_ld*.ab" % cid)}


def find_pmx(stem):
    """(pmx path, character folder) of <ARCHIVE>\\<character>\\pmx\\<stem>\\<stem>.pmx, or (None, None)."""
    if not os.path.isdir(ARCHIVE):
        return None, None
    for character in sorted(os.listdir(ARCHIVE)):
        path = os.path.join(ARCHIVE, character, "pmx", stem, stem + ".pmx")
        if os.path.isfile(path):
            return path, character
    return None, None


def pmx_copies(pmx):
    """The PMX, its _bustB sibling and - for a file in the archive - the D:\\roe_exports\\<id>\\blend\\pmx source pair
    the archive is copied from: an edit made only on E: is undone by the next archive run (g04's fan morph was)."""
    out = [pmx]
    stem = os.path.basename(os.path.dirname(pmx))
    m = re.match(r"pc_([a-z]\d+)", stem)
    if m and os.path.normcase(os.path.abspath(pmx)).startswith(os.path.normcase(os.path.abspath(ARCHIVE)) + os.sep):
        out.append(os.path.join(ROE_EXPORTS, m.group(1), "blend", "pmx", stem, os.path.basename(pmx)))
    both = []
    for p in out:
        both += [p, p[:-4] + "_bustB.pmx"]
    return [p for p in both if os.path.isfile(p)]


def default_out(stem, character):
    return os.path.join(ARCHIVE, character, "vmd", stem)


def vmd_path(out, stem, group, clip):
    folder = os.path.join(out, "battle") if group == "battle" else out
    return os.path.join(folder, "%s_%s.vmd" % (stem, clip))


def game_fbx(cid):
    """The pipeline's FBX of the hd prefab (largest copy), used as the 'game' side of the compare video."""
    root = os.path.join(ROE_EXPORTS, cid)
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        hits += [os.path.join(dirpath, f) for f in files if f == "pc_%s_hd.fbx" % cid]
    return max(hits, key=os.path.getsize) if hits else None


def body_fbx(body):
    """The pipeline's FBX of a nude body prefab (pc_g01_nk -> Prefab_pc_g01_nk_model.fbx, pc_a00_nk -> pc_a00_nk.fbx),
    the 'game' side of an H scene's compare video."""
    m = re.match(r"pc_([a-z]\d+)", body)
    root = os.path.join(ROE_EXPORTS, m.group(1)) if m else ROE_EXPORTS
    for name in ("Prefab_%s_model.fbx" % body, "%s.fbx" % body):
        hits = []
        for dirpath, _dirs, files in os.walk(root):
            hits += [os.path.join(dirpath, f) for f in files if f == name]
        if hits:
            return max(hits, key=os.path.getsize)
    return None


def run(args, log_path):
    """Run a command with its output in log_path; returns the exit code."""
    with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
        return subprocess.run(args, stdout=fh, stderr=subprocess.STDOUT).returncode


def grep(log_path, *needles):
    """Lines of a log that contain any of the needles."""
    out = []
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if any(n in line for n in needles):
                out.append(line.rstrip())
    return out
