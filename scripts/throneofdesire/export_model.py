#!/usr/bin/env python3
"""One-command Throne of Desire model export for Blender 3.6 and FBX."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from extract_nfs import xlegend_hash32
from xlegend_nif import (
    SHAPE_HASH,
    is_primary_character_shape,
    parse_nif,
    parse_shape,
    shape_texture_names,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def run(command: list[str], label: str) -> None:
    print(f"[{label}] {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")


def existing_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def texture_jobs(nif_path: Path, model_id: str) -> list[tuple[str, str]]:
    """Return ``(package, owner model)`` jobs for DDS refs in a NIF.

    Models such as h996 intentionally reuse h001 body textures.  The first
    four filename characters identify both the owning model family and its NFS
    package, so cross-package dependencies can be extracted automatically.

    Character NIFs also catalog many optional attachment meshes.  Only
    cross-package textures referenced by a visible primary shape are included;
    h999's body-completion equipment is primary even though its names use the
    ``he10``/``he50`` families.
    """
    data = nif_path.read_bytes()
    nif = parse_nif(data)
    model_package = f"{xlegend_hash32(model_id[:4]):08x}"
    base_texture_names: set[str] = set()
    for block in nif.blocks:
        if block.type_hash != SHAPE_HASH:
            continue
        try:
            shape = parse_shape(data, nif, block)
        except (ValueError, IndexError):
            continue
        name = shape.get("name") or ""
        textures = shape_texture_names(data, nif, shape)
        if (
            shape.get("skin_instance_ref", -1) >= 0
            and is_primary_character_shape(model_id, name, textures)
        ):
            base_texture_names.update(
                Path(value.replace("\\", "/")).name.lower()
                for value in textures
            )

    owners: dict[str, str] = {}
    for value in nif.strings:
        if not value.lower().endswith(".dds"):
            continue
        filename = Path(value.replace("\\", "/")).name.lower()
        owner = filename[:4]
        package = f"{xlegend_hash32(owner):08x}"
        if package != model_package and filename not in base_texture_names:
            continue
        owners.setdefault(package, model_id if package == model_package else owner)
    return sorted(owners.items())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--lzham-decoder",
        type=Path,
        default=REPO_ROOT / ".tmp" / "lzham_v1_decode_raw",
    )
    parser.add_argument(
        "--etc-decoder",
        type=Path,
        default=REPO_ROOT / ".tmp" / "etc_dds_decode",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("blend", "fbx"),
        default=("blend", "fbx"),
    )
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--include-helpers", action="store_true")
    args = parser.parse_args()

    try:
        blender = existing_file(args.blender, "Blender")
        lzham_decoder = existing_file(args.lzham_decoder, "LZHAM decoder")
        etc_decoder = existing_file(args.etc_decoder, "ETC DDS decoder")
        model_id = args.model.lower()
        output_dir = (args.output / model_id).resolve()
        source_dir = output_dir / "source"
        textures_dir = output_dir / "textures"
        output_dir.mkdir(parents=True, exist_ok=True)

        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "extract_nfs.py"),
                "extract-model",
                "--game",
                str(args.game),
                "--model",
                model_id,
                "--output",
                str(source_dir),
            ],
            "extract model",
        )
        nif_path = existing_file(source_dir / f"{model_id}.nif", "extracted NIF")
        texture_results = []
        for package_name, owner_model in texture_jobs(nif_path, model_id):
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "extract_model_textures.py"),
                    "--game",
                    str(args.game),
                    "--model",
                    owner_model,
                    "--nif",
                    # The character NIF already contains the exact referenced
                    # DDS names.  Equipment texture packages do not ship a KFM,
                    # so trying to extract an owner model first would fail.
                    str(nif_path),
                    "--decoder",
                    str(lzham_decoder),
                    "--etc-decoder",
                    str(etc_decoder),
                    "--output",
                    str(textures_dir),
                ],
                f"extract textures from {owner_model}",
            )
            job_manifest = existing_file(
                textures_dir / "textures_manifest.json", "texture job manifest"
            )
            job_data = json.loads(job_manifest.read_text(encoding="utf-8"))
            dependency_manifest = textures_dir / f"textures_manifest_{owner_model}.json"
            dependency_manifest.write_text(
                json.dumps(job_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            texture_results.append(
                {
                    "package": package_name,
                    "owner_model": owner_model,
                    "manifest": str(dependency_manifest),
                    "mapped_textures": len(job_data.get("textures", [])),
                }
            )

        textures_dir.mkdir(parents=True, exist_ok=True)
        aggregate_texture_manifest = textures_dir / "textures_manifest.json"
        aggregate_texture_manifest.write_text(
            json.dumps(
                {
                    "model": model_id,
                    "texture_dependencies": texture_results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        blend_path = output_dir / f"{model_id}_blender36.blend"
        fbx_path = output_dir / f"{model_id}.fbx"
        preview_path = output_dir / f"{model_id}_preview.png"
        blender_command = [
            str(blender),
            "--background",
            "--python",
            str(SCRIPT_DIR / "import_xlegend_nif36.py"),
            "--",
            "--input",
            str(nif_path),
            "--textures",
            str(textures_dir),
            "--output",
            str(blend_path),
        ]
        if "fbx" in args.formats:
            blender_command.extend(("--fbx", str(fbx_path)))
        if args.render:
            blender_command.extend(("--render", str(preview_path)))
        if args.include_helpers:
            blender_command.append("--include-helpers")
        run(blender_command, "Blender import/export")

        files = {
            "blend": str(existing_file(blend_path, "Blend output")),
            "fbx": str(existing_file(fbx_path, "FBX output"))
            if "fbx" in args.formats
            else None,
            "preview": str(existing_file(preview_path, "preview output"))
            if args.render
            else None,
            "nif": str(nif_path),
            "kfm": str(existing_file(source_dir / f"{model_id}.kfm", "extracted KFM")),
            "textures_manifest": str(
                existing_file(textures_dir / "textures_manifest.json", "texture manifest")
            ),
        }
        manifest = {
            "model": model_id,
            "game": str(args.game.resolve()),
            "blender": str(blender),
            "formats": list(args.formats),
            "known_limitations": [
                "Rest skeleton is present, but optimized skin weights are not applied yet.",
                "FBX contains the imported primary meshes and the rest armature.",
                "Decoded EAC normal maps are preserved but disconnected by default pending channel-convention validation.",
            ],
            "files": files,
        }
        manifest_path = output_dir / "export_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({**manifest, "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))
        return 0
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
