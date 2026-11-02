# TT13 P2 efficiency and gate dependence

Read-only exploratory scan, using the existing TT13 gate-scan configuration and code.

## Cohort

- MINGO00: all 93 current postprocessed simulation files, each grouped by its verified simulation parameter hash.
- MINGO01: 175 files with an exact HV assignment in the existing matched-source manifest, aggregated into 7 HV groups.
- Other current MINGO01 files were excluded because their HV settings are not mapped. No HV point was inferred.
- Per-setting/per-HV results are retained in `closure_and_scan.csv`; group input audit is in `input_audit.json`.

## Definitions

For each gate, with N1234, N134, N123 and N13:

- Count-estimated P2 efficiency from the P1/P3/P4 sample: `N1234 / (N1234 + N134)`.
- Count-estimated P2 efficiency from the P1/P3 sample: `N123 / (N123 + N13)`.
- Closure: observed P2 miss fraction divided by predicted P2 miss fraction.
- MINGO00 exact P2 efficiency comes from the digital-twin input settings.

`config_used.yaml` records the actual thresholds. Charge thresholds require both P1 and P3 charges above the threshold and below 300 ADC units. The data count-estimated efficiency is not an independent truth measurement; closure also uses its predicted estimate in the denominator.

## Summary

Baseline closure medians (IQR): MINGO00 0.891 (0.844–0.916), MINGO01 0.896 (0.879–0.907). The numerical predicted-efficiency estimate tracks exact simulation P2 efficiency strongly (Spearman rho 0.993; median bias +1.6 percentage points), but closure decreases with configured P2 efficiency (rho -0.72 baseline). Among simulation settings with exact P2 efficiency 90–100%, baseline closure median is 0.761 (10 settings); MINGO01 baseline closure median is 0.896.

TimTrack chi2 < 10 brings median closure to 0.787 (simulation) and 0.796 (data), so the two samples become similar but both move farther below unity. Middle-strip cuts retain much less data (median 7.4% simulation / 16.5% data for middle_P1_P3; 3.2% / 7.9% for middle_all_active), so those results need low-statistics caution.

The charge-threshold scan shows a divergence at high thresholds: for P1,P3 charge >40, median closure is 0.864 in simulation (81 settings with valid ratios) vs 1.80 in data (7 HV groups). At >80, medians are 0.614 (26 simulation settings) vs 5.12 (6 HV groups), with very sparse TT134/TT13 cells; treat these as suggestive, not stable estimates.

The Telegram PDF contains three scatter views per fixed gate and per threshold family: closure vs exact simulated efficiency; closure vs count-estimated efficiency; and the two count-estimated efficiencies against each other.
