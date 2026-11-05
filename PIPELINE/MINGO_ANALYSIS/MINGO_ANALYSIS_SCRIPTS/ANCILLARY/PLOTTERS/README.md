# Metadata reports

Run `bash create_metadata_plots.sh` from this directory, or use its full path.
The analysis crontab runs it every ten minutes under a lock. It uses the
repository virtual environment and logs START, DONE, SKIP and FAIL per report.

Sources were recovered from the parent of Git commit `25a2c2d`, before the
repository reorganization. Paths and imports now use `MINGO_ANALYSIS`, simulation
inputs use `SIMULATION_OUTPUTS`, and trigger columns use the current
`tt_taskN_*` naming. Optional JSON configurations were not present in that
snapshot; the plotters use their existing built-in defaults.

Efficiency-vs-position plots require usable Task 4 efficiency metadata.
Exit code 3 means no usable input and is logged as SKIP, not DONE. Inspect
`efficiency_metadata_reason` in `task_4_metadata_efficiency.csv` when skipped.
Other failures remain nonzero and do not prevent independent reports running.
