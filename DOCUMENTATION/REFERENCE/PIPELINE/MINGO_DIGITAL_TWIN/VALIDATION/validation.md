# Validation Suite for MINGO_DIGITAL_TWIN

## Purpose
This validation suite checks the simulation pipeline in three layers:
- Engineering integrity: file discovery, registry/metadata consistency, schema and ID conservation.
- Numerical/statistical sanity: distributions, closure checks, and tolerance-based checks.
- Physics/electronics plausibility: geometry consistency, efficiency closure, trigger logic, and digitization behavior.

All validators are **read-only** against `PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS` and `PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA`.

## Entrypoint and Usage
Main CLI:

```bash
python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py
```

Common examples:

```bash
# All validators, latest discovered artifacts
python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py

# Select validators
python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py --steps cross,2,3,4,8,9,10,final

# Enable plots (plots are never generated without this flag)
python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py -p

# Restrict by SIM_RUN substring match (applied per step run directory name)
python3 PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/run_validation.py --sim-run SIM_RUN_195_003
```

Options:
- `--sim-run`: exact or substring filter on discovered per-step run directory names.
- `--steps`: comma-separated subset from `cross,0,1,2,3,4,5,6,7,8,9,10,final`.
- `-p/--plot`: generate PNG diagnostics under run output.
- `--max-step1-sample`: cap sampled rows for STEP 1 statistical checks.
- `--max-final-files`: limit number of latest `.dat` files for FINAL checks.

## Output Files
Each run writes to a unique folder:

`PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/output/validate_<YYYYMMDD_HHMMSS>/`

Files:
- `validation_results.csv`: long-form metric rows (one row per test metric).
- `validation_summary.csv`: one row per validator with PASS/WARN/FAIL/SKIP/ERROR counts.
- `validation_run_metadata.json`: run context, selected steps, filters, and artifact paths/hashes.
- `plots/` (only when `-p`).

Persistent history:
- `PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/output/validation_history.csv`
- One appended row per execution (overall status and per-status validator counts).

## Report Schema
`validation_results.csv` columns:
- `run_timestamp`
- `validator`
- `test_id`
- `test_name`
- `step`
- `sim_run`
- `config_hash`
- `upstream_hash`
- `n_rows_in`
- `n_rows_out`
- `metric_name`
- `metric_value`
- `expected_value`
- `threshold_low`
- `threshold_high`
- `status` (`PASS|WARN|FAIL|SKIP|ERROR`)
- `notes`

`validation_summary.csv` columns:
- `run_timestamp`, `validator`, `step`, `sim_run`, `status`
- `n_pass`, `n_warn`, `n_fail`, `n_skip`, `n_error`, `n_total`

Overall status rule:
- `FAIL` if any `FAIL` or `ERROR` exists.
- Else `WARN` if any `WARN` exists.
- Else `PASS` if any `PASS` exists.
- Else `SKIP`.

## Implemented Validators and Checks

### `validate_cross_step_lineage`
- Artifact existence by step.
- Config/upstream hash presence checks.
- Registry entry presence checks.
- Manifest `row_count` exact checks when feasible; large-manifest scans are warned/skipped.
- Upstream hash recomputation consistency.
- `source_dataset` path existence (strict from STEP 3+, optional/warn for STEP 2 when absent).
- Step-to-step row deltas.
- Event-ID conservation (exact where expected, subset check for STEP 8->9 trigger selection).

### `validate_step0_mesh`
- Required columns and binary `done` checks.
- Step-ID numeric/duplicate-chain checks.
- Efficiency bounds and z-plane monotonicity.
- Parameter range checks (`cos_n`, flux) against configured ranges.

### `validate_step1_muons`
- Required columns and sample load check.
- Spatial bounds and symmetry checks for generated `(X_gen, Y_gen)`.
- Angular domain checks (`Theta_gen`, `Phi_gen`).
- `cos(theta)` mean closure vs configured `cos_n`.
- Phi uniformity diagnostic via mean resultant vector.
- `T_thick_s` non-negativity and sampled monotonicity check.

### `validate_step2_crossings`
- Required columns and row count checks.
- Crossing tag (`tt_crossing`) consistency with available per-plane hits.
- Geometry/time consistency (normalized time, monotonicity along track direction).
- Unphysical speed/ordering guardrails.

### `validate_step3_avalanche`
- `avalanche_exists` and `tt_avalanche` consistency.
- Non-negative ionization/avalanche sizes.
- Per-plane efficiency closure against configured efficiencies with statistical tolerance.

### `validate_step4_induction`
- Non-negativity of induced strip observables.
- NaN conventions for zero-charge strip values.
- `tt_hit` consistency with per-plane induced responses.
- Charge closure vs STEP 3 avalanche size by plane.

### `validate_step5_strip_obs`
- `q_diff` behavior for non-hit strips.
- Normalized `q_diff` sanity.
- Algebraic consistency of `T_diff` with STEP 4 observables.

### `validate_step6_endpoints`
- Endpoint closure identities vs STEP 5 (`T_front/T_back/Q_front/Q_back`).
- Finite-time checks for active channels.

### `validate_step7_offsets`
- Time-shift deltas consistent with configured offsets.
- Charge invariance through offset stage.
- Offset stationarity diagnostics.

### `validate_step8_fee`
- FEE transform and threshold behavior checks.
- Jitter RMS consistency with configured sigma.
- Threshold suppression sanity.

### `validate_step9_trigger`
- Trigger logic reconstruction and exact event-ID set checks.
- Trigger timestamp consistency.
- Acceptance sanity against an independence-based expectation.

### `validate_step10_tdc`
- Event-ID conservation from STEP 9.
- Jitter/smear sanity and zero-on-inactive behavior.
- `tdc_sigma` closure and variance-addition consistency.

### `validate_final_dat`
- `.dat` field-count checks (71 tokens per data line).
- Parse error counting and timestamp monotonicity checks.
- Payload magnitude sanity.
- Row-count matching against `step_final_simulation_params.csv` when available.
- Param-hash matching against file headers when available.
- Formatting round-trip token consistency.
- Explicit SKIP when exact STEP10->FINAL mapping registry is unavailable.

## Plot Behavior
Plots are created only with `--plot` and saved under:

`.../output/validate_<timestamp>/plots/<validator_name>/`

Examples include distributions, closure histograms, and row-count/acceptance diagnostics.

## Interpreting Results
- `PASS`: check meets strict expectation/tolerance.
- `WARN`: mild anomaly, relaxed tolerance exceedance, or optional input absence.
- `FAIL`: integrity or physics/electronics constraint violation.
- `SKIP`: required input missing for that check.
- `ERROR`: validator exception.

For periodic monitoring, track:
- `validation_history.csv` overall status trend.
- Sudden jumps in `n_fail`/`n_warn` by validator.
- Changes in dominant failing `test_id` values.

## Common Failure Modes
- Cross-step mismatches because latest available run differs by step.
- Missing artifacts for late stages (e.g., STEP 9/10 outputs absent but registry present).
- Metadata lineage drift (hash mismatch due config or upstream changes).
- Trigger selection effects mistaken for unintended row drops.
- Unit/sign convention drift in derived timing or charge fields.

## Adding New Tests Safely
- Keep validators read-only and avoid modifying `INTERSTEPS` or simulation outputs.
- Reuse `validators/common_io.py` for artifact/chunk loading and metadata handling.
- Emit rows through `ResultBuilder` in `validators/common_report.py` to keep schema stable.
- Prefer statistically-scaled thresholds (binomial/variance-aware) when event-count dependent.
- Use stable `test_id` values so history comparisons stay meaningful.

## Limitations
- Without real detector data, these checks validate internal consistency and model plausibility, not absolute detector realism.
- Some checks are conditional on artifact availability; missing late-stage files yield `SKIP`.
- Cross-step checks are strongest when a coherent sim-run chain is selected.
