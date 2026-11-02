# Acceptance-controlled per-plane efficiencies: MINGO02 vs MINGO00

**Corrected analysis, 2 Nov 2026.** This supersedes the earlier wide-acceptance/single-reference efficiency section in the preliminary MINGO02 report. P1/P4 must not be treated as if they share P2/P3 acceptance.

## Selection and estimator

For each target plane independently, a straight track is fitted using the other three planes. Require `theta < 15°`; the predicted target crossing must satisfy `|X|, |Y| <= 80 mm` for P1/P4 and `<= 100 mm` for P2/P3. A reference track must have a hit in each of its three reference planes. Each topology gate is applied only to those reference planes, so the target plane does not select its own denominator. A target is detected when it has at least one finite, nonzero `Q_sum` strip; a multi-strip target response still counts as a detection. The reported efficiency is target-hit / eligible reference tracks.

MINGO02's ten Task-5 files and 21 same-geometry MINGO00 simulation settings are kept separate. No events, files, HV points, or simulation settings are pooled. MINGO00's configured input efficiency is shown alongside its measured efficiency to check the estimator itself. The MC settings span deliberately varied input efficiencies and are not run-matched predictions for MINGO02.

## All-event gate

| Plane | MINGO02 median efficiency (per-file range) | MINGO00 configured input median (range) | MINGO00 measured median | Median MC measured − input |
|---|---:|---:|---:|---:|
| P1 | 0.729 (0.657–0.749) | 0.739 (0.518–0.909) | 0.703 | −0.033 |
| P2 | 0.909 (0.890–0.919) | 0.751 (0.532–0.915) | 0.752 | +0.005 |
| P3 | 0.859 (0.842–0.884) | 0.750 (0.525–0.904) | 0.765 | +0.011 |
| P4 | 0.777 (0.741–0.801) | 0.726 (0.514–0.886) | 0.691 | −0.038 |

The estimator recovers the MINGO00 configured efficiencies to within a few percentage points at the median, including for the restricted P1/P4 acceptance. MINGO02's P2/P3 medians are above the MINGO00 input medians; both fall inside the broad range of intentionally varied MC settings. That overlap is not proof of a matched simulation/data agreement. A run-matched MC configuration and environmental/HV interval are needed for a stronger comparison.

## Topology gates and statistics

Every gate has its own per-plane efficiency: it is applied to the target's three reference planes before counting target hits. The complete per-file results, denominators, Wilson 68% intervals, exact-one target fractions, and MC truth values are in `fiducial_efficiency_real_vs_simulation.csv`. In MINGO00, the `at_most_1_strip_per_plane` and `at_most_2_adjacent_strips_per_plane` reference gates have no settings with at least 50 eligible tracks. Those comparisons are statistically unavailable, not zero-efficiency results. MINGO02 has usable denominators for these gates. The `at_most_3` and `at_most_4` reference gates retain adequate MINGO00 statistics and reproduce the input efficiencies with median biases of about 0–2 percentage points, depending on plane.

## Scope of other closure plots

The TT13/TT14 combinatorial closure plots use TT populations and topology gates but do **not** apply the target-excluded, plane-specific fiducial estimator above. They are useful population diagnostics, not acceptance-corrected intrinsic plane efficiencies. The earlier P1–P3 angle report also used the wrong z separation (145 mm); the physical P1–P3 separation is 290 mm. Do not use that preliminary angle summary. `MINGO00_vs_MINGO02_task5_gate_closure_2026-11-02.pdf` is a separate updated same-geometry closure comparison with the corrected z positions, but its TT closure values remain non-fiducial.

## Outputs

- `MINGO02_fiducial_plane_efficiency_vs_MINGO00_2026-11-02.pdf`: method, all-event median table, and per-plane/per-gate file-level estimates with MINGO00 input truth.
- `fiducial_efficiency_real_vs_simulation.csv`: all 744 plane/file/gate rows.
- `fiducial_efficiency_real_vs_simulation.py`: read-only analysis implementation.
- `MINGO00_vs_MINGO02_task5_gate_closure_2026-11-02.pdf` and `comparative_gate_closure_mingo00_mingo02.csv`: separate gate/angle closure comparison; not a fiducial efficiency estimator.

The calculations use Task-5 plane positions in mm, the per-file z metadata, and the same `[0,145,290,435] mm` geometry for the selected MINGO00 settings and MINGO02 files.
