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
import mmap
import re
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


def resolve_package_offsets(
    mobilepack: Path,
    index: dict[int, IndexEntry],
    entries: Iterable[FileEntry],
) -> tuple[dict[int, IndexEntry], set[int]]:
    """Resolve package-local offsets, including records omitted by packageindex.

    Some shipped packages still contain valid chunks listed by FileListPC.txt
    even though the current packageindex omits their hashes.  NFS chunks start
    on 16-byte boundaries and carry the 64-bit asset hash in their header, so
    those offsets can be recovered without guessing asset order or content.
    """

    entries = list(entries)
    resolved = {
        entry.asset_hash: index[entry.asset_hash]
        for entry in entries
        if entry.asset_hash in index
    }
    missing = {entry.asset_hash: entry for entry in entries if entry.asset_hash not in index}
    recovered: set[int] = set()
    if not missing:
        return resolved, recovered

    package_names = {entry.package_name for entry in entries}
    if len(package_names) != 1:
        raise ValueError("package offset recovery requires exactly one NFS package")
    source = package_path(mobilepack, next(iter(package_names)))
    with source.open("rb") as stream, mmap.mmap(
        stream.fileno(), length=0, access=mmap.ACCESS_READ
    ) as package:
        for offset in range(0, len(package) - 15, 16):
            asset_hash, = struct.unpack_from("<Q", package, offset)
            entry = missing.get(asset_hash)
            if entry is None:
                continue
            resolved[asset_hash] = IndexEntry(
                asset_hash=asset_hash,
                offset=offset,
                uncompressed_size=entry.uncompressed_size,
                checksum=entry.uncompressed_checksum,
                timestamp=entry.timestamp,
            )
            recovered.add(asset_hash)
            if len(recovered) == len(missing):
                break
    return resolved, recovered


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
    *,
    allow_stale_file_list_size: bool = False,
) -> dict:
    index_entry = index[entry.asset_hash]
    data, compression, header_size = read_chunk(mobilepack, entry, index_entry)
    size_matches = len(data) == entry.uncompressed_size
    if not size_matches and not allow_stale_file_list_size:
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
        "uncompressed_size": len(data),
        "declared_uncompressed_size": entry.uncompressed_size,
        "actual_uncompressed_size": len(data),
        "size_matches_file_list": size_matches,
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
    _, index, _, files, _, _ = load_catalog(mobilepack)
    model_id = args.model.lower()
    package_name = f"{xlegend_hash32(model_id[:4]):08x}"
    package_entries = [entry for entry in files if entry.package_name == package_name]
    package_index, recovered = resolve_package_offsets(
        mobilepack, index, package_entries
    )
    candidates = sorted(
        (entry for entry in package_entries if entry.asset_hash in package_index),
        key=lambda entry: package_index[entry.asset_hash].offset,
    )
    if not candidates:
        raise KeyError(f"No NFS package found for model {model_id}: {package_name}")

    inspected: list[tuple[FileEntry, bytes, str]] = []
    for entry in candidates:
        try:
            preview, _, _ = read_chunk(
                mobilepack, entry, package_index[entry.asset_hash], preview_bytes=512
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
    kfm_offset = package_index[kfm[0].asset_hash].offset
    base_nif = next(
        (
            item
            for item in inspected
            if item[2] == ".nif"
            and package_index[item[0].asset_hash].offset > kfm_offset
        ),
        None,
    )
    if base_nif is None:
        raise KeyError(f"Could not identify {model_id}.nif after its KFM entry")

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        write_asset(
            mobilepack,
            package_index,
            kfm[0],
            output_dir / f"{model_id}.kfm",
            allow_stale_file_list_size=kfm[0].asset_hash in recovered,
        ),
        write_asset(
            mobilepack,
            package_index,
            base_nif[0],
            output_dir / f"{model_id}.nif",
            allow_stale_file_list_size=base_nif[0].asset_hash in recovered,
        ),
    ]
    manifest = {
        "model": model_id,
        "package": package_name,
        "selection_rule": "matching KFM followed by the next physical NIF chunk",
        "recovered_packageindex_hashes": [
            f"{value:016x}"
            for value in sorted(
                recovered & {kfm[0].asset_hash, base_nif[0].asset_hash}
            )
        ],
        "files": results,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


KFM_MODEL_REFERENCE = re.compile(
    rb"(?:\.\\)?model\\([A-Za-z0-9_.-]+)\.nif", re.IGNORECASE
)


def model_sort_key(item: dict) -> tuple:
    match = re.fullmatch(r"([a-z_]+?)(\d+)", item["model"], re.IGNORECASE)
    if match:
        return match.group(1).lower(), int(match.group(2)), item["model"].lower()
    return item["model"].lower(), -1, item["model"].lower()


def render_model_list_markdown(models: list[dict], source: Path) -> str:
    """Render the selectable KFM model IDs as UTF-8 Markdown."""
    unique_ids = len({item["model"].lower() for item in models})
    prefix_counts = Counter(item["prefix"] for item in models)
    lines = [
        "# Throne of Desire 可选模型组",
        "",
        f"来源：`{source}`",
        "",
        f"共识别 **{len(models)} 个 KFM 模型组**，对应 **{unique_ids} 个唯一模型编号**。",
        "这里的名称来自 KFM 内部基础 NIF 路径；游戏封包没有提供可直接恢复的角色中文名。",
        "NIF 总数还包括动画、部件、场景和辅助网格，不能当作独立角色数。",
        "",
        "## 前缀统计",
        "",
        "| 前缀 | 数量 |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{prefix}` | {count} |" for prefix, count in sorted(prefix_counts.items())
    )
    lines.extend(
        [
            "",
            "## 完整列表",
            "",
            "| 序号 | 模型编号 | 基础 NIF | NFS 包 | KFM 资源哈希 |",
            "|---:|---|---|---|---|",
        ]
    )
    for number, item in enumerate(models, 1):
        lines.append(
            f"| {number} | `{item['model']}` | `{item['model_path']}` | "
            f"`{item['package']}` | `{item['kfm_hash']}` |"
        )
    lines.extend(
        [
            "",
            "选择时直接给出模型编号即可，例如 `h001` 或 `m001`。",
            "",
        ]
    )
    return "\n".join(lines)


def command_list_models(args: argparse.Namespace) -> int:
    mobilepack = resolve_mobilepack(args.game)
    _, index, _, files, _, mapped = load_catalog(mobilepack)
    by_hash = {entry.asset_hash: entry for entry in mapped}

    candidates: list[FileEntry]
    if args.inventory:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        hashes = {
            parse_hex(item["hash"])
            for item in inventory.get("assets", [])
            if item.get("extension") == ".kfm"
        }
        candidates = [by_hash[value] for value in hashes if value in by_hash]
    else:
        candidates = []
        for entry in mapped:
            try:
                preview, _, _ = read_chunk(
                    mobilepack, entry, index[entry.asset_hash], preview_bytes=512
                )
            except (NotImplementedError, OSError, ValueError):
                continue
            if detect_extension(preview) == ".kfm":
                candidates.append(entry)

    models = []
    for entry in candidates:
        data, compression, header_size = read_chunk(
            mobilepack, entry, index[entry.asset_hash], preview_bytes=8192
        )
        match = KFM_MODEL_REFERENCE.search(data)
        if not match:
            continue
        model_id = match.group(1).decode("ascii").lower()
        prefix_match = re.match(r"[a-z_]+", model_id, re.IGNORECASE)
        models.append(
            {
                "model": model_id,
                "prefix": prefix_match.group(0).lower() if prefix_match else "(numeric)",
                "model_path": match.group(0).decode("ascii"),
                "package": entry.package_name,
                "kfm_hash": f"{entry.asset_hash:016x}",
                "offset": index[entry.asset_hash].offset,
                "compression": compression,
                "header_size": header_size,
            }
        )
    models.sort(key=model_sort_key)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(
            json.dumps(
                {
                    "source": str(mobilepack),
                    "kfm_model_groups": len(models),
                    "unique_model_ids": len({item["model"] for item in models}),
                    "models": models,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        output.write_text(
            render_model_list_markdown(models, mobilepack) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "output": str(output),
                "kfm_model_groups": len(models),
                "unique_model_ids": len({item["model"] for item in models}),
                "prefix_counts": dict(sorted(Counter(item["prefix"] for item in models).items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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

    list_models = subparsers.add_parser(
        "list-models", help="Recover model IDs from all KFM base-NIF references"
    )
    list_models.add_argument("--game", type=Path, required=True)
    list_models.add_argument(
        "--inventory", type=Path, help="Optional scan JSON used to select KFM hashes"
    )
    list_models.add_argument("--output", type=Path, required=True)
    list_models.set_defaults(func=command_list_models)
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
