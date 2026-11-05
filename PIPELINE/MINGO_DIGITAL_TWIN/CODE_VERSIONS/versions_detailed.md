# Digital Twin Version Details

This file expands the short titles stored in `versions.csv`.

## Version 1

- Status: closed on 2026-02-18
- Title: Initial baseline
- Detail:
  Initial version of the digital twin codebase.

## Version 2

- Status: closed on 2026-03-27
- Title: Angular efficiency update
- Detail:
  Added angular dependence to the efficiency model.

## Version 3

- Status: closed on 2026-03-31
- Title: Q_dif correction
- Detail:
  Corrected the `Q_dif` calculation issue.

## Version 4

- Status: open
- Date opened: 2026-04-01
- Title: Simulation retuning and physical charge-chain refactor
- Detail:
  This version consolidates all development work done on 2026-04-01. During the work session, the short CSV temporarily accumulated multiple incremental rows; those changes are all part of this single version.

- Geometry and T_dif tuning:
  Compared MINGO00 and MINGO01 calibrated `T_dif` distributions.
  Derived an effective active-strip length from data and cross-checked it against a direct physical measurement.
  Updated the simulation geometry to reflect a 276 mm active strip region instead of using the full 300 mm strip span as active area.
  Tuned the transverse position smearing to about 15 mm to better match the real-data `T_dif` edge width.
  Later, after rerunning the T_dif tuning on the updated simulation chain, the
  active X span was slightly relaxed again to the current recommendation of
  284.888 mm total width.
  Added a Step 0 option to adapt the allowed `z_positions` roster to the
  selected real-station date ranges in `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/config_selection.yaml`,
  so the simulation mesh can be restricted to geometries that actually exist in
  the real-data comparison window.
  Extended that Step 0 adaptation so the same selected station-config rows also
  provide the allowed trigger combinations (`C1..C4`), preserving only real
  `(z positions, trigger case)` combinations in the simulation mesh.

- Advisory tuning framework:
  Created and organized the `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/SIMULATION_TUNING` area as an advisory-only framework.
  Added shared tuning config and helpers.
  Implemented studies for:
  - active-strip-length / `T_dif`
  - induction-section inference from topology
  - charge spectrum comparison in both `ns` and derived `fC`
  These studies produce recommendations, plots, and reports, but do not mutate simulation configs automatically.

- Charge conversion in the FEE:
  Replaced the ad hoc Step 8 charge-to-width scaling with an inverse use of the real TOT calibration curve when available.
  Kept a linear fallback only for contingency, and set its slope from a regression of the calibration table.

- Physical charge chain:
  Made the Step 4 charge chain explicit:
  avalanche electrons -> gap charge in `fC` -> induced charge in `fC` -> strip sharing -> Step 8 conversion to width in `ns`.
  Added `induced_charge_fraction` as the physical scalar connecting gap charge to induced readout charge.

- Step 4 sharing model:
  Replaced the older geometric/binomial sharing approach.
  First moved to a Lorentzian-based sharing law and then corrected it again to use a truly isotropic radial 2D Lorentzian.
  The final model uses:
  - `lorentzian_gamma_mm` as the only width parameter
  - exact rectangle integrals over the finite detector area and strip bands
  - plotting/debug pages that now show the same isotropic Lorentzian model actually used in the physics
  Also updated the standalone `plot_step_4.py` plotter so it rebuilds a fresh Step 4 plot frame with the live Lorentzian implementation rather than using stale plotting assumptions.
  After the first direct simulation-vs-real topology comparison, `lorentzian_gamma_mm` was first moved to `7.1 mm` using empirical-efficiency matched files.
  Then, after fixing the Step 8 threshold ordering bug (threshold must act before adding the large charge offsets), a local topology sweep suggested a more practical next test point of:
  - `lorentzian_gamma_mm = 5.0 mm`
  - `induced_charge_fraction = 0.6`
  because that regime gives mostly singles, many doubles, some triples, and very few quads in the corrected Step 8 topology.
  The temporary experimental Step 4/Step 8 ids used during that sweep were then restored to `001` so the existing scheduler and param-mesh lineage for Steps 4-10 continue to recognize the tuned physics without requiring orchestration changes.
  After the first fresh end-to-end MINGO00 rerun with those values, the matched simulated-vs-real topology study indicated a smaller remaining broadening mismatch, and the live Step 4 gamma was refined from `5.0 mm` to `4.73 mm` while keeping `induced_charge_fraction = 0.6`.

- Simulation knob cleanup:
  Removed dead or legacy knobs that were no longer physically justified in the live chain:
  - removed `avalanche_gain` from Step 3 live use
  - removed `qdiff_frac`
  - made `qdiff_width` mandatory in Step 5
  Simplified Step 4 to use `lorentzian_gamma_mm` as the only live Lorentzian width parameter.

- Documentation alignment:
  Updated simulation docs, Step 4/5 READMEs, tuning reports, and related explanatory material so they describe the current physical chain and current live knobs.
  The FEE threshold was first aligned with a low-charge assumption under the inverse TOT calibration and later set to the current working value corresponding to `60 fC`.
  Later in the same version, the Step 8 logic was corrected so the threshold is applied to the converted signal before adding the large charge offsets; otherwise the threshold was effectively disabled.
