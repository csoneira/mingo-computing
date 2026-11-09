# STEP 7 (Front/Back -> Uncalibrated)

Purpose:
- Apply per-channel cable/connector offsets to front/back times.

Inputs:
- Physics config: `config_step_7_physics.yaml`
- Runtime config: `config_step_7_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_6_TO_7/SIM_RUN_<N>/step_6.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_7_TO_8/SIM_RUN_<N>/step_7.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_7_TO_8/SIM_RUN_<N>/PLOTS/step_7_plots.pdf`

Algorithm highlights:
- `T_front` and `T_back` receive per-channel offsets from `tfront_offsets` and `tback_offsets`.
- Charges are preserved unchanged.

Run:
```
python3 step_7_timing_to_uncalibrated.py --config config_step_7_physics.yaml
python3 step_7_timing_to_uncalibrated.py --config config_step_7_physics.yaml --runtime-config config_step_7_runtime.yaml
python3 step_7_timing_to_uncalibrated.py --config config_step_7_physics.yaml --plot-only
```

Notes:
- The step skips if the target SIM_RUN exists unless `--force` is provided.
