#!/usr/bin/env python3
"""Batch-export the female Throne of Desire KFM model groups.

The installed game does not ship a model-to-localized-name table.  This list
therefore uses the KFM groups whose rendered base mesh is female.  ``hm*``
groups are composite scene models and are deliberately not duplicated here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


FEMALE_MODEL_IDS = (
    "h005",
    "h006",
    "h008",
    "h009",
    "h011",
    "h012",
    "h015",
    "h020",
    "h021",
    "h091",
    "h997",
    "h998",
    "h999",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--lzham-decoder", type=Path)
    parser.add_argument("--etc-decoder", type=Path)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=FEMALE_MODEL_IDS,
        default=list(FEMALE_MODEL_IDS),
        help="Optional subset; defaults to all classified female KFM groups.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("blend", "fbx"),
        default=("blend", "fbx"),
    )
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--include-helpers", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export models whose requested final artifacts already exist.",
    )
    return parser.parse_args()


def expected_artifacts(
    output_root: Path,
    model_id: str,
    formats: tuple[str, ...] | list[str],
    render: bool,
) -> list[Path]:
    model_dir = output_root / model_id
    artifacts = [
        model_dir / "source" / f"{model_id}.nif",
        model_dir / "source" / f"{model_id}.kfm",
        model_dir / "textures" / "textures_manifest.json",
    ]
    if "blend" in formats:
        artifacts.append(model_dir / f"{model_id}_blender36.blend")
    if "fbx" in formats:
        artifacts.append(model_dir / f"{model_id}.fbx")
    if render:
        artifacts.append(model_dir / f"{model_id}_preview.png")
    return artifacts


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def load_preserved_records(output_root: Path, requested: set[str]) -> list[dict]:
    """Keep prior manifest entries for models not re-exported this run.

    Without this, a ``--models`` subset would rewrite the manifest with only
    the requested models and silently drop the other recorded exports.
    """
    manifest = output_root / "female_export_manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in payload.get("records", [])
            if isinstance(item, dict) and item.get("model") not in requested]


def write_manifest(
    output_root: Path,
    records: list[dict],
    preserved: list[dict] | tuple = (),
) -> None:
    order = {model: index for index, model in enumerate(FEMALE_MODEL_IDS)}
    merged = sorted(
        list(preserved) + records,
        key=lambda item: (
            order.get(item.get("model"), len(order)),
            item.get("model", ""),
        ),
    )
    complete = [item for item in merged if item["status"] in {"complete", "skipped"}]
    failed = [item for item in merged if item["status"] == "failed"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": "render-verified female KFM model groups; hm scene groups excluded",
        "requested_models": [item["model"] for item in records],
        "complete_count": len(complete),
        "failed_count": len(failed),
        "total_bytes": sum(item.get("bytes", 0) for item in complete),
        "records": merged,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "female_export_manifest.json"
    temporary = manifest.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(manifest)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    export_script = script_dir / "export_model.py"
    output_root = args.output.resolve()
    records: list[dict] = []
    preserved = load_preserved_records(output_root, set(args.models))
    formats = list(dict.fromkeys(args.formats))
    render = not args.no_render

    for position, model_id in enumerate(args.models, 1):
        artifacts = expected_artifacts(output_root, model_id, formats, render)
        model_dir = output_root / model_id
        if not args.force and all(item.is_file() and item.stat().st_size for item in artifacts):
            record = {
                "model": model_id,
                "status": "skipped",
                "reason": "all requested artifacts already exist",
                "bytes": directory_size(model_dir),
                "artifacts": [str(item) for item in artifacts],
            }
            records.append(record)
            write_manifest(output_root, records, preserved)
            print(f"[{position}/{len(args.models)}] {model_id}: already complete", flush=True)
            continue

        command = [
            sys.executable,
            str(export_script),
            "--game",
            str(args.game),
            "--model",
            model_id,
            "--blender",
            str(args.blender),
            "--output",
            str(output_root),
            "--formats",
            *formats,
        ]
        if render:
            command.append("--render")
        if args.include_helpers:
            command.append("--include-helpers")
        if args.lzham_decoder:
            command.extend(("--lzham-decoder", str(args.lzham_decoder)))
        if args.etc_decoder:
            command.extend(("--etc-decoder", str(args.etc_decoder)))

        print(f"[{position}/{len(args.models)}] exporting {model_id}", flush=True)
        started = time.monotonic()
        completed = subprocess.run(command, check=False)
        missing = [str(item) for item in artifacts if not item.is_file() or not item.stat().st_size]
        status = "complete" if completed.returncode == 0 and not missing else "failed"
        record = {
            "model": model_id,
            "status": status,
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "bytes": directory_size(model_dir) if model_dir.is_dir() else 0,
            "artifacts": [str(item) for item in artifacts],
            "missing_artifacts": missing,
        }
        records.append(record)
        write_manifest(output_root, records, preserved)
        print(
            f"[{position}/{len(args.models)}] {model_id}: {status} "
            f"({record['duration_seconds']}s)",
            flush=True,
        )

    return 1 if any(item["status"] == "failed" for item in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
