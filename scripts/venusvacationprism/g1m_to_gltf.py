#!/usr/bin/env python3
"""Convert a PRISM G1M to glTF with the required Gust compatibility fixes.

The upstream ``eArmada8/gust_stuff`` converter is intentionally kept as an
external dependency.  This wrapper executes it in-process so it can:

* accept both an unmodified converter and the locally patched PRISM variant;
* retain ordinary homogeneous ``POSITION`` VEC4 surfaces (notably faces);
* force every emitted glTF ``POSITION`` accessor to VEC3;
* replace three quadratic/immutable-buffer hot paths used by NUN cloth; and
* validate the external glTF buffer before returning success.

No file below ``gust_dir`` is edited.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


CONVERTER_NAME = "g1m_to_basic_gltf.py"
REQUIRED_GUST_FILES = (
    CONVERTER_NAME,
    "g1m_export_meshes.py",
    "g1m_import_meshes.py",
    "lib_fmtibvb.py",
)


class G1MConversionError(RuntimeError):
    """Raised when Gust cannot produce a structurally usable glTF."""


@dataclass(frozen=True)
class ConversionResult:
    g1m: Path
    gltf: Path
    buffer: Path
    log: Path
    converter_sha256: str
    prism_vec4_patch: str
    oid: Path | None
    validation: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "g1m": str(self.g1m),
            "gltf": str(self.gltf),
            "buffer": str(self.buffer),
            "log": str(self.log),
            "converter_sha256": self.converter_sha256,
            "prism_vec4_patch": self.prism_vec4_patch,
            "oid": str(self.oid) if self.oid else None,
            "validation": self.validation,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prepend_import_paths(paths: Iterable[Path]) -> list[str]:
    added: list[str] = []
    for path in reversed([Path(item).expanduser().resolve() for item in paths]):
        rendered = str(path)
        if rendered not in sys.path:
            sys.path.insert(0, rendered)
            added.append(rendered)
    return added


def _remove_import_paths(paths: Iterable[str]) -> None:
    for path in paths:
        with contextlib.suppress(ValueError):
            sys.path.remove(path)


def _converter_has_prism_patch(source: str) -> bool:
    """Recognize the patch used during the verified Honoka/Nanami exports."""

    return all(
        marker in source
        for marker in (
            "position_components",
            "position_components == 4 and submesh_lod['clothID'] == 0",
            "if len(submesh['vb'][position_index]['Buffer'][0]) == 4:",
            "submesh['fmt']['elements'][position_index]['Format'] = 'R32G32B32_FLOAT'",
        )
    )


def _patch_prism_vec4(source: str) -> tuple[str, str]:
    """Return a converter source compatible with PRISM homogeneous positions.

    Gust historically classified every four-component POSITION as NUN cloth.
    PRISM also stores regular face/static positions as XYZW with W=1.  The
    first replacement lets those clothID=0 surfaces through; the second clips
    any remaining fourth component immediately before glTF format generation.
    Anchor checks deliberately fail closed when upstream changes materially.
    """

    if _converter_has_prism_patch(source):
        compile(source, CONVERTER_NAME, "exec")
        return source, "present"

    primitive_marker = '            primitive = {"attributes":{}}'
    position_start = source.find("        position_format = ")
    primitive_start = source.find(primitive_marker, position_start)
    if position_start < 0 or primitive_start < 0:
        raise G1MConversionError(
            "Unsupported Gust converter: POSITION/primitive anchors changed"
        )

    replacement = """        position_format = [
            x for x in fmts[subvbs['data'][subindex]['vertexBufferIndex']]['elements']
            if x['SemanticName'] == 'POSITION'
        ][0]['Format']
        position_components = len(re.findall('[0-9]+', position_format))
        # PRISM also stores ordinary homogeneous XYZW positions.  Only a
        # non-zero cloth ID makes four components a cloth-transform signal.
        if position_components == 3 \\
            or (position_components == 4 and submesh_lod['clothID'] == 0) \\
            or not nun_maps == False:
"""
    source = source[:position_start] + replacement + source[primitive_start:]

    normal_marker = (
        "                submesh = fix_normal_type(submesh) # Needed for normals "
        "stored as VEC4 with an empty 4th value - not \"4D\" cloth meshes\n"
    )
    if normal_marker not in source:
        # Permit harmless whitespace/comment drift but still anchor to the
        # exact operation that must precede format conversion.
        match = re.search(
            r"(?m)^(?P<indent>\s*)submesh\s*=\s*fix_normal_type\(submesh\).*$",
            source,
        )
        if not match:
            raise G1MConversionError(
                "Unsupported Gust converter: fix_normal_type anchor changed"
            )
        insertion_at = source.find("\n", match.end()) + 1
        indent = match.group("indent")
    else:
        insertion_at = source.index(normal_marker) + len(normal_marker)
        indent = "                "

    vec3_fix = f"""{indent}# PRISM compatibility: glTF POSITION must always be VEC3.
{indent}position_index = [
{indent}    x['SemanticName'] for x in submesh['fmt']['elements']
{indent}].index('POSITION')
{indent}if len(submesh['vb'][position_index]['Buffer'][0]) == 4:
{indent}    submesh['vb'][position_index]['Buffer'] = [
{indent}        list(position[:3])
{indent}        for position in submesh['vb'][position_index]['Buffer']
{indent}    ]
{indent}    submesh['fmt']['elements'][position_index]['Format'] = 'R32G32B32_FLOAT'
"""
    source = source[:insertion_at] + vec3_fix + source[insertion_at:]
    if not _converter_has_prism_patch(source):
        raise G1MConversionError("Failed to apply the PRISM POSITION VEC4 patch")
    compile(source, CONVERTER_NAME, "exec")
    return source, "applied_in_memory"


def _install_fast_cloth_helpers(gust_dir: Path):
    """Install output-equivalent accelerators used for the Nanami full cloth run."""

    import numpy  # Imported after caller-provided dependency paths are active.

    meshes = importlib.import_module("g1m_export_meshes")
    quaternion = meshes.Quaternion
    lookup_cache: dict[int, dict[int, tuple[object, object]]] = {}

    def cached_center_of_mass(position, weights, bones, nuno_map, transform_info):
        cache_key = id(transform_info)
        transforms = lookup_cache.get(cache_key)
        if transforms is None:
            transforms = {
                int(item["bone_name"].split("_")[-1]): (
                    quaternion(item["abs_q"]),
                    numpy.asarray(item["abs_p"]),
                )
                for item in transform_info
            }
            lookup_cache[cache_key] = transforms
        result = numpy.zeros(3)
        for lane, local_bone in enumerate(bones):
            rotation, translation = transforms[int(nuno_map[local_bone])]
            result += rotation.rotate(position) + translation * weights[lane]
        return result

    def fast_cull_vb(submesh):
        active = {index for triangle in submesh["ib"] for index in triangle}
        new_vb = [
            {
                "SemanticName": item["SemanticName"],
                "SemanticIndex": item["SemanticIndex"],
                "Buffer": [],
            }
            for item in submesh["vb"]
        ]
        remap: dict[int, int] = {}
        for source_index in range(len(submesh["vb"][0]["Buffer"])):
            if source_index not in active:
                continue
            remap[source_index] = len(remap)
            for attribute_index, attribute in enumerate(submesh["vb"]):
                new_vb[attribute_index]["Buffer"].append(
                    attribute["Buffer"][source_index]
                )
        submesh["vb"] = new_vb
        for triangle in submesh["ib"]:
            for lane, value in enumerate(triangle):
                triangle[lane] = remap[value]
        return submesh

    def fast_generate_vb(index, g1mg_stream, model_mesh_metadata, fmts, e="<"):
        vertex_buffers = next(
            section
            for section in model_mesh_metadata["sections"]
            if section["type"] == "VERTEX_BUFFERS"
        )
        attributes = next(
            section
            for section in model_mesh_metadata["sections"]
            if section["type"] == "VERTEX_ATTRIBUTES"
        )
        if index not in range(len(fmts)):
            return None
        buffers = attributes["data"][index]["buffer_list"]
        primary = vertex_buffers["data"][buffers[0]]
        with io.BytesIO(g1mg_stream) as stream:
            if primary["count"] > 1:
                packed = bytearray()
                for vertex in range(primary["count"]):
                    for buffer_index in buffers:
                        item = vertex_buffers["data"][buffer_index]
                        source_vertex = (
                            vertex if vertex < item["count"] else vertex % item["count"]
                        )
                        stream.seek(item["offset"] + item["stride"] * source_vertex)
                        packed.extend(stream.read(item["stride"]))
                return meshes.read_vb_stream(bytes(packed), fmts[index], e)
            stream.seek(primary["offset"])
            return meshes.read_vb_stream(
                stream.read(primary["stride"] * primary["count"]), fmts[index], e
            )

    originals = {
        "computeCenterOfMass": meshes.computeCenterOfMass,
        "cull_vb": meshes.cull_vb,
        "generate_vb": meshes.generate_vb,
    }
    meshes.computeCenterOfMass = cached_center_of_mass
    meshes.cull_vb = fast_cull_vb
    meshes.generate_vb = fast_generate_vb
    return meshes, originals


def _restore_fast_cloth_helpers(state) -> None:
    if state is None:
        return
    module, originals = state
    for name, value in originals.items():
        setattr(module, name, value)


def validate_external_gltf(path: Path) -> dict[str, object]:
    """Perform the converter-level checks needed before material processing."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "asset_version": None,
            "meshes": 0,
            "skins": 0,
            "materials": 0,
            "images": 0,
            "position_accessors": 0,
            "position_accessors_all_vec3_float": False,
            "buffer": str(path.with_suffix(".bin")),
            "buffer_declared_bytes": None,
            "buffer_actual_bytes": None,
            "errors": [f"cannot read glTF JSON: {exc}"],
            "passed": False,
        }
    errors: list[str] = []
    if document.get("asset", {}).get("version") != "2.0":
        errors.append("asset.version is not 2.0")
    buffers = document.get("buffers", [])
    if len(buffers) != 1:
        errors.append(f"expected one external buffer, got {len(buffers)}")
        buffer_path = path.with_suffix(".bin")
    else:
        uri = buffers[0].get("uri")
        if not uri or str(uri).startswith("data:"):
            errors.append("converter did not emit one local external buffer")
            buffer_path = path.with_suffix(".bin")
        else:
            uri_path = Path(str(uri))
            if uri_path.is_absolute():
                errors.append("buffer URI must be relative")
            buffer_path = (path.parent / uri_path).resolve()
            try:
                buffer_path.relative_to(path.parent.resolve())
            except ValueError:
                errors.append("buffer URI escapes the output directory")
    actual_size = buffer_path.stat().st_size if buffer_path.is_file() else None
    declared_size = int(buffers[0].get("byteLength", -1)) if buffers else None
    if actual_size is None:
        errors.append(f"missing external buffer: {buffer_path}")
    elif actual_size != declared_size:
        errors.append(
            f"buffer size mismatch: declared {declared_size}, actual {actual_size}"
        )

    position_accessors: list[int] = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            index = primitive.get("attributes", {}).get("POSITION")
            if index is not None:
                position_accessors.append(int(index))
    bad_positions: list[int] = []
    accessors = document.get("accessors", [])
    for index in position_accessors:
        if not 0 <= index < len(accessors):
            errors.append(f"POSITION accessor is out of range: {index}")
            bad_positions.append(index)
        elif accessors[index].get("type") != "VEC3" or int(
            accessors[index].get("componentType", -1)
        ) != 5126:
            bad_positions.append(index)
    if not position_accessors:
        errors.append("glTF contains no POSITION accessors")
    if bad_positions:
        errors.append(f"non-VEC3 float POSITION accessors: {bad_positions[:16]}")
    return {
        "asset_version": document.get("asset", {}).get("version"),
        "meshes": len(document.get("meshes", [])),
        "skins": len(document.get("skins", [])),
        "materials": len(document.get("materials", [])),
        "images": len(document.get("images", [])),
        "position_accessors": len(position_accessors),
        "position_accessors_all_vec3_float": not bad_positions,
        "buffer": str(buffer_path),
        "buffer_declared_bytes": declared_size,
        "buffer_actual_bytes": actual_size,
        "errors": errors,
        "passed": not errors,
    }


def convert_g1m(
    g1m: Path,
    *,
    gust_dir: Path,
    dependency_paths: Sequence[Path] = (),
    output_stem: Path | None = None,
    oid_path: Path | None = None,
    fast_cloth: bool = True,
) -> ConversionResult:
    """Convert one G1M and return validated output paths.

    ``output_stem`` has no extension.  When supplied, the input G1M is copied
    there first so Gust still writes a conventional sibling ``.gltf/.bin``.
    """

    source_g1m = Path(g1m).expanduser().resolve()
    original_g1m = source_g1m
    if source_g1m.suffix.lower() != ".g1m" or not source_g1m.is_file():
        raise G1MConversionError(f"Input is not a readable .g1m: {source_g1m}")
    gust_dir = Path(gust_dir).expanduser().resolve()
    missing = [name for name in REQUIRED_GUST_FILES if not (gust_dir / name).is_file()]
    if missing:
        raise G1MConversionError(
            f"Gust directory is incomplete ({', '.join(missing)}): {gust_dir}"
        )
    if output_stem is None:
        stem = source_g1m.with_suffix("")
    else:
        stem = Path(output_stem).expanduser().resolve()
        stem.parent.mkdir(parents=True, exist_ok=True)
        target_g1m = stem.with_suffix(".g1m")
        if target_g1m != source_g1m:
            shutil.copy2(source_g1m, target_g1m)
        source_g1m = target_g1m

    resolved_oid = Path(oid_path).expanduser().resolve() if oid_path else None
    if resolved_oid is None:
        automatic_oid = original_g1m.with_suffix(".oid")
        if automatic_oid.is_file():
            resolved_oid = automatic_oid
    if resolved_oid is not None and not resolved_oid.is_file():
        raise G1MConversionError(f"OID is not a readable file: {resolved_oid}")
    gust_oid = stem.parent / f"{stem.name}Oid.bin"
    created_gust_oid = False

    converter_path = gust_dir / CONVERTER_NAME
    raw_source = converter_path.read_bytes()
    try:
        converter_source = raw_source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise G1MConversionError(f"Gust converter is not UTF-8: {converter_path}") from exc
    converter_source, patch_status = _patch_prism_vec4(converter_source)

    import_paths = [gust_dir, *(Path(item) for item in dependency_paths)]
    added = _prepend_import_paths(import_paths)
    old_cwd = Path.cwd()
    log_path = stem.with_suffix(".conversion.log")
    output = io.StringIO()
    fast_helper_state = None
    try:
        if resolved_oid is not None:
            if gust_oid.is_file():
                if gust_oid.read_bytes() != resolved_oid.read_bytes():
                    raise G1MConversionError(
                        f"existing Gust OID alias differs from requested OID: {gust_oid}"
                    )
            else:
                shutil.copy2(resolved_oid, gust_oid)
                created_gust_oid = True
        # Make repeated API calls deterministic when a caller switches Gust
        # directories in one Python process.
        for module_name in ("g1m_export_meshes", "g1m_import_meshes", "lib_fmtibvb"):
            module = sys.modules.get(module_name)
            module_file = Path(getattr(module, "__file__", "")).resolve() if module else None
            if module_file and gust_dir not in module_file.parents:
                del sys.modules[module_name]
        namespace = {
            "__name__": "prism_gust_converter",
            "__file__": str(converter_path),
        }
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exec(compile(converter_source, str(converter_path), "exec"), namespace)
            if fast_cloth:
                fast_helper_state = _install_fast_cloth_helpers(gust_dir)
            os.chdir(stem.parent)
            converted = namespace["G1M2glTF"](
                stem.name, overwrite=True, keep_color=False
            )
        if converted is False:
            raise G1MConversionError("Gust returned failure")
    except SystemExit as exc:
        log_path.write_text(output.getvalue(), encoding="utf-8")
        raise G1MConversionError(
            f"Gust exited during conversion of {source_g1m}; "
            f"see {log_path} (status {exc.code!r})"
        ) from exc
    except Exception as exc:
        log_path.write_text(output.getvalue(), encoding="utf-8")
        if isinstance(exc, G1MConversionError):
            raise
        raise G1MConversionError(
            f"Gust conversion failed for {source_g1m}; see {log_path}: {exc}"
        ) from exc
    finally:
        os.chdir(old_cwd)
        _restore_fast_cloth_helpers(fast_helper_state)
        _remove_import_paths(added)
        if created_gust_oid:
            with contextlib.suppress(OSError):
                gust_oid.unlink()

    log_path.write_text(output.getvalue(), encoding="utf-8")
    gltf_path = stem.with_suffix(".gltf")
    if not gltf_path.is_file():
        raise G1MConversionError(
            f"Gust returned success without creating {gltf_path}; see {log_path}"
        )
    validation = validate_external_gltf(gltf_path)
    if not validation["passed"]:
        raise G1MConversionError(
            f"Converted glTF validation failed: {validation['errors']}"
        )
    buffer_path = Path(str(validation["buffer"]))
    return ConversionResult(
        g1m=source_g1m,
        gltf=gltf_path,
        buffer=buffer_path,
        log=log_path,
        converter_sha256=_sha256(raw_source),
        prism_vec4_patch=patch_status,
        oid=resolved_oid,
        validation=validation,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("g1m", type=Path, help="Input G1M")
    parser.add_argument("--gust-dir", required=True, type=Path)
    parser.add_argument(
        "--deps",
        action="append",
        default=[],
        type=Path,
        help="Dependency directory (repeat for numpy/pyquaternion locations)",
    )
    parser.add_argument(
        "--oid",
        type=Path,
        help="Optional sibling OID resource used for Gust bone-name mapping",
    )
    parser.add_argument(
        "--output-stem",
        type=Path,
        help="Optional output path without extension; the G1M is copied there",
    )
    parser.add_argument("--no-fast-cloth", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = convert_g1m(
            args.g1m,
            gust_dir=args.gust_dir,
            dependency_paths=args.deps,
            output_stem=args.output_stem,
            oid_path=args.oid,
            fast_cloth=not args.no_fast_cloth,
        )
    except (OSError, G1MConversionError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    rendered = json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
