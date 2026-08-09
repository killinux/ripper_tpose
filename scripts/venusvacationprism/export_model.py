#!/usr/bin/env python3
"""Extract one native G1M model from Venus Vacation PRISM."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from prism_rdb import (
    G1M_TYPE,
    PrismArchiveError,
    data_root_from_game,
    find_entry,
    parse_g1m_metadata,
    read_asset,
    rdb_name_hash,
    scan_assets,
)


def parse_file_id(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("file ID must be decimal or 0x-prefixed hex") from exc


def parse_model_name(value: str) -> str:
    name = Path(value).name
    if name.lower().endswith(".g1m"):
        name = name[:-4]
    if not name or "." in name:
        raise argparse.ArgumentTypeError(
            "model name must be an internal basename such as FACE_FON_000")
    return name.upper()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--game", required=True, type=Path,
                        help="Game root or its fdata_package directory")
    selector = result.add_mutually_exclusive_group(required=True)
    selector.add_argument("--id", dest="file_id", type=parse_file_id,
                          help="Model file KTID, for example 0x2c3dbb6b")
    selector.add_argument("--index", type=int,
                          help="One-based index from list_models.py")
    selector.add_argument("--name", type=parse_model_name,
                          help="Recovered internal basename, for example FACE_FON_000")
    result.add_argument("--output", required=True, type=Path,
                        help="Output directory for G1M and manifest")
    result.add_argument("--gltf-tool", type=Path,
                        help="Optional eArmada8/gust_stuff g1m_to_basic_gltf.py")
    result.add_argument("--converter-pythonpath", type=Path,
                        help="Optional dependency directory containing pyquaternion")
    return result


def main() -> int:
    args = parser().parse_args()
    selected_file_id = args.file_id
    if args.name:
        selected_file_id = rdb_name_hash(args.name, "G1M")
    try:
        data_root = data_root_from_game(args.game)
        models = scan_assets(data_root, G1M_TYPE)
        index, entry = find_entry(models, file_id=selected_file_id, index=args.index)
        data = read_asset(entry)
        metadata = parse_g1m_metadata(data)
    except (OSError, PrismArchiveError) as exc:
        raise SystemExit(f"error: {exc}") from exc

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = f"model_{index:04d}_0x{entry.file_id:08x}"
    g1m_path = output / f"{stem}.g1m"
    g1m_path.write_bytes(data)

    manifest = {
        "index": index,
        "internal_name": args.name,
        "source": entry.as_dict(),
        "output_g1m": str(g1m_path),
        "g1m": metadata,
    }
    manifest_path = output / f"{stem}.json"

    def write_manifest() -> None:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Record the successful native extraction before invoking an optional,
    # third-party converter. A converter failure must never hide the usable G1M.
    write_manifest()

    if args.gltf_tool:
        tool = args.gltf_tool.expanduser().resolve()
        if not tool.is_file():
            manifest["conversion_error"] = f"glTF tool does not exist: {tool}"
            write_manifest()
            raise SystemExit(f"error: glTF tool does not exist: {tool}")
        environment = os.environ.copy()
        if args.converter_pythonpath:
            dependency_path = str(args.converter_pythonpath.expanduser().resolve())
            current = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                dependency_path if not current else dependency_path + os.pathsep + current)
        command = [sys.executable, str(tool), "--overwrite", str(g1m_path)]
        completed = subprocess.run(command, env=environment, check=False)
        if completed.returncode != 0:
            manifest["conversion_error"] = (
                f"G1M to glTF converter exited with {completed.returncode}")
            write_manifest()
            raise SystemExit(
                f"error: G1M to glTF converter exited with {completed.returncode}")
        gltf_path = g1m_path.with_suffix(".gltf")
        bin_path = g1m_path.with_suffix(".bin")
        if not gltf_path.is_file() or not bin_path.is_file():
            manifest["conversion_error"] = (
                "converter returned success but produced no glTF/BIN")
            write_manifest()
            raise SystemExit("error: converter returned success but produced no glTF/BIN")
        manifest["output_gltf"] = str(gltf_path)
        manifest["output_bin"] = str(bin_path)

    write_manifest()
    result = {
        "index": index,
        "internal_name": args.name,
        "file_id": f"0x{entry.file_id:08x}",
        "package": entry.package_path.name,
        "g1m": str(g1m_path),
        "size": len(data),
        "skeleton_joints": metadata["skeleton_joints"],
        "category": metadata["category"],
        "manifest": str(manifest_path),
    }
    if "output_gltf" in manifest:
        result["gltf"] = manifest["output_gltf"]
        result["bin"] = manifest["output_bin"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
