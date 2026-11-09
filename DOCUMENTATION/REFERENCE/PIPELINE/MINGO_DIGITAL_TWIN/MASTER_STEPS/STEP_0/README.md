# STEP 0 (Parameter Mesh Setup)

Purpose:
- Build or extend `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv` with sampled parameters.
- Assign step IDs (`step_1_id`..`step_10_id`) that define SIM_RUN naming downstream.

Inputs:
- Physics config: `config_step_0_physics.yaml`
- Runtime config: `config_step_0_runtime.yaml`
- Station config CSVs under `station_config_root` (P1..P4 plane positions).

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh_metadata.json`

Key behavior:
- Samples `cos_n`, `flux_cm2_min`, efficiencies, and z-plane tuples.
- `efficiencies_identical=false` supports configurable spread control via
  `efficiencies_max_spread` (number or `null` for unrestricted spread inside
  configured `efficiencies` bounds).
- Supports fixed geometry override via `z_positions_override_mm` in physics config.
- Supports `adapt_z_positions_for_station_date_range`, which filters the allowed
  geometry roster to the station-config rows overlapping the active
  `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/config_selection.yaml` stations/date ranges.
  When this is enabled, `z_positions_override_mm` is ignored.
- Supports `adapt_trigger_combinations_for_station_date_range`, which copies the
  `C1..C4` trigger combinations from those same selected station-config rows so
  only real `(geometry, trigger)` pairs are sampled into the mesh.
- Supports append `mode`:
  - `uniform_random` (default): one or more random samples.
  - `regular_mesh`: regular grid over selected parameters around random centers.
- Supports `repeat_samples`, `shared_columns`, and `expand_z_positions` for scan design.
- Appends only when all existing rows are marked `done=1` unless `--force` or runtime `force: true`.

Run:
```
python3 step_0_setup_to_blank.py --config config_step_0_physics.yaml
```

Notes:
- Step IDs are normalized to 3-digit strings.
- `step_1_id` is based on (cos_n, flux_cm2_min), `step_2_id` on (z_p1..z_p4),
  `step_3_id` on (eff_p1..eff_p4). Steps 4..10 default to "001".
