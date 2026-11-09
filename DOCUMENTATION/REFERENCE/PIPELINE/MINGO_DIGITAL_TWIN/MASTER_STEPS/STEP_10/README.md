# STEP 10 (DAQ Timing)

Purpose:
- Apply TDC smear and event-level jitter to triggered events.

Inputs:
- Physics config: `config_step_10_physics.yaml`
- Runtime config: `config_step_10_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_9_TO_10/SIM_RUN_<N>/step_9.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_10_TO_FINAL/SIM_RUN_<N>/step_10.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_10_TO_FINAL/SIM_RUN_<N>/PLOTS/step_10_plots.pdf`

Algorithm highlights:
- `tdc_sigma_ns`: Gaussian smear on active channels.
- `jitter_width_ns`: uniform event jitter added to all active channels.
- `daq_jitter_ns` records the applied event-level jitter.

Run:
```
python3 step_10_triggered_to_jitter.py --config config_step_10_physics.yaml
python3 step_10_triggered_to_jitter.py --config config_step_10_physics.yaml --runtime-config config_step_10_runtime.yaml
python3 step_10_triggered_to_jitter.py --config config_step_10_physics.yaml --plot-only
```

Notes:
- Only channels in events with any active strip are jittered.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
