# TT13 quality and middle-strip gates — 2026-10-29

Read-only study of available MINGO01 Task-5 postprocessed parquets, using the same source-file list and HV assignment as the previous TT13 coincidence study. 175 of 176 candidate files were available. Seven separate P1 HV settings are represented (5.500 kV partial coverage through 5.700 kV); P2–P4 are at 5.65 kV. Production Task-5 gate configuration currently defines all_events only. The additional exploratory gates below were applied in the report script; production configuration was not changed.

For each selection independently: e2 = N1234/(N1234+N134); predicted P2 miss = N134/(N1234+N134); observed P2 miss = N13/(N123+N13). TT categories use tt_task0_raw as in the earlier study. Quality and topology quantities are the downstream values in Task 5, so this explicitly studies the population surviving to this stage. Plot error bars are binomial 1-sigma errors; the two reference samples are disjoint. Ratio uncertainties use first-order propagation. Gates overlap and gate-to-gate differences must not be treated as independent.

## Separate populations

- baseline: every relevant TT event available in the same Task-5 files.
- spatial_chi2_lt5: finite 0 <= event_det_chi2_pos < 5. Exploratory, not an independent straight-muon selection across TT multiplicities.
- timtrack_chi2_lt10: finite 0 <= event_tim_th_chi < 10. Exploratory; this is raw chi-square, not reduced chi-square, and degrees of freedom depend on multiplicity.
- middle_P1_P3: reference planes P1 and P3 each have exactly one positive calibrated strip Qsum, and that strip is s2 or s3 (0100 or 0010 in s1,s2,s3,s4 order). Their middle-strip choices need not be identical. P2 and P4 remain unrestricted. This avoids requiring a P2 hit when measuring its misses.
- middle_all_active: the previous reference-plane requirement plus exactly one middle strip on every plane with positive calibrated Qsum; planes without positive Qsum are allowed. This additional gate is explicitly selection-dependent: it changes acceptance differently for each TT. It does not require P2 to fire.

The strip patterns are computed from the sixteen pN_sM_qsum_cal columns, not assumed from a potentially different stored topology representation. Positive calibrated Qsum is the Task-2 strip-hit convention. Raw TT is charge-based before those calibrations; their possible migrations remain part of the selection and should be examined before physical interpretation.

## Results: observed/predicted P2 miss fraction

| P1 kV | Baseline | Spatial chi2 < 5 | TimTrack chi2 < 10 | Middle P1/P3 | Middle all active |
|---:|---:|---:|---:|---:|---:|
| 5.5000 | 0.799 | 0.735 | 0.722 | 0.785 | 0.781 |
| 5.5333 | 0.896 | 0.803 | 0.784 | 0.869 | 0.842 |
| 5.5667 | 0.877 | 0.792 | 0.776 | 0.841 | 0.825 |
| 5.6000 | 0.881 | 0.814 | 0.796 | 0.884 | 0.822 |
| 5.6333 | 0.919 | 0.869 | 0.839 | 0.925 | 0.844 |
| 5.6667 | 0.902 | 0.851 | 0.832 | 0.882 | 0.844 |
| 5.7000 | 0.912 | 0.868 | 0.843 | 0.927 | 0.896 |

The reference-plane middle-strip cut does not consistently improve closure. The chi-square cuts move ratios farther below one. This must not be interpreted as noise removal or proof of a physical efficiency effect.

## Fit degeneracy check

There are 68,074 TT13 events in the selected Task-5 files, of which 63,122 have finite spatial chi-square. All 63,122 finite values are below 1e-12: a two-point spatial line fit has no redundant spatial measurement. A low spatial chi-square gate therefore passes essentially all fitted TT13 events while removing different fractions of three- and four-plane events. Missing/failed fits are also excluded. In Task 4, TimTrack stores ndf = ndat - npar; two-plane fits occur in the ndf=0 category, so the raw TimTrack chi-square threshold likewise does not select equivalent goodness-of-fit populations across TT.

A rigorous future selection must use quantities available and comparably defined in both populations, preferably based only on reference planes P1/P3: reference timing consistency, matched spatial fiducial acceptance, and extrapolation/acceptance checks for P2/P4. Two reference points alone cannot establish spatial straightness. An independent external track or additional reference measurement would be needed for that validation.

Outputs: tt13_gate_comparison.pdf, tt13_gate_scatter.png, tt13_gate_ratios.png, by_hv.csv, per_file_counts.json, chi2_population_audit.csv, file_audit.json and run_summary.txt. The source script is study.py. Parquets are not rewritten. Initial size/mtime audit confirmed all read input files unchanged.
