# Task 1 self-trigger diagnostic pass

This is the initial parallel processing task for Task-0 self-trigger parquets.
It stages `selftrigger_raw_*.parquet` files from Task 0, reads each selected
file into `working_df`, preserves the rows and columns unchanged, and writes
`selftrigger_cleaned_*.parquet` under this task's `OUTPUT_FILES/` directory.
The consumed Task-0 parquet is archived under this task's
`INPUT_FILES/COMPLETED_DIRECTORY/`.

Runtime diagnostics are PNG-only and selected in
`CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_1_SELFTRIGGER/config_plots_task_1_selftrigger.yaml`.
The current plots show per-column distributions and front/back charge-time
scatter plots for each plane/strip.

Run the next configured input for a station with:

```bash
bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/guide_raw_to_corrected.sh --station 1 --self-trigger --task 1
```

The self-trigger task has its own task-number namespace and does not change the
coincidence IDs 0-5. An optional Task-0 parquet path can be supplied when
invoking the Python script directly. Its output remains in this task's
`OUTPUT_FILES/`; the coincidence Task 2 and later scripts do not ingest it.

Input ordering and completed-file reanalysis follow the shared STEP_1
`file_selection_mode` and `complete_reanalysis` settings. Runtime figures are
controlled by this task's `create_plots` switch and explicit `plots` /
`non_plots` lists. The task writes execution, specific, per-second rate,
trigger-type, profiling, and status metadata where those output types are
enabled in the shared `metadata_outputs` configuration. It does not emit
coincidence-only filter, calibration, or efficiency metadata.

Standalone FINAL charge and time spectra comparisons can be generated from a
completed Task 1 self-trigger parquet with:

```bash
python PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_1_SELFTRIGGER/final_plots_task_1_selftrigger.py \
  /path/to/selftrigger_cleaned_*.parquet
```

The plotter pairs that file with the matching Task 0 coincidence parquet and
uses the aliases selected in
`CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_1_SELFTRIGGER/config_final_plots_task_1_selftrigger.yaml`.
