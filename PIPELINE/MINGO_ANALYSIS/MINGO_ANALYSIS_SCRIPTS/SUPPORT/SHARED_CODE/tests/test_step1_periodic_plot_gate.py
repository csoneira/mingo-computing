"""Test step1 periodic plot gate behavior."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE import step1_shared


class Step1PeriodicPlotGateTests(unittest.TestCase):
    def test_resolve_plot_options_uses_discovered_repo_root_for_schedule(self) -> None:
        with tempfile.TemporaryDirectory(prefix="step1-plot-gate-") as temp:
            root = Path(temp)
            config = {
                "_plot_station_id": "test",
                "_plot_task_number": 2,
                "periodic_plotting_interval_hours": 24,
                "create_plots": "none",
            }

            with patch.object(step1_shared, "get_repo_root", return_value=root):
                options = step1_shared.resolve_step1_plot_options(config)

            schedule = (
                root
                / "CONTEXTUAL" / "OPERATIONS"
                / "OPERATIONS_RUNTIME"
                / "PLOT_SCHEDULE"
                / "stage1_station_test_task_2.timestamp"
            )
            self.assertEqual(options[0], "usual")
            self.assertTrue(config["_periodic_plot_due"])
            self.assertTrue(schedule.is_file())


if __name__ == "__main__":
    unittest.main()
