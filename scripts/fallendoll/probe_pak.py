#!/usr/bin/env python3
"""Read-only probe for the Operation LOVECRAFT: Fallen Doll UE4 pak.

Fallen Doll (project name ``Paralogue``) ships a single large
``Paralogue-WindowsNoEditor.pak``.  This script inspects the pak footer to
report the pak version, whether the file index is AES-encrypted, and the
index location/size, without decrypting anything.  It never needs, stores, or
prints an AES key.

Use it to confirm what an extractor (FModel/CUE4Parse or UnrealPak) has to be
told before it can list or export assets.

Example::

    python scripts/fallendoll/probe_pak.py \
        --game "D:/Program Files (x86)/Steam/steamapps/common/Operation Lovecraft Fallen Doll Demo"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys


PAK_MAGIC = 0x5A6F12E1

# UE4 pak versions relevant to this era.  v8 == 4.22-4.25, v9 introduces the
# relative-index/"frozen" layout used around 4.25-4.26.
PAK_VERSION_HINTS = {
    8: "UE4.22-4.25",
    9: "UE4.25-4.26 (relative/frozen index)",
    10: "UE4.26+",
    11: "UE4.27+",
}

DESKTOP_PAK = (
    "Desktop/WindowsNoEditor/Paralogue/Content/Paks/"
    "Paralogue-WindowsNoEditor.pak"
)
VR_PAK = (
    "VR/WindowsNoEditor/Paralogue/Content/Paks/"
    "Paralogue-WindowsNoEditor.pak"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game", type=Path,
        default=Path(r"D:\Program Files (x86)\Steam\steamapps\common"
                     r"\Operation Lovecraft Fallen Doll Demo"),
        help="Game install root (contains Desktop\\ and VR\\).")
    parser.add_argument(
        "--pak", type=Path,
        help="Probe a specific .pak instead of the known Desktop/VR paks.")
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the report as JSON only.")
    return parser.parse_args()


def find_paks(game_root: Path, explicit: Path | None) -> list[Path]:
    if explicit:
        return [explicit]
    found = []
    for relative in (DESKTOP_PAK, VR_PAK):
        candidate = game_root / relative
        if candidate.is_file():
            found.append(candidate)
    return found


def probe_footer(path: Path) -> dict:
    """Parse the pak footer.

    The footer is a fixed trailer at the end of the file.  We scan the last
    64 KiB for the magic to stay robust across the small footer-size
    differences between pak versions, then read the fields immediately around
    it: magic, version (u32), index offset (s64), index size (s64).  The
    encryption flag is the single byte directly before the magic.
    """
    size = path.stat().st_size
    tail_window = min(size, 65536)
    with open(path, "rb") as handle:
        handle.seek(size - tail_window)
        tail = handle.read(tail_window)

    magic_bytes = struct.pack("<I", PAK_MAGIC)
    position = tail.rfind(magic_bytes)
    if position < 0:
        raise RuntimeError(
            "pak magic 0x%08X not found in footer of %s" % (PAK_MAGIC, path))

    version = struct.unpack("<I", tail[position + 4:position + 8])[0]
    index_offset, index_size = struct.unpack(
        "<qq", tail[position + 8:position + 24])
    encrypted_flag = tail[position - 1] if position >= 1 else None

    # Sanity-read the first bytes of the index to corroborate the flag: an
    # unencrypted index begins with a small mount-point string length, an
    # encrypted one is high-entropy.
    index_head = b""
    entropy_distinct = None
    if 0 <= index_offset < size:
        with open(path, "rb") as handle:
            handle.seek(index_offset)
            index_head = handle.read(64)
        entropy_distinct = len(set(index_head))

    return {
        "pak": str(path),
        "file_bytes": size,
        "pak_version": version,
        "engine_hint": PAK_VERSION_HINTS.get(version, "unknown"),
        "index_offset": index_offset,
        "index_size": index_size,
        "index_encrypted": bool(encrypted_flag),
        "index_encrypted_flag_byte": encrypted_flag,
        "index_head_distinct_bytes": entropy_distinct,
        "index_head_hex": index_head[:32].hex(),
    }


def render_human(report: dict) -> str:
    lines = [
        "pak:               %s" % report["pak"],
        "size:              %.2f GiB (%d bytes)" % (
            report["file_bytes"] / (1024 ** 3), report["file_bytes"]),
        "pak version:       %d  (%s)" % (
            report["pak_version"], report["engine_hint"]),
        "index offset/size: %d / %d bytes" % (
            report["index_offset"], report["index_size"]),
        "index encrypted:   %s" % (
            "YES - AES key required" if report["index_encrypted"] else "no"),
    ]
    distinct = report["index_head_distinct_bytes"]
    if distinct is not None:
        lines.append(
            "index head:        %d/64 distinct bytes (%s)" % (
                distinct,
                "high entropy, consistent with encryption" if distinct > 40
                else "low entropy, consistent with plaintext"))
    if report["index_encrypted"]:
        lines.append(
            "next step:         configure the AES key in FModel/CUE4Parse or "
            "UnrealPak before listing/exporting assets")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    paks = find_paks(args.game, args.pak)
    if not paks:
        print("No Fallen Doll pak found under: %s" % args.game, file=sys.stderr)
        print("  expected: %s" % DESKTOP_PAK, file=sys.stderr)
        return 1

    reports = [probe_footer(path) for path in paks]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            print(render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
