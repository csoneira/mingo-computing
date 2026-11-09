"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/MESH/tests/test_expand_params.py
Purpose: Test expand params.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/MESH/tests/test_expand_params.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

import unittest
import pandas as pd

from PIPELINE.MINGO_DIGITAL_TWIN.PLOTTERS.EXECUTION.MESH.plot_param_mesh import expand_params


class TestExpandParams(unittest.TestCase):

    def setUp(self):
        # create a merged_df with numeric eff_p1..eff_p4 and a non-numeric col
        self.merged = pd.DataFrame({
            "eff_p1": [0.9, 0.9],
            "eff_p2": [0.8, 0.8],
            "eff_p3": [0.7, 0.7],
            "eff_p4": [0.6, 0.6],
            "flux_cm2_min": [1.0, 2.0],
            "label": ["a", "b"],
        })

    def test_eff_1_maps_to_eff_p1(self):
        out = expand_params(["eff_1", "flux_cm2_min"], self.merged)
        self.assertEqual(out, ["eff_p1", "flux_cm2_min"])

    def test_efficiencies_expands_to_all_eff_p(self):
        out = expand_params(["cos_n", "efficiencies"], self.merged)
        # eff_p1..eff_p4 should be included (numeric)
        self.assertTrue(all(c in out for c in ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]))

    def test_unknown_eff_is_ignored_if_missing_or_non_numeric(self):
        # create df without eff_p3
        df2 = self.merged.drop(columns=["eff_p3"])
        out = expand_params(["eff_3", "eff_2"], df2)
        self.assertEqual(out, ["eff_p2"])  # eff_3 not present so skipped


if __name__ == "__main__":
    unittest.main()
