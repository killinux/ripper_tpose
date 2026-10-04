"""Rise of Eros outfits dance the motion collection's dances that Taimanin Squad's batch left over: each dance gets
one ROE outfit, the videos go into one folder of the ROE archive, with the lists of what is done and what is not.

    python roe_dances.py --plan                       # only work out who dances what, and write the lists
    python roe_dances.py --count 2                    # the next 2 outfits (in hand-out order) that have no video yet
    python roe_dances.py pc_g01_secretary pc_b04_hd   # these outfits, each with its planned dance
    python roe_dances.py --list                       # only rewrite the lists
    python roe_dances.py --drop pc_b01_jeans --why "裙子穿模"    # this outfit dances no more (its video goes,
    python roe_dances.py --undrop pc_b01_jeans                   # its dance passes to the next outfit) / back again

Who: the ROE outfits that have a PMX in the archive (<ROE root>/<Character>/pmx/<id>/<id>.pmx) and are of a kind in
--kinds - by default the dressed ones: the main outfits (pc_xNN_hd, pc_xNN_outfitN_hd) and the fashion suits
(swimsuit, maid, bride ...), not the nude, full-nude, nude-base and fm versions (KINDS says which is which, by the
folder's name).  Left out as well: an outfit whose PMX has parts on bones that hang from no other bone
(pmx_rig_check.py - a gun, a cup, a flower that would stand still in the air while the body dances away; the lists
name the bones; --keep-loose lets them dance anyway), and the outfits somebody looked at and did not want (--drop).
The hand-out goes round the characters - their order and each one's outfits shuffled with --seed - so that every
character gets about as many dances as the others, until those with few outfits run out.

What: the collection's dances the way Taimanin Squad's dance_batch.py chooses them (one dancer, its music, MIN_SECONDS
or longer, of several releases the newest; the lists say why a folder is left out), less those another game's
batch has already (--taken: that batch's plan.json; by default Taimanin Squad's).  The pairing is drawn once and kept
(plan.json): a second run goes on where the first stopped, an outfit never changes its dance by itself.

How: Taimanin Squad's renderer (dance_video.py / render_dance_blender.py, Blender 3.6 + mmd_tools): the PMX with its
physics, the motion with a lead-in, the joints run the way MMD runs them and baked, the following camera, portrait
1080 x 1920, the music, no .blend.  The PMX is the outfit's <id>_bustB.pmx where there is one (--bust-pmx bustB, the
default): the same model with breast joints that have springs (scripts/mmd_physics/tune_bust_pmx.py) - the plain
<id>.pmx hangs each breast on a 10-degree joint without a spring, where gravity parks it on its limit and it hardly
moves.  Behind the dancer: one of the game's story backgrounds (roe_backgrounds.py), drawn at random with --seed, none
twice until all were used (--no-backdrop: plain grey).  ONE video at a time, below normal priority, and only while
--min-free-gb of memory is free - the machine is somebody's desk meanwhile.

    <ROE root>/_videos/
        <dance>_<Character>_<outfit>.mp4     the videos
        _列表.md                              who dances what, what is done, which dances are left out and why
        _meta/plan.json                      outfit -> dance
        _meta/videos.json                    what was rendered, from what, how long it took
        _meta/dropped.json                   outfit -> why it dances no more (--drop / --undrop)
        _meta/dances.json                    the collection's motion lengths (a cache)
        _meta/rig_check.json                 pmx_rig_check of each outfit's PMX (a cache, by size and time)
        _meta/list.json                      the lists as data (the shared dance page reads it)
        _meta/reports/  thumbs/  logs/       the renderer's report, one frame, Blender's log of each video

The motion collection and the PMX files are only read.  A video that is there is kept unless --force; the video of
an outfit that dances no more stays until --prune (the run names them).
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SQUAD_DIR = os.path.join(os.path.dirname(HERE), "taimaninsquad")
if SQUAD_DIR not in sys.path:
    sys.path.insert(0, SQUAD_DIR)
import dance_batch as db  # noqa: E402 - the collection, the draw, the render of one video, the thumbnail
import dance_video as dv  # noqa: E402
import tsquad_common as tc  # noqa: E402 - Blender's path, json helpers, the follow camera's settings

sys.path.insert(0, HERE)
import pmx_rig_check as rig  # noqa: E402 - parts that would not follow the body
import roe_backgrounds as bg  # noqa: E402 - the game's story backgrounds

GAME = "Rise of Eros"
ROE_ROOT = os.environ.get("ROE_ARCHIVE_ROOT", r"E:\game_export\RiseOfEros")
SQUAD_META = os.path.join(tc.EXPORT_ROOT, db.FOLDER, "_meta")      # Taimanin Squad's dance batch
SEED = 20261004                                         # of the hand-out order and the draw
TITLE = "{dance}_{name}"                                # the videos' file names; {name} = <Character>_<outfit>
# what an outfit folder of the archive holds, by its name: (kind, pattern), the first that fits
KINDS = (("full", r"_hd_full$"), ("nude", r"_hd_nude$"), ("nude_base", r"_nk(_bs|_nudebase)?$"),
         ("fm", r"_fm$"), ("main", r"_hd$"), ("suit", r""))
KIND_ZH = {"main": "主模型", "suit": "时装", "full": "完整裸体版", "nude": "裸体版", "nude_base": "裸体基础模型",
           "fm": "fm 版"}
DANCERS = ("main", "suit")                              # --kinds: the dressed outfits
BUST_PMX = "bustB"                                      # --bust-pmx: dance the <id>_bustB.pmx where there is one


def log(msg: str) -> None:
    print("[roe-dances] " + msg, flush=True)


# ---------------------------------------------------------------- the dancers
def outfit_kind(model_id: str) -> str:
    """main / suit / full / nude / nude_base / fm, from an outfit folder's name (KINDS)."""
    for kind, pattern in KINDS:
        if re.search(pattern, model_id):
            return kind
    return "suit"


def find_outfits(root: str = ROE_ROOT) -> list[dict]:
    """Every outfit of the archive that has its PMX: [{"id", "group" (the character's folder), "outfit", "kind",
    "category", "name"}] sorted by character and id; "name" (<Character>_<outfit>) goes into the file names."""
    out = []
    for group in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        folder = os.path.join(root, group, "pmx")
        if group.startswith(("_", ".")) or not os.path.isdir(folder):
            continue
        for mid in sorted(os.listdir(folder)):
            if not os.path.isfile(os.path.join(folder, mid, mid + ".pmx")):
                continue
            outfit = mid[3:] if mid.startswith("pc_") else mid
            kind = outfit_kind(mid)
            out.append({"id": mid, "group": group, "outfit": outfit, "kind": kind, "category": kind,
                        "name": "%s_%s" % (group, outfit)})
    return out


def hand_out_order(outfits: list[dict], seed: int = SEED) -> list[dict]:
    """The outfits in the order they get dances: round the characters (their order shuffled with `seed`), each time
    the next of a character's outfits (shuffled too); a character whose outfits ran out is passed over."""
    rng = random.Random(seed)
    by_group = {}
    for m in sorted(outfits, key=lambda m: (m["group"], m["id"])):
        by_group.setdefault(m["group"], []).append(m)
    groups = sorted(by_group)
    rng.shuffle(groups)
    for g in groups:
        rng.shuffle(by_group[g])
    rounds = max((len(v) for v in by_group.values()), default=0)
    return [by_group[g][i] for i in range(rounds) for g in groups if i < len(by_group[g])]


def find(outfits: list[dict], wanted: list[str]) -> list[dict]:
    """The outfits named: an id ("pc_g01_secretary"), "<Character>/<id>", or a piece of one id."""
    out = []
    for text in wanted:
        key = text.replace("\\", "/").split("/")[-1].lower()
        exact = [m for m in outfits if m["id"].lower() == key]
        hits = exact or [m for m in outfits if key in m["id"].lower()]
        if len(hits) != 1:
            raise SystemExit("%r fits %s" % (text, "no outfit" if not hits else "%d outfits: %s" % (
                len(hits), ", ".join(m["id"] for m in hits[:12]))))
        out.append(hits[0])
    return out


def pmx_path(model: dict, root: str = ROE_ROOT) -> str:
    return os.path.join(root, model["group"], "pmx", model["id"], model["id"] + ".pmx")


def dance_pmx(model: dict, root: str = ROE_ROOT, variant: str = BUST_PMX) -> str:
    """The PMX that dances: <id>_<variant>.pmx where there is one (bustB: breast joints with springs), else <id>.pmx."""
    plain = pmx_path(model, root)
    if variant and variant != "main":
        tuned = plain[:-4] + "_%s.pmx" % variant
        if os.path.isfile(tuned):
            return tuned
    return plain


def loose_outfits(outfits: list[dict], root: str, cache: dict) -> dict:
    """{outfit id: pmx_rig_check.loose_parts} of the outfits whose PMX has parts that will not follow the body.
    `cache` ({pmx path: [size, mtime, parts]}) is updated: a PMX is read again only when it changed."""
    out = {}
    for m in outfits:
        path = pmx_path(m, root)
        stat = os.stat(path)
        hit = cache.get(path)
        if not hit or hit[:2] != [stat.st_size, int(stat.st_mtime)]:
            hit = cache[path] = [stat.st_size, int(stat.st_mtime), rig.loose_parts(path)]
        if hit[2]:
            out[m["id"]] = hit[2]
    return out


# ---------------------------------------------------------------- the dances
def taken_dances(plans: list[str]) -> dict:
    """{dance folder: "<game folder>/<unit>"} - the dances other games' batches have (their plan.json)."""
    out = {}
    for path in plans:
        plan = db.load(path, None)
        if plan is None:
            raise SystemExit("the plan of another batch is not there: %s (--taken)" % path)
        game = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path)))))
        for unit, entry in sorted(plan.items()):
            if entry.get("dance"):
                out.setdefault(entry["dance"], "%s/%s" % (game, unit))
    return out


def lists(outfits: list[dict], plan: dict, dances: list[dict], videos: dict, taken: dict, collection: str,
          dropped: dict | None = None, loose: dict | None = None, everyone: list[dict] | None = None) -> dict:
    """The lists as data: every outfit that has a dance (with its video), every folder of the collection with what
    became of it here, the outfits left out and why (`dropped`: {id: why} by hand; `loose`: {id: loose parts});
    `everyone` (default `outfits`) is where those are looked up.  A video counts only for the dance planned now."""
    by_folder = {d["folder"]: d for d in dances}
    by_id = {m["id"]: m for m in (everyone or outfits)}
    done = {u: v for u, v in videos.items() if u in plan and v.get("dance") == plan[u].get("dance")
            and v.get("video") and os.path.isfile(v["video"])}
    rows = []
    for m in outfits:
        entry, video = plan.get(m["id"]) or {}, done.get(m["id"]) or {}
        dance = by_folder.get(video.get("dance") or entry.get("dance") or "") or {}
        if not dance:
            continue
        rows.append({"id": m["id"], "character": m["group"], "outfit": m["outfit"], "kind": m["kind"],
                     "dance": dance["title"], "folder": dance["folder"], "seconds": dance["seconds"],
                     "backdrop": video.get("backdrop") if video else entry.get("backdrop", ""),
                     "pmx": video.get("pmx", ""),
                     "video": video.get("video", ""), "thumb": video.get("thumb", ""), "time": video.get("time", ""),
                     "render_seconds": video.get("render_seconds")})
    danced = {v["dance"]: u for u, v in done.items()}
    planned = {p["dance"]: u for u, p in plan.items()}
    table = []
    for d in dances:
        if d["status"]:
            state, who = "不用", ""
        elif d["folder"] in danced:
            state, who = "已导出", danced[d["folder"]]
        elif d["folder"] in planned:
            state, who = "已分配，未导出", planned[d["folder"]]
        elif d["folder"] in taken:
            state, who = "别的游戏已用", taken[d["folder"]]
        else:
            state, who = "未分配", ""
        table.append({"title": d["title"], "folder": d["folder"], "vmd": d["vmd"], "music": d.get("music", ""),
                      "seconds": d["seconds"], "state": state, "unit": who, "why": d["status"]})
    gone = [{"id": u, "character": (by_id.get(u) or {}).get("group", ""), "why": why} for u, why in sorted((dropped or {}).items())]
    broken = [{"id": u, "character": (by_id.get(u) or {}).get("group", ""), "why": rig.describe(parts), "parts": parts}
              for u, parts in sorted((loose or {}).items()) if u not in (dropped or {})]
    count = lambda state: sum(1 for t in table if t["state"] == state)  # noqa: E731
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "game": GAME, "collection": collection,
            "units": rows, "dances": table, "dropped": gone, "loose": broken,
            "summary": {"outfits": len(outfits), "with_dance": len(rows), "with_video": sum(1 for r in rows if r["video"]),
                        "dropped": len(gone), "loose": len(broken), "folders": len(table),
                        "usable": len(table) - count("不用"),
                        "exported": count("已导出"), "planned": count("已分配，未导出"), "taken": count("别的游戏已用"),
                        "free": count("未分配"), "left_out": count("不用")}}


def markdown(data: dict) -> str:
    s = data["summary"]
    out = ["# Rise of Eros 舞蹈视频列表", "",
           "生成于 %s，由 `scripts/mmd_dances/roe_dances.py` 维护（每次运行都会重写）。" % data["generated"],
           "动作合集：`%s`" % data["collection"], "",
           "## 概况", "",
           "- 能跳舞的服装 %d 套，分到动作的 %d 套，**已导出视频 %d**，还没导出 %d" % (
               s["outfits"], s["with_dance"], s["with_video"], s["with_dance"] - s["with_video"]),
           "- 动作：合集里 %d 个文件夹，可用的 %d 支；别的游戏已经用了 %d 支，这里 **已导出 %d**，已分配还没导出 %d，"
           "没分配 %d；不用的 %d 个，原因见最后的表" % (
               s["folders"], s["usable"], s["taken"], s["exported"], s["planned"], s["free"], s["left_out"])]
    if data["dropped"] or data.get("loose"):
        out.append("- 不跳舞的服装：%d 套有部件不跟身体走（模型的问题，换到 MMD 里也一样），%d 套看过后不要的"
                   "（`--drop`；`--undrop` 放回来），见下表" % (len(data.get("loose") or []), len(data["dropped"])))
    out += ["", "## 服装和动作", "", "| 角色 | 服装 | 类型 | 动作 | 秒 | 背景 | 状态 | 视频 |",
            "|---|---|---|---|---:|---|---|---|"]
    for r in data["units"]:
        out.append("| %s | `%s` | %s | %s | %g | %s | %s | %s |" % (
            r["character"], r["id"], KIND_ZH.get(r["kind"], r["kind"]), r["dance"], r["seconds"],
            os.path.splitext(r.get("backdrop") or "")[0] or "灰色",
            "已导出 %s" % r["time"][:16] if r["video"] else "未导出",
            "`%s`" % os.path.basename(r["video"]) if r["video"] else ""))
    if data["dropped"] or data.get("loose"):
        out += ["", "## 不跳舞的服装", "", "| 服装 | 角色 | 原因 |", "|---|---|---|"]
        out += ["| `%s` | %s | %s |" % (d["id"], d["character"], d["why"]) for d in data.get("loose") or []]
        out += ["| `%s` | %s | 看过后不要：%s |" % (d["id"], d["character"], d["why"] or "（没写）") for d in data["dropped"]]
    out += ["", "## 动作", "", "| 动作 | 文件夹 | 秒 | 状态 | 服装 / 原因 |", "|---|---|---:|---|---|"]
    order = {"已导出": 0, "已分配，未导出": 1, "未分配": 2, "别的游戏已用": 3, "不用": 4}
    for t in sorted(data["dances"], key=lambda t: (order[t["state"]], t["title"], t["folder"])):
        out.append("| %s | %s | %s | %s | %s |" % (
            t["title"], t["folder"], "%g" % t["seconds"] if t["seconds"] else "", t["state"],
            "`%s`" % t["unit"] if t["unit"] else t["why"]))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the run
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="*", help="outfits to render (ids, or a piece of one); default: the next --count")
    ap.add_argument("--count", type=int, default=0, metavar="N", help="render the next N outfits that have no video yet")
    ap.add_argument("--plan", action="store_true", help="only draw the plan and write the lists")
    ap.add_argument("--list", action="store_true", help="only rewrite the lists")
    ap.add_argument("--kinds", default=",".join(DANCERS),
                    help="which outfits dance, of %s (default %%(default)s: the dressed ones)" % ", ".join(k for k, _ in KINDS))
    ap.add_argument("--taken", nargs="+", default=[os.path.join(SQUAD_META, "plan.json")], metavar="PLAN",
                    help="plan.json of other games' batches: their dances are not handed out here (default: Taimanin Squad's)")
    ap.add_argument("--motions", default=db.MOTIONS, help="the motion collection: one dance per folder (default %(default)s)")
    ap.add_argument("--min-seconds", type=float, default=db.MIN_SECONDS, help="dances shorter than this are left out (%(default)s)")
    ap.add_argument("--music-tail", type=float, default=dv.MUSIC_TAIL, metavar="SECONDS",
                    help="a motion that goes on for more than this after its music is cut where the music ends (%(default)s)")
    ap.add_argument("--seed", type=int, default=SEED, help="of the hand-out order and the draw (%(default)s); a plan that is there stays")
    ap.add_argument("--title", default=TITLE, metavar="PATTERN", help="the videos' file names (%(default)s; {dance} {name} {id})")
    ap.add_argument("--drop", nargs="+", default=[], metavar="OUTFIT",
                    help="these outfits dance no more (kept in _meta/dropped.json): their video is deleted, their dance "
                         "goes to the next outfit; the lists give --why")
    ap.add_argument("--why", default="", metavar="TEXT", help="with --drop: the reason, for the lists")
    ap.add_argument("--undrop", nargs="+", default=[], metavar="OUTFIT", help="take these outfits back among the dancers")
    ap.add_argument("--keep-loose", action="store_true",
                    help="let outfits dance whose PMX has parts on bones without a parent (default: left out, see pmx_rig_check.py)")
    ap.add_argument("--prune", action="store_true", help="delete the videos of outfits that dance no more (the run names them)")
    ap.add_argument("--camera", choices=("follow", "fixed"), default="follow")
    ap.add_argument("--follow", default="", metavar="KEY=VALUE,...", help="the following camera's settings (tsquad_common.FOLLOW)")
    ap.add_argument("--size", default="", help="WIDTHxHEIGHT (default 1080x1920)")
    ap.add_argument("--samples", type=int, default=32, help="EEVEE samples per frame (%(default)s)")
    ap.add_argument("--bust-pmx", default=BUST_PMX, metavar="VARIANT",
                    help="dance <id>_VARIANT.pmx where there is one (default %(default)s: breast joints with springs); "
                         "main = always <id>.pmx")
    ap.add_argument("--no-backdrop", action="store_true", help="the plain grey background instead of the game's pictures")
    ap.add_argument("--force", action="store_true", help="render again what is there")
    ap.add_argument("--full-speed", action="store_true", help="normal process priority (default: below normal)")
    ap.add_argument("--min-free-gb", type=float, default=db.MIN_FREE_GB, metavar="GB",
                    help="a video is started only while this much memory is free, else it waits (%(default)s; 0 = never wait)")
    ap.add_argument("--roe-root", default=ROE_ROOT, help="the ROE archive (default %(default)s; or ROE_ARCHIVE_ROOT)")
    a = ap.parse_args()
    tc.parse_follow(a.follow)
    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    unknown = [k for k in kinds if k not in KIND_ZH]
    if unknown:
        raise SystemExit("--kinds: unknown %s (there are %s)" % (", ".join(unknown), ", ".join(KIND_ZH)))
    if not os.path.isdir(a.motions):
        raise SystemExit("the motion collection is not there: %s (--motions)" % a.motions)
    if not os.path.isdir(a.roe_root):
        raise SystemExit("the ROE archive is not there: %s (--roe-root, or ROE_ARCHIVE_ROOT)" % a.roe_root)
    where = db.paths(a.roe_root)
    os.makedirs(where.meta, exist_ok=True)
    a.export_root, a.log_dir = a.roe_root, os.path.join(where.meta, "logs")

    everyone = find_outfits(a.roe_root)
    names = {m["id"]: m["name"] for m in everyone}
    dropped = db.load(where.dropped, {})
    going = [m["id"] for m in find(everyone, a.drop)] if a.drop else []
    if a.drop or a.undrop:
        back = [m["id"] for m in find(everyone, a.undrop)] if a.undrop else []
        dropped = db.set_dropped(dropped, going, back, a.why)
        tc.save_json(where.dropped, dropped)
        log("dancing no more: %s" % (", ".join("%s (%s)" % (u, w or "no reason given") for u, w in sorted(dropped.items())) or "nobody"))
    wanted = [m for m in everyone if m["kind"] in kinds and m["id"] not in dropped]
    checks = db.load(os.path.join(where.meta, "rig_check.json"), {})
    loose = loose_outfits(wanted, a.roe_root, checks)
    tc.save_json(os.path.join(where.meta, "rig_check.json"), checks)
    if loose:
        log("%d outfits have parts on bones without a parent%s: %s" % (
            len(loose), " - they dance anyway (--keep-loose)" if a.keep_loose else " - left out (--keep-loose lets them dance)",
            ", ".join(sorted(loose))))
    outfits = hand_out_order([m for m in wanted if a.keep_loose or m["id"] not in loose], a.seed)

    cache = db.load(where.dances, None)
    if cache is None:                                   # the same collection's lengths, as Squad's batch read them
        cache = db.load(os.path.join(SQUAD_META, "dances.json"), {})
    dances = db.choose_dances(db.read_collection(a.motions, cache), a.min_seconds)
    tc.save_json(where.dances, cache)
    taken = taken_dances(a.taken)
    usable = {d["folder"]: d for d in dances if not d["status"]}
    offer = [f for f in usable if f not in taken]
    pictures = [] if a.no_backdrop else bg.backdrops(a.roe_root)
    if not pictures and not a.no_backdrop:
        log("no backgrounds in %s - plain grey (python roe_backgrounds.py writes them)" % bg.folder(a.roe_root))
    plan = db.draw([m["id"] for m in outfits], offer, pictures, a.seed, db.load(where.plan, {}))
    tc.save_json(where.plan, plan)
    videos = db.load(where.videos, {})
    if going:
        for line in db.prune(videos, set(videos) - set(going), where):
            log("removed %s" % line)
        tc.save_json(where.videos, videos)
    strays = [u for u, v in videos.items() if u not in plan or v.get("dance") != plan[u].get("dance")]
    if strays and a.prune:
        for line in db.prune(videos, set(videos) - set(strays), where):
            log("removed %s" % line)
        tc.save_json(where.videos, videos)
    elif strays:
        log("%d video(s) of outfits that no longer dance that dance: %s  (--prune deletes them)" % (
            len(strays), ", ".join("%s (%s)" % (u, os.path.basename(videos[u].get("video", ""))) for u in strays)))
    has = {u for u, v in videos.items() if u in plan and v.get("dance") == plan[u].get("dance")
           and v.get("video") and os.path.isfile(v["video"])}
    log("%d outfits of %s dance (%d characters); %d dances to hand out (%d usable, %d taken by %s); %d videos are there" % (
        len(outfits), "/".join(kinds), len({m["group"] for m in outfits}), len(offer), len(usable),
        len([f for f in usable if f in taken]), ", ".join(sorted({t.split("/")[0] for t in taken.values()})) or "nobody",
        len(has)))

    def finish():
        data = lists(outfits, plan, dances, videos, taken, a.motions, dropped, {} if a.keep_loose else loose, everyone)
        tc.save_json(where.data, data)
        with open(where.text, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(markdown(data))
        log("list: %s" % where.text)
        return data

    if a.plan or a.list:
        finish()
        return 0
    if a.models:
        chosen = find(outfits, a.models)
        missing = [m["id"] for m in chosen if m["id"] not in plan]
        if missing:
            log("no dance for %s (the dances ran out before them in the hand-out order)" % ", ".join(missing))
        chosen = [m for m in chosen if m["id"] in plan]
    else:
        chosen = [m for m in outfits if m["id"] in plan and (a.force or m["id"] not in has)][:max(0, a.count)]
    if not chosen:
        log("nothing to render - give outfits or --count N")
        finish()
        return 0
    if not os.path.isfile(tc.BLENDER):
        raise SystemExit("Blender not found: %s (set TSQUAD_BLENDER)" % tc.BLENDER)
    if not a.full_speed and db.step_aside():
        log("running below normal priority (--full-speed for normal)")
    failed = []
    for n, model in enumerate(chosen, 1):
        dance = usable[plan[model["id"]]["dance"]]
        log("[%d/%d] %s dances %s (%g s)" % (n, len(chosen), model["id"], dance["title"], dance["seconds"]))
        try:
            model = dict(model, pmx=dance_pmx(model, a.roe_root, a.bust_pmx))
            record = db.render(model, dance, "" if a.no_backdrop else plan[model["id"]]["backdrop"], a, where, names)
        except Exception as exc:  # noqa: BLE001 - keep going through the list
            log("FAILED %s: %s" % (model["id"], exc))
            failed.append(model["id"])
            continue
        if record.pop("kept") and model["id"] in videos:
            record = dict(videos[model["id"]], video=record["video"], thumb=record["thumb"] or videos[model["id"]].get("thumb", ""))
        record.update(character=model["group"], outfit=model["outfit"], kind=model["kind"],
                      pmx=os.path.basename(model["pmx"]))
        videos[model["id"]] = record
        tc.save_json(where.videos, videos)               # after every video: a stopped run loses nothing
        log("%s: %s  (%s s of video, rendered in %s s)" % (
            model["id"], os.path.basename(record["video"]), record["seconds"], record.get("render_seconds")))
    data = finish()
    s = data["summary"]
    log("done: %d of %d outfits with a dance have a video, %d failed this run%s" % (
        s["with_video"], s["with_dance"], len(failed), " (%s)" % ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
