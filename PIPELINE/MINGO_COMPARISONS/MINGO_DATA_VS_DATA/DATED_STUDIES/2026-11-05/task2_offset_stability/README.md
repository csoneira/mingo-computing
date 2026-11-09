# Task-2 charge-offset stability

Analyzed 75 unique MINGO01 input files from 2026-10-15 03:24 to 2026-11-05 04:28 acquisition time.

Included 46 files whose latest calibration metadata records the three-strip sigmoid as the applied production offset; those points use hollow diamonds.

The per-channel offset plot compares the legacy derivative pedestal estimate, gamma-CDF x0, and the three-strip crosstalk sigmoid center. The offset time series connects file-level points in acquisition order. Its crimson fill is the sigmoid center ± half of its measured 10–90% transition width; the separate second plot shows that full width over time. See the CSV for per-channel median, spread, endpoints, and linear slope.

Source metadata: `/home/mingo/mingo-computing/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1/EVENT_DATA/STEP_1/TASK_2/METADATA/task_2_metadata_calibration.csv`

Reanalysis log: `/home/mingo/mingo-computing/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/MAIN_ANALYSIS/STAGE_1/EVENT_DATA/STEP_1/task2_offset_stability_reanalysis_2026-11-05.log`
