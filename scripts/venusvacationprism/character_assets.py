#!/usr/bin/env python3
"""Extract and prepare complete PRISM character component assets.

This module is the reusable, non-Blender half of the verified Honoka/Nanami
pipeline.  A character profile supplies BODY/FACE/HAIR component identities;
the exporter then recovers each native resource bundle, resolves every KTID
texture handle through OBJDB, writes G1T/DDS/PNG, converts G1M to glTF, applies
portable material rules, and performs static structural validation.

The optional ``nanami_body722`` postprocessor is deliberately profile-scoped.
In particular, clothID 4 is *not* treated as a universal hidden/helper flag.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib
import json
import shutil
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote

from g1m_to_gltf import G1MConversionError, convert_g1m
from prism_rdb import (
    G1M_TYPE,
    G1T_TYPE,
    AssetEntry,
    PrismArchiveError,
    data_root_from_game,
    read_asset,
    rdb_name_hash,
    scan_assets,
)


OBJDB_TYPE = 0x20A6A0BB
OBJDB_TEXTURE_PROPERTY = 0x6C7321D2
RESOURCE_TYPES = {
    "g1m": G1M_TYPE,
    "oid": 0x1AB40AE8,
    "grp": 0x56EFE45C,
    "ktid": 0x8E39AA37,
    "mtl": 0xB340861A,
}
PROPERTY_SIZES = {
    0: 1,
    1: 1,
    2: 2,
    3: 2,
    4: 4,
    5: 4,
    6: 8,
    7: 8,
    8: 4,
    10: 16,
    12: 8,
    13: 12,
}

DDS_HEADER_FLAGS_TEXTURE = 0x00001007
DDS_HEADER_FLAGS_MIPMAP = 0x00020000
DDS_HEADER_FLAGS_LINEARSIZE = 0x00080000
DDS_SURFACE_FLAGS_TEXTURE = 0x00001000
DDS_SURFACE_FLAGS_MIPMAP = 0x00400008
DDS_FOURCC = 0x00000004
DDS_RGBA = 0x00000041
G1T_EXTENDED_DATA = 0x000000000001
G1T_SRGB = 0x000000002000

FACE_V1_ALPHA = {1, 4, 5, 6, 8, 9, 10}
FACE_V1_IRIS = {2, 3}
NANAMI_BODY722_DEFAULTS: dict[str, Any] = {
    "kind": "nanami_body722",
    "active_dry_meshes": [7, 8, 9, 30],
    "hidden_dt2_meshes": [10, 11, 12, 31, 32, 33],
    "common_meshes": [23, 24],
    "cloth_uv1_meshes": [7, 8, 23, 24],
    "cloth_normal_meshes": [7, 8, 10, 11, 23, 24, 32, 33],
    "cloth_material": 4,
    "common_cloth_material": 8,
    "base_slot": 21,
    "overlay_slot": 22,
    "overlay_mode": "overlay",
    "overlay_strength": 0.054318,
    "normal_slot": 23,
    "normal_strength": 0.15,
}

COMPONENT_FORMATS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
TYPE_WIDTH = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


class CharacterAssetError(RuntimeError):
    """Raised when an asset cannot be resolved or safely converted."""


def _int(value: int | str | None) -> int | None:
    if value is None:
        return None
    return value if isinstance(value, int) else int(value, 0)


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _add_dependency_paths(paths: Sequence[Path]) -> None:
    for path in reversed([Path(item).expanduser().resolve() for item in paths]):
        rendered = str(path)
        if rendered not in sys.path:
            sys.path.insert(0, rendered)


def _pillow():
    try:
        return importlib.import_module("PIL.Image")
    except ModuleNotFoundError as exc:
        raise CharacterAssetError(
            "Pillow is required for G1T PNG conversion; pass its directory with --deps"
        ) from exc


def _numpy():
    try:
        return importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        raise CharacterAssetError(
            "NumPy is required for cloth/material processing; pass it with --deps"
        ) from exc


@dataclass(frozen=True)
class ComponentSpec:
    role: str
    label: str
    model_index: int = 0
    internal_name: str | None = None
    g1m_id: int | None = None
    package: str | None = None
    texture_slots: int | None = None
    resources: Mapping[str, int] = field(default_factory=dict)
    material_profile: str = "auto"
    postprocess: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, role: str, value: Mapping[str, Any]) -> "ComponentSpec":
        label = str(value.get("label") or value.get("internal_name") or "").upper()
        if not label:
            raise CharacterAssetError(f"{role}: component label is required")
        resources = {
            str(key).lower(): int(parsed)
            for key, raw in dict(value.get("resources") or value.get("ids") or {}).items()
            if (parsed := _int(raw)) is not None
        }
        g1m_id = _int(value.get("g1m_id") or value.get("file_id"))
        if g1m_id is None:
            g1m_id = resources.get("g1m")
        return cls(
            role=role.lower(),
            label=label,
            model_index=int(value.get("model_index") or value.get("index") or 0),
            internal_name=(
                str(value["internal_name"]).upper()
                if value.get("internal_name")
                else None
            ),
            g1m_id=g1m_id,
            package=str(value["package"]) if value.get("package") else None,
            texture_slots=(
                int(value["texture_slots"])
                if value.get("texture_slots") is not None
                else None
            ),
            resources=resources,
            material_profile=str(value.get("material_profile") or "auto").lower(),
            postprocess=dict(value.get("postprocess") or {}),
        )


def load_profile(path: Path) -> tuple[str, list[ComponentSpec]]:
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    character = str(
        document.get("character")
        or document.get("name")
        or Path(path).stem
    )
    raw_components = document.get("components")
    if isinstance(raw_components, Mapping):
        specs = [
            ComponentSpec.from_dict(str(role), value)
            for role, value in raw_components.items()
        ]
    elif isinstance(raw_components, list):
        specs = [
            ComponentSpec.from_dict(str(value["role"]), value)
            for value in raw_components
        ]
    else:
        raise CharacterAssetError("profile.components must be an object or array")
    if not specs:
        raise CharacterAssetError("profile contains no components")
    roles = [spec.role for spec in specs]
    if len(roles) != len(set(roles)):
        raise CharacterAssetError(f"duplicate component roles: {roles}")
    return character, specs


def _parse_component(value: str) -> ComponentSpec:
    parts = value.split(":")
    if len(parts) not in (3, 4, 5):
        raise argparse.ArgumentTypeError(
            "component must be ROLE:LABEL:INDEX[:G1M_ID[:MATERIAL_PROFILE]]"
        )
    role, label, index = parts[:3]
    g1m_id = int(parts[3], 0) if len(parts) >= 4 and parts[3] else None
    material_profile = parts[4].lower() if len(parts) == 5 else "auto"
    internal_name = None if g1m_id is not None else label.upper()
    return ComponentSpec(
        role=role.lower(),
        label=label.upper(),
        model_index=int(index, 0),
        internal_name=internal_name,
        g1m_id=g1m_id,
        material_profile=material_profile,
    )


def _parse_ktid(data: bytes) -> list[tuple[int, int]]:
    if len(data) % 8:
        raise CharacterAssetError(
            f"KTID byte size is not a multiple of 8: {len(data)}"
        )
    pairs = [
        struct.unpack_from("<II", data, offset)
        for offset in range(0, len(data), 8)
    ]
    slots = [slot for slot, _handle in pairs]
    if slots != list(range(len(pairs))):
        raise CharacterAssetError(f"KTID slots are not contiguous: {slots[:16]}")
    return pairs


def _unique_entry(
    by_file_id: Mapping[int, Sequence[AssetEntry]],
    file_id: int,
    extension: str,
) -> AssetEntry:
    expected_type = RESOURCE_TYPES[extension]
    matches = [
        entry
        for entry in by_file_id.get(file_id, ())
        if entry.type_id == expected_type
    ]
    if len(matches) != 1:
        raise CharacterAssetError(
            f"{extension.upper()} {_hex(file_id)}: expected one entry, got {len(matches)}"
        )
    return matches[0]


def _infer_bundle(entries: Sequence[AssetEntry], g1m_id: int) -> dict[str, AssetEntry]:
    matches = [
        entry for entry in entries
        if entry.file_id == g1m_id and entry.type_id == G1M_TYPE
    ]
    if len(matches) != 1:
        raise CharacterAssetError(
            f"G1M {_hex(g1m_id)}: expected one entry, got {len(matches)}"
        )
    g1m = matches[0]
    package_entries = sorted(
        (entry for entry in entries if entry.package_path == g1m.package_path),
        key=lambda entry: entry.offset,
    )
    position = package_entries.index(g1m)
    oid = next(
        (
            entry
            for entry in reversed(package_entries[:position])
            if entry.type_id == RESOURCE_TYPES["oid"]
        ),
        None,
    )
    following: list[AssetEntry] = []
    for entry in package_entries[position + 1 :]:
        if entry.type_id in (G1M_TYPE, RESOURCE_TYPES["oid"]):
            break
        following.append(entry)
    result: dict[str, AssetEntry] = {"g1m": g1m}
    if oid is None:
        raise CharacterAssetError(f"G1M {_hex(g1m_id)} has no preceding OID")
    result["oid"] = oid
    for extension in ("grp", "ktid", "mtl"):
        matches = [
            entry
            for entry in following
            if entry.type_id == RESOURCE_TYPES[extension]
        ]
        if len(matches) != 1:
            raise CharacterAssetError(
                f"G1M {_hex(g1m_id)} bundle: expected one {extension}, got {len(matches)}"
            )
        result[extension] = matches[0]
    return result


def _resolve_component_bundle(
    spec: ComponentSpec,
    entries: Sequence[AssetEntry],
    by_file_id: Mapping[int, Sequence[AssetEntry]],
    g1m_indices: Mapping[int, int],
) -> tuple[dict[str, AssetEntry], int]:
    if spec.resources:
        missing = set(RESOURCE_TYPES) - set(spec.resources)
        if missing:
            raise CharacterAssetError(
                f"{spec.label}: explicit resources missing {sorted(missing)}"
            )
        resources = {
            extension: _unique_entry(by_file_id, int(spec.resources[extension]), extension)
            for extension in RESOURCE_TYPES
        }
    elif spec.internal_name:
        resources = {
            extension: _unique_entry(
                by_file_id,
                rdb_name_hash(spec.internal_name, extension),
                extension,
            )
            for extension in RESOURCE_TYPES
        }
    elif spec.g1m_id is not None:
        resources = _infer_bundle(entries, spec.g1m_id)
    else:
        raise CharacterAssetError(
            f"{spec.label}: internal_name, g1m_id, or explicit resources is required"
        )

    packages = {entry.package_path.name.lower() for entry in resources.values()}
    if len(packages) != 1:
        raise CharacterAssetError(
            f"{spec.label}: bundle resources span packages {sorted(packages)}"
        )
    package_name = next(iter(packages))
    if spec.package and package_name != spec.package.lower().removesuffix(".fdata") + ".fdata":
        raise CharacterAssetError(
            f"{spec.label}: expected package {spec.package}, got {package_name}"
        )
    g1m_id = resources["g1m"].file_id
    actual_index = g1m_indices.get(g1m_id)
    if actual_index is None:
        raise CharacterAssetError(f"{spec.label}: G1M is absent from model index")
    if spec.model_index and actual_index != spec.model_index:
        raise CharacterAssetError(
            f"{spec.label}: expected model index {spec.model_index}, got {actual_index}"
        )
    if spec.g1m_id is not None and g1m_id != spec.g1m_id:
        raise CharacterAssetError(
            f"{spec.label}: expected G1M {_hex(spec.g1m_id)}, got {_hex(g1m_id)}"
        )
    return resources, actual_index


def _parse_objdb_records(data: bytes) -> Iterable[dict[str, Any]]:
    if len(data) < 28:
        return
    _magic, _version, header_size, _system, count, _name_ktid, _size = (
        struct.unpack_from("<7I", data)
    )
    offset = header_size
    for record_index in range(count):
        if offset + 24 > len(data):
            raise CharacterAssetError(
                f"OBJDB record {record_index} header exceeds payload"
            )
        record_magic, record_version, record_size = struct.unpack_from(
            "<3I", data, offset
        )
        magic = struct.pack("<I", record_magic)
        if magic == b"IDOK":
            _, _, _, ktid, type_info, property_count = struct.unpack_from(
                "<6I", data, offset
            )
            parent = 0
            fixed_size = 24
        elif magic == b"RDOK":
            _, _, _, ktid, type_info, parent, property_count = struct.unpack_from(
                "<7I", data, offset
            )
            fixed_size = 28
        else:
            raise CharacterAssetError(
                f"Bad OBJDB record {record_index} at 0x{offset:x}: {magic!r}"
            )
        values_offset = offset + fixed_size + property_count * 12
        properties = []
        for property_index in range(property_count):
            type_id, value_count, property_ktid = struct.unpack_from(
                "<3I", data, offset + fixed_size + property_index * 12
            )
            if type_id not in PROPERTY_SIZES:
                raise CharacterAssetError(
                    f"Unsupported OBJDB property type {type_id}"
                )
            byte_size = PROPERTY_SIZES[type_id] * value_count
            raw = data[values_offset : values_offset + byte_size]
            if len(raw) != byte_size:
                raise CharacterAssetError("Short OBJDB property value")
            if type_id == 5:
                values: Any = list(struct.unpack(f"<{value_count}I", raw))
            elif type_id == 4:
                values = list(struct.unpack(f"<{value_count}i", raw))
            else:
                values = raw.hex()
            properties.append(
                {
                    "type_id": type_id,
                    "count": value_count,
                    "property_ktid": property_ktid,
                    "values": values,
                }
            )
            values_offset += byte_size
        yield {
            "index": record_index,
            "offset": offset,
            "magic": magic.decode("ascii"),
            "version": record_version,
            "size": record_size,
            "ktid": ktid,
            "type_info": type_info,
            "parent": parent,
            "properties": properties,
        }
        offset = (offset + record_size + 3) & ~3


def _resolve_texture_handles(
    entries: Sequence[AssetEntry], handles: set[int]
) -> tuple[dict[int, int], dict[int, list[dict[str, Any]]], dict[str, int]]:
    patterns = {handle: struct.pack("<I", handle) for handle in handles}
    resolved: dict[int, set[int]] = defaultdict(set)
    sources: dict[int, list[dict[str, Any]]] = defaultdict(list)
    scanned = matched_assets = 0
    for entry in entries:
        if entry.type_id != OBJDB_TYPE:
            continue
        scanned += 1
        data = read_asset(entry)
        possible = {
            handle for handle, pattern in patterns.items() if pattern in data
        }
        if not possible:
            continue
        matched_assets += 1
        for record in _parse_objdb_records(data):
            handle = int(record["ktid"])
            if handle not in possible:
                continue
            values: set[int] = set()
            for prop in record["properties"]:
                if (
                    prop["property_ktid"] == OBJDB_TEXTURE_PROPERTY
                    and prop["type_id"] == 5
                    and isinstance(prop["values"], list)
                ):
                    values.update(int(value) for value in prop["values"])
            if not values:
                continue
            resolved[handle].update(values)
            sources[handle].append(
                {
                    "file_id": _hex(entry.file_id),
                    "package": entry.package_path.name,
                    "offset": entry.offset,
                    "record_index": record["index"],
                    "record_offset": record["offset"],
                }
            )
    ambiguous = {
        _hex(handle): [_hex(value) for value in sorted(values)]
        for handle, values in resolved.items()
        if len(values) != 1
    }
    missing = handles - set(resolved)
    if ambiguous or missing:
        raise CharacterAssetError(
            "OBJDB handle resolution failed: "
            f"ambiguous={ambiguous}, missing={[_hex(value) for value in sorted(missing)]}"
        )
    return (
        {handle: next(iter(values)) for handle, values in resolved.items()},
        sources,
        {
            "objdb_assets_scanned": scanned,
            "objdb_assets_with_target_handles": matched_assets,
        },
    )


def _dds_header(
    *, width: int, height: int, mipmaps: int, texture_type: int, srgb: bool
) -> bytes:
    dxgi_format: int | None = None
    if texture_type == 0x59:
        bytes_per_block = 8
        fourcc = b"DXT1"
        pf_flags = DDS_FOURCC
        bit_count = red = green = blue = alpha = 0
    elif texture_type in (0x5C, 0x5D, 0x5E, 0x5F):
        bytes_per_block = 8 if texture_type == 0x5C else 16
        dxgi_format = {
            0x5C: 80,
            0x5D: 83,
            0x5E: 95,
            0x5F: 99 if srgb else 98,
        }[texture_type]
        fourcc = b"DX10"
        pf_flags = DDS_FOURCC
        bit_count = red = green = blue = alpha = 0
    elif texture_type == 0x04:
        bytes_per_block = 16
        fourcc = struct.pack("<I", 0x74)
        pf_flags = DDS_FOURCC
        bit_count = red = green = blue = alpha = 0
    elif texture_type in (0x01, 0x02):
        bytes_per_block = 4
        fourcc = b"\0\0\0\0"
        pf_flags = DDS_RGBA
        bit_count = 32
        if texture_type == 0x01:
            red, green, blue, alpha = (
                0x000000FF,
                0x0000FF00,
                0x00FF0000,
                0xFF000000,
            )
        else:
            red, green, blue, alpha = (
                0x00FF0000,
                0x0000FF00,
                0x000000FF,
                0xFF000000,
            )
    else:
        raise CharacterAssetError(
            f"Unsupported PRISM G1T texture type 0x{texture_type:02x}"
        )
    linear_size = (
        ((width + 3) // 4) * ((height + 3) // 4) * bytes_per_block
        if texture_type >= 0x59
        else width * height * bytes_per_block
    )
    flags = DDS_HEADER_FLAGS_TEXTURE | DDS_HEADER_FLAGS_LINEARSIZE
    caps = DDS_SURFACE_FLAGS_TEXTURE
    if mipmaps:
        flags |= DDS_HEADER_FLAGS_MIPMAP
        caps |= DDS_SURFACE_FLAGS_MIPMAP
    pixel_format = struct.pack(
        "<II4sIIIII", 32, pf_flags, fourcc, bit_count, red, green, blue, alpha
    )
    header = struct.pack(
        "<7I11I", 124, flags, height, width, linear_size, 0, mipmaps, *([0] * 11)
    )
    header += pixel_format
    header += struct.pack("<5I", caps, 0, 0, 0, 0)
    result = b"DDS " + header
    if dxgi_format is not None:
        result += struct.pack("<5I", dxgi_format, 3, 0, 1, 0)
    return result


def _convert_g1t(path: Path) -> dict[str, Any]:
    Image = _pillow()
    data = path.read_bytes()
    if data[:4] != b"GT1G":
        raise CharacterAssetError(f"Not a G1T: {path}")
    version, total_size, header_size, count, platform, extra_size = (
        struct.unpack_from("<6I", data, 4)
    )
    if count != 1 or total_size != len(data) or platform != 10:
        raise CharacterAssetError(
            f"Unexpected G1T container: count={count}, size={total_size}/{len(data)}, "
            f"platform={platform}"
        )
    global_flags = struct.unpack_from("<I", data, 28)[0]
    record_offset = header_size + struct.unpack_from("<I", data, header_size)[0]
    packed_mips, texture_type, dimensions = struct.unpack_from(
        "<BBB", data, record_offset
    )
    mipmaps = packed_mips >> 4
    z_mipmaps = packed_mips & 0xF
    width = 1 << (dimensions & 0xF)
    height = 1 << (dimensions >> 4)
    raw_local_flags = data[record_offset + 3 : record_offset + 8]
    local_flags = bytes(
        ((value >> 4) | ((value & 0xF) << 4)) for value in raw_local_flags
    )
    combined_flags = global_flags
    for value in local_flags:
        combined_flags = (combined_flags << 8) | value
    payload_offset = record_offset + 8
    extended_size = 0
    if combined_flags & G1T_EXTENDED_DATA:
        extended_size = struct.unpack_from("<I", data, payload_offset)[0]
        payload_offset += extended_size
    payload = data[payload_offset:]
    dds_path = path.with_suffix(".dds")
    dds_path.write_bytes(
        _dds_header(
            width=width,
            height=height,
            mipmaps=mipmaps,
            texture_type=texture_type,
            srgb=bool(combined_flags & G1T_SRGB),
        )
        + payload
    )
    png_path = path.with_suffix(".png")
    if texture_type == 0x04:
        first_level = payload[: width * height * 16]
        pixels = [
            tuple(max(0, min(255, round(channel * 255.0))) for channel in rgba)
            for rgba in struct.iter_unpack("<4f", first_level)
        ]
        image = Image.new("RGBA", (width, height))
        image.putdata(pixels)
        decoder = "native float32 RGBA"
    else:
        with Image.open(dds_path) as source:
            image = source.convert("RGBA")
            image.load()
        decoder = "Pillow DDS"
    image.save(png_path, optimize=True)
    extrema = image.getextrema()
    alpha_histogram = image.getchannel("A").histogram()
    stats = {
        "decoder": decoder,
        "png": png_path.name,
        "size": [width, height],
        "channel_extrema": {
            channel: [int(low), int(high)]
            for channel, (low, high) in zip("RGBA", extrema, strict=True)
        },
        "alpha_min": int(extrema[3][0]),
        "alpha_max": int(extrema[3][1]),
        "alpha_unique_count": sum(bool(value) for value in alpha_histogram),
        "alpha_zero_pixels": int(alpha_histogram[0]),
        "alpha_partial_pixels": int(sum(alpha_histogram[1:255])),
        "alpha_opaque_pixels": int(alpha_histogram[255]),
        "has_nonopaque_alpha": extrema[3][0] < 255,
        "has_partial_alpha": sum(alpha_histogram[1:255]) > 0,
    }
    return {
        "g1t_version": _hex(version),
        "header_size": header_size,
        "extra_container_size": extra_size,
        "texture_type": f"0x{texture_type:02x}",
        "width": width,
        "height": height,
        "mipmaps": mipmaps,
        "z_mipmaps": z_mipmaps,
        "combined_flags": f"0x{combined_flags:x}",
        "srgb": bool(combined_flags & G1T_SRGB),
        "extended_data_size": extended_size,
        "payload_size": len(payload),
        "image": stats,
    }


def _bake_face_v1_iris(
    component_dir: Path, texture_rows: Sequence[Mapping[str, Any]], label: str
) -> dict[str, Any]:
    """Bake the two face iris overlays used by the verified PRISM face shader."""

    Image = _pillow()
    texture_dir = component_dir / "textures"
    outputs: list[dict[str, Any]] = []
    for material, base_slot, iris_slot in ((2, 25, 26), (3, 35, 36)):
        if max(base_slot, iris_slot) >= len(texture_rows):
            raise CharacterAssetError(
                f"{label}: face_v1 needs texture slots 0..{iris_slot}, "
                f"but KTID contains {len(texture_rows)} slots"
            )
        base_path = component_dir / str(texture_rows[base_slot]["files"]["png"])
        iris_path = component_dir / str(texture_rows[iris_slot]["files"]["png"])
        with Image.open(base_path) as source:
            base = source.convert("RGBA")
            base.load()
        with Image.open(iris_path) as source:
            iris_source = source.convert("RGBA")
            iris_source.load()

        crop = iris_source.crop(
            (0, 0, max(1, iris_source.width // 4), max(1, iris_source.height // 4))
        )
        target_size = (
            max(1, round(base.width * 0.375)),
            max(1, round(base.height * 0.375)),
        )
        resampling = getattr(Image, "Resampling", Image)
        crop = crop.resize(target_size, resampling.LANCZOS)
        canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
        origin = ((base.width - crop.width) // 2, (base.height - crop.height) // 2)
        canvas.alpha_composite(crop, origin)

        # The game shader attenuates the iris texture radially.  Bake that mask
        # so the resulting glTF remains useful in Blender and generic viewers.
        np = _numpy()
        yy, xx = np.ogrid[: base.height, : base.width]
        cx = (base.width - 1) * 0.5
        cy = (base.height - 1) * 0.5
        radius_scale = max(1.0, min(base.width, base.height))
        radius = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius_scale
        amount = 1.0 - np.clip((radius - 0.10) / 0.08, 0.0, 1.0)
        mask = Image.fromarray(np.rint(amount * 255.0).astype(np.uint8), mode="L")
        mask = Image.fromarray(
            np.minimum(
                np.asarray(mask, dtype=np.uint8),
                np.asarray(canvas.getchannel("A"), dtype=np.uint8),
            ),
            mode="L",
        )
        baked = Image.composite(canvas, base, mask)
        baked.putalpha(base.getchannel("A"))

        baked_rel = Path("textures") / f"iris_overlay_{iris_slot:03d}.png"
        mask_rel = Path("textures") / f"iris_overlay_{iris_slot:03d}_mask.png"
        baked.save(component_dir / baked_rel, optimize=True)
        mask.save(component_dir / mask_rel, optimize=True)
        outputs.append(
            {
                "material": material,
                "base_slot": base_slot,
                "iris_slot": iris_slot,
                "baked": baked_rel.as_posix(),
                "mask": mask_rel.as_posix(),
                "crop_fraction": 0.25,
                "canvas_fraction": 0.375,
                "radial_fade": [0.10, 0.18],
            }
        )
    report = {"profile": "face_v1", "overlays": outputs}
    _json_write(component_dir / "iris_overlay_mapping.json", report)
    return report


def _material_texture_semantics(material: Mapping[str, Any]) -> dict[str, Any]:
    pbr = material.get("pbrMetallicRoughness") or {}
    return {
        "baseColor": pbr.get("baseColorTexture"),
        "metallicRoughness": pbr.get("metallicRoughnessTexture"),
        "normal": material.get("normalTexture"),
        "occlusion": material.get("occlusionTexture"),
        "emissive": material.get("emissiveTexture"),
    }


def _patch_gltf_materials(
    component_dir: Path,
    label: str,
    role: str,
    material_profile: str,
    texture_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Point converter materials at decoded PNGs and preserve alpha semantics."""

    gltf_path = component_dir / f"{label}.gltf"
    document = json.loads(gltf_path.read_text(encoding="utf-8"))
    images = document.get("images", [])
    if len(images) != len(texture_rows):
        raise CharacterAssetError(
            f"{label}: converter emitted {len(images)} images, KTID resolved "
            f"{len(texture_rows)}; refusing an unverified slot mapping"
        )
    iris_mapping: dict[int, str] = {}
    if material_profile == "face_v1":
        iris = _bake_face_v1_iris(component_dir, texture_rows, label)
        iris_mapping = {
            int(row["base_slot"]): str(row["baked"]) for row in iris["overlays"]
        }
    for slot, (image, row) in enumerate(zip(images, texture_rows, strict=True)):
        image["uri"] = iris_mapping.get(slot, str(row["files"]["png"]))
        image["name"] = f"slot_{slot:03d}_{row['handle']}"

    mesh_materials: dict[int, list[int]] = defaultdict(list)
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        for primitive in mesh.get("primitives", []):
            if "material" in primitive:
                mesh_materials[int(primitive["material"])].append(mesh_index)

    mappings: list[dict[str, Any]] = []
    for material_index, material in enumerate(document.get("materials", [])):
        if material_profile == "face_v1":
            alpha = material_index in FACE_V1_ALPHA
        elif material_profile == "hair_v1":
            alpha = True
        else:
            pbr = material.get("pbrMetallicRoughness") or {}
            base_info = pbr.get("baseColorTexture") or {}
            texture_index = base_info.get("index")
            source = None
            if isinstance(texture_index, int) and texture_index < len(document.get("textures", [])):
                source = document["textures"][texture_index].get("source")
            alpha = bool(
                isinstance(source, int)
                and source < len(texture_rows)
                and texture_rows[source]["conversion"]["image"]["has_nonopaque_alpha"]
                and texture_rows[source]["conversion"]["image"]["alpha_partial_pixels"] > 16
            )
        if alpha:
            material["alphaMode"] = "BLEND"
            material["doubleSided"] = True
        else:
            material.pop("alphaCutoff", None)
            material["alphaMode"] = "OPAQUE"
        semantic_rows: dict[str, Any] = {}
        for semantic, texture_info in _material_texture_semantics(material).items():
            if not isinstance(texture_info, Mapping):
                continue
            texture_index = texture_info.get("index")
            if not isinstance(texture_index, int) or texture_index >= len(document.get("textures", [])):
                continue
            source = document["textures"][texture_index].get("source")
            if not isinstance(source, int) or source >= len(texture_rows):
                continue
            row = texture_rows[source]
            semantic_rows[semantic] = {
                "texture": texture_index,
                "slot": source,
                "texCoord": int(texture_info.get("texCoord", 0)),
                "handle": row["handle"],
                "g1t_id": row["g1t_id"],
                "png": images[source]["uri"],
                "alpha": row["conversion"]["image"],
            }
        mappings.append(
            {
                "material": material_index,
                "name": material.get("name"),
                "meshes": sorted(set(mesh_materials.get(material_index, []))),
                "alpha_mode": material.get("alphaMode", "OPAQUE"),
                "double_sided": bool(material.get("doubleSided", False)),
                "textures": semantic_rows,
            }
        )

    if document.get("buffers"):
        document["buffers"][0]["uri"] = f"{label}.bin"
    _json_write(gltf_path, document)
    report = {
        "role": role,
        "profile": material_profile,
        "materials": mappings,
        "verified_slot_count": len(texture_rows),
    }
    _json_write(component_dir / "material_mapping.json", report)
    return report


def _accessor_array(document: Mapping[str, Any], payload: bytearray, index: int):
    np = _numpy()
    accessor = document["accessors"][index]
    if "bufferView" not in accessor or accessor.get("sparse"):
        raise CharacterAssetError(f"accessor {index}: sparse/implicit data is unsupported")
    view = document["bufferViews"][int(accessor["bufferView"])]
    component_type = int(accessor["componentType"])
    dtypes = {
        5120: np.dtype("<i1"),
        5121: np.dtype("<u1"),
        5122: np.dtype("<i2"),
        5123: np.dtype("<u2"),
        5125: np.dtype("<u4"),
        5126: np.dtype("<f4"),
    }
    if component_type not in dtypes or accessor["type"] not in TYPE_WIDTH:
        raise CharacterAssetError(f"accessor {index}: unsupported layout")
    dtype = dtypes[component_type]
    width = TYPE_WIDTH[accessor["type"]]
    count = int(accessor["count"])
    stride = int(view.get("byteStride", dtype.itemsize * width))
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    end = offset + (max(0, count - 1) * stride) + dtype.itemsize * width
    if offset < 0 or end > len(payload):
        raise CharacterAssetError(f"accessor {index}: data exceeds external buffer")
    return np.ndarray(
        shape=(count, width),
        dtype=dtype,
        buffer=payload,
        offset=offset,
        strides=(stride, dtype.itemsize),
    )


def _read_g1mg(
    path: Path, gust_dir: Path, dependency_paths: Sequence[Path]
) -> tuple[dict[str, Any], str]:
    _add_dependency_paths([*dependency_paths, gust_dir])
    try:
        module = importlib.import_module("g1m_export_meshes")
    except (ImportError, OSError) as exc:
        raise CharacterAssetError(
            f"cannot import Gust g1m_export_meshes from {gust_dir}: {exc}"
        ) from exc
    module_path = Path(module.__file__).resolve()
    if module_path.parent != Path(gust_dir).resolve():
        raise CharacterAssetError(
            f"g1m_export_meshes resolved to {module_path}, not {Path(gust_dir).resolve()}"
        )
    with path.open("rb") as stream:
        magic = stream.read(4)
        if magic == b"_M1G":
            endian = "<"
        elif magic == b"G1M_":
            endian = ">"
        else:
            raise CharacterAssetError(f"not a G1M: {path}")
        stream.seek(12)
        header = stream.read(12)
        if len(header) != 12:
            raise CharacterAssetError(f"truncated G1M header: {path}")
        first_chunk, _reserved, chunk_count = struct.unpack(endian + "III", header)
        stream.seek(first_chunk)
        for _ in range(chunk_count):
            start = stream.tell()
            chunk_header = stream.read(12)
            if len(chunk_header) != 12:
                break
            chunk_magic = chunk_header[:4]
            (size,) = struct.unpack(endian + "I", chunk_header[8:12])
            if size < 12:
                raise CharacterAssetError(f"invalid G1M chunk size {size}")
            if chunk_magic in (b"G1MG", b"GM1G"):
                stream.seek(start)
                return module.parseG1MG(stream.read(size), endian), endian
            stream.seek(start + size)
    raise CharacterAssetError(f"G1MG chunk not found: {path}")


def _g1mg_cloth_meshes(metadata: Mapping[str, Any], cloth_id: int) -> set[int]:
    try:
        section = next(
            item for item in metadata["sections"] if item["type"] == "MESH_LOD"
        )
    except (KeyError, StopIteration) as exc:
        raise CharacterAssetError("G1MG MESH_LOD section is missing") from exc
    return {
        int(mesh)
        for block in section["data"]
        for lod in block["lod"]
        if int(lod["clothID"]) == cloth_id
        for mesh in lod["indices"]
    }


def _normal_dot_stats(positions, indices, normals) -> dict[str, float]:
    np = _numpy()
    triangles = indices.reshape(-1, 3)
    face = np.cross(
        positions[triangles[:, 1]] - positions[triangles[:, 0]],
        positions[triangles[:, 2]] - positions[triangles[:, 0]],
    )
    average = (
        normals[triangles[:, 0]]
        + normals[triangles[:, 1]]
        + normals[triangles[:, 2]]
    )
    face_length = np.linalg.norm(face, axis=1)
    average_length = np.linalg.norm(average, axis=1)
    valid = (face_length > 1e-12) & (average_length > 1e-12)
    if not bool(valid.any()):
        return {"dot_mean": 0.0, "dot_negative_fraction": 0.0}
    dots = np.einsum(
        "ij,ij->i",
        face[valid] / face_length[valid, None],
        average[valid] / average_length[valid, None],
    )
    return {
        "dot_mean": float(dots.mean()),
        "dot_negative_fraction": float((dots < 0).mean()),
    }


def _geometric_normals(positions, indices):
    np = _numpy()
    triangles = indices.reshape(-1, 3)
    face = np.cross(
        positions[triangles[:, 1]] - positions[triangles[:, 0]],
        positions[triangles[:, 2]] - positions[triangles[:, 0]],
    )
    result = np.zeros_like(positions, dtype=np.float64)
    for lane in range(3):
        np.add.at(result, triangles[:, lane], face)
    lengths = np.linalg.norm(result, axis=1)
    valid = lengths > 1e-12
    result[valid] /= lengths[valid, None]
    result[~valid] = (0.0, 0.0, 1.0)
    return result.astype(np.float32)


def _repair_cloth_normals(
    document: dict[str, Any],
    payload: bytearray,
    metadata: Mapping[str, Any],
    configured_meshes: Iterable[int],
) -> dict[str, Any]:
    cloth4 = _g1mg_cloth_meshes(metadata, 4)
    targets = {int(item) for item in configured_meshes}
    missing = targets - cloth4
    if missing:
        raise CharacterAssetError(
            f"BODY722 normal targets are not G1MG clothID 4 meshes: {sorted(missing)}"
        )
    rows: list[dict[str, Any]] = []
    for mesh_index in sorted(targets):
        if mesh_index >= len(document.get("meshes", [])):
            raise CharacterAssetError(f"BODY722 mesh {mesh_index} is absent")
        for primitive_index, primitive in enumerate(
            document["meshes"][mesh_index].get("primitives", [])
        ):
            if int(primitive.get("mode", 4)) != 4:
                raise CharacterAssetError(
                    f"mesh {mesh_index}: normal repair requires TRIANGLES"
                )
            attributes = primitive.get("attributes", {})
            if not all(key in attributes for key in ("POSITION", "NORMAL")) or "indices" not in primitive:
                raise CharacterAssetError(f"mesh {mesh_index}: incomplete geometry attributes")
            positions = _accessor_array(
                document, payload, int(attributes["POSITION"])
            ).astype("float64")
            normals = _accessor_array(document, payload, int(attributes["NORMAL"]))
            indices = _accessor_array(
                document, payload, int(primitive["indices"])
            ).reshape(-1).astype("int64")
            if len(indices) % 3 or normals.shape != positions.shape or normals.dtype.str != "<f4":
                raise CharacterAssetError(f"mesh {mesh_index}: unexpected normal layout")
            before = _normal_dot_stats(positions, indices, normals.astype("float64"))
            repaired = _geometric_normals(positions, indices)
            normals[:] = repaired
            removed_tangent = attributes.pop("TANGENT", None)
            rows.append(
                {
                    "mesh": mesh_index,
                    "primitive": primitive_index,
                    "vertices": len(positions),
                    "triangles": len(indices) // 3,
                    "before": before,
                    "after": _normal_dot_stats(
                        positions, indices, repaired.astype("float64")
                    ),
                    "removed_tangent_accessor": removed_tangent,
                }
            )
    report = {
        "cloth_id": 4,
        "all_cloth4_meshes": sorted(cloth4),
        "configured_meshes": sorted(targets),
        "method": "area-weighted geometric vertex normals; tangents removed",
        "meshes": rows,
        "passed": len(rows) == len(targets),
    }
    document.setdefault("extras", {})["prism_cloth_normal_repair"] = report
    return report


def _set_material_texcoord(material: Any, texcoord: int) -> int:
    changed = 0

    def visit(value: Any, parent_key: str = "") -> None:
        nonlocal changed
        if isinstance(value, dict):
            if parent_key.endswith("Texture") and "index" in value:
                value["texCoord"] = texcoord
                changed += 1
            for key, child in value.items():
                visit(child, key)
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key)

    visit(material)
    return changed


def _hide_mesh_nodes(document: dict[str, Any], meshes: Iterable[int]) -> list[int]:
    hidden_meshes = {int(item) for item in meshes}
    hidden_nodes = sorted(
        index
        for index, node in enumerate(document.get("nodes", []))
        if int(node.get("mesh", -1)) in hidden_meshes
    )
    hidden_set = set(hidden_nodes)
    for node_index in hidden_nodes:
        node = document["nodes"][node_index]
        mesh_index = int(node.pop("mesh"))
        node.pop("skin", None)
        node["name"] = f"DISPLAY_SET_HIDDEN_Mesh_{mesh_index}"
        node.setdefault("extras", {})["prism_hidden_display_mesh"] = mesh_index
    for scene in document.get("scenes", []):
        scene["nodes"] = [item for item in scene.get("nodes", []) if item not in hidden_set]
    for node in document.get("nodes", []):
        if "children" in node:
            node["children"] = [
                item for item in node["children"] if item not in hidden_set
            ]
            if not node["children"]:
                node.pop("children")
    return hidden_nodes


def _linear_overlay_bake(
    base_path: Path, overlay_path: Path, output_path: Path, strength: float
) -> dict[str, Any]:
    Image = _pillow()
    np = _numpy()
    with Image.open(base_path) as source:
        base_image = source.convert("RGBA")
        base_image.load()
    with Image.open(overlay_path) as source:
        overlay_image = source.convert("RGBA")
        overlay_image.load()
    if overlay_image.size != base_image.size:
        resampling = getattr(Image, "Resampling", Image)
        overlay_image = overlay_image.resize(base_image.size, resampling.LANCZOS)
    base = np.asarray(base_image, dtype=np.float32) / 255.0
    overlay = np.asarray(overlay_image, dtype=np.float32) / 255.0

    def to_linear(values):
        return np.where(
            values <= 0.04045,
            values / 12.92,
            ((values + 0.055) / 1.055) ** 2.4,
        )

    def to_srgb(values):
        return np.where(
            values <= 0.0031308,
            values * 12.92,
            1.055 * np.maximum(values, 0.0) ** (1.0 / 2.4) - 0.055,
        )

    base_linear = to_linear(base[..., :3])
    overlay_linear = to_linear(overlay[..., :3])
    combined = np.where(
        base_linear <= 0.5,
        2.0 * base_linear * overlay_linear,
        1.0 - 2.0 * (1.0 - base_linear) * (1.0 - overlay_linear),
    )
    amount = float(strength) * overlay[..., 3:4]
    rgb = to_srgb(base_linear * (1.0 - amount) + combined * amount)
    result = np.concatenate((np.clip(rgb, 0.0, 1.0), base[..., 3:4]), axis=2)
    encoded = np.rint(result * 255.0).astype(np.uint8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(encoded, mode="RGBA").save(output_path, optimize=True)
    return {
        "base": str(base_path),
        "overlay": str(overlay_path),
        "output": str(output_path),
        "mode": "linear overlay",
        "strength": strength,
        "size": list(base_image.size),
    }


def _texture_index_for_source(document: Mapping[str, Any], source: int) -> int:
    matches = [
        index
        for index, texture in enumerate(document.get("textures", []))
        if int(texture.get("source", -1)) == source
    ]
    if not matches:
        raise CharacterAssetError(f"no glTF texture references image slot {source}")
    return matches[0]


def _apply_nanami_body722(
    component_dir: Path,
    label: str,
    g1m_path: Path,
    gust_dir: Path,
    dependency_paths: Sequence[Path],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the evidence-backed portable dry/static BODY722 approximation."""

    config = copy.deepcopy(NANAMI_BODY722_DEFAULTS)
    config.update(dict(overrides))
    gltf_path = component_dir / f"{label}.gltf"
    bin_path = component_dir / f"{label}.bin"
    document = json.loads(gltf_path.read_text(encoding="utf-8"))
    if len(document.get("buffers", [])) != 1:
        raise CharacterAssetError("BODY722 expects exactly one external glTF buffer")
    document["buffers"][0]["uri"] = bin_path.name
    payload = bytearray(bin_path.read_bytes())
    metadata, endian = _read_g1mg(g1m_path, gust_dir, dependency_paths)
    normal_report = _repair_cloth_normals(
        document,
        payload,
        metadata,
        config["cloth_normal_meshes"],
    )
    _json_write(component_dir / "cloth_normal_repair.json", normal_report)

    # Retain the complete native display-set geometry as a separate glTF before
    # selecting the dry/static portable view.  This is not a reconstructed mesh.
    full_gltf = component_dir / f"{label}_FULL_SOURCE.gltf"
    full_bin = component_dir / f"{label}_FULL_SOURCE.bin"
    full_document = copy.deepcopy(document)
    full_document["buffers"][0]["uri"] = full_bin.name
    full_document.setdefault("extras", {})["prism_full_source"] = {
        "display_sets": "all native model nodes retained",
        "cloth_id_4_policy": "metadata only; not hidden generically",
    }
    full_bin.write_bytes(payload)
    _json_write(full_gltf, full_document)

    hidden_nodes = _hide_mesh_nodes(document, config["hidden_dt2_meshes"])
    hidden_meshes = sorted(
        int(document["nodes"][item]["extras"]["prism_hidden_display_mesh"])
        for item in hidden_nodes
    )
    if hidden_meshes != sorted(int(item) for item in config["hidden_dt2_meshes"]):
        raise CharacterAssetError(
            f"BODY722 display-set mismatch: hid {hidden_meshes}, expected "
            f"{sorted(config['hidden_dt2_meshes'])}"
        )

    duplicated: dict[int, int] = {}
    mesh_changes: list[dict[str, Any]] = []
    for mesh_index in sorted(int(item) for item in config["cloth_uv1_meshes"]):
        if mesh_index >= len(document.get("meshes", [])):
            raise CharacterAssetError(f"BODY722 cloth UV1 mesh {mesh_index} is absent")
        expected_material = (
            int(config["cloth_material"])
            if mesh_index in {7, 8}
            else int(config["common_cloth_material"])
        )
        for primitive_index, primitive in enumerate(
            document["meshes"][mesh_index].get("primitives", [])
        ):
            old_material = int(primitive.get("material", -1))
            if old_material != expected_material:
                raise CharacterAssetError(
                    f"BODY722 mesh {mesh_index} material is {old_material}, "
                    f"expected {expected_material}; profile is not safe for this model"
                )
            if old_material not in duplicated:
                duplicate = copy.deepcopy(document["materials"][old_material])
                old_name = duplicate.get("name", f"Material_{old_material:02d}")
                duplicate["name"] = f"{old_name}_CLOTH_UV1"
                _set_material_texcoord(duplicate, 1)
                duplicated[old_material] = len(document["materials"])
                document["materials"].append(duplicate)
            new_material = duplicated[old_material]
            primitive["material"] = new_material
            mesh_changes.append(
                {
                    "mesh": mesh_index,
                    "primitive": primitive_index,
                    "old_material": old_material,
                    "new_material": new_material,
                    "texcoord": 1,
                }
            )

    base_slot = int(config["base_slot"])
    overlay_slot = int(config["overlay_slot"])
    normal_slot = int(config["normal_slot"])
    if max(base_slot, overlay_slot, normal_slot) >= len(document.get("images", [])):
        raise CharacterAssetError("BODY722 required shader texture slots are absent")
    base_uri = unquote(str(document["images"][base_slot]["uri"]))
    overlay_uri = unquote(str(document["images"][overlay_slot]["uri"]))
    baked_rel = (
        Path("textures")
        / "baked"
        / f"{label}_Mat04_Cloth_overlay_{float(config['overlay_strength']):.6f}.png"
    )
    bake_report = _linear_overlay_bake(
        component_dir / Path(base_uri),
        component_dir / Path(overlay_uri),
        component_dir / baked_rel,
        float(config["overlay_strength"]),
    )
    document["images"].append(
        {
            "name": f"slot_{base_slot:03d}_plus_{overlay_slot:03d}_linear_overlay",
            "uri": baked_rel.as_posix(),
        }
    )
    old_base_texture = _texture_index_for_source(document, base_slot)
    old_texture = document["textures"][old_base_texture]
    new_texture: dict[str, Any] = {"source": len(document["images"]) - 1}
    if "sampler" in old_texture:
        new_texture["sampler"] = old_texture["sampler"]
    document["textures"].append(new_texture)
    baked_texture_index = len(document["textures"]) - 1

    cloth_material_index = duplicated[int(config["cloth_material"])]
    cloth_material = document["materials"][cloth_material_index]
    cloth_material["name"] = (
        f"Material_{int(config['cloth_material']):02d}_CLOTH_UV1_"
        f"OVERLAY_{float(config['overlay_strength']):.3f}"
    )
    pbr = cloth_material.setdefault("pbrMetallicRoughness", {})
    pbr["baseColorTexture"] = {"index": baked_texture_index, "texCoord": 1}
    pbr.setdefault("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
    cloth_material["normalTexture"] = {
        "index": _texture_index_for_source(document, normal_slot),
        "texCoord": 1,
        "scale": float(config["normal_strength"]),
    }
    cloth_material["alphaMode"] = "OPAQUE"
    cloth_material.pop("alphaCutoff", None)

    display_report = {
        "policy": "portable dry/static visual approximation",
        "active_dry_meshes": sorted(int(item) for item in config["active_dry_meshes"]),
        "hidden_dt2_meshes": hidden_meshes,
        "hidden_nodes": hidden_nodes,
        "common_meshes": sorted(int(item) for item in config["common_meshes"]),
        "cloth_uv1_meshes": sorted(int(item) for item in config["cloth_uv1_meshes"]),
        "mesh_material_changes": mesh_changes,
        "duplicated_materials": {str(key): value for key, value in duplicated.items()},
        "full_source_gltf": full_gltf.name,
        "full_source_bin": full_bin.name,
    }
    semantics = {
        "profile": "nanami_body722",
        "g1mg_endian": endian,
        "cloth_id_4_policy": (
            "Only the configured BODY722 mesh set is normal-repaired; clothID 4 "
            "is never treated as a generic hide rule."
        ),
        "selected_display": display_report,
        "base_overlay": {
            "slots": [base_slot, overlay_slot],
            "texcoord": 1,
            "strength": float(config["overlay_strength"]),
            "baked_image": baked_rel.as_posix(),
        },
        "cloth_normal": {
            "slot": normal_slot,
            "texcoord": 1,
            "scale": float(config["normal_strength"]),
        },
        "runtime_limitation": (
            "wet/DT2 conditional behavior remains authoritative in original G1M/MTL; "
            "the final glTF selects a portable dry/static pass"
        ),
    }
    document.setdefault("extras", {})["body722_static_final"] = semantics
    payload_bytes = bytes(payload)
    document["buffers"][0]["byteLength"] = len(payload_bytes)
    document["buffers"][0]["uri"] = bin_path.name
    bin_path.write_bytes(payload_bytes)
    _json_write(gltf_path, document)
    _json_write(component_dir / "display_set.json", display_report)
    _json_write(component_dir / "shader_semantics_report.json", semantics)
    _json_write(component_dir / "body722_overlay_bake.json", bake_report)
    return {
        "kind": "nanami_body722",
        "full_source_gltf": str(full_gltf.resolve()),
        "full_source_bin": str(full_bin.resolve()),
        "normal_report": "cloth_normal_repair.json",
        "display_report": "display_set.json",
        "semantics_report": "shader_semantics_report.json",
        "overlay_report": "body722_overlay_bake.json",
    }


def _accessor_layout(
    document: Mapping[str, Any], accessor_index: int
) -> tuple[Mapping[str, Any], int, int, str, int]:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    code, component_size = COMPONENT_FORMATS[int(accessor["componentType"])]
    width = TYPE_WIDTH[str(accessor["type"])]
    element_size = component_size * width
    stride = int(view.get("byteStride", element_size))
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, offset, stride, code, width


def _read_element(
    payload: bytearray,
    document: Mapping[str, Any],
    accessor_index: int,
    element_index: int,
) -> tuple[list[int | float], int, str]:
    accessor, offset, stride, code, width = _accessor_layout(document, accessor_index)
    if not 0 <= element_index < int(accessor["count"]):
        raise IndexError(element_index)
    item_offset = offset + stride * element_index
    values = list(struct.unpack_from("<" + code * width, payload, item_offset))
    return values, item_offset, code


def _repair_joint_sentinels(
    document: dict[str, Any], payload: bytearray, component: str
) -> dict[str, Any]:
    mesh_skins: dict[int, set[int]] = defaultdict(set)
    for node in document.get("nodes", []):
        if "mesh" in node and "skin" in node:
            mesh_skins[int(node["mesh"])].add(int(node["skin"]))
    rows: list[dict[str, Any]] = []
    total_invalid = total_repaired = total_nonzero = 0
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        skins = sorted(mesh_skins.get(mesh_index, set()))
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            attributes = primitive.get("attributes", {})
            joints_index = attributes.get("JOINTS_0")
            weights_index = attributes.get("WEIGHTS_0")
            if joints_index is None:
                continue
            if len(skins) != 1:
                rows.append(
                    {
                        "mesh": mesh_index,
                        "primitive": primitive_index,
                        "status": "unbound_or_ambiguous_skin",
                        "skins": skins,
                    }
                )
                continue
            if weights_index is None:
                raise CharacterAssetError(f"mesh {mesh_index}: JOINTS_0 lacks WEIGHTS_0")
            skin_index = skins[0]
            joint_limit = len(document["skins"][skin_index]["joints"])
            joint_accessor, _, _, joint_code, joint_width = _accessor_layout(
                document, int(joints_index)
            )
            if joint_width != 4:
                raise CharacterAssetError(f"mesh {mesh_index}: JOINTS_0 is not VEC4")
            weight_accessor = document["accessors"][int(weights_index)]
            if int(weight_accessor["count"]) != int(joint_accessor["count"]):
                raise CharacterAssetError(f"mesh {mesh_index}: joint/weight count mismatch")
            invalid = repaired = nonzero = 0
            samples: list[dict[str, Any]] = []
            for vertex in range(int(joint_accessor["count"])):
                joints, joint_offset, _ = _read_element(
                    payload, document, int(joints_index), vertex
                )
                weights, _, _ = _read_element(
                    payload, document, int(weights_index), vertex
                )
                changed = False
                for lane, joint in enumerate(joints):
                    if 0 <= int(joint) < joint_limit:
                        continue
                    invalid += 1
                    if abs(float(weights[lane])) <= 1e-8:
                        joints[lane] = 0
                        repaired += 1
                        changed = True
                    else:
                        nonzero += 1
                        if len(samples) < 8:
                            samples.append(
                                {
                                    "vertex": vertex,
                                    "lane": lane,
                                    "joint": int(joint),
                                    "weight": float(weights[lane]),
                                }
                            )
                if changed:
                    struct.pack_into("<" + joint_code * 4, payload, joint_offset, *joints)
            rows.append(
                {
                    "mesh": mesh_index,
                    "primitive": primitive_index,
                    "skin": skin_index,
                    "joint_limit": joint_limit,
                    "invalid_joint_lanes": invalid,
                    "zero_weight_sentinels_repaired": repaired,
                    "invalid_nonzero_weight_lanes": nonzero,
                    "nonzero_samples": samples,
                    "status": "passed" if nonzero == 0 else "failed",
                }
            )
            total_invalid += invalid
            total_repaired += repaired
            total_nonzero += nonzero
    return {
        "component": component,
        "policy": (
            "Out-of-range JOINTS_0 lanes are rewritten to joint 0 only when "
            "their paired weight is zero."
        ),
        "invalid_joint_lanes": total_invalid,
        "zero_weight_sentinels_repaired": total_repaired,
        "invalid_nonzero_weight_lanes": total_nonzero,
        "primitives": rows,
        "passed": total_nonzero == 0,
    }


def _local_uri(root: Path, uri: str, kind: str) -> Path:
    decoded = unquote(uri)
    if not decoded or decoded.startswith("data:") or "://" in decoded:
        raise CharacterAssetError(f"unsupported {kind} URI: {uri!r}")
    candidate = (root / Path(decoded)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise CharacterAssetError(f"{kind} URI leaves component directory: {uri}") from exc
    return candidate


def _node_has_identity_transform(node: Mapping[str, Any]) -> bool:
    matrix = node.get("matrix")
    if matrix is not None:
        return len(matrix) == 16 and all(
            abs(float(value) - expected) <= 1e-7
            for value, expected in zip(
                matrix,
                (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
                strict=True,
            )
        )
    translation = node.get("translation", (0, 0, 0))
    rotation = node.get("rotation", (0, 0, 0, 1))
    scale = node.get("scale", (1, 1, 1))
    return (
        list(translation) == [0, 0, 0]
        and list(rotation) == [0, 0, 0, 1]
        and list(scale) == [1, 1, 1]
    )


def _validate_gltf(component_dir: Path, label: str) -> dict[str, Any]:
    """Perform a no-Blender structural/readback validation of the final glTF."""

    Image = _pillow()
    np = _numpy()
    gltf_path = component_dir / f"{label}.gltf"
    document = json.loads(gltf_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if document.get("asset", {}).get("version") != "2.0":
        errors.append("asset.version is not 2.0")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or "uri" not in buffers[0]:
        errors.append("expected one external glTF buffer")
        payload = bytearray()
        bin_path = component_dir / f"{label}.bin"
    else:
        try:
            bin_path = _local_uri(component_dir, str(buffers[0]["uri"]), "buffer")
            payload = bytearray(bin_path.read_bytes())
            if int(buffers[0].get("byteLength", -1)) != len(payload):
                errors.append("declared and actual buffer sizes differ")
        except (OSError, CharacterAssetError) as exc:
            errors.append(str(exc))
            payload = bytearray()
            bin_path = component_dir / f"{label}.bin"

    for view_index, view in enumerate(document.get("bufferViews", [])):
        offset = int(view.get("byteOffset", 0))
        length = int(view.get("byteLength", 0))
        if int(view.get("buffer", -1)) != 0 or offset < 0 or length < 0 or offset + length > len(payload):
            errors.append(f"bufferView {view_index} is out of range")

    position_rows: list[dict[str, Any]] = []
    vertex_total = 0
    mesh_nodes = {
        int(node["mesh"]): index
        for index, node in enumerate(document.get("nodes", []))
        if "mesh" in node
    }
    nonidentity_mesh_nodes = [
        node_index
        for mesh_index, node_index in mesh_nodes.items()
        if mesh_index < len(document.get("meshes", []))
        and not _node_has_identity_transform(document["nodes"][node_index])
    ]
    if nonidentity_mesh_nodes:
        errors.append(f"mesh nodes have non-identity transforms: {nonidentity_mesh_nodes}")
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            attributes = primitive.get("attributes", {})
            position_index = attributes.get("POSITION")
            if not isinstance(position_index, int):
                errors.append(f"mesh {mesh_index}/{primitive_index} has no POSITION")
                continue
            try:
                accessor = document["accessors"][position_index]
                valid_layout = (
                    accessor.get("type") == "VEC3"
                    and int(accessor.get("componentType", -1)) == 5126
                )
                values = _accessor_array(document, payload, position_index)
                finite = bool(np.isfinite(values).all()) if valid_layout else False
            except (IndexError, KeyError, ValueError, CharacterAssetError) as exc:
                valid_layout = finite = False
                errors.append(f"position accessor {position_index}: {exc}")
                accessor = {"count": 0, "type": None, "componentType": None}
            if not valid_layout or not finite:
                errors.append(f"mesh {mesh_index}/{primitive_index} POSITION is not finite FLOAT VEC3")
            count = int(accessor.get("count", 0))
            vertex_total += count
            position_rows.append(
                {
                    "mesh": mesh_index,
                    "primitive": primitive_index,
                    "accessor": position_index,
                    "count": count,
                    "type": accessor.get("type"),
                    "component_type": accessor.get("componentType"),
                    "finite": finite,
                }
            )

    image_rows: list[dict[str, Any]] = []
    for index, image in enumerate(document.get("images", [])):
        uri = image.get("uri")
        row: dict[str, Any] = {"image": index, "uri": uri, "passed": False}
        if not isinstance(uri, str):
            errors.append(f"image {index} has no external URI")
        else:
            try:
                path = _local_uri(component_dir, uri, "image")
                with Image.open(path) as decoded:
                    decoded.verify()
                row.update({"passed": True, "bytes": path.stat().st_size})
            except (OSError, CharacterAssetError) as exc:
                errors.append(f"image {index}: {exc}")
        image_rows.append(row)
    for index, texture in enumerate(document.get("textures", [])):
        source = texture.get("source")
        if not isinstance(source, int) or not 0 <= source < len(image_rows):
            errors.append(f"texture {index} source is out of range")
    for index, material in enumerate(document.get("materials", [])):
        if material.get("alphaMode", "OPAQUE") not in ("OPAQUE", "MASK", "BLEND"):
            errors.append(f"material {index} has invalid alphaMode")

    # Re-read bound JOINTS/WEIGHTS after the sentinel repair.  Unbound preview
    # primitives remain nonfatal because glTF does not evaluate their joints.
    joint_errors = 0
    mesh_skins: dict[int, set[int]] = defaultdict(set)
    for node in document.get("nodes", []):
        if "mesh" in node and "skin" in node:
            mesh_skins[int(node["mesh"])].add(int(node["skin"]))
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        skins = mesh_skins.get(mesh_index, set())
        if len(skins) != 1:
            continue
        skin_index = next(iter(skins))
        if not 0 <= skin_index < len(document.get("skins", [])):
            errors.append(f"mesh {mesh_index} uses invalid skin {skin_index}")
            continue
        limit = len(document["skins"][skin_index].get("joints", []))
        for primitive in mesh.get("primitives", []):
            joints_index = primitive.get("attributes", {}).get("JOINTS_0")
            weights_index = primitive.get("attributes", {}).get("WEIGHTS_0")
            if joints_index is None:
                continue
            if weights_index is None:
                errors.append(f"mesh {mesh_index} has JOINTS_0 without WEIGHTS_0")
                continue
            joints = _accessor_array(document, payload, int(joints_index))
            weights = _accessor_array(document, payload, int(weights_index)).astype("float64")
            invalid = (joints >= limit) & (np.abs(weights) > 1e-8)
            joint_errors += int(invalid.sum())
    if joint_errors:
        errors.append(f"{joint_errors} nonzero-weight joint lanes exceed skin bounds")

    report = {
        "component": label,
        "gltf": gltf_path.name,
        "bin": bin_path.name,
        "mesh_count": len(document.get("meshes", [])),
        "active_mesh_nodes": len(mesh_nodes),
        "material_count": len(document.get("materials", [])),
        "skin_count": len(document.get("skins", [])),
        "image_count": len(image_rows),
        "vertices": vertex_total,
        "position_accessors": position_rows,
        "position_accessors_all_vec3_finite": all(
            row["type"] == "VEC3"
            and row["component_type"] == 5126
            and row["finite"]
            for row in position_rows
        ),
        "buffer_declared_bytes": int(buffers[0].get("byteLength", -1)) if buffers else -1,
        "buffer_actual_bytes": len(payload),
        "images": image_rows,
        "joint_nonzero_out_of_range": joint_errors,
        "errors": errors,
        "passed": not errors,
    }
    _json_write(component_dir / "gltf_validation.json", report)
    if errors:
        raise CharacterAssetError(f"{label}: final glTF validation failed: {errors[:8]}")
    return report


def _normalize_paths(values: Sequence[Path] | Path | str | None) -> tuple[Path, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, Path)):
        values = (Path(values),)
    result: list[Path] = []
    for value in values:
        path = Path(value).expanduser().resolve()
        if path not in result:
            result.append(path)
    return tuple(result)


def _auto_material_profile(spec: ComponentSpec) -> str:
    if spec.material_profile != "auto":
        return spec.material_profile
    if spec.role == "face":
        return "face_v1"
    if spec.role == "hair":
        return "hair_v1"
    return "standard"


def _resume_component(component_dir: Path, label: str) -> dict[str, Any] | None:
    manifest_path = component_dir / "component_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    final_gltf = component_dir / f"{label}.gltf"
    final_bin = component_dir / f"{label}.bin"
    validation_path = component_dir / "gltf_validation.json"
    if not final_gltf.is_file() or not final_bin.is_file() or not validation_path.is_file():
        return None
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not manifest.get("passed") or not validation.get("passed"):
        return None
    return {
        "final_gltf": str(final_gltf.resolve()),
        "final_bin": str(final_bin.resolve()),
        "manifest": str(manifest_path.resolve()),
        "material_mapping": str((component_dir / "material_mapping.json").resolve()),
        "validation": str(validation_path.resolve()),
        "resumed": True,
    }


def _finalize_joint_sentinels(component_dir: Path, label: str) -> dict[str, Any]:
    gltf_path = component_dir / f"{label}.gltf"
    document = json.loads(gltf_path.read_text(encoding="utf-8"))
    if len(document.get("buffers", [])) != 1:
        raise CharacterAssetError(f"{label}: expected one external buffer")
    bin_path = _local_uri(component_dir, str(document["buffers"][0]["uri"]), "buffer")
    payload = bytearray(bin_path.read_bytes())
    report = _repair_joint_sentinels(document, payload, label)
    _json_write(component_dir / "skin_validation.json", report)
    if not report["passed"]:
        raise CharacterAssetError(
            f"{label}: nonzero-weight joint lanes exceed skin bounds; "
            "see skin_validation.json"
        )
    bin_path.write_bytes(payload)
    document["buffers"][0]["byteLength"] = len(payload)
    document["buffers"][0]["uri"] = f"{label}.bin"
    canonical_bin = component_dir / f"{label}.bin"
    if bin_path != canonical_bin:
        shutil.copy2(bin_path, canonical_bin)
    _json_write(gltf_path, document)
    return report


def extract_character_assets(
    game: Path,
    output: Path,
    gust_dir: Path,
    components: Sequence[ComponentSpec | Mapping[str, Any]],
    *,
    character: str = "character",
    converter_deps: Sequence[Path] | Path | str | None = (),
    python_deps: Sequence[Path] | Path | str | None = (),
    resume: bool = False,
    fast_cloth: bool = True,
) -> dict[str, dict[str, Any]]:
    """Extract, decode, convert and validate all requested native components."""

    output = Path(output).expanduser().resolve()
    gust_dir = Path(gust_dir).expanduser().resolve()
    converter_paths = _normalize_paths(converter_deps)
    python_paths = _normalize_paths(python_deps)
    all_dependency_paths = _normalize_paths((*python_paths, *converter_paths))
    _add_dependency_paths(all_dependency_paths)
    specs = [
        item
        if isinstance(item, ComponentSpec)
        else ComponentSpec.from_dict(str(item.get("role", "component")), item)
        for item in components
    ]
    if not specs:
        raise CharacterAssetError("no components were requested")
    roles = [spec.role for spec in specs]
    if len(set(roles)) != len(roles):
        raise CharacterAssetError(f"duplicate component roles: {roles}")
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, Any]] = {}
    pending: list[ComponentSpec] = []
    for spec in specs:
        component_dir = output / spec.role
        resumed = _resume_component(component_dir, spec.label) if resume else None
        if resumed is not None:
            result[spec.role] = resumed
        else:
            pending.append(spec)
    if not pending:
        _json_write(
            output / "extraction_summary.json",
            {
                "character": character,
                "components": result,
                "resumed": True,
                "passed": True,
            },
        )
        return result

    data_root = data_root_from_game(Path(game))
    entries = scan_assets(data_root)
    by_file_id: dict[int, list[AssetEntry]] = defaultdict(list)
    for entry in entries:
        by_file_id[entry.file_id].append(entry)
    g1m_entries = [entry for entry in entries if entry.type_id == G1M_TYPE]
    g1m_indices = {
        entry.file_id: index for index, entry in enumerate(g1m_entries, start=1)
    }

    states: list[dict[str, Any]] = []
    all_handles: set[int] = set()
    for spec in pending:
        resources, actual_index = _resolve_component_bundle(
            spec, entries, by_file_id, g1m_indices
        )
        component_dir = output / spec.role
        component_dir.mkdir(parents=True, exist_ok=True)
        resource_rows: dict[str, Any] = {}
        for extension, entry in resources.items():
            path = component_dir / f"{spec.label}.{extension}"
            payload = read_asset(entry)
            path.write_bytes(payload)
            resource_rows[extension] = {
                **entry.as_dict(),
                "output": path.name,
                "decoded_size": len(payload),
                "sha256": _sha256(path),
            }
        pairs = _parse_ktid(
            (component_dir / f"{spec.label}.ktid").read_bytes()
        )
        if spec.texture_slots is not None and len(pairs) != spec.texture_slots:
            raise CharacterAssetError(
                f"{spec.label}: expected {spec.texture_slots} KTID slots, got {len(pairs)}"
            )
        all_handles.update(handle for _slot, handle in pairs)
        states.append(
            {
                "spec": spec,
                "dir": component_dir,
                "resources": resource_rows,
                "pairs": pairs,
                "model_index": actual_index,
            }
        )

    handle_to_g1t, handle_sources, objdb_stats = _resolve_texture_handles(
        entries, all_handles
    )
    g1t_entries: dict[int, list[AssetEntry]] = defaultdict(list)
    for entry in entries:
        if entry.type_id == G1T_TYPE:
            g1t_entries[entry.file_id].append(entry)

    for state in states:
        spec: ComponentSpec = state["spec"]
        component_dir: Path = state["dir"]
        texture_dir = component_dir / "textures"
        texture_dir.mkdir(exist_ok=True)
        texture_rows: list[dict[str, Any]] = []
        texture_bytes = 0
        for slot, handle in state["pairs"]:
            g1t_id = handle_to_g1t[handle]
            matches = g1t_entries.get(g1t_id, [])
            if len(matches) != 1:
                raise CharacterAssetError(
                    f"{spec.label} slot {slot}: G1T {_hex(g1t_id)} has "
                    f"{len(matches)} entries"
                )
            entry = matches[0]
            stem = f"slot_{slot:03d}_handle-{handle:08x}_g1t-{g1t_id:08x}"
            g1t_path = texture_dir / f"{stem}.g1t"
            payload = read_asset(entry)
            g1t_path.write_bytes(payload)
            texture_bytes += len(payload)
            conversion = _convert_g1t(g1t_path)
            texture_rows.append(
                {
                    "slot": slot,
                    "handle": _hex(handle),
                    "g1t_id": _hex(g1t_id),
                    "source": entry.as_dict(),
                    "objdb_sources": handle_sources[handle],
                    "files": {
                        "g1t": g1t_path.relative_to(component_dir).as_posix(),
                        "dds": g1t_path.with_suffix(".dds").relative_to(component_dir).as_posix(),
                        "png": g1t_path.with_suffix(".png").relative_to(component_dir).as_posix(),
                    },
                    "conversion": conversion,
                }
            )
        _json_write(component_dir / "texture_mapping.json", texture_rows)

        g1m_path = component_dir / f"{spec.label}.g1m"
        conversion_result = convert_g1m(
            g1m_path,
            gust_dir=gust_dir,
            dependency_paths=converter_paths,
            output_stem=component_dir / spec.label,
            oid_path=component_dir / f"{spec.label}.oid",
            fast_cloth=fast_cloth,
        )
        material_profile = _auto_material_profile(spec)
        material_report = _patch_gltf_materials(
            component_dir,
            spec.label,
            spec.role,
            material_profile,
            texture_rows,
        )
        skin_report = _finalize_joint_sentinels(component_dir, spec.label)
        postprocess: dict[str, Any] | None = None
        post_kind = str(spec.postprocess.get("kind") or "").lower()
        if material_profile in ("nanami_body722", "nanami_trad_dry_static"):
            post_kind = "nanami_body722"
        if post_kind == "nanami_body722":
            postprocess = _apply_nanami_body722(
                component_dir,
                spec.label,
                g1m_path,
                gust_dir,
                all_dependency_paths,
                spec.postprocess,
            )
        elif post_kind:
            raise CharacterAssetError(
                f"{spec.label}: unsupported postprocess kind {post_kind!r}"
            )
        validation = _validate_gltf(component_dir, spec.label)
        final_gltf = component_dir / f"{spec.label}.gltf"
        final_bin = component_dir / f"{spec.label}.bin"
        manifest = {
            "character": character,
            "role": spec.role,
            "component": spec.label,
            "model_index": state["model_index"],
            "material_profile": material_profile,
            "resources": state["resources"],
            "ktid_slot_count": len(state["pairs"]),
            "resolved_texture_count": len(texture_rows),
            "all_handles_resolved_uniquely": True,
            "all_pngs_created": all(
                (component_dir / row["files"]["png"]).is_file()
                for row in texture_rows
            ),
            "total_extracted_texture_bytes": texture_bytes,
            "conversion": conversion_result.as_dict(),
            "material_mapping": "material_mapping.json",
            "skin_validation": "skin_validation.json",
            "postprocess": postprocess,
            "gltf_validation": "gltf_validation.json",
            "final_gltf": final_gltf.name,
            "final_bin": final_bin.name,
            "final_sha256": {
                final_gltf.name: _sha256(final_gltf),
                final_bin.name: _sha256(final_bin),
            },
            "passed": bool(
                validation["passed"]
                and skin_report["passed"]
                and len(texture_rows) == len(state["pairs"])
            ),
        }
        manifest_path = component_dir / "component_manifest.json"
        _json_write(manifest_path, manifest)
        result[spec.role] = {
            "final_gltf": str(final_gltf.resolve()),
            "final_bin": str(final_bin.resolve()),
            "manifest": str(manifest_path.resolve()),
            "material_mapping": str((component_dir / "material_mapping.json").resolve()),
            "validation": str((component_dir / "gltf_validation.json").resolve()),
            "resumed": False,
        }

    summary = {
        "character": character,
        "game_data": str(data_root),
        **objdb_stats,
        "unique_texture_handles_processed": len(all_handles),
        "components": result,
        "passed": all(
            json.loads(Path(row["manifest"]).read_text(encoding="utf-8")).get("passed")
            for row in result.values()
        ),
    }
    _json_write(output / "extraction_summary.json", summary)
    return result


def _plain_value(value: Any) -> Any:
    """Recursively serialize dataclasses without deepcopying MappingProxyType."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _plain_value(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _normalized_body_postprocess(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _plain_value(value)
    profile_name = str(raw.get("profile") or raw.get("kind") or "").lower()
    if profile_name not in ("nanami_trad_dry_static", "nanami_body722"):
        return {}
    result: dict[str, Any] = {"kind": "nanami_body722"}
    aliases = {
        "active_conditional_mesh_indices": "active_dry_meshes",
        "common_required_mesh_indices": "common_meshes",
        "excluded_runtime_dt2_mesh_indices": "hidden_dt2_meshes",
        "slot22_overlay_factor": "overlay_strength",
        "normal_slot": "normal_slot",
        "normal_strength": "normal_strength",
    }
    for source, target in aliases.items():
        if source in raw:
            result[target] = raw[source]
    base_slots = raw.get("base_color_slots")
    if isinstance(base_slots, Sequence) and not isinstance(base_slots, str) and len(base_slots) >= 2:
        result["base_slot"] = int(base_slots[0])
        result["overlay_slot"] = int(base_slots[1])
    # Expert callers may override any of the reviewed fields directly.
    for key in NANAMI_BODY722_DEFAULTS:
        if key in raw:
            result[key] = raw[key]
    return result


def _profile_to_specs(profile: Any) -> tuple[str, list[ComponentSpec]]:
    if isinstance(profile, (str, Path)):
        return load_profile(Path(profile))
    if isinstance(profile, Mapping):
        character = str(
            profile.get("name_en")
            or profile.get("character")
            or profile.get("name")
            or profile.get("key")
            or "character"
        )
        components = profile.get("components")
        if not isinstance(components, Mapping):
            raise CharacterAssetError("profile.components must be a mapping")
        specs: list[ComponentSpec] = []
        body_policy = profile.get("body_postprocess")
        for role, component in components.items():
            raw_component = _plain_value(component)
            if not isinstance(raw_component, Mapping):
                raise CharacterAssetError(f"{role}: component must be a mapping")
            raw_component = dict(raw_component)
            if not raw_component.get("resources") and all(
                key in raw_component for key in RESOURCE_TYPES
            ):
                raw_component["resources"] = {
                    key: raw_component[key] for key in RESOURCE_TYPES
                }
            if not raw_component.get("package") and raw_component.get("package_id") is not None:
                raw_component["package"] = f"0x{int(raw_component['package_id']):08x}.fdata"
            role_name = str(role).lower()
            raw_component.setdefault(
                "material_profile",
                "face_v1"
                if role_name == "face"
                else "hair_v1"
                if role_name == "hair"
                else "standard",
            )
            if role_name == "body" and isinstance(body_policy, Mapping):
                raw_component.setdefault(
                    "postprocess", _normalized_body_postprocess(body_policy)
                )
            specs.append(ComponentSpec.from_dict(role_name, raw_component))
        return character, specs

    components = getattr(profile, "components", None)
    if not isinstance(components, Mapping):
        raise CharacterAssetError(
            "profile must be a JSON path, mapping, or CharacterProfile-like object"
        )
    character = str(
        getattr(profile, "name_en", None)
        or getattr(profile, "name", None)
        or getattr(profile, "key", None)
        or "character"
    )
    specs: list[ComponentSpec] = []
    for role_raw, component in components.items():
        role = str(role_raw).lower()
        resources = {
            extension: int(getattr(component, extension))
            for extension in RESOURCE_TYPES
            if hasattr(component, extension)
        }
        if len(resources) != len(RESOURCE_TYPES):
            raw_component = _plain_value(component)
            resources = {
                key: int(value)
                for key, value in dict(
                    raw_component.get("resources")
                    or raw_component.get("resource_ids")
                    or {}
                ).items()
            }
        label = str(getattr(component, "label", "")).upper()
        if not label:
            raise CharacterAssetError(f"{role}: component label is missing")
        package = getattr(component, "package_name", None)
        if callable(package):
            package = package()
        if package is None and hasattr(component, "package_id"):
            package = f"0x{int(component.package_id):08x}.fdata"
        postprocess: dict[str, Any] = {}
        if role == "body":
            raw_body = getattr(profile, "body_postprocess", {})
            if isinstance(raw_body, Mapping):
                postprocess = _normalized_body_postprocess(raw_body)
        material_profile = (
            "face_v1"
            if role == "face"
            else "hair_v1"
            if role == "hair"
            else "standard"
        )
        specs.append(
            ComponentSpec(
                role=role,
                label=label,
                model_index=int(getattr(component, "model_index", 0)),
                internal_name=(
                    str(component.internal_name).upper()
                    if getattr(component, "internal_name", None)
                    else None
                ),
                g1m_id=resources.get("g1m"),
                package=str(package) if package else None,
                texture_slots=(
                    int(component.texture_slots)
                    if getattr(component, "texture_slots", None) is not None
                    else None
                ),
                resources=resources,
                material_profile=material_profile,
                postprocess=postprocess,
            )
        )
    return character, specs


def export_profile_assets(
    profile: Any,
    game: Path,
    output: Path,
    gust_dir: Path,
    converter_deps: Sequence[Path] | Path | str | None = (),
    python_deps: Sequence[Path] | Path | str | None = (),
    resume: bool = False,
) -> dict[str, dict[str, Any]]:
    """Export one CharacterProfile and return role -> final glTF/manifest paths.

    This intentionally reads dataclass attributes recursively instead of using
    :func:`dataclasses.asdict`, because the reviewed profile registry contains
    nested ``MappingProxyType`` values which cannot be deep-copied/pickled.
    """

    character, specs = _profile_to_specs(profile)
    return extract_character_assets(
        game=game,
        output=output,
        gust_dir=gust_dir,
        components=specs,
        character=character,
        converter_deps=converter_deps,
        python_deps=python_deps,
        resume=resume,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gust-dir", required=True, type=Path)
    parser.add_argument("--profile", type=Path, help="Character profile JSON")
    parser.add_argument(
        "--character",
        help="Name/code from character_profiles.py (for example Honoka or Nanami)",
    )
    parser.add_argument(
        "--component",
        action="append",
        type=_parse_component,
        default=[],
        help="ROLE:LABEL:INDEX[:G1M_ID[:MATERIAL_PROFILE]] (repeatable)",
    )
    parser.add_argument(
        "--converter-deps", action="append", type=Path, default=[]
    )
    parser.add_argument("--python-deps", action="append", type=Path, default=[])
    parser.add_argument(
        "--deps",
        action="append",
        type=Path,
        default=[],
        help="Compatibility dependency path used for both converter and images",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-fast-cloth", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    selected = sum(bool(item) for item in (args.profile, args.character, args.component))
    if selected != 1:
        raise SystemExit(
            "error: choose exactly one of --profile, --character, or --component"
        )
    converter_deps = (*args.converter_deps, *args.deps)
    python_deps = (*args.python_deps, *args.deps)
    try:
        if args.character:
            profiles = importlib.import_module("character_profiles")
            profile: Any = profiles.get_character_profile(args.character)
            results = export_profile_assets(
                profile,
                args.game,
                args.output,
                args.gust_dir,
                converter_deps,
                python_deps,
                args.resume,
            )
        elif args.profile:
            character, specs = load_profile(args.profile)
            results = extract_character_assets(
                args.game,
                args.output,
                args.gust_dir,
                specs,
                character=character,
                converter_deps=converter_deps,
                python_deps=python_deps,
                resume=args.resume,
                fast_cloth=not args.no_fast_cloth,
            )
        else:
            results = extract_character_assets(
                args.game,
                args.output,
                args.gust_dir,
                args.component,
                character="custom",
                converter_deps=converter_deps,
                python_deps=python_deps,
                resume=args.resume,
                fast_cloth=not args.no_fast_cloth,
            )
    except (OSError, PrismArchiveError, G1MConversionError, CharacterAssetError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
