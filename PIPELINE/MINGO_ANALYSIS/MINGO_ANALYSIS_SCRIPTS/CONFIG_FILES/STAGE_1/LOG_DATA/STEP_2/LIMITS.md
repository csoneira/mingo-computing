# Log-merge limits

`config_step_2.csv` contains provisional, manually reviewed limits inferred
on 2026-09-23 at the user's request. These are not recovered historical limits
or detector operating specifications. The merger replaces excluded cells with
NaN; it does not delete rows or alter source measurements. Bounds are inclusive.

Basis: up to 18 evenly spaced cleaned daily files per log type per station
for MINGO01–03, parsed with the production merger. Samples contained 27,949 HV
rows, 14,411 rate rows, 4,858 rows per sensor type, 14,575 disk rows and 4,863
flow rows. Station 04 was excluded from inference because it is offline.

Observed HV was 0–5.614 and currents 0–0.288 in stored units. Limits of 0–7
and 0–1 retain shutdowns and provide headroom. Flow readings were 0–1044;
0–1500 retains shutdowns and the full sampled range. Temperatures were
10.9–35.1; broad temperature bounds allow seasonal variation. Humidity and
the two percentage disk columns use 0–100. `odroid_DiskFillX` is deliberately
unfiltered: its values reach millions and its units are not established.

Pressure spans 789.8–1013.4 across stations; 650–1100 preserves both pressure
populations. Never infer a single narrow pressure band from pooled stations.

Rate limits preserve zero and allow headroom above the sampled normal ranges.
Asserted/Edge occasionally exceed 31,000 while their 99.9th percentiles are
below 167. Multiplexer1/M2/M3 have 99.9th percentiles below 1422, with isolated
values above 8,000. CM channels have 99.9th percentiles below 43, with extremes
above 1,800. Their upper bounds are 1000/5000/1000 respectively. M4 is treated
separately: its 99th percentile is about 158,361, so its upper bound is 1,000,000;
negative counter overflow and the sampled 4,306,063 extreme are excluded.

High rates may represent real detector noise rather than sensor corruption.
Review excluded readings before using these merged data for scientific cuts.
Raw logs preserve that evidence. Limits do not adapt automatically as data arrive.

Validation on the sampled files masked 13 of 362,642 nonmissing cells
(0.0036%), all station-3 rate readings. No other sampled channels were masked.
Per-station counts are saved locally at
`CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/log_limits_validation.csv`.
