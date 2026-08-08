#!/usr/bin/env python3
"""Inspect X-Legend NIF shape properties and their DDS string references."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from xlegend_nif import (
    GEOMETRY_HASH,
    SHAPE_HASH,
    parse_geometry,
    parse_nif,
    parse_shape,
    shape_texture_names,
)


def scan_string_refs(payload: bytes, strings: tuple[str, ...]) -> list[dict]:
    dds_indices = {
        index: value for index, value in enumerate(strings) if value.lower().endswith(".dds")
    }
    matches: list[dict] = []
    for width, fmt in ((2, "<H"), (4, "<I")):
        for offset in range(0, len(payload) - width + 1):
            value, = struct.unpack_from(fmt, payload, offset)
            if value in dds_indices:
                matches.append(
                    {
                        "offset": offset,
                        "width": width,
                        "string_index": value,
                        "value": dds_indices[value],
                    }
                )
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nif", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = args.nif.read_bytes()
    nif = parse_nif(data)
    geometries = {
        block.index: parse_geometry(data, block)
        for block in nif.blocks
        if block.type_hash == GEOMETRY_HASH
    }
    shapes = []
    for block in nif.blocks:
        if block.type_hash != SHAPE_HASH:
            continue
        try:
            shape = parse_shape(data, nif, block)
        except ValueError:
            continue
        geometry = geometries.get(shape["data_ref"])
        if not geometry or len(geometry["vertices"]) <= 100:
            continue
        properties = []
        for reference in shape["property_refs"]:
            if reference < 0:
                continue
            prop = nif.blocks[reference]
            payload = data[prop.offset : prop.offset + prop.size]
            properties.append(
                {
                    "block": reference,
                    "type_hash": f"{prop.type_hash:08x}",
                    "size": prop.size,
                    "head_hex": payload[:96].hex(),
                    "dds_string_refs": scan_string_refs(payload, nif.strings),
                }
            )
        shapes.append(
            {
                "shape_block": shape["block"],
                "name": shape["name"],
                "geometry_block": shape["data_ref"],
                "vertices": len(geometry["vertices"]),
                "triangles": len(geometry["faces"]),
                "property_refs": shape["property_refs"],
                "textures": shape_texture_names(data, nif, shape),
                "properties": properties,
            }
        )

    report = {
        "nif": str(args.nif.resolve()),
        "shape_count": len(shapes),
        "shapes": shapes,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
