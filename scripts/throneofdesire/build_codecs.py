#!/usr/bin/env python3
"""Download official codec sources and build the two extraction helpers.

Windows uses the existing WSL g++ toolchain.  The generated executables are
Linux binaries invoked through ``wsl.exe`` by the export scripts.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LZHAM_URL = "https://codeload.github.com/richgel999/lzham_codec/zip/refs/heads/master"
ETCPACK_URL = "https://codeload.github.com/Ericsson/ETCPACK/zip/refs/heads/master"


def download_extract(url: str, archive: Path, destination: Path) -> Path:
    if not destination.is_dir():
        archive.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {url}", flush=True)
        urllib.request.urlretrieve(url, archive)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source:
            source.extractall(destination.parent)
    if not destination.is_dir():
        raise FileNotFoundError(f"Expected extracted source directory: {destination}")
    return destination


def windows_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        raise ValueError(f"WSL path must be drive-qualified: {resolved}")
    return f"/mnt/{drive}/{resolved.as_posix()[3:]}"


def compiler_command(paths: list[Path | str]) -> list[str]:
    if os.name != "nt":
        return [str(value) for value in paths]
    converted = [windows_to_wsl(value) if isinstance(value, Path) else value for value in paths]
    return ["wsl.exe", *converted]


def run(command: list[str], label: str) -> None:
    print(f"[{label}] {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".tmp")
    args = parser.parse_args()
    output = args.output.resolve()
    sources = output / "codec_sources"
    try:
        lzham = download_extract(
            LZHAM_URL,
            sources / "lzham_codec.zip",
            sources / "lzham_codec-master",
        )
        etcpack = download_extract(
            ETCPACK_URL,
            sources / "etcpack.zip",
            sources / "ETCPACK-master",
        )
        lzham_output = output / "lzham_v1_decode_raw"
        etc_output = output / "etc_dds_decode"
        lzham_sources = sorted((lzham / "lzhamdecomp").glob("*.cpp"))
        if not lzham_sources:
            raise FileNotFoundError("lzhamdecomp sources were not found")
        run(
            compiler_command(
                [
                    "g++",
                    "-std=gnu++11",
                    "-O2",
                    "-fno-strict-aliasing",
                    "-include",
                    "cstdint",
                    "-DNDEBUG",
                    "-D_LARGEFILE64_SOURCE=1",
                    "-D_FILE_OFFSET_BITS=64",
                    f"-I{windows_to_wsl(lzham / 'include') if os.name == 'nt' else lzham / 'include'}",
                    f"-I{windows_to_wsl(lzham / 'lzhamdecomp') if os.name == 'nt' else lzham / 'lzhamdecomp'}",
                    *lzham_sources,
                    SCRIPT_DIR / "lzham_alpha_decode.cpp",
                    "-o",
                    lzham_output,
                ]
            ),
            "build LZHAM decoder",
        )
        run(
            compiler_command(
                [
                    "g++",
                    "-std=gnu++11",
                    "-O2",
                    "-fno-strict-aliasing",
                    etcpack / "source" / "etcdec.cxx",
                    SCRIPT_DIR / "etc_dds_decode.cpp",
                    "-o",
                    etc_output,
                ]
            ),
            "build ETC DDS decoder",
        )
        print(f"LZHAM decoder: {lzham_output}")
        print(f"ETC DDS decoder: {etc_output}")
        return 0
    except (FileNotFoundError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
