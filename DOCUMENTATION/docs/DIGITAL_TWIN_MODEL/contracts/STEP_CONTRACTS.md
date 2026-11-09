---
title: Step Interface Contracts
description: Consolidated interface contracts for STEP_0 through STEP_FINAL.
last_updated: 2026-02-24
status: active
supersedes:
  - step_00.md
  - step_01.md
  - step_02.md
  - step_03.md
  - step_04.md
  - step_05.md
  - step_06.md
  - step_07.md
  - step_08.md
  - step_09.md
  - step_10.md
  - step_final.md
---

# Step Interface Contracts

## Table of contents
- [STEP_0](#step_0)
- [STEP_1](#step_1)
- [STEP_2](#step_2)
- [STEP_3](#step_3)
- [STEP_4](#step_4)
- [STEP_5](#step_5)
- [STEP_6](#step_6)
- [STEP_7](#step_7)
- [STEP_8](#step_8)
- [STEP_9](#step_9)
- [STEP_10](#step_10)
- [STEP_FINAL](#step_final)

## STEP_0
Purpose:
- Generate or extend `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv`.

Required inputs:
- `config_step_0_physics.yaml`
- `config_step_0_runtime.yaml`
- station geometry CSVs under `station_config_root`

Outputs:
- `param_mesh.csv`
- `param_mesh_metadata.json`

Failure modes:
- missing/invalid station geometry
- invalid sampling ranges

## STEP_1
Purpose:
- Generate primary muon parameters and optional thick-time tags.

Required inputs:
- STEP_1 physics/runtime config
- `param_mesh.csv` when `cos_n` or `flux_cm2_min` uses `random`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2/SIM_RUN_*/muon_sample_*.(pkl|csv)`
- optional chunk manifest

Core columns:
- `event_id`, `X_gen`, `Y_gen`, `Z_gen`, `Theta_gen`, `Phi_gen`, `T_thick_s`

Failure modes:
- missing mesh/config
- no available unsimulated candidate rows

## STEP_2
Purpose:
- Project generated tracks onto detector planes and compute crossing times.

Required inputs:
- STEP_1 output columns
- `z_positions` or mesh-derived positions
- `active_area_bounds_mm` (or deprecated `bounds_mm` alias) and speed constants

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/SIM_RUN_*/step_2.(pkl|csv|chunks)`

Core columns:
- `X_gen_i`, `Y_gen_i`, `Z_gen_i`, `T_sum_i_ns`, `tt_crossing`, `crossing_mask`

Failure modes:
- missing mesh row for random geometry
- malformed input manifest/path

## STEP_3
Purpose:
- Convert crossings into avalanche observables with efficiency-driven ionization.

Required inputs:
- STEP_2 crossing columns
- efficiencies (explicit or random from mesh)

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4/SIM_RUN_*/step_3.(pkl|csv|chunks)`

Core columns:
- `avalanche_ion_i`, `avalanche_exists_i`, `avalanche_x_i`, `avalanche_y_i`, `avalanche_size_electrons_i`, `tt_avalanche`

Failure modes:
- invalid efficiencies
- missing mesh selection for random mode

## STEP_4
Purpose:
- Induce per-strip hit observables from avalanche state.

Required inputs:
- STEP_3 avalanche columns and times
- four-plane `readout_geometry_mm`, or warned legacy fallback

Geometry contract:
- active-area acceptance is inherited as provenance only and cannot define new strip rectangles
- charge is integrated over each absolute strip rectangle; gaps/outside charge is unassigned
- readout need not be centered or contained in the active area

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_4_TO_5/SIM_RUN_*/step_4.(pkl|csv|chunks)`

Core columns:
- `Y_mea_i_sj`, `X_mea_i_sj`, `T_sum_meas_i_sj`, readout fraction diagnostics, `tt_hit`

Failure modes:
- missing required avalanche fields (plane skipped)
- invalid, incomplete, overlapping, or inconsistent readout geometry

## STEP_5
Purpose:
- Derive `T_diff` and `q_diff` observables.

Required inputs:
- STEP_4 strip-level measurements

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_5_TO_6/SIM_RUN_*/step_5.(pkl|csv|chunks)`

Core columns:
- `T_diff_i_sj`, `q_diff_i_sj`

Failure modes:
- missing strip columns (skipped)

## STEP_6
Purpose:
- Convert sum/difference values to front/back channels.

Required inputs:
- STEP_5 outputs

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_6_TO_7/SIM_RUN_*/step_6.(pkl|csv|chunks)`

Core columns:
- `T_front_i_sj`, `T_back_i_sj`, `Q_front_i_sj`, `Q_back_i_sj`

Failure modes:
- missing strip columns (skipped)

## STEP_7
Purpose:
- Apply fixed cable/connector timing offsets.

Required inputs:
- STEP_6 channels
- 4x4 offset arrays

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_7_TO_8/SIM_RUN_*/step_7.(pkl|csv|chunks)`

Failure modes:
- invalid offset dimensions

## STEP_8
Purpose:
- Apply FEE jitter, time-walk conversion, and thresholding.

Required inputs:
- STEP_7 channels
- jitter/time-walk/threshold config

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_8_TO_9/SIM_RUN_*/step_8.(pkl|csv|chunks)`

Failure modes:
- missing strip columns
- invalid config values (not always explicitly validated)

## STEP_9
Purpose:
- Apply trigger combinations and filter events.

Required inputs:
- STEP_8 channel charges
- `trigger_combinations`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_9_TO_10/SIM_RUN_*/step_9.(pkl|csv|chunks)`

Core columns:
- preserved channels + `tt_trigger`
- `sim_crossing_cumulative_count` and
  `sim_unit_efficiency_trigger_cumulative_count` when `crossing_mask` is available

Failure modes:
- empty trigger list -> empty output

## STEP_10
Purpose:
- Apply TDC smear and event-level jitter.

Required inputs:
- STEP_9 channels and activity state

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_10_TO_FINAL/SIM_RUN_*/step_10.(pkl|csv|chunks)`

Core columns:
- preserved channels + `daq_jitter_ns`
- preserved geometrical rate counters from STEP 9 when available

Failure modes:
- missing channel columns (skipped)

## STEP_FINAL
Purpose:
- Format STEP_10 outputs to station `.dat` and register parameter lineage.

Required inputs:
- STEP_10 channels
- runtime sampling/output config
- mesh linkage for `param_set_id` assignment

Outputs:
- `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/mi00YYDDDHHMMSS.dat`
- one parquet ground-truth sidecar per `.dat`, named
  `sidecar_mi00YYDDDHHMMSS.parquet`, under the configured
  `sidecar_output_dir` (default: `FILES_SIDECARS` beside the `.dat` directory)
- `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_output_registry.json`
- `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv`

Sidecar contract:
- rows correspond one-to-one, in order, to the data rows actually written to the `.dat`
- `event_id` is the physical `.dat` line number used later by Task 0
- `sim_event_id` preserves the upstream STEP_10 `event_id`
- ground truth includes `T_thick_s`, `X_gen`, `Y_gen`, `Theta_gen`, `Phi_gen`,
  and `Z_gen` when available
- rate-counter provenance includes `sim_crossing_cumulative_count` and
  `sim_unit_efficiency_trigger_cumulative_count` for new simulations
- `step_final_simulation_params.csv` records interval-aligned
  `particle_crossing_rate_hz`, `trigger_rate_unit_efficiency_hz`, and
  `trigger_rate_hz`; legacy rows remain nullable

Failure modes:
- missing upstream lineage fields
- ambiguous mesh match
- inconsistent `T_thick_s` presence across selected chunks
- sidecar write failure after `.dat` generation (fails loudly to prevent silent inconsistency)

## Metadata contract common to all steps
Where supported, outputs include metadata sidecars/manifests with:
- `created_at`, `step`, `sim_run`
- config snapshot and hashes
- upstream lineage hashes
- step ID chain and mesh row identifiers when available
