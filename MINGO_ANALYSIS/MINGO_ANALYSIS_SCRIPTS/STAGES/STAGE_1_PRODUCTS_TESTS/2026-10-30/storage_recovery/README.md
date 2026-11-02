# Storage recovery and simulation restart — 2026-10-30

- Initial disk: 96%, approximately 11 GB available.
- Removed 449 consumed simulation INTERSTEPS run directories, 52.6718 GiB.
  Before deletion, loaded 449 downstream chunk manifests and pickle datasets,
  checked all referenced chunks and exact row counts. Zero validation failures.
  Final-stage inputs and pending mesh prefixes were preserved by this cleanup.
  Audit: consumed_simulation_plan.json; command implementation: cleanup_consumed.py.
- Removed one older-than-24h, pre-Oct-19 error/completed file with an existing
  valid lake parquet. Preserved October-19+ files. Audit: cleanup_archived_errors.json.
- Did not delete station Parquet Lake files or use the unavailable secondary disk.
- Re-enabled only simulation main cycle, STEP_FINAL and simulated-data ingestion
  cron jobs. Other cron entries retained. Snapshot: crontab.before-sim.txt.
- Disabled automatic backlog purge, set pending cap 20 and enqueue interval 300 s.
  Added RUN_STEP_MAX_COMPLETED_LINES=5 to yield to existing housekeeping regularly.
  The prior scheduler was paused at a worker boundary, its worker allowed to finish,
  then the control process retired; no scientific worker was signalled.
  Actual logs confirmed five-line batches yielding and consumed cascade cleanup.
  The normal cleanup freed additional consumed products as simulation advanced;
  free space remains approximately 60–65 GB instead of climbing toward saturation.
- Removed three undefined obsolete runtime PDF callbacks in Tasks 1–3; original
  calls preserved in their task_N_legacy.py files. No scientific transformation,
  calibration setting or production gate changed.
- Verified new file mi0005199000000, generated after restart, through Tasks 0–5.
  Output: MINGO00/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE/
  postprocessed_mi0005199000000.parquet, 50,000 rows, 420 columns.
- New independent analysis: ANCILLARY/CALCULATIONS_AND_TUNINGS/TT13_GATE_SCAN.
  Configurable charge spectra for each plane, exact TT, gate and condition;
  reference-charge and chi-square threshold scans; per-TT acceptance; known
  simulation input efficiencies. No automatic cut optimization or parquet mutation.
- Results: `../tt13_real_sim_gate_scan/` and the earlier real-only
  `../tt13_charge_gate_scan/` study folders.
  First simulation baseline observed/predicted ratio 0.899 +/- 0.062; spatial
  chi2<5: 0.849 +/- 0.058; TimTrack chi2<10: 0.751 +/- 0.052. These are counting-only
  errors for conditional probabilities. The first baseline alone is compatible
  with unity at about 1.6 sigma. Raw chi-square has TT-dependent degrees of freedom,
  so the low-chi-square populations are not equivalent muon-purity selections.
- Tests: digital twin 35 passed; focused runtime/final plotting 6 passed;
  gate-study unit tests 3 passed. Changed Python compile checks, shell syntax checks,
  YAML parse and focused git diff --check passed. Existing sparse-fit and plot-layout
  warnings were observed during processing; they were not suppressed.

The scientific next step is common reference-track acceptance and independent
validation of gate choices, not selecting whichever threshold forces closure.
The secondary disk remains unavailable; offload is not active.

Combined report completed successfully: 176 input files (175 real + 1 simulation),
8 separate conditions, 49 PNG figures and a valid 49-page PDF. Final disk check:
approximately 63 GB available / 71% used.
