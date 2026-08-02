#!/usr/bin/env python3
"""Inspect and extract X-Legend mobilepack NFS assets.

The Steam build of Throne of Desire uses a 0x20190503 packageindex, a
FileListPC.txt manifest, and hashed NFS package files.  This script only reads
the installed game and writes explicitly requested output files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_INDEX_VERSION = 0x20190503


@dataclass(frozen=True)
class IndexEntry:
    asset_hash: int
    offset: int
    uncompressed_size: int
    checksum: int
    timestamp: int


@dataclass(frozen=True)
class FileEntry:
    asset_hash: int
    package_name: str
    timestamp: int
    compressed_size: int
    uncompressed_size: int
    compressed_checksum: int
    uncompressed_checksum: int
    flags: int


def parse_hex(value: str) -> int:
    return int(value.strip(), 16)


def resolve_mobilepack(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "packageindex").is_file() and (path / "FileListPC.txt").is_file():
        return path
    candidate = path / "mobilepack"
    if (candidate / "packageindex").is_file() and (candidate / "FileListPC.txt").is_file():
        return candidate
    raise FileNotFoundError(f"Not a Throne of Desire mobilepack directory: {path}")


def read_index(path: Path) -> tuple[int, dict[int, IndexEntry]]:
    data = path.read_bytes()
    if len(data) < 4:
        raise ValueError(f"Index is too short: {path}")
    version = struct.unpack_from("<I", data, 0)[0]
    if version != SUPPORTED_INDEX_VERSION:
        raise ValueError(
            f"Unsupported packageindex version 0x{version:08x}; "
            f"expected 0x{SUPPORTED_INDEX_VERSION:08x}"
        )
    payload_size = len(data) - 4
    if payload_size % 24:
        raise ValueError(f"Misaligned packageindex: {payload_size} payload bytes")

    entries: dict[int, IndexEntry] = {}
    for position in range(4, len(data), 24):
        asset_hash, encoded_offset, encoded_size, checksum, timestamp = struct.unpack_from(
            "<QIIII", data, position
        )
        xor_key = asset_hash & 0xFFFFFFFF
        entry = IndexEntry(
            asset_hash=asset_hash,
            offset=encoded_offset ^ xor_key,
            uncompressed_size=encoded_size ^ xor_key,
            checksum=checksum,
            timestamp=timestamp,
        )
        entries[asset_hash] = entry
    return version, entries


def read_file_list(path: Path) -> tuple[int, list[FileEntry], int]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if not lines:
        raise ValueError(f"Empty file list: {path}")
    declared_count = int(lines[0].strip())
    hashed: list[FileEntry] = []
    named_count = 0
    for line_number, line in enumerate(lines[1:], 2):
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 8:
            continue
        # Named loose files use columns 0/1 as filename/path.  NFS entries use
        # a 64-bit asset hash and an 8-digit package filename instead.
        if "/" in parts[1] or "\\" in parts[1]:
            named_count += 1
            continue
        try:
            hashed.append(
                FileEntry(
                    asset_hash=parse_hex(parts[0]),
                    package_name=parts[1].lower(),
                    timestamp=parse_hex(parts[2]),
                    compressed_size=int(parts[3]),
                    uncompressed_size=int(parts[4]),
                    compressed_checksum=parse_hex(parts[5]),
                    uncompressed_checksum=parse_hex(parts[6]),
                    flags=parse_hex(parts[7]),
                )
            )
        except ValueError as exc:
            raise ValueError(f"Invalid NFS row {line_number}: {line}") from exc
    return declared_count, hashed, named_count


def package_path(mobilepack: Path, package_name: str) -> Path:
    return mobilepack / "nfs" / package_name[0] / package_name


def read_chunk(
    mobilepack: Path,
    file_entry: FileEntry,
    index_entry: IndexEntry,
    *,
    preview_bytes: int | None = None,
) -> tuple[bytes, str, int]:
    source = package_path(mobilepack, file_entry.package_name)
    read_size = file_entry.compressed_size + 16
    if preview_bytes is not None:
        read_size = min(read_size, 65552)
    with source.open("rb") as stream:
        stream.seek(index_entry.offset)
        chunk = stream.read(read_size)

    for header_size in (16, 12):
        payload = chunk[header_size:]
        if not payload:
            continue
        try:
            if preview_bytes is None:
                data = zlib.decompress(payload)
            else:
                data = zlib.decompressobj().decompress(payload, preview_bytes)
            return data, "zlib", header_size
        except zlib.error:
            pass

    marker = chunk[12:24]
    if marker.startswith(b"LZMA") or chunk[16:28].startswith(b"LZMA"):
        raise NotImplementedError(
            f"Asset {file_entry.asset_hash:016x} uses X-Legend's custom LZMA stream"
        )
    raise ValueError(f"Unknown compression for asset {file_entry.asset_hash:016x}")


def detect_extension(data: bytes) -> str:
    if data.startswith(b"Gamebryo File Format"):
        return ".nif"
    if data.startswith((b";Gamebryo KFM File", b"Gamebryo KFM File")):
        return ".kfm"
    if data.startswith(b"DDS "):
        return ".dds"
    if data.startswith(b"OggS"):
        return ".ogg"
    if data.startswith(b"<?xml"):
        return ".xml"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"BM"):
        return ".bmp"
    return ".bin"


def xlegend_hash32(text: str, seed: int = 0) -> int:
    for character in text:
        seed = ((seed * 0x1000193) ^ ord(character)) & 0xFFFFFFFF
    return seed


def load_catalog(mobilepack: Path):
    version, index = read_index(mobilepack / "packageindex")
    declared, files, named_count = read_file_list(mobilepack / "FileListPC.txt")
    mapped = [entry for entry in files if entry.asset_hash in index]
    return version, index, declared, files, named_count, mapped


def classify_entries(
    mobilepack: Path,
    index: dict[int, IndexEntry],
    entries: Iterable[FileEntry],
) -> tuple[Counter, list[dict]]:
    counts: Counter = Counter()
    details: list[dict] = []
    for entry in entries:
        index_entry = index[entry.asset_hash]
        try:
            data, compression, header_size = read_chunk(
                mobilepack, entry, index_entry, preview_bytes=256
            )
            extension = detect_extension(data)
        except NotImplementedError:
            compression, header_size, extension = "lzma", None, ".bin"
        except (OSError, ValueError):
            compression, header_size, extension = "unknown", None, ".bin"
        counts[compression] += 1
        counts[extension] += 1
        details.append(
            {
                "hash": f"{entry.asset_hash:016x}",
                "package": entry.package_name,
                "offset": index_entry.offset,
                "compressed_size": entry.compressed_size,
                "uncompressed_size": entry.uncompressed_size,
                "compression": compression,
                "header_size": header_size,
                "extension": extension,
            }
        )
    return counts, details


def write_asset(
    mobilepack: Path,
    index: dict[int, IndexEntry],
    entry: FileEntry,
    output: Path,
) -> dict:
    index_entry = index[entry.asset_hash]
    data, compression, header_size = read_chunk(mobilepack, entry, index_entry)
    if len(data) != entry.uncompressed_size:
        raise ValueError(
            f"Size mismatch for {entry.asset_hash:016x}: "
            f"got {len(data)}, expected {entry.uncompressed_size}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return {
        "output": str(output.resolve()),
        "hash": f"{entry.asset_hash:016x}",
        "package": entry.package_name,
        "offset": index_entry.offset,
        "compressed_size": entry.compressed_size,
        "uncompressed_size": entry.uncompressed_size,
        "compression": compression,
        "header_size": header_size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def command_scan(args: argparse.Namespace) -> int:
    mobilepack = resolve_mobilepack(args.game)
    version, index, declared, files, named_count, mapped = load_catalog(mobilepack)
    if args.package:
        mapped = [entry for entry in mapped if entry.package_name == args.package.lower()]
    counts, details = classify_entries(mobilepack, index, mapped)
    summary = {
        "mobilepack": str(mobilepack),
        "index_version": f"0x{version:08x}",
        "file_list_declared": declared,
        "named_loose_files": named_count,
        "hashed_rows": len(files),
        "index_records": len(index),
        "mapped_rows": len(mapped),
        "counts": dict(sorted(counts.items())),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        report = {"summary": summary, "assets": details}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


def command_extract_hash(args: argparse.Namespace) -> int:
    mobilepack = resolve_mobilepack(args.game)
    _, index, _, files, _, _ = load_catalog(mobilepack)
    wanted = parse_hex(args.hash)
    entry = next((item for item in files if item.asset_hash == wanted), None)
    if entry is None or wanted not in index:
        raise KeyError(f"Asset hash is not mapped: {wanted:016x}")
    preview, _, _ = read_chunk(mobilepack, entry, index[wanted], preview_bytes=256)
    output = args.output
    if output.suffix == "":
        output = output.with_suffix(detect_extension(preview))
    result = write_asset(mobilepack, index, entry, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_extract_model(args: argparse.Namespace) -> int:
    mobilepack = resolve_mobilepack(args.game)
    _, index, _, _, _, mapped = load_catalog(mobilepack)
    model_id = args.model.lower()
    package_name = f"{xlegend_hash32(model_id[:4]):08x}"
    candidates = sorted(
        (entry for entry in mapped if entry.package_name == package_name),
        key=lambda entry: index[entry.asset_hash].offset,
    )
    if not candidates:
        raise KeyError(f"No NFS package found for model {model_id}: {package_name}")

    inspected: list[tuple[FileEntry, bytes, str]] = []
    for entry in candidates:
        try:
            preview, _, _ = read_chunk(
                mobilepack, entry, index[entry.asset_hash], preview_bytes=512
            )
        except (NotImplementedError, OSError, ValueError):
            continue
        inspected.append((entry, preview, detect_extension(preview)))

    model_reference = f"model\\{model_id}.nif".encode("ascii")
    kfm = next(
        (
            item
            for item in inspected
            if item[2] == ".kfm" and model_reference in item[1].lower()
        ),
        None,
    )
    if kfm is None:
        raise KeyError(f"Could not identify {model_id}.kfm in package {package_name}")
    kfm_offset = index[kfm[0].asset_hash].offset
    base_nif = next(
        (
            item
            for item in inspected
            if item[2] == ".nif" and index[item[0].asset_hash].offset > kfm_offset
        ),
        None,
    )
    if base_nif is None:
        raise KeyError(f"Could not identify {model_id}.nif after its KFM entry")

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        write_asset(mobilepack, index, kfm[0], output_dir / f"{model_id}.kfm"),
        write_asset(mobilepack, index, base_nif[0], output_dir / f"{model_id}.nif"),
    ]
    manifest = {
        "model": model_id,
        "package": package_name,
        "selection_rule": "matching KFM followed by the next NIF chunk",
        "files": results,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Classify mapped NFS assets")
    scan.add_argument("--game", type=Path, required=True)
    scan.add_argument("--package", help="Only scan one 8-digit NFS package")
    scan.add_argument("--output", type=Path, help="Optional JSON inventory")
    scan.set_defaults(func=command_scan)

    extract_hash = subparsers.add_parser("extract-hash", help="Extract one asset hash")
    extract_hash.add_argument("--game", type=Path, required=True)
    extract_hash.add_argument("--hash", required=True)
    extract_hash.add_argument("--output", type=Path, required=True)
    extract_hash.set_defaults(func=command_extract_hash)

    extract_model = subparsers.add_parser(
        "extract-model", help="Extract a numbered Gamebryo model group such as m001"
    )
    extract_model.add_argument("--game", type=Path, required=True)
    extract_model.add_argument("--model", required=True)
    extract_model.add_argument("--output", type=Path, required=True)
    extract_model.set_defaults(func=command_extract_model)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, NotImplementedError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
