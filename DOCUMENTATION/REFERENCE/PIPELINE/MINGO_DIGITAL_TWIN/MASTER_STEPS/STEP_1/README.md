# STEP 1 (Muon Sample)

Purpose:
- Generate primary muon tracks (position, direction, and thick-time tags).

Inputs:
- Physics config: `config_step_1_physics.yaml`
- Runtime config: `config_step_1_runtime.yaml`
- Parameter mesh (optional when `cos_n` or `flux_cm2_min` is `random`).

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2/SIM_RUN_<N>/muon_sample_<N>.(pkl|csv)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2/SIM_RUN_<N>/PLOTS/muon_sample_<N>_plots.pdf`

Algorithm highlights:
- `X_gen ~ U(-xlim_mm, +xlim_mm)`, `Y_gen ~ U(-ylim_mm, +ylim_mm)`.
- `Phi_gen ~ U(-pi, +pi)`, `Theta_gen = arccos(U^(1/(cos_n + 1)))`.
- `T_thick_s` uses a Poisson count-per-second process derived from `flux_cm2_min`.

Run:
```
python3 step_1_blank_to_generated.py --config config_step_1_physics.yaml
python3 step_1_blank_to_generated.py --config config_step_1_physics.yaml --runtime-config config_step_1_runtime.yaml
python3 step_1_blank_to_generated.py --config config_step_1_physics.yaml --plot-only
```

Notes:
- When `cos_n` or `flux_cm2_min` is `random`, values are selected from `param_mesh.csv`.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
