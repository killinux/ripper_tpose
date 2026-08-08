"""Read-only helpers for Venus Vacation PRISM KTGL RDB/FDATA archives."""

from __future__ import annotations

import dataclasses
import struct
import zlib
from pathlib import Path
from typing import Iterable, Iterator


RDB_MAGIC = 0x4B52445F  # bytes: _DRK
RDB_ENTRY_MAGIC = 0x4B524449  # bytes: IDRK
FDATA_MAGIC = 0x4B524450  # bytes: PDRK
PRISM_BLOCK_ZLIB = 0x00400000

G1M_TYPE = 0x563BDEF1
G1T_TYPE = 0xAFBEC60C
G1A_TYPE = 0x6FA91671

TYPE_EXTENSIONS = {
    G1M_TYPE: "g1m",
    G1T_TYPE: "g1t",
    G1A_TYPE: "g1a",
    0x7BCD279F: "g1s",
    0x56EFE45C: "grp",
    0xBF6B52C7: "name",
}

_RDB_HEADER = struct.Struct("<6I")
_RDB_ENTRY = struct.Struct("<IIqqqIIII")


class PrismArchiveError(RuntimeError):
    """Raised when a PRISM archive is missing or structurally invalid."""


@dataclasses.dataclass(frozen=True)
class AssetEntry:
    package_path: Path
    package_id: int
    offset: int
    entry_size: int
    content_size: int
    uncompressed_size: int
    resource_type: int
    file_id: int
    type_id: int
    flags: int

    @property
    def extension(self) -> str:
        return TYPE_EXTENSIONS.get(self.type_id, f"type_{self.type_id:08x}")

    @property
    def suggested_name(self) -> str:
        return f"0x{self.file_id:08x}.{self.extension}"

    @property
    def payload_offset(self) -> int:
        return self.offset + self.entry_size - self.content_size

    def as_dict(self) -> dict[str, object]:
        return {
            "package": self.package_path.name,
            "package_id": f"0x{self.package_id:08x}",
            "offset": self.offset,
            "entry_size": self.entry_size,
            "content_size": self.content_size,
            "uncompressed_size": self.uncompressed_size,
            "resource_type": self.resource_type,
            "file_id": f"0x{self.file_id:08x}",
            "type_id": f"0x{self.type_id:08x}",
            "flags": f"0x{self.flags:08x}",
            "extension": self.extension,
            "suggested_name": self.suggested_name,
        }


def data_root_from_game(game: Path) -> Path:
    """Return the fdata_package directory from a game or package path."""
    game = game.expanduser().resolve()
    candidate = game / "fdata_package"
    data_root = candidate if candidate.is_dir() else game
    required = (data_root / "root.rdb", data_root / "root.rdx")
    if not data_root.is_dir() or not all(path.is_file() for path in required):
        raise PrismArchiveError(
            f"Not a Venus Vacation PRISM data directory: {data_root}")
    return data_root


def package_id_from_path(path: Path) -> int:
    try:
        return int(path.stem, 16)
    except ValueError as exc:
        raise PrismArchiveError(f"Invalid FDATA package name: {path.name}") from exc


def iter_fdata_entries(path: Path) -> Iterator[AssetEntry]:
    """Yield every RDB entry stored in one FDATA package."""
    path = path.resolve()
    package_id = package_id_from_path(path)
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(16)
        if len(header) != 16 or struct.unpack_from("<I", header)[0] != FDATA_MAGIC:
            raise PrismArchiveError(f"Invalid FDATA header: {path}")
        first_entry = struct.unpack_from("<I", header, 8)[0]
        if first_entry < 16 or first_entry >= file_size:
            raise PrismArchiveError(f"Invalid FDATA entry offset in {path}")
        stream.seek(first_entry)
        while stream.tell() + _RDB_ENTRY.size <= file_size:
            offset = stream.tell()
            raw = stream.read(_RDB_ENTRY.size)
            (
                magic,
                _version,
                entry_size,
                content_size,
                uncompressed_size,
                resource_type,
                file_id,
                type_id,
                flags,
            ) = _RDB_ENTRY.unpack(raw)
            if magic != RDB_ENTRY_MAGIC:
                break
            if entry_size < _RDB_ENTRY.size or content_size < 0:
                raise PrismArchiveError(
                    f"Invalid entry sizes at {path.name}:0x{offset:x}")
            if entry_size > file_size - offset or content_size > entry_size:
                raise PrismArchiveError(
                    f"Entry exceeds package at {path.name}:0x{offset:x}")
            yield AssetEntry(
                package_path=path,
                package_id=package_id,
                offset=offset,
                entry_size=entry_size,
                content_size=content_size,
                uncompressed_size=uncompressed_size,
                resource_type=resource_type,
                file_id=file_id,
                type_id=type_id,
                flags=flags,
            )
            stream.seek((offset + entry_size + 15) & ~15)


def scan_assets(data_root: Path, type_id: int | None = None) -> list[AssetEntry]:
    """Scan installed FDATA packages, optionally filtering by type KTID."""
    data_root = data_root_from_game(data_root)
    entries: list[AssetEntry] = []
    packages = sorted(data_root.glob("0x*.fdata"), key=lambda path: path.name.lower())
    if not packages:
        raise PrismArchiveError(f"No FDATA packages found under {data_root}")
    for package in packages:
        for entry in iter_fdata_entries(package):
            if type_id is None or entry.type_id == type_id:
                entries.append(entry)
    return entries


def decompress_prism_blocks(data: bytes, expected_size: int | None = None) -> bytes:
    """Decode PRISM's 10-byte-header, 16 KiB-block Zlib stream."""
    output = bytearray()
    cursor = 0
    block_index = 0
    while cursor + 2 <= len(data):
        compressed_size = struct.unpack_from("<H", data, cursor)[0]
        if compressed_size == 0:
            cursor += 2
            break
        block_end = cursor + 10 + compressed_size
        if block_end > len(data):
            raise PrismArchiveError(
                f"Compressed block {block_index} exceeds payload: "
                f"offset={cursor}, size={compressed_size}, payload={len(data)}")
        compressed = data[cursor + 10:block_end]
        try:
            block = zlib.decompress(compressed)
        except zlib.error as exc:
            raise PrismArchiveError(
                f"Invalid Zlib block {block_index} at payload offset {cursor}") from exc
        if len(block) > 0x4000:
            raise PrismArchiveError(
                f"Unexpected decoded block size {len(block)} at block {block_index}")
        output.extend(block)
        cursor = block_end
        block_index += 1
    if any(data[cursor:]):
        raise PrismArchiveError(
            f"Unexpected non-zero bytes after compressed stream at offset {cursor}")
    if expected_size is not None and len(output) != expected_size:
        raise PrismArchiveError(
            f"Decoded size mismatch: expected {expected_size}, got {len(output)}")
    return bytes(output)


def read_asset(entry: AssetEntry) -> bytes:
    """Read and decode one indexed asset without modifying the package."""
    with entry.package_path.open("rb") as stream:
        stream.seek(entry.payload_offset)
        payload = stream.read(entry.content_size)
    if len(payload) != entry.content_size:
        raise PrismArchiveError(
            f"Short read from {entry.package_path.name}:0x{entry.payload_offset:x}")
    if entry.flags == PRISM_BLOCK_ZLIB:
        return decompress_prism_blocks(payload, entry.uncompressed_size)
    if entry.flags == 0:
        if entry.uncompressed_size not in (0, len(payload)):
            raise PrismArchiveError(
                f"Raw size mismatch for {entry.suggested_name}: "
                f"expected {entry.uncompressed_size}, got {len(payload)}")
        return payload
    raise PrismArchiveError(
        f"Unsupported RDB flags 0x{entry.flags:08x} for {entry.suggested_name}")


def parse_g1m_metadata(data: bytes) -> dict[str, object]:
    """Read lightweight G1M header/chunk/skeleton metadata."""
    if len(data) < 24:
        raise PrismArchiveError("G1M is shorter than its 24-byte header")
    if data[:4] == b"_M1G":
        endian = "<"
    elif data[:4] == b"G1M_":
        endian = ">"
    else:
        raise PrismArchiveError(f"Invalid G1M magic: {data[:4]!r}")
    file_size = struct.unpack_from(endian + "I", data, 8)[0]
    first_chunk, reserved, chunk_count = struct.unpack_from(endian + "III", data, 12)
    if first_chunk < 24 or first_chunk > len(data):
        raise PrismArchiveError(f"Invalid G1M first chunk offset: {first_chunk}")
    chunks: list[dict[str, object]] = []
    skeleton_joints = 0
    cursor = first_chunk
    for index in range(chunk_count):
        if cursor + 12 > len(data):
            raise PrismArchiveError(f"G1M chunk {index} header exceeds file")
        magic = data[cursor:cursor + 4].decode("ascii", "replace")
        version = data[cursor + 4:cursor + 8].decode("ascii", "replace")
        size = struct.unpack_from(endian + "I", data, cursor + 8)[0]
        if size < 12 or cursor + size > len(data):
            raise PrismArchiveError(
                f"Invalid G1M chunk {index} size {size} at 0x{cursor:x}")
        chunk = {"index": index, "magic": magic, "version": version,
                 "offset": cursor, "size": size}
        if magic in {"SM1G", "G1MS"} and size >= 26:
            joint_count = struct.unpack_from(endian + "H", data, cursor + 20)[0]
            joint_indices = struct.unpack_from(endian + "H", data, cursor + 22)[0]
            chunk["joint_count"] = joint_count
            chunk["joint_indices_count"] = joint_indices
            skeleton_joints = max(skeleton_joints, joint_count)
        chunks.append(chunk)
        cursor += size
    if file_size not in (0, len(data)):
        raise PrismArchiveError(
            f"G1M header size mismatch: header={file_size}, actual={len(data)}")
    if skeleton_joints >= 50:
        category = "character_candidate"
    elif skeleton_joints > 1:
        category = "skinned"
    else:
        category = "static"
    return {
        "magic": data[:4].decode("ascii"),
        "version": data[4:8].decode("ascii", "replace"),
        "file_size": file_size,
        "first_chunk": first_chunk,
        "reserved": reserved,
        "chunk_count": chunk_count,
        "skeleton_joints": skeleton_joints,
        "category": category,
        "chunks": chunks,
    }


def find_entry(
    entries: Iterable[AssetEntry], *, file_id: int | None = None,
    index: int | None = None,
) -> tuple[int, AssetEntry]:
    """Find an entry by KTID or stable one-based list index."""
    rows = list(entries)
    if file_id is not None:
        matches = [(position + 1, entry) for position, entry in enumerate(rows)
                   if entry.file_id == file_id]
        if not matches:
            raise PrismArchiveError(f"No model with file ID 0x{file_id:08x}")
        if len(matches) > 1:
            raise PrismArchiveError(
                f"File ID 0x{file_id:08x} occurs {len(matches)} times; use --index")
        return matches[0]
    if index is None or index < 1 or index > len(rows):
        raise PrismArchiveError(
            f"Model index must be between 1 and {len(rows)}, got {index}")
    return index, rows[index - 1]
