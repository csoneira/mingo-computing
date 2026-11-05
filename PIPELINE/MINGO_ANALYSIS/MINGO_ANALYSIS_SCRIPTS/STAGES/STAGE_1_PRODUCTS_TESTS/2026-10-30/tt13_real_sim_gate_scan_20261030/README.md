# TT13 closure and gate study — 30 October 2026

Read-only analysis of completed Task-5 lake parquets. Event classes are exact `tt_task0_raw` values 1234, 134, 123, and 13. For each population, predicted P2 miss = `N134/(N1234+N134)` and observed P2 miss = `N13/(N123+N13)`. The closure ratio is observed/predicted; uncertainty is the existing delta-method propagation of the two binomial fractions.

## Inputs

- MINGO00: six completed simulated files, 50,000 rows each, each kept separate by parameter hash. Their P2 efficiencies range from about 56.0% to 91.5%; geometry and flux also vary, so they are not pooled.
- MINGO01: 175 matched real files across seven distinct P1 HV settings (5.5000–5.7000 kV); each HV point remains separate in setting-level results.
- The existing 4×4 charge-spectra PDF includes baseline, spatial chi-square <5, TimTrack chi-square <10, middle-strip P1/P3, and middle-strip on all active planes.

## Per-file median closure ratio (observed/predicted)

| Population | MINGO00 (6 files) | MINGO01 (175 files) |
|---|---:|---:|
| baseline | 0.865 (0.716–0.915) | 0.905 (0.721–1.068) |
| spatial_chi2_lt5 | 0.824 (0.681–0.880) | 0.835 (0.636–1.021) |
| timtrack_chi2_lt10 | 0.737 (0.606–0.818) | 0.813 (0.615–0.999) |
| middle_P1_P3 | 0.995 (0.778–1.286) | 0.881 (0.477–1.720) |
| middle_all_active | 1.033 (0.725–1.227) | 0.833 (0.512–1.988) |

Per-file ratios are descriptive and can be noisy; the full counts and propagated errors are in `per_file_closure.csv`. The time series `mingo01_per_file_time_series.png` shows substantial point-to-point spread and no clean movement toward unity as P1 HV changes.

## Pooled MINGO01 by fixed HV setting

| P1 HV (kV) | Baseline | Spatial χ² <5 | TimTrack χ² <10 | Middle P1/P3 |
|---:|---:|---:|---:|---:|
| 5.5000 | 0.799 ± 0.045 | 0.735 ± 0.043 | 0.722 ± 0.043 | 0.785 ± 0.103 |
| 5.5333 | 0.896 ± 0.012 | 0.803 ± 0.012 | 0.784 ± 0.011 | 0.869 ± 0.029 |
| 5.5667 | 0.877 ± 0.012 | 0.792 ± 0.011 | 0.776 ± 0.011 | 0.841 ± 0.028 |
| 5.6000 | 0.881 ± 0.012 | 0.814 ± 0.011 | 0.796 ± 0.011 | 0.884 ± 0.030 |
| 5.6333 | 0.919 ± 0.013 | 0.869 ± 0.013 | 0.839 ± 0.013 | 0.925 ± 0.037 |
| 5.6667 | 0.902 ± 0.012 | 0.851 ± 0.012 | 0.832 ± 0.012 | 0.882 ± 0.034 |
| 5.7000 | 0.912 ± 0.014 | 0.868 ± 0.013 | 0.843 ± 0.013 | 0.927 ± 0.041 |

## Interpretation and limits

- Baseline MINGO00 simulation and MINGO01 real data both mostly sit below the equality line. The six simulation-setting ratios span 0.716–0.915; the real per-file median is 0.905, with setting-level ratios about 0.80–0.92.
- The spatial and TimTrack chi-square gates move the median ratio farther below one in both samples; these cuts do not resolve the closure discrepancy.
- The P1/P3 middle-strip gate brings most MINGO00 settings close to unity within their larger statistical errors. MINGO01 remains below unity at each pooled HV setting (0.785–0.927), so this particular topology restriction does not remove the real-data discrepancy.
- The current simulation sample has only six completed parameter settings. Their input efficiency, flux, and plane spacing differ; this is evidence that the baseline bias also appears in simulation, but not yet a controlled same-parameter time series or a causal explanation.
- These are conditional TT populations, not an absolute independent-plane efficiency measurement. Trigger logic, topology classification, acceptance, and event-level dependence can all affect the ratio. Treat gate comparisons as diagnostics, not a noise subtraction or selected physics result.

## Files

- `charge_spectra_and_gate_scan.pdf` — spectra and setting-level gate comparisons.
- `closure_and_scan.csv` — pooled results by simulation parameter hash or real HV point.
- `per_file_closure.csv` — all four TT counts and closure quantities for every file and gate.
- `per_file_observed_vs_predicted.png` — per-file closure scatter by gate.
- `mingo01_per_file_time_series.png` — real per-file closure ratio over time, colored by P1 HV.
- `input_audit.json` — exact parquet files read.

## Raw MINGO00 truth and geometry follow-up — 30 October, 12:30 UTC

The earlier report had only six MINGO00 files that had reached Task 5. At the time of this follow-up the station tree had 11 Task-0 completed `.dat` files, 9 Task-1 completed raw parquets, one Task-1 parquet in PROCESSING, and one additional Task-0 output parquet. I analyzed 11 distinct 50,000-event samples, preserving each simulation parameter setting separately. The active PROCESSING parquet was checked for unchanged inode/size/mtime before and after its read. All 11 TT ratios were below one: median **0.884**, range **0.716–0.992**. This puts the effect in the raw Task-0 TT assignments, before Task-1 filtering and calibration.

### Does the digital-twin model itself predict the effect?

Yes, the current Step-2/Step-3 model predicts the same direction and similar size. For each P1+P3 event in a sample, I joined its sidecar truth row by event ID (one-to-one, complete joins), projected the track through the configured active-area rectangle, and used the configured plane efficiencies. Step 2's geometry decides whether each plane is crossed; Step 3's Poisson-ion model gives the crossing-plane hit probability `1 - (1 - efficiency) ** (1 / abs(cos(theta)))`. This predicts the four TT1234/134/123/13 counts for each setting without fitting to those observed TT counts.

- Observed median closure: **0.884**; full geometry-plus-angle model median: **0.844**. Every one of the 11 observed and modeled ratios is below one.
- Across all 11 separate settings, the four-category goodness-of-fit statistic is χ²=46.48 for 33 degrees of freedom (p=0.060). This is compatible with the model at the conventional 5% threshold, but is borderline and is not proof that the model is complete.
- Ablations isolate an interaction: constant independent efficiencies give closure 1.000; geometry alone gives 1.000; angle response without geometrical acceptance gives median 1.029; combining the actual geometry and angle-dependent response gives median 0.844. The current twin therefore produces the below-one behavior without electronic-noise events.

### The useful gate is generated track angle

The truth-angle gate is particularly diagnostic. Median raw closure across the 11 settings is **1.005** for `Theta_gen < 15°`, **0.985** for `<25°`, **0.957** for `<35°`, and **0.910** for `<45°`. In the 35–45° bin, the median closure is **0.663**; the median fraction of P1+P3 tracks that geometrically crosses P4 is only **1.98%**. Above 45°, P4 has zero geometric crossings in the available samples, so the TT13 closure denominator vanishes and the ratio is undefined.

This is the mechanism indicated by the model: high-angle tracks have a larger modeled hit probability in P2 because of their longer path through the detector, while the fraction that reaches P4's active area collapses with angle. Consequently, P4-missing events include high-angle tracks with an elevated P2 efficiency, and the observed P2 miss fraction in that group is lower than in the P4-hit reference group. This produces closure below one. It is a geometry/response correlation in the simulated detector model, not a noise-only effect. The angle cut is diagnostic; it should not be adopted as an analysis correction without a physics acceptance decision.

### Independent P1–P3 reference-angle check in Task 5

I also estimated direction from only the P1 and P3 positions (`p1_xpos/ypos`, `p3_xpos/ypos`), which are present in every TT population being compared. This avoids using a different all-hit fit for each TT class. For MINGO00, the P1–P3 separation is taken per file from the simulation parameter table; for MINGO01's 30 October data, it is 190 mm from the active station geometry configuration. HV groups remain separate.

The median closure across the seven simulated Task-5 settings falls from **0.974** at `<15°` to **0.908** at `<45°`. For real MINGO01, the median across the seven fixed HV groups falls from **1.215** to **0.938** over the same cuts. The downward angle trend therefore appears in both the simulation and real data. Their low-angle values differ, so this does not establish that the entire real-data discrepancy is explained; it does show the effect is not solely random electronic noise. Full per-HV results are in `reference_pair_angle_summary.csv`.

The separate Task-4 all-hit reconstructed-angle scan (`reconstructed_angle_gate_scan.csv`) shows the same trend but is less suitable for causal interpretation because its fit uses different plane subsets for TT1234, TT134, TT123, and TT13. The common P1–P3 angle scan above is the stronger real-data diagnostic.

### Why only seven MINGO00 files reached Task 5

At the latest queue audit (12:31 UTC): Task 0 had 11 completed and 31 unprocessed files; Task 1 had 9 completed and one processing; Task 2 had 8 completed and one unprocessed; Task 3 had 8 completed; Task 4 had 7 completed and one processing; Task 5 had 7 completed. There are 34 unique files pending against the configured backpressure threshold of 20, so STEP_FINAL is deliberately not ingesting more simulated files. The existing analysis queue is advancing, but this backlog is why the Task-5 sample is smaller than the number of generated MINGO00 files. CPU usage was around 99%, and the resource gate was skipping some scheduled analysis/reprocessing jobs. Task 2 also contains 218 old ERROR_DIRECTORY files, with old file IDs; none of the currently advancing MINGO00 files is in that error set.

There is also a readiness issue for producing *new* simulation settings after the current backlog drains: `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv` is absent, and the run logs show work-cache/sanitize warnings for that missing mesh; `run_step_all` reported zero completed lines in recent cycles. I did not raise the queue limit or create a guessed parameter mesh while the existing queue was saturated and CPU-bound. The 31 already queued MINGO00 files are the safe source for expanding the next analysis pass.

### Reproducible follow-up scripts and outputs

- `geometry_efficiency_check.py` — raw-sidecar join, model and geometry/angle gates.
- `geometry_efficiency_model.csv`, `geometry_and_angle_gates.csv`, `theta_gate_summary.csv`, `theta_cut_scan.csv`, `theta_cut_summary.csv`.
- `geometry_efficiency_model.png`, `gate_decomposition.png`, `theta_cut_scan.png`.
- `reference_pair_angle_scan.py` — common P1–P3 angle gate for real and simulated Task-5 files.
- `reference_pair_angle_scan.csv`, `reference_pair_angle_summary.csv`.
- `reconstructed_angle_gate_scan.py` — secondary all-hit Task-4 angle check.
- `reconstructed_angle_gate_scan.csv`, `reconstructed_angle_gate_summary.csv`.

The scripts read input parquets and sidecars only; they do not modify detector data, production configs, or pipeline queues. Rerunning them will include additional completed files as the backlog drains.


## MINGO00 queue refresh — 30 October, 12:45 UTC

Two more MINGO00 files have advanced since the first raw/model report. The truth-joined raw sample now covers 12 distinct 50,000-event files (600,000 events). All 12 observed closure ratios remain below one: median 0.885, range 0.716–0.992. The geometry/angle model median is 0.850; pooled category test χ²=49.99/36 dof, p=0.061. The ablation remains unchanged: constant-efficiency and geometry-only medians are 1.000; angle-only median 1.028; full geometry plus angle response median 0.850.

With 12 settings, the raw truth-angle cumulative gate has median closure 0.994 for θ<15° and 0.912 for θ<45°. The 35–45° bin median is 0.767, with median P4 geometric crossing fraction 1.70%; the >45° bin still has no P4 crossings. The current Task-5 set is now eight MINGO00 settings, and the common P1–P3 angle scan and MINGO00 Task-5 gate PDF were refreshed for those eight.

The 12:45 UTC queue snapshot was Task 0: 12 completed, 30 unprocessed; Task 1: 10 completed plus one PROCESSING file; Task 2: 8 completed, 1 unprocessed, 1 processing; Tasks 3–5: 8 completed each. The production backpressure gate still blocks new Step-Final ingestion at 33 pending files versus threshold 20. The Task-1 PROCESSING file `raw_mi0005198000000.parquet` remains untouched at 75% completion since 09:44 UTC; it is not actively running.
