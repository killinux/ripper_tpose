#!/usr/bin/env python3
"""Extract the package-owned DDS textures for one X-Legend model.

The game prefixes raw LZHAM streams with the five-byte marker
``7f 64 01 15 12``.  Decoding is delegated to the small helper built from
``lzham_codec`` and ``lzham_alpha_decode.cpp``.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from extract_nfs import (
    package_path,
    read_file_list,
    read_index,
    resolve_mobilepack,
    resolve_package_offsets,
    xlegend_hash32,
)
from xlegend_nif import parse_nif


XLZHAM_MAGIC = bytes.fromhex("7f64011512")


def windows_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        raise ValueError(f"WSL decoder requires a drive-qualified path: {resolved}")
    tail = resolved.as_posix()[3:]
    return f"/mnt/{drive}/{tail}"


def tool_command(tool: Path, *paths_or_values: object) -> list[str]:
    arguments = [str(value) for value in paths_or_values]
    path_count = sum(isinstance(value, Path) for value in paths_or_values)
    if path_count:
        arguments = [
            windows_to_wsl(value) if isinstance(value, Path) else str(value)
            for value in paths_or_values
        ]
    if os.name != "nt" or tool.suffix.lower() == ".exe":
        return [str(tool), *[str(value) for value in paths_or_values]]
    return ["wsl.exe", windows_to_wsl(tool), *arguments]


def decoder_command(decoder: Path, source: Path, output: Path, size: int) -> list[str]:
    return tool_command(decoder, source, output, size)


def read_compressed_payload(
    mobilepack: Path, package_name: str, offset: int, compressed_size: int
) -> bytes:
    source = package_path(mobilepack, package_name)
    with source.open("rb") as stream:
        stream.seek(offset)
        header = stream.read(16)
        payload = stream.read(compressed_size)
    if len(header) != 16 or not payload:
        raise ValueError(f"Truncated NFS chunk at {source}:{offset}")
    return payload


def read_payload_prefix(
    mobilepack: Path, package_name: str, offset: int, size: int = 5
) -> bytes:
    source = package_path(mobilepack, package_name)
    with source.open("rb") as stream:
        stream.seek(offset + 16)
        return stream.read(size)


UTILITY_SUFFIX_RE = re.compile(r"_(?:specular|gloss|normal|light)$", re.IGNORECASE)


def package_texture_groups(nif_path: Path, package_name: str) -> list[list[str]]:
    """Return package-owned DDS names grouped in physical filename order.

    X-Legend groups files by the 32-bit hash of the first four filename
    characters.  Base texture families sort by filename, while members of a
    family retain the material order stored in the NIF (diffuse, specular,
    gloss/light, normal).  This differs from sorting every full filename:
    ``*_specular`` physically precedes ``*_gloss``.
    """
    nif = parse_nif(nif_path.read_bytes())
    ordered: list[str] = []
    seen: set[str] = set()
    for value in nif.strings:
        if not value.lower().endswith(".dds"):
            continue
        filename = Path(value.replace("\\", "/")).name
        key = filename.lower()
        if f"{xlegend_hash32(key[:4]):08x}" != package_name:
            continue
        if key not in seen:
            seen.add(key)
            ordered.append(filename)

    grouped: dict[str, list[str]] = {}
    for filename in ordered:
        key = UTILITY_SUFFIX_RE.sub("", Path(filename).stem.lower())
        grouped.setdefault(key, []).append(filename)
    return [grouped[key] for key in sorted(grouped)]


def package_texture_names(nif_path: Path, package_name: str) -> list[str]:
    return [
        filename
        for group in package_texture_groups(nif_path, package_name)
        for filename in group
    ]


def texture_group_cost(group: list[str], streams: list[dict]) -> float:
    """Score one possible name-to-stream alignment using mip dimensions."""

    diffuse_index = next(
        (
            index
            for index, name in enumerate(group)
            if not UTILITY_SUFFIX_RE.search(Path(name).stem)
        ),
        0,
    )
    base_width = streams[diffuse_index]["width"]
    base_height = streams[diffuse_index]["height"]
    cost = 0.0
    for name, stream in zip(group, streams):
        if not UTILITY_SUFFIX_RE.search(Path(name).stem):
            continue
        width, height = stream["width"], stream["height"]
        if (width, height) == (base_width, base_height):
            continue
        # Shipped gloss/specular/normal slots may deliberately use a tiny
        # constant map in place of a full-sized image.
        if width <= 16 and height <= 16:
            cost += 0.15
            continue
        cost += 3.0 + abs(math.log2(width / base_width)) + abs(
            math.log2(height / base_height)
        )
    return cost


def align_texture_groups(
    groups: list[list[str]], streams: list[dict]
) -> tuple[list[tuple[str, int]], list[int]]:
    """Align known NIF names while allowing unreferenced package streams.

    Several character packages retain one to four DDS chunks whose names no
    longer occur in the NIF.  Those chunks can sit between numbered cosmetics
    and the main ``hNNN_*`` maps, so blindly pairing only the first N streams
    shifts every later texture.  Dynamic programming places the gaps where
    same-family texture dimensions remain coherent.
    """

    known_count = sum(len(group) for group in groups)
    if len(streams) < known_count:
        raise ValueError(
            f"Package has {len(streams)} streams for {known_count} DDS names"
        )
    remaining_names = [0] * (len(groups) + 1)
    for index in range(len(groups) - 1, -1, -1):
        remaining_names[index] = remaining_names[index + 1] + len(groups[index])

    @lru_cache(maxsize=None)
    def solve(group_index: int, stream_index: int) -> tuple[float, tuple[int, ...]]:
        if group_index == len(groups):
            return 0.0, ()
        group = groups[group_index]
        maximum_skip = (
            len(streams) - stream_index - remaining_names[group_index]
        )
        best: tuple[float, tuple[int, ...]] | None = None
        for skipped in range(maximum_skip + 1):
            start = stream_index + skipped
            stop = start + len(group)
            group_cost = texture_group_cost(group, streams[start:stop])
            tail_cost, tail_starts = solve(group_index + 1, stop)
            candidate = (group_cost + tail_cost, (start, *tail_starts))
            # Starts are the tie-breaker, leaving unconstrained surplus chunks
            # as late as possible instead of shifting early single-map groups.
            if best is None or candidate < best:
                best = candidate
        assert best is not None
        return best

    _, starts = solve(0, 0)
    mapped: list[tuple[str, int]] = []
    used: set[int] = set()
    for group, start in zip(groups, starts):
        for offset, filename in enumerate(group):
            stream_index = start + offset
            mapped.append((filename, stream_index))
            used.add(stream_index)
    skipped = [index for index in range(len(streams)) if index not in used]
    return mapped, skipped


def fixed_equipment_alignment(
    model_id: str, groups: list[list[str]], streams: list[dict]
) -> tuple[list[tuple[str, int]], list[int]] | None:
    """Resolve the small shared he50 package when only one outfit is named.

    The package contains exactly three ordered sets: he50000, he50001 and
    he50002, each with diffuse/gloss/normal streams.  A single character NIF
    only names its own set, so dimension scoring alone cannot distinguish the
    three equally sized candidates.  The numeric outfit suffix supplies the
    unambiguous physical set index.
    """

    if model_id != "he50" or len(groups) != 1 or len(streams) != 9:
        return None
    group = groups[0]
    if len(group) != 3:
        return None
    key = UTILITY_SUFFIX_RE.sub("", Path(group[0]).stem.lower())
    match = re.fullmatch(r"he50(00[0-2])", key)
    if not match:
        return None
    start = int(match.group(1)) * 3
    mapped = [(filename, start + offset) for offset, filename in enumerate(group)]
    used = {stream_index for _, stream_index in mapped}
    skipped = [index for index in range(len(streams)) if index not in used]
    return mapped, skipped


def extract(args: argparse.Namespace) -> dict:
    mobilepack = resolve_mobilepack(args.game)
    _, index = read_index(mobilepack / "packageindex")
    _, files, _ = read_file_list(mobilepack / "FileListPC.txt")
    model_id = args.model.lower()
    package_name = f"{xlegend_hash32(model_id[:4]):08x}"
    package_entries = [entry for entry in files if entry.package_name == package_name]
    package_index, recovered = resolve_package_offsets(
        mobilepack, index, package_entries
    )
    entries = sorted(
        (entry for entry in package_entries if entry.asset_hash in package_index),
        key=lambda entry: package_index[entry.asset_hash].offset,
    )

    streams: list[tuple[object, int, int]] = []
    source_size = package_path(mobilepack, package_name).stat().st_size
    for number, entry in enumerate(entries):
        offset = package_index[entry.asset_hash].offset
        if read_payload_prefix(mobilepack, entry.package_name, offset) != XLZHAM_MAGIC:
            continue
        next_offset = (
            package_index[entries[number + 1].asset_hash].offset
            if number + 1 < len(entries)
            else source_size
        )
        physical_size = max(0, next_offset - offset - 16)
        # The shipped FileList contains stale compressed sizes for this package.
        # The next 16-byte-aligned NFS header is the authoritative boundary;
        # the streaming decoder safely stops before any alignment padding.
        stored_size = physical_size
        streams.append((entry, offset, stored_size))

    texture_groups = package_texture_groups(args.nif, package_name)
    texture_names = [name for group in texture_groups for name in group]
    if not streams:
        raise ValueError(f"No X-Legend LZHAM texture streams found for {model_id}")
    if len(streams) < len(texture_names):
        raise ValueError(
            f"NIF references {len(texture_names)} package-owned DDS names but "
            f"the package has only {len(streams)} texture streams"
        )

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    decoder = args.decoder.resolve()
    if not decoder.is_file():
        raise FileNotFoundError(f"LZHAM decoder not found: {decoder}")
    etc_decoder = args.etc_decoder.resolve() if args.etc_decoder else None
    if etc_decoder and not etc_decoder.is_file():
        raise FileNotFoundError(f"ETC DDS decoder not found: {etc_decoder}")

    results: list[dict] = []
    skipped_stream_indices: list[int] = []
    with tempfile.TemporaryDirectory(prefix="xlegend_lzham_", dir=output_dir) as temp:
        temp_dir = Path(temp)
        decoded_streams: list[dict] = []
        for number, (entry, offset, stored_size) in enumerate(streams):
            raw_path = temp_dir / f"{number:03}_{entry.asset_hash:016x}.lzham"
            decoded_path = temp_dir / f"{number:03}_{entry.asset_hash:016x}.dds"
            payload = read_compressed_payload(
                mobilepack, entry.package_name, offset, stored_size
            )
            raw_path.write_bytes(payload)
            completed = subprocess.run(
                decoder_command(
                    decoder, raw_path, decoded_path, entry.uncompressed_size
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"Decoder failed for {entry.asset_hash:016x}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                )
            data = decoded_path.read_bytes()
            if not data.startswith(b"DDS "):
                raise ValueError(f"Decoded output is not DDS: {decoded_path}")
            height, width = struct.unpack_from("<II", data, 12)
            decoded_streams.append(
                {
                    "entry": entry,
                    "offset": offset,
                    "stored_size": stored_size,
                    "path": decoded_path,
                    "size": len(data),
                    "width": width,
                    "height": height,
                }
            )

        fixed_alignment = fixed_equipment_alignment(
            model_id, texture_groups, decoded_streams
        )
        if fixed_alignment:
            mapped_streams, skipped_stream_indices = fixed_alignment
        else:
            mapped_streams, skipped_stream_indices = align_texture_groups(
                texture_groups, decoded_streams
            )
        for texture_name, stream_index in mapped_streams:
            stream = decoded_streams[stream_index]
            entry = stream["entry"]
            offset = stream["offset"]
            stored_size = stream["stored_size"]
            dds_path = output_dir / Path(texture_name).name
            dds_path.write_bytes(stream["path"].read_bytes())
            tga_path = None
            if etc_decoder:
                tga_path = dds_path.with_suffix(".tga")
                converted = subprocess.run(
                    tool_command(etc_decoder, dds_path, tga_path),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if converted.returncode:
                    raise RuntimeError(
                        f"ETC decoder failed for {texture_name}: "
                        f"{converted.stderr.strip() or converted.stdout.strip()}"
                    )
                if not tga_path.is_file() or tga_path.stat().st_size <= 18:
                    raise ValueError(f"ETC decoder did not create TGA: {tga_path}")
            results.append(
                {
                    "name": texture_name,
                    "hash": f"{entry.asset_hash:016x}",
                    "package": entry.package_name,
                    "offset": offset,
                    "compressed_size": entry.compressed_size,
                    "stored_compressed_size": stored_size,
                    "declared_uncompressed_size": entry.uncompressed_size,
                    "actual_uncompressed_size": stream["size"],
                    "size_matches_file_list": stream["size"] == entry.uncompressed_size,
                    "width": stream["width"],
                    "height": stream["height"],
                    "physical_stream_index": stream_index,
                    "packageindex_recovered": entry.asset_hash in recovered,
                    "output": str(dds_path),
                    "output_tga": str(tga_path) if tga_path else None,
                }
            )

    manifest = {
        "model": model_id,
        "nif": str(args.nif.resolve()),
        "package": package_name,
        "mapping_rule": (
            "filename-family order with NIF member order, dimension-aligned to "
            "physical LZHAM streams while skipping unreferenced chunks"
        ),
        "nif_texture_names": len(texture_names),
        "package_texture_streams": len(streams),
        "unmapped_streams": [
            {
                "physical_stream_index": stream_index,
                "hash": f"{entry.asset_hash:016x}",
                "offset": offset,
                "stored_compressed_size": stored_size,
            }
            for stream_index in skipped_stream_indices
            for entry, offset, stored_size in [streams[stream_index]]
        ],
        "textures": results,
    }
    manifest_path = output_dir / "textures_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["manifest"] = str(manifest_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--nif", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, required=True)
    parser.add_argument("--etc-decoder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    try:
        manifest = extract(build_parser().parse_args())
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
