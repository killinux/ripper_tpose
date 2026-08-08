#!/usr/bin/env python3
"""List native G1M models in Venus Vacation PRISM RDB/FDATA packages."""

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
    scan_assets,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--game", required=True, type=Path,
                        help="Game root or its fdata_package directory")
    result.add_argument("--output", required=True, type=Path,
                        help="Directory for models.json, models.csv and models.md")
    result.add_argument("--probe", action="store_true",
                        help="Decode every G1M and include chunk/joint metadata")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        data_root = data_root_from_game(args.game)
        entries = scan_assets(data_root, G1M_TYPE)
    except PrismArchiveError as exc:
        raise SystemExit(f"error: {exc}") from exc

    rows: list[dict[str, object]] = []
    probe_errors = 0
    for index, entry in enumerate(entries, 1):
        row = {"index": index, **entry.as_dict()}
        if args.probe:
            try:
                metadata = parse_g1m_metadata(read_asset(entry))
                row.update({
                    "g1m_version": metadata["version"],
                    "chunk_count": metadata["chunk_count"],
                    "skeleton_joints": metadata["skeleton_joints"],
                    "category": metadata["category"],
                    "chunks": metadata["chunks"],
                })
            except (OSError, PrismArchiveError) as exc:
                row["probe_error"] = str(exc)
                probe_errors += 1
        rows.append(row)

    unique_ids = len({entry.file_id for entry in entries})
    packages = len({entry.package_id for entry in entries})
    total_content_size = sum(entry.content_size for entry in entries)
    total_uncompressed_size = sum(entry.uncompressed_size for entry in entries)
    categories = Counter(str(row.get("category", "unprobed")) for row in rows)
    summary = {
        "game": str(args.game.resolve()),
        "data_root": str(data_root),
        "model_entries": len(entries),
        "unique_model_ids": unique_ids,
        "packages_with_models": packages,
        "total_content_size": total_content_size,
        "total_uncompressed_size": total_uncompressed_size,
        "probe_enabled": args.probe,
        "probe_errors": probe_errors,
        "categories": dict(sorted(categories.items())),
    }

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "models.json").write_text(
        json.dumps({"summary": summary, "models": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    csv_fields = [
        "index", "file_id", "package", "offset", "entry_size",
        "content_size", "uncompressed_size", "flags", "g1m_version",
        "chunk_count", "skeleton_joints", "category", "probe_error",
    ]
    with (output / "models.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Venus Vacation PRISM 模型清单",
        "",
        f"- G1M 条目：{len(entries)}",
        f"- 唯一模型 ID：{unique_ids}",
        f"- 含模型的 FDATA 包：{packages}",
        f"- FDATA 内压缩数据：{total_content_size} 字节",
        f"- 解压后 G1M 数据：{total_uncompressed_size} 字节",
        f"- 深度探测：{'是' if args.probe else '否'}",
        f"- 探测失败：{probe_errors}",
        "",
        "| # | File ID | FDATA | Offset | 解压大小 | 骨骼 | 分类 |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['index']} | `{row['file_id']}` | `{row['package']}` | "
            f"{row['offset']} | {row['uncompressed_size']} | "
            f"{row.get('skeleton_joints', '')} | {row.get('category', '')} |")
    (output / "models.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {output / 'models.json'}")
    print(f"Wrote {output / 'models.csv'}")
    print(f"Wrote {output / 'models.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
