"""List what each downloaded Stellar Blade mod archive holds (read-only: never extracts, never writes next to the
archives).  For every archive: the .pak / .utoc / .ucas triples (grouped by folder = variant), .dekcns.json files,
other files.  Writes inventory.json next to this script.

    python -I -X utf8 inventory.py <download dir>
"""
import json
import os
import subprocess
import sys
import zipfile

SEVENZ = r"E:\tools\7zip\7z.exe"
HERE = os.path.dirname(os.path.abspath(__file__))


def members(path):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            return [(i.filename.replace("\\", "/"), i.file_size) for i in z.infolist() if not i.is_dir()]
    exe = SEVENZ if os.path.exists(SEVENZ) else "7z"
    r = subprocess.run([exe, "l", "-slt", "-ba", path], capture_output=True)
    out, cur = [], {}
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            if cur.get("Path") and cur.get("Attributes", "").find("D") < 0:
                out.append((cur["Path"].replace("\\", "/"), int(cur.get("Size", "0") or 0)))
            cur = {}
            continue
        k, _, v = line.partition(" = ")
        cur[k.strip()] = v
    if cur.get("Path") and cur.get("Attributes", "").find("D") < 0:
        out.append((cur["Path"].replace("\\", "/"), int(cur.get("Size", "0") or 0)))
    if r.returncode != 0 and not out:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-500:])
    return out


def main(root):
    res = {}
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        try:
            ms = members(p)
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": str(e)}
            print("!!", name, e)
            continue
        paks = [m for m in ms if m[0].lower().endswith((".pak", ".utoc", ".ucas"))]
        groups = {}
        for f, s in paks:
            folder, _, base = f.rpartition("/")
            stem = base.rsplit(".", 1)[0]
            groups.setdefault(folder, {}).setdefault(stem, {})[base.rsplit(".", 1)[1].lower()] = s
        cns = [f for f, _ in ms if f.lower().endswith(".json")]
        other = [f for f, _ in ms if not f.lower().endswith((".pak", ".utoc", ".ucas", ".json"))]
        res[name] = {"size": os.path.getsize(p), "files": len(ms), "triples": groups, "json": cns, "other": other[:40],
                     "other_count": len(other)}
        ntrip = sum(len(v) for v in groups.values())
        print("== %s  (%.1f MB, %d files, %d pak stems in %d folders, %d json, %d other)" % (
            name, os.path.getsize(p) / 1e6, len(ms), ntrip, len(groups), len(cns), len(other)))
        for folder, stems in sorted(groups.items()):
            for stem, exts in sorted(stems.items()):
                print("   %-70s %-32s %s" % ((folder or ".")[-70:], stem[:32],
                                           " ".join("%s:%.1fM" % (k, v / 1e6) for k, v in sorted(exts.items()))))
        for j in cns:
            print("   json:", j)
        for o in other[:12]:
            print("   other:", o)
    json.dump(res, open(r"D:\stellarblade_exports\mods\inventory.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
