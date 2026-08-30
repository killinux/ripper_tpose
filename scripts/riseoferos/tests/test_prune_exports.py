"""Synthetic regression for prune_exports.py.

Builds a throwaway export tree covering every case the pruner must judge and
asserts that exactly the redundant files disappear.  Pure Python, no Blender
and no game assets:

  a01/_textures/dup.png            canonical copy                  -> keep
  a01/obj/FBX_GameObjects/dup.png  byte-identical duplicate        -> DELETE
  a01/obj/FBX_GameObjects/same_name_different_bytes.png            -> keep
  a01/obj/FBX_GameObjects/only_here.png   no _textures counterpart -> keep
  a01/blend/a01_preview.png        deliverable, protected dir      -> keep
  a01/blend/a01.blend + .blend1    backup with its blend present   -> DELETE
  a01/blend/orphan.blend1          backup with no blend            -> keep
  b02/obj/FBX_GameObjects/dup.png  character has no _textures      -> keep
  notes.txt                        not a character dir             -> keep

Usage:
  python test_prune_exports.py
"""

import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = "ROE_PRUNE_EXPORTS_TEST"


def load_pruner():
    path = os.path.join(os.path.dirname(HERE), "prune_exports.py")
    spec = importlib.util.spec_from_file_location("prune_exports", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def build_tree(root):
    canonical = b"PNG-canonical-payload" * 64
    other = b"PNG-different-payload" * 64
    paths = {}
    obj = os.path.join(root, "a01", "obj", "FBX_GameObjects")

    paths["twin"] = write(os.path.join(root, "a01", "_textures", "dup.png"), canonical)
    paths["dup"] = write(os.path.join(obj, "dup.png"), canonical)
    # Same name as a _textures entry but different bytes: never assume.
    write(os.path.join(root, "a01", "_textures", "collide.png"), canonical)
    paths["collide"] = write(os.path.join(obj, "collide.png"), other)
    paths["only_here"] = write(os.path.join(obj, "only_here.png"), other)
    # A duplicate sitting inside a protected directory must survive.
    paths["in_blend"] = write(os.path.join(root, "a01", "blend", "dup.png"), canonical)
    paths["preview"] = write(
        os.path.join(root, "a01", "blend", "a01_preview.png"), other)
    paths["blend"] = write(os.path.join(root, "a01", "blend", "a01.blend"), b"blend")
    paths["backup"] = write(
        os.path.join(root, "a01", "blend", "a01.blend1"), b"backup")
    paths["orphan"] = write(
        os.path.join(root, "a01", "blend", "orphan.blend1"), b"orphan")
    # b02 has no _textures at all, so its copies are the only ones it has.
    paths["no_store"] = write(
        os.path.join(root, "b02", "obj", "FBX_GameObjects", "dup.png"), canonical)
    paths["stray"] = write(os.path.join(root, "notes.txt"), b"not a character")
    return paths


def main():
    module = load_pruner()
    root = tempfile.mkdtemp(prefix="roe_prune_test_")
    try:
        paths = build_tree(root)

        planned = {p for p, _ in module.duplicate_textures(root)}
        backups = {p for p, _ in module.stale_backups(root)}
        expected_textures = {paths["dup"]}
        expected_backups = {paths["backup"]}
        assert planned == expected_textures, (
            "texture plan mismatch\n  got      %s\n  expected %s"
            % (sorted(planned), sorted(expected_textures)))
        assert backups == expected_backups, (
            "backup plan mismatch\n  got      %s\n  expected %s"
            % (sorted(backups), sorted(expected_backups)))

        # Dry run must not touch the disk.
        failed = []
        module.sweep(module.duplicate_textures(root), False, "dry", failed)
        module.sweep(module.stale_backups(root), False, "dry", failed)
        assert not failed, failed
        assert os.path.isfile(paths["dup"]), "dry run deleted a file"

        failed = []
        count, freed = module.sweep(
            module.duplicate_textures(root), True, "apply", failed)
        assert (count, bool(failed)) == (1, False), (count, failed)
        assert freed == len(b"PNG-canonical-payload" * 64), freed
        count, _freed = module.sweep(
            module.stale_backups(root), True, "apply", failed)
        assert (count, bool(failed)) == (1, False), (count, failed)

        assert not os.path.exists(paths["dup"]), "duplicate survived"
        assert not os.path.exists(paths["backup"]), "backup survived"
        for key in ("twin", "collide", "only_here", "in_blend", "preview",
                    "blend", "orphan", "no_store", "stray"):
            assert os.path.exists(paths[key]), "%s was deleted but must be kept" % key

        # A second pass on the pruned tree must find nothing left to do.
        assert not list(module.duplicate_textures(root)), "not idempotent"
        assert not list(module.stale_backups(root)), "not idempotent"
    except AssertionError as exc:
        print("%s=FAIL" % MARKER)
        print(exc)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("%s=PASS" % MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
