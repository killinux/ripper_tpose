#!/usr/bin/env python3
"""Shared readers for X-Legend's optimized Gamebryo 20.3.3.2 files.

The game keeps the normal Gamebryo block payloads but replaces parts of the
header: strings are delta-XOR encoded, block types are 32-bit hashes, type
indices are bytes, and block sizes are unsigned 24-bit integers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import re
import struct


SUPPORTED_VERSION = 0x14030302
GEOMETRY_HASH = 0xAD79E131
NODE_HASH = 0xBD8B18FD
SHAPE_HASH = 0xCA51C7F7
SKIN_INSTANCE_HASH = 0x74F8CE41
SKIN_DATA_HASH = 0xC50D2246
SKIN_PARTITION_HASH = 0xF7BBCAC6
TEXTURE_PROPERTY_HASH = 0x742E2A66
TEXTURE_SOURCE_HASH = 0x3B0EDD59


@dataclass(frozen=True)
class Block:
    index: int
    type_index: int
    type_hash: int
    offset: int
    size: int


@dataclass(frozen=True)
class NifFile:
    version: int
    user_version: int
    strings: tuple[str, ...]
    type_hashes: tuple[int, ...]
    blocks: tuple[Block, ...]
    footer_size: int


def decode_delta_xor(value: bytes) -> bytes:
    """Decode X-Legend's bytewise ``plain[i] ^ plain[i - 1]`` strings."""

    output = bytearray()
    previous = 0
    for encoded in value:
        decoded = encoded ^ previous
        output.append(decoded)
        previous = decoded
    return bytes(output)


def read_u24(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 3 > len(data):
        raise ValueError("truncated uint24")
    return int.from_bytes(data[offset : offset + 3], "little"), offset + 3


def parse_nif(data: bytes) -> NifFile:
    if not data.startswith(b"Gamebryo File Format\n"):
        raise ValueError("not a Gamebryo NIF/KF file")
    offset = data.index(b"\n") + 1
    version, = struct.unpack_from("<I", data, offset)
    offset += 4
    if version != SUPPORTED_VERSION:
        raise ValueError(f"unsupported NIF version: 0x{version:08x}")

    endian = data[offset]
    offset += 1
    if endian != 1:
        raise ValueError("only little-endian X-Legend files are supported")

    user_version, block_count, string_count = struct.unpack_from("<III", data, offset)
    offset += 12
    _max_string_length, = struct.unpack_from("<H", data, offset)
    offset += 2

    strings = []
    for _ in range(string_count):
        length, = struct.unpack_from("<H", data, offset)
        offset += 2
        encoded = data[offset : offset + length]
        if len(encoded) != length:
            raise ValueError("truncated X-Legend string table")
        offset += length
        strings.append(decode_delta_xor(encoded).decode("utf-8", errors="replace"))

    type_count, = struct.unpack_from("<H", data, offset)
    offset += 2
    type_hashes = struct.unpack_from(f"<{type_count}I", data, offset)
    offset += 4 * type_count
    if type_count > 0xFF:
        raise ValueError("two-byte X-Legend type indices are not implemented")

    type_indices = data[offset : offset + block_count]
    if len(type_indices) != block_count:
        raise ValueError("truncated block type table")
    offset += block_count

    sizes = []
    for _ in range(block_count):
        size, offset = read_u24(data, offset)
        sizes.append(size)

    blocks = []
    block_offset = offset
    for index, (type_index, size) in enumerate(zip(type_indices, sizes)):
        if type_index >= len(type_hashes):
            raise ValueError(f"invalid type index {type_index} on block {index}")
        blocks.append(
            Block(index, type_index, type_hashes[type_index], block_offset, size)
        )
        block_offset += size
    if block_offset > len(data):
        raise ValueError("block table extends beyond the file")

    return NifFile(
        version=version,
        user_version=user_version,
        strings=tuple(strings),
        type_hashes=tuple(type_hashes),
        blocks=tuple(blocks),
        footer_size=len(data) - block_offset,
    )


def string_at(nif: NifFile, index: int) -> str | None:
    return nif.strings[index] if 0 <= index < len(nif.strings) else None


def parse_geometry(data: bytes, block: Block) -> dict:
    """Read an X-Legend NiTriShapeData-compatible block."""

    # The stored size is two bytes short for blocks which end in the encoded
    # triangle stream.  The following block/footer provides the look-ahead.
    payload = data[block.offset : block.offset + block.size + 2]
    _scale, group_id = struct.unpack_from("<fI", payload, 0)
    vertex_count, keep_flags, compress_flags, has_vertices = struct.unpack_from(
        "<HBBB", payload, 8
    )
    cursor = 13
    if not has_vertices or not vertex_count:
        raise ValueError(f"geometry block {block.index} has no vertices")

    vertices = list(
        struct.iter_unpack("<3f", payload[cursor : cursor + 12 * vertex_count])
    )
    cursor += 12 * vertex_count
    data_flags, has_normals = struct.unpack_from("<HB", payload, cursor)
    cursor += 3
    normals = None
    if has_normals:
        normals = list(
            struct.iter_unpack("<3f", payload[cursor : cursor + 12 * vertex_count])
        )
        cursor += 12 * vertex_count
        if data_flags & 0x3000:
            cursor += 24 * vertex_count

    center = struct.unpack_from("<3f", payload, cursor)
    radius, = struct.unpack_from("<f", payload, cursor + 12)
    cursor += 16
    has_colors = payload[cursor]
    cursor += 1
    if has_colors:
        cursor += 16 * vertex_count

    uv_set_count = data_flags & 0x3F
    uv_sets = []
    for _ in range(uv_set_count):
        uv_sets.append(
            list(struct.iter_unpack("<2f", payload[cursor : cursor + 8 * vertex_count]))
        )
        cursor += 8 * vertex_count

    consistency_flags, = struct.unpack_from("<H", payload, cursor)
    cursor += 2
    additional_data_ref, = struct.unpack_from("<i", payload, cursor)
    cursor += 4
    triangle_count, triangle_point_count, has_triangles = struct.unpack_from(
        "<HIB", payload, cursor
    )
    cursor += 7
    if triangle_point_count != triangle_count * 3:
        raise ValueError(f"unexpected triangle point count on block {block.index}")

    faces = []
    if has_triangles:
        encoded = struct.unpack_from(f"<{triangle_point_count}H", payload, cursor)
        previous = 0
        decoded = []
        for value in encoded:
            previous ^= value
            decoded.append(previous)
        faces = [tuple(decoded[i : i + 3]) for i in range(0, len(decoded), 3)]
    if any(index >= vertex_count for face in faces for index in face):
        raise ValueError(f"triangle index exceeds vertices on block {block.index}")

    return {
        "block": block.index,
        "group_id": group_id,
        "keep_flags": keep_flags,
        "compress_flags": compress_flags,
        "data_flags": data_flags,
        "vertices": vertices,
        "normals": normals,
        "uv_sets": uv_sets,
        "faces": faces,
        "center": center,
        "radius": radius,
        "consistency_flags": consistency_flags,
        "additional_data_ref": additional_data_ref,
    }


def parse_av_object(data: bytes, nif: NifFile, block: Block) -> dict:
    """Read the common optimized NiAVObject prefix used by nodes and shapes."""

    payload = data[block.offset : block.offset + block.size]
    if len(payload) < 79:
        raise ValueError(f"AV object block {block.index} is too short")
    prefix_ref, = struct.unpack_from("<i", payload, 0)
    parsed = None
    errors = []
    # Two optimized layouts occur in the shipped files.  The h001 family uses
    # a 32-bit string index plus an 8-bit extra-data count; larger h005 bundles
    # use a 16-bit string index plus a 32-bit count.  Test both profiles and
    # reject impossible refs so the choice is driven by the payload.
    for name_index_width, extra_count_width in ((4, 1), (2, 4)):
        try:
            if name_index_width == 4:
                name_index, = struct.unpack_from("<I", payload, 4)
            else:
                name_index, = struct.unpack_from("<H", payload, 4)
            if name_index >= len(nif.strings):
                raise ValueError(f"invalid string index {name_index}")
            count_offset = 4 + name_index_width
            if extra_count_width == 1:
                extra_count = payload[count_offset]
            elif extra_count_width == 2:
                extra_count, = struct.unpack_from("<H", payload, count_offset)
            else:
                extra_count, = struct.unpack_from("<I", payload, count_offset)
            if extra_count > 64:
                raise ValueError(f"implausible extra-data count {extra_count}")
            cursor = count_offset + extra_count_width
            extra_refs = list(struct.unpack_from(f"<{extra_count}i", payload, cursor))
            cursor += extra_count * 4
            controller_ref, flags = struct.unpack_from("<iH", payload, cursor)
            cursor += 6
            translation = struct.unpack_from("<3f", payload, cursor)
            cursor += 12
            rotation = struct.unpack_from("<9f", payload, cursor)
            cursor += 36
            scale, = struct.unpack_from("<f", payload, cursor)
            cursor += 4
            property_count, = struct.unpack_from("<I", payload, cursor)
            cursor += 4
            if property_count > 128:
                raise ValueError(f"implausible property count {property_count}")
            property_refs = list(
                struct.unpack_from(f"<{property_count}i", payload, cursor)
            )
            cursor += property_count * 4
            collision_ref, = struct.unpack_from("<i", payload, cursor)
            cursor += 4
            references = extra_refs + property_refs + [controller_ref, collision_ref]
            if any(value < -1 or value >= len(nif.blocks) for value in references):
                raise ValueError("AV object contains an out-of-range block reference")
            if cursor > len(payload):
                raise ValueError("AV object common prefix exceeds its block")
            parsed = (
                name_index_width,
                extra_count_width,
                name_index,
                extra_refs,
                controller_ref,
                flags,
                translation,
                rotation,
                scale,
                property_refs,
                collision_ref,
                cursor,
            )
            break
        except (IndexError, struct.error, ValueError) as exc:
            errors.append(
                f"name-u{name_index_width * 8}/count-u{extra_count_width * 8}: {exc}"
            )
    if parsed is None:
        raise ValueError(
            f"cannot decode AV object block {block.index}: {'; '.join(errors)}"
        )
    (
        name_index_width,
        extra_count_width,
        name_index,
        extra_refs,
        controller_ref,
        flags,
        translation,
        rotation,
        scale,
        property_refs,
        collision_ref,
        cursor,
    ) = parsed
    return {
        "block": block.index,
        "prefix_ref": prefix_ref,
        "name_index": name_index,
        "name": string_at(nif, name_index) or f"block_{block.index:03d}",
        "extra_refs": extra_refs,
        "controller_ref": controller_ref,
        "flags": flags,
        "translation": translation,
        "rotation": rotation,
        "scale": scale,
        "property_refs": property_refs,
        "collision_ref": collision_ref,
        "name_index_width": name_index_width,
        "extra_count_width": extra_count_width,
        "cursor": cursor,
        "payload": payload,
    }


def parse_node(data: bytes, nif: NifFile, block: Block) -> dict:
    node = parse_av_object(data, nif, block)
    cursor = node.pop("cursor")
    payload = node.pop("payload")
    child_count, = struct.unpack_from("<I", payload, cursor)
    cursor += 4
    children = list(struct.unpack_from(f"<{child_count}i", payload, cursor))
    cursor += child_count * 4
    if cursor != len(payload):
        raise ValueError(
            f"node block {block.index} has {len(payload) - cursor} trailing bytes"
        )
    node["children"] = children
    return node


def parse_shape(data: bytes, nif: NifFile, block: Block) -> dict:
    shape = parse_av_object(data, nif, block)
    cursor = shape.pop("cursor")
    payload = shape.pop("payload")
    data_ref, skin_instance_ref = struct.unpack_from("<ii", payload, cursor)
    cursor += 8
    shape.update(
        {
            "data_ref": data_ref,
            "skin_instance_ref": skin_instance_ref,
            "tail_hex": payload[cursor:].hex(),
        }
    )
    return shape


def parse_texture_source(data: bytes, nif: NifFile, block: Block) -> dict:
    """Read an optimized NiSourceTexture-style block."""

    if block.type_hash != TEXTURE_SOURCE_HASH:
        raise ValueError(f"block {block.index} is not a texture source")
    payload = data[block.offset : block.offset + block.size]
    # X-Legend stores both ObjectNET names and the source filename with the
    # smallest index width that can address the file's string table.  h005 has
    # 749 strings (u16 indices), while h996 has only 117 (u8 indices).
    string_index_width = (
        1
        if len(nif.strings) <= 0xFF
        else 2
        if len(nif.strings) <= 0xFFFF
        else 4
    )
    string_offset = 13 + string_index_width
    if len(payload) < string_offset + string_index_width:
        raise ValueError(f"texture source block {block.index} is too short")
    string_index = int.from_bytes(
        payload[string_offset : string_offset + string_index_width], "little"
    )
    if string_index >= len(nif.strings):
        raise ValueError(
            f"texture source block {block.index} has invalid string {string_index}"
        )
    return {
        "block": block.index,
        "string_index": string_index,
        "string_index_width": string_index_width,
        "name": nif.strings[string_index],
    }


def shape_texture_names(data: bytes, nif: NifFile, shape: dict) -> list[str]:
    """Resolve a shape's texture property through its source-texture blocks."""

    result: list[str] = []
    seen_blocks: set[int] = set()
    for property_ref in shape["property_refs"]:
        if property_ref < 0:
            continue
        prop = nif.blocks[property_ref]
        if prop.type_hash != TEXTURE_PROPERTY_HASH:
            continue
        payload = data[prop.offset : prop.offset + prop.size]
        for offset in range(0, len(payload) - 3):
            source_ref, = struct.unpack_from("<i", payload, offset)
            if source_ref < 0 or source_ref >= len(nif.blocks):
                continue
            source = nif.blocks[source_ref]
            if source.type_hash != TEXTURE_SOURCE_HASH or source_ref in seen_blocks:
                continue
            # Some shipped NIFs (for example h996) keep placeholder
            # NiSourceTexture blocks whose filename index is 0xffff.  They are
            # not usable texture references and should not abort the import.
            try:
                texture = parse_texture_source(data, nif, source)
            except ValueError:
                seen_blocks.add(source_ref)
                continue
            if texture["name"].lower().endswith(".dds"):
                seen_blocks.add(source_ref)
                result.append(texture["name"])
    return result


def diffuse_texture_name(texture_names: list[str]) -> str | None:
    """Return the shape-local diffuse texture from a scanned property list.

    X-Legend texture-property payloads can contain an earlier shared texture
    reference before the texture set owned by the current shape.  The local
    diffuse is consequently the *last* non-utility DDS reference, not the
    first one.  This matters for h009/h091 (shared body/colour textures) and
    for h011, whose shapes all use generic 3ds Max object names.
    """

    return next(
        (
            value
            for value in reversed(texture_names)
            if not Path(value).stem.lower().endswith(
                ("_specular", "_gloss", "_normal", "_light")
            )
        ),
        None,
    )


def is_primary_character_shape(
    model_id: str, shape_name: str, texture_names: list[str]
) -> bool:
    """Identify the character body/face/hair shapes used for preview/FBX.

    Most files name these meshes ``hNNN_*``.  h011 instead retained generic
    DCC names, so its shape-local diffuse prefix is the reliable fallback.
    Optional ``he*`` equipment and duplicated facial helpers remain available
    in the Blend attachment collection without being stacked in the preview.
    """

    model_id = model_id.lower()
    lowered_name = shape_name.lower()
    # h999_b is intentionally cut away beneath its equipped meshes.  These
    # two shipped shapes supply its missing limbs/outfit and head accessory;
    # treating them as optional would leave the preview and FBX incomplete.
    required_equipment = {
        "h997": {"he50002"},
        "h999": {"he10000", "he50000"},
    }
    if lowered_name in required_equipment.get(model_id, set()):
        return True
    prefix = f"{model_id}_"
    if lowered_name.startswith(prefix):
        return True
    diffuse = diffuse_texture_name(texture_names)
    return bool(diffuse and Path(diffuse).stem.lower().startswith(prefix))


def parse_skin_instance(data: bytes, block: Block) -> dict:
    """Read the compact instance linking geometry, partitions, and bones."""

    payload = data[block.offset : block.offset + block.size]
    if len(payload) < 20:
        raise ValueError(f"skin instance block {block.index} is too short")
    overlap, data_ref, partition_ref, unknown, bone_count = struct.unpack_from(
        "<Iiiii", payload, 0
    )
    bone_refs = list(struct.unpack_from(f"<{bone_count}i", payload, 20))
    return {
        "block": block.index,
        "overlap": overlap,
        "data_ref": data_ref,
        "partition_ref": partition_ref,
        "unknown": unknown,
        "bone_refs": bone_refs,
    }


def parse_skin_data(data: bytes, block: Block) -> dict:
    """Read per-bone bind transforms and direct vertex weights."""

    payload = data[block.offset : block.offset + block.size + 2]
    cursor = 4  # four bytes overlap the preceding optimized block

    def read_transform() -> dict:
        nonlocal cursor
        rotation = struct.unpack_from("<9f", payload, cursor)
        cursor += 36
        translation = struct.unpack_from("<3f", payload, cursor)
        cursor += 12
        scale, = struct.unpack_from("<f", payload, cursor)
        cursor += 4
        return {"rotation": rotation, "translation": translation, "scale": scale}

    skin_transform = read_transform()
    bone_count, = struct.unpack_from("<I", payload, cursor)
    cursor += 4
    has_vertex_weights = bool(payload[cursor])
    cursor += 1
    bones = []
    for bone_index in range(bone_count):
        transform = read_transform()
        bound_center = struct.unpack_from("<3f", payload, cursor)
        bound_radius, = struct.unpack_from("<f", payload, cursor + 12)
        cursor += 16
        weight_count, = struct.unpack_from("<H", payload, cursor)
        cursor += 2
        weights = []
        for weight_index in range(weight_count):
            if cursor + 6 > len(payload):
                raise ValueError(
                    f"skin data block {block.index} ends in bone {bone_index}, "
                    f"weight {weight_index}/{weight_count}, cursor {cursor}, "
                    f"payload {len(payload)}"
                )
            vertex, weight = struct.unpack_from("<Hf", payload, cursor)
            cursor += 6
            weights.append((vertex, weight))
        bones.append(
            {
                "index": bone_index,
                "transform": transform,
                "bound_center": bound_center,
                "bound_radius": bound_radius,
                "weights": weights,
            }
        )
    return {
        "block": block.index,
        "skin_transform": skin_transform,
        "has_vertex_weights": has_vertex_weights,
        "bones": bones,
        "consumed": cursor,
        "size": len(payload),
    }


ANIMATION_PATH = re.compile(rb"(?:\.\\)?animation\\[A-Za-z0-9_.\\-]+\.kf", re.I)
MODEL_PATH = re.compile(rb"(?:\.\\)?model\\[A-Za-z0-9_.\\-]+\.nif", re.I)


def parse_kfm(data: bytes) -> dict:
    if not data.startswith((b";Gamebryo KFM File", b"Gamebryo KFM File")):
        raise ValueError("not a Gamebryo KFM file")
    animations = [item.decode("ascii") for item in ANIMATION_PATH.findall(data)]
    models = [item.decode("ascii") for item in MODEL_PATH.findall(data)]
    return {
        "models": models,
        "animation_count": len(animations),
        "animations": animations,
    }


def build_report(nif_path: Path, kfm_path: Path | None = None) -> dict:
    data = nif_path.read_bytes()
    nif = parse_nif(data)
    geometries = [
        parse_geometry(data, block)
        for block in nif.blocks
        if block.type_hash == GEOMETRY_HASH
    ]
    type_counts = Counter(block.type_hash for block in nif.blocks)
    report = {
        "nif": str(nif_path.resolve()),
        "version": ".".join(str(data[n]) for n in (24, 23, 22, 21)),
        "user_version": nif.user_version,
        "string_count": len(nif.strings),
        "strings": list(nif.strings),
        "block_count": len(nif.blocks),
        "footer_size": nif.footer_size,
        "type_hashes": [f"{value:08x}" for value in nif.type_hashes],
        "type_counts": {
            f"{value:08x}": type_counts[value] for value in nif.type_hashes
        },
        "geometry": [
            {
                "block": item["block"],
                "vertex_count": len(item["vertices"]),
                "triangle_count": len(item["faces"]),
                "uv_set_count": len(item["uv_sets"]),
                "radius": item["radius"],
            }
            for item in geometries
        ],
    }
    if kfm_path:
        report["kfm"] = parse_kfm(kfm_path.read_bytes())
        report["kfm"]["path"] = str(kfm_path.resolve())
    return report


def preview_block(data: bytes, nif: NifFile, block: Block) -> dict:
    head = data[block.offset : block.offset + min(32, block.size)]
    words = list(struct.unpack_from(f"<{len(head) // 4}I", head))
    return {
        "index": block.index,
        "type_index": block.type_index,
        "type_hash": f"{block.type_hash:08x}",
        "offset": block.offset,
        "size": block.size,
        "head_hex": head.hex(),
        "head_u32": words,
        "head_string_refs": [
            {"word": word_index, "index": value, "value": string_at(nif, value)}
            for word_index, value in enumerate(words)
            if string_at(nif, value) is not None
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nif", type=Path, required=True)
    parser.add_argument("--kfm", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dump-blocks", action="store_true")
    args = parser.parse_args()

    report = build_report(args.nif, args.kfm)
    if args.dump_blocks:
        data = args.nif.read_bytes()
        nif = parse_nif(data)
        report["blocks"] = [preview_block(data, nif, block) for block in nif.blocks]

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
