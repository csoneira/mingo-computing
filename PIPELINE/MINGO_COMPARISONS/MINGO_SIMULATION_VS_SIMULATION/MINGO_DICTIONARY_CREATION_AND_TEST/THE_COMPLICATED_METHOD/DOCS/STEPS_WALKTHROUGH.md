# Steps Walkthrough (Current Code)

This document maps each executable step to its primary inputs/outputs and
runtime role, based on the current scripts in `STEPS/`.

## 1) Setup and dictionary construction

### STEP 1.1 - Collect simulated metadata
- Script:
  `STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/collect_data.py`
- Main inputs:
  station/task metadata CSVs + simulation-parameter CSV
  - `STEP_1_1_COLLECT_DATA/INPUTS/config_step_1.1_columns.json` for explicit `parameter_columns` and `general_columns`
- Main outputs:
  - `.../STEP_1_1_COLLECT_DATA/OUTPUTS/FILES/collected_data.csv`
  - `.../STEP_1_1_COLLECT_DATA/OUTPUTS/FILES/parameter_space_columns.json`
- Role:
  build simulation-aligned base table and record selected parameter-space
  columns for downstream consistency.

### STEP 1.2 - Transform feature space
- Script:
  `STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/transform_feature_space.py`
- Main input:
  - STEP 1.1 `collected_data.csv`
- Main outputs:
  - `.../STEP_1_2_TRANSFORM_FEATURE_SPACE/OUTPUTS/FILES/transformed_feature_space.csv`
  - `.../STEP_1_2_TRANSFORM_FEATURE_SPACE/OUTPUTS/FILES/feature_space_manifest.json`
  - step summary JSON + feature-space diagnostic plots
- Role:
  generate the model feature space used for nearest-neighbor inverse mapping,
  using only the STEP 1.2 feature-space config for kept/new/ancillary columns
  and reusing STEP 1.1 column roles for passthrough bookkeeping. The emitted
  manifest is the authoritative downstream column partition.

### STEP 1.3 - Build dictionary + holdout dataset
- Script:
  `STEPS/STEP_1_SETUP/STEP_1_3_BUILD_DICTIONARY/build_dictionary.py`
- Main input:
  - STEP 1.2 `transformed_feature_space.csv`
  - STEP 1.2 `feature_space_manifest.json`
- Main outputs:
  - `.../STEP_1_3_BUILD_DICTIONARY/OUTPUTS/FILES/dictionary.csv`
  - `.../STEP_1_3_BUILD_DICTIONARY/OUTPUTS/FILES/dataset.csv`
  - `.../STEP_1_3_BUILD_DICTIONARY/OUTPUTS/FILES/selected_feature_columns.json`
- Role:
  split/filter data into dictionary support and evaluation dataset, using the
  STEP 1.2 manifest as the authoritative source of primary feature columns.

### STEP 1.4 - Continuity filtering
- Script:
  `STEPS/STEP_1_SETUP/STEP_1_4_ENSURE_CONTINUITY_DICTIONARY/ensure_continuity_dictionary.py`
- Main inputs:
  - STEP 1.3 `dictionary.csv`, `dataset.csv`, `selected_feature_columns.json`
- Main outputs:
  - filtered `dictionary.csv`
  - filtered `dataset.csv`
  - selected feature columns JSON (propagated or regenerated)
  - continuity flags/summary outputs
- Role:
  reject discontinuous/ambiguous dictionary points before inverse inference.

### STEP 1.5 - Distance-definition tuning
- Script:
  `STEPS/STEP_1_SETUP/STEP_1_5_TUNE_DISTANCE_DEFINITION/tune_distance_definition.py`
- Main inputs:
  - STEP 1.4 dictionary/dataset/features
- Main output:
  - `.../STEP_1_5_TUNE_DISTANCE_DEFINITION/OUTPUTS/FILES/distance_definition.json`
- Role:
  tune distance normalization/weights used by estimator core.

## 2) Inference and uncertainty calibration

### STEP 2.1 - Estimate parameters
- Script:
  `STEPS/STEP_2_INFERENCE/STEP_2_1_ESTIMATE_PARAMS/estimate_and_plot.py`
- Main inputs:
  - STEP 1.4 dictionary + dataset + selected features
  - STEP 1.5 distance definition
- Main output:
  - `.../STEP_2_1_ESTIMATE_PARAMS/OUTPUTS/FILES/estimated_params.csv`
- Role:
  run inverse mapping and emit diagnostic plots.

### STEP 2.2 - Validate estimates
- Script:
  `STEPS/STEP_2_INFERENCE/STEP_2_2_VALIDATION/validate_solution.py`
- Main inputs:
  - STEP 2.1 `estimated_params.csv`
  - STEP 1.4 dictionary/dataset
- Main outputs:
  - validation result CSVs + plots
- Role:
  compare inferred vs known simulated parameters.

### STEP 2.3 - Build uncertainty LUT
- Script:
  `STEPS/STEP_2_INFERENCE/STEP_2_3_UNCERTAINTY/build_uncertainty_lut.py`
- Main inputs:
  - STEP 2.2 validation CSV
  - STEP 1.4 dictionary (for support metadata)
- Main outputs:
  - `.../STEP_2_3_UNCERTAINTY/OUTPUTS/FILES/uncertainty_lut.csv`
  - `.../STEP_2_3_UNCERTAINTY/OUTPUTS/FILES/uncertainty_lut_meta.json`
- Role:
  calibrate empirical uncertainty vs parameter/event-count regimes.

## 3) Synthetic time-series replay

### STEP 3.1 - Build parameter trajectory
- Script:
  `STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_1_TIME_SERIES_CREATION/create_time_series.py`
- Main inputs:
  - STEP 1.4 dataset/dictionary
- Main outputs:
  - `time_series.csv`
  - `complete_curve_time_series.csv`
- Role:
  create smooth/discretized synthetic target trajectory.

### STEP 3.2 - Generate synthetic dataset
- Script:
  `STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES/synthetic_time_series.py`
- Main inputs:
  - STEP 3.1 time-series artifacts
  - STEP 1.4 dictionary + dataset template
- Main outputs:
  - `synthetic_dataset.csv`
  - synthetic generation diagnostics
- Role:
  map target trajectory into synthetic observable rows.

### STEP 3.3 - Correct synthetic series by inference
- Script:
  `STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_3_CORRECTION/correction_by_inference.py`
- Main inputs:
  - STEP 3.2 synthetic dataset
  - STEP 1.4 dictionary/features
  - STEP 2.3 uncertainty LUT
- Main outputs:
  - corrected synthetic inference outputs + summaries/plots
- Role:
  run full inference pipeline on synthetic replay and compare against truth.

## 4) Real-data application

### STEP 4.1 - Collect real metadata
- Script:
  `STEPS/STEP_4_REAL_DATA/STEP_4_1_COLLECT_REAL_DATA/collect_real_data.py`
- Main inputs:
  - station/task metadata in configured real-data window
  - STEP 1.4 selected features / dictionary context
  - STEP 1.2 `feature_space_manifest.json`
- Main outputs:
  - `real_collected_data.csv`
  - collection summary + coverage plots
- Role:
  produce real-data table aligned with inference feature requirements by
  applying the same STEP 1.2 transform contract used for the simulation table.

### STEP 4.2 - Infer real parameters
- Script:
  `STEPS/STEP_4_REAL_DATA/STEP_4_2_ANALYZE/analyze.py`
- Main inputs:
  - STEP 4.1 real collected data
  - STEP 1.4 dictionary/features
  - STEP 2.3 uncertainty LUT
- Main output:
  - `real_results.csv`
  - analysis summary + time-series plots
- Role:
  estimate real flux/efficiency trajectories with uncertainty attachment.

## Shared core

- Core estimator engine:
  `STEPS/STEP_2_INFERENCE/estimate_parameters.py`
- Shared utilities:
  `STEPS/MODULES/*.py`

This estimator module is currently the highest-complexity locus and the
primary target for careful, test-backed refactoring.
