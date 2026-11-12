"""Test Task 2 runtime plot catalogue parsing and selection."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[6]
CONFIG_PATH = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
    / "SUPPORT" / "CONFIG_FILES"
    / "STAGE_1"
    / "EVENT_DATA"
    / "STEP_1"
    / "TASK_2"
    / "config_plots_task_2.yaml"
)
SCRIPT_PATH = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
    / "STAGES"
    / "STAGE_1"
    / "EVENT_DATA"
    / "COIN_TRIGGER"
    / "TASK_2"
    / "script_2_clean_to_cal.py"
)
class Task2PlotCatalogTests(unittest.TestCase):
    def test_catalog_uses_only_explicit_plot_and_not_plot_lists(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        self.assertEqual(set(config), {"-plot", "-not_plot"})
        enabled = config.get("-plot", []) or []
        disabled = config.get("-not_plot", []) or []
        self.assertEqual(len(enabled), len(set(enabled)))
        self.assertEqual(len(disabled), len(set(disabled)))
        self.assertFalse(set(enabled) & set(disabled))
        script_text = SCRIPT_PATH.read_text()
        self.assertIn("def task2_plot_requested", script_text)

    def test_slewing_observable_helpers_remain_available(self) -> None:
        script_text = SCRIPT_PATH.read_text()
        expected_snippets = [
            "TASK2_SLEWING_OBSERVABLE_ALIASES",
        ]

        for snippet in expected_snippets:
            self.assertIn(
                snippet,
                script_text,
                msg=(
                    "Task 2 dx diagnostics must participate in the shared "
                    "slewing-observable gate so essential mode can build them "
                    "even when slewing correction is disabled."
                ),
            )

        self.assertIn("task2_plot_requested", script_text)


if __name__ == "__main__":
    unittest.main()
