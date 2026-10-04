"""One dance for every unit: each exported unit gets a dance of its own from a motion collection and a backdrop from
the game's pictures; the videos go into one folder, with the lists of what is done and what is not.

    python dance_batch.py --count 10            # the next 10 units that have no video yet
    python dance_batch.py --count 10 --jobs 3   # three at a time
    python dance_batch.py 5_sakura 24_kirara    # these units
    python dance_batch.py --plan                # only work out who dances what, and write the lists
    python dance_batch.py --list                # only rewrite the lists and the gallery (after deleting a video, say)
    python dance_batch.py --drop 58_yuphiesophie --why "两个人的单位"    # this unit gets no video: its video goes
    python dance_batch.py --undrop 58_yuphiesophie                      # ... and back among the dancers

Who: every female unit (--men: the others too) that has a PMX with a standard MMD skeleton, each costume on its
own, without monsters and bosses (SKIP_CATEGORIES), and without the units somebody looked at and did not want
(--drop: kept in dropped.json with the reason).  What: the collection's solo dances with music, MIN_SECONDS or longer; of a dance that was
released several times the newest one; folders with several motions (left / right versions, parts) or only versions
fitted to another body are left out - the list says why for each.  The pairing is drawn once with a fixed seed and
kept (plan.json): a second run goes on where the first stopped, a unit never changes its dance by itself.

    <export-root>/_videos/
        <dance>_<name>.mp4           the videos (dance_video.py --title "{dance}_{name}" --plain-name, a random backdrop,
                                     the following camera, no .blend)
        _列表.md                      who has a video and who has not; which dances are used, free, or left out and why
        _meta/plan.json              unit -> dance, backdrop
        _meta/videos.json            what was rendered, from what
        _meta/dropped.json           unit -> why it gets no video (--drop / --undrop)
        _meta/dances.json            the collection as it was read (lengths; a cache)
        _meta/list.json              the lists as data - the gallery (html/make_gallery.py) shows them
        _meta/reports/<video>.json   dance_video's report of each video
        _meta/thumbs/<video>.jpg     one frame of each video

The motion collection is only read.  A video that is there is kept unless --force.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import random
import re
import subprocess
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dance_video as dv  # noqa: E402
import tsquad_common as tc  # noqa: E402

MOTIONS = os.environ.get("TSQUAD_MOTIONS", r"E:\4090\小王动画2026年2月11日以前MMD动作合集")
FOLDER = "_videos"
TITLE = "{dance}_{name}"                               # the videos' file names (dance_video.file_stem)
SEED = 20261003                                        # of the draw: who gets which dance, which backdrop
MIN_SECONDS = 8.0
MEASURE = "body"                                       # how dances.json's lengths were taken: an older cache is read again
MIN_FREE_GB = 6.0                                      # --min-free-gb: no video is started with less memory free
SKIP_CATEGORIES = ("monster", "boss", "mob")
FITTED = re.compile(r"适配|体型")                        # a version of the motion fitted to another body
SEVERAL = re.compile(r"\d\s*人|[双二三四多]人")           # a dance for several dancers
RELEASE = re.compile(r"(20\d\d)\.?(\d{1,2})\.(\d{1,2})")
BACKDROPS = ("剧情_", "过场_")                           # the game's location art (export_backgrounds.py)
# seen from the air, or only sky: nowhere to stand (the names are export_backgrounds.py's)
NO_GROUND = re.compile(r"鸟瞰|俯瞰|_sky_|楼群|群山|霓虹都市_月夜|都市起火|火海都市|港湾都市|海岸公路|月下火海", re.IGNORECASE)
AUDIO = dv.AUDIO
log = tc.log


# ---------------------------------------------------------------- the collection
def read_collection(folder: str, cache: dict | None = None) -> list[dict]:
    """[{"folder", "vmds": [{"file", "frames"}], "audio": [file names]}] of a collection that keeps one dance per
    folder; "frames" = the last key of the body bones (dance_video.dance_frames).  `cache` ({path: [size, mtime,
    frames, MEASURE]}) saves reading the motions again."""
    cache = cache if cache is not None else {}
    out = []
    for name in sorted(os.listdir(folder)):
        sub = os.path.join(folder, name)
        if not os.path.isdir(sub):
            continue
        files = sorted(os.listdir(sub))
        vmds = []
        for f in files:
            if not f.lower().endswith(".vmd"):
                continue
            path = os.path.join(sub, f)
            stat = os.stat(path)
            hit = cache.get(path)
            if not hit or hit[:2] != [stat.st_size, int(stat.st_mtime)] or hit[3:] != [MEASURE]:
                hit = cache[path] = [stat.st_size, int(stat.st_mtime), dv.dance_frames(path), MEASURE]
            vmds.append({"file": f, "frames": hit[2]})
        out.append({"folder": name, "vmds": vmds, "audio": [f for f in files if f.lower().endswith(AUDIO)]})
    return out


def release_date(name: str) -> tuple[int, int, int]:
    """(year, month, day) written in a folder's name, (0, 0, 0) when there is none."""
    found = RELEASE.search(name)
    return tuple(int(v) for v in found.groups()) if found else (0, 0, 0)


def choose_dances(entries: list[dict], min_seconds: float = MIN_SECONDS) -> list[dict]:
    """What each folder of the collection is good for: [{"folder", "title", "vmd", "music", "seconds", "date",
    "status"}] - status "" = a dance to hand out, anything else says (to the user, in the list) why it is not."""
    out = []
    for entry in entries:
        folder = entry["folder"]
        title = dv.clean_name(folder)
        motions = [v for v in entry["vmds"] if not dv.NOT_A_DANCE.search(v["file"])]
        plain = [v for v in motions if not FITTED.search(v["file"])]
        named = [v for v in plain if dv.clean_name(os.path.splitext(v["file"])[0]) == title]
        main = plain[0] if len(plain) == 1 else named[0] if len(named) == 1 else None
        stem = os.path.splitext(main["file"])[0] if main else ""
        same = [f for f in entry["audio"] if os.path.splitext(f)[0] == stem]
        music = same[0] if same else entry["audio"][0] if len(entry["audio"]) == 1 else ""
        seconds = round(main["frames"] / 30.0, 1) if main else 0.0
        if not motions:
            status = "没有 .vmd"
        elif not plain:
            status = "只有给别的体型的适配版"
        elif main is None:
            status = "文件夹里有几段动作（左右版 / 分段 / 长短版）"
        elif SEVERAL.search(folder) or SEVERAL.search(main["file"]):
            status = "多人舞"
        elif not music:
            status = "没有配乐" if not entry["audio"] else "有几个配乐文件，分不清用哪个"
        elif seconds < min_seconds:
            status = "不到 %g 秒" % min_seconds
        else:
            status = ""
        out.append({"folder": folder, "title": title, "vmd": main["file"] if main else "", "music": music,
                    "seconds": seconds, "date": list(release_date(folder)), "status": status})
    newest = {}
    for d in out:                                      # of a dance released several times: the newest
        if not d["status"] and (d["title"] not in newest or (d["date"], d["folder"]) > (newest[d["title"]]["date"], newest[d["title"]]["folder"])):
            newest[d["title"]] = d
    for d in out:
        if not d["status"] and newest[d["title"]] is not d:
            d["status"] = "同一支舞的旧版（新版：%s）" % newest[d["title"]]["folder"]
    return out


# ---------------------------------------------------------------- who, and the draw
def can_dance(model: dict, record: dict | None, men: bool = False) -> bool:
    """A unit that gets a video: a female figure (tsquad_common.is_female - the model needs its "details";
    `men`: the others too), no monster, no boss, and its PMX (`record`: its entry in exports.json) has a standard
    MMD skeleton - a snake's or a fish's body keeps the game's bones and takes no VMD."""
    record = record or {}
    return ((men or tc.is_female(model)) and model["category"] not in SKIP_CATEGORIES and bool(record.get("pmx"))
            and not (record.get("pmx_report") or {}).get("plain_rig"))


def prune(videos: dict, keep: set, where: SimpleNamespace) -> list[str]:
    """Delete the videos (with their thumbnail and report) of units that are no dancers any more - after a rule
    changed.  Only what videos.json lists, only inside the videos folder.  Returns what went."""
    gone = []
    for unit in [u for u in videos if u not in keep]:
        video = videos.pop(unit).get("video") or ""
        stem = os.path.splitext(os.path.basename(video))[0]
        if not stem or os.path.dirname(os.path.abspath(video)) != os.path.abspath(where.folder):
            continue
        for path in (video, os.path.join(where.thumbs, stem + ".jpg"), os.path.join(where.reports, stem + ".json")):
            if os.path.isfile(path):
                os.remove(path)
        gone.append("%s (%s)" % (os.path.basename(video), unit))
    return gone


def set_dropped(dropped: dict, drop: list[str], undrop: list[str], why: str = "") -> dict:
    """{unit: why it gets no video} after --drop / --undrop: what a look at the videos decided (a unit of two
    figures, of which a dance moves one), not something a rule could tell.  A unit dropped again keeps its reason
    unless a new one is given."""
    out = {unit: reason for unit, reason in dropped.items() if unit not in undrop}
    for unit in drop:
        out[unit] = why or out.get(unit, "")
    return out


def backdrop_pool(root: str) -> list[str]:
    """File names of the game's pictures a dancer can stand in front of (<root>/_backgrounds)."""
    folder = os.path.join(root, "_backgrounds")
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if f.lower().endswith(".png") and f.startswith(BACKDROPS) and not NO_GROUND.search(f))


def draw(units: list[str], dances: list[str], backdrops: list[str], seed: int = SEED, old: dict | None = None) -> dict:
    """{unit: {"dance": folder, "backdrop": file name}}.  What `old` says stays as long as the dance and the picture
    are still on offer; the other units, in their order, get the dances nobody has yet in an order drawn with
    `seed`.  No dance twice; a backdrop comes back only when all have been used.  More units than dances: the
    last ones stay without."""
    rng = random.Random(seed)
    offer = sorted(dances)
    rng.shuffle(offer)
    pictures = sorted(backdrops)
    plan, taken = {}, set()
    for unit in units:
        kept = (old or {}).get(unit) or {}
        if kept.get("dance") in dances and kept["dance"] not in taken:
            plan[unit] = {"dance": kept["dance"], "backdrop": kept.get("backdrop") if kept.get("backdrop") in pictures else ""}
            taken.add(kept["dance"])
    free = [d for d in offer if d not in taken]
    for unit in units:
        if unit not in plan and free:
            plan[unit] = {"dance": free.pop(0), "backdrop": ""}
    used = [p["backdrop"] for p in plan.values() if p["backdrop"]]
    stack = []
    for unit in units:
        entry = plan.get(unit)
        if entry is None or entry["backdrop"] or not pictures:
            continue
        if not stack:
            stack = [p for p in pictures if p not in used] or list(pictures)
            rng.shuffle(stack)
            used = []
        entry["backdrop"] = stack.pop()
    return plan


# ---------------------------------------------------------------- state
def paths(root: str) -> SimpleNamespace:
    folder = os.path.join(root, FOLDER)
    meta = os.path.join(folder, "_meta")
    return SimpleNamespace(folder=folder, meta=meta, plan=os.path.join(meta, "plan.json"),
                           videos=os.path.join(meta, "videos.json"), dropped=os.path.join(meta, "dropped.json"),
                           dances=os.path.join(meta, "dances.json"),
                           data=os.path.join(meta, "list.json"), reports=os.path.join(meta, "reports"),
                           thumbs=os.path.join(meta, "thumbs"), text=os.path.join(folder, "_列表.md"))


def load(path: str, default):
    try:
        return tc.load_json(path)
    except (OSError, ValueError):
        return default


def lists(units: list[dict], names: dict, plan: dict, dances: list[dict], videos: dict, collection: str,
          dropped: dict | None = None) -> dict:
    """The lists as data: every unit with its dance and its video, every dance with what became of it, and the
    units that were dropped (`dropped`: {unit: why}) with the reason."""
    by_folder = {d["folder"]: d for d in dances}
    out = [{"id": unit, "name": names.get(unit, unit), "why": why} for unit, why in sorted((dropped or {}).items())]
    done = {u: v for u, v in videos.items() if v.get("video") and os.path.isfile(v["video"])}
    rows = []
    for m in units:
        entry, video = plan.get(m["id"]) or {}, done.get(m["id"]) or {}
        dance = by_folder.get(video.get("dance") or entry.get("dance") or "") or {}
        rows.append({"id": m["id"], "name": names.get(m["id"], m["name"]), "category": m["category"],
                     "dance": dance.get("title", ""), "folder": dance.get("folder", ""), "seconds": dance.get("seconds", 0.0),
                     "backdrop": video.get("backdrop") or entry.get("backdrop") or "",
                     "video": video.get("video", ""), "thumb": video.get("thumb", ""), "time": video.get("time", "")})
    danced = {v["dance"]: u for u, v in done.items()}
    planned = {p["dance"]: u for u, p in plan.items()}
    table = []
    for d in dances:
        if d["status"]:
            state, unit = "不用", ""
        elif d["folder"] in danced:
            state, unit = "已导出", danced[d["folder"]]
        elif d["folder"] in planned:
            state, unit = "已分配，未导出", planned[d["folder"]]
        else:
            state, unit = "未分配", ""
        table.append({"title": d["title"], "folder": d["folder"], "vmd": d["vmd"], "seconds": d["seconds"],
                      "state": state, "unit": unit, "why": d["status"]})
    count = lambda state: sum(1 for t in table if t["state"] == state)  # noqa: E731
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "collection": collection, "units": rows, "dances": table,
            "dropped": out,
            "summary": {"units": len(rows), "with_video": sum(1 for r in rows if r["video"]),
                        "without_dance": sum(1 for r in rows if not r["dance"]), "dropped": len(out),
                        "folders": len(table), "usable": len(table) - count("不用"), "exported": count("已导出"),
                        "planned": count("已分配，未导出"), "free": count("未分配"), "left_out": count("不用")}}


def markdown(data: dict) -> str:
    s = data["summary"]
    out = ["# Taimanin Squad 舞蹈视频列表", "",
           "生成于 %s，由 `scripts/taimaninsquad/dance_batch.py` 维护（每次运行都会重写）。" % data["generated"],
           "动作合集：`%s`" % data["collection"], "",
           "## 概况", "",
           "- 角色（女性，每套服装算一个，不含怪物和 Boss）：%d 个，**已导出视频 %d**，还没导出 %d%s" % (
               s["units"], s["with_video"], s["units"] - s["with_video"],
               "（其中 %d 个没有分到动作）" % s["without_dance"] if s["without_dance"] else ""),
           "- 动作：合集里 %d 个文件夹，可用的 %d 支（单人、有配乐、够长、同一支舞取最新版）—— **已导出 %d**，"
           "已分配还没导出 %d，没分配 %d；不用的 %d 个，原因见下表" % (
               s["folders"], s["usable"], s["exported"], s["planned"], s["free"], s["left_out"])]
    dropped = data.get("dropped") or []
    if dropped:
        out.append("- 不做视频的角色：%d 个（看过之后决定不要的，`--drop`；`--undrop` 放回来），见下表" % len(dropped))
    out += ["", "## 角色", "", "| 单位 | 名字 | 动作 | 秒 | 背景 | 状态 | 视频 |", "|---|---|---|---:|---|---|---|"]
    for r in data["units"]:
        out.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r["name"], r["dance"] or "（没有分到）", "%g" % r["seconds"] if r["dance"] else "",
            os.path.splitext(r["backdrop"])[0], "已导出 %s" % r["time"][:16] if r["video"] else "未导出",
            "`%s`" % os.path.basename(r["video"]) if r["video"] else ""))
    if dropped:
        out += ["", "## 不做视频的角色", "", "| 单位 | 名字 | 原因 |", "|---|---|---|"]
        out += ["| `%s` | %s | %s |" % (d["id"], d["name"], d["why"] or "（没写）") for d in dropped]
    out += ["", "## 动作", "", "| 动作 | 文件夹 | .vmd | 秒 | 状态 | 角色 / 原因 |", "|---|---|---|---:|---|---|"]
    order = {"已导出": 0, "已分配，未导出": 1, "未分配": 2, "不用": 3}
    for t in sorted(data["dances"], key=lambda t: (order[t["state"]], t["title"], t["folder"])):
        out.append("| %s | %s | %s | %s | %s | %s |" % (
            t["title"], t["folder"], t["vmd"], "%g" % t["seconds"] if t["seconds"] else "", t["state"],
            "`%s`" % t["unit"] if t["unit"] else t["why"]))
    return "\n".join(out) + "\n"


def thumbnail(video: str, thumb: str, seconds: float) -> str:
    """One frame of the video (a third of the way in) as a small JPEG; "" when ffmpeg is not there or fails."""
    os.makedirs(os.path.dirname(thumb), exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % max(0.0, seconds / 3.0), "-i", video,
                        "-frames:v", "1", "-vf", "scale=-2:640", "-q:v", "4", thumb], check=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return thumb if os.path.isfile(thumb) else ""


# ---------------------------------------------------------------- the run
def step_aside() -> bool:
    """Run below normal priority, with everything started from here (on Windows a child takes this class over
    from its parent): a batch of an hour must not make the machine sluggish for whoever sits at it."""
    if os.name != "nt":
        try:
            os.nice(5)
        except OSError:
            return False
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return bool(kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000))      # BELOW_NORMAL_PRIORITY_CLASS


def free_memory_gb() -> float | None:
    """Memory that can still be had right now, in GB: the smaller of free RAM and free commit (RAM + page file) -
    other jobs on the machine may have reserved more than they use yet.  None where that cannot be asked."""
    if os.name == "nt":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                        ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                        ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                        ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                        ("ullAvailExtendedVirtual", ctypes.c_uint64)]

        status = Status(dwLength=ctypes.sizeof(Status))
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return min(status.ullAvailPhys, status.ullAvailPageFile) / 2.0 ** 30
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2.0 ** 30
    except (AttributeError, OSError, ValueError):
        return None


def wait_for_memory(least_gb: float, who: str = "", poll: float = 30.0, free=free_memory_gb, sleep=time.sleep) -> float:
    """Hold a video back while less than `least_gb` of memory is free (a render takes 1 - 2.5 GB; the other jobs on
    the machine come and go); returns the seconds waited.  least_gb 0, or a system that does not tell: no waiting."""
    waited = 0.0
    while least_gb > 0:
        have = free()
        if have is None or have >= least_gb:
            break
        if not waited:
            log("%s: %.1f GB of memory free - waiting for %g (--min-free-gb)" % (who, have, least_gb))
        sleep(poll)
        waited += poll
    return waited


def render(model: dict, dance: dict, backdrop: str, a, where: SimpleNamespace, names: dict) -> dict:
    """One unit's video; returns its record for videos.json."""
    wait_for_memory(a.min_free_gb, model["id"])
    folder = os.path.join(a.motions, dance["folder"])
    vmd, bgm = os.path.join(folder, dance["vmd"]), os.path.join(folder, dance["music"])
    job = SimpleNamespace(
        export_root=a.export_root, view="full", bust=None, out_dir=where.folder, title=a.title, plain_name=True,
        backdrop=os.path.join(a.export_root, "_backgrounds", backdrop) if backdrop else "", backdrop_as="auto",
        backdrop_fov=70.0, backdrop_turn=0.0, backdrop_tilt=0.0, shadow=0.45, people=names, dance=dance["title"],
        camera=a.camera, follow=a.follow, physics="mmd", margin=30, samples=a.samples, size=a.size, frames=0,
        music_tail=a.music_tail, stills=0, no_video=False, no_edge=False, no_blend=True, force=a.force)
    rep = dv.render_one(model, vmd, bgm, dv.motion_name(vmd), job)
    video = rep["video"]
    seconds = round(rep["motion_frames"] / float(rep.get("fps") or dv.FPS), 1) if rep.get("motion_frames") else dance["seconds"]
    record = {"video": video, "dance": dance["folder"], "title": dance["title"], "vmd": dance["vmd"],
              "backdrop": backdrop, "time": rep.get("time") or time.strftime("%Y-%m-%d %H:%M:%S"),
              "seconds": seconds, "render_seconds": rep.get("seconds"), "kept": bool(rep.get("skipped"))}
    side = os.path.splitext(video)[0] + ".json"          # dance_video's report: out of the folder people browse
    if os.path.isfile(side):
        os.makedirs(where.reports, exist_ok=True)
        os.replace(side, os.path.join(where.reports, os.path.basename(side)))
    record["thumb"] = thumbnail(video, os.path.join(where.thumbs, os.path.splitext(os.path.basename(video))[0] + ".jpg"),
                                dance["seconds"])
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="*", help="units to render (ids / numbers / names); default: the next --count without a video")
    ap.add_argument("--count", type=int, default=0, metavar="N", help="render the next N units that have no video yet")
    ap.add_argument("--jobs", type=int, default=1, metavar="N", help="render N videos at a time")
    ap.add_argument("--full-speed", action="store_true",
                    help="normal process priority (default: below normal, so the machine stays usable meanwhile)")
    ap.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB, metavar="GB",
                    help="a video is started only while this much memory is free, else it waits (%(default)s; 0 = never wait)")
    ap.add_argument("--plan", action="store_true", help="only draw the plan and write the lists")
    ap.add_argument("--list", action="store_true", help="only rewrite the lists and the gallery")
    ap.add_argument("--motions", default=MOTIONS, help="the motion collection: one dance per folder (default %(default)s)")
    ap.add_argument("--min-seconds", type=float, default=MIN_SECONDS, help="dances shorter than this are left out (%(default)s)")
    ap.add_argument("--music-tail", type=float, default=dv.MUSIC_TAIL, metavar="SECONDS",
                    help="a motion that goes on for more than this after its music is rendered as far as the music "
                         "plays (%(default)s; dance_video.py --music-tail)")
    ap.add_argument("--seed", type=int, default=SEED, help="of the draw (%(default)s); the plan that is there stays")
    ap.add_argument("--title", default=TITLE, metavar="PATTERN", help="the videos' file names (%(default)s; dance_video.py --title)")
    ap.add_argument("--men", action="store_true", help="the male units too (default: female figures only)")
    ap.add_argument("--prune", action="store_true",
                    help="delete the videos of units that are no dancers under the present rules (after a rule changed)")
    ap.add_argument("--drop", nargs="+", default=[], metavar="UNIT",
                    help="these units get no video from now on (kept in _meta/dropped.json): the video they have is "
                         "deleted, their dance is free for somebody else, the lists name them with --why")
    ap.add_argument("--why", default="", metavar="TEXT", help="with --drop: the reason, for the lists")
    ap.add_argument("--undrop", nargs="+", default=[], metavar="UNIT", help="take these units back among the dancers")
    ap.add_argument("--no-backdrop", action="store_true", help="the plain grey background")
    ap.add_argument("--camera", choices=("follow", "fixed"), default="follow")
    ap.add_argument("--follow", default="", metavar="KEY=VALUE,...", help="the following camera's settings (tsquad_common.FOLLOW)")
    ap.add_argument("--size", default="", help="WIDTHxHEIGHT (default 1080x1920)")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--force", action="store_true", help="render again what is there")
    ap.add_argument("--no-gallery", action="store_true", help="do not rewrite html/index.html at the end")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    tc.parse_follow(a.follow)
    if not os.path.isdir(a.motions):
        raise SystemExit("the motion collection is not there: %s (--motions, or the environment variable TSQUAD_MOTIONS)" % a.motions)
    where = paths(a.export_root)
    os.makedirs(where.meta, exist_ok=True)

    import list_models

    everyone = tc.discover_models(tc.catalog_assets(a.export_root), a.export_root)
    list_models.add_details(everyone, a.export_root)    # is_female reads them (cached in _meta/model_details.json)
    names = dv.person_names(everyone)
    exports = load(os.path.join(tc.meta_dir(a.export_root), "exports.json"), {})
    dropped = load(where.dropped, {})
    going = [m["id"] for m in tc.find_models(everyone, a.drop)] if a.drop else []
    if a.drop or a.undrop:
        back = [m["id"] for m in tc.find_models(everyone, a.undrop)] if a.undrop else []
        dropped = set_dropped(dropped, going, back, a.why)
        tc.save_json(where.dropped, dropped)
        log("no video for: %s" % (", ".join("%s (%s)" % (u, w or "no reason given") for u, w in sorted(dropped.items())) or "nobody"))
    units = [m for m in everyone if m["id"] not in dropped and can_dance(m, exports.get(m["id"]), a.men)
             and os.path.isfile(os.path.join(tc.model_dir(m, a.export_root, "pmx"), m["id"] + ".pmx"))]
    cache = load(where.dances, {})
    dances = choose_dances(read_collection(a.motions, cache), a.min_seconds)
    tc.save_json(where.dances, cache)
    usable = {d["folder"]: d for d in dances if not d["status"]}
    pictures = [] if a.no_backdrop else backdrop_pool(a.export_root)
    plan = draw([m["id"] for m in units], list(usable), pictures, a.seed, load(where.plan, {}))
    tc.save_json(where.plan, plan)
    videos = load(where.videos, {})
    strays = [u for u in videos if u not in plan]
    unwanted = strays if a.prune else [u for u in strays if u in going]      # --drop takes its units' videos along
    if unwanted:
        for line in prune(videos, set(videos) - set(unwanted), where):
            log("removed %s" % line)
        tc.save_json(where.videos, videos)
    strays = [u for u in videos if u not in plan]
    if strays:
        log("%d video(s) of units that are no dancers under the present rules: %s  (--prune deletes them)" % (
            len(strays), ", ".join(strays)))
    log("%d units, %d dances to hand out (%d folders), %d backdrops; %d videos are there" % (
        len(units), len(usable), len(dances), len(pictures),
        sum(1 for v in videos.values() if v.get("video") and os.path.isfile(v["video"]))))

    def finish():
        data = lists(units, names, plan, dances, videos, a.motions, dropped)
        tc.save_json(where.data, data)
        with open(where.text, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(markdown(data))
        log("list: %s" % where.text)
        if not a.no_gallery:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "html"))
            import make_gallery

            log("gallery: %s" % make_gallery.build(None, a.export_root))
        return data

    if a.plan or a.list:
        finish()
        return 0
    has = {u for u, v in videos.items() if v.get("video") and os.path.isfile(v["video"])}
    if a.models:
        chosen = [m for m in tc.find_models(everyone, a.models) if m["id"] in plan]
        missing = [m["id"] for m in tc.find_models(everyone, a.models) if m["id"] not in plan]
        if missing:
            log("no dance for %s (not a dancer: no PMX / no MMD skeleton / a monster or boss - or the dances ran out)" % ", ".join(missing))
    else:
        chosen = [m for m in units if m["id"] in plan and (a.force or m["id"] not in has)][:max(0, a.count)]
    if not chosen:
        log("nothing to render - give units or --count N")
        finish()
        return 0
    tc.check_tools(need_blender=True)
    if not a.full_speed and step_aside():
        log("running below normal priority (--full-speed for normal)")
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        jobs = {pool.submit(render, m, usable[plan[m["id"]]["dance"]], plan[m["id"]]["backdrop"], a, where, names): m
                for m in chosen}
        for job in concurrent.futures.as_completed(jobs):
            model = jobs[job]
            try:
                record = job.result()
            except Exception as exc:  # noqa: BLE001 - keep going through the list
                log("FAILED %s: %s" % (model["id"], exc))
                failed.append(model["id"])
                continue
            if record.pop("kept") and model["id"] in videos:
                record = dict(videos[model["id"]], video=record["video"], thumb=record["thumb"] or videos[model["id"]].get("thumb", ""))
            videos[model["id"]] = record
            tc.save_json(where.videos, videos)           # after every video: a stopped run loses nothing
            log("%s: %s  (%s s of video, rendered in %s s, backdrop %s)" % (
                model["id"], os.path.basename(record["video"]), record["seconds"], record.get("render_seconds"),
                os.path.splitext(record["backdrop"])[0] or "none"))
    data = finish()
    s = data["summary"]
    log("done: %d of %d units have a video, %d failed this run%s" % (
        s["with_video"], s["units"], len(failed), " (%s)" % ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
