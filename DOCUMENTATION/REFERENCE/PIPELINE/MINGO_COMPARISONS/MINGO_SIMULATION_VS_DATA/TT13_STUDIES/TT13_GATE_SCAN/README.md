# TT13 gate sensitivity and charge spectra

Independent report generator; does not change task gates or parquets.

```bash
.venv/bin/python PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/TT13_STUDIES/TT13_GATE_SCAN/scan.py \
  --real-manifest PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/DATED_STUDIES/2026-10-29/tt13_closure/matched_source_records.json \
  --output PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/TT13_STUDIES/DATED_STUDIES/2026-10-30/tt13_charge_gate_scan
```

Use after MINGO00 has reached Task 5. Rerun to add completed simulation files.
Real files are grouped by the previous exact CAEN HV assignment. Simulated files
are grouped by parameter hash. Never combine differing simulated efficiencies.
Every spectrum page is 4 planes x 4 exact TTs (1234, 134, 123, 13), independently
for each setting and named gate. Each panel overlays events that pass the
selection as a solid line and events that fail it as a dashed line, with counts
in the legend. The baseline has no failing events. The dense threshold scans
remain in the CSV; spectrum pages are limited to the configured named gates to
keep the report readable. Canonical plane charge
pN_qsum is used; zero and nonfinite charges are omitted. Common plot bounds
can truncate tails; counts annotated include those tails. Bins do not filter the
closure calculation. Hz per charge unit uses Task-0 coincidence active seconds
for exactly those source files. Missing exposure falls back to counts per charge
unit. Do not compare calibrated data and simulated charge units physically
without confirming their calibration definitions.

The `spatial_chi2_lt_*` gates use Task-4's `event_det_chi2_pos`. It is the
three-dimensional squared distance of each fired plane's measured point from
the fitted track, summed across fired planes and divided by
`anc_sx**2 + anc_sy**2 + anc_sz**2`. It is a track straightness/residual cut,
not a conventional reduced chi-square divided by degrees of freedom. Its value
and interpretation therefore depend on how many planes contributed to the fit;
two-point fits have no spatial redundancy and can have zero residual. Treat the
threshold scan as exploratory, not as a universal quality probability.

config.yaml controls scan thresholds and spectra binning. Scans save the full
2x2 TT counts and binomial propagated ratio errors. Gates are exploratory: raw
chi-square has multiplicity-dependent degrees of freedom, and the two-plane
spatial fit is degenerate. No threshold is selected automatically to force
agreement. Reference-plane-only charge thresholds and middle-strip gates also
need acceptance validation and independent/held-out confirmation. The plot labels
spatial_chi2_lt5 / timtrack_chi2_lt10 are historical identifiers; their actual
thresholds are recorded in config_used.yaml. Verify common input survival and
processing versions before interpreting real-versus-simulation differences.

CSV retention_TT*_percent columns report each exact TT's acceptance relative to
its baseline; changing acceptance can move ratios without removing noise.
Gaussian ratio errors are undefined for zero cells; such endpoint points remain
in the CSV with their counts and are omitted from threshold error-bar plots.
