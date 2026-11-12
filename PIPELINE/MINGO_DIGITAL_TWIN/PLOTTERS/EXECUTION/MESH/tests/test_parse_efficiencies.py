
"""Test parsing of configured detector efficiencies."""

import unittest
import pandas as pd
import numpy as np

from PIPELINE.MINGO_DIGITAL_TWIN.PLOTTERS.EXECUTION.MESH.plot_param_mesh import parse_efficiencies_column


class TestParseEfficienciesColumn(unittest.TestCase):

    def test_stringified_list_parses_to_four_numeric_columns(self):
        df = pd.DataFrame({
            "efficiencies": ['[0.9, 0.8, 0.7, 0.6]', '[1.0, 1.0, 1.0, 1.0]']
        })
        out = parse_efficiencies_column(df.copy())
        self.assertIn("eff_p1", out.columns)
        self.assertTrue(np.allclose(out["eff_p1"].values, [0.9, 1.0]))
        self.assertTrue(np.allclose(out[["eff_p1", "eff_p2", "eff_p3", "eff_p4"]].iloc[0].values,
                                    [0.9, 0.8, 0.7, 0.6]))

    def test_list_values_are_handled(self):
        df = pd.DataFrame({"efficiencies": [[0.5, 0.5, 0.5, 0.5], [np.nan, None, 0.3, 0.4]]})
        out = parse_efficiencies_column(df.copy())
        self.assertIn("eff_p3", out.columns)
        self.assertTrue(np.allclose(out.loc[0, ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]].values,
                                    [0.5, 0.5, 0.5, 0.5]))
        self.assertTrue(np.isnan(out.loc[1, "eff_p1"]))

    def test_existing_eff_columns_are_preserved(self):
        df = pd.DataFrame({"eff_p1": [0.1], "eff_p2": [0.2], "eff_p3": [0.3], "eff_p4": [0.4]})
        out = parse_efficiencies_column(df.copy())
        self.assertIn("eff_p4", out.columns)
        self.assertEqual(out.loc[0, "eff_p2"], 0.2)

    def test_empty_or_malformed_results_in_nans(self):
        df = pd.DataFrame({"efficiencies": ["", "[bad,data]"]})
        out = parse_efficiencies_column(df.copy())
        self.assertTrue(out[["eff_p1", "eff_p2", "eff_p3", "eff_p4"]].isna().all().all())


if __name__ == "__main__":
    unittest.main()
