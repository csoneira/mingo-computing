# STEP 9 (Trigger)

Purpose:
- Apply plane-coincidence trigger logic and retain passing events.

Inputs:
- Physics config: `config_step_9_physics.yaml`
- Runtime config: `config_step_9_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_8_TO_9/SIM_RUN_<N>/step_8.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_9_TO_10/SIM_RUN_<N>/step_9.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_9_TO_10/SIM_RUN_<N>/PLOTS/step_9_plots.pdf`

Algorithm highlights:
- A plane is active if any strip has `Q_front > 0` or `Q_back > 0`.
- `tt_trigger` concatenates active plane indices (1..4).
- Events pass if any trigger combination is a subset of the active planes.

Run:
```
python3 step_9_threshold_to_trigger.py --config config_step_9_physics.yaml
python3 step_9_threshold_to_trigger.py --config config_step_9_physics.yaml --runtime-config config_step_9_runtime.yaml
python3 step_9_threshold_to_trigger.py --config config_step_9_physics.yaml --plot-only
```

Notes:
- The step filters events; output row count is typically reduced.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
