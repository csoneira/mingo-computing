# STEPS Overview

This directory contains the executable pipeline for dictionary creation,
inference validation, synthetic replay, and real-data analysis.

## Execution order

1. `STEP_1_SETUP/STEP_1_1_COLLECT_DATA/collect_data.py`
2. `STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/transform_feature_space.py`
3. `STEP_1_SETUP/STEP_1_3_BUILD_DICTIONARY/build_dictionary.py`
4. `STEP_1_SETUP/STEP_1_4_ENSURE_CONTINUITY_DICTIONARY/ensure_continuity_dictionary.py`
5. `STEP_1_SETUP/STEP_1_5_TUNE_DISTANCE_DEFINITION/tune_distance_definition.py`
6. `STEP_2_INFERENCE/STEP_2_1_ESTIMATE_PARAMS/estimate_and_plot.py`
7. `STEP_2_INFERENCE/STEP_2_2_VALIDATION/validate_solution.py`
8. `STEP_2_INFERENCE/STEP_2_3_UNCERTAINTY/build_uncertainty_lut.py`
9. `STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_1_TIME_SERIES_CREATION/create_time_series.py`
10. `STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES/synthetic_time_series.py`
11. `STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_3_CORRECTION/correction_by_inference.py`
12. `STEP_4_REAL_DATA/STEP_4_1_COLLECT_REAL_DATA/collect_real_data.py`
13. `STEP_4_REAL_DATA/STEP_4_2_ANALYZE/analyze.py`

## Primary artifact chain

- `STEP 1.1` writes `collected_data.csv` and `parameter_space_columns.json`.
- `STEP 1.2` reads `collected_data.csv`, writes `transformed_feature_space.csv`.
- `STEP 1.3` reads transformed data, writes `dictionary.csv`, `dataset.csv`,
  and `selected_feature_columns.json`.
- `STEP 1.4` reads STEP 1.3 artifacts, applies continuity filters, rewrites
  filtered `dictionary.csv`/`dataset.csv` and selected-feature metadata.
- `STEP 1.5` reads STEP 1.4 outputs and writes `distance_definition.json`.
- `STEP 2.1` reads dictionary/dataset/feature selection (+ distance definition)
  and writes `estimated_params.csv`.
- `STEP 2.2` reads estimated params + reference tables, writes validation tables.
- `STEP 2.3` reads validation output, writes `uncertainty_lut.csv` and
  `uncertainty_lut_meta.json`.
- `STEP 3.1` generates a synthetic parameter trajectory.
- `STEP 3.2` maps trajectory to synthetic observables and writes
  `synthetic_dataset.csv`.
- `STEP 3.3` runs inference + LUT over synthetic data and writes corrected
  synthetic outputs.
- `STEP 4.1` collects real metadata constrained by config windows.
- `STEP 4.2` runs inference + LUT on real metadata and writes `real_results.csv`.

## Shared code

- `MODULES/` contains shared support code (feature-space config, fit helpers,
  uncertainty helpers, plotting/utilities).
- `STEP_2_INFERENCE/estimate_parameters.py` is the core estimation engine used
  by STEP 2.1, STEP 3.3, and STEP 4.2.
