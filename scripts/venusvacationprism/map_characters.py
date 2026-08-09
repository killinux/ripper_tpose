#!/usr/bin/env python3
"""Recover PRISM character component names and write an actionable model map."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from prism_rdb import (
    G1M_TYPE,
    PrismArchiveError,
    data_root_from_game,
    parse_g1m_metadata,
    read_asset,
    rdb_name_hash,
    scan_assets,
)


CHARACTERS = (
    {"code": "MIS", "name_en": "Misaki", "name_zh": "海咲"},
    {"code": "FON", "name_en": "Fiona", "name_zh": "菲欧娜"},
    {"code": "ELS", "name_en": "Elise", "name_zh": "伊莉丝"},
    {"code": "TAM", "name_en": "Tamaki", "name_zh": "环"},
    {"code": "NNM", "name_en": "Nanami", "name_zh": "七海"},
    {"code": "HON", "name_en": "Honoka", "name_zh": "穗香"},
)

COMPONENTS = (
    ("FACE", "脸部"),
    ("HAIR", "头发"),
    ("COS", "服装/身体"),
    ("BODY", "身体"),
    ("BDY", "身体"),
    ("HEAD", "头部"),
    ("EYE", "眼睛"),
    ("EYELASH", "睫毛"),
    ("BROW", "眉毛"),
    ("TEETH", "牙齿"),
    ("SKIN", "皮肤"),
    ("ARM", "手臂"),
    ("COSTUME", "服装/身体"),
    ("OUTFIT", "服装/身体"),
    ("MODEL", "模型"),
    ("CHARA", "角色"),
    ("CHR", "角色"),
    ("HR", "头发"),
    ("FAC", "脸部"),
)

FORMATS = ("G1M", "MTL", "GRP", "OID")
OFFICIAL_ROSTER_URL = "https://www.gamecity.ne.jp/venusvacation/prism/"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--game", required=True, type=Path,
                        help="Game root or its fdata_package directory")
    result.add_argument("--output", required=True, type=Path,
                        help="Directory for character_models.json/csv/md")
    result.add_argument(
        "--character", action="append", default=[],
        help="Optional Chinese name, English name, or internal code filter")
    return result


def selected_characters(filters: list[str]) -> tuple[dict[str, str], ...]:
    if not filters:
        return CHARACTERS
    wanted = {value.strip().casefold() for value in filters if value.strip()}
    selected = tuple(
        character for character in CHARACTERS
        if wanted.intersection({
            character["code"].casefold(),
            character["name_en"].casefold(),
            character["name_zh"].casefold(),
        })
    )
    missing = wanted.difference(
        value.casefold()
        for character in selected
        for value in character.values()
    )
    if missing:
        valid = ", ".join(
            f"{item['name_zh']}/{item['name_en']}/{item['code']}"
            for item in CHARACTERS)
        raise PrismArchiveError(
            f"Unknown character filter(s): {', '.join(sorted(missing))}. Valid: {valid}")
    return selected


def candidate_basenames(code: str):
    for category, component_zh in COMPONENTS:
        for number in range(1000):
            yield category, component_zh, f"{category}_{code}_{number:03d}"
            yield category, component_zh, f"{code}_{category}_{number:03d}"


def recover_rows(data_root: Path, characters) -> list[dict[str, object]]:
    entries = scan_assets(data_root)
    all_ids = {entry.file_id for entry in entries}
    models = [entry for entry in entries if entry.type_id == G1M_TYPE]
    models_by_id = {
        entry.file_id: (index, entry)
        for index, entry in enumerate(models, 1)
    }
    rows: list[dict[str, object]] = []
    seen_model_ids: set[int] = set()

    for character_order, character in enumerate(characters):
        for category, component_zh, basename in candidate_basenames(character["code"]):
            g1m_id = rdb_name_hash(basename, "G1M")
            model_match = models_by_id.get(g1m_id)
            if model_match is None or g1m_id in seen_model_ids:
                continue
            resource_ids = {
                extension: rdb_name_hash(basename, extension)
                for extension in FORMATS
            }
            present = {
                extension: file_id
                for extension, file_id in resource_ids.items()
                if file_id in all_ids
            }
            # A G1M plus two companion resources makes accidental 32-bit hash
            # collisions vanishingly unlikely while tolerating optional formats.
            if "G1M" not in present or len(present) < 3:
                continue

            index, entry = model_match
            row: dict[str, object] = {
                "character_order": character_order,
                "character_zh": character["name_zh"],
                "character_en": character["name_en"],
                "character_code": character["code"],
                "component": category,
                "component_zh": component_zh,
                "internal_name": basename,
                "model_index": index,
                "file_id": f"0x{entry.file_id:08x}",
                "mtl_id": (
                    f"0x{present['MTL']:08x}" if "MTL" in present else None),
                "grp_id": (
                    f"0x{present['GRP']:08x}" if "GRP" in present else None),
                "oid_id": (
                    f"0x{present['OID']:08x}" if "OID" in present else None),
                "resource_bundle": "+".join(present),
                "confidence": "confirmed_hash_bundle",
                "package": entry.package_path.name,
                "content_size": entry.content_size,
                "uncompressed_size": entry.uncompressed_size,
            }
            try:
                metadata = parse_g1m_metadata(read_asset(entry))
                row.update({
                    "g1m_version": metadata["version"],
                    "chunk_count": metadata["chunk_count"],
                    "skeleton_joints": metadata["skeleton_joints"],
                    "model_category": metadata["category"],
                })
            except (OSError, PrismArchiveError) as exc:
                row["probe_error"] = str(exc)
            rows.append(row)
            seen_model_ids.add(g1m_id)

    component_order = {"FACE": 0, "COS": 1, "HAIR": 2}
    rows.sort(key=lambda row: (
        row["character_order"],
        component_order.get(str(row["component"]), 9),
        row["internal_name"],
    ))
    return rows


def write_outputs(output: Path, game: Path, rows: list[dict[str, object]]) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter(str(row["character_en"]) for row in rows)
    summary = {
        "game": str(game.resolve()),
        "official_roster": OFFICIAL_ROSTER_URL,
        "mapping_method": (
            "KTGL RDB filename hash; a row is accepted only when its G1M and "
            "at least two of MTL/GRP/OID are present"),
        "confirmed_models": len(rows),
        "characters": dict(counts),
        "note": (
            "Face, hair, and costume/body are separate resources. Unnamed shared "
            "base bodies are intentionally not assigned to a character."),
    }
    json_path = output / "character_models.json"
    csv_path = output / "character_models.csv"
    md_path = output / "character_models.md"
    json_path.write_text(
        json.dumps({"summary": summary, "models": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    fields = [
        "character_zh", "character_en", "character_code", "component_zh",
        "component", "internal_name", "model_index", "file_id", "package",
        "uncompressed_size", "skeleton_joints", "model_category", "mtl_id",
        "grp_id", "oid_id", "resource_bundle", "confidence", "probe_error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Venus Vacation PRISM 角色—模型对应表",
        "",
        f"- 已确认角色组件 G1M：{len(rows)}",
        "- 证据：内部名称同时命中 G1M，并至少命中 MTL/GRP/OID 中两项。",
        "- 注意：脸、头发和服装/身体是分件；没有名称证据的共用基础身体不强行归属。",
        "",
        "| 角色 | 类型 | 内部名称（可传给 `--name`） | 模型编号 | KTID | 骨骼 | 解压大小 MiB |",
        "|---|---|---|---:|---|---:|---:|",
    ]
    for row in rows:
        size_mib = int(row["uncompressed_size"]) / (1024 * 1024)
        lines.append(
            f"| {row['character_zh']} ({row['character_en']}) | "
            f"{row['component_zh']} | `{row['internal_name']}` | "
            f"{row['model_index']} | `{row['file_id']}` | "
            f"{row.get('skeleton_joints', '')} | {size_mib:.2f} |")
    lines.extend([
        "",
        "例如按恢复名称导出：",
        "",
        "```powershell",
        "python scripts\\venusvacationprism\\export_model.py `",
        "  --game \"D:\\Program Files (x86)\\Steam\\steamapps\\common\\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -\" `",
        "  --name FACE_FON_000 `",
        "  --output \"D:\\venusvacationprism_exports\\FACE_FON_000\"",
        "```",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parser().parse_args()
    try:
        data_root = data_root_from_game(args.game)
        characters = selected_characters(args.character)
        rows = recover_rows(data_root, characters)
        write_outputs(args.output, args.game, rows)
    except (OSError, PrismArchiveError) as exc:
        raise SystemExit(f"error: {exc}") from exc

    result = {
        "confirmed_models": len(rows),
        "characters": dict(Counter(str(row["character_en"]) for row in rows)),
        "output": str(args.output.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
