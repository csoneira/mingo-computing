# Task 3 ToT-to-charge calibration order

This study compares plane charge spectra made in two ways from Task 3 ToT
widths:

1. Convert each strip width from ns to fC with the shared ToT calibration, then
   sum the four strip charges for the plane.
2. Sum the four strip widths in ns, then apply the same nonlinear calibration
   once to that sum.

The figure also shows Gamma fits to the plane-summed ToT widths and to each fC
result. Fits use positive finite values with the location fixed at zero; the
histogram display is capped at the 99.5th percentile so the main spectrum stays
legible.

The analysis selects Task 3 `listed_*.parquet` products only when the matching
Task 5 `fitted_*.parquet` input is in `COMPLETED_DIRECTORY` and its Task 5
metadata has `completion_fraction >= 1`. Task 3 products generated before the
new fC columns existed are recalculated from their retained Task 2 ToT columns.

Run from the repository root:

```bash
python3 PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/DATED_STUDIES/2026-11-09/task3_tot_charge_calibration_order/analyze_task3_tot_charge_calibration_order.py --station 1
```

Use `--max-files N` for a recent-file smoke run or `--output-dir PATH` to choose
another output directory. By default, the figure is written to this study's
ignored `PLOTS/` directory.
