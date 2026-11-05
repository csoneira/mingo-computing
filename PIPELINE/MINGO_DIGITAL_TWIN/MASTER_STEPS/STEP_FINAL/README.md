# STEP FINAL (DAQ -> Station .dat)

Purpose:
- Format STEP 10 data into station-style .dat files and register outputs.

Inputs:
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_10_TO_FINAL/SIM_RUN_<N>/step_10.(pkl|csv|chunks.json)`
- Physics config: `config_step_final_physics.yaml` (currently empty)
- Runtime config: `config_step_final_runtime.yaml`

Outputs:
- `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/mi00YYDDDHHMMSS.dat`
- `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_output_registry.json`
- `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv`

Algorithm highlights:
- Samples `target_rows` events using reservoir or sequential sampling.
- Generates timestamps from `T_thick_s` if present; otherwise uses exponential spacing.
- Writes 71 fields per line: timestamp header + 64 channel values.

Run:
```
python3 step_final_daq_to_station_dat.py --config config_step_final_physics.yaml
python3 step_final_daq_to_station_dat.py --config config_step_final_physics.yaml --runtime-config config_step_final_runtime.yaml
```

Notes:
- `input_sim_run` accepts explicit SIM_RUN, `latest`, `random`, or `all`.
- `input_collect` controls how multiple SIM_RUN inputs are matched.
- STEP FINAL assigns `param_set_id` and `param_date` in the parameter mesh.
- `.dat` outputs start with `# param_hash=<sha256>` matching `step_final_simulation_params.csv`.
- Each new simulation-parameter row records three rates over the exact same
  sequentially sampled `.dat` interval: `particle_crossing_rate_hz`,
  `trigger_rate_unit_efficiency_hz`, and `trigger_rate_hz`. The latter remains
  `(selected_rows - 1) / (last_timestamp - first_timestamp)`. The first two use
  cumulative STEP-9 geometrical counters at the interval boundaries.
- Their ratios define geometrical trigger efficiency, conditional detector-response
  efficiency, and overall detection efficiency. Legacy inputs and non-sequential
  sampling leave the two new fields empty and emit an explicit warning.
- Each new row records `original_rows`, the total available STEP 10 input rows
  before STEP_FINAL sampling, immediately before `requested_rows`.
- Output multiplicity is controlled independently from STEP_0 `repeat_samples`:
  STEP_FINAL writes `files_per_station_conf + len(subsample_rows)` files per
  parameter set. The default runtime config keeps `subsample_rows` empty.
- STEP FINAL requires an exact `SIM_RUN` step-ID lineage match in the current
  parameter mesh. Stale or unmatched final-stage inputs are skipped and never
  remap, append, or consume current mesh rows.
