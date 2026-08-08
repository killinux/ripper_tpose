from __future__ import annotations

import struct
import sys
import unittest
import zlib
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from prism_rdb import (  # noqa: E402
    FDATA_MAGIC,
    G1M_TYPE,
    PRISM_BLOCK_ZLIB,
    RDB_ENTRY_MAGIC,
    PrismArchiveError,
    decompress_prism_blocks,
    iter_fdata_entries,
    parse_g1m_metadata,
    read_asset,
)


def encode_prism_blocks(data: bytes) -> bytes:
    output = bytearray()
    for offset in range(0, len(data), 0x4000):
        compressed = zlib.compress(data[offset:offset + 0x4000])
        output.extend(struct.pack("<H8x", len(compressed)))
        output.extend(compressed)
    output.extend(b"\0" * 16)
    return bytes(output)


def make_g1m(joint_count: int = 64) -> bytes:
    skeleton = struct.pack(
        "<4s4sI2I4H", b"SM1G", b"2300", 28, 0, 0,
        joint_count, joint_count, 0, 0)
    size = 24 + len(skeleton)
    header = struct.pack("<4s4s4I", b"_M1G", b"9300", size, 24, 0, 1)
    return header + skeleton


class PrismBlockTests(unittest.TestCase):
    def test_decodes_multiple_blocks_and_zero_padding(self) -> None:
        original = bytes(range(256)) * 200
        encoded = encode_prism_blocks(original)
        self.assertEqual(
            decompress_prism_blocks(encoded, expected_size=len(original)), original)

    def test_rejects_wrong_expected_size(self) -> None:
        with self.assertRaisesRegex(PrismArchiveError, "Decoded size mismatch"):
            decompress_prism_blocks(encode_prism_blocks(b"test"), expected_size=5)

    def test_rejects_nonzero_trailing_data(self) -> None:
        encoded = encode_prism_blocks(b"test") + b"x"
        with self.assertRaisesRegex(PrismArchiveError, "non-zero bytes"):
            decompress_prism_blocks(encoded)


class G1MMetadataTests(unittest.TestCase):
    def test_reads_skeleton_and_character_category(self) -> None:
        metadata = parse_g1m_metadata(make_g1m(64))
        self.assertEqual(metadata["version"], "9300")
        self.assertEqual(metadata["skeleton_joints"], 64)
        self.assertEqual(metadata["category"], "character_candidate")
        self.assertEqual(metadata["chunks"][0]["magic"], "SM1G")

    def test_rejects_invalid_magic(self) -> None:
        with self.assertRaisesRegex(PrismArchiveError, "Invalid G1M magic"):
            parse_g1m_metadata(b"NOPE" + b"\0" * 48)


class FdataTests(unittest.TestCase):
    def test_indexes_and_reads_compressed_entry(self) -> None:
        original = make_g1m()
        payload = encode_prism_blocks(original)
        entry_size = 48 + len(payload)
        package_header = struct.pack("<4I", FDATA_MAGIC, 0, 16, 0)
        entry_header = struct.pack(
            "<IIqqqIIII", RDB_ENTRY_MAGIC, 1, entry_size, len(payload),
            len(original), 0, 0x12345678, G1M_TYPE, PRISM_BLOCK_ZLIB)

        # Use a direct workspace fixture: TemporaryDirectory can acquire an
        # unusable ACL in some Windows workspace sandboxes.
        package = SCRIPT_DIR / "tests" / "0x01020304.fdata"
        package.unlink(missing_ok=True)
        self.addCleanup(package.unlink, missing_ok=True)
        try:
            package.write_bytes(package_header + entry_header + payload)
            entries = list(iter_fdata_entries(package))
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].file_id, 0x12345678)
            self.assertEqual(entries[0].suggested_name, "0x12345678.g1m")
            self.assertEqual(read_asset(entries[0]), original)
        finally:
            package.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
