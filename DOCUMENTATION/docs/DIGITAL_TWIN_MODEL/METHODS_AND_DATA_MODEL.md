---
title: Methods and Data Model
description: Physics assumptions, coordinate conventions, and step-level data products for MINGO_DIGITAL_TWIN.
last_updated: 2026-02-24
status: active
supersedes:
  - methods_overview.md
  - data_dictionary.md
  - coordinate_and_timing_conventions.md
---

# Methods and Data Model

## Table of contents
- [Scope and assumptions](#scope-and-assumptions)
- [Units and conventions](#units-and-conventions)
- [Step-by-step method summary](#step-by-step-method-summary)
- [Step output schema summary](#step-output-schema-summary)
- [Trigger and tag semantics](#trigger-and-tag-semantics)

## Scope and assumptions
- Straight-line transport (no scattering or magnetic field).
- RPC response represented by parameterized efficiencies and avalanche statistics.
- Strip response modeled through geometric charge sharing and electronics effects.
- Event building (STEP_FINAL) is formatting/provenance registration, not physics transformation.

## Units and conventions
- Position: `mm`
- Time: `ns` (except `T_thick_s` in seconds)
- Pre-STEP_8 charge-like quantities are arbitrary units.
- Post-STEP_8 `Q_front`/`Q_back` represent time-walk units (`ns`).

Coordinate frame:
- `+Z`: stack axis
- `+X`, `+Y`: detector plane axes
- `Theta_gen`: polar angle from `+Z`
- `Phi_gen`: azimuth from `+X` toward `+Y`

Geometry/indexing:
- planes `1..4`
- strips `1..4`
- per-plane fields: `<field>_<i>`
- per-plane/strip fields: `<field>_<i>_s<j>`

## Step-by-step method summary

### STEP_0: parameter mesh
- Samples `cos_n`, `flux_cm2_min`, efficiencies, and geometry tuples.
- Assigns step IDs for controlled scan traversal.

### STEP_1: muon generation
Sampling model:
- `X_gen ~ U(-xlim_mm, +xlim_mm)`
- `Y_gen ~ U(-ylim_mm, +ylim_mm)`
- `Z_gen = z_plane_mm`
- `Phi_gen ~ U(-pi, +pi)`
- `Theta_gen = arccos(U^(1/(cos_n + 1)))`

`T_thick_s` is generated from Poisson-like counts per second using flux-derived rate proxy.

### STEP_2: plane crossing
For each plane `i`:
- `dz_i = z_i + Z_gen`
- `X_gen_i = X_gen + dz_i * tan(theta) * cos(phi)`
- `Y_gen_i = Y_gen + dz_i * tan(theta) * sin(phi)`
- `T_sum_i_ns = dz_i / (c_mm_per_ns * cos(theta))`

Only projected points inside `active_area_bounds_mm` are valid. Out-of-active-area crossings are NaN; times are normalized so the earliest valid plane per event is zero.

### STEP_3: avalanche
- ionization count: `ions_i ~ Poisson(-ln(1 - eff_i))`
- avalanche size: `ions_i * exp(alpha * gap_mm) * LogNormal(0, sigma)`
- avalanche centroid follows a valid Step 2 crossing exactly.

A larger or translated readout cannot produce an avalanche outside the active gas area, and avalanche coordinates are not clipped to readout strips.

### STEP_4: induction and strip coupling
- avalanche electrons are converted to gap charge in `fC`, then to induced charge with `induced_charge_fraction`.
- charge sharing uses an isotropic 2D Lorentzian normalized over the full plane.
- each strip charge is the exact Lorentzian integral over its configured absolute strip rectangle.
- charge in inactive inter-strip gaps and outside the readout remains unassigned; strip charges are not renormalized.
- `readout_assigned_fraction_i`, `readout_gap_fraction_i`, `readout_outside_fraction_i`, and `readout_bounding_fraction_i` expose this partition without redefining an old field.

The active gas area controls where avalanches may be produced. The readout geometry controls where induced charge is collected. The two geometries are independent and may overlap only partially. Neither coordinate system is assumed centered, symmetric, or identical to the other.

### STEP_5: difference observables
- `T_diff = X_mea * (3 / (2 * c_mm_per_ns))`
- `q_diff ~ Normal(0, qdiff_width)`

### STEP_6: front/back conversion
- `T_front = T_sum_meas - T_diff`
- `T_back  = T_sum_meas + T_diff`
- `Q_front = Y_mea - q_diff`
- `Q_back  = Y_mea + q_diff`

### STEP_7: cable offsets
- per-channel offsets added to `T_front` and `T_back`.

### STEP_8: FEE model
- Gaussian timing jitter.
- charge-to-time-walk conversion and channel offsets.
- thresholding (`charge_threshold`) zeroes low signals.

### STEP_9: trigger
- plane considered active if any strip has positive front/back Q.
- `tt_trigger` is the sorted concatenation of active planes.
- events pass if configured trigger combination is a subset of active planes.

### STEP_10: DAQ jitter
- per-channel Gaussian TDC smear.
- event-level uniform jitter for active channels (`daq_jitter_ns`).

### STEP_FINAL: station formatting
- writes ASCII lines with timestamp header + 64 channels.
- channel order: plane `[4,3,2,1]`, field `[T_front,T_back,Q_front,Q_back]`, strip `[1..4]`.
- writes an atomic parquet sidecar from the exact sampled STEP_10 rows that produced
  each `.dat`; the sidecar is truncated whenever midnight truncation shortens the `.dat`.
- sidecar `event_id` matches the physical `.dat` line number expected by Task 0, while
  `sim_event_id` preserves the upstream simulation event identifier.

## Step output schema summary

Common columns:
- `event_id`
- optional `T_thick_s`

STEP-specific additions:
- STEP_1: `X_gen`, `Y_gen`, `Z_gen`, `Theta_gen`, `Phi_gen`
- STEP_2: `X_gen_i`, `Y_gen_i`, `Z_gen_i`, `T_sum_i_ns`, `tt_crossing`
- STEP_3: `avalanche_ion_i`, `avalanche_exists_i`, `avalanche_x_i`, `avalanche_y_i`, `avalanche_size_electrons_i`, `tt_avalanche`
- STEP_4: `Y_mea_i_sj`, `X_mea_i_sj`, `T_sum_meas_i_sj`, four readout-fraction diagnostics per plane, `tt_hit`
- STEP_5: `T_diff_i_sj`, `q_diff_i_sj`
- STEP_6/7/8/9/10: `T_front_i_sj`, `T_back_i_sj`, `Q_front_i_sj`, `Q_back_i_sj`
- STEP_9: `tt_trigger`
- STEP_10: `daq_jitter_ns`

Detailed per-step contracts:
- `contracts/STEP_CONTRACTS.md`

## Trigger and tag semantics
- `tt_crossing`, `tt_avalanche`, `tt_hit`, `tt_trigger` are ordered plane strings (`1..4`).
- A missing plane digit means inactive state for that stage.
- Tags are stage-specific and should not be compared as equivalent masks across steps without context.
