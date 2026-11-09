# STEP 4 (Avalanche -> Hit)

Purpose:
- Integrate induced charge over four independently configured readout-strip rectangles per plane.

Inputs:
- Physics config: `config_step_4_physics.yaml`
- Runtime config: `config_step_4_runtime.yaml`
- Data: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4/SIM_RUN_<N>/step_3.(pkl|csv|chunks.json)`

Outputs:
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_4_TO_5/SIM_RUN_<N>/step_4.(pkl|csv|chunks.json)`
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_4_TO_5/SIM_RUN_<N>/PLOTS/step_4_plots.pdf`

Geometry rule:

> The active gas area controls where avalanches may be produced. The readout geometry controls where induced charge is collected. The two geometries are independent and may overlap only partially.

`readout_geometry_mm.planes` must define planes `"1"` through `"4"`. Each plane uses either generated Y coordinates:

```yaml
"1":
  x_min: -150.0
  x_max: 150.0
  y_min: -145.0
  strip_widths_mm: [63.0, 63.0, 63.0, 98.0]
  interstrip_gap_mm: 1.0
  y_max: 145.0  # optional derived-coordinate check
```

or four explicit Y intervals:

```yaml
"1":
  x_min: -150.0
  x_max: 150.0
  strip_y_bounds_mm:
    - [-145.0, -82.0]
    - [-81.0, -18.0]
    - [-17.0, 46.0]
    - [47.0, 145.0]
```

Do not mix the generated and explicit forms in one plane. `interstrip_gap_mm` is an inactive physical gap, not a center-to-center pitch. Charge falling in gaps or outside all strip rectangles remains unassigned and is not renormalized.

An avalanche centered in an inter-strip gap can still induce charge on both adjacent strips. The avalanche is not treated as a point assigned according to its center: its induced charge is a continuous two-dimensional Lorentzian cloud with finite width. Each strip collects the portion of that cloud overlapping its own rectangle, while only the portion geometrically falling inside the inactive gap remains unassigned.

```text
Lorentzian cloud:       ~~~~~~~ peak ~~~~~~~
Strip 1:            [----------]
Gap:                            [ 1 mm ]
Strip 2:                              [----------]
Assigned charge:       strip 1          strip 2
Lost charge:                     gap
```

Algorithm highlights:
- Avalanche electrons are converted to gap charge in `fC`, then scaled by `induced_charge_fraction`.
- An isotropic 2D Lorentzian is centered at the unchanged avalanche coordinate.
- Every `Y_mea_i_sj` is the exact integral over that strip's own `[x_min,x_max] x [y_min,y_max]` rectangle.
- Existing four-strip column names and timing/noise behavior are preserved.
- Diagnostic fractions distinguish the readout bounding rectangle, assigned strips, inactive gaps, and outside-readout loss.

Metadata records geometry schema version 2, normalized active bounds, normalized absolute strip rectangles, sources/fallbacks, and gaps. The canonical normalized readout coordinates are included in the STEP 4 configuration hash.

When `readout_geometry_mm` is absent, STEP 4 emits a warning and reproduces the legacy geometry: active-area X limits, centered odd/even hard-coded widths, and zero gaps.

Run:
```bash
python3 step_4_hit_to_measured.py --config config_step_4_physics.yaml
python3 step_4_hit_to_measured.py --config config_step_4_physics.yaml --runtime-config config_step_4_runtime.yaml
python3 step_4_hit_to_measured.py --config config_step_4_physics.yaml --plot-only
```

The example coordinates in `config_step_4_physics.yaml` are explicitly temporary placeholders. Enter final measured readout coordinates there; enter final active-gas coordinates separately in `../STEP_2/config_step_2_physics.yaml`.
