"""List Stellar Blade model packages and which ones are not exported yet.

Reads the IoStore directory index straight out of every ``*.utoc`` under the
game's Paks directory (read-only; Stellar Blade's index is not encrypted, no
AES key involved) and diffs the package list against the files already
present under the export root (FModel PSK/UEFormat exports, UE Viewer PSK
exports, and any FBX/GLB conversions).

The .utoc directory index stores paths only, not asset classes, so "model"
selection is heuristic: everything under the character art tree minus
texture/material/animation/physics naming conventions.  Use --path-filter or
--all-files to widen the view.

Examples:
  python list_models.py                       # character models not yet exported
  python list_models.py --include-exported    # full model table with status
  python list_models.py --path-filter SB/Content/Art/ --csv models.csv
  python list_models.py --all-files --path-filter 00_HR/  # raw path listing
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import io
import os
import struct
import sys
from collections import defaultdict
from pathlib import Path

TOC_MAGIC = b"-==--==--==--==-"
NONE_ENTRY = 0xFFFFFFFF

DEFAULT_PAKS = r"D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks"
DEFAULT_EXPORT_ROOT = r"D:\stellarblade_exports"
DEFAULT_PATH_FILTER = "SB/Content/Art/Character/"

# Extensions that count as "this package was exported as a model already".
EXPORTED_MODEL_EXTENSIONS = {
    ".psk", ".pskx", ".uemodel", ".fbx", ".glb", ".gltf", ".blend",
}

# Name prefixes that are clearly not skeletal/static meshes even inside the
# character tree (textures, materials, physics, animation, blueprints).
NON_MODEL_PREFIXES = (
    "tex_", "t_", "m_", "mi_", "mt_", "mf_", "mm_", "ma_", "pa_", "pc_rig",
    "ab_", "abp_", "bp_", "am_", "as_", "aim_", "bs_", "cu_", "fx_",
    "ns_", "p_", "sk_curve", "st_curve", "phys", "fa_", "result_",
)
NON_MODEL_DIR_PARTS = (
    "/tex/", "/texture/", "/textures/", "/material/", "/materials/", "/ma/",
    "/anim/", "/anims/", "/animation/", "/animations/", "/montage/",
    "/physics/", "/fx/", "/curve/", "/curves/", "/blueprint/", "/blueprints/",
    "/facial/", "/camerabone/", "/animsequence/", "/procedural_animation/",
)
NON_MODEL_SUFFIXES = (
    "_skeleton", "_phy", "_anim", "_montage",
    "_animbp", "_ctrlrig", "_fx", "_seq", "_rig", "_builtdata",
)
NON_MODEL_STEM_PARTS = ("physicsasset", "physics", "collision", "snapshot", "camera")


def read_fstring(reader: io.BufferedReader) -> str:
    (length,) = struct.unpack("<i", reader.read(4))
    if length == 0:
        return ""
    if length < 0:
        raw = reader.read(-length * 2)
        return raw.decode("utf-16-le").rstrip("\x00")
    raw = reader.read(length)
    return raw.decode("utf-8", errors="replace").rstrip("\x00")


def parse_utoc_paths(utoc_path: Path) -> list[str]:
    """Return every file path recorded in one .utoc directory index."""
    with open(utoc_path, "rb") as handle:
        header = handle.read(144)
        if len(header) < 144 or header[:16] != TOC_MAGIC:
            raise ValueError(f"Not an IoStore TOC (bad magic): {utoc_path}")
        version = header[16]
        (
            toc_header_size,
            toc_entry_count,
            compressed_block_count,
            _compressed_block_entry_size,
            compression_name_count,
            compression_name_length,
            _compression_block_size,
            directory_index_size,
            _partition_count,
        ) = struct.unpack_from("<9I", header, 20)
        container_flags = header[80]
        perfect_hash_seed_count, = struct.unpack_from("<I", header, 84)
        chunks_without_perfect_hash, = struct.unpack_from("<I", header, 96)

        if toc_header_size != 144:
            raise ValueError(
                f"Unexpected TOC header size {toc_header_size} in {utoc_path}"
            )
        if directory_index_size == 0:
            return []
        if container_flags & 0x2:  # EIoContainerFlags::Encrypted
            raise ValueError(
                f"Directory index is AES-encrypted: {utoc_path} "
                "(Stellar Blade retail containers are not; wrong file?)"
            )

        offset = toc_header_size
        offset += toc_entry_count * 12          # FIoChunkId[]
        offset += toc_entry_count * 10          # FIoOffsetAndLength[]
        if version >= 4:                        # PerfectHash (UE5)
            offset += perfect_hash_seed_count * 4
        if version >= 5:                        # PerfectHashWithOverflow
            offset += chunks_without_perfect_hash * 4
        offset += compressed_block_count * 12   # FIoStoreTocCompressedBlockEntry[]
        offset += compression_name_count * compression_name_length
        if container_flags & 0x4:               # EIoContainerFlags::Signed
            handle.seek(offset)
            (hash_size,) = struct.unpack("<i", handle.read(4))
            offset += 4 + hash_size * 2 + compressed_block_count * 20

        handle.seek(offset)
        index = io.BytesIO(handle.read(directory_index_size))

    mount_point = read_fstring(index)
    (dir_count,) = struct.unpack("<I", index.read(4))
    dir_entries = [
        struct.unpack("<4I", index.read(16)) for _ in range(dir_count)
    ]  # (Name, FirstChildEntry, NextSiblingEntry, FirstFileEntry)
    (file_count,) = struct.unpack("<I", index.read(4))
    file_entries = [
        struct.unpack("<3I", index.read(12)) for _ in range(file_count)
    ]  # (Name, NextFileEntry, UserData)
    (string_count,) = struct.unpack("<I", index.read(4))
    strings = [read_fstring(index) for _ in range(string_count)]

    mount = mount_point.replace("\\", "/")
    if mount.startswith("../../../"):
        mount = mount[len("../../../"):]

    paths: list[str] = []
    if not dir_entries:
        return paths
    # Depth-first walk from the root entry (index 0, unnamed).
    stack: list[tuple[int, str]] = [(0, mount.rstrip("/"))]
    while stack:
        entry_index, prefix = stack.pop()
        name_index, first_child, next_sibling, first_file = dir_entries[entry_index]
        if entry_index != 0 and name_index != NONE_ENTRY:
            prefix = prefix + "/" + strings[name_index] if prefix else strings[name_index]
        file_index = first_file
        while file_index != NONE_ENTRY:
            file_name_index, next_file, _user_data = file_entries[file_index]
            paths.append(prefix + "/" + strings[file_name_index])
            file_index = next_file
        child = first_child
        while child != NONE_ENTRY:
            stack.append((child, prefix))
            child = dir_entries[child][2]  # NextSiblingEntry
    return paths


def looks_like_model_package(path: str) -> bool:
    lower = path.lower()
    if not lower.endswith(".uasset"):
        return False
    for part in NON_MODEL_DIR_PARTS:
        if part in lower:
            return False
    stem = Path(lower).stem
    if stem.startswith(NON_MODEL_PREFIXES):
        return False
    if stem.endswith(NON_MODEL_SUFFIXES):
        return False
    for part in NON_MODEL_STEM_PARTS:
        if part in stem:
            return False
    return True


def collect_exported_stems(export_root: Path) -> dict[str, list[str]]:
    """Map lowercase file stems of exported model files to their locations."""
    exported: dict[str, list[str]] = defaultdict(list)
    if not export_root.is_dir():
        return exported
    for root, dirs, files in os.walk(export_root):
        # _tools holds the UEFormat source checkout, _probe_stash holds mods.
        dirs[:] = [d for d in dirs if not d.startswith(("_tools", "_probe_stash"))]
        for name in files:
            suffix = Path(name).suffix.lower()
            if suffix in EXPORTED_MODEL_EXTENSIONS:
                exported[Path(name).stem.lower()].append(str(Path(root) / name))
    return exported


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--paks", default=DEFAULT_PAKS, help="game Paks directory")
    parser.add_argument(
        "--export-root", default=DEFAULT_EXPORT_ROOT,
        help="export root to diff against (default: %(default)s)",
    )
    parser.add_argument(
        "--path-filter", default=DEFAULT_PATH_FILTER,
        help="only paths containing this substring (default: %(default)s)",
    )
    parser.add_argument(
        "--glob", default="",
        help="additionally require the file name to match this glob, e.g. 'CH_*'",
    )
    parser.add_argument(
        "--all-files", action="store_true",
        help="list raw paths matching the filter without the model heuristic",
    )
    parser.add_argument(
        "--include-exported", action="store_true",
        help="show already-exported packages too, with their local files",
    )
    parser.add_argument("--csv", default="", help="also write the table to this CSV")
    args = parser.parse_args()

    paks_dir = Path(args.paks)
    if not paks_dir.is_dir():
        print(f"Paks directory not found: {paks_dir}", file=sys.stderr)
        return 1
    utoc_files = sorted(
        p for p in paks_dir.glob("*.utoc")
        if "~mods" not in p.parts
    )
    if not utoc_files:
        print(f"No .utoc files under: {paks_dir}", file=sys.stderr)
        return 1

    all_paths: list[str] = []
    for utoc in utoc_files:
        try:
            paths = parse_utoc_paths(utoc)
        except ValueError as error:
            print(f"WARNING: {error}", file=sys.stderr)
            continue
        print(f"{utoc.name}: {len(paths)} files", file=sys.stderr)
        all_paths.extend(paths)

    needle = args.path_filter.replace("\\", "/").lower()
    filtered = [p for p in all_paths if needle in p.lower()]
    if args.glob:
        filtered = [
            p for p in filtered
            if fnmatch.fnmatch(Path(p).name.lower(), args.glob.lower())
        ]

    if args.all_files:
        for path in sorted(filtered):
            print(path)
        print(
            f"\n{len(filtered)} of {len(all_paths)} indexed files match "
            f"'{args.path_filter}'",
            file=sys.stderr,
        )
        return 0

    models = sorted(p for p in filtered if looks_like_model_package(p))
    exported = collect_exported_stems(Path(args.export_root))

    rows = []
    for package in models:
        stem = Path(package).stem.lower()
        hits = exported.get(stem, [])
        rows.append((package, "EXPORTED" if hits else "MISSING", hits))

    missing = [row for row in rows if row[1] == "MISSING"]
    done = [row for row in rows if row[1] == "EXPORTED"]

    shown = rows if args.include_exported else missing
    for package, status, hits in shown:
        if args.include_exported:
            print(f"{status:9} {package}")
            for hit in hits:
                print(f"          -> {hit}")
        else:
            print(package)

    print(
        f"\nModel-package candidates under '{args.path_filter}': {len(rows)} "
        f"(exported: {len(done)}, missing: {len(missing)})",
        file=sys.stderr,
    )
    print(
        "Heuristic listing from .utoc paths only; textures/materials/anims are "
        "filtered by naming convention, not by asset class.",
        file=sys.stderr,
    )

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["package", "status", "exported_files"])
            for package, status, hits in rows:
                writer.writerow([package, status, "; ".join(hits)])
        print(f"CSV written: {args.csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
