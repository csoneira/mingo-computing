# STEP 8 (Threshold / FEE)

Purpose:
- Apply front-end jitter, charge-to-time conversion, and thresholding.

Inputs:
- Physics config: `config_step_8_physics.yaml`
- Runtime config: `config_step_8_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_7_TO_8/SIM_RUN_<N>/step_7.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_8_TO_9/SIM_RUN_<N>/step_8.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_8_TO_9/SIM_RUN_<N>/PLOTS/step_8_plots.pdf`

Algorithm highlights:
- `T_front` and `T_back` receive Gaussian jitter (`t_fee_sigma_ns`).
- Q values are converted to detector-side width using the configured `charge_conversion_model`.
- The preferred mode is `tot_curve_inverse`, which applies the inverse TOT calibration curve.
- `q_to_time_factor` is kept only as a legacy linear fallback.
- Channels below `charge_threshold` are set to 0.

Run:
```
python3 step_8_uncalibrated_to_threshold.py --config config_step_8_physics.yaml
python3 step_8_uncalibrated_to_threshold.py --config config_step_8_physics.yaml --runtime-config config_step_8_runtime.yaml
python3 step_8_uncalibrated_to_threshold.py --config config_step_8_physics.yaml --plot-only
```

Notes:
- The step skips if the target SIM_RUN exists unless `--force` is provided.
- After this step, Q values are no longer raw charge units.
