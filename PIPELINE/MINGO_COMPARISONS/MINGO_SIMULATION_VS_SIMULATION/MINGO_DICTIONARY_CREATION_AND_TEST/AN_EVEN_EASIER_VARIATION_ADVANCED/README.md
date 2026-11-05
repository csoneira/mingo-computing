# AN_EVEN_EASIER_VARIATION_ADVANCED

This variation adds a Step 0 geometry-aware efficiency correction on top of the simplified real-data workflow.

## Purpose

Step 0 reads the MINGO00 metadata selected by `trigger_type_selection`, merges it with
`PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv` by `param_hash`, and for each geometry
configuration plus each plane it fits a polynomial mapping:

- observed real efficiency -> realistic simulated efficiency

The fit table is stored as a CSV with one row per geometry and one coefficient-vector cell per plane. The
polynomial degree is configurable, so the coefficient vectors can have any length.

Step 1 reads station metadata exactly as the `ANOTHER_METHOD` step 5 workflow does, assigns the online geometry
to each real row from the ONLINE_RUN_DICTIONARY, and writes a compact CSV containing:

- `selected_rate_hz`
- `eff_empirical_1`
- `eff_empirical_2`
- `eff_empirical_3`
- `eff_empirical_4`

When `metadata_source = "robust_efficiency"`, the Step 1 CSV also preserves the original
source efficiency columns such as `eff1_median_x`, `eff2_median_x`, `eff3_median_x`,
and `eff4_median_x`.

It also preserves `filename_base`, `file_timestamp_utc`, and `execution_timestamp_utc` when available.
The metadata source can be either the existing `trigger_type` CSVs or the newer
`robust_efficiency` CSVs. When `corrected_eff` is enabled, the Step 0 polynomial fits are applied before
Step 2, geometry by geometry and plane by plane.

In the current default configuration, the observed per-plane efficiencies are the
robust-efficiency `median_x` columns. Those are the values used as the empirical
inputs for the Step 0 fits, the Step 1 correction, and the Step 2 reference build.

Step 2 reads that output, builds the configured efficiency reference from the selected
empirical-efficiency planes, applies it to `selected_rate_hz`, and plots the
original/corrected rate time series plus the selected efficiency series and their
reference.

## Run

```bash
cd /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/AN_EVEN_EASIER_VARIATION_ADVANCED
python3 run_all.py
```

## Configuration

Edit `config.json` to change the station, date window, selected rate definition, or the Step 0 fit behavior.

When `step5.station = "MINGO00"`, this workflow now falls back to a synthetic single-geometry
schedule because there is no `ONLINE_RUN_DICTIONARY` CSV for station 0. By default it uses
`geometry.station0_z_positions = [0.0, 100.0, 200.0, 400.0]`, validated against
`step0.simulation_params_csv`.

Key Step 0 controls:

- `corrected_eff`
- `geometry.station0_z_positions`
- `step0.simulation_params_csv`
- `step0.mingo00_metadata_root`
- `step0.fit_polynomial_degree`
- `step0.observed_efficiency_upper_limits`
- `step0.fit_clip_output`

Key Step 0 outputs:

- `paths.step0_training_csv`
- `paths.step0_fit_table_csv`
- `paths.step0_meta_json`

Key Step 1 output:

- `paths.step1_meta_json`

Observed-efficiency upper limits are applied in two places:

- Step 0: training points above the plane limit are excluded from the polynomial fit
- Step 1: real rows above the plane limit are dropped before any later correction or plotting

This is useful for noisy empirical tails, for example setting planes 1 and 4 to `0.8`.

`trigger_type_selection.metadata_source` controls which metadata file is read:

- `trigger_type`: reads `task_<id>_metadata_trigger_type.csv`
- `robust_efficiency`: reads `TASK_4/task_4_metadata_robust_efficiency.csv`

When `metadata_source = "robust_efficiency"`, the task/stage/offender settings
are ignored and only the rate choice matters:

- `rate_family = "four_plane"` or `rate_family = "1234"` uses `rate_1234_hz`
- `rate_family = "four_plane_robust_hz"` uses `four_plane_robust_hz`
- `rate_family = "total"` uses `rate_total_hz`
- `rate_family` can also be any numeric robust-metadata column directly, for example:
  - `four_plane_robust_hz_union`
  - `four_plane_robust_hz_intersection`
  - `four_plane_robust_count_union`
  - `four_plane_robust_count_intersection`
  - `four_plane_robust_efficiency_union`

Optional helpers for direct robust-column testing:

- `selected_count_column`: explicit count column paired to the selected column
- `selected_display_label`: plot label override for Step 2

Robust metadata also offers multiple per-plane efficiency families. You can choose
which one is mapped into `eff_empirical_1..4` with:

- `robust_efficiency_variant = "default"` -> `eff1`, `eff2`, `eff3`, `eff4`
- `robust_efficiency_variant = "plateau"` -> `eff1_plateau`, ...
- `robust_efficiency_variant = "overall"` -> `eff1_overall`, ...
- `robust_efficiency_variant = "median_x"` -> `eff1_median_x`, ...

Step 2 scaling is controlled with:

- `step2.efficiency_reference_planes`
- `step2.efficiency_reference_mode`
- `step2.efficiency_reference_min`
- `step2.efficiency_plot_ylim`
- `step2.plot_apply_moving_average`
- `step2.plot_moving_average_kernel`

Example:

- `[3]` uses only `eff_empirical_3`
- `[2, 3]` uses the mean of `eff_empirical_2` and `eff_empirical_3`
- `"mean_power4"` applies the old assumption `1 / mean(selected planes)^4`
- `"product"` applies `1 / product(selected planes)`; with `[1, 2, 3, 4]` this is the direct four-plane efficiency product
- `0.2` drops rows where the derived `eff_reference` is below `0.2`
- `[null, 1.0]` keeps the efficiency-plot lower bound automatic while fixing the top at `1.0`
- `true` plus kernel `9` applies a centered 9-point moving average to both Step 2 time-series plots

Plots written by the advanced flow:

- `OUTPUTS/PLOTS/step0_01_efficiency_fit_overview.png`
- `OUTPUTS/PLOTS/step1_01_efficiency_time_series.png`
- `OUTPUTS/PLOTS/step1_02_efficiency_correction_scatter.png`
- `OUTPUTS/PLOTS/step2_01_selected_vs_corrected_rate.png`
- `OUTPUTS/PLOTS/step2_02_eff_reference_series.png`
- `OUTPUTS/PLOTS/step2_03_eff_reference_vs_rate_scatter.png`
