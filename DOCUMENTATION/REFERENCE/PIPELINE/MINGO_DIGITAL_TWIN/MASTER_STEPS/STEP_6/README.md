# STEP 6 (Signal -> Front/Back)

Purpose:
- Convert sum/difference observables into front/back times and charges per strip.

Inputs:
- Physics config: `config_step_6_physics.yaml`
- Runtime config: `config_step_6_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_5_TO_6/SIM_RUN_<N>/step_5.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_6_TO_7/SIM_RUN_<N>/step_6.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_6_TO_7/SIM_RUN_<N>/PLOTS/step_6_plots.pdf`

Algorithm highlights:
- `T_front = T_sum_meas - T_diff`
- `T_back  = T_sum_meas + T_diff`
- `Q_front = Y_mea - q_diff`
- `Q_back  = Y_mea + q_diff`

Run:
```
python3 step_6_triggered_to_timing.py --config config_step_6_physics.yaml
python3 step_6_triggered_to_timing.py --config config_step_6_physics.yaml --runtime-config config_step_6_runtime.yaml
python3 step_6_triggered_to_timing.py --config config_step_6_physics.yaml --plot-only
```

Notes:
- The step skips if the target SIM_RUN exists unless `--force` is provided.
