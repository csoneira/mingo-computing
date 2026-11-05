from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS"
CFG = SCRIPTS / "CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1"
STEP = SCRIPTS / "STAGES/STAGE_1/EVENT_DATA/STEP_1"


def aliases(path: Path) -> set[str]:
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^  ([A-Za-z0-9_]+):", line)
        if match:
            result.add(match.group(1))
    return result


class RuntimeFinalPlotSplitTests(unittest.TestCase):
    def test_runtime_and_final_catalogs_are_disjoint(self):
        for task in range(6):
            runtime = aliases(CFG / f"TASK_{task}/config_plots_task_{task}.yaml")
            final = aliases(CFG / f"TASK_{task}/config_final_plots_task_{task}.yaml")
            self.assertFalse(runtime & final, (task, sorted(runtime & final)))
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
        shared = (SCRIPTS / "common/step1_shared.py").read_text(encoding="utf-8")
        self.assertIn("create_pdf = False  # Runtime STEP_1 plots are strictly PNG-only.", shared)
        for task, script_name in {
            0: "script_0_acq_to_raw.py",
            1: "script_1_raw_to_clean.py",
            2: "script_2_clean_to_cal.py",
            3: "script_3_cal_to_list.py",
            4: "script_4_list_to_fit.py",
            5: "script_5_fit_to_post.py",
        }.items():
            source = (STEP / f"TASK_{task}/{script_name}").read_text(encoding="utf-8")
            self.assertNotIn("create_pdf = save_plots", source, task)

    def test_final_plotting_module_does_not_import_task_runtime_scripts(self):
        source = (SCRIPTS / "common/final_plotting.py").read_text(encoding="utf-8")
        self.assertNotIn("script_0_acq_to_raw", source)
        self.assertNotIn("script_1_raw_to_clean", source)
        self.assertNotIn("script_2_clean_to_cal", source)
        self.assertNotIn("script_3_cal_to_list", source)
        self.assertNotIn("script_4_list_to_fit", source)
        self.assertNotIn("script_5_fit_to_post", source)


if __name__ == "__main__":
    unittest.main()
