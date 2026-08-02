"""Import an FModel UEFormat model in Blender 3.6 without installing an add-on.

The official UEFormat Blender package currently declares Blender 4.x.  Its
version-9 model reader still works in Blender 3.6 after guarding the Blender 4
bone-colour API.  This bridge loads that reader directly from a source checkout
and is intended for repeatable validation jobs, not global add-on installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="io_scene_ueformat directory")
    parser.add_argument("--input", required=True, help="input .uemodel")
    parser.add_argument("--output", required=True, help="output .blend")
    parser.add_argument("--report", required=True, help="output JSON report")
    parser.add_argument("--scale", type=float, default=0.01)
    return parser.parse_args(argv)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def load_importer(source: str):
    source_path = Path(source).resolve()
    required = source_path / "importer" / "logic.py"
    if not required.is_file():
        raise RuntimeError(f"UEFormat source is incomplete: {required}")

    package = types.ModuleType("io_scene_ueformat")
    package.__path__ = [str(source_path)]
    package.__package__ = "io_scene_ueformat"
    sys.modules[package.__package__] = package

    importer_package = types.ModuleType("io_scene_ueformat.importer")
    importer_package.__path__ = [str(source_path / "importer")]
    importer_package.__package__ = "io_scene_ueformat.importer"
    sys.modules[importer_package.__package__] = importer_package

    from io_scene_ueformat.importer.logic import UEFormatImport
    from io_scene_ueformat.options import UEModelOptions

    return UEFormatImport, UEModelOptions


def main() -> None:
    args = parse_args()
    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        raise RuntimeError(f"UEFormat file does not exist: {input_path}")

    clear_scene()
    importer_type, options_type = load_importer(args.source)
    options = options_type(
        link=True,
        scale_factor=args.scale,
        bone_length=4.0,
        reorient_bones=False,
        import_collision=False,
        import_sockets=False,
        import_morph_targets=True,
        import_virtual_bones=False,
        target_lod=0,
    )
    imported_object, model = importer_type(options).import_file(input_path)

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError("UEFormat import did not create both mesh and armature")

    mesh = meshes[0]
    mesh.name = "Eve_Head_UEFormat_Mesh"
    armatures[0].name = "Eve_Head_UEFormat_Armature"
    shape_keys = (
        [key.name for key in mesh.data.shape_keys.key_blocks]
        if mesh.data.shape_keys
        else []
    )
    source_morphs = [morph.name for morph in model.lods[0].morphs]
    if len(source_morphs) != 53 or len(shape_keys) != 54:
        raise RuntimeError(
            f"Expected 53 source morphs and 54 Blender shape keys; "
            f"got {len(source_morphs)} and {len(shape_keys)}"
        )

    report = {
        "blender_version": bpy.app.version_string,
        "input": input_path,
        "input_size": os.path.getsize(input_path),
        "input_sha256": sha256(input_path),
        "mesh": mesh.name,
        "vertices": len(mesh.data.vertices),
        "polygons": len(mesh.data.polygons),
        "materials": [slot.name for slot in mesh.data.materials],
        "armature": armatures[0].name,
        "bones": len(armatures[0].data.bones),
        "source_morph_count": len(source_morphs),
        "shape_key_count": len(shape_keys),
        "shape_keys": shape_keys,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.output))
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
