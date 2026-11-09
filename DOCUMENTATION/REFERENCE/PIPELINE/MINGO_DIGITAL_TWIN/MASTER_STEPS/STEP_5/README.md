# STEP 5 (Hit -> Signal)

Purpose:
- Derive time-difference and charge-difference observables per strip.

Inputs:
- Physics config: `config_step_5_physics.yaml`
- Runtime config: `config_step_5_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_4_TO_5/SIM_RUN_<N>/step_4.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_5_TO_6/SIM_RUN_<N>/step_5.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_5_TO_6/SIM_RUN_<N>/PLOTS/step_5_plots.pdf`

Algorithm highlights:
- `T_diff = X_mea * (3 / (2 * c_mm_per_ns))`.
- `q_diff ~ Normal(0, qdiff_width)` for hit strips.

Run:
```
python3 step_5_measured_to_triggered.py --config config_step_5_physics.yaml
python3 step_5_measured_to_triggered.py --config config_step_5_physics.yaml --runtime-config config_step_5_runtime.yaml
python3 step_5_measured_to_triggered.py --config config_step_5_physics.yaml --plot-only
```

Notes:
- `c_mm_per_ns` can be specified in config or inherited from upstream metadata.
- `qdiff_width` is the required constant Gaussian sigma in the same units as `Y_mea`.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
