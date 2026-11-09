# Definitive Method

This version is intentionally simple.

The method is:
1. Select exactly four empirical-efficiency columns.
2. Select one or more rate columns.
3. Build one independent LUT scale-factor column per rate from `MINGO00`.
4. Apply each LUT to one real station slice.
5. Convert each corrected rate to flux.

The final LUT output is one outer table with:
- the 4 efficiency coordinates
- one scale-factor column per selected rate

Each rate case also gets its own diagnostic plots and per-case CSVs in its own
subdirectory.

There is no metadata-source abstraction here. The config names the metadata
files and the columns explicitly.

## Config Idea

The example configuration fields in `config.json` are:

```json
"efficiency": {
  "metadata_relative_path": "STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_robust_efficiency.csv",
  "columns": ["eff1", "eff2", "eff3", "eff4"]
},
"rates": [
  {
    "name": "four_plane_robust_hz",
    "metadata_relative_path": "STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_robust_efficiency.csv",
    "rate_column": "four_plane_robust_hz"
  },
  {
    "name": "post_tt_1234_rate_hz",
    "metadata_relative_path": "STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_trigger_type.csv",
    "rate_column": "post_tt_1234_rate_hz"
  }
]
```

To switch to another case, change those lines. The efficiencies come from one
explicit metadata file and 4 explicit columns. Each rate case also names one
explicit metadata file and one explicit rate column. As long as the metadata
contains the join key (`param_hash` for `MINGO00`, `filename_base` for real
data), it works.

The paths are relative to each station directory under `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/`.

## Steps

`step_0_load_inputs.py`
- Reads the selected `MINGO00` efficiency metadata.
- Reads every selected rate metadata source.
- Merges them by `param_hash`.
- Reads the selected real-station efficiency metadata.
- Reads every selected real-station rate metadata source.
- Merges them by `filename_base`.
- Selects one z geometry.
- Writes one shared filtered training table and one shared filtered real-data table.
- Plots one common `parameter_space`.

`step_1_build_lut.py`
- Reads the Step 0 training table.
- Loops independently over the selected rates.
- Bins the 4-D efficiency space.
- Builds the per-flux reference with the asymptote method.
- Builds one scale factor per 4-D efficiency bin for that rate.
- Writes:
  - one per-rate detailed LUT
  - one per-rate rate-to-flux calibration
  - one outer combined LUT with the 4 efficiency columns and all selected scale-factor columns
- Plots one per-rate `reference_asymptote`.

`step_2_apply_lut.py`
- Reads the Step 0 real-data table.
- Loops independently over the selected rates.
- Applies the corresponding per-rate LUT with exact match plus nearest/interpolated fallback.
- Writes one corrected real-data rate table per rate.
- Plots per rate:
  - `real_rate_correction`
  - `real_correction_diagnostics`
  - `lut_real_efficiency_coverage`
  - `real_rate_vs_efficiencies_2x2`

`step_3_rate_to_flux.py`
- Reads each Step 2 corrected-rate table.
- Uses the corresponding Step 1 rate-to-flux calibration.
- Writes one corrected-flux table per rate.
- Plots per rate:
  - `rate_to_flux_calibration`
  - `corrected_flux_time_series`

## Run

```bash
cd /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/DEFINITIVE_METHOD
python3 run_all.py
```

## Output Layout

Common outputs go to:

`OUTPUTS/<case_name>/FILES`

That is where the shared Step 0 outputs and the final combined multi-rate LUT
live.

Per-rate outputs go to:

`OUTPUTS/<case_name>/RATE_CASES/<rate_name>/FILES`

`OUTPUTS/<case_name>/RATE_CASES/<rate_name>/PLOTS`

That is deliberate, because later the same workflow can be repeated for many
different rate cases and each one already has its own isolated subdirectory.
