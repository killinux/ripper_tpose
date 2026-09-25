# -*- coding: utf-8 -*-
"""Batch-fetch one Nexus author's asset mods for FF7 Remake / Rebirth without an API key.

Nexus only hands out download links to Premium API keys, so the files themselves are
downloaded by the user in the browser.  This script does everything around that:

  select   ask the public v2 GraphQL API (no key, no cookies) for the author's mods in the
           given games, keep the files that can carry textures/meshes, write selection.json
  page     write downloads.html: one direct link per file (opens that file's download page),
           with a tick for every file already sitting in the downloads folder
  collect  copy each finished download out of the downloads folder (never touching the
           original), check its size against Nexus, and unpack it next to the copy
  watch    page + collect every N seconds until every selected file is collected

Usage (the FF7 batch of 2026-09-25):
  python nexus_mod_batch.py select --uploader Gantz79 --games finalfantasy7remake,finalfantasy7rebirth
  python nexus_mod_batch.py watch
Everything lands in --root (default D:/ff7_mods): selection.json, downloads.html, collected.json,
remake/<modId>_<slug>/<fileId>_<slug>/{archive, x/...}, rebirth/...
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

API = "https://api.nexusmods.com/v2/graphql"
GAME_DIRS = {"finalfantasy7remake": "remake", "finalfantasy7rebirth": "rebirth"}
UNRAR = r"C:\Program Files\WinRAR\UnRAR.exe"
SEVENZ = r"E:\tools\7zr.exe"


def post(query, variables=None):
    req = urllib.request.Request(
        API, data=json.dumps({"query": query, "variables": variables or {}}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "ripper-tpose/1.0 (local model-export tooling)"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        out = json.loads(fh.read().decode("utf-8"))
    if "errors" in out:
        raise RuntimeError(json.dumps(out["errors"], ensure_ascii=False)[:800])
    return out["data"]


def slug(text, limit=48):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:limit].rstrip("_") or "x"


# ------------------------------------------------------------------ select
MODS_Q = """
query M($f: ModsFilter, $o: Int) {
  mods(filter: $f, offset: $o, count: 20, sort: [{createdAt: {direction: ASC}}]) {
    totalCount
    nodes { modId uid name summary adultContent createdAt updatedAt downloads endorsements
            modCategory { name } uploader { name } game { id name domainName } pictureUrl thumbnailUrl }
  }
}"""
FILES_Q = """
query F($modId: ID!, $gameId: ID!) {
  modFiles(modId: $modId, gameId: $gameId) { fileId name version sizeInBytes category uri date primary }
}"""


MOD_Q = """
query O($modId: ID!, $gameId: ID!) {
  mod(modId: $modId, gameId: $gameId) { modId uid name summary adultContent createdAt updatedAt downloads
    endorsements modCategory { name } uploader { name } game { id name domainName } pictureUrl thumbnailUrl }
}"""
GAME_Q = """query G($d: String!) { game(domainName: $d) { id name domainName } }"""


def select_explicit(a):
    """--mods finalfantasy7remake:967,finalfantasy7rebirth:817=4121+4122 (file ids after '=')."""
    selected = []
    for spec in a.mods.split(","):
        spec = spec.strip()
        if not spec:
            continue
        head, _, file_ids = spec.partition("=")
        domain, _, mod_id = head.partition(":")
        game = post(GAME_Q, {"d": domain})["game"]
        mod = post(MOD_Q, {"modId": mod_id, "gameId": str(game["id"])})["mod"]
        files = post(FILES_Q, {"modId": mod_id, "gameId": str(game["id"])})["modFiles"]
        wanted = {int(x) for x in file_ids.split("+") if x.strip()}
        if wanted:
            keep = [f for f in files if int(f["fileId"]) in wanted]
        else:
            keep = [f for f in files if f["category"] in ("MAIN", "OPTIONAL")]
        selected.append(dict(mod, category=(mod["modCategory"] or {}).get("name") or "", files=keep,
                             all_uris=[f["uri"] for f in files]))
        time.sleep(0.2)
    return selected


def cmd_select(a):
    if a.mods:
        selected = select_explicit(a)
        games = []
        for m in selected:
            if m["game"]["domainName"] not in games:
                games.append(m["game"]["domainName"])
        out = {"uploader": a.title or "selected mods", "games": games, "min_size": 0,
               "selected": selected, "dropped": [], "made": time.strftime("%Y-%m-%d %H:%M")}
        os.makedirs(a.root, exist_ok=True)
        with open(os.path.join(a.root, "selection.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print("selected %d mods / %d files" % (len(selected), sum(len(m["files"]) for m in selected)))
        return
    mods = []
    for domain in a.games.split(","):
        flt = {"uploader": [{"value": a.uploader, "op": "EQUALS"}],
               "gameDomainName": [{"value": domain, "op": "EQUALS"}]}
        offset, total = 0, None
        while total is None or offset < total:
            page = post(MODS_Q, {"f": flt, "o": offset})["mods"]
            total = page["totalCount"]
            mods += [m for m in page["nodes"] if m["uploader"]["name"].lower() == a.uploader.lower()]
            offset += 20
            if not page["nodes"]:
                break
    skip_cats = {c.strip() for c in a.skip_categories.split(",") if c.strip()}
    skip_mods = {int(x) for x in a.skip_mods.split(",") if x.strip()}
    selected, dropped = [], []
    for m in mods:
        cat = (m["modCategory"] or {}).get("name") or ""
        if cat in skip_cats or m["modId"] in skip_mods:
            dropped.append({"modId": m["modId"], "name": m["name"], "why": "category %s / skipped" % cat})
            continue
        files = post(FILES_Q, {"modId": str(m["modId"]), "gameId": str(m["game"]["id"])})["modFiles"]
        time.sleep(0.2)
        keep = [f for f in files if f["category"] in ("MAIN", "OPTIONAL")
                and int(f["sizeInBytes"] or 0) >= a.min_size]
        if not keep:
            dropped.append({"modId": m["modId"], "name": m["name"],
                            "why": "no current file >= %d bytes (data-only mod)" % a.min_size})
            continue
        selected.append(dict(m, category=cat, files=keep))
    os.makedirs(a.root, exist_ok=True)
    out = {"uploader": a.uploader, "games": a.games.split(","), "min_size": a.min_size,
           "selected": selected, "dropped": dropped, "made": time.strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(a.root, "selection.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    n = sum(len(m["files"]) for m in selected)
    size = sum(int(f["sizeInBytes"]) for m in selected for f in m["files"])
    print("selected %d mods / %d files / %.0f MB; dropped %d mods" % (len(selected), n, size / 1e6, len(dropped)))


# ------------------------------------------------------------------ helpers
def load_selection(root):
    with open(os.path.join(root, "selection.json"), encoding="utf-8") as fh:
        return json.load(fh)


def target_dir(root, mod, f):
    game = GAME_DIRS.get(mod["game"]["domainName"], mod["game"]["domainName"])
    return os.path.join(root, game, "%d_%s" % (mod["modId"], slug(mod["name"])),
                        "%d_%s" % (int(f["fileId"]), slug(f["name"])))


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def find_download(downloads, f, other_uris=()):
    """The browser keeps the archive name Nexus serves; a second download may add ' (1)'.
    Newer uploads only have a storage hash as uri; the browser then saves
    "<file name> <modId> <version> <time> <random>.<ext>" (spaces; older ones use hyphens),
    so match on the mod id token + name prefix and skip names that belong to the mod's
    other (not selected) files."""
    want = f["uri"].lower()
    size = int(f["sizeInBytes"] or 0)
    hashed = "/" in want or "." not in want
    prefix = norm(f["name"])
    tag = re.compile("[ -]%d[ -]" % f["_modId"])
    others = {u.lower() for u in other_uris if u.lower() != want}
    hits = []
    for name in os.listdir(downloads):
        path = os.path.join(downloads, name)
        if not os.path.isfile(path) or name.endswith((".crdownload", ".part", ".tmp")):
            continue
        base = re.sub(r" \(\d+\)(?=\.[^.]+$)", "", name).lower()
        if base == want:
            hits.append(path)
        elif hashed and base not in others and tag.search(base):
            stem = norm(tag.split(base, 1)[0])
            if stem and (prefix.startswith(stem) or stem.startswith(prefix)):
                hits.append(path)
    for p in hits:
        if not size or os.path.getsize(p) == size:
            return p, None
    if hits:
        return None, "size %d != %d" % (os.path.getsize(hits[0]), size)
    return None, None


def unpack(archive, dest):
    os.makedirs(dest, exist_ok=True)
    low = archive.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
        return
    if low.endswith(".rar"):
        cmd = [UNRAR, "x", "-o+", "-y", "-idq", archive, dest + os.sep]
    elif low.endswith(".7z"):
        cmd = [SEVENZ, "x", "-y", "-o" + dest, archive]
    else:
        raise RuntimeError("unknown archive type: " + archive)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("%s exit %d: %s" % (os.path.basename(cmd[0]), r.returncode,
                                               (r.stdout + r.stderr).decode("utf-8", "replace")[-400:]))


# ------------------------------------------------------------------ collect
def cmd_collect(a, quiet=False):
    sel = load_selection(a.root)
    state_path = os.path.join(a.root, "collected.json")
    state = {}
    if os.path.isfile(state_path):
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    new = 0
    for m in sel["selected"]:
        for f in m["files"]:
            key = str(f["fileId"])
            if state.get(key, {}).get("status") == "ok":
                continue
            src, problem = find_download(a.downloads, dict(f, _modId=m["modId"]), m.get("all_uris", ()))
            if not src:
                if problem:
                    state[key] = {"status": "bad_size", "detail": problem}
                continue
            dest = target_dir(a.root, m, f)
            os.makedirs(dest, exist_ok=True)
            copy = os.path.join(dest, os.path.basename(src) if "/" in f["uri"] else f["uri"])
            try:
                shutil.copy2(src, copy)          # copy out; the original in Downloads stays untouched
                unpack(copy, os.path.join(dest, "x"))
                files = []
                for dp, _dn, fn in os.walk(os.path.join(dest, "x")):
                    files += [os.path.relpath(os.path.join(dp, x), dest) for x in fn]
                state[key] = {"status": "ok", "modId": m["modId"], "game": m["game"]["domainName"],
                              "file": f["name"], "dir": dest, "archive": copy, "files": sorted(files)}
                new += 1
                if not quiet:
                    print("collected", m["modId"], f["name"], "->", len(files), "files", flush=True)
            except Exception as exc:                # keep going; the page shows the error
                state[key] = {"status": "error", "detail": str(exc)[:300]}
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, state_path)
    return state, new


# ------------------------------------------------------------------ page
CSS = """
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a64; --line:#e3e0d8; --ok:#1f7a3a; --bad:#b3261e;
        --link:#1a56b0; --visited:#7a4bb0; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#171716; --fg:#ecebe6;
        --muted:#9d9b93; --line:#33322e; --ok:#5cc47e; --bad:#ff8a80; --link:#8ab4f8; --visited:#c29df2; } }
:root[data-theme="dark"] { --bg:#171716; --fg:#ecebe6; --muted:#9d9b93; --line:#33322e; --ok:#5cc47e;
        --bad:#ff8a80; --link:#8ab4f8; --visited:#c29df2; }
body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, "Microsoft YaHei", sans-serif;
       margin:0 auto; max-width:980px; padding:16px; }
h1 { font-size:22px; margin:8px 0; }
h2 { margin:28px 0 8px; border-bottom:1px solid var(--line); padding-bottom:4px; }
h3 { font-size:15px; margin:14px 0 4px; }
small, .meta { color:var(--muted); font-weight:normal; font-size:13px; }
ul { margin:0; padding-left:20px; } li { margin:2px 0; }
a { color:var(--link); } a:visited { color:var(--visited); }
.ok { color:var(--ok); font-weight:600; } .bad { color:var(--bad); font-weight:600; } .todo { color:var(--muted); }
li.ok a { text-decoration:line-through; color:var(--muted); }
.box { border:1px solid var(--line); border-radius:8px; padding:10px 14px; margin:12px 0; }
.bar { height:8px; background:var(--line); border-radius:4px; overflow:hidden; }
.bar i { display:block; height:100%; background:var(--ok); }
"""
MARKS = {"ok": '<span class="ok">已下载</span>',
         "bad_size": '<span class="bad">大小不对，请重下</span>',
         "error": '<span class="bad">解压失败</span>'}


def cmd_page(a, state=None):
    sel = load_selection(a.root)
    if state is None:
        p = os.path.join(a.root, "collected.json")
        state = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}

    def status(f):
        return state.get(str(f["fileId"]), {}).get("status")

    total = sum(len(m["files"]) for m in sel["selected"])
    done = sum(1 for m in sel["selected"] for f in m["files"] if status(f) == "ok")
    parts = []
    for domain in sel["games"]:
        mods = [m for m in sel["selected"] if m["game"]["domainName"] == domain]
        if not mods:
            continue
        n = sum(len(m["files"]) for m in mods)
        ok = sum(1 for m in mods for f in m["files"] if status(f) == "ok")
        parts.append("<h2>%s <small>%d / %d</small></h2>" % (html.escape(mods[0]["game"]["name"]), ok, n))
        for m in sorted(mods, key=lambda m: (m["category"], m["modId"])):
            rows = []
            for f in m["files"]:
                s = status(f)
                url = "https://www.nexusmods.com/%s/mods/%d?tab=files&file_id=%d" % (domain, m["modId"], int(f["fileId"]))
                rows.append('<li class="%s"><a href="%s" target="_blank" rel="noopener">%s</a> '
                            '<span class="meta">%s · %s</span> %s</li>'
                            % (s or "todo", url, html.escape(f["name"]), f["category"],
                               ("%.1f MB" % (int(f["sizeInBytes"]) / 1e6)) if f["sizeInBytes"] else "大小未知",
                               MARKS.get(s, '<span class="todo">未下载</span>')))
            parts.append('<section><h3><a href="https://www.nexusmods.com/%s/mods/%d" target="_blank" '
                         'rel="noopener">%s</a> <span class="meta">#%d · %s</span></h3><ul>%s</ul></section>'
                         % (domain, m["modId"], html.escape(m["name"]), m["modId"],
                            html.escape(m["category"]), "".join(rows)))
    head = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Nexus mod downloads</title><style>' + CSS + '</style></head><body>')
    intro = ('<h1>Nexus mod 下载清单 <small>%s</small></h1><div class="box">'
             '<p>已下载 <b>%d / %d</b>(刷新页面更新；上次检查 %s)</p>'
             '<div class="bar"><i style="width:%.1f%%"></i></div>'
             '<p>点文件名 → 在打开的页面点 <b>Slow download</b>,等几秒自动开始 → 存到默认的 '
             '<code>E:\\Downloads</code>,不用改名。点过的链接变紫色；下完后后台脚本会自动复制出来解压，'
             '刷新本页就显示「已下载」。弹出「需要其他文件」时直接继续下载即可。</p></div>'
             % (html.escape(sel["uploader"]), done, total, time.strftime("%H:%M:%S"), 100.0 * done / max(total, 1)))
    out = os.path.join(a.root, "downloads.html")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(head + intro + "\n".join(parts) + "</body></html>")
    os.replace(tmp, out)
    return done, total


def cmd_watch(a):
    t_end = time.time() + a.hours * 3600
    last = -1
    while True:
        state, _new = cmd_collect(a)
        done, total = cmd_page(a, state)
        if done != last:
            print(time.strftime("%H:%M:%S"), "collected %d / %d" % (done, total), flush=True)
            last = done
        if done >= total or time.time() > t_end:
            break
        time.sleep(a.every)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("select", "page", "collect", "watch"))
    ap.add_argument("--root", default=r"D:\ff7_mods")
    ap.add_argument("--downloads", default=r"E:\Downloads")
    ap.add_argument("--uploader", default="Gantz79")
    ap.add_argument("--games", default="finalfantasy7remake,finalfantasy7rebirth")
    ap.add_argument("--mods", default="", help="explicit list instead of --uploader: "
                    "domain:modId[=fileId+fileId],... (no file ids = every MAIN/OPTIONAL file)")
    ap.add_argument("--title", default="", help="page title for an explicit --mods list")
    ap.add_argument("--skip-categories", default="Gameplay,Audio")
    ap.add_argument("--skip-mods", default="754", help="mod ids to leave out (754 = VR stage colours: a level, not a model)")
    ap.add_argument("--min-size", type=int, default=250_000,
                    help="smaller files only redirect or edit data - no textures or meshes")
    ap.add_argument("--every", type=float, default=15.0, help="watch: seconds between checks")
    ap.add_argument("--hours", type=float, default=4.0, help="watch: give up after this long")
    a = ap.parse_args()
    if a.cmd == "select":
        cmd_select(a)
    elif a.cmd == "collect":
        state, new = cmd_collect(a)
        print("new", new, "| page %d / %d" % cmd_page(a, state))
    elif a.cmd == "page":
        print("page %d / %d" % cmd_page(a))
    else:
        cmd_watch(a)


if __name__ == "__main__":
    sys.exit(main())
