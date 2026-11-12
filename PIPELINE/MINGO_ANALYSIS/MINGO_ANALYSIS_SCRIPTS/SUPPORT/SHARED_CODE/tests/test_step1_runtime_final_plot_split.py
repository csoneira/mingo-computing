"""Test step1 runtime final plot split behavior."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[6]
SCRIPTS = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS"
CFG = SCRIPTS / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1"
STEP = SCRIPTS / "STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER"


def aliases(path: Path) -> set[str]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = set((loaded.get("plots") or {}).keys())
    result.update(loaded.get("-plot", []) or [])
    result.update(loaded.get("-not_plot", []) or [])
    return {str(alias) for alias in result}


class RuntimeFinalPlotSplitTests(unittest.TestCase):
    def test_runtime_and_final_catalogs_are_disjoint(self):
        for task in range(6):
            runtime_path = CFG / f"TASK_{task}/config_plots_task_{task}.yaml"
            runtime_config = yaml.safe_load(runtime_path.read_text(encoding="utf-8")) or {}
            runtime = set(runtime_config.get("-plot", []) or [])
            self.assertEqual(set(runtime_config), {"-plot", "-not_plot"})
            self.assertFalse(runtime & set(runtime_config.get("-not_plot", []) or []))
            final = aliases(CFG / f"TASK_{task}/config_final_plots_task_{task}.yaml")
            self.assertFalse(runtime & final, (task, sorted(runtime & final)))
            if task != 5:
                self.assertTrue(final, f"Task {task} FINAL catalog is empty")

    def test_each_task_has_standalone_final_plotter_with_one_cli_argument(self):
        for task in range(6):
            path = STEP / f"TASK_{task}/final_plots_task_{task}.py"
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            self.assertEqual(source.count("parser.add_argument("), 1, task)
            self.assertIn('parser.add_argument("parquet_path"', source)
            self.assertIn(f"config_final_plots_task_{task}.yaml", source)

    def test_runtime_pdf_creation_is_disabled(self):
        shared = (SCRIPTS / "SUPPORT/SHARED_CODE/step1_shared.py").read_text(encoding="utf-8")
        self.assertRegex(shared, r"create_pdf\s*=\s*False")
        for task, script_name in {
            0: "script_0_acq_to_raw.py",
            1: "script_1_raw_to_clean.py",
            2: "script_2_clean_to_cal.py",
            3: "script_3_cal_to_list.py",
            4: "script_4_list_to_fit.py",
            5: "script_5_fit_to_post.py",
        }.items():
            source = (STEP / f"TASK_{task}/{script_name}").read_text(encoding="utf-8")
            active_source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
            self.assertNotIn("PdfPages", active_source, task)
            self.assertNotIn("finalize_saved_plots_to_pdf", active_source, task)
            self.assertNotIn('"pdf_directory"', active_source, task)
            self.assertNotIn("save_pdf_path", active_source, task)

    def test_final_plotting_module_does_not_import_task_runtime_scripts(self):
        source = (SCRIPTS / "SUPPORT/SHARED_CODE/final_plotting.py").read_text(encoding="utf-8")
        self.assertNotIn("script_0_acq_to_raw", source)
        self.assertNotIn("script_1_raw_to_clean", source)
        self.assertNotIn("script_2_clean_to_cal", source)
        self.assertNotIn("script_3_cal_to_list", source)
        self.assertNotIn("script_4_list_to_fit", source)
        self.assertNotIn("script_5_fit_to_post", source)


if __name__ == "__main__":
    unittest.main()
