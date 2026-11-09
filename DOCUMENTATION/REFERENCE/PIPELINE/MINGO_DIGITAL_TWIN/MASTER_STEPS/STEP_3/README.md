# STEP 3 (Crossing -> Avalanche)

Purpose:
- Apply per-plane efficiencies and generate avalanche sizes/centroids.

Inputs:
- Physics config: `config_step_3_physics.yaml`
- Runtime config: `config_step_3_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/SIM_RUN_<N>/step_2.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4/SIM_RUN_<N>/step_3.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4/SIM_RUN_<N>/PLOTS/step_3_plots.pdf`

Algorithm highlights:
- Ionization count: `ions ~ Poisson(lambda)`, with `lambda = -ln(1 - eff)`.
- Avalanche size: `ions * exp(alpha * gap_mm) * LogNormal(0, electron_sigma)`.
- Avalanche x/y positions follow plane crossings.

Run:
```
python3 step_3_crossing_to_hit.py --config config_step_3_physics.yaml
python3 step_3_crossing_to_hit.py --config config_step_3_physics.yaml --runtime-config config_step_3_runtime.yaml
python3 step_3_crossing_to_hit.py --config config_step_3_physics.yaml --plot-only
```

Notes:
- `efficiencies` can be a 4-value list, list of lists, or `random` from `param_mesh.csv`.
- The step skips if the target SIM_RUN exists unless `--force` is provided.
- Avalanche positions are copied only from valid STEP 2 active-area crossings.
- STEP 3 does not inspect readout geometry, expand avalanche acceptance, or clip coordinates to strips.
