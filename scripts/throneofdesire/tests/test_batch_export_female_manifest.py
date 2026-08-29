"""Manifest-merge tests for batch_export_female.py.

Pure python (no game data, no Blender): a ``--models`` subset run must keep
the previously recorded exports in female_export_manifest.json instead of
rewriting the manifest with only the requested models.
"""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


def load_module():
    path = Path(__file__).resolve().parents[1] / "batch_export_female.py"
    spec = importlib.util.spec_from_file_location(
        "batch_export_female_under_test", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def record(model, status="complete", size=1):
    return {"model": model, "status": status, "bytes": size}


class ManifestMergeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def read_manifest(self):
        path = self.root / "female_export_manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_no_previous_manifest(self):
        self.assertEqual(
            MODULE.load_preserved_records(self.root, {"h005"}), [])

    def test_subset_run_preserves_other_records(self):
        MODULE.write_manifest(
            self.root, [record("h005"), record("h006"), record("h020")])
        preserved = MODULE.load_preserved_records(self.root, {"h006"})
        self.assertEqual([item["model"] for item in preserved],
                         ["h005", "h020"])

        MODULE.write_manifest(
            self.root, [record("h006", status="failed")], preserved)
        manifest = self.read_manifest()
        self.assertEqual([item["model"] for item in manifest["records"]],
                         ["h005", "h006", "h020"])
        self.assertEqual(manifest["requested_models"], ["h006"])
        self.assertEqual(manifest["complete_count"], 2)
        self.assertEqual(manifest["failed_count"], 1)

    def test_incremental_writes_are_idempotent(self):
        MODULE.write_manifest(self.root, [record("h005"), record("h020")])
        preserved = MODULE.load_preserved_records(self.root, {"h005"})
        # The batch loop rewrites the manifest after every model; repeated
        # writes with the same preserved list must not duplicate records.
        for _ in range(3):
            MODULE.write_manifest(self.root, [record("h005")], preserved)
        manifest = self.read_manifest()
        self.assertEqual([item["model"] for item in manifest["records"]],
                         ["h005", "h020"])

    def test_records_follow_canonical_order(self):
        MODULE.write_manifest(self.root, [record("h999"), record("h005")])
        manifest = self.read_manifest()
        self.assertEqual([item["model"] for item in manifest["records"]],
                         ["h005", "h999"])

    def test_corrupt_manifest_is_ignored(self):
        (self.root / "female_export_manifest.json").write_text(
            "{not json", encoding="utf-8")
        self.assertEqual(
            MODULE.load_preserved_records(self.root, {"h005"}), [])


if __name__ == "__main__":
    unittest.main()
