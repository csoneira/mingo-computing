# TT13 closure and time evolution — MINGO01, 2026-10-29

Use disjoint P4-present and P4-absent populations within events containing P1 and P3.

e2 = N1234/(N1234+N134); predicted P2 miss = N134/(N1234+N134). Observed P2 miss = N13/(N13+N123). Independence of P2 and P4 conditional on P1,P3 predicts equality. The equivalent count prediction is N13_pred = N123*N134/N1234. Estimating e2 from N123/(N123+N13) itself would give a tautology and is deliberately avoided.

Exact TT codes are used. Coincidence counts are Task-0 coincidence-only execution metadata, not the mixed acquisition population. Self-trigger Task 1 and Task 2 use identical source-file IDs; raw lineage TT is compared with post-filter recomputed TT. All estimates are conditional hit efficiencies, with charge-based plane-hit definitions, not independently measured intrinsic efficiencies.

## Results by coincidence HV setting

| P1 kV | Observed N13 | Predicted N13 | Predicted miss % | Observed miss % | Observed/predicted probability |
|---:|---:|---:|---:|---:|---:|
| 5.5000 | 650 | 822.4 | 5.328 | 4.259 | 0.799 |
| 5.5333 | 11277 | 12660.1 | 5.305 | 4.753 | 0.896 |
| 5.5667 | 12174 | 13975.9 | 5.564 | 4.882 | 0.877 |
| 5.6000 | 11794 | 13480.4 | 5.171 | 4.553 | 0.881 |
| 5.6333 | 10662 | 11651.4 | 4.524 | 4.156 | 0.919 |
| 5.6667 | 11860 | 13214.1 | 4.837 | 4.363 | 0.902 |
| 5.7000 | 9959 | 10977.5 | 4.674 | 4.259 | 0.911 |

No HV settings are pooled. Coincidence coverage with available datetime bounds starts late in the 5.500 kV point; that point is partial. Self-trigger coverage spans ten P1 settings. P2–P4 are at 5.65 kV for the reported settings. Missing datetime metadata is excluded, not imputed. Full excluded-record summary is in run_summary.txt.

Coincidence observed/predicted fractions are about 0.80–0.92. Unlike TT14 joint misses, TT13 has a modest deficit relative to this independence model. At high coincidence counts the deficit is statistically resolved, but counting significance does not account for trigger acceptance, detector geometry, time variation, electronics correlations, or data selection. Self-trigger ratios are approximately 0.79–0.94 with much larger uncertainties; Task 2 barely changes these results. One self-trigger per-setting Fisher p near 0.046 is uncorrected for multiple comparisons and is not standalone evidence of a physical effect.

## Time and correlation studies

Coincidence uses 1 h acquisition bins, self-trigger 6 h bins; bins are split by exact CAEN settings. Files are indivisible, assigned by their acquisition midpoint, so these are approximate time windows. HV-crossing files are excluded. Metadata snapshots, CAEN snapshots, and source-file assignments are saved in inputs/ and matched_source_records.json. study.py regenerates from current live metadata; use the saved snapshots to freeze this run.

The figures show miss probabilities, their ratios, and conditional P2–P4 odds ratios. Equality predicts probability ratio and odds ratio = 1. Binomial standard errors apply to the two disjoint groups. Odds-ratio intervals use the large-count log approximation; Fisher exact p-values are also saved. Zero-cell intervals are unavailable rather than artificially regularized. Predicted count uncertainties use independent Poisson propagation in N123*N134/N1234.

Within-setting hourly coincidence Pearson correlations range from about 0.05 to 0.87 (21–25 bins for the six fully covered settings). Correlation is not closure: a common temporal trend can produce correlation while the points stay off the diagonal. Pearson results are exploratory, without corrections for temporal autocorrelation, uncertainty in both coordinates, or multiple testing. Self-trigger within-setting correlations have only 3–5 bins and are weakly constrained.

## Essential next work

Repeat with matched reconstruction/processing versions and strict common acquisition intervals for cross-mode comparisons. Inspect plane-hit definition, cut migrations and reference acceptance; measure rates over active seconds; repeat complementary reference pairs. Resolve whether the P2–P4 dependence reflects acceptance, trigger selection, noise or genuine response correlations before using it to estimate contamination. Preserve these checks as routine validation of future noise filtering.
