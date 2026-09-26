"""Pull a Vindictus face's MetaHuman data out of the game for the Faceit ARKit add-on
(scripts/blender_addons/faceit_arkit): the DNA (expressions) and the cooked face package (the full
skin weights - UE Viewer's PSK keeps only 4 influences per vertex, the MetaHuman face has up to 12).

    python extract_face_data.py --list                      # face meshes in the container, with/without DNA
    python extract_face_data.py --face Fiona                # -> <out>/SK_Fiona_Face01.dna + .uasset.bin
    python extract_face_data.py --package Vindictus/Content/.../SK_Lethita_Face01.uasset
    [--out E:/game_export/Vindictus/_meta/face] [--game E:/tools/vindictus]

The AES key comes from VINDICTUS_AES_KEY or E:/tools/vindictus/_download/aes_key.txt and is never
printed or written anywhere else.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "firstdescendant"))
from iostore import Oodle, Toc  # noqa: E402

DEFAULT_GAME = r"E:\tools\vindictus"
DEFAULT_KEY_FILE = r"E:\tools\vindictus\_download\aes_key.txt"
DEFAULT_OODLE = r"E:\tools\cue4parse_cli\oodle-data-shared.dll"
DEFAULT_OUT = r"E:\game_export\Vindictus\_meta\face"
DNA_SIGNATURE = b"DNA\x00\x02\x00\x01"


def load_key(key_file):
    key = os.environ.get("VINDICTUS_AES_KEY", "")
    if not key and os.path.isfile(key_file):
        key = open(key_file, encoding="utf-8").read().strip()
    if not key:
        raise SystemExit("no AES key: set VINDICTUS_AES_KEY or put it in %s" % key_file)
    return bytes.fromhex(key[2:] if key.lower().startswith("0x") else key)


def open_container(args):
    utoc = os.path.join(args.game, "Vindictus", "Content", "Paks", "Vindictus-Windows.utoc")
    return Toc(utoc, load_key(args.key_file)), Oodle(args.oodle)


def face_packages(paths):
    return sorted(p for p in paths if p.endswith(".uasset") and "/Character/" in p
                  and os.path.basename(p).startswith("SK_") and "Face" in os.path.basename(p))


def dna_stream(buf):
    start = buf.find(DNA_SIGNATURE)
    if start < 0:
        return None
    return buf[start:buf.find(b"AND", start) + 3]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--face", default="", help="character name, e.g. Fiona or Lethita (matches SK_<name>_Face*)")
    ap.add_argument("--package", default="", help="container path of the face mesh package")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    ap.add_argument("--oodle", default=DEFAULT_OODLE)
    args = ap.parse_args()

    toc, oodle = open_container(args)
    paths = toc.paths()
    faces = face_packages(paths)
    if args.list:
        for p in faces:
            buf = toc.read_chunk(paths[p], oodle)
            stream = dna_stream(buf)
            print("%-6s %8.1f MB  %s" % ("DNA" if stream else "-", len(buf) / 1e6, p))
        return
    if args.package:
        chosen = [args.package]
    elif args.face:
        chosen = [p for p in faces if os.path.basename(p).lower().startswith("sk_%s_face" % args.face.lower())]
    else:
        raise SystemExit("give --face NAME, --package PATH or --list")
    if not chosen:
        raise SystemExit("no face package for %r (try --list)" % (args.face or args.package))
    os.makedirs(args.out, exist_ok=True)
    for p in chosen:
        if p not in paths:
            raise SystemExit("package not in the container: %s" % p)
        buf = toc.read_chunk(paths[p], oodle)
        stem = os.path.splitext(os.path.basename(p))[0]
        stream = dna_stream(buf)
        if stream is None:
            print("%s: no MetaHuman DNA in this package - skipped" % p)
            continue
        with open(os.path.join(args.out, stem + ".dna"), "wb") as fh:
            fh.write(stream)
        with open(os.path.join(args.out, stem + ".uasset.bin"), "wb") as fh:
            fh.write(buf)
        print("wrote %s.dna (%d bytes) and %s.uasset.bin (%d bytes) to %s" % (stem, len(stream), stem, len(buf), args.out))


if __name__ == "__main__":
    main()
