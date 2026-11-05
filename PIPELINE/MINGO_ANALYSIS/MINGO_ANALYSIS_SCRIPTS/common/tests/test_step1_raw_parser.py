from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import (
    build_step1_raw_input_dataframe,
)


class Step1RawParserTests(unittest.TestCase):
    def test_unparseable_numeric_field_is_rejected_without_aborting_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="step1-raw-parser-") as temp:
            source = Path(temp) / "input.dat"
            rejected = Path(temp) / "rejected.txt"
            source.write_text("2026 10 21 12 0 0 1 invalid\n", encoding="utf-8")

            dataframe, read_lines, written_lines = build_step1_raw_input_dataframe(
                source,
                rejected,
                expected_columns=8,
            )

            self.assertTrue(dataframe.empty)
            self.assertEqual(read_lines, 1)
            self.assertEqual(written_lines, 0)
            self.assertIn("Line 1 (Malformed numeric data)", rejected.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
