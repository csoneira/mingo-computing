"""Test independent completed-file and unprocessed-file reprocessing options."""

import unittest

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import resolve_reprocessing_options


class ReprocessingOptionTests(unittest.TestCase):
    def test_both_options_default_off(self):
        messages = []
        self.assertEqual(resolve_reprocessing_options({}, log_fn=messages.append), (False, False))
        self.assertIn("reprocess_from_completed=False", messages[-1])

    def test_completed_reprocessing_does_not_force_unprocessed(self):
        self.assertEqual(
            resolve_reprocessing_options({"reprocess_from_completed": True}, log_fn=lambda _: None),
            (True, False),
        )

    def test_forced_unprocessed_does_not_enable_completed_reprocessing(self):
        self.assertEqual(
            resolve_reprocessing_options({"reprocess_from_unprocessed": True}, log_fn=lambda _: None),
            (False, True),
        )

    def test_legacy_fallback_only_controls_completed_mode(self):
        messages = []
        self.assertEqual(
            resolve_reprocessing_options({"complete_reanalysis": True}, log_fn=messages.append),
            (True, False),
        )
        self.assertTrue(any("DEPRECATED_CONFIG" in message for message in messages))

    def test_explicit_new_key_overrides_legacy(self):
        messages = []
        self.assertEqual(
            resolve_reprocessing_options(
                {"complete_reanalysis": True, "reprocess_from_completed": False},
                log_fn=messages.append,
            ),
            (False, False),
        )
        self.assertFalse(any("DEPRECATED_CONFIG" in message for message in messages))


if __name__ == "__main__":
    unittest.main()

class AtomicParquetWriteTests(unittest.TestCase):
    def test_failed_write_keeps_previous_output(self):
        import tempfile
        from pathlib import Path

        from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import atomic_write_parquet

        class FailingFrame:
            def to_parquet(self, path, **kwargs):
                Path(path).write_bytes(b"partial replacement")
                raise RuntimeError("simulated parquet failure")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.parquet"
            destination.write_bytes(b"valid previous output")
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                atomic_write_parquet(FailingFrame(), destination)
            self.assertEqual(destination.read_bytes(), b"valid previous output")
            self.assertEqual(list(Path(directory).glob(".*.parquet")), [])

class ExistingOutputSelectionTests(unittest.TestCase):
    def test_unprocessed_output_duplicates_are_blocked_by_default(self):
        import tempfile
        from pathlib import Path

        from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import filter_unprocessed_with_existing_outputs

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "cleaned_run-a.parquet").write_bytes(b"existing")
            candidates = ["raw_run-a.parquet", "raw_run-b.parquet"]
            self.assertEqual(
                filter_unprocessed_with_existing_outputs(
                    candidates, output, input_prefix="raw_", output_prefix="cleaned_", force_reprocess=False
                ),
                ["raw_run-b.parquet"],
            )

    def test_forced_mode_allows_matching_unprocessed_output(self):
        import tempfile
        from pathlib import Path

        from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import filter_unprocessed_with_existing_outputs

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "cleaned_run-a.parquet").write_bytes(b"existing")
            candidates = ["raw_run-a.parquet"]
            self.assertEqual(
                filter_unprocessed_with_existing_outputs(
                    candidates, output, input_prefix="raw_", output_prefix="cleaned_", force_reprocess=True
                ),
                candidates,
            )
