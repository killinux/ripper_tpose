"""Temp-file survey for a cleanup table: every Claude window's temp dirs, D: work dirs, %TEMP%, backups in the archive.

Per path: size, files, newest file (time + path), bytes in hard-linked files (>= 1 MB with nlink > 1 - deleting those
frees nothing while the other link lives), "data" bytes (anything that is not a text file <= 2 MB) and reparse points
(junctions / symlinks: listed, never followed).  Read-only - deleting is delete_paths.py's job, after the user has
picked rows of the table (README section "临时文件清点（多窗口）").

usage:
  python temp_survey.py PATH...                         one row per PATH
  python temp_survey.py --children PATH... [--exclude NAME]...
                                                        one row per direct child of each PATH
  python temp_survey.py --find REGEX [--depth N] PATH...
                                                        directories whose NAME matches REGEX (case-insensitive, default
                                                        depth 3, no descent into a match), one row each
  python temp_survey.py --claude-temp                   every %TEMP%\\claude\\<project>\\<session> dir, labelled with
                                                        the window name (the last "agentName" in that session's
                                                        transcript ~/.claude/projects/<project>/<session>.jsonl)
  python temp_survey.py --breakdown PATH...             what a big dir holds: per top folder, per extension, and the
                                                        share of render frame sequences (>= 30 images in one folder)
  --json OUT                                            also write the rows as JSON
"""
import collections
import glob
import json
import os
import re
import stat
import sys
import time

REPARSE = 0x400
TEXT_EXT = {".py", ".md", ".txt", ".json", ".log", ".ps1", ".sh", ".bat", ".cmd", ".csv", ".html", ".htm", ".js",
            ".css", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".xml", ".jsonl", ".diff", ".patch", ".tsv"}
IMG = {".png", ".jpg", ".jpeg", ".exr", ".tga", ".bmp", ".webp", ".dds"}
AGENT_RX = re.compile(rb'"agentName":"([^"]{1,80})"')


def is_reparse(st, entry=None):
    if getattr(st, "st_file_attributes", 0) & REPARSE:
        return True
    return entry.is_symlink() if entry is not None else stat.S_ISLNK(st.st_mode)


def is_text(name, size):
    return os.path.splitext(name)[1].lower() in TEXT_EXT and size <= 2_000_000


def survey(root):
    r = dict(path=root, bytes=0, files=0, dirs=0, newest=0.0, newest_path="", linked=0, data=0, reparse=[], errors=0)
    try:
        st = os.lstat(root)
    except OSError:
        r["errors"] += 1
        return r
    if is_reparse(st):
        r["reparse"].append(root)
        return r
    if not stat.S_ISDIR(st.st_mode):
        r.update(files=1, bytes=st.st_size, newest=st.st_mtime, newest_path=root,
                 data=0 if is_text(root, st.st_size) else st.st_size)
        return r
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            r["errors"] += 1
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                r["errors"] += 1
                continue
            if is_reparse(st, e):
                r["reparse"].append(e.path)
                continue
            if stat.S_ISDIR(st.st_mode):
                r["dirs"] += 1
                stack.append(e.path)
                continue
            r["files"] += 1
            r["bytes"] += st.st_size
            if st.st_mtime > r["newest"]:
                r["newest"], r["newest_path"] = st.st_mtime, e.path
            if not is_text(e.name, st.st_size):
                r["data"] += st.st_size
            if st.st_size >= 1_000_000:
                try:
                    if os.stat(e.path).st_nlink > 1:     # DirEntry.stat() has no st_nlink on Windows
                        r["linked"] += st.st_size
                except OSError:
                    r["errors"] += 1
    return r


def find_dirs(root, rx, depth):
    out, stack = [], [(root, 0)]
    while stack:
        d, lv = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                if not e.is_dir(follow_symlinks=False) or is_reparse(e.stat(follow_symlinks=False), e):
                    continue
            except OSError:
                continue
            if rx.search(e.name):
                out.append(e.path)
            elif lv + 1 < depth:
                stack.append((e.path, lv + 1))
    return sorted(out)


def window_name(session):
    """(window name, transcript mtime) of a Claude session id; ('-', 0) when no transcript names it"""
    best = ("-", 0.0)
    pattern = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", session + ".jsonl")
    for path in glob.glob(pattern):
        try:
            size, mtime = os.path.getsize(path), os.path.getmtime(path)
            with open(path, "rb") as f:
                f.seek(max(0, size - 4_000_000))          # the name is repeated on recent lines; the tail is enough
                found = AGENT_RX.findall(f.read())
        except OSError:
            continue
        name = found[-1].decode("utf-8", "replace") if found else "-"
        if mtime >= best[1]:
            best = (name, mtime)
    return best


def claude_temp_rows():
    base = os.path.join(os.environ.get("TEMP", ""), "claude")
    rows = []
    for proj in sorted(os.scandir(base), key=lambda e: e.name) if os.path.isdir(base) else []:
        if not proj.is_dir(follow_symlinks=False):
            continue
        for sess in sorted(os.scandir(proj.path), key=lambda e: e.name):
            if not sess.is_dir(follow_symlinks=False):
                continue
            r = survey(sess.path)
            r["window"], r["transcript_mtime"] = window_name(sess.name)
            r["project"] = proj.name
            rows.append(r)
    return rows


def breakdown(root, top_n=12):
    by_top, by_ext = collections.Counter(), collections.Counter()
    frames = blend1 = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        seq = sum(1 for e in entries if os.path.splitext(e.name)[1].lower() in IMG) >= 30
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if is_reparse(st, e):
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append(e.path)
                continue
            rel = os.path.relpath(e.path, root)
            by_top[rel.split(os.sep)[0] if os.sep in rel else "(files)"] += st.st_size
            ext = os.path.splitext(e.name)[1].lower() or "(none)"
            by_ext[ext] += st.st_size
            if seq and ext in IMG:
                frames += st.st_size
            if ext == ".blend1":
                blend1 += st.st_size
    print("%s  total %.2f GB  frame sequences %.2f GB  .blend1 %.2f GB" % (
        root, sum(by_top.values()) / 1e9, frames / 1e9, blend1 / 1e9))
    print("  top folders:", ", ".join("%s %.2f" % (k, v / 1e9) for k, v in by_top.most_common(top_n)))
    print("  extensions :", ", ".join("%s %.2f" % (k, v / 1e9) for k, v in by_ext.most_common(top_n)))


def stamp(t):
    return time.strftime("%m-%d %H:%M", time.localtime(t)) if t else "-----------"


def show(r):
    label = ""
    if "window" in r:
        label = "[%s, transcript %s] " % (r["window"], stamp(r["transcript_mtime"]))
    print("%9.3f GB %8d files  newest %s  linked %7.2f GB  data %8.3f GB  reparse %d%s  %s%s" % (
        r["bytes"] / 1e9, r["files"], stamp(r["newest"]), r["linked"] / 1e9, r["data"] / 1e9, len(r["reparse"]),
        "  ERR %d" % r["errors"] if r["errors"] else "", label, r["path"]))
    if r["newest_path"]:
        print("            newest file: %s" % r["newest_path"])
    for p in r["reparse"][:5]:
        print("            reparse point (not followed): %s" % p)


def main():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return
    flags = {"--children", "--claude-temp", "--breakdown"}
    excl, find, depth, out, paths = set(), None, 3, None, []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--exclude", "--find", "--depth", "--json"):
            v = args[i + 1]
            if a == "--exclude":
                excl.add(v.lower())
            elif a == "--find":
                find = re.compile(v, re.I)
            elif a == "--depth":
                depth = int(v)
            else:
                out = v
            i += 2
            continue
        if a not in flags:
            paths.append(a)
        i += 1
    if "--breakdown" in args:
        for p in paths:
            breakdown(p)
        return
    if "--claude-temp" in args:
        rows = claude_temp_rows()
    else:
        targets = []
        for p in paths:
            if find is not None:
                targets += find_dirs(p, find, depth)
            elif "--children" in args:
                try:
                    with os.scandir(p) as it:
                        targets += sorted(e.path for e in it if e.name.lower() not in excl)
                except OSError as e:
                    print("cannot list", p, e)
            else:
                targets.append(p)
        rows = [survey(t) for t in targets]
    for r in rows:
        show(r)
    print("SUM %.3f GB over %d paths" % (sum(r["bytes"] for r in rows) / 1e9, len(rows)))
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
