# STEP 2 (Generated -> Crossing)

Purpose:
- Propagate muon trajectories through plane geometry and compute crossings.

Inputs:
- Physics config: `config_step_2_physics.yaml`
- Runtime config: `config_step_2_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2/SIM_RUN_<N>/muon_sample_<N>.(pkl|csv)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/SIM_RUN_<N>/step_2.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/SIM_RUN_<N>/PLOTS/step_2_plots.pdf`

Algorithm highlights:
- For each plane position z_i:
  - `X_gen_i = X_gen + dz_i * tan(theta) * cos(phi)`
  - `Y_gen_i = Y_gen + dz_i * tan(theta) * sin(phi)`
  - `T_sum_i_ns = dz_i / (c_mm_per_ns * cos(theta))`
- Per-event times are shifted so the earliest valid plane is at time 0.
- Events with no in-bounds crossings are dropped.

Run:
```
python3 step_2_generated_to_crossing.py --config config_step_2_physics.yaml
python3 step_2_generated_to_crossing.py --config config_step_2_physics.yaml --runtime-config config_step_2_runtime.yaml
python3 step_2_generated_to_crossing.py --config config_step_2_physics.yaml --plot-only
```

Notes:
- `z_positions` can be a 4-value list or `random` (from `param_mesh.csv`).
- `normalize_to_first_plane` (runtime) shifts z positions so plane 1 is at z = 0.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
- `active_area_bounds_mm` is the active gas rectangle and alone controls crossing acceptance.
- `bounds_mm` remains accepted as a deprecated alias; `active_area_bounds_mm` wins if both exist.
- The normalized active rectangle and its source are stored in metadata under `active_area_bounds_mm` and `active_area_geometry_source`.
- Readout-strip dimensions belong only to STEP 4 and never expand or clip this avalanche-production region.
