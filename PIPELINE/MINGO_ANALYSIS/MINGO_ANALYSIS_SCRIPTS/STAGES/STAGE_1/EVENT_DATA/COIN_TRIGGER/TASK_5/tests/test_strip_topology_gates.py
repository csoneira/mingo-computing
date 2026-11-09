from pathlib import Path
import importlib.util
import unittest

import numpy as np
import pandas as pd
import yaml
import matplotlib.pyplot as plt


TASK_DIR = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("task5_analysis_functions", TASK_DIR / "analysis_functions.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
final_spec = importlib.util.spec_from_file_location(
    "task5_final_plotting", TASK_DIR.parents[4] / "SUPPORT/SHARED_CODE/final_plotting.py"
)
final_plotting = importlib.util.module_from_spec(final_spec)
final_spec.loader.exec_module(final_plotting)


class Task5StripTopologyGateTests(unittest.TestCase):
    def setUp(self):
        patterns = [
            (),          # no strip in any plane
            (1,),        # one strip
            (1, 2),      # two adjacent strips
            (1, 3),      # two non-adjacent strips
            (1, 2, 3),   # three adjacent strips
            (1, 2, 3, 4),# four adjacent strips
            (1, 2, 4),   # three strips with a gap
        ]
        frame = pd.DataFrame({"event_id": np.arange(len(patterns))})
        for plane in range(1, 5):
            for strip in range(1, 5):
                frame[f"p{plane}_s{strip}_qsum"] = [
                    10.0 if plane == 1 and strip in active else 0.0
                    for active in patterns
                ]
        self.frame = analysis.add_task5_strip_topology_gate_columns(frame)
        self.config = yaml.safe_load(
            (TASK_DIR.parents[4] / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_5/config_gates_task_5.yaml").read_text()
        )

    def test_topology_gate_selections_match_strip_patterns(self):
        expected = {
            "at_most_1_strip_per_plane": [0, 1],
            "at_most_2_adjacent_strips_per_plane": [0, 1, 2],
            "at_most_3_adjacent_strips_per_plane": [0, 1, 2, 4],
            "at_most_4_adjacent_strips_per_plane": [0, 1, 2, 4, 5],
            "any_plane_has_nonadjacent_strips": [3, 6],
        }
        for gate_name, row_indices in expected.items():
            with self.subTest(gate=gate_name):
                expression = self.config["gates"][gate_name]["expression"]
                selected = self.frame.eval(expression, engine="python")
                self.assertEqual(np.flatnonzero(selected.to_numpy()).tolist(), row_indices)

    def test_missing_strip_columns_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "require all 16 strip Q_sum columns"):
            analysis.add_task5_strip_topology_gate_columns(self.frame.drop(columns=["p1_s1_qsum"]))

    def test_task5_final_gate_plot_uses_postprocessed_charge_and_labels(self):
        frame = pd.DataFrame(
            {
                "gate": ["all_events|at_most_1_strip_per_plane", "all_events"],
                "tt_task5_post": [1234, 13],
                "p1_qsum": [40.0, 80.0],
                "p2_qsum": [50.0, 90.0],
                "p3_qsum": [60.0, 100.0],
                "p4_qsum": [70.0, 110.0],
            }
        )
        figure = final_plotting.render_final_alias(
            frame, 5, "gate_charge_spectra_at_most_1_strip_per_plane"
        )
        try:
            self.assertIsNotNone(figure)
            self.assertEqual(len(figure.axes), 8)  # four planes by two exact TTs
        finally:
            if figure is not None:
                plt.close(figure)

    def test_final_config_uses_explicit_plot_lists(self):
        config_path = TASK_DIR.parents[4] / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_5/config_final_plots_task_5.yaml"
        config = yaml.safe_load(config_path.read_text())
        aliases = final_plotting._enabled_aliases(config)
        self.assertEqual(aliases, config["-plot"])
        self.assertEqual(len(aliases), len(set(aliases)))


if __name__ == "__main__":
    unittest.main()
