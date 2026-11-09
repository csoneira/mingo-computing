# Self-trigger Task 2

This is a parallel branch after `TASK_1_SELFTRIGGER`; it does not follow
coincidence Task 2 and does not replace it. It reads
`selftrigger_cleaned_*.parquet`, applies broad per-channel safety limits and
four configured offset matrices, then writes
`selftrigger_calibrated_*.parquet` under the station's `TASK_2_SELFTRIGGER`
directory.

The task can be run once directly for MINGO01 with:

```bash
python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/SELF_TRIGGER/TASK_2_SELFTRIGGER/script_2_selftrigger_clean_to_cal.py 1
```

The regular guide remains active and repeatedly handles enabled tasks. Task 2
is enabled for stations 0–4 through
`CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/config_step_1.yaml`.

## Initial processing

The filter config uses inclusive `[-1000, 1000]` ranges for both charge and
time. Finite channel values outside their range are set to zero; rows and
other columns are retained. Inactive zero sentinels remain zero when offsets
are applied. The filter can be disabled in
`config_filtering_task_2_selftrigger.yaml`.

The calibration config contains four 4×4 matrices indexed by plane and strip:
`tdif`, `tsum`, `qf`, and `qb`. Their initial MINGO01 values are seeded from
recent Task-2 coincidence calibration metadata. Tdif, QF, and QB offsets are
subtracted; Tsum offsets are added. No calibration constants are fitted or
derived by this task.

Per-strip Tsum and Tdif use `(T_F + T_B) / 2` and `(T_B - T_F) / 2`.
Qsum and Qdif use `(Q_F + Q_B) / 2` and `(Q_F - Q_B) / 2`. The six
`delta_tsum_pN_pM` columns are the mean calibrated Tsum in plane M minus the
mean calibrated Tsum in plane N, using active strips with a nonzero calibrated
charge end and nonzero calibrated Tsum.

Runtime diagnostics are controlled by
`config_plots_task_2_selftrigger.yaml`; they include the raw end spectra,
Tdif/Tsum, charge components, and pairwise cross-plane Delta Tsum. The common
debug plotting utility writes PNGs only.

## FINAL report plots

After Task 2 has written a calibrated parquet, generate the report with:

```bash
python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/SELF_TRIGGER/TASK_2_SELFTRIGGER/final_plots_task_2_selftrigger.py \
  PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1/EVENT_DATA/STEP_1/TASK_2_SELFTRIGGER/OUTPUT_FILES/selftrigger_calibrated_<run>.parquet
```

`config_final_plots_task_2_selftrigger.yaml` enables the color-coded Qsum,
Qdif, Tsum and Tdif spectra and the 4×4 calibrated front/back charge overlay.
The script writes FINAL PNGs and a combined PDF under the task's
`PLOTS/FINAL_PLOTS/` tree, separately from parquet data.
