# ONLY_LUT

Minimal conference-poster workflow for the simulated generated-file trigger rate.

It reads only `PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv`,
selects one z-position vector, uses the four simulated efficiencies as LUT
coordinates, and builds a strictly positive rate scale-factor LUT from
`trigger_rate_hz`.

Run with the current default geometry `(0, 145, 290, 435)`:

```bash
python3 build_only_lut.py
```

Choose another geometry:

```bash
python3 build_only_lut.py --z-positions 30 145 290 435
```

Outputs are written under `OUTPUTS/`.
