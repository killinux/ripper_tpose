"""Put an MMD motion (.vmd) on an exported unit and render it to a video with its music.

    python dance_video.py 1_asagi --vmd "E:\\Downloads\\mmd\\some dance"      # a folder: its .vmd and its music
    python dance_video.py 1_asagi --vmd dance.vmd --bgm song.wav --name mydance
    python dance_video.py asagi kirara --vmd <folder> --jobs 2              # several units, two at a time
    python dance_video.py 1_asagi --vmd <folder> --stills 6 --no-video      # only six check frames (fast)
    python dance_video.py 1_asagi --vmd <folder> --view chest               # a close-up that rides the chest
    python dance_video.py 1_asagi --vmd <folder> --bust bounce_hz=3,ratio=0.2   # try other breast physics
    python dance_video.py kirara --vmd <folder> --title "{dance}-{name}"       # named "<dance>-<character>.mp4"

The unit must have its PMX already (python export_model.py <id> --pmx).  The PMX is imported back into
Blender 3.6 with mmd_tools - physics, expressions and toon edges included - the motion is put on it, the
physics is baked and the motion rendered (render_dance_blender.py; EEVEE, lit the way MMD shows a toon
model, a fixed camera that frames the whole motion, portrait 1080 x 1920 by default):

    <export-root>/<Character>/video/<id>/<id>_<motion>.mp4      the video (H.264 + AAC)
    <export-root>/<Character>/video/<id>/<id>_<motion>.blend    the same scene: model, motion, baked physics,
                                                                images and music packed - open it and press play
    <export-root>/<Character>/video/<id>/<id>_<motion>.json     what was rendered from what

Nothing is written next to the motion files.  An existing video is kept unless --force.

The physics runs the way MMD runs it (--physics mmd; "blender" = the stiffer way mmd_tools leaves the
joints).  --bust key=value,... changes the breast physics for the video only, to try values quickly
(the settings are tsquad_blender.BUST); the file name then gets "_bust-..." so that it sits next to the
plain one.  When a setting is right, put it into the PMX: export_model.py <id> --pmx --reconvert --bust ...
The report (.json, and the last line of the run) says how far the breasts travelled, in cm.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import math
import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402
from export_model import bust_settings, run_blender  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "render_dance_blender.py")
AUDIO = (".wav", ".mp3", ".ogg", ".flac", ".m4a")
NOT_A_DANCE = re.compile(r"camera|cam\b|カメラ|镜头|鏡頭|表情|facial|lip", re.IGNORECASE)
# what a collection adds to a dance's name: a "[notice]", "(2025.6.9)" / "2026.1.25" / "202511.2",
# "by小王动画" ("y小王动画", "by小王崩坏原神"), " (2)" of a copied folder
NOTICE = re.compile(r"\s*[\[【][^\]】]*[\]】]\s*")
DATE = re.compile(r"\s*[(（]?\s*20\d\d\.?\d{1,2}\.\d{1,2}\s*[)）]?")
AUTHOR = re.compile(r"\s*b?y\s*小王(?:动画|崩坏原神)?", re.IGNORECASE)
COPY = re.compile(r"\s*[(（]\d[)）]\s*$")
TITLE = "{id}_{motion}"                                # --title: the video's file name
FPS = 30                                               # of a .vmd
# the bones a dance is made of: their last key is where it ends (dance_frames)
BODY = ("全ての親", "センター", "グルーブ", "上半身", "上半身2", "下半身", "首", "頭", "左肩", "右肩", "左腕", "右腕",
        "左ひじ", "右ひじ", "左手首", "右手首", "左足", "右足", "左ひざ", "右ひざ", "左足ＩＫ", "右足ＩＫ")
MUSIC_TAIL = 2.0                                       # --music-tail: seconds a dance may go on after its music
log = tc.log


def pick_motion(path: str, bgm: str = "") -> tuple[str, str]:
    """(vmd file, music file or "") for a .vmd or a folder holding one.  In a folder with several .vmd the
    camera / facial ones are passed over; the music is the audio file named like the motion, else the only
    audio file there is."""
    path = os.path.abspath(path)
    if os.path.isdir(path):
        names = sorted(os.listdir(path))
        vmds = [n for n in names if n.lower().endswith(".vmd")]
        dances = [n for n in vmds if not NOT_A_DANCE.search(n)] or vmds
        if len(dances) != 1:
            raise SystemExit("%s: %s - name the .vmd itself" % (
                path, "no .vmd in this folder" if not vmds else "several motions (%s)" % ", ".join(dances)))
        vmd = os.path.join(path, dances[0])
    elif os.path.isfile(path) and path.lower().endswith(".vmd"):
        vmd = path
    else:
        raise SystemExit("not a .vmd file or a folder with one: %s" % path)
    if bgm:
        if not os.path.isfile(bgm):
            raise SystemExit("music not found: %s" % bgm)
        return vmd, os.path.abspath(bgm)
    folder, stem = os.path.dirname(vmd), os.path.splitext(os.path.basename(vmd))[0]
    audio = [n for n in sorted(os.listdir(folder)) if n.lower().endswith(AUDIO)]
    same = [n for n in audio if os.path.splitext(n)[0] == stem]
    pick = same[0] if same else audio[0] if len(audio) == 1 else ""
    return vmd, os.path.join(folder, pick) if pick else ""


def motion_name(vmd: str, name: str = "") -> str:
    """A file-name-safe label for the motion: --name, else the .vmd's own name."""
    text = name or os.path.splitext(os.path.basename(vmd))[0]
    return re.sub(r'[<>:"/\\|?*\s]+', "_", text).strip("._") or "motion"


def dance_frames(path: str) -> int:
    """The last frame a .vmd keys on a body bone (BODY) - where the dance ends.  Face and eye keys often run on
    for seconds after it (what is left of a longer take); a model that has those morphs would stand still through
    them, with the music over.  A motion that keys no body bone: its last bone key.  0: not a .vmd."""
    import numpy as np

    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 54:
        return 0
    count = struct.unpack_from("<I", data, 50)[0]
    if not count or 54 + count * 111 > len(data):
        return 0
    block = np.frombuffer(data, dtype=np.uint8, count=count * 111, offset=54).reshape(count, 111)
    frames = block[:, 15:19].copy().view("<u4")[:, 0]
    names, which = np.unique(block[:, :15].copy().view("V15")[:, 0], return_inverse=True)
    wanted = {name.encode("shift_jis") for name in BODY}
    body = np.array([n.tobytes().split(b"\0")[0] in wanted for n in names])[which.ravel()]   # after the zero: anything
    return int(frames[body].max() if body.any() else frames.max())


def audio_seconds(path: str) -> float:
    """How long a music file plays (ffprobe); 0.0 when that cannot be found out."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, timeout=60).stdout
        return float(out.decode("ascii", "replace").strip() or 0.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def video_frames(dance: int, music: float = 0.0, tail: float = MUSIC_TAIL) -> int:
    """How many frames of a motion to render: up to its last body key (`dance`, of dance_frames).  A motion that
    goes on for more than `tail` seconds after its music (the dance twice in one file, a stray key far out) is
    rendered as far as the music plays.  0: not known - whatever the file keys."""
    if dance <= 0:
        return 0
    frames = dance + 1
    if music > 0 and frames / FPS - music > tail:
        frames = int(math.ceil(music * FPS))
    return frames


def clean_name(text: str) -> str:
    """A folder's or a file's name without the release date, the author's signature and bracketed notices."""
    for pattern in (NOTICE, AUTHOR, DATE, COPY):
        text = pattern.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ._-")


def dance_title(vmd: str, folder_is_the_dance: bool = True) -> str:
    """The dance's own name, for file names people read: the name of the folder the motion came in (collections
    keep one dance per folder), without the release date, the author's signature and bracketed notices -
    "PUBG胜利之舞爱的主打歌(2025.6.9)by小王动画" -> "PUBG胜利之舞爱的主打歌".  A variant in that folder is told
    apart by its file name ("pubg胜利之舞146 2026.2.7by小王动画/左.vmd" -> "pubg胜利之舞146 左").  A motion that
    was named as a loose file: its own name, cleaned the same way."""
    stem = clean_name(os.path.splitext(os.path.basename(vmd))[0])
    folder = clean_name(os.path.basename(os.path.dirname(os.path.abspath(vmd)))) if folder_is_the_dance else ""
    if not folder or not stem or folder in stem:
        return stem or folder or "motion"
    return folder if stem in folder else "%s %s" % (folder, stem)


def person_names(models: list[dict]) -> dict[str, str]:
    """{unit id: the name to show}: the unit's name; where several units share one (a character's other
    costumes: 1_asagi, 253_asagi) the lowest number keeps it and the others add their number ("Asagi 253")."""
    first = {}
    for m in sorted(models, key=lambda m: (m.get("number") or 0, m["id"])):
        first.setdefault(m["name"], m["id"])
    return {m["id"]: m["name"] if first[m["name"]] == m["id"] else "%s %s" % (m["name"], m.get("number") or m["id"])
            for m in models}


def file_stem(pattern: str, **fields) -> str:
    """The video's file name without the extension, from --title: {id}, {name} (person_names), {motion} (the
    .vmd's name or --name, made file-safe), {dance} (dance_title).  Characters Windows refuses become "_"."""
    try:
        text = pattern.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        raise SystemExit("--title %r: %s - the fields are {id} {name} {motion} {dance}" % (pattern, exc))
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text).strip(" .") or "video"


def find_backdrop(text: str, root: str = tc.EXPORT_ROOT) -> str:
    """The picture --backdrop names: a file, or a piece of the name of one of the game's own backgrounds in
    <root>/_backgrounds (export_backgrounds.py) - "夜店舞台", "S018_B", "霓虹都市"."""
    if os.path.isfile(text):
        return os.path.abspath(text)
    folder = os.path.join(root, "_backgrounds")
    names = [n for n in sorted(os.listdir(folder)) if n.lower().endswith(".png")] if os.path.isdir(folder) else []
    hits = [n for n in names if text.lower() in n.lower()]
    exact = [n for n in hits if text.lower() in (n.lower(), os.path.splitext(n)[0].lower())]
    if len(exact) == 1 or len(hits) == 1:
        return os.path.join(folder, (exact or hits)[0])
    if not hits:
        raise SystemExit("--backdrop: %r is neither a file nor part of a name in %s (python export_backgrounds.py "
                         "writes that folder)" % (text, folder))
    raise SystemExit("--backdrop: %r fits %d pictures - say more of the name: %s" % (text, len(hits), ", ".join(hits[:12])))


def video_paths(model: dict, root: str, name: str, view: str = "full", bust: str | None = None,
                out_dir: str = "", backdrop: str = "", stem: str = "", plain: bool = False) -> tuple[str, str]:
    """(folder, path of the .mp4) - <root>/<Character>/video/<id>/<id>_<motion>[_chest][_bust-...][_bg-...].mp4;
    `stem` (file_stem of --title) stands in for "<id>_<motion>"; `plain`: without the tails (--plain-name)."""
    folder = out_dir or tc.model_dir(model, root, "video")
    tail = "" if view == "full" else "_" + re.sub(r"[^0-9A-Za-z]+", "", view)
    if bust is not None:
        tail += "_bust-" + (re.sub(r"[^0-9A-Za-z.=]+", "-", bust).strip("-") or "default")
    if backdrop:
        picture = os.path.splitext(os.path.basename(backdrop))[0]
        tail += "_bg-" + (re.sub(r'[<>:"/\\|?*\s]+', "_", picture).strip("._")[-40:] or "picture")
    return folder, os.path.join(folder, "%s%s.mp4" % (stem or "%s_%s" % (model["id"], name), "" if plain else tail))


def render_one(model: dict, vmd: str, bgm: str, name: str, a) -> dict:
    pmx = os.path.join(tc.model_dir(model, a.export_root, "pmx"), model["id"] + ".pmx")
    if not os.path.isfile(pmx):
        raise RuntimeError("no PMX yet - run: python export_model.py %s --pmx" % model["id"])
    stem = file_stem(a.title, id=model["id"], name=a.people.get(model["id"], model["name"]), motion=name, dance=a.dance)
    folder, out = video_paths(model, a.export_root, name, a.view, a.bust, a.out_dir, a.backdrop, stem,
                              getattr(a, "plain_name", False))
    if os.path.isfile(out) and not (a.force or a.no_video):
        log("%s: %s is there - --force to redo" % (model["id"], out))
        return {"id": model["id"], "video": out, "skipped": True}
    os.makedirs(folder, exist_ok=True)
    cmd = ["-b", "--python", WORKER, "--", "--pmx", pmx, "--vmd", vmd, "--out", out, "--view", a.view,
           "--physics", a.physics, "--margin", str(a.margin), "--samples", str(a.samples), "--camera", a.camera]
    if a.follow:
        cmd += ["--follow", a.follow]
    if a.size:
        cmd += ["--size", a.size]
    bust = spring = None
    if a.bust is not None:                              # the same steps as export_model.py --pmx --bust
        bust, spring = bust_settings(model, a)
        cmd += ["--bust", tc.bust_text(bust)]
    if bgm:
        cmd += ["--bgm", bgm]
    if a.backdrop:
        cmd += ["--backdrop", a.backdrop, "--backdrop-as", a.backdrop_as, "--backdrop-fov", str(a.backdrop_fov),
                "--backdrop-turn", str(a.backdrop_turn), "--backdrop-tilt", str(a.backdrop_tilt),
                "--shadow", str(a.shadow)]
    frames = a.frames or video_frames(dance_frames(vmd), audio_seconds(bgm) if bgm else 0.0,
                                      getattr(a, "music_tail", MUSIC_TAIL))
    if frames:
        cmd += ["--frames", str(frames)]
    if a.stills:
        cmd += ["--stills", str(a.stills)]
    for flag in ("no_video", "no_edge", "no_blend"):
        if getattr(a, flag):
            cmd.append("--" + flag.replace("_", "-"))
    t0 = time.time()
    log("%s: %s on %s ..." % (model["id"], os.path.basename(vmd), os.path.basename(pmx)))
    log_path = os.path.join(tc.work_dir(a.export_root), "logs", "%s.dance.log" % model["id"])
    rep, code = run_blender(cmd, "TSQ_DANCE=", log_path, timeout=4 * 3600)
    if rep is None or (not a.no_video and not rep.get("video")):
        raise RuntimeError("Blender failed (exit %d), log: %s" % (code, log_path))
    rep.update(id=model["id"], seconds=round(time.time() - t0, 1), time=time.strftime("%Y-%m-%d %H:%M:%S"))
    if bust is not None:
        rep.update(bust_settings={k: bust[k] for k in tc.BUST}, bust_game=spring)
    if not a.no_video:
        tc.save_json(os.path.splitext(out)[0] + ".json", rep)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("models", nargs="+", help="ids / unit numbers / names (as in list_models.py); each needs its PMX")
    ap.add_argument("--vmd", required=True, help="the motion: a .vmd, or a folder holding one (and its music)")
    ap.add_argument("--bgm", default="", help="music; default: the audio file next to the .vmd")
    ap.add_argument("--no-bgm", action="store_true", help="a silent video")
    ap.add_argument("--name", default="", help="label of the motion in the file names (default: the .vmd's name)")
    ap.add_argument("--title", default=TITLE, metavar="PATTERN",
                    help="the video's file name, from {id} {name} {motion} {dance} (default \"%s\"); "
                         "\"{dance}-{name}\" = the dance's name without date / author, then the character's name"
                         % TITLE.replace("%", "%%"))
    ap.add_argument("--plain-name", action="store_true",
                    help="the file name is --title and nothing else: no _chest / _bust-... / _bg-... behind it")
    ap.add_argument("--size", default="", help="WIDTHxHEIGHT of the video (default 1080x1920, portrait; "
                    "1080x1080 for --view chest)")
    ap.add_argument("--view", default="full", help="full (default): the whole figure, fixed camera | chest: a close-up "
                    "that rides the upper body | chest:60: the same from 60 degrees to the model's left")
    ap.add_argument("--camera", choices=("follow", "fixed"), default="follow",
                    help="--view full: follow (default) = the camera goes with the dancer's steps and the picture is as "
                         "wide as the body needs | fixed = it stands still and holds everything the model touches "
                         "during the motion (a dance that walks, or long ribbons, make the figure small)")
    ap.add_argument("--follow", default="", metavar="KEY=VALUE,...",
                    help="the following camera's settings, e.g. cover=100,margin_m=0.2 (tsquad_common.FOLLOW: smooth_s, "
                         "cover, margin_m, head_room)")
    ap.add_argument("--physics", choices=("mmd", "blender"), default="mmd",
                    help="mmd (default): the joints as MMD runs them | blender: as mmd_tools leaves them (stiffer)")
    ap.add_argument("--bust", default=None, metavar="KEY=VALUE,...",
                    help="other breast physics for this video only, e.g. bounce_hz=3,ratio=0.2 (tsquad_common.BUST; "
                         "scaled per unit like export_model.py does; --bust \"\" = the current defaults on an older PMX)")
    ap.add_argument("--backdrop", default="", metavar="PICTURE",
                    help="a picture behind the model: a file, or a piece of the name of one of the game's backgrounds "
                         "in <export-root>\\_backgrounds (export_backgrounds.py), e.g. 夜店舞台 or S018_B.  It fills "
                         "the frame; of a panorama (twice as wide as high, the 全景_ ones) a view is taken")
    ap.add_argument("--backdrop-as", choices=("auto", "flat", "view", "world"), default="auto",
                    help="auto (default): a view of a panorama, any other picture flat | world: the panorama as the "
                         "world around the scene (turns with the camera; blurred by the long lens)")
    ap.add_argument("--backdrop-fov", type=float, default=70.0, metavar="DEG",
                    help="panorama: how many degrees of it the view shows from top to bottom (70)")
    ap.add_argument("--backdrop-turn", type=float, default=0.0, metavar="DEG",
                    help="panorama: look this many degrees to the right of its middle")
    ap.add_argument("--backdrop-tilt", type=float, default=0.0, metavar="DEG", help="panorama: look this many degrees up")
    ap.add_argument("--shadow", type=float, default=0.45, help="with --backdrop: how dark the shadow on the ground is (0 = none)")
    ap.add_argument("--out-dir", default="", help="write the video here instead of <Character>/video/<id>")
    ap.add_argument("--frames", type=int, default=0,
                    help="only the first N frames of the motion (default: up to the last key of the body bones - "
                         "face keys left over after the dance are not waited for)")
    ap.add_argument("--music-tail", type=float, default=MUSIC_TAIL, metavar="SECONDS",
                    help="a motion that goes on for more than this after its music has ended is rendered as far as "
                         "the music plays (%(default)s)")
    ap.add_argument("--margin", type=int, default=30, help="lead-in frames the physics gets before the motion (30)")
    ap.add_argument("--samples", type=int, default=32, help="EEVEE samples per frame (32)")
    ap.add_argument("--stills", type=int, default=0, help="also render N check frames into <video>_stills\\")
    ap.add_argument("--no-video", action="store_true", help="with --stills: the check frames only")
    ap.add_argument("--no-edge", action="store_true", help="no toon outline")
    ap.add_argument("--no-blend", action="store_true", help="do not keep the .blend next to the video")
    ap.add_argument("--jobs", type=int, default=1, metavar="N", help="render N units at a time")
    ap.add_argument("--force", action="store_true", help="redo a video that is there")
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    if a.no_video and not a.stills:
        ap.error("--no-video needs --stills N")
    tc.parse_bust(a.bust)                               # a misspelt setting stops here
    tc.parse_follow(a.follow)
    if a.backdrop:
        a.backdrop = find_backdrop(a.backdrop, a.export_root)

    tc.check_tools(need_blender=True)
    vmd, bgm = pick_motion(a.vmd, a.bgm)
    if a.no_bgm:
        bgm = ""
    name = motion_name(vmd, a.name)
    a.dance = a.name or dance_title(vmd, folder_is_the_dance=os.path.isdir(a.vmd))
    everyone = tc.discover_models(tc.catalog_assets(a.export_root), a.export_root)
    a.people = person_names(everyone)
    models = tc.find_models(everyone, a.models)
    log("motion %s, music %s, %d unit(s)" % (vmd, bgm or "none", len(models)))
    failed, done = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        jobs = {pool.submit(render_one, m, vmd, bgm, name, a): m for m in models}
        for job in concurrent.futures.as_completed(jobs):
            model = jobs[job]
            try:
                rep = job.result()
            except Exception as exc:  # noqa: BLE001 - keep going through the list
                log("FAILED %s: %s" % (model["id"], exc))
                failed.append(model["id"])
                continue
            done.append(rep)
            if rep.get("skipped"):
                continue
            log("%s: %d frames, %s rigid bodies, %s bones on physics, loose bodies stay within %.2f m of the hips, %.0f s" % (
                rep["id"], rep.get("motion_frames", 0), rep.get("rigid_bodies"), rep.get("bones_on_physics"),
                rep.get("max_rigid_body_distance_from_hips_m", 0.0), rep["seconds"]))
            for fit in (rep.get("bust_override") or [])[:1]:
                log("  breast physics for this video: size %s cm, factor %s -> travel %s cm, %s Hz, ratio %s" % (
                    fit.get("size_cm"), fit.get("factor"), fit.get("travel_cm"), fit.get("hz"), fit.get("ratio")))
            for side, m in (rep.get("bust_motion") or {}).items():
                log("  %s travels %s cm (left-right, front-back, up-down), %.2f cm a frame (median), rests %s" % (
                    side, m["travel_cm"], m["speed_cm_per_frame"]["median"], m["settles_at_cm"]))
            for key in ("video", "blend"):
                if rep.get(key):
                    log("  %s %s" % (key.upper(), rep[key]))
            if rep.get("stills"):
                log("  STILLS %s" % os.path.dirname(rep["stills"][0]))
    log("done: %d rendered, %d skipped, %d failed" % (
        sum(1 for r in done if not r.get("skipped")), sum(1 for r in done if r.get("skipped")), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
