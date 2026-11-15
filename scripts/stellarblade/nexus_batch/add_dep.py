"""A dependency download (another file of the mod, or another mod) -> copied into the mod's work folder, unpacked into
<work>\\<mod>\\unzipped\\<dep>\\, and every .utoc in it listed (package folders).  The download folder is only read.

    python -I -X utf8 add_dep.py <mod short> <download file> <dep folder name>
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\stellarblade")
from list_models import parse_utoc_paths  # noqa: E402

WORK = Path(r"D:\stellarblade_exports\mods")
SEVENZ = r"E:\tools\7zip\7z.exe"

mod, src, dep = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
d = WORK / mod
copy = d / src.name
if not copy.exists() or copy.stat().st_size != src.stat().st_size:
    shutil.copy2(src, copy)
dest = d / "unzipped" / dep
if not dest.exists() or not any(dest.rglob("*.utoc")):
    dest.mkdir(parents=True, exist_ok=True)
    if copy.suffix.lower() == ".zip":
        with zipfile.ZipFile(copy) as z:
            z.extractall(dest)
    else:
        r = subprocess.run([SEVENZ, "x", "-y", "-o" + str(dest), str(copy)], capture_output=True)
        if r.returncode != 0:
            raise SystemExit(r.stderr.decode("utf-8", "replace")[-600:])
for u in sorted(dest.rglob("*.utoc")):
    paths = [p for p in parse_utoc_paths(u) if p.endswith(".uasset")]
    print("== %s (%d packages)" % (u.relative_to(d / "unzipped"), len(paths)))
    for p in paths[:40]:
        print("   ", p)
for j in sorted(dest.rglob("*.json")):
    print("json:", j.relative_to(d / "unzipped"))
for o in sorted(x for x in dest.rglob("*") if x.is_file() and x.suffix.lower() not in (".utoc", ".ucas", ".pak", ".json")):
    print("other:", o.relative_to(d / "unzipped"))
