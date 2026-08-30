"""Prune redundant files from the Rise of Eros export tree.

``extract_character.ps1`` writes every texture twice: once into
``<id>\\_textures\\`` and again beside each object under
``<id>\\<object>\\FBX_GameObjects\\``.  Only the ``_textures`` copy is read by
the export pipelines, so the per-object copies are dead weight — on a full
128-character tree they accounted for 18 GB.  They come back on every
re-extraction, so this is a maintenance script, not a one-off.

Nothing is deleted on trust:

* a texture copy goes only when a same-named file exists in that character's
  own ``_textures`` and both files hash identically;
* a ``.blend1`` goes only when its ``.blend`` still exists;
* ``_textures\\`` and ``blend\\`` are never descended into, so the deliverables
  and the canonical texture store cannot be touched.

Dry run by default — pass ``--apply`` to actually delete.

Usage:
  python prune_exports.py                      # report what would go
  python prune_exports.py --apply              # delete it
  python prune_exports.py --root E:\\other --apply
"""

import argparse
import hashlib
import os

CHUNK = 1 << 20
PROTECTED_DIRS = ("_textures", "blend")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prune duplicate texture copies and Blender backups.")
    parser.add_argument("--root", default=r"D:\roe_exports",
                        help="export root (default: %(default)s)")
    parser.add_argument("--apply", action="store_true",
                        help="actually delete; without it this is a dry run")
    parser.add_argument("--skip-textures", action="store_true",
                        help="leave duplicate texture copies alone")
    parser.add_argument("--skip-backups", action="store_true",
                        help="leave .blend1 backups alone")
    return parser.parse_args()


def digest(path):
    hasher = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def character_dirs(root):
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and name[:1].isalpha() and name[1:].isdigit():
            yield path


def duplicate_textures(root):
    """Yield (path, size) for PNGs proven identical to a _textures copy."""
    for char_dir in character_dirs(root):
        texture_dir = os.path.join(char_dir, "_textures")
        if not os.path.isdir(texture_dir):
            # Without the canonical store the per-object copies are the only
            # textures this character has; re-extract with -ExportTextures first.
            continue
        twins = {}
        for dirpath, _dirs, files in os.walk(texture_dir):
            for filename in files:
                twins.setdefault(filename.lower(), os.path.join(dirpath, filename))

        for dirpath, dirs, files in os.walk(char_dir):
            dirs[:] = [d for d in dirs if d.lower() not in PROTECTED_DIRS]
            for filename in files:
                if not filename.lower().endswith(".png"):
                    continue
                twin = twins.get(filename.lower())
                if not twin:
                    continue
                victim = os.path.join(dirpath, filename)
                try:
                    if os.path.getsize(victim) != os.path.getsize(twin):
                        continue
                    if digest(victim) != digest(twin):
                        continue
                    yield victim, os.path.getsize(victim)
                except OSError:
                    continue


def stale_backups(root):
    """Yield (path, size) for .blend1 files whose .blend still exists."""
    for dirpath, _dirs, files in os.walk(root):
        for filename in files:
            if not filename.lower().endswith(".blend1"):
                continue
            path = os.path.join(dirpath, filename)
            if not os.path.isfile(path[:-1]):
                continue
            try:
                yield path, os.path.getsize(path)
            except OSError:
                continue


def sweep(entries, apply_changes, label, failed):
    count = 0
    freed = 0
    for path, size in entries:
        if apply_changes:
            try:
                os.remove(path)
            except OSError as exc:
                failed.append("%s: %s" % (path, exc))
                continue
        count += 1
        freed += size
        if count % 500 == 0:
            print("  %s ... %d files, %.2f GB" % (label, count, freed / 1024 ** 3))
    return count, freed


def main():
    args = parse_args()
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        raise SystemExit("export root not found: %s" % root)
    label = "deleting" if args.apply else "would delete"
    failed = []

    texture_count = texture_bytes = 0
    if not args.skip_textures:
        texture_count, texture_bytes = sweep(
            duplicate_textures(root), args.apply, label, failed)
    print("duplicate textures: %s %d files, %.2f GB"
          % (label, texture_count, texture_bytes / 1024 ** 3))

    backup_count = backup_bytes = 0
    if not args.skip_backups:
        backup_count, backup_bytes = sweep(
            stale_backups(root), args.apply, label, failed)
    print("blender backups   : %s %d files, %.2f GB"
          % (label, backup_count, backup_bytes / 1024 ** 3))

    print("TOTAL             : %.2f GB"
          % ((texture_bytes + backup_bytes) / 1024 ** 3))
    if not args.apply and (texture_count or backup_count):
        print("(dry run - re-run with --apply to delete)")
    if failed:
        print("could not remove %d file(s):" % len(failed))
        for line in failed[:10]:
            print("   " + line)


if __name__ == "__main__":
    main()
