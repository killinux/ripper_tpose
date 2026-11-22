"""Copy each downloaded mod archive into its own work folder D:\\stellarblade_exports\\mods\\<short>\\ (the download
folder is only read), unpack it into <short>\\unzipped\\, then list every .utoc's package paths (which game outfit a
replacer overrides, which mesh / material / texture packages it carries) -> <short>\\listing.json + a printed summary.

    python -I -X utf8 stage.py            # all
    python -I -X utf8 stage.py NikkePlus  # some
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\stellarblade")
from list_models import parse_utoc_paths  # noqa: E402

SRC = Path(r"E:\Downloads\eve_mod_download")
WORK = Path(r"D:\stellarblade_exports\mods")
SEVENZ = r"E:\tools\7zip\7z.exe"
MODS = {
    "NikkePlus": ["1- Nikke Plus - CNS Version AIO-347-1-03-1756272631.zip"],
    "AlbionGirls": ["Albion Girls 4061 2 2026-11-03T12-52Z QZzlX2TZX.zip"],
    "CakeUnveiledCS": ["All in One - CNS Version-533-6-0-1770965905.zip"],
    "YoRHaCeremonial": ["All in One-550-v1-1-0-1750877115.zip"],
    "BlackSling": ["BlackSling 1.0.2 A CNS 4109 1.0.2 2026-11-09T03-09Z FRmrslbVU.zip"],
    "CrimsonWingsBBB": ["Crimson Wings BBB AIO No Panty and Exposed Replace-1933-5-1-1758766245.rar"],
    "CrimsonWingsOP": ["CrimsonWingsOP 2.0 3543 2.0 2026-08-20T05-53Z pHiv6Nnor.zip"],
    "SkinSuitUndressed": ["EVE SkinSuit Undressed Mesh 3929 1.1.0 2026-10-09T06-46Z mYnVuWfC1.zip"],
    "EveNudeNatural": ["Eve Nude Natural - Skin Suit-740-1-6-0-1751728110.zip",
                       "Eve Nude Natural Textures - Big Areola - Pubs-740-1-6-0-1751728177.zip"],
    "EveOriginalProportions": ["EveOriginalProportions-30-2-1-1750283806.rar"],
    "RevealingCrimsonWings": ["RevealingCrimsonWingsNoPantiesV2-221-1-5-1750608867.zip"],
    "YoRHaN2TypeB": ["YoRHa N2 TypeB Uniform CNS v1.2.1 3577 1.2.1 2026-08-17T13-13Z cG409a51z.zip"],
    # 2026-11-22: the Stellar Blade Vindictus mods (full paths: they sit elsewhere in the download folders)
    "VindictusDemonMaiden": [r"E:\Downloads\1114\Vindictus - DemonMaiden - Outfit-1807-1-0-1754919465.zip",
                             r"E:\Downloads\Vindictus - DemonMaiden - Hair-1807-1-0-1754919553.zip"],
    "VindictusLaniakea": [r"E:\Downloads\Vindictus - Laniakea-2233-1-0-1759784265.rar"],
    "HeraldOfGoddess": [r"E:\Downloads\(CNS) EVE - Herald of Goddess-1670-1-1-1-1753797247.zip"],
    "EvilMaid": [r"E:\Downloads\Evil maid-1347-1-2-1752854499.zip", r"E:\Downloads\Evil maid horn-1347-1-0-1752387385.zip"],
    "SummerVacation": [r"E:\Downloads\Summer vacation-1487-1-1-1752848183.zip",
                       r"E:\Downloads\Summer vacation tits-1487-1-1-1752848216.zip"],
}


def unpack(archive, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as z:          # extractall drops absolute / ".." parts
            z.extractall(dest)
    else:
        r = subprocess.run([SEVENZ, "x", "-y", "-o" + str(dest), str(archive)], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[-600:])


def main(names):
    for short in names:
        d = WORK / short
        d.mkdir(parents=True, exist_ok=True)
        un = d / "unzipped"
        for a in MODS[short]:
            src, dst = SRC / a, d / Path(a).name           # a full path in MODS replaces SRC
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
            sub = un / Path(a).stem if len(MODS[short]) > 1 else un
            if not sub.exists() or not any(sub.rglob("*.utoc")):
                unpack(dst, sub)
        listing = {}
        for utoc in sorted(un.rglob("*.utoc")):
            rel = str(utoc.relative_to(un)).replace("\\", "/")
            try:
                listing[rel] = parse_utoc_paths(utoc)
            except Exception as e:  # noqa: BLE001
                listing[rel] = ["ERROR " + str(e)]
        json.dump(listing, open(d / "listing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("== %s: %d utoc" % (short, len(listing)))
        for rel, paths in listing.items():
            ua = [p for p in paths if p.endswith(".uasset")]
            dirs = sorted({p.rsplit("/", 1)[0] for p in ua})
            print("  %s  (%d packages)" % (rel, len(ua)))
            for dd in dirs[:8]:
                names_ = [p.rsplit("/", 1)[1][:-7] for p in ua if p.rsplit("/", 1)[0] == dd]
                print("     %s/: %s%s" % (dd, ", ".join(names_[:14]), " ... +%d" % (len(names_) - 14) if len(names_) > 14 else ""))
            if len(dirs) > 8:
                print("     ... %d more folders" % (len(dirs) - 8))


if __name__ == "__main__":
    main(sys.argv[1:] or list(MODS))
