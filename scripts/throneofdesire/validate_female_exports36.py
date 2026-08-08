"""Reopen Throne of Desire female Blend/FBX exports in Blender 3.6."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bpy


DEFAULT_MODELS = (
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
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    return parser.parse_args(argv)


def validate_blend(path: Path) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    primary = [
        obj for obj in meshes if obj.get("xlegend_category") == "base"
    ]
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    packed_images = [image for image in bpy.data.images if image.packed_file]
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "meshes": len(meshes),
        "primary_meshes": len(primary),
        "armatures": len(armatures),
        "images": len(bpy.data.images),
        "packed_images": len(packed_images),
        "ok": bool(primary and armatures and packed_images),
    }


def validate_fbx(path: Path) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path), use_image_search=False)
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "meshes": len(meshes),
        "armatures": len(armatures),
        "ok": bool(meshes and armatures),
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    records = []
    for model in args.models:
        model = model.lower()
        model_dir = root / model
        blend_path = model_dir / f"{model}_blender36.blend"
        fbx_path = model_dir / f"{model}.fbx"
        record = {"model": model}
        try:
            record["blend"] = validate_blend(blend_path)
            record["fbx"] = validate_fbx(fbx_path)
            record["ok"] = record["blend"]["ok"] and record["fbx"]["ok"]
        except Exception as exc:  # Blender exceptions vary by operator.
            record["ok"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)
        print(f"{model}: {'ok' if record['ok'] else 'FAILED'}", flush=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "model_count": len(records),
        "passed": sum(record["ok"] for record in records),
        "failed": sum(not record["ok"] for record in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["failed"]:
        raise RuntimeError(f"{report['failed']} export(s) failed validation")


if __name__ == "__main__":
    main()
