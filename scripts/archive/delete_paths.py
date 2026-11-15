"""Delete what the user picked from a cleanup table (temp_survey.py makes the table; README "临时文件清点（多窗口）").
For D: export dirs that are registered in games.py use delete_archived.py instead - it re-checks the ledger first.

Refuses drive roots, E:\\Downloads, system folders and ~\\.claude.  Skips a PATH in which a file was written in the last
--min-age minutes (another window may be using it).  Reparse points (junctions / symlinks) are removed as LINKS (never
followed) in the full mode and left alone in the partial modes.  Prints files / bytes removed per PATH.

usage: python delete_paths.py [--dry-run] [--min-age MIN] [--data-only [--keep-ext .jpg,.mp4] | --frames-only] PATH...
  (default)      delete each PATH completely
  --data-only    inside each PATH delete every file that is not a text file <= 2 MB (renders, meshes, .blend ...),
                 except the --keep-ext extensions; scripts / notes / logs / json stay, emptied folders go
  --frames-only  inside each PATH delete only render frame sequences (non-jpg images in a folder holding >= 30
                 images), .blend1 backups and .pyc caches; emptied folders go
  --min-age MIN  default 30
"""
import os
import stat
import sys
import time

REPARSE = 0x400
TEXT_EXT = {".py", ".md", ".txt", ".json", ".log", ".ps1", ".sh", ".bat", ".cmd", ".csv", ".html", ".htm", ".js",
            ".css", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".xml", ".jsonl", ".diff", ".patch", ".tsv"}
IMG = {".png", ".jpg", ".jpeg", ".exr", ".tga", ".bmp", ".webp", ".dds"}
FORBIDDEN = [r"e:\downloads", r"c:\windows", r"c:\program files", r"c:\program files (x86)", r"d:\program files",
             r"d:\program files (x86)", os.path.join(os.path.expanduser("~"), ".claude").lower()]


def is_reparse(st):
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE) or stat.S_ISLNK(st.st_mode)


class Job:
    def __init__(self, mode, keep_ext, dry):
        self.mode, self.keep_ext, self.dry = mode, keep_ext, dry
        self.files = self.bytes = self.dirs = self.links = self.kept_files = self.kept_bytes = 0
        self.errors = []

    def wants(self, name, size, in_seq):
        ext = os.path.splitext(name)[1].lower()
        if self.mode == "full":
            return True
        if self.mode == "frames":
            # .jpg stays even inside a sequence folder: contact sheets / comparison pictures are jpg here
            return (in_seq and ext in IMG and ext not in (".jpg", ".jpeg")) or ext in (".blend1", ".pyc")
        return not ((ext in TEXT_EXT and size <= 2_000_000) or ext in self.keep_ext)

    def unlink(self, path):
        if self.dry:
            return True
        try:
            os.unlink(path)
            return True
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)            # read-only files
                os.unlink(path)
                return True
            except OSError as e:
                self.errors.append("%s: %s" % (path, e))
        except OSError as e:
            self.errors.append("%s: %s" % (path, e))
        return False

    def rm(self, path, top=False, in_seq=False):
        """True when `path` is gone (or would be, in a dry run)"""
        st = os.lstat(path)
        if is_reparse(st):
            if self.mode != "full":
                self.kept_files += 1
                return False
            self.links += 1
            if not self.dry:
                try:
                    if stat.S_ISDIR(st.st_mode) or (getattr(st, "st_file_attributes", 0) & 0x10):
                        os.rmdir(path)               # junction / directory symlink: removes the link only
                    else:
                        os.unlink(path)
                except OSError as e:
                    self.errors.append("%s: %s" % (path, e))
                    return False
            return True
        if stat.S_ISDIR(st.st_mode):
            with os.scandir(path) as it:
                entries = list(it)
            if not entries and self.mode != "full":
                return False                         # partial modes keep folders that were empty before
            seq = sum(1 for e in entries if os.path.splitext(e.name)[1].lower() in IMG) >= 30
            gone = all([self.rm(e.path, in_seq=seq) for e in entries])     # a list: every child is visited
            if gone and not (top and self.mode != "full"):
                if not self.dry:
                    try:
                        os.rmdir(path)
                    except OSError as e:
                        self.errors.append("%s: %s" % (path, e))
                        return False
                self.dirs += 1
                return True
            return False
        if not self.wants(os.path.basename(path), st.st_size, in_seq):
            self.kept_files += 1
            self.kept_bytes += st.st_size
            return False
        if self.unlink(path):
            self.files += 1
            self.bytes += st.st_size
            return True
        return False


def newest_mtime(root):
    """newest file mtime under root (reparse points not followed)"""
    newest, stack = 0.0, [root]
    while stack:
        d = stack.pop()
        try:
            st = os.lstat(d)
        except OSError:
            continue
        if not stat.S_ISDIR(st.st_mode) or is_reparse(st):
            newest = max(newest, st.st_mtime)
            continue
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        est = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(est.st_mode) and not is_reparse(est):
                        stack.append(e.path)
                    else:
                        newest = max(newest, est.st_mtime)
        except OSError:
            continue
    return newest


def main():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return
    dry = "--dry-run" in args
    min_age, keep_ext = 30.0, set()
    if "--min-age" in args:
        k = args.index("--min-age")
        min_age = float(args[k + 1])
        args = args[:k] + args[k + 2:]
    if "--keep-ext" in args:
        k = args.index("--keep-ext")
        keep_ext = {x.strip().lower() for x in args[k + 1].split(",") if x.strip()}
        args = args[:k] + args[k + 2:]
    mode = "data" if "--data-only" in args else "frames" if "--frames-only" in args else "full"
    paths = [a for a in args if not a.startswith("--")]
    total = 0
    for p in paths:
        full = os.path.abspath(p)
        low = full.lower().rstrip("\\/")
        if len(low) <= 3 or any(low == f or low.startswith(f + "\\") for f in FORBIDDEN):
            print("REFUSED", full)
            continue
        if not os.path.lexists(full):
            print("MISSING", full)
            continue
        age = (time.time() - newest_mtime(full)) / 60.0
        if age < min_age:
            print("SKIPPED %s: a file was written %.0f min ago (< --min-age %.0f) - someone may be using it" % (
                full, age, min_age))
            continue
        job = Job(mode, keep_ext, dry)
        job.rm(full, top=True)
        total += job.bytes
        print("%s %s: %d files %.3f GB, %d dirs, %d links%s%s" % (
            "WOULD DELETE" if dry else "DELETED", full, job.files, job.bytes / 1e9, job.dirs, job.links,
            ", kept %d files %.3f GB" % (job.kept_files, job.kept_bytes / 1e9) if mode != "full" else "",
            ", %d ERRORS" % len(job.errors) if job.errors else ""))
        for e in job.errors[:20]:
            print("   ", e)
        if mode == "full" and not dry and os.path.lexists(full):
            print("   STILL THERE:", full)
    print("TOTAL %.3f GB" % (total / 1e9))


if __name__ == "__main__":
    main()
