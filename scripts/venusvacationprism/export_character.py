#!/usr/bin/env python3
"""Export one verified Venus Vacation PRISM character by display name.

This is the high-level entry point.  It selects a reviewed BODY/FACE/HAIR
profile, extracts the original resources and textures, converts the three
components, and asks Blender to build portable Blend/FBX/GLB outputs.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from character_profiles import (
    CHARACTER_PROFILES,
    CharacterProfile,
    get_character_profile,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_GAME = Path(
    r"D:\Program Files (x86)\Steam\steamapps\common"
    r"\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -"
)
DEFAULT_EXPORT_ROOT = Path(r"D:\venusvacationprism_exports")
VALID_FORMATS = ("blend", "fbx", "glb")
OWNER_FILENAME = ".prism-character-export.json"


class ExportError(RuntimeError):
    """A user-actionable complete-character export failure."""


def _csv(value: str) -> tuple[str, ...]:
    values = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = sorted(set(values).difference(VALID_FORMATS))
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown format(s): {', '.join(unknown)}; valid: {', '.join(VALID_FORMATS)}"
        )
    if not values:
        raise argparse.ArgumentTypeError("at least one output format is required")
    return tuple(dict.fromkeys(values))


def _path_list(value: str) -> tuple[Path, ...]:
    return tuple(Path(part.strip()) for part in value.split(os.pathsep) if part.strip())


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--character", "--name", help="English/Chinese name or code")
    result.add_argument(
        "--list-characters", action="store_true",
        help="List reviewed character profiles and exit",
    )
    result.add_argument("--game", type=Path, help="Game root or fdata_package")
    result.add_argument("--output", type=Path, help="Final portable export directory")
    result.add_argument("--blender", type=Path, help="Blender 3.6+ executable")
    result.add_argument("--gust-dir", type=Path, help="eArmada8/gust_stuff directory")
    result.add_argument(
        "--converter-deps", action="append", type=Path, default=[],
        help="Dependency path for the G1M converter; repeat as needed",
    )
    result.add_argument(
        "--python-deps", action="append", type=Path, default=[],
        help="Dependency path containing Pillow/numpy; repeat as needed",
    )
    result.add_argument("--formats", type=_csv, default=VALID_FORMATS)
    result.add_argument("--resume", action="store_true", help="Reuse validated stages")
    result.add_argument("--assets-only", action="store_true", help="Stop after component glTFs")
    result.add_argument("--skip-previews", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--skip-fbx-roundtrip", action="store_true", help=argparse.SUPPRESS)
    result.add_argument(
        "--plan", "--dry-run", action="store_true",
        help="Print the resolved profile, tools and paths without writing",
    )
    return result


def discover_game(explicit: Path | None) -> Path:
    candidates = [
        explicit,
        Path(os.environ["PRISM_GAME"]) if os.environ.get("PRISM_GAME") else None,
        DEFAULT_GAME,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        candidate = candidate.expanduser()
        data_root = candidate / "fdata_package"
        if (data_root / "root.rdb").is_file() and (data_root / "root.rdx").is_file():
            return candidate.resolve()
        if (candidate / "root.rdb").is_file() and (candidate / "root.rdx").is_file():
            return candidate.resolve()
    raise ExportError("game data was not found; pass --game PATH or set PRISM_GAME")


def discover_blender(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("BLENDER_EXE"):
        candidates.append(Path(os.environ["BLENDER_EXE"]))
    candidates.extend([
        Path(r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"),
        Path(r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe"),
    ])
    for candidate in candidates:
        if candidate.expanduser().is_file():
            return candidate.expanduser().resolve()
    raise ExportError(
        "Blender 3.6 LTS was not found; pass --blender PATH or set BLENDER_EXE"
    )


def discover_gust(explicit: Path | None) -> Path:
    candidates = [
        explicit,
        Path(os.environ["GUST_STUFF_DIR"]) if os.environ.get("GUST_STUFF_DIR") else None,
        REPO_ROOT / ".tmp" / "gust_stuff",
    ]
    for candidate in candidates:
        if candidate and (candidate.expanduser() / "g1m_to_basic_gltf.py").is_file():
            return candidate.expanduser().resolve()
    raise ExportError(
        "gust_stuff was not found; clone eArmada8/gust_stuff and pass --gust-dir PATH"
    )


def discover_dependency_paths(
    explicit: Iterable[Path], environment_name: str, defaults: Iterable[Path]
) -> tuple[Path, ...]:
    values = list(explicit)
    if os.environ.get(environment_name):
        values.extend(_path_list(os.environ[environment_name]))
    values.extend(defaults)
    result: list[Path] = []
    for value in values:
        candidate = value.expanduser()
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved not in result:
                result.append(resolved)
    return tuple(result)


def default_output(profile: CharacterProfile) -> Path:
    if DEFAULT_EXPORT_ROOT.parent.exists():
        return DEFAULT_EXPORT_ROOT / profile.key / "complete_auto"
    return REPO_ROOT / "exports" / profile.key / "complete"


def component_plan(profile: CharacterProfile) -> dict[str, dict[str, Any]]:
    return {
        role.lower(): {
            "label": component.label,
            "model_index": component.model_index,
            "package": component.package_name,
            "g1m": f"0x{component.g1m:08x}",
            "oid": f"0x{component.oid:08x}",
            "grp": f"0x{component.grp:08x}",
            "ktid": f"0x{component.ktid:08x}",
            "mtl": f"0x{component.mtl:08x}",
            "texture_slots": component.texture_slots,
        }
        for role, component in profile.components.items()
    }


def resolved_plan(args: argparse.Namespace, profile: CharacterProfile) -> dict[str, Any]:
    game = discover_game(args.game)
    output = (args.output or default_output(profile)).expanduser().resolve()
    gust = discover_gust(args.gust_dir)
    python_deps = discover_dependency_paths(
        args.python_deps, "PRISM_PYTHON_DEPS", (REPO_ROOT / ".tmp" / "pydeps",)
    )
    converter_deps = discover_dependency_paths(
        args.converter_deps, "PRISM_CONVERTER_DEPS", (REPO_ROOT / ".tmp" / "gust_deps",)
    )
    blender = None if args.assets_only else discover_blender(args.blender)
    return {
        "character": profile.name_en,
        "character_zh": profile.name_zh,
        "code": profile.code,
        "support_level": profile.support_level,
        "game": str(game),
        "output": str(output),
        "gust_dir": str(gust),
        "blender": str(blender) if blender else None,
        "python_deps": [str(path) for path in python_deps],
        "converter_deps": [str(path) for path in converter_deps],
        "formats": list(args.formats),
        "resume": args.resume,
        "assets_only": args.assets_only,
        "skip_previews": args.skip_previews,
        "skip_fbx_roundtrip": args.skip_fbx_roundtrip,
        "components": component_plan(profile),
        "body_postprocess": dict(profile.body_postprocess),
    }


def ensure_output_state(output: Path, resume: bool) -> None:
    if output.exists() and not output.is_dir():
        raise ExportError(f"output is not a directory: {output}")
    if output.is_dir() and any(output.iterdir()) and not resume:
        raise ExportError(
            f"output is not empty: {output}; pass --resume or choose another --output"
        )
    output.mkdir(parents=True, exist_ok=True)


def selection_record(profile: CharacterProfile) -> dict[str, Any]:
    return {
        "profile_key": profile.key,
        "components": component_plan(profile),
        "alpha": serializable_profile(profile.alpha),
        "body_postprocess": serializable_profile(profile.body_postprocess),
        "face_postprocess": serializable_profile(profile.face_postprocess),
    }


def claim_output_directory(
    output: Path, profile: CharacterProfile, plan: dict[str, Any], resume: bool
) -> Path:
    """Bind a resumable directory to one reviewed selection and format set."""

    owner_path = output / OWNER_FILENAME
    selection = selection_record(profile)
    expected = {
        "schema": 1,
        **selection,
        "formats": list(plan["formats"]),
        "assets_only": bool(plan["assets_only"]),
        "skip_previews": bool(plan.get("skip_previews")),
        "skip_fbx_roundtrip": bool(plan.get("skip_fbx_roundtrip")),
    }
    prior: dict[str, Any] | None = None
    if owner_path.is_file():
        try:
            prior = json.loads(owner_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExportError(f"invalid output ownership marker: {owner_path}") from exc
    elif resume and any(output.iterdir()):
        legacy_manifest = output / "export_character_manifest.json"
        if not legacy_manifest.is_file():
            raise ExportError(
                f"cannot resume unclaimed output directory: {output}; "
                "choose a new --output"
            )
        try:
            legacy = json.loads(legacy_manifest.read_text(encoding="utf-8"))
            old_profile = legacy["profile"]
            old_plan = legacy["resolved_plan"]
            prior = {
                "schema": 1,
                "profile_key": old_profile["key"],
                "components": old_plan["components"],
                "alpha": old_profile["alpha"],
                "body_postprocess": old_profile["body_postprocess"],
                "face_postprocess": old_profile["face_postprocess"],
                "formats": old_plan["formats"],
                "assets_only": bool(old_plan["assets_only"]),
                "skip_previews": bool(old_plan.get("skip_previews")),
                "skip_fbx_roundtrip": bool(
                    old_plan.get("skip_fbx_roundtrip")
                ),
            }
        except (KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            raise ExportError(
                f"cannot establish ownership from {legacy_manifest}"
            ) from exc
    if prior is not None:
        prior.setdefault("skip_previews", False)
        prior.setdefault("skip_fbx_roundtrip", False)
        immutable_keys = (
            "profile_key",
            "components",
            "alpha",
            "body_postprocess",
            "face_postprocess",
            "formats",
            "skip_previews",
            "skip_fbx_roundtrip",
        )
        changed = [key for key in immutable_keys if prior.get(key) != expected[key]]
        if changed:
            raise ExportError(
                "--resume selection differs from the existing export "
                f"({', '.join(changed)}); choose a new --output"
            )
        # Assets-only is a valid first stage for a later full assembly, but a
        # full delivery may not be narrowed back to assets-only in place.
        if not prior.get("assets_only") and expected["assets_only"]:
            raise ExportError(
                "cannot resume a full delivery as --assets-only; choose a new --output"
            )
    owner_path.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return owner_path


def add_python_paths(paths: Iterable[Path]) -> None:
    for path in reversed(tuple(paths)):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def role_result(assets: dict[str, Any], role: str) -> dict[str, Any]:
    for key, value in assets.items():
        if key.casefold() == role.casefold():
            return value
    raise ExportError(f"asset stage did not return {role}: {sorted(assets)}")


def run_blender(
    *, plan: dict[str, Any], profile: CharacterProfile,
    assets: dict[str, Any], args: argparse.Namespace,
) -> Path:
    output = Path(plan["output"])
    script = SCRIPT_DIR / "blender_assemble_character.py"
    if not script.is_file():
        raise ExportError(f"missing Blender assembly script: {script}")
    report_path = output / f"{profile.name_en}_Complete_Rigged_report.json"
    previous_report_mtime = (
        report_path.stat().st_mtime_ns if report_path.is_file() else None
    )
    body = role_result(assets, "body")
    face = role_result(assets, "face")
    hair = role_result(assets, "hair")
    command = [
        str(plan["blender"]), "--background", "--python-exit-code", "1",
        "--python", str(script), "--",
        "--character", profile.name_en,
        "--body", str(body["final_gltf"]),
        "--face", str(face["final_gltf"]),
        "--hair", str(hair["final_gltf"]),
        "--output-dir", str(output),
        "--formats", ",".join(plan["formats"]),
        "--body-alpha", ",".join(map(str, profile.alpha.body)),
        "--face-alpha", ",".join(map(str, profile.alpha.face)),
        "--hair-alpha", ",".join(map(str, profile.alpha.hair)),
    ]
    if args.skip_previews:
        command.append("--skip-previews")
    if args.skip_fbx_roundtrip:
        command.append("--skip-fbx-roundtrip")
    log_path = output / "blender_export.log"
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    log_path.write_text(
        completed.stdout + "\n--- STDERR ---\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode:
        raise ExportError(
            f"Blender assembly failed with exit code {completed.returncode}; see {log_path}"
        )
    if not report_path.is_file():
        raise ExportError("Blender returned success but produced no assembly report")
    if (
        previous_report_mtime is not None
        and report_path.stat().st_mtime_ns <= previous_report_mtime
    ):
        raise ExportError(
            "Blender returned success but did not refresh the assembly report"
        )
    return report_path


def validate_baseline(profile: CharacterProfile, report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    stats = (
        report.get("assembly_stats")
        or report.get("blend_stats")
        or report.get("scene")
        or report.get("stats")
    )
    if not isinstance(stats, dict):
        raise ExportError(f"assembly report has no blend_stats: {report_path}")
    expected = profile.expected
    checks: dict[str, Any] = {}

    def add(name: str, wanted: Any, actual: Any, passed: bool | None = None) -> None:
        checks[name] = {
            "expected": wanted,
            "actual": actual,
            "passed": bool(actual == wanted if passed is None else passed),
        }

    aliases = {
        "mesh_objects": ("mesh_objects", "meshes"),
        "armatures": ("armatures",),
        "vertices": ("vertices",),
        "polygons": ("polygons", "triangles"),
        "materials": ("materials",),
    }
    for field, names in aliases.items():
        actual = next((stats[name] for name in names if name in stats), None)
        wanted = getattr(expected, field)
        add(field, wanted, actual)

    requested = set(report.get("formats_requested") or ())
    supported = set(expected.output_formats)
    add(
        "requested_formats_verified",
        sorted(supported),
        sorted(requested),
        bool(requested) and requested.issubset(supported),
    )
    add("identity_alignment", True, report.get("identity_alignment"))
    head = report.get("head_fit") or {}
    add(
        "face_hair_bounds_intersect",
        True,
        head.get("face_hair_bounds_intersect"),
    )

    components = report.get("components") or {}
    body_component = components.get("BODY") or {}
    if expected.body_mesh_objects is not None:
        body_mesh_names = body_component.get("mesh_names") or []
        add(
            "body_mesh_objects",
            expected.body_mesh_objects,
            len(body_mesh_names),
        )
    if expected.body_skin_linked_meshes is not None:
        rig_namespace = body_component.get("rig_namespace") or {}
        armature_rows = rig_namespace.get("armatures") or []
        try:
            linked_meshes = sum(int(row["linked_meshes"]) for row in armature_rows)
        except (KeyError, TypeError, ValueError):
            linked_meshes = None
        add(
            "body_skin_linked_meshes",
            expected.body_skin_linked_meshes,
            linked_meshes,
        )
    source_rows: dict[str, Any] = {}
    for role in ("BODY", "FACE", "HAIR"):
        source = (components.get(role) or {}).get("source") or {}
        source_rows[role] = {
            "root_nodes_identity": source.get("root_nodes_identity"),
            "position_accessors_all_vec3": source.get(
                "position_accessors_all_vec3"
            ),
            "images": source.get("images"),
            "external_image_files_present": source.get(
                "external_image_files_present"
            ),
        }
    add(
        "component_source_integrity",
        "identity roots, VEC3 positions, and every external image present",
        source_rows,
        len(components) == 3
        and all(
            row["root_nodes_identity"] is True
            and row["position_accessors_all_vec3"] is True
            and row["images"] == row["external_image_files_present"]
            for row in source_rows.values()
        ),
    )

    neck = report.get("neck_fit") or {}
    neck_min = neck.get("nearest_distance_min")
    if expected.neck_min_distance is not None:
        add(
            "neck_nearest_distance",
            {"baseline": expected.neck_min_distance, "maximum": 0.001},
            neck_min,
            isinstance(neck_min, (int, float)) and 0 <= neck_min <= 0.001,
        )
    within = (neck.get("sampled_vertices_within_distance") or {}).get("0.001")
    if expected.neck_vertices_within_0_001 is not None:
        add(
            "neck_vertices_within_0_001",
            f">={expected.neck_vertices_within_0_001}",
            within,
            isinstance(within, int)
            and within >= expected.neck_vertices_within_0_001,
        )
    overlap = neck.get("face_body_vertical_bounds_overlap")
    add(
        "neck_vertical_overlap",
        ">0",
        overlap,
        isinstance(overlap, (int, float)) and overlap > 0,
    )

    outputs = report.get("outputs") or {}
    output_rows = {
        fmt: outputs.get(fmt)
        for fmt in sorted(requested)
    }
    add(
        "requested_output_files",
        sorted(requested),
        output_rows,
        all(
            isinstance(path, str) and Path(path).is_file()
            for path in output_rows.values()
        ),
    )

    if "blend" in requested:
        packed = report.get("blend_pack_audit") or {}
        add("blend_used_images", expected.blend_used_images, packed.get("images_used"))
        add(
            "blend_packed_images",
            expected.blend_packed_images,
            packed.get("used_images_packed"),
        )
        add(
            "blend_unpacked_images",
            [],
            packed.get("used_images_unpacked"),
        )

    if "fbx" in requested:
        fbx = report.get("fbx_roundtrip_validation") or {}
        fbx_stats = report.get("fbx_reimport_stats") or {}
        add("fbx_roundtrip", True, fbx.get("passed"))
        add("fbx_missing_materials", [], fbx.get("missing_materials"))
        add("fbx_missing_textures", [], fbx.get("missing_textures", []))
        if expected.fbx_bounds_tolerance is not None:
            source_bounds = stats.get("bounds") or {}
            roundtrip_bounds = fbx_stats.get("bounds") or {}
            try:
                bound_delta = max(
                    abs(
                        float(source_bounds[side][axis])
                        - float(roundtrip_bounds[side][axis])
                    )
                    for side in ("min", "max")
                    for axis in range(3)
                )
            except (KeyError, TypeError, ValueError):
                bound_delta = None
            add(
                "fbx_bounds_delta",
                f"<={expected.fbx_bounds_tolerance}",
                bound_delta,
                isinstance(bound_delta, (int, float))
                and bound_delta <= expected.fbx_bounds_tolerance,
            )

    if "glb" in requested:
        glb = report.get("glb_roundtrip_validation") or {}
        glb_stats = report.get("glb_reimport_stats") or {}
        add("glb_roundtrip", True, glb.get("passed"))
        add("glb_polygons", expected.polygons, glb_stats.get("polygons"))
        if expected.glb_readback_vertices is not None:
            add(
                "glb_vertices",
                expected.glb_readback_vertices,
                glb_stats.get("vertices"),
            )
        if expected.glb_readback_polygons is not None:
            add(
                "glb_readback_polygons",
                expected.glb_readback_polygons,
                glb_stats.get("polygons"),
            )

    if not report.get("previews_skipped"):
        preview_paths = [
            *list((report.get("previews") or {}).values()),
            *list((report.get("fbx_reimport_previews") or {}).values()),
        ]
        expected_previews = 8 if "fbx" in requested else 4
        add(
            "preview_files",
            expected_previews,
            len(preview_paths),
            len(preview_paths) == expected_previews
            and all(Path(path).is_file() for path in preview_paths),
        )

    passed = all(item["passed"] for item in checks.values())
    result = {
        "passed": passed,
        "automated": True,
        "manual_visual_review": "not asserted by this validator",
        "checks": checks,
        "report": str(report_path),
    }
    (report_path.parent / "character_profile_regression.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not passed:
        raise ExportError(f"assembly does not match the verified {profile.name_en} baseline")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def serializable_profile(profile: CharacterProfile) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if dataclasses.is_dataclass(value):
            return {
                field.name: convert(getattr(value, field.name))
                for field in dataclasses.fields(value)
            }
        if isinstance(value, dict) or hasattr(value, "items"):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set, frozenset)):
            return [convert(item) for item in value]
        return value

    return convert(profile)


def write_delivery_files(
    output: Path, profile: CharacterProfile, plan: dict[str, Any],
    assets: dict[str, Any], report: Path | None,
) -> dict[str, Any]:
    stem = profile.name_en
    for generated_qa_file in (
        output / f"{stem}_Complete_Rigged.blend1",
        output / f"{stem}_FBX_Reimport_Validated.blend",
        output / f"{stem}_FBX_Reimport_Validated.blend1",
    ):
        generated_qa_file.unlink(missing_ok=True)
    export_record = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": serializable_profile(profile),
        "resolved_plan": plan,
        "assets": assets,
        "assembly_report": str(report) if report else None,
    }
    record_path = output / "export_character_manifest.json"
    record_path.write_text(
        json.dumps(export_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    command_arguments = [
        f'--character "{profile.name_en}"',
        f'--game "{plan["game"]}"',
        f'--output "{output}"',
        f'--gust-dir "{plan["gust_dir"]}"',
    ]
    if plan.get("blender"):
        command_arguments.append(f'--blender "{plan["blender"]}"')
    command_arguments.extend(
        f'--python-deps "{path}"' for path in plan.get("python_deps", [])
    )
    command_arguments.extend(
        f'--converter-deps "{path}"'
        for path in plan.get("converter_deps", [])
    )
    command_arguments.append('--formats "' + ",".join(plan["formats"]) + '"')
    if plan["assets_only"]:
        command_arguments.append("--assets-only")
    if plan.get("skip_previews"):
        command_arguments.append("--skip-previews")
    if plan.get("skip_fbx_roundtrip"):
        command_arguments.append("--skip-fbx-roundtrip")
    command_arguments.append("--resume")
    command = " `\n  ".join([
        "python scripts\\venusvacationprism\\export_character.py",
        *command_arguments,
    ])
    main_files = []
    if plan["assets_only"]:
        main_files.append("- `components/`：三组件原始资源、纹理、glTF 与验证报告。")
    else:
        if "blend" in plan["formats"]:
            main_files.append(
                f"- `{profile.name_en}_Complete_Rigged.blend`：推荐，使用中的贴图已打包。"
            )
        if "fbx" in plan["formats"]:
            main_files.append(
                f"- `{profile.name_en}_Complete_Rigged.fbx`：附材质映射、贴图和 Blender 重连脚本。"
            )
        if "glb" in plan["formats"]:
            main_files.append(
                f"- `{profile.name_en}_Complete_Rigged.glb`：单文件便携格式。"
            )
        main_files.append("- `components/`：原始五件套、逐槽纹理、glTF 与验证报告。")
        if not plan.get("skip_previews"):
            main_files.append("- `previews/`：正面、背面、右侧及头部预览。")
    main_files_text = "\n".join(main_files)
    limitations = "\n".join(f"- {item}" for item in profile.limitations)
    readme = f"""# {profile.name_en} ({profile.name_zh}) PRISM 完整模型

该目录由 `export_character.py` 从游戏原始 FDATA 自动生成。BODY、FACE、HAIR 保持 identity 对齐；没有平移、缩放、焊接或合并骨架。

## 主文件

{main_files_text}

实际生成格式：{', '.join(plan['formats']) if not plan['assets_only'] else 'components only'}

## 重新导出

```powershell
{command}
```

## 已知限制

{limitations}

`SHA256SUMS.txt` 与 `SHA256_MANIFEST.json` 可用于验证交付完整性。
"""
    (output / "README.md").write_text(readme, encoding="utf-8")

    excluded = {"SHA256SUMS.txt", "SHA256_MANIFEST.json"}
    files = sorted(
        path for path in output.rglob("*")
        if path.is_file()
        and path.name not in excluded
        and not path.name.lower().endswith(".blend1")
        and "fbx_reimport_validated.blend" not in path.name.lower()
    )
    rows = []
    for path in files:
        rows.append({
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    sums_path = output / "SHA256SUMS.txt"
    sums_path.write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in rows),
        encoding="utf-8",
    )
    manifest = {
        "schema": 1,
        "algorithm": "SHA-256",
        "payload_file_count": len(rows),
        "payload_total_bytes": sum(row["bytes"] for row in rows),
        "verification_passed": True,
        "sha256sums_sha256": sha256(sums_path),
        "files": rows,
    }
    manifest_path = output / "SHA256_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "output": str(output),
        "payload_files": len(rows),
        "payload_bytes": manifest["payload_total_bytes"],
        "sha256_manifest": str(manifest_path),
    }


def print_character_list() -> None:
    rows = []
    for profile in CHARACTER_PROFILES.values():
        rows.append({
            "name": profile.name_en,
            "name_zh": profile.name_zh,
            "code": profile.code,
            "support": profile.support_level,
            "automated_export": profile.automated_export_enabled,
            "aliases": list(profile.aliases),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def main() -> int:
    args = parser().parse_args()
    if args.list_characters:
        print_character_list()
        return 0
    if not args.character:
        parser().error("--character/--name is required unless --list-characters is used")
    try:
        profile = get_character_profile(args.character)
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}") from exc
    if not profile.automated_export_enabled:
        details = " ".join(profile.limitations)
        raise SystemExit(
            f"error: {profile.name_en} is recorded as {profile.support_level}, not yet "
            f"enabled for unattended export. {details}"
        )
    try:
        plan = resolved_plan(args, profile)
        if args.plan:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        output = Path(plan["output"])
        ensure_output_state(output, args.resume)
        claim_output_directory(output, profile, plan, args.resume)
        python_deps = tuple(Path(value) for value in plan["python_deps"])
        converter_deps = tuple(Path(value) for value in plan["converter_deps"])
        add_python_paths(python_deps)
        from character_assets import export_profile_assets

        assets = export_profile_assets(
            profile=profile,
            game=Path(plan["game"]),
            output=output / "components",
            gust_dir=Path(plan["gust_dir"]),
            converter_deps=converter_deps,
            python_deps=python_deps,
            resume=args.resume,
        )
        report = None
        regression = None
        if not args.assets_only:
            report = run_blender(plan=plan, profile=profile, assets=assets, args=args)
            regression = validate_baseline(profile, report)
        delivery = write_delivery_files(output, profile, plan, assets, report)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise SystemExit(f"error: {exc}") from exc
    print(json.dumps({
        "character": profile.name_en,
        "character_zh": profile.name_zh,
        "components": assets,
        "profile_regression": regression,
        "delivery": delivery,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
