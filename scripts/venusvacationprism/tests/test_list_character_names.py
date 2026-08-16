from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from list_character_names import character_rows, render_text  # noqa: E402


class CharacterNameListTests(unittest.TestCase):
    def test_exportable_filter_lists_only_honoka_and_nanami(self) -> None:
        rows = character_rows(exportable_only=True)
        self.assertEqual({row["name"] for row in rows}, {"Honoka", "Nanami"})
        self.assertTrue(all(row["automated_export"] for row in rows))

    def test_all_names_include_status_and_component_details(self) -> None:
        rows = character_rows()
        self.assertEqual(
            {row["name"] for row in rows},
            {"Misaki", "Elise", "Honoka", "Nanami"},
        )
        nanami = next(row for row in rows if row["name"] == "Nanami")
        self.assertEqual(nanami["accepted_names"], ["Nanami", "七海", "NNM"])
        self.assertEqual(nanami["default_components"]["body"]["model_index"], 722)
        json.dumps(rows, ensure_ascii=False)

    def test_text_output_is_directly_actionable(self) -> None:
        rendered = render_text(character_rows(), details=True)
        self.assertIn("Honoka / 穗香 / HON", rendered)
        self.assertIn("Nanami / 七海 / NNM", rendered)
        self.assertIn("BODY: index 722, 0x4a842a7d", rendered)
        self.assertIn("暂未开放", rendered)


if __name__ == "__main__":
    unittest.main()
