from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
CONFIG_PATH = (
    REPO_ROOT
    / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
    / "CONFIG_FILES"
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
    / "STEP_1"
    / "TASK_2"
    / "script_2_clean_to_cal.py"
)
SUITE_ALIASES = {"debug_suite", "usual_suite", "essential_suite"}
SLEWING_OBSERVABLE_ALIASES = {
    "timing",
    "tsum_spread_histograms_og",
    "tsum_spread_histograms_filtered_og",
    "dx_vs_tsum",
    "dx_vs_travel_time",
    "tsum_pair_charge_correlations",
    "slewing",
    "slewing_3d",
}


class Task2PlotCatalogTests(unittest.TestCase):
    def test_essential_plot_aliases_use_explicit_essential_requests(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        plot_modes = config.get("plots", {})
        script_text = SCRIPT_PATH.read_text()

        essential_aliases = sorted(
            alias
            for alias, mode in plot_modes.items()
            if str(mode).strip().lower() == "essential" and alias not in SUITE_ALIASES
        )

        missing_aliases: list[str] = []
        for alias in essential_aliases:
            escaped = re.escape(alias)
            pattern = rf"task2_plot_requested\(\s*[\"']{escaped}[\"']\s*,\s*essential\s*=\s*True"
            grouped_in_slewing_observables = alias in SLEWING_OBSERVABLE_ALIASES
            if not re.search(pattern, script_text) and not grouped_in_slewing_observables:
                missing_aliases.append(alias)

        self.assertEqual(
            missing_aliases,
            [],
            msg=(
                "Task 2 essential plot aliases declared in YAML but not explicitly "
                f"reachable in essential mode: {missing_aliases}"
            ),
        )

    def test_slewing_observable_plots_feed_the_shared_gate(self) -> None:
        script_text = SCRIPT_PATH.read_text()
        expected_snippets = [
            "TASK2_SLEWING_OBSERVABLE_ALIASES",
            "_slewing_plot_requests = {",
            "if _need_slewing_observables:",
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

        for alias in SLEWING_OBSERVABLE_ALIASES:
            self.assertIn(
                f'"{alias}"',
                script_text,
                msg=(
                    "Task 2 slewing-observable plots must remain part of the "
                    "shared observable gate so they can render independently "
                    "of slewing correction."
                ),
            )


if __name__ == "__main__":
    unittest.main()
