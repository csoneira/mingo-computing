# Stage-1 product tests and studies

Reusable test drivers, configurations, and unit tests remain at this directory's top level. Each completed analysis/test run is archived under a date directory named exactly `YYYY-MM-DD`, with one descriptively named folder per study:

- `2026-10-29/`: initial TT13 closure and TT14 joint-miss studies.
- `2026-10-30/`: topology/charge gate scans and real-versus-simulation comparisons.
- `2026-11-01/`: angular, geometry, chronological, efficiency-gate, charge-correlation, and stage/topology studies.
- `2026-11-02/`: MINGO02 Task-5 gate studies and corrected acceptance-controlled MINGO02-versus-MINGO00 per-plane efficiencies.

Keep each run's scripts, exact configuration, summaries, CSVs, and figures together. Do not copy source Parquet data into a report folder unless a test specifically requires a frozen fixture; document the lake path and file names instead. Generated plots and tabular outputs are ignored by Git in this repository, while scripts and Markdown summaries can be versioned.

Analysis scripts write outputs beside their dated study bundle. Source and documentation references point to the dated archive.
