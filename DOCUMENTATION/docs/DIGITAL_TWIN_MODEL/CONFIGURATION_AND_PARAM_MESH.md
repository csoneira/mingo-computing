---
title: Configuration and Parameter Mesh Reference
description: Runtime/physics configuration keys and parameter-mesh semantics across STEP_0 to STEP_FINAL.
last_updated: 2026-02-24
status: active
supersedes:
  - config_reference.md
  - param_mesh.md
---

# Configuration and Parameter Mesh Reference

## Table of contents
- [Configuration files](#configuration-files)
- [Common runtime keys](#common-runtime-keys)
- [Step-by-step key reference](#step-by-step-key-reference)
- [Parameter mesh schema](#parameter-mesh-schema)
- [Parameter mesh lifecycle](#parameter-mesh-lifecycle)
- [Validation and consistency checks](#validation-and-consistency-checks)

## Configuration files
Each step uses:
- physics config: `MASTER_STEPS/STEP_N/config_step_N_physics.yaml`
- runtime config: `MASTER_STEPS/STEP_N/config_step_N_runtime.yaml` (where applicable)

Canonical contracts are summarized in:
- `contracts/STEP_CONTRACTS.md`

## Common runtime keys
- `input_dir`: upstream directory root.
- `input_glob`: upstream file pattern.
- `input_sim_run`: `latest`, `random`, explicit `SIM_RUN_*`, or list (STEP_FINAL).
- `output_dir`: destination path.
- `output_format`: `pkl` or `csv`.
- `chunk_rows`: rows per chunk for chunked output.
- `plot_sample_rows`: sample count for plots.

## Step-by-step key reference

### STEP_0 (mesh generation)
Physics:
- `cos_n`, `flux_cm2_min`
- `efficiencies`, `efficiencies_identical`
- `efficiencies_max_spread` (number or `null` when `efficiencies_identical=false`)
- `repeat_samples`, `shared_columns`
- `expand_z_positions`

Runtime:
- `station_config_root`
- `output_dir`

### STEP_1 (generation)
Physics:
- `xlim_mm`, `ylim_mm`, `z_plane_mm`
- `seed`, `c_mm_per_ns`
- `cos_n`, `flux_cm2_min` (scalar or `random` from mesh)

Runtime:
- `n_tracks`, `output_basename`
- `param_mesh_dir`, `param_mesh_sim_run`

### STEP_2 (crossings and active gas area)
Physics:
- `active_area_bounds_mm`: required `x_min`, `x_max`, `y_min`, `y_max` coordinates controlling valid gas crossings and therefore Step 3 avalanche production.
- `bounds_mm`: deprecated alias. A warning is emitted when used; `active_area_bounds_mm` takes precedence if both appear.
- `z_positions` (4 values or `random` from mesh)

Runtime:
- `input_basename`
- `normalize_to_first_plane`
- `param_mesh_dir`, `param_mesh_sim_run`

### STEP_3 (avalanche)
Physics:
- `avalanche_gap_mm`
- `townsend_alpha_per_mm`, `avalanche_electron_sigma`
- `efficiencies` (vector(s) or `random`)

Runtime:
- `param_mesh_dir`, `param_mesh_sim_run`

Step 3 inherits valid crossing coordinates. It does not read or clip to Step 4 readout geometry.

### STEP_4 (induction and readout geometry)
Physics:
- `x_noise_mm`, `time_sigma_ns`
- `lorentzian_gamma_mm`
- `induced_charge_fraction`
- `readout_geometry_mm.planes`: all four planes are required. Each plane has `x_min`, `x_max`, and exactly four strips.

Generated strip form:

```yaml
readout_geometry_mm:
  planes:
    "1":
      x_min: -150.0
      x_max: 150.0
      y_min: -145.0
      strip_widths_mm: [63.0, 63.0, 63.0, 98.0]
      interstrip_gap_mm: 1.0
      y_max: 145.0
```

`y_max` is optional and, when supplied, must match the derived last-strip boundary within `1e-9 mm`. `interstrip_gap_mm` is the inactive edge-to-edge gap, not strip pitch.

Explicit strip form:

```yaml
"1":
  x_min: -150.0
  x_max: 150.0
  strip_y_bounds_mm:
    - [-145.0, -82.0]
    - [-81.0, -18.0]
    - [-17.0, 46.0]
    - [47.0, 145.0]
```

A plane cannot mix forms. Coordinates must be finite, limits ordered, strips sorted and non-overlapping, gaps non-negative, and exactly four strips must be defined. Readout containment in the active area is deliberately not required.

If `readout_geometry_mm` is absent, the warned legacy fallback reproduces the old active-X, centered contiguous-Y behavior with zero gaps. The fallback exists only for old configurations.

The active gas area controls where avalanches may be produced. The readout geometry controls where induced charge is collected. The two geometries are independent and may overlap only partially.

Schematic example (not measured dimensions):

```text
readout strip assembly:  +------------------------------------+
active gas area:              +--------------------------+
strip Y bands:           | S1 |gap| S2 |gap| S3 |gap| S4 |
                         +------------------------------------+
```

This illustrates readout extending beyond the active rectangle in X and Y; neither rectangle is clipped to the other.

### STEP_5 (signal observables)
Physics:
- `qdiff_width` (required constant sigma for `q_diff`)
- `c_mm_per_ns` (optional override)

### STEP_6 (front/back)
- No required physics keys.

### STEP_7 (cable offsets)
Physics:
- `tfront_offsets` (4x4)
- `tback_offsets` (4x4)

### STEP_8 (FEE + threshold)
Physics:
- `t_fee_sigma_ns`
- `charge_threshold`
- `charge_conversion_model`
- `tot_to_charge_calibration_path`
- `q_to_time_factor` (legacy fallback for linear conversion mode)
- `qfront_offsets`, `qback_offsets`

### STEP_9 (trigger)
Physics:
- `trigger_combinations` (for example `"12"`, `"23"`)

### STEP_10 (DAQ jitter)
Physics:
- `jitter_width_ns`
- `tdc_sigma_ns`

### STEP_FINAL (event builder)
Runtime:
- `input_collect` (`matching` or `baseline_only`)
- `target_rows`
- `files_per_station_conf`
- `payload_sampling` (`random` or `sequential_random_start`)
- `rate_hz` (when `T_thick_s` absent)
- `param_mesh_dir`, `param_mesh_sim_run`

## Parameter mesh schema
Path:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv`

Core columns:
- `done` (0/1)
- `step_1_id` to `step_10_id` (3-digit IDs)
- `cos_n`, `flux_cm2_min`
- `eff_p1` to `eff_p4`
- `z_p1` to `z_p4`

Optional lineage columns:
- `param_set_id`
- `param_date`
- future scan variables

Associated metadata file:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh_metadata.json`

## Parameter mesh lifecycle
1. STEP_0 appends rows and assigns step IDs from unique parameter combinations.
2. STEP_1 to STEP_3 read randomizable physics values from mesh when configured.
3. STEP_4 to STEP_10 carry IDs forward and use defaults/overrides.
4. STEP_FINAL writes `param_set_id`, `param_date`, and sets `done=1` for matched rows.
5. Housekeeping can prune `done=1` rows from mesh after downstream completion.

## Validation and consistency checks
Recommended checks:

```bash
# Ensure pending mesh rows have upstream runs
PYTHONPATH=. python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py \
  --mesh PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv \
  --intersteps PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS --step 3

# Inspect expected-vs-produced summary
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/size_and_expected_report.py
```

Open review points:
- If fixed-geometry operation is intended, verify mesh-generation policy and closure policy (`RUN_STEP_STRICT_LINE_CLOSURE`) remain compatible.
- If `input_sim_run=random` is used heavily, ensure selection bias is acceptable for the target analysis objective.
